# -*- coding: utf-8 -*-
"""Banco: en MIS_COMPRAS (la factura), la fila que trae el ASIN de su ficha se pregunta a Keepa POR ESE ASIN.

EL FALLO QUE CIERRA (1-oct-2026, medido en produccion). Factura KaffeK 13001738142: una linea, ficha
Elephant Vanilla Chai, EAN 7185897225606, ASIN B000VYP4EM. El escaner preguntaba a Keepa SOLO por EAN
(Fase 1, `keepa_rank` con product_code_is_asin=False) y Keepa no asocia ese EAN a ninguna ficha (su eanList
para B000VYP4EM es 0658564703983). Tres pasadas (escaner_resultados 1708/1709/1710), las tres con
`sondeo_keepa` = «se pregunto y no habia» y 0 filas en `escaner_detalle`: la factura sin informe.
Y en los packs con EAN compartido (Ultra Pro 200/300/400, EAN 74427811266) el EAN lleva a la ficha de 100
fundas (B0002TT3N4) o a unas bolsitas genericas (B004LTYQRY), nunca a la del pack.

QUE SE PRUEBA, Y COMO (calcado de `test_escaner_pelicula_factura.py`): el escaner REAL de punta a punta, en su
proceso, con `keepa` y `supabase` sustituidos por dobles en memoria que APUNTAN cada pregunta a Keepa y cada
fila escrita. Catalogo de cuatro filas, con la columna `asin` que manda la v2:
  - KaffeK: con ASIN, y Keepa por EAN no lo conoce;
  - Ultra Pro 200: con ASIN del pack, y Keepa por EAN devuelve la de 100 fundas;
  - Chai: SIN ASIN -> sigue por EAN, como siempre;
  - una ficha con un ASIN que Keepa no tiene.
  [factura]  (MIS_COMPRAS) -> los tres primeros con informe, cada uno con SU ASIN; ninguno de los tres EAN con
             ASIN se pregunta por EAN; `sondeo_keepa` solo lleva lo que se pregunto por EAN.
  [proveedor] (DINOTOYS, mismo catalogo con la misma columna) -> la columna `asin` NO se usa: todo por EAN,
             como hasta hoy. Es la prueba de que el cambio no sale de MIS_COMPRAS.
"""
import io
import json
import os
import re
import subprocess
import sys
import types

RUTA = 'moloka_escaner_nube.py'

PID = {'kaffek': '766394d3-b6c9-4548-ab88-2bc09ec9cf29', 'up200': '930daa2d-26fe-42c5-a313-c44034be413d',
       'chai': '11111111-2222-3333-4444-555555555555', 'fantasma': '99999999-8888-7777-6666-555555555555'}
CATALOGO = (
    "ean,pvd,nombre,producto_id,asin\n"
    "7185897225606,10.1975,Elephant Vanilla Chai 398 gr,%s,B000VYP4EM\n"
    "74427811266,0.53,Fundas Standard Regular Cards (200 fundas) Ultra Pro,%s,B085DK713X\n"
    "8412345678905,3.10,Chai latte polvo,%s,\n"
    "8400000000017,2.00,Ficha con ASIN que Keepa no tiene,%s,B0FANTASMA\n"
    % (PID['kaffek'], PID['up200'], PID['chai'], PID['fantasma']))
EAN_CON_ASIN = {'7185897225606', '74427811266', '8400000000017'}
# Lo que Keepa contesta POR EAN (eanList incluido): KaffeK no esta; el EAN de Ultra Pro da la de 100 fundas.
POR_EAN = {'8412345678905': 'B0CHAI', '0074427811266': 'B0002TT3N4'}
EANLIST = {'B000VYP4EM': ['0658564703983'], 'B085DK713X': ['0074427811266'],
           'B0CHAI': ['8412345678905'], 'B0002TT3N4': ['0074427811266']}
PRODUCTOS = [{'ean': '7185897225606', 'asin': 'B000VYP4EM', 'iva_pct': '0.1000', 'stock_moloka': 24},
             {'ean': '74427811266', 'asin': 'B085DK713X', 'iva_pct': '0.2100', 'stock_moloka': 0},
             {'ean': '8412345678905', 'asin': None, 'iva_pct': '0.1000', 'stock_moloka': 1}]
