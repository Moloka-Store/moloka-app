# -*- coding: utf-8 -*-
"""ESCANER 2 · EL MOTOR PURO DEL BARRIDO DE HEO, EN SOMBRA (encargo B, trozo 1, 24-sep-2026)

QUE ES. La parte de CALCULO del escaner nuevo de HEO, sin red y sin base: construir la
foto del catalogo, leer los CSV del Visualizador de Keepa, decidir por que PUERTA sale
cada EAN, comprobar el CUADRE y compararse con el escaner viejo. La red (API de HEO,
Supabase, Storage) vive en los dos programas que lo usan:
  · escaner2_heo_barrido.py  (workflow escaner2-heo-barrido.yml): baja HEO y deja la foto.
  · escaner2_heo_cruce.py    (workflow escaner2-heo-cruce.yml):   cruza los CSV y decide.

🔴 NO SE COPIA NI UNA LINEA DEL ESCANER VIEJO: SE LEE DE SU FICHERO, POR ESTRUCTURA.
   `moloka_escaner_nube.py` no se puede importar (crea el cliente de Keepa y sale a la red
   al cargar) y el encargo prohibe modificarlo. Asi que `calc_rentabilidad`, `decision_de`,
   las reglas de EAN/chase/caja (`partir_ean`, `clasificar_chase`, `variantes_ean` con el
   rescate de GTIN), el IVA con su origen, `ISD_PAIS`, `UNIDADES_CASE_TCG` y el perfil HEO
   se SACAN del fichero real con `ast` -- buscando cada `def` y cada asignacion de NIVEL
   SUPERIOR por su nombre, no con un grep -- y se EJECUTAN. Es el mismo metodo con el que
   `test_escaner_memoria.py` prueba las guardas del escaner. Consecuencias:
     · la formula que usa el escaner nuevo ES la del viejo, letra por letra, hoy y manana:
       si alguien la cambia alli, el nuevo la hereda sin tocar este fichero;
     · si alguien la BORRA o la RENOMBRA, esto no adivina: revienta con el nombre que falta.
   Lo mismo con el filtro del director (`_quiere` y sus marcas, de director_heo_prep.py) y
   con la tanda del Visualizador (descargar_heo.py). Las columnas del CSV salen del Escaner
   Pro (`CSV_COLS`, `leer_csv_visualizador`) y de `procesador_keepa_escaparate.py`
   (`TIPADAS`, medidas contra los exports reales del 17 y 18-ago-2026).

🔒 LO QUE NO SE PUEDE SACAR POR NOMBRE, porque en el viejo va escrito EN LINEA dentro de
   un bucle y no en una funcion, se replica aqui con el sitio de donde sale al lado:
   el dedup del proveedor y el guardarrail caja-vs-suelta (Celda 4 y siguientes), la
   division del PA por la caja (Celda 8), el diccionario de IVA por pais (Celda 8) y la
   eleccion del precio de venta del CSV (escanear_pro del Escaner Pro). El banco
   (test_escaner2_motor.py) coteja cada una contra su original ejecutandolo.
"""
import ast
import csv
import io
import math
import os
import re
from datetime import datetime, timezone

RUTA_MOTOR = 'moloka_escaner_nube.py'
RUTA_DIRECTOR_HEO = 'director_heo_prep.py'
RUTA_DESCARGAR_HEO = 'descargar_heo.py'
RUTA_ESCAPARATE = 'procesador_keepa_escaparate.py'

PROVEEDOR = 'HEO'

# Las seis puertas del encargo. Cada EAN de la foto sale por UNA y solo una.
PUERTAS = ('a', 'b', 'c', 'd', 'e', 'f')
NOMBRE_PUERTA = {
    'a': 'No está en Amazon',
    'b': 'Dos o más fichas',
    'c': 'No se vende',
    'd': 'Se vende sin margen',
    'e': 'VALORAR',
    'f': 'COMPRAR',
}
# Los motivos, por puerta. La c tiene los DOS del encargo; el resto afina el porque.
MOTIVOS = {
    'a_no_aparece': 'a', 'a_sin_asin': 'a',
    'b_varias_fichas': 'b',
    'c_pocas_caidas': 'c', 'c_sin_dato': 'c',
    'd_sin_margen': 'd', 'd_sin_datos': 'd',
    'e_valorar': 'e',
    'f_comprar': 'f',
}
# Lo que se aparta ANTES de la foto y se guarda EAN a EAN, con su motivo (escaner2_apartado).
MOTIVOS_APARTADO = ('chase_funko', 'estado_no_servible', 'chase_suelto', 'ean_forma_rara',
                    'duplicado_proveedor')
# 🔴 LAS PUERTAS PREVIAS (Fernando, 24-sep-2026): el cuadre empieza en el catalogo CRUDO de HEO,
#    no en la foto. Todo producto que devuelve HEO sale por UNA de estas o entra en la foto:
#        crudo = puertas previas + foto        y, al cruzar,        crudo = previas + a..f
#    En el orden en que se aplican. Ninguna regla de descarte cambia: solo se cuentan y se ven.
#    `sin_gtin`, `no_disponible` y `marca_fuera` solo se CUENTAN (sin GTIN no hay EAN que listar;
#    no disponible y marca fuera son el catalogo entero de HEO menos lo que se mira); las otras
#    cinco (MOTIVOS_APARTADO: el Funko chase y las cuatro ultimas) ademas se LISTAN en
#    escaner2_apartado.
PUERTAS_PREVIAS = ('chase_funko', 'sin_gtin', 'no_disponible', 'marca_fuera', 'estado_no_servible',
                   'chase_suelto', 'ean_forma_rara', 'duplicado_proveedor')
NOMBRE_PUERTA_PREVIA = {
    'chase_funko': 'Funko chase (código de caja)',
    'sin_gtin': 'Sin GTIN',
    'no_disponible': 'No disponible',
    'marca_fuera': 'Marca fuera de la lista',
    'estado_no_servible': 'Estado no servible',
    'chase_suelto': 'Chase suelto',
    'ean_forma_rara': 'Código de barras con forma rara',
    'duplicado_proveedor': 'Duplicado del proveedor',
}


class PiezaNoEncontrada(Exception):
    """Una pieza que el escaner nuevo lee del viejo ya no esta (o esta dos veces)."""


