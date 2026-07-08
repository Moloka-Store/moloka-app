#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# MOLOKA — TRACKEADOR DE PRECIOS · Procesador de snapshots (v0)
# ----------------------------------------------------------------------------
# Qué hace: cruza por ASIN las TRES fuentes y guarda una foto en monitor_snapshots
#   1) Informe de inventario FBA (Amazon)  -> tu precio, stock, ventas, buy box
#   2) Keepa "Resumen del Vendedor" (CSV)  -> competencia, comision, fee, volatilidad
#   3) Tabla 'productos' (Supabase)        -> PVD (coste) e iva_pct
# Calcula el MARGEN con la formula validada del escaner (NO reinterpretada) y
# escribe un snapshot por producto. Es la memoria historica del trackeador.
#
# NO genera recomendaciones (eso es el siguiente ladrillo, el "cerebro").
#
# Uso:
#   python -u moloka_tracker_snapshot.py --fba informe.txt --keepa keepa.csv [--pais ES] [--dry-run]
# Variables de entorno (GitHub Secrets): SUPABASE_URL, SUPABASE_KEY
# ============================================================================

import os, sys, argparse, json
from collections import Counter
from datetime import datetime, timezone
import pandas as pd

# --- Constantes de la formula (CLONADAS de moloka_escaner_nube.py, no tocar) ---
ALMACEN         = 0.15
COM_DIGITALES   = 1.03          # 3% servicios digitales de Amazon
IVA_DEFAULT_ES  = 0.21
SELLER_ID_MOLOKA = 'A2R25VOCZPEH8K'

# --- Cascada de comision% y fee/envio por pais (MISMOS datos que la pestana
#     "Rotacion de ventas" de la app) --------------------------------------
# Por cada pais y magnitud hay tres fuentes en prelacion:
#   1) 'real'      -> columna real de la tabla productos (comision_pct / comision_envio, etc.)
#   2) 'keepa_bd'  -> dato de Keepa cacheado en productos (comision_pct_keepa_es / keepa_fba_fee_*)
#   3) 'keepa_csv' -> del CSV de Keepa "Resumen del Vendedor" (ref_pct / fee_fba)
# ES no tiene columna 'keepa_bd' de comision distinta de comision_pct_keepa_es;
# IT/FR quedan preparados (misma estructura, con respaldo final al CSV de Keepa).
PAIS_CFG = {
    'ES': {'com_real': 'comision_pct',    'com_keepa': 'comision_pct_keepa_es',
           'fee_real': 'comision_envio',  'fee_keepa': 'keepa_fba_fee_es'},
    'IT': {'com_real': 'comision_pct_it', 'com_keepa': None,
           'fee_real': 'envio_it',        'fee_keepa': 'keepa_fba_fee_it'},
    'FR': {'com_real': 'comision_pct_fr', 'com_keepa': None,
           'fee_real': 'envio_fr',        'fee_keepa': 'keepa_fba_fee_fr'},
}

# Columnas de 'productos' que hay que leer para poder resolver la cascada de cualquier pais.
_COLS_PRODUCTO = ['asin', 'sku', 'ean', 'pvd', 'iva_pct',
                  'comision_pct', 'comision_pct_keepa_es', 'comision_pct_it', 'comision_pct_fr',
                  'comision_envio', 'keepa_fba_fee_es', 'envio_it', 'envio_fr',
                  'keepa_fba_fee_it', 'keepa_fba_fee_fr', 'stock_moloka']

# --- Nombres EXACTOS de columnas del Keepa "Resumen del Vendedor" ---
K = {
    'asin'        : 'ASIN',
    'ref_pct'     : '% de comisión de referencia',
    'fee_fba'     : 'Tarifa FBA Pick&Pack',
    'bb_vendedor' : 'Caja de Compra: Vendedor Caja de Compra',
    'bb_es_fba'   : 'Caja de Compra: Es FBA',
    'umbral'      : 'Umbral de precio competitivo',
    'fba_min'     : 'Nuevo, de Vendedor Externo FBA: Actual',
    'fbm_min'     : 'Nuevo, de Vendedor Externo FBM: Actual',
    'fba_min_v'   : 'Vendedor FBA más barato',
    'fbm_min_v'   : 'Vendedor FBM más barato',
    'ganadores'   : 'Caja de Compra: Recuento de ganadores 90 días',
    'desviacion'  : 'Caja de Compra: Desviación estándar 90 días',
    'ventas_list' : 'Tendencias de ventas mensuales: Comprados el mes pasado',
    'rank'        : 'Clasificación de Ventas: Actual',
    'n_fba'       : 'Recuento ofertas nuevas FBA: Actual',
    'n_fbm'       : 'Recuento ofertas nuevas FBM: Actual',
}

