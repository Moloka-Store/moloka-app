-- ============================================================================
-- MIGRACION · cada copia dice CUANDO se refresco
-- ----------------------------------------------------------------------------
-- 🔴 QUE PROBLEMA RESUELVE. Hoy no hay forma de saber en que ORDEN se refrescaron
--    las copias, ni si una se quedo atras. El centinela de la pantalla dice si el
--    DATO va al dia --compara anclas--, que es otra pregunta: una copia puede
--    tener el ancla buena y haberse refrescado hace tres dias porque desde
--    entonces no ha entrado nada. Y al reves: si el orden del refresco esta mal
--    --por ejemplo la del Trackeador ANTES que las nuestras, cuando lee las
--    mismas tablas-- el ancla no lo nota y el numero sale viejo sin sintoma.
--
-- 🔑 POR QUE UNA COLUMNA DENTRO DE LA COPIA Y NO UNA TABLA DE REGISTRO. Una tabla
--    la escribiria el gancho, o sea que solo veria los refrescos que pasan POR EL
--    GANCHO. `clock_timestamp()` dentro de la definicion se evalua en CADA
--    refresco, venga de donde venga --el gancho, un cron, o alguien a mano en
--    psql--. No se puede esquivar, y eso es justo lo que se le pide a un testigo.
--
-- 🔒 `clock_timestamp()` Y NO `now()`, y no es indiferente: `now()` es la hora de
--    la TRANSACCION, asi que dos copias refrescadas dentro de la misma darian el
--    MISMO instante y no se podria ordenar -- que es exactamente lo que se quiere
--    diagnosticar. `clock_timestamp()` avanza de verdad.
--
-- ⚠️ EL PRECIO, MEDIDO Y ACEPTADO. El refresco sin bloquear lectores no reescribe la
--    copia entera: calcula lo nuevo y solo aplica las filas que CAMBIAN. Con una
--    columna que cambia en todas, cambian todas -- o sea que cada refresco pasa a
--    ser un borrado e insercion completos.
--    🔬 Con los tamanos de hoy da igual: `mv_ventas_ventanas` tiene 293 filas y
--       `mv_rentabilidad_sku` 1.314, y sus refrescos medidos en produccion
--       (2.256 ms y 3.050 ms) los domina la CONSULTA, no el volcado. Se anota
--       porque en una copia de cientos de miles de filas la cuenta cambiaria.
--
-- 🔴 LA COLUMNA NO SALE A LAS VISTAS, Y ES A PROPOSITO. `v_ventas_ventanas`
--    conserva sus 17 columnas y las de rentabilidad sus 21 y 14: el contrato no se
--    toca. Esto es diagnostico, y se consulta en la copia.
--
-- 🔑 EL BAILE DE NOMBRES, que es lo que permite hacerlo sin romper nada. A una
--    materializada NO se le puede anadir una columna: hay que rehacerla. Y no se
--    puede borrar mientras una vista cuelgue de ella. Un `DROP ... CASCADE` se
--    llevaria las vistas por delante --con su OID y sus ACL--, que es justo lo que
--    no se quiere. Asi que:
--      1. se RENOMBRA la copia vieja (las vistas la siguen por OID, no por nombre)
--      2. se crea la nueva, con la columna
--      3. `CREATE OR REPLACE VIEW` reapunta las vistas a la nueva, CONSERVANDO SU
--         OID y por tanto sus permisos y todo lo que cuelgue de ellas
--      4. y entonces la vieja ya no tiene dependientes y se puede tirar
--    La consulta pesada se calcula UNA vez, en el paso 2.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    n_ventanas bigint; n_rent bigint;
BEGIN
    IF to_regclass('public.mv_ventas_ventanas') IS NULL
       OR to_regclass('public.mv_rentabilidad_sku') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: faltan copias. Esta migracion las REHACE; si no existen, es que sus migraciones no se han aplicado aqui.';
    END IF;

    -- 🔴 SI YA TIENEN LA COLUMNA, ESTA MIGRACION YA CORRIO. Un ensayo sobre el
    --    estado de destino sale verde sin demostrar nada.
    -- 🔴 `pg_attribute` Y NO `information_schema`: ESE CATALOGO NO VE LAS
    --    MATERIALIZADAS. No son parte del estandar SQL, asi que no aparecen -- y una
    --    consulta contra el no da error: DEVUELVE CERO FILAS. Escrito asi, este
    --    `IF EXISTS` era inerte: no podia dispararse NUNCA, dijera lo que dijera la
    --    base. Cazado el 25-ago porque el testigo de abajo, escrito con el mismo
    --    error, aborto el ensayo en staging.
    IF EXISTS (SELECT 1 FROM pg_attribute
                WHERE attrelid = 'public.mv_ventas_ventanas'::regclass
                  AND attname = 'refrescada_el' AND attnum > 0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: mv_ventas_ventanas YA tiene refrescada_el.';
    END IF;

    -- Anti-cero: sin filas, todo lo de abajo saldria "bien" sin medir nada.
    SELECT count(*) INTO n_ventanas FROM mv_ventas_ventanas;
    SELECT count(*) INTO n_rent FROM mv_rentabilidad_sku;
    IF n_ventanas = 0 OR n_rent = 0 THEN
        RAISE EXCEPTION 'ABORTA: ventanas=% filas, rentabilidad=% filas. Una copia vacia no prueba nada.', n_ventanas, n_rent;
    END IF;
    RAISE NOTICE 'Guardas OK. ventanas=% filas, rentabilidad=% filas.', n_ventanas, n_rent;
END
$guardas$;

-- ============================================================================
-- 1) mv_ventas_ventanas
-- ============================================================================
ALTER MATERIALIZED VIEW public.mv_ventas_ventanas RENAME TO mv_ventas_ventanas_viejo;
-- 🔒 El indice tambien, o el nombre chocaria al crear el de la copia nueva.
ALTER INDEX public.mv_ventas_ventanas_asin_uk RENAME TO mv_ventas_ventanas_asin_uk_viejo;

