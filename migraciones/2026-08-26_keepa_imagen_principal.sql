-- ============================================================================
-- MIGRACION · media hora de imagenes para usar una
-- ----------------------------------------------------------------------------
-- 🔴 EL DATO QUE LO MOTIVA, medido el 26-ago-2026 en produccion:
--      `keepa_escaparate.imagenes` es un `text[]` con **6,4 URLs de media por fila**,
--      1.653 filas, y pesa **540 kB** de los 2.100 kB que la pantalla de Inventario baja
--      de esa tabla.
--      Y de esas 6,4 URLs **se usa UNA**: `lib/foto.ts:105` hace `f.imagenes[0]` y tira
--      el resto. Medio mega por carga para leer un elemento por fila.
--
-- 🔑 POR QUE UNA COLUMNA Y NO UN CAMBIO EN LA APP. PostgREST no sabe rebanar un `text[]`
--    en el `select=`: o se trae el array entero o no se trae. Con `jsonb` se podria
--    (`imagenes->0`), pero la columna es `text[]` y cambiarle el tipo a una tabla que
--    escriben los procesadores es mucho mas caro que anadir una columna al lado.
--
-- 🔒 GENERADA Y ALMACENADA, no una vista ni un trigger:
--      · no puede desincronizarse -- la calcula Postgres, no un procesador que puede
--        olvidarse;
--      · el procesador de Keepa **no se toca**: sigue escribiendo `imagenes` igual;
--      · y `imagenes` SE QUEDA. El array completo es el dato de Keepa y vive en la
--        Despensa Comun (§2): que hoy solo se use el primero no autoriza a tirarlo.
--        Lo que se arregla no es lo que se GUARDA, es lo que se ENVIA.
--
-- ⚠️ `imagenes[1]` Y NO `[0]`: en SQL los arrays empiezan en UNO. En el TypeScript de la
--    app es `[0]`. Es el mismo elemento con dos nombres, y confundirlos daria la SEGUNDA
--    imagen sin dar ningun error -- una foto que no es la principal, en toda la pantalla.
--
-- 🔬 LO QUE AHORRA, medido: 540 kB de `imagenes` -> ~84 kB de `imagen_principal`.
--    Keepa baja de 2.100 kB a ~1.410 kB en el JSON que viaja. Y de rebote **cabe por si
--    sola en el tope de 2 MB por entrada del Data Cache de Vercel**, que hoy no cabia.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    tipo text; n_filas bigint;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo
      FROM pg_attribute a
     WHERE a.attrelid = 'public.keepa_escaparate'::regclass AND a.attname = 'imagenes';

    IF tipo IS NULL THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate no tiene columna `imagenes`. Esta migracion deriva de ella.';
    END IF;
    -- 🔴 El tipo es el supuesto entero de la migracion: `imagenes[1]` sobre un `jsonb`
    --    daria otra cosa (y sin error), y sobre un `text` a secas daria un caracter.
    IF tipo <> 'text[]' THEN
        RAISE EXCEPTION 'ABORTA: `imagenes` es % y esta migracion asume text[]. Con otro tipo, imagenes[1] devuelve algo distinto SIN dar error.', tipo;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_attribute a
                WHERE a.attrelid = 'public.keepa_escaparate'::regclass
                  AND a.attname = 'imagen_principal' AND NOT a.attisdropped) THEN
        RAISE EXCEPTION 'ABORTA: ya existe `imagen_principal`. Si la migracion se relanza a proposito, quitala antes -- pero mira primero por que existe.';
    END IF;

    SELECT count(*) INTO n_filas FROM public.keepa_escaparate;
    RAISE NOTICE 'Antes: % filas en keepa_escaparate.', n_filas;
END
$guardas$;

-- 🔒 `imagenes[1]` es IMMUTABLE (el subindice de array lo es), que es lo que exige una
--    columna generada. Mismo patron que `asin_k`/`dominio_k` del 25-ago.
ALTER TABLE public.keepa_escaparate
  ADD COLUMN imagen_principal text GENERATED ALWAYS AS (imagenes[1]) STORED;

