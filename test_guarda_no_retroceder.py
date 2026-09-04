# -*- coding: utf-8 -*-
"""BANCO DE PRUEBAS de la guarda no-retroceder en procesador_internacional.py.

Que prueba y que NO:
  · SI: que la guarda se ALCANZA desde main(), en el orden bueno, y que cuando
        salta NO se ejecuta NI UN DELETE NI UN INSERT. Ejecuta el main() REAL y
        la guarda_no_retroceder REAL de foto_comun; lo unico de mentira son el
        buzon y el cursor.
  · NO: las cifras. El MAX que devuelve el cursor de mentira NO es inventado:
        es el que devuelve la SQL literal de la guarda contra las bases reales
        (staging 2026-08-24, produccion 2026-08-27), medido por MCP el 28-ago.

Se corre:  python banco_guarda_internacional.py
"""
import sys, os, io, types, importlib, contextlib
from datetime import datetime, date, timezone

REPO = os.path.dirname(os.path.abspath(__file__))   # el propio repo, sin rutas a fuego
sys.path.insert(0, REPO)

fallos = []
def chk(nombre, ok, detalle=''):
    print(('OK   ' if ok else 'XX   ') + nombre + (('  -> ' + detalle) if detalle else ''))
    if not ok:
        fallos.append(nombre)


# ---------------------------------------------------------------------------
# El cursor de mentira: RESPONDE a las consultas reales y GRABA todo lo que pasa
# ---------------------------------------------------------------------------
class CursorGrabador:
    def __init__(self, estado):
        self.e = estado
        self.sql = []          # todo lo ejecutado, normalizado
        self._ret = []
        self.rowcount = 0

    def execute(self, q, args=None):
        limpio = ' '.join(str(q).split())
        self.sql.append(limpio)
        ql = limpio.lower()
        if 'to_regclass' in ql:
            self._ret = [(('inventario_internacional' if self.e['tabla_existe'] else None),)]
        elif 'max(t.fecha_foto)' in ql:
            self._ret = [(self.e['max_fecha'],)]
        elif 'count(*) from inventario_internacional as t' in ql:
            # la de la anti-encogimiento: es la unica que decide algo
            self._ret = [(self.e['previas'],)]
        elif ql.startswith('select count('):
            # recuentos de informe (historico, fotogramas): un numero cualquiera
            self._ret = [(self.e['filas_fichero'],)]
        elif 'relrowsecurity' in ql:
            self._ret = [(True,)]
        elif ql.startswith('delete'):
            self.rowcount = 0
            self._ret = []
        else:
            self._ret = []

    def fetchone(self):  return self._ret[0] if self._ret else None
    def fetchall(self):  return list(self._ret)
    def close(self):     pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


class ConexionFalsa:
    def __init__(self, estado):
        self.e = estado
        self.autocommit = False
        self.cur = CursorGrabador(estado)
        self.commits = 0
        self.rollbacks = 0
    def cursor(self):  return self.cur
    def commit(self):  self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self):   pass


# ---------------------------------------------------------------------------
# El informe: TSV minimo que pasa las guardas estructurales 1..5 de verdad
# ---------------------------------------------------------------------------
def tsv(n_filas):
    cab = ['seller-sku', 'fulfillment-channel-sku', 'asin', 'condition-type',
           'country', 'quantity-for-local-fulfillment']
    out = ['\t'.join(cab)]
    for i in range(n_filas):
        out.append('\t'.join([f'SKU-{i:04}', f'X0{i:08}', f'B0{i:08}',
                              'NewItem', ['ES', 'IT', 'FR'][i % 3], '7']))
    return ('\n'.join(out) + '\n').encode('utf-8')


def montar_stubs(estado):
    """Deja en sys.modules un supabase y un psycopg2 de mentira, y devuelve la conexion."""
    conexiones = []

    class _Bucket:
        # `options` porque `listar_buzon` PAGINA desde el 4-sep-2026: pasa
        # {'limit','offset','sortBy'} igual que hace `backup_storage`. Y no se ignora
        # — se honra limit/offset como el SDK—, para que este doble no se vuelva un
        # servidor complaciente que devuelva la carpeta entera se pida lo que se pida.
        def list(self, carpeta, options=None):
            o = {'limit': 100, 'offset': 0, **(options or {})}
            objetos = [{'name': '50669020692.txt', 'updated_at': estado['subido_at']}]
            return objetos[o['offset']:o['offset'] + o['limit']]
        def download(self, ruta):
            return tsv(estado['filas_fichero'])
    class _Storage:
        def from_(self, b): return _Bucket()
    class _Cliente:
        storage = _Storage()

    supabase = types.ModuleType('supabase')
    supabase.create_client = lambda url, key: _Cliente()
    sys.modules['supabase'] = supabase

    def _connect(*a, **k):
        c = ConexionFalsa(estado)
        conexiones.append(c)
        return c

    psycopg2 = types.ModuleType('psycopg2')
    psycopg2.connect = _connect
    class _Err(Exception): pass
    psycopg2.Error = _Err
    psycopg2.OperationalError = type('OperationalError', (_Err,), {})
    sys.modules['psycopg2'] = psycopg2

    extras = types.ModuleType('psycopg2.extras')
    extras.Json = lambda v: v
    def _execute_values(cur, sql, argslist, template=None, page_size=100):
        cur.execute(f'{sql}   /* execute_values con {len(list(argslist))} filas */')
    extras.execute_values = _execute_values
    sys.modules['psycopg2.extras'] = extras
    psycopg2.extras = extras

    return conexiones


