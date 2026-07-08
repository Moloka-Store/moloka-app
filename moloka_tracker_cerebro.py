#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# MOLOKA — TRACKEADOR DE PRECIOS · CEREBRO (generador de recomendaciones)
# ----------------------------------------------------------------------------
# Lee la ULTIMA carga de monitor_snapshots por pais y decide, producto a
# producto, que hacer con el precio. Escribe el resultado en
# monitor_recomendaciones con estado PENDIENTE. NO cambia precios.
#
# Reutiliza la formula de margen del trackeador (calc_rentabilidad) para
# recomputar el margen a un precio hipotetico -> asi las decisiones usan la
# MISMA aritmetica que el snapshot (y que la pestana Rotacion).
#
# Uso:
#   python -u moloka_tracker_cerebro.py [--pais ES|IT|FR|ALL] [--dry-run]
# Variables de entorno (GitHub Secrets): SUPABASE_URL, SUPABASE_KEY
# ============================================================================

import os, sys, argparse, json
from datetime import datetime, timezone

# Formula y parsers CLONADOS del trackeador (no reimplementamos aritmetica).
from moloka_tracker_snapshot import calc_rentabilidad, num, txt

# --- IVA por pais (para recomputar margen a un precio hipotetico) ---
IVA_PAIS    = {'ES': 0.21, 'IT': 0.22, 'FR': 0.20}
IVA_DEFAULT = 0.21
PAISES_CONOCIDOS = ['ES', 'IT', 'FR']

# --- Parametros de decision (TUNEABLES) ---
UMBRAL_DEFAULT        = 2.0     # % de margen minimo para competir (si no hay regla)
SUBIR_BAJO_COMPETIDOR = 0.20    # € por debajo del competidor FBA de arriba al subir
UNDERCUT_FBA          = 0.01    # € por debajo del rival FBA para ganarle la Buy Box
PREMIUM_FBA_SOBRE_FBM = 0.01    # € por encima del FBM (la ventaja FBA gana la BB)
GUERRA_MIN_GANADORES  = 5       # nº de ganadores de BB en 90d para sospechar guerra
GUERRA_DESVIACION_REL = 0.05    # desviacion_bb_90d / precio_bb >= 5% -> volatil
EPS = 0.01                      # tolerancia de 1 centimo

# --- Acciones (valores del campo 'accion') ---
SUBIR, BAJAR, MANTENER   = 'SUBIR', 'BAJAR', 'MANTENER'
RECUPERAR_BB             = 'RECUPERAR_BB'
NO_RENTABLE              = 'NO_RENTABLE_COMPETIR'
GUERRA                   = 'GUERRA_ACTIVA'
MALVENDIENDO             = 'MALVENDIENDO'
SIN_ACCION, SIN_DATOS    = 'SIN_ACCION', 'SIN_DATOS'

# ---------------------------------------------------------------------------
# Lecturas
# ---------------------------------------------------------------------------
def leer_umbral(sb):
    """Umbral de rentabilidad (%). 1º monitor_reglas, 2º app_datos, si no 2.0."""
    try:
        r = sb.table('monitor_reglas').select('clave,valor').eq('clave', 'umbral_margen_pct').limit(1).execute()
        if r.data:
            v = num(r.data[0].get('valor'))
            if v is not None: return v, 'monitor_reglas'
    except Exception: pass
    try:
        r = sb.table('app_datos').select('contenido').eq('clave', 'monitor_reglas').limit(1).execute()
        if r.data:
            cont = r.data[0].get('contenido')
            if isinstance(cont, str):
                try: cont = json.loads(cont)
                except ValueError: cont = None
            v = num((cont or {}).get('umbral_margen_pct'))
            if v is not None: return v, 'app_datos'
    except Exception: pass
    return UMBRAL_DEFAULT, 'default'

