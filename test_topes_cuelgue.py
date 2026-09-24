# -*- coding: utf-8 -*-
"""Los topes contra cuelgues de los procesadores (encargo AJ, 24-sep-2026).

🔴 POR QUE. El 24-sep el ledger (run 35956134193) cargo 1592 movimientos y se quedo
   71 min colgado esperando la respuesta del refresco del Trackeador: la base de
   produccion se reinicio a las 06:35:16 Madrid (04:35:16 UTC) con esa llamada en marcha
   («database system was not properly shut down»; la causa NO esta probada). Dos
   agujeros, y esta mesa vigila los dos:
     1. `conectar_bd` abria la conexion sin keepalives ni `tcp_user_timeout`: una
        conexion muerta a mitad de consulta se esperaba PARA SIEMPRE.
     2. Los `procesar-*.yml` no tenian `timeout-minutes` en el job: GitHub espera 6 h.

🔑 POR ESTRUCTURA, NO POR TEXTO. Los workflows se leen con pyyaml y se mira la clave del
   JOB (un `timeout-minutes` de un paso no vale: el del registro lleva uno de 1 min y un
   grep lo contaria). Los procesadores se sacan de `git ls-files`, no de una lista: el
   dia que nazca un `procesar-*.yml` nuevo sin tope, esto se pone ROJO solo.

🔒 Lo que NO ve: que la conexion muerta de error de verdad. Eso se midio contra un
   Postgres local cortando la red con iptables (INFORME del encargo AJ): error a los
   92 s con keepalives; sin ellos, sigue colgado. Y tampoco ve lo que los keepalives no
   pueden ver: si la cadena pasa por el pooler, una base caida detras de el. Ahi manda
   el tope del job.
"""
import os
import subprocess
import sys

import yaml

import foto_comun as fc

RAIZ = os.path.dirname(os.path.abspath(__file__))

# El exito mas largo de los nueve procesar-*.yml, medido el 24-sep-2026 con la API de
# GitHub (622 runs): paneu-aptos, 587 s, el 29-jul. Un tope por debajo cortaria una carga
# buena; uno de horas no es un tope.
EXITO_MAS_LARGO_S = 587
TOPE_MAXIMO_MIN = 60

fallos = []


def chk(nombre, ok, detalle=''):
    if not ok:
        fallos.append(nombre)
    print('%s  %s%s' % ('OK' if ok else 'XX', nombre, '' if ok else '   ' + detalle))


# ── 1 · El tope del JOB en todos los procesar-*.yml ─────────────────────────────────────
salida = subprocess.run(['git', 'ls-files', '.github/workflows'], cwd=RAIZ,
                        capture_output=True, text=True, check=True).stdout.split()
procesadores = sorted(f for f in salida if os.path.basename(f).startswith('procesar-')
                      and f.endswith('.yml'))
chk('hay procesar-*.yml que mirar (9 el 24-sep-2026)', len(procesadores) >= 9,
    'solo %d' % len(procesadores))

for f in procesadores:
    with open(os.path.join(RAIZ, f), encoding='utf-8') as fh:
        wf = yaml.safe_load(fh)
    for nombre_job, job in wf['jobs'].items():
        t = job.get('timeout-minutes')
        etiqueta = '%s · job %s' % (os.path.basename(f), nombre_job)
        chk('%s: tiene timeout-minutes en el JOB' % etiqueta, isinstance(t, int), 'got=%r' % t)
        if isinstance(t, int):
            chk('%s: el tope (%d min) deja pasar el exito mas largo medido (%d s)'
                % (etiqueta, t, EXITO_MAS_LARGO_S), t * 60 > EXITO_MAS_LARGO_S * 1.5)
            chk('%s: y es un tope, no una espera (<= %d min)' % (etiqueta, TOPE_MAXIMO_MIN),
                t <= TOPE_MAXIMO_MIN, 'got=%d' % t)


# ── 2 · Los keepalives llegan a psycopg2.connect ────────────────────────────────────────
kw_vistos = {}


class _ConFalsa:
    pass


def _connect_falso(db_url, **kw):
    kw_vistos.update(kw)
    return _ConFalsa()


orig = fc.psycopg2.connect
fc.psycopg2.connect = _connect_falso
try:
    fc.conectar_bd('postgres://x', esperas=(0,))
finally:
    fc.psycopg2.connect = orig

for clave in ('keepalives', 'keepalives_idle', 'keepalives_interval', 'keepalives_count',
              'tcp_user_timeout'):
    chk('conectar_bd pasa %s a psycopg2.connect' % clave, clave in kw_vistos,
        'kw=%r' % sorted(kw_vistos))
chk('keepalives encendidos (=1)', kw_vistos.get('keepalives') == 1, 'got=%r' % kw_vistos.get('keepalives'))
chk('connect_timeout sigue llegando (10)', kw_vistos.get('connect_timeout') == 10)

# 🔑 La cuenta que importa: cuanto tarda en darse por muerta. El encargo pide ~1-2 min.
if all(k in kw_vistos for k in ('keepalives_idle', 'keepalives_interval', 'keepalives_count',
                                 'tcp_user_timeout')):
    sondas_s = (kw_vistos['keepalives_idle']
                + kw_vistos['keepalives_interval'] * kw_vistos['keepalives_count'])
    usuario_s = kw_vistos['tcp_user_timeout'] / 1000
    chk('keepalives: muerta en 60-120 s (idle + interval x count = %d s)' % sondas_s,
        60 <= sondas_s <= 120)
    chk('tcp_user_timeout: 60-120 s (%d s)' % usuario_s, 60 <= usuario_s <= 120)

# 🔒 Y que la libpq que viene con psycopg2 CONOCE esos nombres. Una opcion desconocida al
#    conectar sale como OperationalError sin pgcode, que `conectar_bd` tomaria por un corte
#    de red: cuatro reintentos y un aborto que culparia a la red. `parse_dsn` pasa por
#    PQconninfoParse, que rechaza lo que no conoce, sin abrir ninguna conexion.
try:
    dsn = fc.psycopg2.extensions.make_dsn('host=x', **{k: v for k, v in kw_vistos.items()})
    fc.psycopg2.extensions.parse_dsn(dsn)
    chk('la libpq instalada (%s) acepta todas las opciones' % fc.psycopg2.__libpq_version__, True)
except Exception as e:  # noqa: BLE001
    chk('la libpq instalada acepta todas las opciones', False, '%s: %s' % (type(e).__name__, e))


print()
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK')
