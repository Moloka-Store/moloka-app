# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR LEDGER — el LIBRO MAYOR de movimientos FBA (7ª pieza, Fase 0)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el "Libro mayor / Ledger" del Seller (Vista detallada + Centro logístico
#   + Diario; .txt separado por TAB) del buzón informes/ledger/ (Supabase Storage
#   de PRODUCCIÓN, aunque el ENTORNO sea staging: solo cambia DB_URL) y carga los
#   movimientos FBA en la tabla `ledger_movimientos`.
#
#   Es el EXTRACTO: de dónde salió cada unidad y a dónde fue. PELÍCULA, no foto.
#
# 🔴 POR QUÉ NO HAY LLAVE Y CÓMO SE CARGA (la decisión de diseño de este PR)
#   Medido contra el fichero real: NO existe llave natural única. Hay 6.623
#   filas idénticas campo por campo a otra (movimientos reales distintos e
#   indistinguibles: dos ventas de 1 ud del mismo producto/centro/día, sin
#   Reference ID). Ni el hash de la fila entera es único. Consecuencia:
#     ❌ NO patrón foto (foto_comun/barrer_sobrantes): borraría el histórico.
#     ❌ NO append por PK de campos: colapsaría los 6.623 idénticos, PERDIENDO
#        movimientos reales.
#     ✅ CARGA POR RANGO DE FECHAS (recerrar un periodo del mayor):
#        1) hallar [fecha_min, fecha_max] de la columna Date del fichero;
#        2) en UNA transacción:
#             DELETE FROM ledger_movimientos WHERE fecha BETWEEN min AND max;
#           y luego INSERT de TODOS los movimientos del fichero (PK sintética);
#        3) commit si aplicar, rollback si ensayo.
#   Idempotente: recargar el mismo fichero deja el mismo resultado. Lo anterior
#   a fecha_min NO se toca (rango parcial reemplaza solo su rango). Los idénticos
#   se reinsertan todos: la PK es sintética (id IDENTITY), no de campos, así que
#   NO se colapsa ninguno.
#
# USO PREVISTO: ~1 vez al mes, descargando el último año completo (~365 días,
#   fichero grande como el real, 24.286 movimientos). Cada carga reescribe todo
#   ese rango con los mismos datos (idempotente) y añade el mes nuevo; lo de hace
#   más de un año queda intacto. Autorregenera huecos (un mes olvidado se rellena
#   solo). Por eso: (a) inserción por LOTES (execute_values), no fila a fila;
#   (b) la guarda anti-encogimiento por rango entiende que el año trae SIEMPRE
#   ≥ lo que ya había en ese rango → en uso normal NO aborta (solo protege ante
#   un fichero truncado de verdad).
#
# 🔒 NO escribe identidad (ni productos ni nada de v1). Solo carga movimientos.
#    Las conciliaciones (envíos perdidos, cruce con salud_fba y con envios_fba)
#    son VISTAS/pasos posteriores, NO en este PR.
#
# Encoding SIN BOM (medido; como el internacional): utf-8-sig decodifica bien
#   igual, fallback cp1252. Separador TAB.
# ============================================================================

import os, sys, io, csv, re
from datetime import date, datetime
from collections import Counter

import psycopg2
from psycopg2.extras import Json, execute_values

# Del patrón común solo se reutiliza Aborta: la carga por rango es lógica propia
# (barrer_sobrantes es para FOTOS y aquí borraría el histórico).
from foto_comun import Aborta

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

BUCKET, CARPETA = 'informes', 'ledger'

