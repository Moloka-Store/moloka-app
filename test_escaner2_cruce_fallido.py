# -*- coding: utf-8 -*-
"""Banco del CRUCE FALLIDO del escaner 2 (28-sep-2026): un cruce que falla no deja filas.

`escaner2_heo_cruce.py` guarda escaner2_resultado_ean y escaner2_resultado_pais en tandas de
LOTE (500), y cada tanda es su propia transaccion. Si falla la segunda, la primera ya esta en
la base. El arreglo: antes de marcar el cruce 'fallida', se borran SUS filas (cruce_id) en las
dos tablas; si el borrado falla, el motivo lo dice.

Se carga el programa DE VERDAD (su fichero, sin ejecutar su main) sobre un supabase de mentira,
y se corre su `main()`. Solo se sustituye `cruzar` por uno que escribe con el `_en_lotes` real
1.200 filas de EAN (tandas 500 + 500 + 200) y sus filas de pais: lo que se prueba es lo que
pasa cuando una tanda falla, no el calculo de las puertas (eso lo prueba
test_escaner2_punta_a_punta.py). Sin red, sin secretos y sin tocar ninguna base.

CASOS:
  1. [segunda tanda] la base acepta la 1.a tanda de EAN y rechaza la 2.a → ROJO; el cruce queda
     'fallida' con el motivo de siempre (el error de la base); 0 filas suyas en las dos tablas;
     el otro cruce, 'lista', intacto; el borrado va ANTES del update y filtra solo por su id.
  2. [borrado frenado] lo mismo, pero la base no deja borrar (hoy, sin el permiso de DELETE) →
     'fallida' igual, y el motivo dice que NO se han podido borrar y cuantas quedan.
  3. [no cuadra] cruzar escribe todo pero devuelve un cierre 'fallida' (el cuadre no sale) →
     tambien se borran sus filas, y el cierre se guarda con su motivo.
  4. [bueno] cruce 'lista' → ni un DELETE.
  5. [muerde] con el borrado quitado (como estaba antes) quedan las 500 filas de la 1.a tanda:
     la escena de los casos 1-3 de verdad deja algo que borrar.
"""
import os
import sys
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
PROGRAMA = os.path.join(AQUI, 'escaner2_heo_cruce.py')
PASADA = '00000000-0000-4000-8000-0000000000aa'
LISTA = '00000000-0000-4000-8000-0000000000bb'
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


class ErrorBase(Exception):
    """Lo que lanza postgrest-py cuando la base contesta con error (APIError)."""


class _Resp:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Consulta:
    def __init__(self, bd, tabla):
        self.bd, self.tabla = bd, tabla
        self.op, self.filtros, self.payload, self.cuenta = 'select', [], None, False

    def select(self, _cols='*', count=None):
        self.op, self.cuenta = 'select', count == 'exact'
        return self

    def insert(self, filas):
        self.op, self.payload = 'insert', filas if isinstance(filas, list) else [filas]
        return self

    def update(self, cambios):
        self.op, self.payload = 'update', cambios
        return self

    def delete(self, count=None, returning=None):
        self.op, self.cuenta = 'delete', count == 'exact'
        return self

    def eq(self, k, v):
        self.filtros.append((k, v))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        bd = self.bd
        bd['ops'].append((self.op, self.tabla, tuple(self.filtros)))
        filas = bd['tablas'].setdefault(self.tabla, [])
        sel = [f for f in filas if all(str(f.get(k)) == str(v) for k, v in self.filtros)]
        if self.op == 'insert':
            n = bd['llamadas'][self.tabla] = bd['llamadas'].get(self.tabla, 0) + 1
            if (self.tabla, n) == bd.get('falla_insert'):
                raise ErrorBase("{'code': '23514', 'message': 'new row for relation \"%s\" violates check "
                                "constraint \"de_mentira\"'}" % self.tabla)
            filas.extend(dict(f) for f in self.payload)
            return _Resp(self.payload)
        if self.op == 'delete':
            if bd.get('frenar_delete'):
                raise ErrorBase("{'code': '42501', 'message': 'permission denied for table %s'}" % self.tabla)
            # La guarda de la base (disparador de la v2): las filas de un cruce 'lista' no se borran.
            listas = {c['id'] for c in bd['tablas']['escaner2_cruce'] if c['estado'] == 'lista'}
            if any(f['cruce_id'] in listas for f in sel):
                raise ErrorBase("{'code': 'P0001', 'message': 'no se borran filas de un cruce lista'}")
            bd['tablas'][self.tabla] = [f for f in filas if f not in sel]
            return _Resp([], len(sel) if self.cuenta else None)
        if self.op == 'update':
            for f in sel:
                f.update(self.payload)
            return _Resp(sel)
        return _Resp(sel, len(sel) if self.cuenta else None)


class _Cliente:
    def __init__(self, bd):
        self.bd = bd

    def table(self, nombre):
        return _Consulta(self.bd, nombre)


