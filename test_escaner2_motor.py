# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO (escaner2_motor.py) — encargo B, trozo 1, 24-sep-2026.

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta la logica de verdad con datos de mentira.

QUE PRUEBA:
  (A) QUE LA FORMULA ES LA DEL VIEJO, NO UNA COPIA. Cada pieza que el escaner nuevo usa
      (`calc_rentabilidad`, `decision_de`, las reglas de EAN/chase/caja, el IVA…) sale del
      fichero `moloka_escaner_nube.py`, de la linea donde vive su `def`. Y si alguien la borra
      o la duplica en el viejo, el nuevo NO arranca: se prueba contra una copia rota.
  (B) LA FORMULA, con los casos que el propio viejo se exige al arrancar (su caso canonico y el
      pedido frances 404-7912092-2024339), y los umbrales de la decision.
  (C) EL LECTOR DE CSV. No hay un CSV real del Visualizador en el repo (y uno de produccion no
      se sube a un repo publico), asi que es SINTETICO: las cabeceras son las EXACTAS del
      Escaner Pro (`CSV_COLS`) y del escaparate (`TIPADAS`), y las celdas imitan el formato
      medido en exports reales del 24-sep-2026 («15.01 %», «yes»/«no», EAN con ceros y varios
      separados por «, », «es»/«de» en minuscula, celdas vacias). El pais sale del dato.
  (D) PRECIO, COMISION Y TARIFA, COMO EL ESCANER PRO: se corre `escanear_pro` de verdad sobre
      el mismo CSV y se coteja fila a fila.
  (E) LA FOTO: filtro del director, chase Funko y chase suelto apartados, caja 5+1 a precio
      por unidad (÷6 leido del viejo), EAN raro fuera, duplicado a la mas barata, rescate GTIN.
  (F) LAS SEIS PUERTAS con sus motivos, una a una.
  (G) EL CUADRE: tiene que ponerse ROJO si las entradas no son la suma de las puertas.
  (H) LA COMPARACION con el viejo: leer su Excel, quedarse con la ultima opinion, y rotular
      «diferencia de criterio» solo lo que el encargo dice.
