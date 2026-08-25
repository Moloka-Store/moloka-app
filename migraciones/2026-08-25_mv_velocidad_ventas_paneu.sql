-- ============================================================================
-- MIGRACION · `v_velocidad_ventas_paneu` deja de recorrer las transacciones en cada carga
-- ----------------------------------------------------------------------------
-- 🔬 LO QUE CUESTA HOY, con el rol de la app sobre llamadas reales:
--      81 llamadas · media 748 ms · minimo 15 ms · 1.643 buffers por llamada
--    13 MB leidos, x2 por el conteo exacto de PostgREST, para devolver 211 filas.
--    Es la mas barata de la tanda, y aun asi cada carga recorre `transacciones_
--    movimientos` entera para quedarse con los ultimos 30 dias.
--
-- 🔴 EL REPARTO ES EL MISMO QUE EN `mv_ventas_ventanas`, Y POR EL MISMO MOTIVO:
--    `dias_desde_ultimo_dato` es `CURRENT_DATE - ventana_hasta`. Depende del RELOJ,
--    no del dato. Congelado, diria "hace 0 dias" para siempre -- justo la cifra que
--    existe para avisar de que el dato es viejo. Se queda VIVO en la vista de
--    encima; las 16 columnas estables van a la copia.
--    ⚠️ Y es la ULTIMA columna del contrato (la 17.a), asi que la vista puede
--       seleccionar las 16 de la copia y calcularla al final sin mover el orden.
--
-- 🔒 CLAVE UNICA POR CONSTRUCCION: la vista es un `GROUP BY asin`. Medido: 211
--    filas, 211 ASIN distintos. Y `asin` no puede ser nulo -- viene de
--    `sku_asin`, que exige `asin IS NOT NULL AND btrim(asin) <> ''`.
--
-- 🔑 DOS FUENTES, DOS ANCLAS. `transacciones_movimientos` (de donde salen las
--    ventas) y `listings_amazon` (el mapa SKU->ASIN). Las dos con gancho ya puesto.
--    `ventana_hasta` YA es el ancla de transacciones --es su `max(fecha)`-- y esta
--    en el contrato; la de listings hay que anadirla como columna de la copia.
--    ⚠️ `listings_amazon` no es adorno: si entra un informe de listings y no se
--       refresca, las ventas de un SKU nuevo dejan de sumarse a su ASIN y la
--       velocidad sale BAJA -- que es peor que salir a cero, porque parece un dato.
--    Hoy: transacciones 2026-08-23, listings 2026-08-24.
--
-- 🔬 HUELLA MEDIDA EN PRODUCCION sobre las 16 columnas estables: 211 filas,
--    md5 = 2dcc1c8682ee10382eece0f7b57f37fe.
-- ============================================================================

DO $guardas$
DECLARE
    k char; n bigint; n_dist bigint; cols text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid='public.v_velocidad_ventas_paneu'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_velocidad_ventas_paneu tiene relkind=%. Si ya es materializada, esta migracion ya corrio.', k;
    END IF;
    IF to_regclass('public.mv_velocidad_ventas_paneu') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_velocidad_ventas_paneu YA existe.';
    END IF;

    SELECT count(*), count(DISTINCT asin) INTO n, n_dist FROM v_velocidad_ventas_paneu;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas todo lo de abajo sale bien sin medir nada.';
    END IF;
    IF n <> n_dist THEN
        RAISE EXCEPTION 'ABORTA: % filas y % ASIN distintos.', n, n_dist;
    END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_velocidad_ventas_paneu';
    IF cols <> 'asin:text,uds_30d_es:bigint,uds_30d_it:bigint,uds_30d_fr:bigint,uds_30d_de:bigint,uds_30d_total:bigint,vel_dia_total:numeric,eur_30d_total:numeric,uds_7d_es:bigint,uds_7d_it:bigint,uds_7d_fr:bigint,uds_7d_de:bigint,uds_7d_total:bigint,ventana_desde:date,ventana_7d_desde:date,ventana_hasta:date,dias_desde_ultimo_dato:integer' THEN
        RAISE EXCEPTION 'ABORTA: v_velocidad_ventas_paneu no tiene el contrato esperado. Ahora: %', cols;
    END IF;
    RAISE NOTICE 'Guardas OK. % filas, % ASIN distintos, contrato de 17 columnas.', n, n_dist;
END
$guardas$;

