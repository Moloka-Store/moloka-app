# -*- coding: utf-8 -*-
"""Cómo se lee un TSV de Amazon: la comilla es TEXTO, no entrecomillado.

🔬 Los cuatro casos salieron de un banco sintético ANTES de tocar ningún procesador, y el
   tercero es el que cambió la decisión: con `QUOTE_NONE` un campo entero entre comillas
   conserva las comillas dentro del valor. Eso no se ve contando filas — el recuento es el
   mismo — y es lo que dejó al LEDGER fuera del cambio.

🔒 Y el caso del ledger va aquí como test, no como nota: 🔬 medido el 21-ago-2026 sobre sus
   10 ficheros del buzón, TODAS las celdas cambian de valor con QUOTE_NONE porque el
   informe trae cada campo entrecomillado. Una nota se olvida; este test se pone rojo.
"""
import csv
import io
import sys

from tsv_comun import leer_tsv

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(f'{"OK " if ok else "XX "} {nombre}'
          + ('' if ok else f'   got={obtenido!r} exp={esperado!r}'))


def hoy(texto):
    """El parseo de ANTES, para poder contrastar. No se usa en producción."""
    return list(csv.reader(io.StringIO(texto), delimiter='\t'))


print('== TSV de Amazon · la comilla es texto ==')

# ── A) 🔴 EL CASO QUE ESTO VIENE A EVITAR ──────────────────────────────────
# Una comilla que ABRE un campo y no cierra se come los tabuladores y el salto de línea:
# el lector de hoy devuelve DOS filas donde hay tres, y no da ningún error.
A = 'sku\tnombre\tuds\nA1\t"Funko POP 10 Deluxe\t5\nA2\tOtro\t7\n'
eq('(A) 🔴 el parseo de hoy FUSIONA filas', len(hoy(A)), 2)
eq('(A) 🔴 … y `leer_tsv` no', len(list(leer_tsv(A))), 3)
eq('(A) 🔒 … con la fila entera en su sitio',
   list(leer_tsv(A))[1], ['A1', '"Funko POP 10 Deluxe', '5'])
# 🔒 Y la tercera fila EXISTE, que es lo que se perdía. Sin este assert, «3 filas» podría
#    ser cualquier reparto.
eq('(A) 🔒 … y la que se perdía vuelve', list(leer_tsv(A))[2], ['A2', 'Otro', '7'])

# ── B) 🔒 LA COMILLA DE LAS PULGADAS ES INOFENSIVA ────────────────────────
# `Funko POP! 10" Deluxe` — la comilla va EN MEDIO del campo, no al principio, y ni el
# lector de hoy ni el nuevo se despistan. Es el caso más común y no era el problema.
B = 'sku\tnombre\tuds\nA1\tFunko POP 10" Deluxe\t5\nA2\tOtro\t7\n'
eq('(B) 🔒 comilla en medio: los dos leen 3 filas', [len(hoy(B)), len(list(leer_tsv(B)))], [3, 3])
eq('(B) 🔒 … y exactamente lo mismo', hoy(B), list(leer_tsv(B)))

# ── C) 🔴 EL QUE DEJÓ AL LEDGER FUERA ─────────────────────────────────────
#
# 🔑 Un campo ENTERO entre comillas da el MISMO número de filas por los dos caminos, y un
#    valor distinto: hoy `Funko`, con QUOTE_NONE `"Funko"`. Contando filas se leería como
#    «no cambia nada» — el falso verde exacto que había que evitar.
C = 'sku\tnombre\tuds\nA1\t"Funko"\t5\nA2\tOtro\t7\n'
eq('(C) 🔒 mismas filas por los dos caminos', [len(hoy(C)), len(list(leer_tsv(C)))], [3, 3])
eq('(C) 🔴 pero el valor NO es el mismo', hoy(C)[1] == list(leer_tsv(C))[1], False)
eq('(C) 🔴 hoy quita las comillas', hoy(C)[1], ['A1', 'Funko', '5'])
eq('(C) 🔴 y `leer_tsv` las conserva', list(leer_tsv(C))[1], ['A1', '"Funko"', '5'])

# ── D) 🔒 UN FICHERO LIMPIO NO SE ENTERA ──────────────────────────────────
# Es el 100 % de los ficheros de `all_listings`, `internacional`, `paneu_aptos` y
# `salud_fba` medidos el 21-ago-2026: 44 ficheros, cero diferencias.
D = 'sku\tnombre\tuds\nA1\tFunko\t5\nA2\tOtro\t7\n'
eq('(D) 🔒 sin comillas, los dos parseos son idénticos', hoy(D), list(leer_tsv(D)))

# ── E) 🔴 EL LEDGER NO PASA POR AQUÍ, Y ESTO LO VIGILA ────────────────────
#
# 🔬 Sus 10 ficheros traen CADA campo entrecomillado: la cabecera es `"Date"`, `"FNSKU"`,
#    `"ASIN"`… Con `leer_tsv` las comillas se quedarían dentro del valor en las 24.287
#    filas. Ahí el entrecomillado es de verdad y preserva los ceros a la izquierda de
#    MSKU/ASIN/FNSKU, que es el motivo de descargar el ledger en `.txt` (CLAUDE.md §2).
#
# ⚠️ El assert va sobre el FICHERO del procesador y no sobre una nota, porque una nota que
#    dice «el ledger no entra» no impide que alguien lo meta. Éste sí.
LEDGER = ('"Date"\t"FNSKU"\t"ASIN"\n"2026-08-20"\t"X001ABC"\t"B01MYNI1W6"\n')
eq('(E) 🔴 el ledger viene entrecomillado: hoy lo limpia',
   hoy(LEDGER)[0], ['Date', 'FNSKU', 'ASIN'])
eq('(E) 🔴 … y `leer_tsv` lo ensuciaría',
   list(leer_tsv(LEDGER))[0], ['"Date"', '"FNSKU"', '"ASIN"'])
with io.open('procesador_ledger.py', encoding='utf-8') as fh:
    src_ledger = fh.read()
eq('(E) 🔴 por eso `procesador_ledger.py` NO usa `leer_tsv`',
   'leer_tsv' in src_ledger, False)
eq('(E) 🔒 … y sigue con `csv.reader`, que es lo correcto AHÍ',
   'csv.reader(io.StringIO(texto)' in src_ledger, True)

# ── F) 🔴 Y LOS CUATRO QUE SÍ, TAMBIÉN ANCLADOS ───────────────────────────
# 🔑 Anclado sobre lo que NO debe aparecer: preguntar «¿está `leer_tsv`?» saldría verde con
#    un `csv.reader` puesto al lado. Lo que se mira es que la llamada vieja se haya ido.
for f in ('procesador_all_listings.py', 'procesador_internacional.py',
          'procesador_paneu_aptos.py', 'procesador_salud_fba.py'):
    with io.open(f, encoding='utf-8') as fh:
        src = fh.read()
    # Fuera los comentarios: el de al lado NOMBRA `csv.reader` para explicar por qué no se
    # usa, y un grep sobre el texto crudo lo contaría como código. Es la trampa de siempre.
    codigo = '\n'.join(l for l in src.split('\n') if not l.lstrip().startswith('#'))
    eq(f'(F) 🔴 {f} ya no llama a csv.reader',
       'csv.reader(io.StringIO(texto)' in codigo, False)
    eq(f'(F) 🔒 … y sí a leer_tsv', 'leer_tsv(texto)' in codigo, True)

print()
if fallos:
    print(f'❌ {len(fallos)} FALLOS: ' + ', '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
