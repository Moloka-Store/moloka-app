-- ============================================================================
-- MIGRACION · `v_demanda_asin_ultima` deja de rebobinar la serie en cada carga
-- ----------------------------------------------------------------------------
-- 🔬 LO QUE CUESTA HOY, con el rol de la app sobre llamadas reales:
--      85 llamadas · media 1.032 ms · minimo 52 ms · 3.047 buffers por llamada
--    24 MB leidos, x2 por el conteo exacto de PostgREST, para devolver 742 filas.
--    El coste es que la vista ORDENA LA SERIE ENTERA de `demanda_asin` --cinco
--    funciones de ventana particionadas por (pais, asin)-- solo para quedarse con
--    la ultima lectura de cada una. Y esa serie SOLO CRECE.
--
-- 🔒 NO HAY REPARTO: una sola tabla, sin joins, sin funciones y sin `CURRENT_DATE`.
--    Lo que devuelve cambia exactamente cuando entra un informe de Custom Analytics,
--    que es cuando se refresca. La copia es la vista entera.
--
-- 🔒 CLAVE UNICA POR CONSTRUCCION: la vista filtra `rn = 1` sobre un
--    `row_number() OVER (PARTITION BY pais, asin ...)`, asi que hay EXACTAMENTE una
--    fila por pareja. No es que hoy no se repita: es que no puede.
--    Medido igualmente: 742 filas, 742 parejas distintas, 0 nulos en la clave.
--
-- 🔑 UNA FUENTE, UNA ANCLA -- Y ESTRENA GANCHO. `demanda_asin` la escribe
--    `procesador_custom_analytics.py`, que hasta hoy NO llamaba a `refrescar_vistas`.
--    Se le pone, con fuente `custom_analytics`.
--    ⚠️ Y eso significa que ademas empieza a poner al dia la copia del Trackeador al
--       final de su corrida, como el resto -- que es lo que se quiere: su pantalla
--       tambien mira la demanda.
--    El ancla es `leido_at`, que YA es columna del contrato. Aun asi viaja tambien
--    como columna propia de la copia (`hasta_demanda`), y no es redundante: la del
--    contrato es un dato POR FILA --la lectura de ESE (pais, asin)-- y el ancla es
--    el corte GLOBAL de la tabla. Un pais que deje de aparecer en el fichero dejaria
--    su `leido_at` viejo para siempre, y el max() de la vista seguiria siendo el
--    bueno solo por casualidad.
--
-- 🔬 HUELLA MEDIDA EN PRODUCCION sobre las 23 columnas: 742 filas,
--    md5 = 099c433a44a0bb486f8806a728215f52. Ancla: 2026-08-20 16:42:44.653+00.
-- ============================================================================

DO $guardas$
DECLARE
    k char; n bigint; n_dist bigint; n_nulos bigint; cols text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid='public.v_demanda_asin_ultima'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_demanda_asin_ultima tiene relkind=%. Si ya es materializada, esta migracion ya corrio.', k;
    END IF;
    IF to_regclass('public.mv_demanda_asin_ultima') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_demanda_asin_ultima YA existe.';
    END IF;

    SELECT count(*), count(DISTINCT (pais, asin)),
           count(*) FILTER (WHERE pais IS NULL OR asin IS NULL)
      INTO n, n_dist, n_nulos FROM v_demanda_asin_ultima;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas todo lo de abajo sale bien sin medir nada.';
    END IF;
    IF n <> n_dist THEN
        RAISE EXCEPTION 'ABORTA: % filas y % parejas (pais, asin) distintas.', n, n_dist;
    END IF;
    -- 🔴 Un indice unico NO enforca sobre NULL: cada NULL es distinto de los demas, y el
    --    refresco sin bloquear usa ese indice para casar filas. Si hubiera nulos en la
    --    clave habria que meter un centinela, como en mv_rentabilidad_sku.
    IF n_nulos > 0 THEN
        RAISE EXCEPTION 'ABORTA: % fila(s) con pais o asin NULO. La clave del indice unico no valdria.', n_nulos;
    END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_demanda_asin_ultima';
    IF cols <> 'pais:text,asin:text,nombre_producto:text,leido_at:timestamp with time zone,leido_anterior:timestamp with time zone,visitas:integer,sesiones:integer,unidades_pedidas:integer,unidades_enviadas:integer,ventas_enviadas_eur:numeric,facturacion_pedida_eur:numeric,precio_venta_medio:numeric,buybox_ratio:numeric,buybox_visiones:integer,conversion:numeric,reembolsos_ratio:numeric,resenas:integer,estrellas:numeric,visitas_periodo:integer,sesiones_periodo:integer,uds_periodo:integer,ventas_periodo:numeric,procesado_at:timestamp with time zone' THEN
        RAISE EXCEPTION 'ABORTA: v_demanda_asin_ultima no tiene el contrato esperado. Ahora: %', cols;
    END IF;
    RAISE NOTICE 'Guardas OK. % filas, % parejas distintas, 0 nulos en la clave, contrato de 23 columnas.', n, n_dist;
