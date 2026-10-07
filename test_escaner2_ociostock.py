# -*- coding: utf-8 -*-
"""Banco de la FOTO DE DISPONIBILIDAD DE OCIOSTOCK (encargo OC2, 07-oct-2026): escaner2_ociostock.py (las reglas) y
escaner2_ociostock_disponibilidad.py (la pasada).

SIN RED, SIN SECRETOS Y SIN BASE. 🔴 LOS DATOS SON INVENTADOS Y REDONDOS: el fichero real de OcioStock no se sube a
este repo, que es publico, y ningun precio de aqui es suyo. Solo dos filas llevan su id, su EAN y su nombre reales
(sin su precio): los dos chase que comparten EAN con una ficha nuestra normal, que el encargo pide como casos
obligatorios.

QUE PRUEBA:
  (A) LAS OCHO REGLAS, pieza a pieza: el EAN base y su cola (y que ean_core no es el campo crudo), GTIN-14, 9-11
      cifras, forma rara; caja de 6 (« C6» exacto, FUNKO con «5 + 1»; la «c» pegada NO); chase suelto (FUNKO con
      « Chase» o con «chase» al final o entre parentesis, salvo «with/w/ Chase»; nunca en otra marca); disponible
      (stock > 0 sin reserva ni prepago; stock vacio = sin dato); precio (unitario tal cual, minimo con los tramos y
      sus unidades, PA = × 0,99, sin filtro del 50 %); llave unica; cabecera exacta; huella.
  (B) LA PASADA ENTERA (runpy, como la lanza el workflow) contra una descarga y una base de mentira: el bueno aplica
      (lotes de 500, recuentos, huella con Last-Modified y ETag, el maximo de fecha_ultima_modificacion, una llamada
      a disp_aplicar_pasada); en gzip, lo mismo; «al día» en VERDE sin subir nada; cabecera cambiada, filas de menos,
      id repetido, precio raro, descarga 500 y error de red: no aplican y dicen por que.
  (C) 🔴 EL REGISTRO NO SUELTA DATOS en ningun caso: ni la URL ni su token, ni nombres, EAN, precios; y el motivo que
      queda en la base, tampoco la URL ni el token.
  (D) Sin secretos: rojo sin abrir pasada ni cliente. El rescate: solo la pasada de ESTE run, de OcioStock, leyendo.
  (E) Por estructura: el programa solo nombra disp_pasada, disp_lectura, disp_parametros y disp_aplicar_pasada; el
      workflow solo se lanza a mano, con grupo propio, los secretos en el primer paso y el rescate solo si estaban.
  (F) 🔴 LA MITAD ROJA: mutantes de las reglas y de la pasada; el banco se tiene que poner ROJO con cada uno.
"""
import ast
import contextlib
import csv
import gzip
import hashlib
import importlib.util
import io
import os
import runpy
import sys
import tempfile
import types
from decimal import Decimal

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(RAIZ, 'escaner2_ociostock.py')
PROGRAMA = os.path.join(RAIZ, 'escaner2_ociostock_disponibilidad.py')
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-ociostock-disponibilidad.yml')
sys.path.insert(0, RAIZ)
import escaner2_ociostock as OC  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def cargar(ruta, nombre):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# (A) LAS REGLAS
# ═══════════════════════════════════════════════════════════════════════════════
def fila(**k):
    """Una fila del CSV con las 54 columnas; lo que no se diga, vacio o un valor neutro."""
    base = {c: '' for c in OC.COLUMNAS}
    base.update({'id_producto': '1', 'fecha_ultima_modificacion': '2026-01-01 00:00:00', 'nombre': 'Cosa',
                 'precio_distribuidores': '10.00', 'stock_disponible': '5', 'marca': 'OTRA', 'ean': '4999999000016',
                 'disponible_para_reserva': '0', 'reserva_prepago': '0', 'last_column': '1'})
    base.update(k)
    return [base[c] for c in OC.COLUMNAS]


def una(m, **k):
    """La fila de disp_lectura de UNA fila del CSV (o la excepcion)."""
    filas, _c = m.convertir(list(m.COLUMNAS), [fila(**k)])
    return filas[0] if filas else None


