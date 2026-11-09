# -*- coding: utf-8 -*-
"""La tabla única de nombres de columna del CSV de Keepa (encargo keepa-nombres-columnas, 9-nov-2026).

🔴 QUÉ COMPRUEBA, EJECUTANDO lo de verdad (`analizar` del procesador, `examinar_csv` y el lector heredado del escáner):
   1. La tabla contra las DOS cabeceras reales (test_keepa_cabeceras.json: solo nombres de columna, ninguna fila).
   2. Los dos formatos de valor, y que no se toca ninguna otra columna.
   3. CABECERA VIEJA Y CABECERA NUEVA DAN LA MISMA FILA TIPADA Y EL MISMO CRUDO (dos filas inventadas).
   4. Lo que tiene que parar: los dos nombres a la vez y una columna obligatoria que falta, diciendo cuál.
   5. El escáner lee igual los dos ficheros.

🔒 Lo que NO ve: la carga real ni la base. Sin red, sin secretos y sin ningún dato de producto.
"""
import csv
import io
import json
import os
import sys
import tempfile

import escaner2_heredado_pro as pro
import escaner2_motor as e2
import keepa_cabeceras as kc
import procesador_keepa_escaparate as proc

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
with io.open('test_keepa_cabeceras.json', encoding='utf-8') as fh:
    REAL = json.load(fh)
ANTIGUA, NUEVA = REAL['antigua_6nov2026'], REAL['nueva_9nov2026']
fallos = []


def eq(nombre, got, exp):
    ok = got == exp
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (got, exp)))


FICHERO = 'KeepaExport-2026-11-09-VisualizadorDeProductos.csv'
PLAZO, PIS, HIST = kc.COL_PLAZO_CAJA, kc.COL_PRECIO_INFERIOR, kc.COLUMNA_RETIRADA
RETRASO_AMAZON = 'Amazon: Retraso en el envío de la oferta de Amazon'
INVERSA = {v: k for k, v in kc.EQUIVALENCIAS.items()}

# ── Dos filas INVENTADAS, por el nombre antiguo. Lo que no se dice va vacío, como en un export real. ──
COMUNES = {
    'Localización': 'es', 'Imagen': 'https://x.invalid/a.jpg', 'Recuento de imágenes': '1', 'Título': 'Producto inventado',
    'Tarifa FBA Pick&Pack': '3.5', '% de comisión de referencia': '15 %', 'Clasificación de Ventas: Actual': '1234',
    'Clasificación de Ventas: Descensos en los últimos 30 días': '5', RETRASO_AMAZON: '0 dia',
    'Oferta de almacén: Actual': '15.5', 'Lista de precio: Actual': '24.99', 'Nuevo: Actual': '20.5',
    'Recuento de ofertas elegibles para la Caja de Compra: Nuevo FBA': '2',
}
FILA_FBA = dict(COMUNES, **{
    'ASIN': 'B0INVENTA1', 'Códigos de producto: EAN': '8400000000017', 'Caja de Compra: Actual': '19.99',
    'Caja de Compra: Vendedor Caja de Compra': 'Vendedor Inventado (99%) / A1INVENTADO1', 'Caja de Compra: Es FBA': 'yes',
    'Caja de Compra: Stock': '3', 'Caja de Compra: Gastos de envío': '0', 'Nuevo, de Vendedor Externo FBA: Actual': '20.5',
    'Nuevo, de Vendedor Externo FBA: Stock': '7', 'Nuevo, de Vendedor Externo FBM: Stock': '2', PLAZO: '', PIS: '1898',
})
FILA_FBM = dict(COMUNES, **{
    'ASIN': 'B0INVENTA2', 'Códigos de producto: EAN': '8400000000024', 'Caja de Compra: Actual': '30',
    'Caja de Compra: Vendedor Caja de Compra': 'Otro Inventado (90%) / A2INVENTADO2', 'Caja de Compra: Es FBA': 'no',
    'Caja de Compra: Stock': '1', 'Caja de Compra: Gastos de envío': '3.99', PLAZO: '2 - 3 días', PIS: '',
})
# Cómo escribe Keepa esos dos valores desde el 9-nov.
FORMATO_NUEVO = {'B0INVENTA1': {PLAZO: '0 dia', PIS: '18.98'}, 'B0INVENTA2': {PIS: '-'}}


def csv_de(cabecera, filas):
    sal = io.StringIO()
    w = csv.writer(sal, lineterminator='\r\n')
    w.writerow(cabecera)
    w.writerows(filas)
    return sal.getvalue()


def texto_viejo(filas=(FILA_FBA, FILA_FBM)):
    return csv_de(ANTIGUA, [[f.get(h, '') for h in ANTIGUA] for f in filas])


def texto_nuevo(filas=(FILA_FBA, FILA_FBM), quitar=()):
    # Se construye desde la cabecera REAL nueva: cada columna busca su valor por su nombre antiguo.
    cab = [h for h in NUEVA if h not in quitar]
    salida = []
    for f in filas:
        cambios = FORMATO_NUEVO[f['ASIN']]
        fila = []
        for h in cab:
            antiguo = kc.EQUIVALENCIAS.get(h, h)
            fila.append(cambios.get(antiguo, f.get(antiguo, '')))
        salida.append(fila)
    return csv_de(cab, salida)


