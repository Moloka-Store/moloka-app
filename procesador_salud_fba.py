# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR SALUD_FBA — Pieza 2 de la Fase 0 de la v2
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el informe SALUD_FBA (MANAGE_INVENTORY_HEALTH) del buzón
#   informes/salud_fba/ (Supabase Storage de PRODUCCIÓN) y lo vuelca a la
#   tabla `salud_fba`, que es una FOTO de Amazon (no un trozo del inventario
#   de Moloka).
#
#   - Guarda lo que Amazon declara, TAL CUAL llega.
#   - NO escribe en `productos`. NO escribe en ninguna tabla de la v1.
#     Cero UPDATE fuera de `salud_fba`.
#   - El cruce con las fichas de Moloka vive en la VISTA de solo lectura
#     v_salud_fba_cruce (§5). La conciliación es otro asiento, no este.
#
# LA CLAVE es (asin, marketplace), NO el SKU (ese fue el error de la v1).
#   - PK (asin, marketplace). Cada pasada hace UPSERT: solo la última foto.
#   - Idempotente: correr dos veces el mismo fichero deja el mismo resultado.
#
# Precedente a imitar: procesador_all_listings.py (ya en producción).
# Mismo estilo, misma escalera (ENTORNO staging|produccion, MODO ensayo|aplicar),
# misma disciplina de guardas.
#
# Principio de la despensa (Diseño §3.5): si el informe entra, TODAS sus
# columnas quedan disponibles. Las que tienen comensal se tipan; la fila
# entera (92 columnas) se guarda además en `crudo jsonb`. Nada se tira.
# ============================================================================

import os, sys, io, csv, json
from datetime import date

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

BUCKET, CARPETA = 'informes', 'salud_fba'

# ---------------------------------------------------------------------------
# Columnas OBLIGATORIAS: si falta el encabezado de alguna → ABORTA (Guarda 1).
# (Amazon renombra columnas: mejor parar que adivinar.) Nombre humano tal cual
# aparece en el informe; la comprobación es tolerante a mayúsculas/espacios.
# ---------------------------------------------------------------------------
OBLIGATORIAS = [
    'snapshot-date', 'sku', 'fnsku', 'asin', 'marketplace',
    'available', 'fc-transfer', 'Total Reserved Quantity',
    'inbound-quantity', 'Inventory Supply at FBA',
]

# Columnas necesarias para las ecuaciones de cuadre (Guardas 4 y 5) que no
# están en la lista obligatoria. Si faltan, tampoco se puede comprobar → ABORTA.
SOPORTE_ECUACIONES = [
    'Reserved FC Processing', 'Reserved Customer Order', 'Reserved Staging',
    'inbound-working', 'inbound-shipped', 'inbound-received',
]

