# -*- coding: utf-8 -*-
"""ESCANER 2 · LA FOTO DE DISPONIBILIDAD DE BEMS: las reglas de lectura del CSV que exporta la web de BEMS (encargo
BE2, 10-oct-2026). MODULO PURO: bytes del CSV y su nombre dentro, filas y recuentos fuera. Ni red, ni base, ni reloj.

Las reglas salen del parte BE1 del 10-oct-2026 (seccion 4.1, «Pieza a», con su dato: el CSV del 10-oct, 28.091 filas,
15.495 con stock) y de lo que decidio Fernando ese dia. Donde se parece a DBLine (escaner2_dbline.py), se dice.

QUE ES EL FICHERO (parte BE1, 1): `BEMS_EXPORT_DD_MM_AAAA.csv`, que Fernando baja a mano de la web de BEMS
(Disponibilidad = Todos, Catalogo = Todos, todas las casillas) y sube al almacen. UTF-8, separador «;», SIN comillas,
punto decimal, una cabecera de 39 columnas (la ultima, «LENGTH », con un espacio al final) y una fila por articulo.

🔑 LAS REGLAS:
  1. LA LLAVE es la «REF BEMS» (la referencia propia de BEMS, como el codigo de DBLine). Una fila IDENTICA repetida
     (la misma linea dos veces: hoy 2) se queda UNA y se cuenta (n_duplicados). Una REF repetida con contenido
     distinto, o una REF vacia → LecturaInvalida: la pasada falla (no se sabe cual de las dos vale).
  2. EAN: 13 cifras con su digito de control bien → ean_core TAL CUAL (con el 0 delante de los UPC de Funko);
     ean_norm lo calcula la base (columna generada, moloka_ean_norm(ean_core)). Vacio (hoy 57) o de otra forma →
     regla 'ean_forma_rara', ean_core None: se cuenta y NO se tira.
  3. DISPONIBLE = STOCK > 0 (Fernando: «Solo quiero ver lo que esta disponible con stock ya»). La foto guarda el
     catalogo ENTERO: lo demas, no disponible. `disponibilidad` = el STOCK como texto, «100+» cuando es 100 (BEMS no
     da mas de 100: es «100 o mas»). STOCK vacio → sin dato de disponibilidad; que no sea un entero ≥ 0 → falla.
  4. PRECIO = PA (sin IVA), sin tramos ni MULTI, porte 0 (Fernando: «habra que calcular con el precio que salga»;
     «Pedido minimo 400 euros sin gasto de envio»): precio_catalogo = precio_unidad = PA. precio_pa, precio_escalon y
     uds_escalon van VACIOS: la base exige que vayan los tres o ninguno (disp_lectura_escalon_entero), y BEMS no
     tiene escalones. PA vacio o 0 → sin dato de precio; que no sea un numero ≥ 0 → falla.
  5. SIN CAJAS: es_caja false siempre. Expositores y blind boxes son UN articulo a su precio de caja, sin dividir
     (Fernando, 10-oct). El «EAN ASSOC» NO se cruza: va al aviso (parte BE1, 1.5).
  6. SIN CHASE SUELTO: es_chase false siempre. Fernando (10-oct), del Hello Kitty «with Mimmy Chase»: «Es la normal,
     si compras 6 pues te vendra 5 normales y un chase»; Cowork midio los 119 Funko del CSV con «chase» en el titulo
     y todos son la figura normal con posibilidad de chase. Si algun dia sale un titulo que SI parezca un chase suelto
     (Funko, «chase» al final o entre parentesis, y sin «w/», «with» ni «avec» antes en el titulo), entra como figura y se
     dice en su aviso («parece chase suelto») y en el recuento (n_parece_chase): al aviso, no fuera.
  7. marca = FABRICANT, nombre = TITRE UK, categoria = CATEGORIE. El STATUS («Disponible en», «Fuera de stock»…) va al
     aviso: no decide nada (parte BE1, 1.1: stock y estado no se contradicen en ninguna fila).
  8. CUADRE: el nombre es `BEMS_EXPORT_DD_MM_AAAA.csv` con una fecha que existe (va a disp_pasada.fichero_fecha_max);
     la cabecera trae, una vez cada una, las columnas que se usan (los nombres se leen sin los espacios de los lados:
     «LENGTH »); todas las filas tienen tantos campos como la cabecera. Si no, LecturaInvalida.
  9. HUELLA «AL DIA» POR CONTENIDO: md5 de (REF, EAN, STOCK, PA, STATUS) de cada articulo, ordenado por REF. El mismo
     catalogo subido dos veces se cierra «al dia» sin tocar nada. Ademas, el md5 y los bytes del fichero.

🔴 REPO PUBLICO: nada de este modulo imprime. Sus errores (`LecturaInvalida`) dicen RECUENTOS, numeros de fila y
   nombres de columna, nunca un valor del fichero (ni una REF, ni un EAN, ni un precio, ni un titulo).
"""
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation

