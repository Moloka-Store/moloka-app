# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR TRANSACCIONES — el EXTRACTO de euros de Amazon (Fase 0, MULTIPAÍS)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el "Custom Transaction Report" del Seller (Pagos → Todas las transacciones,
#   .csv, uno por marketplace ES/IT/FR/DE) del buzón informes/transacciones/ y carga
#   TODOS los movimientos —pedidos, reembolsos, ajustes, tarifas de stock, saldos,
#   transferencias— en la tabla `transacciones_movimientos`.
#
#   Es el ÚNICO informe que trae los EUROS que Amazon cobró de verdad: la comisión
#   (tarifas de venta) y la logística FBA, céntimo a céntimo. PELÍCULA, no foto.
#
# 🔒 EL CARGADOR NO INTERPRETA (regla del encargo, §4)
#   La comisión y las tarifas se guardan TAL CUAL vienen, en euros, con su signo,
#   SIN dividir entre 1,21. El 1,21, el pvd, los 0,15 €/ud de almacén y la cascada
#   de comisión son SUPUESTOS y viven en la VISTA (PR-C), donde se pueden discutir
#   sin tocar el dato. Aquí solo se tipa (texto→número) y se apila.
#
# 🔴 EL PAÍS LO MANDA EL SELECTOR, NUNCA EL FICHERO (decisión de Fernando, §3.1)
#   El país entra por el input PAIS del workflow y se escribe en una COLUMNA de
#   primera clase. No se deduce por el idioma de la cabecera (se rompería si Amazon
#   cambia una palabra). El fichero SÍ trae una columna 'web de Amazon'/'Marketplace'
#   (amazon.es/fr/it), vacía en las filas de tarifas de cuenta. Se usa solo como
#   GUARDA: si una fila trae un marketplace que NO cuadra con PAIS → ABORTA (es el
#   fallo "Francia dentro de España" que documentó la auditoría de la v1).
#   Y si PAIS es el equivocado, la resolución de columnas por idioma ya no encuentra
#   las columnas de ese país y ABORTA sola: doble red.
#
# 🔴 POR QUÉ CARGA POR RANGO (idéntico al ledger, medido contra el fichero real)
#   NO hay llave natural única: la cuaterna (pedido, sku, tipo, fecha) se repite
#   (602 casos en ES) y hay filas IDÉNTICAS campo por campo (15 en ES). Igual que
#   el ledger. Consecuencia:
#     ❌ NO patrón foto (barrer_sobrantes): borraría el histórico.
#     ❌ NO append por PK de campos: colapsaría las idénticas, PERDIENDO movimientos.
#     ✅ CARGA POR RANGO Y PAÍS (recerrar un periodo de un marketplace):
#        1) hallar [fecha_min, fecha_max] de la columna de fecha del fichero;
#        2) en UNA transacción:
#             DELETE FROM transacciones_movimientos
#                 WHERE fecha BETWEEN min AND max AND pais = <el del selector>;
#           y luego INSERT de TODOS los movimientos (PK sintética id IDENTITY);
#        3) commit si aplicar, rollback si ensayo.
#   Idempotente: recargar el mismo fichero deja lo mismo. Lo anterior a fecha_min y
#   los OTROS países quedan intactos. Cura de paso el bug de los 17 €: el informe
#   trae transacciones DIFERIDAS (columna Estado) que cambian entre dos descargas;
#   recerrar el rango hace ganar a la última descarga.
#
# 🔴 GUARDA 8 (el extracto no encoge) — POR QUÉ LA GUARDA 5 NO BASTABA
#   La Guarda 5 mira SOLO el total del rango y tolera hasta un 50% de merma. Un año
#   exportado con UN MES EN BLANCO en medio conserva fmin=enero y fmax=diciembre, el
#   total sigue muy por encima del 50%, la 5 pasa… y entonces el DELETE se lleva los
#   doce meses mientras el INSERT devuelve once. Ese mes desaparecía del extracto sin
#   que chillara nadie. La Guarda 8 compara lo que de verdad se BORRA con lo que de
#   verdad ENTRA: si el TOTAL del rango encoge, ABORTA.
#
#   🔴 POR QUÉ NO BASTA EL TOTAL, Y CÓMO DECIDE POR DÍA (8a) + LA RED (8b)
#   Mirando solo TOTALES no se ve una merma en un día si otro tramo del mismo rango la
#   compensa. Medido el 30-jul en el ledger contra dos exportaciones del mismo informe:
#   de 89 días solapados, 88 traían las mismas filas y el 2026-07-20 traía 281 en una y
#   176 en otra. Aquí pasa lo mismo. Por eso la Guarda 8 decide POR DÍA:
#     · 8a — recuento BD vs FICHERO día a día (por rango Y PAÍS). Día de EN MEDIO que
#       encoge o desaparece → ABORTA antes del DELETE. Día del BORDE que encoge → se
#       ESTRECHA el rango (puede ser un corte legítimo si acaba en el día en curso),
#       condicional: solo si de verdad encoge.
#     · 8b — red de última hora sobre el total del rango efectivo; con la 8a activa es
#       inalcanzable, existe por si la 8a falla o hay escritura concurrente.
#   ⚠️ Tolerancia CERO por ahora, con una exposición conocida y MEDIDA a las diferidas;
#   el detalle y el experimento pendiente están junto a la Guarda 8a, en el cuerpo.
#   🔒 TODO va por rango Y PAÍS: comparar contra otros países haría que cargar FR (243
#   filas) pareciera un derrumbe frente a ES (13.658) y abortaría siempre.
#   🔒 Los días se comparan BD-contra-FICHERO, JAMÁS contra el calendario: hay días
#   sin ninguna transacción que son perfectamente legítimos (medido el 30-jul: IT solo
#   tiene movimiento en 64 de sus 201 días de calendario, FR en 59 de 112). Un detector
#   por calendario daría 137 falsos positivos solo en IT.
#
# 🔒 El SELLO DE FRESCURA: al aplicar, escribe una fila en `informes_subidos`
#   (tipo='transacciones', fecha_dato_hasta, procesado_at). Es lo que lee la RPC
#   frescura_informes() para esta tarjeta. Con el fichero en informes/transacciones/
#   (subido_buzon) la tarjeta deja de salir gris.
#
# Encoding utf-8-sig (BOM MEDIDO en los 3 ficheros el 28-jul), fallback cp1252.
#   Separador coma. Cabecera tras ~9 filas de metadatos.
# ============================================================================

