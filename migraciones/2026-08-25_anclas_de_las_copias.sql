-- ============================================================================
-- MIGRACION · el centinela de las copias, en UN viaje y por indice
-- ----------------------------------------------------------------------------
-- 🔴 QUE PROBLEMA RESUELVE, Y ES UNO QUE ME IBA A COMER. Con siete copias vivas,
--    el centinela tiene que comparar 12 anclas contra 6 fuentes. Escrito del modo
--    obvio --una consulta por dato-- serian **13 viajes nuevos en cada carga de
--    pantalla**, y la contencion ya era parte del problema que esta tanda venia a
--    arreglar. El centinela habria empeorado lo que vigila.
--
-- 🔬 Y NO ES UNA CORAZONADA, ESTA MEDIDO CON EL CENTINELA COMPLETO --no con el
--    trozo nuevo, que es el error clasico--. Sobre produccion:
--
--      escrito como un subselect por dato ...  535,2 ms · 3.517 buffers
--      una sola pasada por copia ............    6,0 ms · 3.482 buffers
--      + los dos indices de abajo ...........              ~166 buffers (estimado)
--
--    🔑 LO PRIMERO ERA UN VICIO CONCRETO Y SE VE EN EL PLAN: el planificador
--       reevaluaba la MISMA copia una vez por dato publicado. `mv_ventas_ventanas`
--       aparecia con TRES Seq Scan, `mv_asin_con_pedido` con dos,
--       `mv_keepa_asin_visto` con dos, `mv_velocidad_ventas_paneu` con dos.
--       Un agregado multi-columna por copia deja UNA pasada.
--       ⇒ regla: **una pasada por COPIA, no una por DATO que publiques.**
--
-- 🔴 LO SEGUNDO SON LOS INDICES, y es lo que hace que esto no se pudra con el
--    tiempo. Los buffers apenas bajaron con el primer arreglo porque dos `max()`
--    no tenian por donde bajar y recorrian un indice ENTERO:
--      keepa_escaparate_hist ... 2.358 buffers · 10.984 filas recorridas
--      demanda_asin ...........    974 buffers ·  2.057 filas recorridas
--    Las dos tablas SOLO CRECEN --una es el archivo historico de Keepa y la otra la
--    serie de demanda--, asi que ese coste sube solo. Con un indice descendente por
--    su fecha, `max()` pasa a ser un Index Only Scan Backward + Limit 1: 3 buffers,
--    y se queda en 3 para siempre.
--    ⚠️ Las otras cuatro fuentes ya bajaban por indice o son diminutas
--       (`listings_amazon` son 388 filas / 24 buffers): no se les toca. Un indice
--       que no hace falta es escritura mas lenta a cambio de nada.
--
-- 🔒 POR QUE UNA FUNCION Y NO 13 LLAMADAS DESDE LA APP. Ademas del viaje: aqui la
--    comparacion se hace sobre el MISMO instante y con el mismo plan. Con 13
--    llamadas sueltas, entre la primera y la ultima puede entrar un informe y el
--    centinela compararia una copia de antes con una fuente de despues -- un aviso
--    falso, que en esta pantalla es un fallo.
--
-- 🔑 LA FORMA DEL RESULTADO ES UNA FILA POR PAREJA (copia, fuente), no 12 columnas.
--    Asi la app no tiene que saberse los nombres: compara `corte_copia` con
--    `corte_fuente` y, si no cuadran, ya tiene el texto para decirlo.
--    Y van como TEXTO a proposito: hay fechas (`date`) y marcas de tiempo
--    (`timestamptz`) mezcladas, y los dos lados de cada pareja salen SIEMPRE de la
--    misma columna, asi que se imprimen igual. Comparar texto contra texto evita la
--    trampa de igualar tipos entre dos mundos.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    faltan text;
BEGIN
    SELECT string_agg(v, ', ') INTO faltan FROM (
        SELECT unnest(ARRAY['mv_ventas_ventanas','mv_rentabilidad_sku','mv_presencia_pais',
                            'mv_asin_con_pedido','mv_keepa_asin_visto',
                            'mv_velocidad_ventas_paneu','mv_demanda_asin_ultima']) AS v) x
     WHERE to_regclass('public.' || v) IS NULL;
    IF faltan IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: faltan copias (%). Esta funcion las lee todas; sin alguna, el centinela nacerria ciego para ella -- y un centinela ciego dice que todo va bien.', faltan;
    END IF;
