# Guion — aplicar a PRODUCCIÓN las dos migraciones del #244

> **Lo ejecuta Fernando, con él delante. Escrito el 28-ago-2026 tras el ensayo completo en staging.**
> Este fichero no aplica nada. Es la lista de pasos y, sobre todo, **la verificación por SQL de después**.

---

## 0. 🔴 ANTES DE NADA — el aviso a Elena

Esta migración toca **`mv_trackeador_pantalla`, `v_trackeador_frescura` y `fn_trackeador_refrescar`**, de los que cuelga la **pantalla del Trackeador**. Se aplica **con Elena avisada y fuera de su horario**.

### Pero midamos el riesgo de verdad, que es menor de lo que parece

⚠️ **NO hay DROP+CREATE de la materializada. No hay ventana sin datos.** Comprobado sobre el fichero que está en `main`: **cero `DROP`** en las dos migraciones.

| Objeto | Cómo lo crea | Qué pasa en producción, donde YA existe |
|---|---|---|
| las 5 vistas | `create or replace view` | reemplaza en sitio: **conserva OID, datos y ACL**; no tira nada de lo que cuelga |
| `mv_trackeador_pantalla` | `create materialized view **if not exists**` | **no-op**. No se borra, no se recrea, no hay que refrescarla |
| los 4 índices | `create index **if not exists**` | no-op |
| tabla y secuencia | `create ... **if not exists**` | no-op |
| las 3 funciones | `create or replace function` | reemplaza el cuerpo |
| `revoke` + `grant` | siempre | se reaplican los mismos valores, dentro de la transacción |

🔑 **Lo que sí hay que vigilar no es un hueco de datos: son los LOCKS.** `CREATE OR REPLACE VIEW` toma un `ACCESS EXCLUSIVE` breve sobre cada vista. Si Elena tiene una consulta leyendo, la migración **espera**. Por eso el workflow ya corre con `PGOPTIONS="-c lock_timeout=5s"`: si no puede coger el lock en 5 s, **falla y no bloquea a nadie**. Falla cerrado, que es lo que se quiere.

🔬 Y el dato de contexto: en staging el `REFRESH ... CONCURRENTLY` tardó **3,6 s con 1.708 filas**. Aquí no hace falta refrescar (la materializada es un no-op), pero queda dicho por si algún día sí.

---

## 1. 🔴 Lo que va a producción ya ROTO, y hay que saberlo antes

`v_doctrina_arranque` y `v_arranque_coste` **ya están rotas hoy en producción** para un usuario logueado. No lo causa esta migración: lo mete en el repo tal cual, porque es una foto.

Las dos son `security_invoker=true` con `authenticated=r`, y con `security_invoker` hace falta permiso en **cada objeto de la cadena**. `authenticated` **no tiene SELECT sobre `doctrina_madres`**, así que dan **42501 permission denied** — no cero filas.

```sql
select 'doctrina_madres' as fuente,
       has_table_privilege('authenticated','public.doctrina_madres','SELECT') as puede
union all
select 'monitor_doctrina',
       has_table_privilege('authenticated','public.monitor_doctrina','SELECT');
```

**No se arregla en esta migración, a propósito.** Es una decisión de permisos sobre producción y es de Fernando: abrir `doctrina_madres` a `authenticated`, o quitarles el GRANT a esas dos vistas, que hoy prometen un acceso que no funciona. Las dos se defienden. **Su propio PR.**

No muerde hoy: ningún código de los dos repos lee las cuatro `*_arranque`.

---

## 2. VERIFICACIÓN PREVIA — lo que se mide ANTES de tocar

> Medido por Fernando el 28-ago-2026 comparando **staging después de aplicar** contra
> **producción antes**. Esto es lo que convierte «creo que es inocuo» en «está medido».
> Si alguna de las tres no da lo esperado, **para**: la migración dejaría de ser un no-op.

### 2.1 · Las firmas: `create or replace` REEMPLAZA, no añade una segunda función

🔴 El riesgo real: **cambiar la firma de una función no la reemplaza, añade una sobrecarga
y la vieja se queda viva**. Pasó de verdad en staging antes del restore, con
`fn_trackeador_frescura` de 3 argumentos y `fn_trackeador_refrescar` sin ninguno.

```sql
select p.proname, pg_get_function_identity_arguments(p.oid) as firma
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and (p.proname like 'fn_trackeador%' or p.proname = 'fn_fee_override_refresh')
 order by 1, 2;
```

Tiene que dar **cinco filas, una por nombre** (ningún nombre repetido):

