# -*- coding: utf-8 -*-
"""ESCANER 2 · EL ESCANEO DE UNA FACTURA (encargo F2, 16-oct-2026).

PARA QUE (Fernando, 16-oct-2026): «Si escaneo la factura es para ver que mandar de esa factura». Elena mete la
factura, abre su tabla, ve lo rentable, crea en Seller las fichas de lo nuevo y prepara cajas. Lo que necesita en
cada pais: el precio de venta, el margen, las ventas al mes (caidas de puesto a 30 dias) donde sale rentable, y en
Paises Bajos y Belgica el precio que deja un 12 % («no se van a tocar nunca»).

QUE HACE, POR LINEA DE LA FACTURA Y PAIS (ES, IT, FR, DE):
  a) Si la app YA TIENE DATOS DE HOY de ese ASIN y pais, se usan: el precio de la caja de compra del cartero
     (`amz_precio_dia`, fecha = hoy) o de la foto diaria de Keepa del Trackeador (`keepa_escaparate`, fecha_foto =
     hoy), y la tarifa y la comision del cartero (`amz_tarifa`, la vigente hoy) o de esa misma foto. Cero tokens.
  b) Si no, Keepa EN EL MOMENTO, pais a pais, con `datos_pais` del viejo (heredado: la caja de compra ATERRIZADA,
     su comision y su tarifa). Sin ASIN en la ficha, primero Keepa ES por el codigo de barras y la eleccion del viejo
     (`EleccionViejo`, su cotejo por nombre). Nada de esperar al cartero.
  🔴 EL ESCALON DE LOS 20 € (Identidad 10): la tarifa del cartero es la de NUESTRO precio (`amz_tarifa.mi_precio`) y la
     de la foto, la del precio de la foto. Si ese precio y el de venta caen a lados distintos de 20 €, la tarifa se
     pasa por `fn_fee_escalon` de la base (la que usa el Trackeador) y la fila lo dice (`tarifa_escalon`). Visto en la
     sombra del 16-oct-2026, en Italia: tarifa del cartero 3,64 € calculada a 19,99 €, y caja de compra a 23,43 €; a ese
     precio la tarifa es 4,61 €, la misma que cobra Keepa. Sin esto el margen salía optimista.
  c) La cuenta y el veredicto, los de siempre: `calcular_pais` del Escaneo PRO, que ejecuta `calc_rentabilidad` y
     `decision_de` del viejo (heredados, letra por letra). Cada fila dice de donde sale cada dato y su fecha.
VENTAS AL MES: las caidas de puesto a 30 dias de la foto de hoy, o de la respuesta de Keepa si se le pregunto; si no
  hay ninguna y el pais sale RENTABLE (COMPRAR), una pregunta a Keepa sin caja de compra (1 token).
PAISES BAJOS Y BELGICA: el precio que deja MARGEN_OBJETIVO con `fn_precio_al_margen_escalon` de la base (la que ya
  usa el Trackeador, con el escalon de los 20 €), comision 15 %, IVA 21 % y la tarifa del pais si la app la tiene
  (`amz_tarifa` NL/BE); si no, la de España de esta misma linea, y la fila lo dice (`tarifa_de = 'ES'`). Ese precio
  se enseña tal cual: no cuenta para «pais rentable» ni decide nada.

🔴 EL CHASE NO SE ESCANEA: la v2 ya no lo manda, y si una ficha chase llegara, se aparta aqui sin preguntar a nadie
   (CLAUDE.md, identidad: el chase NUNCA lleva ASIN).
🔴 SIN DATO NO ES CERO: un pais sin precio, tarifa o comision sale «Sin datos», con su motivo, nunca con un 0.
🔒 Las piezas del viejo salen de escaner2_heredado_nube.py (`sacar_piezas`), no del viejo: lo vigila
   test_escaner2_heredado.py. La llamada a Keepa es la del escaner 2 (`escaner2_novedades.Keepa`, por la API).

MODULO PURO EN LO QUE DECIDE: la base y Keepa entran por parametro (`Base`, `Keepa`), y el banco
(test_escaner2_factura.py) los cambia por dobles. El arranque, la llave y la escritura: escaner2_factura_nube.py.
"""
import base64
import gzip
import json
from datetime import date

import escaner2_motor as e2
import escaner2_novedades as nv

PAISES_CALCULO = ('ES', 'IT', 'FR', 'DE')
PAISES_PRECIO_FIJO = ('NL', 'BE')
# Fernando, 16-oct-2026: «Yo buscaria una rentabilidad del 12% siempre».
MARGEN_OBJETIVO = 0.12
COMISION_FIJA_PCT = 15.0
IVA_FIJO = 0.21
REDONDEO_PRECIO_FIJO = 'ceil_centimo'
# Lo que se deja sin gastar del saldo de Keepa, como el respaldo de las novedades (nov_parametros: 20 y 3).
RESERVA_KEEPA, TOPE_PETICION = 20, 3
# `rentable` = el veredicto del viejo es COMPRAR (margen >= 10 %): es donde se enseñan las ventas al mes.
DECISION_RENTABLE = 'COMPRAR'


