# -*- coding: utf-8 -*-
"""ESCANER 2 · LA FOTO DE DISPONIBILIDAD DE TCG: las reglas de lectura del catalogo en Excel (encargo T2, 13-oct-2026,
pieza (a) del plano del parte T1, 8.0 a 8.3). MODULO PURO: bytes del Excel y cocientes de tramo dentro, filas de
disp_lectura y recuentos fuera. Ni red, ni base, ni reloj (la fecha de «hoy» entra como parametro).

El programa que baja el Excel y lo aplica es escaner2_tcg_disponibilidad.py; el que lee los tramos de la web,
escaner2_tcg_tramos.py (las reglas) con escaner2_tcg_web.py (la red). Este modulo NO lee el escaner viejo
(director_tcg_prep.py, moloka_escaner_nube.py) ni sus heredados: las reglas de TCG son suyas (Fernando, 29-sep-2026:
«cada proveedor, a su medida»).

QUE ES EL FICHERO (parte T1, 1.1, medido sobre los del 12 y el 13-oct): el catalogo ENTERO de TCG, un .xlsx con una hoja
(«Catálogo»), cabecera en la fila 1 con 17 columnas (la ultima sin nombre: la fecha de lanzamiento), ~5.500 filas. El
mismo que baja el director viejo (login + smcatalog downloadcatalog?format=excel).

🔑 LAS REGLAS (las de 8.0 del plano, con lo decidido por Fernando el 13-oct):
  1. LA LLAVE de la foto (`producto_prov`) es el EAN CRUDO del Excel, con su «C» (5.494 filas el 13-oct, 2 repetidos).
     El MISMO EAN DOS VECES: manda la fila DISPONIBLE (los dos Paladone: una Disponible y otra PreOrder); si las dos lo
     son o no lo es ninguna, la primera. La otra se cuenta (`n_duplicados`) y no entra. EAN vacio: se cuenta
     (`n_sin_gtin`) y no entra.
  2. EL EAN DE CRUCE: las cifras del EAN (ean_core); la base le saca `ean_norm` (moloka_ean_norm: sin ceros delante).
     12 o 13 cifras, tal cual; 9 a 11, rellenas con ceros hasta 13 (como OcioStock y OSMA: la base cruza sin los ceros
     de delante); con una «C» pegada, CAJA DE 6 (`es_caja`, `uds_caja` 6; `es_chase` si el nombre dice «5 + 1», como
     OcioStock). Las FORMAS RARAS (14 cifras, 18 y 23 —el codigo GS1 largo—, menos de 9, o una cola que no es la «C»:
     «H», «-2»…) entran con la regla 'ean_forma_rara' y SIN EAN de cruce: se CUENTAN, no se tiran.
  3. DISPONIBLE = «Estado producto» Disponible, Oferta o Saldo, Y Stock > 0 (Fernando: solo disponible). PreOrder →
     `preorder` true; Backorder → `disponibilidad` 'En reposición'. Fuera de lo disponible, pero GUARDADOS (como HEO).
     `disponibilidad` lleva la palabra de la web: Disponible, En reposición, Preventa, Oferta, Saldo. `en_oferta` =
     Oferta. Un estado que no es ninguno de los cinco → LecturaInvalida (con un estado nuevo no se sabe si se compra).
  4. STOCK: el del Excel tal cual (50 = «50 o más»; Fernando, 13-oct: «No creo que haga falta leer stock»). No se
     guarda: solo decide «disponible». Compra minima: ni se lee ni se enseña («Compr minima fuera tambien»).
  5. PRECIO: `precio_catalogo` = «Precio» del Excel (en una caja C, el de la caja); `precio_unidad` = ese, ÷ 6 en una
     caja (como HEO). PRECIO DE COMPRA = EL TRAMO MAS BARATO (Fernando, 7 y 8-oct): `precio_escalon` = `precio_pa` =
     Precio × COCIENTE (÷ 6 en caja), con `uds_escalon` = las unidades de ese tramo (× 6 en caja: figuras). El cociente
     lo pone el lector de tramos (escaner2_tcg_tramos.py: mas barato exacto de la ficha ÷ Precio del Excel al leerla).
     SIN COCIENTE LEIDO: el suelto (`precio_escalon` = `precio_pa` = `precio_unidad`, `uds_escalon` 1) y el aviso
     «sin tramo leído». Cociente de hace mas de 7 dias: se usa y se avisa «tramo leído hace más de 7 días».
     Portes: gratis desde 150 € sin IVA y plazo 3 dias laborables (12-oct): viven en `proveedores`, no aqui.
  6. CHASE SUELTO: el Excel no lo trae (solo dentro de la caja C, «5 + 1»). No hay regla de chase suelto.
  7. LA URL DE LA FICHA sale del nombre de la PRIMERA imagen (parte T1, 1.2: 1.366 de 1.366 casan):
     …/114730-large_default/<nombre>.jpg → https://tcgfactory.com/es/distribucion/<nombre>.html. Sin imagen con esa
     forma, o con el nombre «friendly-url-autogeneration-failed» (2 filas), sin URL (y sin cociente).
  8. «AL DIA» POR CONTENIDO, NO POR BYTES (parte T1, 1.3: la huella de bytes cambia en cada descarga): md5 de las filas
     que se suben, ordenadas por la llave, con todos sus campos (precios ya con el cociente). Si no cambia nada de lo
     que se sube, «al día»; un cambio de stock que no cambia «disponible» no es contenido nuevo.

🔴 REPO PUBLICO: nada de este modulo imprime. Sus errores (`LecturaInvalida`) dicen RECUENTOS y nombres de columna,
   nunca un valor del fichero.
"""
import hashlib
import io
import json
import re
import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

