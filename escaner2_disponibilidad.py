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

🔴 SIN DATO NO ES AGOTADO (Fernando, 29-sep-2026, tras las primeras pasadas reales). El catalogo de HEO
   cambia mientras se pagina (~4 min), y un producto puede llegar en `products` y NO en
   `availabilities` (o no en `prices`). La descarga heredada le pone entonces «agotado» y sin precio
   (`dispo.get(pn) or {}`), y desde la fila NO se distingue de un agotado de verdad (medido en la 1.ª
   pasada: de 92 filas sin `disponibilidad`, 81 son cajas con chase —que nunca la llevan— y 11 son
   productos sin precio ni disponibilidad). Por eso el programa se queda con la LISTA CRUDA de cada
   endpoint al paso (envolviendo `_paginar` en tiempo de ejecucion; la heredada no se toca) y aqui
   cada fila sale marcada: `sin_dato_disponibilidad` y `sin_dato_precio`. La base conserva lo de
   antes para lo que ya estaba (migracion 20260929093000 de la v2).

🔴 REPETIDOS EN LA DESCARGA (remates, 29-sep-2026). HEO repite filas mientras se pagina (run
   36548469929: 23.454 productos con 23.453 declarados). Un producto repetido se queda UNA vez si
   todas sus copias son IDENTICAS en lo que se sube a disp_lectura, y se cuenta (`n_duplicados`); si
   alguna difiere (o una copia trae codigo de barras y otra no), la lectura NO se sube
   (LecturaInvalida). Igual en precios y disponibilidades (`n_duplicados_precios`,
   `n_duplicados_disponibilidades`), comparando el registro entero: todo lo que trae se usa. Cuadre:
   crudo = sin GTIN + leidas + repetidos, y la tolerancia se mide sobre los distintos.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import escaner2_motor as e2

# Las reglas del escaner 2 que apartan un producto de las novedades y de la reposicion. Los mismos
# valores que admite el check de disp_lectura.regla (migracion 20260929070300 de la v2).
REGLAS = ('chase_suelto', 'ean_forma_rara', 'caja_chase_sin_figura')


# 🔴 EL EXPOSITOR ES UNA CAJA (encargo T, 30-sep-2026; PENDIENTE DEL VISTO BUENO DE FERNANDO por su efecto en
#    Reponer). HEO da el precio del expositor ENTERO y dice cuantas unidades lleva al final del nombre:
#    «SpongeBob … Mystery Minis … Expositor 25th Anniversary (12)», «… Blind Box Display (6)», «… Surtido (24)».
#    `clasificar_chase` (heredada) solo reconoce la caja por el sufijo del EAN (C6, C12…) o por «5+1», asi que el
#    expositor salia SUELTO con el precio de las 12 como precio por unidad, y la cuenta de novedades lo comparaba con
#    una ficha de Amazon de UNA unidad (FK76102). Regla: el nombre dice expositor / display / surtido / assortment y
#    TERMINA en «(N)» con N >= 2 → caja de N. Sin esa palabra, «(N)» NO basta: «Pack de Dados (7)», «Sleeves (100)» o
#    «Set de 4 Pósteres (4)» son UNA cosa que se vende entera.
#    Solo en esta foto: la del barrido (Escaneo PRO) conserva la regla heredada, y el banco dice donde difieren.
_RE_EXPOSITOR = re.compile(r'\b(?:expositora?|exspositor|display|surtido|assortment|asst\.?)(?:\b|\s).*\(\s*(\d+)\s*\)\s*$',
                           re.I)


def unidades_expositor(nombre):
    """Las unidades de un expositor de HEO segun su nombre (N de «… Expositor … (N)», N >= 2), o None. Puro."""
    m = _RE_EXPOSITOR.search(str(nombre or ''))
    n = int(m.group(1)) if m else 0
    return n if n >= 2 else None


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


