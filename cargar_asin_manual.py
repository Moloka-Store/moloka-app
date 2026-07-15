# -*- coding: utf-8 -*-
# ============================================================================
# CARGA MANUAL DE ASIN — one-off (25 ASIN + 3 nombres)
# ----------------------------------------------------------------------------
# Qué hace:
#   Fernando sacó a mano del Seller los ASIN de 25 fichas que no lo tenían.
#   Esto rellena `productos.asin` de esas 25 fichas y, de paso, corrige 3
#   nombres que nacieron como el literal 'Sin descripcion' (bug del alta
#   desde factura). Es una carga ÚNICA, no un proceso recurrente.
#
# Patrón (idéntico al de procesador_all_listings.py, ya validado en main):
#   DESTINO = staging | produccion   → a qué base de datos se escribe
#   MODO    = ensayo  | aplicar      → ensayo hace TODAS las comprobaciones
#                                      contra la base real pero NO escribe.
#   Conexión por DB_URL (secret STAGING_DB_URL o SUPABASE_DB_URL según destino).
#
# Regla de Fernando: no hay cabos sueltos. El script no elige, no adivina y
# no tira p'alante. Ante CUALQUIER anomalía aborta SIN escribir nada y la
# imprime con EAN, ASIN y motivo. Todas las guardas van ANTES de escribir.
#
# Escritura: UNA sola transacción. O entran los 25 (y los 3 nombres) o no
# entra ninguno. Solo se toca `asin` y (cuando toca) `nombre`. Nada más.
# ============================================================================

import os, re, sys

import psycopg2

# ---------------------------------------------------------------------------
# 0) Configuración
# ---------------------------------------------------------------------------
DB_URL  = os.environ['DB_URL']                                    # postgres del DESTINO
MODO    = os.environ.get('MODO', 'ensayo').strip().lower()        # ensayo | aplicar
DESTINO = os.environ.get('DESTINO', 'staging').strip().lower()    # staging | produccion

print("=== CARGA MANUAL DE ASIN (25 ASIN + 3 nombres) ===", flush=True)
print(f"MODO: {MODO}", flush=True)
print(f"DESTINO: {DESTINO}", flush=True)
if MODO not in ('ensayo', 'aplicar'):
    sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
if DESTINO not in ('staging', 'produccion'):
    sys.exit(f"DESTINO desconocido: {DESTINO!r} (usa 'staging' o 'produccion')")

# ---------------------------------------------------------------------------
# 1) LOS DATOS (embebidos: no se lee ningún fichero)
# ---------------------------------------------------------------------------
# 1.1 · Los 25 pares EAN → ASIN
PARES = [
    ("4260250073834", "B00K4926L8"),
    ("4260250071663", "B009VEI0M6"),
    ("194735263776",  "B0DNFX5JD9"),
    ("889698863094",  "B0DZXT1QFY"),
    ("889698816786",  "B0CND4M7NT"),
    ("889698797368",  "B0D19CWXM1"),
    ("5050293385723", "B01HY4SMNQ"),
    ("5050293387871", "B0799NY528"),
    ("5050293391618", "B08LN4W6GQ"),
    ("5050293387086", "B0F9PYJPZ9"),
    ("889698783040",  "B0CJFRGH28"),
    ("889698933940",  "B08HH911B7"),
    ("889698927222",  "B0FGXTY1VF"),
    ("889698902885",  "B0F9YTDWWL"),
    ("889698864121",  "B0DP7C6MGS"),
    ("889698801935",  "B0CSVRQ8JN"),
    ("889698838092",  "B0D98TLR7Q"),
    ("889698676083",  "B0B6GFXCWG"),
    ("889698507684",  "B09S8YRLQP"),
    ("889698422390",  "B07P82MKGQ"),
    ("889698568081",  "B08T6LQ51N"),
    ("889698372480",  "B07KPT4L3N"),
    ("889698801423",  "B0CS6QBYHH"),
    ("889698679275",  "B0BNJZRQVP"),
    ("889698870023",  "B0DNRSQXGR"),
]

# 1.2 · Los 3 nombres a corregir. Solo se aplica si el nombre actual sigue
#       siendo EXACTAMENTE el literal 'Sin descripcion' (bug del alta).
NOMBRE_BUG = "Sin descripcion"
NOMBRES = {
    "4260250073834": "Ultimate Guard UGD020019 - Fundas para cómic",
    "4260250071663": "Ultimate Guard - Protector de Libros de Cloruro",
    "194735263776":  "Hot Wheels Premium Formula 1, Oracle Red Bull",
}

ASIN_RE   = re.compile(r'^B0[A-Z0-9]{8}$')   # misma validación que editarASIN() en la app
ESPERADAS = 25                               # anti-desastre (§4.7)