# 🔑 LA CABECERA, AL NOMBRE Y AL ORDEN (las 17 del Excel del 12 y el 13-oct-2026; la ultima, sin nombre).
COLUMNAS = (
    'EAN', 'Stock', 'Precio', 'PVPR', 'Marca', 'Tipo Producto', 'Licencia', 'Version', 'Cabecera', 'Edicion', 'Idioma',
    'Color', 'Talla', 'Fecha Prev. Entrada', 'Estado producto', 'Imágenes', '',
)
IX = {c: i for i, c in enumerate(COLUMNAS)}
UDS_CAJA = 6
# Estado del Excel → (disponibilidad que se guarda, cuenta como disponible si hay stock, preventa)
ESTADOS = {
    'Disponible': ('Disponible', True, False),
    'Oferta': ('Oferta', True, False),
    'Saldo': ('Saldo', True, False),
    'Backorder': ('En reposición', False, False),
    'PreOrder': ('Preventa', False, True),
}
AVISO_SIN_TRAMO = 'sin tramo leído'
AVISO_TRAMO_VIEJO = 'tramo leído hace más de 7 días'
DIAS_TRAMO_FRESCO = 7
BASE_FICHA = 'https://tcgfactory.com/es/distribucion/'
REGLAS = ('ean_forma_rara',)

_RE_EAN = re.compile(r'(\d*)(.*)', re.S)
_RE_IMAGEN = re.compile(r'https://tcgfactory\.com/(\d+)-large_default/([a-z0-9][a-z0-9-]*)\.jpg')
_RE_CINCO_MAS_UNO = re.compile(r'5\s*\+\s*1')
_NOMBRE_FALLIDO = 'friendly-url-autogeneration-failed'


class LecturaInvalida(ValueError):
    """El fichero no se puede subir tal cual. El texto son recuentos y nombres de columna: se puede imprimir."""


# ── El fichero ────────────────────────────────────────────────────────────────────────────
def huella_fichero(contenido):
    """(md5, bytes) del fichero tal cual se baja. Cambia en cada descarga (parte T1, 1.3): no sirve para «al día»."""
    return hashlib.md5(contenido).hexdigest(), len(contenido)


