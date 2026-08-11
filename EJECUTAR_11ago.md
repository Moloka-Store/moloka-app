# SECUENCIA DE EJECUCIÓN — 11-ago-2026

**Los pasos que da Fernando, en orden.** Cada uno con qué comprobar después y qué hacer si sale mal.

### Leyenda

| | |
|---|---|
| 🟢 | **Reversible sin rastro.** Se deshace y queda como antes |
| 🟡 | **Reversible con trabajo.** Se puede volver atrás, pero hay que hacer algo más |
| 🔴 | **No reversible del todo.** Se puede deshacer el cambio, pero algo queda |
| ⛓️ | **Depende de un paso anterior** |

### Mapa de dependencias

```
PASO 1 (merge #143) ──┬──> PASO 2 (migración precio_tarifado)  ⛓️ el .sql tiene que estar en main
                      └──> PASO 5 (gate D1, opcional hoy)      ⛓️ ídem

PASO 0 (avisar a Elena) ──> PASO 3 (merge #149)   ⛓️ toca su pantalla

PASO 4 (SUPABASE_SERVICE_KEY) — independiente de todo lo demás
```

**Los pasos 3 y 4 no dependen del 1.** Se pueden hacer en cualquier orden respecto a él.

---

## PASO 0 · Avisar a Elena 🟢

**Antes del PASO 3, no antes de los demás.** Qué decirle, en una frase:

> *«Mañana cambia una cosa en Inventario: la casilla de Comisión de Amazon ya no aparece rellena
> con 15,5 — sale vacía cuando no lo sabemos. Puedes guardar igual, no te bloquea nada. Lo que
> pasa es que en las fichas sin comisión el margen dirá "no calculable" en vez de un porcentaje.
> Es a propósito: ese 15,5 no era un dato medido.»*

**Comprobación:** que te haya contestado. No hay más.

---

## PASO 1 · Fusionar el PR #143 🟢

Solo documentos y ficheros `.sql` que **no se ejecutan al fusionar**. Cero efecto sobre la app y
sobre la base.

```bash
gh pr merge 143 --squash
```

**Comprobar después:**
```bash
git fetch origin && git log origin/main --oneline -1
ls migraciones/2026-08-11_seller_obs_precio_tarifado.sql
```
Tiene que aparecer el commit del merge **y** existir el `.sql` en `main`.

🔴 **Ojo con la trampa documentada (CLAUDE.md §3):** `gh pr merge` fusiona en GitHub y **no
actualiza tu `origin/main` local**. Sin el `git fetch`, el `ls` te miente.

**Si sale mal:** si el merge da conflicto, no fuerces nada — avísame. Si ya fusionaste y quieres
deshacer: `gh pr revert` o un revert del commit. No hay nada aplicado que revertir.

---

## PASO 2 · Migración `precio_tarifado` 🟡 ⛓️ (necesita el PASO 1)

La escalera completa de CLAUDE.md §5. **Son cinco lanzamientos**, en este orden exacto.

> 🔑 **Antes de nada:** el id de cada run se toma de **la URL que imprime el dispatch**, nunca de
> `gh run list --limit 1` (§5: el run recién creado tarda en registrarse y «el último» puede ser
> el anterior, que suele estar en verde).

### 2.1 · Restaurar staging

