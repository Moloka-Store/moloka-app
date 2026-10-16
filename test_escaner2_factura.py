# -*- coding: utf-8 -*-
"""Banco del ESCANEO DE UNA FACTURA en el escaner 2 (encargo F2, 16-oct-2026): escaner2_factura.py.

SIN RED, SIN SECRETOS Y SIN BASE: Keepa es un doble de su API (`http` de escaner2_novedades.Keepa) y Supabase una
clase con listas. Las cifras esperadas van escritas A MANO (la cuenta del viejo hecha con lapiz, no llamando a la
misma funcion), y al final se rompe una copia del heredado para ver que el escaneo pasa de verdad por el.

QUE PRUEBA:
  (A) datos de HOY de la app: cartero (precio + tarifa) y foto de Keepa → «app», 0 peticiones a Keepa, la cuenta del
      viejo al centimo; un dato de AYER no vale y se pregunta a Keepa. (A2) 🔴 el escalon de los 20 €: la tarifa del
      cartero calculada a otro lado de 20 € que el precio de venta pasa por fn_fee_escalon (caso real de la sombra).
  (B) Keepa en el momento: la caja de compra aterrizada (current[18]) de `datos_pais`, su tarifa y comision, las
      caidas de la misma respuesta y los tokens que Keepa dice haber gastado.
  (C) linea sin ASIN: Keepa ES por el codigo de barras y la eleccion del viejo; el ASIN NO se escribe en ninguna ficha.
  (D) el chase no se escanea: ni una fila, ni una pregunta.
  (E) Paises Bajos y Belgica: la tarifa del pais si la hay; si no, la de España y lo dice; la funcion de la base con
      15 %, 21 %, 12 % y el escalon del pais de la tarifa.
  (F) ventas al mes: un pais rentable sin caidas pregunta a Keepa sin caja de compra (1 peticion); uno no rentable, no.
  (G) Keepa sin saldo: «Sin datos» con su motivo y sin preguntar.
  (H) la grabacion de la sombra: lo grabado repite el escaneo igual, sin red; y no lleva la llave.
  (I) la peticion de la v2 mal formada no se escanea (sin lineas, sin EAN, linea repetida).
  (J) la sombra reconstruye las lineas del viejo de su escaner_detalle.
  (K) 🔴 MUERDE: con `decision_de` del heredado cambiada en una copia, el veredicto cambia.
  (L) 🔴 UN FALLO NO SE CUENTA EN EL LOG PUBLICO (devolución de Cowork, 16-oct-2026): escaner2_factura_nube.py, en su
      proceso, con una excepción cuyo texto lleva una fila con coste, ASIN y EAN: ni en el modo de verdad ni en la
      sombra sale ese texto por la salida; en el de verdad, el detalle llega a `motivo_fallo` (privado).
"""
import io
import os
import subprocess
import sys
import tempfile

import escaner2_factura as ef
import escaner2_motor as e2
import escaner2_novedades as nv

AQUI = os.path.dirname(os.path.abspath(__file__))
fallos = []
SECRETO = 'Failing row contains (P1, 0, 8400000000017, B0SECRETO1, ES, 8.1234)'


