# -*- coding: utf-8 -*-
"""ESCANER 2 · ESCANEO PRO DE OSMA · LA PARTE PURA (encargo AG, 02-oct-2026; AG2, mismo dia: solo España y una lista)

QUE ES. El calculo del Escaneo PRO de OSMA, sin red y sin base: la foto desde la descarga diaria, la lista
para el Visualizador, el cruce de cada articulo con sus fichas de Keepa y el Excel. La red vive en los
dos programas que lo usan:
  · escaner2_osma_barrido.py (workflow escaner2-osma-barrido.yml): de la descarga a la foto y la lista.
  · escaner2_osma_cruce.py   (workflow escaner2-osma-cruce.yml):   los CSV del Visualizador, las puertas y el Excel.

🔑 CADA ESCANER, A LA MEDIDA DE SU PROVEEDOR (Fernando, 02-oct-2026): nada de tronco comun con adaptadores. Leer
   el catalogo, filtrar y cruzar es codigo de OSMA y vive aqui. Lo que se REUTILIZA del escaner 2 de HEO, sin
   tocarlo, son las REGLAS DE COMPRA (las mismas que aplica hoy su PRO) y el formato del Excel:
     · `escaner2_motor.decidir` (las seis puertas, el corte de ventas de escaner2_parametros, el calculo en los
       paises de escaner2_parametros venda o no en cada uno, la eleccion de ficha del viejo y la FICHA COMPARTIDA
       del encargo AA; en OSMA, desde el AG2, los paises son solo ES),
       que por debajo usa `calc_rentabilidad` y `decision_de` del viejo, copiados en escaner2_heredado_nube.py;
     · `escaner2_motor.examinar_csv`, `fichas_compartidas` y el lector del CSV del Visualizador
       (escaner2_heredado_pro.py);
     · la Celda 9 del viejo (`escaner2_motor.datos_como_el_viejo` + `escribir_celda9`) y la columna «Ficha
       compartida» (`poner_columna_ficha_compartida`).

LO PROPIO DE OSMA:
  1. LA FOTO SALE DE LA DESCARGA DIARIA (disp_estado, filas vistas en la ultima pasada aplicada), no de la web.
     Filtro de Fernando (01-oct-2026, «las cosas de marca»): con marca y disponible. Los descatalogados con
     existencias ENTRAN, con la marca «no habrá más» en el Excel.
  2. EL PRECIO LLEVA EL PORTE, UNA SOLA VEZ: el de la puerta comun (v_escaner_fuente, encargo AF): Price_net ×
     (1 + porte de la ultima factura de OSMA ÷ pedido previsto), redondeado a 2 decimales DESPUES. La puerta comun
     solo trae las ~30 filas de OSMA que casan con una ficha; para las demas, la MISMA cuenta (`pa_con_porte`), y
     el barrido comprueba que en las filas que estan en los dos sitios el precio es EL MISMO (si no, falla).
  3. UNA SOLA LISTA Y UN SOLO CSV, EL DE ESPAÑA (encargo AG2, Fernando, 02-oct-2026: «Las cosas de Osma es
     dificil venderlas en Pan EU»). La lista lleva los EAN de OSMA del filtro + el EAN de NUESTRA ficha de cada
     codigo enlazado que esta en la foto, sin repetir (`lista_para_keepa_osma`). La ficha cuyo EAN no conoce Keepa
     NO se rescata (el Lenor 18459, medido el 02-oct-2026): se dice en el Resumen, calculado en cada pasada con
     keepa_escaparate (`fuera_de_keepa`). Ya no hay lista de ASIN.
  4. EL CRUCE POR CODIGO: el articulo de OSMA de un codigo enlazado (codigos_proveedor, lista CERRADA de 20) se
     decide con SUS fichas (las de su familia que traiga el CSV), no con lo que diga el EAN nuevo de OSMA. Una fila
     del CSV con el EAN de una ficha enlazada es de la fila de ESE codigo; la misma ficha por los dos caminos: una,
     la del codigo. Una fila de Keepa de una ficha enlazada no se cuelga de OTRO articulo de OSMA aunque comparta EAN.
  5. NUESTROS PACKS: coste = unidades × precio (como Reponer desde el encargo AC; el factor, como lib/packs de la
     v2, portado aqui: `factores_por_ficha`).
  6. UN SOLO AÑADIDO EN EL EXCEL: la columna «No habrá más» al final de «Análisis» (descatalogados con existencias).
     Descartado por Fernando (02-oct-2026): ni la marca «solo si va en el palé» ni la linea de control final.
"""
import io
import re
from decimal import Decimal, ROUND_HALF_UP

import escaner2_motor as e2

PROVEEDOR = 'OSMA'
CARPETA = 'osma'
# El modo de la pasada (check de escaner2_pasada.modo): todas las marcas, solo lo disponible. Para OSMA, «marca
# fuera» es «sin marca».
MODO = 'todas'
# El Visualizador no admite mas de 10.000 codigos por lista; por encima de 5.000 se avisa (encargo AG).
TOPE_LISTA = e2.TOPE_VISUALIZADOR
AVISO_LISTA = 5000

# Los nombres de las puertas previas EN OSMA. Las mismas ocho del escaner 2 (el cuadre crudo = previas + foto es
# el de siempre); en OSMA solo se usan cinco y las otras tres salen a 0.
NOMBRE_PREVIA = dict(e2.NOMBRE_PUERTA_PREVIA,
                     no_disponible='Sin existencias en OSMA',
                     marca_fuera='Sin marca',
                     sin_gtin='Sin EAN',
                     ean_forma_rara='EAN con forma rara o de relleno',
                     duplicado_proveedor='Mismo EAN que otro artículo de OSMA')

