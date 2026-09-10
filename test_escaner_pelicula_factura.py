# -*- coding: utf-8 -*-
"""Banco: la PELICULA (`escaner_detalle`, Celda 9b) SOLO se escribe en pasadas de FACTURA.

EL ENCARGO (7-sep-2026, decision de Fernando): la historia de los escaneos de
PROVEEDOR no se guarda. `escaner_detalle` solo la lee el informe de la factura
(v2, `entrada-facturas/escanear.ts` y `fase-escaneo.ts`), por `ejecucion`. Antes
de este PR la Celda 9b escribia SIEMPRE que hubiera `SUPABASE_SERVICE_KEY`, sin
mirar de que pasada venia: una pasada de proveedor (HEO, DINOTOYS...) dejaba
filas en `escaner_detalle` que nadie lee y que se quedan ahi para siempre (la
tabla es PELICULA: nunca se borra).

QUE SE PRUEBA, Y COMO (calcado del patron de `test_escaner_catalogo_propio.py`):
  DE PUNTA A PUNTA, dos veces, cada una en su PROCESO (el escaner es un script:
  se corre con `runpy` y hace sus prints/escrituras). Con `keepa` y `supabase`
  sustituidos por dobles en memoria, sin red, sin secretos reales, y CON
  `SUPABASE_SERVICE_KEY` puesta (al contrario que en `test_escaner_catalogo_propio.py`,
  que la quita: aqui es justo la llave la que decide si INTENTA escribir):
    1. perfil MIS_COMPRAS (la factura, `escanear.ts`) -> escribe las N filas de
       detalle (2 productos x 4 paises = 8) y el log dice cuantas.
    2. perfil DINOTOYS (proveedor real, mismo catalogo, misma llave) -> CERO
       escrituras en `escaner_detalle` y la linea de log fija de la omision.
  Y (B) que la guarda este PUESTA, no solo escrita: por estructura (`ast`), que
  el `try` que escribe `escaner_detalle` cuelgue de un `if PERFIL.get('efimero')`
  y no de un `if sb_det` o cualquier otra cosa.

LAS DOS DIRECCIONES. Se ha visto ROJO quitando la condicion a mano (dejando el
`try` de Celda 9b SIN el `if PERFIL.get('efimero')` que lo envuelve): el caso
[proveedor] pasaba de 0 a 8 escrituras y el (B) de abajo se ponia rojo el
primero, antes de correr nada de punta a punta.
"""
import ast
import io
import json
import os
import re
import subprocess
import sys
import types

RUTA = 'moloka_escaner_nube.py'

# ---------------------------------------------------------------------------
# EL CATALOGO DE MENTIRA (2 productos, 4 paises: ES/IT/FR/DE -- los mismos que
# PAISES en el escaner de verdad; ver el aviso de test_escaner_catalogo_propio.py
# sobre por que esto no puede faltar).
# ---------------------------------------------------------------------------
CATALOGO = (
    "Nombre,EAN,Precio,Marca,Stock\n"
    "Funko Pop Gizmo,0889698498883,4.50,Funko,12\n"
    "Chai latte polvo,8412345678905,3.10,Otra,8\n")
ASIN = {'0889698498883': 'B0GIZMO', '8412345678905': 'B0CHAI'}
PRODUCTOS = [
    {'ean': '889698498883', 'asin': 'B0GIZMO', 'iva_pct': '0.2100',
     'stock_moloka': 3, 'stock_fba': 7},
    {'ean': '8412345678905', 'asin': None, 'iva_pct': '0.1000',
     'stock_moloka': 1, 'stock_fba': 0},
]
PRECIOS = {   # asin -> pais -> (precio, ref_pct, fee FBA, rank)
    'B0GIZMO': {'ES': (16.99, 15.0, 3.51, 4200), 'IT': (17.49, 15.0, 3.62, 9100),
                'FR': (18.25, 15.0, 3.72, 6400), 'DE': (17.99, 15.0, 3.55, 5100)},
    'B0CHAI':  {'ES': (12.50, 15.0, 3.10, 22000), 'IT': (12.90, 15.0, 3.20, 41000),
                'FR': (13.10, 15.0, 3.30, 38000), 'DE': (12.70, 15.0, 3.15, 33000)},
}
N_ESPERADO = len(ASIN) * 4   # 2 productos x 4 paises = 8
LINEA_OMITIDA = "PELICULA: omitida (pasada de proveedor; solo se guarda en factura)."


