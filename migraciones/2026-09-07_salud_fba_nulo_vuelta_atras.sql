-- ============================================================================
-- VUELTA ATRÁS de `2026-09-07_salud_fba_el_nulo_no_es_cero.sql`.   7-sep-2026
-- ----------------------------------------------------------------------------
-- 🔴 PARA QUÉ EXISTE, Y CUÁNDO SE LANZA. Sólo hay un motivo: **que Elena deje de
--   ver filas** en el Trackeador o en Salud FBA después de aplicar el paso 2a. Si
--   eso pasa, esto se lanza SIN CONSULTAR A NADIE: primero se devuelve la pantalla
--   y luego se investiga. Un almacén parado cuesta más que una hora de diagnóstico.
--
-- 🔑 QUÉ DESHACE, que es exactamente lo que puede apagar la pantalla:
--     1) `security_invoker` en `salud_fba` y `v_salud_asin`. Es lo único del paso 2a
--        que cambia QUIÉN lee: con él puesto, las vistas leen con los permisos de
--        quien pregunta y quedan sujetas a la RLS de `inventario_fba` y
--        `keepa_escaparate`. Sin él vuelven a leer como su dueño (`postgres`).
--     2) La propagación del nulo. Vuelven los `COALESCE(fc_transfer, 0)` de siempre,
--        o sea que el disponible vuelve a salir como salía antes del 7-sep.
--
-- 🔴 QUÉ **NO** DESHACE, y no es un olvido sino la única forma segura de hacerlo:
--     · **No quita las cuatro columnas nuevas.** `CREATE OR REPLACE VIEW` no puede
--       eliminar columnas; haría falta un `DROP ... CASCADE`, y de estas dos vistas
--       cuelgan SEIS (`v_salud_fba_cruce`, `v_keepa_cruce`, `v_incidencias_ultima`,
--       `v_trackeador_cola`, `v_trackeador_precio_pais` y la propia `v_salud_asin`).
--       Tirarlas para revertir sería cambiar una pantalla apagada por seis objetos
--       muertos. Las columnas sobrantes no las lee nadie todavía: son inertes.
--     · **No devuelve el INSERT/UPDATE/DELETE** que `v_salud_asin` tenía para
--       `authenticated`. Ésos se quitaron a propósito y devolverlos sería una
--       regresión de seguridad, no una vuelta atrás. Además no pueden ser la causa
--       de que la pantalla no lea: no se quita nada de lectura al revocar escritura.
--
-- ⚠️ O SEA QUE ESTO RESTAURA EL COMPORTAMIENTO, NO EL TEXTO. Después de lanzarla,
--   `pg_get_viewdef` no será idéntico al de antes del paso 2a: tendrá cuatro
--   columnas de más. Lo que sí vuelve a ser idéntico es lo que la pantalla ve y
--   quién puede verlo. Es lo que importa y conviene que esté dicho.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI HAY ALGO QUE DESHACER. El testigo:
--       select array_to_string(reloptions,',') from pg_class
--        where oid='public.salud_fba'::regclass;   -- security_invoker=true = hay algo
--
-- PROBADA EN STAGING el 7-sep-2026 con la secuencia completa: aplicar el 2a →
--   lanzar esto → comprobar por SQL que las dos vistas vuelven a su estado de
--   partida. Se prueba ANTES de tocar producción a propósito: cuando no urge, la
--   red va antes del salto.
-- ============================================================================

