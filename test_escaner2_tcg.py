# -*- coding: utf-8 -*-
"""Banco de las REGLAS de TCG en el escaner 2 (encargo T2, 13-oct-2026): escaner2_tcg.py (la foto del Excel) y
escaner2_tcg_tramos.py (la ficha, el listado y que fichas tocan).

SIN RED, SIN SECRETOS Y SIN BASE. 🔴 DATOS INVENTADOS (repo publico): ni un precio, ni un EAN ni una URL de TCG de
verdad. El Excel lo fabrica este banco con openpyxl con la cabecera medida (17 columnas, la ultima sin nombre); las
fichas y las tarjetas, con la ESTRUCTURA medida en la web (parte T1) y numeros inventados.

QUE PRUEBA:
  (A) el Excel: la llave cruda con su «C», el repetido (manda el disponible), la caja de 6 (precio por figura, chase
      con «5+1»), los cinco estados, el stock que decide disponible, las formas raras contadas, el EAN de 11 cifras,
      la URL de la ficha desde la primera imagen, y lo que no se entiende (cabecera, estado, stock) → LecturaInvalida;
  (B) el precio de compra: el cociente aplicado al Precio del Excel (tambien en caja), sin cociente el suelto con su
      aviso, el cociente viejo con el suyo; y la huella de contenido (un stock que no cambia «disponible» no la mueve;
      un cociente nuevo, si);
  (C) la ficha: precio actual, tabla de tramos, suelto exacto (rel, o el actual en una oferta), el mas barato, el
      cociente, y que lo que no tiene la forma medida PARA (sin sesion, sin precio, otro tipo de descuento, celdas que
      no casan); el EAN de la ficha (normal y caja con GS1 largo);
  (D) el listado: el filtro de estado, las tarjetas («desde» y suelto) y los desajustes con lo guardado;
  (E) que fichas tocan y en que orden (nuevas, marcadas, viejas; disponibles con URL; intentos fallidos esperan 24 h).
  Y la mitad roja: mutantes de cinco reglas (repetido, caja, cociente, oferta, desajuste) ponen el banco en rojo.
"""
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
import escaner2_tcg as tcg  # noqa: E402
import escaner2_tcg_tramos as tr  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def lanza(nombre, excepcion, f, *a, **k):
    try:
        f(*a, **k)
    except excepcion as ex:
        eq(nombre, True, True)
        return str(ex)
    except Exception as ex:  # noqa: BLE001
        eq(nombre + ' (otra excepción: %s)' % type(ex).__name__, False, True)
        return None
    eq(nombre + ' (no ha lanzado)', False, True)
    return None


AHORA = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
IMG = 'https://tcgfactory.com/%d-large_default/%s.jpg'


def fila(ean, stock=50, precio=10.0, estado='Disponible', nombre='Cosa inventada', marca='Marca X',
         imagen=None, **k):
    d = {'EAN': ean, 'Stock': stock, 'Precio': precio, 'PVPR': 20, 'Marca': marca, 'Tipo Producto': 'Merchandising-Cosas',
         'Licencia': None, 'Version': None, 'Cabecera': nombre, 'Edicion': None, 'Idioma': None, 'Color': None,
         'Talla': None, 'Fecha Prev. Entrada': None, 'Estado producto': estado,
         'Imágenes': imagen if imagen is not None else IMG % (abs(hash(str(ean))) % 99999 + 1, 'cosa-inventada-%s' % str(ean).lower()),
         '': '2026-01-01'}
    d.update(k)
    return d


def excel(filas, cabecera=None):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'Catálogo'
    cab = list(cabecera if cabecera is not None else tcg.COLUMNAS)
    ws.append([c if c else None for c in cab])
    for f in filas:
        ws.append([f.get(c) for c in tcg.COLUMNAS])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ── (A) El Excel ─────────────────────────────────────────────────────────────────────────
