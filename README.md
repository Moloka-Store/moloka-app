# moloka-app

## 🔴 LAS DOS BASES: cuál es cuál

**Antes de lanzar nada contra una base, comprueba contra cuál la estás lanzando.**

| | ref del proyecto | nombre en Supabase | región | qué es |
|---|---|---|---|---|
| **PRODUCCIÓN** | `ogfbjjdxcltzpygzuyla` | **Moloka** | `eu-west-1` | 🔴 **LA BASE DE VERDAD.** La que usa Elena a diario. Desde una sesión: **sólo lectura** |
| **STAGING** | `lusujlzyndsydibkeija` | moloka-staging | `eu-central-1` | Desechable. Se restaura antes de cada ensayo |

⚠️ **El nombre NO dice cuál es producción.** El proyecto de producción se llama **«Moloka»
a secas** — no dice «producción» por ninguna parte, y el de staging sí lleva su etiqueta.
Fiarse del nombre es exactamente la ambigüedad que hay que evitar: se mira **el ref**.

🔬 **Por qué está escrito aquí y no en la cabeza de nadie.** El 12-ago-2026 una sesión pasó
la mañana entera creyendo que no tenía acceso a producción. Lo tenía: el conector de
Supabase es **de cuenta**, acepta un `project_id` y llega a los dos proyectos. Como sólo se
le había pasado nunca el ref de staging, quedó mentalmente etiquetado como «el conector de
staging». Consecuencia: dos peticiones a Fernando de mediciones que se podían hacer solas.
**No fue un despiste: fue que el dato sólo vivía en la memoria de alguien.**

🔴 **Y NO intentes distinguirlas con una consulta testigo de recuentos: NO FUNCIONA.**
Staging es un **clon restaurado** de producción, así que casi todo coincide. 🔬 Medido el
12-ago-2026, las dos a la vez:

| | producción | staging |
|---|---|---|
| `current_database()` | `postgres` | `postgres` |
| `count(*) from productos` | **455** | **455** |

Iba a dejar aquí justo esa consulta como comprobación de seguridad. Habría dado confianza
falsa en los dos sentidos — que es peor que no tener comprobación.

✅ **Lo que sí distingue** es preguntarle a la API, no a la base, porque el nombre y la
región no se clonan: `list_projects` (o `get_project` con el ref) devuelve el nombre y la
región de la tabla de arriba. Y para dudas rápidas, `eu-west-1` = producción,
`eu-central-1` = staging.

⚠️ Lo que sí cambia entre las dos, pero **sólo sirve en el momento y hay que remedirlo**
(staging vuelve a igualarse en cada restauración): el número de vistas, las filas de
`keepa_escaparate_hist` y la `fecha_foto` viva.

---

## 🔴 DESPUÉS DE CUALQUIER RESTAURACIÓN: correr el canario RLS

**Paso obligatorio, no opcional.** Después de restaurar cualquier base —staging o
producción— hay que ejecutar entero:

```
sql/canario_rls.sql
```

### Por qué

Una tabla con **RLS activa y cero políticas** es invisible para la app y **no avisa**: no
da error, da vacío. Y una vista que la lea con `security_invoker` devuelve 0 filas con la
misma cara de normalidad. Si una política no vuelve tras un restore, lo normal es que
nadie se entere hasta que falte un dato en pantalla — y para entonces ya no se sabe desde
cuándo.

🔬 Medido el 11-ago-2026 en producción: **21 tablas** están así, **20 con datos dentro**
(sólo `web_formato` vacía) y **13.781 filas invisibles**. Y varias vistas `definer`
funcionan hoy *sólo porque son definer*: leen una de esas tablas tapadas.

⚠️ **Las 21 entran en el censo, también la vacía.** Hasta el 12-ago-2026 el censo llevaba
20 —se armó con «las que tienen datos»— y eso hacía que el canario reportase `web_formato`
como 🔴 TAPADA NUEVA **en cada ejecución**. Una alarma permanente se deja de leer, que es
lo contrario de para lo que existe. *Estar vacía hoy no es motivo para excluir nada: puede
llenarse mañana, y entonces estaría tapada CON datos y ya fuera de la lista.*

