#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# descargar_dbline.py  —  Descarga el catalogo de DBLine POR SERVIDOR (sin Chrome).
# DBLine (shop.dbline.it) es web a medida con buzones AJAX. Cazado con DevTools:
#   LOGIN:    POST /include/login_ajax.php           action=ESEGUI_LOGIN + codclifor + password(claro) + checkricorda + otp
#   DESCARGA: POST /include/Servizi/listini_ajax.php action=DOWNLOAD_CATALOGO_GENERALE + formato=xlsx
# Credenciales SOLO en Secrets (DBLINE_USER = codclifor, DBLINE_PASS). NUNCA en el codigo.
#
# Ejecutable suelto = PRUEBA (baja y verifica). El director importa descargar_catalogo_dbline().
import os, sys, io, re
from curl_cffi import requests as cr
import openpyxl

BASE = 'https://shop.dbline.it'
LOGIN_URL = f'{BASE}/include/login_ajax.php'
DOWNLOAD_URL = f'{BASE}/include/Servizi/listini_ajax.php'

def descargar_catalogo_dbline():
    USER, PASS = os.environ.get('DBLINE_USER'), os.environ.get('DBLINE_PASS')
    if not USER or not PASS:
        raise RuntimeError('Faltan los secrets DBLINE_USER / DBLINE_PASS.')
    s = cr.Session(impersonate='chrome120')
    ajax = {'X-Requested-With': 'XMLHttpRequest', 'Origin': BASE, 'Referer': BASE + '/'}

    # 0) Home -> cookies de sesion iniciales
    print('>>> Abriendo la home de DBLine (cookies)...', flush=True)
    r0 = s.get(BASE + '/', timeout=60)
    print(f'   home -> {r0.status_code} ({len(r0.text)} bytes)', flush=True)

    # 1) Login (clave en claro, POST AJAX)
    print('>>> Enviando login...', flush=True)
    r1 = s.post(LOGIN_URL, data={'action': 'ESEGUI_LOGIN', 'codclifor': USER,
                                 'password': PASS, 'checkricorda': 'N', 'otp': ''},
                headers=ajax, timeout=60)
    print(f'   login -> {r1.status_code} | respuesta: {r1.text[:300]}', flush=True)
    low = r1.text.lower()
    if ('errata' in low) or ('non valido' in low) or ('errore' in low and 'ok' not in low):
        print('   AVISO: el login parece NO haber entrado (revisa la respuesta de arriba).', flush=True)

    # 2) Descargar catalogo (POST AJAX). A veces el AJAX responde con la URL del fichero.
    print('>>> Descargando catalogo (DOWNLOAD_CATALOGO_GENERALE)...', flush=True)
    r2 = s.post(DOWNLOAD_URL, data={'action': 'DOWNLOAD_CATALOGO_GENERALE', 'formato': 'xlsx'},
                headers=ajax, timeout=300)
    cont = r2.content
    print(f'   descarga -> {r2.status_code} | {len(cont)} bytes | content-type: {r2.headers.get("content-type","")}', flush=True)

    if cont[:2] != b'PK':
        txt = cont[:600].decode('utf-8', 'replace')
        print('   No es un .xlsx directo. Respuesta (primeros 600):', txt, flush=True)
        m = re.search(r'(https?://[^\s"\'<>]+\.xlsx[^\s"\'<>]*)', txt) or re.search(r'([\w./\-]+\.xlsx)', txt)
        if m:
            url = m.group(1)
            if url.startswith('/'): url = BASE + url
            elif not url.startswith('http'): url = BASE + '/' + url
            print('   Intento bajar el fichero enlazado:', url, flush=True)
            r3 = s.get(url, headers={'Referer': BASE + '/'}, timeout=300)
            cont = r3.content
            print(f'   fichero -> {r3.status_code} | {len(cont)} bytes', flush=True)

    if cont[:2] != b'PK':
        raise RuntimeError('La descarga NO es un .xlsx (login caducado, cabecera distinta o el action devuelve otra cosa). Mira el log de arriba.')

    wb = openpyxl.load_workbook(io.BytesIO(cont), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    print(f'   Excel VALIDO: hoja "{wb.sheetnames[0]}", ~{ws.max_row} filas | hojas: {wb.sheetnames}', flush=True)
    return cont


if __name__ == '__main__':
    cont = descargar_catalogo_dbline()
    with open('dblinecatalog.xlsx', 'wb') as f:
        f.write(cont)
    print('>>> PRUEBA OK: DBLine se baja por servidor, sin Chrome. 🎉', flush=True)
