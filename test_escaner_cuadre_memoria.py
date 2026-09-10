# -*- coding: utf-8 -*-
"""Banco: la escritura de `escaner_memoria` se VERIFICA contando, no creyendo.

EL FALLO QUE CIERRA (10-sep-2026). La Celda 10 hacia el upsert de
`escaner_memoria` en lotes de 500 y no contaba nada despues:

    sb.table('escaner_memoria').upsert(lote, on_conflict=...).execute()
    n_ok += len(lote)

`n_ok` es lo que dice el CLIENTE, no lo que hay en la tabla. Y un upsert frenado
por una politica NO lanza: contesta 200 con cero filas. Desde el escaner se ve
exactamente igual que uno bueno -- mismo log, mismo verde, misma linea "Memoria
actualizada: 1.510/1.510" -- sobre una tabla que ha quedado con los datos del dia
anterior. De `escaner_memoria` salen «Que reponer» y el trackeador: si miente, la
decision de compra se toma sobre un catalogo inventado.

COMO SE CUENTA. Todas las filas de una pasada llevan la MISMA `fecha` (`ahora`,
que se calcula UNA vez al empezar la Celda 10), asi que esa fecha es la huella de
la pasada. Se cuenta por `(proveedor, fecha)`: por proveedor, para que dos
directores a la vez no se sumen; y por fecha, para que no se cuente la tabla
entera -- que es como este banco saldria verde sin probar nada.

QUE SE PRUEBA, Y COMO. DE PUNTA A PUNTA, tres veces, cada una en su PROCESO (el
escaner es un script: se corre con `runpy` y hace `sys.exit`). Con `keepa` y
`supabase` sustituidos por dobles en memoria, sin red y sin secretos, y con
perfil DINOTOYS -- un proveedor de verdad, NO el MIS_COMPRAS de los otros bancos:
MIS_COMPRAS es efimero y no toca `escaner_memoria`, o sea que no probaria nada:

  1. [cuadra]     el doble guarda lo que se le manda  -> exit 0, y la tabla
                  devuelve las mismas 3 fichas que el cliente dijo haber escrito.
  2. [frenado]    el doble ACEPTA el upsert y no guarda nada (200 con cero filas,
                  que es lo que hace una politica que te frena) -> exit 1 con
                  MEMORIA_DESCUADRADA: el cliente dijo 3, en la tabla hay 0.
  3. [sin_conteo] el upsert va bien pero el conteo REVIENTA -> exit 1 con
                  MEMORIA_SIN_VERIFICAR. Una escritura que no se ha podido
                  verificar no es una escritura verificada.

Y en los TRES, la linea CUADRE tiene que estar en el log: cuadre o no cuadre. Es
la disciplina del blindaje anti-vaciado, y por el mismo motivo -- un control que
solo habla cuando falla no se puede auditar, porque el dia que calla no se
distingue "esta bien" de "no llego a mirar".

LA MEMORIA DE MENTIRA LLEVA HISTORIA A PROPOSITO. Antes de la pasada, la tabla
del doble ya tiene 3 fichas de DINOTOYS agotadas hace un mes (que hoy NO se
tocan) y 4 de OCIOSTOCK. Si el conteo se dejara la fecha, contaria 7 donde el
cliente dijo 3 y el caso [cuadra] se pondria ROJO. Si se dejara el proveedor,
sumaria las de OCIOSTOCK. El caso bueno solo sale verde si el filtro es el par
completo, y (D) lo comprueba ademas mirando los filtros que el doble ha recibido.

LAS DOS DIRECCIONES, MEDIDAS. Los tres casos se han visto en rojo quitando a mano
el bloque del conteo de la Celda 10 (y su `if MEMORIA_CUADRE` de la Celda 12):
[frenado] y [sin_conteo] pasan a exit 0 -- verdes sobre una tabla vacia, que es
el fallo entero -- y los tres pierden la linea CUADRE.
"""
import io
import json
import os
import re
import subprocess
import sys
import types
from datetime import datetime

