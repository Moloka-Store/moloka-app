# -*- coding: utf-8 -*-
# Prueba EJECUTABLE del reintento de lecturas de Storage (foto_comun). Compilar no es
# ejecutar: aquí se corre la lógica de verdad con fallos simulados.  python test_reintento_storage.py
import foto_comun as fc

fallos = 0
def chk(nombre, ok):
    global fallos
    print(('OK  ' if ok else 'XX  ') + nombre)
    if not ok:
        fallos += 1

RAPIDO = (0, 0, 0)  # 4 intentos, sin dormir de verdad (time.sleep(0))


class ErrHTTP(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# --- _es_transitorio: SOLO transitorios (red / 5xx); 404/403 NO ---
chk('ConnectionResetError → transitorio', fc._es_transitorio(ConnectionResetError('reset by peer')))
chk('TimeoutError → transitorio', fc._es_transitorio(TimeoutError('timed out')))
chk('BrokenPipeError → transitorio', fc._es_transitorio(BrokenPipeError('broken pipe')))
chk('mensaje 503 → transitorio', fc._es_transitorio(Exception('Storage devolvió 503 Service Unavailable')))
chk('status=500 (atributo) → transitorio', fc._es_transitorio(ErrHTTP('x', status=500)))
chk('mensaje "Connection reset by peer" → transitorio', fc._es_transitorio(Exception('[Errno 104] Connection reset by peer')))
chk('404 (mensaje) → NO transitorio', not fc._es_transitorio(Exception('404: Object not found')))
chk('403 (status) → NO transitorio', not fc._es_transitorio(ErrHTTP('forbidden', status=403)))
chk('ValueError genérico → NO transitorio', not fc._es_transitorio(ValueError('cualquier cosa')))
chk('400 → NO transitorio', not fc._es_transitorio(ErrHTTP('bad request', status=400)))


# --- _leer_con_reintentos ---
# 1) Éxito al 2º intento tras un transitorio → devuelve el valor.
n1 = {'n': 0}
def falla_una_vez():
    n1['n'] += 1
    if n1['n'] == 1:
        raise ConnectionResetError('[Errno 104] Connection reset by peer')
    return ['fichero.txt']
r = fc._leer_con_reintentos('listar prueba', falla_una_vez, esperas=RAPIDO)
chk('éxito al 2º intento → devuelve el valor', r == ['fichero.txt'])
chk('  · se reintentó una vez (2 llamadas)', n1['n'] == 2)

# 2) Transitorio que persiste → aborta diciendo que fue la red.
n2 = {'n': 0}
def siempre_transitorio():
    n2['n'] += 1
    raise ConnectionResetError('connection reset by peer')
try:
    fc._leer_con_reintentos('descargar X', siempre_transitorio, esperas=RAPIDO)
    chk('transitorio persistente → aborta', False)
except fc.Aborta as e:
    chk('transitorio persistente → aborta', True)
    chk('  · dice que no pude hablar con Storage', 'NO pude hablar con Storage' in str(e))
    chk('  · agotó los 4 intentos (3 esperas)', n2['n'] == 4)

# 3) 404 (no transitorio) → aborta YA, sin reintentar.
n3 = {'n': 0}
def fichero_ausente():
    n3['n'] += 1
    raise ErrHTTP('404: objeto no encontrado', status=404)
try:
    fc._leer_con_reintentos('descargar Y', fichero_ausente, esperas=RAPIDO)
    chk('404 → aborta', False)
except fc.Aborta as e:
    chk('404 → aborta', True)
    chk('  · dice que NO es transitorio', 'NO es transitorio' in str(e))
    chk('  · NO reintentó (1 sola llamada)', n3['n'] == 1)

# 4) Éxito-tras-fallo se GRITA en el log (punto 🔒 de Fernando).
import io, contextlib
n4 = {'n': 0}
def falla_dos_veces():
    n4['n'] += 1
    if n4['n'] <= 2:
        raise TimeoutError('read timeout')
    return b'bytes'
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r4 = fc._leer_con_reintentos('descargar Z', falla_dos_veces, esperas=RAPIDO)
salida = buf.getvalue()
chk('éxito tras 2 fallos → devuelve', r4 == b'bytes')
chk('  · el log GRITA el éxito-tras-fallo ("intento 3 OK")', 'intento 3 OK' in salida)
chk('  · el log nombra los fallos previos', 'falló 2 vez/veces' in salida)

# 5) Una Aborta de dentro (una guarda) sube tal cual.
def guarda_aborta():
    raise fc.Aborta('[Guarda X] el fichero no cuadra')
try:
    fc._leer_con_reintentos('leer W', guarda_aborta, esperas=RAPIDO)
    chk('Aborta interna sube tal cual', False)
except fc.Aborta as e:
    chk('Aborta interna sube tal cual', '[Guarda X]' in str(e))

print()
print('✅ TODO OK' if fallos == 0 else f'❌ {fallos} FALLOS')
raise SystemExit(1 if fallos else 0)
