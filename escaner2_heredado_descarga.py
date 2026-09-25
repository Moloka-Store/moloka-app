# -*- coding: utf-8 -*-
"""ESCANER 2 · LO HEREDADO DE descargar_heo.py (la API de HEO), COPIADO LITERALMENTE.

Encargo B7 (25-sep-2026). Todo el modulo hasta `descargar_catalogo_heo` incluida (imports, credenciales
de Secrets, paginacion, traducciones, chase y el cruce de los tres endpoints) y la `TANDA` del
Visualizador, texto EXACTO del commit 2f9c06a (blob 0189eae9af), generado por script. SI se importa: el barrido
hace `from escaner2_heredado_descarga import descargar_catalogo_heo`, y cuenta el crudo y los sin GTIN
con las MISMAS lineas de log de siempre.
No se trae `COLS` ni `a_csv_bytes` (son del director viejo) ni el bloque `__main__` (solo su `TANDA`).
🔴 NO SE TOCA A MANO: si descargar_heo.py cambia, test_escaner2_heredado.py lo avisa y decide Fernando.
"""


# ── ORIGEN: descargar_heo.py, líneas 1-16 · commit 2f9c06a · blob 0189eae9af · md5 102d328455d8ed659dba0ebce87caf61 ──
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


# ── ORIGEN: descargar_heo.py, líneas 17-17 · commit 2f9c06a · blob 0189eae9af · md5 456ec2e39c1b030308042af5ed6ff39c ──
from urllib.parse import quote_plus


# ── ORIGEN: descargar_heo.py, líneas 18-18 · commit 2f9c06a · blob 0189eae9af · md5 2924c296468b39f5309d037fd771cab1 ──
from requests.auth import HTTPBasicAuth


# ── ORIGEN: descargar_heo.py, líneas 20-20 · commit 2f9c06a · blob 0189eae9af · md5 70c03474d5c774226099cac039ef90a9 ──
sys.stdout.reconfigure(line_buffering=True)


# ── ORIGEN: descargar_heo.py, líneas 22-22 · commit 2f9c06a · blob 0189eae9af · md5 423f6dbf573bbfcd2011c575c48dcdac ──
USER = os.environ['HEO_USER']


# ── ORIGEN: descargar_heo.py, líneas 23-23 · commit 2f9c06a · blob 0189eae9af · md5 f4a5394f156dc0346dd955444072dd0e ──
PASS = os.environ['HEO_PASS']


# ── ORIGEN: descargar_heo.py, líneas 24-24 · commit 2f9c06a · blob 0189eae9af · md5 46e5cef93bdc6110e2bbdb2e3b005379 ──
BASE = os.environ.get('HEO_BASE', 'https://integrate.heo.com/retailer-api/v1')


# ── ORIGEN: descargar_heo.py, líneas 25-25 · commit 2f9c06a · blob 0189eae9af · md5 903b7e50919474021eb5c634be951cae ──
PAGE_SIZE = int(os.environ.get('HEO_PAGE_SIZE', '500'))


# ── ORIGEN: descargar_heo.py, líneas 26-26 · commit 2f9c06a · blob 0189eae9af · md5 0ad3dde93ea730be085af5bb296355ae ──
IDIOMA = os.environ.get('HEO_IDIOMA', 'ES')   # preferencia de idioma; fallback EN


# ── ORIGEN: descargar_heo.py, líneas 27-27 · commit 2f9c06a · blob 0189eae9af · md5 f58fe947142d4d176067089fb6e06094 ──
auth = HTTPBasicAuth(USER, PASS)


# ── ORIGEN: descargar_heo.py, líneas 30-48 · commit 2f9c06a · blob 0189eae9af · md5 725d672f39b52e641f4f3b360a0d2cb1 ──
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


# ── ORIGEN: descargar_heo.py, líneas 51-68 · commit 2f9c06a · blob 0189eae9af · md5 58f591c45955496e5f4fe4b24b218303 ──
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


# ── ORIGEN: descargar_heo.py, líneas 71-76 · commit 2f9c06a · blob 0189eae9af · md5 34d2350274af2947edfaffc400e2a3a3 ──
def _trad(lista, idioma=IDIOMA):
    """De [{langIso2, translation}] devuelve la del idioma preferido (o EN, o la 1a)."""
    if not lista:
        return ''
    by = {t.get('langIso2'): t.get('translation') for t in lista if isinstance(t, dict)}
    return by.get(idioma) or by.get('EN') or next(iter(by.values()), '')


