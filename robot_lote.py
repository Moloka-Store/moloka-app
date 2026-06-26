# ============================================================================
# ROBOT LOTE  -  Modo "a lo bruto" de la Fabrica
# ----------------------------------------------------------------------------
# Reutiliza el MOTOR de robot_preparar.py (Keepa + montaje M7 + redaccion) SIN
# tocarlo. La fabrica "joya" de Elena queda intacta.
# Lee un recado propio (informes/fabrica/_solicitud_lote.json) con muchos EANs
# directos (sacados del Excel del escaner) y genera una ficha 'borrador' por
# cada uno, para revisar en bloque y publicar.
# Resumible: si un EAN ya tiene ficha (corrida cortada o ya hecha a mano), lo salta.
# Mismos Secrets que la fabrica: KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY,
# SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY
# ============================================================================
import json, datetime, sys
import robot_preparar as R   # <-- importa el motor tal cual (no lo modifica)

sys.stdout.reconfigure(line_buffering=True)

RECADO_LOTE = 'fabrica_lote/_solicitud_lote.json'

def main():
    crudo = R._bajar(R.BUCKET_BUZON, RECADO_LOTE)
    if crudo is None:
        print("SIN recado de lote. Nada que hacer."); return
    recado = json.loads(crudo.decode('utf-8'))
    tanda  = recado.get('tanda') or datetime.datetime.now().strftime('%Y%m%d_%H%M')
    items  = recado.get('items') or []
    print(f"Recado LOTE: tanda {tanda}, {len(items)} EAN(s).")

    ok, err, saltados = [], [], []
    for i, it in enumerate(items, 1):
        it['tanda'] = tanda
        ean = str(it.get('ean') or '').strip()
        if not ean:
            continue
        # Resumibilidad + dedup: si ya hay ficha de ese EAN (cualquier estado), saltar.
        try:
            ya = R.sb.table('fabrica_fichas').select('id').eq('ean', ean).limit(1).execute().data
        except Exception:
            ya = None
        if ya:
            print(f"[{i}/{len(items)}] {ean} ya tiene ficha -> salto")
            saltados.append(ean); continue
        print(f"\n[{i}/{len(items)}] (lote) EAN {ean}")
        try:
            if R.preparar_item(ean, it, None):
                ok.append(ean)
            else:
                err.append(ean)
        except Exception as e:
            print(f"   ERROR procesando {ean}: {e}")
            err.append(ean)

    # Borra el recado SOLO al terminar (si se corta antes, al relanzar retoma donde iba).
    try:
        R.sb.storage.from_(R.BUCKET_BUZON).remove([RECADO_LOTE])
    except Exception:
        pass

    print(f"\n==== RESUMEN LOTE {tanda} ====")
    print(f"  Borradores OK: {len(ok)} | saltados (ya existían): {len(saltados)} | errores: {len(err)}")
    if err:
        print(f"  EAN con error: {err}")
    print("Fin.")

if __name__ == '__main__':
    main()