FILAS = [
    fila('8000000000017'),                                                       # 0 disponible normal
    fila('8000000000024', estado='PreOrder', stock=0),                           # 1 repetido: la de preventa...
    fila('8000000000024', stock=7),                                              # 2 ...y la disponible: manda esta
    fila('800000000031C', precio=60.0, nombre='Funko POP! 999 Cosa Case 5+1 Chase'),   # 3 caja de 6 con chase
    fila('800000000048C', precio=60.0, nombre='Funko POP! 998 Otra CASE', stock=0),     # 4 caja sin «5+1», agotada
    fila('8000000000055', estado='Backorder', stock=0),                          # 5 en reposición
    fila('8000000000062', estado='PreOrder', stock=0),                           # 6 preventa
    fila('8000000000079', estado='Oferta', stock=3),                             # 7 oferta
    fila('8000000000086', estado='Saldo', stock=-1),                             # 8 saldo sin stock
    fila('8000000000093', estado='Disponible', stock=0),                         # 9 disponible sin stock
    fila('74427800001', stock=12),                                               # 10 11 cifras
    fila('08000000000109', stock=4),                                             # 11 14 cifras: rara
    fila('800000000116H', stock=4),                                              # 12 cola H: rara
    fila(None, stock=4),                                                         # 13 sin EAN
    fila(8000000000123, stock=5),                                                # 14 EAN numérico
    fila('8000000000130', imagen=IMG % (77, 'friendly-url-autogeneration-failed')),  # 15 sin URL
    fila('8000000000147', imagen='https://otra.invalid/foto.png'),               # 16 sin URL
]
lect, c, cat = tcg.convertir(excel(FILAS), {}, AHORA)
por = {f['producto_prov']: f for f in lect}
catp = {e['producto_prov']: e for e in cat}
eq('A1 crudo 17 = sin EAN 1 + leídas 15 + repetidas 1', (c['n_crudo'], c['n_sin_gtin'], c['n_leidas'], c['n_duplicados']),
   (17, 1, 15, 1))
eq('A2 el repetido: manda la fila disponible', (por['8000000000024']['disponible'], por['8000000000024']['preorder']),
   (True, False))
x = por['800000000031C']
eq('A3 caja C: llave cruda, EAN de cruce sin la C, caja de 6, chase por «5+1»',
   (x['ean_core'], x['es_caja'], x['uds_caja'], x['es_chase']), ('800000000031', True, 6, True))
eq('A4 caja C: precio_catalogo el de la caja, precio_unidad por figura', (x['precio_catalogo'], x['precio_unidad']),
   (60.0, 10.0))
eq('A5 caja sin «5+1»: sin chase', por['800000000048C']['es_chase'], False)
eq('A6 Backorder: en reposición, no disponible', (por['8000000000055']['disponibilidad'], por['8000000000055']['disponible'],
                                                   por['8000000000055']['preorder']), ('En reposición', False, False))
eq('A7 PreOrder: preventa', (por['8000000000062']['disponibilidad'], por['8000000000062']['preorder']), ('Preventa', True))
eq('A8 Oferta con stock: disponible y en oferta', (por['8000000000079']['disponible'], por['8000000000079']['en_oferta']),
   (True, True))
eq('A9 Saldo con stock -1 y Disponible con 0 (y la caja agotada): no disponibles',
   (por['8000000000086']['disponible'], por['8000000000093']['disponible'], c['n_disponible_sin_stock']), (False, False, 3))
eq('A10 11 cifras: rellena con ceros hasta 13', por['74427800001']['ean_core'], '0074427800001')
eq('A11 14 cifras y cola H: forma rara, sin EAN de cruce, contadas',
   (por['08000000000109']['regla'], por['08000000000109']['ean_core'], por['800000000116H']['regla'],
    por['800000000116H']['ean_core'], c['n_ean_forma_rara']), ('ean_forma_rara', None, 'ean_forma_rara', None, 2))
eq('A12 EAN numérico: sin «.0»', '8000000000123' in por, True)
eq('A13 URL de la ficha desde la primera imagen',
   catp['8000000000017']['url'], 'https://tcgfactory.com/es/distribucion/cosa-inventada-8000000000017.html')
eq('A14 sin URL: nombre fallido y otra forma', (catp['8000000000130']['url'], catp['8000000000147']['url'], c['n_sin_url']),
   (None, None, 2))
