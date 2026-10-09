# -*- coding: utf-8 -*-
"""ESCANER 2 · ESCANEO PRO DE DBLINE · LA PARTE PURA (encargo DB3, 09-oct-2026; pieza b del plano del parte DB1)

QUE ES. El calculo del Escaneo PRO de DBLine, sin red y sin base: la foto de la pasada desde la FOTO DE DISPONIBILIDAD
de DBLine (disp_estado, que deja escaner2_dbline_disponibilidad.py, encargo DB2), la lista para el Visualizador y el
Excel. La red vive en los dos programas que lo usan:
  · escaner2_dbline_barrido.py (workflow escaner2-dbline-barrido.yml): de la foto a la pasada y la lista.
  · escaner2_dbline_cruce.py   (workflow escaner2-dbline-cruce.yml):   los 4 CSV, las puertas y el Excel.

🔑 CADA ESCANER, A LA MEDIDA DE SU PROVEEDOR (Fernando: «Quiero que cada escaner sea personalizado a cada proveedor»):
   leer y filtrar es de DBLine y vive aqui. Lo que se REUTILIZA sin tocarlo son las REGLAS DE COMPRA del PRO de HEO
   (`escaner2_motor.decidir`, con el corte y los paises de escaner2_parametros: DBLINE = 6 y ES·IT·FR·DE, la fila de
   OcioStock con otro proveedor) y su Excel (la Celda 9 del viejo con «Ventas», la columna «Ficha compartida» y las
   hojas del escaner 2 en el MISMO orden).

LO PROPIO DE DBLINE (decidido por Fernando, 9-oct-2026, y medido en el parte DB1):
  1. LA FOTO SALE DE disp_estado (las filas vistas en la ultima pasada APLICADA). Nada de la web.
  2. SOLO LO QUE SE PUEDE COMPRAR HOY: `disponible` (= Disponibili > 0: «Solo quiero ver lo que este disponible para
     comprar hoy»). La preventa (PRENOTAZIONE) nunca trae unidades (975 de 975 sin unidades, DB1 punto 3): no hay
     regla aparte, se va por «sin unidades». Lo que tiene unidades entra se llame como se llame (TELEFONARE, NEW con
     fecha futura: «si que entren»).
  3. CHASE: en DBLine no hay chase sueltos; «w/Chase» es la figura normal y entra como tal. Si la foto marca uno
     (`regla = 'chase_suelto'`, la guarda de DB2: hoy 0), fuera.
  4. EL PRECIO, EL VIGENTE Y POR UNIDAD («Calcula con el precio vigente de compra en cada momento»): PA =
     `precio_unidad` de la foto (Prezzo, o el de promo si su fin es hoy o despues). 🔴 La promo solo hasta su fin:
     si la foto la dio por vigente pero su `fin_oferta` ya ha pasado el dia del barrido, se usa `precio_catalogo`
     (Prezzo) y se cuenta. Sin escalones, sin el 1 % de transferencia, sin porte, sin cajas, sin MOQ.
  5. SIN PRECIO DE COMPRA (vacio o 0: DB1 vio 4 filas con Prezzo a 0), FUERA: un PA de 0 daria un COMPRAR falso. Va a
     la puerta previa `estado_no_servible`, que en DBLine se llama «Sin precio de compra», listada.
  6. UNA FILA POR EAN BASE: DBLine tiene 4 EAN con dos codigos (DB1 1.3). Gana el de menor PA; a igualdad, el codigo
     menor. El otro, a `duplicado_proveedor`, listado.
  7. EL EXCEL, EL DEL PRO DE HEO, mismo formato y orden, SIN columnas nuevas («yo necesito exactamente el mismo
     formato de excel del escaner antiguo»): el precio es por unidad y no hay escalon ni MOQ que enseñar. Sin
     «Chase_manual» (es de HEO: el viejo de DBLine tampoco la escribe) ni comparacion con el viejo (pieza d, aparte).

🔴 REPO PUBLICO: aqui no hay ni un precio ni un EAN reales; los del banco son inventados (Seguridad 21).
"""
import io
from datetime import date

