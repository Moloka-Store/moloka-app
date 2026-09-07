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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from procesador_inventario_fba import (  # noqa: E402
    analizar, avisar_inbound, Aborta, UMBRAL_FILAS, TIPADAS, NUMERICAS,
    CABECERA_ESPERADA, ESPERADAS, HEADER_FC, ORIGEN_INFORME, ORIGEN_DESCONOCIDO,
    DERIVADAS_COLS, HIST_COLS, HIST_PK, TABLA_HIST, sql_crear_tabla_historico,
    censo_cabecera, misma_version, guarda_continuidad, guarda_transito_desconocido,
    guarda_salto_a_transito_dentro, modelo_del_disponible,
    MODELO_TRANSITO_APARTE, MODELO_TRANSITO_DESCONOCIDO,
    TECHO_CAIDA_VENDIBLE_DIA, TECHO_CAIDA_ALMACEN_DIA, CAIDA_MAX_FICHAS)

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

# 🔬 LA VERSION DEGRADADA, la que Amazon sirvio el 7-sep-2026: las mismas columnas
#    MENOS las dos que se fue. Se construye QUITANDO de la de arriba, no copiando
#    otra lista a mano: dos listas escritas a mano se separan en cuanto una cambia.
CABECERA_24 = [h for h in CABECERA if h not in ESPERADAS]


def sin_esperadas(filas):
    """Las mismas filas, sin las columnas que el 7-sep no vinieron."""
    quitar = {POR[h] for h in ESPERADAS}
    return [[c for i, c in enumerate(f) if i not in quitar] for f in filas]


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
    # 🔬 El testigo de Amazon cumple SU identidad, medida el 6-sep-2026 sobre las
    #    381 filas reales: afn-onhand-buyable = vendible + transito, desvio 0. Una
    #    fila sana que no la cumpliera haria gritar al contraste en cada prueba, y
    #    un aviso que sale siempre deja de leerse.
    f[POR['afn-onhand-buyable-quantity']] = str(
        int(f[POR['afn-fulfillable-quantity']]) + int(f[POR['afn-fc-transfer-quantity']]))
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
# 🔴 AQUI YA NO SE ANCLA UN NUMERO DE COLUMNAS, y es el cambio de fondo del
#    7-sep-2026. Habia una constante `N_COLUMNAS = 26` que NINGUNA guarda leia (la
#    guarda 3 mide contra la cabecera del propio fichero), asi que parecia proteger
#    el ancho del informe y no protegia nada. Y ademas dejo de ser cierta: ese dia
#    Amazon sirvio 24. Un ancla que nadie lee no es un ancla; quien registra la
#    forma del informe ahora es el CENSO (Guarda 11), que ademas guarda CUALES.
eq('(0) las 26 columnas de la version larga y las 24 de la corta',
   (len(CABECERA), len(CABECERA_24)), (26, 24))
eq('(0) los encabezados OBLIGATORIOS son de la cabecera real',
   [h for h in CABECERA_ESPERADA if h not in CABECERA], [])
# 🔑 Y la particion del contrato: las dos esperadas NO estan entre las que abortan.
eq('(0) las esperadas quedan fuera de la Guarda 1',
   sorted(h for h in ESPERADAS if h in CABECERA_ESPERADA), [])
eq('(0) … y son exactamente las dos que Amazon se llevo',
   sorted(ESPERADAS),
   ['afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity'])
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
# 🔑 EL PRECIO ES LA EXCEPCION, Y TIENE PAREJA EN LAS DOS DIRECCIONES. Un hueco
#    en `your-price` NO aborta —un precio ausente no es stock y no puede tumbar el
#    inventario de un almacen— pero tampoco se traga: va a NULL y queda anotado.
#    Caso real: XQ-QJXG-7UQ1 el 7-sep-2026, 1 fila de 381.
precio = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
precio[5][POR['your-price']] = ''
corto, _ = corta(fichero(precio))
eq('(8) your-price vacio: NO aborta', corto, False)
sin_precio = analizar(fichero(precio), 'p.txt', HOY)
eq('(8) … el precio queda a NULO, no a 0',
   sin_precio['filas'][5]['registro']['your_price'], None)
eq('(8) … y la ficha queda anotada con su sku',
   [sku for sku, _ in sin_precio['precios_vacios']], ['SKU-00006'])
eq('(8) … y solo esa (las demas conservan su precio)',
   sin_precio['filas'][4]['registro']['your_price'], 19.99)
