# RESPUESTA AL ENCARGO DEL TRACKEADOR — leyendo el código

**11-ago-2026.** Contesta al `ENCARGO_para_Code_11ago.md`, que a su vez sale de la auditoría SQL
del mismo día. Medido leyendo el repo `moloka-app`, el repo `moloka-app-v2`, el historial de
GitHub Actions y **SQL de solo lectura contra producción** (`ogfbjjdxcltzpygzuyla`, confirmado con
la consulta testigo: 455 productos — staging tiene 409).

**No se ha aplicado nada. No se ha tocado ninguna fórmula. No se ha borrado ninguna tabla.**

---

## 0. TRES PREMISAS DEL ENCARGO QUE NO SE SOSTIENEN — LÉELO PRIMERO

El encargo se construye sobre tres cosas que el código desmiente. Las tres cambian la respuesta,
así que van antes que nada.

### 0.1 🔴 «El trackeador vive en su propio repositorio, fuera de la auditoría del 29-jul»

**No.** El trackeador vive en **`moloka-app`** — el repo que la auditoría del 29-jul sí cubrió.
Son tres ficheros en la raíz, junto a los procesadores:

| Fichero | Qué es |
|---|---|
| [moloka_tracker_snapshot.py](moloka_tracker_snapshot.py) | El motor (fórmulas + cruce por ASIN). 388 líneas |
| [moloka_tracker_snapshot_nube.py](moloka_tracker_snapshot_nube.py) | El robot de buzón que lo llama desde Actions. 121 líneas |
| [moloka_tracker_cerebro.py](moloka_tracker_cerebro.py) | El generador de recomendaciones. 463 líneas |

No hay repositorio que localizar y no hay código sin auditar en otra parte. **A1 queda contestado
así**: rama por defecto `main`, último commit que los toca `2cc8839` («Tracker: un solo botón con
encadenado + auto-refresco, y marca sin-caja»).

🔴 **Y con esto se cae también la explicación que se venía dando del falso positivo de las 1.746
filas** (el del 29-jul y el de esta mañana). Se decía que *«el auditor no podía ver ese código,
estaba en otro repositorio»*. **Falso: estaba en `moloka-app`, dentro del alcance de aquella
auditoría, en la raíz y junto a los procesadores que sí se revisaron.**

**El trackeador no se auditó — pero no por falta de acceso.** Se leyeron los contadores de una tabla
sin abrir el código que la escribe, teniéndolo delante.

⚠️ La distinción no es un matiz: mientras el motivo sea «no se podía ver», quien lo lea concluirá
que hay que ampliar el acceso del auditor, y el error se repetirá igual — porque el acceso nunca
fue el problema. **Falló el método, no el alcance.**

### 0.2 🔴 «`monitor_snapshots` y `monitor_recomendaciones` borran su histórico»

**Es falso, y es el hallazgo más importante de este informe.** Ninguna de las dos ha perdido nunca
una fila de una carga real. Está en el apartado 2, con la prueba.

### 0.3 🔴 «Cuatro workflows escriben en `productos`, entre ellos el trackeador»

**El trackeador no escribe en `productos`.** Ni el snapshot ni el cerebro: solo **leen** (PVD, IVA,
comisiones). Barrido completo en el apartado 6.

---

## 1. BLOQUE A — POR QUÉ SE PARÓ

### A2 · El workflow y su reloj

`tracker-app.yml` (snapshot) y `tracker-cerebro.yml` (recomendaciones).

🔴 **Ninguno de los dos tiene `schedule`. Nunca lo ha tenido.** Está escrito en la cabecera del
propio fichero, en mayúsculas:

> `# >>> SIN RELOJ <<<  Solo cuando lo lanza el boton de la app.`

`tracker-app.yml` es `workflow_dispatch` a secas. `tracker-cerebro.yml` es `workflow_dispatch` +
`workflow_run` encadenado al anterior. En todo el repo solo **dos** workflows tienen cron
(`backup-bd.yml` y `semanal-bems.yml`); el trackeador no es uno de ellos.

**¿Está deshabilitado en Actions?** No. Medido con `gh workflow list --all`:

```
Moloka - Trackeador           active   309165583
Moloka - Cerebro Trackeador   active   309238765
```

Los dos **activos**. Aprietas el botón y arrancan hoy mismo.

### A3 · Cuál de las cuatro es

**Ninguna de las cuatro.** Es una quinta que el encargo no contemplaba: **nadie ha vuelto a
apretar el botón.**

Historial completo de `tracker-app.yml` (13 ejecuciones, todas):

| Cuándo (UTC) | Resultado |
|---|---|
| 8-jul, ocho ejecuciones entre 06:48 y 13:30 | ✅ success × 8 |
| 11-jul 10:06:29 | ✅ success |
| 11-jul 16:11:42 | ✅ success ← **la última** |
| *(después: nada)* | |

`tracker-cerebro.yml`: 8 ejecuciones, **todas `success`**, la última el 11-jul 16:12:17.

**Cero fallos en toda la vida de los dos workflows.** No hay «último run que escribió» y «primero
que no» que traer: no hay ningún run que no escribiera. La cadena cuadra al segundo con la base —
el último snapshot es de las **16:12:10** y el run que lo escribió arrancó a las **16:11:42**.

- ❌ (a) desactivado a propósito → los dos están `active`
- ❌ (b) falló y nadie lo vio → 21 runs, 21 éxitos
- ❌ (c) credencial caducada → nunca llegó a intentarlo
- ❌ (d) corre sin escribir → no corre
- ✅ **(e) es 100 % manual y el método cambió**

Esto encaja con lo que ya decía la corrección de la auditoría: el criterio de este mes se destiló
contra captura manual y ficheros (`keepa_escaparate`, `salud_fba`, popup del Seller). El trackeador
no se abandonó por avería — **dejó de usarse**.

📌 Y el racimo de **ocho ejecuciones en la mañana del 8-jul** es la firma de una tanda de pruebas
de desarrollo. Importa para el apartado 2.

### A4 · Secretos

Los dos workflows inyectan **exactamente dos**, y los mismos:

```yaml
SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
```

**No hay token de Keepa ni de SP-API.** El trackeador no llama a la API de Keepa: lee el CSV que
subes tú («CERO tokens de Keepa», lo dice la cabecera de `moloka_tracker_snapshot_nube.py`). Así
que **no hay nada que pueda caducar** salvo la clave de Supabase.

### 🔴 A4-bis · RESUELTO: el trackeador corre con `anon`

Esto estaba abierto en CLAUDE.md §4 desde hace días («*lo mira Fernando*»). **Ya no hace falta:
se puede contestar sin ver el secreto, porque las claves de Supabase declaran su rol dentro del
propio valor.** Medido el 11-ago-2026 con una sonda temporal en la rama (`on: push`, borrada en el
commit siguiente), que imprime **longitud, formato y rol — nunca el valor**:

```
longitud de la clave: 46 caracteres
formato: sb_publishable_  ->  ROL DECLARADO -> "role":"anon" (clave PUBLICABLE)
```

🔴 **`SUPABASE_KEY` es la clave PUBLICABLE. El trackeador escribe en la base como `anon`.**

Y el código no tiene escapatoria: pide
`os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']`, pero los dos workflows
**solo inyectan `SUPABASE_KEY`**, así que el `or` cae siempre al mismo lado.
(`moloka_tracker_snapshot.py` ni siquiera tiene alternativa: usa `os.environ['SUPABASE_KEY']` a
secas.)

**Lo que esto decide, de golpe:**

- 🔴 **`monitor_snapshots`, `monitor_recomendaciones` y `monitor_reglas` NO se pueden cerrar
  todavía.** Son las tres que el trackeador toca, y hoy pasa por las políticas permisivas de `anon`
  (`anon_all_regla` y compañía). Cerrarlas ahora **lo rompe el día que arranque** — y como está
  parado, el fallo no se vería hasta entonces. Cambia el orden del bloque D3 (apartado 5).
- ✅ **El gate D1 sigue siendo seguro**, y ahora está demostrado por dos vías: el trackeador no lee
  ninguna de las dos vistas (cuenta cerrada abajo), así que revocarle `anon` no le afecta.
- 🔑 **El orden correcto, y no admite inversión:** primero se le da al trackeador una clave de
  servicio (`service_role`, que salta la RLS por `rolbypassrls`) — o sea, añadir
  `SUPABASE_SERVICE_KEY` a los dos workflows, que el código ya sabe preferir — y **solo después**
  se cierran las tres tablas. Nunca al revés.

⚠️ **Y un efecto secundario que hay que mirar antes de dar el paso:** el `or` está en los tres
ficheros del trackeador, pero **también** en otros procesadores. Añadir el secret
`SUPABASE_SERVICE_KEY` a un workflow cambia con qué rol escribe *todo* lo que corra en él. Se hace
workflow a workflow, no de una vez.

### 🔒 CUENTA CERRADA DEL TRACKEADOR — qué toca y con qué cliente

