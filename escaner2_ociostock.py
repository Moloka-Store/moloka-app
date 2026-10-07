# -*- coding: utf-8 -*-
"""ESCANER 2 · LA FOTO DE DISPONIBILIDAD DE OCIOSTOCK: las reglas de lectura del fichero (encargo OC2, 07-oct-2026).
MODULO PURO: bytes del fichero dentro, filas de disp_lectura y recuentos fuera. Ni red, ni base, ni reloj.

El programa que baja el fichero y lo aplica es escaner2_ociostock_disponibilidad.py. Este modulo NO lee el escaner
viejo ni sus heredados: las reglas de OcioStock son suyas (Fernando, 29-sep-2026: «cada proveedor, a su medida»), y
donde se parecen a las del viejo se dice aqui con que pieza se parecen.

QUE ES EL FICHERO (parte OC1 del 07-oct-2026, medido sobre el del dia): el catalogo ENTERO de OcioStock, un CSV con
54 columnas separadas por «;», en utf-8 (con BOM), ~30.300 filas, ~15.000 con stock. Se rehace una vez por noche.

🔑 LAS OCHO REGLAS (decididas en el encargo OC2; las cifras, del fichero del 07-oct-2026):
  1. LA LLAVE de la foto es `id_producto` de OcioStock, no el EAN: hay hasta tres filas por EAN base (suelta, caja
     y chase). Un `id_producto` vacio o repetido deja la pasada 'fallida': con la llave dudosa no se sube nada.
  2. EL EAN DE CRUCE son las CIFRAS DEL PRINCIPIO del campo `ean`, sin la cola (« C6», « Chase», « rosa», una «c»
     pegada…). 🔴 `ean_norm` (columna calculada de la base) sale de ese EAN base, NUNCA del campo crudo:
     moloka_ean_norm('889698679282 C6') deja el 6 pegado. Con 14 cifras (GTIN-14) se queda el EAN-13 de dentro
     (las cifras 2-13 con su digito de control), la variante que `variantes_ean` del viejo añade a un codigo de 14.
     Con 9 a 11 cifras se rellena con ceros hasta 13 (como OSMA: la base cruza sin los ceros de delante, igual que
     `norm` del viejo). Con menos de 9 cifras entra con la regla 'ean_forma_rara' y sin EAN de cruce.
     SIN EAN (el campo vacio o sin ninguna cifra delante): se CUENTA (`n_sin_gtin`) y NO entra.
  3. CAJA DE 6: el sufijo EXACTO « C6», o marca FUNKO con «5 + 1» en el nombre. Su precio es POR FIGURA y NO se
     divide: el fichero ya lo trae dividido (en la web, la caja de 6 vale 6 veces el precio por unidad del
     fichero; p. ej., inventado: 10,00 €/ud y caja de 6 a 60,00 €).
     🔴 La «c» pegada al EAN NO es caja en OcioStock (34 peluches «surtido» de Disney, Marvel, Play by Play…), aunque
     el `partir_ean` del viejo la leeria como caja de TCG. Una caja «5 + 1» es caja CON chase (5 figuras y 1 chase):
     sale con `es_chase` true, como la caja con chase de HEO; una « C6» sin «5 + 1», sin chase (no se sabe que lo
     lleve).
  4. CHASE SUELTO, FUERA (se guarda en la foto con `regla` 'chase_suelto' y `es_chase` true; no se tira): marca FUNKO
     y (sufijo EXACTO « Chase» o «chase» al final del nombre o entre parentesis, salvo «with Chase» / «w/ Chase»).
     NUNCA en otras marcas (el «Chase» de la Patrulla Canina es el perro). El sufijo del EAN manda sobre el nombre,
     como en el viejo. 🔴 Casos que obligan (del fichero real): «Joker with Hat Chase» y «Inosuke… Exclusive Chase»
     comparten EAN con fichas nuestras normales, sin sufijo: salen como chase y NO como la figura.
  5. DISPONIBLE = stock_disponible > 0 y disponible_para_reserva ≠ 1 y reserva_prepago ≠ 1 (Fernando: «Preventas
     evidentemente no entran, solo quiero ver lo que este disponible para comprar ya»). `preorder` = una de las dos
     marcas de reserva. Stock VACIO = sin dato de disponibilidad (la base conserva lo de antes, como en HEO).
  6. PRECIO: (a) `precio_catalogo` = `precio_unidad` = `precio_distribuidores` tal cual (el unitario crudo, el que
     usa el viejo); (b) `precio_escalon` = el minimo entre ese y todos los importes de `txt_precios_volumen`, con
     `uds_escalon` = las unidades desde las que vale (1 si gana el unitario; a igual precio, el de menos unidades);
     (c) `precio_pa` = (b) × 0,99 (Fernando: «El 1% es descuento por pagar por trasnferencia, cosa que siempre
     hacemos»). SIN el filtro del 50 % del viejo (`MIN_RATIO_LOTE`): los escalones de menos de la mitad del unitario
     se comprobaron en la web y son reales. Porte 0 (Fernando: los portes, «siempre gratis»).
  7. SUELTA Y CAJA DEL MISMO EAN BASE: en la foto quedan las dos (cada una con su `id_producto`). Elegir la de menor
     PA, marcada «caja de 6», es de quien lea (pieza 4 del plano), no de la foto.
  8. CADA PASADA GUARDA el md5, los bytes y el maximo de `fecha_ultima_modificacion` del fichero (`huella`).

🔴 REPO PUBLICO: nada de este modulo imprime. Sus errores (`LecturaInvalida`) dicen RECUENTOS y nombres de columna,
   nunca un valor del fichero.
"""
import csv
import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