CREATE MATERIALIZED VIEW public.mv_ventas_ventanas AS
 WITH ancla AS (
         SELECT ( SELECT max(ledger_movimientos.fecha) AS max
                   FROM ledger_movimientos) AS hasta_ledger,
            ( SELECT max(transacciones_movimientos.fecha) AS max
                   FROM transacciones_movimientos) AS hasta_trans,
            ( SELECT max(listings_amazon.fecha_informe) AS max
                   FROM listings_amazon) AS hasta_listings
        ), salidas AS (
         SELECT l.asin,
            sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 8) AND l.fecha < a_1.hasta_ledger) AS uds_7d,
            sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 31) AND l.fecha < a_1.hasta_ledger) AS uds_30d,
            sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 61) AND l.fecha < a_1.hasta_ledger) AS uds_60d,
            sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 91) AND l.fecha < a_1.hasta_ledger) AS uds_90d
           FROM ledger_movimientos l
             CROSS JOIN ancla a_1
          WHERE l.event_type = 'Shipments'::text AND l.asin IS NOT NULL AND l.fecha > (a_1.hasta_ledger - 91) AND l.fecha < a_1.hasta_ledger
          GROUP BY l.asin
        ), devueltas AS (
         SELECT l.asin,
            sum(abs(l.quantity)) AS devoluciones_30d
           FROM ledger_movimientos l
             CROSS JOIN ancla a_1
          WHERE l.event_type = 'CustomerReturns'::text AND l.asin IS NOT NULL AND l.fecha > (a_1.hasta_ledger - 31) AND l.fecha < a_1.hasta_ledger
          GROUP BY l.asin
        ), sku_asin AS (
         SELECT DISTINCT ON ((btrim(listings_amazon.seller_sku))) btrim(listings_amazon.seller_sku) AS sku,
            btrim(listings_amazon.asin) AS asin
           FROM listings_amazon
          WHERE listings_amazon.seller_sku IS NOT NULL AND listings_amazon.asin IS NOT NULL AND btrim(listings_amazon.asin) <> ''::text
          ORDER BY (btrim(listings_amazon.seller_sku)), listings_amazon.fecha_informe DESC
        ), mercado AS (
         SELECT sa.asin,
            COALESCE(sum(t.cantidad) FILTER (WHERE t.pais = 'ES'::text), 0::bigint) AS uds_30d_es,
            COALESCE(sum(t.cantidad) FILTER (WHERE t.pais = 'IT'::text), 0::bigint) AS uds_30d_it,
            COALESCE(sum(t.cantidad) FILTER (WHERE t.pais = 'FR'::text), 0::bigint) AS uds_30d_fr,
            COALESCE(sum(t.cantidad), 0::bigint) AS uds_30d_marketplace,
            round(COALESCE(sum(t.ventas_producto), 0::numeric), 2) AS eur_30d_marketplace
           FROM transacciones_movimientos t
             CROSS JOIN ancla a_1
             JOIN sku_asin sa ON sa.sku = btrim(t.sku)
          WHERE t.tipo_norm = 'pedido'::text AND t.fecha > (a_1.hasta_trans - 30)
          GROUP BY sa.asin
        )
 SELECT COALESCE(s.asin, m.asin) AS asin,
    COALESCE(s.uds_7d, 0::bigint) AS uds_7d,
    COALESCE(s.uds_30d, 0::bigint) AS uds_30d,
    COALESCE(s.uds_60d, 0::bigint) AS uds_60d,
    COALESCE(s.uds_90d, 0::bigint) AS uds_90d,
    round(COALESCE(s.uds_30d, 0::bigint)::numeric / 30::numeric, 3) AS vel_dia_30d,
    round(COALESCE(s.uds_90d, 0::bigint)::numeric / 90::numeric, 3) AS vel_dia_90d,
    COALESCE(m.uds_30d_es, 0::bigint) AS uds_30d_es,
    COALESCE(m.uds_30d_it, 0::bigint) AS uds_30d_it,
    COALESCE(m.uds_30d_fr, 0::bigint) AS uds_30d_fr,
    COALESCE(m.uds_30d_marketplace, 0::bigint) AS uds_30d_marketplace,
    COALESCE(m.eur_30d_marketplace, 0::numeric) AS eur_30d_marketplace,
    COALESCE(d.devoluciones_30d, 0::bigint) AS devoluciones_30d,
    a.hasta_ledger AS ventana_hasta_ledger,
    a.hasta_trans AS ventana_hasta_marketplace,
    a.hasta_listings AS ventana_hasta_listings,
    clock_timestamp() AS refrescada_el
   FROM salidas s
     FULL JOIN mercado m ON m.asin = s.asin
     LEFT JOIN devueltas d ON d.asin = COALESCE(s.asin, m.asin)
     CROSS JOIN ancla a
