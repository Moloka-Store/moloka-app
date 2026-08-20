# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS del país en el procesador de transacciones — Alemania entra (20-ago-2026).

Qué prueba y qué NO:
  · SÍ: que un país SIN mapa de columnas medido ABORTA, y que el aborto sirve para algo
        (dice que no es culpa del fichero e imprime la cabecera REAL, que es lo que hay
        que copiar para rellenar el mapa).
  · SÍ: que ES sigue leyéndose exactamente igual. Es la mitad que se olvida — una guarda
        que sólo se ha visto ponerse roja no está probada, está ejecutada.
  · NO: las cifras alemanas. Esas salen de correr el procesador contra el fichero REAL en
        Actions. Datos sintéticos no prueban nada (§3 de CLAUDE.md); aquí sólo se hacen
        saltar las guardas a propósito.

🔴 POR QUÉ EXISTE. Alemania no se «descartaba»: es que no se podía elegir. El selector
   tenía tres opciones, así que el fichero alemán no se había descargado NUNCA — y de esa
   ausencia salieron dos cosas que parecían hechos:
     · el ISD alemán del 3 %, sostenido en «no hay ni una venta alemana en la tabla»;
     · `v_velocidad_ventas_paneu.uds_30d_de`, que filtra por `pais = 'DE'` sobre una tabla
       sin una sola fila alemana: cero para todos los ASIN, siempre. No falla — devuelve
       cero, y un cero parece un dato.
