# -*- coding: utf-8 -*-
"""Banco de la FOTO DE DISPONIBILIDAD DE HEO (encargo E, tramo 3, pieza 1, 29-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta el modulo de verdad (escaner2_disponibilidad.py, sobre el
motor del escaner 2 y sus piezas heredadas) con filas con la MISMA FORMA que devuelve
`descargar_catalogo_heo(con_chase=True)`, y el programa entero contra una base y un HEO de mentira.
Los codigos de las cajas con chase son reales (los del banco de las cajas, pasada 8ac9a9de); TODOS los
precios son inventados y redondos: el repo es publico y el coste de HEO no se publica, y ninguna regla
depende de cual sea.

QUE PRUEBA:
  (A) Todo lo que devuelve la descarga entra: todas las marcas, disponible y agotado, una fila por
      producto de HEO (los sin GTIN no llegan: la descarga heredada los quita y solo se cuentan).
  (B) LAS MISMAS REGLAS QUE EL BARRIDO: en lo disponible, cada fila de la foto del barrido (modo
      'todas') sale aqui IGUAL (EAN de cruce, caja, unidades, chase, precio de catalogo y por unidad);
      lo que el barrido aparta sale aqui con su regla; y lo que el barrido quita por duplicado, aqui
      esta (la llave es el producto, no el EAN).
  (C) La trampa del precio de caja: precio de catalogo y por unidad SEPARADOS, con las unidades.
  (D) El cuadre: leidas = disponibles + agotados = lo que devolvio descargar_heo.
  (E) Una lectura con la llave rota (sin numero o repetido) no se sube.
  (F) Los recuentos del log: los siete numeros (declarado y llegado de productos, precios y
      disponibilidades, y sin GTIN), y None (no cero) si falta uno.
  (G) EL PROGRAMA, POR ESTRUCTURA: solo toca disp_pasada, disp_lectura y disp_aplicar_pasada; sin la
      llave de servicio aborta antes de abrir ningun cliente; y el workflow no lleva reloj de GitHub,
      solo lee el repo y comparte grupo con el barrido y el cruce (no baja HEO dos veces a la vez).
  (H) LA DESCARGA CORTADA (revision de Cowork, 29-sep-2026): la heredada deja de pedir paginas sin
      error, y sin disponibilidades todo sale agotado. Si uno de los tres endpoints no llega entero,
      se dice cual. «Entero» es con TOLERANCIA (Fernando, 29-sep-2026: 10 por endpoint, porque el
      catalogo cambia mientras se pagina): ±1 y ±10 pasan; 11 y una pagina perdida (500) no; sin
      tolerancia valida, no se da nada por entero.
  (I) EL PROGRAMA ENTERO, con una base y un HEO de mentira: con las disponibilidades cortadas, la
      pasada queda 'fallida' con sus recuentos, sin subir ni una fila y SIN llamar a la funcion de la
      base; con la descarga entera, sube lo leido, llama a la funcion y relee la pasada. Y lo nuevo:
      las listas crudas se cogen al paso de `_paginar` (que queda como estaba), las filas suben
      marcadas si vinieron sin dato y la pasada con sus recuentos; sin tolerancia en la base no se
      baja nada; una CAIDA ACEPTADA sale en rojo con su aviso.
  (J) SIN DATO NO ES AGOTADO (Fernando, 29-sep-2026): cada fila sale marcada si su numero no llego en
      `prices` o en `availabilities` (tambien las cajas con chase), con sus recuentos; y las listas
      crudas tienen que ser las que uso la descarga (su tamaño, el del log), o no se sube nada.
  (L) REPETIDOS (remates, 29-sep-2026): un producto repetido con copias identicas se queda una vez y se
      cuenta; con copias distintas (o una con GTIN y otra sin), no se sube nada; en precios y
      disponibilidades, lo mismo comparando el registro entero; la tolerancia de productos se mide
      sobre los distintos; y el programa cuadra crudo = sin GTIN + leidas + repetidos, corrigiendo
      el sin GTIN del log (que cuenta las copias).
  (M) NOVEDADES DE FUNKO (encargo H, tramo 1, 29-sep-2026): con la pasada aplicada y releida, UNA llamada a
      nov_seleccionar_pasada; si falla, el run acaba en rojo pero la pasada no se toca, el fallo se apunta
      en nov_pasada sin pisar nada, no se reintenta y lo que viene despues (la caida aceptada) se ejecuta;
      con la pasada rechazada o la descarga cortada, no se llama.
  (N) VALORAR LAS NOVEDADES Y EL VIGIA DE LA MARCA (encargo I, tramo 2, 29-sep-2026): detras de la seleccion, UNA
      llamada al paso de valoracion (escaner2_novedades; con el interruptor apagado solo cierra, sin Keepa); si
      falla, rojo AL FINAL con la pasada y la seleccion intactas; y si la seleccion cuenta marcas parecidas a
      'Funko', rojo al final con MARCA_PARECIDA, despues de haberlo aplicado todo.
  (K) CON LA DESCARGA HEREDADA DE VERDAD (solo su `_get`, la red, cambiado por paginas en memoria, y
      un `requests` de mentira para importarla): el envoltorio de `_paginar` coge las listas que usa
      `descargar_catalogo_heo`, las filas suben marcadas y `_paginar` queda como estaba.
  (Q) CON PRECIO TACHADO, SIN TRAMO (encargo H3, 9-oct-2026): con `strikePricePerUnit` > 0 en /catalog/prices, la fila
      se guarda sin tramo (el precio de hoy, uds 1); vacio, null, 0 o negativo, el tramo como antes; en el programa
      entero, solo cambian las tres columnas de esa fila, y el log da el recuento sin importes. Y la fila de marca
      Funko, tachada o no, tambien sin tramo (revision de Cowork, 9-oct-2026), contada aparte si no venia tachada.
"""
import ast
import os
import subprocess
import sys

import escaner2_motor as e2
import escaner2_disponibilidad as dp

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


M = e2.cargar_motor()


def fila(pn, ean, nombre, marca, precio, estado, disp='GREEN', oferta=''):
    return {'productNumber': pn, 'ean': ean, 'nombre': nombre, 'marca': marca, 'categoria': 'Figuras',
            'precio': precio, 'precio_base': precio, 'en_oferta': oferta, 'campana': '', 'estado': estado,
            'disponibilidad': disp, 'imagen': '', 'fin_de_vida': '', 'preorder': ''}


FILAS = [
    fila('FK67928', '0889698679282', 'Star Wars POP! Vinyl Figura Grogu 9 cm', 'Funko', 8.0, 'disponible'),
    fila('FK67929', '0889698679299', 'Star Wars POP! Vinyl Figura Mando 9 cm', 'Funko', 8.0, 'agotado', 'RED'),
    fila('FK67930', '889698679305 C6', 'Star Wars POP! Vinyl Figura Boba 9 cm (caja de 6)', 'Funko', 48.0, 'disponible'),
    fila('FK67931', '889698679312 Chase', 'Star Wars POP! Vinyl Figura Boba CHASE 9 cm', 'Funko', 15.0, 'disponible'),
    fila('HAS0001', '12345', 'Marvel Legends Figura rara', 'Hasbro', 20.0, 'disponible'),
    fila('HAS0002', '05010993999999', 'Marvel Legends Figura 15 cm', 'Hasbro', 21.0, 'disponible', 'YELLOW'),
    fila('HAS0003', '5010993999990', 'Marvel Legends Figura 15 cm agotada', 'Hasbro', 22.0, 'agotado', 'RED'),
    # 🔑 El MISMO EAN en dos productos de HEO: el barrido se queda con el barato; aqui estan los dos.
    fila('UG00001', '4056133012345', 'Ultimate Guard Fundas 100', 'Ultimate Guard', 5.0, 'disponible', oferta='SI'),
    fila('UG00002', '4056133012345', 'Ultimate Guard Fundas 100 (otra ref.)', 'Ultimate Guard', 6.0, 'disponible'),
]
CHASE = [
    # Caja con chase, GS1 con control valido → figura comun; disponible.
    {'producto_heo': 'FK87245', 'nombre': '*heo Exclusive Edition* One Piece POP!&Buddy Animation Vinyl Figuren Rob Lucci with Hattori w/Chase 10 cm Surtido (6)', 'ean_caja': '01108896988724512110000', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''},
    # Caja con chase, agotada: en la foto del barrido no esta; aqui SI, como agotada.
    {'producto_heo': 'FK86264', 'nombre': 'Sleepy Hollow POP! TV Vinyl Figuren Headless Horseman w/ Chase 9 cm Surtido (6)', 'ean_caja': '889698862646', 'marca': 'Funko', 'precio_caja': 60.0, 'estado': 'agotado', 'imagen': '', 'link_amazon': ''},
    # Sin unidades en el nombre: no es caja, va al flujo normal como figura suelta.
    {'producto_heo': 'FK72611-01', 'nombre': 'Demon Slayer: Kimetsu no Yaiba POP! Animation Vinyl Figuren Susamaru w/Ch 9 cm', 'ean_caja': '889698726115', 'marca': 'Funko', 'precio_caja': 9.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''},
    # Caja con chase de la que no se puede sacar el EAN de la figura (ni GS1 ni EAN, y numero no FK).
    {'producto_heo': 'XX00001', 'nombre': 'Figura rara w/Chase Surtido (6)', 'ean_caja': 'ABC', 'marca': 'Funko', 'precio_caja': 30.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''},
]

# Todos los productos llegaron con precio y con disponibilidad: nadie sin dato (lo de (J) va aparte).
TODOS = {f['productNumber'] for f in FILAS} | {c['producto_heo'] for c in CHASE}
# El listado crudo de products: cada producto una vez, y uno sin GTIN (que no da fila).
NUMEROS = [f['productNumber'] for f in FILAS] + [c['producto_heo'] for c in CHASE] + ['SIN-GTIN']
filas, cuentas = dp.construir_disponibilidad(FILAS, CHASE, M, con_precio=TODOS, con_disponibilidad=TODOS,
                                             numeros_crudos=NUMEROS)
por = {f['producto_prov']: f for f in filas}

# ── (A) TODO ENTRA ───────────────────────────────────────────────────────────────────────
eq('(A) una fila por producto que devuelve la descarga, todas las marcas, disponible o no', sorted(por), sorted(
    [f['productNumber'] for f in FILAS] + [c['producto_heo'] for c in CHASE]))
eq('(A) lo agotado entra, marcado como no disponible', (por['FK67929']['disponible'], por['HAS0003']['disponible'],
                                                        por['FK86264']['disponible']), (False, False, False))
eq('(A) sin filtro de marca: Hasbro y Ultimate Guard dentro', sorted({f['marca'] for f in filas}),
   ['Funko', 'Hasbro', 'Ultimate Guard'])
eq('(A) GREEN/YELLOW/RED se guarda tal cual', (por['HAS0002']['disponibilidad'], por['FK67929']['disponibilidad']), ('YELLOW', 'RED'))

# ── (B) LAS MISMAS REGLAS QUE EL BARRIDO ─────────────────────────────────────────────────
quiere, _info = e2.filtro_todas()
foto, apartados, _c = e2.construir_foto(FILAS, CHASE, quiere, M, modo='todas')
CAMPOS = ('ean_core', 'es_caja', 'uds_caja', 'es_chase', 'precio_catalogo', 'precio_unidad')
distintas = [(f['producto_heo'], k, f[k], por[f['producto_heo']][k]) for f in foto for k in CAMPOS
             if f[k] != por[f['producto_heo']][k]]
eq('(B) cada fila de la foto del barrido sale aquí IGUAL (EAN de cruce, caja, unidades, chase, precios)', distintas, [])
eq('(B) y aquí está disponible y sin regla', sorted((por[f['producto_heo']]['disponible'], por[f['producto_heo']]['regla'])
                                                    for f in foto), [(True, None)] * len(foto))
motivo_de = {a['producto_heo']: a['motivo'] for a in apartados}
en_foto = {f['producto_heo'] for f in foto}
fuera_de_la_foto = sorted(p for p, f in por.items() if f['disponible'] and f['regla'] is None and p not in en_foto)
eq('(B) lo disponible y sin regla que no está en la foto es SOLO lo que el barrido quita por duplicado',
   [(p, motivo_de.get(p)) for p in fuera_de_la_foto], [('UG00002', 'duplicado_proveedor')])
EQUIV = {'chase_suelto': 'chase_suelto', 'ean_forma_rara': 'ean_forma_rara', 'caja_chase_sin_figura': 'chase_funko'}
eq('(B) lo que el barrido aparta, aquí sale con su regla (y la misma)',
   sorted((p, EQUIV[f['regla']]) for p, f in por.items() if f['regla']),
   sorted((p, m) for p, m in motivo_de.items() if m != 'duplicado_proveedor'))
eq('(B) el chase suelto se guarda (con su EAN) y no se tira', (por['FK67931']['regla'], por['FK67931']['ean_core']),
   ('chase_suelto', '889698679312'))
eq('(B) el EAN de forma rara se guarda sin EAN de cruce', (por['HAS0001']['regla'], por['HAS0001']['ean_core']), ('ean_forma_rara', None))
eq('(B) 14 cifras con un 0 delante: se cruza con sus 13 (B6)', por['HAS0002']['ean_core'], '5010993999999')
eq('(B) la caja con chase sin EAN de la figura se guarda, con su aviso', (por['XX00001']['regla'], por['XX00001']['ean_core'],
                                                                           bool(por['XX00001']['aviso'])),
   ('caja_chase_sin_figura', None, True))
eq('(B) la caja con chase: EAN de la figura común (GS1 → interior; el mismo del banco de las cajas)', por['FK87245']['ean_core'], '889698872454')
eq('(B) sin unidades en el nombre: figura suelta por el flujo normal', (por['FK72611-01']['es_caja'], por['FK72611-01']['regla']),
   (False, None))

# ── (C) LA TRAMPA DEL PRECIO DE CAJA ─────────────────────────────────────────────────────
eq('(C) caja con chase: precio de la caja, por unidad y unidades, SEPARADOS',
   (por['FK87245']['precio_catalogo'], por['FK87245']['precio_unidad'], por['FK87245']['uds_caja'], por['FK87245']['es_chase']),
   (60.0, 10.0, 6, True))
eq('(C) caja por sufijo C6: 48 la caja, 8 la unidad', (por['FK67930']['precio_catalogo'], por['FK67930']['precio_unidad'],
                                                        por['FK67930']['uds_caja']), (48.0, 8.0, 6))
eq('(C) lo suelto: sin unidades y el mismo precio', (por['FK67928']['uds_caja'], por['FK67928']['precio_unidad']), (None, 8.0))
eq('(C) la caja agotada también lleva su precio por unidad', por['FK86264']['precio_unidad'], 10.0)

# ── (O) EL EXPOSITOR ES UNA CAJA (encargo T, 30-sep-2026; pendiente del visto bueno de Fernando) ───────────
eq('(O) las unidades del expositor salen del «(N)» final, con la palabra que lo hace caja; sin ella, o con N < 2, no',
   [dp.unidades_expositor(n) for n in (
       'SpongeBob SquarePants Mystery Minis Minifiguras 5 cm Expositor 25th Anniversary (12)',
       '101 dálmatas Mystery Minis Minifiguras 5 cm Expositor PDQ (12)',
       'Fresh Farm Figuras Mini Blind Box Display (8)',
       'tokidoki Cat Frenzies Botanical Lanyard Clips Blind Box Surtido 4 cm (24)',
       'Elder Scrolls Skyrim Baraja de Naipes Caja expositora (12)',
       'Jujutsu Kaisen: Kwistal Fwendz Blind Box Assortment (6)',
       'Dragon Storm Inclusion Pack de Dados Green Dragon (7)',
       'Ultimate Guard Classic Sleeves Japanese Size (100)',
       'Las guerreras K-pop Set de 4 Pósteres Movie Key Art 61 x 91 cm (4)',
       'Star Wars POP! Vinyl Figura Grogu 9 cm',
       'Figuras Surtido 9 cm',
       'Figura Expositor (1)',
       None)],
   [12, 12, 8, 24, 12, 6, None, None, None, None, None, None, None])
EXPO = [
    fila('FK76102', '0889698761024', 'SpongeBob SquarePants Mystery Minis Minifiguras 5 cm Expositor 25th Anniversary (12)',
         'Funko', 60.0, 'disponible'),
    fila('FNRL0007', '5904204651234', 'Dragon Storm Inclusion Pack de Dados Green Dragon (7)', 'FanRoll', 14.0, 'disponible'),
    fila('FK99999', '889698999990 C6', 'Marvel POP! Vinyl Figura 9 cm Expositor (12)', 'Funko', 48.0, 'disponible'),
]
filas_o, _co = dp.construir_disponibilidad(EXPO, [], M, con_precio={f['productNumber'] for f in EXPO},
                                           con_disponibilidad={f['productNumber'] for f in EXPO},
                                           numeros_crudos=[f['productNumber'] for f in EXPO])
por_o = {f['producto_prov']: f for f in filas_o}
eq('(O) 🔴 FK76102: el expositor de 12 es CAJA de 12; el precio del expositor, y el de la unidad, SEPARADOS (60 → 5)',
   (por_o['FK76102']['es_caja'], por_o['FK76102']['uds_caja'], por_o['FK76102']['precio_catalogo'], por_o['FK76102']['precio_unidad'],
    por_o['FK76102']['es_chase']), (True, 12, 60.0, 5.0, False))
