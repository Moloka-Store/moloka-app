-- ============================================================================
-- MIGRACION · la huella vigilaba 15 cosas y la pantalla lee 22
-- ----------------------------------------------------------------------------
-- 🔴 EL AGUJERO, MEDIDO EL 26-ago-2026. `huella_de_la_pantalla()` nacio ayer con dos
--    mitades: las siete COPIAS (por su `refrescada_el`) y las ocho tablas que la
--    pantalla lee EN VIVO. Faltaba una tercera, y es la que mas duele: **las tablas-FOTO
--    que escriben los informes**.
--
--    Se creyo que estaban cubiertas "por el camino indirecto": el procesador escribe la
--    foto y despues refresca una copia, la copia mueve su `refrescada_el`, y la huella
--    cambia. Eso es cierto para CINCO procesadores. **No lo es para los otros cuatro.**
--
--    🔬 Medido leyendo los nueve procesadores uno a uno:
--       CON gancho : all_listings · custom_analytics · keepa · ledger · transacciones
--       SIN gancho : canal_amazon_es · internacional · inventario_fba · paneu_aptos
--
--    De los cuatro sin gancho, `canal_amazon_es` da igual --escribe `canales_producto`,
--    que YA estaba en la huella--. Los otros tres, no.
--
-- 🔴 EL FALLO CONCRETO, y por que esto es de la operativa de Elena y no de estilo:
--
--       entra el informe de INVENTARIO_FBA
--         -> se reescribe `inventario_fba` (el stock en Amazon, los dias de cobertura,
--            las alertas -- o sea la pantalla entera)
--         -> ese procesador NO refresca ninguna copia
--         -> ninguna de las 15 partes de la huella se mueve
--         -> la clave de la cache es la MISMA
--         -> Elena abre Inventario y ve **el stock de FBA de ayer**, hasta que caduque
--            la entrada. Un dia entero.
--
--    Y sin un solo sintoma: numeros plausibles, del dia anterior. Es exactamente el
--    fallo mudo contra el que se diseno el mecanismo, entrando por la puerta de atras.
--
-- 🔑 LA LECCION, QUE ES LO QUE HAY QUE QUEDARSE: **la huella vigila lo que la pantalla
--    LEE, no lo que los procesadores REFRESCAN.** Apoyarse en el gancho era hacer que la
--    correccion de la cache dependiera de un mapa que vive en OTRO repo
--    (`REFRESCOS_POR_FUENTE` en `foto_comun.py`) y que nadie obliga a mantener. Quitar
--    una linea de ese mapa no da ningun error aqui: empieza a servir dato viejo.
--    Por eso ahora entran TAMBIEN las fotos que si estaban cubiertas por el camino
--    indirecto (`keepa_escaparate`, `listings_amazon`, `ledger_movimientos`): no para
--    taparlas dos veces, sino para que **la cobertura deje de depender del gancho**.
--
-- 🔬 QUE SE ANADE, y de donde sale que la pantalla lo lee. Censo de los `.from(...)` de
--    `lib/inventory/query.ts`, con las vistas resueltas a sus tablas base por `pg_depend`
--    (por NIVELES, nunca con WITH RECURSIVE -- eso ya lleno el disco temporal de
--    produccion dos veces):
--
--    | se anade                   | la pantalla lo lee por            | tenia gancho |
--    |----------------------------|-----------------------------------|--------------|
--    | inventario_fba             | directo Y via `salud_fba`         | 🔴 NO        |
--    | inventario_internacional   | directo                           | 🔴 NO        |
--    | paneu_aptos                | directo                           | 🔴 NO        |
--    | salud_fba_historico        | directo Y via `v_nunca_enviado_fba` | 🔴 NO      |
--    | keepa_escaparate           | directo, `salud_fba`, `v_keepa_bb_envio` | si (indirecto) |
--    | listings_amazon            | directo                           | si (indirecto) |
--    | ledger_movimientos         | via `v_nunca_enviado_fba`         | si (indirecto) |
--
--    ⚠️ `salud_fba` NO se anade porque es una VISTA sobre `inventario_fba`,
--       `keepa_escaparate` y `v_ventas_ventanas`: las tres ya quedan vigiladas por
--       separado. Vigilar la vista seria pagar su coste dos veces.
--    ⚠️ El TRACKEADOR (`mv_trackeador_pantalla`, `v_trackeador_frescura`) tampoco:
--       `cargarTrackeador()` va por SU PROPIA puerta en `page.tsx` y **no pasa por esta
--       cache**. El dia que se cachee, entra aqui.
--
-- 🔬 COSTE: **17,2 ms y 1.644 buffers** en caliente, con las 22 partes (medido en
--    produccion el 26-ago). Con las 15 eran 31 ms y 823. O sea que taparlo entero
--    cuesta el doble de buffers y NO cuesta tiempo. Barato para lo que compra.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    faltan text;
BEGIN
    IF to_regprocedure('public.huella_de_la_pantalla()') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: no existe huella_de_la_pantalla(). Esta migracion la AMPLIA; primero va 2026-08-25_huella_de_la_pantalla.sql.';
    END IF;

    SELECT string_agg(v, ', ') INTO faltan FROM (
        SELECT unnest(ARRAY['mv_ventas_ventanas','mv_rentabilidad_sku','mv_presencia_pais',
                            'mv_asin_con_pedido','mv_keepa_asin_visto',
                            'mv_velocidad_ventas_paneu','mv_demanda_asin_ultima',
                            'productos','envios_fba','canales_producto','parametro_coste',
                            'compras','facturas','proveedores','escaner_memoria',
                            'inventario_fba','inventario_internacional','paneu_aptos',
                            'salud_fba_historico','keepa_escaparate','listings_amazon',
                            'ledger_movimientos']) AS v) x
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
    -- UN AGREGADO POR OBJETO. Escrito con `max()` y `count()` como dos subconsultas, el
    -- planificador recorre cada tabla DOS VECES: 501 ms contra 31 (medido el 25-ago).
    SELECT md5(string_agg(x.que || '=' || coalesce(x.sello, '-') || '/' || x.n, '|' ORDER BY x.que))
      FROM (
        -- (1) LAS SIETE COPIAS, por su marca de refresco. El ancla es la fecha del DATO,
        --     y un informe CORREGIDO con la misma fecha no la mueve; `refrescada_el` si.
        SELECT 'c.ventanas' AS que, max(refrescada_el)::text AS sello, '' AS n FROM public.mv_ventas_ventanas
        UNION ALL SELECT 'c.rentab',    max(refrescada_el)::text, '' FROM public.mv_rentabilidad_sku
        UNION ALL SELECT 'c.presencia', max(refrescada_el)::text, '' FROM public.mv_presencia_pais
        UNION ALL SELECT 'c.pedido',    max(refrescada_el)::text, '' FROM public.mv_asin_con_pedido
        UNION ALL SELECT 'c.keepa',     max(refrescada_el)::text, '' FROM public.mv_keepa_asin_visto
        UNION ALL SELECT 'c.velocidad', max(refrescada_el)::text, '' FROM public.mv_velocidad_ventas_paneu
        UNION ALL SELECT 'c.demanda',   max(refrescada_el)::text, '' FROM public.mv_demanda_asin_ultima

        -- (2) LAS OCHO TABLAS QUE LA PANTALLA LEE EN VIVO. Sello Y recuento: el sello
        --     caza altas y ediciones, el recuento caza los BORRADOS.
        UNION ALL SELECT 'v.productos',   max(updated_at)::text, count(*)::text FROM public.productos
        UNION ALL SELECT 'v.envios',      max(updated_at)::text, count(*)::text FROM public.envios_fba
        UNION ALL SELECT 'v.canales',     max(updated_at)::text, count(*)::text FROM public.canales_producto
        UNION ALL SELECT 'v.parametro',   max(changed_at)::text, count(*)::text FROM public.parametro_coste
        UNION ALL SELECT 'v.compras',     max(created_at)::text, count(*)::text FROM public.compras
        UNION ALL SELECT 'v.facturas',    max(updated_at)::text, count(*)::text FROM public.facturas
        UNION ALL SELECT 'v.proveedores', max(creado_en)::text,  count(*)::text FROM public.proveedores
        UNION ALL SELECT 'v.escaner',     max(fecha)::text,      count(*)::text FROM public.escaner_memoria

        -- (3) 🔴 LAS SIETE FOTOS QUE ESCRIBEN LOS INFORMES. La mitad que faltaba.
        --     `procesado_at` / `procesado_en` es el `now()` que estampa el procesador al
        --     cargar, asi que se mueve en CADA carga -- tambien cuando el fichero trae los
        --     mismos datos, que es justo cuando el ancla por fecha no se movería.
        UNION ALL SELECT 'f.invfba',    max(procesado_at)::text, count(*)::text FROM public.inventario_fba
        UNION ALL SELECT 'f.intl',      max(procesado_at)::text, count(*)::text FROM public.inventario_internacional
        UNION ALL SELECT 'f.paneu',     max(procesado_en)::text, count(*)::text FROM public.paneu_aptos
        UNION ALL SELECT 'f.saludhist', max(procesado_en)::text, count(*)::text FROM public.salud_fba_historico
        UNION ALL SELECT 'f.keepa',     max(procesado_at)::text, count(*)::text FROM public.keepa_escaparate
        UNION ALL SELECT 'f.listings',  max(procesado_en)::text, count(*)::text FROM public.listings_amazon
        -- ⚠️ El ledger es PELICULA, no foto: no tiene `procesado_*`, y no lo necesita --
        --    solo se apila, asi que `max(fecha)` mas el recuento lo describen entero. Y va
        --    por `idx_ledger_fecha` en Index Only Scan: 48 buffers sobre 20.317 filas.
        UNION ALL SELECT 'f.ledger',    max(fecha)::text,        count(*)::text FROM public.ledger_movimientos
      ) x
