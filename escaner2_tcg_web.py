# -*- coding: utf-8 -*-
"""ESCANER 2 · LA WEB DE TCG: la sesion, el Excel, las fichas y el listado filtrado (encargo T2, 13-oct-2026).

Lo mismo que hace el director viejo (director_tcg_prep.py) para entrar y bajar el Excel —login de PrestaShop por
servidor con TCG_USER/TCG_PASS y el boton de smcatalog— y lo que midio el reconocimiento T1 para las fichas y el
listado filtrado (el POST de solo consulta del filtro de la web, 111 tarjetas por pagina).

🔑 RITMO HUMANO Y ERRATICO (encargo T2): entre peticion y peticion, una pausa al azar de 1,5 a 4 s, y cada 20 a 40
   peticiones (al azar) una mas larga, de 8 a 20 s.
🔴 AL PRIMER BLOQUEO, PARA: un 403, 429 o 503, una pagina de captcha o de «comprobando tu navegador», un fallo de red
   o una respuesta que no es lo que se pidio → `Bloqueo`, y quien llama deja de pedir nada a la web. Nunca se reintenta.
🔴 REPO PUBLICO: este modulo NO imprime. Los textos de `Bloqueo` los escribe el (codigos y que se pedia), nunca una URL
   con datos, la respuesta, el usuario o la clave.
"""
import random
import time
from urllib.parse import urlencode

BASE = 'https://tcgfactory.com'
LOGIN_URLS = (f'{BASE}/es/iniciar-sesion', f'{BASE}/es/mi-cuenta')
EXCEL_URL = f'{BASE}/es/module/smcatalog/downloadcatalog?format=excel'
FILTRO_URL = f'{BASE}/es/module/amazzingfilter/ajax?ajax=1'
# Las categorias del listado filtrado que midio T1 (16 paginas en total). «pinturas» no tiene filtro de estado.
CATEGORIAS = ('distribucion-merchandising', 'distribucion-accesorios', 'trading-card-games',
              'distribucion-juegos-de-mesa')
