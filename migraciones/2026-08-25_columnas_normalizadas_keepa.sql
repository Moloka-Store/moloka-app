-- ============================================================================
-- MIGRACION · el cruce de Keepa vuelve a usar el indice BAJO RLS
-- ----------------------------------------------------------------------------
-- 🔴 EL PROBLEMA, MEDIDO CON EL ROL DE LA APP (no con el lector, que salta la RLS).
--    `salud_fba` es `security_invoker` y su LATERAL cruza contra `keepa_escaparate`,
--    que tiene RLS. Con RLS activa, Postgres NO deja que una condicion que no sea
--    `LEAKPROOF` baje a ser condicion de indice: la deja como `Filter` de un Seq Scan.
--    Y `btrim(text)` y `lower(text)` **no son leakproof** (`proleakproof = false`);
--    `texteq` --el `=` a secas-- **si lo es**.
--
--    Resultado: el LATERAL recorre `keepa_escaparate` ENTERA una vez por cada fila de
--    `inventario_fba`. 361 vueltas x 580 paginas = 209.380 buffers = **1,6 GB**, y la
--    base tiene 224 MB de `shared_buffers`: UNA consulta lee siete veces la cache
--    entera y la vacia. Por eso la pantalla arrastraba a todo lo demas.
--
-- 🔬 LAS TRES MEDIDAS, en la misma corrida, con `SET ROLE authenticated` y las claims
--    puestas (workflow `diagnostico-plan-app.yml`, 25-ago-2026, produccion):
--
--      el LATERAL con btrim/lower, CON RLS ....  209.385 buffers  475,0 ms  Seq Scan x361
--      el LATERAL con cruce CRUDO,  CON RLS ....    1.075 buffers    2,5 ms  Index Scan
--      el LATERAL con btrim/lower, SIN RLS .....    1.075 buffers    1,9 ms  Index Scan
--
--    **195x.** Y la tercera linea es la que cierra el caso: sin RLS el indice funcional
--    del 24-ago SI se usa. O sea que ese indice **es inerte para la app** -- se dio por
--    bueno midiendo con el rol equivocado.
--
-- 🔑 EL ARREGLO NO QUITA LA GARANTIA: LA MUEVE DE LA CONSULTA AL DATO. La limpieza se
--    sigue aplicando, solo que **al escribir** en vez de al leer. Las tres razones de
--    `docs/btrim-lower-decision-en-frio.md` para NO borrar los envoltorios siguen en
--    pie y ninguna se toca:
--      · la limpieza no es propiedad de la casa (454 valores sucios vivos en
--        `escaner_detalle.nombre`) -> sigue sin serlo, y por eso se normaliza aqui;
--      · `inventario_fba` tiene n=1 foto -> da igual, no se apuesta a que venga limpio;
--      · si fallara no lo caza nadie -> no puede fallar: la columna se calcula sola.
--    No se apuesta. Se normaliza.
--
-- 🔒 POR QUE COLUMNAS GENERADAS Y NO OTRA COSA. `btrim(text)` y `lower(text)` son
--    IMMUTABLE (medido: `provolatile = 'i'`), que es lo que exige una columna
--    `GENERATED ALWAYS AS (...) STORED`. Y la comparacion pasa a ser `=` entre dos
--    columnas de texto, o sea `texteq`, que SI es leakproof: la condicion vuelve a
--    poder bajar al indice aunque la RLS este puesta.
--    ❌ La alternativa `ALTER FUNCTION btrim(text) LEAKPROOF` esta DESCARTADA: exige
--       superusuario y `postgres` no lo es aqui (medido: `rolsuper = false`).
--
-- 🔴 EL INDICE NUEVO LLEVA `fecha_foto DESC`, Y NO ES ADORNO. El LATERAL hace
--    `ORDER BY ke.fecha_foto DESC LIMIT 1`. Sin esa tercera columna se recupera la
--    IGUALDAD pero se pierde la ORDENACION, y Postgres tendria que ordenar cada grupo:
--    el `Index Scan` volveria a llevar un `Sort` encima.
--
-- ⚠️ EL ORDEN IMPORTA Y EL PASO 1 YA ESTA DADO. `archivar_foto()` saca las columnas de
--    `pg_attribute`: sin el arreglo del PR #228 --que la hace saltarse las generadas--
--    esta migracion PARARIA la siguiente carga de Keepa, porque su guarda
--    `faltan_en_hist` abortaria al ver `asin_k` y `dominio_k` en la foto y no en el
--    historico. Ese PR va fusionado y hoy es inerte.
--    🔒 El INSERT del procesador de Keepa NO se ve afectado: usa una lista de columnas
--       explicita (`TIPADAS` + cinco fijas), asi que nunca nombraria una generada.
--       `inventario_fba` tampoco: sus columnas van explicitas y no usa `archivar_foto`.
--
-- ⚠️ ANOTADO, NO HECHO AQUI: el otro cruce de la vista --`btrim(v.asin) = btrim(i.asin)`
--    contra `v_ventas_ventanas`-- se queda como esta. Cuesta 113 buffers de 209.753
--    porque la copia son 8 paginas, asi que arreglarlo no cambia nada medible y
--    obligaria a rehacer `mv_ventas_ventanas`. Se deja escrito para que no parezca un
--    olvido.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k char; n bigint; n_es bigint; casan bigint;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid='public.salud_fba'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: salud_fba tiene relkind=%. Se esperaba una VISTA.', k;
    END IF;

    -- 🔴 Por `pg_attribute`: `information_schema` NO VE las columnas generadas de la
    --    misma forma, y sobre todo devuelve cero filas SIN dar error para lo que no
    --    entiende. Si ya existieran, esta migracion ya corrio y el ensayo no probaria nada.
    IF EXISTS (SELECT 1 FROM pg_attribute
                WHERE attrelid='public.keepa_escaparate'::regclass
                  AND attname IN ('asin_k','dominio_k') AND attnum>0 AND NOT attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate YA tiene asin_k o dominio_k.';
    END IF;

    SELECT count(*), count(*) FILTER (WHERE marketplace='ES') INTO n, n_es FROM salud_fba;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: salud_fba esta vacia. Sobre cero filas cualquier comprobacion de abajo sale bien sin medir nada.';
    END IF;

    -- 🔴 EL RECUENTO QUE DECIDE, ANTES DE TOCAR NADA. Es el que hay que volver a ver
    --    igual al final: si el cruce normalizado emparejara distinto, esto lo caza.
    SELECT count(k2.rank) INTO casan
      FROM inventario_fba i
      LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke
                          WHERE btrim(ke.asin) = btrim(i.asin) AND lower(ke.dominio) = 'es'
                          ORDER BY ke.fecha_foto DESC LIMIT 1) k2 ON true;
    RAISE NOTICE 'Guardas OK. salud_fba=% filas (% en ES). El LATERAL empareja % de % fichas.',
        n, n_es, casan, (SELECT count(*) FROM inventario_fba);
    -- 🔴 LA FOTO DE ANTES SE TOMA AQUI, Y ESO ES MEJOR QUE UNA CONSTANTE.
    --    La primera version traia la huella medida en PRODUCCION y la comparaba solo si
    --    el RECUENTO de filas coincidia. Fallo en el ensayo: staging tiene 362 filas
    --    IGUAL que produccion pero con OTRO contenido --es un clon de anoche mas lo que
    --    se ha aplicado encima--, asi que la guarda se creyo que estaba en produccion y
    --    aborto por una diferencia de DATOS que no tenia nada que ver con la migracion.
    -- 🔑 El recuento de filas NO es prueba de "mismos datos". El invariante de verdad no
    --    es "la vista devuelve lo que devolvia en produccion el 25-ago": es "la vista
    --    devuelve LO MISMO QUE DEVOLVIA HACE UN SEGUNDO". Eso se puede medir en
    --    cualquier entorno, y es mas fuerte.
    CREATE TEMP TABLE _salud_fba_antes ON COMMIT DROP AS
        SELECT md5(string_agg(t::text, '|' ORDER BY t.sku, t.marketplace)) AS huella,
               count(*) AS filas
          FROM (SELECT * FROM salud_fba) t;