class FacturaInvalida(ValueError):
    """La peticion de la v2 no se puede escanear tal cual (sin lineas, una linea sin EAN…): se dice y no se gasta nada."""


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · LAS PIEZAS DEL VIEJO (heredadas)
# ═══════════════════════════════════════════════════════════════════════════════
DEFS_KEEPA_PAIS = ('_url_imagen', 'datos_pais')
NOMBRES_KEEPA_PAIS = ('IDX_RANK', 'IDX_NEW', 'IDX_BBOX_LAND')


class PreguntaPais:
    """`datos_pais` del viejo, ejecutado con NUESTRA llamada a Keepa (`keepa_query` inyectada). Ademas de lo que
    devuelve, se queda con el producto crudo de la respuesta: de ahi salen las caidas de puesto, que el viejo no
    devolvia (las leia en la Fase 1)."""

    def __init__(self, keepa, ruta=e2.RUTA_MOTOR):
        self.keepa = keepa
        self.perdidos = []
        self.crudo = {}
        self.motivo = None
        self._ns = e2.sacar_piezas(ruta, DEFS_KEEPA_PAIS, NOMBRES_KEEPA_PAIS,
                                   base={'keepa_query': self._keepa_query, 'PAISES_PERDIDOS': self.perdidos})

    def _keepa_query(self, items, product_code_is_asin=False, domain='ES', stats=90, history=0, buybox=False, **_kw):
        """Lo que `datos_pais` espera de `keepa_query` del viejo: la lista de productos, o None si no se pudo."""
        self.motivo = None
        prods = preguntar(self.keepa, domain, items, 'asin' if product_code_is_asin else 'code', bool(buybox))
        if isinstance(prods, str):
            self.motivo = prods
            return None
        for p in prods:
            self.crudo[(p.get('asin'), domain)] = p
        return prods

    def datos(self, asin, pais):
        """(datos del viejo o None, motivo si no hay)."""
        d = self._ns['datos_pais'](asin, pais)
        if d is None:
            return None, self.motivo or 'Keepa no tiene este ASIN en este país'
        return d, None

    def caidas(self, asin, pais):
        p = self.crudo.get((asin, pais))
        return nv.ficha_de_keepa(p)['caidas_30d'] if p else None


def preguntar(keepa, pais, codigos, por, buybox):
    """Una peticion a Keepa con la reserva de siempre. Devuelve la lista de productos o, si no se pregunta o falla,
    el MOTIVO (texto). Nunca lanza: un pais sin respuesta es «Sin datos» con su porque, no un escaneo roto."""
    if keepa is None or not keepa.llave:
        return 'sin KEEPA_API_KEY: no se ha podido preguntar a Keepa'
    if keepa.caido:
        return 'Keepa no contesta en esta corrida: %s' % keepa.caido[:200]
    try:
        if keepa.saldo is None:
            keepa.leer_saldo()
        if keepa.saldo - RESERVA_KEEPA < TOPE_PETICION:
            return 'Keepa sin saldo: quedaban %d tokens y la reserva es %d' % (keepa.saldo, RESERVA_KEEPA)
        return keepa.productos(pais, list(codigos), por=por, buybox=buybox)
    except nv.KeepaFalla as ex:
        keepa.caido = str(ex)
        return 'Keepa falló: %s' % str(ex)[:200]


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · LAS LINEAS DE LA FACTURA
# ═══════════════════════════════════════════════════════════════════════════════
def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def normalizar_lineas(lineas):
    """La peticion de la v2 (`escaner2_factura_pasada.lineas`) → lineas con la forma que usa el escaneo. Cada linea:
    linea (su orden), producto_id, ean, asin (de la ficha, solo si la v2 sabe su unidad), pa (el coste de la linea,
    ya en la unidad de la ficha: una caja de 4 cuyo papel factura la unidad a 1,00 viaja a 4,00), factor, unidades y
    nombre."""
    if not isinstance(lineas, list) or not lineas:
        raise FacturaInvalida('la factura llega sin líneas que escanear')
    salida, vistas = [], set()
    for i, l in enumerate(lineas):
        if not isinstance(l, dict):
            raise FacturaInvalida('la línea %d no es un objeto' % i)
        ean = str(l.get('ean') or '').strip()
        if not ean:
            raise FacturaInvalida('la línea %d llega sin código de barras' % i)
        n = int(l.get('linea', i))
        if n in vistas:
            raise FacturaInvalida('la línea %d viene dos veces' % n)
        vistas.add(n)
        asin = str(l.get('asin') or '').strip().upper() or None
        salida.append({'linea': n, 'producto_id': (str(l.get('producto_id') or '').strip() or None), 'ean': ean,
                       'asin': asin, 'pa': _num(l.get('pa')), 'factor': int(l.get('factor') or 1),
                       'unidades': _num(l.get('unidades')), 'nombre': str(l.get('nombre') or '').strip()})
    return salida


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · LOS DATOS DE HOY QUE YA TIENE LA APP
# ═══════════════════════════════════════════════════════════════════════════════
def _canal_cartero(logistica):
    return 'BB-FBA' if str(logistica or '').upper() == 'AFN' else 'BB-FBM'