def reglas(m, chk):
    """Las reglas sobre el modulo `m` (el de verdad o un mutante)."""
    # 2 · El EAN base y su cola
    chk('(A2) «889698679282 C6» → base 889698679282 y cola « C6»', m.partir_ean('889698679282 C6'), ('889698679282', ' C6'))
    chk('(A2) la «c» pegada es cola', m.partir_ean('4999999000016c'), ('4999999000016', 'c'))
    chk('(A2) espacios duros en los bordes, fuera', m.partir_ean('\xa04999999000016\xa0'), ('4999999000016', ''))
    chk('(A2) sin cifras delante: sin base', m.partir_ean('rosa'), ('', 'rosa'))
    chk('(A2) 🔴 ean_core es el EAN BASE, no el campo crudo (moloka_ean_norm dejaría el 6 pegado)',
        una(m, ean='889698679282 C6', marca='FUNKO', nombre='Figura POP Algo 5 + 1')['ean_core'], '889698679282')
    chk('(A2) 12 y 13 cifras, tal cual', (m.ean_de_cruce('499999000012'), m.ean_de_cruce('4999990000126')),
        (('499999000012', None), ('4999990000126', None)))
    chk('(A2) GTIN-14 → el EAN-13 de dentro con su dígito (la variante de variantes_ean)',
        (m.ean_de_cruce('04006381333931'), m.ean_de_cruce('14006381333938')), (('4006381333931', None), ('4006381333931', None)))
    chk('(A2) 9 a 11 cifras → rellenado con ceros hasta 13', m.ean_de_cruce('12345678901'), ('0012345678901', None))
    chk('(A2) menos de 9 cifras → forma rara, sin EAN de cruce', m.ean_de_cruce('1234567'), (None, 'ean_forma_rara'))
    _f, c = m.convertir(list(m.COLUMNAS), [fila(id_producto='1', ean=''), fila(id_producto='2', ean=' rosa'),
                                            fila(id_producto='3')])
    chk('(A2) sin EAN: se cuenta y NO entra', (len(_f), c['n_sin_gtin'], c['n_leidas'], c['n_crudo']), (1, 2, 1, 3))

    # 3 · Caja de 6
    chk('(A3) « C6» exacto → caja de 6 (de cualquier marca)', m.clasificar(' C6', 'OTRA', 'Figura'), (True, False, False))
    chk('(A3) FUNKO con «5 + 1» y sin C6 → caja de 6 con chase', m.clasificar('', 'FUNKO', 'POP Algo 5 + 1 Chase'),
        (True, True, False))
    chk('(A3) «5+1» de otra marca, NO es caja', m.clasificar('', 'OTRA', 'Algo 5+1'), (False, False, False))
    chk('(A3) 🔴 la «c» pegada NO es caja en OcioStock', una(m, ean='4999999000016c', nombre='Peluche surtido')['es_caja'],
        False)
    chk('(A3) «C6» pegado o en minúscula NO es el sufijo exacto', (m.clasificar('C6', 'FUNKO', 'x'), m.clasificar(' c6', 'FUNKO', 'x')),
        ((False, False, False), (False, False, False)))
    r = una(m, ean='4999999000016 C6', marca='FUNKO', nombre='Figura POP Algo 5 + 1', precio_distribuidores='8.00')
    chk('(A3) la caja: uds 6 y precio POR FIGURA, sin dividir', (r['es_caja'], r['uds_caja'], r['precio_unidad'],
                                                                 r['precio_catalogo']), (True, 6, 8.0, 8.0))

    # 4 · Chase suelto
    chk('(A4) FUNKO « Chase» de sufijo → chase suelto', m.clasificar(' Chase', 'FUNKO', 'Figura'), (False, True, True))
    chk('(A4) FUNKO «… Chase» al final del nombre → chase suelto', m.clasificar('', 'FUNKO', 'Figura POP Algo Chase'),
        (False, True, True))
    chk('(A4) FUNKO «(… Chase)» entre paréntesis → chase suelto', m.clasificar('', 'Funko', 'Figura POP (Glow Chase) Algo'),
        (False, True, True))
    chk('(A4) «with Chase» y «w/ Chase» NO son chase sueltos',
        (m.clasificar('', 'FUNKO', 'Figura POP Algo with Chase'), m.clasificar('', 'FUNKO', 'Figura POP Algo w/ Chase')),
        ((False, False, False), (False, False, False)))
    chk('(A4) 🔴 «Chase» de otra marca (la Patrulla Canina) NO es chase, ni de sufijo',
        (m.clasificar('', 'PLAY BY PLAY', 'Peluche Invierno Chase'), m.clasificar(' Chase', 'PLAY BY PLAY', 'Peluche')),
        ((False, False, False), (False, False, False)))
    chk('(A4) «Chase» en medio del nombre NO es chase suelto (la regla es al final o entre paréntesis)',
        m.clasificar('', 'FUNKO', 'Figura POP Chase Algo'), (False, False, False))
    # 🔴 LOS DOS CASOS OBLIGATORIOS (id, EAN y nombre reales; precio INVENTADO): comparten EAN con fichas nuestras
    #    normales y tienen stock; salen como chase y NO como la figura.
    duo = [fila(id_producto='101247', ean='889698477093', marca='FUNKO', stock_disponible='0',
                nombre='Figura POP DC Comics Batman 1989 Joker with Hat 5 + 1 Chase'),
           fila(id_producto='101248', ean='889698477093', marca='FUNKO', stock_disponible='9',
                nombre='Figura POP DC Comics Batman 1989 Joker with Hat Chase'),
           fila(id_producto='162010', ean='889698406215', marca='FUNKO', stock_disponible='0',
                nombre='Figura POP Demon Slayer Kimetsu no Yaiba Inosuke Hashibira Exclusive'),
           fila(id_producto='162587', ean='889698406215', marca='FUNKO', stock_disponible='9',
                nombre='Figura POP Demon Slayer Kimetsu no Yaiba Inosuke Hashibira Exclusive Chase')]
    f4, _c = m.convertir(list(m.COLUMNAS), duo)
    por = {x['producto_prov']: (x['ean_core'], x['es_caja'], x['es_chase'], x['regla'], x['disponible']) for x in f4}
    chk('(A4) 🔴 101248 Joker with Hat Chase: chase suelto, fuera; su 5 + 1, caja con chase',
        (por['101248'], por['101247']),
        (('889698477093', False, True, 'chase_suelto', True), ('889698477093', True, True, None, False)))
    chk('(A4) 🔴 162587 Inosuke… Exclusive Chase: chase suelto, fuera; la figura normal, figura',
        (por['162587'], por['162010']),
        (('889698406215', False, True, 'chase_suelto', True), ('889698406215', False, False, None, False)))
    chk('(A4) 🔴 …y de esos dos EAN NO queda ninguna figura disponible que se pueda leer como la figura',
        [k for k, v in por.items() if v[4] and v[3] is None and not v[1]], [])

    # 5 · Disponible
    chk('(A5) stock > 0 sin reserva: disponible', una(m, stock_disponible='3')['disponible'], True)
    chk('(A5) stock 0: agotado', una(m, stock_disponible='0')['disponible'], False)
    chk('(A5) 🔴 preventa con stock (disponible_para_reserva = 1): NO disponible, y marcada',
        (lambda x: (x['disponible'], x['preorder']))(una(m, stock_disponible='3', disponible_para_reserva='1')), (False, True))
    chk('(A5) 🔴 prepago con stock (reserva_prepago = 1): NO disponible',
        una(m, stock_disponible='3', reserva_prepago='1')['disponible'], False)
    chk('(A5) stock vacío: sin dato (ni disponible ni agotado de verdad)',
        (lambda x: (x['disponible'], x['sin_dato_disponibilidad']))(una(m, stock_disponible='')), (False, True))

    # 6 · Precio
    r = una(m, precio_distribuidores='10.00', txt_precios_volumen='6:11:9.00|12::8.00')
    chk('(A6) unitario tal cual; mínimo con los tramos y sus unidades; PA = × 0,99',
        (r['precio_catalogo'], r['precio_unidad'], r['precio_escalon'], r['uds_escalon'], r['precio_pa']),
        (10.0, 10.0, 8.0, 12, 7.92))
    r = una(m, precio_distribuidores='10.00', txt_precios_volumen='36::2.00')
    chk('(A6) 🔴 SIN el filtro del 50 %: un tramo a menos de la mitad se coge', (r['precio_escalon'], r['uds_escalon']),
        (2.0, 36))
    r = una(m, precio_distribuidores='10.00', txt_precios_volumen='6::12.00')
    chk('(A6) un tramo más caro que el unitario: gana el unitario, uds 1',
        (r['precio_escalon'], r['uds_escalon'], r['precio_pa']), (10.0, 1, 9.9))
    r = una(m, precio_distribuidores='10.00', txt_precios_volumen='')
    chk('(A6) sin tramos: el unitario, uds 1, PA × 0,99', (r['precio_escalon'], r['uds_escalon'], r['precio_pa']), (10.0, 1, 9.9))
    chk('(A6) a igual precio, el de menos unidades', m.escalon(Decimal('10'), [(6, Decimal('10'))]),
        (Decimal('10'), 1, Decimal('9.90')))
    r = una(m, precio_distribuidores='')
    chk('(A6) sin unitario: sin dato de precio y sin escalón ni PA',
        (r['sin_dato_precio'], r['precio_unidad'], r['precio_escalon'], r['uds_escalon'], r['precio_pa']),
        (True, None, None, None, None))
    for que, k in (('precio con letras', {'precio_distribuidores': '10 €'}), ('tramo de otra forma', {'txt_precios_volumen': '6-8.00'}),
                   ('stock con letras', {'stock_disponible': 'muchos'}), ('reserva que no es 0 ni 1', {'disponible_para_reserva': 'sí'})):
        try:
            m.convertir(list(m.COLUMNAS), [fila(**k)])
            chk('(A6) %s: no se inventa, LecturaInvalida' % que, 'pasa', 'LecturaInvalida')
        except m.LecturaInvalida as ex:
            chk('(A6) %s: no se inventa, LecturaInvalida (y no dice el valor)' % que, str(list(k.values())[0]) in str(ex), False)

    # 1 · La llave
    for que, filas in (('repetido', [fila(id_producto='7'), fila(id_producto='7')]), ('vacío', [fila(id_producto=' ')])):
        try:
            m.convertir(list(m.COLUMNAS), filas)
            chk('(A1) id_producto %s: LecturaInvalida' % que, 'pasa', 'LecturaInvalida')
        except m.LecturaInvalida as ex:
            chk('(A1) id_producto %s: LecturaInvalida' % que, 'id_producto' in str(ex), True)
    # La cabecera
    for que, cab, palabra in (('una de menos', list(m.COLUMNAS)[:-1], 'last_column'),
                              ('una renombrada', ['ean_13' if c == 'ean' else c for c in m.COLUMNAS], '«ean»'),
                              ('dos cambiadas de sitio', ['marca', 'product_url'] + [c for c in m.COLUMNAS if c not in ('marca', 'product_url')], 'fuera de su sitio'),
                              ('una de más', list(m.COLUMNAS) + ['nueva'], 'de más')):
        try:
            m.comprobar_cabecera(cab)
            chk('(A) cabecera con %s: LecturaInvalida' % que, 'pasa', 'LecturaInvalida')
        except m.LecturaInvalida as ex:
            chk('(A) cabecera con %s: LecturaInvalida que lo dice' % que, palabra in str(ex), True)
    # 8 · La huella y la fecha
    chk('(A8) huella = md5 y bytes', m.huella(b'abc'), ('900150983cd24fb0d6963f7d28e17f72', 3))
    _f, c = m.convertir(list(m.COLUMNAS), [fila(id_producto='1', fecha_ultima_modificacion='2026-10-07 03:23:41'),
                                            fila(id_producto='2', fecha_ultima_modificacion='2026-10-06 23:59:59'),
                                            fila(id_producto='3', fecha_ultima_modificacion='rara')])
    chk('(A8) el máximo de fecha_ultima_modificacion (una rara no cuenta)', c['fecha_max'], '2026-10-07 03:23:41')