# ---------------------------------------------------------------------------
# Utilidades de parseo robusto (comas decimales, %, €, guiones, vacios)
# ---------------------------------------------------------------------------
def num(v):
    if v is None: return None
    s = str(v).strip().replace('%', '').replace('€', '').replace(',', '.').strip()
    if s in ('', '-', 'nan', 'None', 'NaN'): return None
    try: return float(s)
    except ValueError: return None

def ent(v):
    f = num(v)
    return int(f) if f is not None else None

def txt(v):
    if v is None: return None
    s = str(v).strip()
    return None if s in ('', '-', 'nan', 'None', 'NaN') else s

# ---------------------------------------------------------------------------
# Cascada de fuentes: primer valor no-NULL, con etiqueta de origen para auditar
# ---------------------------------------------------------------------------
def cascada(*candidatos):
    """candidatos = pares (valor, fuente). Devuelve el primer (valor, fuente)
    cuyo valor no es None; (None, None) si no hay ninguno."""
    for valor, fuente in candidatos:
        if valor is not None:
            return valor, fuente
    return None, None

# ---------------------------------------------------------------------------
# Formula de rentabilidad — CLONADA del escaner (validada al centimo)
# ---------------------------------------------------------------------------
def calc_rentabilidad(precio_venta, pa, ref_pct, fee_fba, iva):
    """Devuelve (beneficio_ud, margen_pct) o (None, None) si faltan datos."""
    if not precio_venta or ref_pct is None or fee_fba is None:
        return None, None
    base       = precio_venta / (1 + iva)
    com_amazon = precio_venta * (ref_pct / 100.0) * COM_DIGITALES
    beneficio  = base - (pa or 0) - com_amazon - fee_fba - ALMACEN
    margen     = beneficio / precio_venta * 100.0 if precio_venta else None
    return round(beneficio, 2), (round(margen, 2) if margen is not None else None)

