# -*- coding: utf-8 -*-
"""Banco de las guardas de la memoria del escaner (moloka_escaner_nube.py).

QUE PRUEBA, Y POR QUE NO SE PODIA PROBAR ANTES.
   `moloka_escaner_nube.py` no se puede importar: en la linea 46 crea el cliente
   de Keepa con la clave del entorno y SALE A LA RED. Por eso las cuatro
   decisiones de este encargo se sacaron a funciones PURAS, y por eso este banco
   las extrae del fichero real con `ast` -- POR ESTRUCTURA, buscando el `def`
   por su nombre en el arbol, no con un grep -- y las EJECUTA. No prueba una
   copia: prueba el codigo que corre en produccion. Si alguien borra o renombra
   una funcion, este fichero se pone rojo por no encontrarla.

LOS CUATRO FALLOS SILENCIOSOS QUE CIERRA (3-sep-2026):
   1. El blindaje anti-vaciado comparaba el catalogo crudo contra TODA la
      memoria (ausentes incluidos). Como escaner_memoria es un MAESTRO y el
      ausente se MARCA en vez de borrarse, el umbral crecia cada mes solo.
      Medido en produccion: HEO, 9.193 fichas en memoria / 2.471 presentes /
      ~1.838 en el catalogo -> el blindaje saltaba TODOS los dias y 625 fichas
      llevaban meses 'presentes' sin poder marcarse agotadas.
   2. Un producto con un pais perdido en la Fase 2 SI se grababa en la memoria,
      con sus paises a medias -> manana 'sin_cambios' -> el pase 'nuevos' lo
      filtraba fuera -> ese pais no se volvia a mirar nunca.
   3. Un lote de escaner_memoria que fallaba era un 'AVISO' y el run seguia VERDE.
   4. Las cuatro salidas del arranque hacian sys.exit(0): un run que no escanea
      nada se veia EXACTAMENTE igual que uno que escaneo todo.

LAS DOS DIRECCIONES. Cada caso se ha visto rojo rompiendo a mano lo que protege
   (comprobado antes de commitear, uno a uno). El caso (A2) es el mas importante:
   es la regla VIEJA sobre las cifras REALES de HEO, y esta puesta para que
   quede escrito que con ella el blindaje saltaba.
"""
import ast
import io
import sys
from contextlib import redirect_stdout