WITH DATA;

CREATE UNIQUE INDEX mv_ventas_ventanas_asin_uk ON public.mv_ventas_ventanas (asin);

-- 🔴 LA PUERTA SE VUELVE A CERRAR, Y NO ES OPCIONAL. Un `DROP` + `CREATE` PIERDE el
--    ACL y el objeto nace con el default de Supabase. Aqui es un objeto NUEVO, asi
--    que hereda lo que herede -- y hay que revocar antes de conceder, por rol y por
--    su nombre, no confiando en un `revoke ... from public`.
REVOKE ALL ON public.mv_ventas_ventanas FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_ventas_ventanas TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_ventas_ventanas IS
    'Ventanas de ventas por ASIN, materializadas el 25-ago-2026. `refrescada_el` (clock_timestamp) dice cuando se refresco ESTA copia: sirve para diagnosticar el ORDEN de los refrescos, que el ancla no puede contar. La columna NO sale a v_ventas_ventanas: el contrato de la vista son sus 17 columnas. Se refresca desde procesador_ledger.py, procesador_transacciones.py y procesador_all_listings.py.';

-- 🔒 Reapunta la vista a la copia nueva CONSERVANDO SU OID: mismas 17 columnas, mismo
--    orden, mismos tipos. `dias_desde_ultimo_dato` sigue calculandose EN VIVO, que es
--    el motivo por el que nunca entro en la copia.
CREATE OR REPLACE VIEW public.v_ventas_ventanas AS
 SELECT asin,
    uds_7d,
    uds_30d,
    uds_60d,
    uds_90d,
    vel_dia_30d,
    vel_dia_90d,
    uds_30d_es,
    uds_30d_it,
    uds_30d_fr,
    uds_30d_marketplace,
    eur_30d_marketplace,
    devoluciones_30d,
    ventana_hasta_ledger,
    ventana_hasta_marketplace,
    CURRENT_DATE - ventana_hasta_ledger AS dias_desde_ultimo_dato,
    ventana_hasta_listings
   FROM mv_ventas_ventanas;

