# -*- coding: utf-8 -*-
"""Banco: el escaner lee `productos` con una llave que la RLS deja pasar.

EL FALLO QUE CIERRA (10-sep-2026). Los cuatro directores llevaban un dia y medio
en rojo. Ninguno llego a preguntarle nada a Keepa: morian en la guarda del
catalogo propio, con la misma linea en los cuatro logs:

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

QUE SE PRUEBA, Y COMO:
  (A) POR ESTRUCTURA, con `ast` sobre el fichero real (no con un grep sobre el
      texto: el comentario que hay junto a la linea nombra las dos variables, y
      un grep contaria la explicacion como si fuera codigo): que el cliente que
      se llama `sb` nace de `SUPABASE_SERVICE_KEY` con respaldo a `SUPABASE_KEY`.
  (B) POR ESTRUCTURA, con `yaml`: que TODO paso de TODO workflow cuyo `run`
      lance el escaner lleve `SUPABASE_SERVICE_KEY` en SU PROPIO `env`. Por el
      paso, no por el fichero: en los directores la llave ya viajaba en el paso
      de preparar, y ahi no le sirve de nada al escaner.
  (C) LAS DOS DIRECCIONES. Cada comprobacion se corre ademas contra el caso malo
      -- el codigo de antes del arreglo, y un paso sin la llave -- y tiene que
      RECHAZARLO. Sin esto, (A) y (B) saldrian verdes tambien si el detector
      estuviera roto y dijera que todo esta bien.
  (D) Y contra el verde vacio: si el barrido de workflows no encuentra los pasos
      que sabemos que existen, eso es un fallo. "Cero incumplidores" de cero
      pasos mirados es la forma que tiene esta clase de test de mentir.
"""
import ast
import io
import os
import sys

import yaml

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
# El predicado se escribe UNA vez y se usa dos: contra el fichero real (tiene que
# decir que si) y contra el codigo de antes del arreglo (tiene que decir que no).

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
    """Devuelve ('servicio-con-respaldo' | 'solo-anonima' | 'no-encontrado').

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

    if not (isinstance(arg, ast.BoolOp) and isinstance(arg.op, ast.Or) and len(arg.values) == 2):
        return 'no-encontrado'

    preferida, respaldo = arg.values
    if isinstance(preferida, ast.Name):
        preferida = nombres.get(preferida.id)
    if _es_environ_get(preferida, 'SUPABASE_SERVICE_KEY') \
            and _es_environ_idx(respaldo, 'SUPABASE_KEY'):
        return 'servicio-con-respaldo'
    return 'no-encontrado'


print("(A) el cliente del escaner, por estructura")
with io.open('moloka_escaner_nube.py', encoding='utf-8') as fh:
    _fuente = fh.read()
eq('(A) 🔴 `sb` nace de SUPABASE_SERVICE_KEY con respaldo a SUPABASE_KEY',
   llave_del_cliente(_fuente), 'servicio-con-respaldo')

# (C) la otra direccion: EL CODIGO DE ANTES, tal cual estaba en `e181a2c`.
_ANTES = ("from supabase import create_client\n"
          "sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])\n")
eq('(C) 🔴 … y el codigo de antes del arreglo lo RECHAZA',
   llave_del_cliente(_ANTES), 'solo-anonima')

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
print()
if FALLOS:
    print("ROJO: %d comprobacion(es) fallan:" % len(FALLOS))
    for _f in FALLOS:
        print("  - " + _f)
    sys.exit(1)
print("VERDE: el escaner pide la llave de servicio y los cinco pasos se la dan.")
