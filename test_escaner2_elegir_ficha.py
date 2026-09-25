# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO · ELEGIR LA FICHA CUANDO UN EAN TIENE VARIAS (encargo B5, 25-sep-2026;
B6 el mismo dia: el titulo se coteja en ES, IT, FR y DE).

SIN RED, SIN SECRETOS Y SIN BASE. La regla es la del viejo, SACADA de su fichero
(moloka_escaner_nube.py: `elegir_candidato`, su cotejo de titulo y `keyrank`) y ejecutada.

🔑 LOS 13 CASOS SON REALES (casos_b5_fichas.json, volcado por script, no tecleado): los EAN de la puerta
   b del cruce 37eaa138 que el viejo daba como COMPRAR o VALORAR, con sus fichas de ES (ASIN, titulo y
   puesto medio de 90 dias) tal como las guardo el cruce, y como respuesta la ficha que puso el viejo en
   el «Análisis» de su Excel. Para el cotejo, las palabras de esos 13 nombres con en cuantos nombres del
   catalogo de la pasada (7.815) salen: es lo UNICO que el cotejo mira. Sin precios.

   (B6) `fichas_otros` lleva el titulo de cada ficha en IT/FR/DE, del mismo cruce y volcado igual.

QUE PRUEBA:
  (A) (B6) en 12 de los 13 el nuevo elige la MISMA ficha que el viejo; en el Deck Case 100+ Black,
      B00M6XJWVM, y dice que es distinta del viejo. `asin_viejo` es, en los 13, la ficha del viejo;
  (B) el Deck Case 100+ Black: gana por puesto B00M6XJWVM; el viejo eligio B00RLSIUBK porque en ES solo
      el titulo de esa trae «deck»; en IT/FR/DE las dos lo traen, y entre las dos gana el puesto;
  (C) la hoja «Ambiguos»: lo que escribe el viejo es el ganador POR PUESTO, no el del cotejo;
  (D) 🔴 LA GUARDA MUERDE: con la regla cambiada en una copia del fichero del viejo («menor puesto» por
      «mayor», o sin el cotejo de titulo) el banco se pone rojo; (B6) con el cotejo solo en ES (una copia
      del motor con PAISES_COTEJO = ('ES',)) vuelve a salir B00RLSIUBK → rojo; y sin ficha en ES no se
      elige nada.
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


def otros(caso):
    """(B6) {pais: filas} de las fichas del caso fuera de ES, con su titulo, como `cands_por_pais`."""
    salida = {}
    for x in caso['fichas_otros']:
        salida.setdefault(x['pais'], []).append({'asin': x['asin'], 'titulo': x['titulo']})
    return salida


def eleccion(el, caso):
    return el.elegir(caso['nombre'], caso['fichas_es'], otros(caso))


def elige(el, caso):
    r = eleccion(el, caso)
    return r['asin'] if r else None


# (B6) Lo que se espera: la ficha del viejo en 12, y la 100+ negra en el Deck Case 100+ Black.
DECK_EAN, DECK_BUENA, DECK_VIEJO = '4260250075074', 'B00M6XJWVM', 'B00RLSIUBK'
ESPERADO = {c['ean']: (DECK_BUENA if c['ean'] == DECK_EAN else c['esperado']) for c in CASOS}

EL = con_idf()
print('(A) los 13 casos reales: la ficha del viejo en 12, y la buena en el Deck Case 100+ Black')
eq('(A) son 13, del cruce 37eaa138, todos de la puerta b', (len(CASOS), {c['puerta_37eaa138'] for c in CASOS}), (13, {'b'}))
eq('(A) (B6) el volcado trae el título de IT/FR/DE de cada ficha: 94, ninguno vacío',
   (sum(len(c['fichas_otros']) for c in CASOS), all(x['titulo'] for c in CASOS for x in c['fichas_otros'])), (94, True))
eq('(A) el Deck Case es el único en que lo esperado no es la ficha del viejo',
   [c['ean'] for c in CASOS if ESPERADO[c['ean']] != c['esperado']], [DECK_EAN])
for c in CASOS:
    r = eleccion(EL, c)
    eq('(A) %s %s → %s (%s)' % (c['ean'], c['nombre'][:40], ESPERADO[c['ean']], c['excel_viejo'][-18:-5]),
       r['asin'], ESPERADO[c['ean']])
eq('(A) (B6) en los 13, `asin_viejo` es la ficha que puso el viejo en su Excel',
   {c['ean']: eleccion(EL, c)['asin_viejo'] for c in CASOS}, {c['ean']: c['esperado'] for c in CASOS})
