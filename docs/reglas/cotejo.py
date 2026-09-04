# -*- coding: utf-8 -*-
"""Comprueba que al acortar CLAUDE.md no se perdio ni se reescribio ninguna regla.

    python docs/reglas/cotejo.py [ref-git-de-la-BASE]

Coge el CLAUDE.md ENTERO de la BASE y comprueba que **cada linea con texto**
sigue existiendo, caracter a caracter, en el CLAUDE.md nuevo o en alguno de los
docs/reglas/*.md. Sale con 0 si todo esta; con 1 y la lista de lo que falta si no.

No mira el reparto ni el orden: mira que no falte NADA. Es la mitad que importa.

LA BASE POR DEFECTO ES UN SHA FIJO, Y NO ES UN CAPRICHO
-------------------------------------------------------
Antes el defecto era `origin/main`, y el dia que el recorte se fusiono ese
defecto empezo a MENTIR: coge el CLAUDE.md de main --que ya es el CORTO-- y
comprueba que sus lineas siguen estando... en el corto. Sale verde siempre.
Medido el 4-sep-2026: decia «OK: las 107 lineas con texto del CLAUDE.md viejo
siguen todas, literales», y las 107 eran las del propio fichero que tenia que
estar auditando. Es la comprobacion que no puede fallar: se comparan dos cosas
que son iguales por construccion.

Por eso la base por defecto es BASE_ENTERA, el ULTIMO commit con el CLAUDE.md
entero (66.580 caracteres, 849 lineas, 796 con texto). Se puede pasar otra ref
por la linea de comandos --para cotejar contra un recorte intermedio, por
ejemplo--, pero:

🔴 SI EL CLAUDE.md DE LA BASE TIENE MENOS DE `MINIMO` CARACTERES, EL SCRIPT SE
   PONE EN ROJO Y NO COTEJA NADA. Un fichero de ese tamano ya no es el entero,
   asi que el cotejo no probaria nada y su verde seria de adorno. Vale mas un
   rojo que se entiende que un OK que no ha medido.
"""
import collections
import glob
import io
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUIDOS = {'COTEJO.md'}

# El ultimo commit con el CLAUDE.md entero, antes de repartirlo en docs/reglas/.
BASE_ENTERA = '0d1710a'

# Por debajo de esto, lo que se pasa como base NO es el fichero entero.
# El entero son 66.580 caracteres; el corto de hoy ronda los 8.200. El liston
# esta a media distancia a proposito: no hay nada legitimo entre medias.
MINIMO = 40000


def texto_de_la_base(ref):
    out = subprocess.check_output(['git', 'show', '%s:CLAUDE.md' % ref], cwd=RAIZ)
    return out.decode('utf-8').replace('\r\n', '\n')


def destinos():
    rutas = [os.path.join(RAIZ, 'CLAUDE.md')]
    for p in sorted(glob.glob(os.path.join(RAIZ, 'docs', 'reglas', '*.md'))):
        if os.path.basename(p) not in EXCLUIDOS:
            rutas.append(p)
    return rutas


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else BASE_ENTERA
    crudo = texto_de_la_base(ref)
    antes = crudo.split('\n')

    print('Base: %s%s' % (ref, '  (la de por defecto)' if len(sys.argv) <= 1 else ''))
    print('CLAUDE.md de la base: %d caracteres, %d lineas' % (len(crudo), len(antes)))

    if len(crudo) < MINIMO:
        print('')
        print('ROJO - ESTA BASE NO SIRVE: su CLAUDE.md tiene %d caracteres y el minimo son %d.'
              % (len(crudo), MINIMO))
        print('   Con menos de eso ya no es el fichero ENTERO, sino uno ya recortado, y')
        print('   entonces el cotejo se compara consigo mismo y sale verde mida lo que mida.')
        print('   La base buena es %s, que es la de por defecto: corre el script sin argumentos.'
              % BASE_ENTERA)
        return 1

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
    print('Lineas con texto que hay que encontrar: %d' % con_texto)
    print('Destinos mirados: %s' % ', '.join(os.path.relpath(r, RAIZ).replace(os.sep, '/') for r in rutas))

    if faltan:
        print('\nFALTAN %d lineas del CLAUDE.md de la base:\n' % len(faltan))
        for tiene, pide, linea in faltan:
            print('  (aparece %d veces, hacen falta %d) %s' % (tiene, pide, linea[:110]))
        return 1

    print('\nOK: las %d lineas con texto del CLAUDE.md de la base siguen todas, literales.'
          % con_texto)
    return 0


if __name__ == '__main__':
    sys.exit(main())