# ── ORIGEN: descargar_heo.py, líneas 79-83 · commit 2f9c06a · blob 0189eae9af · md5 f0e1ccf1c18470a5d6efe18afd78ad3c ──
def _ean(prod):
    for b in (prod.get('barcodes') or []):
        if str(b.get('type', '')).upper() == 'GTIN' and b.get('barcode'):
            return str(b['barcode']).strip()
    return ''


# ── ORIGEN: descargar_heo.py, líneas 86-92 · commit 2f9c06a · blob 0189eae9af · md5 c6fd15fd65addc0c22a097a66e5d1c4f ──
def _ean_bruto(prod):
    """El PRIMER barcode del producto, sea GTIN o no. Los cases (p.ej. AC/DC Angus)
    traen el codigo de CAJA con type UNDEFINED, que _ean descarta; aqui lo conservamos."""
    for b in (prod.get('barcodes') or []):
        if b.get('barcode'):
            return str(b['barcode']).strip()
    return ''


# ── ORIGEN: descargar_heo.py, líneas 95-98 · commit 2f9c06a · blob 0189eae9af · md5 0845848a6fccc88bb7b2797619c94bf5 ──
# Senal de chase Funko, MEDIDA contra el catalogo real (100 productos, 0 escapes):
# CHASE / 5+1 / abreviatura CH (w/CH, w/ CH(BD), (CH), CH(GW)) / "Surtido 6" / "Surtido (6)".
# En HEO, un Funko + surtido de 6 es un case con chase.
_RE_CHASE = re.compile(r'chase|5\s*\+\s*1|w/\s*ch\b|\(\s*ch\s*\)|\bch\s*\(|surtido\s*\(\s*6\s*\)|surtido\s+6\b', re.I)


# ── ORIGEN: descargar_heo.py, líneas 101-106 · commit 2f9c06a · blob 0189eae9af · md5 d95c629d2679983f52baff7ee3476ea1 ──
def _es_funko_chase(prod):
    """True si es Funko y el nombre lleva senal de chase. Los cases NO cruzan por EAN
    (su codigo es de caja): van a la puente escaner_chase_asin para ASIN manual."""
    if 'FUNKO' not in (_marca(prod) or '').upper():
        return False
    return bool(_RE_CHASE.search(_trad(prod.get('name')) or ''))


# ── ORIGEN: descargar_heo.py, líneas 109-111 · commit 2f9c06a · blob 0189eae9af · md5 a3bdff072a6d2d6b873290b9fd42f1ad ──
def _marca(prod):
    ms = prod.get('manufacturers') or []
    return _trad(ms[0].get('translations')) if (ms and isinstance(ms[0], dict)) else ''


# ── ORIGEN: descargar_heo.py, líneas 114-116 · commit 2f9c06a · blob 0189eae9af · md5 4530af128c6083549977f13a194fa740 ──
def _categoria(prod):
    cs = prod.get('categories') or []
    return _trad(cs[0].get('translations')) if (cs and isinstance(cs[0], dict)) else ''


# ── ORIGEN: descargar_heo.py, líneas 119-127 · commit 2f9c06a · blob 0189eae9af · md5 3c3f6c4daabde73c61399707917b2f62 ──
def _amt(d):
    """amount de un dict de precio {amount, currencyIsoCode}, o None."""
    if isinstance(d, dict):
        v = d.get('amount')
        try:
            return float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            return None
    return None


# ── ORIGEN: descargar_heo.py, líneas 130-137 · commit 2f9c06a · blob 0189eae9af · md5 bc857e8f3cc75ba3b2e1643dc8cec19c ──
def _campana(pr):
    """Nombre/id de la campana si la hay, o '' si no."""
    c = pr.get('campaign')
    if not c:
        return ''
    if isinstance(c, dict):
        return str(c.get('name') or c.get('title') or c.get('id') or 'SI')
    return str(c)


# ── ORIGEN: descargar_heo.py, líneas 140-215 · commit 2f9c06a · blob 0189eae9af · md5 32c3fb61118983621fd581fca2b8ac1a ──
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


# ── ORIGEN: descargar_heo.py, líneas 241-241 · commit 2f9c06a · blob 0189eae9af · md5 ede2950affb2d05906f51e0c0ccb0d0e ──
# ── (en el original, dentro de `if __name__ == '__main__':` y `if HEO_FULL`: aquí va sin su sangría de 8 espacios, nada más; solo lo LEE `tanda_visualizador`)
TANDA = int(os.environ.get('HEO_TANDA', '10000'))
