# -*- coding: utf-8 -*-
"""ESCANER 2 · LA FOTO DE DISPONIBILIDAD DE HEO: todo lo que HEO devuelve con codigo de barras, producto a
producto (encargo E, tramo 3, pieza 1, 29-sep-2026). MODULO PURO: filas dentro, filas fuera. Ni red, ni
base, ni reloj.

🔑 QUE ES Y POR QUE NO ES LA FOTO DEL BARRIDO. Fernando, 29-sep-2026: «Para saber que hay para
   reponer hay que tener el catalogo completo de lo disponible en HEO y otra cosa es que decidamos
   escanear novedades de Funko». La foto del barrido (`escaner2_motor.construir_foto`) se queda solo
   con lo disponible que pasa un filtro de marcas, porque es lo que se lleva al Visualizador. Esta
   se queda con TODO lo que devuelve la descarga, de todas las marcas y disponible o NO, para
   distinguir «en catalogo, agotado» de «no esta en el catalogo»: una fila por producto de HEO
   (`productNumber`, su llave), con la marca `disponible`.
   🔴 CON UN MATIZ (revision de Cowork, 29-sep-2026): la descarga heredada quita los productos SIN
   codigo de barras (GTIN) antes de devolverlos (~1.155 de ~23.500). Esos solo se CUENTAN
   (`n_sin_gtin`): sin codigo de barras no casan con nuestro catalogo ni se venden en Amazon. No es
   «el catalogo entero»: es todo lo que tiene GTIN.

🔴 LAS REGLAS SON LAS DEL ESCANER 2, NO UNAS NUEVAS. Cada fila sale con las MISMAS piezas que la foto
   del barrido, sin copiarlas: `core_de_heo` (el EAN con el que se cruza), `clasificar_chase` del viejo
   (caja por sufijo del EAN; chase suelto), `partir_ean` (unidades de la caja), la regla de la Celda 8
   (precio de la caja entre sus unidades) y, para las cajas con chase que descargar_heo desvia,
   `unidades_caja_chase` + `ean_de_la_figura` + `_fila_de_chase`. `test_escaner2_disponibilidad.py`
   comprueba que, en lo disponible, sale lo MISMO que en la foto del barrido.
   Lo que el barrido APARTA (chase suelto, EAN de forma rara, caja con chase sin EAN de la figura)
   aqui NO se tira: se guarda con su `regla`, porque tambien es catalogo de HEO. Quien lea
   (novedades, reposicion) decide que hacer con ello. El estado no servible no existe aqui: HEO solo
   da 'disponible' o 'agotado', y eso es justo lo que se guarda.

🔴 LA TRAMPA DEL PRECIO DE CAJA: van `precio_catalogo` (el de la caja entera) y `precio_unidad` (el de
   la caja entre sus unidades) SEPARADOS, con `uds_caja`. Quien lea no divide nada.
"""
import escaner2_motor as e2

# Las reglas del escaner 2 que apartan un producto de las novedades y de la reposicion. Los mismos
# valores que admite el check de disp_lectura.regla (migracion 20260929070300 de la v2).
REGLAS = ('chase_suelto', 'ean_forma_rara', 'caja_chase_sin_figura')


class LecturaInvalida(ValueError):
    """Lo leido no se puede subir tal cual (un producto sin numero, dos veces el mismo…)."""


def _texto(v):
    v = '' if v is None else str(v).strip()
    return v or None


