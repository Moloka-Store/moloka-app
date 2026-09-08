-- ============================================================================
-- inventario_fba_cabecera — la LIBRETA apunta también las cargas que NO entran
--                                                                   7-sep-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ, con la medición delante. `inventario_fba_cabecera` nació el 7-sep-2026
--   para censar la forma del informe carga a carga, y el 7-sep-2026 por la tarde
--   estaba a **0 filas en producción**:
--       select count(*) from inventario_fba_cabecera;  ->  0
--   No es un fallo de la tabla: es que las dos únicas cargas posibles no la
--   llenaron. La del 6-sep es ANTERIOR a que la tabla existiera, y la del 7-sep
--   ABORTÓ en la Guarda 1 — y el procesador escribía el censo al final y dentro de
--   la transacción de datos, así que el aborto se lo llevó por delante.
--
-- 🔴 O SEA QUE LA LIBRETA ESTABA MUDA EXACTAMENTE EL DÍA EN QUE TENÍA ALGO QUE
--    DECIR. Es lo contrario de para lo que se hizo: la forma de un informe que se
--    RECHAZA es información, y de la cara — es lo único que mañana distinguirá un
--    informe viejo de uno nuevo, y lo único que dirá desde cuándo Amazon sirve la
--    versión corta.
--
-- QUÉ HACE ESTA MIGRACIÓN: dos columnas, y nada más.
--   · `resultado` — 'cargada' | 'abortada'. Si la carga de ese día entró o no.
--   · `motivo`    — la primera línea del aborto, la que dice qué guarda saltó.
--
-- 🔑 POR QUÉ `resultado` Y NO SÓLO APUNTAR LA FILA. Sin esta columna, una fila de
--    una carga abortada sería una mentira nueva: la serie diría que ese día entró
--    un informe que en realidad no entró, y `cabecera_anterior()` compararía la
--    versión de hoy contra una cabecera que nunca se cargó. Se apunta lo que pasó,
--    no sólo que pasó algo. El procesador lee `resultado IS DISTINCT FROM
--    'abortada'` para saber cuál fue la última carga que DE VERDAD entró.
--
-- 🔒 NULL ES 'CARGADA' PARA QUIEN LEE, y es deliberado: las filas escritas antes de
--    esta columna sólo se escribían cuando la carga había cuadrado. Por eso el
--    procesador usa `IS DISTINCT FROM 'abortada'` y no `= 'cargada'`. Hoy no hay
--    ninguna fila que rescatar (la tabla está a 0), pero la regla se escribe ahora
--    y no el día que haya que adivinarla.
--
-- 🔒 ES ADITIVA Y NO TOCA NINGUNA VISTA. Dos `ADD COLUMN IF NOT EXISTS` sobre una
--    tabla que hoy tiene CERO filas: ni reescribe, ni bloquea, ni hay nada que
--    migrar. No se recrea ningún objeto — y con 27 vistas con `security_invoker`
--    puesto en producción, un `CREATE OR REPLACE VIEW` de más cuesta caro.
--
-- 🔒 LA RLS Y EL ACL NO SE TOCAN. La tabla ya nació cerrada en
--    `2026-09-07_inventario_fba_esperadas_y_censo.sql` (RLS on, 0 políticas, revoke
--    a anon y authenticated por su nombre). Añadir columnas no cambia eso, y
--    volver a lanzar `ENABLE ROW LEVEL SECURITY` pediría un AccessExclusiveLock
--    que aquí no hace ninguna falta.
--
-- ⚠️ EL ENSAYO SÓLO PRUEBA ALGO SI FALTA ALGO. Todo es `IF NOT EXISTS`: sobre un
--    destino que ya esté en el estado final sale verde sin medir nada. El testigo,
--    antes de fiarte:
--        select count(*) from information_schema.columns
--         where table_schema='public' and table_name='inventario_fba_cabecera'
--           and column_name in ('resultado','motivo');   -- 0 = hay algo que probar
--    Medido el 7-sep-2026 en producción: **0** (las columnas de la tabla son
--    fecha_foto, fichero, n_encabezados, encabezados, modelo_disponible,
--    capturado_en).
--
-- VUELTA ATRÁS: `2026-09-07_inventario_fba_libreta_vuelta_atras.sql`.
--
-- ESCALERA: restaurar staging → staging ensayo → aplicar → verificación SQL →
--   producción ensayo → aplicar → verificación SQL. Con `aplicar-migracion.yml`.
-- ============================================================================