def hijo(modo):
    """(L) El programa de la nube de punta a punta con un Supabase de mentira y una excepción que lleva datos."""
    import atexit
    import types
    actualizaciones = []

    class Q:
        def __init__(self, tabla):
            self.tabla, self.upd = tabla, None

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def in_(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def range(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def update(self, campos):
            self.upd = campos
            return self

        def execute(self):
            if self.tabla == 'escaner_detalle':
                raise Exception(SECRETO)
            if self.upd is not None:
                actualizaciones.append(self.upd)
                return types.SimpleNamespace(data=[{'id': 'P1'}])
            return types.SimpleNamespace(data=[{'id': 'P1', 'ejecucion': 'E', 'factura_id': 'F', 'estado': 'pedida',
                                                'lineas': [{'linea': 0, 'ean': '8400000000017', 'pa': 8.1234}]}])

    class Cliente:
        def table(self, nombre):
            return Q(nombre)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda url, key: Cliente()
    os.environ.update(SUPABASE_URL='https://doble.local', SUPABASE_SERVICE_KEY='FAKE', KEEPA_API_KEY='')
    import escaner2_factura as _ef
    import escaner2_novedades as _nv

    def revienta(*a, **k):
        raise Exception(SECRETO)
    _ef.escanear = revienta
    _nv.Keepa.leer_saldo = lambda self: setattr(self, 'saldo', 1000) or 1000
    if modo == 'sombra':
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import base64
        pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        os.environ['SOMBRA_CLAVE_PUBLICA'] = base64.b64encode(pub).decode('ascii')
        sys.argv = ['escaner2_factura_nube.py', '--sombra', 'vieja']
    else:
        sys.argv = ['escaner2_factura_nube.py', '--ejecucion', 'E']

    @atexit.register
    def _informe():
        fallida = [u for u in actualizaciones if u.get('estado') == 'fallida']
        print('MOTIVO_PRIVADO=%d' % int(bool(fallida) and SECRETO in (fallida[0].get('motivo_fallo') or '')))

    import runpy
    runpy.run_path(os.path.join(AQUI, 'escaner2_factura_nube.py'), run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2])
    sys.exit(0)
HOY = '2026-10-16'
AYER = '2026-10-15'


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def cerca(nombre, obtenido, esperado, tol=1e-9):
    ok = obtenido is not None and abs(obtenido - esperado) <= tol
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ── Los dobles ──────────────────────────────────────────────────────────────────────────────
def producto_keepa(asin, bb=None, nuevo=None, ref=15, fee=None, caidas=None, eans=(), titulo='', rank90=1000):
    cur = [-1] * 19
    if nuevo is not None:
        cur[1] = nuevo
    cur[3] = 5000
    if bb is not None:
        cur[18] = bb
    return {'asin': asin, 'title': titulo, 'eanList': list(eans), 'upcList': [],
            'referralFeePercentage': ref, 'fbaFees': {'pickAndPackFee': fee} if fee is not None else {},
            'stats': {'current': cur, 'avg90': [-1, -1, -1, rank90], 'buyBoxIsFBA': True, 'salesRankDrops30': caidas},
            'monthlySold': None}


class KeepaFalso:
    """La API de Keepa: /token y /product. `catalogo[(dominio, 'asin'|'code', codigo)] = [productos]`."""

    def __init__(self, catalogo, saldo=1000):
        self.catalogo, self.saldo, self.llamadas = catalogo, saldo, []

    def __call__(self, url, params, timeout):
        ruta = url.replace(nv.URL_KEEPA, '')
        assert params.get('key') == 'LLAVE-FALSA'
        if ruta == '/token':
            return 200, {'tokensLeft': self.saldo}
        por = 'asin' if 'asin' in params else 'code'
        codigos = params[por].split(',')
        self.llamadas.append((params['domain'], por, tuple(codigos), params.get('buybox')))
        prods = [p for c in codigos for p in self.catalogo.get((params['domain'], por, c), [])]
        gasto = len(prods) * (3 if params.get('buybox') else 1)
        self.saldo -= gasto
        return 200, {'products': prods, 'tokensConsumed': gasto, 'tokensLeft': self.saldo}


class BaseFalsa:
    def __init__(self, productos=(), precios=(), tarifas=(), fotos=()):
        self._p, self._pr, self._t, self._f = list(productos), list(precios), list(tarifas), list(fotos)
        self.llamadas_margen = []

    def productos(self, ids):
        return [p for p in self._p if p['id'] in ids]

    def precios_dia(self, asins, hoy):
        return [p for p in self._pr if p['asin'] in asins and str(p['fecha']) == str(hoy)]

    def tarifas(self, asins, hoy):
        return [t for t in self._t if t['asin'] in asins and str(t['vigente_desde']) <= str(hoy)]

    def fotos_keepa(self, asins, hoy):
        return [k for k in self._f if k['asin'] in asins and str(k['fecha_foto']) == str(hoy)]

    def precio_al_margen(self, **kw):
        self.llamadas_margen.append(kw)
        return 99.99

    escalon = {}
    llamadas_escalon = None

    def fee_escalon(self, asin, dominio, fee, precio):
        if self.llamadas_escalon is None:
            self.llamadas_escalon = []
        self.llamadas_escalon.append((asin, dominio, fee, precio))
        return self.escalon.get((dominio, fee), fee)


def keepa_de(catalogo, saldo=1000):
    falso = KeepaFalso(catalogo, saldo)
    return nv.Keepa('LLAVE-FALSA', http=falso, dormir=lambda s: None), falso


M = e2.cargar_motor()
PROD_A = {'id': 'p-a', 'ean': '8400000000017', 'nombre': 'Funko Pop Hiccup', 'asin': 'B0AAAAAAAA', 'es_chase': False,
          'iva_pct': 0.21}
LINEA_A = {'linea': 0, 'producto_id': 'p-a', 'ean': '8400000000017', 'asin': 'B0AAAAAAAA', 'pa': 5.0, 'factor': 1,
           'unidades': 6, 'nombre': 'Funko Pop Hiccup'}


def por(filas, pais, linea=0):
    return next(f for f in filas if f['pais'] == pais and f['linea'] == linea)


# ═══════════════════════════════════════════════════════════════════════════════
print('(A) los datos de HOY de la app: cartero y foto de Keepa, sin preguntar a Keepa')
base = BaseFalsa(
    productos=[PROD_A],
    precios=[{'asin': 'B0AAAAAAAA', 'pais': 'ES', 'fecha': HOY, 'seller_sku': 'SKU-1', 'bb_precio': 20.00, 'bb_logistica': 'AFN'}],
    tarifas=[{'seller_sku': 'SKU-1', 'asin': 'B0AAAAAAAA', 'pais': 'ES', 'vigente_desde': '2026-10-01', 'mi_precio': 20.00,
              'tarifa_referencia': 3.00, 'tarifa_gestion': 3.51}],
    fotos=[{'asin': 'B0AAAAAAAA', 'dominio': d, 'fecha_foto': HOY, 'bb_precio': 25.00, 'bb_es_fba': True, 'nuevo_precio': None,
            'tarifa_fba': fee, 'comision_pct': 15.0, 'rank_drops_30d': 40} for d, fee in (('es', 3.51), ('it', 4.61), ('fr', 5.15), ('de', 3.29))])
keepa, falso = keepa_de({})
filas, res = ef.escanear([LINEA_A], base, keepa, M, HOY)
es = por(filas, 'ES')
eq('(A) ES sale de la app: precio del cartero, tarifa del cartero', (es['fuente'], es['fuente_precio'], es['fuente_tarifa'],
                                                                    es['precio_venta'], es['fee_fba'], es['ref_pct'], es['canal']),
   ('app', 'cartero', 'cartero', 20.0, 3.51, 15.0, 'BB-FBA'))
# A mano: 20/1,21 = 16,5289256; comision 20×15 % = 3,00 + ISD 3 % = 3,09; 16,5289256 − 5 − 3,09 − 3,51 − 0,15 = 4,7789256
cerca('(A) ES: beneficio de la cuenta del viejo (a mano: 4,7789256)', es['beneficio'], 20 / 1.21 - 5 - 3.09 - 3.51 - 0.15)
cerca('(A) ES: margen = beneficio / precio (0,2389463)', es['margen'], (20 / 1.21 - 5 - 3.09 - 3.51 - 0.15) / 20)
eq('(A) ES: COMPRAR y rentable, con las caídas de la foto de hoy', (es['decision'], es['rentable'], es['caidas_30d'], es['caidas_fuente']),
   ('COMPRAR', True, 40, 'app'))
it = por(filas, 'IT')
eq('(A) IT: de la foto de Keepa de hoy (precio y tarifa)', (it['fuente'], it['fuente_precio'], it['fuente_tarifa'], it['precio_venta'], it['fee_fba']),
   ('app', 'keepa_foto', 'keepa_foto', 25.0, 4.61))
# IT: 25/1,22 = 20,4918033; comision 3,75 × 1,03 = 3,8625; 20,4918033 − 5 − 3,8625 − 4,61 − 0,15 = 6,8693033
cerca('(A) IT: beneficio a mano (6,8693033)', it['beneficio'], 25 / 1.22 - 5 - 3.8625 - 4.61 - 0.15)
fr = por(filas, 'FR')
# FR: el ISD va sobre comision + tarifa: 3,75 + (3,75 + 5,15) × 3 % = 4,017; 25/1,20 − 5 − 4,017 − 5,15 − 0,15 = 6,5163333
cerca('(A) FR: el ISD francés sobre comisión + tarifa (6,5163333)', fr['beneficio'], 25 / 1.20 - 5 - 4.017 - 5.15 - 0.15)
eq('(A) ni una pregunta a Keepa con todo de la app', (falso.llamadas, res['keepa_tokens'], res['paises_app'], res['lineas_todo_app']),
   ([], 0, 4, 1))

base_ayer = BaseFalsa(productos=[PROD_A],
                      precios=[{'asin': 'B0AAAAAAAA', 'pais': 'ES', 'fecha': AYER, 'seller_sku': 'SKU-1', 'bb_precio': 20.0, 'bb_logistica': 'AFN'}],
                      fotos=[{'asin': 'B0AAAAAAAA', 'dominio': 'es', 'fecha_foto': AYER, 'bb_precio': 20.0, 'bb_es_fba': True,
                              'nuevo_precio': None, 'tarifa_fba': 3.51, 'comision_pct': 15.0, 'rank_drops_30d': 9}])
keepa, falso = keepa_de({})
filas, _r = ef.escanear([LINEA_A], base_ayer, keepa, M, HOY)
eq('(A) 🔴 un dato de AYER no vale: se pregunta a Keepa en los cuatro países', sorted(x[0] for x in falso.llamadas), [3, 4, 8, 9])
eq('(A) …y Keepa sin ese ASIN → «Sin datos» con motivo, nunca un 0', (por(filas, 'ES')['fuente'], por(filas, 'ES')['precio_venta'],
                                                                    por(filas, 'ES')['motivo']),
   ('sin_dato', None, 'Keepa no tiene este ASIN en este país'))


# ── (A2) 🔴 el escalón de los 20 €, con las cifras de Amazon de la sombra del 16-oct-2026 (IT) y un coste inventado ────
PROD_H = dict(PROD_A, id='p-h', asin='B0HHHHHHHH')
base = BaseFalsa(
    productos=[PROD_H],
    precios=[{'asin': 'B0HHHHHHHH', 'pais': 'IT', 'fecha': HOY, 'seller_sku': 'NR', 'bb_precio': 23.43, 'bb_logistica': 'MFN'},
             {'asin': 'B0HHHHHHHH', 'pais': 'ES', 'fecha': HOY, 'seller_sku': 'NR', 'bb_precio': 19.19, 'bb_logistica': 'MFN'}],
    tarifas=[{'seller_sku': 'NR', 'asin': 'B0HHHHHHHH', 'pais': 'IT', 'vigente_desde': '2026-10-13', 'mi_precio': 19.99,
              'tarifa_referencia': 3.00, 'tarifa_gestion': 3.64},
             {'seller_sku': 'NR', 'asin': 'B0HHHHHHHH', 'pais': 'ES', 'vigente_desde': '2026-10-13', 'mi_precio': 19.19,
              'tarifa_referencia': 2.88, 'tarifa_gestion': 3.28}])
base.escalon = {('it', 3.64): 4.61}
filas, _r = ef.escanear([dict(LINEA_A, producto_id='p-h', asin='B0HHHHHHHH', pa=8.00)], base, keepa_de({})[0], M, HOY)
it, es = por(filas, 'IT'), por(filas, 'ES')
eq('(A2) IT: la tarifa del cartero (3,64 a 19,99 €) con la caja a 23,43 € pasa por fn_fee_escalon → 4,61',
   (it['fee_fba'], it['tarifa_escalon'], base.llamadas_escalon), (4.61, True, [('B0HHHHHHHH', 'it', 3.64, 23.43)]))
# A mano, IT con 4,61, coste 8,00 y la comisión del CARTERO (3,00 / 19,99 = 15,01 %): 23,43/1,22 = 19,20492;
# 23,43 × 15,01 % × 1,03 = 3,62235; 19,20492 − 8,00 − 3,62235 − 4,61 − 0,15 = 2,82257
cerca('(A2) …y el margen sale con la tarifa buena (2,82257)', it['beneficio'], 2.82257, tol=0.00001)
eq('(A2) ES: precio (19,19) y tarifa (a 19,19 €) del mismo lado → la del cartero tal cual', (es['fee_fba'], es['tarifa_escalon']), (3.28, None))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(B) Keepa en el momento: datos_pais del viejo')
cat = {(9, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2000, nuevo=1800, fee=351, caidas=12)],
       (8, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=None, nuevo=2200, fee=461, caidas=3)],
       (4, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2500, fee=None)],
       (3, 'asin', 'B0AAAAAAAA'): []}
