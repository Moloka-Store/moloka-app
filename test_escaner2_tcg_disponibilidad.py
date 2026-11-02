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
  (J) 🆕 (encargo T4) LA WEB DE FUNKO ANTES DE LA FOTO Y LAS NOVEDADES: el listado de la marca Funko cada hora; las fichas
      de Funko que tocan (nueva, desajustada, con otro Precio en el Excel) se leen ANTES de subir la foto, que sale ya con
      su tramo; la web manda en lo disponible de Funko (lo que da disponible, lo es; lo que no sale con el listado
      entero, no; a medias no quita nada); las novedades se sacan con la pasada aplicada (no «al día») y antes del
      lector; un bloqueo en el listado o en una ficha de Funko deja la pasada 'fallida' (la foto como estaba), Telegram
      y ROJO; un listado con menos de la mitad de lo que da el Excel no se cree; unas novedades que fallan: ROJO con la
      pasada aplicada; y el registro, limpio.
  (K) 🆕 (encargo DI, 2-nov-2026) UNA FICHA CON UN NÚMERO IMPOSIBLE (un descuento de más del 100 %) NO PARA: se guarda
      'no_entendida' sin cociente, se cuenta («dato imposible N de M leídas», solo números) y se sigue. (Encargo DT,
      2-nov-2026) Para como hoy (ROJO, Telegram) solo si en la misma corrida (las de Funko antes de la foto y las del lector,
      juntas) pasan A LA VEZ de 20 y del 20 % de las leídas hasta ese momento (leídas: las que han devuelto tabla; no «sin
      ficha» ni «otro_ean»): 6 de 100 no para, 19 de 20 no, 25 de 100 sí, 21 de 200 no; la forma rota sigue parando a la
      primera; y el registro, limpio.
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

    def upsert(self, d, on_conflict=None, **_k):
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
                                       'disponibles_minimo': disponibles_minimo}],
                  # (Encargo T4) La fila de novedades de TCG, APAGADA (como nace): la valoración se cierra sin Keepa.
                  'nov_parametros': [{'proveedor': 'TCG', 'marcas': ['Funko'], 'valorar': False}]}
        self.lotes, self.rpcs, self.llamadas = [], [], []
        self.falla_lectura = None
        self.falla_novedades = False
        self.marca_parecida = 0
        self.lectura_aplicada = {}

    def table(self, n):
        return _Q(self, n)

    def rpc(self, nombre, params):
        base = self

        class _L:
            def execute(self):
                base.rpcs.append((nombre, params))
                base.llamadas.append(('rpc', nombre))
                if nombre == 'nov_seleccionar_pasada':
                    if base.falla_novedades:
                        raise RuntimeError('SIN_PARAMETROS_NOV: Failing row contains (8000000000017, 9.77)')
                    return _R({'pasada': params['p_pasada'], 'estado': 'hecha', 'novedades': 1, 'subidas_fuera': 0,
                               'marca_parecida': base.marca_parecida})
                if nombre == 'nov_cerrar_valoracion':
                    return _R({'estado': params['p_datos']['estado']})
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
        '<label><input type="checkbox" name="f[53][]" value="a1"><span class="name">Disponible</span></label>'
        # (Encargo T4) El filtro de marca: «m[]», con su nombre (medido en la sonda T4: una sola casilla «Funko»).
        '<label><input type="checkbox" name="m[]" value="m9"><span class="name">Funko</span></label>'
        '<label><input type="checkbox" name="m[]" value="m8"><span class="name">Funko Games</span></label></form>'
        '</body></html>')


