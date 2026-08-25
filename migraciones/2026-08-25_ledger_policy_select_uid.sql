-- ============================================================================
-- MIGRACION · la politica del LEDGER deja de llamar a auth.uid() FILA A FILA
-- ----------------------------------------------------------------------------
-- UNA LINEA, y va SOLA y ANTES que la materializacion de `v_ventas_ventanas`.
-- No es la regla por la regla: si las dos entraran juntas y la consulta de
-- Inventario bajara a 400 ms, NO se sabria cual de las dos lo hizo -- y el plan
-- de repliegue (volver a la fase 0.2 si no baja) depende justo de poder
-- atribuirlo. Separadas, cada numero tiene dueno.
--
-- EL FALLO, medido en produccion el 25-ago-2026 sobre `pg_policies`:
--
--    ledger_movimientos        ->  (auth.uid() IS NOT NULL)            <- esta
--    inventario_fba            ->  ((SELECT auth.uid()) IS NOT NULL)
--    keepa_escaparate          ->  ((SELECT auth.uid()) IS NOT NULL)
--    listings_amazon           ->  ((SELECT auth.uid()) IS NOT NULL)
--    transacciones_movimientos ->  ((SELECT auth.uid()) IS NOT NULL)
--
-- Cuatro tablas la tienen envuelta en un SELECT y una no. Sin ese SELECT,
-- Postgres trata auth.uid() como una expresion que depende de la fila y la
-- evalua UNA VEZ POR FILA; con el la trata como un subplan constante (InitPlan)
-- y la evalua UNA VEZ para toda la consulta.
--
-- POR QUE DUELE AQUI Y NO EN OTRO SITIO: ledger_movimientos tiene 20.317 filas
-- (medido hoy) y es la tabla que mas pesa dentro de v_ventas_ventanas: 1.254 ms
-- de los 1.904 que cuesta esa vista, que a su vez es el 92 % de la consulta de
-- Inventario. Son ~20.000 llamadas a una funcion donde deberia haber una.
--
-- LO QUE ESTA MIGRACION **NO** CAMBIA: quien puede leer. Las dos formas son la
-- MISMA condicion --hay sesion iniciada--, evaluada una vez en vez de veinte
-- mil. No hay filtrado por usuario ni antes ni despues. Si esto cambiara el
-- conjunto de filas visibles, el testigo de abajo ABORTA.
--
-- ALTER POLICY, no DROP + CREATE: con el drop hay un instante en el que la
-- tabla se queda sin politica y la lectura de Elena devolveria 0 filas. Es la
-- misma transaccion y nadie lo veria, pero no hace falta correr ese riesgo para
-- cambiar una expresion.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    q       text;
    n_filas bigint;
    n_pol   int;
BEGIN
    SELECT count(*) INTO n_pol
      FROM pg_policies WHERE schemaname = 'public' AND tablename = 'ledger_movimientos';
    IF n_pol <> 1 THEN
        RAISE EXCEPTION 'ABORTA: ledger_movimientos tiene % politicas y se esperaba exactamente 1. Alguien ha tocado la tabla: miralo antes de seguir.', n_pol;
    END IF;

    SELECT qual INTO q FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'ledger_movimientos'
       AND policyname = 'inventario_read_authenticated';
    IF q IS NULL THEN
        RAISE EXCEPTION 'ABORTA: no existe la politica inventario_read_authenticated sobre ledger_movimientos.';
    END IF;

    -- UN ENSAYO SOBRE UN ESTADO QUE YA ES EL DE DESTINO NO PRUEBA NADA (seccion 3
    -- de CLAUDE.md). Si la politica YA lleva el SELECT, esto no cambiaria nada y
    -- saldria verde verificando algo que era cierto antes de empezar.
    IF position('SELECT auth.uid()' in q) > 0 THEN
        RAISE EXCEPTION 'ABORTA: la politica YA esta en la forma con SELECT (%). Este ensayo saldria verde sin demostrar nada.', q;
    END IF;
    IF q <> '(auth.uid() IS NOT NULL)' THEN
        RAISE EXCEPTION 'ABORTA: la politica dice [%] y se esperaba [(auth.uid() IS NOT NULL)]. No se reescribe una condicion que no es la que se midio.', q;
    END IF;

    -- La pregunta anti-cero: sin filas, el testigo de igualdad no distinguiria
    -- "no cambio nada" de "no habia nada que contar".
    SELECT count(*) INTO n_filas FROM ledger_movimientos;
    IF n_filas < 1000 THEN
        RAISE EXCEPTION 'ABORTA: ledger_movimientos tiene % filas. Con la tabla casi vacia ni el problema existe ni el testigo mide nada.', n_filas;
    END IF;
    RAISE NOTICE 'Guardas OK. 1 politica, forma vieja confirmada, % filas de ledger.', n_filas;
