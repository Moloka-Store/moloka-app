-- ============================================================================
-- MIGRACION · `v_keepa_asin_visto` deja de recorrer el archivo de Keepa en cada carga
-- ----------------------------------------------------------------------------
-- 🔬 LO QUE CUESTA HOY, con el rol de la app sobre llamadas reales:
--      82 llamadas · media 1.132 ms · minimo 9 ms · 3.053 buffers por llamada
--    24 MB leidos, x2 por el conteo exacto de PostgREST, para devolver **416 ASIN**
--    -- una sola columna. Todo el coste es recorrer `keepa_escaparate_hist`, que es
--    el archivo historico y solo crece.
--
-- 🔒 NO HAY REPARTO: la vista es un UNION de dos tablas y NADA MAS. Ni joins, ni
--    funciones, ni `CURRENT_DATE`. Lo que devuelve cambia exactamente cuando entra
--    un informe de Keepa, que es cuando se refresca. La copia es la vista entera.
--
-- 🔒 CLAVE UNICA POR CONSTRUCCION: `UNION` (no `UNION ALL`) deduplica, asi que no
--    puede repetirse un ASIN. Medido: 416 filas, 416 distintos. Y el `WHERE asin IS
--    NOT NULL` de las dos ramas garantiza que no hay nulos, que es lo que un indice
--    unico no sabria enforcar.
--
-- 🔑 DOS FUENTES, DOS ANCLAS, Y UN MISMO PROCESADOR. `keepa_escaparate` (la foto) y
--    `keepa_escaparate_hist` (el archivo) las escribe las dos
--    `procesador_keepa_escaparate.py`, que ya tiene el gancho puesto -- se le anade
--    esta copia a su lista. Aun asi las anclas son DOS, una por tabla: la foto se
--    tira y se reescribe entera cada vez, el archivo solo crece, y una podria
--    quedarse atras sin la otra.
--    Hoy las dos dicen 2026-08-25.
--
-- 🔬 HUELLA MEDIDA EN PRODUCCION: 416 filas, md5 = 9f1e1a1c2895b9678e423ce33952b64d.
-- ============================================================================

DO $guardas$
DECLARE
    k char; n bigint; n_dist bigint; cols text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid='public.v_keepa_asin_visto'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_keepa_asin_visto tiene relkind=%. Si ya es materializada, esta migracion ya corrio.', k;
    END IF;
    IF to_regclass('public.mv_keepa_asin_visto') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_keepa_asin_visto YA existe.';
    END IF;

    SELECT count(*), count(DISTINCT asin) INTO n, n_dist FROM v_keepa_asin_visto;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas todo lo de abajo sale bien sin medir nada.';
    END IF;
    IF n <> n_dist THEN
        RAISE EXCEPTION 'ABORTA: % filas y % ASIN distintos. La clave no seria unica.', n, n_dist;
    END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_keepa_asin_visto';
    IF cols <> 'asin:text' THEN
        RAISE EXCEPTION 'ABORTA: v_keepa_asin_visto no tiene el contrato esperado. Ahora: %', cols;
    END IF;
    RAISE NOTICE 'Guardas OK. % ASIN, todos distintos, contrato de 1 columna.', n;
END
$guardas$;

CREATE MATERIALIZED VIEW public.mv_keepa_asin_visto AS
SELECT v.asin,
       -- 🔑 UNA ANCLA POR TABLA, aunque las escriba el mismo procesador: la foto se
       --    reescribe entera cada vez y el archivo solo crece, asi que una puede
       --    quedarse atras sin la otra. Son constantes en todas las filas: es el corte
       --    que declara ESTA copia, y el centinela lo compara contra el max() de cada
       --    TABLA -- nunca contra si misma, que diria siempre que va al dia.
       (SELECT max(fecha_foto) FROM keepa_escaparate) AS hasta_keepa_foto,
       (SELECT max(fecha_foto) FROM keepa_escaparate_hist) AS hasta_keepa_hist,
       clock_timestamp() AS refrescada_el
  FROM (
     SELECT keepa_escaparate.asin
       FROM keepa_escaparate
      WHERE keepa_escaparate.asin IS NOT NULL
     UNION
     SELECT keepa_escaparate_hist.asin
       FROM keepa_escaparate_hist
      WHERE keepa_escaparate_hist.asin IS NOT NULL) v
WITH DATA;

