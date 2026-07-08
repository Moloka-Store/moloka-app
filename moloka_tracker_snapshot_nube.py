#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# MOLOKA — TRACKEADOR DE PRECIOS · Robot de snapshots EN LA NUBE (GitHub Actions)
# ----------------------------------------------------------------------------
# Segunda mitad del flujo del trackeador: Fernando ya subio en la app los DOS
# ficheros (informe de inventario FBA + CSV del Keepa "Resumen del Vendedor").
# Este robot los lee del BUZON de Supabase Storage (no de argumentos), corre el
# MOTOR VALIDADO (moloka_tracker_snapshot.py: mismas formulas y cruce por ASIN)
# y escribe una foto por producto en monitor_snapshots. CERO tokens de Keepa.
#
# Buzon: informes/tracker/  con:
#   _solicitud_tracker.json  -> {"fba": "<fichero>", "keepa": "<fichero>", "pais": "ES"}
#   <fba>    -> informe de inventario FBA (TSV) subido por la app
#   <keepa>  -> CSV del Keepa "Resumen del Vendedor" subido por la app
#
# NO genera recomendaciones (eso es el siguiente ladrillo, el "cerebro").
# NO toca la operativa de la fabrica (Elena): otro bucket/otras tablas.
#
# Secrets (GitHub -> env): SUPABASE_URL, SUPABASE_KEY (o SUPABASE_SERVICE_KEY).
# ============================================================================

import os, sys, json, tempfile
from supabase import create_client

# Motor validado (mismo repo). NO re-implementamos formulas ni parseo: se
# reutilizan tal cual las funciones de la version CLI.
from moloka_tracker_snapshot import (
    leer_fba, leer_keepa, leer_productos_supabase, construir_snapshots)

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']
BUCKET = 'informes'
BUZON  = 'tracker'
RECADO = '_solicitud_tracker.json'
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def _bajar(ruta_buzon, destino):
    """Descarga un fichero del buzon. La app comprime en gzip los ficheros
    grandes al subir; aqui los descomprimimos si vienen gzip (magic 1f 8b),
    igual que el escaner Pro."""
    data = sb.storage.from_(BUCKET).download(ruta_buzon)
    if len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b:
        import gzip
        data = gzip.decompress(data)
        if destino.endswith('.gz'): destino = destino[:-3]
    with open(destino, 'wb') as f: f.write(data)
    return destino

def leer_recado():
    data = sb.storage.from_(BUCKET).download(f'{BUZON}/{RECADO}')
    return json.loads(data.decode('utf-8'))

def limpiar_buzon():
    """Vacia el buzon (deja solo dotfiles) tras un procesado terminal, para que
    la app no reprocese los mismos ficheros en la siguiente ejecucion."""
    try:
        objs = sb.storage.from_(BUCKET).list(BUZON) or []
        borrar = [f'{BUZON}/{o["name"]}' for o in objs if not o['name'].startswith('.')]
        if borrar: sb.storage.from_(BUCKET).remove(borrar)
        print(f"Buzon limpiado: {len(borrar)} ficheros.")
    except Exception as ex:
        print('AVISO: no se pudo limpiar el buzon:', ex)

def main():
    rec = leer_recado()
    fba_fic = rec.get('fba'); keepa_fic = rec.get('keepa')
    pais = (rec.get('pais') or 'ES').strip().upper()
    if not fba_fic or not keepa_fic:
        sys.exit(f"[ERROR] El recado {RECADO} debe indicar 'fba' y 'keepa'. Recibido: {rec}")
    origen = os.path.basename(keepa_fic)      # misma clave anti-recarga que la version CLI
    print(f">>> TRACKEADOR SNAPSHOT (NUBE) · pais={pais}")
    print(f"    FBA:   {BUZON}/{fba_fic}")
    print(f"    Keepa: {BUZON}/{keepa_fic}\n")

    tmp = tempfile.mkdtemp()
    print("[1/4] Bajando y leyendo informe FBA...")
    fba_path = _bajar(f'{BUZON}/{fba_fic}', os.path.join(tmp, os.path.basename(fba_fic)))
    fba = leer_fba(fba_path); print(f"      {len(fba)} productos con ASIN")
    print("[2/4] Bajando y leyendo Keepa...")
    keepa_path = _bajar(f'{BUZON}/{keepa_fic}', os.path.join(tmp, os.path.basename(keepa_fic)))
    keepa = leer_keepa(keepa_path); print(f"      {len(keepa)} productos con ASIN")

    print("[3/4] Leyendo PVD/IVA de Supabase (productos)...")
    prod = leer_productos_supabase(sb); print(f"      {len(prod)} productos con coste")

    print("[4/4] Cruzando y calculando margen...")
    filas, sin_pvd, sin_keepa = construir_snapshots(fba, keepa, prod, pais, origen)
    print(f"      {len(filas)} snapshots construidos "
          f"({sin_keepa} sin datos Keepa, {sin_pvd} sin PVD)")

    con_margen = [f for f in filas if f['mi_margen_pct'] is not None]
    if con_margen:
        margenes = sorted(f['mi_margen_pct'] for f in con_margen)
        print(f"      margen calculado en {len(con_margen)} · "
              f"min {margenes[0]:.1f}% · mediana {margenes[len(margenes)//2]:.1f}% · max {margenes[-1]:.1f}%")

    # Proteccion anti-recarga: no duplicar si ya hay snapshot de este fichero+pais.
    ya = sb.table('monitor_snapshots').select('id').eq('pais', pais)\
           .eq('origen_carga', origen).limit(1).execute()
    if ya.data:
        print(f"\n[STOP] Ya existen snapshots del fichero '{origen}' en {pais}. "
              f"No se reescribe (evita duplicar).")
        limpiar_buzon()
        return

    print(f"\nEscribiendo {len(filas)} snapshots en Supabase...")
    for i in range(0, len(filas), 200):
        sb.table('monitor_snapshots').insert(filas[i:i+200]).execute()
        print(f"  {min(i+200, len(filas))}/{len(filas)}")
    print(">>> SNAPSHOTS GUARDADOS OK")

    # Buzon limpio SOLO tras un guardado correcto (si algo falla antes, se deja
    # para reintentar en la siguiente ejecucion).
    limpiar_buzon()

if __name__ == '__main__':
    main()
