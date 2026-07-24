# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR ALL_LISTINGS — primera pieza de la Fase 0 de la v2 ("el bicho")
# ----------------------------------------------------------------------------
# Qué hace (Diseño v2 §3.2.5):
#   1) Lee el "Informe de todos los listings" (.txt) del buzón
#      informes/all_listings/ (Supabase Storage de PRODUCCIÓN).
#   2) Vuelca el diccionario SKU↔ASIN completo a la tabla `listings_amazon`
#      (nace CERRADA: RLS activado sin políticas → solo llave de servicio).
#   3) CURA huérfanos por ASIN: rellena el SKU vacío de `productos` cuando
#      el ASIN casa de forma inequívoca. NUNCA pisa un SKU existente.
#      NUNCA toca el EAN (lo puso la factura).
#
# Modos (Diseño: primero STAGING, primero ENSAYO):
#   DESTINO = staging | produccion   → a qué base de datos se escribe
#   MODO    = ensayo  | aplicar      → ensayo NO escribe NADA: ni productos ni
#                                      listings_amazon. Solo cuenta y lista.
#   ⚠️ CAMBIO (20-jul): antes el diccionario listings_amazon se escribía
#      SIEMPRE, también en ensayo. Ya no. Desde que la carga BORRA lo que
#      sobra, un ensayo que commitea no es un ensayo: es una carga con otro
#      nombre. Ensayo = rollback, sin excepciones.
#
# Reglas a fuego respetadas:
#   - Cura por ASIN, jamás por EAN (ASIN→EAN es 1:1; EAN→ASIN no).
#   - Si un ASIN casa con varias fichas sin SKU: se prefiere la NO-chase
#     (los chase no van a FBA, decisión 13-jul). Si aun así hay varias
#     → AMBIGUO, no se toca, se lista.
#   - Un SKU no se asigna dos veces (si ya lo tiene otra ficha → CONFLICTO).
#   - Anti-vacío: si el informe trae <50 filas o le faltan columnas clave,
#     se aborta con error claro. Y anti-encogimiento: <50% de los SKU que ya
#     había → ABORTA sin tocar nada (mismo criterio que salud_fba y keepa).
#   - 🔒 La fecha del DATO sale del NOMBRE del fichero (MM-DD-YYYY al final),
#     igual que en keepa. Si el nombre no la trae, ABORTA: no se inventa ni se
#     cae a la fecha de subida (el informe de ejemplo es del 14 y se subió el
#     15: un día de desfase ya es una cifra que miente).
#   - 🔒 listings_amazon ES UNA FOTO (patrón común en foto_comun.py): los SKU
#     que ya no vienen en el informe se BORRAN. El SKU nace y muere (§1.1); uno
#     muerto que se queda en el diccionario es un fantasma que descuadra el
#     cruce. Borrado y carga en la MISMA transacción.
#   - El único DELETE es ese, y solo dentro de listings_amazon. Fuera de ahí, el
#     único UPDATE es rellenar productos.sku vacío, y solo en modo 'aplicar'.
# ============================================================================

import os, sys, io, csv, re
from datetime import date

import psycopg2
from supabase import create_client

# El patrón de carga de FOTO, común a las cuatro cañerías de la Fase 0.
from foto_comun import (Aborta, guarda_anti_encogimiento, guarda_no_retroceder,
                        claves_previas, barrer_sobrantes, resumen_foto)

# ---------------------------------------------------------------------------
# 0) Configuración
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ['SUPABASE_KEY']          # solo para LEER el Storage
DB_URL       = os.environ['DB_URL']                # postgres del DESTINO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()      # ensayo | aplicar
DESTINO      = os.environ.get('DESTINO', 'staging').strip().lower()  # etiqueta informativa

BUCKET, CARPETA = 'informes', 'all_listings'
MIN_FILAS = 50  # anti-vacío