# `abortos` recoge TODAS las anomalías (ean, asin, motivo). Si al final tiene
# algo, el script aborta sin escribir. Recogemos todas para verlas de una vez.
abortos = []
def aborta(ean, asin, motivo):
    abortos.append((ean, asin, motivo))

def vacio(v):
    return v is None or str(v).strip() == ''

def norm_ean(v):
    # Clave canónica de EAN, igual que hace la app (String(ean).replace(/^0+/,'')).
    return str(v or '').strip().lstrip('0')

def norm_asin(v):
    return str(v or '').strip().upper()

# ---------------------------------------------------------------------------
# 2) GUARDAS que no necesitan la base (§4.1 y §4.2)
# ---------------------------------------------------------------------------
# 2.1 · Formato del ASIN
for ean, asin in PARES:
    if not ASIN_RE.match(asin):
        aborta(ean, asin, "formato de ASIN inválido (debe casar ^B0[A-Z0-9]{8}$)")

# 2.2 · Sin repetidos en la propia lista (ni EAN ni ASIN)
vistos_ean, vistos_asin = {}, {}
for ean, asin in PARES:
    if ean in vistos_ean:
        aborta(ean, asin, "EAN repetido dentro de la lista de 25")
    vistos_ean[ean] = True
    au = norm_asin(asin)
    if au in vistos_asin:
        aborta(vistos_asin[au], asin, f"ASIN repetido dentro de la lista de 25 (también en EAN {ean})")
    vistos_asin[au] = ean

# ---------------------------------------------------------------------------
# 3) Conectar y cargar productos (una sola lectura, todo en Python)
# ---------------------------------------------------------------------------
con = psycopg2.connect(DB_URL)
con.autocommit = False
cur = con.cursor()

cur.execute("SELECT id, ean, asin, es_chase, activo, nombre FROM productos;")
productos = cur.fetchall()
print(f"\nFichas leídas de productos: {len(productos)}", flush=True)

# Índice EAN(normalizado) → fichas ACTIVAS
activas_por_ean = {}
# Índice ASIN(normalizado) → fichas (de TODAS, activas o no) que ya lo tienen
fichas_por_asin = {}
for (pid, ean, asin, es_chase, activo, nom) in productos:
    if activo:
        activas_por_ean.setdefault(norm_ean(ean), []).append(
            (pid, ean, asin, es_chase, nom))
    if not vacio(asin):
        fichas_por_asin.setdefault(norm_asin(asin), []).append((pid, ean, nom))

# ---------------------------------------------------------------------------
# 4) GUARDAS contra la base real (§4.3 a §4.6) + plan de actualización
# ---------------------------------------------------------------------------
# plan: lista de dicts con lo que se HARÍA (ya validado).
plan = []
ids_planeados = set()

for ean, asin in PARES:
    asin_u = norm_asin(asin)

    # §4.3 · Cada EAN casa con EXACTAMENTE UNA ficha activa
    candidatas = activas_por_ean.get(norm_ean(ean), [])
    if len(candidatas) == 0:
        aborta(ean, asin, "el EAN no casa con ninguna ficha activa (0)")
        continue
    if len(candidatas) > 1:
        ids = ", ".join(str(c[0]) for c in candidatas)
        aborta(ean, asin, f"el EAN casa con {len(candidatas)} fichas activas "
                          f"(pack/chase) — no se elige. ids: {ids}")
        continue

    (pid, ean_bd, asin_bd, es_chase, nom) = candidatas[0]

    # Blindaje: dos EAN de la lista no pueden resolver a la misma ficha
    if pid in ids_planeados:
        aborta(ean, asin, f"la ficha id {pid} ya iba a actualizarse por otro EAN de la lista")
        continue

    # §4.4 · La ficha NO puede tener ya un ASIN (jamás se pisa)
    if not vacio(asin_bd):
        aborta(ean, asin, f"la ficha id {pid} ya tiene ASIN '{asin_bd}' (no se pisa)")
        continue

    # §4.5 · La ficha no puede ser chase
    if es_chase:
        aborta(ean, asin, f"la ficha id {pid} es_chase=true (en Amazon no se venden chase)")
        continue

    # §4.6 · El ASIN no puede estar ya en otra ficha (ASIN→EAN es 1:1)
    duenas = [f for f in fichas_por_asin.get(asin_u, []) if f[0] != pid]
    if duenas:
        d = duenas[0]
        aborta(ean, asin, f"el ASIN ya está en otra ficha: id {d[0]} "
                          f"(EAN {d[1]}, '{str(d[2] or '')[:40]}')")
        continue

    # Nombre a corregir (§3.2): solo si el actual es EXACTAMENTE 'Sin descripcion'
    nombre_nuevo = None
    if ean in NOMBRES and str(nom) == NOMBRE_BUG:
        nombre_nuevo = NOMBRES[ean]

    ids_planeados.add(pid)
    plan.append({
        'id': pid, 'ean': ean, 'asin': asin_u,
        'nombre_actual': nom, 'nombre_nuevo': nombre_nuevo,
    })

