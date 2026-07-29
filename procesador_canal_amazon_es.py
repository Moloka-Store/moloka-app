# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR CANAL amazon_es — mete España en canales_producto (Fase 0, PR-C)
# ----------------------------------------------------------------------------
# Qué hace:
#   Calcula, por SKU y desde transacciones_movimientos (país ES), la comisión y
#   la logística REALES por producto —mediana de las últimas 10 ventas— y las
#   UPSERTA en canales_producto con canal='amazon_es'. Es exactamente lo que la
#   v1 hace para amazon_it/amazon_fr (moloka_actualizar_nube.py:2183-2314), pero
#   para España, que hasta hoy se calculaba y se perdía en app_datos.rentabilidad.
#
# 🔒 NO TOCA ni una fila de amazon_it, amazon_fr ni miravia: solo canal='amazon_es'.
# 🔒 SIN valores inventados: sin ventas → comisión NULL y envío NULL (como el
#    código de Amazon, líneas 735/2250). El 13 % y el 3,10 son de MIRAVIA y aquí
#    no pintan nada.
#
# LA FÓRMULA (idéntica ES/IT/FR, líneas 723 y 2230-2255), por venta con cantidad>0
# y ventas>0 (filtro numérico, robusto al idioma):
#     precio_ud = (ventas + impuesto) / cantidad            (con IVA)
#     fba_ud    = -tarifa_fba / 1,21 / cantidad             (NULL si tarifa_fba=0)
#     com_pct   = (-tarifa_venta / 1,21) / (ventas+impuesto) * 100   (NULL si no aplica)
#   y por SKU: mediana de las ÚLTIMAS 10 no nulas (NULL si no hay), precio = última
#   venta, iva_pct = 21. Solo SKUs con ficha en productos (huérfanos se listan, no
#   se escriben). Dedup de productos por sku: la ficha que tiene el sku, activo solo
#   de desempate.
#
# DOS GUARDAS QUE GRITAN EN EL RESUMEN (no abortan):
#   A) 2+ fichas ACTIVAS con el mismo sku → el pvd se desempataría a cara o cruz
#      (medido: en 8/10 de las dos-vidas el pvd difiere hasta 11 €). Hoy: 0.
#   B) fila con cantidad>0 AND ventas>0 cuyo tipo NO es 'Pedido' → el filtro
#      numérico y el literal dejarían de coincidir (Amazon cambió algo, o entró un
#      país nuevo). Hoy: 0. Quiero enterarme por el dato, no por un descuadre.
#
# ⚠️ amazon_es NO se actualiza solo: se lanza tras cada carga de transacciones. El
#    cargador (procesador_transacciones.py) avisa en su resumen de que quedó
#    desfasado. (Encadenarlo con workflow_run para que salga solo: otro encargo.)
#
# Escalera: staging ensayo → staging aplicar → SQL → producción ensayo → aplicar → SQL.
# ============================================================================

import os, sys
import psycopg2
from psycopg2.extras import execute_values

DB_URL  = os.environ.get('DB_URL', '')
MODO    = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

CANAL = 'amazon_es'
# Literal de PEDIDO conocido para ES (Guarda B). Si el filtro numérico casa filas
# con OTRO tipo, se grita: hoy son cero.
PEDIDO_ES = 'Pedido'

# ---------------------------------------------------------------------------
# La vista que calcula las filas de amazon_es (self-sufficient: se crea aquí).
# security_invoker: respeta el RLS del que consulta.
# ---------------------------------------------------------------------------
# La definición de v_canal_amazon_es se movió a migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql (es una migración, no arranque).
# El procesador ya no la ejecuta; solo la consulta.

# Columnas que se escriben (las mismas que la v1 pone para IT/FR).
COLS = ['canal', 'item_id_canal', 'producto_id', 'ean',
        'precio_venta', 'comision_pct', 'iva_pct', 'envio', 'activo']