class CsvIlegible(Exception):
    """Un CSV del Visualizador que no se puede usar: se dice cual y por que, nunca se traga."""


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · SACAR PIEZAS DE UN FICHERO, POR ESTRUCTURA
# ═══════════════════════════════════════════════════════════════════════════════
def _nombres_asignados(nodo):
    """Los nombres a los que asigna un `ast.Assign` de nivel superior (`A = …` o `A, B = …`)."""
    salida = []
    for t in nodo.targets:
        if isinstance(t, ast.Name):
            salida.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            salida.extend(e.id for e in t.elts if isinstance(e, ast.Name))
    return salida


def sacar_piezas(ruta, defs, nombres, base=None):
    """Ejecuta, en un espacio de nombres propio, los `def` y las asignaciones de NIVEL SUPERIOR
    de `ruta` que se piden por nombre, EN EL ORDEN DEL FICHERO (una constante puede depender
    de otra: `ORIGEN_IVA_ASUMIDO` usa `IVA_DEFAULT_ES`). Devuelve ese espacio de nombres.

    🔴 Falla CERRADO: si falta una pieza, o si esta asignada DOS veces a nivel superior (no se
       sabria cual es la buena), lanza PiezaNoEncontrada con los nombres. Nunca devuelve medio
       motor."""
    with io.open(ruta, encoding='utf-8') as fh:
        arbol = ast.parse(fh.read(), ruta)
    por_def, por_nombre = {}, {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef) and nodo.name in defs:
            por_def.setdefault(nodo.name, []).append(nodo)
        elif isinstance(nodo, ast.Assign):
            for n in _nombres_asignados(nodo):
                if n in nombres:
                    por_nombre.setdefault(n, []).append(nodo)
    faltan = [d for d in defs if d not in por_def] + [n for n in nombres if n not in por_nombre]
    if faltan:
        raise PiezaNoEncontrada('%s: ya no tiene (a nivel superior) %s' % (ruta, ', '.join(faltan)))
    dobles = ([d for d, v in por_def.items() if len(v) > 1]
              + [n for n, v in por_nombre.items() if len(v) > 1])
    if dobles:
        raise PiezaNoEncontrada('%s: %s aparece(n) mas de una vez a nivel superior' % (ruta, ', '.join(dobles)))
    nodos = {}
    for lista in list(por_def.values()) + list(por_nombre.values()):
        nodos[id(lista[0])] = lista[0]
    cuerpo = sorted(nodos.values(), key=lambda n: n.lineno)
    ns = dict(base or {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=cuerpo, type_ignores=[])), ruta, 'exec'), ns)
    return ns


# Lo que el escaner nuevo usa del viejo. Si alguna desaparece, el arranque lo dice por su nombre.
DEFS_MOTOR = ('norm', '_num', 'partir_ean', 'clasificar', 'core_ean', 'clasificar_chase',
              '_chk13', '_ean_ok', 'variantes_ean', 'aviso_caja_incoherente',
              'calc_rentabilidad', 'decision_de',
              '_sup', 'iva_es_con_origen', 'iva_es_de', 'origen_iva_fila', 'es_propio')
NOMBRES_MOTOR = ('PAISES', 'IVA_DEFAULT_ES', 'IVA_IT', 'IVA_FR', 'IVA_DE', 'ALMACEN',
                 'COM_DIGITALES', 'UNIDADES_CASE_TCG', 'ISD_PAIS', 'SIN_ISD_HISTORICO',
                 '_RE_SUFIJO', '_RE_CAJA6', '_RE_CHASE_NOM', '_RE_CON_CHASE',
                 'UMBRAL_CAJA_VS_SUELTA', 'ORIGEN_IVA_FICHA', 'ORIGEN_IVA_ASUMIDO', 'PERFILES')


class Motor:
    """Las piezas del escaner viejo, ya ejecutadas. Se leen como atributos (`M.calc_rentabilidad`).

    🔑 Las funciones sacadas llevan como globales ESTE espacio de nombres, asi que el catalogo
       propio (`sup`, el que usa `iva_es_con_origen`) se pone aqui con `poner_catalogo_propio`
       y ellas lo ven igual que en el escaner viejo."""

    def __init__(self, ns):
        self._ns = ns

    def __getattr__(self, k):
        try:
            return self._ns[k]
        except KeyError:
            raise AttributeError(k)

    def poner_catalogo_propio(self, filas_productos):
        """Lo mismo que la Celda 5 del escaner viejo: `sup[norm(ean)] = fila`, solo filas con EAN."""
        sup = {}
        for p in filas_productos or []:
            if p.get('ean'):
                sup[self._ns['norm'](p['ean'])] = p
        self._ns['sup'] = sup
        return len(sup)

    def iva_por_pais(self, core):
        """El IVA de cada pais para ESTE producto, como la Celda 8 del escaner viejo:
        ES de la ficha (o el general, asumido); IT, FR y DE, el general del pais."""
        return {'ES': self.iva_es_de(core), 'IT': self.IVA_IT, 'FR': self.IVA_FR, 'DE': self.IVA_DE}


def cargar_motor(ruta=RUTA_MOTOR):
    return Motor(sacar_piezas(ruta, DEFS_MOTOR, NOMBRES_MOTOR, base={'re': re, 'sup': {}}))


def cargar_filtro_director(regla, ruta=RUTA_DIRECTOR_HEO):
    """El filtro de director_heo_prep.py, el suyo: `_quiere` con las marcas de `reglas_director`.
    Devuelve (quiere, info) con las marcas reales, si pide ofertas y el rank maximo."""
    ns = sacar_piezas(ruta, ('_quiere',), ('marcas', 'quiere_ofertas', 'marcas_reales', 'rank_max'),
                      base={'regla': regla})
    return ns['_quiere'], {'marcas_reales': list(ns['marcas_reales']),
                           'quiere_ofertas': bool(ns['quiere_ofertas']),
                           'rank_max': ns['rank_max']}


def tanda_visualizador(ruta=RUTA_DESCARGAR_HEO):
    """Cuantos EAN caben en una tanda del Visualizador: la `TANDA` de descargar_heo.py (modo
    completo), evaluada igual que alli (acepta HEO_TANDA del entorno). Una sola asignacion o
    nada: si hubiera dos, no se sabria cual manda."""
    with io.open(ruta, encoding='utf-8') as fh:
        arbol = ast.parse(fh.read(), ruta)
    asignaciones = [n for n in ast.walk(arbol)
                    if isinstance(n, ast.Assign) and 'TANDA' in _nombres_asignados(n)]
    if len(asignaciones) != 1:
        raise PiezaNoEncontrada('%s: se esperaba UNA asignacion a TANDA y hay %d' % (ruta, len(asignaciones)))
    valor = eval(compile(ast.Expression(asignaciones[0].value), ruta, 'eval'), {'int': int, 'os': os})
    if not isinstance(valor, int) or valor <= 0:
        raise PiezaNoEncontrada('%s: TANDA no es un entero positivo (%r)' % (ruta, valor))
    return valor


