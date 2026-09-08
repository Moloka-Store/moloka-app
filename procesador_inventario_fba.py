# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR INVENTARIO_FBA — el informe «Gestión de inventario de Logística de
# Amazon» (Seller Central → Informes → Logística de Amazon)
# ----------------------------------------------------------------------------
# QUÉ CONTESTA, y por qué nace: **CUÁNTO VIENE DE CAMINO**.
#
#   `salud_fba` está roto por parte de Amazon (sirve ficheros truncados; los
#   bloquea su Guarda 9) y lleva congelado desde el 16-ago-2026. Casi todo lo
#   suyo ya lo cubren otras tablas MENOS UNA COSA: las unidades en tránsito
#   (`inbound_shipped`). Sin ese dato la app manda a preparar un envío QUE YA
#   SALIÓ.
#
#   El caso que lo motiva, medido en el fichero real (50632020686.txt) el
#   23-ago-2026, ASIN B0BVK34G8X:
#       afn-fulfillable-quantity        1   ← en la estantería
#       afn-inbound-shipped-quantity   36   ← en el camión
#       afn-warehouse-quantity          2
#   `inventario_internacional` dice 2. Este informe dice 38 (`total-quantity`).
#   Ninguno miente: 36 van de camino. Medido el mismo día: 363 unidades en
#   tránsito repartidas en 17 ASIN, contra las 143 que era lo último que sabía
#   `salud_fba` (verificado por SQL en producción: sum(inbound_shipped)=143 en 9
#   filas, snapshot 16-ago).
#
# 🔒 ESTO NACIÓ COMO UNA FUENTE DE MÁS, Y HOY ES LA ÚNICA. Aquí ponía que
#    «`procesador_salud_fba.py` no se toca» y que «nadie lee `inventario_fba`
#    todavía». Las dos frases eran ciertas al escribirlas y dejaron de serlo el
#    **23-ago-2026**, el mismo día:
#      · `procesador_salud_fba.py` se BORRÓ del repo (se jubiló el informe);
#      · `salud_fba` pasó a ser una VISTA que lee de esta tabla, y de ella penden
#        `v_salud_asin`, `v_salud_fba_cruce`, `v_keepa_cruce` y `v_incidencias_ultima`;
#      · y la app v2 lee `inventario_fba` directamente.
#    O sea que esta carga ya NO es aditiva: si falla, se nota aguas abajo.
#
# ----------------------------------------------------------------------------
# EL CAJÓN: **FOTO** (§1.6 de CLAUDE.md). Contesta "¿cómo está esto AHORA?", así
#   que tira la hoja vieja: los SKU que ya no vienen en el fichero se BORRAN.
#   Borrado y carga en la MISMA transacción, y la guarda anti-encogimiento
#   ANTES del borrado. Patrón heredado de `foto_comun.py`, como las otras cuatro.
#
# LA CLAVE ES `sku`, y está MEDIDO, no supuesto (fichero real, 23-ago-2026):
#   · `sku`   → 356 distintos sobre 356 filas. 0 duplicados. ES la clave.
#   · `fnsku` → 356 distintos. También único, pero es un código de etiqueta, no
#               la identidad del listing.
#   · 🔴 `asin` → 355 distintos sobre 356: **B07GRRYFL1 aparece DOS VECES**, con
#               dos SKU y dos vidas distintas — `5I-FPC3-XCAZ`/`X002N87OE5`
#               (FNSKU propio ⇒ etiquetado, 9 uds) y `AE-EFSN-IN21`/`B07GRRYFL1`
#               (FNSKU = ASIN ⇒ **commingled**, 14 uds). Una PK por ASIN
#               REVENTARÍA hoy mismo, y encima fundiría dos realidades que
#               CLAUDE.md §2 manda distinguir.
#   ⚠️ Que la PK sea el SKU **no lo asciende a llave maestra** (§1.1: el SKU nace
#      y muere y JAMÁS cruza catálogos). Es la clave DE ESTA FOTO, la del
#      informe consigo mismo — igual que `inventario_internacional` usa
#      (seller_sku, country). El puente a la identidad se hará por ASIN, en una
#      vista, cuando haya una pregunta que contestar. En este PR NO hay vista
#      (misma disciplina que paneu y que internacional).
#
# 🔴 EL PAÍS: **ESTE INFORME NO TIENE PAÍS, Y NO SE LE INVENTA UNO.**
#   La columna `store` viene VACÍA en las 356 filas. Vacío NO significa "España":
#   significa "todas las tiendas" — el fichero trae el TOTAL EUROPEO. Medido
#   contra la base el 23-ago-2026 con B0002TT3N4:
#       inventario_internacional → ES 1.233 + FR 18 + IT 493 = 1.744
#       este informe             → afn-warehouse-quantity     = 1.749
#   Etiquetar esto como ES metería 1.749 unidades en un país que tiene 1.233, y
#   ese error no da un aviso: da una cifra plausible. Por eso NO hay columna de
#   país en la tabla, y por eso §1.2 (el país es una FILA) no aplica aquí: no
#   hay eje país que modelar, hay un total. Si algún día `store` llegara con
#   valor, el informe estaría contando OTRA COSA → la Guarda 9 lo GRITA y el
#   valor queda en la columna `store`, no sólo en el log.
#
# ÁMBITO DE LA FOTO: NINGUNO (como all_listings, paneu e internacional). El
#   fichero ES la tabla entera: sin ámbito, el barrido borra lo que no viene.
#
# TRAMPAS MEDIDAS contra el fichero real (50632020686.txt, 23-ago-2026):
#   · **SIN BOM** (medido: los 6 primeros bytes son b'sku\tfn'). Como el
#     internacional y el ledger, NO como paneu/salud_fba/keepa. `utf-8-sig`
#     decodifica bien con y sin BOM; reserva `cp1252`. 🔒 El encoding NO se
#     hereda de otra cañería: esto está medido AQUÍ (§2 de CLAUDE.md).
#   · Finales de línea **CRLF** — los resuelve el propio `csv`, y `_clean()`
#     quita el `\r` de todas formas. Medido: la última celda llega limpia.
#   · El nombre del fichero es un ID numérico de Amazon (50632020686.txt): NO
#     trae fecha ni país. → `fecha_foto` sale de la SUBIDA al buzón, como en
#     internacional. Sin guarda de nombre (eso es cosa de keepa).
#   · **DOS columnas vienen vacías en las 356 filas**: `mfn-fulfillable-quantity`
#     y `store`. Y `afn-researching-quantity` trae 14 huecos. Ninguna de las
#     tres es de las que se tipan; las tres se conservan en `crudo`.
#     ⚠️ El encargo decía "ninguna columna vacía": el fichero dice otra cosa. Se
#     escribe lo medido.
#   · `condition` = New y `afn-listing-exists` = Yes en las 356 (no sirven para
#     filtrar, pero sí para GRITAR si cambian).
#
# LECTURA DEL TSV: por `tsv_comun.leer_tsv` (QUOTE_NONE). La comilla de Amazon
#   es TEXTO —los títulos traen pulgadas y comas—, y una que abra un campo sin
#   cerrar FUSIONA FILAS en silencio. Medido en este fichero: QUOTE_NONE y el
#   lector ingenuo dan hoy las mismas 357 filas, así que la red es INERTE sobre
#   el dato de hoy — que es justo el mejor momento para ponerla.
#
# Precedente a imitar: `procesador_internacional.py` (foto SIN ámbito, fecha por
#   subida, PK medida en el fichero) y `procesador_paneu_aptos.py`. Misma
#   escalera (ENTORNO staging|produccion, MODO ensayo|aplicar), misma disciplina
#   de guardas, escritura por LOTES (`execute_values`) desde el primer día.
# ============================================================================

import datetime
import os, sys
from collections import Counter

from psycopg2.extras import Json, execute_values
from supabase import create_client

from tsv_comun import leer_tsv
from foto_comun import (Aborta, conectar_bd, listar_buzon, descargar_buzon,
                        fecha_del_dato_por_subida, guarda_anti_encogimiento,
                        guarda_no_retroceder, claves_previas, barrer_sobrantes,
                        resumen_foto)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
from anti_cero import exigir_poblacion  # noqa: E402

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion
# Nombre EXACTO del .txt del buzón que se quiere procesar. Vacío = el más reciente.
# Lo manda la app v2 al soltar el fichero (`inputFichero` de su catálogo): procesa ESE,
# no «el último que haya», que con dos informes en la carpeta es una lotería.
FICHERO      = os.environ.get('FICHERO', '').strip()

BUCKET, CARPETA = 'informes', 'inventario_fba'
TABLA = 'inventario_fba'
TABLA_HIST = 'inventario_fba_historico'
TABLA_CENSO = 'inventario_fba_cabecera'   # Guarda 11: una fila por foto

# ---------------------------------------------------------------------------
# EL UMBRAL DE FILAS — Guarda 4. El número, y de dónde sale.
# ---------------------------------------------------------------------------
# 🔴 POR QUÉ EXISTE: `salud_fba` se rompió porque Amazon empezó a servir ficheros
#    truncados y NO HABÍA FORMA DE DISTINGUIR UN INFORME PEQUEÑO DE UNO ROTO. Los
#    rotos traían 37 filas (y 17.702 bytes) contra las 219 del sano — el
#    `salud_fba/50629020686.txt` que sigue en el buzón, subido el 21-ago, pesa
#    exactamente esos 17.702 bytes.
#
# LO MEDIDO, que es lo que fija el número (23-ago-2026):
#      este informe, sano                      356 filas
#      inventario_internacional en producción   322 filas · 225 SKU
#      salud_fba en producción (16-ago)         219 filas
#      los salud_fba rotos                       37 filas  ← 17% del sano
#
# 150 son el 42% de las 356 de hoy y CUATRO VECES las 37 del roto. Para que este
# umbral salte por una causa distinta de la que dice medir, el catálogo FBA de
# Moloka tendría que perder más de la mitad de sus SKU de una vez — que es
# exactamente lo que la anti-encogimiento también llama imposible. Y si ese día
# llega de verdad, la puerta tiene nombre: PERMITIR_UMBRAL_BAJO=1.
#
# ⚠️ **NO HAY UMBRAL POR BYTES, y es a propósito.** El encargo daba "97-107 KB"
#    como peso sano; el fichero real pesa **68.365 bytes**. Un suelo de 97 KB
#    habría RECHAZADO el fichero bueno que motiva todo esto. El peso de este TSV
#    lo mandan los títulos de producto, que cambian solos; las filas no. Se mide
#    lo que se quiere medir.
UMBRAL_FILAS = 150

# ---------------------------------------------------------------------------
# 🔴 AQUÍ VIVÍA `N_COLUMNAS = 26`, Y SE HA IDO. Léelo antes de escribir otra igual.
# ---------------------------------------------------------------------------
# Decía ser «el ancho exacto del fichero, un INVARIANTE», y llevaba desde el
# 23-ago-2026 pareciendo que protegía la forma del informe. **No la protegía:
# ninguna guarda la leía.** La Guarda 3 (filas dentadas) mide contra
# `len(cabecera)`, o sea contra la cabecera del propio fichero, que es lo correcto
# — así caza la fila cortada a media línea sin depender de un número escrito a
# mano. Lo único que tocaba `N_COLUMNAS` era una línea del test.
#
# Y el 7-sep-2026 dejó además de ser cierta: Amazon sirvió 24 columnas. Una
# constante muerta y falsa al lado de una guarda que sí funciona es peor que nada,
# porque invita a confiar en ella.
#
# 🔑 Quien registra la forma del informe carga a carga sigue siendo el CENSO
#    (Guarda 11), que guarda cuántos encabezados vinieron **y cuáles**.
# ⚠️ Y desde el 7-sep-2026 SÍ hay un ancla del ancho, pero no es un número suelto:
#    es el CATÁLOGO de modelos conocidos (`MODELO_26` / `MODELO_24`) que lee la
#    Guarda 14, y compara la cabecera entera y en su orden. La diferencia con la
#    constante muerta que había aquí es exactamente ésa: **una guarda la lee**.

# ---------------------------------------------------------------------------
# Columnas: (encabezado EXACTO del .txt, columna Postgres, tipo)
#   tipo: 't' text · 'i' integer · 'n' numeric
# 🔒 Los nombres de destino son los que YA usan las otras tablas para lo mismo
#    (`salud_fba`): available, fc_transfer, inbound_shipped, inbound_working,
#    inbound_receiving, total_reserved_quantity, unfulfillable_quantity,
#    total_quantity, your_price, product_name, sku, fnsku, asin, condition.
#    Dos nombres distintos para el mismo dato son dos verdades esperando a
#    discrepar.
# 🔒 El encabezado se compara EXACTO (sin BOM, sin espacios). Si uno no aparece
#    → Guarda 1 ABORTA. No se conjetura (la regla que mató al PR #26).
# ---------------------------------------------------------------------------
TIPADAS = [
    # Identidad
    ('sku',                             'sku',                     't'),
    ('fnsku',                           'fnsku',                   't'),
    ('asin',                            'asin',                    't'),
    ('product-name',                    'product_name',            't'),
    ('condition',                       'condition',               't'),
    # Stock en la estantería
    ('afn-warehouse-quantity',          'warehouse_quantity',      'i'),
    ('afn-fulfillable-quantity',        'available',               'i'),
    ('afn-unsellable-quantity',         'unfulfillable_quantity',  'i'),
    ('afn-reserved-quantity',           'total_reserved_quantity', 'i'),
    ('afn-total-quantity',              'total_quantity',          'i'),
    ('afn-fc-transfer-quantity',        'fc_transfer',             'i'),
    # 🔬 El disponible CALCULADO POR AMAZON. Medido el 6-sep-2026 sobre las 381
    #    filas: = afn-fulfillable-quantity + afn-fc-transfer-quantity, 381 de 381,
    #    desvío 0 (6.692 = 6.437 + 255). O sea que Amazon manda su propia suma y
    #    coincide al dígito con el criterio de la casa. Se guarda como TESTIGO
    #    INDEPENDIENTE: el día que discrepe de nuestra suma, o Amazon se contradice
    #    o hemos entendido mal el reparto de estados, y las dos cosas hay que verlas.
    # ⚠️ Llevaba MESES llegando en el .txt sin guardarse en ninguna columna (sólo
    #    caía en `crudo`), así que nadie sabía que estaba. De ahí la Guarda 11.
    ('afn-onhand-buyable-quantity',     'onhand_buyable',          'i'),
    # 🔑 EN TRÁNSITO — la razón de ser de esta cañería
    ('afn-inbound-working-quantity',    'inbound_working',         'i'),
    ('afn-inbound-shipped-quantity',    'inbound_shipped',         'i'),
    ('afn-inbound-receiving-quantity',  'inbound_receiving',       'i'),
    # Precio
    ('your-price',                      'your_price',              'n'),
    # 🔴 El testigo de que el informe sigue siendo el total europeo. Vacío en las
    #    356 filas de hoy; si algún día trae valor, se ve EN EL DATO, no sólo en
    #    el log (Guarda 9).
    ('store',                           'store',                   't'),
]
TIPO_SQL = {'t': 'text', 'i': 'integer', 'n': 'numeric'}

# ---------------------------------------------------------------------------
# EL CONTRATO, PARTIDO EN DOS. Lo que ABORTA y lo que se ECHA EN FALTA.
# ---------------------------------------------------------------------------
# 🔴 POR QUÉ SE PARTE, con la fecha y el fichero: el 7-sep-2026 Amazon sirvió el
#    informe con 24 columnas en vez de 26 (`50740020703.txt`). Faltaban
#    `afn-fc-transfer-quantity` y `afn-onhand-buyable-quantity`, insertadas sin
#    avisar antes de `store` (issue amzn/selling-partner-api-models #5289). La
#    Guarda 1 abortó por la primera y la carga diaria se paró en seco.
#
# 🔑 LA DECISIÓN: esas dos salen de las OBLIGATORIAS y pasan a ESPERADAS. Que
#    falten NO aborta — pero tampoco se rellenan por nuestra cuenta.
#
# 🔴 Y LO QUE **NO** SE HACE, que es lo importante: cuando falta
#    `afn-fc-transfer-quantity`, `fc_transfer` queda **NULL en todas las filas de
#    esa carga**, JAMÁS 0. Un 0 dice «no hay nada moviéndose entre centros»; NULL
#    dice «este informe no lo ha dicho». La diferencia son ~250 unidades de stock
#    real que existen y no se ven.
#    ⚠️ Se probó a DEDUCIRLO restando (almacén − vendible − inservible − reservado
#       − investigando) y **está medido que no vale**: en el fichero de 24 columnas
#       esa resta da 0 en las 381 filas, porque el almacén tampoco trae ya el
#       tránsito. Se probó también a reconstruirlo desde el informe internacional
#       y **también está medido que no vale**: acierta en 298 de 313 fichas con
#       tránsito, pero INVENTA 2.107 unidades en 162 fichas que no lo tienen.
#       Una fuente que inventa más de lo que acierta no es una fuente.
#    🔑 La conclusión, escrita para que no haya que volver a descubrirla: **el
#       tránsito entre centros no se deduce. O lo dice un informe, o no se sabe.**
ESPERADAS = {
    'afn-fc-transfer-quantity',
    'afn-onhand-buyable-quantity',
}
# 🔒 Las OBLIGATORIAS, que son las que mira la Guarda 1 y las que ABORTAN. La
#    guarda no ha cambiado ni una línea: ha cambiado la lista que se le da.
CABECERA_ESPERADA = [h for h, _, _ in TIPADAS if h not in ESPERADAS]

# La cabecera de la que sale `fc_transfer`. Se nombra una vez porque hay tres
# sitios que preguntan por ella, y un literal repetido tres veces es un fallo
# esperando a que alguien corrija sólo dos.
HEADER_FC = 'afn-fc-transfer-quantity'

