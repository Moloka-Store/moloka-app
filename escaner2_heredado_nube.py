# -*- coding: utf-8 -*-
"""ESCANER 2 · LO HEREDADO DE moloka_escaner_nube.py (el escaner viejo), COPIADO LITERALMENTE.

Encargo B7 (25-sep-2026): el escaner 2 deja de leer el fichero del viejo. Cada pieza de aqui es el
texto EXACTO del original en el commit 2f9c06a (fichero con blob 21ec2016ef): mismas lineas, mismos nombres y
mismos comentarios, con su origen encima. Generado por script desde `git show`, no tecleado.

🔴 NO SE TOCA A MANO. Las formulas estan validadas (la rentabilidad empieza dividiendo las tarifas
   de Amazon entre 1,21). Si el viejo cambia, test_escaner2_heredado.py lo avisa y decide Fernando.
🔑 No se importa: escaner2_motor.py saca las piezas por nombre (`sacar_piezas`) y las ejecuta en un
   espacio de nombres propio, igual que antes hacia con el fichero del viejo.
   Unicas diferencias con el original: `keyrank` va sin su sangria (en el viejo esta dentro de un
   `if`) y la Celda 9 es la funcion `excel_del_viejo` (ver su cabecera).
"""


# ── ORIGEN: moloka_escaner_nube.py, líneas 310-415 · commit 2f9c06a · blob 21ec2016ef · md5 c2e8877884472b348add0abf8aaec788 ──
PERFILES = {
    'TCG': {
        'tipo':'excel', 'sheet':'Catálogo', 'header':0,
        'col_marca':'Marca', 'col_ean':'EAN', 'col_nombre':'Cabecera',
        'col_pa':'Precio', 'col_stock':'Stock', 'col_estado':'Estado producto',
        'estados_ok':['Disponible','Oferta','Saldo'],   # PreOrder / Backorder quedan FUERA
        'precio_caja6':'caja',   # la 'C' pegada al EAN ya significa la caja 5+1 -> PA es de la CAJA
    },
    'DBLINE': {
        'tipo':'excel', 'sheet':0, 'header':2,
        'col_marca':'Publisher', 'col_ean':'EAN', 'col_nombre':'Descrizione',
        'col_pa':'Prezzo (€)', 'col_pa_promo':'Prezzo promo (€)', 'col_stock':'Disponibili',
        'col_estado':None, 'estados_ok':None,
    },
    'BEMS': {
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'FABRICANT', 'col_ean':'EAN', 'col_nombre':'TITRE UK',
        'col_pa':'PA', 'col_stock':'STOCK', 'col_estado':None, 'estados_ok':None,
    },
    'OSMA': {
        # Mayorista aleman de drogueria/cosmetica (primera necesidad Moloka).
        # Excel .xls, cabecera fila 1 (header=0). Precio UNITARIO con coma decimal
        # alemana (1,099 = 1,099 EUR). Stock 'verfügbar' a veces viene como '>3.000'
        # (punto de MILLAR, no decimal) -> trato especial via stock_especial.
        # Sin filtro de estado (todo lo que tenga stock>0 entra). CHASE no aplica.
        'tipo':'excel', 'sheet':0, 'header':0,
        'col_marca':'Bezeichnung', 'col_ean':'EAN 1', 'col_nombre':'Bezeichnung',
        'col_pa':'Preis_', 'col_stock':'verfügbar', 'col_estado':None, 'estados_ok':None,
        'stock_especial':'osma',        # usa _stock_osma() para parsear '>3.000'
        'col_extra_liq':'wird ausgelistet',   # 'wird ausverkauft' = se liquida (info de compra)
    },
    'BIEDRO': {
        # Mayorista aleman de drogueria (primera necesidad Moloka), misma familia que OSMA.
        # Excel .xlsx; la cabecera de datos esta en la FILA 4 (header=3): las 3 primeras
        # son el formulario de pedido (Kunden-Nr, Kundenname, Anschrift).
        # Precio UNITARIO neto con PUNTO decimal (3.40) -> _num() lo parsea directo.
        # NO trae columna de stock -> sin_columna_stock=True (se asume disponible).
        # Sin marca propia (va en el nombre) ni estado. CHASE no aplica.
        # Validado contra catalogo real: 3.316 productos con EAN+precio.
        'tipo':'excel', 'sheet':0, 'header':3,
        'col_marca':None, 'col_ean':'Stück-EAN', 'col_nombre':'Artikelbezeichnung',
        'col_pa':'Stückpreis\nnetto', 'col_stock':None, 'col_estado':None, 'estados_ok':None,
        'sin_columna_stock':True,
    },
    'OCIOSTOCK': {
        # Mayorista espanol de licencias (Funko, Banpresto, Pyramid, Cerda...).
        # Feed CSV diario con URL FIJA que se autoactualiza (el token va en GitHub
        # Secrets, NUNCA en codigo). Separador ';', campos entrecomillados, BOM
        # (utf-8-sig) -> solo afecta a la 1a columna 'id_producto', que no usamos.
        # TIENE columna de marca limpia -> se puede filtrar por marca (FUNKO, etc.).
        # Stock real en 'stock_disponible' (>0).
        # 🔒 PA = 'precio_distribuidores' (coste del distribuidor). NO usar
        # 'precio_neto'/'precio_bruto': son PVP recomendado, no el coste.
        # OJO dropshipping: el precio puede venir mas alto que el mayorista real
        # -> contrastar Funko contra BEMS/TCG antes de fiarse.
        # Validado contra feed real: 13.412 con stock+EAN+precio (3.475 Funko).
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'marca', 'col_ean':'ean', 'col_nombre':'nombre',
        'col_pa':'precio_distribuidores', 'col_stock':'stock_disponible',
        'col_estado':None, 'estados_ok':None,
        'col_volumen':'txt_precios_volumen',   # descuentos por volumen -> pestana "Precio por lote"
        'col_url':'product_url',   # enlace a la ficha de OcioStock (verificar volumen/precio en su web)
        'precio_caja6':'unidad',   # VERIFICADO en su feed: 11,99 €/ud, 71,94 € la caja -> NO dividir
    },
    'STOCKLIST': {
        # Mayorista nordico GENERALISTA (Toys, Games and consoles, Beauty, Movies, Pet...).
        # Stocklist Excel .xlsx, hoja 'Sheet1', cabecera fila 1 (header=0). 43.174 refs, TODAS
        # con stock real. Multimoneda (EUR/GBP/USD/DKK) -> usamos EUR como coste, con PUNTO
        # decimal (17.99) -> _num() lo parsea directo. Marca limpia en 'Brand' (contains) ->
        # filtrable: Funko, Paladone, Numskull, Nemesis Now, LEGO, Ravensburger, Nintendo...
        # Stock en 'Available' (>0). Sin columna de estado (todo lo con stock entra).
        # 🔒 PENDIENTE VERIFICAR: que 'EUR' es el COSTE de proveedor y no el PVP recomendado.
        # Validado contra catalogo real: 42.878 productos con EAN(12/13)+precio+stock.
        'tipo':'excel', 'sheet':'Sheet1', 'header':0,
        'col_marca':'Brand', 'col_ean':'CodeBars', 'col_nombre':'ItemName',
        'col_pa':'EUR', 'col_stock':'Available', 'col_estado':None, 'estados_ok':None,
    },
    # ============================================================
    # PROVEEDORES DE CLAUDE-IN-CHROME (formato VARIABLE) -> DETECCION TOLERANTE
    # ------------------------------------------------------------
    # Estos catalogos se extraen a mano y cada extraccion puede salir con columnas
    # distintas (nombres, orden, xlsx/csv). En vez de fijar nombres de columna, se
    # usa 'deteccion':'tolerante': el motor detecta solo la columna de EAN (numeros
    # de 12-13 digitos), la de precio (importe, con o sin 'EUR'), la de nombre (texto
    # largo) y, si existen, marca y stock. EAN no-12/13 -> a descartados (NO se
    # inventan EANs). Stock ausente -> se asume disponible. CHASE no aplica.
    # Anadir un proveedor nuevo de Claude-in-Chrome = una linea aqui + el desplegable.
    # ============================================================
    'DINOTOYS': {'tipo':'auto', 'deteccion':'tolerante'},   # mayorista holandes (Logic4)
    'ZENTRADA': {'tipo':'auto', 'deteccion':'tolerante'},   # marketplace mayorista (xlsx/csv)
    'MIS_COMPRAS': {'tipo':'auto', 'deteccion':'tolerante', 'efimero':True},   # compras ad-hoc: deteccion tolerante y NO toca la memoria de ningun proveedor
    'HEO': {
        # heoGATE Retailer API -> catalogo cruzado por descargar_heo.py (CSV ';', columnas
        # fijas). El director de HEO PRE-FILTRA a Funko+Ultimate Guard+ofertas y sube el
        # resultado, asi que aqui se escanea con marca=TODAS. Sin stock numerico: el estado
        # 'disponible' (availableToOrder + AVAILABLE) filtra lo servible. PA = 'precio' (coste
        # de hoy, con oferta si la hay; el escaneo diario se autocorrige si la oferta acaba).
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'marca', 'col_ean':'ean', 'col_nombre':'nombre',
        'col_pa':'precio', 'col_stock':None,
        'col_estado':'estado', 'estados_ok':['disponible'],
        'sin_columna_stock':True,   # HEO no da stock numerico -> estado 'disponible' ya filtra
        'precio_caja6':'caja',   # la pestana Chase_manual trae 'Precio caja' y 'Precio /6' explicitos
    },
    'MOLOKA': {'tipo':'supabase'},   # inventario propio: se lee de la tabla productos
}


