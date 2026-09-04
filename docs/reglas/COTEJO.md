# Cotejo línea a línea: v1_original.md antes y después de acortarlo

Este fichero es la **prueba** de que al acortar `CLAUDE.md` no se ha perdido
ni reescrito ni una sola regla. El reparto se hizo **moviendo rangos de líneas**
con un script, nunca copiando a mano, y aquí está el destino de **cada línea**
del fichero viejo.

Lo que garantiza la tabla, y vuelve a comprobarse con `python docs/reglas/cotejo.py`:

1. **Cada línea con texto** del `CLAUDE.md` viejo aparece **una vez y sólo una**
   en el `CLAUDE.md` nuevo o en un `docs/reglas/*.md`.
2. El texto de destino es **idéntico carácter a carácter** al de origen.
3. Lo único que no viaja son líneas **en blanco**; ninguna lleva texto.

| medida | valor |
|---|---|
| líneas del fichero viejo | 850 |
| de ellas, con texto | 796 |
| líneas con texto colocadas | 796 |
| ficheros de destino | 17 |

## Reparto por bloques

| líneas viejas | destino |
|---|---|
| 1-20 | `CLAUDE.md` |
| 21-23 | `docs/reglas/identidad.md` |
| 24-35 | `CLAUDE.md` |
| 36-41 | `docs/reglas/identidad.md` |
| 42-43 | `CLAUDE.md` |
| 44-71 | `docs/reglas/informes-amazon.md` |
| 72-73 | `CLAUDE.md` |
| 74-79 | `docs/reglas/rentabilidad-amazon.md` |
| 80-83 | `docs/reglas/tres-cajones.md` |
| 84-88 | `CLAUDE.md` |
| 89-108 | `docs/reglas/tres-cajones.md` |
| 109-233 | `docs/reglas/procesadores.md` |
| 234-327 | `docs/reglas/trampas-medidas.md` |
| 328-329 | `docs/reglas/tests-y-falsos-verdes.md` |
| 330-331 | `CLAUDE.md` |
| 332 | `docs/reglas/tests-y-falsos-verdes.md` |
| 333-335 | `CLAUDE.md` |
| 336-495 | `docs/reglas/tests-y-falsos-verdes.md` |
| 496-499 | `CLAUDE.md` |
| 500-534 | `docs/reglas/guardas-y-ensayos.md` |
| 535 | `CLAUDE.md` |
| 536-572 | `docs/reglas/censos-y-catalogos.md` |
| 573-574 | `CLAUDE.md` |
| 575-592 | `docs/reglas/huellas-y-cambios-inertes.md` |
| 593-594 | `CLAUDE.md` |
| 595-596 | `docs/reglas/gotchas-del-entorno.md` |
| 597-599 | `docs/reglas/huellas-y-cambios-inertes.md` |
| 600-601 | `docs/reglas/seguridad-permisos.md` |
| 602-608 | `CLAUDE.md` |
| 609-628 | `docs/reglas/seguridad-permisos.md` |
| 629-631 | `CLAUDE.md` |
| 632-633 | `docs/reglas/seguridad-permisos.md` |
| 634 | `CLAUDE.md` |
| 635-745 | `docs/reglas/pendientes-backup-y-permisos.md` |
| 746-747 | `docs/reglas/como-se-trabaja.md` |
| 748 | `CLAUDE.md` |
| 749-752 | `docs/reglas/como-se-trabaja.md` |
| 753-758 | `CLAUDE.md` |
| 759-788 | `docs/reglas/escalera-de-migraciones.md` |
| 789-795 | `CLAUDE.md` |
| 796-800 | `docs/reglas/como-se-trabaja.md` |
| 801-831 | `docs/reglas/gotchas-del-entorno.md` |
| 832-845 | `docs/reglas/donde-esta-el-proyecto.md` |
| 846-847 | `CLAUDE.md` |
| 848 | `docs/reglas/donde-esta-el-proyecto.md` |
| 849 | `CLAUDE.md` |

## Línea a línea

