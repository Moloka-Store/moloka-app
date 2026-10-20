# -*- coding: utf-8 -*-
"""Banco de escaner2_base.py: el reintento ante un corte breve de PostgREST (encargo D, 20-oct-2026).

SIN BASE, SIN SECRETOS Y CON EL SUPABASE-PY DE VERDAD: un PostgREST de mentira escucha en 127.0.0.1 (un hilo con
http.server), contesta lo que cada prueba le guiona (un 503 PGRST002, un 500, cortar la conexion sin responder...) y
apunta TODO lo que le llega (metodo, ruta, consulta, cabeceras y cuerpo). El cliente es el de `supabase==2.31.0`, el
mismo que corre en Actions: lo que se prueba es la pieza metida en su transporte, no un doble de ella. Las esperas no
duermen de verdad: `escaner2_base._dormir` y `_reloj` se cambian por un reloj de mentira.

  (A) La regla: PGRST002 dos veces y luego bien · PGRST002 hasta el tope · PGRST001 · otro 5xx y otro 503 sin
      reintento · 4xx sin reintento · escritura con fallo de red sin reintento (POST, PATCH, DELETE, rpc) · lectura
      con fallo de red con reintento · el tope es del run, no de cada llamada · sigue puesto si supabase rehace PostgREST.
  (B) Con todo bien, las llamadas son LAS MISMAS que con `create_client`: mismas peticiones al byte, mismo resultado;
      y agotado el tope, el MISMO error que hoy.
  (C) Los programas: `_cerrar_fallida` y `rescatar()` de HEO usan el reintento; los 26 programas compilan, importan y
      salen con el cliente con reintento (los que lo crean dentro de `principal`, por su `--rescate` de verdad contra el
      PostgREST de mentira); y el censo: ningun escaner2_*.py llama a `create_client` directo.

  python test_escaner2_base.py
"""
import ast
import glob
import http.server
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import threading
import types
from contextlib import redirect_stdout
from io import StringIO

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import escaner2_base as eb  # noqa: E402
from supabase import create_client  # noqa: E402  (el de verdad, para comparar)
from postgrest.exceptions import APIError  # noqa: E402
import httpx  # noqa: E402

fallos = 0


def chk(nombre, ok, detalle=''):
    global fallos
    print(('OK  ' if ok else 'XX  ') + nombre + ('' if ok or not detalle else f'  ->  {detalle}'))
    if not ok:
        fallos += 1


# ── El PostgREST de mentira ─────────────────────────────────────────────────────────────────────────────────────────
class Guion:
    """Lo que contesta el servidor, peticion a peticion; agotado el guion, `por_defecto`. Y lo que le llego."""

    def __init__(self):
        self.pasos, self.llegadas, self.por_defecto = [], [], ('json', 200, [])

    def poner(self, *pasos, por_defecto=('json', 200, [])):
        self.pasos, self.llegadas, self.por_defecto = list(pasos), [], por_defecto


GUION = Guion()
P002 = ('json', 503, {'code': 'PGRST002', 'details': None, 'hint': None,
                      'message': 'Could not query the database for the schema cache. Retrying.'})
P001 = ('json', 503, {'code': 'PGRST001', 'details': None, 'hint': None,
                      'message': 'Could not connect with the database due to an internal error.'})
CORTAR = ('cortar',)


class _Manejador(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _atender(self):
        largo = int(self.headers.get('Content-Length') or 0)
        cuerpo = self.rfile.read(largo) if largo else b''
        cab = {k.lower(): v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')}
        GUION.llegadas.append((self.command, self.path, tuple(sorted(cab.items())), cuerpo))
        paso = GUION.pasos.pop(0) if GUION.pasos else GUION.por_defecto
        if paso[0] == 'cortar':
            self.close_connection = True
            self.connection.close()             # sin responder nada: fallo de red sin respuesta
            return
        _, estado, dato = paso
        salida = b'' if dato is None else json.dumps(dato).encode()
        self.send_response(estado)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(salida)))
        self.end_headers()
        self.wfile.write(salida)

    do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = _atender


