#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · OSMA: CUÁNDO VUELVE LO AGOTADO (Fernando, 04-oct-2026).

Fernando, 04-oct-2026: «que reponer identifique que un producto de OSMA no esta disponible hoy pero lo estará
pronto y lo enseñe». El Excel diario de OSMA no trae la fecha; la ficha web de cada artículo sí: «Bestellt
(Wieder verfügbar ab: 11.10.26)», dentro del bloque schema.org/Offer del producto (medido el 04-oct-2026 en
osma-werm.com, sin sesión: 1538 → 11.10.26, 2346 → 05.10.26; Cowork vio 12.10 y 06.10 esa mañana: la fecha
se mueve). Este módulo lo llama escaner2_osma_disponibilidad.py DESPUÉS de aplicar la foto y SOLO si se
aplicó (o en su modo --solo-fechas), con la MISMA sesión con la que ha entrado.

QUÉ HACE, EN ORDEN:
  1. BORRA la fecha de los artículos de OSMA que vuelven a estar disponibles (disponible = true y
     fecha_vuelta no nula → fecha_vuelta = NULL).
  2. ELIGE los agotados que alimentan alguna ficha nuestra: los de disp_estado de OSMA con disponible = false,
     en el catálogo y sin ausencias, cuyo código cumple UNA de estas:
       · tiene enlace en codigos_proveedor (OSMA, con producto_id): la rama «por código» de v_escaner_fuente;
       · su EAN (normalizado como moloka_ean_norm) es el de alguna ficha de productos: la rama «por EAN»;
       · está en osma_mapa_ficha con es_nuestra (el mapa fijo de Cowork, 04-oct-2026).
     Primero los que nunca se han leído y luego los de lectura más vieja. Uno ya leído HOY (día de Madrid) no
     se vuelve a abrir.
  3. PARA CADA UNO, de uno en uno: busca su ficha en la web alemana (/search?search=<EAN>, que lleva directa
     a /<slug>/<código>; si no, el enlace del resultado que acaba en /<código>; si no, lo mismo buscando por el
     nombre). 🔑 Comprueba que el código del final de la URL es el del artículo, y que el «sku» de la página
     también. Lee el bloque Offer: con «Wieder verfügbar ab: dd.mm.aa» → esa fecha; sin ella → NULL. Apunta
     fecha_vuelta y fecha_vuelta_leida_en.
  🔒 LOS FRENOS: al menos PAUSA_S (2 s) entre peticiones; como mucho TOPE_PETICIONES (40) por pasada (las
     búsquedas cuentan); y al PRIMER 403 o 429, o si la web devuelve la página de entrada, PARA EN SECO sin
     reintentar nada.
  🔒 NO SE ESCRIBE lo que no se ha leído bien: sin ficha, otro artículo, página que no es alemana, sin bloque
     Offer o con dos, o una fecha que no existe → no se toca la fila (se cuenta).

🔴 REPO PÚBLICO: el registro SOLO lleva recuentos. Ni códigos, ni EAN, ni nombres, ni fechas, ni URL.
🔒 SOLO TOCA: disp_estado (las dos columnas fecha_vuelta y fecha_vuelta_leida_en, y nada más) y, para LEER,
   codigos_proveedor, productos y osma_mapa_ficha. Migración 20261004180000_disp_osma_fecha_vuelta.sql de
   moloka-app-v2: tiene que estar APLICADA antes.