keepa, falso = keepa_de(cat)
filas, res = ef.escanear([LINEA_A], BaseFalsa(productos=[PROD_A]), keepa, M, HOY)
es, it, fr, de = (por(filas, p) for p in ('ES', 'IT', 'FR', 'DE'))
eq('(B) ES: caja de compra aterrizada (current[18]) 20,00, tarifa 3,51, caídas de la misma respuesta',
   (es['fuente'], es['precio_venta'], es['canal'], es['fee_fba'], es['caidas_30d'], es['caidas_fuente'], es['fecha_precio']),
   ('keepa', 20.0, 'BB-FBA', 3.51, 12, 'keepa', HOY))
cerca('(B) ES: la misma cuenta que con la app (mismos datos, mismo margen)', es['margen'], (20 / 1.21 - 5 - 3.09 - 3.51 - 0.15) / 20)
eq('(B) IT: sin caja de compra → «nuevo» (SIN BB), como el viejo', (it['precio_venta'], it['canal']), (22.0, 'SIN BB'))
eq('(B) FR: sin tarifa en Keepa → «Sin datos», con su motivo', (fr['fuente'], fr['decision'], fr['margen'], fr['motivo']),
   ('keepa', 'Sin datos', None, 'sin comisión o tarifa'))
eq('(B) DE: Keepa no lo tiene → sin dato', (de['fuente'], de['motivo']), ('sin_dato', 'Keepa no tiene este ASIN en este país'))
eq('(B) una petición por país con caja de compra, y los tokens que dice Keepa', (len(falso.llamadas), {x[3] for x in falso.llamadas},
                                                                               res['keepa_tokens']), (4, {1}, 9))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(C) línea sin ASIN: por el código de barras en Keepa ES')
