# -*- coding: utf-8 -*-
"""CANDADO del CLAUDE.md. Nace el 4-sep-2026, con el recorte de 66.580 a 8.294 caracteres.

POR QUE EXISTE, y no es teorico: este fichero entra ENTERO en cada llamada. Engordo
hasta 66.580 caracteres una linea cada vez, y ninguna de esas lineas estaba de mas por
si sola -- el problema es que nadie media la suma. Un techo escrito en un parte se
olvida; un techo con un test detras para el CI.

Y EL SEGUNDO AGUJERO, que es el que de verdad rompe el reparto: el indice del final del
CLAUDE.md promete que cada regla que salio tiene su fichero en docs/reglas/ y que se sabe
cuando abrirlo. Si esa promesa se descuadra --una fila que apunta a un fichero que ya no
esta, o un fichero que nadie nombra-- el recorte deja de ser "mover" y pasa a ser
"esconder", y no se entera nadie. Por eso se mira en LOS DOS SENTIDOS: fila sin fichero,
y fichero sin fila. Preguntar solo por uno saldria verde con la mitad del indice roto.

Falla si:
  1. CLAUDE.md pasa de TECHO caracteres.
  2. Una fila del indice apunta a un docs/reglas/*.md que no existe.
  3. Un docs/reglas/*.md no tiene fila en el indice.

Lo que NO hace: no mira el contenido de las reglas. Eso es docs/reglas/cotejo.py, que es
otra pregunta y tiene su propia base.

Se corre solo:  python -u test_claude_md_candado.py
"""
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# El techo. Subirlo es una decision de Fernando, no un arreglo: lo que sobre se MUEVE a
# docs/reglas/ (literal, sin resumir) y se le pone su fila en el indice.
TECHO = 8300

# COTEJO.md se enlaza en la prosa del CLAUDE.md, no en el indice, y no es una regla: es
# la prueba del reparto. Va fuera de las DOS listas, no solo de una -- si estuviera fuera
# de una sola, la comprobacion gritaria para siempre y se aprenderia a ignorarla.
# cotejo.py no entra porque aqui solo se miran los .md.
SIN_FILA = {'COTEJO.md'}


def main():
    print('-- test_claude_md_candado (el CLAUDE.md no engorda y el indice no miente) --')
    fallos = []

    def ok(m):
        print('OK  ' + m)

    def ko(m):
        fallos.append(m)
        print('XX  ' + m)

    texto = io.open(os.path.join(RAIZ, 'CLAUDE.md'), encoding='utf-8').read().replace('\r\n', '\n')

    # -- 1) el techo -------------------------------------------------------
    # len() sobre str cuenta CARACTERES (code points), que es en lo que se negocio el
    # techo. Ojo si esto se porta a JavaScript: alli `.length` cuenta unidades UTF-16 y
    # cada emoji astral (los 🔴 🔑 🔒 de este fichero) cuenta DOS. Medido el 4-sep-2026
    # en el repo hermano: 7.989 contra 7.977, doce de diferencia.
    largo = len(texto)
    if largo > TECHO:
        ko('CLAUDE.md tiene %d caracteres y el techo son %d: SOBRAN %d.' % (largo, TECHO, largo - TECHO))
        print('    Lo que sobre se MUEVE a docs/reglas/ con su fila en el indice, no se resume.')
    else:
        ok('CLAUDE.md cabe: %d <= %d caracteres (margen %d)' % (largo, TECHO, TECHO - largo))

    # -- 2) y 3) el indice contra docs/reglas/, en los DOS sentidos --------
    # Por ESTRUCTURA, no por texto: solo se miran las lineas que son fila de tabla, y de
    # cada una el destino del enlace. Un docs/reglas/x.md suelto en un parrafo no cuenta
    # como fila, que es justo lo que se quiere.
    filas = set()
    for linea in texto.split('\n'):
        if not linea.lstrip().startswith('|'):
            continue
        for m in re.finditer(r'docs/reglas/([^)\s|]+\.md)', linea):
            filas.add(m.group(1))
    filas -= SIN_FILA

    ficheros = set(f for f in os.listdir(os.path.join(RAIZ, 'docs', 'reglas'))
                   if f.endswith('.md') and f not in SIN_FILA)

    fila_sin_fichero = sorted(filas - ficheros)
    fichero_sin_fila = sorted(ficheros - filas)

    if fila_sin_fichero:
        ko('el indice apunta a ficheros que NO existen: %s' % ', '.join(fila_sin_fichero))
    else:
        ok('las %d filas del indice apuntan a un fichero que existe' % len(filas))

    if fichero_sin_fila:
        ko('hay ficheros en docs/reglas/ SIN fila en el indice: %s' % ', '.join(fichero_sin_fila))
    else:
        ok('los %d ficheros de docs/reglas/ tienen su fila' % len(ficheros))

    print('')
    print('CANDADO OK' if not fallos else '%d FALLOS' % len(fallos))
    return 1 if fallos else 0


if __name__ == '__main__':
    sys.exit(main())