PROVEEDOR = 'BEMS'
SEPARADOR = ';'
# 🔑 Las columnas que se usan, por su nombre (sin espacios a los lados). Las demas (TITRE FR, PVP, IMG1…) no se leen.
COLUMNAS = ('EAN', 'TITRE UK', 'REF BEMS', 'PA', 'STOCK', 'FABRICANT', 'CATEGORIE', 'STATUS', 'EAN ASSOC')
STOCK_TECHO = 100  # BEMS no da mas de 100: 100 es «100 o mas»
MARCA_CHASE = 'FUNKO'
# Recuentos por marca para el registro (filas y disponibles): la marca CONTIENE el patron, en mayusculas.
MARCAS_MEDIDAS = (('funko', 'FUNKO'), ('bandai_model_kit', 'BANDAI MODEL KIT'), ('pyramid', 'PYRAMID'))
MAX_FILAS_CITADAS = 5  # numeros de fila que se citan en un error (nunca su contenido)
_RE_NOMBRE = re.compile(r'BEMS_EXPORT_([0-9]{2})_([0-9]{2})_([0-9]{4})[.]csv')
_RE_CHASE_NOMBRE = re.compile(r'\bchase\b\s*$|\([^)]*\bchase\b[^)]*\)', re.I)
_RE_CON_CHASE = re.compile(r'(?:\bw/|\bwith\b|\bavec\b).*\bchase\b', re.I)
_RE_ENTERO = re.compile(r'[0-9]+')
_RE_DECIMAL = re.compile(r'[0-9]+(?:[.][0-9]+)?')


class LecturaInvalida(ValueError):
    """El fichero no se puede subir tal cual. El texto son recuentos, numeros de fila y nombres de columna: se puede
    imprimir."""


# ── El fichero ────────────────────────────────────────────────────────────────────────────
def huella_fichero(contenido):
    """(md5, bytes) del fichero tal cual se lee."""
    return hashlib.md5(contenido).hexdigest(), len(contenido)


def fecha_del_nombre(nombre):
    """La fecha de `BEMS_EXPORT_DD_MM_AAAA.csv` (regla 8). LecturaInvalida si el nombre no es ese o la fecha no
    existe."""
    m = _RE_NOMBRE.fullmatch(str(nombre or ''))
    if not m:
        raise LecturaInvalida('el nombre del fichero no es BEMS_EXPORT_DD_MM_AAAA.csv')
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        raise LecturaInvalida('el nombre del fichero trae una fecha que no existe') from None


def leer_csv(contenido):
    """(cabecera, filas) del CSV: la cabecera con los nombres sin espacios a los lados, y cada fila de datos como
    (numero de linea, campos). Las lineas del todo vacias, fuera. 🔴 Sin comillas: un «;» de mas o de menos descuadra
    la fila y se dice (regla 8)."""
    try:
        texto = contenido.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise LecturaInvalida('el fichero no es UTF-8') from None
    lineas = texto.split('\n')
    numeradas = [(i + 1, l[:-1] if l.endswith('\r') else l) for i, l in enumerate(lineas)]
    numeradas = [(n, l) for n, l in numeradas if l.strip()]
    if not numeradas:
        raise LecturaInvalida('el fichero está vacío')
    cabecera = [c.strip() for c in numeradas[0][1].split(SEPARADOR)]
    filas = [(n, l.split(SEPARADOR)) for n, l in numeradas[1:]]
    return cabecera, filas


def indices(cabecera):
    """{columna: posicion} de las COLUMNAS (regla 8): cada una una vez. Si falta alguna o se repite, LecturaInvalida
    con sus nombres (los esperados, nunca un valor)."""
    faltan = [c for c in COLUMNAS if cabecera.count(c) == 0]
    dobles = [c for c in COLUMNAS if cabecera.count(c) > 1]
    if faltan or dobles:
        partes = []
        if faltan:
            partes.append('faltan ' + ', '.join(f'«{c}»' for c in faltan))
        if dobles:
            partes.append('repetidas ' + ', '.join(f'«{c}»' for c in dobles))
        raise LecturaInvalida(f'cabecera ({len(cabecera)} columnas): ' + ' y '.join(partes))
    return {c: cabecera.index(c) for c in COLUMNAS}


# ── Las piezas de una fila (puras) ────────────────────────────────────────────────────────
def _chk13(cuerpo12):
    d = [int(x) for x in cuerpo12][::-1]
    return str((10 - sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(d)) % 10) % 10)