class Web:
    """La web de TCG inventada. `fichas`: {ean: html | 404 | 429}; `tarjetas`: html del listado (todas en una pagina)."""

    def __init__(self, contenido, fichas, login=200, tarjetas='', funko='', funko_total=None, funko_codigo=200):
        self.contenido, self.fichas, self.login, self.tarjetas = contenido, fichas, login, tarjetas
        # (Encargo T4) El listado de la marca Funko: sus tarjetas, lo que dice tener (por defecto, las que trae) y su código.
        self.funko, self.funko_codigo = funko, funko_codigo
        self.funko_total = funko_total if funko_total is not None else funko.count('<article')
        self.dentro = False
        self.pedidas = []
        self.filtros = []

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
            con_marca = 'm%5B%5D=m9' in data['params']
            self.filtros.append('funko' if con_marca else 'todo')
            if con_marca:
                if self.funko_codigo != 200:
                    return _Resp(self.funko_codigo, 'Too Many Requests')
                return _Resp(200, '{}', js={'product_list_html': self.funko, 'products_num': self.funko_total})
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
eq('B3 una llamada a disp_aplicar_pasada, un lote (y, encargo T4, después las novedades)', ([n for n, _p in base.rpcs], base.lotes),
   (['disp_aplicar_pasada', 'nov_seleccionar_pasada', 'nov_cerrar_valoracion'], [6]))
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

# ── (J) (Encargo T4) La web de Funko antes de la foto, y las novedades ──────────────────────
#    Seis filas: cinco de Funko y una de otra marca. FA ya leída y la web igual; FB «Disponible» con stock 0 en el Excel
#    y disponible en la web (sin ficha leída); FC disponible en el Excel y fuera del listado; FD leída cuando el Excel
#    decía otro Precio; FE leída, pero la web dice ahora «desde 9,50»; X, de otra marca, sin leer.
JE = {'FA': '8000000001017', 'FB': '8000000001024', 'FC': '8000000001031', 'FD': '8000000001048', 'FE': '8000000001055',
      'X': '8000000001062'}
UJ = {k: URL_FICHA % v.lower() for k, v in JE.items()}


def cat_j(fb_stock=0):
    filas = []
    for i, k in enumerate(('FA', 'FB', 'FC', 'FD', 'FE', 'X')):
        filas.append(fila(JE[k], marca='Funko' if k != 'X' else 'Marca X', stock=fb_stock if k == 'FB' else 50,
                          imagen='https://tcgfactory.com/%d-large_default/%s.jpg' % (40 + i, SLUG % JE[k].lower())))
    return excel(filas)


def guardado_j(k, cociente='0.976600000000', mas_barato='9.766000', precio_excel='10', uds=12):
    hace = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {'proveedor': 'TCG', 'producto_prov': JE[k], 'url': UJ[k], 'intento_en': hace, 'intento_resultado': 'ok',
            'leido_en': hace, 'cociente': cociente, 'uds_mas_barato': uds, 'suelto_web': '10.00', 'mas_barato': mas_barato,
            'precio_excel': precio_excel, 'pide_relectura': None}


def base_j(**k):
    b = Base(**k)
    # FD se leyó con el Excel a 9 € (el cociente de entonces: 9,766 ÷ 9); hoy el Excel dice 10.
    b.t['disp_tramo'] = [guardado_j('FA'), guardado_j('FD', cociente='1.085111111111', precio_excel='9'), guardado_j('FE')]
    return b


FICHAS_J = {JE[k].lower(): ficha_html(tabla=TABLA, eans=(JE[k],)) for k in ('FA', 'FB', 'FC', 'FD', 'X')}
FICHAS_J[JE['FE'].lower()] = ficha_html(tabla=[(12, '10.000000', '0.050000')], eans=(JE['FE'],))
LISTADO_J = (tarjeta(UJ['FA'], '9,77') + tarjeta(UJ['FB'], '9,77') + tarjeta(UJ['FD'], '9,77')
             + tarjeta(UJ['FE'], '9,50'))
PROHIBIDO += ['80000000010', '9,50', '9.766']

telegramas.clear()
base = base_j()
web = Web(cat_j(), FICHAS_J, funko=LISTADO_J)
codigo, reg = correr(base, web)
pj = base.pasadas()[0]
lj = {f['producto_prov']: f for f in base.lectura_aplicada[pj['id']]}
eq('J1 el listado de la marca Funko (con su casilla del filtro), una vez; y la pasada aplicada, en VERDE',
   (web.filtros, pj['estado'], codigo), (['funko'], 'aplicada', 0))