# 🔑 LA CABECERA, AL NOMBRE Y AL ORDEN (las 54 columnas del fichero del 07-oct-2026). Si cambia una, la pasada es
#    'fallida' y dice cual: con columnas movidas, un precio se podria leer de otra.
COLUMNAS = (
    'id_producto', 'fecha_alta', 'fecha_ultima_modificacion', 'nombre', 'referencia', 'descripcion',
    'descripcion_html', 'divisa', 'precio_distribuidores', 'precio_neto', 'iva', 'precio_bruto', 'envio',
    'disponibilidad', 'hay_stock', 'stock_disponible', 'categoria_principal', 'product_url', 'marca', 'ean',
    'plazo_de_entrega', 'tipo_promocion', 'url_imagen_principal', 'url_imagen_principal_grande',
    'min_uds_por_pedido', 'max_uds_por_pedido', 'min_importe_por_pedido', 'max_importe_por_pedido', 'unidad_medida',
    'fecha_lanzamiento', 'con_numeros_serie', 'reserva_prepago', 'en_liquidacion', 'jerarquia_marca',
    'xml_info_peso', 'xml_info_oferta', 'xml_info_dimensiones', 'xml_info_refrigerado', 'xml_info_novedad',
    'xml_info_envases', 'xml_info_codigos_barras', 'xml_info_familias', 'xml_info_otros_idiomas', 'csv_imagenes',
    'xml_info_tallas_colores', 'precio_neto_recomendado', 'hs_intrastat_code', 'xml_campos_dinamicos',
    'xml_info_pack', 'precio_bruto_recomendado', 'xml_precios_volumen', 'txt_precios_volumen',
    'disponible_para_reserva', 'last_column',
)
SEPARADOR = ';'
UDS_CAJA = 6
DESCUENTO_TRANSFERENCIA = Decimal('0.99')
MARCA_CHASE_Y_CAJA = 'FUNKO'
REGLAS = ('chase_suelto', 'ean_forma_rara')

_RE_EAN = re.compile(r'(\d*)(.*)', re.S)
# Las del nombre, con la forma de las del viejo (escaner2_heredado_nube.py: _RE_CAJA6, _RE_CHASE_NOM y _RE_CON_CHASE),
# escritas aqui: este modulo no importa el viejo ni sus copias.
_RE_CINCO_MAS_UNO = re.compile(r'5\s*\+\s*1', re.I)
_RE_CHASE_NOMBRE = re.compile(r'\bchase\b\s*$|\([^)]*\bchase\b[^)]*\)', re.I)
_RE_CON_CHASE = re.compile(r'\b(?:w/|with)\s*ch(?:ase)?\b', re.I)
_RE_PRECIO = re.compile(r'\d+(?:[.,]\d+)?')
_RE_TRAMO = re.compile(r'(\d+):(\d*):(\d+(?:[.,]\d+)?)')
_RE_ENTERO = re.compile(r'\d+')
_FORMATO_FECHA = '%Y-%m-%d %H:%M:%S'