eq('A15 disponibles: 0, 2, 3, 7, 10, 11, 12, 14, 15, 16', c['n_disponibles'], 10)
eq('A16 ningún campo de más para disp_lectura (sin _privados)', sorted({k for f in lect for k in f if k.startswith('_')}), [])
eq('A17 la llave y ean_original, el crudo', (por['800000000031C']['producto_prov'], por['800000000031C']['ean_original']),
   ('800000000031C', '800000000031C'))
cab_mala = list(tcg.COLUMNAS)
cab_mala[2], cab_mala[3] = cab_mala[3], cab_mala[2]
t = lanza('A18 cabecera movida: LecturaInvalida', tcg.LecturaInvalida, tcg.convertir, excel(FILAS, cab_mala))
eq('A18b y dice qué columna, sin valores', 'Precio' in (t or ''), True)
lanza('A19 estado desconocido: LecturaInvalida', tcg.LecturaInvalida, tcg.convertir,
      excel([fila('8000000000017', estado='Agotadísimo')]))
lanza('A20 stock que no es un número: LecturaInvalida', tcg.LecturaInvalida, tcg.convertir,
      excel([fila('8000000000017', stock='muchos')]))
lanza('A21 un xlsx que no lo es: LecturaInvalida', tcg.LecturaInvalida, tcg.convertir, b'no soy un excel')
eq('A22 la cabecera de 16 celdas (la 17 sin nombre) vale', tcg.convertir(excel([fila('8000000000017')]))[1]['n_leidas'], 1)

# ── (B) El precio de compra y la huella ──────────────────────────────────────────────────
P = Decimal('10.00')
TRAMO = {'cociente': Decimal('0.976666134667'), 'uds': 12, 'leido_en': (AHORA - timedelta(days=1)).isoformat()}
pe, uds, pa, aviso = tcg.precio_de_compra(P, False, TRAMO, AHORA)
eq('B1 con cociente: Precio × cociente, uds del tramo, sin aviso', (round(pa, 6), uds, aviso, pe == pa),
   (Decimal('9.766661'), 12, None, True))
pe, uds, pa, aviso = tcg.precio_de_compra(Decimal('60.00'), True, TRAMO, AHORA)
eq('B2 caja: por figura (÷ 6) y uds en figuras (× 6)', (round(pa, 6), uds), (Decimal('9.766661'), 72))
pe, uds, pa, aviso = tcg.precio_de_compra(P, False, None, AHORA)
eq('B3 sin cociente: el suelto, 1 ud y «sin tramo leído»', (pa, uds, aviso), (P, 1, 'sin tramo leído'))
viejo = dict(TRAMO, leido_en=(AHORA - timedelta(days=8)).isoformat())
eq('B4 cociente de hace 8 días: se usa y se avisa', tcg.precio_de_compra(P, False, viejo, AHORA)[2:],
   (P * Decimal('0.976666134667'), 'tramo leído hace más de 7 días'))
eq('B5 sin precio: todo vacío', tcg.precio_de_compra(None, False, TRAMO, AHORA), (None, None, None, None))
lect2, c2, _ = tcg.convertir(excel(FILAS), {'8000000000017': TRAMO}, AHORA)
x = next(f for f in lect2 if f['producto_prov'] == '8000000000017')
eq('B6 convertir aplica el cociente a su fila', (round(x['precio_pa'], 6), x['uds_escalon'], x['aviso']), (9.766661, 12, None))
eq('B7 recuentos de tramo', (c2['n_con_tramo'], c2['n_disponibles_con_tramo'], c2['n_disponibles_sin_tramo']), (1, 1, 9))
eq('B8 un cociente nuevo cambia la huella', c2['huella_contenido'] != c['huella_contenido'], True)
FILAS_STOCK = [dict(f) for f in FILAS]
FILAS_STOCK[0]['Stock'] = 49
eq('B9 un stock que no cambia «disponible»: la misma huella', tcg.convertir(excel(FILAS_STOCK), {}, AHORA)[1]['huella_contenido'],
   c['huella_contenido'])
