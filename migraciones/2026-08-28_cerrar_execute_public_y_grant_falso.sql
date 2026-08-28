-- ============================================================================
-- MIGRACION - Se cierra el EXECUTE a PUBLIC de tres SECURITY DEFINER, y se
--             retira un GRANT que promete un acceso que no funciona
-- ----------------------------------------------------------------------------
-- 🔴 ESTA SI CAMBIA PERMISOS EN PRODUCCION. No es una foto: es una decision,
--    tomada por Fernando el 28-ago-2026 con la medicion delante.
--
-- QUE HACE, y son dos cosas distintas con el mismo motivo -- que lo escrito y lo
-- que pasa coincidan:
--
--   A) `fn_fee_override_refresh()`, `fn_trackeador_refrescar(boolean)` y
--      `fn_trackeador_snapshot(date, interval)` son SECURITY DEFINER, propiedad
--      de `postgres`, y tienen EXECUTE para **PUBLIC**. Corren con permisos de su
--      dueno, que se salta la RLS, y la clave `anon` viaja en el JavaScript de la
--      v1 por diseno. Se les quita PUBLIC.
--
--   B) `v_doctrina_arranque` y `v_arranque_coste` tienen `authenticated=r`, pero
--      son `security_invoker` y leen `doctrina_madres`, donde `authenticated` NO
--      tiene SELECT. O sea que el GRANT promete un acceso que da **42501**, no
--      cero filas. Se retira el GRANT.
--
-- 🔒 LO QUE NO SE HACE, Y ES LA MITAD IMPORTANTE DE LA DECISION: **NO se abre
--    `doctrina_madres` a `authenticated`.** Se cierra la promesa falsa, no se
--    ensancha el acceso. El dia que algo lea esas vistas de verdad, se pone el
--    GRANT entonces -- y para entonces habra que decidir tambien el de la tabla.
--    Abrir por si acaso es como se llega a tener `anon` en todo.
--
-- ----------------------------------------------------------------------------
-- LA MEDICION QUE LO JUSTIFICA, porque un REVOKE a ciegas apaga cosas
-- ----------------------------------------------------------------------------
-- ⚠️ La pregunta que habia que contestar ANTES: *¿con que rol se llaman esas
--    funciones?* Si alguna se llamara con `anon`, este REVOKE apagaria la carga
--    de informes, y eso le toca a Elena.
--
-- CENSO POR CODIGO (los dos repos, 28-ago-2026):
--   · `fn_trackeador_refrescar`  -> solo `foto_comun.py:871`, que conecta con
--     `psycopg2.connect(DB_URL)` y `DB_URL` es `secrets.SUPABASE_DB_URL`: una
--     cadena de conexion Postgres, NO una clave de API. Entra como `postgres`.
--   · `fn_fee_override_refresh`  -> nadie. La invoca `fn_trackeador_refrescar`
--     por dentro (`perform`).
--   · `fn_trackeador_snapshot`   -> nadie en ninguno de los dos repos.
--
-- CENSO POR USO (`pg_stat_statements` en produccion), que es el que no miente,
-- y ampliado a TODOS los roles, no solo a `anon`:
--   · `postgres`       -> 29 llamadas a las tres
--   · `authenticated`  -> 0, de 107 sentencias / 15.258 llamadas suyas
--   · `service_role`   -> 0, de 33
--   · `anon`           -> 0, de 42 sentencias / 14.678 llamadas suyas
--   · `authenticator`  -> 0, de 23
--
-- 🔒 Y LA COMPROBACION DE QUE ESE CENSO PUEDE DECIR "ANON", que es lo que lo
--    hace valido: `anon` tiene 14.678 llamadas registradas en esa ventana. El
--    censo SI lo ve; simplemente ninguna de sus 42 sentencias toca estas
--    funciones. Un censo que no viera a `anon` daria el mismo cero por no mirar.
--
-- ⚠️ LOS DOS LIMITES DE ESA MEDICION, dichos antes de que nadie los use:
--    1. La ventana es de **4 dias 6 h** (`stats_reset` = 24-ago-2026 07:26), no
--       de meses. Sobra para `fn_trackeador_refrescar` (23 llamadas ahi dentro,
--       o sea que corre a diario) y va JUSTA para `fn_trackeador_snapshot` (4).
--    2. Un `perform` dentro de una funcion NO registra sentencia propia. Por eso
--       `fn_fee_override_refresh` no aparece llamada: la invoca la otra.
--
-- ----------------------------------------------------------------------------
-- 🔴 SON CUATRO, NO TRES -- Y LA CUARTA SE QUEDA ABIERTA A PROPOSITO
-- ----------------------------------------------------------------------------
-- Censo de TODAS las `prosecdef` de `public` en produccion (28-ago-2026): **11
-- funciones**, de las cuales **4 alcanzables por `anon`**. Las tres de arriba...
-- y `salud_stock_moloka()`.
--
-- ⚠️ A ESA NO LA TOCA ESTE REVOKE, y no por descuido: su ACL es
--    `postgres=X | anon=X | authenticated=X | service_role=X`. **El `anon=X` es
--    EXPLICITO**, no viene de PUBLIC, asi que un `revoke ... from public` pasa de
--    largo. Si alguien creyera que este fichero cierra "las SECURITY DEFINER
--    abiertas a anon", se equivocaria: cierra las que lo estaban POR PUBLIC.
--
-- 🔒 Y NO SE CIERRA, porque medido es lo contrario de las otras tres:
--    · Es **STABLE** (no escribe). Devuelve dos numeros agregados:
--      `trigger_activo` y `fichas_desincronizadas`.
--    · Es el **centinela del stock derivado**: contesta *"¿sigue puesto el
--      trigger `trg_sync_stock_moloka`?"*. Si alguien lo tira, `stock_moloka`
--      deja de derivarse EN SILENCIO y media app lee un numero muerto.
--    · Es DEFINER **para eso**: para que el numero no pueda ser un cero enganoso
--      por RLS.
--    · Y `anon` SI la llama: **3 llamadas** en `pg_stat_statements` (las otras
--      tres: cero). Quien llama es `salud-derivada.yml` de **moloka-app-v2**, por
--      PostgREST contra `/rest/v1/rpc/salud_stock_moloka` con la clave
--      `publishable`, que entra como `anon`.
--    · El `grant execute ... to anon` es una **decision escrita de Fernando del
--      30-jul-2026**, con su razon en el propio workflow: la clave
--      `sb_publishable_` ya esta en el `index.html` de `moloka-app`, que es un
--      repo PUBLICO, asi que concederla a `anon` no anade exposicion nueva.
--
-- ⇒ Revocarle `anon` **apagaria el centinela**. Se queda, documentada aqui para
--   que la proxima vez que alguien haga este censo no la lea como un olvido.
--   *(Lo unico bueno del caso: el workflow no fallaria en silencio -- comprueba
--   el HTTP y dice "puede que falte el grant a anon". Pero dejaria de vigilar.)*
--
-- ----------------------------------------------------------------------------
-- 🔴 CONFLICTO CONOCIDO CON LA MIGRACION FOTO -- LEER ANTES DE REAPLICAR NADA
-- ----------------------------------------------------------------------------
-- `2026-08-28_repo_arranque_objetos_vivos.sql` lleva dentro
-- `grant select on public.v_doctrina_arranque to authenticated` (y lo mismo para
-- `v_arranque_coste`), porque era la foto de lo que habia. **Si esa migracion se
-- reaplica DESPUES de esta, el GRANT vuelve y este arreglo queda deshecho, en
-- silencio y sin error.**
-- Lo mismo con las tres funciones y su `grant execute ... to public`.
--
-- 📌 No se arregla aqui porque son dos cosas: esta migracion decide permisos, y
--    poner la foto al dia es otro PR. **Pero queda dicho, y es lo primero que
--    hay que hacer despues de aplicar esta.** Mientras tanto, el orden importa:
--    la foto NUNCA despues de esta.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    n_publico int;
    n_auth    int;
    falta     text;
