# ============================================================================
# ROBOT PREPARAR v2  -  Circuito Fabrica (rediseno uno-a-uno, 24-jun)
# ----------------------------------------------------------------------------
# Lee el recado -> foto del culo -> EAN (pyzbar) -> Keepa -> fotos candidatas
# -> REDACTA la descripcion (web+miravia) con la foto de Keepa -> guarda precios
# y protector -> deja el expediente en estado 'borrador' (listo para revisar).
# La redaccion (prompt+funciones) es VERBATIM del robot GENERAR.
# Secrets: KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY
# ============================================================================
import os, re, sys, json, datetime, tempfile, base64, requests, unicodedata, io
import keepa
from supabase import create_client
from pyzbar.pyzbar import decode
from PIL import Image, ImageOps, ImageEnhance
import motor_fotos as M
# Cerebro de redaccion centralizado. Este import RE-EXPORTA estos nombres en el
# namespace de robot_preparar, que es de donde los lee robot_lote (import robot_preparar as R).
from fabrica_cerebro import cliente, MODELO, CATEGORIAS, PROMPT_SISTEMA, slugify, construir_datos, foto_caja, descargar_b64, redactar, bloque_busquedas, sugerencias_google

sys.stdout.reconfigure(line_buffering=True)

BUCKET_BUZON  = 'informes'
CARPETA_BUZON = 'fabrica'
RECADO        = 'fabrica/_solicitud_fabrica.json'
BUCKET_FOTOS  = 'fotos-fabrica'
CARPETA_CULOS = 'culos'

api      = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb       = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
sb_admin = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
SUPABASE_URL = os.environ['SUPABASE_URL']
BUCKET = 'fotos-fabrica'
HEADERS = {"User-Agent": "Mozilla/5.0"}   # Keepa/Amazon sirve imágenes con UA de navegador
print("Tokens Keepa:", api.tokens_left, "| Supabase + Anthropic OK")

# ===================== LECTOR EAN + KEEPA (verbatim) =====================
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

# ===================== REDACCION -> centralizada en fabrica_cerebro.py =====================
# PROMPT_SISTEMA, CATEGORIAS, MODELO, cliente, slugify, construir_datos, foto_caja,
# descargar_b64 y redactar se importan arriba (y quedan re-exportados para robot_lote).

# ===================== MONTAJE DE FOTOS (verbatim del GENERAR) =====================
def descargar(url):
    r = requests.get(url, headers=HEADERS, timeout=20); r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert('RGB')

def a_jpg_bytes(img, q=94):
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=q); return buf.getvalue()

def subir(admin, ruta, data):
    """Sube (o reemplaza) un jpg al bucket y devuelve su URL pública."""
    admin.storage.from_(BUCKET).upload(
        ruta, data,
        {"content-type": "image/jpeg", "upsert": "true"}  # upsert: si ya existe, lo reemplaza
    )
    return admin.storage.from_(BUCKET).get_public_url(ruta)

def descargar_asset(nombre):
    """Baja un asset fijo (fondo_neon / regla_10cm) del Storage en vez de /content."""
    url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/assets/{nombre}"
    r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
    return Image.open(io.BytesIO(r.content))