$fn$;

-- 🔒 `CREATE OR REPLACE` CONSERVA EL ACL, pero eso no se supone: se mide en el testigo.
--    Y si algun dia esta migracion pasara a llevar un DROP, el revoke tendria que ir
--    DETRAS del create -- un DROP+CREATE pierde el ACL y el objeto renace con `anon`
--    dentro por los default privileges.

COMMENT ON FUNCTION public.huella_de_la_pantalla() IS
    'Una cadena corta que cambia EXACTAMENTE cuando cambia algo de lo que lee la pantalla de Inventario. TRES mitades: las 7 copias (por refrescada_el), las 8 tablas que se leen en vivo, y las 7 fotos que escriben los informes (por procesado_at/procesado_en y recuento). Va dentro de la CLAVE de la cache, no en una invalidacion: asi el dato viejo queda bajo otra clave y no se encuentra. Las fotos entran DIRECTAMENTE y no por el gancho de refresco de los procesadores, porque cuatro de los nueve procesadores no lo llaman y porque la correccion de la cache no puede depender de un mapa que vive en otro repo. LIMITE CONOCIDO: envios_fba, canales_producto, parametro_coste, compras y proveedores no mantienen su sello con trigger, asi que una EDICION sobre ellas puede no mover la huella; ahi el recuento solo caza altas y bajas.';

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    h1 text; h2 text; n_partes int; acl_anon boolean; acl_auth boolean;
BEGIN
    SELECT public.huella_de_la_pantalla() INTO h1;
    IF h1 IS NULL OR length(h1) <> 32 THEN
        RAISE EXCEPTION 'ABORTA: la huella es % y tenia que ser un md5 de 32 caracteres. Una huella nula haria que TODA la cache compartiera clave.', h1;
    END IF;

    SELECT public.huella_de_la_pantalla() INTO h2;
    IF h1 <> h2 THEN
        RAISE EXCEPTION 'ABORTA: dos llamadas seguidas dan huellas distintas (% y %). La cache no acertaria nunca.', h1, h2;
    END IF;

    -- 🔴 VEINTIDOS, NO QUINCE. Es el numero que cambia esta migracion, asi que es el que
    --    prueba que ha hecho algo: sobre la version VIEJA este assert da 15 y ABORTA.
    --    (Anclado sobre lo que cambia, no sobre un nombre que las dos versiones tienen.)
    SELECT count(*) INTO n_partes FROM (
        SELECT regexp_matches(pg_get_functiondef('public.huella_de_la_pantalla()'::regprocedure),
                              '''(c|v|f)\.[a-z]+''', 'g')) y;
    IF n_partes <> 22 THEN
        RAISE EXCEPTION 'ABORTA: la huella declara % partes y tienen que ser 22 (7 copias + 8 tablas vivas + 7 fotos). Si se anade o quita una fuente a la pantalla, este numero se actualiza A PROPOSITO.', n_partes;
    END IF;

    -- 🔒 EL ACL, MEDIDO Y NO SUPUESTO. `CREATE OR REPLACE` deberia conservarlo; que
    --    "deberia" no es una comprobacion.
    SELECT has_function_privilege('anon','public.huella_de_la_pantalla()','EXECUTE'),
           has_function_privilege('authenticated','public.huella_de_la_pantalla()','EXECUTE')
      INTO acl_anon, acl_auth;
    IF acl_anon THEN
        RAISE EXCEPTION 'ABORTA: anon puede ejecutar huella_de_la_pantalla. El REPLACE se ha llevado el revoke por delante.';
    END IF;
    IF NOT acl_auth THEN
        RAISE EXCEPTION 'ABORTA: authenticated ya NO puede ejecutar huella_de_la_pantalla. Sin ella la pantalla deja de cachear (y lo grita, pero va lenta).';
    END IF;

    RAISE NOTICE 'Testigo OK. huella=% · 22 partes · anon fuera, authenticated dentro.', h1;