eq('J2 🔑 antes de la foto se leen las de Funko que tocan, en orden (nueva, desajustada, con otro Precio); después, la '
   'de otra marca; ni FA (al día) ni FC (agotada por la web)',
   web.fichas_pedidas(), [UJ['FB'], UJ['FE'], UJ['FD'], UJ['X']])
llam = base.llamadas
eq('J3 🔑 …y se guardan ANTES de subir la foto', llam.index(('disp_tramo', 'upsert')) < llam.index(('disp_lectura', 'insert')),
   True)
eq('J4 🔑 la foto sale ya con su tramo: FB (nueva) 9,766 × 12; FE (desajustada) 9,50; FD (otro Precio) 10 × el cociente '
   'nuevo = 9,766, no 10 × el viejo',
   [(round(lj[JE[k]]['precio_pa'], 6), lj[JE[k]]['uds_escalon'], lj[JE[k]]['aviso']) for k in ('FB', 'FE', 'FD')],
   [(9.766, 12, None), (9.5, 12, None), (9.766, 12, None)])
eq('J5 🔑 la web manda en lo disponible de Funko: FB (stock 0 en el Excel) disponible con la palabra de la web; FC (fuera '
   'del listado entero) agotada; X, de otra marca, como dice el Excel',
   [(lj[JE[k]]['disponible'], lj[JE[k]]['disponibilidad']) for k in ('FB', 'FC', 'X')],
   [(True, 'Disponible'), (False, 'Disponible'), (True, 'Disponible')])
eq('J6 el registro lo cuenta', ('a disponible 1, a agotado 1' in reg, '4 tarjetas (la web dice 4, entero), 1 ya no cuadran' in reg,
                               'pendientes 3, pedidas 3' in reg), (True, True, True))
i_nov = llam.index(('rpc', 'nov_seleccionar_pasada'))
eq('J7 🔑 las novedades, con la pasada aplicada y ANTES del lector de tramos (la ficha de X se lee después)',
   (llam.index(('rpc', 'disp_aplicar_pasada')) < i_nov < len(llam) - 1 - llam[::-1].index(('disp_tramo', 'upsert')),
    [n for n, _p in base.rpcs], base.rpcs[1][1]),
   (True, ['disp_aplicar_pasada', 'nov_seleccionar_pasada', 'nov_cerrar_valoracion'], {'p_pasada': pj['id']}))
eq('J8 apagada (como nace): la valoración se cierra «apagada»', base.rpcs[2][1]['p_datos']['estado'], 'apagada')
limpio('J9', reg)
web2 = Web(cat_j(), FICHAS_J, funko=LISTADO_J)
correr(base, web2)
web3 = Web(cat_j(), FICHAS_J, funko=LISTADO_J)
codigo, reg = correr(base, web3)
eq('J10 al día (mismo contenido y la misma web): VERDE y sin novedades', (codigo, 'TCG_AL_DIA' in reg,
                                                                        [n for n, _p in base.rpcs].count('nov_seleccionar_pasada')),
   (0, True, 2))

base = base_j()
web = Web(cat_j(), FICHAS_J, funko=LISTADO_J, funko_total=5)
codigo, reg = correr(base, web)
lj = {f['producto_prov']: f for f in base.lectura_aplicada[base.pasadas()[0]['id']]}
eq('J11 un listado A MEDIAS (5 dice la web, 4 trae): no quita nada (FC sigue disponible) y sí da lo que ve (FB)',
   (lj[JE['FC']]['disponible'], lj[JE['FB']]['disponible'], 'A MEDIAS' in reg, codigo), (True, True, True, 0))

telegramas.clear()
base = base_j()
web = Web(cat_j(), FICHAS_J, funko=LISTADO_J, funko_codigo=429)
codigo, reg = correr(base, web)
eq('J12 🔴 un 429 en el listado de Funko: para, la pasada «fallida» (la foto como estaba), ni una ficha, Telegram y ROJO',
   (codigo, base.pasadas()[0]['estado'], ('disp_lectura', 'insert') in base.llamadas, web.fichas_pedidas(), len(telegramas),
    'nov_seleccionar_pasada' in [n for n, _p in base.rpcs]),
   (1, 'fallida', False, [], 1, False))