import escaner2_motor as e2

PROVEEDOR = 'DBLINE'
CARPETA = 'dbline'
NOMBRE = 'DBLine'
MODOS = ('marcas', 'todas', 'elegidas')

# Los nombres de las puertas previas EN DBLINE (los mismos que NOMBRE_PREVIA_DBLINE de la v2). Las ocho de siempre
# (crudo = previas + foto); DBLine usa siete y `chase_funko` sale a 0.
NOMBRE_PREVIA = dict(e2.NOMBRE_PUERTA_PREVIA,
                     sin_gtin='Sin EAN',
                     no_disponible='Sin unidades hoy',
                     marca_fuera='Marca fuera de la lista del director',
                     estado_no_servible='Sin precio de compra',
                     chase_suelto='Chase suelto (no se compra)',
                     ean_forma_rara='EAN vacío o con forma rara',
                     duplicado_proveedor='Mismo EAN que otro código de DBLine, más caro')


class FalloDBLine(Exception):
    """Algo que impide seguir: la pasada o el cruce quedan 'fallida' con este motivo (privado, en la base)."""


def nombre_previa(p, modo):
    """El nombre de una puerta previa EN SU PASADA: en el modo «elegidas» la marca que se cae es «no elegida»."""
    if p == 'marca_fuera' and modo == 'elegidas':
        return e2.NOMBRE_MARCA_NO_ELEGIDA
    return NOMBRE_PREVIA[p]


# ═══════════════════════════════════════════════════════════════════════════════
# 1 · EL FILTRO DE MARCA, POR MODO
# ═══════════════════════════════════════════════════════════════════════════════
def filtro_marca(modo, marcas_director=None, elegidas=None):
    """(quiere, info) para el modo:
      · 'marcas'   · las de `reglas_director` (fila DBLINE, solo lectura: hoy Funko y Pyramid) con la regla del viejo:
                     el nombre de la marca de la regla CONTENIDO en el de la fila, sin distinguir mayusculas
                     (`m.lower() in marca`, `_pasa_filtros` de moloka_escaner_nube.py);
      · 'todas'    · todas, sin leer reglas_director (las sin marca, tambien);
      · 'elegidas' · las del selector de la v2, COINCIDENCIA EXACTA (`escaner2_motor.clave_marca`), como HEO.
    `quiere(marca)` → bool. `info` lleva las marcas que se guardan en la pasada (None en 'todas')."""
    if modo == 'todas':
        return (lambda _m: True), {'marcas_reales': None}
    if modo == 'marcas':
        lista = [str(m).strip() for m in (marcas_director or []) if str(m or '').strip()]
        if not lista:
            raise FalloDBLine('la fila DBLINE de reglas_director no trae marcas: no se sabe qué barrer')
        bajas = [m.lower() for m in lista]
        return (lambda m: any(b in str(m or '').lower() for b in bajas)), {'marcas_reales': lista}
    if modo == 'elegidas':
        claves = frozenset(e2.clave_marca(m) for m in (elegidas or []))
        if not claves:
            raise FalloDBLine('modo elegidas sin ninguna marca')
        return (lambda m: e2.clave_marca(m) in claves), {'marcas_reales': list(elegidas)}
    raise FalloDBLine('modo de barrido desconocido: %r' % (modo,))


# ═══════════════════════════════════════════════════════════════════════════════
# 2 · LA FOTO DE LA PASADA, DESDE LA FOTO DE DISPONIBILIDAD
# ═══════════════════════════════════════════════════════════════════════════════
def _num(x):
    return None if x is None else float(x)