def leer_excel(contenido):
    """(cabecera, filas) de la primera hoja: la fila 1 y las de datos (las del todo vacias, fuera)."""
    import openpyxl
    try:
        libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - cualquier fallo de lectura es «no es un .xlsx», sin soltar su texto
        raise LecturaInvalida('el fichero no se abre como .xlsx') from None
    try:
        hoja = libro.worksheets[0]
        hoja.reset_dimensions()  # una dimension mal declarada no recorta columnas (como DBLine)
        todas = [list(f) for f in hoja.iter_rows(values_only=True)]
    finally:
        libro.close()
    if not todas:
        raise LecturaInvalida('el fichero no tiene filas')
    cabecera = ['' if c is None else str(c).strip() for c in todas[0]]
    while len(cabecera) > len(COLUMNAS) and cabecera[-1] == '':
        cabecera.pop()
    # La columna 17 no tiene nombre: openpyxl corta la fila 1 en la 16 (medido en la sonda T2, 13-oct). Se completa
    # con vacias; si falta una con nombre, comprobar_cabecera lo dice.
    cabecera += [''] * (len(COLUMNAS) - len(cabecera))
    filas = [f for f in todas[1:] if any(c is not None and str(c).strip() for c in f)]
    return cabecera, filas


def comprobar_cabecera(cabecera):
    """Nada si la cabecera es EXACTAMENTE la de COLUMNAS; si no, LecturaInvalida con la primera que no casa."""
    if tuple(cabecera) == COLUMNAS:
        return
    for i, col in enumerate(COLUMNAS):
        if i >= len(cabecera):
            raise LecturaInvalida(f'cabecera: falta la columna «{col}» ({len(cabecera)} columnas de {len(COLUMNAS)})')
        if cabecera[i] != col:
            if col and col in cabecera:
                raise LecturaInvalida(f'cabecera: la columna «{col}» está fuera de su sitio')
            raise LecturaInvalida(f'cabecera: la columna {i + 1} no es «{col}» (o ha cambiado de nombre)')
    raise LecturaInvalida(f'cabecera: {len(cabecera)} columnas, {len(cabecera) - len(COLUMNAS)} de más')


# ── Las piezas de una fila (puras) ────────────────────────────────────────────────────────
def texto_ean(v):
    """El EAN crudo como texto: un numero entero (o 4.98e12 con decimales a cero) sin «.0»; el resto, tal cual y sin
    los espacios de los bordes."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return str(v)
    return '' if v is None else str(v).strip()


def partir_ean(crudo):
    """(cifras del principio, cola) del EAN crudo."""
    m = _RE_EAN.fullmatch(crudo)
    return m.group(1), m.group(2)


def ean_de_cruce(crudo):
    """(ean_core, es_caja, regla) de la regla 2."""
    base, cola = partir_ean(crudo)
    if cola not in ('', 'C') or not base:
        return None, False, 'ean_forma_rara'
    es_caja = cola == 'C'
    if len(base) in (12, 13):
        return base, es_caja, None
    if 9 <= len(base) <= 11:
        return base.zfill(13), es_caja, None
    return None, es_caja, 'ean_forma_rara'


def url_de_ficha(imagenes):
    """(url, numero_imagen) de la primera imagen (regla 7); (None, numero o None) si no tiene la forma o el nombre fallo."""
    primera = str(imagenes or '').split(';')[0].strip()
    m = _RE_IMAGEN.fullmatch(primera)
    if not m:
        return None, None
    if m.group(2) == _NOMBRE_FALLIDO:
        return None, m.group(1)
    return BASE_FICHA + m.group(2) + '.html', m.group(1)


def numero(v):
    """Decimal de una celda numerica; None si esta vacia; ValueError si no es un numero finito."""
    if isinstance(v, bool):
        raise ValueError('no es un número')
    if v is None:
        return None
    if isinstance(v, (int, float)):
        d = Decimal(str(v))
    else:
        s = str(v).strip().replace(',', '.')
        if not s:
            return None
        try:
            d = Decimal(s)
        except InvalidOperation:
            raise ValueError('no es un número') from None
    if not d.is_finite():
        raise ValueError('no es un número finito')
    return d


def _texto(v):
    v = '' if v is None else str(v).strip()
    return v or None


def _f(d):
    return None if d is None else float(d)


def _cuando(v):
    """datetime con zona de un leido_en de la base (texto ISO) o de un datetime; None si no se entiende."""
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def precio_de_compra(precio, es_caja, tramo, ahora):
    """(precio_escalon, uds_escalon, precio_pa, aviso) de la regla 5. `tramo`: {'cociente', 'uds', 'leido_en'} del
    lector o None. Todo por unidad (figura) en una caja."""
    if precio is None:
        return None, None, None, None
    div = UDS_CAJA if es_caja else 1
    cociente = None if tramo is None else tramo.get('cociente')
    if cociente is not None and not isinstance(cociente, Decimal):
        cociente = Decimal(str(cociente))
    if cociente is None or not cociente.is_finite() or cociente <= 0 or not tramo.get('uds'):
        unidad = precio / div
        return unidad, 1, unidad, AVISO_SIN_TRAMO
    pa = precio * cociente / div
    aviso = None
    leido = _cuando(tramo.get('leido_en'))
    if leido is None or ahora - leido > timedelta(days=DIAS_TRAMO_FRESCO):
        aviso = AVISO_TRAMO_VIEJO
    return pa, int(tramo['uds']) * div, pa, aviso


# ── El fichero entero → filas de disp_lectura ─────────────────────────────────────────────
def convertir(contenido, tramos=None, ahora=None):
    """De los bytes del .xlsx a las filas de disp_lectura, UNA por EAN crudo, con TODAS las marcas y disponibles o no.
    `tramos`: {producto_prov: {'cociente', 'uds', 'leido_en'}} del lector de tramos (los que no esten, sin cociente).
    Devuelve (filas, cuentas, catalogo); `catalogo` es, por fila que entra, lo que necesita el lector de tramos
    ({producto_prov, url, precio_excel (Decimal), disponible, ean_core, es_caja}). LecturaInvalida si la cabecera, un
    stock, un precio o un estado no se entienden (se dicen los recuentos, no los valores).
    🔴 Ningun aviso (warnings) sale de aqui: los de openpyxl se tragan (pueden citar el fichero)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return _convertir(contenido, tramos or {}, ahora or datetime.now(timezone.utc))


