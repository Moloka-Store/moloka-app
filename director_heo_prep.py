#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# DIRECTOR HEO - preparacion de una pasada
# ------------------------------------------------------------
# 1) lee la regla HEO de reglas_director (marcas + token 'OFERTAS')
# 2) descarga y cruza el catalogo HEO por API (descargar_heo)
# 3) PRE-FILTRA: solo 'disponible' y (marca en la lista  O  (token 'OFERTAS' y en_oferta=SI))
# 4) deja el catalogo filtrado COMPRIMIDO en escaner/catalogo.csv.gz + recado (marca=TODAS,
#    porque ya viene pre-filtrado: el escaner lo escanea entero con el perfil HEO)
# Despues el workflow ejecuta el escaner FBA. NO toca web. Credenciales SOLO en Secrets.
# ============================================================
import os, sys, json, gzip, argparse, io, csv
from supabase import create_client
from descargar_heo import descargar_catalogo_heo, COLS

ap = argparse.ArgumentParser()
ap.add_argument('--tipo', choices=['diario', 'completo'], default='diario')
TIPO = ap.parse_args().tipo
MODO = 'nuevos' if TIPO == 'diario' else 'todo'

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
BUCKET = 'informes'

# 1) Regla HEO
try:
    regla = sb.table('reglas_director').select('*').eq('proveedor', 'HEO').single().execute().data
except Exception as e:
    print("ERROR leyendo reglas_director (¿existe la fila HEO?):", e); sys.exit(1)
if not regla:
    print("No hay regla para HEO en reglas_director. Fin."); sys.exit(1)
if not regla.get('activo'):
    print("HEO esta desactivado en reglas_director. Nada que hacer."); sys.exit(0)

marcas = regla.get('marcas') or ['Funko']
quiere_ofertas = any(str(m).strip().upper() == 'OFERTAS' for m in marcas)
marcas_reales = [str(m).strip() for m in marcas if str(m).strip().upper() != 'OFERTAS']
rank_max = regla.get('rank_maximo', 30000)
print(f">>> Regla HEO. Tipo {TIPO} -> modo '{MODO}'. Marcas: {marcas_reales} | ofertas: {quiere_ofertas} | rank<= {rank_max}")

# 2) Descargar + cruzar el catalogo HEO por API (los 3 endpoints)
filas = descargar_catalogo_heo()

# 3) Pre-filtrar: servible + (marca en la lista  O  oferta si se pidio)
def _quiere(f):
    if f.get('estado') != 'disponible':
        return False
    m = (f.get('marca') or '').lower()
    if any(mr.lower() in m for mr in marcas_reales):
        return True
    if quiere_ofertas and f.get('en_oferta') == 'SI':
        return True
    return False

sel = [f for f in filas if _quiere(f)]
print(f">>> Seleccionados {len(sel)} de {len(filas)} " +
      f"(marcas {marcas_reales}" + (" + ofertas" if quiere_ofertas else "") + ")")
if not sel:
    print("HEO: nada que escanear tras el filtro. Fin."); sys.exit(0)

# CSV en memoria con las columnas del perfil (mismas que descargar_heo)
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=COLS, delimiter=';', extrasaction='ignore')
w.writeheader()
for f in sel:
    w.writerow(f)
contenido = buf.getvalue().encode('utf-8-sig')

# 4) Limpiar buzon (SIN tocar escaner_ckpt/) + subir comprimido + recado
try:
    viejos = sb.storage.from_(BUCKET).list('escaner') or []
    borrar = [f'escaner/{o["name"]}' for o in viejos if o.get('name') and not o['name'].startswith('.')]
    if borrar:
        sb.storage.from_(BUCKET).remove(borrar)
except Exception as e:
    print("AVISO limpiando escaner/:", e)

contenido_gz = gzip.compress(contenido)
sb.storage.from_(BUCKET).upload('escaner/catalogo.csv.gz', contenido_gz,
                                {'upsert': 'true', 'content-type': 'application/gzip'})
print(f">>> Catalogo HEO filtrado en escaner/catalogo.csv.gz ({len(contenido_gz)} bytes comprimidos)")

recado_esc = {
    'proveedor': 'HEO',
    'marca': 'TODAS',        # ya pre-filtrado en el prep -> escanear todo lo subido
    'modo': MODO,
    'rank_maximo': rank_max,
}
sb.storage.from_(BUCKET).upload('escaner/_solicitud_escaner.json',
                                json.dumps(recado_esc, ensure_ascii=False).encode('utf-8'),
                                {'upsert': 'true', 'content-type': 'application/json'})
print(f">>> Recado puesto. Escaner HEO modo '{MODO}', marca TODAS (pre-filtrado), rank<= {rank_max}.")
print(">>> PREP OK. El workflow seguira con: escanear FBA.")