# ── ORIGEN: moloka_escaner_nube.py, líneas 533-547 · commit 2f9c06a · blob 21ec2016ef · md5 46c55b6dc805f607d2acbe05d8ca6cc0 ──
# ============================================================
# LOS PAISES DEL ESCANEO, EN UN SOLO SITIO
# ------------------------------------------------------------
# 🔴 UNA LISTA, NO CINCO. Hasta hoy los paises viajaban como ('ES','IT','FR')
#    LITERAL en cinco bucles distintos (Fase 2, chase de HEO, el calculo, la
#    hoja Analisis y la pestana 'Precio por lote'). Anadir un pais era acordarse
#    de los cinco: el que se quedara sin abrir no daria error -- ese pais
#    sencillamente NO APARECERIA en ese paso, y nadie lo veria. Un fallo que se
#    ve igual que un exito no es un fallo: es un silencio.
# 🔒 EL ORDEN IMPORTA Y ALEMANIA VA LA ULTIMA: la hoja escribe una fila por pais
#    en ESTE orden, asi que ES/IT/FR conservan su sitio y DE se anade detras.
# 🔑 Son los codigos de `keepa.DCODES` (constants.py de keepa 1.5.0): 'DE' es el
#    dominio 3 (amazon.de), igual que 'FR' es el 4, 'IT' el 8 y 'ES' el 9. Se
#    pasan tal cual a `api.query(domain=...)`, sin traduccion.
PAISES = ('ES', 'IT', 'FR', 'DE')


# ── ORIGEN: moloka_escaner_nube.py, líneas 549-550 · commit 2f9c06a · blob 21ec2016ef · md5 55fb37f98713d7eca28186a17766e44c ──
# IVA general de cada pais. El de ES sale de la ficha cuando la hay (iva_es_de).
IVA_DEFAULT_ES, IVA_IT, IVA_FR, IVA_DE = 0.21, 0.22, 0.20, 0.19


# ── ORIGEN: moloka_escaner_nube.py, líneas 551-551 · commit 2f9c06a · blob 21ec2016ef · md5 e3cf42a56db82c9b4c4f22b928d51ba0 ──
ALMACEN, COM_DIGITALES = 0.15, 1.03


# ── ORIGEN: moloka_escaner_nube.py, líneas 552-552 · commit 2f9c06a · blob 21ec2016ef · md5 00d7e0a4ade0a4cb415078cc2ce8c32f ──
UNIDADES_CASE_TCG = 6          # CHASE en case de 6 (5+1) -> coste unitario = PA / 6. TCG y chase HEO.


# ── ORIGEN: moloka_escaner_nube.py, líneas 561-591 · commit 2f9c06a · blob 21ec2016ef · md5 a96047ed24561946802eea111e3cf1ff ──
# ============================================================
# Celda 0 - formula de rentabilidad (validada al centimo)
# ============================================================
# ------------------------------------------------------------
# EL RECARGO POR SERVICIOS DIGITALES (ISD), por PAIS.
#
# 🔴 EL x1,03 PLANO NO CUADRA CON LA FACTURA EN FRANCIA. Cuadrado contra un pedido REAL de
#    Amazon en `transacciones_movimientos` -- `404-7912092-2024339`, SKU `82-4ME9-NOPN`, FR:
#        comision (tarifa_venta)  1,82 EUR
#        tarifa FBA (tarifa_fba)  5,29 EUR
#        ISD que Amazon COBRO     0,21 EUR   <- tarifa_otras
#      · 3 % x (1,82 + 5,29) = 0,2133  -> la base francesa INCLUYE la tarifa FBA  ✅
#      · 3 % x 1,82          = 0,0546  -> lo que daba el x1,03 plano              ❌
#    El escaner se dejaba el 3 % de la tarifa FBA: ~0,97 puntos de margen de MAS en Francia
#    (medido sobre las 1.800 filas francesas con margen de `escaner_detalle`). OPTIMISTA.
#
# 🔬 Los porcentajes estan MEDIDOS sobre los pedidos reales: ES 2,91 % (13.266 pedidos),
#    IT 3,00 % (603), FR 2,97 % sobre comision + FBA (391). Alemania es un SUPUESTO por
#    prudencia de Fernando (no hay ni una venta alemana contra la que contrastar) y su base
#    es la comision, como ES e IT -- Francia es la excepcion, no la norma.
#
# 🔒 Estos mismos valores viven tambien en `lib/inventory/build.ts` del repo de la app
#    (`ISD_PAIS`). NO se comparte codigo entre los dos repos: lo que ata a los dos es que
#    CADA UNO cuadra contra esta misma factura por su lado -- aqui abajo, y alli en
#    `tests/isd-frances.test.mjs`.
ISD_PAIS = {
    'ES': {'pct': 0.03, 'incluye_fba': False},
    'IT': {'pct': 0.03, 'incluye_fba': False},
    'FR': {'pct': 0.03, 'incluye_fba': True},   # <- la excepcion, medida
    'DE': {'pct': 0.03, 'incluye_fba': False},  # <- supuesto por prudencia
}


# ── ORIGEN: moloka_escaner_nube.py, líneas 593-596 · commit 2f9c06a · blob 21ec2016ef · md5 6a7efca23d575cceabcceb9680f6691c ──
# 🔴 "CALCULA CON LA CUENTA VIEJA, Y LO SE." Un parametro opcional cuya omision devuelve la
#    cuenta OPTIMISTA es una trampa con fecha: alguien llama desde un sitio nuevo, no lo
#    pasa, y se lleva el margen inflado sin que nada falle. Asi hay que ESCRIBIRLO.
SIN_ISD_HISTORICO = object()


