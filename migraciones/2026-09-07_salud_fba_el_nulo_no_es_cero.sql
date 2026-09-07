-- ============================================================================
-- salud_fba y v_salud_asin — EL NULO DEJA DE LEERSE COMO CERO.     7-sep-2026
-- (paso 2a de los cuatro del plan; el 2b es la rama del trackeador)
-- ----------------------------------------------------------------------------
-- POR QUÉ. Desde el 7-sep-2026 Amazon puede servir el informe FBA sin la columna
--   del tránsito entre centros, y entonces `inventario_fba.fc_transfer` queda a
--   **NULO** — que es lo correcto: no se sabe. Pero estas dos vistas hacían
--   `COALESCE(fc_transfer, 0)`, o sea que convertían ese «no lo sé» en un CERO y
--   el disponible salía unas 250 unidades corto **sin que nada lo dijera**.
--   Por eso la Guarda 12 del procesador mantiene la carga cerrada: mejor una foto
--   de ayer, vieja y verdadera, que la de hoy corta y creíble.
--
-- 🔑 LO QUE CAMBIA, en una frase: donde había un `COALESCE(fc_transfer, 0)` ahora
--   el nulo se PROPAGA. Una cifra que no se sabe se enseña como que no se sabe.
--
-- 🔴 Y EN LOS AGREGADOS NO BASTA CON QUITAR EL COALESCE, que es la trampa fina de
--   esta migración: `sum()` **ignora los nulos en silencio**. Un ASIN con dos SKU,
--   uno con tránsito leído y otro sin él, daría la suma del primero como si fuera
--   el total — un número creíble y corto, exactamente lo que se persigue evitar.
--   Por eso cada agregado va guardado con
--       CASE WHEN count(*) = count(fc_transfer) THEN sum(...) END
--   que es «si a alguno le falta el dato, el total no se sabe».
--
-- QUÉ COLUMNAS NUEVAS, y por qué se AÑADEN en vez de cambiar las de siempre:
--     · `disponible_cierto`       = available + fc_transfer, sólo cuando el
--       tránsito se ha LEÍDO. NULO cuando no.
--     · `disponible_estimado`     = el puente (paso 1). Lo escribe el procesador.
--     · `disponible_origen`       = 'leido' | 'estimado' | 'desconocido'.
--     · `disponible_fuente_fecha` = de qué día es el internacional que se usó.
--   Se añaden al final para poder usar `CREATE OR REPLACE VIEW`: **aquí no se
--   hace DROP de nada**. De `salud_fba` cuelgan `v_salud_asin`,
--   `v_salud_fba_cruce`, `v_keepa_cruce` y `v_incidencias_ultima`, y de
--   `v_salud_asin` cuelgan `v_trackeador_cola` y `v_trackeador_precio_pais`
--   (medido el 7-sep-2026 cruzando pg_depend con pg_rewrite). Un DROP arrastraría
--   a las seis y se llevaría por delante sus permisos.
--
-- 🔒 Y DE PASO, LAS DOS SE CIERRAN BIEN, porque tocar una vista es la ocasión
--   barata de hacerlo y no se desaprovecha:
--     · `security_invoker = true` en las dos. Medido el 7-sep: `salud_fba` y
--       `v_salud_asin` NO lo tenían (sin opciones, dueño `postgres`), o sea que
--       leían con los permisos del dueño y se saltaban la RLS de las tablas de
--       debajo. `v_trackeador_pantalla` sí lo tiene desde hace tiempo.
--     · `v_salud_asin` tenía **INSERT, UPDATE y DELETE** para `authenticated`
--       (medido: los tres, no sólo el INSERT). Es inofensivo porque la vista no es
--       actualizable, pero sobra — y el `warmer` es un `authenticated`.
--
-- 🔴 EL RIESGO REAL DE ESTA MIGRACIÓN NO ES EL NULO: ES PERDER EL `SELECT`. Si
--   `authenticated` se queda sin SELECT sobre estas vistas, se apaga la pantalla
--   de Elena. Por eso se usa `CREATE OR REPLACE`, que conserva el ACL en vez de
--   rehacerlo, y por eso el bloque 0 fotografía los permisos ANTES y el número de
--   control comprueba que **no se ha perdido ninguno** — con `has_table_privilege`
--   y jamás con `role_table_grants`, que se filtra por el rol de la sesión y
--   devuelve vacío sin avisar (lección del 7-sep-2026).
--
-- 🔴 LO QUE ESTA MIGRACIÓN **NO** PUEDE PROBAR, dicho aquí para que nadie lo dé por
--   probado: que Elena siga VIENDO FILAS. Con `security_invoker` la vista pasa a
--   leer con los permisos de quien pregunta, y `inventario_fba` y `keepa_escaparate`
--   tienen RLS con la política `auth.uid() IS NOT NULL`. Una sesión de Elena la
--   cumple; una sin JWT, no. Aquí sólo se puede comprobar la estructura, porque el
--   job corre como `postgres`. **La prueba de verdad es abrir la pantalla después de
--   aplicar**, y hay que hacerla.
--
-- 🔬 QUE `security_invoker` NO DEJA LA VISTA VACÍA está comprobado, no supuesto:
--   las tres tablas que lee `salud_fba` —`inventario_fba`, `keepa_escaparate` y
--   `v_ventas_ventanas`— son legibles por `authenticated` (medido el 7-sep-2026
--   con `has_table_privilege`), y `v_trackeador_pantalla` ya es `security_invoker`
--   y lee `inventario_fba` con la pantalla funcionando. Ésa es la prueba viva.
--
-- ⚠️ ESTO NO ABRE LA CARGA. La Guarda 12 sigue puesta en el procesador y este
--   fichero no la toca: se abre en el paso 4, cuando la pantalla ya sepa marcar un
--   número estimado. Hasta entonces la foto viva sigue siendo la del 6-sep.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI FALTA ALGO. El testigo, antes de fiarte:
--       select count(*) from information_schema.columns
--        where table_schema='public' and table_name='salud_fba'
--          and column_name='disponible_cierto';        -- 0 = hay algo que probar
--   Medido el 7-sep-2026 en producción: 0.
--
-- 🔬 CORREGIDA DESPUES DE APLICARLA EN STAGING, y queda dicho porque es justo para
--   lo que sirve la escalera. La primera version resolvia el `disponible_origen` del
--   ASIN con un `ELSE 'estimado'`, y con la columna todavia vacia —la carga sigue
--   cerrada por la Guarda 12— eso devolvia **'estimado' en los 361 ASIN de staging**:
--   la vista afirmando que habia una estimacion donde no se habia estimado nada.
--   Produccion no llego a verlo. La migracion es idempotente (CREATE OR REPLACE), asi
--   que relanzarla en staging deja las dos vistas en el estado bueno.
--
-- ESCALERA: staging ensayo → staging aplicar → verificación por SQL → producción
--   ensayo → producción aplicar → verificación por SQL. Con `aplicar-migracion.yml`.
-- ============================================================================

