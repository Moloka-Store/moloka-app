-- ============================================================================
-- MIGRACION · la HUELLA de la pantalla: lo que decide si lo cacheado sigue valiendo
-- ----------------------------------------------------------------------------
-- 🔴 PARA QUE ES. La pantalla de Inventario va a cachearse, y la forma de que una
--    cache NUNCA sirva un dato viejo no es detectarlo: es que el dato viejo **este
--    bajo otra clave y no se encuentre**. Esta funcion devuelve esa clave: una cadena
--    corta que cambia EXACTAMENTE cuando cambia algo de lo que la pantalla lee.
--
--    Entra un informe -> se refresca una copia -> la huella cambia -> fallo de cache
--    natural y recalculo. Entre informes, misma huella, acierto.
--
-- 🔑 Y ESO NO RESUELVE UNA LISTA DE PROBLEMAS: LA QUITA.
--      · no hace falta un secreto compartido
--      · ni una ruta de invalidacion con su autenticacion
--      · ni `revalidateTag`, ni saber si el cache handler de Vercel honra la
--        expiracion -- deja de importar
--      · ni un aviso que se pueda perder: no hay aviso
--    Y sobre todo: **no puede servir dato viejo**, porque el dato viejo esta bajo
--    otra clave. No es que se detecte; es que no puede pasar.
--
-- 🔴 LA HUELLA LLEVA DOS MITADES, Y LA SEGUNDA CASI SE ME OLVIDA.
--
--    1) LAS SIETE COPIAS. Cuando entra un informe y se refresca una copia, su
--       `refrescada_el` avanza y la huella cambia. Es la mitad obvia.
--       🔑 Va por `refrescada_el` y NO por el ancla, aunque las dos existan: el ancla
--          es la fecha del DATO, y un informe CORREGIDO con la misma fecha no la
--          mueve. El contenido si cambia. La clave tiene que cambiar cuando cambia
--          EL CONTENIDO, no cuando cambia la fecha.
--
--    2) 🔴 LAS TABLAS QUE LA PANTALLA LEE **EN VIVO**. Esta es la que importa para
--       Elena: `productos` --y ahi aterriza `stock_moloka` por trigger--,
--       `envios_fba`, `compras`, el escaner. NINGUN informe las mueve.
--       ⚠️ Sin esta mitad, Elena ajusta el stock de una ficha y **el Inventario le
--          sigue ensenando el numero viejo hasta el siguiente informe**. Es el mismo
--          fallo mudo por otra puerta, y ademas el que mas duele porque pasa a diario.
--
-- 🔑 CADA TABLA VIVA APORTA **SELLO Y RECUENTO**, y las dos cosas hacen falta:
--      · el sello (`max(updated_at)` o el equivalente) caza altas y ediciones,
--        SIEMPRE QUE la columna se mantenga;
--      · el recuento caza los BORRADOS, que ningun sello caza.
--    ⚠️ Y donde el sello NO se mantiene, el recuento es lo unico que queda. Medido
--       el 25-ago-2026: `productos` y `facturas` tienen trigger que actualiza
--       `updated_at`; `envios_fba`, `canales_producto` y `parametro_coste` NO -- ahi
--       depende de que la app lo escriba. `compras` y `proveedores` solo tienen fecha
--       de ALTA. O sea que **una edicion sobre esas tablas puede no mover la huella**.
--       Se anota porque es el LIMITE REAL de esto, no un detalle: la cache podria
--       servir una edicion vieja de `compras` hasta que caduque sola.
--       🔒 El caso que de verdad importa --el ajuste de stock de Elena-- SI se caza:
--          escribe `ubicaciones_cant`, el trigger actualiza `productos.stock_moloka`,
--          y `productos` SI mantiene su `updated_at`.
--
-- 🔬 COSTE MEDIDO, y la trampa que costaba 470 ms. Primera version: `max()` y
--    `count()` como DOS subconsultas por tabla -> el planificador recorre cada tabla
--    DOS VECES (`escaner_memoria`, 46.653 filas, salia en el InitPlan 22 y en el 23).
--    **501 ms y 1.580 buffers.** Con UN agregado por objeto: **31 ms y 823 buffers.**
--    Es la misma regla que el centinela: una pasada por objeto, no una por dato.
--
-- 🔒 DEVUELVE UNA CADENA CORTA (md5) Y NO LA LISTA ENTERA: la huella va dentro de la
--    clave de una cache, y una clave larga es una clave fragil.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    faltan text;
BEGIN
    SELECT string_agg(v, ', ') INTO faltan FROM (
        SELECT unnest(ARRAY['mv_ventas_ventanas','mv_rentabilidad_sku','mv_presencia_pais',
                            'mv_asin_con_pedido','mv_keepa_asin_visto',
                            'mv_velocidad_ventas_paneu','mv_demanda_asin_ultima',
                            'productos','envios_fba','canales_producto','parametro_coste',
                            'compras','facturas','proveedores','escaner_memoria']) AS v) x
     WHERE to_regclass('public.' || v) IS NULL;
    IF faltan IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: faltan objetos (%). La huella los lee TODOS; sin alguno se calcularia sobre menos cosas de las que la pantalla lee, y la cache podria servir un dato viejo de justo esa.', faltan;
    END IF;
