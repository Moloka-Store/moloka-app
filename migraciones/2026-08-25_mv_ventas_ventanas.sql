-- ============================================================================
-- MIGRACION · `v_ventas_ventanas` pasa a MATERIALIZADA, SIN CASCADA
-- ----------------------------------------------------------------------------
-- EL PROBLEMA: esa vista reagrega 20.317 filas de ledger + 16.744 de
-- transacciones EN CADA CARGA DE PANTALLA para producir 293 filas que solo
-- cambian cuando entra un informe (ledger y transacciones se cargaron el
-- 24-ago a las 16:58 y 17:04; dos o tres veces por semana). Es el 92 % del
-- coste de `salud_fba`: 1.904 ms de los 2.073 de una evaluacion, con el ledger
-- a 1.254 dentro.
--
-- POR QUE MATERIALIZAR ES SEMANTICAMENTE GRATIS: las ventanas estan ancladas a
-- `max(fecha)` del ledger, NO a `now()`. Comprobado: `ventana_hasta_ledger` =
-- 2026-08-24 = `max(fecha)` del ledger. El resultado solo puede cambiar cuando
-- cambia el ledger. No se congela nada que estuviera vivo.
--
-- 🔴 SIN CASCADA, Y ESTO ES LO QUE HACE LA MIGRACION PEQUENA. De
--    `v_ventas_ventanas` cuelga `salud_fba`, y de `salud_fba` cuelgan DIEZ
--    objetos --el ultimo `mv_trackeador_pantalla`, con 3.248 kB de datos, que
--    alimenta la pantalla del Trackeador--. Un DROP ... CASCADE se los lleva a
--    todos y habria que recrearlos y refrescarlos.
--    `CREATE OR REPLACE VIEW` CONSERVA EL OID, asi que no tira NADA de lo que
--    cuelga, CONSERVA LOS ACL (un DROP+CREATE los pierde, seccion 4) y la
--    vuelta atras es una linea.
--
-- 🔴 `dias_desde_ultimo_dato` SE QUEDA FUERA DE LA MATERIALIZADA. Es
--    `CURRENT_DATE - hasta_ledger`: la unica columna de la definicion que
--    depende del reloj. Materializarla la CONGELA, y una columna que se llama
--    "dias desde el ultimo dato" y deja de contar dias es exactamente la cifra
--    que miente. Se calcula en la vista de encima, sobre un ancla guardada.
--    (Comprobado que no la lee nadie: ni una vista de la base, ni ninguno de
--    los dos repos. Aun asi se conserva, y viva.)
--
-- 🔒 EL CONTRATO NO SE ROMPE: la vista de encima devuelve las MISMAS 16 columnas
--    de antes, con los mismos nombres, tipos y ORDEN, y ANADE una 17.a al final
--    (`ventana_hasta_listings`). `CREATE OR REPLACE VIEW` admite anadir al final
--    y nada mas -- por eso va ahi y no junto a las otras dos anclas.
--    Nadie que lea las 16 de antes se entera del cambio.
--
-- ⚠️ UNA MATERIALIZADA NO APLICA RLS: la puerta pasa a ser SOLO el GRANT. Aqui
--    es equivalente, y esta medido: NINGUNA politica de `public` filtra por
--    usuario --todas son `true` o `auth.uid() IS NOT NULL`--, asi que Elena y
--    Fernando ven el mismo dato y no hay nada que se pueda filtrar de uno a
--    otro. La mv nace revocada a public/anon y con SELECT solo para
--    `authenticated`, y eso SE VERIFICA EN PRODUCCION despues de aplicar (en
--    staging no prueba nada: el dump va sin privilegios).
--
-- 🔒 EL REFRESCO NO VIVE AQUI. Va en los procesadores de las TRES fuentes
--    --ledger, transacciones y listings--, atado al evento que cambia el dato y
--    no al reloj. Una fuente sin gancho es una copia que se queda vieja sin que
--    nadie la refresque; una fuente sin ancla es un desfase invisible. Y no
--    puede ir en una migracion aunque se quisiera: refrescar una materializada
--    sin bloquear lectores no se puede hacer dentro de una transaccion, y este
--    fichero corre entero dentro de una.
--
-- 🔬 EL "ANTES", medido con el rol de la app y por DELTA de una tanda
--    controlada de recargas (no por la media acumulada, que va un 18-73 % por
--    encima): `salud_fba` de Inventario **2.363 ms**.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k        char;
    n_filas  bigint;
    n_asin   bigint;
    n_nulos  bigint;
    hasta    date;
    max_led  date;
    n_cols   int;