| función | firma |
|---|---|
| `fn_fee_override_refresh` | *(sin argumentos)* |
| `fn_trackeador_frescura` | `p_horas_refresco numeric, p_dias_normal integer, p_dias_demanda integer, p_dias_compra integer, p_dias_copia integer` |
| `fn_trackeador_refrescar` | `p_relanzar boolean` |
| `fn_trackeador_salud` | *(sin argumentos)* |
| `fn_trackeador_snapshot` | `p_fecha date, p_edad_max interval` |

Son **idénticas** a las que la migración deja en staging. ⇒ el `create or replace` reemplaza
en sitio. **Si aquí apareciera un nombre dos veces, para**: significaría que la migración va a
dejar dos funciones vivas y el llamador elegiría por resolución de tipos, no por lo que se quiso.

*(`fn_trackeador_salud` y `fn_trackeador_snapshot` no las toca esta migración. Están en la
consulta a propósito: si el `like` no las devolviera, sabrías que estás mirando otra base.)*

### 2.2 · El `security_invoker` no se pierde en el `create or replace`

🔴 El riesgo: un `CREATE OR REPLACE VIEW` **sin** la cláusula `WITH` **borra el
`security_invoker` sin error y sin salir en ningún diff**, y la vista pasa a correr como su
dueño. En staging las **nueve** vistas se crearon **de cero** y salieron con `security_invoker=true`
—y `v_sondas_pendientes` **sin** él, igual que producción—: eso prueba que el DDL lleva la
cláusula dentro.

```sql
select c.relname,
       exists (select 1 from unnest(coalesce(c.reloptions,'{}')) o
                where lower(split_part(o,'=',1)) = 'security_invoker'
                  and lower(split_part(o,'=',2)) in ('true','on','yes','1')) as es_invoker
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public'
   and c.relname in ('v_trackeador_precio_pais','v_trackeador_precio_pais_full',
       'v_trackeador_pantalla','v_trackeador_frescura','v_sondas_pendientes',
       'v_reglas_arranque','v_doctrina_arranque','v_sondas_arranque','v_arranque_coste')
 order by 1;
```

Ocho a `true` y **`v_sondas_pendientes` a `false`**, que es la foto.

⚠️ **Se lee POR OPCIÓN, nunca con un `like '%security_invoker=true%'`.** Postgres guarda
literalmente lo que se escribió y acepta sinónimos: `=on` significa lo mismo y un `like`
contaría esas vistas como definer. Ese error ya se cometió aquí dos veces, por separado, y
las dos dieron el mismo recuento equivocado.

### 2.3 · Los cuatro índices ya existen: los `if not exists` son cuatro no-ops

```sql
select indexname, indexdef from pg_indexes
 where schemaname = 'public' and tablename = 'mv_trackeador_pantalla'
 order by indexname;
```

`mv_tp_accion` · `mv_tp_asin` · `mv_tp_orden` · **`mv_tp_pk` (UNIQUE sobre `asin, dominio`)**.

⇒ **Ni construcción de índice ni lock largo.** Si faltara alguno, la migración lo crearía —y
entonces sí habría trabajo real y un lock que medir—, así que conviene saberlo antes.

### 2.4 · El recuento de la materializada: apúntalo, y no lo leas como descuadre

```sql
select count(*) as filas from public.mv_trackeador_pantalla;
```

**Producción va por 1.740 filas y staging por 1.708.** ⚠️ **Eso es VOLUMEN, no descuadre**:
staging viene del volcado de anoche y producción ha seguido viviendo. Sin decirlo, alguien lo
leerá como un fallo.

Lo que importa: **este número tiene que ser el MISMO antes y después de aplicar**, porque la
materializada es un no-op. Apúntalo ahora.

---

## 3. Los pasos, en orden

Los dos ficheros están **en `main`** y **ensayados y aplicados en staging**.

| | Paso | Cómo |
|---|---|---|
| 1 | Avisar a Elena y esperar a estar fuera de su horario | — |
| 2 | **Ensayo en producción** de la migración del Trackeador | `aplicar-migracion.yml` · `entorno=produccion` · `fichero=2026-08-28_repo_trackeador_objetos_vivos.sql` · `modo=ensayo` |
| 3 | Leer el log: tienen que salir las **cinco** líneas de la sección 4 | — |
| 4 | **Aplicar** esa misma | igual, `modo=aplicar` + escribir el nombre del fichero en `confirmacion` |
| 5 | **Verificación por SQL** (sección 5 de abajo) | el log NO es la prueba |
| 6 | Repetir 2→5 con `2026-08-28_repo_arranque_objetos_vivos.sql` | — |

⚠️ **El orden entre las dos migraciones da igual: son independientes.** La del Trackeador no toca nada de arranque y al revés. Se hace primero la del Trackeador porque es la que afecta a Elena, y así se sabe pronto.