END
$testigo$;

-- -- TESTIGO: QUE SE MUEVA CON LA FOTO QUE ANTES NO LA MOVIA ------------------
-- 🔴 ESTE ES EL TESTIGO DE ESTA MIGRACION, y esta escrito sobre `inventario_fba` a
--    proposito: es la tabla del agujero, la que trae el stock de FBA de Elena, y la que
--    con la huella vieja NO movia nada. Sobre la version de ayer, este bloque ABORTA.
-- 🔒 El toque se deshace con el manejador de excepciones del PROPIO bloque: al atrapar,
--    Postgres revierte lo que el bloque haya escrito, y las variables de plpgsql
--    sobreviven. Sin sub-bloque anidado, porque un `END;` a principio de linea le casa al
--    cerrojo 4 del workflow y aborta la migracion por una causa que no tiene nada que ver.
DO $mueve$
DECLARE
    antes text; despues text; se_movio boolean := false;
BEGIN
    SELECT public.huella_de_la_pantalla() INTO antes;

    IF NOT EXISTS (SELECT 1 FROM public.inventario_fba) THEN
        RAISE WARNING 'NO COMPROBADO: `inventario_fba` esta vacia, asi que no hay nada que mover y un OK aqui no diria nada.';
        RETURN;
    END IF;

    -- ⚠️ Se toca la fila que tiene el MAXIMO, no una cualquiera: la huella lleva el
    --    `max()` de la tabla, y mover una fila vieja no lo moveria -> ABORTA falso.
    UPDATE public.inventario_fba SET procesado_at = procesado_at + interval '1 second'
     WHERE ctid = (SELECT ctid FROM public.inventario_fba ORDER BY procesado_at DESC NULLS LAST LIMIT 1);
    SELECT public.huella_de_la_pantalla() INTO despues;
    se_movio := (antes IS DISTINCT FROM despues);

    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'deshacer-la-prueba';
