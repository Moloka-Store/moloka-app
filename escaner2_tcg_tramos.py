# -*- coding: utf-8 -*-
"""ESCANER 2 · LOS TRAMOS DE TCG: las reglas del lector de fichas y del listado filtrado (encargo T2, 13-oct-2026,
pieza (b) del plano del parte T1, 8.2). MODULO PURO: HTML dentro, datos fuera. Ni red, ni base, ni reloj.

La red la pone escaner2_tcg_web.py (sesion de TCG_USER/TCG_PASS, ritmo humano, paradas); la base y el orden,
escaner2_tcg_disponibilidad.py.

QUE SE LEE DE LA FICHA (parte T1, 2b y 2c, medido en 60 fichas el 12-oct y releidas el 13-oct):
  · el PRECIO ACTUAL a 1 ud: el `content` del <span itemprop="price"> dentro de «current-price» (2 decimales; en una
    Oferta o un Saldo, ya rebajado: Ravensburger 30,06; Banpresto 14,43);
  · la TABLA DE TRAMOS (`table-product-discounts`): fila 1 «A partir de N uds.» por columna; en las siguientes
    (`data-discount-type="percentage"`), por celda, `rel` (el precio SIN rebajas, 6 decimales: Vegeta 8.550579) y `dis`
    (el descuento exacto del tramo: 0.023400). Precio exacto del tramo = rel × (1 − dis);
  · el EAN de la ficha (<label>EAN:</label><span>…</span>), para no guardar el tramo de otro producto;
  · que la pagina es la de alguien CON SESION (clase `usuariologeado` del <body>): sin ella, los precios no son los
    nuestros; y que es la de un PRODUCTO (`<body id="product">`): si la direccion ya no existe, la web manda a la
    categoria (sonda T2, 13-oct) y eso es «sin ficha», no HTML roto.
EL SUELTO EXACTO: `rel` si redondeado a 2 decimales es el precio actual (sin oferta); si no (Oferta, Saldo, o sin tabla),
el precio actual. EL MAS BARATO EXACTO: el minimo entre el suelto exacto (1 ud) y cada tramo (a igual precio, el de
menos unidades). EL COCIENTE = mas barato exacto ÷ «Precio» del Excel EN ESE MOMENTO (parte T1, 2c): Ultra Pro
0,5262816 / 0,66; Vegeta 8,3504954 / 8,55; Ravensburger en Oferta 28,1807858 / 30,06 (y no 1 − 25 %: el tramo va
sobre el precio de antes de la oferta). En cada pasada de la foto, precio de compra = Precio del Excel × cociente.

🔴 LO QUE NO SE ENTIENDE NO SE INVENTA: sin sesion, sin precio actual, una tabla de tramos con otra forma (otro tipo
   de descuento, columnas que no casan, un numero que no lo es) → FichaNoEntendida, y el programa PARA de leer la web
   (encargo T2: «Al primer bloqueo, captcha, 403/429 o HTML que no se entienda: para»). Un EAN de la ficha que no es
   el del Excel no es HTML roto: ese producto se apunta 'otro_ean' y no se le pone cociente.

EL LISTADO FILTRADO (parte T1, 2a y 2d: 16 paginas de 111 tarjetas, el filtro de estado de la propia web): por
tarjeta, la URL de su ficha, el «desde X» (solo si tiene tramo: el mas barato, REDONDEADO) y el suelto. Sirve para
saber, sin abrir fichas, que un tramo guardado ya no cuadra (el tapete ABYstyle del 13-oct: «desde» de 13,09 a 13,36).
Se compara redondeado con redondeado (0,5262816 da «desde 0,53»: no salta en falso).

🔴 REPO PUBLICO: nada de este modulo imprime.
"""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser

DIAS_RELEER = 7
HORAS_REINTENTO = 24
ESTADOS_BUENOS = ('Disponible', 'Oferta', 'Saldo')
CENT = Decimal('0.01')
_DOCE = Decimal('1e-12')
_RE_A_PARTIR = re.compile(r'A partir de\s+(\d+)\s+uds?\.?', re.I)
_RE_EUROS = re.compile(r'(\d{1,3}(?:\.\d{3})+|\d+),(\d{1,2})')
_RE_DECIMAL = re.compile(r'\d+(?:\.\d+)?')
_RE_CAMPO_FILTRO = re.compile(r'f\[\d+\]\[\]')
VACIOS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class FichaNoEntendida(ValueError):
    """La ficha no tiene la forma medida: se para de leer. El texto lo escribe este modulo (sin valores de la pagina)."""


class FichaNoEsProducto(ValueError):
    """La URL de la ficha lleva a otra pagina de la web (una categoria: el producto ya no esta en esa direccion). No es
    HTML roto: ese producto se apunta 'sin_ficha', como un 404 (sonda T2, 13-oct: 1 de 586)."""


