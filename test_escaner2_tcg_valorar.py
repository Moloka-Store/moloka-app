# -*- coding: utf-8 -*-
"""Banco de LA VALORACION DE LAS NOVEDADES DE TCG Y LOS AVISOS DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026):
escaner2_tcg_valorar.py y su workflow, escaner2-tcg-valorar.yml.

SIN RED, SIN SECRETOS Y SIN BASE: una base de mentira en memoria y una valoracion de mentira (la de verdad,
escaner2_novedades.valorar_pasada, tiene su banco en test_escaner2_novedades.py). 🔴 DATOS INVENTADOS (repo publico).

QUE PRUEBA:
  (A) valora TODAS las pasadas de TCG con la seleccion hecha y la valoracion sin cerrar, de la mas vieja a la mas nueva: la
      encargada siempre (aunque sea de hace un segundo) y las demas solo si llevan mas de PENDIENTE_MIN_S; ni las ya
      valoradas, ni las de seleccion fallida, ni las de otro proveedor; cada una con su cifra de novedades para la
      avalancha (novedades menos subidas fuera) y la llave de Keepa;
  (B) 🔴 NINGUNA SE QUEDA SIN VALORAR EN SILENCIO: una pasada cuyo encargo no llego (selección hecha, valoracion vacia) la
      recoge la corrida siguiente, aunque esa corrida venga de otra pasada; una valoracion que falla sale en ROJO y queda
      sin cerrar para la siguiente;
  (C) los avisos: «parada» manda el Telegram con el motivo de la base; «tramos», el suyo; «valorar», ninguno; un Telegram
      que no sale, ROJO;
  (D) guardas: AVISO de la lista, PASADA un uuid o nada, sin la base o sin Keepa ROJO sin valorar nada;
  (E) el registro no suelta el motivo, ni un token, ni un EAN;
  (F) por estructura: el workflow solo se lanza a mano (workflow_dispatch, sin reloj), con su grupo propio sin cancelar,
      los inputs por env:, los secretos solo en el paso que valora, y sin artefactos.
"""
import contextlib
import io
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-tcg-valorar.yml')

import escaner2_novedades as nv  # noqa: E402
import escaner2_tcg_valorar as prog  # noqa: E402

fallos = []
AHORA = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
ENV = {'SUPABASE_URL': 'https://base.invalid', 'SUPABASE_SERVICE_KEY': 'LLAVE-BASE-SECRETA',
       'KEEPA_API_KEY': 'LLAVE-KEEPA-SECRETA', 'TELEGRAM_TOKEN': 'TOKEN-TG', 'TELEGRAM_CHAT_ID': 'CHAT-TG',
       'GITHUB_RUN_ID': '555'}
MOTIVO = 'la web de TCG no deja: login: HTTP 403 · desde la máquina de la oficina · EAN 8000000000017'
P = ['%08d-0000-4000-8000-000000000000' % i for i in range(10)]


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ── La base de mentira ────────────────────────────────────────────────────────────────────
class _Q:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.filtros, self.orden, self.lim = base, tabla, [], None, None

    def select(self, *_a, **_k):
        return self

    def eq(self, k, v):
        self.filtros.append(lambda f, k=k, v=v: f.get(k) == v); return self

    def is_(self, k, v):
        assert v == 'null'
        self.filtros.append(lambda f, k=k: f.get(k) is None); return self

    def order(self, k, desc=False):
        self.orden = (k, desc); return self

    def limit(self, n):
        self.lim = n; return self

    def execute(self):
        filas = [dict(f) for f in self.base.t.get(self.tabla, []) if all(p(f) for p in self.filtros)]
        if self.orden:
            filas.sort(key=lambda f: str(f.get(self.orden[0])), reverse=self.orden[1])
        if self.lim is not None:
            filas = filas[:self.lim]
        return types.SimpleNamespace(data=filas)