POR_PAGINA = 111
MAX_PAGINAS = 20
ESPERA_S = 60
ESPERA_EXCEL_S = 180
PAUSA = (1.5, 4.0)
PAUSA_LARGA = (8.0, 20.0)
CADA_LARGA = (20, 40)
_XHR = {'Accept': 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest'}
_SENALES = ('g-recaptcha', 'cf-challenge', 'just a moment', 'cf-turnstile', 'hcaptcha', 'attention required')


class Bloqueo(Exception):
    """La web ha dicho que no (o algo raro): se para. El texto lo escribe este modulo."""


class Web:
    """La sesion con TCG. `sesion` es un curl_cffi Session (o uno de mentira en las pruebas)."""

    def __init__(self, sesion, dormir=time.sleep, azar=None):
        self.s = sesion
        self.dormir = dormir
        self.azar = azar or random.Random()
        self.peticiones = 0
        self._siguiente_larga = self.azar.randint(*CADA_LARGA)

    def pausa(self):
        espera = self.azar.uniform(*PAUSA)
        if self.peticiones >= self._siguiente_larga:
            espera += self.azar.uniform(*PAUSA_LARGA)
            self._siguiente_larga = self.peticiones + self.azar.randint(*CADA_LARGA)
        self.dormir(espera)

    def _pedir(self, que, metodo, url, **kw):
        self.pausa()
        try:
            r = (self.s.post if metodo == 'POST' else self.s.get)(url, **kw)
        except Exception as ex:  # noqa: BLE001 - un fallo de red tambien para; su texto puede llevar la URL
            raise Bloqueo(f'{que}: fallo de red ({type(ex).__name__})') from None
        self.peticiones += 1
        codigo = getattr(r, 'status_code', 0)
        if codigo in (403, 429, 503):
            raise Bloqueo(f'{que}: la web responde HTTP {codigo}')
        cabeza = (r.text[:30000] if isinstance(getattr(r, 'text', None), str) else '').lower()
        if any(s in cabeza for s in _SENALES):
            raise Bloqueo(f'{que}: la web enseña una comprobación anti-robots (captcha o similar)')
        return r

    # ── La sesion ────────────────────────────────────────────────────────────────────────
    def entrar(self, usuario, clave):
        """Login de PrestaShop por formulario (como director_tcg_prep.py). Bloqueo si no entra."""
        from escaner2_tcg_tramos import arbol
        form, accion = None, None
        for url in LOGIN_URLS:
            r = self._pedir('login (página)', 'GET', url, timeout=ESPERA_S)
            if r.status_code != 200:
                continue
            for f in arbol(r.text).buscar('form'):
                if any(i.attrs.get('type') == 'password' for i in f.buscar('input')):
                    form, accion = f, f.attrs.get('action') or url
                    break
            if form is not None:
                break
        if form is None:
            raise Bloqueo('login: no aparece el formulario de entrada')
        if accion.startswith('/'):
            accion = BASE + accion
        datos = {i.attrs['name']: i.attrs.get('value', '') for i in form.buscar('input') if i.attrs.get('name')}
        datos.update({'email': usuario, 'password': clave, 'submitLogin': '1'})
        r = self._pedir('login (envío)', 'POST', accion, data=datos, timeout=ESPERA_S, allow_redirects=True)
        if not _con_sesion(r.text):
            r = self._pedir('login (comprobación)', 'GET', f'{BASE}/es/mi-cuenta', timeout=ESPERA_S)
            if not _con_sesion(r.text):
                raise Bloqueo('login: la web no da la sesión por abierta (¿credenciales o captcha?)')

    def excel(self):
        """Los bytes del catalogo (.xlsx). Bloqueo si no llega un .xlsx."""
        r = self._pedir('Excel', 'GET', EXCEL_URL, timeout=ESPERA_EXCEL_S)
        contenido = r.content or b''
        if r.status_code != 200 or contenido[:2] != b'PK':
            raise Bloqueo(f'Excel: no llega un .xlsx (HTTP {r.status_code}, {len(contenido)} bytes)')
        return contenido

    def ficha(self, url):
        """El HTML de una ficha; None si la web dice 404 (esa ficha ya no esta). Bloqueo por lo demas que no sea 200."""
        if not url.startswith(BASE + '/'):
            raise Bloqueo('ficha: una URL que no es de la web de TCG')
        r = self._pedir('ficha', 'GET', url, timeout=ESPERA_S)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise Bloqueo(f'ficha: la web responde HTTP {r.status_code}')
        return r.text

    def listado(self, categoria):
        """Las tarjetas (HTML) del listado filtrado (Disponible, Oferta y Saldo) de una categoria, pagina a pagina.
        Devuelve (trozos_html, n_paginas). ListadoNoEntendido (de escaner2_tcg_tramos) si la forma no es la medida."""
        from escaner2_tcg_tramos import ListadoNoEntendido, formulario_filtro, tarjetas
        url_cat = f'{BASE}/es/{categoria}'
        r = self._pedir('listado (categoría)', 'GET', url_cat, timeout=ESPERA_S)
        if r.status_code != 200:
            raise Bloqueo(f'listado: la categoría responde HTTP {r.status_code}')
        ocultos, campo, valores = formulario_filtro(r.text)
        trozos, vistas = [], set()
        disparo = 'f' + ''.join(ch for ch in campo if ch.isdigit())  # «f[53][]» → «f53», como lo manda la web
        for pagina in range(1, MAX_PAGINAS + 1):
            campos = [(k, (str(POR_PAGINA) if k == 'nb_items' else str(pagina) if k == 'page' else v))
                      for k, v in ocultos]
            campos += [(campo, v) for v in valores]
            datos = {'params': urlencode(campos) + '&primary_filter=', 'current_url': url_cat,
                     'trigger': 'af_page' if pagina > 1 else disparo}
            rr = self._pedir('listado (página)', 'POST', FILTRO_URL, data=datos, headers=_XHR, timeout=90)
            if rr.status_code != 200:
                raise Bloqueo(f'listado: una página responde HTTP {rr.status_code}')
            try:
                j = rr.json()
            except Exception:  # noqa: BLE001
                raise ListadoNoEntendido('listado: una página no viene en JSON') from None
            html = j.get('product_list_html') if isinstance(j, dict) else None
            if not isinstance(html, str):
                raise ListadoNoEntendido('listado: el JSON no trae product_list_html')
            cards = tarjetas(html)
            nuevas = [t for t in cards if t['url'] and t['url'] not in vistas]
            vistas.update(t['url'] for t in nuevas)
            trozos.append(html)
            # La web devuelve la ultima pagina otra vez si se pide una de mas (T1, sonda 3): sin tarjetas nuevas, fin.
            if not nuevas or len(cards) < POR_PAGINA:
                return trozos, pagina
        return trozos, MAX_PAGINAS


def _con_sesion(html):
    h = (html or '').lower()
    return 'cerrar sesión' in h or 'cerrar sesion' in h or 'logout' in h


def sesion_de_verdad():
    from curl_cffi import requests as cr
    return cr.Session(impersonate='chrome120')