END
$guardas$;

CREATE OR REPLACE FUNCTION public.huella_de_la_pantalla()
RETURNS text
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $fn$
    -- UN AGREGADO POR OBJETO. Ver el 501 -> 31 ms de la cabecera.
    SELECT md5(string_agg(x.que || '=' || coalesce(x.sello, '-') || '/' || x.n, '|' ORDER BY x.que))
      FROM (
        -- (1) LAS SIETE COPIAS, por su marca de refresco.
        SELECT 'c.ventanas' AS que, max(refrescada_el)::text AS sello, '' AS n FROM public.mv_ventas_ventanas
        UNION ALL SELECT 'c.rentab',    max(refrescada_el)::text, '' FROM public.mv_rentabilidad_sku
        UNION ALL SELECT 'c.presencia', max(refrescada_el)::text, '' FROM public.mv_presencia_pais
        UNION ALL SELECT 'c.pedido',    max(refrescada_el)::text, '' FROM public.mv_asin_con_pedido
        UNION ALL SELECT 'c.keepa',     max(refrescada_el)::text, '' FROM public.mv_keepa_asin_visto
        UNION ALL SELECT 'c.velocidad', max(refrescada_el)::text, '' FROM public.mv_velocidad_ventas_paneu
        UNION ALL SELECT 'c.demanda',   max(refrescada_el)::text, '' FROM public.mv_demanda_asin_ultima

        -- (2) 🔴 LAS OCHO TABLAS QUE LA PANTALLA LEE EN VIVO. Sello Y recuento: el
        --     sello caza altas y ediciones, el recuento caza los BORRADOS.
        UNION ALL SELECT 'v.productos',   max(updated_at)::text, count(*)::text FROM public.productos
        UNION ALL SELECT 'v.envios',      max(updated_at)::text, count(*)::text FROM public.envios_fba
        UNION ALL SELECT 'v.canales',     max(updated_at)::text, count(*)::text FROM public.canales_producto
        UNION ALL SELECT 'v.parametro',   max(changed_at)::text, count(*)::text FROM public.parametro_coste
        UNION ALL SELECT 'v.compras',     max(created_at)::text, count(*)::text FROM public.compras
        UNION ALL SELECT 'v.facturas',    max(updated_at)::text, count(*)::text FROM public.facturas
        UNION ALL SELECT 'v.proveedores', max(creado_en)::text,  count(*)::text FROM public.proveedores
        -- ⚠️ `escaner_memoria` son 46.653 filas y cuesta 613 de los 823 buffers de
        --    toda la huella. Se paga a proposito: el escaner reescribe filas y sin el
        --    recuento un borrado pasaria inadvertido. Si algun dia molesta, la salida
        --    NO es quitarlo, sino una columna de sello mantenida por trigger.
        UNION ALL SELECT 'v.escaner',     max(fecha)::text,      count(*)::text FROM public.escaner_memoria
      ) x