reglas(OC, eq)


# ═══════════════════════════════════════════════════════════════════════════════
# (B-E) LA PASADA ENTERA
# ═══════════════════════════════════════════════════════════════════════════════
TOKEN = 'ab12' * 10
URL = 'https://feed.example.test/catalog_1_50_54_2_%s_csv_plain.csv' % TOKEN
CUERPO_ERROR = 'CUERPO-ERROR-SECRETO'
FILA_BASE = 'FILA-DE-LA-BASE-SECRETA'
LAST_MODIFIED = 'Wed, 07 Oct 2026 01:23:41 GMT'
ETAG = '"etag-de-mentira"'
CENTINELAS = [URL, TOKEN, 'feed.example.test', CUERPO_ERROR, FILA_BASE, 'NOMBRE-SECRETO', 'MARCA-SECRETA', '4999999',
              '10.00', '9.90', '7.50', LAST_MODIFIED, 'etag-de-mentira', 'Traceback']


def fila_inventada(g):
    """Una fila INVENTADA. g % 10: 0 sin EAN · 1 caja C6 FUNKO «5 + 1» · 2 chase suelto FUNKO de sufijo · 3 chase
    FUNKO por el nombre · 4 «c» pegada · 5 GTIN-14 · 6 preventa con stock · el resto, normales. Stock: g % 3 = 0 → 0."""
    k = g % 10
    ean = '4999999%06d' % g
    marca, nombre = 'MARCA-SECRETA', 'NOMBRE-SECRETO %d' % g
    if k == 0:
        ean = ''
    elif k == 1:
        ean, marca, nombre = '499999%06d C6' % g, 'FUNKO', 'NOMBRE-SECRETO %d 5 + 1' % g
    elif k == 2:
        ean, marca = '499999%06d Chase' % g, 'FUNKO'
    elif k == 3:
        marca, nombre = 'FUNKO', 'NOMBRE-SECRETO %d Chase' % g
    elif k == 4:
        ean += 'c'
    elif k == 5:
        ean = '1' + ean
    return fila(id_producto=str(900000 + g), ean=ean, marca=marca, nombre=nombre,
                stock_disponible='0' if g % 3 == 0 else '7', disponible_para_reserva='1' if k == 6 else '0',
                precio_distribuidores='10.00', txt_precios_volumen='6:11:9.90|12::7.50' if g % 2 else '',
                fecha_ultima_modificacion='2026-10-0%d 03:00:00' % (1 + g % 7))


