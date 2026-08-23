-- ============================================================================
-- MIGRACIÓN 2026-08-23 · `salud_fba` DEJA DE SER UNA TABLA Y PASA A SER UNA VISTA
-- ----------------------------------------------------------------------------
-- ES LA MIGRACIÓN QUE CURA LA APP. Las dos anteriores (inventario_fba y
-- v_ventas_ventanas) eran aditivas y no tocaban nada; ésta sí. Léela entera.
--
-- POR QUÉ. Amazon sirve roto el informe «Estado del inventario FBA» desde el
-- 16-ago-2026. Las guardas lo bloquean —bien— y por eso `salud_fba` lleva
-- congelada en esa fecha mientras el resto de producción va al 20-23. Medido el
-- 23-ago contra producción:
--   · de 212 referencias que vendieron algo en 30 días, la app ve ventas en 39;
--   · 174 referencias que venden salen como PARADAS, y una referencia que la app
--     cree parada no se repone nunca;
--   · 88 referencias por debajo de 25 días de cobertura, 66 por debajo de 7,
--     12 ya a cero vendiendo;
--   · el stock desviado son 393 uds de más y 175 de menos sobre 218 ASIN.
--
-- QUÉ HACE. La tabla se renombra a `salud_fba_amazon` (sigue ahí, intacta, y el
-- procesador de Amazon seguirá cargándola cuando se recupere) y en su lugar
-- queda una VISTA con las MISMAS 58 columnas, alimentada por fuentes vivas.
-- Ni la app ni las RPC cambian una línea: no saben si leen una tabla o una vista.
--
-- 🔒 LA REGLA DE DISEÑO, Y NO SE NEGOCIA:
--        LO QUE NO TENGA FUENTE VIVA VA A NULL. NO SE ARRASTRA NI UN VALOR DEL 16.
--    Parece severo y es lo contrario: es lo que impide seguir mintiendo. Y
--    resuelve dos problemas de golpe:
--      · el semáforo `frescuraDot` (umbral 2 días) mira `snapshot_date`. Aquí
--        pasa a ser la fecha real de `inventario_fba`, y detrás NO queda ni un
--        dato viejo avalado por él. El semáforo dice la verdad sin tocar la app.
--      · la rotación por antigüedad de Rentabilidad lee ocho claves `inv-age-*`
--        del `crudo`. 🔬 MEDIDO: el informe nuevo tiene 26 columnas y NINGUNA es
--        `inv-age-*`. No hay fuente. `crudo` va a NULL y el código de la app ya
--        sabe apagarse y escribir su motivo.
--
-- 🔴 LO QUE CASI SE ESCAPA, Y ES LO MÁS IMPORTANTE DE ESTE FICHERO:
--    en Postgres un `ALTER TABLE ... RENAME` **NO rompe las vistas que la leen**.
--    Las vistas guardan el OID, no el nombre: seguirían leyendo la tabla
--    renombrada —la foto CONGELADA— en silencio y para siempre. Por eso las
--    cuatro vistas que leen `salud_fba` se RECREAN aquí, en la misma
--    transacción. (`v_nunca_enviado_fba` no entra: lee `salud_fba_historico`.)
--
-- 🔬 DE DÓNDE SALE CADA COSA (todo medido el 23-ago):
--   · stock e identidad ← `inventario_fba`. Es el mismo universo que medía
--     salud_fba: `available + fc_transfer` de salud casaba con el TOTAL EUROPEO
--     del internacional (104 exactos y 170 dentro de ±2 sobre 206 asin) mucho
--     mejor que con ES solo (87 y 131). Y es un universo MAYOR: 354 sku frente a
--     los 225 del internacional, porque sí lista las referencias A CERO — que son
--     justo las que hay que reponer.
--   · ventas t7/t30/t60/t90 ← `v_ventas_ventanas` (ledger + transacciones).
--   · `sales_rank` ← Keepa dominio 'es', que está más fresco que Amazon.
--   · `inbound_quantity` = working + shipped + receiving, y
--     `inventory_supply_at_fba` = available + fc_transfer + inbound: las dos son
--     las ecuaciones del propio informe, medidas al 100 % en 710 filas, no
--     interpretaciones (§3.8: `fc_transfer` va dentro del almacén y fuera de
--     fulfillable; `inventory_supply_at_fba` no lleva reserved).
--
-- ⚠️ `marketplace` se emite como el literal 'ES'. NO es decorativo:
--    `v_incidencias_ultima` hace `LEFT JOIN salud_fba s ON ... AND s.marketplace
--    = 'ES'`. Sin esa columna con ese valor, esa vista se queda A CERO FILAS SIN
--    DAR ERROR. (`inventario_fba` no tiene columna de marketplace porque el
--    informe es europeo, igual que lo era el dato de salud pese a la etiqueta.)
--
-- 🔒 VUELTA ATRÁS: aplicar `2026-08-23_salud_fba_vuelta_atras.sql`, en el mismo
--    workflow y en menos de un minuto. Deja la base EXACTAMENTE como estaba.
--    ⚠️ Ese fichero lleva `DROP VIEW ... CASCADE` y recrea las cuatro vistas, y
--    no es opcional: sin CASCADE el DROP falla, y con CASCADE las cuatro vistas
--    caen con él. Lo sé porque lo ejecuté: el plan de vuelta atrás que había
--    escrito aquí (un DROP a secas) NO funcionaba.
--
-- 🔒 ANTES DE APLICAR: avisar a Elena. Durante la transacción, la pestaña de
--    Inventario puede parpadear.
-- 🔒 DESPUÉS: el PR que apunta `procesador_salud_fba.py` a `salud_fba_amazon`.
--    Si se olvida, falla BIEN: aborta en su comprobación de RLS (una vista la
--    tiene a `false`) antes de escribir nada.
-- ============================================================================