LINEA_C = dict(LINEA_A, asin=None, producto_id='p-c')
PROD_C = dict(PROD_A, id='p-c', asin=None)
cat = {(9, 'code', '8400000000017'): [producto_keepa('B0CCCCCCC1', eans=['8400000000017'], titulo='Funko Pop Hiccup Dragons', rank90=900),
                                       producto_keepa('B0CCCCCCC2', eans=['8400000000017'], titulo='Casco de moto', rank90=100)],
       (9, 'asin', 'B0CCCCCCC1'): [producto_keepa('B0CCCCCCC1', bb=2000, fee=351, caidas=5)]}
keepa, falso = keepa_de(cat)
filas, _r = ef.escanear([LINEA_C], BaseFalsa(productos=[PROD_C]), keepa, M, HOY)
eq('(C) el cotejo del viejo elige la ficha que se parece, no la de mejor puesto', (por(filas, 'ES')['asin'], por(filas, 'ES')['asin_origen']),
   ('B0CCCCCCC1', 'keepa_ean'))
eq('(C) primero la pregunta por el código, en ES y sin caja de compra', falso.llamadas[0], (9, 'code', ('8400000000017',), None))
eq('(C) 🔒 la ficha sigue sin ASIN (no se escribe identidad)', PROD_C['asin'], None)
keepa, falso = keepa_de({})
filas, _r = ef.escanear([LINEA_C], BaseFalsa(productos=[PROD_C]), keepa, M, HOY)
eq('(C) Keepa no conoce el código → los seis países con motivo', {f['motivo'] for f in filas},
   {'Keepa no encuentra el código de barras en Amazon España'})


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(D) el chase no se escanea')
PROD_D = dict(PROD_A, id='p-d', es_chase=True)
keepa, falso = keepa_de({})
filas, res = ef.escanear([dict(LINEA_A, producto_id='p-d', linea=0), dict(LINEA_A, linea=1)],
                         BaseFalsa(productos=[PROD_D, PROD_A]), keepa, M, HOY)