class ListadoNoEntendido(ValueError):
    """El listado no tiene la forma medida: se para de leer. El texto lo escribe este modulo."""


# ── Un arbol HTML minimo y tolerante (sin dependencias) ───────────────────────────────────
class Nodo:
    __slots__ = ('tag', 'attrs', 'hijos', 'padre')

    def __init__(self, tag, attrs, padre):
        self.tag, self.attrs, self.hijos, self.padre = tag, attrs, [], padre

    def clases(self):
        return set((self.attrs.get('class') or '').split())

    def nodos(self):
        """Los descendientes (elementos), en orden de documento (sin recursion: una pagina mal cerrada anida mucho)."""
        pila = [h for h in reversed(self.hijos) if isinstance(h, Nodo)]
        while pila:
            n = pila.pop()
            yield n
            pila.extend(h for h in reversed(n.hijos) if isinstance(h, Nodo))

    def buscar(self, tag=None, clase=None, **attrs):
        for n in self.nodos():
            if tag is not None and n.tag != tag:
                continue
            if clase is not None and clase not in n.clases():
                continue
            if any(n.attrs.get(k) != v for k, v in attrs.items()):
                continue
            yield n

    def primero(self, tag=None, clase=None, **attrs):
        return next(self.buscar(tag, clase, **attrs), None)

    def hijos_tag(self, tag):
        return [h for h in self.hijos if isinstance(h, Nodo) and h.tag == tag]

    def texto(self):
        """El texto de dentro, en orden y con los espacios juntados (sin recursion)."""
        partes, pila = [], [iter(self.hijos)]
        while pila:
            h = next(pila[-1], None)
            if h is None:
                pila.pop()
            elif isinstance(h, str):
                partes.append(h)
            else:
                pila.append(iter(h.hijos))
        return ' '.join(' '.join(partes).split())