# ---------------------------------------------------------------------------
# LAS DERIVADAS — no salen de ninguna columna del .txt: las escribe el procesador.
# ---------------------------------------------------------------------------
# 🔴 SIN ESTO, `fc_transfer` MIENTE POR OMISIÓN. Un 12 leído del informe y un NULL
#    porque el informe no lo trajo son cosas distintas, y dentro de la columna son
#    indistinguibles. Quien mire el disponible dentro de tres días tiene derecho a
#    saber de dónde sale cada cifra — y, sobre todo, cuándo NO sale de ningún sitio.
#      · 'informe'     → lo dijo Amazon en el .txt de ese día.
#      · 'desconocido' → el informe no traía la columna. `fc_transfer` es NULL.
# 🔑 No hay un tercer valor, y es a propósito: se retiró la reconstrucción desde
#    el informe internacional porque inventaba stock (ver ESPERADAS).
DERIVADAS = [
    ('fc_transfer_origen', 'text'),
    # ── EL PUENTE: qué se puede comprar cuando el informe no dice el tránsito ──
    # 🔴 NO SUSTITUYE A NADA Y EL PRECIO NO LO TOCA. `fc_transfer` sigue siendo
    #    NULO cuando no se sabe, y `available` sigue siendo `available`. Esto es
    #    una columna MÁS, para la pantalla de reposición y de cobertura.
    ('disponible_estimado',     'integer'),
    ('disponible_origen',       'text'),
    ('disponible_fuente_fecha', 'date'),
]

# ---------------------------------------------------------------------------
# EL MODELO DEL DISPONIBLE — y por qué esto NO es una constante en el código.
# ---------------------------------------------------------------------------
# 🔴 LA CAUSA RAÍZ DE TODO ESTO, que no es una avería (aviso oficial de Amazon en
#    la página del informe, leído el 7-sep-2026): **las unidades en «Transferencia
#    entre centros logísticos» han dejado de considerarse reservadas, porque ahora
#    son COMPRABLES.** El cambio ya está hecho en la web y llega a la API «a
#    finales de 2026». Por eso desapareció `afn-fc-transfer-quantity` del informe,
#    y por eso desapareció también del informe de Inventario Reservado: la columna
#    no se ha roto, el concepto se está mudando de sitio.
#
# 🔑 LA CONSECUENCIA, que es la que muerde: hoy el disponible es
#        vendible + tránsito          (el tránsito va APARTE y se suma)
#    y el día que Amazon complete el cambio pasará a ser
#        vendible                     (el tránsito ya está DENTRO del vendible)
#    Seguir sumando ese día contaría DOBLE unas 250 unidades. Y contar doble el
#    disponible no da un error: da una cifra creíble con la que se decide reponer y
#    se decide precio.
#
# 🔒 POR ESO EL MODELO SE DECIDE POR VERSIÓN DEL INFORME Y SE GUARDA CON LA FOTO,
#    no se fija en una constante. Una constante habría que acordarse de cambiarla
#    el día justo, y ese día nadie va a estar mirando. Además, con el modelo
#    anotado en el censo, la serie del histórico se puede leer hacia atrás sabiendo
#    bajo qué regla se escribió cada fotograma.
#
# ⚠️ HOY SOLO ESTÁ LA PUERTA, NO EL MODELO NUEVO, y es a propósito. Medido el
#    7-sep-2026: si las unidades ya estuvieran dentro del vendible, el vendible
#    habría subido ~255 de golpe. Subió **+16** (6.437 → 6.453). O sea que el
#    tránsito de hoy no está dentro del vendible: sencillamente no está en el
#    informe. Eso es 'desconocido', no el modelo nuevo. Quien encienda
#    MODELO_TRANSITO_DENTRO tendrá que medirlo antes, y la Guarda 13 es la que
#    avisará de que ha llegado el día.
MODELO_TRANSITO_APARTE = 'transito_aparte'        # disponible = vendible + transito
MODELO_TRANSITO_DENTRO = 'transito_dentro'        # disponible = vendible (ya lo lleva)
MODELO_TRANSITO_DESCONOCIDO = 'transito_desconocido'   # el informe no lo dice

# ---------------------------------------------------------------------------
# EL CATÁLOGO DE MODELOS CONOCIDOS — Guarda 14. Dos formas, y ninguna más.
# ---------------------------------------------------------------------------
# 🔴 QUÉ CAMBIA HOY (7-sep-2026, encargo F paso 4): **el informe de 24 columnas
#    deja de ser «un informe roto» y pasa a ser un MODELO CONOCIDO.** Hasta ahora
#    entraba por descarte: cualquier cabecera que no llevase `afn-fc-transfer-quantity`
#    se leía como «tránsito desconocido», viniera de donde viniera. O sea que un
#    informe con veinte columnas mal, o con las columnas movidas de sitio, habría
#    entrado exactamente igual que el degradado del 7-sep.
#
# 🔑 LO QUE ESTO CATALOGA ES LA CABECERA ENTERA Y EN SU ORDEN, no la presencia de
#    dos columnas. Se comparan las 26 (o las 24) con `==`. Si Amazon quita, añade o
#    MUEVE una tercera columna, esto no la reconoce y la Guarda 14 para la carga.
#
# ⚠️ Y SÍ, ESTO APRIETA UNA DECISIÓN QUE ANTES ERA MÁS FLOJA. En la Guarda 11 está
#    escrito que «sobrar NO aborta», porque el fichero se lee por NOMBRE de columna
#    y una de más no desplaza nada — y eso sigue siendo cierto para LEER. Lo que ha
#    cambiado es lo que sabemos: el 7-sep Amazon movió el significado de una columna
#    sin cambiarle el nombre, y una cabecera que no reconocemos ya no es «una columna
#    de adorno», es un informe del que no sabemos qué está contando. Durante el mes
#    que le queda a esta cañería —después entra la API—, parar y mirar cuesta menos
#    que una cifra creíble y falsa.
# 🔒 La puerta tiene nombre, como las otras: PERMITIR_MODELO_NUEVO=1. Entonces el
#    modelo se decide por presencia (la regla vieja) y se GRITA que se ha entrado
#    por una forma que nadie ha catalogado.
#
# 🔬 De dónde sale la lista: es la cabecera literal del .txt real, la misma que
#    `test_inventario_fba.py` tiene copiada aparte desde el 23-ago-2026. Las dos se
#    cotejan en el test — si sólo viviera aquí, el test estaría comprobando este
#    fichero contra sí mismo.
MODELO_26 = (
    'sku', 'fnsku', 'asin', 'product-name', 'condition', 'your-price',
    'mfn-listing-exists', 'mfn-fulfillable-quantity', 'afn-listing-exists',
    'afn-warehouse-quantity', 'afn-fulfillable-quantity', 'afn-unsellable-quantity',
    'afn-reserved-quantity', 'afn-total-quantity', 'per-unit-volume',
    'afn-inbound-working-quantity', 'afn-inbound-shipped-quantity',
    'afn-inbound-receiving-quantity', 'afn-researching-quantity',
    'afn-reserved-future-supply', 'afn-future-supply-buyable',
    'afn-fulfillable-quantity-local', 'afn-fulfillable-quantity-remote',
    'afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity', 'store',
)
# 🔒 El degradado se DERIVA quitando las dos esperadas, no se retecla: dos listas
#    escritas a mano se separan en cuanto una cambia, y entonces el catálogo miente.
MODELO_24 = tuple(h for h in MODELO_26 if h not in ESPERADAS)

MODELOS_CONOCIDOS = {
    MODELO_26: MODELO_TRANSITO_APARTE,
    MODELO_24: MODELO_TRANSITO_DESCONOCIDO,
}
NOMBRE_MODELO = {
    MODELO_26: 'el largo (26 columnas, con el transito)',
    MODELO_24: 'el corto (24 columnas, sin el transito), el que sirve Amazon desde el 7-sep-2026',
}


def modelo_del_disponible(cabecera):
    """Bajo qué regla se lee el disponible con ESTA cabecera. None = no catalogada.

    🔑 Ésta es la ÚNICA puerta. El día que Amazon complete el cambio, aquí —y sólo
       aquí— se cataloga la cabecera nueva con MODELO_TRANSITO_DENTRO. Ninguna otra
       parte del procesador decide esto.
    """
    return MODELOS_CONOCIDOS.get(tuple(cabecera))


def _diferencias(cabecera, modelo):
    """(faltan, sobran, movidas) de `cabecera` respecto de un modelo del catálogo."""
    faltan = [h for h in modelo if h not in cabecera]
    sobran = [h for h in cabecera if h not in modelo]
    movidas = (not faltan and not sobran and tuple(cabecera) != tuple(modelo))
    return faltan, sobran, movidas


def guarda_modelo_conocido(cabecera, permitir=None, escribir=print):
    """Guarda 14: la cabecera tiene que ser uno de los dos modelos catalogados.

    🔒 Función PURA: entra una lista de encabezados, sale el modelo o un Aborta.
    """
    if permitir is None:
        permitir = os.environ.get('PERMITIR_MODELO_NUEVO') == '1'
    modelo = modelo_del_disponible(cabecera)
    if modelo is not None:
        return modelo

    detalle = []
    for conocido in (MODELO_26, MODELO_24):
        faltan, sobran, movidas = _diferencias(cabecera, conocido)
        trozos = []
        if faltan:
            trozos.append("le faltan %d (%s)" % (len(faltan), ", ".join(faltan)))
        if sobran:
            trozos.append("le sobran %d (%s)" % (len(sobran), ", ".join(sobran)))
        if movidas:
            trozos.append("trae las mismas columnas pero CAMBIADAS DE ORDEN")
        detalle.append("     - contra %s: %s"
                       % (NOMBRE_MODELO[conocido], "; ".join(trozos) or "?"))

    cuerpo = (
        "[Guarda 14] La cabecera de este informe NO es ninguno de los dos modelos "
        "conocidos.\n"
        "   Trae %d encabezados: %s\n%s\n"
        "   Los dos catalogados son el de 26 columnas y el de 24 (el degradado que "
        "Amazon sirve desde el 7-sep-2026). Cualquier otra forma para la carga: no "
        "sabemos que esta contando, y un informe que cuenta otra cosa no da un error, "
        "da una cifra creible.\n"
        "   QUE HAY QUE HACER: mirar el .txt, decidir que significa la forma nueva y "
        "CATALOGARLA en MODELOS_CONOCIDOS con su modelo de disponible."
        % (len(cabecera), list(cabecera), "\n".join(detalle)))

    if permitir:
        escribir("")
        escribir("AVISO  " + cuerpo)
        escribir("   PERMITIR_MODELO_NUEVO=1 la salta: el modelo se decide por "
                 "presencia de la columna del transito, que es la regla vieja.")
        escribir("   Que conste, y que se mire.")
        escribir("")
        return MODELO_TRANSITO_APARTE if HEADER_FC in cabecera else MODELO_TRANSITO_DESCONOCIDO
    raise Aborta(cuerpo + "\n   (Si hay que cargarlo YA y se asume el riesgo: "
                          "PERMITIR_MODELO_NUEVO=1.)")
DERIVADAS_COLS = [c for c, _ in DERIVADAS]
ORIGEN_INFORME = 'informe'
ORIGEN_DESCONOCIDO = 'desconocido'

# ---------------------------------------------------------------------------
# EL PUENTE — de dónde sale el disponible cuando el informe no trae el tránsito.
# ---------------------------------------------------------------------------
# 🔴 PRIMERO, LO QUE **NO** ES. No es una fuente de stock: `inventario_internacional`
#    NO manda sobre `inventario_fba` (Stock 6 sigue vigente). No sustituye a
#    `available` ni a `fc_transfer`, que se siguen guardando tal cual y en columnas
#    separadas (Stock 1-2). Y **el precio no lo toca**: la sesión de precios usa el
#    disponible LEÍDO, y si no lo hay, la ficha no entra. Esto lo lee la pantalla
#    de reposición y de cobertura, y nadie más.
#
# 🔑 LA FÓRMULA, y por qué tiene esa forma:
#        disponible_estimado = available + max(0, internacional − entrantes − available)
#    que es lo mismo que `max(available, internacional − entrantes)` pero escrito
#    de modo que se vea el suelo: **el vendible nunca se pierde**. El internacional
#    sólo puede AÑADIR por encima, jamás quitar.
#    · Se restan los ENTRANTES porque el internacional los cuenta y el vendible no:
#      sin esa resta se sumaría dos veces la mercancía que va de camino.
#    · Y se toma el máximo con `available` porque el internacional puede ir
#      atrasado; el vendible del propio informe es siempre un suelo cierto.
#
# 🔬 MEDIDO SOBRE LA VERDAD GUARDADA (11 días, 4.042 filas sku-día del histórico,
#    donde `fc_transfer` sí venía leído y por tanto hay contra qué medir):
#        sólo el vendible            → error 3.080 uds, y SIEMPRE corto
#        este puente                 → error 549 uds
#      de las 2.530 filas con estimación, CLAVA 2.425 (95,8%);
#      se pasa en 78 (487 uds, máximo 23 en una ficha) y se queda corto en 27 (62 uds).
#    ⚠️ Y lo que parecía «inflado» no lo es: son unidades de ALEMANIA que el informe
#       FBA no reporta (`B08KJTM337`: 84 en el informe, 84+23 en el internacional los
#       once días), y tránsito que el informe pierde y el internacional sí ve
#       (`B0D6CXB8J1`, contrastado contra la pantalla del Seller el 7-sep). El puente
#       CORRIGE; no infla.
#
# 🔴 LO QUE NO SE ESTIMA SE DICE, NO SE RELLENA. Sin fila de ese ASIN en el
#    internacional, `disponible_estimado` queda a NULO y el origen es 'desconocido'.
#    Nunca un 0 por defecto (Stock 8). Y está medido que eso cuesta poco: de las
#    1.512 filas que caen en 'desconocido', **sólo 3 tienen stock**. El puente falta
#    justo donde no hace falta.
#
# 🔒 SE ESTIMA SIEMPRE QUE SE PUEDE, TAMBIÉN LOS DÍAS EN QUE EL TRÁNSITO SÍ VIENE,
#    y esto es una decisión mía que conviene ver: así el estimado y la verdad
#    conviven en la misma fila y el error del puente se puede medir CADA DÍA, en vez
#    de descubrirlo el día que haga falta. `disponible_origen` dice cuál manda.
ORIGEN_LEIDO = 'leido'          # el informe trajo el tránsito: available + fc_transfer
ORIGEN_ESTIMADO = 'estimado'    # no lo trajo, y el internacional permite estimarlo


