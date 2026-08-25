-- ============================================================================
-- MIGRACION · `v_presencia_pais` deja de agregar el ledger entero en cada carga
-- ----------------------------------------------------------------------------
-- 🔬 LO QUE CUESTA HOY, medido con el rol de la app sobre llamadas reales:
--      66 llamadas · media 2.329 ms · minimo 118 ms · **6.430 buffers por llamada**
--    O sea 50 MB leidos cada vez que alguien abre la pantalla, para devolver 546
--    filas. Y PostgREST la evalua DOS veces --una para los datos y otra para el
--    conteo exacto--, asi que son 100 MB por carga.
--
-- 🔒 ESTA ES LA MAS LIMPIA DE LA TANDA, y conviene decir por que: NO HAY REPARTO.
--    Las otras copias tuvieron que dejar fuera lo volatil --el pvd, `productos`,
--    la fecha de hoy-- porque congelarlo daria una cifra falsa. Aqui no hay nada
--    de eso: la vista agrega `ledger_movimientos` y NADA MAS. Ni un join, ni una
--    funcion, ni `CURRENT_DATE`. Todo lo que devuelve cambia exactamente cuando
--    cambia el ledger, que es justo cuando se refresca.
--    ⇒ la copia es la vista ENTERA, y la vista de encima es un `SELECT *`.
--
-- 🔒 LA CLAVE ES UNICA POR CONSTRUCCION, no por el dato de hoy: la vista es un
--    `GROUP BY (btrim(asin)), (upper(btrim(country)))`, asi que no puede haber dos
--    filas con la misma pareja. Medido igualmente: 546 filas, 546 claves.
--    ⚠️ Y ninguna de las dos admite NULL: el `WHERE` exige `asin IS NOT NULL AND
--       btrim(asin) <> ''` y lo mismo para `country`. Sin nulos no hace falta el
--       centinela de cadena vacia que si necesito `mv_rentabilidad_sku`.
--
-- 🔑 UNA SOLA FUENTE, UNA SOLA ANCLA. `ledger_movimientos`. El gancho ya existe en
--    `procesador_ledger.py`; aqui solo se anade esta copia a su lista.
--    Y el ancla NO hay que inventarla: `ledger_hasta` YA es una columna del
--    contrato --es `max(ledger_movimientos.fecha)`--, asi que el centinela compara
--    esa columna de la COPIA contra el `max(fecha)` de la TABLA. Hoy las dos dicen
--    2026-08-24.
--
-- 🔬 HUELLA MEDIDA EN PRODUCCION antes de tocar nada: 546 filas,
--    md5 = 32a0f90c23fefb03c589673880fc176d sobre las ocho columnas.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k char; n bigint; n_claves bigint; cols text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid = 'public.v_presencia_pais'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_presencia_pais tiene relkind=%. Si ya es materializada, esta migracion ya corrio y el ensayo no probaria nada.', k;
    END IF;
    IF to_regclass('public.mv_presencia_pais') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_presencia_pais YA existe.';
    END IF;

    SELECT count(*), count(DISTINCT (asin, pais)) INTO n, n_claves FROM v_presencia_pais;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas cualquier comprobacion de abajo sale bien sin medir nada.';
    END IF;
    -- 🔴 La unicidad es lo que permite refrescar sin bloquear a quien este leyendo.
    --    Se mide aunque el GROUP BY la garantice: si algun dia alguien anade una
    --    columna al SELECT sin anadirla al GROUP BY, esto lo caza antes que el indice.
    IF n <> n_claves THEN
        RAISE EXCEPTION 'ABORTA: % filas y solo % claves (asin, pais) distintas.', n, n_claves;
    END IF;

    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_presencia_pais';
    IF cols <> 'asin:text,pais:text,uds_recibidas:bigint,uds_vendidas:bigint,primer_movimiento:date,ultimo_movimiento:date,ledger_desde:date,ledger_hasta:date' THEN
        RAISE EXCEPTION 'ABORTA: v_presencia_pais no tiene el contrato esperado. Ahora: %', cols;
    END IF;
    RAISE NOTICE 'Guardas OK. % filas, % claves distintas, contrato de 8 columnas.', n, n_claves;
END
$guardas$;

-- -- 1) LA COPIA · la vista entera, porque no hay nada volatil que dejar fuera --
CREATE MATERIALIZED VIEW public.mv_presencia_pais AS
 WITH ventana AS (
         SELECT min(ledger_movimientos.fecha) AS desde,
            max(ledger_movimientos.fecha) AS hasta
           FROM ledger_movimientos
        )
 SELECT btrim(asin) AS asin,
    upper(btrim(country)) AS pais,
    COALESCE(sum(quantity) FILTER (WHERE (event_type = ANY (ARRAY['WhseTransfers'::text, 'Receipts'::text])) AND quantity > 0), 0::bigint) AS uds_recibidas,
    COALESCE(- sum(quantity) FILTER (WHERE event_type = 'Shipments'::text AND quantity < 0), 0::bigint) AS uds_vendidas,
    min(fecha) AS primer_movimiento,
    max(fecha) AS ultimo_movimiento,
    ( SELECT ventana.desde
           FROM ventana) AS ledger_desde,
    -- 🔑 EL ANCLA DEL CENTINELA. Es `max(ledger_movimientos.fecha)`, o sea el corte
    --    que declara la COPIA. Se compara contra el `max(fecha)` de la TABLA, nunca
    --    contra si misma: comparando la copia consigo misma, un refresco caido diria
    --    siempre que va al dia.
    ( SELECT ventana.hasta
           FROM ventana) AS ledger_hasta,
    -- 🔒 Cuando se refresco ESTA copia. No sale a la vista: el contrato son 8 columnas.
    clock_timestamp() AS refrescada_el
   FROM ledger_movimientos l
  WHERE asin IS NOT NULL AND btrim(asin) <> ''::text AND country IS NOT NULL AND btrim(country) <> ''::text
  GROUP BY (btrim(asin)), (upper(btrim(country)))
