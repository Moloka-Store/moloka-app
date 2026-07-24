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
CARPETA_ESCANER = os.environ.get('CARPETA_ESCANER') or 'escaner'   # buzon propio por director
CARPETA_CKPT    = os.environ.get('CARPETA_CKPT') or 'escaner_ckpt'  # checkpoint propio por director


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

# 1.5) ¿Reanudacion de un escaneo a medias? (CONGELADO DE CATALOGO, igual que TCG)
# Si el escaner se corto y se relanza, quedan checkpoints FRESCOS en CARPETA_CKPT.
# En ese caso NO re-descargamos el catalogo: el buzon (escaner_heo/) ya tiene el
# catalogo y el recado de la corrida que se reanuda -> el _ckpt_id no cambia y la
# caja de rank se reconoce (0 tokens). Un checkpoint viejo (>7h) = huerfano: se limpia.
from datetime import datetime, timezone
_frescos, _viejos = [], []
try:
    _ck = sb.storage.from_(BUCKET).list(CARPETA_CKPT) or []
    for o in _ck:
        nm = o.get('name', '')
        if not (nm.startswith('_ckpt_') or nm.startswith('_rankcache_')):
            continue
        _ts = o.get('updated_at') or o.get('created_at')
        es_viejo = True
        if _ts:
            try:
                _dt = datetime.fromisoformat(str(_ts).replace('Z', '+00:00'))
                es_viejo = (datetime.now(timezone.utc) - _dt).total_seconds() / 3600 >= 7
            except Exception:
                es_viejo = False
        (_viejos if es_viejo else _frescos).append(nm)
except Exception as e:
    print("AVISO comprobando checkpoint:", e)

if _frescos:
    print(f">>> Reanudacion detectada: checkpoint fresco ({_frescos}).")
    print(">>> NO re-descargo el catalogo: lo dejo CONGELADO. El workflow seguira con: escanear.")
    sys.exit(0)
if _viejos:
    print(f">>> Limpio {len(_viejos)} checkpoint(s) huerfano(s) (>7h): {_viejos}")
    try:
        sb.storage.from_(BUCKET).remove([f'{CARPETA_CKPT}/{n}' for n in _viejos])
    except Exception as e:
        print("AVISO limpiando huerfanos:", e)

# 2) Descargar + cruzar el catalogo HEO por API (los 3 endpoints).
#    con_chase=True -> los Funko chase se desvian a 'chase' (no cruzan por EAN).
filas, chase = descargar_catalogo_heo(con_chase=True)

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

# 3.5) Refrescar la puente de Funko chase (ASIN manual). Upsert SIN 'asin': los nuevos
#      nacen con asin NULL (pendientes) y los que Fernando ya relleno conservan su ASIN.
#      Va ANTES del corte por 'sel' para refrescar la puente aunque no haya nada servible.
if chase:
    ahora = datetime.now(timezone.utc).isoformat()
    payload = []
    for c in chase:
        r = {k: c.get(k) for k in ('producto_heo', 'nombre', 'ean_caja', 'marca',
                                   'precio_caja', 'estado', 'imagen', 'link_amazon')}
        r['fecha'] = ahora
        payload.append(r)
    try:
        n_ok = 0
        for i in range(0, len(payload), 500):
            sb.table('escaner_chase_asin').upsert(payload[i:i+500], on_conflict='producto_heo').execute()
            n_ok += len(payload[i:i+500])
        print(f">>> Puente chase Funko actualizada: {n_ok} (asin preservado; nuevos = pendientes).")
    except Exception as e:
        print("AVISO: no se pudo actualizar escaner_chase_asin (sigo con el catalogo):", e)
else:
    print(">>> Sin Funko chase detectados en esta pasada.")

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
    viejos = sb.storage.from_(BUCKET).list(CARPETA_ESCANER) or []
    borrar = [f'{CARPETA_ESCANER}/{o["name"]}' for o in viejos if o.get('name') and not o['name'].startswith('.')]
    if borrar:
        sb.storage.from_(BUCKET).remove(borrar)
except Exception as e:
    print("AVISO limpiando escaner/:", e)

contenido_gz = gzip.compress(contenido)
sb.storage.from_(BUCKET).upload(f'{CARPETA_ESCANER}/catalogo.csv.gz', contenido_gz,
                                {'upsert': 'true', 'content-type': 'application/gzip'})
print(f">>> Catalogo HEO filtrado en escaner/catalogo.csv.gz ({len(contenido_gz)} bytes comprimidos)")

recado_esc = {
    'proveedor': 'HEO',
    'marca': 'TODAS',        # ya pre-filtrado en el prep -> escanear todo lo subido
    'modo': MODO,
    'rank_maximo': rank_max,
}
sb.storage.from_(BUCKET).upload(f'{CARPETA_ESCANER}/_solicitud_escaner.json',
                                json.dumps(recado_esc, ensure_ascii=False).encode('utf-8'),
                                {'upsert': 'true', 'content-type': 'application/json'})
print(f">>> Recado puesto. Escaner HEO modo '{MODO}', marca TODAS (pre-filtrado), rank<= {rank_max}.")
print(">>> PREP OK. El workflow seguira con: escanear FBA.")