BEGIN
    -- 1) El destino es el que esta migracion cree que es.
    SELECT relkind INTO k FROM pg_class
     WHERE oid = 'public.v_ventas_ventanas'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas tiene relkind=% y se esperaba una VISTA. Si ya es materializada, esta migracion ya corrio y este ensayo no probaria nada.', k;
    END IF;
    IF to_regclass('public.mv_ventas_ventanas') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_ventas_ventanas YA existe. Un ensayo sobre el estado de destino sale verde sin demostrar nada (seccion 3).';
    END IF;

    -- 2) La pregunta anti-cero: sin filas, todo lo de abajo saldria "bien" sin
    --    haber medido nada.
    SELECT count(*), count(DISTINCT asin), count(*) FILTER (WHERE asin IS NULL)
      INTO n_filas, n_asin, n_nulos FROM v_ventas_ventanas;
    IF n_filas = 0 THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas devuelve 0 filas. No hay nada que materializar y el testigo no podria comparar nada.';
    END IF;

    -- 3) LA UNICIDAD SE COMPRUEBA, NO SE SUPONE: el indice unico es lo que
    --    permite refrescar sin bloquear lectores, y si un dia dejara de ser
    --    cierto el refresco FALLA y la pantalla se queda con el dato viejo sin
    --    decir nada. (Por construccion lo garantizan los GROUP BY asin de cada
    --    CTE mas el FULL JOIN por asin; esto lo confirma sobre el dato.)
    IF n_asin <> n_filas THEN
        RAISE EXCEPTION 'ABORTA: % filas y % asin distintos. La clave del indice unico no es unica y el REFRESH fallaria.', n_filas, n_asin;
    END IF;
    IF n_nulos > 0 THEN
        RAISE EXCEPTION 'ABORTA: % filas con asin NULL. Un indice unico no enforcea sobre NULL (cada NULL es distinto de los demas) y el refresco no podria casar esas filas.', n_nulos;
    END IF;

    -- 4) LA PREMISA DE QUE MATERIALIZAR ES GRATIS: el ancla es el ledger, no el
    --    reloj. Si esto no se cumpliera, la materializada congelaria un dato
    --    que estaba vivo.
    SELECT ventana_hasta_ledger INTO hasta FROM v_ventas_ventanas LIMIT 1;
    SELECT max(fecha) INTO max_led FROM ledger_movimientos;
    IF hasta IS DISTINCT FROM max_led THEN
        RAISE EXCEPTION 'ABORTA: ventana_hasta_ledger=% y max(fecha) del ledger=%. La vista no esta anclada al ledger como esta migracion supone.', hasta, max_led;
    END IF;

    -- 5) El contrato que hay que reproducir: 16 columnas y la del reloj la ultima.
    SELECT count(*) INTO n_cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_ventas_ventanas';
    IF n_cols <> 16 THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas tiene % columnas y esta migracion reproduce 16. La vista ha cambiado: revisa el CREATE OR REPLACE de abajo antes de seguir.', n_cols;
    END IF;
    IF (SELECT column_name FROM information_schema.columns
         WHERE table_schema='public' AND table_name='v_ventas_ventanas'
         ORDER BY ordinal_position DESC LIMIT 1) <> 'dias_desde_ultimo_dato' THEN
        RAISE EXCEPTION 'ABORTA: la ultima columna de la vista ya no es dias_desde_ultimo_dato. El CREATE OR REPLACE cambiaria el orden del contrato.';
    END IF;

    RAISE NOTICE 'Guardas OK. % filas, % asin unicos, 0 nulos, ancla=% (= max del ledger), 16 columnas.', n_filas, n_asin, hasta;
END
$guardas$;