# ── ORIGEN: moloka_escaner_nube.py, líneas 599-612 · commit 2f9c06a · blob 21ec2016ef · md5 e025570a9cf92fd97ff0b3a8f6d4478a ──
def calc_rentabilidad(precio_venta, pa, ref_pct, fee_fba, iva, almacen=0.15,
                      com_digitales=1.03, isd=SIN_ISD_HISTORICO):
    base = precio_venta / (1 + iva)
    if isd is SIN_ISD_HISTORICO:
        # La cuenta de siempre: el recargo va dentro del x1,03 de la comision. Se conserva
        # para poder REPRODUCIR lo que `escaner_detalle` guardo antes de la correccion.
        com_amazon = precio_venta * (ref_pct/100) * com_digitales
    else:
        com = precio_venta * (ref_pct/100)
        com_amazon = com + (com + (fee_fba if isd['incluye_fba'] else 0)) * isd['pct']
    beneficio  = base - pa - com_amazon - fee_fba - almacen
    roi        = beneficio / pa if pa else 0
    margen     = beneficio / precio_venta if precio_venta else 0
    return dict(base=base, com_amazon=com_amazon, beneficio=beneficio, roi=roi, margen=margen)


# ── ORIGEN: moloka_escaner_nube.py, líneas 636-639 · commit 2f9c06a · blob 21ec2016ef · md5 05e27d5bb3f9ad3fdd3b37e370397879 ──
def pct_comision_celda(ref_pct, isd):
    """El numero que va en la celda '% Comision': la tarifa de referencia MAS su
    propio recargo ISD. Es el factor por el que se multiplica el precio."""
    return (ref_pct / 100.0) * (1 + isd['pct'])


# ── ORIGEN: moloka_escaner_nube.py, líneas 704-713 · commit 2f9c06a · blob 21ec2016ef · md5 bcc97c0df228cdfd9100f0cbfabc4bae ──
# ============================================================
# Funciones de EAN
# ============================================================
# ============================================================
# EL SUFIJO DEL EAN NO SE TIRA, SE LEE (bloque 3). Es el dato que falta.
# OcioStock manda el MISMO EAN 3 veces: '...' (suelta), '... Chase' (suelto,
# se descarta) y '... C6' (la caja de 6, que es la que Fernando compra). Antes
# el 'C6' acababa en '6' -> "EAN forma rara" -> 66 cajas de 6 a la basura.
# ============================================================
_RE_SUFIJO = re.compile(r'^(.*?)\s+(C(\d+)|CHASE|L)\s*$', re.I)


# ── ORIGEN: moloka_escaner_nube.py, líneas 715-737 · commit 2f9c06a · blob 21ec2016ef · md5 6ff8de21b2dbded73205add44f3c62ec ──
def partir_ean(e):
    """'889698679282 C6' -> ('889698679282', 'C6', 6)
       '889698679282 Chase' -> ('889698679282', 'CHASE', None)
       '196214117020L'      -> ('196214117020', 'L', None)   (Latino, va PEGADA)
       '889698679282C'      -> ('889698679282', 'C', 6)      (convencion TCG, pegada)
       '8435507873345'      -> ('8435507873345', None, None)
    Devuelve (ean_limpio, sufijo, unidades_caja)."""
    e = str(e or '').strip().upper()
    if not e:
        return '', None, None
    m = _RE_SUFIJO.match(e)               # sufijo separado por espacio
    if m:
        base, suf = m.group(1).strip(), m.group(2)
        if suf.startswith('C') and m.group(3):
            return base, f'C{m.group(3)}', int(m.group(3))
        if suf == 'CHASE':
            return base, 'CHASE', None
        return base, 'L', None
    if e.endswith('L') and e[:-1].isdigit():      # 'L' pegada = version Latino
        return e[:-1], 'L', None
    if e.endswith('C') and e[:-1].isdigit():      # convencion TCG: la C pegada YA es la caja
        return e[:-1], 'C', 6
    return e, None, None


# ── ORIGEN: moloka_escaner_nube.py, líneas 739-744 · commit 2f9c06a · blob 21ec2016ef · md5 04123be7a79f8363bf9c3d45398e1c7f ──
def clasificar(sufijo):
    """(es_caja, descartar). El chase SUELTO se sigue descartando (regla de negocio)."""
    if sufijo is None:  return False, False       # figura normal
    if sufijo == 'L':   return False, False       # version Latino: producto normal
    if sufijo == 'CHASE': return False, True      # chase suelto -> descartar (ya funcionaba)
    return True, False                            # C / C6 / C12... -> caja


# ── ORIGEN: moloka_escaner_nube.py, líneas 746-756 · commit 2f9c06a · blob 21ec2016ef · md5 ef36dd6c3c4e3427a0e78fd55614262b ──
# ============================================================
# GTIN-14: el proveedor manda a veces el codigo de CAJA (14 digitos) en vez del
# EAN-13 de la unidad, y a veces lo manda TRUNCADO a 13. Se reconstruye el
# EAN-13 y se deja que Keepa confirme: si no existe, se descarta como siempre.
# Coste de equivocarse: 1 token. Coste de no intentarlo: el producto no se ve.
# (_chk13 y _ean_ok los usa variantes_ean; _gtin14_ok y rescatar_gtin quedan como
#  utilidades del modulo -hoy sin llamador- que documentan la reconstruccion.)
# ============================================================
def _chk13(cuerpo12):
    d = [int(x) for x in cuerpo12][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10)


# ── ORIGEN: moloka_escaner_nube.py, líneas 758-759 · commit 2f9c06a · blob 21ec2016ef · md5 ab7e3830fcf1daf9e794efb266a35ae2 ──
def _ean_ok(s):
    return s.isdigit() and len(s) == 13 and _chk13(s[:12]) == s[12]


# ── ORIGEN: moloka_escaner_nube.py, líneas 761-765 · commit 2f9c06a · blob 21ec2016ef · md5 a0c220e16875b86a13db9fd4582aa394 ──
def _gtin14_ok(s):
    if not (s.isdigit() and len(s) == 14):
        return False
    d = [int(x) for x in s[:13]][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10) == s[13]


# ── ORIGEN: moloka_escaner_nube.py, líneas 767-779 · commit 2f9c06a · blob 21ec2016ef · md5 a345b3347279bea1ffff8324de9a2938 ──
def rescatar_gtin(e):
    """Devuelve el EAN-13 de la unidad, o None si no aplica. NO se usa si el
    codigo ya es un EAN-13/UPC-12 valido: solo para los que hoy se tiran."""
    e = str(e or '').strip()
    if not e.isdigit():
        return None
    if len(e) == 12 or _ean_ok(e):
        return None                              # ya vale tal cual
    if len(e) == 14 and _gtin14_ok(e):           # GTIN-14 completo
        return e[1:13] + _chk13(e[1:13])
    if len(e) == 13 and not _ean_ok(e) and e[0] in '123456789':
        return e[1:13] + _chk13(e[1:13])         # GTIN-14 truncado a 13 por el proveedor
    return None


# ── ORIGEN: moloka_escaner_nube.py, líneas 781-781 · commit 2f9c06a · blob 21ec2016ef · md5 a2c49e1e71246f4f55d8dc67e8297652 ──
def core_ean(e):     return partir_ean(e)[0]


