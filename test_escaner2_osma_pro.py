# -*- coding: utf-8 -*-
"""Banco del ESCANEO PRO DE OSMA (encargo AG, 02-oct-2026): la parte pura y los DOS programas de verdad, con dobles.

PARTE A · LO PURO (escaner2_osma.py), en este proceso:
  A1  el porte con la regla de la puerta comun: la ultima factura con porte (NULL delante, como Postgres) ÷ pedido;
  A2  el precio con el porte, al centimo (Kukident 3,299 → 3,52), y 🔴 el porte UNA vez: con el porte sumado dos
      veces, `comprobar_porte` lo caza;
  A3  la foto: cada articulo por una puerta previa o en la foto, crudo = previas + foto; EAN de relleno fuera; el
      duplicado se queda con el codigo enlazado;
  A4  los enlaces (la familia del Lenor da dos ASIN; el chase y las fichas inactivas no) y (AG2) LA lista: los EAN de
      OSMA + el EAN de nuestra ficha de cada codigo de la foto, sin repetir; y que fichas quedan fuera porque Keepa
      no conoce su EAN (keepa_escaparate);
  A5  las fichas de cada articulo con UN CSV: por codigo gana, la misma ficha no sale dos veces, el EAN nuevo con
      otra ficha se aparta, una fila con el EAN de nuestra ficha es de la fila de su codigo, y una ficha enlazada no
      se cuelga de otro articulo;
  A6  el factor de nuestros packs, el de lib/packs de la v2 (Ultra Pro x1-x4, Protefix x1-x2-x5, Lenor x1-x2, la
      casilla; el «2-PACK» suelto y el «Maxi pack 128» no son packs);
  A7  la puerta de un pack: coste = unidades × precio, la misma ficha, y el detalle lo dice.

PARTE B · LOS PROGRAMAS (escaner2_osma_barrido.py y escaner2_osma_cruce.py), cada uno en su proceso, contra un
`supabase` en memoria (sin red, sin secretos, sin produccion):
  B1  [sin_llave] sin la llave de servicio no nace ningun cliente;
  B2  [bueno] barrido → 'esperando_csv' con su foto, SU lista (una: n_tandas 1, sin asins.txt) y barrido.json; se
      sube el CSV de ES (con la CABECERA REAL del Visualizador, 561 columnas, sacada de un export del 02-oct-2026) y
      uno de FR, que el cruce ignora y avisa; cruce → 'lista', cuadra, solo ES, y el Excel: las hojas del PRO de HEO
      (sin «Chase_manual»), el FORMATO del Excel viejo de verdad con «Ficha compartida» y «No habrá más» al final,
      Kukident a 3,52 (el porte una vez), la Protefix pack 3 a 3 × 2,13, la Corega por su codigo (por el EAN de su
      ficha), el Lenor fuera (Keepa no conoce su EAN, y el Resumen lo dice) y «no habrá más» donde toca;
  B3  🔴 el registro (repo PUBLICO) no lleva ni un EAN, ASIN ni precio;
  B4  nada escribe fuera de escaner2_* (ni disp_*, ni productos, ni codigos_proveedor, ni facturas);
  B5  [porte_doble] la puerta comun con el porte sumado dos veces → la pasada falla y no sale lista;
  B6  [memoria] OSMA fuera de 'disp' → falla; [vieja] la foto no es la de la ultima descarga → falla.
"""
import base64
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ═══════════════════════════════════════════════════════════════════════════════
# EL DOBLE DE SUPABASE (el de test_escaner2_punta_a_punta.py, con lo que usan estos programas)
# ═══════════════════════════════════════════════════════════════════════════════
class _Resp:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Consulta:
    def __init__(self, bd, tabla):
        self.bd, self.tabla = bd, tabla
        self.op, self.filtros, self.payload = 'select', [], None
        self.cuenta, self.orden, self.rango, self.tope = False, None, None, None

    def select(self, _cols='*', count=None):
        self.op, self.cuenta = 'select', (count == 'exact')
        return self

    def insert(self, filas):
        self.op, self.payload = 'insert', filas if isinstance(filas, list) else [filas]
        return self

    def update(self, cambios):
        self.op, self.payload = 'update', cambios
        return self

    def upsert(self, filas, **_kw):
        self.op, self.payload = 'upsert', filas
        return self

    def delete(self):
        self.op = 'delete'
        return self

    def eq(self, k, v):
        self.filtros.append((k, v))
        return self

    def order(self, col, desc=False):
        self.orden = (col, desc)
        return self

    def range(self, a, b):
        self.rango = (a, b)
        return self

    def limit(self, n):
        self.tope = n
        return self

    def execute(self):
        self.bd.setdefault('ops', []).append([self.bd.get('programa'), self.op, self.tabla])
        filas = self.bd['tablas'].setdefault(self.tabla, [])
        if self.op in ('upsert', 'delete'):
            return _Resp([])
        if self.op == 'insert':
            for f in self.payload:
                filas.append(json.loads(json.dumps(f, default=str)))
            return _Resp(self.payload)
        sel = [f for f in filas if all(str(f.get(k)) == str(v) for k, v in self.filtros)]
        if self.op == 'update':
            for f in sel:
                f.update(json.loads(json.dumps(self.payload, default=str)))
            return _Resp(sel)
        if self.orden:
            sel = sorted(sel, key=lambda f: (f.get(self.orden[0]) is None, str(f.get(self.orden[0]))),
                         reverse=self.orden[1])
        n = len(sel)
        if self.rango:
            sel = sel[self.rango[0]:self.rango[1] + 1]
        if self.tope is not None:
            sel = sel[:self.tope]
        return _Resp(sel, n if self.cuenta else None)


class _Cubo:
    def __init__(self, bd, cubo):
        self.bd, self.cubo = bd, cubo

    def _objs(self):
        return self.bd['storage'].setdefault(self.cubo, {})

    def upload(self, ruta, datos, _opciones=None):
        self._objs()[ruta] = base64.b64encode(datos if isinstance(datos, bytes) else datos.encode()).decode()
        return {'Key': ruta}

    def download(self, ruta):
        if ruta not in self._objs():
            raise RuntimeError('404 Object not found: %s/%s' % (self.cubo, ruta))
        return base64.b64decode(self._objs()[ruta])

    def list(self, carpeta=None, opciones=None):
        op = dict({'limit': 100, 'offset': 0}, **(opciones or {}))
        pref = (carpeta or '').rstrip('/') + '/'
        nombres = sorted(r[len(pref):] for r in self._objs() if r.startswith(pref) and '/' not in r[len(pref):])
        trozo = nombres[op['offset']:op['offset'] + op['limit']]
        return [{'name': n, 'created_at': '2026-10-02T09:%02d:00Z' % i, 'metadata': {'size': 1}}
                for i, n in enumerate(trozo)]


class _Cliente:
    def __init__(self, bd):
        self.bd = bd
        self.storage = types.SimpleNamespace(from_=lambda cubo: _Cubo(bd, cubo))

    def table(self, nombre):
        return _Consulta(self.bd, nombre)


def hijo(ruta_estado, programa):
    with open(ruta_estado, encoding='utf-8') as fh:
        bd = json.load(fh)
    bd['programa'] = programa
    clientes = []

    def crear(url, llave):
        clientes.append(llave)
        return _Cliente(bd)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = crear
    import runpy
    sys.argv = [programa]
    codigo = 0
    try:
        runpy.run_path(os.path.join(AQUI, programa), run_name='__main__')
    except SystemExit as ex:
        codigo = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
    finally:
        with open(ruta_estado, 'w', encoding='utf-8') as fh:
            json.dump(bd, fh, default=str)
        print('CLIENTES_CREADOS=%d' % len(clientes))
    sys.exit(codigo)


if __name__ == '__main__' and len(sys.argv) >= 4 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2], sys.argv[3])


def correr(ruta_estado, programa, env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ('SUPABASE_SERVICE_KEY', 'PASADA', 'GITHUB_RUN_ID')}
    env.update(env_extra, PYTHONIOENCODING='utf-8', SUPABASE_URL='https://doble.invalid')
    p = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--hijo', ruta_estado, programa],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=AQUI)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


import escaner2_motor as e2  # noqa: E402
import escaner2_osma as eo  # noqa: E402
import escaner2_heredado_pro as pro  # noqa: E402
from decimal import Decimal  # noqa: E402

M = e2.cargar_motor()


def ean13(cuerpo):
    return cuerpo + M._chk13(cuerpo)


# ═══════════════════════════════════════════════════════════════════════════════
# PARTE A · LO PURO
# ═══════════════════════════════════════════════════════════════════════════════
print('A1 · el porte, con la regla de la puerta común')
FACTURAS = [  # las cuatro de OSMA de la base, 02-oct-2026 (id, fecha, created_at, gastos_envio)
    {'id': '60fa2528', 'fecha': '2026-06-01', 'created_at': '2026-06-03T13:26:27+00:00', 'gastos_envio': None},
    {'id': '5287b495', 'fecha': '2026-06-08', 'created_at': '2026-06-19T17:18:00+00:00', 'gastos_envio': None},
    {'id': '80a08341', 'fecha': '2026-08-14', 'created_at': '2026-08-20T14:06:02+00:00', 'gastos_envio': 148.19},
    {'id': '3c3f364c', 'fecha': '2026-08-21', 'created_at': '2026-08-26T10:20:46+00:00', 'gastos_envio': 168.19}]
po = eo.porte_de(FACTURAS, 2500)
eq('A1 · la última factura con porte (21-ago, 168,19) ÷ 2.500 = 0,067276', (po['factura'], po['pct']),
   ('3c3f364c', Decimal('0.067276')))
eq('A1 · una factura con porte y SIN fecha va delante, como `ORDER BY fecha DESC` en Postgres',
   eo.porte_de(FACTURAS + [{'id': 'zz', 'fecha': None, 'created_at': None, 'gastos_envio': 99}], 2500)['factura'], 'zz')
eq('A1 · sin pedido previsto, o sin ninguna factura con porte: sin porte',
   (eo.porte_de(FACTURAS, None)['pct'], eo.porte_de(FACTURAS[:2], 2500)['pct']), (None, None))

print('A2 · el precio con el porte, y el porte UNA vez')
eq('A2 · Kukident 3,299 → 3,52 · Lenor 1,599 → 1,71 · Calgon 77 14,999 → 16,01 (los de la puerta común)',
   [eo.pa_con_porte(x, po['pct']) for x in (3.299, 1.599, 14.999)], [3.52, 1.71, 16.01])
eq('A2 · sin porte, el precio a 2 decimales (numeric(10,2)), con la mitad hacia arriba: 1,005 → 1,01',
   [eo.pa_con_porte(3.299, None), eo.pa_con_porte(1.005, None)], [3.3, 1.01])
_foto_k = [{'producto_heo': '4213', 'ean_core': '4002448039440', 'precio_unidad': 3.52}]
_puerta_k = [{'ean': '4002448039440', 'es_case': False, 'pa': 3.52, 'presente': True}]
eq('A2 · la puerta común y la foto dicen lo mismo → comprobada y sin descuadre',
   eo.comprobar_porte(_foto_k, {}, _puerta_k), (1, []))
_doble = eo.pa_con_porte(eo.pa_con_porte(3.299, po['pct']), po['pct'])
eq('A2 · 🔴 con el porte sumado dos veces (3,76) NO cuadra con la puerta común',
   (_doble, len(eo.comprobar_porte([dict(_foto_k[0], precio_unidad=_doble)], {}, _puerta_k)[1])), (3.76, 1))
