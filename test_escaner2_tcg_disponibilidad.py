# -*- coding: utf-8 -*-
"""Banco de la PASADA DE DISPONIBILIDAD DE TCG Y SU LECTOR DE TRAMOS (encargo T2, 13-oct-2026):
escaner2_tcg_disponibilidad.py, escaner2_tcg_web.py y su workflow.

SIN RED, SIN SECRETOS Y SIN BASE: el programa entero (principal) con una web de TCG de mentira (login, Excel, fichas,
listado) y una base de mentira en memoria. 🔴 DATOS INVENTADOS (repo publico): el Excel y las fichas los fabrica
test_escaner2_tcg.py (se cargan sus funciones sin correr ese banco).

QUE PRUEBA:
  (B) la primera pasada aplica (lotes, recuentos, huella de contenido, sin cociente: el suelto con su aviso) y el
      lector guarda cada ficha (ok con su cociente, sin ficha, de otro EAN); la segunda usa los cocientes y cambia la
      huella; la tercera, igual, sale «al día» en VERDE y el lector sigue; los fallidos no se repiten antes de 24 h;
  (C) 🔴 AL PRIMER BLOQUEO PARA: un 429 en la segunda ficha deja guardada la primera, ni una peticion mas, Telegram y
      ROJO; una ficha que no se entiende (sin sesion) se apunta 'no_entendida', para y ROJO; la web que no deja entrar
      deja la pasada 'fallida', Telegram, ROJO y ni una ficha;
  (D) el listado (LISTADO=si) marca lo que ya no cuadra y esa ficha se relee en la misma corrida;
  (E) guardas: Excel que no se entiende → 'fallida'; por debajo de los minimos → 'rechazada_vaciado'; sin secretos,
      rojo sin abrir pasada; el rescate, solo la pasada de ESTE run;
  (F) 🔴 EL REGISTRO NO SUELTA DATOS: ni la URL de la web, ni el usuario o la clave, ni un EAN, ni un precio, ni el
      texto de un error (que sí queda, limpio de URLs y secretos, en disp_pasada.motivo); y el Telegram, tampoco URLs;
  (G) el ritmo: cada peticion lleva su pausa de 1,5 a 4 s y, cada 20 a 40, una mas larga;
  (H) por estructura: el workflow solo se lanza a mano, con grupo propio, los secretos en el primer paso, los inputs
      por env:, el rescate solo si los secretos estaban, y sin artefactos; descargar-tcg.yml ya no esta.
"""
import contextlib
import io
import json
import os
import random
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-tcg-disponibilidad.yml')

# El Excel y las fichas inventadas del banco de las reglas, sin correr ese banco: solo sus funciones.
_fuente = open(os.path.join(RAIZ, 'test_escaner2_tcg.py'), encoding='utf-8').read()
_ns = {'__file__': os.path.join(RAIZ, 'test_escaner2_tcg.py')}
exec(compile(_fuente.split('# ── (A) El Excel')[0], 'test_escaner2_tcg.py', 'exec'), _ns)
fila, excel = _ns['fila'], _ns['excel']
_cab = _fuente.split('# ── (C) La ficha')[1].split('\n', 1)[1].split('TABLA = ')[0]
exec(compile(_cab, 'test_escaner2_tcg.py', 'exec'), _ns)
ficha_html = _ns['ficha']
_dl = _fuente.split('# ── (D) El listado')[1].split('\n', 1)[1].split('U = ')[0]
exec(compile(_dl, 'test_escaner2_tcg.py', 'exec'), _ns)
tarjeta = _ns['tarjeta']

import escaner2_novedades as nv  # noqa: E402
import escaner2_tcg_disponibilidad as prog  # noqa: E402
import escaner2_tcg_web as tw  # noqa: E402

