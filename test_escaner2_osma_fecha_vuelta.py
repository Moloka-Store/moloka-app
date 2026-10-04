# -*- coding: utf-8 -*-
"""Banco de las FECHAS DE VUELTA DE OSMA (escaner2_osma_fecha_vuelta.py, 04-oct-2026).

SIN RED, SIN SECRETOS Y SIN BASE: el repaso se ejecuta DE VERDAD contra una web de OSMA y una base de mentira.
🔴 TODO ES INVENTADO (el repo es publico): codigos, EAN, nombres y fechas son centinelas que no pueden salir en
el registro. Las paginas imitan la estructura MEDIDA el 04-oct-2026 en osma-werm.com (ficha 2346 y 1538): un
solo bloque itemtype="https://schema.org/Offer" con «Bestellt (Wieder verfügbar ab: dd.mm.aa)», el codigo en un
<span itemprop="sku">, html lang="de-DE", y carruseles de OTROS productos con su propia disponibilidad fuera del
bloque (en la real, 56 «product-availability» y un solo Offer).

QUE PRUEBA:
  (A) ELIGE BIEN: los agotados de OSMA que alimentan una ficha nuestra por enlace (codigos_proveedor con
      producto_id), por EAN normalizado (con ceros delante) o por el mapa (es_nuestra); NO los que no son
      nuestros, ni los que tienen enlace sin ficha, ni los del mapa sin es_nuestra. Primero los nunca leidos y
      luego los de lectura mas vieja; los leidos HOY no se reabren.
  (B) LEE BIEN: la fecha del bloque del producto y no la del carrusel; dd.mm.aa sin ambiguedad; sin fecha → NULL
      apuntado con su hora; la busqueda por EAN que redirige, la que da una lista (el enlace que acaba en el
      codigo) y, si por EAN no sale, por nombre. No escribe: otro articulo (sku distinto), pagina no alemana, sin
      bloque Offer, fecha que no existe, ni nada si no se encuentra la ficha.
  (C) BORRA la fecha de los que vuelven a estar disponibles.
  (D) LOS FRENOS: al menos 2 s entre peticiones (reloj de mentira); 40 peticiones como mucho; al PRIMER 403 o 429
      (tambien en una redireccion) o si vuelve la pagina de entrada, PARA EN SECO: ni una peticion mas ni un
      reintento.
  (E) --sin-escribir no toca la base (ni borra ni apunta).
  (F) SOLO escribe disp_estado, y solo sus dos columnas; lee codigos_proveedor, productos y osma_mapa_ficha.
  (G) 🔴 EL REGISTRO NO SUELTA DATOS: ni codigos, ni EAN, ni nombres, ni fechas, ni URL.
  (H) El programa principal: el codigo de salida del paso 9 (parada → 1, web cambiada → 1, bien → 0) y las
      00:00 de Madrid en UTC.
  (I) 🔴 LA MITAD ROJA: mutantes (sin pausa, sin parar al 429, sin comprobar el codigo de la URL, leyendo la
      primera fecha de la pagina, sin tope) ponen el banco en rojo.
"""
import ast
import contextlib
import io
import os
import runpy
import sys
import tempfile
import types
from datetime import date, datetime, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
MODULO = os.path.join(RAIZ, 'escaner2_osma_fecha_vuelta.py')
PROGRAMA = os.path.join(RAIZ, 'escaner2_osma_disponibilidad.py')
WEB = 'https://osma-werm.com'
INICIO_HOY = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc)      # las 00:00 del 07-oct en Madrid
AHORA = datetime(2026, 10, 7, 5, 20, tzinfo=timezone.utc)

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ── Los centinelas ────────────────────────────────────────────────────────────────────────
CENTINELAS = ['CODFV', '4999990', 'NOMBRE-FV', '2026-10', '11.10.26', '05.10.26', '/search', 'osma-werm', 'Slug-FV']