-- -- 1) LA MATERIALIZADA · la definicion actual MENOS la columna del reloj ----
CREATE MATERIALIZED VIEW public.mv_ventas_ventanas AS
WITH ancla AS (
    SELECT (SELECT max(ledger_movimientos.fecha) FROM ledger_movimientos) AS hasta_ledger,
           (SELECT max(transacciones_movimientos.fecha) FROM transacciones_movimientos) AS hasta_trans,
           -- 🔴 LA TERCERA FUENTE, Y SIN ELLA SU DESFASE ES INVISIBLE POR DISENO.
           --    `listings_amazon` no es adorno aqui: es el MAPA SKU -> ASIN del CTE
           --    `sku_asin`. Las ventas de marketplace llegan por SKU y esa tabla dice a
           --    que ASIN pertenecen. Si entra un informe de listings sin que entre uno de
           --    ledger o transacciones --una referencia nueva, un SKU que cambia de
           --    ASIN--, la copia se queda con el mapa viejo y las ventas de ese SKU dejan
           --    de sumarse a su ASIN: el numero sale BAJO, en silencio.
           --    Las otras dos anclas NO lo ven: ninguna se mueve cuando solo cambia
           --    listings. Por eso hace falta una POR CADA FUENTE.
           (SELECT max(listings_amazon.fecha_informe) FROM listings_amazon) AS hasta_listings
), salidas AS (
    SELECT l.asin,
           sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 8)  AND l.fecha < a_1.hasta_ledger) AS uds_7d,
           sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 31) AND l.fecha < a_1.hasta_ledger) AS uds_30d,
           sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 61) AND l.fecha < a_1.hasta_ledger) AS uds_60d,
           sum(abs(l.quantity)) FILTER (WHERE l.fecha > (a_1.hasta_ledger - 91) AND l.fecha < a_1.hasta_ledger) AS uds_90d
      FROM ledger_movimientos l
      CROSS JOIN ancla a_1
     WHERE l.event_type = 'Shipments'::text AND l.asin IS NOT NULL
       AND l.fecha > (a_1.hasta_ledger - 91) AND l.fecha < a_1.hasta_ledger
     GROUP BY l.asin
), devueltas AS (
    SELECT l.asin, sum(abs(l.quantity)) AS devoluciones_30d
      FROM ledger_movimientos l
      CROSS JOIN ancla a_1
     WHERE l.event_type = 'CustomerReturns'::text AND l.asin IS NOT NULL
       AND l.fecha > (a_1.hasta_ledger - 31) AND l.fecha < a_1.hasta_ledger
     GROUP BY l.asin
), sku_asin AS (
    SELECT DISTINCT ON ((btrim(listings_amazon.seller_sku)))
           btrim(listings_amazon.seller_sku) AS sku,
           btrim(listings_amazon.asin) AS asin
      FROM listings_amazon
     WHERE listings_amazon.seller_sku IS NOT NULL AND listings_amazon.asin IS NOT NULL
       AND btrim(listings_amazon.asin) <> ''::text
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
       a.hasta_trans  AS ventana_hasta_marketplace,
       a.hasta_listings AS ventana_hasta_listings
  FROM salidas s
  FULL JOIN mercado m ON m.asin = s.asin
  LEFT JOIN devueltas d ON d.asin = COALESCE(s.asin, m.asin)
  CROSS JOIN ancla a
WITH DATA;

-- -- 2) EL INDICE UNICO ------------------------------------------------------
-- Sin el no se puede refrescar sin bloquear a quien este leyendo la pantalla.
-- Sobre columna desnuda: `asin` es NOT NULL por construccion (los tres CTE
-- filtran `asin IS NOT NULL` o `<> ''`), asi que no hace falta coalescer nada.
CREATE UNIQUE INDEX mv_ventas_ventanas_asin_uk ON public.mv_ventas_ventanas (asin);

COMMENT ON MATERIALIZED VIEW public.mv_ventas_ventanas IS
    'Ventanas de ventas por ASIN, materializadas el 25-ago-2026. Se refresca desde los procesadores del ledger y de las transacciones, atado al evento que cambia el dato y no al reloj. NO lleva dias_desde_ultimo_dato a proposito: esa columna depende de CURRENT_DATE y aqui se congelaria; la calcula la vista v_ventas_ventanas, que es la que lee todo el mundo.';

