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
# 🔴 GUARDA 8 (el extracto no encoge) — POR QUÉ LA GUARDA 5 NO BASTABA
#   La Guarda 5 mira SOLO el total del rango y tolera hasta un 50% de merma. Un año
#   exportado con UN MES EN BLANCO en medio conserva fmin=enero y fmax=diciembre, el
#   total sigue muy por encima del 50%, la 5 pasa… y entonces el DELETE se lleva los
#   doce meses mientras el INSERT devuelve once. Ese mes desaparecía del extracto sin
#   que chillara nadie. La Guarda 8 compara lo que de verdad se BORRA con lo que de
#   verdad ENTRA: si el TOTAL del rango encoge, ABORTA.
#
#   🔴 POR QUÉ NO BASTA EL TOTAL, Y CÓMO DECIDE POR DÍA (8a) + LA RED (8b)
#   La Guarda 8 mirando solo TOTALES no ve una merma en un día si otro tramo del mismo
#   rango crece y la compensa. Medido el 30-jul contra DOS exportaciones reales del
#   mismo libro mayor (50465020654.txt en staging, 50505020662.txt en producción): de
#   los 89 días que solapan, 88 traen EXACTAMENTE las mismas filas y uno no — el
#   2026-07-20, con 281 filas en una y 176 en la otra. Cargar el ancho sobre el estrecho
#   destruiría 105 asientos con un control por total en verde (el ancho trae 7 meses de
#   más que compensan). Por eso la Guarda 8 decide POR DÍA:
#     · 8a — recuento BD vs FICHERO día a día. Un día de EN MEDIO que encoge o
#       desaparece → el fichero está incompleto → ABORTA (antes del DELETE, sin tocar
#       nada). Un día del BORDE (primero/último del rango) que encoge → NO aborta: puede
#       ser un corte legítimo (rango que acaba en el día en curso), así que se ESTRECHA
#       el rango y ese día se deja como está en la BD. Condicional: solo si de verdad
#       encoge, nunca por sistema.
#     · 8b — red de última hora sobre el total del rango efectivo. Con la 8a activa es
#       matemáticamente inalcanzable; existe SOLO por si la 8a tiene un fallo o alguien
#       escribe en la tabla entre el recuento y el DELETE. NO es ella quien caza el
#       fichero incompleto.
#   Al mismo coste que antes: el recuento por día es un GROUP BY donde antes había un
#   DISTINCT.
#   🔒 Los días se comparan BD-contra-FICHERO, JAMÁS contra el calendario: hay días
#   sin ningún movimiento que son perfectamente legítimos (medido el 30-jul: en
#   transacciones IT solo 64 de 201 días de calendario tienen movimiento). Un detector
#   por calendario daría 137 falsos positivos en ese solo país.
#
# 🔒 NO escribe identidad (ni productos ni nada de v1). Solo carga movimientos.
#    Las conciliaciones (envíos perdidos, cruce con salud_fba y con envios_fba)
#    son VISTAS/pasos posteriores, NO en este PR.
#
# Encoding SIN BOM (medido; como el internacional): utf-8-sig decodifica bien
#   igual, fallback cp1252. Separador TAB.
# ============================================================================

import os, sys, io, csv, re
from datetime import date, datetime, timedelta
from collections import Counter

import psycopg2
from psycopg2.extras import Json, execute_values

