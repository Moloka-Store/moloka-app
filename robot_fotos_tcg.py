# robot_fotos_tcg.py - Enriquecimiento de imagenes Keepa para la linea TCG.
#
# Lee el ranking YA calculado (ranking_tcg.xlsx), coge SOLO los productos dentro
# del corte de rank (los que vamos a publicar) y pide a Keepa POR ASIN su imagen
# en alta resolucion (1600px) + nombre. Asi gastamos ~1 token por producto del
# corte, no por todo el catalogo. NO re-rankea nada: reutiliza el rank guardado.
#
# Salida: ranking_tcg_fotos.xlsx (solo el corte, con Nombre Keepa / Img figura /
# Img caja). El Paso 2 (robot_lote) lo consume para montar el M7.

import os, io, json, sys, re, time
import keepa
from supabase import create_client
import openpyxl

sys.stdout.reconfigure(line_buffering=True)

BUCKET    = 'informes'
CARPETA   = 'web_rank'
RANK_PATH = f'{CARPETA}/ranking_tcg.xlsx'
OUT_PATH  = f'{CARPETA}/ranking_tcg_fotos.xlsx'
RECADO    = f'{CARPETA}/_solicitud.json'

CORTE = 30000   # rank maximo para entrar a la web ("los 580"); editable por recado

api = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print(">>> Tokens Keepa AHORA:", api.tokens_left, flush=True)

# Corte desde el recado, si existe
try:
    crudo = sb.storage.from_(BUCKET).download(RECADO)
    CORTE = int(json.loads(crudo.decode('utf-8')).get('rank_maximo') or CORTE)
except Exception:
    pass
print(f">>> CORTE de rank (los que enriquecemos): <= {CORTE}")

# ---- Imagen Keepa en alta resolucion (copiado verbatim de la fabrica) ----
def _nombre_el(el):
    if isinstance(el, dict):
        for k in ('l','large','hiRes','m','medium','image','name'):
            if el.get(k): return str(el[k])
    elif isinstance(el, str): return el
    return None
def _a_url(n):
    n=str(n); return n if n.startswith('http') else 'https://m.media-amazon.com/images/I/'+n
def _alta(url, px=1600):
    if not url or '/images/I/' not in url: return url
    base,_,fich=url.rpartition('/'); m=re.match(r'^([^.]+)\.',fich)
    return f"{base}/{m.group(1)}._SL{px}_.jpg" if m else url
def extraer_imagenes(prod, max_fotos=8):
    urls=[]
    for el in (prod.get('images') or []):
        n=_nombre_el(el)
        if n:
            u=_alta(_a_url(n))
            if u and u not in urls: urls.append(u)
    return urls[:max_fotos]

# ---- Keepa con reintentos ----
KEEPA_MAX_INTENTOS = 4
KEEPA_ESPERAS = [5, 15, 40, 90]
def keepa_query(items, **kwargs):
    kwargs.setdefault('progress_bar', False)
    for intento in range(KEEPA_MAX_INTENTOS):
        try:
            return api.query(items, **kwargs) or []
        except Exception as ex:
            msg = str(ex)[:60]
            if intento < KEEPA_MAX_INTENTOS - 1:
                print(f"  [Keepa] intento {intento+1}/{KEEPA_MAX_INTENTOS} fallo: {msg} -> reintento en {KEEPA_ESPERAS[intento]}s")
                time.sleep(KEEPA_ESPERAS[intento])
            else:
                print(f"  [Keepa] AGOTADOS {KEEPA_MAX_INTENTOS} intentos: {msg} -> se salta")
                return None

# ---- 1) Cargar ranking guardado ----
try:
    crudo = sb.storage.from_(BUCKET).download(RANK_PATH)
except Exception as e:
    print(f"!!! No encuentro {RANK_PATH} en Supabase: {e}")
    print("!!! Necesito el ranking calculado antes de sacar fotos. Corre el Paso 1 (rank) primero.")
    sys.exit(1)

wb = openpyxl.load_workbook(io.BytesIO(crudo), read_only=True, data_only=True)
ws = wb.active
filas = list(ws.iter_rows(values_only=True))
if not filas:
    print("!!! El ranking esta vacio."); sys.exit(1)