eq('J13 …y el motivo lo dice, sin la URL', ('429' in base.pasadas()[0]['motivo'], 'tcgfactory' in base.pasadas()[0]['motivo']),
   (True, False))
limpio('J14', reg)

telegramas.clear()
base = base_j()
f429 = dict(FICHAS_J)
f429[JE['FE'].lower()] = 429
web = Web(cat_j(), f429, funko=LISTADO_J)
codigo, reg = correr(base, web)
eq('J15 🔴 un 429 en una ficha de Funko antes de la foto: lo leído (FB) queda guardado, ni una más, «fallida», Telegram y '
   'ROJO', (codigo, base.tramo(JE['FB'])['intento_resultado'], web.fichas_pedidas(), base.pasadas()[0]['estado'],
            len(telegramas)), (1, 'ok', [UJ['FB'], UJ['FE']], 'fallida', 1))

base = base_j()
web = Web(cat_j(), FICHAS_J, funko=tarjeta(UJ['FA'], '9,77'))
codigo, reg = correr(base, web)
eq('J16 🔴 un listado con menos de la mitad de lo que el Excel da disponible (1 frente a 4) no se cree: para y ROJO',
   (codigo, base.pasadas()[0]['estado'], web.fichas_pedidas()), (1, 'fallida', []))

base = base_j()
base.falla_novedades = True
web = Web(cat_j(), FICHAS_J, funko=LISTADO_J)
codigo, reg = correr(base, web)
eq('J17 🔴 si las novedades fallan: ROJO, con la pasada aplicada y el lector, que sigue', (codigo, base.pasadas()[0]['estado'],
                                                                                        UJ['X'] in web.fichas_pedidas(),
                                                                                        'TCG_NOVEDADES_EN_ROJO' in reg),
   (1, 'aplicada', True, True))
limpio('J18 (el error de las novedades lleva un EAN y un precio)', reg)
base = base_j()
base.marca_parecida = 2
codigo, reg = correr(base, Web(cat_j(), FICHAS_J, funko=LISTADO_J))
eq('J19 🔴 el vigía de la marca (algo que se parece a Funko y no lo es): ROJO', (codigo, 'MARCA_PARECIDA' in reg), (1, True))

# ── (K) (Encargo DI, 2-nov-2026) Una ficha con un número imposible no para la pasada ────────────
#    Una errata de TCG en una ficha (un descuento de más del 100 % en un tramo) se apunta 'no_entendida', sin cociente
#    nuevo, se cuenta («dato imposible N de M leídas», solo números) y se sigue; (encargo DT) para solo si en la corrida
#    pasan a la vez de DATO_IMPOSIBLE_MIN y de DATO_IMPOSIBLE_PROPORCION de las leídas hasta ese momento.
TABLA_MAL = [(2, '10.000000', '0.010000'), (6, '10.000000', '1.230000'), (12, '10.000000', '0.020000')]


class WebFichas:
    """Solo fichas, para _leer_fichas a pelo: {url: html}."""

    def __init__(self, htmls):
        self.htmls, self.pedidas = htmls, []

    def ficha(self, url):
        self.pedidas.append(url)
        return self.htmls[url]


def cola_k(claves, malas):
    cola, htmls = [], {}
    for k in claves:
        url = URL_FICHA % k.lower()
        cola.append({'producto_prov': k, 'url': url, 'ean_core': k, 'es_caja': False, 'precio_excel': Decimal('10')})
        htmls[url] = ficha_html(tabla=TABLA_MAL if k in malas else TABLA, eans=(k,))
    return cola, htmls


def r_k(**k):
    return dict({'pedidas': 0, 'ok': 0, 'con_tramo': 0, 'sin_ficha': 0, 'otro_ean': 0, 'sin_precio_excel': 0,
                 'dato_imposible': 0, 'leidas': 0}, **k)