RUTA = 'moloka_escaner_nube.py'
FUENTE = io.open(RUTA, encoding='utf-8').read()
ARBOL = ast.parse(FUENTE, RUTA)

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ---------------------------------------------------------------------------
# Extraer y EJECUTAR las funciones reales del escaner (por estructura, con ast)
# ---------------------------------------------------------------------------
def sacar_def(nombre):
    for n in ARBOL.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
    print('XX la funcion %s() ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


NOMBRES = ('abortar', 'presentes_en_memoria', 'catalogo_parcial', 'eans_con_pais_perdido')
_ns = {'sys': sys}
_mod = ast.Module(body=[sacar_def(n) for n in NOMBRES], type_ignores=[])
exec(compile(ast.fix_missing_locations(_mod), RUTA, 'exec'), _ns)
abortar = _ns['abortar']
presentes_en_memoria = _ns['presentes_en_memoria']
catalogo_parcial = _ns['catalogo_parcial']
eans_con_pais_perdido = _ns['eans_con_pais_perdido']
print('extraidas de %s: %s' % (RUTA, ', '.join(NOMBRES)))
print()


def ficha(presente, pa=1.0):
    return {'pa': pa, 'presente': presente, 'ean_db': '0000000000000'}


# --- (A) El blindaje anti-vaciado: contra los PRESENTES ---------------------
# Las cifras de HEO medidas en produccion el 3-sep-2026 (escaner_memoria).
HEO_MEMORIA, HEO_PRESENTES, HEO_CRUDO, UMBRAL = 9193, 2471, 1838, 0.35
mem_heo = dict((i, ficha(i < HEO_PRESENTES)) for i in range(HEO_MEMORIA))

eq('(A) los presentes se cuentan bien', presentes_en_memoria(mem_heo), HEO_PRESENTES)
eq('(A1) HEO contra los PRESENTES -> el blindaje NO salta',
   catalogo_parcial(HEO_CRUDO, HEO_PRESENTES, UMBRAL)[0], False)
# La regla VIEJA, sobre las mismas cifras. Es el bug, escrito.
eq('(A2) 🔴 HEO contra TODA la memoria -> saltaba (el bug)',
   catalogo_parcial(HEO_CRUDO, HEO_MEMORIA, UMBRAL)[0], True)
eq('(A) el corte que se imprime es el 35% de los presentes',
   round(catalogo_parcial(HEO_CRUDO, HEO_PRESENTES, UMBRAL)[1], 2), 864.85)

# El blindaje SIGUE protegiendo de lo que vino a proteger: media descarga.
eq('(A) media descarga de HEO (500 filas) -> SI salta',
   catalogo_parcial(500, HEO_PRESENTES, UMBRAL)[0], True)
eq('(A) justo por debajo del corte -> salta', catalogo_parcial(864, 2471, UMBRAL)[0], True)
eq('(A) justo por encima del corte -> no salta', catalogo_parcial(865, 2471, UMBRAL)[0], False)
# Los dos casos en que no hay con que medir: no se blinda (y no se revienta).
eq('(A) sin catalogo leido (N_CRUDO None) -> no salta',
   catalogo_parcial(None, 2471, UMBRAL), (False, None))
eq('(A) memoria vacia o toda ausente -> no salta',
   catalogo_parcial(0, 0, UMBRAL), (False, None))
eq('(A) memoria toda AUSENTE: 0 presentes', presentes_en_memoria({1: ficha(False)}), 0)

# 🔒 LA INVARIANTE QUE HACE EL CAMBIO SEGURO PARA LOS OTROS PROVEEDORES:
# presentes <= memoria, luego el umbral nuevo <= el viejo. Ningun proveedor que
# hoy marque agotados puede dejar de marcarlos por este cambio.
_regresion = [(crudo, memo, pres)
              for crudo, memo, pres in ((1838, 9193, 2471), (5000, 14082, 4144),
                                        (4696, 4696, 1525), (3000, 3811, 2921), (10, 100, 1))
              if catalogo_parcial(crudo, memo, UMBRAL)[0] is False
              and catalogo_parcial(crudo, pres, UMBRAL)[0] is True]
eq('(A) 🔒 el umbral nuevo nunca es mas duro que el viejo', _regresion, [])


# --- (B) Fase 2: los paises perdidos se quedan fuera de la memoria ----------
INFOS = [
    {'ean': '111', 'asin': 'B01'},          # se le perdio ES
    {'ean': '222', 'asin': 'B02'},          # entero
    {'ean': '333', 'asin': 'B03'},          # se le perdieron IT y FR
    {'ean': '444', 'asin': 'B02'},          # 2 EAN con el MISMO asin bueno
]
PERDIDOS = [('B01', 'ES'), ('B03', 'IT'), ('B03', 'FR')]

eq('(B) sin perdidas, nadie se queda fuera', eans_con_pais_perdido([], INFOS), set())
eq('(B) 🔴 un solo pais perdido ya deja el producto fuera',
   eans_con_pais_perdido(PERDIDOS, INFOS), {'111', '333'})
eq('(B) el que se escaneo entero SI se graba',
   '222' in eans_con_pais_perdido(PERDIDOS, INFOS), False)
# Dos EAN con el mismo ASIN: se saltan los dos. Dejar fuera de mas cuesta un
# reintento; dejar fuera de menos condena a ese pais a no mirarse nunca.
eq('(B) dos EAN con el mismo ASIN perdido -> los dos fuera',
   eans_con_pais_perdido([('B02', 'FR')], INFOS), {'222', '444'})
# El puente de chase mete su ean como str y el checkpoint lo devuelve del JSON:
# la comparacion del bucle es str(f['ean_in']), asi que aqui tambien.
eq('(B) el ean sale siempre como texto',
   eans_con_pais_perdido([('B09', 'ES')], [{'ean': 8412345678901, 'asin': 'B09'}]),
   {'8412345678901'})
eq('(B) un item sin ean no revienta',
   eans_con_pais_perdido([('B09', 'ES')], [{'ean': None, 'asin': 'B09'}]), set())


# --- (C) Un run que no escanea NO es verde ---------------------------------
def correr_abortar(motivo):
    buf = io.StringIO()
    codigo = 'NO SALIO'
    try:
        with redirect_stdout(buf):
            abortar(motivo)
    except SystemExit as e:
        codigo = e.code
    return codigo, buf.getvalue().strip()


_cod, _txt = correr_abortar('proveedor desconocido')
eq('(C) 🔴 abortar() sale en ROJO (exit 1)', _cod, 1)
eq('(C) y deja la linea grepable', _txt, 'ESCANEO_NO_EJECUTADO: proveedor desconocido')
eq('(C) el motivo viaja entero', correr_abortar('falta el catalogo de TCG')[1],
   'ESCANEO_NO_EJECUTADO: falta el catalogo de TCG')


# --- (D) Que las guardas esten PUESTAS, no solo escritas --------------------
# 🔴 «Si desactivas la feature a mano y el banco sigue verde, el banco no la
#    esta probando» (CLAUDE.md §3). Los tres asserts de abajo miran el ARBOL
#    del fichero real: no que la funcion exista, sino que se USE donde toca.

# (D1) Las salidas que NO escanean llaman a abortar(). Cuatro son las del
#      arranque de este encargo (recado ilegible, proveedor desconocido, catalogo
#      ausente, columnas no detectadas). Las dos de la Celda 5 llegaron el
#      3-sep-2026 con la guarda del catalogo propio (lectura fallida y 0 filas)
#      y tienen su banco aparte, en test_escaner_catalogo_propio.py.
_llamadas_abortar = [n for n in ast.walk(ARBOL)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == 'abortar']
eq('(D1) las 6 salidas sin escaneo van por abortar()', len(_llamadas_abortar), 6)

# (D2) El bucle que graba la memoria salta los EAN con pais perdido.
#      Se busca el `for f in filas_hoy:` en el arbol y se mira SU cuerpo.
_bucle_mem = None
for _n in ast.walk(ARBOL):
    if (isinstance(_n, ast.For) and isinstance(_n.target, ast.Name) and _n.target.id == 'f'
            and isinstance(_n.iter, ast.Name) and _n.iter.id == 'filas_hoy'):
        _bucle_mem = _n
        break
eq('(D2) existe el bucle `for f in filas_hoy`', _bucle_mem is not None, True)
_guardas_del_bucle = set()
if _bucle_mem is not None:
    for _h in _bucle_mem.body:
        if isinstance(_h, ast.If) and any(isinstance(_c, ast.Continue) for _c in _h.body):
            _guardas_del_bucle |= {_x.id for _x in ast.walk(_h.test) if isinstance(_x, ast.Name)}
eq('(D2) salta los lotes perdidos de la Fase 1',
   'EANS_NO_PREGUNTADOS' in _guardas_del_bucle, True)
eq('(D2) 🔴 y salta los paises perdidos de la Fase 2',
   '_eans_pais_perdido' in _guardas_del_bucle, True)

# (D3) La regla VIEJA ya no esta en el fichero: ningun `UMBRAL_PARCIAL * len(mem)`.
#      Por estructura (un BinOp de multiplicacion), que un grep casaria tambien
#      dentro de un comentario -- y este fichero tiene comentarios que la citan.
_regla_vieja = 0
for _n in ast.walk(ARBOL):
    if isinstance(_n, ast.BinOp) and isinstance(_n.op, ast.Mult):
        _lados = {ast.dump(_n.left), ast.dump(_n.right)}
        _tiene_umbral = any("id='UMBRAL_PARCIAL'" in _l for _l in _lados)
        _tiene_len_mem = any("id='len'" in _l and "id='mem'" in _l for _l in _lados)
        if _tiene_umbral and _tiene_len_mem:
            _regla_vieja += 1
eq('(D3) 🔴 no queda ningun `UMBRAL_PARCIAL * len(mem)` en el codigo', _regla_vieja, 0)
# La otra mitad del ancla: el fichero SI sigue hablando de len(mem) en la prosa
# del comentario que explica el cambio. Sin esto, el 0 de arriba podria ser
# verde simplemente porque nadie nombra ya la regla vieja.
eq('(D3) el motivo del cambio sigue escrito en el fichero', 'len(mem)' in FUENTE, True)
# Y la otra puerta por la que se colaria el bug: pasarle `len(mem)` a la funcion
# buena. Se comprueba el ARGUMENTO de la llamada, no solo que la funcion exista.
_llam_cat = [n for n in ast.walk(ARBOL)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'catalogo_parcial']
eq('(D3) catalogo_parcial() se llama una sola vez', len(_llam_cat), 1)
eq('(D3) 🔴 y se le pasan los PRESENTES, no len(mem)',
   [ast.dump(a) for a in _llam_cat[0].args] if _llam_cat else [],
   [ast.dump(ast.Name(id='N_CRUDO', ctx=ast.Load())),
    ast.dump(ast.Name(id='_n_pres_mem', ctx=ast.Load())),
    ast.dump(ast.Name(id='UMBRAL_PARCIAL', ctx=ast.Load()))])
_asig_pres = [n for n in ast.walk(ARBOL)
              if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == '_n_pres_mem' for t in n.targets)
              and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
              and n.value.func.id == 'presentes_en_memoria']
eq('(D3) _n_pres_mem sale de presentes_en_memoria(mem)', len(_asig_pres), 1)

# (D4) El fallo de memoria acaba en rojo, y con su etiqueta grepable.
eq('(D4) la etiqueta MEMORIA_INCOMPLETA esta en el codigo',
   FUENTE.count('MEMORIA_INCOMPLETA:') >= 2, True)
_asigna_roja = [n for n in ast.walk(ARBOL)
                if isinstance(n, ast.If)
                and any(isinstance(x, ast.Name) and x.id == 'MEMORIA_LOTES_FALLIDOS'
                        for x in ast.walk(n.test))
                and any(isinstance(a, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == '_SALIDA_ROJA' for t in a.targets)
                        for a in n.body)]
eq('(D4) 🔴 un lote de memoria fallido pone la salida en ROJO', len(_asigna_roja), 1)


print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK')