SERVIDOR = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Manejador)
threading.Thread(target=SERVIDOR.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d' % SERVIDOR.server_address[1]
LLAVE = 'llave-de-mentira'


# ── El reloj de mentira ─────────────────────────────────────────────────────────────────────────────────────────────
class Reloj:
    def __init__(self):
        self.t, self.esperas = 0.0, []

    def dormir(self, s):
        self.esperas.append(s)
        self.t += s

    def ahora(self):
        return self.t


def nuevo_run():
    """Un proceso nuevo: tope entero y reloj a cero."""
    r = Reloj()
    eb._dormir, eb._reloj = r.dormir, r.ahora
    eb.TOPE = eb._Tope(eb.TOPE_SEGUNDOS)
    return r


def con_log(fn):
    buf = StringIO()
    with redirect_stdout(buf):
        try:
            return fn(), None, buf.getvalue()
        except Exception as ex:  # noqa: BLE001
            return None, ex, buf.getvalue()


def lineas(log, marca):
    return [x for x in log.splitlines() if x.startswith(marca + ':')]


# ═════════════════════════════════════════ (A) LA REGLA ═════════════════════════════════════════════════════════════
# 1 · PGRST002 dos veces y luego bien (la subida de disp_lectura del run 39419090368).
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(P002, P002, ('json', 201, [{'id': 1}, {'id': 2}]))
filas = [{'pasada_id': 'p', 'ean': '1'}, {'pasada_id': 'p', 'ean': '2'}]
res, ex, log = con_log(lambda: sb.table('disp_lectura').insert(filas).execute())
chk('PGRST002 ×2 y bien: la inserción sale bien', ex is None and res.data == [{'id': 1}, {'id': 2}], repr(ex))
chk('PGRST002 ×2 y bien: tres peticiones, las tres IGUALES (mismo método, ruta, cabeceras y cuerpo)',
    len(GUION.llegadas) == 3 and len(set(GUION.llegadas)) == 1, len(GUION.llegadas))
chk('PGRST002 ×2 y bien: el cuerpo que llega es el de las filas', json.loads(GUION.llegadas[0][3]) == filas)
chk('PGRST002 ×2 y bien: esperas 5 y 10 s', r.esperas == [5, 10], r.esperas)
chk('PGRST002 ×2 y bien: dos líneas REINTENTO_BASE, con método, tabla y código',
    len(lineas(log, 'REINTENTO_BASE')) == 2 and all('POST disp_lectura' in x and 'PGRST002' in x
                                                    for x in lineas(log, 'REINTENTO_BASE')), log)
chk('PGRST002 ×2 y bien: la línea no lleva la consulta ni el cuerpo (repo público)',
    '?' not in log and 'ean' not in log, log)

# 2 · PGRST002 hasta el tope: sale el MISMO error que hoy.
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(por_defecto=P002)
res, ex, log = con_log(lambda: sb.table('disp_lectura').insert(filas).execute())
chk('PGRST002 sin fin: acaba en APIError PGRST002, como hoy', isinstance(ex, APIError) and ex.code == 'PGRST002', repr(ex))
chk('PGRST002 sin fin: esperas crecientes hasta el tope de 240 s (5,10,20, 30×6 y la última recortada a 25)',
    r.esperas == [5, 10, 20, 30, 30, 30, 30, 30, 30, 25] and sum(r.esperas) == eb.TOPE_SEGUNDOS, r.esperas)
chk('PGRST002 sin fin: 11 peticiones (la primera + 10 reintentos)', len(GUION.llegadas) == 11, len(GUION.llegadas))
chk('PGRST002 sin fin: una línea REINTENTO_BASE_AGOTADO', len(lineas(log, 'REINTENTO_BASE_AGOTADO')) == 1, log)
# … y el tope es del RUN: la siguiente llamada (el _cerrar_fallida) ya no espera.
GUION.poner(por_defecto=P002)
res, ex, log = con_log(lambda: sb.table('disp_lectura').delete().eq('pasada_id', 'p').execute())
chk('tope agotado: la llamada siguiente del mismo run sale al primer intento, sin esperar',
    isinstance(ex, APIError) and len(GUION.llegadas) == 1 and sum(r.esperas) == eb.TOPE_SEGUNDOS and len(r.esperas) == 10,
    len(GUION.llegadas))

# 3 · El tope se comparte: lo gastado en una llamada se descuenta en la siguiente (y cuenta lo que tardan los intentos).
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(P002, P002, P002, P002, P002, ('json', 200, []))      # 5+10+20+30+30 = 95 s
con_log(lambda: sb.table('disp_pasada').select('id').execute())
GUION.poner(por_defecto=P002)
res, ex, log = con_log(lambda: sb.table('disp_pasada').select('id').execute())
chk('tope compartido: la segunda llamada solo tiene lo que queda (240 - 95 = 145 s)',
    sum(r.esperas[5:]) == 145 and isinstance(ex, APIError), (r.esperas, eb.TOPE.gastado))

# 4 · PGRST001 (no pudo conectar con la base): también se reintenta.
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(P001, ('json', 200, [{'id': 'x'}]))
res, ex, log = con_log(lambda: sb.rpc('disp_aplicar_pasada', {'p_pasada': 'x'}).execute())
chk('PGRST001 en una rpc (escritura): se reintenta y sale bien', ex is None and len(GUION.llegadas) == 2
    and r.esperas == [5] and GUION.llegadas[0] == GUION.llegadas[1], (repr(ex), len(GUION.llegadas)))

# 5 · Otro 5xx, otro 503 y los 4xx: SIN reintento, el mismo error que hoy.
for nombre, paso in (
        ('500', ('json', 500, {'code': 'XX000', 'message': 'boom', 'details': None, 'hint': None})),
        ('502', ('json', 502, {'message': 'Bad Gateway'})),
        ('504', ('json', 504, {'message': 'Gateway Timeout'})),
        ('503 PGRST000', ('json', 503, {'code': 'PGRST000', 'message': 'db down', 'details': None, 'hint': None})),
        ('503 sin cuerpo JSON', ('json', 503, None)),
        ('400', ('json', 400, {'code': '22P02', 'message': 'invalid input', 'details': None, 'hint': None})),
        ('409', ('json', 409, {'code': '23505', 'message': 'duplicate key', 'details': None, 'hint': None}))):
    r = nuevo_run()
    sb = eb.cliente(URL, LLAVE)
    GUION.poner(paso, ('json', 201, [{'id': 1}]))
    res, ex, log = con_log(lambda: sb.table('disp_lectura').insert(filas).execute())
    GUION.poner(paso)
    sb0 = create_client(URL, LLAVE)
    _, ex0, _ = con_log(lambda: sb0.table('disp_lectura').insert(filas).execute())
    chk(f'{nombre}: sin reintento (una petición, ninguna espera, sin línea)',
        len(GUION.llegadas) == 1 and r.esperas == [] and 'REINTENTO_BASE' not in log, (len(GUION.llegadas), r.esperas))
    chk(f'{nombre}: el mismo error que con create_client',
        ex is not None and type(ex) is type(ex0) and str(ex) == str(ex0), (repr(ex), repr(ex0)))

# 6 · Escritura con fallo de red: NO se reintenta (puede haberse ejecutado).
for nombre, llamada in (
        ('POST insert', lambda s: s.table('disp_lectura').insert(filas).execute()),
        ('PATCH update', lambda s: s.table('disp_pasada').update({'estado': 'fallida'}).eq('id', 'p').execute()),
        ('DELETE', lambda s: s.table('disp_lectura').delete().eq('pasada_id', 'p').execute()),
        ('POST upsert', lambda s: s.table('nov_pasada').upsert({'pasada_id': 'p'}, on_conflict='pasada_id').execute()),
        ('POST rpc', lambda s: s.rpc('disp_aplicar_pasada', {'p_pasada': 'p'}).execute())):
    r = nuevo_run()
    sb = eb.cliente(URL, LLAVE)
    GUION.poner(CORTAR, ('json', 200, []))
    res, ex, log = con_log(lambda: llamada(sb))
    chk(f'escritura con fallo de red ({nombre}): sale el error de red, sin reintento',
        isinstance(ex, httpx.TransportError) and len(GUION.llegadas) == 1 and r.esperas == [] and 'REINTENTO' not in log,
        (repr(ex), len(GUION.llegadas)))

# 7 · Lectura con fallo de red: SÍ se reintenta.
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(CORTAR, CORTAR, ('json', 200, [{'id': 'p1'}]))
res, ex, log = con_log(lambda: sb.table('disp_pasada').select('id').eq('run_id', 7).eq('estado', 'leyendo').execute())
chk('lectura con fallo de red ×2: se reintenta y sale bien', ex is None and res.data == [{'id': 'p1'}]
    and len(GUION.llegadas) == 3 and r.esperas == [5, 10], (repr(ex), len(GUION.llegadas), r.esperas))
chk('lectura con fallo de red: las líneas dicen «fallo de red sin respuesta»',
    len(lineas(log, 'REINTENTO_BASE')) == 2 and all('GET disp_pasada' in x and 'fallo de red' in x
                                                    for x in lineas(log, 'REINTENTO_BASE')), log)
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
GUION.poner(por_defecto=CORTAR)
res, ex, log = con_log(lambda: sb.table('disp_pasada').select('id').execute())
chk('lectura con fallo de red sin fin: agotado el tope, sale el error de red de siempre',
    isinstance(ex, httpx.TransportError) and sum(r.esperas) == eb.TOPE_SEGUNDOS
    and len(lineas(log, 'REINTENTO_BASE_AGOTADO')) == 1, (repr(ex), r.esperas))

# 8 · El tope cuenta lo que tardan los intentos fallidos (un tope de tiempo de 120 s se come medio tope).
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)


