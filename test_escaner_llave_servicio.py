# -*- coding: utf-8 -*-
"""Banco: los programas desatendidos corren con la llave de SERVICIO, o no corren.

EL PRIMER FALLO, EL QUE CERRO EL #291 (10-sep-2026). Los cuatro directores
llevaban un dia y medio en rojo. Ninguno llego a preguntarle nada a Keepa:
morian en la guarda del catalogo propio, con la misma linea en los cuatro logs:

    ESCANEO_NO_EJECUTADO: catalogo propio ilegible: productos devolvio 0 filas
    con activo=true.

La causa no estaba en el escaner ni en el proveedor: entre las 06:02 y las 06:30
UTC de ese dia se retiraron de `public.productos` las dos politicas permisivas
por las que entraba `anon` ("Acceso publico productos" y "anon_full_access").
`anon` conservaba sus ocho GRANT -- por eso mirar los permisos de tabla no
enseñaba nada --, pero con la RLS puesta y ninguna politica que le toque, un
SELECT de `anon` no lanza: devuelve 200 CON CERO FILAS.

LAS DOS MITADES, Y POR QUE HACEN FALTA LAS DOS. `director-heo.yml` YA pasaba
`SUPABASE_SERVICE_KEY` al paso del escaner el dia del fallo -- se le ve en el log
del run #248, en el volcado del env -- y HEO cayo igual, porque el script solo
leia `SUPABASE_KEY`. Y al reves: cambiar el script no sirve de nada en un
workflow que no le pase la llave. Ninguna de las dos mitades sola arregla esto,
asi que este banco exige LAS DOS.

🔴 Y NO ERAN CUATRO PROGRAMAS: ERAN NUEVE. El #291 arreglo el escaner de tokens,
que es el que corren los directores, porque fue el que se puso ROJO. Los otros
cinco lectores desatendidos de `productos` no se pusieron rojos por la misma
razon por la que son PEORES: no tienen guarda. Se quedaron leyendo un catalogo
vacio y siguiendo adelante en verde. Por eso este banco ya no habla de "el
escaner": habla de la LISTA de programas que leen `productos` sin nadie delante,
y esa lista vive abajo en `PROGRAMAS`, con la forma de llave que se le exige a
cada uno. Anadir un programa desatendido que lea `productos` y no tocar esa
lista es la unica forma que le queda a este fallo de repetirse.

EL SEGUNDO FALLO, EL QUE CIERRA ESTE PR (10-sep-2026, mismo dia). El #291 dejo
el cliente naciendo de `SUPABASE_SERVICE_KEY or SUPABASE_KEY`. Ese respaldo era
prudencia mientras `anon` aun podia escribir. Deja de serlo en cuanto se aplique
la tanda 3 del cierre del invitado, que cierra a `anon` las TRES puertas por las
que el escaner ESCRIBE en `escaner_memoria` (`em_insert`, `em_select`,
`em_update`; medidas por Cowork en produccion): desde ese dia, un lanzamiento SIN
la llave de servicio no revienta -- el upsert devuelve 200 con cero filas -- y el
run sale VERDE sobre una tabla que no se ha tocado. Basta con que el secreto
falte, caduque, o que alguien quite esa linea del workflow. Ahora el escaner
ABORTA en el arranque, sin gastar un token:

    ESCANEO_NO_EJECUTADO: sin llave de servicio

QUE SE PRUEBA, Y COMO:
  (A) POR ESTRUCTURA, con `ast` sobre el fichero real (no con un grep sobre el
      texto: el comentario que hay junto a la linea nombra las dos variables, y
      un grep contaria la explicacion como si fuera codigo): que el cliente de
      cada programa de `PROGRAMAS` nace de la llave que le toca. Al escaner se le
      exige `SUPABASE_SERVICE_KEY` Y NADA MAS; a los otros cinco, de momento, la
      de servicio con respaldo a la anonima. 🔴 Esa diferencia esta declarada a
      proposito y es la pregunta abierta: el argumento del #292 vale igual para
      los cinco -- todos ESCRIBEN en tablas que la tanda 3 cierra --, pero
      apretarlos es una decision de Fernando, no un efecto colateral.
  (B) POR ESTRUCTURA, con `yaml`: que TODO paso de TODO workflow cuyo `run`
      lance uno de esos programas lleve `SUPABASE_SERVICE_KEY` en SU PROPIO `env`.
      Por el paso, no por el fichero: en los directores la llave ya viajaba en el
      paso de preparar, y ahi no le sirve de nada al escaner.
  (C) LAS DOS DIRECCIONES. Cada comprobacion se corre ademas contra los casos
      malos -- el codigo de antes del #291, el del propio #291 (el del respaldo)
      y un paso sin la llave -- y tiene que RECHAZARLOS. Sin esto, (A) y (B)
      saldrian verdes tambien si el detector estuviera roto y dijera que si a
      todo.
  (D) Y contra el verde vacio: si el barrido de workflows no encuentra los pasos
      que sabemos que existen, eso es un fallo. "Cero incumplidores" de cero
      pasos mirados es la forma que tiene esta clase de test de mentir.
  (E) DE PUNTA A PUNTA, dos veces, cada una en su PROCESO (el escaner es un
      script: se corre con `runpy` y hace `sys.exit`). Con `keepa` y `supabase`
      sustituidos por dobles en memoria, sin red y sin secretos:
        1. SIN la llave -> exit 1, la linea exacta de arriba, CERO clientes de
           Supabase creados y CERO llamadas a Keepa. Este es el banco que se ve
           rojo quitando la llave del workflow.
        2. CON la llave -> el arranque la PASA (el cliente nace, y nace con la
           llave de SERVICIO) y el escaner muere mas abajo, en el buzon vacio,
           con OTRA linea. Sin este segundo caso, el primero saldria verde
           tambien si el escaner abortase siempre.

  (F) LA GUARDA DEL CATALOGO PROPIO DEL ESCANER PRO, EJECUTADA. La llave es la
      mitad que arregla; la guarda es la que AVISA el dia que la llave falte. Se
      sacan `abortar` y `leer_productos_propios` del fichero real con `ast` y se
      corren con un Supabase de mentira: cero filas tiene que abortar en ROJO, y
      la version de antes -- guardada ahi tal cual estaba -- tiene que NO abortar.

LAS DOS DIRECCIONES, MEDIDAS. (E1) se ha visto rojo devolviendo a mano el
respaldo del #291 (`_llave_svc or os.environ['SUPABASE_KEY']`): el proceso deja
de abortar, nace el cliente con la anonima y las tres comprobaciones del caso
caen a la vez. (A), (B) y (F) se han visto rojas deshaciendo cada mitad por
separado: la llave del paso de `escaner-pro.yml`, la del cliente del detector y
la guarda del Pro devuelta a su version de antes.
"""
import ast
import io
import os
import re
import subprocess
import sys
import types
from contextlib import redirect_stdout

