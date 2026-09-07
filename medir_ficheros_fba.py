# -*- coding: utf-8 -*-
"""MEDIDOR (solo lectura) — qué hay en el buzón de `inventario_fba`, fichero a fichero.

🔴 POR QUÉ EXISTE, con la fecha y el caso. El 7-sep-2026 la carga del inventario llevaba
   parada desde por la mañana (Amazon sirvió 24 columnas y la Guarda 1 abortó), y al ir a
   rescatar el fichero de ese día resultó que en el buzón había **CUATRO** `.txt` subidos
   el 7, no uno. Los cuatro llevarían la misma `fecha_foto` —la fecha de este informe es
   la de SUBIDA, porque el .txt no la trae ni dentro ni en el nombre—, así que cargar
   «el más reciente» habría sido una lotería, y cargar el equivocado habría dejado la
   foto del día siendo una exportación que nadie eligió.
   Fernando: *«no se carga ninguno hasta decidir cuál es la foto del día»*. Para decidir
   hace falta VERLOS, y para verlos hace falta bajarlos: el buzón es privado y la base no
   guarda el fichero, sólo el `crudo` de la carga que sí entró.

🔒 NO ESCRIBE NADA, ni en la base ni en el Storage. Ni siquiera se conecta a la base: no
   necesita `DB_URL`. Lista el buzón, baja cada `.txt` y cuenta en memoria.

🔑 QUÉ CONTESTA de cada fichero, que es exactamente lo que hace falta para elegir:
     · cuándo se subió (y por tanto qué `fecha_foto` tendría) y cuánto pesa
     · cuántos encabezados trae, cuáles, y si son uno de los dos MODELOS CONOCIDOS
     · cuántas filas de datos, y si alguna viene dentada
     · las tres cifras que permiten compararlos entre sí: vendible, tránsito y unidades
       totales. Dos exportaciones del mismo día pueden pesar casi igual y contar cosas
       distintas, y el peso no lo dice.

⚠️ SE LEE CON `leer_tsv` Y CON `analizar()`, las piezas de verdad del procesador, no con
   un parseo escrito aquí. Un medidor que parsea a su manera mide su parseo, no el de la
   carga. Por eso también aparecen aquí los abortos de las guardas: si un fichero no
   entraría, esto lo dice antes de que nadie lo intente.

Se lanza por `.github/workflows/medir-ficheros-fba.yml`. Solo lectura, sin secretos de
base de datos.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import Aborta, listar_buzon, descargar_buzon, fecha_del_dato_por_subida
from procesador_inventario_fba import (analizar, cabecera_de, modelo_del_disponible,
                                       NOMBRE_MODELO, MODELO_26, MODELO_24)
from scripts.anti_cero import exigir_poblacion
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

BUCKET, CARPETA = 'informes', 'inventario_fba'
# Vacío = todos los del buzón. Con valor, sólo los .txt cuya fecha de subida sea ésa.
SOLO_DIA = os.environ.get('SOLO_DIA', '').strip()


def decodificar(crudo):
    """El mismo par de intentos que hace el procesador: BOM primero, cp1252 de reserva."""
    try:
        return crudo.decode('utf-8-sig')
    except UnicodeDecodeError:
        return crudo.decode('cp1252', errors='replace')


def main():
    print("=== MEDIDOR (SOLO LECTURA) · buzon %s/%s ===" % (BUCKET, CARPETA), flush=True)
    if not SUPABASE_KEY:
        sys.exit("Falta SUPABASE_KEY. Revisa los secrets del workflow.")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    # 🔒 La pregunta anti-cero, hecha código: sin ficheros, todo lo de abajo saldría
    #    «bien» sin haber medido nada.
    exigir_poblacion("ficheros .txt en el buzon %s/%s" % (BUCKET, CARPETA), txts)

    # Del más reciente al más antiguo, que es el orden en que se mira un buzón.
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''),
              reverse=True)

    print("Hay %d .txt en el buzon.%s\n"
          % (len(txts), ("  Filtro SOLO_DIA=%s" % SOLO_DIA) if SOLO_DIA else ""),
          flush=True)

    mirados = 0
    for o in txts:
        nombre = o.get('name')
        try:
            fecha = fecha_del_dato_por_subida(o, 'inventario_fba').date()
        except Aborta as e:
            print("· %s\n    sin sello de subida legible: %s\n" % (nombre, e), flush=True)
            continue
        if SOLO_DIA and str(fecha) != SOLO_DIA:
            continue
        mirados += 1

        crudo = descargar_buzon(sb, BUCKET, "%s/%s" % (CARPETA, nombre))
        texto = decodificar(crudo)
        cab = cabecera_de(texto)
        modelo = modelo_del_disponible(cab)

        print("· %s" % nombre, flush=True)
        print("    subido            : %s  ->  fecha_foto seria %s"
              % (o.get('updated_at') or o.get('created_at'), fecha))
        print("    tamano            : %d bytes" % len(crudo))
        print("    encabezados       : %d" % len(cab))
        if modelo is not None:
            print("    modelo            : %s  (%s)" % (modelo, NOMBRE_MODELO[tuple(cab)]))
        else:
            faltan26 = [h for h in MODELO_26 if h not in cab]
            faltan24 = [h for h in MODELO_24 if h not in cab]
            sobran = [h for h in cab if h not in MODELO_26]
            print("    modelo            : NO CATALOGADO")
            print("      · contra el de 26: le faltan %d %s" % (len(faltan26), faltan26))
            print("      · contra el de 24: le faltan %d %s" % (len(faltan24), faltan24))
            print("      · columnas que no estan en ninguno: %s" % (sobran or 'ninguna'))
        print("    columnas          : %s" % ", ".join(cab))

        # 🔑 Las guardas de verdad, las del procesador. Si un fichero no entraria, aqui
        #    se ve — y se ve ANTES de que nadie lo intente contra una base.
        try:
            info = analizar(texto, nombre, fecha)
        except Aborta as e:
            print("    filas             : NO SE HA PODIDO CONTAR")
            print("    la carga ABORTARIA: %s" % str(e).split('\n')[0])
            print("", flush=True)
            continue

        filas = info['filas']
        con_fc = [f for f in filas if f['registro'].get('fc_transfer') is not None]
        print("    filas de datos    : %d" % len(filas))
        print("    ASIN distintos    : %d"
              % len({f['registro']['asin'] for f in filas if f['registro']['asin']}))
        print("    vendible          : %d uds" % info['vendible_total'])
        if con_fc:
            print("    transito          : %d uds (leido en %d de %d fichas)"
                  % (sum(f['registro']['fc_transfer'] for f in con_fc),
                     len(con_fc), len(filas)))
        else:
            print("    transito          : NO VIENE en este informe (quedaria a NULO)")
        print("    en camino         : %d uds (inbound_shipped, %d ASIN)"
              % (info['total_inbound'], info['asin_con_inbound']))
        print("    unidades totales  : %d" % info['total_unidades'])
        print("    almacen           : %d uds" % info['almacen_total'])
        print("", flush=True)

    if SOLO_DIA and mirados == 0:
        sys.exit("Ningun .txt del buzon se subio el %s. Revisa la fecha." % SOLO_DIA)
    print("=== FIN · %d fichero(s) mirados · NO se ha escrito nada ===" % mirados,
          flush=True)


if __name__ == '__main__':
    main()