class _Lento(httpx.BaseTransport):
    """Un intento que tarda 100 s de reloj y no responde."""

    def handle_request(self, request):
        r.t += 100
        raise httpx.ReadTimeout('lento', request=request)


sb.postgrest.session._transport.interior = _Lento()
res, ex, log = con_log(lambda: sb.table('disp_pasada').select('id').execute())
chk('el tope cuenta la duración de los intentos: 100 + 5 + 100 + 10 + 100 → para ahí (315 s de reloj; contando solo las esperas serían 1.340 s, 22 min)',
    isinstance(ex, httpx.ReadTimeout) and r.esperas == [5, 10] and r.t == 315, (r.esperas, r.t))

# 9 · Sigue puesto si supabase rehace su PostgREST (lo hace al cambiar la sesión).
r = nuevo_run()
sb = eb.cliente(URL, LLAVE)
sb.postgrest                                    # se crea
sb._postgrest = None                            # como hace _listen_to_auth_events
GUION.poner(P002, ('json', 200, []))
res, ex, log = con_log(lambda: sb.table('disp_pasada').select('id').execute())
chk('PostgREST rehecho: sigue reintentando', ex is None and len(GUION.llegadas) == 2 and r.esperas == [5])
chk('el transporte es el del reintento y envuelve al de httpx',
    isinstance(sb.postgrest.session._transport, eb._clase_reintento())
    and isinstance(sb.postgrest.session._transport.interior, httpx.HTTPTransport))