class LecturaInvalida(ValueError):
    """El fichero no se puede subir tal cual. El texto son recuentos y nombres de columna: se puede imprimir."""


# ── El fichero ────────────────────────────────────────────────────────────────────────────
def huella(contenido):
    """(md5, bytes) del fichero tal cual se lee (regla 8)."""
    return hashlib.md5(contenido).hexdigest(), len(contenido)


def leer_csv(contenido):
    """(cabecera, filas) del CSV: utf-8 con o sin BOM, separado por «;». LecturaInvalida si no es texto utf-8."""
    try:
        texto = contenido.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise LecturaInvalida('el fichero no es texto utf-8') from None
    lector = csv.reader(io.StringIO(texto, newline=''), delimiter=SEPARADOR)
    cabecera = next(lector, None)
    if cabecera is None:
        raise LecturaInvalida('el fichero está vacío')
    return [c.strip() for c in cabecera], [f for f in lector if any(c.strip() for c in f)]


def comprobar_cabecera(cabecera):
    """{columna: indice} si la cabecera es EXACTAMENTE la de COLUMNAS; si no, LecturaInvalida con la primera que
    falta, sobra o esta fuera de su sitio."""
    if tuple(cabecera) == COLUMNAS:
        return {c: i for i, c in enumerate(COLUMNAS)}
    for i, col in enumerate(COLUMNAS):
        if i >= len(cabecera):
            raise LecturaInvalida(f'cabecera: falta la columna «{col}» ({len(cabecera)} columnas de {len(COLUMNAS)})')
        if cabecera[i] != col:
            if col in cabecera:
                raise LecturaInvalida(f'cabecera: la columna «{col}» está fuera de su sitio')
            raise LecturaInvalida(f'cabecera: falta la columna «{col}» (o ha cambiado de nombre)')
    raise LecturaInvalida(f'cabecera: {len(cabecera)} columnas, {len(cabecera) - len(COLUMNAS)} de más '
                          f'tras «{COLUMNAS[-1]}»')


# ── Las piezas de una fila (puras) ────────────────────────────────────────────────────────
def _chk13(cuerpo12):
    d = [int(x) for x in cuerpo12][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10)


def partir_ean(crudo):
    """(base, cola) del campo `ean` (regla 2): base = las cifras del principio ('' si no hay); cola = lo que sigue,
    tal cual (« C6», « Chase», «c», « rosa»…). Los espacios de los bordes, normales o duros, fuera."""
    m = _RE_EAN.fullmatch(str(crudo or '').strip())
    return m.group(1), m.group(2)


def ean_de_cruce(base):
    """(ean_core, regla) del EAN base (regla 2): 12 o 13 cifras tal cual; 14 → el EAN-13 de dentro (cifras 2-13 y su
    digito de control); 9 a 11 → rellenado con ceros hasta 13; menos de 9 → (None, 'ean_forma_rara')."""
    if len(base) in (12, 13):
        return base, None
    if len(base) == 14:
        return base[1:13] + _chk13(base[1:13]), None
    if 9 <= len(base) <= 11:
        return base.zfill(13), None
    return None, 'ean_forma_rara'


def clasificar(cola, marca, nombre):
    """(es_caja, es_chase, chase_suelto) de una fila (reglas 3 y 4). El sufijo exacto del EAN manda; luego el
    nombre, y el nombre solo en FUNKO."""
    funko = (marca or '').strip().upper() == MARCA_CHASE_Y_CAJA
    nombre = nombre or ''
    if cola == ' C6':
        cinco_mas_uno = funko and bool(_RE_CINCO_MAS_UNO.search(nombre))
        return True, cinco_mas_uno, False
    if cola == ' Chase':
        return (False, True, True) if funko else (False, False, False)
    if funko and _RE_CINCO_MAS_UNO.search(nombre):
        return True, True, False
    if funko and _RE_CHASE_NOMBRE.search(nombre) and not _RE_CON_CHASE.search(nombre):
        return False, True, True
    return False, False, False