eq('(O) «Pack de Dados (7)» sigue siendo UNA cosa: suelta, y su precio tal cual', (por_o['FNRL0007']['es_caja'], por_o['FNRL0007']['uds_caja'],
                                                                                   por_o['FNRL0007']['precio_unidad']), (False, None, 14.0))
eq('(O) con sufijo de caja en el EAN (C6), manda el sufijo, como siempre: caja de 6 aunque el nombre diga (12)',
   (por_o['FK99999']['es_caja'], por_o['FK99999']['uds_caja'], por_o['FK99999']['precio_unidad']), (True, 6, 8.0))
foto_o, _ap, _c = e2.construir_foto(EXPO, [], e2.filtro_todas()[0], M, modo='todas')
eq('(O) 🔑 y es un desvío SOLO de esta foto: el barrido (Escaneo PRO) sigue con la regla heredada y el expositor suelto',
   [(f['producto_heo'], f['es_caja'], f['precio_unidad']) for f in foto_o if f['producto_heo'] == 'FK76102'], [('FK76102', False, 60.0)])


# ── (D) EL CUADRE ────────────────────────────────────────────────────────────────────────
eq('(D) leídas = disponibles + agotados = lo que devolvió descargar_heo',
   (cuentas['n_leidas'], cuentas['n_disponibles'] + cuentas['n_agotados'], cuentas['n_devueltos']), (13, 13, 13))
eq('(D) disponibles y agotados, contados', (cuentas['n_disponibles'], cuentas['n_agotados']), (10, 3))
eq('(D) las reglas, contadas', cuentas['por_regla'], {'chase_suelto': 1, 'ean_forma_rara': 1, 'caja_chase_sin_figura': 1})
eq('(D) las reglas son las que admite la base', dp.REGLAS, ('chase_suelto', 'ean_forma_rara', 'caja_chase_sin_figura'))

# ── (E) LA LLAVE ROTA NO SE SUBE ─────────────────────────────────────────────────────────
for nombre, filas_mal in (('repetido con datos distintos', FILAS + [dict(FILAS[0], nombre='Otro nombre')]),
                          ('sin número', FILAS + [fila('', '0889698000001', 'x', 'Funko', 1.0, 'disponible')])):
    try:
        dp.construir_disponibilidad(filas_mal, CHASE, M, con_precio=TODOS, con_disponibilidad=TODOS,
                                    numeros_crudos=NUMEROS + [FILAS[0]['productNumber']])
        eq('(E) un producto %s tumba la lectura' % nombre, 'pasó', 'LecturaInvalida')
    except dp.LecturaInvalida:
        eq('(E) un producto %s tumba la lectura' % nombre, True, True)

# ── (F) LOS RECUENTOS DEL LOG ────────────────────────────────────────────────────────────
# El log con la forma REAL (lineas copiadas del run 36110259067 del barrido, 25-sep-2026).
LOG = ("  catalog/products: 23608 items | 48 paginas | pageSize 500\n"
       "  catalog/prices: 23049 items | 47 paginas | pageSize 500\n"
       "  catalog/availabilities: 23049 items | 47 paginas | pageSize 500\n"
       ">>> Cruzando: 23608 productos | 23049 precios | 23049 disponibilidades\n"
       ">>> Catalogo cruzado: 22366 filas con EAN (descartadas 1156 sin GTIN)\n")
eq('(F) los siete números del log', dp.recuentos_del_log(LOG),
   {'n_declarado': 23608, 'n_crudo': 23608, 'n_declarado_precios': 23049, 'n_precios': 23049,
    'n_declarado_disponibilidades': 23049, 'n_disponibilidades': 23049, 'n_sin_gtin': 1156})
eq('(F) uno que falta es None, no cero', dp.recuentos_del_log(LOG.splitlines()[3])['n_sin_gtin'], None)

# ── (H) LA DESCARGA CORTADA ──────────────────────────────────────────────────────────────
def rec0(texto):
    """Los recuentos del log, con 0 repetidos (los repetidos salen de las listas crudas, no del log)."""
    return dict(dp.recuentos_del_log(texto), n_duplicados=0)


entera = rec0(LOG)
eq('(H) la descarga del run real está entera', dp.descarga_cortada(entera, 10), [])
cortada = rec0(LOG.replace('23049 disponibilidades', '22549 disponibilidades'))
eq('(H) 🔴 con una página de disponibilidades menos, se dice (y es lo que dejaría 500 agotados falsos)',
   dp.descarga_cortada(cortada, 10), ['disponibilidades: HEO declara 23049 y llegaron 22549 (tolerancia 10)'])
eq('(H) con los precios cortados, también',
   dp.descarga_cortada(rec0(LOG.replace('23049 precios', '23000 precios')), 10),
   ['precios: HEO declara 23049 y llegaron 23000 (tolerancia 10)'])
sin_pag1 = rec0('\n'.join(l for l in LOG.splitlines() if 'catalog/availabilities' not in l))
eq('(H) si la primera página de disponibilidades ni llegó (no hay totalElements), no se da por entera',
   len(dp.descarga_cortada(sin_pag1, 10)) == 1 and dp.descarga_cortada(sin_pag1, 10)[0].startswith('disponibilidades: sin recuento'), True)
eq('(H) sin el recuento de sin GTIN, tampoco', dp.descarga_cortada(dict(entera, n_sin_gtin=None), 10), ['sin GTIN: sin recuento en el log'])
# 🔑 La tolerancia: lo medido el 29-sep (2 precios de menos; 1 producto de MÁS) pasa; 11 y 500, no.
for campo, dif, pasa in (('n_precios', -2, True), ('n_crudo', 1, True), ('n_crudo', -1, True), ('n_disponibilidades', 1, True),
                         ('n_precios', 10, True), ('n_disponibilidades', -10, True), ('n_crudo', 10, True),
                         ('n_crudo', 11, False), ('n_precios', -11, False), ('n_disponibilidades', 11, False),
                         ('n_disponibilidades', -500, False)):
    eq('(H) %s %+d con tolerancia 10: %s' % (campo, dif, 'entera' if pasa else 'cortada'),
       dp.descarga_cortada(dict(entera, **{campo: entera[campo] + dif}), 10) == [], pasa)
eq('(H) los tres a ±10 a la vez: entera',
   dp.descarga_cortada(dict(entera, n_crudo=entera['n_crudo'] + 10, n_precios=entera['n_precios'] - 10,
                            n_disponibilidades=entera['n_disponibilidades'] + 10), 10), [])
eq('(H) con tolerancia 0, uno de diferencia ya es cortada',
   dp.descarga_cortada(dict(entera, n_crudo=entera['n_crudo'] + 1), 0),
   ['productos: HEO declara 23608 y llegaron 23609 (tolerancia 0)'])
# 🔑 La tolerancia de productos, sobre los DISTINTOS: 11 de crudo de más con 11 repetidos es entera;
#    11 de más con 0 repetidos, no; y sin el recuento de repetidos, no se da por entera.
eq('(H) +11 de crudo que son 11 copias repetidas: entera (se mide sobre los distintos)',
   dp.descarga_cortada(dict(entera, n_crudo=entera['n_crudo'] + 11, n_duplicados=11), 10), [])
eq('(H) +11 de crudo sin repetidos: cortada',
   dp.descarga_cortada(dict(entera, n_crudo=entera['n_crudo'] + 11), 10),
   ['productos: HEO declara 23608 y llegaron 23619 (tolerancia 10)'])
eq('(H) 11 distintos de menos con 3 copias repetidas: cortada, y lo dice',
   dp.descarga_cortada(dict(entera, n_crudo=entera['n_crudo'] - 8, n_duplicados=3), 10),
   ['productos: HEO declara 23608 y llegaron 23597 (tolerancia 10) · repetidos aparte: 3'])
eq('(H) sin el recuento de repetidos, no se da por entera',
   dp.descarga_cortada(dict(entera, n_duplicados=None), 10), ['productos: sin recuento de repetidos'])
for mala in (None, -1, True, '10'):
    eq('(H) sin tolerancia válida (%r), no se da por entera' % (mala,),
       dp.descarga_cortada(entera, mala)[0].startswith('sin tolerancia'), True)

# ── (J) SIN DATO NO ES AGOTADO ───────────────────────────────────────────────────────────
# Lo que la heredada da cuando un producto no llegó en availabilities: agotado y sin «GREEN/RED».
FILAS_J = [dict(f, estado='agotado', disponibilidad='') if f['productNumber'] == 'FK67928' else
           (dict(f, precio='', precio_base='') if f['productNumber'] == 'HAS0002' else dict(f)) for f in FILAS]
CHASE_J = [dict(c, estado='agotado') if c['producto_heo'] == 'FK87245' else dict(c) for c in CHASE]
filas_j, cuentas_j = dp.construir_disponibilidad(FILAS_J, CHASE_J, M, numeros_crudos=NUMEROS, con_precio=TODOS - {'HAS0002'},
                                                 con_disponibilidad=TODOS - {'FK67928', 'FK87245'})
por_j = {f['producto_prov']: f for f in filas_j}
eq('(J) sin dato de disponibilidad: el producto normal y la caja con chase, marcados',
   sorted(p for p, f in por_j.items() if f['sin_dato_disponibilidad']), ['FK67928', 'FK87245'])
eq('(J) …y siguen saliendo como la descarga los da (agotados): lo que se conserva lo decide la base',
   (por_j['FK67928']['disponible'], por_j['FK67928']['disponibilidad'], por_j['FK87245']['disponible']), (False, None, False))
eq('(J) sin dato de precio: marcado y sin precio', (sorted(p for p, f in por_j.items() if f['sin_dato_precio']),
                                                    por_j['HAS0002']['precio_catalogo']), (['HAS0002'], None))
eq('(J) los recuentos de sin dato', (cuentas_j['n_sin_dato_disponibilidad'], cuentas_j['n_sin_dato_precio']), (2, 1))
eq('(J) con todo con dato, nadie marcado', (cuentas['n_sin_dato_disponibilidad'], cuentas['n_sin_dato_precio'],
                                            any(f['sin_dato_disponibilidad'] or f['sin_dato_precio'] for f in filas)), (0, 0, False))
try:
    dp.construir_disponibilidad(FILAS, CHASE, M)
    eq('(J) sin los conjuntos de lo que llegó, no se construye', 'pasó', 'TypeError')
except TypeError:
    eq('(J) sin los conjuntos de lo que llegó, no se construye', True, True)

CRUDOS = {'catalog/products': [{'productNumber': 'A'}, {'productNumber': 'B'}, {'productNumber': 'C'}],
          # 🔑 B dos veces (un salto de página): la heredada lo junta en su dict; aquí, el mismo tamaño.
          'catalog/prices': [{'productNumber': 'A'}, {'productNumber': 'B'}, {'productNumber': 'B'}],
          'catalog/availabilities': [{'productNumber': 'A'}, {'productNumber': 'C'}]}
eq('(J) las listas crudas: con precio A y B, con disponibilidad A y C',
   dp.listas_de_los_crudos(CRUDOS, {'n_precios': 2, 'n_disponibilidades': 2}), ({'A', 'B'}, {'A', 'C'}))
for nombre, crudos_mal, rec_mal in (
        ('sin la lista de disponibilidades', {k: v for k, v in CRUDOS.items() if k != 'catalog/availabilities'},
         {'n_precios': 2, 'n_disponibilidades': 2}),
        ('con una lista que no es la que usó la descarga (3 ≠ 2)', CRUDOS, {'n_precios': 3, 'n_disponibilidades': 2}),
        ('sin el recuento del log', CRUDOS, {'n_precios': 2, 'n_disponibilidades': None})):
    try:
        dp.listas_de_los_crudos(crudos_mal, rec_mal)
        eq('(J) %s, no se sigue' % nombre, 'pasó', 'LecturaInvalida')
    except dp.LecturaInvalida:
        eq('(J) %s, no se sigue' % nombre, True, True)

# ── (L) REPETIDOS ────────────────────────────────────────────────────────────────────────
# Idéntico: FK67928 (normal) y FK87245 (caja con chase) dos veces, y el sin GTIN tres veces.
filas_l, cuentas_l = dp.construir_disponibilidad(
    FILAS + [dict(FILAS[0])], CHASE + [dict(CHASE[0])], M, con_precio=TODOS, con_disponibilidad=TODOS,
    numeros_crudos=NUMEROS + ['FK67928', 'FK87245', 'SIN-GTIN', 'SIN-GTIN'])
eq('(L) repetidos idénticos: una fila por producto, y lo mismo que sin repetir',
   (len(filas_l), sorted(f['producto_prov'] for f in filas_l) == sorted(por), filas_l == filas), (13, True, True))
eq('(L) …y se cuentan: 2 con fila y 2 copias del sin GTIN',
   (cuentas_l['n_duplicados_filas'], cuentas_l['n_duplicados_sin_gtin'], cuentas_l['n_leidas'], cuentas_l['n_devueltos']),
   (2, 2, 13, 15))
eq('(L) sin repetidos, 0 y 0', (cuentas['n_duplicados_filas'], cuentas['n_duplicados_sin_gtin']), (0, 0))
for nombre, filas_mal, chase_mal, numeros_mal in (
        ('una copia con otro precio', FILAS + [dict(FILAS[0], precio=9.0)], CHASE, NUMEROS + ['FK67928']),
        ('una copia de la caja con chase con otro estado', FILAS, CHASE + [dict(CHASE[0], estado='agotado')], NUMEROS + ['FK87245']),
        ('dos copias en el listado y una sola fila (la otra sin GTIN)', FILAS, CHASE, NUMEROS + ['FK67928']),
        ('una fila que no está en el listado crudo', FILAS, CHASE, [n for n in NUMEROS if n != 'HAS0003'])):
    try:
        dp.construir_disponibilidad(filas_mal, chase_mal, M, con_precio=TODOS, con_disponibilidad=TODOS, numeros_crudos=numeros_mal)
        eq('(L) %s: no se sube' % nombre, 'pasó', 'LecturaInvalida')
    except dp.LecturaInvalida:
        eq('(L) %s: no se sube' % nombre, True, True)
try:
    dp.construir_disponibilidad(FILAS, CHASE, M, con_precio=TODOS, con_disponibilidad=TODOS)
    eq('(L) sin los números crudos, no se construye', 'pasó', 'TypeError')
except TypeError:
    eq('(L) sin los números crudos, no se construye', True, True)

CRUDOS_L = {'catalog/products': [{'productNumber': 'A'}, {'productNumber': 'B'}, {'productNumber': 'A'}, {'productNumber': 'A'}],
            'catalog/prices': [{'productNumber': 'A', 'p': 1}, {'productNumber': 'A', 'p': 1}],
            'catalog/availabilities': [{'productNumber': 'A', 'd': 'GREEN'}, {'productNumber': 'B'}]}
eq('(L) los repetidos de cada listado crudo, sin problemas', dp.duplicados_de_los_crudos(CRUDOS_L),
   ({'n_duplicados': 2, 'n_duplicados_precios': 1, 'n_duplicados_disponibilidades': 0}, []))
eq('(L) un precio repetido con otro importe: es un problema, y los conteos se devuelven igual (la fallida los guarda)',
   dp.duplicados_de_los_crudos(dict(CRUDOS_L, **{'catalog/prices': [{'productNumber': 'A', 'p': 1}, {'productNumber': 'A', 'p': 2}]})),
   ({'n_duplicados': 2, 'n_duplicados_precios': 1, 'n_duplicados_disponibilidades': 0},
    ['catalog/prices: número(s) de HEO repetidos con datos distintos: A']))
eq('(L) una disponibilidad repetida con otro estado: igual',
   dp.duplicados_de_los_crudos(dict(CRUDOS_L, **{'catalog/availabilities': [
       {'productNumber': 'A', 'd': 'GREEN'}, {'productNumber': 'A', 'd': 'RED'}]}))[1],
   ['catalog/availabilities: número(s) de HEO repetidos con datos distintos: A'])
try:
    dp.duplicados_de_los_crudos({k: v for k, v in CRUDOS_L.items() if k != 'catalog/products'})
    eq('(L) sin el listado de products: no se sigue', 'pasó', 'LecturaInvalida')
except dp.LecturaInvalida:
    eq('(L) sin el listado de products: no se sigue', True, True)
# El sin GTIN, contado una vez desde el listado crudo: A y B con fila; S sin fila 3 veces; T sin fila 1 vez.
eq('(L) sin GTIN desde el listado crudo: 2 productos (S y T), 4 copias (lo que cuenta el log)',
   dp.sin_gtin_de_los_crudos(['A', 'S', 'B', 'S', 'T', 'S', 'A'], [{'productNumber': 'A'}, {'productNumber': 'A'}],
                             [{'producto_heo': 'B'}]), (2, 4))
eq('(L) …y en el catálogo de prueba: el sin GTIN, 1 y 1', dp.sin_gtin_de_los_crudos(NUMEROS, FILAS, CHASE), (1, 1))

# ── (P) LOS TRAMOS DE HEO, EN SOMBRA (encargo H1, 8-oct-2026) ────────────────────────────────
# Precios inventados y redondos. Una fila de disp_lectura de mentira, con lo que lee poner_escalones.
def _fp(pn, hoy, es_caja=False, uds_caja=None):
    pu = None if hoy is None else (hoy / (uds_caja or 6) if es_caja else hoy)
    return {'producto_prov': pn, 'precio_catalogo': hoy, 'precio_unidad': pu, 'es_caja': es_caja,
            'uds_caja': uds_caja if es_caja else None}


