# -*- coding: utf-8 -*-
"""
EXPLORADOR BEMS v2 - rutas y parametros REALES (confirmados en Swagger 16-jun):
  GET /PRODUCT-LIST-MANUFACTURER   -> marcas (ID_MAN, NAME_MAN, COUNT_PRODUCT_IN_MAN)
  GET /PRODUCT-LIST-FILTER         -> productos, filtros MANUFACTURER/AVAILABLE/NEWS/LIMIT/PAGE/DETAILS/LANGUE

Objetivo de esta corrida:
  1) Bajar la lista de marcas y ver cuantas hay + el conteo de Funko.
  2) Pedir Funko con AVAILABLE=1 (solo disponible) y LIMIT pequeno, para confirmar
     que el STOCK viene >0 y que los campos (EAN, PRICE, NAME_MAN, STOCK) estan ahi.
NO toca nada del escaner. Imprime estructuras, nunca credenciales.
"""
import os, sys, json
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
from curl_cffi import requests as curl_requests

BASE = "https://www.probems.be/API"
IMP = "chrome120"

LOGIN = os.environ.get("BEMS_LOGIN"); PWD = os.environ.get("BEMS_PASSWORD"); SK = os.environ.get("BEMS_SECRET_KEY")
if not (LOGIN and PWD and SK):
    print("ERROR: faltan secrets BEMS_*"); sys.exit(1)

print(">>> Token...")
rt = curl_requests.post(f"{BASE}/TOKEN", data={"login":LOGIN,"password":PWD,"secret_key":SK},
                        headers={"Content-Type":"application/x-www-form-urlencoded"}, impersonate=IMP, timeout=30)
if rt.status_code != 200 or "access_token" not in (rt.text or ""):
    print("ERROR token:", rt.status_code, rt.text[:200]); sys.exit(1)
TOK = rt.json()["access_token"]; print(f">>> Token OK (len {len(TOK)})")
H = {"accept":"application/json", "authorization": f"Bearer {TOK}"}

def get(ep, params=None):
    try:
        r = curl_requests.get(f"{BASE}/{ep}", params=params or {}, headers=H, impersonate=IMP, timeout=60)
    except Exception as ex:
        return None, f"EXC: {ex}"
    try: return r.status_code, r.json()
    except Exception: return r.status_code, (r.text or "")[:200]

# 1) MARCAS
st, raw = get("PRODUCT-LIST-MANUFACTURER")
print(f"\n===== PRODUCT-LIST-MANUFACTURER: HTTP {st} =====")
if st == 200 and isinstance(raw, list):
    print("Total marcas:", len(raw))
    print("Claves del 1er elemento:", list(raw[0].keys()) if raw else "vacio")
    funko = [m for m in raw if str(m.get("NAME_MAN","")).strip().lower() == "funko"]
    print("Marca Funko:", funko[0] if funko else "NO ENCONTRADA con ese nombre exacto")
    # top 15 por numero de productos
    try:
        top = sorted(raw, key=lambda m: int(m.get("COUNT_PRODUCT_IN_MAN") or 0), reverse=True)[:15]
        print("\nTop 15 marcas por nº de productos:")
        for m in top:
            print(f"  {m.get('NAME_MAN')!r:30} -> {m.get('COUNT_PRODUCT_IN_MAN')}  (ID_MAN={m.get('ID_MAN')})")
    except Exception as e:
        print("No pude ordenar:", e)
else:
    print("Respuesta:", str(raw)[:300])

# 2) FUNKO DISPONIBLE (AVAILABLE=1)
st, raw = get("PRODUCT-LIST-FILTER", {"MANUFACTURER":"Funko","AVAILABLE":"1","LIMIT":"5","DETAILS":"1"})
print(f"\n===== PRODUCT-LIST-FILTER Funko AVAILABLE=1 LIMIT=5: HTTP {st} =====")
if st == 200 and isinstance(raw, list):
    print("Productos devueltos:", len(raw))
    for p in raw:
        print(f"  EAN={p.get('EAN')} | STOCK={p.get('STOCK')} | QTY_DISP={p.get('QTY_DISP')} | "
              f"DISPO={p.get('STATUT_DISPO')!r} | PRICE={p.get('PRICE')} | {str(p.get('NAME_PRODUCT'))[:40]!r}")
    if raw:
        print("\nClaves completas del 1er producto:")
        print(list(raw[0].keys()))
else:
    print("Respuesta:", str(raw)[:300])

# 3) Cuantos Funko disponibles hay en total (LIMIT=0 = sin limite) - solo el conteo
st, raw = get("PRODUCT-LIST-FILTER", {"MANUFACTURER":"Funko","AVAILABLE":"1","LIMIT":"0","DETAILS":"0"})
print(f"\n===== Conteo Funko AVAILABLE=1 (LIMIT=0, DETAILS=0): HTTP {st} =====")
if st == 200 and isinstance(raw, list):
    print("TOTAL Funko disponibles ahora mismo:", len(raw))
    print("Claves sin DETAILS:", list(raw[0].keys()) if raw else "vacio")
else:
    print("Respuesta:", str(raw)[:200])

print("\n=== FIN EXPLORACION BEMS v2 ===")
