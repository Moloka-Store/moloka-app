# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO · ELEGIR LA FICHA CUANDO UN EAN TIENE VARIAS (encargo B5, 25-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE. La regla es la del viejo, SACADA de su fichero
(moloka_escaner_nube.py: `elegir_candidato`, su cotejo de titulo y `keyrank`) y ejecutada.

🔑 LOS 13 CASOS SON REALES (casos_b5_fichas.json, volcado por script, no tecleado): los EAN de la puerta
   b del cruce 37eaa138 que el viejo daba como COMPRAR o VALORAR, con sus fichas de ES (ASIN, titulo y
   puesto medio de 90 dias) tal como las guardo el cruce, y como respuesta la ficha que puso el viejo en
   el «Análisis» de su Excel. Para el cotejo, las palabras de esos 13 nombres con en cuantos nombres del
   catalogo de la pasada (7.815) salen: es lo UNICO que el cotejo mira. Sin precios.

QUE PRUEBA:
  (A) en los 13 el nuevo elige la MISMA ficha que el viejo (y escaner_detalle, donde lo hay, dice lo mismo);
  (B) el Deck Case 100+ Black: gana por puesto B00M6XJWVM y el viejo eligio B00RLSIUBK, por el cotejo;
  (C) la hoja «Ambiguos»: lo que escribe el viejo es el ganador POR PUESTO, no el del cotejo;
  (D) 🔴 LA GUARDA MUERDE: con la regla cambiada en una copia del fichero del viejo («menor puesto» por
      «mayor», o sin el cotejo de titulo) el banco se pone rojo; y sin ficha en ES no se elige nada.
