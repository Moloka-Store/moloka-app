# -*- coding: utf-8 -*-
"""ESCANER 2 · ESCANEO PRO DE BEMS · LA PARTE PURA (encargo BE4, 10-oct-2026; pieza c del plano del parte BE1)

QUE ES. El calculo del Escaneo PRO de BEMS, sin red y sin base: la foto de la pasada desde la FOTO DE DISPONIBILIDAD
de BEMS (disp_estado, que deja escaner2_bems_disponibilidad.py desde el CSV que Fernando sube a mano, encargo BE2), la
lista para el Visualizador y el Excel. La red vive en los dos programas que lo usan:
  · escaner2_bems_barrido.py (workflow escaner2-bems-barrido.yml): de la foto a la pasada y la lista.
  · escaner2_bems_cruce.py   (workflow escaner2-bems-cruce.yml):   los 4 CSV, las puertas y el Excel.

🔑 CADA ESCANER, A LA MEDIDA DE SU PROVEEDOR (Fernando: «Quiero que cada escaner sea personalizado a cada proveedor»):
   leer y filtrar es de BEMS y vive aqui. Lo que se REUTILIZA sin tocarlo son las REGLAS DE COMPRA del PRO de HEO
   (`escaner2_motor.decidir`, con el corte y los paises de escaner2_parametros: BEMS = 6 y ES·IT·FR·DE) y su Excel (la
   Celda 9 del viejo con «Ventas», la columna «Ficha compartida» y las hojas del escaner 2 en el MISMO orden).

LO PROPIO DE BEMS (decidido por Fernando el 10-oct-2026, y medido en el parte BE1):
  1. LA FOTO SALE DE disp_estado (las filas vistas en la ULTIMA pasada APLICADA de BEMS). Nada de la web: BEMS no
     tiene API y el CSV lo baja Fernando a mano («hacemos solo el escaner pro que yo descargue manualmente el csv»).
  2. SOLO LO QUE TIENE STOCK YA: `disponible` (= STOCK > 0: «Solo quiero ver lo que esta disponible con stock ya»).
  3. SIN REGLA DE CHASE: en BEMS ningun Funko se aparta por «chase» en el titulo («Es la normal, si compras 6 pues te
     vendra 5 normales y un chase»). La puerta previa `chase_suelto` sale siempre a 0.
  4. EL PRECIO, EL PA DEL CSV: PA = `precio_unidad` de la foto (el PA sin IVA), sin tramos ni MULTI («habra que
     calcular con el precio que salga») y porte 0 («Pedido minimo 400 euros sin gasto de envio»). Expositores y blind
     boxes son UN articulo a su precio de caja, sin dividir: es_caja false siempre.
  5. SIN PRECIO DE COMPRA (vacio o 0), FUERA: un PA de 0 daria un COMPRAR falso. Va a la puerta previa
     `estado_no_servible`, que en BEMS se llama «Sin precio de compra», listada (BE1: 4 filas sin PA, ninguna con stock).
  6. UNA FILA POR EAN: un EAN con varias REF (BE1: 1 de verdad, un Funko con una ficha vieja) → la de menor PA; a
     igualdad, la REF menor. Las otras, a `duplicado_proveedor`, listadas.
  7. EL CRUDO SON LOS ARTICULOS DEL CSV, no sus lineas: la pasada de disponibilidad ya se quedo UNA de cada linea
     identica repetida (BE1: 2). crudo = disp_pasada.n_leidas, y se comprueba que n_crudo (las lineas) = n_leidas +
     n_duplicados. El Excel dice las dos cifras.
  8. EL DIA DEL CSV: la foto es la del CSV que se subio, y ese CSV tiene fecha (la de su nombre, en
     disp_pasada.fichero_fecha_max). Si no es de hoy, el registro y el Excel lo dicen («CSV del …»).
  9. MODOS: 'marcas' = la lista fija de BEMS (`escaner2_parametros.marcas_fijas`: Funko, Bandai Model Kit y Pyramid),
     con la regla del barrido de marcas de siempre (el nombre de la lista DENTRO del de la fila, sin mayusculas: la
     misma que pinta «Tus marcas» en la v2, `casaConFijas`); 'todas' (tambien las sin fabricante); 'elegidas' (las del
     selector, coincidencia EXACTA, como HEO). BEMS no tiene fila en reglas_director: no se lee.
 10. EL EXCEL, EL DEL PRO DE HEO, mismo formato y orden, SIN columnas nuevas: el precio es por unidad y no hay escalon
     ni MOQ que enseñar. Sin «Chase_manual» (es de HEO) ni comparacion con el viejo.

🔴 REPO PUBLICO: aqui no hay ni un precio ni un EAN reales; los del banco son inventados (Seguridad 21).
"""
import io
from datetime import date

