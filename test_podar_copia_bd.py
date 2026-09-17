# -*- coding: utf-8 -*-
"""Banco de `podar_copia_bd.py`: quien se conserva, quien se borra, y las dos
guardas que hacen que "no se puede leer" gane a "borra lo que se pueda".

🔴 EL CASO QUE JUSTIFICA ESTE FICHERO: es un borrado de la ULTIMA copia de
   seguridad que le queda a la v1 en `bd/`. Un fallo aqui no pierde un CSV
   reprocesable (como en `comprimir_keepa_antiguos.py`): pierde un volcado de
   la base que nadie más tiene. Por eso las dos guardas (menos de 4 objetos,
   o un nombre que no se puede leer) SUSPENDEN entero el borrado, no lo
   recortan fichero a fichero como la guarda de R2 del compresor.

🔒 Y LAS DOS DIRECCIONES: cada guarda se prueba tambien ROTA.
"""
import contextlib
import io
import os
import sys
from datetime import date, datetime

from podar_copia_bd import (analizar_listado, construir_plan, elegir_conservar,
                            parsear_nombre)

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(f'{"OK " if ok else "XX "} {nombre}'
          + ('' if ok else f'   got={obtenido!r} exp={esperado!r}'))


# --- (A) parsear_nombre ------------------------------------------------------
eq('(A) un nombre normal se parsea', parsear_nombre('moloka_2026-09-10_0215.sql.gz'),
   datetime(2026, 9, 10, 2, 15))
eq('(A) 🔴 sin la extension exacta -> None', parsear_nombre('moloka_2026-09-10_0215.sql'), None)
eq('(A) 🔴 otro prefijo -> None', parsear_nombre('backup_2026-09-10_0215.sql.gz'), None)
eq('(A) 🔴 fecha imposible -> None (no revienta)', parsear_nombre('moloka_2026-13-40_9999.sql.gz'), None)
eq('(A) 🔴 nombre vacio -> None', parsear_nombre(''), None)
eq('(A) 🔴 None -> None', parsear_nombre(None), None)
eq('(A) un fichero de la v2 con OTRO prefijo no casa (v1/v2 no se mezclan)',
   parsear_nombre('moloka_v2_2026-09-10_0215.sql.gz'), None)

# --- (B) analizar_listado: separa validos de invalidos -----------------------
volcados, invalidos = analizar_listado([
    ('moloka_2026-09-01_0215.sql.gz', 100),
    ('moloka_2026-09-08_0215.sql.gz', 200),
    ('un_fichero_suelto.txt', 50),
])
eq('(B) los que casan entran a volcados', [v['nombre'] for v in volcados],
   ['moloka_2026-09-01_0215.sql.gz', 'moloka_2026-09-08_0215.sql.gz'])
eq('(B) 🔴 el que no casa entra a invalidos, no se ignora', invalidos, ['un_fichero_suelto.txt'])
eq('(B) el tamaño se conserva', volcados[0]['tam'], 100)

# --- (C) elegir_conservar: el mas cercano a cada offset -----------------------
def v(nombre, tam=1000):
    return {'nombre': nombre, 'fecha': parsear_nombre(nombre), 'tam': tam}


HOY = date(2026, 9, 17)
# Uno por semana, de sobra separados: 7, 15 y 21 dias atras caen limpios.
_serie = [v('moloka_2026-09-10_0215.sql.gz'),   # hace 7 dias exactos
          v('moloka_2026-09-02_0215.sql.gz'),   # hace 15 dias exactos
          v('moloka_2026-08-27_0215.sql.gz'),   # hace 21 dias exactos
          v('moloka_2026-09-16_0215.sql.gz')]   # hace 1 dia (no deberia salir elegido)
elegido = elegir_conservar(_serie, HOY)
eq('(C) el de hace 7 dias exactos gana el offset 7',
   elegido[7]['nombre'], 'moloka_2026-09-10_0215.sql.gz')
eq('(C) el de hace 15 dias exactos gana el offset 15',
   elegido[15]['nombre'], 'moloka_2026-09-02_0215.sql.gz')
eq('(C) el de hace 21 dias exactos gana el offset 21',
   elegido[21]['nombre'], 'moloka_2026-08-27_0215.sql.gz')

# 🔴 EMPATE: dos volcados a la misma distancia de un objetivo -> gana el mas
#    antiguo (determinista, no "el que salga primero en la lista").
_empate = [v('moloka_2026-09-09_0215.sql.gz'),   # hace 8 dias
           v('moloka_2026-09-11_0215.sql.gz')]   # hace 6 dias -> las dos a 1 dia del objetivo (7)
elegido_empate = elegir_conservar(_empate, HOY, offsets=(7,))
eq('(C) 🔴 empate a distancia -> gana el mas antiguo, no el ultimo de la lista',
   elegido_empate[7]['nombre'], 'moloka_2026-09-09_0215.sql.gz')

# Sin candidatos -> None, no revienta.
eq('(C) sin volcados -> None para cada offset', elegir_conservar([], HOY)[7], None)

# --- (D) construir_plan: las DOS guardas, y que se para TODO -----------------
_pocos = [v(f'moloka_2026-09-{d:02d}_0215.sql.gz') for d in (1, 2, 3)]
plan_pocos = construir_plan(_pocos, [], HOY, minimo=4)
eq('(D) 🔴 menos de 4 volcados -> ok=False', plan_pocos['ok'], False)
eq('(D) … y no calcula nada', (plan_pocos['conservar'], plan_pocos['borrar']), ([], []))
eq('(D) … y lo dice', 'minimo 4' in plan_pocos['motivo'], True)