# §4.7 · Anti-desastre: las fichas a actualizar deben ser EXACTAMENTE 25
if not abortos and len(plan) != ESPERADAS:
    aborta("—", "—", f"las fichas a actualizar no son {ESPERADAS} sino {len(plan)}")

# ---------------------------------------------------------------------------
# 5) ¿Alguna guarda saltó? → abortar SIN escribir nada
# ---------------------------------------------------------------------------
if abortos:
    print(f"\n❌ ABORTA: {len(abortos)} anomalía(s). No se escribe NADA.\n", flush=True)
    print(f"   {'EAN':<15} {'ASIN':<12} MOTIVO")
    print(f"   {'-'*13:<15} {'-'*10:<12} {'-'*6}")
    for (ean, asin, motivo) in abortos:
        print(f"   {ean:<15} {asin:<12} {motivo}")
    con.rollback()
    cur.close(); con.close()
    sys.exit(1)

# ---------------------------------------------------------------------------
# 6) Tabla de lo que se haría (se imprime siempre, en ensayo y en aplicar)
# ---------------------------------------------------------------------------
n_nombres = sum(1 for p in plan if p['nombre_nuevo'])
print(f"\nTodas las guardas OK. {len(plan)} fichas a rellenar, "
      f"{n_nombres} nombre(s) a corregir.\n", flush=True)
print(f"   {'EAN':<15} {'ASIN':<12} {'¿NOMBRE?':<9} NOMBRE ACTUAL")
print(f"   {'-'*13:<15} {'-'*10:<12} {'-'*8:<9} {'-'*13}")
for p in plan:
    marca = 'sí' if p['nombre_nuevo'] else '—'
    print(f"   {p['ean']:<15} {p['asin']:<12} {marca:<9} {str(p['nombre_actual'] or '')[:50]}")

# ---------------------------------------------------------------------------
# 7) Escritura (solo en 'aplicar'): UNA transacción, todos o ninguno
# ---------------------------------------------------------------------------
def recuento_pendientes():
    cur.execute("SELECT count(*) FROM productos "
                "WHERE activo AND (asin IS NULL OR btrim(asin)='');")
    return cur.fetchone()[0]

if MODO == 'aplicar':
    n_asin, n_nom = 0, 0
    for p in plan:
        if p['nombre_nuevo']:
            # Nombre en el mismo UPDATE cuando toca (§5). El asin siempre se
            # pone; la guarda asin-null protege de una escritura concurrente.
            cur.execute(
                "UPDATE productos SET asin=%s, nombre=%s, updated_at=now() "
                "WHERE id=%s AND (asin IS NULL OR btrim(asin)='');",
                (p['asin'], p['nombre_nuevo'], p['id']))
            if cur.rowcount == 1:
                n_nom += 1
        else:
            cur.execute(
                "UPDATE productos SET asin=%s, updated_at=now() "
                "WHERE id=%s AND (asin IS NULL OR btrim(asin)='');",
                (p['asin'], p['id']))
        n_asin += cur.rowcount

    # Blindaje final: si no cuadran 25 filas, algo cambió bajo los pies → rollback
    if n_asin != ESPERADAS:
        con.rollback()
        cur.close(); con.close()
        sys.exit(f"❌ ABORTA: se esperaban {ESPERADAS} filas con ASIN nuevo pero "
                 f"el UPDATE tocó {n_asin} (¿escritura concurrente?). Nada aplicado.")

    con.commit()
    pendientes = recuento_pendientes()
    print(f"\n✅ APLICADO en {DESTINO}:")
    print(f"   · {n_asin} fichas con ASIN nuevo")
    print(f"   · {n_nom} nombre(s) corregido(s)")
    print(f"   · pendientes ahora (activo sin ASIN): {pendientes}  (debía bajar a 7)")
else:
    con.rollback()   # ensayo: no se escribe nada
    pendientes = recuento_pendientes()
    print(f"\n🔎 ENSAYO (no se ha tocado productos).")
    print(f"   · se rellenarían {len(plan)} ASIN y {n_nombres} nombre(s)")
    print(f"   · pendientes ahora (activo sin ASIN): {pendientes}  (tras aplicar quedarían 7)")

cur.close(); con.close()
print(f"\n=== FIN · destino={DESTINO} · modo={MODO} ===", flush=True)