RUTA = 'moloka_escaner_nube.py'

# ---------------------------------------------------------------------------
# EL CATALOGO DE MENTIRA (2 productos; los cuatro paises son los de PAISES en el
# escaner de verdad -- si falta uno, este banco no se pone rojo: se cuelga).
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
PROVEEDOR = 'DINOTOYS'
VIEJA = '2026-08-11T09:00:00+00:00'
# La memoria de ANTES de la pasada. 4 fichas de DINOTOYS y 4 de otro proveedor.
# - las 3 agotadas de DINOTOYS no se vuelven a tocar hoy (ya estan marcadas)
# - la 5a de DINOTOYS SI se toca: esta presente y no viene en el catalogo -> agotada
MEMORIA_PREVIA = (
    [{'proveedor': PROVEEDOR, 'ean': '840000000000%d' % i, 'es_case': False,
      'pa': 1.0, 'presente': False, 'fecha': VIEJA, 'marca': 'TODAS'} for i in (1, 2, 3)]
    + [{'proveedor': PROVEEDOR, 'ean': '8400000000009', 'es_case': False,
        'pa': 2.0, 'presente': True, 'fecha': VIEJA, 'marca': 'TODAS'}]
    + [{'proveedor': 'OCIOSTOCK', 'ean': '850000000000%d' % i, 'es_case': False,
        'pa': 3.0, 'presente': True, 'fecha': VIEJA, 'marca': 'TODAS'} for i in (1, 2, 3, 4)])
# 2 presentes del catalogo + 1 agotada = 3 fichas escritas HOY.
N_HOY = 3
RECADO = {"proveedor": PROVEEDOR, "marca": "TODAS", "modo": "todo",
          "rank_maximo": 200000, "incluir_sin_rank": True}


# ===========================================================================
# EL HIJO: monta los dobles y corre el escaner de punta a punta
# ===========================================================================
def hijo(caso):
    import atexit

    SUBIDOS = {}
    TABLA = {}          # (proveedor, ean, es_case) -> fila, o sea escaner_memoria
    CONTEOS = []        # los filtros de cada conteo que el escaner ha pedido
    for _f in MEMORIA_PREVIA:
        TABLA[(_f['proveedor'], _f['ean'], _f['es_case'])] = dict(_f)

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

    BUZON = {'escaner/_solicitud_escaner.json': json.dumps(RECADO).encode('utf-8'),
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
        """Doble de una tabla. `escaner_memoria` se comporta como una tabla de
        verdad -- guarda lo que se le manda y CUENTA lo que le piden, honrando
        los filtros --, que es justo lo que este banco necesita medir. El resto
        contesta lo minimo para que el escaner no aborte."""

        def __init__(self, tabla):
            self.tabla = tabla
            self.filtros = {}
            self.conteo = None
            self.op = None
            self.filas = None

        def select(self, *a, **k):
            self.op = 'select'
            self.conteo = k.get('count')
            return self

        def upsert(self, filas, **k):
            self.op = 'upsert'
            self.filas = filas if isinstance(filas, list) else [filas]
            return self

        def insert(self, filas, **k):
            self.op = 'insert'
            self.filas = filas if isinstance(filas, list) else [filas]
            return self

        def eq(self, col, val):
            self.filtros[col] = val
            return self

        def __getattr__(self, nombre):
            return lambda *a, **k: self      # range, limit, order, update, delete…

        # --- lo que de verdad hace la tabla de mentira -----------------------
        def _casan(self, fila):
            for col, val in self.filtros.items():
                if col == 'fecha':
                    if datetime.fromisoformat(str(fila.get('fecha'))) \
                            != datetime.fromisoformat(str(val)):
                        return False
                elif str(fila.get(col)) != str(val):
                    return False
            return True

        def execute(self):
            if self.tabla == 'productos':
                return _Resp(PRODUCTOS)
            if self.tabla != 'escaner_memoria':
                return _Resp([{'id': 1}] if self.tabla == 'escaner_resultados' else [])

            if self.op == 'upsert':
                # 🔴 [frenado]: la politica te para. NO lanza -- devuelve 200 con
                #    cero filas, que es el silencio entero de este banco.
                if caso != 'frenado':
                    for f in self.filas:
                        TABLA[(f['proveedor'], f['ean'], bool(f['es_case']))] = dict(f)
                return _Resp([])

            if self.conteo:                       # el conteo del cuadre
                CONTEOS.append(dict(self.filtros))
                if caso == 'sin_conteo':
                    raise Exception('doble: el conteo revienta a proposito')
                return _Resp([], count=sum(1 for f in TABLA.values() if self._casan(f)))

            # la lectura de la Celda 5b (memoria viva del proveedor)
            return _Resp([{'ean': f['ean'], 'es_case': f['es_case'], 'pa': f['pa'],
                           'presente': f['presente']}
                          for f in TABLA.values() if self._casan(f)])

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
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'   # sin ella el escaner aborta en el arranque
    for v in ('TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID', 'AUTORELANZAR_MIN'):
        os.environ.pop(v, None)

    # Por `atexit`: el escaner sale con sys.exit(1) cuando el cuadre falla, y
    # estas lineas son justo las que hay que leer en ese caso.
    @atexit.register
    def _informe():
        _hoy = [f for f in TABLA.values()
                if f['proveedor'] == PROVEEDOR and str(f['fecha']) != VIEJA]
        print('FILAS_TABLA=%d' % len(TABLA))
        print('FILAS_HOY=%d' % len(_hoy))
        print('CONTEOS=%s' % json.dumps(CONTEOS))
        print('FECHAS_HOY=%s' % ','.join(sorted({str(f['fecha']) for f in _hoy})))

    import runpy
    runpy.run_path(RUTA, run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2])
    sys.exit(0)