-- ── 1) salud_fba vuelve a tapar el nulo, y a leer como su dueño ─────────────
CREATE OR REPLACE VIEW public.salud_fba AS
 SELECT i.sku,
    i.fnsku,
    i.asin,
    i.product_name,
    i.condition,
    'ES'::text AS marketplace,
    i.available,
    i.fc_transfer,
    i.total_reserved_quantity,
    NULL::integer AS reserved_fc_processing,
    NULL::integer AS reserved_customer_order,
    NULL::integer AS reserved_staging,
    COALESCE(i.inbound_working, 0) + COALESCE(i.inbound_shipped, 0) + COALESCE(i.inbound_receiving, 0) AS inbound_quantity,
    i.inbound_working,
    i.inbound_shipped,
    i.inbound_receiving AS inbound_received,
    i.unfulfillable_quantity,
    NULL::integer AS pending_removal_quantity,
    -- El COALESCE de siempre: vuelve a salir la cifra de antes del 7-sep.
    COALESCE(i.available, 0) + COALESCE(i.fc_transfer, 0) + COALESCE(i.inbound_working, 0) + COALESCE(i.inbound_shipped, 0) + COALESCE(i.inbound_receiving, 0) AS inventory_supply_at_fba,
    NULL::numeric AS days_of_supply,
    NULL::numeric AS total_days_of_supply_incl_open_shipments,
    NULL::numeric AS weeks_of_cover_t30,
    NULL::numeric AS weeks_of_cover_t90,
    NULL::numeric AS sell_through,
    COALESCE(v.uds_7d, 0::bigint)::integer AS units_shipped_t7,
    COALESCE(v.uds_30d, 0::bigint)::integer AS units_shipped_t30,
    COALESCE(v.uds_60d, 0::bigint)::integer AS units_shipped_t60,
    COALESCE(v.uds_90d, 0::bigint)::integer AS units_shipped_t90,
    NULL::numeric AS historical_days_of_supply,
    NULL::text AS recommended_action,
    NULL::integer AS recommended_ship_in_quantity,
    NULL::text AS recommended_ship_in_date,
    NULL::numeric AS healthy_inventory_level,
    NULL::text AS alert,
    NULL::integer AS estimated_excess_quantity,
    NULL::integer AS recommended_removal_quantity,
    NULL::numeric AS estimated_cost_savings_of_recommended_actions,
    NULL::integer AS fba_minimum_inventory_level,
    NULL::text AS fba_inventory_level_health_status,
    NULL::text AS low_inventory_fee_applied_current_week,
    NULL::text AS exempted_from_low_inventory_fee,
    NULL::numeric AS estimated_storage_cost_next_month,
    NULL::text AS storage_type,
    NULL::numeric AS storage_volume,
    NULL::numeric AS item_volume,
    NULL::text AS inventory_age_snapshot_date,
    NULL::numeric AS featuredoffer_price,
    NULL::numeric AS lowest_price_new_plus_shipping,
    i.your_price,
    NULL::numeric AS sales_price,
    k.rank AS sales_rank,
    NULL::text AS is_seasonal_in_next_3_months,
    NULL::text AS season_name,
    NULL::text AS season_start_date,
    NULL::text AS season_end_date,
    i.fecha_foto AS snapshot_date,
    i.fichero,
    NULL::jsonb AS crudo,
    i.procesado_at AS procesado_en,
    -- Las cuatro no se pueden quitar sin un DROP CASCADE (ver la cabecera). Se
    -- dejan, inertes: hoy no las lee nadie.
    (i.available + i.fc_transfer) AS disponible_cierto,
    i.disponible_estimado,
    i.disponible_origen,
    i.disponible_fuente_fecha
   FROM inventario_fba i
     LEFT JOIN v_ventas_ventanas v ON btrim(v.asin) = btrim(i.asin)
     LEFT JOIN LATERAL ( SELECT ke.rank
           FROM keepa_escaparate ke
          WHERE ke.asin_k = i.asin_k AND ke.dominio_k = 'es'::text
          ORDER BY ke.fecha_foto DESC
         LIMIT 1) k ON true;

ALTER VIEW public.salud_fba RESET (security_invoker);

-- ── 2) v_salud_asin, igual ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW public.v_salud_asin AS
 SELECT asin,
    marketplace,
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
        CASE
            WHEN COALESCE(sum(units_shipped_t7), 0::bigint) > 0 THEN round(sum(COALESCE(available, 0) + COALESCE(fc_transfer, 0))::numeric / (sum(units_shipped_t7)::numeric / 7::numeric), 1)
            ELSE NULL::numeric
        END AS cobertura_dias_t7,
    min(your_price) AS your_price_min,
    max(your_price) AS your_price_max,
    count(*) > 1 AND min(your_price) IS DISTINCT FROM max(your_price) AS precios_desalineados,
    max(featuredoffer_price) AS featuredoffer_price,
    max(lowest_price_new_plus_shipping) AS lowest_price_new_plus_shipping,
    min(sales_rank) AS sales_rank,
    string_agg(DISTINCT NULLIF(alert, ''::text), ' | '::text) AS alertas,
    string_agg(DISTINCT NULLIF(recommended_action, ''::text), ' | '::text) AS acciones_recomendadas,
    string_agg(DISTINCT NULLIF(fba_inventory_level_health_status, ''::text), ' | '::text) AS salud_nivel,
    max(snapshot_date) AS snapshot_date,
    sum(COALESCE(available, 0) + COALESCE(fc_transfer, 0)) AS disponible_cierto,
    sum(disponible_estimado) AS disponible_estimado,
    NULL::text AS disponible_origen,
    min(disponible_fuente_fecha) AS disponible_fuente_fecha
   FROM salud_fba s
  GROUP BY asin, marketplace;

