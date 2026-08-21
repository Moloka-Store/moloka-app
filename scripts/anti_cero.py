# -*- coding: utf-8 -*-
"""LA PREGUNTA ANTI-CERO, hecha codigo: ¿habia algo que medir?

🔴 LA PREGUNTA, literal, y va antes de creerse cualquier recuento:

      «¿QUE ENTRADA CONCRETA PONDRIA ESTE RECUENTO A DISTINTO DE CERO?»

   Si no hay respuesta —si el resultado sale igual mida lo que mida— la comprobacion no
   comprueba nada, y encima tranquiliza. El guion entero, con los seis casos medidos el
   21-ago-2026, esta en `docs/guion-anti-cero.md`.

🔑 DE TODAS LAS FORMAS QUE TIENE ESE FALLO, UNA ES MECANICA Y SE PUEDE CERRAR AQUI: **el
   resultado calculado sobre una poblacion VACIA**. Un recuento a cero, un fichero vacio,
   una carpeta sin ficheros o una lista sin filas convierten cualquier validacion en un
   tramite que siempre pasa. No hay que pensar para detectarlo: hay que contar la entrada.

🔬 Y ESTA AQUI PORQUE YA SE HABIA ESCRITO A MANO TRES VECES (21-ago-2026):
     · `medir_quote_none.py`      — carpeta del buzon sin ficheros
     · `scripts/comparar_censos.py` — uno de los dos censos vacio
     · y el caso que lo empezo todo: `bash -n` validando un fichero de 0 bytes, que salio
       OK porque el extractor habia petado y no escribio nada.
   La regla de la casa: cuando algo se escribe dos veces se convierte en funcion. La
   tercera no se ve venir.

⚠️ NO ES UN `assert n > 0` CON OTRO NOMBRE. Lo que aporta es el MENSAJE: un
   `AssertionError` dice que algo fallo; esto dice **que lo que parecia un resultado no lo
   era**, que son dos cosas distintas para quien lo lee a las tres de la manana.
"""
import sys

# Salida en ASCII pelado: los emoji revientan en una consola cp1252 y el print muere A
# MEDIAS, dejando fuera justo el detalle que hace util el aviso. En los comentarios se
# quedan, que esos no se imprimen.


def exigir_poblacion(que_se_iba_a_medir, n, minimo=1, salida=None):
    """Corta si no habia nada que medir. Devuelve `n` si lo habia.

    · `que_se_iba_a_medir`: en cristiano y en plural — «ficheros en el buzon de paneu»,
      «objetos en el censo de produccion». Sale en el mensaje.
    · `n`: cuantos habia. Puede ser un int o cualquier cosa con `len()`.
    · `minimo`: por debajo de esto no se considera una medicion. Casi siempre 1.

    🔒 NO devuelve un booleano ni imprime un aviso: **corta**. Un aviso dentro de una
       salida que sigue adelante se lee como una nota al pie, y el recuento de cero se
       queda ahi abajo pareciendo un resultado.
    """
    escribir = salida if salida is not None else print
    cuantos = n if isinstance(n, int) else len(n)
    if cuantos >= minimo:
        return cuantos
    escribir('')
    escribir('  ==================================================================')
    escribir('  NO SE HA MEDIDO NADA. Esto NO es un resultado.')
    escribir('  ==================================================================')
    escribir('    se iba a medir : %s' % que_se_iba_a_medir)
    escribir('    y habia        : %d  (hacian falta al menos %d)' % (cuantos, minimo))
    escribir('')
    escribir('  Un recuento sobre una poblacion vacia sale «bien» siempre, mida lo que')
    escribir('  mida. Antes de creerte cualquier verde de aqui abajo, mira por que no')
    escribir('  habia entrada: un fichero que no se descargo, una carpeta vacia, una')
    escribir('  consulta que fallo antes de escribir su salida.')
    escribir('')
    escribir('  La pregunta que esto contesta: ¿que entrada concreta pondria este')
    escribir('  recuento a distinto de cero? Si no la hay, no habia nada que comprobar.')
    escribir('')
    sys.exit(1)


def exigir_discriminacion(que_se_comparaba, a, b, salida=None):
    """Corta si los dos lados de una comparacion son iguales POR CONSTRUCCION.

    🔴 La otra mitad del mismo fallo, y la mas dificil de ver: no que falte entrada, sino
       que los dos lados no puedan diferir. 🔬 Tres casos medidos en dos dias:
         · el pin del `search_path` comparado en las dos ramas de la MISMA transaccion
           (`set_config(..., true)` es de transaccion: fijado en la primera, la segunda ya
           lo tiene). Salia 379 y 379 siempre.
         · el testigo de entorno `current_database()` entre staging y produccion, que son
           un clon restaurado la una de la otra: coinciden por construccion.
         · la huella `es_case`, que aparecia en la version vieja Y en la nueva.

    ⚠️ Esto NO detecta el caso general —para eso hay que pensar, y para eso esta el
       guion—: detecta el subcaso mecanico de comparar una cosa consigo misma.
    """
    escribir = salida if salida is not None else print
    if a is not b:
        return True
    escribir('')
    escribir('  ==================================================================')
    escribir('  LA COMPARACION NO PUEDE FALLAR: los dos lados son EL MISMO objeto.')
    escribir('  ==================================================================')
    escribir('    se comparaba : %s' % que_se_comparaba)
    escribir('')
    escribir('  Comparar algo consigo mismo sale igual siempre. La pregunta: ¿que')
    escribir('  entrada concreta haria que estos dos lados difirieran?')
    escribir('')
    sys.exit(1)