def columnas_keepa(ruta=RUTA_ESCAPARATE):
    """Las dos cabeceras que el lector del Escaner Pro NO lee y aqui hacen falta, sacadas de
    `TIPADAS` del procesador del escaparate (copiadas LITERALMENTE de los exports reales del
    Visualizador): el pais del fichero y las caidas del puesto en 30 dias."""
    ns = sacar_piezas(ruta, (), ('TIPADAS',))
    por_columna = {col: cab for cab, col, _t in ns['TIPADAS']}
    faltan = [c for c in ('dominio', 'rank_drops_30d') if c not in por_columna]
    if faltan:
        raise PiezaNoEncontrada('%s: TIPADAS ya no declara %s' % (ruta, ', '.join(faltan)))
    return por_columna['dominio'], por_columna['rank_drops_30d']


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · LA FOTO DEL CATALOGO (paso 2 del encargo)
# ═══════════════════════════════════════════════════════════════════════════════
def _apartado(fila, motivo, detalle, ean=None, precio=None):
    return {'producto_heo': fila.get('productNumber') or fila.get('producto_heo'),
            'ean_original': str(ean if ean is not None else (fila.get('ean') or '')).strip(),
            'nombre': fila.get('nombre') or '', 'marca': fila.get('marca') or '',
            'precio_catalogo': precio, 'motivo': motivo, 'detalle': detalle}


def construir_foto(filas_heo, chase_heo, quiere, M, n_crudo=None, n_sin_gtin=None, n_declarado=None):
    """Del catalogo CRUDO de HEO a la foto de la pasada, sin perder a nadie por el camino.

    `filas_heo, chase_heo` es lo que devuelve `descargar_catalogo_heo(con_chase=True)`;
    `n_crudo` (productos que se bajaron de HEO), `n_sin_gtin` (los que descargar_heo tira por no
    tener GTIN) y `n_declarado` (los que HEO DICE que tiene, `totalElements` de la API) salen de
    su log, porque esa funcion no los devuelve y NO se toca.

    Devuelve (foto, apartados, cuentas). Cada producto crudo sale por UNA puerta previa
    (PUERTAS_PREVIAS) o entra en la foto, en el MISMO orden que el viejo para el perfil HEO:
      0. descargar_heo desvia los Funko chase (codigo de caja; el viejo los manda a la puente de
         ASIN manual, que aqui NO se toca) y tira los que no traen GTIN;
      1. el filtro del director (`_quiere`): lo que no esta disponible, y lo disponible cuya marca
         no esta en la regla (ni es oferta, si la regla pide ofertas);
      2. Celda 4: estado servible, chase SUELTO fuera, EAN de forma rara fuera (los GTIN-14 caen
         aqui: el viejo los rechaza ANTES del rescate);
      3. dedup del proveedor: una fila por (EAN, caja), la mas barata;
      4. guardarrail caja-vs-suelta (marca, no borra) y el precio POR UNIDAD (Celda 8)."""
    perfil = M.PERFILES[PROVEEDOR]
    previas = {p: 0 for p in PUERTAS_PREVIAS}
    sel = []
    for f in filas_heo:
        if quiere(f):
            sel.append(f)
        # 🔑 `_quiere` es quien DECIDE; esto solo pone nombre al porque, con su misma primera
        #    condicion: lo que no esta disponible no pasa; lo disponible que no pasa es por marca.
        elif f.get('estado') != 'disponible':
            previas['no_disponible'] += 1
        else:
            previas['marca_fuera'] += 1
    chase_todo = list(chase_heo or [])
    apartados = []
    for c in chase_todo:
        apartados.append(_apartado(
            c, 'chase_funko',
            'Funko chase: HEO lo vende en caja con código de caja y no cruza por EAN '
            '(el escáner viejo lo manda a la tabla de ASIN a mano)',
            ean=c.get('ean_caja') or '', precio=c.get('precio_caja')))

    filas = []
    for f in sel:
        # Celda 4 del viejo, perfil HEO: estado permitido, sin columna de stock (se asume 1).
        if perfil.get('estados_ok'):
            if str(f.get(perfil['col_estado'], '')).strip() not in perfil['estados_ok']:
                apartados.append(_apartado(f, 'estado_no_servible',
                                           'Estado %r fuera de %s' % (f.get(perfil['col_estado']),
                                                                      perfil['estados_ok'])))
                continue
        ean_in = str(f.get(perfil['col_ean']) or '').strip()
        nombre = f.get(perfil['col_nombre']) or ''
        es_case, es_caja6, descartar = M.clasificar_chase(nombre, ean_in)
        if descartar:
            apartados.append(_apartado(f, 'chase_suelto',
                                       'Chase SUELTO descartado (solo se compra en caja de 6)'))
            continue
        core = M.core_ean(ean_in)
        if (not core.isdigit()) or len(core) not in (12, 13):
            apartados.append(_apartado(f, 'ean_forma_rara', 'EAN forma rara (len=%d)' % len(core)
                                       + (': GTIN-14, el escáner viejo lo rechaza antes del rescate'
                                          if core.isdigit() and len(core) == 14 else '')))
            continue
        filas.append({
            'producto_heo': f.get('productNumber'), 'ean_in': ean_in, 'core': core,
            'nombre': nombre, 'marca': f.get(perfil['col_marca']) or '',
            'categoria': f.get('categoria') or '',
            'pa': M._num(f.get(perfil['col_pa'], '')),
            'es_chase': bool(es_case), 'es_caja': bool(es_caja6),
            'uds_caja': (M.partir_ean(ean_in)[2] or M.UNIDADES_CASE_TCG),
            'en_oferta': f.get('en_oferta') == 'SI', 'campana': f.get('campana') or '',
            'disponibilidad': f.get('disponibilidad') or '', 'fin_de_vida': f.get('fin_de_vida') == 'SI',
            'preorder': f.get('preorder') == 'SI', 'imagen': f.get('imagen') or '',
        })

    # DEDUP del proveedor (moloka_escaner_nube.py, "DEDUP del proveedor"): una fila por
    # (norm(core), es_chase), la MAS BARATA; la otra se lista, no se tira en silencio.
    uni = {}
    for f in filas:
        k = (M.norm(f['core']), bool(f['es_chase']))
        prev = uni.get(k)
        if prev is None:
            uni[k] = f
            continue
        if f['pa'] is not None and (prev['pa'] is None or f['pa'] < prev['pa']):
            barato, caro = f, prev
        else:
            barato, caro = prev, f
        uni[k] = barato
        apartados.append(_apartado({'productNumber': caro['producto_heo'], 'nombre': caro['nombre'],
                                    'marca': caro['marca']}, 'duplicado_proveedor',
                                   'Duplicado del proveedor: me quedo con %s (esta venía a %s)'
                                   % (barato['pa'], caro['pa']), ean=caro['ean_in'], precio=caro['pa']))
    filas = list(uni.values())

    # GUARDARRAIL caja-vs-suelta (mismo bloque del viejo): marca, no borra.
    sueltas = {}
    for f in filas:
        if not f['es_caja'] and f['pa']:
            k = M.norm(f['core'])
            if k not in sueltas or f['pa'] < sueltas[k]:
                sueltas[k] = f['pa']
    for f in filas:
        f['aviso_caja'] = None
        if f['es_caja'] and f['pa']:
            su = sueltas.get(M.norm(f['core']))
            if su:
                pa_ud = (f['pa'] / (f.get('uds_caja') or M.UNIDADES_CASE_TCG)
                         if perfil.get('precio_caja6') == 'caja' else f['pa'])
                f['aviso_caja'] = M.aviso_caja_incoherente(pa_ud, su)

    foto = []
    for f in filas:
        # Celda 8: solo se divide donde el proveedor da el precio de la CAJA COMPLETA.
        pa = f['pa']
        if f['es_caja'] and pa and perfil.get('precio_caja6') == 'caja':
            pa = pa / (f.get('uds_caja') or M.UNIDADES_CASE_TCG)
        variantes = sorted({M.norm(v) for v in M.variantes_ean(f['core'])} - {''})
        foto.append({
            'producto_heo': f['producto_heo'], 'ean_original': f['ean_in'], 'ean_core': f['core'],
            'variantes': variantes, 'codigos_keepa': codigos_para_keepa(f['core'], M),
            'nombre': f['nombre'], 'marca': f['marca'], 'categoria': f['categoria'],
            'precio_catalogo': f['pa'], 'precio_unidad': pa,
            'es_caja': f['es_caja'], 'uds_caja': (f['uds_caja'] if f['es_caja'] else None),
            'es_chase': f['es_chase'], 'en_oferta': f['en_oferta'], 'campana': f['campana'],
            'disponibilidad': f['disponibilidad'], 'fin_de_vida': f['fin_de_vida'],
            'preorder': f['preorder'], 'imagen': f['imagen'], 'aviso_caja': f['aviso_caja'],
        })

    for m in MOTIVOS_APARTADO:
        previas[m] = sum(1 for a in apartados if a['motivo'] == m)
    previas['sin_gtin'] = n_sin_gtin
    cuentas = {'n_crudo': n_crudo, 'n_declarado': n_declarado, 'n_foto': len(foto), 'previas': previas,
               'n_devueltos': len(filas_heo) + len(chase_todo)}
    cuentas.update(cuadre_previo(cuentas))
    return foto, apartados, cuentas