END
$guardas$;

CREATE MATERIALIZED VIEW public.mv_demanda_asin_ultima AS
 WITH ranked AS (
         SELECT d.pais,
            d.asin,
            d.nombre_producto,
            d.resenas,
            d.estrellas,
            d.visitas,
            d.sesiones,
            d.conversion,
            d.unidades_pedidas,
            d.unidades_enviadas,
            d.precio_venta_medio,
            d.ventas_enviadas_eur,
            d.facturacion_pedida_eur,
            d.buybox_ratio,
            d.buybox_visiones,
            d.reembolsos_ratio,
            d.leido_at,
            d.procesado_at,
            row_number() OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at DESC) AS rn,
            lag(d.leido_at) OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at) AS leido_anterior,
            lag(d.visitas) OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at) AS visitas_ant,
            lag(d.sesiones) OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at) AS sesiones_ant,
            lag(d.unidades_pedidas) OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at) AS uds_ant,
            lag(d.ventas_enviadas_eur) OVER (PARTITION BY d.pais, d.asin ORDER BY d.leido_at) AS ventas_ant
           FROM demanda_asin d
        )
 SELECT pais,
    asin,
    nombre_producto,
    leido_at,
    leido_anterior,
    visitas,
    sesiones,
    unidades_pedidas,
    unidades_enviadas,
    ventas_enviadas_eur,
    facturacion_pedida_eur,
    precio_venta_medio,
    buybox_ratio,
    buybox_visiones,
    conversion,
    reembolsos_ratio,
    resenas,
    estrellas,
        CASE
            WHEN visitas >= visitas_ant THEN visitas - visitas_ant
            ELSE NULL::integer
        END AS visitas_periodo,
        CASE
            WHEN sesiones >= sesiones_ant THEN sesiones - sesiones_ant
            ELSE NULL::integer
        END AS sesiones_periodo,
        CASE
            WHEN unidades_pedidas >= uds_ant THEN unidades_pedidas - uds_ant
            ELSE NULL::integer
        END AS uds_periodo,
        CASE
            WHEN ventas_enviadas_eur >= ventas_ant THEN ventas_enviadas_eur - ventas_ant
            ELSE NULL::numeric
        END AS ventas_periodo,
    procesado_at,
    -- 🔑 EL ANCLA, y NO es lo mismo que la columna `leido_at` de al lado. Esa es un
    --    dato POR FILA --cuando se leyo ESE (pais, asin)--; esta es el corte GLOBAL
    --    de la tabla. Un pais que deje de aparecer en el fichero se quedaria con su
    --    `leido_at` viejo para siempre, y el max() de la vista seguiria siendo el
    --    bueno solo por casualidad. El centinela necesita el corte, no el maximo de
    --    lo que haya sobrevivido.
    ( SELECT max(demanda_asin.leido_at) FROM demanda_asin) AS hasta_demanda,
    -- 🔒 Cuando se refresco ESTA copia. No sale a la vista: el contrato son 23 columnas.
    clock_timestamp() AS refrescada_el
   FROM ranked
  WHERE rn = 1
WITH DATA;

CREATE UNIQUE INDEX mv_demanda_asin_ultima_uk ON public.mv_demanda_asin_ultima (pais, asin);

-- 🔴 LA PUERTA. Una copia NO aplica RLS: el GRANT es la unica puerta. `demanda_asin`
--    tiene RLS y su unica politica es para `authenticated`, asi que hoy `anon` no
--    llega. Aqui van las visitas, la conversion y la facturacion por ASIN. Se revoca
--    por rol y por su nombre ANTES de conceder.
REVOKE ALL ON public.mv_demanda_asin_ultima FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_demanda_asin_ultima TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_demanda_asin_ultima IS
    'Ultima lectura de demanda por (pais, ASIN), materializada el 25-ago-2026: la vista ordenaba la SERIE ENTERA de demanda_asin --cinco funciones de ventana-- en cada carga solo para quedarse con rn=1, y esa serie solo crece. `hasta_demanda` es el ancla del centinela (el corte GLOBAL de la tabla, que NO es lo mismo que el leido_at de cada fila) y `refrescada_el` dice cuando se refresco. Se refresca desde procesador_custom_analytics.py.';