-- ── 0) LA FOTO DEL «ANTES», que es lo que convierte la condición (d) en medible ─
-- 🔴 NO SE COMPRUEBA «authenticated TIENE SELECT», SE COMPRUEBA «NO LO HA PERDIDO»,
--    y la diferencia no es sutil: medido el 7-sep-2026, en PRODUCCIÓN `authenticated`
--    lee estas dos vistas y en STAGING **no** (ahí no tiene SELECT ni sobre ellas ni
--    sobre `inventario_fba`, `keepa_escaparate` o `v_ventas_ventanas`). Una guarda
--    escrita como «tiene que tener SELECT» abortaría en staging por una diferencia
--    de entornos que no tiene nada que ver con lo que esta migración hace — y una
--    guarda que salta por una causa distinta de la que dice medir no es una guarda.
--    La invariante de verdad es: **esta migración no quita ningún permiso**.
CREATE TEMP TABLE _permisos_antes ON COMMIT DROP AS
SELECT v AS vista,
       has_table_privilege('authenticated', 'public.' || v, 'SELECT') AS auth_select,
       has_table_privilege('anon',          'public.' || v, 'SELECT') AS anon_select
  FROM unnest(ARRAY['salud_fba', 'v_salud_asin']) AS v;

-- ── 1) salud_fba ────────────────────────────────────────────────────────────
-- Copiada LITERAL de `pg_get_viewdef(oid, true)` de producción del 7-sep-2026,
-- con DOS cambios y ni una coma más: `inventory_supply_at_fba` deja de tapar el
-- nulo, y se añaden cuatro columnas al final.
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
    -- 🔴 CAMBIO 1. Antes: COALESCE(i.fc_transfer, 0). El tránsito ya NO se tapa —
    --    si no se sabe, el suministro total tampoco se sabe. Los entrantes sí
    --    conservan su COALESCE: ésos vienen siempre en el informe, y un hueco ahí
    --    lo aborta la Guarda 6 antes de llegar a la tabla.
    (i.available + i.fc_transfer + COALESCE(i.inbound_working, 0) + COALESCE(i.inbound_shipped, 0) + COALESCE(i.inbound_receiving, 0)) AS inventory_supply_at_fba,
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
    -- 🔴 CAMBIO 2, las cuatro columnas nuevas. Van AL FINAL porque es lo único que
    --    permite `CREATE OR REPLACE` sin arrastrar a las cuatro vistas que cuelgan.
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