eq('(D) la línea chase no deja fila; la otra, sus seis', (sorted({f['linea'] for f in filas}), len(filas), res['chase_fuera']), ([1], 6, 1))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(E) Países Bajos y Bélgica: el precio que deja un 12 %')
base = BaseFalsa(productos=[PROD_A],
                 tarifas=[{'seller_sku': 'S', 'asin': 'B0AAAAAAAA', 'pais': 'NL', 'vigente_desde': '2026-09-01', 'mi_precio': 20,
                           'tarifa_referencia': 3, 'tarifa_gestion': 3.56}],
                 fotos=[{'asin': 'B0AAAAAAAA', 'dominio': d, 'fecha_foto': HOY, 'bb_precio': 20.0, 'bb_es_fba': True,
                         'nuevo_precio': None, 'tarifa_fba': 3.51, 'comision_pct': 15.0, 'rank_drops_30d': 1} for d in ('es', 'it', 'fr', 'de')])
keepa, falso = keepa_de({})
filas, _r = ef.escanear([LINEA_A], base, keepa, M, HOY)
nl, be = por(filas, 'NL'), por(filas, 'BE')
eq('(E) NL con SU tarifa; BE con la de España, y lo dice', ((nl['tarifa_de'], nl['fee_fba']), (be['tarifa_de'], be['fee_fba'])),
   (('NL', 3.56), ('ES', 3.51)))
