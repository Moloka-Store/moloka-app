#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# DIRECTOR DBLINE - preparacion de una pasada (clon del de TCG, sin paso web)
# ------------------------------------------------------------
# 1) lee la regla de DBLINE de reglas_director
# 2) descarga el Excel de DBLine por servidor (login + POST)
# 3) lo deja en el buzon del escaner: escaner/catalogo.xlsx
# 4) deja el recado: filtros (marcas Funko+Pyramid) + modo segun --tipo
# Despues el workflow ejecuta el escaner FBA. NO toca web. NO usa Keepa aqui.
# Credenciales SOLO en Secrets.
# ============================================================
import os, sys, json, argparse
from supabase import create_client
from descargar_dbline import descargar_catalogo_dbline

ap = argparse.ArgumentParser()
ap.add_argument('--tipo', choices=['diario', 'completo'], default='diario')
TIPO = ap.parse_args().tipo
MODO = 'nuevos' if TIPO == 'diario' else 'todo'

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
BUCKET = 'informes'
CARPETA_ESCANER = os.environ.get('CARPETA_ESCANER') or 'escaner'   # buzon propio por director

XLSX_CT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# 1) Regla DBLINE
try:
    regla = sb.table('reglas_director').select('*').eq('proveedor', 'DBLINE').single().execute().data
except Exception as e:
    print("ERROR leyendo reglas_director (¿existe la fila DBLINE?):", e); sys.exit(1)
if not regla:
    print("No hay regla para DBLINE en reglas_director. Fin."); sys.exit(1)
if not regla.get('activo'):
    print("DBLINE esta desactivado en reglas_director. Nada que hacer."); sys.exit(0)
print(f">>> Regla DBLINE cargada. Tipo: {TIPO} -> modo escaner '{MODO}'.")

# 2) Descargar el Excel de DBLine (login + POST). Si falla, corta aqui (no escanea).
contenido = descargar_catalogo_dbline()
print(f">>> Catalogo DBLine descargado: {len(contenido)} bytes")

# 3) Dejar el catalogo en el buzon del escaner (limpiar escaner/ SIN tocar escaner_ckpt/)
try:
    viejos = sb.storage.from_(BUCKET).list(CARPETA_ESCANER) or []
    borrar = [f'{CARPETA_ESCANER}/{o["name"]}' for o in viejos
              if o.get('name') and not o['name'].startswith('.')]
    if borrar:
        sb.storage.from_(BUCKET).remove(borrar)
except Exception as e:
    print("AVISO limpiando escaner/:", e)
sb.storage.from_(BUCKET).upload(f'{CARPETA_ESCANER}/catalogo.xlsx', contenido,
                                {'upsert': 'true', 'content-type': XLSX_CT})
print(">>> Catalogo dejado en escaner/catalogo.xlsx")

# 4) Recado para el escaner (motor de filtros del director)
recado_esc = {
    'proveedor': 'DBLINE',
    'modo': MODO,
    'rank_maximo': regla.get('rank_maximo', 30000),
    'filtros': {
        'marcas': regla.get('marcas') or ['Funko', 'Pyramid'],
        'marcas_es': regla.get('marcas_es') or [],
        'col_idioma': regla.get('col_idioma'),
        'incluir_estados': regla.get('incluir_estados') or [],
    },
}
sb.storage.from_(BUCKET).upload(f'{CARPETA_ESCANER}/_solicitud_escaner.json',
                                json.dumps(recado_esc, ensure_ascii=False).encode('utf-8'),
                                {'upsert': 'true', 'content-type': 'application/json'})
print(f">>> Recado puesto. Escaner DBLINE modo '{MODO}', marcas {recado_esc['filtros']['marcas']}, rank<= {recado_esc['rank_maximo']}.")
print(">>> PREP OK. El workflow seguira con: escanear FBA.")
