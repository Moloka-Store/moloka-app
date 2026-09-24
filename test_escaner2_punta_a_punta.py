# -*- coding: utf-8 -*-
"""Banco de punta a punta del escaner 2 de HEO: los DOS programas de verdad, con dobles.

`escaner2_heo_barrido.py` y `escaner2_heo_cruce.py` son scripts (se corren con `runpy` y
hacen `sys.exit`), asi que cada caso va en su PROCESO. `supabase` (base y Storage) y la API de
HEO (`descargar_heo`) se sustituyen por dobles EN MEMORIA que guardan su estado en un fichero
entre proceso y proceso: el barrido deja la foto y el cruce la lee. Sin red, sin secretos y
sin tocar produccion. El escaner viejo NO se toca: sus piezas se leen de su fichero real.

CASOS:
  1. [sin_llave]  sin SUPABASE_SERVICE_KEY → ROJO, la linea exacta y NINGUN cliente creado.
  2. [bueno]      barrido → la pasada queda 'esperando_csv' con su foto, sus apartados y la
                  lista de EAN en el bucket cerrado; subo un CSV de ES y otro de DE; cruce →
                  'lista', CUADRA contra la base, compara con el viejo y deja el Excel.
  3. [frenado]    la base ACEPTA el insert de las puertas y se come las de la puerta b (lo que
                  haria una politica que frena: 200 y cero filas) → el cruce CUENTA en la base,
                  ve que no cuadra y queda 'fallida' en ROJO. Es el cuadre del encargo en vivo.
"""
import base64
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ═══════════════════════════════════════════════════════════════════════════════
# EL DOBLE DE SUPABASE: tablas en memoria y un Storage que pagina como storage3 2.31.0
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
        filas = self.bd['tablas'].setdefault(self.tabla, [])
        if self.op == 'insert':
            for f in self.payload:
                if self.bd.get('frenar') and self.tabla == self.bd['frenar'][0] and f.get('puerta') == self.bd['frenar'][1]:
                    continue       # 200 y cero filas: lo que hace una politica que frena
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
        # Como storage3 2.31.0: DEFAULT_SEARCH_OPTIONS = limit 100, offset 0, por nombre asc.
        op = dict({'limit': 100, 'offset': 0}, **(opciones or {}))
        pref = (carpeta or '').rstrip('/') + '/'
        nombres = sorted(r[len(pref):] for r in self._objs() if r.startswith(pref) and '/' not in r[len(pref):])
        trozo = nombres[op['offset']:op['offset'] + op['limit']]
        return [{'name': n, 'created_at': '2026-09-24T12:%02d:00Z' % i, 'metadata': {'size': 1}}
                for i, n in enumerate(trozo)]


class _Cliente:
    def __init__(self, bd):
        self.bd = bd
        self.storage = types.SimpleNamespace(from_=lambda cubo: _Cubo(bd, cubo))

    def table(self, nombre):
        return _Consulta(self.bd, nombre)


# ═══════════════════════════════════════════════════════════════════════════════
# LA ESCENA: el catalogo de HEO, los dos CSV y el escaner viejo
# ═══════════════════════════════════════════════════════════════════════════════
def _escena():
    sys.path.insert(0, AQUI)
    import escaner2_motor as e2
    import moloka_escaner_pro as pro
    M = e2.cargar_motor(os.path.join(AQUI, e2.RUTA_MOTOR))
    return e2, pro, M


def _ean(M, n):
    cuerpo = '84355%07d' % n
    return cuerpo + M._chk13(cuerpo)


def filas_heo(M):
    def h(n, nombre, precio, marca='FUNKO'):
        return {'productNumber': 'HEO%04d' % n, 'ean': _ean(M, n), 'nombre': nombre, 'marca': marca,
                'categoria': 'Figuras', 'precio': precio, 'precio_base': precio, 'en_oferta': '',
                'campana': '', 'estado': 'disponible', 'disponibilidad': 'GREEN', 'imagen': '',
                'fin_de_vida': '', 'preorder': ''}
    return [h(1, 'Funko Pop Alfa', 8.00), h(2, 'Funko Pop Beta', 10.00), h(3, 'Funko Pop Gamma', 8.00),
            h(4, 'Funko Pop Delta', 8.00), h(5, 'Funko Pop Epsilon', 8.00),
            h(6, 'Funko Pop Zeta Chase', 30.00), h(7, 'Hasbro fuera', 5.00, marca='Hasbro')]