# 🔴 La pareja que impide que esto se convierta en «los huecos ya no importan»:
#    una CANTIDAD vacia sigue abortando exactamente igual que antes.
cantidad = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
cantidad[5][POR['afn-warehouse-quantity']] = ''
corto, msg = corta(fichero(cantidad))
eq('(8) … pero una CANTIDAD vacia sigue abortando', corto, True)
eq('(8) … y por la razon de siempre', 'viene VACÍA' in msg, True)

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
eq('(12) … y se tipan 17 de las 26', len(TIPADAS), 17)
eq('(12) … de las que 11 son numericas', len(NUMERICAS), 11)
eq('(12) … y 15 de las 17 abortan si faltan; 2 son esperadas',
   (len(CABECERA_ESPERADA), len(ESPERADAS)), (15, 2))


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
# 🔑 Las columnas que anade una migracion POSTERIOR cuentan igual: la tabla la
#    describe el conjunto de las migraciones, no solo la que la creo. Sin esto,
#    anadir una columna dejaria este cotejo en rojo para siempre o —peor— invitaria
#    a reescribir una migracion ya aplicada.
# 🔴 SE LEEN **TODAS** las migraciones, no una nombrada a mano. Con el nombre
#    escrito aqui, cada migracion nueva dejaba este cotejo en rojo hasta que
#    alguien se acordase de anadirla — y la tentacion entonces es tocar el test en
#    vez del codigo. Leyendolas todas, el cotejo se mantiene solo.
# ⚠️ Y cada `ADD COLUMN` se atribuye a SU tabla: buscar el nombre de la columna en
#    todo el .sql daria por buena una columna anadida a OTRA tabla cualquiera.
def columnas_anadidas(por_tabla=None):
    """{tabla: {columnas}} de todos los ALTER TABLE ... ADD COLUMN de migraciones/."""
    carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migraciones')
    salida = {}
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.endswith('.sql') or nombre.startswith('_PRUEBA'):
            continue
        with open(os.path.join(carpeta, nombre), encoding='utf-8') as fh:
            limpio = sin_comentarios(fh.read())
        for trozo in limpio.split('ALTER TABLE')[1:]:
            cuerpo = trozo.split(';')[0]
            m = re.match(r'\s+(?:ONLY\s+)?(?:public\.)?(\w+)', cuerpo)
            if not m:
                continue
            # 🔴 Las columnas GENERADAS se quedan FUERA, y no es un detalle: las
            #    calcula Postgres al escribir, asi que el procesador NO PUEDE
            #    ponerlas en su INSERT — un `GENERATED ALWAYS` en la lista de
            #    columnas es un error de SQL en cada carga. `inventario_fba.asin_k`
            #    es una de ellas (migracion del 25-ago, para que el cruce por ASIN
            #    baje al indice con la RLS puesta).
            cols = set()
            for frag in re.split(r'ADD COLUMN\s+', cuerpo)[1:]:
                m2 = re.match(r'(?:IF NOT EXISTS\s+)?(\w+)', frag)
                if not m2:
                    continue
                trozo = frag.split(',')[0] if 'GENERATED' not in frag.split(',')[0].upper() else frag
                if 'GENERATED' in trozo.upper():
                    continue
                cols.add(m2.group(1))
            if cols:
                salida.setdefault(m.group(1), set()).update(cols)
    return salida


ALTERADAS = columnas_anadidas()
anadidas = ALTERADAS.get('inventario_fba', set())
eq('(14) las migraciones anaden columnas a inventario_fba (si no, no comprueba nada)',
   len(anadidas) > 0, True)
# 🔒 Y la pareja que impide que el recorte por tabla sea decorativo: lo que se
#    anadio al HISTORICO no puede colarse como si fuera de la foto.
eq('(14) … y el recorte separa las dos tablas',
   'inventario_fba_historico' in ALTERADAS, True)
# 🔴 Y el aserto que impide el error de SQL en cada carga: la columna GENERADA no
#    esta entre las que el procesador escribe. Postgres la calcula el solo.
eq('(14) el procesador NO escribe la columna generada asin_k',
   'asin_k' in {c for _, c, _ in TIPADAS} | set(DERIVADAS_COLS), False)
eq('(14) … y el recorte tampoco la cuenta como suya', 'asin_k' in anadidas, False)
cols_sql |= anadidas
cols_py = {c for _, c, _ in TIPADAS} | {'fichero', 'fecha_foto', 'crudo', 'procesado_at'}
cols_py |= set(DERIVADAS_COLS)
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
cols_h |= ALTERADAS.get('inventario_fba_historico', set())
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


print('\n== 16) QUE FICHERO SE PROCESA: el que se PIDE, o el mas reciente ==')
# 🔴 Nace con el buzon de la app (24-ago-2026). Hasta hoy esta caneria cogia siempre
#    «el mas reciente» del buzon, y eso es una loteria en cuanto hay dos informes
#    dentro: Elena suelta el suyo, se procesa otro, y la pantalla dice «Procesado».
#    La direccion que importa aqui NO es «¿aborta si no esta?» sino «¿se cae al mas
#    reciente cuando el pedido no aparece?» — porque un fallback silencioso pasaria
#    igual de verde y seria justo el bug.
from procesador_inventario_fba import elegir_fichero  # noqa: E402

VIEJO = {'name': '50632020686.txt', 'updated_at': '2026-08-21T10:00:00Z'}
NUEVO = {'name': '50638020688.txt', 'updated_at': '2026-08-23T13:17:00Z'}
# A proposito DESORDENADO y con el viejo delante: si alguien quitara el `sorted`, el
# «mas reciente» pasaria a ser «el primero que liste el Storage» sin que nada chille.
BUZON = [VIEJO, NUEVO]

