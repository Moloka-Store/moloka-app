# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO · EL MODO «MARCAS ELEGIDAS» (encargo B4, 25-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta el motor de verdad (escaner2_motor.py, con las piezas
del escaner viejo leidas de su fichero) y se lee el workflow de verdad.

QUE PRUEBA:
  (A) la seleccion que llega del workflow se valida: una lista JSON de textos, sin comillas dobles,
      acentos graves, barras, `$ < > ; | { }` ni saltos de linea, con topes; vacia, NO. El apostrofo
      pasa (HEO tiene «Loop' », y cae en «Otras»).
  (B) 🔴 COINCIDENCIA EXACTA: «CID» deja fuera a «Cidadela Toys» y a «Acid Games», que el filtro del
      director (por trozo) si meteria; sin espacios a los lados y sin distinguir mayusculas.
  (C) las ofertas de otra marca entran con la casilla y no sin ella; lo agotado, nunca.
  (D) la foto del modo: solo lo elegido; el resto de lo disponible, a la marca fuera, «no elegida» y
      con su oferta apuntada; y crudo = previas + foto.
  (E) el workflow: el modo 'elegidas' y los dos inputs nuevos llegan por `env:`, y NINGUN `run:`
      lleva un `${{ inputs.… }}` dentro (seria inyeccion de codigo en bash).
  (F) el Excel con el formato del viejo (correccion del 5c, 25-sep-2026 11:58): la huella del Excel
      viejo de verdad tiene sus seis hojas; la comparacion se pone ROJA si cambia el orden, una
      cabecera, una regla del semaforo, un color, un ancho, la tabla, una formula, un enlace o la fila
      congelada; y la Celda 9 del viejo se saca por dos anclas unicas y falla CERRADA.
"""
import json
import os
import sys

import escaner2_motor as e2

AQUI = os.path.dirname(os.path.abspath(__file__))
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def rechaza(marcas, ofertas='false'):
    try:
        e2.validar_seleccion(marcas, ofertas)
    except e2.SeleccionInvalida as ex:
        return str(ex)
    return None


M = e2.cargar_motor()

print('(A) la seleccion que llega del workflow')
eq('(A) una lista buena: sin espacios a los lados, sin repetir (sin distinguir mayúsculas), en su orden',
   e2.validar_seleccion('["Funko", " CID ", "funko", "Good Smile Company"]', 'false'),
   (['Funko', 'CID', 'Good Smile Company'], False))
eq("(A) el apóstrofo pasa: HEO tiene «Loop' » (25-sep-2026), y va en «Otras»",
   e2.validar_seleccion('["Loop\' ", "Beadle & Grimm´s", "Honey²", "Joy Toy (CN)", "Topps/Merlin", "Phat!"]', 'true'),
   (["Loop'", 'Beadle & Grimm´s', 'Honey²', 'Joy Toy (CN)', 'Topps/Merlin', 'Phat!'], True))
eq('(A) solo las ofertas, sin marcas: vale', e2.validar_seleccion('[]', 'true'), ([], True))
for _nombre, _marcas, _ofertas in (
        ('no es JSON', 'Funko, CID', 'false'),
        ('JSON que no es una lista', '{"marcas": ["Funko"]}', 'false'),
        ('un número en la lista', '["Funko", 3]', 'false'),
        ('null en la lista', '["Funko", null]', 'false'),
        ('comillas dobles dentro', '["Mal\\"a"]', 'false'),
        ('un salto de línea dentro', '["Fun\\nko"]', 'false'),
        ('un retorno de carro dentro', '["Fun\\rko"]', 'false'),
        ('un tabulador dentro', '["Fun\\tko"]', 'false'),
        ('un separador de línea unicode dentro', json.dumps(['Fun' + chr(0x2028) + 'ko']), 'false'),
        ('un carácter invisible dentro', json.dumps(['Fun' + chr(0x200b) + 'ko']), 'false'),
        ('un acento grave', '["Fun`ko"]', 'false'),
        ('una barra invertida', '["Fun\\\\ko"]', 'false'),
        ('un dólar', '["$(whoami)"]', 'false'),
        ('un punto y coma', '["Funko; rm"]', 'false'),
        ('una tubería', '["Funko|x"]', 'false'),
        ('llaves', '["${x}"]', 'false'),
        ('una marca de 81 caracteres', json.dumps(['x' * 81]), 'false'),
        ('501 marcas', json.dumps(['m%d' % i for i in range(501)]), 'false'),
        ('un texto de más de 20.000 caracteres', json.dumps(['x' * 70] * 300), 'false'),
        ('selección vacía (ni marcas ni ofertas)', '[]', 'false'),
        ('solo espacios', '   ', 'true'),
        ('sin lista', None, 'true'),
        ('la casilla que no es true ni false', '["Funko"]', 'si'),
        ('la casilla vacía', '["Funko"]', ''),
        ('la casilla en mayúsculas', '["Funko"]', 'True')):
    eq('(A) 🔴 se rechaza: %s' % _nombre, rechaza(_marcas, _ofertas) is not None, True)
eq('(A) …y el rechazo dice por qué (la selección vacía)', rechaza('[]'), 'selección vacía: ni una marca ni las ofertas')

print('\n(B) coincidencia EXACTA')


def fila(marca, estado='disponible', oferta=''):
    return {'estado': estado, 'marca': marca, 'en_oferta': oferta}


CATALOGO = [fila('CID'), fila(' cid '), fila('Cidadela Toys'), fila('Acid Games'), fila('Funko'), fila('FUNKO'),
            fila('Funko Pop'), fila('Numskull')]
Q, INFO = e2.filtro_elegidas(['CID'], False)
eq('(B) 🔴 «CID» mete «CID» y « cid », y deja fuera a «Cidadela Toys» y «Acid Games»',
   [f['marca'] for f in CATALOGO if Q(f)], ['CID', ' cid '])
QD, _ = e2.cargar_filtro_director({'marcas': ['CID']})
eq('(B) …que el filtro del director (por trozo) SÍ metería: por eso aquí no se usa',
   [f['marca'] for f in CATALOGO if QD(f)], ['CID', ' cid ', 'Cidadela Toys', 'Acid Games'])
Q, INFO = e2.filtro_elegidas(['funko'], False)
eq('(B) «funko» mete «Funko» y «FUNKO», no «Funko Pop»', [f['marca'] for f in CATALOGO if Q(f)], ['Funko', 'FUNKO'])
eq('(B) el info del modo: las marcas elegidas y la casilla, sin puesto máximo', INFO,
   {'marcas_reales': ['funko'], 'quiere_ofertas': False, 'rank_max': None})

print('\n(C) las ofertas de otra marca')
OFERTA = fila('Hasbro', oferta='SI')
AGOTADA = fila('Funko', estado='agotado', oferta='SI')
Q_sin, _ = e2.filtro_elegidas(['Funko'], False)
Q_con, _ = e2.filtro_elegidas(['Funko'], True)
eq('(C) 🔴 sin la casilla, la oferta de Hasbro NO entra', Q_sin(OFERTA), False)
eq('(C) 🔴 con la casilla, SÍ', Q_con(OFERTA), True)
eq('(C) lo agotado no entra nunca, ni elegido ni en oferta', (Q_sin(AGOTADA), Q_con(AGOTADA)), (False, False))
Q_of, _ = e2.filtro_elegidas([], True)
eq('(C) solo ofertas: entra lo que está en oferta, de cualquier marca', (Q_of(OFERTA), Q_of(fila('Funko'))), (True, False))

print('\n(D) la foto del modo «elegidas»')


def heo(n, marca, oferta='', estado='disponible'):
    cuerpo = '84355%07d' % n
    return {'productNumber': 'HEO%04d' % n, 'ean': cuerpo + M._chk13(cuerpo), 'nombre': 'Producto %d' % n,
            'marca': marca, 'categoria': 'Figuras', 'precio': 10.0, 'precio_base': 10.0, 'en_oferta': oferta,
            'campana': '', 'estado': estado, 'disponibilidad': 'GREEN', 'imagen': '', 'fin_de_vida': '', 'preorder': ''}


FILAS = [heo(1, 'CID'), heo(2, 'Cidadela Toys'), heo(3, 'Cidadela Toys', oferta='SI'), heo(4, 'Funko'),
         heo(5, 'CID', estado='agotado')]
Q, INFO = e2.filtro_elegidas(['CID'], False)
FOTO, APART, C = e2.construir_foto(FILAS, [], Q, M, n_crudo=6, n_sin_gtin=1, n_declarado=6, modo='elegidas')
eq('(D) 🔴 la foto solo trae CID', [f['marca'] for f in FOTO], ['CID'])
eq('(D) 🔴 el resto de lo disponible va a la marca fuera, «no elegida», con su oferta apuntada',
   [(a['marca'], a['detalle'], a['en_oferta']) for a in APART if a['motivo'] == 'marca_fuera'],
   [('Cidadela Toys', "Marca 'Cidadela Toys' no elegida", False), ('Cidadela Toys', "Marca 'Cidadela Toys' no elegida", True),
    ('Funko', "Marca 'Funko' no elegida", False)])
eq('(D) 🔴 CUADRA: crudo 6 = sin GTIN 1 + no disponible 1 + marca no elegida 3 + foto 1',
   (C['previas']['sin_gtin'], C['previas']['no_disponible'], C['previas']['marca_fuera'], C['n_foto'], C['cuadra_previo']),
   (1, 1, 3, 1, True))
_, APART_M, _ = e2.construir_foto(FILAS, [], Q, M, n_crudo=6, n_sin_gtin=1, n_declarado=6)
eq('(D) en el modo de siempre el detalle sigue diciendo «fuera de la lista del director»',
   {a['detalle'] for a in APART_M if a['motivo'] == 'marca_fuera'},
   {"Marca 'Cidadela Toys' fuera de la lista del director", "Marca 'Funko' fuera de la lista del director"})
eq('(D) la oferta solo se apunta en la marca fuera: en las demás puertas previas, None',
   {a['en_oferta'] for a in APART if a['motivo'] != 'marca_fuera'}, set())
eq('(D) el nombre de la puerta en pantalla y en el Excel: «Marca no elegida» solo en este modo',
   [e2.nombre_previa('marca_fuera', m) for m in ('elegidas', 'marcas', 'todas', None)],
   ['Marca no elegida', 'Marca fuera de la lista', 'Marca fuera de la lista', 'Marca fuera de la lista'])
eq('(D) los tres modos, en el orden de la base', e2.MODOS, ('marcas', 'todas', 'elegidas'))

print('\n(E) el workflow')
import yaml  # noqa: E402

with open(os.path.join(AQUI, '.github', 'workflows', 'escaner2-heo-barrido.yml'), encoding='utf-8') as fh:
    WF = yaml.safe_load(fh)
# `on:` se lee como True en YAML 1.1 (el «problema de Noruega»): se busca por las dos llaves.
ENTRADAS = (WF.get('on') or WF.get(True))['workflow_dispatch']['inputs']
eq('(E) el modo admite «elegidas», entre comillas (texto, no booleano)', ENTRADAS['modo']['options'],
   ['marcas', 'todas', 'elegidas'])
eq('(E) los inputs nuevos: marcas (texto) y ofertas (booleano, apagado)',
   (ENTRADAS['marcas']['type'], ENTRADAS['ofertas']['type'], ENTRADAS['ofertas']['default']), ('string', 'boolean', False))
PASOS = [p for j in WF['jobs'].values() for p in j['steps']]
eq('(E) 🔴 NINGÚN `run:` lleva un `${{ … }}` dentro: los inputs no se pegan en bash',
   [p.get('name') for p in PASOS if '${{' in str(p.get('run') or '')], [])
_barrer = [p for p in PASOS if p.get('run') == 'python -u escaner2_heo_barrido.py'][0]
eq('(E) 🔴 …llegan por env al paso que barre',
   {k: _barrer['env'].get(k) for k in ('MODO_BARRIDO', 'MARCAS_ELEGIDAS', 'OFERTAS_ELEGIDAS')},
   {'MODO_BARRIDO': '${{ inputs.modo }}', 'MARCAS_ELEGIDAS': '${{ inputs.marcas }}',
    'OFERTAS_ELEGIDAS': '${{ inputs.ofertas }}'})

print('\n(F) el Excel con el formato del viejo: la comparacion muerde y la Celda 9 falla CERRADA')
import copy  # noqa: E402
import tempfile  # noqa: E402

import escaner2_huella_excel as HU  # noqa: E402

REF = json.load(open(os.path.join(AQUI, 'huella_excel_viejo_heo.json'), encoding='utf-8'))
HOJAS_VIEJO = ['Análisis', 'Descartados', 'Ambiguos', 'Sin_rank', 'Precio por lote', 'Chase_manual']
eq('(F) la huella del Excel viejo de verdad: sus seis hojas, en su orden', [h['hoja'] for h in REF['hojas']], HOJAS_VIEJO)
eq('(F) …y «Análisis» con las columnas de COLS del viejo, «ISD s/ Fee Log. (€)» y «Origen IVA» al final',
   REF['hojas'][0]['cabecera'], list(e2.sacar_piezas(e2.RUTA_MOTOR, (), ('COLS',))['COLS']))
eq('(F) la huella contra sí misma: ni una diferencia', HU.diferencias(REF, REF), [])


def muta(f):
    h = copy.deepcopy(REF)
    f(h)
    return HU.diferencias(REF, h)


for _nombre, _f in (
        ('dos hojas cambiadas de orden', lambda h: h['hojas'].insert(1, h['hojas'].pop(2))),
        ('una cabecera renombrada', lambda h: h['hojas'][0]['cabecera'].__setitem__(4, 'PA')),
        ('una columna metida en medio', lambda h: h['hojas'][0]['cabecera'].insert(5, 'Nueva')),
        ('una regla del semáforo quitada', lambda h: h['hojas'][0]['formato_condicional'].pop()),
        ('otro color en COMPRAR', lambda h: [r.__setitem__('relleno', '00FFFFFF') for r in h['hojas'][0]['formato_condicional']
                                              if 'COMPRAR' in str(r['formula']) and 'NO' not in str(r['formula'])]),
        ('otro ancho de columna', lambda h: h['hojas'][0]['anchos'].__setitem__('Nombre', 30.0)),
        ('sin la tabla T_Analisis', lambda h: h['hojas'][0]['tablas'].clear()),
        ('un beneficio que no es la fórmula del viejo', lambda h: h['hojas'][0]['columnas']['Beneficio (€)'].__setitem__(
            'formula', ['=C[-8]R[0]-C[-13]R[0]'])),
        ('el ASIN sin enlace', lambda h: h['hojas'][0]['columnas']['ASIN'].__setitem__('enlace', False)),
        ('la fila sin congelar', lambda h: h['hojas'][0].__setitem__('congelada', None))):
    eq('(F) 🔴 la comparación se pone roja con %s' % _nombre, bool(muta(_f)), True)

with open(e2.RUTA_MOTOR, encoding='utf-8') as fh:
    _VIEJO = fh.read()


def bloque_de(texto):
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as t:
        t.write(texto)
    try:
        e2.sacar_bloque_excel(t.name)
        return None
    except e2.PiezaNoEncontrada as ex:
        return str(ex)
    finally:
        os.unlink(t.name)


_codigo, _necesita = e2.sacar_bloque_excel()
eq('(F) la Celda 9 del viejo se saca por sus dos anclas, y pide lo que el escáner 2 le da',
   sorted(_necesita - set(M._ns) - {'pct_comision_celda', 'en_bd_txt'}),
   sorted(['registros', 'problematicos', 'no_encontrados', 'chase_sueltos', '_dups', 'ambiguos', 'sin_rank',
           'chase_pendientes', 'cotejo_info', 'PROVEEDOR']))
eq('(F) 🔴 sin el ancla final (`_sin_excel = …`), no arranca',
   'UNA asignacion de nivel superior a _sin_excel' in (bloque_de(_VIEJO.replace('\n_sin_excel = ', '\n_sin_excel_x = ')) or ''), True)
eq('(F) 🔴 con el ancla de inicio dos veces, no arranca',
   'UNA asignacion de nivel superior a COLS' in (bloque_de(_VIEJO + '\nCOLS = []\n') or ''), True)
_F = [{'id': 'f1', 'ean_original': '8435500000014', 'ean_core': '8435500000014', 'nombre': 'x', 'marca': 'm',
       'precio_unidad': 5.0, 'aviso_caja': None}]
_R = [{'foto_id': 'f1', 'puerta': 'f', 'motivo': 'f_comprar', 'detalle': 'x', 'asin': 'B0X', 'paises': {}}]
try:
    _mal = _VIEJO.replace('\n_sin_excel = ', '\nprint(NOMBRE_QUE_NADIE_DA)\n_sin_excel = ', 1)
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as _t:
        _t.write(_mal)
    e2.excel_como_el_viejo(_F, _R, [], M, ruta=_t.name)
    _r = None
except e2.PiezaNoEncontrada as ex:
    _r = str(ex)
finally:
    os.unlink(_t.name)
eq('(F) 🔴 si la Celda 9 empieza a usar un nombre que el escáner 2 no le da, NO se adivina: revienta con su nombre',
   'NOMBRE_QUE_NADIE_DA' in (_r or ''), True)

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: el modo «marcas elegidas» valida lo que llega, casa las marcas EXACTAS, respeta la casilla de ofertas y cuadra.')
