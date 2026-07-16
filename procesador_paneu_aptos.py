# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR PANEU_APTOS — 5ª pieza de la Fase 0 de la v2 (EJE PAÍS, PR #1)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el informe "Inventario Paneuropeo de Logística de Amazon" (.tsv) del
#   buzón informes/paneu_aptos/ (Supabase Storage de PRODUCCIÓN, aunque el
#   ENTORNO sea staging: solo cambia DB_URL) y lo vuelca a DOS tablas nuevas:
#     · paneu_aptos        — lo que es del SKU.        PK (seller_sku)
#     · paneu_oferta_pais  — lo que es del par SKU×país. PK (seller_sku, pais)
#
#   🔒 El PAÍS es una FILA, no un sufijo de columna. El pecado de la v1
#      (columnas _es/_it/_fr) se corta aquí: 328 SKU × 10 países = 3.280 filas.
#   🔒 NO escribe en `productos`, ni en `index.html`, ni en ninguna tabla de la
#      v1. Cero cruce contra `productos`.
#   🔒 NINGUNA VISTA en este PR: la del eje país está bloqueada por una decisión
#      de diseño abierta (el ranking de reconsideración). No se adelanta.
#
# TRAMPA 1 — el fichero LLEVA BOM: se lee con utf-8-sig. (El del INTERNACIONAL
#   del PR #2 NO lleva BOM: no copiar el encoding de uno al otro.)
# TRAMPA 2 — los nombres de las 20 columnas de país NO son interpolables
#   (f'Estado de la oferta {pais}' falla en FR, BE e IE). Van HARDCODEADOS y
#   verificados 20/20 en MAPA_PAIS. Esa es la clase de bug que mató al PR #26.
#
# 🔴 EL PUNTO FINO (§5.1): 'Estado de la oferta XX' significa TRES cosas en la
#   misma celda (un precio, una ausencia, o un motivo de bloqueo). Se parte en
#   campos AL ENTRAR, nunca al leer. Una columna que significa tres cosas es un
#   cabo suelto de nacimiento. La Guarda 5 lo protege.
#
# Precedente a imitar: procesador_keepa_escaparate.py (4ª pieza, en producción).
# Misma escalera (ENTORNO staging|produccion, MODO ensayo|aplicar), misma
# disciplina de guardas y de "lo nuevo nace cerrado" (RLS on, 0 políticas).
# ============================================================================

import os, sys, io, csv, re
from datetime import date, datetime, timezone

import psycopg2
from psycopg2.extras import Json
from supabase import create_client

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

BUCKET, CARPETA = 'informes', 'paneu_aptos'

# ---------------------------------------------------------------------------
# Las 10 columnas del SKU (encabezados LITERALES del fichero real, 30/30).
# ---------------------------------------------------------------------------
COLS_SKU = [
    'ASIN', 'MerchantSKU', 'Registrarse', 'FnSKU', 'Estado de PanEU',
    'Enrollment Date', 'Title', 'Última actividad el',
    'Fecha en que caduca PanEU', 'Comentarios del producto',
]

# ---------------------------------------------------------------------------
# 🔒 MAPA HARDCODEADO Y VERIFICADO 20/20 CONTRA EL FICHERO.
# NO construir estos nombres por interpolación: fallaría en FR ("de FR"), BE e
# IE (nombres en inglés/castellano irregulares). Cada país → (columna de estado
# de la oferta, columna de beneficios PanEU).
# ---------------------------------------------------------------------------
MAPA_PAIS = {
    'UK': ('Estado de la oferta UK', 'Beneficios de PanEU UK'),
    'DE': ('Estado de la oferta DE', 'Beneficios de PanEU DE'),
    'FR': ('Estado de la oferta FR', 'Beneficios de PanEU de FR'),   # ← el único con "de" en medio
    'IT': ('Estado de la oferta IT', 'Beneficios de PanEU IT'),
    'ES': ('Estado de la oferta ES', 'Beneficios de PanEU ES'),
    'NL': ('Estado de la oferta NL', 'Beneficios de PanEU NL'),
    'SE': ('Estado de la oferta SE', 'Beneficios de PanEU SE'),
    'PL': ('Estado de la oferta PL', 'Beneficios de PanEU PL'),
    'BE': ('BE Offer Status (Estado de la oferta en Bélgica)',
           'BE PanEU Benefits (Ventajas del Programa paneuropeo en Bélgica)'),
    'IE': ('Estado de la oferta en Irlanda',
           'Ventajas del Programa paneuropeo en Irlanda'),
}