$fn$;

-- 🔴 NACE CERRADA Y SE LE DA LO MINIMO. Se revoca por rol y por su nombre ANTES de
--    conceder: no se supone lo que trae el default, se pone.
REVOKE ALL ON FUNCTION public.huella_de_la_pantalla() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.huella_de_la_pantalla() TO authenticated;

COMMENT ON FUNCTION public.huella_de_la_pantalla() IS
    'Una cadena corta que cambia EXACTAMENTE cuando cambia algo de lo que lee la pantalla de Inventario: las siete copias (por su refrescada_el) y las ocho tablas que se leen en vivo (por sello y recuento). Va dentro de la CLAVE de la cache de la pantalla, no en una invalidacion: asi el dato viejo queda bajo otra clave y no se encuentra. No es que se detecte -- es que no puede servirse. LIMITE CONOCIDO: envios_fba, canales_producto, parametro_coste, compras y proveedores no mantienen su sello con trigger, asi que una EDICION sobre ellas puede no mover la huella; ahi el recuento solo caza altas y bajas.';

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    h1 text; h2 text; n_partes int;
BEGIN
    SELECT public.huella_de_la_pantalla() INTO h1;
    IF h1 IS NULL OR length(h1) <> 32 THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y tenia que ser un md5 de 32 caracteres. Una huella nula haria que TODA la cache compartiera clave.', h1;
    END IF;

    -- 🔒 ESTABLE ENTRE LLAMADAS. Si cambiara sola --por un `now()` colado, por
    --    ejemplo-- la cache no acertaria NUNCA y esto seria un adorno caro.
    SELECT public.huella_de_la_pantalla() INTO h2;
    IF h1 <> h2 THEN
        RAISE EXCEPTION 'ABORTA: dos llamadas seguidas dan huellas distintas (% y %). La cache no acertaria nunca.', h1, h2;
    END IF;

    -- 🔴 Y QUE MIRE LAS QUINCE COSAS. Sin esto, una huella calculada sobre menos
    --    objetos de los que la pantalla lee saldria verde igual -- el md5 sale bien
    --    mida lo que mida, que es la comprobacion que no puede fallar en su forma
    --    clasica. Esto NO comprueba que la lista cubra la pantalla (eso la base no lo
    --    sabe): comprueba que nadie quite una parte sin darse cuenta.
    SELECT count(*) INTO n_partes FROM (
        SELECT regexp_matches(pg_get_functiondef('public.huella_de_la_pantalla()'::regprocedure),
                              '''(c|v)\.[a-z]+''', 'g')) y;
    IF n_partes <> 15 THEN
        RAISE EXCEPTION 'ABORTA: la huella declara % partes y tienen que ser 15 (7 copias + 8 tablas vivas). Si se anade o quita una fuente a la pantalla, este numero se actualiza A PROPOSITO.', n_partes;
    END IF;

    RAISE NOTICE 'Testigo OK. huella=% (estable entre dos llamadas), 15 partes: 7 copias + 8 tablas vivas.', h1;
END
$testigo$;

-- -- TESTIGO: QUE LA HUELLA SE MUEVA CUANDO SE MUEVE EL DATO --------------------
-- 🔴 LA MITAD QUE DE VERDAD PRUEBA ALGO. Que devuelva un md5 estable no dice nada:
--    una funcion que devolviera `md5('hola')` pasaria los tres asserts de arriba, y
--    con ella la cache no se invalidaria JAMAS. Aqui se ROMPE a proposito --se toca
--    una fila de `productos`, que es por donde entra el ajuste de stock de Elena-- y
--    la huella TIENE que cambiar.
--
-- 🔒 EL TOQUE SE DESHACE CON UN ROLLBACK DE SUBTRANSACCION, no con un UPDATE
--    inverso, y la diferencia importa: `productos` tiene un TRIGGER sobre
--    `updated_at`, asi que un UPDATE de vuelta lo volveria a disparar y dejaria la
--    columna en `now()` en vez de en su valor de antes. Esto es dato de Elena; una
--    prueba no lo toca. Las variables de plpgsql NO se deshacen con el rollback, asi
--    que el veredicto sobrevive.
--
-- ⚠️ Y SE TOCA LA FILA QUE TIENE EL `max(updated_at)`, no una cualquiera: la huella
--    lleva el maximo de la tabla, asi que mover una fila vieja no lo movería y esto
--    daria un ABORTA **falso**. Con el maximo funciona tanto si el trigger pisa el
--    valor (lo pone en `now()`, que es mayor) como si no (max + 1 s).
DO $mueve$
DECLARE
    antes text; despues text; se_movio boolean := false; hay_filas boolean;