_reloj = lambda: datetime.now(timezone.utc)  # noqa: E731
KK = ['8000000002017', '8000000002024', '8000000002031']
base = Base()
cola, htmls = cola_k(KK, {KK[1]})
wk, rk = WebFichas(htmls), r_k()
try:
    prog._leer_fichas(base, wk, cola, 777, rk, _reloj)
    lanzo = None
except Exception as ex:  # noqa: BLE001
    lanzo = type(ex).__name__
eq('K1 (iii) _leer_fichas, 3 fichas y la del medio con dato imposible: lee las 3, no lanza, «dato imposible» 1',
   (lanzo, len(wk.pedidas), rk['dato_imposible'], rk['ok']), (None, 3, 1, 2))
eq('K2 (iii) …la del medio, guardada «no_entendida» y sin cociente; las otras dos, ok con el suyo',
   [(base.tramo(k)['intento_resultado'], base.tramo(k).get('cociente')) for k in KK],
   [('ok', '0.976600000000'), ('no_entendida', None), ('ok', '0.976600000000')])

eq('K1b (DT) …y las 3 cuentan como leídas (las tres han devuelto tabla)', rk['leidas'], 3)


# (Encargo DT, 2-nov-2026) El tope pasa de 5 fijo a proporcional: para solo si las de dato imposible de la corrida pasan A LA
# VEZ de DATO_IMPOSIBLE_MIN (20) y de DATO_IMPOSIBLE_PROPORCION (20 %) de las leídas hasta ese momento, tras cada una.
def corrida_k(orden, previos=(0, 0)):
    """_leer_fichas sobre una cola con una letra por ficha, en su orden: b buena, m dato imposible, r forma rota, n sin ficha
    (404), o de otro EAN, s sin precio en el Excel. Devuelve (lanza, pedidas, r, base, claves, texto de lo que lanza)."""
    claves = ['800000006%04d' % i for i in range(len(orden))]
    cola, htmls = [], {}
    for k, x in zip(claves, orden):
        url = URL_FICHA % k
        cola.append({'producto_prov': k, 'url': url, 'ean_core': k, 'es_caja': False,
                     'precio_excel': None if x == 's' else Decimal('10')})
        htmls[url] = None if x == 'n' else ficha_html(tabla=TABLA_MAL if x == 'm' else TABLA,
                                                      tipo='amount' if x == 'r' else 'percentage',
                                                      eans=('8000000069997',) if x == 'o' else (k,))
    base, wk = Base(), WebFichas(htmls)
    rk = r_k(dato_imposible_previos=previos[0], leidas_previas=previos[1])
    try:
        prog._leer_fichas(base, wk, cola, 777, rk, _reloj)
        lanza, texto = None, ''
    except Exception as ex:  # noqa: BLE001
        lanza, texto = type(ex).__name__, str(ex)
    return lanza, len(wk.pedidas), rk, base, claves, texto


eq('K3 (DT) las dos constantes con nombre, y el tope fijo ya no está',
   (prog.DATO_IMPOSIBLE_MIN, prog.DATO_IMPOSIBLE_PROPORCION, hasattr(prog, 'DATO_IMPOSIBLE_MAX')), (20, 0.20, False))
lanza, ped, rk, base, claves, _t = corrida_k('m' * 6 + 'b' * 94)
eq('K4 (a) 🔑 el caso real de hoy: 6 con dato imposible entre 100 leídas (las 6, las primeras) NO para; se leen las 100',
   (lanza, ped, rk['dato_imposible'], rk['leidas'], rk['ok']), (None, 100, 6, 100, 94))
eq('K4b (a) …y las seis quedan guardadas «no_entendida», sin cociente',
   [(base.tramo(k)['intento_resultado'], base.tramo(k).get('cociente')) for k in claves[:6]], [('no_entendida', None)] * 6)
lanza, ped, rk, *_r = corrida_k('m' * 19 + 'b')
eq('K5 (b) 19 de 20 leídas NO para (no pasa del mínimo de 20, aunque sea el 95 %)', (lanza, ped, rk['dato_imposible']),
   (None, 20, 19))