fallos = []
USUARIO, CLAVE = 'USUARIO-TCG-SECRETO', 'CLAVE-TCG-SECRETA'
ENV = {'TCG_USER': USUARIO, 'TCG_PASS': CLAVE, 'SUPABASE_URL': 'https://base.invalid', 'SUPABASE_SERVICE_KEY': 'k',
       'GITHUB_RUN_ID': '777', 'LISTADO': 'no'}


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ── La base de mentira ────────────────────────────────────────────────────────────────────
class _R:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.op, self.datos, self.filtros = base, tabla, 'select', None, []
        self.orden, self.desc, self.lim, self.rango, self.conflicto = None, False, None, None, None

    def select(self, *_a, **_k):
        self.op = 'select'; return self

    def insert(self, d):
        self.op, self.datos = 'insert', d; return self

    def update(self, d):
        self.op, self.datos = 'update', d; return self

    def upsert(self, d, on_conflict=None):
        self.op, self.datos, self.conflicto = 'upsert', d, on_conflict; return self

    def delete(self):
        self.op = 'delete'; return self

    def eq(self, k, v):
        self.filtros.append((k, lambda x, v=v: x == v)); return self

    def in_(self, k, vals):
        s = set(vals); self.filtros.append((k, lambda x, s=s: x in s)); return self

    def order(self, k, desc=False):
        self.orden, self.desc = k, desc; return self

    def limit(self, n):
        self.lim = n; return self

    def range(self, a, b):
        self.rango = (a, b); return self

    def execute(self):
        b = self.base
        b.llamadas.append((self.tabla, self.op))
        filas = b.t.setdefault(self.tabla, [])
        ok = [f for f in filas if all(p(f.get(k)) for k, p in self.filtros)]
        if self.op == 'insert':
            if self.tabla == 'disp_lectura' and b.falla_lectura:
                raise RuntimeError('Failing row contains (%s, https://tcgfactory.com/es/x.html, %s)' % (b.falla_lectura, CLAVE))
            nuevas = self.datos if isinstance(self.datos, list) else [self.datos]
            if self.tabla == 'disp_lectura':
                b.lotes.append(len(nuevas))
            out = []
            for n in nuevas:
                n = dict(n)
                if self.tabla == 'disp_pasada':
                    n.setdefault('id', 'PASADA-TCG-%d' % (len(filas) + 1))
                    n.setdefault('creada_en', '2026-10-13T16:%02d:00+00:00' % len(filas))  # en orden, sin empates
                filas.append(n)
                out.append(n)
            return _R(out)
        if self.op == 'update':
            for f in ok:
                f.update(self.datos)
            return _R(ok)
        if self.op == 'delete':
            b.t[self.tabla] = [f for f in filas if f not in ok]
            return _R(ok)
        if self.op == 'upsert':
            claves = self.conflicto.split(',')
            d = json.loads(json.dumps(self.datos))  # lo que de verdad viaja: JSON (un Decimal suelto reventaria aqui)
            prev = next((f for f in filas if all(f.get(k) == d.get(k) for k in claves)), None)
            if prev is None:
                filas.append(d)
            else:
                prev.update(d)
            return _R([d])
        if self.orden:
            ok = sorted(ok, key=lambda f: str(f.get(self.orden)), reverse=self.desc)
        if self.rango:
            ok = ok[self.rango[0]:self.rango[1] + 1]
        if self.lim is not None:
            ok = ok[:self.lim]
        return _R([dict(f) for f in ok])