# 10 · Un doble de los bancos pasa tal cual; y si supabase cambia sus piezas, cliente() LANZA.
guardado = sys.modules['supabase']
falso = types.ModuleType('supabase')
doble = object()
falso.create_client = lambda url, llave: doble
sys.modules['supabase'] = falso
try:
    chk('con un supabase de mentira, cliente() devuelve el doble tal cual', eb.cliente(URL, LLAVE) is doble)
finally:
    sys.modules['supabase'] = guardado
sb_raro = create_client(URL, LLAVE)
sb_raro._init_postgrest_client = None
original = guardado.create_client
guardado.create_client = lambda url, llave: sb_raro
try:
    _, ex, _ = con_log(lambda: eb.cliente(URL, LLAVE))
finally:
    guardado.create_client = original
chk('si supabase ya no tiene _init_postgrest_client, cliente() lanza (no da un cliente sin reintento)',
    isinstance(ex, RuntimeError) and 'sin reintento' in str(ex), repr(ex))
pg_raro = types.SimpleNamespace(session=object())
_, ex, _ = con_log(lambda: eb._poner_reintento(pg_raro, eb.TOPE))
chk('si la sesión de PostgREST no es un httpx.Client, lanza', isinstance(ex, RuntimeError), repr(ex))


# ═════════════════════════════ (B) CON TODO BIEN, LAS MISMAS LLAMADAS Y EL MISMO RESULTADO ═════════════════════════
def tanda(s):
    """Lo que hacen los programas: abrir pasada, leer, subir en lote, actualizar, borrar, upsert, rpc, contar."""
    return [
        s.table('disp_pasada').insert({'proveedor': 'HEO', 'estado': 'leyendo', 'run_id': 1}).execute().data,
        s.table('disp_parametros').select('tolerancia_endpoint').eq('proveedor', 'HEO').execute().data,
        s.table('disp_lectura').insert([{'pasada_id': 'p', 'ean': str(i)} for i in range(3)]).execute().data,
        s.table('disp_pasada').update({'n_leidas': 3}).eq('id', 'p').execute().data,
        s.table('disp_lectura').delete().eq('pasada_id', 'p').execute().data,
        s.table('nov_pasada').upsert({'pasada_id': 'p', 'estado': 'fallida'}, on_conflict='pasada_id',
                                     ignore_duplicates=True).execute().data,
        s.rpc('disp_aplicar_pasada', {'p_pasada': 'p'}).execute().data,
        s.table('disp_pasada').select('*', count='exact').eq('id', 'p').execute().count,
    ]


