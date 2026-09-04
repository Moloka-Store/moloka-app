# Trampas medidas (no re-descubrir)

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

### Trampas medidas (no re-descubrir)
- **Filas fantasma: RESUELTO (PR #33, 20-jul-2026).** Antes las tablas-foto se cargaban con upsert
  **sin DELETE**: si el informe encogía (salud_fba: 195→188 SKU en dos días), quedaban filas viejas
  conviviendo con las nuevas. **Ya no. La Foto tira la hoja vieja** (§1.6). Las cuatro cañerías
  heredan el patrón de `foto_comun.py`: lo que no viene en el fichero se BORRA, con guarda
  anti-encogimiento (<50% de las filas previas → ABORTA) **antes** del borrado, y borrado y carga en
  la misma transacción.
  ✅ **El ACUERDO de "no se lanza salud_fba en `aplicar`" queda LEVANTADO.** La decisión que
  esperaba ya está tomada: se lanza como cualquier otro.
  ⚠️ Lo que sí sigue mereciendo aviso: **la PRIMERA pasada `produccion`+`aplicar` de cada cañería
  dará de baja los fantasmas acumulados**. Es lo que se busca, pero mira las bajas que anuncia el
  ensayo antes de aplicar.
  El ledger no tiene este problema: es Película, no Foto.
- **Escritura masiva: SIEMPRE por lotes (`execute_values`), JAMÁS un `cur.execute()` por fila
  (PRs #65-#68 y #70, 29-jul-2026).** El runner de Actions está en EEUU y Supabase en `eu-west-1`
  (Irlanda): cada `cur.execute()` es un viaje transatlántico de **~90 ms**. Un
  `for fila in filas: cur.execute(...)` de 3.806 filas = **5 m 48 s esperando a la red** (PanEU,
  medido en el run #14); el mismo volcado con `psycopg2.extras.execute_values` baja a **<10 s** y la
  ventana de locks sobre la tabla de Elena de ~6 min a segundos. Los cinco que iban fila a fila
  entonces (paneu, internacional, salud_fba, all_listings, keepa) se pasaron a lotes. **Hoy TODO
  VOLCADO DE FICHERO va por lotes** (medido el 28-ago recorriendo el árbol, no el texto). `salud_fba`
  ya no está en esa lista: su procesador se jubiló el 23-ago. El patrón está calcado de
  `procesador_ledger.py`, que nació así. **Si mañana nace un procesador nuevo, nace por lotes.**
  📌 Dos cosas quedan fuera del patrón, y conviene saber cuál es cuál:
  - `procesador_canal_amazon_es.py` **no es una excepción, es mejor**: escribe con un solo
    `INSERT … SELECT FROM v_canal_amazon_es`, o sea que las filas nunca salen de la base. Cero
    viajes. Si un día alguien «lo arregla» pasándolo a `execute_values`, lo **empeora**.
  - ⚠️ **La curación de SKU de `all_listings` SÍ sigue fila a fila**: un `cur.execute` de `UPDATE`
    sobre `productos` por cada ficha curable, dentro de un `for`. Es exactamente el patrón que este
    apartado prohíbe. Hoy no duele porque son pocas fichas, pero **paga los ~90 ms por fila como
    todo lo demás**, así que si un día crece, ahí está. *(Se encontró el 28-ago al comprobar una
    frase de este mismo párrafo que decía «ya no queda ninguno». No la había: quedaba ésta.)*
  🔴 **La trampa del lote:** con `execute_values` todas las filas van en UN comando, así que dos con
  la misma clave del `ON CONFLICT` abortan con `ON CONFLICT DO UPDATE command cannot affect row a
  second time` (fila a fila no saltaba: la segunda pisaba a la primera en silencio). Qué significa un
  duplicado se decide POR PROCESADOR y NO se copia entre ellos:
  - **Duplicado = "la última gana"** (paneu, all_listings: el informe puede repetir clave y es
    legítimo) → **deduplicar en Python** por la clave del `ON CONFLICT` antes del lote, quedándote con
    la última; y si descartas algo, GRÍTALO al log (fila a fila era invisible).
  - **Duplicado = informe CORRUPTO** con una guarda que ya ABORTA por él (salud_fba y keepa: Guarda 2,
    *"el procesador NO elige"*) → **NO deduplicar**: dedup enmascararía justo lo que la guarda manda
    gritar. Y dedup por la clave REAL de cada tabla, nunca una "colapsada" que dependa de un supuesto
    (internacional: el histórico se deduplica por `(sku, country, fecha_foto)`, no por `(sku, country)`).
  🔒 **Prueba de que el cambio no movió ni un dato:** mismo fichero, viejo(`main`) vs nuevo, `md5` del
  CONTENIDO de la tabla —`md5(string_agg((to_jsonb(t) - '<col now()>')::text, '|' order by pk))`,
  excluyendo la columna `now()` (`procesado_en`/`procesado_at`/`capturado_en`, cada tabla la suya)—
  idéntico. El diff de logs solo prueba los recuentos, NO que cada columna caiga en su sitio (el
  riesgo real al pasar a tuplas en `execute_values`).
- **Dos fórmulas de stock que NO se unifican.** Son asientos distintos y ninguna "corrige" a la otra:
  - **La columna de Amazon** (`Inventory Supply at FBA`, en salud_fba) `= available + fc-transfer +
    inbound-quantity`, **SIN `reserved`**. Verificado fila a fila; lo comprueba la Guarda 6. Es la
    aritmética interna del informe — **no es el stock de Moloka**.
  - **El stock de Moloka** (v1, `moloka_actualizar_nube.py`) `= available + reserved`, con
    **`fc-transfer` DENTRO de `reserved`** e **`inbound` aparte** (está de camino). El v1 rechaza a
    propósito la columna de Amazon: "inflaba el stock".
  🔴 **`fc-transfer` cambia de bando entre las dos.** Llevar el "SIN `reserved`" de la primera al v1
  borra el FC Transfer del stock — el error exacto contra el que el v1 avisa por escrito.
- ⚠️ **`productos.unidades_compradas` cuenta unidades FÍSICAS, no facturadas: el nombre engaña.**
  "Compradas" suena a lo que dice el papel y no lo es. Con los packs se ve a la vista: una línea de
  400 paquetes facturados que son 100 unidades físicas deja `unidades_compradas = 100`.
  **Está BIEN así y no se cambia.** Su único uso real es elegir la ficha principal al consolidar
  duplicados (*"Principal: la que tiene mas unidades_compradas historicas"*, `index.html:10171-10172`)
  y ahí las físicas son lo correcto: contando facturadas, la ficha de packs ganaría artificialmente.
  **No entra en costes ni en rentabilidad**, así que no hay riesgo contable — solo un nombre que
  miente. Medido el 30-jul-2026.
- 🔴 **Al comparar un número del FICHERO contra uno de la BASE, iguala los tipos ANTES.**
  `psycopg2` devuelve los `numeric` como **`Decimal` exacto**; el fichero da **`float`
  binario**. Y en Python `43.98 < Decimal('43.98')` es **`True`**, porque el float 43,98 vale
  en realidad 43,9799999… Medido el 10-ago-2026 con nueve importes reales de un export:
  **siete daban "bajada" siendo idénticos.**
  Una guarda de no-retroceso escrita sin igualar tipos **aborta cargas buenas y no da
  error**: dice que el contador retrocedió. Es peor que no tenerla, porque miente con
  autoridad. Se arregla con un `float()` en los dos lados.
  ⚠️ **Hoy solo hay UN procesador que cruce esos dos mundos** (`procesador_custom_analytics`),
  y no es suerte: **es que el patrón es nuevo.** Los demás son FOTO o PELÍCULA —tiran la hoja
  vieja o apilan—, así que ninguno necesita saber qué había antes. La comparación
  fichero-contra-base nació con el **modelo contador**; el día que otro informe acumulado
  tenga su cañería, hereda la trampa.
  🔒 Y la forma de dar por bueno el arreglo, que vale para cualquier bug de comparación:
  **las dos mitades**. Que el falso positivo desaparezca *y* que el verdadero siga saltando,
  con el recuento cuadrando al dígito contra la otra vía que mide lo mismo. Aquí: 1.583
  bajadas del fichero malo, idénticas a las que ya contaba el inventario, y 0 sobre el bueno.
- **`FNSKU = ASIN` ⇒ listing commingled** (pozo común por EAN entre vendedores). FNSKU propio
  (`X0…`) ⇒ etiquetado. Explica stock que aparece en países donde no enviaste nada.
- **El "país" del INTERNACIONAL puede ser de PROGRAMA, no físico** (stock en Praga contado como DE).
  Y CZ/SK no existen para ese informe, pero el ledger demuestra stock físico allí.
- **Dominios de Keepa: 3=DE · 4=FR · 8=IT · 9=ES** (10 es India). Ojo con el 8: es IT, no FR.
  *(Aquí vivió un aviso de "bug latente en `DOMINIO_NUM`" que se quedó mintiendo **10 días**
  después de estar arreglado — el mapa se corrigió el 20-jul-2026 en `007632c` y la nota siguió
  diciendo que estaba mal. Es el ejemplo de andar por casa de §3: **el estado vive en el repo, no
  en las notas**. Si dudas del mapa, míralo en el fichero; si lo cambias, borra la nota.)*

---