class Base:
    def __init__(self, crudo_minimo=5, disponibles_minimo=2):
        self.t = {'disp_parametros': [{'proveedor': 'TCG', 'crudo_minimo': crudo_minimo,
                                       'disponibles_minimo': disponibles_minimo}]}
        self.lotes, self.rpcs, self.llamadas = [], [], []
        self.falla_lectura = None
        self.lectura_aplicada = {}

    def table(self, n):
        return _Q(self, n)

    def rpc(self, nombre, params):
        base = self

        class _L:
            def execute(self):
                base.rpcs.append((nombre, params))
                pid = params['p_pasada']
                lect = [f for f in base.t.get('disp_lectura', []) if f['pasada_id'] == pid]
                base.lectura_aplicada[pid] = lect
                for p in base.t['disp_pasada']:
                    if p['id'] == pid and p.get('n_leidas') == len(lect):
                        p.update(estado='aplicada', primera=True, caida_aceptada=False, n_en_catalogo=len(lect),
                                 n_disponibles_estado=sum(1 for x in lect if x['disponible']))
                return _R(None)
        return _L()

    def pasadas(self):
        return self.t.get('disp_pasada', [])

    def tramo(self, k):
        return next((f for f in self.t.get('disp_tramo', []) if f['producto_prov'] == k), None)


# ── La web de mentira ─────────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, codigo=200, texto='', contenido=None, js=None):
        self.status_code, self.text = codigo, texto
        self.content = contenido if contenido is not None else texto.encode('utf-8')
        self._js = js
        self.headers = {}

    def json(self):
        if self._js is None:
            raise ValueError('no es JSON')
        return self._js


LOGIN = ('<html><body><form action="https://tcgfactory.com/es/iniciar-sesion" method="post">'
         '<input type="hidden" name="back" value="my-account"><input type="email" name="email">'
         '<input type="password" name="password"><button>Entrar</button></form></body></html>')
DENTRO = '<html><body class="usuariologeado"><a href="/es/?mylogout=">Cerrar sesión</a></body></html>'
SLUG = 'cosa-inventada-%s'
URL_FICHA = 'https://tcgfactory.com/es/distribucion/' + SLUG + '.html'
FORM = ('<html><body><form id="af_form"><input type="hidden" name="id_category" value="70">'
        '<input type="hidden" name="nb_items" value="27"><input type="hidden" name="page" value="1">'
        '<label><input type="checkbox" name="f[53][]" value="a1"><span class="name">Disponible</span></label></form>'
        '</body></html>')


class Web:
    """La web de TCG inventada. `fichas`: {ean: html | 404 | 429}; `tarjetas`: html del listado (todas en una pagina)."""

    def __init__(self, contenido, fichas, login=200, tarjetas=''):
        self.contenido, self.fichas, self.login, self.tarjetas = contenido, fichas, login, tarjetas
        self.dentro = False
        self.pedidas = []

    def get(self, url, **_k):
        self.pedidas.append(('GET', url))
        if url in tw.LOGIN_URLS or url.endswith('/es/mi-cuenta'):
            if self.login != 200:
                return _Resp(self.login, 'Access denied')
            return _Resp(200, DENTRO if self.dentro else LOGIN)
        if url == tw.EXCEL_URL:
            return _Resp(200, '', self.contenido)
        if url.startswith('https://tcgfactory.com/es/distribucion/'):
            ean = url[len('https://tcgfactory.com/es/distribucion/cosa-inventada-'):-len('.html')]
            h = self.fichas.get(ean, 404)
            if isinstance(h, int):
                return _Resp(h, 'Too Many Requests' if h == 429 else 'No encontrado')
            return _Resp(200, h)
        if url.startswith('https://tcgfactory.com/es/distribucion-') or url.endswith('/trading-card-games'):
            return _Resp(200, FORM)
        return _Resp(404, 'no')

    def post(self, url, data=None, **_k):
        self.pedidas.append(('POST', url))
        if url == 'https://tcgfactory.com/es/iniciar-sesion':
            ok = data.get('email') == USUARIO and data.get('password') == CLAVE
            self.dentro = ok
            return _Resp(200, DENTRO if ok else LOGIN)
        if url == tw.FILTRO_URL:
            return _Resp(200, '{}', js={'product_list_html': self.tarjetas, 'products_num': 3})
        return _Resp(404, 'no')

    def fichas_pedidas(self):
        return [u for m, u in self.pedidas if '/es/distribucion/' in u]


