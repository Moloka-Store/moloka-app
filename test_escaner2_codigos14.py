# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO · LOS CODIGOS DE 14 CIFRAS QUE EMPIEZAN POR 0 (encargo B6, 25-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta el motor de verdad (escaner2_motor.py, con las piezas del
escaner viejo leidas de su fichero) sobre los CODIGOS REALES de la pasada ed95d086.

🔑 DESVIO DELIBERADO DEL VIEJO (Fernando, 25-sep-2026): un codigo de 14 cifras que empieza por 0 es el
   mismo EAN-13 con un cero de relleno delante; se normaliza a 13 quitando ese 0 (`core_de_heo`). El
   `ean_original` se guarda tal cual; el de 13 es el que va a Keepa y al cruce. Los de 14 que empiezan
   por 1-9 (codigo de CAJA) y los de 8 cifras NO se tocan: siguen en «forma rara».

🔑 LOS 184 CODIGOS SON REALES (casos_b6_codigos.json, volcado por script, no tecleado): los que la pasada
   ed95d086 aparto como «EAN forma rara», con su numero de HEO, marca y nombre. SIN PRECIOS: donde la
   prueba necesita uno (el duplicado, el mas barato), es redondo y lo dice.

QUE PRUEBA:
  (A) los 184: 51 de 14 cifras con 0 delante, 121 de 14 con 1-9 y 12 de 8, y su huella;
  (B) el digito de control del GTIN no cambia con ceros a la izquierda: en los 51, y en 2.000 al azar;
  (C) la foto con los 184: salen de «forma rara» los 51 (184 → 133); 49 codigos distintos entran en la
      foto con su EAN de 13 y el original de 14; los otros 2 son el MISMO codigo dos veces en HEO (dos
      surtidos de Hot Wheels) y van a «duplicado del proveedor»; y a Keepa va el de 13, nunca el de 14;
  (D) si las 13 cifras ya estan en la foto, el de 14 se junta con el por la regla de siempre (el mas
      barato se queda, el otro a «duplicado del proveedor»), en las dos direcciones;
  (E) la hoja «Descartados» del Excel del viejo: 133 filas por forma rara, no 184;
  (F) el corpus del cotejo aplica la misma regla a la marca no elegida;
  (G) 🔴 LA GUARDA MUERDE: sin la normalizacion (una copia del motor), los 51 vuelven a «forma rara»;
      y si se quitara la primera cifra a TODO codigo de 14, entrarian los 121 de caja → rojo.
