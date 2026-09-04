# -*- coding: utf-8 -*-
"""Comprueba que al acortar CLAUDE.md no se perdio ni se reescribio ninguna regla.

    python docs/reglas/cotejo.py [ref-git-del-CLAUDE.md-viejo]

Coge el CLAUDE.md ANTERIOR (por defecto, el de `origin/main`) y comprueba que
**cada linea con texto** sigue existiendo, caracter a caracter, en el CLAUDE.md
nuevo o en alguno de los docs/reglas/*.md. Sale con 0 si todo esta; con 1 y la
lista de lo que falta si no.

No mira el reparto ni el orden: mira que no falte NADA. Es la mitad que importa.
"""
import collections
import glob
import io
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUIDOS = {'COTEJO.md'}


def viejo(ref):
    out = subprocess.check_output(['git', 'show', '%s:CLAUDE.md' % ref], cwd=RAIZ)
    return out.decode('utf-8').replace('\r\n', '\n').split('\n')


def destinos():
    rutas = [os.path.join(RAIZ, 'CLAUDE.md')]
    for p in sorted(glob.glob(os.path.join(RAIZ, 'docs', 'reglas', '*.md'))):
        if os.path.basename(p) not in EXCLUIDOS:
            rutas.append(p)
    return rutas


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else 'origin/main'
    antes = viejo(ref)
    rutas = destinos()

    hay = collections.Counter()
    for r in rutas:
        for l in io.open(r, encoding='utf-8').read().replace('\r\n', '\n').split('\n'):
            hay[l] += 1

    quiero = collections.Counter(l for l in antes if l.strip())

    faltan = []
    for linea, n in quiero.items():
        if hay[linea] < n:
            faltan.append((hay[linea], n, linea))

    con_texto = sum(quiero.values())
    print('CLAUDE.md viejo (%s): %d lineas, %d con texto' % (ref, len(antes), con_texto))
    print('Destinos mirados: %s' % ', '.join(os.path.relpath(r, RAIZ).replace(os.sep, '/') for r in rutas))

    if faltan:
        print('\nFALTAN %d lineas del CLAUDE.md viejo:\n' % len(faltan))
        for tiene, pide, linea in faltan:
            print('  (aparece %d veces, hacen falta %d) %s' % (tiene, pide, linea[:110]))
        return 1

    print('\nOK: las %d lineas con texto del CLAUDE.md viejo siguen todas, literales.' % con_texto)
    return 0


if __name__ == '__main__':
    sys.exit(main())