-- -- 3) LA PUERTA · una mv no aplica RLS, asi que el GRANT es todo -----------
-- 🔬 CON QUE ROL SE APLICA ESTO, medido el 25-ago-2026: como `postgres` (todos
--    los objetos de las migraciones recientes --inventario_fba, salud_fba,
--    mv_trackeador_pantalla-- tienen `relowner = postgres`). Y en `public`
--    conviven DOS reglas de `pg_default_acl`:
--      creados por `postgres`       -> {postgres, service_role}            <- la nuestra
--      creados por `supabase_admin` -> {postgres, service_role, authenticated, ANON}
--    O sea que HOY la mv nace CERRADA y el REVOKE de abajo es un cinturon; el
--    que hace falta de verdad es el GRANT a `authenticated`, sin el cual la
--    pantalla se queda sin datos. **El REVOKE se queda igual**: el dia que esto
--    se aplique con `supabase_admin`, es el unico freno.
--
-- 🔴 Y LO QUE ESTA EN JUEGO SI NACIERA ABIERTA, medido para esta vista: sus
--    tres fuentes --ledger_movimientos, transacciones_movimientos y
--    listings_amazon-- son HOY ILEGIBLES para `anon`. Las dos ultimas tienen el
--    GRANT heredado de la v1, pero su RLS no tiene ni una politica que alcance a
--    `anon`, asi que devuelven CERO filas (el permiso no es la puerta: la
--    politica si). Una materializada NO tiene RLS detras. Si esta naciera
--    abierta, el movimiento del ledger seria legible anonimamente POR PRIMERA
--    VEZ: un agujero NUEVO abierto por nosotros, no heredado.
REVOKE ALL ON public.mv_ventas_ventanas FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_ventas_ventanas TO authenticated;

-- -- 4) LA VISTA DE ENCIMA · mismo nombre, mismo OID, mismo contrato ---------
-- 🔒 CREATE OR REPLACE (no DROP+CREATE): conserva el OID, asi que los diez
--    objetos que cuelgan de aqui no se enteran, y conserva los ACL.
-- 🔴 Las 16 columnas en el MISMO orden, y la del reloj calculada AQUI, viva.
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
       -- 🔒 AL FINAL, y no por gusto: `CREATE OR REPLACE VIEW` solo admite ANADIR
       --    columnas al final. Meterla en medio obligaria a un DROP, y un DROP aqui se
       --    lleva por delante los diez objetos que cuelgan.
       ventana_hasta_listings
  FROM public.mv_ventas_ventanas;

-- -- TESTIGO · el contrato y el dato, no el log ------------------------------
DO $testigo$
DECLARE
    -- 🔬 La huella del contrato de salida, MEDIDA contra la vista original el
    --    25-ago-2026 antes de aplicar nada (293 filas, 15 columnas estables).
    --    Valor perecedero: despues de aplicar ya no se puede recalcular contra
    --    el original. Por eso viaja escrito aqui.
    HUELLA_ANTES constant text := '747d612229bda09cc3418fa46115f93c';
    -- Las filas que tenia PRODUCCION cuando se midio esa huella. Si la base no tiene
    -- exactamente estas, la huella no aplica y se dice (ver mas abajo).
    FILAS_DE_LA_HUELLA constant bigint := 293;
    n_mv       bigint;
    n_vista    bigint;
    n_cols     int;
    ultima     text;
    dias       int;
    hasta      date;
    huella_hoy text;