def _reparto(excedente, pesos):
    """Reparte `excedente` entre `pesos` sin perder ni inventar una unidad.

    🔴 Restos mayores, no `round()` a secas: redondear cada parte por su cuenta
       hace que la suma de las partes NO sea el total (dos fichas con 0,5 dan 1+1=2
       donde había 1). Aquí lo que se reparte es STOCK: una unidad que aparece o
       desaparece en el reparto es una unidad que no existe o que se pierde.
    🔒 El desempate es la POSICIÓN en `pesos`, y quien llama las ordena por `sku`:
       así el reparto de esta función y el de la migración de relleno coinciden.
    """
    total = sum(pesos)
    if total <= 0:
        return None
    # 🔴 ARITMÉTICA ENTERA, no coma flotante, y no es purismo: el resto exacto es
    #    `(excedente*peso) mod total`, y así es como lo calcula la migración de
    #    relleno en SQL. Con floats, dos restos exactos distintos pueden redondear
    #    al mismo número y el desempate cambiar de ficha — o sea, las dos cañerías
    #    escribiendo repartos distintos del MISMO día.
    numeradores = [excedente * p for p in pesos]
    partes = [n // total for n in numeradores]
    restos = [n % total for n in numeradores]
    faltan = excedente - sum(partes)
    # Las que más resto tienen se llevan la unidad suelta, en orden estable.
    orden = sorted(range(len(pesos)), key=lambda i: (-restos[i], i))
    for i in orden[:faltan]:
        partes[i] += 1
    return partes


def estimar_disponible(filas, intl, fecha_foto=None, escribir=print):
    """Rellena disponible_estimado / _origen / _fuente_fecha. Devuelve el resumen.

    🔒 Función PURA: `intl` es {asin: (unidades, fecha_foto)}, ya leído de la base
       por quien llame. Así se prueba sin base y sin red.

    🔑 El reparto entre SKU de un mismo ASIN (fichas commingled) va en proporción al
       vendible de cada uno. Medido en 11 días: 13 casos commingled y NINGUNO con
       excedente, o sea que hoy este reparto no mueve un solo dato — que es el mejor
       momento para escribirlo bien. El caso que no se puede repartir (varios SKU y
       vendible 0 en todos) tampoco ha pasado nunca: se deja en 'desconocido' y se
       GRITA, jamás se parte a ojo.
    """
    por_asin = {}
    for f in filas:
        por_asin.setdefault(f['registro']['asin'], []).append(f)
    # 🔒 ORDEN ESTABLE POR SKU, y no es cosmética: el desempate de los restos
    #    mayores decide qué ficha se lleva la unidad suelta. Si el orden fuera el
    #    del fichero, la migración de relleno —que ordena por `sku`, porque en SQL
    #    no existe «el orden del .txt»— escribiría un reparto distinto del que
    #    escribe esta función. Dos verdades para el mismo día.
    for grupo in por_asin.values():
        grupo.sort(key=lambda r: r['registro']['sku'])

    resumen = {'leido': 0, 'estimado': 0, 'desconocido': 0,
               'sin_intl': 0, 'sin_reparto': [], 'fuente_mas_vieja': None,
               'aporta_uds': 0, 'discrepa': [],
               # 🔴 EL FALLO SILENCIOSO QUE ESTO CIERRA (punto 4 del encargo F,
               #    7-sep-2026): cuando el internacional NO es del mismo día que este
               #    informe, el disponible se estima con una foto VIEJA y hasta hoy
               #    nada lo decía. Medido ese día en producción: el internacional
               #    tiene 21 fotos entre el 23-jul y el 7-sep, con huecos de hasta 7
               #    días, PERO los 11 días del histórico del inventario caen todos en
               #    días que SÍ tienen internacional, así que el desfase es 0 en los 12
               #    casos guardados. O sea que esto no ha pasado NUNCA todavía — que es
               #    exactamente el momento de ponerle el aviso, porque el día que uno de
               #    los dos informes llegue sin el otro, la cifra saldrá igual de
               #    creíble y será de otro día.
               'fuente_vieja': 0, 'fuente_dias': None}

    for asin, grupo in por_asin.items():
        uds_intl, fecha_intl = intl.get(asin, (None, None))
        av = [r['registro']['available'] for r in grupo]
        ent = sum(r['registro']['inbound_working'] + r['registro']['inbound_shipped']
                  + r['registro']['inbound_receiving'] for r in grupo)
        excedente = None
        if uds_intl is not None:
            excedente = max(0, uds_intl - ent - sum(av))

        partes = None
        if excedente is None:
            resumen['sin_intl'] += len(grupo)
        elif excedente == 0:
            partes = [0] * len(grupo)          # el vendible es el suelo y basta
        elif sum(av) > 0:
            partes = _reparto(excedente, av)
        elif len(grupo) == 1:
            partes = [excedente]               # una sola ficha: todo suyo
        else:
            # 🔴 Varios SKU, ninguno con vendible: no hay proporcion con la que
            #    repartir. No se parte a ojo — se dice que no se sabe.
            resumen['sin_reparto'].append((asin, len(grupo), excedente))

        for r, vendible, parte in zip(grupo, av,
                                      partes if partes is not None else [None] * len(grupo)):
            reg = r['registro']
            if parte is None:
                reg['disponible_estimado'] = None
                reg['disponible_fuente_fecha'] = None
            else:
                reg['disponible_estimado'] = vendible + parte
                reg['disponible_fuente_fecha'] = fecha_intl
                resumen['aporta_uds'] += parte
                if fecha_foto is not None and fecha_intl != fecha_foto:
                    resumen['fuente_vieja'] += 1
                    resumen['fuente_dias'] = (fecha_foto - fecha_intl).days
                if (resumen['fuente_mas_vieja'] is None
                        or fecha_intl < resumen['fuente_mas_vieja']):
                    resumen['fuente_mas_vieja'] = fecha_intl

            if reg.get('fc_transfer') is not None:
                reg['disponible_origen'] = ORIGEN_LEIDO
                resumen['leido'] += 1
                # 🔬 El falsador permanente: los días que hay verdad, se compara.
                cierto = reg['available'] + reg['fc_transfer']
                if reg['disponible_estimado'] is not None and reg['disponible_estimado'] != cierto:
                    resumen['discrepa'].append(
                        (reg['sku'], reg['disponible_estimado'], cierto))
            elif reg['disponible_estimado'] is not None:
                reg['disponible_origen'] = ORIGEN_ESTIMADO
                resumen['estimado'] += 1
            else:
                reg['disponible_origen'] = ORIGEN_DESCONOCIDO
                resumen['desconocido'] += 1

    if resumen['fuente_vieja']:
        escribir("")
        escribir("  ==================================================================")
        escribir("  EL DISPONIBLE DE HOY SE ESTA ESTIMANDO CON UNA FOTO DE OTRO DIA.")
        escribir("  ==================================================================")
        escribir("    fichas afectadas : %d" % resumen['fuente_vieja'])
        escribir("    foto usada       : %s" % resumen['fuente_mas_vieja'])
        escribir("    esta carga es del: %s  (%d dia(s) despues)"
                 % (fecha_foto, resumen['fuente_dias']))
        escribir("")
        escribir("  El informe del almacen internacional y el de FBA llegan juntos, y por")
        escribir("  eso hasta hoy el desfase habia sido 0 en los 12 casos guardados. Si")
        escribir("  esto sale, uno de los dos NO ha entrado: el disponible que se escriba")
        escribir("  para estas fichas no es de hoy, y una cifra sin la fecha del dato que")
        escribir("  la sostiene miente. Carga el internacional del dia y repite.")
        escribir("")

    if resumen['sin_reparto']:
        escribir("")
        escribir("[Puente] %d ASIN con varios SKU y ninguno con vendible: no hay "
                 "proporcion con la que repartir, y NO se parte a ojo. Quedan en "
                 "«desconocido»:" % len(resumen['sin_reparto']))
        for asin, n, exc in resumen['sin_reparto'][:10]:
            escribir("        · %s · %d SKU · %d uds sin repartir" % (asin, n, exc))
        escribir("     Medido en 11 dias: esto no habia pasado nunca. Miralo.")
    return resumen

# ---------------------------------------------------------------------------
# EL HISTÓRICO (cajón PELÍCULA). Mismas columnas tipadas + fecha_foto y fichero.
# 🔴 SIN `crudo`, y es decisión: el .txt entero se conserva en
#    informes/inventario_fba/, así que la despensa común del histórico vive en el
#    Storage y no duplicada en la base. CONTRAPARTIDA: esos ficheros NO SE BORRAN
#    NUNCA — el rescate va por la columna `fichero`. (Mismo trato que los CSV de
#    Keepa desde el 29-jul-2026.)
# 🔑 La PK lleva `fecha_foto`: es lo que convierte la foto en fotograma. Sin ella
#    cada carga pisaría a la anterior y esto no sería una película.
# ---------------------------------------------------------------------------
HIST_PK = ('sku', 'fecha_foto')
HIST_COLS = (['sku', 'fecha_foto'] + [c for _, c, _ in TIPADAS if c != 'sku']
             + DERIVADAS_COLS + ['fichero'])

# Las numéricas que NO pueden faltar: son el inventario. Un hueco aquí no es un
# 0, es un informe que dejó de decir lo que decía → ABORTA (Guarda 6).
NUMERICAS = [(h, c, t) for h, c, t in TIPADAS if t in ('i', 'n')]

# Hoy el informe solo trae esto. Otro valor NO aborta: se GRITA (Guarda 9).
CONDITION_CONOCIDA = 'New'
AFN_LISTING_CONOCIDO = 'Yes'

# ---------------------------------------------------------------------------
# EL ÚNICO HUECO QUE NO ABORTA — y por qué es uno, no dos.
# ---------------------------------------------------------------------------
# 🔴 LA REGLA GENERAL NO SE TOCA: en las CANTIDADES, vacío no es 0 y un hueco
#    ABORTA (Guarda 6). Las quince cantidades siguen exactamente igual.
#
# 🔑 `your-price` NO ES UNA CANTIDAD, y ahí se rompe la analogía. Un precio
#    ausente significa «esta ficha no tiene precio puesto», que es un estado
#    normal de un listing (cerrado, sin oferta, en revisión). No es stock, no
#    entra en ninguna suma de unidades, y no puede tumbar la carga del inventario
#    de un almacén entero.
#
# 🔬 EL CASO QUE LO TRAE, medido en `50740020703.txt` el 7-sep-2026:
#      sku XQ-QJXG-7UQ1 (ASIN B0D98V7WQ6) · your-price VACÍO · condition 'Unknown'
#      · 0 unidades en las cinco cantidades de stock.
#    Ayer esa misma ficha traía 'New' y 25,95 €. **1 fila de 381.** Con la regla
#    vieja, esa fila sola habría impedido cargar las otras 380.
#
# 🔴 VA A NULL, NO A 0. Un `your_price = 0` sería un precio de cero euros, y eso
#    es una mentira con consecuencias: la rentabilidad se calcula sobre él.
# 🔑 Y SE GRITA, con sku y ASIN: un precio que desaparece es una ficha que ha
#    cambiado de estado en Amazon, y eso se mira.
#
# ⚠️ Es una LISTA, no un `if` suelto, para que meter otra columna en la excepción
#    sea una decisión visible y no un parche escondido dentro del bucle.
VACIO_ES_NULO = {'your-price'}


def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()


def cabecera_de(texto):
    """Sólo la cabecera del .txt, sin parsear el resto. [] si no hay ni una línea.

    🔑 EXISTE PARA LA LIBRETA, y ése es todo el motivo. Cuando `analizar()` aborta
       —que es lo que pasó el 7-sep-2026— no devuelve nada, así que sin esto no habría
       con qué anotar en `inventario_fba_cabecera` qué forma tenía el informe que se
       rechazó. Y la carga que se rechaza es justo la que hay que dejar escrita.
    🔒 Por `leer_tsv`, el mismo lector que el resto del fichero: la cabecera se lee
       igual que los datos o algún día dirán cosas distintas.
    """
    primera = texto.split('\n', 1)[0]
    for fila in leer_tsv(primera):
        return [_clean(c) for c in fila]
    return []


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..9). Sin tocar la base todavía.
#    🔒 Función PURA: entra texto, sale un dict o un Aborta. Por eso se puede
#       probar de verdad en `test_inventario_fba.py` sin base ni red — y por eso
#       cada guarda se puede ver ROJA rompiendo el fichero a mano.
# ---------------------------------------------------------------------------
def analizar(texto, fichero, fecha_foto, umbral_filas=None):
    if umbral_filas is None:
        umbral_filas = UMBRAL_FILAS

    # 🔒 Por `leer_tsv`, no por `csv.reader` a pelo: ver la cabecera del fichero.
    filas = [f for f in leer_tsv(texto) if any((c or '').strip() for c in f)]

    # Guarda 2: anti-vacío (≥1 fila de datos)
    if len(filas) < 2:
        raise Aborta("[Guarda 2] 0 filas de datos (fichero vacío o no es TAB-separated). "
                     "Abortando.")

    cabecera = [_clean(c) for c in filas[0]]
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)

    # Guarda 1: los encabezados EXACTOS existen (§0: no se conjetura, se ABORTA)
    faltan = [h for h in CABECERA_ESPERADA if h not in idx]
    if faltan:
        raise Aborta(
            "[Guarda 1] Encabezado(s) que NO aparecen EXACTOS en el .txt "
            "(regla que mató al PR #26: se ABORTA, no se aproxima):\n   · "
            + "\n   · ".join(repr(h) for h in faltan)
            + f"\n   Cabecera real ({len(cabecera)} cols): {cabecera}")

    # Guarda 14: y además la cabecera ENTERA tiene que ser un modelo catalogado.
    # 🔑 Va justo detrás de la Guarda 1 y no al final: si el informe ha cambiado de
    #    forma, no tiene sentido seguir midiendo sus filas. La Guarda 1 mira que estén
    #    las obligatorias; ésta mira que no haya nada más, ni de menos, ni movido.
    modelo = guarda_modelo_conocido(cabecera)

    filas_datos = filas[1:]

    # Guarda 3: FILAS DENTADAS = FICHERO CORTADO A MEDIA LÍNEA.
    # 🔴 Éste es el detector de truncamiento que a salud_fba le faltó, y no es un
    #    número inventado: es el ancho que declara la propia cabecera. Un fichero
    #    que Amazon corta en mitad de un envío deja la última fila con menos
    #    columnas — y sin esta guarda entraría con esa fila a medias dentro.
    dentadas = [(pos + 2, len(f)) for pos, f in enumerate(filas_datos)
                if len(f) != len(cabecera)]
    if dentadas:
        muestra = ", ".join(f"fila {n} tiene {c} col." for n, c in dentadas[:5])
        raise Aborta(
            f"[Guarda 3] {len(dentadas)} fila(s) con un número de columnas distinto de "
            f"las {len(cabecera)} que declara la cabecera: {muestra}"
            + ("…" if len(dentadas) > 5 else "")
            + "\n   Un TSV al que le faltan columnas en una fila es un fichero CORTADO a "
              "media línea. Es exactamente lo que Amazon lleva sirviendo en salud_fba "
              "desde el 16-ago. No se carga a medias: abortando.")

    # Guarda 4: UMBRAL DE FILAS (ver el bloque UMBRAL_FILAS arriba para el porqué
    # del número). Es el suelo ABSOLUTO: la anti-encogimiento es relativa y no
    # protege la PRIMERA carga, cuando la tabla está vacía y no hay contra qué
    # comparar — una comprobación sin nada que comparar no comprueba nada (§3).
    if len(filas_datos) < umbral_filas:
        if os.environ.get('PERMITIR_UMBRAL_BAJO') == '1':
            print(f"\n⚠️  [Guarda 4] {len(filas_datos)} filas, por debajo del umbral de "
                  f"{umbral_filas} — PERMITIR_UMBRAL_BAJO=1 la salta. Que conste.",
                  flush=True)
        else:
            raise Aborta(
                f"[Guarda 4] El fichero trae {len(filas_datos)} filas de datos y el umbral "
                f"son {umbral_filas}.\n"
                f"   Un informe pequeño y uno ROTO se parecen mucho, y ésa es justo la "
                f"razón por la que salud_fba se cayó: los ficheros truncados que Amazon "
                f"sirve desde el 16-ago traen 37 filas contra las 219 del sano.\n"
                f"   Un informe caducado o a medias no da información incompleta: da "
                f"información FALSA. No se escribe nada.\n"
                f"   (Si el catálogo ha encogido DE VERDAD y esto es correcto: "
                f"PERMITIR_UMBRAL_BAJO=1.)")

    def celda(fila, h):
        i = idx.get(h)
        if i is None or i >= len(fila):
            return ''
        return _clean(fila[i])

    salida = []
    vistos = {}
    duplicadas = []
    condiciones_raras = Counter()
    listing_raro = Counter()
    stores_con_valor = Counter()
    precios_vacios = []            # (sku, asin) de las fichas que llegan sin precio
    esperadas_vacias = Counter()   # la cabecera vino, pero la celda estaba en blanco
    onhand_discrepa = []           # (sku, lo que dice Amazon, lo que sale de sumar)

    # 🔑 QUÉ ESPERADAS NO HAN VENIDO. Se decide UNA VEZ, por la cabecera, no fila a
    #    fila: o la columna está en el informe o no está. Si no está, su valor es
    #    NULL en las 381 filas — nunca 0 (ver el bloque ESPERADAS).
    esperadas_ausentes = sorted(h for h in ESPERADAS if h not in idx)
    fc_origen = ORIGEN_INFORME if HEADER_FC in idx else ORIGEN_DESCONOCIDO

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 cabecera, +1 para numerar desde 1

        sku = celda(fila, 'sku')

        # Guarda 5: la PK debe venir. Una clave vacía no puede decidir qué se
        # borra ni qué se escribe.
        if sku == '':
            raise Aborta(f"[Guarda 5] Fila {num_fila}: 'sku' vacío. Es la PK de la foto: "
                         f"sin ella no se sabe qué fila se está reemplazando. Abortando.")
        if sku in vistos:
            duplicadas.append(f"{sku} — filas {vistos[sku]} y {num_fila}")
        else:
            vistos[sku] = num_fila

        registro = {}
        for h, db_col, tipo in TIPADAS:
            # 🔴 La ESPERADA que no viene queda a NULL, no a 0. Aquí no se aborta:
            #    para eso están las obligatorias y su Guarda 1, que no se ha tocado.
            if h in ESPERADAS and h not in idx:
                registro[db_col] = None
                continue
            bruto = celda(fila, h)
            if tipo == 't':
                registro[db_col] = bruto or None
                continue

            # Guarda 6: las numéricas del inventario no pueden venir vacías ni
            # ser basura. 🔴 Vacío NO es 0: un 0 dice "no hay"; un hueco dice
            # "este informe ya no contesta a esta pregunta", y son cosas
            # distintas. (Medido: hoy las 15 numéricas tipadas vienen llenas en
            # las 356 filas; los huecos del fichero están en columnas que NO se
            # tipan — mfn-fulfillable-quantity, store, afn-researching-quantity.)
            if bruto == '' and h in VACIO_ES_NULO:
                # 🔑 El precio ausente NO tumba la carga: va a NULL y se GRITA con
                #    sku y ASIN (ver el bloque VACIO_ES_NULO). Las cantidades, que
                #    son las de abajo, siguen abortando exactamente igual.
                registro[db_col] = None
                precios_vacios.append((sku, celda(fila, 'asin')))
                continue
            if bruto == '' and h in ESPERADAS:
                # La cabecera vino pero la celda está en blanco: NULL y se cuenta.
                registro[db_col] = None
                esperadas_vacias[h] += 1
                continue
            if bruto == '':
                raise Aborta(
                    f"[Guarda 6] Fila {num_fila} (sku {sku}): '{h}' viene VACÍA. "
                    f"En este informe las cantidades llegan siempre con valor (un 0 es "
                    f"un 0); un hueco significa que el informe ha dejado de contestar a "
                    f"esa pregunta, y eso no se rellena por nuestra cuenta. Abortando.")
            try:
                valor = int(bruto) if tipo == 'i' else float(bruto)
            except ValueError:
                raise Aborta(
                    f"[Guarda 6] Fila {num_fila} (sku {sku}): '{h}' no es un número: "
                    f"{bruto!r}. Abortando.")
            if valor < 0:
                raise Aborta(
                    f"[Guarda 6] Fila {num_fila} (sku {sku}): '{h}' = {valor} (negativo). "
                    f"Ni el stock ni el precio pueden serlo. Abortando.")
            registro[db_col] = valor

        # 🔴 DE DÓNDE SALE EL TRÁNSITO DE ESTA FILA. Se escribe SIEMPRE, también
        #    cuando es 'informe': una columna de trazabilidad que sólo se rellena
        #    en el caso raro obliga a adivinar qué significa el hueco.
        registro['fc_transfer_origen'] = fc_origen

        # 🔬 EL TESTIGO CONTRA EL CRITERIO DE LA CASA. Amazon manda su propio
        #    disponible (`onhand_buyable`) y aquí se suma el nuestro
        #    (available + fc_transfer). Medido el 6-sep-2026: iguales en las 381
        #    filas, desvío 0. Si algún día discrepan, o Amazon se contradice o
        #    hemos entendido mal el reparto de estados; se GRITA con las dos cifras,
        #    que es lo único que permite saber cuál de las dos falla.
        # 🔒 Sólo se contrasta cuando el tránsito se SABE: comparar contra un NULL
        #    leído como 0 daría una discrepancia falsa en cada fila.
        oh = registro.get('onhand_buyable')
        if oh is not None and registro.get('fc_transfer') is not None:
            nuestro = registro['available'] + registro['fc_transfer']
            if oh != nuestro:
                onhand_discrepa.append((sku, oh, nuestro))

        # Guarda 9 (grita, no aborta): lo que hoy es constante y mañana podría no
        # serlo. Los tres viven EN EL DATO (columnas condition y store), porque un
        # aviso que sólo vive en el log NO es un aviso.
        if registro['condition'] != CONDITION_CONOCIDA:
            condiciones_raras[registro['condition']] += 1
        afn = celda(fila, 'afn-listing-exists')
        if afn != AFN_LISTING_CONOCIDO:
            listing_raro[afn] += 1
        if registro['store']:
            stores_con_valor[registro['store']] += 1

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        salida.append({'registro': registro, 'crudo': crudo})

    # Guarda 5 (dup, informe final): el procesador NO elige entre dos filas.
    # 🔴 Aquí NO se deduplica, y es deliberado: un `sku` repetido en este informe
    #    significa que el fichero está contando algo que no entendemos (dos
    #    tiendas, dos vidas del mismo SKU). Deduplicar taparía justo lo que hay
    #    que gritar. Es el mismo criterio que salud_fba y keepa, no el de paneu.
    if duplicadas:
        raise Aborta("[Guarda 5] 'sku' duplicado dentro del fichero (es la PK; el "
                     "procesador NO elige con cuál se queda):\n   · "
                     + "\n   · ".join(duplicadas)
                     + "\n   Medido el 23-ago-2026: los 356 SKU del fichero real son "
                       "únicos. Si esto salta, el informe ha cambiado de forma — "
                       "míralo antes de forzar nada.")

    # ── Guarda 7: ANTI-CERO ────────────────────────────────────────────────
    # «¿Qué entrada concreta pondría este recuento a distinto de cero?» Si no la
    # hay, lo que parece un resultado no lo es (scripts/anti_cero.py).
    total_unidades = sum(f['registro']['total_quantity'] for f in salida)
    total_inbound  = sum(f['registro']['inbound_shipped'] for f in salida)

    if total_unidades == 0:
        raise Aborta(
            f"[Guarda 7] Las {len(salida)} filas suman 0 unidades en total. Un almacén con "
            f"{len(salida)} listings FBA activos y cero unidades no es un dato, es un "
            f"fichero roto. Abortando.")

    return {'filas': salida, 'fichero': fichero, 'fecha_foto': fecha_foto,
            'cabecera': cabecera,
            'esperadas_ausentes': esperadas_ausentes,
            'esperadas_vacias': esperadas_vacias,
            'fc_origen': fc_origen,
            'modelo_disponible': modelo,
            'inbound_total': sum(f['registro']['inbound_shipped'] for f in salida),
            'precios_vacios': precios_vacios,
            'onhand_discrepa': onhand_discrepa,
            # Las dos magnitudes que compara la Guarda 10. El VENDIBLE es el que
            # sobrevive a un cambio de versión del informe; el ALMACÉN no (el
            # 7-sep-2026 dejó de incluir el tránsito y cambió de significado).
            'vendible_total': sum(f['registro']['available'] for f in salida),
            'almacen_total': sum(f['registro']['warehouse_quantity'] for f in salida),
            'condiciones_raras': condiciones_raras, 'listing_raro': listing_raro,
            'stores_con_valor': stores_con_valor,
            'total_unidades': total_unidades, 'total_inbound': total_inbound,
            'asin_con_inbound': len({f['registro']['asin'] for f in salida
                                     if f['registro']['inbound_shipped'] > 0})}