import os, sys, io, csv, re, unicodedata
from datetime import date, datetime, timedelta
from collections import Counter

import psycopg2
from psycopg2.extras import Json, execute_values

# Del patrón común solo se reutiliza Aborta: la carga por rango es lógica propia
# (barrer_sobrantes es para FOTOS y aquí borraría el histórico) — igual que el ledger.
from foto_comun import Aborta, conectar_bd, listar_buzon, descargar_buzon, refrescar_vistas

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion
PAIS         = os.environ.get('PAIS', '').strip().upper()             # ES | IT | FR (selector)
FICHERO      = os.environ.get('FICHERO', '').strip()                  # nombre EXACTO; vacío = más reciente

BUCKET, CARPETA = 'informes', 'transacciones'
# 🔴 ALEMANIA ENTRA AQUÍ EL 20-ago-2026, y hasta hoy NO era que se descartara: es que no
#    se podía ni elegir. El selector tenía tres opciones, así que el fichero alemán no se
#    había descargado nunca — y de ahí salían dos cosas que parecían hechos y eran huecos:
#      · el ISD alemán del 3 %, «supuesto por prudencia» porque *«no hay ni una venta
#        alemana en transacciones_movimientos»*. No las hay porque falta el fichero.
#      · `v_velocidad_ventas_paneu.uds_30d_de`, que es
#        `sum(cantidad) FILTER (WHERE pais = 'DE')` sobre esta tabla. Sin una sola fila
#        alemana esa columna vale CERO para todos los ASIN, siempre. No falla: devuelve
#        cero, y un cero parece un dato.
PAISES_VALIDOS = ('ES', 'IT', 'FR', 'DE')

# ---------------------------------------------------------------------------
# Mapa por país: aliases de cada columna canónica (normalizados SIN acentos y en
# minúsculas). Cabeceras reales medidas contra los 3 ficheros el 28-jul-2026.
# La resolución acepta coincidencia EXACTA o por prefijo (startswith), como la v1.
# ---------------------------------------------------------------------------
COLS_ALIAS = {
    'ES': {
        'fecha':            ['fecha y hora'],
        'tipo':             ['tipo'],
        'numero_pedido':    ['numero de pedido'],
        'identificador_pago': ['identificador de pago'],
        'sku':              ['sku'],
        'descripcion':      ['descripcion'],
        'cantidad':         ['cantidad'],
        'marketplace':      ['web de amazon'],
        'ventas_producto':  ['ventas de productos'],
        'impuesto_producto': ['impuesto de ventas de productos'],
        'tarifa_venta':     ['tarifas de venta'],
        'tarifa_fba':       ['tarifas de logistica de amazon'],
        'tarifa_otras':     ['tarifas de otras transacciones'],
        'otro':             ['otro'],
        'total':            ['total'],
        'estado':           ['estado de la transaccion'],
        'fecha_liberacion': ['fecha de liberacion de la transaccion'],
    },
    'IT': {
        'fecha':            ['data/ora'],
        'tipo':             ['tipo'],
        'numero_pedido':    ['numero ordine'],
        'identificador_pago': ['numero pagamento'],
        'sku':              ['sku'],
        'descripcion':      ['descrizione'],
        'cantidad':         ['quantita'],
        'marketplace':      ['marketplace'],
        'ventas_producto':  ['vendite'],
        'impuesto_producto': ['imposta sulle vendite dei prodotti'],
        'tarifa_venta':     ['commissioni di vendita'],
        'tarifa_fba':       ['costi del servizio logistica di amazon'],
        'tarifa_otras':     ['altri costi relativi alle transazioni'],
        'otro':             ['altro'],
        'total':            ['totale'],
        'estado':           ['stato della transazione'],
        'fecha_liberacion': ['data di rilascio della transazione'],
    },
    'FR': {
        'fecha':            ['date/heure'],
        'tipo':             ['type'],
        'numero_pedido':    ['numero de la commande'],
        'identificador_pago': ['numero de versement'],
        'sku':              ['sku'],
        'descripcion':      ['description'],
        'cantidad':         ['quantite'],
        'marketplace':      ['marketplace'],
        'ventas_producto':  ['ventes de produits'],
        'impuesto_producto': ['taxes sur la vente des produits'],
        'tarifa_venta':     ['frais de vente'],
        'tarifa_fba':       ['frais expedie par amazon'],
        'tarifa_otras':     ['autres frais de transaction'],
        'otro':             ['autre'],
        'total':            ['total'],
        'estado':           ['statut de la transaction'],
        'fecha_liberacion': ['date de sortie de la transaction'],
    },
    # 🔴 ALEMANIA VA VACÍA A PROPÓSITO, Y NO ES UN OLVIDO.
    #
    #    Las cabeceras de los otros tres están MEDIDAS contra los ficheros reales (28-jul).
    #    Del alemán no hay fichero todavía, así que aquí no hay nada que medir — y la regla
    #    de la casa es que un mapa de columnas no se traduce a ojo. No es escrupulosidad:
    #    la resolución acepta coincidencia POR PREFIJO, así que un alias inventado puede
    #    casar con la columna de al lado y meter el importe equivocado en una columna de
    #    dinero. Eso no daría error: cargaría cifras falsas con aspecto de buenas.
    #
    # 🔑 POR ESO LA PRIMERA CARGA ALEMANA ES UNA MEDICIÓN, no un intento fallido: la
    #    Guarda 2 aborta ANTES de tocar nada e imprime la cabecera real del fichero. Con
    #    esa línea se rellena este mapa con valores medidos y la segunda carga entra.
    #    Un `ensayo` basta: no hace falta arriesgar un `aplicar`.
    'DE': {},
}

# Columnas cuya AUSENCIA aborta (las que la vista PR-C necesita para la fórmula).
# El resto son opcionales: si no aparecen, quedan NULL (el crudo conserva todo).
COLS_OBLIGATORIAS = ('fecha', 'tipo', 'sku', 'cantidad', 'ventas_producto',
                     'impuesto_producto', 'tarifa_venta', 'tarifa_fba',
                     'tarifa_otras', 'total')

