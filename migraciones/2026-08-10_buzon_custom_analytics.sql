-- ============================================================================
-- 🔒 SELLO DE LO APLICADO — leer ESTO antes de contrastar hashes.
--   Esta migración se aplicó en PRODUCCIÓN el 10-ago-2026, run 31414939816, con:
--       sha256  a018731b0a7aa862b6f576b038a04b39240ba826f2996d4654783833f2f8a754
--       commit  b5b333f262771742f9ad63b89c4c10d292ae4692
--   DESPUÉS se amplió esta cabecera. Solo comentarios: no cambió ni una línea de SQL.
--   Por eso el sha256 del fichero YA NO CUADRA con el que publicó aquel run. No es una
--   manipulación: es esto, y por eso está escrito aquí.
--   🔑 CONVENCIÓN: si hay que ampliar una migración YA APLICADA, se deja este sello con
--   el hash y el run originales. Un hash que no cuadra sin explicación es exactamente la
--   alarma que el sello evita — y una alarma que salta sin motivo se deja de mirar.
--   Si lo que cambia es el SQL, entonces NO es una ampliación: es otra migración.
-- ============================================================================
-- moloka_buzones_fase0(): AÑADIR 'custom_analytics'  ·  10-ago-2026
-- ----------------------------------------------------------------------------
-- 🔴 LA LECCIÓN QUE DEJA ESTA MIGRACIÓN, por si sirve para la siguiente:
--   EN UNA BASE DONDE EL BACKUP NO CUBRE TODOS LOS ESQUEMAS, CUALQUIER NÚMERO
--   ABSOLUTO SOBRE LO QUE NO SE COPIA ES UN FALSO ROJO ESPERANDO. SE COMPARAN
--   INVARIANTES, NO CIFRAS.
--   Aquí en concreto: `backup-bd.yml` vuelca con `--schema=public`, así que las
--   políticas de `storage.objects` no están en la copia y `restaurar-staging.yml` no
--   las repone. La guarda pedida era "tienen que ser 4 políticas"; habría dado ROJO en
--   staging por el alcance del backup, no por la migración. Se guarda el recuento ANTES
--   (paso 1b) y se compara DESPUÉS: el invariante real de un CREATE OR REPLACE es "no
--   se llevó ninguna por delante", y eso es cierto valgan 4 o valga otra cosa.
--   Generalizado en §3 de CLAUDE.md: una comprobación que puede saltar por una causa
--   distinta de la que dice medir no es una guarda, es ruido futuro.
-- ----------------------------------------------------------------------------
-- EL BLOQUEO. Al subir un .xlsx al buzón de Custom Analytics desde la app v2:
--     "No se pudo firmar la subida: new row violates row-level security policy"
--
-- LA CAUSA, medida en producción el 10-ago-2026 (no deducida):
--   Las políticas buzones_v2_* de storage.objects exigen que la carpeta de primer
--   nivel esté en public.moloka_buzones_fase0(). Esa función devuelve SIETE carpetas
--   y 'custom_analytics' NO está entre ellas:
--       salud_fba · internacional · keepa_escaparate · all_listings · ledger ·
--       paneu_aptos · transacciones
--   Comprobado: select 'custom_analytics' = any(public.moloka_buzones_fase0())
--               → false
--
-- POR QUÉ NO SALTÓ ANTES. El buzón se creó, entró en el catálogo de la v2, se le hizo
--   procesador y workflow... y nadie añadió la carpeta a la función que AUTORIZA la
--   subida. Es el último eslabón de la cadena y el único que no se probó. Los ocho
--   ficheros que ya hay en ese buzón entraron por el conector de Supabase, que va como
--   `postgres` y tiene rolbypassrls: funcionaba por un camino y no por el otro. La
--   prueba de que nadie lo subió nunca desde la app es que los ocho tienen owner_id
--   vacío y no hay ni un registro de custom_analytics en informes_subidos.
--
-- 🔴 CREATE OR REPLACE, JAMÁS DROP. Medido hoy: las CUATRO políticas buzones_v2_*
--   (select, insert, update, delete) invocan esta función. Un `DROP ... CASCADE` se
--   las llevaría por delante y habría que rehacerlas y coordinarlas — que es
--   exactamente el CASCADE que casi nos cuesta el día 9. CREATE OR REPLACE conserva
--   la firma, y con ella las cuatro políticas y sus permisos.
--
-- 🔒 SE CONSERVAN, y el paso 3 lo verifica: IMMUTABLE, SET search_path TO '',
--   LANGUAGE sql, RETURNS text[] y las siete carpetas que ya estaban.
--
-- ESCALERA: staging (ensayo → aplicar) → verificación SQL → producción (ensayo →
--   aplicar) → verificación SQL. Se aplica con aplicar-migracion.yml.
--
-- 🔒 RIESGO PARA ELENA: nulo por construcción. Este cambio solo AÑADE una carpeta a
--   una lista de autorización; no quita ninguna ni toca las políticas. Nada de lo que
--   hoy funciona deja de funcionar. Lo que hoy está bloqueado, se desbloquea.
-- ============================================================================

