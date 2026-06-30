# ============================================================
# DIRECTOR TCG - preparacion de una pasada
# ------------------------------------------------------------
# 1) lee la regla de TCG de la tabla reglas_director
# 2) descarga el Excel de TCG (login + boton, por servidor)
# 3) lo deja en la biblioteca: web_rank/catalogo.xlsx (para la web) y
#    escaner/catalogo.xlsx (para el escaner)
# 4) deja los recados: web (modo aplicar) y escaner (filtros + modo segun --tipo)
#
# Despues, el workflow ejecuta en orden: actualizador web -> escaner.
# Credenciales SOLO en Secrets. Esto NO escanea ni toca Keepa: solo prepara.
# ============================================================
import os, sys, json, argparse
from curl_cffi import requests as cr
from bs4 import BeautifulSoup
from supabase import create_client

ap = argparse.ArgumentParser()
ap.add_argument('--tipo', choices=['diario', 'completo'], default='diario')
TIPO = ap.parse_args().tipo
MODO = 'nuevos' if TIPO == 'diario' else 'todo'

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
BUCKET = 'informes'
XLSX_CT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# 1) Regla de TCG
try:
    regla = sb.table('reglas_director').select('*').eq('proveedor', 'TCG').single().execute().data
except Exception as e:
    print("ERROR leyendo reglas_director:", e); sys.exit(1)
if not regla:
    print("No hay regla para TCG en reglas_director. Fin."); sys.exit(1)
if not regla.get('activo'):
    print("TCG esta desactivado en reglas_director. Nada que hacer."); sys.exit(0)
print(f">>> Regla TCG cargada. Tipo de pasada: {TIPO} -> modo escaner '{MODO}'.")

# 2) Descargar el Excel de TCG (login PrestaShop + boton)
BASE = 'https://tcgfactory.com'
LOGIN_URLS = [f'{BASE}/es/iniciar-sesion', f'{BASE}/es/mi-cuenta']
DOWNLOAD_URL = f'{BASE}/es/module/smcatalog/downloadcatalog?format=excel'
USER, PASS = os.environ.get('TCG_USER'), os.environ.get('TCG_PASS')
if not USER or not PASS:
    print("ERROR: faltan TCG_USER / TCG_PASS."); sys.exit(1)

s = cr.Session(impersonate='chrome120')
form = None
for url in LOGIN_URLS:
    try:
        r = s.get(url, timeout=60)
        soup = BeautifulSoup(r.text, 'html.parser')
        for f in soup.find_all('form'):
            if f.find('input', {'type': 'password'}):
                form = f; break
        if form:
            break
    except Exception as e:
        print(f"   AVISO {url}: {e}")
if not form:
    print("ERROR: no encuentro el login de TCG (¿Cloudflare/captcha?)."); sys.exit(1)

action = form.get('action') or LOGIN_URLS[0]
if action.startswith('/'):
    action = BASE + action
data = {inp.get('name'): inp.get('value', '') for inp in form.find_all('input') if inp.get('name')}
data['email'] = USER; data['password'] = PASS; data['submitLogin'] = '1'
s.post(action, data=data, timeout=60)

r3 = s.get(DOWNLOAD_URL, timeout=180)
contenido = r3.content
if contenido[:2] != b'PK':
    print("ERROR: la descarga NO es un Excel (login caducado o error)."); sys.exit(1)
print(f">>> Catalogo TCG descargado: {len(contenido)} bytes")

# 3) Dejar el catalogo en la biblioteca
sb.storage.from_(BUCKET).upload('web_rank/catalogo.xlsx', contenido,
                                {'upsert': 'true', 'content-type': XLSX_CT})
# Limpiar escaner/ (como hace el boton) sin tocar escaner_ckpt/ (carpeta aparte)
try:
    viejos = sb.storage.from_(BUCKET).list('escaner') or []
    borrar = [f'escaner/{o["name"]}' for o in viejos
              if o.get('name') and not o['name'].startswith('.')]
    if borrar:
        sb.storage.from_(BUCKET).remove(borrar)
except Exception as e:
    print("AVISO limpiando escaner/:", e)
sb.storage.from_(BUCKET).upload('escaner/catalogo.xlsx', contenido,
                                {'upsert': 'true', 'content-type': XLSX_CT})
print(">>> Catalogo dejado en web_rank/ y escaner/")

# 4) Recados
# Web: aplicar (despublica agotados/stock<2 + reprecia + reconstruye web)
sb.storage.from_(BUCKET).upload('actualizar_tcg/_solicitud.json',
                                json.dumps({'modo': 'aplicar'}).encode(),
                                {'upsert': 'true', 'content-type': 'application/json'})
# Escaner: filtros de la regla + modo segun tipo
recado_esc = {
    'proveedor': 'TCG',
    'modo': MODO,
    'rank_maximo': regla.get('rank_maximo', 50000),
    'filtros': {
        'marcas': regla.get('marcas', []),
        'marcas_es': regla.get('marcas_es', []),
        'col_idioma': regla.get('col_idioma'),
        'incluir_estados': regla.get('incluir_estados', []),
    },
}
sb.storage.from_(BUCKET).upload('escaner/_solicitud_escaner.json',
                                json.dumps(recado_esc, ensure_ascii=False).encode('utf-8'),
                                {'upsert': 'true', 'content-type': 'application/json'})
print(f">>> Recados puestos. Escaner en modo '{MODO}'.")
print(">>> PREP OK. El workflow seguira con: actualizar web -> escanear.")
