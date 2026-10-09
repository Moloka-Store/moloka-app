# -*- coding: utf-8 -*-
"""Banco de la PASADA DE DISPONIBILIDAD DE DBLINE (encargo DB2-A, 09-oct-2026): escaner2_dbline_disponibilidad.py y
su workflow.

SIN RED, SIN SECRETOS Y SIN BASE: el programa entero (runpy, como lo lanza el workflow) con una `descargar_dbline` y
una `supabase` de mentira. 🔴 DATOS INVENTADOS (repo publico): el Excel lo fabrica test_escaner2_dbline.py.

QUE PRUEBA:
  (B) el bueno aplica (lotes de 500, recuentos, huella de contenido, sin `fecha_salida`, una llamada a
      disp_aplicar_pasada); «al día» por contenido en VERDE sin subir nada; fichero ilegible, filas por debajo del
      minimo, sin minimo en la base y error de la descarga: no aplican y dicen por que.
  (C) 🔴 EL REGISTRO NO SUELTA DATOS: la descarga de mentira imprime la «respuesta del login», una URL y el usuario y
      la clave (como puede hacer descargar_dbline.py); nada de eso, ni un codigo, EAN, nombre o precio, sale al
      registro; y el motivo que queda en la base, tampoco la URL ni los secretos.
  (D) sin secretos: rojo sin abrir pasada. El rescate: solo la pasada de ESTE run, de DBLine.
  (E) por estructura: el workflow solo se lanza a mano, con grupo propio, y los secretos en el primer paso.
"""
import contextlib
import io
import os
import runpy
import sys
import types

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
PROGRAMA = os.path.join(RAIZ, 'escaner2_dbline_disponibilidad.py')
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-dbline-disponibilidad.yml')
sys.path.insert(0, RAIZ)

# El Excel inventado del banco de las reglas, sin correr ese banco: se cargan solo sus funciones.
_fuente = open(os.path.join(RAIZ, 'test_escaner2_dbline.py'), encoding='utf-8').read()
_ns = {'__file__': os.path.join(RAIZ, 'test_escaner2_dbline.py')}
exec(compile(_fuente.split('# ── (1) La llave por formula')[0], 'test_escaner2_dbline.py', 'exec'), _ns)
fila, excel = _ns['fila'], _ns['excel']

fallos = []
USUARIO, CLAVE = 'USUARIO-DBLINE-SECRETO', 'CLAVE-DBLINE-SECRETA'
URL = 'https://tienda.invalid/descarga/catalogo.xlsx?token=abcdef0123456789abcdef0123456789'


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def libro(n=1200, disponibles=None, **k):
    """Un catalogo inventado de n filas; las primeras `disponibles` con unidades (todas, si no se dice)."""
    disponibles = n if disponibles is None else disponibles
    return excel([fila('ZQ%05d' % i, Disponibili=(3 if i < disponibles else 0), Descrizione='Nombre inventado %d' % i,
                       EAN='49999990%05d' % i, **k) for i in range(n)])


class _Consulta:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.accion, self.datos, self.filtros = base, tabla, None, None, {}

    def insert(self, d):
        self.accion, self.datos = 'insert', d
        return self

    def update(self, d):
        self.accion, self.datos = 'update', d
        return self

    def delete(self):
        self.accion = 'delete'
        return self

    def select(self, *_a, **_k):
        self.accion = 'select'
        return self

    def eq(self, col, val):
        self.filtros[col] = val
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        b = self.base
        r = []
        if self.tabla == 'disp_pasada':
            if self.accion == 'insert':
                pid = 'PASADA-DBL-%d' % (len(b.pasadas) + 1)
                b.pasadas[pid] = dict(self.datos, id=pid)
                r = [{'id': pid}]
            elif self.accion == 'update':
                p = b.pasadas.get(self.filtros.get('id'))
                if p is not None and all(p.get(k) == v for k, v in self.filtros.items()):
                    p.update(self.datos)
            elif self.accion == 'select':
                if 'id' in self.filtros:
                    r = [dict(b.pasadas[self.filtros['id']])]
                elif self.filtros.get('estado') == 'aplicada':
                    r = [{'id': 'P-ANTES', 'huella_contenido': b.ultima_huella}] if b.ultima_huella else []
                elif self.filtros.get('estado') == 'leyendo':
                    r = [{'id': i} for i, p in b.pasadas.items()
                         if p.get('estado') == 'leyendo' and p.get('run_id') == self.filtros.get('run_id')
                         and p.get('proveedor') == self.filtros.get('proveedor')]
        elif self.tabla == 'disp_parametros' and self.accion == 'select':
            r = [{'crudo_minimo': b.minimo}] if b.minimo is not None else []
        elif self.tabla == 'disp_lectura':
            if self.accion == 'insert':
                b.lectura.extend(self.datos)
                b.lotes.append(len(self.datos))
            elif self.accion == 'delete':
                b.lectura = [x for x in b.lectura if x['pasada_id'] != self.filtros.get('pasada_id')]
        return types.SimpleNamespace(data=r)


