# CLAUDE.md — moloka-app

Este fichero contiene lo que **no puedes deducir leyendo el código**: el porqué, las trampas y las
convenciones no estándar de esta casa. La estructura del repo, las dependencias y la arquitectura
las ves tú solo — no están aquí a propósito.

---

## 0. QUIÉN USA ESTO

**Elena usa esta app a diario para operar un almacén real.** Moloka Store S.L.U. vende en Amazon
FBA Pan-EU (ES/IT/FR), Miravia y web propia. Si rompes la app, se para el almacén.

- **`index.html` (v1) está CONGELADO.** Solo bugs críticos. Es un monolito y no se refactoriza.
  Si tu cambio lo toca, párate y pregunta.
- **Cualquier cambio que roce la operativa de Elena se avisa ANTES de desplegar.**
- **Fernando no es programador.** Es economista y contable. Explica en cristiano, con analogías
  contables si ayudan. Él aprueba todos los PR.

---

## 1. LAS REGLAS QUE NO SE REINTERPRETAN

### 1.1 Identidad: dos ejes, no un maestro único
- **EAN = el producto físico.** Universal, cero huecos. Lo escribe la **factura** (fuente dura).
- **ASIN = la capa Amazon**, por país. Lo pega Fernando a mano desde el Seller.
- **SKU = un traductor de los informes del Seller. JAMÁS llave maestra.** Fue el error de la v1:
  cruzar por SKU dejó fuera al 41,7% del catálogo. El SKU **nace y muere**; un mismo ASIN puede
  tener dos vidas de SKU con stock en países distintos.
- **La llave de la capa Amazon es (ASIN, país).** Nunca el SKU.
- **"ASIN→EAN es 1:1" es la regla DE MOLOKA, no un hecho de Amazon.** Keepa devuelve varios EAN
  para algunos ASIN. Ir siempre ASIN→EAN, nunca EAN→ASIN (ambiguo con los packs).
- **Ningún informe del Seller trae EAN.** El puente EAN↔ASIN es responsabilidad de Moloka.
- **Fuentes duras escriben identidad; las blandas nunca.** Factura → EAN. All Listings → ASIN/SKU.
  **Keepa NO escribe identidad**, solo rellena huecos, y **NADA en fichas `es_chase=true`**.
- **`moloka_ean_norm()` ya existe en producción** (esquema `public`, `IMMUTABLE`, sin
  `SECURITY DEFINER`): úsala, no la reescribas.
  **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.** No es una
  descripción de hoy — hoy solo hay UN cruce que la usa (la vista de `procesador_keepa_escaparate.py`).
  Es la regla para el siguiente.

### 1.2 El país es una FILA, nunca un sufijo de columna
Sin excepciones. Si una tabla necesita `stock_es`, `stock_it`, está mal diseñada.

### 1.3 Los informes de Amazon JAMÁS se suman entre sí
Cada uno responde **una** pregunta y son universos distintos:

| Informe | Es | Responde |
|---|---|---|
| **INTERNACIONAL** | El INVENTARIO (replica la pantalla del Seller) | ¿Cuánto tengo y dónde? |
| **SALUD_FBA** | GESTIÓN (rotación, alertas). Solo ES. Llega ~10 días tarde con altas | ¿Cómo de sano está? |
| **PANEU_APTOS** | La dimensión Pan-EU. Es película: cambia en horas | ¿Qué me deja Amazon? |
| **LEDGER** | El EXTRACTO. Libro append, no foto | ¿De dónde salió y a dónde fue? |
| **ALL_LISTINGS** | La identidad (ASIN/SKU) | ¿Qué tengo listado? |
| **KEEPA (CSV)** | Mercado, fotos, competencia | ¿Qué pasa fuera? |

Si tu código suma dos de estos, está mal. Si dos discrepan, **no promedies ni lo achaques al
desfase: es un dato, y hay que explicarlo al dígito.**

### 1.4 Un informe caducado no da información incompleta: da información FALSA
Hermano de: **una cifra sin la fecha del dato que la sostiene es una cifra que miente.**

### 1.5 Los cálculos de rentabilidad de Amazon NO entran
Fernando: *"los míos son los buenos"*. Las fórmulas de rentabilidad, IVA y alertas están validadas
al céntimo y **no se reinterpretan**. `estimated-cost-savings-*` de salud_fba es **marketing**
(prometía 10.747 € con un almacenamiento real de 94,86 €/mes): jamás usarlo como "ahorro".

### 1.6 Los TRES CAJONES: cada tabla se escribe de UNA manera
Antes de escribir en una tabla, mira **en qué cajón está**. El cajón decide qué pasa con lo que ya
había, y los cajones no se mezclan:

| Cajón | Qué se hace con lo viejo | Quién vive aquí |
|---|---|---|
| **FOTO** | **Se tira la hoja vieja.** Lo que no viene en el fichero se **BORRA** | `salud_fba`, `listings_amazon`, `keepa_escaparate`, `paneu_aptos` + `paneu_oferta_pais`, custom analytics |
| **PELÍCULA** | **Se apila. NUNCA se borra** | `movimientos`, el ledger |
| **MAESTRO** | **Se MARCA. Ni se borra ni se sustituye** | `productos` |

- Una **FOTO** contesta *"¿cómo está esto AHORA?"*. Una fila que sobrevive a su fichero es un
  fantasma que descuadra el cruce. La memoria histórica **no vive aquí**: vive en la Película.
