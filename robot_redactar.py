# ============================================================================
# ROBOT REDACTAR  -  Circuito Fabrica (boton "Regenerar descripcion", 24-jun)
# ----------------------------------------------------------------------------
# Lee el recado {id, instruccion} -> redacta de nuevo la descripcion de ese
# expediente, anadiendo la instruccion libre del usuario al prompt -> actualiza
# solo los campos de texto (no toca fotos ni estado).
# Prompt y funciones VERBATIM del robot GENERAR.
# Secrets: SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
# ============================================================================
import os, re, sys, json, base64, requests, unicodedata
from supabase import create_client
from anthropic import Anthropic

sys.stdout.reconfigure(line_buffering=True)
RECADO = 'fabrica/_solicitud_redactar.json'

sb      = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
cliente = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
print("Supabase + Anthropic OK")

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

def redactar(f, instruccion=None):
    datos = construir_datos(f)
    contenido = [{"type":"text","text":
        "DATOS (verificados, no anadas nada que no este aqui):\n"+json.dumps(datos,ensure_ascii=False,indent=2)+
        "\n\nLee el numero de coleccion de la imagen de la caja (esquina sup. derecha). Si no se ve claro, no pongas numero."}]
    if instruccion:
        contenido.append({"type":"text","text":"INSTRUCCION DEL USUARIO (tiene prioridad sobre el estilo por defecto, sin romper el rigor ni inventar): "+str(instruccion)})
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
# ===================== MAIN =====================
def main():
    try:
        crudo = sb.storage.from_('informes').download(RECADO)
    except Exception:
        print("SIN recado de redactar. Nada que hacer."); return
    rec = json.loads(crudo.decode('utf-8'))
    fid = rec.get('id'); instr = rec.get('instruccion')
    if not fid:
        print("Recado sin id."); return
    print(f"Regenerar descripcion del expediente {fid} | instruccion: {instr or '(ninguna)'}")

    r = sb.table('fabrica_fichas').select('*').eq('id', fid).execute().data
    if not r:
        print("No existe ese expediente."); return
    f = r[0]
    try:
        out = redactar(f, instruccion=instr)
    except Exception as e:
        print(f"ERROR redaccion: {e}"); return
    categoria = out.get('categoria') if out.get('categoria') in CATEGORIAS else f.get('categoria')
    nombre_corto = (out.get('nombre_corto') or '').strip() or f.get('nombre_corto') or f.get('titulo_keepa')
    slug = slugify(out.get('slug') or nombre_corto)
    campos = {'miravia_titulo': out.get('miravia_titulo'), 'miravia_desc': out.get('miravia_desc'),
              'web_titulo': out.get('web_titulo'), 'web_desc': out.get('web_desc'),
              'categoria': categoria, 'fandom': out.get('fandom'),
              'slug': slug, 'nombre_corto': nombre_corto}
    sb.table('fabrica_fichas').update(campos).eq('id', fid).execute()
    # limpiar recado
    try: sb.storage.from_('informes').remove([RECADO])
    except Exception: pass
    print(f"OK -> descripcion regenerada: {nombre_corto[:50]}")

if __name__ == '__main__':
    main()