def _pc(pn, *tramos):
    """Un producto del listado crudo de products con sus tramos (uds, %)."""
    return {'productNumber': pn, 'prices': {'scaledDiscounts': [{'quantity': q, 'discount': {'amount': a}} for q, a in tramos]}}


def _pb(pn, base):
    return {'productNumber': pn, 'basePricePerUnit': {'amount': base}}


def _esc(f):
    # .get: si la pasada no los pone, el assert sale en rojo con su nombre (y no un KeyError del banco).
    return (None if f.get('precio_escalon') is None else round(f['precio_escalon'], 6), f.get('uds_escalon', 'FALTA'),
            None if f.get('precio_pa') is None else round(f['precio_pa'], 6))


_filas_p = [_fp('P1', 10.0), _fp('P2', 10.0), _fp('P3', 8.5), _fp('P4', 9.5), _fp('P5', 10.0), _fp('P6', 4.99),
            _fp('P7', 60.0, es_caja=True, uds_caja=6), _fp('P8', None), _fp('P9', 10.0), _fp('P10', 10.0), _fp('P11', 10.0)]
_prods_p = [{'productNumber': 'P1', 'prices': {'scaledDiscounts': []}},            # sin tramos
            _pc('P2', (10, 10)),                                                  # 10 % desde 10 sobre la base
            _pc('P3', (10, 10)),                                                  # descuento propio (8,50) y tramo: gana el propio
            _pc('P4', (10, 10)),                                                  # descuento propio (9,50) y tramo: gana el tramo
            _pc('P5', (6, 5), (12, 10), (24, 10)),                                # el MAYOR %; a igual %, el de menos uds
            _pc('P6', (6, 10)),                                                   # redondeo al céntimo: 4,99 × 0,90 = 4,491 → 4,49
            _pc('P7', (2, 10)),                                                   # caja de 6: el tramo, por unidad
            _pc('P8', (10, 10)),                                                  # sin precio de hoy: las tres vacías
            _pc('P9', (10, 0), (5, 100), (0, 10), (3, None)),                    # tramos raros: se ignoran y se cuentan
            _pc('P10', (10, 10)), _pc('P10', (12, 10)),                          # repetido con tramos DISTINTOS: vacías
            _pc('P11', (10, 10)), _pc('P11', (10, 10))]                          # repetido con tramos iguales: vale
_precios_p = [_pb('P1', 10.0), _pb('P2', 10.0), _pb('P3', 10.0), _pb('P4', 10.0), _pb('P5', 10.0), _pb('P6', 4.99),
              _pb('P7', 60.0), _pb('P9', 10.0), _pb('P10', 10.0), _pb('P11', 10.0)]
_cp = dp.poner_escalones(_filas_p, _prods_p, _precios_p, M)
_pp = {f['producto_prov']: f for f in _filas_p}
eq('(P) sin tramos: uds 1 y el precio de hoy (y precio_pa igual)', _esc(_pp['P1']), (10.0, 1, 10.0))
eq('(P) con tramo: el % sobre el precio base (10 × 0,90 = 9), desde 10 uds', _esc(_pp['P2']), (9.0, 10, 9.0))
eq('(P) 🔴 descuento propio (8,50) y tramo del 10 %: gana el propio, SIN acumular (no 7,65)', _esc(_pp['P3']), (8.5, 1, 8.5))
eq('(P) 🔴 descuento propio (9,50) y tramo del 10 %: gana el tramo sobre la BASE (9), SIN acumular (no 8,55)',
   _esc(_pp['P4']), (9.0, 10, 9.0))
eq('(P) varios tramos: el MAYOR % y, a igual %, el de menos unidades (12, no 24)', _esc(_pp['P5']), (9.0, 12, 9.0))
eq('(P) al céntimo, redondeando: 4,99 × 0,90 = 4,491 → 4,49', _esc(_pp['P6']), (4.49, 6, 4.49))
eq('(P) caja de 6 a 60: el tramo sobre la caja (54) y por unidad como precio_unidad (9), desde 2 (cajas)',
   (_esc(_pp['P7']), _pp['P7']['precio_unidad']), ((9.0, 2, 9.0), 10.0))
eq('(P) sin precio de hoy: las tres vacías', _esc(_pp['P8']), (None, None, None))
eq('(P) tramos raros (0 %, 100 %, 0 uds, sin %): se ignoran → el precio de hoy, uds 1', _esc(_pp['P9']), (10.0, 1, 10.0))
eq('(P) 🔴 repetido con tramos DISTINTOS: las tres vacías (no se adivina cuál vale)', _esc(_pp['P10']), (None, None, None))
eq('(P) repetido con tramos iguales: vale', _esc(_pp['P11']), (9.0, 10, 9.0))
eq('(P) las cuentas: con tramo, gana el tramo, raros, dudosos y sin precio', _cp,
   {'n_con_tramo': 9, 'n_escalon_gana': 6, 'n_propio_y_tramo': 2, 'n_tramos_raros': 4, 'n_tramos_dudosos': 1,
    'n_sin_precio': 1, 'n_tachado_sin_tramo': 0, 'n_funko_sin_tramo': 0})
eq('(P) 🔒 la regla de la base: en cada fila, las tres llenas o las tres vacías',
   all((f['precio_escalon'] is None) == (f['uds_escalon'] is None) == (f['precio_pa'] is None) for f in _filas_p), True)
eq('(P) …y solo toca esas tres claves (el resto de la fila, como venía)',
   [sorted(set(f) - {'precio_escalon', 'uds_escalon', 'precio_pa'}) for f in _filas_p[:1]],
   [sorted(_fp('P1', 10.0))])
# Sin base en /catalog/prices (no llegó o vino sin importe): el tramo no se puede calcular → el de hoy.
_f_sinbase = [_fp('PB', 10.0)]
dp.poner_escalones(_f_sinbase, [_pc('PB', (10, 10))], [{'productNumber': 'PB'}], M)
eq('(P) sin precio base: el de hoy, uds 1', _esc(_f_sinbase[0]), (10.0, 1, 10.0))
# El caso del encargo T, con números REDONDOS en lugar de los reales: base 5, 10 % desde 10 → 4,50.
_f_caso = [_fp('UGD-DE-MENTIRA', 5.0)]
dp.poner_escalones(_f_caso, [_pc('UGD-DE-MENTIRA', (10, 10), (10, 10))], [_pb('UGD-DE-MENTIRA', 5.0)], M)
eq('(P) dos tramos iguales en el mismo producto (como trae HEO uno de verdad): 10 % desde 10', _esc(_f_caso[0]), (4.5, 10, 4.5))

# ── (Q) CON PRECIO TACHADO, SIN TRAMO (encargo H3, 9-oct-2026) ──────────────────────────────
# Lo rebajado no tiene descuento por cantidad: si /catalog/prices trae `strikePricePerUnit` con importe > 0, el tramo
# de la API no vale. Códigos e importes inventados: base 10 y 10 % desde 10 (→ 9) salvo que se diga otra cosa.
def _pt(pn, base, strike=..., campo='strikePricePerUnit'):
    """Un registro de /catalog/prices con su base y, si se da, el tachado tal cual (dict, None o lo que sea)."""
    r = _pb(pn, base)
    if strike is not ...:
        r[campo] = strike
    return r


_filas_q = [_fp('Q1', 10.0), _fp('Q2', 10.0), _fp('Q3', 10.0), _fp('Q4', 10.0), _fp('Q5', 10.0), _fp('Q6', 10.0),
            _fp('Q7', 10.0), _fp('Q8', 8.5), _fp('Q9', 10.0), _fp('Q10', 10.0), _fp('Q11', 60.0, es_caja=True, uds_caja=6),
            _fp('Q12', 10.0), _fp('Q13', 10.0), _fp('Q14', None), _fp('Q15', 10.0)]
_prods_q = [_pc(pn, (10, 10)) for pn in ('Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'Q10', 'Q12', 'Q13', 'Q14')] + [
    {'productNumber': 'Q9', 'prices': {'scaledDiscounts': []}},                    # tachado y sin tramo
    _pc('Q11', (2, 10)),                                                         # caja tachada
    _pc('Q15', (10, 10)), _pc('Q15', (12, 10))]                                  # tachado y repetido con tramos distintos
_precios_q = [_pt('Q1', 10.0, {'amount': 12.0, 'currencyIsoCode': 'EUR'}),      # tachado
              _pt('Q2', 10.0),                                                   # sin la clave
              _pt('Q3', 10.0, None),                                             # null
              _pt('Q4', 10.0, {'amount': 0}),                                    # 0
              _pt('Q5', 10.0, {'amount': None}),                                 # sin importe
              _pt('Q6', 10.0, {'amount': '0,00'}),                               # 0 en texto
              _pt('Q7', 10.0, {'amount': '12,50'}),                              # tachado en texto
              _pt('Q8', 10.0, {'amount': 12.0}),                                 # tachado con descuento propio (8,50)
              _pt('Q9', 10.0, {'amount': 12.0}),
              _pt('Q10', 10.0, {'amount': 12.0}, campo='discountedStrikePricePerUnit'),  # otro campo: no cuenta
              _pt('Q11', 60.0, {'amount': 72.0}),
              _pt('Q12', 10.0, {'amount': 12.0}), _pt('Q12', 10.0),             # repetido: una copia tachada (la 1.ª)
              _pt('Q13', 10.0, {'amount': -1}),                                  # negativo: no es > 0
              _pt('Q14', 10.0, {'amount': 12.0}),                                # tachado y sin precio de hoy
              _pt('Q15', 10.0, {'amount': 12.0})]
_cq = dp.poner_escalones(_filas_q, _prods_q, _precios_q, M)
_pq = {f['producto_prov']: f for f in _filas_q}
eq('(Q) 🔴 con tachado > 0 y tramo: SIN tramo, el precio de hoy y uds 1 (no 9 desde 10)', _esc(_pq['Q1']), (10.0, 1, 10.0))
eq('(Q) sin strikePricePerUnit y con tramo: el tramo, como hoy', _esc(_pq['Q2']), (9.0, 10, 9.0))
eq('(Q) tachado null, 0, sin importe o «0,00»: como sin tachado, con su tramo',
   [_esc(_pq[pn]) for pn in ('Q3', 'Q4', 'Q5', 'Q6')], [(9.0, 10, 9.0)] * 4)
eq('(Q) tachado en texto con coma («12,50»): cuenta como tachado, sin tramo', _esc(_pq['Q7']), (10.0, 1, 10.0))
eq('(Q) tachado con descuento propio (8,50): el de hoy, sin tramo', _esc(_pq['Q8']), (8.5, 1, 8.5))
eq('(Q) tachado y sin tramo en la API: el de hoy, como cualquiera sin tramo', _esc(_pq['Q9']), (10.0, 1, 10.0))
eq('(Q) el tachado es el de strikePricePerUnit: uno en discountedStrikePricePerUnit no quita el tramo',
   _esc(_pq['Q10']), (9.0, 10, 9.0))
eq('(Q) caja tachada: su precio por unidad de hoy (10) y uds 1, no el tramo (9 desde 2)', _esc(_pq['Q11']), (10.0, 1, 10.0))
eq('(Q) repetido en precios con una copia tachada: sin tramo (lo prudente)', _esc(_pq['Q12']), (10.0, 1, 10.0))
eq('(Q) tachado negativo: no es > 0, el tramo como hoy', _esc(_pq['Q13']), (9.0, 10, 9.0))
eq('(Q) tachado y sin precio de hoy, o repetido con tramos distintos: las tres vacías, como antes',
   [_esc(_pq[pn]) for pn in ('Q14', 'Q15')], [(None, None, None)] * 2)
eq('(Q) las cuentas: 5 con tramo y tachado se guardan sin tramo (Q1, Q7, Q8, Q11, Q12; no Q9, sin tramo, ni Q14 y Q15, '
   'vacías), el tramo gana en los 7 sin tachado, y Q8 (tachado) no cuenta como descuento propio y tramo',
   _cq, {'n_con_tramo': 14, 'n_escalon_gana': 7, 'n_propio_y_tramo': 0, 'n_tramos_raros': 0, 'n_tramos_dudosos': 1,
         'n_sin_precio': 1, 'n_tachado_sin_tramo': 5, 'n_funko_sin_tramo': 0})
eq('(Q) 🔒 la regla de la base, también con tachado: las tres llenas o las tres vacías',
   all((f['precio_escalon'] is None) == (f['uds_escalon'] is None) == (f['precio_pa'] is None) for f in _filas_q), True)

# (Q) FUNKO, SIN TRAMO (revisión de Cowork al H3): en la web de HEO ningún Funko tiene descuento por cantidad, tampoco
#     los que vienen sin tachado. La marca sale de la propia fila. Códigos e importes inventados, como arriba.
def _fm(pn, hoy, marca, **k):
    return dict(_fp(pn, hoy, **k), marca=marca)


_filas_f = [_fm('QF1', 10.0, 'Funko'), _fm('QF2', 10.0, ' FUNKO '), _fm('QF3', 10.0, 'Funko'), _fm('QF4', 10.0, 'Funko'),
            _fm('QF5', 60.0, 'Funko', es_caja=True, uds_caja=6), _fm('QF6', 10.0, 'Funko Europe'),
            _fm('QF7', 10.0, 'Hasbro'), _fm('QF8', 10.0, None)]
_prods_f = [_pc(pn, (10, 10)) for pn in ('QF1', 'QF2', 'QF3', 'QF6', 'QF7', 'QF8')] + [
    {'productNumber': 'QF4', 'prices': {'scaledDiscounts': []}}, _pc('QF5', (2, 10))]
_precios_f = [_pt('QF1', 10.0), _pt('QF2', 10.0), _pt('QF3', 10.0, {'amount': 12.0}), _pt('QF4', 10.0), _pt('QF5', 60.0),
              _pt('QF6', 10.0), _pt('QF7', 10.0), _pt('QF8', 10.0)]
_cf = dp.poner_escalones(_filas_f, _prods_f, _precios_f, M)
_pf = {f['producto_prov']: f for f in _filas_f}
eq('(Q) 🔴 Funko sin tachado y con tramo: SIN tramo, el de hoy y uds 1 (no 9 desde 10)', _esc(_pf['QF1']), (10.0, 1, 10.0))
eq('(Q) la marca, sin distinguir mayúsculas ni espacios de los lados (« FUNKO »): sin tramo', _esc(_pf['QF2']), (10.0, 1, 10.0))
eq('(Q) Funko y tachado: sin tramo, y cuenta como tachado (no como Funko)', _esc(_pf['QF3']), (10.0, 1, 10.0))
eq('(Q) caja de Funko con tramo: su precio por unidad (10) y uds 1', _esc(_pf['QF5']), (10.0, 1, 10.0))
eq('(Q) una marca parecida y distinta («Funko Europe»), Hasbro o sin marca: el tramo, como hoy',
   [_esc(_pf[pn]) for pn in ('QF6', 'QF7', 'QF8')], [(9.0, 10, 9.0)] * 3)
eq('(Q) las cuentas de Funko: 3 sin tramo solo por la marca (QF1, QF2, la caja QF5), 1 tachado (QF3); QF4 sin tramo en '
   'la API no cuenta; el tramo gana en los 3 que no son Funko',
   _cf, {'n_con_tramo': 7, 'n_escalon_gana': 3, 'n_propio_y_tramo': 0, 'n_tramos_raros': 0, 'n_tramos_dudosos': 0,
         'n_sin_precio': 0, 'n_tachado_sin_tramo': 1, 'n_funko_sin_tramo': 3})

# ── (G) EL PROGRAMA Y EL WORKFLOW, POR ESTRUCTURA ────────────────────────────────────────
AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), encoding='utf-8') as fh:
    arbol = ast.parse(fh.read())
tablas, funciones = set(), set()
for nodo in ast.walk(arbol):
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in ('table', 'rpc') and nodo.args:
        a = nodo.args[0]
        (tablas if nodo.func.attr == 'table' else funciones).add(a.value if isinstance(a, ast.Constant) else '<no literal>')
eq('(G) el programa solo toca disp_pasada y disp_lectura, lee disp_parametros y apunta en nov_pasada (ni escaner_memoria, ni escaner2_*, ni productos)',
   sorted(tablas), ['disp_lectura', 'disp_parametros', 'disp_pasada', 'nov_pasada'])
acciones_parametros = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Call)
                       and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'table'
                       and n.value.args and isinstance(n.value.args[0], ast.Constant) and n.value.args[0].value == 'disp_parametros'}
eq('(G) …y a disp_parametros solo le hace select', acciones_parametros, {'select'})
acciones_nov = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'table'
                and n.value.args and isinstance(n.value.args[0], ast.Constant) and n.value.args[0].value == 'nov_pasada'}
eq('(G) …y en nov_pasada solo apunta un fallo (upsert que no pisa)', acciones_nov, {'upsert'})
with open(os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), encoding='utf-8') as fh:
    _prog = fh.read()
eq('(G) la heredada no se escribe: solo se envuelve su _paginar en memoria y se deja como estaba (y el programa no abre ficheros)',
   ("hd._paginar = _paginar_que_guarda" in _prog, "hd._paginar = paginar" in _prog,
    any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'open' for n in ast.walk(arbol))),
   (True, True, False))