# ---------------------------------------------------------------------------
# Columnas: (encabezado EXACTO del .txt, columna Postgres). El tipo se aplica en
# el parseo por nombre (fecha, quantity y fecha_hora tienen guarda propia).
# 🔒 El encabezado se compara EXACTO. Si uno no aparece → Guarda 1 ABORTA.
# ---------------------------------------------------------------------------
TIPADAS = [
    ('Date',                  'fecha'),              # MM/DD/YYYY → date (Guarda 3)
    ('FNSKU',                 'fnsku'),
    ('ASIN',                  'asin'),
    ('MSKU',                  'msku'),
    ('Title',                 'titulo'),
    ('Event Type',            'event_type'),
    ('Reference ID',          'reference_id'),
    ('Quantity',              'quantity'),           # entero, permite negativo y 0 (Guarda 4)
    ('Fulfillment Center',    'fulfillment_center'),
    ('Disposition',           'disposition'),
    ('Reason',                'reason'),
    ('Country',               'country'),
    ('Reconciled Quantity',   'reconciled_qty'),     # entero leniente → NULL si no parsea
    ('Unreconciled Quantity', 'unreconciled_qty'),   # entero leniente → NULL si no parsea
    ('Date and Time',         'fecha_hora'),         # ISO → timestamptz (leniente → NULL)
]
CABECERA_ESPERADA = [h for h, _ in TIPADAS]

# Columnas de la tabla en el orden del INSERT (id IDENTITY y procesado_at aparte).
COLS_DB = [c for _, c in TIPADAS] + ['fichero', 'crudo']

# Los 6 Event Type medidos; otro valor NO aborta, se GRITA (Guarda 6).
EVENT_TYPES_CONOCIDOS = {'Shipments', 'WhseTransfers', 'Receipts',
                         'Adjustments', 'CustomerReturns', 'VendorReturns'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()

def txt(v):
    s = _clean(v)
    return s or None

def ent_leniente(v):
    """Entero o None (para reconciled/unreconciled: no tienen guarda de aborto)."""
    s = _clean(v)
    if s == '':
        return None
    try:
        return int(s)
    except ValueError:
        return None

_RE_OFFSET = re.compile(r'([+-]\d{2})(\d{2})$')

def marca_tiempo(v):
    """'2026-07-20T01:00:00+0100' → timestamptz. NULL si no casa (el crudo lo
    conserva). fromisoformat acepta '+0100' en 3.11+, pero se mete ':' por si
    acaso para no depender de la versión."""
    s = _clean(v)
    if s == '':
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        s2 = _RE_OFFSET.sub(r'\1:\2', s)
        try:
            return datetime.fromisoformat(s2)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..4, 6). Sin tocar la base todavía.
# ---------------------------------------------------------------------------
def analizar(texto, fichero):
    lector = csv.reader(io.StringIO(texto), delimiter='\t')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 2: anti-vacío (≥1 movimiento)
    if len(filas) < 2:
        raise Aborta("[Guarda 2] 0 movimientos (fichero vacío o no es TAB-separated). "
                     "Abortando.")

    cabecera = [_clean(c) for c in filas[0]]
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)

    # Guarda 1: las 15 columnas EXACTAS existen (§0: no se conjetura, se ABORTA)
    faltan = [h for h in CABECERA_ESPERADA if h not in idx]
    if faltan:
        raise Aborta(
            "[Guarda 1] Encabezado(s) que NO aparecen EXACTOS en el .txt "
            "(regla que mató al PR #26: se ABORTA, no se aproxima):\n   · "
            + "\n   · ".join(repr(h) for h in faltan)
            + f"\n   Cabecera real ({len(cabecera)} cols): {cabecera}")

    def celda(fila, h):
        i = idx.get(h)
        if i is None or i >= len(fila):
            return ''
        return _clean(fila[i])

    filas_datos = filas[1:]
    movimientos = []
    event_desconocidos = Counter()

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 cabecera, +1 para numerar desde 1

        # Guarda 3: Date parsea como MM/DD/YYYY
        d_raw = celda(fila, 'Date')
        m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', d_raw)
        if not m:
            raise Aborta(f"[Guarda 3] Fila {num_fila}: 'Date' no es MM/DD/YYYY: {d_raw!r}. "
                         f"Abortando.")
        try:
            fecha = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            raise Aborta(f"[Guarda 3] Fila {num_fila}: fecha inexistente en el calendario: "
                         f"{d_raw!r} (leída MM/DD/YYYY). Abortando.")

        # Guarda 4: Quantity entero (permite negativo y 0)
        q_raw = celda(fila, 'Quantity')
        try:
            quantity = int(q_raw)
        except ValueError:
            raise Aborta(f"[Guarda 4] Fila {num_fila}: 'Quantity' no es un entero: "
                         f"{q_raw!r}. Abortando.")

        event_type = celda(fila, 'Event Type')
        # Guarda 6: Event Type fuera de los conocidos → NO aborta, se GRITA
        if event_type and event_type not in EVENT_TYPES_CONOCIDOS:
            event_desconocidos[event_type] += 1

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        movimientos.append({
            'fecha': fecha,
            'fnsku': txt(celda(fila, 'FNSKU')),
            'asin': txt(celda(fila, 'ASIN')),
            'msku': txt(celda(fila, 'MSKU')),
            'titulo': txt(celda(fila, 'Title')),
            'event_type': txt(event_type),
            'reference_id': txt(celda(fila, 'Reference ID')),
            'quantity': quantity,
            'fulfillment_center': txt(celda(fila, 'Fulfillment Center')),
            'disposition': txt(celda(fila, 'Disposition')),
            'reason': txt(celda(fila, 'Reason')),
            'country': txt(celda(fila, 'Country')),
            'reconciled_qty': ent_leniente(celda(fila, 'Reconciled Quantity')),
            'unreconciled_qty': ent_leniente(celda(fila, 'Unreconciled Quantity')),
            'fecha_hora': marca_tiempo(celda(fila, 'Date and Time')),
            'crudo': crudo,
        })

    fecha_min = min(mv['fecha'] for mv in movimientos)
    fecha_max = max(mv['fecha'] for mv in movimientos)

    return {'movimientos': movimientos, 'fichero': fichero,
            'fecha_min': fecha_min, 'fecha_max': fecha_max,
            'event_desconocidos': event_desconocidos}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas). PK sintética.