def csv_inventado(n=1200, cabecera=None, cambio=None):
    filas = [fila_inventada(g) for g in range(n)]
    if cambio:
        cambio(filas)
    b = io.StringIO(newline='')
    w = csv.writer(b, delimiter=';', lineterminator='\r\n')
    w.writerow(cabecera or OC.COLUMNAS)
    w.writerows(filas)
    return b.getvalue().encode('utf-8-sig')


def esperado(n=1200):
    filas, c = OC.convertir(list(OC.COLUMNAS), [fila_inventada(g) for g in range(n)])
    return c


class _Resp:
    def __init__(self, status=200, contenido=b'', cabeceras=None):
        self.status_code, self.content = status, contenido
        self.text = contenido.decode('utf-8', 'replace')
        self.headers = cabeceras if cabeceras is not None else {'Last-Modified': LAST_MODIFIED, 'ETag': ETAG,
                                                               'Set-Cookie': 'x=' + CUERPO_ERROR}


class Web:
    def __init__(self, fichero=None, estado=200, error_red=False, cabeceras=None):
        self.fichero = csv_inventado() if fichero is None else fichero
        self.estado, self.error_red, self.cabeceras = estado, error_red, cabeceras
        self.llamadas = []

    def get(self, url, timeout=None):
        self.llamadas.append(url)
        if self.error_red:
            raise ConnectionError(f'HTTPSConnectionPool: Max retries exceeded with url: {url} ({CUERPO_ERROR})')
        if self.estado != 200:
            return _Resp(self.estado, f'<pre>{CUERPO_ERROR}</pre>'.encode())
        return _Resp(200, self.fichero, self.cabeceras)


def _modulo_requests(web, sesiones):
    m = types.ModuleType('requests')

    class Session:
        def __init__(self):
            self.headers = {}
            sesiones.append(self)

        def get(self, url, timeout=None):
            return web.get(url, timeout)

    m.Session = Session
    return m