DROP MATERIALIZED VIEW public.mv_ventas_ventanas_viejo;

-- ============================================================================
-- 2) mv_rentabilidad_sku
-- ============================================================================
ALTER MATERIALIZED VIEW public.mv_rentabilidad_sku RENAME TO mv_rentabilidad_sku_viejo;
ALTER INDEX public.mv_rentabilidad_sku_uk RENAME TO mv_rentabilidad_sku_uk_viejo;

CREATE MATERIALIZED VIEW public.mv_rentabilidad_sku AS
SELECT t.pais,
       date_trunc('month'::text, t.fecha::timestamp with time zone)::date AS mes,
       t.sku,
       COALESCE(t.sku, ''::text) AS sku_k,
       max(t.fecha) AS fecha_hasta,
       sum(t.ventas_producto + t.impuesto_producto)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS facturacion_iva,
       sum(t.ventas_producto)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS facturacion_sin_iva,
       sum(t.cantidad)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS unidades,
       sum((- t.tarifa_venta) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS comision_amazon,
       sum((- t.tarifa_fba) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS logistica_fba,
       sum((- t.tarifa_otras) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS otras_tarifas,
       COALESCE(sum(t.ventas_producto) FILTER (WHERE t.tipo_norm = 'reembolso'::text), 0::numeric)
       + COALESCE(sum((t.tarifa_venta + t.tarifa_fba + t.tarifa_otras) / 1.21)
                  FILTER (WHERE t.tipo_norm = 'reembolso'::text), 0::numeric) AS reembolsos_netos,
       clock_timestamp() AS refrescada_el
  FROM transacciones_movimientos t
 GROUP BY t.pais, date_trunc('month'::text, t.fecha::timestamp with time zone)::date, t.sku
WITH DATA;

CREATE UNIQUE INDEX mv_rentabilidad_sku_uk
    ON public.mv_rentabilidad_sku (pais, mes, sku_k);

REVOKE ALL ON public.mv_rentabilidad_sku FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_rentabilidad_sku TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_rentabilidad_sku IS
    'Agregado CRUDO de transacciones_movimientos por (pais, mes, sku), materializado el 25-ago-2026. Sirve a v_rentabilidad_producto_mes y a v_rentabilidad_transacciones, que son la misma cuenta a dos niveles. NO lleva NADA de productos --ni el pvd, ni producto_id, ni con_ficha-- a proposito: eso cambia mientras Elena trabaja y se cruza en vivo en las vistas de encima. Un coste congelado es una cifra falsa. `refrescada_el` (clock_timestamp) dice cuando se refresco ESTA copia. Se refresca desde procesador_transacciones.py.';

CREATE OR REPLACE VIEW public.v_rentabilidad_producto_mes AS
WITH prod AS (
    SELECT DISTINCT ON (p.sku) p.sku, p.id, p.pvd, p.asin, p.nombre, p.ean, p.es_chase
      FROM productos p
     WHERE p.sku IS NOT NULL
     ORDER BY p.sku, (p.activo IS TRUE) DESC, p.id DESC
)
SELECT m.pais,
       m.mes,
       m.sku,
       (p.sku IS NOT NULL) AS con_ficha,
       CASE WHEN p.es_chase IS TRUE THEN NULL::text ELSE p.asin END AS asin,
       p.nombre,
       p.ean,
       COALESCE(p.es_chase, false) AS es_chase,
       p.nombre ~* '\mpack'::text AS es_pack,
       NULLIF(COALESCE((regexp_match(p.nombre, 'pack\s*de\s*(\d+)'::text, 'i'::text))[1],
                       (regexp_match(p.nombre, 'pack\s*(\d+)'::text, 'i'::text))[1],
                       (regexp_match(p.nombre, '(\d+)\s*-?\s*pack'::text, 'i'::text))[1]),
              ''::text)::integer AS factor_pack,
       m.fecha_hasta,
       CASE WHEN p.sku IS NOT NULL THEN m.unidades END AS unidades,
       CASE WHEN p.sku IS NOT NULL THEN m.facturacion_iva END AS facturacion_iva,
       CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END AS facturacion_sin_iva,
       CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END AS coste_pvd,
       CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END AS comision_amazon,
       CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END AS logistica_fba,
       CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END AS otras_tarifas,
       COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
           * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric) AS coste_almacen,
       m.reembolsos_netos,
       COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END, 0::numeric)
       - (COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
            * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric))
       + COALESCE(m.reembolsos_netos, 0::numeric) AS beneficio
  FROM public.mv_rentabilidad_sku m
  LEFT JOIN prod p ON p.sku = m.sku;