BEGIN
    -- 1) Los cinco objetos tienen que existir con la firma exacta. Si alguno no
    --    esta, el REVOKE fallaria a medias y no es lo que se quiere.
    SELECT string_agg(x.n, ', ' ORDER BY x.n) INTO falta
      FROM (VALUES ('public.fn_fee_override_refresh()'),
                   ('public.fn_trackeador_refrescar(boolean)'),
                   ('public.fn_trackeador_snapshot(date, interval)')) x(n)
     WHERE to_regprocedure(x.n) IS NULL;
    IF falta IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: no existe(n) %. Comprueba la firma antes de revocar.', falta;
    END IF;
    IF to_regclass('public.v_doctrina_arranque') IS NULL
       OR to_regclass('public.v_arranque_coste') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: falta v_doctrina_arranque o v_arranque_coste.';
    END IF;

    -- 2) 🔴 LA GUARDA ANTI-VERDE-MUDO: si PUBLIC ya no tuviera EXECUTE, este
    --    REVOKE no cambiaria nada y el verde no probaria absolutamente nada.
    --    Se cuenta lo que hay ANTES, y tiene que haber algo que quitar.
    SELECT count(*) INTO n_publico
      FROM (VALUES ('public.fn_fee_override_refresh()'),
                   ('public.fn_trackeador_refrescar(boolean)'),
                   ('public.fn_trackeador_snapshot(date, interval)')) x(n)
     WHERE has_function_privilege('anon', to_regprocedure(x.n), 'EXECUTE');
    IF n_publico <> 3 THEN
        RAISE EXCEPTION 'ABORTA: se esperaba que anon pudiera ejecutar las TRES (via PUBLIC) y puede %. O ya se revoco, o la foto de partida no es la que esta migracion cree.', n_publico;
    END IF;

    SELECT count(*) INTO n_auth
      FROM (VALUES ('v_doctrina_arranque'), ('v_arranque_coste')) x(n)
     WHERE has_table_privilege('authenticated', 'public.' || x.n, 'SELECT');
    IF n_auth <> 2 THEN
        RAISE EXCEPTION 'ABORTA: se esperaba que authenticated tuviera SELECT en las DOS vistas y lo tiene en %. O ya se revoco, o el punto de partida es otro.', n_auth;
    END IF;

    RAISE NOTICE 'Guardas OK. Punto de partida el esperado: anon ejecuta las 3 funciones y authenticated lee las 2 vistas. Hay algo que quitar.';
