# -*- coding: utf-8 -*-
"""Banco del escaner 2 de HEO · CAJAS CON CHASE Y LOS DOS MODOS DE MARCAS (encargo B2, 25-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta el motor de verdad (escaner2_motor.py, con las piezas
del escaner viejo leidas de su fichero) sobre CODIGOS REALES de HEO.

🔑 LOS CODIGOS SON LOS DE LA PASADA 8ac9a9de (25-sep-2026 07:48, produccion): nombre, codigo de la
   caja y estado sacados de `escaner2_apartado` + `escaner_chase_asin` por el conector de lectura y
   pegados aqui POR SCRIPT desde el registro de la sesion, no tecleados. El PRECIO es el real solo
   donde el encargo lo cita (8,62 · 6,59 · 11,44); en el resto es redondo (60 / 30): el repo es
   publico y el coste de HEO no se publica, y la regla (precio de la caja ÷ unidades) no depende
   de cual sea.

QUE PRUEBA:
  (A) el EAN de la figura comun, por su orden: GS1 con control valido → interior; EAN/UPC valido →
      ese; si no, 889698 + numero FK + control, y se dice. Si no casan, aviso (no se descarta).
  (B) las unidades salen del NOMBRE; si no las dice, no es caja.
  (C) la foto en el modo de SIEMPRE: cajas disponibles dentro, a precio de caja ÷ unidades, con el
      EAN de la figura; agotadas a «no disponible»; sin unidades, figura suelta por el flujo normal;
      la marca fuera se LISTA con su EAN, nombre, marca y precio. Y crudo = previas + foto.
  (D) la foto en el modo TODAS: sin filtro de marca, sin leer la regla, y crudo = previas + foto.
  (E) la comparacion con el viejo: cajas con chase y marca fuera = diferencia de criterio.
  (F) el tope del Visualizador (10.000 por lista) y las tandas.
"""
import io
import os
import sys
import tempfile

import escaner2_motor as e2

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


M = e2.cargar_motor()

# Las filas de la lista `chase` de descargar_heo, reales (ver cabecera).
CHASE_REAL = [
    {'producto_heo': 'FK87245', 'nombre': '*heo Exclusive Edition* One Piece POP!&Buddy Animation Vinyl Figuren Rob Lucci with Hattori w/Chase 10 cm Surtido (6)', 'ean_caja': '01108896988724512110000', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK86264', 'nombre': 'Sleepy Hollow POP! TV Vinyl Figuren Headless Horseman w/ Chase 9 cm Surtido (6)', 'ean_caja': '889698862646', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK88859', 'nombre': 'Invincible Figura POP! TV Vinyl B.B. w/(CH)(BD) heo exclusive Assortment Surtido (6) 9 cm ', 'ean_caja': '88645974', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK93057', 'nombre': "NFL Figura POP! Vinyl : Bengals- Ja'Marr Chase (clear visor) 9 cm", 'ean_caja': '889698930574', 'marca': 'Funko', 'precio_caja': 8.62, 'estado': 'agotado',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK91391', 'nombre': 'X-Men Pack de 4 Figuras Bitty POP! Vinyl Jean Grey w/CH 2,5 cm', 'ean_caja': '889698913911', 'marca': 'Funko', 'precio_caja': 6.59, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK72611-01', 'nombre': 'Demon Slayer: Kimetsu no Yaiba POP! Animation Vinyl Figuren Susamaru w/Ch 9 cm', 'ean_caja': '889698726115', 'marca': 'Funko', 'precio_caja': 8.62, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK93894', 'nombre': 'Demon Slayer: Kimetsu no Yaiba Figura POP! Premium Vinyl Zenitsu with Chase (Glow) 9 cm Surtido (3)', 'ean_caja': '889698938945', 'marca': 'Funko', 'precio_caja': 30.0, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK86643', 'nombre': 'Superman (2025) POP! Animation Vinyl Figuren Hammer of Boravia w/CH 9 cm Surtido (6)', 'ean_caja': '01108896988664362110000', 'marca': 'Funko', 'precio_caja': 11.44, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK13318', 'nombre': 'Stranger Things POP! TV Vinyl Figuren Eleven With Eggos 9 cm Surtido (6)', 'ean_caja': '01108896981331872110000', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'agotado',
     'imagen': '', 'link_amazon': ''},
    {'producto_heo': 'FK77398', 'nombre': 'Pop! Disney: Devil Donald with Blacklight Chase Asst.  (6)', 'ean_caja': '0889698773980', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'disponible',
     'imagen': '', 'link_amazon': ''},
]
POR_FK = {c['producto_heo']: c for c in CHASE_REAL}


