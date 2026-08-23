# -*- coding: utf-8 -*-
"""Las guardas del buzon de inventario_fba, vistas ROJAS y vistas CALLADAS.

🔴 LAS DOS DIRECCIONES, Y LA SEGUNDA ES LA QUE SE OLVIDA (§3 de CLAUDE.md):
     1) que se ponga ROJA cuando toca  → se rompe el fichero a mano y tiene que saltar
     2) que este CALLADA cuando no toca → se corre con todo en orden y no debe decir nada
   Cada bloque de aqui abajo lleva su pareja. Un `raise Aborta` incondicional pasaria
   todos los tests de la direccion 1 y ninguno de la 2; un `pass` los pasaria al reves.
   Hacen falta las dos para saber si la guarda mide algo o solo hace ruido en una
   direccion fija.

🔒 AQUI NO HAY NI UNA FILA DEL FICHERO REAL, Y ES A PROPOSITO: **este repo es PUBLICO**
   (§5 de CLAUDE.md). El informe trae SKU, FNSKU, titulos, precios y el stock real de
   Moloka. Lo que se copia del fichero real es LA FORMA —los 26 encabezados literales,
   que no son un dato de negocio— y las filas se fabrican aqui. Para una guarda eso es
   exactamente lo que hace falta: lo que se prueba es el criterio, no el inventario.
   La medicion contra el fichero real se hace al cargarlo (ensayo del workflow), y sus
   numeros del 23-ago-2026 estan anclados abajo, en el bloque (0).

⚠️ Y el vicio que este fichero tiene mas cerca: comprobar que algo esta ESCRITO en vez de
   que se EJECUTA. Por eso las guardas se prueban LLAMANDO a `analizar()`, nunca con un
   grep sobre el .py — un regex casa igual dentro de un comentario.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from procesador_inventario_fba import (analizar, avisar_inbound, Aborta,  # noqa: E402
                                       UMBRAL_FILAS, N_COLUMNAS, TIPADAS, NUMERICAS,
                                       CABECERA_ESPERADA)

fallos = []
HOY = datetime.date(2026, 8, 23)


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK  ' if ok else 'XX  ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def corta(texto, **kw):
    """Corre `analizar` sobre `texto`. Devuelve (aborto?, mensaje)."""
    try:
        analizar(texto, 'prueba.txt', HOY, **kw)
        return False, ''
    except Aborta as e:
        return True, str(e)


# ---------------------------------------------------------------------------
# EL FICHERO DE MENTIRA: los 26 encabezados REALES, filas fabricadas aqui.
# ---------------------------------------------------------------------------
CABECERA = [
    'sku', 'fnsku', 'asin', 'product-name', 'condition', 'your-price',
    'mfn-listing-exists', 'mfn-fulfillable-quantity', 'afn-listing-exists',
    'afn-warehouse-quantity', 'afn-fulfillable-quantity', 'afn-unsellable-quantity',
    'afn-reserved-quantity', 'afn-total-quantity', 'per-unit-volume',
    'afn-inbound-working-quantity', 'afn-inbound-shipped-quantity',
    'afn-inbound-receiving-quantity', 'afn-researching-quantity',
    'afn-reserved-future-supply', 'afn-future-supply-buyable',
    'afn-fulfillable-quantity-local', 'afn-fulfillable-quantity-remote',
    'afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity', 'store',
]
POR = {h: i for i, h in enumerate(CABECERA)}


def fila(n, inbound=0, **cambios):
    """Una fila sana. `n` la hace unica; `cambios` la rompe por un sitio concreto."""
    f = [''] * len(CABECERA)
    f[POR['sku']] = 'SKU-%05d' % n
    f[POR['fnsku']] = 'X00%08d' % n
    f[POR['asin']] = 'B0%08d' % n
    # 🔬 El titulo lleva comilla y coma A PROPOSITO: es la trampa de `tsv_comun`
    #    (`Funko POP! 10" Deluxe`). Con el lector ingenuo esto fusionaria filas.
    f[POR['product-name']] = 'Figura 10" Deluxe, edicion %d' % n
    f[POR['condition']] = 'New'
    f[POR['your-price']] = '19.99'
    f[POR['mfn-listing-exists']] = 'No'
    f[POR['afn-listing-exists']] = 'Yes'
    for h in ('afn-warehouse-quantity', 'afn-fulfillable-quantity',
              'afn-unsellable-quantity', 'afn-reserved-quantity', 'afn-total-quantity',
              'afn-inbound-working-quantity', 'afn-inbound-shipped-quantity',
              'afn-inbound-receiving-quantity', 'afn-fc-transfer-quantity',
              'afn-reserved-future-supply', 'afn-future-supply-buyable',
              'afn-fulfillable-quantity-local', 'afn-fulfillable-quantity-remote',
              'afn-onhand-buyable-quantity', 'afn-researching-quantity'):
        f[POR[h]] = '0'
    f[POR['afn-warehouse-quantity']] = '5'
    f[POR['afn-fulfillable-quantity']] = '5'
    f[POR['afn-total-quantity']] = str(5 + inbound)
    f[POR['afn-inbound-shipped-quantity']] = str(inbound)
    f[POR['per-unit-volume']] = '1657.06'
    for h, v in cambios.items():
        f[POR[h.replace('_', '-')]] = v
    return f


def fichero(filas, cabecera=None, crlf=True):
    fin = '\r\n' if crlf else '\n'
    cab = cabecera if cabecera is not None else CABECERA
    return fin.join(['\t'.join(cab)] + ['\t'.join(f) for f in filas])


# 🔒 EL SANO: por encima del umbral, con transito en 3 de sus filas. Todo lo demas
#    se mide contra este — si el sano no entrase, cada "rechazado" de abajo saldria
#    verde sin probar nada (la comprobacion que no puede fallar).
SANAS = [fila(n, inbound=(12 if n % 60 == 0 else 0)) for n in range(1, UMBRAL_FILAS + 6)]
SANO = fichero(SANAS)


print('== 0) LO QUE SE MIDIO EN EL FICHERO REAL (anclas, 23-ago-2026) ==')
# Si Amazon cambia la forma del informe, esto salta antes que nada y dice por donde.
eq('(0) el informe declara 26 columnas', N_COLUMNAS, 26)
eq('(0) los 16 encabezados tipados son de la cabecera real',
   [h for h in CABECERA_ESPERADA if h not in CABECERA], [])
eq('(0) la PK es el sku', TIPADAS[0][:2], ('sku', 'sku'))
eq('(0) inbound_shipped viene de afn-inbound-shipped-quantity',
   [c for h, c, _ in TIPADAS if h == 'afn-inbound-shipped-quantity'], ['inbound_shipped'])
eq('(0) el umbral de filas es 150 (356 sanas · 37 el roto de salud_fba)',
   UMBRAL_FILAS, 150)


print('\n== 1) EL FICHERO SANO ENTRA (la mitad callada, y la base de todo lo demas) ==')
sano = analizar(SANO, 'prueba.txt', HOY)
eq('(1) el sano NO aborta', len(sano['filas']), len(SANAS))
eq('(1) … y cuenta el transito', sano['total_inbound'], 12 * sum(1 for n in range(1, UMBRAL_FILAS + 6) if n % 60 == 0))
eq('(1) … sin gritos de condition', dict(sano['condiciones_raras']), {})
eq('(1) … sin gritos de store', dict(sano['stores_con_valor']), {})
eq('(1) … y no grita por falta de transito', avisar_inbound(sano, lambda *a: None), False)
# 🔬 La comilla del titulo NO fusiono filas: es `tsv_comun.leer_tsv` (QUOTE_NONE)
#    haciendo su trabajo. Con `csv.reader` a pelo saldrian menos filas.
eq('(1) la comilla del titulo no fusiona filas', len(sano['filas']), len(SANAS))
eq('(1) … y el titulo llega entero',
   sano['filas'][0]['registro']['product_name'], 'Figura 10" Deluxe, edicion 1')


print('\n== 2) GUARDA 1 · la cabecera EXACTA ==')
# 🔑 SE ROMPE UN ENCABEZADO **DE TEXTO**, Y NO ES UN CAPRICHO. Con uno numerico
#    (afn-inbound-shipped-quantity) este test SALIA VERDE CON LA GUARDA 1 APAGADA:
#    al faltar la columna, la celda llega vacia y aborta la Guarda 6 — con un mensaje
#    que ademas nombra la misma columna, asi que los dos asserts pasaban igual.
#    Medido al romper la guarda a mano el 23-ago-2026. Con `product-name` no hay
#    segunda guarda detras: si la 1 no salta, no salta nada.
sin_titulo = [h if h != 'product-name' else 'product_name' for h in CABECERA]
corto, msg = corta(fichero(SANAS, cabecera=sin_titulo))
eq('(2) si falta un encabezado, ABORTA', corto, True)
eq('(2) … y es la Guarda 1 quien lo para', '[Guarda 1]' in msg, True)
eq('(2) … y dice cual falta', "'product-name'" in msg, True)
# La pareja: la cabecera buena no aborta (ya lo prueba el bloque 1, se re-ancla aqui).
corto, _ = corta(fichero(SANAS, cabecera=CABECERA))
eq('(2) con la cabecera real, NO aborta', corto, False)


print('\n== 3) GUARDA 2 · anti-vacio ==')
corto, msg = corta('\t'.join(CABECERA))
eq('(3) solo cabecera, sin filas: ABORTA', corto, True)
eq('(3) … y lo llama por su nombre', '[Guarda 2]' in msg, True)
corto, _ = corta('')
eq('(3) fichero vacio: ABORTA', corto, True)


print('\n== 4) GUARDA 3 · FILAS DENTADAS = fichero cortado a media linea ==')
# 🔴 Es el detector de truncamiento que a salud_fba le falto. Y no es un numero
#    inventado: es el ancho que declara la cabecera del propio fichero.
cortada = fichero(SANAS) + '\r\nSKU-99999\tX00\tB0'      # ultima fila a medias
corto, msg = corta(cortada)
eq('(4) una fila con menos columnas: ABORTA', corto, True)
eq('(4) … y dice cuantas trae', '3 col.' in msg, True)
eq('(4) … y lo llama truncamiento', 'CORTADO' in msg, True)
# Una fila con columnas DE MAS tambien es otra forma (un tabulador dentro de un campo).
de_mas = fichero(SANAS) + '\r\n' + '\t'.join(fila(99999)) + '\tsobra'
corto, _ = corta(de_mas)
eq('(4) una fila con columnas de mas: ABORTA', corto, True)
# La pareja: 26 columnas exactas en todas y no dice nada.
corto, _ = corta(SANO)
eq('(4) con todas las filas completas, NO aborta', corto, False)


print('\n== 5) GUARDA 4 · el umbral de filas ==')
corto, msg = corta(fichero(SANAS[:37]))
eq('(5) 37 filas (las del salud_fba roto): ABORTA', corto, True)
eq('(5) … y explica que un informe a medias MIENTE', 'FALSA' in msg, True)
eq('(5) … y nombra la valvula', 'PERMITIR_UMBRAL_BAJO' in msg, True)
corto, _ = corta(fichero(SANAS[:UMBRAL_FILAS - 1]))
eq('(5) justo por debajo del umbral: ABORTA', corto, True)
# 🔑 La pareja, y la que fija el borde: JUSTO en el umbral tiene que entrar.
corto, _ = corta(fichero(SANAS[:UMBRAL_FILAS]))
eq('(5) justo EN el umbral: NO aborta', corto, False)
# La valvula abre de verdad (si no, seria una puerta pintada en la pared).
os.environ['PERMITIR_UMBRAL_BAJO'] = '1'
corto, _ = corta(fichero(SANAS[:37]))
eq('(5) con PERMITIR_UMBRAL_BAJO=1, pasa', corto, False)
del os.environ['PERMITIR_UMBRAL_BAJO']
corto, _ = corta(fichero(SANAS[:37]))
eq('(5) … y al quitarla, vuelve a abortar', corto, True)


print('\n== 6) GUARDA 5 · el sku es la PK ==')
sin_sku = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
sin_sku[3][POR['sku']] = ''
corto, msg = corta(fichero(sin_sku))
eq('(6) sku vacio: ABORTA', corto, True)
eq('(6) … y dice que es la PK', 'PK' in msg, True)

dup = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
dup[7][POR['sku']] = dup[2][POR['sku']]
corto, msg = corta(fichero(dup))
eq('(7) sku duplicado: ABORTA', corto, True)
eq('(7) … y NO elige (no deduplica)', 'NO elige' in msg, True)
# 🔴 La pareja que importa aqui: el ASIN repetido NO aborta. En el fichero real
#    B07GRRYFL1 viene dos veces (una etiquetada y otra commingled) y es legitimo —
#    una PK por ASIN reventaria. Si esto se pusiera rojo, la clave estaria mal puesta.
dos_vidas = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
dos_vidas[9][POR['asin']] = dos_vidas[4][POR['asin']]
dos_vidas[9][POR['fnsku']] = dos_vidas[9][POR['asin']]      # FNSKU = ASIN ⇒ commingled
corto, _ = corta(fichero(dos_vidas))
eq('(7) el mismo ASIN con dos SKU (commingled): NO aborta', corto, False)


print('\n== 8) GUARDA 6 · las numericas del inventario ==')
# 🔑 Cada caso se ancla en LA MITAD QUE CAMBIA, no en «aborta». Con el `bruto == ''`
#    apagado, un hueco sigue abortando —por el `int('')` que revienta dos lineas mas
#    abajo— y un assert de «aborta» a secas SEGUIA VERDE (medido al romperlo a mano el
#    23-ago-2026). Lo que distingue las dos ramas es el mensaje: «viene VACIA» dice que
#    el informe dejo de contestar; «no es un numero» dice que trae basura.
for col, valor, que, marca in (
        ('afn-inbound-shipped-quantity', '', 'vacia', 'viene VACÍA'),
        ('your-price', '', 'precio vacio', 'viene VACÍA'),
        ('afn-fulfillable-quantity', 'N/A', 'no numerica', 'no es un número'),
        ('afn-total-quantity', '-3', 'negativa', '(negativo)')):
    rotas = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
    rotas[5][POR[col]] = valor
    corto, msg = corta(fichero(rotas))
    eq('(8) %s %s: ABORTA' % (col, que), corto, True)
    eq('(8) … y por la razon correcta (%s)' % que, marca in msg, True)
# 🔑 «Vacio NO es 0»: la pareja es que un 0 de verdad SI entra. Sin esto, la guarda
#    podria estar rechazando el cero legitimo y nadie se enteraria.
ceros = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
ceros[5][POR['afn-inbound-shipped-quantity']] = '0'
corto, _ = corta(fichero(ceros))
eq('(8) un 0 explicito NO aborta (vacio != cero)', corto, False)
# Y las columnas que el fichero real trae vacias de serie no molestan: no se tipan.
huecos = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
for f in huecos:
    f[POR['mfn-fulfillable-quantity']] = ''
    f[POR['afn-researching-quantity']] = ''
    f[POR['store']] = ''
corto, _ = corta(fichero(huecos))
eq('(8) mfn-fulfillable / researching / store vacias: NO abortan', corto, False)


print('\n== 9) GUARDA 7 · anti-cero ==')
a_cero = [fila(n, inbound=0) for n in range(1, UMBRAL_FILAS + 6)]
for f in a_cero:
    f[POR['afn-warehouse-quantity']] = '0'
    f[POR['afn-fulfillable-quantity']] = '0'
    f[POR['afn-total-quantity']] = '0'
corto, msg = corta(fichero(a_cero))
eq('(9) el fichero entero a 0 unidades: ABORTA', corto, True)
eq('(9) … y dice que es un fichero roto', 'roto' in msg, True)
# La pareja: con una sola unidad en todo el fichero, ya hay algo que medir.
una = [fila(n, inbound=0) for n in range(1, UMBRAL_FILAS + 6)]
for f in una:
    f[POR['afn-warehouse-quantity']] = '0'
    f[POR['afn-fulfillable-quantity']] = '0'
    f[POR['afn-total-quantity']] = '0'
una[0][POR['afn-total-quantity']] = '1'
corto, _ = corta(fichero(una))
eq('(9) con una sola unidad: NO aborta', corto, False)


print('\n== 10) GUARDA 7b · sin transito se GRITA, no se aborta ==')
# 🔴 Aqui esta la unica desviacion consciente del encargo, y esta MEDIDA: el
#    25-jul-2026 salud_fba cargo 218 filas con inbound_shipped=0 en TODAS y ni un
#    nulo — informe sano de un dia sin nada de camino (consulta a salud_fba_hist en
#    produccion, 23-ago-2026). Abortar por eso rechazaria informes buenos.
sin_transito = analizar(fichero([fila(n, inbound=0) for n in range(1, UMBRAL_FILAS + 6)]),
                        'prueba.txt', HOY)
dicho = []
eq('(10) sin transito NO aborta al analizar', sin_transito['total_inbound'], 0)
eq('(10) … pero GRITA', avisar_inbound(sin_transito, dicho.append), True)
texto_grito = '\n'.join(dicho)
eq('(10) … y el grito dice por que no puede distinguir',
   'NO puede distinguir' in texto_grito, True)
eq('(10) … y nombra la puerta al criterio estricto',
   'EXIGIR_INBOUND' in texto_grito, True)
# La pareja 1: con transito, CALLADO. Una alarma que grita siempre no informa.
eq('(10) con transito, NO grita', avisar_inbound(sano, lambda *a: None), False)
# La pareja 2: la puerta abre de verdad.
os.environ['EXIGIR_INBOUND'] = '1'
try:
    avisar_inbound(sin_transito, lambda *a: None)
    eq('(10) con EXIGIR_INBOUND=1, ABORTA', False, True)
except Aborta:
    eq('(10) con EXIGIR_INBOUND=1, ABORTA', True, True)
del os.environ['EXIGIR_INBOUND']
try:
    avisar_inbound(sin_transito, lambda *a: None)
    eq('(10) … y al quitarla, vuelve a solo gritar', True, True)
except Aborta:
    eq('(10) … y al quitarla, vuelve a solo gritar', False, True)


print('\n== 11) GUARDA 9 · lo que GRITA vive EN EL DATO, no solo en el log ==')
raras = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
raras[2][POR['condition']] = 'UsedGood'
raras[3][POR['afn-listing-exists']] = 'No'
raras[4][POR['store']] = 'Amazon.es'
info = analizar(fichero(raras), 'prueba.txt', HOY)
eq('(11) condition rara: NO aborta, cuenta', dict(info['condiciones_raras']), {'UsedGood': 1})
eq('(11) … y queda en la COLUMNA condition',
   info['filas'][2]['registro']['condition'], 'UsedGood')
eq('(11) afn-listing-exists raro: cuenta', dict(info['listing_raro']), {'No': 1})
eq('(11) store con valor: cuenta', dict(info['stores_con_valor']), {'Amazon.es': 1})
eq('(11) … y queda en la COLUMNA store',
   info['filas'][4]['registro']['store'], 'Amazon.es')
# 🔒 La pareja: con el fichero sano, los tres contadores CALLADOS. Ya se comprobo en
#    el bloque 1; se re-ancla aqui porque es el sitio donde se leen.
eq('(11) con el sano, los tres callados',
   (dict(sano['condiciones_raras']), dict(sano['listing_raro']),
    dict(sano['stores_con_valor'])), ({}, {}, {}))


print('\n== 12) EL CRUDO SE GUARDA ENTERO (la despensa comun) ==')
# Las 26 columnas van a `crudo` aunque hoy solo se tipen 16: el sales-rank de keepa
# llevaba semanas sin mirarse y resulto ser el detector de ASIN muertos.
eq('(12) crudo trae las 26 columnas', len(sano['filas'][0]['crudo']), 26)
eq('(12) … incluidas las que hoy no se tipan',
   all(h in sano['filas'][0]['crudo'] for h in
       ('per-unit-volume', 'afn-researching-quantity', 'mfn-fulfillable-quantity')), True)
eq('(12) … y se tipan 16 de las 26', len(TIPADAS), 16)
eq('(12) … de las que 10 son numericas', len(NUMERICAS), 10)


print('\n== 13) EL FICHERO LLEGA EN CRLF (medido) y se lee igual en LF ==')
eq('(13) CRLF y LF dan las mismas filas',
   len(analizar(fichero(SANAS, crlf=False), 'p.txt', HOY)['filas']), len(SANAS))
eq('(13) … y el ultimo campo llega limpio, sin \\r',
   analizar(SANO, 'p.txt', HOY)['filas'][0]['crudo']['store'], '')


print('\n== 14) LA MIGRACION Y EL PROCESADOR ESCRIBEN LA MISMA TABLA ==')
# 🔴 Son DOS sitios que describen una sola cosa: `CREATE TABLE` en la migracion y
#    `TIPADAS` en el procesador. Dos verdades esperando a discrepar — y si discrepan,
#    el fallo aparece en el INSERT de la carga, no aqui. Esto las ata.
# ⚠️ Y el modo de hacerlo mal esta a un paso: buscar el nombre de la columna EN TODO
#    el .sql saldria verde siempre, porque los `COMMENT ON COLUMN` (que son SQL, no
#    comentarios, asi que `sin_comentarios` no los quita) nombran esas mismas
#    columnas. Se recorta el CREATE TABLE y se mira SOLO dentro.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
from censo_migraciones import sin_comentarios  # noqa: E402

MIGRACION = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'migraciones', '2026-08-23_inventario_fba.sql')
with open(MIGRACION, encoding='utf-8') as fh:
    sql = sin_comentarios(fh.read())
ini = sql.lower().index('create table if not exists public.inventario_fba')
cuerpo = sql[sql.index('(', ini) + 1:sql.index(');', ini)]
cols_sql = set()
for linea in cuerpo.split('\n'):
    linea = linea.strip()
    if not linea or linea.lower().startswith('primary key'):
        continue
    cols_sql.add(linea.split()[0].strip(','))

eq('(14) el recorte del CREATE TABLE trae columnas (si no, no comprueba nada)',
   len(cols_sql) > 0, True)
cols_py = {c for _, c, _ in TIPADAS} | {'fichero', 'fecha_foto', 'crudo', 'procesado_at'}
eq('(14) las que el procesador escribe y la tabla no tiene', sorted(cols_py - cols_sql), [])
eq('(14) las que la tabla tiene y el procesador no escribe', sorted(cols_sql - cols_py), [])
# La PK tambien: si la migracion la pusiera en otra columna, el ON CONFLICT (sku)
# del procesador reventaria en la carga.
eq('(14) la PK de la migracion es sku', 'PRIMARY KEY (sku)' in cuerpo, True)
# 🔴 Y LO QUE ESTA MIGRACION NO PUEDE TOCAR, QUE ES LA MITAD QUE IMPORTA AHORA.
#    El 23-ago-2026 Fernando mando SACAR de aqui el `CREATE OR REPLACE` de
#    `moloka_buzones_fase0()`: de esa funcion cuelgan las CUATRO politicas
#    buzones_v2_* de storage.objects, o sea que ES la lista blanca de subida de
#    Elena. Si se rompe, Elena no puede meter informes. Eso se ve aparte y con el
#    delante, no de polizon en la migracion de una tabla que no lee nadie.
#    Este assert es lo que impide que vuelva a colarse sin querer.
# ⚠️ Se mira sobre el CODIGO (sin comentarios): la cabecera EXPLICA por que se saco
#    y nombra la funcion y las politicas. Un grep sobre el fichero crudo daria rojo
#    por la explicacion — que es justo el vicio de «lo que se lee como texto no
#    distingue codigo de comentario».
for aguja in ('moloka_buzones_fase0', 'storage.objects', 'buzones_v2',
              'CREATE OR REPLACE FUNCTION'):
    eq('(14) la migracion de la tabla NO toca %s' % aguja, aguja in sql, False)


print('\n== 15) EL HISTORICO: PELICULA, no otra foto ==')
# 🔴 La foto tira la hoja vieja en cada carga. Si el historico se equivocara de
#    clave —solo (sku), sin fecha_foto— cada carga pisaria la anterior y esto
#    dejaria de ser una pelicula SIN QUE NADIE SE ENTERE: la tabla existiria, se
#    llenaria, y solo tendria el ultimo dia. Es el fallo mudo peor de este PR.
from procesador_inventario_fba import (HIST_COLS, HIST_PK, TABLA_HIST,  # noqa: E402
                                       sql_crear_tabla_historico)

eq('(15) la PK del historico lleva fecha_foto', HIST_PK, ('sku', 'fecha_foto'))
eq('(15) … y el DDL tambien', 'PRIMARY KEY (sku, fecha_foto)' in sql_crear_tabla_historico(), True)
# 🔒 Anclado sobre lo que NO debe aparecer: preguntar «¿esta sku en la PK?» saldria
#    verde con la clave mal puesta, porque sku esta en las dos versiones.
eq('(15) … y NO es una PK de solo sku',
   'PRIMARY KEY (sku)' in sql_crear_tabla_historico(), False)
eq('(15) el historico NO guarda crudo (vive en el Storage)', 'crudo' in HIST_COLS, False)
eq('(15) … pero SI el fichero, que es la llave del rescate', 'fichero' in HIST_COLS, True)
eq('(15) lleva inbound_shipped, que es su razon de ser', 'inbound_shipped' in HIST_COLS, True)

# La migracion del historico y el procesador escriben la MISMA tabla.
MIG_H = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'migraciones', '2026-08-23_inventario_fba_historico.sql')
with open(MIG_H, encoding='utf-8') as fh:
    sql_h = sin_comentarios(fh.read())
ini_h = sql_h.lower().index('create table if not exists public.inventario_fba_historico')
cuerpo_h = sql_h[sql_h.index('(', ini_h) + 1:sql_h.index(');', ini_h)]
cols_h = set()
for linea in cuerpo_h.split('\n'):
    linea = linea.strip()
    if linea and not linea.lower().startswith('primary key'):
        cols_h.add(linea.split()[0].strip(','))
eq('(15) el recorte del CREATE TABLE trae columnas', len(cols_h) > 0, True)
py_h = set(HIST_COLS) | {'capturado_en'}
eq('(15) las que el procesador escribe y la tabla no tiene', sorted(py_h - cols_h), [])
eq('(15) las que la tabla tiene y el procesador no escribe', sorted(cols_h - py_h), [])
eq('(15) la migracion del historico tampoco toca storage',
   'storage.objects' in sql_h or 'moloka_buzones_fase0' in sql_h, False)
# 🔴 Y LA PK DE LA MIGRACION, que es la que manda: el DDL del procesador es
#    `IF NOT EXISTS`, o sea que sobre una base donde la tabla YA existe no hace
#    nada y la clave real es la que puso la migracion. Comprobar solo la del
#    procesador dejaba este agujero — cazado al romperlo a mano el 23-ago-2026:
#    con la PK de la migracion a `(sku)` el suite seguia VERDE.
eq('(15) la PK de la MIGRACION lleva fecha_foto',
   'PRIMARY KEY (sku, fecha_foto)' in cuerpo_h, True)
eq('(15) … y no es de solo sku', 'PRIMARY KEY (sku)' in cuerpo_h, False)
# La guarda de la propia migracion tambien tiene que exigirlo, no solo el DDL.
eq('(15) … y su numero de control lo verifica', "'sku,fecha_foto'" in sql_h, True)


print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · guardas de inventario_fba')