def generar_fotos(f, fondo, regla, prot=None):
    """Recorta la figura, control de calidad, monta neón/regla/portada y sube a Storage.
    Devuelve (fotos_generadas, error_o_None). La caja y la figura se reutilizan de los
    inputs Keepa para que la galería web salga completa (portada/caja/figura/neon/regla)."""
    ean = f.get('ean','sinEAN')
    # 🔒 La chase comparte EAN con la común: sus fotos van a {ean}-chase/ para NO pisar
    # las de la común en el Storage (si no, la última generada machaca a la otra).
    pref = str(ean) + ('-chase' if f.get('es_chase') else '')
    fe  = f.get('fotos_elegidas') or {}
    url_fig  = fe.get('recorte_moloka') or fe.get('principal')
    url_caja = fe.get('caja')                       # costura: la caja es 'caja' (no 'portada')
    if not url_fig:
        return None, "sin foto de figura (recorte)"
    figura = descargar(url_fig)
    rec = M.recortar(figura)
    ok, motivo = M.test_calidad(rec)
    if not ok:
        return None, f"recorte sucio ({motivo})"
    enlaces = {}
    enlaces['ficha'] = subir(admin, f"{pref}/ficha.jpg", a_jpg_bytes(M.montar_m7(rec, f)))
    if url_caja:
        caja = descargar(url_caja)
        enlaces['portada'] = subir(admin, f"{pref}/portada.jpg", a_jpg_bytes(M.montar_portada(caja, figura)))
        enlaces['caja']    = url_caja               # input reutilizado para la galería
    enlaces['figura'] = url_fig                      # input reutilizado para la galería
    # PROTECTOR: solo si la ficha lo lleva y tenemos plantilla + caja
    if f.get('con_protector') and prot is not None and url_caja:
        try:
            caja_img = descargar(url_caja)
            enlaces['protector'] = subir(admin, f"{pref}/protector.jpg", a_jpg_bytes(M.montar_protector(caja_img, prot)))
        except Exception as e:
            print(f"   (aviso: no pude montar el protector: {e})")
    return enlaces, None

admin = sb_admin

# ===================== PREPARAR + REDACTAR (uno a uno) =====================
def preparar_item(ean, item, foto_culo_url):
    print(f"   Keepa {ean} ...")
    try:
        productos = api.query(ean, domain='ES', product_code_is_asin=False, history=False, to_datetime=False)
    except Exception as e:
        print(f"      ERROR Keepa: {e}"); return False
    if not productos:
        print("      Keepa no devuelve nada."); return False
    prod = productos[0]
    fotos = extraer_imagenes(prod)

    # Expediente base con rarezas + precios + protector (del recado)
    fila = {
        'tanda': item.get('tanda'), 'ean': ean, 'estado': 'borrador',
        'titulo_keepa': prod.get('title'), 'marca': prod.get('brand'), 'asin': prod.get('asin'),
        'es_vaulted': item.get('es_vaulted', False), 'es_chase': item.get('es_chase', False),
        'es_exclusivo': item.get('es_exclusivo', False), 'tipo_exclusivo': item.get('tipo_exclusivo'),
        'fotos_keepa': fotos, 'fotos_elegidas': {}, 'foto_culo': foto_culo_url,
        'precio_web': item.get('precio_web'), 'precio_miravia': item.get('precio_miravia'),
        'con_protector': bool(item.get('con_protector', False)),
        'en_web': bool(item.get('en_web', True)), 'en_miravia': bool(item.get('en_miravia', False)),
    }

    # REDACTAR (usa la foto de Keepa para leer el numero de la caja)
    f_red = {'titulo_keepa': prod.get('title'), 'marca': prod.get('brand'),
             'es_vaulted': fila['es_vaulted'], 'es_chase': fila['es_chase'],
             'es_exclusivo': fila['es_exclusivo'], 'tipo_exclusivo': fila['tipo_exclusivo'],
             'fotos_keepa': fotos, 'fotos_elegidas': {}}
    try:
        out = redactar(f_red)
        categoria = out.get('categoria') if out.get('categoria') in CATEGORIAS else None
        nombre_corto = (out.get('nombre_corto') or '').strip() or prod.get('title')
        slug = slugify(out.get('slug') or nombre_corto)
        fila.update({
            'miravia_titulo': out.get('miravia_titulo'), 'miravia_desc': out.get('miravia_desc'),
            'web_titulo': out.get('web_titulo'), 'web_desc': out.get('web_desc'),
            'categoria': categoria, 'fandom': out.get('fandom'),
            'slug': slug, 'nombre_corto': nombre_corto,
        })
        print(f"      redactado: {nombre_corto[:50]} | cat={categoria}")
    except Exception as e:
        print(f"      AVISO: redaccion fallo ({e}). Dejo el borrador sin texto, se puede regenerar.")

    # Montaje de fotos (auto-elige caja=foto0, recorte=foto1) para que se revise YA montado.
    try:
        fila['fotos_elegidas'] = {'caja': fotos[0] if fotos else None,
                                  'recorte_moloka': fotos[1] if len(fotos) > 1 else (fotos[0] if fotos else None),
                                  'secundarias': [], 'propias_n': 0}
        fondo = descargar_asset('fondo_neon.png')
        regla = descargar_asset('regla_10cm.png')
        try: prot = descargar_asset('protector_funko.png')
        except Exception: prot = None
        enlaces, err = generar_fotos({**fila, 'fotos_elegidas': fila['fotos_elegidas']}, fondo, regla, prot)
        if enlaces:
            fila['fotos_generadas'] = enlaces
            print(f"      fotos montadas: {', '.join(k for k in ('portada','ficha','protector') if k in enlaces)}")
        elif err:
            print(f"      AVISO montaje: {err} (se podrá subir la foto a mano en la app)")
    except Exception as e:
        print(f"      AVISO: montaje de fotos falló ({e}). Se podrá subir a mano en la app.")

    # Evitar duplicados: si ya hay borradores de este mismo EAN (regeneraciones), se borran
    # antes de insertar el nuevo, para no acumular copias en la lista de borradores.
    try:
        viejos = sb.table('fabrica_fichas').select('id').eq('ean', ean).eq('estado', 'borrador').execute().data or []
        if viejos:
            for v in viejos:
                sb.table('fabrica_fichas').delete().eq('id', v['id']).execute()
            print(f"      (limpiados {len(viejos)} borrador(es) anterior(es) del mismo EAN)")
    except Exception as e:
        print(f"      (aviso: no pude limpiar borradores anteriores: {e})")

    sb.table('fabrica_fichas').insert(fila).execute()
    print(f"      OK -> 'borrador', {len(fotos)} candidatas + montaje.")
    return True