FILAS_PRECIO = [dict(f) for f in FILAS]
FILAS_PRECIO[0]['Precio'] = 10.5
eq('B10 un precio que cambia: otra huella', tcg.convertir(excel(FILAS_PRECIO), {}, AHORA)[1]['huella_contenido']
   != c['huella_contenido'], True)
eq('B11 la huella cabe en disp_pasada (32 hex)', len(c['huella_contenido']) == 32 and all(ch in '0123456789abcdef'
                                                                                         for ch in c['huella_contenido']), True)

# ── (C) La ficha ─────────────────────────────────────────────────────────────────────────
def ficha(precio='10.00', tabla=None, eans=('8000000000017',), sesion=True, tipo='percentage', regular=None):
    """Una ficha con la ESTRUCTURA medida en la web (parte T1); todo lo demás, inventado."""
    filas = ''
    if tabla is not None:
        cab = ''.join('<td>A partir de %d uds.</td>' % u for u, _r, _d in tabla)
        celdas = ''.join('<td rel="%s" dis="%s"> 1,00€ </td>' % (r, d) for _u, r, d in tabla)
        filas = ('<section class="product-discounts"><table class="table-product-discounts"><tbody><tr>%s</tr>'
                 '<tr data-discount-type="%s" data-discount="-1.5" data-discount-quantity="12">%s</tr></tbody></table>'
                 '</section>' % (cab, tipo, celdas))
    e = ''.join('<div class="product-availability-date"><label class="label">EAN:</label> <span>%s</span></div>' % x
                for x in eans)
    reg = '<span class="regular-price">%s €</span>' % regular if regular else ''
    return ('<html><head><title>x</title><script>var a = "<div class=\\"current-price\\">";</script></head>'
            '<body id="product" class="lang-es %s product-id-1"><div class="product-reference"><span itemprop="sku">X-1</span></div>%s'
            '<div class="product-prices"><div class="product-price"><div class="row">'
            '<div class="current-price col-sm-6 col-xs-6"><span itemprop="price" content="%s">%s €</span>%s</div></div></div>'
            '<div class="preciopvp"><label class="label">PVPR:</label> <span itemprop="price" >20.00€</span></div></div>'
            '<form><input type="hidden" name="id_product" value="1">%s<input type="number" name="qty" min="1"></form>'
            '<div class="product-miniature"><div class="product-availability-date"><label class="label">EAN:</label>'
            '<span>9999999999994</span></div></div></body></html>'
            % ('usuariologeado' if sesion else '', e, precio, precio, reg, filas))


TABLA = [(2, '10.000000', '0.005800'), (6, '10.000000', '0.017500'), (12, '10.000000', '0.023400')]
f = tr.leer_ficha(ficha(tabla=TABLA))
eq('C1 precio actual, tramos y EAN', (f['precio_actual'], [u for u, _r, _d in f['tramos']], f['eans'][0]),
   (Decimal('10.00'), [2, 6, 12], '8000000000017'))
t = tr.tramo_de_ficha(f, Decimal('10.00'))
eq('C2 el más barato: rel × (1 − dis) del tramo de 12, exacto', (t['mas_barato'], t['uds_mas_barato'], t['suelto_exacto']),
   (Decimal('9.766000000000'), 12, Decimal('10.000000')))
eq('C3 cociente = más barato ÷ Precio del Excel', t['cociente'], Decimal('0.976600000000'))
eq('C4 × 12 al céntimo, como la cesta', (Decimal('10.00') * t['cociente'] * 12).quantize(Decimal('0.01')), Decimal('117.19'))
t = tr.tramo_de_ficha(f, Decimal('20.00'))
eq('C5 con el Excel en otro precio, el cociente lo lleva (precio × cociente = el de la web)',
   (Decimal('20.00') * t['cociente']).quantize(Decimal('0.000001')), Decimal('9.766000'))
# Una oferta: el precio actual ya rebajado y el tramo sobre el precio de antes (rel), como el T1 midió.
f = tr.leer_ficha(ficha(precio='16.00', tabla=[(6, '20.000000', '0.250000')], regular='20,00'))
t = tr.tramo_de_ficha(f, Decimal('16.00'))
eq('C6 oferta: suelto = el actual (no rel); el tramo, rel × 0,75', (t['suelto_exacto'], t['mas_barato'], t['uds_mas_barato']),
   (Decimal('16.00'), Decimal('15.00000000'), 6))