# 10 propias + 20 del mapa = 30 (las que tiene el fichero).
COLS_PAIS = [c for par in MAPA_PAIS.values() for c in par]
CABECERA_ESPERADA = set(COLS_SKU) | set(COLS_PAIS)
assert len(COLS_SKU) == 10 and len(COLS_PAIS) == 20 and len(CABECERA_ESPERADA) == 30, \
    "El recuento de columnas esperadas no da 30."

# Estados de PanEU conocidos (Guarda 6: un valor fuera → GRITA, no aborta).
ESTADOS_PANEU_CONOCIDOS = {'Inscrito', 'Válido', 'No válido', 'Inscripción finalizada'}

# Patrón de "columna de país" para detectar un país NUEVO (Guarda 7).
RE_PAIS_NUEVO = re.compile(r'^Estado de la oferta ([A-Z]{2})$')

# Meses en inglés para parsear 'Fri May 29 09:49:18 UTC 2026' sin depender del locale.
_MESES = {m: i for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], start=1)}
RE_FECHA = re.compile(
    r'^[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+UTC\s+(\d{4})$')


class Aborta(Exception):
    """Cualquier guarda que aborta lanza esto: se imprime, NO se escribe nada y
    el workflow sale en rojo."""
    pass


# ---------------------------------------------------------------------------
# Helpers de limpieza y parseo
# ---------------------------------------------------------------------------
def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()

def txt(v):
    """'' → NULL. (El paneu no usa '-' como marcador; se guarda lo que venga.)"""
    s = _clean(v)
    return s or None

def bool_yn(v):
    """'Y' → true, 'N' → false, resto → NULL (el crudo conserva el original)."""
    s = _clean(v).upper()
    if s == 'Y':
        return True
    if s == 'N':
        return False
    return None

def fecha_utc(v):
    """'Fri May 29 09:49:18 UTC 2026' → timestamptz. NULL si no casa el formato
    (el crudo conserva el original). Parseo sin locale para ser reproducible."""
    s = _clean(v)
    if not s:
        return None
    m = RE_FECHA.match(s)
    if not m:
        return None
    mes = _MESES.get(m.group(1))
    if not mes:
        return None
    return datetime(int(m.group(6)), mes, int(m.group(2)),
                    int(m.group(3)), int(m.group(4)), int(m.group(5)), tzinfo=timezone.utc)

def precio_eur(cell):
    """El número tras '€ '. Tolerante a coma decimal. NULL si no parsea."""
    s = _clean(cell).replace('€', '').replace('€', '').strip()
    if not s:
        return None
    if ',' in s and '.' not in s:      # coma decimal europea
        s = s.replace(',', '.')
    s = s.replace(' ', '')
    try:
        return float(s)
    except ValueError:
        return None


