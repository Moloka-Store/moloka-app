# -*- coding: utf-8 -*-
"""Banco de la FOTO DE DISPONIBILIDAD DE HEO (encargo E, tramo 3, pieza 1, 29-sep-2026).

SIN RED, SIN SECRETOS Y SIN BASE: se ejecuta el modulo de verdad (escaner2_disponibilidad.py, sobre el
motor del escaner 2 y sus piezas heredadas) con filas con la MISMA FORMA que devuelve
`descargar_catalogo_heo(con_chase=True)`. Los codigos de las cajas con chase son reales (los del banco
de las cajas, pasada 8ac9a9de); los precios son redondos: el repo es publico y el coste de HEO no se
publica, y ninguna regla depende de cual sea.

QUE PRUEBA:
  (A) TODO entra: todas las marcas, disponible y agotado, una fila por producto de HEO.
  (B) LAS MISMAS REGLAS QUE EL BARRIDO: en lo disponible, cada fila de la foto del barrido (modo
      'todas') sale aqui IGUAL (EAN de cruce, caja, unidades, chase, precio de catalogo y por unidad);
      lo que el barrido aparta sale aqui con su regla; y lo que el barrido quita por duplicado, aqui
      esta (la llave es el producto, no el EAN).
  (C) La trampa del precio de caja: precio de catalogo y por unidad SEPARADOS, con las unidades.
  (D) El cuadre: leidas = disponibles + agotados = lo que devolvio descargar_heo.
  (E) Una lectura con la llave rota (sin numero o repetido) no se sube.
  (F) Los recuentos del log: los tres numeros, y None (no cero) si falta uno.
  (G) EL PROGRAMA, POR ESTRUCTURA: solo toca disp_pasada, disp_lectura y disp_aplicar_pasada; sin la
      llave de servicio aborta antes de abrir ningun cliente; y el workflow no lleva reloj de GitHub
      ni comparte grupo con el barrido.
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
    {'producto_heo': 'FK72611-01', 'nombre': 'Demon Slayer: Kimetsu no Yaiba POP! Animation Vinyl Figuren Susamaru w/Ch 9 cm', 'ean_caja': '889698726115', 'marca': 'Funko', 'precio_caja': 8.62, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''},
    # Caja con chase de la que no se puede sacar el EAN de la figura (ni GS1 ni EAN, y numero no FK).
    {'producto_heo': 'XX00001', 'nombre': 'Figura rara w/Chase Surtido (6)', 'ean_caja': 'ABC', 'marca': 'Funko', 'precio_caja': 30.0, 'estado': 'disponible', 'imagen': '', 'link_amazon': ''},
]

filas, cuentas = dp.construir_disponibilidad(FILAS, CHASE, M)
por = {f['producto_prov']: f for f in filas}

# ── (A) TODO ENTRA ───────────────────────────────────────────────────────────────────────
eq('(A) una fila por producto de HEO, todas las marcas, disponible o no', sorted(por), sorted(
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
        dp.construir_disponibilidad(filas_mal, CHASE, M)
        eq('(E) un producto %s tumba la lectura' % nombre, 'pasó', 'LecturaInvalida')
    except dp.LecturaInvalida:
        eq('(E) un producto %s tumba la lectura' % nombre, True, True)

# ── (F) LOS RECUENTOS DEL LOG ────────────────────────────────────────────────────────────
LOG = ("  catalog/products: 23608 items | 48 paginas | pageSize 500\n"
       ">>> Cruzando: 23608 productos | 23608 precios | 23608 disponibilidades\n"
       ">>> Catalogo cruzado: 22452 filas con EAN (descartadas 1156 sin GTIN)\n")
eq('(F) los tres números del log', dp.recuentos_del_log(LOG), {'n_declarado': 23608, 'n_crudo': 23608, 'n_sin_gtin': 1156})
eq('(F) uno que falta es None, no cero', dp.recuentos_del_log(LOG.splitlines()[1])['n_sin_gtin'], None)

# ── (G) EL PROGRAMA Y EL WORKFLOW, POR ESTRUCTURA ────────────────────────────────────────
AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, 'escaner2_heo_disponibilidad.py'), encoding='utf-8') as fh:
    arbol = ast.parse(fh.read())
tablas, funciones = set(), set()
for nodo in ast.walk(arbol):
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in ('table', 'rpc') and nodo.args:
        a = nodo.args[0]
        (tablas if nodo.func.attr == 'table' else funciones).add(a.value if isinstance(a, ast.Constant) else '<no literal>')
eq('(G) el programa solo toca disp_pasada y disp_lectura (ni escaner_memoria, ni escaner2_*, ni productos)',
   sorted(tablas), ['disp_lectura', 'disp_pasada'])
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
eq('(G) su grupo de concurrencia es el suyo, no el del barrido y el cruce',
   [l.strip() for l in lineas if l.strip().startswith('group:')], ['group: escaner2-heo-disponibilidad'])
eq('(G) corre este programa, y el rescate si falla',
   [l.strip() for l in lineas if l.strip().startswith('run: python')],
   ['run: python -u escaner2_heo_disponibilidad.py', 'run: python -u escaner2_heo_disponibilidad.py --rescate'])

print()
if fallos:
    print('ROJO: %d fallo(s): %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: la foto de disponibilidad guarda TODO HEO con las reglas del escáner 2, cuadra y no toca nada más.')
