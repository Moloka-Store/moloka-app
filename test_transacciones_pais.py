# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS del país en el procesador de transacciones.
Alemania ENTRA (mapa de columnas + parser de fecha MEDIDOS el 26-ago-2026 contra el
Custom Transaction Report real de amazon.de).

Qué prueba y qué NO:
  · SÍ: que DE resuelve sus columnas y sus fechas y ENTRA con tipo_norm correcto, contra
        cabecera y filas REALES del fichero (no inventadas).
  · SÍ: que la rama de fecha DE es LOAD-BEARING — la fecha numérica 'DD.MM.YYYY' NO parsea
        por la rama francesa; si alguien quita la rama DE, la Guarda 3 vuelve a abortar y
        estos asserts se ponen ROJOS. Anclado contra lo que cambió, no contra lo que ya había.
  · SÍ: que ES sigue leyéndose exactamente igual (la mitad que se olvida).
  · NO: las cifras alemanas AGREGADAS. Esas salen de correr el procesador contra el fichero
        real en Actions (el ensayo). Aquí se ejercita el parseo por fila y las guardas.

🔴 POR QUÉ CAMBIÓ. Hasta el 26-ago COLS_ALIAS['DE'] estaba vacío y el test probaba que DE
   ABORTABA (Guarda 2). Con el fichero real medido, DE ya entra: el test prueba lo contrario
   y, sobre todo, que el arreglo de la fecha no se puede quitar sin que salte algo.