def ean_de_cruce(crudo):
    """(ean_core, regla) del EAN (regla 2): 13 cifras con su control bien → tal cual; lo demas (vacio incluido) →
    (None, 'ean_forma_rara')."""
    s = str(crudo or '').strip()
    if len(s) == 13 and s.isdigit() and s.isascii() and _chk13(s[:12]) == s[12]:
        return s, None
    return None, 'ean_forma_rara'


def stock(crudo):
    """El STOCK como entero ≥ 0; None si esta vacio; ValueError si no es un entero ≥ 0."""
    s = str(crudo or '').strip()
    if not s:
        return None
    if not _RE_ENTERO.fullmatch(s):
        raise ValueError('no es un entero ≥ 0')
    return int(s)


def texto_stock(uds):
    """`disponibilidad` (regla 3): el STOCK como texto, «100+» en el techo."""
    if uds is None:
        return None
    return f'{STOCK_TECHO}+' if uds >= STOCK_TECHO else str(uds)


def precio(crudo):
    """El PA como Decimal; None si esta vacio o es 0 (sin dato, regla 4); ValueError si no es un numero ≥ 0."""
    s = str(crudo or '').strip()
    if not s:
        return None
    if not _RE_DECIMAL.fullmatch(s):
        raise ValueError('no es un número ≥ 0')
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError('no es un número') from None
    return None if d == 0 else d


def parece_chase_suelto(marca, nombre):
    """Regla 6: FUNKO y «chase» al final o entre parentesis, sin «w/», «with» ni «avec» ANTES en el titulo
    («w/Chase», «with Chase», «with Mimmy Chase» y «avec Chase» son la figura normal: el CSV del 10-oct trae un
    «… avec Chase» en TITRE UK). Solo informa: la fila entra igual como figura."""
    if MARCA_CHASE not in str(marca or '').upper():
        return False
    nombre = str(nombre or '')
    return bool(_RE_CHASE_NOMBRE.search(nombre)) and not _RE_CON_CHASE.search(nombre)


def aviso(status, ean_assoc, chase):
    """El aviso de la fila (reglas 5, 6 y 7): el STATUS, el EAN ASSOC si lo hay y «parece chase suelto» si toca."""
    partes = []
    if status:
        partes.append(f'STATUS: {status}')
    if ean_assoc:
        partes.append(f'EAN ASSOC: {ean_assoc}')
    if chase:
        partes.append('parece chase suelto (entra como figura)')
    return ' · '.join(partes) or None


def _texto(v):
    v = '' if v is None else str(v).strip()
    return v or None


def huella_contenido(articulos):
    """md5 de (REF, EAN, STOCK, PA, STATUS) de cada articulo, ordenado por REF (regla 9). Los campos, tal cual vienen
    en el fichero (sin espacios a los lados)."""
    lineas = ['|'.join(a) for a in sorted(articulos, key=lambda x: x[0])]
    return hashlib.md5('\n'.join(lineas).encode('utf-8')).hexdigest()


def _citar(numeros):
    """Los primeros numeros de fila, para un error (nunca su contenido)."""
    mas = len(numeros) - MAX_FILAS_CITADAS
    return ', '.join(str(n) for n in numeros[:MAX_FILAS_CITADAS]) + (f' y {mas} más' if mas > 0 else '')