"""
import io
import json
import os
import random
import sys
import tempfile
import uuid
from collections import Counter

import escaner2_motor as e2

AQUI = os.path.dirname(os.path.abspath(__file__))
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


M = e2.cargar_motor()
DATOS = json.load(io.open(os.path.join(AQUI, 'casos_b6_codigos.json'), encoding='utf-8'))
CODIGOS = DATOS['filas']


def forma(e):
    if len(e) == 14:
        return '14 con 0' if e[0] == '0' else '14 con 1-9'
    return '%d cifras' % len(e)


CERO = [f for f in CODIGOS if forma(f['ean_original']) == '14 con 0']
CAJA = [f for f in CODIGOS if forma(f['ean_original']) == '14 con 1-9']

print('(A) los 184 códigos de forma rara de ed95d086')
import hashlib  # noqa: E402
eq('(A) son 184, con la huella de la base', (len(CODIGOS), hashlib.md5(','.join(f['ean_original'] for f in CODIGOS).encode()).hexdigest()),
   (184, DATOS['origen'].rsplit(' ', 1)[-1].rstrip('.')))
eq('(A) 51 de 14 cifras con 0 delante, 121 de 14 con 1-9 y 12 de 8', Counter(forma(f['ean_original']) for f in CODIGOS),
   Counter({'14 con 0': 51, '14 con 1-9': 121, '8 cifras': 12}))
eq('(A) los 51 son de Hasbro, Mattel, Phat Mojo, ThreeZero y Wizards of the Coast', sorted({f['marca'] for f in CERO}),
   ['Hasbro', 'Mattel', 'Phat Mojo', 'ThreeZero', 'Wizards of the Coast'])

print('\n(B) el dígito de control no cambia con ceros a la izquierda')
eq('(B) en los 51: GTIN-14 válido con el 0, y EAN-13 válido sin él (los dos del viejo: _gtin14_ok y _ean_ok)',
   (sum(1 for f in CERO if M._gtin14_ok(f['ean_original'])), sum(1 for f in CERO if M._ean_ok(f['ean_original'][1:]))), (51, 51))
_azar = random.Random(20260925)
_casos = []
for _ in range(2000):
    cuerpo = ''.join(_azar.choice('0123456789') for _ in range(12))
    control = _azar.choice('0123456789')                     # válido o no, al azar
    _casos.append(cuerpo + control)
eq('(B) en 2.000 códigos de 13 al azar: «0» + código es GTIN-14 válido si y solo si el código es EAN-13 válido',
   [c for c in _casos if M._gtin14_ok('0' + c) != M._ean_ok(c)], [])
eq('(B) …y la muestra tiene de los dos (no es una comprobación que no pueda fallar)',
   (any(M._ean_ok(c) for c in _casos), any(not M._ean_ok(c) for c in _casos)), (True, True))
eq('(B) core_de_heo: 14 con 0 → 13; 14 con 1-9, 8, 13 y 12 cifras, tal cual; y el sufijo se sigue leyendo',
   [e2.core_de_heo(x, M) for x in ('00887961619805', '10887961619802', '12345678', '0887961619805', '887961619805',
                                   '00887961619805 C6')],
   ['0887961619805', '10887961619802', '12345678', '0887961619805', '887961619805', '0887961619805'])


def fila_heo(f, precio=10.0, marca=None):
    return {'productNumber': f['producto_heo'], 'ean': f['ean_original'], 'nombre': f['nombre'], 'marca': marca or f['marca'],
            'categoria': '', 'precio': precio, 'precio_base': '', 'en_oferta': '', 'campana': '', 'estado': 'disponible',
            'disponibilidad': '', 'imagen': '', 'fin_de_vida': '', 'preorder': ''}


print('\n(C) la foto con los 184 códigos reales (modo «todas»)')
QUIERE = e2.filtro_todas()[0]
FOTO, APART, CUENTAS = e2.construir_foto([fila_heo(f) for f in CODIGOS], [], QUIERE, M, n_crudo=184, n_sin_gtin=0,
                                         n_declarado=184, modo='todas')
_motivos = Counter(a['motivo'] for a in APART)
eq('(C) 🔴 «forma rara» baja de 184 a 133: los 121 de caja y los 12 de 8 cifras, ninguno de los 51',
   (_motivos['ean_forma_rara'], sorted({forma(a['ean_original']) for a in APART if a['motivo'] == 'ean_forma_rara'})),
   (133, ['14 con 1-9', '8 cifras']))
_distintos = sorted({f['ean_original'] for f in CERO})
eq('(C) entran en la foto 49: los 49 códigos distintos de los 51', (len(FOTO), sorted(f['ean_original'] for f in FOTO)),
   (49, _distintos))
eq('(C) …con el EAN de 13 (sin el 0) para buscar y cruzar, y el original de 14 guardado tal cual',
   [f for f in FOTO if not (f['ean_core'] == f['ean_original'][1:] and len(f['ean_original']) == 14 and len(f['ean_core']) == 13)], [])
_dup = [a for a in APART if a['motivo'] == 'duplicado_proveedor']
eq('(C) los otros 2 son el MISMO código dos veces en HEO (dos surtidos de Hot Wheels): duplicado del proveedor',
   sorted((a['ean_original'], a['producto_heo']) for a in _dup),
   sorted([('00194735152469', 'MATTHNR88-979P'), ('00887961619805', 'MATTFPY86-976R')]))
eq('(C) 🔴 crudo 184 = 133 forma rara + 2 duplicados + 49 en la foto → cuadra',
   (CUENTAS['n_previas'], CUENTAS['n_foto'], CUENTAS['cuadra_previo']), (135, 49, True))
_lista = e2.lista_para_keepa(FOTO)
eq('(C) a Keepa van los 49 EAN de 13 y ningún código de 14', (sorted(_lista), [c for c in _lista if len(c) == 14]),
   (sorted(f['ean_original'][1:] for f in FOTO), []))
eq('(C) …y las variantes con las que se cruza el CSV son las del EAN de 13 (sin ceros delante, como el lector)',
   all(M.norm(f['ean_original']) in f['variantes'] for f in FOTO), True)

print('\n(D) si las 13 cifras ya están, el de 14 se junta con ellas (el más barato se queda)')
_uno = CERO[0]
_trece = dict(_uno, producto_heo='HEO13', ean_original=_uno['ean_original'][1:])
for barato, precios in (('el de 14', (8.0, 10.0)), ('el de 13', (10.0, 8.0))):
    foto, apart, cu = e2.construir_foto([fila_heo(_uno, precios[0]), fila_heo(_trece, precios[1])], [], QUIERE, M,
                                        n_crudo=2, n_sin_gtin=0, n_declarado=2, modo='todas')
    queda = _uno['ean_original'] if barato == 'el de 14' else _trece['ean_original']
    va = _trece['ean_original'] if barato == 'el de 14' else _uno['ean_original']
    eq('(D) %s más barato (precios redondos): se queda él, y el otro va a duplicado del proveedor' % barato,
       ([f['ean_original'] for f in foto], [(a['motivo'], a['ean_original'], a['precio_catalogo']) for a in apart], cu['cuadra_previo']),
       ([queda], [('duplicado_proveedor', va, 10.0)], True))

print('\n(E) la hoja «Descartados» del Excel del viejo')
M.poner_catalogo_propio([])
for f in FOTO:
    f['id'] = str(uuid.uuid4())
RES = [{'foto_id': f['id'], 'id': str(uuid.uuid4()), 'puerta': 'a', 'motivo': 'a_no_aparece', 'detalle': 'No aparece en ningún CSV',
        'asin': None, 'fichas': None, 'paises': {}, 'caidas': {}, 'mejor': None} for f in FOTO]
_datos = e2.datos_como_el_viejo(FOTO, RES, APART, M)
eq('(E) sus «problematicos» (forma rara y estado no servible): 133', len(_datos['problematicos']), 133)
_wb = e2.excel_como_el_viejo(FOTO, RES, APART, M)
_ws = _wb['Descartados']
_cab = [c.value for c in _ws[1]]
_filas = [[c.value for c in fila] for fila in _ws.iter_rows(min_row=2)]
_mot = _cab.index('Motivo')
eq('(E) 🔴 en el Excel, «Descartados» lleva 133 filas por forma rara (eran 184), 49 que no aparecen y 2 duplicados',
   Counter(str(x[_mot]).split(' (')[0].split(':')[0] for x in _filas),
   Counter({'EAN forma rara': 133, 'No aparece en ningún CSV': 49, 'Duplicado del proveedor': 2}))

print('\n(F) el corpus del cotejo, con la marca no elegida')
_foto_el, _ap_el, _ = e2.construir_foto([fila_heo(f) for f in CODIGOS], [], e2.filtro_elegidas(['Nadie'], False)[0], M,
                                        n_crudo=184, n_sin_gtin=0, n_declarado=184, modo='elegidas')
_nombres, _fuera = e2.corpus_cotejo(_foto_el, _ap_el, M)
eq('(F) con ninguna marca elegida la foto queda vacía, y el corpus es el de «todas»: los mismos nombres',
   (len(_foto_el), sorted(_nombres)), (0, sorted(f['nombre'] for f in FOTO)))

print('\n(G) la guarda muerde')
with io.open(os.path.join(AQUI, 'escaner2_motor.py'), encoding='utf-8') as fh:
    TEXTO = fh.read()


def motor_con(sustituir, por):
    """Una copia del motor con un cambio, cargada como modulo aparte (el original, intacto)."""
    import importlib.util
    assert TEXTO.count(sustituir) == 1, sustituir
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as t:
        t.write(TEXTO.replace(sustituir, por))
    try:
        spec = importlib.util.spec_from_file_location('escaner2_motor_roto', t.name)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(t.name)


def forma_rara_con(mod):
    _f, ap, _c = mod.construir_foto([fila_heo(f) for f in CODIGOS], [], mod.filtro_todas()[0], M, n_crudo=184, n_sin_gtin=0,
                                    n_declarado=184, modo='todas')
    return sum(1 for a in ap if a['motivo'] == 'ean_forma_rara'), len(_f)


_ANCLA = "    if core.isdigit() and len(core) == 14 and core.startswith('0'):"
eq('(G) 🔴 sin la normalización (como el viejo): los 51 vuelven a forma rara, 184 y la foto vacía',
   forma_rara_con(motor_con(_ANCLA, "    if False:")), (184, 0))
eq('(G) 🔴 quitando la primera cifra a TODO código de 14: entrarían los 121 de caja, y no se puede',
   forma_rara_con(motor_con(_ANCLA, "    if core.isdigit() and len(core) == 14:"))[0] < 133, True)
eq('(G) con el motor sin tocar, 133 y 49 (las dos direcciones)', forma_rara_con(e2), (133, 49))

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: los 51 códigos de 14 cifras con 0 delante de ed95d086 salen de «forma rara» y se buscan con sus 13;'
      ' los de caja y los de 8 cifras siguen fuera.')
