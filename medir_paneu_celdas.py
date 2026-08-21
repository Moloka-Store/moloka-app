# -*- coding: utf-8 -*-
"""MEDIDOR (solo lectura) — ¿cuántas veces trae PanEU una celda ilegible, y en qué países?

🔴 POR QUÉ ESTO NO SE PUEDE MEDIR CONTRA LA BASE, que es lo que obliga a bajar los
   ficheros. `paneu_aptos` es una FOTO: solo guarda el último informe. Y **todo lo que está
   dentro pasó la Guarda 5 por construcción**, así que preguntarle a la base «¿cuántas
   celdas ilegibles ha habido?» devuelve CERO SIEMPRE — no porque no las haya habido, sino
   porque las que las traían nunca entraron. Es la comprobación que no puede fallar, otra
   vez: el resultado no depende del estado que se quiere medir.
   La historia está en los ficheros del buzón, y ahí es donde hay que ir a buscarla.

🔒 NO ESCRIBE NADA. Lista el buzón, baja cada fichero y cuenta. Ni un INSERT, ni un DELETE.

🔒 Y CLASIFICA CON EL CLASIFICADOR DE VERDAD (`clasificar_oferta` del procesador), no con
   una copia del criterio. Si mañana alguien cambia qué cuenta como legible, este medidor
   cambia con él. Dos parseos que miden lo mismo son dos verdades esperando a discrepar.

LA PREGUNTA, que la puso Fernando: cuántas veces ha habido celdas vacías o ilegibles en los
SEIS países que la app no usa (UK, IE, PL, SE, BE, NL) y en cuántos ficheros distintos —
para decidir si una celda que no entendemos en un país que no miramos debe tumbar la carga
de los cuatro que sí.
"""
import io, os, sys, csv
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procesador_paneu_aptos as P
from foto_comun import listar_buzon, descargar_buzon
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# Los cuatro que la app mira, y los seis que no. La lista sale del procesador, no de aquí.
USADOS = ('ES', 'IT', 'FR', 'DE')
NO_USADOS = tuple(p for p in P.MAPA_PAIS if p not in USADOS)


def main():
    if not SUPABASE_KEY:
        sys.exit('Falta SUPABASE_KEY. Este medidor solo LEE el buzón.')
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    objs = listar_buzon(sb, P.BUCKET, P.CARPETA)
    ficheros = sorted(o['name'] for o in objs
                      if o['name'].lower().endswith(('.txt', '.tsv')))
    print(f'=== MEDIDOR PanEU · celdas ilegibles por país ===')
    print(f'Ficheros en {P.BUCKET}/{P.CARPETA}/: {len(ficheros)}\n')
    print(f'Países que la app USA:    {", ".join(USADOS)}')
    print(f'Países que NO usa:        {", ".join(NO_USADOS)}\n')

    tot_pais = Counter()          # celdas ilegibles por país, en todos los ficheros
    ficheros_con = Counter()      # en cuántos FICHEROS distintos aparece cada país
    resumen = []

    for nombre in ficheros:
        try:
            crudo = descargar_buzon(sb, P.BUCKET, f'{P.CARPETA}/{nombre}')
            try:
                texto = crudo.decode('utf-8-sig')
            except UnicodeDecodeError:
                texto = crudo.decode('cp1252', errors='replace')

            lector = csv.reader(io.StringIO(texto), delimiter='\t')
            filas = [f for f in lector if any((c or '').strip() for c in f)]
            if len(filas) < 2:
                resumen.append((nombre, 0, {}, 'fichero vacío o no es TSV'))
                continue

            cab = [P._clean(c) for c in filas[0]]
            idx = {c: i for i, c in enumerate(cab)}

            malas = Counter()
            # 🔴 EL DETALLE DE LA FILA, que es lo que decide la FORMA del arreglo: no es lo
            #    mismo «una celda suelta de un país» que «una fila entera sin ningún estado».
            #    Lo primero se arregla por país; lo segundo, por fila. Sin este dato se
            #    elegiría el arreglo por intuición.
            detalle = []
            for num, fila in enumerate(filas[1:], start=2):
                sueltas = []
                for pais, (col_estado, _) in P.MAPA_PAIS.items():
                    i = idx.get(col_estado)
                    if i is None:
                        # La columna de ese país NO viene en el fichero. No es una celda
                        # ilegible: es un país que el informe no trae. Se cuenta aparte.
                        malas[f'{pais}·SIN COLUMNA'] += 0
                        continue
                    cell = fila[i] if i < len(fila) else ''
                    of = P.clasificar_oferta(cell)
                    # La Guarda 5: los cuatro estados tienen que sumar exactamente 1.
                    suma = (int(of['tiene_oferta']) + int(of['sin_listing'])
                            + int(of['no_requiere_oferta']) + int(of['motivo_bloqueo'] is not None))
                    if suma != 1:
                        malas[pais] += 1
                        sueltas.append((pais, cell))
                if sueltas:
                    # Cuántas celdas de la fila ENTERA vienen con algo: distingue una fila
                    # huérfana (SKU recién creado, sin evaluar) de un fichero corrupto.
                    con_algo = sum(1 for c in fila if (c or '').strip())
                    detalle.append((num, fila[0] if fila else '?', len(sueltas),
                                    con_algo, len(fila)))

            for num, sku, n_paises, con_algo, ancho in detalle[:6]:
                print(f'   🔴 fila {num} · sku {sku!r}: {n_paises}/10 países ilegibles · '
                      f'{con_algo} de {ancho} celdas de la fila traen algo', flush=True)

            for p, n in malas.items():
                if n:
                    tot_pais[p] += n
                    ficheros_con[p] += 1
            faltan = [p for p, (c, _) in P.MAPA_PAIS.items() if c not in idx]
            resumen.append((nombre, len(filas) - 1, dict(malas),
                            ('sin columna: ' + ','.join(faltan)) if faltan else ''))
        except Exception as e:                                    # noqa: BLE001
            resumen.append((nombre, 0, {}, f'ERROR: {e}'))

    print('--- Por fichero ---')
    for nombre, nfilas, malas, nota in resumen:
        ilegibles = {k: v for k, v in malas.items() if v}
        marca = '🔴' if ilegibles else '  '
        print(f'{marca} {nombre:<28} {nfilas:>4} filas   '
              f'{("ilegibles: " + str(ilegibles)) if ilegibles else "todas legibles"}'
              f'{("   [" + nota + "]") if nota else ""}')

    print('\n--- Total por país ---')
    if not tot_pais:
        print('   Ninguna celda ilegible en ningún fichero.')
    for p, n in sorted(tot_pais.items(), key=lambda kv: -kv[1]):
        uso = 'USADO' if p in USADOS else 'no usado'
        print(f'   {p:<4} {uso:<9} {n:>5} celdas   en {ficheros_con[p]} de {len(ficheros)} ficheros')

    en_usados = sum(n for p, n in tot_pais.items() if p in USADOS)
    en_no_usados = sum(n for p, n in tot_pais.items() if p in NO_USADOS)
    print(f'\n   en países USADOS:     {en_usados}')
    print(f'   en países NO usados:  {en_no_usados}')
    print('\n🔑 Si todo lo ilegible cae en los NO usados, una celda que no entendemos en un')
    print('   país que no miramos está tumbando la carga de los cuatro que sí. Ése es el')
    print('   dato con el que se decide — no la impresión de que «pasa poco».')


if __name__ == '__main__':
    main()