# El catálogo: 6 filas, 4 disponibles (A, B, C, D), una caja disponible (E) y una agotada (F).
EANS = {'A': '8000000000017', 'B': '8000000000024', 'C': '8000000000031', 'D': '8000000000048', 'E': '800000000055C',
        'F': '8000000000062'}


def catalogo(**precios):
    filas = [fila(EANS[k], precio=float(precios.get(k, 10.0)), imagen='https://tcgfactory.com/%d-large_default/%s.jpg'
                  % (i + 1, SLUG % EANS[k].lower())) for i, k in enumerate('ABCD')]
    filas.append(fila(EANS['E'], precio=60.0, nombre='Funko POP! Case 5+1 Chase',
                      imagen='https://tcgfactory.com/9-large_default/%s.jpg' % (SLUG % EANS['E'].lower())))
    filas.append(fila(EANS['F'], stock=0, imagen='https://tcgfactory.com/8-large_default/%s.jpg' % (SLUG % EANS['F'].lower())))
    return excel(filas)


TABLA = [(2, '10.000000', '0.005800'), (12, '10.000000', '0.023400')]
FICHAS = {EANS['A'].lower(): ficha_html(tabla=TABLA, eans=(EANS['A'],)),
          EANS['B'].lower(): 404,
          EANS['C'].lower(): ficha_html(tabla=TABLA, eans=('8000000000999',)),
          EANS['D'].lower(): ficha_html(precio='10.00', eans=(EANS['D'],)),
          EANS['E'].lower(): ficha_html(precio='60.00', tabla=[(2, '60.000000', '0.050000')],
                                        eans=('01' + '10800000000052' + '2110000',))}


def correr(base, web, env=None, argv=()):
    """principal() con todo de mentira. Devuelve (codigo, registro)."""
    salida = io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(salida):
        try:
            codigo = prog.principal(list(argv), env=dict(ENV, **(env or {})), sb=base, sesion=web, dormir=lambda s: None)
        except SystemExit as ex:
            codigo = ex.code
    return codigo, salida.getvalue()


PROHIBIDO = ['tcgfactory', USUARIO, CLAVE, '8000000000', '800000000055', '9.766', '9,77', '10.00', '60.0', '0.9766',
             'cosa-inventada']


def limpio(nombre, registro):
    sucio = [p for p in PROHIBIDO if p in registro]
    eq(nombre + ': el registro no suelta URL, usuario, clave, EAN ni precios', sucio, [])


telegramas = []
os.environ['TELEGRAM_TOKEN'], os.environ['TELEGRAM_CHAT_ID'] = 'TOKEN-TG', 'CHAT-TG'
nv._post_de_verdad = lambda url, data, timeout: (telegramas.append(data['text']), types.SimpleNamespace(status_code=200))[1]

# ── (B) Primera, segunda y tercera pasada ────────────────────────────────────────────────
base = Base()
web = Web(catalogo(), FICHAS)
codigo, reg = correr(base, web)
print(reg)
p1 = base.pasadas()[0]
eq('B1 primera: código 0 y la pasada aplicada', (codigo, p1['estado']), (0, 'aplicada'))
eq('B2 recuentos: crudo 6, sin repetidas, leídas 6, disponibles 5', (p1['n_crudo'], p1['n_duplicados'], p1['n_leidas'],
                                                                     p1['n_disponibles']), (6, 0, 6, 5))
eq('B3 una llamada a disp_aplicar_pasada, un lote', ([n for n, _p in base.rpcs], base.lotes), (['disp_aplicar_pasada'], [6]))
lect = {f['producto_prov']: f for f in base.lectura_aplicada[p1['id']]}
eq('B4 sin cociente todavía: el suelto, 1 ud y «sin tramo leído»', (lect[EANS['A']]['precio_pa'], lect[EANS['A']]['uds_escalon'],
                                                                   lect[EANS['A']]['aviso']), (10.0, 1, 'sin tramo leído'))