import yaml

RUTA = 'moloka_escaner_nube.py'

# ---------------------------------------------------------------------------
# LA LISTA. Un programa desatendido que lee `productos`, la forma de llave que
# se le exige, y cuantos pasos lo lanzan HOY.
# ---------------------------------------------------------------------------
# La cuenta de pasos es la mitad (D), contra el verde vacio: si manana nace uno
# mas, ese numero sube A PROPOSITO, no por descuido.
#
# 🔒 El cero de `moloka_tracker_snapshot.py` NO es un descuido: se corre a mano
#    desde el portatil y no lo lanza ningun workflow (medido el 10-sep-2026
#    sobre los 57 ficheros de .github/workflows). Su mitad (A) se le exige
#    igual; la (B) no existe. El dia que alguien le ponga un workflow, este
#    cero se pone rojo y obliga a mirar si le pasa la llave.
PROGRAMAS = [
    (RUTA,                         'solo-servicio',         5),   # 4 directores + escaner-app
    ('moloka_escaner_pro_nube.py', 'servicio-con-respaldo', 1),   # escaner-pro
    ('moloka_actualizar_nube.py',  'servicio-con-respaldo', 1),   # actualizar-app
    ('moloka_detector_bems.py',    'servicio-con-respaldo', 1),   # detector-bems
    ('robot_generar.py',           'servicio-con-respaldo', 1),   # fabrica-generar
    ('moloka_tracker_snapshot.py', 'servicio-con-respaldo', 0),   # a mano: ningun workflow
]