CREATE MATERIALIZED VIEW public.mv_velocidad_ventas_paneu AS
 WITH ventana AS (
         SELECT max(transacciones_movimientos.fecha) AS hasta,
            (max(transacciones_movimientos.fecha) - '30 days'::interval)::date AS desde_30,
            (max(transacciones_movimientos.fecha) - '7 days'::interval)::date AS desde_7
           FROM transacciones_movimientos
        ), sku_asin AS (
         SELECT DISTINCT ON ((btrim(listings_amazon.seller_sku))) btrim(listings_amazon.seller_sku) AS sku,
            btrim(listings_amazon.asin) AS asin
           FROM listings_amazon
          WHERE listings_amazon.seller_sku IS NOT NULL AND listings_amazon.asin IS NOT NULL AND btrim(listings_amazon.asin) <> ''::text
          ORDER BY (btrim(listings_amazon.seller_sku)), listings_amazon.fecha_informe DESC
        ), ventas AS (
         SELECT sa.asin,
            t.pais,
            t.cantidad,
            t.ventas_producto,
            t.fecha
           FROM transacciones_movimientos t
             JOIN ventana v ON t.fecha > v.desde_30
             JOIN sku_asin sa ON sa.sku = btrim(t.sku)
          WHERE t.tipo_norm = 'pedido'::text
        )
 SELECT asin,
    COALESCE(sum(cantidad) FILTER (WHERE pais = 'ES'::text), 0::bigint) AS uds_30d_es,
    COALESCE(sum(cantidad) FILTER (WHERE pais = 'IT'::text), 0::bigint) AS uds_30d_it,
    COALESCE(sum(cantidad) FILTER (WHERE pais = 'FR'::text), 0::bigint) AS uds_30d_fr,
    COALESCE(sum(cantidad) FILTER (WHERE pais = 'DE'::text), 0::bigint) AS uds_30d_de,
    sum(cantidad) AS uds_30d_total,
    round(sum(cantidad)::numeric / 30::numeric, 2) AS vel_dia_total,
    round(sum(ventas_producto), 2) AS eur_30d_total,
    COALESCE(sum(cantidad) FILTER (WHERE fecha > (( SELECT ventana.desde_7
           FROM ventana)) AND pais = 'ES'::text), 0::bigint) AS uds_7d_es,
    COALESCE(sum(cantidad) FILTER (WHERE fecha > (( SELECT ventana.desde_7
           FROM ventana)) AND pais = 'IT'::text), 0::bigint) AS uds_7d_it,
    COALESCE(sum(cantidad) FILTER (WHERE fecha > (( SELECT ventana.desde_7
           FROM ventana)) AND pais = 'FR'::text), 0::bigint) AS uds_7d_fr,
    COALESCE(sum(cantidad) FILTER (WHERE fecha > (( SELECT ventana.desde_7
           FROM ventana)) AND pais = 'DE'::text), 0::bigint) AS uds_7d_de,
    COALESCE(sum(cantidad) FILTER (WHERE fecha > (( SELECT ventana.desde_7
           FROM ventana))), 0::bigint) AS uds_7d_total,
    ( SELECT ventana.desde_30
           FROM ventana) AS ventana_desde,
    ( SELECT ventana.desde_7
           FROM ventana) AS ventana_7d_desde,
    -- 🔑 EL ANCLA DE TRANSACCIONES. Ya estaba en el contrato: es su `max(fecha)`.
    ( SELECT ventana.hasta
           FROM ventana) AS ventana_hasta,
    -- 🔑 LA ANCLA DE LISTINGS, que NO estaba y hace falta: es el mapa SKU->ASIN. Si
    --    entra un informe suyo y esta copia no se refresca, las ventas de un SKU
    --    nuevo dejan de sumarse a su ASIN y la velocidad sale BAJA -- peor que salir
    --    a cero, porque parece un dato.
    ( SELECT max(listings_amazon.fecha_informe)
           FROM listings_amazon) AS ventana_hasta_listings,
    -- 🔒 Cuando se refresco ESTA copia. No sale a la vista: el contrato son 17 columnas.
    clock_timestamp() AS refrescada_el
   FROM ventas
  GROUP BY asin
WITH DATA;

CREATE UNIQUE INDEX mv_velocidad_ventas_paneu_uk ON public.mv_velocidad_ventas_paneu (asin);

-- 🔴 LA PUERTA. Una copia NO aplica RLS: el GRANT es la unica puerta. Aqui van los
--    EUROS y las unidades vendidas por pais. Se revoca por rol y por su nombre ANTES
--    de conceder: un `revoke ... from public` no quita los grants explicitos que el
--    default de Supabase da a `anon` y `authenticated`.
REVOKE ALL ON public.mv_velocidad_ventas_paneu FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_velocidad_ventas_paneu TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_velocidad_ventas_paneu IS
    'Velocidad de venta por ASIN y pais (30 y 7 dias), materializada el 25-ago-2026. `dias_desde_ultimo_dato` NO esta aqui a proposito: depende del RELOJ y se calcula en vivo en v_velocidad_ventas_paneu -- congelada diria "hace 0 dias" para siempre, que es justo la cifra que existe para avisar de que el dato es viejo. Dos anclas: ventana_hasta (transacciones) y ventana_hasta_listings (el mapa SKU->ASIN). Se refresca desde procesador_transacciones.py y procesador_all_listings.py.';

-- 🔒 La vista: las 16 estables de la copia y la 17.a calculada EN VIVO, al final,
--    que es donde estaba. Mismo nombre, mismo OID, mismo contrato.
CREATE OR REPLACE VIEW public.v_velocidad_ventas_paneu AS
 SELECT asin,
    uds_30d_es,
    uds_30d_it,
    uds_30d_fr,
    uds_30d_de,
    uds_30d_total,
    vel_dia_total,
    eur_30d_total,
    uds_7d_es,
    uds_7d_it,
    uds_7d_fr,
    uds_7d_de,
    uds_7d_total,
    ventana_desde,
    ventana_7d_desde,
    ventana_hasta,
    CURRENT_DATE - ventana_hasta AS dias_desde_ultimo_dato
   FROM mv_velocidad_ventas_paneu;