SET lock_timeout = '5s';

ALTER TABLE public.inventario_fba_cabecera
    ADD COLUMN IF NOT EXISTS resultado text,
    ADD COLUMN IF NOT EXISTS motivo    text;

COMMENT ON COLUMN public.inventario_fba_cabecera.resultado IS
  'Si la carga de ese dia ENTRO o no: cargada | abortada. Lo escribe '
  'procesador_inventario_fba.py, tambien cuando aborta — la forma de un informe '
  'rechazado es informacion. NULL = fila anterior a esta columna, y esas solo se '
  'escribian cuando la carga cuadraba: por eso quien lee usa '
  'resultado IS DISTINCT FROM ''abortada'', nunca = ''cargada''.';

COMMENT ON COLUMN public.inventario_fba_cabecera.motivo IS
  'La primera linea del aborto, la que dice que guarda salto. NULL en las cargas '
  'que entraron.';

-- ---------------------------------------------------------------------------
-- EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN. Si esto no cuadra, no se
-- escribe nada.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  n_cols int; rls boolean; n_pol int; pk text; n_mentiras int;
BEGIN
  -- 1 · Las dos columnas existen, por nombre.
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'inventario_fba_cabecera'
     AND column_name IN ('resultado', 'motivo');
  IF n_cols <> 2 THEN
    RAISE EXCEPTION 'ABORTA: se esperaban las 2 columnas nuevas y hay %.', n_cols;
  END IF;

  -- 2 · Y la tabla sigue CERRADA y con la misma PK. Un ALTER no debería tocar
  --     nada de esto; se comprueba porque «no debería» no es una comprobación.
  SELECT relrowsecurity INTO rls FROM pg_class
   WHERE oid = 'public.inventario_fba_cabecera'::regclass;
  IF NOT rls THEN
    RAISE EXCEPTION 'ABORTA: la libreta se ha quedado con la RLS APAGADA.';
  END IF;

  SELECT count(*) INTO n_pol FROM pg_policies
   WHERE schemaname = 'public' AND tablename = 'inventario_fba_cabecera';
  IF n_pol <> 0 THEN
    RAISE EXCEPTION 'ABORTA: la libreta tiene % politica(s) y tiene que seguir con CERO.', n_pol;
  END IF;

  IF has_table_privilege('anon', 'public.inventario_fba_cabecera', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `anon` puede leer la libreta.';
  END IF;
  IF has_table_privilege('authenticated', 'public.inventario_fba_cabecera', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` puede leer la libreta.';
  END IF;

  SELECT string_agg(a.attname, ', ' ORDER BY k.ord) INTO pk
    FROM pg_constraint c
    CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
   WHERE c.conrelid = 'public.inventario_fba_cabecera'::regclass AND c.contype = 'p';
  IF pk IS DISTINCT FROM 'fecha_foto' THEN
    RAISE EXCEPTION 'ABORTA: la PK de la libreta es (%) y tiene que ser (fecha_foto).', pk;
  END IF;

  -- 3 · Y que no haya quedado ningún valor fuera del vocabulario. Hoy la tabla
  --     está vacía, así que esto no puede saltar — que es justo cuando se pone.
  SELECT count(*) INTO n_mentiras FROM public.inventario_fba_cabecera
   WHERE resultado IS NOT NULL AND resultado NOT IN ('cargada', 'abortada');
  IF n_mentiras > 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) con un `resultado` que no es cargada ni abortada.', n_mentiras;
  END IF;

  RAISE NOTICE 'Libreta OK: 2 columnas nuevas, RLS on, 0 politicas, PK (fecha_foto), '
               'anon y authenticated fuera. Filas hoy: %',
               (SELECT count(*) FROM public.inventario_fba_cabecera);
END $$;
