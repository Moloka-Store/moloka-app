# =====================================================================
#  MOLOKA · FÁBRICA DE FICHAS · ROBOT GENERAR  (Colab / nube)
#  Ensamblado de tus motores reales (no se reescribe su lógica):
#     · REDACCIÓN  = motor_paso3_v2   (lee el nº de la caja, redacta SEO)
#     · FOTOS      = motor_fotos      (recorte + neón + regla + portada)
#     · VOLCADO    = motor_paso7_web  (upsert a web_productos)
#
#  Coge cada expediente en 'fotos_ok' y lo deja 'publicado' en una sola pasada:
#  redacta -> monta y sube fotos -> vuelca a la web. Resuelve el choque de
#  estados (antes fotos dejaba 'fotos_subidas' y el volcado buscaba 'generado').
#
#  Necesita en /content: motor_fotos.py
#  Assets: se descargan solos de Storage -> fotos-fabrica/assets/
#  Secrets de Colab: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
# =====================================================================

import json, base64, requests, unicodedata, re, io
from PIL import Image
from supabase import create_client
import os, sys
import motor_fotos as M
from fabrica_cerebro import cliente, MODELO, CATEGORIAS, PROMPT_SISTEMA, slugify, construir_datos, foto_caja, descargar_b64, redactar

sys.stdout.reconfigure(line_buffering=True)   # log vivo en Actions
SUPABASE_URL = os.environ['SUPABASE_URL']
BUCKET  = "fotos-fabrica"
HEADERS = {"User-Agent": "Mozilla/5.0"}   # Keepa/Amazon sirve imágenes con UA de navegador

sb      = create_client(SUPABASE_URL, os.environ['SUPABASE_KEY'])          # leer/escribir (anon)
admin   = create_client(SUPABASE_URL, os.environ['SUPABASE_SERVICE_KEY'])  # subir al Storage
print("Anthropic + Supabase (anon + service) conectados OK")

# ====================================================================
# BLOQUE REDACCIÓN  -> centralizado en fabrica_cerebro.py
# (PROMPT_SISTEMA, CATEGORIAS, MODELO, cliente, slugify, construir_datos,
#  foto_caja, descargar_b64 y redactar se importan arriba.)
# ====================================================================

# ====================================================================
# BLOQUE FOTOS  (recetas intactas de motor_fotos.py vía M.*; helpers de Storage)
# ====================================================================
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
    enlaces['ficha'] = subir(admin, f"{ean}/ficha.jpg", a_jpg_bytes(M.montar_m7(rec, f)))
    if url_caja:
        caja = descargar(url_caja)
        enlaces['portada'] = subir(admin, f"{ean}/portada.jpg", a_jpg_bytes(M.montar_portada(caja, figura)))
        enlaces['caja']    = url_caja               # input reutilizado para la galería
    enlaces['figura'] = url_fig                      # input reutilizado para la galería
    # PROTECTOR: solo si la ficha lo lleva y tenemos plantilla + caja
    if f.get('con_protector') and prot is not None and url_caja:
        try:
            caja_img = descargar(url_caja)
            enlaces['protector'] = subir(admin, f"{ean}/protector.jpg", a_jpg_bytes(M.montar_protector(caja_img, prot)))
        except Exception as e:
            print(f"   (aviso: no pude montar el protector: {e})")
    return enlaces, None

# ====================================================================
# BLOQUE VOLCADO  (verbatim de motor_paso7_web; el upsert va envuelto en función)
# ====================================================================
COLETILLA_WEB = "<br><br>Funda protectora incluida — gratis. Este Funko sale de nuestro almacén con su protector específico de regalo, para que la caja se mantenga perfecta de camino a tu estantería. Cuidamos cada pieza que enviamos protegida."
COLETILLA_MIRAVIA = "<br><br>🎁 Protector de regalo. Este Funko Pop! se envía dentro de su funda protectora específica, incluida sin coste. Lo recibes impecable y lo conservas como el primer día: la caja, a salvo de roces, polvo y luz. Un detalle de tienda especializada."

GPSR_WEB = "<br><br><b>Información de seguridad del producto (GPSR)</b><br>Responsable en la UE: Funko EU BV · Zuidplein 36, 1077 XV Ámsterdam (NL) · supportEMEA@funko.com"

