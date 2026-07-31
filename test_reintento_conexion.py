# -*- coding: utf-8 -*-
# Prueba EJECUTABLE del reintento de la CONEXIÓN a Postgres (foto_comun.conectar_bd).
# Compilar no es ejecutar: aquí se corre la lógica de verdad con fallos simulados.
#   python test_reintento_conexion.py
import io, contextlib
import foto_comun as fc

fallos = 0
def chk(nombre, ok):
    global fallos
    print(('OK  ' if ok else 'XX  ') + nombre)
    if not ok:
        fallos += 1

RAPIDO = (0, 0, 0)  # 4 intentos, sin dormir de verdad (time.sleep(0))


def op_err(msg, pgcode=None):
    """Un psycopg2.OperationalError con el pgcode que queramos (los de connect: None si no
    llegamos al servidor; un SQLSTATE si el servidor respondió rechazando). `pgcode` es un
    descriptor de solo-lectura en la instancia real, así que se fija como atributo de CLASE
    en una subclase (sigue pasando el isinstance de OperationalError)."""
    cls = type('FakeOpErr', (fc.psycopg2.OperationalError,), {'pgcode': pgcode})
    return cls(msg)


# --- _es_transitorio_conexion: red SÍ, credenciales/base NO ---
chk('OperationalError sin pgcode (no llegó al servidor) → transitorio',
    fc._es_transitorio_conexion(op_err('connection to server at "pooler" failed: timeout expired')))
chk('clase 08 (08006 connection_failure) → transitorio',
    fc._es_transitorio_conexion(op_err('server closed the connection unexpectedly', pgcode='08006')))
chk('57P03 (cannot_connect_now) → transitorio',
    fc._es_transitorio_conexion(op_err('the database system is starting up', pgcode='57P03')))
chk('53300 (too_many_connections) → transitorio',
    fc._es_transitorio_conexion(op_err('too many clients already', pgcode='53300')))
chk('28P01 (password) → NO transitorio',
    not fc._es_transitorio_conexion(op_err('password authentication failed', pgcode='28P01')))
chk('3D000 (base inexistente) → NO transitorio',
    not fc._es_transitorio_conexion(op_err('database "x" does not exist', pgcode='3D000')))
chk('ValueError genérico → NO transitorio (cae en _es_transitorio)',
    not fc._es_transitorio_conexion(ValueError('cualquier cosa')))


# --- conectar_bd: se monkeypatchea psycopg2.connect ---
orig_connect = fc.psycopg2.connect

class FakeCon:
    pass

try:
    # 1) Éxito al 2º intento tras un transitorio → devuelve la conexión y lo GRITA.
    s1 = {'n': 0, 'kw': None}
    def connect_falla_una_vez(db_url, **kw):
        s1['n'] += 1
        s1['kw'] = kw
        if s1['n'] == 1:
            raise op_err('timeout expired')  # sin pgcode → transitorio
        return FakeCon()
    fc.psycopg2.connect = connect_falla_una_vez
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        con = fc.conectar_bd('postgres://x', esperas=RAPIDO)
    chk('éxito al 2º intento → devuelve la conexión', isinstance(con, FakeCon))
    chk('  · se reintentó una vez (2 llamadas)', s1['n'] == 2)
    chk('  · el log GRITA el éxito-tras-fallo ("intento 2 OK")', 'intento 2 OK' in buf.getvalue())
    chk('  · pasa connect_timeout por defecto (10)', s1['kw'].get('connect_timeout') == 10)

    # 2) Transitorio que persiste → aborta diciendo que fue la red, tras 4 intentos.
    s2 = {'n': 0}
    def connect_siempre_transitorio(db_url, **kw):
        s2['n'] += 1
        raise op_err('timeout expired')
    fc.psycopg2.connect = connect_siempre_transitorio
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fc.conectar_bd('postgres://x', esperas=RAPIDO)
        chk('transitorio persistente → aborta', False)
    except fc.Aborta as e:
        chk('transitorio persistente → aborta', True)
        chk('  · dice que NO pude conectar a Postgres', 'NO pude conectar a Postgres' in str(e))
        chk('  · agotó los 4 intentos', s2['n'] == 4)

    # 3) Credenciales (28P01, no transitorio) → aborta YA, sin reintentar.
    s3 = {'n': 0}
    def connect_password(db_url, **kw):
        s3['n'] += 1
        raise op_err('password authentication failed', pgcode='28P01')
    fc.psycopg2.connect = connect_password
    try:
        fc.conectar_bd('postgres://x', esperas=RAPIDO)
        chk('28P01 → aborta', False)
    except fc.Aborta as e:
        chk('28P01 → aborta', True)
        chk('  · dice que NO es un corte de red', 'NO es un corte de red' in str(e))
        chk('  · NO reintentó (1 sola llamada)', s3['n'] == 1)

    # 4) connect_timeout configurable llega a psycopg2.connect.
    s4 = {'kw': None}
    def connect_ok(db_url, **kw):
        s4['kw'] = kw
        return FakeCon()
    fc.psycopg2.connect = connect_ok
    fc.conectar_bd('postgres://x', esperas=RAPIDO, connect_timeout=3)
    chk('connect_timeout configurable llega a psycopg2.connect', s4['kw'].get('connect_timeout') == 3)
finally:
    fc.psycopg2.connect = orig_connect

print()
print('✅ TODO OK' if fallos == 0 else f'❌ {fallos} FALLOS')
raise SystemExit(1 if fallos else 0)