# ---------------------------------------------------------------------------
# 🔒 EL NOMBRE DEL FICHERO ES DATO, no decoración. Misma regla que la Guarda 4
# de procesador_keepa_escaparate.py.
# Amazon nombra este informe con la fecha AL FINAL, en MM-DD-YYYY:
#     Informe+de+todos+los+listings_07-14-2026.txt
# Esa es la fecha del DATO. Ojo: NO es la de subida al buzón — el fichero de
# ejemplo es del día 14 y se subió el 15. Un día de desfase es exactamente la
# clase de mentira que hace que una cifra no se sostenga.
# El prefijo se deja libre a propósito (Amazon lo devuelve URL-codificado y
# traducido, y eso sí varía); lo que se exige EXACTO es el sufijo de fecha.
# ---------------------------------------------------------------------------
RE_FECHA_NOMBRE = re.compile(r'^.*_(\d{2})-(\d{2})-(\d{4})\.txt$', re.IGNORECASE)


def fecha_del_nombre(nombre):
    """MM-DD-YYYY del final del nombre → date. Si no casa, ABORTA.

    🔴 No inventa fecha y NO cae a la fecha de subida: si el nombre no la trae,
    no se sabe de qué día es la foto, y una foto sin fecha no da información
    incompleta, da información FALSA. Se para y se grita.
    """
    m = RE_FECHA_NOMBRE.match(nombre or '')
    if not m:
        raise Aborta(
            f"[Guarda nombre] El nombre del fichero no acaba en '_MM-DD-YYYY.txt'.\n"
            f"   Visto: {nombre!r}. De ahí sale la fecha del DATO (el informe no la\n"
            f"   trae dentro). Sin ella no se carga: renombra el fichero en el buzón\n"
            f"   respetando el nombre con que lo descarga el Seller, y relanza.")
    mes, dia, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(anio, mes, dia)
    except ValueError:
        raise Aborta(
            f"[Guarda nombre] La fecha del nombre no existe en el calendario: "
            f"mes={mes:02d} día={dia:02d} año={anio} (leído de {nombre!r} como "
            f"MM-DD-YYYY). ¿Seguro que no viene en DD-MM-YYYY?")

print(f"=== PROCESADOR ALL_LISTINGS · destino={DESTINO} · modo={MODO} ===", flush=True)
if MODO not in ('ensayo', 'aplicar'):
    sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
if DESTINO not in ('staging', 'produccion'):
    sys.exit(f"DESTINO desconocido: {DESTINO!r} (usa 'staging' o 'produccion')")

# ---------------------------------------------------------------------------
# 1) Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN)
# ---------------------------------------------------------------------------
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
objs = sb.storage.from_(BUCKET).list(CARPETA) or []
txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
if not txts:
    sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. "
             "Sube el 'Informe de todos los listings' (descargado en .txt) y relanza.")
txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)
nombre = txts[0]['name']
print(f"Informe elegido (el más reciente): {nombre}")

# fecha_informe = LA FECHA DEL DATO, jamás now(). Este informe no la trae dentro
# (a diferencia de salud_fba, que tiene 'snapshot-date'), pero SÍ en el nombre,
# igual que keepa. De ahí sale, y de ningún otro sitio.
try:
    fecha_dato = fecha_del_nombre(nombre)
except Aborta as e:
    sys.exit(f"\n❌ ABORTA (no se ha escrito nada):\n{e}")
print(f"   · fecha_informe={fecha_dato.isoformat()} (leída del NOMBRE del fichero)")

crudo = sb.storage.from_(BUCKET).download(f"{CARPETA}/{nombre}")

# Encoding tolerante: Amazon suele dar UTF-8, a veces cp1252
try:
    texto = crudo.decode('utf-8-sig')
except UnicodeDecodeError:
    texto = crudo.decode('cp1252')

# ---------------------------------------------------------------------------
# 2) Parsear (tab-separated) con cabeceras tolerantes
# ---------------------------------------------------------------------------
lector = csv.reader(io.StringIO(texto), delimiter='\t')
filas = [f for f in lector if any(c.strip() for c in f)]
if len(filas) < 2:
    sys.exit("El informe está vacío o no es tab-separated. Abortando.")

cab = [c.strip().lower() for c in filas[0]]

def col(nombre_col):
    """Índice de columna por nombre exacto; None si no está."""
    return cab.index(nombre_col) if nombre_col in cab else None

i_sku, i_asin = col('seller-sku'), col('asin1')
i_pid, i_nom  = col('product-id'), col('item-name')
i_est, i_open = col('status'), col('open-date')
i_pre, i_lid  = col('price'), col('listing-id')