def clasificar_oferta(cell):
    """§5.1 — parte la celda de 'Estado de la oferta XX' en campos AL ENTRAR.
    Las cuatro son mutuamente excluyentes y exhaustivas (Guarda 5)."""
    c = _clean(cell)
    tiene = c.startswith('€')
    sin_listing = (c == 'No hay listing')
    no_requiere = (c == 'No requiere oferta')
    motivo = None
    if not (tiene or sin_listing or no_requiere):
        # 'Material peligroso', 'Alimentación', 'Tipo de producto', combinaciones…
        # Se guarda LITERAL: no normalizar, no partir por comas, no mapear a enum.
        motivo = c if c != '' else None
    return {
        'tiene_oferta': tiene,
        'sin_listing': sin_listing,
        'no_requiere_oferta': no_requiere,
        'motivo_bloqueo': motivo,
        'precio': precio_eur(c) if tiene else None,
        'crudo_celda': cell if cell is not None else '',
    }


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales. Sin tocar la base todavía.
#    Devuelve filas de las DOS tablas + los avisos que van "en el dato".
# ---------------------------------------------------------------------------
def analizar(texto, fichero, snapshot_date):
    lector = csv.reader(io.StringIO(texto), delimiter='\t')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Anti-vacío (sin datos = fichero incompleto o no es TSV): aborta.
    if len(filas) < 2:
        raise Aborta("[anti-vacío] 0 filas de datos (fichero vacío o no es TSV). Abortando.")

    cabecera = [_clean(c) for c in filas[0]]   # _clean quita el BOM (utf-8-sig ya lo hizo)
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)

    # --- Guarda 2: cada columna del MAPA_PAIS debe existir, CON NOMBRE si falta ---
    faltan_pais = [c for c in COLS_PAIS if c not in idx]
    if faltan_pais:
        raise Aborta("[Guarda 2] Falta(n) columna(s) de país del MAPA_PAIS (Amazon las "
                     "renombró; se ABORTA, no se interpola):\n   · "
                     + "\n   · ".join(repr(c) for c in faltan_pais))

    # --- Guarda 1: las 10 columnas del SKU deben existir ---
    faltan_sku = [c for c in COLS_SKU if c not in idx]
    if faltan_sku:
        raise Aborta("[Guarda 1] Falta(n) columna(s) del SKU:\n   · "
                     + "\n   · ".join(repr(c) for c in faltan_sku)
                     + f"\n   Cabecera vista ({len(cabecera)} cols): {cabecera}")

    # --- Guarda 7: país NUEVO (columna extra con pinta de país) → GRITA, no aborta.
    #     Cualquier otra columna desconocida sí rompe "las 30 exactas" (Guarda 1). ---
    paises = dict(MAPA_PAIS)             # país → (col_estado, col_beneficios | None)
    paises_nuevos = []
    extras_no_pais = []
    for h in cabecera:
        if h in CABECERA_ESPERADA:
            continue
        m = RE_PAIS_NUEVO.match(h)
        if m and m.group(1) not in paises:
            code = m.group(1)
            benef = f'Beneficios de PanEU {code}'
            paises[code] = (h, benef if benef in idx else None)
            paises_nuevos.append(code)
        elif h.startswith('Beneficios de PanEU ') and any(
                h == f'Beneficios de PanEU {c}' for c in paises_nuevos):
            continue   # es la pareja de beneficios de un país nuevo ya contado
        else:
            extras_no_pais.append(h)
    if extras_no_pais:
        raise Aborta("[Guarda 1] La cabecera trae columnas desconocidas que no son de país "
                     "(≠ las 30 exactas):\n   · " + "\n   · ".join(repr(h) for h in extras_no_pais))

    def celda(fila, h):
        i = idx.get(h)
        if i is None or i >= len(fila):
            return ''
        return fila[i] if fila[i] is not None else ''

    filas_datos = filas[1:]
    aptos, ofertas = [], []
    skus_vistos = {}
    dup_sku = []
    par_visto = {}
    dup_par = []
    estados_desconocidos = {}   # valor → nº de filas (Guarda 6, "en el dato" vía estado_paneu)

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 cabecera, +1 para numerar desde 1

        sku = _clean(celda(fila, 'MerchantSKU'))
        # Guarda 3: MerchantSKU vacío
        if sku == '':
            raise Aborta(f"[Guarda 3] Fila {num_fila}: 'MerchantSKU' vacío. Abortando.")
        # Guarda 3: MerchantSKU duplicado (se recopilan todos)
        if sku in skus_vistos:
            dup_sku.append(f"{sku} — filas {skus_vistos[sku]} y {num_fila}")
        else:
            skus_vistos[sku] = num_fila

        estado_paneu = txt(celda(fila, 'Estado de PanEU'))
        # Guarda 6: estado fuera de los conocidos → NO aborta, se GUARDA (ya va en
        # estado_paneu, texto libre) y se GRITA.
        if estado_paneu is not None and estado_paneu not in ESTADOS_PANEU_CONOCIDOS:
            estados_desconocidos[estado_paneu] = estados_desconocidos.get(estado_paneu, 0) + 1

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        aptos.append({
            'seller_sku': sku,
            'asin': txt(celda(fila, 'ASIN')),
            'fnsku': txt(celda(fila, 'FnSKU')),
            'titulo': txt(celda(fila, 'Title')),
            'estado_paneu': estado_paneu,
            'registrado': bool_yn(celda(fila, 'Registrarse')),
            'fecha_inscripcion': fecha_utc(celda(fila, 'Enrollment Date')),
            'fecha_caducidad': fecha_utc(celda(fila, 'Fecha en que caduca PanEU')),
            'ultima_actividad': txt(celda(fila, 'Última actividad el')),
            'comentarios': txt(celda(fila, 'Comentarios del producto')),
            'crudo': crudo,
        })

        for pais, (col_estado, col_benef) in paises.items():
            of = clasificar_oferta(celda(fila, col_estado))

            # Guarda 5 (protege el §5.1): los cuatro estados suman EXACTAMENTE 1.
            suma = sum([of['tiene_oferta'], of['sin_listing'],
                        of['no_requiere_oferta'], of['motivo_bloqueo'] is not None])
            if suma != 1:
                raise Aborta(
                    f"[Guarda 5] Fila {num_fila} (sku {sku}, país {pais}): los cuatro estados "
                    f"de la oferta suman {suma}, no 1. Celda literal: "
                    f"{of['crudo_celda']!r}. La columna 'Estado de la oferta' significa tres "
                    f"cosas y esta celda no encaja en ninguna.")

            of['beneficios_paneu'] = (_clean(celda(fila, col_benef)) == 'Y') if col_benef else None

            k = (sku, pais)
            if k in par_visto:
                dup_par.append(f"({sku}, {pais}) — filas {par_visto[k]} y {num_fila}")
            else:
                par_visto[k] = num_fila

            ofertas.append({
                'seller_sku': sku, 'pais': pais,
                'tiene_oferta': of['tiene_oferta'], 'precio': of['precio'],
                'sin_listing': of['sin_listing'], 'no_requiere_oferta': of['no_requiere_oferta'],
                'motivo_bloqueo': of['motivo_bloqueo'], 'beneficios_paneu': of['beneficios_paneu'],
                'crudo_celda': _clean(of['crudo_celda']) or None,
            })

    # Guarda 3 (informe final si hubo duplicados de SKU)
    if dup_sku:
        raise Aborta("[Guarda 3] MerchantSKU duplicado (el procesador NO elige):\n   · "
                     + "\n   · ".join(dup_sku))
    # Guarda 4: par (seller_sku, pais) duplicado
    if dup_par:
        raise Aborta("[Guarda 4] Par (seller_sku, pais) duplicado:\n   · "
                     + "\n   · ".join(dup_par))

    # Guarda 8: la aritmética de filas tiene que cuadrar exactamente
    if len(aptos) != len(filas_datos):
        raise Aborta(f"[Guarda 8] Filas de datos del fichero ({len(filas_datos)}) ≠ filas "
                     f"paneu_aptos ({len(aptos)}).")
    if len(ofertas) != len(aptos) * len(paises):
        raise Aborta(f"[Guarda 8] paneu_oferta_pais ({len(ofertas)}) ≠ aptos × países "
                     f"({len(aptos)} × {len(paises)} = {len(aptos) * len(paises)}).")

    return {
        'aptos': aptos, 'ofertas': ofertas, 'fichero': fichero,
        'snapshot_date': snapshot_date, 'paises': list(paises.keys()),
        'paises_nuevos': paises_nuevos, 'estados_desconocidos': estados_desconocidos,
    }


