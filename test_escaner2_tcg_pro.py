# -*- coding: utf-8 -*-
"""Banco del ESCANEO PRO DE TCG (encargo T3, 14-oct-2026; copiado del de OcioStock, encargo OC3): la parte pura y los
DOS programas de verdad, con dobles. Sin red, sin secretos, sin produccion. 🔴 Repo PUBLICO (Seguridad 21): la foto de
TCG de aqui es INVENTADA (EAN de mentira con su digito de control bueno, precios redondos, marcas reales sin precio).

PARTE A · LO PURO (escaner2_tcg_pro.py), en este proceso:
  A1  las marcas del director (marcas + marcas_es, sin idioma ni rank) y el filtro de marca por modo: el del director
      (el nombre de la regla DENTRO del de la fila, como el viejo), todas (las sin marca tambien) y elegidas
      (coincidencia EXACTA, como HEO);
  A2  la foto: solo lo que se puede comprar ya (sin reposicion ni preventa), sin chase suelto, la caja C «5 + 1» SI
      (es_chase y es_caja), PA = precio_escalon SIN descuento, el «sin tramo leído» entra con su suelto y su aviso, el
      EAN de 14 con un 0 delante entra por sus 13 y las demas formas raras no, sin precio de compra fuera, una fila por
      EAN base con el menor PA (a igualdad, la suelta), «caja de 6» marcada; crudo = previas + foto, y si no, lo dice;
  A3  🔴 mutantes de lo puro: cada uno, A2 en rojo.

PARTE B · LOS PROGRAMAS (escaner2_tcg_barrido.py y escaner2_tcg_cruce.py), cada uno en su proceso, contra un `supabase`
en memoria:
  B1  [sin_llave] sin la llave de servicio no nace ningun cliente; [ofertas] el modo elegidas con ofertas, tampoco;
  B2  [marcas] foto → barrido → 'esperando_csv' con su foto, eans.txt y barrido.json → los CUATRO CSV (ES, IT, FR, DE,
      con la CABECERA REAL del Visualizador y una FICHA COMPARTIDA) → cruce → 'lista', cuadra en los cuatro, PA =
      precio_escalon, la ficha compartida dividida (Z2) y el Excel: las hojas del PRO de HEO en su orden (sin
      «Chase_manual»), «Análisis» con «Ficha compartida», «Uds. escalón», «Precio unidad» y «Aviso del tramo» AL FINAL,
      «caja de 6» en «Coherencia caja», y la biblioteca puede leer su ruta;
  B3  🔴 el registro (repo PUBLICO) no lleva ni un EAN, precio, ASIN, nombre ni marca;
  B4  nada escribe fuera de escaner2_* ni del almacen tcg/<pasada>/; disp_*, reglas_director y productos acaban como
      empezaron;
  B5  [todas] y [elegidas]: su foto; [ajena] una foto que no es la de su ultima pasada aplicada, y [lineas] una pasada
      cuyas lineas no son articulos + sin EAN + repetidos: ROJO y la pasada 'fallida' sin foto.
"""
import base64
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# ═══════════════════════════════════════════════════════════════════════════════
# EL DOBLE DE SUPABASE (el de test_escaner2_ociostock_pro.py, copiado: cada banco, el suyo)
# ═══════════════════════════════════════════════════════════════════════════════
class _Resp:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Consulta:
    def __init__(self, bd, tabla):
        self.bd, self.tabla = bd, tabla
        self.op, self.filtros, self.payload = 'select', [], None
        self.cuenta, self.orden, self.rango, self.tope = False, None, None, None

    def select(self, _cols='*', count=None):
        self.op, self.cuenta = 'select', (count == 'exact')
        return self

    def insert(self, filas):
        self.op, self.payload = 'insert', filas if isinstance(filas, list) else [filas]
        return self

    def update(self, cambios):
        self.op, self.payload = 'update', cambios
        return self

    def eq(self, k, v):
        self.filtros.append((k, v))
        return self

    def order(self, col, desc=False):
        self.orden = (col, desc)
        return self

    def range(self, a, b):
        self.rango = (a, b)
        return self

    def limit(self, n):
        self.tope = n
        return self

    def execute(self):
        self.bd.setdefault('ops', []).append([self.bd.get('programa'), self.op, self.tabla])
        filas = self.bd['tablas'].setdefault(self.tabla, [])
        if self.op == 'insert':
            for f in self.payload:
                filas.append(json.loads(json.dumps(f, default=str)))
            return _Resp(self.payload)
        sel = [f for f in filas if all(str(f.get(k)) == str(v) for k, v in self.filtros)]
        if self.op == 'update':
            for f in sel:
                f.update(json.loads(json.dumps(self.payload, default=str)))
            return _Resp(sel)
        if self.orden:
            sel = sorted(sel, key=lambda f: (f.get(self.orden[0]) is None, str(f.get(self.orden[0]))),
                         reverse=self.orden[1])
        n = len(sel)
        if self.rango:
            sel = sel[self.rango[0]:self.rango[1] + 1]
        if self.tope is not None:
            sel = sel[:self.tope]
        return _Resp(sel, n if self.cuenta else None)


class _Cubo:
    def __init__(self, bd, cubo):
        self.bd, self.cubo = bd, cubo

    def _objs(self):
        return self.bd['storage'].setdefault(self.cubo, {})

    def upload(self, ruta, datos, _opciones=None):
        self.bd.setdefault('subidas', []).append(ruta)
        self._objs()[ruta] = base64.b64encode(datos if isinstance(datos, bytes) else datos.encode()).decode()
        return {'Key': ruta}

    def download(self, ruta):
        if ruta not in self._objs():
            raise RuntimeError('404 Object not found: %s/%s' % (self.cubo, ruta))
        return base64.b64decode(self._objs()[ruta])

    def list(self, carpeta=None, opciones=None):
        op = dict({'limit': 100, 'offset': 0}, **(opciones or {}))
        pref = (carpeta or '').rstrip('/') + '/'
        nombres = sorted(r[len(pref):] for r in self._objs() if r.startswith(pref) and '/' not in r[len(pref):])
        trozo = nombres[op['offset']:op['offset'] + op['limit']]
        return [{'name': n, 'created_at': '2026-10-14T09:%02d:00Z' % i, 'metadata': {'size': 1}}
                for i, n in enumerate(trozo)]