def _dia(x):
    """El dia de una fecha de la base ('2026-10-15' o con hora), o None."""
    if x is None or x == '':
        return None
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def precio_vigente(f, hoy):
    """(PA, promo_vigente, caducada_desde_la_foto) de una fila de la foto, el dia `hoy`. La foto ya trae el vigente en
    `precio_unidad` (DB2, regla 4); aqui solo se corrige la promo que la foto dio por buena y cuyo fin ya ha pasado
    (la foto puede ser de un dia anterior): entonces vale Prezzo (`precio_catalogo`)."""
    unidad, catalogo = _num(f.get('precio_unidad')), _num(f.get('precio_catalogo'))
    if not f.get('en_oferta'):
        return unidad, False, False
    fin = _dia(f.get('fin_oferta'))
    if fin is not None and fin < hoy:
        return catalogo, False, True
    return unidad, True, False


def _apartado(f, motivo, detalle):
    return {'producto_heo': str(f.get('producto_prov') or ''), 'ean_original': str(f.get('ean_original') or ''),
            'nombre': f.get('nombre') or '', 'marca': (f.get('marca') or '').strip(),
            'precio_catalogo': _num(f.get('precio_catalogo')), 'motivo': motivo, 'detalle': detalle, 'en_oferta': None}


def construir_foto(filas, quiere_marca, M, n_crudo, n_sin_gtin, hoy, modo='marcas'):
    """De la foto de disponibilidad de DBLine a la foto de la pasada, sin perder a nadie: cada fila sale por UNA puerta
    previa o entra en la foto, y crudo (el fichero) = previas + foto. En este orden:
      1. sin unidades hoy (`disponible` falso) → `no_disponible` (se cuenta);
      2. marca que no pasa el filtro del modo → `marca_fuera` (se lista);
      3. chase suelto (`regla` de la foto, o `es_chase`) → `chase_suelto` (se lista; hoy 0);
      4. EAN base vacio o que no son 12 o 13 cifras, u otra `regla` de la foto → `ean_forma_rara` (se lista);
      5. sin precio de compra (vacio o 0, con la promo ya corregida) → `estado_no_servible` (se lista);
      6. dos filas con el mismo EAN base → la de menor PA (a igualdad, el codigo menor); la otra → `duplicado_proveedor`.
    `filas`: disp_estado de DBLINE vistas en la ultima pasada aplicada; `n_crudo` y `n_sin_gtin`: los de esa pasada
    (DB2 sube TODAS las filas, tambien las sin EAN, con `regla = 'ean_forma_rara'`: su `n_sin_gtin` es 0). `hoy`: el
    dia del barrido en Madrid. Devuelve (foto, apartados, cuentas)."""
    hoy = _dia(hoy)
    previas = {p: 0 for p in e2.PUERTAS_PREVIAS}
    previas['sin_gtin'] = n_sin_gtin
    apartados, sirven = [], []
    n_caducadas = 0
    no_elegida = modo == 'elegidas'
    for f in sorted(filas or [], key=lambda x: str(x.get('producto_prov') or '')):
        if not f.get('disponible'):
            previas['no_disponible'] += 1
            continue
        if not quiere_marca(f.get('marca')):
            apartados.append(_apartado(f, 'marca_fuera', ('Marca %r no elegida' if no_elegida
                                                          else 'Marca %r fuera de la lista del director')
                                       % ((f.get('marca') or '').strip(),)))
            continue
        regla = f.get('regla')
        if regla == 'chase_suelto' or f.get('es_chase'):
            apartados.append(_apartado(f, 'chase_suelto', 'Chase suelto: en DBLine no se compra'))
            continue
        core = str(f.get('ean_core') or '').strip()
        if regla or not core.isdigit() or len(core) not in (12, 13):
            apartados.append(_apartado(f, 'ean_forma_rara', 'EAN vacío o con forma rara (%s%s)'
                                       % (str(f.get('ean_original') or '').strip() or 'vacío',
                                          ', regla %s' % regla if regla else '')))
            continue
        pa, oferta, caducada = precio_vigente(f, hoy)
        if pa is None or pa <= 0:
            apartados.append(_apartado(f, 'estado_no_servible', 'Sin precio de compra en el catálogo de DBLine'))
            continue
        n_caducadas += 1 if caducada else 0
        sirven.append((f, pa, oferta))

    uno = {}
    for f, pa, oferta in sirven:
        k = M.norm(str(f['ean_core']).strip())
        prev = uno.get(k)
        if prev is None:
            uno[k] = (f, pa, oferta)
            continue
        gana, pierde = ((f, pa, oferta), prev) if (pa, str(f.get('producto_prov'))) < (prev[1], str(prev[0].get('producto_prov'))) \
            else (prev, (f, pa, oferta))
        uno[k] = gana
        apartados.append(_apartado(pierde[0], 'duplicado_proveedor', 'Mismo EAN que el %s de DBLine: me quedo con el '
                                   'más barato (%s frente a %s)' % (gana[0].get('producto_prov'), gana[1], pierde[1])))

    foto = []
    for f, pa, oferta in sorted(uno.values(), key=lambda x: str(x[0].get('producto_prov') or '')):
        core = str(f['ean_core']).strip()
        variantes = sorted({M.norm(v) for v in M.variantes_ean(core)} - {''})
        foto.append({
            'producto_heo': str(f.get('producto_prov') or ''),
            'ean_original': str(f.get('ean_original') or '').strip() or core,
            'ean_core': core, 'variantes': variantes, 'codigos_keepa': e2.codigos_para_keepa(core, M),
            'nombre': f.get('nombre') or '', 'marca': (f.get('marca') or '').strip(),
            'categoria': f.get('categoria') or '',
            # 🔑 precio_unidad = el PA (el vigente, por unidad): con el decide `escaner2_motor.decidir`.
            #    precio_catalogo = Prezzo, sin promo.
            'precio_catalogo': _num(f.get('precio_catalogo')), 'precio_unidad': pa,
            'es_caja': False, 'uds_caja': None, 'es_chase': False, 'en_oferta': oferta, 'campana': None,
            'disponibilidad': None, 'fin_de_vida': None, 'preorder': False, 'imagen': None,
            'aviso_caja': None, 'origen_ean': None, 'aviso_ean': None,
        })

    for m in e2.MOTIVOS_APARTADO:
        previas[m] = sum(1 for a in apartados if a['motivo'] == m)
    cuentas = {'n_crudo': n_crudo, 'n_filas': len(filas or []), 'n_foto': len(foto), 'previas': previas,
               'n_promo_caducada': n_caducadas, 'n_en_oferta': sum(1 for f in foto if f['en_oferta'])}
    cuentas.update(cuadre_previo(cuentas))
    return foto, apartados, cuentas


