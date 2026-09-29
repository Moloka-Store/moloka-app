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
  (K) CON LA DESCARGA HEREDADA DE VERDAD (solo su `_get`, la red, cambiado por paginas en memoria): el
      envoltorio de `_paginar` coge las listas que usa `descargar_catalogo_heo`, las filas suben
      marcadas y `_paginar` queda como estaba.
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
filas, cuentas = dp.construir_disponibilidad(FILAS, CHASE, M, con_precio=TODOS, con_disponibilidad=TODOS)
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

# ── (D) EL CUADRE ────────────────────────────────────────────────────────────────────────
eq('(D) leídas = disponibles + agotados = lo que devolvió descargar_heo',
   (cuentas['n_leidas'], cuentas['n_disponibles'] + cuentas['n_agotados'], cuentas['n_devueltos']), (13, 13, 13))
eq('(D) disponibles y agotados, contados', (cuentas['n_disponibles'], cuentas['n_agotados']), (10, 3))
eq('(D) las reglas, contadas', cuentas['por_regla'], {'chase_suelto': 1, 'ean_forma_rara': 1, 'caja_chase_sin_figura': 1})
eq('(D) las reglas son las que admite la base', dp.REGLAS, ('chase_suelto', 'ean_forma_rara', 'caja_chase_sin_figura'))

# ── (E) LA LLAVE ROTA NO SE SUBE ─────────────────────────────────────────────────────────
for nombre, filas_mal in (('repetido', FILAS + [dict(FILAS[0])]), ('sin número', FILAS + [fila('', '0889698000001', 'x', 'Funko', 1.0, 'disponible')])):
    try:
        dp.construir_disponibilidad(filas_mal, CHASE, M, con_precio=TODOS, con_disponibilidad=TODOS)
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
entera = dp.recuentos_del_log(LOG)
eq('(H) la descarga del run real está entera', dp.descarga_cortada(entera, 10), [])
cortada = dp.recuentos_del_log(LOG.replace('23049 disponibilidades', '22549 disponibilidades'))
eq('(H) 🔴 con una página de disponibilidades menos, se dice (y es lo que dejaría 500 agotados falsos)',
   dp.descarga_cortada(cortada, 10), ['disponibilidades: HEO declara 23049 y llegaron 22549 (tolerancia 10)'])
eq('(H) con los precios cortados, también',
   dp.descarga_cortada(dp.recuentos_del_log(LOG.replace('23049 precios', '23000 precios')), 10),
   ['precios: HEO declara 23049 y llegaron 23000 (tolerancia 10)'])
sin_pag1 = dp.recuentos_del_log('\n'.join(l for l in LOG.splitlines() if 'catalog/availabilities' not in l))
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
for mala in (None, -1, True, '10'):
    eq('(H) sin tolerancia válida (%r), no se da por entera' % (mala,),
       dp.descarga_cortada(entera, mala)[0].startswith('sin tolerancia'), True)

# ── (J) SIN DATO NO ES AGOTADO ───────────────────────────────────────────────────────────
# Lo que la heredada da cuando un producto no llegó en availabilities: agotado y sin «GREEN/RED».
FILAS_J = [dict(f, estado='agotado', disponibilidad='') if f['productNumber'] == 'FK67928' else
           (dict(f, precio='', precio_base='') if f['productNumber'] == 'HAS0002' else dict(f)) for f in FILAS]
CHASE_J = [dict(c, estado='agotado') if c['producto_heo'] == 'FK87245' else dict(c) for c in CHASE]
filas_j, cuentas_j = dp.construir_disponibilidad(FILAS_J, CHASE_J, M, con_precio=TODOS - {'HAS0002'},
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

# ── (G) EL PROGRAMA Y EL WORKFLOW, POR ESTRUCTURA ────────────────────────────────────────
AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), encoding='utf-8') as fh:
    arbol = ast.parse(fh.read())
tablas, funciones = set(), set()
for nodo in ast.walk(arbol):
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in ('table', 'rpc') and nodo.args:
        a = nodo.args[0]
        (tablas if nodo.func.attr == 'table' else funciones).add(a.value if isinstance(a, ast.Constant) else '<no literal>')
eq('(G) el programa solo toca disp_pasada y disp_lectura, y lee disp_parametros (ni escaner_memoria, ni escaner2_*, ni productos)',
   sorted(tablas), ['disp_lectura', 'disp_parametros', 'disp_pasada'])