class _Cliente:
    def __init__(self, bd):
        self.bd = bd
        self.storage = types.SimpleNamespace(from_=lambda cubo: _Cubo(bd, cubo))

    def table(self, nombre):
        return _Consulta(self.bd, nombre)


def hijo(ruta_estado, programa):
    with open(ruta_estado, encoding='utf-8') as fh:
        bd = json.load(fh)
    bd['programa'] = programa
    clientes = []

    def crear(url, llave):
        clientes.append(llave)
        return _Cliente(bd)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = crear
    import runpy
    sys.argv = [programa]
    codigo = 0
    try:
        runpy.run_path(os.path.join(AQUI, programa), run_name='__main__')
    except SystemExit as ex:
        codigo = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
    finally:
        with open(ruta_estado, 'w', encoding='utf-8') as fh:
            json.dump(bd, fh, default=str)
        print('CLIENTES_CREADOS=%d' % len(clientes))
    sys.exit(codigo)


if __name__ == '__main__' and len(sys.argv) >= 4 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2], sys.argv[3])


def correr(ruta_estado, programa, env_extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ('SUPABASE_SERVICE_KEY', 'PASADA', 'GITHUB_RUN_ID', 'MODO_BARRIDO', 'MARCAS_ELEGIDAS',
                        'OFERTAS_ELEGIDAS')}
    env.update(env_extra, PYTHONIOENCODING='utf-8', SUPABASE_URL='https://doble.invalid')
    p = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--hijo', ruta_estado, programa],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=AQUI)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


import escaner2_motor as e2  # noqa: E402
import escaner2_tcg_pro as etc  # noqa: E402
import escaner2_heredado_pro as pro  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

M = e2.cargar_motor()


def ean13(cuerpo):
    return cuerpo + M._chk13(cuerpo)


# ═══════════════════════════════════════════════════════════════════════════════
# LA FOTO DE TCG, INVENTADA (la forma de disp_estado tras el encargo T2: la llave es el EAN crudo, con su «C»)
# ═══════════════════════════════════════════════════════════════════════════════
E1 = ean13('840000000201')    # Funko suelta, tramo 3,00 desde 12; su caja «5 + 1» (E1C), mas cara: gana la suelta
E2 = ean13('840000000202')    # Funko: la caja «5 + 1» (E2C) a 2,00 por figura y la suelta a 3,10: gana la CAJA
E3 = ean13('840000000203')    # Funko chase que no es caja: fuera (chase suelto)
E5 = ean13('840000000205')    # Ultra Pro SIN TRAMO LEIDO: entra con su suelto y el aviso
E6 = ean13('840000000206')    # Paladone: fuera de las marcas del director
E7 = ean13('840000000207')    # Magic the Gathering en INGLES: entra (Magic en cualquier idioma)
E8 = ean13('840000000208')    # sin marca
E10 = ean13('840000000210')   # suelta y caja al mismo PA: la suelta
E11 = ean13('840000000211')   # Yu-Gi-Oh! con el EAN en GTIN-14 con un 0 delante: entra por sus 13
E12 = ean13('840000000212')   # Banpresto con precio de compra 0: fuera
E13 = ean13('840000000213')   # Bandai Hobby («Bandai» del director, por trozo); comparte ficha con E1 en Amazon
EG = ean13('840000000214')    # Funko en reposicion (Backorder)
EP = ean13('840000000215')    # Funko en preventa (disponible = true a proposito: la preventa manda)
E_GS1 = '1' + ean13('840000000216')   # GTIN-14 de caja (indicador 1): forma rara, fuera
DISP = '00000000-0000-4000-8000-0000000d1700'
OTRA = '00000000-0000-4000-8000-0000000d1701'


def fila(llave, marca, unidad, escalon, uds, caja=False, chase=False, disp=True, pre=False, regla=None, core='auto',
         nombre=None, aviso=None, pasada=DISP, oferta=False):
    if core == 'auto':
        core = llave[:-1] if llave.endswith('C') else llave
    return {'proveedor': 'TCG', 'producto_prov': llave, 'ean_original': llave, 'ean_core': core,
            'ean_norm': core.lstrip('0') if core else None, 'marca': marca,
            'nombre': nombre or 'Producto inventado %s' % llave[-4:], 'categoria': 'Figuras',
            'precio_catalogo': None if unidad is None else unidad * (6 if caja else 1), 'precio_unidad': unidad,
            'precio_escalon': escalon, 'uds_escalon': uds, 'precio_pa': escalon, 'es_caja': caja,
            'uds_caja': 6 if caja else None, 'es_chase': chase, 'en_oferta': oferta, 'disponible': disp,
            'preorder': pre, 'regla': regla, 'aviso': aviso, 'pasada_id': pasada, 'ausencias': 0}


def foto_disp(pasada_ajena=False):
    return [
        fila(E1, 'Funko', 4.0, 3.0, 12),
        fila(E1 + 'C', 'Funko', 4.5, 3.5, 36, caja=True, chase=True, nombre='Caja inventada 5 + 1 Chase'),
        fila(E2 + 'C', 'Funko', 2.5, 2.0, 6, caja=True, chase=True),
        fila(E2, 'Funko', 3.5, 3.1, 6),
        fila(E3, 'Funko', 9.0, 9.0, 1, chase=True),
        fila(E5, 'Ultra Pro', 0.5, 0.5, 1, aviso=etc.AVISO_SIN_TRAMO),
        fila(E6, 'Paladone', 3.0, 3.0, 1),
        fila(E7, 'Magic the Gathering', 90.0, 85.0, 3, nombre='Display inventado Inglés - Magic The Gathering'),
        fila(E8, None, 2.0, 2.0, 1),
        fila(E10 + 'C', 'Funko', 4.0, 3.0, 6, caja=True, chase=True),
        fila(E10, 'Funko', 4.0, 3.0, 12, pasada=OTRA if pasada_ajena else DISP),
        fila(EG, 'Funko', 4.0, 3.0, 12, disp=False),
        fila(EP, 'Funko', 4.0, 3.0, 12, pre=True),
        fila('4000', 'Ultra Pro', 3.0, 3.0, 50, regla='ean_forma_rara', core=None),
        fila('0' + E11, 'Yu-Gi-Oh!', 20.0, 18.0, 2, regla='ean_forma_rara', core=None, oferta=True),
        fila(E_GS1, 'Ultra Pro', 40.0, 40.0, 1, regla='ean_forma_rara', core=None),
        fila(E12, 'Banpresto', 0.0, 0.0, 1),
        fila(E13, 'Bandai Hobby', 6.0, 5.0, 4),
    ]