def cuadre_previo(cuentas):
    """🔴 El cuadre de ANTES de las puertas, desde el catalogo CRUDO: crudo = previas + foto.
    Un recuento que falta (None) NO es un cero: sin el no se puede afirmar que cuadra.
    Tambien se exige que lo que descargar_heo DEVOLVIO mas lo que tiro sin GTIN sea el crudo:
    es la prueba de que los dos numeros sacados de su log son los buenos."""
    previas = cuentas['previas']
    faltan = [p for p in PUERTAS_PREVIAS if previas.get(p) is None]
    if cuentas.get('n_crudo') is None:
        faltan.insert(0, 'crudo')
    if cuentas.get('n_declarado') is None:
        faltan.insert(0, 'total que declara HEO')
    if faltan:
        return {'n_previas': None, 'cuadra_previo': False,
                'motivo_previo': 'sin recuento de: ' + ', '.join(faltan)}
    n_previas = sum(previas[p] for p in PUERTAS_PREVIAS)
    # 🔴 El catalogo «tal como llega de HEO» es el que HEO DICE que tiene, no lo que se bajo:
    #    `_paginar` de descargar_heo se para EN SILENCIO si una pagina falla cinco veces, y sin
    #    esto el cuadre diria CUADRA sobre un catalogo recortado.
    if cuentas['n_crudo'] != cuentas['n_declarado']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'HEO dice que tiene %d productos y se bajaron %d: la descarga se cortó'
                                 % (cuentas['n_declarado'], cuentas['n_crudo'])}
    if cuentas['n_devueltos'] + previas['sin_gtin'] != cuentas['n_crudo']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'HEO dio %d productos y descargar_heo devolvió %d + %d sin GTIN'
                                 % (cuentas['n_crudo'], cuentas['n_devueltos'], previas['sin_gtin'])}
    if cuentas['n_crudo'] != n_previas + cuentas['n_foto']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'catálogo crudo %d ≠ puertas previas %d + foto %d'
                                 % (cuentas['n_crudo'], n_previas, cuentas['n_foto'])}
    return {'n_previas': n_previas, 'cuadra_previo': True, 'motivo_previo': None}


def codigos_para_keepa(core, M):
    """Lo que se pega en el Visualizador por esta fila: el EAN tal cual y, si el rescate de
    GTIN del escaner viejo (`variantes_ean`) reconstruye OTRO EAN distinto, tambien ese. Las
    variantes que solo cambian ceros a la izquierda no se repiten: Keepa y el lector del Pro
    comparan sin esos ceros."""
    codigos = [core]
    for v in sorted(M.variantes_ean(core)):
        if M.norm(v) and M.norm(v) != M.norm(core) and all(M.norm(v) != M.norm(c) for c in codigos):
            codigos.append(v)
    return codigos


def lista_para_keepa(foto):
    """Los codigos de toda la foto, sin repetir y en el orden de la foto: uno por linea."""
    return list(dict.fromkeys(c for f in foto for c in f['codigos_keepa']))