def figura(fk, codigo=None):
    c = POR_FK[fk]
    return e2.ean_de_la_figura(c['ean_caja'] if codigo is None else codigo, fk, M)


# ═══════════════════════════════════════════════════════════════════════════════
print('(A) el EAN de la figura comun')
eq('(A) FK87245 · GS1 «01»+GTIN-14 con control valido → su interior (UPC de 12)', figura('FK87245'),
   ('889698872454', 'gs1_caja', None))
eq('(A) FK86643 · GS1 → 889698866439', figura('FK86643'), ('889698866439', 'gs1_caja', None))
eq('(A) FK86264 · ya trae el UPC de 12 de la figura → ese', figura('FK86264'), ('889698862646', 'ean_caja', None))
eq('(A) FK77398 · EAN-13 con cero delante → su UPC de 12', figura('FK77398'), ('889698773980', 'ean_caja', None))
eq('(A) FK88859 · código de 8 cifras que no es EAN → deducido del número de HEO (y lo dice)',
   figura('FK88859'), ('889698888592', 'numero_heo', None))
eq('(A) …el deducido es 889698 + las cinco cifras del FK + control', e2.ORIGEN_EAN['numero_heo'], 'deducido del número de HEO')
_ean, _origen, _aviso = e2.ean_de_la_figura(POR_FK['FK87245']['ean_caja'], 'FK11111', M)
eq('(A) 🔴 el GS1 dice una figura y el número de HEO otra → se queda el GS1 y AVISA, no se descarta',
   (_ean, _origen, 'FK11111' in (_aviso or '') and ('88969811111' + M._chk13('088969811111')) in (_aviso or '')),
   ('889698872454', 'gs1_caja', True))
_roto = POR_FK['FK87245']['ean_caja'][:15] + '9' + POR_FK['FK87245']['ean_caja'][16:]
eq('(A) 🔴 un GS1 con el control MAL no se cree: se deduce del número', figura('FK87245', _roto),
   ('889698872454', 'numero_heo', None))
eq('(A) FK72611-01 y FK95150-1: las cinco cifras del FK, sin el sufijo',
   [e2.ean_de_la_figura('', 'FK72611-01', M)[0], e2.ean_de_la_figura('', 'FK95150-1', M)[0]],
   ['889698726115', '889698951500'])
_n, _o, _motivo = e2.ean_de_la_figura('ABC', 'ZZ00001', M)
eq('(A) 🔴 ni código ni número FK → no hay EAN, y el motivo lo dice', (_n, _o, 'ZZ00001' in _motivo), (None, None, True))

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(B) las unidades, del nombre')
eq('(B) «Surtido (6)», «Surtido (3)», «Asst.  (6)» y «Assortment Surtido (6) 9 cm»',
   [e2.unidades_caja_chase(POR_FK[k]['nombre']) for k in ('FK87245', 'FK93894', 'FK77398', 'FK88859')], [6, 3, 6, 6])
eq('(B) «Surtido 6» sin paréntesis también; «Asst. (12)» también',
   [e2.unidades_caja_chase('Figura X Surtido 6'), e2.unidades_caja_chase('Figura X Asst. (12)')], [6, 12])
eq('(B) 🔴 «Surtido 9 cm» NO son 9 unidades', e2.unidades_caja_chase('Figura Surtido 9 cm'), None)
eq('(B) 🔴 el apellido (FK93057), el pack «w/CH» (FK91391) y «w/Ch 9 cm» (FK72611-01) NO son caja',
   [e2.unidades_caja_chase(POR_FK[k]['nombre']) for k in ('FK93057', 'FK91391', 'FK72611-01')], [None, None, None])


# ═══════════════════════════════════════════════════════════════════════════════
def heo(n, nombre, precio, marca='FUNKO', estado='disponible', ean=None, oferta=''):
    cuerpo = '84355%07d' % n
    return {'productNumber': 'HEO%04d' % n, 'ean': ean or (cuerpo + M._chk13(cuerpo)), 'nombre': nombre,
            'marca': marca, 'categoria': 'Figuras', 'precio': precio, 'precio_base': precio, 'en_oferta': oferta,
            'campana': '', 'estado': estado, 'disponibilidad': 'GREEN', 'imagen': '', 'fin_de_vida': '', 'preorder': ''}


