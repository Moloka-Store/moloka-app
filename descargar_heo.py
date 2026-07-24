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
import os, io, csv, sys, time, re, requests
from urllib.parse import quote_plus
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


def _ean_bruto(prod):
    """El PRIMER barcode del producto, sea GTIN o no. Los cases (p.ej. AC/DC Angus)
    traen el codigo de CAJA con type UNDEFINED, que _ean descarta; aqui lo conservamos."""
    for b in (prod.get('barcodes') or []):
        if b.get('barcode'):
            return str(b['barcode']).strip()
    return ''


# Senal de chase Funko, MEDIDA contra el catalogo real (100 productos, 0 escapes):
# CHASE / 5+1 / abreviatura CH (w/CH, w/ CH(BD), (CH), CH(GW)) / "Surtido 6" / "Surtido (6)".
# En HEO, un Funko + surtido de 6 es un case con chase.
_RE_CHASE = re.compile(r'chase|5\s*\+\s*1|w/\s*ch\b|\(\s*ch\s*\)|\bch\s*\(|surtido\s*\(\s*6\s*\)|surtido\s+6\b', re.I)


def _es_funko_chase(prod):
    """True si es Funko y el nombre lleva senal de chase. Los cases NO cruzan por EAN
    (su codigo es de caja): van a la puente escaner_chase_asin para ASIN manual."""
    if 'FUNKO' not in (_marca(prod) or '').upper():
        return False
    return bool(_RE_CHASE.search(_trad(prod.get('name')) or ''))


def _marca(prod):
    ms = prod.get('manufacturers') or []
    return _trad(ms[0].get('translations')) if (ms and isinstance(ms[0], dict)) else ''


def _categoria(prod):
    cs = prod.get('categories') or []
    return _trad(cs[0].get('translations')) if (cs and isinstance(cs[0], dict)) else ''


def _amt(d):
    """amount de un dict de precio {amount, currencyIsoCode}, o None."""
    if isinstance(d, dict):
        v = d.get('amount')
        try:
            return float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            return None
    return None


def _campana(pr):
    """Nombre/id de la campana si la hay, o '' si no."""
    c = pr.get('campaign')
    if not c:
        return ''
    if isinstance(c, dict):
        return str(c.get('name') or c.get('title') or c.get('id') or 'SI')
    return str(c)


def descargar_catalogo_heo(max_paginas=None, con_chase=False):
    """Baja y cruza los 3 endpoints. Devuelve lista de dicts (una fila por producto CON EAN).
    Si con_chase=True devuelve (filas, chase): los Funko chase se DESVIAN a 'chase' (no
    entran al cruce normal) para la puente escaner_chase_asin (ASIN manual)."""
    print(">>> Bajando PRODUCTS...", flush=True)
    productos = _paginar('catalog/products', max_paginas)
    print(">>> Bajando PRICES...", flush=True)
    precios = {p.get('productNumber'): p for p in _paginar('catalog/prices', max_paginas)}
    print(">>> Bajando AVAILABILITIES...", flush=True)
    dispo = {a.get('productNumber'): a for a in _paginar('catalog/availabilities', max_paginas)}
    print(f">>> Cruzando: {len(productos)} productos | {len(precios)} precios | {len(dispo)} disponibilidades")

    filas, sin_ean, chase = [], 0, []
    for prod in productos:
        if con_chase and _es_funko_chase(prod):
            pnc = prod.get('productNumber')
            prc = precios.get(pnc) or {}
            avc = dispo.get(pnc) or {}
            basec = _amt(prc.get('basePricePerUnit'))
            discc = _amt(prc.get('discountedPricePerUnit'))
            precioc = discc if discc is not None else basec
            orderablec = bool(avc.get('availableToOrder')) and str(avc.get('availabilityState', '')).upper() == 'AVAILABLE'
            nombrec = _trad(prod.get('name'))
            chase.append({
                'producto_heo': pnc,
                'nombre':       nombrec,
                'ean_caja':     _ean_bruto(prod),
                'marca':        _marca(prod),
                'precio_caja':  (None if precioc is None else round(precioc, 2)),
                'estado':       ('disponible' if orderablec else 'agotado'),
                'imagen':       ((prod.get('media') or {}).get('mainImage') or {}).get('url') or '',
                'link_amazon':  'https://www.amazon.es/s?k=' + quote_plus(nombrec or ''),
            })
            continue                     # los chase NO cruzan por EAN (su codigo es de caja)
        ean = _ean(prod)
        if not ean:                      # sin GTIN no se puede cruzar con Amazon -> fuera
            sin_ean += 1
            continue
        pn = prod.get('productNumber')
        pr = precios.get(pn) or {}
        av = dispo.get(pn) or {}
        # Precios: base (estable), discounted (lo que pagas hoy, con promo), descuento y campana.
        base  = _amt(pr.get('basePricePerUnit'))
        disc  = _amt(pr.get('discountedPricePerUnit'))
        dto   = _amt(pr.get('retailerProductDiscount'))
        strike = _amt(pr.get('strikePricePerUnit'))
        campana = _campana(pr)
        precio = disc if disc is not None else base   # el coste real de hoy
        # En oferta si: hay campana, o descuento>0, o el precio de hoy es menor que el base.
        en_oferta = bool(campana) or (dto is not None and dto > 0) or \
                    (base is not None and precio is not None and precio < base - 0.001)
        orderable = bool(av.get('availableToOrder')) and str(av.get('availabilityState', '')).upper() == 'AVAILABLE'
        img = ((prod.get('media') or {}).get('mainImage') or {}).get('url') or ''
        filas.append({
            'productNumber':  pn,
            'ean':            ean,
            'nombre':         _trad(prod.get('name')),
            'marca':          _marca(prod),
            'categoria':      _categoria(prod),
            'precio':         ('' if precio is None else round(precio, 2)),
            'precio_base':    ('' if base is None else round(base, 2)),
            'en_oferta':      ('SI' if en_oferta else ''),
            'campana':        campana,
            'estado':         ('disponible' if orderable else 'agotado'),
            'disponibilidad': (av.get('availability') or ''),        # GREEN / YELLOW / RED
            'imagen':         img,
            'fin_de_vida':    ('SI' if prod.get('isEndOfLife') else ''),
            'preorder':       ('SI' if prod.get('preorderDeadline') else ''),
        })
    print(f">>> Catalogo cruzado: {len(filas)} filas con EAN (descartadas {sin_ean} sin GTIN)")
    en_of = sum(1 for f in filas if f['en_oferta'])
    print(f">>> En oferta (campana/descuento/precio<base): {en_of}")
    if con_chase:
        print(f">>> Funko chase desviados a la puente: {len(chase)}")
        return filas, chase
    return filas


COLS = ['productNumber', 'ean', 'nombre', 'marca', 'categoria', 'precio', 'precio_base',
        'en_oferta', 'campana', 'estado', 'disponibilidad', 'imagen', 'fin_de_vida', 'preorder']


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