eq('(G) y solo llama a las funciones disp_aplicar_pasada y nov_seleccionar_pasada', sorted(funciones),
   ['disp_aplicar_pasada', 'nov_seleccionar_pasada'])
env = {k: v for k, v in os.environ.items() if k not in ('SUPABASE_SERVICE_KEY', 'HEO_USER', 'HEO_PASS')}
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run([sys.executable, os.path.join(AQUI, 'escaner2_heo_disponibilidad.py')], capture_output=True, text=True,
                   encoding='utf-8', env=env, cwd=AQUI)
eq('(G) sin la llave de servicio aborta en rojo antes de abrir ningún cliente',
   (r.returncode, r.stdout.strip()), (1, 'DISPONIBILIDAD_NO_EJECUTADA: sin llave de servicio'))
r = subprocess.run([sys.executable, os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), '--otra-cosa'], capture_output=True,
                   text=True, encoding='utf-8', env=env, cwd=AQUI)
eq('(G) un argumento desconocido: no corre', r.returncode, 1)

with open(os.path.join(AQUI, '.github', 'workflows', 'escaner2-heo-disponibilidad.yml'), encoding='utf-8') as fh:
    lineas = [l for l in fh.read().splitlines() if not l.lstrip().startswith('#')]
eq('(G) el workflow se lanza a mano', any(l.strip() == 'workflow_dispatch:' for l in lineas), True)
eq('(G) y NO lleva reloj de GitHub (el reloj es cron-job.org, con Fernando delante)',
   any(l.strip().startswith('schedule:') for l in lineas), False)
eq('(G) comparte grupo con el barrido y el cruce (no baja HEO dos veces a la vez), sin cancelar lo que corre',
   ([l.strip() for l in lineas if l.strip().startswith('group:')], [l.strip() for l in lineas if 'cancel-in-progress' in l]),
   (['group: escaner2-heo'], ['cancel-in-progress: false']))
for _wf in ('escaner2-heo-barrido.yml', 'escaner2-heo-cruce.yml'):
    with open(os.path.join(AQUI, '.github', 'workflows', _wf), encoding='utf-8') as fh:
        eq('(G) …y es de verdad el grupo de %s' % _wf,
           [l.strip() for l in fh.read().splitlines() if l.strip().startswith('group:')], ['group: escaner2-heo'])
i_perm = [i for i, l in enumerate(lineas) if l.strip() == 'permissions:']
eq('(G) solo lee el repo: un bloque permissions con contents: read y nada más',
   (len(i_perm), lineas[i_perm[0] + 1].strip() if i_perm else None,
    lineas[i_perm[0] + 2].strip().startswith(('timeout-minutes:', 'steps:')) if i_perm else None),
   (1, 'contents: read', True))
eq('(G) corre este programa, y el rescate si falla',
   [l.strip() for l in lineas if l.strip().startswith('run: python')],
   ['run: python -u escaner2_heo_disponibilidad.py', 'run: python -u escaner2_heo_disponibilidad.py --rescate'])

# ── (I) EL PROGRAMA ENTERO, CON UNA BASE Y UN HEO DE MENTIRA ────────────────────────────
import importlib
import io as _io
import types
from contextlib import redirect_stdout as _redirigir


class _Consulta:
    """Una consulta de supabase-py de mentira: apunta que se pidio y a que tabla."""

    def __init__(self, base, tabla):
        self.base, self.op = base, {'tabla': tabla}

    def _accion(self, nombre, datos=None):
        self.op.update(accion=nombre, datos=datos)
        return self

    def insert(self, datos):
        return self._accion('insert', datos)

    def update(self, datos):
        return self._accion('update', datos)

    def delete(self):
        return self._accion('delete')

    def upsert(self, datos, **opciones):
        self.op['opciones'] = opciones
        return self._accion('upsert', datos)

    def select(self, *_a, **_k):
        return self._accion('select', _a)

    def eq(self, *args):
        self.op.setdefault('filtros', []).append(args)
        return self

    def execute(self):
        self.base.ops.append(self.op)
        if (self.op['tabla'], self.op['accion']) in self.base.fallan:
            raise RuntimeError('la base de mentira falla en %s %s' % (self.op['tabla'], self.op['accion']))
        datos = []
        if self.op['tabla'] == 'disp_pasada' and self.op['accion'] == 'insert':
            datos = [{'id': 'PASADA-1'}]
        elif self.op['tabla'] == 'disp_pasada' and self.op['accion'] == 'select':
            datos = [self.base.fila_final]
        elif self.op['tabla'] == 'disp_parametros' and self.op['accion'] == 'select':
            datos = self.base.parametros
        elif self.op['tabla'] == 'nov_parametros' and self.op['accion'] == 'select':
            datos = self.base.nov_parametros
        return types.SimpleNamespace(data=datos)


class _BaseDeMentira:
    def __init__(self):
        self.ops = []
        self.fila_final = dict({k: 0 for k in (
            'primera', 'n_crudo', 'n_leidas', 'n_disponibles', 'n_agotados', 'n_entran', 'n_vuelven', 'n_salen',
            'n_a_disponible', 'n_a_agotado', 'n_cambio_precio', 'n_ausentes', 'n_en_catalogo',
            'n_disponibles_estado', 'dif_productos', 'dif_precios', 'dif_disponibilidades', 'n_sin_dato_disponibilidad',
            'n_sin_dato_precio', 'n_duplicados', 'n_sin_gtin', 'n_agotados_sin_dato', 'n_recuperan_dato')},
                               estado='aplicada', motivo=None, caida_aceptada=False)
        self.parametros = [{'tolerancia_endpoint': 10}]
        # (N) El interruptor de la valoración, APAGADO (como nace), y el vigía de la marca a 0.
        self.nov_parametros = [{'proveedor': 'HEO', 'valorar': False}]
        self.marca_parecida = 0
        # Lo que falla a propósito: ('rpc:<función>', 'rpc') o (tabla, acción).
        self.fallan = set()

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, params):
        base = self

        class _Llamada:
            def execute(self):
                base.ops.append({'tabla': 'rpc:' + nombre, 'accion': 'rpc', 'datos': params})
                if ('rpc:' + nombre, 'rpc') in base.fallan:
                    raise RuntimeError('APIError de mentira en ' + nombre)
                if nombre == 'nov_seleccionar_pasada':
                    return types.SimpleNamespace(data={'estado': 'hecha', 'marca_parecida': base.marca_parecida})
                if nombre == 'nov_cerrar_valoracion':
                    return types.SimpleNamespace(data={'estado': 'apagada' if params['p_datos'].get('estado') == 'apagada'
                                                       else params['p_datos'].get('estado')})
                return types.SimpleNamespace(data={'estado': 'aplicada' if nombre == 'disp_aplicar_pasada' else 'hecha'})
        return _Llamada()


def correr_programa(disponibilidades_declaradas=None, sin_dispo=(), sin_precio=(), parametros=None, caida=False,
                    modulo_descarga=None, repetir=(), repetir_distinto=(), sin_gtin_copias=1, precio_repetido_distinto=(),
                    fallan=(), estado_final=None, marca_parecida=0, tramos=None, bases=None, tachados=None):
    """El programa de verdad, importado con `supabase` y la descarga heredada cambiados por dobles. La
    descarga de mentira hace como la de verdad: pide cada endpoint a SU `_paginar` (buscándolo en su
    módulo en cada llamada), junta por número y dice en el log lo declarado y lo llegado. Los de
    `sin_dispo` / `sin_precio` no vienen en esa lista (y salen agotados / sin precio, como en la
    heredada). Los de `repetir` vienen DOS veces en products (idénticos); los de `repetir_distinto`,
    dos veces y la segunda con otro nombre; el sin GTIN, `sin_gtin_copias` veces; y los de
    `precio_repetido_distinto`, dos veces en prices con otro importe. Lo declarado de products es lo
    DISTINTO (como HEO). (H1) `tramos` = {número: [(uds, %)]} van en products, como `prices.scaledDiscounts`, y
    `bases` = {número: euros} en prices, como `basePricePerUnit`; (H3) `tachados` = {número: euros} en prices, como
    `strikePricePerUnit`."""
    base = _BaseDeMentira()
    if parametros is not None:
        base.parametros = parametros
    if caida:
        base.fila_final.update(caida_aceptada=True, motivo='caída aceptada tras 3 rechazos estables (±2.0 %): …')
    if estado_final:
        base.fila_final.update(estado=estado_final, motivo='rechazada de mentira')
    base.fallan = set(fallan)
    base.marca_parecida = marca_parecida
    falso_supabase = types.ModuleType('supabase')
    falso_supabase.create_client = lambda url, llave: base
    falsa_descarga = types.ModuleType('escaner2_heredado_descarga')
    numeros = [f['productNumber'] for f in FILAS] + [c['producto_heo'] for c in CHASE]
    tramos, bases, tachados = tramos or {}, bases or {}, tachados or {}

    def _producto(pn):
        if pn not in tramos:
            return {'productNumber': pn}
        return {'productNumber': pn, 'prices': {'scaledDiscounts': [{'quantity': q, 'discount': {'amount': a}}
                                                                    for q, a in tramos[pn]]}}

    def _precio_crudo(pn):
        return {'productNumber': pn, **({'basePricePerUnit': {'amount': bases[pn]}} if pn in bases else {}),
                **({'strikePricePerUnit': {'amount': tachados[pn]}} if pn in tachados else {})}
    listas = {'catalog/products': [_producto(pn) for pn in numeros + list(repetir) + list(repetir_distinto)]
                                  + [{'productNumber': 'SIN-GTIN'}] * sin_gtin_copias,
              'catalog/prices': [_precio_crudo(pn) for pn in numeros if pn not in sin_precio]
                                + [{'productNumber': pn, 'otro': 1} for pn in precio_repetido_distinto],
              'catalog/availabilities': [{'productNumber': pn} for pn in numeros if pn not in sin_dispo]}
    por_numero = {f['productNumber']: ('fila', f) for f in FILAS}
    por_numero.update({c['producto_heo']: ('chase', c) for c in CHASE})

    def _paginar(endpoint, max_paginas=None):
        return listas[endpoint]

    def descargar_catalogo_heo(con_chase=False):
        productos = falsa_descarga._paginar('catalog/products')
        precios = {p['productNumber']: p for p in falsa_descarga._paginar('catalog/prices')}
        dispo = {a['productNumber']: a for a in falsa_descarga._paginar('catalog/availabilities')}
        declaradas = len(dispo) if disponibilidades_declaradas is None else disponibilidades_declaradas
        print('  catalog/products: %d items | 1 paginas | pageSize 500' % len({x['productNumber'] for x in productos}))
        print('  catalog/prices: %d items | 1 paginas | pageSize 500' % len(precios))
        print('  catalog/availabilities: %d items | 1 paginas | pageSize 500' % declaradas)
        print('>>> Cruzando: %d productos | %d precios | %d disponibilidades' % (len(productos), len(precios), len(dispo)))
        # Como la heredada: una fila por cada entrada del listado (también las repetidas).
        filas_d, chase_d, vistos, sin_ean = [], [], set(), 0
        for x in productos:
            pn = x['productNumber']
            if pn == 'SIN-GTIN':
                sin_ean += 1
                continue
            clase, r = por_numero[pn]
            segunda = pn in vistos
            vistos.add(pn)
            if clase == 'fila':
                filas_d.append(dict(r, **({'estado': 'agotado', 'disponibilidad': ''} if pn not in dispo else {}),
                                    **({'precio': '', 'precio_base': ''} if pn not in precios else {}),
                                    **({'nombre': r['nombre'] + ' (otra)'} if segunda and pn in repetir_distinto else {})))
            else:
                chase_d.append(dict(r, **({'estado': 'agotado'} if pn not in dispo else {}),
                                    **({'precio_caja': None} if pn not in precios else {}),
                                    **({'nombre': r['nombre'] + ' (otra)'} if segunda and pn in repetir_distinto else {})))
        print('>>> Catalogo cruzado: %d filas con EAN (descartadas %d sin GTIN)' % (len(filas_d), sin_ean))
        return filas_d, chase_d
    falsa_descarga._paginar = _paginar
    falsa_descarga.descargar_catalogo_heo = descargar_catalogo_heo

    modulos = ('supabase', 'escaner2_heredado_descarga', 'escaner2_heo_disponibilidad')
    guardado = {k: sys.modules.get(k) for k in modulos}
    variables = ('SUPABASE_URL', 'SUPABASE_SERVICE_KEY', 'HEO_USER', 'HEO_PASS', 'GITHUB_RUN_ID')
    entorno = {k: os.environ.get(k) for k in variables}
    sys.modules['supabase'], sys.modules['escaner2_heredado_descarga'] = falso_supabase, modulo_descarga or falsa_descarga
    sys.modules.pop('escaner2_heo_disponibilidad', None)
    os.environ.update(SUPABASE_URL='https://ejemplo.invalid', SUPABASE_SERVICE_KEY='llave-de-mentira',
                      HEO_USER='u', HEO_PASS='p', GITHUB_RUN_ID='123')
    salida, codigo = _io.StringIO(), 0
    try:
        with _redirigir(salida):
            prog = importlib.import_module('escaner2_heo_disponibilidad')
            try:
                prog.main()
            except SystemExit as ex:
                codigo = ex.code
    finally:
        for k, v in guardado.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for k, v in entorno.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    correr_programa.paginar_despues = falsa_descarga._paginar is _paginar
    return base.ops, codigo, salida.getvalue()


def _de(ops, tabla, accion):
    return [o for o in ops if o['tabla'] == tabla and o['accion'] == accion]


N_TOTAL = len(FILAS) + len(CHASE)
# 🔴 Una página perdida: HEO declara 13 + 11 disponibilidades y llegan 13 (más que la tolerancia de 10).
ops, codigo, _texto = correr_programa(disponibilidades_declaradas=N_TOTAL + 11)
eq('(I) 🔴 con las disponibilidades cortadas (11 de más que la tolerancia), el run sale en ROJO', codigo, 1)
eq('(I) …NO sube ni una fila a disp_lectura', _de(ops, 'disp_lectura', 'insert'), [])
eq('(I) …y NO llama a la función de la base', [o for o in ops if o['tabla'].startswith('rpc:')], [])
ultima = _de(ops, 'disp_pasada', 'update')[-1]['datos']
eq('(I) …la pasada queda fallida y el motivo dice qué endpoint y la tolerancia',
   (ultima['estado'], 'disponibilidades: HEO declara 24 y llegaron 13 (tolerancia 10)' in ultima['motivo']), ('fallida', True))
subidos = _de(ops, 'disp_pasada', 'update')[0]['datos']
eq('(I) …con sus recuentos subidos antes (también una fallida los necesita)',
   (subidos['n_declarado_disponibilidades'], subidos['n_disponibilidades'], subidos['n_declarado'], subidos['n_crudo']),
   (24, 13, 14, 14))
eq('(I) …la tolerancia se lee de disp_parametros, de HEO',
   [(o['datos'], o.get('filtros')) for o in _de(ops, 'disp_parametros', 'select')], [(('tolerancia_endpoint',), [('proveedor', 'HEO')])])
eq('(I) …y el _paginar de la heredada queda como estaba', correr_programa.paginar_despues, True)

ops, codigo, _texto = correr_programa()
eq('(I) con la descarga entera, termina bien', codigo, 0)
eq('(I) …sube lo leído (13 filas)', sum(len(o['datos']) for o in _de(ops, 'disp_lectura', 'insert')), 13)
eq('(I) …llama UNA vez a disp_aplicar_pasada con su pasada, después UNA a nov_seleccionar_pasada y, con la valoración '
   'APAGADA, solo la cierra (N)',
   [(o['tabla'], o['datos']) for o in ops if o['tabla'].startswith('rpc:')],
   [('rpc:disp_aplicar_pasada', {'p_pasada': 'PASADA-1'}), ('rpc:nov_seleccionar_pasada', {'p_pasada': 'PASADA-1'}),
    ('rpc:nov_cerrar_valoracion', {'p_pasada': 'PASADA-1', 'p_datos': {'estado': 'apagada'}})])
eq('(M) …con la selección bien, no apunta nada en nov_pasada y el log la dice',
   (_de(ops, 'nov_pasada', 'upsert'), '>>> NOVEDADES DE FUNKO:' in _texto), ([], True))
eq('(I) …y relee la pasada en la base', [o['accion'] for o in ops if o['tabla'] == 'disp_pasada'][-1], 'select')
eq('(I) …y el _paginar de la heredada queda como estaba', correr_programa.paginar_despues, True)

# 🔑 Dentro de la tolerancia y con sin dato: FK67928 y la caja FK87245 no llegan en availabilities
#    (HEO declara 12 y llegan 11), y HAS0002 no llega en prices.
ops, codigo, _texto = correr_programa(disponibilidades_declaradas=N_TOTAL - 1, sin_dispo={'FK67928', 'FK87245'},
                                      sin_precio={'HAS0002'})
eq('(I) sin dato y dentro de la tolerancia (declara 12, llegan 11): termina bien', codigo, 0)
lectura = [f for o in _de(ops, 'disp_lectura', 'insert') for f in o['datos']]
eq('(I) …las filas suben marcadas: sin disponibilidad FK67928 y la caja FK87245; sin precio HAS0002',
   (sorted(f['producto_prov'] for f in lectura if f['sin_dato_disponibilidad']),
    sorted(f['producto_prov'] for f in lectura if f['sin_dato_precio'])), (['FK67928', 'FK87245'], ['HAS0002']))