eq('A2 · …y sin porte (3,30) tampoco', len(eo.comprobar_porte([dict(_foto_k[0], precio_unidad=3.3)], {}, _puerta_k)[1]), 1)

print('A3 · la foto desde la descarga')
EAN_NORMAL = ean13('400000000001')
EAN_OTRO = ean13('400000000002')
EAN_FICHA_COREGA = '5054563091970'
EAN_OSMA_COREGA = '5054563279279'


def d(codigo, ean, precio, marca='MARCA', disponible=True, fdv=False, regla=None, nombre=None):
    core = ean if (ean and not regla) else None
    return {'producto_prov': codigo, 'ean_original': ean, 'ean_core': core, 'marca': marca,
            'nombre': nombre or ('Artículo %s' % codigo), 'categoria': None, 'precio_unidad': precio,
            'disponible': disponible, 'en_oferta': False, 'fin_de_vida': fdv, 'regla': regla,
            'pasada_id': 'p-osma', 'ausencias': 0}


ESTADO = [
    d('4213', '4002448039440', 3.299, 'KUKIDENT', nombre='Kukident Aktiv Plus 99er'),
    d('1929', EAN_OSMA_COREGA, 4.199, 'COREGA', nombre='Corega Tabs 108er'),
    d('18459', '8001090747723', 1.599, 'LENOR', nombre='Lenor Trocknertücher Aprilfrisch 34er'),
    d('3000', '4009932002171', 1.999, 'PROTEFIX', nombre='Protefix Haftcreme 47g Aloe Vera'),
    d('7001', EAN_NORMAL, 2.00, 'NIVEA', fdv=True, nombre='Nivea Creme 150ml'),
    d('7002', EAN_OTRO, 1.00, None),
    d('7003', ean13('400000000003'), 1.00, 'NIVEA', disponible=False),
    d('7004', '1111111111111', 1.50, 'SENTIO', nombre='Display surtido'),
    d('7005', '12345', 1.50, 'AXE', regla='ean_forma_rara'),
    d('7006', EAN_NORMAL, 2.50, 'NIVEA'),
    d('1056', '4001499961472', 1.699, 'FROSCH', disponible=False),
]
CODIGOS = [{'codigo_proveedor': c, 'producto_id': p} for c, p in
           (('4213', 'kuki'), ('1929', 'corega'), ('18459', 'lenor1'), ('1056', 'frosch'), ('9999', 'no-existe'))]
PRODUCTOS = [
    {'id': 'kuki', 'asin': 'B001PASC5E', 'ean': '4002448039440', 'activo': True, 'es_chase': False,
     'nombre': 'Kukident Active Plus 99', 'iva_pct': 0.21, 'stock_moloka': 3},
    {'id': 'corega', 'asin': 'B0C9T9RZT3', 'ean': EAN_FICHA_COREGA, 'activo': True, 'es_chase': False,
     'nombre': 'Corega pastillas limpiadoras para dentaduras', 'iva_pct': 0.21, 'stock_moloka': 0},
    {'id': 'lenor1', 'asin': 'B014DGG0OQ', 'ean': '8001090747723', 'activo': True, 'es_chase': False,
     'nombre': 'Lenor se está secando. abril fresco, paquete de 34', 'iva_pct': 0.21, 'stock_moloka': 0},
    {'id': 'lenor2', 'asin': 'B07HCJQ45L', 'ean': '8001090747723', 'activo': True, 'es_chase': False,
     'nombre': 'Pack 2. Lenor se está secando. abril fresco, paquete de 34', 'iva_pct': 0.21, 'stock_moloka': 0},
    {'id': 'lenor-chase', 'asin': 'B0CHASE000', 'ean': '8001090747723', 'activo': True, 'es_chase': True,
     'nombre': 'Lenor chase (no existe: el chase no lleva ASIN)', 'iva_pct': 0.21, 'stock_moloka': 0},
    {'id': 'lenor-viejo', 'asin': 'B0VIEJO000', 'ean': '8001090747723', 'activo': False, 'es_chase': False,
     'nombre': 'Lenor ficha inactiva', 'iva_pct': 0.21, 'stock_moloka': 0},
    {'id': 'protefix3', 'asin': 'B01GIE0QSM', 'ean': '4009932002171', 'activo': True, 'es_chase': False,
     'nombre': 'Crema Adhesiva Protefix 47g Extra Fuerte Aloe Vera Pack 3', 'iva_pct': 0.21, 'stock_moloka': 0,
     'unidades_por_pack': 3},
    {'id': 'frosch', 'asin': 'B0BCPP43YN', 'ean': '4001499961472', 'activo': True, 'es_chase': False,
     'nombre': 'Limpiador de ducha y baño Frosch Citrus 500 ml', 'iva_pct': 0.21, 'stock_moloka': 0},
]
ENLACES, AVISOS_ENL = eo.enlaces_de(CODIGOS, PRODUCTOS)
FOTO, APARTADOS, CUENTAS = eo.construir_foto(ESTADO, ENLACES, M, po['pct'])
eq('A3 · 🔴 crudo 11 = no disponible 2 + sin marca 1 + EAN raro o de relleno 2 + duplicado 1 + foto 5',
   (CUENTAS['n_crudo'], CUENTAS['previas']['no_disponible'], CUENTAS['previas']['marca_fuera'],
    CUENTAS['previas']['ean_forma_rara'], CUENTAS['previas']['duplicado_proveedor'], CUENTAS['n_foto'],
    CUENTAS['cuadra_previo']), (11, 2, 1, 2, 1, 5, True))
eq('A3 · el EAN de relleno (1111111111111) sale con su motivo, no va a Keepa',
   [a['detalle'] for a in APARTADOS if a['producto_heo'] == '7004'],
   ['EAN 1111111111111 con el dígito de control mal: de relleno o mal escrito'])
eq('A3 · del duplicado se queda el más barato (7001 a 2,00 frente a 7006 a 2,50)',
   sorted(f['producto_heo'] for f in FOTO), ['18459', '1929', '3000', '4213', '7001'])
_por = {f['producto_heo']: f for f in FOTO}
eq('A3 · en la foto: Price_net en precio_catalogo y el precio con el porte en precio_unidad (Kukident, Corega)',
   [(_por[c]['precio_catalogo'], _por[c]['precio_unidad']) for c in ('4213', '1929')], [(3.299, 3.52), (4.199, 4.48)])
_dup = eo.construir_foto([d('5', EAN_NORMAL, 1.0), d('4213', EAN_NORMAL, 9.0)], ENLACES, M, None)
eq('A3 · con el mismo EAN, gana el código ENLAZADO aunque sea más caro',
   ([f['producto_heo'] for f in _dup[0]], [a['detalle'] for a in _dup[1]]),
   (['4213'], ['Mismo EAN que el código 4213: me quedo con 4213 (el código 4213 está enlazado a nuestra ficha)']))

print('A4 · los enlaces y LA lista (AG2)')
eq('A4 · los enlaces: el Lenor trae suelta y Pack 2 (ni el chase ni la inactiva); el código sin ficha se avisa',
   ({c: e['asins'] for c, e in ENLACES.items()}, AVISOS_ENL),
   ({'1056': ['B0BCPP43YN'], '1929': ['B0C9T9RZT3'], '4213': ['B001PASC5E'], '18459': ['B014DGG0OQ', 'B07HCJQ45L']},
    ['El código 9999 de OSMA apunta a una ficha que no está en productos']))
ASINS = ['B0C9T9RZT3', 'B001PASC5E', 'B014DGG0OQ', 'B07HCJQ45L']  # los de los códigos de la foto
LISTA, EANS_FICHAS = eo.lista_para_keepa_osma(FOTO, ENLACES, M)
eq('🔴 A4 · UNA lista: los EAN de OSMA de la foto y, detrás, el de nuestra ficha de la Corega (el único que OSMA no '
   'traía ya); sin repetir el del Kukident ni el del Lenor',
   LISTA, e2.lista_para_keepa(FOTO) + [EAN_FICHA_COREGA])
eq('A4 · el EAN de nuestra ficha, por código, solo de los enlazados QUE ESTÁN EN LA FOTO (el 1056 no tiene existencias)',
   EANS_FICHAS, {'1929': EAN_FICHA_COREGA, '4213': '4002448039440', '18459': '8001090747723'})
eq('A4 · …y sin repetir aunque el EAN de la ficha venga con ceros delante (el Kukident con «00…»: no entra otra vez)',
   eo.lista_para_keepa_osma(FOTO, dict(ENLACES, **{'4213': dict(ENLACES['4213'], ean_ficha='004002448039440')}), M)[0],
   LISTA)
_ENL_FOTO = {c: e for c, e in ENLACES.items() if c in EANS_FICHAS}
KEEPA = [  # keepa_escaparate: lo que Keepa lista de cada ficha (02-oct-2026, medido para el Kukident y el Lenor)
    {'asin': 'B001PASC5E', 'dominio': 'es', 'ean_keepa_crudo': '4002448039440', 'upc_keepa': None, 'fecha_foto': '2026-10-01'},
    {'asin': 'B014DGG0OQ', 'dominio': 'es', 'ean_keepa_crudo': '5413149849693,5413149849709,7427128022579,8001841036984',
     'upc_keepa': None, 'fecha_foto': '2026-10-02'},
    {'asin': 'B07HCJQ45L', 'dominio': 'es', 'ean_keepa_crudo': '4055902127801', 'upc_keepa': None, 'fecha_foto': '2026-10-02'},
    # En FR sí lo conoce (inventado): no cuenta, el cruce es solo de ES.
    {'asin': 'B07HCJQ45L', 'dominio': 'fr', 'ean_keepa_crudo': '8001090747723', 'upc_keepa': None, 'fecha_foto': '2026-10-03'}]
FK = eo.fuera_de_keepa(_ENL_FOTO, EANS_FICHAS, KEEPA, {'es'})
eq('🔴 A4 · fuera: las dos fichas del Lenor (Keepa no conoce su EAN en ES); la Corega, sin fila, «no se sabe»',
   FK, {'fuera': [('18459', 'B014DGG0OQ', 'Keepa no conoce el EAN 8001090747723 de la ficha (ES)'),
                  ('18459', 'B07HCJQ45L', 'Keepa no conoce el EAN 8001090747723 de la ficha (ES)')],
        'sin_dato': [('1929', 'B0C9T9RZT3')], 'fecha': '2026-10-02'})
eq('A4 · …con la fila de FR que sí lo lista, el Lenor Pack 2 ya no está fuera (se mira en los países del cruce)',
   [x[1] for x in eo.fuera_de_keepa(_ENL_FOTO, EANS_FICHAS, KEEPA, {'es', 'fr'})['fuera']], ['B014DGG0OQ'])
eq('A4 · …una ficha sin EAN, fuera; y la línea del Resumen lo dice todo, con la fecha de keepa_escaparate',
   (eo.fuera_de_keepa({'1': {'asins': ['B0SINEAN01']}}, {}, [], {'es'})['fuera'], eo.texto_fuera_de_keepa(FK)),
   ([('1', 'B0SINEAN01', 'la ficha no tiene EAN')],
    '18459 · B014DGG0OQ: Keepa no conoce el EAN 8001090747723 de la ficha (ES) | 18459 · B07HCJQ45L: Keepa no conoce '
    'el EAN 8001090747723 de la ficha (ES) | sin fila en keepa_escaparate (no se sabe): 1929 · B0C9T9RZT3 '
    '(keepa_escaparate del 2026-10-02)'))

