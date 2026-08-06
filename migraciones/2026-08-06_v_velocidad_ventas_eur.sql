-- ============================================================================
-- MIGRACIÓN 2026-08-06 · v_velocidad_ventas — AÑADIR eur_30d_total (ventas €)
-- ----------------------------------------------------------------------------
-- QUÉ Y POR QUÉ. La ficha de Inventario (v2) muestra "Ventas 30 d" en UNIDADES
-- (uds_30d_total) como número principal, y Fernando pidió los EUROS debajo, en
-- gris, para leer "cuánto pesa" cada producto. Esta migración añade UNA columna a
-- la vista, `eur_30d_total`, con las MISMAS filas que las unidades: misma ventana
-- (30 d hasta max(fecha)), mismo `tipo_norm='pedido'`, mismo puente SKU→ASIN. Así
-- unidades y euros NO pueden discrepar (salen de la misma pasada), y la app no
-- paga ni una consulta ni un byte extra: ya lee esta vista.
--
-- 🔴 CON/SIN IVA — LITERAL, PORQUE LO PIDIÓ EL CONTABLE. `eur_30d_total` es la suma
--    de `ventas_producto`, que es la BASE IMPONIBLE (SIN IVA). Medido contra la
--    fórmula validada `v_rentabilidad_transacciones` (3-ago): allí
--    `facturacion_sin_iva = sum(ventas_producto)` y
--    `facturacion_iva      = sum(ventas_producto + impuesto_producto)`.
--    Es decir: el IVA vive en `impuesto_producto`; el CON IVA sería sumar los dos.
--    Aquí se usa `ventas_producto` A PROPÓSITO (base imponible): es la magnitud que
--    entra en el margen. La interfaz lo etiqueta "sin IVA (base imponible)", literal.
--
-- Lo demás de la vista NO cambia: mismas columnas, mismo orden, mismos tipos; solo
-- se AÑADE `eur_30d_total` al final (lo que permite CREATE OR REPLACE VIEW sin DROP).
--
-- 🔒 security_invoker = true (se conserva): respeta el RLS de transacciones y
--    listings. Sin SECURITY DEFINER.
-- 🔒 ACL: CREATE OR REPLACE conserva el ACL, pero se re-afirma el patrón "nace
--    cerrado" (§4) por si en algún momento se recreó con DROP+CREATE: revoke a cada
--    rol por su nombre y grant mínimo. Idempotente. MEDIR el relacl al terminar.
--
-- DESPLIEGUE. CREATE OR REPLACE VIEW = AccessShareLock, no tumba nada. Por la
--   escalera (staging → SQL → prod → SQL), lock_timeout corto en prod. Solo LECTURA.
--   Es aditiva y compatible: la app v2 sigue funcionando ANTES de que lea la columna
--   nueva; el PR de v2 que la LEE se fusiona DESPUÉS de aplicar esto en producción
--   (si la app pidiera eur_30d_total antes de que exista, PostgREST daría error).
-- ============================================================================

create or replace view public.v_velocidad_ventas
with (security_invoker = true) as
with ventana as (
    select (max(fecha) - interval '30 days')::date as desde,
           max(fecha)                              as hasta
    from transacciones_movimientos
),
sku_asin as (   -- puente identidad SKU→ASIN (listings_amazon, fuente dura §1.1)
    select distinct on (btrim(seller_sku))
           btrim(seller_sku) as sku,
           btrim(asin)       as asin
    from listings_amazon
    where seller_sku is not null and asin is not null and btrim(asin) <> ''
    order by btrim(seller_sku), fecha_informe desc
),
ventas as (
    select sa.asin, t.pais, t.cantidad, t.ventas_producto   -- + ventas_producto (base, sin IVA)
    from transacciones_movimientos t
    join ventana  v  on t.fecha > v.desde            -- ventana desde max(fecha)
    join sku_asin sa on sa.sku = btrim(t.sku)
    where t.tipo_norm = 'pedido'                      -- venta; NO reembolsos
)
select
    asin,
    coalesce(sum(cantidad) filter (where pais = 'ES'), 0) as uds_30d_es,
    coalesce(sum(cantidad) filter (where pais = 'IT'), 0) as uds_30d_it,
    coalesce(sum(cantidad) filter (where pais = 'FR'), 0) as uds_30d_fr,
    sum(cantidad)                                         as uds_30d_total,
    round(sum(cantidad)::numeric / 30, 2)                 as vel_dia_total,
    (select desde from ventana)                          as ventana_desde,
    (select hasta from ventana)                          as ventana_hasta,
    (CURRENT_DATE - (select hasta from ventana))         as dias_desde_ultimo_dato,
    -- NUEVA: ventas en € SIN IVA (base imponible) = suma de ventas_producto de los
    -- MISMOS pedidos que cuentan las unidades. round a 2 decimales (importe €).
    round(sum(ventas_producto)::numeric, 2)              as eur_30d_total
from ventas
group by asin;

-- Nace cerrado (§4): revocar los grants por defecto de Supabase a CADA rol por su
-- nombre y luego conceder el mínimo. Idempotente: se re-afirma en cada aplicación.
revoke all on public.v_velocidad_ventas from public, anon, authenticated;
grant select on public.v_velocidad_ventas to authenticated;