def ficha(codigo, fecha_txt=None, lang='de-DE', sku=None, ofertas=1, disponible=False):
    """Una ficha con la estructura medida. `fecha_txt` = '11.10.26' o None (sin fecha)."""
    carrusel = ('<div class="product-slider"><div class="product-box"><div class="product-availability">'
                '<span class="availability-text">Bestellt</span>&nbsp;<small>(Wieder verfügbar ab: 01.01.27)</small>'
                '</div><a class="product-name" href="/Otro-Slug-FV/CODFVOTRO">NOMBRE-FV otro</a></div></div>')
    if disponible:
        disp = '<div class="availability-circle available"></div><span class="availability-text">Verfügbar</span>'
    elif fecha_txt:
        disp = ('<div class="availability-circle pre-order"></div><span class="availability-text">Bestellt</span>'
                f'&nbsp;\n<small>\n    (Wieder verfügbar ab: {fecha_txt})\n</small>')
    else:
        disp = ('<div class="availability-circle pre-order"></div><span class="availability-text">\n'
                '   Wird bestellt\n</span>')
    oferta = ('<div itemprop="offers"\n     itemscope\n     itemtype="https://schema.org/Offer">\n'
              f'<div class="product-availability">{disp}</div><div class="product-dangerous-goods"></div>'
              '<div class="product-detail-form-container"><form action="/checkout/line-item/add" method="post">'
              '<input type="hidden" name="redirectTo" value="frontend.detail.page"><p>Menge'
              '<button class="btn">In den Warenkorb</button></form></div></div>')
    return (f'<!DOCTYPE html><html lang="{lang}"><head><title>NOMBRE-FV | {codigo}</title>'
            '<meta charset="utf-8"></head><body>' + carrusel + '<div class="product-detail-buy">'
            + oferta * ofertas + '</div><div class="product-detail-ordernumber-container">'
            '<span class="product-detail-ordernumber-label">Artikel-Nr.:</span>'
            '<meta itemprop="productID" content="019f83ff5a987155b3eab55e7f1d4452">'
            f'<span class="product-detail-ordernumber" itemprop="sku">\n   {sku or codigo}\n</span></div>'
            + carrusel + '</body></html>')


def lista(*codigos):
    return ('<!DOCTYPE html><html lang="de-DE"><body><div class="cms-listing-row">'
            + ''.join(f'<div class="product-box"><a href="{WEB}/Slug-FV-{c}/{c}" class="product-name">NOMBRE-FV</a>'
                      f'<a href="/Slug-FV-{c}/{c}#reviews">x</a></div>' for c in codigos)
            + '</div></body></html>')


class _Resp:
    def __init__(self, url, status=200, texto='', history=()):
        self.url, self.status_code, self.text, self.history = url, status, texto, list(history)


class Web:
    """rutas: {ruta: (status, url_final, html)}; lo que no está, 404. Apunta cada GET."""

    def __init__(self, rutas):
        self.rutas, self.llamadas, self.headers = rutas, [], {}

    def get(self, url, timeout=None, allow_redirects=True):
        self.llamadas.append(url)
        ruta = url.replace(WEB, '')
        if ruta not in self.rutas:
            return _Resp(url, 404, 'NOMBRE-FV no encontrado')
        st, final, html = self.rutas[ruta]
        hist = [_Resp(url, st)] if st in (403, 429) and final.endswith('#redir') else []
        return _Resp(WEB + final.replace('#redir', ''), 200 if hist else st, html, hist)


# ── La base de mentira ────────────────────────────────────────────────────────────────────
class _Consulta:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.accion, self.datos, self.filtros, self.nulos = base, tabla, None, None, {}, []
        self._neg = False
        self.desde, self.hasta = 0, None

    def select(self, *_a, **_k):
        self.accion = 'select'
        return self

    def update(self, d):
        self.accion, self.datos = 'update', d
        return self

    def eq(self, c, v):
        self.filtros[c] = v
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, d, h):
        self.desde, self.hasta = d, h
        return self

    @property
    def not_(self):
        self._neg = True
        return self

    def is_(self, c, v):
        self.nulos.append((c, self._neg))
        self._neg = False
        return self

    def _vale(self, f):
        if any(f.get(c) != v for c, v in self.filtros.items()):
            return False
        return all((f.get(c) is not None) if neg else (f.get(c) is None) for c, neg in self.nulos)

    def execute(self):
        b = self.base
        if b.falla.get(self.tabla):
            raise RuntimeError('tabla %s inexistente (de mentira)' % self.tabla)
        filas = b.tablas.setdefault(self.tabla, [])
        b.ops.append((self.tabla, self.accion, dict(self.filtros), dict(self.datos or {})))
        if self.accion == 'select':
            r = [dict(f) for f in filas if self._vale(f)]
            return types.SimpleNamespace(data=r[self.desde:(self.hasta + 1) if self.hasta is not None else None])
        if self.accion == 'update':
            for f in filas:
                if self._vale(f):
                    f.update(self.datos)
            return types.SimpleNamespace(data=[])
        raise AssertionError('accion no prevista: %r' % self.accion)