print('A5 · las fichas de cada artículo, con UN CSV')
_r = lambda asin, t='': {'asin': asin, 'titulo': t, 'buybox': 10.0, 'es_fba': True, 'nuevo': 10.0, 'compct': 15.0,  # noqa: E731
                         'fba': 3.0, 'rank': 1000.0, 'rank90': 1000.0}
_corega = _por['1929']
_nuestra = _r('B0C9T9RZT3', 'por el EAN de nuestra ficha')
_ajena = _r('B0AJENA001', 'otra ficha con el EAN de la nuestra')
_datos = {M.norm(EAN_OSMA_COREGA): [_r('B0NUEVA001')], M.norm(EAN_FICHA_COREGA): [_nuestra, _ajena]}
_ids = eo.de_las_fichas(_datos, EANS_FICHAS, M)
c, camino, aparte = eo.candidatos_osma(_corega, _datos, eo.indice_por_asin(_datos), ENLACES['1929'], set(ASINS), M,
                                       EAN_FICHA_COREGA, _ids)
eq('🔴 A5 · la Corega: por su código, con la fila del EAN de NUESTRA ficha; lo del EAN nuevo de OSMA y la otra ficha '
   'con nuestro EAN, apartado',
   ([x['titulo'] for x in c], camino, [x['asin'] for x in aparte]),
   (['por el EAN de nuestra ficha'], 'codigo', ['B0NUEVA001', 'B0AJENA001']))
_datos2 = {M.norm(EAN_OSMA_COREGA): [_r('B0NUEVA001'), _nuestra], M.norm(EAN_FICHA_COREGA): [_nuestra]}
c, camino, aparte = eo.candidatos_osma(_corega, _datos2, eo.indice_por_asin(_datos2), ENLACES['1929'], set(ASINS), M,
                                       EAN_FICHA_COREGA, eo.de_las_fichas(_datos2, EANS_FICHAS, M))
eq('A5 · la misma ficha por los dos caminos (EAN de OSMA y EAN de la ficha): una, la del código',
   ([x['asin'] for x in c], camino, [x['asin'] for x in aparte]), (['B0C9T9RZT3'], 'codigo', ['B0NUEVA001']))
_datos3 = {M.norm(EAN_OSMA_COREGA): [_r('B0NUEVA001')]}
c, camino, aparte = eo.candidatos_osma(_corega, _datos3, eo.indice_por_asin(_datos3), ENLACES['1929'], set(ASINS), M,
                                       EAN_FICHA_COREGA, frozenset())
eq('A5 · si el CSV no trae nuestra ficha, por su EAN de OSMA, como cualquier otra fila',
   ([x['asin'] for x in c], camino, aparte), (['B0NUEVA001'], 'ean_sin_codigo', []))
_otro = eo.construir_foto([d('7010', EAN_FICHA_COREGA, 1.0, 'COREGA')], {}, M, None)[0][0]
c, camino, aparte = eo.candidatos_osma(_otro, _datos, eo.indice_por_asin(_datos), None, set(ASINS), M, None, _ids)
eq('🔴 A5 · otro artículo de OSMA con el EAN de nuestra ficha NO se queda sus filas: son de la fila del código',
   ([x['asin'] for x in c], camino, [x['asin'] for x in aparte]), ([], 'ean', ['B0C9T9RZT3', 'B0AJENA001']))
c, camino, aparte = eo.candidatos_osma(_por['7001'], {M.norm(EAN_NORMAL): [_r('B0C9T9RZT3'), _r('B0NIVEA001')]}, {},
                                       None, set(ASINS), M, None, frozenset())
eq('A5 · una ficha enlazada a otro código no se cuelga de otro artículo aunque comparta su EAN',
   ([x['asin'] for x in c], camino, [x['asin'] for x in aparte]), (['B0NIVEA001'], 'ean', ['B0C9T9RZT3']))

print('A6 · el factor de nuestros packs (lib/packs de la v2)')
_g = lambda nombres: eo.factores_por_ficha([{'id': str(i), 'nombre': n, 'ean': '1', 'activo': True}  # noqa: E731
                                           for i, n in enumerate(nombres)])
eq('A6 · Ultra Pro 100/200/300/400 → x1-x4 (plantilla común)',
   _g(['Fundas Standard Regular Cards (%d fundas) Ultra Pro' % n for n in (100, 200, 300, 400)]),
   {'0': 1, '1': 2, '2': 3, '3': 4})
eq('A6 · Protefix suelta, PACK 2, PACK 5 → x1-x2-x5 (marcador)',
   _g(['almohadilla adhesiva protefix para mandíbula', 'almohadilla adhesiva protefix para mandíbula PACK 2',
       'almohadilla adhesiva protefix para mandíbula PACK 5']), {'0': 1, '1': 2, '2': 5})
eq('A6 · Lenor: el 34 de «paquete de 34» NO es el pack → x1-x2',
   _g(['Lenor se está secando. abril fresco, paquete de 34',
       'Pack 2. Lenor se está secando. abril fresco, paquete de 34']), {'0': 1, '1': 2})
eq('A6 · fuera de un grupo el marcador no cuenta («2-PACK», «Maxi pack 128»); la casilla sí',
   (eo.factores_por_ficha([{'id': 'a', 'nombre': 'Funko POP 2-PACK', 'ean': '1', 'activo': True},
                           {'id': 'b', 'nombre': 'Kleenex Maxi pack 128', 'ean': '2', 'activo': True},
                           {'id': 'c', 'nombre': 'Crema Pack 3', 'ean': '3', 'activo': True, 'unidades_por_pack': 3}])),
   {'c': 3})
FACTORES, AV_PACKS = eo.factor_por_asin(PRODUCTOS)
eq('A6 · por ASIN: el Lenor Pack 2 ×2 y la Protefix ×3 (casilla); los demás, 1', (FACTORES, AV_PACKS),
   ({'B07HCJQ45L': 2, 'B01GIE0QSM': 3}, []))

print('A7 · la puerta de un pack: unidades × precio')
_prot = _por['3000']
_cands = {'ES': [dict(_r('B01GIE0QSM', 'Protefix crema adhesiva 47 g, pack de 3'), buybox=19.0, nuevo=19.0)]}
_caidas = {'ES': {'B01GIE0QSM': 30}}
_params = {'umbral': 6, 'paises_filtro': ['ES'], 'paises_calculo': ['ES']}
M.poner_catalogo_propio([p for p in PRODUCTOS if p['activo']])
_rp = eo.decidir_osma(_prot, _cands, _caidas, _params, M, None, {}, None, FACTORES)
eq('A7 · la Protefix pack 3: coste 3 × 2,13 = 6,39, y es el coste con el que se calcula',
   (_rp['asin'], _rp['factor'], _rp['pa'], _rp['paises']['ES']['pa']), ('B01GIE0QSM', 3, 6.39, 6.39))
eq('A7 · …y el detalle lo dice', 'pack de 3: coste 3 × 2,13 € = 6,39 €' in _rp['detalle'], True)
_r1 = e2.decidir(_prot, _cands, _caidas, _params, M, None, {})
eq('A7 · …con un margen distinto del de una unidad (sin el factor saldría mejor de lo que es)',
   _r1['paises']['ES']['margen'] > _rp['paises']['ES']['margen'], True)

print('A8 · (AM) los packs de Amazon, con las señales REALES del CSV de la primera pasada (655b3e06, 02-oct-2026)')
# (ASIN, nombre en OSMA, «Número de artículos», «Valor de la unidad», «Tipo de unidad», «Paquete: Cantidad», «Tamaño»,
# «Título»), sacadas del CSV con `senales_pack_csv`, no tecleadas.
SENALES = [
    ('B004SGFVHE', 'Food Chupa Chups Melody Pops 15g', '48', '48', 'unidad', '1', '48 Unidad (Paquete de 1)',
     'CHUPA CHUPS Melody Pops, Caramelo con Palo, Sabor Fresa, Pack 48 Piruletas'),
    ('B00XAQ99PI', 'Food Haribo Mega Roulette 45g Frucht', '1', '1080', 'gramo', '1', '45 g (Paquete de 24)',
     'Haribo Mega Roulette Caramelos de Goma - 45g cada paquete, 1080 gr en total'),
    ('B0DDF9RDYG', 'Seife Lux 80g Aqua Sparkle', '12', '960', 'gramo', '12', '80 g (Paquete de 12)',
     'Lux Aqua Sparkle - Lote de 12 jabones perfumados florales con aroma a almizcle y aceite de menta (80 g)'),
    ('B08W2BS7VD', 'RUSTIK Stumpenkerze 190x68 altrot', '4', '4', 'unidad', '1', '19 x 7 cm',
     'Bolsius Vela rústica de pilar rojo oscuro, paquete de 4, larga duración de combustión de 85 horas, vela '
     'doméstica, decoración de interiores, sin perfume, cera vegana natural, sin aceite de palma, 19 x'),
    ('B003UWY00Q', 'Swiffer Wet Wischtücher Nachfüllpackung 24er', '1', '72', 'unidad', '1', '24 unità (Confezione da 1)',
     'Swiffer Limpiador De Pisos Suelo Mojado De Toallitas Con El Limón Fresco Olor'),
    ('B000GPI7YA', 'TESA Klebefilm 33mx15mm Lose, Preis pro Rolle', '1', '10', 'unidad', '1', '33m x 15mm',
     'tesa film transparente, Cinta Autoadhesiva Resistente al Paso del Tiempo y al Rompimiento, Cinta de Oficina con '
     'Fuerte Adhesión, 33 m x 15 mm, 10 Piezas'),
    ('B098DWKTCY', 'Dr. Beckmann Fleckenteufel 50ml Fett+Saucen', '3', '150', 'mililitro', '3', '50 ml (Paquete de 3)',
     'Dr. Beckmann Manchas grasas y salsas | Quitamanchas especial contra manchas de grasa, manchas de chocolate, etc. '
     '| 3 x 50 ml'),
    ('B00829FH1I', 'Vileda Schwammtuch Original 8er', '8', '8', 'unidad', '1', '8 Unidad (Paquete de 1)',
     'Vileda 142274 esponja paño – Alta Absorción hasta 100 ml, 1 paquete de 8 [colores surtidos]'),
    ('B0DCNWGPHM', 'Ohropax Ohrstöpsel Color 8 Stück', '8', '8', 'unidad', '1', '8 unidades',
     'OHROPAX Tapones para los oídos Color – Tapones para los oídos de espuma suave – Muy cómodos incluso durante mu'),
    ('B0DCNTJKHZ', 'Ohropax Ohrstöpsel Soft 10 Stück', '10', '10', 'unidad', '1', '10 unidades',
     'OHROPAX Tapones para los oídos blandos de espuma suave – muy discretos y cómodos – Aislamiento acústico SNR 31'),
    ('B000EGQT7I', 'Batterie VARTA Akku Power Mignon AA 2er Blister', '2', '2', 'unidad', '1', '2 unidades',
     'VARTA Pilas AA, recargables, paquete de 2, Recharge Accu Power, batería recargable, 2100 mAh Ni-MH, sin efecto'),
    ('B08H5F8184', 'Gillette Blue3 Einwegrasierer 12er', '1', '12', 'unidad', '1', '12 unidad (Paquete de 1)',
     'Gillette Blue 3 Smooth Afeitadoras Desechables, 12 unidades (paquete de 1)'),
    ('B0000WU094', 'Gillette Contour Plus 10er Klingen', '10', '10', 'unidad', '1', '1 unidad (Paquete de 10)',
     'Gillette Contour Plus Recambio de Maquinilla de Afeitar para Hombre 10 Recambios'),
    ('B000094G2Z', 'Wasserfilter Kartusche BRITA CLASSIC 3er-Pack', '3', '3', 'unidad', '3', '3 Unidad (Paquete de 1)',
     'Brita M91904 - Filtro classic, 3 unidades'),
    ('B014SY8BRC', 'Tempo Taschentücher 56x10 4 lagig', '560', '560', 'unidad', '1', '1 unidad (Paquete de 560)',
     'Tempo Classic Pañuelos (56 paquetes de 10 pañuelos)'),
    ('B0C9T9RZT3', 'Corega Gebissreiniger Tabs Intensiv 108er', '1', '108', 'unidad', '1', '',
     'Corega Limpiador dental intensivo de TABS, protección completa para prótesis dentales extraíbles/terceros '
     'dientes, 1 x 108 pastillas de limpieza de dientes'),
    ('B0BXBDB433', 'Calgon 4in1 Tabs 77Stk Wasserenthärter 1001g', '1', '77', 'unidad', '', '77 unidad (Paquete de 1)',
     'Calgon Tabs 4 en 1 77'),
    ('B0BLW8TF8V', 'Pampers Premium Protect. Gr.1 New Baby 180 Stück', '1', '180', 'unidad', '1', 'Größe 1 (180 Stück)',
     'Pampers Pañales para bebé tamaño 1 (2-5 kg) Premium Protection, Newborn, HalBMONATSBOX, la mejor comodidad y p'),
    ('B0BLW7N46Z', 'Pampers Baby Dry Gr.7 Extra Large (15+kg) 132 St.', '1', '132', 'unidad', '1', 'Größe 7 (132 Stück)',
     'Pampers Pañales tamaño 7 (15 kg+) Baby Dry, extra grande, caja de meses, hasta 12 horas de protección contra f'),
    ('B0BCFMZ8WR', 'Swiffer Wet Wischtücher NF 24er Morning Fresh', '1', '24', 'unidad', '', '24 unidad (Paquete de 1)',
     'Mopa Swiffer Paños Húmedos Con Fragancia Fresca De Frescura de la mañana 24 Unidades Para Una Limpieza Rápida '),
    ('B0794VHRVZ', 'Lenor Trocknertücher 34er Aprilfrisch', '1', '34', 'unidad', '1', '34 unidad (Paquete de 1)',
     'Lenor -Toallitas de secado con aroma a flores de primavera, cuidado de la ropa en la secadora, lavado sin arru'),
    ('B087RWYJN3', 'Dr. Beckmann Waschmaschinen Reiniger Frische 3er', '3', '60', 'gramo', '1', '20 g (Paquete de 3)',
     'Dr. Beckmann Limpiador de lavadora | 3 x 20 g Caps'),
    ('B0FC2RR77V', 'Adidas GP EdT 100ml + Dusch 250ml Ice Dive', '6', '350', 'mililitro', '', '58.33 ml (Paquete de 6)',
     'adidas Ice Dive Giftset including an Eau de Toilette and Shower Gel'),
    ('B0CVHD3RKQ', 'Scholl Einlegesohle GelActiv Everyday Größe S', '2', '2', 'unidad', '1', '35.5-40.5 cm',
     'Scholl GelActiv Plantillas Everyday para mujer, pies cómodos durante todo el día, amortiguación de espuma visc'),
    ('B01GIE0QSM', 'Protefix Haftcreme 47g Extra Stark mit Aloe Vera', '3', '141', 'gramo', '3', '47 g (Paquete de 3)',
     'PROTEFIX Crema Adhesiva Extra Fuerte Aloe Vera 3x40ml')]