- Una **PELÍCULA** es un libro de asientos: append, jamás update destructivo. Borrar una línea del
  ledger es falsificar el extracto.
- Un **MAESTRO** es la identidad. Un producto que deja de venderse no se borra: se **marca**
  (`activo=false`). Borrarlo deja huérfanos los movimientos que lo citan.

🔴 **El error caro es tratar un cajón como si fuera otro.** Un upsert-sin-DELETE convierte una Foto
en un collage de dos días (fue el caso real de salud_fba, §2); un DELETE en una Película destruye
el histórico y no hay de dónde recuperarlo.

---

## 2. LOS PROCESADORES: EL PATRÓN

**El procesador nuevo se tiene que parecer a los que ya están en producción. Míralos antes de picar.**

- **NO HAY CABOS SUELTOS: el procesador no elige. O ABORTA o GRITA en el dato.**
  Fichero que no se entiende → aborta. Fichero que cuenta algo nuevo → guarda y avisa.
  Un aviso que solo vive en el log NO es un aviso.
- **Las guardas NO se copian entre procesadores: se MIDEN contra el fichero real de ese informe.**
  También para descartarlas (la guarda "una sola fecha" no vale para Keepa: su fecha vive en el
  nombre del fichero).
- **Cada fichero tiene SU encoding. No lo copies entre procesadores: mídelo contra el fichero real.**
  Lo que hay medido hoy, según el procesador de cada uno:
  - **PANEU_APTOS, SALUD_FBA y KEEPA → traen BOM** (`utf-8-sig`, con `cp1252` de reserva).
  - **ALL_LISTINGS → no consta medido.** Su procesador solo decodifica de forma tolerante; que no
    reviente no demuestra que el fichero lleve BOM.
  - **INTERNACIONAL → sin BOM** (medido en el PR #2; hoy solo vive como comentario en
    `procesador_paneu_aptos.py`). **LEDGER → no consta.** Ninguno de los dos tiene procesador en
    este repo todavía: cuando lo tengan, se mide, no se hereda de aquí.
- **El LEDGER se descarga SIEMPRE en `.txt`.** El `.csv` se come los ceros a la izquierda de
  MSKU/ASIN/FNSKU. Lo avisa el propio Seller.
- 🔴 **CUSTOM ANALYTICS se exporta SIEMPRE con el periodo «Desde el inicio de año».** Es el
  que viene por defecto (1-ene → hoy): **inicio FIJO, fin móvil**. Eso es lo que convierte
  el informe en un **contador acumulado** y lo que hace que restar dos lecturas signifique
  algo. El panel deja elegir otro rango (hay un *Custom date range* con tope de 92 días), y
  **cualquier otro periodo produce un fichero que NO es una lectura de este contador**: sus
  cifras son más pequeñas y, mezcladas con la serie, meten restas negativas.
  *Medido el 10-ago-2026: un export con rango corto (`metric-data (14)`) traía 246 ASIN
  contra los 321 de la lectura anterior y 1.583 bajadas sobre 2.214 comparaciones — un ASIN
  cualquiera pasaba de 35.400 visitas a 428.* La red que lo caza es la **guarda 6.14** del
  procesador, que ABORTA cuando el retroceso tiene la firma de otro rango; pero la red no
  sustituye a la regla, que es de quien exporta. *(Los criterios exactos viven en el código
  y en el `.yml` —van por la tercera versión en dos días—, no aquí: una nota con el criterio
  dentro se queda mintiendo en una semana.)*
- 🔬 **Y la red tiene un punto ciego MEDIDO: si la lectura de referencia se queda muy por
  detrás, un fichero de otro rango SUBE EN TODO y pasa por bueno.** No es una hipótesis: la
  pareja `2-ago DISCONTINUO → 7-ago` da **0 bajadas sobre 2.214 y las nueve métricas
  subiendo** — la misma firma exacta que una carga limpia (medido el 11-ago-2026). De ahí la
  **zona gris** de la 6.14: cuando la comparación no puede probar nada, para y pide un
  `forzar` en vez de dar un verde que no ha medido. 🔑 La regla de la que esto es un caso:
  **restar dos lecturas solo prueba algo si están cerca.**
- 🔴 **AMAZON RECALCULA PEDIDOS, NO TRÁFICO.** Es la regla que decide qué bajada significa
  algo: una cancelación o una devolución mueve unidades y euros —es la vida normal de un
  marketplace—, pero **nadie devuelve una visita**. Por eso el criterio de «desplome» de la
  guarda 6.14 mira **solo visitas, sesiones y buybox_visiones**, y las seis de pedido quedan
  fuera. *Medido el 11-ago-2026 sobre cuatro pares: en los tres buenos, CERO desplomes de
  tráfico (el falso rojo de IT eran 2 bajadas, las DOS de pedido); en el malo, 610.*
  🔒 **Y el suelo numérico se descartó CON DATOS, que es lo que lo hace una decisión y no un
  gusto:** exigir 50 uds / 500 € para mirar una bajada dejaría exentas el **89,3%** de las
  celdas de FR y el **78,4%** de las de IT (sobre las nueve columnas de la última lectura: FR
  1.764 celdas, IT 1.008). Eso no es afinar un criterio, es **apagarlo con un número
  inventado**. 🔑 La regla de la que esto es un caso: **un criterio se parte por la
  NATURALEZA del dato, no por un umbral que valga para todo.**
  ⚠️ **EL LÍMITE, que no está cerrado: no está probado que el tráfico no pueda bajar
  legítimamente.** Una fusión de fichas o una depuración de tráfico inválido por parte de
  Amazon lo harían. La evidencia son **3 pares buenos con cero y 1 malo con 610** — suficiente
  para elegir, no para dar el asunto por zanjado. **Si un día salta un desplome de tráfico con
  todo lo demás en orden, ÉSE es el caso a estudiar**, y lo que habría que cambiar entonces es
  el criterio, no el fichero. El procesador lo dice así en el aborto.