class Base:
    def __init__(self, estado, codigos=(), productos=(), mapa=(), falla=None):
        self.tablas = {'disp_estado': [dict(f) for f in estado], 'codigos_proveedor': list(codigos),
                       'productos': list(productos), 'osma_mapa_ficha': list(mapa)}
        self.ops, self.falla = [], dict(falla or {})

    def table(self, nombre):
        return _Consulta(self, nombre)

    def fila(self, codigo):
        return next(f for f in self.tablas['disp_estado'] if f['producto_prov'] == codigo)

    def escrituras(self):
        return [o for o in self.ops if o[1] == 'update']


def agotado(codigo, ean, nombre='NOMBRE-FV', leida=None, **k):
    f = {'proveedor': 'OSMA', 'producto_prov': codigo, 'ean_core': ean, 'ean_norm': (ean or '').lstrip('0') or None,
         'nombre': nombre, 'disponible': False, 'en_catalogo': True, 'ausencias': 0,
         'fecha_vuelta': None, 'fecha_vuelta_leida_en': leida}
    f.update(k)
    return f


class Reloj:
    def __init__(self):
        self.t, self.sueños, self.en_peticion = 100.0, [], []

    def reloj(self):
        return self.t

    def dormir(self, s):
        self.sueños.append(s)
        self.t += s


def repasar(mod, base, web, escribir=True, rel=None):
    rel = rel or Reloj()
    orig_get = web.get

    def get(url, **k):
        rel.en_peticion.append(rel.t)
        return orig_get(url, **k)
    web.get = get
    c, parada = mod['repasar'](base, web, INICIO_HOY, escribir=escribir, dormir=rel.dormir, reloj=rel.reloj, ahora=AHORA)
    return c, parada, rel