cuentas_subidas = next((o['datos'] for o in _de(ops, 'disp_pasada', 'update') if 'n_leidas' in o['datos']), {})
eq('(I) …y la pasada con sus recuentos de sin dato',
   (cuentas_subidas.get('n_sin_dato_disponibilidad'), cuentas_subidas.get('n_sin_dato_precio'), cuentas_subidas.get('n_leidas')), (2, 1, 13))
eq('(I) …el log lo dice', 'sin dato de disponibilidad 2, de precio 1' in _texto, True)

# 🔑 REPETIDOS en el programa entero: FK67928 y la caja FK87245 dos veces (idénticas) y el sin GTIN
#    tres veces → se aplica, sube 13 filas, 4 repetidos, sin GTIN 1 (no 3) y el cuadre.
ops, codigo, _texto = correr_programa(repetir=('FK67928', 'FK87245'), sin_gtin_copias=3)
eq('(I) con repetidos idénticos, termina bien', codigo, 0)
eq('(I) …sube una fila por producto (13)', sum(len(o['datos']) for o in _de(ops, 'disp_lectura', 'insert')), 13)
primeros = _de(ops, 'disp_pasada', 'update')[0]['datos']
eq('(I) …la pasada lleva sus repetidos y el crudo con ellos: 18 = 1 sin GTIN + 13 leídas + 4 repetidos',
   (primeros['n_duplicados'], primeros['n_duplicados_precios'], primeros['n_duplicados_disponibilidades'], primeros['n_crudo'],
    primeros['n_declarado']), (4, 0, 0, 18, 14))
eq('(I) …y el sin GTIN, contado UNA vez desde el PRIMER guardado (el log contó sus 3 copias)', primeros['n_sin_gtin'], 1)
eq('(I) …y ningún guardado posterior lo cambia', [o['datos']['n_sin_gtin'] for o in _de(ops, 'disp_pasada', 'update')
                                                   if 'n_sin_gtin' in o['datos']], [1])

ops, codigo, _texto = correr_programa(repetir_distinto=('FK67928',), sin_gtin_copias=3)
eq('(I) 🔴 un repetido con copias DISTINTAS: rojo, sin subir nada ni llamar a la función',
   (codigo, _de(ops, 'disp_lectura', 'insert'), [o for o in ops if o['tabla'].startswith('rpc:')]), (1, [], []))
eq('(I) …y la pasada fallida lo dice', ('repetidos con datos distintos: FK67928' in _de(ops, 'disp_pasada', 'update')[-1]['datos'].get('motivo', ''),
                                        _de(ops, 'disp_pasada', 'update')[-1]['datos'].get('estado')), (True, 'fallida'))
eq('(I) …y la fallida guarda sus recuentos con el sin GTIN ya contado una vez (el log contó 3 copias)',
   {k: _de(ops, 'disp_pasada', 'update')[0]['datos'].get(k) for k in ('n_crudo', 'n_duplicados', 'n_sin_gtin')},
   {'n_crudo': 17, 'n_duplicados': 3, 'n_sin_gtin': 1})

ops, codigo, _texto = correr_programa(precio_repetido_distinto=('HAS0002',))
eq('(I) 🔴 un precio repetido con otro importe: rojo, sin subir nada ni llamar a la función',
   (codigo, _de(ops, 'disp_lectura', 'insert'), [o for o in ops if o['tabla'].startswith('rpc:')],
    'catalog/prices: número(s) de HEO repetidos con datos distintos: HAS0002' in _de(ops, 'disp_pasada', 'update')[-1]['datos'].get('motivo', '')),
   (1, [], [], True))
eq('(I) …y la fallida guarda ANTES sus recuentos crudos y sus repetidos (1 de precios)',
   {k: _de(ops, 'disp_pasada', 'update')[0]['datos'].get(k) for k in
    ('n_declarado', 'n_crudo', 'n_precios', 'n_disponibilidades', 'n_sin_gtin', 'n_duplicados', 'n_duplicados_precios',
     'n_duplicados_disponibilidades')},
   {'n_declarado': 14, 'n_crudo': 14, 'n_precios': 13, 'n_disponibilidades': 13, 'n_sin_gtin': 1, 'n_duplicados': 0,
    'n_duplicados_precios': 1, 'n_duplicados_disponibilidades': 0})

ops, codigo, _texto = correr_programa(parametros=[])
eq('(I) 🔴 sin tolerancia en la base: rojo, sin bajar nada de HEO ni subir nada',
   (codigo, _de(ops, 'disp_lectura', 'insert'), 'Bajando' in _texto or 'catalog/products' in _texto), (1, [], False))
eq('(I) …y la pasada queda fallida diciendo por qué',
   (_de(ops, 'disp_pasada', 'update')[-1]['datos'].get('estado'), 'sin tolerancia' in _de(ops, 'disp_pasada', 'update')[-1]['datos'].get('motivo', '')),
   ('fallida', True))

ops, codigo, _texto = correr_programa(caida=True)
eq('(I) 🔴 una CAÍDA ACEPTADA: aplicada, pero el run en ROJO y con su aviso',
   (codigo, [o['datos'] for o in ops if o['tabla'] == 'rpc:disp_aplicar_pasada'], 'CAIDA_ACEPTADA: la pasada PASADA-1' in _texto,
    'PASADA APLICADA' in _texto), (1, [{'p_pasada': 'PASADA-1'}], True, True))

# ── (P) LOS TRAMOS EN EL PROGRAMA ENTERO (encargo H1) ─────────────────────────────────────
_TRAMOS_I = {'HAS0002': [(10, 10)], 'UG00001': [(6, 10)], 'FK67930': [(2, 10)]}
_BASES_I = {'HAS0002': 21.0, 'UG00001': 6.0, 'FK67930': 48.0}
ops_sin, codigo_sin, texto_sin = correr_programa()
ops_con, codigo_con, texto_con = correr_programa(tramos=_TRAMOS_I, bases=_BASES_I)
_lec_sin = {f['producto_prov']: f for o in _de(ops_sin, 'disp_lectura', 'insert') for f in o['datos']}
_lec_con = {f['producto_prov']: f for o in _de(ops_con, 'disp_lectura', 'insert') for f in o['datos']}
eq('(P) en el programa: sin tramos, toda fila con precio lleva las tres llenas con el de hoy y uds 1; sin precio, vacías',
   sorted({(f.get('precio_escalon') == f['precio_unidad'] == f.get('precio_pa'), f.get('uds_escalon', 'FALTA'))
           if f['precio_unidad'] is not None else _esc(f) for f in _lec_sin.values()}, key=str),
   sorted({(True, 1)}, key=str))
# Los tres de _TRAMOS_I, en su orden: el de Hasbro, el de Ultimate Guard y la caja de Funko.
eq('(P) …con tramos: el de Hasbro (21, 10 % desde 10) → 18,90; el de UG (hoy 5, base 6, 10 %) se queda en 5; la caja '
   'de Funko (48 la caja de 6, 10 % desde 2), sin tramo desde el H3: 8 por unidad y uds 1',
   [_esc(_lec_con[pn]) for pn in _TRAMOS_I], [(18.9, 10, 18.9), (5.0, 1, 5.0), (8.0, 1, 8.0)])
_quitar = lambda ops: [dict(o, datos=[{k: v for k, v in f.items() if k not in ('precio_escalon', 'uds_escalon', 'precio_pa')}
                                      for f in o['datos']]) if (o['tabla'], o['accion']) == ('disp_lectura', 'insert') else o
                       for o in ops]
eq('(P) 🔒 EL BLINDAJE, IGUAL: con y sin tramos, la pasada hace EXACTAMENTE lo mismo (recuentos, llamadas a la base y '
   'filas subidas) salvo las tres columnas nuevas, y termina igual',
   (_quitar(ops_con) == _quitar(ops_sin), codigo_con, codigo_sin), (True, 0, 0))
eq('(P) …y las tres columnas no van a la pasada (disp_pasada no las lleva en ningún guardado)',
   any(k in o['datos'] for o in _de(ops_con, 'disp_pasada', 'update') for k in ('precio_escalon', 'uds_escalon', 'precio_pa')),
   False)
import re as _re
_linea_tramos = [l for l in texto_con.splitlines() if l.startswith('>>> TRAMOS')]
eq('(P) 🔒 en el log, SOLO recuentos (el repo es público): ni un importe',
   [bool(_re.fullmatch(r'>>> TRAMOS \(en sombra, nadie los lee\): \d+ productos con tramo · el tramo gana en \d+ · '
                       r'con descuento propio y tramo \d+ · '
                       r'tramos raros ignorados \d+ · repetidos con tramos distintos \(vacíos\) \d+ · sin precio \(vacíos\) \d+'
                       r' · con precio tachado, sin tramo \d+ · Funko sin tachado, sin tramo \d+',
                       l)) for l in _linea_tramos], [True])
eq('(P) …y son los de este banco: 3 con tramo, gana en 1, 1 con descuento propio y tramo (el de UG) y 1 Funko sin tramo',
   ('3 productos con tramo · el tramo gana en 1 · con descuento propio y tramo 1 ·' in texto_con,
    texto_con.count(' · Funko sin tachado, sin tramo 1')), (True, 1))

# (Q) CON PRECIO TACHADO, EN EL PROGRAMA ENTERO (encargo H3): HAS0002 trae tramo y tachado → sin tramo, el de hoy (21).
ops_tach, codigo_tach, texto_tach = correr_programa(tramos=_TRAMOS_I, bases=_BASES_I, tachados={'HAS0002': 25.0})
_lec_tach = {f['producto_prov']: f for o in _de(ops_tach, 'disp_lectura', 'insert') for f in o['datos']}
eq('(Q) en el programa: HAS0002 con tachado se queda en el de hoy (21) y uds 1 (con tramos y sin tachado iba a 18,90)',
   (_esc(_lec_tach['HAS0002']), _esc(_lec_con['HAS0002'])), ((21.0, 1, 21.0), (18.9, 10, 18.9)))
eq('(Q) …y todas las demás filas, igual que con tramos y sin tachado (ninguna se queda con tramo: la caja es Funko)',
   ({pn: _esc(f) for pn, f in _lec_tach.items() if pn != 'HAS0002'} ==
    {pn: _esc(f) for pn, f in _lec_con.items() if pn != 'HAS0002'},
    sum(1 for pn, f in _lec_tach.items() if pn != 'HAS0002' and f.get('uds_escalon') not in (None, 1))), (True, 0))
eq('(Q) 🔒 …y la pasada hace EXACTAMENTE lo mismo que sin tramos salvo las tres columnas, y termina igual',
   (_quitar(ops_tach) == _quitar(ops_sin), codigo_tach), (True, 0))
eq('(Q) …en el log, el recuento: 3 con tramo, gana en 0, con precio tachado sin tramo 1, Funko sin tramo 1',
   ('3 productos con tramo · el tramo gana en 0 ·' in texto_tach, ' · con precio tachado, sin tramo 1 ·' in texto_tach,
    ' · con precio tachado, sin tramo 0 ·' in texto_con, ' · Funko sin tachado, sin tramo 1' in texto_tach),
   (True, True, True, True))
eq('(Q) 🔒 …y el importe del tachado (25) no sale en el log', '25' in texto_tach, False)
# 🔴 Si los tramos FALLAN, la pasada se aplica igual con las tres vacías, y el run acaba en ROJO al final.
_poner_de_verdad = dp.poner_escalones
dp.poner_escalones = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('tramos de mentira que fallan'))
try:
    ops, codigo, _texto = correr_programa(tramos=_TRAMOS_I, bases=_BASES_I)
finally:
    dp.poner_escalones = _poner_de_verdad
eq('(P) 🔴 si los tramos fallan: rojo AL FINAL, pero la pasada se sube, se aplica y se relee',
   (codigo, [o['tabla'] for o in ops if o['tabla'] == 'rpc:disp_aplicar_pasada'], 'PASADA APLICADA' in _texto,
    'ESCALONES_NO_CALCULADOS' in _texto), (1, ['rpc:disp_aplicar_pasada'], True, True))
eq('(P) …con las tres columnas VACÍAS en todas las filas y lo demás igual que sin fallo',
   ({_esc(f) for o in _de(ops, 'disp_lectura', 'insert') for f in o['datos']}, _quitar(ops) == _quitar(ops_sin)),
   ({(None, None, None)}, True))

# ── (M) LAS NOVEDADES DE FUNKO, UN PASO APARTE (encargo H, tramo 1) ─────────────────────────
ops, codigo, _texto = correr_programa(fallan={('rpc:nov_seleccionar_pasada', 'rpc')})
eq('(M) 🔴 si la selección de novedades FALLA: el run acaba en ROJO…', codigo, 1)
eq('(M) …pero la pasada se aplicó y se releyó ANTES (la selección va después)',
   ([o['tabla'] for o in ops if o['tabla'].startswith('rpc:') or (o['tabla'] == 'disp_pasada' and o['accion'] == 'select')],
    'PASADA APLICADA' in _texto),
   (['rpc:disp_aplicar_pasada', 'disp_pasada', 'rpc:nov_seleccionar_pasada', 'rpc:nov_cerrar_valoracion'], True))
eq('(M) …y la pasada NO se toca después: ni se cierra fallida ni se borra lo leído',
   ([o['datos'] for o in _de(ops, 'disp_pasada', 'update') if o['datos'].get('estado') == 'fallida'], _de(ops, 'disp_lectura', 'delete')),
   ([], []))
eq('(M) …el fallo se apunta en nov_pasada, sin pisar una fila que ya hubiera, y en el log',
   ([(o['datos']['pasada_id'], o['datos']['proveedor'], o['datos']['estado'], 'APIError de mentira' in o['datos']['motivo'], o['opciones'])
     for o in _de(ops, 'nov_pasada', 'upsert')],
    'NOVEDADES_NO_SELECCIONADAS: la pasada PASADA-1 sigue aplicada' in _texto),
   ([('PASADA-1', 'HEO', 'fallida', True, {'on_conflict': 'pasada_id', 'ignore_duplicates': True})], True))
eq('(M) …y no se reintenta: UNA llamada', len([o for o in ops if o['tabla'] == 'rpc:nov_seleccionar_pasada']), 1)

ops, codigo, _texto = correr_programa(fallan={('rpc:nov_seleccionar_pasada', 'rpc'), ('nov_pasada', 'upsert')})
eq('(M) 🔴 si ni siquiera se puede apuntar el fallo: rojo, dicho en el log, y sin excepción sin atrapar',
   (codigo, 'NOVEDADES_FALLO_SIN_APUNTAR' in _texto, 'Traceback' in _texto), (1, True, False))

ops, codigo, _texto = correr_programa(caida=True, fallan={('rpc:nov_seleccionar_pasada', 'rpc')})
eq('(M) 🔴 lo que viene DESPUÉS se ejecuta aunque la selección falle (el aviso de la caída aceptada)',
   (codigo, 'NOVEDADES_NO_SELECCIONADAS' in _texto, 'CAIDA_ACEPTADA: la pasada PASADA-1' in _texto), (1, True, True))

ops, codigo, _texto = correr_programa(caida=True)
eq('(M) con una caída aceptada, las novedades se seleccionan y se valoran igual (la pasada está aplicada)',
   [o['tabla'] for o in ops if o['tabla'].startswith('rpc:')],
   ['rpc:disp_aplicar_pasada', 'rpc:nov_seleccionar_pasada', 'rpc:nov_cerrar_valoracion'])

ops, codigo, _texto = correr_programa(estado_final='rechazada')
eq('(M) 🔴 con la pasada RECHAZADA no se seleccionan novedades (rojo, y sin llamar a la función)',
   (codigo, [o['tabla'] for o in ops if o['tabla'].startswith('rpc:')], _de(ops, 'nov_pasada', 'upsert')),
   (1, ['rpc:disp_aplicar_pasada'], []))

ops, codigo, _texto = correr_programa(disponibilidades_declaradas=N_TOTAL + 11)
eq('(M) …ni con la descarga cortada (no se llega a aplicar)', [o for o in ops if o['tabla'].startswith('rpc:')], [])

# ── (N) VALORAR LAS NOVEDADES Y EL VIGÍA DE LA MARCA (encargo I, tramo 2) ──────────────────────
ops, codigo, _texto = correr_programa()
eq('(N) con la valoración APAGADA: lee el interruptor, cierra la valoración como apagada y termina bien (verde)',
   (codigo, [o['datos'] for o in _de(ops, 'nov_parametros', 'select')], '>>> VALORACION DE NOVEDADES: APAGADA' in _texto),
   (0, [('*',)], True))
ops, codigo, _texto = correr_programa(fallan={('rpc:nov_cerrar_valoracion', 'rpc')})
eq('(N) 🔴 si la valoración FALLA: rojo al final, con la pasada aplicada y las novedades seleccionadas ANTES',
   (codigo, [o['tabla'] for o in ops if o['tabla'].startswith('rpc:')], 'NOVEDADES_NO_VALORADAS: la pasada PASADA-1 sigue aplicada' in _texto),
   (1, ['rpc:disp_aplicar_pasada', 'rpc:nov_seleccionar_pasada', 'rpc:nov_cerrar_valoracion'], True))