COMMENT ON COLUMN public.keepa_escaparate.imagen_principal IS
    'La PRIMERA URL de `imagenes`, derivada. Existe porque PostgREST no sabe rebanar un text[] en el select= y la pantalla de Inventario solo usa la primera: se bajaban 540 kB de array (6,4 URLs de media por fila) para leer una. Generada y almacenada, asi que no puede desincronizarse y el procesador de Keepa no se entera. OJO: imagenes[1] en SQL es imagenes[0] en TypeScript -- los arrays de SQL empiezan en 1.';

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    n_total bigint; n_con_array bigint; n_con_derivada bigint; n_discrepan bigint;
    bytes_array bigint; bytes_derivada bigint;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE imagenes IS NOT NULL AND array_length(imagenes,1) > 0),
           count(*) FILTER (WHERE imagen_principal IS NOT NULL)
      INTO n_total, n_con_array, n_con_derivada
      FROM public.keepa_escaparate;

    -- 🔴 LA COMPROBACION QUE DE VERDAD PRUEBA ALGO: fila a fila, la derivada tiene que ser
    --    EXACTAMENTE lo que la app leia antes. Un recuento que cuadre no dice que cada
    --    fila tenga SU imagen -- diria lo mismo si estuvieran todas cambiadas de sitio.
    SELECT count(*) INTO n_discrepan
      FROM public.keepa_escaparate
     WHERE imagen_principal IS DISTINCT FROM imagenes[1];
    IF n_discrepan <> 0 THEN
        RAISE EXCEPTION 'ABORTA: % filas donde imagen_principal no es imagenes[1].', n_discrepan;
    END IF;

    -- 🔒 Y que no se haya quedado en blanco: si la derivada saliera NULL en todas, los
    --    dos asserts de arriba pasarian igual (null = null) y la pantalla se quedaria SIN
    --    fotos. Es la comprobacion que no puede fallar, y por eso va esta.
    IF n_con_derivada <> n_con_array THEN
        RAISE EXCEPTION 'ABORTA: % filas tienen array con contenido pero solo % tienen imagen_principal.', n_con_array, n_con_derivada;
    END IF;
    IF n_con_derivada = 0 AND n_total > 0 THEN
        RAISE EXCEPTION 'ABORTA: NINGUNA fila tiene imagen_principal. La pantalla se quedaria sin fotos.';
    END IF;

    -- 🔬 Y el numero que justifica todo esto.
    SELECT sum(octet_length(coalesce(imagenes::text,''))),
           sum(octet_length(coalesce(imagen_principal,'')))
      INTO bytes_array, bytes_derivada
      FROM public.keepa_escaparate;

    RAISE NOTICE 'Testigo OK. % filas · % con imagen · 0 discrepancias.', n_total, n_con_derivada;
    RAISE NOTICE '  el array pesa % kB; la derivada, % kB. Se dejan de enviar % kB por carga.',
        round(bytes_array/1024.0), round(bytes_derivada/1024.0), round((bytes_array - bytes_derivada)/1024.0);
END
$testigo$;

-- -- TESTIGO: QUE SIGA CUADRANDO SI SE MUEVE EL ARRAY -------------------------
-- 🔴 Una columna generada solo vale si se mantiene sola. Aqui se ROMPE a proposito --se
--    le cambia el array a una fila-- y la derivada TIENE que seguirla. Si no, esto seria
--    una foto de hoy que empieza a mentir manana, y sin dar error.
-- 🔒 El toque se deshace con el manejador de excepciones del PROPIO bloque: al atrapar,
--    Postgres revierte lo que el bloque escribio. Sin sub-bloque anidado, que un `END;` a
--    principio de linea le casa al cerrojo 4 del workflow.
DO $sigue$
DECLARE
    antes text; despues text; clave_asin text; clave_dom text;