⚠️ Y el recuento de vistas `definer` **ya no se cita de memoria**: durante un día se dijo
«18» porque se contaban con un `like '%security_invoker=true%'`, que da por definer las que
lo tienen puesto como `on`. Son **13**. La consulta correcta —por opción, no por texto—
está en este mismo canario.

### Qué comprueba

Grita en **los dos sentidos** contra un censo fijado:

- 🔴 **Tapada nueva** — una tabla tapada que no estaba en el censo. Casi siempre es una
  política que no ha vuelto. Es el fallo que mata en silencio.
- 🟡 **Ya no está tapada** — una del censo que ahora tiene política. Puede ser bueno, pero
  hay que enterarse y actualizar el censo, o el censo empieza a mentir.
- 🟡 **Desaparecida** — una del censo que ya no existe.

Probado haciéndolo saltar a propósito: quitando la política del ledger en staging, sale
`🔴🔴 TAPADA NUEVA · 18.461 filas`.

### ⚠️ No vale medirlo con el conector

El conector corre como `postgres`, que tiene `BYPASSRLS`: cuenta todo y no se entera de
nada. Al pasar `v_presencia_pais` a `security_invoker`, el conector decía **508 filas**
mientras la app habría visto **0**. Para comprobar lo que ve la app de verdad:

```sql
begin;
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
select count(*) from public.la_tabla;
rollback;
```

### Si sale una tapada nueva

La política vive en su migración. Las que ya son reaplicables:

| Tabla | Migración |
|---|---|
| `ledger_movimientos` | `migraciones/2026-08-11_ledger_politica_idempotente.sql` |

Si la que falta no está en esa lista, **no la inventes**: mira de qué migración salió y
hazla reaplicable antes de nada, o el problema vuelve en el siguiente restore.

### 🔴 Y en staging, ADEMÁS: cruzar las definiciones contra producción

Dos minutos, y dice de golpe qué objetos quedaron viejos:

```
sql/huella_vistas_entorno.sql
```

Se lanza **tal cual en los dos entornos** y se comparan los `md5`. Lo que difiera es un
objeto cuya definición no es la misma en los dos sitios.

**Por qué es obligatorio y no una curiosidad:** una restauración devuelve el esquema del
backup, y con él **definiciones viejas de objetos que producción ya tiene arreglados**. Un
ensayo hecho sobre eso mide otra cosa **sin avisar** — sale verde y no significa nada.

🔬 Medido el 12-ago-2026, y por eso está aquí: de siete objetos cruzados, seis coincidían
al hash y **`v_escaner_ultimo` no**. Staging conservaba la versión con la clave de
deduplicación corta `(ean, proveedor)` —la que perdía 30 filas— mientras producción tenía
ya la buena, `(ean, proveedor, es_case)`. Nada lo señalaba: la vista existía, respondía y
tenía buena cara.

⚠️ **Dos trampas del método, las dos medidas** (están explicadas dentro del `.sql`):
- El `search_path` **cambia el hash** de la misma vista. Va fijado, y cada fila trae la
  columna `pin_aplicado`: si sale `false`, esa fila **no es comparable**.
- El hash es de la definición **normalizada por Postgres**, no del texto del `.sql`. Sirve
  para comparar **entorno contra entorno**, nunca contra el fichero — eso es el `sha256`
  que imprime `aplicar-migracion.yml`, y mide otra cosa.

---

## ⏳ Las nueve vistas cerradas a `anon` — revisar a los 30 días

El **11-ago-2026** se cerraron a `anon` nueve vistas `definer` que leen tablas tapadas
(`v_amazon_se_despierta`, `v_analisis_auditable`, `v_auditoria_tarifas`,
`v_decisiones_estado`, `v_incidencias_movimientos`, `v_incidencias_resumen`,
`v_incidencias_ultima`, `v_scoreboard_reglas`, `v_sondas_pendientes`).