def _fila(producto, disponible, ean_in, core, nombre, marca, categoria, pa, es_caja, uds, es_chase,
          en_oferta, preorder, fin_de_vida, disponibilidad, regla, aviso, M):
    """Una fila de disp_lectura. El precio por unidad, con la regla de la Celda 8 del escaner 2: solo se
    divide donde el proveedor da el precio de la CAJA COMPLETA (HEO: si)."""
    perfil = M.PERFILES[e2.PROVEEDOR]
    precio_unidad = pa
    if es_caja and pa and perfil.get('precio_caja6') == 'caja':
        precio_unidad = pa / (uds or M.UNIDADES_CASE_TCG)
    return {
        'producto_prov': producto,
        'ean_original': _texto(ean_in),
        'ean_core': core,
        'marca': _texto(marca),
        'nombre': _texto(nombre),
        'categoria': _texto(categoria),
        'es_caja': bool(es_caja),
        'uds_caja': uds if es_caja else None,
        'es_chase': bool(es_chase),
        'precio_catalogo': pa,
        'precio_unidad': precio_unidad,
        'disponible': bool(disponible),
        'disponibilidad': _texto(disponibilidad),
        'en_oferta': en_oferta,
        'preorder': preorder,
        'fin_de_vida': fin_de_vida,
        'regla': regla,
        'aviso': _texto(aviso),
    }


def _core_valido(core):
    return core if (core.isdigit() and len(core) in (12, 13)) else None


def construir_disponibilidad(filas_heo, chase_heo, M):
    """Del catalogo de HEO (lo que devuelve `descargar_catalogo_heo(con_chase=True)`) a las filas de
    disp_lectura: UNA por producto, disponible o no, sin filtro de marca.

    Devuelve (filas, cuentas) con cuentas = {n_leidas, n_disponibles, n_agotados, n_devueltos,
    por_regla}. Lanza LecturaInvalida si un producto no trae numero o sale dos veces: la llave es el
    numero de HEO, y una lectura con la llave rota no se sube."""
    perfil = M.PERFILES[e2.PROVEEDOR]
    filas = []

    # Las que descargar_heo desvia por sonar a chase: con unidades en el nombre, CAJA con chase (con el
    # EAN de su figura comun); sin ellas, figura suelta por el flujo normal. Como en construir_foto.
    normales = list(filas_heo or [])
    cajas = []
    chase_todo = list(chase_heo or [])
    for c in chase_todo:
        uds = e2.unidades_caja_chase(c.get('nombre'))
        if uds is None:
            normales.append(e2._fila_de_chase(c))
        else:
            cajas.append((c, e2._fila_de_chase(c), uds))

    for c, f, uds in cajas:
        ean, _origen, aviso = e2.ean_de_la_figura(c.get('ean_caja'), c.get('producto_heo'), M)
        filas.append(_fila(
            producto=_texto(c.get('producto_heo')), disponible=f.get('estado') == 'disponible',
            ean_in=f['ean'], core=ean, nombre=f['nombre'], marca=f['marca'], categoria=None,
            pa=M._num(f['precio']), es_caja=True, uds=uds, es_chase=True,
            en_oferta=False, preorder=False, fin_de_vida=False, disponibilidad=None,
            regla=None if ean is not None else 'caja_chase_sin_figura',
            aviso=aviso, M=M))

    for f in normales:
        ean_in = str(f.get(perfil['col_ean']) or '').strip()
        nombre = f.get(perfil['col_nombre']) or ''
        es_case, es_caja6, descartar = M.clasificar_chase(nombre, ean_in)
        core = _core_valido(e2.core_de_heo(ean_in, M))
        regla = 'chase_suelto' if descartar else ('ean_forma_rara' if core is None else None)
        uds = (M.partir_ean(ean_in)[2] or M.UNIDADES_CASE_TCG) if es_caja6 else None
        filas.append(_fila(
            producto=_texto(f.get('productNumber')), disponible=f.get(perfil['col_estado']) == 'disponible',
            ean_in=ean_in, core=core, nombre=nombre, marca=f.get(perfil['col_marca']) or '',
            categoria=f.get('categoria') or '', pa=M._num(f.get(perfil['col_pa'], '')),
            es_caja=bool(es_caja6), uds=uds, es_chase=bool(es_case),
            en_oferta=f.get('en_oferta') == 'SI', preorder=f.get('preorder') == 'SI',
            fin_de_vida=f.get('fin_de_vida') == 'SI', disponibilidad=f.get('disponibilidad') or '',
            regla=regla, aviso=None, M=M))

    sin_numero = [f for f in filas if not f['producto_prov']]
    if sin_numero:
        raise LecturaInvalida('%d producto(s) sin número de HEO: la llave de la foto es ese número' % len(sin_numero))
    vistos, repetidos = set(), set()
    for f in filas:
        if f['producto_prov'] in vistos:
            repetidos.add(f['producto_prov'])
        vistos.add(f['producto_prov'])
    if repetidos:
        raise LecturaInvalida('número(s) de HEO repetidos en la lectura: %s' % ', '.join(sorted(repetidos)[:10]))

    n_disp = sum(1 for f in filas if f['disponible'])
    cuentas = {
        'n_leidas': len(filas),
        'n_disponibles': n_disp,
        'n_agotados': len(filas) - n_disp,
        'n_devueltos': len(filas_heo or []) + len(chase_todo),
        'por_regla': {r: sum(1 for f in filas if f['regla'] == r) for r in REGLAS},
    }
    if cuentas['n_leidas'] != cuentas['n_devueltos']:
        raise LecturaInvalida('descargar_heo devolvió %d productos y salen %d filas'
                              % (cuentas['n_devueltos'], cuentas['n_leidas']))
    return filas, cuentas