COLUMNA_NO_HABRA_MAS = 'No habrá más'
TEXTO_NO_HABRA_MAS = 'no habrá más'
ANCHO_NO_HABRA_MAS = 14


class FalloOsma(Exception):
    """Algo que impide seguir: la pasada o el cruce quedan 'fallida' con este motivo."""


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · EL PRECIO CON EL PORTE: LA CUENTA DE LA PUERTA COMUN
# ═══════════════════════════════════════════════════════════════════════════════
def _dec(x):
    return None if x is None else Decimal(str(x))


def _desc_nulos_primero(v):
    """Una clave de orden DESCENDENTE con los NULL delante, como `ORDER BY … DESC` de Postgres."""
    return (v is None, '' if v is None else str(v))


def porte_de(facturas, pedido_previsto):
    """El porte de OSMA con la MISMA regla que v_escaner_fuente (migracion 20261001154500, encargo AF):
    `gastos_envio` de la factura de OSMA mas reciente que lo tenga (`fecha DESC, created_at DESC, id DESC`, con
    los NULL delante como en Postgres) ÷ `disp_parametros.pedido_previsto_eur`. Sin pedido previsto o sin factura
    con porte, `pct` es None y el precio va sin porte, como en la puerta comun.

    `facturas`: filas de `facturas` de OSMA con `id, fecha, created_at, gastos_envio`."""
    pedido = _dec(pedido_previsto)
    con = [f for f in facturas or [] if f.get('gastos_envio') is not None]
    if pedido is None or pedido <= 0 or not con:
        return {'pct': None, 'factura': None, 'fecha': None, 'gastos_envio': None,
                'pedido_previsto': None if pedido is None else float(pedido)}
    ultima = sorted(con, key=lambda f: (_desc_nulos_primero(f.get('fecha')), _desc_nulos_primero(f.get('created_at')),
                                        _desc_nulos_primero(f.get('id'))), reverse=True)[0]
    gastos = _dec(ultima['gastos_envio'])
    return {'pct': gastos / pedido, 'factura': ultima.get('id'), 'fecha': ultima.get('fecha'),
            'gastos_envio': float(gastos), 'pedido_previsto': float(pedido)}


