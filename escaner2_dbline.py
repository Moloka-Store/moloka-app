# -*- coding: utf-8 -*-
"""ESCANER 2 · LA FOTO DE DISPONIBILIDAD DE DBLINE: las reglas de lectura del catalogo general (encargo DB2-A,
09-oct-2026). MODULO PURO: bytes del Excel dentro, filas y recuentos fuera. Ni red, ni base, ni reloj: la fecha de
«hoy» entra como parametro.

Las reglas salen del parte DB1 del 09-oct-2026 (punto 10.0, con su dato) y de lo que decidio Fernando. Este modulo NO
lee el escaner viejo ni sus heredados; donde se parece a OcioStock (escaner2_ociostock.py), se dice.

QUE ES EL FICHERO (parte DB1, 1.1): un .xlsx con una hoja. Fila 1, el titulo con la fecha del dia («Catalogo generale
<dd-mm-aaaa>» en la copia del navegador; la de servidor, en ingles, no la habia visto nadie: encargo DB2-B, 9-oct); la
fila 2 lleva el codigo de cliente y el nombre de Moloka (🔴 no se lee ni se cuenta nunca); fila 3, la cabecera de 29
columnas, en italiano (navegador) o en ingles (servidor), siempre en el mismo orden (por servidor: fila 3 y 16
traducidas en las 25 ultimas corridas del director viejo); desde la 4, una fila por producto (~18.700, ~12.500 con
unidades).

🔑 LAS REGLAS:
  1. LA LLAVE es el codigo propio de DBLine: el texto que enseña la formula =HYPERLINK(<enlace>,"<CODIGO>") de
     «Codice/Link». Se lee con openpyxl SIN data_only (con data_only, o con pandas, sale vacia). Se contrasta con el
     COD_PRODOTTO del base64 del `param` del enlace. Codigo vacio, repetido o que no case → LecturaInvalida.
  2. EAN: sin espacios (vienen rellenados a la derecha hasta 20); solo cifras; 12 o 13 → ean_core tal cual; 11 →
     '0' + crudo si forma un UPC-A de 12 con su digito de control bien (las fundas Ultra Pro); vacio o raro → regla
     'ean_forma_rara', ean_core None, se cuenta y NO se tira.
  3. DISPONIBLE = Disponibili > 0 (Fernando: «Solo quiero ver lo que este disponible para comprar hoy»). TELEFONARE y
     NEW con unidades entran (Fernando: «si que entren»). preorder = Note PRENOTAZIONE. Note se guarda tal cual.
  4. PRECIO: precio_catalogo = Prezzo; precio_unidad = Prezzo promo si es > 0 y su fin (solo el dia) es hoy o
     despues; si no, Prezzo (Fernando: «Calcula con el precio vigente de compra en cada momento»). en_oferta y
     fin_oferta (solo el dia). Promo > 0 sin fin: con Prezzo, y se cuenta (n_promo_sin_fin). Sin escalones, sin el 1 % de transferencia, sin cajas (es_caja false siempre).
     EL MINIMO (encargo DB5, 10-oct-2026; Fernando: «Tengo un precio tan negociado en DBLine que hasta las ofertas
     salen mas caras muchas veces que mi precio normal»): la promo vigente que NO es mas barata que Prezzo (igual o
     mas cara) no vale: precio_unidad = Prezzo, en_oferta false y fin_oferta vacio, como un producto sin promo; se
     cuenta (n_promo_mas_cara). Con Prezzo vacio o 0, como antes (la promo vigente vale).
  5. CHASE SUELTO: solo marca FUNKO (Publisher) con «chase» al final del nombre o entre parentesis, sin «w/» ni
     «with» → regla 'chase_suelto' y es_chase true (como OcioStock, regla 4). «w/Chase» es la figura normal.
  6. FECHAS: solo el dia (la hora que traen es la de la descarga y no significa nada).
  7. HUELLA «AL DIA» POR CONTENIDO: md5 de las filas ordenadas por codigo con (codigo, disponible, precio_unidad,
     precio_catalogo, fin_oferta, ean_core, nota). El EAN y la nota (PRENOTAZIONE, NEW, TELEFONARE…) van dentro
     (Cowork, DB2-B): un cambio de EAN o de reserva no se da por «al dia». Ademas, el md5 y los bytes del fichero
     (cambian en cada descarga).
  8. CUADRE: la fila 1 trae la FECHA DE HOY (Madrid), diga lo que diga alrededor (italiano o ingles) y con el separador
     que sea (- / .); si la fecha admite dos lecturas (dd-mm y mm-dd), vale si una de las dos es hoy (encargo DB2-B).
     29 columnas exactas; ≥ MIN_FILAS filas y ≥ MIN_DISPONIBLES disponibles. Si no, LecturaInvalida.
  9. RECUENTOS POR MARCA para la semana de medicion: total, Funko y Pyramid (filas y disponibles); y, tras aplicar,
     lo que ha cambiado EN ESA PASADA por marca (recuentos_cambios, de las filas de disp_cambio).
 10. SIN AVISOS AL REGISTRO: convertir() corre bajo warnings.catch_warnings(); un aviso de openpyxl puede citar el
     fichero (encargo DB2-B).

🔴 REPO PUBLICO: nada de este modulo imprime. Sus errores (`LecturaInvalida`) dicen RECUENTOS y nombres de columna,
   nunca un valor del fichero. Si falla la fila 1 o la cabecera, el texto de la excepcion lleva solo la FORMA de esa
   fila (letras → a, cifras → 9) y en que fila estan «Publisher» y «EAN»; su texto real, recortado a 80 caracteres, va
   aparte (`LecturaInvalida.privado`, `para_la_base()`): solo a disp_pasada.motivo, que es privada. Nunca la fila 2.
"""
import base64
import binascii
import hashlib
import io
import json
import re
import warnings
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