N_SIN_EAN = 2
N_REPETIDOS = 3
N_CRUDO = len(foto_disp()) + N_SIN_EAN          # 20 articulos (las lineas del Excel: 23)
REGLA = {'proveedor': 'TCG', 'activo': True, 'marcas': ['Bandai', 'Banpresto', 'Dragon Shield', 'Funko', 'Ultra Pro'],
         'marcas_es': ['Magic', 'Yu-Gi-Oh'], 'col_idioma': 'Idioma', 'incluir_estados': ['Oferta', 'Saldo'],
         'rank_maximo': 30000}
DIRECTOR = ['Bandai', 'Banpresto', 'Dragon Shield', 'Funko', 'Ultra Pro', 'Magic', 'Yu-Gi-Oh']

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE A · LO PURO
# ═══════════════════════════════════════════════════════════════════════════════
print('A1 · las marcas del director y el filtro de marca, por modo')
eq('A1 · marcas del director: marcas y marcas_es, sin idioma ni rank ni estados', etc.marcas_del_director(REGLA),
   DIRECTOR)
_q, _i = etc.filtro_marca('marcas', DIRECTOR)
eq('A1 · marcas: la regla del viejo (el nombre de la regla dentro del de la fila, sin mayúsculas)',
   [_q(m) for m in ('Funko', 'Bandai Hobby', 'Magic the Gathering', 'Yu-Gi-Oh!', 'Paladone', None, 'ULTRA PRO')],
   [True, True, True, True, False, False, True])
eq('A1 · …y guarda las marcas del director', _i['marcas_reales'], DIRECTOR)
_q, _i = etc.filtro_marca('todas')
eq('A1 · todas: también las sin marca, y sin marcas que guardar', ([_q(m) for m in ('Paladone', None)], _i['marcas_reales']),
   ([True, True], None))
_q, _i = etc.filtro_marca('elegidas', elegidas=['Paladone'])
eq('A1 · elegidas: coincidencia EXACTA (sin mayúsculas), como HEO', [_q(m) for m in ('PALADONE', 'Paladone X',
                                                                                    ' paladone ')],
   [True, False, True])
for _modo, _args in (('marcas', ([],)), ('elegidas', (None, [])), ('raro', ())):
    try:
        etc.filtro_marca(_modo, *_args)
        _r = 'pasa'
    except etc.FalloTCG:
        _r = 'para'
    eq('A1 · %s sin marcas (o desconocido): para' % _modo, _r, 'para')


def comprobar_foto(mod):
    """A2 entero contra un modulo (el de verdad o un mutante). Devuelve los nombres de lo que falla; si revienta, eso
    tambien es rojo (y se dice con que)."""
    try:
        return _comprobar_foto(mod)
    except Exception as ex:  # noqa: BLE001 - un mutante que rompe la foto tambien la pone en rojo
        return [('revienta', type(ex).__name__, None)]


def _comprobar_foto(mod):
    rotas = []

    def chk(nombre, obtenido, esperado):
        if obtenido != esperado:
            rotas.append((nombre, obtenido, esperado))
    quiere, _ = mod.filtro_marca('marcas', mod.marcas_del_director(REGLA))
    foto, apartados, cuentas, escalon = mod.construir_foto(foto_disp(), quiere, M, N_CRUDO, N_SIN_EAN, 'marcas')
    por = {f['ean_core']: f for f in foto}
    chk('foto', sorted(por), sorted([E1, E2, E5, E7, E10, E11, E13]))
    chk('llaves', {k: por[k]['producto_heo'] for k in por},
        {E1: E1, E2: E2 + 'C', E5: E5, E7: E7, E10: E10, E11: '0' + E11, E13: E13})
    chk('PA = precio_escalon, sin descuento, y el del Excel aparte',
        [(por[k]['precio_unidad'], por[k]['precio_catalogo']) for k in (E1, E2, E5, E7)],
        [(3.0, 4.0), (2.0, 2.5), (0.5, 0.5), (85.0, 90.0)])
    chk('caja', [(por[k]['es_caja'], por[k]['es_chase'], por[k]['uds_caja'], por[k]['aviso_caja']) for k in (E1, E2)],
        [(False, False, None, None), (True, True, 6, 'caja de 6')])
    chk('códigos', (por[E2]['ean_original'], por[E2]['codigos_keepa'][0], por[E11]['ean_original'],
                    por[E11]['codigos_keepa'][0]), (E2 + 'C', E2, '0' + E11, E11))
    previas = cuentas['previas']
    chk('previas', previas, {'chase_funko': 0, 'sin_gtin': 2, 'no_disponible': 2, 'marca_fuera': 2,
                             'estado_no_servible': 1, 'chase_suelto': 1, 'ean_forma_rara': 2,
                             'duplicado_proveedor': 3})
    chk('apartados', sorted((a['producto_heo'], a['motivo']) for a in apartados),
        sorted([(E6, 'marca_fuera'), (E8, 'marca_fuera'), (E3, 'chase_suelto'), ('4000', 'ean_forma_rara'),
                (E_GS1, 'ean_forma_rara'), (E12, 'estado_no_servible'), (E1 + 'C', 'duplicado_proveedor'),
                (E2, 'duplicado_proveedor'), (E10 + 'C', 'duplicado_proveedor')]))
    chk('cuadra', (cuentas['n_foto'], cuentas['n_previas'], cuentas['cuadra_previo']), (7, 13, True))
    chk('sin tramo y rescatados', (cuentas['n_sin_tramo'], cuentas['n_ean14_rescatado']), (1, 1))
    chk('escalón', (escalon.get(E1), escalon.get(E5)),
        ({'uds_escalon': 12, 'precio_unidad': 4.0, 'precio_escalon': 3.0, 'aviso': None},
         {'uds_escalon': 1, 'precio_unidad': 0.5, 'precio_escalon': 0.5, 'aviso': etc.AVISO_SIN_TRAMO}))
    chk('escalón de la caja: en figuras', escalon.get(E2 + 'C', {}).get('uds_escalon'), 6)
    chk('escalón solo de la foto', sorted(escalon), sorted(por[k]['producto_heo'] for k in por))
    _f, _a, c2, _e = mod.construir_foto(foto_disp(), quiere, M, N_CRUDO + 1, N_SIN_EAN, 'marcas')
    chk('Excel que no casa: no cuadra y lo dice', (c2['cuadra_previo'], 'el Excel tenía 21 artículos' in
                                                   (c2['motivo_previo'] or '')), (False, True))
    return rotas


