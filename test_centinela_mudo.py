# -*- coding: utf-8 -*-
"""Banco: el centinela avisa cuando un director lleva horas sin escribir.

EL FALLO QUE CIERRA (9 y 10-sep-2026). Los cuatro directores se quedaron sin
poder leer `productos` y empezaron a morir en el arranque. DBLine dejo de
escribir el 9-sep a las 10:31 UTC y OcioStock a las 15:01; no se supo hasta el
10-sep por la tarde. DOS DIAS con «Que reponer» y el trackeador ensenando el
catalogo de anteayer con toda la cara de estar al dia. El run de cada director
salia rojo en Actions, pero un rojo en Actions no llega a donde esta Fernando.

LA TRAMPA DE ESTE CONTROL, Y COMO SE ESQUIVA. Los tres proveedores de fichero NO
trabajan los domingos (medido: cero pasadas en cuatro domingos seguidos), asi que
su hueco normal mas largo es el del sabado al lunes: 44 h en DBLine. Un umbral en
horas BRUTAS tendria que ser de 50 h para no dar un aviso falso cada lunes -- o
sea, justo los dos dias de silencio que se vienen a evitar. Descontando las horas
de domingo, ese mismo hueco son 23 h y la X puede bajar a 26.

QUE SE PRUEBA, Y COMO:
  (A) LAS TRES FUNCIONES REALES, sacadas de `centinela_escaner.py` con `ast` (POR
      ESTRUCTURA, no con un grep) y EJECUTADAS con las fechas del apagon de
      verdad y con un sabado-a-lunes de verdad.
  (B) POR ESTRUCTURA: que la tabla de horarios cubra EXACTAMENTE los directores
      que existen en `.github/workflows`. Un director nuevo que naciera sin su
      linea aqui seria un proveedor sin centinela, y el centinela saldria verde
      sin mirarlo -- que es la forma que tiene esta clase de control de mentir.
      Y que la X de cada uno este POR ENCIMA del hueco mayor medido: una X por
      debajo es un aviso falso cada semana, y un aviso falso semanal se aprende a
      ignorar en quince dias.
  (C) DE PUNTA A PUNTA, tres veces, cada una en su PROCESO, con `supabase` y
      `requests` sustituidos por dobles en memoria (sin red, sin secretos):
        1. [al_dia]  los cuatro escribieron hace 2 h -> exit 0, CERO Telegram.
        2. [mudo]    DBLine lleva 200 h callado -> exit 1, UN Telegram que le
                     nombra, y la etiqueta grepable CENTINELA_MUDO.
        3. [ilegible] la lectura revienta -> exit 1: no saber no es estar bien.
      Y en los TRES, las CUATRO lineas del informe tienen que salir. Un centinela
      que solo escribe cuando salta no se puede auditar: el dia que calla no se
      distingue "estan todos al dia" de "no llego a mirar".
  (D) LAS DOS DIRECCIONES del descuento del domingo: el MISMO sabado-a-lunes sale
      "al dia" para quien descansa el domingo y MUDO para quien no. Sin ese
      contraste, (A) saldria verde tambien con un descuento que no descontara
      nada.

Las horas del caso [mudo] son 200 a proposito (mas de ocho dias) y no 40: con 40,
este banco cambiaria de resultado segun el dia de la semana en que se corriera.
"""
import ast
import io
import json
import os
import re
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone

RUTA = 'centinela_escaner.py'


# ===========================================================================
# EL HIJO: monta los dobles y corre el centinela de punta a punta
# ===========================================================================
def hijo(caso):
    import atexit

    ENVIADOS = []
    HORAS = {'al_dia': {'DBLINE': 2, 'HEO': 2, 'OCIOSTOCK': 2, 'TCG': 2},
             'mudo': {'DBLINE': 200, 'HEO': 2, 'OCIOSTOCK': 2, 'TCG': 2}}.get(caso, {})

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, tabla):
            self.tabla = tabla
            self.proveedor = None

        def eq(self, col, val):
            if col == 'proveedor':
                self.proveedor = val
            return self

        def __getattr__(self, nombre):
            return lambda *a, **k: self       # select, order, limit…

        def execute(self):
            if caso == 'ilegible':
                raise Exception('doble: la lectura revienta a proposito')
            horas = HORAS.get(self.proveedor)
            if horas is None:
                return _Resp([])
            fecha = datetime.now(timezone.utc) - timedelta(hours=horas)
            return _Resp([{'fecha': fecha.isoformat()}])

    class _Cliente:
        def table(self, nombre):
            return _Query(nombre)

    def _post(url, data=None, timeout=None):
        ENVIADOS.append({'url': url, 'texto': (data or {}).get('text', '')})
        return types.SimpleNamespace(status_code=200)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda url, key: _Cliente()
    sys.modules['requests'] = types.ModuleType('requests')
    sys.modules['requests'].post = _post

    os.environ['SUPABASE_URL'] = 'https://doble.local'
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    os.environ['TELEGRAM_TOKEN'] = 'FAKE-TG'
    os.environ['TELEGRAM_CHAT_ID'] = '123'

    @atexit.register
    def _informe():
        print('TELEGRAMS=%d' % len(ENVIADOS))
        print('TELEGRAM_TEXTO=%s' % json.dumps('\n'.join(e['texto'] for e in ENVIADOS)))

    import runpy
    runpy.run_path(RUTA, run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2])
    sys.exit(0)