# ---------------------------------------------------------------------------
# Columnas TIPADAS (las que ya tienen comensal). (db_col, tipo).
#   tipo: 't' text · 'i' integer · 'n' numeric.
# El encabezado de origen se localiza normalizando: db_col con '_'→'-' casa
# con 'Total Reserved Quantity', 'fc-transfer', 'Inventory Supply at FBA', etc.
# Si algún encabezado no casa (Amazon lo renombró), la columna tipada queda
# NULL pero el valor SIGUE en `crudo`: la despensa no pierde nada.
# ---------------------------------------------------------------------------
TIPADAS = [
    # Identidad
    ('sku', 't'), ('fnsku', 't'), ('asin', 't'), ('product_name', 't'),
    ('condition', 't'), ('marketplace', 't'),
    # Stock → maestro
    ('available', 'i'), ('fc_transfer', 'i'), ('total_reserved_quantity', 'i'),
    ('reserved_fc_processing', 'i'), ('reserved_customer_order', 'i'),
    ('reserved_staging', 'i'), ('inbound_quantity', 'i'), ('inbound_working', 'i'),
    ('inbound_shipped', 'i'), ('inbound_received', 'i'), ('unfulfillable_quantity', 'i'),
    ('pending_removal_quantity', 'i'), ('inventory_supply_at_fba', 'i'),
    # Cobertura → alertas
    ('days_of_supply', 'n'), ('total_days_of_supply_incl_open_shipments', 'n'),
    ('weeks_of_cover_t30', 'n'), ('weeks_of_cover_t90', 'n'), ('sell_through', 'n'),
    ('units_shipped_t7', 'i'), ('units_shipped_t30', 'i'), ('units_shipped_t60', 'i'),
    ('units_shipped_t90', 'i'), ('historical_days_of_supply', 'n'),
    # Reposición (2ª opinión de Amazon) → capa 5
    ('recommended_action', 't'), ('recommended_ship_in_quantity', 'i'),
    ('recommended_ship_in_date', 't'), ('healthy_inventory_level', 'n'), ('alert', 't'),
    # Exceso → capa 4
    ('estimated_excess_quantity', 'i'), ('recommended_removal_quantity', 'i'),
    ('estimated_cost_savings_of_recommended_actions', 'n'),
    # LIL → alertas
    ('fba_minimum_inventory_level', 'i'), ('fba_inventory_level_health_status', 't'),
    ('low_inventory_fee_applied_current_week', 't'), ('exempted_from_low_inventory_fee', 't'),
    # Coste / antigüedad → costes
    ('estimated_storage_cost_next_month', 'n'), ('storage_type', 't'),
    ('storage_volume', 'n'), ('item_volume', 'n'), ('inventory_age_snapshot_date', 't'),
    # Competencia → la consume el trackeador desde SU proyecto
    ('featuredoffer_price', 'n'), ('lowest_price_new_plus_shipping', 'n'),
    ('your_price', 'n'), ('sales_price', 'n'), ('sales_rank', 'i'),
    # Estacionalidad → capa 3
    ('is_seasonal_in_next_3_months', 't'), ('season_name', 't'),
    ('season_start_date', 't'), ('season_end_date', 't'),
]
TIPO_SQL = {'t': 'text', 'i': 'integer', 'n': 'numeric'}


class Aborta(Exception):
    """Cualquier guarda 1-8 lanza esto: se imprime, NO se escribe nada y el
    workflow sale en rojo."""
    pass


# ---------------------------------------------------------------------------
# Helpers de normalización y parseo
# ---------------------------------------------------------------------------
def norm(s):
    """Clave canónica de encabezado: sin BOM, minúsculas, espacios/guion_bajo → '-'."""
    return (s or '').replace('﻿', '').strip().lower().replace(' ', '-').replace('_', '-')

def clave(db_col):
    return db_col.replace('_', '-')

def txt(v):
    v = ('' if v is None else str(v)).strip()
    return v or None

def ent(v):
    v = ('' if v is None else str(v)).strip()
    if v == '':
        return None
    try:
        return int(round(float(v)))
    except ValueError:
        return None   # el crudo conserva el valor original; la despensa no pierde

def dec(v):
    v = ('' if v is None else str(v)).strip()
    if v == '':
        return None
    try:
        return float(v)
    except ValueError:
        return None