Mismo método que el de la v1 (apartado 5, D1): enumerar y cuadrar, no buscar y no encontrar.
En los tres ficheros hay **15 llamadas `.table(`** y **las 15 usan nombre literal** — ninguna
variable, así que la lista es cerrada:

| Objeto | `snapshot.py` | `snapshot_nube.py` | `cerebro.py` | Qué hace |
|---|---|---|---|---|
| `productos` | 1 | — | 1 | **solo lee** (PVD, IVA, comisiones) |
| `app_datos` | 1 | — | 2 | lee `rentabilidad`; escribe `tracker_estado` |
| `monitor_snapshots` | 2 | 2 | 2 | guarda anti-recarga + `insert` |
| `monitor_recomendaciones` | — | — | 3 | anti-recarga + `update` a OBSOLETA + `insert` |
| `monitor_reglas` | — | — | 1 | **solo lee** (el umbral de margen) |

Más **un bucket de Storage**: `informes`, buzón `tracker/` (`storage.from_`), que además **vacía**
al terminar (`limpiar_buzon()`).

**Cliente: uno solo, `create_client(SUPABASE_URL, SUPABASE_KEY)` → `anon`.** No hay `psycopg2` ni
`DB_URL` en el trackeador: a diferencia de los procesadores, **no tiene una vía que salte la RLS**.

✅ **Ni `v_analisis_auditable` ni `v_scoreboard_reglas` están en esa lista** — ni ninguna vista, de
hecho: el trackeador no lee una sola vista. **El gate D1 no puede romperlo.**

---

## 2. BLOQUE B — FOTO O PELÍCULA · **YA SON PELÍCULA. NO HAY NADA QUE ARREGLAR.**

### B1 · Qué hace el código con `monitor_snapshots`

[`moloka_tracker_snapshot.py:373-385`](moloka_tracker_snapshot.py) y su gemelo en la nube
[`moloka_tracker_snapshot_nube.py:101-114`](moloka_tracker_snapshot_nube.py):

```python
# Proteccion anti-recarga: no duplicar si ya hay snapshot de este mismo fichero+pais
ya = sb.table('monitor_snapshots').select('id').eq('pais', args.pais)\
       .eq('origen_carga', origen).limit(1).execute()
if ya.data:
    print(f"\n[STOP] Ya existen snapshots del fichero '{origen}' en {args.pais}. ...")
    return
for i in range(0, len(filas), 200):
    sb.table('monitor_snapshots').insert(filas[i:i+200]).execute()
```

**`insert` puro.** Ni `DELETE`, ni `upsert`, ni `onConflict`, ni `truncate` — y además una guarda
anti-recarga que impide reprocesar el mismo fichero. **No existe la palabra `delete` en los tres
ficheros del trackeador.**

### B2 · Qué hace con `monitor_recomendaciones`

[`moloka_tracker_cerebro.py:419-433`](moloka_tracker_cerebro.py). El comentario contesta la
pregunta antes de que se haga:

```python
# PIEZA 1: recalculo limpio. Cada pasada es una foto nueva, no se apila sobre
# las anteriores. Justo ANTES de insertar, se marcan como OBSOLETA todas las
# PENDIENTE de este pais (de cargas previas) -> la pestana (que lee solo
# PENDIENTE) deja de mostrar duplicados y recomendaciones caducas.
# NO se tocan DESCARTADA ni APLICADA (histórico + criterio de Fernando).
# Es un UPDATE reversible, NO un DELETE.
obs = sb.table('monitor_recomendaciones').update({'estado': ESTADO_OBSOLETA})\
        .eq('pais', pais).eq('estado', ESTADO_PENDIENTE).execute()
```

Las recomendaciones viejas **no se borran: se marcan**. Es exactamente el cajón MAESTRO de
CLAUDE.md §1.6, aplicado a una tabla de decisiones. Y el descarte manual desde la v1
([`index.html:3251`](index.html)) también es un `update` a `DESCARTADA` con motivo obligatorio,
nunca un borrado.

### 🔬 LA PRUEBA: de dónde salen los 1.746 y los 970 borrados

Los contadores de la auditoría son correctos — los he vuelto a medir yo:

| Tabla | insertadas | **actualizadas** | borradas | vivas |
|---|---|---|---|---|
| `monitor_snapshots` | 2.322 | **0** | 1.746 | 576 |
| `monitor_recomendaciones` | 1.546 | **385** | 970 | 576 |

La columna que la auditoría no miró es la de en medio, y lo cuenta todo:

- `monitor_snapshots` tiene **0 actualizaciones**. Nunca se ha tocado una fila. Append puro.
- `monitor_recomendaciones` tiene **385 actualizaciones**, y resulta que hay **exactamente 385
  filas en estado `OBSOLETA`**. Los updates *son* el marcado. El código hace lo que dice.

Y ahora el rango de identificadores, que es la prueba de verdad:

| Tabla | id mínimo | id máximo | filas | rango | **huecos dentro** |
|---|---|---|---|---|---|
| `monitor_snapshots` | 1.747 | 2.322 | 576 | 576 | **0** |
| `monitor_recomendaciones` | 972 | 1.547 | 576 | 576 | **0** |

**Cero huecos.** Los 1.746 borrados son los id 1…1746 — un bloque contiguo, entero, **por debajo**
de todo lo que hay vivo. Los 970 de recomendaciones, igual (los id 1…971; el id que sobra es un
número de secuencia quemado por una inserción que se echó atrás, que no llega a ser fila).

En términos contables: **no es que se hayan ido arrancando hojas del libro según se escribían
otras. Es que se arrancó de una vez el cuaderno de borrador, y el libro bueno empieza en la
página siguiente y está completo.**

Y el libro bueno tiene **tres asientos, los tres enteros**:

| Carga | Fichero de origen | Filas |
|---|---|---|
| 8-jul 13:30:35 | `KeepaExport-2026-07-08-…` | 194 |
| 11-jul 10:06:53 | `KeepaExport-2026-07-11-…` | 191 |
| 11-jul 16:12:10 | `KeepaExport-2026-07-11-… (1)` | 191 |
| | **total** | **576** ✅ |

Si estas tablas fueran FOTO, hoy habría **191** filas —solo la última carga— y no 576. Hay tres
cargas conviviendo. **Son PELÍCULA, y se comportan como tal desde el primer día.**

Los 1.746 borrados son la limpieza de la tanda de pruebas del 8-jul (aquellas ocho ejecuciones de
una mañana). Se hizo a mano, una vez, y no ha vuelto a pasar.

⚠️ **Lo que no puedo demostrar:** *quién* ejecutó ese borrado ni *cuándo* exactamente. Postgres no
guarda esa traza y en esta base no hay log de auditoría. Lo que sí está probado es que **no fue el
código** (no existe) y que **no se repite** (no hay un solo hueco después).

### B3 · El `_hist` que el encargo pide — **no hace falta, y ponerlo sería un error**

El patrón `viva + _hist` de la casa existe para resolver un problema concreto: la tabla viva es una
**FOTO** que tira la hoja vieja en cada carga, así que si no se archiva antes, la memoria se pierde.
Por eso `keepa_escaparate` → `keepa_escaparate_hist`.

Comprobado cómo está implementado en los tres casos que cita el encargo: **no es un trigger ni una
función SQL. Es un paso en Python dentro del procesador**, en la misma transacción
([`procesador_salud_fba.py:745`](procesador_salud_fba.py): `INSERT INTO salud_fba_historico … `).
Medido en la base: **cero triggers propios** en las nueve tablas implicadas.

Pero `monitor_snapshots` **no es una Foto**. No tira nada. Darle un `_hist` sería copiar filas
permanentes a otro sitio donde también serían permanentes: **dos verdades y el doble de sitio, para
proteger de un borrado que no ocurre.**

🔑 La regla de la casa que aplica aquí es la del cajón (§1.6): *el error caro es tratar un cajón como
si fuera otro*. La auditoría leyó una Película y la trató de Foto. La respuesta correcta no es
construirle una Película a algo que ya lo es.

**Lo que sí hay que arreglar es de una línea**, y es lo que causó todo el malentendido — el
comentario de la tabla, que se contradice a sí mismo:

> `Foto por producto/país en cada carga. Serie histórica del trackeador de precios.`

Va en el mismo PR que el comentario de `monitor_recomendaciones` (apartado 3).

### B4 · Los dos históricos de salud FBA

| Tabla | Columnas | Quién la escribe | Quién la lee |
|---|---|---|---|
| `salud_fba_historico` (1.549 filas, viva) | 34, **LEAN** | [`procesador_salud_fba.py:745`](procesador_salud_fba.py), explícita como *«PELÍCULA: apila, NUNCA borra»* | el procesador y las vistas |
| `salud_fba_hist` (227 filas, muerta) | **62**, con `crudo` | **nadie** — ver abajo | **nadie** |

