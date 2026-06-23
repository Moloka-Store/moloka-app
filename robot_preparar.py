# ============================================================================
# ROBOT PREPARAR  -  Circuito Fabrica en la nube (pieza PREPARAR)
# ----------------------------------------------------------------------------
# Lee el recado del buzon -> de cada foto del culo saca el EAN (pyzbar 5/5) ->
# guarda la foto en sitio permanente (Miravia campo 24) -> busca Keepa ->
# escribe el expediente en fabrica_fichas estado 'preparado'/'sin_foto'.
#
# El lector EAN y el bloque Keepa+expediente son VERBATIM de las piezas ya
# validadas (lector 5/5 del 18-jun ; motor_paso2_preparar.py con Eleven/IronMan).
# Lo unico nuevo es la fontaneria del recado (leer buzon, mover foto, limpiar).
#
# Secrets (GitHub Actions): KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY,
#                           SUPABASE_SERVICE_KEY (service_role, para subir foto)
# ============================================================================
import os, re, sys, json, datetime, tempfile
import keepa
from supabase import create_client
from pyzbar.pyzbar import decode
from PIL import Image, ImageOps, ImageEnhance

sys.stdout.reconfigure(line_buffering=True)  # log vivo en Actions (leccion 16-jun)

# ---- rutas del buzon / fotos -----------------------------------------------
BUCKET_BUZON  = 'informes'                       # privado, ya con permisos anon
CARPETA_BUZON = 'fabrica'                         # informes/fabrica/...
RECADO        = 'fabrica/_solicitud_fabrica.json'
BUCKET_FOTOS  = 'fotos-fabrica'                   # publico (la web lo lee)
CARPETA_CULOS = 'culos'                           # fotos-fabrica/culos/...

# ---- credenciales (nube = os.environ) --------------------------------------
api      = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb       = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])          # anon: tabla + buzon
sb_admin = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])  # service: subir foto permanente
print("Tokens Keepa:", api.tokens_left, "| Supabase OK")


# ============================================================================
# LECTOR EAN  (VERBATIM, validado 5/5 el 18-jun)
# ============================================================================
def leer_ean(path):
    """Lee el EAN de una foto. 4 estrategias hasta que una funcione:
    directo, escala de grises, contraste x2, y recorte de la zona del codigo."""
    im = Image.open(path).convert('RGB')
    for prueba in range(4):
        img = im
        if prueba == 1:
            img = ImageOps.grayscale(im)
        if prueba == 2:
            img = ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(2.0)
        if prueba == 3:  # recortar zona superior-izquierda (donde suele estar el codigo)
            w, h = im.size
            img = ImageOps.grayscale(im.crop((0, 0, int(w*0.45), int(h*0.40))))
        res = decode(img)
        if res:
            return [r.data.decode() for r in res if r.type in ('EAN13','UPCA','EAN8','CODE128')]
    return []


# ============================================================================
# KEEPA + EXPEDIENTE  (VERBATIM de motor_paso2_preparar.py)
# ============================================================================
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

def preparar_ean(ean, tanda, foto_culo=None, es_vaulted=False, es_chase=False,
                 es_exclusivo=False, tipo_exclusivo=None):
    print(f"   Preparando {ean} ...")
    try:
        productos = api.query(ean, domain='ES', product_code_is_asin=False, history=False, to_datetime=False)
    except Exception as e:
        print(f"      ERROR Keepa: {e}"); return False
    if not productos:
        print("      Keepa no devuelve nada."); return False
    prod = productos[0]
    fotos = extraer_imagenes(prod)
    estado = 'sin_foto' if (es_chase or not fotos) else 'preparado'
    fila = {
        'tanda': tanda, 'ean': ean, 'estado': estado,
        'titulo_keepa': prod.get('title'), 'marca': prod.get('brand'), 'asin': prod.get('asin'),
        'es_vaulted': es_vaulted, 'es_chase': es_chase, 'es_exclusivo': es_exclusivo, 'tipo_exclusivo': tipo_exclusivo,
        'fotos_keepa': fotos, 'fotos_elegidas': [], 'foto_culo': foto_culo,
    }
    sb.table('fabrica_fichas').insert(fila).execute()
    t = prod.get('title') or ''
    print(f"      OK -> estado '{estado}', {len(fotos)} fotos candidatas. {t[:55]}")
    return True