import escaner2_motor as e2

PROVEEDOR = 'BEMS'
CARPETA = 'bems'
NOMBRE = 'BEMS'
MODOS = ('marcas', 'todas', 'elegidas')

# Los nombres de las puertas previas EN BEMS (los mismos que NOMBRE_PREVIA_BEMS de la v2). Las ocho de siempre
# (crudo = previas + foto); BEMS usa cinco: `chase_funko`, `sin_gtin` y `chase_suelto` salen a 0.
NOMBRE_PREVIA = dict(e2.NOMBRE_PUERTA_PREVIA,
                     sin_gtin='Sin EAN',
                     no_disponible='Sin stock hoy',
                     marca_fuera='Marca fuera de la lista fija de BEMS',
                     estado_no_servible='Sin precio de compra',
                     chase_suelto='Chase suelto (en BEMS no se aparta ninguno)',
                     ean_forma_rara='EAN vacío o con forma rara',
                     duplicado_proveedor='Mismo EAN que otra referencia de BEMS, más cara')


class FalloBEMS(Exception):
    """Algo que impide seguir: la pasada o el cruce quedan 'fallida' con este motivo (privado, en la base)."""


def nombre_previa(p, modo):
    """El nombre de una puerta previa EN SU PASADA: en el modo «elegidas» la marca que se cae es «no elegida»."""
    if p == 'marca_fuera' and modo == 'elegidas':
        return e2.NOMBRE_MARCA_NO_ELEGIDA
    return NOMBRE_PREVIA[p]


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · EL FILTRO DE MARCA, POR MODO
# ═══════════════════════════════════════════════════════════════════════════════
def filtro_marca(modo, marcas_fijas=None, elegidas=None):
    """(quiere, info) para el modo:
      · 'marcas'   · la lista fija de BEMS (`escaner2_parametros.marcas_fijas`, solo lectura) con la regla de siempre:
                     el nombre de la lista CONTENIDO en el de la fila, sin distinguir mayusculas (`casaConFijas` de la
                     v2, `_pasa_filtros` del viejo). Ojo: «Funko» casa tambien con «Funko Tees».
      · 'todas'    · todas (las sin fabricante, tambien);
      · 'elegidas' · las del selector de la v2, COINCIDENCIA EXACTA (`escaner2_motor.clave_marca`), como HEO.
    `quiere(marca)` → bool. `info` lleva las marcas que se guardan en la pasada (None en 'todas')."""
    if modo == 'todas':
        return (lambda _m: True), {'marcas_reales': None}
    if modo == 'marcas':
        lista = [str(m).strip() for m in (marcas_fijas or []) if str(m or '').strip()]
        if not lista:
            raise FalloBEMS('la fila BEMS de escaner2_parametros no trae marcas_fijas: no se sabe qué barrer')
        bajas = [m.lower() for m in lista]
        return (lambda m: any(b in str(m or '').lower() for b in bajas)), {'marcas_reales': lista}
    if modo == 'elegidas':
        claves = frozenset(e2.clave_marca(m) for m in (elegidas or []))
        if not claves:
            raise FalloBEMS('modo elegidas sin ninguna marca')
        return (lambda m: e2.clave_marca(m) in claves), {'marcas_reales': list(elegidas)}
    raise FalloBEMS('modo de barrido desconocido: %r' % (modo,))


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · LA FOTO DE LA PASADA, DESDE LA FOTO DE DISPONIBILIDAD
# ═══════════════════════════════════════════════════════════════════════════════
def _num(x):
    return None if x is None else float(x)


def _dia(x):
    """El dia de una fecha de la base ('2026-10-10' o con hora), o None."""
    if x is None or x == '':
        return None
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def texto_dia(d):
    """10-10-2026 (el dia como lo lee Fernando)."""
    return '—' if d is None else d.strftime('%d-%m-%Y')


def aviso_fecha_csv(fecha_csv, hoy):
    """None si el CSV de la foto es de `hoy`; si no, la frase que lo dice (el dato es de ese dia, no de hoy)."""
    fecha_csv, hoy = _dia(fecha_csv), _dia(hoy)
    if fecha_csv is None:
        return 'La foto de BEMS no dice de qué día es su CSV: los precios y el stock pueden ser viejos'
    if fecha_csv == hoy:
        return None
    dias = (hoy - fecha_csv).days
    hace = ('ayer' if dias == 1 else 'hace %d días' % dias) if dias > 0 else 'con fecha posterior a hoy'
    return ('La foto de BEMS es del CSV del %s (%s), no de hoy: los precios y el stock son los de ese día'
            % (texto_dia(fecha_csv), hace))