- ⚠️ **PENDIENTE — el agujero «VIEJA DETRÁS DE NUEVA».** Los criterios que comparan con la
  lectura anterior solo miran **hacia adelante** (`leido_at > ref_cual`). Una lectura ANTERIOR
  a la última cargada solo la ve la guarda 6.8, que **grita y sigue**. *Medido el 10-ago-2026
  (run 31416925455): `CA_ES_02ago_DISCONTINUO.xlsx` —246 ASIN contra 321 y 1.583 bajadas—
  pasó el ensayo ENTERO sin que nada lo parase.* Si entrara, quedaría intercalada entre el
  1-ago y el 7-ago, y el `lag()` de `v_demanda_asin_ultima` calcularía **7-ago menos 2-ago**:
  un delta falso enorme. El 11-ago-2026 se le quitó **una esquina, no el agujero**: el
  criterio de los acumulados negativos mide el FICHERO y no la comparación, así que corre en
  cualquier orden y ese DISCONTINUO ya no pasaría (trae dos negativos). Un export de otro
  rango **sin** negativos sigue colándose: **el orden de carga es responsabilidad de quien
  lanza y nadie lo comprueba del todo por él.**
- 🔴 **EL CONTADOR SE REINICIA EL 1-ENE-2027, Y ESE DÍA FALLA SEGURO.** Es la consecuencia
  directa de la regla de arriba: «Desde el inicio de año» tiene el **inicio fijo en el 1 de
  enero**, así que el 1-ene-2027 el acumulado vuelve a cero. Entonces:
  - la primera lectura de 2027 traerá cifras **muchísimo menores** que la última de 2026;
  - la **guarda 6.14 lo leerá como un retroceso y ABORTARÁ la carga** — hará bien, es justo
    lo que se le pidió, pero el informe se queda fuera;
  - y si alguien la fuerza, la resta entre la última de 2026 y la primera de 2027 da **basura**.
  🔑 **Hoy la tabla no guarda DESDE CUÁNDO acumula cada lectura**: solo `leido_at`, que es
  *cuándo se exportó*. (Medido el 10-ago-2026: la única columna de fecha de `demanda_asin` es
  `leido_at`.) El año se puede **derivar** de ahí mientras se cumpla la regla del periodo,
  pero **derivarlo no es guardarlo**, y ahora mismo nada obliga a que la comparación se quede
  dentro del mismo año de acumulación.
  **LO QUE HAY QUE HACER, y va con el PR del modelo** —el de la columna de huella y el
  `rn = 1`, porque toca lo mismo—: **la guarda de no retroceso y la comparación entre lecturas
  deben quedarse dentro del mismo AÑO DE ACUMULACIÓN, y ese año merece estar en la tabla.**
  ⚠️ Lo que lo hace urgente sin serlo hoy: **no falla hasta el 1 de enero, y entonces falla
  seguro.** No es un riesgo que pueda o no darse: es una cita con fecha. Lo vio Fernando el
  10-ago-2026.
- ⚠️ **Y el panel de Custom Analytics va DÍAS POR DETRÁS.** El 10-ago-2026 avisaba *"datos
  disponibles hasta el 1/8/2026"*: **nueve días**. Consecuencias que no se pueden olvidar:
  dos exportaciones de días distintos pueden traer **cifras idénticas** (el corte no se
  movió — no es un fichero duplicado), y `leido_at` es **cuándo se exportó, no la fecha de
  los datos**. Restar dos lecturas mide **la cadencia de Amazon**, no lo que pasó en el
  mercado entre esas dos fechas: vale para tendencia y para comparar ASIN, no para decir
  *"en agosto se vendieron X"*.
- **La DESPENSA COMÚN:** `crudo` guarda todas las columnas aunque hoy no se usen. Caso real: el
  `sales-rank` llevaba semanas descargándose sin mirarse — y resultó ser el detector de ASIN muertos.
- 🔴 **Los CSV de Keepa en Storage (`informes/keepa_escaparate/`) NO SE BORRAN NUNCA.** Dejaron de
  ser fichero temporal el día que `keepa_escaparate_hist` dejó de guardar `crudo` (29-jul-2026):
  pasaron a ser **el archivo histórico permanente**. Ese `crudo` era copia byte a byte del CSV y se
  sacó de la base porque estaba duplicado con 25× menos margen (BD 500 MB vs Storage 1 GB), pero las
  512 claves que solo viven ahí siguen siendo munición del trackeador. **El rescate de cualquiera se
  hace por `keepa_escaparate_hist.fichero` → `informes/keepa_escaparate/<fichero>`.** Borrar esos CSV
  para "hacer sitio" es borrar el histórico sin vuelta atrás. Es la CONTRAPARTIDA del `DROP COLUMN
  crudo` (migración `2026-07-29_keepa_hist_drop_crudo.sql`): el DROP solo fue seguro porque el CSV se
  conserva. La misma regla aplica a cualquier `crudo` que en el futuro se mueva de la BD al Storage.

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
  (paneu, internacional, salud_fba, all_listings, keepa) ya están por lotes; el patrón está calcado
  de `procesador_ledger.py`, que nació así. **Si mañana nace un procesador nuevo, nace por lotes.**
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