eq('(16) sin pedir nada, el mas reciente', elegir_fichero(BUZON, '')[0]['name'], NUEVO['name'])
eq('(16) … y por FECHA, no por el orden en que vino la lista',
   elegir_fichero([NUEVO, VIEJO], '')[0]['name'], NUEVO['name'])
eq('(16) se pide el VIEJO y se procesa el viejo',
   elegir_fichero(BUZON, VIEJO['name'])[0]['name'], VIEJO['name'])
# 🔒 El OBJETO, no el nombre: de el sale la fecha_foto. Si devolviera otro con el
#    mismo nombre, la foto se sellaria con una fecha que no es la suya.
eq('(16) … y devuelve el OBJETO entero, que es de donde sale la fecha_foto',
   elegir_fichero(BUZON, VIEJO['name'])[0] is VIEJO, True)

falta, msg = False, ''
try:
    elegir_fichero(BUZON, 'no_existe.txt')
except Aborta as e:
    falta, msg = True, str(e)
eq('(16) 🔴 se pide uno que NO esta → ABORTA', falta, True)
eq('(16) … y el aborto dice cual se pidio', 'no_existe.txt' in msg, True)
eq('(16) … y lista lo que si hay, para que se vea el dedazo', VIEJO['name'] in msg, True)

# 🔴 LA MITAD QUE SE OLVIDA, y aqui es la que vale: que NO caiga al mas reciente.
#    Un `return recientes[0]` en vez del `raise` pasaria los tres asserts de arriba
#    salvo este. Se comprueba por el valor devuelto, no por el mensaje.
cayo = None
try:
    cayo = elegir_fichero(BUZON, 'no_existe.txt')[0]['name']
except Aborta:
    pass
eq('(16) 🔴 … y NO se cae al mas reciente', cayo, None)


print('\n== 17) EL DATO LLEGA: el input del workflow y el env ==')
# 🔴 Un CI verde no prueba que una feature este viva (§3 de CLAUDE.md). `elegir_fichero`
#    puede estar perfecta y no ejecutarse nunca: si el .yml no declara el input, la app
#    recibe un 422 al disparar; si el `env:` no lo pasa, el procesador ve FICHERO vacio
#    y vuelve a coger el mas reciente EN SILENCIO. Estos asserts mueren si se quita
#    cualquiera de las dos piezas.
# ⚠️ Sobre el texto SIN comentarios: la cabecera del input explica por que existe y
#    nombra `fichero` y `FICHERO` varias veces — un grep sobre el fichero crudo daria
#    verde con el input borrado. Es la trampa de siempre: lo que se lee como texto no
#    distingue codigo de comentario.
#    📌 Esta es la SEGUNDA copia de este recorte (la otra, en test_tsv_quote_none.py).
#       A la tercera deja de escribirse y se convierte en funcion, al lado de
#       `sin_comentarios` de scripts/censo_migraciones.py.
def sin_almohadillas(texto):
    return '\n'.join(l for l in texto.split('\n') if not l.lstrip().startswith('#'))

YML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '.github', 'workflows', 'procesar-inventario-fba.yml')
with open(YML, encoding='utf-8') as fh:
    yml = sin_almohadillas(fh.read())

eq('(17) el recorte deja codigo (si no, no comprueba nada)', 'workflow_dispatch' in yml, True)
eq('(17) el .yml declara el input `fichero`', '\n      fichero:' in yml, True)
eq('(17) 🔴 … y el env se lo pasa al procesador',
   'FICHERO: ${{ inputs.fichero }}' in yml, True)
# 🔒 Anclado sobre lo que NO debe aparecer: `required: true` en ese input haria que la
#    app —y cualquier lanzamiento a mano sin rellenarlo— se comiera un 422.
#    ⚠️ El recorte se hace por INDENTACION, no con un `index` del siguiente salto de
#       linea: la linea de abajo (`description:`) lleva OCHO espacios y empieza igual
#       que una de seis, asi que cortar por ahi dejaba el trozo en una sola linea —
#       y entonces el assert de `required: true` no podia fallar NUNCA. Cazado al
#       verlo pasar con el trozo vacio.
lineas = yml[yml.index('\n      fichero:') + 1:].split('\n')
trozo, hermanos = [lineas[0]], 0
for linea in lineas[1:]:
    if linea[:6] == '      ' and linea[6:7] not in ('', ' '):
        break
    trozo.append(linea)
trozo = '\n'.join(trozo)
eq('(17) el recorte coge el bloque entero del input (%d lineas)' % len(trozo.split('\n')),
   len(trozo.split('\n')) >= 4, True)
eq('(17) … y NO es obligatorio (un 422 dejaria a Elena sin boton)',
   'required: true' in trozo, False)
eq('(17) … lo es opcional, dicho a proposito', 'required: false' in trozo, True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'procesador_inventario_fba.py'), encoding='utf-8') as fh:
    codigo = sin_almohadillas(fh.read())
eq('(17) 🔴 y main() le pasa FICHERO de verdad, no una cadena vacia',
   'elegir_fichero(txts, FICHERO)' in codigo, True)


