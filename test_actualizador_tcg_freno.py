# -*- coding: utf-8 -*-
"""Banco del freno del Actualizador TCG (moloka_actualizar_tcg.py).

QUE PRUEBA, Y POR QUE NO SE PODIA PROBAR ANTES.
   `moloka_actualizar_tcg.py` no se puede importar: en la linea 35 lee
   SUPABASE_URL del entorno y revienta si falta. Por eso las funciones puras
   del freno se sacan del fichero real con `ast` -- POR ESTRUCTURA, buscando
   el `def`/`Assign` por su nombre en el arbol, no con un grep -- y se
   EJECUTAN. No prueba una copia: prueba el codigo que corre en produccion.

EL ENCARGO (10-sep-2026), medido en produccion antes de tocar nada:
   475 fichas activas de origen='tcg'. El robot, con su propio criterio,
   despublicaria 103 (21,7%) porque el proveedor esta de mudanza de almacen
   y medio catalogo esta "en reposicion" -- limpieza real, no una descarga
   coja. El viejo UMBRAL_FRENO=40 (numero fijo) habria frenado esa limpieza
   IGUAL que a un Excel corrupto, y ademas el `return` de la guarda vieja
   dejaba la web sin refrescar precios: dos bugs, un solo freno.

LAS DOS DIRECCIONES.
   (A) decidir_freno() en aislamiento, con las cifras reales del encargo y
       con los bordes (0 activas, justo en el corte).
   (B) 🔴 el freno VIEJO (numero fijo) sobre esas MISMAS cifras, para que
       quede escrito que con el saltaba.
   (C) por estructura: que decidir_freno() se USA en main(), que el bucle
       de despublicar es el UNICO que el freno frena, y que ya no queda
       ningun `return` que corte precios/reactivaciones cuando frena.
"""
import ast
import io
import sys

RUTA = 'moloka_actualizar_tcg.py'
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
# Extraer y EJECUTAR el codigo real (por estructura, con ast)
# ---------------------------------------------------------------------------
def sacar_def(nombre):
    for n in ARBOL.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
    print('XX la funcion %s() ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


def sacar_asignacion(nombre):
    for n in ARBOL.body:
        if (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == nombre for t in n.targets)):
            return n
    print('XX la constante %s ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


_ns = {}
_mod = ast.Module(
    body=[sacar_asignacion('UMBRAL_FRENO_PCT'), sacar_def('decidir_freno'), sacar_def('ejemplos_despublicar')],
    type_ignores=[])
exec(compile(ast.fix_missing_locations(_mod), RUTA, 'exec'), _ns)
UMBRAL_FRENO_PCT = _ns['UMBRAL_FRENO_PCT']
decidir_freno = _ns['decidir_freno']
ejemplos_despublicar = _ns['ejemplos_despublicar']
print('extraidas de %s: UMBRAL_FRENO_PCT=%r, decidir_freno, ejemplos_despublicar' % (RUTA, UMBRAL_FRENO_PCT))
print()


# --- (A) decidir_freno(): PORCENTAJE de las activas, no un numero fijo -----
eq('(A) el corte vive en el fichero y es 0.35 (35%, el del blindaje del escaner)',
   UMBRAL_FRENO_PCT, 0.35)

# Las cifras REALES del encargo (10-sep-2026): 103 de 475 activas = 21,7%.
eq('(A) 🔴 103/475 (21,7%, limpieza real por mudanza de proveedor) -> NO frena',
   decidir_freno(103, 475), (False, 21.7))

# Una descarga a medias de verdad SI tiene que seguir frenando.
eq('(A) 200/475 (42,1%, mas de media descarga) -> SI frena',
   decidir_freno(200, 475)[0], True)

# Bordes exactos del corte (numeros redondos para que el borde caiga limpio).
eq('(A) justo EN el 35% (35/100) -> no frena (es ">", no ">=")',
   decidir_freno(35, 100), (False, 35.0))
eq('(A) justo POR ENCIMA del 35% (36/100) -> frena',
   decidir_freno(36, 100)[0], True)

# Sin activas con que medir: no hay division por cero, y no se inventa un frenado.
eq('(A) 0 activas -> no frena y no hay porcentaje que enseñar',
   decidir_freno(0, 0), (False, None))


# --- (B) 🔴 el freno VIEJO (UMBRAL_FRENO=40 fijo), sobre las MISMAS cifras --
# UMBRAL_FRENO ya no vive en el fichero (lo comprueba (C) mas abajo); el 40
# se deja aqui EXPLICITO para que quede escrito que con el freno viejo
# saltaba, tal como pide el encargo.
UMBRAL_FRENO_VIEJO = 40
eq('(B) 🔴 el freno VIEJO (40 fijo) SI saltaba con la limpieza real del 10-sep',
   103 > UMBRAL_FRENO_VIEJO, True)
eq('(B) el freno NUEVO (35%) NO salta con esa misma limpieza',
   decidir_freno(103, 475)[0], False)


# --- (C) ejemplos_despublicar(): hasta 8, con nombre y motivo --------------
def _f(nombre, ean='0000000000000'):
    return {'nombre': nombre, 'ean': ean}


_doce = [(_f('Funko %d' % i), 'stock 0') for i in range(12)]
_txt8 = ejemplos_despublicar(_doce)
eq('(C) por defecto lista 8 ejemplos, no los 12', _txt8.count('\n') + 1, 8)
eq('(C) el primero lleva nombre y motivo', 'Funko 0' in _txt8 and 'stock 0' in _txt8, True)
eq('(C) el noveno NO sale', 'Funko 8' in _txt8, False)
eq('(C) sin nombre, cae al EAN', ejemplos_despublicar([(_f(None, '123'), 'desaparecio')]), '  • 123 (desaparecio)')
eq('(C) lista vacia -> texto vacio', ejemplos_despublicar([]), '')


# --- (D) Que las guardas esten PUESTAS EN main(), no solo escritas --------
# 🔴 «Si desactivas la feature a mano y el banco sigue verde, el banco no la
#    esta probando» (CLAUDE.md §3). Los asserts de abajo miran el ARBOL del
#    fichero real: que decidir_freno() se llama, que el freno frena SOLO el
#    bucle de despublicar, y que ya no queda un `return` que corte precios.

_main = None
for _n in ARBOL.body:
    if isinstance(_n, ast.FunctionDef) and _n.name == 'main':
        _main = _n
        break
eq('(D) existe main()', _main is not None, True)

# (D1) La constante vieja (un numero fijo de fichas) ya no esta.
_umbral_viejo = [n for n in ARBOL.body
                 if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'UMBRAL_FRENO' for t in n.targets)]
