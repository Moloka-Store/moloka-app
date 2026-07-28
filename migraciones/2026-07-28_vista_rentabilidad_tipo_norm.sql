-- ============================================================================
-- Migración TRANSACCIONES — v_rentabilidad_transacciones lee tipo_norm, no literales
-- ----------------------------------------------------------------------------
-- Único cambio respecto a 2026-07-28_vista_rentabilidad_transacciones.sql: el
-- reembolso deja de cablearse a los 3 literales (Reembolso/Rimborso/Remboursement)
-- y pasa a `tipo_norm = 'reembolso'`. Así el día que entre DE su reembolso cuenta
-- sin tocar la vista (y si el literal DE no está en TIPO_CANON, tipo_norm queda NULL
-- y el procesador GRITA — nunca se cae en silencio).
--
-- 🔴 IGUALDAD EXACTA `tipo_norm = 'reembolso'`, NUNCA `LIKE 'reembolso%'`: existe
-- `reembolso_inventario` (Ajuste ES / Modifica IT: indemnizaciones de Amazon por
-- inventario, +374,54 €, con SKU). Un prefijo colaría esas indemnizaciones dentro de
-- los reembolsos de venta y movería los totales. Son familias distintas.
--
-- El pedido se queda NUMÉRICO (cantidad>0 AND ventas>0): ya es a prueba de idioma;
-- el único literal cableado hoy era el reembolso.
--
-- Aplicar DESPUÉS de poblar tipo_norm (recarga de los 3 países). Verificación: los
-- totales por país y los reembolsos idénticos a los medidos antes (ver la otra migración).
-- ============================================================================

CREATE OR REPLACE VIEW v_rentabilidad_transacciones
WITH (security_invoker = true) AS
WITH prod AS (
    SELECT DISTINCT ON (sku) sku, pvd
    FROM productos WHERE sku IS NOT NULL
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
        (t.tipo_norm = 'reembolso') AS es_reembolso   -- 🔴 igualdad EXACTA, nunca LIKE
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