if i_sku is None or i_asin is None:
    sys.exit(f"Faltan columnas clave ('seller-sku'/'asin1'). Cabecera vista: {cab[:12]}... "
             "¿Seguro que es el Informe de todos los listings en .txt?")

def celda(fila, i):
    if i is None or i >= len(fila):
        return ''
    return (fila[i] or '').strip()

ofertas = []
for f in filas[1:]:
    sku, asin = celda(f, i_sku), celda(f, i_asin).upper()
    if not sku or not asin:
        continue
    ofertas.append({
        'sku': sku, 'asin': asin,
        'product_id': celda(f, i_pid),
        'nombre': celda(f, i_nom)[:300],
        'status': celda(f, i_est),
        'open_date': celda(f, i_open),
        'price': celda(f, i_pre),
        'listing_id': celda(f, i_lid),
    })

if len(ofertas) < MIN_FILAS:
    sys.exit(f"ANTI-VACÍO: solo {len(ofertas)} ofertas con SKU+ASIN (mínimo {MIN_FILAS}). "
             "El fichero no parece completo. Abortando sin tocar nada.")

n_active = sum(1 for o in ofertas if o['status'].lower() == 'active')
print(f"Ofertas leídas: {len(ofertas)} ({n_active} Active, {len(ofertas)-n_active} otras)")

# Ojo al contar: el informe puede traer el mismo seller-sku en dos filas y la PK
# es el SKU, así que las filas que QUEDARÁN en la tabla son los SKU distintos, no
# len(ofertas). Todo lo que compare contra la tabla (la guarda anti-encogimiento,
# el recuento del resumen) usa ESTE número, que es el que se verifica por SQL.
skus_fichero = {o['sku'] for o in ofertas}
if len(skus_fichero) != len(ofertas):
    print(f"⚠️  El informe trae {len(ofertas)} filas con SKU+ASIN pero solo "
          f"{len(skus_fichero)} SKU distintos: {len(ofertas) - len(skus_fichero)} "
          f"repetido(s). La PK es el SKU, así que gana la última fila leída.")

# --- Mapa ASIN → SKU del informe (prefiriendo Active si hay varias) ---
por_asin = {}
for o in ofertas:
    por_asin.setdefault(o['asin'], []).append(o)

asin_a_sku = {}      # ASIN → sku elegido
asin_ambiguo = {}    # ASIN → lista de SKUs (no se puede elegir)
for asin, lst in por_asin.items():
    skus = sorted({o['sku'] for o in lst})
    if len(skus) == 1:
        asin_a_sku[asin] = skus[0]
        continue
    activos = sorted({o['sku'] for o in lst if o['status'].lower() == 'active'})
    if len(activos) == 1:
        asin_a_sku[asin] = activos[0]
    else:
        asin_ambiguo[asin] = skus

# ---------------------------------------------------------------------------
# 3) Conectar al DESTINO y asegurar la tabla del diccionario (nace CERRADA)
# ---------------------------------------------------------------------------
con = psycopg2.connect(DB_URL)
con.autocommit = False
cur = con.cursor()

# 🔒 ÁMBITO DE LA FOTO: ninguno. Este informe ES el diccionario entero.
AMBITO = None

# Anti-encogimiento: si el informe trae menos del 50% de los SKU que ya había
# → ABORTA sin borrar ni escribir. Va ANTES del barrido. Es el criterio de
# salud_fba y keepa; el MIN_FILAS=50 de arriba se mantiene además (tapa el caso
# "tabla vacía", donde el 50% de 0 no protege de nada).
try:
    previas = guarda_anti_encogimiento(cur, 'listings_amazon', len(skus_fichero),
                                       ambito=AMBITO, etiqueta='anti-encogimiento')
    # No-retroceder: un informe más viejo que el que ya está cargado no entra
    # (información caducada = información FALSA). PERMITIR_RETROCESO=1 la salta.
    guarda_no_retroceder(cur, 'listings_amazon', 'fecha_informe', fecha_dato, ambito=AMBITO)
except Aborta as e:
    print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
    con.rollback(); cur.close(); con.close(); sys.exit(1)

prev = claves_previas(cur, 'listings_amazon', ['seller_sku'], ambito=AMBITO)