# ===========================================================================
# EL HIJO: monta los dobles y corre el escaner de punta a punta
# ---------------------------------------------------------------------------
# A proposito NO monta buzon ni catalogo: lo que se mide aqui es el ARRANQUE.
# El caso [con-llave] muere unas lineas mas abajo, en el recado ausente, y esa
# es justo la prueba de que la guarda de la llave le ha dejado pasar.
# ===========================================================================
def hijo(caso):
    import atexit

    CUENTA = {'keepa': 0, 'clientes': 0}
    LLAVES = []

    class _FakeKeepa:
        def __init__(self, key, timeout=None):
            self.tokens_left = 1500

        def update_status(self):
            pass

        def query(self, items, **kw):
            CUENTA['keepa'] += 1
            return []

    class _Bucket:
        def list(self, carpeta):
            return []      # buzon VACIO -> el escaner aborta por el recado

        def download(self, ruta):
            raise Exception('404 ' + ruta)

    class _Cliente:
        def __init__(self):
            self.storage = types.SimpleNamespace(from_=lambda _b: _Bucket())

        def table(self, nombre):
            raise AssertionError('el arranque no toca ninguna tabla: ' + nombre)

    def _create_client(url, key):
        CUENTA['clientes'] += 1
        LLAVES.append(key)
        return _Cliente()

    sys.modules['keepa'] = types.ModuleType('keepa')
    sys.modules['keepa'].Keepa = _FakeKeepa
    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = _create_client

    os.environ['KEEPA_API_KEY'] = 'FAKE'
    os.environ['SUPABASE_URL'] = 'https://doble.local'
    os.environ['SUPABASE_KEY'] = 'FAKE-ANONIMA'
    if caso == 'con-llave':
        os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    else:
        os.environ.pop('SUPABASE_SERVICE_KEY', None)
    for v in ('TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID', 'AUTORELANZAR_MIN'):
        os.environ.pop(v, None)

    # Por `atexit`: el escaner sale con sys.exit(1) al abortar, y estas tres
    # lineas son justo las que hay que leer en ese caso.
    @atexit.register
    def _informe():
        print('CLIENTES_SUPABASE=%d' % CUENTA['clientes'])
        print('LLAMADAS_KEEPA=%d' % CUENTA['keepa'])
        print('LLAVES=%s' % ','.join(str(k) for k in LLAVES))

    import runpy
    runpy.run_path(RUTA, run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2])
    sys.exit(0)


# ===========================================================================
# EL PADRE: los asserts
# ===========================================================================
FALLOS = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("  OK  " if ok else "  FALLA  ") + nombre
          + ("" if ok else "\n        esperado: %r\n        obtenido: %r" % (esperado, obtenido)))
    if not ok:
        FALLOS.append(nombre)


# ─────────────────────────────────────────────────────────────────────────────
# (A) EL CLIENTE DEL ESCANER, POR ESTRUCTURA
# ─────────────────────────────────────────────────────────────────────────────
# El predicado se escribe UNA vez y se usa tres: contra el fichero real (tiene
# que decir 'solo-servicio') y contra los dos codigos viejos (tienen que salir
# con su nombre, que NO es ese).

def _es_environ_get(nodo, clave):
    """`os.environ.get('CLAVE')`"""
    return (isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == 'get'
            and isinstance(nodo.func.value, ast.Attribute)
            and nodo.func.value.attr == 'environ'
            and len(nodo.args) == 1
            and isinstance(nodo.args[0], ast.Constant) and nodo.args[0].value == clave)


