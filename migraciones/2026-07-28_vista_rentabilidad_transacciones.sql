-- ============================================================================
-- Migración PR-C (1/2) — VISTA de rentabilidad real sobre transacciones_movimientos
-- ----------------------------------------------------------------------------
-- Porta la fórmula VALIDADA de la v1 (moloka_actualizar_nube.py:468-502), NO la
-- reinventa. Por (país, mes):
--   comisión = Σ(−tarifa_venta)/1,21 · logística = Σ(−tarifa_fba)/1,21
--   otras = Σ(−tarifa_otras)/1,21 · almacén = unidades × 0,15 (COSTE_ALMACEN_UD)
--   coste_pvd = Σ(cantidad × pvd)   [pvd de productos, dedup por sku]
--   reembolsos_netos = Σ ventas(Reembolso) + Σ(t_venta+t_fba+t_otras)(Reembolso)/1,21
--   beneficio = facturación_SIN_IVA − (pvd+comisión+logística+otras+almacén) + reembolsos
--   margen % = beneficio / facturación_CON_IVA × 100     🔒 sobre CON IVA (línea 488)
--
-- 🔒 fact_sin_iva y las tarifas son SOLO de PEDIDO. Los reembolsos NO se restan de
--    la facturación: van aparte en reembolsos_netos y se suman al final (si se
--    metieran dentro, el beneficio se desviaría ~859 € en junio buscando un fallo
--    que no existe). Verificado: junio-2026 ES reproduce la v1 al céntimo salvo
--    coste_pvd (0,27 €, que es el pvd de las fichas "dos vidas"; ver la otra vista).
--
-- 🔒 LAS TARIFAS DE INVENTARIO DE AMAZON QUEDAN FUERA DEL CÁLCULO (§0.1 del encargo):
--    el 0,15 €/ud YA lleva almacenamiento estimado dentro; sumar además las
--    'Tarifas de inventario de Logística de Amazon' (726 mov · 1.885,83 € en ES)
--    contaría el almacenamiento DOS VECES. Están guardadas en la tabla (tipo/otro)
--    pero NO entran aquí. No se tocan: se dejan fuera a propósito.
--
-- FILTRO: PEDIDO = cantidad>0 AND ventas>0 (numérico, robusto al idioma; idéntico
--    hoy a tipo='Pedido': 12.382 ES/364 IT/232 FR). REEMBOLSO = literal por país
--    (para el reembolso NO hay señal numérica limpia: un ventas<0 podría ser un
--    Ajuste). Los literales son los medidos el 28-jul.
--
-- Solo cuenta lo que tiene ficha en productos (huérfanos fuera, como la v1).
-- Nace security_invoker (respeta el RLS del que consulta).
-- ============================================================================

CREATE OR REPLACE VIEW v_rentabilidad_transacciones
WITH (security_invoker = true) AS
WITH prod AS (
    -- Una ficha por sku; activo SOLO como desempate (ver la guarda de "2 activas"
    -- en procesador_canal_amazon_es.py: si algún día hay 2 activas con el mismo
    -- sku, desempatar por id elegiría el pvd a cara o cruz — se avisa allí).
    SELECT DISTINCT ON (sku) sku, pvd
    FROM productos
    WHERE sku IS NOT NULL
    ORDER BY sku, (activo IS TRUE) DESC, id DESC
),
mov AS (
    SELECT
        t.pais,
        date_trunc('month', t.fecha)::date AS mes,
        t.cantidad, t.ventas_producto, t.impuesto_producto,
        t.tarifa_venta, t.tarifa_fba, t.tarifa_otras,
        (p.sku IS NOT NULL) AS con_ficha,
        p.pvd,
        (t.cantidad > 0 AND t.ventas_producto > 0) AS es_pedido,
        (t.tipo IN ('Reembolso','Rimborso','Remboursement')) AS es_reembolso
    FROM transacciones_movimientos t
    LEFT JOIN prod p ON p.sku = t.sku
),
agg AS (
    SELECT
        pais, mes,
        round(sum(ventas_producto + impuesto_producto) FILTER (WHERE es_pedido AND con_ficha), 2) AS facturacion_iva,
        round(sum(ventas_producto)                     FILTER (WHERE es_pedido AND con_ficha), 2) AS facturacion_sin_iva,
        sum(cantidad)                                  FILTER (WHERE es_pedido AND con_ficha)     AS unidades,
        round(sum(cantidad * pvd)                      FILTER (WHERE es_pedido AND con_ficha), 2) AS coste_pvd,
        round(sum(-tarifa_venta / 1.21)                FILTER (WHERE es_pedido AND con_ficha), 2) AS comision_amazon,
        round(sum(-tarifa_fba   / 1.21)                FILTER (WHERE es_pedido AND con_ficha), 2) AS logistica_fba,
        round(sum(-tarifa_otras / 1.21)                FILTER (WHERE es_pedido AND con_ficha), 2) AS otras_tarifas,
        round(coalesce(sum(cantidad) FILTER (WHERE es_pedido AND con_ficha), 0) * 0.15, 2)        AS coste_almacen,
        round(
            coalesce(sum(ventas_producto) FILTER (WHERE es_reembolso), 0)
          + coalesce(sum((tarifa_venta + tarifa_fba + tarifa_otras) / 1.21) FILTER (WHERE es_reembolso), 0)
        , 2) AS reembolsos_netos
    FROM mov
    GROUP BY pais, mes
),
benef AS (
    SELECT *,
        round(facturacion_sin_iva
              - (coalesce(coste_pvd,0) + coalesce(comision_amazon,0) + coalesce(logistica_fba,0)
                 + coalesce(otras_tarifas,0) + coalesce(coste_almacen,0))
              + coalesce(reembolsos_netos,0), 2) AS beneficio
    FROM agg
)
SELECT *,
    CASE WHEN facturacion_iva > 0
         THEN round(beneficio / facturacion_iva * 100, 1) END AS margen_pct
FROM benef;