# Tipo de movimiento CANÓNICO (literal del idioma → canon). El `tipo` crudo queda intacto
# para auditar; `tipo_norm` es lo que lee la vista, para no cablear literales por idioma
# (el techo de la v1 con su `for pais in ('IT','FR')`: el día que entre DE, se caería solo).
# 🔴 Los canon están MEDIDOS contra producción (descripciones reales), no traducidos a ojo:
#   · reembolso_inventario (Ajuste ES / Modifica IT): NO son ajustes contables, son
#     INDEMNIZACIONES de Amazon por inventario perdido/dañado/no devuelto (+374,54 €, con SKU
#     al 100%, imputables a producto). Llamarlo 'ajuste' escondería ese dinero.
#   · ajuste_tarifa (Ajuste de tarifa ES) SEPARADO de reembolso_inventario: medido, lleva SKU
#     0/44 (no imputable a producto) frente a 122/122 del otro. Mezclarlos rompe el análisis
#     por SKU. (Los 44 son 'cambio de peso y dimensión', 1-10 jun, todos a favor: +54,90 €.)
# Un literal SIN canon → tipo_norm NULL y se GRITA en el resumen (así DE no entra en silencio).
# 🔴 Y ESO LE TOCA A ALEMANIA EN LA PRIMERA CARGA: aquí no hay ni un literal alemán, porque
#    tampoco hay fichero contra el que medirlos. Consecuencia dicha, porque no es obvia y
#    es la que decide si el arreglo sirve de algo: `tipo_norm` a NULL significa que la vista
#    NO cuenta esas filas, y `v_velocidad_ventas_paneu` filtra por `tipo_norm = 'pedido'`.
#    O sea que cargar el fichero alemán SIN rellenar esto deja `uds_30d_de` valiendo cero
#    igual que antes — la bomba seguiría armada, sólo que con datos dentro.
#    El grito del resumen trae los literales exactos con su recuento: de ahí salen medidos.
TIPO_CANON = {
    'Pedido': 'pedido', 'Ordine': 'pedido', 'Commande': 'pedido',
    'Reembolso': 'reembolso', 'Rimborso': 'reembolso', 'Remboursement': 'reembolso',
    'Ajuste': 'reembolso_inventario', 'Modifica': 'reembolso_inventario',
    'Ajuste de tarifa': 'ajuste_tarifa',
    'Transferir': 'transferencia', 'Trasferimento': 'transferencia', 'Transfert': 'transferencia',
    'Tarifas de inventario de Logística de Amazon': 'tarifa_inventario',
    'Costo di stoccaggio Logistica di Amazon': 'tarifa_inventario',
    'Frais de stock Expédié par Amazon': 'tarifa_inventario',
    'Tarifas de transacción de Logística de Amazon': 'tarifa_transaccion_fba',
    'Commissioni per le transazioni di Logistica di Amazon': 'tarifa_transaccion_fba',
    'Frais de transaction Expédié par Amazon': 'tarifa_transaccion_fba',
    'Tarifa de prestación de servicio': 'tarifa_servicio',
    'Saldo descubierto': 'saldo', 'Saldo negativo': 'saldo', 'Solde négatif': 'saldo',
}

# Columnas tipadas de la tabla, en el orden del INSERT (id IDENTITY y procesado_at aparte).
COLS_DB = ['pais', 'fecha', 'fecha_hora', 'tipo', 'tipo_norm', 'numero_pedido', 'identificador_pago',
           'sku', 'descripcion', 'cantidad', 'marketplace',
           'ventas_producto', 'impuesto_producto', 'tarifa_venta', 'tarifa_fba',
           'tarifa_otras', 'otro', 'total', 'estado', 'fecha_liberacion', 'fichero', 'crudo']

# marketplace → país, para la GUARDA de coherencia (no para detectar).
MKT_A_PAIS = {'amazon.es': 'ES', 'amazon.fr': 'FR', 'amazon.it': 'IT', 'amazon.de': 'DE'}

