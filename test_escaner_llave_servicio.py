# -*- coding: utf-8 -*-
"""Banco: el escaner corre con la llave de SERVICIO, o no corre.

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
      un grep contaria la explicacion como si fuera codigo): que el cliente que
      se llama `sb` nace de `SUPABASE_SERVICE_KEY` y DE NADA MAS.
  (B) POR ESTRUCTURA, con `yaml`: que TODO paso de TODO workflow cuyo `run`
      lance el escaner lleve `SUPABASE_SERVICE_KEY` en SU PROPIO `env`. Por el
      paso, no por el fichero: en los directores la llave ya viajaba en el paso
      de preparar, y ahi no le sirve de nada al escaner.
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

LAS DOS DIRECCIONES, MEDIDAS. (E1) se ha visto rojo devolviendo a mano el
respaldo del #291 (`_llave_svc or os.environ['SUPABASE_KEY']`): el proceso deja
de abortar, nace el cliente con la anonima y las tres comprobaciones del caso
caen a la vez.
"""
import ast
import io
import os
import re
import subprocess
import sys
import types

import yaml

RUTA = 'moloka_escaner_nube.py'


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


def llave_del_cliente(fuente):
    """Devuelve ('solo-servicio' | 'servicio-con-respaldo' | 'solo-anonima' |
    'no-encontrado').

    Busca la asignacion a `sb` cuyo valor sea `create_client(...)`, resuelve el
    segundo argumento y, si es un Name, lo sigue hasta su asignacion. Eso ultimo
    no es adorno: la linea real guarda la llave en `_llave_svc` antes de usarla,
    y un test que solo mirase dentro del `create_client` no veria de donde sale.
    """
    arbol = ast.parse(fuente)
    nombres = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 \
                and isinstance(nodo.targets[0], ast.Name):
            nombres[nodo.targets[0].id] = nodo.value

    llamada = nombres.get('sb')
    if not (isinstance(llamada, ast.Call)
            and isinstance(llamada.func, ast.Name) and llamada.func.id == 'create_client'
            and len(llamada.args) == 2):
        return 'no-encontrado'

    arg = llamada.args[1]
    if _es_environ_idx(arg, 'SUPABASE_KEY') or _es_environ_get(arg, 'SUPABASE_KEY'):
        return 'solo-anonima'

    # El caso de HOY: un Name que se resuelve a `os.environ.get('SUPABASE_SERVICE_KEY')`
    # y a nada mas. Sin `or`, que es lo que este PR viene a quitar.
    suelto = nombres.get(arg.id) if isinstance(arg, ast.Name) else arg
    if _es_environ_get(suelto, 'SUPABASE_SERVICE_KEY'):
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


print("(A) el cliente del escaner, por estructura")
with io.open(RUTA, encoding='utf-8') as fh:
    _fuente = fh.read()
eq('(A) 🔴 `sb` nace de SUPABASE_SERVICE_KEY y de nada mas',
   llave_del_cliente(_fuente), 'solo-servicio')

# (C) las otras direcciones: los DOS codigos viejos, tal cual estaban.
_ANTES = ("from supabase import create_client\n"
          "sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])\n")
eq('(C) 🔴 … y el codigo de antes del #291 (solo anonima) lo RECHAZA',
   llave_del_cliente(_ANTES), 'solo-anonima')

_291 = ("from supabase import create_client\n"
        "_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')\n"
        "sb  = create_client(os.environ['SUPABASE_URL'], _llave_svc or os.environ['SUPABASE_KEY'])\n")
eq('(C) 🔴 … y el del #291 (con respaldo mudo a la anonima) TAMBIEN lo rechaza',
   llave_del_cliente(_291), 'servicio-con-respaldo')

# ─────────────────────────────────────────────────────────────────────────────
# (B) LA LLAVE, EN EL PASO QUE LANZA EL ESCANER
# ─────────────────────────────────────────────────────────────────────────────
ESCANER = 'moloka_escaner_nube.py'


def pasos_del_escaner(doc):
    """Todo paso de `doc` cuyo `run` lance el escaner, con su `env` propio."""
    salida = []
    for job in (doc.get('jobs') or {}).values():
        for paso in (job.get('steps') or []):
            if ESCANER in (paso.get('run') or ''):
                salida.append(paso)
    return salida


def sin_llave(doc):
    """Los pasos que lanzan el escaner y NO llevan la llave de servicio."""
    return [p for p in pasos_del_escaner(doc)
            if 'SUPABASE_SERVICE_KEY' not in (p.get('env') or {})]


print("\n(B) la llave de servicio, en el paso que lanza el escaner")
_dir = os.path.join('.github', 'workflows')
_mirados, _incumplen = [], []
for _f in sorted(os.listdir(_dir)):
    if not _f.endswith(('.yml', '.yaml')):
        continue
    with io.open(os.path.join(_dir, _f), encoding='utf-8') as fh:
        _doc = yaml.safe_load(fh) or {}
    for _p in pasos_del_escaner(_doc):
        _mirados.append('%s :: %s' % (_f, _p.get('name') or '(sin nombre)'))
    for _p in sin_llave(_doc):
        _incumplen.append('%s :: %s' % (_f, _p.get('name') or '(sin nombre)'))

print("    pasos que lanzan el escaner: %d" % len(_mirados))
for _m in _mirados:
    print("      · " + _m)

eq('(B) 🔴 ningun paso lanza el escaner sin la llave de servicio', _incumplen, [])

# (D) contra el verde vacio. Los cinco son los cuatro directores + `escaner-app`.
# Si mañana nace un sexto, este numero sube A PROPOSITO, no por descuido.
eq('(D) …y se han mirado los CINCO pasos que existen, no cero', len(_mirados), 5)

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
print()
if FALLOS:
    print("ROJO: %d comprobacion(es) fallan:" % len(FALLOS))
    for _f in FALLOS:
        print("  - " + _f)
    sys.exit(1)
print("VERDE: el escaner exige la llave de servicio, y los cinco pasos se la dan.")