📌 **El id del run se toma de la URL que imprime el dispatch**, nunca de `gh run list --limit 1`: el run recién creado tarda unos segundos en registrarse y «el último» puede ser el anterior.

---

## 4. Lo que tiene que decir el log (no es la prueba, pero si falta algo, para)

**Trackeador** — las cinco:
```
Guardas OK. Existian 9 de 9  ← en produccion saldra un WARNING: "los 9 objetos YA EXISTIAN"
Testigo OK. 9 objetos, 4 indices (mv_tp_pk UNIQUE puesto), 2 DEFINER, default de p_relanzar vivo.
Testigo OK (puerta). anon REBOTA en mv_trackeador_pantalla.
Testigo OK (puerta). authenticated LEE mv_trackeador_pantalla, que es la que alimenta la pantalla.
Testigo OK (grant, que no puerta). authenticated tiene SELECT sobre las dos vistas invoker;
```

🔑 **Ese WARNING de «YA EXISTIAN» es lo ESPERADO en producción y no es un fallo**: esta migración es una foto de lo que ya está. En un ensayo de staging significaría lo contrario (que no se tiraron antes y el verde no vale). La guarda lo dice con esas palabras.

**Arranque** — las tres: `Existian 6 de 6` (mismo WARNING) · `6 objetos, 7 madres, v_sondas_pendientes sigue definer` · `anon REBOTA en v_arranque_coste`.

---

## 5. LA VERIFICACIÓN POR SQL — esto sí es la prueba

Se corre **después de aplicar**, contra producción.

### 4.1 · Los 13 md5

```sql
select c.relname as objeto,
       md5(replace(pg_get_viewdef(c.oid,true), chr(13)||chr(10), chr(10))) as md5,
       length(pg_get_viewdef(c.oid,true)) as largo
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public'
   and c.relname in ('v_trackeador_precio_pais','v_trackeador_precio_pais_full',
       'v_trackeador_pantalla','mv_trackeador_pantalla','v_trackeador_frescura',
       'v_sondas_pendientes','v_reglas_arranque','v_doctrina_arranque',
       'v_sondas_arranque','v_arranque_coste')
union all
select p.proname, md5(replace(p.prosrc, chr(13)||chr(10), chr(10))), length(p.prosrc)
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and p.proname in ('fn_fee_override_refresh','fn_trackeador_frescura','fn_trackeador_refrescar')
 order by 1;
```

Tiene que dar exactamente esto (medido en staging tras aplicar):

| objeto | md5 | largo |
|---|---|---|
| `fn_fee_override_refresh` | `54ef7e432e687adb0d9a3f1402f231c8` | 1094 |
| `fn_trackeador_frescura` | `3f9741b060abe2352d437c8ae59c9477` | 3954 |
| `fn_trackeador_refrescar` | `3a6351e01be5d37ffaeb03d282fff5a1` | 1638 |
| `mv_trackeador_pantalla` | `ca8e0c1c319d916a51acfd651f311383` | 2070 |
| `v_arranque_coste` | **`bc2e65814ea23d3784e3976936ed025e`** | **1922** |
| `v_doctrina_arranque` | `1e6ad5908460f8ca4638b8c823a1cdf9` | 542 |
| `v_reglas_arranque` | `80c5efe6d418474c1749cdc51c5f2171` | 871 |
| `v_sondas_arranque` | `b4f164b054a8169baecb17e080e3635c` | 479 |
| `v_sondas_pendientes` | `a92d435f77895df2e2c531009f87b9b8` | 549 |
| `v_trackeador_frescura` | `d1f613c471881da9ffa9bf3083f04c70` | 831 |
| `v_trackeador_pantalla` | `8cc855a9d7d3fff92c54ca7d0d387ecf` | 46026 |
| `v_trackeador_precio_pais` | `66319d0826ba4ccc62ac5391daff619b` | 17046 |
| `v_trackeador_precio_pais_full` | `71a2888d749a6586cc656e3ce812393a` | 7203 |

🔴 **`v_arranque_coste` es la ÚNICA que CAMBIA.** Antes de aplicar, producción da `3c33ce292563114bee1759c85642ebc8` (1.898). Después dará `bc2e6581…` (1.922). **Es lo esperado, no un fallo**: Postgres re-renderiza y añade `AS text` a las ramas 2-4 del `UNION ALL` — tres veces por 8 caracteres, los 24 exactos. Es inerte y es punto fijo. Las otras doce **no se mueven**.

### 4.2 · Las ACL de los objetos