cur.execute("""
CREATE TABLE IF NOT EXISTS listings_amazon (
    seller_sku    text PRIMARY KEY,
    asin          text NOT NULL,
    product_id    text,
    item_name     text,
    status        text,
    open_date     text,
    price         text,
    listing_id    text,
    fecha_informe timestamptz NOT NULL DEFAULT now()
);
""")
# fecha_informe pasa a ser la fecha del DATO (la del NOMBRE del fichero).
# procesado_en es el metadato de cuándo corrió el robot: ese sí es now(). Son
# dos cosas distintas y a partir de aquí no se confunden.
# 🔒 El TIPO de fecha_informe NO cambia: sigue siendo timestamptz, como está hoy
# en producción. Se le pasa un `date` y Postgres lo sube a timestamptz (00:00);
# no hay ALTER COLUMN ... TYPE por ningún lado. Y el CREATE TABLE IF NOT EXISTS
# no toca una tabla que ya existe: por eso el ADD COLUMN va aparte.
cur.execute("ALTER TABLE listings_amazon "
            "ADD COLUMN IF NOT EXISTS procesado_en timestamptz NOT NULL DEFAULT now();")
cur.execute("CREATE INDEX IF NOT EXISTS idx_listings_amazon_asin ON listings_amazon(asin);")
# Nace cerrada: RLS activo y CERO políticas → anon no puede ni leerla.
cur.execute("ALTER TABLE listings_amazon ENABLE ROW LEVEL SECURITY;")

# 🔒 LA FOTO TIRA LA HOJA VIEJA: los SKU que ya no vienen en el informe se
# BORRAN. El SKU nace y muere (regla de identidad §1.1): un SKU muerto que se
# queda en el diccionario es exactamente el fantasma que hace cuadrar mal el
# cruce. Mismo commit que la carga: o todo o nada.
try:
    borradas = barrer_sobrantes(cur, 'listings_amazon', ['seller_sku'],
                                [(s,) for s in skus_fichero], ambito=AMBITO)
except Aborta as e:
    print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
    con.rollback(); cur.close(); con.close(); sys.exit(1)

for o in ofertas:
    cur.execute("""
        INSERT INTO listings_amazon
            (seller_sku, asin, product_id, item_name, status, open_date, price, listing_id, fecha_informe)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (seller_sku) DO UPDATE SET
            asin=EXCLUDED.asin, product_id=EXCLUDED.product_id,
            item_name=EXCLUDED.item_name, status=EXCLUDED.status,
            open_date=EXCLUDED.open_date, price=EXCLUDED.price,
            listing_id=EXCLUDED.listing_id, fecha_informe=EXCLUDED.fecha_informe,
            procesado_en=now();
    """, (o['sku'], o['asin'], o['product_id'], o['nombre'],
          o['status'], o['open_date'], o['price'], o['listing_id'], fecha_dato))

altas = sum(1 for s in skus_fichero if (s,) not in prev)
print(resumen_foto('listings_amazon', AMBITO, previas, len(skus_fichero),
                   altas, borradas, MODO), flush=True)

# ---------------------------------------------------------------------------
# 4) Cargar productos y clasificar
# ---------------------------------------------------------------------------
cur.execute("SELECT id, ean, asin, sku, es_chase, activo, nombre FROM productos;")
productos = cur.fetchall()
print(f"Fichas en productos: {len(productos)}")

def vacio(v):
    return v is None or str(v).strip() == ''

# SKUs ya usados en productos (para no asignar uno dos veces)
skus_usados = {}
for (pid, ean, asin, sku, es_chase, activo, nom) in productos:
    if not vacio(sku):
        skus_usados.setdefault(str(sku).strip(), []).append(pid)

# Fichas ACTIVAS sin SKU con ASIN, agrupadas por ASIN (desempate chase).
# Solo se clasifican/curan las ACTIVAS (cifras comparables con lo medido:
# 160 sin SKU / 135 con ASIN / 25 sin ASIN a 15-jul), pero skus_usados
# vigila TODAS las fichas para no duplicar un SKU jamás.
sin_sku_por_asin = {}
for p in productos:
    (pid, ean, asin, sku, es_chase, activo, nom) = p
    if activo and vacio(sku) and not vacio(asin):
        sin_sku_por_asin.setdefault(str(asin).strip().upper(), []).append(p)

curables, ambiguos, conflictos, no_casa, sin_asin, discrepancias = [], [], [], [], [], []

