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
from anthropic import Anthropic
from supabase import create_client
import os, sys
import motor_fotos as M

sys.stdout.reconfigure(line_buffering=True)   # log vivo en Actions
SUPABASE_URL = os.environ['SUPABASE_URL']
BUCKET  = "fotos-fabrica"
HEADERS = {"User-Agent": "Mozilla/5.0"}   # Keepa/Amazon sirve imágenes con UA de navegador
MODELO  = "claude-sonnet-4-6"

sb      = create_client(SUPABASE_URL, os.environ['SUPABASE_KEY'])          # leer/escribir (anon)
admin   = create_client(SUPABASE_URL, os.environ['SUPABASE_SERVICE_KEY'])  # subir al Storage
cliente = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
print("Anthropic + Supabase (anon + service) conectados OK")

# ====================================================================
# BLOQUE REDACCIÓN  (verbatim de motor_paso3_v2; única costura: lee la CAJA)
# ====================================================================
CATEGORIAS = ["Anime y Manga", "Películas y TV", "Animación",
              "Cómics y Superhéroes", "Terror", "Videojuegos", "Música", "Deportes"]

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

def descargar_b64(url):
    r = requests.get(url, timeout=30); r.raise_for_status()
    return base64.standard_b64encode(r.content).decode()

def foto_caja(f):
    """Imagen para que la IA lea el nº de colección = la CAJA marcada en la selección."""
    el = f.get('fotos_elegidas') or {}
    if isinstance(el, dict) and el.get('caja'): return el['caja']
    fk = f.get('fotos_keepa') or []
    return fk[0] if fk else None

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

# ====================================================================
# BLOQUE VOLCADO  (verbatim de motor_paso7_web; el upsert va envuelto en función)
# ====================================================================
COLETILLA_WEB = "<br><br>Funda protectora incluida — gratis. Este Funko sale de nuestro almacén con su protector específico de regalo, para que la caja se mantenga perfecta de camino a tu estantería. Cuidamos cada pieza que enviamos protegida."
COLETILLA_MIRAVIA = "<br><br>🎁 Protector de regalo. Este Funko Pop! se envía dentro de su funda protectora específica, incluida sin coste. Lo recibes impecable y lo conservas como el primer día: la caja, a salvo de roces, polvo y luz. Un detalle de tienda especializada."

ORDEN_GALERIA = ['portada', 'caja', 'figura', 'neon', 'regla', 'protector']   # orden fijo (protector si lleva)

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

def galeria(fg, secundarias=None):
    """Orden: portada, caja, figura, [secundarias elegidas], neon, regla, protector."""
    fg = fg or {}
    out = [fg[k] for k in ('portada','caja','figura') if fg.get(k)]
    for u in (secundarias or []):
        if u and u not in out: out.append(u)
    out += [fg[k] for k in ('neon','regla','protector') if fg.get(k)]
    return out

def volcar_a_web(f, indice):
    """Upsert de un expediente a web_productos (idéntico a motor_paso7, por ficha)."""
    ean = f.get('ean'); slug = f.get('slug')
    if not ean or not slug:
        return 'saltado', None
    secundarias = (f.get('fotos_elegidas') or {}).get('secundarias') or []
    imgs = galeria(f.get('fotos_generadas'), secundarias)
    principal = (f.get('fotos_generadas') or {}).get('portada') or (imgs[0] if imgs else None)
    contenido = {
        'ean': str(ean), 'slug': slug,
        'titulo_seo': f.get('web_titulo'),
        'nombre': f.get('nombre_corto') or f.get('web_titulo'),
        'descripcion_html': f.get('web_desc'),
        'licencia': f.get('marca'),
        'categoria': f.get('categoria'), 'fandom': f.get('fandom'),
        'es_chase': bool(f.get('es_chase')), 'es_vaulted': bool(f.get('es_vaulted')),
        'es_exclusivo': bool(f.get('es_exclusivo')),
        'precio': f.get('precio_web'),            # la web lee 'precio' -> va el precio WEB
        'precio_web': f.get('precio_web'),        # para la pestaña Precios
        'precio_miravia': f.get('precio_miravia'),# solo para el feed de Miravia
        'imagen_principal': principal, 'imagenes': imgs or None,
        'origen': 'fabrica', 'activo': True,
    }
    contenido = {k: v for k, v in contenido.items() if v is not None}
    clave = (norm_ean(ean), bool(f.get('es_chase')))
    existente = indice.get(clave)
    nombre_log = (contenido.get('nombre') or f.get('web_titulo') or '')[:50]
    if existente:
        sb.table('web_productos').update(contenido).eq('id', existente['id']).execute()
        return 'actualizado', nombre_log
    nueva = dict(contenido); nueva['stock'] = 0; nueva['disponibilidad'] = 'agotado'
    sb.table('web_productos').insert(nueva).execute()
    return 'creado', nombre_log

# ====================================================================
# DIRECTOR DE ORQUESTA  (lo único nuevo: encadena los tres en una pasada)
# ====================================================================
def main():
    pendientes = sb.table('fabrica_fichas').select('*').eq('estado','fotos_ok').order('id').execute().data or []
    print(f"\nExpedientes 'fotos_ok' a publicar: {len(pendientes)}")
    if not pendientes:
        print("Nada que hacer. (Elige fotos de alguna ficha en la app y vuelve a lanzar.)"); return

    print("Descargando assets fijos del Storage...")
    try:
        fondo = descargar_asset('fondo_neon.png')
        regla = descargar_asset('regla_10cm.png')
        try:
            prot = descargar_asset('protector_funko.png')
        except Exception:
            prot = None
            print("   (aviso: sin protector_funko.png en assets/; las fichas con protector saldrán sin esa foto)")
    except Exception as e:
        print(f"❌ No pude bajar los assets (¿están en fotos-fabrica/assets/?): {e}"); return

    web = cargar_web_productos()
    indice = {(norm_ean(w.get('ean')), bool(w.get('es_chase'))): w for w in web}

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

        # 2) FOTOS
        try:
            enlaces, err = generar_fotos(f, fondo, regla, prot)
        except Exception as e:
            avisos.append(f"{ean}: fallo fotos ({e})"); continue
        if err:
            avisos.append(f"{ean}: {err} -> revisar foto a mano"); continue
        f['fotos_generadas'] = enlaces
        sb.table('fabrica_fichas').update({'fotos_generadas': enlaces}).eq('id', f['id']).execute()
        montajes = [k for k in ('portada','neon','regla') if k in enlaces]
        print(f"   📸 montajes: {', '.join(montajes)}  (+ caja/figura para la galería)")

        # 3) VOLCADO A WEB
        try:
            accion, nom = volcar_a_web(f, indice)
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

        # Regenerar el feed de Miravia (CSV en Storage). Miravia lo lee 1x/dia por su URL.
        # NO toca Miravia: solo deja el CSV fresco. Si falla, no rompe la publicacion.
        try:
            import motor_feed_miravia as FEED
            url_feed, n_feed, avisos_feed = FEED.generar_feed(sb, admin)
            print(f"🛒 Feed de Miravia regenerado: {n_feed} producto(s).")
            for a in avisos_feed: print("   ⚠️ ", a)
            print(f"   URL del feed (pégala UNA vez en Miravia, cuando la revises): {url_feed}")
        except Exception as e:
            print(f"⚠️  No pude regenerar el feed de Miravia ({e}). La web sí quedó publicada.")

    print("\n👉 Recuerda correr el sincronizador de stock para que los productos nuevos cojan stock real.")

if __name__ == "__main__":
    main()