def _apartado(f, motivo, detalle):
    return {'producto_heo': str(f.get('producto_prov') or ''), 'ean_original': str(f.get('ean_original') or ''),
            'nombre': f.get('nombre') or '', 'marca': (f.get('marca') or '').strip(),
            'precio_catalogo': _num(f.get('precio_catalogo')), 'motivo': motivo, 'detalle': detalle, 'en_oferta': None}


def construir_foto(filas, quiere_marca, M, n_crudo, n_sin_gtin, modo='marcas'):
    """De la foto de disponibilidad de BEMS a la foto de la pasada, sin perder a nadie: cada fila sale por UNA puerta
    previa o entra en la foto, y crudo (los articulos del CSV) = previas + foto. En este orden:
      1. sin stock hoy (`disponible` falso) → `no_disponible` (se cuenta);
      2. marca que no pasa el filtro del modo → `marca_fuera` (se lista);
      3. EAN vacio o que no son 12 o 13 cifras, o con una `regla` de la foto → `ean_forma_rara` (se lista);
      4. sin precio de compra (vacio o 0) → `estado_no_servible` (se lista);
      5. dos REF con el mismo EAN → la de menor PA (a igualdad, la REF menor); la otra → `duplicado_proveedor`.
    Sin regla de chase (3 de la cabecera). `filas`: disp_estado de BEMS vistas en la ultima pasada aplicada;
    `n_crudo` y `n_sin_gtin`: los articulos de esa pasada (n_leidas) y los sin EAN que no entraron en ella (BE2 sube
    todas las filas, tambien las sin EAN, con `regla = 'ean_forma_rara'`: 0). Devuelve (foto, apartados, cuentas)."""
    previas = {p: 0 for p in e2.PUERTAS_PREVIAS}
    previas['sin_gtin'] = n_sin_gtin
    apartados, sirven = [], []
    no_elegida = modo == 'elegidas'
    for f in sorted(filas or [], key=lambda x: str(x.get('producto_prov') or '')):
        if not f.get('disponible'):
            previas['no_disponible'] += 1
            continue
        if not quiere_marca(f.get('marca')):
            apartados.append(_apartado(f, 'marca_fuera', ('Marca %r no elegida' if no_elegida
                                                          else 'Marca %r fuera de la lista fija de BEMS')
                                       % ((f.get('marca') or '').strip(),)))
            continue
        regla = f.get('regla')
        core = str(f.get('ean_core') or '').strip()
        if regla or not core.isdigit() or len(core) not in (12, 13):
            apartados.append(_apartado(f, 'ean_forma_rara', 'EAN vacío o con forma rara (%s%s)'
                                       % (str(f.get('ean_original') or '').strip() or 'vacío',
                                          ', regla %s' % regla if regla else '')))
            continue
        pa = _num(f.get('precio_unidad'))
        if pa is None or pa <= 0:
            apartados.append(_apartado(f, 'estado_no_servible', 'Sin precio de compra (PA) en el CSV de BEMS'))
            continue
        sirven.append((f, pa))

    uno = {}
    for f, pa in sirven:
        k = M.norm(str(f['ean_core']).strip())
        prev = uno.get(k)
        if prev is None:
            uno[k] = (f, pa)
            continue
        gana, pierde = ((f, pa), prev) if (pa, str(f.get('producto_prov'))) < (prev[1], str(prev[0].get('producto_prov'))) \
            else (prev, (f, pa))
        uno[k] = gana
        apartados.append(_apartado(pierde[0], 'duplicado_proveedor', 'Mismo EAN que la referencia %s de BEMS: me quedo '
                                   'con la más barata (%s frente a %s)' % (gana[0].get('producto_prov'), gana[1], pierde[1])))

    foto = []
    for f, pa in sorted(uno.values(), key=lambda x: str(x[0].get('producto_prov') or '')):
        core = str(f['ean_core']).strip()
        variantes = sorted({M.norm(v) for v in M.variantes_ean(core)} - {''})
        foto.append({
            'producto_heo': str(f.get('producto_prov') or ''),
            'ean_original': str(f.get('ean_original') or '').strip() or core,
            'ean_core': core, 'variantes': variantes, 'codigos_keepa': e2.codigos_para_keepa(core, M),
            'nombre': f.get('nombre') or '', 'marca': (f.get('marca') or '').strip(),
            'categoria': f.get('categoria') or '',
            # 🔑 precio_unidad = el PA del CSV (sin IVA, por articulo): con el decide `escaner2_motor.decidir`.
            'precio_catalogo': _num(f.get('precio_catalogo')), 'precio_unidad': pa,
            'es_caja': False, 'uds_caja': None, 'es_chase': False, 'en_oferta': False, 'campana': None,
            'disponibilidad': None, 'fin_de_vida': None, 'preorder': False, 'imagen': None,
            'aviso_caja': None, 'origen_ean': None, 'aviso_ean': None,
        })

    for m in e2.MOTIVOS_APARTADO:
        previas[m] = sum(1 for a in apartados if a['motivo'] == m)
    cuentas = {'n_crudo': n_crudo, 'n_filas': len(filas or []), 'n_foto': len(foto), 'previas': previas}
    cuentas.update(cuadre_previo(cuentas))
    return foto, apartados, cuentas