END
$guardas$;

-- -- 1) LAS COLUMNAS NORMALIZADAS ---------------------------------------------
-- 🔒 `STORED` y no `VIRTUAL`: se calcula al escribir y se guarda, que es lo unico que
--    permite indexarla. Cuesta unos bytes por fila (1.653 + 362) y una reescritura de
--    28 MB + 1 MB, o sea instantanea. El workflow pone `lock_timeout=5s`: si Elena
--    tuviera la tabla cogida, esto FALLA RAPIDO en vez de encolarse detras.
ALTER TABLE public.keepa_escaparate
    ADD COLUMN asin_k text GENERATED ALWAYS AS (btrim(asin)) STORED;
ALTER TABLE public.keepa_escaparate
    ADD COLUMN dominio_k text GENERATED ALWAYS AS (lower(dominio)) STORED;
ALTER TABLE public.inventario_fba
    ADD COLUMN asin_k text GENERATED ALWAYS AS (btrim(asin)) STORED;

COMMENT ON COLUMN public.keepa_escaparate.asin_k IS
    'El ASIN ya normalizado (btrim), calculado al ESCRIBIR. Existe para que el cruce sea `=` entre columnas --o sea `texteq`, que es LEAKPROOF-- y por tanto pueda bajar al indice aunque la RLS este puesta. Con `btrim()` en la consulta no puede: btrim NO es leakproof, y el indice se queda sin usar (medido: 195x).';