ORDEN_GALERIA = ['portada', 'caja', 'figura', 'ficha', 'protector']   # orden fijo (protector si lleva)

def norm_ean(ean):
    """EAN normalizado para casar (hay UPC con/sin cero inicial)."""
    return (str(ean) or '').strip().lstrip('0')

def cargar_web_productos():
    """Trae web_productos entero (paginado por si supera 1000 filas)."""
    filas, desde = [], 0
    while True:
        r = sb.table('web_productos').select('*').range(desde, desde+999).execute()
        lote = r.data or []
        filas += lote
        if len(lote) < 1000:
            break
        desde += 1000
    return filas

_CACHE_CLAVE_IMG = {}
def _clave_contenido(url):
    """Clave para deduplicar por CONTENIDO (misma imagen subida con distinto nombre/URL).
    Usa el ETag de Supabase (hash del archivo) o, si no, el tamaño; via HEAD (sin descargar).
    Si el HEAD falla, cae a la propia URL (no rompe). Cachea para no repetir HEADs."""
    if url in _CACHE_CLAVE_IMG:
        return _CACHE_CLAVE_IMG[url]
    import urllib.request
    clave = url
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=15) as r:
            et = r.headers.get('ETag')
            cl = r.headers.get('Content-Length')
            if et: clave = 'etag:' + et.strip('"')
            elif cl: clave = 'len:' + cl
    except Exception:
        pass
    _CACHE_CLAVE_IMG[url] = clave
    return clave


def _dedup_contenido(urls):
    """Quita imagenes con el mismo CONTENIDO (misma imagen, distinto nombre/URL), en orden."""
    vistos, out = {}, []
    for u in urls:
        if not (isinstance(u, str) and u.strip()):
            continue
        k = _clave_contenido(u)
        if k in vistos:
            continue
        vistos[k] = 1
        out.append(u)
    return out


def galeria(fg, secundarias=None):
    """Orden: portada, caja, figura, ficha (M7), [secundarias], protector.
    Dedup por CONTENIDO (ETag): quita la misma imagen subida con distinto nombre."""
    fg = fg or {}
    cand = [fg[k] for k in ('portada','caja','figura','ficha') if fg.get(k)]
    cand += list(secundarias or [])
    if fg.get('protector'):
        cand.append(fg['protector'])
    return _dedup_contenido(cand)

def cargar_stock_inventario():
    """Índice {(ean_norm, es_chase): stock_moloka} desde el inventario (tabla 'productos').
    Es la fuente REAL del stock del almacén — la misma que usa la app. La web refleja ESTE
    stock; nunca se inventa 0/agotado. La común y la chase son filas distintas (es_chase),
    así que cada una cruza con SU stock y no se mezclan."""
    filas, desde = [], 0
    while True:
        r = sb.table('productos').select('ean,es_chase,stock_moloka').range(desde, desde+999).execute()
        lote = r.data or []
        filas += lote
        if len(lote) < 1000:
            break
        desde += 1000
    idx = {}
    for prod in filas:
        idx[(norm_ean(prod.get('ean')), bool(prod.get('es_chase')))] = prod.get('stock_moloka') or 0
    return idx