# Nombres de mes por idioma (los del informe: '31 dic 2025', '7 avr. 2026', '8 gen 2026').
MESES_ES = {'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,'jul':7,'ago':8,'sep':9,'oct':10,'nov':11,'dic':12}
MESES_IT = {'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12}
MESES_FR = {'janv':1,'fevr':2,'mars':3,'avr':4,'mai':5,'juin':6,'juil':7,'aout':8,'sept':9,'oct':10,'nov':11,'dec':12}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()

def _sin_acentos(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def _norm(s):
    """Normaliza una cabecera: sin acentos, minúsculas, sin ':' final, recortada."""
    return _sin_acentos(_clean(s)).lower().rstrip(':').strip()

def txt(v):
    s = _clean(v)
    return s or None

def num_o_null(v):
    """Importe europeo → float, o None si viene vacío. Conserva el SIGNO tal cual.
    Acepta coma decimal y punto de miles ('1.234,56'); '' y '-' → None."""
    s = _clean(v)
    if s in ('', '-'):
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None

def ent_o_null(v):
    """Entero o None (cantidad viene vacía en las filas de tarifas de cuenta)."""
    f = num_o_null(v)
    return int(f) if f is not None else None

def parse_fecha_pais(s, pais):
    """'31 dic 2025 23:21:47 UTC' / '7 avr. 2026 ...' / '8 gen 2026 ...' → date. None si no casa."""
    if not s:
        return None
    m = re.match(r'(\d+)\s+([^\s]+)\s+(\d{4})', str(s).strip())
    if not m:
        return None
    dia, mes_tok, anyo = m.groups()
    tok = _sin_acentos(mes_tok).lower().strip('.').strip()
    if pais == 'ES':
        mm = MESES_ES.get(tok[:3])
    elif pais == 'IT':
        mm = MESES_IT.get(tok[:3])
    else:  # FR: 'juin'/'juil' comparten prefijo de 3 → match por token completo o prefijo
        mm = MESES_FR.get(tok)
        if not mm:
            for clave, num in MESES_FR.items():
                if tok.startswith(clave) or clave.startswith(tok):
                    mm = num; break
    if not mm:
        return None
    try:
        return date(int(anyo), mm, int(dia))
    except ValueError:
        return None

def parse_fecha_hora(s, pais):
    """La misma cadena con hora: → datetime (UTC). None si no hay hora. Leniente."""
    if not s:
        return None
    m = re.match(r'(\d+)\s+([^\s]+)\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})', str(s).strip())
    d = parse_fecha_pais(s, pais)
    if not m or not d:
        return None
    from datetime import timezone
    return datetime(d.year, d.month, d.day, int(m.group(4)), int(m.group(5)),
                    int(m.group(6)), tzinfo=timezone.utc)


def _tramos_de_dias(dias):
    """Agrupa fechas sueltas en tramos consecutivos: del 1 al 30 de junio → un tramo."""
    tramos = []
    for d in sorted(dias):
        if tramos and d == tramos[-1][1] + timedelta(days=1):
            tramos[-1][1] = d
        else:
            tramos.append([d, d])
    return tramos

def texto_dias(dias):
    """Los días, en cristiano y en una línea. Es lo que convierte el aviso en útil:
    'falta 2026-06-01→2026-06-30 (30 días)' se lee de un vistazo; treinta fechas
    seguidas, no. (Se duplica en procesador_ledger.py a propósito: foto_comun es el
    patrón de las FOTOS y estos dos son PELÍCULAS — no se toca.)"""
    partes = []
    for a, b in _tramos_de_dias(dias):
        partes.append(str(a) if a == b else f"{a}→{b} ({(b - a).days + 1} días)")
    return " · ".join(partes)


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales. Sin tocar la base todavía.
# ---------------------------------------------------------------------------
def _resolver_columna(cabecera, cab_norm, alias_list):
    # EXACTO primero, y solo si ninguno casa exacto se prueba por PREFIJO. Es
    # deliberado: el alias 'autre' (col 'otro' en FR) es prefijo de 'autres frais
    # de transaction' (que es tarifa_otras). Con prefijo-primero, 'autre' capturaría
    # la columna equivocada porque aparece antes. Con exacto-primero, cada una casa
    # con la suya. Ningún alias actual depende del prefijo (todos casan exacto tras
    # _norm), así que esto NO cambia ninguna resolución previa; solo blinda 'otro'.
    for alias in alias_list:
        for real, norm in zip(cabecera, cab_norm):
            if norm == alias:
                return real
    for alias in alias_list:
        for real, norm in zip(cabecera, cab_norm):
            if norm.startswith(alias):
                return real
    return None

def analizar(texto, pais, fichero):
    if pais not in PAISES_VALIDOS:
        raise Aborta(f"[PAIS] {pais!r} no es uno de {PAISES_VALIDOS}. El país lo manda el "
                     f"selector del workflow y no se asume: sin país determinado, ABORTA (§3.1).")

    lector = csv.reader(io.StringIO(texto))
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 1: encontrar la cabecera (tras ~9 filas de metadatos). Primera fila con
    # ≥15 columnas que contenga una columna de tipo/type.
    # 🔴 LA PALABRA DE LA COLUMNA DE TIPO VA POR IDIOMA, y hasta el 20-ago-2026 la
    #    lista eran dos: 'tipo' (ES/IT) y 'type' (FR). En alemán es 'Typ', así que un
    #    fichero DE no llegaba ni a la Guarda 2: moría aquí preguntando «�es un Custom
    #    Transaction Report?» — que es mandar a buscar el fallo donde no está.
    # 🔒 Ampliar esta lista es seguro: solo sirve para ENCONTRAR la fila de cabecera. Quién
    #    es cada columna lo decide COLS_ALIAS, y eso sigue exigiendo valores medidos.
    CAB_TIPO = ('tipo', 'type', 'typ')
    cab_idx, cabecera = None, None
    for i, f in enumerate(filas[:30]):
        norm = [_norm(c) for c in f]
        if len(f) >= 15 and any(n in CAB_TIPO for n in norm):
            cab_idx, cabecera = i, f
            break
    if cab_idx is None:
        # 🔑 SE ENSEÑA LO QUE SÍ SE HA VISTO. Un «no la encuentro» a secas obliga a abrir el
        #    CSV a mano; con la fila más ancha delante se ve en un vistazo si es que el
        #    informe no es el que toca, o es que su columna de tipo se llama de otra forma
        #    — y entonces se añade a CAB_TIPO con el literal medido, no traducido.
        anchas = sorted(filas[:30], key=len, reverse=True)[:1]
        raise Aborta("[Guarda 1] No se encuentra la cabecera del informe: ninguna fila de las "
                     f"30 primeras tiene >=15 columnas Y una columna de tipo {CAB_TIPO}.\n"
                     "   O no es un Custom Transaction Report, o su columna de tipo se llama "
                     "de otra forma en ese idioma (se añade a CAB_TIPO).\n"
                     f"   La fila más ancha que se ha visto ({len(anchas[0]) if anchas else 0} "
                     f"cols): {anchas[0] if anchas else '(ninguna)'}")

    cab_norm = [_norm(c) for c in cabecera]
    alias = COLS_ALIAS[pais]

    # Resolver el nombre real de cada columna canónica para este país.
    col = {}
    for canon, al in alias.items():
        col[canon] = _resolver_columna(cabecera, cab_norm, al)
    faltan = [c for c in COLS_OBLIGATORIAS if col.get(c) is None]
    if faltan:
        # 🔑 UN PAÍS SIN MAPA NO ES UN FICHERO MALO, y el mensaje genérico mandaría a
        #    buscar el fallo donde no está (¿me equivoqué de selector?). Se dice cuál de
        #    los dos casos es, y en los dos se imprime la cabecera REAL, que es la única
        #    forma de rellenar el mapa con algo medido en vez de traducido.
        if not alias:
            raise Aborta(
                f"[Guarda 2] El mapa de columnas de {pais} está VACÍO: nadie ha medido "
                f"todavía cómo se llaman sus columnas, así que no hay con qué leer el "
                f"fichero. Esto NO es un fallo del fichero ni del selector.\n"
                f"   👉 Copia la cabecera de aquí abajo y rellena COLS_ALIAS[{pais!r}] en "
                f"procesador_transacciones.py. Con eso la siguiente carga entra.\n"
                f"   Cabecera real ({len(cabecera)} cols): {cabecera}")
        raise Aborta(
            f"[Guarda 2] En un fichero marcado {pais} NO aparecen columnas obligatorias: "
            f"{faltan}. O el fichero no es de {pais} (el selector va equivocado), o Amazon "
            f"cambió la cabecera. NO se aproxima: se ABORTA.\n"
            f"   Cabecera real ({len(cabecera)} cols): {cabecera}")

    # Índice por nombre real (para leer celdas y para el crudo).
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)

    def celda(fila, nombre_real):
        i = idx.get(nombre_real)
        if i is None or i >= len(fila):
            return ''
        return _clean(fila[i])

    filas_datos = filas[cab_idx + 1:]
    movimientos = []
    tipos = Counter()
    tipos_sin_canon = Counter()   # literal de tipo que no está en TIPO_CANON → tipo_norm NULL
    mkt_incoherente = Counter()   # marketplace no vacío que NO cuadra con PAIS

    for pos, fila in enumerate(filas_datos):
        num_fila = cab_idx + 1 + pos + 1   # numerar desde 1 en el fichero

        # Guarda 3: la fecha parsea (medido: 100% parsea; una que no, es anomalía → ABORTA,
        # no se descarta en silencio: en una película, tirar una fila falsifica el extracto).
        f_raw = celda(fila, col['fecha'])
        fecha = parse_fecha_pais(f_raw, pais)
        if fecha is None:
            raise Aborta(f"[Guarda 3] Fila {num_fila}: la fecha {f_raw!r} no parsea como "
                         f"fecha de {pais}. Abortando (no se descarta ninguna fila).")

        # Guarda 4 (país): coherencia del marketplace con el selector.
        mkt_real = celda(fila, col['marketplace']) if col.get('marketplace') else ''
        mkt_norm = _norm(mkt_real)
        if mkt_norm and MKT_A_PAIS.get(mkt_norm) not in (None, pais):
            mkt_incoherente[mkt_real] += 1

        tipo_raw = celda(fila, col['tipo'])
        tipos[tipo_raw] += 1
        tipo_norm = TIPO_CANON.get(tipo_raw)
        if tipo_raw and tipo_norm is None:
            tipos_sin_canon[tipo_raw] += 1

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        movimientos.append({
            'pais': pais,
            'fecha': fecha,
            'fecha_hora': parse_fecha_hora(f_raw, pais),
            'tipo': txt(tipo_raw),
            'tipo_norm': tipo_norm,   # canon (la vista lee de aquí); NULL si el literal no está en TIPO_CANON
            'numero_pedido': txt(celda(fila, col['numero_pedido'])) if col.get('numero_pedido') else None,
            'identificador_pago': txt(celda(fila, col['identificador_pago'])) if col.get('identificador_pago') else None,
            'sku': txt(celda(fila, col['sku'])),
            'descripcion': txt(celda(fila, col['descripcion'])) if col.get('descripcion') else None,
            'cantidad': ent_o_null(celda(fila, col['cantidad'])),
            'marketplace': txt(mkt_real),
            'ventas_producto': num_o_null(celda(fila, col['ventas_producto'])),
            'impuesto_producto': num_o_null(celda(fila, col['impuesto_producto'])),
            'tarifa_venta': num_o_null(celda(fila, col['tarifa_venta'])),
            'tarifa_fba': num_o_null(celda(fila, col['tarifa_fba'])),
            'tarifa_otras': num_o_null(celda(fila, col['tarifa_otras'])),
            # 'otro' TAL CUAL, en euros, con signo. Aquí Amazon MEZCLA en una sola
            # columna costes reales (tarifas de inventario, prestación de servicio,
            # ajustes a favor) con las TRANSFERENCIAS al banco (que NO son coste).
            # Por eso se tipa al lado de 'tipo': separarlas es cosa de la vista (PR-C),
            # el cargador solo guarda el dato sin interpretarlo.
            'otro': num_o_null(celda(fila, col['otro'])) if col.get('otro') else None,
            'total': num_o_null(celda(fila, col['total'])),
            'estado': txt(celda(fila, col['estado'])) if col.get('estado') else None,
            'fecha_liberacion': parse_fecha_pais(celda(fila, col['fecha_liberacion']), pais) if col.get('fecha_liberacion') else None,
            'crudo': crudo,
        })

    # Guarda 2b: anti-vacío (≥1 movimiento).
    if not movimientos:
        raise Aborta("[Guarda 2b] 0 movimientos de datos bajo la cabecera. Abortando.")

    # Guarda 4 (país): si alguna fila delata OTRO marketplace → ABORTA (Francia dentro de España).
    if mkt_incoherente:
        detalle = " · ".join(f"{v!r} en {n} fila(s)" for v, n in mkt_incoherente.most_common())
        raise Aborta(
            f"[Guarda 4] El fichero se marcó como {pais} pero {sum(mkt_incoherente.values())} "
            f"fila(s) traen otro marketplace: {detalle}. Esto es MEZCLA de países — el fallo "
            f"exacto que ha contaminado los datos durante meses. NO se carga: revisa el PAIS "
            f"del selector o el fichero.")

    fecha_min = min(mv['fecha'] for mv in movimientos)
    fecha_max = max(mv['fecha'] for mv in movimientos)

    return {'movimientos': movimientos, 'fichero': fichero, 'pais': pais,
            'fecha_min': fecha_min, 'fecha_max': fecha_max, 'tipos': tipos,
            'tipos_sin_canon': tipos_sin_canon}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas). PK sintética.
# 🔒 Ni comisión ni tarifas se dividen: numeric TAL CUAL, con su signo.
# ---------------------------------------------------------------------------
SQL_TABLA = """
CREATE TABLE IF NOT EXISTS transacciones_movimientos (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pais               text NOT NULL,
    fecha              date NOT NULL,
    fecha_hora         timestamptz,
    tipo               text,
    tipo_norm          text,   -- canon (pedido/reembolso/reembolso_inventario/…); tipo crudo intacto
    numero_pedido      text,
    identificador_pago text,
    sku                text,
    descripcion        text,
    cantidad           integer,
    marketplace        text,
    ventas_producto    numeric,
    impuesto_producto  numeric,
    tarifa_venta       numeric,
    tarifa_fba         numeric,
    tarifa_otras       numeric,
    otro               numeric,   -- 'otro'/'altro'/'autre': MEZCLA costes y transferencias
    total              numeric,
    estado             text,
    fecha_liberacion   date,
    fichero            text,
    crudo              jsonb,
    procesado_at       timestamptz NOT NULL DEFAULT now()
);
"""

# Los índices de transacciones_movimientos se movieron a
# migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql (son migración, no
# arranque: CREATE INDEX en cada carga pedía lock sobre la tabla).


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== PROCESADOR TRANSACCIONES (EXTRACTO de euros · carga por rango y país) ===", flush=True)
    print(f"MODO: {MODO}  ·  ENTORNO: {ENTORNO}  ·  PAIS: {PAIS or '(sin selector)'}", flush=True)
    print("=" * 60, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if PAIS not in PAISES_VALIDOS:
        sys.exit(f"PAIS desconocido: {PAIS!r}. El país lo manda el selector (ES/IT/FR) y NO "
                 f"se asume: sin país no se carga (§3.1).")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)  # reintenta cortes de red; aborta si no lo es
    csvs = [o for o in objs if (o.get('name') or '').lower().endswith('.csv')]
    if not csvs:
        sys.exit(f"No hay ningún .csv en {BUCKET}/{CARPETA}/. Sube el Custom Transaction "
                 f"Report del país {PAIS} y relanza. (Sin fichero, el ensayo aborta en el "
                 "primer paso: es el orden, no un fallo.)")
    csvs.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)

    # Con ES/IT/FR en la misma carpeta, "el más reciente" es una lotería (subes dos,
    # lanzas PAIS=ES y te coge el italiano). Por eso el catálogo v2 pasa el nombre
    # EXACTO por el input FICHERO. Igual que salud_fba/keepa: si se pide, tiene que
    # estar; NO se cae al más reciente (cargaría otro fichero sin avisar).
    if FICHERO:
        nombres = [o['name'] for o in csvs]
        if FICHERO not in nombres:
            print(f"\n❌ ABORTA (no se ha escrito nada):\n"
                  f"[Guarda fichero] Se pidió procesar {FICHERO!r} y no está en "
                  f"{BUCKET}/{CARPETA}/.\n"
                  f"   Hay {len(nombres)} .csv en el buzón: {nombres}\n"
                  f"   No se cae al más reciente: cargaría un informe distinto del que "
                  f"pediste sin avisar.", flush=True)
            sys.exit(1)
        fichero = FICHERO
        print(f"Informe elegido (pedido a dedo por FICHERO): {fichero}", flush=True)
    else:
        fichero = csvs[0]['name']
        print(f"Informe elegido (el más reciente de {len(csvs)}): {fichero}", flush=True)

    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales (antes de tocar la base) ---
    try:
        info = analizar(texto, PAIS, fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    movs = info['movimientos']
    fmin, fmax = info['fecha_min'], info['fecha_max']

    print(f"\nMovimientos leídos: {len(movs)}  ·  país {PAIS}  ·  rango {fmin} → {fmax}", flush=True)
    print("   Tipos:  " + " · ".join(f"{k or '(vacío)'} {v}" for k, v in info['tipos'].most_common()), flush=True)

    # 🔴 GRITA: literal de tipo SIN canon → tipo_norm queda NULL y la vista NO lo cuenta.
    # Es el seguro contra el techo de la v1: el día que entre un país nuevo (DE, PL…) o Amazon
    # renombre un tipo, salta aquí y se añade a TIPO_CANON — nunca se cae en silencio.
    if info['tipos_sin_canon']:
        print("\n⚠️  [tipo sin canon] Estos literales NO están en TIPO_CANON → tipo_norm=NULL "
              "(añádelos al mapa; la vista de rentabilidad no los cuenta hasta entonces):",
              flush=True)
        for val, n in info['tipos_sin_canon'].most_common():
            print(f"        · {val!r} en {n} fila(s)", flush=True)

    # --- Conectar al ENTORNO (con reintento ante transitorios de red; ver conectar_bd) ---
    con = conectar_bd(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    cur.execute(SQL_TABLA)
    # 🔒 El ENABLE RLS pedía AccessExclusiveLock sobre transacciones_movimientos EN
    # CADA carga (el lock que dejaba fuera al sondeo de la cola). RLS e índices viven
    # en migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql. Solo se comprueba
    # que la tabla está CERRADA (RLS activa); si no, ABORTA pidiéndola.
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.transacciones_movimientos'::regclass;")
    if not cur.fetchone()[0]:
        raise Aborta(
            "RLS no está activa en transacciones_movimientos. Ya NO la activa el procesador (era un "
            "lock exclusivo en cada carga). Aplica migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql y relanza.")

    # --- Guarda 5: anti-encogimiento POR RANGO Y PAÍS ---
    cur.execute("SELECT count(*) FROM transacciones_movimientos "
                "WHERE fecha BETWEEN %s AND %s AND pais = %s;", (fmin, fmax, PAIS))
    previas_rango = cur.fetchone()[0]
    if len(movs) < previas_rango * 0.5:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 5] El fichero trae {len(movs)} movimientos en {PAIS} [{fmin}→{fmax}] "
              f"y ya había {previas_rango}: menos del 50%. Un extracto a medias no da "
              f"información incompleta, da información FALSA. No se borra ni se escribe nada.",
              flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Guarda 6: PAÍS NUEVO (radar fiscal; NO aborta) ---
    cur.execute("SELECT DISTINCT pais FROM transacciones_movimientos;")
    paises_bd = {r[0] for r in cur.fetchall()}
    if not paises_bd:
        print(f"\n1ª carga (tabla vacía): país inicial → {PAIS}", flush=True)
    elif PAIS not in paises_bd:
        print(f"\n🆕 PAÍS NUEVO en transacciones: {PAIS}. Amazon factura ventas en un "
              f"marketplace nuevo; posible NUEVA OBLIGACIÓN DE IVA — revisar. (Entra igual.)",
              flush=True)

    # --- Guarda 8 (1ª parte): foto de los DÍAS que había de ESTE país, ANTES de borrar ---
    # Se lee aquí y no después porque después del DELETE ya no hay con qué comparar.
    # 🔒 Con el filtro de PAIS: los días de los otros países no son asunto de esta carga.
    # 🔒 BD contra FICHERO, nunca contra el calendario: un día sin transacciones es
    # legítimo (IT tiene movimiento en 64 de 201 días) y no se inventa un hueco.
    cur.execute("SELECT fecha, count(*) FROM transacciones_movimientos "
                "WHERE fecha BETWEEN %s AND %s AND pais = %s GROUP BY fecha;", (fmin, fmax, PAIS))
    filas_bd_dia = {f: n for f, n in cur.fetchall()}
    filas_fich_dia = Counter(mv['fecha'] for mv in movs)

    dias_perdidos = sorted(d for d in filas_bd_dia if d not in filas_fich_dia)
    dias_adelgazan = sorted((d, filas_bd_dia[d], filas_fich_dia[d]) for d in filas_bd_dia
                            if d in filas_fich_dia and filas_fich_dia[d] < filas_bd_dia[d])

    def _pinta(perdidos, adelgazan, sangria="        "):
        """El detalle del hueco. Se usa en el aviso, en el aborto, en el resumen y en el
        sello: el mismo texto en todos para que no haya dos versiones de la verdad."""
        lineas = []
        if perdidos:
            lineas.append(f"{sangria}· DESAPARECEN {len(perdidos)} día(s) enteros: "
                          f"{texto_dias(perdidos)}")
        if adelgazan:
            peor = sorted(adelgazan, key=lambda t: t[1] - t[2], reverse=True)[:5]
            lineas.append(f"{sangria}· ADELGAZAN {len(adelgazan)} día(s) (vienen, pero "
                          f"con menos movimientos de los que ya había):")
            for d, antes, ahora in peor:
                lineas.append(f"{sangria}    {d}: {antes} → {ahora}  ({antes - ahora} de menos)")
            if len(adelgazan) > len(peor):
                lineas.append(f"{sangria}    … y {len(adelgazan) - len(peor)} día(s) más")
        if lineas:
            n = (sum(filas_bd_dia[d] for d in perdidos)
                 + sum(antes - ahora for _, antes, ahora in adelgazan))
            lineas.append(f"{sangria}En total {n} movimiento(s) del rango se quedan sin "
                          f"contrapartida en el fichero.")
        return "\n".join(lineas)

    # 🔴 EL BORDE ES DISTINTO DEL MEDIO (idéntico al ledger, misma razón)
    #   fmin/fmax salen del fichero, así que el borde solo puede ADELGAZAR, no faltar. Y
    #   puede venir cortado de forma legítima cuando el rango acaba en el día en curso.
    #   Un día de EN MEDIO no se corta solo → si encoge o desaparece, ABORTA.
    #   🔒 ASUNCIÓN EXPLÍCITA del recorte: al estrechar el borde nos quedamos con lo de la
    #   BD (que tiene más) y descartamos lo del fichero. En el ledger eso es un subconjunto
    #   limpio (es acumulativo); AQUÍ es menos limpio por las diferidas (una del último día
    #   podría haberse cancelado, no solo "aún no exportada"). Da igual para el lado que se
    #   elige: quedarse con la versión de la BD conserva DE MÁS, nunca de menos — el lado
    #   seguro, coherente con la tolerancia cero. Si el experimento de las diferidas (abajo)
    #   demostrara que hay que soltar por el borde, se decide entonces y con el número.
    #   ⚠️ EXPOSICIÓN CONOCIDA, tolerancia CERO por ahora (decisión de Fernando, 31-jul):
    #   este informe trae transacciones DIFERIDAS que cambian entre dos descargas; una
    #   que se cancele en un día INTERMEDIO haría abortar la 8a. Medido hoy: IT 43,6% de
    #   sus filas diferidas, FR 34,6%, ES 4,2% — pero es artefacto de que IT/FR son series
    #   cortas y recientes, no una propiedad del país (ES tiene 13.658 filas de historia).
    #   Antes de aflojar NADA hay que MEDIR (bajar IT dos veces el mismo rango y ver si una
    #   diferida cancelada BORRA la fila o si Amazon añade una línea de reembolso). Ese
    #   experimento es de Elena (el Seller es suyo). Si algún día se afloja, será SOLO aquí
    #   y con el número delante — el ledger es de movimientos físicos y no se toca.
    BORDE = {fmin, fmax}
    adelgazan_medio = [t for t in dias_adelgazan if t[0] not in BORDE]
    adelgazan_borde = [t for t in dias_adelgazan if t[0] in BORDE]

    # --- Guarda 8a: UN DÍA DE EN MEDIO NO SE CORTA SOLO → ABORTA (antes del DELETE) ---
    if dias_perdidos or adelgazan_medio:
        print(f"\n❌ ABORTA (no se ha escrito nada; no se ha llegado ni a borrar):\n"
              f"[Guarda 8a] EL EXTRACTO ENCOGE POR DENTRO. En {PAIS} [{fmin}→{fmax}] hay días "
              f"INTERMEDIOS que la BD tiene y este fichero no cubre:\n"
              + _pinta(dias_perdidos, adelgazan_medio, "      ") + "\n"
              f"   El día de corte de una exportación es el PRIMERO o el ÚLTIMO, nunca uno de "
              f"en medio: un hueco aquí significa que el fichero está INCOMPLETO.\n"
              f"   Vuelve a exportarlo del Seller comprobando el rango y que sea el de {PAIS}.\n"
              f"   (El extracto es PELÍCULA: lo que se borra no se recupera.)", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Regla del BORDE: no se aborta, se ESTRECHA el rango (DELETE e INSERT) ---
    # 🔴 Estrechar el DELETE no basta: hay que sacar ese día TAMBIÉN del INSERT, o queda
    # duplicado. Sacarlo por los dos lados = "ese día se queda como está en la BD".
    fmin_ef, fmax_ef = fmin, fmax
    if any(d == fmin for d, _, _ in adelgazan_borde):
        fmin_ef = fmin + timedelta(days=1)
    if any(d == fmax for d, _, _ in adelgazan_borde):
        fmax_ef = fmax - timedelta(days=1)

    if adelgazan_borde:
        print(f"\n✂️  [Guarda 8 · regla del borde] el borde del fichero de {PAIS} viene "
              f"cortado (el rango acaba en el día en curso), así que NO se aborta: se "
              f"ESTRECHA el rango y esos días se dejan tal como están en la BD.")
        for d, antes, ahora in adelgazan_borde:
            cual = 'PRIMER' if d == fmin else 'ÚLTIMO'
            print(f"        · {d} ({cual} día): trae {ahora} y la BD ya tiene {antes} → "
                  f"se respeta el de la BD")
        print(f"        Rango efectivo: {fmin_ef} → {fmax_ef}", flush=True)

    if fmin_ef > fmax_ef:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 8] Tras la regla del borde no queda NADA que cargar en {PAIS}: el "
              f"fichero cubre {fmin}→{fmax} y sus extremos vienen más flacos que la BD. "
              f"Vuelve a exportarlo con un rango más ancho.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    movs_ef = [mv for mv in movs if fmin_ef <= mv['fecha'] <= fmax_ef]
    descartados_borde = len(movs) - len(movs_ef)

    # --- Carga por rango EFECTIVO y país: DELETE + INSERT (misma transacción) ---
    cur.execute("DELETE FROM transacciones_movimientos "
                "WHERE fecha BETWEEN %s AND %s AND pais = %s;", (fmin_ef, fmax_ef, PAIS))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [
        [mv['pais'], mv['fecha'], mv['fecha_hora'], mv['tipo'], mv['tipo_norm'], mv['numero_pedido'],
         mv['identificador_pago'], mv['sku'], mv['descripcion'], mv['cantidad'],
         mv['marketplace'], mv['ventas_producto'], mv['impuesto_producto'],
         mv['tarifa_venta'], mv['tarifa_fba'], mv['tarifa_otras'], mv['otro'], mv['total'],
         mv['estado'], mv['fecha_liberacion'], fichero, Json(mv['crudo'])]
        for mv in movs_ef
    ]
    execute_values(
        cur,
        f"INSERT INTO transacciones_movimientos ({', '.join(COLS_DB)}) VALUES %s",
        valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- Guarda 8b: RED DE ÚLTIMA HORA (el total del rango efectivo) ---
    # 🔒 Con la 8a activa es matemáticamente inalcanzable: todo día intermedio cumple
    # fichero ≥ BD y el borde ha quedado fuera del rango efectivo. Existe SOLO por si la
    # 8a tiene un fallo o alguien escribe en la tabla entre el recuento y el DELETE. NO es
    # ella quien caza el fichero incompleto — ésa es la 8a. Va antes del sello: un
    # extracto que no se carga no se sella.
    if insertadas < borradas:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 8b] EL EXTRACTO ENCOGE EN TOTAL y la comprobación por día no lo vio: "
              f"en {PAIS} [{fmin_ef}→{fmax_ef}] se iban a BORRAR {borradas} y entran "
              f"{insertadas} ({borradas - insertadas} de menos).\n"
              f"   Esto NO debería poder pasar: o hay un fallo en la Guarda 8a, o alguien ha "
              f"escrito en transacciones_movimientos mientras corría esta carga. No se "
              f"escribe nada; avisa antes de volver a lanzarlo.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- SELLO DE FRESCURA: una fila en informes_subidos (lo que lee frescura_informes) ---
    resumen = {
        'pais': PAIS, 'tipo': 'transacciones', 'archivo': fichero,
        'fecha_desde': fmin.isoformat(), 'fecha_hasta': fmax.isoformat(),
        'rango_efectivo_desde': fmin_ef.isoformat(), 'rango_efectivo_hasta': fmax_ef.isoformat(),
        'filas': len(movs), 'tipos': dict(info['tipos']),
        'fuente': 'procesador_transacciones (Fase 0)',
        # 🔒 El borde recortado va EN EL DATO, no solo en el log. Sin esto, dentro de tres
        # meses nadie sabría que este rango se cargó con el borde estrechado: una cifra sin
        # la fecha del dato que la sostiene es una cifra que miente.
        'dias_recortados_borde': [{'dia': d.isoformat(), 'bd': antes, 'fichero': ahora}
                                  for d, antes, ahora in adelgazan_borde],
        'movimientos_descartados_borde': descartados_borde,
    }
    cur.execute(
        "INSERT INTO informes_subidos "
        "(tipo, archivo_nombre, filas_procesadas, filas_validas, filas_descartadas, "
        " fecha_dato_desde, fecha_dato_hasta, resumen_json, procesado_at, notas) "
        "VALUES ('transacciones', %s, %s, %s, %s, %s, %s, %s, now(), %s);",
        (fichero, len(movs), insertadas, descartados_borde, fmin, fmax, Json(resumen),
         f'procesador_transacciones Fase 0 · {PAIS}'))

    # --- Resumen ---
    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- TRANSACCIONES (carga por rango {PAIS} [{fmin} → {fmax}]) ---")
    print(f"   · movimientos del fichero:        {len(movs)}")
    print(f"   · ya había en ese rango/país:     {previas_rango}")
    print(f"   · BORRADOS del rango ({verbo}):    {borradas}")
    print(f"   · INSERTADOS ({verbo}):            {insertadas}")
    print(f"   · otros países y lo anterior a {fmin}: intactos")
    if adelgazan_borde:
        print(f"   · ✂️  BORDE recortado: rango efectivo {fmin_ef} → {fmax_ef}")
        for d, antes, ahora in adelgazan_borde:
            print(f"        {d}: se respeta la BD ({antes}) y se descarta lo del fichero ({ahora})")
        print(f"        movimientos del fichero descartados por el borde: {descartados_borde}")
    else:
        print(f"   · borde recortado: no (los dos extremos vienen completos)")
    print(f"   · huecos en días INTERMEDIOS:     0 (si hubiera, habría abortado)")
    print(f"   · sello en informes_subidos ({verbo}): 1 fila (tipo='transacciones')")

    if MODO == 'aplicar':
        con.commit()
        # 🔒 Mismo sitio y mismo porque que en el ledger: despues del commit, fuera de la
        #    transaccion, y solo en `aplicar`. Ver refrescar_vistas() en foto_comun.py.
        refrescar_vistas(con, 'transacciones')
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} movimientos de {PAIS} en "
              f"transacciones_movimientos (rango efectivo {fmin_ef}→{fmax_ef} recerrado; "
              f"RLS activo sin políticas; sello escrito en informes_subidos).")
        # amazon_es (canales_producto) se calcula DESDE esta tabla y NO se refresca
        # solo: tras esta carga puede haber quedado desfasado. Aviso, no acción.
        # (Encadenarlo con workflow_run para que salga solo: otro encargo.)
        if PAIS == 'ES':
            print(f"\n⚠️  amazon_es en canales_producto se calcula desde estos datos y NO se "
                  f"actualiza solo: acaba de quedar DESFASADO. Lanza 'procesar-canal-amazon-es' "
                  f"({ENTORNO}) para refrescarlo.", flush=True)
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(El borrado por rango, el volcado y el sello se han probado dentro de una "
              f"transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · pais={PAIS} · "
          f"movimientos={len(movs)} · rango={fmin}→{fmax} · rango_efectivo={fmin_ef}→{fmax_ef} · "
          f"borrados={borradas} · insertados={insertadas} · "
          f"borde_recortado={len(adelgazan_borde)} · descartados_borde={descartados_borde} "
          f"===", flush=True)


if __name__ == '__main__':
    main()