def _es_environ_idx(nodo, clave):
    """`os.environ['CLAVE']`"""
    return (isinstance(nodo, ast.Subscript)
            and isinstance(nodo.value, ast.Attribute) and nodo.value.attr == 'environ'
            and isinstance(nodo.slice, ast.Constant) and nodo.slice.value == clave)


def llave_del_cliente(fuente, var='sb'):
    """Devuelve ('solo-servicio' | 'servicio-con-respaldo' | 'solo-anonima' |
    'no-encontrado').

    Busca la asignacion a `var` cuyo valor sea `create_client(...)`, resuelve el
    segundo argumento y, si es un Name, lo sigue hasta su asignacion. Eso ultimo
    no es adorno: hay ficheros que guardan la llave en una variable antes de
    usarla, y un test que solo mirase dentro del `create_client` no veria de
    donde sale.

    🔒 Se busca LA ASIGNACION QUE ES UN create_client, no la ultima asignacion
       a ese nombre. En `moloka_tracker_snapshot.py` el cliente vive dentro de
       `main()` y unas lineas mas arriba hay un `sb = None`; quedarse con la
       ultima de la lista dependeria del orden en que `ast.walk` baja por el
       arbol, que no es el orden del fichero.
    """
    arbol = ast.parse(fuente)
    nombres = {}
    llamada = None
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and isinstance(nodo.targets[0], ast.Name)):
            continue
        nombres[nodo.targets[0].id] = nodo.value
        if (nodo.targets[0].id == var and isinstance(nodo.value, ast.Call)
                and isinstance(nodo.value.func, ast.Name)
                and nodo.value.func.id == 'create_client'):
            llamada = nodo.value

    if llamada is None or len(llamada.args) != 2:
        return 'no-encontrado'

    arg = llamada.args[1]
    # Un Name se sigue hasta su asignacion ANTES de clasificar: si no, un
    # `SUPABASE_KEY = <servicio> or <anonima>` usado por nombre se leeria como
    # 'no-encontrado' y este banco saldria verde sin haber mirado nada.
    if isinstance(arg, ast.Name) and arg.id in nombres:
        arg = nombres[arg.id]

    if _es_environ_idx(arg, 'SUPABASE_KEY') or _es_environ_get(arg, 'SUPABASE_KEY'):
        return 'solo-anonima'

    # El caso del escaner desde el #292: `os.environ.get('SUPABASE_SERVICE_KEY')`
    # y nada mas. Sin `or`.
    if _es_environ_get(arg, 'SUPABASE_SERVICE_KEY'):
        return 'solo-servicio'

    # El caso del #291: `<servicio> or <anonima>`.
    if isinstance(arg, ast.BoolOp) and isinstance(arg.op, ast.Or) and len(arg.values) == 2:
        preferida, respaldo = arg.values
        if isinstance(preferida, ast.Name):
            preferida = nombres.get(preferida.id)
        if _es_environ_get(preferida, 'SUPABASE_SERVICE_KEY') \
                and _es_environ_idx(respaldo, 'SUPABASE_KEY'):
            return 'servicio-con-respaldo'
    return 'no-encontrado'


print("(A) el cliente de cada programa, por estructura")
for _script, _forma, _n in PROGRAMAS:
    with io.open(_script, encoding='utf-8') as fh:
        _fuente = fh.read()
    eq('(A) 🔴 %-28s `sb` nace %s' % (_script, _forma),
       llave_del_cliente(_fuente), _forma)

# (C) las otras direcciones: los DOS codigos viejos, tal cual estaban.
_ANTES = ("from supabase import create_client\n"
          "sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])\n")
eq('(C) 🔴 … y el codigo de antes del #291 (solo anonima) lo RECHAZA',
   llave_del_cliente(_ANTES), 'solo-anonima')

_291 = ("from supabase import create_client\n"
        "_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')\n"
        "sb  = create_client(os.environ['SUPABASE_URL'], _llave_svc or os.environ['SUPABASE_KEY'])\n")
eq('(C) 🔴 … y el del #291 (con respaldo mudo a la anonima) sale con SU nombre',
   llave_del_cliente(_291), 'servicio-con-respaldo')