# ---------------------------------------------------------------------------
SQL_TABLA = """
CREATE TABLE IF NOT EXISTS ledger_movimientos (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha              date NOT NULL,
    fnsku              text,
    asin               text,
    msku               text,
    titulo             text,
    event_type         text,
    reference_id       text,
    quantity           integer,
    fulfillment_center text,
    disposition        text,
    reason             text,
    country            text,
    reconciled_qty     integer,
    unreconciled_qty   integer,
    fecha_hora         timestamptz,
    fichero            text,
    crudo              jsonb,
    procesado_at       timestamptz NOT NULL DEFAULT now()
);
"""

SQL_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_ledger_fecha ON ledger_movimientos(fecha);",
    "CREATE INDEX IF NOT EXISTS idx_ledger_event_type ON ledger_movimientos(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_ledger_reference_id ON ledger_movimientos(reference_id);",
    "CREATE INDEX IF NOT EXISTS idx_ledger_asin ON ledger_movimientos(asin);",
    "CREATE INDEX IF NOT EXISTS idx_ledger_country ON ledger_movimientos(country);",
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== PROCESADOR LEDGER (LIBRO MAYOR · carga por rango) ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 56, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA) or []
    except Exception as e:
        sys.exit(f"No se pudo listar {BUCKET}/{CARPETA}/ ({e}). ¿Existe la carpeta? "
                 "Créala y sube el 'Libro mayor / Ledger' en .txt.")
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    if not txts:
        sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. Sube el 'Libro mayor / Ledger' "
                 "(.txt, descargado del Seller) y relanza. (Sin fichero, el ensayo aborta "
                 "en el primer paso: es el orden, no un fallo.)")
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    fichero = txts[0]['name']
    print(f"Informe elegido (el más reciente de {len(txts)}): {fichero}", flush=True)

    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales 1..4, 6 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    movs = info['movimientos']
    fmin, fmax = info['fecha_min'], info['fecha_max']

    # Guarda 6: Event Type desconocido → GRITA (en el log Y en el dato, queda en event_type)
    if info['event_desconocidos']:
        print("\n⚠️  [Guarda 6] Event Type FUERA de los 6 conocidos (se guarda tal cual en "
              "event_type y se GRITA; NO aborta):", flush=True)
        for val, n in info['event_desconocidos'].most_common():
            print(f"        · {val!r} en {n} fila(s)", flush=True)

    # Desglose del fichero (se verifica por SQL después)
    ev = Counter(mv['event_type'] for mv in movs)
    co = Counter(mv['country'] for mv in movs)
    print(f"\nMovimientos leídos: {len(movs)} · rango {fmin} → {fmax}", flush=True)
    print("   Event Type:  " + " · ".join(f"{k} {v}" for k, v in ev.most_common()), flush=True)
    print("   Country:     " + " · ".join(f"{k} {v}" for k, v in co.most_common()), flush=True)

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # Crear tabla (nace CERRADA) e índices — dentro de la transacción.
    cur.execute(SQL_TABLA)
    for ddl in SQL_INDICES:
        cur.execute(ddl)
    cur.execute("ALTER TABLE ledger_movimientos ENABLE ROW LEVEL SECURITY;")

    # --- Guarda 5: anti-encogimiento POR RANGO ---
    # Cuenta lo que ya había en [fmin, fmax]. Si el fichero trae < 50% → ABORTA
    # (fichero truncado). En la 1ª carga (0 en rango) no aborta.
    cur.execute("SELECT count(*) FROM ledger_movimientos WHERE fecha BETWEEN %s AND %s;",
                (fmin, fmax))
    previas_rango = cur.fetchone()[0]
    if len(movs) < previas_rango * 0.5:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 5] El fichero trae {len(movs)} movimientos en el rango "
              f"{fmin}→{fmax} y en la tabla ya había {previas_rango}: menos del 50%. "
              f"Un ledger a medias no da información incompleta, da información FALSA. "
              f"No se borra ni se escribe nada.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Guarda 7: PAÍS NUEVO (alerta fiscal; NO aborta) ---
    # Dinámica, sin lista hardcodeada: compara los países del fichero con los que
    # YA hay en la tabla. País del fichero que no estaba (y tabla no vacía) → GRITA.
    cur.execute("SELECT DISTINCT country FROM ledger_movimientos WHERE country IS NOT NULL;")
    paises_bd = {r[0] for r in cur.fetchall()}
    paises_fichero = {mv['country'] for mv in movs if mv['country']}
    if not paises_bd:
        print(f"\n1ª carga (tabla vacía): países iniciales del ledger → "
              f"{sorted(paises_fichero)}", flush=True)
    else:
        nuevos = sorted(paises_fichero - paises_bd)
        for x in nuevos:
            print(f"\n🆕 PAÍS NUEVO detectado: {x}. Amazon ha empezado a almacenar ahí "
                  f"(Pan-EU); posible NUEVA OBLIGACIÓN DE IVA en ese país — revisar.",
                  flush=True)

    # --- Carga por rango: DELETE del rango + INSERT de todo (misma transacción) ---
    cur.execute("DELETE FROM ledger_movimientos WHERE fecha BETWEEN %s AND %s;", (fmin, fmax))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [
        [mv['fecha'], mv['fnsku'], mv['asin'], mv['msku'], mv['titulo'],
         mv['event_type'], mv['reference_id'], mv['quantity'], mv['fulfillment_center'],
         mv['disposition'], mv['reason'], mv['country'], mv['reconciled_qty'],
         mv['unreconciled_qty'], mv['fecha_hora'], fichero, Json(mv['crudo'])]
        for mv in movs
    ]
    execute_values(
        cur,
        f"INSERT INTO ledger_movimientos ({', '.join(COLS_DB)}) VALUES %s",
        valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- Resumen ---
    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- LEDGER (carga por rango {fmin} → {fmax}) ---")
    print(f"   · movimientos del fichero:        {len(movs)}")
    print(f"   · ya había en ese rango (BD):      {previas_rango}")
    print(f"   · BORRADOS del rango ({verbo}):    {borradas}")
    print(f"   · INSERTADOS ({verbo}):            {insertadas}")
    print(f"   · anteriores a {fmin} (intactos):  no se tocan")

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} movimientos en ledger_movimientos "
              f"(rango {fmin}→{fmax} recerrado; RLS activo sin políticas).")
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(El borrado por rango y el volcado se han probado dentro de una "
              f"transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · movimientos={len(movs)} · "
          f"rango={fmin}→{fmax} · borrados_rango={borradas} · insertados={insertadas} · "
          f"event_desconocidos={len(info['event_desconocidos'])} ===", flush=True)


if __name__ == '__main__':
    main()