def base_inicial():
    # El otro cruce, ya 'lista', con sus filas: no se toca.
    return {
        'ops': [], 'llamadas': {},
        'tablas': {
            'escaner2_pasada': [{'id': PASADA, 'estado': 'esperando_csv'}],
            'escaner2_parametros': [{'proveedor': 'HEO', 'umbral_caidas_30d': 8, 'paises_filtro': ['ES', 'DE'],
                                     'paises_calculo': ['ES', 'IT', 'FR', 'DE']}],
            'escaner2_cruce': [{'id': LISTA, 'pasada_id': PASADA, 'estado': 'lista'}],
            'escaner2_resultado_ean': [{'id': 'L-e%d' % i, 'cruce_id': LISTA} for i in range(7)],
            'escaner2_resultado_pais': [{'id': 'L-p%d' % i, 'cruce_id': LISTA, 'resultado_ean_id': 'L-e%d' % i}
                                        for i in range(7)],
        }}


def cargar(bd):
    """El programa de verdad, sin correr su main, con el supabase de mentira. Con `exec` sobre un
    diccionario nuestro y no con runpy.run_path, que devuelve una COPIA de los globales: cambiar
    `cruzar` en la copia no lo cambia para `main`."""
    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda _u, _k: _Cliente(bd)
    os.environ.update(SUPABASE_SERVICE_KEY='svc-de-mentira', SUPABASE_URL='https://doble.invalid',
                      PASADA=PASADA, GITHUB_RUN_ID='515151')
    if AQUI not in sys.path:
        sys.path.insert(0, AQUI)
    g = {'__name__': 'cruce_de_prueba', '__file__': PROGRAMA}
    with open(PROGRAMA, encoding='utf-8') as fh:
        exec(compile(fh.read(), PROGRAMA, 'exec'), g)
    return g


def cruzar_de_mentira(g, bd, cierre_estado='lista'):
    """Escribe con el `_en_lotes` REAL: 1.200 EAN (500 + 500 + 200) y dos paises por EAN."""
    def cruzar(cruce, params, pasada):
        ean = [{'id': 'e%d' % i, 'cruce_id': cruce, 'foto_id': 'f%d' % i} for i in range(1200)]
        pais = [{'cruce_id': cruce, 'resultado_ean_id': 'e%d' % i, 'pais': p} for i in range(1200) for p in ('ES', 'DE')]
        g['_en_lotes']('escaner2_resultado_ean', ean)
        g['_en_lotes']('escaner2_resultado_pais', pais)
        cierre = {'estado': cierre_estado, 'motivo_fallo': None if cierre_estado == 'lista' else
                  'NO CUADRA en la base: 1200 entradas y 1199 en las puertas', 'n_crudo': 1, 'n_previas': 0,
                  'n_entradas': 1200}
        for p in 'abcdef':
            cierre['n_' + p] = 0
        return cierre, False
    return cruzar


def correr(bd, cierre_estado='lista'):
    g = cargar(bd)
    g['cruzar'] = cruzar_de_mentira(g, bd, cierre_estado)
    codigo = 0
    try:
        g['main']()
    except SystemExit as ex:
        codigo = ex.code if isinstance(ex.code, int) else 1
    nuevo = [c for c in bd['tablas']['escaner2_cruce'] if c['id'] != LISTA][0]
    return codigo, g, nuevo


def de(bd, tabla, cruce):
    return len([f for f in bd['tablas'][tabla] if f['cruce_id'] == cruce])


def lo_del_otro(bd):
    return (de(bd, 'escaner2_resultado_ean', LISTA), de(bd, 'escaner2_resultado_pais', LISTA),
            [c['estado'] for c in bd['tablas']['escaner2_cruce'] if c['id'] == LISTA])


print('1 · [segunda tanda] la 2.a tanda de EAN falla → 0 filas del cruce, el otro intacto')
bd = base_inicial()
bd['falla_insert'] = ('escaner2_resultado_ean', 2)
cod, g, c = correr(bd)
eq('1 · el programa escribe en tandas de 500 (no se ha tocado el tamaño)', g['LOTE'], 500)
eq('1 · la 1.a tanda SI entró antes del fallo (hay algo que borrar)',
   [o[:2] for o in bd['ops'] if o[0] == 'insert'], [('insert', 'escaner2_cruce'), ('insert', 'escaner2_resultado_ean'),
                                                   ('insert', 'escaner2_resultado_ean')])
eq('1 · 🔴 el run sale en ROJO', cod, 1)
eq('1 · 🔴 el cruce queda fallida, con el motivo de siempre (el error de la base) y nada más',
   (c['estado'], c['motivo_fallo'].startswith('ErrorBase: ') and 'violates check constraint' in c['motivo_fallo'],
    'NO SE HAN PODIDO BORRAR' in c['motivo_fallo']), ('fallida', True, False))
eq('1 · 🔴 0 filas de ESE cruce en escaner2_resultado_ean y en escaner2_resultado_pais',
   (de(bd, 'escaner2_resultado_ean', c['id']), de(bd, 'escaner2_resultado_pais', c['id'])), (0, 0))