# ===========================================================================
# EL PADRE: los asserts
# ===========================================================================
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def correr(caso):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout or '') + (p.stderr or '')

    def cifra(clave):
        m = re.search(r'^%s=(\d+)\s*$' % clave, out, re.M)
        return int(m.group(1)) if m else -1

    _c = re.search(r'^CONTEOS=(.*)$', out, re.M)
    _f = re.search(r'^FECHAS_HOY=(.*)$', out, re.M)
    _cu = re.search(r'^CUADRE memoria .*$', out, re.M)
    return {'codigo': p.returncode, 'salida': out,
            'filas': cifra('FILAS_TABLA'), 'hoy': cifra('FILAS_HOY'),
            'conteos': json.loads(_c.group(1)) if _c else [],
            'fechas_hoy': [x for x in (_f.group(1).strip() if _f else '').split(',') if x],
            'cuadre': _cu.group(0) if _cu else None}


# ---------------------------------------------------------------------------
# (A) [cuadra] el caso bueno. Es la mitad del ancla que impide que los otros dos
#     salgan verdes por un escaner que se cayera siempre.
# ---------------------------------------------------------------------------
print('(A) [cuadra] el doble guarda lo que se le manda')
_ok = correr('cuadra')
eq('(A) [cuadra] 🔴 el run sale VERDE (exit 0)', _ok['codigo'], 0)
eq('(A) [cuadra] las 3 fichas de hoy estan en la tabla', _ok['hoy'], N_HOY)
eq('(A) [cuadra] y la tabla conserva las 8 de antes + las 2 nuevas', _ok['filas'], 10)
eq('(A) [cuadra] 🔴 la linea CUADRE esta en el log',
   _ok['cuadre'], 'CUADRE memoria [DINOTOYS/TODAS]: queriamos=%d | el cliente dijo OK=%d'
                  ' | en la tabla con la fecha de esta pasada=%d' % (N_HOY, N_HOY, N_HOY))