def _convertir(contenido, tramos, ahora):
    cabecera, crudas = leer_excel(contenido)
    comprobar_cabecera(cabecera)
    n_col = len(COLUMNAS)
    malos = {'stock': 0, 'precio': 0, 'estado': 0}
    c = {'n_crudo': len(crudas), 'n_sin_gtin': 0, 'n_duplicados': 0, 'n_leidas': 0, 'n_disponibles': 0,
         'n_agotados': 0, 'n_sin_dato_precio': 0, 'n_disponible_sin_stock': 0, 'n_preventa': 0, 'n_reposicion': 0,
         'n_oferta': 0, 'n_saldo': 0, 'n_cajas': 0, 'n_cajas_disponibles': 0, 'n_ean_forma_rara': 0, 'n_sin_url': 0,
         'n_disponibles_sin_url': 0, 'n_con_tramo': 0, 'n_disponibles_con_tramo': 0, 'n_disponibles_sin_tramo': 0,
         'n_tramo_viejo': 0}
    elegidas = {}   # producto_prov → (fila, disponible)
    orden = []
    for f in crudas:
        f = list(f) + [None] * (n_col - len(f))

        def v(col):
            return f[IX[col]]

        llave = texto_ean(v('EAN'))
        if not llave:
            c['n_sin_gtin'] += 1
            continue
        estado = _texto(v('Estado producto'))
        if estado not in ESTADOS:
            malos['estado'] += 1
            continue
        try:
            stock = numero(v('Stock'))
            if stock is None or stock != stock.to_integral_value():
                raise ValueError('stock')
        except ValueError:
            malos['stock'] += 1
            continue
        try:
            precio = numero(v('Precio'))
            if precio is not None and precio < 0:
                raise ValueError('negativo')
        except ValueError:
            malos['precio'] += 1
            continue
        disponible = ESTADOS[estado][1] and stock > 0
        if llave in elegidas:
            c['n_duplicados'] += 1
            if disponible and not elegidas[llave][1]:
                elegidas[llave] = ((f, estado, stock, precio), disponible)
            continue
        elegidas[llave] = ((f, estado, stock, precio), disponible)
        orden.append(llave)

    problemas = [f'{n} fila(s) con «{col}» que no se entiende' for que, col, n in
                 (('stock', 'Stock', malos['stock']), ('precio', 'Precio', malos['precio']),
                  ('estado', 'Estado producto', malos['estado'])) if n]
    if problemas:
        raise LecturaInvalida(' · '.join(problemas))

    salida, catalogo = [], []
    for llave in orden:
        (f, estado, stock, precio), disponible = elegidas[llave]

        def v(col):
            return f[IX[col]]

        core, es_caja, regla = ean_de_cruce(llave)
        disp_txt, _cuenta, preventa = ESTADOS[estado]
        nombre = _texto(v('Cabecera'))
        es_chase = es_caja and bool(_RE_CINCO_MAS_UNO.search(nombre or ''))
        url, _img = url_de_ficha(v('Imágenes'))
        tramo = tramos.get(llave)
        p_escalon, uds_escalon, pa, aviso = precio_de_compra(precio, es_caja, tramo, ahora)
        unidad = None if precio is None else precio / (UDS_CAJA if es_caja else 1)
        salida.append({
            'producto_prov': llave,
            'ean_original': llave, 'ean_core': core,
            'marca': _texto(v('Marca')), 'nombre': nombre, 'categoria': _texto(v('Tipo Producto')),
            'es_caja': es_caja, 'uds_caja': UDS_CAJA if es_caja else None, 'es_chase': es_chase,
            'precio_catalogo': _f(precio), 'precio_unidad': _f(unidad),
            'precio_escalon': _f(p_escalon), 'uds_escalon': uds_escalon, 'precio_pa': _f(pa),
            'disponible': disponible, 'disponibilidad': disp_txt,
            'en_oferta': estado == 'Oferta', 'preorder': preventa, 'fin_de_vida': None,
            'regla': regla, 'aviso': aviso,
            'sin_dato_disponibilidad': False, 'sin_dato_precio': precio is None,
        })
        catalogo.append({'producto_prov': llave, 'url': url, 'precio_excel': precio, 'disponible': disponible,
                         'ean_core': core, 'es_caja': es_caja})
        con_tramo = aviso != AVISO_SIN_TRAMO and precio is not None
        c['n_leidas'] += 1
        c['n_disponibles' if disponible else 'n_agotados'] += 1
        c['n_sin_dato_precio'] += precio is None
        c['n_disponible_sin_stock'] += ESTADOS[estado][1] and not disponible
        c['n_preventa'] += preventa
        c['n_reposicion'] += estado == 'Backorder'
        c['n_oferta'] += estado == 'Oferta'
        c['n_saldo'] += estado == 'Saldo'
        c['n_cajas'] += es_caja
        c['n_cajas_disponibles'] += es_caja and disponible
        c['n_ean_forma_rara'] += regla == 'ean_forma_rara'
        c['n_sin_url'] += url is None
        c['n_disponibles_sin_url'] += url is None and disponible
        c['n_con_tramo'] += con_tramo
        c['n_disponibles_con_tramo'] += con_tramo and disponible
        c['n_disponibles_sin_tramo'] += disponible and not con_tramo
        c['n_tramo_viejo'] += aviso == AVISO_TRAMO_VIEJO

    if c['n_crudo'] != c['n_sin_gtin'] + c['n_leidas'] + c['n_duplicados']:
        raise LecturaInvalida(f"no cuadra: crudo {c['n_crudo']} ≠ sin EAN {c['n_sin_gtin']} + leídas {c['n_leidas']} + "
                              f"repetidas {c['n_duplicados']}")
    c['huella_contenido'] = huella_contenido(salida)
    return salida, c, catalogo


def huella_contenido(filas):
    """md5 de las filas que se suben, ordenadas por la llave, con todos sus campos (regla 8)."""
    lineas = [json.dumps(f, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
              for f in sorted(filas, key=lambda x: x['producto_prov'])]
    return hashlib.md5('\n'.join(lineas).encode('utf-8')).hexdigest()