def recado(proveedor):
    return {"proveedor": proveedor, "marca": "TODAS", "modo": "todo",
            "rank_maximo": 200000, "incluir_sin_rank": True}


# ===========================================================================
# EL HIJO: monta los dobles y corre el escaner de punta a punta
# ===========================================================================
def hijo(caso, destino):
    import atexit

    ESCRITURAS = []            # 'tabla.metodo' por cada escritura, EN ORDEN
    FILAS = {}                 # tabla -> filas insertadas (suma de todos los insert)
    SUBIDOS = {}

    def _stats(rank, precio, con_bb):
        cur = [-1] * 20
        cur[1] = int(round(precio * 100))
        cur[3] = rank
        if con_bb:
            cur[18] = int(round(precio * 100))
        a90 = [-1] * 20
        a90[3] = rank
        return cur, a90

    class _FakeKeepa:
        def __init__(self, key, timeout=None):
            self.tokens_left = 1500

        def update_status(self):
            pass

        def query(self, items, **kw):
            if kw.get('product_code_is_asin'):
                a = items[0]
                precio, ref, fee, rank = PRECIOS[a][(kw.get('domain') or 'ES').upper()]
                cur, a90 = _stats(rank, precio, True)
                return [{'asin': a, 'title': 'T ' + a,
                         'stats': {'current': cur, 'avg90': a90, 'buyBoxIsFBA': True,
                                   'totalOfferCount': 5,
                                   'buyBoxPrice': int(round(precio * 100))},
                         'referralFeePercentage': ref,
                         'fbaFees': {'pickAndPackFee': int(round(fee * 100))},
                         'monthlySold': 40, 'images': ['x.jpg']}]
            out = []
            for cod in items:
                c13 = str(cod).zfill(13)
                a = ASIN.get(c13)
                if not a:
                    continue
                precio, _r, _f, rank = PRECIOS[a]['ES']
                cur, a90 = _stats(rank, precio, False)
                out.append({'asin': a, 'title': 'T ' + a,
                            'stats': {'current': cur, 'avg90': a90, 'salesRankDrops30': 12},
                            'listedSince': 6000000, 'eanList': [c13], 'upcList': []})
            return out

    PROVEEDOR_RECADO = {'factura': 'MIS_COMPRAS', 'proveedor': 'DINOTOYS'}[caso]
    BUZON = {'escaner/_solicitud_escaner.json': json.dumps(recado(PROVEEDOR_RECADO)).encode('utf-8'),
             'escaner/catalogo.csv': CATALOGO.encode('utf-8-sig')}

    class _Bucket:
        def list(self, carpeta):
            pre = carpeta.rstrip('/') + '/'
            return [{'name': n} for n in sorted({k[len(pre):].split('/')[0]
                                                 for k in list(BUZON) + list(SUBIDOS)
                                                 if k.startswith(pre)})]

        def download(self, ruta):
            if ruta in BUZON:
                return BUZON[ruta]
            if ruta in SUBIDOS:
                return SUBIDOS[ruta]
            raise Exception('404 ' + ruta)

        def upload(self, ruta, data, opts=None):
            SUBIDOS[ruta] = data
            return {'path': ruta}

        def remove(self, rutas):
            for r in rutas:
                BUZON.pop(r, None)
                SUBIDOS.pop(r, None)
            return []

    class _Resp:
        def __init__(self, data, count=None):
            self.data = data
            self.count = count

    class _Query:
        """Doble tonto a proposito, calcado de test_escaner_catalogo_propio.py: acepta
        cualquier metodo encadenado (select/eq/range/...). SOLO cuenta de verdad las
        filas de un `insert` (que es lo que Celda 9b usa para escaner_detalle) y
        contesta a `productos`/`escaner_resultados` lo que necesitan para no abortar."""
        def __init__(self, tabla):
            self.tabla = tabla
            self.conteo = None

        def insert(self, filas):
            filas = filas if isinstance(filas, list) else [filas]
            ESCRITURAS.append('%s.insert' % self.tabla)
            FILAS[self.tabla] = FILAS.get(self.tabla, 0) + len(filas)
            return self

        def upsert(self, filas, **k):
            filas = filas if isinstance(filas, list) else [filas]
            ESCRITURAS.append('%s.upsert' % self.tabla)
            FILAS[self.tabla] = FILAS.get(self.tabla, 0) + len(filas)
            return self

        def select(self, *a, **k):
            self.conteo = k.get('count')
            return self

        def __getattr__(self, nombre):
            if nombre in ('update', 'delete'):
                ESCRITURAS.append('%s.%s' % (self.tabla, nombre))
            return lambda *a, **k: self

        def execute(self):
            if self.tabla == 'productos':
                return _Resp(PRODUCTOS)
            # 🔒 El cuadre de la Celda 10 (10-sep-2026) cuenta lo que ha entrado en
            #    escaner_memoria y sale en ROJO si no cuadra con lo que dijo el
            #    cliente. El caso [proveedor] de este banco SI escribe memoria, asi
            #    que el doble tiene que saber contestar al conteo o el run acabaria
            #    rojo por un motivo que no es el suyo. Devuelve lo que se le mando:
            #    aqui el cuadre no es lo que se mide -- de eso va
            #    test_escaner_cuadre_memoria.py, que si lleva tabla de verdad.
            if self.tabla == 'escaner_memoria' and self.conteo:
                return _Resp([], count=FILAS.get('escaner_memoria', 0))
            return _Resp([{'id': 1}] if self.tabla == 'escaner_resultados' else [])

    class _Cliente:
        def __init__(self):
            self.storage = types.SimpleNamespace(from_=lambda _b: _Bucket())

        def table(self, nombre):
            return _Query(nombre)

    sys.modules['keepa'] = types.ModuleType('keepa')
    sys.modules['keepa'].Keepa = _FakeKeepa
    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda url, key: _Cliente()

    os.environ['KEEPA_API_KEY'] = 'FAKE'
    os.environ['SUPABASE_URL'] = 'https://doble.local'
    os.environ['SUPABASE_KEY'] = 'FAKE'
    # 🔴 AL CONTRARIO que test_escaner_catalogo_propio.py (que la quita): aqui es
    #    justo la SERVICE KEY la que decide si Celda 9b INTENTA escribir. Sin ella
    #    puesta, el caso [factura] saldria en 0 escrituras por el motivo EQUIVOCADO
    #    (falta de llave, no el perfil) y no probaria nada.
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    for v in ('TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID', 'AUTORELANZAR_MIN'):
        os.environ.pop(v, None)

    @atexit.register
    def _informe():
        print('ESCRITURAS=%s' % ','.join(ESCRITURAS))
        print('FILAS_ESCANER_DETALLE=%d' % FILAS.get('escaner_detalle', 0))

    import runpy
    runpy.run_path(RUTA, run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    sys.exit(0)


# ===========================================================================
# EL PADRE: los asserts
# ===========================================================================
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
# (A) Que la guarda este PUESTA, no solo escrita: el `try` que escribe
#     escaner_detalle cuelga de `if PERFIL.get('efimero')`, no de otra cosa.
# ---------------------------------------------------------------------------
_if_pelicula = None
for _n in ast.walk(ARBOL):
    if isinstance(_n, ast.If) and any(
            isinstance(c, ast.Constant) and isinstance(c.value, str) and LINEA_OMITIDA in c.value
            for h in _n.body for c in ast.walk(h)):
        _if_pelicula = _n
        break
eq('(A) existe el `if` que imprime la linea de omision', _if_pelicula is not None, True)

if _if_pelicula is not None:
    _test_nombres = {x.id for x in ast.walk(_if_pelicula.test) if isinstance(x, ast.Name)}
    _test_attrs = {x.attr for x in ast.walk(_if_pelicula.test) if isinstance(x, ast.Attribute)}
    eq('(A) 🔴 la condicion mira PERFIL', 'PERFIL' in _test_nombres, True)
    eq('(A) 🔴 y llama a .get(\'efimero\')', 'get' in _test_attrs
       and "Constant(value='efimero')" in ast.dump(_if_pelicula.test), True)
    # La rama que SI escribe (orelse) tiene el try/except de escaner_detalle.
    _tiene_try_detalle = any(
        isinstance(h, ast.Try) and any(
            isinstance(c, ast.Constant) and isinstance(c.value, str) and 'escaner_detalle' in c.value
            for c in ast.walk(h))
        for h in _if_pelicula.orelse)
    eq('(A) 🔴 la rama ELSE (no-omitida) es la que escribe escaner_detalle',
       _tiene_try_detalle, True)
    # Y que NO haya quedado un create_client() en la rama que omite (IF, no ELSE):
    # si alguien "arregla" el aviso pero deja el cliente creandose antes, el
    # motivo del log mentiria (parece que no escribe por falta de llave, no por
    # el perfil).
    _crea_cliente_en_omitida = any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == 'create_client'
        for h in _if_pelicula.body for c in ast.walk(h))
    eq('(A) 🔴 en la rama que omite NO se crea el cliente de servicio',
       _crea_cliente_en_omitida, False)