lanza, ped, rk, *_r = corrida_k('m' * 20)
eq('K5b (b) …20 de 20, el mínimo justo, tampoco («pasar de 20» es más de 20)', (lanza, ped), (None, 20))
lanza, ped, rk, *_r = corrida_k('m' * 21 + 'b')
eq('K5c (b) …21 de 21: para a la 21.ª, ni una ficha más', (lanza, ped, rk['dato_imposible']), ('FichaNoEntendida', 21, 21))
lanza, ped, rk, base, claves, texto = corrida_k('b' * 75 + 'm' * 25)
eq('K6 (c) 🔑 25 de 100 (las malas, al final): para a la 21.ª (21 de 96 leídas: más de 20 y más del 20 %); ni una más',
   (lanza, ped, rk['dato_imposible'], rk['leidas']), ('FichaNoEntendida', 96, 21, 96))
eq('K6b (c) …el motivo lo dice con los números, sin un EAN', ('21 fichas con un número imposible en su tabla de tramos de 96 '
                                                              'leídas en esta corrida, más de 20 y más del 20 %' in texto,
                                                              '800000006' in texto), (True, False))
eq('K6c (c) …y la que para también queda guardada «no_entendida», sin cociente',
   (base.tramo(claves[95])['intento_resultado'], base.tramo(claves[95]).get('cociente'), base.tramo(claves[96])),
   ('no_entendida', None, None))
eq('K6d (c) 25 de 100 para en cualquier orden: al principio (a la 21.ª) o salteadas (una de cada cuatro: a las 84 leídas)',
   [corrida_k(o)[:2] for o in ('m' * 25 + 'b' * 75, 'bbbm' * 25)], [('FichaNoEntendida', 21), ('FichaNoEntendida', 84)])
lanza, ped, rk, *_r = corrida_k('b' * 179 + 'm' * 21)
eq('K7 (d) 🔑 21 de 200 (las malas, al final) NO para: pasa de 20 pero no del 20 % (sería 40)',
   (lanza, ped, rk['dato_imposible'], rk['leidas']), (None, 200, 21, 200))
eq('K7b (d) …el orden cuenta, como pide el encargo («de las leídas hasta ese momento»): las mismas 21 al PRINCIPIO de la '
   'cola paran a la 21.ª (21 de 21)', corrida_k('m' * 21 + 'b' * 179)[:2], ('FichaNoEntendida', 21))
eq('K7c frontera del 20 %: 21 de 105 (el 20 % justo) no para; 21 de 104, sí',
   [corrida_k('b' * 84 + 'm' * 21)[:2], corrida_k('b' * 83 + 'm' * 21)[:2]], [(None, 105), ('FichaNoEntendida', 104)])
lanza, ped, rk, *_r = corrida_k('b' * 60 + 'mno' * 21)
eq('K7d «sin ficha» y «otro_ean» NO cuentan como leídas: 60 buenas + 21 × (dato imposible, 404, otro EAN) para a la 21.ª '
   'con 81 leídas (contándolas serían 121 y no pararía)',
   (lanza, ped, rk['leidas'], rk['sin_ficha'], rk['otro_ean']), ('FichaNoEntendida', 121, 81, 20, 20))
lanza, ped, rk, *_r = corrida_k('s' * 84 + 'm' * 21)
eq('K7e «sin precio en el Excel» SÍ cuenta (ha devuelto tabla, y buena): 84 + 21 = 105 leídas, el 20 % justo, no para',
   (lanza, ped, rk['leidas'], rk['sin_precio_excel']), (None, 105, 105, 84))
eq('K8 (e) 🔴 la forma rota sigue parando a la primera: sola, tras 3 de dato imposible, o con 19 de 30 de antes en la corrida',
   [corrida_k(o, p)[:2] for o, p in (('rbbbb', (0, 0)), ('mmmrbb', (0, 0)), ('rbb', (19, 30)))],
   [('FichaNoEntendida', 1), ('FichaNoEntendida', 4), ('FichaNoEntendida', 1)])