🔴 **Es un experimento, no un final.** Si al llegar a **~10-sep-2026** nadie ha reportado
nada roto, **las nueve se borran** — junto con `v_estado_asin`, que ya estaba cerrada.

Una vista que no llama nadie **no es inocente**: aparece en cada censo de seguridad,
confunde a quien audita y ya costó medio día de trabajo. Pero el borrado va **después** de
que el revoke demuestre que nadie las usa, no antes.

**Si algo se rompe**, el rollback está al final de
`migraciones/2026-08-11_revoke_anon_9_vistas.sql`, probado (9 → 0 → 9). Y si hace falta
usarlo, **eso es el hallazgo**: hay un consumidor no versionado. Encontrarlo y anotarlo
antes de volver a cerrarlas.

---

## 😴 Cuando BEMS despierte

BEMS está **en pausa** (su API no responde). Los dos workflows tienen el `schedule:`
**comentado a propósito**. El día que vuelva, hay que descomentar **los dos**:

| Fichero | Cron que hay que descomentar |
|---|---|
| `.github/workflows/detector-bems.yml` | `0,30 7-12 * * 1-5` + los repasos de 13:00 y 15:00 |
| `.github/workflows/semanal-bems.yml` | `0 0 * * 4` (jueves) |

🔴 **Si solo se descomenta uno, el otro se queda dormido en silencio.** Por eso están
en la misma tabla y cada fichero cita al otro.

⚠️ **Y antes de darlo por vivo, comprobar que ESCRIBE**, no que corre. Hasta el
11-ago-2026 el semanal corría los jueves, salía en **verde** y no hacía nada: su propio
resumen decía «Funko: no lanzado» tres veces. Desde entonces lleva una guarda que avisa
en amarillo si no lanza ninguna marca, pero la prueba buena es el dato:

```sql
-- 🔑 LOS PRESENTES, no `max(fecha)` a secas: una fila ya marcada agotada NUNCA se vuelve
--    a tocar, así que su fecha queda congelada y arrastra el máximo hacia atrás.
select max(fecha) filter (where presente)::date
  from public.escaner_memoria where proveedor = 'BEMS';
```

Si eso no avanza tras un run, BEMS no está vivo aunque el workflow salga verde.
🔬 El 11-ago-2026 estaba en **26-jun**: 46 días.

---

## ⚠️ Staging es COMPARTIDO

Varias sesiones trabajan sobre esta base a la vez. 🔬 El 11-ago-2026 staging se restauró
**tres veces en una hora**, y una de ellas se llevó por delante una vista ya aplicada y
verificada por otra sesión, que siguió trabajando sobre un ensayo que ya no existía.

- **Quien vaya a restaurar staging, lo anuncia antes.**
- **Quien esté midiendo, re-verifica al terminar** en vez de fiarse de un ensayo de hace
  media hora. Un `count(*)` de comprobación cuesta segundos.

### El rastro está en la propia base

`restaurar-staging.yml` deja constancia en **`public.staging_restauraciones`** (quién,
cuándo, para qué, y el enlace al run). No depende de que dos sesiones se lean entre sí:

```sql
select restaurado_en, quien, motivo from public.staging_restauraciones
 order by restaurado_en desc limit 5;
```

- **Antes** de restaurar, el workflow enseña las últimas cinco y **avisa** si hubo una
  hace menos de una hora: es cuando lo más probable es que alguien esté midiendo.
- **Después** lo apunta, con `if: always()` — una restauración que falla a medias también
  deja staging distinto de como estaba, así que hay que enterarse igual.
- La tabla vive **solo en staging** y no viene en el backup de producción, así que
  sobrevive a la propia restauración.

⚠️ El `concurrency` del workflow impide que dos restauraciones se pisen **entre sí**, pero
no protege a quien está midiendo. Para eso es este rastro.

---

Lo demás —las reglas de la casa, las trampas medidas y cómo se trabaja aquí— está en
[`CLAUDE.md`](CLAUDE.md).