class _Consulta:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.accion, self.datos, self.filtros = base, tabla, None, None, {}

    def insert(self, d):
        self.accion, self.datos = 'insert', d
        return self

    def update(self, d):
        self.accion, self.datos = 'update', d
        return self

    def delete(self):
        self.accion = 'delete'
        return self

    def select(self, *_a, **_k):
        self.accion = 'select'
        return self

    def eq(self, col, val):
        self.filtros[col] = val
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        b = self.base
        b.ops.append((self.tabla, self.accion, dict(self.filtros)))
        r = []
        if self.tabla == 'disp_pasada':
            if self.accion == 'insert':
                pid = 'PASADA-OCIO-%d' % (len(b.pasadas) + 1)
                b.pasadas[pid] = dict(self.datos, id=pid)
                r = [{'id': pid}]
            elif self.accion == 'update':
                p = b.pasadas.get(self.filtros.get('id'))
                if p is not None and all(p.get(k) == v for k, v in self.filtros.items()):
                    p.update(self.datos)
            elif self.accion == 'select':
                if 'id' in self.filtros:
                    r = [dict(b.pasadas[self.filtros['id']])]
                elif self.filtros.get('estado') == 'aplicada':
                    r = [{'id': 'P-ANTES', 'fichero_md5': b.ultima_md5}] if b.ultima_md5 else []
                elif self.filtros.get('estado') == 'leyendo':
                    r = [{'id': i} for i, p in b.pasadas.items()
                         if p.get('estado') == 'leyendo' and p.get('run_id') == self.filtros.get('run_id')
                         and p.get('proveedor') == self.filtros.get('proveedor')]
        elif self.tabla == 'disp_parametros' and self.accion == 'select':
            r = [{'crudo_minimo': b.minimo}]
        elif self.tabla == 'disp_lectura':
            if self.accion == 'insert':
                if b.falla_lectura:
                    raise RuntimeError(f"APIError: new row violates check constraint · Failing row contains "
                                       f"({FILA_BASE}, 4999999000001, 10.00) · {URL}")
                b.lectura.extend(self.datos)
                b.lotes.append(len(self.datos))
            elif self.accion == 'delete':
                b.lectura = [x for x in b.lectura if x['pasada_id'] != self.filtros.get('pasada_id')]
        return types.SimpleNamespace(data=r)


class Base:
    def __init__(self, minimo=1000, ultima_md5=None, falla_lectura=False):
        self.minimo, self.ultima_md5, self.falla_lectura = minimo, ultima_md5, falla_lectura
        self.ops, self.pasadas, self.lectura, self.lotes, self.rpcs = [], {}, [], [], []

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, params):
        base = self

        class _Llamada:
            def execute(self):
                base.rpcs.append((nombre, params))
                base.ops.append(('rpc', nombre, {}))
                p = base.pasadas[params['p_pasada']]
                leidas = [x for x in base.lectura if x['pasada_id'] == p['id']]
                if p.get('n_leidas') == len(leidas) and p.get('n_crudo') == p.get('n_sin_gtin', 0) + len(leidas):
                    p.update(estado='aplicada', primera=True, n_en_catalogo=len(leidas),
                             n_disponibles_estado=sum(1 for x in leidas if x['disponible']), caida_aceptada=False)
                else:
                    p.update(estado='rechazada', motivo='no cuadra (de mentira)')
                base.lectura = [x for x in base.lectura if x['pasada_id'] != p['id']]
                return types.SimpleNamespace(data={'estado': p['estado']})
        return _Llamada()


def correr(programa, web=None, base=None, argv=(), secretos=True, run_id='4242', pasadas_previas=None):
    """El programa entero, como lo lanza el workflow (runpy, __main__), con `supabase` y `requests` de mentira."""
    web = web or Web()
    base = base or Base()
    if pasadas_previas:
        base.pasadas.update(pasadas_previas)
    sesiones, clientes = [], []
    falso_supabase = types.ModuleType('supabase')

    def create_client(url, llave):
        clientes.append((url, llave))
        return base
    falso_supabase.create_client = create_client
    guardados = {k: sys.modules.get(k) for k in ('supabase', 'requests')}
    sys.modules['supabase'] = falso_supabase
    sys.modules['requests'] = _modulo_requests(web, sesiones)
    entorno = {'SUPABASE_URL': 'https://base.example.test', 'SUPABASE_SERVICE_KEY': 'LLAVE-DE-SERVICIO-SECRETA',
               'GITHUB_RUN_ID': run_id}
    if secretos:
        entorno['OCIOSTOCK_FEED_URL'] = URL
    viejo_env = {k: os.environ.get(k) for k in list(entorno) + ['OCIOSTOCK_FEED_URL']}
    os.environ.pop('OCIOSTOCK_FEED_URL', None)
    os.environ.update(entorno)
    viejo_argv = sys.argv
    sys.argv = [programa] + list(argv)
    salida = io.StringIO()
    codigo = None
    try:
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            try:
                runpy.run_path(programa, run_name='__main__')
                codigo = 0
            except SystemExit as e:
                codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = viejo_argv
        for k, v in viejo_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k, v in guardados.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return codigo, salida.getvalue(), base, web, sesiones, clientes