DO $testigo$
DECLARE
    HUELLA constant text := '2dcc1c8682ee10382eece0f7b57f37fe';
    FILAS  constant bigint := 211;
    n bigint; h text; cols text;
    a_t date; f_t date; a_l timestamptz; f_l timestamptz; n_dias int;
BEGIN
    SELECT count(*) INTO n FROM v_velocidad_ventas_paneu;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.'; END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_velocidad_ventas_paneu';
    IF cols <> 'asin:text,uds_30d_es:bigint,uds_30d_it:bigint,uds_30d_fr:bigint,uds_30d_de:bigint,uds_30d_total:bigint,vel_dia_total:numeric,eur_30d_total:numeric,uds_7d_es:bigint,uds_7d_it:bigint,uds_7d_fr:bigint,uds_7d_de:bigint,uds_7d_total:bigint,ventana_desde:date,ventana_7d_desde:date,ventana_hasta:date,dias_desde_ultimo_dato:integer' THEN
        RAISE EXCEPTION 'ABORTA: el contrato ha cambiado. Ahora: %', cols;
    END IF;

    -- 🔴 LA COLUMNA DEL RELOJ SE QUEDA FUERA DE LA COPIA. Si estuviera dentro, se
    --    congelaria y diria "hace 0 dias" para siempre. Anclado sobre lo que NO debe
    --    aparecer, que es la mitad que se mueve.
    IF EXISTS (SELECT 1 FROM pg_attribute
                WHERE attrelid='public.mv_velocidad_ventas_paneu'::regclass
                  AND attname='dias_desde_ultimo_dato' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: dias_desde_ultimo_dato se ha colado DENTRO de la copia. Congelada diria "hace 0 dias" para siempre.';
    END IF;
    -- 🔒 Y que la vista SI la calcule: si se cayera del SELECT, el contrato de arriba
    --    ya habria abortado; esto comprueba que ademas da un numero coherente.
    SELECT max(dias_desde_ultimo_dato) INTO n_dias FROM v_velocidad_ventas_paneu;
    IF n_dias IS NULL OR n_dias < 0 THEN
        RAISE EXCEPTION 'ABORTA: dias_desde_ultimo_dato da % -- no puede ser nulo ni negativo.', n_dias;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_velocidad_ventas_paneu'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: la copia no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;
    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las materializadas.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid='public.mv_velocidad_ventas_paneu'::regclass
                      AND attname='refrescada_el' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: la copia se ha quedado sin refrescada_el.';
    END IF;

    SELECT max(ventana_hasta), max(ventana_hasta_listings) INTO a_t, a_l FROM mv_velocidad_ventas_paneu;
    SELECT max(fecha) INTO f_t FROM transacciones_movimientos;
    SELECT max(fecha_informe) INTO f_l FROM listings_amazon;
    IF a_t IS DISTINCT FROM f_t OR a_l IS DISTINCT FROM f_l THEN
        RAISE EXCEPTION 'ABORTA: las anclas de la copia dicen %/% y las fuentes %/%. Recien creadas tienen que cuadrar.', a_t, a_l, f_t, f_l;
    END IF;

    SELECT md5(string_agg(t::text,'|' ORDER BY t.asin)) INTO h FROM (
        SELECT asin,uds_30d_es,uds_30d_it,uds_30d_fr,uds_30d_de,uds_30d_total,vel_dia_total,
               eur_30d_total,uds_7d_es,uds_7d_it,uds_7d_fr,uds_7d_de,uds_7d_total,
               ventana_desde,ventana_7d_desde,ventana_hasta FROM v_velocidad_ventas_paneu) t;
    IF n <> FILAS THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que la vista devuelva lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS, n;
    ELSIF h <> HUELLA THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y antes era %. Se ha movido un numero.', h, HUELLA;
    END IF;

    RAISE NOTICE 'Testigo OK. % filas (huella %), contrato de 17 columnas intacto, el reloj FUERA de la copia (hoy da % dias), indice unico puesto, anclas cuadrando en % y %.', n, h, n_dias, a_t, a_l;
END
$testigo$;

DO $puerta_anon$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_velocidad_ventas_paneu' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_velocidad_ventas_paneu y ha contado % filas. Ahi van los euros y las unidades vendidas por pais, y hoy anon no llega por ningun camino.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_velocidad_ventas_paneu.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE n bigint; m bigint;
BEGIN
    SELECT count(*) INTO m FROM mv_velocidad_ventas_paneu;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_velocidad_ventas_paneu' INTO n;
    RESET ROLE;
    IF n <> m THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la copia tiene %.', n, m;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_velocidad_ventas_paneu. La velocidad de venta se quedaria vacia en la pantalla.';
END
$puerta_auth$;
