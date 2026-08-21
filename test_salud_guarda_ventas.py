# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS de la Guarda 11 — las columnas de ventas vacías de golpe.

Qué prueba y qué NO:
  · SÍ: que la guarda ABORTA con las cifras REALES del 16-ago-2026, y que se queda
        CALLADA con las cifras REALES de las ocho fotos sanas. Las dos direcciones.
  · SÍ: que el mensaje trae la proporción de esta carga Y la de las anteriores, que es
        lo que permite decidir si la rara es la foto o ha cambiado el negocio.
  · NO: la carga en sí. Eso sale de correr el procesador contra el fichero REAL en
        Actions. Aquí sólo se hace saltar la guarda a propósito.

🔴 POR QUÉ EXISTE ESTA GUARDA, en corto: el 16-ago entró un informe con
   `units_shipped_t30` a NULL en 173 de 215 filas (80,5 %) contra el ~17 % de siempre, y
   pasó todas las guardas porque el STOCK venía perfecto. Estuvo CINCO DÍAS alimentando la
   portada, que decía «Manda 0 productos» mientras la pestaña Enviar decía 65. El detalle
   completo, con la calibración, está junto a la guarda en `procesador_salud_fba.py`.
"""
import os, sys

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_salud_fba.py')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_salud_fba as P

# ── LAS CIFRAS REALES, medidas en producción el 21-ago-2026 ─────────────────
# `salud_fba_historico`, marketplace ES: (fecha, filas, nulos en units_shipped_t30)
SANAS = [
    ('2026-07-22', 216, 34),   # 15,7 %
    ('2026-07-25', 219, 40),   # 18,3 %
    ('2026-07-28', 221, 36),   # 16,3 %
    ('2026-07-30', 217, 33),   # 15,2 %
    ('2026-08-07', 229, 49),   # 21,4 %  ← la PEOR de las sanas
    ('2026-08-09', 224, 44),   # 19,6 %
    ('2026-08-10', 223, 39),   # 17,5 %
    ('2026-08-12', 220, 38),   # 17,3 %
]
AVERIADA = ('2026-08-16', 215, 173)   # 80,5 %


class CurFalso:
    """Un cursor de mentira que devuelve las fotos anteriores que se le digan.
    🔒 Devuelve MÁS RECIENTE PRIMERO, como el `ORDER BY 1 DESC` de la consulta real."""

    def __init__(self, previas):
        self._previas = previas

    def execute(self, sql, args=None):
        limite = args[1] if args and len(args) > 1 else 5
        self._filas = list(reversed(self._previas))[:limite]

    def fetchall(self):
        return self._filas


def filas_con(total, nulos, campo='units_shipped_t30'):
    """`filas` como las arma el procesador: lista de dicts con su `registro`."""
    return [{'registro': {campo: (None if i < nulos else 3)}} for i in range(total)]


fallos = 0


def eq(nombre, got, exp):
    global fallos
    ok = got == exp
    if not ok:
        fallos += 1
    print(('OK  ' if ok else 'XX  ') + nombre + ('' if ok else '  got=%r exp=%r' % (got, exp)))


print('-- salud_fba: la guarda de las columnas de ventas --')

# ── 1) 🔴 CON LA AVERÍA REAL, ABORTA ────────────────────────────────────────
# Se le dan las cinco fotos anteriores al 16-ago, que es lo que habría visto ese día.
cur = CurFalso(SANAS[-5:])
try:
    P.guarda_columnas_ventas(cur, filas_con(AVERIADA[1], AVERIADA[2]), ['ES'])
    eq('(1) la averia del 16-ago tenia que abortar', 'no aborto', 'Aborta')
except P.Aborta as e:
    m = str(e)
    eq('(1) ABORTA con las cifras reales del 16-ago', '[Guarda 11]' in m, True)
    # 🔑 Lo que Fernando pidió del mensaje: la de esta carga Y la de las anteriores.
    eq('(1) ... dice la proporcion de ESTA carga', '173/215 = 80.5% NULL' in m, True)
    eq('(1) ... y la de las cinco anteriores', '2026-08-12 17.3%' in m and '2026-07-30 15.2%' in m, True)
    eq('(1) ... y el tope que se ha aplicado', 'Tope: 35.0%' in m, True)
    # 🔒 Y dice qué hacer, que es la mitad del valor de un aborto.
    eq('(1) ... y manda a volver a descargar', 'Vuelve a descargar' in m, True)
    eq('(1) ... sin dar por hecho que es el fichero: contempla que cambie el negocio',
       'ha cambiado el negocio' in m, True)

# ── 2) 🔒 LA OTRA DIRECCION · con las fotos SANAS se queda CALLADA ──────────
# Es la mitad que se olvida. Una guarda que sólo se ha visto en rojo no está probada.
# Se recorre la serie real: cada foto contra las cinco que la precedieron.
for i in range(3, len(SANAS)):
    fecha, total, nulos = SANAS[i]
    cur = CurFalso(SANAS[max(0, i - 5):i])
    try:
        P.guarda_columnas_ventas(cur, filas_con(total, nulos), ['ES'])
        eq(f'(2) la foto sana del {fecha} pasa ({100.0 * nulos / total:.1f}%)', True, True)
    except P.Aborta as e:
        eq(f'(2) la foto sana del {fecha} NO debia abortar', str(e), 'sin aborto')

# 🔴 EL CASO QUE MAS SE ACERCA, nombrado aparte porque es el que decide si el umbral
#    tiene margen: el 07-ago es la peor de las sanas (21,4 %) y se mide contra una
#    mediana de 16,3 % → tope 32,6 %. Se queda en dos tercios del tope.
cur = CurFalso(SANAS[:4])
try:
    P.guarda_columnas_ventas(cur, filas_con(229, 49), ['ES'])
    eq('(2) 🔴 la PEOR foto sana (07-ago, 21,4%) pasa con margen', True, True)
except P.Aborta as e:
    eq('(2) la peor sana NO debia abortar', str(e), 'sin aborto')

# ── 3) 🔒 DONDE ESTA EL CORTE, medido en las dos orillas ────────────────────
# Con la mediana de las cinco previas al 16-ago en 17,5 %, el tope es 35 %. Se comprueba
# que el corte cae donde dice y no dos puntos más allá: un umbral que nadie ha visto
# actuar en su borde es un umbral supuesto.
cur = CurFalso(SANAS[-5:])
try:
    P.guarda_columnas_ventas(cur, filas_con(200, 69), ['ES'])   # 34,5 % < 35 %
    eq('(3) 🔒 justo por DEBAJO del tope (34,5%) pasa', True, True)
except P.Aborta as e:
    eq('(3) 34,5% NO debia abortar', str(e), 'sin aborto')
try:
    P.guarda_columnas_ventas(cur, filas_con(200, 71), ['ES'])   # 35,5 % > 35 %
    eq('(3) 35,5% tenia que abortar', 'no aborto', 'Aborta')
except P.Aborta as e:
    eq('(3) 🔴 justo por ENCIMA del tope (35,5%) aborta', '[Guarda 11]' in str(e), True)

# ── 4) 🔒 SIN HISTORICO NO SE INVENTA UNA MEDIANA ──────────────────────────
# Con menos de tres fotos previas no hay banda que calcular. Sólo actúa el suelo
# absoluto, y se DICE en el log que la guarda va a medio gas.
cur = CurFalso(SANAS[-2:])
try:
    P.guarda_columnas_ventas(cur, filas_con(215, 173), ['ES'])  # 80,5 % > 50 %
    eq('(4) sin historico, el 80% tenia que abortar por el suelo', 'no aborto', 'Aborta')
except P.Aborta as e:
    eq('(4) 🔴 sin historico, el suelo del 50% sigue abortando', 'suelo fijo del 50%' in str(e), True)
cur = CurFalso(SANAS[-2:])
try:
    P.guarda_columnas_ventas(cur, filas_con(215, 60), ['ES'])   # 27,9 % < 50 %
    eq('(4) 🔒 ... y por debajo del suelo NO bloquea un estreno legitimo', True, True)
except P.Aborta as e:
    eq('(4) 27,9% sin historico NO debia abortar', str(e), 'sin aborto')

# ── 5) 🔒 UN INFORME PERFECTO NO DA FALSO POSITIVO ─────────────────────────
# Cero nulos es el caso mejor posible, y tiene que pasar. Si esto se pusiera rojo, la
# guarda estaría midiendo al revés.
cur = CurFalso(SANAS[-5:])
try:
    P.guarda_columnas_ventas(cur, filas_con(215, 0), ['ES'])
    eq('(5) 🔒 un informe SIN nulos pasa', True, True)
except P.Aborta as e:
    eq('(5) cero nulos NO debia abortar', str(e), 'sin aborto')

print('\n' + ('TODO OK' if fallos == 0 else '%d FALLOS' % fallos))
sys.exit(0 if fallos == 0 else 1)