eq('(D1) 🔴 no queda ningun UMBRAL_FRENO (numero fijo); solo UMBRAL_FRENO_PCT',
   len(_umbral_viejo), 0)

# (D2) decidir_freno() se llama dentro de main(), y con lo que toca:
#      cuantas se despublicarian y cuantas activas hay hoy -- no al reves,
#      y no con el total del catalogo.
_llam_decidir = [n for n in ast.walk(_main)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == 'decidir_freno']
eq('(D2) decidir_freno() se llama una sola vez en main()', len(_llam_decidir), 1)
if _llam_decidir:
    _args = [ast.dump(a) for a in _llam_decidir[0].args]
    eq('(D2) se le pasa len(despublicar) primero',
       _args[0] if _args else None,
       ast.dump(ast.Call(func=ast.Name(id='len', ctx=ast.Load()),
                          args=[ast.Name(id='despublicar', ctx=ast.Load())], keywords=[])))
    eq('(D2) y activas_hoy segundo (no el total del catalogo)',
       _args[1] if len(_args) > 1 else None,
       ast.dump(ast.Name(id='activas_hoy', ctx=ast.Load())))

# (D3) El bucle que APLICA la baja es el UNICO condicionado por `frenado`:
#      su iterable es `[] if frenado else despublicar` (un IfExp).
_bucles_for = [n for n in ast.walk(_main) if isinstance(n, ast.For)]


def _iter_de(nombre_target0):
    for b in _bucles_for:
        if (isinstance(b.target, ast.Tuple) and len(b.target.elts) == 2
                and isinstance(b.target.elts[0], ast.Name) and b.target.elts[0].id == 'f'
                and isinstance(b.target.elts[1], ast.Name) and b.target.elts[1].id == nombre_target0):
            return b.iter
    return None