CREATE OR REPLACE VIEW public.v_rentabilidad_transacciones AS
WITH prod AS (
    SELECT DISTINCT ON (p.sku) p.sku, p.id, p.pvd
      FROM productos p
     WHERE p.sku IS NOT NULL
     ORDER BY p.sku, (p.activo IS TRUE) DESC, p.id DESC
), por_sku AS (
    SELECT m.pais, m.mes, m.fecha_hasta,
           CASE WHEN p.sku IS NOT NULL THEN m.facturacion_iva END AS f_iva,
           CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END AS f_sin,
           CASE WHEN p.sku IS NOT NULL THEN m.unidades END AS uds,
           CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END AS pvd,
           CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END AS com,
           CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END AS fba,
           CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END AS otras,
           COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
               * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric) AS alm,
           m.reembolsos_netos AS reem
      FROM public.mv_rentabilidad_sku m
      LEFT JOIN prod p ON p.sku = m.sku
), agr AS (
    SELECT pais, mes, max(fecha_hasta) AS fecha_hasta,
           round(sum(f_iva), 2) AS facturacion_iva,
           round(sum(f_sin), 2) AS facturacion_sin_iva,
           sum(uds)::bigint AS unidades,
           round(sum(pvd), 2) AS coste_pvd,
           round(sum(com), 2) AS comision_amazon,
           round(sum(fba), 2) AS logistica_fba,
           round(sum(otras), 2) AS otras_tarifas,
           round(sum(alm), 2) AS coste_almacen,
           round(sum(reem), 2) AS reembolsos_netos
      FROM por_sku
     GROUP BY pais, mes
)
SELECT pais,
       mes,
       facturacion_iva,
       facturacion_sin_iva,
       unidades,
       coste_pvd,
       comision_amazon,
       logistica_fba,
       otras_tarifas,
       coste_almacen,
       reembolsos_netos,
       round(COALESCE(facturacion_sin_iva, 0::numeric)
             - (COALESCE(coste_pvd, 0::numeric) + COALESCE(comision_amazon, 0::numeric)
                + COALESCE(logistica_fba, 0::numeric) + COALESCE(otras_tarifas, 0::numeric)
                + COALESCE(coste_almacen, 0::numeric))
             + COALESCE(reembolsos_netos, 0::numeric), 2) AS beneficio,
       CASE WHEN COALESCE(facturacion_iva, 0::numeric) <> 0::numeric
            THEN round((COALESCE(facturacion_sin_iva, 0::numeric)
                        - (COALESCE(coste_pvd, 0::numeric) + COALESCE(comision_amazon, 0::numeric)
                           + COALESCE(logistica_fba, 0::numeric) + COALESCE(otras_tarifas, 0::numeric)
                           + COALESCE(coste_almacen, 0::numeric))
                        + COALESCE(reembolsos_netos, 0::numeric)) / facturacion_iva * 100::numeric, 2)
       END AS margen_pct,
       fecha_hasta
  FROM agr;

DROP MATERIALIZED VIEW public.mv_rentabilidad_sku_viejo;

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    -- 🔬 Medidas contra PRODUCCION. Si las tres vistas siguen dando esto EXACTO,
    --    el baile de nombres no ha movido un dato.
    HUELLA_VENT constant text := '747d612229bda09cc3418fa46115f93c';
    FILAS_VENT  constant bigint := 293;
    HUELLA_PM   constant text := 'e106bc95001130eadc105490642250bc';
    FILAS_PM    constant bigint := 1314;
    HUELLA_TX   constant text := 'a22690ab9386ec7eed54c75c4e8f46cd';
    FILAS_TX    constant bigint := 22;
    n_v bigint; n_pm bigint; n_tx bigint;
    h_v text; h_pm text; h_tx text;
    cols text;
    sobra int;
