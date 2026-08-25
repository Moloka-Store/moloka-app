-- ============================================================================
-- MIGRACION · `v_nunca_enviado_fba`: se materializa la rama CARA, no la vista
-- ----------------------------------------------------------------------------
-- 🔬 LO QUE CUESTA HOY, con el rol de la app sobre llamadas reales:
--      75 llamadas · media 2.181 ms · minimo 71 ms · 5.216 buffers por llamada
--    41 MB leidos, x2 por el conteo exacto de PostgREST, para devolver 417 filas.
--
-- 🔴 AQUI EL REPARTO NO SE DECIDE, SE MIDE -- y el plan lo deja en evidencia.
--    La vista cruza CINCO fuentes, y el coste NO esta repartido entre ellas:
--
--      rama                             buffers   volatil?
--      transacciones x listings           5.512    no  (dos informes)
--      salud_fba_historico                   54    no
--      ledger_movimientos                    48    no
--      productos                             42    SI  (manda las filas)
--      envios_fba (jsonb)                    30    SI  (Elena crea envios)
--
--    🔑 EL 97% DEL COSTE ES UNA SOLA RAMA, y las dos volatiles cuestan 72 buffers
--       ENTRE LAS DOS. O sea que no hay que elegir entre velocidad y frescura:
--       se materializa la rama cara y TODO LO VOLATIL SE QUEDA VIVO.
--
--    ⚠️ Y esto NO se podia saber sin mirar el plan. La lectura facil --"son cinco
--       fuentes, materializo la vista entera"-- habria congelado `envios_fba`: en
--       cuanto Elena preparase un envio con un ASIN nuevo, la pantalla seguiria
--       diciendo "nunca enviado" hasta el siguiente refresco. Cifra falsa, y por
--       ahorrar 30 buffers de 5.686.
--
-- 🔒 LA COPIA ES UNA LISTA, NO UNA VISTA: los ASIN que alguna vez tuvieron un
--    pedido de marketplace. `mv_asin_con_pedido` se llama por lo que contiene, no
--    por la vista a la que sirve -- manana puede servir a otra.
--
-- 🔒 CLAVE UNICA POR CONSTRUCCION: es un `SELECT DISTINCT`, asi que no puede
--    repetirse. Y no admite NULL (`la.asin IS NOT NULL`). Medido: 324 filas, 0
--    nulos, 0 cadenas vacias -- no hace falta centinela de vacio.
--
-- 🔑 DOS FUENTES, DOS ANCLAS: `transacciones_movimientos` y `listings_amazon`, las
--    dos con gancho ya puesto en su procesador. Las dos anclas viajan como columnas
--    de la copia --son constantes en todas sus filas-- para que el centinela lea el
--    corte que declara LA COPIA y lo compare con el `max()` de cada TABLA. Hoy:
--    transacciones 2026-08-23, listings 2026-08-24.
--    ⚠️ `listings_amazon` NO es adorno aqui: es el mapa SKU->ASIN. Si entra un
--       informe de listings y no se refresca, un SKU que cambia de ASIN deja de
--       contar como "tuvo pedido" y su ficha aparece como NUNCA ENVIADA.
--
-- 🔬 HUELLA MEDIDA EN PRODUCCION: 417 filas, 50 de ellas nunca enviadas,
--    md5 = 1ae363a41926a3b7242fa20542b1948e.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k char; n bigint; n_mv bigint; n_dist bigint; cols text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid = 'public.v_nunca_enviado_fba'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_nunca_enviado_fba tiene relkind=%. Si ya es materializada, esta migracion ya corrio.', k;
    END IF;
    IF to_regclass('public.mv_asin_con_pedido') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_asin_con_pedido YA existe.';
    END IF;

    SELECT count(*) INTO n FROM v_nunca_enviado_fba;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas todo lo de abajo sale bien sin medir nada.';
    END IF;

    SELECT count(*), count(DISTINCT a) INTO n_mv, n_dist FROM (
        SELECT btrim(la.asin) AS a
          FROM transacciones_movimientos t
          JOIN listings_amazon la ON btrim(la.seller_sku) = btrim(t.sku)
         WHERE t.tipo_norm = 'pedido'::text AND la.asin IS NOT NULL
         GROUP BY btrim(la.asin)) x;
    IF n_mv = 0 THEN
        RAISE EXCEPTION 'ABORTA: la rama de pedidos no devuelve NI UN ASIN. Con la lista vacia, TODAS las fichas saldrian como nunca enviadas.';
    END IF;
    IF n_mv <> n_dist THEN
        RAISE EXCEPTION 'ABORTA: % filas y % distintas. La clave del indice unico no seria unica.', n_mv, n_dist;
    END IF;

    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_nunca_enviado_fba';
    IF cols <> 'asin:text,nunca_enviado:boolean,historia_incierta:boolean' THEN
        RAISE EXCEPTION 'ABORTA: v_nunca_enviado_fba no tiene el contrato esperado. Ahora: %', cols;
    END IF;
    RAISE NOTICE 'Guardas OK. vista=% filas, rama de pedidos=% ASIN distintos, contrato de 3 columnas.', n, n_mv;