"""
import io, os, sys

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_transacciones.py')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_transacciones as P

# ── Cabeceras de mentira, y lo que cada una prueba ──────────────────────────
# 🔒 La española es la MEDIDA (está en COLS_ALIAS['ES'], 28-jul-2026), así que si alguien
#    la toca ahí y no aquí, este banco lo dice.
CAB_ES = ('fecha y hora,tipo,numero de pedido,identificador de pago,sku,descripcion,'
          'cantidad,web de amazon,ventas de productos,impuesto de ventas de productos,'
          'tarifas de venta,tarifas de logistica de amazon,tarifas de otras transacciones,'
          'otro,total,estado de la transaccion,fecha de liberacion de la transaccion')
FILA_ES = ('1 ago 2026 10:00:00 CEST,Pedido,404-1,PAGO1,SKU-X,cosa,1,amazon.es,'
           '10,00,2.10,-1.50,-3.00,0,0,5.60,Liberado,2 ago 2026')

# ⚠️ La alemana es INVENTADA, y da igual que lo sea: lo que se prueba es que el procesador
#    la RECHAZA por no tener mapa medido, no que la entienda. Si algún día se mide la de
#    verdad, esta se queda igual — sigue siendo un fichero de un país sin mapa.
CAB_DE = ('datum/uhrzeit,typ,bestellnummer,zahlungsnummer,sku,beschreibung,menge,'
          'amazon-website,produktumsatz,produktumsatzsteuer,verkaufsgebuehren,'
          'gebuehren fuer versand durch amazon,andere transaktionsgebuehren,sonstige,'
          'gesamt,transaktionsstatus,freigabedatum der transaktion')
FILA_DE = ('1. Aug. 2026 10:00:00 CEST,Bestellung,404-2,ZAHL1,SKU-Y,ding,1,amazon.de,'
           '10,00,2.10,-1.50,-3.00,0,0,5.60,Freigegeben,2. Aug. 2026')


def csv_de(cab, fila):
    """El informe real trae ~9 filas de metadatos antes de la cabecera. Se replica para que
    la Guarda 1 tenga que buscarla de verdad y no la encuentre en la primera línea."""
    meta = '\n'.join(['"Informe de transacciones"'] + ['' for _ in range(8)])
    return meta + '\n' + cab + '\n' + fila + '\n'


fallos = 0


def eq(nombre, got, exp):
    global fallos
    ok = got == exp
    if not ok:
        fallos += 1
    print(('OK  ' if ok else 'XX  ') + nombre + ('' if ok else '  got=%r exp=%r' % (got, exp)))


print('-- transacciones: el pais y su mapa de columnas --')

# ── 1) ALEMANIA SE PUEDE ELEGIR, que es lo que no se podía ──────────────────
eq('(1) DE esta en PAISES_VALIDOS', 'DE' in P.PAISES_VALIDOS, True)
eq('(1) ... y amazon.de mapea a DE para la guarda de coherencia',
   P.MKT_A_PAIS.get('amazon.de'), 'DE')
# 🔒 Los tres de siempre siguen ahí. Sin esto, borrar uno pasaría inadvertido.
eq('(1) los tres de siempre siguen', all(p in P.PAISES_VALIDOS for p in ('ES', 'IT', 'FR')), True)

# ── 2) 🔴 Y ABORTA, porque su mapa de columnas NO esta medido ───────────────
try:
    P.analizar(csv_de(CAB_DE, FILA_DE), 'DE', 'de.csv')
    eq('(2) DE tenia que abortar', 'no aborto', 'Aborta')
except P.Aborta as e:
    m = str(e)
    # 🔴 Que llegue a la Guarda 2 ya prueba la ampliacion de CAB_TIPO: en aleman la columna
    #    se llama «Typ», y con la lista vieja ('tipo','type') esto moria en la Guarda 1
    #    preguntando «¿es un Custom Transaction Report?» — mandando a buscar donde no esta.
    eq('(2) llega a la Guarda 2 (o sea, CAB_TIPO reconoce «typ»)', '[Guarda 2]' in m, True)
    eq('(2) aborta por el MAPA VACIO, no por el mensaje generico',
       'mapa de columnas de DE' in m and 'VAC' in m, True)
    eq('(2) ... y dice que NO es culpa del fichero ni del selector',
       'NO es un fallo del fichero ni del selector' in m, True)
    # 🔑 ESTO ES PARA LO QUE SIRVE EL ABORTO: la primera carga alemana es una MEDICION.
    eq('(2) ... e imprime la cabecera REAL, que es lo que hay que copiar',
       'datum/uhrzeit' in m and 'freigabedatum der transaktion' in m, True)
    eq('(2) ... y dice donde pegarla', "COLS_ALIAS['DE']" in m, True)

# ── 3) 🔒 LA OTRA DIRECCION · ES sigue entrando igual ───────────────────────
# Una guarda que solo se ha visto en rojo no esta probada. Si esto se cae, el arreglo de
# Alemania se ha llevado por delante los tres paises que ya funcionaban.
try:
    info = P.analizar(csv_de(CAB_ES, FILA_ES), 'ES', 'es.csv')
    eq('(3) ES sigue leyendose sin tocar nada', len(info['movimientos']) >= 1, True)
    eq('(3) ... con su pais puesto por el selector', info['movimientos'][0]['pais'], 'ES')
    eq('(3) ... y su tipo canonico', info['movimientos'][0]['tipo_norm'], 'pedido')
except P.Aborta as e:
    eq('(3) ES NO debia abortar', str(e), 'sin aborto')

# ── 4) 🔒 Y EL SELECTOR SIGUE SIENDO EL QUE MANDA ──────────────────────────
try:
    P.analizar(csv_de(CAB_ES, FILA_ES), 'PT', 'pt.csv')
    eq('(4) un pais fuera de la lista tenia que abortar', 'no aborto', 'Aborta')
except P.Aborta as e:
    eq('(4) un pais fuera de la lista sigue abortando', '[PAIS]' in str(e), True)
    eq('(4) ... y el mensaje enseña la lista al dia', "'DE'" in str(e), True)

# ── 5) ⚠️ LA SEGUNDA MITAD DEL TRABAJO, ANOTADA COMO TEST ──────────────────
# Rellenar COLS_ALIAS['DE'] hace que el fichero ENTRE, pero no que CUENTE: la vista de
# velocidad filtra por `tipo_norm = 'pedido'`, y sin literales alemanes en TIPO_CANON esas
# filas quedan con tipo_norm NULL. `uds_30d_de` seguiria valiendo cero, con datos dentro.
# 🔑 Este assert se pone rojo el dia que alguien mida las columnas alemanas y se olvide de
#    los tipos — que es exactamente cuando hace falta que alguien lo diga.
_de_medido = bool(P.COLS_ALIAS.get('DE'))
_tipos_de = any(t in P.TIPO_CANON for t in ('Bestellung', 'Erstattung', 'Bestellungen'))
eq('(5) si el mapa de columnas DE ya esta medido, los TIPOS aleman tambien',
   (not _de_medido) or _tipos_de, True)

print('\n' + ('TODO OK' if fallos == 0 else '%d FALLOS' % fallos))
sys.exit(0 if fallos == 0 else 1)