eq('C7 oferta: el cociente es 15/16, no 0,75', t['cociente'], Decimal('0.937500000000'))
f = tr.leer_ficha(ficha(precio='16.00', tabla=[(6, '20.000000', '0.100000')]))
t = tr.tramo_de_ficha(f, Decimal('16.00'))
eq('C8 oferta con un tramo más caro que ella: gana el suelto (1 ud)', (t['mas_barato'], t['uds_mas_barato'], t['cociente']),
   (Decimal('16.00'), 1, Decimal('1.000000000000')))
f = tr.leer_ficha(ficha(precio='12.30'))
t = tr.tramo_de_ficha(f, Decimal('24.60'))
eq('C9 sin tabla: el actual, 1 ud; el Excel al doble da cociente 0,5', (f['tramos'], t['mas_barato'], t['uds_mas_barato'],
                                                                       t['cociente'], t['rel']),
   ([], Decimal('12.30'), 1, Decimal('0.500000000000'), None))
eq('C10 sin precio en el Excel: sin cociente', tr.tramo_de_ficha(f, None)['cociente'], None)
lanza('C11 sin sesión: para', tr.FichaNoEntendida, tr.leer_ficha, ficha(sesion=False))
lanza('C12 sin precio actual: para', tr.FichaNoEntendida, tr.leer_ficha, ficha().replace('itemprop="price" content="10.00"', 'itemprop="price"'))
lanza('C13 descuento que no es porcentaje: para', tr.FichaNoEntendida, tr.leer_ficha, ficha(tabla=TABLA, tipo='amount'))
lanza('C14 celdas que no casan: para', tr.FichaNoEntendida, tr.leer_ficha,
      ficha(tabla=TABLA).replace('<td>A partir de 12 uds.</td>', ''))
lanza('C15 un dis que no es un número: para', tr.FichaNoEntendida, tr.leer_ficha, ficha(tabla=[(6, '10.000000', 'mucho')]))
lanza('C16 una columna sin «A partir de»: para', tr.FichaNoEntendida, tr.leer_ficha,
      ficha(tabla=TABLA).replace('A partir de 6 uds.', 'Seis'))
lanza('C17 HTML vacío: para', tr.FichaNoEntendida, tr.leer_ficha, '')
lanza('C17b la URL lleva a una categoría (el producto ya no está ahí): sin ficha, NO para', tr.FichaNoEsProducto, tr.leer_ficha,
      ficha(tabla=TABLA).replace('id="product"', 'id="category"'))
lanza('C17c una categoría sin sesión: para (la sesión se mira antes)', tr.FichaNoEntendida, tr.leer_ficha,
      ficha(tabla=TABLA, sesion=False).replace('id="product"', 'id="category"'))
eq('C18 el EAN de la ficha casa sin ceros delante', tr.ean_casa(['008000000000017'], '8000000000017', '8000000000017', False), True)
eq('C19 el de otro producto, no', tr.ean_casa(['8000000000024'], '8000000000017', '8000000000017', False), False)
eq('C20 caja: el GS1 largo de la web casa con la C del Excel (GTIN-14 sin indicador ni control)',
   tr.ean_casa(['01' + '10800000000039' + '2110000'], '800000000031C', '800000000031', True), True)
eq('C21 caja: un GS1 de otra caja, no', tr.ean_casa(['01' + '10800000000046' + '2110000'], '800000000031C', '800000000031', True), False)
eq('C22 forma rara: las cifras del crudo', tr.ean_casa(['8000000000116'], '800000000116H', None, False), False)
eq('C23 sin EAN en la ficha: no casa', tr.ean_casa([], '8000000000017', '8000000000017', False), False)