eq('B5 la huella de contenido queda en la pasada', len(p1.get('huella_contenido') or ''), 32)
eq('B6 el lector: la ficha de A, ok con su cociente (texto exacto)', (base.tramo(EANS['A'])['intento_resultado'],
                                                                      base.tramo(EANS['A'])['cociente'],
                                                                      base.tramo(EANS['A'])['uds_mas_barato'],
                                                                      base.tramo(EANS['A'])['precio_excel']),
   ('ok', '0.976600000000', 12, '10'))  # openpyxl devuelve un 10.0 guardado como entero
eq('B7 B sin ficha (404), C de otro EAN: apuntados, sin cociente', (base.tramo(EANS['B'])['intento_resultado'],
                                                                     base.tramo(EANS['B']).get('cociente'),
                                                                     base.tramo(EANS['C'])['intento_resultado'],
                                                                     base.tramo(EANS['C']).get('cociente')),
   ('sin_ficha', None, 'otro_ean', None))
eq('B8 la caja E (GS1 largo en la web): ok', base.tramo(EANS['E'])['intento_resultado'], 'ok')
eq('B9 la agotada F: ni se pide', EANS['F'].lower() in ' '.join(web.fichas_pedidas()), False)
eq('B10 la lectura de A, entera', sorted(k for k, v in base.tramo(EANS['A']).items() if v is None), ['pide_relectura'])
eq('B11 un login y un Excel', ([u for m, u in web.pedidas].count(tw.EXCEL_URL),
                               [u for m, u in web.pedidas if m == 'POST'].count('https://tcgfactory.com/es/iniciar-sesion')), (1, 1))
limpio('B12', reg)

web2 = Web(catalogo(), FICHAS)
codigo, reg = correr(base, web2)
p2 = base.pasadas()[1]
lect2 = {f['producto_prov']: f for f in base.lectura_aplicada[p2['id']]}
eq('B13 segunda: aplicada y con otra huella (los cocientes)', (codigo, p2['estado'], p2['huella_contenido'] != p1['huella_contenido']),
   (0, 'aplicada', True))
eq('B14 A con el precio del tramo: Precio × cociente, 12 uds, sin aviso',
   (round(lect2[EANS['A']]['precio_pa'], 6), lect2[EANS['A']]['uds_escalon'], lect2[EANS['A']]['aviso']), (9.766, 12, None))
eq('B15 la caja E por figura y en figuras', (round(lect2[EANS['E']]['precio_pa'], 6), lect2[EANS['E']]['uds_escalon']),
   (9.5, 12))
eq('B16 los fallidos de hace un rato no se repiten', web2.fichas_pedidas(), [])
limpio('B17', reg)

web3 = Web(catalogo(), FICHAS)
codigo, reg = correr(base, web3)
p3 = base.pasadas()[2]
eq('B18 tercera, mismo contenido: «al día» en VERDE, sin subir nada', (codigo, p3['estado'], 'TCG_AL_DIA' in reg,
                                                                       base.lotes), (0, 'rechazada', True, [6, 6]))
eq('B19 al día, el lector corre (y no le toca ninguna)', '>>> TRAMOS:' in reg and 'pendientes 0' in reg, True)
# El Excel con otro precio para A: el cociente se aplica al Precio nuevo (la web no se ha mirado).
web4 = Web(catalogo(A=11), FICHAS)
codigo, reg = correr(base, web4)
p4 = base.pasadas()[3]
eq('B20 Precio nuevo × el mismo cociente', round({f['producto_prov']: f for f in base.lectura_aplicada[p4['id']]}[EANS['A']]['precio_pa'], 6),
   round(11 * 0.9766, 6))