# ---------------------------------------------------------------------------
# 🔴 LA MITAD DEL ANTI-CERO QUE **NO** ABORTA, Y POR QUÉ. Léelo antes de cambiarlo.
# ---------------------------------------------------------------------------
# El encargo pedía: «si inbound_shipped viene vacío o a cero en TODAS las filas,
# es un informe roto: rechaza». La primera mitad se cumple y aborta — pero por la
# Guarda 6, que es más estricta todavía: una celda numérica VACÍA, aunque sea una
# sola, ya para la carga. Un "nada en tránsito" legítimo llega como `0`, nunca en
# blanco.
#
# 🔬 LA SEGUNDA MITAD —todo a CERO— **NO ABORTA, Y ESTÁ MEDIDO POR QUÉ**: el
#    25-jul-2026 `salud_fba` cargó 218 filas con `inbound_shipped` = 0 en TODAS y
#    ni un nulo (consulta a `salud_fba_hist` en producción, 23-ago-2026). Era un
#    informe perfectamente sano de un día sin nada de camino. O sea que esa guarda,
#    escrita como pedía el encargo, **habría rechazado un informe bueno** — y
#    encima el día que más falta hace cargarlo, porque es el día en que la app
#    debe dejar de esperar mercancía.
#    Es el caso exacto de §3 de CLAUDE.md: *una comprobación que puede saltar por
#    una causa distinta de la que dice medir no es una guarda, es ruido futuro.*
#    Un aborto que salta en días legítimos se aprende a forzar, y el día que salte
#    de verdad nadie lo lee.
# 🔑 Así que se GRITA, muy fuerte y con el número delante, y la puerta al criterio
#    estricto tiene nombre para quien lo quiera: EXIGIR_INBOUND=1 lo convierte en
#    aborto. Lo que no se hace es elegir por Fernando y llamarlo guarda.
def avisar_inbound(info, escribir=print):
    """Grita si el fichero no trae NADA en tránsito. Devuelve True si gritó."""
    if info['total_inbound'] > 0:
        return False
    escribir("")
    escribir("  ==================================================================")
    escribir("  ESTE INFORME NO TRAE NI UNA UNIDAD EN TRANSITO.")
    escribir("  ==================================================================")
    escribir("    filas leidas          : %d" % len(info['filas']))
    escribir("    inbound_shipped total : 0  (en las %d filas)" % len(info['filas']))
    escribir("")
    escribir("  `inbound_shipped` es la UNICA razon por la que existe esta canieria:")
    escribir("  es lo que evita que la app mande a preparar un envio que ya salio.")
    escribir("  Si viene entero a cero, o no hay nada de camino (paso el 25-jul-2026:")
    escribir("  218 filas de salud_fba a cero, informe sano), o el informe ha dejado")
    escribir("  de contestar. Los dos son posibles y esto NO puede distinguirlos.")
    escribir("")
    escribir("  MIRALO antes de fiarte de la carga. (EXIGIR_INBOUND=1 lo convierte")
    escribir("  en aborto si prefieres que pare en seco.)")
    escribir("")
    if os.environ.get('EXIGIR_INBOUND') == '1':
        raise Aborta("[Guarda 7b] inbound_shipped a cero en todas las filas y "
                     "EXIGIR_INBOUND=1. Abortando a peticion.")
    return True


# ---------------------------------------------------------------------------
# GUARDA 11 — EL CENSO DE LA CABECERA. No aborta: se entera. Y decide.
# ---------------------------------------------------------------------------
# 🔴 POR QUÉ EXISTE, con el caso medido: `afn-onhand-buyable-quantity` llevaba
#    MESES llegando en el .txt y no se guardaba en ninguna columna —sólo caía en
#    `crudo`—, así que nadie sabía que estaba ahí. Cuando el 7-sep-2026
#    desapareció junto con `afn-fc-transfer-quantity`, tampoco nadie supo que se
#    había ido: la Guarda 1 abortó por la otra, porque sólo la otra estaba en el
#    contrato. **Un dato que llega y nadie censa es un dato que no llega.**
#
# 🔑 Y HACE UNA SEGUNDA COSA, que es la importante: define la VERSIÓN del informe.
#    El 7-sep `afn-warehouse-quantity` CAMBIÓ DE SIGNIFICADO —el 6-sep incluía el
#    tránsito entre centros y el 7-sep ya no— sin cambiar de nombre. Comparar el
#    almacén de una versión con el de la otra es comparar peras con manzanas, y de
#    eso salió una caída de 246 unidades que no era una caída. La Guarda 10 usa
#    este censo para saber si puede comparar el almacén o tiene que comparar otra
#    cosa. Sin censo, ese cambio de significado es INVISIBLE.
#
# 🔒 Sobrar NO aborta, y es una decisión medida: el fichero se lee por NOMBRE de
#    columna, no por posición. Por eso cuando Amazon insertó dos columnas EN MEDIO
#    (antes de `store`) no se desplazó nada y la carga cuadró 381/381.
def censo_cabecera(cabecera_nueva, cabecera_anterior):
    """(faltan, sobran) respecto a la carga anterior. Sin anterior, (None, None)."""
    if not cabecera_anterior:
        return None, None
    antes, ahora = set(cabecera_anterior), set(cabecera_nueva)
    return sorted(antes - ahora), sorted(ahora - antes)


def misma_version(cabecera_nueva, cabecera_anterior):
    """¿Trae el informe exactamente los mismos encabezados que la carga anterior?

    🔴 Sin carga anterior devuelve False: NO se supone que la versión es la misma.
       Suponerlo dejaría a la Guarda 10 comparando el almacén contra nada.
    """
    faltan, sobran = censo_cabecera(cabecera_nueva, cabecera_anterior)
    if faltan is None:
        return False
    return not faltan and not sobran


def avisar_censo(cabecera_nueva, cabecera_anterior, escribir=print):
    """Grita el censo. NUNCA aborta: censar no es decidir. Devuelve True si gritó."""
    faltan, sobran = censo_cabecera(cabecera_nueva, cabecera_anterior)
    if faltan is None:
        escribir("\n[Guarda 11] Censo de la cabecera: %d encabezados. No hay carga "
                 "anterior con la que comparar, asi que este censo es el primero y "
                 "queda de referencia para el siguiente." % len(cabecera_nueva))
        return False
    if not faltan and not sobran:
        escribir("\n[Guarda 11] Censo de la cabecera: %d encabezados, los mismos que "
                 "la carga anterior. Misma version del informe." % len(cabecera_nueva))
        return False
    escribir("")
    escribir("[Guarda 11] LA CABECERA DEL INFORME HA CAMBIADO desde la carga anterior.")
    escribir("     ahora trae %d encabezados; antes traia %d."
             % (len(cabecera_nueva), len(cabecera_anterior)))
    if faltan:
        escribir("     YA NO VIENEN (%d):" % len(faltan))
        for h in faltan:
            escribir("        · %s" % h)
        escribir("     Si alguno era obligatorio, la Guarda 1 ya ha abortado antes que")
        escribir("     esto. Si era de los esperados, su columna queda a NULO en toda la")
        escribir("     carga — nunca a cero.")
    if sobran:
        escribir("     SON NUEVOS (%d):" % len(sobran))
        for h in sobran:
            escribir("        · %s" % h)
        escribir("     Sobrar NO aborta: el fichero se lee por nombre de columna, no por")
        escribir("     posicion, asi que una columna de mas no desplaza nada. Pero si trae")
        escribir("     algo que hoy no se guarda, esto es lo unico que lo dira.")
    escribir("     🔑 Al ser otra version, la Guarda 10 dejara de comparar el almacen y")
    escribir("        comparara el stock vendible, que es lo unico homogeneo entre")
    escribir("        versiones distintas del informe.")
    escribir("")
    return True


# ---------------------------------------------------------------------------
# GUARDA 10 — EL BALANCE DEL DÍA. Lo que cae tiene que caber en algo medido.
# ---------------------------------------------------------------------------
# 🔴 EL AGUJERO QUE TAPA: todas las guardas de arriba miran el fichero CONSIGO
#    MISMO. Ninguna lo mira contra el de ayer. Y el 7-sep-2026 Amazon sirvió un
#    informe **internamente coherente** —cuadra consigo mismo al dígito y pasa las
#    otras guardas— al que le faltaban dos columnas y las unidades que había detrás
#    de una de ellas. Lo que lo paró ese día fue la Guarda 1, porque la columna que
#    faltaba estaba en el contrato: **pura suerte de contrato**.
#
# 🔑 QUÉ SE COMPARA: el DISPONIBLE, con la misma cuenta a los dos lados de la resta.
#        available + fc_transfer   si el informe trajo el tránsito      ('leido')
#        disponible_estimado       si no, y el internacional lo permite ('estimado')
#        available                 si tampoco ('desconocido': el vendible es el suelo)
#    🔒 Así la resta es HOMOGÉNEA aunque el informe cambie de versión por el medio, que
#       es justo lo que pasó el 7-sep. Comparar el almacén de una versión con el de otra
#       daba una caída de 246 unidades que no era una caída.
#
# 🔬 EL CASO QUE TIENE QUE CAZAR — Y LA TRAMPA DE SU CIFRA, que es lo que hay que
#    leer despacio (medido en producción el 7-sep-2026):
#       disponible del 6-sep   6.692  (6.437 vendible + 255 tránsito, 381 fichas)
#       vendible del 7-sep     6.453
#    Esas dos cifras se restan solas y dan **239**, y esa resta está MAL: compara el
#    disponible de un día con el VENDIBLE del siguiente. Peras con manzanas.
#
# 🔴 LO QUE PASARÍA SI LA GUARDA MIDIERA ASÍ, y por eso no lo hace: el tránsito del
#    6-sep eran 255 unidades, y mientras Amazon no lo reporte el vendible en bruto va a
#    salir cada día ~250 por debajo del disponible de la víspera. Con un techo de 177,
#    **la carga abortaría todos los días del mes, siempre por el mismo motivo falso** — y
#    una guarda que salta siempre se acaba desactivando.
#
# 🔑 POR ESO LOS DOS LADOS SE MIDEN POR LA MISMA ESCALERA (la del 2c):
#    `disponible_de()` en Python y `SQL_DISPONIBLE` en SQL, las dos
#    COALESCE(leído, estimado, vendible). 🔬 Y está MEDIDO que con eso el escalón
#    desaparece: sobre la foto viva del 6-sep, fingiendo que el tránsito no viniera,
#       disponible real (con tránsito)     6.692
#       por la escalera (sin tránsito)     6.717   → escalón **−25**, o sea que SUBE
#       sólo el vendible en bruto          6.437   → escalón 255, que es el falso
#    Y las 137 fichas que se quedan sin estimación suman **0 unidades de tránsito**: el
#    puente falta justo donde no hace falta.
#
# ⚠️ Lo que SÍ haría saltar la guarda es que el informe internacional no llegue: sin él
#    no hay estimación, la escalera cae al vendible y el escalón vuelve. Eso es correcto
#    — ese día no se sabe el disponible — y el aviso de la fuente vieja lo dice antes.
#
# ---------------------------------------------------------------------------
# 🔴 DE DÓNDE SALE EL TECHO, Y POR QUÉ HAY DOS FUENTES. Esto se reescribió entero el
#    7-sep-2026 por una medición de Fernando que tumbó la versión anterior.
# ---------------------------------------------------------------------------
# La primera versión comparaba la caída contra las salidas del ledger, y para los días
# que el ledger no cubriera usaba su pico diario. **Eso no se sostenía**, y así está
# medido en producción el 7-sep-2026 a las 17:40:
#   · `ledger_movimientos` **no tiene reloj**: `procesar-ledger.yml` es sólo
#     `workflow_dispatch`. Se carga cuando alguien pulsa el botón — sus 16 cargas van
#     del 23-jul al 6-sep, con huecos de hasta cuatro días.
#   · Y **su último día siempre viene cortado**, porque el informe se descarga a media
#     mañana: el 6-sep trae 16 unidades de salida contra 74, 119, 97, 130 y 174 los
#     cinco días anteriores.
#   ∴ O sea que el día que hay que juzgar NUNCA está completo en el ledger, y el
#     anterior tampoco lo está si es el último que se descargó. Una guarda que se apoya
#     en eso no mide lo que dice medir: mide a qué hora se bajó un informe.
#
# 🔑 LA REGLA, EN DOS PASOS, Y EL PRIMERO ES LA COBERTURA:
#   1) ¿Puede el ledger opinar? Sólo si tiene DÍAS COMPLETOS que lleguen hasta la fecha
#      del informe que entra. Completo = ANTERIOR a su último día, que está cortado.
#      Si cubre → techo = lo que salió + 60 uds/día de margen.
#   2) Si no cubre —que hoy es lo NORMAL, no la excepción— opina la PELÍCULA: la mayor
#      caída de un día medida en `inventario_fba_historico`, que es un dato completo por
#      construcción porque es la misma serie que se está protegiendo.
#      🔬 Medido el 7-sep-2026: 7 saltos de un día, con caídas de **111, 95, 91, 76, 73
#         y 58**, y una subida de 181. La mayor caída de un día es **111**.
#         Con la holgura de la casa: 111 × 1,6 = **177 uds/día**.
#         Contra el caso del 7-sep: 239 contra 177, salta por 62 unidades — no por 5,
#         que es lo que daba la versión del pico. Y ninguno de los 7 saltos reales lo roza.
#   3) Y si la película tampoco tiene con qué —menos de 5 saltos de un día—,
#      la guarda **no opina y PARA**. Decir «no puedo juzgar esto» no es lo mismo que
#      decir «esto está mal», y las dos cosas tienen que poder distinguirse en el log.
#
# ⚠️ EL MARGEN DEL LEDGER, y de dónde sale su número. Medido sobre los 10 saltos del
#    histórico comparando la caída con lo que salió en esa ventana (`EVENTOS_QUE_SACAN`):
#        caída 111 / salidas  82     caída  76 / salidas  47     caída 227 / salidas 209
#        caída  95 / salidas 103     caída  73 / salidas  88     caída  58 / salidas  97
#        caída  91 / salidas 113     y tres saltos en que el disponible SUBIÓ
#    El exceso de la caída sobre lo que salió nunca pasó de +29 unidades. De ahí el
#    margen: 29 × 2 ≈ 60 uds/día.
#
# ⚠️ ES UN SUELO POR CAÍDA, NO POR SUBIDA, a propósito: una entrada de mercancía puede
#    subir el stock todo lo que quiera en un día (llega un camión). Lo que no puede es
#    BAJAR más rápido de lo que sale.
#
# 🔴 LA PUERTA TIENE NOMBRE: PERMITIR_SALTO=1. Lo que no se hace es subir el margen
#    hasta que deje de molestar.
CAIDA_MAX_FICHAS = 0.15        # medido: el peor dia perdio un 0,5% de las fichas
MARGEN_CAIDA_DIA = 60          # el peor exceso de la caída sobre las salidas fue +29 × 2
FACTOR_PELICULA = 1.6          # la holgura de la casa sobre la peor caída observada
MINIMO_SALTOS_PELICULA = 5     # con menos, la película no tiene con qué opinar


def disponible_de(reg):
    """El disponible de UNA ficha. La misma regla a los dos lados de la resta.

    🔴 `available + fc_transfer` con `fc_transfer` a NULO da NULO, no `available`:
       por eso el orden importa y por eso NO hay ningún `or 0` sobre el tránsito. Un
       tránsito que no se sabe no vale cero (Stock 8); lo que se hace es bajar al
       escalón siguiente, que es la estimación, y si tampoco la hay, al vendible — que
       es un SUELO cierto, no una cifra completa.
    """
    if reg.get('fc_transfer') is not None:
        return (reg.get('available') or 0) + reg['fc_transfer']
    if reg.get('disponible_estimado') is not None:
        return reg['disponible_estimado']
    return reg.get('available') or 0