COMMENT ON COLUMN public.keepa_escaparate.dominio_k IS
    'El dominio ya normalizado (lower), calculado al ESCRIBIR. Mismo motivo que asin_k.';
COMMENT ON COLUMN public.inventario_fba.asin_k IS
    'El ASIN ya normalizado (btrim), calculado al ESCRIBIR. Es el otro lado del cruce de salud_fba con keepa_escaparate: si solo se normalizara un lado, la comparacion seguiria llevando una funcion y el indice seguiria sin usarse.';

-- -- 2) EL INDICE -------------------------------------------------------------
-- 🔴 `fecha_foto DESC` NO es adorno: el LATERAL hace `ORDER BY ke.fecha_foto DESC
--    LIMIT 1`. Sin esa tercera columna se recupera la igualdad y se pierde la
--    ordenacion -- el Index Scan volveria a llevar un Sort encima.
CREATE INDEX idx_keepa_k_asin_dominio_foto
    ON public.keepa_escaparate (asin_k, dominio_k, fecha_foto DESC);

COMMENT ON INDEX public.idx_keepa_k_asin_dominio_foto IS
    'El indice del LATERAL de salud_fba, sobre las columnas YA normalizadas. Sustituye en la practica a idx_keepa_asin_dominio_foto, que es funcional y por eso NO se puede usar bajo RLS. Ese se deja en pie a proposito: lo pueden estar usando las vistas `definer` (v_keepa_cruce, v_salud_fba_cruce), a las que la RLS no les aplica. Quitarlo es otra decision y otro PR.';

-- -- 3) LA VISTA · mismo nombre, mismo OID, mismo contrato ---------------------
-- 🔒 Lo unico que cambia son las DOS condiciones del LATERAL. Las 59 columnas, su
--    orden y sus tipos quedan intactos, y `CREATE OR REPLACE VIEW` conserva el OID:
--    nada de lo que cuelga se entera y los ACL se mantienen.
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
    i.procesado_at AS procesado_en
   FROM inventario_fba i
     -- ⚠️ Este cruce NO se toca: cuesta 113 buffers de 209.753 porque la copia son 8
     --    paginas. Arreglarlo no cambia nada medible y obligaria a rehacer la copia.
     LEFT JOIN v_ventas_ventanas v ON btrim(v.asin) = btrim(i.asin)
     -- 🔴 AQUI ESTA TODO EL ARREGLO: dos columnas ya normalizadas en vez de dos
     --    llamadas a funcion. La comparacion pasa a ser `texteq`, que es LEAKPROOF, y
     --    por eso puede volver a bajar al indice con la RLS puesta.
     LEFT JOIN LATERAL ( SELECT ke.rank
           FROM keepa_escaparate ke
          WHERE ke.asin_k = i.asin_k AND ke.dominio_k = 'es'::text
          ORDER BY ke.fecha_foto DESC
         LIMIT 1) k ON true;

