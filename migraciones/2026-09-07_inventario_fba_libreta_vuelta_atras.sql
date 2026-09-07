-- ============================================================================
-- VUELTA ATRÁS de `2026-09-07_inventario_fba_libreta_resultado.sql`   7-sep-2026
-- ----------------------------------------------------------------------------
-- 🔴 NO SE APLICA SALVO QUE HAGA FALTA DESHACER. Existe para que deshacer sea un
--    fichero y no una improvisación a las once de la noche.
--
-- QUÉ DESHACE: quita las dos columnas (`resultado`, `motivo`) que la migración
--   añadió a `inventario_fba_cabecera`. La tabla vuelve exactamente a las seis
--   columnas con las que nació el 7-sep-2026.
--
-- 🔴 LO QUE SE PIERDE, DICHO ANTES DE HACERLO: si ya se ha cargado algo con el
--    procesador nuevo, aquí se van por el desagüe los motivos de las cargas que
--    abortaron. Las filas NO se borran (siguen la fecha, el fichero y los
--    encabezados de cada día), pero se pierde saber cuáles entraron y cuáles no.
--    Por eso el número de control de abajo DICE cuántas filas abortadas se están
--    quedando sin marca — no aborta por ello, pero que conste en el log.
--
-- ⚠️ Y CON ESTAS COLUMNAS FUERA, EL PROCESADOR NUEVO NO ARRANCA: `exigir_columnas`
--    aborta pidiendo la migración. Es a propósito. Si se vuelve atrás en la base,
--    hay que volver atrás también en el código (revertir el PR), o la carga del
--    inventario se queda parada — que es ruidoso, y por tanto correcto.
-- ============================================================================

SET lock_timeout = '5s';

DO $$
DECLARE n_abortadas int;
BEGIN
  SELECT count(*) INTO n_abortadas FROM public.inventario_fba_cabecera
   WHERE resultado = 'abortada';
  RAISE NOTICE 'Vuelta atras de la libreta: se pierden la marca y el motivo de % '
               'carga(s) abortada(s). Las filas se quedan.', n_abortadas;
END $$;

ALTER TABLE public.inventario_fba_cabecera
    DROP COLUMN IF EXISTS resultado,
    DROP COLUMN IF EXISTS motivo;

DO $$
DECLARE n_cols int;
BEGIN
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'inventario_fba_cabecera'
     AND column_name IN ('resultado', 'motivo');
  IF n_cols <> 0 THEN
    RAISE EXCEPTION 'ABORTA: quedan % columna(s) de las dos que habia que quitar.', n_cols;
  END IF;
  RAISE NOTICE 'Vuelta atras OK: la libreta vuelve a sus 6 columnas.';
END $$;