BEGIN
    SELECT asin, dominio INTO clave_asin, clave_dom
      FROM public.keepa_escaparate WHERE imagenes IS NOT NULL AND array_length(imagenes,1) > 0 LIMIT 1;
    IF clave_asin IS NULL THEN
        RAISE WARNING 'NO COMPROBADO: no hay ninguna fila con imagenes, asi que no hay nada que mover.';
        RETURN;
    END IF;

    SELECT imagen_principal INTO antes FROM public.keepa_escaparate
     WHERE asin = clave_asin AND dominio = clave_dom;

    UPDATE public.keepa_escaparate
       SET imagenes = ARRAY['https://ejemplo.invalido/testigo.jpg'] || imagenes
     WHERE asin = clave_asin AND dominio = clave_dom;

    SELECT imagen_principal INTO despues FROM public.keepa_escaparate
     WHERE asin = clave_asin AND dominio = clave_dom;

    IF despues IS NOT DISTINCT FROM antes THEN
        RAISE EXCEPTION 'ABORTA: se ha puesto una imagen nueva al principio del array y imagen_principal no se ha movido (sigue en %). La columna no se mantiene sola.', antes;
    END IF;
    IF despues <> 'https://ejemplo.invalido/testigo.jpg' THEN
        RAISE EXCEPTION 'ABORTA: imagen_principal es % y tenia que ser la primera del array nuevo. Cuidado con el desfase 0/1 entre SQL y TypeScript.', despues;
    END IF;

    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'deshacer-la-prueba';
EXCEPTION
    WHEN raise_exception THEN
        IF SQLERRM <> 'deshacer-la-prueba' THEN
            RAISE;
        END IF;
        RAISE NOTICE 'Testigo OK (se mantiene sola). Se antepuso una URL y imagen_principal la siguio (y el toque, deshecho).';
END
$sigue$;

-- -- LA PUERTA -----------------------------------------------------------------
-- 🔒 Una columna nueva HEREDA el ACL de su tabla, asi que no hay nada que conceder. Pero
--    eso se MIDE, no se supone: si `authenticated` no pudiera leerla, la pantalla se
--    quedaria sin fotos en cuanto la app dejara de pedir `imagenes`.
--
-- ⚠️ Y ANTES DE MIRARLA, SE MIRA SI HAY ALGO QUE MIRAR. En staging el volcado va con
--    `--no-privileges`, asi que alli `authenticated` NO tiene SELECT **sobre la tabla
--    entera** -- ni sobre `asin`, ni sobre `imagenes`, ni sobre nada. Medido el
--    26-ago-2026 en las dos bases: en staging el ACL de `keepa_escaparate` es
--    `{postgres, service_role}`; en produccion, `{postgres, anon, authenticated,
--    service_role}`.
--    🔴 Comprobar la columna NUEVA sin comprobar antes la TABLA da un rojo que dice
--       «falta un permiso en mi columna» cuando lo que pasa es que no hay permisos de
--       nada. Es una guarda que salta por una causa distinta de la que dice medir, o sea
--       ruido futuro -- y la primera version de este bloque tumbo el ensayo por eso.
--    🔑 Se parte en dos: si la tabla no es legible, esto NO SE PUEDE COMPROBAR aqui y se
--       GRITA; si lo es, la columna nueva tiene que heredarlo y ahi si se ABORTA. El ACL
--       de verdad se verifica EN PRODUCCION al aplicar.
DO $puerta$
DECLARE tabla boolean; columna boolean;
BEGIN
    SELECT has_table_privilege('authenticated', 'public.keepa_escaparate', 'SELECT'),
           has_column_privilege('authenticated', 'public.keepa_escaparate', 'imagen_principal', 'SELECT')
      INTO tabla, columna;

    IF NOT tabla THEN
        RAISE WARNING 'PUERTA NO COMPROBADA EN ESTE ENTORNO: `authenticated` no tiene SELECT sobre keepa_escaparate ENTERA, asi que la columna nueva no dice nada. Pasa porque el volcado va con --no-privileges; NO dice nada sobre produccion.';
        RETURN;
    END IF;

    -- Aqui si: la tabla se lee, o sea que la columna nueva DEBE heredarlo.
    IF NOT columna THEN
        RAISE EXCEPTION 'ABORTA: la tabla es legible por authenticated pero la columna imagen_principal NO. Eso si es un permiso que falta, y la pantalla se quedaria sin fotos.';
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated lee la tabla y tambien imagen_principal.';
END
$puerta$;
