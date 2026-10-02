# -*- coding: utf-8 -*-
"""Banco del ESCANEO PRO DE OSMA (encargo AG, 02-oct-2026): la parte pura y los DOS programas de verdad, con dobles.

PARTE A · LO PURO (escaner2_osma.py), en este proceso:
  A1  el porte con la regla de la puerta comun: la ultima factura con porte (NULL delante, como Postgres) ÷ pedido;
  A2  el precio con el porte, al centimo (Kukident 3,299 → 3,52), y 🔴 el porte UNA vez: con el porte sumado dos
      veces, `comprobar_porte` lo caza;
  A3  la foto: cada articulo por una puerta previa o en la foto, crudo = previas + foto; EAN de relleno fuera; el
      duplicado se queda con el codigo enlazado;
  A4  los enlaces (la familia del Lenor da dos ASIN; el chase y las fichas inactivas no) y las dos listas;
  A5  de que lista es un CSV, y las fichas de cada articulo: por codigo gana, la misma ficha no sale dos veces, el
      EAN nuevo con otra ficha se aparta, y una ficha enlazada no se cuelga de otro articulo;
  A6  el factor de nuestros packs, el de lib/packs de la v2 (Ultra Pro x1-x4, Protefix x1-x2-x5, Lenor x1-x2, la
      casilla; el «2-PACK» suelto y el «Maxi pack 128» no son packs);
  A7  la puerta de un pack: coste = unidades × precio, la misma ficha, y el detalle lo dice.

PARTE B · LOS PROGRAMAS (escaner2_osma_barrido.py y escaner2_osma_cruce.py), cada uno en su proceso, contra un
`supabase` en memoria (sin red, sin secretos, sin produccion):
  B1  [sin_llave] sin la llave de servicio no nace ningun cliente;
  B2  [bueno] barrido → 'esperando_csv' con su foto, sus listas (EAN y ASIN) y barrido.json; se suben los CSV de
      las dos listas de ES, IT, FR y DE (con la CABECERA REAL del Visualizador, 561 columnas, sacada de un export
      del 02-oct-2026); cruce → 'lista', cuadra, y el Excel: las hojas del PRO de HEO (sin «Chase_manual»), el
      FORMATO del Excel viejo de verdad con «Ficha compartida» y «No habrá más» al final, Kukident a 3,52 (el
      porte una vez), la Protefix pack 3 a 3 × 2,13, la Corega por su codigo y «no habrá más» donde toca;
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

print('A4 · los enlaces y las dos listas')
eq('A4 · los enlaces: el Lenor trae suelta y Pack 2 (ni el chase ni la inactiva); el código sin ficha se avisa',
   ({c: e['asins'] for c, e in ENLACES.items()}, AVISOS_ENL),
   ({'1056': ['B0BCPP43YN'], '1929': ['B0C9T9RZT3'], '4213': ['B001PASC5E'], '18459': ['B014DGG0OQ', 'B07HCJQ45L']},
    ['El código 9999 de OSMA apunta a una ficha que no está en productos']))
EANS, ASINS = eo.listas_para_keepa(FOTO, ENLACES)
eq('A4 · la lista de EAN: los de la foto (el EAN de OSMA, también el nuevo de la Corega)',
   sorted(EANS), sorted(['4002448039440', EAN_OSMA_COREGA, '8001090747723', '4009932002171', EAN_NORMAL]))
eq('A4 · la lista de ASIN: los de los códigos enlazados QUE ESTÁN EN LA FOTO (el 1056 no tiene existencias)',
   ASINS, ['B0C9T9RZT3', 'B001PASC5E', 'B014DGG0OQ', 'B07HCJQ45L'])

print('A5 · la lista de cada CSV y las fichas de cada artículo')
eq('A5 · un CSV con todos sus ASIN en la lista de ASIN es de esa lista; uno con uno de cien, de la de EAN',
   (eo.lista_de_csv(['B001PASC5E', 'B0C9T9RZT3'], ASINS),
    eo.lista_de_csv(['B001PASC5E'] + ['B0X%07d' % i for i in range(99)], ASINS), eo.lista_de_csv([], ASINS)),
   ('asin', 'ean', 'ean'))
_r = lambda asin, t='': {'asin': asin, 'titulo': t, 'buybox': 10.0, 'es_fba': True, 'nuevo': 10.0, 'compct': 15.0,  # noqa: E731
                         'fba': 3.0, 'rank': 1000.0, 'rank90': 1000.0}
_corega = _por['1929']
_datos_ean = {M.norm(EAN_OSMA_COREGA): [_r('B0NUEVA001'), _r('B0C9T9RZT3')]}
_por_asin = {'B0C9T9RZT3': _r('B0C9T9RZT3', 'por la lista de ASIN')}
c, camino, aparte = eo.candidatos_osma(_corega, _datos_ean, _por_asin, ENLACES['1929'], set(ASINS))
eq('A5 · la Corega: por su código (la ficha de la lista de ASIN, una vez) y el EAN nuevo con otra ficha, apartado',
   ([x['titulo'] for x in c], camino, [x['asin'] for x in aparte]), (['por la lista de ASIN'], 'codigo', ['B0NUEVA001']))
c, camino, aparte = eo.candidatos_osma(_corega, _datos_ean, {}, ENLACES['1929'], set(ASINS))
eq('A5 · si la lista de ASIN no trae su ficha, por su EAN de OSMA, como cualquier otra fila',
   ([x['asin'] for x in c], camino, aparte), (['B0NUEVA001', 'B0C9T9RZT3'], 'ean_sin_codigo', []))
c, camino, aparte = eo.candidatos_osma(_por['7001'], {M.norm(EAN_NORMAL): [_r('B0C9T9RZT3'), _r('B0NIVEA001')]}, {},
                                       None, set(ASINS))
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
    for asin, eans, caidas, precio, titulo in filas:
        fila = [''] * len(CABECERA)
        for h, v in ((C['asin'], asin), (COL_PAIS, pais), ('Título', titulo), (C['ean'], eans),
                     (C['rank'], '9000'), (C['rank90'], '11000'), (COL_CAIDAS, caidas), (C['buybox'], precio),
                     (C['es_fba'], 'yes'), (C['nuevo'], precio), (C['fba'], '3.10'), (C['compct'], '15.01 %'),
                     (C['nvar'], ''), (COL_PADRE, '')):
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
             'productos', 'v_escaner_fuente', 'inventario_fba')


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
                                {'proveedor': 'OSMA', 'umbral_caidas_30d': 6, 'paises_filtro': ['ES', 'IT', 'FR', 'DE'],
                                 'paises_calculo': ['ES', 'IT', 'FR', 'DE']}],
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

print('B2 · [bueno] barrido → listas → CSV de las dos listas → cruce → Excel')
cod, log, bd, ruta, inicial = caso('bueno')
eq('B2 · el barrido sale en VERDE', cod, 0)
pas = [p for p in bd['tablas']['escaner2_pasada'] if p.get('run_id') == 515151][0]
eq('B2 · la pasada: OSMA, modo todas, esperando_csv, crudo 11 = previas 6 + foto 5, dos listas',
   (pas['proveedor'], pas['modo'], pas['estado'], pas['n_crudo'], pas['n_foto'],
    sum(pas['p_' + p] for p in e2.PUERTAS_PREVIAS), pas['n_tandas'], pas['ruta_lista']),
   ('OSMA', 'todas', 'esperando_csv', 11, 5, 6, 2, 'osma/%s/eans.txt' % pas['id']))
_alm = bd['storage']['escaner2']
_txt = lambda k: base64.b64decode(_alm[k]).decode('utf-8')  # noqa: E731
eq('B2 · las dos listas en el almacén cerrado (5 EAN · 4 ASIN) y n_eans_lista = 9',
   (len(_txt('osma/%s/eans.txt' % pas['id']).split('\n')), _txt('osma/%s/asins.txt' % pas['id']).split('\n'),
    pas['n_eans_lista']), (5, ASINS, 9))
_sc = json.loads(_txt('osma/%s/barrido.json' % pas['id']))
eq('B2 · barrido.json: de qué descarga sale, el porte comprobado en 4 filas de la puerta común y los 3 enlaces de la foto',
   (_sc['disp_pasada'], _sc['porte']['pct'], _sc['porte_comprobado'], sorted(_sc['enlaces'])),
   ('p-osma', '0.067276', 4, ['18459', '1929', '4213']))
_fk = [f for f in bd['tablas']['escaner2_foto'] if f['producto_heo'] == '4213'][0]
eq('B2 · en la foto, Kukident a 3,52 (el porte una vez)', (_fk['precio_catalogo'], _fk['precio_unidad']), (3.299, 3.52))

# Fernando exporta las dos listas en los cuatro países y las suelta en el buzón.
_carpeta = 'osma/%s/csv/' % pas['id']
_filas_ean = [('B001PASC5E', '4002448039440', '30', '12.95', 'Kukident Active Plus 99 Tabletas'),
              ('B0NUEVA001', EAN_OSMA_COREGA, '40', '9.99', 'Corega Tabs caja nueva'),
              ('B01GIE0QSM', '4009932002171', '25', '19.50', 'Protefix Crema adhesiva Aloe Vera 47 g pack de 3'),
              ('B0NIVEA001', EAN_NORMAL, '12', '8.90', 'Nivea Creme 150 ml')]
_filas_asin = [('B001PASC5E', '4002448039440', '30', '12.95', 'Kukident Active Plus 99 Tabletas'),
               ('B0C9T9RZT3', EAN_FICHA_COREGA, '18', '11.50', 'Corega Tabs pastillas limpiadoras 108'),
               ('B014DGG0OQ', '5413149849693', '10', '6.50', 'Lenor toallitas secadora abril fresco 34'),
               ('B07HCJQ45L', '4055902127801', '8', '11.90', 'Lenor toallitas secadora abril fresco 34 pack 2')]
for _i, _pais in enumerate(('es', 'it', 'fr', 'de')):
    _alm[_carpeta + '20261002-09%02d00-KeepaExport-2026-10-02-VisualizadorDeProductos (%d).csv' % (_i, 2 * _i)] = \
        base64.b64encode(csv_real(_pais, _filas_ean)).decode()
    _alm[_carpeta + '20261002-09%02d30-KeepaExport-2026-10-02-VisualizadorDeProductos (%d).csv' % (_i, 2 * _i + 1)] = \
        base64.b64encode(csv_real(_pais, _filas_asin)).decode()
bd.pop('programa', None)
json.dump(bd, open(ruta, 'w', encoding='utf-8'), default=str)
cod2, log2 = correr(ruta, 'escaner2_osma_cruce.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'PASADA': pas['id'],
                                                      'GITHUB_RUN_ID': '525252'})
bd = json.load(open(ruta, encoding='utf-8'))
T = bd['tablas']
_alm = bd['storage']['escaner2']
eq('B2 · el cruce sale en VERDE', cod2, 0)
cr = [c for c in T['escaner2_cruce'] if c.get('run_id') == 525252][0]
eq('B2 · 🔴 el cruce: lista, cuadra, catálogo 11 = previas 6 + 5 puertas',
   (cr['estado'], cr['cuadra'], cr['n_crudo'], cr['n_previas'], cr['n_entradas'], sum(cr['n_' + x] for x in 'abcdef')),
   ('lista', True, 11, 6, 5, 5))
eq('B2 · los 8 CSV leídos: 4 de la lista de EAN y 4 de la de ASIN, uno por país',
   sorted((f['pais'], f['lista']) for f in cr['ficheros']),
   sorted((p, li) for p in ('ES', 'IT', 'FR', 'DE') for li in ('ean', 'asin')))
_res = {f['producto_heo']: r for r in T['escaner2_resultado_ean'] for f in T['escaner2_foto'] if f['id'] == r['foto_id']}
eq('B2 · la Corega por su código: nuestra ficha, no la de la caja nueva',
   (_res['1929']['asin'], 'Por el código 1929 de OSMA' in _res['1929']['detalle'], 'B0NUEVA001' in _res['1929']['detalle']),
   ('B0C9T9RZT3', True, True))
eq('B2 · el Kukident por su código (la misma ficha por los dos caminos: una)', _res['4213']['asin'], 'B001PASC5E')
eq('B2 · el Lenor, con una de nuestras dos fichas (las trae la lista de ASIN: Keepa no conoce su EAN)',
   _res['18459']['asin'] in ('B014DGG0OQ', 'B07HCJQ45L'), True)
eq('B2 · la Protefix (por EAN) es nuestro pack de 3', (_res['3000']['asin'], 'pack de 3' in _res['3000']['detalle']),
   ('B01GIE0QSM', True))
_rp = [p for p in T['escaner2_resultado_pais'] if p['resultado_ean_id'] == _res['3000']['id'] and p['pais'] == 'ES'][0]
eq('B2 · …y su cuenta de ES va con el coste del pack (3 × 2,13 = 6,39)', _rp['pa'], 6.39)
_xl = [k for k in _alm if k.startswith('osma/%s/%s/Escaner2_OSMA_' % (pas['id'], cr['id']))]
eq('B2 · el Excel, en su carpeta y con su nombre (el que guarda el cruce)', (len(_xl), cr['ruta_excel'] == _xl[0]), (1, True))
from openpyxl import load_workbook  # noqa: E402
_bytes = base64.b64decode(_alm[_xl[0]])
_wb = load_workbook(io.BytesIO(_bytes))
HOJAS_VIEJO = ['Análisis', 'Descartados', 'Ambiguos', 'Sin_rank', 'Precio por lote']
HOJAS_E2 = ['Resumen', 'Comparación', 'Varias fichas', 'Puertas', 'Puertas previas']
eq('B2 · las hojas del PRO de HEO, en su orden (sin «Chase_manual»: es de los Funko chase de HEO)',
   _wb.sheetnames, HOJAS_VIEJO + HOJAS_E2)
_cab = [c.value for c in _wb['Análisis'][1]]
eq('B2 · «Análisis»: las columnas del PRO de HEO y, AL FINAL, «No habrá más» (el único añadido)',
   _cab, e2.columnas_analisis() + [e2.COLUMNA_FICHA_COMPARTIDA, eo.COLUMNA_NO_HABRA_MAS])
import escaner2_desvios as DV  # noqa: E402
import escaner2_huella_excel as HU  # noqa: E402
_REF = HU.sin_columnas(json.load(open(os.path.join(AQUI, 'huella_excel_viejo_heo.json'), encoding='utf-8')),
                       DV.ANALISIS_QUITADAS, DV.ANALISIS_RENOMBRADAS)
_REF = HU.con_columna_al_final(_REF, e2.COLUMNA_FICHA_COMPARTIDA, e2.ANCHO_FICHA_COMPARTIDA)
_REF = HU.con_columna_al_final(_REF, eo.COLUMNA_NO_HABRA_MAS, eo.ANCHO_NO_HABRA_MAS)
_REF['hojas'] = [h for h in _REF['hojas'] if h['hoja'] != 'Chase_manual']
eq('B2 · 🔴 el FORMATO de las hojas del viejo es el del Excel viejo de verdad (con «Ventas», «Ficha compartida» y «No habrá más»)',
   HU.diferencias(_REF, HU.huella(_bytes), solo_hojas=HOJAS_VIEJO, vacias=('Sin_rank',)), [])
_filas = list(_wb['Análisis'].iter_rows(min_row=2, values_only=True))
_i = {n: _cab.index(n) for n in ('EAN', 'ASIN', 'PA (€)', 'Nombre', eo.COLUMNA_NO_HABRA_MAS)}
eq('B2 · 🔴 el porte UNA vez: el Kukident lleva 3,52 en «PA (€)», el mismo de la puerta común',
   sorted({r[_i['PA (€)']] for r in _filas if r[_i['EAN']] == '4002448039440'}), [3.52])
eq('B2 · la Protefix pack 3: «PA (€)» 6,39 y el nombre lo dice',
   sorted({(r[_i['PA (€)']], r[_i['Nombre']]) for r in _filas if r[_i['ASIN']] == 'B01GIE0QSM'}),
   [(6.39, 'Protefix Haftcreme 47g Aloe Vera · pack de 3 (3 × 2,13 €)')])
eq('B2 · «no habrá más» en las cuatro filas del descatalogado (Nivea) y en ninguna otra',
   sorted((r[_i['EAN']], r[_i[eo.COLUMNA_NO_HABRA_MAS]]) for r in _filas if r[_i[eo.COLUMNA_NO_HABRA_MAS]]),
   [(EAN_NORMAL, 'no habrá más')] * 4)
_resu = {r[0]: r[1] for r in _wb['Resumen'].iter_rows(values_only=True)}
eq('B2 · el Resumen dice el porte (una vez), los códigos y ASIN de la lista y los packs',
   (_resu.get('Porte en el precio (el de la puerta común, una sola vez)'),
    _resu.get('Códigos enlazados en la foto (lista de ASIN)'), _resu.get('Packs nuestros valorados como unidades × precio')),
   ('168,19 € de la factura 3c3f364c (2026-08-21) ÷ pedido previsto 2500,00 € = 6,73 %', '3 códigos · 4 ASIN',
    1 + (_res['18459']['asin'] == 'B07HCJQ45L')))
eq('B2 · «Puertas previas» con los nombres de OSMA', sorted({r[4] for r in list(_wb['Puertas previas'].iter_rows(
    values_only=True))[1:]}), sorted(['Sin marca', 'EAN con forma rara o de relleno', 'Mismo EAN que otro artículo de OSMA']))

print('B3 · 🔴 el registro (repo PÚBLICO) no lleva ni un EAN, ASIN ni precio')
_prohibido = ['4002448039440', EAN_OSMA_COREGA, EAN_FICHA_COREGA, EAN_NORMAL, 'B001PASC5E', 'B0C9T9RZT3', 'B01GIE0QSM',
              '3.52', '3,52', '3.299', '6.39', 'Kukident', 'Corega', 'Protefix', 'Nivea']
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