print('\n== 18) EL CONTRATO PARTIDO: lo que aborta y lo que se echa en falta ==')
# 🔴 LAS DOS DIRECCIONES, y aqui la segunda es la que de verdad importa: que el
#    fichero degradado ENTRE (para que la carga diaria no se pare) pero que lo que
#    falta NO se rellene con un cero.
degradado = analizar(fichero(sin_esperadas(SANAS), cabecera=CABECERA_24), 'p.txt', HOY)
eq('(18) el fichero de 24 columnas ENTRA', len(degradado['filas']), len(SANAS))
eq('(18) … y dice cuales le faltan',
   degradado['esperadas_ausentes'],
   ['afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity'])
# 🔑 EL ASSERT QUE VALE MAS DE TODO EL FICHERO: NULL, no 0. Un `== 0` aqui saldria
#    verde con la version que rellena ceros, que es justo el fallo que se persigue.
eq('(18) 🔴 el transito queda a NULO en TODAS las filas, no a 0',
   {f['registro']['fc_transfer'] for f in degradado['filas']}, {None})
eq('(18) … y ninguna es 0 (que seria «no hay», y es otra cosa)',
   any(f['registro']['fc_transfer'] == 0 for f in degradado['filas']), False)
eq('(18) … el origen lo dice en el dato, no solo en el log',
   {f['registro']['fc_transfer_origen'] for f in degradado['filas']}, {ORIGEN_DESCONOCIDO})
eq('(18) … y el testigo de Amazon tambien queda a NULO',
   {f['registro']['onhand_buyable'] for f in degradado['filas']}, {None})
# La pareja: con la version larga, todo eso se llena y el origen es el informe.
eq('(18) con las 26 columnas el transito viene del informe',
   {f['registro']['fc_transfer_origen'] for f in sano['filas']}, {ORIGEN_INFORME})
eq('(18) … y el transito es un numero, no un nulo',
   sano['filas'][0]['registro']['fc_transfer'], 0)
eq('(18) … y el testigo llega, cuadrando con vendible + transito',
   sano['filas'][0]['registro']['onhand_buyable'], 5)
# 🔴 Y LO QUE **NO** HA CAMBIADO: una OBLIGATORIA que falta sigue abortando. Sin
#    esto, «partir el contrato» seria un eufemismo de «quitar la guarda 1».
sin_vendible = [h for h in CABECERA if h != 'afn-fulfillable-quantity']
quita = POR['afn-fulfillable-quantity']
filas_sv = [[c for i, c in enumerate(f) if i != quita] for f in SANAS]
corto, msg = corta(fichero(filas_sv, cabecera=sin_vendible))
eq('(18) 🔒 una columna OBLIGATORIA que falta sigue abortando', corto, True)
eq('(18) … y por la Guarda 1 de siempre', '[Guarda 1]' in msg, True)
# El modelo del disponible lo decide la version, no una constante.
eq('(18) con la columna del transito, el modelo es «aparte»',
   modelo_del_disponible(CABECERA), MODELO_TRANSITO_APARTE)
eq('(18) sin ella, el modelo es «desconocido» (NO el modelo nuevo)',
   modelo_del_disponible(CABECERA_24), MODELO_TRANSITO_DESCONOCIDO)


print('\n== 19) GUARDA 11 · el censo de la cabecera, y la VERSION ==')
eq('(19) sin carga anterior no se inventa comparacion',
   censo_cabecera(CABECERA_24, None), (None, None))
eq('(19) … y entonces la version NO se da por igual',
   misma_version(CABECERA_24, None), False)
eq('(19) misma cabecera = misma version', misma_version(CABECERA, CABECERA), True)
eq('(19) el caso del 7-sep: faltan dos, no sobra ninguna',
   censo_cabecera(CABECERA_24, CABECERA),
   (['afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity'], []))
eq('(19) … y por tanto NO es la misma version',
   misma_version(CABECERA_24, CABECERA), False)
# 🔑 El caso al reves, que es el que nadie vio venir: Amazon METIO esas dos
#    columnas en su dia y nadie se entero. Sobrar no aborta, pero se censa.
eq('(19) el caso de vuelta: sobran dos, no falta ninguna',
   censo_cabecera(CABECERA, CABECERA_24),
   ([], ['afn-fc-transfer-quantity', 'afn-onhand-buyable-quantity']))


print('\n== 20) GUARDA 10 · continuidad contra la foto anterior ==')
AYER, HOY10 = datetime.date(2026, 9, 6), datetime.date(2026, 9, 7)
# 🔴 EL CASO REAL DEL 7-sep, y las dos lecturas del MISMO dato:
#    almacen 6.881 → 6.635 (−246) · vendible 6.437 → 6.453 (+16).
#    Con otra version se compara el vendible y PASA; con la misma version se
#    compararia el almacen y ABORTA. Las dos direcciones sobre las mismas cifras.
eq('(20) 7-sep con version distinta (mira el vendible): PASA',
   guarda_continuidad(AYER, HOY10, False, 6437, 6453, 6881, 6635, 381, 381,
                      permitir_salto=False), [])