# ── El escenario completo ──────────────────────────────────────────────────────────────────
def escenario():
    estado = [
        agotado('CODFV1', '4999990000017'),                       # por enlace · búsqueda por EAN que redirige
        agotado('CODFV2', '0004999990000024'),                    # por EAN con ceros · búsqueda que da una lista
        agotado('CODFV3', None, nombre='NOMBRE-FV tres'),         # por el mapa · sin EAN: por nombre
        agotado('CODFV4', '4999990000048'),                       # NO nuestro: no se abre
        agotado('CODFV5', '4999990000055', leida='2026-10-06T23:30:00+00:00', fecha_vuelta='2026-10-20'),  # leído hoy
        agotado('CODFV6', '4999990000062', leida='2026-10-01T05:00:00+00:00'),   # leído hace días: va DESPUÉS
        agotado('CODFV7', '4999990000079'),                       # página inglesa: no se escribe
        agotado('CODFV8', '4999990000086'),                       # otro artículo (sku): no se escribe
        agotado('CODFV9', '4999990000093'),                       # fecha que no existe: no se escribe
        agotado('CODFVA', '4999990000109'),                       # sin ficha: no se escribe
        agotado('CODFVB', '4999990000116', ausencias=1),          # fuera del Excel: no se abre
        agotado('CODFVC', '4999990000123'),                       # enlace SIN ficha: no es nuestro
        agotado('CODFVD', '4999990000130'),                       # en el mapa sin es_nuestra: no es nuestro
        dict(agotado('CODFVE', '4999990000147', leida='2026-10-02T05:00:00+00:00', fecha_vuelta='2026-10-05'),
             disponible=True),                                    # vuelve a estar disponible: se borra
    ]
    codigos = [{'id': 1, 'proveedor': 'OSMA', 'codigo_proveedor': 'CODFV1', 'producto_id': 'u1'},
               {'id': 2, 'proveedor': 'OSMA', 'codigo_proveedor': 'CODFVC', 'producto_id': None},
               {'id': 3, 'proveedor': 'HEO', 'codigo_proveedor': 'CODFV4', 'producto_id': 'u9'}]
    productos = [{'id': i, 'ean': e} for i, e in enumerate(
        ['4999990000024', '4999990000055', '4999990000062', '4999990000079', '4999990000086', '4999990000093',
         '4999990000109', None, ''])]
    mapa = [{'codigo_osma': 'CODFV3', 'es_nuestra': True}, {'codigo_osma': 'CODFVD', 'es_nuestra': False}]
    rutas = {
        '/search?search=4999990000017': (200, '/Slug-FV-1/CODFV1', ficha('CODFV1', '11.10.26')),
        '/search?search=0004999990000024': (200, '/search?search=0004999990000024', lista('CODFV2X', 'CODFV2')),
        '/Slug-FV-CODFV2/CODFV2': (200, '/Slug-FV-CODFV2/CODFV2', ficha('CODFV2')),
        '/search?search=NOMBRE-FV%20tres': (200, '/Slug-FV-3/CODFV3', ficha('CODFV3', '05.10.26')),
        '/search?search=4999990000062': (200, '/Slug-FV-6/CODFV6', ficha('CODFV6', '3.11.2026')),
        '/search?search=4999990000079': (200, '/en/Slug-FV-7/CODFV7', ficha('CODFV7', '11.10.26', lang='en-GB')),
        '/search?search=4999990000086': (200, '/Slug-FV-8/CODFV8', ficha('CODFV8', '11.10.26', sku='CODFVOTRO')),
        '/search?search=4999990000093': (200, '/Slug-FV-9/CODFV9', ficha('CODFV9', '31.02.26')),
        '/search?search=4999990000109': (200, '/search?search=4999990000109', lista('CODFVOTRO')),
        '/search?search=NOMBRE-FV': (200, '/search?search=NOMBRE-FV', lista()),
    }
    return Base(estado, codigos, productos, mapa), Web(rutas)


