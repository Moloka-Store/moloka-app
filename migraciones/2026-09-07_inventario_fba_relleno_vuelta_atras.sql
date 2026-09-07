-- ============================================================================
-- VUELTA ATRÁS de `2026-09-07_inventario_fba_relleno_disponible_estimado.sql`.
--                                                                   7-sep-2026
-- ----------------------------------------------------------------------------
-- 🔴 PARA QUÉ EXISTE Y CUÁNDO SE LANZA. Deja las tres columnas del puente
--   (`disponible_estimado`, `disponible_origen`, `disponible_fuente_fecha`) a NULO
--   otra vez, que es EXACTAMENTE el estado en que las dejó la migración de esta
--   mañana: nacieron vacías y las llena el procesador. Se lanza si el relleno
--   escribe algo que no cuadra y hace falta volver al suelo conocido antes de
--   ponerse a investigar.
--
-- 🔒 POR QUÉ ES SEGURA, y esto conviene tenerlo medido y no supuesto: el 7-sep-2026
--   los ÚNICOS objetos de la base que mencionan `disponible_estimado` son las vistas
--   `salud_fba` (que la deja pasar tal cual, fila a fila) y `v_salud_asin` (que la
--   suma sólo cuando TODAS las fichas del ASIN la traen). Ninguna pantalla, ninguna
--   decisión y ningún precio la leen. Vaciarla devuelve las dos vistas a lo que
--   enseñaban ayer: nulo. No apaga nada que Elena esté mirando.
--
-- 🔑 QUÉ **NO** DESHACE, y es a propósito: las columnas siguen EXISTIENDO. Quitarlas
--   sería deshacer la migración de esta mañana, que es otra cosa y tiene su propio
--   camino. Aquí sólo se vacía lo escrito.
--
-- 🔴 NO TOCA NINGUNA VISTA. Ni `salud_fba`, ni `v_salud_asin`, ni ninguna otra: hay
--   seis en esta base que pierden `security_invoker` al recrearse, y una vuelta atrás
--   que además apaga una opción de seguridad en silencio no es una vuelta atrás.
--   Tampoco toca permisos, ni RLS, ni la Guarda 12 del procesador.
--
-- 🔴 SIN UNA SOLA CIFRA ABSOLUTA, por la misma razón de siempre: la escalera pasa
--   por STAGING, donde hay 362 fichas y 1.440 fotogramas contra las 381 y 4.042 de
--   producción. Lo que se exige no es un número: es que **esto no mueva nada más que
--   las tres columnas**. Se fotografía el antes y se compara contra él.
--
-- 🔒 ES IDEMPOTENTE: lanzarla dos veces deja lo mismo (todo a nulo). Y si se lanza
--   sin haber rellenado, tampoco pasa nada — no habrá nada que vaciar.
--
-- ⚠️ EL ENSAYO SÓLO PRUEBA ALGO SI HAY ALGO QUE DESHACER. El testigo, antes:
--       select count(disponible_origen) as escritas from public.inventario_fba;
--   Si sale 0, esta migración no está probando nada: primero se aplica el relleno.
--   Por eso el ciclo completo que hay que hacer en staging ANTES de tocar producción
--   es: aplicar relleno → verificar → aplicar ESTO → verificar 0 → aplicar relleno
--   otra vez → verificar que vuelven las mismas cifras.
-- ============================================================================

-- ── 1) LA FOTO DEL «ANTES» ──────────────────────────────────────────────────
-- La huella se calcula sobre la fila SIN las tres columnas del puente: es lo que
-- permite exigir «no se ha movido NADA más» sin escribir un número de producción.
CREATE TEMP TABLE _antes_fba ON COMMIT DROP AS
SELECT count(*) AS filas,
       count(t.disponible_origen) AS con_origen,
       md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                       - 'disponible_fuente_fecha')::text, ',' ORDER BY t.sku)) AS huella_resto
  FROM public.inventario_fba t;

CREATE TEMP TABLE _antes_hist ON COMMIT DROP AS
SELECT count(*) AS filas,
       count(t.disponible_origen) AS con_origen,
       md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                       - 'disponible_fuente_fecha')::text, ','
                      ORDER BY t.fecha_foto, t.sku)) AS huella_resto
  FROM public.inventario_fba_historico t;

-- ── 2) VACIAR LAS TRES COLUMNAS, Y SÓLO LAS TRES ────────────────────────────
-- 🔑 El `WHERE` no es un adorno: sin él, un UPDATE sobre la tabla entera reescribe
--    4.042 filas para dejarlas igual. Con él, sólo se tocan las que tienen algo.
UPDATE public.inventario_fba_historico
   SET disponible_estimado = NULL,
       disponible_origen = NULL,
       disponible_fuente_fecha = NULL
 WHERE disponible_estimado IS NOT NULL
    OR disponible_origen IS NOT NULL
    OR disponible_fuente_fecha IS NOT NULL;