def precio(texto):
    """Decimal de un precio del fichero; None si esta vacio; ValueError si no es un numero."""
    s = str(texto or '').strip()
    if not s:
        return None
    if not _RE_PRECIO.fullmatch(s):
        raise ValueError('precio no numérico')
    return Decimal(s.replace(',', '.'))


def tramos(texto):
    """[(unidades_desde, precio)] de `txt_precios_volumen` («6:11:9.5|12::8.9»: desde:hasta:precio). [] si esta
    vacio; ValueError si un tramo no tiene esa forma."""
    s = str(texto or '').strip()
    if not s:
        return []
    salida = []
    for trozo in s.split('|'):
        m = _RE_TRAMO.fullmatch(trozo.strip())
        if not m:
            raise ValueError('tramo con otra forma')
        salida.append((int(m.group(1)), Decimal(m.group(3).replace(',', '.'))))
    return salida


def escalon(unitario, lista_tramos):
    """(precio_escalon, uds_escalon, precio_pa) de la regla 6: el minimo del unitario y de los tramos (a igual precio,
    el de menos unidades) y ese × 0,99. Sin unitario, (None, None, None)."""
    if unitario is None:
        return None, None, None
    p, uds = min([(unitario, 1)] + [(pr, u) for u, pr in lista_tramos])
    return p, uds, p * DESCUENTO_TRANSFERENCIA


def _decimal_a_base(d):
    return None if d is None else float(d)


def _texto(v):
    v = '' if v is None else str(v).strip()
    return v or None