_sen = {a: {'n_art': n, 'valor_ud': v, 'tipo_ud': t, 'paquete': q, 'tamano': tam, 'titulo': tit}
        for a, _nom, n, v, t, q, tam, tit in SENALES}
_nom = {a: x[1] for x in SENALES for a in (x[0],)}


def _veredicto(asin):
    x = eo.factor_pack_amazon(_sen[asin], eo.cantidad_osma(_nom[asin]))
    return x['estado'], x['factor']


SI_PACK = {'B004SGFVHE': 48, 'B00XAQ99PI': 24, 'B0DDF9RDYG': 12, 'B08W2BS7VD': 4, 'B000GPI7YA': 10, 'B098DWKTCY': 3}
eq('🔴 A8 · se multiplican, cada uno con dos señales o más: Melody Pops ×48, Haribo ×24, Lux ×12, Rustik ×4, TESA ×10, '
   'Fleckenteufel ×3', {a: _veredicto(a) for a in SI_PACK}, {a: (eo.PACK_SI, n) for a, n in SI_PACK.items()})
eq('🔴 A8 · el Swiffer Wet 24er NO va ×3: el contenido dice 72 pero el tamaño dice «24 unità» (y nuestra ficha, '
   'enlazada a su código, es «refill 24\'s»): se contradicen → posible pack, sin multiplicar',
   _veredicto('B003UWY00Q'), (eo.PACK_DUDOSO, 1))
NO_PACK = ['B00829FH1I', 'B0DCNWGPHM', 'B0DCNTJKHZ', 'B000EGQT7I', 'B08H5F8184', 'B0000WU094', 'B000094G2Z',
           'B014SY8BRC', 'B0C9T9RZT3', 'B0BXBDB433', 'B0BLW8TF8V', 'B0BLW7N46Z', 'B0BCFMZ8WR', 'B0794VHRVZ', 'B087RWYJN3']
eq('🔴 A8 · NO se multiplican: la cantidad de OSMA ya coincide (Vileda 8er, Ohropax 8 y 10 Stück, VARTA 2er, Blue3 12er, '
   'Contour 10er, BRITA 3er, Tempo 56x10, Corega 108er, Calgon 77Stk, Pampers 180 y 132, Swiffer NF 24er, Lenor 34er, '
   'Dr. Beckmann 3er)', {a: _veredicto(a) for a in NO_PACK}, {a: (eo.PACK_NO, 1) for a in NO_PACK})
eq('🔴 A8 · Adidas: Amazon dice «6 artículos», pero 100 + 250 ml = 350 ml es lo que lleva el ASIN: el set, no un pack',
   _veredicto('B0FC2RR77V'), (eo.PACK_NO, 1))
eq('A8 · Scholl GelActiv: «2 artículos» y «2 unidad» son el mismo recuento del vendedor (una sola señal; es un par): '
   'posible pack, no se multiplica', _veredicto('B0CVHD3RKQ'), (eo.PACK_DUDOSO, 1))
eq('A8 · la cantidad del nombre de OSMA: medida, recuento, «56x10», el set con «+», la vela «190x68» (medida, no '
   'recuento), el expositor y el «6x50g»',
   [(c['n'], c['medida'], c['ambigua']) for c in map(eo.cantidad_osma, (
       'Food Chupa Chups Melody Pops 15g', 'Swiffer Wet Wischtücher Nachfüllpackung 24er',
       'Tempo Taschentücher 56x10 4 lagig', 'Adidas GP EdT 100ml + Dusch 250ml Ice Dive',
       'RUSTIK Stumpenkerze 190x68 altrot', 'Duftöl 10ml Christkindl in Glasfl. im 18er Tray',
       'WC Frisch Kraft-Aktiv Lemon XXL-Pack 6x50g', 'Perwoll Feinwaschmittel Sport 27WL 1,35 Liter',
       'Pampers Baby Dry Gr.7 Extra Large (15+kg) 132 St.', 'Wundverb. Erste Hilfe Reise Set 32 teil.',
       'Kosmetik 3er Set mit 4 Stück'))],
   [(None, (15.0, 'g'), False), (24, None, False), (560, None, False), (None, (350.0, 'ml'), False),
    (None, None, False), (None, (10.0, 'ml'), False), (6, (300.0, 'g'), False), (None, (1350.0, 'ml'), False),
    (132, None, False), (32, None, False), (None, None, True)])
eq('A8 · con dos recuentos distintos en el nombre de OSMA, aunque Amazon diga lo mismo dos veces: posible pack',
   eo.factor_pack_amazon(_sen['B08W2BS7VD'], eo.cantidad_osma('Kosmetik 3er Set mit 4 Stück'))['estado'],
   eo.PACK_DUDOSO)

# La decision: el pack de Amazon cuesta N × el precio, el «posible pack» nunca es COMPRAR, y nuestro pack no se
# multiplica dos veces. Precios de Amazon inventados (los de `_r`: 10 €, 15 %, 3 € de FBA).
_melody = eo.construir_foto([d('7020', ean13('400000000020'), 0.299, 'CHUPA CHUPS',
                               nombre='Food Chupa Chups Melody Pops 15g')], {}, M, po['pct'])[0][0]
_sp = {'ES': {'B004SGFVHE': _sen['B004SGFVHE'], 'B0CVHD3RKQ': _sen['B0CVHD3RKQ'], 'B01GIE0QSM': _sen['B01GIE0QSM']}}
_c_mel = {'ES': [_r('B004SGFVHE', 'Pack 48 Piruletas')]}
_r_uno = eo.decidir_osma(_melody, _c_mel, {'ES': {'B004SGFVHE': 30}}, _params, M, None, {}, None, {})
eq('A8 · sin las señales (como hasta hoy), las Melody Pops a 0,32 € salen COMPRAR', (_r_uno['puerta'], _r_uno['pack']),
   ('f', None))
_r48 = eo.decidir_osma(_melody, _c_mel, {'ES': {'B004SGFVHE': 30}}, _params, M, None, {}, None, {}, senales_pack=_sp)
eq('🔴 A8 · con ellas: pack de 48 en Amazon, coste 48 × 0,32 € = 15,36 € → NO COMPRAR, y el detalle lo dice como el pack '
   'nuestro', (_r48['puerta'], _r48['factor'], _r48['pa'], _r48['paises']['ES']['pa'], _r48['pack'],
               'pack de 48 en Amazon: coste 48 × 0,32 € = 15,36 €' in _r48['detalle']),
   ('d', 48, 15.36, 15.36, 'amazon', True))
_scholl = eo.construir_foto([d('7021', ean13('400000000021'), 6.499, 'SCHOLL',
                               nombre='Scholl Einlegesohle GelActiv Everyday Größe S')], {}, M, po['pct'])[0][0]
_c_sch = {'ES': [dict(_r('B0CVHD3RKQ', 'Scholl GelActiv'), buybox=25.0, nuevo=25.0)]}
_rs = eo.decidir_osma(_scholl, _c_sch, {'ES': {'B0CVHD3RKQ': 30}}, _params, M, None, {}, None, {}, senales_pack=_sp)
_rs0 = eo.decidir_osma(_scholl, _c_sch, {'ES': {'B0CVHD3RKQ': 30}}, _params, M, None, {}, None, {})
eq('🔴 A8 · el posible pack con margen de COMPRAR baja a VALORAR (puerta e, y ES dice VALORAR), con el mismo coste y '
   'margen, y el detalle dice por qué',
   (_rs0['puerta'], _rs['puerta'], _rs['motivo'], _rs['paises']['ES']['decision'], _rs['pa'],
    _rs['paises']['ES']['margen'] == _rs0['paises']['ES']['margen'], _rs['detalle'].startswith('VALORAR en ES (margen '),
    'posible pack en Amazon: revisar (OSMA sin cantidad: 1 unidad; Amazon: contenido 2 unidad → 2 · n.º de artículos 2 '
    '→ 2)' in _rs['detalle'], _rs['factor']),
   ('f', 'e', 'e_valorar', 'VALORAR', 6.94, True, True, True, 1))
