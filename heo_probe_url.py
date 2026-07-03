#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# HEO PROBE URL - vuelca TODOS los campos de un producto para buscar un enlace de ficha
# (url/link/webUrl/permalink/slug...). Solo lee. Credenciales en Secrets HEO_USER/HEO_PASS.
import os, json, requests
from requests.auth import HTTPBasicAuth

USER = os.environ['HEO_USER']
PASS = os.environ['HEO_PASS']
BASE = os.environ.get('HEO_BASE', 'https://integrate.heo.com/retailer-api/v1')
auth = HTTPBasicAuth(USER, PASS)

r = requests.get(f"{BASE}/catalog/products", auth=auth,
                 params={'page': 1, 'pageSize': 2},
                 headers={'Accept': 'application/json'}, timeout=60)
print("HTTP", r.status_code)
data = r.json()
item = (data.get('content') or [{}])[0]

print("\n=== TODAS las claves del producto (nivel 1) ===")
print(list(item.keys()))

# Buscar cualquier clave que huela a enlace, a cualquier nivel
SOSPECHOSAS = ('url', 'link', 'web', 'permalink', 'slug', 'href', 'shop', 'page', 'seo')
print("\n=== Claves que podrían ser un ENLACE (a cualquier profundidad) ===")
def buscar(obj, ruta=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            r2 = f"{ruta}.{k}" if ruta else k
            if any(s in k.lower() for s in SOSPECHOSAS):
                muestra = v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)[:120]
                print(f"  {r2} = {muestra}")
            buscar(v, r2)
    elif isinstance(obj, list) and obj:
        buscar(obj[0], ruta + '[0]')
buscar(item)

print("\n=== Vuelco COMPLETO del producto (por si el enlace no lleva 'url' en el nombre) ===")
print(json.dumps(item, ensure_ascii=False, indent=1)[:6000])
print("\n=== FIN ===")