def ultima_carga(sb, pais):
    """Devuelve (filas, snapshot_ts) de la ULTIMA carga de ese pais, o ([],None)."""
    r = sb.table('monitor_snapshots').select('snapshot_ts').eq('pais', pais)\
          .order('snapshot_ts', desc=True).limit(1).execute()
    if not r.data: return [], None
    ts = r.data[0]['snapshot_ts']
    filas, desde = [], 0
    while True:
        res = sb.table('monitor_snapshots').select('*').eq('pais', pais)\
                .eq('snapshot_ts', ts).range(desde, desde+999).execute()
        lote = res.data or []
        filas.extend(lote)
        if len(lote) < 1000: break
        desde += 1000
    return filas, ts

# ---------------------------------------------------------------------------
# Nucleo de decision (PURO y testeable: recibe un snapshot dict)
# ---------------------------------------------------------------------------
def decidir(s, umbral, iva):
    """Devuelve un dict de recomendacion a partir de una fila de snapshot."""
    precio   = num(s.get('mi_precio'))
    pvd      = num(s.get('pvd'))
    com_pct  = num(s.get('comision_pct_usada'))
    fee      = num(s.get('fee_fba_usada'))
    com_fte  = txt(s.get('comision_fuente'))
    bb_mia   = s.get('buybox_es_mia')
    bb_fba   = s.get('buybox_es_fba')
    bb_prec  = num(s.get('buybox_precio'))
    bb_vend  = txt(s.get('buybox_vendedor'))
    fba_min  = num(s.get('fba_min_precio'))
    fbm_min  = num(s.get('fbm_min_precio'));  fbm_v = txt(s.get('fbm_min_vendedor'))
    umbral_sup = num(s.get('umbral_supresion'))
    ganadores  = num(s.get('ganadores_bb_90d'))
    desviacion = num(s.get('desviacion_bb_90d'))
    mi_margen  = num(s.get('mi_margen_pct'))
    mi_benef   = num(s.get('mi_beneficio_ud'))
    v_t30      = num(s.get('mis_ventas_t30')) or 0.0
    v_list     = num(s.get('ventas_listado_mes')) or 0.0

    def margen_en(px):
        if px is None: return (None, None)
        return calc_rentabilidad(px, pvd, com_pct, fee, iva)

    # Guerra de precios: muchos ganadores de BB + alta volatilidad del precio de BB
    guerra = (ganadores is not None and desviacion is not None and bb_prec and bb_prec > 0
              and ganadores >= GUERRA_MIN_GANADORES
              and (desviacion / bb_prec) >= GUERRA_DESVIACION_REL)

    accion, objetivo, motivo = SIN_ACCION, None, ''

    if bb_mia is True:
        # --- Tengo yo la Buy Box ---
        techos = []
        if fba_min is not None:   techos.append(fba_min - SUBIR_BAJO_COMPETIDOR)
        if umbral_sup is not None: techos.append(umbral_sup)
        techo = min(techos) if techos else None
        malvend = (com_fte == 'real_tx' and mi_margen is not None and mi_margen < 0)
        if malvend:
            accion  = MALVENDIENDO
            objetivo = techo if (techo is not None and precio is not None and techo > precio + EPS) else None
            motivo  = ("Margen NEGATIVO con datos reales de transacciones y tienes la Buy Box: "
                       "estas MALVENDIENDO, sube el precio" +
                       (f" (hasta {objetivo:.2f}€)" if objetivo is not None else " (sin techo claro por competidor/umbral)") + ".")
        elif techo is not None and precio is not None and techo > precio + EPS:
            accion, objetivo = SUBIR, round(techo, 2)
            motivo = (f"Tienes la Buy Box; puedes subir hasta {objetivo:.2f}€ "
                      f"(min de 'competidor FBA de arriba -0,20€' y umbral de supresion).")
        else:
            accion = MANTENER
            motivo = "Tienes la Buy Box y ya estas en el techo (competidor/umbral). Mantener."

    elif bb_mia is None:
        accion = SIN_DATOS
        motivo = "No se sabe quien tiene la Buy Box (sin dato en el snapshot)."

    else:
        # --- No tengo la Buy Box ---
        if bb_fba is False:
            # La tiene un FBM y yo soy FBA -> recuperarla quedandome por encima del FBM
            if fbm_min is not None:
                objetivo = round(fbm_min + PREMIUM_FBA_SOBRE_FBM, 2)
                _, m = margen_en(objetivo)
                if m is not None and m >= umbral:
                    accion = RECUPERAR_BB
                    motivo = (f"La Buy Box la tiene un FBM ({fbm_v or 'rival'}); como eres FBA puedes "
                              f"recuperarla por encima de el a {objetivo:.2f}€ (margen {m:.1f}% >= {umbral:.0f}%).")
                else:
                    accion, objetivo = NO_RENTABLE, None
                    motivo = (f"La tiene un FBM ({fbm_min:.2f}€) pero recuperarla dejaria el margen por "
                              f"debajo del {umbral:.0f}%: no compensa.")
            else:
                accion = SIN_ACCION
                motivo = "Buy Box en manos de un FBM pero sin precio FBM de referencia en el snapshot."
        else:
            # La tiene un FBA (o Amazon, tratado como competidor mas)
            if bb_prec is not None and precio is not None and bb_prec < precio - EPS:
                if guerra:
                    accion, objetivo = GUERRA, None
                    motivo = (f"Rival FBA mas barato ({bb_prec:.2f}€) pero hay GUERRA de precios "
                              f"(ganadores {ganadores:.0f} en 90d, desviacion alta): no bajar.")
                else:
                    objetivo = round(bb_prec - UNDERCUT_FBA, 2)
                    _, m = margen_en(objetivo)
                    if m is not None and m >= umbral:
                        accion = BAJAR
                        motivo = (f"La Buy Box la tiene un FBA mas barato ({bb_prec:.2f}€"
                                  + (f", {bb_vend}" if bb_vend else "") + f"); bajar a {objetivo:.2f}€ "
                                  f"mantiene margen {m:.1f}% >= {umbral:.0f}%.")
                    else:
                        accion, objetivo = NO_RENTABLE, None
                        motivo = (f"Bajar al nivel del rival ({bb_prec:.2f}€) dejaria el margen por debajo "
                                  f"del {umbral:.0f}%: NO rentable competir.")
            else:
                accion = MANTENER
                motivo = "No tienes la Buy Box, pero no hay un rival mas barato accionable por precio."

    # --- Margen objetivo e impacto en €/mes ---
    benef_obj, margen_obj = margen_en(objetivo) if objetivo is not None else (None, None)

    if accion in (SUBIR, MALVENDIENDO, MANTENER):
        # Mantengo la BB: mismo volumen, distinto margen unitario
        ventas_mes = v_t30
        extra_ud   = (benef_obj - mi_benef) if (benef_obj is not None and mi_benef is not None) else 0.0
        impacto    = extra_ud * ventas_mes
    elif accion in (RECUPERAR_BB, BAJAR):
        # Recupero la BB: capturo la demanda del mercado (listado) al nuevo margen
        ventas_mes = max(v_list, v_t30)
        impacto    = (benef_obj or 0.0) * ventas_mes - (mi_benef or 0.0) * v_t30
    else:
        ventas_mes = v_t30
        impacto    = 0.0

    confianza = ('alta' if com_fte == 'real_tx'
                 else 'media' if com_fte in ('real', 'keepa_bd')
                 else 'baja' if com_fte == 'keepa_csv' else None)

    return {
        'pais': s.get('pais'), 'asin': s.get('asin'), 'sku': s.get('sku'),
        'accion': accion, 'motivo': motivo,
        'precio_actual': precio, 'precio_objetivo': objetivo,
        'margen_actual_pct': mi_margen, 'margen_objetivo_pct': margen_obj,
        'beneficio_actual_ud': mi_benef, 'beneficio_objetivo_ud': benef_obj,
        'ventas_mes': ventas_mes, 'impacto_eur_mes': round(impacto, 2),
        'competidor_precio': bb_prec, 'competidor_vendedor': bb_vend,
        'buybox_es_mia': bb_mia, 'buybox_es_fba': bb_fba,
        'guerra_activa': bool(guerra),
        'fuente_margen': com_fte, 'confianza': confianza,
        'estado': 'PENDIENTE',
    }