```sql
select c.relname, array_to_string(c.relacl,' | ') as acl
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname='public' and c.relname in ('v_trackeador_precio_pais','v_trackeador_precio_pais_full',
   'v_trackeador_pantalla','mv_trackeador_pantalla','v_trackeador_frescura','trackeador_refrescos',
   'v_sondas_pendientes','doctrina_madres','v_reglas_arranque','v_doctrina_arranque',
   'v_sondas_arranque','v_arranque_coste')
union all
select p.proname||'()', array_to_string(p.proacl,' | ')
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname='public' and p.proname in ('fn_fee_override_refresh','fn_trackeador_frescura','fn_trackeador_refrescar')
 order by 1;
```

Esperado (medido en staging tras aplicar; coincide con producción):

| objeto | ACL |
|---|---|
| las 10 vistas/matview/tabla normales | `postgres=arwdDxtm` · `service_role=arwdDxtm` · **`authenticated=r`** |
| `v_sondas_pendientes` | `authenticated=**arwdDxtm**` — es la foto, y es un frente aparte |
| `doctrina_madres` | `postgres` y `service_role` y **nada más** (RLS activo, 0 políticas) |
| las 3 funciones | `postgres=X` · `service_role=X` · **`=X`** (PUBLIC) — la foto; frente aparte |

🔴 **Y lo que NO debe aparecer en ninguna: `anon`.** Es la mitad que se mueve, así que es la que hay que mirar.

### 4.3 · El índice único y el recuento

```sql
select indexname, indexdef from pg_indexes
 where schemaname='public' and tablename='mv_trackeador_pantalla' order by indexname;
select count(*) as filas from public.mv_trackeador_pantalla;
```

Los **cuatro**: `mv_tp_accion`, `mv_tp_asin`, `mv_tp_orden` y `mv_tp_pk`, este último
`CREATE UNIQUE INDEX mv_tp_pk ON public.mv_trackeador_pantalla USING btree (asin, dominio)`.

🔴 **Sin `mv_tp_pk` el `REFRESH ... CONCURRENTLY` no arranca**, y ése es el que corre en cada carga de cada informe desde `foto_comun.py`. Si falta, para.

El recuento tiene que ser **el mismo** que apuntaste en la sección 2.4 (la materializada es un no-op). Producción va por 1.740 y staging por 1.708: eso es volumen, no descuadre.

### 4.4 · La prueba de verdad: ejercer, no leer el catálogo

```sql
set role authenticated;
select count(*) from (select 1 from public.mv_trackeador_pantalla limit 1) z;   -- tiene que ir
select count(*) from (select * from public.v_trackeador_pantalla limit 0) z;    -- tiene que ir
select count(*) from (select * from public.v_trackeador_frescura limit 0) z;    -- tiene que ir
reset role;

set role anon;
select count(*) from public.mv_trackeador_pantalla;   -- tiene que REBOTAR con 42501
reset role;
```

⚠️ **Estas tres de `authenticated` son las que en staging NO se podían probar** —allí `authenticated` no tiene SELECT en ninguna de las nueve tablas fuente, por el volcado `--no-privileges`—. **En producción sí, y es donde importa.** Si alguna da 42501, la pantalla del Trackeador se queda vacía y **sin error visible**: para y no sigas.

📌 Y las dos rotas conocidas, para no confundirlas con un fallo nuevo:
```sql
set role authenticated;
select * from public.v_doctrina_arranque limit 1;   -- 42501 ESPERADO, ver seccion 1
reset role;
```

---

## 6. Si algo va mal

- **En `ensayo`**: el workflow hace `rollback`. La base se queda como estaba. Se lee el error y se decide.
- **En `aplicar`**: corre con `--single-transaction`, así que un error deja la base **exactamente como estaba**. El propio workflow avisa aparte si detectase `no transaction in progress`, que sería el único caso en que quedaría a medias.
- **Lock ocupado**: falla en 5 s por `lock_timeout`. No bloquea a Elena. Se reintenta cuando esté libre.
- **Vuelta atrás**: no hace falta guion de reversa. Estas migraciones **no borran nada** y son idempotentes; el estado anterior es el mismo salvo el md5 de `v_arranque_coste`, que es inerte.

---

## 7. Lo que este guion NO cubre

- ❌ Que la **pantalla del Trackeador se vea bien** en la app. Eso se abre y se mira. Aquí solo hay base de datos.
- ❌ Los frentes de permisos que la foto reproduce **a propósito**: `SECURITY DEFINER` con `EXECUTE` a PUBLIC en dos funciones, `v_sondas_pendientes` sin `security_invoker`, y las dos vistas rotas de la sección 1. **Cada uno su PR.**