# ── (D) El listado ───────────────────────────────────────────────────────────────────────
def tarjeta(url, desde=None, suelto='10,00', estado='Disponible'):
    d = ('<div class="row first_line"><div class="col-sm-6"><span itemprop="price" class="price">desde <strong>%s€</strong>'
         '</span></div></div>' % desde) if desde else '<div class="row first_line"></div>'
    return ('<article class="product-miniature js-product-miniature 1 caja_producto_cat %s" data-id-product="1">'
            '<div class="product-container"><h5 class="product-title" itemprop="name"><a href="%s">Cosa…</a></h5>'
            '<div class="product-info right-block"><div class="row"><div class="pvpr"><span>PVPR: 20.00€</span></div></div>%s'
            '<form><div class="product-price-and-shipping"><div class="row second_line"><div class="price">'
            '<span itemprop="price" class="price">%s €</span></div></div></div><input type="number" name="qty" value="1" min="1">'
            '</form></div></div></article>' % (estado, url, d, suelto))


U = 'https://tcgfactory.com/es/distribucion/cosa-%d.html'
html = tarjeta(U % 1, '9,77') + tarjeta(U % 2) + tarjeta(U % 3, '1.234,56', '1.300,00', 'Oferta')
cards = tr.tarjetas(html)
eq('D1 tarjetas: url, estado, desde y suelto (con miles)', [(x['url'], x['estado'], x['desde'], x['suelto']) for x in cards],
   [(U % 1, 'Disponible', Decimal('9.77'), Decimal('10.00')), (U % 2, 'Disponible', None, Decimal('10.00')),
    (U % 3, 'Oferta', Decimal('1234.56'), Decimal('1300.00'))])
G = {U % 1: {'producto_prov': 'A', 'suelto_web': '10.00', 'mas_barato': '9.766000', 'uds_mas_barato': 12},
     U % 2: {'producto_prov': 'B', 'suelto_web': '10.00', 'mas_barato': '10.00', 'uds_mas_barato': 1},
     U % 4: {'producto_prov': 'D', 'suelto_web': '10.00', 'mas_barato': '10.00', 'uds_mas_barato': 1}}
eq('D2 cuadra (redondeado con redondeado): ningún desajuste', tr.desajustes(cards[:2], G), set())
eq('D3 el «desde» ha cambiado', tr.desajustes(tr.tarjetas(tarjeta(U % 1, '9,80')), G), {'A'})
eq('D4 el suelto ha cambiado', tr.desajustes(tr.tarjetas(tarjeta(U % 2, None, '10,50')), G), {'B'})
eq('D5 aparece un tramo donde no había', tr.desajustes(tr.tarjetas(tarjeta(U % 2, '9,50')), G), {'B'})
eq('D6 desaparece el tramo', tr.desajustes(tr.tarjetas(tarjeta(U % 1, None)), G), {'A'})
eq('D7 una tarjeta sin tramo guardado no dice nada', tr.desajustes(tr.tarjetas(tarjeta(U % 9, '1,00')), G), set())
FORM = ('<form id="af_form"><input type="hidden" name="id_category" value="70"><input type="hidden" name="nb_items" value="27">'
        '<input type="hidden" name="page" value="1">'
        '<label><input type="checkbox" name="f[53][]" value="a1"><span class="name">Disponible</span><span class="count">9</span></label>'
        '<label><input type="checkbox" name="f[53][]" value="a2"><span class="name">En reposición</span></label>'
        '<label><input type="checkbox" name="f[53][]" value="a3"><span class="name">Saldo</span></label></form>')
eq('D8 el filtro de estado: ocultos, su campo y Disponible/Saldo (no En reposición)', tr.formulario_filtro(FORM),
   ([('id_category', '70'), ('nb_items', '27'), ('page', '1')], 'f[53][]', ['a1', 'a3']))
lanza('D9 sin el filtro: para', tr.ListadoNoEntendido, tr.formulario_filtro, '<form id="otro"></form>')
lanza('D10 sin opciones buenas: para', tr.ListadoNoEntendido, tr.formulario_filtro, FORM.replace('Disponible', 'X').replace('Saldo', 'Y'))

# ── (E) Qué fichas tocan ─────────────────────────────────────────────────────────────────
def e(k, disponible=True, url=True):
    return {'producto_prov': k, 'url': (U % hash(k)) if url else None, 'disponible': disponible, 'precio_excel': P,
            'ean_core': k, 'es_caja': False}


