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
# 🔒 El SELLO DE FRESCURA: al aplicar, escribe una fila en `informes_subidos`
#   (tipo='transacciones', fecha_dato_hasta, procesado_at). Es lo que lee la RPC
#   frescura_informes() para esta tarjeta. Con el fichero en informes/transacciones/
#   (subido_buzon) la tarjeta deja de salir gris.
#
# Encoding utf-8-sig (BOM MEDIDO en los 3 ficheros el 28-jul), fallback cp1252.
#   Separador coma. Cabecera tras ~9 filas de metadatos.
# ============================================================================

import os, sys, io, csv, re, unicodedata
from datetime import date, datetime
from collections import Counter

import psycopg2
from psycopg2.extras import Json, execute_values

# Del patrón común solo se reutiliza Aborta: la carga por rango es lógica propia
# (barrer_sobrantes es para FOTOS y aquí borraría el histórico) — igual que el ledger.
from foto_comun import Aborta

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

# Columnas tipadas de la tabla, en el orden del INSERT (id IDENTITY y procesado_at aparte).
COLS_DB = ['pais', 'fecha', 'fecha_hora', 'tipo', 'numero_pedido', 'identificador_pago',
           'sku', 'descripcion', 'cantidad', 'marketplace',
           'ventas_producto', 'impuesto_producto', 'tarifa_venta', 'tarifa_fba',
           'tarifa_otras', 'total', 'estado', 'fecha_liberacion', 'fichero', 'crudo']

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


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales. Sin tocar la base todavía.
# ---------------------------------------------------------------------------
def _resolver_columna(cabecera, cab_norm, alias_list):
    for alias in alias_list:
        for real, norm in zip(cabecera, cab_norm):
            if norm == alias or norm.startswith(alias):
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

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        movimientos.append({
            'pais': pais,
            'fecha': fecha,
            'fecha_hora': parse_fecha_hora(f_raw, pais),
            'tipo': txt(tipo_raw),
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
            'fecha_min': fecha_min, 'fecha_max': fecha_max, 'tipos': tipos}


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
    total              numeric,
    estado             text,
    fecha_liberacion   date,
    fichero            text,
    crudo              jsonb,
    procesado_at       timestamptz NOT NULL DEFAULT now()
);
"""

SQL_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_trans_pais_fecha ON transacciones_movimientos(pais, fecha);",
    "CREATE INDEX IF NOT EXISTS idx_trans_fecha ON transacciones_movimientos(fecha);",
    "CREATE INDEX IF NOT EXISTS idx_trans_tipo ON transacciones_movimientos(tipo);",
    "CREATE INDEX IF NOT EXISTS idx_trans_sku ON transacciones_movimientos(sku);",
    "CREATE INDEX IF NOT EXISTS idx_trans_pedido ON transacciones_movimientos(numero_pedido);",
]


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
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA) or []
    except Exception as e:
        sys.exit(f"No se pudo listar {BUCKET}/{CARPETA}/ ({e}). ¿Existe la carpeta? "
                 "Créala y sube el Custom Transaction Report (.csv) del país que vas a procesar.")
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

    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")
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

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    cur.execute(SQL_TABLA)
    for ddl in SQL_INDICES:
        cur.execute(ddl)
    cur.execute("ALTER TABLE transacciones_movimientos ENABLE ROW LEVEL SECURITY;")

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

    # --- Carga por rango y país: DELETE + INSERT (misma transacción) ---
    cur.execute("DELETE FROM transacciones_movimientos "
                "WHERE fecha BETWEEN %s AND %s AND pais = %s;", (fmin, fmax, PAIS))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [
        [mv['pais'], mv['fecha'], mv['fecha_hora'], mv['tipo'], mv['numero_pedido'],
         mv['identificador_pago'], mv['sku'], mv['descripcion'], mv['cantidad'],
         mv['marketplace'], mv['ventas_producto'], mv['impuesto_producto'],
         mv['tarifa_venta'], mv['tarifa_fba'], mv['tarifa_otras'], mv['total'],
         mv['estado'], mv['fecha_liberacion'], fichero, Json(mv['crudo'])]
        for mv in movs
    ]
    execute_values(
        cur,
        f"INSERT INTO transacciones_movimientos ({', '.join(COLS_DB)}) VALUES %s",
        valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- SELLO DE FRESCURA: una fila en informes_subidos (lo que lee frescura_informes) ---
    resumen = {
        'pais': PAIS, 'tipo': 'transacciones', 'archivo': fichero,
        'fecha_desde': fmin.isoformat(), 'fecha_hasta': fmax.isoformat(),
        'filas': len(movs), 'tipos': dict(info['tipos']),
        'fuente': 'procesador_transacciones (Fase 0)',
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

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} movimientos de {PAIS} en "
              f"transacciones_movimientos (rango recerrado; RLS activo sin políticas; "
              f"sello escrito en informes_subidos).")
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(El borrado por rango, el volcado y el sello se han probado dentro de una "
              f"transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · pais={PAIS} · "
          f"movimientos={len(movs)} · rango={fmin}→{fmax} · borrados={borradas} · "
          f"insertados={insertadas} ===", flush=True)


if __name__ == '__main__':
    main()