try:
    guarda_continuidad(AYER, HOY10, True, 6437, 6453, 6881, 6635, 381, 381,
                       permitir_salto=False)
    eq('(20) 7-sep con la MISMA version (mira el almacen): ABORTA', False, True)
except Aborta as e:
    eq('(20) 7-sep con la MISMA version (mira el almacen): ABORTA', True, True)
    eq('(20) … y lo dice en castellano y sin nombres de columna',
       'El almacen ha caido 246 unidades en 1 dia(s)' in str(e), True)
    eq('(20) … y dice cual era el techo', 'son %d' % TECHO_CAIDA_ALMACEN_DIA in str(e), True)
    eq('(20) … sin colar el nombre de la columna en esa primera linea',
       'warehouse' in str(e).split('\n')[0], False)
# El techo del vendible, justo por debajo y justo por encima.
eq('(20) el vendible cayendo justo el techo: NO aborta',
   guarda_continuidad(AYER, HOY10, False, 6437, 6437 - TECHO_CAIDA_VENDIBLE_DIA,
                      6881, 6881, 381, 381, permitir_salto=False), [])
try:
    guarda_continuidad(AYER, HOY10, False, 6437, 6437 - TECHO_CAIDA_VENDIBLE_DIA - 1,
                       6881, 6881, 381, 381, permitir_salto=False)
    eq('(20) … y una unidad mas: ABORTA', False, True)
except Aborta:
    eq('(20) … y una unidad mas: ABORTA', True, True)
# 🔑 Se normaliza POR DIA: los huecos del historico van de 1 a 3 dias, y una caida
#    de dos dias no puede juzgarse con el techo de uno.
eq('(20) con dos dias de hueco, el techo es el doble',
   guarda_continuidad(datetime.date(2026, 9, 5), HOY10, False,
                      6437, 6437 - 2 * TECHO_CAIDA_VENDIBLE_DIA, 6881, 6881,
                      381, 381, permitir_salto=False), [])
# El catalogo: 20% menos fichas aborta, 5% menos no.
try:
    guarda_continuidad(AYER, HOY10, True, 6437, 6437, 6881, 6881, 381, 305,
                       permitir_salto=False)
    eq('(20) 20% menos fichas: ABORTA', False, True)
except Aborta as e:
    eq('(20) 20% menos fichas: ABORTA', True, True)
    eq('(20) … y dice el porcentaje perdido', '19.9%' in str(e), True)
eq('(20) 5% menos fichas: NO aborta',
   guarda_continuidad(AYER, HOY10, True, 6437, 6437, 6881, 6881, 381, 362,
                      permitir_salto=False), [])
# 🔴 La primera carga NO se juzga: no hay contra que comparar, y una comprobacion
#    sin nada que comparar no comprueba nada. La cubre el suelo de la Guarda 4.
eq('(20) sin foto anterior: no aplica',
   guarda_continuidad(None, HOY10, False, 0, 6453, 0, 6635, 0, 381,
                      permitir_salto=False), [])
eq('(20) la misma fecha (recarga de la misma foto): no aplica',
   guarda_continuidad(HOY10, HOY10, True, 6437, 1, 6881, 1, 381, 381,
                      permitir_salto=False), [])
# La valvula, con nombre y dejando rastro.
motivos = guarda_continuidad(AYER, HOY10, True, 6437, 6453, 6881, 6635, 381, 381,
                             permitir_salto=True, escribir=lambda *a: None)
eq('(20) PERMITIR_SALTO=1 la deja pasar…', len(motivos), 1)
eq('(20) … pero devuelve el motivo, no lo borra', 'ha caido 246' in motivos[0], True)


print('\n== 21) GUARDA 12 · el cerrojo mientras las vistas lean el nulo como 0 ==')
# 🔴 Que `fc_transfer` pueda ser NULL ya funciona (bloque 18). Lo que NO funciona
#    todavia es quien lo LEE: medido el 7-sep-2026 en produccion, cuatro objetos
#    hacen COALESCE(fc_transfer, 0). Abrir la carga hoy cambiaria un aborto ruidoso
#    por un disponible ~250 uds corto y creible.
try:
    guarda_transito_desconocido(ORIGEN_DESCONOCIDO)
    eq('(21) con el transito desconocido: ABORTA', False, True)
except Aborta as e:
    eq('(21) con el transito desconocido: ABORTA', True, True)
    eq('(21) … y nombra los objetos que hay que arreglar',
       all(v in str(e) for v in ('salud_fba', 'v_salud_asin', 'v_trackeador_pantalla')), True)
    eq('(21) … y dice como se abre', 'VISTAS_QUE_LEEN_NULO_COMO_CERO' in str(e), True)
# 🔑 Las dos parejas calladas: con el transito leido no estorba, y el dia que se
#    arreglen las vistas se abre vaciando la lista — sin tocar ninguna guarda.
eq('(21) con el transito leido del informe: no dice nada',
   guarda_transito_desconocido(ORIGEN_INFORME), None)
eq('(21) con la lista vacia (vistas ya arregladas): se abre',
   guarda_transito_desconocido(ORIGEN_DESCONOCIDO, vistas=[]), None)