def csv_visualizador(e2, pro, M, pais, filas):
    col_pais, col_caidas = e2.columnas_keepa(os.path.join(AQUI, e2.RUTA_ESCAPARATE))
    C = pro.CSV_COLS
    cab = ['ASIN', col_pais, 'Título', C['ean'], C['rank'], C['rank90'], col_caidas, C['buybox'], C['es_fba'],
           C['nuevo'], C['fba'], C['compct'], C['nof'], C['vendidos'], C['vendidos2'], C['nvar']]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cab)
    for asin, n, caidas, bb in filas:
        w.writerow([asin, pais, 'Funko %d' % n, _ean(M, n), '12000', '15000', caidas, bb, 'yes', bb,
                    '3.50', '15.01 %', '10', '50', '', '0'])
    return ('﻿' + buf.getvalue()).encode('utf-8')


def excel_viejo(e2, M, filas):
    from openpyxl import Workbook
    cols = e2.sacar_piezas(os.path.join(AQUI, e2.RUTA_MOTOR), (), ('COLS',))['COLS']
    wb = Workbook()
    ws = wb.active
    ws.title = 'Análisis'
    ws.append(cols)
    for n, pais, dec in filas:
        fila = [None] * len(cols)
        fila[cols.index('EAN')], fila[cols.index('País')], fila[cols.index('Decisión')] = _ean(M, n), pais, dec
        ws.append(fila)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# EL HIJO: monta los dobles y corre el programa de verdad
# ═══════════════════════════════════════════════════════════════════════════════
def hijo(ruta_estado, programa):
    with open(ruta_estado, encoding='utf-8') as fh:
        bd = json.load(fh)
    clientes = []

    def crear(url, llave):
        clientes.append(llave)
        return _Cliente(bd)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = crear
    e2, _pro, M = _escena()

    def descargar_catalogo_heo(max_paginas=None, con_chase=False):
        # Las dos lineas del log de la funcion de verdad (descargar_heo.py) de las que el barrido
        # saca el catalogo CRUDO y los tirados sin GTIN: 7 con EAN + 1 Funko chase + 3 sin GTIN.
        print('>>> Cruzando: %d productos | 0 precios | 0 disponibilidades' % int(os.environ.get('E2_CRUDO', '11')))
        print('>>> Catalogo cruzado: 7 filas con EAN (descartadas 3 sin GTIN)')
        chase = [{'producto_heo': 'HEO9001', 'nombre': 'Funko Pop Omega w/CH', 'ean_caja': '9990000000011',
                  'marca': 'FUNKO', 'precio_caja': 70.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''}]
        return (filas_heo(M), chase) if con_chase else filas_heo(M)

    sys.modules['descargar_heo'] = types.ModuleType('descargar_heo')
    sys.modules['descargar_heo'].descargar_catalogo_heo = descargar_catalogo_heo
    import runpy
    sys.argv = [programa] + os.environ.get('E2_ARGS', '').split()
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


def correr(ruta_estado, programa, env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ('SUPABASE_SERVICE_KEY', 'HEO_USER', 'HEO_PASS', 'PASADA')}
    env.update(env_extra, PYTHONIOENCODING='utf-8', SUPABASE_URL='https://doble.invalid')
    p = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--hijo', ruta_estado, programa],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=AQUI)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def estado_inicial(e2, M, frenar=None):
    viejo = excel_viejo(e2, M, [(1, 'ES', 'COMPRAR'), (1, 'DE', 'COMPRAR'), (5, 'ES', 'COMPRAR'), (3, 'IT', 'VALORAR')])
    return {
        'frenar': frenar,
        'tablas': {
            'reglas_director': [{'proveedor': 'HEO', 'activo': True, 'marcas': ['Funko', 'OFERTAS'], 'rank_maximo': 30000}],
            'escaner2_parametros': [{'proveedor': 'HEO', 'umbral_caidas_30d': 8, 'paises': ['ES', 'DE']}],
            'productos': [{'id': 'p1', 'ean': _ean(M, 1), 'asin': 'B0ALFA0001', 'iva_pct': 0.10, 'activo': True,
                           'stock_moloka': 0, 'stock_fba': 3}],
            'escaner_resultados': [{'id': 1, 'proveedor': 'HEO', 'modo': 'todo', 'rank_maximo': 30000,
                                    'fecha': '2026-09-24T00:16:10+00:00',
                                    'fichero': 'resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx'}],
        },
        'storage': {'informes': {'resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx': base64.b64encode(viejo).decode()}},
    }