# ============================================================================
# FONTANERIA DEL RECADO  (lo unico nuevo)
# ============================================================================
def _bajar(bucket, ruta):
    """Devuelve los bytes de un objeto de Storage, o None si no existe."""
    try:
        return sb.storage.from_(bucket).download(ruta)
    except Exception:
        return None

def _guardar_culo_permanente(img_bytes, tanda, ean):
    """Sube la foto del culo a fotos-fabrica/culos/ (publico) y devuelve su URL.
    Si falla, devuelve None (el expediente se crea igual, se avisa)."""
    nombre = f"{CARPETA_CULOS}/{tanda}_{ean}.jpg"
    try:
        sb_admin.storage.from_(BUCKET_FOTOS).upload(
            nombre, img_bytes, {"content-type": "image/jpeg", "upsert": "true"})
    except Exception as e:
        print(f"      AVISO: no pude subir la foto permanente ({e}).")
        return None
    pub = sb_admin.storage.from_(BUCKET_FOTOS).get_public_url(nombre)
    if isinstance(pub, dict):
        pub = pub.get('publicUrl') or pub.get('publicURL')
    return pub

def main():
    tmp = tempfile.mkdtemp()

    crudo = _bajar(BUCKET_BUZON, RECADO)
    if crudo is None:
        print("SIN recado en informes/fabrica/. Nada que preparar. Fin.")
        return
    recado = json.loads(crudo.decode('utf-8'))
    tanda  = recado.get('tanda') or datetime.datetime.now().strftime('%Y%m%d_%H%M')
    items  = recado.get('items') or []
    print(f"Recado leido: tanda {tanda}, {len(items)} item(s).")

    ok, sin_keepa, ilegibles = [], [], []

    for i, it in enumerate(items, 1):
        ruta = it.get('foto_culo')   # ruta dentro de informes/ (la subio la app)
        print(f"\n[{i}/{len(items)}] {ruta}")
        if not ruta:
            print("   item sin foto, salto."); continue

        img_bytes = _bajar(BUCKET_BUZON, ruta)
        if img_bytes is None:
            print("   no pude bajar la foto del buzon."); ilegibles.append(ruta); continue

        local = os.path.join(tmp, os.path.basename(ruta))
        with open(local, 'wb') as f: f.write(img_bytes)

        codigos = leer_ean(local)
        if not codigos:
            print("   EAN NO LEIDO (foto movida/reflejo). La dejo en el buzon para repetir.")
            ilegibles.append(ruta); continue
        ean = codigos[0]
        print(f"   EAN leido: {ean}")

        url_culo = _guardar_culo_permanente(img_bytes, tanda, ean)

        hecho = preparar_ean(
            ean, tanda, foto_culo=url_culo,
            es_vaulted   = it.get('es_vaulted', False),
            es_chase     = it.get('es_chase', False),
            es_exclusivo = it.get('es_exclusivo', False),
            tipo_exclusivo = it.get('tipo_exclusivo'),
        )
        (ok if hecho else sin_keepa).append(ean)

    # --- limpieza: borra el recado y SOLO las fotos ya procesadas -------------
    # (las ilegibles se quedan en el buzon para que repitas la foto)
    procesadas = [it['foto_culo'] for it in items
                  if it.get('foto_culo') and it['foto_culo'] not in ilegibles]
    for ruta in procesadas:
        try: sb.storage.from_(BUCKET_BUZON).remove([ruta])
        except Exception: pass
    try: sb.storage.from_(BUCKET_BUZON).remove([RECADO])
    except Exception: pass

    print(f"\n==== RESUMEN tanda {tanda} ====")
    print(f"  Preparados OK ........ {len(ok)}  {ok}")
    if sin_keepa:  print(f"  Sin datos en Keepa ... {len(sin_keepa)}  {sin_keepa}")
    if ilegibles:  print(f"  EAN ilegible (repetir) {len(ilegibles)}  {ilegibles}")
    print("Fin.")


if __name__ == '__main__':
    main()
