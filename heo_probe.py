#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# HEO PROBE  -  SOLO para ver la ESTRUCTURA de la API heoGATE (una vez).
# ----------------------------------------------------------------------------
# Lee HEO_USER / HEO_PASS de entorno (GitHub Secrets), pide un trocito de cada
# endpoint (productos, precios, disponibilidades) e imprime la forma del JSON
# (claves top-level, paginacion, un ejemplo de item). NO hace pedidos, solo GET
# de lectura del catalogo. Con el log de esto se construye el robot definitivo.
# ============================================================================
import os, json, requests
from requests.auth import HTTPBasicAuth

USER = os.environ['HEO_USER']
PASS = os.environ['HEO_PASS']
BASE = os.environ.get('HEO_BASE', 'https://integrate.heo.com/retailer-api/v1')
auth = HTTPBasicAuth(USER, PASS)


def probe(nombre, url, params=None):
    print(f"\n===== {nombre} :: {url} =====", flush=True)
    try:
        r = requests.get(url, auth=auth, params=params or {}, timeout=90,
                         headers={'Accept': 'application/json'})
        print("HTTP", r.status_code)
        ct = r.headers.get('Content-Type', '')
        print("Content-Type:", ct, "| tamano cuerpo:", len(r.content), "bytes")
        if r.status_code != 200:
            print("Cuerpo (primeros 700):", r.text[:700])
            return
        if 'json' not in ct.lower():
            print("No es JSON. Primeros 700:", r.text[:700]); return
        data = r.json()
        if isinstance(data, dict):
            print("Claves top-level:", list(data.keys()))
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"  '{k}': lista de {len(v)} items.")
                    if v:
                        print("   EJEMPLO item[0]:")
                        print("   " + json.dumps(v[0], indent=1, ensure_ascii=False)[:2600])
                elif isinstance(v, dict):
                    print(f"  '{k}' (dict): " + json.dumps(v, ensure_ascii=False)[:500])
                else:
                    print(f"  '{k}': {str(v)[:150]}")
        elif isinstance(data, list):
            print(f"La respuesta es una LISTA de {len(data)} items.")
            if data:
                print("EJEMPLO item[0]:")
                print(json.dumps(data[0], indent=1, ensure_ascii=False)[:2600])
    except Exception as e:
        print("ERROR:", repr(e))


# Limites pequenos (probamos varios nombres de parametro a la vez; los que no
# valgan, la API los ignora). Solo queremos ver la forma, no bajar el catalogo.
peq = {'size': 2, 'limit': 2, 'page': 0, 'pageSize': 2}
probe("PRODUCTS",       f"{BASE}/catalog/products",       peq)
probe("PRICES",         f"{BASE}/catalog/prices",         peq)
probe("AVAILABILITIES", f"{BASE}/catalog/availabilities", peq)
print("\n=== FIN PROBE ===")