def disponible_total(filas):
    """El disponible de toda la foto que entra. Se llama DESPUÉS del puente."""
    return sum(disponible_de(f['registro']) for f in filas)


# 🔒 La MISMA regla que `disponible_de()`, escrita en SQL para el lado de la base.
#    Van juntas y con el mismo comentario a propósito: el día que una cambie y la otra
#    no, la resta compararía dos cuentas distintas y la diferencia parecería un salto.
SQL_DISPONIBLE = "coalesce(available + fc_transfer, disponible_estimado, available)"

TABLA_LEDGER = 'ledger_movimientos'

# ---------------------------------------------------------------------------
# QUÉ CUENTA COMO «SALIDA», Y POR QUÉ CADA UNA. Medido el 7-sep-2026, 60 días.
# ---------------------------------------------------------------------------
# 🔴 NO SON «LAS VENTAS». Lo que tiene que caber en la caída del disponible es TODO lo
#    que saca unidades del almacén europeo:
#      · Shipments     — la venta. Mayor día 155, y 5.365 uds en los 60.
#      · Adjustments   — mermas y correcciones de Amazon. Mayor día 23 en negativo.
#      · VendorReturns — devoluciones al proveedor. Mayor día 11.
#      · Receipts      — normalmente ENTRAN (5.310 uds), pero hay días en negativo:
#                        mayor día 7. Sólo cuentan los negativos, como en las otras.
#    🔒 Se cuentan SÓLO las cantidades NEGATIVAS: un `Adjustments` positivo es stock
#       que aparece, y esta guarda es un suelo por caída, no por subida.
#
# 🔴 Y LA QUE SE QUEDA FUERA, que es la que más pesa: `WhseTransfers`. Mayor día
#    **790 unidades**, y en los 60 días saca 5.662 y mete 5.669 — son traslados ENTRE
#    centros de Amazon. No reducen el stock europeo, y contarlas dispararía el techo
#    justo en los días de más movimiento interno.
#
# ⚠️ Un `event_type` que no esté en ninguna de las listas se GRITA. No se cuenta ni se
#    descarta por su cuenta: un evento nuevo que saque stock haría que las salidas
#    midiesen de menos, y una guarda que mide de menos aborta de más.
EVENTOS_QUE_SACAN = ('Shipments', 'Adjustments', 'VendorReturns', 'Receipts')
EVENTOS_INTERNOS = ('WhseTransfers',)
EVENTOS_QUE_ENTRAN = ('CustomerReturns',)


def salidas_del_ledger(cur, desde, hasta):
    """Lo que SALIÓ del almacén entre dos fotos, y si el ledger puede opinar siquiera.

    🔑 POR QUÉ EL LEDGER Y NO `transacciones_movimientos` — y el motivo NO es el que
       puse primero. Escribí que transacciones «no tiene Alemania», y es FALSO: medido
       el 7-sep-2026 sobre 60 días, trae de, es, fr e it. Las razones de verdad:
         · el ledger es la SALIDA FÍSICA del almacén, que es lo que baja este stock;
           transacciones es el pedido en el marketplace;
         · llega más lejos: hasta el 6-sep cuando transacciones se queda en el 5;
         · y trae dos países más, `pl` y `sk`.

    🔴 EL ÚLTIMO DÍA DEL LEDGER NO CUENTA COMO DÍA. El informe se descarga a media
       mañana, así que su último día viene cortado a esa hora: medido el 7-sep-2026, el
       6-sep trae 16 unidades contra 74, 119, 97, 130 y 174 los cinco días anteriores.
       Contarlo como un día entero hace que el techo dependa de a qué hora se bajó un
       informe, que es lo contrario de una medida.

    🔒 Las cantidades llegan NEGATIVAS (una salida), de ahí el abs().

    Devuelve el dict que lee la Guarda 10, o None si no hay ledger que leer. `cubre`
    dice si puede opinar: días completos hasta la fecha del informe que entra.
    """
    cur.execute("SELECT to_regclass(%s);", ('public.' + TABLA_LEDGER,))
    if cur.fetchone()[0] is None:
        return None
    cur.execute("SELECT max(fecha) FROM %s;" % TABLA_LEDGER)
    hasta_ledger = cur.fetchone()[0]
    if hasta_ledger is None:
        return None

    # El último día COMPLETO del ledger es el anterior al último que trae.
    completo_hasta = hasta_ledger - datetime.timedelta(days=1)
    cubre = completo_hasta >= hasta

    cur.execute(
        "SELECT coalesce(sum(abs(quantity)), 0) FROM %s "
        "WHERE quantity < 0 AND event_type = ANY(%%s) "
        "  AND fecha > %%s AND fecha <= %%s;" % TABLA_LEDGER,
        (list(EVENTOS_QUE_SACAN), desde, min(hasta, completo_hasta)))
    uds = int(cur.fetchone()[0] or 0)

    cur.execute(
        "SELECT DISTINCT event_type FROM %s "
        " WHERE fecha > %%s - 60 AND NOT (event_type = ANY(%%s));" % TABLA_LEDGER,
        (hasta_ledger,
         list(EVENTOS_QUE_SACAN + EVENTOS_INTERNOS + EVENTOS_QUE_ENTRAN)))
    sin_catalogar = sorted(r[0] for r in cur.fetchall() if r[0])

    return {'uds': uds, 'cubre': cubre, 'hasta_ledger': hasta_ledger,
            'completo_hasta': completo_hasta, 'sin_catalogar': sin_catalogar}


def caida_maxima_de_la_pelicula(cur):
    """La mayor caída de UN día medida en la propia película del inventario.

    🔑 POR QUÉ ESTA FUENTE. Es el único dato completo que hay: la película es la misma
       serie que la guarda protege, así que no depende de que otra cañería se haya
       cargado hoy ni de a qué hora se descargó un informe. Lo que mide no es cuánto se
       vendió ayer, sino **cuánto ha llegado a caer este almacén en un día**, que para un
       suelo por caída es exactamente la pregunta.

    🔴 SÓLO SALTOS DE UN DÍA. Repartir la caída de una ventana de tres días entre sus
       tres días es inventarse el reparto: pudo caer todo en uno. Un salto de varios
       días no dice cuál fue la peor caída diaria, así que no se usa para medirla.

    ⚠️ Y LO QUE ESTO NO SABE: describe el pasado. Un día de venta récord o una retirada
       grande pueden pasar del techo sin que el informe tenga nada malo — para eso está
       PERMITIR_SALTO, y por eso el aborto dice que compruebe si el salto es real.

    Devuelve {'saltos': n, 'peor': uds} o None si la tabla no existe.
    """
    cur.execute("SELECT to_regclass(%s);", ('public.' + TABLA_HIST,))
    if cur.fetchone()[0] is None:
        return None
    cur.execute(
        """WITH fotos AS (
               SELECT fecha_foto, sum(%s) AS disp
                 FROM %s GROUP BY fecha_foto),
                p AS (
               SELECT fecha_foto, disp,
                      lag(fecha_foto) OVER (ORDER BY fecha_foto) AS f_ant,
                      lag(disp)       OVER (ORDER BY fecha_foto) AS d_ant
                 FROM fotos)
           SELECT count(*), coalesce(max(d_ant - disp), 0)
             FROM p
            WHERE f_ant IS NOT NULL AND fecha_foto - f_ant = 1;""" % (
            SQL_DISPONIBLE, TABLA_HIST))
    saltos, peor = cur.fetchone()
    return {'saltos': int(saltos or 0), 'peor': int(peor or 0)}


def guarda_continuidad(fecha_ant, fecha_nueva, disponible_ant, disponible_nuevo,
                       fichas_ant, fichas_nuevas, salidas=None, pelicula=None,
                       permitir_salto=None, escribir=print):
    """Compara la foto que entra con la que ya está. Aborta si la resta no cuadra.

    🔒 Función PURA a propósito: las dos fuentes llegan YA MEDIDAS
       (`salidas_del_ledger`, `caida_maxima_de_la_pelicula`), que es lo único que toca
       la base. Así se prueba sin base y sin red, con números a mano.

    Devuelve la lista de motivos. Vacía = todo en orden. No vacía sólo puede pasar si
    PERMITIR_SALTO=1 la dejó pasar, y entonces ya ha gritado.
    """
    if permitir_salto is None:
        permitir_salto = os.environ.get('PERMITIR_SALTO') == '1'

    # Sin foto anterior no hay contra qué comparar, y una comprobación sin nada que
    # comparar no comprueba nada: la primera carga la cubre el suelo de la Guarda 4.
    if fecha_ant is None or not fichas_ant:
        return []
    if fecha_nueva == fecha_ant:
        return []
    dias = (fecha_nueva - fecha_ant).days
    if dias <= 0:
        return []

    motivos = []
    caida = (disponible_ant or 0) - (disponible_nuevo or 0)

    # 🔑 PASO 1: ¿quién puede opinar? La cobertura ANTES que el veredicto.
    if salidas is not None and salidas.get('cubre'):
        techo = salidas['uds'] + MARGEN_CAIDA_DIA * dias
        fuente = ("lo que salio del almacen entre el %s y el %s (%d uds, del ledger) "
                  "mas %d uds/dia de margen"
                  % (fecha_ant, fecha_nueva, salidas['uds'], MARGEN_CAIDA_DIA))
    elif pelicula is not None and pelicula['saltos'] >= MINIMO_SALTOS_PELICULA:
        techo = int(pelicula['peor'] * FACTOR_PELICULA) * dias
        motivo_ledger = "no hay ledger que leer"
        if salidas is not None:
            motivo_ledger = ("el ledger solo tiene dias completos hasta el %s y este "
                             "informe es del %s"
                             % (salidas['completo_hasta'], fecha_nueva))
        fuente = ("la peor caida de un dia medida en la pelicula del propio inventario "
                  "(%d uds en %d saltos de un dia) por %s de holgura, %s"
                  % (pelicula['peor'], pelicula['saltos'], FACTOR_PELICULA,
                     "y no el ledger porque " + motivo_ledger))
    else:
        # 🔴 «No puedo juzgar esto» NO es «esto está mal», y se dice distinto.
        cuerpo = (
            "[Guarda 10] NO SE PUEDE JUZGAR ESTA CARGA: no hay con que.\n"
            "   El disponible pasa de %s a %s (%+d) entre el %s y el %s, y no hay "
            "ninguna fuente completa con la que decir si esa caida cabe:\n"
            "   · el ledger %s\n"
            "   · y la pelicula del inventario tiene %d salto(s) de un dia, y hacen "
            "falta %d para que pueda opinar.\n"
            "   Esto NO dice que el informe este mal: dice que nadie puede decir si "
            "esta bien. Carga el ledger (procesar-ledger.yml, que no tiene reloj y va "
            "a mano) y repite, o mira la foto tu mismo y sigue con PERMITIR_SALTO=1."
            % (disponible_ant, disponible_nuevo, -caida, fecha_ant, fecha_nueva,
               ("no se puede leer" if salidas is None else
                ("solo tiene dias completos hasta el %s y este informe es del %s"
                 % (salidas['completo_hasta'], fecha_nueva))),
               0 if pelicula is None else pelicula['saltos'],
               MINIMO_SALTOS_PELICULA))
        if permitir_salto:
            escribir("")
            escribir("AVISO  " + cuerpo)
            escribir("   PERMITIR_SALTO=1 la salta. Que conste, y que se mire.")
            escribir("")
            return [cuerpo]
        raise Aborta(cuerpo)

    if caida > techo:
        motivos.append(
            "El disponible ha caido %d unidades entre el %s y el %s, y lo maximo que "
            "puede caer son %d.\n"
            "   Ese techo es %s.\n"
            "   Para que esto fuera movimiento real habrian tenido que salir %d "
            "unidades del almacen en %d dia(s). No pasa.\n"
            "   Lo que si pasa es que Amazon sirva un informe que cuadra consigo "
            "mismo pero deja unidades fuera. ¡OJO CON LA CIFRA QUE SE MIRA! El 7-sep-2026 "
            "el VENDIBLE EN BRUTO caia 239 (6.692 del dia 6 contra 6.453 del dia 7), pero "
            "eso NO es una caida del disponible: es comparar el disponible de un dia con "
            "el vendible del siguiente, o sea peras con manzanas. Esta guarda mide el "
            "disponible por la ESCALERA a los dos lados (leido, si no estimado, si no "
            "vendible), y con ella el escalon del transito no existe."
            % (caida, fecha_ant, fecha_nueva, techo, fuente, caida, dias))

    if fichas_nuevas < fichas_ant * (1 - CAIDA_MAX_FICHAS):
        perdido = (fichas_ant - fichas_nuevas) / float(fichas_ant) * 100
        motivos.append(
            "El informe trae %d fichas y el anterior traia %d: se ha perdido un "
            "%.1f%%, y el maximo admitido es el %.0f%% (medido: el peor dia perdio "
            "un 0,5%%).\n"
            "   La Guarda 4 pone el suelo absoluto (%d filas) y no ve esto: un "
            "informe puede traer 320 fichas de 381, quedarse muy por encima del "
            "suelo, y aun asi haber perdido un catalogo entero por el camino."
            % (fichas_nuevas, fichas_ant, perdido, CAIDA_MAX_FICHAS * 100, UMBRAL_FILAS))

    if not motivos:
        return []

    cuerpo = "[Guarda 10] " + "\n   ".join(motivos)
    if permitir_salto:
        escribir("")
        escribir("AVISO  " + cuerpo)
        escribir("   PERMITIR_SALTO=1 la salta. Que conste, y que se mire.")
        escribir("")
        return motivos
    raise Aborta(cuerpo + "\n   (Si el salto es REAL —una retirada grande, un cierre "
                          "de fichas— la puerta es PERMITIR_SALTO=1.)")


# ---------------------------------------------------------------------------
# GUARDA 12 — EL CERROJO: con el tránsito en DESCONOCIDO, la carga NO se abre.
# ---------------------------------------------------------------------------
# 🔴 QUÉ IMPIDE, en una frase: que entre una carga con el tránsito a NULO mientras
#    quien lo LEE siga convirtiendo ese «no se sabe» en un CERO. Que `fc_transfer`
#    pueda ser NULL está hecho y probado aquí arriba; lo que hay que comprobar es
#    quién lo lee después.
#
# 🔬 LA MEDICIÓN QUE LO ABRIÓ. El 7-sep-2026 por la mañana los cuatro consumidores
#    hacían `COALESCE(fc_transfer, 0)`, así que un NULL habría entrado por esos
#    cuatro sitios convertido en cero y el disponible habría quedado ~250 unidades
#    corto **sin que nada lo dijera**. Esa misma tarde, leídas otra vez sus
#    definiciones en producción, los cuatro estaban ya arreglados: usan
#    `CASE WHEN count(*) = count(fc_transfer) THEN sum(…) ELSE NULL END`, que es
#    tratar el nulo como lo que es.
#
# 🔑 CÓMO SE ABRE, Y ESTO ES LO QUE CAMBIÓ EL 7-sep-2026 (encargo F): **ya no se
#    abre vaciando una lista a mano.** Antes había aquí una lista de cuatro nombres
#    y el cerrojo se abría borrándolos, o sea que la carga del almacén dependía de
#    que alguien se acordara de editarla el día justo. Ahora los culpables se MIDEN
#    en cada carga contra la definición viva de cada objeto
#    (`objetos_que_leen_nulo_como_cero`): el cerrojo se abre solo el día que el
#    último queda arreglado, se cierra solo si alguno vuelve atrás, y contesta
#    distinto en staging y en producción — que es justo lo que una lista escrita en
#    el código no puede hacer.
# 🔒 Lo que sigue siendo una decisión humana es A QUIÉN se mira, y por eso
#    `CONSUMIDORES_DEL_TRANSITO` sigue existiendo: es la lista de quien consume la
#    columna, no la lista de quien está roto.
# ---------------------------------------------------------------------------
# GUARDA 13 — EL DÍA EN QUE SUMAR EMPIEZA A CONTAR DOBLE.
# ---------------------------------------------------------------------------
# 🔴 QUÉ VIGILA, en una frase: que el vendible NO suba de golpe en el orden del
#    tránsito del día anterior. Si eso pasa, Amazon ha terminado de meter las
#    unidades de «Transferencia entre centros» DENTRO del vendible (es el cambio
#    que anunció en la página del informe), y a partir de ese momento
#    `vendible + tránsito` cuenta doble esas ~250 unidades.
#
# 🔑 POR QUÉ NO BASTA CON «EL VENDIBLE HA SUBIDO MUCHO»: una entrega grande también
#    sube el vendible de golpe, y sería un falso positivo cada vez que llega un
#    camión. La diferencia está medida y es limpia: **en una entrega, las unidades
#    vienen de `inbound_shipped`**, que baja justo lo que sube el vendible. En el
#    cambio de modelo, el tránsito no pasa por ahí: el vendible sube y los
#    entrantes no se mueven. Por eso lo que se compara es la subida NO EXPLICADA
#    por la bajada de entrantes.
#
# 🔬 LOS NÚMEROS, del histórico (23-ago → 6-sep-2026, 10 saltos):
#      · subida diaria del vendible: máximo real +40. Con 1,6 de holgura → 64/día.
#      · el tránsito del 6-sep eran 255 uds, o sea 6 veces esa subida máxima: si un
#        día aparecen de golpe, no hay forma de confundirlo con un día normal.
#    Se exige que la subida no explicada pase LAS DOS cosas: que sea anormal
#    (> 64/día) y que además sea del ORDEN del tránsito de ayer (≥ la mitad). Una
#    sola de las dos daría ruido; las dos juntas describen el día que se busca.
#
# ⚠️ ABORTA, no grita. Es el único caso de este fichero donde una cifra plausible
#    es peor que ninguna: la carga entraría bien, las guardas saldrían verdes, y el
#    disponible quedaría 250 unidades LARGO sin que nada lo dijera.
TECHO_SUBIDA_VENDIBLE_DIA = 64   # subida diaria máxima medida 40 × 1,6


