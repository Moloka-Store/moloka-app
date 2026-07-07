# ============================================================================
# MOLOKA · FÁBRICA DE FICHAS · CEREBRO DE REDACCIÓN (módulo compartido)
# ----------------------------------------------------------------------------
# Único sitio donde vive el "cerebro" de redacción de la fábrica: el prompt de
# sistema de Claude, las constantes (modelo, categorías) y las funciones que
# arman la llamada a la API. Lo importan robot_generar, robot_preparar y
# robot_redactar (y, vía robot_preparar, robot_lote) para NO tener el prompt
# copiado en cada uno.
#
# Antes estaba duplicado VERBATIM en los tres robots; cualquier retoque había
# que hacerlo tres veces. Aquí es uno solo.
#   · PROMPT_SISTEMA          -> versión base (generar + preparar + lote).
#   · PROMPT_SISTEMA_REDACTAR -> base + cola GEO (para robot_redactar).
#
# Secrets: ANTHROPIC_API_KEY (el cliente se crea al importar).
# Los clientes de Supabase NO viven aquí: cada robot crea el suyo.
# ============================================================================
import os, json, base64, re, unicodedata, requests
import xml.etree.ElementTree as ET
from anthropic import Anthropic

cliente = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
# Motor por carril (env-configurable): la fabrica actual (PREPARAR/Regenerar/GENERAR)
# va con Sonnet; los lotes / TCG (robot_lote) van con Haiku, mas barato/rapido.
MODELO      = os.environ.get('MODELO_FABRICA', 'claude-sonnet-4-6')  # carril fabrica
MODELO_LOTE = os.environ.get('MODELO_LOTE',    'claude-haiku-4-5')   # carril lotes / TCG

HEADERS = {"User-Agent": "Mozilla/5.0"}   # UA de navegador (para bajar imagenes y para Google)

# --- Autocompletar de Google (busquedas reales de la gente, para SEO) ---
GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
MAX_SUGERENCIAS    = 10
# Freno rapido por si Google limita: SUGERENCIAS_GOOGLE=0 desactiva la consulta.
SUGERENCIAS_ON = os.environ.get('SUGERENCIAS_GOOGLE', '1').strip().lower() not in ('0', 'false', 'no', '')

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
- nombre_corto: nombre legible y corto para la TARJETA de producto (ej. "Eleven (Hospital Gown) #511"). SIN "Funko Pop!" delante ni coletillas de marketing. Incluye el numero con # si lo leiste. Este es el nombre corto de la tarjeta: NO metas aqui palabras clave de SEO (eso va en web_titulo y sinonimos), mantenlo limpio.
- web_titulo: titulo SEO para el <title>/<h1> de la web (distinto de nombre_corto, que es la tarjeta). Rico en las palabras que la gente busca DE VERDAD: "Funko Pop!" + franquicia + personaje + #numero si lo leiste, y algun termino del bloque BUSQUEDAS REALES cuando encaje y sea CIERTO para este producto. Legible y natural, sin amontonar palabras clave.
- sinonimos: cadena separada por comas con nombres alternativos y terminos de busqueda para el buscador (variantes espanol/ingles del personaje y la franquicia, alias, numero de coleccion, con y sin "funko"). Solo terminos CIERTOS y relevantes para este producto; apoyate en las BUSQUEDAS REALES cuando encajen. No inventes. Vacio si no hay nada claro.
- alt: texto alternativo de la imagen principal (accesibilidad y SEO de imagen). UNA sola frase concisa que describe lo que SE VE ("Funko Pop! de <personaje> (#<num> si lo hay) de <franquicia>, figura de vinilo"). Cierto y sin marketing.

SALIDA: SOLO un JSON valido, sin texto alrededor:
{"numero_leido":"511 o vacio si no se ve","categoria":"una de la lista","fandom":"...","slug":"...","nombre_corto":"...","sinonimos":"...","alt":"...","miravia_titulo":"...","miravia_desc":"...(HTML <b> <br>)...","web_titulo":"...","web_desc":"...(narrativa, distinta de miravia, cero frases repetidas)..."}

