#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# DESCARGAR HEO  -  Baja el catalogo de la heoGATE Retailer API y lo cruza.
# ----------------------------------------------------------------------------
# 3 endpoints (JSON, Basic Auth, paginacion desde page=1):
#   /catalog/products       -> productNumber, name(ML), barcodes(GTIN=EAN),
#                              manufacturers, categories, media.mainImage, isEndOfLife...
#   /catalog/prices         -> discountedPricePerUnit (mi coste con descuento)
#   /catalog/availabilities -> availabilityState, availableToOrder, availability(GREEN/..)
# Se cruzan por productNumber -> una fila por producto CON EAN.
# El robot que ejecuta suelto = PRUEBA (lista marcas + muestra de cruce).
# El director importa descargar_catalogo_heo() / a_csv_bytes().
# Credenciales SOLO en Secrets: HEO_USER, HEO_PASS.
# ============================================================================
import os, io, csv, sys, time, requests
from requests.auth import HTTPBasicAuth

sys.stdout.reconfigure(line_buffering=True)

USER = os.environ['HEO_USER']
PASS = os.environ['HEO_PASS']
BASE = os.environ.get('HEO_BASE', 'https://integrate.heo.com/retailer-api/v1')
PAGE_SIZE = int(os.environ.get('HEO_PAGE_SIZE', '500'))
IDIOMA = os.environ.get('HEO_IDIOMA', 'ES')   # preferencia de idioma; fallback EN
auth = HTTPBasicAuth(USER, PASS)