def _repetido(filas):
    filas[10][0] = filas[11][0]


def _precio_raro(filas):
    filas[21][OC.COLUMNAS.index('precio_distribuidores')] = '10,00 EUR'


def comprobar(programa, decir):
    """Corre los casos de la pasada sobre `programa` y llama a decir(nombre, obtenido, esperado)."""
    salidas, motivos = {}, {}

    def pasada_de(base):
        return next(iter(base.pasadas.values())) if base.pasadas else {}

    e = esperado()
    # (B) el bueno
    cod, out, base, web, _s, _c = correr(programa)
    salidas['bueno'] = out
    p = pasada_de(base)
    decir('(B) el bueno: sale bien y la pasada queda aplicada', (cod, p.get('estado')), (0, 'aplicada'))
    decir('(B) …baja UNA vez, de la URL del secreto', web.llamadas, [URL])
    decir('(B) …declarado = llegados = filas; sin EAN contados; repetidos a 0',
          tuple(p.get(k) for k in ('n_declarado', 'n_crudo', 'n_declarado_precios', 'n_precios', 'n_declarado_disponibilidades',
                                   'n_disponibilidades', 'n_sin_gtin', 'n_duplicados')), (1200,) * 6 + (e['n_sin_gtin'], 0))
    decir('(B) …leídas, disponibles, agotados y sin dato, los de las reglas',
          tuple(p.get(k) for k in ('n_leidas', 'n_disponibles', 'n_agotados', 'n_sin_dato_disponibilidad', 'n_sin_dato_precio')),
          (e['n_leidas'], e['n_disponibles'], e['n_agotados'], 0, 0))
    decir('(B) …la huella: md5, bytes, Last-Modified, ETag y el máximo de fecha_ultima_modificacion',
          tuple(p.get(k) for k in ('fichero_md5', 'fichero_bytes', 'http_last_modified', 'http_etag', 'fichero_fecha_max')),
          (hashlib.md5(web.fichero).hexdigest(), len(web.fichero), LAST_MODIFIED, ETAG, '2026-10-07 03:00:00'))
    decir('(B) …en lotes de 500 y UNA llamada a disp_aplicar_pasada; disp_lectura vacía al acabar',
          (base.lotes, [r[0] for r in base.rpcs], base.lectura), ([500, 500, 80], ['disp_aplicar_pasada'], []))
    decir('(B) …las cuentas de las reglas, en el registro',
          all(s in out for s in ('chase sueltos %d' % e['n_chase_suelto'], 'cajas de 6 %d' % e['n_cajas'],
                                 'con stock %d' % e['n_preventa_con_stock'])), True)
    # Lo subido, fila a fila, con una base que no aplica (para verlo)
    base_v = Base()
    base_v.rpc = lambda n, p: types.SimpleNamespace(execute=lambda: base_v.rpcs.append((n, p)))
    correr(programa, base=base_v)
    subidas = {x['producto_prov']: x for x in base_v.lectura}
    decir('(B) …lo subido son las filas de las reglas, una por id_producto',
          sorted(subidas) == sorted(x['producto_prov'] for x in OC.convertir(list(OC.COLUMNAS),
                                                                               [fila_inventada(g) for g in range(1200)])[0])
          and all(set(x) >= {'precio_escalon', 'uds_escalon', 'precio_pa', 'pasada_id'} for x in subidas.values()), True)
    # gzip: lo mismo, con la huella del descomprimido
    cod_g, out_g, base_g, web_g, _s, _c = correr(programa, web=Web(fichero=gzip.compress(csv_inventado())))
    salidas['gzip'] = out_g
    pg = pasada_de(base_g)
    decir('(B) en gzip: aplica igual, y la huella es la del CSV', (cod_g, pg.get('estado'), pg.get('n_leidas'), pg.get('fichero_md5')),
          (0, 'aplicada', e['n_leidas'], hashlib.md5(csv_inventado()).hexdigest()))
    # Sin Last-Modified ni ETag: nulos
    cod_h, out_h, base_h, _w, _s, _c = correr(programa, web=Web(cabeceras={}))
    salidas['sin cabeceras'] = out_h
    decir('(B) sin Last-Modified ni ETag: la pasada aplica y los deja vacíos',
          (cod_h, pasada_de(base_h).get('http_last_modified'), pasada_de(base_h).get('http_etag')), (0, None, None))

    # (B) al día
    md5 = hashlib.md5(csv_inventado()).hexdigest()
    cod_a, out_a, base_a, _w, _s, _c = correr(programa, base=Base(ultima_md5=md5))
    salidas['al día'] = out_a
    pa = pasada_de(base_a)
    decir('(B) 🔑 «al día»: el md5 de la última aplicada → VERDE, rechazada «al día», sin subir nada ni aplicar',
          (cod_a, 'OCIOSTOCK_AL_DIA' in out_a, pa.get('estado'), (pa.get('motivo') or '')[:7], base_a.lotes, base_a.rpcs,
           pa.get('fichero_md5')), (0, True, 'rechazada', 'al día:', [], [], md5))
    cod_o, out_o, base_o, _w, _s, _c = correr(programa, base=Base(ultima_md5='0' * 32))
    salidas['otro md5'] = out_o
    decir('(B) con otro md5 en la última aplicada: aplica', (cod_o, pasada_de(base_o).get('estado')), (0, 'aplicada'))

    # (B) no aplican y dicen por qué
    casos = [
        ('cabecera cambiada', Web(fichero=csv_inventado(cabecera=['ean_13' if c == 'ean' else c for c in OC.COLUMNAS])),
         Base(), 'fallida', '«ean»'),
        ('filas de menos', Web(fichero=csv_inventado(n=900)), Base(), 'rechazada_vaciado', 'mínimo 1000'),
        ('id repetido', Web(fichero=csv_inventado(cambio=_repetido)), Base(), 'fallida', 'id_producto repetido'),
        ('precio raro', Web(fichero=csv_inventado(cambio=_precio_raro)), Base(), 'fallida', 'precio_distribuidores'),
        ('descarga 500', Web(estado=500), Base(), 'fallida', 'respondió 500'),
        ('no es utf-8', Web(fichero=b'\xff\xfe' + 'id_producto;'.encode('utf-16-le')), Base(), 'fallida', 'utf-8'),
        ('error de red', Web(error_red=True), Base(), 'fallida', 'ConnectionError'),
        ('la base rechaza una fila', Web(), Base(falla_lectura=True), 'fallida', 'RuntimeError'),
    ]
    for nombre, w, b, estado, palabra in casos:
        cod_x, out_x, base_x, _w, _s, _c = correr(programa, web=w, base=b)
        salidas[nombre] = out_x
        px = pasada_de(base_x)
        motivos[nombre] = px.get('motivo') or ''
        decir('(B) %s: ROJO, la pasada %s y dice por qué, sin aplicar ni dejar filas' % (nombre, estado),
              (cod_x, px.get('estado'), palabra in motivos[nombre], base_x.rpcs, base_x.lectura, 'OCIOSTOCK_NO_APLICADA' in out_x),
              (1, estado, True, [], [], True))

    # (C) el registro no suelta datos
    for nombre, out_x in salidas.items():
        decir('(C) 🔴 el registro de «%s» no suelta la URL, su token, nombres, EAN, precios ni cabeceras' % nombre,
              [c for c in CENTINELAS if c in out_x], [])
    for nombre, mot in motivos.items():
        decir('(C) 🔴 el motivo de «%s» en la base no lleva la URL ni su token' % nombre,
              [c for c in (URL, TOKEN, 'feed.example.test') if c in mot], [])

    # (D) sin secretos y rescate
    cod_s, out_s, base_s, web_s, ses_s, cli_s = correr(programa, secretos=False)
    decir('(D) sin OCIOSTOCK_FEED_URL: rojo sin abrir pasada ni cliente', (cod_s, base_s.ops, cli_s, web_s.llamadas,
                                                                          'OCIOSTOCK_NO_EJECUTADA' in out_s), (1, [], [], [], True))
    previas = {'P-ESTE': {'id': 'P-ESTE', 'proveedor': 'OCIOSTOCK', 'estado': 'leyendo', 'run_id': 4242},
               'P-OTRO-RUN': {'id': 'P-OTRO-RUN', 'proveedor': 'OCIOSTOCK', 'estado': 'leyendo', 'run_id': 1},
               'P-OSMA': {'id': 'P-OSMA', 'proveedor': 'OSMA', 'estado': 'leyendo', 'run_id': 4242}}
    cod_r, out_r, base_r, web_r, _s, _c = correr(programa, argv=['--rescate'], pasadas_previas=previas)
    decir('(D) el rescate: solo la de ESTE run, de OcioStock y leyendo; sin bajar nada',
          (cod_r, {k: v['estado'] for k, v in base_r.pasadas.items()}, web_r.llamadas),
          (0, {'P-ESTE': 'fallida', 'P-OTRO-RUN': 'leyendo', 'P-OSMA': 'leyendo'}, []))