def datos_app(precios, tarifas, fotos, hoy):
    """{(asin, PAIS): dato} con lo que la app sabe HOY. Puro.
      · precio: la caja de compra del cartero de hoy; si no, la de la foto de Keepa de hoy; si no, el «nuevo» de esa
        foto (SIN BB, como el viejo cuando no hay caja de compra);
      · tarifa y comision: la tarifa vigente del cartero (comision = tarifa de referencia / su precio, como
        `v_hechos_ficha_pais`); si no, las de la foto de Keepa de hoy;
      · caidas: las de la foto de hoy.
    Un dato de otro dia NO entra: un informe caducado da informacion falsa."""
    hoy = str(hoy)
    sku_hoy, out = {}, {}

    def fila(asin, pais):
        return out.setdefault((asin, pais), {'asin': asin, 'pais': pais})

    for p in precios:
        if str(p.get('fecha')) != hoy:
            continue
        asin, pais = p['asin'], str(p['pais']).upper()
        sku_hoy[(asin, pais)] = p.get('seller_sku')
        if _num(p.get('bb_precio')):
            f = fila(asin, pais)
            f.update(precio=_num(p['bb_precio']), canal=_canal_cartero(p.get('bb_logistica')), fuente_precio='cartero',
                     fecha_precio=hoy)
    # La tarifa: la vigente hoy (vigente_desde <= hoy), la del SKU del precio de hoy si lo hay, si no la mas reciente.
    mejor = {}
    for t in tarifas:
        if str(t.get('vigente_desde')) > hoy or _num(t.get('tarifa_gestion')) is None:
            continue
        clave = (t['asin'], str(t['pais']).upper())
        rango = (t.get('seller_sku') == sku_hoy.get(clave), str(t.get('vigente_desde')))
        if clave not in mejor or rango > mejor[clave][0]:
            mejor[clave] = (rango, t)
    for clave, (_r, t) in mejor.items():
        f = fila(*clave)
        precio_t = _num(t.get('mi_precio'))
        ref = _num(t.get('tarifa_referencia'))
        f.update(fee=_num(t['tarifa_gestion']), fuente_tarifa='cartero', fecha_tarifa=str(t.get('vigente_desde')),
                 ref_pct=round(100.0 * ref / precio_t, 2) if (ref is not None and precio_t) else None, base_tarifa=precio_t)
    for k in fotos:
        if str(k.get('fecha_foto')) != hoy:
            continue
        f = fila(k['asin'], str(k['dominio']).upper())
        if f.get('precio') is None:
            if _num(k.get('bb_precio')):
                f.update(precio=_num(k['bb_precio']), canal='BB-FBA' if k.get('bb_es_fba') else 'BB-FBM',
                         fuente_precio='keepa_foto', fecha_precio=hoy)
            elif _num(k.get('nuevo_precio')):
                f.update(precio=_num(k['nuevo_precio']), canal='SIN BB', fuente_precio='keepa_foto', fecha_precio=hoy)
        if f.get('fee') is None and _num(k.get('tarifa_fba')) is not None and _num(k.get('comision_pct')) is not None:
            f.update(fee=_num(k['tarifa_fba']), ref_pct=_num(k['comision_pct']), fuente_tarifa='keepa_foto',
                     fecha_tarifa=hoy, base_tarifa=_num(k.get('bb_precio')) or _num(k.get('nuevo_precio')))
        if k.get('rank_drops_30d') is not None and int(k['rank_drops_30d']) >= 0:
            f['caidas'] = int(k['rank_drops_30d'])
    return out