-- ── 1) GUARDA: la función tiene que ser la que creemos ──────────────────────
-- Si alguien la cambió por otro camino (el desfase repo-base de siempre), PARA antes
-- de sobrescribirla: reemplazar a ciegas una función que no es la que leímos es cómo
-- se pierde trabajo ajeno sin enterarse.
DO $$
DECLARE n_carpetas int; es_inmutable boolean; sp text[];
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc
                  WHERE proname = 'moloka_buzones_fase0'
                    AND pronamespace = 'public'::regnamespace) THEN
    RAISE EXCEPTION 'ABORTA: public.moloka_buzones_fase0() no existe en esta base. '
                    'Aquí no se crea de cero: PARA y mira qué base es.';
  END IF;

  SELECT array_length(public.moloka_buzones_fase0(), 1) INTO n_carpetas;
  SELECT provolatile = 'i', proconfig INTO es_inmutable, sp
    FROM pg_proc WHERE proname = 'moloka_buzones_fase0'
                   AND pronamespace = 'public'::regnamespace;

  IF n_carpetas <> 7 THEN
    RAISE EXCEPTION 'ABORTA: esperaba 7 carpetas antes del cambio y hay %. '
                    'La función no es la que se leyó el 10-ago. PARA y compara.', n_carpetas;
  END IF;
  IF NOT es_inmutable THEN
    RAISE EXCEPTION 'ABORTA: la función ya no es IMMUTABLE. PARA: algo la cambió.';
  END IF;
  IF sp IS DISTINCT FROM ARRAY['search_path=""'] THEN
    RAISE EXCEPTION 'ABORTA: el search_path de la función no es el esperado (es %). PARA.', sp;
  END IF;

  RAISE NOTICE 'Guarda 1 OK: 7 carpetas, IMMUTABLE, search_path a vacío.';
END $$;

-- ── 1b) FOTO DE LAS POLÍTICAS **ANTES** ─────────────────────────────────────
-- 🔴 Se guarda el RECUENTO PREVIO, no un número fijo, y el paso 3 comprueba que no
--   ha cambiado. El invariante real de un CREATE OR REPLACE es "no se llevó ninguna
--   política por delante", y eso es cierto valga 4 o valga otra cosa.
--   POR QUÉ NO UN 4 A PELO: `backup-bd.yml` vuelca con `--schema=public`, así que las
--   políticas de `storage.objects` NO están en la copia y `restaurar-staging.yml` no
--   las repone. Un `<> 4` daría ROJO en staging por el alcance del backup, no por la
--   migración — un falso rojo, que es como se muere una guarda (§5 de CLAUDE.md).
--   En PRODUCCIÓN hoy son 4 (select, insert, update, delete), medido el 10-ago-2026.
CREATE TEMP TABLE _control_buzones AS
SELECT count(*)::int AS n_politicas_antes
  FROM pg_policy
 WHERE polrelid = 'storage.objects'::regclass
   AND polname LIKE 'buzones_v2%';

DO $$
DECLARE n int;
BEGIN
  SELECT n_politicas_antes INTO n FROM _control_buzones;
  RAISE NOTICE 'Políticas buzones_v2_* ANTES del cambio: %', n;
END $$;

-- ── 2) EL CAMBIO: una carpeta más ───────────────────────────────────────────
-- Firma idéntica (RETURNS text[], LANGUAGE sql, IMMUTABLE, search_path ''), para que
-- las cuatro políticas sigan colgando de ella sin enterarse.
CREATE OR REPLACE FUNCTION public.moloka_buzones_fase0()
 RETURNS text[]
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select array['salud_fba','internacional','keepa_escaparate',
               'all_listings','ledger','paneu_aptos','transacciones',
               'custom_analytics']