# ---------------------------------------------------------------------------
# DDL: las dos tablas nacen CERRADAS (RLS on, cero políticas). SIN vista.
# ---------------------------------------------------------------------------
SQL_TABLA_APTOS = """
CREATE TABLE IF NOT EXISTS paneu_aptos (
    seller_sku        text NOT NULL,
    asin              text,
    fnsku             text,
    titulo            text,
    estado_paneu      text,
    registrado        boolean,
    fecha_inscripcion timestamptz,
    fecha_caducidad   timestamptz,
    ultima_actividad  text,
    comentarios       text,
    snapshot_date     date,
    fichero           text,
    crudo             jsonb,
    procesado_en      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_sku)
);
"""

SQL_TABLA_OFERTA = """
CREATE TABLE IF NOT EXISTS paneu_oferta_pais (
    seller_sku         text NOT NULL,
    pais               text NOT NULL,
    tiene_oferta       boolean,
    precio             numeric,
    sin_listing        boolean,
    no_requiere_oferta boolean,
    motivo_bloqueo     text,
    beneficios_paneu   boolean,
    crudo_celda        text,
    snapshot_date      date,
    fichero            text,
    procesado_en       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_sku, pais)
);
"""

COLS_APTOS = ['seller_sku', 'asin', 'fnsku', 'titulo', 'estado_paneu', 'registrado',
              'fecha_inscripcion', 'fecha_caducidad', 'ultima_actividad', 'comentarios']
