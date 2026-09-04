# Los procesadores: el patrón

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

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
  - **PANEU_APTOS y KEEPA → traen BOM** (`utf-8-sig`, con `cp1252` de reserva). *(SALUD_FBA estaba
    en esta lista y se jubiló el 23-ago; su medición se fue con su procesador. Lo que lo relevó,
    INVENTARIO_FBA, tiene la SUYA propia, más abajo — no se hereda.)*
  - **ALL_LISTINGS → no consta medido.** Su procesador solo decodifica de forma tolerante; que no
    reviente no demuestra que el fichero lleve BOM.
  - **INTERNACIONAL → sin BOM** (medido en el PR #2). **LEDGER → no consta medido.**
    ⚠️ Aquí ponía que *«ninguno de los dos tiene procesador en este repo todavía»*: **los dos lo
    tienen** —`procesador_internacional.py` y `procesador_ledger.py`—, así que esa frase caducó
    cuando nacieron. Lo que sigue valiendo es la regla: el encoding **se mide contra el fichero
    real de cada informe**, no se hereda de la lista de al lado.
  - **INVENTARIO_FBA → sin BOM y en CRLF** (medido el 23-ago-2026 sobre `50632020686.txt`: los
    seis primeros bytes son `b'sku\tfn'`). Se decodifica con `utf-8-sig` igualmente —decodifica
    bien con BOM y sin él— y `cp1252` de reserva. Los CRLF los resuelve el propio `csv`.
    🔬 Y de paso, el aviso que deja: **el PESO tampoco se hereda ni se conjetura.** El encargo daba
    "97-107 KB" como fichero sano y el real pesa **68.365 bytes**; un umbral por bytes copiado de
    ahí habría RECHAZADO el fichero bueno. El peso de un TSV lo mandan los títulos de producto, que
    cambian solos. Se cuentan FILAS, que es lo que se quiere medir.
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
  📏 **Y hay que saber a CUÁNTO llega ese criterio, que no es a todo el catálogo.** Solo vigila
  al ASIN que tenga alguna métrica de tráfico ≥100 en la lectura anterior. *Medido el
  11-ago-2026 sobre la última lectura de cada país:* **ES 86,4%** de los ASIN (299/346),
  **IT 71,1%** (91/128), **FR 37,2%** (73/196). O sea que **en FR el criterio 3 solo mira a 4
  de cada 10 ASIN**: allí quien protege son el 2 y el 4. No es un fallo —por debajo de 100
  visitas un porcentaje no significa nada—, pero sí algo que **hay que volver a mirar cuando
  FR crezca**: la cobertura sube sola con el tráfico, y conviene saber cuándo deja de ser un
  país a medio vigilar.
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