acciones_parametros = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Call)
                       and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'table'
                       and n.value.args and isinstance(n.value.args[0], ast.Constant) and n.value.args[0].value == 'disp_parametros'}
eq('(G) …y a disp_parametros solo le hace select', acciones_parametros, {'select'})
with open(os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), encoding='utf-8') as fh:
    _prog = fh.read()
eq('(G) la heredada no se escribe: solo se envuelve su _paginar en memoria y se deja como estaba (y el programa no abre ficheros)',
   ("hd._paginar = _paginar_que_guarda" in _prog, "hd._paginar = paginar" in _prog,
    any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'open' for n in ast.walk(arbol))),
   (True, True, False))
eq('(G) y solo llama a la función disp_aplicar_pasada', sorted(funciones), ['disp_aplicar_pasada'])
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

    def select(self, *_a, **_k):
        return self._accion('select', _a)

    def eq(self, *args):
        self.op.setdefault('filtros', []).append(args)
        return self

    def execute(self):
        self.base.ops.append(self.op)
        datos = []
        if self.op['tabla'] == 'disp_pasada' and self.op['accion'] == 'insert':
            datos = [{'id': 'PASADA-1'}]
        elif self.op['tabla'] == 'disp_pasada' and self.op['accion'] == 'select':
            datos = [self.base.fila_final]
        elif self.op['tabla'] == 'disp_parametros' and self.op['accion'] == 'select':
            datos = self.base.parametros
        return types.SimpleNamespace(data=datos)


class _BaseDeMentira:
    def __init__(self):
        self.ops = []
        self.fila_final = dict({k: 0 for k in (
            'primera', 'n_crudo', 'n_leidas', 'n_disponibles', 'n_agotados', 'n_entran', 'n_vuelven', 'n_salen',
            'n_a_disponible', 'n_a_agotado', 'n_cambio_precio', 'n_ausentes', 'n_en_catalogo',
            'n_disponibles_estado', 'dif_productos', 'dif_precios', 'dif_disponibilidades', 'n_sin_dato_disponibilidad',
            'n_sin_dato_precio')}, estado='aplicada', motivo=None, caida_aceptada=False)
        self.parametros = [{'tolerancia_endpoint': 10}]

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, params):
        base = self

        class _Llamada:
            def execute(self):
                base.ops.append({'tabla': 'rpc:' + nombre, 'accion': 'rpc', 'datos': params})
                return types.SimpleNamespace(data={'estado': 'aplicada'})
        return _Llamada()


def correr_programa(disponibilidades_declaradas=None, sin_dispo=(), sin_precio=(), parametros=None, caida=False,
                    modulo_descarga=None):
    """El programa de verdad, importado con `supabase` y la descarga heredada cambiados por dobles. La
    descarga de mentira hace como la de verdad: pide cada endpoint a SU `_paginar` (buscándolo en su
    módulo en cada llamada), junta por número y dice en el log lo declarado y lo llegado. Los de
    `sin_dispo` / `sin_precio` no vienen en esa lista (y salen agotados / sin precio, como en la
    heredada)."""
    base = _BaseDeMentira()
    if parametros is not None:
        base.parametros = parametros
    if caida:
        base.fila_final.update(caida_aceptada=True, motivo='caída aceptada tras 3 rechazos estables (±2.0 %): …')
    falso_supabase = types.ModuleType('supabase')
    falso_supabase.create_client = lambda url, llave: base
    falsa_descarga = types.ModuleType('escaner2_heredado_descarga')
    numeros = [f['productNumber'] for f in FILAS] + [c['producto_heo'] for c in CHASE]
    listas = {'catalog/products': [{'productNumber': pn} for pn in numeros + ['SIN-GTIN']],
              'catalog/prices': [{'productNumber': pn} for pn in numeros if pn not in sin_precio],
              'catalog/availabilities': [{'productNumber': pn} for pn in numeros if pn not in sin_dispo]}

    def _paginar(endpoint, max_paginas=None):
        return listas[endpoint]

    def descargar_catalogo_heo(con_chase=False):
        productos = falsa_descarga._paginar('catalog/products')
        precios = {p['productNumber']: p for p in falsa_descarga._paginar('catalog/prices')}
        dispo = {a['productNumber']: a for a in falsa_descarga._paginar('catalog/availabilities')}
        declaradas = len(dispo) if disponibilidades_declaradas is None else disponibilidades_declaradas
        print('  catalog/products: %d items | 1 paginas | pageSize 500' % len(productos))
        print('  catalog/prices: %d items | 1 paginas | pageSize 500' % len(precios))
        print('  catalog/availabilities: %d items | 1 paginas | pageSize 500' % declaradas)
        print('>>> Cruzando: %d productos | %d precios | %d disponibilidades' % (len(productos), len(precios), len(dispo)))
        print('>>> Catalogo cruzado: %d filas con EAN (descartadas 1 sin GTIN)' % len(FILAS))
        filas_d = [dict(f, **({'estado': 'agotado', 'disponibilidad': ''} if f['productNumber'] not in dispo else {}),
                        **({'precio': '', 'precio_base': ''} if f['productNumber'] not in precios else {})) for f in FILAS]
        chase_d = [dict(c, **({'estado': 'agotado'} if c['producto_heo'] not in dispo else {}),
                        **({'precio_caja': None} if c['producto_heo'] not in precios else {})) for c in CHASE]
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
eq('(I) …llama UNA vez a disp_aplicar_pasada con su pasada',
   [o['datos'] for o in ops if o['tabla'].startswith('rpc:')], [{'p_pasada': 'PASADA-1'}])
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
cuentas_subidas = [o['datos'] for o in _de(ops, 'disp_pasada', 'update') if 'n_leidas' in o['datos']][0]
eq('(I) …y la pasada con sus recuentos de sin dato',
   (cuentas_subidas['n_sin_dato_disponibilidad'], cuentas_subidas['n_sin_dato_precio'], cuentas_subidas['n_leidas']), (2, 1, 13))