lanza, ped, rk, base, claves, _t = corrida_k('mmmr')
eq('K8b (e) …y la rota, guardada «no_entendida», sin cociente', (base.tramo(claves[3])['intento_resultado'],
                                                                 base.tramo(claves[3]).get('cociente')), ('no_entendida', None))
eq('K9 el tope es de la corrida: 20 de 50 de antes (Funko) + 1 ahora = 21 de 51: para; 20 de 200 + 1 = 21 de 201: no',
   [corrida_k('mb', (20, 50))[:2], corrida_k('mb', (20, 200))[:2]], [('FichaNoEntendida', 1), (None, 2)])

# El programa entero: A ok, B con dato imposible, C de su EAN (cola de 3 con FICHAS_MAX=3).
telegramas.clear()
base = Base()
fk = dict(FICHAS)
fk[EANS['B'].lower()] = ficha_html(tabla=TABLA_MAL, eans=(EANS['B'],))
fk[EANS['C'].lower()] = ficha_html(tabla=TABLA, eans=(EANS['C'],))
web = Web(catalogo(), fk)
codigo, reg = correr(base, web, env={'FICHAS_MAX': '3'})
eq('K20 (iii) entero: VERDE, sin parada ni Telegram, las 3 pedidas; B «no_entendida» sin cociente; C ok',
   (codigo, 'TCG_TRAMOS_PARADO' in reg, len(telegramas), len(web.fichas_pedidas()), base.tramo(EANS['B'])['intento_resultado'],
    base.tramo(EANS['B']).get('cociente'), base.tramo(EANS['C'])['intento_resultado']),
   (0, False, 0, 3, 'no_entendida', None, 'ok'))
eq('K21 (iii) el registro lo cuenta, solo números, con las leídas: en la línea de TRAMOS 1 de 3 (y en la de Funko, 0 de 0)',
   ('· dato imposible 1 de 3 leídas' in reg, ', dato imposible 0 de 0 leídas' in reg), (True, True))
limpio('K22', reg)
web = Web(catalogo(), fk)
codigo, reg = correr(base, web)
eq('K23 la de dato imposible no se reintenta antes de 24 h (como hoy una «no_entendida»)', EANS['B'].lower() in ' '.join(web.fichas_pedidas()), False)


def corrida_entera(funko_buenas, funko_malas, otras_malas=0):
    """principal() con `funko_buenas` + `funko_malas` fichas de Funko (antes de la foto) y `otras_malas` de otra marca (el
    lector), todas nuevas. Devuelve (base, web, codigo, registro)."""
    funko = ['800000007%04d' % i for i in range(funko_buenas + funko_malas)]
    otras = ['800000008%04d' % i for i in range(otras_malas)]
    malas = set(funko[funko_buenas:]) | set(otras)
    cat = excel([fila(v, marca='Funko' if v in funko else 'Marca X',
                      imagen='https://tcgfactory.com/%d-large_default/%s.jpg' % (100 + i, SLUG % v))
                 for i, v in enumerate(funko + otras)])
    fk = {v: ficha_html(tabla=TABLA_MAL if v in malas else TABLA, eans=(v,)) for v in funko + otras}
    telegramas.clear()
    base = Base()
    web = Web(cat, fk, funko=''.join(tarjeta(URL_FICHA % v, '9,90') for v in funko))
    codigo, reg = correr(base, web)
    return base, web, codigo, reg


PROHIBIDO += ['80000000020', '800000006', '800000007', '800000008', '1.23', '9,90']
# (a) entero, el caso real de hoy: 6 Funko con dato imposible entre 100 leídas antes de la foto.
base, web, codigo, reg = corrida_entera(94, 6)
eq('K24 (a) 🔑 entero, el caso de hoy: 6 de 100 Funko con dato imposible antes de la foto: la foto se APLICA, VERDE, sin '
   'Telegram, las 100 pedidas',
   (base.pasadas()[0]['estado'], codigo, len(telegramas), len(web.fichas_pedidas()), 'TCG_NO_APLICADA' in reg),
   ('aplicada', 0, 0, 100, False))