# ── ORIGEN: moloka_escaner_nube.py, líneas 784-793 · commit 2f9c06a · blob 21ec2016ef · md5 0032572bd58dd808f9214faaed83b20f ──
# ============================================================
# GUARDARRAIL RELATIVO caja-vs-suelta (regla de Fernando: NINGUN umbral absoluto
# de precio; compra Funkos a 2,99 y llaveros a 1 €). Se compara la ficha CAJA
# contra la ficha SUELTA del MISMO EAN. Una oferta agresiva baja las DOS -> pasa
# limpia. Un fallo de parseo (÷6 mal aplicado) baja solo la caja -> salta.
# Medido sobre el feed real de OcioStock (28-jul), 105 pares caja/suelta:
#   ratio real min 0.48 | mediana 1.00 | max 1.50 ; con el ÷6 del bug: 0.079 a 0.25.
# Umbral 0.40: cero falsos positivos, caza el bug 105 de 105.
# ============================================================
UMBRAL_CAJA_VS_SUELTA = 0.40


# ── ORIGEN: moloka_escaner_nube.py, líneas 794-801 · commit 2f9c06a · blob 21ec2016ef · md5 aed993edc649ae64d27045a2bef1fb06 ──
def aviso_caja_incoherente(pa_caja_ud, pa_suelta):
    if not (pa_caja_ud and pa_suelta and pa_suelta > 0):
        return None
    ratio = pa_caja_ud / pa_suelta
    if ratio < UMBRAL_CAJA_VS_SUELTA:
        return (f'INCOHERENTE: la caja sale a {pa_caja_ud:.2f} €/ud y la unidad suelta del '
                f'MISMO EAN esta a {pa_suelta:.2f} € (ratio {ratio:.2f}). Parseo roto, no ganga.')
    return None


# ── ORIGEN: moloka_escaner_nube.py, líneas 803-813 · commit 2f9c06a · blob 21ec2016ef · md5 55ce1f3c73175b1c13353d4103c31a72 ──
# ---- REGLA DE NEGOCIO DEL CHASE (todos los proveedores) --------------------
# El chase SOLO se compra en CAJA DE 6 (5+1): coste unitario = PA / 6.
# El chase SUELTO es un atraco -> se DESCARTA (no se escanea, no gasta tokens).
# OJO AL ORDEN: el sufijo del EAN manda sobre el nombre, porque en TCG la 'C'
# pegada al EAN YA significa la caja 5+1; si mirasemos el nombre primero,
# descartariamos por error los cases de TCG que se llaman "... Chase".
# De paso corta el bucle de OcioStock: alli el mismo EAN llega como figura
# normal, como caja 5+1 y como chase suelto, con precios muy distintos; al
# descartar el suelto y separar normal/caja en claves de memoria distintas,
# deja de haber 'cambio_precio' perpetuo.
_RE_CAJA6 = re.compile(r'5\s*\+\s*1', re.I)


# ── ORIGEN: moloka_escaner_nube.py, líneas 814-820 · commit 2f9c06a · blob 21ec2016ef · md5 92af5a48e7c7bd3c02197b2fd6122dc2 ──
# "chase" SOLO cuenta cuando es MARCADOR DE VARIANTE: al FINAL del nombre
# ("... Dilophosaurus Chase") o entre PARENTESIS ("... Pink Batman (CHASE) 18 cm").
# Si aparece en MEDIO es, casi siempre, un NOMBRE PROPIO: Chase es el perro de la
# Patrulla Canina, y sin esta restriccion se tiraban paraguas, gorros, mochilas y
# peluches perfectamente legitimos ("Peluche Chase Patrulla Canina Paw Patrol").
# Medido en el ensayo del 24-jul-2026 contra el feed real de OcioStock.
_RE_CHASE_NOM = re.compile(r'\bchase\b\s*$|\([^)]*\bchase\b[^)]*\)', re.I)


# ── ORIGEN: moloka_escaner_nube.py, líneas 821-825 · commit 2f9c06a · blob 21ec2016ef · md5 7e31f74ba3257ca9c358a094a5fd1ab9 ──
# "w/Chase" y "with Chase" significan CON chase: la linea INCLUYE el chase, no
# ES un chase suelto. Es la forma habitual de DBLine ("FUNKO GOLD ... w/Chase",
# a precio de unidad) y tambien de HEO ("... w/CH 9 cm Surtido (6)"). Entra
# como producto NORMAL. Medido en el ensayo del 24-jul-2026.
_RE_CON_CHASE = re.compile(r'\b(?:w/|with)\s*ch(?:ase)?\b', re.I)


# ── ORIGEN: moloka_escaner_nube.py, líneas 827-841 · commit 2f9c06a · blob 21ec2016ef · md5 d504d7ffda199a462e55d372b1969886 ──
def clasificar_chase(nombre, ean_in):
    """(es_case, es_caja6, descartar). El SUFIJO del EAN manda sobre el nombre."""
    _base, suf, _uds = partir_ean(ean_in)
    if suf is not None:
        es_caja, descartar = clasificar(suf)
        if descartar:   return False, False, True      # chase SUELTO -> fuera
        if es_caja:     return True, True, False        # C / C6 / C12 -> caja
        return False, False, False                      # 'L' (Latino) -> producto normal
    n = str(nombre or '')
    # 🔒 El nombre YA NO decide si es caja: eso lo dice el sufijo del EAN. "5 + 1"
    # en el nombre solo sirve para NO descartarlo como chase suelto.
    if _RE_CAJA6.search(n):     return True, True, False
    if _RE_CON_CHASE.search(n): return False, False, False
    if _RE_CHASE_NOM.search(n): return False, False, True
    return False, False, False


# ── ORIGEN: moloka_escaner_nube.py, líneas 842-856 · commit 2f9c06a · blob 21ec2016ef · md5 163db5c8a4a39ceed83bf5c3ea659cac ──
def variantes_ean(core):
    c, vs = str(core).strip(), set()
    if c.isdigit():
        vs.add(c); vs.add(c.lstrip('0'))
        if len(c)==12: vs.add('0'+c)
        if len(c)==13 and c.startswith('0'): vs.add(c[1:])
        # 🆕 GTIN-14: codigo de CAJA (14 digitos) o truncado a 13 por el proveedor.
        # Solo si NO es un EAN-13 valido, o si empieza por 1/2 (prefijos GS1 que no
        # son de pais). Medido sobre el catalogo real: genera variante en 5 de 1.557
        # codigos (0,32%), y son EXACTAMENTE los 5 raros. Cero falsos positivos.
        # (ningun EAN-13 legitimo empieza por 1 o 2; los buenos van por 8, 0 y 3.)
        if len(c) == 14 or (len(c) == 13 and (not _ean_ok(c) or c[0] in '12')):
            cuerpo = c[1:13]
            if len(cuerpo) == 12: vs.add(cuerpo + _chk13(cuerpo))
    return [v for v in vs if v]


# ── ORIGEN: moloka_escaner_nube.py, líneas 857-857 · commit 2f9c06a · blob 21ec2016ef · md5 02dcdbb04a7d062e3e163f764dea1ca2 ──
def norm(code): return str(code).strip().lstrip('0')


# ── ORIGEN: moloka_escaner_nube.py, líneas 858-860 · commit 2f9c06a · blob 21ec2016ef · md5 9ed2527777f221213474775848ad89c4 ──
def _num(x):
    try: return float(str(x).replace(',', '.').strip())
    except Exception: return None