hdr = [str(c).strip() if c else '' for c in filas[0]]
idx = {h:i for i,h in enumerate(hdr)}
need = ['EAN','Nombre','Formato','Mejor rank','ASIN']
faltan = [c for c in need if c not in idx]
if faltan:
    print(f"!!! Al ranking le faltan columnas {faltan}. Columnas presentes: {hdr}")
    sys.exit(1)

iE,iN,iF,iMR,iA = idx['EAN'],idx['Nombre'],idx['Formato'],idx['Mejor rank'],idx['ASIN']
iRA = idx.get('Rank actual'); iR90 = idx.get('Rank 90d')
iPA = idx.get('PA (coste)'); iPV = idx.get('PVPR'); iPasa = idx.get('Pasa')

filas_d = filas[1:]
print(f">>> Ranking cargado: {len(filas_d)} filas")

# ---- 2) Filtrar al corte ----
def to_int(v):
    try: return int(v) if v not in (None,'') else None
    except Exception: return None

objetivo = []
for r in filas_d:
    mr = to_int(r[iMR])
    if mr is None or mr > CORTE: continue
    if not r[iA]: continue            # sin ASIN no podemos pedir foto por ASIN
    objetivo.append(r)
print(f">>> Dentro del corte <= {CORTE} y con ASIN: {len(objetivo)} productos")
if not objetivo:
    print("!!! No hay productos dentro del corte. Revisa el CORTE o el ranking."); sys.exit(1)

# ---- 3) Chequeo de saldo: NO quemar la corrida a medias ----
necesarios = len(objetivo)
if api.tokens_left < necesarios:
    print(f"!!! Tokens insuficientes: tienes {api.tokens_left}, necesitas ~{necesarios}.")
    print(f"!!! Keepa regenera 1500/h. Espera a tener >= {necesarios} y relanza.")
    print("!!! Paro AQUI para no gastar tokens en una corrida incompleta.")
    sys.exit(1)

# ---- 4) Pedir imagen+nombre a Keepa POR ASIN (1 token/producto) ----
asins = [str(r[iA]).strip() for r in objetivo]
por_asin = {}
LOTE = 100
n_lotes = (len(asins)+LOTE-1)//LOTE
for i in range(0, len(asins), LOTE):
    lote = asins[i:i+LOTE]
    prods = keepa_query(lote, product_code_is_asin=True, domain='ES', stats=90, history=0)
    if prods is None:
        print(f"  lote {i//LOTE+1}/{n_lotes}: fallo entero, se salta")
        continue
    for prod in prods:
        a = prod.get('asin')
        if not a: continue
        fotos = extraer_imagenes(prod)
        por_asin[a] = {
            'nombre_keepa': (prod.get('title') or '').strip(),
            'img_caja':   fotos[0] if fotos else '',                                  # [0]=caja
            'img_figura': fotos[1] if len(fotos) > 1 else (fotos[0] if fotos else ''),# [1]=figura
        }
    print(f"  lote {i//LOTE+1}/{n_lotes} | tokens {api.tokens_left}")

# ---- 5) Escribir ranking enriquecido (solo el corte) ----
wb2 = openpyxl.Workbook(); ws2 = wb2.active; ws2.title = 'Ranking fotos'
COLS = ['EAN','Nombre','Formato','Rank actual','Rank 90d','Mejor rank','PA (coste)','PVPR','ASIN','Pasa','Nombre Keepa','Img figura','Img caja']
ws2.append(COLS)
con_foto = 0
for r in objetivo:
    a = str(r[iA]).strip()
    k = por_asin.get(a, {})
    if k.get('img_figura'): con_foto += 1
    ws2.append([
        r[iE], r[iN], r[iF],
        r[iRA] if iRA is not None else '', r[iR90] if iR90 is not None else '', r[iMR],
        r[iPA] if iPA is not None else '', r[iPV] if iPV is not None else '', a,
        r[iPasa] if iPasa is not None else '',
        k.get('nombre_keepa',''), k.get('img_figura',''), k.get('img_caja',''),
    ])
buf = io.BytesIO(); wb2.save(buf); buf.seek(0)
sb.storage.from_(BUCKET).upload(OUT_PATH, buf.read(),
    {'content-type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','upsert':'true'})

print(f"\n>>> Escrito {OUT_PATH}")
print(f">>> {len(objetivo)} productos en el corte | {con_foto} con foto Keepa | {len(objetivo)-con_foto} sin foto (fallback TCG en Paso 2)")
print(f">>> Tokens Keepa al terminar: {api.tokens_left}")