"""
import ast
import csv
import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import escaner2_motor as e2
import moloka_escaner_pro as pro

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def casi(nombre, obtenido, esperado, tol=0.005):
    ok = obtenido is not None and abs(obtenido - esperado) < tol
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


M = e2.cargar_motor()
COL_PAIS, COL_CAIDAS = e2.columnas_keepa()

# ═══════════════════════════════════════════════════════════════════════════════
print('(A) las piezas salen del fichero del escaner viejo')
_arbol = ast.parse(io.open(e2.RUTA_MOTOR, encoding='utf-8').read())
_lineas = {n.name: n.lineno for n in _arbol.body if isinstance(n, ast.FunctionDef)}
for _nombre in e2.DEFS_MOTOR:
    _f = getattr(M, _nombre)
    eq('(A) %-22s viene de %s, linea %s' % (_nombre, e2.RUTA_MOTOR, _lineas.get(_nombre)),
       (_f.__code__.co_filename, _f.__code__.co_firstlineno), (e2.RUTA_MOTOR, _lineas.get(_nombre)))
eq('(A) las 6 unidades de la caja se LEEN del viejo (UNIDADES_CASE_TCG)', M.UNIDADES_CASE_TCG, 6)
eq('(A) el perfil HEO del viejo divide por caja', M.PERFILES['HEO'].get('precio_caja6'), 'caja')

_tmp = tempfile.mkdtemp(prefix='e2_')
_roto = os.path.join(_tmp, 'motor_roto.py')
_src = io.open(e2.RUTA_MOTOR, encoding='utf-8').read()
io.open(_roto, 'w', encoding='utf-8').write(_src.replace('def calc_rentabilidad(', 'def calc_rentabilidad_v2(', 1))
try:
    e2.cargar_motor(_roto)
    _msg = 'arranco'
except e2.PiezaNoEncontrada as ex:
    _msg = str(ex)
eq('(A) 🔴 sin calc_rentabilidad en el viejo, el nuevo NO arranca (y dice cual falta)',
   'calc_rentabilidad' in _msg and 'ya no tiene' in _msg, True)
io.open(_roto, 'w', encoding='utf-8').write(_src + '\nALMACEN = 0.5\n')
try:
    e2.cargar_motor(_roto)
    _msg = 'arranco'
except e2.PiezaNoEncontrada as ex:
    _msg = str(ex)
eq('(A) 🔴 con ALMACEN asignado dos veces, NO arranca (no se sabe cual manda)',
   'ALMACEN' in _msg and 'mas de una vez' in _msg, True)
eq('(A) la tanda del Visualizador se lee de descargar_heo.py', e2.tanda_visualizador(), 10000)
eq('(A) las cabeceras que el Pro no lee, de TIPADAS del escaparate',
   (COL_PAIS, COL_CAIDAS), ('Localización', 'Clasificación de Ventas: Descensos en los últimos 30 días'))

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(B) la formula, con los casos que el viejo se exige al arrancar')
_r = M.calc_rentabilidad(15.99, 8.12, 15, 3.51, 0.21)
casi('(B) caso canonico: beneficio -1,04', _r['beneficio'], -1.04, 0.01)
casi('(B) caso canonico: comision Amazon 2,47', _r['com_amazon'], 2.47, 0.01)
# Pedido 404-7912092-2024339 (FR): comision 1,82 + FBA 5,29 → ISD cobrado 0,21.
_precio_fr = 1.82 / 0.15
_fr = e2.calcular_pais('FR', {'asin': 'B0TESTFR01', 'buybox': _precio_fr, 'es_fba': True, 'compct': 15.0,
                              'fba': 5.29}, 5.0, '8435507873345', M)
casi('(B) FR: el recargo ISD va sobre comision + tarifa FBA (0,21 de la factura)',
     _fr['com_amazon'] - 1.82, 0.21, 0.005)
_es = e2.calcular_pais('ES', {'asin': 'B0TESTES01', 'buybox': _precio_fr, 'es_fba': True, 'compct': 15.0,
                              'fba': 5.29}, 5.0, '8435507873345', M)
casi('(B) ES: el recargo va solo sobre la comision (3 %)', _es['com_amazon'] - 1.82, 1.82 * 0.03, 0.0001)
eq('(B) margen 10 % → COMPRAR', M.decision_de(0.10), 'COMPRAR')
eq('(B) margen 9,99 % → VALORAR', M.decision_de(0.0999), 'VALORAR')
eq('(B) margen 1 % → VALORAR', M.decision_de(0.01), 'VALORAR')
eq('(B) margen 0,99 % → NO COMPRAR', M.decision_de(0.0099), 'NO COMPRAR')
eq('(B) sin margen → Sin datos', M.decision_de(None), 'Sin datos')

# ═══════════════════════════════════════════════════════════════════════════════
# Datos de mentira comunes: EAN validos, un catalogo HEO y dos CSV (ES y DE)
# ═══════════════════════════════════════════════════════════════════════════════
def ean(n):
    cuerpo = '84355%07d' % n
    return cuerpo + M._chk13(cuerpo)


C = pro.CSV_COLS
CABECERA = ['ASIN', COL_PAIS, 'Título', 'Marca', C['ean'], C['rank'], C['rank90'], COL_CAIDAS,
            C['buybox'], C['es_fba'], 'Caja de Compra: Gastos de envío', C['nuevo'], C['fba'],
            C['compct'], C['nof'], C['vendidos'], C['vendidos2'], C['nvar'], 'URL: Slug de URL']


def fila_csv(pais, asin, eans, titulo, rank='15000', rank90='18000', caidas='20', bb='20.00',
             es_fba='yes', nuevo='19.50', fba='3.50', com='15.01 %'):
    return {'ASIN': asin, COL_PAIS: pais, 'Título': titulo, 'Marca': 'Funko', C['ean']: eans,
            C['rank']: rank, C['rank90']: rank90, COL_CAIDAS: caidas, C['buybox']: bb, C['es_fba']: es_fba,
            'Caja de Compra: Gastos de envío': '', C['nuevo']: nuevo, C['fba']: fba, C['compct']: com,
            C['nof']: '12', C['vendidos']: '50', C['vendidos2']: '', C['nvar']: '0', 'URL: Slug de URL': ''}


def escribir_csv(ruta, filas, cabecera=CABECERA):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cabecera, extrasaction='ignore')
    w.writeheader()
    for f in filas:
        w.writerow(f)
    io.open(ruta, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())
    return ruta


GTIN14 = '1' + ean(12)[:12]                 # codigo de CAJA de 14 cifras (checksum GTIN-14)
GTIN14 = GTIN14 + M._chk13(GTIN14[1:13])[:0]  # se completa abajo con su digito de control GTIN-14


def _dc14(s13):
    d = [int(x) for x in s13][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10)


GTIN14 = GTIN14[:13] + _dc14(GTIN14[:13])
# 🔑 EL RESCATE DEL VIEJO ES PARA EL GTIN-14 TRUNCADO A 13 CIFRAS (`variantes_ean`): el de 14
#    cifras enteras lo tira antes la Celda 4 como «EAN forma rara» (len 14), y el nuevo igual.
TRUNCADO13 = GTIN14[:13]
EAN_RESCATADO = TRUNCADO13[1:13] + M._chk13(TRUNCADO13[1:13])


def heo(n, nombre, precio, marca='FUNKO', estado='disponible', oferta='', e=None):
    return {'productNumber': 'HEO%04d' % n, 'ean': e or ean(n), 'nombre': nombre, 'marca': marca,
            'categoria': 'Figuras', 'precio': precio, 'precio_base': precio, 'en_oferta': oferta,
            'campana': '', 'estado': estado, 'disponibilidad': 'GREEN', 'imagen': '',
            'fin_de_vida': '', 'preorder': ''}


FILAS_HEO = [
    heo(1, 'Funko Pop Alfa', 8.00),                       # f: COMPRAR (ES 10 % de IVA de ficha)
    heo(2, 'Funko Pop Beta', 10.00),                      # e: VALORAR (margen ~5 % en ES)
    heo(3, 'Funko Pop Gamma', 25.00),                     # d: sin margen
    heo(4, 'Funko Pop Delta', 8.00),                      # d: sin datos (sin precio en el CSV)
    heo(5, 'Funko Pop Epsilon', 8.00),                    # c: pocas caidas
    heo(6, 'Funko Pop Zeta', 8.00),                       # c: sin dato de caidas
    heo(7, 'Funko Pop Eta', 8.00),                        # a: no aparece
    heo(8, 'Funko Pop Theta', 8.00),                      # a: sin ASIN
    heo(9, 'Funko Pop Iota', 8.00),                       # b: ES y DE dan fichas distintas
    heo(10, 'Ultimate Guard Fundas', 3.00, marca='Ultimate Guard'),   # b: dos fichas en ES
    heo(11, 'Funko Pop Kappa 5+1', 60.00),                # caja de 6 → 10 €/ud
    heo(12, 'Funko Pop Lambda caja', 8.00, e=TRUNCADO13), # GTIN-14 truncado: se rescata el EAN-13
    heo(13, 'Funko Pop Mu', 8.00),                        # se vende en DE (no en ES): mejor pais ES
    heo(14, 'Hasbro Nerf Oferta', 5.00, marca='Hasbro', oferta='SI'),   # entra por OFERTAS
    heo(15, 'Hasbro Nerf', 5.00, marca='Hasbro'),         # fuera: ni marca ni oferta
    heo(16, 'Funko Pop Agotado', 8.00, estado='agotado'), # fuera: no disponible
    heo(17, 'Funko Pop Nu Chase', 30.00),                 # chase SUELTO → apartado
    heo(18, 'Funko Pop Raro', 8.00, e='12345'),           # EAN de forma rara → apartado
    heo(19, 'Funko Pop Alfa (otra fila)', 9.50, e=ean(1)),   # duplicado: se queda la de 8,00
    heo(20, 'Funko Pop Codigo de caja', 8.00, e=GTIN14),  # GTIN-14 entero (14 cifras) → apartado, como el viejo
]
CHASE_HEO = [{'producto_heo': 'HEO9001', 'nombre': 'Funko Pop Omega w/CH Surtido (6)', 'ean_caja': '9990000000011',
              'marca': 'FUNKO', 'precio_caja': 70.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''}]
REGLA = {'proveedor': 'HEO', 'activo': True, 'marcas': ['Funko', 'Ultimate Guard', 'OFERTAS'], 'rank_maximo': 30000}

CSV_ES = [
    fila_csv('es', 'B0ALFA0001', ean(1), 'Funko Pop Alfa figura', bb='22.00', fba='3.50', caidas='30'),
    fila_csv('es', 'B0BETA0001', ean(2), 'Funko Pop Beta', bb='22.00', fba='3.50', caidas='12'),
    fila_csv('es', 'B0GAMA0001', ean(3), 'Funko Pop Gamma', bb='20.00', caidas='40'),
    fila_csv('es', 'B0DELT0001', ean(4), 'Funko Pop Delta', bb='', nuevo='', caidas='25'),
    fila_csv('es', 'B0EPSI0001', ean(5), 'Funko Pop Epsilon', caidas='5'),
    fila_csv('es', 'B0ZETA0001', ean(6), 'Funko Pop Zeta', caidas=''),
    fila_csv('es', '', ean(8), 'Funko Pop Theta'),
    fila_csv('es', 'B0IOTA0001', ean(9), 'Funko Pop Iota'),
    fila_csv('es', 'B0FUND0100', '0' + ean(10), 'Fundas 100'),
    fila_csv('es', 'B0FUND0200', ean(10) + ', ' + ean(99), 'Fundas 200'),
    fila_csv('es', 'B0KAPA0001', ean(11), 'Funko Pop Kappa', bb='26.00', caidas='15'),
    fila_csv('es', 'B0LAMB0001', EAN_RESCATADO, 'Funko Pop Lambda', bb='24.00', caidas='15'),
    fila_csv('es', 'B0MUMU0001', ean(13), 'Funko Pop Mu', bb='24.00', caidas='2', rank='45000', rank90='50000'),
    fila_csv('es', 'B0NERF0001', ean(14), 'Nerf', bb='20.00', caidas='50'),
]
CSV_DE = [
    fila_csv('de', 'B0ALFA0001', ean(1), 'Funko Pop Alfa figur', bb='21.00', caidas='12'),
    fila_csv('de', 'B0EPSI0001', ean(5), 'Funko Pop Epsilon', caidas='3'),
    fila_csv('de', 'B0ZETA0001', ean(6), 'Funko Pop Zeta', caidas='-'),
    fila_csv('de', 'B0IOTA0002', ean(9), 'Funko Pop Iota DE', caidas='30'),
    fila_csv('de', 'B0MUMU0001', ean(13), 'Funko Pop Mu', bb='18.00', caidas='15'),
]
RUTA_ES = escribir_csv(os.path.join(_tmp, 'KeepaExport-2026-09-24-VisualizadorDeProductos.csv'), CSV_ES)
RUTA_DE = escribir_csv(os.path.join(_tmp, 'KeepaExport-2026-09-24-VisualizadorDeProductos (1).csv'), CSV_DE)

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(C) el lector de CSV: el pais sale del dato, las caidas se leen')
_ex_es = e2.examinar_csv(RUTA_ES, pro, COL_PAIS, COL_CAIDAS)
_ex_de = e2.examinar_csv(RUTA_DE, pro, COL_PAIS, COL_CAIDAS)
eq('(C) el export de amazon.es dice ES (columna Localización)', (_ex_es['pais'], _ex_es['fuente_pais']), ('ES', COL_PAIS))
eq('(C) el de amazon.de dice DE, aunque el nombre del fichero no lo diga', _ex_de['pais'], 'DE')
eq('(C) filas leidas', (_ex_es['filas'], _ex_de['filas']), (len(CSV_ES), len(CSV_DE)))
eq('(C) caidas: numero', _ex_es['caidas']['B0ALFA0001'], 30.0)
eq('(C) caidas: celda vacia → sin dato (None), no cero', _ex_es['caidas']['B0ZETA0001'], None)
eq('(C) caidas: «-» de Keepa → sin dato (None)', _ex_de['caidas']['B0ZETA0001'], None)
_datos_es = pro.leer_csv_visualizador(RUTA_ES)
eq('(C) el lector del Pro indexa por EAN sin ceros y guarda las fichas del EAN compartido',
   sorted(r['asin'] for r in _datos_es[M.norm(ean(10))]), ['B0FUND0100', 'B0FUND0200'])
eq('(C) …y lee «15.01 %» como 15,01', _datos_es[M.norm(ean(1))][0]['compct'], 15.01)

_mezcla = escribir_csv(os.path.join(_tmp, 'mezcla.csv'), CSV_ES[:2] + CSV_DE[:1])
try:
    e2.examinar_csv(_mezcla, pro, COL_PAIS, COL_CAIDAS)
    _msg = 'paso'
except e2.CsvIlegible as ex:
    _msg = str(ex)
eq('(C) 🔴 un fichero con ES y DE mezclados se RECHAZA', 'mezcla países' in _msg, True)
_sin_caidas = escribir_csv(os.path.join(_tmp, 'sin_caidas.csv'), CSV_ES, [c for c in CABECERA if c != COL_CAIDAS])
try:
    e2.examinar_csv(_sin_caidas, pro, COL_PAIS, COL_CAIDAS)
    _msg = 'paso'
except e2.CsvIlegible as ex:
    _msg = str(ex)
eq('(C) 🔴 sin la columna de caidas se RECHAZA nombrandola (no se inventa un sustituto)',
   COL_CAIDAS in _msg, True)
_hueco = [dict(CSV_ES[0]), dict(CSV_ES[1], **{COL_PAIS: ''})]
try:
    e2.examinar_csv(escribir_csv(os.path.join(_tmp, 'hueco.csv'), _hueco), pro, COL_PAIS, COL_CAIDAS)
    _msg = 'paso'
except e2.CsvIlegible as ex:
    _msg = str(ex)
eq('(C) 🔴 una fila sin Localización se rechaza (es la unica fuente de pais)', 'vacía' in _msg, True)
_cab_url = [c for c in CABECERA if c != COL_PAIS] + ['URL: Amazon']
_url = [dict(f, **{'URL: Amazon': 'https://www.amazon.de/dp/%s' % (f['ASIN'] or 'B000000000')}) for f in CSV_DE]
_ex_url = e2.examinar_csv(escribir_csv(os.path.join(_tmp, 'url.csv'), _url, _cab_url), pro, COL_PAIS, COL_CAIDAS)
eq('(C) sin Localización, el pais sale del dominio de la URL de Amazon', (_ex_url['pais'], _ex_url['fuente_pais']),
   ('DE', 'URL de Amazon'))

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(D) precio de venta, comision y tarifa: como el Escaner Pro, cotejado ejecutandolo')
_cat = os.path.join(_tmp, 'heo.csv')
with io.open(_cat, 'w', encoding='utf-8', newline='') as fh:
    _w = csv.writer(fh, delimiter=';')
    _w.writerow(['ean', 'nombre', 'marca', 'precio', 'estado'])
    for _h in FILAS_HEO[:14]:
        _w.writerow([_h['ean'], _h['nombre'], _h['marca'], _h['precio'], _h['estado']])
_res_pro = pro.escanear_pro('HEO', 'TODAS', _cat, {'ES': RUTA_ES}, rank_maximo=30000)
_n_cotejadas = 0
for _reg in _res_pro['registros']:
    _dpro = _reg['paises'].get('ES') or {}
    _rec = next(r for r in _datos_es[M.norm(_reg['ean'])] if r['asin'] == _reg['asin'])
    _mio = e2.calcular_pais('ES', _rec, 8.0, M.core_ean(_reg['ean']), M)
    if (_mio['precio_venta'], _mio['ref_pct'], _mio['fee_fba']) != (_dpro.get('precio'), _dpro.get('ref_pct'), _dpro.get('fee')):
        fallos.append('(D) %s' % _reg['ean'])
        print('XX (D) %s: nuevo %r / Pro %r' % (_reg['ean'], (_mio['precio_venta'], _mio['ref_pct'], _mio['fee_fba']),
                                                (_dpro.get('precio'), _dpro.get('ref_pct'), _dpro.get('fee'))))
    _n_cotejadas += 1
eq('(D) precio, comision y tarifa FBA identicos a los del Pro en las %d fichas que el Pro calcula' % _n_cotejadas,
   _n_cotejadas >= 8 and not [f for f in fallos if f.startswith('(D)')], True)

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(E) la foto: filtro del director, chase, caja, EAN raro, duplicado y GTIN')
QUIERE, _info = e2.cargar_filtro_director(REGLA)
eq('(E) el filtro sale de director_heo_prep.py con las marcas de la regla',
   (_info['marcas_reales'], _info['quiere_ofertas']), (['Funko', 'Ultimate Guard'], True))
# El catalogo CRUDO de la escena: las 20 filas con GTIN + el Funko chase + 3 sin GTIN = 24.
FOTO, APARTADOS, CUENTAS = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=24, n_sin_gtin=3, n_declarado=24)
_por_ean = {f['ean_original']: f for f in FOTO}
eq('(E) en la foto: los 13 de la escena + la oferta de Hasbro, sin el agotado ni el de otra marca',
   sorted(f['producto_heo'] for f in FOTO),
   sorted(['HEO%04d' % n for n in range(1, 15)]))
# (B2) La marca fuera (el Hasbro sin oferta) se LISTA desde el encargo B2; antes solo se contaba.
#      La caja con chase de la escena (HEO9001, codigo 999… que no es EAN y numero que no es FK) no
#      tiene EAN de figura posible: sigue en su puerta previa.
eq('(E) apartados (las listas de las puertas previas), cada uno con su motivo', sorted(a['motivo'] for a in APARTADOS),
   sorted(['chase_funko', 'marca_fuera', 'chase_suelto', 'ean_forma_rara', 'ean_forma_rara', 'duplicado_proveedor']))
eq('(E) el GTIN-14 de 14 cifras se aparta como EAN de forma rara (len=14), igual que en el viejo, y lo dice',
   [a['detalle'] for a in APARTADOS if a['ean_original'] == GTIN14],
   ['EAN forma rara (len=14): GTIN-14, el escáner viejo lo rechaza antes del rescate'])
eq('(E) 🔴 PUERTAS PREVIAS: cada producto crudo, en UNA', CUENTAS['previas'],
   {'chase_funko': 1, 'sin_gtin': 3, 'no_disponible': 1, 'marca_fuera': 1, 'estado_no_servible': 0,
    'chase_suelto': 1, 'ean_forma_rara': 2, 'duplicado_proveedor': 1})
eq('(E) 🔴 crudo 24 = previas 10 + foto 14 → cuadra', (CUENTAS['n_previas'], CUENTAS['n_foto'], CUENTAS['cuadra_previo']),
   (10, 14, True))
eq('(E) las puertas previas son las de la migración, en su orden',
   list(e2.PUERTAS_PREVIAS), ['chase_funko', 'sin_gtin', 'no_disponible', 'marca_fuera', 'estado_no_servible',
                              'chase_suelto', 'ean_forma_rara', 'duplicado_proveedor'])
# Una caja con chase AGOTADA tambien se cuenta: desde el B2, como «no disponible» (antes, Funko chase).
_chase2 = CHASE_HEO + [dict(CHASE_HEO[0], producto_heo='HEO9002', estado='agotado')]
_, _, _c2 = e2.construir_foto(FILAS_HEO, _chase2, QUIERE, M, n_crudo=25, n_sin_gtin=3, n_declarado=25)
eq('(E) 🔴 la caja con chase que no pasa el filtro también se cuenta: agotada → no disponible (B2)',
   (_c2['previas']['chase_funko'], _c2['previas']['no_disponible'], _c2['cuadra_previo']), (1, 2, True))
# Los rojos: el cuadre previo no puede salir verde por las malas.
_, _, _r = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=24, n_sin_gtin=None, n_declarado=24)
eq('(E) 🔴 sin el recuento de sin GTIN (log ilegible) → NO cuadra, y dice cuál falta',
   (_r['cuadra_previo'], _r['motivo_previo']), (False, 'sin recuento de: sin_gtin'))
_, _, _r = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=None, n_sin_gtin=3, n_declarado=24)
eq('(E) 🔴 sin el crudo → NO cuadra', (_r['cuadra_previo'], _r['motivo_previo']), (False, 'sin recuento de: crudo'))
_, _, _r = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=25, n_sin_gtin=3, n_declarado=25)
eq('(E) 🔴 HEO dio uno más de los que salen de descargar_heo → NO cuadra', _r['cuadra_previo'], False)
_, _, _r = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=24, n_sin_gtin=3, n_declarado=None)
eq('(E) 🔴 sin el total que DECLARA HEO → NO cuadra (no se puede saber si la descarga vino entera)',
   (_r['cuadra_previo'], _r['motivo_previo']), (False, 'sin recuento de: total que declara HEO'))
_, _, _r = e2.construir_foto(FILAS_HEO, CHASE_HEO, QUIERE, M, n_crudo=24, n_sin_gtin=3, n_declarado=30)
eq('(E) 🔴 HEO dice 30 y se bajaron 24 (una página falló en silencio) → NO cuadra',
   (_r['cuadra_previo'], _r['motivo_previo']), (False, 'HEO dice que tiene 30 productos y se bajaron 24: la descarga se cortó'))
_r = e2.cuadre_previo(dict(CUENTAS, n_foto=13))
eq('(E) 🔴 un producto que se pierde entre las previas y la foto → NO cuadra',
   (_r['cuadra_previo'], _r['motivo_previo']), (False, 'catálogo crudo 24 ≠ puertas previas 10 + foto 13'))
eq('(E) duplicado: se queda la MAS BARATA (8,00, no 9,50)', _por_ean[ean(1)]['precio_unidad'], 8.0)
_k = _por_ean[ean(11)]
eq('(E) la caja 5+1: es caja, de 6, precio por unidad 60/6 = 10', (_k['es_caja'], _k['uds_caja'], _k['precio_unidad']),
   (True, 6, 10.0))
eq('(E) …y el precio del catalogo se guarda tal cual (60)', _k['precio_catalogo'], 60.0)
eq('(E) GTIN-14 truncado: a Keepa van el codigo tal cual Y el EAN-13 rescatado', _por_ean[TRUNCADO13]['codigos_keepa'],
   [TRUNCADO13, EAN_RESCATADO])
_lista = e2.lista_para_keepa(FOTO)
eq('(E) la lista para el Visualizador: sin repetidos, uno por codigo', len(_lista), len(set(_lista)))
eq('(E) tandas: 25.000 codigos en tandas de 10.000 son 3', [len(t) for t in e2.partir_en_tandas(list(range(25000)), 10000)],
   [10000, 10000, 5000])

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(F) las seis puertas')
M.poner_catalogo_propio([{'ean': ean(1), 'iva_pct': 0.10, 'stock_moloka': 0, 'stock_fba': 0}])
_datos = {'ES': pro.leer_csv_visualizador(RUTA_ES), 'DE': pro.leer_csv_visualizador(RUTA_DE)}
_caidas = {'ES': _ex_es['caidas'], 'DE': _ex_de['caidas']}
# Las DOS listas (Fernando, 24-sep-2026): el filtro de ventas mira ES y DE; se calcula en los cuatro.
PARAMS = {'umbral': 8, 'paises_filtro': ['ES', 'DE'], 'paises_calculo': ['ES', 'IT', 'FR', 'DE']}
RES = {}
for _f in FOTO:
    _f['id'] = _f['producto_heo']
    RES[_f['producto_heo']] = e2.decidir(_f, {p: e2.candidatos(_f, _datos[p]) for p in ('ES', 'DE')}, _caidas, PARAMS, M)


def puerta(n):
    r = RES['HEO%04d' % n]
    return r['puerta'], r['motivo']


eq('(F) f · COMPRAR', puerta(1), ('f', 'f_comprar'))
eq('(F) f · el mejor pais es el de MAS margen (ES, IVA de ficha 10 %)', RES['HEO0001']['mejor']['pais'], 'ES')
eq('(F) f · la fila dice de donde sale el IVA: ES de la ficha, DE el general',
   (RES['HEO0001']['paises']['ES']['iva_origen'], RES['HEO0001']['paises']['DE']['iva_origen']),
   ('ficha', 'general DE 19%'))
eq('(F) …y sin ficha, «asumido 21%»', RES['HEO0002']['paises']['ES']['iva_origen'], 'asumido 21%')
eq('(F) e · VALORAR', puerta(2), ('e', 'e_valorar'))
eq('(F) d · se vende sin margen', puerta(3), ('d', 'd_sin_margen'))
eq('(F) d · se vende pero el CSV no trae precio', puerta(4), ('d', 'd_sin_datos'))
eq('(F) c · ≤ 8 caidas en ES y en DE', puerta(5), ('c', 'c_pocas_caidas'))
eq('(F) c · …con el texto del encargo', RES['HEO0005']['detalle'], '≤ 8 caídas en ES y en DE')
eq('(F) c · sin dato de caidas (vacio en ES, «-» en DE)', puerta(6), ('c', 'c_sin_dato'))
eq('(F) a · no aparece en ningun CSV', puerta(7), ('a', 'a_no_aparece'))
eq('(F) a · aparece sin ASIN', puerta(8), ('a', 'a_sin_asin'))
eq('(F) b · ES y DE dan fichas DISTINTAS para el mismo EAN', puerta(9), ('b', 'b_varias_fichas'))
eq('(F) b · …y no se calcula nada: se listan las dos', ([x['asin'] for x in RES['HEO0009']['fichas']], RES['HEO0009']['paises']),
   (['B0IOTA0001', 'B0IOTA0002'], {}))
eq('(F) b · dos fichas en ES para el mismo EAN (el caso de las fundas)', puerta(10), ('b', 'b_varias_fichas'))
eq('(F) la caja 5+1 se calcula con 10 €/ud', RES['HEO0011']['paises']['ES']['pa'], 10.0)
eq('(F) el GTIN-14 casa con Keepa por su EAN-13 rescatado', RES['HEO0012']['asin'], 'B0LAMB0001')
eq('(F) se vende SOLO en DE (15 caidas) y aun asi el mejor pais puede ser ES',
   (puerta(13), RES['HEO0013']['mejor']['pais'], RES['HEO0013']['caidas']), (('f', 'f_comprar'), 'ES', {'ES': 2.0, 'DE': 15.0}))
eq('(F) la oferta de Hasbro solo tiene ES: DE sin dato, sin calculo', (puerta(14)[0], sorted(RES['HEO0014']['paises'])),
   ('f', ['ES']))
_solo_es = e2.decidir(FOTO[4], {'ES': e2.candidatos(FOTO[4], _datos['ES'])}, _caidas, PARAMS, M)
eq('(F) c · con solo el CSV de ES, el motivo dice que DE no tiene dato', _solo_es['detalle'],
   '≤ 8 caídas en ES (DE: sin dato)')
_umbral_bajo = e2.decidir(FOTO[4], {p: e2.candidatos(FOTO[4], _datos[p]) for p in ('ES', 'DE')}, _caidas,
                          dict(PARAMS, umbral=4), M)
eq('(F) el umbral es un PARAMETRO: con 4, 5 caidas en ES ya se vende', _umbral_bajo['puerta'] in ('d', 'e', 'f'), True)

# 🔴 EL CASO DE FERNANDO: 20 caidas en ES, 0 en DE y MAS margen en DE → COMPRAR con mejor pais DE,
#    y DE marcado «no vende aqui». Mas IT (5 caidas) y FR (sin dato): se calculan y se marcan.
_tres = {
    'ES': escribir_csv(os.path.join(_tmp, 'es4.csv'), [fila_csv('es', 'B0ALFA0001', ean(1), 'Alfa', bb='22.00', caidas='20')]),
    'DE': escribir_csv(os.path.join(_tmp, 'de4.csv'), [fila_csv('de', 'B0ALFA0001', ean(1), 'Alfa', bb='40.00', caidas='0')]),
    'IT': escribir_csv(os.path.join(_tmp, 'it4.csv'), [fila_csv('it', 'B0ALFA0001', ean(1), 'Alfa', bb='30.00', caidas='5')]),
    'FR': escribir_csv(os.path.join(_tmp, 'fr4.csv'), [fila_csv('fr', 'B0ALFA0001', ean(1), 'Alfa', bb='30.00', caidas='')]),
}
_d4 = {p: pro.leer_csv_visualizador(r) for p, r in _tres.items()}
_c4 = {p: e2.examinar_csv(r, pro, COL_PAIS, COL_CAIDAS)['caidas'] for p, r in _tres.items()}
_alfa = FOTO[[f['producto_heo'] for f in FOTO].index('HEO0001')]
_r4 = e2.decidir(_alfa, {p: e2.candidatos(_alfa, _d4[p]) for p in _d4}, _c4, PARAMS, M)
eq('(F) 🔴 20 caídas en ES, 0 en DE y más margen en DE → COMPRAR con mejor país DE',
   (_r4['puerta'], _r4['mejor']['pais']), ('f', 'DE'))
eq('(F) 🔴 …y DE lleva «no vende aquí»; ES vende; IT (5) y FR (sin dato) tampoco venden, pero se calculan',
   {p: (c['vende_aqui'], c['decision'] is not None) for p, c in _r4['paises'].items()},
   {'ES': (True, True), 'IT': (False, True), 'FR': (False, True), 'DE': (False, True)})
eq('(F) 🔴 los cuatro países, en el orden de los parámetros', list(_r4['paises']), ['ES', 'IT', 'FR', 'DE'])
eq('(F) 🔴 IT con 50 caídas NO hace que se venda: el filtro es solo ES y DE',
   e2.decidir(_alfa, {p: e2.candidatos(_alfa, _d4[p]) for p in ('IT', 'DE')},
              dict(_c4, IT={'B0ALFA0001': 50.0}), PARAMS, M)['puerta'], 'c')

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(G) el cuadre: entradas = suma de puertas, y cada EAN por UNA sola')
_ids = [f['id'] for f in FOTO]
_resultados = [dict(RES[i], foto_id=i) for i in _ids]
_cq = e2.cuadre(_ids, _resultados)
eq('(G) la escena cuadra: %d entradas = %d en puertas' % (len(_ids), _cq['suma']), _cq['cuadra'], True)
eq('(G) …y el reparto por puertas es el de la escena', _cq['conteo'], {'a': 2, 'b': 2, 'c': 2, 'd': 2, 'e': 1, 'f': 5})
eq('(G) …con los dos motivos de la c contados', (_cq['n_c_pocas'], _cq['n_c_sin_dato']), (1, 1))
_menos = e2.cuadre(_ids, _resultados[:-1])
eq('(G) 🔴 una entrada sin puerta → NO CUADRA (entradas ≠ suma de puertas)',
   (_menos['cuadra'], _menos['n_entradas'] != _menos['suma'], _menos['faltan']), (False, True, [_ids[-1]]))
_doble = e2.cuadre(_ids, _resultados + [_resultados[0]])
eq('(G) 🔴 un EAN por DOS puertas → NO CUADRA', (_doble['cuadra'], _doble['repetidos']), (False, [_ids[0]]))
_intruso = e2.cuadre(_ids, _resultados[:-1] + [dict(_resultados[-1], foto_id='intruso')])
eq('(G) 🔴 la suma sale igual pero hay una salida que no es de la foto → NO CUADRA',
   (_intruso['cuadra'], _intruso['suma'] == _intruso['n_entradas'], _intruso['sobran']), (False, True, ['intruso']))
_rara = e2.cuadre(_ids, _resultados[:-1] + [dict(_resultados[-1], puerta='z')])
eq('(G) 🔴 una puerta que no es de las seis → NO CUADRA', _rara['cuadra'], False)

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(H) la comparacion con el viejo')
_cols_viejo = e2.sacar_piezas(e2.RUTA_MOTOR, (), ('COLS',))['COLS']


def excel_viejo(filas):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Análisis'
    ws.append(_cols_viejo)
    for e, pais, dec in filas:
        fila = [None] * len(_cols_viejo)
        fila[_cols_viejo.index('Nombre')] = 'Producto %s' % e[-4:]
        fila[_cols_viejo.index('EAN')] = e
        fila[_cols_viejo.index('País')] = pais
        fila[_cols_viejo.index('Decisión')] = dec
        fila[_cols_viejo.index('Margen')] = '=R2/J2'      # en el viejo es una formula viva
        ws.append(fila)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


_completo = excel_viejo([(ean(1), p, 'COMPRAR') for p in ('ES', 'IT', 'FR', 'DE')]
                        + [(ean(5), 'ES', 'COMPRAR'), (ean(5), 'DE', 'NO COMPRAR')]
                        + [(ean(3), 'ES', 'NO COMPRAR'), (ean(3), 'IT', 'VALORAR')]
                        + [(ean(2), 'ES', 'NO COMPRAR')]
                        + [(ean(7), 'ES', 'COMPRAR')]
                        + [(ean(6), 'ES', 'COMPRAR')]
                        + [(ean(14), 'ES', 'COMPRAR')]
                        + [('9990000000011', 'ES', 'COMPRAR')])
_novedad = excel_viejo([(ean(14), 'ES', 'NO COMPRAR')])
_leido = e2.leer_excel_viejo(_completo, M)
eq('(H) el Excel viejo se lee por NOMBRE de columna (aunque Margen sea formula)',
   _leido[M.norm(ean(1))]['decisiones'], {'ES': 'COMPRAR', 'IT': 'COMPRAR', 'FR': 'COMPRAR', 'DE': 'COMPRAR'})
eq('(H) la fecha del viejo sale del nombre del Excel (UTC del runner)',
   e2.fecha_del_excel_viejo('resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx'),
   datetime(2026, 9, 23, 20, 6, tzinfo=timezone.utc))
_filas_bib = [{'fichero': 'resultados/Escaneo_HEO_TODAS_20260924_1135.xlsx', 'modo': 'nuevos'},
              {'fichero': None, 'modo': 'nuevos'},
              {'fichero': 'resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx', 'modo': 'todo'},
              {'fichero': 'resultados/Escaneo_HEO_TODAS_20260923_1335.xlsx', 'modo': 'nuevos'}]
_elegidas, _hay = e2.elegir_excels_viejos(_filas_bib)
eq('(H) se comparan el ULTIMO completo y las novedades POSTERIORES, no las anteriores',
   ([f['fichero'][-18:] for f in _elegidas], _hay), (['20260924_1135.xlsx', '20260923_2006.xlsx'], True))
_viejo = e2.fusionar_viejos([
    ({'fichero': 'resultados/Escaneo_HEO_TODAS_20260924_1135.xlsx', 'fecha': datetime(2026, 9, 24, 11, 35, tzinfo=timezone.utc), 'modo': 'nuevos'},
     e2.leer_excel_viejo(_novedad, M)),
    ({'fichero': 'resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx', 'fecha': datetime(2026, 9, 23, 20, 6, tzinfo=timezone.utc), 'modo': 'todo'},
     _leido)])
eq('(H) la novedad POSTERIOR manda sobre el completo', _viejo[M.norm(ean(14))]['decisiones'], {'ES': 'NO COMPRAR'})
_nuevo = e2.nuevo_por_ean(FOTO, RES, M)
_apart = {M.norm(M.core_ean(a['ean_original'])): 'apartado antes de la foto: ' + a['detalle'] for a in APARTADOS}
CMP = {c['ean_norm']: c for c in e2.comparar(_viejo, _nuevo, {'umbral': 8, 'paises': ['ES', 'DE'], 'paises_filtro': ['ES', 'DE'], 'rank_max': 30000,
                                                              'apartados': _apart, 'fecha_nuevo': None}, M)}


def cmp(n):
    c = CMP.get(M.norm(ean(n)))
    return (c['categoria'], c['diferencia_criterio']) if c else None


eq('(H) COMPRAR en los dos', cmp(1), ('ambos', False))
eq('(H) solo en el viejo porque el nuevo no ve caidas → DIFERENCIA DE CRITERIO', cmp(5), ('solo_viejo', True))
eq('(H) …y la explicacion lo dice', 'caídas' in CMP[M.norm(ean(5))]['explicacion'], True)
eq('(H) solo en el viejo porque solo lo da en IT → DIFERENCIA DE CRITERIO (paises)', cmp(3), ('solo_viejo', True))
eq('(H) …y nombra el pais', 'IT' in CMP[M.norm(ean(3))]['explicacion'], True)
eq('(H) 🔴 solo en el viejo y el nuevo no tiene DATO de caídas → SIN EXPLICAR (es un hueco, no criterio)',
   cmp(6), ('solo_viejo', False))
eq('(H) solo en el viejo y el nuevo no lo encuentra en Amazon → SIN EXPLICAR (se mira)', cmp(7), ('solo_viejo', False))
eq('(H) el viejo lo evaluo NO COMPRAR y el nuevo VALORAR → SIN EXPLICAR', cmp(2), ('solo_nuevo', False))
eq('(H) el viejo no lo tiene y su puesto en ES pasa de 30.000 → DIFERENCIA DE CRITERIO', cmp(13), ('solo_nuevo', True))
eq('(H) el viejo no lo tiene y su puesto en ES SI entraba → SIN EXPLICAR', cmp(11), ('solo_nuevo', False))
_chase = CMP.get(M.norm('9990000000011'))
eq('(H) el chase de la puente: solo en el viejo, SIN EXPLICAR, y dice que se aparto',
   (_chase['categoria'], _chase['diferencia_criterio'], 'apartado' in (_chase['explicacion'] or '')), ('solo_viejo', False, True))
_rs = e2.resumen_comparacion(list(CMP.values()))
eq('(H) el resumen cuadra: criterio + sin explicar = solo en uno de los dos',
   _rs['n_cmp_criterio'] + _rs['n_cmp_sin_explicar'], _rs['n_cmp_solo_viejo'] + _rs['n_cmp_solo_nuevo'])

shutil.rmtree(_tmp, ignore_errors=True)
print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: el escaner 2 usa la formula del viejo, lee los CSV, reparte por las seis puertas, '
      'cuadra y se compara.')
