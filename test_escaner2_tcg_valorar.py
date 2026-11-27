# -*- coding: utf-8 -*-
"""Banco de LA VALORACION DE LAS NOVEDADES DE TCG DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026):
escaner2_tcg_valorar.py, su workflow (escaner2-tcg-valorar.yml) y su red con reloj (escaner2-tcg-novedades-cuentas.yml).

SIN RED, SIN SECRETOS Y SIN BASE: una base de mentira en memoria (nov_pasada, nov_novedad y el cierre de la valoracion) y una
valoracion de mentira FIEL a la de verdad (escaner2_novedades.valorar_pasada, con su banco en test_escaner2_novedades.py):
cierra la fila de nov_pasada con 'hecha' o 'fallida' y valoracion_en = AHORA (como nov_cerrar_valoracion, en CADA cierre),
devuelve lo de la base con su motivo, ok=False si falla, y con una avalancha manda su Telegram «⚠️ Avalancha» (como
aviso_telegram). Las corridas se encadenan con su propio AHORA. 🔴 DATOS INVENTADOS (repo publico).

QUE PRUEBA:
  (A) valora lo pendiente de TCG: la pedida siempre, las demas sin cerrar si llevan mas de PENDIENTE_MIN_S, de la mas
      vieja a la mas nueva; ni las ya valoradas, ni las de seleccion fallida, ni las de otro proveedor; con su cifra para la
      avalancha y la llave de Keepa;
  (B) 🔴 LAS AVALANCHAS ANTES DE TOCAR KEEPA, tengan la edad que tengan: una avalancha recien seleccionada y aun no recogida
      cierra sus novedades antes de que otra corrida valore nada; su aviso sale UNA vez por pasada, encadenando corridas;
      una avalancha fallida no se reintenta (ni otro aviso); sin poder cerrar una avalancha, no se valora nada;
  (C) 🔴 LAS FALLIDAS: a la vista (fallida en la base, ROJO y nombrada) y reintentadas solo mientras su SELECCION tenga
      menos de RECOGER_FALLIDAS_H, aunque cada cierre renueve valoracion_en (corridas encadenadas);
  (V) 🔴 LO VIEJO: seleccionado hace mas de TOPE_PENDIENTE_H y sin valorar se cierra sin valorar, sus «pendiente» caducan con
      su motivo, y ni Keepa ni Telegram;
  (D) guardas: PASADA un uuid o nada; sin la base o sin Keepa, ROJO sin valorar nada;
  (E) 🔴 el registro no suelta el motivo de la base, ni un token, ni un EAN;
  (F) por estructura, el workflow: solo por dispatch (el reloj es cron-job.org); un job, en el grupo `escaner2-tcg` (el de
      las cuentas) sin cancelar; el input por env:; secretos solo en su paso; topes; sin artefactos;
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
T0 = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
AHORA = T0
ENV = {'SUPABASE_URL': 'https://base.invalid', 'SUPABASE_SERVICE_KEY': 'LLAVE-BASE-SECRETA',
       'KEEPA_API_KEY': 'LLAVE-KEEPA-SECRETA', 'TELEGRAM_TOKEN': 'TOKEN-TG', 'TELEGRAM_CHAT_ID': 'CHAT-TG',
       'GITHUB_RUN_ID': '555'}
MOTIVO_BASE = 'NO CUADRA: Failing row contains (8000000000017, 9.77)'
P = ['%08d-0000-4000-8000-000000000000' % i for i in range(10)]
AV = nv.AVALANCHA


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ── La base de mentira ────────────────────────────────────────────────────────────────────
class _Q:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.filtros, self.orden, self.lim, self.cambio = base, tabla, [], None, None, None

    def select(self, *_a, **_k):
        return self

    def update(self, d):
        self.cambio = d; return self

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
        if self.base.rota == self.tabla:
            raise RuntimeError('Failing row contains (8000000000017)')
        vivas = [f for f in self.base.t.get(self.tabla, []) if all(p(f) for p in self.filtros)]
        if self.cambio is not None:
            for f in vivas:
                f.update(self.cambio)
            self.base.eventos.append(('update', self.tabla, len(vivas)))
            return types.SimpleNamespace(data=[dict(f) for f in vivas])
        filas = [dict(f) for f in vivas]
        if self.orden:
            filas.sort(key=lambda f: str(f.get(self.orden[0])), reverse=self.orden[1])
        if self.lim is not None:
            filas = filas[:self.lim]
        return types.SimpleNamespace(data=filas)


class Base:
    def __init__(self, nov=(), novedades=()):
        self.t = {'nov_pasada': [dict(f) for f in nov], 'nov_novedad': [dict(f) for f in novedades]}
        self.eventos, self.rota = [], None

    def table(self, n):
        return _Q(self, n)

    def rpc(self, nombre, params):
        base = self

        class _L:
            def execute(self):
                assert nombre == 'nov_cerrar_valoracion', nombre
                base.eventos.append(('cerrar_valoracion', params['p_pasada'], params['p_datos']['estado']))
                for f in base.t['nov_pasada']:
                    if f['pasada_id'] == params['p_pasada']:
                        f.update(valoracion_estado=params['p_datos']['estado'], valoracion_en=AHORA.isoformat(),
                                 valoracion_motivo=params['p_datos'].get('motivo'))
                return types.SimpleNamespace(data={'estado': params['p_datos']['estado']})
        return _L()


def nov(pid, hace_s, estado='hecha', valoracion=None, proveedor='TCG', novedades=3, subidas=1, valorada_hace_s=None):
    return {'pasada_id': pid, 'proveedor': proveedor, 'estado': estado, 'valoracion_estado': valoracion,
            'valoracion_en': None if valorada_hace_s is None else (AHORA - timedelta(seconds=valorada_hace_s)).isoformat(),
            'creada_en': (AHORA - timedelta(seconds=hace_s)).isoformat(), 'n_novedades': novedades,
            'n_subidas_fuera': subidas}


def novedad(pid, n, estado='pendiente', proveedor='TCG'):
    return {'id': '%s-%d' % (pid[:8], n), 'pasada_id': pid, 'proveedor': proveedor, 'estado': estado}


telegramas = []


def post_tg(url, data, timeout):
    telegramas.append(data['text'])
    return types.SimpleNamespace(status_code=200)


class Valoracion:
    """valorar_pasada de mentira, FIEL a la de verdad (ver la cabecera). `fallan`: las pasadas cuya valoracion falla."""

    def __init__(self, base, fallan=()):
        self.base, self.fallan, self.llamadas = base, set(fallan), []

    def __call__(self, sb, pasada, keepa_llave=None, imprimir=None, run_id=None, novedades_pasada=None, env=None,
                 post=None, proveedor=None):
        self.llamadas.append((pasada, novedades_pasada, keepa_llave, proveedor, run_id))
        if (novedades_pasada or 0) > AV:
            nv.enviar_telegram('⚠️ Avalancha: %d cambios en TCG Funko — no se valora ninguna' % novedades_pasada, env=env,
                               post=post, imprimir=lambda *a, **k: None)
        else:
            self.base.eventos.append(('keepa', pasada))
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


def cerrar_de_mentira(base):
    def cerrar(sb, pid, n):
        base.eventos.append(('cerrar_avalancha', pid))
        return nv.cerrar_por_avalancha(sb, pid, n, proveedor='TCG')
    return cerrar


def correr(base, env=None, fallan=(), post=post_tg, ahora=None, val=None):
    global AHORA
    AHORA = ahora or AHORA
    val = val or Valoracion(base, fallan)
    salida = io.StringIO()
    codigo = None
    with contextlib.redirect_stdout(salida):
        try:
            codigo = prog.principal(env=dict(ENV, **(env or {})), sb=base, valorar_pasada=val, post=post, ahora=AHORA,
                                    cerrar_avalancha=cerrar_de_mentira(base))
        except SystemExit as ex:
            codigo = ex.code
    return codigo, salida.getvalue(), val


def limpio(nombre, registro):
    eq(nombre + ': el registro no suelta el motivo, tokens, llaves ni EAN',
       [p for p in ('403', 'NO CUADRA', 'Failing row', 'LLAVE-', 'TOKEN-TG', 'CHAT-TG', '8000000000017') if p in registro], [])


def estados(base, tabla='nov_pasada', clave='pasada_id', campo='valoracion_estado'):
    return {f[clave]: f.get(campo) for f in base.t[tabla]}


# ── (A) Qué se valora ─────────────────────────────────────────────────────────────────────
AHORA = T0
base = Base(nov=[nov(P[1], 3600, novedades=5, subidas=2),                 # se quedó atrás hace 1 h
                 nov(P[2], 30),                                           # la pedida a mano, de hace 30 s
                 nov(P[3], 120),                                          # otra de hace 2 min: la puede estar valorando su dueño
                 nov(P[4], 7200, valoracion='hecha', valorada_hace_s=7000),   # ya valorada
                 nov(P[5], 7200, estado='fallida'),                       # la selección falló: no hay nada que valorar
                 nov(P[6], 7200, proveedor='DBLINE')])                    # de otro proveedor
telegramas.clear()
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('A1 valora la que se quedó atrás y la pedida, de la más vieja a la más nueva; ni la de hace 2 min (su dueño), ni las '
   'valoradas, ni las de selección fallida, ni las de otro proveedor', [c[0] for c in val.llamadas], [P[1], P[2]])
eq('A2 …cada una con sus novedades para la avalancha (novedades − subidas fuera), la llave de Keepa, TCG y el run',
   [(c[1], c[2], c[3], c[4]) for c in val.llamadas],
   [(3, 'LLAVE-KEEPA-SECRETA', 'TCG', '555'), (2, 'LLAVE-KEEPA-SECRETA', 'TCG', '555')])
eq('A3 …VERDE, sin Telegram, y el registro lo cuenta, pasada a pasada, con su estado y sus cifras',
   (codigo, len(telegramas), 'pendientes 2 (la pedida sí)' in reg,
    '>>> VALORACION de la pasada %s (pendiente): hecha · novedades 12 · pendientes 0 · valoradas 4 · bien.' % P[2] in reg),
   (0, 0, True, True))
limpio('A4', reg)
eq('A5 el umbral de las ajenas son 5 min (la valoración en el acto de TCG tarda hasta 227 s medidos)', prog.PENDIENTE_MIN_S, 300)
base = Base(nov=[nov(P[3], prog.PENDIENTE_MIN_S + 1), nov(P[4], prog.PENDIENTE_MIN_S - 1)])
codigo, reg, val = correr(base)
eq('A6 sin pasada (el reloj o la red): solo lo pendiente de más de 5 min', [c[0] for c in val.llamadas], [P[3]])
base = Base(nov=[nov(P[2], 7200, valoracion='hecha', valorada_hace_s=7000)])
codigo, reg, val = correr(base, env={'PASADA': P[2]})
eq('A7 la pedida ya valorada (un relanzamiento): no se repite, VERDE y lo dice',
   (codigo, val.llamadas, 'la pedida no: ya valorada' in reg), (0, [], True))

# ── (B) Las avalanchas, antes de tocar Keepa, y su aviso una vez ──────────────────────────
AHORA = T0
base = Base(nov=[nov(P[1], 3600, novedades=3), nov(P[2], 30, novedades=AV + 51, subidas=1)],
            novedades=[novedad(P[2], i) for i in range(3)] + [novedad(P[1], 9)])
telegramas.clear()
codigo, reg, val = correr(base)
ev = [e for e in base.eventos if e[0] in ('cerrar_avalancha', 'keepa')]
eq('B1 🔴 una avalancha RECIÉN seleccionada (30 s, aún no toca recogerla) y una vieja normal: las novedades de la avalancha se '
   'cierran ANTES de que Keepa recorra la cola', ev, [('cerrar_avalancha', P[2]), ('keepa', P[1])])
eq('B2 …sus «pendiente» quedan «caducada» por avalancha (cerrar_por_avalancha de verdad), las de la otra no',
   ({f['id']: f['estado'] for f in base.t['nov_novedad']}),
   {'00000002-0': 'caducada', '00000002-1': 'caducada', '00000002-2': 'caducada', '00000001-9': 'pendiente'})
eq('B3 …la avalancha recién seleccionada no se valora aún (su cierre y su aviso, en la corrida siguiente): ni aviso',
   ([c[0] for c in val.llamadas], len(telegramas)), ([P[1]], 0))
codigo, reg, val = correr(base, ahora=T0 + timedelta(minutes=10))
eq('B4 🔴 la corrida siguiente (10 min después) cierra la valoración de la avalancha y manda su aviso, UNA vez',
   ([c[0] for c in val.llamadas], len(telegramas), estados(base)[P[2]]), ([P[2]], 1, 'hecha'))
codigo, reg, val = correr(base, ahora=T0 + timedelta(minutes=70))
eq('B5 🔴 y la otra (1 h después): ni la vuelve a valorar ni otro aviso', (val.llamadas, len(telegramas)), ([], 1))
AHORA = T0
base = Base(nov=[nov(P[1], 7200, novedades=AV + 1, subidas=0), nov(P[2], 3600, novedades=AV + 1, subidas=1),
                 nov(P[3], 600, novedades=4)])
codigo, reg, val = correr(base)
eq('B6 el límite es «más de» AVALANCHA (novedades − subidas): 101 lo es, 100 no; las avalanchas, primero',
   ([c[0] for c in val.llamadas], [e[1] for e in base.eventos if e[0] == 'cerrar_avalancha']), ([P[1], P[2], P[3]], [P[1]]))
AHORA = T0
base = Base(nov=[nov(P[2], 600, novedades=AV + 30, subidas=0, valoracion='fallida', valorada_hace_s=300)])
telegramas.clear()
codigo, reg, val = correr(base)
eq('B7 🔴 una avalancha que cerró «fallida»: sus novedades se cierran igual, pero ni se reintenta ni otro aviso',
   ([e for e in base.eventos if e[0] == 'cerrar_avalancha'], val.llamadas, len(telegramas)), ([('cerrar_avalancha', P[2])], [], 0))
base = Base(nov=[nov(P[1], 3600), nov(P[2], 30, novedades=AV + 10, subidas=0)])
base.rota = 'nov_novedad'
codigo, reg, val = correr(base)
eq('B8 🔴 si no se pueden cerrar las novedades de una avalancha, no se valora nada (Keepa las cogería): ROJO y dicho',
   (codigo, val.llamadas, 'TCG_AVALANCHA_SIN_CERRAR' in reg), (1, [], True))
limpio('B9', reg)

# ── (C) Las fallidas: a la vista y reintentadas un día desde la selección ─────────────────
AHORA = T0
base = Base(nov=[nov(P[1], 3600), nov(P[2], 5)])
codigo, reg, val = correr(base, env={'PASADA': P[2]}, fallan={P[1]})
eq('C1 🔴 una valoración que falla: ROJO, las demás siguen, y la que falló queda A LA VISTA (fallida en la base)',
   (codigo, [c[0] for c in val.llamadas], estados(base)), (1, [P[1], P[2]], {P[1]: 'fallida', P[2]: 'hecha'}))
eq('C2 …el registro la nombra, EN ROJO, y dice dónde está el motivo (sin el motivo)',
   ('>>> VALORACION de la pasada %s (pendiente): fallida · novedades 12 · pendientes 0 · valoradas 4 · EN ROJO (el motivo, en '
    'nov_pasada.valoracion_motivo).' % P[1] in reg), True)
limpio('C3', reg)
codigo, reg, val = correr(base, fallan={P[1]}, ahora=T0 + timedelta(hours=2))
eq('C4 🔴 la corrida siguiente la REINTENTA (y vuelve a fallar: su cierre renueva valoracion_en)',
   ([c[0] for c in val.llamadas], codigo, 'reintento de una fallida' in reg, estados(base, campo='valoracion_en')[P[1]]),
   ([P[1]], 1, True, (T0 + timedelta(hours=2)).isoformat()))
codigo, reg, val = correr(base, fallan={P[1]}, ahora=T0 + timedelta(hours=23))
eq('C5 …a las 23 h de su selección, otra vez', [c[0] for c in val.llamadas], [P[1]])
codigo, reg, val = correr(base, fallan={P[1]}, ahora=T0 + timedelta(hours=24))
eq('C6 🔴 pasadas 24 h DESDE LA SELECCIÓN ya no, aunque el último cierre sea de hace 1 h: el plazo no se renueva solo',
   (val.llamadas, codigo, estados(base)[P[1]]), ([], 0, 'fallida'))
eq('C7 los reintentos, un día', prog.RECOGER_FALLIDAS_H, 24)


class Revienta(Valoracion):
    def __call__(self, *a, **k):
        raise RuntimeError('Failing row contains (8000000000017, LLAVE-KEEPA-SECRETA)')


AHORA = T0
base = Base(nov=[nov(P[1], 3600)])
codigo, reg, _v = correr(base, val=Revienta(None))
eq('C8 una valoración que revienta (la de verdad no lanza): ROJO, sin cerrar (la recoge la siguiente) y dicho',
   (codigo, estados(base)[P[1]], 'sin cerrar (RuntimeError)' in reg), (1, None, True))
limpio('C9', reg)

# ── (V) Lo viejo, cerrado sin valorar ─────────────────────────────────────────────────────
AHORA = T0
base = Base(nov=[nov(P[1], prog.TOPE_PENDIENTE_H * 3600 + 60), nov(P[2], 3600)],
            novedades=[novedad(P[1], 1), novedad(P[1], 2), novedad(P[1], 3, estado='espera_keepa'), novedad(P[2], 4)])
telegramas.clear()
codigo, reg, val = correr(base)
eq('V1 🔴 seleccionada hace más de 24 h y sin valorar: se cierra «fallida» con su motivo, sin valorarla ni avisar',
   (estados(base)[P[1]], str(estados(base, campo='valoracion_motivo')[P[1]]).startswith('sin valorar a tiempo'),
    [c[0] for c in val.llamadas], len(telegramas)), ('fallida', True, [P[2]], 0))
eq('V2 …sus «pendiente» caducan con el motivo (no las que esperan a Keepa ni las de otra pasada)',
   {f['id']: f['estado'] for f in base.t['nov_novedad']},
   {'00000001-1': 'caducada', '00000001-2': 'caducada', '00000001-3': 'espera_keepa', '00000002-4': 'pendiente'})
eq('V3 …y lo cierra ANTES de valorar nada (Keepa no las ve)',
   [e[0] for e in base.eventos if e[0] in ('update', 'cerrar_valoracion', 'keepa')][:3], ['update', 'cerrar_valoracion', 'keepa'])
eq('V4 …el registro lo dice, sin motivo de la base', ('>>> SIN VALORAR A TIEMPO: la pasada %s' % P[1] in reg, codigo), (True, 0))
codigo, reg, val = correr(base, ahora=T0 + timedelta(hours=1))
eq('V5 y no se reintenta (cerró hace más de 24 h de su selección)', P[1] in [c[0] for c in val.llamadas], False)
eq('V6 el tope, un día', prog.TOPE_PENDIENTE_H, 24)

# ── (D) Guardas ───────────────────────────────────────────────────────────────────────────
AHORA = T0
for nombre, env in (('PASADA que no es un uuid', {'PASADA': "x'; drop table"}),
                    ('sin la base', {'SUPABASE_SERVICE_KEY': ''}), ('sin Keepa', {'KEEPA_API_KEY': ''})):
    base = Base(nov=[nov(P[1], 3600)])
    codigo, reg, val = correr(base, env=env)
    eq('D1 %s: ROJO sin valorar nada' % nombre, (codigo, val.llamadas, 'TCG_VALORAR_NO_EJECUTADO' in reg), (1, [], True))
codigo, reg, val = correr(Base(nov=[nov(P[2], 5)]), env={'PASADA': P[2].upper()})
eq('D3 el uuid en mayúsculas vale (se normaliza)', [c[0] for c in val.llamadas], [P[2]])

# ── (F) El workflow, por estructura ───────────────────────────────────────────────────────
texto_wf = open(WORKFLOW, encoding='utf-8').read()
wf = yaml.safe_load(texto_wf)
disparo = wf.get(True) or wf.get('on')
eq('F1 solo se lanza a mano (workflow_dispatch), sin reloj', sorted(disparo), ['workflow_dispatch'])
eq('F2 un solo input, la pasada (a mano)', sorted(disparo['workflow_dispatch']['inputs']), ['pasada'])
eq('F3 un job: la valoración', sorted(wf['jobs']), ['valorar'])
j_val = wf['jobs']['valorar']
eq('F4 🔴 en el grupo de las cuentas (escaner2-tcg) y sin cancelar la que corre; nada de grupo a nivel de workflow',
   (j_val.get('concurrency'), 'concurrency' in wf), ({'group': 'escaner2-tcg', 'cancel-in-progress': False}, False))


def secretos(paso):
    import re
    return sorted(set(re.findall(r'secrets\.([A-Z_]+)', yaml.safe_dump(paso))))


p_val = j_val['steps'][-1]
eq('F5 los secretos, solo en el último paso', [p.get('name') for p in j_val['steps'] if secretos(p)], [p_val['name']])
eq('F6 …y son los de la valoración', secretos(p_val),
   ['KEEPA_API_KEY', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL', 'TELEGRAM_CHAT_ID', 'TELEGRAM_TOKEN'])
eq('F7 el input llega por env:, nunca dentro de run:', ('inputs.' in p_val['run'], p_val['env']['PASADA']),
   (False, '${{ inputs.pasada }}'))
eq('F8 corre el programa, con tope en el job y en el paso, y sin artefactos',
   (p_val['run'], bool(j_val.get('timeout-minutes')) and bool(p_val.get('timeout-minutes')), 'upload-artifact' in texto_wf),
   ('python -u escaner2_tcg_valorar.py', True, False))
eq('F9 el token del run, solo para leer el repo', wf['permissions'], {'contents': 'read'})
eq('F10 🔑 el workflow que nombra la lectura de la oficina es ESTE (mismo nombre en los dos lados)',
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
eq('G3 …solo en las cuentas sueltas, con su tope y Keepa',
   (pv.get('if'), bool(pv.get('timeout-minutes')), 'KEEPA_API_KEY' in secretos(pv)), ("inputs.pasada == ''", True, True))
eq('G4 …y las cuentas corren aunque la valoración falle (no si se cancela)', pc.get('if'), '${{ !cancelled() }}')
eq('G5 el tope del job cabe la valoración y las cuentas',
   cu['jobs']['cuentas']['timeout-minutes'] >= pv['timeout-minutes'] + pc['timeout-minutes'], True)

print()
print('TODO OK' if not fallos else 'FALLOS: %d (%s)' % (len(fallos), ', '.join(fallos)))
sys.exit(1 if fallos else 0)