PRECIOS = {   # asin -> pais -> (precio, ref_pct, fee FBA, rank)
    'B000VYP4EM': {'ES': (19.99, 15.0, 3.40, 8000), 'IT': (20.49, 15.0, 3.50, 9000),
                   'FR': (21.25, 15.0, 3.60, 7000), 'DE': (18.99, 15.0, 3.45, 6000)},
    'B085DK713X': {'ES': (12.99, 15.0, 3.10, 15000), 'IT': (13.49, 15.0, 3.20, 19000),
                   'FR': (13.25, 15.0, 3.30, 17000), 'DE': (12.49, 15.0, 3.15, 14000)},
    'B0CHAI':     {'ES': (12.50, 15.0, 3.10, 22000), 'IT': (12.90, 15.0, 3.20, 41000),
                   'FR': (13.10, 15.0, 3.30, 38000), 'DE': (12.70, 15.0, 3.15, 33000)},
    'B0002TT3N4': {'ES': (6.99, 15.0, 2.90, 3000), 'IT': (7.49, 15.0, 2.95, 4000),
                   'FR': (7.25, 15.0, 2.95, 3500), 'DE': (6.49, 15.0, 2.90, 2500)},
}


def recado(proveedor):
    return {"proveedor": proveedor, "marca": "TODAS", "modo": "todo",
            "rank_maximo": 999999999, "incluir_sin_rank": True, "ejecucion": "mis_compras_banco.csv"}


# ===========================================================================
# EL HIJO: monta los dobles y corre el escaner de punta a punta
# ===========================================================================
def hijo(caso):
    import atexit

    PREGUNTAS = []             # {'por': 'ean'|'asin_f1'|'asin_f2', 'items': [...]} por cada llamada a Keepa
    INSERTADAS = {}            # tabla -> filas insertadas
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

    def _prod_f1(a):
        precio, _r, _f, rank = PRECIOS[a]['ES']
        cur, a90 = _stats(rank, precio, False)
        return {'asin': a, 'title': 'T ' + a, 'stats': {'current': cur, 'avg90': a90, 'salesRankDrops30': 12},
                'listedSince': 6000000, 'eanList': EANLIST[a], 'upcList': []}

    class _FakeKeepa:
        def __init__(self, key, timeout=None):
            self.tokens_left = 1500

        def update_status(self):
            pass

        def query(self, items, **kw):
            items = [str(x) for x in items]
            if kw.get('product_code_is_asin') and kw.get('buybox'):      # Fase 2: un ASIN, un pais
                PREGUNTAS.append({'por': 'asin_f2', 'items': items})
                a = items[0]
                precio, ref, fee, rank = PRECIOS[a][(kw.get('domain') or 'ES').upper()]
                cur, a90 = _stats(rank, precio, True)
                return [{'asin': a, 'title': 'T ' + a,
                         'stats': {'current': cur, 'avg90': a90, 'buyBoxIsFBA': True, 'totalOfferCount': 5,
                                   'buyBoxPrice': int(round(precio * 100))},
                         'referralFeePercentage': ref, 'fbaFees': {'pickAndPackFee': int(round(fee * 100))},
                         'monthlySold': 40, 'images': ['x.jpg']}]
            if kw.get('product_code_is_asin'):                           # Fase 1 por ASIN de ficha
                PREGUNTAS.append({'por': 'asin_f1', 'items': items})
                return [_prod_f1(a) for a in items if a in PRECIOS]
            PREGUNTAS.append({'por': 'ean', 'items': items})             # Fase 1 por EAN
            out = []
            for cod in items:
                a = POR_EAN.get(cod.zfill(13))
                if a:
                    out.append(_prod_f1(a))
            return out

    BUZON = {'escaner/_solicitud_escaner.json': json.dumps(recado({'factura': 'MIS_COMPRAS',
                                                                   'proveedor': 'DINOTOYS'}[caso])).encode('utf-8'),
             'escaner/mis_compras_banco.csv': CATALOGO.encode('utf-8-sig')}

    class _Bucket:
        def list(self, carpeta):
            pre = carpeta.rstrip('/') + '/'
            return [{'name': n} for n in sorted({k[len(pre):].split('/')[0]
                                                 for k in list(BUZON) + list(SUBIDOS) if k.startswith(pre)})]

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
        def __init__(self, tabla):
            self.tabla = tabla
            self.conteo = None

        def insert(self, filas):
            INSERTADAS.setdefault(self.tabla, []).extend(filas if isinstance(filas, list) else [filas])
            return self

        def upsert(self, filas, **k):
            INSERTADAS.setdefault(self.tabla, []).extend(filas if isinstance(filas, list) else [filas])
            return self

        def select(self, *a, **k):
            self.conteo = k.get('count')
            return self

        def __getattr__(self, nombre):
            return lambda *a, **k: self

        def execute(self):
            if self.tabla == 'productos':
                return _Resp(PRODUCTOS)
            if self.tabla == 'escaner_memoria' and self.conteo:
                return _Resp([], count=len(INSERTADAS.get('escaner_memoria', [])))
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
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    for v in ('TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID', 'AUTORELANZAR_MIN'):
        os.environ.pop(v, None)

    @atexit.register
    def _informe():
        det = [{k: r.get(k) for k in ('ean', 'asin', 'producto_id', 'pais', 'pa')}
               for r in INSERTADAS.get('escaner_detalle', [])]
        snd = [{'ean': r.get('ean_consultado'), 'asin': r.get('asin_candidato'),
                'motivo': (r.get('crudo') or {}).get('motivo')} for r in INSERTADAS.get('sondeo_keepa', [])]
        print('BANCO=' + json.dumps({'preguntas': PREGUNTAS, 'detalle': det, 'sondeo': snd}))

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
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def correr(caso):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout or '') + (p.stderr or '')
    m = re.search(r'^BANCO=(.*)$', out, re.M)
    if p.returncode != 0 or not m:
        print(out[-3000:])
    return p.returncode, (json.loads(m.group(1)) if m else {'preguntas': [], 'detalle': [], 'sondeo': []}), out