WITH DATA;

CREATE UNIQUE INDEX mv_presencia_pais_uk ON public.mv_presencia_pais (asin, pais);

-- 🔴 LA PUERTA. Una materializada NO aplica RLS: el GRANT es la unica puerta.
--    `ledger_movimientos` tiene RLS y su unica politica es para `authenticated`, asi
--    que hoy `anon` no llega a ese dato por ningun camino. Si la copia naciera
--    abierta, el movimiento de almacen seria legible anonimamente POR PRIMERA VEZ.
--    Se revoca por rol y por su nombre antes de conceder: un `revoke ... from public`
--    NO quita los grants explicitos del default de Supabase.
REVOKE ALL ON public.mv_presencia_pais FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_presencia_pais TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_presencia_pais IS
    'Presencia por (ASIN, pais) segun el ledger, materializada el 25-ago-2026. La copia es la vista ENTERA porque aqui no hay nada volatil: agrega ledger_movimientos y nada mas, sin joins ni CURRENT_DATE. `ledger_hasta` es el ancla del centinela y `refrescada_el` (clock_timestamp) dice cuando se refresco. Se refresca desde procesador_ledger.py.';

-- -- 2) LA VISTA · mismo nombre, mismo OID, mismas 8 columnas ------------------
CREATE OR REPLACE VIEW public.v_presencia_pais AS
 SELECT asin,
    pais,
    uds_recibidas,
    uds_vendidas,
    primer_movimiento,
    ultimo_movimiento,
    ledger_desde,
    ledger_hasta
   FROM mv_presencia_pais;

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    HUELLA constant text := '32a0f90c23fefb03c589673880fc176d';
    FILAS  constant bigint := 546;
    n bigint; h text; cols text; ancla_copia date; ancla_fuente date;
BEGIN
    SELECT count(*) INTO n FROM v_presencia_pais;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.';
    END IF;

    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_presencia_pais';
    IF cols <> 'asin:text,pais:text,uds_recibidas:bigint,uds_vendidas:bigint,primer_movimiento:date,ultimo_movimiento:date,ledger_desde:date,ledger_hasta:date' THEN
        RAISE EXCEPTION 'ABORTA: el contrato ha cambiado. Ahora: %', cols;
    END IF;
    -- 🔒 Anclado sobre lo que NO debe aparecer: `refrescada_el` es diagnostico y vive
    --    en la copia; en la vista cambiaria el contrato y la app la veria.
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='v_presencia_pais'
                  AND column_name='refrescada_el') THEN
        RAISE EXCEPTION 'ABORTA: refrescada_el se ha colado en la vista.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_presencia_pais'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: mv_presencia_pais no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;
    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las materializadas y devuelve
    --    cero filas SIN dar error, asi que un assert escrito contra el seria inerte.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid='public.mv_presencia_pais'::regclass
                      AND attname='refrescada_el' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: la copia se ha quedado sin refrescada_el.';
    END IF;

    -- 🔴 EL ANCLA TIENE QUE CUADRAR RECIEN CREADA. Si no cuadra aqui --con la copia
    --    calculada hace un segundo-- es que la columna no mide lo que dice medir, y el
    --    centinela de la pantalla nacerria mintiendo en la direccion mala: callado.
    SELECT max(ledger_hasta) INTO ancla_copia FROM v_presencia_pais;
    SELECT max(fecha) INTO ancla_fuente FROM ledger_movimientos;
    IF ancla_copia IS DISTINCT FROM ancla_fuente THEN
        RAISE EXCEPTION 'ABORTA: el ancla de la copia dice % y la fuente %. Recien creada tienen que ser el mismo dia.', ancla_copia, ancla_fuente;
    END IF;

    SELECT md5(string_agg(t::text, '|' ORDER BY t.asin, t.pais)) INTO h FROM (
        SELECT asin, pais, uds_recibidas, uds_vendidas, primer_movimiento,
               ultimo_movimiento, ledger_desde, ledger_hasta FROM v_presencia_pais) t;
    IF n <> FILAS THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que la vista devuelva lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS, n;
    ELSIF h <> HUELLA THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y antes era %. Se ha movido un numero.', h, HUELLA;
    END IF;

    RAISE NOTICE 'Testigo OK. % filas (huella %), contrato y tipos intactos, indice unico puesto, ancla cuadrando en %.', n, h, ancla_copia;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · en bloques propios (un `END;` suelto lo rechaza el cerrojo)
DO $puerta_anon$
DECLARE
    n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_presencia_pais' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_presencia_pais y ha contado % filas. Es el movimiento de almacen, y hoy anon no llega a el por ningun camino: una copia sin RLS abierta seria una puerta NUEVA.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_presencia_pais.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n bigint; m bigint;
BEGIN
    SELECT count(*) INTO m FROM mv_presencia_pais;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_presencia_pais' INTO n;
    RESET ROLE;
    IF n <> m THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la copia tiene %.', n, m;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_presencia_pais. La tira de paises del Cockpit se quedaria vacia.';
END
$puerta_auth$;