print('A2 · la foto de la pasada')
_rotas = comprobar_foto(etc)
for _n, _o, _e in _rotas:
    eq('A2 · ' + _n, _o, _e)
eq('A2 · las catorce comprobaciones de la foto, en verde', len(_rotas), 0)
quiere_t, _ = etc.filtro_marca('todas')
_ft, _at, _ct, _et = etc.construir_foto(foto_disp(), quiere_t, M, N_CRUDO, N_SIN_EAN, 'todas')
eq('A2 · todas: entran Paladone y la sin marca (9), y cuadra', (len(_ft), _ct['cuadra_previo'], _ct['previas']['marca_fuera']),
   (9, True, 0))
_qe, _ = etc.filtro_marca('elegidas', elegidas=['PALADONE'])
_fe, _ae, _ce, _ee = etc.construir_foto(foto_disp(), _qe, M, N_CRUDO, N_SIN_EAN, 'elegidas')
eq('A2 · elegidas: una, y la marca fuera dice «no elegida»', (
    [f['ean_core'] for f in _fe], sorted({a['detalle'].split("'")[0] for a in _ae if a['motivo'] == 'marca_fuera'})),
   ([E6], ['Marca ']))
eq('A2 · …y su puerta previa se llama «Marca no elegida»', etc.nombre_previa('marca_fuera', 'elegidas'), 'Marca no elegida')
eq('A2 · las rutas que admiten los checks de la v2',
   (etc.ruta_lista(DISP), etc.ruta_excel(DISP, OTRA, '20261014_1530')),
   ('tcg/%s/eans.txt' % DISP, 'tcg/%s/%s/Escaner2_TCG_20261014_1530.xlsx' % (DISP, OTRA)))
eq('A2 · el EAN de cruce: 12/13 tal cual, el 14 con 0 por sus 13, las demás formas raras nada',
   [etc.ean_de_la_foto({'ean_core': E1, 'regla': None}),
    etc.ean_de_la_foto({'ean_original': '0' + E11, 'ean_core': None, 'regla': 'ean_forma_rara'}),
    etc.ean_de_la_foto({'ean_original': E_GS1, 'ean_core': None, 'regla': 'ean_forma_rara'}),
    etc.ean_de_la_foto({'ean_original': '00' + E11, 'ean_core': None, 'regla': 'ean_forma_rara'}),
    etc.ean_de_la_foto({'ean_original': '0' + E11 + 'H', 'ean_core': None, 'regla': 'ean_forma_rara'}),
    etc.ean_de_la_foto({'ean_core': '84000', 'regla': None}),
    etc.ean_de_la_foto({'ean_original': '0' + E11, 'ean_core': None, 'regla': 'otra_regla'})],
   [(E1, False), (E11, True), (None, False), (None, False), (None, False), (None, False), (None, False)])

print('A3 · 🔴 mutantes de lo puro: cada uno pone A2 en rojo')
with io.open(os.path.join(AQUI, 'escaner2_tcg_pro.py'), encoding='utf-8') as _fh:
    FUENTE = _fh.read()
MUTANTES = [
    ('el PA es el precio del Excel', "'precio_unidad': _num(f.get('precio_escalon'))",
     "'precio_unidad': _num(f.get('precio_unidad'))"),
    ('el × 0,99 de OcioStock', "'precio_unidad': _num(f.get('precio_escalon'))",
     "'precio_unidad': _num(f.get('precio_escalon')) * 0.99"),
    ('la preventa entra', "if not f.get('disponible') or f.get('preorder'):", "if not f.get('disponible'):"),
    ('el chase que no es caja entra', "if f.get('es_chase') and not f.get('es_caja'):", "if False:"),
    ('fuera toda caja con chase', "if f.get('es_chase') and not f.get('es_caja'):", "if f.get('es_chase'):"),
    ('gana la más cara', "return clave(a) < clave(b)", "return clave(a) > clave(b)"),
    ('a igualdad, la caja', "bool(f.get('es_caja')), str(f.get('producto_prov')", "not f.get('es_caja'), str(f.get('producto_prov')"),
    ('sin «caja de 6»', "'aviso_caja': TEXTO_CAJA if caja else None", "'aviso_caja': None"),
    ('sin las sin EAN en el cuadre', "if cuentas['n_filas'] + previas['sin_gtin'] != cuentas['n_crudo']:",
     "if cuentas['n_filas'] != cuentas['n_crudo']:"),
    ('sin rescate del 14 con 0', "return m.group(1), True", "return None, False"),
    ('rescate de cualquier 14', r"re.compile(r'0(\d{13})')", r"re.compile(r'\d(\d{13})')"),
    ('el precio 0 entra', "if pa is None or pa <= 0:", "if pa is None:"),
    ('el director por igualdad', "any(b in str(m or '').lower() for b in bajas)", "str(m or '').lower() in bajas"),
    ('sin Magic ni Yu-Gi-Oh', "list(regla.get('marcas') or []) + list(regla.get('marcas_es') or [])",
     "list(regla.get('marcas') or [])"),
    ('sin el aviso del tramo', "'aviso': f.get('aviso') or None}", "'aviso': None}"),
]
for _nombre, _antes, _despues in MUTANTES:
    if FUENTE.count(_antes) != 1:
        eq('A3 · el ancla del mutante «%s» es única' % _nombre, FUENTE.count(_antes), 1)
        continue
    _mod = types.ModuleType('mutante')
    exec(compile(FUENTE.replace(_antes, _despues), 'mutante', 'exec'), _mod.__dict__)
    eq('A3 · mutante «%s»: A2 en rojo' % _nombre, len(comprobar_foto(_mod)) > 0, True)

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE B · LOS DOS PROGRAMAS, DE PUNTA A PUNTA
# ═══════════════════════════════════════════════════════════════════════════════
with io.open(os.path.join(AQUI, 'test_escaner2_osma_cabecera.json'), encoding='utf-8') as fh:
    CABECERA = json.load(fh)['cabecera']