"""
import re
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

PROVEEDOR = 'OSMA'
WEB = 'https://osma-werm.com'
PAUSA_S = 2.0
TOPE_PETICIONES = 40
ESPERA_S = 60
PAGINA = 1000
PARAR_EN = (403, 429)
_FECHA_RE = re.compile(r'Wieder\s+verf(?:ü|ue)gbar\s+ab\s*:?\s*(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})(?!\d)', re.I)
_OFFER_RE = re.compile(r'schema\.org/Offer$', re.I)
_VACIOS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source',
           'track', 'wbr'}


class Parar(Exception):
    """La web ha dicho basta (403/429) o ha perdido la sesión: no se pide nada más. `motivo` lo escribe este
    módulo (un estado, nunca la web)."""

    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


class _SinPresupuesto(Exception):
    pass


def norm_ean(v):
    """Lo mismo que public.moloka_ean_norm: solo cifras, sin ceros a la izquierda; vacío → None."""
    s = re.sub(r'[^0-9]', '', str(v or '')).lstrip('0')
    return s or None


def _ultimo_tramo(url):
    return urlparse(url or '').path.rstrip('/').rsplit('/', 1)[-1]


def _misma_web(url):
    return urlparse(url or '').netloc == urlparse(WEB).netloc


def _en_la_entrada(url):
    return urlparse(url or '').path.rstrip('/').endswith('/account/login')


# ── La ficha: un lector mínimo con html.parser ────────────────────────────────────────────
class _Ficha(HTMLParser):
    """Recoge el idioma de la página, el texto de CADA bloque schema.org/Offer, los «sku» y los enlaces."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang, self.ofertas, self.skus, self.enlaces = None, [], [], []
        self._pila = []          # por cada etiqueta abierta: (tag, abre_offer, abre_sku)
        self._offer = 0          # profundidad dentro de un Offer
        self._sku = 0
        self._txt_offer, self._txt_sku = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html' and self.lang is None:
            self.lang = (a.get('lang') or '').strip().lower()
        if tag == 'a' and a.get('href'):
            self.enlaces.append(a['href'])
        if tag in _VACIOS:
            if a.get('itemprop') == 'sku' and a.get('content'):
                self.skus.append(a['content'].strip())
            return
        abre_offer = bool(_OFFER_RE.search((a.get('itemtype') or '').strip()))
        abre_sku = a.get('itemprop') == 'sku'
        if abre_offer:
            if self._offer == 0:
                self._txt_offer = []
            self._offer += 1
        if abre_sku:
            if self._sku == 0:
                self._txt_sku = []
            self._sku += 1
        self._pila.append((tag, abre_offer, abre_sku))

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.enlaces.append(a['href'])
        if a.get('itemprop') == 'sku' and a.get('content'):
            self.skus.append(a['content'].strip())

    def handle_endtag(self, tag):
        for i in range(len(self._pila) - 1, -1, -1):
            if self._pila[i][0] == tag:
                for _t, offer, sku in reversed(self._pila[i:]):
                    if offer:
                        self._offer -= 1
                        if self._offer == 0:
                            self.ofertas.append(' '.join(self._txt_offer))
                    if sku:
                        self._sku -= 1
                        if self._sku == 0:
                            self.skus.append(' '.join(self._txt_sku).strip())
                del self._pila[i:]
                return

    def handle_data(self, data):
        d = data.strip()
        if d:
            if self._offer:
                self._txt_offer.append(d)
            if self._sku:
                self._txt_sku.append(d)


def leer_ficha(html, codigo):
    """('con_fecha', date) · ('sin_fecha', None) · o (motivo, None) si la página no vale: 'no_alemana',
    'otro_articulo', 'sin_bloque' (ningún Offer o más de uno), 'fecha_rara'."""
    f = _Ficha()
    f.feed(html or '')
    f.close()
    if not (f.lang or '').startswith('de'):
        return 'no_alemana', None
    skus = {s for s in f.skus if s}
    if skus and skus != {codigo}:
        return 'otro_articulo', None
    if len(f.ofertas) != 1:
        return 'sin_bloque', None
    m = _FECHA_RE.search(f.ofertas[0])
    if not m:
        return 'sin_fecha', None
    dia, mes, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return 'con_fecha', date(anio if anio >= 100 else 2000 + anio, mes, dia)
    except ValueError:
        return 'fecha_rara', None


def enlaces_al_codigo(html, base_url, codigo):
    """Los enlaces DISTINTOS de una página de resultados cuyo último tramo es el código (misma web)."""
    f = _Ficha()
    f.feed(html or '')
    f.close()
    urls = []
    for h in f.enlaces:
        u = urljoin(base_url, h).split('#')[0]
        if _misma_web(u) and _ultimo_tramo(u) == codigo and u not in urls:
            urls.append(u)
    return urls