def caso(nombre, frenar=None, crudo=None):
    e2, pro, M = _escena()
    tmp = tempfile.mkdtemp(prefix='e2pp_')
    ruta = os.path.join(tmp, 'estado.json')
    with open(ruta, 'w', encoding='utf-8') as fh:
        json.dump(estado_inicial(e2, M, frenar), fh)
    llave = {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'HEO_USER': 'u', 'HEO_PASS': 'p', 'GITHUB_RUN_ID': '424242'}
    if crudo is not None:
        llave['E2_CRUDO'] = str(crudo)
    cod, log = correr(ruta, 'escaner2_heo_barrido.py', llave)
    bd = json.load(open(ruta, encoding='utf-8'))
    pasada = bd['tablas']['escaner2_pasada'][0]
    # Fernando exporta del Visualizador y sube los dos CSV (el nombre NO dice el pais).
    carpeta = 'heo/%s/csv/' % pasada['id']
    bd['storage'].setdefault('escaner2', {})
    for nombre_fichero, pais, filas in (
            ('KeepaExport-2026-09-24-VisualizadorDeProductos.csv', 'es',
             [('B0ALFA0001', 1, '30', '22.00'), ('B0BETA0001', 2, '12', '22.00'), ('B0GAMA0001', 3, '4', '22.00'),
              ('B0DELT0001', 4, '20', '22.00'), ('B0DELT0002', 4, '20', '21.00')]),
            ('KeepaExport-2026-09-24-VisualizadorDeProductos (1).csv', 'de',
             [('B0ALFA0001', 1, '12', '21.00'), ('B0GAMA0001', 3, '2', '21.00')])):
        bd['storage']['escaner2'][carpeta + '20260924-1200-' + nombre_fichero] = base64.b64encode(
            csv_visualizador(e2, pro, M, pais, filas)).decode()
    if nombre == 'bueno':
        # 🔑 Un ES MAS VIEJO con otro precio y 0 caidas para el ALFA: el mas reciente tiene que
        #    mandar (antes mandaba el primero por nombre, o sea el viejo).
        bd['storage']['escaner2'][carpeta + '20260924-1100-KeepaExport-antiguo.csv'] = base64.b64encode(
            csv_visualizador(e2, pro, M, 'es', [('B0ALFA0001', 1, '0', '99.00')])).decode()
        # 🔑 Y un fichero que no se puede leer: se dice y se sigue (no bloquea la pasada para siempre).
        bd['storage']['escaner2'][carpeta + '20260924-1300-roto.csv'] = base64.b64encode(b'esto no es un csv').decode()
    json.dump(bd, open(ruta, 'w', encoding='utf-8'), default=str)
    cod2, log2 = correr(ruta, 'escaner2_heo_cruce.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'PASADA': pasada['id'],
                                                        'GITHUB_RUN_ID': '434343'})
    return (cod, log, cod2, log2, json.load(open(ruta, encoding='utf-8')), pasada['id'], M, e2)


if __name__ == '__main__' and len(sys.argv) >= 4 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2], sys.argv[3])

# ═══════════════════════════════════════════════════════════════════════════════
print('1 · [sin_llave] sin la llave de servicio no se corre')
_e2, _pro, _M = _escena()
_tmp = tempfile.mkdtemp(prefix='e2pp_')
_ruta = os.path.join(_tmp, 'estado.json')
json.dump(estado_inicial(_e2, _M), open(_ruta, 'w', encoding='utf-8'))
for _prog in ('escaner2_heo_barrido.py', 'escaner2_heo_cruce.py'):
    _cod, _log = correr(_ruta, _prog, {'HEO_USER': 'u', 'HEO_PASS': 'p', 'PASADA': '00000000-0000-0000-0000-000000000000'})
    eq('1 · %s sin llave → ROJO' % _prog, _cod, 1)
    eq('1 · …con la linea exacta', 'ESCANER2_NO_EJECUTADO: sin llave de servicio' in _log, True)
    eq('1 · …y sin crear NINGUN cliente', 'CLIENTES_CREADOS=0' in _log, True)

print('\n2 · [bueno] barrido → CSV de ES y DE → cruce')
cod, log, cod2, log2, bd, pasada, M, e2 = caso('bueno')
T = bd['tablas']
p = T['escaner2_pasada'][0]
eq('2 · el barrido sale en VERDE', cod, 0)
eq('2 · la pasada queda esperando los CSV, con el run apuntado', (p['estado'], p['run_id']), ('esperando_csv', 424242))
eq('2 · foto: los 5 Funko (el chase suelto y Hasbro, fuera)', (p['n_foto'], len(T['escaner2_foto'])), (5, 5))
eq('2 · apartados: el Funko chase de la API y el chase suelto', sorted(a['motivo'] for a in T['escaner2_apartado']),
   ['chase_funko', 'chase_suelto'])