COL_PAIS, COL_CAIDAS = e2.columnas_keepa()
COL_PADRE, COL_NVAR, COL_RANK = e2.columnas_ficha_compartida()
C = pro.CSV_COLS


def csv_real(pais, filas):
    """Un export del Visualizador con la CABECERA REAL (561 columnas, la del banco de OSMA) y solo lo que se lee."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CABECERA)
    ix = {h: i for i, h in enumerate(CABECERA)}
    for asin, eans, caidas, precio, titulo, padre, nvar in filas:
        fila_ = [''] * len(CABECERA)
        for h, v in ((C['asin'], asin), (COL_PAIS, pais), ('Título', titulo), (C['ean'], eans),
                     (C['rank'], '9000'), (C['rank90'], '11000'), (COL_CAIDAS, caidas), (C['buybox'], precio),
                     (C['es_fba'], 'yes'), (C['nuevo'], precio), (C['fba'], '3.10'), (C['compct'], '15.01 %'),
                     (COL_NVAR, nvar), (COL_PADRE, padre)):
            fila_[ix[h]] = v
        w.writerow(fila_)
    return ('\ufeff' + buf.getvalue()).encode('utf-8')


ASIN1, ASIN2, ASIN5, ASIN10, ASIN13 = 'B0TCGX0001', 'B0TCGX0002', 'B0TCGX0005', 'B0TCGX0010', 'B0TCGX0013'
PADRE = 'B0TCGXPADR'
PRODUCTOS = [{'id': 1, 'ean': E1, 'asin': ASIN1, 'nombre': 'Figura de Moloka', 'activo': True, 'es_chase': False,
              'iva_pct': 0.21, 'stock_moloka': 3}]
SEMBRADAS = ('productos', 'inventario_fba', 'disp_pasada', 'disp_estado', 'reglas_director', 'escaner2_parametros')


def estado_inicial(escena):
    n_crudo_disp = N_CRUDO + N_REPETIDOS + (1 if escena == 'lineas' else 0)
    return {'tablas': {
        'escaner2_parametros': [{'proveedor': 'HEO', 'umbral_caidas_30d': 6, 'paises_filtro': ['ES', 'IT', 'FR', 'DE'],
                                 'paises_calculo': ['ES', 'IT', 'FR', 'DE']},
                                # La fila de TCG que deja la migracion de la v2: el corte y los cuatro paises.
                                {'proveedor': 'TCG', 'umbral_caidas_30d': 6,
                                 'paises_filtro': ['ES', 'IT', 'FR', 'DE'], 'paises_calculo': ['ES', 'IT', 'FR', 'DE'],
                                 'marcas_fijas': ['Funko', 'Ultra Pro', 'Ravensburger']}],
        'escaner2_pasada': [],
        'disp_pasada': [{'id': OTRA, 'proveedor': 'TCG', 'estado': 'aplicada', 'creada_en': '2026-10-14T06:20:00Z',
                         'n_leidas': 1, 'n_crudo': 2, 'n_sin_gtin': 1, 'n_duplicados': 0},
                        {'id': DISP, 'proveedor': 'TCG', 'estado': 'aplicada', 'creada_en': '2026-10-14T07:20:00Z',
                         'terminada_en': '2026-10-14T07:21:00Z', 'n_leidas': len(foto_disp()), 'n_crudo': n_crudo_disp,
                         'n_sin_gtin': N_SIN_EAN, 'n_duplicados': N_REPETIDOS, 'fichero_md5': 'f' * 32,
                         'huella_contenido': 'e' * 32},
                        {'id': 'leyendo-ahora', 'proveedor': 'TCG', 'estado': 'leyendo',
                         'creada_en': '2026-10-14T08:20:00Z'}],
        'disp_estado': foto_disp(pasada_ajena=(escena == 'ajena')),
        'reglas_director': [REGLA, {'proveedor': 'HEO', 'activo': True, 'marcas': ['Otra'], 'marcas_es': []}],
        'productos': json.loads(json.dumps(PRODUCTOS)),
        'inventario_fba': [],
    }, 'storage': {'escaner2': {}}}


def caso(escena, env=None):
    tmp = tempfile.mkdtemp(prefix='e2tcg_')
    ruta = os.path.join(tmp, 'estado.json')
    inicial = estado_inicial(escena)
    with open(ruta, 'w', encoding='utf-8') as fh:
        json.dump(inicial, fh)
    cod, log = correr(ruta, 'escaner2_tcg_barrido.py', dict({'SUPABASE_SERVICE_KEY': 'svc-de-mentira',
                                                             'GITHUB_RUN_ID': '818181'}, **(env or {})))
    bd = json.load(open(ruta, encoding='utf-8'))
    return cod, log, bd, ruta, inicial


print('B1 · sin llave, o elegidas con ofertas: no se corre')
_tmp = tempfile.mkdtemp(prefix='e2tcg_')
_ruta = os.path.join(_tmp, 'estado.json')
json.dump(estado_inicial('marcas'), open(_ruta, 'w', encoding='utf-8'))
for _prog in ('escaner2_tcg_barrido.py', 'escaner2_tcg_cruce.py'):
    _cod, _log = correr(_ruta, _prog, {'PASADA': DISP})
    eq('B1 · %s: ROJO, la línea exacta y NINGÚN cliente' % _prog,
       (_cod, 'ESCANER2_NO_EJECUTADO: sin llave de servicio' in _log, 'CLIENTES_CREADOS=0' in _log), (1, True, True))
_cod, _log = correr(_ruta, 'escaner2_tcg_barrido.py', {'SUPABASE_SERVICE_KEY': 'x', 'MODO_BARRIDO': 'elegidas',
                                                       'MARCAS_ELEGIDAS': '["Funko"]', 'OFERTAS_ELEGIDAS': 'true'})
eq('B1 · elegidas con ofertas: ROJO, lo dice y NINGÚN cliente',
   (_cod, 'no tiene casilla de ofertas' in _log, 'CLIENTES_CREADOS=0' in _log), (1, True, True))
_cod, _log = correr(_ruta, 'escaner2_tcg_barrido.py', {'SUPABASE_SERVICE_KEY': 'x', 'MODO_BARRIDO': 'elegidas',
                                                       'MARCAS_ELEGIDAS': '["Funko", "a$b"]',
                                                       'OFERTAS_ELEGIDAS': 'false'})
eq('B1 · una marca con «$»: ROJO y NINGÚN cliente (la validación de HEO)',
   (_cod, 'selección de marcas no válida' in _log, 'CLIENTES_CREADOS=0' in _log), (1, True, True))
_cod, _log = correr(_ruta, 'escaner2_tcg_cruce.py', {'SUPABASE_SERVICE_KEY': 'x', 'PASADA': 'no-es-un-id'})
eq('B1 · el cruce con una pasada que no es un id: ROJO y NINGÚN cliente',
   (_cod, 'la pasada no es un id válido' in _log, 'CLIENTES_CREADOS=0' in _log), (1, True, True))

print('B2 · [marcas] la foto → barrido → la lista → los 4 CSV → cruce → Excel')
cod, log, bd, ruta, inicial = caso('marcas')
eq('B2 · el barrido sale en VERDE', cod, 0)
pas = [p for p in bd['tablas']['escaner2_pasada'] if p.get('run_id') == 818181][0]
PASADA = pas['id']
eq('B2 · 🔴 la pasada: TCG, modo marcas, esperando_csv, artículos 20 = previas 13 + foto 7, las marcas del director',
   (pas['proveedor'], pas['modo'], pas['estado'], pas['n_crudo'], pas['n_foto'],
    sum(pas['p_' + p] for p in e2.PUERTAS_PREVIAS), pas['n_tandas'], pas['ruta_lista'], pas['marcas'], pas['ofertas']),
   ('TCG', 'marcas', 'esperando_csv', 20, 7, 13, 1, 'tcg/%s/eans.txt' % PASADA, DIRECTOR, False))
_foto = [f for f in bd['tablas']['escaner2_foto'] if f['pasada_id'] == PASADA]
eq('B2 · la foto en la base: 7, y las listas de las puertas previas: 9',
   (len(_foto), len([a for a in bd['tablas']['escaner2_apartado'] if a['pasada_id'] == PASADA])), (7, 9))
_alm = bd['storage']['escaner2']
_txt = lambda k: base64.b64decode(_alm[k]).decode('utf-8')  # noqa: E731
eq('B2 · en el almacén: eans.txt y barrido.json', sorted(k.split('/')[-1] for k in _alm), ['barrido.json', 'eans.txt'])
eq('B2 · eans.txt: los siete EAN (el de la caja sin su «C», el de 14 por sus 13)',
   sorted(_txt('tcg/%s/eans.txt' % PASADA).split('\n')), sorted([E1, E2, E5, E7, E10, E11, E13]))
_side = json.loads(_txt('tcg/%s/barrido.json' % PASADA))
eq('B2 · barrido.json: de qué foto sale, las líneas del Excel, los sin tramo y el escalón de cada fila',
   (_side['disp_pasada'], _side['n_lineas_excel'], _side['n_sin_tramo'], sorted(_side['escalon']),
    _side['escalon'][E2 + 'C']),
   (DISP, 23, 1, sorted([E1, E2 + 'C', E5, E7, E10, '0' + E11, E13]),
    {'uds_escalon': 6, 'precio_unidad': 2.5, 'precio_escalon': 2.0, 'aviso': None}))

_carpeta = 'tcg/%s/csv/' % PASADA
# E1 y E13 comparten ficha en Amazon (mismo padre y puesto, 3 variaciones): 30 ventas ÷ 3 = 10, se venden y llevan la
# marca. E2 y E5 se venden; E10 no; E7 y E11 no están en Keepa.
_filas = [(ASIN1, E1, '30', '12.95', 'Figura uno', PADRE, '3'), (ASIN13, E13, '30', '19.95', 'Figura trece', PADRE, '3'),
          (ASIN2, E2, '30', '12.95', 'Figura dos', '', ''), (ASIN5, E5, '30', '4.95', 'Fundas cinco', '', ''),
          (ASIN10, E10, '2', '12.95', 'Figura diez', '', '')]
for _i, _p in enumerate(('es', 'it', 'fr', 'de')):
    _alm[_carpeta + '20261014-1000%02d-KeepaExport-2026-10-14-VisualizadorDeProductos (%d).csv' % (_i, _i)] = \
        base64.b64encode(csv_real(_p, _filas)).decode()
bd.pop('programa', None)
json.dump(bd, open(ruta, 'w', encoding='utf-8'), default=str)
cod2, log2 = correr(ruta, 'escaner2_tcg_cruce.py', {'SUPABASE_SERVICE_KEY': 'svc-de-mentira', 'PASADA': PASADA,
                                                     'GITHUB_RUN_ID': '828282'})
bd = json.load(open(ruta, encoding='utf-8'))
T = bd['tablas']
_alm = bd['storage']['escaner2']
eq('B2 · el cruce sale en VERDE', cod2, 0)
cr = [c for c in T['escaner2_cruce'] if c.get('run_id') == 828282][0]
eq('B2 · 🔴 el cruce: lista, cuadra, artículos 20 = previas 13 + 7 puertas, en los CUATRO países',
   (cr['estado'], cr['cuadra'], cr['n_crudo'], cr['n_previas'], cr['n_entradas'], sum(cr['n_' + x] for x in 'abcdef'),
    cr['paises_filtro'], cr['paises_calculo'], cr['paises_usados'], cr['aviso']),
   ('lista', True, 20, 13, 7, 7, ['ES', 'IT', 'FR', 'DE'], ['ES', 'IT', 'FR', 'DE'], ['ES', 'IT', 'FR', 'DE'], None))
_res = {f['ean_core']: r for r in T['escaner2_resultado_ean'] for f in T['escaner2_foto'] if f['id'] == r['foto_id']}
_pais = {}
for _r in T['escaner2_resultado_pais']:
    _pais.setdefault(_r['resultado_ean_id'], {})[_r['pais']] = _r
eq('B2 · 🔴 E1: COMPRAR con PA = precio_escalon (3,00, sin 0,99) en los cuatro países',
   (_res[E1]['puerta'], sorted(_pais[_res[E1]['id']]), {r['pa'] for r in _pais[_res[E1]['id']].values()}),
   ('f', ['DE', 'ES', 'FR', 'IT'], {3.0}))
eq('B2 · 🔴 E2: la caja «5 + 1», con su PA por figura (2,00), sin dividir entre 6',
   (_res[E2]['puerta'], _pais[_res[E2]['id']]['ES']['pa']), ('f', 2.0))
eq('B2 · 🔴 E5 sin tramo leído: decide con su suelto (0,50)', _pais[_res[E5]['id']]['ES']['pa'], 0.5)
eq('B2 · 🔴 (Z2) E1 y E13 comparten ficha: 30 ÷ 3 = 10 por variación, pasan y el detalle lo dice',
   (_res[E13]['puerta'] in ('e', 'f'), 'compartida' in (_res[E1]['detalle'] or '').lower()), (True, True))
eq('B2 · E10 no se vende (puerta c) y E7/E11 no están en Keepa (puerta a)',
   (_res[E10]['puerta'], _res[E7]['puerta'], _res[E11]['puerta']), ('c', 'a', 'a'))

_xl = [k for k in _alm if k.startswith('tcg/%s/%s/Escaner2_TCG_' % (PASADA, cr['id']))]
eq('B2 · el Excel, en su carpeta y con su nombre (el que guarda el cruce)', (len(_xl), cr['ruta_excel'] == _xl[0]),
   (1, True))
_wb = load_workbook(io.BytesIO(base64.b64decode(_alm[_xl[0]])))
eq('B2 · las hojas del PRO de HEO, en su orden (sin «Chase_manual», que es de HEO)', _wb.sheetnames,
   ['Análisis', 'Descartados', 'Ambiguos', 'Sin_rank', 'Precio por lote', 'Resumen', 'Comparación', 'Varias fichas',
    'Puertas', 'Puertas previas'])
_cab = [c.value for c in _wb['Análisis'][1]]
eq('🔴 B2 · «Análisis»: las del PRO de HEO (con «Ventas») y, AL FINAL, «Ficha compartida» y las tres de TCG',
   _cab, e2.columnas_analisis() + [e2.COLUMNA_FICHA_COMPARTIDA, 'Uds. escalón', 'Precio unidad', 'Aviso del tramo'])
eq('B2 · «Ventas» en lugar de los dos rank', ('Ventas' in _cab, any('rank' in str(c).lower() for c in _cab)), (True, False))
_ix = {n: _cab.index(n) for n in _cab}
_an = list(_wb['Análisis'].iter_rows(min_row=2, values_only=True))
_por = {}
for _r in _an:
    _por.setdefault(_r[_ix['EAN']], []).append(_r)
eq('B2 · «Análisis»: los que se venden, una fila por país (los cuatro)',
   sorted((k, sorted(r[_ix['País']] for r in v)) for k, v in _por.items()),
   sorted((k, ['DE', 'ES', 'FR', 'IT']) for k in (E1, E2 + 'C', E5, E13)))
eq('🔴 B2 · E1: PA 3,00, Uds. escalón 12, Precio unidad 4,00 y sin aviso, en las cuatro filas',
   {(r[_ix['PA (€)']], r[_ix['Uds. escalón']], r[_ix['Precio unidad']], r[_ix['Aviso del tramo']]) for r in _por[E1]},
   {(3.0, 12, 4.0, None)})
eq('🔴 B2 · E1: la «Ficha compartida» marcada; E2, sin marca',
   (all(r[_ix[e2.COLUMNA_FICHA_COMPARTIDA]] for r in _por[E1]),
    any(r[_ix[e2.COLUMNA_FICHA_COMPARTIDA]] for r in _por[E2 + 'C'])), (True, False))
eq('🔴 B2 · E5: «sin tramo leído» en «Aviso del tramo», con 1 ud y su suelto',
   {(r[_ix['PA (€)']], r[_ix['Uds. escalón']], r[_ix['Aviso del tramo']]) for r in _por[E5]},
   {(0.5, 1, 'sin tramo leído')})
eq('🔴 B2 · la caja: «caja de 6» en «Coherencia caja», PA 2,00, 6 figuras de escalón y 2,50 del Excel',
   {(r[_ix['Coherencia caja']], r[_ix['PA (€)']], r[_ix['Uds. escalón']], r[_ix['Precio unidad']])
    for r in _por[E2 + 'C']}, {('caja de 6', 2.0, 6, 2.5)})
_tabla = list(_wb['Análisis'].tables.values())[0]
eq('B2 · la tabla de «Análisis» cubre las tres columnas nuevas',
   (_tabla.ref.split(':')[1].rstrip('0123456789'), [c.name for c in _tabla.tableColumns][-3:]),
   (_wb['Análisis'].cell(row=1, column=len(_cab)).column_letter, ['Uds. escalón', 'Precio unidad', 'Aviso del tramo']))
_pu = list(_wb['Puertas'].iter_rows(values_only=True))
_pcab = list(_pu[0])
_pcaja = [r for r in _pu[1:] if r[0] == E2 + 'C'][0]
eq('B2 · «Puertas»: la caja con su rótulo y el precio de la caja (6 × 2,50)',
   (_pcaja[_pcab.index('Caja')], _pcaja[_pcab.index('Precio caja (€)')], len(_pu) - 1),
   ('caja con chase · 6 uds', 15.0, 7))
_resu = {r[0]: r[1] for r in _wb['Resumen'].iter_rows(values_only=True)}
eq('B2 · el Resumen: modo, marcas, cuadre, sin tramo, líneas, compartidas y las puertas previas con nombre de TCG',
   (_resu.get('Modo del barrido'),
    _resu.get('Marcas del director (Magic y Yu-Gi-Oh en cualquier idioma, sin corte de rank)'), _resu.get('Cuadra'),
    _resu.get('Filas con su precio suelto («sin tramo leído»)'), _resu.get('Líneas del Excel de TCG (con los EAN repetidos)'),
    _resu.get('Catálogo crudo de TCG (artículos distintos del Excel)'),
    _resu.get('Fichas compartidas (productos de la lista, por país)'),
    _resu.get('Puerta previa · Sin stock, en reposición o en preventa'), _resu.get('Puerta previa · Sin precio de compra')),
   ('marcas de siempre', ', '.join(DIRECTOR), 'SÍ', 1, 23, 20, 'ES 2 · IT 2 · FR 2 · DE 2', 2, 1))

print('B3 · 🔴 el registro (repo PÚBLICO) no lleva ni un EAN, precio, ASIN, nombre ni marca')
_prohibido = [E1, E2, E3, E5, E6, E7, E8, E10, E11, E12, E13, EG, EP, E_GS1, ASIN1, ASIN2, ASIN5, ASIN10, ASIN13,
              PADRE, '3.0', '2.0', '0.5', '85.0', '12.95', '19.95', 'Producto inventado', 'Figura uno', 'Fundas',
              'Display inventado', 'Funko', 'Ultra Pro', 'Paladone', 'Magic', 'Bandai', 'Banpresto']
eq('B3 · ni en el barrido ni en el cruce (si sale algo, la línea que lo lleva)',
   [(x, [ln for ln in (log + log2).splitlines() if x in ln][:2]) for x in _prohibido if x in log or x in log2], [])

print('B4 · solo se escribe en escaner2_* y en la carpeta de la pasada')
eq('B4 · las tablas escritas', sorted({t for _p, op, t in bd['ops'] if op != 'select'}),
   ['escaner2_apartado', 'escaner2_cruce', 'escaner2_foto', 'escaner2_pasada', 'escaner2_resultado_ean',
    'escaner2_resultado_pais'])
eq('B4 · y las sembradas acaban como empezaron',
   [t for t in SEMBRADAS if bd['tablas'][t] != json.loads(json.dumps(inicial['tablas'][t]))], [])
eq('B4 · en el almacén, solo tcg/<pasada>/', sorted({'/'.join(s.split('/')[:2]) for s in bd.get('subidas', [])}),
   ['tcg/' + PASADA])

print('B5 · los otros modos, una foto que no es la suya y unas líneas que no cuadran')
cod, log, bd, _r, _i0 = caso('todas', {'MODO_BARRIDO': 'todas'})
_p = bd['tablas']['escaner2_pasada'][0]
eq('B5 · [todas] VERDE, 9 en la foto (Paladone y la sin marca), sin marcas guardadas y sin leer reglas_director',
   (cod, _p['modo'], _p['n_foto'], _p['p_marca_fuera'], _p['marcas'],
    [t for _p2, op, t in bd['ops'] if t == 'reglas_director']), (0, 'todas', 9, 0, None, []))
cod, log, bd, _r, _i0 = caso('elegidas', {'MODO_BARRIDO': 'elegidas', 'MARCAS_ELEGIDAS': '["Paladone"]',
                                          'OFERTAS_ELEGIDAS': 'false'})
_p = bd['tablas']['escaner2_pasada'][0]
eq('B5 · [elegidas] VERDE, una en la foto, con su lista y ofertas a false',
   (cod, _p['modo'], _p['n_foto'], _p['marcas'], _p['ofertas']), (0, 'elegidas', 1, ['Paladone'], False))
cod, log, bd, _r, _i0 = caso('ajena')
_p = bd['tablas']['escaner2_pasada'][0]
eq('B5 · 🔴 [ajena] una fila de otra pasada de disponibilidad: ROJO, la pasada fallida con el motivo y SIN foto',
   (cod, _p['estado'], 'no es la de su última pasada aplicada' in (_p['motivo_fallo'] or ''),
    bd['tablas'].get('escaner2_foto', [])), (1, 'fallida', True, []))
cod, log, bd, _r, _i0 = caso('lineas')
_p = bd['tablas']['escaner2_pasada'][0]
eq('B5 · 🔴 [lineas] las líneas del Excel no son artículos + sin EAN + repetidos: ROJO, fallida y SIN foto',
   (cod, _p['estado'], 'no cuadra' in (_p['motivo_fallo'] or ''), bd['tablas'].get('escaner2_foto', [])),
   (1, 'fallida', True, []))

print()
if fallos:
    print('FALLAN %d: %s' % (len(fallos), fallos))
    sys.exit(1)
print('TODO OK')
