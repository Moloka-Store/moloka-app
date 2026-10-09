#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# descargar_dbline.py  —  Descarga el catalogo de DBLine POR SERVIDOR (sin Chrome).
# DBLine (shop.dbline.it) es web a medida con buzones AJAX. Cazado con DevTools:
#   LOGIN:    POST /include/login_ajax.php           action=ESEGUI_LOGIN + codclifor + password(claro) + checkricorda + otp
#   DESCARGA: POST /include/Servizi/listini_ajax.php action=DOWNLOAD_CATALOGO_GENERALE + formato=xlsx
# Credenciales SOLO en Secrets (DBLINE_USER = codclifor, DBLINE_PASS). NUNCA en el codigo.
#
# Ejecutable suelto = PRUEBA (baja y verifica). El director importa descargar_catalogo_dbline().
#
# 🔴 REPO PUBLICO (encargo DB2-B, 9-oct-2026): al registro SOLO codigos de estado y bytes. Ni la respuesta del login,
#    ni trozos de la respuesta, ni URLs, ni cabeceras. El error, igual: dice que paso con codigos y bytes.
import os, sys, io, re
from curl_cffi import requests as cr
import openpyxl

BASE = 'https://shop.dbline.it'
LOGIN_URL = f'{BASE}/include/login_ajax.php'
DOWNLOAD_URL = f'{BASE}/include/Servizi/listini_ajax.php'

# La cadena de certificados de shop.dbline.it (GoDaddy), para verificar la conexion: ver el propio fichero.
CADENA_DBLINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certificados', 'dbline_cadena.pem')


# Mapa cabeceras INGLES -> ITALIANO. DBLine exporta por servidor en ingles y por navegador
# en italiano; el perfil del escaner usa los nombres italianos. Traducimos para que el
# escaner lea igual venga como venga (sin tocar el escaner).
_MAP_ITA = {
    'Genre': 'Genere', 'Price List ID': 'ID Listino', 'Image Link': 'Link immagine',
    'Code/Link': 'Codice/Link', 'Description': 'Descrizione', 'Notes': 'Note',
    'Release date': 'Data uscita', 'Available': 'Disponibili', 'List Price (€)': 'Listino (€)',
    'Discount 1 (%)': 'Sconto 1 (%)', 'Discount 2 (%)': 'Sconto 2 (%)', 'Price (€)': 'Prezzo (€)',
    'VAT (%)': 'Iva (%)', 'Promo Expiration': 'Scadenza promo', 'Promo Price (€)': 'Prezzo promo (€)',
    'Weight (gr)': 'Peso (gr)',
}


def _normalizar_cabeceras(cont):
    import openpyxl, io as _io
    wb = openpyxl.load_workbook(_io.BytesIO(cont))
    ws = wb[wb.sheetnames[0]]
    hdr = None
    for r in range(1, 7):
        vals = [str(ws.cell(row=r, column=c).value or '').strip() for c in range(1, ws.max_column + 1)]
        if 'Publisher' in vals and 'EAN' in vals:
            hdr = r; break
    if hdr is None:
        print('   AVISO: no encuentro la fila de cabecera; dejo el Excel tal cual.', flush=True)
        return cont
    cambiadas = 0
    for c in range(1, ws.max_column + 1):
        cell = ws.cell(row=hdr, column=c)
        v = str(cell.value or '').strip()
        if v in _MAP_ITA:
            cell.value = _MAP_ITA[v]; cambiadas += 1
    if cambiadas:
        print(f'   Cabeceras traducidas ingles->italiano: {cambiadas} columnas (fila {hdr}).', flush=True)
        out = _io.BytesIO(); wb.save(out); return out.getvalue()
    print('   Cabeceras ya en italiano; no toco nada.', flush=True)
    return cont


