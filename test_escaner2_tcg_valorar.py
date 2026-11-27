# -*- coding: utf-8 -*-
"""Banco de LA VALORACION DE LAS NOVEDADES DE TCG Y LOS AVISOS DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026):
escaner2_tcg_valorar.py, su workflow (escaner2-tcg-valorar.yml) y su red con reloj (escaner2-tcg-novedades-cuentas.yml).

SIN RED, SIN SECRETOS Y SIN BASE: una base de mentira en memoria y una valoracion de mentira FIEL a la de verdad
(escaner2_novedades.valorar_pasada, con su banco en test_escaner2_novedades.py): cierra la fila de nov_pasada con
valoracion_estado 'hecha' o 'fallida' y valoracion_en, devuelve lo que devuelve nov_cerrar_valoracion (con su motivo) y
ok=False si falla. 🔴 DATOS INVENTADOS (repo publico).

QUE PRUEBA:
  (A) valora lo pendiente de TCG: la encargada siempre (aunque sea de hace un segundo), las demas sin cerrar solo si
      llevan mas de PENDIENTE_MIN_S, de la mas vieja a la mas nueva; ni las ya valoradas, ni las de seleccion fallida, ni
      las de otro proveedor; cada una con su cifra para la avalancha (novedades menos subidas fuera) y la llave de Keepa;
  (B) 🔴 LAS AVALANCHAS ANTES DE TOCAR KEEPA, sea cual sea el orden; 🔴 NINGUNA SE QUEDA SIN VALORAR EN SILENCIO: la que se
      quedo sin encargo la recoge la corrida siguiente; una valoracion fallida queda a la vista (fallida en la base,
      ROJO y dicho en el registro) y la siguiente corrida la reintenta, durante RECOGER_FALLIDAS_H; pasado ese tiempo, no;
  (C) los avisos: «parada» manda SOLO el Telegram con el motivo de la base (sin Keepa ni valorar nada); «tramos», el suyo;
      un Telegram que no sale, ROJO;
  (D) guardas: AVISO de la lista, PASADA un uuid o nada, sin la base ROJO; sin Keepa no se valora (el aviso sí sale);
  (E) 🔴 el registro no suelta el motivo de la base, ni un token, ni un EAN;
  (F) por estructura, el workflow: solo a mano; el job del aviso SIN grupo (nada lo espera ni lo sustituye) y sin Keepa; el
      job de valorar en el grupo `escaner2-tcg` (el de las cuentas) sin cancelar; inputs por env:; secretos solo en sus
      pasos; topes; sin artefactos;
  (G) por estructura, la red: escaner2-tcg-novedades-cuentas.yml valora lo pendiente ANTES de sus cuentas, en el mismo job
      (grupo escaner2-tcg), solo en las cuentas sueltas, y las cuentas corren aunque la valoracion falle.
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
CUENTAS = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-tcg-novedades-cuentas.yml')

import escaner2_novedades as nv  # noqa: E402
import escaner2_tcg_valorar as prog  # noqa: E402

fallos = []
AHORA = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
ENV = {'SUPABASE_URL': 'https://base.invalid', 'SUPABASE_SERVICE_KEY': 'LLAVE-BASE-SECRETA',
       'KEEPA_API_KEY': 'LLAVE-KEEPA-SECRETA', 'TELEGRAM_TOKEN': 'TOKEN-TG', 'TELEGRAM_CHAT_ID': 'CHAT-TG',
       'GITHUB_RUN_ID': '555'}
MOTIVO = 'la web de TCG no deja: login: HTTP 403 · desde la máquina de la oficina · EAN 8000000000017'
MOTIVO_BASE = 'NO CUADRA: Failing row contains (8000000000017, 9.77)'
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

    def gte(self, k, v):
        self.filtros.append(lambda f, k=k, v=v: f.get(k) is not None and prog._fecha(f[k]) >= prog._fecha(v)); return self

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


def nov(pid, hace_s, estado='hecha', valoracion=None, proveedor='TCG', novedades=3, subidas=1, valorada_hace_s=None):
    return {'pasada_id': pid, 'proveedor': proveedor, 'estado': estado, 'valoracion_estado': valoracion,
            'valoracion_en': None if valorada_hace_s is None else (AHORA - timedelta(seconds=valorada_hace_s)).isoformat(),
            'creada_en': (AHORA - timedelta(seconds=hace_s)).isoformat(), 'n_novedades': novedades,
            'n_subidas_fuera': subidas}


class Valoracion:
    """valorar_pasada de mentira, FIEL a la de verdad: apunta cada llamada; cierra la fila (valoracion_estado y valoracion_en,
    como nov_cerrar_valoracion) con 'hecha', o con 'fallida' si la pasada esta en `fallan`; devuelve lo de la base, con su
    motivo; y ok=False si falla. `keepa`: las pasadas que llegaron a recorrer la cola (las que no son avalancha)."""

    def __init__(self, base, fallan=()):
        self.base, self.fallan, self.llamadas, self.keepa = base, set(fallan), [], []

    def __call__(self, sb, pasada, keepa_llave=None, imprimir=None, run_id=None, novedades_pasada=None, env=None,
                 post=None, proveedor=None):
        self.llamadas.append((pasada, novedades_pasada, keepa_llave, proveedor, run_id))
        if not (novedades_pasada or 0) > nv.AVALANCHA:
            self.keepa.append(pasada)
        estado = 'fallida' if pasada in self.fallan else 'hecha'
        for f in self.base.t['nov_pasada']:
            if f['pasada_id'] == pasada:
                f['valoracion_estado'], f['valoracion_en'] = estado, AHORA.isoformat()
        res = {'pasada': pasada, 'estado': estado, 'motivo': MOTIVO_BASE if estado == 'fallida' else None,
               'novedades': 12, 'valoradas': 4, 'pendientes': 0}
        if imprimir:
            imprimir('>>> VALORACION DE NOVEDADES: %s' % (res,), flush=True)
            if estado == 'fallida':
                imprimir('    AVISO: %s' % MOTIVO_BASE, flush=True)
        return estado == 'hecha', res


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
       [p for p in ('403', 'NO CUADRA', 'Failing row', 'LLAVE-', 'TOKEN-TG', 'CHAT-TG', '8000000000017') if p in registro], [])


# ── (A) Qué se valora ─────────────────────────────────────────────────────────────────────
base = Base(nov=[nov(P[1], 3600, novedades=5, subidas=2),                 # se quedó atrás hace 1 h
                 nov(P[2], 30),                                           # la encargada, de hace 30 s
                 nov(P[3], 300),                                          # otra de hace 5 min: la puede estar valorando su dueño
                 nov(P[4], 7200, valoracion='hecha', valorada_hace_s=7000),   # ya valorada
                 nov(P[5], 7200, estado='fallida'),                       # la selección falló: no hay nada que valorar
                 nov(P[6], 7200, proveedor='DBLINE')])                    # de otro proveedor
telegramas.clear()
codigo, reg, val = correr(base, env={'AVISO': 'valorar', 'PASADA': P[2]})
eq('A1 valora la que se quedó atrás y la encargada, de la más vieja a la más nueva; ni la de hace 5 min (su dueño), ni '
   'las valoradas, ni las de selección fallida, ni las de otro proveedor', [c[0] for c in val.llamadas], [P[1], P[2]])
eq('A2 …cada una con sus novedades para la avalancha (novedades − subidas fuera), la llave de Keepa, TCG y el run',
   [(c[1], c[2], c[3], c[4]) for c in val.llamadas],
   [(3, 'LLAVE-KEEPA-SECRETA', 'TCG', '555'), (2, 'LLAVE-KEEPA-SECRETA', 'TCG', '555')])
eq('A3 …VERDE, sin Telegram propio, y el registro lo cuenta, pasada a pasada, con su estado y sus cifras',
   (codigo, len(telegramas), 'pendientes 2 (la encargada sí está entre ellas) · bien 2 · en ROJO 0' in reg,
    '>>> VALORACION de la pasada %s (pendiente): hecha · novedades 12 · pendientes 0 · valoradas 4 · bien.' % P[2] in reg),
   (0, 0, True, True))
limpio('A4', reg)
eq('A5 el umbral de las ajenas son 15 min (la valoración en el acto de TCG tarda hasta 227 s medidos)', prog.PENDIENTE_MIN_S, 900)
base = Base(nov=[nov(P[3], prog.PENDIENTE_MIN_S + 1), nov(P[4], prog.PENDIENTE_MIN_S - 1)])
codigo, reg, val = correr(base)
eq('A6 sin pasada (a mano o la red): solo lo pendiente de más de 15 min', [c[0] for c in val.llamadas], [P[3]])
base = Base(nov=[nov(P[2], 7200, valoracion='hecha', valorada_hace_s=7000)])
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('A7 la encargada ya valorada (un relanzamiento): no se repite, VERDE y lo dice',
   (codigo, val.llamadas, 'ya valorada, sin selección hecha o no es de TCG' in reg), (0, [], True))

# ── (B) Avalanchas primero, y ninguna sin valorar en silencio ─────────────────────────────
AV = nv.AVALANCHA
base = Base(nov=[nov(P[1], 3600, novedades=3), nov(P[2], 30, novedades=AV + 51, subidas=1)])
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('B1 🔴 una pendiente vieja normal y una nueva con avalancha: la avalancha se cierra PRIMERO; Keepa solo recorre la cola '
   'después', ([c[0] for c in val.llamadas], val.keepa), ([P[2], P[1]], [P[1]]))
eq('B1b …y el registro dice cuál era la avalancha', '>>> VALORACION de la pasada %s (avalancha, pendiente)' % P[2] in reg, True)
base = Base(nov=[nov(P[1], 7200, novedades=AV + 1, subidas=0), nov(P[2], 3600, novedades=AV + 1, subidas=1),
                 nov(P[3], 30, novedades=4)])
codigo, reg, val = correr(base, env={'PASADA': P[3]})
eq('B2 el límite es «más de» AVALANCHA (novedades − subidas): 101 lo es, 100 no', [c[0] for c in val.llamadas], [P[1], P[2], P[3]])
eq('B2b …y solo la de 101 se cierra sin Keepa', val.keepa, [P[2], P[3]])
# El encargo de la pasada 1 no llegó (la lectura salió en ROJO con TCG_VALORACION_NO_ENCARGADA): su fila sigue sin cerrar.
base = Base(nov=[nov(P[1], 3600), nov(P[2], 5)])
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('B3 🔴 la corrida que llega por la pasada siguiente valora también la que se quedó sin encargo',
   ([c[0] for c in val.llamadas], [f['valoracion_estado'] for f in base.t['nov_pasada']]), ([P[1], P[2]], ['hecha', 'hecha']))
base = Base(nov=[nov(P[1], 3600), nov(P[2], 5)])
codigo, reg, val = correr(base, env={'PASADA': P[2]}, fallan={P[1]})
eq('B4 🔴 una valoración que falla: ROJO, las demás siguen, y la que falló queda A LA VISTA (fallida en la base)',
   (codigo, [c[0] for c in val.llamadas], [f['valoracion_estado'] for f in base.t['nov_pasada']]),
   (1, [P[1], P[2]], ['fallida', 'hecha']))
eq('B5 …el registro la nombra, EN ROJO, y dice dónde está el motivo (sin el motivo)',
   ('>>> VALORACION de la pasada %s (pendiente): fallida · novedades 12 · pendientes 0 · valoradas 4 · EN ROJO (el motivo, en '
    'nov_pasada.valoracion_motivo).' % P[1] in reg, 'bien 1 · en ROJO 1' in reg), (True, True))
limpio('B6', reg)
codigo, reg, val = correr(base)
eq('B7 🔴 …y la siguiente corrida (la red de las cuentas, sin pasada) la REINTENTA, y lo dice',
   ([c[0] for c in val.llamadas], codigo, 'reintento de una fallida' in reg), ([P[1]], 0, True))
base = Base(nov=[nov(P[1], 90000, valoracion='fallida', valorada_hace_s=prog.RECOGER_FALLIDAS_H * 3600 + 60),
                 nov(P[2], 90000, valoracion='fallida', valorada_hace_s=prog.RECOGER_FALLIDAS_H * 3600 - 60)])
codigo, reg, val = correr(base)
eq('B8 una fallida se reintenta durante 24 h; la de hace más, no (su motivo sigue en la base)', [c[0] for c in val.llamadas], [P[2]])
eq('B9 los reintentos, un día', prog.RECOGER_FALLIDAS_H, 24)


class Revienta(Valoracion):
    def __call__(self, *a, **k):
        raise RuntimeError('Failing row contains (8000000000017, LLAVE-KEEPA-SECRETA)')


base = Base(nov=[nov(P[1], 3600)])
salida = io.StringIO()
with contextlib.redirect_stdout(salida):
    codigo = prog.principal(env=dict(ENV), sb=base, valorar_pasada=Revienta(base), post=post_tg, ahora=AHORA)
eq('B10 una valoración que revienta (la de verdad no lanza): ROJO, sin cerrar (la recoge la siguiente) y dicho',
   (codigo, base.t['nov_pasada'][0]['valoracion_estado'], 'sin cerrar (RuntimeError)' in salida.getvalue()), (1, None, True))
limpio('B11', salida.getvalue())

# ── (C) Los avisos: solo el Telegram ──────────────────────────────────────────────────────
base = Base(nov=[nov(P[1], 3600)], disp=[{'id': P[7], 'proveedor': 'TCG', 'estado': 'fallida', 'motivo': MOTIVO}])
telegramas.clear()
codigo, reg, val = correr(base, env={'AVISO': 'parada', 'PASADA': P[7]})
eq('C1 «parada»: un Telegram con el motivo de la base, que dice que era la oficina; VERDE',
   (codigo, len(telegramas), MOTIVO in telegramas[0] if telegramas else None, 'oficina' in (telegramas or [''])[0]),
   (0, 1, True, True))
eq('C2 …y SOLO eso: ni Keepa ni valorar (eso es el otro job)', (val.llamadas, base.t['nov_pasada'][0]['valoracion_estado']),
   ([], None))
limpio('C3', reg)
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'parada', 'PASADA': P[8]})
eq('C4 «parada» de una pasada que no está en la base: el Telegram lo dice igual', (codigo, len(telegramas),
   'no está en la base' in (telegramas or [''])[0]), (0, 1, True))
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'tramos', 'PASADA': P[8]})
eq('C5 «tramos»: el Telegram del lector parado', (codigo, len(telegramas), 'lector de tramos' in (telegramas or [''])[0]),
   (0, 1, True))
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'valorar', 'PASADA': P[8]})
eq('C6 «valorar»: ningún Telegram propio', (codigo, len(telegramas)), (0, 0))
codigo, reg, val = correr(Base(), env={'AVISO': 'parada', 'PASADA': P[8]},
                         post=lambda url, data, timeout: types.SimpleNamespace(status_code=500))
eq('C7 🔴 el Telegram de la parada no sale: ROJO', codigo, 1)

# ── (D) Guardas ───────────────────────────────────────────────────────────────────────────
for nombre, env in (('AVISO raro', {'AVISO': 'todo'}), ('PASADA que no es un uuid', {'PASADA': "x'; drop table"}),
                    ('sin la base', {'SUPABASE_SERVICE_KEY': ''}), ('sin Keepa', {'KEEPA_API_KEY': ''})):
    base = Base(nov=[nov(P[1], 3600)])
    codigo, reg, val = correr(base, env=env)
    eq('D1 %s: ROJO sin valorar nada' % nombre, (codigo, val.llamadas, 'TCG_VALORAR_NO_EJECUTADO' in reg), (1, [], True))
telegramas.clear()
codigo, reg, val = correr(Base(), env={'AVISO': 'tramos', 'KEEPA_API_KEY': ''})
eq('D2 el aviso no necesita Keepa (su job no la lleva)', (codigo, len(telegramas)), (0, 1))
codigo, reg, val = correr(Base(nov=[nov(P[2], 5)]), env={'PASADA': P[2].upper()})
eq('D3 el uuid en mayúsculas vale (se normaliza)', [c[0] for c in val.llamadas], [P[2]])

# ── (F) El workflow, por estructura ───────────────────────────────────────────────────────
texto_wf = open(WORKFLOW, encoding='utf-8').read()
wf = yaml.safe_load(texto_wf)
disparo = wf.get(True) or wf.get('on')
eq('F1 solo se lanza a mano (workflow_dispatch), sin reloj', sorted(disparo), ['workflow_dispatch'])
eq('F2 los inputs: aviso de la lista (por defecto valorar) y pasada',
   (disparo['workflow_dispatch']['inputs']['aviso']['options'], disparo['workflow_dispatch']['inputs']['aviso']['default'],
    sorted(disparo['workflow_dispatch']['inputs'])), (list(prog.AVISOS), 'valorar', ['aviso', 'pasada']))
eq('F3 dos jobs: el aviso y la valoración', sorted(wf['jobs']), ['aviso', 'valorar'])
j_av, j_val = wf['jobs']['aviso'], wf['jobs']['valorar']
eq('F4 🔴 el aviso: solo si se pide, SIN grupo de concurrency (nada lo espera ni lo sustituye), ni a nivel de workflow',
   (j_av.get('if'), 'concurrency' in j_av, 'concurrency' in wf), ("inputs.aviso != 'valorar'", False, False))
eq('F5 🔴 la valoración: siempre, en el grupo de las cuentas (escaner2-tcg) y sin cancelar la que corre',
   ('if' in j_val, j_val.get('concurrency')), (False, {'group': 'escaner2-tcg', 'cancel-in-progress': False}))


def secretos(paso):
    import re
    return sorted(set(re.findall(r'secrets\.([A-Z_]+)', yaml.safe_dump(paso))))


p_av, p_val = j_av['steps'][-1], j_val['steps'][-1]
eq('F6 los secretos, solo en el último paso de cada job',
   [p.get('name') for j in (j_av, j_val) for p in j['steps'] if secretos(p)], [p_av['name'], p_val['name']])
eq('F7 el aviso, sin Keepa; la valoración, con ella',
   (secretos(p_av), secretos(p_val)),
   (['SUPABASE_SERVICE_KEY', 'SUPABASE_URL', 'TELEGRAM_CHAT_ID', 'TELEGRAM_TOKEN'],
    ['KEEPA_API_KEY', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL', 'TELEGRAM_CHAT_ID', 'TELEGRAM_TOKEN']))
eq('F8 los inputs llegan por env:, nunca dentro de run:; la valoración siempre con AVISO=valorar',
   ('inputs.' in p_av['run'] + p_val['run'], p_av['env']['AVISO'], p_val['env']['AVISO'], p_val['env']['PASADA']),
   (False, '${{ inputs.aviso }}', 'valorar', '${{ inputs.pasada }}'))
eq('F9 corren el programa, con tope en los jobs y en los pasos, y sin artefactos',
   (p_av['run'], p_val['run'], all(bool(j.get('timeout-minutes')) and bool(j['steps'][-1].get('timeout-minutes'))
                                   for j in (j_av, j_val)), 'upload-artifact' in texto_wf),
   ('python -u escaner2_tcg_valorar.py', 'python -u escaner2_tcg_valorar.py', True, False))
eq('F10 el token del run, solo para leer el repo', wf['permissions'], {'contents': 'read'})
eq('F11 🔑 el workflow que encarga la lectura de la oficina es ESTE (mismo nombre en los dos lados)',
   os.path.basename(WORKFLOW), __import__('escaner2_tcg_disponibilidad').WORKFLOW_VALORAR)

# ── (G) La red con reloj: las cuentas valoran antes lo pendiente ──────────────────────────
cu = yaml.safe_load(open(CUENTAS, encoding='utf-8').read())
eq('G1 las cuentas siguen en el grupo escaner2-tcg, sin cancelar', cu['concurrency'],
   {'group': 'escaner2-tcg', 'cancel-in-progress': False})
pasos_cu = cu['jobs']['cuentas']['steps']
nombres = [p.get('run', '') for p in pasos_cu]
i_val = next((i for i, r in enumerate(nombres) if 'escaner2_tcg_valorar.py' in r), -1)
i_cue = next((i for i, r in enumerate(nombres) if 'escaner2_tcg_novedades_cuentas.py' in r), -1)
eq('G2 🔴 en el MISMO job, la valoración de lo pendiente va ANTES de las cuentas', 0 <= i_val < i_cue, True)
pv, pc = pasos_cu[i_val], pasos_cu[i_cue]
eq('G3 …solo en las cuentas sueltas, con AVISO=valorar, su tope y Keepa',
   (pv.get('if'), pv['env'].get('AVISO'), bool(pv.get('timeout-minutes')), 'KEEPA_API_KEY' in secretos(pv)),
   ("inputs.pasada == ''", 'valorar', True, True))
eq('G4 …y las cuentas corren aunque la valoración falle (no si se cancela)', pc.get('if'), '${{ !cancelled() }}')
eq('G5 el tope del job cabe la valoración y las cuentas',
   cu['jobs']['cuentas']['timeout-minutes'] >= pv['timeout-minutes'] + pc['timeout-minutes'], True)

print()
print('TODO OK' if not fallos else 'FALLOS: %d (%s)' % (len(fallos), ', '.join(fallos)))
sys.exit(1 if fallos else 0)
