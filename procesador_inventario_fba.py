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
# 🔒 ESTO **AÑADE** UNA FUENTE. No quita ninguna: `procesador_salud_fba.py` no
#    se toca (ni su salvaguarda anti-omisión ni sus guardas), ni se toca ninguna
#    tabla existente. Nadie lee `inventario_fba` todavía.
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

BUCKET, CARPETA = 'informes', 'inventario_fba'
TABLA = 'inventario_fba'

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

# El ancho exacto del fichero. Una fila con otro número de columnas es un fichero
# cortado a media línea — el detector de truncamiento que a salud_fba le faltó, y
# es un INVARIANTE, no un número inventado.
N_COLUMNAS = 26

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
CABECERA_ESPERADA = [h for h, _, _ in TIPADAS]

# Las numéricas que NO pueden faltar: son el inventario. Un hueco aquí no es un
# 0, es un informe que dejó de decir lo que decía → ABORTA (Guarda 6).
NUMERICAS = [(h, c, t) for h, c, t in TIPADAS if t in ('i', 'n')]

# Hoy el informe solo trae esto. Otro valor NO aborta: se GRITA (Guarda 9).
CONDITION_CONOCIDA = 'New'
AFN_LISTING_CONOCIDO = 'Yes'


def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()


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
# DDL: la tabla la crea la MIGRACIÓN (nace CERRADA: RLS on, 0 políticas, revoke
# a public/anon/authenticated). Aquí sólo el IF NOT EXISTS idempotente, como en
# las otras cañerías — y la COMPROBACIÓN de que está cerrada, que sí aborta.
# 🔒 `ENABLE RLS` NO se lanza aquí: pide AccessExclusiveLock EN CADA CARGA y ése
#    es el lock que tumbó la base el 28-jul. Vive en la migración.
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n        ".join(f"{c} {TIPO_SQL[t]}" for _, c, t in TIPADAS)
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

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    # 🔒 La pregunta anti-cero, hecha código: si no hay ficheros, todo lo de abajo
    #    saldría «bien» sin haber medido nada.
    exigir_poblacion(f"ficheros .txt en el buzon {BUCKET}/{CARPETA}/ "
                     f"(informe «Gestion de inventario de Logistica de Amazon»)", txts)
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    elegido = txts[0]
    fichero = elegido['name']
    print(f"Informe elegido (el mas reciente de {len(txts)}): {fichero}", flush=True)

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

    # --- Guardas estructurales 1..7 y 9 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero, fecha_foto)
        avisar_inbound(info)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

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

    print(f"\nFilas leidas y cuadradas: {len(filas)} · fecha_foto {info['fecha_foto']}",
          flush=True)
    print(f"   · unidades totales (afn-total-quantity) : {info['total_unidades']}")
    print(f"   · EN TRANSITO (inbound_shipped)         : {info['total_inbound']} uds "
          f"en {info['asin_con_inbound']} ASIN", flush=True)

    # --- Conectar al ENTORNO ---
    con = conectar_bd(DB_URL)
    con.autocommit = False
    cur = con.cursor()

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
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

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

    # 🔒 LA FOTO TIRA LA HOJA VIEJA: los sku que ya no vienen se BORRAN. Mismo
    # commit que la carga: o todo o nada. Las claves son EXACTAMENTE los valores
    # que el upsert va a escribir.
    claves_nuevas = [(f['registro']['sku'],) for f in filas]
    try:
        borradas = barrer_sobrantes(cur, TABLA, ['sku'], claves_nuevas, ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Volcar POR LOTES (execute_values, jamás fila a fila: el runner está en
    # EEUU y Supabase en Irlanda; cada execute() son ~90 ms de viaje) ---
    # 🔒 Sin dedup en Python: aquí un sku repetido es informe CORRUPTO y la
    #    Guarda 5 ya ABORTÓ por él. Deduplicar enmascararía justo lo que la guarda
    #    manda gritar (criterio de salud_fba/keepa, no el de paneu).
    cols = [c for _, c, _ in TIPADAS] + ['fichero', 'fecha_foto', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != 'sku')
    sql_upsert = (f"INSERT INTO {TABLA} ({', '.join(cols)}) VALUES %s "
                  f"ON CONFLICT (sku) DO UPDATE SET {upd}, procesado_at=now();")
    vals = [tuple([f['registro'][c] for _, c, _ in TIPADAS]
                  + [fichero, info['fecha_foto'], Json(f['crudo'])])
            for f in filas]
    execute_values(cur, sql_upsert, vals, template=f"({ph})", page_size=500)

    altas = sum(1 for f in filas if (f['registro']['sku'],) not in prev)

    # --- La verificación que importa, DENTRO de la transacción ---
    # 🔒 El log dice lo que el procesador cree; esto lee lo que la tabla tiene.
    cur.execute(f"SELECT count(*), coalesce(sum(inbound_shipped),0), "
                f"count(DISTINCT asin) FILTER (WHERE inbound_shipped > 0) FROM {TABLA};")
    n_bd, inbound_bd, asin_bd = cur.fetchone()
    print(f"\n--- LO QUE HAY EN LA TABLA (leido de {TABLA}, no del log) ---")
    print(f"   · filas            : {n_bd}")
    print(f"   · inbound_shipped  : {inbound_bd} uds en {asin_bd} ASIN", flush=True)
    if (n_bd, inbound_bd) != (len(filas), info['total_inbound']):
        print(f"\n❌ ABORTA: la tabla dice ({n_bd} filas, {inbound_bd} uds) y el fichero "
              f"decía ({len(filas)}, {info['total_inbound']}). No cuadran al dígito: algo "
              f"se ha quedado por el camino.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

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