eq('(A) [cuadra] y NO sale ningun aviso de descuadre',
   ('MEMORIA_DESCUADRADA' in _ok['salida'], 'MEMORIA_SIN_VERIFICAR' in _ok['salida']),
   (False, False))

# ---------------------------------------------------------------------------
# (B) [frenado] el upsert dice 200 y no escribe nada. ESTE es el fallo.
# ---------------------------------------------------------------------------
print('\n(B) [frenado] el upsert contesta 200 con cero filas (una politica que frena)')
_fr = correr('frenado')
eq('(B) [frenado] 🔴 el run sale en ROJO (exit 1)', _fr['codigo'], 1)
eq('(B) [frenado] 🔴 con la etiqueta grepable MEMORIA_DESCUADRADA',
   'MEMORIA_DESCUADRADA' in _fr['salida'], True)
eq('(B) [frenado] 🔴 la linea CUADRE dice 3 dichas y 0 en la tabla',
   _fr['cuadre'], 'CUADRE memoria [DINOTOYS/TODAS]: queriamos=%d | el cliente dijo OK=%d'
                  ' | en la tabla con la fecha de esta pasada=0' % (N_HOY, N_HOY))
eq('(B) [frenado] y en la tabla no ha entrado ni una ficha de hoy', _fr['hoy'], 0)
eq('(B) [frenado] el escaner SI creyo haberlas escrito (esa es la trampa)',
   'Memoria actualizada: %d/%d' % (N_HOY, N_HOY) in _fr['salida'], True)

# ---------------------------------------------------------------------------
# (C) [sin_conteo] no poder contar tampoco es prueba de nada.
# ---------------------------------------------------------------------------
print('\n(C) [sin_conteo] el upsert va bien pero el conteo revienta')
_sc = correr('sin_conteo')
eq('(C) [sin_conteo] 🔴 el run sale en ROJO (exit 1)', _sc['codigo'], 1)
eq('(C) [sin_conteo] 🔴 con la etiqueta grepable MEMORIA_SIN_VERIFICAR',
   'MEMORIA_SIN_VERIFICAR' in _sc['salida'], True)
eq('(C) [sin_conteo] 🔴 y la linea CUADRE sale IGUAL, con n/d donde no se pudo contar',
   _sc['cuadre'], 'CUADRE memoria [DINOTOYS/TODAS]: queriamos=%d | el cliente dijo OK=%d'
                  ' | en la tabla con la fecha de esta pasada=n/d' % (N_HOY, N_HOY))
eq('(C) [sin_conteo] las fichas SI estan en la tabla: lo que falla es la verificacion',
   _sc['hoy'], N_HOY)

# ---------------------------------------------------------------------------
# (D) EL FILTRO DEL CONTEO, mirado en lo que el doble ha recibido de verdad.
#     Un conteo sin `fecha` contaria la tabla entera; uno sin `proveedor` se
#     sumaria las fichas de otro director corriendo a la vez.
# ---------------------------------------------------------------------------
print('\n(D) el conteo se hace por (proveedor, fecha), y por nada mas')
eq('(D) se ha pedido UN conteo, no cero', len(_ok['conteos']), 1)
if _ok['conteos']:
    _filtros = _ok['conteos'][0]
    eq('(D) 🔴 filtra por proveedor Y por fecha', sorted(_filtros), ['fecha', 'proveedor'])
    eq('(D) 🔴 y el proveedor es el de la pasada', _filtros.get('proveedor'), PROVEEDOR)
    eq('(D) 🔴 la fecha del filtro es la MISMA que llevan las filas escritas hoy',
       [datetime.fromisoformat(_filtros.get('fecha'))],
       [datetime.fromisoformat(f) for f in _ok['fechas_hoy']])
    eq('(D) …y las 3 filas de hoy llevan UNA sola fecha (la huella de la pasada)',
       len(_ok['fechas_hoy']), 1)

# ---------------------------------------------------------------------------
print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK (la escritura de escaner_memoria se cuenta, y el descuadre sale en rojo)')