respuestas = [('json', 201, [{'id': 'p'}]), ('json', 200, [{'tolerancia_endpoint': 10}]),
              ('json', 201, [{'id': 1}, {'id': 2}, {'id': 3}]), ('json', 200, [{'id': 'p', 'n_leidas': 3}]),
              ('json', 200, []), ('json', 201, []), ('json', 200, {'estado': 'aplicada'}), ('json', 200, [{'id': 'p'}])]
nuevo_run()
GUION.poner(*respuestas)
antes = tanda(create_client(URL, LLAVE))
llegadas_antes = list(GUION.llegadas)
r = nuevo_run()
GUION.poner(*respuestas)
res, ex, log = con_log(lambda: tanda(eb.cliente(URL, LLAVE)))
chk('todo bien: el MISMO resultado que con create_client', ex is None and res == antes, (repr(ex), res, antes))
chk('todo bien: las MISMAS peticiones, al byte (método, ruta y consulta, cabeceras, cuerpo) y en el mismo orden',
    GUION.llegadas == llegadas_antes and len(llegadas_antes) == 8, (len(GUION.llegadas), len(llegadas_antes)))
chk('todo bien: ni una espera ni una línea de reintento', r.esperas == [] and log == '', (r.esperas, log))


# ═════════════════════════════════════════ (C) LOS PROGRAMAS ════════════════════════════════════════════════════════
# Los 26 programas del escáner 2 que hablan con la base (20-oct-2026). Un programa nuevo que hable con la base usa
# escaner2_base.cliente; el censo de abajo lo vigila sin tener que añadirlo aquí.
VEINTISEIS = sorted('''
escaner2_bems_barrido escaner2_bems_cruce escaner2_bems_disponibilidad escaner2_dbline_barrido escaner2_dbline_cruce
escaner2_dbline_disponibilidad escaner2_dbline_novedades_cuentas escaner2_factura_nube escaner2_heo_barrido
escaner2_heo_cruce escaner2_heo_disponibilidad escaner2_heo_novedades_cuentas escaner2_ociostock_barrido
escaner2_ociostock_cruce escaner2_ociostock_disponibilidad escaner2_ociostock_novedades_cuentas escaner2_osma_barrido
escaner2_osma_cruce escaner2_osma_disponibilidad escaner2_rescate escaner2_tcg_barrido escaner2_tcg_cruce
escaner2_tcg_disponibilidad escaner2_tcg_novedades_cuentas escaner2_zentrada_barrido escaner2_zentrada_cruce'''.split())
DENTRO_DE_PRINCIPAL = ('escaner2_bems_disponibilidad', 'escaner2_dbline_disponibilidad', 'escaner2_ociostock_disponibilidad',
                       'escaner2_osma_disponibilidad', 'escaner2_tcg_disponibilidad')
chk('son 26', len(VEINTISEIS) == 26 and len(set(VEINTISEIS)) == 26)