# ── ORIGEN: moloka_escaner_nube.py, líneas 925-925 · commit 2f9c06a · blob 21ec2016ef · md5 92acfc7028874dfc2d3daace255b6e68 ──
UMBRAL_COTEJO = 0.40        # solo se usa cuando el nombre NO tiene ninguna palabra distintiva


# ── ORIGEN: moloka_escaner_nube.py, líneas 929-938 · commit 2f9c06a · blob 21ec2016ef · md5 f66d3d89a6ed834a06f6d9d2d4267523 ──
def _tok_cot(t):
    t = unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode().lower()
    out = []
    for w in re.sub(r'[^a-z0-9]+', ' ', t).split():
        if len(w) < 3 and not w.isdigit():
            continue
        if len(w) > 4 and w.endswith('s'):
            w = w[:-1]                     # plural simple
        out.append(w)
    return out


# ── ORIGEN: moloka_escaner_nube.py, líneas 940-952 · commit 2f9c06a · blob 21ec2016ef · md5 5a2bf080e1f640e6abdbf5cafa8bc2da ──
def construir_idf(nombres):
    """Una palabra que sale en MUCHOS productos del catalogo (funko, pop, figura,
    disney, dragon...) no distingue nada. El propio catalogo dice cuales son:
    no hace falta mantener a mano ninguna lista de palabras a ignorar."""
    global _DF, _NDOC
    _DF, vistos = Counter(), set()
    for n in nombres:
        n = str(n or '').strip()
        if not n or n in vistos:
            continue
        vistos.add(n)
        _DF.update(set(_tok_cot(n)))
    _NDOC = max(1, len(vistos))


# ── ORIGEN: moloka_escaner_nube.py, líneas 954-954 · commit 2f9c06a · blob 21ec2016ef · md5 e9c25ef4c83dec3047b4edfd4281a1a0 ──
def _idf(w):          return math.log(_NDOC / (1 + _DF.get(w, 0)))


# ── ORIGEN: moloka_escaner_nube.py, líneas 955-955 · commit 2f9c06a · blob 21ec2016ef · md5 ff561ede1131187618d1d5b9779e86df ──
def _distintivo(w):   return _DF.get(w, 0) <= max(2, _NDOC * 0.01)


# ── ORIGEN: moloka_escaner_nube.py, líneas 957-980 · commit 2f9c06a · blob 21ec2016ef · md5 aa080efcf36de50e6641f9868c7d8ad7 ──
def cotejar(nombre_prov, titulo_amz):
    """(casa, score, motivo). casa=None -> NO SE PUEDE cotejar: el llamador debe
    comportarse como hasta hoy (desempate por rank), nunca rechazar por esto."""
    if not COTEJO_ACTIVO:
        return None, 0.0, 'n/d: proveedor sin columna de nombre'
    tp = _tok_cot(nombre_prov)
    ta = set(_tok_cot(titulo_amz))
    if not tp or not ta:
        return None, 0.0, 'n/d: sin texto que comparar'
    # 🔒 RED DE SEGURIDAD (defensa en profundidad). Con deteccion tolerante, si el
    # motor no encuentra columna de nombre usa la del EAN como nombre
    # (`det['nombre'] or det['ean']`). Un "nombre" que son solo digitos NO es un
    # nombre: sin esto, ZENTRADA/DINOTOYS rechazarian el catalogo entero.
    if not [w for w in tp if not w.isdigit()]:
        return None, 0.0, 'n/d: el nombre no tiene palabras (parece un codigo)'
    pesos = {w: _idf(w) for w in set(tp)}
    score = sum(p for w, p in pesos.items() if w in ta) / (sum(pesos.values()) or 1)
    fuertes = {w for w in pesos if _distintivo(w)}
    if fuertes:                                     # via 1 (95,5% del catalogo)
        casan = fuertes & ta
        if casan:
            return True, score, 'casa: ' + ', '.join(sorted(casan)[:3])
        return False, score, 'ningun distintivo casa (faltan: ' + ', '.join(sorted(fuertes)[:3]) + ')'
    return (score >= UMBRAL_COTEJO), score, f'cobertura {score:.0%} (nombre sin palabras distintivas)'


# ── ORIGEN: moloka_escaner_nube.py, líneas 982-1008 · commit 2f9c06a · blob 21ec2016ef · md5 5d080f87e44613986413122b84d97cbc ──
def elegir_candidato(nombre_prov, cands, keyrank):
    """cands: [{'asin','title','r_90',...}] -> (elegido, veredicto, detalle).
    🔒 REGLA DE FERNANDO (28-jul): NUNCA devuelve None. Si ninguno pasa el filtro
    se entrega EL MAS PARECIDO y se marca DUDOSO. Sacar un producto del informe
    porque el criterio no lo reconoce seria cambiar un error VISIBLE (un ASIN
    equivocado, que se ve y se corrige) por una AUSENCIA INVISIBLE (un producto
    que falta y del que nadie se entera). Es el mismo pecado que la fuga
    silenciosa. El criterio ORDENA y AVISA; no decide qué desaparece.
    Ademas el filtro fallara por idioma (Vengadores/Avengers) y eso no puede
    costarte dejar de ver el producto."""
    if not cands:
        return None, '—', 'sin candidatos'
    ev = [(c, cotejar(nombre_prov, c.get('title'))) for c in cands]
    if all(v[0] is None for _, v in ev):                    # no hay con que cotejar
        return min(cands, key=keyrank), 'n/d', ev[0][1][2] + ' -> elegido por rank, como siempre'
    casan = [(c, v) for c, v in ev if v[0] is True]
    if casan:
        elegido = min((c for c, _ in casan), key=keyrank)
        det = next(v[2] for c, v in casan if c is elegido)
        return elegido, 'OK', f'{len(casan)}/{len(cands)} casan; entre esos, mejor rank ({det})'
    # Ninguno pasa el filtro -> se entrega el MAS PARECIDO, nunca se descarta.
    mejor_c, mejor_v = max(ev, key=lambda cv: (cv[1][1], -keyrank(cv[0])))
    if mejor_v[1] <= 0:                                     # ni uno se parece en nada
        return (min(cands, key=keyrank), '⚠ DUDOSO',
                f'ninguno de los {len(cands)} se parece al nombre; te pongo el de mejor rank — REVISAR')
    return (mejor_c, '⚠ DUDOSO',
            f'ninguno pasa el filtro; te pongo el MAS PARECIDO ({mejor_v[1]:.0%} de {len(cands)}) — REVISAR')


# ── ORIGEN: moloka_escaner_nube.py, líneas 1435-1438 · commit 2f9c06a · blob 21ec2016ef · md5 aa7d68dc6618238364445d0edcd016d7 ──
def _sup(core):
    for v in [norm(core), core, '0'+core]:
        if v in sup: return sup[v]
    return None


# ── ORIGEN: moloka_escaner_nube.py, líneas 1439-1443 · commit 2f9c06a · blob 21ec2016ef · md5 52a63a131710f056767043543464bb2e ──
# 🔒 EL VALOR Y SU ORIGEN, EN LA MISMA FUNCION. Si la etiqueta de la hoja se
# calculara aparte, podria decir 'ficha' en una fila cuyo IVA es el 21% asumido
# -- dos cuentas en la misma fila, que es el pecado que cerro el #266 por el
# lado del ISD. Aqui solo hay un sitio donde se decide, y devuelve las dos cosas.
ORIGEN_IVA_FICHA = 'ficha'