# La forma en que estaba escrito ANTES en los otros cinco: la llave anonima
# guardada en una variable. Sin resolver el Name, esto salia 'no-encontrado'.
_ANTES_VARIABLE = ("SUPABASE_KEY = os.environ['SUPABASE_KEY']\n"
                   "sb = create_client(SUPABASE_URL, SUPABASE_KEY)\n")
eq('(C) 🔴 … y la llave anonima guardada en una variable TAMBIEN se ve',
   llave_del_cliente(_ANTES_VARIABLE), 'solo-anonima')
# Y que el predicado no diga que si a todo: un fichero sin cliente.
eq('(C) …y un fichero sin cliente sale "no-encontrado"',
   llave_del_cliente("x = 1\n"), 'no-encontrado')

# ─────────────────────────────────────────────────────────────────────────────
# (B) LA LLAVE, EN EL PASO QUE LANZA EL ESCANER
# ─────────────────────────────────────────────────────────────────────────────
ESCANER = 'moloka_escaner_nube.py'


def pasos_del_escaner(doc, script=ESCANER):
    """Todo paso de `doc` cuyo `run` lance `script`, con su `env` propio."""
    salida = []
    for job in (doc.get('jobs') or {}).values():
        for paso in (job.get('steps') or []):
            if script in (paso.get('run') or ''):
                salida.append(paso)
    return salida


def sin_llave(doc, script=ESCANER):
    """Los pasos que lanzan `script` y NO llevan la llave de servicio."""
    return [p for p in pasos_del_escaner(doc, script)
            if 'SUPABASE_SERVICE_KEY' not in (p.get('env') or {})]


print("\n(B) la llave de servicio, en el paso que lanza cada programa")
_dir = os.path.join('.github', 'workflows')
_docs = []
for _f in sorted(os.listdir(_dir)):
    if not _f.endswith(('.yml', '.yaml')):
        continue
    with io.open(os.path.join(_dir, _f), encoding='utf-8') as fh:
        _docs.append((_f, yaml.safe_load(fh) or {}))

_incumplen, _total = [], 0
for _script, _forma, _esperados in PROGRAMAS:
    _mirados = []
    for _f, _doc in _docs:
        for _p in pasos_del_escaner(_doc, _script):
            _mirados.append('%s :: %s' % (_f, _p.get('name') or '(sin nombre)'))
        for _p in sin_llave(_doc, _script):
            _incumplen.append('%s :: %s' % (_f, _p.get('name') or '(sin nombre)'))
    _total += len(_mirados)
    print("    %-28s %d paso(s)" % (_script, len(_mirados)))
    for _m in _mirados:
        print("      · " + _m)
    # (D) contra el verde vacio, programa a programa.
    eq('(D) …y de %-28s se han mirado sus %d paso(s)' % (_script, _esperados),
       len(_mirados), _esperados)

eq('(B) 🔴 ningun paso lanza ninguno de estos programas sin la llave de servicio',
   _incumplen, [])
eq('(D) …y en total se han mirado los NUEVE pasos que existen, no cero', _total, 9)

# (C) la otra direccion: un paso que lanza el escaner sin la llave tiene que
# salir en la lista. Este es el estado exacto de `director-dbline.yml` ayer.
_MALO = {'jobs': {'director': {'steps': [
    {'name': '1) Preparar', 'env': {'SUPABASE_SERVICE_KEY': 'x'},
     'run': 'python -u director_dbline_prep.py'},
    {'name': '2) Escanear FBA', 'env': {'SUPABASE_KEY': 'x'},
     'run': 'python -u ' + ESCANER},
]}}}
eq('(C) 🔴 … y el workflow de ayer lo RECHAZA (la llave en preparar no cuenta)',
   [p.get('name') for p in sin_llave(_MALO)], ['2) Escanear FBA'])