eq('(E) la función de la base con 15 %, 21 %, 12 %, el almacén y el ×1,03 de siempre, y el escalón del país de la tarifa',
   [(k['dominio'], k['fee'], k['pvd'], k['iva'], k['com_pct'], k['k_com'], k['k_fee'], k['alm'], k['margen'], k['redondeo'])
    for k in base.llamadas_margen],
   [('nl', 3.56, 5.0, 0.21, 15.0, 1.03, 0.0, 0.15, 0.12, 'ceil_centimo'),
    ('es', 3.51, 5.0, 0.21, 15.0, 1.03, 0.0, 0.15, 0.12, 'ceil_centimo')])
eq('(E) el precio se enseña tal cual y no decide nada (sin veredicto ni «rentable»)', (nl['precio_objetivo'], nl['decision'], nl['rentable']),
   (99.99, None, None))
base2 = BaseFalsa(productos=[PROD_A])
filas, _r = ef.escanear([dict(LINEA_A, pa=None)], base2, keepa_de({})[0], M, HOY)
eq('(E) sin coste en la línea, ni precio objetivo ni llamada', (por(filas, 'NL')['motivo'], base2.llamadas_margen),
   ('sin coste en la línea', []))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(F) las ventas al mes de los países rentables')
base = BaseFalsa(productos=[PROD_A],
                 precios=[{'asin': 'B0AAAAAAAA', 'pais': p, 'fecha': HOY, 'seller_sku': 'SKU-' + p, 'bb_precio': precio, 'bb_logistica': 'AFN'}
                          for p, precio in (('ES', 20.0), ('IT', 9.0), ('FR', 20.0), ('DE', 20.0))],
                 tarifas=[{'seller_sku': 'SKU-' + p, 'asin': 'B0AAAAAAAA', 'pais': p, 'vigente_desde': '2026-10-01', 'mi_precio': 20.0,
                           'tarifa_referencia': 3.0, 'tarifa_gestion': 3.51} for p in ('ES', 'IT', 'FR', 'DE')])
