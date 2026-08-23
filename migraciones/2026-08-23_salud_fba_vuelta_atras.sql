-- ============================================================================
-- VUELTA ATRÁS de 2026-08-23_salud_fba_pasa_a_vista.sql
-- ----------------------------------------------------------------------------
-- Deshace el cambio y deja la base EXACTAMENTE como estaba: `salud_fba` vuelve a
-- ser la TABLA que carga Amazon, y las cuatro vistas vuelven a leerla.
--
-- 🔬 PROBADO el 23-ago-2026 sobre un Postgres 16 con la estructura real: tras
--    aplicarlo, `v_salud_asin` vuelve a dar las mismas filas que antes y
--    `salud_fba` vuelve a ser relkind='r'.
--
-- ⚠️ EL `CASCADE` NO ES OPCIONAL y hay que saber lo que hace: sin él, el DROP
--    falla porque cuatro vistas dependen de `salud_fba`; con él, esas cuatro
--    vistas SE BORRAN. Por eso se recrean aquí abajo, en la misma transacción.
--    (El plan de vuelta atrás original decía sólo `DROP VIEW public.salud_fba` y
--    no funcionaba. Se descubrió ejecutándolo, no leyéndolo.)
--
-- ⚠️ Si el procesador de Amazon ya se apuntó a `salud_fba_amazon`, hay que
--    devolverlo también a `salud_fba` o dejará de cargar. Aborta bien si se
--    olvida (comprueba RLS antes de escribir), pero no carga.
-- ============================================================================

SET lock_timeout = '5s';