class Base:
    def __init__(self, minimo=1000, ultima_huella=None):
        self.minimo, self.ultima_huella = minimo, ultima_huella
        self.pasadas, self.lectura, self.lotes, self.rpcs = {}, [], [], []

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, params):
        base = self

        class _Llamada:
            def execute(self):
                base.rpcs.append((nombre, params))
                p = base.pasadas[params['p_pasada']]
                leidas = [x for x in base.lectura if x['pasada_id'] == p['id']]
                base.leidas_al_aplicar = leidas
                if p.get('n_leidas') == len(leidas) == p.get('n_crudo'):
                    p.update(estado='aplicada', primera=True, n_en_catalogo=len(leidas),
                             n_disponibles_estado=sum(1 for x in leidas if x['disponible']), caida_aceptada=False)
                else:
                    p.update(estado='rechazada', motivo='no cuadra (de mentira)')
                base.lectura = [x for x in base.lectura if x['pasada_id'] != p['id']]
                return types.SimpleNamespace(data={'estado': p['estado']})
        return _Llamada()


def descarga_de_mentira(contenido=None, error=None):
    """Una `descargar_dbline` que, como la de verdad, IMPRIME cosas que no pueden salir al registro."""
    m = types.ModuleType('descargar_dbline')

    def descargar_catalogo_dbline():
        print(f'   login -> 200 | respuesta: {{"ok":1,"utente":"{USUARIO}","pw":"{CLAVE}"}}')
        print(f'   Intento bajar el fichero enlazado: {URL}')
        if error:
            raise RuntimeError(f'La descarga NO es un .xlsx · {URL} · {USUARIO}')
        return contenido
    m.descargar_catalogo_dbline = descargar_catalogo_dbline
    return m


def correr(contenido=None, base=None, argv=(), secretos=True, run_id='4242', error=None):
    base = base or Base()
    falso = types.ModuleType('supabase')
    falso.create_client = lambda url, llave: base
    guardados = {k: sys.modules.get(k) for k in ('supabase', 'descargar_dbline')}
    sys.modules['supabase'] = falso
    sys.modules['descargar_dbline'] = descarga_de_mentira(contenido, error)
    entorno = {'SUPABASE_URL': 'https://base.example.test', 'SUPABASE_SERVICE_KEY': 'LLAVE-DE-SERVICIO-SECRETA',
               'GITHUB_RUN_ID': run_id}
    if secretos:
        entorno.update(DBLINE_USER=USUARIO, DBLINE_PASS=CLAVE)
    viejo_env = {k: os.environ.get(k) for k in list(entorno) + ['DBLINE_USER', 'DBLINE_PASS']}
    os.environ.pop('DBLINE_USER', None)
    os.environ.pop('DBLINE_PASS', None)
    os.environ.update(entorno)
    viejo_argv, sys.argv = sys.argv, [PROGRAMA] + list(argv)
    salida = io.StringIO()
    try:
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            try:
                runpy.run_path(PROGRAMA, run_name='__main__')
                codigo = 0
            except SystemExit as e:
                codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = viejo_argv
        for k, v in viejo_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k, v in guardados.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return codigo, salida.getvalue(), base


PROHIBIDO = (USUARIO, CLAVE, URL, 'tienda.invalid', 'abcdef0123456789', 'ZQ0', '49999990', 'Nombre inventado', '10.0',
             'LLAVE-DE-SERVICIO-SECRETA', 'login ->', 'Traceback')


def limpio_de_datos(texto):
    return [p for p in PROHIBIDO if p in texto]


# Los minimos de la casa (16.500 filas, 11.000 disponibles) obligarian a fabricar Excel enormes: se bajan los del
# modulo durante el banco (el programa los lee de escaner2_dbline).
import escaner2_dbline as DB  # noqa: E402
DB.MIN_DISPONIBLES = 500

# ── (B) El bueno aplica ───────────────────────────────────────────────────────────────────
bueno = libro(1200)
cod, log, base = correr(bueno)
p = list(base.pasadas.values())[0]
eq('bueno: sale en verde', cod, 0)
eq('bueno: aplicada', p['estado'], 'aplicada')
eq('bueno: lotes de 500', base.lotes, [500, 500, 200])
eq('bueno: una llamada a disp_aplicar_pasada', [n for n, _ in base.rpcs], ['disp_aplicar_pasada'])
eq('bueno: recuentos en la pasada', (p['n_crudo'], p['n_leidas'], p['n_disponibles']), (1200, 1200, 1200))
eq('bueno: huella de contenido guardada', len(p.get('huella_contenido') or ''), 32)
eq('bueno: md5 y bytes del fichero', (len(p.get('fichero_md5') or ''), p.get('fichero_bytes')), (32, len(bueno)))
eq('bueno: las filas suben sin fecha_salida y con fin_oferta',
   ('fecha_salida' in base.leidas_al_aplicar[0], 'fin_oferta' in base.leidas_al_aplicar[0]), (False, True))