def _usos(arbol):
    """(importa create_client de supabase o lo nombra, llamadas a `cliente`, importa cliente de escaner2_base)."""
    directo = llamadas = importa = 0
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split('.')[0] == 'supabase':
            directo += any(a.name == 'create_client' for a in n.names)
        elif isinstance(n, (ast.Name, ast.Attribute)) and (getattr(n, 'id', None) or getattr(n, 'attr', None)) == 'create_client':
            directo += 1
        if isinstance(n, ast.ImportFrom) and n.module == 'escaner2_base':
            importa += any(a.name == 'cliente' for a in n.names)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'cliente':
            llamadas += 1
    return directo, llamadas, importa


# El censo, por estructura (ast), sobre TODOS los escaner2_*.py del repo.
todos = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(AQUI, 'escaner2_*.py')))
usan, directos = [], []
for nombre in todos:
    if nombre == 'escaner2_base':
        continue
    with open(os.path.join(AQUI, nombre + '.py'), encoding='utf-8') as f:
        d, ll, imp = _usos(ast.parse(f.read()))
    if d:
        directos.append(nombre)
    if ll or imp:
        usan.append(nombre)
        chk(f'{nombre}: importa cliente de escaner2_base y lo llama una vez', imp == 1 and ll == 1, (imp, ll))
chk('CENSO: ningún escaner2_*.py llama a create_client de supabase directo (solo escaner2_base)', directos == [], directos)
chk('los 26 usan escaner2_base.cliente, y nadie más (hoy)', usan == VEINTISEIS, sorted(set(usan) ^ set(VEINTISEIS)))
with open(os.path.join(AQUI, 'escaner2_base.py'), encoding='utf-8') as f:
    chk('escaner2_base no importa supabase al cargar (los bancos lo cambian por un doble después)',
        not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.parse(f.read()).body
                if 'supabase' in ast.dump(n)))

# Compilan los 26 (y el módulo).
for nombre in VEINTISEIS + ['escaner2_base']:
    try:
        py_compile.compile(os.path.join(AQUI, nombre + '.py'), cfile=os.path.join(tempfile.gettempdir(), nombre + '.pyc'),
                           doraise=True)
        ok = True
    except py_compile.PyCompileError as ex:
        ok = repr(ex)
    chk(f'compila: {nombre}', ok is True, ok)

# Arrancan los 26, cada uno en su proceso, con el supabase de verdad apuntando al PostgREST de mentira.
ENTORNO = dict(os.environ, SUPABASE_URL=URL, SUPABASE_SERVICE_KEY=LLAVE, GITHUB_RUN_ID='4242', PASADA='00000000-0000-4000-8000-000000000000',
               HEO_USER='u', HEO_PASS='p', DBLINE_USER='u', DBLINE_PASS='p', OSMA_USER='u', OSMA_PASS='p', TCG_USER='u',
               TCG_PASS='p', OCIOSTOCK_FEED_URL='http://127.0.0.1:9/x', KEEPA_API_KEY='k', PYTHONIOENCODING='utf-8',
               PYTHONPATH=AQUI + os.pathsep + os.environ.get('PYTHONPATH', ''))
for k in ('TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'):
    ENTORNO.pop(k, None)

SONDA_IMPORTA = r'''
import importlib, sys, escaner2_base as eb
sys.argv = [sys.argv[1] + '.py'] + sys.argv[2:]
m = importlib.import_module(sys.argv[0][:-3])
sb = getattr(m, 'sb', None)
pg = sb.postgrest
print('ARRANCA', type(sb).__module__, isinstance(pg.session._transport, eb._clase_reintento()))
'''
SONDA_RESCATE = r'''
import runpy, sys, escaner2_base as eb
crear = eb.cliente
vistos = []
def espia(*a, **k):
    sb = crear(*a, **k); vistos.append(sb); return sb
eb.cliente = espia
nombre = sys.argv[1]
sys.argv = [nombre + '.py'] + sys.argv[2:]
try:
    runpy.run_path(nombre + '.py', run_name='__main__')
except SystemExit as s:
    codigo = s.code
else:
    codigo = 0
sb = vistos[0]
print('ARRANCA', type(sb).__module__, isinstance(sb.postgrest.session._transport, eb._clase_reintento()), 'salida', codigo)
'''


def arrancar(sonda, nombre, *argv):
    GUION.poner(por_defecto=('json', 200, []))
    p = subprocess.run([sys.executable, '-c', sonda, nombre, *argv], cwd=AQUI, env=ENTORNO, capture_output=True,
                       text=True, encoding='utf-8', timeout=120)
    return p.returncode, p.stdout + p.stderr, list(GUION.llegadas)