class Base:
    def __init__(self, nov=(), disp=()):
        self.t = {'nov_pasada': [dict(f) for f in nov], 'disp_pasada': [dict(f) for f in disp]}

    def table(self, n):
        return _Q(self, n)


def nov(pid, hace_s, estado='hecha', valoracion=None, proveedor='TCG', novedades=3, subidas=1):
    return {'pasada_id': pid, 'proveedor': proveedor, 'estado': estado, 'valoracion_estado': valoracion,
            'creada_en': (AHORA - timedelta(seconds=hace_s)).isoformat(), 'n_novedades': novedades,
            'n_subidas_fuera': subidas}


class Valoracion:
    """valorar_pasada de mentira: apunta cada llamada y cierra la fila (como nov_cerrar_valoracion), o falla."""

    def __init__(self, base, fallan=()):
        self.base, self.fallan, self.llamadas = base, set(fallan), []

    def __call__(self, sb, pasada, keepa_llave=None, imprimir=None, run_id=None, novedades_pasada=None, env=None,
                 post=None, proveedor=None):
        self.llamadas.append((pasada, novedades_pasada, keepa_llave, proveedor, run_id))
        if pasada in self.fallan:
            return False, {'estado': 'fallida'}
        for f in self.base.t['nov_pasada']:
            if f['pasada_id'] == pasada:
                f['valoracion_estado'] = 'hecha'
        return True, {'estado': 'hecha'}


telegramas = []


def post_tg(url, data, timeout):
    telegramas.append(data['text'])
    return types.SimpleNamespace(status_code=200)


def correr(base, env=None, fallan=(), post=post_tg):
    val = Valoracion(base, fallan)
    salida = io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(salida):
        try:
            codigo = prog.principal(env=dict(ENV, **(env or {})), sb=base, valorar_pasada=val, post=post, ahora=AHORA)
        except SystemExit as ex:
            codigo = ex.code
    return codigo, salida.getvalue(), val


def limpio(nombre, registro):
    eq(nombre + ': el registro no suelta el motivo, tokens, llaves ni EAN',
       [p for p in ('403', 'LLAVE-', 'TOKEN-TG', 'CHAT-TG', '8000000000017') if p in registro], [])


# ── (A) Qué se valora ─────────────────────────────────────────────────────────────────────
base = Base(nov=[nov(P[1], 3600, novedades=5, subidas=2),                 # se quedó atrás hace 1 h
                 nov(P[2], 30),                                           # la encargada, de hace 30 s
                 nov(P[3], 60),                                           # otra de hace 1 min: la está valorando su dueño
                 nov(P[4], 7200, valoracion='hecha'),                     # ya valorada
                 nov(P[5], 7200, estado='fallida'),                       # la selección falló: no hay nada que valorar
                 nov(P[6], 7200, proveedor='DBLINE')])                    # de otro proveedor
telegramas.clear()
codigo, reg, val = correr(base, env={'AVISO': 'valorar', 'PASADA': P[2]})
eq('A1 valora la que se quedó atrás y la encargada, de la más vieja a la más nueva; ni la de hace 1 min (su dueño), ni '
   'las valoradas, ni las de selección fallida, ni las de otro proveedor', [c[0] for c in val.llamadas], [P[1], P[2]])
eq('A2 …cada una con sus novedades para la avalancha (novedades − subidas fuera), la llave de Keepa, TCG y el run',
   [(c[1], c[2], c[3], c[4]) for c in val.llamadas],
   [(3, 'LLAVE-KEEPA-SECRETA', 'TCG', '555'), (2, 'LLAVE-KEEPA-SECRETA', 'TCG', '555')])
eq('A3 …VERDE, sin Telegram propio, y el registro lo cuenta',
   (codigo, len(telegramas), 'pendientes 2 (la encargada sí está entre ellas) · bien 2 · en ROJO 0' in reg), (0, 0, True))