# Del patrón común solo se reutiliza Aborta: la carga por rango es lógica propia
# (barrer_sobrantes es para FOTOS y aquí borraría el histórico).
from foto_comun import Aborta, listar_buzon, descargar_buzon

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
    seguidas, no. (Se duplica en procesador_transacciones.py a propósito: foto_comun
    es el patrón de las FOTOS y estos dos son PELÍCULAS — no se toca.)"""
    partes = []
    for a, b in _tramos_de_dias(dias):
        partes.append(str(a) if a == b else f"{a}→{b} ({(b - a).days + 1} días)")
    return " · ".join(partes)


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

# Los índices de ledger_movimientos se movieron a
# migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql (son migración, no
# arranque: CREATE INDEX en cada carga pedía lock sobre la tabla).


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
    objs = listar_buzon(sb, BUCKET, CARPETA)  # reintenta cortes de red; aborta si no lo es
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    if not txts:
        sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. Sube el 'Libro mayor / Ledger' "
                 "(.txt, descargado del Seller) y relanza. (Sin fichero, el ensayo aborta "
                 "en el primer paso: es el orden, no un fallo.)")
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    fichero = txts[0]['name']
    print(f"Informe elegido (el más reciente de {len(txts)}): {fichero}", flush=True)

    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")
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

    # Crear tabla — dentro de la transacción. RLS e índices ya NO aquí (migración).
    cur.execute(SQL_TABLA)
    # 🔒 El ENABLE RLS pedía AccessExclusiveLock sobre ledger_movimientos EN CADA
    # carga (el lock que dejaba fuera al sondeo de la cola). RLS e índices viven en
    # migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql. Solo se comprueba
    # que la tabla está CERRADA (RLS activa); si no, ABORTA pidiéndola.
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.ledger_movimientos'::regclass;")
    if not cur.fetchone()[0]:
        raise Aborta(
            "RLS no está activa en ledger_movimientos. Ya NO la activa el procesador (era un lock "
            "exclusivo en cada carga). Aplica migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql y relanza.")

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

    # --- Guarda 8 (1ª parte): RECUENTO POR DÍA de lo que había, ANTES de borrar ---
    # Se lee aquí y no después porque después del DELETE ya no hay con qué comparar.
    # 🔒 Por RECUENTO, no por presencia: un día que viene "a medias" (el día de corte
    # de una exportación) no falta, pero pierde movimientos igual. Medido: 2026-07-20
    # trae 281 filas en una exportación y 176 en otra.
    # 🔒 BD contra FICHERO, nunca contra el calendario: un día sin movimientos es
    # legítimo y no se inventa un hueco donde no lo hay.
    cur.execute("SELECT fecha, count(*) FROM ledger_movimientos "
                "WHERE fecha BETWEEN %s AND %s GROUP BY fecha;", (fmin, fmax))
    filas_bd_dia = {f: n for f, n in cur.fetchall()}
    filas_fich_dia = Counter(mv['fecha'] for mv in movs)

    dias_perdidos = sorted(d for d in filas_bd_dia if d not in filas_fich_dia)
    dias_adelgazan = sorted((d, filas_bd_dia[d], filas_fich_dia[d]) for d in filas_bd_dia
                            if d in filas_fich_dia and filas_fich_dia[d] < filas_bd_dia[d])

    def _pinta(perdidos, adelgazan, sangria="        "):
        """El detalle del hueco. Se usa en el aviso, en el aborto y en el resumen: el
        mismo texto en todos para que no haya dos versiones de la verdad."""
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

    # 🔴 EL BORDE ES DISTINTO DEL MEDIO, Y ESA DISTINCIÓN ES TODA LA GUARDA 8
    #   fmin y fmax salen del PROPIO fichero, así que el borde NUNCA puede faltar: solo
    #   puede venir ADELGAZADO. Y puede venir cortado de forma LEGÍTIMA: cuando el rango
    #   termina en el día EN CURSO, ese día trae solo las horas transcurridas hasta que
    #   se pulsó exportar. Pero NO es sistemático — depende de dónde caiga el corte.
    #   Medido en producción (97 días): mediana 157 filas/día, p10 83. El primer día
    #   (23-abr) trae 84 → cortado. El último (28-jul) trae 162, POR ENCIMA de la mediana
    #   → NO cortado. Por eso el recorte es CONDICIONAL: solo si ese borde encoge frente
    #   a la BD, nunca por sistema. Y ojo: 12 días de en medio traen menos de 84 filas,
    #   así que "pocas filas" no es señal de corte — la señal es "menos que la BD".
    #   Un día de EN MEDIO no se corta solo. Si encoge o desaparece, el fichero está
    #   incompleto y se ABORTA.
    #   🔒 ASUNCIÓN EXPLÍCITA del recorte: una exportación más corta de un día del borde
    #   es un SUBCONJUNTO de la que ya está en la BD. Se sostiene porque el ledger es
    #   ACUMULATIVO: los movimientos de un día no se corrigen a posteriori, solo se AÑADEN
    #   según avanza el día. Por eso al recortar nos quedamos con lo de la BD (que tiene
    #   más) y descartamos lo del fichero. Si esa asunción se rompiera algún día (un
    #   movimiento del borde desapareciera de verdad), lo conservaríamos DE MÁS, nunca de
    #   menos — que es justo el lado seguro y coherente con "el extracto no encoge".
    BORDE = {fmin, fmax}
    adelgazan_medio = [t for t in dias_adelgazan if t[0] not in BORDE]
    adelgazan_borde = [t for t in dias_adelgazan if t[0] in BORDE]

    # --- Guarda 8a: UN DÍA DE EN MEDIO NO SE CORTA SOLO → ABORTA ---
    # Va ANTES del DELETE: así no se toca nada y no se pide un lock sobre la tabla de
    # Elena para revertirlo un instante después.
    if dias_perdidos or adelgazan_medio:
        print(f"\n❌ ABORTA (no se ha escrito nada; no se ha llegado ni a borrar):\n"
              f"[Guarda 8a] EL EXTRACTO ENCOGE POR DENTRO. En el rango {fmin}→{fmax} hay días "
              f"INTERMEDIOS que la BD tiene y este fichero no cubre:\n"
              + _pinta(dias_perdidos, adelgazan_medio, "      ") + "\n"
              f"   El día de corte de una exportación es el PRIMERO o el ÚLTIMO, nunca uno de "
              f"en medio: un hueco aquí significa que el fichero está INCOMPLETO.\n"
              f"   Vuelve a exportarlo del Seller comprobando el rango de fechas.\n"
              f"   (El ledger es PELÍCULA: lo que se borra no se recupera. Por eso no se "
              f"escribe nada.)", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Regla del BORDE: no se aborta, se ESTRECHA el rango ---
    # 🔴 Estrechar el DELETE NO BASTA: hay que sacar ese día TAMBIÉN del INSERT. Si se
    # borrase menos pero se insertara igual, el día del borde quedaría DUPLICADO (las
    # que ya había + las del fichero). Sacarlo por los dos lados es exactamente lo que
    # significa "ese día se queda como está en la BD".
    fmin_ef, fmax_ef = fmin, fmax
    if any(d == fmin for d, _, _ in adelgazan_borde):
        fmin_ef = fmin + timedelta(days=1)
    if any(d == fmax for d, _, _ in adelgazan_borde):
        fmax_ef = fmax - timedelta(days=1)

    if adelgazan_borde:
        print(f"\n✂️  [Guarda 8 · regla del borde] el borde del fichero viene cortado (es la "
              f"hora a la que se pulsó exportar), así que NO se aborta: se ESTRECHA el rango "
              f"y esos días se dejan tal como están en la BD.")
        for d, antes, ahora in adelgazan_borde:
            cual = 'PRIMER' if d == fmin else 'ÚLTIMO'
            print(f"        · {d} ({cual} día del fichero): trae {ahora} y la BD ya tiene "
                  f"{antes} → se respeta el de la BD")
        print(f"        Rango efectivo: {fmin_ef} → {fmax_ef}", flush=True)

    if fmin_ef > fmax_ef:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 8] Tras aplicar la regla del borde no queda NADA que cargar: el "
              f"fichero cubre {fmin}→{fmax} y sus extremos vienen más flacos que lo que ya "
              f"hay en la BD. Vuelve a exportarlo con un rango más ancho.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    movs_ef = [mv for mv in movs if fmin_ef <= mv['fecha'] <= fmax_ef]
    descartados_borde = len(movs) - len(movs_ef)

    # --- Carga por rango EFECTIVO: DELETE + INSERT (misma transacción) ---
    cur.execute("DELETE FROM ledger_movimientos WHERE fecha BETWEEN %s AND %s;",
                (fmin_ef, fmax_ef))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [
        [mv['fecha'], mv['fnsku'], mv['asin'], mv['msku'], mv['titulo'],
         mv['event_type'], mv['reference_id'], mv['quantity'], mv['fulfillment_center'],
         mv['disposition'], mv['reason'], mv['country'], mv['reconciled_qty'],
         mv['unreconciled_qty'], mv['fecha_hora'], fichero, Json(mv['crudo'])]
        for mv in movs_ef
    ]
    execute_values(
        cur,
        f"INSERT INTO ledger_movimientos ({', '.join(COLS_DB)}) VALUES %s",
        valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- Guarda 8b: RED DE ÚLTIMA HORA (el total del rango efectivo) ---
    # 🔒 En condiciones normales esta comprobación NO PUEDE saltar, y es a propósito:
    # tras la 8a todo día intermedio cumple fichero ≥ BD, y los que no cumplían (el
    # borde) han quedado FUERA del rango efectivo — así que la suma cumple por fuerza.
    # Se deja como red por lo que la comprobación por día no ve: un fallo en esta misma
    # lógica, o una escritura concurrente entre el SELECT del recuento y el DELETE.
    # ⚠️ NO es ella quien caza el fichero incompleto: ésa es la 8a. Que no se documente
    # al revés — este comentario ya mintió una vez (se corrigió en el commit 6c06423).
    if insertadas < borradas:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 8b] EL EXTRACTO ENCOGE EN TOTAL y la comprobación por día no lo vio: "
              f"en {fmin_ef}→{fmax_ef} se iban a BORRAR {borradas} y entran {insertadas} "
              f"({borradas - insertadas} de menos).\n"
              f"   Esto NO debería poder pasar: o hay un fallo en la Guarda 8a, o alguien ha "
              f"escrito en ledger_movimientos mientras corría esta carga. No se escribe nada; "
              f"avisa antes de volver a lanzarlo.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- SELLO DEL RANGO: una fila en informes_subidos (rastro DURABLE) ---
    # Copiado del patrón de procesador_transacciones.py y dentro de la MISMA transacción:
    # en ensayo se prueba y se revierte igual que todo lo demás.
    # Por qué existe: dentro de un mes, qué rango se cargó hoy solo viviría en el log de
    # la corrida, que caduca. Una cifra sin la fecha del dato que la sostiene miente.
    # 🔒 Esto NO cambia la tarjeta de frescura de la v2: frescura_informes() tiene la lista
    # CABLEADA y su línea de 'ledger' lee de ledger_movimientos, no de aquí (solo la de
    # 'transacciones' lee del sello). Es rastro de auditoría, no un dato de pantalla.
    # 🔒 fecha_dato_desde/hasta llevan el rango DEL FICHERO (fmin/fmax): es hasta dónde
    # llega el dato. El rango EFECTIVO que se reescribió va en el resumen_json.
    resumen = {
        'tipo': 'ledger', 'archivo': fichero,
        'fecha_desde': fmin.isoformat(), 'fecha_hasta': fmax.isoformat(),
        'rango_efectivo_desde': fmin_ef.isoformat(),
        'rango_efectivo_hasta': fmax_ef.isoformat(),
        'filas_fichero': len(movs), 'borradas': borradas, 'insertadas': insertadas,
        'guarda8': 'pasa · borde recortado' if adelgazan_borde else 'pasa · sin huecos',
        'dias_recortados_borde': [{'dia': d.isoformat(), 'bd': antes, 'fichero': ahora}
                                  for d, antes, ahora in adelgazan_borde],
        'movimientos_descartados_borde': descartados_borde,
        'fuente': 'procesador_ledger (Fase 0)',
    }
    cur.execute(
        "INSERT INTO informes_subidos "
        "(tipo, archivo_nombre, filas_procesadas, filas_validas, filas_descartadas, "
        " fecha_dato_desde, fecha_dato_hasta, resumen_json, procesado_at, notas) "
        "VALUES ('ledger', %s, %s, %s, %s, %s, %s, %s, now(), %s);",
        (fichero, len(movs), insertadas, descartados_borde, fmin, fmax, Json(resumen),
         'procesador_ledger Fase 0 · carga por rango'))

    # --- Resumen ---
    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- LEDGER (carga por rango {fmin} → {fmax}) ---")
    print(f"   · movimientos del fichero:        {len(movs)}")
    print(f"   · ya había en ese rango (BD):      {previas_rango}")
    print(f"   · BORRADOS del rango ({verbo}):    {borradas}")
    print(f"   · INSERTADOS ({verbo}):            {insertadas}")
    print(f"   · anteriores a {fmin} (intactos):  no se tocan")
    if adelgazan_borde:
        print(f"   · ✂️  BORDE recortado: rango efectivo {fmin_ef} → {fmax_ef}")
        for d, antes, ahora in adelgazan_borde:
            print(f"        {d}: se respeta la BD ({antes}) y se descarta lo del fichero ({ahora})")
        print(f"        movimientos del fichero descartados por el borde: {descartados_borde}")
    else:
        print(f"   · borde recortado: no (los dos extremos vienen completos)")
    print(f"   · huecos en días INTERMEDIOS:     0 (si hubiera, habría abortado)")
    print(f"   · sello del rango en informes_subidos ({verbo}): 1 fila (tipo='ledger')")

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} movimientos en ledger_movimientos "
              f"(rango efectivo {fmin_ef}→{fmax_ef} recerrado; RLS activo sin políticas; "
              f"sello del rango escrito en informes_subidos).")
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(El borrado por rango, el volcado y el sello se han probado dentro de una "
              f"transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · movimientos={len(movs)} · "
          f"rango={fmin}→{fmax} · rango_efectivo={fmin_ef}→{fmax_ef} · "
          f"borrados_rango={borradas} · insertados={insertadas} · "
          f"borde_recortado={len(adelgazan_borde)} · descartados_borde={descartados_borde} · "
          f"event_desconocidos={len(info['event_desconocidos'])} ===", flush=True)


if __name__ == '__main__':
    main()