DO $$
BEGIN
    IF to_regclass('public.salud_fba_amazon') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba_amazon` no existe. O la migración no se aplicó, o ya se deshizo.';
    END IF;
END $$;

DROP VIEW public.salud_fba CASCADE;   -- se lleva por delante las cuatro vistas
ALTER TABLE public.salud_fba_amazon RENAME TO salud_fba;

CREATE OR REPLACE VIEW public.v_salud_asin AS
 SELECT asin, marketplace,
    count(*) AS n_skus,
    string_agg(sku, ' + '::text ORDER BY sku) AS skus,
    max(product_name) AS product_name,
    sum(COALESCE(available, 0) + COALESCE(fc_transfer, 0)) AS disponible,
    sum(COALESCE(available, 0)) AS available,
    sum(COALESCE(fc_transfer, 0)) AS fc_transfer,
    sum(COALESCE(total_reserved_quantity, 0)) AS reservado,
    sum(COALESCE(inbound_quantity, 0)) AS entrante,
    sum(COALESCE(unfulfillable_quantity, 0)) AS no_vendible,
    sum(COALESCE(pending_removal_quantity, 0)) AS pendiente_retirada,
    sum(COALESCE(inventory_supply_at_fba, 0)) AS stock_fba_total,
    sum(units_shipped_t7) AS t7,
    sum(units_shipped_t30) AS t30,
    sum(units_shipped_t60) AS t60,
    sum(units_shipped_t90) AS t90,
    CASE WHEN COALESCE(sum(units_shipped_t7), 0::bigint) > 0
         THEN round(sum(COALESCE(available, 0) + COALESCE(fc_transfer, 0))::numeric
                    / (sum(units_shipped_t7)::numeric / 7::numeric), 1)
         ELSE NULL::numeric END AS cobertura_dias_t7,
    min(your_price) AS your_price_min,
    max(your_price) AS your_price_max,
    count(*) > 1 AND min(your_price) IS DISTINCT FROM max(your_price) AS precios_desalineados,
    max(featuredoffer_price) AS featuredoffer_price,
    max(lowest_price_new_plus_shipping) AS lowest_price_new_plus_shipping,
    min(sales_rank) AS sales_rank,
    string_agg(DISTINCT NULLIF(alert, ''::text), ' | '::text) AS alertas,
    string_agg(DISTINCT NULLIF(recommended_action, ''::text), ' | '::text) AS acciones_recomendadas,
    string_agg(DISTINCT NULLIF(fba_inventory_level_health_status, ''::text), ' | '::text) AS salud_nivel,
    max(snapshot_date) AS snapshot_date
   FROM public.salud_fba s
  GROUP BY asin, marketplace;

CREATE OR REPLACE VIEW public.v_salud_fba_cruce AS
 SELECT asin, marketplace, sku, product_name, available,
    (SELECT count(*) FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin)) AS fichas_activas,
    NOT (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin))) AS sin_ficha,
    (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin)))
      AND NOT (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin) AND btrim(p.sku) = btrim(s.sku))) AS sku_discrepante,
    (SELECT count(*) FROM public.salud_fba s2 WHERE btrim(s2.asin) = btrim(s.asin) AND s2.marketplace = s.marketplace) AS n_skus_vivos,
    NOT (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin) AND btrim(p.sku) = btrim(s.sku))) AS sku_sin_ficha,
    (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(s.asin)))
      AND NOT (EXISTS (SELECT 1 FROM public.salud_fba s2 JOIN productos p ON p.activo AND btrim(p.asin) = btrim(s2.asin) AND btrim(p.sku) = btrim(s2.sku)
                       WHERE btrim(s2.asin) = btrim(s.asin) AND s2.marketplace = s.marketplace)) AS asin_sin_ningun_sku_fichado
   FROM public.salud_fba s;


-- v_keepa_cruce: sólo usa `salud_fba` en `buybox_ajena_con_stock`. Transcrita
-- literal de pg_get_viewdef() del 23-ago; lo único que cambia es a qué objeto
-- se resuelve el nombre. ⚠️ Su `EXISTS ... WHERE upper(s.marketplace) =
-- upper(k.dominio)` sigue dando NULL para it/fr/de, igual que hoy: la foto sólo
-- se etiqueta ES. No empeora nada, pero queda dicho.
CREATE OR REPLACE VIEW public.v_keepa_cruce AS
 SELECT 'escaparate'::text AS origen, k.asin, k.dominio, k.titulo, k.tarifa_fba,
    k.bb_vendedor, k.bb_seller_id,
    (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND moloka_ean_norm(p.ean) IS NOT NULL))
      AND NOT (EXISTS (SELECT 1 FROM productos p
                       WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
                         AND (moloka_ean_norm(p.ean) IN (SELECT moloka_ean_norm(e.e) FROM unnest(string_to_array(COALESCE(k.ean_keepa_crudo, ''::text), ','::text)) e(e)
                                                          WHERE moloka_ean_norm(e.e) IS NOT NULL)))) AS ean_no_confirmado,
    CASE WHEN k.dominio = ANY (ARRAY['es'::text, 'fr'::text, 'it'::text])
         THEN (EXISTS (SELECT 1 FROM productos p
                       WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND k.tarifa_fba IS NOT NULL
                         AND CASE k.dominio WHEN 'es'::text THEN p.keepa_fba_fee_es
                                            WHEN 'it'::text THEN p.keepa_fba_fee_it
                                            WHEN 'fr'::text THEN p.keepa_fba_fee_fr
                                            ELSE NULL::numeric END IS NOT NULL
                         AND abs(CASE k.dominio WHEN 'es'::text THEN p.keepa_fba_fee_es
                                                WHEN 'it'::text THEN p.keepa_fba_fee_it
                                                WHEN 'fr'::text THEN p.keepa_fba_fee_fr
                                                ELSE NULL::numeric END - k.tarifa_fba) > 0.01))
         ELSE NULL::boolean END AS tarifa_discrepante,
    (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND COALESCE(btrim(p.keepa_image), ''::text) = ''::text))
      AND COALESCE(array_length(k.imagenes, 1), 0) > 0 AS sin_foto_curable,
    CASE WHEN (EXISTS (SELECT 1 FROM public.salud_fba s WHERE upper(s.marketplace) = upper(k.dominio)))
         THEN (EXISTS (SELECT 1 FROM public.salud_fba s
                       WHERE btrim(s.asin) = btrim(k.asin) AND upper(s.marketplace) = upper(k.dominio)
                         AND COALESCE(s.available, 0) > 0))
              AND k.bb_seller_id IS NOT NULL AND k.bb_seller_id <> 'A2R25VOCZPEH8K'::text
         ELSE NULL::boolean END AS buybox_ajena_con_stock,
    NULL::boolean AS pedido_sin_respuesta
   FROM keepa_escaparate k
UNION ALL
 SELECT 'pedido_sin_respuesta'::text AS origen, l.asin, NULL::text AS dominio, l.item_name AS titulo,
    NULL::numeric AS tarifa_fba, NULL::text AS bb_vendedor, NULL::text AS bb_seller_id,
    NULL::boolean AS ean_no_confirmado, NULL::boolean AS tarifa_discrepante,
    NULL::boolean AS sin_foto_curable, NULL::boolean AS buybox_ajena_con_stock,
    true AS pedido_sin_respuesta
   FROM (SELECT btrim(listings_amazon.asin) AS asin, max(listings_amazon.item_name) AS item_name
           FROM listings_amazon
          WHERE listings_amazon.status = 'Active'::text AND listings_amazon.asin IS NOT NULL
            AND btrim(listings_amazon.asin) <> ''::text
          GROUP BY (btrim(listings_amazon.asin))) l
  WHERE (EXISTS (SELECT 1 FROM productos p WHERE p.activo AND NOT COALESCE(p.es_chase, false) AND upper(btrim(p.asin)) = upper(l.asin)))
    AND NOT (EXISTS (SELECT 1 FROM keepa_escaparate k WHERE upper(btrim(k.asin)) = upper(l.asin)));

CREATE OR REPLACE VIEW public.v_incidencias_ultima AS
 WITH ult AS (SELECT max(fecha_lectura) AS f FROM incidencias_lecturas),
 prod AS (
   SELECT DISTINCT ON (productos.sku) productos.sku, productos.pvd, productos.nombre
     FROM productos WHERE productos.sku IS NOT NULL
    ORDER BY productos.sku, (productos.activo IS TRUE) DESC, productos.id DESC),
 ven AS (
   SELECT t.sku, sum(t.cantidad) AS uds_2026,
          round(sum(t.ventas_producto + t.impuesto_producto), 2) AS fact_2026,
          max(t.fecha) AS ultima_venta
     FROM transacciones_movimientos t
    WHERE t.fecha >= '2026-01-01'::date AND t.tipo_norm = 'pedido'::text
      AND t.cantidad > 0 AND t.ventas_producto > 0::numeric
    GROUP BY t.sku)
 SELECT i.fecha_lectura, i.estado, i.sku, i.asin,
    COALESCE(p.nombre, i.producto) AS producto,
    i.fecha_aviso, i.fecha_limite, i.ventas_riesgo, i.sin_ventas_12m, i.n_filas_panel,
    v.uds_2026, v.fact_2026, v.ultima_venta,
    s.available AS stock_fba, s.your_price
   FROM incidencias_juguetes i
     JOIN ult ON i.fecha_lectura = ult.f
     LEFT JOIN prod p ON p.sku = i.sku
     LEFT JOIN ven v ON v.sku = i.sku
     LEFT JOIN public.salud_fba s ON s.sku = i.sku AND s.marketplace = 'ES'::text
  ORDER BY i.estado, i.ventas_riesgo DESC NULLS LAST;

-- ---------------------------------------------------------------------------

DO $$
DECLARE k char; n int;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid='public.salud_fba'::regclass;
    IF k <> 'r' THEN RAISE EXCEPTION 'ABORTA: salud_fba no ha vuelto a ser una tabla (relkind=%).', k; END IF;
    SELECT count(*) INTO n FROM public.v_salud_asin;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: v_salud_asin a 0 filas tras la vuelta atrás.'; END IF;
    RAISE NOTICE 'Vuelta atrás OK: salud_fba es TABLA otra vez, v_salud_asin % filas.', n;
END $$;
