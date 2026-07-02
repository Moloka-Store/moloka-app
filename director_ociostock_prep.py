#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# DIRECTOR OCIOSTOCK - preparacion de una pasada (clon del de DBLine, SIN login)
# ------------------------------------------------------------
# 1) lee la regla OCIOSTOCK de reglas_director
# 2) descarga el feed CSV por URL (Secret OCIOSTOCK_FEED_URL, sin login)
# 3) lo deja COMPRIMIDO en el buzon del escaner: escaner/catalogo.csv.gz
#    (el escaner descomprime gzip solo; el CSV de OcioStock es grande)
# 4) deja el recado: filtros (marcas elegidas) + modo segun --tipo
# Despues el workflow ejecuta el escaner FBA. NO toca web. NO usa Keepa aqui.
# Credenciales/URL SOLO en Secrets.
# ============================================================
import os, sys, json, gzip, argparse
from supabase import create_client
from descargar_ociostock import descargar_catalogo_ociostock

ap = argparse.ArgumentParser()
ap.add_argument('--tipo', choices=['diario', 'completo'], default='diario')
TIPO = ap.parse_args().tipo
MODO = 'nuevos' if TIPO == 'diario' else 'todo'

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
BUCKET = 'informes'

# 1) Regla OCIOSTOCK
try:
    regla = sb.table('reglas_director').select('*').eq('proveedor', 'OCIOSTOCK').single().execute().data
except Exception as e:
    print("ERROR leyendo reglas_director (¿existe la fila OCIOSTOCK?):", e); sys.exit(1)
if not regla:
    print("No hay regla para OCIOSTOCK en reglas_director. Fin."); sys.exit(1)
if not regla.get('activo'):
    print("OCIOSTOCK esta desactivado en reglas_director. Nada que hacer."); sys.exit(0)
print(f">>> Regla OCIOSTOCK cargada. Tipo: {TIPO} -> modo escaner '{MODO}'.")

# 2) Descargar el feed CSV (sin login). Si falla, corta aqui (no escanea).
contenido = descargar_catalogo_ociostock()
print(f">>> Feed OcioStock descargado: {len(contenido)} bytes (CSV plano)")

# 3) Dejar el catalogo COMPRIMIDO en el buzon (limpiar escaner/ SIN tocar escaner_ckpt/)
try:
    viejos = sb.storage.from_(BUCKET).list('escaner') or []
    borrar = [f'escaner/{o["name"]}' for o in viejos
              if o.get('name') and not o['name'].startswith('.')]
    if borrar:
        sb.storage.from_(BUCKET).remove(borrar)
except Exception as e:
    print("AVISO limpiando escaner/:", e)
contenido_gz = gzip.compress(contenido)
sb.storage.from_(BUCKET).upload('escaner/catalogo.csv.gz', contenido_gz,
                                {'upsert': 'true', 'content-type': 'application/gzip'})
print(f">>> Catalogo dejado en escaner/catalogo.csv.gz ({len(contenido_gz)} bytes comprimidos)")

# 4) Recado para el escaner (motor de filtros del director -> varias marcas)
recado_esc = {
    'proveedor': 'OCIOSTOCK',
    'marca': 'Seleccion',                       # etiqueta para la memoria/nombre; el filtro real va en 'filtros'
    'modo': MODO,
    'rank_maximo': regla.get('rank_maximo', 30000),
    'filtros': {
        'marcas': regla.get('marcas') or ['Funko'],
        'marcas_es': regla.get('marcas_es') or [],
        'col_idioma': regla.get('col_idioma'),
        'incluir_estados': regla.get('incluir_estados') or [],
    },
}
sb.storage.from_(BUCKET).upload('escaner/_solicitud_escaner.json',
                                json.dumps(recado_esc, ensure_ascii=False).encode('utf-8'),
                                {'upsert': 'true', 'content-type': 'application/json'})
print(f">>> Recado puesto. Escaner OCIOSTOCK modo '{MODO}', marcas {recado_esc['filtros']['marcas']}, rank<= {recado_esc['rank_maximo']}.")
print(">>> PREP OK. El workflow seguira con: escanear FBA.")
