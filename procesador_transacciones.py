# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR TRANSACCIONES — el EXTRACTO de euros de Amazon (Fase 0, MULTIPAÍS)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el "Custom Transaction Report" del Seller (Pagos → Todas las transacciones,
#   .csv, uno por marketplace ES/IT/FR) del buzón informes/transacciones/ y carga
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
#   🔴 LO QUE LA GUARDA 8 NO PUEDE VER, Y POR QUÉ EL DETECTOR VA POR RECUENTO
#   La Guarda 8 compara TOTALES del rango, así que una merma en un día queda
#   COMPENSADA por crecimiento en otro tramo del mismo rango. Medido el 30-jul en el
#   ledger contra dos exportaciones reales del mismo informe: de 89 días solapados, 88
#   traían las mismas filas y el 2026-07-20 traía 281 en una y 176 en otra — el día de
#   CORTE de una exportación viene siempre a medias. Aquí pasa lo mismo.
#   Por eso el DETECTOR DE HUECOS no mira solo qué días FALTAN: compara el RECUENTO
#   POR DÍA y avisa también de los días que ADELGAZAN. Al mismo coste: el SELECT ya
#   recorría esas filas, solo cambia DISTINCT por GROUP BY.
#   ⚠️ El detector AVISA, no aborta (así se pidió). Un día que adelgaza o desaparece
#   mientras el total sube se borra igualmente y el proceso termina en verde: lee el
#   aviso ANTES de aplicar. Queda además escrito en el resumen_json del sello, para
#   que no viva solo en el log de Actions.
#   🔒 Aquí TODO va por rango Y PAÍS, también la Guarda 8: se compara contra lo que
#   había de ESE país. Mezclar países haría que cargar FR (243 filas) pareciera un
#   derrumbe frente a ES (13.658) y abortaría siempre.
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
from foto_comun import Aborta, listar_buzon, descargar_buzon

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
PAISES_VALIDOS = ('ES', 'IT', 'FR')

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
MKT_A_PAIS = {'amazon.es': 'ES', 'amazon.fr': 'FR', 'amazon.it': 'IT'}

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
        raise Aborta(f"[PAIS] {pais!r} no es ES/IT/FR. El país lo manda el selector del "
                     f"workflow y no se asume: sin país determinado, se ABORTA (§3.1).")

    lector = csv.reader(io.StringIO(texto))
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 1: encontrar la cabecera (tras ~9 filas de metadatos). Primera fila con
    # ≥15 columnas que contenga una columna de tipo/type.
    cab_idx, cabecera = None, None
    for i, f in enumerate(filas[:30]):
        norm = [_norm(c) for c in f]
        if len(f) >= 15 and any(n in ('tipo', 'type') for n in norm):
            cab_idx, cabecera = i, f
            break
    if cab_idx is None:
        raise Aborta("[Guarda 1] No se encuentra la cabecera del informe (ninguna fila con "
                     "≥15 columnas y una columna 'tipo'/'type' en las primeras 30). "
                     "¿Es un Custom Transaction Report? Abortando.")

    cab_norm = [_norm(c) for c in cabecera]
    alias = COLS_ALIAS[pais]

    # Resolver el nombre real de cada columna canónica para este país.
    col = {}
    for canon, al in alias.items():
        col[canon] = _resolver_columna(cabecera, cab_norm, al)
    faltan = [c for c in COLS_OBLIGATORIAS if col.get(c) is None]
    if faltan:
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

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
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
    movs_sin_contrapartida = (sum(filas_bd_dia[d] for d in dias_perdidos)
                              + sum(antes - ahora for _, antes, ahora in dias_adelgazan))

    def _pinta_huecos(sangria="        "):
        """El detalle del hueco. Se usa en el aviso, en el aborto, en el resumen y en el
        sello: el mismo texto en todos para que no haya dos versiones de la verdad."""
        lineas = []
        if dias_perdidos:
            lineas.append(f"{sangria}· DESAPARECEN {len(dias_perdidos)} día(s) enteros: "
                          f"{texto_dias(dias_perdidos)}")
        if dias_adelgazan:
            peor = sorted(dias_adelgazan, key=lambda t: t[1] - t[2], reverse=True)[:5]
            lineas.append(f"{sangria}· ADELGAZAN {len(dias_adelgazan)} día(s) (vienen, pero "
                          f"con menos movimientos de los que ya había):")
            for d, antes, ahora in peor:
                lineas.append(f"{sangria}    {d}: {antes} → {ahora}  ({antes - ahora} de menos)")
            if len(dias_adelgazan) > len(peor):
                lineas.append(f"{sangria}    … y {len(dias_adelgazan) - len(peor)} día(s) más")
        if lineas:
            lineas.append(f"{sangria}En total {movs_sin_contrapartida} movimiento(s) del rango "
                          f"se quedan sin contrapartida en el fichero.")
        return "\n".join(lineas)

    if dias_perdidos or dias_adelgazan:
        print(f"\n⚠️  [Guarda 8 · huecos por día] el fichero de {PAIS} NO cubre todo lo que la "
              f"BD ya tenía en {fmin}→{fmax}:\n" + _pinta_huecos(), flush=True)

    # --- Carga por rango y país: DELETE + INSERT (misma transacción) ---
    cur.execute("DELETE FROM transacciones_movimientos "
                "WHERE fecha BETWEEN %s AND %s AND pais = %s;", (fmin, fmax, PAIS))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [
        [mv['pais'], mv['fecha'], mv['fecha_hora'], mv['tipo'], mv['tipo_norm'], mv['numero_pedido'],
         mv['identificador_pago'], mv['sku'], mv['descripcion'], mv['cantidad'],
         mv['marketplace'], mv['ventas_producto'], mv['impuesto_producto'],
         mv['tarifa_venta'], mv['tarifa_fba'], mv['tarifa_otras'], mv['otro'], mv['total'],
         mv['estado'], mv['fecha_liberacion'], fichero, Json(mv['crudo'])]
        for mv in movs
    ]
    execute_values(
        cur,
        f"INSERT INTO transacciones_movimientos ({', '.join(COLS_DB)}) VALUES %s",
        valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- Guarda 8: EL EXTRACTO NO ENCOGE ---
    # La 5 mira el total ANTES de borrar y tolera hasta un 50% de merma; ésta compara
    # lo que de verdad se DESTRUYE con lo que de verdad ENTRA. Si el rango de ESTE país
    # encoge aunque sea en un movimiento, el fichero está incompleto y NO se escribe nada.
    # Va ANTES del sello de frescura a propósito: un extracto que no se carga no se sella.
    if insertadas < borradas:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 8] EL EXTRACTO ENCOGE. En {PAIS} [{fmin}→{fmax}] se iban a BORRAR "
              f"{borradas} movimientos y el fichero solo trae {insertadas}: se habrían "
              f"PERDIDO {borradas - insertadas}.\n"
              f"   Un extracto de euros no encoge solo. Causa probable: el fichero exportado "
              f"está INCOMPLETO — vuelve a exportarlo del Seller comprobando el rango de "
              f"fechas (y que sea el del país {PAIS}).\n"
              f"   Dónde está el hueco:\n"
              + (_pinta_huecos("      ") or
                 "      en ningún día concreto: el fichero trae menos filas repartidas."),
              flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- SELLO DE FRESCURA: una fila en informes_subidos (lo que lee frescura_informes) ---
    resumen = {
        'pais': PAIS, 'tipo': 'transacciones', 'archivo': fichero,
        'fecha_desde': fmin.isoformat(), 'fecha_hasta': fmax.isoformat(),
        'filas': len(movs), 'tipos': dict(info['tipos']),
        'fuente': 'procesador_transacciones (Fase 0)',
        # 🔒 Los huecos van EN EL DATO, no solo en el log. Sin esto, dentro de tres meses
        # nadie podría saber que este rango se cargó con días adelgazados: la tarjeta de
        # frescura saldría verde sobre un extracto agujereado, y una cifra sin la fecha
        # del dato que la sostiene es una cifra que miente.
        'dias_perdidos': [d.isoformat() for d in dias_perdidos],
        'dias_adelgazan': [{'dia': d.isoformat(), 'antes': antes, 'ahora': ahora}
                           for d, antes, ahora in dias_adelgazan],
        'movs_sin_contrapartida': movs_sin_contrapartida,
    }
    cur.execute(
        "INSERT INTO informes_subidos "
        "(tipo, archivo_nombre, filas_procesadas, filas_validas, filas_descartadas, "
        " fecha_dato_desde, fecha_dato_hasta, resumen_json, procesado_at, notas) "
        "VALUES ('transacciones', %s, %s, %s, 0, %s, %s, %s, now(), %s);",
        (fichero, len(movs), len(movs), fmin, fmax, Json(resumen),
         f'procesador_transacciones Fase 0 · {PAIS}'))

    # --- Resumen ---
    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- TRANSACCIONES (carga por rango {PAIS} [{fmin} → {fmax}]) ---")
    print(f"   · movimientos del fichero:        {len(movs)}")
    print(f"   · ya había en ese rango/país:     {previas_rango}")
    print(f"   · BORRADOS del rango ({verbo}):    {borradas}")
    print(f"   · INSERTADOS ({verbo}):            {insertadas}")
    print(f"   · otros países y lo anterior a {fmin}: intactos")
    if dias_perdidos or dias_adelgazan:
        print(f"   · ⚠️  HUECOS POR DÍA en {PAIS} — {movs_sin_contrapartida} movimiento(s) del "
              f"rango se quedan sin contrapartida:")
        print(_pinta_huecos("        "))
        print(f"        El TOTAL del rango no encoge (por eso no aborta), pero esos "
              f"movimientos se borran igual.")
        print(f"        MÍRALO antes de aplicar: el extracto es PELÍCULA y no se recupera.")
        print(f"        (Queda anotado en resumen_json de informes_subidos.)")
    else:
        print(f"   · huecos por día (desaparecidos o adelgazados): 0")

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} movimientos de {PAIS} en "
              f"transacciones_movimientos (rango recerrado; RLS activo sin políticas; "
              f"sello escrito en informes_subidos).")
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
          f"movimientos={len(movs)} · rango={fmin}→{fmax} · borrados={borradas} · "
          f"insertados={insertadas} · dias_perdidos={len(dias_perdidos)} · "
          f"dias_adelgazan={len(dias_adelgazan)} · "
          f"movs_sin_contrapartida={movs_sin_contrapartida} ===", flush=True)


if __name__ == '__main__':
    main()