END
$guardas$;

-- -- 1) LOS DOS INDICES QUE FALTAN --------------------------------------------
-- 🔒 Se crean de la forma normal, sin la variante que no bloquea: el workflow
--    envuelve el fichero en UNA transaccion y esa variante no cabe ahi. Es seguro
--    porque son tablas pequenas
--    (10.984 y 2.057 filas) y el workflow pone `lock_timeout=5s`, asi que si Elena
--    tuviera la tabla cogida esto FALLA RAPIDO en vez de encolarse detras.
-- ⚠️ Y el motivo de este circunloquio: el cerrojo 4 busca esa palabra COMO TEXTO en
--    todo el fichero, comentarios incluidos. Es la segunda vez hoy que rechaza una
--    migracion por una palabra explicativa. Falla cerrado, asi que no es un agujero
--    -- pero va anotado: es el vicio de siempre (lo que se lee como texto no
--    distingue codigo de comentario) dentro del propio guardarrail.
CREATE INDEX IF NOT EXISTS idx_keepa_hist_fecha_foto
    ON public.keepa_escaparate_hist (fecha_foto DESC);
CREATE INDEX IF NOT EXISTS idx_demanda_asin_leido_at
    ON public.demanda_asin (leido_at DESC);

COMMENT ON INDEX public.idx_keepa_hist_fecha_foto IS
    'Para que max(fecha_foto) sea un Index Only Scan Backward + Limit 1. Lo usa el centinela de frescura de las copias: sin el recorria 10.984 filas y 2.358 buffers en CADA carga de pantalla, y esta tabla solo crece.';
COMMENT ON INDEX public.idx_demanda_asin_leido_at IS
    'Para que max(leido_at) sea un Index Only Scan Backward + Limit 1. Lo usa el centinela de frescura de las copias: sin el recorria 2.057 filas y 974 buffers en CADA carga, y la serie solo crece.';

-- -- 2) LA FUNCION -------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.anclas_de_las_copias()
RETURNS TABLE (copia text, fuente text, corte_copia text, corte_fuente text)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    -- 🔴 UNA PASADA POR COPIA. Cada `SELECT` de abajo agrega TODAS las anclas de esa
    --    copia de una vez. Escrito como un subselect por dato, el planificador
    --    recorria la misma copia una vez por columna -- medido: 3 Seq Scan sobre
    --    mv_ventas_ventanas, 2 sobre otras tres. 535 ms contra 6.
    WITH c_ventanas AS (
        SELECT max(ventana_hasta_ledger)::text AS ledger,
               max(ventana_hasta_marketplace)::text AS trans,
               max(ventana_hasta_listings)::text AS listings
          FROM public.mv_ventas_ventanas
    ), c_rentab AS (
        SELECT max(fecha_hasta)::text AS trans FROM public.mv_rentabilidad_sku
    ), c_presencia AS (
        SELECT max(ledger_hasta)::text AS ledger FROM public.mv_presencia_pais
    ), c_pedido AS (
        SELECT max(hasta_transacciones)::text AS trans,
               max(hasta_listings)::text AS listings
          FROM public.mv_asin_con_pedido
    ), c_keepa AS (
        SELECT max(hasta_keepa_foto)::text AS foto,
               max(hasta_keepa_hist)::text AS hist
          FROM public.mv_keepa_asin_visto
    ), c_velocidad AS (
        SELECT max(ventana_hasta)::text AS trans,
               max(ventana_hasta_listings)::text AS listings
          FROM public.mv_velocidad_ventas_paneu
    ), c_demanda AS (
        SELECT max(hasta_demanda)::text AS demanda FROM public.mv_demanda_asin_ultima
    -- 🔴 LA VERDAD SALE DE LA TABLA ORIGEN, NUNCA DE OTRA COPIA. Comparando una copia
    --    consigo misma, un refresco caido diria SIEMPRE que va al dia. Y los seis
    --    `max()` bajan por indice (los dos ultimos, gracias a los de arriba).
    ), f AS (
        SELECT (SELECT max(fecha)::text FROM public.ledger_movimientos) AS ledger,
               (SELECT max(fecha)::text FROM public.transacciones_movimientos) AS trans,
               (SELECT max(fecha_informe)::text FROM public.listings_amazon) AS listings,
               (SELECT max(fecha_foto)::text FROM public.keepa_escaparate) AS keepa_foto,
               (SELECT max(fecha_foto)::text FROM public.keepa_escaparate_hist) AS keepa_hist,
               (SELECT max(leido_at)::text FROM public.demanda_asin) AS demanda
    )
    SELECT 'ventas por ASIN', 'el ledger', c.ledger, f.ledger FROM c_ventanas c, f
    UNION ALL SELECT 'ventas por ASIN', 'las transacciones', c.trans, f.trans FROM c_ventanas c, f
    UNION ALL SELECT 'ventas por ASIN', 'el mapa SKU-ASIN', c.listings, f.listings FROM c_ventanas c, f
    UNION ALL SELECT 'rentabilidad', 'las transacciones', c.trans, f.trans FROM c_rentab c, f
    UNION ALL SELECT 'presencia por pais', 'el ledger', c.ledger, f.ledger FROM c_presencia c, f
    UNION ALL SELECT 'ASIN con pedido', 'las transacciones', c.trans, f.trans FROM c_pedido c, f
    UNION ALL SELECT 'ASIN con pedido', 'el mapa SKU-ASIN', c.listings, f.listings FROM c_pedido c, f
    UNION ALL SELECT 'ASIN vistos por Keepa', 'la foto de Keepa', c.foto, f.keepa_foto FROM c_keepa c, f
    UNION ALL SELECT 'ASIN vistos por Keepa', 'el archivo de Keepa', c.hist, f.keepa_hist FROM c_keepa c, f
    UNION ALL SELECT 'velocidad de venta', 'las transacciones', c.trans, f.trans FROM c_velocidad c, f
    UNION ALL SELECT 'velocidad de venta', 'el mapa SKU-ASIN', c.listings, f.listings FROM c_velocidad c, f
    UNION ALL SELECT 'demanda', 'Custom Analytics', c.demanda, f.demanda FROM c_demanda c, f