_rp3 = eo.decidir_osma(_prot, _cands, _caidas, _params, M, None, {}, None, FACTORES, senales_pack=_sp)
eq('🔴 A8 · la Protefix es NUESTRO pack de 3 (y Amazon también dice 3): 3 × 2,13 = 6,39, no 9 × 2,13; ni se mira el de '
   'Amazon', (_rp3['factor'], _rp3['pa'], _rp3['pack'], _rp3['pack_amazon'], 'en Amazon' in _rp3['detalle']),
   (3, 6.39, 'nuestro', None, False))
_rc = eo.decidir_osma(_melody, _c_mel, {'ES': {'B004SGFVHE': 2}}, _params, M, None, {}, None, {}, senales_pack=_sp)
eq('A8 · lo que no se vende (puerta c) no se mira: sin decisión, no hay coste que corregir',
   (_rc['puerta'], _rc['pack_amazon'], _rc['factor']), ('c', None, 1))

print('A9 · (AM) las fórmulas vivas de «Análisis»')
eq('A9 · «PA (€)»: el sin porte × (1 + porte ÷ pedido), redondeado a 2 DESPUÉS; sin pedido, sin porte',
   eo.formula_pa('AD', 7, 1), '=ROUND(AD7*(1+IF(N(PedidoPrevisto)>0,N(PorteEnvio)/PedidoPrevisto,0)),2)')
eq('A9 · …y en un pack de N, N × el precio de UNA unidad ya redondeado (como `decidir_osma` y la Protefix 3 × 2,13)',
   eo.formula_pa('AD', 7, 48), '=48*ROUND(AD7/48*(1+IF(N(PedidoPrevisto)>0,N(PorteEnvio)/PedidoPrevisto,0)),2)')
eq('A9 · «Decisión»: la de decision_de del viejo (≥ 10 % COMPRAR, ≥ 1 % VALORAR); el posible pack, sin COMPRAR',
   (eo.formula_decision('P', 7, False), eo.formula_decision('P', 7, True)),
   ('=IF(P7*100>=10,"COMPRAR",IF(P7*100>=1,"VALORAR","NO COMPRAR"))', '=IF(P7*100>=1,"VALORAR","NO COMPRAR")'))
_dec_viejo = e2.sacar_piezas(e2.RUTA_MOTOR, ('decision_de',), ())['decision_de']
eq('A9 · 🔴 los umbrales de la fórmula son la frontera de decision_de del viejo (se le pregunta a él justo en el umbral '
   'y una millonésima por debajo)',
   [_dec_viejo(eo.UMBRAL_COMPRAR / 100), _dec_viejo(eo.UMBRAL_COMPRAR / 100 - 1e-6),
    _dec_viejo(eo.UMBRAL_VALORAR / 100), _dec_viejo(eo.UMBRAL_VALORAR / 100 - 1e-6)],
   ['COMPRAR', 'VALORAR', 'VALORAR', 'NO COMPRAR'])

print('A10 · (Mapa de OSMA, 04-oct-2026) el mapa fijo: código OSMA → ASIN → unidades')
eq('A10 · 🔴 el Lenor pack de 2 (18459, B07HCJQ45L): PA = 2 × 1,599 × (1 + 168,19/2.500) = 3,41, con UN redondeo al '
   'final (con el porte como Decimal o como el texto de barrido.json); el suelto 1,71; sin porte 3,20',
   (eo.pa_mapa(1.599, 2, po['pct']), eo.pa_mapa(1.599, 2, str(po['pct'])), eo.pa_mapa(1.599, 1, po['pct']),
    eo.pa_mapa(1.599, 2, None)), (3.41, 3.41, 1.71, 3.2))
_EST_MAPA = ESTADO + [d('2346', ean13('400845500000'), 2.299, 'DR. BECKMANN', disponible=False,
                        nombre='Dr. Beckmann Fleckstift Express 9ml')]
_MAPA = [{'codigo_osma': '18459', 'asin': 'B07HCJQ45L', 'unidades': 2, 'es_nuestra': True},
         {'codigo_osma': '18459', 'asin': 'B014DGG0OQ', 'unidades': 1, 'es_nuestra': True},
         {'codigo_osma': '2346', 'asin': 'B003U1NE40', 'unidades': 1, 'es_nuestra': True},
         {'codigo_osma': '7003', 'asin': 'B0OTRO0001', 'unidades': 1, 'es_nuestra': False},
         {'codigo_osma': '55555', 'asin': 'B0FUERA001', 'unidades': 1, 'es_nuestra': False}]
_md, _ma, _mc, _mf = eo.mapa_de_la_descarga(_MAPA, _EST_MAPA)
eq('A10 · el mapa contra la descarga: disponibles (a la lista de ASIN), agotados (a su hoja) y el código que la descarga '
   'no trae (se cuenta)',
   ([(m['codigo'], m['asin'], m['unidades']) for m in _md], [(m['codigo'], m['asin']) for m in _ma], _mf,
    eo.lista_asin_mapa(_md), _mc['2346']['precio_catalogo'], _mc['2346']['disponible']),
   ([('18459', 'B014DGG0OQ', 1), ('18459', 'B07HCJQ45L', 2)], [('2346', 'B003U1NE40'), ('7003', 'B0OTRO0001')], 1,
    ['B014DGG0OQ', 'B07HCJQ45L'], 2.299, False))
eq('A10 · 🔴 el Dr. Beckmann 2346, agotado y nuestro: sale en su hoja con «agotado en OSMA», sin Keepa ni margen; el '
   'agotado que no es nuestro, no',
   eo.agotados_nuestros(_ma, _mc, eo.fichas_nuestras_de(PRODUCTOS)),
   [['2346', 'Dr. Beckmann Fleckstift Express 9ml', 'B003U1NE40', '—', 1, 2.299, 'agotado en OSMA']])
eq('A10 · el CSV de la lista de ASIN se reconoce por sus ASIN (casi todos del mapa); el de EAN, no',
   [eo.es_csv_del_mapa({'B07HCJQ45L': 27, 'B014DGG0OQ': 28}, ['B014DGG0OQ', 'B07HCJQ45L']),
    eo.es_csv_del_mapa({'B001PASC5E': 1, 'B0NUEVA001': 1, 'B0C9T9RZT3': 1, 'B014DGG0OQ': 1}, ['B014DGG0OQ']),
    eo.es_csv_del_mapa({}, ['B014DGG0OQ']), eo.es_csv_del_mapa({'B07HCJQ45L': 1}, [])], [True, False, False, False])
_rm = eo.decidir_osma(_prot, _cands, _caidas, _params, M, None, {}, None, FACTORES, mapa_codigo={'B01GIE0QSM': 2},
                      pct=po['pct'])
eq('A10 · 🔴 con el ASIN en el mapa de su código, MANDAN LAS UNIDADES DEL MAPA (2, no nuestro pack de 3), las señales de '
   'Amazon ni se miran, y el coste es el del mapa (2 × 1,999 × 1,067276 = 4,27)',
   (_rm['factor'], _rm['pack'], _rm['pa'], _rm['paises']['ES']['pa'], _rm['pack_amazon'],
    'pack de 2 del mapa: coste 2 × precio de OSMA × (1 + porte) = 4,27 €' in _rm['detalle']),
   (2, 'mapa', 4.27, 4.27, None, True))
eq('A10 · …y con el mapa de otro ASIN, todo como siempre (nuestro pack de 3, 6,39)',
   [eo.decidir_osma(_prot, _cands, _caidas, _params, M, None, {}, None, FACTORES, mapa_codigo={'B0OTRO0001': 1},
                    pct=po['pct'])[k] for k in ('factor', 'pa')], [3, 6.39])


# ═══════════════════════════════════════════════════════════════════════════════
# PARTE B · LOS DOS PROGRAMAS, DE PUNTA A PUNTA
# ═══════════════════════════════════════════════════════════════════════════════
with io.open(os.path.join(AQUI, 'test_escaner2_osma_cabecera.json'), encoding='utf-8') as fh:
    CABECERA = json.load(fh)['cabecera']
COL_PAIS, COL_CAIDAS = e2.columnas_keepa()
COL_PADRE, COL_NVAR, COL_RANK = e2.columnas_ficha_compartida()
C = pro.CSV_COLS