eq('2 · los descartados sin GTIN se rescatan del log de descargar_heo', p['p_sin_gtin'], 3)
eq('2 · 🔴 el catálogo CRUDO sale del log, y cuadra: crudo = previas + foto',
   (p['n_crudo'], sum(p['p_' + x] for x in e2.PUERTAS_PREVIAS) + p['n_foto']), (11, 11))
_lista = base64.b64decode(bd['storage']['escaner2']['heo/%s/eans.txt' % pasada]).decode().split('\n')
eq('2 · la lista para el Visualizador: un EAN por linea, en el bucket escaner2', (len(_lista), p['n_eans_lista'], p['n_tandas']),
   (5, 5, 1))
eq('2 · ni una escritura en tablas del escaner viejo',
   sorted(t for t in T if not t.startswith('escaner2_')), ['escaner_resultados', 'productos', 'reglas_director'])
eq('2 · …y las tablas viejas siguen como estaban', (len(T['escaner_resultados']), len(T['productos']), len(T['reglas_director'])),
   (1, 1, 1))
c = T['escaner2_cruce'][0]
eq('2 · el cruce sale en VERDE', cod2, 0)
eq('2 · …y queda LISTA, cuadrado', (c['estado'], c['cuadra'], c['motivo_fallo']), ('lista', True, None))
eq('2 · el pais de cada CSV sale del dato', sorted((f['pais'] or '', f['usado']) for f in c['ficheros']),
   [('', False), ('DE', True), ('ES', True), ('ES', True)])
eq('2 · 🔴 el CSV roto se dice (en ficheros) y NO tumba el cruce',
   [(f['nombre'].endswith('roto.csv'), bool(f['error'])) for f in c['ficheros'] if f['error']], [(True, True)])
eq('2 · puertas: entradas 5 = a1 b1 c1 d0 e1 f1', (c['n_entradas'], c['n_a'], c['n_b'], c['n_c'], c['n_d'], c['n_e'], c['n_f']),
   (5, 1, 1, 1, 0, 1, 1))
eq('2 · …una fila por EAN, ni mas ni menos', len(T['escaner2_resultado_ean']), 5)
_f1 = [r for r in T['escaner2_resultado_ean'] if r['puerta'] == 'f']
eq('2 · COMPRAR con su mejor pais (ES: IVA de ficha 10 %)', sorted((r['asin'], r['mejor_pais']) for r in _f1),
   [('B0ALFA0001', 'ES')])
_es1 = [r for r in T['escaner2_resultado_pais'] if r['asin'] == 'B0ALFA0001' and r['pais'] == 'ES'][0]
eq('2 · 🔴 manda el CSV MAS RECIENTE de ES: precio 22 y 30 caídas, no 99 y 0 del antiguo',
   (_es1['precio_venta'], _es1['caidas_30d']), (22.0, 30))
eq('2 · el IVA de ES sale de la ficha y la fila lo dice', (_es1['iva'], _es1['iva_origen']), (0.1, 'ficha'))
eq('2 · la cuenta es la del viejo (margen guardado, decision COMPRAR)', (_es1['decision'], round(_es1['margen'], 4)),
   ('COMPRAR', round(M.calc_rentabilidad(22.0, 8.0, 15.01, 3.5, 0.10, almacen=M.ALMACEN, com_digitales=M.COM_DIGITALES,
                                          isd=M.ISD_PAIS['ES'])['margen'], 4)))
_cmp = {r['ean']: r for r in T['escaner2_comparacion']}
eq('2 · comparacion: el EAN 1, COMPRAR en los dos', _cmp[_ean(M, 1)]['categoria'], 'ambos')
eq('2 · comparacion: el EAN 3 (IT en el viejo, pocas caidas en el nuevo) → diferencia de criterio',
   (_cmp[_ean(M, 3)]['categoria'], _cmp[_ean(M, 3)]['diferencia_criterio']), ('solo_viejo', True))
eq('2 · …y la fecha del viejo es la de su Excel (UTC)', str(_cmp[_ean(M, 1)]['fecha_viejo'])[:16], '2026-09-23T20:06')
_xl = [k for k in bd['storage']['escaner2'] if k.startswith('heo/%s/%s/Escaner2_HEO_' % (pasada, c['id']))]
eq('2 · el Excel del cruce queda en el bucket escaner2 y apuntado en el cruce', (len(_xl), c['ruta_excel'] == (_xl or [None])[0]),
   (1, True))
