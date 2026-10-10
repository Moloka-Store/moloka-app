# -*- coding: utf-8 -*-
"""Banco de la PASADA DE DISPONIBILIDAD DE BEMS (encargo BE2, 10-oct-2026): escaner2_bems_disponibilidad.py y su
workflow.

SIN RED, SIN SECRETOS Y SIN BASE: el programa entero (runpy, como lo lanza el workflow) con una `supabase` de mentira
que trae la base Y el almacen; el listado y la descarga pasan por el foto_comun DE VERDAD. 🔴 DATOS INVENTADOS (repo
publico): el CSV lo fabrica test_escaner2_bems.py.

QUE PRUEBA:
  (B) el bueno aplica con el ID DE LA CARPETA (lotes de 500, recuentos con las repetidas, huella de contenido, md5,
      bytes y fecha del nombre, sin ean_norm, una llamada a disp_aplicar_pasada); «al día» por contenido en VERDE sin
      subir nada; lo que no aplica (CSV descuadrado, filas o disponibles por debajo de los minimos DE LA BASE, sin
      minimos, carpeta vacia, dos ficheros, nombre malo, fichero que no se puede bajar) queda 'fallida' o
      'rechazada_vaciado', en ROJO y diciendo por que.
  (C) 🔴 EL REGISTRO NO SUELTA DATOS: ni una REF, EAN, titulo o precio, ni la llave, ni la URL, ni el texto de un error
      del almacen (tampoco el de un reintento, que foto_comun imprime: al registro solo cuantos hubo).
  (D) las guardas antes de la red: sin PASADA, con una PASADA sin forma de uuid o sin los secretos, ROJO sin crear el
      cliente; con una pasada que ya existe, ROJO sin escribir nada. El rescate: solo esa pasada, de BEMS y leyendo.
  (E) el workflow, por estructura: solo a mano con el input `pasada`, que llega por env: (nunca dentro de un run:) y
      se valida en el primer paso junto con los secretos; grupo propio; el rescate solo si el primer paso salio bien.
"""
import contextlib
import io
import os
import runpy
import sys
import types

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
PROGRAMA = os.path.join(RAIZ, 'escaner2_bems_disponibilidad.py')
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'escaner2-bems-disponibilidad.yml')
sys.path.insert(0, RAIZ)

# El CSV inventado del banco de las reglas, sin correr ese banco: se cargan solo sus funciones.
_fuente = open(os.path.join(RAIZ, 'test_escaner2_bems.py'), encoding='utf-8').read()
_ns = {'__file__': os.path.join(RAIZ, 'test_escaner2_bems.py')}
exec(compile(_fuente.split('# ── (1) El bueno')[0], 'test_escaner2_bems.py', 'exec'), _ns)
fila, csv = _ns['fila'], _ns['csv']

fallos = []
LLAVE = 'LLAVE-DE-SERVICIO-SECRETA'
URL_BASE = 'https://base-secreta.example.test'
PASADA = 'b2e00000-0000-4000-8000-00000000be02'
NOMBRE = 'BEMS_EXPORT_10_10_2026.csv'


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def catalogo(n=1200, sin_stock=200, repetidas=0, **k):
    """Un CSV inventado de n articulos (los `sin_stock` ultimos con STOCK 0) y `repetidas` filas identicas de mas."""
    filas = [fila('7%05d' % i, PA='13.57', STOCK=('0' if i >= n - sin_stock else '4'), **k) for i in range(n)]
    return csv(filas + [list(f) for f in filas[:repetidas]])


class ErrorAlmacen(Exception):
    """Como el de storage3: trae su codigo y un texto con la ruta y la URL (que no pueden salir al registro)."""

    def __init__(self, status, texto):
        super().__init__(texto)
        self.status = status