def correr(caso, estado, env_extra=None):
    """Importa el procesador de cero y ejecuta main(). Devuelve (codigo, salida, conexion)."""
    for m in ('procesador_internacional', 'foto_comun', 'tsv_comun',
              'supabase', 'psycopg2', 'psycopg2.extras'):
        sys.modules.pop(m, None)

    os.environ.update({'MODO': 'ensayo', 'ENTORNO': 'staging',
                       'SUPABASE_KEY': 'de-mentira', 'DB_URL': 'de-mentira',
                       'SUPABASE_URL': 'http://de-mentira'})
    os.environ.pop('PERMITIR_RETROCESO', None)
    if env_extra:
        os.environ.update(env_extra)

    conexiones = montar_stubs(estado)
    mod = importlib.import_module('procesador_internacional')

    buf = io.StringIO()
    codigo = 0
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else 1
    con = conexiones[0] if conexiones else None
    return codigo, buf.getvalue(), con


def sqls(con):
    return [s.lower() for s in (con.cur.sql if con else [])]

def hubo_borrado(con):
    return any(s.startswith('delete') for s in sqls(con))

def hubo_escritura(con):
    return any(s.startswith('insert') or 'execute_values' in s for s in sqls(con))


# ===========================================================================
print('=' * 78)
print('BANCO · guarda no-retroceder en procesador_internacional.py')
print('MAX medidos por SQL real (28-ago): staging 2026-08-24 · produccion 2026-08-27')
print('=' * 78)

BASE = dict(tabla_existe=True, previas=309, filas_fichero=300,
            subido_at='2026-08-28T09:00:00+00:00', max_fecha=date(2026, 8, 24))

# --- 1. CALLADA: la foto de hoy es MAS NUEVA que la ultima (el caso normal) ---
cod, out, con = correr('normal', dict(BASE))
chk('1 · foto de hoy (28) sobre max 24  ->  NO aborta',
    cod == 0 and 'no-retroceder' not in out.lower(), f'exit={cod}')
chk('1b · y llega a hacer su trabajo (borra y escribe dentro de la transaccion)',
    hubo_borrado(con) and hubo_escritura(con))
chk('1c · ensayo: hace rollback y NO commit',
    con.rollbacks == 1 and con.commits == 0, f'commits={con.commits} rollbacks={con.rollbacks}')

# --- 2. CALLADA en el BORDE: misma fecha (recargar el informe del mismo dia) ---
e = dict(BASE); e['max_fecha'] = date(2026, 8, 28)
cod, out, con = correr('borde', e)
chk('2 · MISMA fecha (28 sobre 28)  ->  NO aborta (el operador es <, no <=)',
    cod == 0 and 'no-retroceder' not in out.lower(), f'exit={cod}')

# --- 3. SALTA: la carga queda POR DETRAS de lo ya registrado ---
e = dict(BASE); e['subido_at'] = '2026-08-20T09:00:00+00:00'
cod, out, con = correr('retroceso', e)
chk('3 · foto del 20 sobre max 24  ->  ABORTA con exit 1',
    cod == 1, f'exit={cod}')
chk('3b · el mensaje es el de la guarda y dice las dos fechas',
    'no-retroceder' in out.lower() and '2026-08-20' in out and '2026-08-24' in out)
chk('3c · 🔴 NO SE BORRA NADA (ni un DELETE llego a ejecutarse)',
    not hubo_borrado(con), f'sql ejecutado: {len(sqls(con))} sentencias')
chk('3d · 🔴 NO SE ESCRIBE NADA',
    not hubo_escritura(con))
chk('3e · y deshace la transaccion',
    con.rollbacks >= 1 and con.commits == 0)

# --- 4. La valvula de escape ---
e = dict(BASE); e['subido_at'] = '2026-08-20T09:00:00+00:00'
cod, out, con = correr('valvula', e, env_extra={'PERMITIR_RETROCESO': '1'})
chk('4 · el mismo retroceso con PERMITIR_RETROCESO=1  ->  pasa',
    cod == 0, f'exit={cod}')

# --- 5. Primera carga: la tabla aun no existe ---
e = dict(BASE); e['tabla_existe'] = False; e['previas'] = 0
cod, out, con = correr('sin_tabla', e)
chk('5 · tabla sin crear  ->  NO aborta (no hay pasado contra el que retroceder)',
    cod == 0, f'exit={cod}')

# --- 6. Tabla vacia: MAX es NULL ---
e = dict(BASE); e['max_fecha'] = None; e['previas'] = 0
cod, out, con = correr('vacia', e)
chk('6 · tabla vacia (MAX NULL)  ->  NO aborta', cod == 0, f'exit={cod}')

# --- 7. EL ORDEN: la guarda corre ANTES del borrado ---
cod, out, con = correr('orden', dict(BASE))
s = sqls(con)
i_max = next((i for i, q in enumerate(s) if 'max(t.fecha_foto)' in q), -1)
i_del = next((i for i, q in enumerate(s) if q.startswith('delete')), -1)
chk('7 · la consulta de la guarda va ANTES del primer DELETE',
    i_max >= 0 and i_del >= 0 and i_max < i_del, f'max en {i_max}, delete en {i_del}')

# --- 8. FALSADOR DEL BANCO: si la guarda no estuviera, el caso 3 pasaria ---
#     Se comprueba que el caso 3 depende DE VERDAD de la llamada, no de otra cosa.
import re as _re
fuente = open(os.path.join(REPO, 'procesador_internacional.py'), encoding='utf-8').read()
sin_comentarios = _re.sub(r'^\s*#[^\n]*$', '', fuente, flags=_re.M)
chk('8 · la llamada existe en CODIGO, no solo en un comentario',
    'guarda_no_retroceder(' in sin_comentarios,
    f"apariciones en codigo: {sin_comentarios.count('guarda_no_retroceder(')}")

print('=' * 78)
print(('TODO OK' if not fallos else f'FALLOS: {fallos}'))
sys.exit(1 if fallos else 0)