miravia_desc: encabezado -> intro del momento iconico -> caracteristicas (check) -> bloque rareza SI aplica -> envio/garantia -> cierre.
web_desc: arranca por la busqueda real ("?Buscas...?") -> prosa con cine -> bloque rareza + categoria SI aplica -> envio Espana -> datos duros. NUNCA repitas frases entre las dos."""

# Cola GEO (Generative Engine Optimization): solo para robot_redactar. Ayuda a que
# ChatGPT/Gemini/Perplexity puedan CITAR la ficha con datos autocontenidos.
EXTRA_GEO = """Ademas, para que los asistentes de IA (ChatGPT, Gemini, Perplexity...) puedan CITARTE bien, responde de forma clara y directa -sin inventar- a lo que un comprador preguntaria: que es una figura OFICIAL de Funko, nueva y sin abrir, que se envia desde Espana con embalaje protegido, y si es chase/vaulted/exclusivo cuando aplique. Cierra con una frase de datos autocontenida y citable (tamano aprox. 10 cm, vinilo, oficial, envio desde Espana), integrada con naturalidad, sin que parezca una ficha tecnica fria."""

PROMPT_SISTEMA_REDACTAR = PROMPT_SISTEMA + " " + EXTRA_GEO


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

# --- Autocompletar de Google: busquedas reales de la gente para el SEO ---
_MULETILLAS = {"pop", "pop!", "vinyl", "figure", "figura", "figuras", "television",
               "tv", "vinilo", "collectible", "coleccionable", "de", "the"}

def _limpiar_semilla(texto):
    """De un titulo ruidoso (p.ej. de Keepa) saca una semilla corta y buscable, con
    el prefijo 'funko' (asi es como busca la gente: 'funko eleven 511')."""
    if not texto:
        return ''
    t = str(texto).lower()
    t = re.sub(r'[^a-z0-9áéíóúñü ]+', ' ', t)          # fuera puntuacion/simbolos
    palabras = [w for w in t.split() if w and w not in _MULETILLAS]
    palabras = palabras[:6]                             # primeras palabras distintivas
    if not palabras:
        return ''
    if palabras[0] != 'funko':
        palabras = ['funko'] + palabras
    return ' '.join(palabras).strip()

def sugerencias_google(consulta):
    """Busquedas reales del autocompletar de Google (endpoint gratuito 'suggestqueries',
    output=toolbar -> XML). BEST-EFFORT: ante cualquier fallo devuelve [] y no rompe nada.
    Devuelve una lista de sugerencias normalizadas (minusculas, sin duplicados, cap)."""
    consulta = (consulta or '').strip()
    if not consulta:
        return []
    try:
        r = requests.get(GOOGLE_SUGGEST_URL,
                         params={"output": "toolbar", "hl": "es", "gl": "ES", "q": consulta},
                         headers=HEADERS, timeout=8)
        r.raise_for_status()
        # Parsear los BYTES: el XML de toolbar declara ISO-8859-1 y ET respeta esa cabecera.
        raiz = ET.fromstring(r.content)
        out, vistos = [], set()
        base = consulta.lower()
        for sug in raiz.iter('suggestion'):
            data = (sug.get('data') or '').strip().lower()
            if not data or data == base or data in vistos:
                continue
            vistos.add(data)
            out.append(data)
            if len(out) >= MAX_SUGERENCIAS:
                break
        return out
    except Exception as e:
        print(f"    (aviso: autocompletar de Google no disponible, sigo sin el: {e})")
        return []

def bloque_busquedas(semilla):
    """Bloque de texto (dict para 'contenido') con las busquedas reales de Google para
    orientar el SEO de la redaccion. Devuelve None si el toggle esta off, no hay semilla
    o Google no devuelve nada. Las sugerencias son PISTAS DE FRASEO, nunca datos."""
    if not SUGERENCIAS_ON:
        return None
    limpia = _limpiar_semilla(semilla)
    if not limpia:
        return None
    sugs = sugerencias_google(limpia)
    if not sugs:
        return None
    lista = "; ".join(sugs)
    return {"type": "text", "text":
        "BUSQUEDAS REALES EN GOOGLE (autocomplete, hl=es) para orientar el SEO — la gente "
        "busca cosas asi: " + lista + ". Usa estas palabras clave con naturalidad en "
        "web_titulo y web_desc SOLO si encajan y son CIERTAS para este producto. Son pistas "
        "de fraseo, NO datos: no inventes ni fuerces, el rigor manda."}

def redactar(f, instruccion=None, incluir_geo=False):
    """Redacta la ficha (web+miravia) con Claude a partir del expediente f.
    - instruccion: texto libre del usuario que tiene prioridad sobre el estilo por
      defecto (lo usa robot_redactar en el boton "Regenerar descripcion").
    - incluir_geo: si True, usa el prompt con la cola GEO (robot_redactar).
    Devuelve el JSON parseado de la respuesta."""
    prompt = PROMPT_SISTEMA_REDACTAR if incluir_geo else PROMPT_SISTEMA
    datos = construir_datos(f)
    contenido = [{"type":"text","text":
        "DATOS (verificados, no anadas nada que no este aqui):\n"+json.dumps(datos,ensure_ascii=False,indent=2)+
        "\n\nLee el numero de coleccion de la imagen de la caja (esquina sup. derecha). Si no se ve claro, no pongas numero."}]
    if instruccion:
        contenido.append({"type":"text","text":"INSTRUCCION DEL USUARIO (tiene prioridad sobre el estilo por defecto, sin romper el rigor ni inventar): "+str(instruccion)})
    # Busquedas reales de Google (best-effort): en Regenerar hay nombre_corto; en Preparar, titulo_keepa.
    blk = bloque_busquedas(f.get('nombre_corto') or f.get('titulo_keepa') or '')
    if blk:
        contenido.append(blk)
    url = foto_caja(f)
    if url:
        try:
            b64 = descargar_b64(url)
            contenido.insert(0, {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}})
        except Exception as e:
            print(f"    (aviso: no pude bajar la imagen, redacto sin ella: {e})")
    msg = cliente.messages.create(model=MODELO, max_tokens=1800, system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role":"user","content":contenido}])
    texto = msg.content[0].text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"): texto = texto[4:]
        texto = texto.strip()
    return json.loads(texto)