def _get(url, page):
    global PAGE_SIZE
    for intento in range(5):
        try:
            r = requests.get(url, auth=auth, params={'page': page, 'pageSize': PAGE_SIZE},
                             headers={'Accept': 'application/json'}, timeout=120)
            if r.status_code == 200:
                return r.json()
            txt = r.text[:180]
            print(f"  HTTP {r.status_code} {url} page {page}: {txt}")
            # Si el pageSize es demasiado grande, lo reduzco y reintento (se estabiliza en la 1a pagina).
            if r.status_code == 400 and 'size' in txt.lower() and PAGE_SIZE > 50:
                PAGE_SIZE = max(50, PAGE_SIZE // 2)
                print(f"  -> reduzco pageSize a {PAGE_SIZE} y reintento")
                continue
        except Exception as e:
            print(f"  error {url} page {page}: {e}")
        time.sleep(3 * (intento + 1))
    return None


def _paginar(endpoint, max_paginas=None):
    url = f"{BASE}/{endpoint}"
    out, page, total = [], 1, None
    while True:
        data = _get(url, page)
        if not data:
            break
        out.extend(data.get('content') or [])
        pag = data.get('pagination') or {}
        total = pag.get('totalPages') or 1
        if page == 1:
            print(f"  {endpoint}: {pag.get('totalElements')} items | {total} paginas | pageSize {pag.get('pageSize')}")
        if max_paginas and page >= max_paginas:
            break
        if page >= total:
            break
        page += 1
    return out


def _trad(lista, idioma=IDIOMA):
    """De [{langIso2, translation}] devuelve la del idioma preferido (o EN, o la 1a)."""
    if not lista:
        return ''
    by = {t.get('langIso2'): t.get('translation') for t in lista if isinstance(t, dict)}
    return by.get(idioma) or by.get('EN') or next(iter(by.values()), '')


def _ean(prod):
    for b in (prod.get('barcodes') or []):
        if str(b.get('type', '')).upper() == 'GTIN' and b.get('barcode'):
            return str(b['barcode']).strip()
    return ''


def _marca(prod):
    ms = prod.get('manufacturers') or []
    return _trad(ms[0].get('translations')) if (ms and isinstance(ms[0], dict)) else ''


def _categoria(prod):
    cs = prod.get('categories') or []
    return _trad(cs[0].get('translations')) if (cs and isinstance(cs[0], dict)) else ''


def descargar_catalogo_heo(max_paginas=None):
    """Baja y cruza los 3 endpoints. Devuelve lista de dicts (una fila por producto CON EAN)."""
    print(">>> Bajando PRODUCTS...", flush=True)
    productos = _paginar('catalog/products', max_paginas)
    print(">>> Bajando PRICES...", flush=True)
    precios = {p.get('productNumber'): p for p in _paginar('catalog/prices', max_paginas)}
    print(">>> Bajando AVAILABILITIES...", flush=True)
    dispo = {a.get('productNumber'): a for a in _paginar('catalog/availabilities', max_paginas)}
    print(f">>> Cruzando: {len(productos)} productos | {len(precios)} precios | {len(dispo)} disponibilidades")

    filas, sin_ean = [], 0
    for prod in productos:
        ean = _ean(prod)
        if not ean:                      # sin GTIN no se puede cruzar con Amazon -> fuera
            sin_ean += 1
            continue
        pn = prod.get('productNumber')
        pr = precios.get(pn) or {}
        av = dispo.get(pn) or {}
        dpu = pr.get('discountedPricePerUnit') or pr.get('basePricePerUnit') or {}
        # Servible = se puede pedir (aunque sea fin de vida, si hay stock: decision de Fernando).
        orderable = bool(av.get('availableToOrder')) and str(av.get('availabilityState', '')).upper() == 'AVAILABLE'
        img = ((prod.get('media') or {}).get('mainImage') or {}).get('url') or ''
        filas.append({
            'productNumber':  pn,
            'ean':            ean,
            'nombre':         _trad(prod.get('name')),
            'marca':          _marca(prod),
            'categoria':      _categoria(prod),
            'precio':         (dpu.get('amount') or ''),
            'estado':         ('disponible' if orderable else 'agotado'),
            'disponibilidad': (av.get('availability') or ''),        # GREEN / YELLOW / RED
            'imagen':         img,
            'fin_de_vida':    ('SI' if prod.get('isEndOfLife') else ''),
            'preorder':       ('SI' if prod.get('preorderDeadline') else ''),
        })
    print(f">>> Catalogo cruzado: {len(filas)} filas con EAN (descartadas {sin_ean} sin GTIN)")
    return filas


COLS = ['productNumber', 'ean', 'nombre', 'marca', 'categoria', 'precio', 'estado',
        'disponibilidad', 'imagen', 'fin_de_vida', 'preorder']


def a_csv_bytes(filas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    w.writeheader()
    for f in filas:
        w.writerow(f)
    return buf.getvalue().encode('utf-8-sig')


if __name__ == '__main__':
    from collections import Counter

    if os.environ.get('HEO_FULL'):
        # ===== MODO COMPLETO: catalogo entero + EANs para el Visualizador =====
        filas = descargar_catalogo_heo()
        with open('heo_catalogo.csv', 'wb') as fh:
            fh.write(a_csv_bytes(filas))
        # EANs SERVIBLES (disponible), sin repetir, en tandas de 10.000 para el Visualizador.
        eans = list(dict.fromkeys(f['ean'] for f in filas if f['estado'] == 'disponible'))
        TANDA = int(os.environ.get('HEO_TANDA', '10000'))
        n_tandas = (len(eans) + TANDA - 1) // TANDA
        for i in range(n_tandas):
            with open(f'heo_eans_{i+1}.txt', 'w') as fh:
                fh.write('\n'.join(eans[i*TANDA:(i+1)*TANDA]))
        print(f"\n>>> heo_catalogo.csv: {len(filas)} filas")
        print(f">>> EANs servibles: {len(eans)} -> {n_tandas} tandas de <= {TANDA} (heo_eans_1.txt ...)")
        marcas = Counter(f['marca'] for f in filas if f['marca'])
        print(f"\n=== {len(marcas)} marcas en el catalogo servible. TOP 40 ===")
        for m, k in marcas.most_common(40):
            print(f"  {k:5}  {m}")
        print("\n=== FIN MODO COMPLETO ===")
    else:
        # ===== MODO PRUEBA: descubre marcas + muestra de cruce =====
        print(">>> DESCUBRIMIENTO de marcas (bajando todos los productos)...", flush=True)
        prods = _paginar('catalog/products')
        marcas = Counter(_marca(p) for p in prods if _marca(p))
        con_ean = sum(1 for p in prods if _ean(p))
        print(f"\n=== {len(prods)} productos ({con_ean} con EAN GTIN) | {len(marcas)} marcas distintas ===")
        print("=== TOP 50 marcas por nº de referencias ===")
        for m, k in marcas.most_common(50):
            print(f"  {k:5}  {m}")
        print("\n>>> MUESTRA de cruce (2 paginas)...")
        filas = descargar_catalogo_heo(max_paginas=2)
        print(f"=== {min(8, len(filas))} filas de muestra ===")
        for f in filas[:8]:
            print(f"  {f['ean']} | {f['marca'][:22]:22} | {str(f['precio']):>7} EUR | {f['estado']:11} | fdv={f['fin_de_vida'] or '-'} | {f['nombre'][:40]}")
        print("\n=== FIN PRUEBA HEO ===")