END
$guardas$;

-- -- A) LAS TRES FUNCIONES: fuera PUBLIC --------------------------------------
-- No lleva ningun `grant` detras, y NO es un olvido: esta comprobado. El ACL
-- antes es `postgres=X | service_role=X | =X`; al quitar el `=X` (que es PUBLIC)
-- quedan las otras dos entradas, que son GRANT propios y no dependen de PUBLIC.
-- El dueno conserva su EXECUTE, y `service_role` el suyo. Nadie mas lo necesita:
-- quien las llama entra como `postgres` (ver el censo de la cabecera).
revoke all on function public.fn_fee_override_refresh()               from public;
revoke all on function public.fn_trackeador_refrescar(boolean)        from public;
revoke all on function public.fn_trackeador_snapshot(date, interval)  from public;

-- -- B) LAS DOS VISTAS: fuera la promesa falsa --------------------------------
-- Se retira SOLO el GRANT que no funciona. `doctrina_madres` NO se abre.
revoke select on public.v_doctrina_arranque from authenticated;
revoke select on public.v_arranque_coste    from authenticated;

-- -- TESTIGOS ----------------------------------------------------------------
DO $testigo$
DECLARE
    n         int;
    n_secdef  int;
    abiertas  text;
BEGIN
    -- A) Ninguno de los tres roles de la app puede ya ejecutar las funciones...
    SELECT count(*) INTO n
      FROM (VALUES ('public.fn_fee_override_refresh()'),
                   ('public.fn_trackeador_refrescar(boolean)'),
                   ('public.fn_trackeador_snapshot(date, interval)')) x(n),
           (VALUES ('anon'), ('authenticated')) y(rol)
     WHERE has_function_privilege(y.rol, to_regprocedure(x.n), 'EXECUTE');
    IF n <> 0 THEN
        RAISE EXCEPTION 'ABORTA: despues del revoke, anon o authenticated todavia pueden ejecutar % de las 6 combinaciones.', n;
    END IF;

    -- 🔴 EL CENSO DE VERDAD: TODAS las `prosecdef` de public, no solo las tres.
    --    Un testigo que solo mira lo que ya sabes no es un censo: saldria VERDE
    --    con una cuarta funcion abierta. Y de hecho la HAY -- y no se cierra:
    --    `salud_stock_moloka()` tiene `anon=X` EXPLICITO, no por PUBLIC, asi que
    --    ningun `revoke ... from public` la toca. Es la excepcion documentada de
    --    la cabecera.
    --
    --    Se ancla en el CONJUNTO esperado, no en un recuento: si aparece una
    --    quinta, o si desaparece la que debe quedar, aqui se ve con su nombre.
    SELECT string_agg(f.firma, ', ' ORDER BY f.firma) INTO abiertas
      FROM (SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS firma
              FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
             WHERE ns.nspname = 'public' AND p.prosecdef
               AND has_function_privilege('anon', p.oid, 'EXECUTE')) f;

    IF coalesce(abiertas, '(ninguna)') <> 'salud_stock_moloka()' THEN
        RAISE EXCEPTION 'ABORTA: las SECURITY DEFINER de public alcanzables por anon son [%] y se esperaba EXACTAMENTE [salud_stock_moloka()]. Si hay de mas, este revoke se ha quedado corto; si falta esa, alguien ha apagado el centinela del stock derivado.', coalesce(abiertas, 'ninguna');
    END IF;

    SELECT count(*) INTO n_secdef
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname = 'public' AND p.prosecdef;
    RAISE NOTICE 'Censo OK. % funciones SECURITY DEFINER en public; alcanzable por anon queda 1, y es salud_stock_moloka() a proposito.', n_secdef;

    -- ...y el dueno y service_role SI, que es lo que hace que no se rompa nada.
    -- Se ancla en las DOS mitades: quitar de mas es tan fallo como quitar de menos.
    SELECT count(*) INTO n
      FROM (VALUES ('public.fn_fee_override_refresh()'),
                   ('public.fn_trackeador_refrescar(boolean)'),
                   ('public.fn_trackeador_snapshot(date, interval)')) x(n),
           (VALUES ('postgres'), ('service_role')) y(rol)
     WHERE has_function_privilege(y.rol, to_regprocedure(x.n), 'EXECUTE');
    IF n <> 6 THEN
        RAISE EXCEPTION 'ABORTA: el revoke se ha llevado por delante a postgres o service_role (solo % de 6 conservan EXECUTE). La carga de informes se pararia.', n;
    END IF;

    -- B) authenticated ya no las lee; postgres y service_role si.
    SELECT count(*) INTO n
      FROM (VALUES ('v_doctrina_arranque'), ('v_arranque_coste')) x(n)
     WHERE has_table_privilege('authenticated', 'public.' || x.n, 'SELECT');
    IF n <> 0 THEN
        RAISE EXCEPTION 'ABORTA: authenticated todavia tiene SELECT en % de las 2 vistas.', n;
    END IF;
    SELECT count(*) INTO n
      FROM (VALUES ('v_doctrina_arranque'), ('v_arranque_coste')) x(n),
           (VALUES ('postgres'), ('service_role')) y(rol)
     WHERE has_table_privilege(y.rol, 'public.' || x.n, 'SELECT');
    IF n <> 4 THEN
        RAISE EXCEPTION 'ABORTA: postgres o service_role han perdido el SELECT sobre las vistas (solo % de 4).', n;
    END IF;

    RAISE NOTICE 'Testigo OK. anon y authenticated fuera de las 3 funciones; postgres y service_role dentro. authenticated fuera de las 2 vistas; postgres y service_role dentro.';