# ---------------------------------------------------------------------------
# (B) DE PUNTA A PUNTA: el escaner real, dos veces, cada una en su proceso
# ---------------------------------------------------------------------------
print()


def correr(caso):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout or '') + (p.stderr or '')
    m = re.search(r'^FILAS_ESCANER_DETALLE=(\d+)\s*$', out, re.M)
    esc = re.search(r'^ESCRITURAS=(.*)$', out, re.M)
    return {'codigo': p.returncode, 'salida': out,
            'filas_detalle': int(m.group(1)) if m else -1,
            'escrituras': [x for x in (esc.group(1).strip() if esc else '').split(',') if x]}


_r_fac = correr('factura')
eq('(B) [factura] 🔴 el run sale VERDE (exit 0)', _r_fac['codigo'], 0)
eq('(B) [factura] 🔴 escribe las N filas de detalle (2 productos x 4 paises)',
   _r_fac['filas_detalle'], N_ESPERADO)
eq('(B) [factura] hay exactamente un lote insertado en escaner_detalle',
   _r_fac['escrituras'].count('escaner_detalle.insert'), 1)
eq('(B) [factura] el log dice cuantas filas escribio',
   ('escaner_detalle: %d filas de detalle escritas' % N_ESPERADO) in _r_fac['salida'], True)
eq('(B) [factura] la linea de omision NO sale', LINEA_OMITIDA in _r_fac['salida'], False)

_r_prov = correr('proveedor')
eq('(B) [proveedor] 🔴 el run sale VERDE (exit 0)', _r_prov['codigo'], 0)
eq('(B) [proveedor] 🔴 CERO filas en escaner_detalle (mismo catalogo, misma llave)',
   _r_prov['filas_detalle'], 0)
eq('(B) [proveedor] 🔴 y CERO escrituras a escaner_detalle (ni un intento)',
   'escaner_detalle.insert' in _r_prov['escrituras'], False)
eq('(B) [proveedor] 🔴 la linea de omision fija SI sale',
   LINEA_OMITIDA in _r_prov['salida'], True)
# La otra mitad del ancla: el sondeo (Celda 9c) SI escribe en las dos pasadas
# (su propio try, sin este guardian) -- si `escaner_detalle.insert` faltase
# porque el escaner entero fallo antes de llegar a la Celda 9b, esto lo delata.
eq('(B) [proveedor] la Celda 9c (sondeo_keepa) SI corre -- prueba que no aborto antes',
   any(e.startswith('sondeo_keepa.') for e in _r_prov['escrituras']), True)


print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK')