print('\n== 22) GUARDA 13 · el dia en que sumar empieza a contar doble ==')
# 🔴 El cambio que Amazon anuncio: las unidades en transferencia entre centros
#    dejan de estar aparte porque pasan a ser comprables. El dia que aparezcan
#    dentro del vendible, `vendible + transito` cuenta DOBLE.
try:
    guarda_salto_a_transito_dentro(6437, 6692, 248, 248, 255, 1)
    eq('(22) el vendible absorbe el transito de ayer: ABORTA', False, True)
except Aborta as e:
    eq('(22) el vendible absorbe el transito de ayer: ABORTA', True, True)
    eq('(22) … y dice cuanto no lo explica ninguna entrega',
       '255 de ellas NO las explica' in str(e), True)
    eq('(22) … y manda cambiar el modelo, no forzar la guarda',
       'MODELO_TRANSITO_DENTRO' in str(e), True)
# 🔑 LA PAREJA QUE HACE QUE ESTA GUARDA MIDA ALGO: una ENTREGA grande sube el
#    vendible igual de golpe. Si abortara tambien ahi, seria ruido cada vez que
#    llega un camion y se aprenderia a forzarla. La diferencia esta en que en una
#    entrega los entrantes BAJAN justo lo que sube el vendible.
eq('(22) una entrega grande (los entrantes bajan igual): NO aborta',
   guarda_salto_a_transito_dentro(6437, 6692, 500, 245, 255, 1), False)
eq('(22) un dia normal (+16): NO aborta',
   guarda_salto_a_transito_dentro(6437, 6453, 248, 248, 255, 1), False)
eq('(22) el mejor dia de subida medido (+40): NO aborta',
   guarda_salto_a_transito_dentro(6437, 6477, 248, 248, 255, 1), False)
eq('(22) sin transito ayer no hay nada que absorber: NO aborta',
   guarda_salto_a_transito_dentro(6437, 6900, 248, 248, 0, 1), False)


print('\n== 23) EL TESTIGO: el disponible que calcula Amazon ==')
# 🔬 Medido el 6-sep-2026: afn-onhand-buyable-quantity = vendible + transito en las
#    381 filas, desvio 0. Aqui se comprueba que la discrepancia se GRITA con las
#    dos cifras — es lo unico que permite saber cual de las dos falla.
testigo = [fila(n) for n in range(1, UMBRAL_FILAS + 6)]
testigo[3][POR['afn-onhand-buyable-quantity']] = '99'   # deberia ser 5 + 0
con_ruido = analizar(fichero(testigo), 'p.txt', HOY)
eq('(23) la discrepancia se anota con sku y las dos cifras',
   con_ruido['onhand_discrepa'], [('SKU-00004', 99, 5)])
eq('(23) … y NO aborta (es un testigo, no una fuente)', len(con_ruido['filas']),
   len(testigo))
eq('(23) cuando cuadra, no dice nada', sano['onhand_discrepa'], [])
# 🔴 Y con el transito DESCONOCIDO no se contrasta: comparar contra un nulo leido
#    como 0 daria una discrepancia falsa en cada fila.
eq('(23) con el transito desconocido no se inventa discrepancia',
   degradado['onhand_discrepa'], [])


print('\n== 24) EL PUENTE: el disponible estimado ==')
from procesador_inventario_fba import (  # noqa: E402
    estimar_disponible, _reparto, ORIGEN_LEIDO, ORIGEN_ESTIMADO)

D6 = datetime.date(2026, 9, 6)


def reg(sku, asin, available, fc=None, ent=0):
    """Una fila ya analizada, tal como se la pasa `main()` al puente."""
    return {'registro': {'sku': sku, 'asin': asin, 'available': available,
                         'fc_transfer': fc, 'inbound_working': 0,
                         'inbound_shipped': ent, 'inbound_receiving': 0}}


# 🔬 EL CASO QUE MOTIVA TODO, con las cifras reales de B0D6CXB8J1 el 7-sep-2026:
#    el informe dice vendible 0 y no trae transito; el internacional dice 12; la
#    pantalla del Seller enseña «Disponible (FBA) 12».
f = [reg('S1', 'B0D6CXB8J1', 0)]
r = estimar_disponible(f, {'B0D6CXB8J1': (12, D6)}, escribir=lambda *a: None)
eq('(24) sin transito y con internacional: estima', f[0]['registro']['disponible_estimado'], 12)
eq('(24) … y lo marca como estimado', f[0]['registro']['disponible_origen'], ORIGEN_ESTIMADO)
eq('(24) … y deja dicho de que dia era la fuente',
   f[0]['registro']['disponible_fuente_fecha'], D6)

# 🔴 LOS ENTRANTES SE RESTAN. Sin esa resta se contaria dos veces lo que va de
#    camino, que es el error mas caro que puede tener esta formula.
f = [reg('S1', 'A1', 4, ent=10)]
estimar_disponible(f, {'A1': (16, D6)}, escribir=lambda *a: None)
eq('(24) los entrantes se restan (16 - 10 entrantes - 4 vendible = 2 encima)',
   f[0]['registro']['disponible_estimado'], 6)