END
$testigo$;

-- La puerta de las VISTAS, EJERCIDA. El catalogo dice lo que esta escrito; esto
-- dice lo que pasa.
-- ⚠️ Las FUNCIONES no se ejercen aqui a proposito: llamarlas tiene efectos
--    --refrescan la materializada, escriben en `trackeador_refrescos`-- y si el
--    revoke hubiera fallado, el propio testigo las ejecutaria. Para ellas vale
--    `has_function_privilege`, y se dice que es catalogo y no puerta.
DO $puerta$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM (SELECT * FROM public.v_doctrina_arranque LIMIT 0) z' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: authenticated ha ENTRADO en v_doctrina_arranque despues del revoke.';
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). authenticated REBOTA en v_doctrina_arranque.';
END
$puerta$;

-- ============================================================================
-- DESHACER -- si hubiera que volver atras, esto es exactamente lo de antes
-- ----------------------------------------------------------------------------
-- Foto del ACL medida en PRODUCCION el 28-ago-2026, ANTES de esta migracion:
--
--   fn_fee_override_refresh()                      postgres=X | service_role=X | =X
--   fn_trackeador_refrescar(p_relanzar boolean)    postgres=X | service_role=X | =X
--   fn_trackeador_snapshot(p_fecha date,
--                          p_edad_max interval)    =X | postgres=X | service_role=X
--   v_doctrina_arranque   postgres=arwdDxtm | service_role=arwdDxtm | authenticated=r
--   v_arranque_coste      postgres=arwdDxtm | service_role=arwdDxtm | authenticated=r
--
-- El `=X` sin rol delante es PUBLIC. Para volver a ese estado exacto:
--
--   grant execute on function public.fn_fee_override_refresh()              to public;
--   grant execute on function public.fn_trackeador_refrescar(boolean)       to public;
--   grant execute on function public.fn_trackeador_snapshot(date, interval) to public;
--   grant select on public.v_doctrina_arranque to authenticated;
--   grant select on public.v_arranque_coste    to authenticated;
--
-- ⚠️ Volver atras devuelve EXACTAMENTE el problema que esto cierra. Si hay que
--    hacerlo, que sea porque algo se rompio -- y entonces lo que hay que mirar
--    es QUE se rompio, porque segun el censo nadie deberia notar este cambio.
-- ============================================================================