def comprobar(modulo, decir):
    rotos = []

    def chk(nombre, obtenido, esperado):
        if obtenido != esperado:
            rotos.append(nombre)
        decir(nombre, obtenido, esperado)

    mod = runpy.run_path(modulo, run_name='fv_banco')
    salidas = {}

    # (A)(B)(C)(F) el escenario completo, escribiendo
    base, web = escenario()
    c, parada, rel = repasar(mod, base, web)
    salidas['escenario'] = mod['resumen'](c, True)
    abiertos = [u.replace(WEB, '') for u in web.llamadas]
    chk('(A) elige los nuestros: por enlace, por EAN con ceros, por mapa; ni el ajeno, ni el de fuera del Excel, '
        'ni el enlace sin ficha, ni el del mapa sin es_nuestra',
        (c['agotados_osma'], c['nuestros'], c['leidos_hoy']), (12, 9, 1))
    chk('(A) …y no abre nada de los que no son suyos',
        [u for u in abiertos if any(x in u for x in ('0000048', '0000123', '0000130', '0000116'))], [])
    chk('(A) …primero los nunca leídos y DESPUÉS el de lectura vieja; el leído hoy, no se reabre',
        (abiertos[-1], any('0000055' in u for u in abiertos)), ('/search?search=4999990000062', False))
    chk('(B) la fecha del bloque del producto, no la del carrusel (dd.mm.aa → 2026)',
        (base.fila('CODFV1')['fecha_vuelta'], base.fila('CODFV1')['fecha_vuelta_leida_en']),
        ('2026-10-11', AHORA.isoformat()))
    chk('(B) la búsqueda que da una lista: abre el enlace que acaba en el código; sin fecha → NULL con su hora',
        (base.fila('CODFV2')['fecha_vuelta'], base.fila('CODFV2')['fecha_vuelta_leida_en'],
         '/Slug-FV-CODFV2/CODFV2' in abiertos), (None, AHORA.isoformat(), True))
    chk('(B) sin EAN, por el nombre', base.fila('CODFV3')['fecha_vuelta'], '2026-10-05')
    chk('(B) dd.mm.aaaa también vale', base.fila('CODFV6')['fecha_vuelta'], '2026-11-03')
    chk('(B) no escribe: página inglesa, otro artículo, fecha que no existe, sin ficha',
        [(k, base.fila(k)['fecha_vuelta_leida_en']) for k in ('CODFV7', 'CODFV8', 'CODFV9', 'CODFVA')],
        [(k, None) for k in ('CODFV7', 'CODFV8', 'CODFV9', 'CODFVA')])
    chk('(B) los recuentos', tuple(c[k] for k in ('abiertas', 'con_fecha', 'sin_fecha', 'no_alemana', 'otro_articulo',
                                                  'fecha_rara', 'no_encontrada', 'sin_bloque', 'sin_turno')),
        (7, 3, 1, 1, 1, 1, 1, 0, 0))
    chk('(B) sin ficha: busca por EAN y por nombre, y no abre el enlace de otro artículo',
        [u for u in abiertos if 'CODFVOTRO' in u], [])
    chk('(C) borra la fecha del que vuelve a estar disponible (y nada más de él)',
        (base.fila('CODFVE')['fecha_vuelta'], base.fila('CODFVE')['fecha_vuelta_leida_en'], c['borradas']),
        (None, '2026-10-02T05:00:00+00:00', 1))
    chk('(C) …y el leído hoy conserva su fecha', base.fila('CODFV5')['fecha_vuelta'], '2026-10-20')
    chk('(F) solo escribe disp_estado, y solo sus dos columnas',
        sorted({(o[0], k) for o in base.escrituras() for k in o[3]}),
        [('disp_estado', 'fecha_vuelta'), ('disp_estado', 'fecha_vuelta_leida_en')])
    chk('(F) …y solo lee estas cuatro tablas', sorted({o[0] for o in base.ops}),
        ['codigos_proveedor', 'disp_estado', 'osma_mapa_ficha', 'productos'])
    huecos = [b - a for a, b in zip(rel.en_peticion, rel.en_peticion[1:])]
    chk('(D) al menos 2 s entre peticiones, todas', (len(huecos) == c['peticiones'] - 1, min(huecos) >= 2.0),
        (True, True))
    chk('(D) cuenta sus peticiones', c['peticiones'], len(web.llamadas))
    chk('(D) sin parada', parada, None)

    # (E) sin escribir
    base, web = escenario()
    c, parada, _r = repasar(mod, base, web, escribir=False)
    salidas['sin escribir'] = mod['resumen'](c, False)
    chk('(E) --sin-escribir: ni una escritura, y los mismos recuentos de lectura',
        (base.escrituras(), c['con_fecha'], c['borradas']), ([], 3, 0))

    # (D) LA PARADA: 429 a la segunda petición. Ni una más, ni un reintento; lo de antes, escrito.
    for st, redir in ((429, False), (403, False), (429, True)):
        base, web = escenario()
        r = web.rutas['/search?search=0004999990000024']
        web.rutas['/search?search=0004999990000024'] = (st, (r[1] + '#redir') if redir else r[1], 'NOMBRE-FV error')
        c, parada, _r = repasar(mod, base, web)
        salidas['parada %s' % st] = mod['resumen'](c, True)
        chk('(D) %s%s a la segunda: PARA en seco tras ella, sin reintento' % (st, ' en una redirección' if redir else ''),
            (len(web.llamadas), parada is not None, c['sin_turno'], base.fila('CODFV1')['fecha_vuelta']),
            (2, True, 7, '2026-10-11'))
    base, web = escenario()
    web.rutas['/search?search=4999990000017'] = (200, '/account/login', 'NOMBRE-FV entrada')
    c, parada, _r = repasar(mod, base, web)
    chk('(D) si vuelve la página de entrada (sesión caída): PARA a la primera',
        (len(web.llamadas), parada is not None, base.escrituras()[1:]), (1, True, []))

    # (D) EL TOPE: 45 agotados nuestros, cada uno con su ficha a una petición → 40 peticiones y 5 sin turno.
    estado = [agotado('CODFVT%02d' % i, '49999901%05d' % i) for i in range(45)]
    rutas = {'/search?search=49999901%05d' % i: (200, '/Slug-FV/CODFVT%02d' % i, ficha('CODFVT%02d' % i, '11.10.26'))
             for i in range(45)}
    base = Base(estado, [], [{'id': i, 'ean': '49999901%05d' % i} for i in range(45)])
    web = Web(rutas)
    c, parada, _r = repasar(mod, base, web)
    salidas['tope'] = mod['resumen'](c, True)
    chk('(D) el tope: 40 peticiones como mucho; el resto, sin turno (mañana)',
        (len(web.llamadas), c['peticiones'], c['con_fecha'], c['sin_turno'], parada), (40, 40, 40, 5, None))

    # Sin mapa (la tabla no se puede leer): sigue con los enlaces y el EAN, y lo dice.
    base, web = escenario()
    base.falla['osma_mapa_ficha'] = True
    c, parada, _r = repasar(mod, base, web)
    chk('sin el mapa: sigue sin el del mapa y lo dice', (c['nuestros'], c['mapa_sin_leer']), (8, 1))

    # (B) LAS PIEZAS: leer_ficha
    lf = mod['leer_ficha']
    chk('(B) leer_ficha: dos bloques Offer → no vale', lf(ficha('X', '11.10.26', ofertas=2), 'X'), ('sin_bloque', None))
    chk('(B) leer_ficha: sin bloque Offer → no vale',
        lf('<html lang="de-DE"><body><small>(Wieder verfügbar ab: 11.10.26)</small></body></html>', 'X'),
        ('sin_bloque', None))
    chk('(B) leer_ficha: disponible → sin fecha', lf(ficha('X', disponible=True), 'X'), ('sin_fecha', None))
    chk('(B) leer_ficha: 11.10.26 es el 11 de octubre', lf(ficha('X', '11.10.26'), 'X'), ('con_fecha', date(2026, 10, 11)))
    chk('(B) norm_ean como moloka_ean_norm', [mod['norm_ean'](x) for x in ('0004999', ' 49-99 ', None, '000', 4999)],
        ['4999', '4999', None, None, '4999'])

    # (G) el registro no lleva datos
    for nombre, out in salidas.items():
        chk('(G) %s: el registro no lleva ningún dato' % nombre, [x for x in CENTINELAS if x in out], [])
    return rotos