"""
import io, os, sys
from datetime import date

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_transacciones.py')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_transacciones as P

# ── ES: cabecera MEDIDA (la de COLS_ALIAS['ES'], 28-jul). Si alguien la toca allí y no
#    aquí, este banco lo dice. ──────────────────────────────────────────────
CAB_ES = ('fecha y hora,tipo,numero de pedido,identificador de pago,sku,descripcion,'
          'cantidad,web de amazon,ventas de productos,impuesto de ventas de productos,'
          'tarifas de venta,tarifas de logistica de amazon,tarifas de otras transacciones,'
          'otro,total,estado de la transaccion,fecha de liberacion de la transaccion')
FILA_ES = ('1 ago 2026 10:00:00 CEST,Pedido,404-1,PAGO1,SKU-X,cosa,1,amazon.es,'
           '10,00,2.10,-1.50,-3.00,0,0,5.60,Liberado,2 ago 2026')

# ── DE: cabecera (línea 10) y filas del fichero (identidad/importes/fechas reales; desc. abreviada)
#    2026Jan1-2026Aug25CustomTransaction.csv (amazon.de). 29 columnas, campos entre comillas
#    (el separador decimal es la coma, por eso el fichero va entrecomillado). ──
_H = ["Datum/Uhrzeit", "Abrechnungsnummer", "Typ", "Bestellnummer", "SKU", "Beschreibung",
      "Menge", "Marketplace", "Versand", "Ort der Bestellung", "Bundesland", "Postleitzahl",
      "Steuererhebungsmodell", "Umsätze", "Produktumsatzsteuer", "Gutschrift für Versandkosten",
      "Steuer auf Versandgutschrift", "Gutschrift für Geschenkverpackung",
      "Steuer auf Geschenkverpackungsgutschriften", "Rabatte aus Werbeaktionen",
      "Steuer auf Aktionsrabatte", "Einbehaltene Steuer auf Marketplace", "Verkaufsgebühren",
      "Gebühren zu Versand durch Amazon", "Andere Transaktionsgebühren", "Andere", "Gesamt",
      "Transaktionsstatus", "Freigabedatum der Transaktion"]


def _row(vals):
    assert len(vals) == 29, 'fila con %d campos, no 29' % len(vals)
    return '"' + '","'.join(vals) + '"'


CAB_DE = _row(_H)
# Un pedido (Bestellung), una indemnización de inventario con SKU (Anpassung) y una
# compensación entre cuentas (Verbindlichkeit, que se deja SIN canon a propósito).
FILA_DE_PEDIDO = _row([
    "02.06.2026 18:28:02 UTC", "27205273902", "Bestellung", "028-4141567-1447500",
    "0Z-1PO5-YACU", "Funko Pop Daredevil", "1", "amazon.de", "Amazon", "Siero", "Asturias",
    "33429", "", "26,36", "5,54", "0", "0", "0", "0", "0", "0", "0", "-5,80", "-3,85", "0",
    "0", "22,25", "Veröffentlicht", "13.06.2026 23:40:37 UTC"])
FILA_DE_ANP = _row([
    "03.03.2026 05:33:54 UTC", "26430871022", "Anpassung", "", "HZ-ZYEZ-2D80",
    "Erstattung Lagerbestand - Im Lager verloren", "1", "", "", "", "", "", "", "0", "0", "0",
    "0", "0", "0", "0", "0", "0", "0", "0", "0", "2,41", "2,41", "Veröffentlicht",
    "03.03.2026 05:33:54 UTC"])
FILA_DE_VERB = _row([
    "03.03.2026 15:39:22 UTC", "26605196182", "Verbindlichkeit", "", "",
    "Kontoübergreifender Schuldenausgleich für IT", "", "", "", "", "", "", "", "0", "0", "0",
    "0", "0", "0", "0", "0", "0", "0", "0", "0", "-0,06", "-0,06", "Veröffentlicht",
    "03.03.2026 15:39:22 UTC"])


def csv_meta(cab, filas):
    """El informe real trae ~9 filas de metadatos antes de la cabecera. Se replica para que
    la Guarda 1 tenga que buscar la cabecera de verdad y no la coja en la primera línea."""
    meta = '\n'.join(['"Informe de transacciones"'] + ['' for _ in range(8)])
    return meta + '\n' + cab + '\n' + '\n'.join(filas) + '\n'


fallos = 0


def eq(nombre, got, exp):
    global fallos
    ok = got == exp
    if not ok:
        fallos += 1
    print(('OK  ' if ok else 'XX  ') + nombre + ('' if ok else '  got=%r exp=%r' % (got, exp)))


print('-- transacciones: el pais y su mapa de columnas --')

# ── 1) ALEMANIA SE PUEDE ELEGIR ─────────────────────────────────────────────
eq('(1) DE esta en PAISES_VALIDOS', 'DE' in P.PAISES_VALIDOS, True)
eq('(1) ... y amazon.de mapea a DE para la guarda de coherencia',
   P.MKT_A_PAIS.get('amazon.de'), 'DE')
eq('(1) los tres de siempre siguen', all(p in P.PAISES_VALIDOS for p in ('ES', 'IT', 'FR')), True)

# ── 2) 🇩🇪 ALEMANIA ENTRA: columnas + fecha + tipo_norm, contra fichero REAL ──
try:
    info = P.analizar(csv_meta(CAB_DE, [FILA_DE_PEDIDO, FILA_DE_ANP, FILA_DE_VERB]),
                      'DE', 'de.csv')
    movs = info['movimientos']
    eq('(2) DE ya no aborta: las 3 filas entran', len(movs), 3)
    ped = next((m for m in movs if m['tipo'] == 'Bestellung'), None)
    eq('(2) el pedido lleva su pais (del selector)', ped and ped['pais'], 'DE')
    eq('(2) ... tipo_norm=pedido (lo que alimenta vendo_30d)', ped and ped['tipo_norm'], 'pedido')
    eq('(2) ... y la fecha NUMERICA alemana parsea', ped and ped['fecha'], date(2026, 6, 2))
    eq('(2) ... con su cantidad', ped and ped['cantidad'], 1)
    eq('(2) ... y la comision cae en su columna (tal cual, con signo)',
       ped and ped['tarifa_venta'], -5.80)
    anp = next((m for m in movs if m['tipo'] == 'Anpassung'), None)
    eq('(2) Anpassung (indemnizacion con SKU) -> reembolso_inventario',
       anp and anp['tipo_norm'], 'reembolso_inventario')
    # 🔒 ANCLA de la desambiguacion exacto-primero: 'andere' (otro) NO debe capturar
    #    'andere transaktionsgebuhren' (tarifa_otras). Si _resolver_columna cayera a
    #    prefijo-primero, otro pasaria de 2,41 a 0,0 en silencio. Este assert lo caza.
    eq('(2) otro != tarifa_otras (Andere no captura Andere Transaktionsgebuehren)',
       anp and anp['otro'], 2.41)
    eq('(2) ... y tarifa_otras queda en su columna (0 en esta fila)',
       anp and anp['tarifa_otras'], 0.0)
    verb = next((m for m in movs if m['tipo'] == 'Verbindlichkeit'), None)
    eq('(2) Verbindlichkeit se deja SIN canon a proposito (tipo_norm NULL)',
       (verb is not None) and verb['tipo_norm'], None)
    eq('(2) ... y la GRITA el resumen (no en silencio)',
       'Verbindlichkeit' in info['tipos_sin_canon'], True)
except P.Aborta as e:
    eq('(2) DE NO debia abortar', str(e), 'sin aborto')

# ── 2b) 🔴 LA RAMA DE FECHA DE ES LOAD-BEARING (anclada contra lo que cambio) ─
eq('(2b) fecha DE numerica parsea por la rama DE',
   P.parse_fecha_pais('08.01.2026 00:27:58 UTC', 'DE'), date(2026, 1, 8))
eq('(2b) ... y NO parsea por la rama FR (por eso DE necesita rama propia)',
   P.parse_fecha_pais('08.01.2026 00:27:58 UTC', 'FR'), None)
_dh = P.parse_fecha_hora('02.06.2026 18:28:02 UTC', 'DE')
eq('(2b) fecha_hora DE trae la hora', (_dh is not None) and _dh.hour, 18)

# ── 3) 🔒 ES sigue entrando igual (la otra direccion, la que se olvida) ──────
try:
    info = P.analizar(csv_meta(CAB_ES, [FILA_ES]), 'ES', 'es.csv')
    eq('(3) ES sigue leyendose sin tocar nada', len(info['movimientos']) >= 1, True)
    eq('(3) ... con su pais puesto por el selector', info['movimientos'][0]['pais'], 'ES')
    eq('(3) ... su tipo canonico', info['movimientos'][0]['tipo_norm'], 'pedido')
    eq('(3) ... y su fecha por meses ES', info['movimientos'][0]['fecha'], date(2026, 8, 1))
except P.Aborta as e:
    eq('(3) ES NO debia abortar', str(e), 'sin aborto')

# ── 4) 🔒 El selector sigue mandando ────────────────────────────────────────
try:
    P.analizar(csv_meta(CAB_ES, [FILA_ES]), 'PT', 'pt.csv')
    eq('(4) un pais fuera de la lista tenia que abortar', 'no aborto', 'Aborta')
except P.Aborta as e:
    eq('(4) un pais fuera de la lista sigue abortando', '[PAIS]' in str(e), True)
    eq('(4) ... y el mensaje enseña la lista al dia', "'DE'" in str(e), True)

# ── 5) 🔒 Mapa DE medido ⇒ los TIPOS alemanes tambien ───────────────────────
# Rellenar columnas sin rellenar tipos dejaria vendo_30d a cero con datos dentro.
eq('(5) Bestellung esta en TIPO_CANON (sin el, vendo_30d seguiria a cero)',
   P.TIPO_CANON.get('Bestellung'), 'pedido')
eq('(5) COLS_ALIAS[DE] trae las obligatorias',
   all(P.COLS_ALIAS['DE'].get(c) for c in ('fecha', 'tipo', 'sku', 'cantidad', 'total')), True)

print('\n' + ('TODO OK' if fallos == 0 else '%d FALLOS' % fallos))
sys.exit(0 if fallos == 0 else 1)