UPDATE public.inventario_fba
   SET disponible_estimado = NULL,
       disponible_origen = NULL,
       disponible_fuente_fecha = NULL
 WHERE disponible_estimado IS NOT NULL
    OR disponible_origen IS NOT NULL
    OR disponible_fuente_fecha IS NOT NULL;

-- ── 3) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  n bigint; txt text;
BEGIN
  -- 3.1 · Las tres columnas están VACÍAS en las dos tablas. Las tres, no sólo el
  --       origen: vaciar una y dejar otra sería un tercer estado.
  SELECT (SELECT count(disponible_estimado) + count(disponible_origen)
                 + count(disponible_fuente_fecha) FROM public.inventario_fba)
       + (SELECT count(disponible_estimado) + count(disponible_origen)
                 + count(disponible_fuente_fecha) FROM public.inventario_fba_historico)
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: quedan % valor(es) escritos en las tres columnas del puente.', n;
  END IF;

  -- 3.2 · LAS COLUMNAS SIGUEN EXISTIENDO. Esto vacía, no desmonta: si alguien
  --       convierte esta vuelta atrás en un DROP COLUMN, aquí se entera.
  SELECT count(*) INTO n FROM information_schema.columns
   WHERE table_schema = 'public'
     AND table_name IN ('inventario_fba', 'inventario_fba_historico')
     AND column_name IN ('disponible_estimado', 'disponible_origen',
                         'disponible_fuente_fecha');
  IF n <> 6 THEN
    RAISE EXCEPTION 'ABORTA: deberian seguir estando las 6 columnas del puente y hay %. '
                    'Esta vuelta atras VACIA, no quita columnas.', n;
  END IF;

  -- 3.3 · NO SE HA MOVIDO NADA MÁS. Mismo numero de filas y el resto de cada fila
  --       bit a bit igual que antes del UPDATE.
  SELECT a.filas INTO n FROM _antes_fba a;
  IF n <> (SELECT count(*) FROM public.inventario_fba) THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba tenia % filas y ahora tiene otra cosa.', n;
  END IF;
  SELECT a.filas INTO n FROM _antes_hist a;
  IF n <> (SELECT count(*) FROM public.inventario_fba_historico) THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba_historico tenia % filas y ahora tiene otra cosa.', n;
  END IF;

  SELECT a.huella_resto INTO txt FROM _antes_fba a;
  IF txt IS DISTINCT FROM (
        SELECT md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                               - 'disponible_fuente_fecha')::text, ',' ORDER BY t.sku))
          FROM public.inventario_fba t) THEN
    RAISE EXCEPTION 'ABORTA: en inventario_fba ha cambiado alguna columna que NO es del '
                    'puente. Esta vuelta atras solo puede tocar las tres.';
  END IF;
  SELECT a.huella_resto INTO txt FROM _antes_hist a;
  IF txt IS DISTINCT FROM (
        SELECT md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                               - 'disponible_fuente_fecha')::text, ','
                              ORDER BY t.fecha_foto, t.sku))
          FROM public.inventario_fba_historico t) THEN
    RAISE EXCEPTION 'ABORTA: en inventario_fba_historico ha cambiado alguna columna que NO '
                    'es del puente.';
  END IF;

  -- 3.4 · Y LAS DOS TABLAS SIGUEN CERRADAS. Un UPDATE no cambia el ACL, pero
  --       comprobarlo es barato y el dia que no se cumpla hay que enterarse.
  SELECT count(*) INTO n FROM pg_class
   WHERE oid IN ('public.inventario_fba'::regclass,
                 'public.inventario_fba_historico'::regclass)
     AND relrowsecurity;
  IF n <> 2 THEN
    RAISE EXCEPTION 'ABORTA: solo % de las 2 tablas tienen la RLS activa.', n;
  END IF;

  SELECT a.con_origen INTO n FROM _antes_fba a;
  RAISE NOTICE 'Vuelta atras OK: se han vaciado % fila(s) de la foto viva y % del '
               'historico; nada mas se ha movido y las 6 columnas siguen ahi.',
               n, (SELECT b.con_origen FROM _antes_hist b);
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job):
--
--   select 'foto viva' as tabla, count(*) as filas,
--          count(disponible_estimado) as est, count(disponible_origen) as ori,
--          count(disponible_fuente_fecha) as fue
--     from public.inventario_fba
--   union all
--   select 'historico', count(*), count(disponible_estimado), count(disponible_origen),
--          count(disponible_fuente_fecha)
--     from public.inventario_fba_historico;
--   -- → est/ori/fue a 0 en las dos, y `filas` igual que antes.
--
--   -- y las columnas siguen existiendo (esto VACIA, no desmonta):
--   select table_name, column_name from information_schema.columns
--    where table_schema='public'
--      and table_name in ('inventario_fba','inventario_fba_historico')
--      and column_name like 'disponible_%' order by 1,2;
--   -- → 6 filas.
-- ============================================================================