eq('1 · 🔴 el cruce lista de al lado, intacto (7 y 7 filas, sigue lista)', lo_del_otro(bd), (7, 7, ['lista']))
_borrados = [o for o in bd['ops'] if o[0] == 'delete']
eq('1 · 🔴 dos DELETE, primero país (apunta a EAN) y luego EAN, filtrando SOLO por su cruce_id',
   _borrados, [('delete', 'escaner2_resultado_pais', (('cruce_id', c['id']),)),
               ('delete', 'escaner2_resultado_ean', (('cruce_id', c['id']),))])
_i_del = max(i for i, o in enumerate(bd['ops']) if o[0] == 'delete')
_i_upd = [i for i, o in enumerate(bd['ops']) if o[0] == 'update' and o[1] == 'escaner2_cruce'][0]
eq('1 · 🔴 se borra ANTES de marcarlo fallida', _i_del < _i_upd, True)

print('\n2 · [borrado frenado] la base no deja borrar → fallida igual, y el motivo lo dice')
bd = base_inicial()
bd['falla_insert'] = ('escaner2_resultado_ean', 2)
bd['frenar_delete'] = True
cod, g, c = correr(bd)
eq('2 · 🔴 el run sale en ROJO y el cruce queda fallida (no colgado en cruzando)', (cod, c['estado']), (1, 'fallida'))
eq('2 · 🔴 el motivo empieza por el de siempre y DICE que no se han podido borrar, cuántas quedan y por qué',
   (c['motivo_fallo'].startswith('ErrorBase: '),
    'NO SE HAN PODIDO BORRAR SUS FILAS (quedan: escaner2_resultado_pais 0, escaner2_resultado_ean 500)' in c['motivo_fallo'],
    'permission denied' in c['motivo_fallo']), (True, True, True))
eq('2 · …y cabe en la columna (2.000)', len(c['motivo_fallo']) <= 2000, True)
bd2 = base_inicial()
bd2['falla_insert'] = ('escaner2_resultado_ean', 2)
bd2['frenar_delete'] = True


def _cruzar_largo(cruce, params, pasada):
    g2['_en_lotes']('escaner2_resultado_ean', [{'id': 'x', 'cruce_id': cruce}])
    raise RuntimeError('x' * 5000)


g2 = cargar(bd2)
g2['cruzar'] = _cruzar_largo
try:
    g2['main']()
except SystemExit:
    pass
_c2 = [x for x in bd2['tablas']['escaner2_cruce'] if x['id'] != LISTA][0]
eq('2 · con un motivo de 5.000 caracteres, el aviso del borrado NO se pierde al recortar',
   (len(_c2['motivo_fallo']) <= 2000, 'NO SE HAN PODIDO BORRAR' in _c2['motivo_fallo']), (True, True))

print('\n3 · [no cuadra] todo escrito, pero el cuadre no sale → también sin filas')
bd = base_inicial()
cod, g, c = correr(bd, cierre_estado='fallida')
eq('3 · 🔴 ROJO, fallida con su motivo del cuadre', (cod, c['estado'], c['motivo_fallo']),
   (1, 'fallida', 'NO CUADRA en la base: 1200 entradas y 1199 en las puertas'))
eq('3 · 🔴 0 filas suyas; el lista, intacto',
   (de(bd, 'escaner2_resultado_ean', c['id']), de(bd, 'escaner2_resultado_pais', c['id']), lo_del_otro(bd)),
   (0, 0, (7, 7, ['lista'])))
eq('3 · …y el cierre guarda sus cifras (las contadas en la base antes de borrar)', c['n_entradas'], 1200)

print('\n4 · [bueno] cruce lista → ni un DELETE')
bd = base_inicial()
cod, g, c = correr(bd)
eq('4 · verde y lista, con sus 1.200 + 2.400 filas', (cod, c['estado'], de(bd, 'escaner2_resultado_ean', c['id']),
                                                      de(bd, 'escaner2_resultado_pais', c['id'])), (0, 'lista', 1200, 2400))
eq('4 · 🔴 ni un DELETE', [o for o in bd['ops'] if o[0] == 'delete'], [])

print('\n5 · [muerde] sin el borrado (el programa de antes), quedan las 500 filas de la 1.a tanda')
bd = base_inicial()
bd['falla_insert'] = ('escaner2_resultado_ean', 2)
g = cargar(bd)
g['cruzar'] = cruzar_de_mentira(g, bd)
g['_motivo_tras_limpiar'] = lambda _cruce, motivo: motivo[:2000]   # lo que hacia el main de antes
try:
    g['main']()
except SystemExit:
    pass
c = [x for x in bd['tablas']['escaner2_cruce'] if x['id'] != LISTA][0]
eq('5 · 🔴 sin el arreglo, un cruce fallida con 500 filas: es lo que los casos 1-3 cazan',
   (c['estado'], de(bd, 'escaner2_resultado_ean', c['id'])), ('fallida', 500))

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: un cruce fallido no deja filas en escaner2_resultado_ean ni _pais, y el lista de al lado no se toca.')