def construir_disponibilidad(filas_heo, chase_heo, M, *, con_precio, con_disponibilidad, numeros_crudos):
    """Del catalogo de HEO (lo que devuelve `descargar_catalogo_heo(con_chase=True)`) a las filas de
    disp_lectura: UNA por producto, disponible o no, sin filtro de marca.

    `con_precio` y `con_disponibilidad` son los numeros de HEO que SI llegaron en `prices` y en
    `availabilities` (`listas_de_los_crudos`). Obligatorios: sin ellos no se distingue «sin dato» de
    «agotado». Cada fila sale con `sin_dato_disponibilidad` / `sin_dato_precio`.

    `numeros_crudos` son los numeros de HEO del listado CRUDO de products, con sus repeticiones (lo que
    devolvio `_paginar`). Obligatorio: con el se cuentan los repetidos y se sabe cuantas copias de cada
    producto hay que ver.

    Devuelve (filas, cuentas) con cuentas = {n_leidas, n_disponibles, n_agotados, n_devueltos,
    n_duplicados_filas, n_duplicados_sin_gtin, n_sin_dato_disponibilidad, n_sin_dato_precio,
    por_regla}. Las filas salen UNA por producto. Lanza LecturaInvalida si un producto no trae numero,
    o si sale repetido con copias DISTINTAS (en lo que se sube, o una con codigo de barras y otra sin
    el): la llave es el numero de HEO, y una lectura con la llave dudosa no se sube."""
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
        # 🔴 Encargo T: el expositor (lo que la regla heredada no ve como caja), caja de N.
        if not es_caja6 and not descartar and unidades_expositor(nombre):
            es_caja6, uds = True, unidades_expositor(nombre)
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
    n_devueltos = len(filas_heo or []) + len(chase_todo)
    if len(filas) != n_devueltos:
        raise LecturaInvalida('descargar_heo devolvió %d productos y salen %d filas' % (n_devueltos, len(filas)))

    # 🔑 Los repetidos: cada producto, tantas filas como copias trae el listado crudo; si son identicas
    #    se queda una, y si no, no se sube nada. Lo que no tiene fila (sin GTIN) solo se cuenta.
    copias = {}
    for pn in numeros_crudos:
        copias[_texto(pn)] = copias.get(_texto(pn), 0) + 1
    por_numero = {}
    for f in filas:
        por_numero.setdefault(f['producto_prov'], []).append(f)
    distintos = sorted(pn for pn, fs in por_numero.items() if any(x != fs[0] for x in fs[1:]))
    if distintos:
        raise LecturaInvalida('número(s) de HEO repetidos con datos distintos: %s' % ', '.join(distintos[:10]))
    mezclados = sorted(pn for pn, fs in por_numero.items() if copias.get(pn, 0) != len(fs))
    if mezclados:
        raise LecturaInvalida('número(s) de HEO con copias que no son iguales en el listado (una con código de barras y otra '
                              'sin él, o que no está en el listado crudo): %s' % ', '.join(mezclados[:10]))
    n_duplicados_filas = sum(len(fs) - 1 for fs in por_numero.values())
    n_duplicados_sin_gtin = sum(n - 1 for pn, n in copias.items() if pn not in por_numero)
    filas = [fs[0] for fs in por_numero.values()]

    # 🔑 Sin dato no es agotado: la marca sale de las listas crudas, por el numero de HEO (tambien las
    #    cajas con chase, que la descarga cruza con la MISMA lista de disponibilidades).
    for f in filas:
        f['sin_dato_disponibilidad'] = f['producto_prov'] not in con_disponibilidad
        f['sin_dato_precio'] = f['producto_prov'] not in con_precio

    n_disp = sum(1 for f in filas if f['disponible'])
    cuentas = {
        'n_leidas': len(filas),
        'n_disponibles': n_disp,
        'n_agotados': len(filas) - n_disp,
        'n_devueltos': n_devueltos,
        'n_duplicados_filas': n_duplicados_filas,
        'n_duplicados_sin_gtin': n_duplicados_sin_gtin,
        'n_sin_dato_disponibilidad': sum(1 for f in filas if f['sin_dato_disponibilidad']),
        'n_sin_dato_precio': sum(1 for f in filas if f['sin_dato_precio']),
        'por_regla': {r: sum(1 for f in filas if f['regla'] == r) for r in REGLAS},
    }
    if cuentas['n_leidas'] + n_duplicados_filas != n_devueltos:
        raise LecturaInvalida('descargar_heo devolvió %d productos y salen %d filas más %d repetidas'
                              % (n_devueltos, cuentas['n_leidas'], n_duplicados_filas))
    return filas, cuentas