END
$guardas$;

-- -- 1) LA COPIA · SOLO la rama cara -----------------------------------------
CREATE MATERIALIZED VIEW public.mv_asin_con_pedido AS
SELECT v.asin,
       -- 🔑 LAS DOS ANCLAS, como columnas. Son constantes en todas las filas: es el
       --    corte que declara ESTA copia, y el centinela lo compara contra el max()
       --    de cada TABLA. Nunca contra si misma -- comparando la copia consigo
       --    misma, un refresco caido diria siempre que va al dia.
       ( SELECT max(transacciones_movimientos.fecha)
           FROM transacciones_movimientos) AS hasta_transacciones,
       ( SELECT max(listings_amazon.fecha_informe)
           FROM listings_amazon) AS hasta_listings,
       clock_timestamp() AS refrescada_el
  FROM ( SELECT DISTINCT btrim(la.asin) AS asin
           FROM transacciones_movimientos t
             JOIN listings_amazon la ON btrim(la.seller_sku) = btrim(t.sku)
          WHERE t.tipo_norm = 'pedido'::text AND la.asin IS NOT NULL) v
WITH DATA;

CREATE UNIQUE INDEX mv_asin_con_pedido_uk ON public.mv_asin_con_pedido (asin);

-- 🔴 LA PUERTA. Una copia NO aplica RLS: el GRANT es la unica puerta. Las dos
--    fuentes tienen RLS con politica solo para `authenticated`, asi que hoy `anon`
--    no llega. Se revoca por rol y por su nombre ANTES de conceder: un
--    `revoke ... from public` no quita los grants explicitos del default de Supabase.
REVOKE ALL ON public.mv_asin_con_pedido FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_asin_con_pedido TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_asin_con_pedido IS
    'ASIN que alguna vez tuvieron un pedido de marketplace, segun transacciones_movimientos cruzado con el mapa SKU->ASIN de listings_amazon. Materializada el 25-ago-2026 porque era el 97% del coste de v_nunca_enviado_fba (5.512 de 5.686 buffers). Lo demas de esa vista --productos, salud_fba_historico, ledger, envios_fba-- se queda VIVO: las dos fuentes volatiles costaban 72 buffers entre las dos, y congelarlas daria cifras falsas. Se refresca desde procesador_transacciones.py y procesador_all_listings.py.';