COLS_OFERTA = ['seller_sku', 'pais', 'tiene_oferta', 'precio', 'sin_listing',
               'no_requiere_oferta', 'motivo_bloqueo', 'beneficios_paneu', 'crudo_celda']


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 🔒 PRIMERA línea del log, bien visible.
    print("=== PROCESADOR PANEU_APTOS (EJE PAÍS · PR #1) ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 48, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA) or []
    except Exception as e:
        sys.exit(f"No se pudo listar {BUCKET}/{CARPETA}/ ({e}). ¿Existe la carpeta?")
    tsvs = [o for o in objs if (o.get('name') or '').lower().endswith(('.tsv', '.txt'))]
    if not tsvs:
        # §9: sin fichero en el buzón, el ensayo aborta en el primer paso. Es el orden.
        sys.exit(f"No hay ningún .tsv/.txt en {BUCKET}/{CARPETA}/. Sube el informe "
                 "'Inventario Paneuropeo de Logística de Amazon' y relanza. "
                 "(Sin fichero, el ensayo aborta en el primer paso: es el orden, no un fallo.)")
    tsvs.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    elegido = tsvs[0]
    fichero = elegido['name']
    print(f"Informe elegido (el más reciente): {fichero}", flush=True)

    # snapshot_date: el fichero no trae columna de snapshot ni fecha en el nombre;
    # se toma la fecha de subida del objeto (cuándo se puso esta foto en el buzón).
    sello = elegido.get('updated_at') or elegido.get('created_at') or ''
    try:
        snapshot_date = datetime.fromisoformat(sello.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        snapshot_date = date.today()
    print(f"   · snapshot_date={snapshot_date} (fecha de subida al buzón)", flush=True)

    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")
    # 🔴 TRAMPA 1: este fichero LLEVA BOM → utf-8-sig. Fallback cp1252.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero, snapshot_date)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    aptos, ofertas = info['aptos'], info['ofertas']
    paises = info['paises']

    # --- Lo que GRITA (Guardas 6 y 7): en el log Y en el dato ---
    if info['estados_desconocidos']:
        print("\n⚠️  [Guarda 6] Estado(s) de PanEU FUERA de los conocidos "
              "(se guardan en estado_paneu y se GRITA; Amazon pudo añadir un estado):",
              flush=True)
        for val, n in sorted(info['estados_desconocidos'].items()):
            print(f"        · {val!r} en {n} fila(s)", flush=True)
    if info['paises_nuevos']:
        print("\n⚠️  [Guarda 7] País(es) NUEVO(s) en la cabecera "
              "(se cargan como filas de paneu_oferta_pais y se GRITA; Amazon abrió un país):",
              flush=True)
        for code in info['paises_nuevos']:
            print(f"        · {code}", flush=True)

    print(f"\nFilas leídas y cuadradas: paneu_aptos {len(aptos)} · "
          f"paneu_oferta_pais {len(ofertas)} ({len(aptos)} SKU × {len(paises)} países)", flush=True)

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # Claves previas (para contar altas vs actualizaciones)
    def claves_previas(tabla, cols):
        cur.execute(f"SELECT to_regclass('public.{tabla}');")
        if cur.fetchone()[0] is None:
            return set()
        cur.execute(f"SELECT {', '.join(cols)} FROM {tabla};")
        return {tuple(str(x).strip() for x in row) for row in cur.fetchall()}

    prev_aptos = claves_previas('paneu_aptos', ['seller_sku'])
    prev_ofertas = claves_previas('paneu_oferta_pais', ['seller_sku', 'pais'])

    # --- Crear tablas (nacen CERRADAS) e índices. SIN vista. ---
    cur.execute(SQL_TABLA_APTOS)
    cur.execute(SQL_TABLA_OFERTA)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paneu_aptos_asin ON paneu_aptos(asin);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paneu_oferta_pais_pais ON paneu_oferta_pais(pais);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paneu_oferta_pais_sku ON paneu_oferta_pais(seller_sku);")
    cur.execute("ALTER TABLE paneu_aptos ENABLE ROW LEVEL SECURITY;")
    cur.execute("ALTER TABLE paneu_oferta_pais ENABLE ROW LEVEL SECURITY;")

    # --- Volcar paneu_aptos ---
    cols_a = COLS_APTOS + ['snapshot_date', 'fichero', 'crudo']
    ph_a = ", ".join(['%s'] * len(cols_a))
    upd_a = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols_a if c != 'seller_sku')
    sql_a = (f"INSERT INTO paneu_aptos ({', '.join(cols_a)}) VALUES ({ph_a}) "
             f"ON CONFLICT (seller_sku) DO UPDATE SET {upd_a}, procesado_en=now();")
    for r in aptos:
        cur.execute(sql_a, [r[c] for c in COLS_APTOS]
                    + [info['snapshot_date'], fichero, Json(r['crudo'])])

    # --- Volcar paneu_oferta_pais ---
    cols_o = COLS_OFERTA + ['snapshot_date', 'fichero']
    ph_o = ", ".join(['%s'] * len(cols_o))
    upd_o = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols_o if c not in ('seller_sku', 'pais'))
    sql_o = (f"INSERT INTO paneu_oferta_pais ({', '.join(cols_o)}) VALUES ({ph_o}) "
             f"ON CONFLICT (seller_sku, pais) DO UPDATE SET {upd_o}, procesado_en=now();")
    for r in ofertas:
        cur.execute(sql_o, [r[c] for c in COLS_OFERTA] + [info['snapshot_date'], fichero])

    altas_aptos = sum(1 for r in aptos if (r['seller_sku'],) not in prev_aptos)
    altas_ofertas = sum(1 for r in ofertas if (r['seller_sku'], r['pais']) not in prev_ofertas)

    # --- Resumen: los números del §7, calculados y mostrados (verificar por SQL) ---
    print(f"\n--- Lo que {'se ha escrito' if MODO == 'aplicar' else 'se escribiría'} "
          f"({ENTORNO}) ---")
    print(f"   · paneu_aptos:       {len(aptos)} filas  (altas {altas_aptos})")
    print(f"   · paneu_oferta_pais: {len(ofertas)} filas  (altas {altas_ofertas})")

    from collections import Counter
    est = Counter(r['estado_paneu'] for r in aptos)
    reg = Counter(r['registrado'] for r in aptos)
    print("\n--- paneu_aptos (§7) ---")
    print("   · estado_paneu: " + " · ".join(f"{k} {v}" for k, v in est.most_common()))
    print(f"   · registrado: Y {reg.get(True, 0)} · N {reg.get(False, 0)} · "
          f"otros {reg.get(None, 0)}")
    print(f"   · fecha_inscripcion no nula: {sum(1 for r in aptos if r['fecha_inscripcion'])}"
          f"      fecha_caducidad no nula: {sum(1 for r in aptos if r['fecha_caducidad'])}")
    print(f"   · ultima_actividad no nula: {sum(1 for r in aptos if r['ultima_actividad'])}"
          f"      comentarios no nulos: {sum(1 for r in aptos if r['comentarios'])}")

    print("\n--- paneu_oferta_pais por país (§7) — cada fila suma 328 en horizontal ---")
    print(f"   {'país':4} {'oferta':>7} {'motivo':>7} {'listing':>8} {'no_req':>7} {'benef':>6}  suma")
    tot = Counter()
    for pais in paises:
        f = [r for r in ofertas if r['pais'] == pais]
        o = sum(1 for r in f if r['tiene_oferta'])
        mb = sum(1 for r in f if r['motivo_bloqueo'] is not None)
        sl = sum(1 for r in f if r['sin_listing'])
        nr = sum(1 for r in f if r['no_requiere_oferta'])
        bn = sum(1 for r in f if r['beneficios_paneu'])
        tot['oferta'] += o; tot['benef'] += bn
        print(f"   {pais:4} {o:7} {mb:7} {sl:8} {nr:7} {bn:6}  {o + mb + sl + nr}")
    print(f"   {'TOT':4} {tot['oferta']:7} {'':7} {'':8} {'':7} {tot['benef']:6}")

    # --- Escritura (o no) ---
    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: paneu_aptos {len(aptos)} · paneu_oferta_pais "
              f"{len(ofertas)} (tablas listas, RLS activo sin políticas, sin vista).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(Las tablas y el volcado se han probado dentro de una transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · aptos={len(aptos)} · "
          f"ofertas={len(ofertas)} · paises={len(paises)} · "
          f"estados_desconocidos={len(info['estados_desconocidos'])} · "
          f"paises_nuevos={len(info['paises_nuevos'])} ===", flush=True)


if __name__ == '__main__':
    main()