EXCEPTION
    WHEN raise_exception THEN
        IF NOT se_movio THEN
            RAISE EXCEPTION 'ABORTA: se ha movido inventario_fba y la huella NO ha cambiado (sigue en %). Con esta huella, entra el informe de inventario y la cache le sigue enseñando a Elena el stock de FBA de ayer, sin ningun sintoma. Es el agujero que esta migracion viene a tapar.', antes;
        END IF;
        RAISE NOTICE 'Testigo OK (se mueve con la foto). inventario_fba tocado -> huella % -> % (y el toque, deshecho).', antes, despues;
END
$mueve$;

-- -- Y QUE SIGA MOVIENDOSE CON LO DE ANTES -----------------------------------
-- 🔒 La otra direccion de la misma prueba: ampliar la huella no puede haber roto lo que
--    ya vigilaba. Si `productos` deja de moverla, el ajuste de stock diario de Elena
--    vuelve a quedarse detras de la cache.
DO $sigue$
DECLARE
    antes text; despues text; se_movio boolean := false;
BEGIN
    SELECT public.huella_de_la_pantalla() INTO antes;
    IF NOT EXISTS (SELECT 1 FROM public.productos) THEN
        RAISE WARNING 'NO COMPROBADO: `productos` esta vacia.';
        RETURN;
    END IF;
    UPDATE public.productos SET updated_at = updated_at + interval '1 second'
     WHERE id = (SELECT id FROM public.productos ORDER BY updated_at DESC NULLS LAST LIMIT 1);
    SELECT public.huella_de_la_pantalla() INTO despues;
    se_movio := (antes IS DISTINCT FROM despues);
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'deshacer-la-prueba';
EXCEPTION
    WHEN raise_exception THEN
        IF NOT se_movio THEN
            RAISE EXCEPTION 'ABORTA: al ampliar la huella se ha roto lo que ya vigilaba: mover productos.updated_at ya no la cambia (sigue en %).', antes;
        END IF;
        RAISE NOTICE 'Testigo OK (sigue moviendose). productos tocado -> huella % -> %.', antes, despues;
END
$sigue$;

-- -- TESTIGOS DE LA PUERTA -----------------------------------------------------
DO $puerta_anon$
DECLARE h text;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT public.huella_de_la_pantalla()' INTO h;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha EJECUTADO huella_de_la_pantalla (%). No filtra filas, pero si dice cuando se cargo cada informe y cuantas filas hay en cada tabla.', h;
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
    --    `authenticated` puede no tener SELECT sobre las fuentes y la funcion rebotaria
    --    por ELLAS, no por el EXECUTE. Se GRITA en vez de abortar; el ACL de verdad se
    --    verifica EN PRODUCCION al aplicar.
    SELECT string_agg(t, ', ') INTO sin_permiso FROM (
        SELECT unnest(ARRAY['productos','inventario_fba','paneu_aptos','keepa_escaparate',
                            'listings_amazon','ledger_movimientos','salud_fba_historico',
                            'inventario_internacional']) AS t) x
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
        RAISE EXCEPTION 'ABORTA: authenticated ha rebotado con: %. Sin la huella la pantalla no puede cachear.', SQLERRM;
END
$puerta_auth$;
