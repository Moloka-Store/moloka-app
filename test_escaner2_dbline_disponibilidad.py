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
  (E) por estructura: el workflow solo se lanza a mano, con grupo propio, y los secretos en el primer paso; curl_cffi
      con la version de requirements.txt (DB2-B).
  (F) DB2-B: la pasada pide la descarga VALIDANDO el certificado (verificar=CADENA_DBLINE); la semana de medicion
      (los cambios de la pasada por marca, de 1.000 en 1.000, cuadrados con disp_pasada; rojo si no cuadran o no se
      leen); y descargar_dbline.py DE VERDAD con un curl_cffi de mentira: por defecto sin verificar (el director viejo,
      como hoy), con la cadena si se le pide, su registro solo con codigos y bytes, y su error diciendo que paso sin
      «mira el log de arriba».
"""
import contextlib
import importlib
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

    def range(self, desde, hasta):
        self.rango = (desde, hasta)
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
        elif self.tabla == 'disp_cambio' and self.accion == 'select':
            if b.error_cambios:
                raise RuntimeError('la base de mentira no deja leer disp_cambio · fila FUNKO ZQ00001')
            b.lecturas_cambio.append(self.rango)
            todas = [c for c in b.cambios if c['pasada_id'] == self.filtros.get('pasada_id')]
            desde, hasta = self.rango
            r = [{'tipo': c['tipo'], 'marca': c['marca']} for c in todas[desde:hasta + 1]]
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
    def __init__(self, minimo=1000, ultima_huella=None, cambios=(), descuadre=False, error_cambios=False):
        """cambios: (tipo, marca) que deja disp_aplicar_pasada en disp_cambio al aplicar, y sus n_* en la pasada
        (descuadre=True: n_entran de mas, como si la lectura de disp_cambio se hubiera quedado corta)."""
        self.minimo, self.ultima_huella = minimo, ultima_huella
        self.pasadas, self.lectura, self.lotes, self.rpcs = {}, [], [], []
        self.al_aplicar, self.descuadre, self.error_cambios = list(cambios), descuadre, error_cambios
        self.cambios, self.lecturas_cambio = [], []

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
                    p.update(estado='aplicada', primera=not base.al_aplicar, n_en_catalogo=len(leidas),
                             n_disponibles_estado=sum(1 for x in leidas if x['disponible']), caida_aceptada=False)
                    for i, (tipo, marca) in enumerate(base.al_aplicar):
                        base.cambios.append({'id': i, 'pasada_id': p['id'], 'tipo': tipo, 'marca': marca})
                    for tipo, col in (('entra_catalogo', 'n_entran'), ('vuelve_catalogo', 'n_vuelven'),
                                      ('sale_catalogo', 'n_salen'), ('pasa_disponible', 'n_a_disponible'),
                                      ('pasa_agotado', 'n_a_agotado'), ('cambia_precio', 'n_cambio_precio')):
                        p[col] = sum(1 for t, _m in base.al_aplicar if t == tipo)
                    if base.descuadre:
                        p['n_entran'] += 1
                else:
                    p.update(estado='rechazada', motivo='no cuadra (de mentira)')
                base.lectura = [x for x in base.lectura if x['pasada_id'] != p['id']]
                return types.SimpleNamespace(data={'estado': p['estado']})
        return _Llamada()


LLAMADAS_DESCARGA = []


def descarga_de_mentira(contenido=None, error=None):
    """Una `descargar_dbline` que, como la vieja, IMPRIME cosas que no pueden salir al registro; apunta con que
    argumentos la llaman (LLAMADAS_DESCARGA)."""
    m = types.ModuleType('descargar_dbline')
    m.CADENA_DBLINE = 'CADENA-DE-MENTIRA.pem'

    def descargar_catalogo_dbline(**k):
        LLAMADAS_DESCARGA.append(k)
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
_req = [l.strip() for l in open(os.path.join(RAIZ, 'requirements.txt'), encoding='utf-8') if l.strip().startswith('curl_cffi')]
eq('workflow (DB2-B): curl_cffi con la version de requirements.txt', (len(_req), _req[0] in pasos[3]['run'].split()),
   (1, True))

# ── (F) DB2-B: certificado, semana de medicion y descargar_dbline.py de verdad ─────────────────
# La pasada pide la descarga VALIDANDO el certificado.
LLAMADAS_DESCARGA.clear()
cod, log, base = correr(bueno)
eq('certificado (DB2-B): la pasada llama con verificar=CADENA_DBLINE', (cod, LLAMADAS_DESCARGA),
   (0, [{'verificar': 'CADENA-DE-MENTIRA.pem'}]))

# c) La semana de medicion: 2.550 cambios (mas de una pagina de 1.000), por marca y cuadrados con disp_pasada.
_al_aplicar = ([('entra_catalogo', 'FUNKO')] * 1200 + [('cambia_precio', 'Pyramid International')] * 900
               + [('pasa_agotado', 'OTRA')] * 400 + [('pasa_disponible', 'FUNKO')] * 30 + [('vuelve_catalogo', 'OTRA')] * 5
               + [('sale_catalogo', 'PYRAMID')] * 15)
cod, log, base = correr(bueno, base=Base(cambios=_al_aplicar))
eq('medición: verde', (cod, list(base.pasadas.values())[0]['estado']), (0, 'aplicada'))
eq('medición: lee disp_cambio de 1.000 en 1.000 hasta acabar', base.lecturas_cambio,
   [(0, 999), (1000, 1999), (2000, 2999)])
eq('medición: Funko', 'MEDICIÓN Funko: entran 1200 · vuelven 0 · salen 0 · a disponible 30 · a agotado 0 · cambian de '
                      'precio 0' in log, True)
eq('medición: Pyramid', 'MEDICIÓN Pyramid: entran 0 · vuelven 0 · salen 15 · a disponible 0 · a agotado 0 · cambian de '
                        'precio 900' in log, True)
eq('medición: total', 'MEDICIÓN Total: entran 1200 · vuelven 5 · salen 15 · a disponible 30 · a agotado 400 · cambian '
                      'de precio 900' in log, True)
eq('(C) medición: el registro no suelta datos', limpio_de_datos(log), [])
cod, log, base = correr(bueno, base=Base(cambios=_al_aplicar, descuadre=True))
eq('medición: si no cuadra con disp_pasada, ROJO y la pasada sigue aplicada',
   (cod, 'DBLINE_SIN_RECUENTOS' in log, 'entran 1200 ≠ n_entran 1201' in log, list(base.pasadas.values())[0]['estado']),
   (1, True, True, 'aplicada'))
cod, log, base = correr(bueno, base=Base(cambios=_al_aplicar, error_cambios=True))
eq('medición: si no se pueden leer los cambios, ROJO con el tipo y sin el texto',
   (cod, 'DBLINE_SIN_RECUENTOS' in log, '(RuntimeError)' in log, 'ZQ00001' in log), (1, True, True, False))
cod, log, base = correr(bueno, base=Base(ultima_huella=huella))
eq('medición: al día, ningún cambio', (cod, 'MEDICIÓN: al día' in log), (0, True))

# descargar_dbline.py DE VERDAD, con un curl_cffi de mentira que devuelve lo que diga cada caso.
XLSX = excel([fila('ZQ00001', Descrizione='Nombre inventado 1')])
SECRETO_RESPUESTA = 'RESPUESTA-SECRETA-DE-DBLINE'


class _Resp:
    def __init__(self, status, contenido):
        self.status_code, self.content = status, contenido
        self.text = contenido.decode('utf-8', 'replace')
        self.headers = {'content-type': 'text/html; tipo-secreto'}


class _Sesion:
    kwargs, descarga, enlazado, login = {}, b'', b'', b''

    def __init__(self, **k):
        _Sesion.kwargs = k

    def get(self, url, **_k):
        return _Resp(200, b'<html>home</html>') if url.endswith('/') else _Resp(200, _Sesion.enlazado)

    def post(self, _url, data=None, **_k):
        return _Resp(200, _Sesion.login) if data['action'] == 'ESEGUI_LOGIN' else _Resp(200, _Sesion.descarga)


def descargar_de_verdad(descarga, enlazado=b'', login=None, **kw):
    """(modulo, bytes, error, registro, kwargs de la sesion) de descargar_dbline.descargar_catalogo_dbline(**kw)."""
    falso = types.ModuleType('curl_cffi')
    falso.requests = types.SimpleNamespace(Session=_Sesion)
    guardados = {k: sys.modules.get(k) for k in ('curl_cffi', 'descargar_dbline')}
    viejo_env = {k: os.environ.get(k) for k in ('DBLINE_USER', 'DBLINE_PASS')}
    sys.modules['curl_cffi'] = falso
    sys.modules.pop('descargar_dbline', None)
    os.environ.update(DBLINE_USER=USUARIO, DBLINE_PASS=CLAVE)
    _Sesion.descarga, _Sesion.enlazado = descarga, enlazado
    _Sesion.login = login if login is not None else (
        f'{{"ok":1,"utente":"{USUARIO}","pw":"{CLAVE}","nota":"{SECRETO_RESPUESTA}"}}'.encode())
    salida, cont, err = io.StringIO(), None, None
    try:
        mod = importlib.import_module('descargar_dbline')
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            try:
                cont = mod.descargar_catalogo_dbline(**kw)
            except RuntimeError as e:
                err = str(e)
    finally:
        for k, v in guardados.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for k, v in viejo_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return mod, cont, err, salida.getvalue(), dict(_Sesion.kwargs)


PROHIBIDO_DESCARGA = (USUARIO, CLAVE, URL, 'tienda.invalid', 'abcdef0123456789', SECRETO_RESPUESTA, 'utente',
                      'tipo-secreto', 'ZQ0', 'Nombre inventado')

mod, cont, err, log, k = descargar_de_verdad(XLSX)
eq('descargar_dbline: por defecto SIN verificar (el director viejo, como hoy)', (k.get('verify'), err), (False, None))
eq('descargar_dbline: devuelve el .xlsx', (cont or b'')[:2], b'PK')
eq('descargar_dbline: el registro solo con códigos y bytes', [p for p in PROHIBIDO_DESCARGA if p in log], [])
eq('descargar_dbline: el registro dice los códigos', ('login -> 200' in log, 'descarga -> 200' in log), (True, True))
mod, cont, err, log, k = descargar_de_verdad(XLSX, verificar=mod.CADENA_DBLINE)
eq('descargar_dbline: con verificar=CADENA_DBLINE, la sesión valida contra la cadena', k.get('verify'), mod.CADENA_DBLINE)
_pem = open(mod.CADENA_DBLINE, encoding='utf-8').read()
eq('certificado: el fichero existe, con 3 certificados y sin claves', (_pem.count('-----BEGIN CERTIFICATE-----'),
                                                                     'PRIVATE' in _pem), (3, False))
_html = (f'<html>{SECRETO_RESPUESTA} <a href="{URL}">catalogo</a></html>').encode()
mod, cont, err, log, k = descargar_de_verdad(_html, enlazado=XLSX)
eq('descargar_dbline: con enlace a un .xlsx, lo baja', ((cont or b'')[:2], err), (b'PK', None))
eq('descargar_dbline: con enlace, ni la respuesta ni la URL al registro', [p for p in PROHIBIDO_DESCARGA if p in log], [])
mod, cont, err, log, k = descargar_de_verdad(f'<html>{SECRETO_RESPUESTA}</html>'.encode(),
                                             login=b'{"esito":"password errata"}')
eq('descargar_dbline (e): sin .xlsx, error que dice qué pasó con códigos y bytes',
   (err is not None, 'login 200 (parece que NO entra)' in (err or ''), 'descarga 200 (' in (err or ''),
    'sin enlace a un .xlsx' in (err or '')), (True, True, True, True))
eq('descargar_dbline (e): el error ya no manda a «mirar el log de arriba»', 'log de arriba' in (err or '').lower(), False)
eq('descargar_dbline (e): ni el error ni el registro sueltan datos',
   [p for p in PROHIBIDO_DESCARGA if p in (err or '') + log], [])

print()
if fallos:
    print('ROJO: %d comprobación(es) fallida(s):' % len(fallos))
    for f in fallos:
        print('  - ' + f)
    sys.exit(1)
print('VERDE: todas las comprobaciones pasan.')
