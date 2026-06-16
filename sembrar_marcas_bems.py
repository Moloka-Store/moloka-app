# -*- coding: utf-8 -*-
"""
SIEMBRA DE MARCAS BEMS -> Supabase (app_datos['bems_marcas']).

Baja la lista de marcas de BEMS (PRODUCT-LIST-MANUFACTURER) con su conteo de
productos y la guarda en la tabla app_datos, clave 'bems_marcas', para que el
desplegable de marcas de la app pueda leerla (el navegador no puede llamar a BEMS).

Cuesta ~1 token de BEMS y 0 de Keepa. Reutilizable para refrescar marcas.

Variables de entorno (GitHub Secrets):
  BEMS_LOGIN, BEMS_PASSWORD, BEMS_SECRET_KEY, SUPABASE_URL, SUPABASE_KEY
"""
import os, sys, json
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
from curl_cffi import requests as curl_requests
from supabase import create_client
from datetime import datetime, timezone

BASE = "https://www.probems.be/API"
IMP = "chrome120"

LOGIN = os.environ.get("BEMS_LOGIN"); PWD = os.environ.get("BEMS_PASSWORD"); SK = os.environ.get("BEMS_SECRET_KEY")
SUPA_URL = os.environ.get("SUPABASE_URL"); SUPA_KEY = os.environ.get("SUPABASE_KEY")
if not (LOGIN and PWD and SK):
    print("ERROR: faltan secrets BEMS_*"); sys.exit(1)
if not (SUPA_URL and SUPA_KEY):
    print("ERROR: faltan secrets SUPABASE_URL / SUPABASE_KEY"); sys.exit(1)

# --- Token BEMS ---
print(">>> Token BEMS...")
rt = curl_requests.post(f"{BASE}/TOKEN", data={"login":LOGIN,"password":PWD,"secret_key":SK},
                        headers={"Content-Type":"application/x-www-form-urlencoded"}, impersonate=IMP, timeout=30)
if rt.status_code != 200 or "access_token" not in (rt.text or ""):
    print("ERROR token:", rt.status_code, rt.text[:200]); sys.exit(1)
TOK = rt.json()["access_token"]; print(f">>> Token OK (len {len(TOK)})")
H = {"accept":"application/json", "authorization": f"Bearer {TOK}"}

# --- Lista de marcas ---
print(">>> Bajando PRODUCT-LIST-MANUFACTURER...")
r = curl_requests.get(f"{BASE}/PRODUCT-LIST-MANUFACTURER", headers=H, impersonate=IMP, timeout=60)
if r.status_code != 200:
    print("ERROR lista marcas:", r.status_code, r.text[:200]); sys.exit(1)
raw = r.json()
if not isinstance(raw, list) or not raw:
    print("ERROR: respuesta inesperada:", str(raw)[:200]); sys.exit(1)

# Construir [ [NAME_MAN, count], ... ] ordenado por count desc, solo marcas con conteo>0
marcas = []
for m in raw:
    nombre = str(m.get("NAME_MAN") or "").strip()
    try: n = int(m.get("COUNT_PRODUCT_IN_MAN") or 0)
    except Exception: n = 0
    if nombre and n > 0:
        marcas.append([nombre, n])
marcas.sort(key=lambda x: x[1], reverse=True)
print(f">>> {len(marcas)} marcas con productos. Top 5: {marcas[:5]}")

payload = {"actualizado": datetime.now(timezone.utc).isoformat(), "marcas": marcas}

# --- Guardar en Supabase app_datos ---
print(">>> Guardando en app_datos['bems_marcas']...")
sb = create_client(SUPA_URL, SUPA_KEY)
try:
    sb.table("app_datos").upsert({
        "clave": "bems_marcas",
        "contenido": payload,
        "actualizado": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="clave").execute()
    print(">>> Guardado OK.")
except Exception as ex:
    print("ERROR guardando en Supabase:", ex); sys.exit(1)

# --- Verificar leyendo de vuelta ---
try:
    res = sb.table("app_datos").select("clave,actualizado,contenido").eq("clave","bems_marcas").execute()
    if res.data:
        cont = res.data[0]["contenido"]
        n = len(cont.get("marcas", [])) if isinstance(cont, dict) else "?"
        print(f">>> VERIFICADO en Supabase: {n} marcas guardadas. Actualizado: {res.data[0]['actualizado']}")
    else:
        print("AVISO: no se pudo leer de vuelta (¿permiso select?).")
except Exception as ex:
    print("AVISO verificacion:", ex)

print("=== SIEMBRA DE MARCAS BEMS FIN ===")