ALTER VIEW public.salud_fba SET (security_invoker = true);

COMMENT ON COLUMN public.salud_fba.disponible_cierto IS
  'available + fc_transfer, y SOLO cuando el transito viene LEIDO del informe. '
  'NULO cuando Amazon no manda esa columna. 🔴 NULO NO ES CERO: quien lo lea tiene '
  'que enseniarlo como desconocido, jamas como 0. Para esos casos esta '
  'disponible_estimado, que va marcado como estimacion.';
COMMENT ON COLUMN public.salud_fba.inventory_supply_at_fba IS
  'Suministro total en FBA. Desde el 7-sep-2026 es NULO cuando el transito no se '
  'sabe: antes se tapaba con COALESCE y salia ~250 uds corto sin decirlo.';

-- ── 2) v_salud_asin ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW public.v_salud_asin AS
 SELECT asin,
    marketplace,
    count(*) AS n_skus,
    string_agg(sku, ' + '::text ORDER BY sku) AS skus,
    max(product_name) AS product_name,
    -- 🔴 EL GUARDADO DE LOS AGREGADOS. `sum()` ignora los nulos en silencio, asi
    --    que un ASIN con dos SKU y el transito leido en uno solo daria la mitad
    --    como si fuera el total. Si a alguno le falta, el total NO se sabe.
    CASE WHEN count(*) = count(fc_transfer)
         THEN sum(COALESCE(available, 0) + fc_transfer) END AS disponible,
    sum(COALESCE(available, 0)) AS available,
    CASE WHEN count(*) = count(fc_transfer)
         THEN sum(fc_transfer) END AS fc_transfer,
    sum(COALESCE(total_reserved_quantity, 0)) AS reservado,
    sum(COALESCE(inbound_quantity, 0)) AS entrante,
    sum(COALESCE(unfulfillable_quantity, 0)) AS no_vendible,
    sum(COALESCE(pending_removal_quantity, 0)) AS pendiente_retirada,
    CASE WHEN count(*) = count(inventory_supply_at_fba)
         THEN sum(inventory_supply_at_fba) END AS stock_fba_total,
    sum(units_shipped_t7) AS t7,
    sum(units_shipped_t30) AS t30,
    sum(units_shipped_t60) AS t60,
    sum(units_shipped_t90) AS t90,
    -- La cobertura hereda el nulo: dividir un disponible desconocido por las
    -- ventas daria una cobertura inventada, y con ella se decide reponer.
        CASE
            WHEN COALESCE(sum(units_shipped_t7), 0::bigint) > 0 AND count(*) = count(fc_transfer)
            THEN round(sum(COALESCE(available, 0) + fc_transfer)::numeric / (sum(units_shipped_t7)::numeric / 7::numeric), 1)
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
    -- Las cuatro nuevas, al final. Mismo guardado para el estimado.
    CASE WHEN count(*) = count(fc_transfer)
         THEN sum(COALESCE(available, 0) + fc_transfer) END AS disponible_cierto,
    CASE WHEN count(*) = count(disponible_estimado)
         THEN sum(disponible_estimado) END AS disponible_estimado,
    -- 🔑 El origen del ASIN es el PEOR de sus SKU, no el mejor: si a uno solo le
    --    falta el dato, la cifra del ASIN no es fiable del todo.
    -- 🔴 LA PRIMERA RAMA LA CAZO STAGING, y sin ella esta vista MENTIA. Mientras la
    --    carga siga cerrada por la Guarda 12, `disponible_origen` esta VACIA en toda
    --    la tabla; sin este primer CASE ninguna fila casaba con 'desconocido' ni con
    --    'leido' y el ELSE devolvia **'estimado' para los 361 ASIN** — o sea, la
    --    vista afirmando que hay una estimacion donde no se ha estimado nada.
    --    Un ELSE es una AFIRMACION, no un valor por defecto.
        CASE
            WHEN count(*) <> count(disponible_origen) THEN NULL::text
            WHEN count(*) FILTER (WHERE disponible_origen = 'desconocido'::text) > 0 THEN 'desconocido'::text
            WHEN count(*) = count(*) FILTER (WHERE disponible_origen = 'leido'::text) THEN 'leido'::text
            ELSE 'estimado'::text
        END AS disponible_origen,
    -- El dato MAS VIEJO del que depende esta cifra, no el mas nuevo.
    min(disponible_fuente_fecha) AS disponible_fuente_fecha
   FROM salud_fba s
  GROUP BY asin, marketplace;

