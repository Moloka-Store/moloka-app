# -*- coding: utf-8 -*-
"""Banco de las REGLAS DE LECTURA DEL CSV DE BEMS (encargo BE2, 10-oct-2026): escaner2_bems.py, modulo puro.

🔴 DATOS INVENTADOS (repo publico): el CSV se fabrica aqui con la MISMA FORMA que el real (parte BE1, 1: UTF-8, «;»
sin comillas, punto decimal, la cabecera de 39 columnas con «LENGTH » al final), pero ni una REF, EAN, titulo ni
precio sale del fichero de BEMS. Las REF empiezan por 9, los EAN por 49999 (con su digito de control bien).

QUE PRUEBA:
  (1) el bueno: una fila por REF, marca/nombre/categoria, precio = PA, disponible = STOCK > 0, «100+», el STATUS al
      aviso, sin cajas ni chase, recuentos y huellas.
  (2) la fila IDENTICA repetida: una y se cuenta; la REF repetida con contenido distinto: falla, sin soltar valores.
  (3) EAN: 13 cifras con control → tal cual (el 0 delante tambien); vacio, 12 cifras o control malo →
      'ean_forma_rara', dentro y contados.
  (4) STOCK y PA: vacio = sin dato; 0 en PA = sin dato; lo que no es un numero → falla.
  (5) blind box con EAN ASSOC: un articulo a su precio de caja, sin dividir, el EAN ASSOC al aviso; «w/Chase» y
      «with Mimmy Chase» entran como figura sin aviso de chase; un «(Chase)» de Funko entra igual pero lo avisa.
  (6) el cuadre: el nombre del fichero y su fecha, la cabecera (con «LENGTH », sin una columna, con una repetida),
      la fila descuadrada, BOM y CRLF, no UTF-8.
  (7) la huella de contenido: el orden no cuenta; REF, EAN, STOCK, PA y STATUS si; el titulo no.
  (8) 🔴 los errores no sueltan valores del fichero.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

import escaner2_bems as EB  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


# 🔑 La cabecera real, en su orden (nombres de columna, no datos): 39, la ultima con un espacio al final.
CABECERA = ('EAN', 'TITRE FR', 'TITRE NL', 'TITRE UK', 'REF BEMS', 'GENRE', 'PVP', 'PA', 'STOCK', 'RELEASE DATE',
            'DATE IN', 'PEGI', 'KEYWORD', 'POIDS', 'EAN ASSOC', 'TVA', 'IMG1', 'IMG2', 'IMG3', 'IMG4', 'IMG5', 'IMG6',
            'DESC FR', 'DESC UK', 'PLATEFORME', 'CATEGORIE', 'LICENCE', 'FABRICANT', 'LANGUE', 'INTRASTAT',
            'PAYS ORIGINE', 'TAILLE', 'COULEUR', 'INNER CARTON', 'OUTER CARTON', 'STATUS', 'HEIGHT', 'WIDTH', 'LENGTH ')
NOMBRE = 'BEMS_EXPORT_10_10_2026.csv'


def ean13(cuerpo12):
    """Un EAN-13 inventado con su digito de control bien."""
    return cuerpo12 + EB._chk13(cuerpo12)


def fila(ref, **k):
    """Una fila inventada de 39 campos. Por defecto: Funko con stock 5 a 7.25 €, «Disponible en»."""
    d = {c: '' for c in CABECERA}
    d.update({'EAN': ean13('49999%07d' % int(ref or 0)),'TITRE FR': 'Titre inventé %s' % ref,
              'TITRE NL': 'Titel verzonnen %s' % ref, 'TITRE UK': 'Invented title %s' % ref, 'REF BEMS': ref,
              'PVP': '14.99', 'PA': '7.25', 'STOCK': '5', 'TVA': '21.00', 'CATEGORIE': 'Bobble Head POP',
              'FABRICANT': 'Funko', 'STATUS': 'Disponible en', 'INNER CARTON': '6', 'OUTER CARTON': '36'})
    for clave, valor in k.items():
        d[clave.replace('_', ' ')] = valor
    return [d[c] for c in CABECERA]


def csv(filas, cabecera=CABECERA, fin='\n', bom=False):
    lineas = [';'.join(cabecera)] + [';'.join(f) for f in filas]
    texto = fin.join(lineas) + fin
    return (b'\xef\xbb\xbf' if bom else b'') + texto.encode('utf-8')


def falla(contenido, nombre=NOMBRE):
    """El texto de la LecturaInvalida, o None si no falla."""
    try:
        EB.convertir(contenido, nombre)
    except EB.LecturaInvalida as ex:
        return str(ex)
    return None


# ── (1) El bueno ──────────────────────────────────────────────────────────────────────────
BASE = [fila('900%03d' % i) for i in range(20)]
BASE[1] = fila('900001', STOCK='0', STATUS='Fuera de stock')
BASE[2] = fila('900002', STOCK='100', STATUS='Últimas piezas')
BASE[3] = fila('900003', FABRICANT='Bandai Model Kit', CATEGORIE='Model Kit', PA='13.93', STOCK='100')
BASE[4] = fila('900004', FABRICANT='Pyramid', PA='1.50', STOCK='0', STATUS='Fuera de stock')
BASE[5] = fila('900005', FABRICANT='', CATEGORIE='Manga', TITRE_UK='Invented manga 5', STOCK='3')
filas, c = EB.convertir(csv(BASE), NOMBRE)
por = {f['producto_prov']: f for f in filas}
eq('bueno: una fila por REF', (len(filas), sorted(por) == sorted('900%03d' % i for i in range(20))), (20, True))
eq('bueno: recuentos', (c['n_crudo'], c['n_leidas'], c['n_duplicados'], c['n_disponibles'], c['n_agotados']),
   (20, 20, 0, 18, 2))
f0 = por['900000']
eq('bueno: marca = FABRICANT, nombre = TITRE UK, categoria = CATEGORIE',
   (f0['marca'], f0['nombre'], f0['categoria']), ('Funko', 'Invented title 900000', 'Bobble Head POP'))
eq('bueno: precio = PA en catalogo y unidad; sin escalon ni precio_pa (la base los pide los tres o ninguno)',
   (f0['precio_catalogo'], f0['precio_unidad'], f0['precio_pa'], f0['precio_escalon'], f0['uds_escalon']),
   (7.25, 7.25, None, None, None))
eq('bueno: disponible con stock 5, «5»', (f0['disponible'], f0['disponibilidad']), (True, '5'))
eq('bueno: stock 0 → no disponible, «0», y no es sin dato',
   (por['900001']['disponible'], por['900001']['disponibilidad'], por['900001']['sin_dato_disponibilidad']),
   (False, '0', False))
eq('bueno: stock 100 → «100+»', (por['900002']['disponible'], por['900002']['disponibilidad']), (True, '100+'))
eq('bueno: el techo de 100 se cuenta', c['n_stock_techo'], 2)
eq('bueno: el STATUS al aviso', (f0['aviso'], por['900001']['aviso']),
   ('STATUS: Disponible en', 'STATUS: Fuera de stock'))
eq('bueno: sin cajas ni chase, ni oferta, ni preventa',
   {(f['es_caja'], f['uds_caja'], f['es_chase'], f['en_oferta'], f['fin_oferta'], f['preorder']) for f in filas},
   {(False, None, False, False, None, False)})
eq('bueno: EAN tal cual y sin regla', (f0['ean_core'], f0['ean_original'], f0['regla']),
   (ean13('49999%07d' % 900000), ean13('49999%07d' % 900000), None))
eq('bueno: no manda ean_norm (la base la calcula: columna generada)', 'ean_norm' in f0, False)
eq('bueno: sin fabricante → marca vacía, y se cuenta si tiene stock',
   (por['900005']['marca'], c['n_sin_marca_disponibles']), (None, 1))
eq('bueno: por marca (Funko, Bandai Model Kit, Pyramid, total)',
   (c['por_marca']['funko'], c['por_marca']['bandai_model_kit'], c['por_marca']['pyramid'], c['por_marca']['total']),
   ({'filas': 17, 'disponibles': 16}, {'filas': 1, 'disponibles': 1}, {'filas': 1, 'disponibles': 0},
    {'filas': 20, 'disponibles': 18}))
eq('bueno: huellas y fecha', (len(c['huella_contenido']), len(c['md5_fichero']), c['bytes_fichero'] == len(csv(BASE)),
                              c['fecha_fichero'], c['columnas']), (32, 32, True, '2026-10-10', 39))

# ── (2) Repetidas ─────────────────────────────────────────────────────────────────────────
filas, c = EB.convertir(csv(BASE + [list(BASE[7]), list(BASE[9])]), NOMBRE)
eq('fila idéntica repetida: una por REF y se cuentan', (len(filas), c['n_crudo'], c['n_leidas'], c['n_duplicados']),
   (20, 22, 20, 2))
eq('fila idéntica repetida: no cambia la huella de contenido',
   c['huella_contenido'], EB.convertir(csv(BASE), NOMBRE)[1]['huella_contenido'])
distinta = list(BASE[7])
distinta[CABECERA.index('PA')] = '6.10'
t = falla(csv(BASE + [distinta]))
eq('REF repetida con contenido distinto: la pasada falla y dice la línea', (t is not None and 'REF BEMS' in (t or ''),
                                                                            'línea' in (t or '')), (True, True))
eq('🔴 REF repetida: el error no suelta la REF ni el precio', [x for x in ('900007', '6.10', '7.25') if x in (t or '')], [])
t = falla(csv(BASE + [fila('', TITRE_UK='Sin ref')]))
eq('REF vacía: falla', 'REF BEMS' in (t or ''), True)

# ── (3) EAN ───────────────────────────────────────────────────────────────────────────────
upc = ean13('0499999%05d' % 31)
malo = ean13('49999%07d' % 32)
malo = malo[:12] + str((int(malo[12]) + 1) % 10)
F3 = BASE + [fila('900030', EAN='', STOCK='4'), fila('900031', EAN=upc), fila('900032', EAN=malo),
             fila('900033', EAN='499999000033'), fila('900034', EAN=' %s ' % ean13('49999%07d' % 34))]
filas, c = EB.convertir(csv(F3), NOMBRE)
por = {f['producto_prov']: f for f in filas}
eq('EAN vacío: dentro, ean_forma_rara, sin ean_core, disponible',
   (por['900030']['regla'], por['900030']['ean_core'], por['900030']['disponible']), ('ean_forma_rara', None, True))
eq('EAN con 0 delante (UPC de Funko): tal cual', (por['900031']['ean_core'], por['900031']['regla']), (upc, None))
eq('EAN con el control mal: forma rara', (por['900032']['regla'], por['900032']['ean_core']), ('ean_forma_rara', None))
eq('EAN de 12 cifras: forma rara (en BEMS todos son de 13)', por['900033']['regla'], 'ean_forma_rara')
eq('EAN con espacios a los lados: sin ellos', por['900034']['ean_core'], ean13('49999%07d' % 34))
eq('EAN: recuentos (forma rara 3, vacíos 1, con stock 3)',
   (c['n_ean_forma_rara'], c['n_ean_vacio'], c['n_ean_forma_rara_disponibles'], c['n_leidas']), (3, 1, 3, 25))

# ── (4) STOCK y PA ────────────────────────────────────────────────────────────────────────
F4 = BASE + [fila('900040', STOCK=''), fila('900041', PA=''), fila('900042', PA='0'), fila('900043', PA='0.00'),
             fila('900044', PA='64.02', STOCK='1')]
filas, c = EB.convertir(csv(F4), NOMBRE)
por = {f['producto_prov']: f for f in filas}
eq('STOCK vacío: sin dato, no disponible, sin texto',
   (por['900040']['sin_dato_disponibilidad'], por['900040']['disponible'], por['900040']['disponibilidad']),
   (True, False, None))
eq('PA vacío, 0 y 0.00: sin dato de precio y sin precio',
   [(por[r]['sin_dato_precio'], por[r]['precio_unidad'], por[r]['precio_catalogo']) for r in ('900041', '900042', '900043')],
   [(True, None, None)] * 3)
eq('PA con decimales', por['900044']['precio_unidad'], 64.02)
eq('sin dato: recuentos', (c['n_sin_dato_disponibilidad'], c['n_sin_dato_precio']), (1, 3))
for nombre, k in (('STOCK con letras', {'STOCK': 'muchos'}), ('STOCK negativo', {'STOCK': '-1'}),
                  ('STOCK con decimales', {'STOCK': '2.5'}), ('PA con coma', {'PA': '7,25'}),
                  ('PA negativo', {'PA': '-7.25'}), ('PA con letras', {'PA': 'gratis'})):
    t = falla(csv(BASE + [fila('900049', **k)]))
    eq('%s: falla y dice la columna' % nombre, t is not None and ('«STOCK»' in t or '«PA»' in t), True)
    eq('🔴 %s: el error no suelta el valor' % nombre, [v for v in k.values() if v in (t or '')], [])

# ── (5) Cajas y chase ─────────────────────────────────────────────────────────────────────
caja_ean, pieza_ean = ean13('49999%07d' % 50), ean13('49999%07d' % 51)
F5 = BASE + [
    fila('900050', EAN=caja_ean, EAN_ASSOC=pieza_ean, PA='64.02', STOCK='3', FABRICANT='Inventada',
         CATEGORIE='Blind Box', TITRE_UK='Invented - Blind Box Plush (6pcs) - 14cm'),
    fila('900051', TITRE_UK='FUNKO POP Invented Hero w/Chase 1985'),
    fila('900052', TITRE_UK='INVENTED KITTY - POP N° 81 - Invented Kitty with Mimmy Chase', STOCK='100', PA='10.80'),
    fila('900053', TITRE_UK='Funko Pop! Invented Hero with Chase'),
    fila('900054', TITRE_UK='Funko Pop! Invented Villain (Chase)'),
    fila('900055', TITRE_UK='Funko Pop! Invented Villain Chase', FABRICANT='Otra marca'),
]
filas, c = EB.convertir(csv(F5), NOMBRE)
por = {f['producto_prov']: f for f in filas}
caja = por['900050']
eq('blind box: un artículo a su precio de caja, sin dividir, con su EAN',
   (caja['es_caja'], caja['uds_caja'], caja['precio_unidad'], caja['ean_core'], caja['disponible']),
   (False, None, 64.02, caja_ean, True))
eq('blind box: el EAN ASSOC al aviso, no al cruce', (caja['aviso'], pieza_ean != caja['ean_core']),
   ('STATUS: Disponible en · EAN ASSOC: %s' % pieza_ean, True))
for ref, que in (('900051', '«w/Chase»'), ('900052', '«with Mimmy Chase»'), ('900053', '«with Chase»')):
    f = por[ref]
    eq('%s entra como figura: disponible, sin regla, sin chase y sin aviso de chase' % que,
       (f['disponible'], f['regla'], f['es_chase'], 'chase' in (f['aviso'] or '').lower()), (True, None, False, False))
eq('«with Mimmy Chase»: su precio y «100+»', (por['900052']['precio_unidad'], por['900052']['disponibilidad']),
   (10.8, '100+'))
f = por['900054']
eq('«(Chase)» de Funko: entra como figura igual, pero lo dice el aviso',
   (f['disponible'], f['regla'], f['es_chase'], f['aviso']),
   (True, None, False, 'STATUS: Disponible en · parece chase suelto (entra como figura)'))
eq('«Chase» de otra marca: nada', 'chase' in (por['900055']['aviso'] or '').lower(), False)
eq('chase y EAN ASSOC: recuentos', (c['n_parece_chase'], c['n_ean_assoc']), (1, 1))
eq('regla de chase, suelta', [EB.parece_chase_suelto('Funko', t) for t in (
    'X w/Chase', 'X with Mimmy Chase', 'X (Chase)', 'X Chase', 'X (Chase Edition)', 'Chaser X', 'X w/ Chase',
    'X avec Chase', 'X Avec Chase (Exc)')],
   [False, False, True, True, True, False, False, False, False])

# ── (6) El cuadre ─────────────────────────────────────────────────────────────────────────
eq('nombre: la fecha del nombre', EB.fecha_del_nombre('BEMS_EXPORT_01_02_2027.csv').isoformat(), '2027-02-01')
for malo_nombre in ('BEMS_EXPORT_31_02_2026.csv', 'BEMS_EXPORT_10_10_26.csv', 'bems_export_10_10_2026.csv',
                    'BEMS_EXPORT_10_10_2026.csv.gz', 'otro.csv', ''):
    eq('nombre malo %r: falla' % malo_nombre, falla(csv(BASE), malo_nombre) is not None, True)
eq('cabecera sin el espacio de «LENGTH » también vale',
   EB.convertir(csv(BASE, cabecera=CABECERA[:-1] + ('LENGTH',)), NOMBRE)[1]['n_leidas'], 20)
eq('cabecera con espacios a los lados de cada nombre: vale',
   EB.convertir(csv(BASE, cabecera=tuple(' %s ' % x for x in CABECERA)), NOMBRE)[1]['n_leidas'], 20)
sin_stock = tuple('STOCKS' if x == 'STOCK' else x for x in CABECERA)
t = falla(csv(BASE, cabecera=sin_stock))
eq('cabecera sin «STOCK»: falla y la nombra', ('faltan «STOCK»' in (t or ''), '39 columnas' in (t or '')), (True, True))
doble = tuple('PA' if x == 'PVP' else x for x in CABECERA)
eq('cabecera con «PA» dos veces: falla', 'repetidas «PA»' in (falla(csv(BASE, cabecera=doble)) or ''), True)
corta = [list(f) for f in BASE]
corta[4] = corta[4][:-1]
corta[9] = corta[9] + ['un ; de más']
t = falla(csv(corta))
eq('filas descuadradas: falla con su número de línea (las de la cabecera cuentan)',
   ('2 fila(s) sin 39 campos' in (t or ''), 'líneas 6, 11' in (t or '')), (True, True))
eq('🔴 filas descuadradas: el error no suelta el contenido', 'un ; de más' in (t or ''), False)
eq('BOM y CRLF: se leen igual (mismas filas y misma huella)',
   EB.convertir(csv(BASE, fin='\r\n', bom=True), NOMBRE)[1]['huella_contenido'],
   EB.convertir(csv(BASE), NOMBRE)[1]['huella_contenido'])
eq('no UTF-8: falla', falla(';'.join(CABECERA).encode('utf-8') + b'\n\xff\xfe;x\n') is not None, True)
eq('vacío: falla', falla(b'') is not None, True)
eq('solo la cabecera: 0 leídas (los mínimos los pone la base)',
   EB.convertir(csv([]), NOMBRE)[1]['n_leidas'], 0)

# ── (7) La huella de contenido ────────────────────────────────────────────────────────────
h0 = EB.convertir(csv(BASE), NOMBRE)[1]['huella_contenido']
eq('huella: el orden de las filas no cuenta', EB.convertir(csv(BASE[::-1]), NOMBRE)[1]['huella_contenido'], h0)
for col, val in (('PA', '7.26'), ('STOCK', '6'), ('STATUS', 'Últimas piezas'),
                 ('EAN', ean13('49999%07d' % 99))):
    otra = [list(f) for f in BASE]
    otra[0][CABECERA.index(col)] = val
    eq('huella: cambia con %s' % col, EB.convertir(csv(otra), NOMBRE)[1]['huella_contenido'] != h0, True)
for col, val in (('TITRE UK', 'Otro título'), ('PVP', '99.99'), ('IMG1', 'otra-imagen.jpg')):
    otra = [list(f) for f in BASE]
    otra[0][CABECERA.index(col)] = val
    eq('huella: NO cambia con %s' % col, EB.convertir(csv(otra), NOMBRE)[1]['huella_contenido'], h0)
eq('huella: el nombre del fichero no cuenta',
   EB.convertir(csv(BASE), 'BEMS_EXPORT_11_10_2026.csv')[1]['huella_contenido'], h0)

print()
if fallos:
    print('ROJO: %d comprobación(es) fallida(s):' % len(fallos))
    for f in fallos:
        print('  - ' + f)
    sys.exit(1)
print('VERDE: todas las comprobaciones pasan.')