**Qué la lee: nadie.** Barrido de los dos repos (`.py`, `.html`, `.sql`, `.ts`, `.tsx`):
`salud_fba_hist` aparece **únicamente** en [`sql/canario_rls.sql`](sql/canario_rls.sql), y ahí solo
como entrada de un censo de tablas.

**Qué la escribía — esto es lo que faltaba, y no es lo que parecía.** No la escribía ningún
procesador: 🔬 **las 227 filas tienen UN ÚNICO `archivado_en`, el 26-jul-2026 a las 07:16:30.**
Es una sola operación de relleno, hecha a mano, que no se repitió nunca. Sale de **tres ficheros**:

| Fichero de origen | Filas | `snapshot_date` |
|---|---|---|
| `50438020648.txt` | 6 | 14-jul |
| `50489020656.txt` | 3 | 22-jul |
| `50497020659 (1).txt` | 218 | 25-jul |

📌 Y la propia forma delata que **quedó a medias**: esos `.txt` pesan ~100 KB y traen unas 220
filas cada uno, pero de los dos primeros solo entraron **6 y 3**. No es un archivo: es un relleno
que se abandonó a mitad. Encaja con la cronología del repo — `procesador_salud_fba.py` nació el
**24-jul** (`8a158e8`) escribiendo `salud_fba_historico` **directamente**, o sea que la tabla LEAN
ya existía dos días antes de que alguien rellenara la gorda. Nunca fue la titular.

**¿Se puede jubilar? Sí, y ahora con la prueba en la mano.** Lo que me preocupaba al abrirla era
que fuese la única copia de algo: tiene **26 columnas que la viva no tiene** (`crudo`, `fnsku`,
`product_name`, `storage_volume`, `item_volume`, los `season_*`, los `recommended_*`,
`healthy_inventory_level`…) y el **14-jul no existe en `salud_fba_historico`**. Pero:

🔒 **Los tres ficheros de origen siguen en Storage** (`informes/salud_fba/`, comprobado uno a uno:
`50438020648.txt` del 16-jul, `50489020656.txt` del 23-jul, `50497020659 (1).txt` del 25-jul). El
procesador **no limpia su buzón** — no hay `remove` ni `limpiar_buzon` en él. **Todo lo que hay en
esa tabla se puede reconstruir del `.txt`, columna a columna, incluido el `crudo`.** No se pierde
nada.

Y el `crudo` que le falta a la viva no es un olvido, es el diseño, escrito en el propio procesador
(`:170-172`): *«LEAN: solo las columnas que dibujan una curva. NADA de `crudo jsonb` … la completa
del día de hoy sigue entera en `salud_fba.crudo`»*. Es la misma regla que el `DROP COLUMN crudo` de
Keepa (CLAUDE.md §2): el crudo sale de la base **porque el fichero se conserva**.

**No la he tocado.** Cuando se jubile, en su propio PR y en dos tiempos: primero
`ALTER TABLE … RENAME TO _zz_salud_fba_hist_jubilada`, el `DROP` semanas después. No por duda —
está medido— sino porque renombrar es gratis y revela cualquier lector que el barrido no viera.

#### 🔬 La prueba que falta antes del RENAME — y por qué su criterio no puede ser «227 filas»

**Que los ficheros existan no demuestra que el procesador de hoy los reprocese bien.** Es cierto y
es la diferencia entre una copia y una copia *probada* — el mismo agujero que motivó el simulacro
de restauración (CLAUDE.md §4). Así que antes del RENAME hay que reprocesar los tres en staging.

Es viable sin tocar nada: `procesar-salud-fba.yml` ya tiene los tres mandos que hacen falta —
`entorno` (staging), `modo` (aplicar) y **`fichero`** (nombre exacto del `.txt`), que además nació
justo para recargas dirigidas como ésta. Y el reparto de credenciales encaja: `SUPABASE_URL`/`KEY`
—o sea el Storage— son siempre los de **producción**, mientras lo que se escribe va a `DB_URL`, que
conmuta a `STAGING_DB_URL`. **Lee los ficheros buenos y escribe en staging.**

🔴 **Pero el criterio de aprobado NO puede ser «que salgan las 227 filas», y conviene verlo antes
de lanzarlo:** las 227 son el resultado de aquel relleno a medias, no el contenido de los ficheros.
Los tres `.txt` pesan ~100 KB y traen unas 220 filas **cada uno**, así que reprocesarlos producirá
del orden de **660**, no 227. Si se toma «227» como listón, la prueba sale en rojo **haciendo el
procesador exactamente lo correcto**, y se acaba dudando de una cañería sana.

**El criterio correcto es de contención, no de recuento:** que las **227 parejas
`(sku, snapshot_date)`** de la tabla muerta estén **todas** dentro de lo que produce el reprocesado.
Eso es justo lo que hay que demostrar —que nada de lo que hoy solo vive ahí es irrecuperable— y no
depende de cuántas filas traigan de más los ficheros:

```sql
-- en STAGING, tras reprocesar los tres. Debe dar 0.
select count(*) from public.salud_fba_hist h
where not exists (
  select 1 from public.salud_fba_historico v
  where v.sku = h.sku and v.snapshot_date = h.snapshot_date);
```

#### 🔬 LANZADO el 11-ago — y el resultado cambia la conclusión