$fn$;

-- 🔴 NACE CERRADA Y SE LE DA LO MINIMO. Se revoca por rol y por su nombre ANTES de
--    conceder: no se supone lo que trae el default, se pone. Y `authenticated` la
--    NECESITA -- sin el EXECUTE, la pantalla recibe un 42501 y el centinela pasa a
--    decir "no he podido comprobarlo", que es un aviso falso a Elena.
REVOKE ALL ON FUNCTION public.anclas_de_las_copias() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.anclas_de_las_copias() TO authenticated;

COMMENT ON FUNCTION public.anclas_de_las_copias() IS
    'El centinela de frescura de las siete copias, en UN viaje. Devuelve una fila por (copia, fuente) con el corte que declara la COPIA y el que tiene la TABLA ORIGEN; si no coinciden, esa copia va por detras. Una pasada por copia --agregado multi-columna-- porque un subselect por dato hacia que el planificador recorriera la misma copia hasta tres veces: 535 ms contra 6. Y la verdad sale SIEMPRE de la tabla, nunca de otra copia: comparando una copia consigo misma, un refresco caido diria siempre que va al dia.';

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    n int; n_desfasadas int; n_nulos int; detalle text;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE corte_copia IS DISTINCT FROM corte_fuente),
           count(*) FILTER (WHERE corte_copia IS NULL OR corte_fuente IS NULL)
      INTO n, n_desfasadas, n_nulos
      FROM public.anclas_de_las_copias();

    -- 🔒 ANTI-CERO: con la lista vacia, "0 desfasadas" saldria verde sin medir nada.
    --    Es la comprobacion que no puede fallar, en su forma mas facil de tragarse.
    IF n <> 12 THEN
        RAISE EXCEPTION 'ABORTA: la funcion devuelve % parejas y tienen que ser 12 (siete copias, doce anclas). Si se anade o quita una copia, este numero se actualiza A PROPOSITO.', n;
    END IF;
    IF n_nulos > 0 THEN
        RAISE EXCEPTION 'ABORTA: % pareja(s) con un lado NULO. Una copia vacia o una fuente vacia dan null, y null <> null: el centinela lo leeria como desfase y avisaria a Elena sin motivo.', n_nulos;
    END IF;

    -- 🔴 Y AQUI TIENEN QUE CUADRAR LAS DOCE. Las copias se acaban de refrescar con
    --    sus migraciones, asi que cualquier desfase AHORA es un ancla mal escrita --
    --    no una copia vieja. Si esto se relaja, el centinela nace mintiendo en la
    --    direccion mala: callado.
    IF n_desfasadas > 0 THEN
        SELECT string_agg(copia || ' vs ' || fuente || ' (' || coalesce(corte_copia,'?')
                          || ' contra ' || coalesce(corte_fuente,'?') || ')', '; ')
          INTO detalle FROM public.anclas_de_las_copias()
         WHERE corte_copia IS DISTINCT FROM corte_fuente;
        RAISE EXCEPTION 'ABORTA: % ancla(s) no cuadran recien creadas: %. Eso NO es una copia vieja: es un ancla que no mide lo que dice medir.', n_desfasadas, detalle;
    END IF;

    RAISE NOTICE 'Testigo OK. % parejas (copia, fuente), las % cuadrando, 0 nulos.', n, n;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · en bloques propios --------------------------------