for nombre in VEINTISEIS:
    if nombre in DENTRO_DE_PRINCIPAL:
        rc, salida, llegadas = arrancar(SONDA_RESCATE, nombre, '--rescate')
        ok = rc == 0 and 'ARRANCA supabase._sync.client True salida 0' in salida
        chk(f'arranca: {nombre} --rescate (cliente de verdad con reintento, rescate contra la base de mentira)',
            ok and any(x[0] == 'GET' and '/rest/v1/disp_pasada' in x[1] for x in llegadas), salida[-600:])
    elif nombre == 'escaner2_rescate':
        for que, tabla in (('pasada', 'escaner2_pasada'), ('cruce', 'escaner2_cruce')):
            rc, salida, llegadas = arrancar(SONDA_RESCATE, nombre, que)
            chk(f'arranca: escaner2_rescate.py {que} (y marca su tabla por PATCH)',
                rc == 0 and 'ARRANCA supabase._sync.client True salida 0' in salida
                and [x[0] for x in llegadas] == ['PATCH'] and f'/rest/v1/{tabla}?' in llegadas[0][1], salida[-600:])
    else:
        argv = {'escaner2_heo_disponibilidad': ['--rescate'],
                'escaner2_factura_nube': ['--ejecucion', '00000000-0000-4000-8000-000000000000']}.get(nombre, [])
        rc, salida, llegadas = arrancar(SONDA_IMPORTA, nombre, *argv)
        chk(f'arranca: {nombre} (importa; su sb es el de verdad, con reintento; no llama a la base al cargar)',
            rc == 0 and 'ARRANCA supabase._sync.client True' in salida and llegadas == [], salida[-600:])

# _cerrar_fallida y rescatar() de HEO: el rescate del run 39419090368, con la base cortándose a ratos.
ENTORNO_HEO = {'SUPABASE_URL': URL, 'SUPABASE_SERVICE_KEY': LLAVE, 'GITHUB_RUN_ID': '39419090368'}
viejo_env, viejo_argv = {k: os.environ.get(k) for k in ENTORNO_HEO}, sys.argv
os.environ.update(ENTORNO_HEO)
sys.argv = ['escaner2_heo_disponibilidad.py', '--rescate']
try:
    sys.modules.pop('escaner2_heo_disponibilidad', None)
    import escaner2_heo_disponibilidad as heo  # noqa: E402
finally:
    sys.argv = viejo_argv
    for k, v in viejo_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
r = nuevo_run()
GUION.poner(P002, ('json', 200, [{'id': '14291e8e'}]),           # rescatar(): el select
            P002, P002, ('json', 204, None),                      # _cerrar_fallida: el delete de disp_lectura
            P001, ('json', 200, [{'id': '14291e8e'}]))            #                 y el update de disp_pasada
res, ex, log = con_log(heo.rescatar)
metodos = [x[0] for x in GUION.llegadas]
chk('HEO rescatar(): con PGRST002/001 por medio, el select, el delete y el update salen',
    ex is None and metodos == ['GET', 'GET', 'DELETE', 'DELETE', 'DELETE', 'PATCH', 'PATCH'], (repr(ex), metodos))
chk('HEO rescatar(): 4 reintentos y la pasada pasa a fallida',
    len(lineas(log, 'REINTENTO_BASE')) == 4 and "1 pasada(s) de este run pasan de 'leyendo' a 'fallida'" in log
    and json.loads(GUION.llegadas[-1][3])['estado'] == 'fallida', log)
chk('HEO _cerrar_fallida: borra SOLO lo de su pasada y cierra SOLO si sigue leyendo',
    'pasada_id=eq.14291e8e' in GUION.llegadas[2][1] and 'estado=eq.leyendo' in GUION.llegadas[-1][1]
    and 'id=eq.14291e8e' in GUION.llegadas[-1][1], [x[1] for x in GUION.llegadas])

SERVIDOR.shutdown()
print()
print('test_escaner2_base: %s' % ('TODO EN VERDE' if not fallos else '%d FALLO(S)' % fallos))
sys.exit(1 if fallos else 0)