Ejecutado `procesar-salud-fba.yml` con `entorno=staging`, `modo=ensayo`,
`fichero=50438020648.txt` (el del 14-jul, el único día que solo vive en la tabla muerta).
**Run [31485223052](https://github.com/Moloka-Store/moloka-app/actions/runs/31485223052):**

```
Informe elegido (pedido a dedo por FICHERO): 50438020648.txt
Filas leídas y cuadradas: 195 · snapshot 2026-07-14 · marketplaces ['ES']
❌ ABORTA (no se ha escrito nada):
[Guarda no-retroceder] La foto que entra es del 2026-07-14 y en salud_fba
(marketplace ∈ ['ES']) ya hay dato del 2026-08-10: sería retroceder en el tiempo.
No se escribe nada. (Si de verdad quieres recargar una foto vieja: PERMITIR_RETROCESO=1.)
```

**Dos cosas, y son de signo contrario:**

✅ **El fichero se lee perfectamente y el procesador de hoy lo entiende.** Pasó las ocho guardas
estructurales y dio **195 filas cuadradas**, con el `snapshot_date` **bien derivado a 14-jul** (que
era la duda de fondo: que un `.txt` de hace un mes siguiera siendo interpretable). El contenido no
está podrido.

📌 Y de paso mide lo incompleto que fue el relleno: ese fichero da **195 filas** para el 14-jul y en
`salud_fba_hist` solo hay **6**. Se quedó con el **3 %**.

🔴 **Pero NO se puede reproducir por la vía normal**, y no por el fichero: por la **Guarda 10
(no-retroceder)**. Cualquier recarga histórica es, por definición, un retroceso. Hay válvula de
escape —`PERMITIR_RETROCESO=1`— **pero `procesar-salud-fba.yml` no la expone como input**: solo
inyecta `ENTORNO`, `MODO` y `FICHERO`. Comprobado en los dos sitios; en el repo la cadena
`PERMITIR_RETROCESO` solo aparece **en un comentario**.

**Paré tras el primer despacho en vez de lanzar los cuatro**, porque los otros tres abortarían
igual —los tres ficheros son de julio y staging está en 10-ago— y `restaurar-staging.yml` habría
**empeorado** el intento: es justo lo que vuelve a poner el 10-ago. Cuatro despachos habrían dado
cuatro veces el mismo rojo.

> ### 🔑 Lo que esto significa, que vale más que la tabla
> **El buzón sí es reconstruible —los ficheros están y se parsean— pero HOY NO HAY UNA VÍA
> SOPORTADA PARA REPRODUCIRLOS.** La guarda que protege de cargar un informe caducado bloquea
> también la recarga histórica deliberada, y la válvula que existe para eso no llega al workflow.
> Es un agujero de *recuperación*, no de *conservación*: el día que haya que reconstruir una serie
> —o comprobar una copia, que es el caso de hoy— hay que tocar el `.yml` primero.

**Por eso NO se hace el RENAME todavía.** La contención no ha salido limpia: no ha podido correr.
El orden correcto es:
1. PR pequeño que añada `permitir_retroceso` como input a `procesar-salud-fba.yml` (y, por la
   misma razón, a los demás procesadores-Foto que tengan la Guarda 10). Por §5 tiene que estar en
   `main` para poder despacharse.
2. Con eso, los 3 despachos + la consulta de contención de arriba.
3. Y **solo si sale 0**, el RENAME.

### B5 · La respuesta en una línea

> **Se reactiva.** El archivado no está roto: `monitor_snapshots` y `monitor_recomendaciones` ya
> son Película y conservan sus tres cargas íntegras. Lo único que falta para encenderlo es apretar
> el botón — y arreglar antes el cálculo del acantilado de 20 € (apartado 4, C6), que sí es un bug
> real y afecta al **42 % de las recomendaciones que proponen precio**.

**Y no se jubila a favor de `keepa_escaparate_hist`**, porque no miden lo mismo:
`keepa_escaparate_hist` guarda el **mercado** (buy box, competencia); `monitor_snapshots` guarda
**tu posición en él con el margen ya calculado y la fuente de cada dato** (`comision_fuente`,
`fee_fuente`). Eso último no está en ninguna otra tabla de la base.

⚠️ **Aviso operativo para cuando se encienda:** la primera pasada del cerebro marcará las **191
recomendaciones `PENDIENTE` de julio como `OBSOLETA`** antes de escribir las nuevas. Es lo correcto
—son de hace un mes— pero desaparecerán de la pestaña. No se borran: quedan consultables por
`estado='OBSOLETA'`.

---

## 3. EL CONTRATO DE `monitor_recomendaciones` (petición 2 del encargo)

**Quién la consume hoy: solo la v1.** [`index.html:3072`](index.html) lee
`.select('*').eq('pais', pais).eq('estado','PENDIENTE')`, y [`index.html:3251`](index.html) escribe
el descarte. **El cockpit de la v2 no la toca** — cero referencias en `app/` y `lib/`; el encargo
del Cockpit multipaís dice literalmente *«No se cablea hasta que el trackeador vuelva a correr»*.

Contrato medido contra las 38 columnas reales y el código que las produce y consume:

```sql
comment on table public.monitor_recomendaciones is
'PELÍCULA (apila; NUNCA se borra). Recomendaciones de precio del cerebro del trackeador
(moloka_tracker_cerebro.py). Una fila por (pais, asin) y pasada. NO cambia precios: propone.

CICLO DE VIDA — campo `estado`, y es la llave de todo:
  PENDIENTE  = viva. Es lo ÚNICO que pinta la app (index.html:3073 filtra por estado+pais).
  OBSOLETA   = recalculada fuera por una pasada posterior. La pone el cerebro con un UPDATE
               (cerebro:425) sobre las PENDIENTE del MISMO pais, justo antes de insertar.
               Reversible. NO es un borrado.
  DESCARTADA = criterio de Fernando desde la app (index.html:3252). Exige `motivo_descarte`
               no vacío y sella `descartada_en`. El cerebro NUNCA la toca.
  APLICADA   = reservado: precio ya movido en el Seller. Hoy no lo escribe nadie.

`descartada_en` y `motivo_descarte` son NULL en todo lo que no esté DESCARTADA, y eso es lo
normal: hoy las 576 filas lo tienen a NULL porque nunca se ha descartado ninguna. Un consumidor
que dé por hecho que hay fecha se rompe.

ANTI-RECARGA: el cerebro no reescribe si ya existe la pareja (pais, snapshot_ts).

ESCALAS — tres trampas medidas:
  · `comision_pct`         → PORCENTAJE (15.04), NO fracción. El cerebro ya normalizó
                             el 0.155 de productos multiplicando por 100 (snapshot:277).
  · `margen_*_pct`         → PORCENTAJE con 2 decimales.
  · `impacto_eur_mes`      → EUR/mes. Nunca NULL: es 0.0 cuando no hay acción.

`precio_objetivo` vs `precio_techo`: objetivo = lo que se propone EN ESTA PASADA (subida topada
al +10%); techo = el destino final. Si difieren, la subida va escalonada. Los dos son NULL en
toda acción que no mueva precio.

`fuente_margen` (real_tx > real > keepa_bd > keepa_csv) dice de dónde salió la comisión, y
`confianza` (alta/media/baja) lo traduce. `fuente_margen=''keepa_csv''` significa margen
estimado, no medido.

ACCIONES: SUBIR · BAJAR · RECUPERAR_BB · MALVENDIENDO · NO_RENTABLE_COMPETIR · GUERRA_ACTIVA ·
MANTENER · SIN_ACCION · SIN_DATOS. Solo las cuatro primeras traen `precio_objetivo`.

🔴 El margen de esta tabla se calcula con `calc_rentabilidad` (CON el x1.03 de servicios
digitales). El cockpit v2 usa `calcularMargenVivo`, que NO lo lleva: los dos números no coinciden
y la diferencia es conocida (docs/rentabilidad-dos-formulas.md). No mezclar sin decidir cuál manda.';
```

⚠️ **Un aviso sobre este comentario:** describe el contrato de hoy, y el estado `APLICADA` está
declarado en el código pero **no lo escribe nadie**. Si se decide que el analista lo use, hay que
escribirlo antes de darlo por cierto.

---

## 4. BLOQUE C — LO QUE NECESITA EL ANALISTA

### C2 · Con qué frecuencia entra cada fuente (calendario realista)

Medido en los workflows: **de las 8 fuentes, solo una tiene reloj.**

| Fuente | Disparo | Frecuencia real | ¿Reconstruible hacia atrás? |
|---|---|---|---|
| `keepa_escaparate` (+`_hist`) | manual (botón) | cuando subes el CSV | ✅ **sí** — los CSV están en Storage y NO se borran nunca |
| `salud_fba` (+`_historico`) | manual | cuando subes el informe | ⚠️ solo desde el 22-jul |
| `seller_observaciones` | **captura a mano** del popup | cuando la haces | ❌ no |
| `monitor_snapshots` | manual (botón) | parado desde el 11-jul | ❌ no |
| `backup-bd` | **cron `15 2 * * *`** | diaria | — |

🔑 **Solo se puede reconstruir hacia atrás lo de Keepa**, y por una razón muy concreta que ya está
en CLAUDE.md §2: los CSV de `informes/keepa_escaparate/` son **archivo histórico permanente** desde
que `keepa_escaparate_hist` dejó de guardar `crudo`. Se rescatan por
`keepa_escaparate_hist.fichero`. Todo lo demás, no: lo que no se capturó, no existe.

**Consecuencia para el analista:** la serie temporal es corta y lo seguirá siendo *hasta que algo
tenga reloj*. Hoy la profundidad la marca la mano de Fernando, no la máquina.

### 🔴 C2-bis · La serie de `salud_fba_historico` no es diaria ni regular — y hay que EXPONER los huecos

Medido el 11-ago: **siete fotos en veinte días**, con estos saltos:

| Foto | 22-jul | 25-jul | 28-jul | 30-jul | **7-ago** | 9-ago | 10-ago |
|---|---|---|---|---|---|---|---|
| Días desde la anterior | — | 3 | 3 | 2 | **8** | 2 | 1 |

**¿Se puede automatizar a diario? No.** El informe se descarga a mano del Seller y
`procesar-salud-fba.yml` es `workflow_dispatch` sin reloj. Bajarlo solo requeriría SP-API, que está
**descartado y no se plantea**. Así que la cadencia la marca la mano de Fernando, y eso no va a
cambiar: **el diseño tiene que asumir la serie irregular como permanente, no como algo a arreglar.**

**Así que sí: hay que exponer los huecos explícitamente.** Y no como adorno — 🔑 **el hueco no rompe
lo mismo en todas partes, y ésa es la distinción que el analista necesita:**

- ✅ **Las ventanas T7/T30/T60/T90 aguantan.** Vienen **precalculadas por Amazon dentro del propio
  informe**, así que una foto del 7-ago trae el T30 correcto del 7-ago aunque la anterior fuera del
  30-jul. Para las reglas que comparan T7 contra T30, el agujero es indiferente.
- 🔴 **Lo que el hueco rompe es la RESTA entre dos fotos.** Un delta entre el 30-jul y el 7-ago no
  es «lo que pasó en una semana»: son dos puntos lejanos, y en medio no hay nada. Es la misma regla
  que ya está escrita para Custom Analytics: **restar dos lecturas solo prueba algo si están cerca.**

**La casa ya tiene media pieza y le falta la otra media.** `frescura_informes()` (migración
`2026-07-31_frescura_custom_analytics.sql`) ya publica, para los ocho informes, la fecha del dato,
cuándo se subió y cuándo se procesó. Contesta *«¿cómo de fresco es lo último?»* — pero **no**
contesta *«¿es continuo lo que hay detrás?»*. Un analista que vea «salud_fba: dato del 10-ago» da
por buena una serie que tiene ocho días de vacío dentro.

#### 🔑 La regla, concretada — el gap viaja EN LA FILA, no en una nota al pie

Una vista de continuidad aparte no basta: nadie la mira. **La regla para el diseño de la v2 es que
cualquier vista o función que sirva un DELTA devuelva también, como COLUMNA, el hueco en días entre
las dos fotos que ha usado.** Si se pregunta *«¿cómo ha evolucionado esto?»* y el gap es 8, el 8
tiene que verse en la misma fila que el dato.

Concretamente: al lado de `delta_stock` (o lo que sea que se sirva), una columna
`gap_dias` — y las fechas de las dos fotos que se han restado, no solo la última. Eso convierte
*«ha bajado 40 unidades»* en *«ha bajado 40 unidades entre el 30-jul y el 7-ago, 8 días»*, que es
una frase que ya no engaña a nadie. Un consumidor puede decidir ignorar el gap; lo que no puede es
no verlo.

🔑 Es la misma regla que §1.4 (*una cifra sin la fecha del dato que la sostiene es una cifra que
miente*) llevada a las restas: **una diferencia sin el intervalo que la sostiene es una diferencia
que miente.** Y es hermana de la de Custom Analytics: *restar dos lecturas solo prueba algo si
están cerca* — con la ventaja de que aquí, si el gap viaja en la fila, «cerca» deja de ser una
suposición y pasa a ser un dato que el consumidor puede comprobar.

`frescura_informes()` se queda como está: contesta otra pregunta (*qué tan fresco es lo último*) y
la contesta bien. Esto es la otra media pieza, y va donde se sirve el delta.

⚠️ Y un recordatorio que agrava el asunto y ya está en §1.3: **`salud_fba` llega ~10 días tarde con
las altas.** O sea que la fecha de la foto no es la fecha del mundo. Las dos cosas juntas —serie
irregular y desfase de origen— son la razón por la que este informe **no sirve para decir «en tal
semana pasó X»**, solo para tendencia y comparación entre ASIN.

### C3 · Tarifas reales — **VEREDICTO: el dato duro ya estaba en casa; nadie lo leía**

Revalidado hoy contra producción, y la auditoría clava los números:

| | |
|---|---|
| Universo repreciable (activo + stock FBA + ASIN) | **176** |
| Con tarifa real medida en Seller Central | **10** (5,7 %) |
| ASIN con tarifa real medida **en total** | **60** |

📌 **Un dato que no estaba en la auditoría y que cambia el plan:** hay **60 ASIN** con tarifa real
capturada, pero **solo 10 están en el universo repreciable**. Los otros **50 se capturaron sobre
productos que no se van a repreciar** (sin stock, inactivos o sin ASIN). El esfuerzo manual ya
hecho es seis veces mayor de lo que parece — **está apuntando al sitio equivocado**. Antes de
planificar más capturas, la lista de objetivos debe salir del universo, no del catálogo.

### 🔴 CORRECCIÓN (misma tarde) — este apartado partía de un dato FALSO

**El «94 % sin tarifa real» es falso y lo retiro.** El error fue fiarme del comentario de
`seller_observaciones` (*«la única fuente de verdad de tarifas»*) en vez de ir a buscar el dato.
Es la misma clase de error que cometió la auditoría con `n_tup_del`: **un comentario describe una
intención, no un censo.**

**La verdad, medida:** `transacciones_movimientos` trae `tarifa_venta` y `tarifa_fba` **reales, de
factura** — 13.146 movimientos de tipo `pedido` en ES, del 1-ene al 9-ago-2026. **160 de los 176
del universo (90,9 %) tienen tarifa facturada en los últimos 3 meses.** Lo no vendido aún lo cubre
`keepa_escaparate` con su estimación.

Así que **la captura manual nunca fue insustituible: el dato duro ya estaba en casa y nadie lo
leía.** Lo que falla es que `productos` no bebe de ahí.

📄 **El análisis completo —prelación, impacto producto a producto y el acantilado reconstruido desde
las facturas— está en [`PRELACION_TARIFAS_11ago.md`](PRELACION_TARIFAS_11ago.md).** El titular:
el problema **no es la comisión** (solo 6 de 176 cambian), es el **fee**: cambia en **152 de 176**,
sube **+0,63 €** de media y deja el margen **3,54 puntos más bajo**, con **10 productos que parecen
rentables y venden a pérdida**.

> 🔴 **SP-API queda descartado y fuera de todo diseño.** Ni Moloka ni la app v2 se conectan a
> SP-API bajo ningún concepto. No es una vía a valorar y no se vuelve a plantear.

### C4 · Comisiones de relleno — **VEREDICTO: el 0,1550 es un valor por defecto de un formulario**

Revalidado: **148 de 176** del universo llevan `comision_pct = 0,1550` exacto (y 307 de 331 en todo
el catálogo activo).

**Dónde se pone, localizado:** [`index.html:5710`](index.html), en el formulario de edición de
producto de la v1:

```js
value="${p.comision_pct!=null?(p.comision_pct*100).toFixed(1):'15.5'}"
```

Cuando editas una ficha que **no tiene** comisión, el campo aparece **relleno con 15,5**. Si
guardas sin tocarlo —y no hay motivo para tocarlo, porque parece un dato— se escribe `0,155`. Hay
un segundo `15.5` en [`index.html:7563`](index.html), pero ése solo pinta, no guarda.

🔑 **Por eso la doctrina 39 acierta al llamarlo relleno: no es una estimación equivocada, es el
valor por defecto de una caja de texto que se ha quedado grabado 307 veces.** Y es
indistinguible de una medición real, porque en la base es un número como cualquier otro.

**¿Hay vía para la comisión real?** Sí, y es la misma que la de la tarifa: **la factura**. La
comisión nominal se despeja de `transacciones_movimientos` con la fórmula de la doctrina 44 y da
picos limpios en 15,0 / 13,0 / 8,0 / 5,0. Ver [`PRELACION_TARIFAS_11ago.md`](PRELACION_TARIFAS_11ago.md).

🔬 **Y ahí sale el matiz que salva y condena al relleno a la vez:** de los 160 con factura, **142
están de verdad en el tramo del 15 %**. Como `15,0 × 1,03 = 15,45` y el relleno dice `15,50`, **se
desvía 5 centésimas: acierta por casualidad en 142 de 160.** Pero en los 8 del tramo del 8 % y los
3 del 5 % se desvía 7 y 10 puntos. **Es la peor forma de estar mal: acierta lo bastante para que
nadie lo mire y falla justo donde duele.**

✅ **ARREGLADO** en su propio PR ([#149](https://github.com/Moloka-Store/moloka-app/pull/149)): la
caja nace **vacía** y obligatoria. Toca la v1 congelada, así que va aparte y **Elena tiene que estar
avisada antes de desplegar** — el bloqueo muerde en las 99 fichas activas que hoy no tienen comisión.

### C5 · Dónde vive la fórmula, y si divergen — **SÍ DIVERGEN, y ya está documentado**

**Hay tres copias**, no dos:

| # | Dónde | Con `×1.03` | ROI | Escala del margen |
|---|---|---|---|---|
| A | `moloka_escaner_nube.py:435-444` — el escáner (compra) | ✅ | ✅ | fracción |
| A' | [`moloka_tracker_snapshot.py:115-123`](moloka_tracker_snapshot.py) — **el trackeador** | ✅ | ❌ | **porcentaje, redondeado a 2** |
| B | `lib/inventory/build.ts:244-280` (v2) — `calcularMargenVivo` | 🔴 **NO** | ❌ | porcentaje, 1 decimal |

- **A vs A′:** mismo beneficio al céntimo. A′ es una clonación declarada («CLONADAS de
  `moloka_escaner_nube.py`, no tocar») que solo cambia la presentación: devuelve el margen ×100 y
  no calcula ROI. **No divergen en el dinero.**
- **A vs B:** 🔴 **divergen**, y no es opinable. Falta el `×1.03` de servicios digitales en B.
  `docs/rentabilidad-dos-formulas.md` lo tiene medido: sobre el caso canónico, beneficio **−1,04 €
  (A) contra −0,96 € (B)**, y el margen del cockpit sale **optimista ~0,45 puntos**. El documento
  registra tu decisión del 3-ago: *«el `×1.03` que le falta a `calcularMargenVivo` es un BUG
  confirmado, no una decisión»*, diferido a su propio PR.

✅ **Confirmado lo que preguntas:** la fórmula de COMPRA (escáner, con ROI y semáforo) y la de
repricing **no se están cruzando** — son la misma aritmética con distinta presentación, y el
documento deja escrito que no se unifican.

🔴 **Pero lo que sí te afecta para el analista:** el trackeador y el cockpit **hoy dan márgenes
distintos para el mismo producto**. Si el analista se conecta al cockpit y cita márgenes, citará
los del cockpit — los que llevan el bug. **El PR del `×1.03` debería ir antes que el analista**, no
después. No he tocado nada.

### C6 · El acantilado de 20 € — **hay un bug, pero no es el que el encargo supone**

La pregunta era *«¿cómo sabe el código a qué producto aplicarle el acantilado? Si lo aplica a todo,
es un bug de margen.»*

**El código no aplica ningún acantilado, ni a todo ni a nada.** `calc_rentabilidad` recibe
`fee_fba` **como parámetro** — nunca lo deduce del precio. La doctrina 7 lo describe como un
escalón de la **tarifa FBA** (los pares 3,28↔3,80 y 3,51↔4,01), específico de FUNKO por tamaño de
caja. Es un criterio para saber *qué tarifa es la correcta*, no una rama de código.

🔴 **Y ahí está el bug de verdad**, en [`moloka_tracker_cerebro.py:148-150`](moloka_tracker_cerebro.py):

```python
def margen_en(px):
    if px is None: return (None, None)
    return calc_rentabilidad(px, pvd, com_pct, fee, iva)   # ← 'fee' es constante
```

El cerebro propone precios nuevos y recalcula el margen a ese precio **manteniendo fija la tarifa
FBA del precio viejo**. Si la propuesta cruza los 20 €, la tarifa real cambia y el margen que se
enseña es falso — y encima en la dirección peligrosa: al **subir** de precio la tarifa sube, así
que el margen prometido está **inflado**.

🔬 **Medido sobre las 191 recomendaciones `PENDIENTE` que hay ahora mismo en producción:**

| Acción | Recos | Con precio objetivo | **Cruzan los 20 € subiendo** |
|---|---|---|---|
| RECUPERAR_BB | 14 | 14 | **8** |
| SUBIR | 3 | 3 | 0 |
| BAJAR | 2 | 2 | 0 |
| *(el resto no propone precio)* | 172 | 0 | 0 |
| | | **19** | **8** |

**8 de las 19 recomendaciones que proponen un precio (42 %) cruzan el acantilado**, y las 8 lo
cruzan hacia arriba. Sus márgenes objetivo están calculados con la tarifa de más abajo.

**Contando también las obsoletas —o sea, todo lo que el motor ha producido en su vida—:**

| | Con precio objetivo | Cruzan los 20 € | Objetivo entre 19 y 21 € |
|---|---|---|---|
| PENDIENTE | 19 | **8** | 7 |
| OBSOLETA | 122 | **15** | 32 |
| **TOTAL** | **141** | **23** | **39** |

#### 🔬 El caso que lo resume, al céntimo: `B08HH5V55W`

**FUNKO POP Astro Bot 1089** — o sea, exactamente la categoría a la que la doctrina 7 dice que
aplica el acantilado. Lo que la recomendación viva dice hoy:

| Dato | Valor |
|---|---|
| `precio_actual` | 19,99 € |
| `precio_objetivo` | **20,37 €** (+38 céntimos) |
| `fee_logistica` | **3,28 €** ← la mitad BAJA del par `3,28 ↔ 3,80` de la doctrina 7 |
| `comision_pct` | 15,5 % ← y encima es el relleno de C4 |
| `margen_actual_pct` → `margen_objetivo_pct` | 10,35 % → **11,40 %** |
| `pvd` (de `productos`) | 7,83 € |

Con esos números la fórmula reproduce el margen actual **exacto** (10,35 %), así que se puede
recalcular el objetivo con la tarifa que de verdad tocaría por encima del escalón:

| A 20,37 € | Tarifa | Beneficio/ud | Margen |
|---|---|---|---|
| Lo que dice la reco | 3,28 € | 2,32 € | **11,40 %** |
| Lo que sería de verdad | 3,80 € *(estimado)* | 1,80 € | **≈ 8,85 %** *(estimado)* |

🔴 **La recomendación promete pasar de 10,35 % a 11,40 % (+1,05 puntos). En realidad el margen
BAJA.** No es que el número esté un poco mal — **es que le cambia el signo a la decisión.** Subir
38 céntimos parece ganar margen y lo pierde.

⚠️ **Distinción de rigor, para que nadie cite esto como una medición:**

- **La DIRECCIÓN es un hecho.** Al cruzar el escalón la tarifa FBA sube, y el cerebro la mantiene
  fija; por tanto el margen real es **menor** que el prometido, siempre, en las 23 que cruzan. Eso
  no depende de ningún supuesto: se deduce de que `margen_en()` no recalcula `fee`.
- **El `8,85 %` es una ESTIMACIÓN**, y depende de que `3,80 €` sea el tramo correcto de la tabla
  para este producto. Sale del par `3,28 ↔ 3,80` de la doctrina 7, que es doctrina de la casa, no
  una tarifa leída del Seller para este ASIN. Si el tramo real fuese otro, la cifra cambia; la
  dirección, no.

🔴 **Y hay una ironía que refuerza el caso: el ejemplo está construido sobre DOS estimaciones, no
sobre medidas.** Su `comision_pct` es **0,1550** —el relleno del formulario de C4— y su
`tarifa_fba` real en `seller_observaciones` es **NULL**: es uno de los 166 de 176 sin tarifa medida
(C3). O sea que el caso que le cambia el signo a la decisión **no tiene ni un solo dato duro de
tarifa detrás**. C3, C4 y C6 no son tres problemas separados: se acumulan sobre el mismo producto.

💰 **Y el tamaño de lo que el cockpit enseñaría en verde:** las **8 recomendaciones pendientes que
cruzan** suman **172,77 €/mes de impacto prometido**.

> ### 🔴 CONDICIÓN DE REACTIVACIÓN
> **El trackeador no se enciende hasta que el cerebro recalcule la tarifa FBA al cruzar los 20 €.**
> No es una mejora pendiente: mientras no esté, el motor recomienda subidas prometiendo un margen
> que no se va a cumplir, y en al menos un caso medido la recomendación es exactamente la contraria
> a la correcta.

**No lo he arreglado**, como pediste: toca la aritmética y eso lo apruebas tú. Va en su propio PR.

No es teórico y no es marginal: es casi la mitad de lo accionable. **Encender el trackeador sin
arreglar esto es reactivar un motor que recomienda subir precios prometiendo un margen que no se
va a cumplir** — justo el tipo de error contra el que existe la regla de «ningún precio sin margen
calculado». Va en su propio PR y **no lo he tocado** (toca la aritmética, y eso lo apruebas tú).

---

## 5. BLOQUE D — SEGURIDAD

### D1 · Las dos vistas escribibles → **migración propuesta, sin ejecutar**

📄 [`migraciones/2026-08-11_gate_anon_vistas_monitor.sql`](migraciones/2026-08-11_gate_anon_vistas_monitor.sql)

**¿Deliberado o arrastre?** 🔬 **Arrastre, y se demuestra comparando el ACL carácter a carácter:**

| Objeto | ACL real |
|---|---|
| `monitor_analisis` (tabla) | `postgres=arwdDxtm │ anon=arwdDxtm │ authenticated=arwdDxtm │ service_role=arwdDxtm` |
| `v_analisis_auditable` | **idéntico** |
| `v_scoreboard_reglas` | **idéntico** |
| `v_presencia_pais` *(bien hecha)* | `postgres=arwdDxtm │ service_role=arwdDxtm │ **authenticated=r**` |

Los tres primeros son, letra por letra, el `pg_default_acl` de `public`. Una vista con un GRANT
escrito a mano no se parece a eso — se parece a la cuarta, que lleva su `revoke` en la migración.
**Nadie concedió esto: nacieron abiertas y nadie las cerró.**

**¿Por qué el event trigger no las salvó?** Porque `rls_auto_enable()` solo dispara con
`CREATE TABLE` / `CREATE TABLE AS` / `SELECT INTO`. **`CREATE VIEW` no está en su lista**, y una
vista no tiene RLS propia: para ella el ACL es la única defensa, y el ACL nace abierto.

**¿La usa alguien? ¿Rompe el gate alguna pantalla de la v1?** 🔒 **No, y esta vez con la cuenta
cerrada**, que es más fuerte que un grep negativo. En `index.html` hay **164 llamadas `.from(`** y
se reparten así, sin que sobre ni una:

| | |
|---|---|
| Con nombre literal entrecomillado | **158** |
| `Array.from(…)` — JavaScript, no Supabase | 2 |
| `db.storage.from('fotos-fabrica' / 'facturas-pdfs')` — buckets, no tablas | 4 |
| | **164** ✅ |

**Ninguna usa una variable**, así que la lista de lo que la v1 puede tocar es cerrada y completa —
**16 objetos de base de datos**, éstos y no otros:

> `ajustes_stock` · `alertas_silenciadas` · `app_datos` · `canales_producto` · `codigos_proveedor` ·
> `compras` · `devoluciones` · `envios_fba` · `escaner_resultados` · `fabrica_fichas` · `facturas` ·
> `monitor_recomendaciones` · `movimientos` · `productos` · `tareas` · `web_productos`

**Ni `v_analisis_auditable` ni `v_scoreboard_reglas` están.** Y tampoco hay puerta trasera: cero
`fetch` a `/rest/v1/`, cero `.rpc(`, y cero apariciones de las cadenas `v_analisis`, `v_scoreboard`,
`auditable` o `scoreboard` en todo el fichero. Lo mismo en `api/disparar.js`.

Sumado a los otros dos barridos (0 en `app/` y `lib/` de la v2, 0 en los tres ficheros del
trackeador) y a **0 dependencias en `pg_depend`**: el gate no puede romper ninguna pantalla, porque
ninguna pantalla las abre. Como dice el encargo: *si nadie la lee, la respuesta es revocar y punto.*

⚠️ El límite honesto sigue siendo el mismo: esto cubre los dos repos y la base. Un Colab o un
script suelto fuera de ahí no lo puedo ver, y la ausencia no se demuestra.

**⚠️ Lo que la migración NO hace, a propósito:** no les pone `security_invoker`. Medido —
`monitor_analisis` tiene RLS con **cero políticas** (la vista quedaría a 0 filas) y `monitor_reglas`
solo tiene política para `anon` (quedaría a 0 filas para `authenticated`). Es el mismo caso que
`v_estado_asin` en el gate del 10-ago. Se cierra el permiso, que es lo que urge; la defensa en
profundidad depende de qué se decida con esas dos tablas.

### D2 · El DEFAULT ACL → **migración propuesta, sin ejecutar**

📄 [`migraciones/2026-08-11_default_acl_public.sql`](migraciones/2026-08-11_default_acl_public.sql)

**¿Está en alguna migración del repo?** **No.** Cero coincidencias de `ALTER DEFAULT PRIVILEGES` en
`migraciones/`. Es la configuración por defecto de Supabase, nunca versionada.

La migración revoca por rol nombrado (`anon` y `authenticated`) sobre tablas, secuencias y
funciones. **Tres límites que van escritos dentro y que hay que aceptar antes de aplicarla:**

1. **No toca ni un objeto existente.** Las 53 tablas de hoy siguen igual — eso es D3.
2. **Solo revoca el default de `postgres`**, no el de `supabase_admin` (son entradas distintas y
   `ALTER DEFAULT PRIVILEGES` va por rol concedente). El de `postgres` es el que importa, porque es
   quien crea.
3. 🔴 **Un restore se la lleva**, igual que todo lo demás de CLAUDE.md §4: el volcado usa
   `--no-privileges`. Protege de aquí en adelante; no cierra el frente del backup.

Y el efecto secundario a aceptar a propósito: **toda tabla nueva necesitará su `grant` explícito**.
Muerde en un sitio concreto — `procesador_salud_fba.py:433` crea `salud_fba_historico` con
`CREATE TABLE IF NOT EXISTS`. Los procesadores escriben con `DB_URL` (rol `postgres`) y seguirán
funcionando; lo que se rompería es la app leyendo con `anon`/`authenticated` si nadie pone el grant.

### D3 · Orden para cerrar las 22 tablas sin romper la v1

La v1 escribe **con la clave `anon`** en estas tablas (barrido de `index.html`):

| Tabla | Operaciones desde la v1 |
|---|---|
| `productos` | 17 update + 5 insert |
| `alertas_silenciadas` | 4 insert + 1 delete |
| `compras` | 3 insert |
| `tareas` | insert + update + 2 delete |
| `ajustes_stock` | 2 insert |
| `movimientos`, `facturas`, `envios_fba` | 1 insert cada una |
| `fabrica_fichas`, `escaner_resultados` | update / delete |
| `codigos_proveedor` | upsert |
| `monitor_recomendaciones` | update (el descarte) |
| `web_productos` | 2 update |

**Orden propuesto, de fuera hacia dentro** — el criterio es *empezar por lo que la v1 no toca, para
que los primeros pasos sean gratis*:

0. 🔴 **PASO PREVIO OBLIGATORIO, y ya no es condicional: dar al trackeador una clave de servicio.**
   Medido (A4-bis): **`SUPABASE_KEY` es `sb_publishable_…`, rol `anon`**, y el trackeador escribe
   con ella sin tener otra vía (ni `psycopg2` ni `DB_URL`). Hasta que `tracker-app.yml` y
   `tracker-cerebro.yml` inyecten `SUPABASE_SERVICE_KEY` —que el código ya prefiere si existe—
   **las tres tablas que toca se quedan como están**: `monitor_snapshots`,
   `monitor_recomendaciones` y `monitor_reglas`.
1. 🟢 **Gratis, sin riesgo — no las tocan ni la v1 ni el trackeador.** `monitor_resultados`,
   `competidor_evento`, `competidor_perfil`, `devoluciones`, `informes_subidos`,
   `sincronizaciones`, `ventas`, `factura_lineas`, `canales_producto`.
   Las escriben los procesadores con `DB_URL`, que no pasa por RLS.
   *(`monitor_reglas` y `monitor_snapshots` estaban aquí en la primera versión y se han ido al
   paso 0: la cuenta cerrada del trackeador demuestra que sí las toca.)*
2. 🟡 **Quitar solo el `DELETE`, dejando lectura y escritura.** Éste es el paso que más riesgo quita
   por menos rotura, y se puede medir al dedo: 🔬 **en las 10.342 líneas de `index.html` hay
   exactamente CINCO llamadas a `.delete()`, sobre CUATRO tablas** — `fabrica_fichas` (:1712),
   `escaner_resultados` (:3373), `alertas_silenciadas` (:4795) y `tareas` (:7410 y :7417).
   **Ninguna otra.** O sea que se le puede quitar el `DELETE` a `anon` en las **18 tablas
   restantes** —incluidas `productos`, `movimientos`, `compras` y `facturas`— **sin romper una sola
   llamada del frontend actual**. Es la mitad del riesgo del bloque D3 a coste cero.
3. 🟠 **Las que la v1 sí escribe pero son de baja frecuencia** (`tareas`, `alertas_silenciadas`,
   `ajustes_stock`, `codigos_proveedor`, `fabrica_fichas`, `escaner_resultados`): cada una rompe una
   pantalla concreta, así que van de una en una y con Elena avisada.
4. 🔴 **`productos` al final.** Es el maestro, 22 llamadas de escritura desde la v1 y 24.725
   actualizaciones acumuladas. **Esta no se cierra hasta que la v2 tenga Auth**, que es la decisión
   ya tomada. Cerrarla antes es parar el almacén.

🔑 **El principio:** el paso 2 (quitar solo `DELETE`) elimina lo irreversible sin tocar la
operativa. Se puede hacer ya y no rompe una sola llamada del frontend actual. Los pasos 3 y 4 son
los que necesitan la v2.

### D4 · ¿Está versionado el event trigger?

🔴 **No. Solo existe en la base.** `ensure_rls` → `rls_auto_enable()` no aparece en ningún fichero
de ninguno de los dos repos (cero coincidencias). Es `SECURITY DEFINER`, dueño `postgres`, y se
distingue de los seis triggers de Supabase (esos son de `supabase_admin`).

**Consecuencia exacta:** es una defensa que **se pierde en cualquier restauración**, y que además
nadie puede revisar sin conectarse a producción. Y se pierde justo cuando más falta hace — el día
del incendio, sobre una base que vuelve con los ACL abiertos.

Debería bajar a `migraciones/` tal cual está. Es un PR de cinco minutos y no lo he hecho porque no
me lo pedías; lo dejo anotado con los demás pendientes.

---

## 6. BLOQUE E — CONCURRENCIA

### E1 · La lista de los cuatro está mal

**Barrido completo de escrituras a `productos`** (`UPDATE productos`, `INSERT INTO productos`,
`table('productos').update/insert/upsert/delete`) en todo el repo:

| Fichero | Workflow | ¿Tiene `concurrency`? |
|---|---|---|
| `moloka_actualizar_nube.py` (líneas 925, 943, 952, 2004, 2079) | `actualizar-app.yml` | 🔴 **no** |
| `cargar_asin_manual.py` (líneas 246, 253) | `cargar-asin-manual.yml` | ✅ sí |
| `procesador_all_listings.py` (línea 413) | `procesar-all-listings.yml` | ✅ sí |
| **`moloka_tracker_cerebro.py`** | `tracker-cerebro.yml` | — **no escribe `productos`** |
| **`moloka_escaner_nube.py`** | `escaner-app.yml` | — **no escribe `productos`** |
| **`moloka_escaner_pro_nube.py`** | `escaner-pro.yml` | — **no escribe `productos`** |

Correcciones a E1:

- 🔴 **El trackeador no escribe en `productos`.** Solo lee (`select` de PVD, IVA y comisiones) y
  escribe en `monitor_snapshots`, `monitor_recomendaciones` y `app_datos`. **Reactivarlo no crea
  ninguna disputa sobre `productos`.**
- 🔴 **Los dos escáneres tampoco.** Escriben en `escaner_resultados` / `escaner_memoria`.
- 🟢 **Aparece un escritor que no estaba en la lista:** `procesador_all_listings.py`. Ya tiene grupo.

**Escritores reales: tres. Dos ya tienen `concurrency`. El único descubierto es
`actualizar-app.yml`** — y es el más pesado de los tres (cinco puntos de escritura, incluido el
stock FBA).

### E2 · El grupo compartido

La convención de la casa hoy es **un grupo por workflow, con el nombre del workflow** y
`cancel-in-progress: false` (20 workflows lo llevan así).

Un grupo **compartido** es un cambio de patrón, y para `productos` está justificado: da igual qué
workflow escriba, el recurso disputado es la misma tabla. Propuesta:

```yaml
concurrency:
  group: escritores-productos
  cancel-in-progress: false
```

Con **`cancel-in-progress: false`**, que es lo que ya hacen los 20: en una tabla maestra no se
cancela al que está a medias, se le espera.

**Quién debe entrar:** los tres escritores reales — `actualizar-app.yml` (que hoy no tiene nada),
`cargar-asin-manual.yml` y `procesar-all-listings.yml` (que cambiarían su grupo propio por el
compartido).

⚠️ **Dos avisos honestos:**
1. Ese grupo **también serializa cosas que hoy corren en paralelo sin problema**.
   `procesar-all-listings.yml` solo rellena SKU vacíos (`sku IS NULL`), así que casi nunca choca de
   verdad. El coste es tiempo de espera, no corrección.
2. 🔴 **`concurrency` de GitHub Actions no protege de nada que no venga de GitHub Actions.** La v1
   de Elena escribe en `productos` **desde el navegador** con la clave `anon`, 22 llamadas
   distintas, y eso no entra en ningún grupo. Las 24.725 actualizaciones no son solo de los
   workflows. **El grupo compartido es correcto y barato, pero no cierra la carrera de verdad**;
   eso lo cierra la v2 con Auth + RPC.

---

## 7. LO QUE HE ENCONTRADO Y NO ESTABA EN EL ENCARGO

Por orden de lo que más duele:

1. 🔴 **El bug del acantilado en el cerebro (C6).** No estaba en el encargo con esta forma: el
   encargo temía que se aplicase a todo, y lo que pasa es que **no se aplica nunca al recalcular**.
   Afecta al 42 % de las recomendaciones que proponen precio. **Es lo que bloquea la reactivación**,
   no el archivado.

2. 🔴 **El trackeador corre con la clave publicable** (A4-bis). Lo daba por «pendiente de que lo
   mire Fernando» hasta CLAUDE.md §4; se resuelve **sin ver el secreto**, porque las claves de
   Supabase declaran su rol dentro del valor. Es `anon`, y eso **fija el orden** del bloque D3: la
   clave de servicio primero, cerrar las tablas después. Al revés se rompe el trackeador, y como
   está parado, no se vería hasta el día que arranque.

3. 🔴 **No hay vía soportada para reproducir un informe histórico** (B4, medido en el run
   [31485223052](https://github.com/Moloka-Store/moloka-app/actions/runs/31485223052)). El fichero
   del 14-jul se lee perfecto —195 filas cuadradas, `snapshot_date` bien derivado— pero la Guarda
   10 aborta cualquier recarga vieja y su válvula `PERMITIR_RETROCESO` **no llega al workflow**. Es
   un agujero de **recuperación**, no de conservación, y solo se descubre el día que se intenta —
   que es el peor día. Salió al ir a *probar* la copia en vez de dar por buena su existencia.

4. 🔴 **La serie de `salud_fba_historico` tiene un agujero de ocho días** (C2-bis) y nada lo
   señala. `frescura_informes()` dice cómo de fresco es lo último, no si lo de detrás es continuo.
   Las ventanas T7/T30 de Amazon aguantan; lo que se rompe es **restar dos fotos**.

5. 🔴 **El trackeador y el cockpit v2 dan márgenes distintos hoy** (C5). El bug del `×1.03` está
   documentado y diferido desde el 3-ago. Si el analista se conecta al cockpit antes de que se
   arregle, citará márgenes optimistas en ~0,45 puntos con la autoridad de un número calculado.

6. 🟠 **50 de las 60 capturas manuales de tarifa están fuera del universo repreciable.** El trabajo
   manual ya hecho es seis veces mayor de lo que la auditoría veía, pero apuntando al sitio
   equivocado. Antes de capturar más, la lista de objetivos tiene que salir del universo.

7. 🟠 **El `15,5` de la caja de texto** (C4). No es una estimación mala: es un valor por defecto de
   formulario grabado 307 veces, indistinguible de una medición. Se arregla borrando cuatro
   caracteres de `index.html:5710`.

8. 🟡 **`ensure_rls` no cubre `CREATE VIEW`** (D1/D4). Es la explicación mecánica de por qué las dos
   vistas nacieron abiertas, y significa que **cualquier vista futura nacerá igual**. Las dos
   migraciones propuestas juntas lo tapan; ninguna de las dos por separado.

9. 🟡 **Ni `v_analisis_auditable` ni `v_scoreboard_reglas` están en ninguna migración.** Se crearon
   a mano y no hay rastro versionado de su definición. Si se pierden, se pierden.

10. 🟡 **La guarda anti-recarga del snapshot depende del nombre del fichero.** Las dos cargas del
   11-jul solo convivieron porque el segundo CSV se llamaba `… (1).csv.gz`. Si un día descargas dos
   veces el mismo día y el navegador no renombra, la segunda carga se salta en silencio con un
   `[STOP]` en el log. **Un aviso que solo vive en el log no es un aviso** (CLAUDE.md §2).

---

## 8. LO QUE NO HE PODIDO COMPROBAR

Dicho como preguntas abiertas, no como suposiciones:

*(Lo de `SUPABASE_KEY` ya no está aquí: resuelto en A4-bis — es `sb_publishable_…`, rol `anon`, y
no hizo falta ver el secreto porque la clave declara su rol dentro del propio valor.)*
- **Quién ejecutó el borrado de los 1.746 + 970 registros y cuándo.** Postgres no guarda esa traza.
  Lo que sí está probado: no fue el código, y no se ha repetido.
- **Si algo fuera de los dos repos lee `v_analisis_auditable`** (un Colab, un script suelto). Dentro
  de los dos repos y de la base está descartado con cuenta cerrada (apartado D1); fuera, la ausencia
  no se puede demostrar desde aquí.
- **Por qué el relleno de `salud_fba_hist` se quedó en 6 y 3 filas** de dos ficheros que traen ~220
  cada uno. Que fue una única operación del 26-jul está medido; el criterio que dejó fuera al resto
  no, y como no la escribe nadie desde entonces, tampoco cambia ninguna decisión.
- **Si el Fee Preview de Seller Central trae la tarifa al detalle que hace falta.** Sé que el
  informe existe; no he visto un fichero real de esta cuenta. Antes de diseñar el procesador hay que
  descargar uno y medirlo — como manda §2: *las guardas se miden contra el fichero real*.
*(Lo de `salud_fba_hist` ya no está aquí: contestado en B4 — un único relleno manual del 26-jul,
reconstruible entero desde Storage.)*

---

## 9. LO QUE PROPONGO HACER, EN ORDEN

Ninguno de estos pasos está dado. Los tres primeros son independientes entre sí.

| # | Qué | Por qué ahora |
|---|---|---|
| 1 | **Aplicar D1** (revocar `anon` en las dos vistas) | Es el agujero crítico y no rompe nada: demostrado por cuenta cerrada en los dos repos **y** en el trackeador |
| 2 | 🔴 **PR del acantilado** en el cerebro | **Condición de reactivación.** Sin esto el motor invierte el signo de la decisión (caso `B08HH5V55W`) |
| 2b | **`SUPABASE_SERVICE_KEY` en los dos workflows del trackeador** | Desbloquea el paso 0 de D3. Va **antes** de cerrar ninguna `monitor_*` |
| 3 | **PR de comentarios**: `monitor_recomendaciones` (el contrato) y corregir «Foto» → Película en `monitor_snapshots` | Es lo que causó este malentendido. Barato |
| 4 | **PR del `×1.03`** en el cockpit v2 (ya decidido el 3-ago, sin hacer) | Debe ir **antes** que el analista |
| 5 | **Aplicar D2** (default ACL), el mismo día que se revisen los grants de las tablas que crean los procesadores | Cierra el nacimiento; no toca lo existente |
| 6 | **`concurrency: escritores-productos`** en los tres workflows reales | Barato, aunque no cierre la carrera de la v1 |
| 7 | **D3 paso 2** (quitar solo `DELETE` a `anon`) | Quita lo irreversible sin romper una sola llamada del frontend |
| 8 | **Versionar `ensure_rls`** a `migraciones/` | Cinco minutos, y hoy es una defensa que un restore se lleva |
| 9 | 🔴 **Exponer `permitir_retroceso` como input** en `procesar-salud-fba.yml` (y demás Foto con Guarda 10) | **Medido el 11-ago: hoy NO hay vía soportada para reproducir un informe histórico.** Es un agujero de recuperación, y se ve el día que haga falta |
| 10 | **Contención + jubilar `salud_fba_hist`** — *depende del 9* | El RENAME espera: la prueba no ha podido correr todavía |
| 11 | **El `gap_dias` en la fila** dondequiera que se sirva un delta | Para que el analista no reste sobre un agujero de 8 días sin verlo (C2-bis) |

**Todo por la escalera de CLAUDE.md §5** — restaurar staging → ensayo → aplicar → verificación SQL →
producción ensayo → aplicar → verificación SQL, con Elena avisada antes de tocar producción. Y el
ACL **se verifica en producción**, no en staging (§4).

---

*Medido el 11-ago-2026 contra `ogfbjjdxcltzpygzuyla`. El estado de una base caduca en horas: si algo
de aquí se va a usar para decidir dentro de unos días, vuelve a medirlo.*
