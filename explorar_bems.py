# -*- coding: utf-8 -*-
"""
EXPLORADOR de la API de BEMS — endpoints de LISTADO.

Objetivo: descubrir, contra la API REAL (no la doc, que miente), CÓMO se listan
los productos de una marca, para poder montar el cliente BEMS del escáner.

Responde a estas preguntas:
  1) LIST-MANUFACTURER  -> ¿qué marcas/fabricantes hay y cómo se llaman exactamente?
  2) LIST-CATEGORIES    -> ¿qué categorías hay? (cómic, figuras, textil, etc.)
  3) LIST-PRODUCTS-FILTRED -> ¿se puede filtrar por marca? ¿con qué parámetro?
       ¿qué campos trae cada producto (EAN, precio, stock, nombre)?

NO toca nada del escáner. Solo lee. Imprime estructuras, nunca credenciales.

Variables de entorno (GitHub Secrets): BEMS_LOGIN, BEMS_PASSWORD, BEMS_SECRET_KEY
"""

import os, sys, json
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from curl_cffi import requests as curl_requests

BASE = "https://www.probems.be/API"
IMPERSONATE = "chrome120"   # validado: pasa el Cloudflare de BEMS desde Actions


def pp(titulo, obj, limite=1500):
    """Imprime una estructura recortada y legible."""
    print(f"\n----- {titulo} -----")
    try:
        s = json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        s = str(obj)
    print(s[:limite] + ("  ...[recortado]" if len(s) > limite else ""))


def estructura(titulo, raw):
    """Resume tipo + claves de la respuesta, sin volcarla entera."""
    print(f"\n===== {titulo} =====")
    print("Tipo:", type(raw).__name__)
    if isinstance(raw, list):
        print("Longitud lista:", len(raw))
        if raw:
            print("Tipo del 1er elemento:", type(raw[0]).__name__)
            if isinstance(raw[0], dict):
                print("Claves del 1er elemento:", list(raw[0].keys()))
            pp("Muestra (primeros 3 elementos)", raw[:3])
    elif isinstance(raw, dict):
        print("Claves:", list(raw.keys()))
        pp("Contenido (recorte)", raw)
    else:
        print("Valor:", str(raw)[:300])


# --- 1. Token ---
LOGIN = os.environ.get("BEMS_LOGIN")
PASSWORD = os.environ.get("BEMS_PASSWORD")
SECRET_KEY = os.environ.get("BEMS_SECRET_KEY")
if not (LOGIN and PASSWORD and SECRET_KEY):
    print("ERROR: faltan secrets BEMS_LOGIN / BEMS_PASSWORD / BEMS_SECRET_KEY")
    sys.exit(1)

print(">>> Obteniendo token BEMS...")
rtok = curl_requests.post(
    f"{BASE}/TOKEN",
    data={"login": LOGIN, "password": PASSWORD, "secret_key": SECRET_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    impersonate=IMPERSONATE, timeout=30,
)
if rtok.status_code != 200 or "access_token" not in (rtok.text or ""):
    print(f"ERROR obteniendo token: HTTP {rtok.status_code} | {rtok.text[:200]}")
    sys.exit(1)
TOKEN = rtok.json()["access_token"]
print(f">>> Token OK (longitud {len(TOKEN)}).")

H = {"accept": "application/json", "authorization": f"Bearer {TOKEN}"}


def get(endpoint, params=None):
    """GET con manejo de errores; devuelve (status, objeto_json_o_texto)."""
    try:
        r = curl_requests.get(f"{BASE}/{endpoint}", params=params or {},
                              headers=H, impersonate=IMPERSONATE, timeout=60)
    except Exception as ex:
        return None, f"EXCEPCION: {ex}"
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, (r.text or "")[:300]


# --- 2. LIST-MANUFACTURER (marcas) ---
st, raw = get("LIST-MANUFACTURER")
print(f"\nHTTP LIST-MANUFACTURER: {st}")
if st == 200:
    estructura("LIST-MANUFACTURER", raw)
else:
    print("Respuesta:", raw)

# --- 3. LIST-CATEGORIES (categorias) ---
st, raw = get("LIST-CATEGORIES")
print(f"\nHTTP LIST-CATEGORIES: {st}")
if st == 200:
    estructura("LIST-CATEGORIES", raw)
else:
    print("Respuesta:", raw)

# --- 4. LIST-PRODUCTS-FILTRED: tanteamos parametros (la doc no los documenta) ---
# Probamos distintos nombres de parametro para filtrar por marca 'Funko',
# en MAYUSCULAS (la API de BEMS exige mayusculas en los query params).
# Solo queremos ver la ESTRUCTURA (campos por producto) y si el filtro funciona,
# asi que NO hace falta traer el catalogo entero; pedimos limite si lo acepta.
print("\n\n########## LIST-PRODUCTS-FILTRED ##########")
intentos = [
    {"MANUFACTURER": "Funko"},
    {"FABRICANT": "Funko"},
    {"NAME_MAN": "Funko"},
    {"MANUFACTURER": "Funko", "PAGE": "1", "LIMIT": "5"},
    {"MANUFACTURER": "Funko", "PAGE": "1"},
    {},   # sin filtro, por ver si devuelve algo y con que forma (ojo: puede ser grande)
]
for i, params in enumerate(intentos, 1):
    st, raw = get("LIST-PRODUCTS-FILTRED", params)
    n = len(raw) if isinstance(raw, list) else ("dict" if isinstance(raw, dict) else "?")
    print(f"\n--- Intento {i}: params={params} -> HTTP {st} | elementos={n} ---")
    if st == 200 and isinstance(raw, list) and raw:
        print("Claves del 1er producto:", list(raw[0].keys()) if isinstance(raw[0], dict) else type(raw[0]).__name__)
        pp("Primeros 2 productos", raw[:2], limite=1200)
        # si este filtro funciono, no hace falta seguir probando nombres de parametro
        if i <= 3:
            print(">>> Este nombre de parametro PARECE valido. (seguimos por ver paginacion)")
    elif st == 200 and isinstance(raw, dict):
        print("Devolvio un dict. Claves:", list(raw.keys()))
        pp("Contenido", raw, limite=800)
    else:
        print("Respuesta:", str(raw)[:300])

print("\n=== FIN EXPLORACION BEMS ===")
print("Pega TODO este log en el chat para diseñar el cliente BEMS sobre datos reales.")