def preguntado_por_ean(banco, ean):
    """¿Se pregunto a Keepa por este EAN (con cualquiera de sus variantes: con o sin ceros delante)?"""
    e = ean.lstrip('0')
    return any(str(i).lstrip('0') == e for q in banco['preguntas'] if q['por'] == 'ean' for i in q['items'])


# ---------------------------------------------------------------------------
# [factura] MIS_COMPRAS
# ---------------------------------------------------------------------------
cod, b, out = correr('factura')
eq('[factura] 🔴 el run sale VERDE (exit 0)', cod, 0)

asin_f1 = sorted(i for q in b['preguntas'] if q['por'] == 'asin_f1' for i in q['items'])
eq('[factura] 🔴 la Fase 1 pregunta por los TRES ASIN de ficha', asin_f1, ['B000VYP4EM', 'B085DK713X', 'B0FANTASMA'])
for e in sorted(EAN_CON_ASIN):
    eq('[factura] 🔴 el EAN %s (su ficha trae ASIN) NO se pregunta por EAN' % e, preguntado_por_ean(b, e), False)
eq('[factura] la ficha SIN ASIN (Chai) sigue por EAN, como siempre', preguntado_por_ean(b, '8412345678905'), True)

por_ficha = {}
for r in b['detalle']:
    por_ficha.setdefault(r['producto_id'], set()).add((r['ean'], r['asin'], r['pais']))
PAISES4 = ('ES', 'IT', 'FR', 'DE')
eq('[factura] 🔴 KaffeK: informe en los 4 paises, con SU ASIN y el EAN de la ficha',
   por_ficha.get(PID['kaffek']), {('7185897225606', 'B000VYP4EM', p) for p in PAISES4})
eq('[factura] 🔴 Ultra Pro 200: el ASIN del PACK (no el de 100 fundas)',
   por_ficha.get(PID['up200']), {('74427811266', 'B085DK713X', p) for p in PAISES4})
eq('[factura] Chai (por EAN): su ASIN de Keepa, como siempre',
   por_ficha.get(PID['chai']), {('8412345678905', 'B0CHAI', p) for p in PAISES4})
eq('[factura] la ficha con un ASIN que Keepa no tiene se queda sin filas', PID['fantasma'] in por_ficha, False)
eq('[factura] el coste viaja tal cual (KaffeK pa=10.1975)',
   {r['pa'] for r in b['detalle'] if r['producto_id'] == PID['kaffek']}, {10.1975})
eq('[factura] ni una fila con el ASIN de 100 fundas', any(r['asin'] == 'B0002TT3N4' for r in b['detalle']), False)
eq('[factura] Ultra Pro (EAN de 11 cifras) ya NO cae en «EAN forma rara»', 'EAN problematicos: 0 ' in out, True)

eq('[factura] 🔴 sondeo_keepa: SOLO lo preguntado por EAN (Chai -> B0CHAI)',
   [(s['ean'], s['asin']) for s in b['sondeo']], [('8412345678905', 'B0CHAI')])

# ---------------------------------------------------------------------------
# [proveedor] DINOTOYS con el MISMO catalogo (y su columna asin): nada cambia
# ---------------------------------------------------------------------------
cod, b, out = correr('proveedor')
eq('[proveedor] 🔴 el run sale VERDE (exit 0)', cod, 0)
eq('[proveedor] 🔴 la columna asin NO se usa: cero preguntas por ASIN en Fase 1',
   [q for q in b['preguntas'] if q['por'] == 'asin_f1'], [])
for e in ('7185897225606', '8400000000017', '8412345678905'):
    eq('[proveedor] el EAN %s se pregunta por EAN, como hasta hoy' % e, preguntado_por_ean(b, e), True)
eq('[proveedor] el EAN de 11 cifras sigue cayendo en «EAN forma rara», como hasta hoy',
   ('EAN problematicos: 1 ' in out) and not preguntado_por_ean(b, '74427811266'), True)
eq('[proveedor] KaffeK por EAN: centinela «Keepa sin ASIN» en sondeo_keepa',
   ('7185897225606', None, 'Keepa sin ASIN') in [(s['ean'], s['asin'], s['motivo']) for s in b['sondeo']], True)

print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK')