SET lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 0) GUARDAS PREVIAS. Si algo no está, se aborta ANTES de renombrar nada.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_inv int; f_inv date; n_ven int; transito int;
BEGIN
    IF to_regclass('public.inventario_fba') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: `inventario_fba` no existe. Aplica antes su migración y CARGA el informe. Sin dato fresco, esta vista deja la app peor que ahora.';
    END IF;
    IF to_regclass('public.v_ventas_ventanas') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: `v_ventas_ventanas` no existe. Aplica antes 2026-08-23_v_ventas_ventanas.sql.';
    END IF;
    IF to_regclass('public.salud_fba_amazon') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba_amazon` YA existe. Esta migración ya se aplicó, o hay una vuelta atrás a medias. Míralo antes de seguir.';
    END IF;

    SELECT count(*), max(fecha_foto), coalesce(sum(inbound_shipped),0)
      INTO n_inv, f_inv, transito FROM public.inventario_fba;
    IF n_inv < 100 THEN
        RAISE EXCEPTION 'ABORTA: `inventario_fba` tiene % filas. Esperaba del orden de 350. Carga el informe primero.', n_inv;
    END IF;
    IF f_inv < CURRENT_DATE - 3 THEN
        RAISE EXCEPTION 'ABORTA: la foto de `inventario_fba` es del % — ya nace vieja. Carga el informe de hoy.', f_inv;
    END IF;

    SELECT count(*) INTO n_ven FROM public.v_ventas_ventanas WHERE uds_30d > 0;
    IF n_ven < 100 THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas sólo ve % referencias con venta en 30 días. Esperaba ~211. Si entra así, la app repetiría el error que venimos a arreglar.', n_ven;
    END IF;

    RAISE NOTICE 'Guardas previas OK: inventario_fba % filas (foto %, % uds en tránsito) · % referencias con venta 30d',
                 n_inv, f_inv, transito, n_ven;
END $$;

-- ---------------------------------------------------------------------------
-- 1) La tabla se aparta. No se borra: es el archivo de lo que dijo Amazon.
-- ---------------------------------------------------------------------------
ALTER TABLE public.salud_fba RENAME TO salud_fba_amazon;

COMMENT ON TABLE public.salud_fba_amazon IS
  'Lo que dijo AMAZON en el informe "Estado del inventario FBA", tal cual llego. Era `salud_fba` '
  'hasta el 23-ago-2026, cuando ese nombre paso a ser una VISTA alimentada por fuentes vivas '
  'porque Amazon lleva sirviendo el informe roto desde el 16-ago. La sigue cargando '
  'procesador_salud_fba.py y aqui es donde hay que mirar el dia que Amazon lo arregle: si esta '
  'tabla vuelve a traer ventas en la mayoria de sus filas, se puede reconsiderar la vista.';

-- ---------------------------------------------------------------------------
-- 2) LA VISTA. Mismas 58 columnas, mismos nombres, mismos tipos.
--    Los ::integer / ::text no son adorno: si un tipo baila, el CREATE OR
--    REPLACE de las cuatro vistas de abajo falla (y menos mal).
-- ---------------------------------------------------------------------------
CREATE VIEW public.salud_fba
WITH (security_invoker = true) AS
SELECT
    -- Identidad ------------------------------------------------------------
    i.sku,
    i.fnsku,
    i.asin,
    i.product_name,
    i.condition,
    'ES'::text                                    AS marketplace,   -- ⚠️ v_incidencias_ultima
    -- Stock: fuente viva ---------------------------------------------------
    i.available,
    i.fc_transfer,
    i.total_reserved_quantity,
    NULL::integer                                 AS reserved_fc_processing,
    NULL::integer                                 AS reserved_customer_order,
    NULL::integer                                 AS reserved_staging,
    (coalesce(i.inbound_working,0) + coalesce(i.inbound_shipped,0)
        + coalesce(i.inbound_receiving,0))::integer AS inbound_quantity,
    i.inbound_working,
    i.inbound_shipped,
    i.inbound_receiving                           AS inbound_received,
    i.unfulfillable_quantity,
    NULL::integer                                 AS pending_removal_quantity,  -- valía 0 en las 219 y no la lee nadie
    (coalesce(i.available,0) + coalesce(i.fc_transfer,0) + coalesce(i.inbound_working,0)
        + coalesce(i.inbound_shipped,0) + coalesce(i.inbound_receiving,0))::integer
                                                  AS inventory_supply_at_fba,   -- §3.8: sin reserved
    -- Cobertura: la calcula quien la necesite, aquí NO se inventa -----------
    NULL::numeric                                 AS days_of_supply,
    NULL::numeric                                 AS total_days_of_supply_incl_open_shipments,
    NULL::numeric                                 AS weeks_of_cover_t30,
    NULL::numeric                                 AS weeks_of_cover_t90,
    NULL::numeric                                 AS sell_through,
    -- Ventas: fuente viva (ledger + transacciones) -------------------------
    coalesce(v.uds_7d , 0)::integer               AS units_shipped_t7,
    coalesce(v.uds_30d, 0)::integer               AS units_shipped_t30,
    coalesce(v.uds_60d, 0)::integer               AS units_shipped_t60,
    coalesce(v.uds_90d, 0)::integer               AS units_shipped_t90,
    NULL::numeric                                 AS historical_days_of_supply,
    -- La "segunda opinión" de Amazon: sin fuente ---------------------------
    NULL::text                                    AS recommended_action,
    NULL::integer                                 AS recommended_ship_in_quantity,
    NULL::text                                    AS recommended_ship_in_date,
    NULL::numeric                                 AS healthy_inventory_level,
    NULL::text                                    AS alert,
    NULL::integer                                 AS estimated_excess_quantity,
    NULL::integer                                 AS recommended_removal_quantity,
    NULL::numeric                                 AS estimated_cost_savings_of_recommended_actions, -- era MARKETING
    NULL::integer                                 AS fba_minimum_inventory_level,
    NULL::text                                    AS fba_inventory_level_health_status,
    NULL::text                                    AS low_inventory_fee_applied_current_week,
    NULL::text                                    AS exempted_from_low_inventory_fee,
    NULL::numeric                                 AS estimated_storage_cost_next_month,
    NULL::text                                    AS storage_type,
    NULL::numeric                                 AS storage_volume,
    NULL::numeric                                 AS item_volume,
    NULL::text                                    AS inventory_age_snapshot_date,
    -- Competencia y precio -------------------------------------------------
    NULL::numeric                                 AS featuredoffer_price,
    NULL::numeric                                 AS lowest_price_new_plus_shipping,
    i.your_price,
    NULL::numeric                                 AS sales_price,
    k.rank::integer                               AS sales_rank,      -- Keepa ES, más fresco que Amazon
    -- Estacionalidad: sin fuente -------------------------------------------
    NULL::text                                    AS is_seasonal_in_next_3_months,
    NULL::text                                    AS season_name,
    NULL::text                                    AS season_start_date,
    NULL::text                                    AS season_end_date,
    -- Trazabilidad ---------------------------------------------------------
    i.fecha_foto                                  AS snapshot_date,
    i.fichero,
    NULL::jsonb                                   AS crudo,           -- 🔴 sin inv-age-*: no existen en el informe nuevo
    i.procesado_at                                AS procesado_en
FROM public.inventario_fba i
LEFT JOIN public.v_ventas_ventanas v
       ON btrim(v.asin) = btrim(i.asin)
LEFT JOIN LATERAL (
    SELECT ke.rank FROM public.keepa_escaparate ke
    WHERE btrim(ke.asin) = btrim(i.asin) AND lower(ke.dominio) = 'es'
    ORDER BY ke.fecha_foto DESC LIMIT 1
) k ON true;

COMMENT ON VIEW public.salud_fba IS
  'VISTA desde el 23-ago-2026. Era una tabla; lo que dijo Amazon vive ahora en `salud_fba_amazon`. '
  'Mantiene las 58 columnas y sus tipos para que la app y las RPC no cambien una linea. '
  'Stock e identidad: inventario_fba. Ventas t7/t30/t60/t90: v_ventas_ventanas (ledger + '
  'transacciones). sales_rank: Keepa dominio es. TODO LO DEMAS ES NULL A PROPOSITO: lo que no '
  'tiene fuente viva no se arrastra del 16-ago. marketplace se emite como literal ES porque '
  'v_incidencias_ultima cruza por esa columna y sin ella se quedaria a cero filas en silencio.';

-- ---------------------------------------------------------------------------
-- 3) 🔴 RECREAR LAS CUATRO VISTAS. Sin esto seguirían leyendo, por OID, la
--    tabla renombrada — es decir, la foto congelada — sin dar un solo error.
--    Se recrean con su definición EXACTA de hoy (transcrita de pg_get_viewdef()
--    el 23-ago): lo único que cambia es a qué objeto se resuelve el nombre.
-- ---------------------------------------------------------------------------
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
-- 4) PERMISOS. La vista es `security_invoker`: no da más de lo que ya tiene
--    quien pregunta. Para que la app (rol `authenticated`) la lea hacen falta
--    las dos cosas — el GRANT sobre la vista y la política sobre la tabla base.
--    `anon` no entra en ninguna de las dos.
-- ---------------------------------------------------------------------------
GRANT SELECT ON public.salud_fba TO authenticated;
REVOKE ALL ON public.salud_fba FROM PUBLIC, anon;

DROP POLICY IF EXISTS inventario_read_authenticated ON public.inventario_fba;
CREATE POLICY inventario_read_authenticated ON public.inventario_fba
    FOR SELECT TO authenticated USING (true);
GRANT SELECT ON public.inventario_fba TO authenticated;
REVOKE ALL ON public.inventario_fba FROM PUBLIC, anon;

-- `salud_fba_amazon` conserva su política de lectura del rename. No se toca.

-- ---------------------------------------------------------------------------
-- 5) TESTIGOS. Si algo sale a cero, se aborta y la transacción deja la base
--    EXACTAMENTE como estaba. Es el punto de todo esto: fallar en alto.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n int; n_ventas int; n_asin int; n_cruce int; n_inc int; n_keepa int; f date; disp bigint; trans bigint;
BEGIN
    SELECT count(*), max(snapshot_date),
           coalesce(sum(available + fc_transfer),0), coalesce(sum(inbound_shipped),0)
      INTO n, f, disp, trans FROM public.salud_fba;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: la vista salud_fba devuelve 0 filas.'; END IF;

    SELECT count(*) INTO n_ventas FROM public.salud_fba WHERE units_shipped_t30 > 0;
    IF n_ventas < 100 THEN
        RAISE EXCEPTION 'ABORTA: sólo % filas con units_shipped_t30 > 0. Antes de esto eran 39 y el objetivo es ~200. Si entra así, no hemos arreglado nada.', n_ventas;
    END IF;

    SELECT count(*) INTO n_asin  FROM public.v_salud_asin;
    SELECT count(*) INTO n_cruce FROM public.v_salud_fba_cruce;
    SELECT count(*) INTO n_inc   FROM public.v_incidencias_ultima WHERE stock_fba IS NOT NULL;
    SELECT count(*) INTO n_keepa FROM public.v_keepa_cruce;
    IF n_asin = 0  THEN RAISE EXCEPTION 'ABORTA: v_salud_asin a 0 filas.'; END IF;
    IF n_cruce = 0 THEN RAISE EXCEPTION 'ABORTA: v_salud_fba_cruce a 0 filas.'; END IF;
    IF n_inc = 0   THEN RAISE EXCEPTION 'ABORTA: v_incidencias_ultima no cruza ni una fila con salud_fba. Es el caso del marketplace: revisa el literal ES.'; END IF;
    IF n_keepa = 0 THEN RAISE EXCEPTION 'ABORTA: v_keepa_cruce a 0 filas.'; END IF;

    RAISE NOTICE 'salud_fba (vista): % filas · foto % · disponible % · tránsito % · % con ventas t30',
                 n, f, disp, trans, n_ventas;
    RAISE NOTICE 'v_salud_asin % · v_salud_fba_cruce % · v_incidencias_ultima con stock % · v_keepa_cruce %',
                 n_asin, n_cruce, n_inc, n_keepa;
END $$;