def volcar_a_web(f, indice, stock_inv):
    """Upsert de un expediente a web_productos (idéntico a motor_paso7, por ficha)."""
    ean = f.get('ean'); slug = f.get('slug')
    if not ean or not slug:
        return 'saltado', None
    # 🔒 SLUG ÚNICO PARA LA CHASE: la chase comparte EAN con la común y la IA les da el
    # MISMO slug (lo saca del nombre, que es idéntico). Sin esto, las dos acaban con la
    # misma URL en la web y una pisa a la otra (getStaticPaths descarta el path duplicado:
    # "dos fichas en una"). Con el sufijo, la chase vive en su propia ficha separada.
    if bool(f.get('es_chase')) and not str(slug).endswith('-chase'):
        slug = str(slug) + '-chase'
    secundarias = (f.get('fotos_elegidas') or {}).get('secundarias') or []
    imgs = galeria(f.get('fotos_generadas'), secundarias)
    principal = (f.get('fotos_generadas') or {}).get('portada') or (imgs[0] if imgs else None)
    # Titulo visible: si lleva protector, lo anadimos al nombre (guard anti-duplicado)
    nombre_titulo = f.get('nombre_corto') or f.get('web_titulo') or ''
    if f.get('con_protector') and 'protector' not in nombre_titulo.lower():
        nombre_titulo = nombre_titulo.rstrip() + ' con protector incluido'
    # --- Datos para el Excel de Miravia (atributos adicionales + foto caja GPSR) ---
    _nc = (f.get('nombre_corto') or '').strip()
    _mnum = re.search(r'#\s*(\d+)', _nc)
    _num = _mnum.group(1) if _mnum else ''
    _personaje = re.sub(r'\s*#\s*\d+\s*$', '', _nc).strip()
    _atrs = f"Franchise:{f.get('fandom') or ''};Character:{_personaje};Collection Number:{_num};Height:10 cm;Official Product:Yes"
    _foto_caja = (f.get('fotos_elegidas') or {}).get('caja')
    # Imágenes para Miravia: PRINCIPAL en fondo blanco (figura Keepa) primero, luego caja y montajes M7
    _fg = f.get('fotos_generadas') or {}
    _mimgs = _dedup_contenido([_fg.get('portada'), _fg.get('caja'), _fg.get('figura'), _fg.get('ficha')] + list(secundarias or []))
    # Stock REAL del almacén (inventario). Una joya que tienes NO nace agotada; y la que
    # no tengas sale agotada de verdad. Común y chase cruzan por (EAN, es_chase) por separado.
    stock_real = stock_inv.get((norm_ean(ean), bool(f.get('es_chase'))), 0)
    disponible = 'inmediato' if stock_real and stock_real > 0 else 'agotado'
    contenido = {
        'ean': str(ean), 'slug': slug,
        'stock': stock_real, 'disponibilidad': disponible,
        'titulo_seo': f.get('web_titulo'),
        'nombre': nombre_titulo,
        'descripcion_html': f.get('web_desc'),
        'licencia': f.get('marca'),
        'categoria': f.get('categoria'), 'fandom': f.get('fandom'),
        'es_chase': bool(f.get('es_chase')), 'es_vaulted': bool(f.get('es_vaulted')),
        'es_exclusivo': bool(f.get('es_exclusivo')),
        'precio': f.get('precio_web'),            # la web lee 'precio' -> va el precio WEB
        'precio_web': f.get('precio_web'),        # para la pestaña Precios
        'precio_miravia': f.get('precio_miravia'),# solo para el feed de Miravia
        'imagen_principal': principal, 'imagenes': imgs or None,
        'miravia_titulo': f.get('miravia_titulo'), 'miravia_desc': f.get('miravia_desc'),
        'miravia_atributos': _atrs, 'foto_caja': _foto_caja, 'miravia_imagenes': _mimgs or None,
        'foto_culo': f.get('foto_culo'),
        'origen': 'fabrica', 'activo': bool(f.get('en_web', True)),
        # origen_id = id del producto dentro de la fabrica. Como chase y comun
        # comparten EAN, la chase lleva sufijo -chase para no colisionar (igual
        # que el slug y que la clave de dedup (ean, es_chase)).
        'origen_id': str(ean) + ('-chase' if f.get('es_chase') else ''),
        'en_web': bool(f.get('en_web', True)), 'en_miravia': bool(f.get('en_miravia', False)),
    }
    contenido = {k: v for k, v in contenido.items() if v is not None}
    clave = (norm_ean(ean), bool(f.get('es_chase')))
    existente = indice.get(clave)
    nombre_log = (contenido.get('nombre') or f.get('web_titulo') or '')[:50]
    if existente:
        # Si el producto venía de otro origen (TCG/BEMS) y ahora pasa a fábrica, limpiar el
        # precio_oferta HEREDADO: el de TCG lo puso el director automático y aquí quedaría
        # colgado (el director ya no toca los de fábrica). Las ofertas de fábrica se ponen a mano.
        if (existente.get('origen') or '') != 'fabrica':
            contenido['precio_oferta'] = None
        sb.table('web_productos').update(contenido).eq('id', existente['id']).execute()
        return 'actualizado', nombre_log
    # stock y disponibilidad ya van en 'contenido' con el valor REAL del inventario
    sb.table('web_productos').insert(dict(contenido)).execute()
    return 'creado', nombre_log