def cuadre_previo(cuentas):
    """🔴 crudo = previas + foto, y el crudo es el del fichero: filas de la foto de disponibilidad + las sin EAN que no
    esten en ella (en DBLine, 0). Un recuento que falta (None) NO es un cero."""
    previas = cuentas['previas']
    faltan = [p for p in e2.PUERTAS_PREVIAS if previas.get(p) is None]
    if cuentas.get('n_crudo') is None:
        faltan.insert(0, 'crudo')
    if faltan:
        return {'n_previas': None, 'cuadra_previo': False, 'motivo_previo': 'sin recuento de: ' + ', '.join(faltan)}
    n_previas = sum(previas[p] for p in e2.PUERTAS_PREVIAS)
    if cuentas['n_filas'] + previas['sin_gtin'] != cuentas['n_crudo']:
        return {'n_previas': n_previas, 'cuadra_previo': False,
                'motivo_previo': 'el fichero tenía %d filas y la foto de disponibilidad trae %d + %d sin EAN'
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
    """`dbline/<pasada>/<cruce>/Escaner2_DBLINE_<AAAAMMDD_HHMM>.xlsx`: la forma que admite
    escaner2_cruce.ruta_excel desde la migracion de la v2 de este encargo."""
    return '%s/%s/%s/Escaner2_DBLINE_%s.xlsx' % (CARPETA, pasada, cruce, sello)


def nombre_modo(modo):
    """Como se llama el modo de la pasada en el Excel (el mismo texto que el cruce de HEO)."""
    return {'todas': 'todas las marcas', 'elegidas': 'marcas elegidas'}.get(modo or 'marcas', 'marcas de siempre')


# ═══════════════════════════════════════════════════════════════════════════════
# 3 · EL EXCEL: EL DEL PRO DE HEO, TAL CUAL
# ═══════════════════════════════════════════════════════════════════════════════
COLUMNAS_CAJA = ['Caja', 'Precio caja (€)', 'EAN de la figura', 'Origen del EAN', 'Aviso del EAN']


def escribir_excel(foto, resultados, apartados, M, info):
    """El Excel del cruce de DBLine: el del PRO de HEO (`escaner2_heo_cruce.escribir_excel`), mismo formato y orden.
    DELANTE las hojas del viejo (la Celda 9: Análisis con «Ventas», Descartados, Ambiguos, Sin_rank, Precio por lote),
    con «Ficha compartida» al final de «Análisis»; DETRAS Resumen, Comparación (vacía: la comparacion con el viejo es
    la pieza d), Varias fichas, Puertas y Puertas previas. Solo lo calculado: aqui no se decide nada. → bytes."""
    from openpyxl.styles import Font
    por_foto = {f['id']: f for f in foto}
    datos = e2.datos_como_el_viejo(foto, resultados, apartados, M, eleccion=info.get('eleccion'))
    # El viejo de DBLine tampoco escribe «Chase_manual» (solo con PROVEEDOR == 'HEO').
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
        filas_res += [['Marcas del director', ', '.join(info.get('marcas') or []) or '(ninguna)']]
    filas_res += [['Foto de DBLine (pasada de disponibilidad)', info.get('foto') or '—'],
                  ['Precio de compra (PA)', 'el vigente, por unidad: el precio del catálogo, o el de la promo hasta '
                                            'su fin; sin escalón, sin 1 %, sin porte'],
                  ['Promos vigentes en la foto de la pasada', info.get('n_en_oferta', '—')],
                  ['Promos caducadas desde la foto (con el precio normal)', info.get('n_promo_caducada', '—')],
                  ['Umbral de caídas (30 días)', '%s (> %d)' % (e2.texto_corte(p['umbral']), p['umbral'])],
                  ['Fichas compartidas (productos de la lista, por país)',
                   ' · '.join('%s %d' % (k, n) for k, n in (info.get('n_compartidas') or {}).items()) or '—'],
                  ['Países del filtro de ventas', ', '.join(p['paises_filtro'])],
                  ['Países que se calculan (si traen CSV)', ', '.join(p['paises_calculo'])],
                  ['Países con CSV', ', '.join(info['usados'])],
                  ['Catálogo crudo de DBLine (el fichero)', info['n_crudo']]]
    filas_res += [['Puerta previa · %s' % nombre_previa(x, modo), info['previas'][x]] for x in e2.PUERTAS_PREVIAS]
    filas_res += [['Entradas (filas de la foto: un EAN, su código más barato)', info['n_entradas']]]
    filas_res += [['Puerta %s · %s' % (x, e2.NOMBRE_PUERTA[x]), info['n_bd'][x]] for x in e2.PUERTAS]
    filas_res += [['Puertas previas + suma de puertas', sum(info['previas'].values()) + sum(info['n_bd'].values())],
                  ['Cuadra', 'SÍ' if info['cuadra'] else 'NO'],
                  ['Comparación con el escáner viejo', 'no se hace aquí: es la pieza d (aparte)']]
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
    hoja('Varias fichas', ['EAN', 'Nombre DBLine', 'País', 'ASIN', 'Título Amazon', 'Puesto', 'Caídas 30 d',
                           'Precio venta (€)'], varias, {'A': 15, 'B': 50, 'E': 60})

    # Las cinco columnas de caja del PRO de HEO, vacias: DBLine no tiene cajas (mismo formato que el de HEO).
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
