# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR INVENTARIO_INTERNACIONAL — 6ª pieza de la Fase 0 de la v2 (EJE PAÍS)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el informe "Inventario internacional" del Seller (.txt separado por TAB)
#   del buzón informes/internacional/ (Supabase Storage de PRODUCCIÓN, aunque el
#   ENTORNO sea staging: solo cambia DB_URL) y lo vuelca a la tabla
#   `inventario_internacional`, que es UNA FOTO del stock FBA por país.
#
#   Es "el inventario": cuánto tengo y dónde. Alimenta la PRIMERA pestaña de la
#   app v2 (la mudanza empieza por Inventario).
#
#   🔒 El PAÍS es una FILA, no un sufijo de columna: la columna `country` del
#      informe YA es una fila, así que esto nace bien (§1.2). Un país nuevo
#      (SK, CZ…) entra solo como filas, sin tocar código.
#   🔒 NO escribe identidad (ni `productos`, ni `canales_producto`): solo
#      fotografía el stock. El cruce con `productos` (por ASIN/SKU), cuando se
#      decida qué debe contestar, irá en una VISTA de solo lectura — nunca
#      escribiendo. En este PR NO hay vista (misma disciplina que paneu_aptos:
#      no se adelanta una vista antes de tener clara la pregunta).
#
# LA CLAVE es (seller_sku, country). Cada pasada deja SOLO la última foto.
#   - PK (seller_sku, country). Medido único al dígito en el fichero real:
#     0 duplicados. ⚠️ NO se usa (asin, country): hay ASIN con más de un SKU
#     (B071NJ764Q repite ASIN en un mismo país), y esa PK rompería.
#   - 🔒 ES UNA FOTO, NO UN COLLAGE (patrón común en foto_comun.py): los pares
#     (seller_sku, country) que ya no vienen en el informe se BORRAN. Borrado y
#     carga en la MISMA transacción: o todo o nada.
#
# ÁMBITO DE LA FOTO: NINGUNO (como all_listings y paneu, NO como keepa). El
#   informe trae TODOS los países de una vez, así que ES la tabla entera. Sin
#   ámbito el barrido borra lo que no viene, en toda la tabla.
#
# TRAMPAS MEDIDAS contra el fichero real (50466020654.txt, 21-jul):
#   - SIN BOM (excepción del estándar, como el ledger; §2.5 de CLAUDE.md). Se
#     lee con utf-8-sig igualmente (decodifica bien con y sin BOM), fallback
#     cp1252. NO se hereda el encoding de otra cañería: esto está medido aquí.
#   - El nombre del fichero es un ID numérico de Amazon (50466020654.txt): NO
#     trae fecha ni país. → La fecha del dato sale de la SUBIDA al buzón
#     (fecha_del_dato_por_subida), y el país sale de la columna `country`. No
#     hay Guarda de nombre como en keepa.
#
# Precedente a imitar: procesador_paneu_aptos.py y procesador_all_listings.py
# (foto SIN ámbito, fecha por subida). Misma escalera (ENTORNO staging|
# produccion, MODO ensayo|aplicar), misma disciplina de guardas.
# ============================================================================

import os, sys, io, csv
from collections import Counter

import psycopg2
from psycopg2.extras import Json
from supabase import create_client

# El patrón de carga de FOTO, común a las cañerías de la Fase 0.
from foto_comun import (Aborta, fecha_del_dato_por_subida, guarda_anti_encogimiento,
                        claves_previas, barrer_sobrantes, resumen_foto)

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

BUCKET, CARPETA = 'informes', 'internacional'

# ---------------------------------------------------------------------------
# Columnas: (encabezado EXACTO del .txt, columna Postgres, tipo).
#   tipo: 't' text · 'i' integer (>0)
# 🔒 El encabezado se compara EXACTO (sin BOM, sin espacios). Si uno no aparece
#    → Guarda 1 ABORTA. No se conjetura (regla que mató al PR #26).
# Cabecera literal del fichero real (6 columnas):
#   seller-sku · fulfillment-channel-sku · asin · condition-type · country ·
#   quantity-for-local-fulfillment
# ---------------------------------------------------------------------------
TIPADAS = [
    ('seller-sku',                      'seller_sku',     't'),
    ('fulfillment-channel-sku',         'fulfillment_sku', 't'),
    ('asin',                            'asin',           't'),
    ('condition-type',                  'condition_type', 't'),
    ('country',                         'country',        't'),
    ('quantity-for-local-fulfillment',  'quantity',       'i'),
]
CABECERA_ESPERADA = [h for h, _, _ in TIPADAS]