def construir_recomendaciones(filas, umbral, iva, snapshot_ts, ahora):
    recos = []
    for s in filas:
        r = decidir(s, umbral, iva)
        if r['accion'] == SIN_DATOS and r['precio_actual'] is None:
            continue   # nada que decir
        r['snapshot_ts'] = snapshot_ts
        r['reco_ts'] = ahora
        r['origen_carga'] = txt(s.get('origen_carga'))
        recos.append(r)
    # Orden por impacto en € al mes (descendente)
    recos.sort(key=lambda x: (x['impacto_eur_mes'] if x['impacto_eur_mes'] is not None else 0), reverse=True)
    return recos

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def procesar_pais(sb, pais, umbral, iva, dry_run):
    filas, ts = ultima_carga(sb, pais)
    if not filas:
        print(f"[{pais}] sin snapshots. Saltando.")
        return
    print(f"[{pais}] ultima carga: {ts} · {len(filas)} productos")
    ahora = datetime.now(timezone.utc).isoformat()
    recos = construir_recomendaciones(filas, umbral, iva, ts, ahora)

    from collections import Counter
    tal = Counter(r['accion'] for r in recos)
    print(f"[{pais}] acciones: {dict(tal)}")

    if dry_run:
        print(f"[{pais}] --- TOP 8 por impacto (€/mes) ---")
        for r in recos[:8]:
            po = f"{r['precio_objetivo']:.2f}" if r['precio_objetivo'] is not None else '—'
            print(f"  {r['asin']} | {r['accion']:20} | {r['precio_actual']}→{po} | "
                  f"margen {r['margen_actual_pct']}→{r['margen_objetivo_pct']} | "
                  f"impacto {r['impacto_eur_mes']}€/mes | fuente {r['fuente_margen']}")
        return

    # Anti-recarga: no duplicar recomendaciones de esta misma carga (snapshot_ts+pais)
    ya = sb.table('monitor_recomendaciones').select('id').eq('pais', pais)\
           .eq('snapshot_ts', ts).limit(1).execute()
    if ya.data:
        print(f"[{pais}] ya hay recomendaciones para la carga {ts}. No se reescribe.")
        return

    print(f"[{pais}] escribiendo {len(recos)} recomendaciones...")
    for i in range(0, len(recos), 200):
        sb.table('monitor_recomendaciones').insert(recos[i:i+200]).execute()
        print(f"  {min(i+200, len(recos))}/{len(recos)}")
    print(f"[{pais}] OK")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pais', default='ES', help='ES | IT | FR | ALL')
    ap.add_argument('--dry-run', action='store_true', help='No escribe; solo resumen')
    args = ap.parse_args()

    print(f">>> CEREBRO TRACKEADOR · pais={args.pais} · dry_run={args.dry_run}")

    if args.dry_run and not (os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_KEY')):
        sys.exit("DRY-RUN necesita SUPABASE_URL/KEY para leer los snapshots (solo lee, no escribe).")

    from supabase import create_client
    sb = create_client(os.environ['SUPABASE_URL'],
                       os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY'])

    umbral, fuente_umbral = leer_umbral(sb)
    print(f"    Umbral de rentabilidad: {umbral:.1f}% (fuente: {fuente_umbral})")

    paises = PAISES_CONOCIDOS if args.pais.upper() == 'ALL' else [args.pais.upper()]
    for pais in paises:
        iva = IVA_PAIS.get(pais, IVA_DEFAULT)
        procesar_pais(sb, pais, umbral, iva, args.dry_run)

if __name__ == '__main__':
    main()