def guarda_salto_a_transito_dentro(vendible_ant, vendible_nuevo,
                                   inbound_ant, inbound_nuevo,
                                   fc_ant, dias, escribir=print):
    """Aborta si el vendible ha absorbido de golpe el tránsito del día anterior."""
    if not fc_ant or not dias or dias <= 0:
        return False
    subida = (vendible_nuevo or 0) - (vendible_ant or 0)
    if subida <= 0:
        return False
    # Lo que explican los entrantes que han aterrizado (una entrega normal).
    aterrizado = max((inbound_ant or 0) - (inbound_nuevo or 0), 0)
    no_explicada = subida - aterrizado
    if no_explicada <= TECHO_SUBIDA_VENDIBLE_DIA * dias:
        return False
    if no_explicada < 0.5 * fc_ant:
        return False
    raise Aborta(
        "[Guarda 13] El stock vendible ha subido %d unidades en %d dia(s), y %d de "
        "ellas NO las explica ninguna entrega: los entrantes solo bajaron %d.\n"
        "   Justo ayer habia %d unidades en transferencia entre centros. Que "
        "aparezcan de golpe dentro del vendible es la senal de que Amazon ha "
        "terminado el cambio que anuncio: las unidades en transferencia han dejado "
        "de estar aparte porque ahora son comprables.\n"
        "   A partir de ese dia, sumar el transito al vendible cuenta DOBLE esas "
        "unidades. Y un disponible largo no da un error: da una cifra creible con "
        "la que se decide reponer y se decide precio.\n"
        "   QUE HAY QUE HACER: comprobarlo contra el Seller y, si es eso, ensenar a "
        "`modelo_del_disponible()` a devolver MODELO_TRANSITO_DENTRO para esta "
        "version del informe. No se fuerza esta guarda: se cambia el modelo."
        % (subida, dias, no_explicada, aterrizado, fc_ant))


# 🔴 AQUÍ VIVÍA `VISTAS_QUE_LEEN_NULO_COMO_CERO`, UNA LISTA ESCRITA A MANO, Y SE HA
#    IDO. Léelo antes de escribir otra igual. Decía qué objetos hacían
#    `COALESCE(fc_transfer, 0)` el 7-sep-2026 por la mañana, y el cerrojo se abría
#    VACIÁNDOLA a mano. O sea que la carga del almacén dependía de que alguien se
#    acordara de borrar cuatro nombres el día justo — ni antes (se abriría con las
#    vistas todavía rotas) ni después (el almacén a ciegas un día de más).
#
# 🔑 AHORA SE PREGUNTA A LA BASE, EN CADA CARGA. La lista de abajo dice a QUIÉN hay
#    que mirar —esa decisión sí es humana, es quién consume la columna— y el veredicto
#    lo da la definición viva de cada objeto, leída con `pg_get_viewdef`. Ventajas, y
#    no son teóricas: el cerrojo se abre solo el día que el último objeto queda
#    arreglado, se cierra solo si alguno vuelve atrás, y **contesta distinto en staging
#    y en producción**, que es justo lo que una constante no puede hacer.
#
# 🔬 MEDIDO EL 7-sep-2026 EN PRODUCCIÓN con la expresión de abajo: los cuatro salen
#    LIMPIOS. Ya no hacen `COALESCE(fc_transfer, 0)`; hacen
#    `CASE WHEN count(*) = count(fc_transfer) THEN sum(...) ELSE NULL END`, que es
#    tratar el nulo como lo que es. O sea que hoy, en producción, el cerrojo está
#    ABIERTO — pero por medición, no porque nadie lo haya declarado.
CONSUMIDORES_DEL_TRANSITO = [
    'salud_fba',
    'v_salud_asin',
    'v_trackeador_pantalla',
    'mv_trackeador_pantalla',
]

# 🔒 LA EXPRESIÓN, Y POR QUÉ ES TAN ESTRECHA. Tiene que cazar el `COALESCE` cuyo
#    PRIMER argumento es `fc_transfer` (o algo que lo envuelve, como `sum(fc_transfer)`)
#    y cuyo segundo es 0. Y tiene que dejar en paz `COALESCE(available, 0) + fc_transfer`,
#    que es CORRECTO y que `v_salud_asin` hace de verdad: ahí el que se coalesce es el
#    vendible, y el tránsito sigue propagando su nulo. Una expresión más ancha daría
#    ese falso positivo y el cerrojo no se abriría jamás.
#    🔬 Probada el 7-sep-2026 contra siete casos, cuatro que debe cazar y tres que no
#       (están en `test_inventario_fba.py`, bloque 21).
RE_NULO_COMO_CERO = (r'coalesce\s*\(\s*(?:[a-z0-9_]+\s*\(\s*)?[^,()]*'
                     r'fc_transfer[^,]{0,20},\s*\(?\s*0')


def objetos_que_leen_nulo_como_cero(cur, objetos=None):
    """Cuáles de los consumidores convierten HOY el NULO en 0. Se mide, no se cree.

    Devuelve (culpables, ausentes). `ausentes` son los que ni siquiera existen en esta
    base: no son culpables, pero se dicen — un consumidor que se ha esfumado también
    es una noticia.
    """
    if objetos is None:
        objetos = CONSUMIDORES_DEL_TRANSITO
    cur.execute(
        "SELECT c.relname, pg_get_viewdef(c.oid) ~* %s "
        "  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        " WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm') "
        "   AND c.relname = ANY(%s);",
        (RE_NULO_COMO_CERO, list(objetos)))
    visto = {nombre: sucio for nombre, sucio in cur.fetchall()}
    culpables = [o for o in objetos if visto.get(o)]
    ausentes = [o for o in objetos if o not in visto]
    return culpables, ausentes


def guarda_transito_desconocido(fc_origen, culpables, abre_fernando=None):
    """Con `fc_transfer` a NULO, dos llaves: la medición y Fernando.

    🔴 LA DOBLE LLAVE, y el reparto entre las dos NO es simétrico (decisión de
       Fernando, 7-sep-2026): **la medición puede mantener CERRADO, pero no puede
       ABRIR**. Que ningún consumidor haga ya `COALESCE(fc_transfer, 0)` es condición
       necesaria y no suficiente: dice que el camino está despejado, no que sea hoy el
       día de soltar por él una foto sin tránsito. Lo segundo lo decide una persona.
       🔑 Por qué así: la medición mira UNA expresión en CUATRO objetos. Si mañana el
          nulo se leyera como cero en un sitio que esa expresión no ve —otro objeto,
          la app, un informe—, la medición diría «limpio» y la carga se abriría sola.
          Una guarda que puede equivocarse por el lado de ABRIR no debe poder abrir.

    🔒 Función PURA: los culpables llegan YA MEDIDOS
       (`objetos_que_leen_nulo_como_cero`), que es lo único que toca la base.
    """
    if abre_fernando is None:
        abre_fernando = os.environ.get('ABRIR_TRANSITO_DESCONOCIDO') == '1'
    if fc_origen != ORIGEN_DESCONOCIDO:
        return
    if not culpables and abre_fernando:
        return
    if not culpables:
        raise Aborta(
            "[Guarda 12] Este informe no trae el transito entre centros, y la medicion "
            "dice que se PODRIA abrir: ninguno de los %d consumidores hace ya "
            "COALESCE(fc_transfer, 0) en esta base.\n"
            "   Pero abrir no lo decide la medicion, lo decide Fernando. La medicion "
            "solo puede mantener CERRADO.\n"
            "   COMO SE ABRE: ABRIR_TRANSITO_DESCONOCIDO=1 (en el .yml, «abrir transito "
            "desconocido = si»), y con Fernando delante.\n"
            "   Por que la segunda llave: esa expresion mira CUATRO objetos. Si el nulo "
            "se leyera como cero en un sitio que no mira —otro objeto, la app, un "
            "informe—, la medicion diria «limpio» y la carga se abriria sola con el "
            "disponible ~250 uds corto."
            % len(CONSUMIDORES_DEL_TRANSITO))
    raise Aborta(
        "[Guarda 12] Este informe no trae el transito entre centros, asi que "
        "`fc_transfer` quedaria a NULO en todas las filas — que es lo correcto: no "
        "se sabe.\n"
        "   El problema no es la carga: es quien la lee. Estos %d objetos hacen HOY "
        "COALESCE(fc_transfer, 0) en esta base, o sea que convertirian ese «no lo "
        "se» en un cero (medido leyendo su definicion viva, no una lista):\n"
        "   · %s\n"
        "   El disponible saldria unas 250 unidades corto y NADA lo diria. Un aborto "
        "ruidoso es mejor que una cifra falsa y creible.\n"
        "   COMO SE ABRE: arreglar esos objetos para que traten el NULO como "
        "desconocido — el patron que ya usan los demas es "
        "CASE WHEN count(*) = count(fc_transfer) THEN sum(...) ELSE NULL END. No hay "
        "que tocar ninguna guarda ni editar ninguna lista: en cuanto la definicion "
        "cambie, este cerrojo se abre solo."
        % (len(culpables), "\n   · ".join(culpables)))


# ---------------------------------------------------------------------------
# DDL: la tabla la crea la MIGRACIÓN (nace CERRADA: RLS on, 0 políticas, revoke
# a public/anon/authenticated). Aquí sólo el IF NOT EXISTS idempotente, como en
# las otras cañerías — y la COMPROBACIÓN de que está cerrada, que sí aborta.
# 🔒 `ENABLE RLS` NO se lanza aquí: pide AccessExclusiveLock EN CADA CARGA y ése
#    es el lock que tumbó la base el 28-jul. Vive en la migración.
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n        ".join(
        [f"{c} {TIPO_SQL[t]}" for _, c, t in TIPADAS]
        + [f"{c} {t}" for c, t in DERIVADAS])
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA} (
        {cols},
        fichero       text,
        fecha_foto    date,
        crudo         jsonb,
        procesado_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (sku)
    );
    """


def sql_crear_tabla_historico():
    """DDL idempotente del histórico. La RLS y los índices los pone la MIGRACIÓN
    (2026-08-23_inventario_fba_historico.sql): un `ENABLE RLS` en cada carga es un
    AccessExclusiveLock en cada carga, y ése fue el lock que tumbó la base el
    28-jul. Aquí solo el `IF NOT EXISTS`, que es barato."""
    tipos = {c: TIPO_SQL[t] for _, c, t in TIPADAS}
    tipos.update(dict(DERIVADAS))
    tipos['fecha_foto'] = 'date'
    tipos['fichero'] = 'text'
    cols = ",\n        ".join(
        f"{c} {tipos[c]}" + (' NOT NULL' if c in HIST_PK else '') for c in HIST_COLS)
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA_HIST} (
        {cols},
        capturado_en timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (sku, fecha_foto)
    );
    """