eq('K25 (a) …WEB FUNKO lo cuenta, «dato imposible 6 de 100 leídas»; y las 6, «no_entendida» sin cociente',
   (', dato imposible 6 de 100 leídas' in reg,
    sorted((t['intento_resultado'], t.get('cociente')) for t in base.t['disp_tramo'] if t['intento_resultado'] != 'ok')),
   (True, [('no_entendida', None)] * 6))
limpio('K26 (f)', reg)
# (c) entero: 25 de 100 Funko con dato imposible antes de la foto, como la corrida de hoy pero con el tope nuevo.
base, web, codigo, reg = corrida_entera(75, 25)
eq('K27 (c) 🔑 entero: 25 de 100 Funko con dato imposible antes de la foto: para como hoy (pasada «fallida», la foto como '
   'estaba, ni lector ni novedades), Telegram y ROJO',
   (base.pasadas()[0]['estado'], codigo, ('disp_lectura', 'insert') in base.llamadas, 'TRAMOS: no se leen' in reg,
    [n for n, _p in base.rpcs], len(telegramas)),
   ('fallida', 1, False, True, [], 1))
eq('K28 (c) …el registro dice por qué, con los números: 21 de las leídas hasta ese momento, más de 20 y más del 20 %',
   ('TCG_NO_APLICADA' in reg, 'fichas con un número imposible en su tabla de tramos de' in reg,
    'más de 20 y más del 20 %: ya no es una errata suelta' in reg, reg.count('21 fichas con un número imposible')),
   (True, True, True, 1))
eq('K29 (c) …las de dato imposible leídas, «no_entendida» sin cociente: 21 (la que para también)',
   sorted((t['intento_resultado'], t.get('cociente')) for t in base.t['disp_tramo'] if t['intento_resultado'] != 'ok'),
   [('no_entendida', None)] * 21)
limpio('K30 (f)', reg)
eq('K31 (f) el Telegram de la parada, sin URLs ni EAN', (len(telegramas), any(p in ''.join(telegramas) for p in PROHIBIDO)),
   (1, False))
codigo, reg = correr(base, None, argv=['--rescate'])
eq('K32 (c) …y el rescate, como hoy: 0 pasadas a «fallida» (la pasada ya se cerró sola)',
   ('0 pasada(s) de TCG de este run' in reg, [p['estado'] for p in base.pasadas()]), (True, ['fallida']))
# El tope es de la corrida: 15 de Funko antes de la foto (no paran solas) + 6 del lector = 21 de 21 leídas.
base, web, codigo, reg = corrida_entera(0, 15, 6)
eq('K33 entero: 15 de Funko (la foto se aplica) + 6 del lector = 21 de 21 en la corrida: para en el lector, ROJO y Telegram',
   (base.pasadas()[0]['estado'], codigo, 'TCG_TRAMOS_PARADO' in reg, len(web.fichas_pedidas()), len(telegramas)),
   ('aplicada', 1, True, 21, 1))
eq('K34 …WEB FUNKO cuenta sus 15 de 15 y TRAMOS las suyas (6 de 6, la que para también)',
   (', dato imposible 15 de 15 leídas' in reg, '· dato imposible 6 de 6 leídas' in reg), (True, True))
eq('K35 …las 21, «no_entendida» y sin cociente',
   sorted((t['intento_resultado'], t.get('cociente')) for t in base.t['disp_tramo']), [('no_entendida', None)] * 21)
limpio('K36 (f)', reg)
eq('K37 (f) el Telegram de la parada, sin URLs ni EAN', any(p in ''.join(telegramas) for p in PROHIBIDO), False)

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
eq('H5b (encargo T4) la llave de Keepa (la valoración de las novedades), en el paso de la pasada y no en el rescate',
   (paso['env'].get('KEEPA_API_KEY'), 'KEEPA_API_KEY' in pasos[-1]['env']), ('${{ secrets.KEEPA_API_KEY }}', False))
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