# 🔑 EL VENDIBLE ES EL SUELO: un internacional atrasado NO puede bajar el dato.
f = [reg('S1', 'A1', 40)]
estimar_disponible(f, {'A1': (5, D6)}, escribir=lambda *a: None)
eq('(24) el internacional atrasado no baja el vendible',
   f[0]['registro']['disponible_estimado'], 40)

# 🔴 SIN INTERNACIONAL NO SE INVENTA: NULO y «desconocido», jamas un 0 ni el
#    vendible disfrazado de estimacion.
f = [reg('S1', 'A1', 7)]
estimar_disponible(f, {}, escribir=lambda *a: None)
eq('(24) sin fila en el internacional: NULO', f[0]['registro']['disponible_estimado'], None)
eq('(24) … y dicho en el dato', f[0]['registro']['disponible_origen'], 'desconocido')

# 🔑 CON EL TRANSITO LEIDO manda el dato leido, pero la estimacion se guarda al
#    lado: es el falsador permanente del puente.
f = [reg('S1', 'A1', 10, fc=5)]
r = estimar_disponible(f, {'A1': (15, D6)}, escribir=lambda *a: None)
eq('(24) con transito leido, el origen es «leido»',
   f[0]['registro']['disponible_origen'], ORIGEN_LEIDO)
eq('(24) … y la estimacion se guarda igual, para poder contrastarla',
   f[0]['registro']['disponible_estimado'], 15)
eq('(24) … y cuando coincide con la verdad no se grita', r['discrepa'], [])
f = [reg('S1', 'A1', 10, fc=5)]
r = estimar_disponible(f, {'A1': (99, D6)}, escribir=lambda *a: None)
eq('(24) … y cuando NO coincide, se anota con las dos cifras',
   r['discrepa'], [('S1', 99, 15)])

# 🔬 EL REPARTO entre SKU de un mismo ASIN, en proporcion al vendible. Medido: 13
#    casos commingled en 11 dias y NINGUNO con excedente, asi que hoy esto no
#    mueve un dato — que es el mejor momento para escribirlo bien.
f = [reg('S1', 'A1', 30), reg('S2', 'A1', 10)]
estimar_disponible(f, {'A1': (60, D6)}, escribir=lambda *a: None)
eq('(24) el excedente se reparte en proporcion al vendible',
   [x['registro']['disponible_estimado'] for x in f], [45, 15])
# 🔴 Y NO SE PIERDE NI SE INVENTA UNA UNIDAD: es la razon de los restos mayores.
f = [reg('S1', 'A1', 1), reg('S2', 'A1', 1), reg('S3', 'A1', 1)]
estimar_disponible(f, {'A1': (4, D6)}, escribir=lambda *a: None)
eq('(24) el reparto conserva el total (1 ud entre 3 fichas iguales)',
   sum(x['registro']['disponible_estimado'] for x in f), 4)

# 🔴 VARIOS SKU Y NINGUNO CON VENDIBLE: no hay proporcion, y NO se parte a ojo.
f = [reg('S1', 'A1', 0), reg('S2', 'A1', 0)]
avisos = []
r = estimar_disponible(f, {'A1': (8, D6)}, escribir=avisos.append)
eq('(24) sin proporcion con la que repartir: NULO en las dos',
   [x['registro']['disponible_estimado'] for x in f], [None, None])
eq('(24) … marcadas como desconocido',
   [x['registro']['disponible_origen'] for x in f], ['desconocido', 'desconocido'])
eq('(24) … y se GRITA con el ASIN y las unidades', r['sin_reparto'], [('A1', 2, 8)])
eq('(24) … en el log, no solo en el resumen', any('A1' in a for a in avisos), True)
# La pareja: con UNA sola ficha sin vendible, si se puede, y se estima.
f = [reg('S1', 'A1', 0)]
estimar_disponible(f, {'A1': (8, D6)}, escribir=lambda *a: None)
eq('(24) una sola ficha sin vendible: todo el excedente es suyo',
   f[0]['registro']['disponible_estimado'], 8)


print('')
print('== 25) LA FOTO DEL INTERNACIONAL: UNA, Y LA MISMA PARA TODOS ==')
# 🔴 EL FALLO QUE ESTO FIJA. `internacional_por_asin` hacia
#    `DISTINCT ON (asin) ... ORDER BY asin, fecha_foto DESC`: a cada ASIN le daba SU
#    ultima lectura, cada uno de un dia distinto. El internacional es cajon FOTO —lo
#    que no viene en la hoja se BORRA—, asi que un ASIN que no esta en la ultima foto
#    no es «no lo se»: es «ahi ya no queda nada». Rescatarle una lectura de hace
#    semanas resucita unidades que no existen.
#    🔬 Medido el 7-sep-2026 sobre los 11 dias del historico, a nivel de ASIN-dia:
#         una foto (lo de ahora)   → error 549 uds · clava 2.414 · se pasa 78
#         la ultima de cada ASIN   → error 2.204 uds · clava 2.456 · se pasa 715
from procesador_inventario_fba import (  # noqa: E402
    internacional_por_asin, foto_internacional)