def pa_con_porte(precio, pct):
    """El precio de compra de UNA unidad de OSMA con el porte, como la puerta comun: `round(precio × (1 + pct), 2)`
    (sin porte, `precio` a 2 decimales: la vista lo saca como numeric(10,2)). Redondeo de Postgres (la mitad, lejos
    del cero), con Decimal: nada de coma flotante en medio."""
    if precio is None:
        return None
    p = _dec(precio)
    v = p if pct is None else p * (1 + pct)
    return float(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def texto_pct(pct):
    return '—' if pct is None else ('%.2f %%' % (float(pct) * 100)).replace('.', ',')


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · LOS ENLACES POR CODIGO Y NUESTROS PACKS
# ═══════════════════════════════════════════════════════════════════════════════
def ean_norm(v):
    """`moloka_ean_norm` de la base y `eanNorm` de la v2: solo cifras y sin ceros delante; vacio → None."""
    s = re.sub(r'[^0-9]', '', str(v or '')).lstrip('0')
    return s or None


def _clave_codigo(c):
    s = str(c or '')
    return (0, int(s), s) if s.isdigit() else (1, 0, s)


def _ficha_viva(p):
    """Una ficha que se vende en Amazon por ASIN: activa, no chase (el chase NUNCA lleva ASIN) y con ASIN."""
    return bool(p.get('activo')) and not p.get('es_chase') and bool(p.get('asin'))


def enlaces_de(codigos, productos):
    """{codigo: {'producto_id', 'ean_ficha', 'asins'}} de los enlaces de OSMA (`codigos_proveedor`), con las fichas
    de la MISMA familia que la puerta comun: la ficha del codigo y todas las fichas vivas con su EAN normalizado
    (asi el 18459 trae el Lenor suelto y el Pack 2). Y los avisos de lo que no se puede usar (un codigo sin ficha,
    o sin ninguna ficha viva). Puro.

    `codigos`: filas de codigos_proveedor (proveedor OSMA) con `codigo_proveedor, producto_id`;
    `productos`: filas con `id, asin, ean, activo, es_chase`."""
    por_id = {p['id']: p for p in productos or []}
    familia = {}
    for p in productos or []:
        k = ean_norm(p.get('ean'))
        if k and _ficha_viva(p):
            familia.setdefault(k, []).append(p)
    enlaces, avisos = {}, []
    for c in sorted(codigos or [], key=lambda x: _clave_codigo(x.get('codigo_proveedor'))):
        codigo = str(c.get('codigo_proveedor') or '').strip()
        ficha = por_id.get(c.get('producto_id'))
        if not codigo:
            continue
        if ficha is None:
            avisos.append('El código %s de OSMA apunta a una ficha que no está en productos' % codigo)
            continue
        k = ean_norm(ficha.get('ean'))
        fichas = list(familia.get(k, [])) if k else ([ficha] if _ficha_viva(ficha) else [])
        asins = sorted({p['asin'] for p in fichas})
        if not asins:
            avisos.append('El código %s de OSMA no tiene ninguna ficha activa con ASIN' % codigo)
            continue
        enlaces[codigo] = {'producto_id': ficha['id'], 'ean_ficha': ficha.get('ean'), 'asins': asins}
    return enlaces, avisos


# ── EL FACTOR DE UN PACK: lib/packs/factores.ts y lib/packs/grupos.ts de la v2, PORTADOS ─────────────────────
# 🔑 La MISMA regla que Reponer (encargo AC) y la casilla «Unidades por pack» (encargo AD). Si se cambia alli, se
#    cambia aqui: test_escaner2_osma.py coteja los tres grupos reales que mide la v2 (Ultra Pro x1-x4, Protefix
#    x1-x2-x5, Lenor x1-x2) y la casilla. 🔴 El marcador del nombre SOLO decide dentro de un grupo de fichas que
#    comparten EAN: fuera de uno, factor 1 (los Funko «2-PACK», el Kleenex «Maxi pack 128»).
#    re.ASCII: `\b` y `\d` como en JavaScript.
_RE_PACK = re.compile(r'\bpack\s*(?:de\s*)?(\d{1,4})\b', re.I | re.A)
_RE_PACK_INV = re.compile(r'\b(\d{1,4})\s*-?\s*pack\b', re.I | re.A)


def unidades_por_pack_de(v):
    """`unidadesPorPackDe`: la casilla vale solo si es un entero > 1."""
    try:
        if isinstance(v, bool):
            return None
        n = float(v) if isinstance(v, (int, float)) else (float(v) if isinstance(v, str) and v.strip() else float('nan'))
    except ValueError:
        return None
    return int(n) if (n == n and n.is_integer() and n > 1) else None


def tamano_pack_por_marcador(nombre):
    s = str(nombre or '')
    m = _RE_PACK.search(s) or _RE_PACK_INV.search(s)
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


def _esqueleto(nombre):
    nums = []

    def poner(m):
        nums.append(int(m.group(0)))
        return '#'
    return re.sub(r'\d+', poner, str(nombre or ''), flags=re.A), nums


def tamanos_por_plantilla(nombres):
    if len(nombres) < 2:
        return None
    partes = [_esqueleto(n) for n in nombres]
    if any(p[0] != partes[0][0] for p in partes):
        return None
    n = len(partes[0][1])
    if n == 0 or any(len(p[1]) != n for p in partes):
        return None
    variables = [i for i in range(n) if any(p[1][i] != partes[0][1][i] for p in partes)]
    if len(variables) != 1:
        return None
    tam = [p[1][variables[0]] for p in partes]
    return tam if all(t > 0 for t in tam) else None


def _normalizar(tam):
    m = min(tam)
    if not m > 0:
        return None
    f = [t / m for t in tam]
    return [int(x) for x in f] if all(float(x).is_integer() and x >= 1 for x in f) else None


def factores_de_grupo(nombres):
    if len(nombres) < 2:
        return None
    por_marcador = [tamano_pack_por_marcador(n) or 1 for n in nombres]
    if any(t > 1 for t in por_marcador) and len(set(por_marcador)) > 1:
        f = _normalizar(por_marcador)
        if f:
            return f
    por_plantilla = tamanos_por_plantilla(nombres)
    if por_plantilla and len(set(por_plantilla)) > 1:
        f = _normalizar(por_plantilla)
        if f:
            return f
    return None


def factores_por_ficha(fichas):
    """`factoresPorFicha`: {id: factor} SOLO de las fichas con factor deducido (las de factor 1 de un grupo con
    factores tambien entran); quien lo lee usa `.get(id, 1)`. La casilla de la ficha manda sobre todo."""
    out = {}
    por_ean = {}
    for f in fichas or []:
        if f.get('es_chase'):
            continue
        k = ean_norm(f.get('ean'))
        if k:
            por_ean.setdefault(k, []).append(f)
    for lista in por_ean.values():
        if len(lista) < 2:
            continue
        activas = [f for f in lista if f.get('activo') is not False]
        if len(activas) >= 2:
            fx = factores_de_grupo([f.get('nombre') for f in activas])
            if fx:
                for f, x in zip(activas, fx):
                    out[f['id']] = x
        for f in lista:
            if f.get('activo') is not False:
                continue
            grupo = activas + [f]
            if len(grupo) < 2:
                continue
            fx = factores_de_grupo([g.get('nombre') for g in grupo])
            if fx:
                out[f['id']] = fx[-1]
    for f in fichas or []:
        if f.get('es_chase'):
            continue
        n = unidades_por_pack_de(f.get('unidades_por_pack'))
        if n is not None:
            out[f['id']] = n
    return out


def factor_por_asin(productos):
    """{asin: factor > 1} de nuestras fichas vivas que son pack, y los avisos (un ASIN en dos fichas vivas con
    factores distintos no se adivina: factor 1 y se dice)."""
    por_id = factores_por_ficha(productos)
    vistos, avisos = {}, []
    for p in productos or []:
        if not _ficha_viva(p):
            continue
        vistos.setdefault(p['asin'], set()).add(por_id.get(p['id'], 1))
    salida = {}
    for asin, fs in vistos.items():
        if len(fs) > 1:
            avisos.append('El ASIN %s está en dos fichas con factores de pack distintos (%s): se valora como 1'
                          % (asin, ', '.join(str(x) for x in sorted(fs))))
        elif next(iter(fs)) > 1:
            salida[asin] = next(iter(fs))
    return salida, avisos


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · LA FOTO, DESDE LA DESCARGA DIARIA
# ═══════════════════════════════════════════════════════════════════════════════
def ean_valido(core, M):
    """Un EAN-13 (o UPC-12) con su digito de control bueno (`_ean_ok` del viejo). 🔑 Regla de OSMA, medida el
    02-oct-2026: 76 articulos con marca y existencias traen EAN de RELLENO (1111111111111 ×69, 9999999999999 ×7,
    de displays y cajas surtidas) y 4 con el control mal; ninguno identifica un producto en Amazon."""
    c = str(core or '')
    if not c.isdigit():
        return False
    if len(c) == 13:
        return M._ean_ok(c)
    if len(c) == 12:
        return M._ean_ok('0' + c)
    return False


def _num(x):
    return None if x is None else float(x)


def _apartado(f, motivo, detalle):
    return {'producto_heo': str(f.get('producto_prov') or ''), 'ean_original': str(f.get('ean_original') or ''),
            'nombre': f.get('nombre') or '', 'marca': (f.get('marca') or '').strip(),
            'precio_catalogo': _num(f.get('precio_unidad')), 'motivo': motivo, 'detalle': detalle,
            'en_oferta': bool(f.get('en_oferta')) if motivo == 'marca_fuera' else None}


def construir_foto(filas, enlaces, M, pct):
    """De la descarga de OSMA a la foto de la pasada, sin perder a nadie: cada articulo sale por UNA puerta previa
    o entra en la foto, y crudo = previas + foto. En este orden:
      1. no disponible (`disponible` de la descarga: stock > 0 o mas de 10.000) → `no_disponible` (se cuenta);
      2. sin marca → `marca_fuera` (se lista: «Sin marca»);
      3. sin EAN → `sin_gtin` (se cuenta);
      4. EAN con forma rara (`regla` de la descarga) o con el digito de control mal → `ean_forma_rara` (se lista);
      5. dos articulos con el mismo EAN → uno: el de un codigo ENLAZADO si lo hay y si no el mas barato (a igual
         precio, el de codigo menor); el otro → `duplicado_proveedor` (se lista).
    `filas`: disp_estado de OSMA vistas en la ultima pasada aplicada; `enlaces`: los de `enlaces_de`; `pct`: el
    porte de `porte_de`. Devuelve (foto, apartados, cuentas)."""
    previas = {p: 0 for p in e2.PUERTAS_PREVIAS}
    apartados, sirven = [], []
    for f in sorted(filas or [], key=lambda x: _clave_codigo(x.get('producto_prov'))):
        if not f.get('disponible'):
            previas['no_disponible'] += 1
            continue
        if not (f.get('marca') or '').strip():
            apartados.append(_apartado(f, 'marca_fuera', 'Sin marca en el catálogo de OSMA'))
            continue
        if not str(f.get('ean_original') or '').strip():
            previas['sin_gtin'] += 1
            continue
        core = str(f.get('ean_core') or '').strip()
        if f.get('regla') or not core:
            apartados.append(_apartado(f, 'ean_forma_rara', 'EAN con forma rara (%s)' % (f.get('ean_original') or '')))
            continue
        if not ean_valido(core, M):
            apartados.append(_apartado(f, 'ean_forma_rara',
                                       'EAN %s con el dígito de control mal: de relleno o mal escrito' % core))
            continue
        sirven.append(f)

    uno = {}
    for f in sirven:
        k = M.norm(f['ean_core'])
        prev = uno.get(k)
        if prev is None:
            uno[k] = f
            continue
        enl_f, enl_p = str(f['producto_prov']) in enlaces, str(prev['producto_prov']) in enlaces
        if enl_f != enl_p:
            gana, pierde = (f, prev) if enl_f else (prev, f)
            porque = 'el código %s está enlazado a nuestra ficha' % gana['producto_prov']
        else:
            pf, pp = f.get('precio_unidad'), prev.get('precio_unidad')
            gana, pierde = (f, prev) if (pf is not None and (pp is None or pf < pp)) else (prev, f)
            porque = 'el más barato'
        uno[k] = gana
        apartados.append(_apartado(pierde, 'duplicado_proveedor', 'Mismo EAN que el código %s: me quedo con %s (%s)'
                                   % (gana['producto_prov'], gana['producto_prov'], porque)))

    foto = []
    for f in sorted(uno.values(), key=lambda x: _clave_codigo(x.get('producto_prov'))):
        core = f['ean_core'].strip()
        foto.append({
            'producto_heo': str(f['producto_prov']), 'ean_original': str(f['ean_original']).strip(), 'ean_core': core,
            'variantes': sorted({M.norm(v) for v in M.variantes_ean(core)} - {''}),
            'codigos_keepa': e2.codigos_para_keepa(core, M),
            'nombre': f.get('nombre') or '', 'marca': f['marca'].strip(), 'categoria': f.get('categoria') or '',
            'precio_catalogo': _num(f.get('precio_unidad')), 'precio_unidad': pa_con_porte(f.get('precio_unidad'), pct),
            'es_caja': False, 'uds_caja': None, 'es_chase': False,
            'en_oferta': bool(f.get('en_oferta')), 'campana': '', 'disponibilidad': '',
            'fin_de_vida': bool(f.get('fin_de_vida')), 'preorder': False, 'imagen': '', 'aviso_caja': None,
            'origen_ean': None, 'aviso_ean': None,
        })
    for m in e2.MOTIVOS_APARTADO:
        previas[m] = sum(1 for a in apartados if a['motivo'] == m)
    n_previas = sum(previas.values())
    cuentas = {'n_crudo': len(filas or []), 'n_foto': len(foto), 'previas': previas, 'n_previas': n_previas,
               'cuadra_previo': len(filas or []) == n_previas + len(foto)}
    return foto, apartados, cuentas


def comprobar_porte(foto, enlaces, puerta):
    """🔴 EL PORTE, UNA SOLA VEZ. Cada fila de OSMA de la puerta comun (`v_escaner_fuente`: ean de la ficha, pa,
    presente) cuyo articulo esta en la foto tiene que traer EL MISMO precio que la foto. Si alguien sumara el porte
    otra vez (o la puerta comun dejara de sumarlo), aqui no cuadra y la pasada falla.
    → (comprobadas, [descuadres]). El articulo de cada fila de la puerta: el de su codigo enlazado (por el EAN de
    la ficha) o el de su mismo EAN."""
    por_clave = {}
    for f in foto:
        por_clave.setdefault(ean_norm(f['ean_core']), []).append(f)
    for codigo, e in enlaces.items():
        for f in foto:
            if f['producto_heo'] == codigo:
                por_clave.setdefault(ean_norm(e['ean_ficha']), []).append(f)
    comprobadas, mal = 0, []
    for v in puerta or []:
        if v.get('es_case') or not v.get('presente'):
            continue
        filas = por_clave.get(ean_norm(v.get('ean')))
        if not filas:
            continue
        comprobadas += 1
        pa = _num(v.get('pa'))
        if not any(f['precio_unidad'] is not None and pa is not None and abs(f['precio_unidad'] - pa) < 0.005
                   for f in filas):
            mal.append('EAN %s: la puerta común dice %s y la foto %s'
                       % (v.get('ean'), v.get('pa'), ', '.join(str(f['precio_unidad']) for f in filas)))
    return comprobadas, mal


def lista_para_keepa_osma(foto, enlaces, M):
    """(AG2) LA lista para el Visualizador → (codigos, eans_fichas):
      · los EAN de la foto (uno por linea, sin repetir, con el rescate de GTIN del viejo como HEO), y
      · el EAN de NUESTRA ficha de cada codigo enlazado QUE ESTA EN LA FOTO (un codigo sin existencias o sin marca
        no tiene a que fila colgarse), detras y solo si no estaba ya (sin ceros delante, como compara Keepa).
    La familia de un codigo (activas, no chase, `enlaces_de`) comparte EAN: es UN EAN por codigo. `eans_fichas`:
    {codigo: EAN de la ficha} de los codigos de la foto que tienen EAN (este o no ya en la lista)."""
    codigos = e2.lista_para_keepa(foto)
    vistos = {M.norm(c) for c in codigos}
    en_foto = {f['producto_heo'] for f in foto}
    eans_fichas = {}
    for c in sorted(enlaces, key=_clave_codigo):
        ean = str(enlaces[c].get('ean_ficha') or '').strip()
        if c not in en_foto or not M.norm(ean):
            continue
        eans_fichas[c] = ean
        if M.norm(ean) not in vistos:
            vistos.add(M.norm(ean))
            codigos.append(ean)
    return codigos, eans_fichas


def _codigos_keepa(fila):
    """Los codigos que Keepa tiene de una ficha (keepa_escaparate: `ean_keepa_crudo` y `upc_keepa`), normalizados."""
    texto = '%s,%s' % (fila.get('ean_keepa_crudo') or '', fila.get('upc_keepa') or '')
    return {k for k in (ean_norm(x) for x in re.split(r'[^0-9]+', texto)) if k}


def fuera_de_keepa(enlaces, eans_fichas, keepa, dominios):
    """(AG2) Nuestras fichas de los codigos de la foto que la lista NO puede traer porque Keepa no conoce su EAN:
    NO se rescatan (Fernando, 02-oct-2026). Se calcula en cada cruce con keepa_escaparate (FOTO: se dice su fecha),
    en los paises del cruce (`dominios`, en minusculas: 'es'). → {'fuera': [(codigo, asin, por que)],
    'sin_dato': [(codigo, asin)], 'fecha': la mas reciente de las filas miradas}.
      · el codigo sin EAN en la ficha → fuera ('la ficha no tiene EAN');
      · la ficha con fila en keepa_escaparate en algun pais del cruce y en NINGUNO lista nuestro EAN → fuera;
      · sin fila en ningun pais del cruce → 'sin_dato' (no se sabe: se dice aparte, no se da por fuera)."""
    por_asin = {}
    for k in keepa or []:
        if str(k.get('dominio') or '').lower() in dominios:
            por_asin.setdefault(k.get('asin'), []).append(k)
    fuera, sin_dato, fechas = [], [], []
    for c in sorted(enlaces, key=_clave_codigo):
        clave = ean_norm(eans_fichas.get(c))
        for a in enlaces[c]['asins']:
            filas = por_asin.get(a) or []
            fechas += [str(k['fecha_foto']) for k in filas if k.get('fecha_foto')]
            if not clave:
                fuera.append((c, a, 'la ficha no tiene EAN'))
            elif not filas:
                sin_dato.append((c, a))
            elif not any(clave in _codigos_keepa(k) for k in filas):
                fuera.append((c, a, 'Keepa no conoce el EAN %s de la ficha (%s)'
                              % (eans_fichas[c], ', '.join(sorted(str(k['dominio']).upper() for k in filas)))))
    return {'fuera': fuera, 'sin_dato': sin_dato, 'fecha': max(fechas) if fechas else None}


def texto_fuera_de_keepa(fk):
    """La linea del Resumen: las fichas que quedan fuera, por codigo, y las que no se saben."""
    if not fk:
        return 'no se ha podido mirar'
    partes = ['%s · %s: %s' % (c, a, porque) for c, a, porque in fk['fuera']] or ['ninguna']
    if fk['sin_dato']:
        partes.append('sin fila en keepa_escaparate (no se sabe): %s'
                      % ', '.join('%s · %s' % (c, a) for c, a in fk['sin_dato']))
    return '%s (keepa_escaparate del %s)' % (' | '.join(partes), fk['fecha'] or '—')


# ═══════════════════════════════════════════════════════════════════════════════
# 4 · EL CRUCE: LAS FICHAS DE CADA ARTICULO
# ═══════════════════════════════════════════════════════════════════════════════
def indice_por_asin(datos_por_ean):
    """{asin: registro} a partir de lo que devuelve `leer_csv_visualizador` (indexado por EAN): el primer
    registro de cada ASIN (el lector recorre los CSV del mas nuevo al mas viejo, como el cruce de HEO)."""
    salida = {}
    for recs in (datos_por_ean or {}).values():
        for r in recs:
            if r.get('asin') and r['asin'] not in salida:
                salida[r['asin']] = r
    return salida


def de_las_fichas(datos, eans_fichas, M):
    """(AG2) Los registros del CSV que llegan por el EAN de una ficha enlazada (por identidad: el lector cuelga el
    mismo registro de cada uno de sus EAN). Son de la fila de ESE codigo, nunca de otro articulo de OSMA."""
    return {id(r) for e in (eans_fichas or {}).values() for r in (datos or {}).get(M.norm(e), [])}


def candidatos_osma(fila, datos, por_asin, enlace, asins_enlazados, M, ean_ficha=None, ids_fichas=frozenset()):
    """Las fichas de UN pais para una fila de la foto → (candidatas, camino, apartadas). (AG2) UN solo CSV, con los
    EAN de OSMA y los de nuestras fichas:
      · fila de un codigo ENLAZADO: las de nuestras fichas que trae el CSV, por cualquiera de sus EAN (`camino`
        'codigo'); lo que traen su EAN de OSMA o el de nuestra ficha con OTRO ASIN se aparta (la misma ficha por los
        dos caminos: una, la del codigo). Si el CSV no trae ninguna de nuestras fichas, las de su EAN de OSMA, como
        cualquier otra fila ('ean_sin_codigo').
      · las demas: las de su EAN ('ean'), menos las de una ficha enlazada y las que llegan por el EAN de una ficha
        enlazada (`ids_fichas`, de `de_las_fichas`), que se apartan: son de la fila de su codigo.
    `datos`: el lector del CSV; `por_asin`: `indice_por_asin` del mismo CSV."""
    por_ean = e2.candidatos(fila, datos or {})
    if enlace:
        por_codigo = [por_asin[a] for a in enlace['asins'] if a in (por_asin or {})]
        if por_codigo:
            por_ficha = e2.candidatos({'variantes': [M.norm(ean_ficha)]}, datos or {}) if M.norm(ean_ficha or '') else []
            vistos, apartadas = set(), []
            for r in por_ean + por_ficha:
                if r.get('asin') and r['asin'] not in enlace['asins'] and r['asin'] not in vistos:
                    vistos.add(r['asin'])
                    apartadas.append(r)
            return por_codigo, 'codigo', apartadas
        return por_ean, 'ean_sin_codigo', []
    fuera = [r for r in por_ean if r.get('asin') in asins_enlazados or id(r) in ids_fichas]
    return [r for r in por_ean if not (r.get('asin') in asins_enlazados or id(r) in ids_fichas)], 'ean', fuera


def decidir_osma(fila, cands_por_pais, caidas_por_pais, params, M, eleccion, compartidas, enlace, factores,
                 caminos=None, apartadas=None):
    """La puerta de UNA fila de OSMA con las reglas de compra del PRO de HEO (`escaner2_motor.decidir`, sin
    tocarlas), y lo propio de OSMA alrededor:
      · fila enlazada: el IVA (y «En mi BD») se leen de NUESTRA ficha (su EAN), no del EAN nuevo de OSMA;
      · si la ficha que sale es uno de nuestros PACKS, el coste es unidades × precio: se decide OTRA VEZ con ese
        coste (la eleccion de ficha no depende del precio: sale la misma, y se comprueba);
      · el detalle dice por donde llego la ficha y lo apartado.
    Devuelve el resultado de `decidir` con 'factor' y 'pa' (el coste con el que se ha calculado)."""
    calc = dict(fila, ean_core=str(enlace['ean_ficha']).strip()) if (enlace and enlace.get('ean_ficha')) else dict(fila)
    r = e2.decidir(calc, cands_por_pais, caidas_por_pais, params, M, eleccion, compartidas)
    factor = (factores or {}).get(r.get('asin'), 1) if r.get('asin') else 1
    pa = fila['precio_unidad']
    if factor > 1 and pa is not None:
        pa = float((_dec(pa) * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        r2 = e2.decidir(dict(calc, precio_unidad=pa), cands_por_pais, caidas_por_pais, params, M, eleccion, compartidas)
        if r2.get('asin') != r.get('asin'):
            raise FalloOsma('la ficha elegida cambia con el coste del pack (%s → %s): no debería'
                            % (r.get('asin'), r2.get('asin')))
        r = r2
    notas = []
    caminos = caminos or {}
    if enlace and 'codigo' in caminos.values():
        notas.append('Por el código %s de OSMA (nuestra ficha %s)' % (fila['producto_heo'], ', '.join(enlace['asins'])))
    elif enlace:
        notas.append('Código %s enlazado, pero el CSV no trae nuestra ficha: decidido por el EAN de OSMA'
                     % fila['producto_heo'])
    if factor > 1:
        notas.append('pack de %d: coste %d × %s € = %s €' % (factor, factor, _coma(fila['precio_unidad']), _coma(pa)))
    aparte = sorted({x.get('asin') for xs in (apartadas or {}).values() for x in xs if x.get('asin')})
    if aparte:
        notas.append('apartadas (de otra ficha enlazada o del EAN nuevo): %s' % ', '.join(aparte))
    if notas:
        r = dict(r, detalle='%s · %s' % (r['detalle'], ' · '.join(notas)))
    return dict(r, factor=factor, pa=pa)


def _coma(x):
    return '—' if x is None else ('%.2f' % x).replace('.', ',')


# ═══════════════════════════════════════════════════════════════════════════════
# 5 · EL EXCEL: EL DEL ESCANER 2 DE HEO, CON UN SOLO AÑADIDO
# ═══════════════════════════════════════════════════════════════════════════════
def foto_para_excel(foto, resultados, enlaces):
    """La foto con la que se escribe la Celda 9, fila a fila igual que la guardada salvo dos cosas, para que las
    formulas vivas de «Análisis» den lo mismo que la decision:
      · si la ficha que sale es uno de nuestros packs, «PA (€)» es el coste del pack (unidades × precio) y el
        nombre lo dice (« · pack de 2 (2 × 1,71 €)»);
      · si la fila es de un codigo enlazado, `ean_core` es el EAN de nuestra ficha (el IVA y «En mi BD» de la
        ficha); la columna «EAN» sigue diciendo el de OSMA."""
    por_foto = {r['foto_id']: r for r in resultados}
    salida = []
    for f in foto:
        r = por_foto.get(f['id']) or {}
        g = dict(f)
        e = enlaces.get(f['producto_heo'])
        if e and e.get('ean_ficha'):
            g['ean_core'] = str(e['ean_ficha']).strip()
        if r.get('factor', 1) > 1:
            g['precio_unidad'] = r['pa']
            g['nombre'] = '%s · pack de %d (%d × %s €)' % (f.get('nombre') or '', r['factor'], r['factor'],
                                                         _coma(f['precio_unidad']))
        salida.append(g)
    return salida


def excel_como_el_viejo_osma(foto_excel, resultados, apartados, M, eleccion=None):
    """Las hojas del viejo con SU codigo (la Celda 9, `escaner2_motor.escribir_celda9`) y la columna «Ficha
    compartida», como el PRO de HEO (`escaner2_motor.excel_como_el_viejo`), con `PROVEEDOR` = 'OSMA': la Celda 9
    solo escribe «Chase_manual» para HEO (son los Funko chase sin ASIN), igual que hacia el escaner viejo con
    OSMA. Y DETRAS de todo, en «Análisis», la columna «No habrá más»."""
    datos = e2.datos_como_el_viejo(foto_excel, resultados, apartados, M, eleccion)
    datos['PROVEEDOR'] = PROVEEDOR
    wb = e2.escribir_celda9(datos, M)
    e2.poner_columna_ficha_compartida(wb, foto_excel, resultados)
    poner_columna_no_habra_mas(wb, foto_excel)
    return wb


def poner_columna_no_habra_mas(wb, foto):
    """«No habrá más» detras de la ultima columna de «Análisis» (columna nueva → al final, SIEMPRE: hay quien lee
    la hoja por letra), fila a fila por EAN, en los descatalogados de OSMA (Discontinued) que aun tienen
    existencias (todos los de la foto lo son: el filtro exige disponible). Alarga la tabla. Devuelve cuantas filas."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import TableColumn
    ws = wb['Análisis']
    cab = [c.value for c in ws[1]]
    i_ean = cab.index('EAN')
    col = len(cab) + 1
    ws.cell(row=1, column=col, value=COLUMNA_NO_HABRA_MAS).font = Font(bold=True)
    ws.column_dimensions[get_column_letter(col)].width = ANCHO_NO_HABRA_MAS
    fdv = {str(f['ean_original']) for f in foto if f.get('fin_de_vida')}
    n = 0
    for fila in range(2, ws.max_row + 1):
        if str(ws.cell(row=fila, column=i_ean + 1).value) in fdv:
            ws.cell(row=fila, column=col, value=TEXTO_NO_HABRA_MAS)
            n += 1
    for tabla in ws.tables.values():
        ini, fin = tabla.ref.split(':')
        tabla.ref = '%s:%s%s' % (ini, get_column_letter(col), re.sub(r'^[A-Z]+', '', fin))
        if tabla.tableColumns:
            tabla.tableColumns.append(TableColumn(id=len(tabla.tableColumns) + 1, name=COLUMNA_NO_HABRA_MAS))
        if tabla.autoFilter is not None:
            tabla.autoFilter.ref = tabla.ref
    return n


COLUMNAS_PUERTAS = ['EAN', 'Nombre', 'Marca', 'Precio compra (€)', 'Puerta', 'Motivo', 'Detalle', 'Caja',
                    'Precio caja (€)', 'EAN de la figura', 'Origen del EAN', 'Aviso del EAN']


def escribir_excel(foto, resultados, apartados, M, info):
    """El Excel del cruce de OSMA: DELANTE las hojas del viejo (`excel_como_el_viejo_osma`), DETRAS las del escaner 2
    con los mismos nombres y columnas que el de HEO (Resumen, Comparación, Varias fichas, Puertas y Puertas previas).
    «Comparación» va con su cabecera y sin filas: el escaner viejo no tiene escaneos de OSMA con que comparar
    (escaner_resultados, medido el 02-oct-2026). Solo lo calculado: aqui no se decide nada. → bytes."""
    from openpyxl.styles import Font
    por_foto = {f['id']: f for f in foto}
    foto_excel = foto_para_excel(foto, resultados, info['enlaces'])
    wb = excel_como_el_viejo_osma(foto_excel, resultados, apartados, M, eleccion=info.get('eleccion'))

    def hoja(nombre, cabecera, filas, anchos=None):
        ws = wb.create_sheet(nombre)
        ws.append(cabecera)
        for c in ws[1]:
            c.font = Font(bold=True)
        for fila in filas:
            ws.append(fila)
        for letra, ancho in (anchos or {}).items():
            ws.column_dimensions[letra].width = ancho
        ws.freeze_panes = 'A2'
        return ws

    p = info['params']
    po = info.get('porte') or {}
    filas_res = [['Pasada', info['pasada']], ['Cruce', info['cruce']],
                 ['Proveedor', 'OSMA · artículos con marca y existencias'],
                 ['Descarga de OSMA', '%s (pasada %s)' % (info.get('descarga_en') or '—', info.get('disp_pasada') or '—')],
                 ['Porte en el precio (el de la puerta común, una sola vez)',
                  ('%s € de la factura %s (%s) ÷ pedido previsto %s € = %s'
                   % (_coma(po.get('gastos_envio')), po.get('factura') or '—', po.get('fecha') or '—',
                      _coma(po.get('pedido_previsto')), texto_pct(_dec(po['pct']) if po.get('pct') is not None else None)))
                  if po.get('pct') is not None else 'sin porte (sin pedido previsto o sin factura con porte)'],
                 ['Umbral de caídas (30 días)', '%s (> %d)' % (e2.texto_corte(p['umbral']), p['umbral'])],
                 ['Fichas compartidas (productos de la lista, por país)',
                  ' · '.join('%s %d' % (k, n) for k, n in (info.get('n_compartidas') or {}).items()) or '—'],
                 ['Países del filtro de ventas', ', '.join(p['paises_filtro'])],
                 ['Países que se calculan (si traen CSV)', ', '.join(p['paises_calculo'])],
                 ['Países con CSV', ', '.join(info['usados'])],
                 ['Códigos enlazados en la foto (el EAN de nuestra ficha va en la lista)', '%d códigos · %d EAN de '
                  'nuestras fichas (%d que no traía ya OSMA)'
                  % (len(info.get('enlaces_foto') or []), len(info.get('eans_fichas') or {}),
                     info.get('n_eans_fichas_nuevos') or 0)],
                 ['Fichas nuestras que quedan fuera: Keepa no conoce su EAN (no se rescatan)',
                  texto_fuera_de_keepa(info.get('fuera_keepa'))],
                 ['Packs nuestros valorados como unidades × precio', info.get('n_packs', 0)],
                 ['Catálogo de OSMA (descarga)', info['n_crudo']]]
    filas_res += [['Puerta previa · %s' % NOMBRE_PREVIA[x], info['previas'][x]] for x in e2.PUERTAS_PREVIAS]
    filas_res += [['Entradas (filas de la foto)', info['n_entradas']]]
    filas_res += [['Puerta %s · %s' % (x, e2.NOMBRE_PUERTA[x]), info['n_bd'][x]] for x in e2.PUERTAS]
    filas_res += [['Puertas previas + suma de puertas', sum(info['previas'].values()) + sum(info['n_bd'].values())],
                  ['Cuadra', 'SÍ' if info['cuadra'] else 'NO'],
                  ['Comparación con el escáner viejo', 'no se hace: el viejo no tiene escaneos de OSMA']]
    filas_res += [['CSV', '%s · %s · %s filas%s%s' % (
        f['nombre'], f.get('pais') or '¿?', f.get('filas') or 0,
        '' if f.get('usado') else ' · NO USADO', (' · ' + f['error']) if f.get('error') else '')]
        for f in info['ficheros']]
    filas_res += [['Aviso', a] for a in info['avisos']]
    hoja('Resumen', ['Qué', 'Valor'], filas_res, {'A': 44, 'B': 90})

    hoja('Comparación', ['EAN', 'Nombre', 'Categoría', 'Viejo', 'País viejo', 'Fecha viejo (UTC)', 'Excel viejo',
                         'Puerta nuevo', 'Nuevo', 'País nuevo', 'Fecha nuevo (UTC)', 'Diferencia de criterio',
                         'Explicación'], [], {'A': 15, 'B': 50, 'C': 16, 'G': 36, 'M': 110})

    varias = []
    for res in resultados:
        if res['puerta'] == 'b':
            f = por_foto[res['foto_id']]
            for fi in res['fichas']:
                varias.append([f['ean_original'], f['nombre'], fi['pais'], fi['asin'], fi['titulo'], fi['rank'],
                               fi['caidas_30d'], fi['precio_venta']])
    hoja('Varias fichas', ['EAN', 'Nombre OSMA', 'País', 'ASIN', 'Título Amazon', 'Puesto', 'Caídas 30 d',
                           'Precio venta (€)'], varias, {'A': 15, 'B': 50, 'E': 60})

    hoja('Puertas', COLUMNAS_PUERTAS,
         [[por_foto[r['foto_id']]['ean_original'], por_foto[r['foto_id']]['nombre'], por_foto[r['foto_id']]['marca'],
           r.get('pa', por_foto[r['foto_id']]['precio_unidad']), '%s · %s' % (r['puerta'], e2.NOMBRE_PUERTA[r['puerta']]),
           r['motivo'], r['detalle'], None, None, None, None, None] for r in resultados],
         {'A': 15, 'B': 55, 'C': 16, 'E': 24, 'F': 16, 'G': 70, 'H': 26})

    hoja('Puertas previas', ['EAN tal como vino', 'Nombre', 'Marca', 'Precio catálogo (€)', 'Puerta previa', 'Detalle'],
         [[a['ean_original'], a['nombre'], a['marca'], a['precio_catalogo'],
           NOMBRE_PREVIA.get(a['motivo'], a['motivo']), a['detalle']] for a in apartados],
         {'A': 18, 'B': 55, 'C': 16, 'E': 32, 'F': 80})
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def ruta_excel(pasada, cruce, sello):
    """`osma/<pasada>/<cruce>/Escaner2_OSMA_<AAAAMMDD_HHMM>.xlsx`: la forma que admite escaner2_cruce.ruta_excel
    desde la migracion del encargo AG (v2)."""
    return '%s/%s/%s/Escaner2_OSMA_%s.xlsx' % (CARPETA, pasada, cruce, sello)

