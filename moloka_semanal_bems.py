#!/usr/bin/env python3
# ============================================================
# MOLOKA - Repaso SEMANAL de BEMS  (NUBE / GitHub Actions)
# ------------------------------------------------------------
# Una vez por semana (jueves de madrugada) escanea las marcas vigiladas de BEMS
# ENTERAS (modo "todo"), una tras otra, reutilizando el ESCANER NORMAL. Cada
# marca genera su Excel y se registra en la biblioteca de la app, igual que si
# Fernando pulsara el boton "Escanear" 3 veces.
#
# POR QUE EXISTE: el detector diario solo ve cambios en BEMS (precio de compra).
# El repaso semanal RE-EVALUA todo contra los precios de Amazon de HOY, asi caza
# lo que el diario no ve: un producto que en BEMS sigue igual pero que en Amazon
# ha subido de precio y ahora SI es rentable.
#
# COMO FUNCIONA (encadenado, sin tocar el escaner ni duplicar el Excel):
#   Para cada marca:
#     1) deja el recado en el buzon (informes/escaner/_solicitud_escaner.json)
#        con { proveedor:BEMS, marca, modo:'todo', rank_maximo, ... }
#     2) dispara el escaner llamando a la funcion de Vercel /api/disparar
#        (la MISMA puerta que usa el boton de la app; con DISPARO_SECRET)
#     3) ESPERA a que termine, mirando la tabla escaner_resultados: cuando
#        aparece una fila nueva de esa marca (id > baseline), ha acabado.
#     4) pasa a la siguiente marca.
#
# Variables de entorno (GitHub Secrets):
#   SUPABASE_URL, SUPABASE_KEY, DISPARO_SECRET, VERCEL_URL (opcional)
# ============================================================

import os, sys, time, json
from datetime import datetime, timezone

import requests as rq
from supabase import create_client

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# ============================================================
# CONFIG
# ============================================================
PROVEEDOR   = 'BEMS'
MODO        = 'todo'
RANK_MAXIMO = int(os.environ.get('SEM_RANK_MAXIMO', '30000'))

# URL de la funcion de disparo de Vercel (la app real). Se puede sobreescribir
# por entorno por si cambia el dominio.
VERCEL_URL = os.environ.get('VERCEL_URL', 'https://moloka-app.vercel.app').rstrip('/')
DISPARAR_ENDPOINT = f'{VERCEL_URL}/api/disparar'

DISPARO_SECRET = os.environ.get('DISPARO_SECRET')

# Marcas por defecto (mismas que el detector). Si Supabase tiene la lista
# bems_marcas_vigiladas, se usa esa (asi cambian en un sitio).
MARCAS_DEFAULT = ['Funko', 'Bandai Model Kit', 'Pyramid Int.']

# Tiempos de espera
ESPERA_POLL_SEG   = 60          # cada cuanto consulto si termino la marca
MAX_ESPERA_MARCA  = 4 * 60 * 60 # 4h tope por marca (catalogo grande + goteo Keepa)
PAUSA_ENTRE_MARCAS = 30         # respiro entre una marca y la siguiente

BUCKET = 'informes'
CARPETA_ESCANER = 'escaner'
RECADO = '_solicitud_escaner.json'

# ============================================================
# CLIENTES
# ============================================================
print(">>> ARRANCANDO repaso semanal BEMS. Conectando Supabase...", flush=True)
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

if not DISPARO_SECRET:
    print("ERROR: falta DISPARO_SECRET en el entorno. No puedo disparar el escaner. Fin.")
    sys.exit(1)

# ============================================================
# HELPERS
# ============================================================
def leer_marcas_vigiladas():
    try:
        res = sb.table('app_datos').select('contenido').eq('clave','bems_marcas_vigiladas').execute()
        if res.data:
            cont = res.data[0]['contenido']
            if isinstance(cont, dict) and isinstance(cont.get('marcas'), list):
                marcas = [str(m).strip() for m in cont['marcas'] if str(m).strip()]
            elif isinstance(cont, list):
                marcas = [str(m).strip() for m in cont if str(m).strip()]
            else:
                marcas = []
            if marcas:
                print(f"Marcas vigiladas (Supabase): {marcas}")
                return marcas
    except Exception as ex:
        print("AVISO: no se pudo leer bems_marcas_vigiladas, uso lista por defecto:", ex)
    print(f"Marcas vigiladas (por defecto): {MARCAS_DEFAULT}")
    return MARCAS_DEFAULT