limpio('A4', reg)
eq('A5 el umbral de las ajenas son 2 min', prog.PENDIENTE_MIN_S, 120)
base = Base(nov=[nov(P[3], prog.PENDIENTE_MIN_S + 1), nov(P[4], prog.PENDIENTE_MIN_S - 1)])
codigo, reg, val = correr(base)
eq('A6 sin pasada (a mano): solo lo pendiente de más de 2 min', [c[0] for c in val.llamadas], [P[3]])
base = Base(nov=[nov(P[2], 7200, valoracion='hecha')])
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('A7 la encargada ya valorada (un relanzamiento): no se repite, VERDE y lo dice',
   (codigo, val.llamadas, 'ya valorada, sin selección hecha o no es de TCG' in reg), (0, [], True))

# ── (B) Ninguna se queda sin valorar en silencio ──────────────────────────────────────────
# El encargo de la pasada 1 no llegó (la lectura salió en ROJO con TCG_VALORACION_NO_ENCARGADA): su fila sigue sin cerrar.
base = Base(nov=[nov(P[1], 3600)])
base.t['nov_pasada'].append(nov(P[2], 5))
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('B1 🔴 la corrida que llega por la pasada siguiente valora también la que se quedó sin encargo',
   ([c[0] for c in val.llamadas], [f['valoracion_estado'] for f in base.t['nov_pasada']]), ([P[1], P[2]], ['hecha', 'hecha']))
base = Base(nov=[nov(P[1], 3600), nov(P[2], 5)])
codigo, reg, val = correr(base, env={'PASADA': P[2]}, fallan={P[1]})
eq('B2 🔴 una valoración que falla: ROJO, las demás siguen, y la que falló queda sin cerrar',
   (codigo, [c[0] for c in val.llamadas], [f['valoracion_estado'] for f in base.t['nov_pasada']],
    'bien 1 · en ROJO 1' in reg), (1, [P[1], P[2]], [None, 'hecha'], True))
codigo, reg, val = correr(base, env={'PASADA': P[3]})
eq('B3 …y la recoge la corrida siguiente', ([c[0] for c in val.llamadas], codigo), ([P[1]], 0))


class Revienta(Valoracion):
    def __call__(self, *a, **k):
        raise RuntimeError('Failing row contains (8000000000017, LLAVE-KEEPA-SECRETA)')


base = Base(nov=[nov(P[1], 3600)])
salida = io.StringIO()
with contextlib.redirect_stdout(salida):
    codigo = prog.principal(env=dict(ENV), sb=base, valorar_pasada=Revienta(base), post=post_tg, ahora=AHORA)
eq('B4 una valoración que revienta (no debería: valorar_pasada no lanza): ROJO y sin cerrar',
   (codigo, base.t['nov_pasada'][0]['valoracion_estado']), (1, None))
limpio('B5', salida.getvalue())

# ── (C) Los avisos ────────────────────────────────────────────────────────────────────────
base = Base(disp=[{'id': P[7], 'proveedor': 'TCG', 'estado': 'fallida', 'motivo': MOTIVO}])
telegramas.clear()
codigo, reg, val = correr(base, env={'AVISO': 'parada', 'PASADA': P[7]})
eq('C1 «parada»: un Telegram con el motivo de la base, que dice que era la oficina; VERDE',
   (codigo, len(telegramas), MOTIVO in telegramas[0] if telegramas else None, 'oficina' in (telegramas or [''])[0]),
   (0, 1, True, True))
limpio('C2', reg)
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'parada', 'PASADA': P[8]})
eq('C3 «parada» de una pasada que no está en la base: el Telegram lo dice igual', (codigo, len(telegramas),
   'no está en la base' in (telegramas or [''])[0]), (0, 1, True))
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'tramos', 'PASADA': P[8]})
eq('C4 «tramos»: el Telegram del lector parado', (codigo, len(telegramas), 'lector de tramos' in (telegramas or [''])[0]),
   (0, 1, True))
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'valorar', 'PASADA': P[8]})
eq('C5 «valorar»: ningún Telegram propio', (codigo, len(telegramas)), (0, 0))
codigo, reg, val = correr(Base(), env={'AVISO': 'parada', 'PASADA': P[8]},
                         post=lambda url, data, timeout: types.SimpleNamespace(status_code=500))