def main():
    tmp = tempfile.mkdtemp()
    crudo = _bajar(BUCKET_BUZON, RECADO)
    if crudo is None:
        print("SIN recado. Nada que preparar."); return
    recado = json.loads(crudo.decode('utf-8'))
    tanda  = recado.get('tanda') or datetime.datetime.now().strftime('%Y%m%d_%H%M')
    items  = recado.get('items') or []
    print(f"Recado: tanda {tanda}, {len(items)} item(s).")

    ok, ilegibles = [], []
    for i, it in enumerate(items, 1):
        it['tanda'] = tanda
        ruta = it.get('foto_culo')
        print(f"\n[{i}/{len(items)}] {ruta}")
        if not ruta: continue
        img_bytes = _bajar(BUCKET_BUZON, ruta)
        if img_bytes is None:
            print("   no pude bajar la foto."); ilegibles.append(ruta); continue
        local = os.path.join(tmp, os.path.basename(ruta))
        with open(local, 'wb') as f: f.write(img_bytes)
        codigos = leer_ean(local)
        if not codigos:
            print("   EAN NO LEIDO. La dejo para repetir."); ilegibles.append(ruta); continue
        ean = codigos[0]
        print(f"   EAN: {ean}")
        url_culo = _guardar_culo_permanente(img_bytes, tanda, ean)
        if preparar_item(ean, it, url_culo): ok.append(ean)

    procesadas = [it['foto_culo'] for it in items if it.get('foto_culo') and it['foto_culo'] not in ilegibles]
    for r in procesadas:
        try: sb.storage.from_(BUCKET_BUZON).remove([r])
        except Exception: pass
    try: sb.storage.from_(BUCKET_BUZON).remove([RECADO])
    except Exception: pass

    print(f"\n==== RESUMEN tanda {tanda} ====")
    print(f"  Borradores OK: {ok}")
    if ilegibles: print(f"  EAN ilegible (repetir): {ilegibles}")
    print("Fin.")

if __name__ == '__main__':
    main()