# Y que el detector no este diciendo que si a todo: el mismo doc con la llave
# puesta en el paso del escaner tiene que salir limpio.
_BUENO = yaml.safe_load(yaml.safe_dump(_MALO))
_BUENO['jobs']['director']['steps'][1]['env']['SUPABASE_SERVICE_KEY'] = 'x'
eq('(C) …y el mismo con la llave puesta sale limpio', sin_llave(_BUENO), [])


# ─────────────────────────────────────────────────────────────────────────────
# (E) DE PUNTA A PUNTA: el escaner real, dos veces, cada una en su proceso
# ─────────────────────────────────────────────────────────────────────────────
print("\n(E) de punta a punta, con dobles")


def correr(caso):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout or '') + (p.stderr or '')

    def cifra(clave):
        m = re.search(r'^%s=(\d+)\s*$' % clave, out, re.M)
        return int(m.group(1)) if m else -1

    _ll = re.search(r'^LLAVES=(.*)$', out, re.M)
    return {'codigo': p.returncode, 'salida': out,
            'clientes': cifra('CLIENTES_SUPABASE'), 'keepa': cifra('LLAMADAS_KEEPA'),
            'llaves': [x for x in (_ll.group(1).strip() if _ll else '').split(',') if x]}


_sin = correr('sin-llave')
eq('(E1) 🔴 sin la llave de servicio el run sale en ROJO (exit 1)', _sin['codigo'], 1)
eq('(E1) 🔴 con la linea exacta, grepable',
   'ESCANEO_NO_EJECUTADO: sin llave de servicio' in _sin['salida'], True)
eq('(E1) 🔴 y NO nace ningun cliente de Supabase (ni con la anonima de respaldo)',
   _sin['clientes'], 0)
eq('(E1) 🔴 cero llamadas a Keepa: no se gasta ni un token', _sin['keepa'], 0)

_con = correr('con-llave')
eq('(E2) 🔴 con la llave, el arranque la PASA: el cliente nace', _con['clientes'], 1)
eq('(E2) 🔴 y nace con la llave de SERVICIO, no con la anonima',
   _con['llaves'], ['FAKE-SERVICE'])
eq('(E2) 🔴 el escaner muere mas abajo y por OTRO motivo (buzon vacio)',
   ('sin llave de servicio' not in _con['salida']
    and 'ESCANEO_NO_EJECUTADO: recado ilegible o ausente' in _con['salida']), True)

# ─────────────────────────────────────────────────────────────────────────────
# (F) LA GUARDA DEL CATALOGO PROPIO DEL ESCANER PRO, EJECUTADA
# ─────────────────────────────────────────────────────────────────────────────
# `moloka_escaner_pro_nube.py` no se puede importar: crea el cliente de Supabase
# con la llave del entorno nada mas arrancar. Asi que las dos funciones se sacan
# del fichero REAL con `ast` -- por estructura, buscando el `def` por su nombre en
# el arbol -- y se EJECUTAN. No se prueba una copia: se prueba lo que corre.
PRO = 'moloka_escaner_pro_nube.py'
_ARBOL_PRO = ast.parse(io.open(PRO, encoding='utf-8').read(), PRO)


def sacar_def(nombre):
    for n in _ARBOL_PRO.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
    print('  FALLA  (F) la funcion %s() ya no esta en %s (o dejo de ser de nivel superior)'
          % (nombre, PRO))
    sys.exit(1)


class _Resp:
    def __init__(self, data):
        self.data = data


class _Consulta:
    """Imita la cadena select().eq().range().execute() de supabase-py."""

    def __init__(self, filas, error):
        self._filas, self._error, self._desde = filas, error, 0

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def range(self, desde, hasta):
        self._desde = desde
        return self

    def execute(self):
        if self._error is not None:
            raise self._error
        # La primera pagina trae todo; la segunda viene vacia, como en la vida real.
        return _Resp(self._filas if self._desde == 0 else [])


class _SB:
    def __init__(self, filas=(), error=None):
        self._filas, self._error = list(filas), error

    def table(self, nombre):
        assert nombre == 'productos', 'la guarda no deberia mirar otra tabla: ' + nombre
        return _Consulta(self._filas, self._error)