# ── El módulo de verdad ────────────────────────────────────────────────────────────────────
print('── El módulo de verdad ──')
comprobar(MODULO, eq)

# (F) por estructura
arbol = ast.parse(io.open(MODULO, encoding='utf-8').read())
tablas = {n.args[0].value for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr == 'table' and n.args and isinstance(n.args[0], ast.Constant)}
eq('(F) por estructura: el módulo solo nombra estas cuatro tablas', sorted(tablas),
   ['codigos_proveedor', 'disp_estado', 'osma_mapa_ficha', 'productos'])
eq('(F) …sin rpc, sin storage, sin traceback ni logging',
   (sum(1 for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and n.attr in ('rpc', 'storage')),
    sorted({a.name for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
            if a.name in ('traceback', 'logging')})), (0, []))

# (H) el programa principal
sys.path.insert(0, RAIZ)
g = runpy.run_path(PROGRAMA, run_name='osma_fv_banco')
eq('(H) las 00:00 de Madrid en UTC (octubre, UTC+2; diciembre, UTC+1)',
   (g['inicio_del_dia_de_madrid'](datetime(2026, 10, 7, 5, 20, tzinfo=timezone.utc)),
    g['inicio_del_dia_de_madrid'](datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc)),
    g['inicio_del_dia_de_madrid'](datetime(2026, 12, 7, 5, 20, tzinfo=timezone.utc))),
   (datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc), datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc),
    datetime(2026, 12, 6, 23, 0, tzinfo=timezone.utc)))


def paso9(base, web):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        r = g['fechas_de_vuelta'](base, web, AHORA, escribir=True)
    return r, salida.getvalue()