## 3. VALIDACIÓN: QUÉ CUENTA COMO PRUEBA

🔴 **PROHIBIDO TEORIZAR.** Si no lo puedes medir en esta respuesta, di **"no lo sé"** y di qué
fichero o consulta lo contestaría. No inventes explicaciones plausibles.

- **La verificación final es SQL contra la BD. NUNCA el log.**
- **Compilar no es ejecutar.** `py_compile` pasa un script que redefine un built-in y peta en
  runtime. Ejecuta contra **el fichero real**.
- 🔴 **UN TEST VERDE SOLO CUENTA SI HAS VISTO SU NOMBRE EN LA SALIDA.** El «✅ TODO OK» del final
  **no demuestra que tu suite se haya ejecutado**: demuestra que no falló ninguno de los que
  corrieron. Si el tuyo no está en la lista, no ha corrido — y el runner no tiene forma de saber
  que falta. **Es el falso verde peor de todos: no es un test que falla, es un test que no existe**,
  y encima te da la sensación contraria.
  *Medido el 10-ago-2026 en `moloka-app-v2`: un suite nuevo quedó con el `import` puesto y sin su
  entrada en el array `SUITES` de `tests/run.mjs`. `npm test` dio «TODO OK» con 16 casos sin
  ejecutar. Se cazó al ir a leer el suite por su nombre en la salida en vez de fiarse del verde.*
  Regla práctica: después de añadir un suite, `npm test | grep "<su cabecera>"`. Si no sale, no
  existe. Vale igual para cualquier runner en el que registrar el test sea un paso aparte de
  escribirlo.
- 🔴 **ANTES DE CREAR RAMA, `git fetch`.** Una rama nacida de un `origin/main` viejo construye
  sobre un bug **ya arreglado**, y los tests no lo cazan porque el arreglo simplemente **no está**:
  no hay nada que se ponga rojo. Sales con todo en verde y devuelves el fallo a `main` por la
  puerta de atrás, encima con la firma de haberlo verificado.
  *Medido el 10-ago-2026: la rama de las seis correcciones de pantalla se creó de un `origin/main`
  que no tenía el PR recién fusionado con el arreglo del doble conteo de la tira de país. Se
  descubrió por casualidad, buscando otra cosa —el suite que no aparecía por su nombre, la regla de
  arriba— y se integró antes de seguir.*
  🔑 Y de ahí, lo que hay que hacer cuando pasa: **integrar `origin/main` EN CUANTO se detecta**, no
  al final. Cuanto más tarde, más código escrito sobre la base equivocada. Ojo también con `gh pr
  merge`: fusiona en GitHub y **no actualiza tu `origin/main` local** — hace falta el `fetch`.
- 🔴 **HAY VARIAS SESIONES SOBRE ESTE REPO A LA VEZ, y el accidente típico se lleva trabajo
  ajeno por delante.** El worktree que vas a crear puede tener el nombre ya cogido por otra
  sesión; entonces `git worktree add` falla, y si lo encadenaste con `&&`, **el `cd` no se
  ejecuta y todo lo que venga después corre en el repo principal** — que está en LA RAMA DE
  OTRO. Un `git add -A && git commit` ahí se lleva sus ficheros sin tocar dentro de tu commit.
  *Medido el 11-ago-2026: pasó exactamente eso, y el commit cayó en `claude/buzon-keepa-url`.
  Se salvó porque el `push` falló solo (la rama no tenía remoto) y se deshizo con `git reset
  --mixed HEAD~1`, que quita el commit SIN tocar los ficheros — el `--hard` habría borrado el
  trabajo de la otra sesión.*
  🔑 Las tres cosas que lo evitan, por orden de utilidad:
  1. **Nombre de worktree único por encargo** (`moloka-v2-<tema>`), y si `add` falla, PARAR —
     no seguir con los comandos encadenados.
  2. **`git add <fichero>`, no `git add -A`**, cuando el cambio son uno o dos ficheros. Es lo
     único que habría hecho inofensivo el accidente.
  3. Antes de commitear en un sitio del que no vienes: `git branch --show-current`.
- **Los datos sintéticos no prueban nada.** Una vista se prueba con la tabla **poblada**.
- **Escribe los números esperados ANTES de correr.** Si no salen, di lo que sale — no ajustes la
  expectativa al resultado.
- **Haz saltar las guardas a propósito** antes de dar un procesador por bueno.
- 🔴 **UNA GUARDA COMPARA INVARIANTES, NO CIFRAS ABSOLUTAS** — y con más motivo si mide algo que
  el backup no copia. `backup-bd.yml` vuelca con `--schema=public`, así que `storage`, `auth` y
  todo lo demás **no están en la copia** y `restaurar-staging.yml` no los repone. Cualquier número
  fijo sobre lo que no se copia da **rojo en staging por el alcance del backup, no por la
  migración**: un falso rojo esperando su día.
  *Medido el 10-ago-2026 en `2026-08-10_buzon_custom_analytics.sql`: el encargo pedía comprobar
  `n_politicas <> 4` sobre `storage.objects`. Se cambió a guardar el recuento ANTES y compararlo
  DESPUÉS, porque el invariante real de un `CREATE OR REPLACE` es "no se llevó ninguna política
  por delante", y eso es cierto valgan 4 o valga otra cosa.*
  🔑 **La regla de la que esto es un caso: una comprobación que puede saltar por una causa
  distinta de la que dice medir no es una guarda, es ruido futuro.** Se deja de mirar en dos
  semanas — es el `ON_ERROR_STOP=0` por el otro extremo. El 10-ago-2026 el mismo patrón apareció
  **tres veces por caminos que no se parecen en nada**: los tipos (`Decimal` contra `float`, §2),
  un `LIKE` más ancho de lo que decía medir, y este número fijo de políticas. Antes de dar una
  guarda por buena, pregúntale: *¿puedes ponerte roja por el entorno, por el tipo de dato o por
  el alcance de una copia?* Si la respuesta es sí, todavía no es una guarda.