# ── (C) Paradas ──────────────────────────────────────────────────────────────────────────
telegramas.clear()
base = Base()
f429 = dict(FICHAS)
f429[EANS['B'].lower()] = 429
web = Web(catalogo(), f429)
codigo, reg = correr(base, web)
eq('C1 un 429: ROJO y TCG_TRAMOS_PARADO', (codigo, 'TCG_TRAMOS_PARADO' in reg), (1, True))
eq('C2 lo leído antes queda guardado; ni una ficha más tras el 429',
   (base.tramo(EANS['A'])['intento_resultado'], base.tramo(EANS['B']), len(web.fichas_pedidas())), ('ok', None, 2))
eq('C3 la pasada de la foto sí está aplicada', base.pasadas()[0]['estado'], 'aplicada')
eq('C4 Telegram de la parada, sin URLs ni EAN', (len(telegramas), any(p in ''.join(telegramas) for p in PROHIBIDO)), (1, False))
limpio('C5', reg)

base = Base()
fsin = dict(FICHAS)
fsin[EANS['A'].lower()] = ficha_html(tabla=TABLA, eans=(EANS['A'],), sesion=False)
web = Web(catalogo(), fsin)
codigo, reg = correr(base, web)
eq('C6 una ficha sin sesión: no_entendida, ROJO, para ahí', (codigo, base.tramo(EANS['A'])['intento_resultado'],
                                                              base.tramo(EANS['A']).get('cociente'), len(web.fichas_pedidas())),
   (1, 'no_entendida', None, 1))
limpio('C7', reg)

# Una ficha que lleva a una categoría: sin ficha y se sigue; cinco seguidas sin producto: para.
base = Base()
fcat = dict(FICHAS)
fcat[EANS['A'].lower()] = ficha_html(tabla=TABLA, eans=(EANS['A'],)).replace('id="product"', 'id="category"')
web = Web(catalogo(), fcat)
codigo, reg = correr(base, web)
eq('C6b la URL lleva a una categoría: sin_ficha y sigue con las demás', (codigo, base.tramo(EANS['A'])['intento_resultado'],
                                                                       len(web.fichas_pedidas()), base.tramo(EANS['D'])['intento_resultado']),
   (0, 'sin_ficha', 5, 'ok'))
base = Base()
web = Web(catalogo(), {})
codigo, reg = correr(base, web)
eq('C6c cinco fichas seguidas sin producto: para, ROJO', (codigo, 'TCG_TRAMOS_PARADO' in reg, len(web.fichas_pedidas()),
                                                       sum(1 for t in base.t['disp_tramo'] if t['intento_resultado'] == 'sin_ficha')),
   (1, True, 5, 5))
limpio('C6d', reg)

telegramas.clear()
base = Base()
web = Web(catalogo(), FICHAS, login=403)
codigo, reg = correr(base, web)
eq('C8 la web no deja entrar: fallida, ROJO, ni Excel ni fichas, Telegram',
   (codigo, base.pasadas()[0]['estado'], tw.EXCEL_URL in [u for m, u in web.pedidas], web.fichas_pedidas(), len(telegramas)),
   (1, 'fallida', False, [], 1))
eq('C9 el motivo lo dice', '403' in base.pasadas()[0]['motivo'], True)
limpio('C10', reg)

# ── (D) El listado ───────────────────────────────────────────────────────────────────────
base = Base()
Web_ = Web(catalogo(), FICHAS)
correr(base, Web_)
# La web dice ahora que A va «desde 9,50»: no cuadra con lo guardado (9,77); D sigue igual (10,00, sin tramo).
web = Web(catalogo(), FICHAS, tarjetas=tarjeta(URL_FICHA % EANS['A'].lower(), '9,50') + tarjeta(URL_FICHA % EANS['D'].lower()))
codigo, reg = correr(base, web, env={'LISTADO': 'si'})
eq('D1 listado: A marcada y releída en la misma corrida, D no', (codigo, web.fichas_pedidas()),
   (0, [URL_FICHA % EANS['A'].lower()]))