def parse_val(tipo, raw):
    return txt(raw) if tipo == 't' else ent(raw) if tipo == 'i' else dec(raw)


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..8). Sin tocar la base todavía.
#    Devuelve la lista de filas ya tipadas + su `crudo`, o lanza Aborta.
# ---------------------------------------------------------------------------
def analizar(texto, fichero):
    lector = csv.reader(io.StringIO(texto), delimiter='\t')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 8: anti-vacío
    if len(filas) < 2:
        raise Aborta("[Guarda 8] 0 filas de datos (fichero vacío o no es TSV). Abortando.")

    cabecera = [(c or '').strip() for c in filas[0]]
    cab_norm = [norm(c) for c in cabecera]
    idx_por_norm = {}
    for i, cn in enumerate(cab_norm):
        idx_por_norm.setdefault(cn, i)   # primera aparición

    # Guarda 1: columnas obligatorias presentes
    faltan = [c for c in OBLIGATORIAS if norm(c) not in idx_por_norm]
    if faltan:
        raise Aborta("[Guarda 1] Faltan columnas obligatorias en el informe: "
                     + ", ".join(faltan) + f". Cabecera vista: {cabecera[:12]}...")

    # Soporte de ecuaciones presente (habilita Guardas 4 y 5)
    faltan_eq = [c for c in SOPORTE_ECUACIONES if norm(c) not in idx_por_norm]
    if faltan_eq:
        raise Aborta("[Guarda 1] Faltan columnas necesarias para las comprobaciones "
                     "de cuadre (§4.4/§4.5): " + ", ".join(faltan_eq) + ".")

    def celda_norm(fila, cn):
        i = idx_por_norm.get(cn)
        if i is None or i >= len(fila):
            return ''
        return (fila[i] or '').strip()

    def eq_int(fila, db_col, num_fila, humano):
        raw = celda_norm(fila, clave(db_col))
        if raw == '':
            raise Aborta(f"[Guarda 4/5/6] Fila {num_fila}: '{humano}' vacía; no se puede cuadrar.")
        try:
            return int(round(float(raw)))
        except ValueError:
            raise Aborta(f"[Guarda 4/5/6] Fila {num_fila}: valor no numérico en '{humano}' ({raw!r}).")

    filas_datos = filas[1:]
    snapshots = set()
    claves_vistas = {}
    duplicadas = []
    salida = []

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 por cabecera, +1 para numerar desde 1

        asin_v = celda_norm(fila, 'asin')
        sku_v  = celda_norm(fila, 'sku')
        mk_v   = celda_norm(fila, 'marketplace')

        # Guarda 3: asin o sku vacío
        if asin_v == '' or sku_v == '':
            cual = 'asin' if asin_v == '' else 'sku'
            raise Aborta(f"[Guarda 3] Fila {num_fila}: '{cual}' vacío. Abortando.")

        snapshots.add(celda_norm(fila, 'snapshot-date'))

        # Guarda 2: par (asin, marketplace) duplicado (se recopilan todos)
        k = (asin_v.upper(), mk_v.upper())
        if k in claves_vistas:
            duplicadas.append(f"({asin_v}, {mk_v}) — filas {claves_vistas[k]} y {num_fila}")
        else:
            claves_vistas[k] = num_fila

        # Guardas 4, 5, 6: ecuaciones internas (verificadas fila a fila)
        trq = eq_int(fila, 'total_reserved_quantity', num_fila, 'Total Reserved Quantity')
        rfp = eq_int(fila, 'reserved_fc_processing', num_fila, 'Reserved FC Processing')
        rco = eq_int(fila, 'reserved_customer_order', num_fila, 'Reserved Customer Order')
        rst = eq_int(fila, 'reserved_staging', num_fila, 'Reserved Staging')
        if trq != rfp + rco + rst:
            raise Aborta(f"[Guarda 4] Fila {num_fila} (asin {asin_v}): Total Reserved "
                         f"Quantity ({trq}) ≠ FC Processing+Customer Order+Staging "
                         f"({rfp}+{rco}+{rst}={rfp+rco+rst}).")

        iq = eq_int(fila, 'inbound_quantity', num_fila, 'inbound-quantity')
        iw = eq_int(fila, 'inbound_working', num_fila, 'inbound-working')
        ish = eq_int(fila, 'inbound_shipped', num_fila, 'inbound-shipped')
        ir = eq_int(fila, 'inbound_received', num_fila, 'inbound-received')
        if iq != iw + ish + ir:
            raise Aborta(f"[Guarda 5] Fila {num_fila} (asin {asin_v}): inbound-quantity "
                         f"({iq}) ≠ working+shipped+received ({iw}+{ish}+{ir}={iw+ish+ir}).")

        av = eq_int(fila, 'available', num_fila, 'available')
        fct = eq_int(fila, 'fc_transfer', num_fila, 'fc-transfer')
        isf = eq_int(fila, 'inventory_supply_at_fba', num_fila, 'Inventory Supply at FBA')
        # ⚠️ NO incluye el reservado (comprobado fila a fila). No "corregir".
        if isf != av + fct + iq:
            raise Aborta(f"[Guarda 6] Fila {num_fila} (asin {asin_v}): Inventory Supply "
                         f"at FBA ({isf}) ≠ available+fc-transfer+inbound-quantity "
                         f"({av}+{fct}+{iq}={av+fct+iq}).")

        # Fila tipada + crudo (fila entera, encabezados originales)
        registro = {}
        for db_col, tipo in TIPADAS:
            registro[db_col] = parse_val(tipo, celda_norm(fila, clave(db_col)))
        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = (fila[i].strip() if i < len(fila) and fila[i] is not None else '')

        salida.append({
            'asin': asin_v, 'marketplace': mk_v, 'sku': sku_v,
            'registro': registro, 'crudo': crudo,
        })

    # Guarda 2 (informe final si hubo duplicados)
    if duplicadas:
        raise Aborta("[Guarda 2] Pares (asin, marketplace) duplicados (el procesador "
                     "NO elige):\n   · " + "\n   · ".join(duplicadas))

    # Guarda 7: más de una snapshot-date distinta
    snapshots = {s for s in snapshots if s}
    if len(snapshots) > 1:
        raise Aborta(f"[Guarda 7] Más de una snapshot-date en el fichero: {sorted(snapshots)}.")
    if not snapshots:
        raise Aborta("[Guarda 7] Ninguna snapshot-date en las filas. Abortando.")

    snap_txt = next(iter(snapshots))
    try:
        snap = date.fromisoformat(snap_txt)
    except ValueError:
        raise Aborta(f"[Guarda 7] snapshot-date no es una fecha ISO válida: {snap_txt!r}.")

    return {'filas': salida, 'snapshot': snap, 'fichero': fichero}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas) y la vista de cruce
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n    ".join(f"{c} {TIPO_SQL[t]}" for c, t in TIPADAS)
    return f"""
    CREATE TABLE IF NOT EXISTS salud_fba (
        {cols},
        snapshot_date  date,
        fichero        text,
        crudo          jsonb,
        procesado_en   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asin, marketplace)
    );
    """

