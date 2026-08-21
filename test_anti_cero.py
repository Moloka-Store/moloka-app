# -*- coding: utf-8 -*-
"""La pregunta anti-cero, hecha codigo: que corta cuando toca y calla cuando no.

⚠️ Y este fichero es el sitio mas facil del repo para cometer el fallo que persigue: un
   test de `exigir_poblacion` escrito con una poblacion vacia probaria que corta y NADA
   mas. Por eso cada bloque lleva su pareja — la direccion que corta y la que sigue.
"""
import io
import sys

sys.path.insert(0, 'scripts')
from anti_cero import exigir_poblacion, exigir_discriminacion  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK  ' if ok else 'XX  ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def corta(fn):
    """Corre `fn` y dice si corto (SystemExit) y que imprimio."""
    dicho = []
    try:
        fn(dicho.append)
        return False, '\n'.join(dicho)
    except SystemExit:
        return True, '\n'.join(dicho)


print('== la pregunta anti-cero ==')

# -- 1) POBLACION VACIA: corta -----------------------------------------------
for n in (0, [], {}, ''):
    corto, _ = corta(lambda s, n=n: exigir_poblacion('ficheros del buzon', n, salida=s))
    eq('(1) poblacion %r corta' % (n,), corto, True)

# -- 1b) Y CON POBLACION, SIGUE ----------------------------------------------
# La mitad que se olvida. Sin esto, un `sys.exit(1)` incondicional pasaria todo lo de
# arriba y el guarda seria una alarma permanente — la cara B del propio guion.
for n in (1, 54, ['a'], {'k': 1}):
    corto, _ = corta(lambda s, n=n: exigir_poblacion('x', n, salida=s))
    eq('(1b) poblacion %r NO corta' % (n,), corto, False)

# -- 1c) Devuelve el recuento, para poder encadenar --------------------------
eq('(1c) devuelve cuantos habia', exigir_poblacion('x', ['a', 'b', 'c']), 3)
eq('(1c) … y cuenta un int tal cual', exigir_poblacion('x', 54), 54)

# -- 1d) El minimo se respeta ------------------------------------------------
corto, _ = corta(lambda s: exigir_poblacion('x', 2, minimo=5, salida=s))
eq('(1d) por debajo del minimo, corta', corto, True)
corto, _ = corta(lambda s: exigir_poblacion('x', 5, minimo=5, salida=s))
eq('(1d) justo en el minimo, sigue', corto, False)

# -- 2) EL MENSAJE DICE QUE SE IBA A MEDIR ----------------------------------
# 🔑 Es lo unico que separa esto de un `assert n > 0`: quien lo lee tiene que saber que
#    faltaba. Un corte sin nombre manda a leer codigo a las tres de la manana.
_, texto = corta(lambda s: exigir_poblacion('ficheros TSV en el buzon', 0, salida=s))
eq('(2) nombra lo que se iba a medir', 'ficheros TSV en el buzon' in texto, True)
eq('(2) dice que NO es un resultado', 'NO es un resultado' in texto, True)
eq('(2) y lleva la pregunta literal',
   'que entrada concreta pondria este' in texto, True)

# -- 3) DOS LADOS IGUALES POR CONSTRUCCION ----------------------------------
mismo = {'a': 1}
corto, texto = corta(lambda s: exigir_discriminacion('la vista contra si misma', mismo, mismo, salida=s))
eq('(3) comparar algo consigo mismo corta', corto, True)
eq('(3) … y lo dice', 'los dos lados son EL MISMO objeto' in texto, True)
# La pareja: dos objetos distintos siguen adelante AUNQUE sean iguales en valor — esto
# detecta el subcaso mecanico, no el semantico, y el docstring lo dice.
corto, _ = corta(lambda s: exigir_discriminacion('x', {'a': 1}, {'a': 1}, salida=s))
eq('(3) dos objetos distintos NO cortan', corto, False)

# -- 4) LOS SITIOS QUE LO USAN, ANCLADOS ------------------------------------
# 🔑 Anclado sobre lo que NO debe volver: la comprobacion escrita a mano. Preguntar
#    «¿esta exigir_poblacion?» saldria verde con un `if not x: sys.exit(1)` puesto al lado.
for f, marca in (('scripts/comparar_censos.py', 'censo'),
                 ('medir_quote_none.py', 'buzon')):
    with io.open(f, encoding='utf-8') as fh:
        src = fh.read()
    codigo = '\n'.join(l for l in src.split('\n') if not l.lstrip().startswith('#'))
    eq('(4) %s usa exigir_poblacion' % f, 'exigir_poblacion(' in codigo, True)
    eq('(4) … y ya no lo hace a mano', 'vino VACIO' in codigo or 'NI UN FICHERO' in codigo, False)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK')