from openpyxl import load_workbook  # noqa: E402
_wb = load_workbook(io.BytesIO(base64.b64decode(bd['storage']['escaner2'][_xl[0]])), read_only=True)
eq('2 · …con sus seis hojas (la última, las listas de las puertas previas)', _wb.sheetnames, ['Resumen', 'COMPRAR y VALORAR', 'Comparación', 'Varias fichas', 'Puertas', 'Puertas previas'])
eq('2 · el log deja el CUADRE, cuadre o no', 'CUADRE [HEO]: crudo=11 | previas=6' in log2
   and '| entradas=5 | suma de puertas=5' in log2, True)
eq('2 · 🔴 el cruce guarda el crudo y las previas: crudo 11 = previas 6 + puertas 5',
   (c['n_crudo'], c['n_previas'], sum(c['n_' + x] for x in 'abcdef')), (11, 6, 5))

print('\n3 · [frenado] la base se come las filas de una puerta → el cuadre lo caza')
cod, log, cod2, log2, bd, pasada, M, e2 = caso('frenado', frenar=('escaner2_resultado_ean', 'b'))
c = bd['tablas']['escaner2_cruce'][0]
eq('3 · 🔴 el cruce sale en ROJO', cod2, 1)
eq('3 · 🔴 …y queda FALLIDA, sin cuadrar, con el motivo', (c['estado'], c['cuadra'], 'NO CUADRA' in (c['motivo_fallo'] or '')),
   ('fallida', False, True))
eq('3 · 🔴 …contando en la BASE: 5 entradas y 4 en las puertas', (c['n_entradas'], sum(c['n_' + x] for x in 'abcdef')), (5, 4))
eq('3 · el log lo dice', 'NO CUADRA' in log2, True)

print('\n4 · [crudo_de_mas] HEO dice un producto más de los que salen → la pasada FALLA')
cod, log, cod2, log2, bd, pasada, M, e2 = caso('crudo_de_mas', crudo=12)
p = bd['tablas']['escaner2_pasada'][0]
eq('4 · 🔴 el barrido sale en ROJO', cod, 1)
eq('4 · 🔴 …y la pasada queda FALLIDA con el motivo', (p['estado'], 'NO CUADRA antes de la foto' in (p['motivo_fallo'] or '')),
   ('fallida', True))
eq('4 · 🔴 …sin lista para Keepa: no se puede cruzar', (p.get('ruta_lista'), cod2), (None, 1))

print('\n5 · [rescate] el run muere a medias → SU fila queda fallida, las demás no se tocan')
_ruta = os.path.join(_tmp, 'rescate.json')
json.dump({'tablas': {
    'escaner2_pasada': [{'id': 'p-colgada', 'run_id': 777, 'estado': 'descargando'},
                        {'id': 'p-otro-run', 'run_id': 888, 'estado': 'descargando'},
                        {'id': 'p-cerrada', 'run_id': 777, 'estado': 'esperando_csv'}],
    'escaner2_cruce': [{'id': 'c-colgado', 'run_id': 777, 'estado': 'cruzando'},
                       {'id': 'c-lista', 'run_id': 777, 'estado': 'lista'}]}, 'storage': {}},
          open(_ruta, 'w', encoding='utf-8'))
for _que in ('pasada', 'cruce'):
    _cod, _log = correr(_ruta, 'escaner2_rescate.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'GITHUB_RUN_ID': '777',
                                                       'E2_ARGS': _que})
    eq('5 · el rescate de %s sale en verde' % _que, _cod, 0)
_bd = json.load(open(_ruta, encoding='utf-8'))['tablas']
eq('5 · 🔴 la pasada colgada de ESTE run queda fallida, con el motivo',
   [(f['id'], f['estado'], 'run 777' in (f.get('motivo_fallo') or '')) for f in _bd['escaner2_pasada']],
   [('p-colgada', 'fallida', True), ('p-otro-run', 'descargando', False), ('p-cerrada', 'esperando_csv', False)])
eq('5 · 🔴 el cruce colgado también; el que ya estaba lista, no',
   [(f['id'], f['estado']) for f in _bd['escaner2_cruce']], [('c-colgado', 'fallida'), ('c-lista', 'lista')])
_cod, _log = correr(_ruta, 'escaner2_rescate.py', {'GITHUB_RUN_ID': '777', 'E2_ARGS': 'pasada'})
eq('5 · sin llave, el rescate tampoco corre', (_cod, 'CLIENTES_CREADOS=0' in _log), (1, True))

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: barrido y cruce de punta a punta; sin llave no se corre, y un cruce que no cuadra sale en ROJO.')