# Hoy el informe solo lista NewItem; otro valor NO aborta, se GRITA (Guarda 5).
CONDITION_CONOCIDA = 'NewItem'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(v):
    """Sin BOM, NBSP→espacio, sin \\r, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..5). Sin tocar la base todavía.
# ---------------------------------------------------------------------------
def analizar(texto, fichero, fecha_foto):
    lector = csv.reader(io.StringIO(texto), delimiter='\t')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 2: anti-vacío (≥1 fila de datos)
    if len(filas) < 2:
        raise Aborta("[Guarda 2] 0 filas de datos (fichero vacío o no es TAB-separated). "
                     "Abortando.")

    cabecera = [_clean(c) for c in filas[0]]
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)

    # Guarda 1: las 6 columnas EXACTAS existen (§0: no se conjetura, se ABORTA)
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
    salida = []
    vistos = {}
    duplicadas = []
    condiciones_raras = Counter()

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 cabecera, +1 para numerar desde 1

        sku  = celda(fila, 'seller-sku')
        pais = celda(fila, 'country')

        # Guarda 3: los dos campos de la PK deben venir. Una clave incompleta no
        # puede decidir qué se borra ni qué se escribe.
        if sku == '':
            raise Aborta(f"[Guarda 3] Fila {num_fila}: 'seller-sku' vacío. Abortando.")
        if pais == '':
            raise Aborta(f"[Guarda 3] Fila {num_fila} (sku {sku}): 'country' vacío. "
                         f"Sin país no hay clave (PK = seller_sku, country). Abortando.")

        # Guarda 4: quantity entero > 0. El informe SOLO lista lo que tiene stock;
        # un 0, un negativo o un no-número es un informe raro → ABORTA y lo cuenta.
        q_raw = celda(fila, 'quantity-for-local-fulfillment')
        try:
            q = int(q_raw)
        except ValueError:
            raise Aborta(f"[Guarda 4] Fila {num_fila} (sku {sku}, país {pais}): "
                         f"'quantity-for-local-fulfillment' no es un entero: {q_raw!r}. "
                         f"Abortando.")
        if q <= 0:
            raise Aborta(f"[Guarda 4] Fila {num_fila} (sku {sku}, país {pais}): quantity "
                         f"= {q} (≤ 0). El informe solo lista lo que tiene stock; un 0 o "
                         f"negativo es un informe raro. Abortando.")

        # Guarda 2 (dup): par (seller_sku, country) duplicado dentro del fichero
        k = (sku, pais)
        if k in vistos:
            duplicadas.append(f"({sku}, {pais}) — filas {vistos[k]} y {num_fila}")
        else:
            vistos[k] = num_fila

        # Guarda 5: condition-type distinto de NewItem → NO aborta, se GRITA.
        cond = celda(fila, 'condition-type')
        if cond != CONDITION_CONOCIDA:
            condiciones_raras[cond] += 1

        registro = {}
        for h, db_col, tipo in TIPADAS:
            registro[db_col] = q if tipo == 'i' else (celda(fila, h) or None)

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        salida.append({'registro': registro, 'crudo': crudo})

    # Guarda 2 (dup, informe final): el procesador NO elige entre dos filas
    if duplicadas:
        raise Aborta("[Guarda 2] Par (seller_sku, country) duplicado (la PK; el "
                     "procesador NO elige):\n   · " + "\n   · ".join(duplicadas))

    return {'filas': salida, 'fichero': fichero, 'fecha_foto': fecha_foto,
            'condiciones_raras': condiciones_raras}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas). SIN vista.
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n    ".join(
        f"{c} {'integer' if t == 'i' else 'text'}" for _, c, t in TIPADAS)
    return f"""
    CREATE TABLE IF NOT EXISTS inventario_internacional (
        {cols},
        fichero       text,
        fecha_foto    date,
        crudo         jsonb,
        procesado_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (seller_sku, country)
    );
    """


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 🔒 PRIMERA línea del log, bien visible.
    print("=== PROCESADOR INVENTARIO_INTERNACIONAL (EJE PAÍS) ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 54, flush=True)

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
        sys.exit(f"No se pudo listar {BUCKET}/{CARPETA}/ ({e}). ¿Existe la carpeta? "
                 "Créala y sube el informe 'Inventario internacional' en .txt.")
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    if not txts:
        # Sin fichero, el ensayo aborta en el primer paso. Es el orden, no un fallo.
        sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. Sube el informe "
                 "'Inventario internacional' (.txt) y relanza. (Sin fichero, el ensayo "
                 "aborta en el primer paso: es el orden, no un fallo.)")
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
    elegido = txts[0]
    fichero = elegido['name']
    print(f"Informe elegido (el más reciente de {len(txts)}): {fichero}", flush=True)

    # fecha_foto = LA FECHA DEL DATO. Este informe no trae fecha ni dentro ni en
    # el nombre (es un ID numérico de Amazon): el único sello honrado es cuándo se
    # subió esta foto al buzón. 🔴 Si no se puede leer, ABORTA (no cae a today()).
    try:
        fecha_foto = fecha_del_dato_por_subida(elegido, 'internacional').date()
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)
    print(f"   · fecha_foto={fecha_foto} (fecha de subida al buzón = fecha del dato)",
          flush=True)

    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")
    # 🔴 SIN BOM (medido), pero utf-8-sig decodifica bien igual. Fallback cp1252.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales 1..5 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero, fecha_foto)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    filas = info['filas']

    # --- Lo que GRITA (Guarda 5): en el log Y en el dato (queda en condition_type) ---
    if info['condiciones_raras']:
        print("\n⚠️  [Guarda 5] condition-type FUERA de 'NewItem' (se guarda tal cual en "
              "condition_type y se GRITA; NO aborta):", flush=True)
        for val, n in info['condiciones_raras'].most_common():
            print(f"        · {val!r} en {n} fila(s)", flush=True)

    # Desglose por país del fichero (se verifica por SQL después)
    por_pais = Counter(f['registro']['country'] for f in filas)
    stock_pais = Counter()
    for f in filas:
        stock_pais[f['registro']['country']] += f['registro']['quantity']
    print(f"\nFilas leídas y cuadradas: {len(filas)} · fecha_foto {info['fecha_foto']}",
          flush=True)
    print("   País    filas   stock")
    for p in sorted(por_pais):
        print(f"   {p:4}  {por_pais[p]:6}  {stock_pais[p]:6}")
    print(f"   {'TOT':4}  {len(filas):6}  {sum(stock_pais.values()):6}")

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # 🔒 ÁMBITO DE LA FOTO: ninguno. El informe trae todos los países de una vez.
    AMBITO = None

    # Guarda 3 (foto_comun): anti-encogimiento. Corre ANTES de borrar y de escribir.
    try:
        previas = guarda_anti_encogimiento(cur, 'inventario_internacional', len(filas),
                                           ambito=AMBITO, etiqueta='anti-encogimiento')
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # Claves que ya estaban (solo para contar altas). Antes del barrido.
    prev = claves_previas(cur, 'inventario_internacional', ['seller_sku', 'country'],
                          ambito=AMBITO)

    # --- Crear tabla (nace CERRADA) e índices ---
    cur.execute(sql_crear_tabla())
    cur.execute("CREATE INDEX IF NOT EXISTS idx_inventario_internacional_asin "
                "ON inventario_internacional(asin);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_inventario_internacional_country "
                "ON inventario_internacional(country);")
    cur.execute("ALTER TABLE inventario_internacional ENABLE ROW LEVEL SECURITY;")

    # 🔒 LA FOTO TIRA LA HOJA VIEJA: los (seller_sku, country) que ya no vienen en
    # el informe se BORRAN. Mismo commit que la carga: o todo o nada. Las claves
    # son EXACTAMENTE los valores que el upsert va a escribir.
    claves_nuevas = [(f['registro']['seller_sku'], f['registro']['country']) for f in filas]
    try:
        borradas = barrer_sobrantes(cur, 'inventario_internacional',
                                    ['seller_sku', 'country'], claves_nuevas, ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Volcar ---
    cols = [c for _, c, _ in TIPADAS] + ['fichero', 'fecha_foto', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols
                    if c not in ('seller_sku', 'country'))
    sql_upsert = (f"INSERT INTO inventario_internacional ({', '.join(cols)}) VALUES ({ph}) "
                  f"ON CONFLICT (seller_sku, country) DO UPDATE SET {upd}, procesado_at=now();")
    for f in filas:
        r = f['registro']
        vals = [r[c] for _, c, _ in TIPADAS] + [fichero, info['fecha_foto'], Json(f['crudo'])]
        cur.execute(sql_upsert, vals)

    altas = sum(1 for f in filas
                if (f['registro']['seller_sku'], f['registro']['country']) not in prev)

    # --- Resumen (se imprime siempre) ---
    print(resumen_foto('inventario_internacional', AMBITO, previas, len(filas),
                       altas, borradas, MODO), flush=True)

    # --- Escritura (o no) ---
    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {len(filas)} filas en inventario_internacional "
              f"(tabla lista, RLS activo sin políticas).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(La tabla y el volcado se han probado dentro de una transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · filas={len(filas)} · "
          f"altas={altas} · bajas={borradas} · paises={len(por_pais)} · "
          f"condiciones_raras={len(info['condiciones_raras'])} ===", flush=True)


if __name__ == '__main__':
    main()
