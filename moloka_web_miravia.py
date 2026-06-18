# ==========================================================================
# MOLOKA WEB · Alimentador Miravia -> web_productos (Capa 1: rarezas propias)
# --------------------------------------------------------------------------
# Coge tus productos de Miravia (fotos + ficha) y los vuelca a la tabla
# web_productos, YA estructurados para SEO: slug de URL limpia + título
# optimizado + disponibilidad. Reutiliza la firma de Miravia ya validada.
#
# Para GitHub Actions. Lee credenciales de Secrets.
# NO inventa: si un campo no viene de Miravia, lo deja vacío y lo avisa.
# ==========================================================================
import os, sys, time, hmac, hashlib, re, unicodedata, json
import requests as _rq
from supabase import create_client

sys.stdout.reconfigure(line_buffering=True)

# ---- credenciales ----
MRV_APP_KEY      = os.environ['MIRAVIA_APP_KEY']
MRV_APP_SECRET   = os.environ['MIRAVIA_APP_SECRET']
MRV_ACCESS_TOKEN = os.environ['MIRAVIA_ACCESS_TOKEN']
MRV_GATEWAY      = 'https://api.miravia.es/rest'
SUPABASE_URL     = os.environ['SUPABASE_URL']
SUPABASE_KEY     = os.environ['SUPABASE_KEY']

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- firma Miravia (copiada del ActualizarApp, validada) ----
def _mrv_firmar(api, params):
    base = api + ''.join('%s%s' % (k, params[k]) for k in sorted(params))
    return hmac.new(MRV_APP_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()

def _mrv(api, bp=None):
    p = dict(bp or {})
    p.update({'app_key': MRV_APP_KEY, 'access_token': MRV_ACCESS_TOKEN,
              'timestamp': str(int(time.time()*1000)), 'sign_method': 'sha256'})
    p['sign'] = _mrv_firmar(api, p)
    return _rq.get(MRV_GATEWAY + api, params=p, timeout=30).json()

# ---- utilidades SEO ----
def slugify(texto):
    if not texto: return ''
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode()
    t = t.lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return re.sub(r'-{2,}', '-', t).strip('-')[:70]

def construir_titulo_seo(nombre, licencia, es_chase):
    """Título optimizado. Si el nombre ya empieza por 'Funko', no duplicar."""
    base = (nombre or '').strip()
    if not base:
        base = 'Figura Coleccionable'
    if not base.lower().startswith('funko'):
        base = 'Funko Pop! ' + base
    extra = []
    if licencia and licencia.strip() and licencia.lower() not in base.lower():
        extra.append(licencia.strip().title())
    if es_chase and 'chase' not in base.lower():
        extra.append('CHASE')
    cola = ' – '.join(extra)
    titulo = base + (f' – {cola}' if cola else '') + ' – Original, Caja Protegida'
    return titulo[:160]

def primera_imagen(imgs):
    if isinstance(imgs, list):
        for u in imgs:
            if isinstance(u, str) and u.startswith('http'):
                return u
    return None

def stock_de_sku(sku):
    """Stock disponible del SKU (Miravia trae multiWarehouseInventories)."""
    inv = sku.get('multiWarehouseInventories')
    if isinstance(inv, list) and inv:
        try: return sum(int(w.get('quantity') or 0) for w in inv)
        except: pass
    for k in ('quantity', 'SellableQuantity', 'Available'):
        v = sku.get(k)
        if v is not None:
            try: return int(v)
            except: pass
    return 0

# ---- 1) traer productos de Miravia (paginado) ----
print(">>> Descargando productos de Miravia...")
productos = []
offset = 0
_diag = True
while True:
    d = _mrv('/products/get', {'limit': '50', 'offset': str(offset)})
    if str(d.get('code')) != '0':
        print("  [products/get] respuesta:", d.get('code'), d.get('message')); break
    data = d.get('data') or {}
    lote = data.get('products', [])
    if not lote: break
    if _diag and lote:
        p0 = lote[0]
        print("  [DIAG] claves producto:", list(p0.keys()))
        print("  [DIAG] claves attributes:", list((p0.get('attributes') or {}).keys()))
        print("  [DIAG] claves sku:", list(((p0.get('skus') or [{}])[0]).keys()))
        _diag = False
    productos += lote
    offset += 50
    if offset >= (data.get('total_products') or 0): break
print(f">>> Productos recibidos de Miravia: {len(productos)}")

if not productos:
    print("!!! Miravia no devolvió productos. Revisa secrets/token. Abortando sin tocar la web.")
    sys.exit(1)

# ---- 2) mapear a filas web_productos ----
filas = []
sin_nombre = sin_imagen = 0
for p in productos:
    attrs = p.get('attributes') or {}
    sku0  = (p.get('skus') or [{}])[0]
    item_id = str(p.get('item_id') or '')

    nombre = (attrs.get('name') or attrs.get('title') or attrs.get('short_title')
              or p.get('name') or '').strip()
    descripcion = (attrs.get('description') or attrs.get('short_description') or '')
    licencia = (attrs.get('brand') or attrs.get('marca') or '').strip()
    ean = sku0.get('ean_code', '') or ''
    try: precio = float(sku0.get('price') or 0) or None
    except: precio = None
    stock = stock_de_sku(sku0)
    imgs = p.get('images') if isinstance(p.get('images'), list) else []
    es_chase = 'chase' in (nombre + ' ' + str(attrs)).lower()

    if not nombre: sin_nombre += 1
    if not imgs:   sin_imagen += 1

    slug = slugify(nombre) or 'producto'
    slug = f"{slug}-{item_id[-6:]}" if item_id else slug

    filas.append({
        'origen': 'miravia',
        'origen_id': item_id,
        'ean': ean,
        'slug': slug,
        'titulo_seo': construir_titulo_seo(nombre, licencia, es_chase),
        'nombre': nombre,
        'descripcion_html': descripcion,
        'licencia': licencia or None,
        'es_chase': es_chase,
        'precio': precio,             # precio de Miravia; la política de precio web se decide aparte
        'precio_origen': precio,
        'disponibilidad': 'inmediato' if stock > 0 else 'agotado',
        'stock': stock,
        'imagen_principal': primera_imagen(imgs),
        'imagenes': imgs,
        'activo': stock > 0,
    })

print(f">>> Filas preparadas: {len(filas)} | sin nombre: {sin_nombre} | sin imagen: {sin_imagen}")
if filas:
    ej = filas[0]
    print("  [EJEMPLO] slug:", ej['slug'])
    print("  [EJEMPLO] titulo_seo:", ej['titulo_seo'])
    print("  [EJEMPLO] precio:", ej['precio'], "| stock:", ej['stock'], "| imgs:", len(ej['imagenes']))

# ---- 3) upsert a web_productos ----
BLOQUE = 200
subidas = 0
for i in range(0, len(filas), BLOQUE):
    lote = filas[i:i+BLOQUE]
    sb.table('web_productos').upsert(lote, on_conflict='origen,origen_id').execute()
    subidas += len(lote)
    print(f"  subidas {subidas}/{len(filas)}")

print(f">>> LISTO. {subidas} productos de Miravia volcados a web_productos.")
print("=== ALIMENTADOR MIRAVIA FIN ===")