ALTER VIEW public.v_salud_asin RESET (security_invoker);

-- ── 3) EL NÚMERO DE CONTROL: ha vuelto lo que tenía que volver ──────────────
DO $$
DECLARE
  v text; opciones text; n int;
BEGIN
  FOREACH v IN ARRAY ARRAY['salud_fba', 'v_salud_asin'] LOOP
    -- 3.1 · Ya no leen con los permisos de quien pregunta.
    SELECT array_to_string(reloptions, ',') INTO opciones
      FROM pg_class WHERE oid = ('public.' || v)::regclass;
    IF coalesce(opciones, '') LIKE '%security_invoker=true%' THEN
      RAISE EXCEPTION 'ABORTA: % sigue con security_invoker. La vuelta atras no ha '
                      'hecho su trabajo.', v;
    END IF;
    -- 3.2 · Y la escritura NO ha vuelto: revertir la pantalla no es reabrir permisos.
    IF has_table_privilege('authenticated', 'public.' || v, 'INSERT')
       OR has_table_privilege('authenticated', 'public.' || v, 'UPDATE')
       OR has_table_privilege('authenticated', 'public.' || v, 'DELETE') THEN
      RAISE EXCEPTION 'ABORTA: la vuelta atras le ha devuelto escritura a '
                      '`authenticated` sobre %. Eso no se revierte.', v;
    END IF;
  END LOOP;

  -- 3.3 · 🔑 LO QUE DE VERDAD SE REVIERTE: el nulo vuelve a taparse. Con el
  --       transito leido en todas las fichas esto no cambia ninguna cifra, pero si
  --       manana faltara, `inventory_supply_at_fba` tiene que volver a dar numero.
  SELECT count(*) INTO n FROM public.salud_fba WHERE inventory_supply_at_fba IS NULL;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) con inventory_supply_at_fba NULO despues de '
                    'revertir. El COALESCE no ha vuelto.', n;
  END IF;
  SELECT count(*) INTO n FROM public.v_salud_asin WHERE disponible IS NULL;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % ASIN con disponible NULO despues de revertir.', n;
  END IF;

  -- 3.4 · Y las seis que cuelgan siguen vivas: aqui no se ha hecho ningun DROP.
  SELECT count(*) INTO n FROM pg_class
   WHERE relname IN ('v_salud_fba_cruce', 'v_keepa_cruce', 'v_incidencias_ultima',
                     'v_trackeador_cola', 'v_trackeador_precio_pais', 'v_salud_asin');
  IF n <> 6 THEN
    RAISE EXCEPTION 'ABORTA: solo quedan % de las 6 vistas que cuelgan.', n;
  END IF;

  RAISE NOTICE 'Numero de control OK: las dos vistas vuelven a leer como su dueno y '
               'a tapar el nulo, `authenticated` sigue sin escritura, y las 6 vistas '
               'que cuelgan siguen vivas.';
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job):
--
--   select relname, coalesce(array_to_string(reloptions,','),'(sin opciones)') as opciones,
--          has_table_privilege('authenticated','public.'||relname,'SELECT') as auth_lee
--     from pg_class
--    where oid in ('public.salud_fba'::regclass,'public.v_salud_asin'::regclass);
--   -- → (sin opciones) en las dos, y auth_lee tal como estuviera antes
--
--   select count(*) as filas, count(inventory_supply_at_fba) as con_cifra
--     from public.salud_fba;
--   -- → iguales: el COALESCE ha vuelto y no queda ningun nulo
--
--   -- Y LO QUE NO SE PUEDE COMPROBAR DESDE AQUI: que Elena vea filas. Eso se mira
--   -- abriendo el Trackeador y Salud FBA. Es el motivo por el que existe este
--   -- fichero, y la unica prueba que vale.
-- ============================================================================