import openpyxl

# 🔑 LA CABECERA (fila 3), AL NOMBRE Y AL ORDEN: las 29 del parte DB1, 1.1. Las dos listas van en el MISMO orden; las
#    filas se leen por posicion, asi que el idioma no cambia que columna es cual.
COLUMNAS_IT = (
    'Cat 1', 'Cat 2', 'Cat 3', 'Genere', 'Publisher', 'ID Listino', 'Link immagine', 'Codice/Link', 'Descrizione',
    'SKU', 'EAN', 'Note', 'Data uscita', 'Disponibili', 'Listino (€)', 'Sconto 1 (%)', 'Sconto 2 (%)', 'Prezzo (€)',
    'Iva (%)', 'RRP', 'Promo', 'Scadenza promo', 'Prezzo promo (€)', 'MOQ', 'Pcs/MC', 'Peso (gr)', 'X (mm)', 'Y (mm)',
    'Z (mm)',
)
COLUMNAS_EN = (
    'Cat 1', 'Cat 2', 'Cat 3', 'Genre', 'Publisher', 'Price List ID', 'Image Link', 'Code/Link', 'Description',
    'SKU', 'EAN', 'Notes', 'Release date', 'Available', 'List Price (€)', 'Discount 1 (%)', 'Discount 2 (%)',
    'Price (€)', 'VAT (%)', 'RRP', 'Promo', 'Promo Expiration', 'Promo Price (€)', 'MOQ', 'Pcs/MC', 'Weight (gr)',
    'X (mm)', 'Y (mm)', 'Z (mm)',
)
IX = {c: i for i, c in enumerate(COLUMNAS_IT)}  # la posicion de cada columna, por su nombre italiano
FILA_TITULO = 1
FILA_CABECERA = 3
MIN_FILAS = 16500        # el 90 % de las 18.414 mas bajas de 3 meses (parte DB1, 10.0.10)
MIN_DISPONIBLES = 11000  # hoy ~12.500
MARCA_CHASE = 'FUNKO'
MARCAS_MEDIDAS = (('funko', 'FUNKO'), ('pyramid', 'PYRAMID'))
NOTA_PREVENTA = 'PRENOTAZIONE'
REGLAS = ('chase_suelto', 'ean_forma_rara')
# Los cambios de una pasada (disp_cambio.tipo) que cuenta la semana de medicion, con su nombre en el registro.
CAMBIOS_MEDIDOS = (('entra_catalogo', 'entran'), ('vuelve_catalogo', 'vuelven'), ('sale_catalogo', 'salen'),
                   ('pasa_disponible', 'a_disponible'), ('pasa_agotado', 'a_agotado'),
                   ('cambia_precio', 'cambio_precio'))