SQL_VISTA = """
CREATE OR REPLACE VIEW v_salud_fba_cruce
WITH (security_invoker = true) AS
SELECT
    s.asin,
    s.marketplace,
    s.sku,
    s.product_name,
    s.available,
    (SELECT count(*) FROM productos p
       WHERE p.activo AND btrim(p.asin) = btrim(s.asin)) AS fichas_activas,
    NOT EXISTS (SELECT 1 FROM productos p
       WHERE p.activo AND btrim(p.asin) = btrim(s.asin)) AS sin_ficha,
    (EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(s.asin))
     AND NOT EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(s.asin)
          AND btrim(p.sku) = btrim(s.sku))) AS sku_discrepante
FROM salud_fba s;
"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 🔒 PRIMERA línea del log, bien visible (el desplegable de Actions se queda
    # donde lo dejaste — ya mordió una vez).
    print(f"=== PROCESADOR SALUD_FBA ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 40, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = sb.storage.from_(BUCKET).list(CARPETA) or []
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    if not txts:
        sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. "
                 "Sube el informe SALUD_FBA (MANAGE_INVENTORY_HEALTH) en .txt y relanza.")
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    fichero = txts[0]['name']
    print(f"Informe elegido (el más reciente): {fichero}", flush=True)
    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")

    # Encoding: el real trae UTF-8 con BOM (utf-8-sig). Fallback cp1252.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales 1..8 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    filas = info['filas']
    snap = info['snapshot']
    print(f"\nFilas leídas y cuadradas: {len(filas)} · snapshot {snap} · "
          f"marketplaces {sorted({f['marketplace'] for f in filas})}", flush=True)

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # Recuento previo (para Guarda 9). Si la tabla no existe aún → 0.
    cur.execute("SELECT to_regclass('public.salud_fba');")
    existe_tabla = cur.fetchone()[0] is not None
    if existe_tabla:
        cur.execute("SELECT count(*) FROM salud_fba;")
        previas = cur.fetchone()[0]
        cur.execute("SELECT asin, marketplace FROM salud_fba;")
        claves_previas = {(str(a).strip().upper(), str(m).strip().upper()) for a, m in cur.fetchall()}
    else:
        previas, claves_previas = 0, set()

    # Guarda 9: anti-encogimiento (< 50% de lo que ya hay → ABORTA)
    if len(filas) < previas * 0.5:
        print(f"\n❌ ABORTA [Guarda 9] anti-encogimiento: el fichero trae {len(filas)} "
              f"filas y en salud_fba ya hay {previas} (menos del 50%). No se escribe nada.",
              flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Cruce en memoria contra `productos` (para los avisos §4.2 y el premio §5) ---
    cur.execute("SELECT btrim(asin), btrim(sku) FROM productos WHERE activo AND asin IS NOT NULL;")
    asins_activos = set()
    skus_por_asin = {}
    for a, s in cur.fetchall():
        if not a:
            continue
        au = a.upper()
        asins_activos.add(au)
        if s:
            skus_por_asin.setdefault(au, set()).add(s)

    sin_ficha, sku_discrepante = [], []
    for f in filas:
        au = f['asin'].strip().upper()
        if au not in asins_activos:
            sin_ficha.append(f"{f['asin']} · sku informe {f['sku']}")
        elif f['sku'].strip() not in skus_por_asin.get(au, set()):
            sku_discrepante.append(f"{f['asin']} · BD {sorted(skus_por_asin.get(au, set()))} "
                                   f"vs informe {f['sku']}")

    altas = [f for f in filas
             if (f['asin'].strip().upper(), f['marketplace'].strip().upper()) not in claves_previas]
    actualizaciones = len(filas) - len(altas)

    # --- Crear tabla + vista y volcar (todo dentro de la transacción) ---
    cur.execute(sql_crear_tabla())
    cur.execute("CREATE INDEX IF NOT EXISTS idx_salud_fba_asin ON salud_fba(asin);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_salud_fba_sku  ON salud_fba(sku);")
    cur.execute("ALTER TABLE salud_fba ENABLE ROW LEVEL SECURITY;")   # nace CERRADA
    cur.execute(SQL_VISTA)

    cols = [c for c, _ in TIPADAS] + ['snapshot_date', 'fichero', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    set_upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ('asin', 'marketplace'))
    sql_upsert = (f"INSERT INTO salud_fba ({', '.join(cols)}) VALUES ({ph}) "
                  f"ON CONFLICT (asin, marketplace) DO UPDATE SET {set_upd}, procesado_en=now();")

    for f in filas:
        vals = [f['registro'][c] for c, _ in TIPADAS] + [snap, fichero, Json(f['crudo'])]
        cur.execute(sql_upsert, vals)

    # --- Resumen (se imprime siempre) ---
    print(f"\n--- Lo que {'se ha escrito' if MODO == 'aplicar' else 'se escribiría'} en "
          f"salud_fba ({ENTORNO}) ---")
    print(f"   · altas (par nuevo):        {len(altas)}")
    print(f"   · actualizaciones (upsert): {actualizaciones}")
    print(f"   · total filas volcadas:     {len(filas)}")

    print(f"\n--- Avisos (§4.2 · NO abortan · viven en la vista v_salud_fba_cruce) ---")
    print(f"   · ASIN sin ficha activa en productos (red del reverso): {len(sin_ficha)}")
    for s in sin_ficha[:50]:
        print(f"        · {s}")
    if len(sin_ficha) > 50:
        print(f"        … y {len(sin_ficha) - 50} más")
    print(f"   · SKU discrepante informe≠BD (el premio §5): {len(sku_discrepante)}")
    for s in sku_discrepante[:50]:
        print(f"        · {s}")

    # --- Escritura (o no) ---
    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {len(filas)} filas en salud_fba "
              f"(tabla y vista listas, RLS activo sin políticas).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(La tabla/vista y el volcado se han probado dentro de una transacción "
              f"revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · filas={len(filas)} · "
          f"altas={len(altas)} · sin_ficha={len(sin_ficha)} · "
          f"sku_discrepante={len(sku_discrepante)} ===", flush=True)


if __name__ == '__main__':
    main()