eq('bueno: proveedor DBLINE y run', (p['proveedor'], p['run_id']), ('DBLINE', 4242))
eq('(C) bueno: el registro no suelta datos', limpio_de_datos(log), [])
huella = p['huella_contenido']

# ── «al día» por contenido ────────────────────────────────────────────────────────────────
cod, log, base = correr(bueno, base=Base(ultima_huella=huella))
p = list(base.pasadas.values())[0]
eq('al día: verde', (cod, 'DBLINE_AL_DIA' in log), (0, True))
eq('al día: rechazada y sin subir nada', (p['estado'], base.lotes, base.rpcs), ('rechazada', [], []))

# ── Lo que no aplica ──────────────────────────────────────────────────────────────────────
cod, log, base = correr(b'esto no es un excel')
p = list(base.pasadas.values())[0]
eq('ilegible: rojo y fallida', (cod, p['estado']), (1, 'fallida'))
cod, log, base = correr(libro(900))
p = list(base.pasadas.values())[0]
eq('vaciado: filas por debajo del minimo', (cod, p['estado'], base.lotes), (1, 'rechazada_vaciado', []))
cod, log, base = correr(libro(1200, disponibles=100))
p = list(base.pasadas.values())[0]
eq('vaciado: disponibles por debajo del minimo', (cod, p['estado']), (1, 'rechazada_vaciado'))
cod, log, base = correr(bueno, base=Base(minimo=None))
p = list(base.pasadas.values())[0]
eq('sin minimo en la base (falta la migracion): fallida sin bajar', (cod, p['estado'], 'sin mínimo' in p['motivo']),
   (1, 'fallida', True))
cod, log, base = correr(error=True)
p = list(base.pasadas.values())[0]
eq('descarga que falla: rojo y fallida', (cod, p['estado']), (1, 'fallida'))
eq('(C) descarga que falla: el registro solo dice el tipo', ('RuntimeError' in log, limpio_de_datos(log)),
   (True, []))
eq('(C) descarga que falla: el motivo de la base sin URL ni secretos',
   [x for x in (URL, USUARIO, 'tienda.invalid') if x in p['motivo']], [])
for nombre, args in (('ilegible', {'contenido': b'x'}), ('vaciado', {'contenido': libro(900)})):
    _c, log, _b = correr(**args)
    eq('(C) %s: el registro no suelta datos' % nombre, limpio_de_datos(log), [])

# ── (D) Sin secretos y rescate ────────────────────────────────────────────────────────────
cod, log, base = correr(bueno, secretos=False)
eq('sin secretos: rojo sin abrir pasada', (cod, base.pasadas, 'DBLINE_NO_EJECUTADA' in log), (1, {}, True))
base = Base()
base.pasadas = {'A': {'id': 'A', 'proveedor': 'DBLINE', 'estado': 'leyendo', 'run_id': 4242},
                'B': {'id': 'B', 'proveedor': 'DBLINE', 'estado': 'leyendo', 'run_id': 9999},
                'C': {'id': 'C', 'proveedor': 'OCIOSTOCK', 'estado': 'leyendo', 'run_id': 4242}}
cod, log, base = correr(base=base, argv=['--rescate'], secretos=False)
eq('rescate: solo la de este run y de DBLine', (cod, [base.pasadas[k]['estado'] for k in 'ABC']),
   (0, ['fallida', 'leyendo', 'leyendo']))

# ── (E) El workflow, por estructura ───────────────────────────────────────────────────────
wf = yaml.safe_load(open(WORKFLOW, encoding='utf-8'))
pasos = wf['jobs']['leer']['steps']
eq('workflow: solo a mano', list(wf[True]), ['workflow_dispatch'])
eq('workflow: grupo propio sin cancelar', wf['concurrency'], {'group': 'escaner2-dbline', 'cancel-in-progress': False})
eq('workflow: los secretos, en el primer paso', sorted(pasos[0]['env']),
   ['DBLINE_PASS', 'DBLINE_USER', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL'])
eq('workflow: la pasada lleva DBLINE_USER/PASS y la base',
   sorted(k for k in pasos[4]['env'] if k != 'PYTHONIOENCODING'),
   ['DBLINE_PASS', 'DBLINE_USER', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL'])
eq('workflow: el rescate no lleva los de DBLine', 'DBLINE_PASS' in pasos[5]['env'], False)
eq('workflow: el rescate solo si los secretos estaban', 'steps.secretos.outcome' in pasos[5]['if'], True)

print()
if fallos:
    print('ROJO: %d comprobación(es) fallida(s):' % len(fallos))
    for f in fallos:
        print('  - ' + f)
    sys.exit(1)
print('VERDE: todas las comprobaciones pasan.')