def partir_en_tandas(codigos, tanda):
    return [codigos[i:i + tanda] for i in range(0, len(codigos), tanda)] or [[]]


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · LOS CSV DEL VISUALIZADOR (paso 3 y 4)
# ═══════════════════════════════════════════════════════════════════════════════
_RE_AMAZON = re.compile(r'amazon\.(es|de|fr|it)(?![a-z.])', re.I)


def _limpio(v):
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()


def _leer_crudo(ruta):
    with open(ruta, encoding='utf-8-sig', newline='') as fh:
        filas = [r for r in csv.reader(fh) if any((c or '').strip() for c in r)]
    if not filas:
        raise CsvIlegible('el fichero está vacío')
    return [_limpio(h) for h in filas[0]], filas[1:]


def columnas_requeridas(pro, col_caidas):
    """Sin estas, el CSV no sirve para decidir nada: se rechaza con su nombre."""
    c = pro.CSV_COLS
    return [c['ean'], c['asin'], c['buybox'], c['nuevo'], c['fba'], c['compct'], col_caidas]


def examinar_csv(ruta, pro, col_pais, col_caidas):
    """Lee UN export del Visualizador y devuelve {'pais', 'filas', 'fuente_pais', 'caidas'}.

    🔑 EL PAIS LO DICE EL DATO, no se pregunta: la columna `Localización` (la que usa la
       Guarda 5 bis del procesador del escaparate) y, si no estuviera, el dominio de las URL
       de Amazon del propio fichero. Tiene que ser UNO en todo el fichero.
    `caidas` = {asin: caidas_30d o None}, leidas con el mismo `_num_csv` del Escaner Pro."""
    cab, filas = _leer_crudo(ruta)
    if not filas:
        raise CsvIlegible('sin filas de datos (solo cabecera)')
    idx = {}
    for i, h in enumerate(cab):
        idx.setdefault(h, i)
    faltan = [h for h in columnas_requeridas(pro, col_caidas) if h not in idx]
    if faltan:
        raise CsvIlegible('le faltan columnas del Visualizador: ' + ', '.join(repr(h) for h in faltan))

    def celda(fila, h):
        i = idx.get(h)
        return _limpio(fila[i]) if (i is not None and i < len(fila)) else ''

    if col_pais in idx:
        vistos = set()
        for n, fila in enumerate(filas, 2):
            v = celda(fila, col_pais).lower()
            if not v:
                raise CsvIlegible("fila %d: '%s' vacía; es la única fuente de país del fichero" % (n, col_pais))
            vistos.add(v)
        fuente = col_pais
    else:
        cols_url = [h for h in cab if 'url' in h.lower()]
        vistos = set()
        for fila in filas:
            doms = {m.group(1).lower() for h in cols_url for m in _RE_AMAZON.finditer(celda(fila, h))}
            vistos |= doms
        fuente = 'URL de Amazon'
        if not vistos:
            raise CsvIlegible("no trae '%s' ni URL de Amazon: no se puede saber de qué país es" % col_pais)
    if len(vistos) != 1:
        raise CsvIlegible('mezcla países (%s); cada export del Visualizador es de UN dominio'
                          % ', '.join(sorted(vistos)))
    pais = vistos.pop().upper()

    caidas, choques = {}, 0
    col_asin = pro.CSV_COLS['asin']
    for fila in filas:
        asin = celda(fila, col_asin)
        if not asin:
            continue
        v = pro._num_csv(celda(fila, col_caidas))
        if asin in caidas and caidas[asin] != v:
            choques += 1          # el mismo ASIN dos veces con caidas distintas: se queda la primera
            continue
        caidas.setdefault(asin, v)
    return {'pais': pais, 'filas': len(filas), 'fuente_pais': fuente, 'caidas': caidas,
            'choques_caidas': choques}


def candidatos(fila_foto, datos_pais):
    """Las fichas del CSV de UN pais para esta fila de la foto: todas las que casan con alguna de
    sus variantes (sin ceros a la izquierda, como el lector del Pro), sin repetir ASIN. Se
    conservan tambien las filas SIN ASIN: 'aparece sin ASIN' no es lo mismo que 'no aparece'."""
    salida, vistos = [], set()
    for v in fila_foto['variantes']:
        for rec in datos_pais.get(v, []):
            clave = rec.get('asin') or ('sin-asin', id(rec))
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(rec)
    return salida


def precio_de_venta(rec):
    """El precio de venta de una ficha del CSV, COMO EL ESCANER PRO (escanear_pro): la Caja de
    Compra si hay; si no, «Nuevo: Actual»; si no, ninguno. Devuelve (precio, canal)."""
    if rec.get('buybox') and rec['buybox'] > 0:
        return rec['buybox'], ('BB-FBA' if rec.get('es_fba') else 'BB-FBM')
    if rec.get('nuevo') and rec['nuevo'] > 0:
        return rec['nuevo'], 'SIN BB'
    return None, 'sin precio'


def calcular_pais(pais, rec, pa, core, M):
    """La rentabilidad de UNA ficha en UN pais, con `calc_rentabilidad` del viejo y el recargo
    ISD de ese pais (lo que hace hoy la Celda 8). Misma condicion para calcular: precio, PA,
    comision y tarifa FBA; si falta una, 'Sin datos' y ni un numero inventado."""
    precio, canal = precio_de_venta(rec)
    iva = M.iva_por_pais(core)[pais]
    isd = M.ISD_PAIS[pais]
    out = {'pais': pais, 'asin': rec.get('asin'), 'titulo': rec.get('titulo') or '',
           'rank': rec.get('rank'), 'rank_90d': rec.get('rank90'),
           'precio_venta': precio, 'canal': canal, 'ref_pct': rec.get('compct'),
           'fee_fba': rec.get('fba'), 'iva': iva, 'iva_origen': M.origen_iva_fila(pais, iva, core),
           'almacen': M.ALMACEN, 'com_digitales': M.COM_DIGITALES,
           'isd_pct': isd['pct'], 'isd_incluye_fba': bool(isd['incluye_fba']), 'pa': pa}
    if precio and pa and rec.get('compct') is not None and rec.get('fba') is not None:
        r = M.calc_rentabilidad(precio, pa, rec['compct'], rec['fba'], iva,
                                almacen=M.ALMACEN, com_digitales=M.COM_DIGITALES, isd=isd)
        out.update(com_amazon=r['com_amazon'], beneficio=r['beneficio'], roi=r['roi'],
                   margen=r['margen'], decision=M.decision_de(r['margen']))
    else:
        out.update(com_amazon=None, beneficio=None, roi=None, margen=None, decision='Sin datos')
    return out