$function$;

-- ── 3) GUARDA: el número de control, DENTRO de la transacción ───────────────
-- Si algo de esto no cuadra, RAISE aborta y el cambio entero se deshace. Verificar
-- después de commitear sería enterarse tarde.
DO $$
DECLARE
  n_carpetas int; n_politicas int; n_antes int; es_inmutable boolean; sp text[];
  faltan text;
BEGIN
  SELECT array_length(public.moloka_buzones_fase0(), 1) INTO n_carpetas;

  IF NOT ('custom_analytics' = any(public.moloka_buzones_fase0())) THEN
    RAISE EXCEPTION 'ABORTA: tras el REPLACE, custom_analytics sigue sin estar autorizado.';
  END IF;
  IF n_carpetas <> 8 THEN
    RAISE EXCEPTION 'ABORTA: esperaba 8 carpetas y hay %.', n_carpetas;
  END IF;

  -- Las siete de antes siguen: añadir no puede haber quitado nada.
  SELECT string_agg(c, ', ') INTO faltan
    FROM unnest(ARRAY['salud_fba','internacional','keepa_escaparate',
                      'all_listings','ledger','paneu_aptos','transacciones']) AS c
   WHERE NOT (c = any(public.moloka_buzones_fase0()));
  IF faltan IS NOT NULL THEN
    RAISE EXCEPTION 'ABORTA: han desaparecido carpetas que estaban: %', faltan;
  END IF;

  -- Las propiedades que sostienen la seguridad.
  SELECT provolatile = 'i', proconfig INTO es_inmutable, sp
    FROM pg_proc WHERE proname = 'moloka_buzones_fase0'
                   AND pronamespace = 'public'::regnamespace;
  IF NOT es_inmutable THEN
    RAISE EXCEPTION 'ABORTA: la función ha dejado de ser IMMUTABLE.';
  END IF;
  IF sp IS DISTINCT FROM ARRAY['search_path=""'] THEN
    RAISE EXCEPTION 'ABORTA: se ha perdido el search_path a vacío (es %).', sp;
  END IF;

  -- 🔴 Lo que un DROP se habría llevado: las políticas. Se compara contra el recuento
  --   PREVIO (paso 1b), no contra un 4 fijo: el invariante es que el REPLACE no se
  --   lleve ninguna, y eso vale en cualquier base. Un número fijo daría falso rojo en
  --   staging, donde el backup (--schema=public) no repone storage.objects.
  SELECT count(*) INTO n_politicas
    FROM pg_policy
   WHERE polrelid = 'storage.objects'::regclass
     AND polname LIKE 'buzones_v2%';
  SELECT n_politicas_antes INTO n_antes FROM _control_buzones;

  IF n_politicas <> n_antes THEN
    RAISE EXCEPTION 'ABORTA: había % políticas buzones_v2_* antes y ahora hay %. '
                    'El CREATE OR REPLACE se ha llevado alguna por delante — eso solo pasa '
                    'con un DROP. PARA y mira qué se ha ejecutado.', n_antes, n_politicas;
  END IF;

  RAISE NOTICE 'Número de control OK: 8 carpetas (custom_analytics dentro), IMMUTABLE, '
               'search_path a vacío, y las % políticas buzones_v2_* siguen en pie '
               '(las mismas que antes del cambio).', n_politicas;
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (Fernando la cuenta por SQL, aparte del job):
--
--   select 'custom_analytics' = any(public.moloka_buzones_fase0())  as autorizado,
--          array_length(public.moloka_buzones_fase0(), 1)           as n_carpetas,
--          public.moloka_buzones_fase0()                            as carpetas;
--   -- → true · 8 · {...,custom_analytics}
--
--   select polname,
--          case polcmd when 'r' then 'SELECT' when 'a' then 'INSERT'
--                      when 'w' then 'UPDATE' when 'd' then 'DELETE' end as comando
--     from pg_policy
--    where polrelid = 'storage.objects'::regclass
--      and polname like 'buzones_v2%'
--    order by polname;
--   -- → 4 filas: delete, insert, select, update
--
-- Y la prueba de verdad, la única que cierra el caso: que Fernando suba
-- metric-data (1).xlsx al buzón DESDE LA APP y entre. El SQL dice que la puerta está
-- abierta; sólo cruzarla lo demuestra.
-- ============================================================================