eq('C6 🔴 el Telegram de la parada no sale: ROJO', codigo, 1)
base = Base(nov=[nov(P[1], 3600)], disp=[{'id': P[7], 'proveedor': 'TCG', 'estado': 'fallida', 'motivo': MOTIVO}])
codigo, reg, val = correr(base, env={'AVISO': 'parada', 'PASADA': P[7]})
eq('C7 con un aviso también se valora lo pendiente', [c[0] for c in val.llamadas], [P[1]])

# ── (D) Guardas ───────────────────────────────────────────────────────────────────────────
for nombre, env in (('AVISO raro', {'AVISO': 'todo'}), ('PASADA que no es un uuid', {'PASADA': "x'; drop table"}),
                    ('sin la base', {'SUPABASE_SERVICE_KEY': ''}), ('sin Keepa', {'KEEPA_API_KEY': ''})):
    base = Base(nov=[nov(P[1], 3600)])
    codigo, reg, val = correr(base, env=env)
    eq('D1 %s: ROJO sin valorar nada' % nombre, (codigo, val.llamadas, 'TCG_VALORAR_NO_EJECUTADO' in reg), (1, [], True))
codigo, reg, val = correr(Base(nov=[nov(P[2], 5)]), env={'PASADA': P[2].upper()})
eq('D2 el uuid en mayúsculas vale (se normaliza)', [c[0] for c in val.llamadas], [P[2]])

# ── (F) El workflow, por estructura ───────────────────────────────────────────────────────
wf = yaml.safe_load(open(WORKFLOW, encoding='utf-8'))
disparo = wf.get(True) or wf.get('on')
eq('F1 solo se lanza a mano (workflow_dispatch), sin reloj', sorted(disparo), ['workflow_dispatch'])
eq('F2 los inputs: aviso de la lista (por defecto valorar) y pasada',
   (disparo['workflow_dispatch']['inputs']['aviso']['options'], disparo['workflow_dispatch']['inputs']['aviso']['default'],
    sorted(disparo['workflow_dispatch']['inputs'])), (list(prog.AVISOS), 'valorar', ['aviso', 'pasada']))
eq('F3 grupo propio, sin cancelar la que corre', wf['concurrency'], {'group': 'escaner2-tcg-valorar', 'cancel-in-progress': False})
pasos = wf['jobs']['valorar']['steps']
con_secretos = [p.get('name') for p in pasos if 'secrets.' in yaml.safe_dump(p)]
eq('F4 los secretos, solo en el paso que valora', con_secretos, ['Valorar lo pendiente de TCG y mandar el aviso encargado'])
paso = pasos[-1]
eq('F5 los inputs llegan por env:, nunca dentro de run:',
   ('inputs.' in paso['run'], paso['env']['AVISO'], paso['env']['PASADA']),
   (False, '${{ inputs.aviso }}', '${{ inputs.pasada }}'))
eq('F6 corre el programa, con tope en el job y en el paso, y sin artefactos',
   (paso['run'], bool(wf['jobs']['valorar'].get('timeout-minutes')), bool(paso.get('timeout-minutes')),
    'upload-artifact' in open(WORKFLOW, encoding='utf-8').read()), ('python -u escaner2_tcg_valorar.py', True, True, False))
eq('F7 el token del run, solo para leer el repo', wf['permissions'], {'contents': 'read'})
eq('F8 🔑 el workflow que encarga la lectura de la oficina es ESTE (mismo nombre en los dos lados)',
   os.path.basename(WORKFLOW), __import__('escaner2_tcg_disponibilidad').WORKFLOW_VALORAR)

print()
print('TODO OK' if not fallos else 'FALLOS: %d (%s)' % (len(fallos), ', '.join(fallos)))
sys.exit(1 if fallos else 0)