cat = {(9, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', caidas=33)]}
keepa, falso = keepa_de(cat)
filas, _r = ef.escanear([LINEA_A], base, keepa, M, HOY)
eq('(F) IT a 9 € no es rentable y no pregunta; ES, FR y DE sí, sin caja de compra',
   (por(filas, 'IT')['rentable'], sorted((x[0], x[3]) for x in falso.llamadas)), (False, [(3, None), (4, None), (9, None)]))
eq('(F) ES: las caídas de esa pregunta', (por(filas, 'ES')['caidas_30d'], por(filas, 'ES')['caidas_fuente']), (33, 'keepa'))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(G) Keepa sin saldo')
keepa, falso = keepa_de({(9, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2000, fee=351)]}, saldo=10)
filas, _r = ef.escanear([LINEA_A], BaseFalsa(productos=[PROD_A]), keepa, M, HOY)
eq('(G) «Sin datos» con el motivo del saldo, y sin pedir productos', (por(filas, 'ES')['motivo'], falso.llamadas),
   ('Keepa sin saldo: quedaban 10 tokens y la reserva es 20', []))


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(H) la grabación de la sombra se repite igual, sin red')
cat = {(9, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2000, fee=351, caidas=12)],
       (8, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2300, fee=461, caidas=2)]}
falso = KeepaFalso(cat)
grab = ef.Grabadora(http=falso)
k1 = nv.Keepa('LLAVE-FALSA', http=grab, dormir=lambda s: None)
k1.leer_saldo()
f1, r1 = ef.escanear([LINEA_A], BaseFalsa(productos=[PROD_A]), k1, M, HOY)
paquete = grab.empaquetar()
eq('(H) 🔒 la grabación no lleva la llave', 'LLAVE-FALSA' in ef.Grabadora.desempaquetar(paquete).__repr__(), False)
rep = ef.Grabadora.repetidor(ef.Grabadora.desempaquetar(paquete))
k2 = nv.Keepa('OTRA-LLAVE', http=rep, dormir=lambda s: None)
k2.leer_saldo()
f2, r2 = ef.escanear([LINEA_A], BaseFalsa(productos=[PROD_A]), k2, M, HOY)
eq('(H) las mismas filas y los mismos tokens', (f2 == f1, r2['keepa_tokens'] == r1['keepa_tokens'], len(rep.pendientes)), (True, True, 0))
# 🔒 La sombra solo saca la grabación CIFRADA (Fernando, 16-oct-2026): con la pública se cifra, con la privada se abre.
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pem_priv = _priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode('ascii')
_pem_pub = _priv.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
cifrado = grab.cifrar(_pem_pub)
eq('(H) 🔒 el cifrado no deja ver ningún ASIN ni código de barras', ('B0AAAAAAAA' in cifrado, '8400000000017' in cifrado,
                                                                  'B0AAAAAAAA' in __import__('base64').b64decode(cifrado).decode('ascii')),
   (False, False, False))
eq('(H) …y con la privada se abre y es la misma grabación', ef.Grabadora.descifrar(cifrado, _pem_priv), ef.Grabadora.desempaquetar(paquete))
_otra = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode('ascii')
try:
    ef.Grabadora.descifrar(cifrado, _otra)
    eq('(H) 🔴 con otra privada no se abre', 'se abrió', 'no se abre')