class _Cubo:
    def __init__(self, base, bucket):
        self.base, self.bucket = base, bucket

    def list(self, carpeta, opciones=None):
        self.base.listados.append((self.bucket, carpeta))
        pre = carpeta.rstrip('/') + '/'
        nombres = sorted(r[len(pre):] for (b, r) in self.base.ficheros if b == self.bucket and r.startswith(pre))
        o = (opciones or {}).get('offset', 0)
        return [{'name': n, 'id': 'x'} for n in nombres[o:o + (opciones or {}).get('limit', 100)]]

    def download(self, ruta):
        if self.base.cortes_descarga:
            self.base.cortes_descarga -= 1
            raise ConnectionResetError(f'connection reset by peer · {URL_BASE}/storage/{ruta} · {LLAVE}')
        if self.base.no_bajar or (self.bucket, ruta) not in self.base.ficheros:
            raise ErrorAlmacen(404, f'{{"statusCode":"404","error":"not_found","message":"Object not found {ruta}"}} '
                                    f'{URL_BASE}')
        return self.base.ficheros[(self.bucket, ruta)]


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
        b.escrituras.append((self.tabla, self.accion)) if self.accion != 'select' else None
        r = []
        if self.tabla == 'disp_pasada':
            if self.accion == 'insert':
                b.pasadas[self.datos['id']] = dict(self.datos)
                r = [dict(self.datos)]
            elif self.accion == 'update':
                p = b.pasadas.get(self.filtros.get('id'))
                if p is not None and all(p.get(k) == v for k, v in self.filtros.items()):
                    p.update(self.datos)
            elif self.accion == 'select':
                if self.filtros.get('estado') == 'aplicada':
                    r = [{'id': 'P-ANTES', 'huella_contenido': b.ultima_huella}] if b.ultima_huella else []
                else:
                    r = [dict(p) for p in b.pasadas.values() if all(p.get(k) == v for k, v in self.filtros.items())]
        elif self.tabla == 'disp_parametros' and self.accion == 'select':
            r = [b.parametros] if b.parametros is not None else []
        elif self.tabla == 'disp_lectura':
            if self.accion == 'insert':
                b.lectura.extend(self.datos)
                b.lotes.append(len(self.datos))
            elif self.accion == 'delete':
                b.lectura = [x for x in b.lectura if x['pasada_id'] != self.filtros.get('pasada_id')]
        return types.SimpleNamespace(data=r)


class Base:
    def __init__(self, minimo=1000, minimo_disp=500, ultima_huella=None, ficheros=None, parametros=True):
        """ficheros: {nombre: bytes} en bems/foto/<PASADA>/ (por defecto, el catalogo bueno)."""
        self.parametros = {'crudo_minimo': minimo, 'disponibles_minimo': minimo_disp} if parametros else None
        self.ultima_huella = ultima_huella
        self.pasadas, self.lectura, self.lotes, self.rpcs, self.escrituras, self.listados = {}, [], [], [], [], []
        self.cortes_descarga, self.no_bajar = 0, False
        ficheros = {NOMBRE: catalogo()} if ficheros is None else ficheros
        self.ficheros = {('escaner2', f'bems/foto/{PASADA}/{n}'): c for n, c in ficheros.items()}
        self.storage = types.SimpleNamespace(from_=lambda bucket: _Cubo(self, bucket))

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
                if p.get('n_leidas') == len(leidas) and p.get('n_crudo') == p.get('n_leidas') + p.get('n_duplicados'):
                    p.update(estado='aplicada', primera=True, n_en_catalogo=len(leidas),
                             n_disponibles_estado=sum(1 for x in leidas if x['disponible']), caida_aceptada=False)
                else:
                    p.update(estado='rechazada', motivo='no cuadra (de mentira)')
                base.lectura = [x for x in base.lectura if x['pasada_id'] != p['id']]
                return types.SimpleNamespace(data={'estado': p['estado']})
        return _Llamada()


CLIENTES = []