FILAS = [
    heo(1, 'Funko Pop Alfa', 8.00),
    heo(2, 'Hasbro Nerf', 5.00, marca='Hasbro'),                    # marca fuera (en el modo de siempre)
    heo(3, 'Funko Pop agotado', 8.00, estado='agotado'),
    # La figura COMUN, suelta, de dos cajas: la caja no la pisa (es_chase distinto) y el guardarrail
    # caja-vs-suelta compara: 60/6 = 10 frente a 9,50 pasa; 11,44/6 = 1,91 frente a 8,62 SALTA.
    heo(4, 'Sleepy Hollow Headless Horseman suelta', 9.50, ean='889698862646'),
    heo(5, 'Superman Hammer of Boravia suelta', 8.62, ean='889698866439'),
]
RARA = {'producto_heo': 'ZZ00001', 'nombre': 'Caja rara Surtido (6)', 'ean_caja': 'ABC', 'marca': 'Funko',
        'precio_caja': 60.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''}
CHASE = CHASE_REAL + [RARA]
REGLA = {'proveedor': 'HEO', 'activo': True, 'marcas': ['Funko', 'Ultimate Guard', 'OFERTAS'], 'rank_maximo': 30000}
SIN_GTIN = 2
CRUDO = len(FILAS) + len(CHASE) + SIN_GTIN            # 5 + 11 + 2 = 18

print('\n(C) la foto en el modo de siempre (marcas)')
QUIERE, _info = e2.cargar_filtro_director(REGLA)
FOTO, APART, CUENTAS = e2.construir_foto(FILAS, CHASE, QUIERE, M, n_crudo=CRUDO, n_sin_gtin=SIN_GTIN, n_declarado=CRUDO)
_pf = {f['producto_heo']: f for f in FOTO}
eq('(C) en la foto: 3 de HEO + 6 cajas disponibles + 2 figuras sueltas que el regex tomó por chase',
   sorted(_pf), sorted(['HEO0001', 'HEO0004', 'HEO0005', 'FK87245', 'FK86264', 'FK88859', 'FK93894', 'FK86643',
                        'FK77398', 'FK91391', 'FK72611-01']))
eq('(C) 🔴 puertas previas: 1 caja sin EAN posible, 3 no disponibles (el agotado, la caja FK13318 y el '
   'suelto FK93057), 1 marca fuera', CUENTAS['previas'],
   {'chase_funko': 1, 'sin_gtin': 2, 'no_disponible': 3, 'marca_fuera': 1, 'estado_no_servible': 0,
    'chase_suelto': 0, 'ean_forma_rara': 0, 'duplicado_proveedor': 0})
eq('(C) 🔴 CUADRA: crudo 18 = previas 7 + foto 11', (CUENTAS['n_previas'], CUENTAS['n_foto'], CUENTAS['cuadra_previo']),
   (7, 11, True))
_k = _pf['FK87245']
eq('(C) FK87245: caja con chase de 6, con el EAN de la figura y el código de la caja tal cual',
   (_k['es_caja'], _k['es_chase'], _k['uds_caja'], _k['ean_core'], _k['ean_original'], _k['origen_ean']),
   (True, True, 6, '889698872454', POR_FK['FK87245']['ean_caja'], 'gs1_caja'))
eq('(C) 🔴 precio de la CAJA guardado, y la unidad = caja ÷ 6', (_k['precio_catalogo'], _k['precio_unidad']), (60.0, 10.0))
eq('(C) a Keepa va el EAN de la FIGURA (nunca el código de la caja)', _k['codigos_keepa'], ['889698872454'])
eq('(C) FK93894: caja de 3 → 30 ÷ 3 = 10', (_pf['FK93894']['uds_caja'], _pf['FK93894']['precio_unidad']), (3, 10.0))
eq('(C) FK88859: EAN deducido del número de HEO, y la fila lo dice',
   (_pf['FK88859']['ean_core'], _pf['FK88859']['origen_ean']), ('889698888592', 'numero_heo'))