def descargar_catalogo_dbline(verificar=False):
    """Los bytes del catalogo general de DBLine (.xlsx, cabeceras en italiano).

    `verificar` va tal cual al `verify` de curl_cffi:
      · False (por defecto, COMO HASTA HOY): no se valida el certificado. Lo usa el director viejo; no cambia.
      · CADENA_DBLINE: se valida contra la cadena GoDaddy del fichero de la v1. Lo usa la pasada nueva
        (escaner2_dbline_disponibilidad.py). Si no valida, curl_cffi lanza su error y no se baja nada.
    """
    USER, PASS = os.environ.get('DBLINE_USER'), os.environ.get('DBLINE_PASS')
    if not USER or not PASS:
        raise RuntimeError('Faltan los secrets DBLINE_USER / DBLINE_PASS.')
    # verify=False (por defecto): descargar_dbline.py nacio con la cadena SSL de DBLine mal montada (le faltaba el
    # intermedio) y el runner no podia validar su certificado (curl error 60). La conexion sigue cifrada por HTTPS;
    # solo se salta la validacion de la cadena. La pasada nueva SI valida (verificar=CADENA_DBLINE).
    s = cr.Session(impersonate='chrome120', verify=verificar)
    ajax = {'X-Requested-With': 'XMLHttpRequest', 'Origin': BASE, 'Referer': BASE + '/'}

    # 0) Home -> cookies de sesion iniciales
    print('>>> Abriendo la home de DBLine (cookies)...', flush=True)
    r0 = s.get(BASE + '/', timeout=60)
    print(f'   home -> {r0.status_code} ({len(r0.content)} bytes)', flush=True)

    # 1) Login (clave en claro, POST AJAX). 🔴 Su respuesta NO se imprime: solo el codigo y los bytes.
    print('>>> Enviando login...', flush=True)
    r1 = s.post(LOGIN_URL, data={'action': 'ESEGUI_LOGIN', 'codclifor': USER,
                                 'password': PASS, 'checkricorda': 'N', 'otp': ''},
                headers=ajax, timeout=60)
    print(f'   login -> {r1.status_code} ({len(r1.content)} bytes)', flush=True)
    low = r1.text.lower()
    login_ko = ('errata' in low) or ('non valido' in low) or ('errore' in low and 'ok' not in low)
    if login_ko:
        print('   AVISO: el login parece NO haber entrado (su respuesta no se imprime: repo publico).', flush=True)

    # 2) Descargar catalogo (POST AJAX). A veces el AJAX responde con la URL del fichero.
    print('>>> Descargando catalogo (DOWNLOAD_CATALOGO_GENERALE)...', flush=True)
    r2 = s.post(DOWNLOAD_URL, data={'action': 'DOWNLOAD_CATALOGO_GENERALE', 'formato': 'xlsx'},
                headers=ajax, timeout=300)
    cont = r2.content
    print(f'   descarga -> {r2.status_code} ({len(cont)} bytes)', flush=True)

    enlace = 'sin buscar'
    if cont[:2] != b'PK':
        txt = cont[:600].decode('utf-8', 'replace')
        print('   No es un .xlsx directo; busco en la respuesta un enlace a un .xlsx (ni la respuesta ni el enlace '
              'se imprimen).', flush=True)
        m = re.search(r'(https?://[^\s"\'<>]+\.xlsx[^\s"\'<>]*)', txt) or re.search(r'([\w./\-]+\.xlsx)', txt)
        enlace = 'sin enlace a un .xlsx en la respuesta'
        if m:
            url = m.group(1)
            if url.startswith('/'): url = BASE + url
            elif not url.startswith('http'): url = BASE + '/' + url
            r3 = s.get(url, headers={'Referer': BASE + '/'}, timeout=300)
            cont = r3.content
            enlace = f'el enlace a un .xlsx dio {r3.status_code} ({len(cont)} bytes)'
            print(f'   fichero enlazado -> {r3.status_code} ({len(cont)} bytes)', flush=True)

    if cont[:2] != b'PK':
        # 🔑 Dice QUE PASO sin depender del registro (la pasada nueva se traga el registro de este modulo): codigos,
        #    bytes y si el login parecia fallar. Nunca la respuesta ni una URL.
        raise RuntimeError(
            f'La descarga NO es un .xlsx: home {r0.status_code}, login {r1.status_code} '
            f'({"parece que NO entra" if login_ko else "sin señal de error en su respuesta"}), descarga '
            f'{r2.status_code} ({len(r2.content)} bytes, no empieza como un .xlsx), {enlace}. Lo normal: login caducado '
            f'o que DBLine ha cambiado la respuesta de la descarga.')

    wb = openpyxl.load_workbook(io.BytesIO(cont), read_only=True, data_only=True)
    wb.close()
    print(f'   Excel VALIDO ({len(cont)} bytes).', flush=True)
    cont = _normalizar_cabeceras(cont)   # ingles -> italiano para que el escaner lo lea
    return cont


if __name__ == '__main__':
    cont = descargar_catalogo_dbline()
    with open('dblinecatalog.xlsx', 'wb') as f:
        f.write(cont)
    print('>>> PRUEBA OK: DBLine se baja por servidor, sin Chrome. 🎉', flush=True)