# ── ORIGEN: moloka_escaner_nube.py, líneas 1444-1444 · commit 2f9c06a · blob 21ec2016ef · md5 78a65eb97333dc06f71cb14cbfeb9809 ──
ORIGEN_IVA_ASUMIDO = f'asumido {IVA_DEFAULT_ES:.0%}'


# ── ORIGEN: moloka_escaner_nube.py, líneas 1445-1453 · commit 2f9c06a · blob 21ec2016ef · md5 dd2d02fadd1ed7598be0356188bb9c42 ──
def iva_es_con_origen(core):
    """(IVA de ES, de donde sale). 'ficha' = lo dice `productos.iva_pct` de esta
    ficha; 'asumido 21%' = no hay ficha (o su iva_pct no es un numero) y se usa
    IVA_DEFAULT_ES. Ojo: iva_pct se guarda como FRACCION (0.21), no como 21."""
    s = _sup(core)
    if s and s.get('iva_pct') not in (None,''):
        try: return float(s['iva_pct']), ORIGEN_IVA_FICHA
        except Exception: pass
    return IVA_DEFAULT_ES, ORIGEN_IVA_ASUMIDO


# ── ORIGEN: moloka_escaner_nube.py, líneas 1454-1455 · commit 2f9c06a · blob 21ec2016ef · md5 eb255a60b72c255d0089ddb5345f205f ──
def iva_es_de(core):
    return iva_es_con_origen(core)[0]


# ── ORIGEN: moloka_escaner_nube.py, líneas 1456-1463 · commit 2f9c06a · blob 21ec2016ef · md5 b05628dfa72d19e7433d068a25e9dc36 ──
def origen_iva_fila(dom, iva, core):
    """De donde sale el IVA de ESTA fila de la hoja (la columna 'Origen IVA').
    IT y FR llevan el tipo GENERAL del pais, que no vive en la ficha: se rotula
    con el numero que la fila ha usado de verdad, no con un texto fijo. Sin IVA
    (el pais no dio datos) no hay nada que explicar: la fila calla."""
    if iva is None: return '—'
    if dom == 'ES': return iva_es_con_origen(core)[1]
    return f'general {dom} {iva:.0%}'


# ── ORIGEN: moloka_escaner_nube.py, líneas 1464-1464 · commit 2f9c06a · blob 21ec2016ef · md5 8419f9c4aa5b8b14fe10f0213b9576fc ──
def es_propio(core): return _sup(core) is not None


# ── ORIGEN: moloka_escaner_nube.py, líneas 1465-1468 · commit 2f9c06a · blob 21ec2016ef · md5 5d2f78f0a69058de55c90e6b393ad448 ──
def en_bd_txt(core):
    s = _sup(core)
    if not s: return ''
    return f"OK Alm:{s.get('stock_moloka',0)} FBA:{s.get('stock_fba',0)}"


# ── ORIGEN: moloka_escaner_nube.py, líneas 1617-1617 · commit 2f9c06a · blob 21ec2016ef · md5 4b708d33bb7eda285751d1193994db38 ──
# ── (anidada en el original: aquí va sin su sangría de 4 espacios, nada más)
def keyrank(c): return c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12


# ── ORIGEN: moloka_escaner_nube.py, líneas 1941-1948 · commit 2f9c06a · blob 21ec2016ef · md5 7d53ece74eeee15ba65686348f4a9c8e ──
# ============================================================
# Celda 8 - calculo (decision + orden por margen ES)
# ============================================================
def decision_de(margen):
    if margen is None: return 'Sin datos'
    if margen*100 >= 10: return 'COMPRAR'
    if margen*100 >= 1:  return 'VALORAR'
    return 'NO COMPRAR'