"""
import copy
import io
import json
import os
import sys
import tempfile

import escaner2_motor as e2

AQUI = os.path.dirname(os.path.abspath(__file__))
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


DATOS = json.load(io.open(os.path.join(AQUI, 'casos_b5_fichas.json'), encoding='utf-8'))
CASOS = DATOS['casos']


def con_idf(ruta=e2.RUTA_MOTOR):
    """La regla del viejo con las palabras del catalogo de la pasada ed95d086 (las medidas)."""
    from collections import Counter
    el = e2.cargar_eleccion_viejo([], ruta)
    el._ns['_DF'] = Counter(DATOS['idf']['df'])
    el._ns['_NDOC'] = DATOS['idf']['n_nombres']
    return el


def elige(el, caso):
    r = el.elegir(caso['nombre'], caso['fichas_es'])
    return r['asin'] if r else None


EL = con_idf()
print('(A) los 13 casos reales: la misma ficha que el viejo')
eq('(A) son 13, del cruce 37eaa138, todos de la puerta b', (len(CASOS), {c['puerta_37eaa138'] for c in CASOS}), (13, {'b'}))
for c in CASOS:
    r = EL.elegir(c['nombre'], c['fichas_es'])
    eq('(A) %s %s → %s (%s)' % (c['ean'], c['nombre'][:40], c['esperado'], c['excel_viejo'][-18:-5]), r['asin'], c['esperado'])
eq('(A) donde el viejo cotejó entre varias, el veredicto es el suyo («OK» en su Excel)',
   {c['ean']: EL.elegir(c['nombre'], c['fichas_es'])['veredicto'] for c in CASOS if len(c['fichas_es']) >= 2},
   {c['ean']: c['cotejo_viejo'] for c in CASOS if len(c['fichas_es']) >= 2})
eq('(A) los dos con UNA sola ficha en ES (Supernenas y Hermione): esa, como el viejo, que solo mira ES',
   [(c['ean'], EL.elegir(c['nombre'], c['fichas_es'])['veredicto']) for c in CASOS if len(c['fichas_es']) == 1],
   [('889698577755', 'única en ES'), ('889698760102', 'única en ES')])
eq('(A) contraste: escaner_detalle (2-sep o antes) dice lo mismo que el Excel en los 10 que tiene; 3 sin registro',
   ([c['ean'] for c in CASOS if c['escaner_detalle'] and c['escaner_detalle'] != c['esperado']],
    sorted(c['ean'] for c in CASOS if not c['escaner_detalle'])),
   ([], ['849803058616', '889698372480', '889698856423']))

print('\n(B) el Deck Case 100+ Black')
DECK = [c for c in CASOS if c['ean'] == '4260250075074'][0]
kr = EL._ns['keyrank']
cands = [{'asin': x['asin'], 'r_90': x['rank90']} for x in DECK['fichas_es']]
eq('(B) por PUESTO ganaría B00M6XJWVM (1.556 de puesto medio de 90 días frente a 22.137)',
   min(cands, key=kr)['asin'], 'B00M6XJWVM')
cot = {x['asin']: EL._ns['cotejar'](DECK['nombre'], x['titulo'])[0] for x in DECK['fichas_es']}
eq('(B) 🔑 pero el cotejo de título manda: solo B00RLSIUBK comparte una palabra distintiva («deck»)',
   cot, {'B00RLSIUBK': True, 'B00M6XJWVM': False})
eq('(B) …y «deck» es distintiva (37 de 7.815 nombres); «black», «100», «ultimate» y «guard» no',
   {w: EL._ns['_distintivo'](w) for w in ('deck', 'case', 'black', '100', 'ultimate', 'guard')},
   {'deck': True, 'case': True, 'black': False, '100': False, 'ultimate': False, 'guard': False})

print('\n(C) la hoja «Ambiguos»: el ganador POR PUESTO, como la escribe el viejo')
for c in CASOS:
    if len(c['fichas_es']) == 2:
        eq('(C) %s: %s' % (c['ean'], c['ambiguos_viejo']), EL.ganador_por_puesto(c['fichas_es']), c['ambiguos_viejo'])
CARD = [c for c in CASOS if c['ean'] == '4056133014595'][0]
_g = EL.ganador_por_puesto(CARD['fichas_es'])
eq('(C) con 8 fichas: 7 filas y la ÚLTIMA es la del viejo (las de en medio dependen del orden en que Keepa se las dio)',
   (len(_g), _g[-1]), (len(CARD['ambiguos_viejo']), CARD['ambiguos_viejo'][-1]))

print('\n(D) la guarda muerde')
with io.open(os.path.join(AQUI, e2.RUTA_MOTOR), encoding='utf-8') as fh:
    VIEJO = fh.read()


def fallan_con(sustituir, por):
    """Los EAN de los 13 en los que falla la regla con el fichero del viejo cambiado (en una copia)."""
    assert VIEJO.count(sustituir) == 1, sustituir
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as t:
        t.write(VIEJO.replace(sustituir, por))
    try:
        el = con_idf(t.name)
        return sorted(c['ean'] for c in CASOS if elige(el, c) != c['esperado'])
    finally:
        os.unlink(t.name)


_MAYOR = fallan_con('elegido = min((c for c, _ in casan), key=keyrank)', 'elegido = max((c for c, _ in casan), key=keyrank)')
print('    (con «mayor puesto» fallan: %s)' % ', '.join(_MAYOR))
eq('(D) 🔴 «menor puesto» cambiado por «mayor» (entre las que casan): falla en alguno de los 13', bool(_MAYOR), True)
eq('(D) 🔴 sin el cotejo de título (todo «n/d» → por puesto): falla justo el Deck Case 100+ Black, y solo él',
   fallan_con("    if not COTEJO_ACTIVO:\n        return None, 0.0, 'n/d: proveedor sin columna de nombre'",
              "    if True:\n        return None, 0.0, 'n/d: proveedor sin columna de nombre'"), ['4260250075074'])
eq('(D) 🔴 keyrank al revés (el MAYOR puesto primero): falla',
   bool(fallan_con("def keyrank(c): return c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12",
                   "def keyrank(c): return -c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12")), True)
eq('(D) sin ninguna ficha en ES no se elige nada (el viejo solo mira ES): sigue en la puerta b',
   EL.elegir('Algo', [{'asin': None, 'titulo': 'x'}]), None)
_mal = copy.deepcopy(VIEJO) + "\ndef keyrank(c): return 0\n"
with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as _t:
    _t.write(_mal)
try:
    e2.cargar_eleccion_viejo([], _t.name)
    _r = None
except e2.PiezaNoEncontrada as ex:
    _r = str(ex)
finally:
    os.unlink(_t.name)
eq('(D) 🔴 si hay DOS keyrank en el fichero del viejo, no adivina: no arranca', 'UN def keyrank' in (_r or ''), True)

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: en los 13 casos reales el escáner 2 elige la misma ficha que el viejo, con su regla leída de su fichero.')