BEGIN
    SELECT count(*) INTO n_mv FROM mv_ventas_ventanas;
    SELECT count(*) INTO n_vista FROM v_ventas_ventanas;

    -- 1) El dato no ha cambiado de tamano.
    IF n_mv = 0 OR n_vista = 0 THEN
        RAISE EXCEPTION 'ABORTA: mv=% filas, vista=% filas. Algo se ha quedado vacio.', n_mv, n_vista;
    END IF;
    IF n_mv <> n_vista THEN
        RAISE EXCEPTION 'ABORTA: la mv tiene % filas y la vista %. La vista de encima no puede perder ni anadir filas.', n_mv, n_vista;
    END IF;

    -- 2) EL CONTRATO: las 16 de antes intactas + la 17.a anadida al final. Es lo
    --    que impide que los diez objetos que cuelgan se rompan.
    SELECT count(*) INTO n_cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_ventas_ventanas';
    IF n_cols <> 17 THEN
        RAISE EXCEPTION 'ABORTA: la vista quedo con % columnas y tenian que ser 17 (las 16 de antes + ventana_hasta_listings).', n_cols;
    END IF;
    -- 🔒 La 16.a sigue siendo la del reloj: si se hubiera colado la nueva EN MEDIO,
    --    el orden del contrato habria cambiado para los diez que cuelgan.
    SELECT column_name INTO ultima FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_ventas_ventanas'
       AND ordinal_position = 16;
    IF ultima <> 'dias_desde_ultimo_dato' THEN
        RAISE EXCEPTION 'ABORTA: la columna 16 es % y tenia que seguir siendo dias_desde_ultimo_dato. La nueva se ha colado en medio.', ultima;
    END IF;
    SELECT column_name INTO ultima FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_ventas_ventanas'
     ORDER BY ordinal_position DESC LIMIT 1;
    IF ultima <> 'ventana_hasta_listings' THEN
        RAISE EXCEPTION 'ABORTA: la ultima columna es % y tenia que ser ventana_hasta_listings.', ultima;
    END IF;

    -- 🔴 Y EL ANCLA NUEVA TIENE QUE CUADRAR CON SU FUENTE, que es para lo que existe.
    IF (SELECT ventana_hasta_listings FROM v_ventas_ventanas LIMIT 1)
       IS DISTINCT FROM (SELECT max(fecha_informe) FROM listings_amazon) THEN
        RAISE EXCEPTION 'ABORTA: ventana_hasta_listings no coincide con max(fecha_informe) de listings_amazon. El ancla de la tercera fuente no mide lo que dice medir.';
    END IF;

    -- 3) 🔴 LA COLUMNA DEL RELOJ SIGUE VIVA, que es la mitad de este diseno. Se
    --    ancla sobre lo que NO debe pasar: si se hubiera materializado, seria
    --    una constante guardada y no cuadraria con la cuenta de hoy.
    SELECT dias_desde_ultimo_dato, ventana_hasta_ledger INTO dias, hasta
      FROM v_ventas_ventanas LIMIT 1;
    IF dias IS DISTINCT FROM (CURRENT_DATE - hasta) THEN
        RAISE EXCEPTION 'ABORTA: dias_desde_ultimo_dato=% y CURRENT_DATE - ventana_hasta_ledger=%. La columna del reloj no se esta calculando en la vista.', dias, (CURRENT_DATE - hasta);
    END IF;
    -- Y que NO este dentro de la materializada, que es de donde se saco.
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='mv_ventas_ventanas'
                  AND column_name='dias_desde_ultimo_dato') THEN
        RAISE EXCEPTION 'ABORTA: dias_desde_ultimo_dato esta DENTRO de la materializada. Ahi se congela: es la cifra que miente.';
    END IF;

    -- 4) El indice unico existe y es el que el refresco necesita.
    IF NOT EXISTS (SELECT 1 FROM pg_index i
                    WHERE i.indrelid = 'public.mv_ventas_ventanas'::regclass
                      AND i.indisunique) THEN
        RAISE EXCEPTION 'ABORTA: la materializada no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo la pantalla.';
    END IF;

    -- 5) 🔴 EL CONTRATO DE SALIDA, POR SU HUELLA. Es el testigo mas barato y el
    --    mas concluyente, y es el que faltaba: los de arriba prueban que la
    --    COPIA es fiel (recuentos, columnas), pero lo que hay que demostrar es
    --    que lo que sale por la vista NO SE HA MOVIDO. Y eso solo lo dice la
    --    misma huella, calculada arriba, despues.
    -- 🔬 El valor se midio contra la vista ORIGINAL el 25-ago-2026, ANTES de
    --    aplicar nada, corriendo el cuerpo de la mv y la vista vieja lado a
    --    lado: las dos dieron 747d612229bda09cc3418fa46115f93c sobre 293 filas.
    --    Es un valor PERECEDERO: despues de aplicar ya no se puede recalcular
    --    contra el original, por eso queda escrito aqui y en el cuerpo del PR.
    -- ⚠️ Sobre las 15 columnas ESTABLES, no las 16. `dias_desde_ultimo_dato`
    --    depende de CURRENT_DATE, asi que meterla haria que esta huella
    --    caducara manana. Esa columna tiene su propio testigo, el (3).
    SELECT md5(string_agg(t::text, '|' ORDER BY t.asin)) INTO huella_hoy
      FROM (SELECT asin, uds_7d, uds_30d, uds_60d, uds_90d, vel_dia_30d, vel_dia_90d,
                   uds_30d_es, uds_30d_it, uds_30d_fr, uds_30d_marketplace,
                   eur_30d_marketplace, devoluciones_30d,
                   ventana_hasta_ledger, ventana_hasta_marketplace
              FROM v_ventas_ventanas) t;
    -- 🔴 LA HUELLA SOLO VALE SOBRE LA BASE EN LA QUE SE MIDIO. Se tomo en PRODUCCION,
    --    sobre sus 293 filas. Staging tiene otras (290 el 25-ago): alli esta huella no
    --    puede coincidir, y compararla haria ABORTAR EL ENSAYO POR EL DATO, no por la
    --    migracion -- el ruido futuro de la seccion 3, y encima en el peldano que existe
    --    para dar confianza.
    -- 🔒 Asi que se comprueba donde puede comprobarse y se GRITA donde no, diciendo que
    --    no se ha comprobado. Nunca se apaga en silencio.
    IF n_mv <> FILAS_DE_LA_HUELLA THEN
        RAISE WARNING 'HUELLA NO COMPROBADA EN ESTE ENTORNO: la huella % se midio sobre PRODUCCION con % filas y aqui hay %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que el contrato de salida no se haya movido; ESO SE VERIFICA EN PRODUCCION, al aplicar.', HUELLA_ANTES, FILAS_DE_LA_HUELLA, n_mv;
    ELSIF huella_hoy <> HUELLA_ANTES THEN
        RAISE EXCEPTION 'ABORTA: la huella de v_ventas_ventanas es % y antes de aplicar era %. El contrato de salida ha CAMBIADO: algo de la definicion no se copio igual. No se sigue.', huella_hoy, HUELLA_ANTES;
    END IF;

    -- 6) 🔴 LA PUERTA SE PRUEBA EJERCIENDOLA, NO LEYENDO EL CATALOGO. Consultar
    --    `has_table_privilege` o `role_table_grants` dice lo que esta ESCRITO,
    --    no lo que pasa: es la misma familia que el grep sobre comentarios. La
    --    unica prueba es entrar como anon y que rebote.
    --    (Una materializada NO aplica RLS, asi que aqui no hay red detras del
    --     GRANT: si esto no rebota, el dato esta abierto de verdad.)
    --
    -- 🔒 TRES CERROJOS DE ESTE BLOQUE, para los siete que vienen detras. Copiar
    --    el bloque sin ellos lo convierte en decoracion:
    --
    --    a) SE CAZA `insufficient_privilege`, **NUNCA `OTHERS`**. Con `OTHERS`,
    --       el propio `RAISE EXCEPTION` con el que se grita "la puerta esta
    --       abierta" se lo come este mismo manejador, y el testigo pasa a ser
    --       INCAPAZ DE FALLAR. Comprobado el 25-ago-2026 en staging: con la
    --       puerta abierta a proposito, el P0001 atraviesa el manejador y el
    --       bloque aborta como debe.
    --
    --    b) El `RESET ROLE` del manejador es un cinturon, no el mecanismo: un
    --       bloque con EXCEPTION es una subtransaccion, y al saltar el rollback
    --       deshace tambien el `SET LOCAL ROLE`. El rol vuelve solo.
    --
    --    c) ⚠️ **STAGING NO REPRODUCE HOY LOS PERMISOS DE PRODUCCION, Y ASI SE
    --       ARREGLA.** Medido el 25-ago-2026: de los objetos de `public`,
    --       produccion tiene 114 con permisos para `authenticated` y 53 con
    --       permiso para `anon` --de los que la POLITICA solo deja leer 26; los
    --       otros 27 estan cerrados de hecho--; staging tiene **4 y CERO**.
    --       (El permiso y la politica son DOS cerraduras: contar solo permisos
    --        mide la cantidad equivocada.) Causa: `backup-bd.yml` vuelca
    --       con `--no-privileges`, asi que el dump no lleva ni un GRANT y
    --       `restaurar-staging.yml` no los repone.
    --       CONSECUENCIA MIENTRAS SIGA ASI: alli la mitad del `anon` de este
    --       bloque sale verde no porque el REVOKE funcione, sino porque no
    --       habia nada que revocar --VERDE VACIO--, y por eso **el testigo del
    --       anon se cree EN PRODUCCION, despues de aplicar**. La mitad de
    --       `authenticated` si vale en staging: ese GRANT lo pone esta misma
    --       migracion.
    --       🔑 **Y ESTO ES UNA BANDERA, NO UNA LEY.** El arreglo existe y es
    --       barato: leer los ACL de produccion de `pg_class.relacl`, convertirlos
    --       en sentencias GRANT y reproducirlos en staging despues de cada
    --       restauracion. Un guion, una vez, y staging pasa de 4 de 117 a
    --       reproducir los 114. **No se ha hecho todavia, no es que no se pueda.**
    --       El dia que se haga, esta nota se borra y el testigo del anon empieza
    --       a valer tambien en staging.
    --
    --    🔬 LOS DOS CAMINOS, PROBADOS ROMPIENDOLOS (25-ago-2026, en staging,
    --       sobre una materializada de usar y tirar):
    --         · con `GRANT SELECT TO anon` a proposito -> ROJO, contando 1 fila
    --         · tras el `REVOKE`                       -> callado
    --         · sin `GRANT SELECT TO authenticated`    -> ROJO, "se quedaria sin datos"
    --         · con el grant puesto                    -> callado
    --       Las dos mitades, en las dos direcciones. La de `authenticated` no es
    --       menos importante: protege a Elena de un REVOKE demasiado ancho, y su
    --       fallo seria mudo (pantalla vacia con el testigo diciendo que bien).
    RAISE NOTICE 'Testigo OK (contrato). mv=% filas, vista=% filas, 17 columnas, dias_desde_ultimo_dato VIVA (=%), huella %, indice unico puesto.', n_mv, n_vista, dias, huella_hoy;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · en bloques PROPIOS, y no por gusto ---------------