# Una fecha en la fila 1: dia y mes (en el orden que sea) y año de 4 cifras, o año-mes-dia; separador - / o .
_RE_FECHA_DMA = re.compile(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)')
_RE_FECHA_AMD = re.compile(r'(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)')
RECORTE = 80  # caracteres del texto real de una fila que van a la base cuando falla
FILAS_BUSCAR_CABECERA = 6
_RE_HIPERVINCULO = re.compile(r'=\s*HYPERLINK\(\s*"([^"]*)"\s*[,;]\s*"([^"]*)"\s*\)\s*', re.I)
_RE_CHASE_NOMBRE = re.compile(r'\bchase\b\s*$|\([^)]*\bchase\b[^)]*\)', re.I)
_RE_CON_CHASE = re.compile(r'(?:\bw/|\bwith\b)\s*chase\b', re.I)
_RE_NUMERO = re.compile(r'-?\d+(?:[.,]\d+)?')
_FORMATOS_DIA = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y')


class LecturaInvalida(ValueError):
    """El fichero no se puede subir tal cual. El texto son recuentos, nombres de columna y formas: se puede imprimir.
    `privado` (si lo hay) lleva el texto real de la fila que falla, recortado: SOLO para la base (para_la_base)."""

    def __init__(self, texto, privado=None):
        super().__init__(texto)
        self.privado = privado

    def para_la_base(self):
        return str(self) + (f' · {self.privado}' if self.privado else '')


def forma(texto):
    """La forma de un texto para el registro publico: letras → a, cifras → 9, lo demas igual; recortada a RECORTE."""
    return ''.join('a' if ch.isalpha() else '9' if ch.isdigit() else ch for ch in str(texto))[:RECORTE]


def texto_de_fila(fila):
    """Las celdas no vacias de una fila, unidas por un espacio."""
    return ' '.join(str(c).strip() for c in (fila or []) if c is not None and str(c).strip())


# ── El fichero ────────────────────────────────────────────────────────────────────────────
def huella_fichero(contenido):
    """(md5, bytes) del fichero tal cual se lee. Cambia en cada descarga (la hora va pegada a las fechas)."""
    return hashlib.md5(contenido).hexdigest(), len(contenido)


def leer_excel(contenido):
    """(fila1, cabecera, filas, donde) del .xlsx: las celdas de la fila 1, la fila 3, las filas desde la 4 (las del
    todo vacias, fuera) y `donde`: en que fila estan «Publisher» y «EAN» (de las 6 primeras) y cuantas columnas tiene
    la fila 3, para decirlo si algo falla. 🔴 SIN data_only: la llave vive en una formula y con data_only sale vacia."""
    try:
        libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=False)
    except Exception:  # noqa: BLE001 - cualquier fallo de lectura es «no es un .xlsx», sin soltar su texto
        raise LecturaInvalida('el fichero no se abre como .xlsx') from None
    try:
        hoja = libro.worksheets[0]
        hoja.reset_dimensions()  # (Cowork, 9-oct) una dimension mal declarada por el servidor no recorta columnas
        todas = [list(f) for f in hoja.iter_rows(values_only=True)]
    finally:
        libro.close()
    if len(todas) < FILA_CABECERA:
        raise LecturaInvalida(f'el fichero tiene {len(todas)} fila(s): no llega a la cabecera (fila {FILA_CABECERA})')
    fila1 = list(todas[FILA_TITULO - 1] or [])
    cabecera = ['' if c is None else str(c).strip() for c in todas[FILA_CABECERA - 1]]
    while cabecera and cabecera[-1] == '':
        cabecera.pop()
    filas = [f for f in todas[FILA_CABECERA:] if any(c is not None and str(c).strip() for c in f)]
    # Solo el NUMERO de la fila que tiene «Publisher» y «EAN» (la fila 2 se mira, pero nada suyo sale de aqui).
    fila_pub = next((i + 1 for i, f in enumerate(todas[:FILAS_BUSCAR_CABECERA])
                     if {'Publisher', 'EAN'} <= {str(c).strip() for c in f if c is not None}), None)
    donde = (f'«Publisher» y «EAN» en la fila {fila_pub}' if fila_pub else
             f'sin «Publisher» y «EAN» en las {FILAS_BUSCAR_CABECERA} primeras filas')
    donde += f'; {len(cabecera)} columnas en la fila {FILA_CABECERA}'
    return fila1, cabecera, filas, donde