- 🔴 **UN ENSAYO SOBRE UN ESTADO QUE YA ES EL DE DESTINO NO PRUEBA NADA.** Sale verde,
  parece una verificación y no lo es: solo dice que el destino ya estaba como se quería.
  *Caso real del 10-ago-2026, y es mío: la migración de los comentarios de `demanda_asin` se
  probó primero "en humo" escribiéndola a mano en staging para ver si el SQL parseaba. Luego
  iba a correr el `aplicar` encima — sobre unos comentarios que ya eran los nuevos. Habría
  dado verde verificando algo que ya era cierto antes de empezar. Se salvó devolviendo
  staging al texto viejo ANTES del ensayo, y entonces sí midió algo.*
  **Antes de fiarte de un ensayo, mira en qué estado está el destino.** Aplica a todo lo
  idempotente: `CREATE OR REPLACE`, `IF NOT EXISTS`, `COMMENT ON`, un `setval` que ya estaba
  bien, un upsert que no cambia una fila. Y es hermano del simulacro de restauración: una
  copia en la que se confía y que nadie ha probado **contra un estado distinto** no está
  probada.
  📌 **PENDIENTE — convertirlo en guarda, que es mejor que en regla.** `aplicar-migracion.yml`
  puede detectarlo solo: si en modo `ensayo` la migración no cambia NADA —cero filas
  afectadas, cero objetos tocados— que lo GRITE (*"este ensayo no ha cambiado nada; o la
  migración es un no-op o el destino ya estaba en el estado final, y en los dos casos esto
  NO prueba que funcione"*). **Sin abortar**: hay migraciones legítimamente idempotentes que
  se relanzan a propósito. Pero que un verde mudo no pueda hacerse pasar por una
  verificación. Va **detrás** del registro de migraciones de §4.
- **"Lo ha revisado un agente" NO es prueba.** Un revisor lee código, no lo ejecuta.
- **Greps parciales no son lectura.** Si te preguntan "¿seguro que el código hace X?", lee el
  fichero entero.
- 🔴 **"Es idéntico en efecto" es una hipótesis. Para demostrar que un cambio en la CAÑERÍA no
  cambia nada: DOS RECORRIDOS COMPLETOS Y LAS MISMAS HUELLAS.** Estrenado el 9-ago-2026 con el
  `search_path` explícito de `aplicar-migracion.yml`. El método:
  1. `restaurar-staging.yml` → `ensayo` → `aplicar`, con la versión **vieja**, y tomar las huellas
     md5 del estado resultante.
  2. El mismo recorrido entero con la versión **nueva**.
  3. Comparar. Si salen idénticas, el cambio es inerte **medido sobre el resultado**, no
     argumentado — y entonces sí se puede llevar a la base de Elena.

  **Las siete huellas**, que juntas describen la forma de la base: columnas+tipos · definición de
  los índices · restricciones · firma de las funciones · políticas con su `qual` · SQL de las
  vistas · ACL. *Staging no tiene los mismos nombres que producción: tiene la misma FORMA.*
  🔒 **La huella se calcula desde UN solo sitio** (`sql/huella_acl.sql` para los ACL). Dos códigos
  que hoy coinciden es una coincidencia, no una garantía: el día que alguien retoque uno, la
  comparación empieza a mentir sin que nadie lo note. Es el hermano del `LC_ALL=C`.
  ⚠️ Y sirve para lo contrario también: si las huellas que **deben** cambiar cambian y las que
  **no** deben, no, eso demuestra que la migración hace lo que dice **y nada más**.

### El estado vive en el repo, no en las notas
- Antes de afirmar el estado de cualquier pieza: **míralo**. Las notas de ayer mienten hoy.
- `raw.githubusercontent.com` tiene retraso de caché tras un commit. Para leer el repo desde fuera:
  **tarball por `codeload.github.com`**. La API de GitHub sin token da 60 peticiones/hora por IP.

---

## 4. SEGURIDAD

- 🔴 **Las credenciales NUNCA van en el código ni en un mensaje.** Viven en GitHub Secrets, Vercel
  y R2. Una llave que aparece en un chat está quemada y se regenera.
  **Introducir credenciales no es algo que hagas tú: se lo pides a Fernando.**
- **Supabase es PRODUCCIÓN.** Desde una sesión: **solo lectura**. Toda escritura va por
  rama → PR → Fernando aprueba → ensayo en staging → producción.
- **Todo lo NUEVO nace CERRADO:** RLS activo y 0 políticas. Vistas `security_invoker`. Funciones
  `IMMUTABLE`, sin `SECURITY DEFINER`.
- 🔴 **Pero "nace cerrado" NO es el estado por defecto: hay que REVOCAR antes de conceder.**
  Medido el 30-jul-2026 en `pg_default_acl` de las DOS bases: en `public`, toda **tabla o vista**
  nueva nace con **`arwdDxtm` concedido a `anon` Y a `authenticated`**, y toda **función** nueva con
  `EXECUTE` para `anon`. Son DEFAULT PRIVILEGES de Supabase y **un `revoke … from public` NO los
  quita** (son grants explícitos a un rol, no a `public`). Si escribes `grant select, insert to
  authenticated` y te quedas ahí, **el grant no añade nada porque ya lo tenía todo**: el `relacl`
  sigue diciendo `authenticated=arwdDxtm`. Hay que revocar a **cada rol por su nombre** antes de
  conceder — `revoke all on <objeto> from public, anon, authenticated;` y luego el `grant` mínimo —
  y **MEDIR** el resultado (`pg_class.relacl` / `pg_proc.proacl`), no suponerlo.
  Afecta a **todo objeto nuevo**, también a las tablas que crean los procesadores.
- 🔴 **Y no basta con revocar AL CREAR: hay que revocar CADA VEZ QUE SE RECREA.**
  `CREATE OR REPLACE` **conserva** el ACL; **`DROP` + `CREATE` lo PIERDE**, y el objeto vuelve a nacer
  con el default puesto, o sea con `anon` dentro. Caso real medido el 30-jul-2026:
  `entrada_factura_pvd` tenía `anon=X` en **staging** y no en producción, **aunque su migración lleva
  el `revoke`** — alguien la había recreado con DROP+CREATE y aquel revoke ya no aplicaba a la función
  nueva. No era explotable (aritmética pura, `IMMUTABLE`, no lee tablas), pero **las dos bases dejaron
  de ser iguales, y entonces un ensayo en staging ya no demuestra nada sobre producción**. Corregido
  con un `revoke … from anon` en staging.
  Regla práctica: **si la migración lleva un `drop`, el `revoke` va DESPUÉS del `create`, en la misma
  migración, y se mide el ACL al terminar.**
- **La v1 tiene escritura anónima abierta** (deuda estructural). **No se toca a mitad de vuelo**:
  se cierra en la v2 con Auth + RPC. El problema no es la llave `publishable` (es pública por
  diseño): son las políticas.
- **SP-API: jamás con credenciales de Moloka SL.** Decidido y cerrado. Las cuentas de Moloka
  (Elena) y Fernando (autónomo) están separadas a nivel de credenciales.
- **Confirmar una factura SIEMPRE inyecta stock.** Nunca subir facturas antiguas retroactivamente.
- 🔴 **PENDIENTE — el backup NO copia los permisos: restaurar te deja la base ABIERTA.**
  `backup-bd.yml` vuelca con `--no-privileges`, así que el fichero **no contiene ni un `GRANT` ni un
  `REVOKE`**. Dicho en alto y sin adornos: **el día que haya que restaurar de verdad, la base vuelve
  con los ACL por defecto de Supabase — o sea, con `anon` dentro de todo** (es el mismo
  `pg_default_acl` de los dos puntos de arriba: los objetos nacen con `arwdDxtm` para `anon` y
  `authenticated`, y aquí nadie revoca después). Restauras el incendio y te queda la casa abierta.
  **Esto no es una nota al pie: es un frente propio y hoy está abierto.** Lo que falta por decidir en
  frío es cuál de los dos caminos: que el volcado se lleve los privilegios (quitar `--no-privileges`,
  y entonces el dump arrastra dueños y ACL, con lo que eso implica al restaurar en otro proyecto), o
  que el restore aplique al terminar un guion de permisos propio y **medido**. Sin cerrar desde el
  9-ago-2026.
  🔬 **YA NO ES HIPOTÉTICO: medido el 10-ago en staging, recién restaurado.** `v_velocidad_ventas` y
  `v_producto_amazon` tenían ahí `anon=arwdDxtm`, y en producción las dos tienen `authenticated=r`
  sin `anon`. La restauración las devolvió abiertas, exactamente como dice el párrafo de arriba.
  🔒 **Y de ahí sale una REGLA para cualquier migración que se ensaye:** *un test de ACL en staging
  NO prueba nada sobre producción.* Staging viene del dump sin privilegios, así que sus ACL son los
  de Supabase por defecto, no los de prod. La ÚNICA excepción es el objeto que crea la propia
  migración que estás ensayando, porque lleva su `revoke` dentro y por eso sí nace bien allí.
  **Conclusión práctica: el ACL se verifica EN PRODUCCIÓN, después de aplicar** — `relacl` y
  `has_table_privilege('anon', …)`, no en el ensayo. Con `v_presencia_pais` se hizo así.
- ⚠️ **PENDIENTE — el simulacro comprueba que las SECUENCIAS existan, y eso no es lo que importa.**
  Una secuencia puede volver de la copia **existiendo y con el contador a 1 sobre una tabla llena**:
  la primera inserción del día del incendio choca con clave duplicada. Por nombre, eso sale **verde**.
  El contraste que vale es de **valores**: los `setval` que emite el dump contra
  `pg_sequences.last_value`. Medido el 9-ago-2026: las **23** secuencias de producción tienen el
  contador avanzado (0 sin estrenar), así que le aplica a las 23. `restaurar-staging.yml` ya
  imprime en cada ejecución cuántos `setval` trae el dump, para que el agujero se vea. Es otro
  diseño y merece su propio PR.
- ⚠️ **PENDIENTE — el simulacro no compara las RESTRICCIONES, y son las que deciden si un ensayo vale.**
  Lo que importa de un índice no es el índice: es la **garantía**. Si staging admite un duplicado que
  producción rechaza, un ensayo sale verde y la migración revienta al aplicarla de verdad — que es
  exactamente el agujero que el simulacro existe para cerrar. Y las garantías viven en
  `pg_constraint` (PK, UNIQUE, FK, CHECK), con nombre, y en el dump como `ADD CONSTRAINT`:
  comparación limpia. Ojo al detalle que hace inútil el atajo: **los índices que respaldan una PK o
  un UNIQUE NO aparecen en el dump como `CREATE INDEX`**, sino dentro de un `ALTER TABLE … ADD
  CONSTRAINT`, así que contar `CREATE INDEX` da de menos y se inventa un rojo falso. Los índices de
  puro rendimiento no cambian si un ensayo es válido. Ese PR se llama **restricciones**, no índices.
- ⚠️ **PENDIENTE — la copia de FICHEROS a R2 no tiene simulacro de restauración.** Desde el
  30-jul-2026 el backup diario (`backup-bd.yml` + `backup_storage.py`) copia a R2 los buckets
  `facturas-pdfs` e `informes` (las facturas de proveedor y el archivo histórico de Keepa). Pero
  `restaurar-staging.yml` solo ensaya el incendio de la **BD**: **esos ficheros no los recupera ni
  los abre nadie nunca.** Es el MISMO agujero que motivó todo esto (una copia en la que se confía y
  que nadie ha probado), en el otro activo. Falta un `restaurar-ficheros` que baje de R2 una muestra
  y compruebe que abre. Hasta que exista, la copia de ficheros está **hecha pero no verificada de
  extremo a extremo**. *(El backup sí tiene número de control externo contra `storage.objects`, así
  que una copia CORTA no pasa por buena — pero eso valida la subida, no la restauración.)*
- 🔴 **PENDIENTE — las tablas `monitor_*` del trackeador están abiertas a `anon`, y no solo para
  leer: para BORRAR.** Medido el 10-ago en producción, al cerrar el gate de las tres vistas (§6):

  | Tabla | Política | Rol | Qué permite |
  |---|---|---|---|
  | `monitor_reglas` | `anon_all_regla` `ALL using(true)` | **anon** | leer, MODIFICAR y **BORRAR** |
  | `monitor_snapshots` | `anon_all_snap` `ALL using(true)` | **anon** | leer, MODIFICAR y **BORRAR** |
  | `monitor_resultados` | `p_resultados_all` `ALL using(true)` | **PUBLIC** | leer, MODIFICAR y **BORRAR** |
  | `monitor_recomendaciones` | 2 políticas `anon` | **anon** | leer y ACTUALIZAR |
  | `monitor_analisis` · `monitor_doctrina` · `monitor_reponibilidad_manual` | — | — | ✅ RLS y 0 políticas: cerradas |

  `monitor_reglas` son **las 21 reglas del trackeador**: la doctrina de precios de la casa, expuesta a
  un `DELETE` anónimo. La clave publicable viaja en el JavaScript de la app por diseño, así que esto
  no es teórico.

  🔴 **PERO NO SE CIERRA A CIEGAS, y esta es la parte que hay que resolver ANTES:** hay que saber con
  qué clave escribe el trackeador. Medido en el repo: sus scripts hacen
  `os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']` (y `moloka_tracker_snapshot.py`
  usa **solo** `SUPABASE_KEY`, sin alternativa), y **sus dos workflows —`tracker-app.yml` y
  `tracker-cerebro.yml`— inyectan ÚNICAMENTE `secrets.SUPABASE_KEY`**, no la de servicio. O sea que
  el `or` cae siempre al mismo lado: **el trackeador corre con `SUPABASE_KEY`**.
  ⚠️ Lo que falta por saber es **qué contiene ese secret**: si es la publicable (`anon`), cerrar estas
  políticas **rompe el trackeador el día que vuelva a arrancar** — y está parado desde el 11-jul, así
  que el fallo no se vería hasta entonces, que es la peor forma de encontrarlo. Que los dos secrets
  existan por separado apunta a que son distintas, pero **no se ha comprobado y no se supone**.
  Lo mira Fernando (GitHub → Settings → Secrets); no se toca la BD hasta tenerlo.

  Cuando se sepa: si es `anon`, el arreglo es darle al trackeador la clave de servicio (que salta la
  RLS por `rolbypassrls`) y solo DESPUÉS quitar las políticas de `anon`. En ese orden, nunca al revés.
  ⚠️ Y `productos` sigue con **455 filas legibles por `anon`** (§6 ya lo señalaba): mismo frente.
- 🔴 **PENDIENTE — NO EXISTE UNA LISTA FIABLE DE QUÉ MIGRACIONES SE HAN APLICADO A PRODUCCIÓN.**
  `supabase_migrations.schema_migrations` existe y tiene **37 registros, el último
  `20260806085625`** — o sea del **6-ago-2026**. Ni el contador ni el `setval` del 10-ago están
  ahí, ni nada de lo aplicado desde entonces. **Medido el 10-ago-2026.**
  Son **dos agujeros, uno encima del otro**:
  1. `aplicar-migracion.yml` aplica con **psql directo**, no por la CLI de Supabase, así que ese
     registro no se toca nunca. No es un fallo del workflow: es que nadie lo escribe.
  2. Y esa tabla vive en el esquema **`supabase_migrations`**, mientras el volcado es
     `pg_dump --schema=public`. Así que **aunque estuviera al día, el backup no la copiaría.**

  🔴 **Lo que esto significa el día del incendio:** *"restaurar y reaplicar lo posterior al
  backup"* NO se puede resolver mirando la base. Hay que reconstruirlo del historial de runs de
  GitHub o de memoria — y la memoria es justo lo que no funciona a las tres de la mañana. Es el
  mismo patrón que las tres viñetas de arriba: **el estado en un sitio que el backup no cubre.**

  🔑 **El arreglo es barato porque la pieza ya existe:** el paso 8 de `aplicar-migracion.yml` YA
  calcula el `sha256` del fichero. Basta con que escriba una fila en una tabla **de `public`** —
  fichero, sha256, entorno, quién lo despachó, cuándo, y si fue `ensayo` o `aplicar`— y el
  registro pasa a **sobrevivir al restore**. Con eso, restaurar deja de ser *"acordarse"* y pasa a
  ser *"mira qué falta desde la fecha del dump"*. Va **detrás** del PR del modelo y del
  `--no-privileges`; se anota aquí para que no dependa de que alguien lo recuerde.

---

## 5. CÓMO SE TRABAJA AQUÍ

- **UN PR, UNA COSA.** Sin excepciones.
- 🔴 **ANTES DE ENSAYAR UNA MIGRACIÓN EN STAGING, SE RESTAURA STAGING.** Se lanza
  `restaurar-staging.yml` y se espera a que salga en VERDE. La escalera entera es:
  **restaurar staging → staging ensayo → staging aplicar → verificación SQL → producción ensayo →
  producción aplicar → verificación SQL**, con Elena avisada antes de tocar producción.
  **Por qué:** un ensayo en staging solo demuestra algo sobre producción si las dos bases se parecen.
  El 9-ago-2026 staging tenía 54 objetos contra los 83 de producción — faltaban 29, entre ellos
  `v_salud_asin` y `v_trackeador_cola` — y con eso los ensayos de semanas enteras no demostraban
  nada. El caso concreto: el ensayo de `2026-08-07_demanda_asin_contador.sql` murió con
  `ERROR: relation "v_salud_asin" does not exist`, que no era un problema de la migración sino de la
  base contra la que se probaba.
  **Y por qué así y no con un vigilante de deriva:** porque la deriva no se mide, se **elimina**. Una
  alarma diaria cuya única acción posible es siempre la misma —restaurar staging— se deja de leer en
  dos semanas. Es el `ON_ERROR_STOP=0` por el otro extremo. Restaurando antes de cada ensayo, staging
  nunca es más viejo que el backup de anoche y no queda deriva que vigilar.
- **Antes de picar: lee cómo se hizo lo anterior.** Hay procesadores en producción que funcionan;
  el siguiente se les tiene que parecer. Si algo se aparta del patrón, dilo y explica por qué.
- **Las dudas de diseño no se resuelven en caliente.** Se anotan en una línea y se deciden en frío.
- **Cuando Fernando dice "esto no me cuadra", PARA y baja al dato.** Acierta ~95% de las veces.
  Casos reales: un bug oficial de la API de Amazon (FBA_CORE), un envío perdido de 24 uds, un ASIN
  borrado con 12 uds dentro. En los cuatro, la explicación cómoda era la equivocada.
- **Darle la razón sin medir es fallarle.** Si tienes el dato y contradice lo que dice, enséñaselo.
- **Distingue "podría" de "está documentado".** Una hipótesis bien redactada no es un hecho.
  Si no lo has verificado ahora mismo, dilo.
- **Antes de decir "no se puede":** eso es una hipótesis. Agota la búsqueda (documentación oficial,
  la propia herramienta, la web). *"No conozco una manera"* ≠ *"no existe una manera"*.

### Gotchas del entorno
- **La máquina de Fernando es Windows y su terminal es PowerShell**, pero las herramientas ejecutan
  **Bash**. `&&` no funciona en su terminal; las here-strings de PowerShell (`@'...'@`) corrompen
  los mensajes de commit si las usas en Bash. Comandos de una línea, sintaxis Bash.
- **`workflow_dispatch` exige que el `.yml` esté en la rama por defecto.** Orden forzoso:
  fichero → merge → ensayo.
- **En un `.yml`, un `no` suelto es el BOOLEANO `false`, no la cadena "no"** (el "problema de
  Noruega": `NO` = Norway). *Medido el 11-ago-2026 sobre
  `procesar-custom-analytics.yml`: `options: [no, si]` de un input se lee `[False, 'si']`.*
  Las opciones y los defaults de texto van **entrecomillados**. Vale para `on`, `off`, `yes`,
  `y`, `n` y las variantes en mayúsculas.
- **Los commits de este repo se firman con la dirección noreply de GitHub.** El repo es PÚBLICO:
  no publiques correos reales en la historia. La identidad está en `git config --local`, nunca
  `--global`.

---

## 6. DÓNDE ESTÁ EL PROYECTO AHORA

La v2 ("el bicho") se construye con **patrón estrangulador**: nace al lado de la v1, sobre la misma
Supabase, y Elena se muda pestaña a pestaña. **Los datos no se mudan: se curan.** Una BD nueva serían
dos verdades y un descuadre garantizado.

**Fase 0 (la capa de datos) va PRIMERO** y está a medias. De la app v2 en sí (repo, pantallas, Auth)
no hay nada todavía, y está bien.

Orden de mudanza acordado: Inventario → Inicio → Alertas → Movimientos → Rotación+Rentabilidad →
*(frontera lectura/escritura)* → Entrada → Facturas → Envío FBA → Motores.

*Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pongas aquí — caduca en horas.*
