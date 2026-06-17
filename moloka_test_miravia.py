# ==========================================================================
# MOLOKA — PRUEBA: ¿la API de Miravia devuelve IMÁGENES y TÍTULO?
# --------------------------------------------------------------------------
# Reutiliza EXACTAMENTE la firma y la llamada del ActualizarApp (probadas).
# Pregunta a Miravia por tus productos e imprime la respuesta para ver si
# vienen las fotos. NO escribe nada en ningún lado: solo lee y muestra.
# Para GitHub Actions (lee los 3 Secrets MIRAVIA_*).
# ==========================================================================
import os, sys, time, hmac, hashlib, json
import requests as _rq

sys.stdout.reconfigure(line_buffering=True)

MRV_APP_KEY      = os.environ['MIRAVIA_APP_KEY']
MRV_APP_SECRET   = os.environ['MIRAVIA_APP_SECRET']
MRV_ACCESS_TOKEN = os.environ['MIRAVIA_ACCESS_TOKEN']
MRV_GATEWAY      = 'https://api.miravia.es/rest'

# ---- firma y llamada: COPIADAS del ActualizarApp (no se inventan) --------
def _mrv_firmar(api, params):
    base = api + ''.join('%s%s' % (k, params[k]) for k in sorted(params))
    return hmac.new(MRV_APP_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()

def _mrv(api, bp=None):
    p = dict(bp or {})
    p.update({'app_key': MRV_APP_KEY, 'access_token': MRV_ACCESS_TOKEN,
              'timestamp': str(int(time.time() * 1000)), 'sign_method': 'sha256'})
    p['sign'] = _mrv_firmar(api, p)
    return _rq.get(MRV_GATEWAY + api, params=p, timeout=30).json()

# ---- buscador recursivo de URLs de imagen --------------------------------
def buscar_imagenes(obj, ruta=''):
    """Devuelve lista de (ruta, valor) donde la clave o el valor huelen a imagen."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            sub = f"{ruta}.{k}" if ruta else str(k)
            if any(t in kl for t in ('image', 'img', 'photo', 'pic')) and isinstance(v, (str, list)):
                hits.append((sub, v))
            hits += buscar_imagenes(v, sub)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            hits += buscar_imagenes(v, f"{ruta}[{i}]")
    elif isinstance(obj, str):
        if ('http' in obj) and any(e in obj.lower() for e in ('.jpg', '.jpeg', '.png', '.webp')):
            hits.append((ruta, obj))
    return hits

print("="*70)
print("  PRUEBA API MIRAVIA — ¿devuelve imágenes y título?")
print("="*70)

# ---- 1) LISTA de productos -----------------------------------------------
print("\n>>> Llamando a /products/get (limit 3)...")
d = _mrv('/products/get', {'limit': '3', 'offset': '0'})
print("    code:", d.get('code'), "| message:", d.get('message'))

if str(d.get('code')) != '0':
    print("\n!!! Miravia no devolvió productos. Causas posibles: token caducado,")
    print("    secret mal, o permiso de la app. Revisa los 3 Secrets MIRAVIA_*.")
    sys.exit(1)

productos = (d.get('data') or {}).get('products', [])
print(f"    productos recibidos: {len(productos)}")

if not productos:
    print("    (la cuenta no devolvió productos en esta llamada)")
    sys.exit(0)

p0 = productos[0]
item_id = p0.get('item_id')
print(f"\n>>> Primer producto: item_id = {item_id}")
print(">>> CLAVES de nivel producto:", list(p0.keys()))
sku0 = (p0.get('skus') or [{}])[0]
print(">>> CLAVES de nivel SKU     :", list(sku0.keys()))

imgs_lista = buscar_imagenes(p0)
print(f"\n>>> Imágenes encontradas en /products/get: {len(imgs_lista)}")
for ruta, val in imgs_lista[:8]:
    muestra = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    print(f"    [{ruta}] -> {muestra[:120]}")

# ---- 2) DETALLE del producto (suele traer más: imágenes + título) --------
print("\n>>> Probando el endpoint de DETALLE /product/item/get (item_id)...")
det = _mrv('/product/item/get', {'item_id': str(item_id)})
print("    code:", det.get('code'), "| message:", det.get('message'))
imgs_det = []
if str(det.get('code')) == '0':
    data_det = det.get('data') or {}
    print(">>> CLAVES del detalle:", list(data_det.keys()) if isinstance(data_det, dict) else type(data_det).__name__)
    imgs_det = buscar_imagenes(data_det)
    print(f">>> Imágenes encontradas en el DETALLE: {len(imgs_det)}")
    for ruta, val in imgs_det[:8]:
        muestra = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        print(f"    [{ruta}] -> {muestra[:120]}")
    # título / nombre
    txt = json.dumps(data_det, ensure_ascii=False).lower()
    tiene_titulo = any(t in txt for t in ('"name"', '"title"', 'short_description', 'attributes'))
    print(f">>> ¿Trae título/atributos en el detalle?: {'SÍ' if tiene_titulo else 'no visible'}")
else:
    print("    (este endpoint no respondió OK; puede llamarse distinto en Miravia)")

# ---- 3) VEREDICTO ---------------------------------------------------------
total_imgs = len(imgs_lista) + len(imgs_det)
print("\n" + "="*70)
if total_imgs > 0:
    print("  ✅ VEREDICTO: la API de Miravia SÍ devuelve imágenes de tus productos.")
    print("     => Miravia puede ser la FUENTE; la web es su espejo; Elena NO cambia nada.")
else:
    print("  ❌ VEREDICTO: en estas llamadas NO han aparecido imágenes.")
    print("     => Habría que sacar las fotos por otra vía, o invertir el flujo")
    print("        (subir en la web y de ahí a Miravia). Pega el log y lo miramos.")
print("="*70)

# ---- 4) Volcado del primer producto (por si hay que mirar a mano) --------
print("\n--- JSON del primer producto (primeros 2500 car.) ---")
print(json.dumps(p0, ensure_ascii=False, indent=2)[:2500])
print("=== PRUEBA MIRAVIA FIN ===")