-- -- 2) LA VISTA · mismo nombre, mismo OID, mismas 3 columnas -----------------
CREATE OR REPLACE VIEW public.v_nunca_enviado_fba AS
 WITH cat AS (
         -- 🔴 EN VIVO: `productos` manda QUE FILAS tiene la vista. Congelarlo haria
         --    que una ficha nueva no apareciera hasta el siguiente refresco.
         SELECT btrim(productos.asin) AS asin,
            bool_or(productos.historia_previa_desconocida) AS incierta
           FROM productos
          WHERE productos.asin IS NOT NULL AND btrim(productos.asin) <> ''::text
          GROUP BY (btrim(productos.asin))
        ), vistos AS (
         SELECT DISTINCT btrim(salud_fba_historico.asin) AS asin
           FROM salud_fba_historico
          WHERE salud_fba_historico.asin IS NOT NULL
        UNION
         SELECT DISTINCT btrim(ledger_movimientos.asin) AS btrim
           FROM ledger_movimientos
          WHERE ledger_movimientos.asin IS NOT NULL
        UNION
         -- 🔒 LA RAMA CARA, YA CALCULADA. Era 5.512 de los 5.686 buffers.
         SELECT mv_asin_con_pedido.asin
           FROM mv_asin_con_pedido
        UNION
         -- 🔴 EN VIVO, Y ES LO QUE MAS IMPORTA DE ESTE REPARTO: `envios_fba` cambia
         --    cuando Elena prepara un envio. Si estuviera dentro de la copia, en
         --    cuanto metiera un ASIN nuevo la pantalla seguiria diciendo "nunca
         --    enviado" hasta el siguiente informe. Cuesta 30 buffers.
         SELECT DISTINCT btrim(li.value ->> 'asin'::text) AS btrim
           FROM envios_fba ef,
            LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(ef.productos) = 'array'::text THEN ef.productos
                    ELSE '[]'::jsonb
                END) li(value)
          WHERE (li.value ->> 'asin'::text) IS NOT NULL AND btrim(li.value ->> 'asin'::text) <> ''::text
        )
 SELECT c.asin,
    v.asin IS NULL AS nunca_enviado,
    c.incierta AS historia_incierta
   FROM cat c
     LEFT JOIN vistos v ON v.asin = c.asin;

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    HUELLA constant text := '1ae363a41926a3b7242fa20542b1948e';
    FILAS  constant bigint := 417;
    NUNCA  constant bigint := 50;
    n bigint; n_nunca bigint; h text; cols text;
    a_t date; f_t date; a_l timestamptz; f_l timestamptz;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE nunca_enviado) INTO n, n_nunca FROM v_nunca_enviado_fba;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.';
    END IF;

    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_nunca_enviado_fba';
    IF cols <> 'asin:text,nunca_enviado:boolean,historia_incierta:boolean' THEN
        RAISE EXCEPTION 'ABORTA: el contrato ha cambiado. Ahora: %', cols;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_asin_con_pedido'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: mv_asin_con_pedido no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;
    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las materializadas y devuelve
    --    cero filas SIN dar error, asi que un assert escrito contra el seria inerte.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid='public.mv_asin_con_pedido'::regclass
                      AND attname='refrescada_el' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: la copia se ha quedado sin refrescada_el.';
    END IF;

    -- 🔴 LAS DOS ANCLAS TIENEN QUE CUADRAR RECIEN CREADAS. Si no cuadran aqui --con la
    --    copia calculada hace un segundo-- es que no miden lo que dicen medir, y el
    --    centinela de la pantalla nacerria mintiendo en la direccion mala: callado.
    SELECT max(hasta_transacciones), max(hasta_listings) INTO a_t, a_l FROM mv_asin_con_pedido;
    SELECT max(fecha) INTO f_t FROM transacciones_movimientos;
    SELECT max(fecha_informe) INTO f_l FROM listings_amazon;
    IF a_t IS DISTINCT FROM f_t OR a_l IS DISTINCT FROM f_l THEN
        RAISE EXCEPTION 'ABORTA: las anclas de la copia dicen %/% y las fuentes %/%.', a_t, a_l, f_t, f_l;
    END IF;

    SELECT md5(string_agg(t::text, '|' ORDER BY t.asin)) INTO h FROM (
        SELECT asin, nunca_enviado, historia_incierta FROM v_nunca_enviado_fba) t;
    IF n <> FILAS THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que la vista devuelva lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS, n;
    ELSE
        IF h <> HUELLA THEN
            RAISE EXCEPTION 'ABORTA: la huella es % y antes era %. Se ha movido un numero.', h, HUELLA;
        END IF;
        -- 🔒 Y el recuento que de verdad se mira en pantalla, aparte de la huella: si
        --    la rama de pedidos se quedara fuera del UNION, esto se dispararia.
        IF n_nunca <> NUNCA THEN
            RAISE EXCEPTION 'ABORTA: % fichas salen como NUNCA ENVIADAS y antes eran %.', n_nunca, NUNCA;
        END IF;
    END IF;

    RAISE NOTICE 'Testigo OK. % filas (huella %), % nunca enviadas, contrato intacto, indice unico puesto, anclas cuadrando en % y %.', n, h, n_nunca, a_t, a_l;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · en bloques propios --------------------------------
DO $puerta_anon$
DECLARE
    n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_asin_con_pedido' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_asin_con_pedido y ha contado % filas. Hoy no llega a ese dato por ningun camino: una copia sin RLS abierta seria una puerta NUEVA.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_asin_con_pedido.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n bigint; m bigint;
BEGIN
    SELECT count(*) INTO m FROM mv_asin_con_pedido;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_asin_con_pedido' INTO n;
    RESET ROLE;
    IF n <> m THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la copia tiene %.', n, m;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_asin_con_pedido. Entonces la vista lo veria VACIO y TODAS las fichas saldrian como nunca enviadas -- que es peor que quedarse en blanco: es una cifra falsa creible.';
END
$puerta_auth$;
