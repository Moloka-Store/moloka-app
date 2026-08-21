# -*- coding: utf-8 -*-
"""MEDIDOR (solo lectura) — ¿cambia algo parsear los TSV de Amazon con QUOTE_NONE?

🔴 LA PREGUNTA, y por qué no vale razonarla. El módulo `csv` de Python, por defecto, trata
   la comilla doble como CARÁCTER DE ENTRECOMILLADO. Los informes de Amazon son TSV: los
   campos van separados por tabuladores y las comillas que aparecen dentro son texto
   normal — parte de un título de producto («Funko POP! 10" Deluxe»). Cuando una comilla
   abre al PRINCIPIO de un campo y no cierra, el lector se come los tabuladores y los
   saltos de línea que vengan detrás hasta encontrar otra comilla: **fusiona filas**.

   Con `QUOTE_NONE` la comilla deja de ser especial y el fichero se lee como lo que es:
   texto partido por tabuladores.

⚠️ PERO ESO ES EL RAZONAMIENTO, NO LA MEDIDA. Fernando: *«no lo apoyes solo en el
   razonamiento — parsea el mismo fichero por los dos caminos y compara fila a fila»*. Eso
   es lo que hace este script, sobre los ficheros REALES del buzón, y por eso puede
   contestar tres cosas que el razonamiento no contesta:
     · ¿pasa hoy, o es un riesgo teórico?  → cuántas filas se fusionan, en qué fichero
     · ¿en cuáles de los cinco informes?    → los cinco se miden por separado
     · ¿el cambio ROMPE algo que hoy va bien? → si algún parseo difiere a peor, se ve aquí

🔒 NO ESCRIBE NADA. Lista el buzón, baja cada fichero y compara dos lecturas en memoria.

🔑 Y COMPARA CELDA A CELDA, no solo el recuento de filas. Dos parseos pueden dar el MISMO
   número de filas y repartir el contenido distinto — y un recuento igual se leería como
   «no cambia nada». Es el mismo error que contar filas para dar por buena una carga.
"""
import io, os, sys, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import listar_buzon, descargar_buzon
from scripts.anti_cero import exigir_poblacion
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

BUCKET = 'informes'

# 🔴 LOS CINCO INFORMES TSV, con su carpeta. No entran `keepa_escaparate` ni
#    `transacciones`: ésos son CSV de verdad, con campos entrecomillados a propósito
#    (títulos con comas dentro), y ahí la comilla SÍ es un carácter de entrecomillado.
#    Aplicarles QUOTE_NONE los rompería — es el caso contrario exacto.
CARPETAS = ['all_listings', 'internacional', 'ledger', 'paneu_aptos', 'salud_fba']


def decodificar(crudo):
    """El mismo par de intentos que hacen los procesadores: BOM primero, cp1252 de reserva."""
    try:
        return crudo.decode('utf-8-sig')
    except UnicodeDecodeError:
        return crudo.decode('cp1252', errors='replace')


def parsear(texto, quote_none):
    """Las DOS lecturas, con la única diferencia que se está midiendo."""
    if quote_none:
        # `quoting=QUOTE_NONE` sin `escapechar`: ninguna comilla ni barra es especial.
        return list(csv.reader(io.StringIO(texto), delimiter='\t',
                               quoting=csv.QUOTE_NONE))
    return list(csv.reader(io.StringIO(texto), delimiter='\t'))


def comparar(viejo, nuevo):
    """Qué se movió. Devuelve (n_filas_viejo, n_filas_nuevo, diferencias, primera).

    🔒 Se comparan las filas EN ORDEN y celda a celda. Si el número de filas difiere, ya
       hay fusión; si coincide pero alguna celda no, el contenido se repartió distinto y
       eso también hay que verlo.
    """
    difs = 0
    primera = None
    for i in range(min(len(viejo), len(nuevo))):
        if viejo[i] != nuevo[i]:
            difs += 1
            if primera is None:
                primera = (i + 1, viejo[i], nuevo[i])
    return len(viejo), len(nuevo), difs, primera