def _dia(a, m, d):
    try:
        return date(a, m, d)
    except ValueError:
        return None


def fechas_de_la_fila(texto):
    """Los dias que puede decir el texto de la fila 1: cada dd-mm-aaaa en sus dos lecturas (dd-mm y mm-dd) y cada
    aaaa-mm-dd; las que no son un dia, fuera."""
    dias = set()
    for m in _RE_FECHA_DMA.finditer(texto):
        x, y, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dias.update(d for d in (_dia(a, y, x), _dia(a, x, y)) if d)
    for m in _RE_FECHA_AMD.finditer(texto):
        d = _dia(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            dias.add(d)
    return dias


def fecha_del_titulo(fila1, hoy, donde=''):
    """HOY si la fila 1 trae la fecha de hoy (regla 8), diga lo que diga alrededor. Si no, LecturaInvalida: al texto,
    la forma de la fila y `donde`; a `privado`, su texto real recortado."""
    texto = texto_de_fila(fila1)
    if hoy in fechas_de_la_fila(texto):
        return hoy
    raise LecturaInvalida(f'fila 1: no trae la fecha de hoy ({hoy:%d-%m-%Y}) · su forma: «{forma(texto)}»'
                          + (f' · {donde}' if donde else ''),
                          privado=f'su texto: «{texto[:RECORTE]}»')


def comprobar_cabecera(cabecera, donde=''):
    """'it' o 'en' si la cabecera es EXACTAMENTE una de las dos; si no, LecturaInvalida con la cuenta de columnas y la
    primera que no casa (nombres de columna esperados, nunca valores), la forma de la fila 3 y `donde`; su texto real,
    recortado, a `privado`."""
    if tuple(cabecera) == COLUMNAS_IT:
        return 'it'
    if tuple(cabecera) == COLUMNAS_EN:
        return 'en'
    if len(cabecera) != len(COLUMNAS_IT):
        que = f'cabecera: {len(cabecera)} columnas, y son {len(COLUMNAS_IT)}'
    else:
        que = next((f'cabecera: la columna {i + 1} no es «{it}» ni «{en}» (o se mezclan los idiomas)'
                    for i, (it, en) in enumerate(zip(COLUMNAS_IT, COLUMNAS_EN)) if cabecera[i] not in (it, en)),
                   'cabecera: mezcla columnas en italiano y en inglés')
    texto = texto_de_fila(cabecera)
    raise LecturaInvalida(f'{que} · su forma: «{forma(texto)}»' + (f' · {donde}' if donde else ''),
                          privado=f'su texto: «{texto[:RECORTE]}»')


# ── Las piezas de una fila (puras) ────────────────────────────────────────────────────────
def codigo_de_formula(celda):
    """El codigo propio de DBLine de la celda «Codice/Link» (regla 1), o None si no es la formula esperada, si el
    texto esta vacio o si no casa con el COD_PRODOTTO del enlace."""
    m = _RE_HIPERVINCULO.fullmatch(str(celda or ''))
    if not m:
        return None
    enlace, codigo = m.group(1), m.group(2).strip()
    if not codigo:
        return None
    param = parse_qs(urlparse(enlace).query).get('param', [''])[0]
    try:
        crudo = base64.b64decode(param + '=' * (-len(param) % 4), validate=False)
        cod_enlace = json.loads(crudo.decode('utf-8')).get('COD_PRODOTTO')
    except (binascii.Error, ValueError, UnicodeDecodeError, AttributeError):
        return None
    return codigo if isinstance(cod_enlace, str) and cod_enlace.strip() == codigo else None


def _chk13(cuerpo12):
    d = [int(x) for x in cuerpo12][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10)


def ean_de_cruce(crudo):
    """(ean_core, regla) del EAN (regla 2): sin espacios; 12 o 13 cifras tal cual; 11 → '0' + crudo si es un UPC-A
    de 12 con su digito de control bien; lo demas (vacio incluido) → (None, 'ean_forma_rara')."""
    if isinstance(crudo, float) and crudo.is_integer():
        crudo = int(crudo)  # (Cowork, 9-oct) un EAN numerico llega a veces como 4999999000016.0
    if isinstance(crudo, int) and not isinstance(crudo, bool):
        crudo = str(crudo)
    s = re.sub(r'\s+', '', str(crudo or ''))
    if not s.isdigit() or not s.isascii():
        return None, 'ean_forma_rara'
    if len(s) in (12, 13):
        return s, None
    if len(s) == 11:
        upc = '0' + s
        if _chk13('0' + upc[:11]) == upc[11]:
            return upc, None
    return None, 'ean_forma_rara'


def es_chase_suelto(marca, nombre):
    """Regla 5: FUNKO y «chase» al final o entre parentesis, sin «w/» ni «with» delante."""
    if MARCA_CHASE not in str(marca or '').upper():
        return False
    nombre = str(nombre or '')
    return bool(_RE_CHASE_NOMBRE.search(nombre)) and not _RE_CON_CHASE.search(nombre)


def numero(v):
    """Decimal de una celda numerica; None si esta vacia; ValueError si no es un numero."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError('no es un número')
    if isinstance(v, (int, float, Decimal)):
        d = Decimal(str(v))
        if not d.is_finite():
            raise ValueError('no es un número finito')  # (Cowork, 9-oct) NaN e Infinity, fuera
        return d
    s = str(v).strip()
    if not s:
        return None
    if not _RE_NUMERO.fullmatch(s):
        raise ValueError('no es un número')
    return Decimal(s.replace(',', '.'))


def solo_dia(v):
    """El dia de una celda de fecha (regla 6): la hora, fuera. None si esta vacia; ValueError si no es una fecha."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    primero = s.replace('T', ' ').split(' ')[0]
    for fmt in _FORMATOS_DIA:
        try:
            return datetime.strptime(primero, fmt).date()
        except ValueError:
            pass
    raise ValueError('no es una fecha')


def precio_vigente(prezzo, promo, fin, hoy):
    """(precio_unidad, en_oferta) de la regla 4: la promo si es > 0, su fin es hoy o despues y es mas barata que
    Prezzo (DB5: el minimo); si no, Prezzo. Con Prezzo vacio o 0, la promo vigente vale (como antes de DB5)."""
    if promo is not None and promo > 0 and fin is not None and fin >= hoy:
        if prezzo is not None and prezzo > 0 and promo >= prezzo:
            return prezzo, False
        return promo, True
    return prezzo, False


def _texto(v):
    v = '' if v is None else str(v).strip()
    return v or None


def _num_txt(d):
    return '' if d is None else format(d.normalize(), 'f')


def huella_contenido(filas):
    """md5 de las filas ordenadas por codigo con (codigo, disponible, precio_unidad, precio_catalogo, fin_oferta,
    ean_core, nota) (regla 7). No mira la hora de las fechas ni nada que cambie en cada descarga sin cambiar el
    contenido (unidades, nombre)."""
    lineas = []
    for f in sorted(filas, key=lambda x: x['producto_prov']):
        lineas.append('|'.join((f['producto_prov'], '1' if f['disponible'] else '0',
                                _num_txt(f['_precio_unidad']), _num_txt(f['_precio_catalogo']),
                                f['fin_oferta'] or '', f['ean_core'] or '', f['disponibilidad'] or '')))
    return hashlib.md5('\n'.join(lineas).encode('utf-8')).hexdigest()


# ── El fichero entero → filas de disp_lectura ─────────────────────────────────────────────
def convertir(contenido, hoy, min_filas=MIN_FILAS, min_disponibles=MIN_DISPONIBLES):
    """De los bytes del .xlsx a las filas de disp_lectura, UNA por codigo, con TODAS las marcas y disponibles o no.
    Devuelve (filas, cuentas). LecturaInvalida si la fila 1, la cabecera, la llave, un numero o una fecha de promo no
    se entienden, o si no llega a los minimos (se dicen los recuentos, no los valores).
    🔴 Regla 10: ningun aviso (warnings) sale de aqui; los de openpyxl se tragan."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return _convertir(contenido, hoy, min_filas, min_disponibles)


def _convertir(contenido, hoy, min_filas, min_disponibles):
    hoy = solo_dia(hoy)  # (Cowork, 9-oct) si entra un datetime, solo su dia
    fila1, cabecera, crudas, donde = leer_excel(contenido)
    fecha_catalogo = fecha_del_titulo(fila1, hoy, donde)
    idioma = comprobar_cabecera(cabecera, donde)
    n_col = len(COLUMNAS_IT)

    salida = []
    vistos, repetidos = set(), set()
    malos = {'llave': 0, 'disponibles': 0, 'precio': 0, 'promo': 0, 'fin_promo': 0}
    c = {'n_crudo': len(crudas), 'n_leidas': 0, 'n_disponibles': 0, 'n_agotados': 0,
         'n_sin_dato_disponibilidad': 0, 'n_sin_dato_precio': 0, 'n_preventa': 0, 'n_preventa_con_stock': 0,
         'n_telefonare_disponibles': 0, 'n_new_disponibles': 0, 'n_en_oferta': 0, 'n_promo_caducada': 0,
         'n_promo_sin_fin': 0, 'n_promo_mas_cara': 0,
         'n_chase_suelto': 0, 'n_chase_suelto_disponibles': 0, 'n_ean_forma_rara': 0, 'n_ean_11_upc': 0,
         'n_fecha_salida_rara': 0}
    por_marca = {k: {'filas': 0, 'disponibles': 0} for k in ['total'] + [k for k, _m in MARCAS_MEDIDAS]}
    for f in crudas:
        f = list(f) + [None] * (n_col - len(f))

        def v(col):
            return f[IX[col]]

        codigo = codigo_de_formula(v('Codice/Link'))
        if codigo is None:
            malos['llave'] += 1
            continue
        if codigo in vistos:
            repetidos.add(codigo)
            continue
        vistos.add(codigo)

        core, regla = ean_de_cruce(v('EAN'))
        if core is not None and len(re.sub(r'\s+', '', str(v('EAN')))) == 11:
            c['n_ean_11_upc'] += 1
        marca, nombre = _texto(v('Publisher')), _texto(v('Descrizione'))
        chase = es_chase_suelto(marca, nombre)
        if chase:
            regla = 'chase_suelto'

        try:
            uds = numero(v('Disponibili'))
            if uds is not None and uds != uds.to_integral_value():
                raise ValueError('no es entero')
        except ValueError:
            malos['disponibles'] += 1
            uds = None
        try:
            prezzo = numero(v('Prezzo (€)'))
        except ValueError:
            malos['precio'] += 1
            prezzo = None
        try:
            promo = numero(v('Prezzo promo (€)'))
        except ValueError:
            malos['promo'] += 1
            promo = None
        try:
            fin = solo_dia(v('Scadenza promo'))
        except ValueError:
            fin = None
            if promo is not None and promo > 0:
                malos['fin_promo'] += 1  # con promo, sin su fin no se sabe el precio vigente
        try:
            salida_dia = solo_dia(v('Data uscita'))
        except ValueError:
            salida_dia = None
            c['n_fecha_salida_rara'] += 1

        p_unidad, en_oferta = precio_vigente(prezzo, promo, fin, hoy)
        # DB5: promo vigente que no baja de Prezzo → como un producto sin promo (fin_oferta vacio) y se cuenta.
        promo_mas_cara = (promo is not None and promo > 0 and fin is not None and fin >= hoy and not en_oferta)
        fin_oferta = None if promo_mas_cara else fin
        nota = _texto(v('Note'))
        nota_up = (nota or '').upper()
        preventa = nota_up == NOTA_PREVENTA
        sin_dato_disp = uds is None
        disponible = uds is not None and uds > 0

        salida.append({
            'producto_prov': codigo,
            'ean_original': _texto(v('EAN')), 'ean_core': core,
            'marca': marca, 'nombre': nombre, 'categoria': _texto(v('Cat 3')),
            'es_caja': False, 'uds_caja': None, 'es_chase': chase,
            'precio_catalogo': None if prezzo is None else float(prezzo),
            'precio_unidad': None if p_unidad is None else float(p_unidad),
            'precio_escalon': None, 'uds_escalon': None, 'precio_pa': None,
            'disponible': disponible, 'disponibilidad': nota,
            'en_oferta': en_oferta, 'preorder': preventa, 'fin_de_vida': None,
            'fin_oferta': fin_oferta.isoformat() if fin_oferta else None,
            'fecha_salida': salida_dia.isoformat() if salida_dia else None,
            'regla': regla, 'aviso': None,
            'sin_dato_disponibilidad': sin_dato_disp, 'sin_dato_precio': prezzo is None,
            '_precio_unidad': p_unidad, '_precio_catalogo': prezzo,
        })
        c['n_leidas'] += 1
        c['n_disponibles' if disponible else 'n_agotados'] += 1
        c['n_sin_dato_disponibilidad'] += sin_dato_disp
        c['n_sin_dato_precio'] += prezzo is None
        c['n_preventa'] += preventa
        c['n_preventa_con_stock'] += preventa and disponible
        c['n_telefonare_disponibles'] += nota_up == 'TELEFONARE' and disponible
        c['n_new_disponibles'] += nota_up == 'NEW' and disponible
        c['n_en_oferta'] += en_oferta
        c['n_promo_caducada'] += (promo is not None and promo > 0 and fin is not None and fin < hoy)
        c['n_promo_sin_fin'] += (promo is not None and promo > 0 and fin is None)  # se calcula con Prezzo
        c['n_promo_mas_cara'] += promo_mas_cara
        c['n_chase_suelto'] += chase
        c['n_chase_suelto_disponibles'] += chase and disponible
        c['n_ean_forma_rara'] += core is None  # (Cowork, 9-oct) por el EAN: un chase suelto con EAN raro tambien cuenta
        marca_up = (marca or '').upper()
        for clave, patron in [('total', '')] + list(MARCAS_MEDIDAS):
            if patron in marca_up:
                por_marca[clave]['filas'] += 1
                por_marca[clave]['disponibles'] += disponible

    problemas = []
    if malos['llave']:
        problemas.append(f"{malos['llave']} fila(s) sin código en «Codice/Link» o que no casa con el enlace (la llave)")
    if repetidos:
        problemas.append(f'{len(repetidos)} código(s) repetido(s) (la llave)')
    textos = {'disponibles': 'con «Disponibili» que no es un entero',
              'precio': 'con «Prezzo» que no es un número',
              'promo': 'con «Prezzo promo» que no es un número',
              'fin_promo': 'con promo y sin «Scadenza promo» que se entienda'}
    for que, texto in textos.items():
        if malos[que]:
            problemas.append(f'{malos[que]} fila(s) {texto}')
    if problemas:
        raise LecturaInvalida(' · '.join(problemas))
    if c['n_crudo'] != c['n_leidas']:
        raise LecturaInvalida(f"no cuadra: crudo {c['n_crudo']} ≠ leídas {c['n_leidas']}")
    if c['n_leidas'] < min_filas:
        raise LecturaInvalida(f"cuadre: {c['n_leidas']} filas, y el mínimo es {min_filas}")
    if c['n_disponibles'] < min_disponibles:
        raise LecturaInvalida(f"cuadre: {c['n_disponibles']} disponibles, y el mínimo es {min_disponibles}")

    c['huella_contenido'] = huella_contenido(salida)
    c['md5_fichero'], c['bytes_fichero'] = huella_fichero(contenido)
    c['idioma_cabecera'] = idioma
    c['fecha_catalogo'] = fecha_catalogo.isoformat()
    c['por_marca'] = por_marca
    for fila in salida:
        del fila['_precio_unidad'], fila['_precio_catalogo']
    return salida, c


# ── Lo que ha cambiado en una pasada, por marca (semana de medicion) ─────────────────────
def recuentos_cambios(cambios):
    """De las filas de disp_cambio de UNA pasada ({'tipo', 'marca'}), cuantas entran, vuelven, salen, pasan a
    disponible, pasan a agotado y cambian de precio, para el total, Funko y Pyramid (la marca, como en por_marca:
    contiene FUNKO / PYRAMID, en mayusculas). Los tipos que no se miden (agotado_sin_dato, recupera_dato) no cuentan.
    Solo recuentos: ni codigos ni marcas salen de aqui."""
    nombre = dict(CAMBIOS_MEDIDOS)
    r = {k: {n: 0 for _t, n in CAMBIOS_MEDIDOS} for k in ['total'] + [k for k, _m in MARCAS_MEDIDAS]}
    for c in cambios:
        n = nombre.get(c.get('tipo'))
        if n is None:
            continue
        marca_up = (c.get('marca') or '').upper()
        for clave, patron in [('total', '')] + list(MARCAS_MEDIDAS):
            if patron in marca_up:
                r[clave][n] += 1
    return r