CAT = [e('nueva'), e('agotada', disponible=False), e('sin_url', url=False), e('marcada'), e('vieja_8'), e('vieja_9'),
       e('fresca'), e('fallo_reciente'), e('fallo_antiguo')]
GUARD = {
    'marcada': {'leido_en': (AHORA - timedelta(days=1)).isoformat(), 'cociente': 0.9, 'pide_relectura': AHORA.isoformat(),
                'intento_resultado': 'ok'},
    'vieja_8': {'leido_en': (AHORA - timedelta(days=8)).isoformat(), 'cociente': 0.9, 'intento_resultado': 'ok'},
    'vieja_9': {'leido_en': (AHORA - timedelta(days=9)).isoformat(), 'cociente': 0.9, 'intento_resultado': 'ok'},
    'fresca': {'leido_en': (AHORA - timedelta(days=2)).isoformat(), 'cociente': 0.9, 'intento_resultado': 'ok'},
    'fallo_reciente': {'intento_en': (AHORA - timedelta(hours=3)).isoformat(), 'intento_resultado': 'sin_ficha'},
    'fallo_antiguo': {'intento_en': (AHORA - timedelta(hours=30)).isoformat(), 'intento_resultado': 'otro_ean'},
}
cola, total = tr.pendientes(CAT, GUARD, AHORA, 10)
eq('E1 orden: nuevas (y fallos de hace más de 24 h), marcadas, viejas (la más vieja primero)',
   ([x['producto_prov'] for x in cola], total), (['nueva', 'fallo_antiguo', 'marcada', 'vieja_9', 'vieja_8'], 5))
eq('E2 el tope corta la cola y dice cuántas tocaban', ([x['producto_prov'] for x in tr.pendientes(CAT, GUARD, AHORA, 2)[0]],
                                                       tr.pendientes(CAT, GUARD, AHORA, 2)[1]), (['nueva', 'fallo_antiguo'], 5))
eq('E3 con tope 0, ninguna', tr.pendientes(CAT, GUARD, AHORA, 0)[0], [])

# ── La mitad roja: cinco reglas rotas, cinco rojos ───────────────────────────────────────
def muta(modulo, nombre, sustituto, prueba):
    viejo = getattr(modulo, nombre)
    setattr(modulo, nombre, sustituto)
    try:
        rojo = not prueba()
    except Exception:  # noqa: BLE001
        rojo = True
    finally:
        setattr(modulo, nombre, viejo)
    eq('M ' + nombre + ': el mutante se pone rojo', rojo, True)


muta(tcg, 'ESTADOS', dict(tcg.ESTADOS, Disponible=('Disponible', False, False)),
     lambda: {f['producto_prov']: f for f in tcg.convertir(excel(FILAS), {}, AHORA)[0]}['8000000000024']['preorder'] is False)
muta(tcg, 'UDS_CAJA', 1,
     lambda: {f['producto_prov']: f for f in tcg.convertir(excel(FILAS), {}, AHORA)[0]}['800000000031C']['precio_unidad'] == 10.0)
muta(tcg, 'precio_de_compra', lambda p, caja, t, a: (p, 1, p, None),
     lambda: round({f['producto_prov']: f for f in tcg.convertir(excel(FILAS), {'8000000000017': TRAMO}, AHORA)[0]}
                   ['8000000000017']['precio_pa'], 6) == 9.766661)
muta(tr, 'redondeo', lambda d: d,
     lambda: tr.tramo_de_ficha(tr.leer_ficha(ficha(precio='16.00', tabla=[(6, '20.000000', '0.250000')])),
                               Decimal('16.00'))['suelto_exacto'] == Decimal('16.00')
     and tr.desajustes(cards[:2], G) == set())
muta(tr, 'desajustes', lambda cards, g: set(), lambda: tr.desajustes(tr.tarjetas(tarjeta(U % 1, '9,80')), G) == {'A'})

print()
print('TODO OK' if not fallos else 'FALLOS: %d (%s)' % (len(fallos), ', '.join(fallos)))
sys.exit(1 if fallos else 0)