-- -- TESTIGO · que no se mueva un dato -----------------------------------------
DO $testigo$
DECLARE
    HUELLA constant text := '83ae37c2dbc892b0b2ccea9a974d4079';
    FILAS  constant bigint := 362;
    CASAN  constant bigint := 345;
    n bigint; h text; cols text;
    casan_nuevo bigint; casan_roto bigint;
    h_antes text; n_antes bigint; n_distintas bigint;
BEGIN
    SELECT count(*) INTO n FROM salud_fba;
    IF n = 0 THEN RAISE EXCEPTION 'ABORTA: salud_fba se ha quedado vacia.'; END IF;

    -- El contrato, con TIPOS: la huella md5 sobre `t::text` es ciega a ellos.
    SELECT string_agg(column_name||':'||data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='salud_fba';
    IF cols <> 'sku:text,fnsku:text,asin:text,product_name:text,condition:text,marketplace:text,available:integer,fc_transfer:integer,total_reserved_quantity:integer,reserved_fc_processing:integer,reserved_customer_order:integer,reserved_staging:integer,inbound_quantity:integer,inbound_working:integer,inbound_shipped:integer,inbound_received:integer,unfulfillable_quantity:integer,pending_removal_quantity:integer,inventory_supply_at_fba:integer,days_of_supply:numeric,total_days_of_supply_incl_open_shipments:numeric,weeks_of_cover_t30:numeric,weeks_of_cover_t90:numeric,sell_through:numeric,units_shipped_t7:integer,units_shipped_t30:integer,units_shipped_t60:integer,units_shipped_t90:integer,historical_days_of_supply:numeric,recommended_action:text,recommended_ship_in_quantity:integer,recommended_ship_in_date:text,healthy_inventory_level:numeric,alert:text,estimated_excess_quantity:integer,recommended_removal_quantity:integer,estimated_cost_savings_of_recommended_actions:numeric,fba_minimum_inventory_level:integer,fba_inventory_level_health_status:text,low_inventory_fee_applied_current_week:text,exempted_from_low_inventory_fee:text,estimated_storage_cost_next_month:numeric,storage_type:text,storage_volume:numeric,item_volume:numeric,inventory_age_snapshot_date:text,featuredoffer_price:numeric,lowest_price_new_plus_shipping:numeric,your_price:numeric,sales_price:numeric,sales_rank:integer,is_seasonal_in_next_3_months:text,season_name:text,season_start_date:text,season_end_date:text,snapshot_date:date,fichero:text,crudo:jsonb,procesado_en:timestamp with time zone' THEN
        RAISE EXCEPTION 'ABORTA: salud_fba ha cambiado de contrato. Ahora: %', cols;
    END IF;

    -- 🔴 EL TESTIGO QUE PIDIO FERNANDO, Y SUS DOS MITADES.
    --    (a) el cruce normalizado tiene que emparejar lo MISMO que el de antes.
    SELECT count(k2.rank) INTO casan_nuevo
      FROM inventario_fba i
      LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke
                          WHERE ke.asin_k = i.asin_k AND ke.dominio_k = 'es'
                          ORDER BY ke.fecha_foto DESC LIMIT 1) k2 ON true;
    --    (b) …y la comprobacion tiene que PODER ponerse roja. Con un espacio inyectado
    --        en un lado, el emparejamiento debe caer a CERO. Sin esta mitad, un
    --        "345 = 345" no seria una medicion: seria un verde prestado.
    SELECT count(k2.rank) INTO casan_roto
      FROM inventario_fba i
      LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke
                          WHERE ke.asin_k = i.asin_k || ' ' AND ke.dominio_k = 'es'
                          ORDER BY ke.fecha_foto DESC LIMIT 1) k2 ON true;
    IF casan_roto <> 0 THEN
        RAISE EXCEPTION 'ABORTA: con un espacio inyectado el cruce sigue emparejando % fichas. La comprobacion del 345=345 no puede ponerse roja, asi que no mide nada.', casan_roto;
    END IF;

    SELECT md5(string_agg(t::text,'|' ORDER BY t.sku, t.marketplace)) INTO h
      FROM (SELECT * FROM salud_fba) t;

    -- 🔴 LA COMPARACION QUE VALE EN CUALQUIER ENTORNO: contra la foto tomada al empezar,
    --    sobre los MISMOS datos. Si esto cuadra, la migracion no ha movido nada -- aqui,
    --    en staging, y en produccion.
    -- 🔒 Cualificadas con el alias, y NO es un detalle de estilo: plpgsql no
    --    distingue mayusculas, asi que la columna `huella` y la constante `HUELLA`
    --    son el MISMO identificador. Sin el alias da
    --    `column reference "huella" is ambiguous` -- que al menos es ruidoso; lo
    --    peligroso de este choque es cuando resuelve a favor de la variable y
    --    compara una cosa consigo misma.
    SELECT a.huella, a.filas INTO h_antes, n_antes FROM _salud_fba_antes a;
    IF n_antes IS NULL THEN
        RAISE EXCEPTION 'ABORTA: no se tomo la foto de antes. Sin ella esto no comprueba nada.';
    END IF;
    IF n <> n_antes THEN
        RAISE EXCEPTION 'ABORTA: salud_fba tenia % filas al empezar y ahora tiene %.', n_antes, n;
    END IF;
    IF h <> h_antes THEN
        RAISE EXCEPTION 'ABORTA: la huella de salud_fba era % al empezar y ahora es %. Se ha movido un dato.', h_antes, h;
    END IF;

    -- 🔒 Y ADEMAS, la comparacion DIFERENCIAL sobre lo unico que ha cambiado: cada fila
    --    contra lo que habria dado la formula VIEJA. Es redundante con la huella a
    --    proposito -- la huella dice QUE algo se movio, esto dice CUANTAS filas y
    --    cual es la columna.
    SELECT count(*) INTO n_distintas
      FROM salud_fba s
      LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke
                          WHERE btrim(ke.asin) = btrim(s.asin) AND lower(ke.dominio) = 'es'
                          ORDER BY ke.fecha_foto DESC LIMIT 1) viejo ON true
     WHERE s.sales_rank IS DISTINCT FROM viejo.rank;
    IF n_distintas > 0 THEN
        RAISE EXCEPTION 'ABORTA: % fila(s) tienen un sales_rank distinto del que daba la formula vieja.', n_distintas;
    END IF;

    -- 🔒 La huella de PRODUCCION se comprueba solo si coincide la de antes: alli si
    --    dice algo, y en cualquier otro sitio seria un rojo por el entorno.
    IF h_antes = HUELLA AND n = FILAS AND casan_nuevo <> CASAN THEN
        RAISE EXCEPTION 'ABORTA: el cruce empareja % fichas y en produccion emparejaba %.', casan_nuevo, CASAN;
    END IF;

    RAISE NOTICE 'Testigo OK (dato). % filas, huella IDENTICA a la de antes de tocar nada (%), 0 filas con sales_rank distinto de la formula vieja, contrato de 59 columnas con tipos intacto, el cruce empareja % y con un espacio inyectado cae a 0.', n, h, casan_nuevo;