def _pct(x):
    return ('%.1f %%' % (x * 100)).replace('.', ',') if x is not None else '—'


def decidir(fila_foto, cands_por_pais, caidas_por_pais, params, M):
    """La PUERTA de una fila de la foto. Devuelve {'puerta', 'motivo', 'detalle', 'asin',
    'fichas', 'paises': {pais: calculo}, 'caidas': {pais: n o None}, 'mejor': {...} o None}.

    `cands_por_pais`: {pais: [fichas del CSV]}, los paises que se CALCULAN de los que se ha
    subido CSV. `params` (escaner2_parametros, Fernando 24-sep-2026), DOS listas distintas:
      · 'paises_filtro'  (ES, DE): donde se mira si SE VENDE (> `umbral` caidas en 30 dias en
        alguno de ellos);
      · 'paises_calculo' (ES, IT, FR, DE): donde se CALCULA la rentabilidad, si traen CSV. El
        mejor pais sale de TODOS los calculados, venda o no alli: cada pais lleva `vende_aqui`
        y la pantalla marca «no vende aquí», pero se ve (decide Fernando).

    Orden de las puertas (una y solo una):
      a · ninguna ficha con ASIN en ningun CSV;
      b · dos o mas ASIN distintos para el mismo EAN (no se calcula: se listan);
      c · no se vende: ningun pais del FILTRO con MAS de `umbral` caidas en 30 dias;
      d/e/f · se vende: COMPRAR si algun pais da COMPRAR, VALORAR si alguno da VALORAR, y si
              ninguno, sin margen. El mejor pais es el de mas margen dentro de esa decision."""
    umbral = params['umbral']
    filtro = list(params['paises_filtro'])
    # Los que se calculan, en el orden de los parametros; solo los que traen CSV.
    paises = [p for p in params['paises_calculo'] if p in cands_por_pais]
    todas = [(p, r) for p in cands_por_pais for r in cands_por_pais[p]]
    asins = list(dict.fromkeys(r['asin'] for _p, r in todas if r.get('asin')))
    base = {'asin': None, 'fichas': None, 'paises': {}, 'caidas': {}, 'mejor': None}

    if not asins:
        if not todas:
            return dict(base, puerta='a', motivo='a_no_aparece', detalle='No aparece en ningún CSV')
        return dict(base, puerta='a', motivo='a_sin_asin', detalle='Aparece en el CSV pero sin ASIN')

    if len(asins) >= 2:
        fichas = []
        for p, r in todas:
            if not r.get('asin'):
                continue
            precio, canal = precio_de_venta(r)
            fichas.append({'pais': p, 'asin': r['asin'], 'titulo': r.get('titulo') or '',
                           'rank': r.get('rank'), 'rank_90d': r.get('rank90'),
                           'caidas_30d': caidas_por_pais.get(p, {}).get(r['asin']),
                           'precio_venta': precio, 'canal': canal})
        return dict(base, puerta='b', motivo='b_varias_fichas',
                    detalle='%d fichas para el mismo EAN: %s' % (len(asins), ', '.join(asins)),
                    fichas=fichas)

    asin = asins[0]
    calculos, caidas = {}, {}
    for p in paises:
        rec = next((r for r in cands_por_pais.get(p, []) if r.get('asin') == asin), None)
        caidas[p] = caidas_por_pais.get(p, {}).get(asin) if rec is not None else None
        if rec is not None:
            calculos[p] = calcular_pais(p, rec, fila_foto['precio_unidad'], fila_foto['ean_core'], M)
            calculos[p]['caidas_30d'] = caidas[p]
            # 🔑 La marca «no vende aquí»: se decide AQUI y se guarda; la pantalla no la recalcula.
            calculos[p]['vende_aqui'] = caidas[p] is not None and caidas[p] > umbral
    salida = dict(base, asin=asin, paises=calculos, caidas=caidas)

    se_vende = any(caidas.get(p) is not None and caidas[p] > umbral for p in filtro)
    if not se_vende:
        con_dato = [p for p in filtro if caidas.get(p) is not None]
        sin_dato = [p for p in filtro if caidas.get(p) is None]
        if not con_dato:
            return dict(salida, puerta='c', motivo='c_sin_dato',
                        detalle='Sin dato de caídas en ' + ' ni en '.join(filtro))
        det = '≤ %d caídas en %s' % (umbral, ' y en '.join(con_dato))
        if sin_dato:
            det += ' (%s: sin dato)' % ', '.join(sin_dato)
        return dict(salida, puerta='c', motivo='c_pocas_caidas', detalle=det)

    def mejor_de(decision):
        cand = [p for p in paises if p in calculos and calculos[p]['decision'] == decision]
        if not cand:
            return None
        # El de mas margen; a igualdad, el primero de los paises configurados.
        return max(cand, key=lambda p: (calculos[p]['margen'], -paises.index(p)))

    for decision, puerta, motivo in (('COMPRAR', 'f', 'f_comprar'), ('VALORAR', 'e', 'e_valorar')):
        p = mejor_de(decision)
        if p:
            c = calculos[p]
            mejor = {'pais': p, 'margen': c['margen'], 'beneficio': c['beneficio'],
                     'precio_venta': c['precio_venta']}
            return dict(salida, puerta=puerta, motivo=motivo, mejor=mejor,
                        detalle='%s en %s (margen %s)' % (decision, p, _pct(c['margen'])))
    con_margen = [p for p in paises if p in calculos and calculos[p]['margen'] is not None]
    if con_margen:
        return dict(salida, puerta='d', motivo='d_sin_margen',
                    detalle='Margen por debajo de VALORAR: ' + ' · '.join(
                        '%s %s' % (p, _pct(calculos[p]['margen'])) for p in con_margen))
    return dict(salida, puerta='d', motivo='d_sin_datos',
                detalle='Se vende pero el CSV no trae precio, comisión o tarifa FBA para calcular')