# ── La web, con sus frenos ─────────────────────────────────────────────────────────────────
class _Pedidor:
    def __init__(self, sesion, dormir, reloj, tope):
        self.sesion, self.dormir, self.reloj, self.tope = sesion, dormir, reloj, tope
        self.hechas, self._ultima = 0, None

    def get(self, url):
        if self.hechas >= self.tope:
            raise _SinPresupuesto()
        if self._ultima is not None:
            falta = PAUSA_S - (self.reloj() - self._ultima)
            if falta > 0:
                self.dormir(falta)
        self.hechas += 1
        try:
            r = self.sesion.get(url, timeout=ESPERA_S, allow_redirects=True)
        finally:
            self._ultima = self.reloj()
        if r.status_code in PARAR_EN or any(getattr(h, 'status_code', None) in PARAR_EN for h in getattr(r, 'history', []) or []):
            raise Parar(f'la web respondió {r.status_code if r.status_code in PARAR_EN else "403/429 en una redirección"}')
        if _en_la_entrada(r.url):
            raise Parar('la web ha devuelto la página de entrada: la sesión no vale')
        return r


def buscar_ficha(pedidor, fila):
    """La respuesta de la ficha del artículo, o None. Prueba por EAN y luego por nombre."""
    codigo = fila['producto_prov']
    for termino in (fila.get('ean_core'), fila.get('nombre')):
        if not termino:
            continue
        r = pedidor.get(WEB + '/search?search=' + quote(str(termino)))
        if r.status_code == 200 and _misma_web(r.url) and _ultimo_tramo(r.url) == codigo:
            return r
        if r.status_code != 200:
            continue
        urls = enlaces_al_codigo(r.text, r.url, codigo)
        if len(urls) != 1:
            continue
        r2 = pedidor.get(urls[0])
        if r2.status_code == 200 and _misma_web(r2.url) and _ultimo_tramo(r2.url) == codigo:
            return r2
    return None


# ── La base ───────────────────────────────────────────────────────────────────────────────
def _todas(hacer):
    """Todas las filas de una consulta, de PAGINA en PAGINA (PostgREST corta a 1.000)."""
    filas, desde = [], 0
    while True:
        lote = hacer().range(desde, desde + PAGINA - 1).execute().data or []
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        desde += PAGINA


def _fecha_base(v):
    if not v:
        return None
    t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def candidatos(sb, cuentas):
    """Los agotados de OSMA que alimentan alguna ficha nuestra (ver el apartado 2 de la cabecera)."""
    agotados = _todas(lambda: sb.table('disp_estado')
                      .select('producto_prov, ean_core, ean_norm, nombre, fecha_vuelta_leida_en')
                      .eq('proveedor', PROVEEDOR).eq('disponible', False).eq('en_catalogo', True).eq('ausencias', 0)
                      .order('producto_prov'))
    enlaces = {f['codigo_proveedor'] for f in _todas(lambda: sb.table('codigos_proveedor')
                                                     .select('codigo_proveedor, producto_id')
                                                     .eq('proveedor', PROVEEDOR).order('id'))
               if f.get('producto_id') and f.get('codigo_proveedor')}
    eans = {norm_ean(f.get('ean')) for f in _todas(lambda: sb.table('productos').select('ean').order('id'))} - {None}
    try:
        mapa = {f['codigo_osma'] for f in _todas(lambda: sb.table('osma_mapa_ficha').select('codigo_osma')
                                                 .eq('es_nuestra', True).order('codigo_osma'))}
    except Exception:
        # El mapa es una ayuda (los enlaces y el EAN ya cubren lo que lee Reponer): sin él, se sigue y se dice.
        mapa, cuentas['mapa_sin_leer'] = set(), 1
    elegidos = [a for a in agotados
                if a.get('producto_prov') in enlaces
                or (a.get('ean_norm') or norm_ean(a.get('ean_core'))) in eans
                or a.get('producto_prov') in mapa]
    cuentas['agotados_osma'], cuentas['nuestros'] = len(agotados), len(elegidos)
    return elegidos