def max_id_resultados():
    """Mayor id actual en escaner_resultados (baseline para detectar la fila nueva)."""
    try:
        res = sb.table('escaner_resultados').select('id').order('id', desc=True).limit(1).execute()
        if res.data:
            return int(res.data[0]['id'])
    except Exception as ex:
        print("AVISO al leer max id de escaner_resultados:", ex)
    return 0

def vaciar_buzon_escaner():
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA_ESCANER) or []
        borrar = [f'{CARPETA_ESCANER}/{o["name"]}' for o in objs
                  if o.get('name') and not o['name'].startswith('.')]
        if borrar:
            sb.storage.from_(BUCKET).remove(borrar)
    except Exception as ex:
        print("AVISO al vaciar el buzon del escaner:", ex)

def dejar_recado(marca):
    recado = {'proveedor': PROVEEDOR, 'marca': marca, 'modo': MODO,
              'rank_maximo': RANK_MAXIMO, 'incluir_sin_rank': False,
              'fecha': datetime.now(timezone.utc).isoformat()}
    data = json.dumps(recado).encode('utf-8')
    sb.storage.from_(BUCKET).upload(
        f'{CARPETA_ESCANER}/{RECADO}', data,
        {'content-type': 'application/json', 'upsert': 'true'})

def disparar_escaner():
    """Llama a la funcion de Vercel (misma puerta que el boton de la app)."""
    try:
        r = rq.post(DISPARAR_ENDPOINT,
                    json={'secreto': DISPARO_SECRET, 'workflow': 'escaner-app.yml'},
                    timeout=30)
        return r.status_code, (r.json() if r.headers.get('content-type','').startswith('application/json') else {})
    except Exception as ex:
        return None, {'error': str(ex)}

def esperar_a_que_termine(baseline_id, marca):
    """Espera hasta que aparezca una fila nueva en escaner_resultados (id>baseline).
    Devuelve True si termino, False si se agoto el tiempo."""
    t0 = time.time()
    while time.time() - t0 < MAX_ESPERA_MARCA:
        time.sleep(ESPERA_POLL_SEG)
        nuevo = max_id_resultados()
        if nuevo > baseline_id:
            print(f"  -> '{marca}' TERMINO (nueva fila id={nuevo} en la biblioteca).")
            return True
        mins = int((time.time()-t0)/60)
        print(f"  ... '{marca}' aun en marcha ({mins} min). Esperando...")
    print(f"  ATENCION: '{marca}' no termino en {MAX_ESPERA_MARCA//3600}h. Sigo con la siguiente.")
    return False

# ============================================================
# MAIN: encadenar las marcas
# ============================================================
def main():
    marcas = leer_marcas_vigiladas()
    print(f">>> Repaso semanal de {len(marcas)} marcas BEMS (modo '{MODO}', rank<= {RANK_MAXIMO}).")
    resumen = []

    for i, marca in enumerate(marcas, 1):
        print(f"\n===== [{i}/{len(marcas)}] MARCA: {marca} =====")

        # esperar a que no haya OTRA corrida del escaner en marcha (la barrera de
        # Vercel devuelve 409; reintentamos unas cuantas veces con pausa)
        baseline = max_id_resultados()
        vaciar_buzon_escaner()
        try:
            dejar_recado(marca)
        except Exception as ex:
            print(f"  ERROR dejando el recado de '{marca}': {ex}. Se salta.")
            resumen.append((marca, 'error recado'))
            continue

        # disparar (reintentando si hay otra corrida en marcha -> 409)
        lanzado = False
        for intento in range(1, 11):   # hasta 10 intentos, 60s entre ellos
            code, data = disparar_escaner()
            if code == 200:
                print(f"  Escaner lanzado para '{marca}'.")
                lanzado = True
                break
            elif code == 409:
                print(f"  Hay otra corrida en marcha (intento {intento}/10). Espero 60s...")
                time.sleep(60)
            else:
                print(f"  AVISO disparo '{marca}': HTTP {code} {data}. Reintento en 60s...")
                time.sleep(60)
        if not lanzado:
            print(f"  No se pudo lanzar '{marca}' tras varios intentos. Se salta.")
            resumen.append((marca, 'no lanzado'))
            continue

        # dar un margen para que la corrida arranque y registre antes de mirar
        time.sleep(45)
        ok = esperar_a_que_termine(baseline, marca)
        resumen.append((marca, 'OK' if ok else 'timeout'))
        time.sleep(PAUSA_ENTRE_MARCAS)

    print("\n===== RESUMEN DEL REPASO SEMANAL =====")
    for marca, estado in resumen:
        print(f"  {marca}: {estado}")
    print("Los Excels estan en la biblioteca de escaneos de la app.")
    print("=== REPASO SEMANAL BEMS FIN ===")

if __name__ == '__main__':
    main()