```bash
URL=$(gh workflow run restaurar-staging.yml 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
**Comprobar:** que acabe en verde.
**Si falla:** para aquí. Sin staging restaurado, el ensayo no demuestra nada.

### 2.2 · Staging, ensayo *(lo corre de verdad y lo deshace)*

```bash
URL=$(gh workflow run aplicar-migracion.yml -f entorno=staging -f modo=ensayo -f fichero=2026-08-11_seller_obs_precio_tarifado.sql 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
**Comprobar:** verde, y en el log que no aparezca ningún `ERROR:`.
**Si falla:** el SQL tiene un problema. Mándame el log; no toques producción.

### 2.3 · Staging, aplicar

```bash
URL=$(gh workflow run aplicar-migracion.yml -f entorno=staging -f modo=aplicar -f fichero=2026-08-11_seller_obs_precio_tarifado.sql 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
**Comprobar — por SQL contra STAGING, no por el log** (§3). Debe dar `64 / 1 / 1`:
```sql
select count(*) filter (where precio_tarifado is not null) as con_precio,
       count(*) filter (where precio_tarifado is null)     as sin_precio,
       count(*) filter (where id = 62 and precio_tarifado = 20.49) as la_simulacion
  from public.seller_observaciones;
```
⚠️ **Si `con_precio` sale 65 y `sin_precio` 0**, algo rellenó la id 5: **para**. Es justo lo que no
debe pasar.

### 2.4 · Producción, ensayo

```bash
URL=$(gh workflow run aplicar-migracion.yml -f entorno=produccion -f modo=ensayo -f fichero=2026-08-11_seller_obs_precio_tarifado.sql 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
**Comprobar:** verde.

### 2.5 · Producción, aplicar

Lleva confirmación: hay que reescribir el nombre del fichero.

```bash
URL=$(gh workflow run aplicar-migracion.yml -f entorno=produccion -f modo=aplicar -f fichero=2026-08-11_seller_obs_precio_tarifado.sql -f confirmacion=2026-08-11_seller_obs_precio_tarifado.sql 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
**Comprobar:** la **misma consulta SQL de 2.3, contra producción**. Debe dar `64 / 1 / 1`.

🟡 **Si sale mal:** se deshace con `alter table public.seller_observaciones drop column precio_tarifado;`
La columna es aditiva y nada la lee todavía, así que quitarla no rompe nada. **Lo único que se
pierde es el relleno**, y es recalculable — está en la propia migración.

---

## PASO 3 · Fusionar el PR #149 🟡 ⛓️ (necesita el PASO 0)

Toca `index.html`, o sea la pantalla que Elena usa a diario. **Vercel despliega solo al fusionar.**

```bash
gh pr merge 149 --squash
```

**Comprobar después, en la app ya desplegada (no en el código):**
1. Abre una ficha **sin** comisión → la casilla sale **vacía**, con «sin medir» en gris.
2. Guarda sin ponerla → **guarda**, y avisa de que el margen saldrá «no calculable».
3. Abre la calculadora de Buy Box en esa ficha, mete un precio → dice **«Margen no calculable»**.
4. Abre una ficha **con** comisión → sigue mostrando su porcentaje y el margen de siempre.

**El punto 4 es el importante:** demuestra que no se rompió el camino bueno.

🟡 **Si sale mal:** `git revert` del commit de merge y push. Vercel vuelve a desplegar la versión
anterior en un par de minutos. **Avisa a Elena también de la vuelta atrás**, para que no piense que
lo de ayer fue cosa suya.

---

## PASO 4 · `SUPABASE_SERVICE_KEY` en el trackeador 🔴

**Independiente de todo lo demás.** Desbloquea el bloque D3 (poder cerrar `monitor_snapshots`,
`monitor_recomendaciones` y `monitor_reglas`), que hoy no se puede tocar porque el trackeador
escribe como `anon`.

### 4.1 · Crear el secret *(lo haces tú; yo no manejo credenciales)*

1. **Supabase** → proyecto de producción → *Project Settings* → *API keys* → copia la clave
   **secreta** (`service_role`, o `sb_secret_…` en el formato nuevo).
2. **GitHub** → `Moloka-Store/moloka-app` → *Settings* → *Secrets and variables* → *Actions* →
   **New repository secret**.
   - **Name:** `SUPABASE_SERVICE_KEY` *(exacto, así escrito)*
   - **Secret:** la clave.

🔴 **No la pegues en el chat ni en un commit.** Si aparece en algún sitio, se regenera (§4).

### 4.2 · Añadirla a los dos workflows

En `.github/workflows/tracker-app.yml` y `.github/workflows/tracker-cerebro.yml`, en el bloque
`env:` del paso que ejecuta Python, **añadir una línea** debajo de `SUPABASE_KEY`:

```yaml
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}   # ← nueva
```

**No hay que tocar el código.** Los dos scripts que corren en la nube ya la prefieren si existe:
`os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']`.

📌 *(`moloka_tracker_snapshot.py` en su modo CLI sí usa `SUPABASE_KEY` a secas, pero ningún workflow
lo lanza así: `tracker-app.yml` ejecuta la versión `_nube`. No estorba.)*

Va en su propio PR — es un cambio de workflow, no mezclarlo con nada.

### 4.3 · Comprobar

**No sirve mirar el log.** La prueba es que el trackeador escriba **teniendo la RLS cerrada**, y eso
solo se ve el día que se cierre. Lo comprobable hoy:

```bash
URL=$(gh workflow run tracker-cerebro.yml -f pais=ES 2>&1 | head -1); ID=${URL##*/}; echo $ID; gh run watch $ID
```
Tiene que acabar **en verde** y escribir recomendaciones nuevas. Si con la clave de servicio fallara
donde antes funcionaba, el problema es la clave (mal copiada o del proyecto equivocado).

🔴 **Por qué está marcado como no reversible del todo:** el run del cerebro **marca como `OBSOLETA`
las 191 recomendaciones `PENDIENTE` de julio** antes de escribir las nuevas. Quitar el secret
después no las devuelve a `PENDIENTE`. **No se pierde nada** —siguen consultables por
`estado='OBSOLETA'`— pero la pestaña dejará de mostrarlas. Es lo correcto: son de hace un mes.

⚠️ **Y esto NO enciende el trackeador para repreciar.** Sigue en pie la condición: **no se usa para
subir precios hasta que el cerebro recalcule la tarifa al cruzar los 20 €.** Este paso es solo para
poder cerrar las tablas.

---

## PASO 5 · *(opcional hoy)* Gate de seguridad D1 🟡 ⛓️ (necesita el PASO 1)

No lo pediste en la secuencia, pero está listo y es el agujero más grave del informe: `anon` puede
**borrar** `monitor_analisis` —las 284 filas de criterio— a través de `v_analisis_auditable`.

Misma escalera que el PASO 2, con `fichero=2026-08-11_gate_anon_vistas_monitor.sql`.
**Comprobación, en PRODUCCIÓN después de aplicar** (§4: el ACL no se verifica en staging):

```sql
select relname,
       has_table_privilege('anon', c.oid, 'SELECT') anon_lee,
       has_table_privilege('anon', c.oid, 'DELETE') anon_borra
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname='public' and c.relname in ('v_analisis_auditable','v_scoreboard_reglas');
```
Las cuatro celdas en `false`. Y `select count(*) from public.monitor_analisis;` debe seguir dando
**284**.

**Si sale mal:** `grant select on <vista> to anon;` lo devuelve como estaba.

---

## Resumen para tener al lado

| # | Qué | Riesgo | Depende de |
|---|---|---|---|
| 0 | Avisar a Elena | 🟢 | — |
| 1 | `gh pr merge 143` | 🟢 | — |
| 2 | Migración `precio_tarifado` (5 lanzamientos) | 🟡 | ⛓️ 1 |
| 3 | `gh pr merge 149` | 🟡 | ⛓️ 0 |
| 4 | `SUPABASE_SERVICE_KEY` | 🔴 | — |
| 5 | Gate D1 *(opcional)* | 🟡 | ⛓️ 1 |