CREATE OR REPLACE VIEW public.v_demanda_asin_ultima AS
 SELECT pais, asin, nombre_producto, leido_at, leido_anterior, visitas, sesiones,
    unidades_pedidas, unidades_enviadas, ventas_enviadas_eur, facturacion_pedida_eur,
    precio_venta_medio, buybox_ratio, buybox_visiones, conversion, reembolsos_ratio,
    resenas, estrellas, visitas_periodo, sesiones_periodo, uds_periodo, ventas_periodo,
    procesado_at
   FROM mv_demanda_asin_ultima;

DO $testigo$
DECLARE
    HUELLA constant text := '099c433a44a0bb486f8806a728215f52';
    FILAS  constant bigint := 742;
    n bigint; h text; cols text; a timestamptz; f timestamptz;
BEGIN
    SELECT count(*) INTO n FROM v_demanda_asin_ultima;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.'; END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_demanda_asin_ultima';
    IF cols <> 'pais:text,asin:text,nombre_producto:text,leido_at:timestamp with time zone,leido_anterior:timestamp with time zone,visitas:integer,sesiones:integer,unidades_pedidas:integer,unidades_enviadas:integer,ventas_enviadas_eur:numeric,facturacion_pedida_eur:numeric,precio_venta_medio:numeric,buybox_ratio:numeric,buybox_visiones:integer,conversion:numeric,reembolsos_ratio:numeric,resenas:integer,estrellas:numeric,visitas_periodo:integer,sesiones_periodo:integer,uds_periodo:integer,ventas_periodo:numeric,procesado_at:timestamp with time zone' THEN
        RAISE EXCEPTION 'ABORTA: el contrato ha cambiado. Ahora: %', cols;
    END IF;
    -- 🔒 Anclado sobre lo que NO debe aparecer: las dos columnas de diagnostico viven
    --    en la copia; en la vista cambiarian el contrato y la app las veria.
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='v_demanda_asin_ultima'
                  AND column_name IN ('hasta_demanda','refrescada_el')) THEN
        RAISE EXCEPTION 'ABORTA: hasta_demanda o refrescada_el se han colado en la VISTA.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_demanda_asin_ultima'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: la copia no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;
    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las materializadas.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid='public.mv_demanda_asin_ultima'::regclass
                      AND attname='refrescada_el' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: la copia se ha quedado sin refrescada_el.';
    END IF;

    SELECT max(hasta_demanda) INTO a FROM mv_demanda_asin_ultima;
    SELECT max(leido_at) INTO f FROM demanda_asin;
    IF a IS DISTINCT FROM f THEN
        RAISE EXCEPTION 'ABORTA: el ancla de la copia dice % y la fuente %. Recien creada tiene que cuadrar.', a, f;
    END IF;

    SELECT md5(string_agg(t::text,'|' ORDER BY t.pais, t.asin)) INTO h FROM (
        SELECT pais,asin,nombre_producto,leido_at,leido_anterior,visitas,sesiones,unidades_pedidas,
               unidades_enviadas,ventas_enviadas_eur,facturacion_pedida_eur,precio_venta_medio,
               buybox_ratio,buybox_visiones,conversion,reembolsos_ratio,resenas,estrellas,
               visitas_periodo,sesiones_periodo,uds_periodo,ventas_periodo,procesado_at
          FROM v_demanda_asin_ultima) t;
    IF n <> FILAS THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que la vista devuelva lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS, n;
    ELSIF h <> HUELLA THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y antes era %. Se ha movido un numero.', h, HUELLA;
    END IF;

    RAISE NOTICE 'Testigo OK. % filas (huella %), contrato de 23 columnas intacto, indice unico puesto, ancla cuadrando en %.', n, h, a;
END
$testigo$;

DO $puerta_anon$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_demanda_asin_ultima' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_demanda_asin_ultima y ha contado % filas. Ahi van las visitas, la conversion y la facturacion por ASIN, y hoy anon no llega por ningun camino.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_demanda_asin_ultima.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE n bigint; m bigint;
BEGIN
    SELECT count(*) INTO m FROM mv_demanda_asin_ultima;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_demanda_asin_ultima' INTO n;
    RESET ROLE;
    IF n <> m THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la copia tiene %.', n, m;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_demanda_asin_ultima. La demanda se quedaria vacia en la pantalla.';
END
$puerta_auth$;