# ── El fichero entero → filas de disp_lectura ─────────────────────────────────────────────
def convertir(cabecera, filas):
    """De las filas del CSV a las de disp_lectura, UNA por `id_producto`, con TODAS las marcas y disponibles o no.
    Devuelve (filas, cuentas). LecturaInvalida si la cabecera no es la de COLUMNAS, una fila no tiene sus 54 campos,
    un id falta o se repite, o un precio, un tramo, un stock o una marca de reserva no se entienden (se dicen
    los recuentos, no los valores)."""
    ix = comprobar_cabecera(cabecera)
    n_col = len(COLUMNAS)
    malas = [f for f in filas if len(f) != n_col]
    if malas:
        raise LecturaInvalida(f'{len(malas)} fila(s) sin sus {n_col} campos')

    salida = []
    vistos, repetidos, sin_id = set(), set(), 0
    malos = {'precio': 0, 'tramos': 0, 'stock': 0, 'reserva': 0}
    c = {'n_crudo': len(filas), 'n_sin_gtin': 0, 'n_leidas': 0, 'n_disponibles': 0, 'n_agotados': 0,
         'n_sin_dato_disponibilidad': 0, 'n_sin_dato_precio': 0, 'n_preventa': 0, 'n_preventa_con_stock': 0,
         'n_cajas': 0, 'n_cajas_disponibles': 0, 'n_cajas_cinco_mas_uno_sin_c6_disponibles': 0,
         'n_chase_suelto': 0, 'n_chase_suelto_disponibles': 0, 'n_ean_forma_rara': 0, 'n_gtin14': 0,
         'n_escalon_gana': 0}
    fecha_max = None
    for f in filas:
        def v(col):
            return f[ix[col]]

        pid = v('id_producto').strip()
        if not pid:
            sin_id += 1
            continue
        if pid in vistos:
            repetidos.add(pid)
            continue
        vistos.add(pid)

        try:
            t = datetime.strptime(v('fecha_ultima_modificacion').strip(), _FORMATO_FECHA)
            fecha_max = t if fecha_max is None or t > fecha_max else fecha_max
        except ValueError:
            pass  # una fecha rara no invalida la fila: solo no cuenta para el maximo

        base, cola = partir_ean(v('ean'))
        if not base:
            c['n_sin_gtin'] += 1
            continue
        core, regla = ean_de_cruce(base)
        es_caja, es_chase, chase_suelto = clasificar(cola, v('marca'), v('nombre'))
        if chase_suelto:
            regla = 'chase_suelto'

        try:
            unitario = precio(v('precio_distribuidores'))
        except ValueError:
            malos['precio'] += 1
            unitario = None
        try:
            lista_tramos = tramos(v('txt_precios_volumen'))
        except ValueError:
            malos['tramos'] += 1
            lista_tramos = []
        p_escalon, uds_escalon, pa = escalon(unitario, lista_tramos)

        stock_txt = v('stock_disponible').strip()
        if stock_txt and not _RE_ENTERO.fullmatch(stock_txt):
            malos['stock'] += 1
        reservas = (v('disponible_para_reserva').strip(), v('reserva_prepago').strip())
        if any(r not in ('', '0', '1') for r in reservas):
            malos['reserva'] += 1
        preventa = '1' in reservas
        sin_dato_disp = not stock_txt
        con_stock = bool(stock_txt) and _RE_ENTERO.fullmatch(stock_txt) is not None and int(stock_txt) > 0
        disponible = con_stock and not preventa

        salida.append({
            'producto_prov': pid,
            'ean_original': _texto(v('ean')), 'ean_core': core,
            'marca': _texto(v('marca')), 'nombre': _texto(v('nombre')), 'categoria': _texto(v('categoria_principal')),
            'es_caja': es_caja, 'uds_caja': UDS_CAJA if es_caja else None, 'es_chase': es_chase,
            'precio_catalogo': _decimal_a_base(unitario), 'precio_unidad': _decimal_a_base(unitario),
            'precio_escalon': _decimal_a_base(p_escalon), 'uds_escalon': uds_escalon,
            'precio_pa': _decimal_a_base(pa),
            'disponible': disponible, 'disponibilidad': None,
            'en_oferta': None, 'preorder': preventa, 'fin_de_vida': None,
            'regla': regla, 'aviso': None,
            'sin_dato_disponibilidad': sin_dato_disp, 'sin_dato_precio': unitario is None,
        })
        c['n_leidas'] += 1
        c['n_disponibles' if disponible else 'n_agotados'] += 1
        c['n_sin_dato_disponibilidad'] += sin_dato_disp
        c['n_sin_dato_precio'] += unitario is None
        c['n_preventa'] += preventa
        c['n_preventa_con_stock'] += preventa and con_stock
        c['n_cajas'] += es_caja
        c['n_cajas_disponibles'] += es_caja and disponible
        c['n_cajas_cinco_mas_uno_sin_c6_disponibles'] += es_caja and cola != ' C6' and disponible
        c['n_chase_suelto'] += chase_suelto
        c['n_chase_suelto_disponibles'] += chase_suelto and disponible
        c['n_ean_forma_rara'] += regla == 'ean_forma_rara'
        c['n_gtin14'] += len(base) == 14
        c['n_escalon_gana'] += uds_escalon is not None and uds_escalon > 1

    problemas = []
    if sin_id:
        problemas.append(f'{sin_id} fila(s) sin id_producto (la llave)')
    if repetidos:
        problemas.append(f'{len(repetidos)} id_producto repetido(s) (la llave)')
    for que, n in malos.items():
        if n:
            problemas.append({'precio': f'{n} fila(s) con precio_distribuidores que no es un número',
                              'tramos': f'{n} fila(s) con txt_precios_volumen de otra forma',
                              'stock': f'{n} fila(s) con stock_disponible que no es un entero',
                              'reserva': f'{n} fila(s) con disponible_para_reserva o reserva_prepago que no es 0 ni 1'}[que])
    if problemas:
        raise LecturaInvalida(' · '.join(problemas))
    if c['n_crudo'] != c['n_sin_gtin'] + c['n_leidas']:
        raise LecturaInvalida(f"no cuadra: crudo {c['n_crudo']} ≠ sin EAN {c['n_sin_gtin']} + leídas {c['n_leidas']}")
    c['fecha_max'] = fecha_max.strftime(_FORMATO_FECHA) if fecha_max else None
    return salida, c