_iter_off = _iter_de('_m')
eq('(D3) existe el bucle `for f, _m in ...` (la baja)', _iter_off is not None, True)
if _iter_off is not None:
    eq('(D3) 🔴 su iterable depende de `frenado` (IfExp), no es `despublicar` a secas',
       isinstance(_iter_off, ast.IfExp) and isinstance(_iter_off.test, ast.Name)
       and _iter_off.test.id == 'frenado', True)
    eq('(D3) si frena, la baja se queda en NADA (lista vacia), no en un `continue`/`pass`',
       isinstance(_iter_off, ast.IfExp) and isinstance(_iter_off.body, ast.List)
       and _iter_off.body.elts == [], True)
    eq('(D3) si no frena, aplica `despublicar` entero',
       isinstance(_iter_off, ast.IfExp) and isinstance(_iter_off.orelse, ast.Name)
       and _iter_off.orelse.id == 'despublicar', True)

# (D4) Reactivar y recios NO estan condicionados por `frenado`: se aplican
#      SIEMPRE. Sus iterables son Name llanos, no un IfExp.
#      Ambos bucles tienen target (f, pw, pof) -> hay 4 con ese target (2 del
#      resumen que imprimen `recios[:60]`/`reactivar[:60]`, 2 que APLICAN);
#      los del resumen recortan con `[:60]` (un Subscript) y quedan fuera.
_bucles_pw = [b for b in _bucles_for
              if isinstance(b.target, ast.Tuple) and len(b.target.elts) == 3
              and isinstance(b.target.elts[0], ast.Name) and b.target.elts[0].id == 'f'
              and isinstance(b.target.elts[1], ast.Name) and b.target.elts[1].id == 'pw'
              and isinstance(b.target.elts[2], ast.Name) and b.target.elts[2].id == 'pof'
              and not isinstance(b.iter, ast.Subscript)]
_iters_pw = [ast.dump(b.iter) for b in _bucles_pw]
eq('(D4) hay exactamente 2 bucles `for f, pw, ... in ...` (reactivar + recios)', len(_bucles_pw), 2)
eq('(D4) 🔴 ninguno de los dos depende de `frenado`: reactivar y recios se aplican SIEMPRE',
   all('IfExp' not in it for it in _iters_pw), True)
eq('(D4) son exactamente `reactivar` y `recios`, sin envolver',
   sorted(it for it in _iters_pw),
   sorted([ast.dump(ast.Name(id='reactivar', ctx=ast.Load())),
           ast.dump(ast.Name(id='recios', ctx=ast.Load()))]))

# (D5) 🔴 Cuando el freno salta, main() YA NO CORTA LA FUNCION: ningun `If`
#      cuyo test hable de `frenado` lleva un `return` en su cuerpo. Es la
#      regla vieja (avisar + `return`) que dejaba precios sin aplicar.
_ifs_frenado_con_return = [n for n in ast.walk(_main)
                           if isinstance(n, ast.If)
                           and any(isinstance(x, ast.Name) and x.id == 'frenado' for x in ast.walk(n.test))
                           and any(isinstance(s, ast.Return) for s in ast.walk(n))]
eq('(D5) 🔴 ningun `if` sobre `frenado` contiene un `return` (ya no corta precios)',
   len(_ifs_frenado_con_return), 0)

# (D6) El aviso de Telegram usa ejemplos_despublicar() al menos dos veces
#      (preview y freno-en-aplicar): no hace falta abrir el log para ver
#      CUALES fichas estan en juego.
_llam_ejemplos = [n for n in ast.walk(_main)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == 'ejemplos_despublicar']
eq('(D6) ejemplos_despublicar() se usa al menos 2 veces en main() (preview y freno)',
   len(_llam_ejemplos) >= 2, True)

# (D7) Y el mensaje de freno lleva el PORCENTAJE, no solo la cuenta cruda:
#      cita `resumen_baja` (que ya trae "N/M (X%)"), no `len(despublicar)` a secas.
_avisos_frenado = [n for n in ast.walk(_main)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'avisar'
                   and any(isinstance(x, ast.Name) and x.id == 'resumen_baja'
                           for a in n.args for x in ast.walk(a))]
eq('(D7) al menos un aviso cita `resumen_baja` (cuenta + total + %)', len(_avisos_frenado) >= 1, True)


print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK')