eq('(A) (B6) «distinta del viejo» solo lo dice el Deck Case, y con el ASIN del viejo',
   [(c['ean'], eleccion(EL, c)['detalle'].split('distinta del viejo: ')[-1]) for c in CASOS
    if 'distinta del viejo' in eleccion(EL, c)['detalle']], [(DECK_EAN, 'el viejo elegiría ' + DECK_VIEJO)])
eq('(A) donde el viejo cotejó entre varias, el veredicto es el suyo («OK» en su Excel)',
   {c['ean']: eleccion(EL, c)['veredicto'] for c in CASOS if len(c['fichas_es']) >= 2},
   {c['ean']: c['cotejo_viejo'] for c in CASOS if len(c['fichas_es']) >= 2})
eq('(A) los dos con UNA sola ficha en ES (Supernenas y Hermione): esa, como el viejo, que solo mira ES',
   [(c['ean'], eleccion(EL, c)['veredicto']) for c in CASOS if len(c['fichas_es']) == 1],
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
_tit = {(x['pais'], x['asin']): x['titulo'] for x in DECK['fichas_otros']}
eq('(B) (B6) en IT, FR y DE el título de las DOS trae «deck» y «case»: casan las dos, en los tres',
   {(p, a): EL._ns['cotejar'](DECK['nombre'], _tit[(p, a)])[0] for p in ('IT', 'FR', 'DE') for a in (DECK_BUENA, DECK_VIEJO)},
   {(p, a): True for p in ('IT', 'FR', 'DE') for a in (DECK_BUENA, DECK_VIEJO)})
_r = eleccion(EL, DECK)
eq('(B) (B6) …así que entre las dos manda el puesto: B00M6XJWVM, que casó en IT, FR y DE (no en ES)',
   (_r['asin'], _r['veredicto'], _r['paises_cotejo'], _r['asin_viejo']), (DECK_BUENA, 'OK', ['IT', 'FR', 'DE'], DECK_VIEJO))
eq('(B) (B6) el detalle dice en qué país casó y que es distinta de la del viejo', _r['detalle'],
   '2/2 casan; entre esos, mejor rank (casó en IT, FR, DE · casa: case, deck)'
   ' · distinta del viejo: el viejo elegiría B00RLSIUBK')
_v = EL.elegir(DECK['nombre'], DECK['fichas_es'])
eq('(B) (B6) sin los títulos de fuera de ES sale lo del viejo, y dice que casó en ES', (_v['asin'], _v['detalle']),
   (DECK_VIEJO, '1/2 casan; entre esos, mejor rank (casó en ES · casa: deck)'))
# Si en ningún país casa ninguna, se sigue EXACTAMENTE como el viejo: su «⚠ DUDOSO» y su elegida.
_nada = [{'asin': 'B0NADA0001', 'titulo': 'Zapatilla de deporte roja', 'rank90': 500},
         {'asin': 'B0NADA0002', 'titulo': 'Taza de cafe Ultimate', 'rank90': 90000}]
_otros_nada = {'FR': [{'asin': 'B0NADA0001', 'titulo': 'Chaussure rouge'}, {'asin': 'B0NADA0002', 'titulo': 'Tasse Guard'}]}
_rn = EL.elegir(DECK['nombre'], _nada, _otros_nada)
_vn = EL._ns['elegir_candidato'](DECK['nombre'], [{'asin': x['asin'], 'title': x['titulo'], 'r_90': x['rank90']} for x in _nada],
                                 EL._ns['keyrank'])
eq('(B) (B6) ninguna casa en ningún país → la del viejo, con su veredicto y su detalle, y lo dice',
   (_rn['asin'], _rn['veredicto'], _rn['detalle'], _rn['paises_cotejo']),
   (_vn[0]['asin'], '⚠ DUDOSO', _vn[2] + ' · ninguna casa en ningún país (ES/IT/FR/DE): como el viejo', []))

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
        return sorted(c['ean'] for c in CASOS if (eleccion(el, c)['asin'], eleccion(el, c)['veredicto'])
                      != (ESPERADO[c['ean']], c['cotejo_viejo'] if len(c['fichas_es']) >= 2 else 'única en ES'))
    finally:
        os.unlink(t.name)


_MAYOR = fallan_con('elegido = min((c for c, _ in casan), key=keyrank)', 'elegido = max((c for c, _ in casan), key=keyrank)')
print('    (con «mayor puesto» fallan: %s)' % ', '.join(_MAYOR))
eq('(D) 🔴 «menor puesto» cambiado por «mayor» (entre las que casan): falla en alguno de los 13', bool(_MAYOR), True)
# (B6) Sin cotejo, el puesto solo da la ficha esperada en los 13 (B00M6XJWVM es la de mejor puesto): lo
#      que se pone rojo es el veredicto, «n/d» en vez del «OK» del viejo, en los 11 con varias fichas en ES.
eq('(D) 🔴 sin el cotejo de título (todo «n/d» → por puesto): fallan los 11 con varias fichas en ES',
   fallan_con("    if not COTEJO_ACTIVO:\n        return None, 0.0, 'n/d: proveedor sin columna de nombre'",
              "    if True:\n        return None, 0.0, 'n/d: proveedor sin columna de nombre'"),
   sorted(c['ean'] for c in CASOS if len(c['fichas_es']) >= 2))
eq('(D) 🔴 keyrank al revés (el MAYOR puesto primero): falla',
   bool(fallan_con("def keyrank(c): return c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12",
                   "def keyrank(c): return -c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12")), True)
eq('(D) sin ninguna ficha en ES no se elige nada (el viejo solo mira ES): sigue en la puerta b',
   EL.elegir('Algo', [{'asin': None, 'titulo': 'x'}]), None)
eq('(D) (B6) …aunque la haya en otros países: las candidatas son las de ES',
   EL.elegir('Ultimate Guard Deck Case', [], {'FR': [{'asin': 'B0FR000001', 'titulo': 'Ultimate Guard Deck Case'}]}), None)


def motor_con(sustituir, por):
    """Una copia del motor del escaner 2 con un cambio, cargada como modulo aparte (el original, intacto)."""
    import importlib.util
    with io.open(os.path.join(AQUI, 'escaner2_motor.py'), encoding='utf-8') as fh:
        texto = fh.read()
    assert texto.count(sustituir) == 1, sustituir
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as t:
        t.write(texto.replace(sustituir, por))
    try:
        spec = importlib.util.spec_from_file_location('escaner2_motor_roto', t.name)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(t.name)


_solo_es = motor_con("PAISES_COTEJO = ('ES', 'IT', 'FR', 'DE')", "PAISES_COTEJO = ('ES',)")
_el_es = _solo_es.cargar_eleccion_viejo([])
_el_es._ns['_DF'], _el_es._ns['_NDOC'] = EL._ns['_DF'], EL._ns['_NDOC']
eq('(D) 🔴 (B6) con el cotejo SOLO en ES (una copia del motor) vuelve a salir B00RLSIUBK: falla el Deck Case, y solo él',
   (sorted(c['ean'] for c in CASOS if elige(_el_es, c) != ESPERADO[c['ean']]), elige(_el_es, DECK)), ([DECK_EAN], DECK_VIEJO))
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

print('\n(E) (B5-bis) el corpus del cotejo NO depende de las marcas elegidas')
# Un MISMO catalogo, barrido en modo «todas» y en modo «elegidas» con solo Ultimate Guard. La escena
# reproduce los recuentos REALES del corpus de la pasada ed95d086 (7.815 nombres; en cuantos sale cada
# palabra de los 13 nombres): los 13 productos, y relleno con palabras inventadas hasta cuadrar cada
# recuento. La mitad del relleno es de Ultimate Guard y la otra mitad de otras marcas. Y tres filas de
# otra marca que las demas puertas previas echan en «todas» (forma rara, chase suelto, duplicado).
M = e2.cargar_motor()
TOK = EL._ns['_tok_cot']
ABC = 'abcdefghijklmnopqrtuvwxyz'            # sin «s»: el cotejo quita la «s» final de los plurales


def palabra(k):
    w = 'zq'
    for _ in range(4):
        w += ABC[k % 25]
        k //= 25
    return w


def ean13(n):
    cuerpo = '84399%07d' % n
    return cuerpo + M._chk13(cuerpo)


def fila_heo(n, nombre, marca, precio=10.0, ean=None):
    return {'productNumber': 'HEO%05d' % n, 'ean': ean or ean13(n), 'nombre': nombre, 'marca': marca,
            'categoria': 'x', 'precio': precio, 'precio_base': precio, 'en_oferta': '', 'campana': '',
            'estado': 'disponible', 'disponibilidad': 'GREEN', 'imagen': '', 'fin_de_vida': '', 'preorder': ''}


filas_cat, cuenta, n = [], {}, 0
for c in CASOS:
    marca = 'Ultimate Guard' if c['nombre'].startswith('Ultimate Guard') else 'Funko'
    filas_cat.append(fila_heo(0, c['nombre'], marca, ean=c['ean']))
    for w in set(TOK(c['nombre'])):
        cuenta[w] = cuenta.get(w, 0) + 1
# Como en la realidad, un nombre de relleno lleva VARIAS de esas palabras: en la vuelta r van todas las que
# todavía necesitan más de r apariciones (así cada una sale exactamente las que le faltan).
falta = {w: df - cuenta.get(w, 0) for w, df in DATOS['idf']['df'].items()}
k = 0
for r in range(max(falta.values())):
    n += 1
    k += 1
    palabras = [w if TOK(w) == [w] else w + 's' for w in sorted(falta) if falta[w] > r]
    filas_cat.append(fila_heo(n, ' '.join(palabras + [palabra(k)]), 'Ultimate Guard' if n % 2 else 'Otra %d' % (n % 7)))
while len({f['nombre'] for f in filas_cat}) < DATOS['idf']['n_nombres']:
    n += 1
    k += 1
    filas_cat.append(fila_heo(n, '%s %s' % (palabra(k), palabra(k + 10 ** 6)), 'Ultimate Guard' if n % 2 else 'Otra %d' % (n % 7)))
# Las que echan las demás puertas previas (y llevan «deck», para que se note si se cuelan en el corpus).
_ug = [f for f in filas_cat if f['marca'] == 'Ultimate Guard' and f['productNumber'] != 'HEO00000'][0]
RARAS = [fila_heo(900001, 'deck forma rara zqzzzz', 'Otra 1', ean='12345'),
         fila_heo(900002, 'deck zqyyyy Chase', 'Otra 2'),
         fila_heo(900003, 'deck duplicado zqxxxx', 'Otra 3', precio=99.0, ean=_ug['ean'])]
eq('(E) la escena: el chase suelto lo es para el viejo (su `clasificar_chase`)', M.clasificar_chase(RARAS[1]['nombre'], RARAS[1]['ean'])[2], True)
CATALOGO = filas_cat + RARAS


def corpus_de(quiere, modo, solo_foto=False):
    foto, apart, _c = e2.construir_foto(CATALOGO, [], quiere, M, modo=modo)
    if solo_foto:
        return e2.cargar_eleccion_viejo([f['nombre'] for f in foto]), len(foto), apart
    nombres, _fuera = e2.corpus_cotejo(foto, apart, M)
    return e2.cargar_eleccion_viejo(nombres), len(foto), apart


EL_T, N_T, AP_T = corpus_de(e2.filtro_todas()[0], 'todas')
EL_UG, N_UG, AP_UG = corpus_de(e2.filtro_elegidas(['Ultimate Guard'], False)[0], 'elegidas')
eq('(E) la escena reproduce el corpus real en modo «todas»: 7.815 nombres, y los recuentos de las 49 palabras',
   (EL_T.n_nombres, {w: EL_T._ns['_DF'].get(w, 0) for w in DATOS['idf']['df']}), (DATOS['idf']['n_nombres'], DATOS['idf']['df']))
eq('(E) …y las tres raras las echan sus puertas (forma rara, chase suelto, duplicado)',
   sorted(a['motivo'] for a in AP_T), ['chase_suelto', 'duplicado_proveedor', 'ean_forma_rara'])
eq('(E) en modo «elegidas» (solo Ultimate Guard) la FOTO encoge, y la marca no elegida va aparte',
   (N_UG < N_T / 2 + 20, sum(1 for a in AP_UG if a['motivo'] == 'marca_fuera') > 3000), (True, True))
eq('(E) 🔴 pero el corpus del cotejo es el MISMO: mismos nombres y los mismos recuentos',
   (EL_UG.n_nombres, dict(EL_UG._ns['_DF'])), (EL_T.n_nombres, dict(EL_T._ns['_DF'])))
eq('(E) 🔴 …y la MISMA elección en los 13 casos, la esperada (B6)',
   [elige(EL_UG, c) for c in CASOS], [ESPERADO[c['ean']] for c in CASOS])
EL_FOTO, _n, _a = corpus_de(e2.filtro_elegidas(['Ultimate Guard'], False)[0], 'elegidas', solo_foto=True)
eq('(E) 🔴 si el corpus fuera solo la foto (lo del #313 antes del B5-bis), con solo UG cambiaría: otro número de nombres y «deck» con otro recuento',
   (EL_FOTO.n_nombres != EL_T.n_nombres, EL_FOTO._ns['_DF'].get('deck') != EL_T._ns['_DF'].get('deck')), (True, True))

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: en los 13 casos reales el escáner 2 elige la ficha del viejo en 12 y la buena en el Deck Case 100+ Black,'
      ' con la regla del viejo leída de su fichero y el título cotejado en ES, IT, FR y DE.')