eq('D2 y la marca se borra al releer', base.tramo(EANS['A'])['pide_relectura'], None)
eq('D3 el registro cuenta páginas y desajustes', '1 ya no cuadran' in reg, True)
limpio('D4', reg)
madrid = ZoneInfo('Europe/Madrid')
eq('D5 auto: lunes a las 09 (Madrid) sí; a las 10 no; sábado no; «si» y «no» mandan',
   (prog.toca_listado('auto', datetime(2026, 10, 12, 9, 20, tzinfo=madrid)),
    prog.toca_listado('auto', datetime(2026, 10, 12, 10, 20, tzinfo=madrid)),
    prog.toca_listado('auto', datetime(2026, 10, 17, 9, 20, tzinfo=madrid)),
    prog.toca_listado('si', datetime(2026, 10, 17, 3, 0, tzinfo=madrid)),
    prog.toca_listado('no', datetime(2026, 10, 12, 9, 20, tzinfo=madrid))), (True, False, False, True, False))

# ── (E) Guardas ──────────────────────────────────────────────────────────────────────────
base = Base()
cab = list(_ns['tcg'].COLUMNAS)
cab[2], cab[3] = cab[3], cab[2]
web = Web(excel([fila(EANS['A'])], cab), FICHAS)
codigo, reg = correr(base, web)
eq('E1 cabecera movida: fallida, ROJO y sin fichas', (codigo, base.pasadas()[0]['estado'], web.fichas_pedidas()),
   (1, 'fallida', []))
base = Base(disponibles_minimo=50)
web = Web(catalogo(), FICHAS)
codigo, reg = correr(base, web)
eq('E2 por debajo del mínimo de disponibles: vaciado, ROJO, sin subir y sin fichas',
   (codigo, base.pasadas()[0]['estado'], base.lotes, web.fichas_pedidas()), (1, 'rechazada_vaciado', [], []))
base = Base(crudo_minimo=7)
codigo, reg = correr(base, Web(catalogo(), FICHAS))
eq('E3 por debajo del mínimo de filas: vaciado', base.pasadas()[0]['estado'], 'rechazada_vaciado')
base = Base()
base.t['disp_parametros'] = []
codigo, reg = correr(base, Web(catalogo(), FICHAS))
eq('E4 sin fila de parámetros: fallida antes de bajar nada', (codigo, base.pasadas()[0]['estado']), (1, 'fallida'))
base = Base()
web = Web(catalogo(), FICHAS)
codigo, reg = correr(base, web, env={'TCG_PASS': ''})
eq('E5 sin TCG_PASS: rojo sin abrir pasada ni pedir nada', (codigo, base.pasadas(), web.pedidas), (1, [], []))
codigo, reg = correr(base, web, env={'FICHAS_MAX': 'muchas'})
eq('E6 FICHAS_MAX que no es un número: rojo sin abrir pasada', (codigo, base.pasadas()), (1, []))
base = Base()
base.t['disp_pasada'] = [{'id': 'P1', 'proveedor': 'TCG', 'estado': 'leyendo', 'run_id': 777},
                         {'id': 'P2', 'proveedor': 'TCG', 'estado': 'leyendo', 'run_id': 778},
                         {'id': 'P3', 'proveedor': 'DBLINE', 'estado': 'leyendo', 'run_id': 777}]
codigo, reg = correr(base, None, argv=['--rescate'])
eq('E7 el rescate: solo la de TCG de ESTE run', [p['estado'] for p in base.pasadas()], ['fallida', 'leyendo', 'leyendo'])

# ── (F) Un error inesperado con datos dentro ─────────────────────────────────────────────
base = Base()
base.falla_lectura = EANS['A']
codigo, reg = correr(base, Web(catalogo(), FICHAS))
eq('F1 error al subir: fallida, ROJO, al registro solo el tipo', (codigo, base.pasadas()[0]['estado'],
                                                                  'error inesperado (RuntimeError)' in reg), (1, 'fallida', True))
