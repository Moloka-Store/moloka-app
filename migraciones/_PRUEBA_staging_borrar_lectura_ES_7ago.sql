-- ============================================================================
-- 🔴🔴🔴  NO ES UNA MIGRACIÓN. SOLO STAGING. BORRA DATOS A PROPÓSITO.  🔴🔴🔴
-- ----------------------------------------------------------------------------
-- Esto es ANDAMIO DE PRUEBA: monta un escenario en staging para poder ejercitar una
-- rama de código que con los datos actuales NO se puede alcanzar.
--
-- QUÉ RAMA. La guarda 6.14 de `procesador_custom_analytics.py` distingue desde el
--   10-ago-2026 dos clases de retroceso: PUNTUAL (los totales suben, bajan unos pocos
--   ASIN → grita y carga) y GLOBAL (bajan los totales acumulados → aborta). La rama
--   PUNTUAL se ejercitó con `metric-data (1).xlsx` de IT. La GLOBAL no se podía: el
--   único fichero que la dispara —`CA_ES_02ago_DISCONTINUO.xlsx`, 246 ASIN contra 321—
--   es del 2-ago, ANTERIOR a la lectura de ES del 7-ago que hay cargada, y la 6.14
--   solo compara hacia adelante. Así que ni la mira.
--
-- QUÉ HACE. Borra de STAGING la lectura de ES del 7-ago. Con eso la última de ES pasa a
--   ser la del 30-jul, el fichero del 2-ago queda POR DELANTE, y la 6.14 sí lo compara.
--
-- CÓMO SE USA:
--   1) `Moloka - Aplicar MIGRACION` · entorno=staging · modo=aplicar ·
--      fichero=_PRUEBA_staging_borrar_lectura_ES_7ago.sql
--   2) `Moloka - Procesar CUSTOM ANALYTICS` · entorno=staging · modo=ensayo · pais=ES ·
--      fichero=CA_ES_02ago_DISCONTINUO.xlsx
--      🔑 TIENE QUE ABORTAR, y por la rama GLOBAL («bajan los totales de …»). Si aborta
--         por la PUNTUAL, la lógica está al revés. Si no aborta, peor.
--   3) `Moloka - Restaurar backup en STAGING` para dejar staging como estaba.
--
-- 🔒 POR QUÉ ES SEGURO TENERLO EN EL REPO. Se llama `_PRUEBA*`, y el cerrojo 6 de
--   `aplicar-migracion.yml` RECHAZA de plano cualquier `_PRUEBA*` contra producción —ni
--   en ensayo, ni con confirmación, ni con nada—. No puede tocar la base de Elena. Y lo
--   que borra en staging vuelve con `restaurar-staging.yml`, que es de dónde salió.
--
-- ⚠️ LA GUARDA DE ESTE PROPIO FICHERO: aborta si la base no es la que espera. Un
--   `DELETE` que no encuentra su escenario es un `DELETE` que está en el sitio
--   equivocado, y prefiero que se pare a que borre otra cosa.
-- ============================================================================

DO $$
DECLARE n_borradas int; n_es_antes int; n_es_despues int;
BEGIN
  SELECT count(*) INTO n_es_antes FROM public.demanda_asin WHERE pais = 'ES';

  -- 🔴 Cerrojo: en producción esto NO debe correr nunca (el cerrojo 6 del workflow ya lo
  --   impide), pero un fichero que borra datos lleva su propio cinturón.
  IF current_setting('server_version_num')::int > 0
     AND EXISTS (SELECT 1 FROM public.demanda_asin
                  WHERE pais = 'ES' AND leido_at = TIMESTAMPTZ '2026-08-07 18:03:29.812+00')
  THEN
    DELETE FROM public.demanda_asin
     WHERE pais = 'ES' AND leido_at = TIMESTAMPTZ '2026-08-07 18:03:29.812+00';
    GET DIAGNOSTICS n_borradas = ROW_COUNT;
  ELSE
    RAISE EXCEPTION
      'ABORTA: no encuentro la lectura de ES del 2026-08-07 18:03:29.812+00 en esta base. '
      'O ya se borró, o esta no es la staging recién restaurada que este andamio espera. '
      'PARA: un DELETE que no encuentra su escenario está en el sitio equivocado.';
  END IF;

  SELECT count(*) INTO n_es_despues FROM public.demanda_asin WHERE pais = 'ES';
  RAISE NOTICE 'Andamio montado: borradas % filas de la lectura ES 7-ago. ES pasa de % a % filas.',
               n_borradas, n_es_antes, n_es_despues;
  RAISE NOTICE 'La última lectura de ES es ahora la del 30-jul. Ya se puede ejercitar la rama GLOBAL.';
END $$;