def csv_real(pais, filas):
    """Un export del Visualizador con la CABECERA REAL (561 columnas) y solo las celdas que se leen."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CABECERA)
    ix = {h: i for i, h in enumerate(CABECERA)}
    for asin, eans, caidas, precio, titulo, *extra in filas:
        fila = [''] * len(CABECERA)
        for h, v in ((C['asin'], asin), (COL_PAIS, pais), ('Título', titulo), (C['ean'], eans),
                     (C['rank'], '9000'), (C['rank90'], '11000'), (COL_CAIDAS, caidas), (C['buybox'], precio),
                     (C['es_fba'], 'yes'), (C['nuevo'], precio), (C['fba'], '3.10'), (C['compct'], '15.01 %'),
                     (C['nvar'], ''), (COL_PADRE, '')) + tuple((extra[0] if extra else {}).items()):
            fila[ix[h]] = v
        w.writerow(fila)
    return ('\ufeff' + buf.getvalue()).encode('utf-8')


PUERTA = [{'proveedor': 'OSMA', 'ean': '4002448039440', 'es_case': False, 'pa': 3.52, 'presente': True},
          {'proveedor': 'OSMA', 'ean': EAN_FICHA_COREGA, 'es_case': False, 'pa': 4.48, 'presente': True},
          {'proveedor': 'OSMA', 'ean': '8001090747723', 'es_case': False, 'pa': 1.71, 'presente': True},
          {'proveedor': 'OSMA', 'ean': '4009932002171', 'es_case': False, 'pa': 2.13, 'presente': True},
          {'proveedor': 'OSMA', 'ean': '4001499961472', 'es_case': False, 'pa': 1.81, 'presente': False},
          {'proveedor': 'HEO', 'ean': '889698000000', 'es_case': False, 'pa': 9.99, 'presente': True}]
SEMBRADAS = ('disp_pasada', 'disp_estado', 'disp_fuente', 'disp_parametros', 'facturas', 'codigos_proveedor',
             'productos', 'v_escaner_fuente', 'inventario_fba', 'keepa_escaparate', 'osma_mapa_ficha')
# (Mapa de OSMA) El mapa fijo: el Lenor 18459 con sus tres fichas (el pack de 2 incluido), el Kukident por su ficha
# (también la trae el CSV de EAN: manda la del mapa), la Frosch 1056 agotada y nuestra (a su hoja) y un agotado que no
# es nuestro (fuera de la hoja).
MAPA_BD = [{'codigo_osma': '18459', 'asin': 'B014DGG0OQ', 'unidades': 1, 'es_nuestra': True},
           {'codigo_osma': '18459', 'asin': 'B07HCJQ45L', 'unidades': 2, 'es_nuestra': True},
           {'codigo_osma': '18459', 'asin': 'B0794VHRVZ', 'unidades': 1, 'es_nuestra': False},
           {'codigo_osma': '4213', 'asin': 'B001PASC5E', 'unidades': 1, 'es_nuestra': True},
           {'codigo_osma': '1056', 'asin': 'B0BCPP43YN', 'unidades': 1, 'es_nuestra': False},
           {'codigo_osma': '7003', 'asin': 'B0OTRO0001', 'unidades': 1, 'es_nuestra': False}]
ASINS_MAPA = ['B001PASC5E', 'B014DGG0OQ', 'B0794VHRVZ', 'B07HCJQ45L']


def estado_inicial(escena):
    puerta = json.loads(json.dumps(PUERTA))
    estado = json.loads(json.dumps(ESTADO))
    fuente = 'disp'
    n_leidas = len(estado)
    if escena == 'porte_doble':
        puerta[0]['pa'] = 3.76
    if escena == 'memoria':
        fuente = 'memoria'
    if escena == 'vieja':
        n_leidas += 1
    return {'tablas': {
        'escaner2_parametros': [{'proveedor': 'HEO', 'umbral_caidas_30d': 6, 'paises_filtro': ['ES', 'IT', 'FR', 'DE'],
                                 'paises_calculo': ['ES', 'IT', 'FR', 'DE']},
                                # (AG2) OSMA, solo España: la fila que deja la migración de la v2.
                                {'proveedor': 'OSMA', 'umbral_caidas_30d': 6, 'paises_filtro': ['ES'],
                                 'paises_calculo': ['ES']}],
        'disp_pasada': [{'id': 'p-vieja', 'proveedor': 'OSMA', 'estado': 'aplicada', 'creada_en': '2026-10-01T12:01:00+00:00',
                         'terminada_en': '2026-10-01T12:02:00+00:00', 'n_leidas': 3050},
                        {'id': 'p-osma', 'proveedor': 'OSMA', 'estado': 'aplicada', 'creada_en': '2026-10-02T05:15:38+00:00',
                         'terminada_en': '2026-10-02T05:15:46+00:00', 'n_leidas': n_leidas},
                        {'id': 'p-heo', 'proveedor': 'HEO', 'estado': 'aplicada', 'creada_en': '2026-10-02T06:00:00+00:00',
                         'n_leidas': 99}],
        'disp_estado': [dict(f, proveedor='OSMA') for f in estado]
        + [dict(d('X1', ean13('400000000009'), 1.0), proveedor='OSMA', ausencias=1)],
        'disp_fuente': [{'proveedor': 'HEO', 'fuente': 'disp'}, {'proveedor': 'OSMA', 'fuente': fuente}],
        'disp_parametros': [{'proveedor': 'HEO', 'pedido_previsto_eur': None},
                            {'proveedor': 'OSMA', 'pedido_previsto_eur': 2500}],
        'facturas': [dict(f, proveedor='OSMA') for f in FACTURAS]
        + [{'id': 'heo1', 'proveedor': 'HEO', 'fecha': '2026-09-30', 'created_at': None, 'gastos_envio': 500}],
        'codigos_proveedor': [dict(c, proveedor='OSMA') for c in CODIGOS],
        'productos': json.loads(json.dumps(PRODUCTOS)),
        'v_escaner_fuente': puerta,
        'inventario_fba': [],
        'keepa_escaparate': json.loads(json.dumps(KEEPA)),
        'osma_mapa_ficha': json.loads(json.dumps(MAPA_BD)),
    }, 'storage': {}}


def caso(escena):
    tmp = tempfile.mkdtemp(prefix='e2osma_')
    ruta = os.path.join(tmp, 'estado.json')
    inicial = estado_inicial(escena)
    with open(ruta, 'w', encoding='utf-8') as fh:
        json.dump(inicial, fh)
    cod, log = correr(ruta, 'escaner2_osma_barrido.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira',
                                                          'GITHUB_RUN_ID': '515151'})
    bd = json.load(open(ruta, encoding='utf-8'))
    return cod, log, bd, ruta, inicial


print('B1 · [sin_llave] sin la llave de servicio no se corre')
_tmp = tempfile.mkdtemp(prefix='e2osma_')
_ruta = os.path.join(_tmp, 'estado.json')
json.dump(estado_inicial('bueno'), open(_ruta, 'w', encoding='utf-8'))
for _prog in ('escaner2_osma_barrido.py', 'escaner2_osma_cruce.py'):
    _cod, _log = correr(_ruta, _prog, {'PASADA': '00000000-0000-4000-8000-000000000009'})
    eq('B1 · %s: ROJO, la línea exacta y NINGÚN cliente' % _prog,
       (_cod, 'ESCANER2_NO_EJECUTADO: sin llave de servicio' in _log, 'CLIENTES_CREADOS=0' in _log), (1, True, True))

print('B2 · [bueno] barrido → LA lista → el CSV de ES (y uno de FR, que no cuenta) → cruce → Excel')
cod, log, bd, ruta, inicial = caso('bueno')
eq('B2 · el barrido sale en VERDE', cod, 0)
pas = [p for p in bd['tablas']['escaner2_pasada'] if p.get('run_id') == 515151][0]
eq('B2 · 🔴 la pasada: OSMA, modo todas, esperando_csv, crudo 11 = previas 6 + foto 5, UNA lista (n_tandas 1)',
   (pas['proveedor'], pas['modo'], pas['estado'], pas['n_crudo'], pas['n_foto'],
    sum(pas['p_' + p] for p in e2.PUERTAS_PREVIAS), pas['n_tandas'], pas['tanda'], pas['ruta_lista']),
   ('OSMA', 'todas', 'esperando_csv', 11, 5, 6, 1, 6, 'osma/%s/eans.txt' % pas['id']))
_alm = bd['storage']['escaner2']
_txt = lambda k: base64.b64decode(_alm[k]).decode('utf-8')  # noqa: E731
eq('🔴 B2 · en el almacén cerrado, LA lista de EAN (los 5 EAN de OSMA + el de la ficha de la Corega), n_eans_lista = 6, '
   'y (Mapa de OSMA) asins.txt aparte',
   (_txt('osma/%s/eans.txt' % pas['id']).split('\n'), pas['n_eans_lista'],
    sorted(k.split('/')[-1] for k in _alm if k.startswith('osma/%s/' % pas['id']))),
   (LISTA, 6, ['asins.txt', 'barrido.json', 'eans.txt']))
eq('🔴 B2 · (Mapa de OSMA) asins.txt: los ASIN del mapa de los códigos DISPONIBLES (Kukident y Lenor), sin los agotados; '
   'y barrido.json lleva los agotados para su hoja',
   (_txt('osma/%s/asins.txt' % pas['id']).split('\n'),
    [(m['codigo'], m['asin']) for m in json.loads(_txt('osma/%s/barrido.json' % pas['id']))['mapa']['agotados']]),
   (ASINS_MAPA, [('1056', 'B0BCPP43YN'), ('7003', 'B0OTRO0001')]))
_sc = json.loads(_txt('osma/%s/barrido.json' % pas['id']))
eq('B2 · barrido.json: de qué descarga sale, el porte comprobado en 4 filas de la puerta común, los 3 enlaces de la foto '
   'y el EAN de cada ficha (1 que OSMA no traía)',
   (_sc['disp_pasada'], _sc['porte']['pct'], _sc['porte_comprobado'], sorted(_sc['enlaces']), _sc['eans_fichas'],
    _sc['n_eans_fichas_nuevos'], 'lista_asins' in _sc),
   ('p-osma', '0.067276', 4, ['18459', '1929', '4213'], EANS_FICHAS, 1, False))
_fk = [f for f in bd['tablas']['escaner2_foto'] if f['producto_heo'] == '4213'][0]
eq('B2 · en la foto, Kukident a 3,52 (el porte una vez)', (_fk['precio_catalogo'], _fk['precio_unidad']), (3.299, 3.52))

# Fernando exporta LA lista en el Visualizador de España y suelta el CSV en el buzón. Keepa trae la Corega por los
# dos EAN (la caja nueva de OSMA con otra ficha, y nuestra ficha por el suyo) y NO trae el Lenor (no conoce su EAN).
# Y un CSV de FR que se cuela (el buzón de la v2 ya lo rechaza): el cruce lo ignora y lo avisa.
_carpeta = 'osma/%s/csv/' % pas['id']
# (AM) Con las señales de pack: la ficha de la Corega es un pack de 3 en Amazon (324 tabletas = 3 × las 108 de OSMA, y el
# tamaño lo dice), y la Protefix, nuestro pack de 3, también lo dice Amazon (no se multiplica otra vez).
_PACK_COREGA = {'Detalles de la unidad: Valor de la unidad': '324', 'Detalles de la unidad: Tipo de unidad': 'unidad',
                'Tamaño': '108 unidad (Paquete de 3)'}
_PACK_PROTEFIX = {'Número de artículos': '3', 'Paquete: Cantidad': '3', 'Tamaño': '47 g (Paquete de 3)'}
_filas_es = [('B001PASC5E', '4002448039440', '30', '12.95', 'Kukident Active Plus 99 Tabletas'),
             ('B0NUEVA001', EAN_OSMA_COREGA, '40', '9.99', 'Corega Tabs caja nueva'),
             ('B0C9T9RZT3', EAN_FICHA_COREGA, '18', '11.50', 'Corega Tabs pastillas limpiadoras 108', _PACK_COREGA),
             ('B01GIE0QSM', '4009932002171', '25', '19.50', 'Protefix Crema adhesiva Aloe Vera 47 g pack de 3',
              _PACK_PROTEFIX),
             ('B0NIVEA001', EAN_NORMAL, '12', '8.90', 'Nivea Creme 150 ml'),
             # Dos fichas para el EAN de la Nivea: la hoja «Ambiguos» del viejo tiene algo que enseñar.
             ('B0NIVEA002', EAN_NORMAL, '9', '9.40', 'Nivea Creme 150 ml lata')]
_alm[_carpeta + '20261002-090000-KeepaExport-2026-10-02-VisualizadorDeProductos.csv'] = \
    base64.b64encode(csv_real('es', _filas_es)).decode()
_alm[_carpeta + '20261002-090100-KeepaExport-2026-10-02-VisualizadorDeProductos (1).csv'] = \
    base64.b64encode(csv_real('fr', _filas_es)).decode()
# (Mapa de OSMA) Y el CSV de la lista de ASIN (modo «ASIN» del Visualizador): el pack de 2 del Lenor SIN EAN en Keepa (el
# lector por EAN lo perdería), el suelto nuestro con el EAN de OSMA, el otro suelto y el Kukident (también en el de EAN).
_filas_asin = [('B014DGG0OQ', '8001090747723', '28', '6.95', 'Lenor toallitas secadora Aprilfrisch 34'),
               ('B07HCJQ45L', '', '27', '12.95', 'Lenor toallitas secadora pack 2 x 34'),
               ('B0794VHRVZ', '8001090747723', '17', '6.49', 'Lenor toallitas secadora 34'),
               ('B001PASC5E', '4002448039440', '30', '12.95', 'Kukident Active Plus 99 Tabletas')]
_alm[_carpeta + '20261002-090200-KeepaExport-2026-10-02-VisualizadorDeProductos (2).csv'] = \
    base64.b64encode(csv_real('es', _filas_asin)).decode()
_ruta_m = os.path.join(tempfile.mkdtemp(prefix='e2osma_m_'), 'asin.csv')
with open(_ruta_m, 'wb') as _fh:
    _fh.write(csv_real('es', _filas_asin))
_por_asin_m = eo.leer_csv_mapa(_ruta_m, pro)
_por_ean_v = pro.leer_csv_visualizador(_ruta_m)
eq('A10 · (Mapa de OSMA) el CSV de ASIN, leído por ASIN con el lector del Pro sin tocar: trae el pack sin EAN (que el '
   'lector por EAN pierde) y cada ficha sale IGUAL que por EAN',
   (sorted(_por_asin_m), 'B07HCJQ45L' in {r['asin'] for rs in _por_ean_v.values() for r in rs},
    _por_asin_m['B0794VHRVZ'] == next(r for r in _por_ean_v[pro.norm('8001090747723')] if r['asin'] == 'B0794VHRVZ')),
   (sorted(ASINS_MAPA), False, True))
bd.pop('programa', None)
json.dump(bd, open(ruta, 'w', encoding='utf-8'), default=str)
cod2, log2 = correr(ruta, 'escaner2_osma_cruce.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'PASADA': pas['id'],
                                                      'GITHUB_RUN_ID': '525252'})
bd = json.load(open(ruta, encoding='utf-8'))
T = bd['tablas']
_alm = bd['storage']['escaner2']
eq('B2 · el cruce sale en VERDE', cod2, 0)
cr = [c for c in T['escaner2_cruce'] if c.get('run_id') == 525252][0]
eq('B2 · 🔴 el cruce: lista, cuadra, catálogo 11 = previas 6 + 5 puertas, con los países de OSMA (solo ES)',
   (cr['estado'], cr['cuadra'], cr['n_crudo'], cr['n_previas'], cr['n_entradas'], sum(cr['n_' + x] for x in 'abcdef'),
    cr['paises_filtro'], cr['paises_calculo'], cr['paises_usados']),
   ('lista', True, 11, 6, 5, 5, ['ES'], ['ES'], ['ES']))
eq('🔴 B2 · los CSV: el de EAN y (Mapa de OSMA) el de ASIN, de ES, cuentan, cada uno por su lista; el de FR se ignora y '
   'se avisa',
   (sorted((f['pais'], f['usado'], f.get('lista')) for f in cr['ficheros']), 'CSV de FR ignorado' in (cr['aviso'] or '')),
   ([('ES', True, 'asin'), ('ES', True, 'ean'), ('FR', False, 'ean')], True))
eq('B2 · y solo se calcula ES: ninguna cuenta de otro país',
   sorted({p['pais'] for p in T['escaner2_resultado_pais'] if p['cruce_id'] == cr['id']}), ['ES'])
_res = {f['producto_heo']: r for r in T['escaner2_resultado_ean'] for f in T['escaner2_foto'] if f['id'] == r['foto_id']}
eq('🔴 B2 · la Corega por su código, con la fila del EAN de nuestra ficha: nuestra ficha, no la de la caja nueva',
   (_res['1929']['asin'], 'Por el código 1929 de OSMA' in _res['1929']['detalle'], 'B0NUEVA001' in _res['1929']['detalle']),
   ('B0C9T9RZT3', True, True))
eq('B2 · el Kukident por su código (la misma ficha por los dos caminos: una)', _res['4213']['asin'], 'B001PASC5E')
eq('🔴 B2 · el Lenor NO se rescata: Keepa no conoce su EAN, el CSV no lo trae → no está (puerta a)',
   (_res['18459']['puerta'], _res['18459']['asin']), ('a', None))
eq('B2 · la Protefix (por EAN) es nuestro pack de 3', (_res['3000']['asin'], 'pack de 3' in _res['3000']['detalle']),
   ('B01GIE0QSM', True))
_rp = [p for p in T['escaner2_resultado_pais'] if p['resultado_ean_id'] == _res['3000']['id'] and p['pais'] == 'ES'][0]
eq('B2 · …y su cuenta de ES va con el coste del pack (3 × 2,13 = 6,39), aunque Amazon también diga 3: no se multiplica '
   'dos veces', (_rp['pa'], 'en Amazon' in _res['3000']['detalle']), (6.39, False))
_rpc = [p for p in T['escaner2_resultado_pais'] if p['resultado_ean_id'] == _res['1929']['id'] and p['pais'] == 'ES'][0]
eq('🔴 B2 · (AM) la ficha de la Corega es un pack de 3 en Amazon: coste 3 × 4,48 = 13,44, NO COMPRAR, y el detalle lo dice',
   (_rpc['pa'], _res['1929']['puerta'], 'pack de 3 en Amazon: coste 3 × 4,48 € = 13,44 €' in _res['1929']['detalle']),
   (13.44, 'd', True))
_rpk = [p for p in T['escaner2_resultado_pais'] if p['resultado_ean_id'] == _res['4213']['id'] and p['pais'] == 'ES'][0]
eq('B2 · el Kukident, sin pack: su cuenta de ES con 3,52 (el porte una vez)', _rpk['pa'], 3.52)
_xl = [k for k in _alm if k.startswith('osma/%s/%s/Escaner2_OSMA_' % (pas['id'], cr['id']))]
eq('B2 · el Excel, en su carpeta y con su nombre (el que guarda el cruce)', (len(_xl), cr['ruta_excel'] == _xl[0]), (1, True))
from openpyxl import load_workbook  # noqa: E402
_bytes = base64.b64decode(_alm[_xl[0]])
_wb = load_workbook(io.BytesIO(_bytes))
HOJAS_VIEJO = ['Análisis', 'Descartados', 'Ambiguos', 'Sin_rank', 'Precio por lote']
HOJAS_E2 = ['Resumen', 'Comparación', 'Varias fichas', 'Puertas', 'Puertas previas', eo.HOJA_AGOTADOS]
eq('B2 · las hojas del PRO de HEO, en su orden (sin «Chase_manual»: es de los Funko chase de HEO)',
   _wb.sheetnames, HOJAS_VIEJO + HOJAS_E2)
_cab = [c.value for c in _wb['Análisis'][1]]
eq('B2 · «Análisis»: las columnas del PRO de HEO y, AL FINAL, «No habrá más» y (AM) «Precio OSMA sin porte (€)»',
   _cab, e2.columnas_analisis() + [e2.COLUMNA_FICHA_COMPARTIDA, eo.COLUMNA_NO_HABRA_MAS, eo.COLUMNA_SIN_PORTE,
                                   eo.COLUMNA_MAPA])
import escaner2_desvios as DV  # noqa: E402
import escaner2_huella_excel as HU  # noqa: E402
_REF = HU.sin_columnas(json.load(open(os.path.join(AQUI, 'huella_excel_viejo_heo.json'), encoding='utf-8')),
                       DV.ANALISIS_QUITADAS, DV.ANALISIS_RENOMBRADAS)
_REF = HU.con_columna_al_final(_REF, e2.COLUMNA_FICHA_COMPARTIDA, e2.ANCHO_FICHA_COMPARTIDA)
_REF = HU.con_columna_al_final(_REF, eo.COLUMNA_NO_HABRA_MAS, eo.ANCHO_NO_HABRA_MAS)
_REF = HU.con_columna_al_final(_REF, eo.COLUMNA_SIN_PORTE, eo.ANCHO_SIN_PORTE)
_REF = HU.con_columna_al_final(_REF, eo.COLUMNA_MAPA, eo.ANCHO_MAPA)
# (AM) Las dos únicas fórmulas nuevas de «Análisis», escritas a mano en R1C1 (la huella pone «k» en cada número): «PA (€)»
# (la de una unidad y la de un pack) apunta a «Precio OSMA sin porte (€)» y a las celdas con nombre del Resumen, y
# «Decisión» (la normal y la del posible pack) al «Margen» de su fila. Ninguna otra.
_an_ref = next(h for h in _REF['hojas'] if h['hoja'] == 'Análisis')
_an_ref['columnas']['PA (€)']['formula'] = [
    '=ROUND(C[25]R[0]*(k+IF(N(PedidoPrevisto)>k,N(PorteEnvio)/PedidoPrevisto,k)),k)',
    '=k*ROUND(C[25]R[0]/k*(k+IF(N(PedidoPrevisto)>k,N(PorteEnvio)/PedidoPrevisto,k)),k)']
_an_ref['columnas']['Decisión']['formula'] = ['=IF(C[-1]R[0]*k>=k,"COMPRAR",IF(C[-1]R[0]*k>=k,"VALORAR","NO COMPRAR"))',
                                              '=IF(C[-1]R[0]*k>=k,"VALORAR","NO COMPRAR")']
_REF['hojas'] = [h for h in _REF['hojas'] if h['hoja'] != 'Chase_manual']
_huella = HU.huella(_bytes)
eq('B2 · 🔴 el FORMATO de las hojas del viejo es el del Excel viejo de verdad (con «Ventas», «Ficha compartida», «No habrá '
   'más», «Precio OSMA sin porte (€)» y las dos fórmulas vivas)',
   HU.diferencias(_REF, _huella, solo_hojas=HOJAS_VIEJO, vacias=('Sin_rank',)), [])
eq('B2 · …y las fórmulas vivas están de verdad en la hoja (la huella de arriba solo dice que no hay otras)',
   [sorted(next(h for h in _huella['hojas'] if h['hoja'] == 'Análisis')['columnas'][c]['formula'])
    for c in ('PA (€)', 'Decisión')],
   [sorted(_an_ref['columnas']['PA (€)']['formula']), [_an_ref['columnas']['Decisión']['formula'][0]]])
_filas = list(_wb['Análisis'].iter_rows(min_row=2, values_only=True))
_i = {n: _cab.index(n) for n in ('EAN', 'ASIN', 'PA (€)', 'Nombre', 'Decisión', 'Coherencia caja',
                                 eo.COLUMNA_NO_HABRA_MAS, eo.COLUMNA_SIN_PORTE)}
_l_sin = _wb['Análisis'].cell(row=1, column=_i[eo.COLUMNA_SIN_PORTE] + 1).column_letter
_por_ean = {r[_i['EAN']]: (n, r) for n, r in enumerate(_filas, 2)}
_n, _k = _por_ean['4002448039440']
eq('B2 · 🔴 el porte UNA vez: el Kukident lleva en «PA (€)» la fórmula sobre su precio sin porte (3,299), que con el '
   'pedido y el porte del Resumen da los 3,52 de la puerta común (lo prueba Excel en el parte)',
   (_k[_i['PA (€)']], _k[_i[eo.COLUMNA_SIN_PORTE]]), (eo.formula_pa(_l_sin, _n, 1), 3.299))
_n, _k = _por_ean['4009932002171']
eq('B2 · la Protefix pack 3: «PA (€)» = 3 × la unidad redondeada, sin porte 3 × 1,999, y el nombre y la coherencia lo dicen',
   (_k[_i['PA (€)']], _k[_i[eo.COLUMNA_SIN_PORTE]], _k[_i['Nombre']], _k[_i['Coherencia caja']]),
   (eo.formula_pa(_l_sin, _n, 3), 5.997, 'Protefix Haftcreme 47g Aloe Vera · pack de 3 (3 × 2,13 €)',
    'pack de 3: coste 3 × 2,13 € = 6,39 €'))
_n, _k = _por_ean[EAN_OSMA_COREGA]
eq('🔴 B2 · (AM) la Corega, pack de 3 en Amazon: «PA (€)» = 3 × la unidad, «Coherencia caja» lo dice',
   (_k[_i['PA (€)']], _k[_i[eo.COLUMNA_SIN_PORTE]], _k[_i['Coherencia caja']]),
   (eo.formula_pa(_l_sin, _n, 3), 12.597, 'pack de 3 en Amazon: coste 3 × 4,48 € = 13,44 €'))
eq('B2 · «Decisión» viva en las filas con cuenta (la de su margen)',
   sorted({_k[_i['Decisión']] == eo.formula_decision('P', _n, False) for _n, _k in _por_ean.values()}), [True])
eq('B2 · «no habrá más» en la fila del descatalogado (Nivea) y en ninguna otra',
   sorted((r[_i['EAN']], r[_i[eo.COLUMNA_NO_HABRA_MAS]]) for r in _filas if r[_i[eo.COLUMNA_NO_HABRA_MAS]]),
   [(EAN_NORMAL, 'no habrá más')])
# (AM) OSMA calcula un solo país: «Análisis» pinta solo ES, una fila por artículo que se vende (HEO sigue con cuatro).
# (Mapa de OSMA) Las fichas del mapa, de «Puertas» (van todas allí, con su marca en la última columna).
_pu = list(_wb['Puertas'].iter_rows(values_only=True))
_pu_mapa = [r for r in _pu[1:] if r[-1]]
_def_bd = [r for r in T['escaner2_resultado_ean'] if r['cruce_id'] == cr['id'] and r['puerta'] in 'def']
_sustituidas = [r for r in _def_bd if r['asin'] in ASINS_MAPA]
_mapa_def = [r for r in _pu_mapa if r[4][0] in 'def']
eq('🔴 B2 · «Análisis»: solo ES; las filas de las puertas d, e y f MENOS las que sustituye el mapa (el Kukident) MÁS las '
   'fichas del mapa que se venden; todas con su cuenta',
   (sorted({r[_cab.index('País')] for r in _filas}), len(_filas), [r['asin'] for r in _sustituidas],
    all(r[_cab.index('Decisión')] != 'Sin datos' for r in _filas)),
   (['ES'], len(_def_bd) - len(_sustituidas) + len(_mapa_def), ['B001PASC5E'], True))
eq('🔴 B2 · (Mapa de OSMA) «Puertas»: las 4 fichas del mapa de códigos disponibles, con su marca al final; el pack de 2 '
   'del Lenor con PA 3,41 (2 × 1,599 × 1,067276, un redondeo)',
   (_pu[0][-1], sorted(r[-1] for r in _pu_mapa), next(r[3] for r in _pu_mapa if 'B07HCJQ45L' in r[-1])),
   (eo.COLUMNA_MAPA, sorted(['ficha del mapa · B001PASC5E', 'ficha del mapa · B014DGG0OQ', 'ficha del mapa · B0794VHRVZ',
                             'pack ×2 (ficha del mapa) · B07HCJQ45L']), 3.41))
_i_mapa = _cab.index(eo.COLUMNA_MAPA)
_lenor2 = [(n, r) for n, r in enumerate(_filas, 2) if r[_i['ASIN']] == 'B07HCJQ45L']
eq('🔴 B2 · (Mapa de OSMA) en «Análisis», el Lenor pack de 2: UNA fila, su marca al final, «PA (€)» viva sobre 2 × 1,599 '
   'sin porte (que con el porte del Resumen da 3,41) y el nombre lo dice',
   (len(_lenor2), _lenor2[0][1][_i_mapa], _lenor2[0][1][_i['PA (€)']], _lenor2[0][1][_i[eo.COLUMNA_SIN_PORTE]],
    round(_lenor2[0][1][_i[eo.COLUMNA_SIN_PORTE]] * (1 + 168.19 / 2500), 2), _lenor2[0][1][_i['Nombre']])
   if _lenor2 else None,
   (1, 'pack ×2 (ficha del mapa)', eo.formula_pa(_l_sin, _lenor2[0][0], 1) if _lenor2 else None, 3.198, 3.41,
    'Lenor Trocknertücher Aprilfrisch 34er · pack ×2 (ficha del mapa)'))
eq('B2 · (Mapa de OSMA) el Kukident sale UNA vez en «Análisis», como ficha del mapa (manda la del mapa)',
   [r[_i_mapa] for r in _filas if r[_i['ASIN']] == 'B001PASC5E'], ['ficha del mapa'])
_ag = list(_wb[eo.HOJA_AGOTADOS].iter_rows(values_only=True))
eq('🔴 B2 · (Mapa de OSMA) la ÚLTIMA hoja, «Nuestros agotados en OSMA»: la Frosch 1056 (nuestra por productos, aunque el '
   'mapa no la marque), con «agotado en OSMA»; el agotado que no es nuestro, no',
   (_wb.sheetnames[-1], [list(r) for r in _ag]),
   (eo.HOJA_AGOTADOS, [eo.COLUMNAS_AGOTADOS, ['1056', 'Artículo 1056', 'B0BCPP43YN',
                                               'Limpiador de ducha y baño Frosch Citrus 500 ml', 1, 1.699,
                                               'agotado en OSMA']]))
_ws_res = _wb['Resumen']
_resu = {r[0]: r[1] for r in _ws_res.iter_rows(values_only=True)}
_l_dec = _wb['Análisis'].cell(row=1, column=_i['Decisión'] + 1).column_letter
_l_pais = _wb['Análisis'].cell(row=1, column=_cab.index('País') + 1).column_letter
eq('🔴 B2 · (AM) arriba del Resumen, las dos celdas amarillas con el pedido y el porte de la pasada, con su nombre, y lo '
   'que sale de ellas',
   ([(_ws_res[c].value, _ws_res[c].fill.fgColor.rgb) for c in ('A2', 'B2', 'A3', 'B3')], _ws_res['B4'].value,
    sorted((n, _wb.defined_names[n].attr_text) for n in (eo.NOMBRE_PEDIDO, eo.NOMBRE_PORTE))),
   ([('Pedido previsto (€)', '00000000'), (2500.0, '00FFFF00'), ('Porte del envío (€)', '00000000'),
     (168.19, '00FFFF00')], '=IF(N(PedidoPrevisto)>0,N(PorteEnvio)/PedidoPrevisto,0)',
    [('PedidoPrevisto', "'Resumen'!$B$2"), ('PorteEnvio', "'Resumen'!$B$3")]))
eq('🔴 B2 · (AM) COMPRAR y VALORAR de ES, por fórmula (contando «Decisión») y al lado los de la pasada; y la línea de '
   'puertas y cuadre y la de los packs de Amazon',
   ([[c.value for c in _ws_res[f]] for f in (6, 7, 8)], _resu.get('Puertas y cuadre'),
    _resu.get('Packs de Amazon detectados')),
   ([['Recuento en ES', 'con el pedido de arriba (fórmula)', 'en la pasada'],
     ['COMPRAR', "=COUNTIFS('Análisis'!$%s:$%s,\"ES\",'Análisis'!$%s:$%s,\"COMPRAR\")"
      % (_l_pais, _l_pais, _l_dec, _l_dec),
      cr['n_f'] - sum(1 for r in _sustituidas if r['puerta'] == 'f') + sum(1 for r in _mapa_def if r[4][0] == 'f')],
     ['VALORAR', "=COUNTIFS('Análisis'!$%s:$%s,\"ES\",'Análisis'!$%s:$%s,\"VALORAR\")"
      % (_l_pais, _l_pais, _l_dec, _l_dec),
      cr['n_e'] - sum(1 for r in _sustituidas if r['puerta'] == 'e') + sum(1 for r in _mapa_def if r[4][0] == 'e')]],
    'con el pedido de la pasada', '1 multiplicados · 0 dudosos a VALORAR'))
eq('🔴 B2 · el Resumen dice el porte (una vez), los países, los códigos y el EAN de sus fichas, las fichas que quedan '
   'fuera (calculadas con keepa_escaparate) y los packs',
   (_resu.get('Porte en el precio (el de la puerta común, una sola vez)'), _resu.get('Países del filtro de ventas'),
    _resu.get('Países con CSV'), _resu.get('Códigos enlazados en la foto (el EAN de nuestra ficha va en la lista)'),
    _resu.get('Fichas nuestras que quedan fuera: Keepa no conoce su EAN (no se rescatan)'),
    _resu.get('Packs nuestros valorados como unidades × precio')),
   ('168,19 € de la factura 3c3f364c (2026-08-21) ÷ pedido previsto 2500,00 € = 6,73 %', 'ES', 'ES',
    '3 códigos · 3 EAN de nuestras fichas (1 que no traía ya OSMA)', eo.texto_fuera_de_keepa(FK), 1))
eq('B2 · …y la línea de las fichas fuera nombra el Lenor', '18459 · B014DGG0OQ' in str(
    _resu.get('Fichas nuestras que quedan fuera: Keepa no conoce su EAN (no se rescatan)')), True)
eq('B2 · «Puertas previas» con los nombres de OSMA', sorted({r[4] for r in list(_wb['Puertas previas'].iter_rows(
    values_only=True))[1:]}), sorted(['Sin marca', 'EAN con forma rara o de relleno', 'Mismo EAN que otro artículo de OSMA']))

print('B3 · 🔴 el registro (repo PÚBLICO) no lleva ni un EAN, ASIN ni precio')
_prohibido = ['4002448039440', EAN_OSMA_COREGA, EAN_FICHA_COREGA, EAN_NORMAL, 'B001PASC5E', 'B0C9T9RZT3', 'B01GIE0QSM',
              '3.52', '3,52', '3.299', '6.39', 'Kukident', 'Corega', 'Protefix', 'Nivea',
              # (AG2) Ni el Lenor que queda fuera (sus ASIN y el EAN de la ficha).
              'B014DGG0OQ', 'B07HCJQ45L', '8001090747723', 'Lenor']
eq('B3 · ni en el barrido ni en el cruce', [x for x in _prohibido if x in log or x in log2], [])

print('B4 · solo se escribe en escaner2_* y en su carpeta del almacén')
_escritas = sorted({t for _p, op, t in bd['ops'] if op != 'select'})
eq('B4 · las tablas escritas', _escritas, ['escaner2_apartado', 'escaner2_cruce', 'escaner2_foto', 'escaner2_pasada',
                                          'escaner2_resultado_ean', 'escaner2_resultado_pais'])
eq('B4 · y las sembradas (disp_*, productos, codigos_proveedor, facturas, la puerta común) acaban como empezaron',
   [t for t in SEMBRADAS if bd['tablas'][t] != json.loads(json.dumps(inicial['tablas'][t]))], [])
eq('B4 · en el almacén, solo osma/<pasada>/', sorted({k.split('/')[0] + '/' + k.split('/')[1] for k in _alm}),
   ['osma/' + pas['id']])

print('B5 · [porte_doble] la puerta común con el porte dos veces: la pasada falla')
cod, log, bd, _r, _i0 = caso('porte_doble')
p = [x for x in bd['tablas']['escaner2_pasada'] if x.get('run_id') == 515151][0]
eq('B5 · ROJO, fallida, el motivo en la base y sin lista', (cod, p['estado'], 'puerta común' in (p['motivo_fallo'] or ''),
                                                             'escaner2' in bd['storage']), (1, 'fallida', True, False))
eq('B5 · …y el registro no dice el precio', [x for x in ('3.76', '3.52', '4002448039440') if x in log], [])

print('B6 · [memoria] y [vieja]: sin la puerta común en disp, o con otra foto, no hay pasada')
for _esc, _trozo in (('memoria', "no lee OSMA de la descarga"), ('vieja', 'no es la de su última descarga aplicada')):
    cod, log, bd, _r, _i0 = caso(_esc)
    p = [x for x in bd['tablas']['escaner2_pasada'] if x.get('run_id') == 515151][0]
    eq('B6 · [%s] ROJO y fallida con su motivo' % _esc, (cod, p['estado'], _trozo in (p['motivo_fallo'] or '')),
       (1, 'fallida', True))

print()
if fallos:
    print('FALLAN %d: %s' % (len(fallos), fallos))
    sys.exit(1)
print('TODO OK')