def correr(base=None, argv=(), secretos=True, pasada=PASADA, run_id='4242'):
    base = base or Base()
    falso = types.ModuleType('supabase')

    def create_client(url, llave):
        CLIENTES.append(url)
        return base
    falso.create_client = create_client
    guardado = sys.modules.get('supabase')
    sys.modules['supabase'] = falso
    entorno = {'GITHUB_RUN_ID': run_id}
    if secretos:
        entorno.update(SUPABASE_URL=URL_BASE, SUPABASE_SERVICE_KEY=LLAVE)
    if pasada is not None:
        entorno['PASADA'] = pasada
    claves = ('GITHUB_RUN_ID', 'SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'PASADA')
    viejo_env = {k: os.environ.get(k) for k in claves}
    for k in claves:
        os.environ.pop(k, None)
    os.environ.update(entorno)
    viejo_argv, sys.argv = sys.argv, [PROGRAMA] + list(argv)
    salida = io.StringIO()
    CLIENTES.clear()
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
        if guardado is None:
            sys.modules.pop('supabase', None)
        else:
            sys.modules['supabase'] = guardado
    return codigo, salida.getvalue(), base


PROHIBIDO = ('49999', 'Invented title', 'Titre inventé', '13.57', '13,57', LLAVE, URL_BASE, 'base-secreta', 'storage/',
             'not_found', 'Object not found', 'reset by peer', 'Traceback')


def limpio_de_datos(texto):
    return [p for p in PROHIBIDO if p in texto]


# ── (B) El bueno aplica ───────────────────────────────────────────────────────────────────
bueno = catalogo(repetidas=2)
cod, log, base = correr(Base(ficheros={NOMBRE: bueno}))
p = base.pasadas.get(PASADA, {})
eq('bueno: sale en verde', cod, 0)
eq('bueno: la pasada lleva el id de la carpeta, de BEMS y con el run', (list(base.pasadas), p.get('proveedor'),
                                                                       p.get('run_id')), ([PASADA], 'BEMS', 4242))
eq('bueno: aplicada', p.get('estado'), 'aplicada')
eq('bueno: lista bems/foto/<pasada> del almacén escaner2', base.listados, [('escaner2', f'bems/foto/{PASADA}')])
eq('bueno: lotes de 500', base.lotes, [500, 500, 200])
eq('bueno: una llamada a disp_aplicar_pasada con su id', base.rpcs, [('disp_aplicar_pasada', {'p_pasada': PASADA})])
eq('bueno: recuentos (las 2 idénticas, como repetidas)',
   tuple(p.get(k) for k in ('n_crudo', 'n_duplicados', 'n_leidas', 'n_declarado', 'n_disponibles', 'n_agotados',
                            'n_sin_gtin', 'n_precios', 'n_disponibilidades')),
   (1202, 2, 1200, 1200, 1000, 200, 0, 1200, 1200))
eq('bueno: md5, bytes y la fecha del nombre', (len(p.get('fichero_md5') or ''), p.get('fichero_bytes'),
                                                p.get('fichero_fecha_max')), (32, len(bueno), '2026-10-10T00:00:00'))
eq('bueno: huella de contenido guardada', len(p.get('huella_contenido') or ''), 32)
eq('bueno: las filas suben con su pasada y sin ean_norm (la calcula la base)',
   (base.leidas_al_aplicar[0]['pasada_id'], 'ean_norm' in base.leidas_al_aplicar[0]), (PASADA, False))
eq('bueno: el registro dice los recuentos', ('Leídas 1200 de 1202 filas (2 repetidas idénticas' in log,
                                             'PASADA APLICADA: 1200 artículos' in log), (True, True))
eq('(C) bueno: el registro no suelta datos', limpio_de_datos(log), [])
huella = p['huella_contenido']

# ── «al día» por contenido: el mismo catálogo, otro día y otro fichero ───────────────────────
cod, log, base = correr(Base(ultima_huella=huella,
                             ficheros={'BEMS_EXPORT_11_10_2026.csv': catalogo()}))
p = base.pasadas[PASADA]
eq('al día: verde', (cod, 'BEMS_AL_DIA' in log), (0, True))
eq('al día: rechazada, con su motivo y sin subir nada', (p['estado'], 'al día' in p['motivo'], base.lotes, base.rpcs),
   ('rechazada', True, [], []))

# ── Lo que no aplica ──────────────────────────────────────────────────────────────────────
_filas = [fila('7%05d' % i, PA='13.57', STOCK='4') for i in range(1200)]
_filas[5] = _filas[5] + ['de mas']
descuadrado = csv(_filas)
cod, log, base = correr(Base(ficheros={NOMBRE: descuadrado}))
p = base.pasadas[PASADA]
eq('CSV descuadrado: rojo y fallida, con las líneas', (cod, p['estado'], 'líneas' in p['motivo']), (1, 'fallida', True))
eq('CSV descuadrado: sin subir nada', (base.lotes, base.rpcs), ([], []))
cod, log, base = correr(Base(minimo=1500))
p = base.pasadas[PASADA]
eq('vaciado: artículos por debajo del mínimo de la base', (cod, p['estado'], 'mínimo 1500' in p['motivo'], base.lotes),
   (1, 'rechazada_vaciado', True, []))
cod, log, base = correr(Base(minimo_disp=1100))
p = base.pasadas[PASADA]
eq('vaciado: con stock por debajo del mínimo de la base', (cod, p['estado'], 'mínimo 1100' in p['motivo']),
   (1, 'rechazada_vaciado', True))
cod, log, base = correr(Base(parametros=False))
p = base.pasadas[PASADA]
eq('sin fila en disp_parametros: fallida sin bajar nada', (cod, p['estado'], 'sin mínimo' in p['motivo'], base.listados),
   (1, 'fallida', True, []))
for nombre, ficheros, texto in (
        ('carpeta vacía', {}, '0 fichero(s)'),
        ('dos ficheros', {NOMBRE: catalogo(), 'BEMS_EXPORT_09_10_2026.csv': catalogo()}, '2 fichero(s)'),
        ('nombre que no es el de BEMS', {'catalogo.csv': catalogo()}, 'BEMS_EXPORT_DD_MM_AAAA.csv'),
        ('fecha imposible en el nombre', {'BEMS_EXPORT_31_02_2026.csv': catalogo()}, 'no existe')):
    cod, log, base = correr(Base(ficheros=ficheros))
    p = base.pasadas[PASADA]
    eq('%s: rojo y fallida, diciendo por qué' % nombre, (cod, p['estado'], texto in p['motivo'], base.lotes),
       (1, 'fallida', True, []))
# El marcador que deja el almacén en una carpeta no cuenta como fichero.
cod, log, base = correr(Base(ficheros={NOMBRE: catalogo(), '.emptyFolderPlaceholder': b''}))
eq('el marcador de carpeta del almacén no cuenta', (cod, base.pasadas[PASADA]['estado']), (0, 'aplicada'))

# El almacén no da el fichero (404, no transitorio): fallida; al registro, solo el tipo.
base = Base()
base.no_bajar = True  # lo lista, pero no se puede bajar
cod, log, base = correr(base)
p = base.pasadas[PASADA]
eq('el almacén no da el fichero: rojo y fallida', (cod, p['estado'], 'error inesperado (Aborta)' in log), (1, 'fallida', True))
eq('(C) el almacén no da el fichero: el registro no suelta el error', limpio_de_datos(log), [])
eq('(C) el almacén no da el fichero: el motivo de la base, sin URL ni llave',
   [x for x in (URL_BASE, LLAVE, 'base-secreta') if x in p['motivo']], [])

# Un corte de red al bajar: foto_comun reintenta (y lo imprime con el texto del error); al registro, solo cuántos.
base = Base()
base.cortes_descarga = 1
cod, log, base = correr(base)
eq('corte de red al bajar: reintenta y aplica', (cod, base.pasadas[PASADA]['estado']), (0, 'aplicada'))
eq('corte de red al bajar: el registro dice cuántas líneas de aviso (la del fallo y la del intento bueno)',
   '2 línea(s) de aviso de reintento al bajar' in log, True)
eq('(C) corte de red al bajar: ni el texto del error, ni la URL, ni la llave', limpio_de_datos(log), [])

# ── (D) Las guardas antes de la red, y el rescate ────────────────────────────────────────
for nombre, kw in (('sin PASADA', {'pasada': None}), ('PASADA sin forma de uuid', {'pasada': 'bems/foto/../otra'}),
                   ('PASADA en mayúsculas de otra forma', {'pasada': 'B2E00000-0000-4000-8000'}),
                   ('sin secretos', {'secretos': False})):
    cod, log, base = correr(**kw)
    eq('%s: rojo sin crear el cliente ni abrir nada' % nombre,
       (cod, CLIENTES, base.pasadas, 'BEMS_NO_EJECUTADA' in log), (1, [], {}, True))
eq('PASADA en mayúsculas pero con forma de uuid: vale (se pasa a minúsculas)',
   (correr(pasada=PASADA.upper())[0], list(correr(pasada=PASADA.upper())[2].pasadas)), (0, [PASADA]))
base = Base()
base.pasadas[PASADA] = {'id': PASADA, 'proveedor': 'BEMS', 'estado': 'aplicada'}
cod, log, base = correr(base)
eq('pasada que ya existe: rojo, sin escribir ni listar nada', (cod, base.escrituras, base.listados,
                                                               'ya existe' in log), (1, [], [], True))
base = Base()
otra = 'b2e00000-0000-4000-8000-0000000000ff'
base.pasadas = {PASADA: {'id': PASADA, 'proveedor': 'BEMS', 'estado': 'leyendo'},
                otra: {'id': otra, 'proveedor': 'BEMS', 'estado': 'leyendo'}}
cod, log, base = correr(base, argv=['--rescate'])
eq('rescate: solo la pasada del input', (cod, base.pasadas[PASADA]['estado'], base.pasadas[otra]['estado']),
   (0, 'fallida', 'leyendo'))
base = Base()
base.pasadas = {PASADA: {'id': PASADA, 'proveedor': 'DBLINE', 'estado': 'leyendo'}}
cod, log, base = correr(base, argv=['--rescate'])
eq('rescate: si no es de BEMS, no la toca', base.pasadas[PASADA]['estado'], 'leyendo')
cod, log, base = correr(argv=['--rescate'], pasada='no-es-un-uuid')
eq('rescate sin PASADA válida: rojo sin cliente', (cod, CLIENTES), (1, []))
cod, log, base = correr(argv=['--otra'])
eq('argumento desconocido: rojo sin cliente', (cod, CLIENTES), (1, []))

# ── (E) El workflow, por estructura ───────────────────────────────────────────────────────
wf = yaml.safe_load(open(WORKFLOW, encoding='utf-8'))
pasos = wf['jobs']['leer']['steps']
eq('workflow: solo a mano', list(wf[True]), ['workflow_dispatch'])
eq('workflow: un input, pasada, obligatorio y de texto',
   {k: (v.get('required'), v.get('type')) for k, v in wf[True]['workflow_dispatch']['inputs'].items()},
   {'pasada': (True, 'string')})
eq('workflow: grupo propio sin cancelar', wf['concurrency'], {'group': 'escaner2-bems', 'cancel-in-progress': False})
eq('workflow: el primer paso mira los secretos y la pasada', sorted(pasos[0]['env']),
   ['PASADA', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL'])
eq('workflow: el primer paso valida la forma de uuid',
   "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" in pasos[0]['run'], True)
eq('🔴 workflow: el input nunca va dentro de un run: (solo por env:)',
   [p.get('name') for p in pasos if 'inputs.' in (p.get('run') or '') or 'github.event' in (p.get('run') or '')], [])
eq('workflow: la pasada y el rescate llevan la base y la PASADA',
   [sorted(k for k in pasos[i]['env'] if k != 'PYTHONIOENCODING') for i in (4, 5)],
   [['PASADA', 'SUPABASE_SERVICE_KEY', 'SUPABASE_URL']] * 2)
eq('workflow: corren este programa', [pasos[4]['run'], pasos[5]['run']],
   ['python -u escaner2_bems_disponibilidad.py', 'python -u escaner2_bems_disponibilidad.py --rescate'])
eq('workflow: el rescate solo si el primer paso salió bien', 'steps.secretos.outcome' in pasos[5]['if'], True)
eq('workflow: topes en el job y en el paso', (wf['jobs']['leer']['timeout-minutes'], pasos[4]['timeout-minutes']),
   (20, 15))
eq('workflow: permisos de solo leer el repo', wf['jobs']['leer']['permissions'], {'contents': 'read'})

print()
if fallos:
    print('ROJO: %d comprobación(es) fallida(s):' % len(fallos))
    for f in fallos:
        print('  - ' + f)
    sys.exit(1)
print('VERDE: todas las comprobaciones pasan.')
