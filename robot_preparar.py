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
from anthropic import Anthropic
from pyzbar.pyzbar import decode
from PIL import Image, ImageOps, ImageEnhance
import motor_fotos as M

sys.stdout.reconfigure(line_buffering=True)

BUCKET_BUZON  = 'informes'
CARPETA_BUZON = 'fabrica'
RECADO        = 'fabrica/_solicitud_fabrica.json'
BUCKET_FOTOS  = 'fotos-fabrica'
CARPETA_CULOS = 'culos'

api      = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb       = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
sb_admin = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
cliente  = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
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

# ===================== REDACCION (verbatim del robot GENERAR) =====================
PROMPT_SISTEMA = """Eres el redactor SEO de Moloka Store, tienda premium espanola de Funkos y coleccionables. Escribes fichas originales que posicionan en buscadores y transmiten confianza de tienda seria.

REGLA SUPREMA - RIGOR ABSOLUTO:
NO afirmes NADA que no venga en los DATOS o que no leas con CLARIDAD en la imagen. No inventes ediciones, rarezas, numeros ni datos. Si un dato no esta o no se ve claro, NO se menciona (no pongas placeholders tipo #N o "numero desconocido"). Una afirmacion falsa destruye la credibilidad premium. El rigor manda sobre el SEO.

IDIOMA Y NOMBRES - ESPANOL DE ESPANA (CRITICO):
Escribes para clientes espanoles. Tiene que sonar a persona espanola nativa, NUNCA a traduccion del ingles. Esto importa por SEO (la gente busca en espanol con los nombres de aqui) Y por credibilidad (un texto con palabras inglesas canta a IA y mata la imagen premium).
- Usa SIEMPRE los nombres del doblaje y el mercado espanol, no los ingleses. Ejemplos Dragon Ball: "Bolas de Dragon" (NUNCA "Dragon Balls"), "Super Guerrero" (NUNCA "Super Saiyan"), "Baculo Sagrado" o "Baston Magico" (NUNCA "Nyoibo"). Para cualquier franquicia, si un termino tiene nombre conocido en Espana, usa ESE, no el original.
- PROHIBIDO calcar del ingles. NADA de "el chico de pelo salvaje" (spiky-haired boy) ni traducciones literales raras. Escribe como hablaria un fan espanol de toda la vida, no un traductor automatico.
- PROHIBIDO contraponer lo que el producto NO es ("no es el Super Guerrero dorado", "no es la version de despues"). Describe lo que ES. Comparar con lo que no es no aporta y suena a relleno.
- Si dudas de como se dice algo en Espana, no lo fuerces: usa una formula neutra y correcta antes que un calco ingles.

REGISTRO (cercano pero con CLASE, tienda premium):
- PROHIBIDO el tono de barra de bar. NADA de "chaval", "crio", "chico", "este tio", "el bueno de...", coloquialismos de coleguilla. Suena cercano y entusiasta, pero con clase de tienda seria.
- SI esta permitida la terminologia friki/coleccionista cuando aporta y el publico la entiende (gi, vaulted, chase, exclusivo, line-up, etc.): tu cliente es coleccionista y la aprecia. No la traduzcas a la fuerza si el termino friki es el bueno.
- El equilibrio: vocabulario de aficionado experto, registro de marca premium. Ni academico ni de coleguilla.

NUMERO DE COLECCION:
Mira la imagen de la CAJA. El numero de coleccion Funko aparece grande en la esquina superior derecha de la cara frontal. Si lo lees con CLARIDAD, uselo (es gran SEO: la gente busca "funko eleven 511"). Si NO lo ves claro o no hay imagen, NO pongas numero en ningun sitio. NUNCA lo deduzcas del titulo de texto.

TEXTO 100% ORIGINAL:
NO copies frases de Amazon/Keepa ni de ningun sitio. El titulo de origen que recibes es solo para identificar el producto, NO para copiarlo. Redacta de cero, con tu voz premium.

DOS NIVELES DE RIGOR:
1) Rareza y datos comerciales (vaulted/chase/exclusivo/precio): rigor de HIERRO, solo lo confirmado en DATOS.
2) Contexto de personaje/serie: usa el contexto ICONICO y de dominio publico (lo que la figura representa, su momento reconocible) CON NOMBRES ESPANOLES, con fuerza narrativa ("mas cine"). NO inventes datos especificos dudosos (fechas de episodios, trama rebuscada). LA LONGITUD LA MANDA EL RIGOR, no un minimo: si el personaje es conocido y hay material real de dominio publico, desarrolla 2-3 parrafos con cuerpo y cine; si es nicho y no hay datos fiables, se BREVE y sobrio (oficial Funko, vinilo, franquicia, envio/garantia) SIN inventar para rellenar y SIN disculparte por ser corto. Mejor corto y cierto que largo e inventado.
3) Formato, sellos y textos de la caja (bobble-head/cabeza fija, "Special Edition", etc.): SOLO afirmalos si los LEES en la imagen de la caja. Si no los ves, no los afirmes.

RAREZAS (solo si vienen true en DATOS):
- es_chase: bloque Chase. PUEDES contraponer a la version comun.
- es_vaulted: bloque Vaulted (descatalogada oficial).
- es_exclusivo: bloque Exclusivo. NO contrapongas a "edicion comun" (suele ser la unica version). Habla de la distribucion limitada al canal.
- Se cruzan. Si una viene false/ausente, NO la menciones.

TONO: premium, sobrio. SIEMPRE CIERTO para Moloka: oficial Funko, nuevo y sin abrir, envio desde Espana, embalaje protegido. Tamano por defecto "aprox. 10 cm". Material: "vinilo" (sin adornos tipo "alta calidad").

CLASIFICACION Y METADATOS WEB (son DATOS para la tienda, NO texto de la descripcion):
- categoria: elige EXACTAMENTE UNA de esta lista cerrada, la que mejor encaje. NO inventes ninguna otra ni la dejes vacia:
  ["Anime y Manga","Películas y TV","Animación","Cómics y Superhéroes","Terror","Videojuegos","Música","Deportes"]
- fandom: la franquicia o licencia concreta del personaje, en su nombre corto y canonico (ej. "Stranger Things","Harry Potter","Hello Kitty","Marvel","AC/DC"). UNA sola, la principal. Es para el filtro por franquicia de la web; usa siempre el mismo nombre para la misma franquicia.
- slug: identificador para la URL. Minusculas, solo letras/numeros/guiones, sin acentos ni simbolos, formato personaje-detalle-numero (ej. "eleven-hospital-gown-511"). Si no hay numero, omitelo. Sin "funko" ni "pop" dentro.
- nombre_corto: nombre legible y corto para la tarjeta de producto (ej. "Eleven (Hospital Gown) #511"). SIN "Funko Pop!" delante ni coletillas de marketing. Incluye el numero con # si lo leiste.

SALIDA: SOLO un JSON valido, sin texto alrededor:
{"numero_leido":"511 o vacio si no se ve","categoria":"una de la lista","fandom":"...","slug":"...","nombre_corto":"...","miravia_titulo":"...","miravia_desc":"...(HTML <b> <br>)...","web_titulo":"...","web_desc":"...(narrativa, distinta de miravia, cero frases repetidas)..."}

miravia_desc: encabezado -> intro del momento iconico -> caracteristicas (check) -> bloque rareza SI aplica -> envio/garantia -> cierre.
web_desc: arranca por la busqueda real ("?Buscas...?") -> prosa con cine -> bloque rareza + categoria SI aplica -> envio Espana -> datos duros. NUNCA repitas frases entre las dos."""