eq('(C) 🔴 FK86643 (11,44 € la caja de 6): 1,91 €/ud, y el guardarrail relativo lo marca frente a su '
   'suelta de 8,62 (sin umbral absoluto de precio)',
   (round(_pf['FK86643']['precio_unidad'], 4), (_pf['FK86643']['aviso_caja'] or '').startswith('INCOHERENTE')),
   (round(11.44 / 6, 4), True))
eq('(C) FK86264: 10 €/ud frente a su suelta de 9,50 → sin aviso', _pf['FK86264']['aviso_caja'], None)
eq('(C) 🔑 la caja y su figura suelta conviven (una es chase y la otra no)',
   sorted((f['ean_core'], f['es_chase']) for f in FOTO if f['ean_core'] == '889698862646'),
   [('889698862646', False), ('889698862646', True)])
eq('(C) 🔴 las sueltas del regex van como figura NORMAL con su EAN (no son caja ni chase)',
   [(_pf[k]['es_caja'], _pf[k]['es_chase'], _pf[k]['ean_core'], _pf[k]['origen_ean']) for k in ('FK91391', 'FK72611-01')],
   [(False, False, '889698913911', None), (False, False, '889698726115', None)])
eq('(C) 🔴 el chase nunca lleva ASIN propio: la foto no tiene ASIN (lo pone Keepa por el EAN de la figura)',
   any('asin' in f for f in FOTO), False)
eq('(C) el rótulo: «caja con chase · N uds»', [e2.rotulo_caja(_pf[k]) for k in ('FK87245', 'FK93894', 'HEO0001')],
   ['caja con chase · 6 uds', 'caja con chase · 3 uds', ''])
_mf = [a for a in APART if a['motivo'] == 'marca_fuera']
eq('(C) 🔴 la marca fuera se LISTA con su EAN, nombre, marca y precio',
   [(a['ean_original'], a['nombre'], a['marca'], a['precio_catalogo']) for a in _mf],
   [(FILAS[1]['ean'], 'Hasbro Nerf', 'Hasbro', 5.0)])
eq('(C) la caja sin EAN posible, a su puerta, con el motivo',
   [(a['producto_heo'], a['motivo']) for a in APART if a['motivo'] == 'chase_funko'], [('ZZ00001', 'chase_funko')])

print('\n(D) la foto en el modo TODAS LAS MARCAS')
Q2, INFO2 = e2.filtro_todas()
eq('(D) el filtro no trae marcas ni ofertas (no se ha leído ninguna regla)', (INFO2['marcas_reales'], INFO2['quiere_ofertas']),
   (None, None))
FOTO2, APART2, C2 = e2.construir_foto(FILAS, CHASE, Q2, M, n_crudo=CRUDO, n_sin_gtin=SIN_GTIN, n_declarado=CRUDO)
eq('(D) 🔴 la marca de fuera entra (Hasbro), y lo agotado sigue fuera',
   ('HEO0002' in {f['producto_heo'] for f in FOTO2}, 'HEO0003' in {f['producto_heo'] for f in FOTO2}), (True, False))
eq('(D) 🔴 CUADRA: crudo 18 = previas 6 (sin marca fuera) + foto 12',
   (C2['previas']['marca_fuera'], C2['n_previas'], C2['n_foto'], C2['cuadra_previo']), (0, 6, 12, True))
_c = e2.cuadre_previo(dict(C2, n_foto=11))
eq('(D) 🔴 y si uno se pierde, NO cuadra', _c['cuadra_previo'], False)
eq('(D) 🔴 las cajas con chase entran igual en los dos modos',
   sorted(f['producto_heo'] for f in FOTO2 if f['origen_ean']), sorted(f['producto_heo'] for f in FOTO if f['origen_ean']))

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(E) la comparacion con el viejo')
fuera = e2.marca_fuera_del_viejo(['Funko', 'Ultimate Guard'], True)
eq('(E) la lista del viejo es SU filtro: Hasbro fuera; Hasbro en oferta y Funko, dentro',
   [fuera({'marca': 'Hasbro'}) is not None, fuera({'marca': 'Hasbro', 'en_oferta': True}), fuera({'marca': 'FUNKO'})],
   [True, None, None])
eq('(E) …y el texto dice cuál es la lista', fuera({'marca': 'Hasbro'}),
   'marca fuera de la lista del viejo (Funko, Ultimate Guard y ofertas)')


