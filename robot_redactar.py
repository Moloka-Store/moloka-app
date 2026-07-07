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
# Cerebro de redaccion centralizado (prompt + funciones). redactar() usa aqui
# incluir_geo=True para conservar la cola GEO (citabilidad por IAs) que este robot ya tenia.
from fabrica_cerebro import CATEGORIAS, slugify, redactar

sys.stdout.reconfigure(line_buffering=True)
RECADO = 'fabrica/_solicitud_redactar.json'

sb      = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print("Supabase + Anthropic OK")

# ===================== REDACCION -> centralizada en fabrica_cerebro.py =====================
# El prompt (con cola GEO), CATEGORIAS, slugify y redactar se importan arriba.

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
        out = redactar(f, instruccion=instr, incluir_geo=True)
    except Exception as e:
        print(f"ERROR redaccion: {e}"); return
    categoria = out.get('categoria') if out.get('categoria') in CATEGORIAS else f.get('categoria')
    nombre_corto = (out.get('nombre_corto') or '').strip() or f.get('nombre_corto') or f.get('titulo_keepa')
    slug = slugify(out.get('slug') or nombre_corto)
    campos = {'miravia_titulo': out.get('miravia_titulo'), 'miravia_desc': out.get('miravia_desc'),
              'web_titulo': out.get('web_titulo'), 'web_desc': out.get('web_desc'),
              'categoria': categoria, 'fandom': out.get('fandom'),
              'slug': slug, 'nombre_corto': nombre_corto,
              'sinonimos': out.get('sinonimos'), 'alt': out.get('alt')}
    sb.table('fabrica_fichas').update(campos).eq('id', fid).execute()
    # limpiar recado
    try: sb.storage.from_('informes').remove([RECADO])
    except Exception: pass
    print(f"OK -> descripcion regenerada: {nombre_corto[:50]}")

if __name__ == '__main__':
    main()