-- 🔴 CADA MITAD EN SU `DO`, porque un `BEGIN ... EXCEPTION ... END;` anidado deja
--    una linea `END;` suelta, y el cerrojo 4 del workflow la RECHAZA: fuera de
--    PL/pgSQL, `END;` es sinonimo de `COMMIT;` y ese cerrojo existe para que
--    ningun fichero cierre la transaccion por su cuenta. No puede distinguir un
--    `END;` de PL/pgSQL de uno de SQL, y hace bien en no fiarse.
--    Un `DO $x$ ... END $x$;` no deja esa linea. Mismo testigo, sin falso positivo.
--    (Cazado al subir la escalera, no leyendo el fichero.)
DO $puerta_anon$
DECLARE
    n_anon bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_ventas_ventanas' INTO n_anon;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_ventas_ventanas y ha contado % filas. La puerta esta abierta, y ningun catalogo te lo iba a decir.', n_anon;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;   -- lo esperado: rebota
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_ventas_ventanas.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n_auth bigint;
    n_mv   bigint;
BEGIN
    SELECT count(*) INTO n_mv FROM mv_ventas_ventanas;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_ventas_ventanas' INTO n_auth;
    RESET ROLE;
    IF n_auth <> n_mv THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la mv tiene %.', n_auth, n_mv;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n_auth;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_ventas_ventanas. La app se quedaria sin datos y la pantalla vacia.';
END
$puerta_auth$;