for p in productos:
    (pid, ean, asin, sku, es_chase, activo, nom) = p
    if not activo:
        continue
    et = f"[{ean}] {str(nom or '')[:50]}"

    if vacio(asin):
        if vacio(sku):
            sin_asin.append(et)                      # los 25 (decisión pendiente)
        continue

    asin_n = str(asin).strip().upper()

    if not vacio(sku):
        # Ya tiene SKU: contrastar con el informe, sin tocar nada
        sku_inf = asin_a_sku.get(asin_n)
        if sku_inf and sku_inf != str(sku).strip():
            discrepancias.append(f"{et} · BD={sku} vs informe={sku_inf} (ASIN {asin_n})")
        continue

    # --- Ficha SIN SKU con ASIN ---
    if asin_n in asin_ambiguo:
        ambiguos.append(f"{et} · ASIN {asin_n} tiene varios SKUs en el informe: {asin_ambiguo[asin_n]}")
        continue
    sku_inf = asin_a_sku.get(asin_n)
    if not sku_inf:
        no_casa.append(f"{et} · ASIN {asin_n} no aparece en el informe")   # los ~57
        continue

    # Desempate chase: si varias fichas sin SKU comparten el ASIN,
    # el SKU es de la NO-chase (los chase no van a FBA)
    hermanas = sin_sku_por_asin.get(asin_n, [])
    if len(hermanas) > 1:
        normales = [h for h in hermanas if not h[4]]  # es_chase == False
        if len(normales) != 1:
            ambiguos.append(f"{et} · {len(hermanas)} fichas sin SKU comparten el ASIN {asin_n}")
            continue
        if normales[0][0] != pid:
            continue  # esta es la chase (u otra): el SKU no es suyo

    if sku_inf in skus_usados:
        conflictos.append(f"{et} · el SKU {sku_inf} ya lo tiene otra ficha (id {skus_usados[sku_inf]})")
        continue

    curables.append((pid, sku_inf, et))
    skus_usados[sku_inf] = [pid]  # reservarlo para no repetirlo en esta pasada

# ---------------------------------------------------------------------------
# 5) Aplicar (o no) y contar en cristiano
# ---------------------------------------------------------------------------
if MODO == 'aplicar':
    for (pid, sku_inf, et) in curables:
        cur.execute(
            "UPDATE productos SET sku=%s WHERE id=%s AND (sku IS NULL OR btrim(sku)='');",
            (sku_inf, pid))
    print(f"\n✅ APLICADO: {len(curables)} SKUs rellenados en productos.")
else:
    print(f"\n🔎 ENSAYO (no se ha tocado productos). Se rellenarían {len(curables)} SKUs.")

def bloque(titulo, lista, tope=80):
    print(f"\n--- {titulo}: {len(lista)} ---")
    for linea in lista[:tope]:
        print("   ·", linea)
    if len(lista) > tope:
        print(f"   … y {len(lista)-tope} más")

bloque("CURADOS (SKU rellenado)" if MODO == 'aplicar' else "CURABLES (se rellenarían)",
       [f"{et} → SKU {s}" for (_, s, et) in curables])
bloque("ASIN NO CASA con el informe (revisar a mano)", no_casa)
bloque("SIN ASIN de ninguna clase (decisión pendiente)", sin_asin)
bloque("DISCREPANCIAS SKU BD≠informe (no se toca, solo aviso)", discrepancias)
bloque("AMBIGUOS (no se toca)", ambiguos)
bloque("CONFLICTOS de SKU repetido (no se toca)", conflictos)

if MODO == 'aplicar':
    con.commit()
    print(f"\n✅ APLICADO en {DESTINO}: listings_amazon con {len(skus_fichero)} filas "
          f"(la foto del informe y nada más).")
else:
    con.rollback()   # 🔒 ensayo: no se escribe ni un byte, tampoco el diccionario
    print(f"\n🔎 ENSAYO: NO se ha escrito nada. El barrido y el volcado se han "
          f"probado dentro de una transacción revertida.")

cur.close(); con.close()
print(f"\n=== FIN · destino={DESTINO} · modo={MODO} · filas={len(skus_fichero)} · "
      f"altas={altas} · bajas={borradas} · curables={len(curables)} · "
      f"no_casa={len(no_casa)} · sin_asin={len(sin_asin)} ===")