def tarifas_fijas(tarifas, hoy):
    """{(asin, 'NL'|'BE'): tarifa de gestion vigente hoy} (la mas reciente). Puro."""
    hoy, mejor = str(hoy), {}
    for t in tarifas:
        pais = str(t.get('pais')).upper()
        if pais not in PAISES_PRECIO_FIJO or str(t.get('vigente_desde')) > hoy or _num(t.get('tarifa_gestion')) is None:
            continue
        clave = (t['asin'], pais)
        if clave not in mejor or str(t['vigente_desde']) > mejor[clave][0]:
            mejor[clave] = (str(t['vigente_desde']), _num(t['tarifa_gestion']))
    return {k: v[1] for k, v in mejor.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# 4 · EL ESCANEO
# ═══════════════════════════════════════════════════════════════════════════════
def _fila_vacia(l, pais, asin, asin_origen):
    return {'linea': l['linea'], 'producto_id': l['producto_id'], 'ean': l['ean'], 'asin': asin,
            'asin_origen': asin_origen, 'pais': pais, 'pa': l['pa'], 'fuente': 'sin_dato', 'fuente_precio': None,
            'fuente_tarifa': None, 'fecha_precio': None, 'fecha_tarifa': None, 'precio_venta': None, 'canal': None,
            'ref_pct': None, 'fee_fba': None, 'iva': None, 'almacen': None, 'com_digitales': None, 'isd_pct': None,
            'isd_incluye_fba': None, 'beneficio': None, 'roi': None, 'margen': None, 'decision': None,
            'tarifa_escalon': None, 'caidas_30d': None, 'caidas_fuente': None, 'rentable': None, 'precio_objetivo': None,
            'margen_objetivo': None, 'tarifa_de': None, 'motivo': None}


def _cuenta(fila, pais, precio, canal, ref_pct, fee, core, M, asin):
    """La cuenta del pais con `calcular_pais` del Escaneo PRO (calc_rentabilidad + decision_de del viejo)."""
    rec = nv.rec_de_fila({'asin': asin, 'precio_venta': precio, 'canal': canal, 'ref_pct': ref_pct, 'fee_fba': fee})
    r = e2.calcular_pais(pais, rec, fila['pa'], core, M)
    fila.update(precio_venta=r['precio_venta'], canal=r['canal'], ref_pct=r['ref_pct'], fee_fba=r['fee_fba'],
                iva=r['iva'], almacen=r['almacen'], com_digitales=r['com_digitales'], isd_pct=r['isd_pct'],
                isd_incluye_fba=r['isd_incluye_fba'], beneficio=r['beneficio'], roi=r['roi'], margen=r['margen'],
                decision=r['decision'], rentable=r['decision'] == DECISION_RENTABLE)
    if r['decision'] == 'Sin datos' and not fila['motivo']:
        fila['motivo'] = ('sin coste en la línea' if not fila['pa'] else
                          'sin precio de venta' if not r['precio_venta'] else 'sin comisión o tarifa')


def _km_a_fecha(km):
    """`listedSince` de Keepa (minutos Keepa: epoca 2011-01-01 = +21564000 min sobre Unix) -> 'AAAA-MM-DD', o None si
    no lo sabe (0 o negativo). La misma cuenta que el viejo al escribir `sondeo_keepa.listado_desde`."""
    if not isinstance(km, (int, float)) or km <= 0:
        return None
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp((km + 21564000) * 60, timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _candidato_sondeo(l, p, posicion, elegido):
    """Un producto de Keepa que casa con el codigo de barras de la linea -> la fila de `sondeo_keepa` (sin `lote` ni
    fecha: los pone quien escribe). Los MISMOS campos que dejaba el viejo (Celda 9c de moloka_escaner_nube.py), para
    que el clasificador de la v2 (lib/sondeo/clasificar.ts) los lea sin cambiar nada."""
    st = p.get('stats') or {}
    f = nv.ficha_de_keepa(p)
    cur, a90 = st.get('current') or [], st.get('avg90') or []
    return {'ean_consultado': l['ean'], 'asin_candidato': p['asin'], 'posicion': posicion,
            'titulo': f['titulo'] or None, 'rank': f['rank'], 'rank_drops_30d': f['caidas_30d'],
            'listado_desde': _km_a_fecha(p.get('listedSince')),
            'crudo': {'asin': p['asin'], 'title': p.get('title'),
                      'r_act': cur[nv.IDX_RANK] if len(cur) > nv.IDX_RANK else -1,
                      'r_90': a90[nv.IDX_RANK] if len(a90) > nv.IDX_RANK else -1,
                      'ean_in': l['ean'], 'rank_drops_30d': st.get('salesRankDrops30'),
                      'listedSince': p.get('listedSince'),
                      # Lo que el viejo no tenia: quien escribio la fila y si fue el que eligio el cotejo por nombre
                      # (para ESTE escaneo). La v2 NO lo usa para escribir: con varios candidatos decide una persona.
                      'escaner': 'escaner2_factura', 'elegido_por_nombre': elegido}}


def resolver_asin(lineas, keepa, M, eleccion, sondeo=None):
    """{linea: (asin, origen, motivo)}. Con ASIN de la ficha, ese (origen 'ficha'). Sin el, Keepa ES por el codigo de
    barras (el `core` y sus variantes, como la Fase 1 del viejo) y, si hay varias fichas, la eleccion del viejo por
    su cotejo de nombre (`EleccionViejo.elegir`). Identidad: el ASIN elegido por nombre solo sirve para ESTE escaneo;
    este programa no escribe en ninguna ficha.

    🔑 (encargo P1, 19-oct-2026) Con `sondeo` (una lista), apunta en ella TODOS los candidatos que Keepa devolvio para
       el codigo de barras de cada linea, no solo el elegido: es lo que la v2 clasifica para poner el ASIN en la ficha
       (`asignar_asin_sondeo`, con sus guardas). Hasta hoy solo quedaba el elegido, y desde la base no se sabia si el
       escaneo habia dudado. Si Keepa contesta y no casa ninguno, una fila CENTINELA (`asin_candidato` = None): «se
       pregunto y no habia» es un dato. Si a Keepa no se le pudo preguntar (sin saldo, caido, codigo raro), NADA: eso
       no es «no hay», es «no se sabe». Las lineas con el ASIN de su ficha no se preguntan por el codigo: tampoco."""
    out = {}
    for l in lineas:
        if l['asin']:
            out[l['linea']] = (l['asin'], 'ficha', None)
            continue
        core = M.core_ean(l['ean'])
        if not core.isdigit() or len(core) not in (12, 13):
            out[l['linea']] = (None, None, 'código de barras con forma rara (%d cifras) y la ficha sin ASIN' % len(core))
            continue
        variantes = {M.norm(v) for v in M.variantes_ean(core)}
        registros, motivo, prods_casan = [], None, []
        for codigos in ([core], [v for v in M.variantes_ean(core) if v != core]):
            if not codigos:
                continue
            prods = preguntar(keepa, 'ES', codigos, 'code', False)
            if isinstance(prods, str):
                motivo = prods
                break
            for p in prods:
                eans = {M.norm(str(e)) for e in (p.get('eanList') or []) + (p.get('upcList') or [])}
                if p.get('asin') and eans & variantes and p['asin'] not in {r['asin'] for r in registros}:
                    f = nv.ficha_de_keepa(p)
                    registros.append({'asin': p['asin'], 'titulo': f['titulo'], 'rank90': f['rank_90d']})
                    prods_casan.append(p)
            if registros:
                break
        if not registros:
            sin = 'Keepa no encuentra el código de barras en Amazon España'
            out[l['linea']] = (None, None, motivo or sin)
            if sondeo is not None and motivo is None:
                sondeo.append({'ean_consultado': l['ean'], 'asin_candidato': None, 'posicion': None, 'titulo': None,
                               'rank': None, 'rank_drops_30d': None, 'listado_desde': None,
                               'crudo': {'centinela': True, 'motivo': sin, 'escaner': 'escaner2_factura'}})
            continue
        e = eleccion.elegir(l['nombre'], registros)
        out[l['linea']] = (e['asin'], 'keepa_ean', None)
        if sondeo is not None:
            sondeo.extend(_candidato_sondeo(l, p, i, p['asin'] == e['asin']) for i, p in enumerate(prods_casan))
    return out


def _ean_norm(cod):
    """Replica de `public.moloka_ean_norm`: solo cifras, sin ceros delante; vacio -> None."""
    return ''.join(ch for ch in str(cod or '') if ch.isdigit()).lstrip('0') or None


def filas_sondeo(ejecucion, candidatos, hoy):
    """Las filas de `sondeo_keepa` de esta pasada: `lote` = la ejecucion (lo que la v2 le pasa a la asignacion),
    `dominio` 'es' (se pregunta a Keepa ES), `fecha_sondeo` = hoy y `fichero` = la ejecucion, como el viejo.
    🔴 La clave unica de la tabla es (lote, ean_norm, dominio, asin_candidato) NULLS NOT DISTINCT: dos lineas con el
       mismo codigo de barras darian la misma fila y el INSERT entero fallaria. Se deja la primera y se CUENTA lo
       descartado (devuelve (filas, descartadas)). `ean_norm` lo calcula Postgres; aqui solo se replica para no chocar."""
    filas, vistos, dups = [], set(), 0
    for c in candidatos:
        k = (_ean_norm(c['ean_consultado']), c['asin_candidato'])
        if k in vistos:
            dups += 1
            continue
        vistos.add(k)
        filas.append(dict(c, lote=ejecucion, dominio='es', fecha_sondeo=str(hoy), fichero=ejecucion))
    return filas, dups


def escanear(lineas, base, keepa, M, hoy, eleccion=None, productos=None):
    """El escaneo de una factura → (filas, resumen). `base` da los datos de la app (lecturas) y el precio al margen
    (`precio_al_margen`); `keepa` es un `escaner2_novedades.Keepa` (o su doble). NO ESCRIBE NADA."""
    lineas = normalizar_lineas(lineas)
    productos = productos if productos is not None else base.productos([l['producto_id'] for l in lineas if l['producto_id']])
    por_id = {p['id']: p for p in productos}
    M.poner_catalogo_propio(productos)
    chase = [l['linea'] for l in lineas if (por_id.get(l['producto_id']) or {}).get('es_chase')]
    lineas = [l for l in lineas if l['linea'] not in chase]
    if eleccion is None:
        eleccion = e2.cargar_eleccion_viejo([l['nombre'] for l in lineas])
    sondeo = []
    asin_de = resolver_asin(lineas, keepa, M, eleccion, sondeo)
    asins = sorted({a for a, _o, _m in asin_de.values() if a})
    tarifas = base.tarifas(asins, hoy)
    app = datos_app(base.precios_dia(asins, hoy), tarifas, base.fotos_keepa(asins, hoy), hoy)
    fijas = tarifas_fijas(tarifas, hoy)
    pregunta = PreguntaPais(keepa)
    filas = []
    for l in lineas:
        asin, origen, motivo_asin = asin_de[l['linea']]
        core = M.core_ean(l['ean'])
        por_pais = {}
        for pais in PAISES_CALCULO:
            f = _fila_vacia(l, pais, asin, origen)
            por_pais[pais] = f
            filas.append(f)
            if not asin:
                f['motivo'] = motivo_asin
                continue
            a = app.get((asin, pais)) or {}
            if a.get('precio') is not None and a.get('fee') is not None and a.get('ref_pct') is not None:
                f.update(fuente='app', fuente_precio=a['fuente_precio'], fuente_tarifa=a['fuente_tarifa'],
                         fecha_precio=a['fecha_precio'], fecha_tarifa=a['fecha_tarifa'])
                fee = a['fee']
                b = a.get('base_tarifa')
                if b and (b < nv.ESCALON_EUR) != (a['precio'] < nv.ESCALON_EUR):
                    ajustada = base.fee_escalon(asin=asin, dominio=pais.lower(), fee=fee, precio=a['precio'])
                    if ajustada is not None and abs(ajustada - fee) > 0.004:
                        fee, f['tarifa_escalon'] = ajustada, True
                _cuenta(f, pais, a['precio'], a['canal'], a['ref_pct'], fee, core, M, asin)
                if a.get('caidas') is not None:
                    f.update(caidas_30d=a['caidas'], caidas_fuente='app')
            else:
                d, motivo = pregunta.datos(asin, pais)
                if d is None:
                    f['motivo'] = motivo
                    continue
                f.update(fuente='keepa', fuente_precio='keepa', fuente_tarifa='keepa', fecha_precio=str(hoy),
                         fecha_tarifa=str(hoy))
                _cuenta(f, pais, d.get('precio'), d.get('canal'), d.get('ref_pct'), d.get('fee'), core, M, asin)
                c = pregunta.caidas(asin, pais)
                if c is not None:
                    f.update(caidas_30d=c, caidas_fuente='keepa')
            if f['rentable'] and f['caidas_30d'] is None:
                prods = preguntar(keepa, pais, [asin], 'asin', False)
                p = next((x for x in prods if x.get('asin') == asin), None) if isinstance(prods, list) else None
                c = nv.ficha_de_keepa(p)['caidas_30d'] if p else None
                if c is not None:
                    f.update(caidas_30d=c, caidas_fuente='keepa')
        es = por_pais['ES']
        for pais in PAISES_PRECIO_FIJO:
            f = _fila_vacia(l, pais, asin, origen)
            filas.append(f)
            f['margen_objetivo'] = MARGEN_OBJETIVO
            fee, tarifa_de = fijas.get((asin, pais)), pais
            if fee is None:
                fee, tarifa_de = es['fee_fba'], 'ES'
            if not asin:
                f['motivo'] = motivo_asin
            elif not l['pa']:
                f['motivo'] = 'sin coste en la línea'
            elif fee is None:
                f['motivo'] = 'sin tarifa de %s ni de España' % pais
            else:
                f.update(fee_fba=fee, tarifa_de=tarifa_de, iva=IVA_FIJO, ref_pct=COMISION_FIJA_PCT, almacen=M.ALMACEN,
                         com_digitales=M.COM_DIGITALES,
                         fuente='app' if tarifa_de == pais or es['fuente'] == 'app' else 'keepa',
                         fuente_tarifa=('cartero' if tarifa_de == pais else es['fuente_tarifa']))
                f['precio_objetivo'] = base.precio_al_margen(
                    asin=asin, dominio=(pais if tarifa_de == pais else 'ES').lower(), fee=fee, pvd=l['pa'], iva=IVA_FIJO,
                    com_pct=COMISION_FIJA_PCT, k_com=M.COM_DIGITALES, k_fee=0.0, alm=M.ALMACEN, margen=MARGEN_OBJETIVO,
                    redondeo=REDONDEO_PRECIO_FIJO)
                if f['precio_objetivo'] is None:
                    f['motivo'] = 'la base no devuelve precio para ese margen'
    calc = [f for f in filas if f['pais'] in PAISES_CALCULO]
    resumen = {'lineas': len(lineas), 'chase_fuera': len(chase),
               'paises_app': sum(1 for f in calc if f['fuente'] == 'app'),
               'paises_keepa': sum(1 for f in calc if f['fuente'] == 'keepa'),
               'paises_sin_dato': sum(1 for f in calc if f['fuente'] == 'sin_dato'),
               'lineas_todo_app': sum(1 for l in lineas
                                      if all(f['fuente'] == 'app' for f in calc if f['linea'] == l['linea'])),
               'keepa_peticiones': getattr(keepa, 'peticiones', 0), 'keepa_tokens': getattr(keepa, 'tokens', 0),
               'keepa_saldo': getattr(keepa, 'saldo', None),
               # (encargo P1) los candidatos de Keepa por codigo de barras, para `sondeo_keepa` (los escribe la nube).
               'sondeo': sondeo}
    return filas, resumen


# ═══════════════════════════════════════════════════════════════════════════════
# 5 · LA BASE (lecturas y la funcion del precio al margen)
# ═══════════════════════════════════════════════════════════════════════════════
COLS_PRECIO = 'asin,pais,fecha,seller_sku,bb_precio,bb_logistica'
COLS_TARIFA = 'seller_sku,asin,pais,vigente_desde,mi_precio,tarifa_referencia,tarifa_gestion'
COLS_FOTO = 'asin,dominio,fecha_foto,bb_precio,bb_es_fba,nuevo_precio,tarifa_fba,comision_pct,rank_drops_30d'


class Base:
    """Lo que el escaneo lee de Supabase (con la llave de servicio) y la funcion del precio al margen."""

    def __init__(self, sb):
        self.sb = sb

    def productos(self, ids):
        return nv._en_trozos(self.sb, 'productos', 'id,ean,nombre,asin,es_chase,iva_pct', 'id', 'id', ids) if ids else []

    def precios_dia(self, asins, hoy):
        return nv._en_trozos(self.sb, 'amz_precio_dia', COLS_PRECIO, 'asin', 'asin', asins,
                             [('eq', 'fecha', str(hoy))]) if asins else []

    def tarifas(self, asins, hoy):
        if not asins:
            return []
        filas = nv._en_trozos(self.sb, 'amz_tarifa', COLS_TARIFA, 'vigente_desde', 'asin', asins)
        return [t for t in filas if str(t.get('vigente_desde')) <= str(hoy)]

    def fotos_keepa(self, asins, hoy):
        return nv._en_trozos(self.sb, 'keepa_escaparate', COLS_FOTO, 'asin', 'asin', asins,
                             [('eq', 'fecha_foto', str(hoy))]) if asins else []

    def fee_escalon(self, asin, dominio, fee, precio):
        r = self.sb.rpc('fn_fee_escalon', {'p_asin': asin, 'p_dominio': dominio, 'p_fee': fee, 'p_precio': precio}).execute()
        return _num(r.data)

    def precio_al_margen(self, asin, dominio, fee, pvd, iva, com_pct, k_com, k_fee, alm, margen, redondeo):
        r = self.sb.rpc('fn_precio_al_margen_escalon', {
            'p_asin': asin, 'p_dominio': dominio, 'p_fee': fee, 'p_pvd': pvd, 'p_iva': iva, 'p_com_pct': com_pct,
            'p_k_com': k_com, 'p_k_fee': k_fee, 'p_alm': alm, 'p_margen': margen, 'p_redondeo': redondeo}).execute()
        return _num(r.data)

    # ── lo que escribe (solo el modo de verdad; la sombra no llama a nada de esto) ──
    def pasada(self, ejecucion):
        filas = (self.sb.table(TABLA_PASADA).select('id,ejecucion,factura_id,lineas,estado')
                 .eq('ejecucion', ejecucion).execute().data) or []
        return filas[0] if filas else None

    def marcar(self, pasada_id, campos, estado_antes=None):
        """UPDATE de la pasada; con `estado_antes`, solo si sigue en ese estado (dos corridas no la toman a la vez).
        Devuelve cuantas filas cambio."""
        q = self.sb.table(TABLA_PASADA).update(campos).eq('id', pasada_id)
        if estado_antes:
            q = q.eq('estado', estado_antes)
        return len(q.execute().data or [])

    def escribir(self, pasada_id, ejecucion, filas):
        filas = [dict(f, pasada_id=pasada_id, ejecucion=ejecucion) for f in filas]
        for i in range(0, len(filas), 500):
            self.sb.table(TABLA_PAIS).insert(filas[i:i + 500]).execute()
        n = (self.sb.table(TABLA_PAIS).select('id', count='exact').eq('pasada_id', pasada_id).limit(1).execute().count)
        return n

    def escribir_sondeo(self, ejecucion, filas):
        """(encargo P1) Los candidatos de esta pasada en `sondeo_keepa`, y comprueba cuantos hay con ese `lote`."""
        for i in range(0, len(filas), 500):
            self.sb.table(TABLA_SONDEO).insert(filas[i:i + 500]).execute()
        return (self.sb.table(TABLA_SONDEO).select('id', count='exact').eq('lote', ejecucion).limit(1).execute().count)

    def detalle_viejo(self, ejecucion):
        return nv._todas(self.sb, 'escaner_detalle',
                         'ejecucion,ean,producto_id,asin,pais,pa,precio_venta,fee_fba,ref_pct,margen,decision',
                         'id', [('eq', 'ejecucion', ejecucion)])


TABLA_PASADA = 'escaner2_factura_pasada'
TABLA_PAIS = 'escaner2_factura_pais'
TABLA_SONDEO = 'sondeo_keepa'


# ═══════════════════════════════════════════════════════════════════════════════
# 6 · LA SOMBRA: las facturas ya escaneadas por el viejo, otra vez, sin escribir
# ═══════════════════════════════════════════════════════════════════════════════
def lineas_de_la_pasada_vieja(detalle, productos):
    """Las lineas que recibio el viejo en una ejecucion, reconstruidas de lo que ESCRIBIO (`escaner_detalle`): un EAN
    por fila, con su ficha y su coste (el `pa` con el que calculo). El ASIN viaja si es el de la ficha: el viejo
    pregunto por el (la ficha lo llevaba en el catalogo) o llego a el por el codigo de barras; en los dos casos es
    el mismo producto. Si el viejo eligio otro ASIN, la linea va sin ASIN, por el codigo de barras, como el."""
    por_id = {p['id']: p for p in productos}
    vistos, salida = set(), []
    for d in sorted(detalle, key=lambda x: (str(x.get('ean')), str(x.get('pais')))):
        clave = (d.get('producto_id'), d.get('ean'))
        if clave in vistos:
            continue
        vistos.add(clave)
        ficha = por_id.get(d.get('producto_id')) or {}
        asin_ficha = (ficha.get('asin') or '').strip().upper() or None
        salida.append({'linea': len(salida), 'producto_id': d.get('producto_id'), 'ean': d.get('ean'),
                       'asin': asin_ficha if asin_ficha and asin_ficha == (d.get('asin') or '').upper() else None,
                       'pa': _num(d.get('pa')), 'factor': 1, 'unidades': None,
                       'nombre': ficha.get('nombre') or d.get('nombre') or ''})
    return salida


# ═══════════════════════════════════════════════════════════════════════════════
# 7 · LA GRABACION DE KEEPA (para repetir la sombra en local sin red)
# ═══════════════════════════════════════════════════════════════════════════════
def _reducir_producto(p):
    """Lo PUBLICO de un producto de Keepa que usa este escaneo (datos de Amazon: ni costes ni facturas)."""
    st = p.get('stats') or {}
    return {'asin': p.get('asin'), 'title': p.get('title'), 'eanList': p.get('eanList'), 'upcList': p.get('upcList'),
            'referralFeePercentage': p.get('referralFeePercentage'), 'referralFeePercent': p.get('referralFeePercent'),
            'fbaFees': {'pickAndPackFee': (p.get('fbaFees') or {}).get('pickAndPackFee')},
            'monthlySold': p.get('monthlySold'),
            'stats': {k: st.get(k) for k in ('current', 'avg90', 'buyBoxPrice', 'buyBoxIsFBA', 'salesRankDrops30',
                                             'totalOfferCount')}}


class Grabadora:
    """Un `http` para `escaner2_novedades.Keepa` que pasa la peticion al de verdad y se queda con la respuesta reducida
    (sin la llave). `repetidor()` da el `http` que las sirve otra vez, en el mismo orden y con los mismos parametros."""

    def __init__(self, http=None):
        self._http = http or nv._http_de_verdad
        self.peticiones = []

    @staticmethod
    def _clave(url, params):
        return url.replace(nv.URL_KEEPA, ''), {k: str(v) for k, v in sorted(params.items()) if k != 'key'}

    def __call__(self, url, params, timeout):
        estado, cuerpo = self._http(url, params, timeout)
        ruta, p = self._clave(url, params)
        red = None
        if isinstance(cuerpo, dict):
            red = {k: cuerpo.get(k) for k in ('tokensLeft', 'tokensConsumed', 'error') if k in cuerpo}
            if 'products' in cuerpo:
                red['products'] = [_reducir_producto(x) for x in (cuerpo.get('products') or [])]
        self.peticiones.append({'ruta': ruta, 'params': p, 'estado': estado, 'cuerpo': red})
        return estado, cuerpo

    def empaquetar(self):
        return base64.b64encode(gzip.compress(json.dumps(self.peticiones, sort_keys=True).encode('utf-8'))).decode('ascii')

    @staticmethod
    def desempaquetar(texto):
        return json.loads(gzip.decompress(base64.b64decode(texto)).decode('utf-8'))

    # 🔒 LA SOMBRA SOLO SACA LA GRABACION CIFRADA (Fernando, 16-oct-2026): el repo es publico y la lista de ASIN y
    #    EAN de nuestras facturas dice que compramos, a quien y cuando. Cifrado hibrido: la grabacion comprimida va
    #    con AES-256-GCM y una clave de un solo uso; esa clave, envuelta con la clave PUBLICA RSA (OAEP, SHA-256) que
    #    llega como input del disparo. Solo quien tiene la privada (en local, fuera del repo) la abre.
    def cifrar(self, clave_publica_pem):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os as _os
        pub = serialization.load_pem_public_key(clave_publica_pem.encode('ascii'))
        clave, nonce = AESGCM.generate_key(bit_length=256), _os.urandom(12)
        claro = gzip.compress(json.dumps(self.peticiones, sort_keys=True).encode('utf-8'))
        oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        sobre = {'k': base64.b64encode(pub.encrypt(clave, oaep)).decode('ascii'),
                 'n': base64.b64encode(nonce).decode('ascii'),
                 'c': base64.b64encode(AESGCM(clave).encrypt(nonce, claro, None)).decode('ascii')}
        return base64.b64encode(json.dumps(sobre).encode('ascii')).decode('ascii')

    @staticmethod
    def descifrar(texto, clave_privada_pem):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        sobre = json.loads(base64.b64decode(texto))
        priv = serialization.load_pem_private_key(clave_privada_pem.encode('ascii'), password=None)
        oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        clave = priv.decrypt(base64.b64decode(sobre['k']), oaep)
        claro = AESGCM(clave).decrypt(base64.b64decode(sobre['n']), base64.b64decode(sobre['c']), None)
        return json.loads(gzip.decompress(claro).decode('utf-8'))

    @staticmethod
    def repetidor(peticiones):
        cola = list(peticiones)

        def http(url, params, timeout):
            ruta, p = Grabadora._clave(url, params)
            for i, x in enumerate(cola):
                if x['ruta'] == ruta and x['params'] == p:
                    cola.pop(i)
                    return x['estado'], x['cuerpo']
            raise AssertionError('la repetición pide algo que no se grabó: %s %s' % (ruta, p))
        http.pendientes = cola
        return http


def hoy_madrid():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Madrid')).date()


def fecha(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])