def correr_guarda(fuente_defs, sb, llave='ANONIMA (la RLS decide)'):
    """Ejecuta `leer_productos_propios()` -> (resultado, salida, codigo de salida).

    `codigo` es None si NO aborto, o el codigo con el que salio si aborto."""
    ns = {'sys': sys, 'sb': sb, '_ORIGEN_LLAVE': llave,
          'norm': lambda v: str(v or '').strip().lstrip('0')}
    exec(compile(fuente_defs, PRO, 'exec'), ns)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            return ns['leer_productos_propios'](), buf.getvalue(), None
    except SystemExit as ex:
        return None, buf.getvalue(), ex.code


_MOD_PRO = ast.fix_missing_locations(
    ast.Module(body=[sacar_def('abortar'), sacar_def('leer_productos_propios')], type_ignores=[]))

print("\n(F) la guarda del catalogo propio del escaner Pro, ejecutada")

_FICHAS = [{'ean': '0074427811266', 'stock_moloka': 3, 'stock_fba': 7},
           {'ean': '8412345678905', 'stock_moloka': 0, 'stock_fba': 1}]

_sup, _log, _codigo = correr_guarda(_MOD_PRO, _SB(_FICHAS), llave='SERVICIO')
eq('(F) con fichas: NO aborta', _codigo, None)
eq('(F) …y devuelve las dos fichas indexadas por EAN normalizado', sorted(_sup or {}),
   ['74427811266', '8412345678905'])
eq('(F) …y el log deja las cifras y la llave',
   'CATALOGO_PROPIO: filas=2 | con_ean=2 | llave=SERVICIO' in _log, True)

_sup, _log, _codigo = correr_guarda(_MOD_PRO, _SB([]))
eq('(F) 🔴 CERO FILAS con la llave anonima: aborta en ROJO', _codigo, 1)
eq('(F) …con la linea grepable de los dos escaneres',
   'ESCANEO_NO_EJECUTADO' in _log, True)
eq('(F) …y el motivo dice con que llave se leyo',
   'ANONIMA' in _log.split('ESCANEO_NO_EJECUTADO')[-1], True)

_sup, _log, _codigo = correr_guarda(_MOD_PRO, _SB([], error=RuntimeError('conexion caida')))
eq('(F) 🔴 y si la lectura LANZA, tambien aborta en ROJO', _codigo, 1)
eq('(F) …diciendo que lanzo, no que venia vacia',
   'RuntimeError' in _log and 'conexion caida' in _log, True)

# (C) la otra direccion, y es la que importa: EL CODIGO DE ANTES DEL ARREGLO,
# copiado tal cual estaba en `a981a69`. Con cero filas devolvia {} tan tranquilo,
# el boton salia VERDE y el Excel llevaba la columna «En mi BD» vacia entera.
_ANTES_GUARDA = '''
def leer_productos_propios():
    sup = {}
    try:
        d = 0
        while True:
            res = sb.table('productos').select('ean,stock_moloka,stock_fba').eq('activo', True).range(d, d+999).execute()
            if not res.data: break
            for p in res.data:
                if p.get('ean'): sup[norm(p['ean'])] = p
            if len(res.data) < 1000: break
            d += 1000
    except Exception as ex:
        print('AVISO: no se pudieron leer productos propios:', ex)
    return sup
'''
_sup, _log, _codigo = correr_guarda(_ANTES_GUARDA, _SB([]))
eq('(C) 🔴 …y el codigo de antes NO abortaba: seguia con el catalogo vacio', _codigo, None)
eq('(C) …devolviendo {} y sin imprimir ni un aviso', (_sup, _log.strip()), ({}, ''))

# ─────────────────────────────────────────────────────────────────────────────
print()
if FALLOS:
    print("ROJO: %d comprobacion(es) fallan:" % len(FALLOS))
    for _f in FALLOS:
        print("  - " + _f)
    sys.exit(1)
print("VERDE: los seis programas piden su llave, los nueve pasos se la dan\n"
      "       y la guarda del Pro aborta cuando `productos` viene vacio.")
