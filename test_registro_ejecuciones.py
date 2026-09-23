# -*- coding: utf-8 -*-
"""La linea del registro en cada procesador vigilado (encargo H, 23-sep-2026).

🔴 QUE COMPRUEBA. Que en los ocho `procesar-*.yml` que escriben en produccion a diario o
   cada semana, el ULTIMO paso del job apunta en `registro_ejecuciones` sin poder cambiar
   el resultado del job:
     · `if: always()`            → se apunta tambien el rojo y la cancelacion;
     · `continue-on-error: true` → un fallo al apuntar no pone el job en rojo;
     · `timeout-minutes` <= 2    → ni lo retrasa;
     · `R_RESULTADO: ${{ job.status }}` → el color es el REAL del job;
     · `DB_URL` es LA MISMA expresion que la del paso del procesador → la linea va a la
       misma base que la carga (staging o produccion), y sin credenciales nuevas.
   Y en `procesar-inventario-fba.yml`, el 2 bis: el paso del procesador tiene `id` y el
   paso final lee de su SALIDA las guardas saltadas (`guarda_4`, `guarda_10`).

🔑 POR ESTRUCTURA, NO POR TEXTO: se lee el YAML con pyyaml y se mira el ULTIMO paso de
   cada job. Que la llamada aparezca en el fichero no basta: un paso de registro que no
   es el ultimo no ve el color final.

🔒 Lo que NO ve: que la linea llegue a la base. Eso lo prueba el ensayo contra staging
   (workflow de prueba del encargo H) y la consulta en produccion despues de aplicar.
"""
import ast
import os
import re
import sys

import yaml

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_WF = os.path.join(RAIZ, '.github', 'workflows')
VIGILADOS = [
    'procesar-all-listings.yml', 'procesar-internacional.yml', 'procesar-inventario-fba.yml',
    'procesar-paneu-aptos.yml', 'procesar-ledger.yml', 'procesar-transacciones.yml',
    'procesar-keepa-escaparate.yml', 'procesar-custom-analytics.yml',
]
NOMBRE = 'Apuntar la ejecución en el registro'

fallos = []


def eq(nombre, got, exp):
    ok = got == exp
    if not ok:
        fallos.append(nombre)
    print('%s  %s%s' % ('OK' if ok else 'XX', nombre, '' if ok else '   got=%r exp=%r' % (got, exp)))


for fichero in VIGILADOS:
    with open(os.path.join(DIR_WF, fichero), encoding='utf-8') as fh:
        wf = yaml.safe_load(fh)
    pasos = wf['jobs']['procesar']['steps']
    ultimo = pasos[-1]
    procesador = [p for p in pasos if p.get('name') == 'Ejecutar procesador']
    eq('%s: hay UN paso «Ejecutar procesador»' % fichero, len(procesador), 1)
    procesador = procesador[0] if procesador else {}
    eq('%s: el ULTIMO paso es el del registro' % fichero, ultimo.get('name'), NOMBRE)
    eq('%s: y es el unico' % fichero, sum(1 for p in pasos if p.get('name') == NOMBRE), 1)
    eq('%s: corre siempre' % fichero, ultimo.get('if'), 'always()')
    eq('%s: un fallo al apuntar no cambia el color' % fichero, ultimo.get('continue-on-error'), True)
    tope = ultimo.get('timeout-minutes')
    eq('%s: tope corto (<= 2 min)' % fichero, isinstance(tope, int) and 0 < tope <= 2, True)
    env = ultimo.get('env') or {}
    eq('%s: apunta el color REAL del job' % fichero,
       re.fullmatch(r'\$\{\{\s*job\.status\s*\}\}', env.get('R_RESULTADO', '')) is not None, True)
    eq('%s: la cadena es la MISMA que la del procesador' % fichero,
       (env.get('DB_URL'), bool(env.get('DB_URL'))),
       ((procesador.get('env') or {}).get('DB_URL'), True))
    run = ultimo.get('run', '')
    eq('%s: llama a public.registrar_ejecucion con psql bajo timeout' % fichero,
       ('public.registrar_ejecucion(' in run, bool(re.search(r'\btimeout\s+\d+\s+psql\b', run))),
       (True, True))

# ── 2 bis · la guarda saltada llega de la SALIDA del paso del procesador ──────────────
with open(os.path.join(DIR_WF, 'procesar-inventario-fba.yml'), encoding='utf-8') as fh:
    inv = yaml.safe_load(fh)
pasos = inv['jobs']['procesar']['steps']
proc = next((p for p in pasos if p.get('name') == 'Ejecutar procesador'), {})
env = pasos[-1].get('env') or {}
eq('(2 bis) el paso del procesador tiene id', bool(proc.get('id')), True)
for g in ('guarda_4', 'guarda_10'):
    eq('(2 bis) el paso final lee %s de la SALIDA de ese paso' % g,
       re.sub(r'\s', '', env.get('R_' + g.upper(), '')),
       '${{steps.%s.outputs.%s}}' % (proc.get('id'), g))
# 🔴 Y NO del entorno: la mesa de pruebas corre antes en el mismo job y salta guardas a
#    proposito. Por $GITHUB_ENV esas lineas llegarian al registro como si fueran de la carga.
#    Se mira el ARBOL, no el texto: el docstring de la funcion nombra $GITHUB_ENV justo para
#    explicar por que no se usa, y un grep lo contaria.
with open(os.path.join(RAIZ, 'procesador_inventario_fba.py'), encoding='utf-8') as fh:
    arbol = ast.parse(fh.read())
fn = next((n for n in ast.walk(arbol)
           if isinstance(n, ast.FunctionDef) and n.name == 'dejar_constancia'), None)
leidas = sorted({c.args[0].value for c in ast.walk(fn or ast.Module(body=[], type_ignores=[]))
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                 and c.func.attr == 'get' and ast.unparse(c.func.value) == 'os.environ'
                 and c.args and isinstance(c.args[0], ast.Constant)})
eq('(2 bis) dejar_constancia escribe en GITHUB_OUTPUT, y en nada mas del entorno',
   leidas, ['GITHUB_OUTPUT'])
# Y las valvulas del boton van al registro aunque la guarda no llegue a saltar.
for v in ('permitir_umbral_bajo', 'permitir_salto'):
    eq('(2 bis) el paso final recibe la valvula %s del boton' % v,
       re.sub(r'\s', '', env.get('V_' + v.upper(), '')), '${{inputs.%s}}' % v)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · registro de ejecuciones en los procesadores')