except Exception:
    eq('(H) 🔴 con otra privada no se abre', 'no se abre', 'no se abre')


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(I) la petición mal formada no se escanea')
for nombre, lineas in (('sin líneas', []), ('sin EAN', [dict(LINEA_A, ean='')]),
                       ('línea repetida', [LINEA_A, dict(LINEA_A)])):
    try:
        ef.normalizar_lineas(lineas)
        eq('(I) %s: se rechaza' % nombre, 'pasó', 'FacturaInvalida')
    except ef.FacturaInvalida:
        eq('(I) %s: se rechaza' % nombre, 'FacturaInvalida', 'FacturaInvalida')


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(J) la sombra reconstruye las líneas que recibió el viejo')
detalle = [{'ean': '8400000000017', 'producto_id': 'p-a', 'asin': 'B0AAAAAAAA', 'pais': p, 'pa': 5.0} for p in ('ES', 'IT', 'FR', 'DE')]
detalle += [{'ean': '0000000000017', 'producto_id': 'p-c', 'asin': 'B0OTRO0000', 'pais': 'ES', 'pa': 3.0}]
lineas = ef.lineas_de_la_pasada_vieja(detalle, [PROD_A, dict(PROD_C, asin='B0CCCCCCC1')])
eq('(J) una por EAN, con su coste; ASIN solo si es el de la ficha', [(x['ean'], x['asin'], x['pa']) for x in lineas],
   [('0000000000017', None, 3.0), ('8400000000017', 'B0AAAAAAAA', 5.0)])


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(K) 🔴 muerde: el veredicto sale del heredado')
with io.open(os.path.join(AQUI, e2.RUTA_MOTOR), encoding='utf-8') as fh:
    texto = fh.read()
assert texto.count("    if margen*100 >= 10: return 'COMPRAR'") == 1
with tempfile.TemporaryDirectory() as tmp:
    ruta = os.path.join(tmp, 'heredado_roto.py')
    with io.open(ruta, 'w', encoding='utf-8') as fh:
        fh.write(texto.replace("    if margen*100 >= 10: return 'COMPRAR'", "    if margen*100 >= 99: return 'COMPRAR'"))
    keepa, falso = keepa_de({(9, 'asin', 'B0AAAAAAAA'): [producto_keepa('B0AAAAAAAA', bb=2000, fee=351, caidas=1)]})
    filas, _r = ef.escanear([LINEA_A], BaseFalsa(productos=[PROD_A]), keepa, e2.cargar_motor(ruta), HOY)
    eq('(K) con el umbral de COMPRAR roto en la copia, ES deja de ser COMPRAR', por(filas, 'ES')['decision'], 'VALORAR')


# ═══════════════════════════════════════════════════════════════════════════════
print('\n(L) 🔴 un fallo no se cuenta en el log público')
for _modo in ('verdad', 'sombra'):
    _r = subprocess.run([sys.executable, os.path.abspath(__file__), '--hijo', _modo], capture_output=True, text=True,
                        encoding='utf-8', errors='replace', cwd=AQUI, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    _salida = _r.stdout + _r.stderr
    eq('(L) %s: sale en rojo y lo dice con su línea buscable' % _modo,
       (_r.returncode, 'ESCANEO_FACTURA_NO_EJECUTADO' in _r.stdout), (1, True))
    eq('(L) 🔴 %s: ni el coste, ni el ASIN, ni el EAN, ni la fila salen por la salida' % _modo,
       [x for x in ('8.1234', 'B0SECRETO1', '8400000000017', 'Failing row') if x in _salida], [])
    eq('(L) %s: sí dice el TIPO de la excepción y dónde saltó' % _modo, 'Exception en ' in _r.stdout, True)
    if _modo == 'verdad':
        eq('(L) verdad: el detalle entero llega a motivo_fallo (privado)', 'MOTIVO_PRIVADO=1' in _r.stdout, True)

print()
if fallos:
    print('ROJO: %d fallos: %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: el escaneo de la factura usa la app de hoy o Keepa en el momento, la cuenta del viejo y NL/BE al 12 %.')