eq('F2 en la base el detalle, sin URL ni clave', ('tcgfactory' in base.pasadas()[0]['motivo'], CLAVE in base.pasadas()[0]['motivo'],
                                                 '<url>' in base.pasadas()[0]['motivo']), (False, False, True))
limpio('F3', reg)

# ── (G) El ritmo ─────────────────────────────────────────────────────────────────────────
esperas = []
w = tw.Web(types.SimpleNamespace(get=lambda *a, **k: _Resp(200, 'x')), dormir=esperas.append, azar=random.Random(1))
for _ in range(100):
    w._pedir('prueba', 'GET', 'https://tcgfactory.com/x')
cortas = [e for e in esperas if e < 4.0 + 1e-9]
eq('G1 cada petición lleva su pausa, de 1,5 a 4 s salvo las largas', (len(esperas), all(e >= 1.5 for e in esperas)), (100, True))
eq('G2 de 2 a 5 pausas largas (cada 20 a 40) en 100 peticiones', 2 <= len(esperas) - len(cortas) <= 5, True)
w = tw.Web(types.SimpleNamespace(get=lambda *a, **k: _Resp(200, '<div class="g-recaptcha"></div>')), dormir=lambda s: None)
try:
    w._pedir('prueba', 'GET', 'https://tcgfactory.com/x')
    eq('G3 un captcha para', False, True)
except tw.Bloqueo as ex:
    eq('G3 un captcha para, y el texto no lleva la URL', 'tcgfactory' in str(ex), False)

# ── (H) El workflow ──────────────────────────────────────────────────────────────────────
wf = yaml.safe_load(open(WORKFLOW, encoding='utf-8'))
on = wf.get('on', wf.get(True))
eq('H1 solo a mano (sin reloj, sin push)', sorted(on.keys()), ['workflow_dispatch'])
eq('H2 grupo propio y sin cancelar', (wf['concurrency']['group'], wf['concurrency']['cancel-in-progress']), ('escaner2-tcg', False))
pasos = wf['jobs']['leer']['steps']
eq('H3 el primer paso comprueba los secretos', (pasos[0].get('id'), sorted(pasos[0]['env'])),
   ('secretos', ['SUPABASE_SERVICE_KEY', 'SUPABASE_URL', 'TCG_PASS', 'TCG_USER']))
paso = next(p for p in pasos if p.get('run') == 'python -u escaner2_tcg_disponibilidad.py')
eq('H4 los inputs llegan por env:, nunca dentro del run:', (paso['env']['FICHAS_MAX'], paso['env']['LISTADO'],
                                                            '${{' in paso['run']), ('${{ inputs.fichas_max }}', '${{ inputs.listado }}', False))
eq('H5 el Telegram solo en el paso de la pasada', sorted(k for k in paso['env'] if k.startswith('TELEGRAM')),
   ['TELEGRAM_CHAT_ID', 'TELEGRAM_TOKEN'])
resc = pasos[-1]
eq('H6 el rescate: si falla o se cancela y los secretos estaban; sin Telegram ni TCG',
   (resc['run'], resc['if'], sorted(resc['env'])),
   ('python -u escaner2_tcg_disponibilidad.py --rescate', "(failure() || cancelled()) && steps.secretos.outcome == 'success'",
    ['PYTHONIOENCODING', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL']))
eq('H7 sin artefactos (el repo es público)', [p.get('uses', '') for p in pasos if 'upload-artifact' in p.get('uses', '')], [])
eq('H8 descargar-tcg.yml ya no está (publicaba el Excel sin cifrar)',
   os.path.exists(os.path.join(RAIZ, '.github', 'workflows', 'descargar-tcg.yml')), False)

print()
print('TODO OK' if not fallos else 'FALLOS: %d (%s)' % (len(fallos), ', '.join(fallos)))
sys.exit(1 if fallos else 0)