BEGIN
    SELECT public.huella_de_la_pantalla() INTO antes;

    SELECT EXISTS (SELECT 1 FROM public.productos) INTO hay_filas;
    IF NOT hay_filas THEN
        RAISE WARNING 'NO COMPROBADO: `productos` esta vacia, asi que no hay nada que mover y un OK aqui no diria nada.';
        RETURN;
    END IF;

    BEGIN
        UPDATE public.productos SET updated_at = updated_at + interval '1 second'
         WHERE id = (SELECT id FROM public.productos ORDER BY updated_at DESC NULLS LAST LIMIT 1);
        SELECT public.huella_de_la_pantalla() INTO despues;
        se_movio := (antes IS DISTINCT FROM despues);
        -- Se sale por excepcion A PROPOSITO: es lo que deshace el UPDATE de prueba.
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'deshacer-la-prueba';
    EXCEPTION
        WHEN raise_exception THEN
            NULL;  -- el UPDATE queda deshecho; `se_movio` y `despues` sobreviven
    END;

    IF NOT se_movio THEN
        RAISE EXCEPTION 'ABORTA: se ha movido productos.updated_at y la huella NO ha cambiado (sigue en %). Con esta huella, la cache le serviria a Elena su stock viejo despues de cada ajuste.', antes;
    END IF;

    RAISE NOTICE 'Testigo OK (se mueve). productos tocado -> huella % -> % (y el toque, deshecho).', antes, despues;
END
$mueve$;

-- -- TESTIGOS DE LA PUERTA -----------------------------------------------------
DO $puerta_anon$
DECLARE h text;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT public.huella_de_la_pantalla()' INTO h;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha EJECUTADO huella_de_la_pantalla (%). Es SECURITY INVOKER y no filtra filas, pero si dice cuando se cargo cada informe y cuantas filas hay en cada tabla.', h;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al ejecutar huella_de_la_pantalla.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    h text; sin_permiso text;
BEGIN
    -- ⚠️ Staging NO lo reproduce: su volcado va con `--no-privileges`, asi que
    --    `authenticated` puede no tener SELECT sobre las fuentes y la funcion
    --    rebotaria por ELLAS, no por el EXECUTE. Se GRITA en vez de abortar, y el ACL
    --    se verifica EN PRODUCCION al aplicar.
    SELECT string_agg(t, ', ') INTO sin_permiso FROM (
        SELECT unnest(ARRAY['productos','envios_fba','compras','facturas','escaner_memoria']) AS t) x
     WHERE NOT has_table_privilege('authenticated', 'public.' || t, 'SELECT');
    IF sin_permiso IS NOT NULL THEN
        RAISE WARNING 'PUERTA NO COMPROBADA EN ESTE ENTORNO: `authenticated` no tiene SELECT sobre %. Esto NO dice nada sobre produccion: pasa porque el volcado va con --no-privileges.', sin_permiso;
        RETURN;
    END IF;

    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT public.huella_de_la_pantalla()' INTO h;
    RESET ROLE;
    IF h IS NULL OR length(h) <> 32 THEN
        RAISE EXCEPTION 'ABORTA: authenticated obtiene una huella invalida (%).', h;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated obtiene la huella (%).', h;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated ha rebotado con: %. Sin la huella la pantalla no puede cachear -- y si se le diera un valor por defecto, TODA la cache compartiria clave.', SQLERRM;
END
$puerta_auth$;