# 🆕 LOS TRAMOS DE HEO, EN SOMBRA (encargo H1, 8-oct-2026). Fernando, 8-oct: «siempre hay que calcular con el tramo mas
#    barato». HEO los da en `/catalog/products` → `prices.scaledDiscounts[]` = {quantity, discount: {amount}}, con
#    `amount` en % (medido en el encargo T: los 1.784 con tramo, todos <= 100; el caso UGD020019, 10 % desde 10 uds,
#    da el pvd al centimo). El programa ya baja ese listado (la lista cruda de `_paginar`): no hay peticion nueva ni se
#    toca la heredada. Se rellenan las tres columnas de OC2 (`precio_escalon`, `uds_escalon`, `precio_pa`) como en
#    OcioStock, pero NADIE las lee para HEO todavia: v_escaner_fuente solo usa `precio_pa` en OCIOSTOCK y
#    nov_parametros de HEO dice `precio_unidad`. Esto es solo guardar.
def _decimal(v):
    try:
        d = Decimal(str(v).replace(',', '.').strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def _tramos_de(producto):
    """(validos, raros) de un producto del listado crudo de products: validos = [(uds, pct)] con 0 < pct < 100 y uds
    entero >= 1; raros = cuantos traia que no lo son (se ignoran y se cuentan: un tramo raro no tumba la pasada de
    disponibilidad, que es la que dice que hay en HEO)."""
    lista = ((producto or {}).get('prices') or {}).get('scaledDiscounts') or []
    validos, raros = [], 0
    for t in lista if isinstance(lista, list) else [None]:
        t = t if isinstance(t, dict) else {}
        pct = _decimal((t.get('discount') or {}).get('amount') if isinstance(t.get('discount'), dict) else None)
        q = t.get('quantity')
        if pct is None or not (0 < pct < 100) or isinstance(q, bool) or not isinstance(q, int) or q < 1:
            raros += 1
        else:
            validos.append((q, pct))
    return validos, raros


def poner_escalones(filas, productos_crudos, precios_crudos, M):
    """Rellena en cada fila de disp_lectura `precio_escalon`, `uds_escalon` y `precio_pa` con el tramo MAS BARATO de
    HEO, y devuelve sus cuentas {n_con_tramo, n_escalon_gana, n_tramos_raros, n_tramos_dudosos, n_sin_precio}.
    Modifica `filas` (solo esas tres claves).

    La regla (encargo H1):
      · `precio_escalon` = el MENOR entre el precio de hoy (`precio_unidad`: el descontado, como siempre) y el precio
        BASE (`basePricePerUnit` de /catalog/prices, el mismo registro del que sale el de hoy) × (1 − el MAYOR % de sus
        tramos), redondeado al centimo. 🔴 SIN ACUMULAR: el % va sobre la base, nunca sobre el ya rebajado (no se sabe
        si HEO lo acumula); con descuento propio y tramo, gana el menor de los dos;
      · `uds_escalon` = las unidades del tramo que gana (a igual %, el de menos unidades), o 1 si gana el de hoy (a
        igual precio, el de hoy); en una caja son las unidades que pide HEO, es decir, CAJAS;
      · `precio_pa` = `precio_escalon` (en HEO no consta descuento por transferencia);
      · en las cajas, POR UNIDAD como `precio_unidad`: el tramo se calcula sobre el precio de la caja y se divide entre
        las MISMAS unidades;
      · sin precio de hoy, las tres vacias (la regla de la base: las tres llenas o las tres vacias).
    🔴 Un producto que el listado trae repetido con TRAMOS DISTINTOS no sabe cual es su tramo: sus tres columnas se
    quedan VACIAS y se cuenta (`n_tramos_dudosos`). No se tumba la pasada: esto va en sombra y la pasada es la que dice
    que hay en HEO; lo que se sube y se aplica es exactamente lo de antes."""
    perfil = M.PERFILES[e2.PROVEEDOR]
    tramos, raros_por, dudosos = {}, {}, set()
    for x in productos_crudos or []:
        pn = _texto(x.get('productNumber'))
        t = _tramos_de(x)
        if pn in tramos and tramos[pn] != t[0]:
            dudosos.add(pn)
        tramos.setdefault(pn, t[0])
        raros_por.setdefault(pn, t[1])
    bases = {_texto(p.get('productNumber')): _decimal((p.get('basePricePerUnit') or {}).get('amount')
                                                      if isinstance(p.get('basePricePerUnit'), dict) else None)
             for p in precios_crudos or []}
    c = {'n_con_tramo': 0, 'n_escalon_gana': 0, 'n_tramos_raros': 0, 'n_tramos_dudosos': 0, 'n_sin_precio': 0}
    for f in filas:
        pn = f['producto_prov']
        validos = tramos.get(pn) or []
        c['n_tramos_raros'] += raros_por.get(pn) or 0
        c['n_con_tramo'] += bool(validos)
        if f.get('precio_unidad') is None or f.get('precio_catalogo') is None or pn in dudosos:
            f.update(precio_escalon=None, uds_escalon=None, precio_pa=None)
            c['n_tramos_dudosos' if pn in dudosos else 'n_sin_precio'] += 1
            continue
        escalon, uds = f['precio_unidad'], 1
        base = bases.get(pn)
        if validos and base is not None and base > 0:
            q, pct = min(validos, key=lambda t: (-t[1], t[0]))
            tramo = (base * (Decimal(100) - pct) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if tramo < _decimal(f['precio_catalogo']):
                divisor = (f.get('uds_caja') or M.UNIDADES_CASE_TCG) if (f['es_caja'] and perfil.get('precio_caja6') == 'caja') else 1
                escalon, uds = float(tramo) / divisor, q
                c['n_escalon_gana'] += 1
        f.update(precio_escalon=escalon, uds_escalon=uds, precio_pa=escalon)
    return c


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


def descarga_cortada(rec, tolerancia):
    """🔴 Lo que falta para dar la descarga por ENTERA, o [] si esta entera.

    La descarga heredada (`_paginar`) deja de pedir paginas SIN ERROR si una no llega, y un producto
    sin su fila de disponibilidad sale AGOTADO (`dispo.get(pn) or {}`). Con las disponibilidades
    cortadas, la foto diria «agotado» a cientos de productos que no lo estan, con el crudo de
    productos intacto: por eso se exige que LOS TRES endpoints lleguen enteros.

    «Entera» = |llegados − declarados| <= `tolerancia` en cada endpoint (`disp_parametros.
    tolerancia_endpoint`; HEO: 10, Fernando, 29-sep-2026). El catalogo de HEO cambia mientras se
    pagina: el 29-sep, dos pasadas seguidas llegaron con 2 precios de menos y con 1 producto de MAS,
    sin perder ninguna pagina. Una pagina perdida son 500 (o lo que traiga la ultima).
    🔑 Los productos se cuentan DISTINTOS: el crudo menos sus copias repetidas (`n_duplicados`, de
    `duplicados_de_los_crudos`). Precios y disponibilidades ya llegan contados sin repetir (la
    heredada los junta por numero)."""
    faltan = []
    if not isinstance(tolerancia, int) or isinstance(tolerancia, bool) or tolerancia < 0:
        return ['sin tolerancia: la base no da una tolerancia_endpoint válida (%r)' % (tolerancia,)]
    for nombre, declarado, llego in ENDPOINTS:
        llegados = rec.get(llego)
        if nombre == 'productos' and llegados is not None:
            if rec.get('n_duplicados') is None:
                faltan.append('productos: sin recuento de repetidos')
                continue
            llegados -= rec['n_duplicados']
        if rec.get(declarado) is None or llegados is None:
            faltan.append('%s: sin recuento en el log (declarado %s, llegados %s)' % (nombre, rec.get(declarado), rec.get(llego)))
        elif abs(llegados - rec[declarado]) > tolerancia:
            faltan.append('%s: HEO declara %s y llegaron %s (tolerancia %s)' % (nombre, rec[declarado], llegados, tolerancia)
                          + (' · repetidos aparte: %s' % rec['n_duplicados'] if nombre == 'productos' and rec['n_duplicados'] else ''))
    if rec.get('n_sin_gtin') is None:
        faltan.append('sin GTIN: sin recuento en el log')
    return faltan


# Los tres listados crudos, con el nombre de su recuento de repetidos y si sus copias se comparan aqui
# (products no: sus copias se comparan fila a fila, en lo que se sube; ver construir_disponibilidad).
REPETIDOS = (('catalog/products', 'n_duplicados', False),
             ('catalog/prices', 'n_duplicados_precios', True),
             ('catalog/availabilities', 'n_duplicados_disponibilidades', True))


def duplicados_de_los_crudos(crudos):
    """Cuantas copias REPETIDAS de un mismo producto trae cada listado crudo (lo que devolvio
    `_paginar`). Devuelve (conteos, problemas): conteos = {n_duplicados, n_duplicados_precios,
    n_duplicados_disponibilidades} y problemas = lo que impide seguir.

    🔴 En precios y disponibilidades, dos copias del mismo numero tienen que ser IDENTICAS (el registro
    entero: todo lo que trae se usa, y la heredada se queda con la ultima sin avisar); si no, es un
    problema y la lectura no se sube. Los conteos se devuelven igual, para que la pasada fallida los
    guarde (revision de Cowork, 29-sep-2026). Sin un listado, LecturaInvalida."""
    out, problemas = {}, []
    for endpoint, clave, comparar in REPETIDOS:
        if endpoint not in crudos:
            raise LecturaInvalida('no se vio la lista cruda de %s: sin ella no se cuentan los repetidos' % endpoint)
        vistos, n, distintos = {}, 0, []
        for x in crudos[endpoint] or []:
            pn = x.get('productNumber')
            if pn in vistos:
                n += 1
                if comparar and x != vistos[pn]:
                    distintos.append(str(pn))
            else:
                vistos[pn] = x
        if distintos:
            problemas.append('%s: número(s) de HEO repetidos con datos distintos: %s'
                             % (endpoint, ', '.join(sorted(set(distintos))[:10])))
        out[clave] = n
    return out, problemas


def sin_gtin_de_los_crudos(numeros_crudos, filas_heo, chase_heo):
    """Los productos SIN GTIN, contados UNA vez, desde el listado crudo de products y lo que devolvio la
    descarga: (unicos, copias). Un numero del listado sin ninguna fila es un sin GTIN (la heredada lo
    tira); `copias` son todas sus apariciones, que es lo que cuenta el log («descartadas N sin
    GTIN»), y `unicos`, los productos. Se sabe ANTES de construir nada, asi que la pasada guarda el
    bueno desde el principio, tambien si acaba fallida (revision de Cowork, 29-sep-2026)."""
    con_fila = {}
    for f in filas_heo or []:
        con_fila[_texto(f.get('productNumber'))] = con_fila.get(_texto(f.get('productNumber')), 0) + 1
    for c in chase_heo or []:
        con_fila[_texto(c.get('producto_heo'))] = con_fila.get(_texto(c.get('producto_heo')), 0) + 1
    en_listado, sin_numero = {}, 0
    for pn in numeros_crudos:
        if _texto(pn) is None:
            sin_numero += 1   # sin numero no se puede agrupar: cada uno cuenta como un producto
        else:
            en_listado[_texto(pn)] = en_listado.get(_texto(pn), 0) + 1
    copias = sin_numero + sum(max(n - con_fila.get(pn, 0), 0) for pn, n in en_listado.items())
    unicos = sin_numero + sum(1 for pn in en_listado if con_fila.get(pn, 0) == 0)
    return unicos, copias


# Las listas crudas que hacen falta para distinguir «sin dato», con el recuento del log que las cuadra.
CRUDOS = (('catalog/prices', 'n_precios'), ('catalog/availabilities', 'n_disponibilidades'))


def listas_de_los_crudos(crudos, rec):
    """De las listas crudas de `prices` y `availabilities` (lo que devolvio `_paginar`, cogido al paso)
    a los dos conjuntos de numeros de HEO CON dato: (con_precio, con_disponibilidad).

    🔴 Comprueba que son las MISMAS listas que uso la descarga: la heredada las junta en un dict por
    `productNumber` y dice su tamaño en el log («Cruzando: … Q precios | R disponibilidades»). Si
    falta una lista o su tamaño no es ese, LecturaInvalida: sin ellas no se distingue «sin dato» de
    «agotado», y eso no se adivina."""
    conjuntos = []
    for endpoint, clave in CRUDOS:
        if endpoint not in crudos:
            raise LecturaInvalida('no se vio la lista cruda de %s: sin ella no se distingue «sin dato» de «agotado»' % endpoint)
        crudos_pn = {x.get('productNumber') for x in crudos[endpoint] or []}
        if len(crudos_pn) != rec.get(clave):
            raise LecturaInvalida('la lista cruda de %s tiene %d números y la descarga dijo %s: no es la que usó'
                                  % (endpoint, len(crudos_pn), rec.get(clave)))
        conjuntos.append({_texto(pn) for pn in crudos_pn} - {None})
    return tuple(conjuntos)