# ===========================================================================
# EL PADRE: los asserts
# ===========================================================================
FUENTE = io.open(RUTA, encoding='utf-8').read()
ARBOL = ast.parse(FUENTE, RUTA)
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def _nodo(nombre):
    for n in ARBOL.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return n
    print('XX %s ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


NOMBRES = ('horas_en_domingo', 'horas_de_silencio', 'esta_mudo')
_ns = {'timedelta': timedelta}
exec(compile(ast.fix_missing_locations(ast.Module(body=[_nodo(n) for n in NOMBRES],
                                                  type_ignores=[])), RUTA, 'exec'), _ns)
horas_en_domingo = _ns['horas_en_domingo']
horas_de_silencio = _ns['horas_de_silencio']
esta_mudo = _ns['esta_mudo']
HORARIOS = ast.literal_eval(_nodo('HORARIOS').value)
print('extraidas de %s: %s, HORARIOS' % (RUTA, ', '.join(NOMBRES)))
print()


def utc(txt):
    return datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# (A) Las funciones REALES, con las fechas de verdad
# ---------------------------------------------------------------------------
# El sabado-a-lunes de DBLine, tal cual: sabado 5-sep 11:00 -> lunes 7-sep 06:00.
SAB, LUN = utc('2026-09-05T11:00:00'), utc('2026-09-07T06:00:00')
eq('(A) el sabado-a-lunes son 43 h de reloj',
   round((LUN - SAB).total_seconds() / 3600.0, 2), 43.0)
eq('(A) 🔴 y 24 de ellas caen en domingo', horas_en_domingo(SAB, LUN), 24.0)
eq('(A) 🔴 asi que para quien descansa el domingo son 19 h de silencio',
   horas_de_silencio(SAB, LUN, True), 19.0)
eq('(A) un tramo sin domingo por medio no descuenta nada',
   horas_en_domingo(utc('2026-09-09T10:00:00'), utc('2026-09-10T15:00:00')), 0.0)
eq('(A) un tramo dentro del propio domingo se descuenta entero',
   horas_en_domingo(utc('2026-09-06T02:00:00'), utc('2026-09-06T08:30:00')), 6.5)
eq('(A) tres semanas descuentan tres domingos',
   horas_en_domingo(utc('2026-08-17T00:00:00'), utc('2026-09-07T00:00:00')), 72.0)
eq('(A) el reloj al reves no da horas negativas',
   horas_de_silencio(LUN, SAB, True), 0.0)
eq('(A) sin dato, mudo: no saber no es estar bien', esta_mudo(None, 26), True)

# EL APAGON DE VERDAD. DBLine escribio por ultima vez el miercoles 9-sep a las
# 10:31 UTC. Sin domingo por medio: horas brutas = horas de silencio.
APAGON = utc('2026-09-09T10:31:00')
_x_dbline = HORARIOS['DBLINE']['umbral_h']
eq('(A) 🔴 [apagon] el 10-sep a las 12:00 UTC aun no ha vencido el plazo',
   esta_mudo(horas_de_silencio(APAGON, utc('2026-09-10T12:00:00'), True), _x_dbline), False)
eq('(A) 🔴 [apagon] y a las 14:00 UTC del 10-sep SI: 27,5 h > 26',
   (round(horas_de_silencio(APAGON, utc('2026-09-10T14:00:00'), True), 2),
    esta_mudo(horas_de_silencio(APAGON, utc('2026-09-10T14:00:00'), True), _x_dbline)),
   (27.48, True))

# ---------------------------------------------------------------------------
# (D) Las dos direcciones del descuento: el MISMO hueco, los DOS calendarios
# ---------------------------------------------------------------------------
print()
eq('(D) 🔴 el sabado-a-lunes NO es mudo para quien descansa el domingo (19 h)',
   esta_mudo(horas_de_silencio(SAB, LUN, True), _x_dbline), False)
eq('(D) 🔴 y el MISMO hueco SI es mudo para quien no descansa (43 h)',
   esta_mudo(horas_de_silencio(SAB, LUN, False), HORARIOS['TCG']['umbral_h']), True)

# ---------------------------------------------------------------------------
# (B) La tabla cubre los directores que existen, y con margen
# ---------------------------------------------------------------------------
print()
_dir = os.path.join('.github', 'workflows')
_directores = sorted(f[len('director-'):-len('.yml')].upper()
                     for f in os.listdir(_dir)
                     if f.startswith('director-') and f.endswith('.yml'))
print('    directores en .github/workflows: %s' % ', '.join(_directores))
eq('(B) 🔴 hay directores que mirar, no cero', len(_directores) > 0, True)
eq('(B) 🔴 la tabla de horarios cubre EXACTAMENTE los directores que existen',
   sorted(HORARIOS), _directores)
for _p in sorted(HORARIOS):
    _cfg = HORARIOS[_p]
    eq('(B) [%s] 🔴 la X (%d h) esta por encima del hueco mayor medido (%.2f h)'
       % (_p, _cfg['umbral_h'], _cfg['medido_h']), _cfg['umbral_h'] > _cfg['medido_h'], True)
    eq('(B) [%s] …y el margen no pasa de 6 h (una X floja no avisa a tiempo)' % _p,
       _cfg['umbral_h'] - _cfg['medido_h'] <= 6, True)

# ---------------------------------------------------------------------------
# (C) De punta a punta, tres veces, cada una en su proceso
# ---------------------------------------------------------------------------
print()


def correr(caso):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout or '') + (p.stderr or '')
    _n = re.search(r'^TELEGRAMS=(\d+)\s*$', out, re.M)
    _t = re.search(r'^TELEGRAM_TEXTO=(.*)$', out, re.M)
    return {'codigo': p.returncode, 'salida': out,
            'telegrams': int(_n.group(1)) if _n else -1,
            'texto': json.loads(_t.group(1)) if _t else '',
            'lineas': len(re.findall(r'^  \w+ *(?:ultima|SIN DATO)', out, re.M))}


