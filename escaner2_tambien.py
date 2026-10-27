# -*- coding: utf-8 -*-
"""ESCANER 2 · LA COLUMNA «También lo tiene» (encargo TL, 24-oct-2026)

QUE ES. Lo que lee y escribe la ultima columna de «Análisis» en los Excel del escaner 2 (el Escaneo PRO de cada
proveedor y las novedades automaticas; el escaneo de facturas, no: «no se mira», Fernando, 16-oct): que OTROS
proveedores tienen ese EAN disponible hoy, del mas barato al mas caro, con su precio de compra por unidad. Fernando,
24-oct-2026: «Imagina que me sale un funko rentable en dbline pero resulta que esta semana estaba en oferta en TCG,
pues como se que es rentable a precio mas caro me voy a tcg y lo compro directamente, asi de simple».

🔒 SOLO INFORMA Y SOLO LEE: no recalcula la rentabilidad, no cambia la «Decisión» ni ninguna otra columna, no reordena
   filas, y no escribe en ninguna tabla. La hoja la toca `escaner2_motor.poner_columna_tambien`.
🔑 (EX, 27-oct-2026) Ya no se queda la ultima: el paso final de cada Excel (`escaner2_motor.poner_almacen_fba_tambien`)
   la pone detras de «Decisión», con «Almacén» y «FBA», y en NEGRITA cada proveedor mas barato que el de la fila.

LA CELDA: «TCG 6,95 € oferta · OcioStock 7,20 € · BEMS 7,40 € (10-oct)». Cada otro proveedor (NUNCA el del propio
Excel), una vez, con su precio mas barato del EAN; «oferta» si lo esta en ese proveedor; la fecha de su foto solo si
no es de hoy (Madrid). Nadie mas → vacia. La lectura falla → toda la columna «sin consultar», y el aviso al cruce.
🔑 (Cowork, 24-oct-2026) SI ESE PRECIO ES DE UNA CAJA (es_caja con uds_caja > 1, en cualquier proveedor), « caja de N»
   detras del precio: «HEO 4,52 € caja de 6 · BEMS 6,48 €». El precio sigue siendo por unidad (comparable con la suelta
   del mismo EAN), pero solo se consigue comprando la caja entera, y eso se tiene que ver sin abrir la web.

🔑 EL PRECIO ES EL DEL ESCANEO DE ESE PROVEEDOR, NO UNO NUEVO: las filas de su foto de disponibilidad (`disp_estado`,
   vistas en su ultima pasada, en catalogo y disponibles) pasan por SU `construir_foto`, la misma que usa su barrido,
   en el modo «todas» (sin filtro de marca), y se lee su `precio_unidad`, que es el PA con el que decide su cruce:
     · DBLine    → escaner2_dbline_pro.construir_foto: Prezzo o la promo vigente (la caducada vuelve a Prezzo);
     · OcioStock → escaner2_ociostock_pro.construir_foto: `precio_pa` (el escalon mas barato × 0,99), por figura;
     · TCG       → escaner2_tcg_pro.construir_foto: `precio_escalon` (el tramo mas barato), por figura;
     · BEMS      → escaner2_bems_pro.construir_foto: el PA del CSV;
     · OSMA      → escaner2_osma.construir_foto con el porte de `porte_de` (facturas + disp_parametros) y sus enlaces
                   (`enlaces_de`), como su barrido: precio × (1 + porte), redondeado;
     · HEO       → su Escaneo PRO no sale de disp_estado (baja la web): se lee `precio_unidad` de su foto, que escribe
                   escaner2_disponibilidad._fila con la Celda 8 (la caja, entre sus unidades). Ver `foto_heo`.
     · Zentrada  → no esta en disp_estado: la foto de su ultimo Escaneo PRO con un cruce «lista» (escaner2_foto, la
                   misma regla que la puerta comun v_escaner_fuente), su `precio_unidad` (la oferta mas barata que se
                   puede pedir) y la fecha de esa pasada.
     · Kaffek    → fuera: no hay ninguna lectura con precio (en v_escaner_fuente es «siempre», sin precio).
🔑 «OFERTA», LA DE CADA PROVEEDOR, sin inventar: el `en_oferta` que deja su `construir_foto` (DBLine: promo vigente;
   TCG: estado «Oferta»; OSMA: casilla SALE; HEO: precio tachado, de su foto). BEMS, OcioStock y Zentrada no tienen
   oferta (su foto la deja en falso o vacia): nunca dicen «oferta».
🔴 FUERA DE LA CELDA: lo no disponible, las preventas, los chase sueltos (la regla de cada `construir_foto`; las cajas
   «5 + 1» entran, por figura y con el EAN de la figura comun, como en su escaneo y en la puerta comun), y la foto de
   MAS DE 30 DIAS: la regla de Reponer para BEMS (FOTO_A_MANO_VALE_DIAS de la v2, lib/inventory/build.ts): el dia UTC
   de `visto_en` contra hoy de Madrid, y fuera si pasan de 30.

🔴 REPO PUBLICO: aqui no hay ni un precio ni un EAN reales.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import escaner2_bems_pro as ebe
import escaner2_dbline_pro as edb
import escaner2_motor as e2
import escaner2_ociostock_pro as eoc
import escaner2_osma as eo
import escaner2_tcg_pro as etc
import escaner2_zentrada as ez

PROVEEDORES_DISP = ('BEMS', 'DBLINE', 'HEO', 'OCIOSTOCK', 'OSMA', 'TCG')
NOMBRE = {'BEMS': ebe.NOMBRE, 'DBLINE': edb.NOMBRE, 'HEO': 'HEO', 'OCIOSTOCK': eoc.NOMBRE, 'OSMA': eo.PROVEEDOR,
          'TCG': etc.NOMBRE, 'ZENTRADA': ez.NOMBRE}
# Las columnas que leen los barridos de cada proveedor (la union), y con que se cruza y se fecha.
COLUMNAS_DISP = ('proveedor,producto_prov,ean_original,ean_core,ean_norm,marca,nombre,categoria,precio_unidad,'
                 'precio_catalogo,precio_escalon,uds_escalon,precio_pa,es_caja,uds_caja,es_chase,en_oferta,fin_oferta,'
                 'disponible,preorder,fin_de_vida,regla,aviso,en_catalogo,ausencias,visto_en,pasada_id')
TANDA_EAN = 150
PAGINA = 1000
FOTO_VALE_DIAS = 30
MESES = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')
_TODAS = (lambda _m: True)


def _madrid():
    from zoneinfo import ZoneInfo
    return ZoneInfo('Europe/Madrid')


def hoy_madrid():
    return datetime.now(_madrid()).date()


def _instante(x):
    if x is None or x == '':
        return None
    if isinstance(x, datetime):
        return x
    return datetime.fromisoformat(str(x).replace('Z', '+00:00'))


def dia_madrid(x):
    """El dia de Madrid de un instante de la base (o None)."""
    t = _instante(x)
    return None if t is None else t.astimezone(_madrid()).date()


def caducada(x, hoy):
    """¿La foto de este instante tiene MAS de 30 dias? La regla de Reponer para BEMS (`diasDesde` de la v2): el dia UTC
    del instante contra hoy de Madrid. Sin fecha no se juzga (no caduca)."""
    t = _instante(x)
    if t is None:
        return False
    return (hoy - t.astimezone(timezone.utc).date()).days > FOTO_VALE_DIAS


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · EL PRECIO DE CADA PROVEEDOR, CON LA FOTO DE SU PROPIO ESCANEO
# ═══════════════════════════════════════════════════════════════════════════════
def foto_heo(filas):
    """La foto de HEO desde disp_estado. Su Escaneo PRO baja la web y no tiene una `construir_foto` sobre disp_estado;
    lo que si es suyo es el precio: `precio_unidad` lo escribe escaner2_disponibilidad._fila con la Celda 8 (la caja
    de HEO, entre sus unidades) y `en_oferta` es el precio tachado (desvio CJ4). Aqui solo se aparta lo que su escaneo
    no compra: una `regla` de la foto (chase suelto, EAN que no son 12 o 13 cifras, caja con chase sin figura: con el
    EAN raro la regla va siempre, escaner2_disponibilidad.construir_disponibilidad). Lo no disponible, la preventa y un
    chase que no es caja ya los quita `ofertas_de`, para todos. Sin dedup: el mas barato por EAN lo elige `ofertas_de`."""
    foto = []
    for f in filas or []:
        if f.get('regla'):
            continue
        foto.append({'producto_heo': str(f.get('producto_prov') or ''), 'ean_core': str(f.get('ean_core') or '').strip(),
                     'precio_unidad': None if f.get('precio_unidad') is None else float(f['precio_unidad']),
                     'es_caja': bool(f.get('es_caja')), 'uds_caja': f.get('uds_caja'), 'es_chase': bool(f.get('es_chase')),
                     'en_oferta': bool(f.get('en_oferta')), 'preorder': False})
    return foto


def foto_de(proveedor, filas, M, hoy, osma=None):
    """La foto de un proveedor con SU `construir_foto` (modo «todas»: sin filtro de marca). `osma`: (enlaces, pct) de
    OSMA. Los recuentos y el cuadre previo no se miran: aqui no hay pasada que cuadrar."""
    n = len(filas or [])
    if proveedor == 'DBLINE':
        return edb.construir_foto(filas, _TODAS, M, n, 0, hoy, 'todas')[0]
    if proveedor == 'OCIOSTOCK':
        return eoc.construir_foto(filas, _TODAS, M, n, 0, 'todas')[0]
    if proveedor == 'TCG':
        return etc.construir_foto(filas, _TODAS, M, n, 0, 'todas')[0]
    if proveedor == 'BEMS':
        return ebe.construir_foto(filas, _TODAS, M, n, 0, 'todas')[0]
    if proveedor == 'OSMA':
        enlaces, pct = osma if osma is not None else ({}, None)
        return eo.construir_foto(filas, enlaces, M, pct)[0]
    if proveedor == 'HEO':
        return foto_heo(filas)
    raise ValueError('proveedor sin foto: %r' % (proveedor,))


def uds_de_caja(f):
    """Las unidades de la caja de una fila de foto (es_caja con uds_caja > 1), o None si va suelta."""
    try:
        n = int(f.get('uds_caja') or 0)
    except (TypeError, ValueError):
        return None
    return n if f.get('es_caja') and n > 1 else None


def ofertas_de(proveedor, filas, M, hoy, osma=None):
    """{ean_norm: oferta} de un proveedor: la de menor precio por unidad de su foto, sin preventas, sin chase suelto y
    sin foto de mas de 30 dias. Oferta = {proveedor, precio, oferta, dia, caja}; `dia`, el de Madrid de su `visto_en`;
    `caja`, las unidades si ese precio es de una caja (`uds_de_caja`)."""
    filas = [f for f in filas or [] if f.get('disponible') and not f.get('preorder')]
    visto = {str(f.get('producto_prov') or ''): f.get('visto_en') for f in filas}
    mejor = {}
    for f in foto_de(proveedor, filas, M, hoy, osma):
        precio = f.get('precio_unidad')
        if precio is None or precio <= 0 or f.get('preorder') or (f.get('es_chase') and not f.get('es_caja')):
            continue
        cuando = visto.get(str(f.get('producto_heo') or ''))
        if caducada(cuando, hoy):
            continue
        k = M.norm(str(f.get('ean_core') or '').strip())
        o = {'proveedor': proveedor, 'precio': float(precio), 'oferta': bool(f.get('en_oferta')),
             'dia': dia_madrid(cuando), 'caja': uds_de_caja(f)}
        if k and (k not in mejor or o['precio'] < mejor[k]['precio']):
            mejor[k] = o
    return mejor


def ofertas_zentrada(fotos, creada_en, M, hoy):
    """{ean_norm: oferta} de Zentrada desde la foto de su ultimo Escaneo PRO (escaner2_foto): su `precio_unidad` (la
    oferta mas barata que se puede pedir) y la fecha de la pasada. Sin chase ni preventa (su foto no los trae)."""
    if caducada(creada_en, hoy):
        return {}
    mejor = {}
    for f in fotos or []:
        precio = None if f.get('precio_unidad') is None else float(f['precio_unidad'])
        if precio is None or precio <= 0 or f.get('es_chase') or f.get('preorder'):
            continue
        k = M.norm(str(f.get('ean_core') or '').strip())
        o = {'proveedor': 'ZENTRADA', 'precio': precio, 'oferta': bool(f.get('en_oferta')),
             'dia': dia_madrid(creada_en), 'caja': uds_de_caja(f)}
        if k and (k not in mejor or precio < mejor[k]['precio']):
            mejor[k] = o
    return mejor


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · EL TEXTO DE LA CELDA
# ═══════════════════════════════════════════════════════════════════════════════
def precio_texto(x):
    """6.95 → «6,95 €» (dos decimales, redondeo comercial)."""
    return '%s €' % str(Decimal(str(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)).replace('.', ',')


def dia_texto(d):
    return '%d-%s' % (d.day, MESES[d.month - 1])


def texto_tambien(ofertas, hoy):
    """La celda para un EAN: `ofertas`, una por proveedor. Del mas barato al mas caro (a igual precio, por nombre),
    separadas por « · », cada una «Nombre precio[ caja de N][ oferta][ (dia)]». None si no hay ninguna. Puro."""
    partes = []
    for o in sorted(ofertas or [], key=lambda o: (o['precio'], NOMBRE.get(o['proveedor'], o['proveedor']))):
        t = '%s %s' % (NOMBRE.get(o['proveedor'], o['proveedor']), precio_texto(o['precio']))
        if o.get('caja'):
            t += ' caja de %d' % o['caja']
        if o.get('oferta'):
            t += ' oferta'
        if o.get('dia') is not None and o['dia'] != hoy:
            t += ' (%s)' % dia_texto(o['dia'])
        partes.append(t)
    return ' · '.join(partes) or None


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · LA LECTURA (solo lectura)
# ═══════════════════════════════════════════════════════════════════════════════
def _paginas(consulta):
    """Todas las filas de una consulta, de 1.000 en 1.000 (el tope de la API). `consulta()` da una nueva cada vez."""
    salida, desde = [], 0
    while True:
        pagina = consulta().range(desde, desde + PAGINA - 1).execute().data or []
        salida.extend(pagina)
        if len(pagina) < PAGINA:
            return salida
        desde += PAGINA


def leer_disp(sb, proveedores, eans):
    """Las filas de disp_estado de esos proveedores y esos EAN normalizados: vistas en su ultima pasada (ausencias = 0,
    lo que lee cada barrido), en catalogo y disponibles."""
    filas = []
    for i in range(0, len(eans), TANDA_EAN):
        tanda = eans[i:i + TANDA_EAN]
        filas += _paginas(lambda: sb.table('disp_estado').select(COLUMNAS_DISP).in_('proveedor', list(proveedores))
                          .in_('ean_norm', tanda).eq('ausencias', 0).eq('en_catalogo', True).eq('disponible', True)
                          .order('proveedor').order('producto_prov'))
    return filas


def leer_osma(sb):
    """(enlaces, pct) de OSMA, como su barrido: el porte de `porte_de` (las facturas de OSMA y el pedido previsto de
    disp_parametros) y los enlaces por codigo de `enlaces_de` (codigos_proveedor y productos)."""
    par = (sb.table('disp_parametros').select('pedido_previsto_eur').eq('proveedor', eo.PROVEEDOR).execute().data
           or [{}])[0]
    facturas = _paginas(lambda: sb.table('facturas').select('id,fecha,created_at,gastos_envio')
                        .eq('proveedor', eo.PROVEEDOR).order('id'))
    codigos = _paginas(lambda: sb.table('codigos_proveedor').select('codigo_proveedor,producto_id')
                       .eq('proveedor', eo.PROVEEDOR).order('id'))
    productos = _paginas(lambda: sb.table('productos').select('id,asin,ean,activo,es_chase').order('id'))
    enlaces, _avisos = eo.enlaces_de(codigos, productos)
    return enlaces, eo.porte_de(facturas, par.get('pedido_previsto_eur'))['pct']


def leer_zentrada(sb, eans):
    """(filas de escaner2_foto con esos EAN, creada_en) del ultimo Escaneo PRO de Zentrada con un cruce «lista» (la
    regla de v_escaner_fuente), o ([], None) si no hay."""
    pasadas = (sb.table('escaner2_pasada').select('id,creada_en').eq('proveedor', ez.PROVEEDOR)
               .order('creada_en', desc=True).limit(20).execute().data) or []
    if not pasadas:
        return [], None
    listas = {c['pasada_id'] for c in (sb.table('escaner2_cruce').select('pasada_id')
                                       .in_('pasada_id', [p['id'] for p in pasadas]).eq('estado', 'lista')
                                       .execute().data or [])}
    ult = next((p for p in pasadas if p['id'] in listas), None)
    if ult is None:
        return [], None
    fotos = []
    for i in range(0, len(eans), TANDA_EAN):
        tanda = eans[i:i + TANDA_EAN]
        fotos += _paginas(lambda: sb.table('escaner2_foto').select('ean_core,ean_norm,precio_unidad,es_caja,uds_caja,'
                                                                   'es_chase,preorder,en_oferta').eq('pasada_id', ult['id'])
                          .in_('ean_norm', tanda).order('id'))
    return fotos, ult['creada_en']


def lector_tambien(sb, propio, M, avisos=None, hoy=None):
    """Una funcion EAN de la hoja → {EAN: texto} que lee a los OTROS proveedores (nunca `propio`) en una pasada. Si la
    lectura falla, devuelve None (toda la columna «sin consultar») y deja el porque en `avisos`: el Excel no se cae."""
    propio = str(propio or '').upper()

    def leer(eans_hoja):
        dia = hoy or hoy_madrid()
        norm = {e: M.norm(e) for e in eans_hoja if e}
        eans = sorted({k for k in norm.values() if k})
        try:
            otros = [p for p in PROVEEDORES_DISP if p != propio]
            filas = leer_disp(sb, otros, eans) if eans else []
            por_prov = {}
            for f in filas:
                por_prov.setdefault(f['proveedor'], []).append(f)
            por_ean = {}
            for p in otros:
                if not por_prov.get(p):
                    continue
                osma = leer_osma(sb) if p == 'OSMA' else None
                for k, o in ofertas_de(p, por_prov[p], M, dia, osma).items():
                    por_ean.setdefault(k, []).append(o)
            if propio != ez.PROVEEDOR and eans:
                fotos, creada_en = leer_zentrada(sb, eans)
                for k, o in ofertas_zentrada(fotos, creada_en, M, dia).items():
                    por_ean.setdefault(k, []).append(o)
        except Exception as ex:
            if avisos is not None:
                avisos.append('Columna «%s» sin datos (se escribe «%s»): %s: %s'
                              % (e2.COLUMNA_TAMBIEN, e2.TEXTO_SIN_CONSULTAR_TAMBIEN, type(ex).__name__, str(ex)[:160]))
            return None
        return {e: texto_tambien(por_ean.get(k), dia) for e, k in norm.items()}
    return leer