eq('(N) …y la pasada NO se toca después: ni se cierra fallida ni se borra lo leído, ni sale un traceback',
   ([o['datos'] for o in _de(ops, 'disp_pasada', 'update') if o['datos'].get('estado') == 'fallida'], _de(ops, 'disp_lectura', 'delete'),
    'Traceback' in _texto), ([], [], False))
ops, codigo, _texto = correr_programa(fallan={('rpc:nov_seleccionar_pasada', 'rpc')})
eq('(N) si la SELECCIÓN falla, la valoración corre igual (la cola de antes sigue ahí) y el run acaba en rojo',
   (codigo, [o['tabla'] for o in ops if o['tabla'].startswith('rpc:')]),
   (1, ['rpc:disp_aplicar_pasada', 'rpc:nov_seleccionar_pasada', 'rpc:nov_cerrar_valoracion']))
ops, codigo, _texto = correr_programa(marca_parecida=2)
eq('(N) 🔴 EL VIGÍA: con 2 productos de marca parecida a Funko, rojo AL FINAL, con el motivo en el log…',
   (codigo, 'MARCA_PARECIDA: 2 producto(s) de HEO' in _texto), (1, True))
eq('(N) …y DESPUÉS de haberlo aplicado todo: la pasada, la selección y la valoración',
   ([o['tabla'] for o in ops if o['tabla'].startswith('rpc:')], 'PASADA APLICADA' in _texto,
    _texto.index('>>> VALORACION DE NOVEDADES') < _texto.index('MARCA_PARECIDA')),
   (['rpc:disp_aplicar_pasada', 'rpc:nov_seleccionar_pasada', 'rpc:nov_cerrar_valoracion'], True, True))
ops, codigo, _texto = correr_programa(caida=True, marca_parecida=1)
eq('(N) …y no se come otro aviso: con la caída aceptada, salen los dos',
   (codigo, 'CAIDA_ACEPTADA' in _texto, 'MARCA_PARECIDA: 1' in _texto), (1, True, True))
with open(os.path.join(AQUI, '.github', 'workflows', 'escaner2-heo-disponibilidad.yml'), encoding='utf-8') as fh:
    _lineas_wf = [l for l in fh.read().splitlines() if not l.lstrip().startswith('#')]
eq('(N) el workflow le da la llave de Keepa al paso de la pasada (la misma que el director: KEEPA_API_KEY), y ninguna para disparar la v2',
   ([l.strip() for l in _lineas_wf if 'KEEPA_API_KEY' in l], any('GH_TOKEN' in l or 'dispatches' in l for l in _lineas_wf)),
   (['KEEPA_API_KEY:        ${{ secrets.KEEPA_API_KEY }}'], False))

# ── (K) CON LA DESCARGA HEREDADA DE VERDAD ───────────────────────────────────────────────
# Solo se cambia `_get` (la red) por páginas en memoria; `_paginar` y `descargar_catalogo_heo` son los
# de verdad. R1 no llega en availabilities, R2 no llega en prices, R3 (caja con chase) llega en las
# dos, y R4 no trae GTIN.
_env_heo = {k: os.environ.get(k) for k in ('HEO_USER', 'HEO_PASS')}
_mod_antes = sys.modules.pop('escaner2_heredado_descarga', None)
# 🔒 Sin red: la heredada importa `requests`; aquí se le da uno de mentira que no sabe salir a
#    internet (y el CI de Python no lo tiene instalado). Su `_get` se cambia además por páginas en memoria.
_req_antes = {k: sys.modules.get(k) for k in ('requests', 'requests.auth')}
_req = types.ModuleType('requests')
_req.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('el banco no sale a la red'))
_req.auth = types.ModuleType('requests.auth')
_req.auth.HTTPBasicAuth = lambda usuario, clave: None
sys.modules['requests'], sys.modules['requests.auth'] = _req, _req.auth
os.environ.update(HEO_USER='u', HEO_PASS='p')
try:
    import escaner2_heredado_descarga as hd_real
finally:
    for k, v in _req_antes.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v
    for k, v in _env_heo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    sys.modules.pop('escaner2_heredado_descarga', None)
    if _mod_antes is not None:
        sys.modules['escaner2_heredado_descarga'] = _mod_antes


def _prod(pn, nombre, marca, gtin):
    return {'productNumber': pn, 'name': [{'langIso2': 'ES', 'translation': nombre}],
            'manufacturers': [{'translations': [{'langIso2': 'ES', 'translation': marca}]}],
            'barcodes': [{'type': 'GTIN', 'barcode': gtin}] if gtin else []}


def _precio(pn, euros):
    return {'productNumber': pn, 'basePricePerUnit': {'amount': euros}, 'discountedPricePerUnit': {'amount': euros}}


def _dispo(pn):
    return {'productNumber': pn, 'availableToOrder': True, 'availabilityState': 'AVAILABLE', 'availability': 'GREEN'}


# (H1) R1 trae un tramo, como lo da HEO en products: 10 % desde 10 uds.
_R1 = dict(_prod('R1', 'Figura uno', 'Hasbro', '5010993999990'),
           prices={'basePricePerUnit': {'amount': 10.0}, 'scaledDiscounts': [{'quantity': 10, 'discount': {'amount': 10.0}}]})
PAGINAS = {'catalog/products': [_R1, _prod('R2', 'Figura dos', 'Hasbro', '5010993999991'),
                                _prod('R3', 'Figura tres w/Chase Surtido (6)', 'Funko', '889698862646'),
                                _prod('R4', 'Figura sin código', 'Hasbro', '')],
           'catalog/prices': [_precio('R1', 10.0), _precio('R3', 60.0)],
           'catalog/availabilities': [_dispo('R2'), _dispo('R3')]}


def _get_en_memoria(url, page):
    contenido = PAGINAS[url[len(hd_real.BASE) + 1:]]
    # HEO declara lo DISTINTO; si repite, es al paginar.
    return {'content': contenido, 'pagination': {'totalPages': 1, 'totalElements': len({x['productNumber'] for x in contenido}),
                                                 'pageSize': 500}}


_get_de_verdad, _paginar_de_verdad = hd_real._get, hd_real._paginar
hd_real._get = _get_en_memoria
try:
    ops, codigo, _texto = correr_programa(modulo_descarga=hd_real)
finally:
    hd_real._get = _get_de_verdad
lectura = {f['producto_prov']: f for o in _de(ops, 'disp_lectura', 'insert') for f in o['datos']}
eq('(K) con la heredada de verdad, termina bien y sube R1, R2 y R3 (R4 sin GTIN solo se cuenta)',
   (codigo, sorted(lectura)), (0, ['R1', 'R2', 'R3']))
eq('(K) …R1 sin dato de disponibilidad (la heredada lo da agotado), R2 sin dato de precio, R3 con todo',
   [(p, f['disponible'], f['sin_dato_disponibilidad'], f['sin_dato_precio']) for p, f in sorted(lectura.items())],
   [('R1', False, True, False), ('R2', True, False, True), ('R3', True, False, False)])
eq('(K) …la caja con chase entra por la lista de chase y se marca por su número',
   (lectura['R3']['es_chase'], lectura['R3']['es_caja']), (True, True))
recs = _de(ops, 'disp_pasada', 'update')[0]['datos']
eq('(K) …los recuentos del log de la heredada: 4 productos, 2 precios, 2 disponibilidades, 1 sin GTIN',
   (recs['n_declarado'], recs['n_crudo'], recs['n_precios'], recs['n_disponibilidades'], recs['n_sin_gtin']), (4, 4, 2, 2, 1))
eq('(K) …y su _paginar queda el de verdad', hd_real._paginar is _paginar_de_verdad, True)
eq('(K) (H1) los tramos salen de la lista cruda de products de la heredada: R1 (10, 10 % desde 10) → 9 desde 10; '
   'R2 sin precio, vacías; la caja R3 sin tramo, su precio por unidad y uds 1',
   {p: _esc(f) for p, f in sorted(lectura.items())},
   {'R1': (9.0, 10, 9.0), 'R2': (None, None, None), 'R3': (10.0, 1, 10.0)})

# (K) con REPETIDOS en la heredada de verdad: R1 dos veces en products (idéntico) y en prices, y R4
#     (sin GTIN) dos veces → se aplica con 2 repetidos de productos, 1 de precios, y sin GTIN 1.
PAGINAS['catalog/products'] = PAGINAS['catalog/products'] + [PAGINAS['catalog/products'][0], PAGINAS['catalog/products'][3]]
PAGINAS['catalog/prices'] = PAGINAS['catalog/prices'] + [PAGINAS['catalog/prices'][0]]
hd_real._get = _get_en_memoria
try:
    ops, codigo, _texto = correr_programa(modulo_descarga=hd_real)
finally:
    hd_real._get = _get_de_verdad
lectura = {f['producto_prov']: f for o in _de(ops, 'disp_lectura', 'insert') for f in o['datos']}
recs = _de(ops, 'disp_pasada', 'update')[0]['datos']
cuentas_subidas = next((o['datos'] for o in _de(ops, 'disp_pasada', 'update') if 'n_leidas' in o['datos']), {})
eq('(K) con repetidos en la heredada de verdad: termina bien y sube R1, R2 y R3 una vez',
   (codigo, sorted(lectura), sum(len(o['datos']) for o in _de(ops, 'disp_lectura', 'insert'))), (0, ['R1', 'R2', 'R3'], 3))
eq('(K) …crudo 6 con 2 repetidos, 1 de precios; declarados 4 (distintos)',
   (recs['n_crudo'], recs['n_duplicados'], recs['n_duplicados_precios'], recs['n_declarado']), (6, 2, 1, 4))
eq('(K) …el log contó 2 sin GTIN (las copias de R4) y se guarda 1 desde el principio: 6 = 1 + 3 + 2',
   ('descartadas 2 sin GTIN' in _texto, recs['n_sin_gtin'], cuentas_subidas.get('n_leidas')), (True, 1, 3))

# (K) y con R2 repetido con OTRO nombre en la heredada de verdad → fallida, sin subir nada.
PAGINAS['catalog/products'] = PAGINAS['catalog/products'] + [_prod('R2', 'Figura dos (otra)', 'Hasbro', '5010993999991')]
hd_real._get = _get_en_memoria
try:
    ops, codigo, _texto = correr_programa(modulo_descarga=hd_real)
finally:
    hd_real._get = _get_de_verdad
eq('(K) …un repetido DISTINTO en la heredada de verdad: rojo, sin subir nada ni llamar a la función',
   (codigo, _de(ops, 'disp_lectura', 'insert'), [o for o in ops if o['tabla'].startswith('rpc:')],
    'repetidos con datos distintos: R2' in _de(ops, 'disp_pasada', 'update')[-1]['datos'].get('motivo', '')), (1, [], [], True))

# (K) 🆕 (encargo CJ4, 11-oct-2026) LA OFERTA DE HEO ES EL PRECIO TACHADO, con la heredada de verdad (desvío CJ4 de
#     escaner2_desvios.py). Importes INVENTADOS. R1 trae `strikePricePerUnit` → en oferta, con su tachado; R2 lo trae a
#     0 → no; R5 trae el DESCUENTO DE CLIENTE (`retailerProductDiscount` y precio de hoy por debajo del base) sin
#     tachado → NO es oferta (antes, sí); la caja con chase R3 trae tachado → en oferta, con el de la caja.
PAGINAS = {'catalog/products': [_prod('R1', 'Figura uno', 'Hasbro', '5010993999990'),
                                _prod('R2', 'Figura dos', 'Hasbro', '5010993999991'),
                                _prod('R3', 'Figura tres w/Chase Surtido (6)', 'Funko', '889698862646'),
                                _prod('R5', 'Figura cinco', 'Funko', '5010993999992')],
           'catalog/prices': [dict(_precio('R1', 10.0), strikePricePerUnit={'amount': 12.5}),
                              dict(_precio('R2', 10.0), strikePricePerUnit={'amount': 0}),
                              dict(_precio('R3', 60.0), strikePricePerUnit={'amount': 72.0}),
                              {'productNumber': 'R5', 'basePricePerUnit': {'amount': 10.0},
                               'discountedPricePerUnit': {'amount': 9.0}, 'retailerProductDiscount': {'amount': 10.0}}],
           'catalog/availabilities': [_dispo('R1'), _dispo('R2'), _dispo('R3'), _dispo('R5')]}
hd_real._get = _get_en_memoria
try:
    ops, codigo, _texto = correr_programa(modulo_descarga=hd_real)
finally:
    hd_real._get = _get_de_verdad
lectura = {f['producto_prov']: f for o in _de(ops, 'disp_lectura', 'insert') for f in o['datos']}
eq('(K) (CJ4) en oferta = trae precio tachado, y sube su tachado: R1 sí (12,5), R2 a 0 no, R5 con solo el descuento de '
   'cliente NO, y la caja con chase R3 sí (72, el de la caja)',
   (codigo, {p: (f['en_oferta'], f.get('precio_tachado', 'FALTA')) for p, f in sorted(lectura.items())}),
   (0, {'R1': (True, 12.5), 'R2': (False, None), 'R3': (True, 72.0), 'R5': (False, None)}))
eq('(K) (CJ4) …y la descarga lo dice en su log con su nombre nuevo',
   ('En oferta (precio tachado de HEO, DESVÍO CJ4): 1' in _texto, 'campana/descuento' in _texto), (True, False))


# ═══════════════════════════════════════════════════════════════════════════════
# (PD) 🆕 ENCARGO PD, 27-nov-2026 · escaner2_pro_en_directo POR DENTRO: la lectura en directo del Escaneo PRO
#      (la guarda del PRO, el freno, el turno, la decision y el motivo). Los barridos de punta a punta, en los bancos
#      *_pro (B6); los cuatro lectores reales, en los bancos de cada lectura.
# ═══════════════════════════════════════════════════════════════════════════════
print('\n(PD) la lectura en directo del Escaneo PRO, por dentro')
import types as _types  # noqa: E402
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
import escaner2_pro_en_directo as epd  # noqa: E402


class _BasePD:
    """Una base de mentira minima: tablas en memoria; select/eq/order/limit/range/update."""

    def __init__(self, **tablas):
        self.t = {k: [dict(f) for f in v] for k, v in tablas.items()}
        self.updates = []

    def table(self, nombre):
        base = self

        class _Q:
            def __init__(self):
                self.f, self.op, self.datos, self.orden, self.tope, self.rango = [], 'select', None, None, None, None

            def select(self, *_a, **_k):
                return self

            def update(self, d):
                self.op, self.datos = 'update', d
                return self

            def eq(self, k, v):
                self.f.append((k, v))
                return self

            def order(self, col, desc=False):
                self.orden = (col, desc)
                return self

            def limit(self, n):
                self.tope = n
                return self

            def range(self, a, b):
                self.rango = (a, b)
                return self

            def execute(self):
                filas = [x for x in base.t.setdefault(nombre, []) if all(x.get(k) == v for k, v in self.f)]
                if self.op == 'update':
                    base.updates.append((nombre, dict(self.f), self.datos))
                    for x in filas:
                        x.update(self.datos)
                    return _types.SimpleNamespace(data=filas)
                if self.orden:
                    filas = sorted(filas, key=lambda x: str(x.get(self.orden[0])), reverse=self.orden[1])
                if self.rango:
                    filas = filas[self.rango[0]:self.rango[1] + 1]
                if self.tope is not None:
                    filas = filas[:self.tope]
                return _types.SimpleNamespace(data=[dict(x) for x in filas])
        return _Q()


_AHORA = _dt(2026, 11, 27, 10, 30, tzinfo=_tz.utc)


def _iso(min_antes):
    return (_AHORA - _td(minutes=min_antes)).isoformat()


_PAR = {'proveedor': 'TCG', 'rechazos_para_aceptar': 3, 'ausencias_para_salir': 2, 'sin_dato_para_agotar': 3}


def _base_pd(aplicada_hace=5, estado=(), extra=()):
    return _BasePD(disp_parametros=[_PAR],
                   disp_pasada=[{'id': 'A', 'proveedor': 'TCG', 'estado': 'aplicada', 'creada_en': _iso(aplicada_hace),
                                 'terminada_en': _iso(aplicada_hace - 1)}] + list(extra),
                   disp_estado=list(estado))


g = epd.GuardaPro(_base_pd(5), 'TCG')
# 🔑 La lectura buena de hace menos de 15 min: se usa esa, sin volver a leer (quien dirige, 27-nov-2026)
eq('(PD) reciente: la aplicada TERMINADA hace 4 min es la foto, y se dice cuánto hace',
   epd.lectura_reciente(_base_pd(5), 'TCG', _AHORA), ('A', 4))
eq('(PD) reciente: terminada hace 15 min o más, ya no (se lee)', epd.lectura_reciente(_base_pd(16), 'TCG', _AHORA), None)
_bd2 = _base_pd(90, extra=[{'id': 'D', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(6),
                            'terminada_en': _iso(5), 'motivo': 'al día: … pasada aplicada A; nada nuevo'}])
eq('(PD) reciente: un «al día» de hace 5 min que confirma la última aplicada (de hace hora y media) vale: su foto',
   epd.lectura_reciente(_bd2, 'TCG', _AHORA), ('A', 5))