BEGIN
    -- 🔴 LO PRIMERO: QUE NO QUEDEN RESTOS. Si el DROP de una copia vieja no hubiera
    --    corrido, la migracion habria dejado una copia huerfana ocupando sitio y
    --    congelada para siempre -- y nada mas se quejaria.
    SELECT count(*) INTO sobra FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relname LIKE '%\_viejo';
    IF sobra > 0 THEN
        RAISE EXCEPTION 'ABORTA: han quedado % objeto(s) con sufijo _viejo. El baile de nombres no termino.', sobra;
    END IF;

    -- La columna nueva, en las dos copias y en NINGUNA vista.
    -- 🔴 Por `pg_attribute`, no por `information_schema`: ese catalogo NO VE LAS
    --    MATERIALIZADAS y devuelve cero filas sin dar error. Ver la guarda de arriba.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid = 'public.mv_ventas_ventanas'::regclass
                      AND attname = 'refrescada_el' AND attnum > 0 AND NOT attisdropped)
       OR NOT EXISTS (SELECT 1 FROM pg_attribute
                       WHERE attrelid = 'public.mv_rentabilidad_sku'::regclass
                         AND attname = 'refrescada_el' AND attnum > 0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: alguna copia se ha quedado sin refrescada_el.';
    END IF;
    -- 🔒 Y anclado sobre lo que NO debe aparecer, que es la mitad que se mueve: si la
    --    columna se colara a una vista, cambiaria su contrato y la app la veria.
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND column_name='refrescada_el'
                  AND table_name IN ('v_ventas_ventanas','v_rentabilidad_producto_mes',
                                     'v_rentabilidad_transacciones')) THEN
        RAISE EXCEPTION 'ABORTA: refrescada_el se ha colado en una VISTA. Es diagnostico y vive en la copia; en la vista cambiaria el contrato.';
    END IF;

    -- Los contratos, con TIPOS: la huella md5 sobre el texto de las filas es ciega a ellos.
    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_rentabilidad_transacciones';
    IF cols <> 'pais:text,mes:date,facturacion_iva:numeric,facturacion_sin_iva:numeric,unidades:bigint,coste_pvd:numeric,comision_amazon:numeric,logistica_fba:numeric,otras_tarifas:numeric,coste_almacen:numeric,reembolsos_netos:numeric,beneficio:numeric,margen_pct:numeric,fecha_hasta:date' THEN
        RAISE EXCEPTION 'ABORTA: v_rentabilidad_transacciones cambio de contrato. Ahora: %', cols;
    END IF;
    -- ⚠️ ESTE CONTRATO ESTA COPIADO DE LA BASE, NO ESCRITO A MANO, y hubo que
    --    aprenderlo: la primera version decia `ventana_hasta_listings:date` porque
    --    las otras dos anclas lo son. No: sale de `listings_amazon.fecha_informe`,
    --    que es `timestamptz`. Lo cazo el ensayo -- que es lo que tiene que pasar --
    --    pero un contrato que se escribe de memoria no es un contrato, es un
    --    recuerdo. Se saca con la misma consulta que lo comprueba.
    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_ventas_ventanas';
    IF cols <> 'asin:text,uds_7d:bigint,uds_30d:bigint,uds_60d:bigint,uds_90d:bigint,vel_dia_30d:numeric,vel_dia_90d:numeric,uds_30d_es:bigint,uds_30d_it:bigint,uds_30d_fr:bigint,uds_30d_marketplace:bigint,eur_30d_marketplace:numeric,devoluciones_30d:bigint,ventana_hasta_ledger:date,ventana_hasta_marketplace:date,dias_desde_ultimo_dato:integer,ventana_hasta_listings:timestamp with time zone' THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas cambio de contrato. Ahora: %', cols;
    END IF;

    -- Los indices unicos, que son lo que permite refrescar sin bloquear lectores.
    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_ventas_ventanas'::regclass AND indisunique)
       OR NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_rentabilidad_sku'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: alguna copia se ha quedado sin indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;

    -- Y las huellas: que el baile de nombres no haya movido un dato.
    SELECT count(*) INTO n_v FROM v_ventas_ventanas;
    SELECT count(*) INTO n_pm FROM v_rentabilidad_producto_mes;
    SELECT count(*) INTO n_tx FROM v_rentabilidad_transacciones;
    SELECT md5(string_agg(t::text, '|' ORDER BY t.asin)) INTO h_v FROM (
        SELECT asin, uds_7d, uds_30d, uds_60d, uds_90d, vel_dia_30d, vel_dia_90d,
               uds_30d_es, uds_30d_it, uds_30d_fr, uds_30d_marketplace, eur_30d_marketplace,
               devoluciones_30d, ventana_hasta_ledger, ventana_hasta_marketplace
          FROM v_ventas_ventanas) t;
    SELECT md5(string_agg(t::text, '|' ORDER BY t.pais, t.mes, COALESCE(t.sku,'~'))) INTO h_pm FROM (
        SELECT pais, mes, sku, con_ficha, fecha_hasta, unidades, facturacion_iva,
               facturacion_sin_iva, coste_pvd, comision_amazon, logistica_fba,
               otras_tarifas, coste_almacen, reembolsos_netos
          FROM v_rentabilidad_producto_mes) t;
    SELECT md5(string_agg(t::text, '|' ORDER BY t.pais, t.mes)) INTO h_tx FROM (
        SELECT pais, mes, facturacion_iva, facturacion_sin_iva, unidades, coste_pvd,
               comision_amazon, logistica_fba, otras_tarifas, coste_almacen,
               reembolsos_netos, beneficio, margen_pct, fecha_hasta
          FROM v_rentabilidad_transacciones) t;

    IF n_v <> FILAS_VENT OR n_pm <> FILAS_PM OR n_tx <> FILAS_TX THEN
        RAISE WARNING 'HUELLAS NO COMPROBADAS EN ESTE ENTORNO: se midieron sobre PRODUCCION con %/%/% filas y aqui hay %/%/%. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que las tres vistas devuelvan lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.',
            FILAS_VENT, FILAS_PM, FILAS_TX, n_v, n_pm, n_tx;
    ELSE
        IF h_v <> HUELLA_VENT THEN
            RAISE EXCEPTION 'ABORTA: la huella de v_ventas_ventanas es % y antes era %.', h_v, HUELLA_VENT;
        END IF;
        IF h_pm <> HUELLA_PM THEN
            RAISE EXCEPTION 'ABORTA: la huella de v_rentabilidad_producto_mes es % y antes era %.', h_pm, HUELLA_PM;
        END IF;
        IF h_tx <> HUELLA_TX THEN
            RAISE EXCEPTION 'ABORTA: la huella de v_rentabilidad_transacciones es % y antes era %.', h_tx, HUELLA_TX;
        END IF;
    END IF;

    RAISE NOTICE 'Testigo OK. ventanas=% filas (huella %), producto_mes=% (huella %), transacciones=% (huella %). Sin restos _viejo, contratos y tipos intactos, indices unicos puestos.',
        n_v, h_v, n_pm, h_pm, n_tx, h_tx;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · las dos copias, en las dos direcciones -------------
DO $puerta_anon$
DECLARE
    n1 bigint; n2 bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_ventas_ventanas' INTO n1;
    EXECUTE 'SELECT count(*) FROM public.mv_rentabilidad_sku' INTO n2;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO las copias (% y % filas). Un DROP+CREATE PIERDE el ACL y el objeto renace con el default de Supabase: si el revoke de arriba no hubiera corrido, esto seria una puerta nueva a los euros del negocio.', n1, n2;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA en las dos copias.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n1 bigint; n2 bigint; m1 bigint; m2 bigint;
BEGIN
    SELECT count(*) INTO m1 FROM mv_ventas_ventanas;
    SELECT count(*) INTO m2 FROM mv_rentabilidad_sku;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_ventas_ventanas' INTO n1;
    EXECUTE 'SELECT count(*) FROM public.mv_rentabilidad_sku' INTO n2;
    RESET ROLE;
    IF n1 <> m1 OR n2 <> m2 THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve %/% y las copias tienen %/%.', n1, n2, m1, m2;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % y % filas.', n1, n2;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer las copias. Las pantallas de Inventario y Rentabilidad se quedarian vacias.';
END
$puerta_auth$;