ALTER VIEW public.v_salud_asin SET (security_invoker = true);

-- 🔴 El `warmer` es un `authenticated`. Estas tres no hacen nada hoy (la vista no
--    es actualizable), pero una vista de solo lectura no tiene por que tenerlas.
REVOKE INSERT, UPDATE, DELETE ON public.v_salud_asin FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.salud_fba FROM authenticated;

COMMENT ON COLUMN public.v_salud_asin.disponible IS
  'Suma de available + fc_transfer del ASIN, y NULO si a alguno de sus SKU le falta '
  'el transito. 🔴 El CASE no es decorativo: sum() ignora los nulos en silencio y '
  'sin el saldria la suma parcial como si fuera el total.';
COMMENT ON COLUMN public.v_salud_asin.disponible_origen IS
  'El PEOR origen de los SKU del ASIN: ''desconocido'' si a alguno le falta, '
  '''leido'' solo si a todos les consta, ''estimado'' en el resto.';

-- ── 3) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  v text; n int; opciones text;
BEGIN
  -- 3.1 · 🔴 LO PRIMERO Y LO MÁS IMPORTANTE: nadie ha PERDIDO el SELECT. Si esto
  --       falla, la pantalla de Elena se apaga. Se compara contra la foto del
  --       bloque 0, no contra un absoluto (ver el porqué allí).
  FOREACH v IN ARRAY ARRAY['salud_fba', 'v_salud_asin'] LOOP
    IF EXISTS (SELECT 1 FROM _permisos_antes a
                WHERE a.vista = v AND a.auth_select
                  AND NOT has_table_privilege('authenticated', 'public.' || v, 'SELECT')) THEN
      RAISE EXCEPTION 'ABORTA: `authenticated` LEIA % y ha dejado de leerla. Eso '
                      'apaga la pantalla de Elena. No se aplica nada.', v;
    END IF;
    -- 3.2 · y ninguna de las dos escribe.
    IF has_table_privilege('authenticated', 'public.' || v, 'INSERT')
       OR has_table_privilege('authenticated', 'public.' || v, 'UPDATE')
       OR has_table_privilege('authenticated', 'public.' || v, 'DELETE') THEN
      RAISE EXCEPTION 'ABORTA: `authenticated` conserva escritura sobre %.', v;
    END IF;
    -- 3.3 · y las dos leen con los permisos de quien pregunta.
    SELECT array_to_string(reloptions, ',') INTO opciones
      FROM pg_class WHERE oid = ('public.' || v)::regclass;
    IF opciones IS NULL OR opciones NOT LIKE '%security_invoker=true%' THEN
      RAISE EXCEPTION 'ABORTA: % no ha quedado con security_invoker=true (reloptions: %).',
                      v, coalesce(opciones, '(sin opciones)');
    END IF;
    -- 3.4 · `anon` no entra, ni antes ni ahora. Aqui SI vale el absoluto: en los
    --       dos entornos estaba fuera, y ganar un permiso nunca es aceptable.
    IF has_table_privilege('anon', 'public.' || v, 'SELECT') THEN
      RAISE EXCEPTION 'ABORTA: `anon` puede leer %.', v;
    END IF;
  END LOOP;

  -- 3.5 · Las cuatro columnas nuevas existen en las dos vistas.
  SELECT count(*) INTO n FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name IN ('salud_fba', 'v_salud_asin')
     AND column_name IN ('disponible_cierto', 'disponible_estimado',
                         'disponible_origen', 'disponible_fuente_fecha');
  IF n <> 8 THEN
    RAISE EXCEPTION 'ABORTA: se esperaban 8 columnas nuevas (4 en cada vista) y hay %.', n;
  END IF;

  -- 3.6 · 🔑 LA COMPROBACIÓN QUE MIDE LO QUE ESTA MIGRACIÓN DICE HACER: hoy la
  --       foto viva del 6-sep trae el tránsito LEÍDO en las 381 fichas, así que
  --       `disponible_cierto` NO puede ser nulo en ninguna. Si lo fuera, el
  --       cambio habría roto el caso normal en vez de arreglar el raro.
  SELECT count(*) INTO n FROM public.salud_fba WHERE disponible_cierto IS NULL;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) con disponible_cierto NULO, y hoy el informe '
                    'trae el transito en todas. El cambio ha roto el caso normal.', n;
  END IF;

  -- 3.7 · Y que la cifra sea la MISMA de siempre cuando el tránsito se sabe: esta
  --       migración no debe mover ni una unidad del caso normal.
  SELECT count(*) INTO n FROM public.salud_fba
   WHERE disponible_cierto IS DISTINCT FROM (COALESCE(available, 0) + COALESCE(fc_transfer, 0));
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) donde el disponible nuevo no coincide con el '
                    'viejo, y con el transito leido tienen que ser identicos.', n;
  END IF;

  -- 3.8 · 🔴 EL FALLO QUE CAZO STAGING: con `disponible_origen` sin escribir, el
  --       agregado por ASIN no puede afirmar 'estimado'. O lo sabe, o es NULO.
  SELECT count(*) INTO n FROM public.v_salud_asin a
   WHERE a.disponible_origen IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM public.salud_fba s
                      WHERE s.asin = a.asin AND s.disponible_origen IS NOT NULL);
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % ASIN dicen tener un origen del disponible y ninguno de '
                    'sus SKU lo tiene. La vista estaria afirmando lo que no sabe.', n;
  END IF;

  RAISE NOTICE 'Numero de control OK: authenticated conserva el SELECT y no escribe, '
               'las dos con security_invoker=true, anon fuera, 8 columnas nuevas, y '
               'el disponible del caso normal no se ha movido ni una unidad.';
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   -- 🔴 lo primero: el SELECT sigue ahí, y no hay escritura
--   select relname,
--          array_to_string(reloptions,',')                                as opciones,
--          has_table_privilege('authenticated','public.'||relname,'SELECT') as auth_lee,
--          has_table_privilege('authenticated','public.'||relname,'INSERT') as auth_ins,
--          has_table_privilege('authenticated','public.'||relname,'UPDATE') as auth_upd,
--          has_table_privilege('authenticated','public.'||relname,'DELETE') as auth_del,
--          has_table_privilege('anon','public.'||relname,'SELECT')          as anon_lee
--     from pg_class
--    where oid in ('public.salud_fba'::regclass,'public.v_salud_asin'::regclass);
--   -- → security_invoker=true · true · false · false · false · false, en las dos
--
--   -- el caso normal no se ha movido (hoy la foto del 6-sep trae el transito):
--   select count(*)                                        as filas,
--          count(disponible_cierto)                        as con_cierto,
--          count(*) filter (where disponible_origen is null) as sin_origen,
--          sum(disponible_cierto)                          as suma_cierto
--     from public.salud_fba;
--   -- → 381 · 381 · 381 · 6692
--   --   (sin_origen = 381 es lo esperado HOY: la columna del procesador esta
--   --    vacia porque la carga sigue cerrada por la Guarda 12. Se llena en el paso 4.)
--
--   -- y las seis vistas que cuelgan siguen vivas (un DROP se las habria llevado):
--   select count(*) from pg_class
--    where relname in ('v_salud_fba_cruce','v_keepa_cruce','v_incidencias_ultima',
--                      'v_trackeador_cola','v_trackeador_precio_pais','v_salud_asin');
--   -- → 6
-- ============================================================================