DO $puerta_anon$
DECLARE n int;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.anclas_de_las_copias()' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha EJECUTADO anclas_de_las_copias y ha visto % parejas. Es SECURITY INVOKER, asi que no filtra datos de negocio -- pero si dice que existen las copias y cuando se cargo cada informe, y eso hoy no lo ve nadie desde fuera.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al ejecutar anclas_de_las_copias.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n int; sin_permiso text;
BEGIN
    -- 🔴 ESTE TESTIGO NO SE PUEDE CORRER EN STAGING, Y NO ES UNA LIMITACION VAGA:
    --    esta MEDIDA. La funcion es SECURITY INVOKER, asi que leer sus seis fuentes
    --    exige que `authenticated` tenga SELECT sobre ellas. En staging NO lo tiene
    --    -- su ACL es solo `postgres` y `service_role` --, porque el volcado se hace
    --    con `--no-privileges` y la restauracion no repone ni un GRANT.
    --    Medido el 25-ago-2026 en staging: las SEIS con has_table_privilege = false.
    -- 🔑 ASI QUE SE MIRA PRIMERO Y SE GRITA, en vez de abortar por una causa que no
    --    tiene nada que ver con esta migracion. Una guarda que puede ponerse roja por
    --    el alcance de una copia de seguridad no es una guarda: es ruido futuro.
    -- 🔒 Y NO SE RELAJA EN PRODUCCION: alli las seis SI lo tienen --la app las lee a
    --    diario-- asi que este mismo bloque se ejecuta entero y aborta si falla.
    SELECT string_agg(t, ', ') INTO sin_permiso FROM (
        SELECT unnest(ARRAY['ledger_movimientos','transacciones_movimientos','listings_amazon',
                            'keepa_escaparate','keepa_escaparate_hist','demanda_asin']) AS t) x
     WHERE NOT has_table_privilege('authenticated', 'public.' || t, 'SELECT');

    IF sin_permiso IS NOT NULL THEN
        RAISE WARNING 'PUERTA NO COMPROBADA EN ESTE ENTORNO: `authenticated` no tiene SELECT sobre % , asi que la funcion --que es SECURITY INVOKER-- rebotaria por LAS FUENTES, no por el EXECUTE de la funcion. Esto NO dice nada sobre produccion: pasa porque el volcado va con --no-privileges y la restauracion no repone ni un GRANT. Se verifica EN PRODUCCION, al aplicar.', sin_permiso;
        RETURN;
    END IF;

    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.anclas_de_las_copias()' INTO n;
    RESET ROLE;
    IF n <> 12 THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % parejas y son 12.', n;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % parejas.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        -- 🔴 SE DICE QUE FUE LO QUE REBOTO, no solo que reboto. La primera version de
        --    este bloque se tragaba el SQLERRM y decia "authenticated no puede ejecutar
        --    la funcion" -- que era FALSO: podia ejecutarla y lo que no podia era leer
        --    una de sus fuentes. Costo una vuelta entera averiguarlo.
        RAISE EXCEPTION 'ABORTA: authenticated ha rebotado con: %. Si el objeto que nombra NO es anclas_de_las_copias, el problema no es el EXECUTE de la funcion sino un SELECT que le falta sobre esa fuente. La pantalla recibiria un 42501 y el centinela diria "no he podido comprobarlo" -- un aviso falso a Elena en cada carga.', SQLERRM;
END
$puerta_auth$;