comprobar(PROGRAMA, eq)


# (E) por estructura
def _textos_de(ruta):
    arbol = ast.parse(open(ruta, encoding='utf-8').read())
    tablas, rpcs = set(), set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.args and isinstance(n.args[0], ast.Constant):
            if n.func.attr == 'table':
                tablas.add(n.args[0].value)
            elif n.func.attr == 'rpc':
                rpcs.add(n.args[0].value)
    return tablas, rpcs


eq('(E) el programa solo nombra disp_pasada, disp_lectura y disp_parametros, y solo llama a disp_aplicar_pasada',
   _textos_de(PROGRAMA), ({'disp_pasada', 'disp_lectura', 'disp_parametros'}, {'disp_aplicar_pasada'}))
eq('(E) el módulo de las reglas no habla con nada (ni table, ni rpc, ni print, ni requests)',
   (_textos_de(MODULO), [n.func.id for n in ast.walk(ast.parse(open(MODULO, encoding='utf-8').read()))
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'print'],
    'requests' in open(MODULO, encoding='utf-8').read()), ((set(), set()), [], False))
wf = yaml.safe_load(open(WORKFLOW, encoding='utf-8'))
_on = wf.get('on', wf.get(True))
pasos = wf['jobs']['leer']['steps']
eq('(E) el workflow: solo a mano, sin reloj, grupo propio sin cancelar',
   (list(_on), wf['concurrency']), (['workflow_dispatch'], {'group': 'escaner2-ociostock', 'cancel-in-progress': False}))
