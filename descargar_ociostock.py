#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# descargar_ociostock.py - Descarga el feed CSV de OcioStock POR URL (sin login).
# ------------------------------------------------------------
# La URL lleva el TOKEN de acceso de Fernando y vive SOLO en el Secret
# OCIOSTOCK_FEED_URL (GitHub Secrets). NUNCA en el codigo ni en logs.
# Ejecutable suelto = PRUEBA (baja y verifica). El director importa
# descargar_catalogo_ociostock().
# ============================================================
import os, sys, requests


def descargar_catalogo_ociostock():
    url = os.environ.get('OCIOSTOCK_FEED_URL')
    if not url:
        raise RuntimeError("Falta el Secret OCIOSTOCK_FEED_URL")
    print('>>> Descargando feed de OcioStock por URL...', flush=True)
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    cont = r.content
    # Si el fichero viene comprimido en gzip (magic 1f 8b), lo dejamos en CSV plano.
    if cont[:2] == b'\x1f\x8b':
        import gzip
        cont = gzip.decompress(cont)
        print('>>> El feed venia en gzip: descomprimido a CSV plano.')
    # Verificacion minima: que huela al CSV de OcioStock (separador ';' + columna 'ean').
    cab = cont[:2000].decode('utf-8-sig', errors='ignore').lower()
    if ('ean' not in cab) or (';' not in cab):
        raise RuntimeError("El contenido descargado no parece el CSV de OcioStock "
                           "(no encuentro 'ean'/';' en la cabecera). ¿URL correcta?")
    return cont


if __name__ == '__main__':
    c = descargar_catalogo_ociostock()
    cab = c[:150].decode('utf-8-sig', errors='ignore').replace('\n', ' ')
    print(f"OK: {len(c)} bytes descargados.")
    print(f"Cabecera: {cab}")