END
$testigo$;

-- -- TESTIGO DEL PLAN · que el indice se use CON LA RLS PUESTA -----------------
-- 🔴 ES EL QUE DE VERDAD DICE SI ESTO HA SERVIDO. Sin el, la migracion podria aplicarse
--    limpia, con la huella igual y el contrato intacto, y NO ARREGLAR NADA -- que es
--    exactamente lo que paso con el indice funcional del 24-ago. Un verde que no mide
--    el plan no vale aqui.
DO $puerta_plan$
DECLARE
    linea text; plan text := '';
    sin_permiso text;
    buffers bigint := NULL;
    trozo text;
BEGIN
    -- ⚠️ Staging NO lo reproduce, y esta medido: su volcado va con `--no-privileges`,
    --    asi que `authenticated` no tiene SELECT sobre estas tablas y la funcion
    --    rebotaria por LAS FUENTES, no por el plan. Se GRITA en vez de abortar: una
    --    guarda que puede ponerse roja por el alcance de una copia de seguridad no es
    --    una guarda, es ruido futuro.
    SELECT string_agg(t, ', ') INTO sin_permiso FROM (
        SELECT unnest(ARRAY['keepa_escaparate','inventario_fba','mv_ventas_ventanas']) AS t) x
     WHERE NOT has_table_privilege('authenticated', 'public.' || t, 'SELECT');
    IF sin_permiso IS NOT NULL THEN
        RAISE WARNING 'PLAN NO COMPROBADO EN ESTE ENTORNO: `authenticated` no tiene SELECT sobre %. Esto NO dice nada sobre produccion: pasa porque el volcado va con --no-privileges. El plan SE VERIFICA EN PRODUCCION, al aplicar.', sin_permiso;
        RETURN;
    END IF;

    PERFORM set_config('request.jwt.claims',
        '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
    SET LOCAL ROLE authenticated;

    -- 🔴 Sin rol efectivo o sin uid, el plan saldria sobre CERO FILAS: rapido, verde y
    --    midiendo nada.
    IF current_user <> 'authenticated' OR auth.uid() IS NULL THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: rol efectivo % y auth.uid()=%. El plan no mediria con la RLS puesta.', current_user, auth.uid();
    END IF;

    FOR linea IN
        EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) '
                'SELECT count(k.rank) FROM inventario_fba i '
                'LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke '
                '  WHERE ke.asin_k = i.asin_k AND ke.dominio_k = ''es'' '
                '  ORDER BY ke.fecha_foto DESC LIMIT 1) k ON true'
    LOOP
        plan := plan || linea || chr(10);
        IF buffers IS NULL AND position('Buffers: shared hit=' in linea) > 0 THEN
            trozo := split_part(split_part(linea, 'Buffers: shared hit=', 2), ' ', 1);
            buffers := replace(trozo, ',', '')::bigint;
        END IF;
    END LOOP;
    RESET ROLE;

    -- 🔴 LAS DOS MITADES DEL PLAN.
    --    ⚠️ Y cada una dice CUAL ha saltado. La primera version usaba `%%` en el
    --       mensaje --que en RAISE es un POR CIENTO LITERAL y no consume argumento--,
    --       asi que reventaba con 'too many parameters specified for RAISE' y tapaba
    --       cual de las tres comprobaciones habia fallado. Un error que oculta el
    --       error es peor que no comprobar.
    --    (a) que el Seq Scan sobre keepa haya DESAPARECIDO -- es lo que costaba 1,6 GB.
    IF position('Seq Scan on keepa_escaparate' in plan) > 0 THEN
        RAISE EXCEPTION 'ABORTA: el plan SIGUE recorriendo keepa_escaparate entera. La migracion no ha servido de nada. Plan: %', chr(10) || plan;
    END IF;
    --    (b) …y que use un Index Scan. Anclado sobre lo que TIENE que aparecer ademas
    --        de sobre lo que no: sin esto, un plan que no leyera nada pasaria.
    IF position('Index Scan' in plan) = 0 AND position('Index Only Scan' in plan) = 0 THEN
        RAISE EXCEPTION 'ABORTA: el plan no usa ningun indice sobre keepa_escaparate. Plan: %', chr(10) || plan;
    END IF;
    -- 🔒 Y el numero, que es lo unico que no se puede fingir. Era 209.385 con RLS y
    --    1.075 con el cruce crudo. Un techo de 20.000 esta 10x por encima de lo bueno y
    --    10x por debajo de lo malo: no puede pasar por casualidad en ninguno de los dos
    --    sentidos.
    IF buffers IS NULL THEN
        RAISE EXCEPTION 'ABORTA: no se ha podido leer los buffers del plan. Sin ese numero esto no comprueba nada. Plan: %', chr(10) || plan;
    END IF;
    IF buffers > 20000 THEN
        RAISE EXCEPTION 'ABORTA: el plan lee % buffers y antes leia 209.385. Se esperaba del orden de 1.075. Plan: %', buffers, chr(10) || plan;
    END IF;

    RAISE NOTICE 'Testigo OK (plan). CON LA RLS PUESTA el LATERAL usa indice y lee % buffers (antes 209.385, o sea 1,6 GB). Mejora de %x.', buffers, round(209385.0 / greatest(buffers,1));
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated ha rebotado con: %. Si el objeto que nombra no es salud_fba, falta un SELECT sobre esa fuente.', SQLERRM;
END
$puerta_plan$;