CREATE UNIQUE INDEX mv_keepa_asin_visto_uk ON public.mv_keepa_asin_visto (asin);

-- 🔴 LA PUERTA. Una copia NO aplica RLS: el GRANT es la unica puerta. Se revoca por
--    rol y por su nombre ANTES de conceder -- un `revoke ... from public` no quita los
--    grants explicitos que el default de Supabase da a `anon` y `authenticated`.
REVOKE ALL ON public.mv_keepa_asin_visto FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_keepa_asin_visto TO authenticated;

COMMENT ON MATERIALIZED VIEW public.mv_keepa_asin_visto IS
    'Los ASIN que Keepa ha visto alguna vez (foto + archivo historico). Materializada el 25-ago-2026: eran 3.053 buffers por llamada --24 MB-- para devolver 416 ASIN de una sola columna. La copia es la vista entera porque no hay nada volatil: es un UNION de dos tablas, sin joins ni CURRENT_DATE. Se refresca desde procesador_keepa_escaparate.py.';

CREATE OR REPLACE VIEW public.v_keepa_asin_visto AS
 SELECT asin FROM mv_keepa_asin_visto;

DO $testigo$
DECLARE
    HUELLA constant text := '9f1e1a1c2895b9678e423ce33952b64d';
    FILAS  constant bigint := 416;
    n bigint; h text; cols text;
    a_f date; f_f date; a_h date; f_h date;
BEGIN
    SELECT count(*) INTO n FROM v_keepa_asin_visto;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.'; END IF;

    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_keepa_asin_visto';
    IF cols <> 'asin:text' THEN
        RAISE EXCEPTION 'ABORTA: el contrato ha cambiado. Ahora: %', cols;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_index WHERE indrelid='public.mv_keepa_asin_visto'::regclass AND indisunique) THEN
        RAISE EXCEPTION 'ABORTA: mv_keepa_asin_visto no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;
    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las materializadas y devuelve
    --    cero filas SIN dar error, asi que un assert escrito contra el seria inerte.
    IF NOT EXISTS (SELECT 1 FROM pg_attribute
                    WHERE attrelid='public.mv_keepa_asin_visto'::regclass
                      AND attname='refrescada_el' AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: la copia se ha quedado sin refrescada_el.';
    END IF;

    -- 🔴 LAS ANCLAS TIENEN QUE CUADRAR RECIEN CREADAS. Si no cuadran aqui, no miden lo
    --    que dicen medir y el centinela de la pantalla nacerria mintiendo en la
    --    direccion mala: callado.
    SELECT max(hasta_keepa_foto), max(hasta_keepa_hist) INTO a_f, a_h FROM mv_keepa_asin_visto;
    SELECT max(fecha_foto) INTO f_f FROM keepa_escaparate;
    SELECT max(fecha_foto) INTO f_h FROM keepa_escaparate_hist;
    IF a_f IS DISTINCT FROM f_f OR a_h IS DISTINCT FROM f_h THEN
        RAISE EXCEPTION 'ABORTA: las anclas de la copia dicen %/% y las fuentes %/%.', a_f, a_h, f_f, f_h;
    END IF;

    SELECT md5(string_agg(asin,'|' ORDER BY asin)) INTO h FROM v_keepa_asin_visto;
    IF n <> FILAS THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que la vista devuelva lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS, n;
    ELSIF h <> HUELLA THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y antes era %. Se ha movido un ASIN.', h, HUELLA;
    END IF;

    RAISE NOTICE 'Testigo OK. % ASIN (huella %), contrato intacto, indice unico puesto, anclas cuadrando en % y %.', n, h, a_f, a_h;
END
$testigo$;

DO $puerta_anon$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_keepa_asin_visto' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_keepa_asin_visto y ha contado % filas. Hoy no llega a ese dato por ningun camino: una copia sin RLS abierta seria una puerta NUEVA.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_keepa_asin_visto.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE n bigint; m bigint;
BEGIN
    SELECT count(*) INTO m FROM mv_keepa_asin_visto;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_keepa_asin_visto' INTO n;
    RESET ROLE;
    IF n <> m THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la copia tiene %.', n, m;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve los % ASIN.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_keepa_asin_visto. La vista lo veria VACIO y la pantalla creeria que Keepa no ha visto NINGUN ASIN -- una cifra falsa creible, peor que quedarse en blanco.';
END
$puerta_auth$;