eq('(I) …el log lo dice', 'sin dato de disponibilidad 2, de precio 1' in _texto, True)

ops, codigo, _texto = correr_programa(parametros=[])
eq('(I) 🔴 sin tolerancia en la base: rojo, sin bajar nada de HEO ni subir nada',
   (codigo, _de(ops, 'disp_lectura', 'insert'), 'Bajando' in _texto or 'catalog/products' in _texto), (1, [], False))
eq('(I) …y la pasada queda fallida diciendo por qué',
   (_de(ops, 'disp_pasada', 'update')[-1]['datos']['estado'], 'sin tolerancia' in _de(ops, 'disp_pasada', 'update')[-1]['datos']['motivo']),
   ('fallida', True))

ops, codigo, _texto = correr_programa(caida=True)
eq('(I) 🔴 una CAÍDA ACEPTADA: aplicada, pero el run en ROJO y con su aviso',
   (codigo, [o['datos'] for o in ops if o['tabla'].startswith('rpc:')], 'CAIDA_ACEPTADA: la pasada PASADA-1' in _texto,
    'PASADA APLICADA' in _texto), (1, [{'p_pasada': 'PASADA-1'}], True, True))

# ── (K) CON LA DESCARGA HEREDADA DE VERDAD ───────────────────────────────────────────────
# Solo se cambia `_get` (la red) por páginas en memoria; `_paginar` y `descargar_catalogo_heo` son los
# de verdad. R1 no llega en availabilities, R2 no llega en prices, R3 (caja con chase) llega en las
# dos, y R4 no trae GTIN.
_env_heo = {k: os.environ.get(k) for k in ('HEO_USER', 'HEO_PASS')}
_mod_antes = sys.modules.pop('escaner2_heredado_descarga', None)
os.environ.update(HEO_USER='u', HEO_PASS='p')
try:
    import escaner2_heredado_descarga as hd_real
finally:
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


PAGINAS = {'catalog/products': [_prod('R1', 'Figura uno', 'Hasbro', '5010993999990'), _prod('R2', 'Figura dos', 'Hasbro', '5010993999991'),
                                _prod('R3', 'Figura tres w/Chase Surtido (6)', 'Funko', '889698862646'),
                                _prod('R4', 'Figura sin código', 'Hasbro', '')],
           'catalog/prices': [_precio('R1', 10.0), _precio('R3', 60.0)],
           'catalog/availabilities': [_dispo('R2'), _dispo('R3')]}


def _get_en_memoria(url, page):
    contenido = PAGINAS[url[len(hd_real.BASE) + 1:]]
    return {'content': contenido, 'pagination': {'totalPages': 1, 'totalElements': len(contenido), 'pageSize': 500}}


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

print()
if fallos:
    print('ROJO: %d fallo(s): %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: la foto de disponibilidad guarda todo lo que HEO da con código de barras, con las reglas del escáner 2; '
      'una descarga cortada (más allá de la tolerancia) no se aplica; lo que llega sin dato va marcado; '
      'una caída aceptada sale en rojo; cuadra y no toca nada más.')