_bd3 = _base_pd(90, extra=[
    {'id': 'F', 'proveedor': 'TCG', 'estado': 'fallida', 'creada_en': _iso(3), 'terminada_en': _iso(2), 'motivo': 'x'},
    {'id': 'V', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'creada_en': _iso(4), 'terminada_en': _iso(3)},
    {'id': 'C', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(4), 'terminada_en': _iso(3),
     'motivo': 'descarga cortada: …'},
    {'id': 'X', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(4), 'terminada_en': _iso(3),
     'motivo': 'al día: … pasada aplicada Z9; nada'},
    {'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(2)},
    {'id': 'H', 'proveedor': 'HEO', 'estado': 'aplicada', 'creada_en': _iso(2), 'terminada_en': _iso(1)}])
eq('(PD) 🔴 reciente: ni una fallida, ni un vaciado, ni otra rechazada, ni un «al día» de otra, ni una «leyendo», ni la '
   'de otro proveedor', epd.lectura_reciente(_bd3, 'TCG', _AHORA), None)
_bd4 = _base_pd(5, extra=[{'id': 'B', 'proveedor': 'TCG', 'estado': 'aplicada', 'creada_en': _iso(3),
                           'terminada_en': _iso(70)}])
eq('(PD) reciente: si después se ha aplicado otra (B), la de hace 4 min ya no es la buena; B tampoco (hace 70 min)',
   epd.lectura_reciente(_bd4, 'TCG', _AHORA), None)


# 🔑 OSMA: el fichero de ahora confirma la ultima aplicada si es EL MISMO y no ha vencido ninguna lectura prevista
class _BaseOsma(_BasePD):
    def __init__(self, copia, frescura, **tablas):
        super().__init__(**tablas)
        self.copia, self.frescura, self.rpcs = copia, frescura, []
        base = self

        class _Cubo:
            def __init__(self, nombre):
                self.nombre = nombre

            def download(self, ruta):
                base.rpcs.append(('download', self.nombre, ruta))
                if base.copia is None:
                    raise RuntimeError('404 Object not found')
                return base.copia
        self.storage = _types.SimpleNamespace(from_=_Cubo)

    def rpc(self, nombre, params):
        self.rpcs.append((nombre, params))
        return _types.SimpleNamespace(execute=lambda: _types.SimpleNamespace(data=self.frescura))


_VIERNES = _dt(2026, 11, 27, 6, 16, tzinfo=_tz.utc)        # la lectura aplicada del viernes, 07:16 de Madrid
_APL_OSMA = [{'id': 'OV', 'proveedor': 'OSMA', 'estado': 'aplicada', 'creada_en': _VIERNES.isoformat(),
              'terminada_en': _VIERNES.isoformat()}]


def _fresc(prevista):
    return [{'proveedor': 'TCG', 'ultima_aplicada': None, 'ultima_prevista': None},
            {'proveedor': 'OSMA', 'ultima_aplicada': _VIERNES.isoformat(), 'ultima_prevista': prevista.isoformat()}]


_FICHERO = b'PK\x03\x04 el xlsx del viernes'
_DOMINGO = _dt(2026, 11, 29, 17, 0, tzinfo=_tz.utc)
_CREADO = _dt(2026, 11, 27, 2, 33, tzinfo=_tz.utc)
_b = _BaseOsma(_FICHERO, _fresc(_dt(2026, 11, 27, 6, 15, tzinfo=_tz.utc)), disp_pasada=_APL_OSMA)
eq('(PD) 🔑 OSMA el domingo: el fichero es EL MISMO que la copia del viernes y no ha vencido ninguna prevista desde '
   'ella → confirma la aplicada del viernes', (epd.confirmar_osma(_b, _FICHERO, _DOMINGO, 'osma/ultimo/x.xlsx', 'escaner2',
                                                                  _CREADO),
                                              [r[0] for r in _b.rpcs], _b.rpcs[0][2], _b.rpcs[1][1]),
   (('OV', None), ['download', 'disp_frescura_en'], 'osma/ultimo/x.xlsx', {'p_ahora': _DOMINGO.isoformat()}))
_b = _BaseOsma(_FICHERO, _fresc(_dt(2026, 11, 30, 6, 15, tzinfo=_tz.utc)), disp_pasada=_APL_OSMA)
eq('(PD) 🔴 OSMA el lunes a las 10:00, con la lectura prevista del lunes vencida y sin aplicar: no confirma, y dice de '
   'cuándo es el último fichero', epd.confirmar_osma(_b, _FICHERO, _dt(2026, 11, 30, 9, 0, tzinfo=_tz.utc),
                                                    'osma/ultimo/x.xlsx', 'escaner2', _CREADO),
   (None, 'OSMA no ha publicado fichero nuevo hoy; el último es del 27-11-2026 a las 03:33'))
_b = _BaseOsma(b'PK\x03\x04 otro', _fresc(_dt(2026, 11, 27, 6, 15, tzinfo=_tz.utc)), disp_pasada=_APL_OSMA)
eq('(PD) 🔴 OSMA: un fichero que no es el de la copia (no es más nuevo ni el mismo) no confirma, y ni mira el horario',
   (epd.confirmar_osma(_b, _FICHERO, _DOMINGO, 'r', 'escaner2')[0], [r[0] for r in _b.rpcs]), (None, ['download']))
_b = _BaseOsma(None, _fresc(_dt(2026, 11, 27, 6, 15, tzinfo=_tz.utc)), disp_pasada=_APL_OSMA)
eq('(PD) 🔴 OSMA: sin la copia para comparar, no confirma', 'no se ha podido leer la copia' in
   (epd.confirmar_osma(_b, _FICHERO, _DOMINGO, 'r', 'escaner2')[1] or ''), True)
_b = _BaseOsma(_FICHERO, [], disp_pasada=_APL_OSMA)
eq('(PD) 🔴 OSMA: sin su fila en disp_frescura_en, no confirma', 'disp_frescura_en' in
   (epd.confirmar_osma(_b, _FICHERO, _DOMINGO, 'r', 'escaner2')[1] or ''), True)
_r = epd.leer_en_directo(_base_pd(90), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 1,
                         {'TCG': lambda *a: epd.Lectura(pid='P', confirma='A')}, _AHORA)
eq('(PD) una lectura que confirma la última aplicada: su foto', (_r.foto, _r.motivo), ('A', None))
_r = epd.leer_en_directo(_base_pd(90), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 1,
                         {'TCG': lambda *a: epd.Lectura(pid='P', confirma='OTRA')}, _AHORA)
eq('(PD) 🔴 …una que confirma otra que ya no es la última: no', 'ya no es la última' in (_r.motivo or ''), True)
_r = epd.leer_en_directo(_base_pd(90), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 1,
                         {'TCG': lambda *a: epd.Lectura(pid='P', por_que='OSMA no ha publicado')}, _AHORA)
eq('(PD) …y el porqué del lector va al motivo', (_r.foto, '(OSMA no ha publicado)' in _r.motivo), (None, True))
_llamado = []
_r = epd.leer_en_directo(_base_pd(5), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 1,
                         {'TCG': lambda *a: _llamado.append(1)}, _AHORA)
eq('(PD) 🔴 con una lectura buena de hace 4 min, el PRO NO vuelve a leer: sale de esa', (_r.foto, _llamado), ('A', []))
# El vaciado del PRO no suma rechazos: ni el del programa ni el de la funcion
eq('(PD) 🔴 sin_freno: un vaciado del programa queda «fallida», con su motivo; lo demás, tal cual',
   (g.sin_freno('rechazada_vaciado', 'vaciado: x'), g.sin_freno('rechazada', 'al día: y'), g.sin_freno('fallida', 'z')),
   (('fallida', epd.PREFIJO_VACIADO + 'vaciado: x'), ('rechazada', 'al día: y'), ('fallida', 'z')))
_b = _base_pd(5, extra=[{'id': 'V', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'motivo': 'vaciado: w'},
                        {'id': 'W', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'motivo': 'vaciado: q'}])
_f = epd.GuardaPro(_b, 'TCG').tras_aplicar('V', {'id': 'V', 'estado': 'rechazada_vaciado', 'motivo': 'vaciado: w'})
eq('(PD) 🔴 tras_aplicar: el vaciado que deja la función pasa a «fallida» (solo ESA pasada); la aplicada, intacta',
   (_f['estado'], [p['estado'] for p in _b.t['disp_pasada'] if p['id'] in ('V', 'W')],
    epd.GuardaPro(_b, 'TCG').tras_aplicar('A', {'id': 'A', 'estado': 'aplicada'})['estado']),
   ('fallida', ['fallida', 'rechazada_vaciado'], 'aplicada'))
# Antes de leer: el turno y el freno
eq('(PD) antes de leer: nada en marcha y sin rechazos, se lee', epd.antes_de_leer(_base_pd(90), 'TCG', _AHORA), None)
eq('(PD) 🔴 antes de leer: una «leyendo» de hace 10 min es otra lectura viva: no se lee a la vez',
   'en marcha desde el 27-11-2026 a las 11:20' in (epd.antes_de_leer(_base_pd(90, extra=[
       {'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(10)}]), 'TCG', _AHORA) or ''), True)
eq('(PD) antes de leer: una «leyendo» de hace 2 h ya es huérfana (la función la cerrará): se lee',
   epd.antes_de_leer(_base_pd(150, extra=[{'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(120)}]),
                     'TCG', _AHORA), None)
_rech = [{'id': 'R%d' % i, 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'creada_en': _iso(60 - i)} for i in (1, 2, 3)]
eq('(PD) 🔴 antes de leer: con 3 vaciados desde la última aplicada, esta podría aceptar la caída: no lee',
   'lleva 3 lecturas rechazadas' in (epd.antes_de_leer(_base_pd(90, extra=_rech), 'TCG', _AHORA) or ''), True)
eq('(PD) antes de leer: con 2, sí lee (la función solo acepta con 3 anteriores)',
   epd.antes_de_leer(_base_pd(90, extra=_rech[:2]), 'TCG', _AHORA), None)
eq('(PD) antes de leer: los vaciados de ANTES de la última aplicada no cuentan',
   epd.antes_de_leer(_base_pd(30, extra=_rech), 'TCG', _AHORA), None)
# Decidir
_bd = _base_pd(90, extra=[
    {'id': 'R', 'proveedor': 'TCG', 'estado': 'aplicada', 'creada_en': _iso(1), 'motivo': None},
    {'id': 'D', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(0), 'motivo': 'al día: … pasada aplicada R; nada'},
    {'id': 'X', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(0), 'motivo': 'descarga cortada: …'},
    {'id': 'F', 'proveedor': 'TCG', 'estado': 'fallida', 'creada_en': _iso(0), 'motivo': 'la web no deja'},
    {'id': 'H', 'proveedor': 'HEO', 'estado': 'aplicada', 'creada_en': _iso(0)}])
eq('(PD) decidir: aplicada y la última → su foto; «al día» que nombra la última → esa; lo demás, no, con su porqué',
   [epd.decidir(_bd, 'TCG', p) for p in ('R', 'D', 'X', 'F', 'A', 'H', None)],
   [('R', None), ('R', None), (None, 'rechazada: descarga cortada: …'), (None, 'fallida: la web no deja'),
    (None, 'la lectura se aplicó, pero después se ha aplicado otra'), (None, 'la pasada de la lectura no está en la base'),
    (None, 'la lectura no llegó a abrir su pasada')])
_bd.t['disp_pasada'].append({'id': 'D2', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(2),
                             'motivo': 'al día: … pasada aplicada R; nada'})
eq('(PD) 🔴 decidir: un «al día» ANTERIOR a la última aplicada no la confirma',
   epd.decidir(_bd, 'TCG', 'D2'), (None, 'la lectura dice «al día», pero hay una aplicada posterior'))
_bd.t['disp_pasada'].append({'id': 'D3', 'proveedor': 'TCG', 'estado': 'rechazada', 'creada_en': _iso(0),
                             'motivo': 'al día: … pasada aplicada A; nada'})
eq('(PD) 🔴 decidir: un «al día» que nombra OTRA aplicada (no la última) no la confirma',
   epd.decidir(_bd, 'TCG', 'D3'), (None, 'la lectura dice «al día», pero la última aplicada no es la que nombra'))
eq('(PD) el motivo para la pantalla: qué, por qué y con qué lectura NO se valora (hora de Madrid)',
   epd.motivo_de_fallo(_base_pd(90), 'TCG', 'la web no deja'),
   'no he podido leer a TCG ahora (la web no deja); no se valora con la lectura del 27-11-2026 a las 10:01')
eq('(PD) …y sin ninguna lectura aplicada, lo dice',
   epd.motivo_de_fallo(_BasePD(disp_pasada=[]), 'OSMA', 'x'),
   'no he podido leer a OSMA ahora (x); y no hay ninguna lectura anterior aplicada')
# leer_en_directo: nunca lanza


def _revienta(*_a):
    raise RuntimeError('fila con un EAN 4999999000001 y una URL https://x.invalid')


_r = epd.leer_en_directo(_base_pd(90), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 1, {'TCG': _revienta}, _AHORA)
eq('(PD) 🔴 un lector que revienta: sin foto, el motivo dice solo el TIPO (ni el EAN ni la URL)',
   (_r.foto, 'se ha caído (RuntimeError)' in _r.motivo, '4999' in _r.motivo or 'invalid' in _r.motivo), (None, True, False))
_r = epd.leer_en_directo(_base_pd(90), 'OCIOSTOCK', {}, '1', 1, {'OCIOSTOCK': _revienta}, _AHORA)
eq('(PD) sin el secreto del proveedor, ni se llama al lector', (_r.foto, 'OCIOSTOCK_FEED_URL' in _r.motivo), (None, True))
_vistos = []
_r = epd.leer_en_directo(_bd, 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '7', 2,
                         {'TCG': lambda sb, env, run, intento, guarda: (_vistos.append((run, intento, type(guarda).__name__))
                                                                       or epd.Lectura(pid='R'))}, _AHORA)
eq('(PD) el lector recibe el run, el intento y la guarda del PRO; con su pasada aplicada, sale su foto',
   (_vistos, _r.foto, _r.motivo), ([('7', 2, 'GuardaPro')], 'R', None))
eq('(PD) 🔴 TCG sin intentos (la página anti-robots a las 3 máquinas): el motivo, claro, con la última lectura buena',
   epd.motivo_sin_intentos(_base_pd(90), 3),
   'la web de TCG no deja entrar ahora a las máquinas de lectura (3 intentos); la última lectura buena es del 27-11-2026 '
   'a las 10:01')
_r = epd.leer_en_directo(_base_pd(90), 'TCG', {'TCG_USER': 'u', 'TCG_PASS': 'p'}, '1', 3,
                         {'TCG': lambda *a: epd.Lectura(pid='P', motivo_entero='la web de TCG no deja entrar ahora …')}, _AHORA)
eq('(PD) …y ese motivo va tal cual a la pantalla, sin foto', (_r.foto, _r.motivo), (None, 'la web de TCG no deja entrar ahora …'))
eq('(PD) los cuatro proveedores tienen lector y secretos (los de su workflow horario)',
   (sorted(epd.LECTORES), sorted(epd.PROVEEDORES), epd.PROVEEDORES['TCG'][1], epd.PROVEEDORES['OSMA'][1]),
   (['DBLINE', 'OCIOSTOCK', 'OSMA', 'TCG'], ['DBLINE', 'OCIOSTOCK', 'OSMA', 'TCG'], ('TCG_USER', 'TCG_PASS'),
    ('OSMA_USER', 'OSMA_PASS')))

# 🔑 (Revisión de quien dirige) LO QUE DECIDE `abrir`, ANTES de entrar en el grupo de la horaria
_dormidas = []
eq('(PD) previo: una lectura buena de hace 4 min → «reciente», su foto y cuánto hace, sin esperar',
   (epd.previo(_base_pd(5), 'TCG', ahora=lambda: _AHORA, dormir=_dormidas.append), _dormidas), (('reciente', 'A', 4), []))
eq('(PD) previo: nada en marcha y la última de hace hora y media → «leer», sin esperar',
   (epd.previo(_base_pd(90), 'TCG', ahora=lambda: _AHORA, dormir=_dormidas.append), _dormidas), (('leer', None, None), []))
_bl = _base_pd(90, extra=[{'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(1)}])
_reloj = [_AHORA]


def _duerme(s, base=_bl):
    _dormidas.append(s)
    _reloj[0] += _td(seconds=s)
    if len(_dormidas) == 3:   # la horaria acaba bien a los 45 s: la lectura de ahora
        for p in base.t['disp_pasada']:
            if p['id'] == 'L':
                p.update(estado='aplicada', creada_en=_iso(1), terminada_en=_reloj[0].isoformat())


_r = epd.previo(_bl, 'TCG', ahora=lambda: _reloj[0], dormir=_duerme)
eq('(PD) 🔑 previo: con la horaria leyendo, espera mirando la base; cuando acaba bien, sale de ella («reciente», 0 min)',
   (_r, _dormidas), (('reciente', 'L', 0), [15, 15, 15]))
_dormidas.clear()
_bl = _base_pd(90, extra=[{'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(3)}])
_r = epd.previo(_bl, 'TCG', ahora=lambda: _AHORA, dormir=_dormidas.append, espera_max_s=60)
eq('(PD) 🔴 previo: si la horaria no acaba en el tope, «fallida» con el motivo (desde cuándo), sin esperar más',
   (_r[0], 'se está leyendo ahora (la lectura horaria, desde el 27-11-2026 a las 11:27)' in (_r[1] or ''), _dormidas),
   ('fallida', True, [15, 15, 15, 15]))
_dormidas.clear()
_bl = _base_pd(90, extra=[{'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(3)}])
_r = epd.previo(_bl, 'TCG', ahora=lambda: _AHORA, dormir=_dormidas.append, espera_max_s=0)
eq('(PD) previo: con el tope a 0 (el del banco de los barridos), falla al momento', (_r[0], _dormidas), ('fallida', []))
eq('(PD) el tope de la espera es 4 min, y se mira cada 15 s', (epd.ESPERA_MAX_S, epd.ESPERA_CADA_S), (240, 15))

# 🔑 LO QUE EL BARRIDO DEJA ESCRITO (barrido.json y el «Resumen» del Excel)
_bn = _base_pd(90)
eq('(PD) la nota: leída ahora / confirmada hoy / leída hace N min, en hora de Madrid',
   [epd.nota_de(_bn, 'A', c, _AHORA, 7)['texto'] for c in ('ahora', 'confirmada', 'reciente')],
   ['leída ahora (la lectura del 27-11-2026 a las 10:01)',
    'confirmada hoy a las 11:30; el contenido es el de la lectura del 27-11-2026 a las 10:01',
    'leída hace 7 min (la lectura del 27-11-2026 a las 10:01); no se ha vuelto a leer'])
eq('(PD) …y con las dos fechas (la de la comprobación y la del contenido)',
   {k: v for k, v in epd.nota_de(_bn, 'A', 'confirmada', _AHORA).items() if k != 'texto'},
   {'como': 'confirmada', 'comprobada_en': _AHORA.isoformat(), 'contenido_de': _iso(89), 'hace': None})

# 🔑 EL PASO DE DESPUÉS DE LA LECTURA: lo de después de aplicar, aunque el barrido falle, y el vaciado que se quedó a medias
_bt = _BasePD(disp_pasada=[
    {'id': 'AP', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77},
    {'id': 'AH', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77},
    {'id': 'VA', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'run_id': 77, 'motivo': 'vaciado: x'},
    {'id': 'OT', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 78},
    {'id': 'VO', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'run_id': 78, 'motivo': 'vaciado: y'},
    {'id': 'HE', 'proveedor': 'HEO', 'estado': 'aplicada', 'run_id': 77}],
    nov_pasada=[{'pasada_id': 'AH', 'estado': 'hecha'}])
_hechos = []
_cod = epd.tras_la_lectura(_bt, 'TCG', '77', {}, {'TCG': lambda sb, env, run, pid, fila: _hechos.append((run, pid)) is None})
eq('(PD) 🔴 tras la lectura: lo de después de la aplicada de ESTE run que no lo tiene (AP), no la que ya lo tiene (AH) '
   'ni las de otro run u otro proveedor; y el vaciado de ESTE run pasa a «fallida» (el de otro, no)',
   (_cod, _hechos, {p['id']: p['estado'] for p in _bt.t['disp_pasada'] if p['id'] in ('VA', 'VO')},
    [p['motivo'] for p in _bt.t['disp_pasada'] if p['id'] == 'VA'][0].startswith(epd.PREFIJO_VACIADO)),
   (0, [('77', 'AP')], {'VA': 'fallida', 'VO': 'rechazada_vaciado'}, True))
_cod = epd.tras_la_lectura(_BasePD(disp_pasada=[{'id': 'AP', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77}]),
                           'TCG', '77', {}, {'TCG': lambda *a: False})
eq('(PD) tras la lectura: si lo de después sale mal, ROJO (la pasada sigue aplicada)', _cod, 1)
_cod = epd.tras_la_lectura(_BasePD(disp_pasada=[{'id': 'AP', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77}]),
                           'TCG', '77', {}, {'TCG': _revienta})
eq('(PD) tras la lectura: si revienta, ROJO y solo el tipo al registro (nunca lanza)', _cod, 1)
_hechos.clear()
_bo = _BasePD(disp_pasada=[{'id': 'OS', 'proveedor': 'OSMA', 'estado': 'aplicada', 'run_id': 77}],
              nov_pasada=[{'pasada_id': 'OS'}])
epd.tras_la_lectura(_bo, 'OSMA', '77', {}, {'OSMA': lambda sb, env, run, pid, fila: _hechos.append(pid) is None})
eq('(PD) tras la lectura: OSMA no tiene novedades: sus fechas de vuelta, siempre que haya una aplicada de este run',
   _hechos, ['OS'])
eq('(PD) tras la lectura: sin el id del run no se sabe qué pasadas son: ROJO', epd.tras_la_lectura(_bo, 'OSMA', '', {}), 1)
eq('(PD) el paso, por la línea de órdenes: uso y llave', (epd.principal([]), epd.principal(['--despues', 'HEO']),
                                                          epd.principal(['--despues', 'TCG'], env={})), (1, 1, 1))

# 🔴 LA MITAD ROJA, AUTOMÁTICA: cada guarda de escaner2_pro_en_directo, rota a propósito, la ve el banco.
#    (ancla única en el fuente; el módulo mutado, en este proceso; su comprobación tiene que dar «mal»)
_FUENTE_PD = open(epd.__file__, encoding='utf-8').read()


def _base_tras():
    return _BasePD(disp_pasada=[{'id': 'AP', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77},
                                {'id': 'AH', 'proveedor': 'TCG', 'estado': 'aplicada', 'run_id': 77},
                                {'id': 'VA', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'run_id': 77,
                                 'motivo': 'vaciado: x'}],
                   nov_pasada=[{'pasada_id': 'AH'}])


def _tras_bien(m):
    b, hechos = _base_tras(), []
    m.tras_la_lectura(b, 'TCG', '77', {}, {'TCG': lambda sb, env, run, pid, fila: hechos.append(pid) is None})
    return hechos == ['AP'] and [p['estado'] for p in b.t['disp_pasada'] if p['id'] == 'VA'] == ['fallida']


def _vaciado_tras(m):
    b = _base_pd(5, extra=[{'id': 'V', 'proveedor': 'TCG', 'estado': 'rechazada_vaciado', 'motivo': 'v'}])
    return m.GuardaPro(b, 'TCG').tras_aplicar('V', {'id': 'V', 'estado': 'rechazada_vaciado'})['estado'] == 'fallida'


def _osma(m, copia, prevista):
    b = _BaseOsma(copia, _fresc(prevista), disp_pasada=_APL_OSMA)
    return m.confirmar_osma(b, _FICHERO, _dt(2026, 11, 30, 9, 0, tzinfo=_tz.utc), 'r', 'escaner2', _CREADO)[0]


_LEYENDO = [{'id': 'L', 'proveedor': 'TCG', 'estado': 'leyendo', 'creada_en': _iso(3)}]
_MUTANTES_PD = [
    ('sin_freno que no cambia', "            return 'fallida', PREFIJO_VACIADO + motivo", "            return estado, motivo",
     lambda m: m.GuardaPro(None, 'TCG').sin_freno('rechazada_vaciado', 'v')[0] == 'fallida'),
    ('tras_aplicar que no toca', "        if fila.get('estado') != 'rechazada_vaciado':\n            return fila",
     "        if True:\n            return fila", _vaciado_tras),
    ('sin turno', "    if vivas:\n        desde = min(", "    if False:\n        desde = min(",
     lambda m: m.antes_de_leer(_base_pd(90, extra=_LEYENDO), 'TCG', _AHORA) is not None),
    ('sin freno', "    if n >= k:\n", "    if False:\n",
     lambda m: m.antes_de_leer(_base_pd(90, extra=_rech), 'TCG', _AHORA) is not None),
    ('«al día» sin mirar qué aplicada nombra', "        if not ult or str(ult.get('id')) not in motivo:",
     "        if not ult:", lambda m: m.decidir(_bd, 'TCG', 'D3')[0] is None),
    ('«al día» anterior vale', "        if t_ult is None or t_esta is None or t_ult > t_esta:",
     "        if t_ult is None or t_esta is None:", lambda m: m.decidir(_bd, 'TCG', 'D2')[0] is None),
    ('la lectura reciente sin tope', "        if t is None or not (timedelta(0) <= ahora - t < timedelta(minutes=minutos)):",
     "        if t is None:", lambda m: m.lectura_reciente(_base_pd(16), 'TCG', _AHORA) is None),
    ('la lectura reciente sin decidir', "            foto, _por_que = decidir(sb, proveedor, f['id'])",
     "            foto, _por_que = f['id'], None", lambda m: m.lectura_reciente(_bd4, 'TCG', _AHORA) is None),
    ('OSMA sin comparar el fichero',
     "    if not contenido or hashlib.md5(copia).hexdigest() != hashlib.md5(contenido).hexdigest():",
     "    if not contenido:", lambda m: _osma(m, b'otro', _dt(2026, 11, 27, 6, 15, tzinfo=_tz.utc)) is None),
    ('OSMA sin mirar el horario', "    if u is None or (p is not None and u < p):", "    if u is None:",
     lambda m: _osma(m, _FICHERO, _dt(2026, 11, 30, 6, 15, tzinfo=_tz.utc)) is None),
    ('previo sin tope de espera', "        if esperado >= espera_max_s:", "        if False:",
     lambda m: m.previo(_base_pd(90, extra=_LEYENDO), 'TCG', ahora=lambda: _AHORA,
                        dormir=lambda s: (_ for _ in ()).throw(RuntimeError('esperaría para siempre')),
                        espera_max_s=0)[0] == 'fallida'),
    ('tras la lectura sin pasar el vaciado a fallida', "        g.tras_aplicar(p['id'], dict(p, estado='rechazada_vaciado'))",
     "        pass", _tras_bien),
    ('tras la lectura repite lo ya hecho', "            ya += 1\n            continue", "            ya += 1", _tras_bien),
]
for _nombre, _antes, _despues, _bien in _MUTANTES_PD:
    eq('(PD) mutante «%s»: el ancla es única y, sin mutar, la comprobación da bien' % _nombre,
       (_FUENTE_PD.count(_antes), bool(_bien(epd))), (1, True))
    _m = _types.ModuleType('mutante_pd')
    _m.__file__ = epd.__file__
    exec(compile(_FUENTE_PD.replace(_antes, _despues), 'mutante_pd', 'exec'), _m.__dict__)
    try:
        _vista = not _bien(_m)
    except Exception:  # noqa: BLE001 — revienta: también lo ve
        _vista = True
    eq('(PD) 🔴 mutante «%s»: el banco lo ve (ROJO)' % _nombre, _vista, True)

# Los cuatro workflows del barrido: el grupo de la horaria en la lectura, sus secretos y sus dependencias
import yaml as _yaml  # noqa: E402
for _p, _sec in (('tcg', ('TCG_USER', 'TCG_PASS')), ('dbline', ('DBLINE_USER', 'DBLINE_PASS')),
                 ('ociostock', ('OCIOSTOCK_FEED_URL',)), ('osma', ('OSMA_USER', 'OSMA_PASS'))):
    _raiz = os.path.dirname(os.path.abspath(__file__))
    _wb = _yaml.safe_load(open(os.path.join(_raiz, '.github', 'workflows', 'escaner2-%s-barrido.yml' % _p), encoding='utf-8'))
    _wh = _yaml.safe_load(open(os.path.join(_raiz, '.github', 'workflows', 'escaner2-%s-disponibilidad.yml' % _p),
                               encoding='utf-8'))
    _grupo_h = _wh['concurrency']['group']
    _lect = [j for n, j in _wb['jobs'].items() if n.startswith('barrer') and n != 'barrer_ya']
    _pasos = [s for j in _lect for s in j['steps'] if 'barrido.py --leer' in str(s.get('run', ''))]
    _barr = [s for j in _lect for s in j['steps'] if str(s.get('run', '')).strip().endswith('_barrido.py')]
    _desp = [s for j in _lect for s in j['steps'] if '--despues' in str(s.get('run', ''))]
    _pip_h = {x for s in _wh['jobs']['leer']['steps'] for x in str(s.get('run', '')).split() if '==' in x}
    _pip_b = [{x for s in j['steps'] for x in str(s.get('run', '')).split() if '==' in x} for j in _lect]
    _env_h = {k for s in _wh['jobs']['leer']['steps'] if 'disponibilidad.py' in str(s.get('run', ''))
              and '--rescate' not in str(s.get('run')) for k in (s.get('env') or {})}
    _J = _wb['jobs']
    _ab = _J['abrir']
    eq('(PD) workflow %s: abrir (decide, sin grupo) → barrer_ya (la lectura reciente, sin grupo) | la(s) lectura(s) en el '
       'grupo de la horaria (%s) → rescate final (always); el barrido, en su grupo PRO; y solo lee el repo' % (_p, _grupo_h),
       (list(_J)[0], list(_J)[1], list(_J)[-1], {j['concurrency']['group'] for j in _lect},
        'concurrency' in _J['barrer_ya'] or 'concurrency' in _ab, _wb['concurrency']['group'], _J['rescate']['if'],
        _J['barrer_ya']['if'], _J['barrer']['if'], _wb.get('permissions')),
       ('abrir', 'barrer_ya', 'rescate', {_grupo_h}, False, _grupo_h + '-pro', 'always()',
        "needs.abrir.outputs.camino == 'reciente'", "needs.abrir.outputs.camino == 'leer'", {'contents': 'read'}))
    eq('(PD) workflow %s: abrir deja pasada, camino, foto y hace, y tiene su rescate (si muere tras abrir la pasada)' % _p,
       (sorted(_ab['outputs']), [s['if'] for s in _ab['steps'] if 'rescate' in str(s.get('run', ''))],
        ['--abrir' in str(s.get('run', '')) for s in _ab['steps']].count(True)),
       (['camino', 'foto', 'hace', 'pasada'], ['failure() || cancelled()'], 1))
    eq('(PD) workflow %s: barrer_ya sale de la foto que dice abrir (FOTO, «reciente»), sin secretos del proveedor' % _p,
       [(s['env'].get('FOTO'), s['env'].get('FOTO_COMO'), s['env'].get('ESCANER2_PASADA'), bool(set(_sec) & set(s['env'])))
        for s in _J['barrer_ya']['steps'] if 'barrido.py' in str(s.get('run', ''))],
       [('${{ needs.abrir.outputs.foto }}', 'reciente', '${{ needs.abrir.outputs.pasada }}', False)])
    eq('(PD) workflow %s: 🔑 la lectura, en SU paso (--leer, separable), y el barrido en otro, detrás, solo si la lectura '
       'da foto, con la foto de ese paso y SIN secretos del proveedor' % _p,
       [(s.get('if'), s['env'].get('FOTO'), s['env'].get('FOTO_COMO'), bool(set(_sec) & set(s['env']))) for s in _barr],
       [("steps.leer.outputs.camino == 'foto'", '${{ steps.leer.outputs.foto }}', '${{ steps.leer.outputs.como }}', False)]
       * len(_lect))
    eq('(PD) workflow %s: el paso de la lectura lleva los secretos y las claves del paso horario (menos sus inputs: '
       'FICHAS_MAX, LISTADO, el MODO de OSMA), y las dependencias de la horaria' % _p,
       (all(set(_sec) <= set(s['env']) for s in _pasos),
        sorted((_env_h - {'FICHAS_MAX', 'LISTADO', 'INTENTO', 'MODO'}) - set(_pasos[0]['env'])),
        all(_pip_h <= b for b in _pip_b), len(_pasos)), (True, [], True, 3 if _p == 'tcg' else 1))
    eq('(PD) workflow %s: 🔴 lo de después, en SU paso de cada lectura, SIEMPRE (aunque el barrido falle), con su tope, '
       'detrás del barrido y con las claves del horario (menos sus inputs)' % _p,
       ([(s['if'], bool(s.get('timeout-minutes')), s['run'].split()[-1]) for s in _desp],
        all(j['steps'].index([s for s in j['steps'] if '--despues' in str(s.get('run', ''))][0])
            > j['steps'].index([s for s in j['steps'] if 'barrido.py' in str(s.get('run', ''))][0]) for j in _lect),
        sorted((_env_h - {'FICHAS_MAX', 'LISTADO', 'INTENTO', 'MODO'}) - set(_desp[0]['env']))),
       ([('always()', True, epd.PROVEEDORES and {'tcg': 'TCG', 'dbline': 'DBLINE', 'ociostock': 'OCIOSTOCK',
                                                 'osma': 'OSMA'}[_p])] * len(_lect), True, []))
    eq('(PD) workflow %s: los secretos del proveedor SOLO en los pasos de la lectura y de lo de después (ni en abrir, ni '
       'en barrer_ya, ni en los rescates)' % _p,
       sorted({n for n, j in _wb['jobs'].items() for s in j['steps'] for k in (s.get('env') or {})
               if k in _sec and s not in _pasos and s not in _desp}), [])
    eq('(PD) workflow %s: las salidas de cada lectura (pared, pasada) salen del paso de la lectura' % _p,
       {n: j.get('outputs') for n, j in _J.items() if n.startswith('barrer_') is False and n.startswith('barrer')
        and j.get('outputs')}, {'barrer': {'pared': '${{ steps.leer.outputs.pared }}',
                                           'pasada': '${{ steps.leer.outputs.pasada }}'}} if _p == 'tcg' else {})

print()
if fallos:
    print('ROJO: %d fallo(s): %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: la foto de disponibilidad guarda todo lo que HEO da con código de barras, con las reglas del escáner 2; '
      'una descarga cortada (más allá de la tolerancia) no se aplica; lo que llega sin dato va marcado; '
      'una caída aceptada sale en rojo; cuadra y no toca nada más.')