def main():
    if not SUPABASE_KEY:
        sys.exit('Falta SUPABASE_KEY. Este medidor solo LEE el buzón.')
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print('=== MEDIDOR · QUOTE_NONE sobre los cinco informes TSV ===')
    print('Compara DOS parseos del MISMO fichero, fila a fila y celda a celda.')
    print('Solo lectura: no escribe nada.\n')

    tot_ficheros = 0
    tot_con_cambio = 0
    # 🔴 EL CONTRAEJEMPLO QUE HAY QUE BUSCAR: un fichero donde QUOTE_NONE dé MENOS filas
    #    que el parseo de hoy. Eso significaría que el entrecomillado estaba haciendo algo
    #    útil y que el cambio rompe. Si sale cero, es un dato; si sale >0, es un freno.
    tot_pierde = 0
    # 🔴 Y EL OTRO FRENO, que es el que NO se ve contando filas y por poco se me escapa.
    #    🔬 Medido en banco antes de escribir esto, con cuatro casos sintéticos:
    #      A · comilla que ABRE un campo y no cierra → hoy 2 filas, QUOTE_NONE 3. Es la
    #          fusión temida, y el cambio la arregla.
    #      B · comilla EN MEDIO de un campo (`10" Deluxe`) → los dos igual. Inofensiva.
    #      C · campo ENTERO entre comillas (`"Funko"`) → mismas filas, **distinto valor**:
    #          hoy sale `Funko` y con QUOTE_NONE sale `"Funko"`. Eso no es un arreglo: es
    #          un cambio de dato, y metido a ciegas ensuciaría SKU, ASIN y títulos.
    #      D · fichero limpio → los dos igual.
    #    Por eso el medidor compara CELDA A CELDA y no solo el recuento: el caso C da el
    #    mismo número de filas, y contando filas se leería como «no cambia nada».
    tot_mismas_filas_otro_valor = 0

    for carpeta in CARPETAS:
        try:
            objs = listar_buzon(sb, BUCKET, carpeta)
        except Exception as e:
            print(f'── {carpeta}: no se pudo listar ({e})\n')
            continue
        ficheros = sorted(o['name'] for o in objs
                          if o['name'].lower().endswith(('.txt', '.tsv', '.csv')))
        print(f'── {carpeta}/  ({len(ficheros)} ficheros)')
        if not ficheros:
            # ⚠️ Una carpeta vacía NO es «todo en orden»: es que no había nada que medir.
            #    Sin decirlo, el verde de abajo se leería como una comprobación hecha.
            print('   ⚠️ VACÍA — aquí no se ha medido nada, que no es lo mismo que «no cambia».\n')
            continue

        for nombre in ficheros:
            tot_ficheros += 1
            try:
                texto = decodificar(descargar_buzon(sb, BUCKET, f'{carpeta}/{nombre}'))
            except Exception as e:
                print(f'   {nombre[:44]:<44} ERROR al bajar: {e}')
                continue

            # 🔑 LAS LÍNEAS FÍSICAS del fichero: es el número contra el que se contrasta.
            #    Un TSV bien leído tiene una fila por línea; si el parseo de hoy da MENOS,
            #    la diferencia son exactamente las filas fusionadas.
            fisicas = sum(1 for _ in io.StringIO(texto))

            viejo = parsear(texto, quote_none=False)
            nuevo = parsear(texto, quote_none=True)
            nv, nn, difs, primera = comparar(viejo, nuevo)

            marca = '  '
            if nn > nv:
                marca = '🔴'
                tot_con_cambio += 1
            elif nn < nv:
                marca = '⛔'
                tot_pierde += 1
                tot_con_cambio += 1
            elif difs:
                marca = '🟠'
                tot_con_cambio += 1
                tot_mismas_filas_otro_valor += 1

            print(f'   {marca} {nombre[:40]:<40} lineas={fisicas:>6}  '
                  f'hoy={nv:>6}  QUOTE_NONE={nn:>6}  celdas dist={difs}')
            if primera is not None:
                fila, v, n = primera
                print(f'        primera diferencia en la fila {fila}:')
                print(f'          hoy        → {len(v)} campos · {str(v)[:120]}')
                print(f'          QUOTE_NONE → {len(n)} campos · {str(n)[:120]}')
        print('')

    print('=== RESUMEN ===')
    print(f'  ficheros medidos                 {tot_ficheros}')
    print(f'  con alguna diferencia            {tot_con_cambio}')
    print(f'  🔴 QUOTE_NONE da MENOS filas     {tot_pierde}   <- si esto no es 0, NO se cambia')
    print(f'  🔴 mismas filas, OTRO valor       {tot_mismas_filas_otro_valor}   <- ni esto (caso C: comillas que hoy se quitan)')
    # 🔒 Por `exigir_poblacion`, no a mano. Ver `docs/guion-anti-cero.md`.
    exigir_poblacion('ficheros TSV en el buzon', tot_ficheros)
    if tot_pierde or tot_mismas_filas_otro_valor:
        print('')
        print('  ⛔ HAY UN FRENO. El cambio no es inerte sobre el dato de hoy: o pierde filas')
        print('     o cambia el valor de alguna celda. Mira la primera diferencia de arriba')
        print('     ANTES de tocar ningún procesador.')
        sys.exit(1)
    if tot_con_cambio == 0:
        print('\n  Los dos parseos dan EXACTAMENTE lo mismo en todos los ficheros de hoy.')
        print('  ⚠️ Eso NO significa que el cambio sobre. Significa que hoy no hay ninguna')
        print('     comilla en posición de romper — y que el cambio es INERTE sobre el dato')
        print('     actual, que es la mejor situación para meterlo: cierra el riesgo sin')
        print('     mover ni una fila.')


if __name__ == '__main__':
    main()