import escaner2_osma_fecha_vuelta as _fv  # noqa: E402 — el mismo que importa el programa
_fv.repasar.__defaults__ = (True, lambda s: None, lambda: 0.0, None)
b, w = escenario()
r, out = paso9(b, w)
eq('(H) paso 9 bien: código 0 y su línea de recuentos, sin datos', (r, 'FECHAS DE VUELTA' in out, [x for x in CENTINELAS if x in out]),
   (0, True, []))
b, w = escenario()
w.rutas['/search?search=4999990000017'] = (429, '/x', 'NOMBRE-FV')
r, out = paso9(b, w)
eq('(H) paso 9 con 429: código 1 y OSMA_FECHAS_PARADAS', (r, 'OSMA_FECHAS_PARADAS' in out), (1, True))
b, w = escenario()
for k, v in list(w.rutas.items()):
    w.rutas[k] = (v[0], v[1], v[2].replace('schema.org/Offer', 'schema.org/Thing'))
r, out = paso9(b, w)
eq('(H) paso 9 con la web cambiada (ninguna ficha se puede leer): código 1 y OSMA_FECHAS_WEB_CAMBIADA',
   (r, 'OSMA_FECHAS_WEB_CAMBIADA' in out), (1, True))
b, w = escenario()
b.falla['disp_estado'] = True
r, out = paso9(b, w)
eq('(H) paso 9 si la base falla: código 1, solo el tipo del error', (r, 'OSMA_FECHAS_NO_LEIDAS' in out, 'inexistente' in out),
   (1, True, False))

# (I) LA MITAD ROJA
print('\n── (I) La mitad roja ──')
fuente = io.open(MODULO, encoding='utf-8').read()
MUTANTES = [
    ('sin_pausa', '            if falta > 0:\n', '            if False:\n', '(D) al menos 2 s entre peticiones, todas'),
    ('sin_parar_al_429', "        if r.status_code in PARAR_EN or any(", "        if False and any(",
     '(D) 429 a la segunda: PARA en seco tras ella, sin reintento'),
    ('sin_comprobar_codigo', "        if r.status_code == 200 and _misma_web(r.url) and _ultimo_tramo(r.url) == codigo:\n",
     "        if r.status_code == 200 and _misma_web(r.url):\n",
     '(B) la búsqueda que da una lista: abre el enlace que acaba en el código; sin fecha → NULL con su hora'),
    ('sin_sku', "    if skus and skus != {codigo}:\n", "    if False:\n",
     '(B) no escribe: página inglesa, otro artículo, fecha que no existe, sin ficha'),
    ('primera_fecha_de_la_pagina', "    m = _FECHA_RE.search(f.ofertas[0])\n", "    m = _FECHA_RE.search(html)\n",
     '(B) la fecha del bloque del producto, no la del carrusel (dd.mm.aa → 2026)'),
    ('sin_tope', "        if self.hechas >= self.tope:\n", "        if False:\n",
     '(D) el tope: 40 peticiones como mucho; el resto, sin turno (mañana)'),
    ('relee_lo_de_hoy', "        if leida is not None and leida >= inicio_hoy:\n", "        if False:\n",
     '(A) …primero los nunca leídos y DESPUÉS el de lectura vieja; el leído hoy, no se reabre'),
]
with tempfile.TemporaryDirectory() as carpeta:
    for nombre, viejo, nuevo, vigila in MUTANTES:
        eq('(I) el ancla del mutante %s está UNA vez en el módulo' % nombre, fuente.count(viejo), 1)
        ruta = os.path.join(carpeta, 'mutante_%s.py' % nombre)
        io.open(ruta, 'w', encoding='utf-8').write(fuente.replace(viejo, nuevo))
        rotos = comprobar(ruta, lambda *_a: None)
        eq('(I) con el mutante %s el banco se pone ROJO en «%s»' % (nombre, vigila), vigila in rotos, True)

print()
if fallos:
    print('ROJO: %d fallo(s): %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: las fechas de vuelta eligen los agotados nuestros, leen la fecha del bloque del producto, comprueban '
      'que es su artículo, borran la de los que vuelven, respetan los 2 s, el tope de 40 y la parada al 403/429, '
      'no escriben con --sin-escribir, su registro no suelta datos, y cada mutante lo pone en rojo.')