# ====================================================================
# DIRECTOR DE ORQUESTA  (lo único nuevo: encadena los tres en una pasada)
# ====================================================================
def main():
    pendientes = sb.table('fabrica_fichas').select('*').eq('estado','fotos_ok').order('id').execute().data or []
    print(f"\nExpedientes 'fotos_ok' a publicar: {len(pendientes)}")
    if not pendientes:
        print("Nada que hacer. (Elige fotos de alguna ficha en la app y vuelve a lanzar.)"); return

    web = cargar_web_productos()
    indice = {(norm_ean(w.get('ean')), bool(w.get('es_chase'))): w for w in web}
    stock_inv = cargar_stock_inventario()   # stock REAL del almacén (tabla productos)
    print(f"   inventario: {len(stock_inv)} referencias con su stock_moloka")

    publicadas, avisos = 0, []
    for f in pendientes:
        ean = f.get('ean','sinEAN')
        print(f"\n── {ean} · {(f.get('titulo_keepa') or '')[:45]}")

        # 1) PROTECTOR: si lleva, pegar la coletilla aprobada al final de las descripciones
        if f.get('con_protector'):
            if f.get('web_desc'):     f['web_desc']     = (f['web_desc'] or '').rstrip() + COLETILLA_WEB
            if f.get('miravia_desc'): f['miravia_desc'] = (f['miravia_desc'] or '').rstrip() + COLETILLA_MIRAVIA
            sb.table('fabrica_fichas').update({'web_desc': f.get('web_desc'), 'miravia_desc': f.get('miravia_desc')}).eq('id', f['id']).execute()
            print("   protector: coletillas anadidas")

        # 1b) GPSR: bloque legal fijo (Funko) al final de la descripcion web, sin duplicar
        if f.get('web_desc') and 'GPSR' not in (f.get('web_desc') or ''):
            f['web_desc'] = (f['web_desc'] or '').rstrip() + GPSR_WEB
            sb.table('fabrica_fichas').update({'web_desc': f.get('web_desc')}).eq('id', f['id']).execute()
            print("   GPSR: bloque legal anadido")

        # 2) VOLCADO A WEB (las fotos ya vienen montadas y revisadas desde PREPARAR)
        try:
            accion, nom = volcar_a_web(f, indice, stock_inv)
        except Exception as e:
            avisos.append(f"{ean}: fallo volcado ({e})"); continue

        # 4) ESTADO FINAL
        sb.table('fabrica_fichas').update({'estado': 'publicado'}).eq('id', f['id']).execute()
        publicadas += 1
        print(f"   🌐 web: {accion} · estado -> publicado")

    print("\n" + "─"*55)
    print(f"✅ {publicadas} fichas publicadas (texto + fotos + web).")
    if avisos:
        print(f"⚠️  {len(avisos)} para revisar a mano:")
        for a in avisos: print("   -", a)

    # Reconstruir la web sola (Astro es estático): avisar al Deploy Hook de Vercel.
    # Solo si se publicó algo y el hook está configurado. Si falla, no rompe nada.
    if publicadas:
        hook = os.environ.get('VERCEL_DEPLOY_HOOK')
        if hook:
            try:
                r = requests.post(hook, timeout=30)
                if r.status_code in (200, 201):
                    print("🔄 Web avisada para reconstruirse (Vercel). En ~1-2 min saldrá lo nuevo.")
                else:
                    print(f"⚠️  El aviso a Vercel respondió HTTP {r.status_code} (revisa el Deploy Hook).")
            except Exception as e:
                print(f"⚠️  No pude avisar a Vercel ({e}). La web se reconstruirá en el próximo deploy.")
        else:
            print("ℹ️  Sin VERCEL_DEPLOY_HOOK configurado: la web no se reconstruye sola.")

    print("\n👉 Recuerda correr el sincronizador de stock para que los productos nuevos cojan stock real.")

if __name__ == "__main__":
    main()