_ok = correr('al_dia')
eq('(C) [al_dia] 🔴 el run sale VERDE (exit 0)', _ok['codigo'], 0)
eq('(C) [al_dia] 🔴 y NO se manda ningun Telegram', _ok['telegrams'], 0)
eq('(C) [al_dia] las CUATRO lineas del informe estan en el log', _ok['lineas'], 4)
eq('(C) [al_dia] con su linea de conforme',
   'CENTINELA OK: los 4 directores han escrito dentro de su plazo.' in _ok['salida'], True)

_mudo = correr('mudo')
eq('(C) [mudo] 🔴 el run sale en ROJO (exit 1)', _mudo['codigo'], 1)
eq('(C) [mudo] 🔴 con la etiqueta grepable, y nombrando a DBLINE',
   'CENTINELA_MUDO: DBLINE' in _mudo['salida'], True)
eq('(C) [mudo] 🔴 se manda UN Telegram, ni cero ni dos', _mudo['telegrams'], 1)
eq('(C) [mudo] 🔴 y el aviso nombra al que se ha callado', 'DBLINE' in _mudo['texto'], True)
eq('(C) [mudo] …y NO nombra a los que estan al dia',
   ('HEO' in _mudo['texto'], 'TCG' in _mudo['texto']), (False, False))
eq('(C) [mudo] las CUATRO lineas siguen estando: tambien las de los que hablan',
   _mudo['lineas'], 4)

_ileg = correr('ilegible')
eq('(C) [ilegible] 🔴 el run sale en ROJO (exit 1)', _ileg['codigo'], 1)
eq('(C) [ilegible] 🔴 y el log dice que no se pudo leer',
   'no se pudo leer' in _ileg['salida'], True)
eq('(C) [ilegible] los cuatro salen como SIN DATO, no como al dia',
   _ileg['salida'].count('SIN DATO'), 4)
eq('(C) [ilegible] y se avisa por Telegram: un centinela ciego no puede callarse',
   _ileg['telegrams'], 1)

# ---------------------------------------------------------------------------
print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK (el proveedor mudo se detecta, y el domingo no da falsos avisos)')