def recuentos_del_log(texto):
    """Los numeros que `descargar_catalogo_heo` solo dice en su log (y NO se toca), con los mismos nombres
    que las columnas de disp_pasada. Un numero que no aparece es None, no cero.

      · lo que HEO DECLARA de cada endpoint (`totalElements`, impreso en su primera pagina):
        productos, precios y disponibilidades;
      · lo que LLEGO de cada uno («Cruzando: P productos | Q precios | R disponibilidades»);
      · lo que tiro por no traer GTIN."""
    import re
    def uno(patron):
        m = re.search(patron, texto or '')
        return int(m.group(1)) if m else None
    cruce = re.search(r'Cruzando: (\d+) productos \| (\d+) precios \| (\d+) disponibilidades', texto or '')
    return {
        'n_declarado': uno(r'catalog/products: (\d+) items'),
        'n_crudo': int(cruce.group(1)) if cruce else None,
        'n_declarado_precios': uno(r'catalog/prices: (\d+) items'),
        'n_precios': int(cruce.group(2)) if cruce else None,
        'n_declarado_disponibilidades': uno(r'catalog/availabilities: (\d+) items'),
        'n_disponibilidades': int(cruce.group(3)) if cruce else None,
        'n_sin_gtin': uno(r'descartadas (\d+) sin GTIN'),
    }


# Cada endpoint, con el nombre de su recuento declarado y del que llego.
ENDPOINTS = (('productos', 'n_declarado', 'n_crudo'),
             ('precios', 'n_declarado_precios', 'n_precios'),
             ('disponibilidades', 'n_declarado_disponibilidades', 'n_disponibilidades'))


def descarga_cortada(rec):
    """🔴 Lo que falta para dar la descarga por ENTERA, o [] si esta entera.

    La descarga heredada (`_paginar`) deja de pedir paginas SIN ERROR si una no llega, y un producto
    sin su fila de disponibilidad sale AGOTADO (`dispo.get(pn) or {}`). Con las disponibilidades
    cortadas, la foto diria «agotado» a cientos de productos que no lo estan, con el crudo de
    productos intacto: por eso se exige que LOS TRES endpoints lleguen enteros. Medido en 3 runs del
    barrido (25 y 28-sep-2026): hoy llegan enteros (precios y disponibilidades 22.926–23.049, igual
    a su totalElements)."""
    faltan = []
    for nombre, declarado, llego in ENDPOINTS:
        if rec.get(declarado) is None or rec.get(llego) is None:
            faltan.append('%s: sin recuento en el log (declarado %s, llegados %s)' % (nombre, rec.get(declarado), rec.get(llego)))
        elif rec[declarado] != rec[llego]:
            faltan.append('%s: HEO declara %s y llegaron %s' % (nombre, rec[declarado], rec[llego]))
    if rec.get('n_sin_gtin') is None:
        faltan.append('sin GTIN: sin recuento en el log')
    return faltan