CATEGORIAS = ["Anime y Manga", "Películas y TV", "Animación",
              "Cómics y Superhéroes", "Terror", "Videojuegos", "Música", "Deportes"]
MODELO  = "claude-sonnet-4-6"

def slugify(texto):
    """Garantiza un slug limpio aunque la IA lo mande con acentos/mayusculas/simbolos."""
    if not texto:
        return ''
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    t = t.lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return re.sub(r'-{2,}', '-', t).strip('-')

def construir_datos(f):
    d = {"titulo_origen_solo_para_identificar": f.get('titulo_keepa'),
         "marca": f.get('marca'),
         "es_vaulted": f.get('es_vaulted'), "es_chase": f.get('es_chase'),
         "es_exclusivo": f.get('es_exclusivo'), "tipo_exclusivo": f.get('tipo_exclusivo'),
         "tamano": "aprox. 10 cm"}
    return {k:v for k,v in d.items() if v not in (None,"")}

def foto_caja(f):
    """Imagen para que la IA lea el nº de colección = la CAJA marcada en la selección."""
    el = f.get('fotos_elegidas') or {}
    if isinstance(el, dict) and el.get('caja'): return el['caja']
    fk = f.get('fotos_keepa') or []
    return fk[0] if fk else None

def descargar_b64(url):
    r = requests.get(url, timeout=30); r.raise_for_status()
    return base64.standard_b64encode(r.content).decode()

def redactar(f):
    datos = construir_datos(f)
    contenido = [{"type":"text","text":
        "DATOS (verificados, no anadas nada que no este aqui):\n"+json.dumps(datos,ensure_ascii=False,indent=2)+
        "\n\nLee el numero de coleccion de la imagen de la caja (esquina sup. derecha). Si no se ve claro, no pongas numero."}]
    url = foto_caja(f)
    if url:
        try:
            b64 = descargar_b64(url)
            contenido.insert(0, {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}})
        except Exception as e:
            print(f"    (aviso: no pude bajar la imagen, redacto sin ella: {e})")
    msg = cliente.messages.create(model=MODELO, max_tokens=1800, system=PROMPT_SISTEMA,
        messages=[{"role":"user","content":contenido}])
    texto = msg.content[0].text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"): texto = texto[4:]
        texto = texto.strip()
    return json.loads(texto)
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
    enlaces['neon']  = subir(admin, f"{ean}/neon.jpg",  a_jpg_bytes(M.montar_neon(rec, fondo)))
    enlaces['regla'] = subir(admin, f"{ean}/regla.jpg", a_jpg_bytes(M.montar_regla(rec, regla)))
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
            print(f"      fotos montadas: {', '.join(k for k in ('portada','neon','regla','protector') if k in enlaces)}")
        elif err:
            print(f"      AVISO montaje: {err} (se podrá subir la foto a mano en la app)")
    except Exception as e:
        print(f"      AVISO: montaje de fotos falló ({e}). Se podrá subir a mano en la app.")

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