def main():
    print("=== PROCESADOR CANAL amazon_es (comisión y logística reales de España) ===", flush=True)
    print(f"MODO: {MODO}  ·  ENTORNO: {ENTORNO}", flush=True)
    print("=" * 60, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not DB_URL:
        sys.exit("Falta DB_URL. Revisa los secrets del workflow.")

    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # ¿Hay transacciones de ES? Sin ellas, no hay nada que calcular.
    cur.execute("SELECT count(*) FROM transacciones_movimientos WHERE pais='ES';")
    if cur.fetchone()[0] == 0:
        print("No hay transacciones de ES en transacciones_movimientos. "
              "Carga el Custom Transaction de ES primero (procesar-transacciones). "
              "Nada que escribir.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(0)

    # Crear/actualizar la vista.
    # La vista v_canal_amazon_es YA NO se recrea aquí (recrearla en cada carga pedía lock
    # exclusivo sobre media base y tumbó la app el 28-jul 15:47). Su definición vive en
    # migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql. Solo se comprueba que existe.
    cur.execute("SELECT to_regclass('public.v_canal_amazon_es');")
    if cur.fetchone()[0] is None:
        sys.exit("La vista v_canal_amazon_es no existe. Ya NO la crea el procesador (era un lock "
                 "que tumbaba la base). Aplica migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql y relanza.")

    # --- Guarda A: 2+ fichas ACTIVAS con el mismo sku ---
    cur.execute("""
        SELECT sku, count(*) FROM productos
        WHERE sku IS NOT NULL AND activo IS TRUE
        GROUP BY sku HAVING count(*) > 1 ORDER BY sku;""")
    dos_activas = cur.fetchall()
    if dos_activas:
        print("\n🔴 [Guarda A] SKU con 2+ fichas ACTIVAS: el pvd se elige a cara o cruz "
              "(en las dos-vidas el pvd difiere hasta 11 €). REVISAR — se sigue, pero avisa:",
              flush=True)
        for sku, n in dos_activas:
            print(f"        · {sku}: {n} fichas activas", flush=True)

    # --- Guarda B: filtro numérico casa filas con tipo != 'Pedido' ---
    cur.execute("""
        SELECT tipo, count(*) FROM transacciones_movimientos
        WHERE pais='ES' AND cantidad > 0 AND ventas_producto > 0
          AND tipo IS DISTINCT FROM %s
        GROUP BY tipo ORDER BY count(*) DESC;""", (PEDIDO_ES,))
    tipos_raros = cur.fetchall()
    if tipos_raros:
        print(f"\n⚠️  [Guarda B] Filas con cantidad>0 AND ventas>0 cuyo tipo NO es "
              f"{PEDIDO_ES!r} (el filtro numérico y el literal han dejado de coincidir; "
              f"se cuentan igual, pero avisa):", flush=True)
        for tipo, n in tipos_raros:
            print(f"        · {tipo!r}: {n} fila(s)", flush=True)

    # --- Huérfanos: SKUs con venta en ES SIN ficha en productos (se listan, no se escriben) ---
    cur.execute("""
        SELECT t.sku, sum(t.cantidad) uds, round(sum(t.ventas_producto), 2) eur
        FROM transacciones_movimientos t
        WHERE t.pais='ES' AND t.cantidad > 0 AND t.ventas_producto > 0
          AND t.sku IS NOT NULL AND t.sku <> ''
          AND NOT EXISTS (SELECT 1 FROM productos p WHERE p.sku = t.sku)
        GROUP BY t.sku ORDER BY eur DESC;""")
    huerfanos = cur.fetchall()
    if huerfanos:
        tot_uds = sum(h[1] for h in huerfanos)
        tot_eur = sum(h[2] for h in huerfanos)
        print(f"\n⚠️  SKUs con ventas en ES pero SIN ficha en productos "
              f"({len(huerfanos)} SKU · {tot_uds} uds · {tot_eur} €) — NO se escriben:", flush=True)
        for sku, uds, eur in huerfanos:
            print(f"        · {sku}: {uds} uds · {eur} €", flush=True)

    # --- Cuántas filas trae la vista y cuántas amazon_es había ya ---
    cur.execute("SELECT count(*) FROM v_canal_amazon_es;")
    filas_vista = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM canales_producto WHERE canal = %s;", (CANAL,))
    previas = cur.fetchone()[0]

    # --- UPSERT amazon_es (solo este canal; NO toca it/fr/miravia) ---
    cur.execute(f"""
        INSERT INTO canales_producto ({', '.join(COLS)})
        SELECT {', '.join(COLS)} FROM v_canal_amazon_es
        ON CONFLICT (canal, item_id_canal) DO UPDATE SET
            producto_id  = EXCLUDED.producto_id,
            ean          = EXCLUDED.ean,
            precio_venta = EXCLUDED.precio_venta,
            comision_pct = EXCLUDED.comision_pct,
            iva_pct      = EXCLUDED.iva_pct,
            envio        = EXCLUDED.envio,
            activo       = EXCLUDED.activo,
            updated_at   = now();""")
    afectadas = cur.rowcount

    cur.execute("SELECT count(*) FROM canales_producto WHERE canal = %s;", (CANAL,))
    despues = cur.fetchone()[0]
    altas = despues - previas
    actualizadas = filas_vista - altas

    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- CANAL amazon_es ---")
    print(f"   · filas que calcula la vista:      {filas_vista}")
    print(f"   · amazon_es que había antes:       {previas}")
    print(f"   · altas ({verbo} insertar):        {altas}")
    print(f"   · actualizaciones:                 {actualizadas}")
    print(f"   · huérfanos (no escritos):         {len(huerfanos)}")

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {filas_vista} filas de amazon_es en "
              f"canales_producto (it/fr/miravia intactos).")
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: NO se ha escrito nada. (El UPSERT se ha probado dentro de una "
              f"transacción revertida; la vista v_canal_amazon_es SÍ queda creada.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · canal=amazon_es · "
          f"filas={filas_vista} · altas={altas} · huerfanos={len(huerfanos)} ===", flush=True)


if __name__ == '__main__':
    main()