def analizar(texto):
    return proc.analizar(texto, FICHERO, proc.leer_nombre(FICHERO))


def aborta(texto):
    try:
        analizar(texto)
    except proc.Aborta as ex:
        return str(ex)
    return None


# ══════════════════════════════════════════════════════════════════
print('1 · la tabla contra las dos cabeceras reales')
SIN_HIST = [h for h in ANTIGUA if h != HIST]
eq('(1) 561 columnas la antigua y 560 la nueva', (len(ANTIGUA), len(NUEVA)), (561, 560))
eq('(1) 124 equivalencias', len(kc.EQUIVALENCIAS), 124)
eq('(1) 🔴 la nueva traducida es la antigua sin la retirada, COLUMNA A COLUMNA', kc.normalizar_cabecera(NUEVA), SIN_HIST)
eq('(1) una cabecera antigua no cambia', kc.normalizar_cabecera(ANTIGUA), ANTIGUA)
eq('(1) ningún nombre antiguo es clave de la tabla', [h for h in ANTIGUA if h in kc.EQUIVALENCIAS], [])
eq('(1) todas las claves están en la cabecera nueva', [h for h in kc.EQUIVALENCIAS if h not in NUEVA], [])
eq('(1) dos nuevos no van a parar al mismo antiguo', len(set(kc.EQUIVALENCIAS.values())), 124)
EXC = 'Comisión de referencia basada en el precio actual de la Buy Box'
eq('(1) 🔒 la excepción: la comisión de la Buy Box no se traduce', (EXC in NUEVA, EXC in ANTIGUA, EXC in kc.EQUIVALENCIAS), (True, True, False))
USADO = [h for h in NUEVA if h.startswith('Caja de Compra Usado')]
eq('(1) 🔒 las 19 «Caja de Compra Usado» se llaman igual en las dos', (len(USADO), all(h in ANTIGUA for h in USADO)), (19, True))
eq('(1) con BOM y espacio duro también', kc.normalizar_cabecera([chr(0xFEFF) + 'Buy' + chr(0xA0) + 'Box: Actual ']), ['Caja de Compra: Actual'])

# ══════════════════════════════════════════════════════════════════
print('2 · los dos formatos de valor')
for col, antes, despues, nombre in (
        (PLAZO, '0 dia', '', "'0 dia' → vacío"),
        (PLAZO, ' 0 dia ', '', "'0 dia' con espacios → vacío"),
        (PLAZO, '1 dia', '1 dia', "'1 dia' se queda"),
        (PLAZO, '', '', 'el plazo vacío se queda'),
        (PIS, '18.98', '1898', 'euros → céntimos'),
        (PIS, '5.10', '510', 'euros con cero final'),
        (PIS, '189.9', '18990', 'un solo decimal'),
        (PIS, '-', '', "'-' → vacío"),
        (PIS, '1898', '1898', 'céntimos del formato antiguo: se quedan'),
        (PIS, '', '', 'vacío se queda'),
        (PIS, '18.985', '18.985', 'lo que no son céntimos exactos NO se redondea'),
        (PIS, 'a.b', 'a.b', 'lo que no es un número se deja'),
        (RETRASO_AMAZON, '0 dia', '0 dia', "🔴 el '0 dia' de Amazon es un dato: no se toca"),
        ('Otra columna', '-', '-', "el '-' de otra columna no se toca"),
        ('Otra columna', '18.98', '18.98', 'los decimales de otra columna no se tocan')):
    eq('(2) %s' % nombre, kc.normalizar_valor(col, antes), despues)

# ══════════════════════════════════════════════════════════════════
print('3 · cabecera vieja y cabecera nueva: la misma fila tipada y el mismo crudo')
VIEJO, NUEVO = analizar(texto_viejo()), analizar(texto_nuevo())
eq('(3) dos filas en cada uno', (len(VIEJO['filas']), len(NUEVO['filas'])), (2, 2))
for pos, nombre in ((0, 'caja FBA'), (1, 'caja FBM')):
    eq('(3) 🔴 %s: la MISMA fila tipada' % nombre, NUEVO['filas'][pos]['registro'], VIEJO['filas'][pos]['registro'])
    eq('(3) 🔴 %s: el MISMO crudo' % nombre, NUEVO['filas'][pos]['crudo'], VIEJO['filas'][pos]['crudo'])
    eq('(3) %s: el crudo con las 561 claves de siempre' % nombre, len(NUEVO['filas'][pos]['crudo']), 561)