# ═══════════════════════════════════════════════════════════════════════════════
# 4 · EL CUADRE (paso 5): entradas = suma de puertas, y cada EAN por UNA sola
# ═══════════════════════════════════════════════════════════════════════════════
def cuadre(ids_foto, resultados):
    """Comprueba que cada fila de la foto sale por UNA y solo una puerta.

    `ids_foto`: los ids de las filas de la foto (las ENTRADAS). `resultados`: dicts con 'foto_id'
    y 'puerta'. Devuelve {'cuadra', 'n_entradas', 'conteo', 'suma', 'n_c_pocas', 'n_c_sin_dato',
    'faltan', 'sobran', 'repetidos', 'puerta_rara'}. `cuadra` solo es True si NO falta ninguna
    entrada, NO sobra ninguna salida, NINGUNA sale dos veces, todas las puertas son de las seis y
    la suma de las puertas es igual a las entradas."""
    ids = list(ids_foto)
    conteo = {p: 0 for p in PUERTAS}
    vistos, repetidos, rara = set(), [], []
    for r in resultados:
        if r['foto_id'] in vistos:
            repetidos.append(r['foto_id'])
        vistos.add(r['foto_id'])
        if r.get('puerta') in conteo:
            conteo[r['puerta']] += 1
        else:
            rara.append(r.get('puerta'))
    faltan = sorted(set(ids) - vistos)
    sobran = sorted(vistos - set(ids))
    suma = sum(conteo.values())
    return {'cuadra': (not faltan and not sobran and not repetidos and not rara
                       and suma == len(ids) and len(set(ids)) == len(ids)),
            'n_entradas': len(ids), 'conteo': conteo, 'suma': suma,
            'n_c_pocas': sum(1 for r in resultados if r.get('motivo') == 'c_pocas_caidas'),
            'n_c_sin_dato': sum(1 for r in resultados if r.get('motivo') == 'c_sin_dato'),
            'faltan': faltan, 'sobran': sobran, 'repetidos': repetidos, 'puerta_rara': rara}


# ═══════════════════════════════════════════════════════════════════════════════
# 5 · LA COMPARACION CON EL ESCANER VIEJO (paso 6)
# ═══════════════════════════════════════════════════════════════════════════════
_RE_NOMBRE_VIEJO = re.compile(r'Escaneo_HEO_[^/]*_(\d{8})_(\d{4})\.xlsx$')
POSITIVAS = ('COMPRAR', 'VALORAR')


def fecha_del_excel_viejo(ruta):
    """`resultados/Escaneo_HEO_TODAS_20260923_2006.xlsx` → 2026-09-23 20:06 UTC. El sello lo pone
    el escaner viejo con `datetime.now()` en el runner de GitHub, que va en UTC."""
    m = _RE_NOMBRE_VIEJO.search(ruta or '')
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M').replace(tzinfo=timezone.utc)