# ── El fichero entero → filas de disp_lectura ─────────────────────────────────────────────
def convertir(contenido, nombre_fichero):
    """De los bytes del CSV (y su nombre) a las filas de disp_lectura, UNA por REF, con TODAS las marcas y con stock o
    no. Devuelve (filas, cuentas). LecturaInvalida si el nombre, la cabecera, una fila descuadrada, la llave, un STOCK
    o un PA no se entienden (se dicen recuentos y numeros de fila, no los valores). Los minimos de filas y de
    disponibles NO se miran aqui: los pone la base (disp_parametros) y los mira el programa de la pasada."""
    fecha = fecha_del_nombre(nombre_fichero)
    cabecera, crudas = leer_csv(contenido)
    ix = indices(cabecera)
    n_col = len(cabecera)

    descuadradas = [n for n, f in crudas if len(f) != n_col]
    if descuadradas:
        raise LecturaInvalida(f'{len(descuadradas)} fila(s) sin {n_col} campos (un «;» de más o de menos), '
                              f'líneas {_citar(descuadradas)}')

    salida, articulos = [], []
    vistas = {}  # REF → la fila entera tal cual (para distinguir la copia identica de la REF repetida distinta)
    malos = {'llave': [], 'distinta': [], 'stock': [], 'precio': []}
    c = {'n_crudo': len(crudas), 'n_duplicados': 0, 'n_leidas': 0, 'n_disponibles': 0, 'n_agotados': 0,
         'n_sin_dato_disponibilidad': 0, 'n_sin_dato_precio': 0, 'n_stock_techo': 0, 'n_ean_vacio': 0,
         'n_ean_forma_rara': 0, 'n_ean_forma_rara_disponibles': 0, 'n_ean_assoc': 0, 'n_parece_chase': 0,
         'n_sin_marca_disponibles': 0}
    por_marca = {k: {'filas': 0, 'disponibles': 0} for k in ['total'] + [k for k, _m in MARCAS_MEDIDAS]}
    for n, f in crudas:
        def v(col):
            return f[ix[col]].strip()

        ref = v('REF BEMS')
        if not ref:
            malos['llave'].append(n)
            continue
        entera = tuple(x.strip() for x in f)
        if ref in vistas:
            if vistas[ref] == entera:
                c['n_duplicados'] += 1  # la misma linea otra vez: se queda la primera
            else:
                malos['distinta'].append(n)
            continue
        vistas[ref] = entera

        try:
            uds = stock(v('STOCK'))
        except ValueError:
            malos['stock'].append(n)
            uds = None
        try:
            pa = precio(v('PA'))
        except ValueError:
            malos['precio'].append(n)
            pa = None

        core, regla = ean_de_cruce(v('EAN'))
        marca, nombre = _texto(v('FABRICANT')), _texto(v('TITRE UK'))
        assoc = _texto(v('EAN ASSOC'))
        chase = parece_chase_suelto(marca, nombre)
        sin_dato_disp = uds is None
        disponible = uds is not None and uds > 0

        salida.append({
            'producto_prov': ref,
            'ean_original': _texto(v('EAN')), 'ean_core': core,
            'marca': marca, 'nombre': nombre, 'categoria': _texto(v('CATEGORIE')),
            'es_caja': False, 'uds_caja': None, 'es_chase': False,
            'precio_catalogo': None if pa is None else float(pa),
            'precio_unidad': None if pa is None else float(pa),
            'precio_escalon': None, 'uds_escalon': None, 'precio_pa': None,
            'disponible': disponible, 'disponibilidad': texto_stock(uds),
            'en_oferta': False, 'fin_oferta': None, 'preorder': False, 'fin_de_vida': None,
            'regla': regla, 'aviso': aviso(_texto(v('STATUS')), assoc, chase),
            'sin_dato_disponibilidad': sin_dato_disp, 'sin_dato_precio': pa is None,
        })
        articulos.append((ref, v('EAN'), v('STOCK'), v('PA'), v('STATUS')))
        c['n_leidas'] += 1
        c['n_disponibles' if disponible else 'n_agotados'] += 1
        c['n_sin_dato_disponibilidad'] += sin_dato_disp
        c['n_sin_dato_precio'] += pa is None
        c['n_stock_techo'] += uds is not None and uds >= STOCK_TECHO
        c['n_ean_vacio'] += not v('EAN')
        c['n_ean_forma_rara'] += core is None
        c['n_ean_forma_rara_disponibles'] += core is None and disponible
        c['n_ean_assoc'] += assoc is not None
        c['n_parece_chase'] += chase
        c['n_sin_marca_disponibles'] += marca is None and disponible
        marca_up = (marca or '').upper()
        for clave, patron in [('total', '')] + list(MARCAS_MEDIDAS):
            if patron in marca_up:
                por_marca[clave]['filas'] += 1
                por_marca[clave]['disponibles'] += disponible

    problemas = []
    textos = {'llave': 'con la «REF BEMS» vacía (la llave)',
              'distinta': 'con una «REF BEMS» repetida y contenido distinto (la llave)',
              'stock': 'con «STOCK» que no es un entero ≥ 0',
              'precio': 'con «PA» que no es un número ≥ 0'}
    for que, texto in textos.items():
        if malos[que]:
            problemas.append(f'{len(malos[que])} fila(s) {texto}, líneas {_citar(malos[que])}')
    if problemas:
        raise LecturaInvalida(' · '.join(problemas))
    if c['n_crudo'] != c['n_leidas'] + c['n_duplicados']:
        raise LecturaInvalida(f"no cuadra: crudo {c['n_crudo']} ≠ leídas {c['n_leidas']} + repetidas "
                              f"{c['n_duplicados']}")
    if c['n_leidas'] != c['n_disponibles'] + c['n_agotados']:
        raise LecturaInvalida(f"no cuadra: leídas {c['n_leidas']} ≠ disponibles {c['n_disponibles']} + agotados "
                              f"{c['n_agotados']}")

    c['huella_contenido'] = huella_contenido(articulos)
    c['md5_fichero'], c['bytes_fichero'] = huella_fichero(contenido)
    c['fecha_fichero'] = fecha.isoformat()
    c['columnas'] = n_col
    c['por_marca'] = por_marca
    return salida, c