def borrar_las_que_vuelven(sb):
    """Los disponibles con fecha: la fecha ya no dice nada. Devuelve cuántos."""
    con = _todas(lambda: sb.table('disp_estado').select('producto_prov').eq('proveedor', PROVEEDOR)
                 .eq('disponible', True).not_.is_('fecha_vuelta', 'null').order('producto_prov'))
    for f in con:
        sb.table('disp_estado').update({'fecha_vuelta': None}) \
          .eq('proveedor', PROVEEDOR).eq('producto_prov', f['producto_prov']).execute()
    return len(con)


def repasar(sb, sesion, inicio_hoy, escribir=True, dormir=time.sleep, reloj=time.monotonic, ahora=None):
    """Todo el repaso. `inicio_hoy` = las 00:00 de hoy en Madrid, en UTC (lo leído desde entonces no se relee).
    Devuelve (cuentas, motivo_parada o None). Lanza solo lo inesperado (el que llama lo imprime por su tipo)."""
    cuentas = {k: 0 for k in ('agotados_osma', 'nuestros', 'leidos_hoy', 'abiertas', 'con_fecha', 'sin_fecha',
                              'no_encontrada', 'otro_articulo', 'no_alemana', 'sin_bloque', 'fecha_rara',
                              'sin_turno', 'borradas', 'peticiones', 'mapa_sin_leer')}
    cuentas['borradas'] = borrar_las_que_vuelven(sb) if escribir else 0
    elegidos = candidatos(sb, cuentas)
    pendientes = []
    for f in elegidos:
        leida = _fecha_base(f.get('fecha_vuelta_leida_en'))
        if leida is not None and leida >= inicio_hoy:
            cuentas['leidos_hoy'] += 1
        else:
            pendientes.append((leida is not None, leida or inicio_hoy, f['producto_prov'], f))
    pendientes.sort(key=lambda x: x[:3])
    pedidor = _Pedidor(sesion, dormir, reloj, TOPE_PETICIONES)
    parada = None
    for i, (_l, _t, codigo, f) in enumerate(pendientes):
        try:
            r = buscar_ficha(pedidor, f)
        except _SinPresupuesto:
            cuentas['sin_turno'] = len(pendientes) - i
            break
        except Parar as ex:
            parada = ex.motivo
            cuentas['sin_turno'] = len(pendientes) - i
            break
        if r is None:
            cuentas['no_encontrada'] += 1
            continue
        cuentas['abiertas'] += 1
        estado, fecha = leer_ficha(r.text, codigo)
        cuentas[estado] += 1
        if estado in ('con_fecha', 'sin_fecha') and escribir:
            sb.table('disp_estado').update({
                'fecha_vuelta': fecha.isoformat() if fecha else None,
                'fecha_vuelta_leida_en': (ahora or datetime.now(timezone.utc)).isoformat(),
            }).eq('proveedor', PROVEEDOR).eq('producto_prov', codigo).execute()
    cuentas['peticiones'] = pedidor.hechas
    return cuentas, parada


def resumen(c, escribir):
    """La línea del registro: SOLO recuentos."""
    return (f">>> FECHAS DE VUELTA{'' if escribir else ' (SIN ESCRIBIR)'}: {c['nuestros']} agotados nuestros "
            f"(de {c['agotados_osma']} agotados de OSMA), {c['leidos_hoy']} ya leídos hoy · fichas abiertas "
            f"{c['abiertas']} (con fecha {c['con_fecha']}, sin fecha {c['sin_fecha']}; no valen: otro artículo "
            f"{c['otro_articulo']}, no alemana {c['no_alemana']}, sin bloque {c['sin_bloque']}, fecha rara "
            f"{c['fecha_rara']}) · sin ficha {c['no_encontrada']} · sin turno {c['sin_turno']} · peticiones "
            f"{c['peticiones']} · fechas borradas (vuelven a estar disponibles) {c['borradas']}"
            + (' · el mapa osma_mapa_ficha no se ha podido leer' if c['mapa_sin_leer'] else ''))