| vieja | nueva | fichero de destino | primeros caracteres de la línea |
|---|---|---|---|
| 1 | 1 | `CLAUDE.md` | # CLAUDE.md — moloka-app |
| 3 | 3 | `CLAUDE.md` | Este fichero contiene lo que **no puedes deducir leyendo el código**: el porqu |
| 4 | 4 | `CLAUDE.md` | convenciones no estándar de esta casa. La estructura del repo, las dependencia |
| 5 | 5 | `CLAUDE.md` | las ves tú solo — no están aquí a propósito. |
| 7 | 7 | `CLAUDE.md` | --- |
| 9 | 9 | `CLAUDE.md` | ## 0. QUIÉN USA ESTO |
| 11 | 11 | `CLAUDE.md` | **Elena usa esta app a diario para operar un almacén real.** Moloka Store S.L. |
| 12 | 12 | `CLAUDE.md` | FBA Pan-EU (ES/IT/FR), Miravia y web propia. Si rompes la app, se para el alma |
| 14 | 14 | `CLAUDE.md` | - **'index.html' (v1) está CONGELADO.** Solo bugs críticos. Es un monolito y n |
| 15 | 15 | `CLAUDE.md` | Si tu cambio lo toca, párate y pregunta. |
| 16 | 16 | `CLAUDE.md` | - **Cualquier cambio que roce la operativa de Elena se avisa ANTES de desplega |
| 17 | 17 | `CLAUDE.md` | - **Fernando no es programador.** Es economista y contable. Explica en cristia |
| 18 | 18 | `CLAUDE.md` | contables si ayudan. Él aprueba todos los PR. |
| 20 | 20 | `CLAUDE.md` | --- |
| 22 | 8 | `docs/reglas/identidad.md` | ## 1. LAS REGLAS QUE NO SE REINTERPRETAN |
| 24 | 24 | `CLAUDE.md` | ### 1.1 Identidad: dos ejes, no un maestro único |
| 25 | 25 | `CLAUDE.md` | - **EAN = el producto físico.** Universal, cero huecos. Lo escribe la **factur |
| 26 | 26 | `CLAUDE.md` | - **ASIN = la capa Amazon**, por país. Lo pega Fernando a mano desde el Seller |
| 27 | 27 | `CLAUDE.md` | - **SKU = un traductor de los informes del Seller. JAMÁS llave maestra.** Fue  |
| 28 | 28 | `CLAUDE.md` | cruzar por SKU dejó fuera al 41,7% del catálogo. El SKU **nace y muere**; un m |
| 29 | 29 | `CLAUDE.md` | tener dos vidas de SKU con stock en países distintos. |
| 30 | 30 | `CLAUDE.md` | - **La llave de la capa Amazon es (ASIN, país).** Nunca el SKU. |
| 31 | 31 | `CLAUDE.md` | - **"ASIN→EAN es 1:1" es la regla DE MOLOKA, no un hecho de Amazon.** Keepa de |
| 32 | 32 | `CLAUDE.md` | para algunos ASIN. Ir siempre ASIN→EAN, nunca EAN→ASIN (ambiguo con los packs) |
| 33 | 33 | `CLAUDE.md` | - **Ningún informe del Seller trae EAN.** El puente EAN↔ASIN es responsabilida |
| 34 | 34 | `CLAUDE.md` | - **Fuentes duras escriben identidad; las blandas nunca.** Factura → EAN. All  |
| 35 | 35 | `CLAUDE.md` | **Keepa NO escribe identidad**, solo rellena huecos, y **NADA en fichas 'es_ch |
| 36 | 10 | `docs/reglas/identidad.md` | - **'moloka_ean_norm()' ya existe en producción** (esquema 'public', 'IMMUTABL |
| 37 | 11 | `docs/reglas/identidad.md` | 'SECURITY DEFINER'): úsala, no la reescribas. |
| 38 | 12 | `docs/reglas/identidad.md` | **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.**  |
| 39 | 13 | `docs/reglas/identidad.md` | descripción de hoy — hoy solo hay UN cruce que la usa (la vista de 'procesador |
| 40 | 14 | `docs/reglas/identidad.md` | Es la regla para el siguiente. |
| 42 | 37 | `CLAUDE.md` | ### 1.2 El país es una FILA, nunca un sufijo de columna |
| 43 | 38 | `CLAUDE.md` | Sin excepciones. Si una tabla necesita 'stock_es', 'stock_it', está mal diseña |
| 45 | 8 | `docs/reglas/informes-amazon.md` | ### 1.3 Los informes de Amazon JAMÁS se suman entre sí |
| 46 | 9 | `docs/reglas/informes-amazon.md` | Cada uno responde **una** pregunta y son universos distintos: |
| 48 | 11 | `docs/reglas/informes-amazon.md` | \| Informe \| Es \| Responde \| |
| 49 | 12 | `docs/reglas/informes-amazon.md` | \|---\|---\|---\| |
| 50 | 13 | `docs/reglas/informes-amazon.md` | \| **INTERNACIONAL** \| El INVENTARIO por país (replica la pantalla del Seller |
| 51 | 14 | `docs/reglas/informes-amazon.md` | \| **INVENTARIO_FBA** \| El informe de gestión de inventario FBA. Nació por ** |
| 52 | 15 | `docs/reglas/informes-amazon.md` | \| **PANEU_APTOS** \| La dimensión Pan-EU. Es película: cambia en horas \| ¿Qu |
| 53 | 16 | `docs/reglas/informes-amazon.md` | \| **LEDGER** \| El EXTRACTO de UNIDADES. Libro append, no foto \| ¿De dónde s |
| 54 | 17 | `docs/reglas/informes-amazon.md` | \| **TRANSACCIONES** \| El EXTRACTO de EUROS. Uno por marketplace (ES/IT/FR/DE |
| 55 | 18 | `docs/reglas/informes-amazon.md` | \| **CUSTOM_ANALYTICS** \| La DEMANDA por ASIN (visitas, sesiones, conversión) |
| 56 | 19 | `docs/reglas/informes-amazon.md` | \| **ALL_LISTINGS** \| La identidad (ASIN/SKU) \| ¿Qué tengo listado? \| |
| 57 | 20 | `docs/reglas/informes-amazon.md` | \| **KEEPA (CSV)** \| Mercado, fotos, competencia \| ¿Qué pasa fuera? \| |
| 59 | 22 | `docs/reglas/informes-amazon.md` | ⚰️ **SALUD_FBA estuvo aquí y se jubiló el 23-ago-2026** ('migraciones/2026-08- |
| 60 | 23 | `docs/reglas/informes-amazon.md` | Amazon servía ficheros truncados; lo relevó INVENTARIO_FBA. 'procesador_salud_ |
| 61 | 24 | `docs/reglas/informes-amazon.md` | en el repo. ⚠️ Pero **la palabra 'salud_fba' sigue viva como VISTA de compatib |
| 62 | 25 | `docs/reglas/informes-amazon.md` | 'inventario_fba' — lo que se jubiló es el INFORME, no el nombre: si lo ves en  |
| 63 | 26 | `docs/reglas/informes-amazon.md` | fantasma. Y 'salud_fba_historico' **no se borra a propósito**: es memoria cong |
| 64 | 27 | `docs/reglas/informes-amazon.md` | 'v_nunca_enviado_fba' (por eso, cualquier cifra que salga de ahí necesita su f |
| 66 | 29 | `docs/reglas/informes-amazon.md` | 📌 'procesador_canal_amazon_es.py' **no está en la tabla y no es un descuido**: |
| 67 | 30 | `docs/reglas/informes-amazon.md` | Recalcula comisión y logística desde TRANSACCIONES, ya cargado. Es derivado, n |
| 69 | 32 | `docs/reglas/informes-amazon.md` | Si tu código suma dos de estos, está mal. Si dos discrepan, **no promedies ni  |
| 70 | 33 | `docs/reglas/informes-amazon.md` | desfase: es un dato, y hay que explicarlo al dígito.** |
| 72 | 40 | `CLAUDE.md` | ### 1.4 Un informe caducado no da información incompleta: da información FALSA |
| 73 | 41 | `CLAUDE.md` | Hermano de: **una cifra sin la fecha del dato que la sostiene es una cifra que |
| 75 | 8 | `docs/reglas/rentabilidad-amazon.md` | ### 1.5 Los cálculos de rentabilidad de Amazon NO entran |
| 76 | 9 | `docs/reglas/rentabilidad-amazon.md` | Fernando: *"los míos son los buenos"*. Las fórmulas de rentabilidad, IVA y ale |
| 77 | 10 | `docs/reglas/rentabilidad-amazon.md` | al céntimo y **no se reinterpretan**. 'estimated-cost-savings-*' de salud_fba  |
| 78 | 11 | `docs/reglas/rentabilidad-amazon.md` | (prometía 10.747 € con un almacenamiento real de 94,86 €/mes): jamás usarlo co |
| 80 | 11 | `docs/reglas/tres-cajones.md` | ### 1.6 Los TRES CAJONES: cada tabla se escribe de UNA manera |
| 81 | 12 | `docs/reglas/tres-cajones.md` | Antes de escribir en una tabla, mira **en qué cajón está**. El cajón decide qu |
| 82 | 13 | `docs/reglas/tres-cajones.md` | había, y los cajones no se mezclan: |
| 84 | 45 | `CLAUDE.md` | \| Cajón \| Qué se hace con lo viejo \| Quién vive aquí \| |
| 85 | 46 | `CLAUDE.md` | \|---\|---\|---\| |
| 86 | 47 | `CLAUDE.md` | \| **FOTO** \| **Se tira la hoja vieja.** Lo que no viene en el fichero se **B |
| 87 | 48 | `CLAUDE.md` | \| **PELÍCULA** \| **Se apila. NUNCA se borra** \| 'movimientos', el ledger, ' |
| 88 | 49 | `CLAUDE.md` | \| **MAESTRO** \| **Se MARCA. Ni se borra ni se sustituye** \| 'productos' \| |
| 90 | 16 | `docs/reglas/tres-cajones.md` | ⚠️ **'custom analytics' estaba en la fila FOTO y ahí no va.** Cambió de cajón  |
| 91 | 17 | `docs/reglas/tres-cajones.md` | lo dice su propio procesador en la cabecera (*«EL CAJÓN: PELÍCULA DE LECTURAS» |
| 92 | 18 | `docs/reglas/tres-cajones.md` | una lectura** del contador, no sustituye la anterior. El cuadro se quedó con e |
| 93 | 19 | `docs/reglas/tres-cajones.md` | ⚰️ Y 'salud_fba' sale de la fila FOTO porque su informe se jubiló el 23-ago (§ |
| 94 | 20 | `docs/reglas/tres-cajones.md` | 'inventario_fba', que sí es Foto. |
| 96 | 22 | `docs/reglas/tres-cajones.md` | - Una **FOTO** contesta *"¿cómo está esto AHORA?"*. Una fila que sobrevive a s |
| 97 | 23 | `docs/reglas/tres-cajones.md` | fantasma que descuadra el cruce. La memoria histórica **no vive aquí**: vive e |
| 98 | 24 | `docs/reglas/tres-cajones.md` | - Una **PELÍCULA** es un libro de asientos: append, jamás update destructivo.  |
| 99 | 25 | `docs/reglas/tres-cajones.md` | ledger es falsificar el extracto. |
| 100 | 26 | `docs/reglas/tres-cajones.md` | - Un **MAESTRO** es la identidad. Un producto que deja de venderse no se borra |
| 101 | 27 | `docs/reglas/tres-cajones.md` | ('activo=false'). Borrarlo deja huérfanos los movimientos que lo citan. |
| 103 | 29 | `docs/reglas/tres-cajones.md` | 🔴 **El error caro es tratar un cajón como si fuera otro.** Un upsert-sin-DELET |
| 104 | 30 | `docs/reglas/tres-cajones.md` | en un collage de dos días (fue el caso real de salud_fba, §2); un DELETE en un |
| 105 | 31 | `docs/reglas/tres-cajones.md` | el histórico y no hay de dónde recuperarlo. |
| 107 | 33 | `docs/reglas/tres-cajones.md` | --- |
| 109 | 7 | `docs/reglas/procesadores.md` | ## 2. LOS PROCESADORES: EL PATRÓN |
| 111 | 9 | `docs/reglas/procesadores.md` | **El procesador nuevo se tiene que parecer a los que ya están en producción. M |
| 113 | 11 | `docs/reglas/procesadores.md` | - **NO HAY CABOS SUELTOS: el procesador no elige. O ABORTA o GRITA en el dato. |
| 114 | 12 | `docs/reglas/procesadores.md` | Fichero que no se entiende → aborta. Fichero que cuenta algo nuevo → guarda y  |
| 115 | 13 | `docs/reglas/procesadores.md` | Un aviso que solo vive en el log NO es un aviso. |
| 116 | 14 | `docs/reglas/procesadores.md` | - **Las guardas NO se copian entre procesadores: se MIDEN contra el fichero re |
| 117 | 15 | `docs/reglas/procesadores.md` | También para descartarlas (la guarda "una sola fecha" no vale para Keepa: su f |
| 118 | 16 | `docs/reglas/procesadores.md` | nombre del fichero). |
| 119 | 17 | `docs/reglas/procesadores.md` | - **Cada fichero tiene SU encoding. No lo copies entre procesadores: mídelo co |
| 120 | 18 | `docs/reglas/procesadores.md` | Lo que hay medido hoy, según el procesador de cada uno: |
| 121 | 19 | `docs/reglas/procesadores.md` | - **PANEU_APTOS y KEEPA → traen BOM** ('utf-8-sig', con 'cp1252' de reserva).  |
| 122 | 20 | `docs/reglas/procesadores.md` | en esta lista y se jubiló el 23-ago; su medición se fue con su procesador. Lo  |
| 123 | 21 | `docs/reglas/procesadores.md` | INVENTARIO_FBA, tiene la SUYA propia, más abajo — no se hereda.)* |
| 124 | 22 | `docs/reglas/procesadores.md` | - **ALL_LISTINGS → no consta medido.** Su procesador solo decodifica de forma  |
| 125 | 23 | `docs/reglas/procesadores.md` | reviente no demuestra que el fichero lleve BOM. |
| 126 | 24 | `docs/reglas/procesadores.md` | - **INTERNACIONAL → sin BOM** (medido en el PR #2). **LEDGER → no consta medid |
| 127 | 25 | `docs/reglas/procesadores.md` | ⚠️ Aquí ponía que *«ninguno de los dos tiene procesador en este repo todavía»* |
| 128 | 26 | `docs/reglas/procesadores.md` | tienen** —'procesador_internacional.py' y 'procesador_ledger.py'—, así que esa |
| 129 | 27 | `docs/reglas/procesadores.md` | cuando nacieron. Lo que sigue valiendo es la regla: el encoding **se mide cont |
| 130 | 28 | `docs/reglas/procesadores.md` | real de cada informe**, no se hereda de la lista de al lado. |
| 131 | 29 | `docs/reglas/procesadores.md` | - **INVENTARIO_FBA → sin BOM y en CRLF** (medido el 23-ago-2026 sobre '5063202 |
| 132 | 30 | `docs/reglas/procesadores.md` | seis primeros bytes son 'b'sku\tfn''). Se decodifica con 'utf-8-sig' igualment |
| 133 | 31 | `docs/reglas/procesadores.md` | bien con BOM y sin él— y 'cp1252' de reserva. Los CRLF los resuelve el propio  |
| 134 | 32 | `docs/reglas/procesadores.md` | 🔬 Y de paso, el aviso que deja: **el PESO tampoco se hereda ni se conjetura.** |
| 135 | 33 | `docs/reglas/procesadores.md` | "97-107 KB" como fichero sano y el real pesa **68.365 bytes**; un umbral por b |
| 136 | 34 | `docs/reglas/procesadores.md` | ahí habría RECHAZADO el fichero bueno. El peso de un TSV lo mandan los títulos |
| 137 | 35 | `docs/reglas/procesadores.md` | cambian solos. Se cuentan FILAS, que es lo que se quiere medir. |
| 138 | 36 | `docs/reglas/procesadores.md` | - **El LEDGER se descarga SIEMPRE en '.txt'.** El '.csv' se come los ceros a l |
| 139 | 37 | `docs/reglas/procesadores.md` | MSKU/ASIN/FNSKU. Lo avisa el propio Seller. |
| 140 | 38 | `docs/reglas/procesadores.md` | - 🔴 **CUSTOM ANALYTICS se exporta SIEMPRE con el periodo «Desde el inicio de a |
| 141 | 39 | `docs/reglas/procesadores.md` | que viene por defecto (1-ene → hoy): **inicio FIJO, fin móvil**. Eso es lo que |
| 142 | 40 | `docs/reglas/procesadores.md` | el informe en un **contador acumulado** y lo que hace que restar dos lecturas  |
| 143 | 41 | `docs/reglas/procesadores.md` | algo. El panel deja elegir otro rango (hay un *Custom date range* con tope de  |
| 144 | 42 | `docs/reglas/procesadores.md` | **cualquier otro periodo produce un fichero que NO es una lectura de este cont |
| 145 | 43 | `docs/reglas/procesadores.md` | cifras son más pequeñas y, mezcladas con la serie, meten restas negativas. |
| 146 | 44 | `docs/reglas/procesadores.md` | *Medido el 10-ago-2026: un export con rango corto ('metric-data (14)') traía 2 |
| 147 | 45 | `docs/reglas/procesadores.md` | contra los 321 de la lectura anterior y 1.583 bajadas sobre 2.214 comparacione |
| 148 | 46 | `docs/reglas/procesadores.md` | cualquiera pasaba de 35.400 visitas a 428.* La red que lo caza es la **guarda  |
| 149 | 47 | `docs/reglas/procesadores.md` | procesador, que ABORTA cuando el retroceso tiene la firma de otro rango; pero  |
| 150 | 48 | `docs/reglas/procesadores.md` | sustituye a la regla, que es de quien exporta. *(Los criterios exactos viven e |
| 151 | 49 | `docs/reglas/procesadores.md` | y en el '.yml' —van por la tercera versión en dos días—, no aquí: una nota con |
| 152 | 50 | `docs/reglas/procesadores.md` | dentro se queda mintiendo en una semana.)* |
| 153 | 51 | `docs/reglas/procesadores.md` | - 🔬 **Y la red tiene un punto ciego MEDIDO: si la lectura de referencia se que |
| 154 | 52 | `docs/reglas/procesadores.md` | detrás, un fichero de otro rango SUBE EN TODO y pasa por bueno.** No es una hi |
| 155 | 53 | `docs/reglas/procesadores.md` | pareja '2-ago DISCONTINUO → 7-ago' da **0 bajadas sobre 2.214 y las nueve métr |
| 156 | 54 | `docs/reglas/procesadores.md` | subiendo** — la misma firma exacta que una carga limpia (medido el 11-ago-2026 |
| 157 | 55 | `docs/reglas/procesadores.md` | **zona gris** de la 6.14: cuando la comparación no puede probar nada, para y p |
| 158 | 56 | `docs/reglas/procesadores.md` | 'forzar' en vez de dar un verde que no ha medido. 🔑 La regla de la que esto es |
| 159 | 57 | `docs/reglas/procesadores.md` | **restar dos lecturas solo prueba algo si están cerca.** |
| 160 | 58 | `docs/reglas/procesadores.md` | - 🔴 **AMAZON RECALCULA PEDIDOS, NO TRÁFICO.** Es la regla que decide qué bajad |
| 161 | 59 | `docs/reglas/procesadores.md` | algo: una cancelación o una devolución mueve unidades y euros —es la vida norm |
| 162 | 60 | `docs/reglas/procesadores.md` | marketplace—, pero **nadie devuelve una visita**. Por eso el criterio de «desp |
| 163 | 61 | `docs/reglas/procesadores.md` | guarda 6.14 mira **solo visitas, sesiones y buybox_visiones**, y las seis de p |
| 164 | 62 | `docs/reglas/procesadores.md` | fuera. *Medido el 11-ago-2026 sobre cuatro pares: en los tres buenos, CERO des |
| 165 | 63 | `docs/reglas/procesadores.md` | tráfico (el falso rojo de IT eran 2 bajadas, las DOS de pedido); en el malo, 6 |
| 166 | 64 | `docs/reglas/procesadores.md` | 🔒 **Y el suelo numérico se descartó CON DATOS, que es lo que lo hace una decis |
| 167 | 65 | `docs/reglas/procesadores.md` | gusto:** exigir 50 uds / 500 € para mirar una bajada dejaría exentas el **89,3 |
| 168 | 66 | `docs/reglas/procesadores.md` | celdas de FR y el **78,4%** de las de IT (sobre las nueve columnas de la últim |
| 169 | 67 | `docs/reglas/procesadores.md` | 1.764 celdas, IT 1.008). Eso no es afinar un criterio, es **apagarlo con un nú |
| 170 | 68 | `docs/reglas/procesadores.md` | inventado**. 🔑 La regla de la que esto es un caso: **un criterio se parte por  |
| 171 | 69 | `docs/reglas/procesadores.md` | NATURALEZA del dato, no por un umbral que valga para todo.** |
| 172 | 70 | `docs/reglas/procesadores.md` | ⚠️ **EL LÍMITE, que no está cerrado: no está probado que el tráfico no pueda b |
| 173 | 71 | `docs/reglas/procesadores.md` | legítimamente.** Una fusión de fichas o una depuración de tráfico inválido por |
| 174 | 72 | `docs/reglas/procesadores.md` | Amazon lo harían. La evidencia son **3 pares buenos con cero y 1 malo con 610* |
| 175 | 73 | `docs/reglas/procesadores.md` | para elegir, no para dar el asunto por zanjado. **Si un día salta un desplome  |
| 176 | 74 | `docs/reglas/procesadores.md` | todo lo demás en orden, ÉSE es el caso a estudiar**, y lo que habría que cambi |
| 177 | 75 | `docs/reglas/procesadores.md` | el criterio, no el fichero. El procesador lo dice así en el aborto. |
| 178 | 76 | `docs/reglas/procesadores.md` | 📏 **Y hay que saber a CUÁNTO llega ese criterio, que no es a todo el catálogo. |
| 179 | 77 | `docs/reglas/procesadores.md` | al ASIN que tenga alguna métrica de tráfico ≥100 en la lectura anterior. *Medi |
| 180 | 78 | `docs/reglas/procesadores.md` | 11-ago-2026 sobre la última lectura de cada país:* **ES 86,4%** de los ASIN (2 |
| 181 | 79 | `docs/reglas/procesadores.md` | **IT 71,1%** (91/128), **FR 37,2%** (73/196). O sea que **en FR el criterio 3  |
| 182 | 80 | `docs/reglas/procesadores.md` | de cada 10 ASIN**: allí quien protege son el 2 y el 4. No es un fallo —por deb |
| 183 | 81 | `docs/reglas/procesadores.md` | visitas un porcentaje no significa nada—, pero sí algo que **hay que volver a  |
| 184 | 82 | `docs/reglas/procesadores.md` | FR crezca**: la cobertura sube sola con el tráfico, y conviene saber cuándo de |
| 185 | 83 | `docs/reglas/procesadores.md` | país a medio vigilar. |
| 186 | 84 | `docs/reglas/procesadores.md` | - ⚠️ **PENDIENTE — el agujero «VIEJA DETRÁS DE NUEVA».** Los criterios que com |
| 187 | 85 | `docs/reglas/procesadores.md` | lectura anterior solo miran **hacia adelante** ('leido_at > ref_cual'). Una le |
| 188 | 86 | `docs/reglas/procesadores.md` | a la última cargada solo la ve la guarda 6.8, que **grita y sigue**. *Medido e |
| 189 | 87 | `docs/reglas/procesadores.md` | (run 31416925455): 'CA_ES_02ago_DISCONTINUO.xlsx' —246 ASIN contra 321 y 1.583 |
| 190 | 88 | `docs/reglas/procesadores.md` | pasó el ensayo ENTERO sin que nada lo parase.* Si entrara, quedaría intercalad |
| 191 | 89 | `docs/reglas/procesadores.md` | 1-ago y el 7-ago, y el 'lag()' de 'v_demanda_asin_ultima' calcularía **7-ago m |
| 192 | 90 | `docs/reglas/procesadores.md` | un delta falso enorme. El 11-ago-2026 se le quitó **una esquina, no el agujero |
| 193 | 91 | `docs/reglas/procesadores.md` | criterio de los acumulados negativos mide el FICHERO y no la comparación, así  |
| 194 | 92 | `docs/reglas/procesadores.md` | cualquier orden y ese DISCONTINUO ya no pasaría (trae dos negativos). Un expor |
| 195 | 93 | `docs/reglas/procesadores.md` | rango **sin** negativos sigue colándose: **el orden de carga es responsabilida |
| 196 | 94 | `docs/reglas/procesadores.md` | lanza y nadie lo comprueba del todo por él.** |
| 197 | 95 | `docs/reglas/procesadores.md` | - 🔴 **EL CONTADOR SE REINICIA EL 1-ENE-2027, Y ESE DÍA FALLA SEGURO.** Es la c |
| 198 | 96 | `docs/reglas/procesadores.md` | directa de la regla de arriba: «Desde el inicio de año» tiene el **inicio fijo |
| 199 | 97 | `docs/reglas/procesadores.md` | enero**, así que el 1-ene-2027 el acumulado vuelve a cero. Entonces: |
| 200 | 98 | `docs/reglas/procesadores.md` | - la primera lectura de 2027 traerá cifras **muchísimo menores** que la última |
| 201 | 99 | `docs/reglas/procesadores.md` | - la **guarda 6.14 lo leerá como un retroceso y ABORTARÁ la carga** — hará bie |
| 202 | 100 | `docs/reglas/procesadores.md` | lo que se le pidió, pero el informe se queda fuera; |
| 203 | 101 | `docs/reglas/procesadores.md` | - y si alguien la fuerza, la resta entre la última de 2026 y la primera de 202 |
| 204 | 102 | `docs/reglas/procesadores.md` | 🔑 **Hoy la tabla no guarda DESDE CUÁNDO acumula cada lectura**: solo 'leido_at |
| 205 | 103 | `docs/reglas/procesadores.md` | *cuándo se exportó*. (Medido el 10-ago-2026: la única columna de fecha de 'dem |
| 206 | 104 | `docs/reglas/procesadores.md` | 'leido_at'.) El año se puede **derivar** de ahí mientras se cumpla la regla de |
| 207 | 105 | `docs/reglas/procesadores.md` | pero **derivarlo no es guardarlo**, y ahora mismo nada obliga a que la compara |
| 208 | 106 | `docs/reglas/procesadores.md` | dentro del mismo año de acumulación. |
| 209 | 107 | `docs/reglas/procesadores.md` | **LO QUE HAY QUE HACER, y va con el PR del modelo** —el de la columna de huell |
| 210 | 108 | `docs/reglas/procesadores.md` | 'rn = 1', porque toca lo mismo—: **la guarda de no retroceso y la comparación  |
| 211 | 109 | `docs/reglas/procesadores.md` | deben quedarse dentro del mismo AÑO DE ACUMULACIÓN, y ese año merece estar en  |
| 212 | 110 | `docs/reglas/procesadores.md` | ⚠️ Lo que lo hace urgente sin serlo hoy: **no falla hasta el 1 de enero, y ent |
| 213 | 111 | `docs/reglas/procesadores.md` | seguro.** No es un riesgo que pueda o no darse: es una cita con fecha. Lo vio  |
| 214 | 112 | `docs/reglas/procesadores.md` | 10-ago-2026. |
| 215 | 113 | `docs/reglas/procesadores.md` | - ⚠️ **Y el panel de Custom Analytics va DÍAS POR DETRÁS.** El 10-ago-2026 avi |
| 216 | 114 | `docs/reglas/procesadores.md` | disponibles hasta el 1/8/2026"*: **nueve días**. Consecuencias que no se puede |
| 217 | 115 | `docs/reglas/procesadores.md` | dos exportaciones de días distintos pueden traer **cifras idénticas** (el cort |
| 218 | 116 | `docs/reglas/procesadores.md` | movió — no es un fichero duplicado), y 'leido_at' es **cuándo se exportó, no l |
| 219 | 117 | `docs/reglas/procesadores.md` | los datos**. Restar dos lecturas mide **la cadencia de Amazon**, no lo que pas |
| 220 | 118 | `docs/reglas/procesadores.md` | mercado entre esas dos fechas: vale para tendencia y para comparar ASIN, no pa |
| 221 | 119 | `docs/reglas/procesadores.md` | *"en agosto se vendieron X"*. |
| 222 | 120 | `docs/reglas/procesadores.md` | - **La DESPENSA COMÚN:** 'crudo' guarda todas las columnas aunque hoy no se us |
| 223 | 121 | `docs/reglas/procesadores.md` | 'sales-rank' llevaba semanas descargándose sin mirarse — y resultó ser el dete |
| 224 | 122 | `docs/reglas/procesadores.md` | - 🔴 **Los CSV de Keepa en Storage ('informes/keepa_escaparate/') NO SE BORRAN  |
| 225 | 123 | `docs/reglas/procesadores.md` | ser fichero temporal el día que 'keepa_escaparate_hist' dejó de guardar 'crudo |
| 226 | 124 | `docs/reglas/procesadores.md` | pasaron a ser **el archivo histórico permanente**. Ese 'crudo' era copia byte  |
| 227 | 125 | `docs/reglas/procesadores.md` | sacó de la base porque estaba duplicado con 25× menos margen (BD 500 MB vs Sto |
| 228 | 126 | `docs/reglas/procesadores.md` | 512 claves que solo viven ahí siguen siendo munición del trackeador. **El resc |
| 229 | 127 | `docs/reglas/procesadores.md` | hace por 'keepa_escaparate_hist.fichero' → 'informes/keepa_escaparate/<fichero |
| 230 | 128 | `docs/reglas/procesadores.md` | para "hacer sitio" es borrar el histórico sin vuelta atrás. Es la CONTRAPARTID |
| 231 | 129 | `docs/reglas/procesadores.md` | crudo' (migración '2026-07-29_keepa_hist_drop_crudo.sql'): el DROP solo fue se |
| 232 | 130 | `docs/reglas/procesadores.md` | conserva. La misma regla aplica a cualquier 'crudo' que en el futuro se mueva  |
| 234 | 7 | `docs/reglas/trampas-medidas.md` | ### Trampas medidas (no re-descubrir) |
| 235 | 8 | `docs/reglas/trampas-medidas.md` | - **Filas fantasma: RESUELTO (PR #33, 20-jul-2026).** Antes las tablas-foto se |
| 236 | 9 | `docs/reglas/trampas-medidas.md` | **sin DELETE**: si el informe encogía (salud_fba: 195→188 SKU en dos días), qu |
| 237 | 10 | `docs/reglas/trampas-medidas.md` | conviviendo con las nuevas. **Ya no. La Foto tira la hoja vieja** (§1.6). Las  |
| 238 | 11 | `docs/reglas/trampas-medidas.md` | heredan el patrón de 'foto_comun.py': lo que no viene en el fichero se BORRA,  |
| 239 | 12 | `docs/reglas/trampas-medidas.md` | anti-encogimiento (<50% de las filas previas → ABORTA) **antes** del borrado,  |
| 240 | 13 | `docs/reglas/trampas-medidas.md` | la misma transacción. |
| 241 | 14 | `docs/reglas/trampas-medidas.md` | ✅ **El ACUERDO de "no se lanza salud_fba en 'aplicar'" queda LEVANTADO.** La d |
| 242 | 15 | `docs/reglas/trampas-medidas.md` | esperaba ya está tomada: se lanza como cualquier otro. |
| 243 | 16 | `docs/reglas/trampas-medidas.md` | ⚠️ Lo que sí sigue mereciendo aviso: **la PRIMERA pasada 'produccion'+'aplicar |
| 244 | 17 | `docs/reglas/trampas-medidas.md` | dará de baja los fantasmas acumulados**. Es lo que se busca, pero mira las baj |
| 245 | 18 | `docs/reglas/trampas-medidas.md` | ensayo antes de aplicar. |
| 246 | 19 | `docs/reglas/trampas-medidas.md` | El ledger no tiene este problema: es Película, no Foto. |
| 247 | 20 | `docs/reglas/trampas-medidas.md` | - **Escritura masiva: SIEMPRE por lotes ('execute_values'), JAMÁS un 'cur.exec |
| 248 | 21 | `docs/reglas/trampas-medidas.md` | (PRs #65-#68 y #70, 29-jul-2026).** El runner de Actions está en EEUU y Supaba |
| 249 | 22 | `docs/reglas/trampas-medidas.md` | (Irlanda): cada 'cur.execute()' es un viaje transatlántico de **~90 ms**. Un |
| 250 | 23 | `docs/reglas/trampas-medidas.md` | 'for fila in filas: cur.execute(...)' de 3.806 filas = **5 m 48 s esperando a  |
| 251 | 24 | `docs/reglas/trampas-medidas.md` | medido en el run #14); el mismo volcado con 'psycopg2.extras.execute_values' b |
| 252 | 25 | `docs/reglas/trampas-medidas.md` | ventana de locks sobre la tabla de Elena de ~6 min a segundos. Los cinco que i |
| 253 | 26 | `docs/reglas/trampas-medidas.md` | entonces (paneu, internacional, salud_fba, all_listings, keepa) se pasaron a l |
| 254 | 27 | `docs/reglas/trampas-medidas.md` | VOLCADO DE FICHERO va por lotes** (medido el 28-ago recorriendo el árbol, no e |
| 255 | 28 | `docs/reglas/trampas-medidas.md` | ya no está en esa lista: su procesador se jubiló el 23-ago. El patrón está cal |
| 256 | 29 | `docs/reglas/trampas-medidas.md` | 'procesador_ledger.py', que nació así. **Si mañana nace un procesador nuevo, n |
| 257 | 30 | `docs/reglas/trampas-medidas.md` | 📌 Dos cosas quedan fuera del patrón, y conviene saber cuál es cuál: |
| 258 | 31 | `docs/reglas/trampas-medidas.md` | - 'procesador_canal_amazon_es.py' **no es una excepción, es mejor**: escribe c |
| 259 | 32 | `docs/reglas/trampas-medidas.md` | 'INSERT … SELECT FROM v_canal_amazon_es', o sea que las filas nunca salen de l |
| 260 | 33 | `docs/reglas/trampas-medidas.md` | viajes. Si un día alguien «lo arregla» pasándolo a 'execute_values', lo **empe |
| 261 | 34 | `docs/reglas/trampas-medidas.md` | - ⚠️ **La curación de SKU de 'all_listings' SÍ sigue fila a fila**: un 'cur.ex |
| 262 | 35 | `docs/reglas/trampas-medidas.md` | sobre 'productos' por cada ficha curable, dentro de un 'for'. Es exactamente e |
| 263 | 36 | `docs/reglas/trampas-medidas.md` | apartado prohíbe. Hoy no duele porque son pocas fichas, pero **paga los ~90 ms |
| 264 | 37 | `docs/reglas/trampas-medidas.md` | todo lo demás**, así que si un día crece, ahí está. *(Se encontró el 28-ago al |
| 265 | 38 | `docs/reglas/trampas-medidas.md` | frase de este mismo párrafo que decía «ya no queda ninguno». No la había: qued |
| 266 | 39 | `docs/reglas/trampas-medidas.md` | 🔴 **La trampa del lote:** con 'execute_values' todas las filas van en UN coman |
| 267 | 40 | `docs/reglas/trampas-medidas.md` | la misma clave del 'ON CONFLICT' abortan con 'ON CONFLICT DO UPDATE command ca |
| 268 | 41 | `docs/reglas/trampas-medidas.md` | second time' (fila a fila no saltaba: la segunda pisaba a la primera en silenc |
| 269 | 42 | `docs/reglas/trampas-medidas.md` | duplicado se decide POR PROCESADOR y NO se copia entre ellos: |
| 270 | 43 | `docs/reglas/trampas-medidas.md` | - **Duplicado = "la última gana"** (paneu, all_listings: el informe puede repe |
| 271 | 44 | `docs/reglas/trampas-medidas.md` | legítimo) → **deduplicar en Python** por la clave del 'ON CONFLICT' antes del  |
| 272 | 45 | `docs/reglas/trampas-medidas.md` | la última; y si descartas algo, GRÍTALO al log (fila a fila era invisible). |
| 273 | 46 | `docs/reglas/trampas-medidas.md` | - **Duplicado = informe CORRUPTO** con una guarda que ya ABORTA por él (salud_ |
| 274 | 47 | `docs/reglas/trampas-medidas.md` | *"el procesador NO elige"*) → **NO deduplicar**: dedup enmascararía justo lo q |
| 275 | 48 | `docs/reglas/trampas-medidas.md` | gritar. Y dedup por la clave REAL de cada tabla, nunca una "colapsada" que dep |
| 276 | 49 | `docs/reglas/trampas-medidas.md` | (internacional: el histórico se deduplica por '(sku, country, fecha_foto)', no |
| 277 | 50 | `docs/reglas/trampas-medidas.md` | 🔒 **Prueba de que el cambio no movió ni un dato:** mismo fichero, viejo('main' |
| 278 | 51 | `docs/reglas/trampas-medidas.md` | CONTENIDO de la tabla —'md5(string_agg((to_jsonb(t) - '<col now()>')::text, '\ |
| 279 | 52 | `docs/reglas/trampas-medidas.md` | excluyendo la columna 'now()' ('procesado_en'/'procesado_at'/'capturado_en', c |
| 280 | 53 | `docs/reglas/trampas-medidas.md` | idéntico. El diff de logs solo prueba los recuentos, NO que cada columna caiga |
| 281 | 54 | `docs/reglas/trampas-medidas.md` | riesgo real al pasar a tuplas en 'execute_values'). |
| 282 | 55 | `docs/reglas/trampas-medidas.md` | - **Dos fórmulas de stock que NO se unifican.** Son asientos distintos y ningu |
| 283 | 56 | `docs/reglas/trampas-medidas.md` | - **La columna de Amazon** ('Inventory Supply at FBA', en salud_fba) '= availa |
| 284 | 57 | `docs/reglas/trampas-medidas.md` | inbound-quantity', **SIN 'reserved'**. Verificado fila a fila; lo comprueba la |
| 285 | 58 | `docs/reglas/trampas-medidas.md` | aritmética interna del informe — **no es el stock de Moloka**. |
| 286 | 59 | `docs/reglas/trampas-medidas.md` | - **El stock de Moloka** (v1, 'moloka_actualizar_nube.py') '= available + rese |
| 287 | 60 | `docs/reglas/trampas-medidas.md` | **'fc-transfer' DENTRO de 'reserved'** e **'inbound' aparte** (está de camino) |
| 288 | 61 | `docs/reglas/trampas-medidas.md` | propósito la columna de Amazon: "inflaba el stock". |
| 289 | 62 | `docs/reglas/trampas-medidas.md` | 🔴 **'fc-transfer' cambia de bando entre las dos.** Llevar el "SIN 'reserved'"  |
| 290 | 63 | `docs/reglas/trampas-medidas.md` | borra el FC Transfer del stock — el error exacto contra el que el v1 avisa por |
| 291 | 64 | `docs/reglas/trampas-medidas.md` | - ⚠️ **'productos.unidades_compradas' cuenta unidades FÍSICAS, no facturadas:  |
| 292 | 65 | `docs/reglas/trampas-medidas.md` | "Compradas" suena a lo que dice el papel y no lo es. Con los packs se ve a la  |
| 293 | 66 | `docs/reglas/trampas-medidas.md` | 400 paquetes facturados que son 100 unidades físicas deja 'unidades_compradas  |
| 294 | 67 | `docs/reglas/trampas-medidas.md` | **Está BIEN así y no se cambia.** Su único uso real es elegir la ficha princip |
| 295 | 68 | `docs/reglas/trampas-medidas.md` | duplicados (*"Principal: la que tiene mas unidades_compradas historicas"*, 'in |
| 296 | 69 | `docs/reglas/trampas-medidas.md` | y ahí las físicas son lo correcto: contando facturadas, la ficha de packs gana |
| 297 | 70 | `docs/reglas/trampas-medidas.md` | **No entra en costes ni en rentabilidad**, así que no hay riesgo contable — so |
| 298 | 71 | `docs/reglas/trampas-medidas.md` | miente. Medido el 30-jul-2026. |
| 299 | 72 | `docs/reglas/trampas-medidas.md` | - 🔴 **Al comparar un número del FICHERO contra uno de la BASE, iguala los tipo |
| 300 | 73 | `docs/reglas/trampas-medidas.md` | 'psycopg2' devuelve los 'numeric' como **'Decimal' exacto**; el fichero da **' |
| 301 | 74 | `docs/reglas/trampas-medidas.md` | binario**. Y en Python '43.98 < Decimal('43.98')' es **'True'**, porque el flo |
| 302 | 75 | `docs/reglas/trampas-medidas.md` | en realidad 43,9799999… Medido el 10-ago-2026 con nueve importes reales de un  |
| 303 | 76 | `docs/reglas/trampas-medidas.md` | **siete daban "bajada" siendo idénticos.** |
| 304 | 77 | `docs/reglas/trampas-medidas.md` | Una guarda de no-retroceso escrita sin igualar tipos **aborta cargas buenas y  |
| 305 | 78 | `docs/reglas/trampas-medidas.md` | error**: dice que el contador retrocedió. Es peor que no tenerla, porque mient |
| 306 | 79 | `docs/reglas/trampas-medidas.md` | autoridad. Se arregla con un 'float()' en los dos lados. |
| 307 | 80 | `docs/reglas/trampas-medidas.md` | ⚠️ **Hoy solo hay UN procesador que cruce esos dos mundos** ('procesador_custo |
| 308 | 81 | `docs/reglas/trampas-medidas.md` | y no es suerte: **es que el patrón es nuevo.** Los demás son FOTO o PELÍCULA — |
| 309 | 82 | `docs/reglas/trampas-medidas.md` | vieja o apilan—, así que ninguno necesita saber qué había antes. La comparació |
| 310 | 83 | `docs/reglas/trampas-medidas.md` | fichero-contra-base nació con el **modelo contador**; el día que otro informe  |
| 311 | 84 | `docs/reglas/trampas-medidas.md` | tenga su cañería, hereda la trampa. |
| 312 | 85 | `docs/reglas/trampas-medidas.md` | 🔒 Y la forma de dar por bueno el arreglo, que vale para cualquier bug de compa |
| 313 | 86 | `docs/reglas/trampas-medidas.md` | **las dos mitades**. Que el falso positivo desaparezca *y* que el verdadero si |
| 314 | 87 | `docs/reglas/trampas-medidas.md` | con el recuento cuadrando al dígito contra la otra vía que mide lo mismo. Aquí |
| 315 | 88 | `docs/reglas/trampas-medidas.md` | bajadas del fichero malo, idénticas a las que ya contaba el inventario, y 0 so |
| 316 | 89 | `docs/reglas/trampas-medidas.md` | - **'FNSKU = ASIN' ⇒ listing commingled** (pozo común por EAN entre vendedores |
| 317 | 90 | `docs/reglas/trampas-medidas.md` | ('X0…') ⇒ etiquetado. Explica stock que aparece en países donde no enviaste na |
| 318 | 91 | `docs/reglas/trampas-medidas.md` | - **El "país" del INTERNACIONAL puede ser de PROGRAMA, no físico** (stock en P |
| 319 | 92 | `docs/reglas/trampas-medidas.md` | Y CZ/SK no existen para ese informe, pero el ledger demuestra stock físico all |
| 320 | 93 | `docs/reglas/trampas-medidas.md` | - **Dominios de Keepa: 3=DE · 4=FR · 8=IT · 9=ES** (10 es India). Ojo con el 8 |
| 321 | 94 | `docs/reglas/trampas-medidas.md` | *(Aquí vivió un aviso de "bug latente en 'DOMINIO_NUM'" que se quedó mintiendo |
| 322 | 95 | `docs/reglas/trampas-medidas.md` | después de estar arreglado — el mapa se corrigió el 20-jul-2026 en '007632c' y |
| 323 | 96 | `docs/reglas/trampas-medidas.md` | diciendo que estaba mal. Es el ejemplo de andar por casa de §3: **el estado vi |
| 324 | 97 | `docs/reglas/trampas-medidas.md` | en las notas**. Si dudas del mapa, míralo en el fichero; si lo cambias, borra  |
| 326 | 99 | `docs/reglas/trampas-medidas.md` | --- |
| 328 | 7 | `docs/reglas/tests-y-falsos-verdes.md` | ## 3. VALIDACIÓN: QUÉ CUENTA COMO PRUEBA |
| 330 | 55 | `CLAUDE.md` | 🔴 **PROHIBIDO TEORIZAR.** Si no lo puedes medir en esta respuesta, di **"no lo |
| 331 | 56 | `CLAUDE.md` | fichero o consulta lo contestaría. No inventes explicaciones plausibles. |
| 333 | 58 | `CLAUDE.md` | - **La verificación final es SQL contra la BD. NUNCA el log.** |
| 334 | 59 | `CLAUDE.md` | - **Compilar no es ejecutar.** 'py_compile' pasa un script que redefine un bui |
| 335 | 60 | `CLAUDE.md` | runtime. Ejecuta contra **el fichero real**. |
| 336 | 10 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **UN TEST VERDE SOLO CUENTA SI HAS VISTO SU NOMBRE EN LA SALIDA.** El «✅ T |
| 337 | 11 | `docs/reglas/tests-y-falsos-verdes.md` | **no demuestra que tu suite se haya ejecutado**: demuestra que no falló ningun |
| 338 | 12 | `docs/reglas/tests-y-falsos-verdes.md` | corrieron. Si el tuyo no está en la lista, no ha corrido — y el runner no tien |
| 339 | 13 | `docs/reglas/tests-y-falsos-verdes.md` | que falta. **Es el falso verde peor de todos: no es un test que falla, es un t |
| 340 | 14 | `docs/reglas/tests-y-falsos-verdes.md` | y encima te da la sensación contraria. |
| 341 | 15 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 10-ago-2026 en 'moloka-app-v2': un suite nuevo quedó con el 'import |
| 342 | 16 | `docs/reglas/tests-y-falsos-verdes.md` | entrada en el array 'SUITES' de 'tests/run.mjs'. 'npm test' dio «TODO OK» con  |
| 343 | 17 | `docs/reglas/tests-y-falsos-verdes.md` | ejecutar. Se cazó al ir a leer el suite por su nombre en la salida en vez de f |
| 344 | 18 | `docs/reglas/tests-y-falsos-verdes.md` | Regla práctica: después de añadir un suite, 'npm test \| grep "<su cabecera>"' |
| 345 | 19 | `docs/reglas/tests-y-falsos-verdes.md` | existe. Vale igual para cualquier runner en el que registrar el test sea un pa |
| 346 | 20 | `docs/reglas/tests-y-falsos-verdes.md` | escribirlo. |
| 347 | 21 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **ANTES DE CREAR RAMA, 'git fetch'.** Una rama nacida de un 'origin/main'  |
| 348 | 22 | `docs/reglas/tests-y-falsos-verdes.md` | sobre un bug **ya arreglado**, y los tests no lo cazan porque el arreglo simpl |
| 349 | 23 | `docs/reglas/tests-y-falsos-verdes.md` | no hay nada que se ponga rojo. Sales con todo en verde y devuelves el fallo a  |
| 350 | 24 | `docs/reglas/tests-y-falsos-verdes.md` | puerta de atrás, encima con la firma de haberlo verificado. |
| 351 | 25 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 10-ago-2026: la rama de las seis correcciones de pantalla se creó d |
| 352 | 26 | `docs/reglas/tests-y-falsos-verdes.md` | que no tenía el PR recién fusionado con el arreglo del doble conteo de la tira |
| 353 | 27 | `docs/reglas/tests-y-falsos-verdes.md` | descubrió por casualidad, buscando otra cosa —el suite que no aparecía por su  |
| 354 | 28 | `docs/reglas/tests-y-falsos-verdes.md` | arriba— y se integró antes de seguir.* |
| 355 | 29 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 Y de ahí, lo que hay que hacer cuando pasa: **integrar 'origin/main' EN CUAN |
| 356 | 30 | `docs/reglas/tests-y-falsos-verdes.md` | al final. Cuanto más tarde, más código escrito sobre la base equivocada. Ojo t |
| 357 | 31 | `docs/reglas/tests-y-falsos-verdes.md` | merge': fusiona en GitHub y **no actualiza tu 'origin/main' local** — hace fal |
| 358 | 32 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **HAY VARIAS SESIONES SOBRE ESTE REPO A LA VEZ, y el accidente típico se l |
| 359 | 33 | `docs/reglas/tests-y-falsos-verdes.md` | ajeno por delante.** El worktree que vas a crear puede tener el nombre ya cogi |
| 360 | 34 | `docs/reglas/tests-y-falsos-verdes.md` | sesión; entonces 'git worktree add' falla, y si lo encadenaste con '&&', **el  |
| 361 | 35 | `docs/reglas/tests-y-falsos-verdes.md` | ejecuta y todo lo que venga después corre en el repo principal** — que está en |
| 362 | 36 | `docs/reglas/tests-y-falsos-verdes.md` | OTRO. Un 'git add -A && git commit' ahí se lleva sus ficheros sin tocar dentro |
| 363 | 37 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 11-ago-2026: pasó exactamente eso, y el commit cayó en 'claude/buzo |
| 364 | 38 | `docs/reglas/tests-y-falsos-verdes.md` | Se salvó porque el 'push' falló solo (la rama no tenía remoto) y se deshizo co |
| 365 | 39 | `docs/reglas/tests-y-falsos-verdes.md` | --mixed HEAD~1', que quita el commit SIN tocar los ficheros — el '--hard' habr |
| 366 | 40 | `docs/reglas/tests-y-falsos-verdes.md` | trabajo de la otra sesión.* |
| 367 | 41 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 Las tres cosas que lo evitan, por orden de utilidad: |
| 368 | 42 | `docs/reglas/tests-y-falsos-verdes.md` | 1. **Nombre de worktree único por encargo** ('moloka-v2-<tema>'), y si 'add' f |
| 369 | 43 | `docs/reglas/tests-y-falsos-verdes.md` | no seguir con los comandos encadenados. |
| 370 | 44 | `docs/reglas/tests-y-falsos-verdes.md` | 2. **'git add <fichero>', no 'git add -A'**, cuando el cambio son uno o dos fi |
| 371 | 45 | `docs/reglas/tests-y-falsos-verdes.md` | único que habría hecho inofensivo el accidente. |
| 372 | 46 | `docs/reglas/tests-y-falsos-verdes.md` | 3. Antes de commitear en un sitio del que no vienes: 'git branch --show-curren |
| 373 | 47 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **EL CI EN VERDE NO PRUEBA QUE UNA FEATURE ESTÉ VIVA.** Prueba que compila |
| 374 | 48 | `docs/reglas/tests-y-falsos-verdes.md` | que hay escrito pasa; no que lo que escribiste llegue a ejecutarse. |
| 375 | 49 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 11-ago-2026: al fusionar dos ramas que tocaban la misma función, el |
| 376 | 50 | `docs/reglas/tests-y-falsos-verdes.md` | **dos 'return construirInventario(...)' seguidos**. El primero ganaba, el segu |
| 377 | 51 | `docs/reglas/tests-y-falsos-verdes.md` | código muerto, y con él se anulaba una feature entera —el envío de la buy box  |
| 378 | 52 | `docs/reglas/tests-y-falsos-verdes.md` | al builder—. TypeScript no dice nada de eso, el lint tampoco, y el CI salió ve |
| 379 | 53 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 **Toda feature nueva necesita al menos UN assert que falle si se desactiva.* |
| 380 | 54 | `docs/reglas/tests-y-falsos-verdes.md` | con que haya tests del cálculo: tiene que haber uno que compruebe que el dato  |
| 381 | 55 | `docs/reglas/tests-y-falsos-verdes.md` | Los que cazaron aquello fueron los del suite, que sí miran el resultado con el |
| 382 | 56 | `docs/reglas/tests-y-falsos-verdes.md` | puesto — el mismo día había 1.887 y por eso saltó a la primera. |
| 383 | 57 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Y el corolario, que es el que se olvida: **si desactivas la feature a mano  |
| 384 | 58 | `docs/reglas/tests-y-falsos-verdes.md` | sigue verde, el suite no la está probando.** Es la versión de «haz saltar las  |
| 385 | 59 | `docs/reglas/tests-y-falsos-verdes.md` | propósito» aplicada a las funcionalidades, no solo a las guardas. |
| 386 | 60 | `docs/reglas/tests-y-falsos-verdes.md` | 🔴 **Y NO BASTA CON QUE EL TEST PASE: HAY QUE ROMPER LA COSA A MANO Y VERLO PON |
| 387 | 61 | `docs/reglas/tests-y-falsos-verdes.md` | Las DOS direcciones, siempre, y la segunda es la que prueba algo — un test que |
| 388 | 62 | `docs/reglas/tests-y-falsos-verdes.md` | visto en verde no se ha probado, se ha ejecutado. |
| 389 | 63 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 11-ago-2026, y el ejemplo es el test que venía a cazar justo esto:  |
| 390 | 64 | `docs/reglas/tests-y-falsos-verdes.md` | un test para que ninguna alerta se quedara sin filtro en el Cockpit; pasó a la |
| 391 | 65 | `docs/reglas/tests-y-falsos-verdes.md` | Al comentar la línea '// tipo: 'BB_DISCREPA_FUENTES',' para verlo morir, **sig |
| 392 | 66 | `docs/reglas/tests-y-falsos-verdes.md` | verde**: buscaba el patrón sobre el fichero crudo y el regex casa igual dentro |
| 393 | 67 | `docs/reglas/tests-y-falsos-verdes.md` | comentario, así que daba por vivo el código comentado. El vicio que el test pe |
| 394 | 68 | `docs/reglas/tests-y-falsos-verdes.md` | estaba dentro del test.* |
| 395 | 69 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Ojo al patrón, porque se repite: **lo que se lee como texto (grep, regex, a |
| 396 | 70 | `docs/reglas/tests-y-falsos-verdes.md` | distingue código de comentario.** Si un test mira el fichero como cadena, quit |
| 397 | 71 | `docs/reglas/tests-y-falsos-verdes.md` | comentarios antes de mirar — o comprobará que algo está escrito, no que se eje |
| 398 | 72 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 Vale para todo, no sólo para tests: una guarda nueva se hace saltar, un avis |
| 399 | 73 | `docs/reglas/tests-y-falsos-verdes.md` | provoca, y una feature nueva se desactiva. Si al romperla no pasa nada, no est |
| 400 | 74 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **CUANDO UNA REGLA SE REPITE, DEJA DE ESCRIBIRSE Y SE CONVIERTE EN FUNCIÓN |
| 401 | 75 | `docs/reglas/tests-y-falsos-verdes.md` | Una regla escrita **se olvida en veinte minutos**; una regla convertida en her |
| 402 | 76 | `docs/reglas/tests-y-falsos-verdes.md` | aplica sola. |
| 403 | 77 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 12-ago-2026, y el caso es contra mí: por la mañana se escribió la r |
| 404 | 78 | `docs/reglas/tests-y-falsos-verdes.md` | que se lee como texto no distingue código de comentario», se le puso un test a |
| 405 | 79 | `docs/reglas/tests-y-falsos-verdes.md` | se corrigió una atribución por ella. **Veinte minutos después**, al escribir u |
| 406 | 80 | `docs/reglas/tests-y-falsos-verdes.md` | en SQL a mano, el mismo fallo: un regex casó la palabra «ventas» dentro de la  |
| 407 | 81 | `docs/reglas/tests-y-falsos-verdes.md` | española de un 'comment on column' y clasificó la tabla como creada por el con |
| 408 | 82 | `docs/reglas/tests-y-falsos-verdes.md` | La regla estaba escrita, probada y aplicada en Python — y no protegió al SQL d |
| 409 | 83 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 **La forma de saber que toca:** si al escribir algo piensas «esto ya lo sé», |
| 410 | 84 | `docs/reglas/tests-y-falsos-verdes.md` | segunda vez. La tercera no la vas a ver venir. |
| 411 | 85 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Y el corolario que evita el daño peor: **una sola implementación por regla. |
| 412 | 86 | `docs/reglas/tests-y-falsos-verdes.md` | parseos distintos que miden lo mismo son dos verdades esperando a discrepar; y |
| 413 | 87 | `docs/reglas/tests-y-falsos-verdes.md` | encuentra una trampa, se arregla en un sitio y queda arreglada en todos. |
| 414 | 88 | `docs/reglas/tests-y-falsos-verdes.md` | 🔬 Sin nombrarlo, este movimiento ya se hizo cuatro veces: 'v_salud_escaner' (l |
| 415 | 89 | `docs/reglas/tests-y-falsos-verdes.md` | del 'presente=true' como objeto, no como nota), el centinela de despliegue (la |
| 416 | 90 | `docs/reglas/tests-y-falsos-verdes.md` | merge, en el repo y no en la memoria de alguien), el canario RLS (el checklist |
| 417 | 91 | `docs/reglas/tests-y-falsos-verdes.md` | fichero) y 'sin_comentarios()' (la regla del comentario, como código con test) |
| 418 | 92 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **LA COMPROBACIÓN QUE NO PUEDE FALLAR: el error más repetido, y siempre sa |
| 419 | 93 | `docs/reglas/tests-y-falsos-verdes.md` | Antes de fiarte de una comprobación, pregúntate **qué la pondría roja**. Si no |
| 420 | 94 | `docs/reglas/tests-y-falsos-verdes.md` | respuesta —si el resultado sale igual mida lo que mida— no comprueba nada, y e |
| 421 | 95 | `docs/reglas/tests-y-falsos-verdes.md` | tranquiliza. Es el peor de los fallos: no da error, da permiso. |
| 422 | 96 | `docs/reglas/tests-y-falsos-verdes.md` | *Tres veces en dos días, con tres caras distintas y la misma forma:* |
| 423 | 97 | `docs/reglas/tests-y-falsos-verdes.md` | \| \| la comprobación \| por qué no podía fallar \| |
| 424 | 98 | `docs/reglas/tests-y-falsos-verdes.md` | \|---\|---\|---\| |
| 425 | 99 | `docs/reglas/tests-y-falsos-verdes.md` | \| 1 \| El pin del 'search_path': longitud **con** y **sin** pin en el mismo ' |
| 426 | 100 | `docs/reglas/tests-y-falsos-verdes.md` | \| 2 \| Testigo de entorno: 'current_database()' y 'count(*) from productos' \ |
| 427 | 101 | `docs/reglas/tests-y-falsos-verdes.md` | \| 3 \| La huella 'es_case' para saber si 'v_escaner_ultimo' estaba al día \|  |
| 428 | 102 | `docs/reglas/tests-y-falsos-verdes.md` | \| 4 \| 'bash -n' sobre el script extraído de un '.yml', para validar su sinta |
| 429 | 103 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 **La forma común: la entrada no puede producir un resultado distinto** — por |
| 430 | 104 | `docs/reglas/tests-y-falsos-verdes.md` | comparan dos cosas iguales por construcción (1, 2, 3) o porque directamente ** |
| 431 | 105 | `docs/reglas/tests-y-falsos-verdes.md` | entrada** (4). ⚠️ De ahí el reflejo que hay que coger: **antes de creerse un O |
| 432 | 106 | `docs/reglas/tests-y-falsos-verdes.md` | mirar que había algo que comprobar.** Un recuento a cero, un fichero vacío o u |
| 433 | 107 | `docs/reglas/tests-y-falsos-verdes.md` | lista sin filas convierten cualquier validación en un trámite. |
| 434 | 108 | `docs/reglas/tests-y-falsos-verdes.md` | Dicho del otro modo: se comparan dos cosas que son iguales por construcción. D |
| 435 | 109 | `docs/reglas/tests-y-falsos-verdes.md` | de la misma transacción, dos copias de la misma base, dos versiones que compar |
| 436 | 110 | `docs/reglas/tests-y-falsos-verdes.md` | texto. El resultado no depende del estado que se quería medir. |
| 437 | 111 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Y el corolario para el caso 3, que aplica a toda huella o marcador de versi |
| 438 | 112 | `docs/reglas/tests-y-falsos-verdes.md` | elige contra la versión VIEJA, no contra la nueva.** Que aparezca en la actual |
| 439 | 113 | `docs/reglas/tests-y-falsos-verdes.md` | nada; hay que comprobar que **NO** aparece en la anterior. La huella va sobre  |
| 440 | 114 | `docs/reglas/tests-y-falsos-verdes.md` | **cambió** —la cláusula, la condición, la firma—, nunca sobre un nombre que la |
| 441 | 115 | `docs/reglas/tests-y-falsos-verdes.md` | versiones mencionan. |
| 442 | 116 | `docs/reglas/tests-y-falsos-verdes.md` | 🔬 Las tres las destapó **medir con otra vía**, no la propia comprobación: el p |
| 443 | 117 | `docs/reglas/tests-y-falsos-verdes.md` | el número no cuadraba con uno ya conocido; el testigo, porque se midieron las  |
| 444 | 118 | `docs/reglas/tests-y-falsos-verdes.md` | la vez antes de escribirlo; y la huella, porque el cruce de 'md5' entre entorn |
| 445 | 119 | `docs/reglas/tests-y-falsos-verdes.md` | diferencia que la huella daba por buena. |
| 446 | 120 | `docs/reglas/tests-y-falsos-verdes.md` | 🔴 **LA FORMA MÁS FRECUENTE, MEDIDA CINCO VECES EN UN SOLO DÍA: LA COMPROBACIÓN |
| 447 | 121 | `docs/reglas/tests-y-falsos-verdes.md` | MIRA LO QUE NO CAMBIA.** Un assert que busca un texto presente en las DOS vers |
| 448 | 122 | `docs/reglas/tests-y-falsos-verdes.md` | prefijo de una firma, el nombre de una función, una columna del 'SELECT'— sale |
| 449 | 123 | `docs/reglas/tests-y-falsos-verdes.md` | hagas lo que hagas. 🔑 **Se ancla contra lo que NO debe aparecer**, que es la ú |
| 450 | 124 | `docs/reglas/tests-y-falsos-verdes.md` | que se mueve: no «¿está el parámetro?» sino «¿tiene default?»; no «¿existe la  |
| 451 | 125 | `docs/reglas/tests-y-falsos-verdes.md` | sino «¿sigue la excepción que la tapaba?». |
| 452 | 126 | `docs/reglas/tests-y-falsos-verdes.md` | *Los cinco del 20-ago-2026, todos cazados por la MISMA maniobra —romper la cos |
| 453 | 127 | `docs/reglas/tests-y-falsos-verdes.md` | ver que no saltaba nada—:* |
| 454 | 128 | `docs/reglas/tests-y-falsos-verdes.md` | \| \| la comprobación \| por qué no podía fallar \| |
| 455 | 129 | `docs/reglas/tests-y-falsos-verdes.md` | \|---\|---\|---\| |
| 456 | 130 | `docs/reglas/tests-y-falsos-verdes.md` | \| 1 \| el test de la paginación \| los asserts usaban el fixture del propio t |
| 457 | 131 | `docs/reglas/tests-y-falsos-verdes.md` | \| 2 \| el test de la velocidad efectiva \| el servidor de mentira nunca llega |
| 458 | 132 | `docs/reglas/tests-y-falsos-verdes.md` | \| 3 \| el test del criterio del negro \| el caso real no discriminaba: sus mo |
| 459 | 133 | `docs/reglas/tests-y-falsos-verdes.md` | \| 4 \| 'isd' sin default \| el regex casaba el PREFIJO de la firma, así que d |
| 460 | 134 | `docs/reglas/tests-y-falsos-verdes.md` | \| 5 \| el assert del ISD en el escáner \| sumaba la tarifa FBA **a mano** en  |
| 461 | 135 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Los cinco eran tests **nuevos, escritos ese día, para cazar un bug recién m |
| 462 | 136 | `docs/reglas/tests-y-falsos-verdes.md` | ninguno lo habría cazado. Escribir el test no es la prueba; verlo rojo sí. |
| 464 | 138 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ **Y la cara B, que es la misma enfermedad: la que SIEMPRE está roja.** Un a |
| 465 | 139 | `docs/reglas/tests-y-falsos-verdes.md` | salta en cada ejecución tampoco informa — se aprende a ignorarlo, y el día que |
| 466 | 140 | `docs/reglas/tests-y-falsos-verdes.md` | algo de verdad ya nadie lo lee. |
| 467 | 141 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 12-ago-2026: el censo de 'sql/canario_rls.sql' llevaba **20** tabla |
| 468 | 142 | `docs/reglas/tests-y-falsos-verdes.md` | porque se armó con «las 20 que tienen datos dentro», dejando fuera 'web_format |
| 469 | 143 | `docs/reglas/tests-y-falsos-verdes.md` | estar vacía. Tapadas hay **21**. Con ella fuera, el canario reportaba 'web_for |
| 470 | 144 | `docs/reglas/tests-y-falsos-verdes.md` | **🔴 TAPADA NUEVA** en cada pasada, para siempre.* |
| 471 | 145 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 **Estar vacía hoy no es motivo para excluir nada de un censo.** «Con datos»  |
| 472 | 146 | `docs/reglas/tests-y-falsos-verdes.md` | son dos estadísticas distintas: mezclarlas mete un falso positivo permanente.  |
| 473 | 147 | `docs/reglas/tests-y-falsos-verdes.md` | de filas ya lo da la consulta, columna a columna. |
| 474 | 148 | `docs/reglas/tests-y-falsos-verdes.md` | ⇒ **«Las dos direcciones» son DOS, y la segunda es la que se olvida:** |
| 475 | 149 | `docs/reglas/tests-y-falsos-verdes.md` | \| \| qué se prueba \| cómo \| |
| 476 | 150 | `docs/reglas/tests-y-falsos-verdes.md` | \|---\|---\|---\| |
| 477 | 151 | `docs/reglas/tests-y-falsos-verdes.md` | \| 1 \| **que se ponga ROJA cuando toca** \| se rompe la cosa a mano y tiene q |
| 478 | 152 | `docs/reglas/tests-y-falsos-verdes.md` | \| 2 \| **que esté CALLADA cuando no toca** \| se corre con **todo en orden**  |
| 479 | 153 | `docs/reglas/tests-y-falsos-verdes.md` | La 1 la hacemos casi siempre; **la 2 se nos escapó** — y es la que llevaba al  |
| 480 | 154 | `docs/reglas/tests-y-falsos-verdes.md` | gritando desde el 11-ago. Las dos cuestan una ejecución cada una, y sin las do |
| 481 | 155 | `docs/reglas/tests-y-falsos-verdes.md` | sabe si la alarma mide algo o sólo hace ruido en una dirección fija. |
| 482 | 156 | `docs/reglas/tests-y-falsos-verdes.md` | - 🔴 **UNA VISTA QUE NO PUEDE VER SU FUENTE DEBE CONFESARLO, NO RELLENAR CON UN |
| 483 | 157 | `docs/reglas/tests-y-falsos-verdes.md` | El caso general de «0 filas por RLS ≠ 0 filas porque no hay»: si una vista se  |
| 484 | 158 | `docs/reglas/tests-y-falsos-verdes.md` | una tabla que puede estar tapada, tiene que **distinguir los dos ceros dentro  |
| 485 | 159 | `docs/reglas/tests-y-falsos-verdes.md` | dato** —columna a 'null' y un veredicto que diga *«no puedo leerla»*— en vez d |
| 486 | 160 | `docs/reglas/tests-y-falsos-verdes.md` | el valor que sale por defecto. |
| 487 | 161 | `docs/reglas/tests-y-falsos-verdes.md` | *Medido el 11-ago-2026: 'v_salud_escaner' cruza con 'reglas_director' para dec |
| 488 | 162 | `docs/reglas/tests-y-falsos-verdes.md` | proveedor tiene director. Esa tabla es una de las 20 con RLS y cero políticas, |
| 489 | 163 | `docs/reglas/tests-y-falsos-verdes.md` | con 'security_invoker' el join no devolvía nada y la vista decía «sin director |
| 490 | 164 | `docs/reglas/tests-y-falsos-verdes.md` | CUATRO que sí lo tienen. La vista construida para evitar una trampa se metió d |
| 491 | 165 | `docs/reglas/tests-y-falsos-verdes.md` | 🔑 Y de ahí lo que hay que hacer: la comprobación va **en el dato, no en un scr |
| 492 | 166 | `docs/reglas/tests-y-falsos-verdes.md` | aparte**. Un canario externo hay que acordarse de mirarlo; una columna a 'null |
| 493 | 167 | `docs/reglas/tests-y-falsos-verdes.md` | motivo la ve quien consulta, cuando consulta, sin saber nada de esto. |
| 494 | 168 | `docs/reglas/tests-y-falsos-verdes.md` | ⚠️ Corolario, porque es el que se olvida: **las 20 tablas tapadas contaminan t |
| 495 | 169 | `docs/reglas/tests-y-falsos-verdes.md` | se apoye en ellas.** Antes de cruzar con una tabla, mírala en 'sql/canario_rls |
| 496 | 61 | `CLAUDE.md` | - **Los datos sintéticos no prueban nada.** Una vista se prueba con la tabla * |
| 497 | 62 | `CLAUDE.md` | - **Escribe los números esperados ANTES de correr.** Si no salen, di lo que sa |
| 498 | 63 | `CLAUDE.md` | expectativa al resultado. |
| 499 | 64 | `CLAUDE.md` | - **Haz saltar las guardas a propósito** antes de dar un procesador por bueno. |
| 500 | 7 | `docs/reglas/guardas-y-ensayos.md` | - 🔴 **UNA GUARDA COMPARA INVARIANTES, NO CIFRAS ABSOLUTAS** — y con más motivo |
| 501 | 8 | `docs/reglas/guardas-y-ensayos.md` | el backup no copia. 'backup-bd.yml' vuelca con '--schema=public', así que 'sto |
| 502 | 9 | `docs/reglas/guardas-y-ensayos.md` | todo lo demás **no están en la copia** y 'restaurar-staging.yml' no los repone |
| 503 | 10 | `docs/reglas/guardas-y-ensayos.md` | fijo sobre lo que no se copia da **rojo en staging por el alcance del backup,  |
| 504 | 11 | `docs/reglas/guardas-y-ensayos.md` | migración**: un falso rojo esperando su día. |
| 505 | 12 | `docs/reglas/guardas-y-ensayos.md` | *Medido el 10-ago-2026 en '2026-08-10_buzon_custom_analytics.sql': el encargo  |
| 506 | 13 | `docs/reglas/guardas-y-ensayos.md` | 'n_politicas <> 4' sobre 'storage.objects'. Se cambió a guardar el recuento AN |
| 507 | 14 | `docs/reglas/guardas-y-ensayos.md` | DESPUÉS, porque el invariante real de un 'CREATE OR REPLACE' es "no se llevó n |
| 508 | 15 | `docs/reglas/guardas-y-ensayos.md` | por delante", y eso es cierto valgan 4 o valga otra cosa.* |
| 509 | 16 | `docs/reglas/guardas-y-ensayos.md` | 🔑 **La regla de la que esto es un caso: una comprobación que puede saltar por  |
| 510 | 17 | `docs/reglas/guardas-y-ensayos.md` | distinta de la que dice medir no es una guarda, es ruido futuro.** Se deja de  |
| 511 | 18 | `docs/reglas/guardas-y-ensayos.md` | semanas — es el 'ON_ERROR_STOP=0' por el otro extremo. El 10-ago-2026 el mismo |
| 512 | 19 | `docs/reglas/guardas-y-ensayos.md` | **tres veces por caminos que no se parecen en nada**: los tipos ('Decimal' con |
| 513 | 20 | `docs/reglas/guardas-y-ensayos.md` | un 'LIKE' más ancho de lo que decía medir, y este número fijo de políticas. An |
| 514 | 21 | `docs/reglas/guardas-y-ensayos.md` | guarda por buena, pregúntale: *¿puedes ponerte roja por el entorno, por el tip |
| 515 | 22 | `docs/reglas/guardas-y-ensayos.md` | el alcance de una copia?* Si la respuesta es sí, todavía no es una guarda. |
| 516 | 23 | `docs/reglas/guardas-y-ensayos.md` | - 🔴 **UN ENSAYO SOBRE UN ESTADO QUE YA ES EL DE DESTINO NO PRUEBA NADA.** Sale |
| 517 | 24 | `docs/reglas/guardas-y-ensayos.md` | parece una verificación y no lo es: solo dice que el destino ya estaba como se |
| 518 | 25 | `docs/reglas/guardas-y-ensayos.md` | *Caso real del 10-ago-2026, y es mío: la migración de los comentarios de 'dema |
| 519 | 26 | `docs/reglas/guardas-y-ensayos.md` | probó primero "en humo" escribiéndola a mano en staging para ver si el SQL par |
| 520 | 27 | `docs/reglas/guardas-y-ensayos.md` | iba a correr el 'aplicar' encima — sobre unos comentarios que ya eran los nuev |
| 521 | 28 | `docs/reglas/guardas-y-ensayos.md` | dado verde verificando algo que ya era cierto antes de empezar. Se salvó devol |
| 522 | 29 | `docs/reglas/guardas-y-ensayos.md` | staging al texto viejo ANTES del ensayo, y entonces sí midió algo.* |
| 523 | 30 | `docs/reglas/guardas-y-ensayos.md` | **Antes de fiarte de un ensayo, mira en qué estado está el destino.** Aplica a |
| 524 | 31 | `docs/reglas/guardas-y-ensayos.md` | idempotente: 'CREATE OR REPLACE', 'IF NOT EXISTS', 'COMMENT ON', un 'setval' q |
| 525 | 32 | `docs/reglas/guardas-y-ensayos.md` | bien, un upsert que no cambia una fila. Y es hermano del simulacro de restaura |
| 526 | 33 | `docs/reglas/guardas-y-ensayos.md` | copia en la que se confía y que nadie ha probado **contra un estado distinto** |
| 527 | 34 | `docs/reglas/guardas-y-ensayos.md` | probada. |
| 528 | 35 | `docs/reglas/guardas-y-ensayos.md` | 📌 **PENDIENTE — convertirlo en guarda, que es mejor que en regla.** 'aplicar-m |
| 529 | 36 | `docs/reglas/guardas-y-ensayos.md` | puede detectarlo solo: si en modo 'ensayo' la migración no cambia NADA —cero f |
| 530 | 37 | `docs/reglas/guardas-y-ensayos.md` | afectadas, cero objetos tocados— que lo GRITE (*"este ensayo no ha cambiado na |
| 531 | 38 | `docs/reglas/guardas-y-ensayos.md` | migración es un no-op o el destino ya estaba en el estado final, y en los dos  |
| 532 | 39 | `docs/reglas/guardas-y-ensayos.md` | NO prueba que funcione"*). **Sin abortar**: hay migraciones legítimamente idem |
| 533 | 40 | `docs/reglas/guardas-y-ensayos.md` | se relanzan a propósito. Pero que un verde mudo no pueda hacerse pasar por una |
| 534 | 41 | `docs/reglas/guardas-y-ensayos.md` | verificación. Va **detrás** del registro de migraciones de §4. |
| 535 | 65 | `CLAUDE.md` | - **"Lo ha revisado un agente" NO es prueba.** Un revisor lee código, no lo ej |
| 536 | 7 | `docs/reglas/censos-y-catalogos.md` | - 🔴 **LAS OPCIONES DE UN OBJETO SE LEEN POR OPCIÓN, NUNCA CON UN 'like' SOBRE  |
| 537 | 8 | `docs/reglas/censos-y-catalogos.md` | Postgres guarda en 'reloptions' **literalmente lo que se escribió**, y acepta  |
| 538 | 9 | `docs/reglas/censos-y-catalogos.md` | 'security_invoker=true' y 'security_invoker=on' significan lo mismo y se almac |
| 539 | 10 | `docs/reglas/censos-y-catalogos.md` | distinto. Un '... not like '%security_invoker=true%'' cuenta las de 'on' como  |
| 540 | 11 | `docs/reglas/censos-y-catalogos.md` | *Medido el 12-ago-2026: el censo de vistas definer decía **18**. Son **13**. L |
| 541 | 12 | `docs/reglas/censos-y-catalogos.md` | de más eran 'v_escaparate', 'v_factura_cuadre', 'v_factura_escaneo' y 'v_salud |
| 542 | 13 | `docs/reglas/censos-y-catalogos.md` | sí son invoker — con 'on'. Reparto real de las 30: 13 sin poner · 13 'true' ·  |
| 543 | 14 | `docs/reglas/censos-y-catalogos.md` | 🔑 **Y lo que lo convierte en regla y no en anécdota: Fernando y yo escribimos  |
| 544 | 15 | `docs/reglas/censos-y-catalogos.md` | 'like '…=true%'' por separado, sin vernos, y los dos contamos 18.** Cuando dos |
| 545 | 16 | `docs/reglas/censos-y-catalogos.md` | caen igual en el mismo sitio, no es un despiste: es que la forma obvia está ma |
| 546 | 17 | `docs/reglas/censos-y-catalogos.md` | así, y devuelve lo mismo se escriba como se escriba: |
| 547 | 18 | `docs/reglas/censos-y-catalogos.md` | '''sql |
| 548 | 19 | `docs/reglas/censos-y-catalogos.md` | exists (select 1 from unnest(coalesce(c.reloptions,'{}')) o |
| 549 | 20 | `docs/reglas/censos-y-catalogos.md` | where lower(split_part(o,'=',1)) = 'security_invoker' |
| 550 | 21 | `docs/reglas/censos-y-catalogos.md` | and lower(split_part(o,'=',2)) in ('true','on','yes','1')) |
| 551 | 22 | `docs/reglas/censos-y-catalogos.md` | ''' |
| 552 | 23 | `docs/reglas/censos-y-catalogos.md` | ⚠️ Vale para **cualquier** 'reloptions' ('fillfactor', 'autovacuum_*', 'check_ |
| 553 | 24 | `docs/reglas/censos-y-catalogos.md` | no solo para ésta, y para todo catálogo que guarde texto libre. El fallo no da |
| 554 | 25 | `docs/reglas/censos-y-catalogos.md` | un recuento plausible, que es el peor. |
| 555 | 26 | `docs/reglas/censos-y-catalogos.md` | - 🔴 **EL CENSO POR CÓDIGO NO BASTA: HAY QUE CRUZARLO CON EL CENSO POR USO.** E |
| 556 | 27 | `docs/reglas/censos-y-catalogos.md` | qué está **escrito**; 'pg_stat_statements' dice qué se **ejecuta**. No respond |
| 557 | 28 | `docs/reglas/censos-y-catalogos.md` | misma pregunta y ninguno de los dos sustituye al otro. |
| 558 | 29 | `docs/reglas/censos-y-catalogos.md` | *Medido el 11-ago-2026: el censo de qué lee la v1 se hizo con un grep de '.fro |
| 559 | 30 | `docs/reglas/censos-y-catalogos.md` | sobre 'index.html' y dio 17 tablas. Parseando el FROM de las 511 consultas que |
| 560 | 31 | `docs/reglas/censos-y-catalogos.md` | 'anon' ha ejecutado de verdad salen **19**, y **seis no estaban** — entre ella |
| 561 | 32 | `docs/reglas/censos-y-catalogos.md` | 'escaner_memoria', con **5.767 llamadas**. Un grep de literales no ve lo que n |
| 562 | 33 | `docs/reglas/censos-y-catalogos.md` | escrito como literal, y sobre todo no ve a los consumidores que están FUERA de |
| 563 | 34 | `docs/reglas/censos-y-catalogos.md` | que estás mirando.* |
| 564 | 35 | `docs/reglas/censos-y-catalogos.md` | 🔑 Las dos consultas que lo hacen, y conviene tenerlas a mano: |
| 565 | 36 | `docs/reglas/censos-y-catalogos.md` | · **quién ejecuta** — 'pg_stat_statements' cruzado con 'pg_roles' por 'userid' |
| 566 | 37 | `docs/reglas/censos-y-catalogos.md` | CON QUÉ ROL, que es lo que suele decidir (un 'revoke' a 'anon' no toca lo que  |
| 567 | 38 | `docs/reglas/censos-y-catalogos.md` | 'authenticated'). |
| 568 | 39 | `docs/reglas/censos-y-catalogos.md` | · **cuánto histórico** — mucho mayor que los logs de la API: 🔬 105 días contra |
| 569 | 40 | `docs/reglas/censos-y-catalogos.md` | hora, y además cubre conector, 'psql' y cron, no sólo PostgREST. |
| 570 | 41 | `docs/reglas/censos-y-catalogos.md` | ⚠️ Y al revés también: que algo se ejecute **no** significa que esté en el rep |
| 571 | 42 | `docs/reglas/censos-y-catalogos.md` | donde aparecen los consumidores no versionados, que es justo lo que un censo d |
| 572 | 43 | `docs/reglas/censos-y-catalogos.md` | jubilación tiene que encontrar. |
| 573 | 66 | `CLAUDE.md` | - **Greps parciales no son lectura.** Si te preguntan "¿seguro que el código h |
| 574 | 67 | `CLAUDE.md` | fichero entero. |
| 575 | 7 | `docs/reglas/huellas-y-cambios-inertes.md` | - 🔴 **"Es idéntico en efecto" es una hipótesis. Para demostrar que un cambio e |
| 576 | 8 | `docs/reglas/huellas-y-cambios-inertes.md` | cambia nada: DOS RECORRIDOS COMPLETOS Y LAS MISMAS HUELLAS.** Estrenado el 9-a |
| 577 | 9 | `docs/reglas/huellas-y-cambios-inertes.md` | 'search_path' explícito de 'aplicar-migracion.yml'. El método: |
| 578 | 10 | `docs/reglas/huellas-y-cambios-inertes.md` | 1. 'restaurar-staging.yml' → 'ensayo' → 'aplicar', con la versión **vieja**, y |
| 579 | 11 | `docs/reglas/huellas-y-cambios-inertes.md` | md5 del estado resultante. |
| 580 | 12 | `docs/reglas/huellas-y-cambios-inertes.md` | 2. El mismo recorrido entero con la versión **nueva**. |
| 581 | 13 | `docs/reglas/huellas-y-cambios-inertes.md` | 3. Comparar. Si salen idénticas, el cambio es inerte **medido sobre el resulta |
| 582 | 14 | `docs/reglas/huellas-y-cambios-inertes.md` | argumentado — y entonces sí se puede llevar a la base de Elena. |
| 584 | 16 | `docs/reglas/huellas-y-cambios-inertes.md` | **Las siete huellas**, que juntas describen la forma de la base: columnas+tipo |
| 585 | 17 | `docs/reglas/huellas-y-cambios-inertes.md` | los índices · restricciones · firma de las funciones · políticas con su 'qual' |
| 586 | 18 | `docs/reglas/huellas-y-cambios-inertes.md` | vistas · ACL. *Staging no tiene los mismos nombres que producción: tiene la mi |
| 587 | 19 | `docs/reglas/huellas-y-cambios-inertes.md` | 🔒 **La huella se calcula desde UN solo sitio** ('sql/huella_acl.sql' para los  |
| 588 | 20 | `docs/reglas/huellas-y-cambios-inertes.md` | que hoy coinciden es una coincidencia, no una garantía: el día que alguien ret |
| 589 | 21 | `docs/reglas/huellas-y-cambios-inertes.md` | comparación empieza a mentir sin que nadie lo note. Es el hermano del 'LC_ALL= |
| 590 | 22 | `docs/reglas/huellas-y-cambios-inertes.md` | ⚠️ Y sirve para lo contrario también: si las huellas que **deben** cambiar cam |
| 591 | 23 | `docs/reglas/huellas-y-cambios-inertes.md` | **no** deben, no, eso demuestra que la migración hace lo que dice **y nada más |
| 593 | 69 | `CLAUDE.md` | ### El estado vive en el repo, no en las notas |
| 594 | 70 | `CLAUDE.md` | - Antes de afirmar el estado de cualquier pieza: **míralo**. Las notas de ayer |
| 595 | 36 | `docs/reglas/gotchas-del-entorno.md` | - 'raw.githubusercontent.com' tiene retraso de caché tras un commit. Para leer |
| 596 | 37 | `docs/reglas/gotchas-del-entorno.md` | **tarball por 'codeload.github.com'**. La API de GitHub sin token da 60 petici |
| 598 | 26 | `docs/reglas/huellas-y-cambios-inertes.md` | --- |
| 600 | 7 | `docs/reglas/seguridad-permisos.md` | ## 4. SEGURIDAD |
| 602 | 76 | `CLAUDE.md` | - 🔴 **Las credenciales NUNCA van en el código ni en un mensaje.** Viven en Git |
| 603 | 77 | `CLAUDE.md` | y R2. Una llave que aparece en un chat está quemada y se regenera. |
| 604 | 78 | `CLAUDE.md` | **Introducir credenciales no es algo que hagas tú: se lo pides a Fernando.** |
| 605 | 79 | `CLAUDE.md` | - **Supabase es PRODUCCIÓN.** Desde una sesión: **solo lectura**. Toda escritu |
| 606 | 80 | `CLAUDE.md` | rama → PR → Fernando aprueba → ensayo en staging → producción. |
| 607 | 81 | `CLAUDE.md` | - **Todo lo NUEVO nace CERRADO:** RLS activo y 0 políticas. Vistas 'security_i |
| 608 | 82 | `CLAUDE.md` | 'IMMUTABLE', sin 'SECURITY DEFINER'. |
| 609 | 9 | `docs/reglas/seguridad-permisos.md` | - 🔴 **Pero "nace cerrado" NO es el estado por defecto: hay que REVOCAR antes d |
| 610 | 10 | `docs/reglas/seguridad-permisos.md` | Medido el 30-jul-2026 en 'pg_default_acl' de las DOS bases: en 'public', toda  |
| 611 | 11 | `docs/reglas/seguridad-permisos.md` | nueva nace con **'arwdDxtm' concedido a 'anon' Y a 'authenticated'**, y toda * |
| 612 | 12 | `docs/reglas/seguridad-permisos.md` | 'EXECUTE' para 'anon'. Son DEFAULT PRIVILEGES de Supabase y **un 'revoke … fro |
| 613 | 13 | `docs/reglas/seguridad-permisos.md` | quita** (son grants explícitos a un rol, no a 'public'). Si escribes 'grant se |
| 614 | 14 | `docs/reglas/seguridad-permisos.md` | authenticated' y te quedas ahí, **el grant no añade nada porque ya lo tenía to |
| 615 | 15 | `docs/reglas/seguridad-permisos.md` | sigue diciendo 'authenticated=arwdDxtm'. Hay que revocar a **cada rol por su n |
| 616 | 16 | `docs/reglas/seguridad-permisos.md` | conceder — 'revoke all on <objeto> from public, anon, authenticated;' y luego  |
| 617 | 17 | `docs/reglas/seguridad-permisos.md` | y **MEDIR** el resultado ('pg_class.relacl' / 'pg_proc.proacl'), no suponerlo. |
| 618 | 18 | `docs/reglas/seguridad-permisos.md` | Afecta a **todo objeto nuevo**, también a las tablas que crean los procesadore |
| 619 | 19 | `docs/reglas/seguridad-permisos.md` | - 🔴 **Y no basta con revocar AL CREAR: hay que revocar CADA VEZ QUE SE RECREA. |
| 620 | 20 | `docs/reglas/seguridad-permisos.md` | 'CREATE OR REPLACE' **conserva** el ACL; **'DROP' + 'CREATE' lo PIERDE**, y el |
| 621 | 21 | `docs/reglas/seguridad-permisos.md` | con el default puesto, o sea con 'anon' dentro. Caso real medido el 30-jul-202 |
| 622 | 22 | `docs/reglas/seguridad-permisos.md` | 'entrada_factura_pvd' tenía 'anon=X' en **staging** y no en producción, **aunq |
| 623 | 23 | `docs/reglas/seguridad-permisos.md` | el 'revoke'** — alguien la había recreado con DROP+CREATE y aquel revoke ya no |
| 624 | 24 | `docs/reglas/seguridad-permisos.md` | nueva. No era explotable (aritmética pura, 'IMMUTABLE', no lee tablas), pero * |
| 625 | 25 | `docs/reglas/seguridad-permisos.md` | de ser iguales, y entonces un ensayo en staging ya no demuestra nada sobre pro |
| 626 | 26 | `docs/reglas/seguridad-permisos.md` | con un 'revoke … from anon' en staging. |
| 627 | 27 | `docs/reglas/seguridad-permisos.md` | Regla práctica: **si la migración lleva un 'drop', el 'revoke' va DESPUÉS del  |
| 628 | 28 | `docs/reglas/seguridad-permisos.md` | migración, y se mide el ACL al terminar.** |
| 629 | 83 | `CLAUDE.md` | - **La v1 tiene escritura anónima abierta** (deuda estructural). **No se toca  |
| 630 | 84 | `CLAUDE.md` | se cierra en la v2 con Auth + RPC. El problema no es la llave 'publishable' (e |
| 631 | 85 | `CLAUDE.md` | diseño): son las políticas. |
| 632 | 29 | `docs/reglas/seguridad-permisos.md` | - **SP-API: jamás con credenciales de Moloka SL.** Decidido y cerrado. Las cue |
| 633 | 30 | `docs/reglas/seguridad-permisos.md` | (Elena) y Fernando (autónomo) están separadas a nivel de credenciales. |
| 634 | 86 | `CLAUDE.md` | - **Confirmar una factura SIEMPRE inyecta stock.** Nunca subir facturas antigu |
| 635 | 7 | `docs/reglas/pendientes-backup-y-permisos.md` | - 🔴 **PENDIENTE — el backup NO copia los permisos: restaurar te deja la base A |
| 636 | 8 | `docs/reglas/pendientes-backup-y-permisos.md` | 'backup-bd.yml' vuelca con '--no-privileges', así que el fichero **no contiene |
| 637 | 9 | `docs/reglas/pendientes-backup-y-permisos.md` | 'REVOKE'**. Dicho en alto y sin adornos: **el día que haya que restaurar de ve |
| 638 | 10 | `docs/reglas/pendientes-backup-y-permisos.md` | con los ACL por defecto de Supabase — o sea, con 'anon' dentro de todo** (es e |
| 639 | 11 | `docs/reglas/pendientes-backup-y-permisos.md` | 'pg_default_acl' de los dos puntos de arriba: los objetos nacen con 'arwdDxtm' |
| 640 | 12 | `docs/reglas/pendientes-backup-y-permisos.md` | 'authenticated', y aquí nadie revoca después). Restauras el incendio y te qued |
| 641 | 13 | `docs/reglas/pendientes-backup-y-permisos.md` | **Esto no es una nota al pie: es un frente propio y hoy está abierto.** Lo que |
| 642 | 14 | `docs/reglas/pendientes-backup-y-permisos.md` | frío es cuál de los dos caminos: que el volcado se lleve los privilegios (quit |
| 643 | 15 | `docs/reglas/pendientes-backup-y-permisos.md` | y entonces el dump arrastra dueños y ACL, con lo que eso implica al restaurar  |
| 644 | 16 | `docs/reglas/pendientes-backup-y-permisos.md` | que el restore aplique al terminar un guion de permisos propio y **medido**. S |
| 645 | 17 | `docs/reglas/pendientes-backup-y-permisos.md` | 9-ago-2026. |
| 646 | 18 | `docs/reglas/pendientes-backup-y-permisos.md` | 🔬 **YA NO ES HIPOTÉTICO: medido el 10-ago en staging, recién restaurado.** 'v_ |
| 647 | 19 | `docs/reglas/pendientes-backup-y-permisos.md` | 'v_producto_amazon' tenían ahí 'anon=arwdDxtm', y en producción las dos tienen |
| 648 | 20 | `docs/reglas/pendientes-backup-y-permisos.md` | sin 'anon'. La restauración las devolvió abiertas, exactamente como dice el pá |
| 649 | 21 | `docs/reglas/pendientes-backup-y-permisos.md` | 🔒 **Y de ahí sale una REGLA para cualquier migración que se ensaye:** *un test |
| 650 | 22 | `docs/reglas/pendientes-backup-y-permisos.md` | NO prueba nada sobre producción.* Staging viene del dump sin privilegios, así  |
| 651 | 23 | `docs/reglas/pendientes-backup-y-permisos.md` | de Supabase por defecto, no los de prod. La ÚNICA excepción es el objeto que c |
| 652 | 24 | `docs/reglas/pendientes-backup-y-permisos.md` | migración que estás ensayando, porque lleva su 'revoke' dentro y por eso sí na |
| 653 | 25 | `docs/reglas/pendientes-backup-y-permisos.md` | **Conclusión práctica: el ACL se verifica EN PRODUCCIÓN, después de aplicar**  |
| 654 | 26 | `docs/reglas/pendientes-backup-y-permisos.md` | 'has_table_privilege('anon', …)', no en el ensayo. Con 'v_presencia_pais' se h |
| 655 | 27 | `docs/reglas/pendientes-backup-y-permisos.md` | - ⚠️ **PENDIENTE — el simulacro comprueba que las SECUENCIAS existan, y eso no |
| 656 | 28 | `docs/reglas/pendientes-backup-y-permisos.md` | Una secuencia puede volver de la copia **existiendo y con el contador a 1 sobr |
| 657 | 29 | `docs/reglas/pendientes-backup-y-permisos.md` | la primera inserción del día del incendio choca con clave duplicada. Por nombr |
| 658 | 30 | `docs/reglas/pendientes-backup-y-permisos.md` | El contraste que vale es de **valores**: los 'setval' que emite el dump contra |
| 659 | 31 | `docs/reglas/pendientes-backup-y-permisos.md` | 'pg_sequences.last_value'. Medido el 9-ago-2026: las **23** secuencias de prod |
| 660 | 32 | `docs/reglas/pendientes-backup-y-permisos.md` | contador avanzado (0 sin estrenar), así que le aplica a las 23. 'restaurar-sta |
| 661 | 33 | `docs/reglas/pendientes-backup-y-permisos.md` | imprime en cada ejecución cuántos 'setval' trae el dump, para que el agujero s |
| 662 | 34 | `docs/reglas/pendientes-backup-y-permisos.md` | diseño y merece su propio PR. |
| 663 | 35 | `docs/reglas/pendientes-backup-y-permisos.md` | - ⚠️ **PENDIENTE — el simulacro no compara las RESTRICCIONES, y son las que de |
| 664 | 36 | `docs/reglas/pendientes-backup-y-permisos.md` | Lo que importa de un índice no es el índice: es la **garantía**. Si staging ad |
| 665 | 37 | `docs/reglas/pendientes-backup-y-permisos.md` | producción rechaza, un ensayo sale verde y la migración revienta al aplicarla  |
| 666 | 38 | `docs/reglas/pendientes-backup-y-permisos.md` | exactamente el agujero que el simulacro existe para cerrar. Y las garantías vi |
| 667 | 39 | `docs/reglas/pendientes-backup-y-permisos.md` | 'pg_constraint' (PK, UNIQUE, FK, CHECK), con nombre, y en el dump como 'ADD CO |
| 668 | 40 | `docs/reglas/pendientes-backup-y-permisos.md` | comparación limpia. Ojo al detalle que hace inútil el atajo: **los índices que |
| 669 | 41 | `docs/reglas/pendientes-backup-y-permisos.md` | un UNIQUE NO aparecen en el dump como 'CREATE INDEX'**, sino dentro de un 'ALT |
| 670 | 42 | `docs/reglas/pendientes-backup-y-permisos.md` | CONSTRAINT', así que contar 'CREATE INDEX' da de menos y se inventa un rojo fa |
| 671 | 43 | `docs/reglas/pendientes-backup-y-permisos.md` | puro rendimiento no cambian si un ensayo es válido. Ese PR se llama **restricc |
| 672 | 44 | `docs/reglas/pendientes-backup-y-permisos.md` | - ⚠️ **PENDIENTE — la copia de FICHEROS a R2 no tiene simulacro de restauració |
| 673 | 45 | `docs/reglas/pendientes-backup-y-permisos.md` | 30-jul-2026 el backup diario ('backup-bd.yml' + 'backup_storage.py') copia a R |
| 674 | 46 | `docs/reglas/pendientes-backup-y-permisos.md` | 'facturas-pdfs' e 'informes' (las facturas de proveedor y el archivo histórico |
| 675 | 47 | `docs/reglas/pendientes-backup-y-permisos.md` | 'restaurar-staging.yml' solo ensaya el incendio de la **BD**: **esos ficheros  |
| 676 | 48 | `docs/reglas/pendientes-backup-y-permisos.md` | los abre nadie nunca.** Es el MISMO agujero que motivó todo esto (una copia en |
| 677 | 49 | `docs/reglas/pendientes-backup-y-permisos.md` | que nadie ha probado), en el otro activo. Falta un 'restaurar-ficheros' que ba |
| 678 | 50 | `docs/reglas/pendientes-backup-y-permisos.md` | y compruebe que abre. Hasta que exista, la copia de ficheros está **hecha pero |
| 679 | 51 | `docs/reglas/pendientes-backup-y-permisos.md` | extremo a extremo**. *(El backup sí tiene número de control externo contra 'st |
| 680 | 52 | `docs/reglas/pendientes-backup-y-permisos.md` | que una copia CORTA no pasa por buena — pero eso valida la subida, no la resta |
| 681 | 53 | `docs/reglas/pendientes-backup-y-permisos.md` | - 🔴 **PENDIENTE — las tablas 'monitor_*' del trackeador están abiertas a 'anon |
| 682 | 54 | `docs/reglas/pendientes-backup-y-permisos.md` | leer: para BORRAR.** Medido el 10-ago en producción, al cerrar el gate de las  |
| 684 | 56 | `docs/reglas/pendientes-backup-y-permisos.md` | \| Tabla \| Política \| Rol \| Qué permite \| |
| 685 | 57 | `docs/reglas/pendientes-backup-y-permisos.md` | \|---\|---\|---\|---\| |
| 686 | 58 | `docs/reglas/pendientes-backup-y-permisos.md` | \| 'monitor_reglas' \| 'anon_all_regla' 'ALL using(true)' \| **anon** \| leer, |
| 687 | 59 | `docs/reglas/pendientes-backup-y-permisos.md` | \| 'monitor_snapshots' \| 'anon_all_snap' 'ALL using(true)' \| **anon** \| lee |
| 688 | 60 | `docs/reglas/pendientes-backup-y-permisos.md` | \| 'monitor_resultados' \| 'p_resultados_all' 'ALL using(true)' \| **PUBLIC**  |
| 689 | 61 | `docs/reglas/pendientes-backup-y-permisos.md` | \| 'monitor_recomendaciones' \| 2 políticas 'anon' \| **anon** \| leer y ACTUA |
| 690 | 62 | `docs/reglas/pendientes-backup-y-permisos.md` | \| 'monitor_analisis' · 'monitor_doctrina' · 'monitor_reponibilidad_manual' \| |
| 692 | 64 | `docs/reglas/pendientes-backup-y-permisos.md` | 'monitor_reglas' son **las 21 reglas del trackeador**: la doctrina de precios  |
| 693 | 65 | `docs/reglas/pendientes-backup-y-permisos.md` | un 'DELETE' anónimo. La clave publicable viaja en el JavaScript de la app por  |
| 694 | 66 | `docs/reglas/pendientes-backup-y-permisos.md` | no es teórico. |
| 696 | 68 | `docs/reglas/pendientes-backup-y-permisos.md` | ✅ **EL PASO PREVIO QUE ESTO EXIGÍA YA ESTÁ DADO** (11-ago-2026, 'ef6e72e', PR  |
| 697 | 69 | `docs/reglas/pendientes-backup-y-permisos.md` | trackeador deja de escribir como anon»*). Aquí vivía un párrafo que decía que  |
| 698 | 70 | `docs/reglas/pendientes-backup-y-permisos.md` | del trackeador *«inyectan ÚNICAMENTE 'secrets.SUPABASE_KEY'»* y que por tanto  |
| 699 | 71 | `docs/reglas/pendientes-backup-y-permisos.md` | nada hasta saber qué contenía ese secreto. **Era cierto cuando se escribió y d |
| 700 | 72 | `docs/reglas/pendientes-backup-y-permisos.md` | 11-ago**; la nota siguió en pie 17 días. Lo que hay hoy, medido en el repo: |
| 701 | 73 | `docs/reglas/pendientes-backup-y-permisos.md` | - 'tracker-app.yml:45' y 'tracker-cerebro.yml:53' **inyectan las DOS**, inclui |
| 702 | 74 | `docs/reglas/pendientes-backup-y-permisos.md` | 'SUPABASE_SERVICE_KEY'. |
| 703 | 75 | `docs/reglas/pendientes-backup-y-permisos.md` | - Los scripts que esos workflows lanzan —'moloka_tracker_snapshot_nube.py' y |
| 704 | 76 | `docs/reglas/pendientes-backup-y-permisos.md` | 'moloka_tracker_cerebro.py'— hacen |
| 705 | 77 | `docs/reglas/pendientes-backup-y-permisos.md` | 'os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']', así qu |
| 706 | 78 | `docs/reglas/pendientes-backup-y-permisos.md` | lado de la **de servicio**. |
| 707 | 79 | `docs/reglas/pendientes-backup-y-permisos.md` | - ⚠️ 'moloka_tracker_snapshot.py' (sin '_nube') sí usa **solo** 'SUPABASE_KEY' |
| 708 | 80 | `docs/reglas/pendientes-backup-y-permisos.md` | pero **no lo lanza ningún workflow**: es la versión **CLI**, la que se corre a |
| 709 | 81 | `docs/reglas/pendientes-backup-y-permisos.md` | '--fba/--keepa', y en Actions entra solo como motor importado. No confundirla  |
| 710 | 82 | `docs/reglas/pendientes-backup-y-permisos.md` | que es el que corre de verdad. |
| 712 | 84 | `docs/reglas/pendientes-backup-y-permisos.md` | 🔒 **Lo que NO cambia, y es lo que hay que llevarse:** las políticas de la tabl |
| 713 | 85 | `docs/reglas/pendientes-backup-y-permisos.md` | ahí** — ninguna migración del repo las toca (comprobado el 28-ago). Que el tra |
| 714 | 86 | `docs/reglas/pendientes-backup-y-permisos.md` | de 'anon' quita el motivo por el que esto estaba parado, **no cierra las polít |
| 715 | 87 | `docs/reglas/pendientes-backup-y-permisos.md` | 📌 **Y cerrarlas NO se decide aquí: está APARCADO hasta jubilar la v1**, junto  |
| 716 | 88 | `docs/reglas/pendientes-backup-y-permisos.md` | 'escaner_memoria'. Decisión cerrada de Fernando; este apartado la registra, no |
| 718 | 90 | `docs/reglas/pendientes-backup-y-permisos.md` | ⚠️ El trackeador sigue **parado desde el 11-jul-2026** (última ejecución de lo |
| 719 | 91 | `docs/reglas/pendientes-backup-y-permisos.md` | Cuando se retome, el día que se toque esto: primero se comprueba que arranca c |
| 720 | 92 | `docs/reglas/pendientes-backup-y-permisos.md` | y solo DESPUÉS se quitan las políticas de 'anon'. En ese orden, nunca al revés |
| 721 | 93 | `docs/reglas/pendientes-backup-y-permisos.md` | ⚠️ Y 'productos' sigue con **455 filas legibles por 'anon'** (§6 ya lo señalab |
| 722 | 94 | `docs/reglas/pendientes-backup-y-permisos.md` | - 🔴 **PENDIENTE — NO EXISTE UNA LISTA FIABLE DE QUÉ MIGRACIONES SE HAN APLICAD |
| 723 | 95 | `docs/reglas/pendientes-backup-y-permisos.md` | 'supabase_migrations.schema_migrations' existe y tiene **37 registros, el últi |
| 724 | 96 | `docs/reglas/pendientes-backup-y-permisos.md` | '20260806085625'** — o sea del **6-ago-2026**. Ni el contador ni el 'setval' d |
| 725 | 97 | `docs/reglas/pendientes-backup-y-permisos.md` | ahí, ni nada de lo aplicado desde entonces. **Medido el 10-ago-2026.** |
| 726 | 98 | `docs/reglas/pendientes-backup-y-permisos.md` | Son **dos agujeros, uno encima del otro**: |
| 727 | 99 | `docs/reglas/pendientes-backup-y-permisos.md` | 1. 'aplicar-migracion.yml' aplica con **psql directo**, no por la CLI de Supab |
| 728 | 100 | `docs/reglas/pendientes-backup-y-permisos.md` | registro no se toca nunca. No es un fallo del workflow: es que nadie lo escrib |
| 729 | 101 | `docs/reglas/pendientes-backup-y-permisos.md` | 2. Y esa tabla vive en el esquema **'supabase_migrations'**, mientras el volca |
| 730 | 102 | `docs/reglas/pendientes-backup-y-permisos.md` | 'pg_dump --schema=public'. Así que **aunque estuviera al día, el backup no la  |
| 732 | 104 | `docs/reglas/pendientes-backup-y-permisos.md` | 🔴 **Lo que esto significa el día del incendio:** *"restaurar y reaplicar lo po |
| 733 | 105 | `docs/reglas/pendientes-backup-y-permisos.md` | backup"* NO se puede resolver mirando la base. Hay que reconstruirlo del histo |
| 734 | 106 | `docs/reglas/pendientes-backup-y-permisos.md` | GitHub o de memoria — y la memoria es justo lo que no funciona a las tres de l |
| 735 | 107 | `docs/reglas/pendientes-backup-y-permisos.md` | mismo patrón que las tres viñetas de arriba: **el estado en un sitio que el ba |
| 737 | 109 | `docs/reglas/pendientes-backup-y-permisos.md` | 🔑 **El arreglo es barato porque la pieza ya existe:** el paso 8 de 'aplicar-mi |
| 738 | 110 | `docs/reglas/pendientes-backup-y-permisos.md` | calcula el 'sha256' del fichero. Basta con que escriba una fila en una tabla * |
| 739 | 111 | `docs/reglas/pendientes-backup-y-permisos.md` | fichero, sha256, entorno, quién lo despachó, cuándo, y si fue 'ensayo' o 'apli |
| 740 | 112 | `docs/reglas/pendientes-backup-y-permisos.md` | registro pasa a **sobrevivir al restore**. Con eso, restaurar deja de ser *"ac |
| 741 | 113 | `docs/reglas/pendientes-backup-y-permisos.md` | ser *"mira qué falta desde la fecha del dump"*. Va **detrás** del PR del model |
| 742 | 114 | `docs/reglas/pendientes-backup-y-permisos.md` | '--no-privileges'; se anota aquí para que no dependa de que alguien lo recuerd |
| 744 | 116 | `docs/reglas/pendientes-backup-y-permisos.md` | --- |
| 746 | 7 | `docs/reglas/como-se-trabaja.md` | ## 5. CÓMO SE TRABAJA AQUÍ |
| 748 | 92 | `CLAUDE.md` | - **UN PR, UNA COSA.** Sin excepciones. |
| 749 | 9 | `docs/reglas/como-se-trabaja.md` | - 🔴 **AL FUSIONAR UN PR, QUIEN CREÓ EL WORKTREE LO RETIRA CON 'git worktree re |
| 750 | 10 | `docs/reglas/como-se-trabaja.md` | Un worktree que sobrevive a su PR es un clon fantasma más donde alguien leerá  |
| 751 | 11 | `docs/reglas/como-se-trabaja.md` | equivocado. Nunca se borra la carpeta a mano —eso deja el registro de 'git wor |
| 752 | 12 | `docs/reglas/como-se-trabaja.md` | mintiendo—: 'git worktree remove <ruta>' y, al terminar la tanda, 'git worktre |
| 753 | 93 | `CLAUDE.md` | - 🔴 **AL TERMINAR UN TRABAJO, EL PARTE SE DEJA EN LA BANDEJA.** Además del PR, |
| 754 | 94 | `CLAUDE.md` | una copia del informe en 'G:\Mi unidad\Moloka\bandeja\' con el nombre |
| 755 | 95 | `CLAUDE.md` | **'AAAA-MM-DD-HHMM-tema.md'** (hora española). **Primera línea del fichero: qu |
| 756 | 96 | `CLAUDE.md` | cuándo.** Sin esa copia, el trabajo solo existe dentro del repo y Fernando tie |
| 757 | 97 | `CLAUDE.md` | correveidile entre Code y los chats. La bandeja es lo que lo evita, y **no dep |
| 758 | 98 | `CLAUDE.md` | nadie se acuerde de pedirlo en el encargo**. |
| 759 | 7 | `docs/reglas/escalera-de-migraciones.md` | - 🔴 **ANTES DE ENSAYAR UNA MIGRACIÓN EN STAGING, SE RESTAURA STAGING.** Se lan |
| 760 | 8 | `docs/reglas/escalera-de-migraciones.md` | 'restaurar-staging.yml' y se espera a que salga en VERDE. La escalera entera e |
| 761 | 9 | `docs/reglas/escalera-de-migraciones.md` | **restaurar staging → staging ensayo → staging aplicar → verificación SQL → pr |
| 762 | 10 | `docs/reglas/escalera-de-migraciones.md` | producción aplicar → verificación SQL**, con Elena avisada antes de tocar prod |
| 763 | 11 | `docs/reglas/escalera-de-migraciones.md` | **Por qué:** un ensayo en staging solo demuestra algo sobre producción si las  |
| 764 | 12 | `docs/reglas/escalera-de-migraciones.md` | El 9-ago-2026 staging tenía 54 objetos contra los 83 de producción — faltaban  |
| 765 | 13 | `docs/reglas/escalera-de-migraciones.md` | 'v_salud_asin' y 'v_trackeador_cola' — y con eso los ensayos de semanas entera |
| 766 | 14 | `docs/reglas/escalera-de-migraciones.md` | nada. El caso concreto: el ensayo de '2026-08-07_demanda_asin_contador.sql' mu |
| 767 | 15 | `docs/reglas/escalera-de-migraciones.md` | 'ERROR: relation "v_salud_asin" does not exist', que no era un problema de la  |
| 768 | 16 | `docs/reglas/escalera-de-migraciones.md` | base contra la que se probaba. |
| 769 | 17 | `docs/reglas/escalera-de-migraciones.md` | **Y por qué así y no con un vigilante de deriva:** porque la deriva no se mide |
| 770 | 18 | `docs/reglas/escalera-de-migraciones.md` | alarma diaria cuya única acción posible es siempre la misma —restaurar staging |
| 771 | 19 | `docs/reglas/escalera-de-migraciones.md` | dos semanas. Es el 'ON_ERROR_STOP=0' por el otro extremo. Restaurando antes de |
| 772 | 20 | `docs/reglas/escalera-de-migraciones.md` | nunca es más viejo que el backup de anoche y no queda deriva que vigilar. |
| 773 | 21 | `docs/reglas/escalera-de-migraciones.md` | ⚠️ **LA ÚNICA EXCEPCIÓN, y viene con su fecha para que no se haga costumbre: e |
| 774 | 22 | `docs/reglas/escalera-de-migraciones.md` | volcado va POR DETRÁS de lo que se acaba de crear.** El 23-ago-2026, con la mi |
| 775 | 23 | `docs/reglas/escalera-de-migraciones.md` | '2026-08-23_jubilar_salud_fba.sql', restaurar staging lo habría dejado **PEOR* |
| 776 | 24 | `docs/reglas/escalera-de-migraciones.md` | anoche es anterior a 'inventario_fba', así que la tabla no existiría allí y la |
| 777 | 25 | `docs/reglas/escalera-de-migraciones.md` | la migración habría abortado por una causa que no tiene nada que ver con la mi |
| 778 | 26 | `docs/reglas/escalera-de-migraciones.md` | 🔑 **No se desactiva la regla: se esquiva el único día en que el volcado va por |
| 779 | 27 | `docs/reglas/escalera-de-migraciones.md` | base.** La regla existe para que staging se PAREZCA a producción, y ese día se |
| 780 | 28 | `docs/reglas/escalera-de-migraciones.md` | desde las dos bases antes de decidir: 'inventario_fba' 354 filas y foto del 23 |
| 781 | 29 | `docs/reglas/escalera-de-migraciones.md` | 'inventario_fba_historico' 354 y 1 fecha, 'salud_fba' con 'relkind='v'', 'salu |
| 782 | 30 | `docs/reglas/escalera-de-migraciones.md` | 'salud_fba_historico' 1.984 filas y 9 fechas, 'v_ventas_ventanas' viva, y los  |
| 783 | 31 | `docs/reglas/escalera-de-migraciones.md` | restaurar lo que la habría alejado. |
| 784 | 32 | `docs/reglas/escalera-de-migraciones.md` | ⏳ **Y la ventana es de UN día**: el backup de esa noche ya incluye 'inventario |
| 785 | 33 | `docs/reglas/escalera-de-migraciones.md` | partir del 24-ago el restaurado vuelve a hacer lo que promete y la regla se ap |
| 786 | 34 | `docs/reglas/escalera-de-migraciones.md` | 📌 La forma de saber si vuelve a tocar: **mirar el estado del destino antes de  |
| 787 | 35 | `docs/reglas/escalera-de-migraciones.md` | fecha. Si lo que la migración necesita nació DESPUÉS del último volcado, resta |
| 788 | 36 | `docs/reglas/escalera-de-migraciones.md` | suelo sobre el que se iba a ensayar; en cualquier otro caso, se restaura. |
| 789 | 99 | `CLAUDE.md` | - **Antes de picar: lee cómo se hizo lo anterior.** Hay procesadores en produc |
| 790 | 100 | `CLAUDE.md` | el siguiente se les tiene que parecer. Si algo se aparta del patrón, dilo y ex |
| 791 | 101 | `CLAUDE.md` | - **Las dudas de diseño no se resuelven en caliente.** Se anotan en una línea  |
| 792 | 102 | `CLAUDE.md` | - **Cuando Fernando dice "esto no me cuadra", PARA y baja al dato.** Acierta ~ |
| 793 | 103 | `CLAUDE.md` | Casos reales: un bug oficial de la API de Amazon (FBA_CORE), un envío perdido  |
| 794 | 104 | `CLAUDE.md` | borrado con 12 uds dentro. En los cuatro, la explicación cómoda era la equivoc |
| 795 | 105 | `CLAUDE.md` | - **Darle la razón sin medir es fallarle.** Si tienes el dato y contradice lo  |
| 796 | 13 | `docs/reglas/como-se-trabaja.md` | - **Distingue "podría" de "está documentado".** Una hipótesis bien redactada n |
| 797 | 14 | `docs/reglas/como-se-trabaja.md` | Si no lo has verificado ahora mismo, dilo. |
| 798 | 15 | `docs/reglas/como-se-trabaja.md` | - **Antes de decir "no se puede":** eso es una hipótesis. Agota la búsqueda (d |
| 799 | 16 | `docs/reglas/como-se-trabaja.md` | la propia herramienta, la web). *"No conozco una manera"* ≠ *"no existe una ma |
| 801 | 7 | `docs/reglas/gotchas-del-entorno.md` | ### Gotchas del entorno |
| 802 | 8 | `docs/reglas/gotchas-del-entorno.md` | - **La máquina de Fernando es Windows y su terminal es PowerShell**, pero las  |
| 803 | 9 | `docs/reglas/gotchas-del-entorno.md` | **Bash**. '&&' no funciona en su terminal; las here-strings de PowerShell ('@' |
| 804 | 10 | `docs/reglas/gotchas-del-entorno.md` | los mensajes de commit si las usas en Bash. Comandos de una línea, sintaxis Ba |
| 805 | 11 | `docs/reglas/gotchas-del-entorno.md` | - **'workflow_dispatch' exige que el '.yml' esté en la rama por defecto.** Ord |
| 806 | 12 | `docs/reglas/gotchas-del-entorno.md` | fichero → merge → ensayo. |
| 807 | 13 | `docs/reglas/gotchas-del-entorno.md` | - 🔴 **EL ID DE UN RUN SE TOMA DE LA URL QUE IMPRIME EL DISPATCH, JAMÁS DE |
| 808 | 14 | `docs/reglas/gotchas-del-entorno.md` | 'gh run list --limit 1'.** El run recién creado tarda unos segundos en registr |
| 809 | 15 | `docs/reglas/gotchas-del-entorno.md` | "el último de la lista" puede ser **el ANTERIOR** — y como ése suele estar en  |
| 810 | 16 | `docs/reglas/gotchas-del-entorno.md` | 'gh run watch' vuelve al instante y da por bueno un trabajo que **todavía no h |
| 811 | 17 | `docs/reglas/gotchas-del-entorno.md` | Es un verde prestado, hermano de los dos de §3. |
| 812 | 18 | `docs/reglas/gotchas-del-entorno.md` | *Medido el 11-ago-2026: di por aplicado un andamio de staging leyendo el run d |
| 813 | 19 | `docs/reglas/gotchas-del-entorno.md` | antes. Se cazó porque la comprobación por SQL no cuadraba con lo que decía el  |
| 814 | 20 | `docs/reglas/gotchas-del-entorno.md` | 'gh workflow run' (v2.96.0, la de esta máquina) **sí imprime la URL del run cr |
| 815 | 21 | `docs/reglas/gotchas-del-entorno.md` | ahí sale el id: |
| 816 | 22 | `docs/reglas/gotchas-del-entorno.md` | '''bash |
| 817 | 23 | `docs/reglas/gotchas-del-entorno.md` | URL=$(gh workflow run X.yml -f entorno=staging 2>&1 \| head -1); ID=${URL##*/} |
| 818 | 24 | `docs/reglas/gotchas-del-entorno.md` | ''' |
| 819 | 25 | `docs/reglas/gotchas-del-entorno.md` | Si algún día no la imprimiera, la salida es acotar por '--branch' o '--created |
| 820 | 26 | `docs/reglas/gotchas-del-entorno.md` | "el último". Y la regla de fondo es la de siempre: la verificación es SQL cont |
| 821 | 27 | `docs/reglas/gotchas-del-entorno.md` | el log — y menos aún el log de otro run. |
| 822 | 28 | `docs/reglas/gotchas-del-entorno.md` | - **En un '.yml', un 'no' suelto es el BOOLEANO 'false', no la cadena "no"** ( |
| 823 | 29 | `docs/reglas/gotchas-del-entorno.md` | Noruega": 'NO' = Norway). *Medido el 11-ago-2026 sobre |
| 824 | 30 | `docs/reglas/gotchas-del-entorno.md` | 'procesar-custom-analytics.yml': 'options: [no, si]' de un input se lee '[Fals |
| 825 | 31 | `docs/reglas/gotchas-del-entorno.md` | Las opciones y los defaults de texto van **entrecomillados**. Vale para 'on',  |
| 826 | 32 | `docs/reglas/gotchas-del-entorno.md` | 'y', 'n' y las variantes en mayúsculas. |
| 827 | 33 | `docs/reglas/gotchas-del-entorno.md` | - **Los commits de este repo se firman con la dirección noreply de GitHub.** E |
| 828 | 34 | `docs/reglas/gotchas-del-entorno.md` | no publiques correos reales en la historia. La identidad está en 'git config - |
| 829 | 35 | `docs/reglas/gotchas-del-entorno.md` | '--global'. |
| 831 | 39 | `docs/reglas/gotchas-del-entorno.md` | --- |
| 833 | 8 | `docs/reglas/donde-esta-el-proyecto.md` | ## 6. DÓNDE ESTÁ EL PROYECTO AHORA |
| 835 | 10 | `docs/reglas/donde-esta-el-proyecto.md` | La v2 ("el bicho") se construye con **patrón estrangulador**: nace al lado de  |
| 836 | 11 | `docs/reglas/donde-esta-el-proyecto.md` | Supabase, y Elena se muda pestaña a pestaña. **Los datos no se mudan: se curan |
| 837 | 12 | `docs/reglas/donde-esta-el-proyecto.md` | dos verdades y un descuadre garantizado. |
| 839 | 14 | `docs/reglas/donde-esta-el-proyecto.md` | **Fase 0 (la capa de datos) va PRIMERO** y está a medias. ⚠️ Aquí ponía que *« |
| 840 | 15 | `docs/reglas/donde-esta-el-proyecto.md` | (repo, pantallas, Auth) no hay nada todavía»*: eso era cierto al arrancar el p |
| 841 | 16 | `docs/reglas/donde-esta-el-proyecto.md` | es**. La app existe en el repo 'moloka-app-v2', se despliega en Vercel, tiene  |
| 842 | 17 | `docs/reglas/donde-esta-el-proyecto.md` | '@supabase/ssr', y su Inventario está en marcha — hasta el punto de que un wor |
| 843 | 18 | `docs/reglas/donde-esta-el-proyecto.md` | mañana laborable «antes de que entre Elena». Lo que sigue siendo verdad es el  |
| 844 | 19 | `docs/reglas/donde-esta-el-proyecto.md` | va primero. |
| 846 | 111 | `CLAUDE.md` | Orden de mudanza acordado: Inventario → Inicio → Alertas → Movimientos → Rotac |
| 847 | 112 | `CLAUDE.md` | *(frontera lectura/escritura)* → Entrada → Facturas → Envío FBA → Motores. |
| 849 | 143 | `CLAUDE.md` | *Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pong |