def cuadre_previo(cuentas):
    """🔴 crudo = previas + foto, y el crudo son los articulos del CSV: filas de la foto de disponibilidad + las sin EAN
    que no esten en ella (en BEMS, 0). Un recuento que falta (None) NO es un cero."""
    previas = cuentas['previas']
    faltan = [p for p in e2.PUERTAS_PREVIAS if previas.get(p) is None]
    if cuentas.get('n_crudo') is None:
        faltan.insert(0, 'crudo')
    if faltan:
        return {'n_previas': None, 'cuadra_previo': False, 'motivo_previo': 'sin recuento de: ' + ', '.join(faltan)}
    n_previas = sum(previas[p] for p in e2.PUERTAS_PREVIAS)
    if cuentas['n_filas'] + previas['sin_gtin'] != cuentas['n_crudo']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'el CSV tenía %d artículos y la foto de disponibilidad trae %d + %d sin EAN'
                                 % (cuentas['n_crudo'], cuentas['n_filas'], previas['sin_gtin'])}
    if cuentas['n_crudo'] != n_previas + cuentas['n_foto']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'catálogo crudo %d ≠ puertas previas %d + foto %d'
                                 % (cuentas['n_crudo'], n_previas, cuentas['n_foto'])}
    return {'n_previas': n_previas, 'cuadra_previo': True, 'motivo_previo': None}


def corpus_cotejo(foto, apartados):
    """Los nombres con que la regla del viejo mide sus palabras distintivas al elegir entre varias fichas: los de la
    foto y los de lo disponible apartado por MARCA (que la eleccion no dependa de las marcas elegidas)."""
    nombres = [f.get('nombre') or '' for f in foto]
    nombres += [a.get('nombre') or '' for a in apartados if a.get('motivo') == 'marca_fuera']
    return nombres


def ruta_lista(pasada):
    return '%s/%s/eans.txt' % (CARPETA, pasada)


def ruta_excel(pasada, cruce, sello):
    """`bems/<pasada>/<cruce>/Escaner2_BEMS_<AAAAMMDD_HHMM>.xlsx`: la forma que admite escaner2_cruce.ruta_excel desde
    la migracion de la v2 de este encargo."""
    return '%s/%s/%s/Escaner2_BEMS_%s.xlsx' % (CARPETA, pasada, cruce, sello)


def nombre_modo(modo):
    """Como se llama el modo de la pasada en el Excel (el mismo texto que el cruce de HEO)."""
    return {'todas': 'todas las marcas', 'elegidas': 'marcas elegidas'}.get(modo or 'marcas', 'marcas de siempre')


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · EL EXCEL: EL DEL PRO DE HEO, TAL CUAL
# ═══════════════════════════════════════════════════════════════════════════════
COLUMNAS_CAJA = ['Caja', 'Precio caja (€)', 'EAN de la figura', 'Origen del EAN', 'Aviso del EAN']