_con_invalido = [v(f'moloka_2026-09-{d:02d}_0215.sql.gz') for d in (1, 2, 3, 4, 5)]
plan_invalido = construir_plan(_con_invalido, ['rareza.csv'], HOY, minimo=4)
eq('(D) 🔴 UN invalido basta para que ok=False, aunque haya 5 volcados', plan_invalido['ok'], False)
eq('(D) … y dice CUAL', 'rareza.csv' in plan_invalido['motivo'], True)
eq('(D) … y no toca nada aunque la lista de validos sea de sobra',
   (plan_invalido['conservar'], plan_invalido['borrar']), ([], []))

# La direccion VERDE: con 4+ volcados y ninguno invalido, SI calcula.
plan_ok = construir_plan(_serie, [], HOY, minimo=4)
eq('(D) 4 volcados sin invalidos -> ok=True', plan_ok['ok'], True)
eq('(D) se conservan los 3 (uno por offset, sin empates aqui)', len(plan_ok['conservar']), 3)
eq('(D) y se borra el resto (el de "hace 1 dia")', [b['nombre'] for b in plan_ok['borrar']],
   ['moloka_2026-09-16_0215.sql.gz'])

# 🔴 UN VOLCADO PUEDE SER EL MAS CERCANO A DOS OFFSETS A LA VEZ -> se
#    conservan MENOS de tres, y el plan lo dice con sus dos offsets.
_disperso = [v('moloka_2026-09-10_0215.sql.gz'),   # el unico candidato real
             v('moloka_2026-08-01_0215.sql.gz'),
             v('moloka_2026-07-01_0215.sql.gz'),
             v('moloka_2026-06-01_0215.sql.gz')]
plan_disperso = construir_plan(_disperso, [], HOY, minimo=4, offsets=(7, 8))
eq('(D) 🔴 un mismo volcado puede cubrir DOS offsets -> se conservan menos de N',
   len(plan_disperso['conservar']), 1)
eq('(D) … y el plan dice los dos offsets que cubre',
   sorted(plan_disperso['conservar'][0]['offsets']), [7, 8])

# --- (E) El CLI: stdin -> informe + fichero de borrado ------------------------
print("\n(E) el CLI, ejecutando main() de verdad")
import podar_copia_bd as _mod                                        # noqa: E402


def correr_cli(texto_stdin, hoy=None, salida_borrar=None):
    old_stdin, old_env = sys.stdin, dict(os.environ)
    sys.stdin = io.StringIO(texto_stdin)
    if hoy:
        os.environ['HOY'] = hoy
    else:
        os.environ.pop('HOY', None)
    if salida_borrar:
        os.environ['SALIDA_BORRAR'] = salida_borrar
    else:
        os.environ.pop('SALIDA_BORRAR', None)
    buf, codigo = io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(buf):
            _mod.main()
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.stdin = old_stdin
        os.environ.clear(); os.environ.update(old_env)
    return codigo, buf.getvalue()


_tsv_ok = '\n'.join([
    'moloka_2026-09-10_0215.sql.gz\t100',
    'moloka_2026-09-02_0215.sql.gz\t200',
    'moloka_2026-08-27_0215.sql.gz\t300',
    'moloka_2026-09-16_0215.sql.gz\t400',
]) + '\n'

_tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_tmp_a_borrar.txt')
try:
    cod, txt = correr_cli(_tsv_ok, hoy='2026-09-17', salida_borrar=_tmp)
    eq('(E) con 4 volcados validos, el CLI termina en 0', cod, 0)
    eq('(E) … y lista lo que conserva, con fechas y tamaños',
       'CONSERVAR (3)' in txt and 'MB' in txt, True)
    eq('(E) … y lo que borraria', 'BORRAR (1)' in txt, True)
    with io.open(_tmp, encoding='utf-8') as fh:
        eq('(E) … y escribe el fichero de borrado con ESE nombre',
           fh.read().strip(), 'moloka_2026-09-16_0215.sql.gz')
finally:
    if os.path.exists(_tmp):
        os.remove(_tmp)

# 🔴 Guarda ROJA por el CLI: con menos de 4, el 0 del disco NO se toca.
_tsv_pocos = '\n'.join([
    'moloka_2026-09-10_0215.sql.gz\t100',
    'moloka_2026-09-02_0215.sql.gz\t200',
]) + '\n'
try:
    cod, txt = correr_cli(_tsv_pocos, hoy='2026-09-17', salida_borrar=_tmp)
    eq('(E) 🔴 con menos de 4, el CLI termina en 1', cod, 1)
    eq('(E) … y lo dice en el log', 'GUARDA' in txt, True)
    eq('(E) 🔴 … y el fichero de borrado queda VACIO, no ausente ni con basura',
       os.path.exists(_tmp) and io.open(_tmp, encoding='utf-8').read() == '', True)
finally:
    if os.path.exists(_tmp):
        os.remove(_tmp)

# 🔴 Guarda ROJA por nombre ilegible: una linea que no es "nombre\tbytes".
_tsv_raro = 'moloka_2026-09-10_0215.sql.gz\t100\nnombre_sin_tabulador\n' \
            'moloka_2026-09-02_0215.sql.gz\t200\nmoloka_2026-08-27_0215.sql.gz\t300\n'
cod, txt = correr_cli(_tsv_raro, hoy='2026-09-17')
eq('(E) 🔴 una linea sin tabulador tambien hace saltar la guarda', cod, 1)
eq('(E) … y la nombra', 'nombre_sin_tabulador' in txt, True)

print()
if fallos:
    print(f'❌ {len(fallos)} FALLOS: ' + ', '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