D1 = datetime.date(2026, 8, 30)
D2 = datetime.date(2026, 9, 3)
D3 = datetime.date(2026, 9, 6)


class CursorInternacional:
    """Doble del cursor SOLO para el internacional. Dos consultas y en este orden:
    1) la fecha de la foto que toca, 2) las filas DE ESA foto.

    🔒 Es un guion, no un motor de SQL: contesta por el NUMERO DE LLAMADA. Por eso
       cuenta las llamadas y el test las comprueba — la version vieja hacia UNA
       sola consulta, asi que con este doble se pone roja por el numero de viajes
       antes incluso de mirar el resultado.
    """

    def __init__(self, filas):
        self.filas = filas            # [(fecha_foto, asin, quantity)]
        self.llamadas = []
        self._ultimo = None

    def execute(self, sql, params):
        self.llamadas.append(params)
        if len(self.llamadas) == 1:
            fechas = [f for f, _, _ in self.filas if f <= params[0]]
            self._ultimo = [(max(fechas) if fechas else None,)]
        else:
            foto, asines = params
            acumulado = {}
            for f, a, q in self.filas:
                if f == foto and a in asines:
                    acumulado[a] = acumulado.get(a, 0) + q
            self._ultimo = sorted(acumulado.items())

    def fetchone(self):
        return self._ultimo[0] if self._ultimo else None

    def fetchall(self):
        return self._ultimo


# El internacional: A1 esta en las tres fotos; A2 solo en la primera (se cayo de la
# hoja el 3-sep); A3 aparece con dos paises el 6-sep.
INTL = [(D1, 'A1', 10), (D1, 'A2', 7),
        (D2, 'A1', 8),
        (D3, 'A1', 6), (D3, 'A3', 4), (D3, 'A3', 5)]

cur = CursorInternacional(INTL)
res = internacional_por_asin(cur, D3, ['A1', 'A2', 'A3'])
eq('(25) el ASIN que sigue en la ultima foto: su cifra y la fecha de esa foto',
   res.get('A1'), (6, D3))
eq('(25) los paises de un mismo ASIN se suman (TODOS, sin filtrar)',
   res.get('A3'), (9, D3))
# 🔴 LA PAREJA QUE HACE QUE ESTO MIDA ALGO.
eq('(25) el ASIN que se cayo de la hoja NO se rescata de una foto vieja',
   'A2' in res, False)
eq('(25) … y por tanto queda DESCONOCIDO, que es lo que dice el internacional',
   res.get('A2'), None)
eq('(25) dos consultas: primero que foto toca, luego las filas de esa foto',
   len(cur.llamadas), 2)
eq('(25) … y la segunda pregunta por LA FOTO elegida, no por «<= la fecha»',
   cur.llamadas[1][0], D3)

# 🔒 UN DIA SIN FOTO PROPIA se estima con la anterior ENTERA: el internacional no se
#    carga a diario (21 fotos entre el 23-jul y el 7-sep). Lo que no se hace es
#    mezclar dias.
cur = CursorInternacional(INTL)
res = internacional_por_asin(cur, datetime.date(2026, 9, 5), ['A1', 'A2', 'A3'])
eq('(25) sin foto de ese dia, se usa la anterior entera', res.get('A1'), (8, D2))
eq('(25) … y con ella tampoco vuelve el ASIN caido', 'A2' in res, False)

# 🔴 JAMAS UNA FOTO FUTURA: estimar el 30-ago con el internacional del 6-sep daria un
#    numero que ese dia no existia.
cur = CursorInternacional(INTL)
res = internacional_por_asin(cur, D1, ['A1', 'A2'])
eq('(25) no se estima un dia con datos posteriores', res.get('A1'), (10, D1))
eq('(25) … y ahi A2 SI estaba, luego se estima', res.get('A2'), (7, D1))

# Sin ninguna foto anterior no se inventa nada, y sin ASIN no se viaja a la base.
cur = CursorInternacional(INTL)
eq('(25) antes de la primera foto del internacional: vacio',
   internacional_por_asin(cur, datetime.date(2026, 7, 1), ['A1']), {})
cur = CursorInternacional(INTL)
eq('(25) sin ASIN que preguntar, no se toca la base',
   (internacional_por_asin(cur, D3, []), len(cur.llamadas)), ({}, 0))
cur = CursorInternacional(INTL)
eq('(25) la foto que toca se puede pedir sola', foto_internacional(cur, D2), D2)

# 🔒 EL DESEMPATE DEL REPARTO ES POR SKU, no por el orden del fichero: es lo que hace
#    que el procesador y la migracion de relleno escriban LO MISMO.
f = [reg('S9', 'A1', 1), reg('S1', 'A1', 1)]
estimar_disponible(f, {'A1': (3, D3)}, escribir=lambda *a: None)
eq('(25) la unidad suelta se la lleva el sku menor, venga como venga el fichero',
   {x['registro']['sku']: x['registro']['disponible_estimado'] for x in f},
   {'S1': 2, 'S9': 1})


print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · guardas de inventario_fba')
