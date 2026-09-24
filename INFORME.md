# INFORME · Encargo AJ · Topes contra cuelgues en los procesadores de la v1 + por qué el refresco del Trackeador pesa el triple

> **Lo lee:** Fernando y Cowork, al revisar el PR [Moloka-Store/moloka-app#308](https://github.com/Moloka-Store/moloka-app/pull/308), antes de decidir si se fusiona.
> **Hora real:** 24-sep-2026, **09:10:33 Madrid** según Postgres (`now() at time zone 'Europe/Madrid'`); el reloj de la sesión decía 09:10:34. La hora de cierre va en §7.
> 🔴 **Este fichero NO va a `main`.** Solo lo tocan commits suyos (4704360 y el del cierre). Antes de fusionar hay que **borrar el fichero** en un commit y, como `main` se fusiona por squash, **editar el mensaje de squash**: el que propone GitHub encadena los de todos los commits, incluido el «encargo AA» de cfee17f y los del INFORME. En `main` de la v1 **no existe** hoy (`git ls-tree origin/main` no lo lista).

---

## ⚠️ 0 · Lo primero: esta mañana se han lanzado cuatro refrescos seguidos, cada uno más lento

`trackeador_refrescos` en producción, leído a las 09:0x:

| id | empezó (Madrid) | duración |
|---|---|---|
| 244 | 08:15:00 (cron) | 48,3 s |
| 245 | 08:50:06 | 49,8 s |
| 246 | 08:51:46 | 70,1 s |
| 247 | 08:53:46 | 79,9 s |
| **248** | **08:56:07** | **97,3 s** |

- **No los he lanzado yo.** En esta sesión no ha habido ni un REFRESH ni una llamada a `fn_trackeador_refrescar`.
- Entre las 08:56 y las 09:00 entraron en producción tres migraciones: `amz_salud_resenas_y_avisos`, `ventas_puente_impuesto_cero` e `inicio_resumen`.
- Que cada refresco tarde más que el anterior, en una máquina de 1 GB que se reinició sin apagado limpio a las 06:35, es lo que cabría esperar si la memoria no da abasto. Pero **no lo he medido**.
- **Quien los esté lanzando debería saberlo ya.**

---

## 1 · Punto 0 · Punto de partida

```
git fetch
HEAD                                              = cfee17fc9ca06f92603106e5b2c7213f0ae8b766
refs/heads/main                                   = b97d1aee2b38ca03e415a826b9a2b1c3fbd03a33
refs/remotes/origin/main                          = b97d1aee2b38ca03e415a826b9a2b1c3fbd03a33
refs/remotes/origin/claude/hopeful-brown-m8q1wk   = cfee17fc9ca06f92603106e5b2c7213f0ae8b766
git ls-remote: refs/heads/claude/hopeful-brown-m8q1wk = cfee17f…, refs/heads/main = b97d1ae…
```
- La punta era **cfee17f**, sin nada encima, con el árbol limpio y 0 commits por detrás de `main`.
- El clon es superficial y solo traía `main`. La ref remota de la rama se trajo con un `fetch` explícito; `ls-remote` da lo mismo.
- Encima quedan ahora los commits de este encargo (§2).

## 2 · Lo que cambia en el PR

**Commits sobre `main`:**
- `cfee17f` Topes contra cuelgues en los procesadores: timeout del job y keepalives *(mensaje con «encargo AA»: ya estaba publicado y **no reescribo historia publicada**)*.
- `98c1836` Topes contra cuelgues: letra AJ y comentarios que dicen solo lo medido (encargo AJ).
- *(y el de este INFORME.md, que se revierte antes de fusionar)*.

**Ficheros del diff contra `main`** (`git diff --stat origin/main..98c1836`):
```
 .github/workflows/ci-tests-python.yml           |   8 ++
 .github/workflows/procesar-all-listings.yml     |   8 ++
 .github/workflows/procesar-canal-amazon-es.yml  |   8 ++
 .github/workflows/procesar-custom-analytics.yml |   8 ++
 .github/workflows/procesar-internacional.yml    |   8 ++
 .github/workflows/procesar-inventario-fba.yml   |   8 ++
 .github/workflows/procesar-keepa-escaparate.yml |   8 ++
 .github/workflows/procesar-ledger.yml           |   8 ++
 .github/workflows/procesar-paneu-aptos.yml      |   8 ++
 .github/workflows/procesar-transacciones.yml    |   8 ++
 foto_comun.py                                   |  32 +++++-
 test_topes_cuelgue.py                           | 124 ++++++++++++++++++++++++
 12 files changed, 235 insertions(+), 1 deletion(-)
```
Más `INFORME.md`, que no va a `main`.

**Qué ha cambiado respecto a cfee17f (98c1836). Valores y lógica, sin tocar:**
- **La letra:** «encargo AA» → «encargo AJ» en los comentarios de los 9 workflows, en el paso 25 quater del CI y en el docstring del test. `grep -rn --exclude-dir=.git "encargo AA" .` → **0 en el código** (medido en 98c1836). En la punta de la rama salen las citas de este INFORME, que no va a main. Con `.git` incluido salen además el mensaje del commit cfee17f y los reflogs, que no se reescriben.
- **`foto_comun.py`, comentario del connect:** dice solo lo medido. La base de producción se reinició a las 06:35:16 Madrid (04:35:16 UTC, `pg_postmaster_start_time()`) y su registro dice «database system was not properly shut down; automatic recovery in progress». **La causa no está probada y no se afirma.**
- **`foto_comun.py`, límite de los keepalives:** vigilan el tramo TCP hasta el **primer** extremo. Si `SUPABASE_DB_URL` pasa por el pooler (no se sabe: es un secreto), una base caída detrás de él no la ven, y ahí manda el `timeout-minutes` del job.
- **`test_topes_cuelgue.py`:** el mismo cambio en su docstring.

**Lo que no se rehace** (auditado por Cowork):
- `timeout-minutes: 15` en el job de los 9 `procesar-*.yml` (`procesar-custom-analytics` lleva solo su tope);
- `_KEEPALIVES` (30 s + 6×10 s, `tcp_user_timeout` de 90 s);
- `test_topes_cuelgue.py` registrado en CI (paso 25 quater) y en el censo.

## 3 · CI

- **Run:** [35967565939](https://github.com/Moloka-Store/moloka-app/actions/runs/35967565939), sobre `98c1836`, evento `pull_request` (#308). Job `tests` 107529510409: **success**, con los 36 pasos en verde.
- La punta con este INFORME (`4704360`) tiene también su run en verde, el 35968448369 (lo vio el auditor). El commit del cierre lanza otro: su resultado va en el PR.
- **Censo:** `tests en el repo: 30 | declarados aqui: 30` · `Censo OK: los 30 tests del repo tienen su paso.`
- **Salida de `test_topes_cuelgue.py` en el CI** (paso «25 quater»), literal:

```
OK  hay procesar-*.yml que mirar (9 el 24-sep-2026)
OK  procesar-all-listings.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-all-listings.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-all-listings.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-canal-amazon-es.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-canal-amazon-es.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-canal-amazon-es.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-custom-analytics.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-custom-analytics.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-custom-analytics.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-internacional.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-internacional.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-internacional.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-inventario-fba.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-inventario-fba.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-inventario-fba.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-keepa-escaparate.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-keepa-escaparate.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-keepa-escaparate.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-ledger.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-ledger.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-ledger.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-paneu-aptos.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-paneu-aptos.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-paneu-aptos.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  procesar-transacciones.yml · job procesar: tiene timeout-minutes en el JOB
OK  procesar-transacciones.yml · job procesar: el tope (15 min) deja pasar el exito mas largo medido (587 s)
OK  procesar-transacciones.yml · job procesar: y es un tope, no una espera (<= 60 min)
OK  conectar_bd pasa keepalives a psycopg2.connect
OK  conectar_bd pasa keepalives_idle a psycopg2.connect
OK  conectar_bd pasa keepalives_interval a psycopg2.connect
OK  conectar_bd pasa keepalives_count a psycopg2.connect
OK  conectar_bd pasa tcp_user_timeout a psycopg2.connect
OK  keepalives encendidos (=1)
OK  connect_timeout sigue llegando (10)
OK  keepalives: muerta en 60-120 s (idle + interval x count = 90 s)
OK  tcp_user_timeout: 60-120 s (90 s)
OK  la libpq instalada (170011) acepta todas las opciones

TODO OK
```
Ninguna línea `XX`.

**En local**, antes de subir, pasaron las **30 mesas del repo**, con las versiones fijadas del CI (Python 3.11.15, psycopg2-binary 2.9.13 / libpq 17.0.11, openpyxl 3.1.5, supabase 2.31.0, pandas 3.0.0, pyyaml 6.0.3). **La mesa nueva se ha visto roja cinco veces**, rompiendo a propósito lo que vigila:
1. sin el tope del ledger;
2. con el tope en un paso en vez de en el job;
3. conectando sin keepalives;
4. con una opción que libpq no conoce (`keepalive_idle` → `ProgrammingError: invalid dsn`);
5. con keepalives de 10 min.

### Lo medido para elegir los topes (de la sesión anterior, sin cambios)

**Las duraciones:** 622 runs de los 9 `procesar-*.yml`, con la API de GitHub.
- El éxito más largo es paneu-aptos, **587 s**, el 29-jul.
- Desde el 29-jul ninguno pasa de 137 s.
- El ledger dura entre 21 y 67 s.

**Un tope de job apunta `cancelled` en el registro:**
- En staging, run 35843826193, job `v1-cancelado` (`timeout-minutes: 1` a nivel de job): lo cortó a los 87 s, el paso `always()` corrió después y apuntó `resultado = cancelled` en `registro_ejecuciones`.
- En producción, el run del ledger cancelado hoy también quedó apuntado como `cancelled`.
- El CHECK de la tabla admite `success`, `failure` y `cancelled`.
- `procesar-canal-amazon-es.yml` no tiene paso de registro: se quedó fuera a propósito en el encargo H. Lleva el tope igual.

**Los keepalives, probados contra un Postgres 16 local, cortando la red con iptables solo para el puerto de la conexión probada:**

| Caso | Resultado |
|---|---|
| Consulta legítima `pg_sleep(150)` con la base viva | **termina bien** a los 150,0 s |
| Conexión muerta **con** keepalives | `OperationalError: could not receive data from server: Connection timed out` a los **92,1 s** |
| Conexión muerta **sin** keepalives | a los **300 s** seguía colgada (la mató el `timeout 300`) |
| `refrescar_vistas(con,'ledger')` real, cortado a mitad | grita «EL REFRESCO HA REVENTADO: InterfaceError: connection already closed» y devuelve False a los 92,1 s |
| Cierre de un procesador tras ese corte (`cur.close(); con.close()`) | sin excepción; llega a `=== FIN ===` con código 0 |

---

## 4 · Punto 4 · Por qué el refresco del Trackeador pesa el triple (SOLO LECTURA)

**Qué se ha hecho y qué no:**
- Todo con **MOLOKA-PROD-LECTURA**.
- **Sin** EXPLAIN ANALYZE, **sin** REFRESH, **sin** llamar a `fn_trackeador_refrescar` y **sin** ejecutar entera la consulta de ninguna materializada.
- Sí he hecho `EXPLAIN` sin ANALYZE (también `EXPLAIN (VERBOSE)`, que solo planifica) y lecturas ligeras: catálogo, recuentos de tablas base y una prueba de 2.044 llamadas a una función (§4.4).
- En staging, solo un SELECT de `schema_migrations`.

### 4.0 · Las migraciones de la franja, confirmadas con `list_migrations`

Las versiones son UTC. La franja pedida, 23-sep de 08:39 a 21:45 Madrid, es de **06:39 a 19:45 UTC**.

| versión (UTC) | Madrid | nombre | ¿toca el camino del refresco? |
|---|---|---|---|
| 20260923**073516** | 09:35 | `20260923100000_trackeador_nueve_fallos_de_hecho` | **SÍ: redefine `v_trackeador_pantalla`** (y `fn_escalon_umbral_eur`). ⚠️ **El traspaso no la nombra** |
| 20260923**085336** | 10:53 | `trackeador_demanda_del_cartero` | **SÍ: redefine `v_trackeador_precio_pais`** (CTE `dem`), por `execute format('create or replace view public.%I …')` |
| 20260923095931 | 11:59 | `registro_ejecuciones` | no |
| 20260923102102 | 12:21 | `amz_salud_cuenta_semana` | no |
| 20260923125810 | 14:58 | `frescura_comentarios_y_permiso` | no (`fn_trackeador_frescura`, fuera del árbol) |
| 20260923133059 | 15:30 | `guia_precios_ia` | no |
| 20260923**133352** | 15:33 | `recomendacion_precio_ia` | no: **lee** `mv_trackeador_pantalla`, no la cambia |
| 20260923**133652** | 15:36 | `ia_paquete_del_dia` | no: lee |
| 20260923**141026** | 16:10 | `20260923190000_devoluciones_asin_90d` (**P2**) | no (`v_devoluciones_asin_90d`, fuera del árbol) |
| 20260923**153146** | 17:31 | `20260923200000_retirar_demanda_manual` (**P3**) | no |
| 20260923**155633** | 17:56 | `ia_arrastre` | no: lee |
| 20260923172316 | 19:23 | `balda_i3` | no |

- **Ojo con el traspaso: mezcla nombres de fichero con versiones.** «20260923190000 (P2)» y «20260923200000 (P3)» son los prefijos de fichero; sus versiones en la base son **141026** y **153146**.
- **Cómo se ha decidido «toca / no toca», por estructura:** primero el árbol de `pg_depend`/`pg_rewrite` de las 4 materializadas, que da 52 relaciones más las funciones que llaman sus vistas; después, qué migración crea o reemplaza alguna de esas piezas, mirando su `statements`.
- **Dos trampas de la búsqueda por texto:**
  - `demanda_del_cartero` **no aparece** como «create … v_trackeador_precio_pais» porque usa un `execute format` dinámico: se ha confirmado leyendo su SQL.
  - En P3 salía un falso «redefine `compras`»: era `created_at`.

### 4.1 · Qué refresca `fn_trackeador_refrescar` y en qué orden

Leído con `pg_get_functiondef('public.fn_trackeador_refrescar(boolean)'::regprocedure)`, en este orden:
1. `insert` en `trackeador_refrescos` y el aviso de «cartero sin correr».
2. `perform fn_fee_override_refresh()`: un `pg_advisory_xact_lock(hashtext('fee_override'))` y un `delete from fee_override`. **Ese cerrojo pone en fila dos refrescos a la vez.** Encaja con que el 22 y el 23 la segunda llamada de las 06:33 tardara 30,4 s en vez de 16, pero **la espera no la he medido**.
3. `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_escalon_fisico`, en su propio bloque.
4. `… mv_escalon_peso`, en su bloque.
5. `… mv_hechos_ficha_pais`, en su bloque.
6. `… mv_trackeador_pantalla`, y comprueba que salen ≥ 1.000 filas.
7. Pone `acabo_el` y `ok = true`. **La duración de `trackeador_refrescos` mide del paso 1 al 7.**
8. Después, **fuera de esa medida**: `fn_precio_historico_llenar(max(fecha_foto))`.

### 4.2 · Definición de hoy y `EXPLAIN` (sin ANALYZE) de cada una

Consultas: `select matviewname, definition from pg_matviews where schemaname='public' and matviewname in (…)`, y `EXPLAIN <definición literal>`.

**`mv_escalon_fisico`** (272 filas, 32 kB): `SELECT DISTINCT ON (asin) … FROM amz_tarifa t WHERE … ORDER BY asin, vigente_desde DESC, …`
```
Unique  (cost=171.82..179.44 rows=307 width=161)
  ->  Sort  (cost=171.82..175.63 rows=1525 width=161)
        Sort Key: asin, vigente_desde DESC, peso_paquete DESC, (((lado_mayor * lado_medio) * lado_menor)) DESC
        ->  Seq Scan on amz_tarifa t  (cost=0.00..91.19 rows=1525 width=161)
              Filter: ((peso_paquete IS NOT NULL) AND (lado_mayor IS NOT NULL) AND (lado_medio IS NOT NULL) AND (lado_menor IS NOT NULL))
```

**`mv_escalon_peso`** (517 filas, 64 kB): `mv_escalon_fisico UNION ALL (amz_ficha agrupada por asin WHERE NOT EXISTS en mv_escalon_fisico)`
```
Append  (cost=0.00..275.80 rows=540 width=127)
  ->  Seq Scan on mv_escalon_fisico f  (cost=0.00..6.72 rows=272 width=79)
  ->  Hash Anti Join  (cost=253.25..266.38 rows=268 width=175)
        Hash Cond: (a.asin = x.asin)
        ->  HashAggregate  (cost=243.13..251.19 rows=537 width=79)
              Group Key: a.asin
              ->  Seq Scan on amz_ficha a  (cost=0.00..182.05 rows=3054 width=42)
                    Filter: ((paquete_peso_g IS NOT NULL) AND (paquete_largo_cm IS NOT NULL) AND (paquete_ancho_cm IS NOT NULL) AND (paquete_alto_cm IS NOT NULL))
        ->  Hash  (cost=6.72..6.72 rows=272 width=11)
              ->  Seq Scan on mv_escalon_fisico x  (cost=0.00..6.72 rows=272 width=11)
```

**`mv_hechos_ficha_pais`** (2.390 filas, 2,2 MB): `SELECT <71 columnas> FROM v_hechos_ficha_pais`. **Coste total estimado: 7.061** (`Hash Left Join (cost=6658.05..7061.07 rows=3165)`). Sus piezas más caras:
```
  CTE pd  -> Unique (cost=2.80..1056.84 rows=1140) -> Incremental Sort -> Index Scan using amz_precio_dia_pkey (rows=11395)
  CTE kee -> Seq Scan on keepa_escaparate k_1  (cost=0.00..745.31 rows=2025)
  ->  Unique  (cost=3657.51..3735.00 rows=57)
        -> Merge Join … -> Sort (rows=6025) -> HashAggregate (cost=3142.34..3217.65 rows=6025)
             Group Key: e_1.asin, lower(e_1.pais), e_1.fecha
             ->  Seq Scan on amz_escalera_oferta e_1  (cost=0.00..1636.11 rows=60249)
  ->  GroupAggregate (cost=691.82..693.83 rows=35)   -- ventana de 30 días de amz_ventas_dia
        ->  Hash Join … Join Filter: ((v_1.fecha <= h.hasta) AND (v_1.fecha >= (h.hasta - 29)))
              ->  Seq Scan on amz_ventas_dia v_1  (cost=0.00..291.63 rows=10463)
```

**`mv_trackeador_pantalla`** (2.044 filas, 3,8 MB): `SELECT <130 columnas>, clock_timestamp() AS refrescada_el, … FROM v_trackeador_pantalla v`.
- `EXPLAIN` sin VERBOSE: **622 líneas y 369 nodos**. Sale de `EXPLAIN SELECT <la definición literal de pg_matviews>`, que se puede repetir.
- **Cabeza del plan:**
```
Hash Left Join  (cost=2298443779.44..2298703147.49 rows=5176995 width=2191)
  Hash Cond: ((k.asin = h.asin) AND (k.dominio = h.dominio))
  ->  WindowAgg  (cost=2298443447.69..2298662693.46 rows=5176995 width=2093)
  …
        ->  Sort  (cost=2298380144.99..2298393087.48 rows=5176995 width=2061)
              ->  Subquery Scan on k  (cost=2286134952.20..2286982685.10 rows=5176995)
                    ->  WindowAgg  (cost=2286134952.20..2286930915.15 rows=5176995)
                          ->  Sort  …
                                ->  Subquery Scan on g  (cost=1814616.95..2275234969.88 rows=5176995)
                                      ->  WindowAgg  (cost=1814616.95..2275002005.10 rows=5176995)      ← el coste salta de 5 M a 2.275 M aquí
                                            ->  Nested Loop  (cost=1666980.90..5096777.41 rows=5176995)
                                                  ->  Merge Left Join … (rows=5176995)
                                                        … Merge Left Join (rows=2575619) … (rows=2004373) … (rows=1642929)
                                                              ->  Hash Left Join  (cost=11137.28..16560.99 rows=1642929)
                                                                    Hash Cond: (p.ean = r.ean)          ← aquí «explota» la estimación
                                                                    ->  Hash Left Join (rows=8978) …
                                                                    ->  Hash (rows=36599) -> Subquery Scan on r
                                                                          -> GroupAggregate  Group Key: e.ean
                                                                               -> Seq Scan on escaner_memoria e (rows=47163)
```
- **Recuentos en el plan:**
  - `mv_hechos_ficha_pais` se lee **7 veces** y `transacciones_movimientos` **14**;
  - `keepa_escaparate_hist` (**92 MB**) se lee **1 vez**;
  - hay 19 CTE, 28 SubPlan y 32 InitPlan.

### 4.3 · Lo que dicen los planes, y lo que NO se puede decir con ellos

1. **Las estimaciones de la pantalla son inservibles para señalar la pieza lenta.**
   - El plan cree que sale **5.176.995 filas**; la copia tiene **2.044**.
   - La «explosión» empieza en `p.ean = r.ean`, pero `r` es `escaner_memoria` **agrupada por EAN**: una fila por EAN, así que ese cruce **no puede multiplicar** filas en la realidad. Es un error de estimación, no un hecho.
   - En el otro sentido, el CTE `ult_ud` (el de F5, sobre el histórico de Keepa) se estima en **26 filas** y lee de verdad **4.069** (recuento directo, abajo).
2. **Las otras tres materializadas son baratas en el plan:** 179, 276 y 7.061 de coste.
3. **La unión nueva de `demanda_del_cartero`** (el CTE `dem`, alias `hd`, que ahora lee `mv_hechos_ficha_pais` en vez de `v_demanda_asin_ultima`) sale como un `Hash Left Join ((p.asin = hd.asin) AND (h_1.dominio = hd.dominio))` de **629 filas** estimadas contra una copia de 2.390. **Nada en el plan la señala como cara.** Tampoco se puede descartar sin ejecutar.

### 4.4 · La medida que SÍ se ha podido hacer sin ejecutar: la vista copia 3.348 veces la misma llamada

`EXPLAIN (VERBOSE)` de la definición de la pantalla (solo planifica, no ejecuta). Salida: **1.001 líneas y 5.642.680 caracteres**. Guardada y analizada con un script; leída entera por programa, no a trozos.

```
apariciones de 'fn_fee_escalon(' en todo el plan:              3.578
apariciones de 'fn_precio_al_margen_escalon(':                    227
nodo WindowAgg (línea 279 del plan VERBOSE, filas_est=5.176.995, coste 2.275.002.005):
    su lista de expresiones de salida ocupa 5.059.364 caracteres
    y contiene 3.348 llamadas a fn_fee_escalon(
```

**Y en la definición de la vista (`pg_get_viewdef`, 94.430 caracteres), `fn_fee_escalon(` aparece solo 16 veces:**

| CTE | `fn_fee_escalon(` | `fn_escalon_umbral_eur(` |
|---|---|---|
| base | 2 | 0 |
| calc | 4 | 0 |
| **pre2** | **8** | 13 |
| fin | 2 | 10 |

**El mecanismo, visto en el plan:**
- La vista es una cadena de **19 CTE** (`ven_pais → … → base → calc → acc → pre → pre2 → fin → fila → fila2 → fila3`) y **ninguno lleva `MATERIALIZED`** (0 en la definición).
- Como cada CTE se usa una sola vez, Postgres los **aplana** en uno solo.
- Cada vez que una columna calculada con `fn_fee_escalon(...)` se usa más abajo, **la llamada se copia entera** en la expresión.
- Resultado: 16 llamadas escritas se convierten en 3.348 copias dentro de un solo nodo, y el plan pesa 5,7 MB.

**Qué metió cada migración:**
- **`nueve_fallos` (23-sep, 09:35)** añadió, en su sustitución #15 («pre2: arrastra y el escalón de 20 € (F3)»), exactamente las **8 llamadas de `pre2`** y 13 de `fn_escalon_umbral_eur`. Contado deshaciendo sus 27 sustituciones declaradas (ancla contra texto nuevo): +8 `fn_fee_escalon`, +23 `fn_escalon_umbral_eur`, +1 lectura de `keepa_escaparate_hist` (el `ult_ud` de F5) y +2 ventanas (`OVER`). **Antes de ella la vista tenía 8 llamadas; desde ella, 16.** Y las nuevas están en `pre2`, casi al fondo de la cadena, así que se copian a través de `fin → fila → fila2 → fila3`.
- **`escalon_por_peso` (21-sep, 16:20)** es la que introdujo `fn_fee_escalon` en la pantalla. Es la única migración entre el refresco de las 09:41 (2,6 s) y el de las 21:45 (16,2 s) de ese día:

| refresco | duración | qué entró antes |
|---|---|---|
| 21-sep 09:41 | 2,6 s | — |
| 21-sep 21:45 | **16,2 s** | `20260921170000_escalon_por_peso` (versión 142003), la **única** migración entre medias |
| 23-sep 08:39 | 16,3 s | — (y la escalera ×4 del cartero YA había entrado, ver abajo) |
| 23-sep 21:45 | **56,1 s** | `nueve_fallos` (**+8 `fn_fee_escalon`**) y `demanda_del_cartero` (cambia `dem`) |

**Coste de cada llamada, medido:**
- 2.044 llamadas a `fn_fee_escalon` con los argumentos de las filas de la copia ya guardada: **108 ms**, o sea **~53 µs por llamada**.
- La consulta: `select … sum(fn_fee_escalon(m.asin, m.dominio, m.fee, m.mi_precio)) from mv_trackeador_pantalla m`, con marcas de `clock_timestamp()`. Lee la copia guardada; **no ejecuta la consulta de la materializada**.
- La función es `LANGUAGE sql STABLE`, con `SET search_path TO ''` (con una cláusula `SET` **nunca se incrusta** en la consulta), y hace 3-5 búsquedas por índice en `tarifa_fba_escalon` (33 filas), `tarifa_fba_sin_precio_bajo` (5) y `mv_escalon_peso` (517).
- **Dos cuentas extremas:**
  - 16 llamadas × 2.044 filas × 53 µs ≈ **1,7 s**;
  - 3.348 copias × 2.044 × 53 µs ≈ **363 s** (techo: los `CASE` no evalúan todas las ramas).
- **Los 40 s que se han sumado caben entre esos dos extremos.** Cuántas copias se evalúan de verdad por fila **no se puede saber sin ejecutar**.

**Descartado con el dato: la escalera del cartero no explica el salto.**
- `amz_escalera_oferta` pasó de ~3.200 filas al día a **14.031** el 23-sep: el cartero miró 248 ASIN de ES en vez de 70.
- Pero esas filas entraron **de 06:38 a 06:47**, según `amz_crudo.tomado_en`. Es decir, **antes** de los cuatro refrescos de 08:35-08:39, que tardaron 16,1-16,9 s, lo de siempre.
- Por tanto el salto de 16 a 56 s vino **después de las 08:39**. En ese tramo, las únicas **migraciones** que cambiaron el camino del refresco son las dos de arriba. Los datos de las tablas base también se mueven durante el día: eso no lo he descartado tabla a tabla.

**La máquina** (`pg_settings`):
- `shared_buffers` 256 MB, `work_mem` 3,5 MB, `hash_mem_multiplier` 2, `max_connections` 60, `jit` off.
- MICRO, 1 GB (dato del panel medido por Cowork, no por mí).

### 4.5 · Conclusión

**Qué pieza creció, según el plan (no hay tiempo medido por materializada):** `mv_trackeador_pantalla`. Las otras tres cuestan poco en el plan y sus definiciones no cambiaron el 23-sep.

**Por qué, lo que está medido:**
- La vista se escribe con 16 llamadas a `fn_fee_escalon`, y al aplanar sus 19 CTE el planificador las **copia 3.348 veces** en una sola expresión de 5 MB.
- **`nueve_fallos` duplicó esas llamadas (de 8 a 16) justo en el CTE más profundo.**
- **Los dos escalones de tiempo** (2,5 → 16 s el 21-sep y 16 → 56 s el 23-sep) **coinciden cada uno con la migración que añadió llamadas a `fn_fee_escalon`**, y el 21-sep no hubo ninguna otra.

**Lo que NO está probado:**
- Que sea esto y no `demanda_del_cartero`, ni cuántos de los 40 s pone cada una. Sin ejecutar no se ve.
- **Y que el desbordamiento de memoria que el panel de Cowork ve en los refrescos venga de aquí.** Según el panel medido por Cowork, a las 06:34 había 1,84 GB comprometidos con un límite de 1,44 GB, en una máquina de 1 GB; eso no lo he medido yo. Es verosímil, porque una expresión de 5 MB se compila en memoria para cada ejecución, pero no lo he medido.

### 4.6 · Arreglos propuestos (ninguno aplicado)

1. **Que la vista deje de copiar las llamadas.**
   - **Qué:** poner `AS MATERIALIZED` en `pre2`, y probar también en `calc` y `fin`. O calcular las tarifas del escalón **una vez por fila** en un `LATERAL (select fn_fee_escalon(...) as fee_19, …)` y usar después solo la columna.
   - **Coste:** una migración en la v2 que cambie `v_trackeador_pantalla` por anclas, como las anteriores, probada antes en staging. El resultado es el mismo, porque las funciones son `STABLE`. Materializar ~2.044 filas × ~1,6 kB son unos 3 MB.
   - **Cómo se sabe que funciona:** en `EXPLAIN (VERBOSE)` las 3.348 copias bajan a unas 16 y el plan de 5,7 MB a una fracción; y el refresco en staging tarda menos.
   - **Es el que ataca el mecanismo medido.**
2. **Un refresco por tanda, no uno por procesador.**
   - **Qué:** hoy cada procesador llama a `fn_trackeador_refrescar`. A las 06:33 fueron dos seguidos (`all-listings` y ledger), con el segundo esperando al primero por el cerrojo de `fee_override`, y dos refrescos de ~50 s encadenados son el doble de tiempo con la carga del refresco (la memoria, según el panel de Cowork). La idea: `pg_try_advisory_lock` y saltar si ya hay uno en marcha, o no refrescar si el último acabó hace menos de N minutos.
   - **Coste:** pequeño. Un cambio en la función, en la v2, o en `_refrescar_trackeador` de `foto_comun.py`, en otro PR (aquí no se toca). Hay que decidir qué pasa con el dato del procesador que llega segundo.
3. **Dar margen a la máquina: de MICRO (1 GB) a SMALL (2 GB).**
   - **Coste:** dinero cada mes (**no lo he consultado**: está en el panel de Supabase) y un reinicio de la base al cambiar, unos minutos, fuera del horario de Elena.
   - **No arregla la causa**, pero quita el riesgo de caída mientras se hace el 1.

**Cómo medirlo sin riesgo** (lo que falta para pasar de «coincide» a «probado»), en la **copia de pruebas**:
- Staging tiene hoy las mismas migraciones del 23-sep (`schema_migrations` de staging: `trackeador_demanda_del_cartero` 20260923083752, …, `ia_arrastre`, `balda_i3`), así que **no conserva el «antes»**.
- Los pasos:
  - (a) Restaurar en staging una copia reciente de producción con `restaurar-staging`.
  - (b) `EXPLAIN (ANALYZE, BUFFERS)` de `SELECT * FROM v_trackeador_pantalla` tal cual: da tiempo y filas reales por nodo.
  - (c) Lo mismo con `pre2 AS MATERIALIZED`, en una copia de la definición como consulta suelta, sin crear nada.
  - (d) Lo mismo con las 8 llamadas de F3 cambiadas por la tarifa sin escalón, para aislar `nueve_fallos`.
  - (e) Mirar la memoria de staging en el panel mientras corre.
- La máquina de staging puede no ser igual: **compararlo en relativo, no en absoluto**.
- **Lo que no he conseguido:** reconstruir aquí la vista «de antes de `nueve_fallos`» deshaciendo sus sustituciones. Sus anclas no casan con el texto vivo (otro formato de `pg_get_viewdef` y cambios posteriores). Por eso **no hay EXPLAIN del «antes»**.

### 4.7 · Consultas usadas (todas con MOLOKA-PROD-LECTURA salvo la indicada)

```sql
-- migraciones
list_migrations   -- herramienta del conector
select version, name from supabase_migrations.schema_migrations where version >= '20260921000000' order by version;
-- (staging, solo lectura) select version, name from supabase_migrations.schema_migrations where version >= '20260920000000' order by version;

-- la función y las definiciones
select pg_get_functiondef('public.fn_trackeador_refrescar(boolean)'::regprocedure);
select pg_get_functiondef('public.fn_fee_override_refresh()'::regprocedure);
select pg_get_functiondef('public.fn_fee_escalon(text,text,numeric,numeric)'::regprocedure);
select matviewname, definition from pg_matviews where schemaname='public'
  and matviewname in ('mv_escalon_fisico','mv_escalon_peso','mv_hechos_ficha_pais','mv_trackeador_pantalla');
select pg_get_viewdef('public.v_trackeador_pantalla'::regclass, false);

-- los planes (SIN ANALYZE)
EXPLAIN <definición literal de cada materializada>;
EXPLAIN (VERBOSE) <definición literal de mv_trackeador_pantalla>;

-- árbol de dependencias (por estructura)
with recursive arbol(oid, raiz, nivel) as (
  select c.oid, c.relname::text, 0 from pg_class c join pg_namespace n on n.oid=c.relnamespace
   where n.nspname='public' and c.relname in ('mv_escalon_fisico','mv_escalon_peso','mv_hechos_ficha_pais','mv_trackeador_pantalla')
  union
  select d.refobjid, a.raiz, a.nivel+1 from arbol a
    join pg_rewrite r on r.ev_class = a.oid
    join pg_depend d on d.objid = r.oid and d.classid='pg_rewrite'::regclass and d.refclassid='pg_class'::regclass and d.refobjid <> a.oid
   where a.nivel < 12)
select raiz, c.relname, c.relkind, min(nivel), c.reltuples::bigint, pg_size_pretty(pg_relation_size(c.oid)) from arbol a join pg_class c on c.oid=a.oid … ;
-- + las funciones que llaman esas vistas (pg_depend con refclassid = pg_proc) y, para cada
--   migración del 21 al 24-sep, qué nombres del árbol crea/reemplaza/nombra en `statements`.

-- el historial de refrescos
select id, empezo_el at time zone 'Europe/Madrid', acabo_el at time zone 'Europe/Madrid',
       round(extract(epoch from acabo_el-empezo_el)::numeric,1) s, ok, filas from public.trackeador_refrescos …;

-- recuentos ligeros (tablas base, no la consulta de ninguna materializada)
select fecha, pais, count(*), count(distinct asin), max(posicion), count(distinct crudo_id)
  from amz_escalera_oferta where fecha between '2026-09-21' and '2026-09-24' group by 1,2;
select e.fecha, (c.tomado_en at time zone 'Europe/Madrid')::timestamp(0), count(*)
  from amz_escalera_oferta e join amz_crudo c on c.id = e.crudo_id where e.fecha between '2026-09-22' and '2026-09-24' group by 1,2;
select (select count(*) from keepa_escaparate where bb_stock <= 1),
       (select count(*) from keepa_escaparate_hist h join keepa_escaparate u
          on u.asin=h.asin and lower(u.dominio)=lower(h.dominio) where u.bb_stock<=1 and h.fecha_foto<=u.fecha_foto);
select name, setting, unit from pg_settings where name in ('work_mem','hash_mem_multiplier','shared_buffers', …);

-- coste por llamada de fn_fee_escalon (2.044 llamadas sobre la copia guardada)
select round(extract(epoch from (z.b - x.a))*1000) ms_total, y.n, …
from (select clock_timestamp() a) x
cross join lateral (select count(*) n, sum(public.fn_fee_escalon(m.asin, m.dominio, m.fee, m.mi_precio) + 0*extract(epoch from x.a)) s
                    from public.mv_trackeador_pantalla m) y
cross join lateral (select clock_timestamp() + 0*y.n * interval '1 s' b) z;
```

---

## 5 · Lo que NO he podido verificar

- **Por qué se reinició la base a las 06:35:16.** El registro que cita Cowork dice «not properly shut down», y hay un desbordamiento de memoria medido en el panel, pero **la causa no está probada**.
- **Cuánto de los +40 s pone `nueve_fallos` y cuánto `demanda_del_cartero`.** Hace falta ejecutar, y eso solo en staging (§4.6).
- **Que la memoria que desborda venga de la expresión de 5 MB.** Es verosímil y no lo he medido.
- **Quién ha lanzado los refrescos de 08:50-08:56** (§0).
- **Si `SUPABASE_DB_URL` pasa por el pooler.** Es un secreto. Lo dice el comentario nuevo de los keepalives.
- **Los keepalives en GitHub Actions contra el Supabase de verdad.** Probados contra un Postgres local; la prueba real será la primera carga tras fusionar.
- **Un procesador entero con la red cortada antes del commit de la carga.** Solo he probado el tramo del refresco y el cierre.
- **El precio del cambio de MICRO a SMALL.**

## 6 · Lo que NO he tocado

- Nada en producción: ni migraciones, ni REFRESH, ni variables, ni secretos, ni relojes.
- La v2: solo he leído sus ficheros.
- No he fusionado nada.
- `procesar-custom-analytics.yml` lleva solo su tope.

## 7 · Auditoría

**Hora de cierre:** 24-sep-2026, **09:17:29 Madrid** según Postgres (`now() at time zone 'Europe/Madrid'`).

Auditor: un subagente que no ha escrito ni una línea del código. Leyó el diff COMPLETO contra `origin/main` (13 ficheros, INFORME incluido), pasó en local cuatro mesas, rompió la mesa nueva en una copia desechable (roja en 5 casos) y leyó el CI. Sin tocar nada.

**Primera pasada (punta 4704360), veredicto literal:**

> VEREDICTO: FUSIONABLE — El diff de código hace exactamente lo que piden los puntos 1-2: los topes a nivel de job en los 9 procesadores, los keepalives, la letra AJ y comentarios que no afirman la causa y recogen el límite del pooler, sin tocar valores ni lógica. El test puede ponerse rojo, está registrado en el CI y en el censo, y el CI está en verde. Los fallos son menores y están en el INFORME (que se revierte) y en el mensaje de squash, que hay que editar al fusionar.

**Sus hallazgos, todos [MENOR], y qué se ha hecho con cada uno:**

| Hallazgo | Qué se ha hecho |
|---|---|
| El squash encadena el mensaje «encargo AA» de cfee17f | Avisado en la cabecera: **editar el mensaje de squash al fusionar** |
| El grep «= 0» no es cierto en la punta (lo cita este INFORME) | Corregido: «0 en el código» |
| Faltaba la hora de cierre en §7 | Puesta arriba |
| Afirmaciones más allá de lo medido (el cerrojo de las 30,4 s, «lo único que cambió», «qué pieza creció», los 1,84 GB, «se cayó», «memoria al límite») | Reescritas como «encaja / según el plan / según el panel de Cowork / no medido» |
| `test_topes_cuelgue.py:19` remitía a un INFORME que no llega a main | Ahora remite al PR #308 |
| «(06:35:16)» sin zona en los 9 yml | Ahora «(06:35:16 Madrid)» |
| Los keepalives llegan también a los tres scripts que usan `conectar_bd` | Informativo: es lo que pide el encargo |

**Segunda pasada, sobre ese delta de comentarios, veredicto literal:**

> VEREDICTO: FUSIONABLE — El delta nuevo solo toca comentarios, el YAML sigue válido y el test pasa; el código cumple los puntos 1-2 del encargo AJ. Antes de fusionar: commit y push, CI en verde, INFORME.md borrado y mensaje de squash editado.

**Antes de fusionar** (lo dice también la regla de la casa):
1. `gh pr checks 308` en verde sobre la punta.
2. `git rev-list --count HEAD..origin/main` = 0.
3. **Borrar INFORME.md** en un commit.
4. **Editar el mensaje de squash.**
5. **El visto bueno de Cowork.**