END
$guardas$;

-- -- EL CAMBIO ---------------------------------------------------------------
ALTER POLICY inventario_read_authenticated ON public.ledger_movimientos
    USING ((SELECT auth.uid()) IS NOT NULL);

COMMENT ON TABLE public.ledger_movimientos IS
    'Pelicula (append) de movimientos de Amazon. Su politica RLS envuelve auth.uid() en un SELECT a proposito: sin el, Postgres la evalua una vez POR FILA (20.317 llamadas el 25-ago-2026) en vez de una vez por consulta. Misma condicion, mismo control de acceso.';

-- -- TESTIGO. Se mide el EFECTO con el rol de la app, no el texto -------------
-- Comprobar que pg_policies.qual ya dice SELECT seria la comprobacion que no
-- puede fallar: se cumple por construccion en cuanto corre el ALTER de arriba.
-- Lo que hay que demostrar es (1) que el plan deja de llamar a la funcion por
-- fila y (2) que las filas visibles NO cambian. Las dos cosas solo se ven con
-- SET ROLE authenticated: como postgres, la RLS ni siquiera se aplica.
DO $testigo$
DECLARE
    linea    text;
    plan_txt text := '';
    n_auth   bigint;
    n_total  bigint;
    q        text;
BEGIN
    SELECT count(*) INTO n_total FROM ledger_movimientos;

    SET LOCAL ROLE authenticated;
    PERFORM set_config('request.jwt.claims',
                       '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}',
                       true);

    SELECT count(*) INTO n_auth FROM ledger_movimientos;

    FOR linea IN EXECUTE 'EXPLAIN (ANALYZE, COSTS OFF) SELECT count(*) FROM public.ledger_movimientos' LOOP
        plan_txt := plan_txt || linea || chr(10);
    END LOOP;

    RESET ROLE;

    -- 1) EL MISMO CONJUNTO DE FILAS. Es la mitad que importa: una politica mas
    --    rapida que ademas cambia lo que se ve no es una optimizacion.
    IF n_auth <> n_total THEN
        RAISE EXCEPTION 'ABORTA: como authenticated se ven % filas y la tabla tiene %. La reescritura ha cambiado QUE se ve, no solo cuanto tarda.', n_auth, n_total;
    END IF;
    IF n_auth = 0 THEN
        RAISE EXCEPTION 'ABORTA: 0 filas visibles como authenticated. Sin filas este testigo no comprueba nada, y ademas la pantalla se quedaria vacia.';
    END IF;

    -- 2) EL PLAN. Con el SELECT, la funcion se resuelve en un InitPlan una sola
    --    vez; sin el, se evalua en el Filter de cada fila. Se ancla sobre la
    --    marca que SOLO existe en la forma nueva.
    IF position('InitPlan' in plan_txt) = 0 THEN
        RAISE EXCEPTION 'ABORTA: el plan como authenticated NO trae InitPlan, o sea que auth.uid() se sigue evaluando por fila. El ALTER no ha surtido efecto donde importa. Plan: %', plan_txt;
    END IF;

    -- 3) La forma nueva, anclada sobre lo que ya NO debe aparecer.
    SELECT qual INTO q FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'ledger_movimientos'
       AND policyname = 'inventario_read_authenticated';
    IF q = '(auth.uid() IS NOT NULL)' THEN
        RAISE EXCEPTION 'ABORTA: la politica sigue con la forma vieja. El ALTER no ha hecho efecto.';
    END IF;

    RAISE NOTICE 'Testigo OK. % filas visibles como authenticated (= las % de la tabla), plan con InitPlan, politica [%].', n_auth, n_total, q;
END
$testigo$;
