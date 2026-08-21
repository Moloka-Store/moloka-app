# -*- coding: utf-8 -*-
"""Cómo se lee un TSV de Amazon en esta casa. UNA sola implementación.

🔴 EL PROBLEMA. El módulo `csv` de Python trata la comilla doble como CARÁCTER DE
   ENTRECOMILLADO. Los informes TSV de Amazon la traen como texto normal — un título con
   pulgadas, `Funko POP! 10" Deluxe`. Cuando una comilla ABRE un campo y no cierra, el
   lector se come los tabuladores y los saltos de línea que vengan detrás hasta encontrar
   otra: **fusiona filas**. Y lo hace en silencio: no da error, da menos filas.

🔬 MEDIDO EL 21-ago-2026 sobre los 54 ficheros del buzón (`medir_quote_none.py`), y el dato
   es lo que decide la forma de esto:

     carpeta          ficheros   filas fusionadas hoy   con QUOTE_NONE
     all_listings           11            0              idéntico
     internacional          10            0              idéntico
     paneu_aptos            11            0              idéntico
     salud_fba              12            0              idéntico
     ledger                 10            0              🔴 CAMBIA TODAS LAS CELDAS

   Dos conclusiones, y las dos importan:

   1. **La fusión NO está pasando hoy.** En los 54 ficheros, las líneas físicas y las filas
      parseadas coinciden. Esto no arregla un fallo en curso: pone una red antes de que lo
      haya. Y por eso mismo es el mejor momento para meterla — es INERTE sobre el dato de
      hoy en los cuatro, medido fichero a fichero y celda a celda.

   2. 🔴 **EL LEDGER NO ENTRA, Y NO ES UN OLVIDO.** Sus ficheros traen **cada campo entre
      comillas**: la cabecera es `"Date"`, `"FNSKU"`, `"ASIN"`… Hoy el lector las quita —
      que es lo correcto— y con `QUOTE_NONE` se quedarían DENTRO del valor, en las 24.287
      filas. Ahí el entrecomillado es de verdad y está haciendo su trabajo: es lo que
      preserva los ceros a la izquierda de MSKU/ASIN/FNSKU por los que el ledger se descarga
      en `.txt` (CLAUDE.md §2). Quitarlo sería justo lo contrario de lo que esa regla busca.
      Tampoco entran `keepa_escaparate` ni `transacciones`, que son CSV con campos
      entrecomillados a propósito.

⚠️ Y EL CAMBIO DE COMPORTAMIENTO QUE ESTO INTRODUCE, dicho en alto: si algún día uno de los
   cuatro llegara entrecomillado como el ledger, con `QUOTE_NONE` las comillas se quedarían
   en los valores y **la comprobación de cabeceras del procesador fallaría** (`"ASIN"` no es
   `ASIN`) → ABORTA. Es peor de leer y mejor de comportamiento: hoy ese mismo fichero se
   cargaría en silencio con las filas fusionadas. Se cambia un fallo mudo por uno que grita,
   que es la regla de la casa.

🔒 VIVE AQUÍ Y NO COPIADO EN CUATRO SITIOS. La regla se escribió una vez, se midió una vez y
   se aplica desde un sitio: el día que haya que tocarla, se toca donde está.
"""
import csv
import io


def leer_tsv(texto):
    """Las filas de un TSV de Amazon, sin tratar la comilla como entrecomillado.

    Devuelve una lista de listas, igual que `csv.reader`. Ver el porqué arriba.
    """
    # `quoting=QUOTE_NONE` sin `escapechar`: ni la comilla ni la barra son especiales.
    return csv.reader(io.StringIO(texto), delimiter='\t', quoting=csv.QUOTE_NONE)