def escribir_excel(foto, resultados, apartados, M, info):
    """El Excel del cruce de BEMS: el del PRO de HEO (`escaner2_heo_cruce.escribir_excel`), mismo formato y orden.
    DELANTE las hojas del viejo (la Celda 9: Análisis con «Ventas», Descartados, Ambiguos, Sin_rank, Precio por lote),
    con «Ficha compartida» al final de «Análisis»; DETRAS Resumen, Comparación (vacía), Varias fichas, Puertas y
    Puertas previas. Solo lo calculado: aqui no se decide nada. → bytes."""
    from openpyxl.styles import Font
    por_foto = {f['id']: f for f in foto}
    datos = e2.datos_como_el_viejo(foto, resultados, apartados, M, eleccion=info.get('eleccion'))
    # Sin «Chase_manual» (solo con PROVEEDOR == 'HEO').
    datos['PROVEEDOR'] = PROVEEDOR
    wb = e2.escribir_celda9(datos, M)
    e2.poner_columna_ficha_compartida(wb, foto, resultados)

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
    modo = info.get('modo')
    filas_res = [['Pasada', info['pasada']], ['Cruce', info['cruce']], ['Modo del barrido', nombre_modo(modo)]]
    if modo == 'elegidas':
        filas_res += [['Marcas elegidas', ', '.join(info.get('marcas') or []) or '(ninguna)']]
    elif modo == 'marcas':
        filas_res += [['Marcas de la lista fija', ', '.join(info.get('marcas') or []) or '(ninguna)']]
    filas_res += [['CSV de BEMS (el día del fichero)', info.get('fecha_csv') or '—'],
                  ['Foto de BEMS (pasada de disponibilidad)', info.get('foto') or '—'],
                  ['Precio de compra (PA)', 'el PA del CSV de BEMS, sin IVA y por artículo (un expositor o una blind '
                                            'box, a su precio de caja, sin dividir); sin tramos ni MULTI, porte 0'],
                  ['Umbral de caídas (30 días)', '%s (> %d)' % (e2.texto_corte(p['umbral']), p['umbral'])],
                  ['Fichas compartidas (productos de la lista, por país)',
                   ' · '.join('%s %d' % (k, n) for k, n in (info.get('n_compartidas') or {}).items()) or '—'],
                  ['Países del filtro de ventas', ', '.join(p['paises_filtro'])],
                  ['Países que se calculan (si traen CSV)', ', '.join(p['paises_calculo'])],
                  ['Países con CSV', ', '.join(info['usados'])],
                  ['Líneas del CSV de BEMS (con las repetidas idénticas)', info.get('n_lineas_csv', '—')],
                  ['Catálogo crudo de BEMS (artículos distintos del CSV)', info['n_crudo']]]
    filas_res += [['Puerta previa · %s' % nombre_previa(x, modo), info['previas'][x]] for x in e2.PUERTAS_PREVIAS]
    filas_res += [['Entradas (filas de la foto: un EAN, su referencia más barata)', info['n_entradas']]]
    filas_res += [['Puerta %s · %s' % (x, e2.NOMBRE_PUERTA[x]), info['n_bd'][x]] for x in e2.PUERTAS]
    filas_res += [['Puertas previas + suma de puertas', sum(info['previas'].values()) + sum(info['n_bd'].values())],
                  ['Cuadra', 'SÍ' if info['cuadra'] else 'NO'],
                  ['Comparación con el escáner viejo', 'no se hace aquí']]
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
    hoja('Varias fichas', ['EAN', 'Nombre BEMS', 'País', 'ASIN', 'Título Amazon', 'Puesto', 'Caídas 30 d',
                           'Precio venta (€)'], varias, {'A': 15, 'B': 50, 'E': 60})

    # Las cinco columnas de caja del PRO de HEO, vacias: en BEMS una caja es un articulo (mismo formato que el de HEO).
    hoja('Puertas', ['EAN', 'Nombre', 'Marca', 'Precio compra (€)', 'Puerta', 'Motivo', 'Detalle'] + COLUMNAS_CAJA,
         [[por_foto[r['foto_id']]['ean_original'], por_foto[r['foto_id']]['nombre'], por_foto[r['foto_id']]['marca'],
           por_foto[r['foto_id']]['precio_unidad'], '%s · %s' % (r['puerta'], e2.NOMBRE_PUERTA[r['puerta']]),
           r['motivo'], r['detalle']] + [None] * len(COLUMNAS_CAJA) for r in resultados],
         {'A': 15, 'B': 55, 'C': 16, 'E': 24, 'F': 16, 'G': 70, 'H': 26})

    hoja('Puertas previas', ['EAN tal como vino', 'Nombre', 'Marca', 'Precio catálogo (€)', 'Puerta previa', 'Detalle'],
         [[a['ean_original'], a['nombre'], a['marca'], a['precio_catalogo'],
           nombre_previa(a['motivo'], modo) if a['motivo'] in NOMBRE_PREVIA else a['motivo'], a['detalle']]
          for a in apartados],
         {'A': 18, 'B': 55, 'C': 16, 'E': 32, 'F': 80})
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()