def nuevo(ean, puerta='f', caja=False, marca='FUNKO', en_oferta=False, rank=12000):
    return {'puerta': puerta, 'motivo': {'f': 'f_comprar', 'c': 'c_pocas_caidas'}[puerta], 'detalle': 'x',
            'mejor_pais': 'ES', 'decision': {'f': 'COMPRAR'}.get(puerta), 'ean': ean, 'nombre': 'n', 'core': ean,
            'rank_es': rank, 'rank90_es': rank, 'propio': False, 'caja_chase_heo': caja, 'marca': marca,
            'en_oferta': en_oferta}


_viejo = {'889698862646': {'ean': '889698862646', 'nombre': 'suelta', 'decisiones': {'ES': 'COMPRAR'},
                           'fichero': 'f.xlsx', 'fecha': None, 'modo': 'todo'}}
_nuevo = {'889698872454': nuevo('889698872454', caja=True),
          '889698862646': nuevo('889698862646', puerta='c', caja=True),
          '8435500000021': nuevo('8435500000021', marca='Hasbro'),
          '8435500000038': nuevo('8435500000038', marca='Hasbro', en_oferta=True),
          '8435500000045': nuevo('8435500000045')}
_ctx = {'umbral': 8, 'paises': ['ES', 'DE'], 'paises_filtro': ['ES', 'DE'], 'rank_max': 30000, 'apartados': {},
        'fecha_nuevo': None}
CMP = {c['ean_norm']: c for c in e2.comparar(_viejo, _nuevo, dict(_ctx, marca_fuera_viejo=fuera), M)}
eq('(E) 🔴 caja con chase COMPRAR que el viejo no tiene → DIFERENCIA DE CRITERIO, no «sin explicar»',
   (CMP['889698872454']['diferencia_criterio'], CMP['889698872454']['explicacion']),
   (True, 'Diferencia de criterio: el viejo no valora cajas con chase de HEO'))
eq('(E) 🔴 el viejo dice COMPRAR a la suelta y el nuevo solo ve la caja (no se vende) → también criterio',
   (CMP['889698862646']['categoria'], CMP['889698862646']['diferencia_criterio'],
    'no valora cajas con chase' in CMP['889698862646']['explicacion']), ('solo_viejo', True, True))
eq('(E) 🔴 modo todas: Hasbro sin oferta → «marca fuera de la lista del viejo»',
   (CMP['8435500000021']['diferencia_criterio'], 'marca fuera de la lista del viejo' in CMP['8435500000021']['explicacion']),
   (True, True))
eq('(E) Hasbro EN OFERTA sí lo mira el viejo: sin ese criterio (y con puesto ≤ 30.000, sin explicar)',
   (CMP['8435500000038']['diferencia_criterio'], CMP['8435500000038']['explicacion']),
   (False, 'Sin explicar: no está en los Excel del viejo'))
eq('(E) un Funko que el viejo no tiene sigue SIN EXPLICAR', CMP['8435500000045']['diferencia_criterio'], False)
_marcas = {c['ean_norm']: c for c in e2.comparar(_viejo, _nuevo, _ctx, M)}
eq('(E) 🔴 en el modo de siempre (sin lista) la marca no explica nada', _marcas['8435500000021']['diferencia_criterio'], False)

# ═══════════════════════════════════════════════════════════════════════════════
print('\n(F) el tope del Visualizador')
eq('(F) la tanda del motor no pasa de 10.000', e2.tanda_visualizador() <= e2.TOPE_VISUALIZADOR == 10000, True)
_tmp = tempfile.mkdtemp(prefix='e2b2_')
_ruta = os.path.join(_tmp, 'escaner2_heredado_descarga.py')
io.open(_ruta, 'w', encoding='utf-8').write("TANDA = int(os.environ.get('HEO_TANDA', '20000'))\n")
try:
    e2.tanda_visualizador(_ruta)
    _msg = 'arranco'
except e2.PiezaNoEncontrada as ex:
    _msg = str(ex)
eq('(F) 🔴 una TANDA de 20.000 no arranca (el Visualizador no la acepta entera)', 'tope del Visualizador' in _msg, True)
_t = e2.partir_en_tandas([str(i) for i in range(23563)], e2.tanda_visualizador())
eq('(F) 23.563 códigos → tres tandas, ninguna de más de 10.000', [len(x) for x in _t], [10000, 10000, 3563])

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: las cajas con chase de HEO entran con el EAN de su figura, los dos modos cuadran y el viejo '
      'queda explicado.')