# ── ORIGEN: moloka_escaner_nube.py, líneas 1981-2245 · commit 2f9c06a · blob 21ec2016ef · md5 e41e3f07aed1c76a13850c0d1d4b6912 ──
# ── La «Celda 9» del viejo, hecha FUNCION (encargo B7). Lo UNICO que cambia respecto al original:
# ──   1) esta linea `def` con sus parametros (los datos que el bloque leia como globales);
# ──   2) cada linea del bloque lleva 4 espacios mas de sangria (las vacias siguen vacias);
# ──   3) `return wb` al final.
# ── Todo lo demas (texto, formulas, formatos, anchos, semaforo, comentarios) es el del original.
def excel_del_viejo(registros, problematicos, no_encontrados, chase_sueltos, _dups, ambiguos, sin_rank, chase_pendientes, cotejo_info, PROVEEDOR):
    # ============================================================
    # Celda 9 - Excel final (1 fila por pais, formulas vivas, semaforo)
    # ============================================================
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.formatting.rule import FormulaRule, CellIsRule

    COLS = ['Nombre','EAN','ASIN','Marca','PA (€)','País','Rank actual','Rank 90d','Vendidos/mes',
            'Precio venta (€)','Canal BB','Nº ofertas','% Comisión',
            'Com. Amazon (€)','Fee Logística (€)','Almacén (€)','Promo activa',
            'Beneficio (€)','ROI','Margen','Decisión','En mi BD','EAN ambiguo','Amazon (título)','Coincide',
            'Cotejo','Cotejo (detalle)','Coherencia caja','OcioStock',
            # 🔴 AL FINAL, Y NO POR COMODIDAD: hay consumidores que leen la hoja por LETRA de
            # columna. Metida en medio, 'ISD s/ Fee Log.' correria A..AB una posicion y el que
            # leyera 'R' se llevaria otra cosa sin enterarse. Columna nueva -> al final, SIEMPRE.
            'ISD s/ Fee Log. (€)',
            # Y esta detras de aquella, por lo mismo. Dice de donde sale el IVA con el que se
            # ha dividido el precio de ESTA fila: 'ficha' (lo dice productos.iva_pct), 'asumido
            # 21%' (no esta en el catalogo propio) o el tipo general de IT/FR. Sin ella, el 21%
            # por defecto y un 21% de la ficha se leen igual, y no hay forma de saber si el
            # catalogo propio se cruzo de verdad.
            'Origen IVA']
    L = {name:get_column_letter(i+1) for i,name in enumerate(COLS)}
    DOM_AMZ = {'ES':'amazon.es','IT':'amazon.it','FR':'amazon.fr','DE':'amazon.de'}

    wb = Workbook(); ws = wb.active; ws.title='Análisis'
    ws.append(COLS)

    r = 1
    for item in registros:
        en_bd = en_bd_txt(item['core'])
        amb = 'AMBIGUO' if item['ambiguo'] else ''
        _cot = cotejo_info.get(item['ean']) or {}   # veredicto del cotejo para este producto ('—' si no hay)
        for dom in PAISES:
            d = item['_paises_calc'].get(dom)
            if not d:
                d = {'rank_act':None,'rank90':None,'vendidos':None,'precio':None,'canal':'sin datos',
                     'n_of':None,'ref_pct':None,'fee':None,'iva':None,'decision':'Sin datos'}
            r += 1
            # 🔴 DE ISD_PAIS, NO DE COM_DIGITALES. En ES los dos dan 1,03 y por eso el fallo
            # se veia solo en Francia; leyendo la tabla, la hoja se entera de cualquier cambio.
            _isd = ISD_PAIS[dom]
            pct = pct_comision_celda(d['ref_pct'], _isd) if d.get('ref_pct') is not None else None
            div = (1+d['iva']) if d.get('iva') else None
            # 🔴 LA HOJA SOLO ECHA LA CUENTA SI `_paises_calc` TAMBIEN LA ECHO. Misma
            # condicion que la Celda 8, palabra por palabra. Hasta hoy la hoja pedia
            # menos: si Keepa no daba la tarifa FBA (o faltaba el PA), la columna
            # Decision decia 'Sin datos' y la fila de al lado ensenaba un Beneficio
            # calculado con esa celda VACIA leida como 0 -- o sea, de mas. Dos cuentas
            # en la misma fila otra vez, por el otro lado.
            hay_cuenta = bool(div and d.get('precio') and pct is not None
                              and d.get('fee') is not None and item['_pa_efectivo'])
            ws.append([
                item['nombre'], item['ean'], item['asin'], item['marca'], item['_pa_efectivo'], dom,
                d['rank_act'] if d['rank_act'] and d['rank_act']>0 else None,
                d['rank90'] if d['rank90'] and d['rank90']>0 else None,
                d['vendidos'], d['precio'], d['canal'], d['n_of'], pct,
                # com_amazon = precio x %Comision  +  ISD s/ Fee Log.  (el 2o sumando es 0 fuera
                # de Francia). Exactamente lo que hace calc_rentabilidad con isd=ISD_PAIS[dom].
                (f"={L['Precio venta (€)']}{r}*{L['% Comisión']}{r}"
                 f"+{L['ISD s/ Fee Log. (€)']}{r}") if pct is not None else None,
                d['fee'], ALMACEN, None,
                (f"=({L['Precio venta (€)']}{r}/{div})-{L['PA (€)']}{r}-{L['Com. Amazon (€)']}{r}"
                 f"-{L['Fee Logística (€)']}{r}-{L['Almacén (€)']}{r}") if hay_cuenta else None,
                f"={L['Beneficio (€)']}{r}/{L['PA (€)']}{r}" if hay_cuenta else None,
                f"={L['Beneficio (€)']}{r}/{L['Precio venta (€)']}{r}" if hay_cuenta else None,
                d['decision'], en_bd, amb,
                item.get('titulo_amz',''), item.get('coincide','?'),
                _cot.get('veredicto','—'), _cot.get('detalle','—'),
                item.get('coherencia_caja','') or '—',
                ('Ver ficha ↗' if item.get('url') else ''),
                # VIVA, como el resto de la hoja: si Elena corrige la fee, el ISD se recalcula.
                # Fuera de Francia es un 0 escrito, no un hueco: un hueco se lee como "no lo se".
                (f"={L['Fee Logística (€)']}{r}*{_isd['pct']}"
                 if (_isd['incluye_fba'] and d.get('fee') is not None) else 0),
                origen_iva_fila(dom, d.get('iva'), item['core'])])
            cell = ws.cell(row=r, column=3)
            cell.hyperlink = f"https://www.{DOM_AMZ[dom]}/dp/{item['asin']}"
            cell.font = Font(color='0563C1', underline='single')
            if item.get('url'):
                # 🔴 POR NOMBRE, NO POR len(COLS). OcioStock era la ultima columna y esto lo
                # daba por hecho; al anadir 'ISD s/ Fee Log.' detras, el enlace habria caido en
                # la columna equivocada. Un indice que significa "la ultima" es una bomba de
                # relojeria con la fecha puesta en el dia que alguien anada una columna.
                cocel = ws.cell(row=r, column=COLS.index('OcioStock') + 1)
                cocel.hyperlink = item['url']
                cocel.font = Font(color='0563C1', underline='single')

    last = ws.max_row
    def fmt(colname, code):
        c = L[colname]
        for row in range(2,last+1):
            ws[f'{c}{row}'].number_format = code
    for nm in ['PA (€)','Precio venta (€)','Com. Amazon (€)','Fee Logística (€)','Almacén (€)',
               'Beneficio (€)','ISD s/ Fee Log. (€)']:
        fmt(nm,'0.00')
    fmt('% Comisión','0.00%'); fmt('ROI','0.0%'); fmt('Margen','0.0%')

    for c in range(1,len(COLS)+1):
        ws.cell(row=1,column=c).font = Font(bold=True)
    anchos = {'Nombre':50,'EAN':14,'ASIN':12,'Marca':12,'En mi BD':20,'Decisión':15,
              'Amazon (título)':50,'Coincide':11,'Cotejo':16,'Cotejo (detalle)':46,
              'Coherencia caja':46,'OcioStock':13,'ISD s/ Fee Log. (€)':17,
              'Origen IVA':14}
    for nm,w in anchos.items(): ws.column_dimensions[L[nm]].width = w

    ws.freeze_panes = 'A2'

    def _cf_fill(hexcolor): return PatternFill(start_color=hexcolor, end_color=hexcolor, fill_type='solid')
    # Tabla + semaforo SOLO si hay al menos una fila de datos. Un escaneo 'nuevos' sin
    # novedades deja registros vacio -> last=1 -> rango invertido (U2:U1) que PETA openpyxl.
    if last >= 2:
        tab = Table(displayName='T_Analisis', ref=f"A1:{get_column_letter(len(COLS))}{last}")
        tab.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=False,
                                            showColumnStripes=False, showFirstColumn=False, showLastColumn=False)
        ws.add_table(tab)
        dec = L['Decisión']; rng_dec = f'{dec}2:{dec}{last}'
        ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO COMPRAR",{dec}2))'],
            fill=_cf_fill('FFC7CE'), font=Font(color='9C0006'), stopIfTrue=True))
        ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("VALORAR",{dec}2))'],
            fill=_cf_fill('FFEB9C'), font=Font(color='9C6500'), stopIfTrue=True))
        ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("COMPRAR",{dec}2))'],
            fill=_cf_fill('C6EFCE'), font=Font(color='006100'), stopIfTrue=True))
        ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("Sin datos",{dec}2))'],
            fill=_cf_fill('E7E6E6'), font=Font(color='808080'), stopIfTrue=True))
        ws.conditional_formatting.add(f"{L['Margen']}2:{L['Margen']}{last}",
            CellIsRule(operator='greaterThan', formula=['0.1'], font=Font(color='006100')))
        coi = L['Coincide']; rng_coi = f'{coi}2:{coi}{last}'
        ws.conditional_formatting.add(rng_coi, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO",{coi}2))'],
            fill=_cf_fill('FFC7CE'), font=Font(color='9C0006')))
        # Semaforo del COTEJO (mismo espiritu que Coincide): DUDOSO rojo (revisar el
        # ASIN), n/d gris (no habia con que cotejar), OK verde (rank y cotejo coinciden).
        cot = L['Cotejo']; rng_cot = f'{cot}2:{cot}{last}'
        ws.conditional_formatting.add(rng_cot, FormulaRule(formula=[f'ISNUMBER(SEARCH("DUDOSO",{cot}2))'],
            fill=_cf_fill('FFC7CE'), font=Font(color='9C0006'), stopIfTrue=True))
        ws.conditional_formatting.add(rng_cot, FormulaRule(formula=[f'ISNUMBER(SEARCH("n/d",{cot}2))'],
            fill=_cf_fill('E7E6E6'), font=Font(color='808080'), stopIfTrue=True))
        ws.conditional_formatting.add(rng_cot, FormulaRule(formula=[f'ISNUMBER(SEARCH("OK",{cot}2))'],
            fill=_cf_fill('C6EFCE'), font=Font(color='006100'), stopIfTrue=True))
        # Coherencia caja: rojo si el precio/ud de la caja no cuadra con el de la suelta.
        ccj = L['Coherencia caja']; rng_ccj = f'{ccj}2:{ccj}{last}'
        ws.conditional_formatting.add(rng_ccj, FormulaRule(formula=[f'ISNUMBER(SEARCH("INCOHERENTE",{ccj}2))'],
            fill=_cf_fill('FFC7CE'), font=Font(color='9C0006')))
        ws.conditional_formatting.add(f'A2:{get_column_letter(len(COLS))}{last}',
            # 🔒 El /len(PAISES) NO es cosmetica: la banda gris marca UN PRODUCTO, y
            # un 3 escrito a mano pintaria media banda por producto con cuatro paises.
            FormulaRule(formula=[f'ISODD(INT((ROW()-2)/{len(PAISES)}))'], fill=_cf_fill('D9D9D9')))

    def hoja(nombre, regs):
        w = wb.create_sheet(nombre)
        if regs:
            ks = list(regs[0].keys()); w.append(ks)
            for x in regs: w.append([x.get(k) for k in ks])
        else: w.append(['(vacio)'])
    hoja('Descartados', problematicos + no_encontrados + chase_sueltos + _dups)
    hoja('Ambiguos', ambiguos)
    hoja('Sin_rank', [{'EAN':c['ean_in'],'ASIN':c['asin'],'Nombre':c['fila']['nombre'],
                       'rank_act':c['r_act'],'rank90':c['r_90']} for c in sin_rank])

    # ============================================================
    # Pestana "Precio por lote": escenario con descuento por VOLUMEN (OcioStock).
    # La hoja Analisis se queda igual (precio unitario). Aqui recalculamos el beneficio
    # con el precio del LOTE y ponemos a la derecha del todo las unidades minimas para
    # lograr ese precio. Solo entran los productos cuyo lote REBAJA el precio suelto.
    # ============================================================
    COLS_LOTE = ['Nombre','EAN','ASIN','Marca','País','Precio venta (€)','PA suelto (€)',
                 'PA lote (€)','Ahorro/ud (€)','Beneficio lote (€)','Margen lote','Decisión lote',
                 'Uds. para ese precio','Coherencia']
    filas_lote = []
    for item in registros:
        vol = item.get('volumen')
        if not vol:
            continue
        pa_lote = vol['pa']; uds = vol['uds']
        pa_suelto = item.get('_pa_efectivo')
        # 🔒 Guardarrail RELATIVO (nunca un umbral absoluto de precio: Fernando compra
        # Funkos a 2,99 y llaveros a 1 €). Un descuento por volumen NEGATIVO es imposible
        # por definicion: el lote no puede salir MAS CARO que el suelto -> firma de un
        # parseo roto. Se MARCA, no se borra (regla del #56: nada desaparece).
        _coh = ''
        if pa_suelto and pa_lote and pa_lote > pa_suelto * 1.05:
            _coh = f'INCOHERENTE: lote ({pa_lote}) mas caro que suelto ({pa_suelto})'
        for dom in PAISES:
            d = item['_paises_calc'].get(dom)
            if not d or not d.get('precio') or d.get('ref_pct') is None or d.get('fee') is None:
                continue
            rr = calc_rentabilidad(d['precio'], pa_lote, d['ref_pct'], d['fee'], d['iva'],
                                   almacen=ALMACEN, com_digitales=COM_DIGITALES,
                                   isd=ISD_PAIS[dom])
            filas_lote.append([
                item['nombre'], item['ean'], item['asin'], item['marca'], dom,
                round(d['precio'], 2),
                round(pa_suelto, 2) if pa_suelto else None,
                round(pa_lote, 2),
                round(pa_suelto - pa_lote, 2) if pa_suelto else None,
                round(rr['beneficio'], 2),
                round(rr['margen'], 4),
                decision_de(rr['margen']),
                uds,
                _coh,
            ])
    filas_lote.sort(key=lambda x: (x[10] if x[10] is not None else -9), reverse=True)

    wl = wb.create_sheet('Precio por lote')
    wl.append(COLS_LOTE)
    for fl in filas_lote:
        wl.append(fl)
    for c in range(1, len(COLS_LOTE)+1):
        wl.cell(row=1, column=c).font = Font(bold=True)
    if filas_lote:
        LL = {name: get_column_letter(i+1) for i, name in enumerate(COLS_LOTE)}
        lastL = wl.max_row
        for nm in ['Precio venta (€)','PA suelto (€)','PA lote (€)','Ahorro/ud (€)','Beneficio lote (€)']:
            for row in range(2, lastL+1):
                wl[f'{LL[nm]}{row}'].number_format = '0.00'
        for row in range(2, lastL+1):
            wl[f'{LL["Margen lote"]}{row}'].number_format = '0.0%'
        decL = LL['Decisión lote']; rngL = f'{decL}2:{decL}{lastL}'
        wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO COMPRAR",{decL}2))'],
            fill=_cf_fill('FFC7CE'), font=Font(color='9C0006'), stopIfTrue=True))
        wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("VALORAR",{decL}2))'],
            fill=_cf_fill('FFEB9C'), font=Font(color='9C6500'), stopIfTrue=True))
        wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("COMPRAR",{decL}2))'],
            fill=_cf_fill('C6EFCE'), font=Font(color='006100'), stopIfTrue=True))
        wl.column_dimensions[LL['Nombre']].width = 50
        wl.column_dimensions[LL['Uds. para ese precio']].width = 18
        wl.column_dimensions[LL['Coherencia']].width = 46
        wl.freeze_panes = 'A2'
    print(f"Pestana 'Precio por lote': {len(filas_lote)} filas con descuento por volumen")

    # ============================================================
    # Pestana "Chase_manual": Funko chase de HEO SIN ASIN todavia. Pega el ASIN en
    # Supabase (tabla escaner_chase_asin) usando el enlace de busqueda; la proxima
    # corrida ya lo cruza sola y desaparece de aqui.
    # ============================================================
    if PROVEEDOR == 'HEO':
        wc = wb.create_sheet('Chase_manual')
        COLS_CHASE = ['Nombre', 'Código HEO', 'EAN caja', 'Precio caja (€)', 'Precio /6 (€)',
                      'Estado', 'Imagen', 'Buscar en Amazon', 'ASIN (pégalo en Supabase)']
        wc.append(COLS_CHASE)
        for c in range(1, len(COLS_CHASE) + 1):
            wc.cell(row=1, column=c).font = Font(bold=True)
        rc = 1
        for x in chase_pendientes:
            rc += 1
            _pc = _num(x.get('precio_caja'))
            wc.append([x.get('nombre', ''), x.get('producto_heo', ''), str(x.get('ean_caja') or ''),
                       round(_pc, 2) if _pc else None,
                       round(_pc / UNIDADES_CASE_TCG, 2) if _pc else None,
                       x.get('estado', ''),
                       'Ver imagen ↗' if x.get('imagen') else '',
                       'Buscar ↗' if x.get('link_amazon') else '', ''])
            if x.get('imagen'):
                _ci = wc.cell(row=rc, column=7); _ci.hyperlink = x['imagen']; _ci.font = Font(color='0563C1', underline='single')
            if x.get('link_amazon'):
                _cl = wc.cell(row=rc, column=8); _cl.hyperlink = x['link_amazon']; _cl.font = Font(color='0563C1', underline='single')
        for _cw, _w in ((1, 55), (2, 16), (3, 16), (7, 14), (8, 16), (9, 26)):
            wc.column_dimensions[get_column_letter(_cw)].width = _w
        for _col in (4, 5):
            for _row in range(2, wc.max_row + 1):
                wc.cell(row=_row, column=_col).number_format = '0.00'
        wc.freeze_panes = 'A2'
        print(f"Pestana 'Chase_manual': {len(chase_pendientes)} Funko chase pendientes de ASIN.")
    return wb