def leer_excel_viejo(contenido, M):
    """La hoja 'Análisis' de un Excel del escaner viejo → {ean_norm: {'ean', 'nombre',
    'decisiones': {pais: decision}}}. Por NOMBRE de columna, no por letra (el viejo avisa de que
    hay columnas que se han ido anadiendo al final)."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=False)
    if 'Análisis' not in wb.sheetnames:
        raise ValueError("el Excel no tiene la hoja 'Análisis' (tiene %s)" % wb.sheetnames)
    filas = wb['Análisis'].iter_rows(values_only=True)
    cab = [str(c or '').strip() for c in next(filas)]
    faltan = [c for c in ('EAN', 'País', 'Decisión') if c not in cab]
    if faltan:
        raise ValueError('a la hoja Análisis le faltan las columnas %s' % faltan)
    i_ean, i_pais, i_dec = cab.index('EAN'), cab.index('País'), cab.index('Decisión')
    i_nom = cab.index('Nombre') if 'Nombre' in cab else None
    salida = {}
    for fila in filas:
        if fila is None or i_ean >= len(fila) or fila[i_ean] in (None, ''):
            continue
        ean = str(fila[i_ean]).strip()
        k = M.norm(M.core_ean(ean))
        d = salida.setdefault(k, {'ean': ean, 'nombre': (fila[i_nom] if i_nom is not None else '') or '',
                                  'decisiones': {}})
        pais = str(fila[i_pais] or '').strip().upper()
        if pais:
            d['decisiones'][pais] = str(fila[i_dec] or '').strip()
    return salida


def fusionar_viejos(excels):
    """[(meta, datos)] con meta = {'fichero', 'fecha', 'modo'} → {ean_norm: {..., 'fichero',
    'fecha', 'modo'}}. Se recorren de MAS VIEJO a MAS NUEVO y el mas nuevo manda: es la ultima
    opinion del escaner viejo sobre cada EAN."""
    salida = {}
    for meta, datos in sorted(excels, key=lambda md: md[0]['fecha']):
        for k, d in datos.items():
            salida[k] = dict(d, fichero=meta['fichero'], fecha=meta['fecha'], modo=meta.get('modo'))
    return salida


def elegir_excels_viejos(filas_resultados):
    """De las filas de `escaner_resultados` de HEO con fichero (las mas nuevas primero) → las que
    hacen falta: el ULTIMO escaneo completo ('todo') y todas las pasadas de novedades
    ('nuevos') posteriores. Si no hay ninguno completo, todas las que haya (y se dice)."""
    filas = [f for f in filas_resultados if f.get('fichero')]
    for i, f in enumerate(filas):
        if (f.get('modo') or '').lower() == 'todo':
            return filas[:i + 1], True
    return filas, False


def _positiva(decisiones):
    """De {pais: decision} → (mejor, [paises con esa decision]) o (None, [])."""
    for d in POSITIVAS:
        ps = sorted(p for p, v in decisiones.items() if v == d)
        if ps:
            return d, ps
    return None, []


_ORDEN_PUERTA = {'f': 6, 'e': 5, 'd': 4, 'c': 3, 'b': 2, 'a': 1}


def comparar(viejo, nuevo, contexto, M):
    """Cruza la ultima opinion del viejo con la del nuevo, EAN a EAN.

    `viejo`: salida de fusionar_viejos. `nuevo`: {ean_norm: {'puerta', 'motivo', 'detalle',
    'mejor_pais', 'decision', 'ean', 'nombre', 'core', 'rank_es', 'rank90_es'}} (si un EAN tiene
    dos filas en la foto --unidad y caja-- manda la de puerta mas alta). `contexto`: {'umbral',
    'paises' (los calculados), 'paises_filtro', 'rank_max', 'apartados': {ean_norm: detalle},
    'fecha_nuevo'}.

    Solo entran los EAN que son COMPRAR o VALORAR en ALGUNO de los dos lados. Se rotula como
    DIFERENCIA DE CRITERIO lo que se explica por lo que el encargo nombra:
      · el viejo filtra por puesto ≤ rank_max en ES (actual o media de 90 dias) y el nuevo
        por caidas de 30 dias en ES o DE;
      · el viejo calcula ES/IT/FR/DE y el nuevo solo los paises configurados.
    Todo lo demas queda como SIN EXPLICAR, con una nota de lo que dice cada lado."""
    # `paises_filtro`: donde el nuevo mira si se vende; `paises`: los que el nuevo CALCULO (con CSV).
    umbral, paises, rank_max = contexto['umbral'], list(contexto['paises']), contexto['rank_max']
    filtro = list(contexto.get('paises_filtro') or paises)
    filas = []
    for k in sorted(set(viejo) | set(nuevo)):
        v, n = viejo.get(k), nuevo.get(k)
        dec_v, paises_v = _positiva(v['decisiones']) if v else (None, [])
        dec_n = n['decision'] if (n and n['puerta'] in ('e', 'f')) else None
        if not dec_v and not dec_n:
            continue
        if dec_v and dec_n:
            categoria = 'ambos'
        elif dec_v:
            categoria = 'solo_viejo'
        else:
            categoria = 'solo_nuevo'

        criterio, notas = [], []
        if categoria == 'solo_viejo':
            if n is None:
                # No es criterio: es que HOY no esta en el catalogo filtrado (o se aparto antes).
                notas.append(contexto['apartados'].get(k) or 'no está en el catálogo filtrado de esta pasada')
            elif n['puerta'] in ('a', 'b'):
                # El nuevo ni siquiera llego a calcularlo: eso hay que mirarlo, no explicarlo.
                notas.append('nuevo: puerta %s · %s' % (n['puerta'], n['detalle']))
            else:
                # c o d: el nuevo lo evaluo y dijo que no. Solo aqui caben los dos criterios.
                if paises_v and not [p for p in paises_v if p in paises]:
                    criterio.append('el viejo solo lo da en %s y el nuevo calcula %s'
                                    % (', '.join(paises_v), ' y '.join(paises)))
                # 🔑 Solo «pocas caidas» es criterio: «sin dato de caidas» es un HUECO de dato
                #    (el CSV no las trae), y un hueco se mira, no se explica.
                if n['motivo'] == 'c_pocas_caidas':
                    criterio.append('el nuevo pide más de %d caídas en 30 días en %s (%s); el viejo '
                                    'filtra por puesto ≤ %s en ES' % (umbral, ' o '.join(filtro), n['detalle'],
                                                                     '{:,}'.format(rank_max).replace(',', '.')))
                if not criterio:
                    notas.append('nuevo: puerta %s · %s' % (n['puerta'], n['detalle']))
        elif categoria == 'solo_nuevo':
            if v is not None:
                notas.append('el viejo lo evaluó: ' + ', '.join('%s %s' % (p, d) for p, d in sorted(v['decisiones'].items())))
            else:
                r, r90 = n.get('rank_es'), n.get('rank90_es')
                pasa = any(x and x > 0 and x <= rank_max for x in (r, r90))
                if not pasa and not n.get('propio'):
                    criterio.append('el viejo solo mira puesto ≤ %s en ES (actual o media de 90 días) y '
                                    'este tiene %s / %s' % ('{:,}'.format(rank_max).replace(',', '.'),
                                                            _num_o_raya(r), _num_o_raya(r90)))
                else:
                    notas.append('no está en los Excel del viejo')
        filas.append({
            'ean_norm': k,
            'ean': (n or {}).get('ean') or (v or {}).get('ean'),
            'nombre': (n or {}).get('nombre') or (v or {}).get('nombre') or '',
            'categoria': categoria,
            'decision_viejo': dec_v, 'pais_viejo': ', '.join(paises_v) or None,
            'fecha_viejo': v['fecha'] if v else None, 'excel_viejo': v['fichero'] if v else None,
            'puerta_nuevo': n['puerta'] if n else None, 'motivo_nuevo': n['motivo'] if n else None,
            'decision_nuevo': dec_n, 'pais_nuevo': n.get('mejor_pais') if n else None,
            'fecha_nuevo': contexto.get('fecha_nuevo'),
            'diferencia_criterio': bool(criterio) and categoria != 'ambos',
            'explicacion': (('Diferencia de criterio: ' + '; '.join(criterio)) if criterio
                            else ('Sin explicar: ' + '; '.join(notas)) if notas and categoria != 'ambos'
                            else None),
        })
    return filas


def _num_o_raya(x):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) or x <= 0 else '{:,}'.format(int(x)).replace(',', '.')


def resumen_comparacion(filas):
    solo = [f for f in filas if f['categoria'] != 'ambos']
    return {'n_cmp_ambos': sum(1 for f in filas if f['categoria'] == 'ambos'),
            'n_cmp_solo_viejo': sum(1 for f in filas if f['categoria'] == 'solo_viejo'),
            'n_cmp_solo_nuevo': sum(1 for f in filas if f['categoria'] == 'solo_nuevo'),
            'n_cmp_criterio': sum(1 for f in solo if f['diferencia_criterio']),
            'n_cmp_sin_explicar': sum(1 for f in solo if not f['diferencia_criterio'])}


def nuevo_por_ean(foto, resultados_por_foto, M):
    """{ean_norm: lo que el nuevo dice de ese EAN}, para `comparar`. Si un EAN vive en dos filas
    de la foto (unidad y caja), manda la de puerta mas alta."""
    salida = {}
    for f in foto:
        r = resultados_por_foto[f['id']]
        k = M.norm(f['ean_core'])
        es = (r.get('paises') or {}).get('ES') or {}
        cand = {'puerta': r['puerta'], 'motivo': r['motivo'], 'detalle': r['detalle'],
                'mejor_pais': (r.get('mejor') or {}).get('pais'),
                'decision': {'f': 'COMPRAR', 'e': 'VALORAR'}.get(r['puerta']),
                'ean': f['ean_original'], 'nombre': f['nombre'], 'core': f['ean_core'],
                'rank_es': es.get('rank'), 'rank90_es': es.get('rank_90d'),
                'propio': M.es_propio(f['ean_core'])}
        prev = salida.get(k)
        if prev is None or _ORDEN_PUERTA[cand['puerta']] > _ORDEN_PUERTA[prev['puerta']]:
            salida[k] = cand
    return salida