eq('(E) …los secretos, en el primer paso; el rescate, el último y solo si estaban',
   (pasos[0].get('id'), 'OCIOSTOCK_FEED_URL' in pasos[0]['env'], pasos[-1]['if'], '--rescate' in pasos[-1]['run']),
   ('secretos', True, "(failure() || cancelled()) && steps.secretos.outcome == 'success'", True))
eq('(E) …y el secreto del fichero solo llega al paso que lo usa (y al de comprobar)',
   [i for i, s in enumerate(pasos) if 'OCIOSTOCK_FEED_URL' in (s.get('env') or {})], [0, 4])


# ═══════════════════════════════════════════════════════════════════════════════
# (F) LA MITAD ROJA
# ═══════════════════════════════════════════════════════════════════════════════
def mutar(ruta, antes, despues, carpeta, nombre):
    texto = open(ruta, encoding='utf-8').read()
    assert texto.count(antes) == 1, 'el ancla del mutante «%s» no es única (%d)' % (nombre, texto.count(antes))
    destino = os.path.join(carpeta, os.path.basename(ruta))
    with open(destino, 'w', encoding='utf-8', newline='') as f:
        f.write(texto.replace(antes, despues))
    return destino


MUTANTES_REGLAS = [
    ('el chase en cualquier marca', "funko = (marca or '').strip().upper() == MARCA_CHASE_Y_CAJA", 'funko = True'),
    ('la «c» pegada como caja', "    if cola == ' C6':", "    if cola in (' C6', 'c'):"),
    ('ean_core del campo crudo', '        core, regla = ean_de_cruce(base)',
     "        core, regla = ean_de_cruce(re.sub(r'\\D', '', v('ean')))"),
    ('la preventa con stock disponible', '        disponible = con_stock and not preventa', '        disponible = con_stock'),
    ('el filtro del 50 % del viejo', "[(pr, u) for u, pr in lista_tramos]", "[(pr, u) for u, pr in lista_tramos if pr >= unitario / 2]"),
    ('sin el 1 %', "DESCUENTO_TRANSFERENCIA = Decimal('0.99')", "DESCUENTO_TRANSFERENCIA = Decimal('1')"),
    ('la caja dividida entre 6', "'precio_unidad': _decimal_a_base(unitario)",
     "'precio_unidad': _decimal_a_base(unitario / UDS_CAJA if es_caja and unitario else unitario)"),
    ('«with Chase» como chase', "and not _RE_CON_CHASE.search(nombre)", ''),
    ('sin EAN entra', "        if not base:\n            c['n_sin_gtin'] += 1\n            continue\n", ''),
    ('el GTIN-14 tal cual', "        return base[1:13] + _chk13(base[1:13]), None", "        return None, 'ean_forma_rara'"),
]
MUTANTES_PASADA = [
    ('«al día» en rojo', "            return 0\n        print(f\"OCIOSTOCK_NO_APLICADA", "            return 1\n        print(f\"OCIOSTOCK_NO_APLICADA"),
    ('sin «al día»', "        if ult[0].get('fichero_md5') == md5:\n            raise AlDia(ult[0].get('id'))\n", ''),
    ('imprime el error', "motivo_log = f'error inesperado ({type(ex).__name__}); el detalle queda en disp_pasada.motivo'",
     "motivo_log = f'error inesperado: {ex}'"),
    ('el motivo sin limpiar', "limpio(f'{type(ex).__name__}: {ex}', url)", "f'{type(ex).__name__}: {ex}'"),
    ('sin mínimo de filas', "        if n < minimo:", "        if False:"),
    ('sin la huella', "        sb.table('disp_pasada').update(huella).eq('id', pid).execute()\n", ''),
]
with tempfile.TemporaryDirectory() as tmp:
    for nombre, antes, despues in MUTANTES_REGLAS:
        d = os.path.join(tmp, 'r_' + str(abs(hash(nombre))))
        os.makedirs(d)
        m = cargar(mutar(MODULO, antes, despues, d, nombre), 'mutante_' + str(abs(hash(nombre))))
        rotos = []
        try:
            reglas(m, lambda n, o, e: rotos.append(n) if o != e else None)
        except Exception as ex:  # un mutante que revienta tambien es rojo
            rotos.append(type(ex).__name__)
        eq('(F) 🔴 el banco se pone ROJO con el mutante de las reglas «%s»' % nombre, bool(rotos), True)
    for nombre, antes, despues in MUTANTES_PASADA:
        d = os.path.join(tmp, 'p_' + str(abs(hash(nombre))))
        os.makedirs(d)
        prog = mutar(PROGRAMA, antes, despues, d, nombre)
        rotos = []
        comprobar(prog, lambda n, o, e: rotos.append(n) if o != e else None)
        eq('(F) 🔴 el banco se pone ROJO con el mutante de la pasada «%s»' % nombre, bool(rotos), True)

print()
if fallos:
    print('ROJO: %d comprobación(es) fallida(s):' % len(fallos))
    for f in fallos:
        print('   - ' + f)
    sys.exit(1)
print('VERDE: todas las comprobaciones pasan.')