R0, C0 = NUEVO['filas'][0]['registro'], NUEVO['filas'][0]['crudo']
# Para que el «igual» de arriba no sea «igual de vacío»: los datos llegan, y con los nombres antiguos.
eq('(3) el precio de la caja llega', R0['bb_precio'], 19.99)
eq('(3) el vendedor llega y su seller id también', (R0['bb_vendedor'][:8], R0['bb_seller_id']), ('Vendedor', 'A1INVENTADO1'))
eq('(3) FBA y stock de la caja', (R0['bb_es_fba'], R0['bb_stock']), (True, 3))
eq('(3) las de terceros llegan', (R0['p3_fba_precio'], R0['p3_fba_stock'], R0['p3_fbm_stock']), (20.5, 7, 2))
eq("(3) el plazo con '0 dia' queda vacío en la tipada", R0['bb_plazo_txt'], None)
eq('(3) y en el crudo, con su clave antigua', C0[PLAZO], '')
eq('(3) el plazo de verdad se conserva', NUEVO['filas'][1]['registro']['bb_plazo_txt'], '2 - 3 días')
eq('(3) el precio inferior en céntimos en el crudo', (C0[PIS], NUEVO['filas'][1]['crudo'][PIS]), ('1898', ''))
eq("(3) 🔴 el crudo no conserva ningún nombre nuevo", [k for k in C0 if k in kc.EQUIVALENCIAS], [])
eq('(3) la retirada sigue como clave, vacía', C0[HIST], '')
eq('(3) lo que vino en las otras columnas, igual', (C0['Oferta de almacén: Actual'], C0['Lista de precio: Actual'], C0[RETRASO_AMAZON]), ('15.5', '24.99', '0 dia'))
eq('(3) un fichero antiguo que traiga la retirada la conserva', len(analizar(texto_viejo())['filas'][0]['crudo']), 561)

# ══════════════════════════════════════════════════════════════════
print('4 · lo que tiene que parar, diciendo qué')
eq('(4) 🔒 que falte la retirada NO aborta', aborta(texto_nuevo()), None)
_sin = aborta(texto_nuevo(quitar=('Buy Box: Actual',)))
eq('(4) falta una tipada en un fichero nuevo: aborta en la Guarda 1', (_sin or '').startswith('[Guarda 1]'), True)
eq('(4) y dice los dos nombres', "'Caja de Compra: Actual' (o 'Buy Box: Actual')" in (_sin or ''), True)
_ambos = csv_de(NUEVA + ['Caja de Compra: Actual'], [[''] * len(NUEVA) + ['1']])
_msg = aborta(_ambos)
eq('(4) 🔴 los dos nombres a la vez: aborta, no elige', (_msg or '').startswith('[Guarda 1 bis]'), True)
eq('(4) y nombra la columna', "'Buy Box: Actual' y 'Caja de Compra: Actual'" in (_msg or ''), True)
eq('(4) una columna sin nombre antiguo se nombra sola', kc.nombre_para_aviso('ASIN'), "'ASIN'")

# ══════════════════════════════════════════════════════════════════
print('5 · el escáner lee igual los dos ficheros')
COL_PAIS, COL_CAIDAS = e2.columnas_keepa()
COLS_FICHA = e2.columnas_ficha_compartida()
with tempfile.TemporaryDirectory() as tmp:
    def ruta(nombre, texto):
        p = os.path.join(tmp, nombre)
        with io.open(p, 'w', encoding='utf-8-sig', newline='') as fh:
            fh.write(texto)
        return p

    viejo, nuevo = ruta('viejo.csv', texto_viejo()), ruta('nuevo.csv', texto_nuevo())
    a, b = (e2.examinar_csv(p, pro, COL_PAIS, COL_CAIDAS, COLS_FICHA) for p in (viejo, nuevo))
    eq('(5) 🔴 examinar_csv da lo mismo con los dos', b, a)
    eq('(5) y lee el fichero nuevo de verdad', (b['pais'], b['filas'], b['caidas']['B0INVENTA1']), ('ES', 2, 5.0))
    l_v, l_n = pro.leer_csv_visualizador(viejo), pro.leer_csv_visualizador(nuevo)
    eq('(5) 🔴 el lector heredado da lo mismo con los dos', l_n, l_v)
    rec = l_n['8400000000017'][0]
    eq('(5) el lector ve la caja y si es FBA', (rec['buybox'], rec['es_fba']), (19.99, True))

    sin_caja = ruta('sin.csv', texto_nuevo(quitar=('Buy Box: Actual',)))
    try:
        e2.examinar_csv(sin_caja, pro, COL_PAIS, COL_CAIDAS, COLS_FICHA)
        _m = ''
    except e2.CsvIlegible as ex:
        _m = str(ex)
    eq('(5) le falta la obligatoria: lo dice en castellano y con los dos nombres',
       _m, "le faltan columnas del Visualizador: 'Caja de Compra: Actual' (o 'Buy Box: Actual')")
    ambos = ruta('ambos.csv', _ambos)
    try:
        e2.examinar_csv(ambos, pro, COL_PAIS, COL_CAIDAS, COLS_FICHA)
        _m = ''
    except e2.CsvIlegible as ex:
        _m = str(ex)
    eq('(5) 🔴 los dos nombres a la vez se rechazan', 'nombre nuevo y con el antiguo' in _m, True)

print('\n' + ('XX ' + str(len(fallos)) + ' fallos: ' + '; '.join(fallos) if fallos else 'OK todo'))
sys.exit(1 if fallos else 0)