class _Arbol(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo('#doc', {}, None)
        self.actual = self.raiz

    def handle_starttag(self, tag, attrs):
        n = Nodo(tag, {k: (v or '') for k, v in attrs}, self.actual)
        self.actual.hijos.append(n)
        if tag not in VACIOS:
            self.actual = n

    def handle_startendtag(self, tag, attrs):
        self.actual.hijos.append(Nodo(tag, {k: (v or '') for k, v in attrs}, self.actual))

    def handle_endtag(self, tag):
        n = self.actual
        while n is not self.raiz and n.tag != tag:
            n = n.padre
        if n is not self.raiz:
            self.actual = n.padre

    def handle_data(self, data):
        self.actual.hijos.append(data)


def arbol(html):
    p = _Arbol()
    p.feed(html or '')
    p.close()
    return p.raiz


# ── Numeros ───────────────────────────────────────────────────────────────────────────────
def decimal(texto):
    """Decimal de «8.550579» (atributos de la web, con punto). None si no tiene esa forma."""
    s = str(texto or '').strip()
    if not _RE_DECIMAL.fullmatch(s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def euros(texto):
    """Decimal de «8,35€», «desde 8,35 €» o «1.234,56 €» (lo que se ve, con coma). None si no hay un importe."""
    m = _RE_EUROS.search(str(texto or ''))
    if not m:
        return None
    return Decimal(m.group(1).replace('.', '') + '.' + m.group(2))


def redondeo(d):
    return None if d is None else d.quantize(CENT, rounding=ROUND_HALF_UP)


def norm_ean(texto):
    """Como moloka_ean_norm: solo cifras y sin ceros delante."""
    return re.sub(r'\D', '', str(texto or '')).lstrip('0')


# ── La ficha ──────────────────────────────────────────────────────────────────────────────
def leer_ficha(html):
    """{'precio_actual', 'eans', 'tramos': [(uds, rel, dis)]} de una ficha. FichaNoEntendida si falta la sesion o el
    precio actual, o si la tabla de tramos no tiene la forma medida."""
    raiz = arbol(html)
    cuerpo = raiz.primero('body')
    if cuerpo is None or 'usuariologeado' not in cuerpo.clases():
        raise FichaNoEntendida('la ficha no es la de una sesión abierta (sin «usuariologeado» en el body)')
    if cuerpo.attrs.get('id') != 'product':
        raise FichaNoEsProducto('la URL de la ficha lleva a otra página (body id «%s»)' % (cuerpo.attrs.get('id') or '')[:20])
    precio = None
    for cp in raiz.buscar(clase='current-price'):
        sp = cp.primero('span', itemprop='price')
        if sp is not None:
            precio = decimal(sp.attrs.get('content'))
            break
    if precio is None or precio <= 0:
        raise FichaNoEntendida('la ficha no trae el precio actual (span itemprop=price dentro de current-price)')

    eans = []
    for bloque in raiz.buscar('div', clase='product-availability-date'):
        etiqueta = bloque.primero('label')
        if etiqueta is not None and etiqueta.texto().strip() == 'EAN:':
            sp = bloque.primero('span')
            if sp is not None and sp.texto().strip():
                eans.append(sp.texto().strip())

    tramos = []
    tabla = raiz.primero('table', clase='table-product-discounts')
    if tabla is not None:
        filas = [n for n in tabla.buscar('tr')]
        if len(filas) < 2:
            raise FichaNoEntendida('tabla de tramos sin fila de unidades o sin fila de precios')
        cabecera = []
        for td in filas[0].buscar('td'):
            m = _RE_A_PARTIR.search(td.texto())
            if not m:
                raise FichaNoEntendida('tabla de tramos: una columna sin «A partir de N uds.»')
            cabecera.append(int(m.group(1)))
        if not cabecera:
            raise FichaNoEntendida('tabla de tramos sin columnas')
        for fila in filas[1:]:
            tipo = fila.attrs.get('data-discount-type')
            celdas = list(fila.buscar('td'))
            if tipo != 'percentage':
                raise FichaNoEntendida('tabla de tramos con un descuento que no es de porcentaje')
            if len(celdas) != len(cabecera):
                raise FichaNoEntendida('tabla de tramos: las celdas no casan con las columnas')
            for uds, td in zip(cabecera, celdas):
                rel, dis = decimal(td.attrs.get('rel')), decimal(td.attrs.get('dis'))
                if rel is None or dis is None or rel <= 0 or not (0 <= dis < 1) or uds < 1:
                    raise FichaNoEntendida('tabla de tramos: una celda sin rel/dis que se entiendan')
                tramos.append((uds, rel, dis))
        if len({r for _u, r, _d in tramos}) > 1:
            raise FichaNoEntendida('tabla de tramos con dos precios base distintos')
    return {'precio_actual': precio, 'eans': eans, 'tramos': tramos}


def ean_casa(eans_ficha, producto_prov, ean_core, es_caja):
    """True si algun EAN de la ficha es el del Excel. Normal: iguales sin ceros delante (como ean_norm). Caja «C»: la
    web la codifica con el GS1 largo (01 + GTIN-14 + …): el GTIN-14 sin su primera cifra ni su control = el EAN-13 del
    Excel sin su control. Sin EAN de cruce (forma rara), las cifras del crudo."""
    propio = ean_core or re.sub(r'\D', '', producto_prov)
    if not propio:
        return False
    for e in eans_ficha:
        cifras = re.sub(r'\D', '', e)
        if cifras and norm_ean(cifras) == norm_ean(propio):
            return True
        if es_caja and len(cifras) >= 16 and cifras.startswith('01'):
            gtin14 = cifras[2:16]
            if gtin14[1:13] == propio.zfill(13)[:12]:
                return True
    return False


def tramo_de_ficha(ficha, precio_excel):
    """Lo que se guarda de una ficha leida (8.2.1): suelto, tramos, el mas barato exacto, sus uds y el cociente sobre
    `precio_excel` (Decimal > 0; si no, None: sin cociente)."""
    actual = ficha['precio_actual']
    tramos = ficha['tramos']
    rel = tramos[0][1] if tramos else None
    suelto = rel if rel is not None and redondeo(rel) == actual else actual
    candidatos = [(suelto, 1)] + [(r * (1 - d), u) for u, r, d in tramos]
    barato, uds = min(candidatos, key=lambda x: (x[0], x[1]))
    cociente = None
    if precio_excel is not None and precio_excel > 0:
        cociente = (barato / precio_excel).quantize(_DOCE, rounding=ROUND_HALF_UP)
    return {'suelto_web': actual, 'suelto_exacto': suelto, 'rel': rel,
            'tramos': [{'uds': u, 'dis': str(d)} for u, _r, d in tramos],
            'mas_barato': barato, 'uds_mas_barato': uds, 'precio_excel': precio_excel, 'cociente': cociente}


# ── El listado filtrado ───────────────────────────────────────────────────────────────────
def formulario_filtro(html):
    """(campos_ocultos [(nombre, valor)], campo_estado, [valores de Disponible/Oferta/Saldo]) del filtro de la web
    (#af_form). ListadoNoEntendido si no esta o no tiene el filtro de estado."""
    raiz = arbol(html)
    form = raiz.primero('form', id='af_form')
    if form is None:
        raise ListadoNoEntendido('la página de la categoría no trae el filtro (#af_form)')
    ocultos = [(i.attrs['name'], i.attrs.get('value', '')) for i in form.buscar('input')
               if i.attrs.get('type') == 'hidden' and i.attrs.get('name')]
    campo, valores = None, []
    for i in form.buscar('input'):
        nombre = i.attrs.get('name') or ''
        if not _RE_CAMPO_FILTRO.fullmatch(nombre):
            continue
        lab = i.padre
        while lab is not None and lab.tag != 'label':
            lab = lab.padre
        nom = lab.primero(clase='name') if lab is not None else None
        if nom is not None and nom.texto().strip() in ESTADOS_BUENOS:
            if campo not in (None, nombre):
                raise ListadoNoEntendido('el filtro de estado mezcla dos campos')
            campo = nombre
            valores.append(i.attrs.get('value', ''))
    if campo is None or not valores:
        raise ListadoNoEntendido('el filtro no tiene «Disponible», «Oferta» ni «Saldo»')
    if not any(k == 'nb_items' for k, _v in ocultos) or not any(k == 'page' for k, _v in ocultos):
        raise ListadoNoEntendido('el filtro no trae nb_items ni page')
    return ocultos, campo, valores


def tarjetas(html):
    """[{url, estado, desde, suelto}] de las tarjetas de un trozo de listado."""
    raiz = arbol(html)
    salida = []
    for art in raiz.buscar('article', clase='product-miniature'):
        h5 = art.primero('h5', clase='product-title')
        a = h5.primero('a') if h5 is not None else None
        url = a.attrs.get('href') if a is not None else None
        clases = (art.attrs.get('class') or '').split()
        desde = None
        for linea in art.buscar(clase='first_line'):
            for sp in linea.buscar('span', clase='price'):
                t = sp.texto()
                if t.lower().startswith('desde'):
                    desde = euros(t)
        suelto = None
        for linea in art.buscar(clase='second_line'):
            sp = linea.primero('span', clase='price')
            if sp is not None:
                suelto = euros(sp.texto())
                break
        salida.append({'url': url, 'estado': clases[-1] if clases else None, 'desde': desde, 'suelto': suelto})
    return salida


def desajustes(cards, guardados_por_url):
    """Las llaves (producto_prov) cuyo tramo guardado ya no cuadra con su tarjeta (8.2.3): el suelto no es el mismo,
    tiene «desde» y lo guardado no tiene tramo (o al reves), o el «desde» no es el mas barato guardado redondeado.
    `guardados_por_url`: {url: {'producto_prov', 'suelto_web', 'mas_barato', 'uds_mas_barato'}} (solo los leidos)."""
    malas = set()
    for t in cards:
        g = guardados_por_url.get(t['url'])
        if g is None:
            continue
        suelto_g = g.get('suelto_web')
        suelto_g = None if suelto_g is None else Decimal(str(suelto_g))
        barato_g = g.get('mas_barato')
        barato_g = None if barato_g is None else Decimal(str(barato_g))
        con_tramo = (g.get('uds_mas_barato') or 1) > 1
        if t['suelto'] is not None and suelto_g is not None and t['suelto'] != redondeo(suelto_g):
            malas.add(g['producto_prov'])
        elif (t['desde'] is not None) != con_tramo:
            malas.add(g['producto_prov'])
        elif t['desde'] is not None and barato_g is not None and t['desde'] != redondeo(barato_g):
            malas.add(g['producto_prov'])
    return malas


# ── Que fichas toca leer ──────────────────────────────────────────────────────────────────
def _cuando(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def pendientes(catalogo, guardados, ahora, n_max):
    """Las entradas de `catalogo` (las de escaner2_tcg.convertir) cuya ficha toca leer, en orden, hasta `n_max`:
    1) disponibles nunca leidas (sin cociente); 2) las que el listado ha marcado (`pide_relectura`); 3) las leidas hace
    mas de DIAS_RELEER dias, la mas vieja primero. Solo disponibles con URL. Un intento fallido (sin ficha, otro EAN,
    no entendida) no se repite hasta pasadas HORAS_REINTENTO horas. `guardados`: {producto_prov: fila de disp_tramo}."""
    nuevas, marcadas, viejas = [], [], []
    for e in catalogo:
        if not e['disponible'] or not e['url']:
            continue
        g = guardados.get(e['producto_prov'])
        if g is not None and g.get('intento_resultado') not in (None, 'ok'):
            intento = _cuando(g.get('intento_en'))
            if intento is not None and ahora - intento < timedelta(hours=HORAS_REINTENTO):
                continue
        leido = None if g is None else _cuando(g.get('leido_en'))
        if leido is None or g.get('cociente') is None:
            nuevas.append(e)
        elif g.get('pide_relectura'):
            marcadas.append((_cuando(g.get('pide_relectura')) or ahora, e))
        elif ahora - leido > timedelta(days=DIAS_RELEER):
            viejas.append((leido, e))
    marcadas.sort(key=lambda x: x[0])
    viejas.sort(key=lambda x: x[0])
    orden = nuevas + [e for _t, e in marcadas] + [e for _t, e in viejas]
    return orden[:max(0, n_max)], len(orden)