# ---------------------------------------------------------------------------
# Lectura de las fuentes
# ---------------------------------------------------------------------------
def leer_fba(ruta):
    """Informe de inventario FBA (TSV). Devuelve dict por ASIN."""
    df = pd.read_csv(ruta, sep='\t', dtype=str, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    out = {}
    for _, r in df.iterrows():
        asin = txt(r.get('asin'))
        if not asin: continue
        out[asin] = {
            'sku'        : txt(r.get('sku')),
            'mi_precio'  : num(r.get('your-price')),
            'mi_stock'   : ent(r.get('available')),
            'v_t7'       : ent(r.get('units-shipped-t7')),
            'v_t30'      : ent(r.get('units-shipped-t30')),
            'v_t90'      : ent(r.get('units-shipped-t90')),
            'bb_precio'  : num(r.get('featuredoffer-price')),
            'rank'       : ent(r.get('sales-rank')),
        }
    return out

def leer_keepa(ruta):
    """Keepa Resumen del Vendedor (CSV). Devuelve dict por ASIN."""
    df = pd.read_csv(ruta, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    faltan = [v for v in K.values() if v not in df.columns]
    if faltan:
        print(f"  AVISO: faltan columnas en el Keepa (se ignoran): {faltan}")
    out = {}
    for _, r in df.iterrows():
        asin = txt(r.get(K['asin']))
        if not asin: continue
        bb_v = txt(r.get(K['bb_vendedor'], '')) or ''
        out[asin] = {
            'ref_pct'    : num(r.get(K['ref_pct'])),
            'fee_fba'    : num(r.get(K['fee_fba'])),
            'bb_vendedor': bb_v,
            'bb_es_mia'  : SELLER_ID_MOLOKA in bb_v,
            'bb_es_fba'  : str(r.get(K['bb_es_fba'], '')).strip().lower() in ('sí','si','yes','true','1'),
            'umbral'     : num(r.get(K['umbral'])),
            'fba_min'    : num(r.get(K['fba_min'])),
            'fbm_min'    : num(r.get(K['fbm_min'])),
            'fba_min_v'  : txt(r.get(K['fba_min_v'])),
            'fbm_min_v'  : txt(r.get(K['fbm_min_v'])),
            'ganadores'  : ent(r.get(K['ganadores'])),
            'desviacion' : num(r.get(K['desviacion'])),
            'ventas_list': ent(r.get(K['ventas_list'])),
            'rank_keepa' : ent(r.get(K['rank'])),
            'n_fba'      : ent(r.get(K['n_fba'])),
            'n_fbm'      : ent(r.get(K['n_fbm'])),
        }
    return out

def leer_productos_supabase(sb):
    """Lee coste (pvd), iva y las comisiones/fees por pais de la tabla productos
    (paginado). Guarda cada columna con su nombre real para la cascada."""
    out = {}
    desde = 0
    while True:
        res = sb.table('productos').select(
            ','.join(_COLS_PRODUCTO)).eq('activo', True).range(desde, desde+999).execute()
        filas = res.data or []
        for p in filas:
            asin = txt(p.get('asin'))
            if not asin: continue
            out[asin] = {
                'pvd'    : num(p.get('pvd')) or 0.0,
                'iva_pct': num(p.get('iva_pct')),
                'ean'    : txt(p.get('ean')),
                'sku'    : txt(p.get('sku')),
                # Comision% y fee/envio por pais (real + respaldo Keepa cacheado).
                'comision_pct'          : num(p.get('comision_pct')),
                'comision_pct_keepa_es' : num(p.get('comision_pct_keepa_es')),
                'comision_pct_it'       : num(p.get('comision_pct_it')),
                'comision_pct_fr'       : num(p.get('comision_pct_fr')),
                'comision_envio'        : num(p.get('comision_envio')),
                'keepa_fba_fee_es'      : num(p.get('keepa_fba_fee_es')),
                'envio_it'              : num(p.get('envio_it')),
                'envio_fr'              : num(p.get('envio_fr')),
                'keepa_fba_fee_it'      : num(p.get('keepa_fba_fee_it')),
                'keepa_fba_fee_fr'      : num(p.get('keepa_fba_fee_fr')),
                'stock_moloka'          : ent(p.get('stock_moloka')),
            }
        if len(filas) < 1000: break
        desde += 1000
    return out

def leer_venta_actual_supabase(sb):
    """Comision y envio EFECTIVOS de transacciones (SOLO ES) — la MISMA fuente
    que la pestana Rotacion. Vive en Supabase: tabla app_datos, clave='rentabilidad'
    (campo 'contenido', el rentabilidad.json entero) -> venta_actual[asin].
    Devuelve dict por ASIN con {comision_pct_mediana, envio_mediana}. Ambos ya en
    sus unidades finales (comision en PORCENTAJE, p.ej. 15.04; envio en euros)."""
    try:
        res = sb.table('app_datos').select('contenido').eq('clave', 'rentabilidad').limit(1).execute()
    except Exception as ex:
        print('  AVISO: no se pudo leer app_datos/rentabilidad (se ignora tx):', ex)
        return {}
    filas = res.data or []
    cont = filas[0].get('contenido') if filas else None
    if isinstance(cont, str):            # por si el jsonb llega como texto
        try: cont = json.loads(cont)
        except ValueError: cont = None
    va = (cont or {}).get('venta_actual') or {}
    out = {}
    for asin, v in va.items():
        a = txt(asin)
        if not a or not isinstance(v, dict): continue
        out[a] = {
            'comision_pct_mediana': num(v.get('comision_pct_mediana')),
            'envio_mediana'       : num(v.get('envio_mediana')),
        }
    return out

# ---------------------------------------------------------------------------
# Cruce y construccion de snapshots
# ---------------------------------------------------------------------------
def construir_snapshots(fba, keepa, prod, pais, origen, venta_tx=None):
    ahora = datetime.now(timezone.utc).isoformat()
    cfg = PAIS_CFG.get(pais, PAIS_CFG['ES'])   # ES por defecto
    tx = venta_tx or {}
    usa_tx = (pais == 'ES')   # la comision/envio efectivos de transacciones son SOLO-ES
    filas, sin_pvd, sin_keepa = [], 0, 0
    for asin, f in fba.items():
        k = keepa.get(asin, {})
        p = prod.get(asin, {})
        if not k: sin_keepa += 1
        if not p or not p.get('pvd'): sin_pvd += 1

        # Cascada (misma prelacion que la pestana Rotacion):
        #   ES : real_tx (transacciones) -> ficha -> keepa cacheado -> CSV Keepa
        #   IT/FR: ficha -> keepa cacheado -> CSV Keepa   (no hay dato real, es solo-ES)
        vt = tx.get(asin, {}) if usa_tx else {}
        com_pct, com_fuente = cascada(
            (vt.get('comision_pct_mediana'),                    'real_tx'),
            (p.get(cfg['com_real']),                            'real'),
            (p.get(cfg['com_keepa']) if cfg['com_keepa'] else None, 'keepa_bd'),
            (k.get('ref_pct'),                                  'keepa_csv'))
        fee, fee_fuente = cascada(
            (vt.get('envio_mediana'),                           'real_tx'),
            (p.get(cfg['fee_real']),                            'real'),
            (p.get(cfg['fee_keepa']) if cfg['fee_keepa'] else None, 'keepa_bd'),
            (k.get('fee_fba'),                                  'keepa_csv'))

        # Normalizar la comision a PORCENTAJE (mismo criterio que el IVA): el campo
        # real 'comision_pct' viene en DECIMAL (0.155 = 15,5%) y los de Keepa en
        # PORCENTAJE (15.03). Si el valor resuelto es < 1 es decimal -> x100; la
        # formula ya divide /100, asi que un decimal acaba multiplicando el precio
        # directamente. Aplica a ES e IT/FR (va despues de la cascada, sin importar pais).
        if com_pct is not None and com_pct < 1:
            com_pct = com_pct * 100.0

        iva = p.get('iva_pct')
        iva = (iva/100.0 if iva and iva > 1 else iva) if iva is not None else IVA_DEFAULT_ES
        benef, margen = calc_rentabilidad(
            f.get('mi_precio'), p.get('pvd'), com_pct, fee, iva)

        # buy box mia: por Keepa (vendedor) o, si no hay Keepa, por precio ~ featuredoffer
        bb_mia = k.get('bb_es_mia')
        if bb_mia is None and f.get('mi_precio') and f.get('bb_precio'):
            bb_mia = abs(f['mi_precio'] - f['bb_precio']) < 0.01

        filas.append({
            'snapshot_ts': ahora, 'pais': pais, 'asin': asin,
            'sku': f.get('sku') or p.get('sku'), 'ean': p.get('ean'),
            'mi_precio': f.get('mi_precio'), 'mi_stock': f.get('mi_stock'),
            'stock_almacen': p.get('stock_moloka'),
            'mis_ventas_t7': f.get('v_t7'), 'mis_ventas_t30': f.get('v_t30'),
            'mis_ventas_t90': f.get('v_t90'), 'pvd': p.get('pvd'),
            'mi_beneficio_ud': benef, 'mi_margen_pct': margen,
            # Datos usados en el calculo + de que fuente salieron (auditoria):
            'comision_pct_usada': com_pct, 'comision_fuente': com_fuente,
            'fee_fba_usada': fee, 'fee_fuente': fee_fuente,
            'buybox_precio': f.get('bb_precio'), 'buybox_vendedor': k.get('bb_vendedor'),
            'buybox_es_mia': bb_mia, 'buybox_es_fba': k.get('bb_es_fba'),
            'fba_min_precio': k.get('fba_min'), 'fba_min_vendedor': k.get('fba_min_v'),
            'fbm_min_precio': k.get('fbm_min'), 'fbm_min_vendedor': k.get('fbm_min_v'),
            'umbral_supresion': k.get('umbral'),
            'rank': f.get('rank') or k.get('rank_keepa'),
            'ventas_listado_mes': k.get('ventas_list'),
            'num_ofertas_fba': k.get('n_fba'), 'num_ofertas_fbm': k.get('n_fbm'),
            'ganadores_bb_90d': k.get('ganadores'), 'desviacion_bb_90d': k.get('desviacion'),
            'origen_carga': origen,
        })
    return filas, sin_pvd, sin_keepa

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fba', required=True, help='Informe de inventario FBA (TSV)')
    ap.add_argument('--keepa', required=True, help='Keepa Resumen del Vendedor (CSV)')
    ap.add_argument('--pais', default='ES')
    ap.add_argument('--dry-run', action='store_true', help='No escribe en Supabase; solo resumen')
    args = ap.parse_args()

    origen = os.path.basename(args.keepa)
    print(f">>> TRACKEADOR SNAPSHOT · pais={args.pais} · dry_run={args.dry_run}")
    print(f"    FBA:   {args.fba}")
    print(f"    Keepa: {args.keepa}\n")

    print("[1/4] Leyendo informe FBA...")
    fba = leer_fba(args.fba);   print(f"      {len(fba)} productos con ASIN")
    print("[2/4] Leyendo Keepa...")
    keepa = leer_keepa(args.keepa); print(f"      {len(keepa)} productos con ASIN")

    sb = None
    prod = {}
    venta_tx = {}
    if not args.dry_run:
        from supabase import create_client
        sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
        print("[3/4] Leyendo PVD/IVA de Supabase (productos)...")
        prod = leer_productos_supabase(sb); print(f"      {len(prod)} productos con coste")
        venta_tx = leer_venta_actual_supabase(sb)
        print(f"      {len(venta_tx)} ASINs con comision/envio efectivos (venta_actual, solo ES)")
    else:
        print("[3/4] DRY-RUN: no se lee Supabase (PVD=0, IVA=21% para la prueba)")

    print("[4/4] Cruzando y calculando margen...")
    filas, sin_pvd, sin_keepa = construir_snapshots(fba, keepa, prod, args.pais, origen, venta_tx)
    print(f"      {len(filas)} snapshots construidos "
          f"({sin_keepa} sin datos Keepa, {sin_pvd} sin PVD)")

    con_margen = [f for f in filas if f['mi_margen_pct'] is not None]
    if con_margen:
        margenes = sorted(f['mi_margen_pct'] for f in con_margen)
        print(f"      margen calculado en {len(con_margen)} · "
              f"min {margenes[0]:.1f}% · mediana {margenes[len(margenes)//2]:.1f}% · max {margenes[-1]:.1f}%")
    # Auditoria: de que fuente salio la comision y el fee (real / keepa_bd / keepa_csv / None)
    tal_com = Counter(f['comision_fuente'] for f in filas)
    tal_fee = Counter(f['fee_fuente'] for f in filas)
    print(f"      fuentes comision: {dict(tal_com)} · fuentes fee/envio: {dict(tal_fee)}")

    if args.dry_run:
        print("\n--- EJEMPLOS (primeros 5 con margen) ---")
        for f in con_margen[:5]:
            print(f"  {f['asin']} | precio {f['mi_precio']} | bb {f['buybox_precio']} "
                  f"| com {f['comision_pct_usada']}% ({f['comision_fuente']}) "
                  f"| fee {f['fee_fba_usada']}€ ({f['fee_fuente']}) "
                  f"| margen {f['mi_margen_pct']}% | benef {f['mi_beneficio_ud']}€")
        print("\nDRY-RUN OK — no se ha escrito nada en Supabase.")
        return

    # Proteccion anti-recarga: no duplicar si ya hay snapshot de este mismo fichero+pais
    ya = sb.table('monitor_snapshots').select('id').eq('pais', args.pais)\
           .eq('origen_carga', origen).limit(1).execute()
    if ya.data:
        print(f"\n[STOP] Ya existen snapshots del fichero '{origen}' en {args.pais}. "
              f"No se reescribe (evita duplicar). Borra esos snapshots si quieres recargar.")
        return

    print(f"\nEscribiendo {len(filas)} snapshots en Supabase...")
    for i in range(0, len(filas), 200):
        sb.table('monitor_snapshots').insert(filas[i:i+200]).execute()
        print(f"  {min(i+200, len(filas))}/{len(filas)}")
    print(">>> SNAPSHOTS GUARDADOS OK")

if __name__ == '__main__':
    main()