def sql_crear_tabla_censo():
    """DDL idempotente del censo de cabeceras (Guarda 11). Cajón PELÍCULA.

    🔑 UNA FILA POR FOTO, no una por SKU: lo que se censa es el INFORME, no el
       inventario. Con eso se contesta «¿desde cuándo llega esta columna?» y
       «¿cambió de versión entre estas dos cargas?», que es lo que necesita la
       Guarda 10 para saber si el almacén es comparable.
    🔒 La RLS y el revoke los pone la MIGRACIÓN, como en las otras dos tablas: un
       ENABLE RLS en cada carga es un AccessExclusiveLock en cada carga, y ése fue
       el lock que tumbó la base el 28-jul.
    """
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA_CENSO} (
        fecha_foto    date NOT NULL,
        fichero       text,
        n_encabezados integer NOT NULL,
        encabezados   text[] NOT NULL,
        -- 🔑 Bajo qué regla se leyó el disponible ese día. Sin esto, la serie del
        --    histórico no se puede releer: un fotograma de antes del cambio y uno
        --    de después significan cosas distintas con las mismas columnas.
        modelo_disponible text,
        -- 🔴 SI LA CARGA ENTRÓ O NO, y el porqué si no. Sin esto la libreta no
        --    puede llevar las cargas fallidas, y son justo las que hay que apuntar:
        --    la del 7-sep-2026 abortó y no dejó rastro en ninguna parte.
        resultado     text,
        motivo        text,
        capturado_en  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (fecha_foto)
    );
    """


CARGA_ENTRO = 'cargada'
CARGA_ABORTO = 'abortada'


def anotar_libreta(cur, fecha_foto, fichero, cabecera, modelo, resultado, motivo=None):
    """Deja en `inventario_fba_cabecera` la fila de ESTA carga. No hace commit.

    🔴 POR QUÉ TAMBIÉN SE APUNTAN LAS CARGAS QUE ABORTAN (encargo F, punto 2). El
       7-sep-2026 la libreta estaba a **0 filas en producción**, medido: la carga del
       6-sep es anterior a que la tabla existiera y la del 7 abortó antes de llegar
       aquí, porque esto se escribía al final y dentro de la transacción de datos. O
       sea que el día en que el informe cambió de forma —el único día en que esta
       libreta tenía algo que decir— fue exactamente el día en que no anotó nada.
       La forma del informe que se RECHAZA es información, y de las caras: es lo único
       que distinguirá mañana un informe viejo de uno nuevo.

    🔒 Y POR ESO LLEVA `resultado`. Una fila sin él sería una mentira nueva: la
       serie diría que ese día entró una carga que en realidad no entró, y
       `cabecera_anterior()` compararía la versión de hoy contra un informe que nunca
       se cargó. Se apunta lo que pasó, no sólo que pasó algo.
    """
    # 🔴 UN ABORTO NO PISA UN DÍA QUE SÍ SE CARGÓ, y esto no es una precaución: es un
    #    caso que va a pasar. Basta con relanzar a mano el fichero de un día ya cargado
    #    cuando ya hay una foto más nueva — `guarda_no_retroceder` aborta, y sin este
    #    `WHERE` la fila de aquel día pasaría de 'cargada' a 'abortada' y la libreta
    #    diría que un día que SÍ entró no entró. La carga buena manda sobre el intento
    #    fallido, siempre.
    filtro = ("" if resultado == CARGA_ENTRO
              else " WHERE %s.resultado IS DISTINCT FROM '%s'" % (TABLA_CENSO, CARGA_ENTRO))
    cur.execute(
        "INSERT INTO %s (fecha_foto, fichero, n_encabezados, encabezados, "
        "modelo_disponible, resultado, motivo) VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s) "
        "ON CONFLICT (fecha_foto) DO UPDATE SET "
        "fichero=EXCLUDED.fichero, n_encabezados=EXCLUDED.n_encabezados, "
        "encabezados=EXCLUDED.encabezados, "
        "modelo_disponible=EXCLUDED.modelo_disponible, "
        "resultado=EXCLUDED.resultado, motivo=EXCLUDED.motivo, capturado_en=now()%s;"
        % (TABLA_CENSO, filtro),
        (fecha_foto, fichero, len(cabecera), list(cabecera), modelo, resultado, motivo))


def _motivo_corto(e):
    """La primera línea del aborto, que es la que dice qué guarda ha saltado."""
    return str(e).strip().split('\n')[0][:500]


def cabecera_anterior(cur, fecha_nueva):
    """Los encabezados de la carga ANTERIOR, o None si no hay ninguna.

    🔑 DOS SITIOS, Y EL SEGUNDO ES EL QUE HACE QUE ESTO SIRVA DESDE EL PRIMER DÍA.
       El censo es nuevo y arranca vacío, así que la primera carga no tendría con
       qué comparar y la Guarda 11 nacería muda justo el día que hace falta. Pero
       los encabezados de la foto viva YA están guardados: `crudo` es un jsonb cuyas
       CLAVES son exactamente la cabecera de aquel .txt. Así que si el censo aún no
       tiene fila, se leen de ahí.
    🔒 Se pregunta por `to_regclass` antes de tocar el censo: si la migración
       todavía no ha pasado, esto no puede reventar la carga.
    """
    cur.execute("SELECT to_regclass(%s);", ('public.' + TABLA_CENSO,))
    if cur.fetchone()[0] is not None:
        # 🔴 `resultado <> 'abortada'`: la carga anterior es la última que ENTRÓ,
        #    no la última que se intentó. Desde que la libreta apunta también los
        #    rechazos, comparar contra el último intento haría que un informe raro
        #    rechazado ayer se convirtiera hoy en «la versión anterior». El
        #    `IS DISTINCT FROM` deja pasar los NULL: las filas anteriores a esta
        #    columna se escribieron sólo cuando la carga había cuadrado.
        cur.execute(f"SELECT encabezados FROM {TABLA_CENSO} WHERE fecha_foto < %s "
                    f"AND resultado IS DISTINCT FROM '{CARGA_ABORTO}' "
                    f"ORDER BY fecha_foto DESC LIMIT 1;", (fecha_nueva,))
        fila = cur.fetchone()
        if fila and fila[0]:
            return list(fila[0])
    cur.execute(f"SELECT array(SELECT jsonb_object_keys(crudo)) FROM {TABLA} "
                f"WHERE crudo IS NOT NULL LIMIT 1;")
    fila = cur.fetchone()
    return list(fila[0]) if fila and fila[0] else None


TABLA_INTL_HIST = 'inventario_internacional_historico'


def foto_internacional(cur, fecha_foto):
    """La `fecha_foto` del internacional que se usa para estimar el día `fecha_foto`.

    Es la MÁS RECIENTE que no sea futura, o None si no hay ninguna.

    🔒 `<= la de esta carga`: jamás se estima un día con datos de un día posterior.
       Eso daría un número que el día que se escribió no existía.
    """
    cur.execute(f"SELECT max(fecha_foto) FROM {TABLA_INTL_HIST} WHERE fecha_foto <= %s;",
                (fecha_foto,))
    fila = cur.fetchone()
    return fila[0] if fila else None


def internacional_por_asin(cur, fecha_foto, asines):
    """{asin: (unidades, fecha_foto)} leído de UNA sola foto del internacional.

    🔑 Del HISTÓRICO, no de la foto viva del internacional, y por dos razones: la
       foto viva puede ser de otro día que el informe FBA que se está cargando, y
       —sobre todo— de aquí sale `disponible_fuente_fecha`, que es lo que delata a
       los tres días que se está tirando de un dato viejo. Una fuente sin su fecha
       no se puede auditar.

    🔴 UNA FOTO, LA MISMA PARA TODOS LOS ASIN — y esto es lo que se corrigió el
       7-sep-2026, porque antes no era así. La primera versión hacía
       `DISTINCT ON (asin) ... ORDER BY asin, fecha_foto DESC`, o sea que a cada
       ASIN le daba SU última lectura, cada uno de un día distinto.
       El internacional es cajón FOTO: **lo que no viene en la hoja, se borra**. Que
       un ASIN no esté en la última foto no es «no lo sé», es «el internacional dice
       que ahí no queda nada». Rescatarle una lectura de hace semanas resucita
       unidades que ya no existen.
       🔬 MEDIDO sobre los 11 días del histórico (4.042 filas, con el tránsito LEÍDO
       y por tanto con verdad contra la que medir), a nivel de ASIN-día:
             una foto (esto)          → error 549 uds · clava 2.414 · se pasa 78
             la última de cada ASIN   → error 2.204 uds · clava 2.456 · se pasa 715
       Cuatro veces peor, y siempre por arriba. Y de los 71 ASIN que el 6-sep tiraban
       de una lectura vieja, 68 se pasaban (el más viejo, de hace 45 días).
       ⚠️ Las cifras que justificaron el puente en la migración del 7-sep (error 549,
       se pasa en 78 fichas con 487 uds, corto en 27 con 62) están medidas ASÍ. El
       código hacía otra cosa: la medición era buena y la implementación no la seguía.

    🔒 Y el `<=` sigue estando, pero en la FOTO, no en el ASIN: el internacional no
       se carga a diario (21 fotos entre el 23-jul y el 7-sep), así que un día sin
       foto propia se estima con la anterior ENTERA, que es un estado coherente del
       almacén internacional. Lo que no se hace es mezclar días.
    🔴 Se limita a los ASIN de esta carga a propósito: traer el internacional entero
       serían miles de filas para nada, y el runner está en EEUU y la base en Irlanda.
    """
    if not asines:
        return {}
    foto = foto_internacional(cur, fecha_foto)
    if foto is None:
        return {}
    cur.execute(
        f"""SELECT asin, sum(quantity) AS uds
              FROM {TABLA_INTL_HIST}
             WHERE fecha_foto = %s AND asin = ANY(%s)
             GROUP BY asin;""",
        (foto, list(asines)))
    return {a: (int(u), foto) for a, u in cur.fetchall()}


def exigir_columnas(cur, tabla, columnas):
    """La MIGRACIÓN pone las columnas; aquí sólo se comprueba que están.

    🔒 Mismo criterio que la comprobación de RLS: el procesador no hace DDL que
       cambie la forma de una tabla viva (`CREATE TABLE IF NOT EXISTS` no añade
       columnas a una tabla que ya existe, así que sin esto el fallo saldría como
       un error de SQL ilegible en mitad del upsert).
    """
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s;", (tabla,))
    hay = {r[0] for r in cur.fetchall()}
    faltan = [c for c in columnas if c not in hay]
    if faltan:
        raise Aborta(
            f"A la tabla {tabla} le faltan columnas que este procesador escribe:\n"
            f"   · " + "\n   · ".join(faltan) + "\n"
            f"   Las pone la MIGRACION, no el procesador. Aplica "
            f"migraciones/ (las DOS del 7-sep-2026: _esperadas_y_censo.sql y _disponible_estimado.sql) y relanza.")


# ---------------------------------------------------------------------------
# ¿CUÁL DE LOS FICHEROS DEL BUZÓN?
# ---------------------------------------------------------------------------
def elegir_fichero(txts, pedido):
    """De los .txt del buzón, cuál se procesa. Devuelve (objeto, motivo).

    🔒 Devuelve el OBJETO del Storage, no el nombre: de él sale también la `fecha_foto`
       (este informe no trae su fecha ni dentro ni en el nombre, así que la fecha del
       dato es la de subida al buzón). Quien elija el fichero tiene que elegir su fecha
       con él, o serían dos decisiones que pueden discrepar.

    🔴 SE PIDE A DEDO Y NO ESTÁ → ABORTA, y NO se cae al más reciente. Caer sería la
       forma silenciosa de cargar una foto distinta de la que se mandó: quien pulsó el
       botón en la app vería «Procesado» sobre un fichero que no es el suyo, y el
       inventario de Elena quedaría el de otro día sin que nada lo dijera. Es la misma
       decisión que ya tomaron keepa y custom_analytics, por el mismo motivo.
    """
    recientes = sorted(txts, key=lambda o: (o.get('updated_at') or o.get('created_at') or ''),
                       reverse=True)
    if not pedido:
        return recientes[0], f"el mas reciente de {len(recientes)}"
    for o in recientes:
        if (o.get('name') or '') == pedido:
            return o, "pedido a dedo"
    nombres = [o.get('name') for o in recientes]
    raise Aborta(
        f"[Guarda fichero] Se pidio {pedido!r} y no esta en {BUCKET}/{CARPETA}/.\n"
        f"   Hay {len(nombres)} .txt en el buzon: {nombres}\n"
        f"   NO se cae al mas reciente: cargaria una foto de otro dia y la carga\n"
        f"   saldria verde sobre un fichero que nadie pidio.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== PROCESADOR INVENTARIO_FBA (Gestion de inventario de Logistica de Amazon) ===",
          flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 78, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    # 🔒 La pregunta anti-cero, hecha código: si no hay ficheros, todo lo de abajo
    #    saldría «bien» sin haber medido nada.
    exigir_poblacion(f"ficheros .txt en el buzon {BUCKET}/{CARPETA}/ "
                     f"(informe «Gestion de inventario de Logistica de Amazon»)", txts)
    try:
        elegido, motivo = elegir_fichero(txts, FICHERO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)
    fichero = elegido['name']
    print(f"Informe elegido ({motivo}): {fichero}", flush=True)

    # fecha_foto = LA FECHA DEL DATO. Este informe no la trae ni dentro ni en el
    # nombre (es un ID numérico de Amazon): el único sello honrado es cuándo se
    # subió la foto al buzón. 🔴 Si no se puede leer, ABORTA (no cae a today()).
    try:
        fecha_foto = fecha_del_dato_por_subida(elegido, 'inventario_fba').date()
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)
    print(f"   · fecha_foto={fecha_foto} (fecha de subida al buzon = fecha del dato)",
          flush=True)

    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")
    print(f"   · {len(crudo_bytes)} bytes descargados", flush=True)
    # 🔴 SIN BOM (medido en el fichero real), pero utf-8-sig decodifica bien con y
    #    sin él. Reserva cp1252. NO se hereda de otra cañería.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # 🔑 LA CABECERA, APARTE Y ANTES QUE NADA. `analizar()` no devuelve nada cuando
    #    aborta — y la carga que aborta es justo la que hay que apuntar en la libreta.
    cabecera_txt = cabecera_de(texto)
    # 🔑 Y se imprimen los NOMBRES, no solo cuantos. Cuando Amazon cambia la forma del
    #    informe, «24 encabezados» no dice nada y la lista lo dice todo — y esta linea
    #    sale ANTES de tocar la base, asi que un ensayo la escupe pase lo que pase.
    print(f"   · la cabecera trae {len(cabecera_txt)} encabezados: "
          f"{', '.join(cabecera_txt)}", flush=True)

    # --- Conectar al ENTORNO ---
    # 🔴 SE CONECTA ANTES DE ANALIZAR, y el orden es el cambio de fondo del encargo F
    #    (punto 2). Antes se analizaba primero y se conectaba después, así que una carga
    #    rechazada por una guarda estructural —la del 7-sep-2026, sin ir más lejos— se
    #    moría sin haber tocado la base y sin dejar ni una línea de qué forma tenía el
    #    informe que se rechazó. Conectar antes no escribe nada de más: sólo permite
    #    que el aborto quede anotado.
    con = conectar_bd(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # La libreta tiene que estar EN PIE antes de la primera guarda, o el aborto no
    # tendría dónde anotarse. El `IF NOT EXISTS` es barato; la RLS y las columnas las
    # pone la MIGRACIÓN, como en las otras dos tablas.
    cur.execute(sql_crear_tabla_censo())
    cur.execute(f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{TABLA_CENSO}'::regclass;")
    if not cur.fetchone()[0]:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"RLS no esta activa en {TABLA_CENSO}. La tabla nace CERRADA por "
              f"migracion, no por el procesador. Aplica migraciones/ y relanza.",
              flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)
    try:
        exigir_columnas(cur, TABLA_CENSO, ['resultado', 'motivo'])
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)
    con.commit()

    def morir(e):
        """Aborta: revierte, ANOTA la carga fallida en la libreta y sale.

        🔒 El orden importa: primero el `rollback` —con la transacción envenenada no
           se puede escribir nada— y luego la fila de la libreta, en una transacción
           propia que SÍ se confirma. Lo que no entra son los datos; lo que queda
           escrito es que ese día hubo un informe con esta forma y no se cargó.
        🔴 Y en ENSAYO no se escribe ni un byte, tampoco esto. Un ensayo que deja
           filas detrás deja de ser un ensayo.
        """
        try:
            con.rollback()
        except Exception:
            pass
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        if cabecera_txt:
            modelo_txt = modelo_del_disponible(cabecera_txt)
            if MODO == 'aplicar':
                try:
                    anotar_libreta(cur, fecha_foto, fichero, cabecera_txt, modelo_txt,
                                   CARGA_ABORTO, _motivo_corto(e))
                    con.commit()
                    print(f"   · anotado en {TABLA_CENSO}: la carga del {fecha_foto} "
                          f"({len(cabecera_txt)} encabezados, modelo {modelo_txt}) "
                          f"ABORTO. La forma del informe que se rechaza tambien es un "
                          f"dato.", flush=True)
                except Exception as x:
                    try:
                        con.rollback()
                    except Exception:
                        pass
                    print(f"   ⚠️  y encima no se ha podido anotar en la libreta: {x}",
                          flush=True)
            else:
                print(f"   · ENSAYO: en modo aplicar esto habria dejado su fila en "
                      f"{TABLA_CENSO} ({len(cabecera_txt)} encabezados, ABORTO).",
                      flush=True)
        try:
            cur.close(); con.close()
        except Exception:
            pass
        sys.exit(1)

    # --- Guardas estructurales 1..7, 9 y 14 (sin escribir nada todavia) ---
    try:
        info = analizar(texto, fichero, fecha_foto)
        avisar_inbound(info)
    except Aborta as e:
        morir(e)

    filas = info['filas']

    # --- Lo que GRITA (Guarda 9): en el log Y en el dato ---
    if info['condiciones_raras']:
        print("\n⚠️  [Guarda 9] 'condition' fuera de 'New' (se guarda tal cual en la "
              "columna condition y se GRITA; NO aborta):", flush=True)
        for val, n in info['condiciones_raras'].most_common():
            print(f"        · {val!r} en {n} fila(s)", flush=True)
    if info['listing_raro']:
        print("\n⚠️  [Guarda 9] 'afn-listing-exists' fuera de 'Yes' en el informe "
              "(queda en crudo; NO aborta):", flush=True)
        for val, n in info['listing_raro'].most_common():
            print(f"        · {val!r} en {n} fila(s)", flush=True)
    if info['stores_con_valor']:
        print("\n🔴 [Guarda 9] 'store' VIENE CON VALOR, y en las 356 filas medidas el "
              "23-ago-2026 venía VACÍO en todas.", flush=True)
        print("     Vacío significaba «todas las tiendas»: el fichero traía el TOTAL "
              "EUROPEO. Con `store` relleno el informe está contando OTRA COSA — "
              "probablemente por tienda — y entonces las cifras de esta tabla YA NO "
              "son comparables con las de antes.", flush=True)
        print("     El valor queda en la columna `store` (no sólo aquí). PARA y míralo "
              "antes de que nadie use estos números.", flush=True)
        for val, n in info['stores_con_valor'].most_common(10):
            print(f"        · {val!r} en {n} fila(s)", flush=True)

    # --- Lo que trae y lo que no: las ESPERADAS ---
    if info['esperadas_ausentes']:
        print("\n[Contrato] El informe NO trae %d de las columnas esperadas:"
              % len(info['esperadas_ausentes']), flush=True)
        for h in info['esperadas_ausentes']:
            print(f"        · {h}", flush=True)
        print("     Su columna queda a NULO en toda la carga. NUNCA a cero: un 0 diria "
              "«no hay» y esto es «no se sabe».", flush=True)
    if info['esperadas_vacias']:
        print("\n[Contrato] Columnas esperadas que vienen con la celda en blanco "
              "(quedan a NULO):", flush=True)
        for h, n in info['esperadas_vacias'].most_common():
            print(f"        · {h} en {n} fila(s)", flush=True)

    # --- El precio que falta: se GRITA, no aborta (ver VACIO_ES_NULO) ---
    if info['precios_vacios']:
        print("\n[Guarda 6] %d ficha(s) llegan SIN PRECIO. `your_price` queda a NULO "
              "(no a 0: un cero seria un precio de cero euros, y la rentabilidad se "
              "calcula sobre el):" % len(info['precios_vacios']), flush=True)
        for sku_v, asin_v in info['precios_vacios'][:20]:
            print(f"        · sku {sku_v} · ASIN {asin_v}", flush=True)
        if len(info['precios_vacios']) > 20:
            print(f"        … y {len(info['precios_vacios']) - 20} mas", flush=True)
        print("     Un precio que desaparece es una ficha que ha cambiado de estado en "
              "Amazon. No tumba el inventario, pero se mira.", flush=True)

    # --- El testigo contra el criterio de la casa ---
    if info['onhand_discrepa']:
        print("\n🔴 [Testigo] Amazon se contradice a si mismo en %d ficha(s): su "
              "disponible calculado NO cuadra con vendible + transito."
              % len(info['onhand_discrepa']), flush=True)
        for sku_v, dice, sumamos in info['onhand_discrepa'][:20]:
            print(f"        · sku {sku_v}: Amazon dice {dice}, sumando sale {sumamos}",
                  flush=True)
        print("     Medido el 6-sep-2026: cuadraban las 381 de 381, desvio 0. Si esto "
              "sale, o Amazon se contradice o hemos entendido mal el reparto de "
              "estados. Las dos cosas hay que mirarlas.", flush=True)

    print(f"\nFilas leidas y cuadradas: {len(filas)} · fecha_foto {info['fecha_foto']}",
          flush=True)
    print(f"   · unidades totales (afn-total-quantity) : {info['total_unidades']}")
    print(f"   · EN TRANSITO (inbound_shipped)         : {info['total_inbound']} uds "
          f"en {info['asin_con_inbound']} ASIN", flush=True)
    # 🔑 La linea llana del transito entre centros: de donde sale, en castellano.
    if info['fc_origen'] == ORIGEN_INFORME:
        _con_fc = sum(1 for f in filas if (f['registro']['fc_transfer'] or 0) > 0)
        _uds_fc = sum(f['registro']['fc_transfer'] or 0 for f in filas)
        print(f"   · transito entre centros                : LEIDO DEL INFORME en las "
              f"{len(filas)} fichas ({_uds_fc} uds en {_con_fc} de ellas)", flush=True)
    else:
        print(f"   · transito entre centros                : DESCONOCIDO en las "
              f"{len(filas)} fichas — el informe de hoy no trae esa columna, asi que "
              f"queda a NULO y el disponible de esta foto es «al menos el vendible»",
              flush=True)
    print(f"   · modelo del disponible                 : {info['modelo_disponible']}"
          f"  (lo decide la version del informe, no una constante)", flush=True)
    _con_oh = sum(1 for f in filas if f['registro']['onhand_buyable'] is not None)
    print(f"   · disponible que calcula Amazon         : {_con_oh} de {len(filas)} "
          f"fichas lo traen", flush=True)

    # 🔒 ÁMBITO DE LA FOTO: ninguno. El fichero ES la tabla entera.
    AMBITO = None

    # Guardas de foto: anti-encogimiento y no-retroceder. ANTES de borrar y de
    # escribir. La anti-encogimiento es la RELATIVA (no protege la primera carga);
    # el suelo absoluto es la Guarda 4, arriba.
    try:
        previas = guarda_anti_encogimiento(cur, TABLA, len(filas), ambito=AMBITO,
                                           etiqueta='8 anti-encogimiento')
        guarda_no_retroceder(cur, TABLA, 'fecha_foto', info['fecha_foto'], ambito=AMBITO)
    except Aborta as e:
        morir(e)

    # ── GUARDA 11: el censo de la cabecera, y con el la VERSION del informe ──
    # 🔑 LA VERSION YA NO ES UN INTERRUPTOR, ES CONTEXTO. Hasta el encargo F esto
    #    decidia QUE comparaba la Guarda 10 (el almacen si la version era la misma, el
    #    vendible si no). Ya no hace falta: la Guarda 10 compara el DISPONIBLE, que se
    #    calcula igual en las dos versiones del informe. Pero saber que la carga de hoy
    #    y la de ayer son de versiones distintas sigue siendo lo primero que hay que
    #    leer cuando una cifra no cuadra, asi que se dice.
    cab_ant = cabecera_anterior(cur, info['fecha_foto'])
    avisar_censo(info['cabecera'], cab_ant)
    version_igual = misma_version(info['cabecera'], cab_ant)
    if cab_ant and not version_igual:
        print("     🔑 La carga anterior que ENTRO era de otra version del informe. "
              "El balance del dia se hace igual: compara el disponible, que es la "
              "misma cuenta a los dos lados.", flush=True)

    # ── LA FOTO ANTERIOR, EN CIFRAS ────────────────────────────────
    #    🔑 El disponible sale con la MISMA cuenta que `disponible_de()` en Python
    #       (SQL_DISPONIBLE). La Guarda 10 lo compara mas abajo, DESPUES del puente:
    #       sin el puente, el disponible de una foto sin transito no esta calculado
    #       todavia y la resta compararia dos cosas distintas.
    cur.execute(f"SELECT max(fecha_foto), count(*), coalesce(sum(available),0), "
                f"coalesce(sum(warehouse_quantity),0), coalesce(sum(fc_transfer),0), "
                f"coalesce(sum(inbound_shipped),0), "
                f"coalesce(sum({SQL_DISPONIBLE}),0) FROM {TABLA};")
    (fecha_ant, fichas_ant, vendible_ant, almacen_ant,
     fc_ant, inbound_ant, disponible_ant) = cur.fetchone()

    # ── GUARDA 13: ¿ha metido Amazon el transito DENTRO del vendible? ────────
    #    Va aqui porque necesita las dos fotos y el transito de la anterior, y
    #    porque si salta hay que parar ANTES de escribir un disponible doble.
    try:
        if fecha_ant is not None and fecha_ant != info['fecha_foto']:
            guarda_salto_a_transito_dentro(
                vendible_ant, info['vendible_total'], inbound_ant,
                info['inbound_total'], fc_ant, (info['fecha_foto'] - fecha_ant).days)
    except Aborta as e:
        morir(e)

    # ── EL PUENTE: estimar el disponible cuando el informe no trae el transito ──
    # 🔑 Va ANTES del cerrojo y ANTES de la Guarda 10, y las dos razones son buenas:
    #    si el cerrojo esta echado, el log dice igualmente que habria estimado — que es
    #    lo unico que permite ver si el puente esta sano el dia que haga falta abrirlo;
    #    y la Guarda 10 compara el disponible, que sin el puente no existe todavia en
    #    una foto que no trae el transito.
    _asines = sorted({f['registro']['asin'] for f in filas if f['registro']['asin']})
    intl = internacional_por_asin(cur, info['fecha_foto'], _asines)
    puente = estimar_disponible(filas, intl, info['fecha_foto'])
    print(f"\n--- EL PUENTE (disponible estimado) ---")
    print(f"   · el informe trae el transito en    : {puente['leido']} fichas "
          f"(ahi manda el dato leido, no la estimacion)")
    print(f"   · estimado desde el internacional en: {puente['estimado']} fichas "
          f"(+{puente['aporta_uds']} uds sobre el vendible)")
    print(f"   · en DESCONOCIDO                    : {puente['desconocido']} fichas "
          f"(sin fila de ese ASIN en el internacional; queda NULO, nunca 0)",
          flush=True)
    if puente['fuente_mas_vieja'] is not None:
        _viejo = (info['fecha_foto'] - puente['fuente_mas_vieja']).days
        # 🔑 Es UNA sola foto para toda la carga, asi que esta linea dice de que
        #    dia es el internacional entero con el que se ha estimado hoy.
        print(f"   · foto del internacional usada      : {puente['fuente_mas_vieja']} "
              f"({_viejo} dia(s) antes que esta foto)", flush=True)
        # 🔴 El aviso de la FUENTE VIEJA lo da ya `estimar_disponible()`, que sabe
        #    cuantas fichas afecta. Aqui habia un `if _viejo >= 3` que solo miraba los
        #    dias y callaba con uno o dos: un disponible estimado con la foto de
        #    anteayer es igual de viejo se avise o no.
    # 🔬 El falsador permanente del puente: los dias que el transito SI viene, el
    #    estimado y la verdad conviven y se comparan. Si esto crece, el puente se
    #    esta separando de la realidad y hay que enterarse antes de necesitarlo.
    if puente['discrepa']:
        _n = len(puente['discrepa'])
        _uds = sum(abs(e - c) for _, e, c in puente['discrepa'])
        print(f"   · CONTRASTE contra la verdad        : difiere en {_n} de "
              f"{puente['leido']} fichas leidas, {_uds} uds en total", flush=True)
        for _sku, _est, _cierto in sorted(
                puente['discrepa'], key=lambda t: -abs(t[1] - t[2]))[:10]:
            print(f"        · {_sku}: estimado {_est}, cierto {_cierto} "
                  f"({_est - _cierto:+d})", flush=True)

    # ── GUARDA 10: EL BALANCE DEL DIA ──────────────────────────────
    #    Va aqui, y no arriba con la lectura de la foto anterior, porque necesita el
    #    disponible de HOY — y el disponible de hoy no existe hasta que el puente ha
    #    pasado. Antes de escribir nada, que es lo que importa.
    disponible_nuevo = disponible_total(filas)
    salidas = None
    pelicula = None
    if fecha_ant is not None and fecha_ant != info['fecha_foto']:
        salidas = salidas_del_ledger(cur, fecha_ant, info['fecha_foto'])
        pelicula = caida_maxima_de_la_pelicula(cur)
        _dias = (info['fecha_foto'] - fecha_ant).days
        print(f"\n--- EL BALANCE DEL DIA (Guarda 10) ---")
        print(f"   · disponible                  : {disponible_ant} → "
              f"{disponible_nuevo}  ({disponible_nuevo - disponible_ant:+d} entre "
              f"el {fecha_ant} y el {info['fecha_foto']}, {_dias} dia(s))")
        print(f"   · el almacen, de contexto      : {almacen_ant} → "
              f"{info['almacen_total']}  (⚠️ no es comparable entre versiones "
              f"distintas del informe: el 7-sep-2026 dejo de incluir el transito)")
        # 🔑 LA COBERTURA, ANTES QUE EL VEREDICTO. El ledger no tiene reloj y su ultimo
        #    dia viene cortado a la hora de la descarga, asi que decir «que fuente puede
        #    opinar» es la primera pregunta, no un detalle del log.
        if salidas is None:
            print(f"   · ledger                       : NO SE PUEDE LEER")
        else:
            print(f"   · ledger                       : llega al "
                  f"{salidas['hasta_ledger']}, y su ultimo dia viene cortado, asi que "
                  f"completo hasta el {salidas['completo_hasta']}")
            print(f"   · ¿puede opinar el ledger?     : "
                  f"{'SI' if salidas['cubre'] else 'NO'}")
        if pelicula is not None:
            print(f"   · la pelicula del inventario   : {pelicula['saltos']} salto(s) "
                  f"de un dia, la peor caida {pelicula['peor']} uds")
        if salidas is not None and salidas['cubre']:
            _techo = salidas['uds'] + MARGEN_CAIDA_DIA * _dias
            print(f"   · OPINA EL LEDGER             : salieron {salidas['uds']} uds; "
                  f"caida maxima admitida {_techo} (mas {MARGEN_CAIDA_DIA} uds/dia de "
                  f"margen medido)", flush=True)
        elif pelicula is not None and pelicula['saltos'] >= MINIMO_SALTOS_PELICULA:
            _techo = int(pelicula['peor'] * FACTOR_PELICULA) * _dias
            print(f"   · OPINA LA PELICULA           : caida maxima admitida {_techo} "
                  f"({pelicula['peor']} x {FACTOR_PELICULA} x {_dias} dia(s))",
                  flush=True)
        else:
            print(f"   🔴 NO PUEDE OPINAR NADIE        : ni el ledger cubre ni la "
                  f"pelicula tiene {MINIMO_SALTOS_PELICULA} saltos de un dia",
                  flush=True)
        # ⚠️ Un event_type que nadie ha catalogado: ni cuenta como salida ni se descarta.
        #    Si saca stock, las salidas miden de menos y la guarda abortaria de mas.
        if salidas is not None and salidas['sin_catalogar']:
            print(f"   🔴 el ledger trae {len(salidas['sin_catalogar'])} tipo(s) de "
                  f"movimiento que este procesador no conoce: "
                  f"{', '.join(salidas['sin_catalogar'])}", flush=True)
            print(f"      No se cuentan ni se descartan solos. Miralos y ponlos en "
                  f"EVENTOS_QUE_SACAN o en EVENTOS_INTERNOS.", flush=True)
    try:
        guarda_continuidad(fecha_ant, info['fecha_foto'],
                           disponible_ant, disponible_nuevo,
                           fichas_ant, len(filas),
                           salidas=salidas, pelicula=pelicula)
    except Aborta as e:
        morir(e)

    # ── GUARDA 12: el cerrojo. Va la ULTIMA de las tres a proposito, para que el
    #    log ya haya dicho que version es y como va la continuidad antes de parar.
    # 🔑 Y los culpables se MIDEN aqui, contra la definicion viva de cada objeto en
    #    ESTA base: en staging y en produccion la respuesta puede ser distinta, y una
    #    lista escrita en el codigo contestaria lo mismo en las dos.
    culpables, ausentes = objetos_que_leen_nulo_como_cero(cur)
    print(f"\n--- QUIEN LEE EL TRANSITO (cerrojo de la Guarda 12) ---")
    print(f"   · consumidores mirados       : {len(CONSUMIDORES_DEL_TRANSITO)}")
    print(f"   · siguen haciendo COALESCE(fc_transfer, 0): "
          f"{', '.join(culpables) if culpables else 'ninguno'}", flush=True)
    if ausentes:
        print(f"   ⚠️  y {len(ausentes)} no existe(n) en esta base: "
              f"{', '.join(ausentes)}. No cuentan como culpables, pero mirelo: un "
              f"consumidor que se ha esfumado tambien es una noticia.", flush=True)
    try:
        guarda_transito_desconocido(info['fc_origen'], culpables)
    except Aborta as e:
        morir(e)

    # Claves que ya estaban (solo para contar altas). Antes del barrido.
    prev = claves_previas(cur, TABLA, ['sku'], ambito=AMBITO)

    cur.execute(sql_crear_tabla())
    # 🔒 La tabla tiene que estar CERRADA. Si no lo está, se aborta pidiendo la
    #    migración: aquí NO se activa RLS (era un lock exclusivo en cada carga).
    cur.execute(f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{TABLA}'::regclass;")
    if not cur.fetchone()[0]:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"RLS no está activa en {TABLA}. La tabla nace CERRADA por migración, no "
              f"por el procesador. Aplica migraciones/2026-08-23_inventario_fba.sql y "
              f"relanza.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # 🔒 Las columnas nuevas las pone la MIGRACION, no el `CREATE IF NOT EXISTS`
    #    de arriba (que sobre una tabla que ya existe no anade nada).
    try:
        exigir_columnas(cur, TABLA, ['onhand_buyable'] + DERIVADAS_COLS)
    except Aborta as e:
        morir(e)

    # 🔒 LA FOTO TIRA LA HOJA VIEJA: los sku que ya no vienen se BORRAN. Mismo
    # commit que la carga: o todo o nada. Las claves son EXACTAMENTE los valores
    # que el upsert va a escribir.
    claves_nuevas = [(f['registro']['sku'],) for f in filas]
    try:
        borradas = barrer_sobrantes(cur, TABLA, ['sku'], claves_nuevas, ambito=AMBITO)
    except Aborta as e:
        morir(e)

    # --- Volcar POR LOTES (execute_values, jamás fila a fila: el runner está en
    # EEUU y Supabase en Irlanda; cada execute() son ~90 ms de viaje) ---
    # 🔒 Sin dedup en Python: aquí un sku repetido es informe CORRUPTO y la
    #    Guarda 5 ya ABORTÓ por él. Deduplicar enmascararía justo lo que la guarda
    #    manda gritar (criterio de salud_fba/keepa, no el de paneu).
    cols = [c for _, c, _ in TIPADAS] + DERIVADAS_COLS + ['fichero', 'fecha_foto', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != 'sku')
    sql_upsert = (f"INSERT INTO {TABLA} ({', '.join(cols)}) VALUES %s "
                  f"ON CONFLICT (sku) DO UPDATE SET {upd}, procesado_at=now();")
    vals = [tuple([f['registro'][c] for _, c, _ in TIPADAS]
                  + [f['registro'][c] for c in DERIVADAS_COLS]
                  + [fichero, info['fecha_foto'], Json(f['crudo'])])
            for f in filas]
    execute_values(cur, sql_upsert, vals, template=f"({ph})", page_size=500)

    altas = sum(1 for f in filas if (f['registro']['sku'],) not in prev)

    # --- HISTÓRICO: apilar esta foto (cajón PELÍCULA) ---
    # 🔴 POR QUÉ EXISTE: la tabla de arriba es FOTO y tira la hoja vieja en cada
    #    carga. Sin esto, la lectura de hoy desaparece mañana y no hay de dónde
    #    sacarla — ni tendencias, ni «qué cambió desde ayer», ni la serie de
    #    `inbound_shipped`, que es lo único que dice CUÁNDO salió y CUÁNDO llegó un
    #    envío. Una cifra que se mueve sin serie no cuenta una historia.
    # 🔒 Se APILA, jamás se borra: aquí no hay barrido. La misma pareja que
    #    inventario_internacional / inventario_internacional_historico.
    # 🔴 SIN `crudo`, y es decisión: el .txt entero se conserva en
    #    informes/inventario_fba/ (por eso esos ficheros NO SE BORRAN NUNCA), así
    #    que la despensa común del histórico vive en el Storage, no duplicada en
    #    la base. El rescate va por la columna `fichero`.
    cur.execute(sql_crear_tabla_historico())
    cur.execute(f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{TABLA_HIST}'::regclass;")
    if not cur.fetchone()[0]:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"RLS no está activa en {TABLA_HIST}. La tabla nace CERRADA por migración, "
              f"no por el procesador. Aplica "
              f"migraciones/2026-08-23_inventario_fba_historico.sql y relanza.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    try:
        exigir_columnas(cur, TABLA_HIST, ['onhand_buyable'] + DERIVADAS_COLS)
    except Aborta as e:
        morir(e)

    def _val_hist(f, col):
        if col == 'fecha_foto': return info['fecha_foto']
        if col == 'fichero':    return fichero
        return f['registro'][col]

    # 🔒 Dedup por la clave REAL del histórico (sku, fecha_foto), derivada con el
    #    MISMO `_val_hist` que escribe los valores: así la clave del dedup nunca se
    #    separa de la del ON CONFLICT. Hoy la Guarda 5 ya aborta por sku duplicado,
    #    o sea que esto no debería descartar nada nunca — y si algún día descarta,
    #    lo GRITA en vez de tragárselo en silencio.
    dedup = {}
    for f in filas:
        dedup[tuple(_val_hist(f, c) for c in HIST_PK)] = f
    filas_hist = list(dedup.values())
    if len(filas_hist) != len(filas):
        print(f"⚠️ {len(filas) - len(filas_hist)} filas duplicadas por {HIST_PK} en "
              f"{TABLA_HIST}, me quedo con la última. (Ojo: la Guarda 5 debería haber "
              f"abortado antes por sku duplicado — míralo.)", flush=True)

    ph_h  = ", ".join(['%s'] * len(HIST_COLS))
    set_h = ", ".join(f"{c}=EXCLUDED.{c}" for c in HIST_COLS if c not in HIST_PK)
    sql_hist = (f"INSERT INTO {TABLA_HIST} ({', '.join(HIST_COLS)}) VALUES %s "
                f"ON CONFLICT (sku, fecha_foto) DO UPDATE SET {set_h}, capturado_en=now();")
    vals_hist = [tuple(_val_hist(f, c) for c in HIST_COLS) for f in filas_hist]
    execute_values(cur, sql_hist, vals_hist, template=f"({ph_h})", page_size=500)

    cur.execute(f"SELECT count(*) FROM {TABLA_HIST} WHERE fecha_foto=%s;", (info['fecha_foto'],))
    hist_hoy = cur.fetchone()[0]
    cur.execute(f"SELECT count(DISTINCT fecha_foto), min(fecha_foto), max(fecha_foto) FROM {TABLA_HIST};")
    hist_fechas, hist_desde, hist_hasta = cur.fetchone()
    print(f"\n--- HISTORICO {TABLA_HIST} (cajon PELICULA) ---")
    print(f"   · filas apiladas de esta foto ({info['fecha_foto']}): {hist_hoy}")
    print(f"   · fechas acumuladas: {hist_fechas} (de {hist_desde} a {hist_hasta})", flush=True)

    # 🔒 El fotograma de hoy tiene que cuadrar con la foto viva, AL DÍGITO. Si no,
    #    algo se quedó por el camino y la película empieza a mentir desde el primer
    #    día — que es cuando menos se nota.
    if hist_hoy != len(filas):
        morir(Aborta(f"La foto trae {len(filas)} filas y el fotograma de "
                     f"{info['fecha_foto']} tiene {hist_hoy}. No cuadran."))

    # --- LA LIBRETA DE ESTA CARGA (Guarda 11, cajon PELICULA) ---
    # 🔑 La fila de la carga que ENTRA va DENTRO de la transaccion de datos, para
    #    que no pueda quedar un 'cargada' de una carga que luego se revierte. La de la
    #    carga que aborta la escribe `morir()`, en una transaccion propia. Dos
    #    caminos, un solo escritor: `anotar_libreta()`.
    anotar_libreta(cur, info['fecha_foto'], fichero, info['cabecera'],
                   info['modelo_disponible'], CARGA_ENTRO)
    print(f"\n--- LIBRETA DE CARGAS {TABLA_CENSO} ---")
    print(f"   · {len(info['cabecera'])} encabezados anotados para la foto del "
          f"{info['fecha_foto']} · modelo {info['modelo_disponible']} · "
          f"resultado {CARGA_ENTRO}", flush=True)

    # --- La verificación que importa, DENTRO de la transacción ---
    # 🔒 El log dice lo que el procesador cree; esto lee lo que la tabla tiene.
    cur.execute(f"SELECT count(*), coalesce(sum(inbound_shipped),0), "
                f"count(DISTINCT asin) FILTER (WHERE inbound_shipped > 0) FROM {TABLA};")
    n_bd, inbound_bd, asin_bd = cur.fetchone()
    print(f"\n--- LO QUE HAY EN LA TABLA (leido de {TABLA}, no del log) ---")
    print(f"   · filas            : {n_bd}")
    print(f"   · inbound_shipped  : {inbound_bd} uds en {asin_bd} ASIN", flush=True)
    if (n_bd, inbound_bd) != (len(filas), info['total_inbound']):
        morir(Aborta(f"La tabla dice ({n_bd} filas, {inbound_bd} uds) y el fichero "
                     f"decía ({len(filas)}, {info['total_inbound']}). No cuadran al "
                     f"dígito: algo se ha quedado por el camino."))

    print(resumen_foto(TABLA, AMBITO, previas, len(filas), altas, borradas, MODO),
          flush=True)

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {len(filas)} filas en {TABLA} "
              f"({info['total_inbound']} uds en transito).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(La carga se ha probado entera dentro de una transaccion revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · filas={len(filas)} · "
          f"altas={altas} · bajas={borradas} · en_transito={info['total_inbound']} "
          f"en {info['asin_con_inbound']} ASIN ===", flush=True)


if __name__ == '__main__':
    main()
