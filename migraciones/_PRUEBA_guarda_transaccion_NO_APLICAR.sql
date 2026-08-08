-- ============================================================================
-- 🔴🔴🔴  NO ES UNA MIGRACIÓN. NO APLICAR. NO TOCA NINGÚN DATO.  🔴🔴🔴
-- ----------------------------------------------------------------------------
-- Esto es un FIXTURE: un fichero roto A PROPÓSITO cuyo único trabajo es hacer
-- SALTAR el cerrojo 4 de `.github/workflows/aplicar-migracion.yml`.
--
-- POR QUÉ EXISTE. La regla de la casa dice que una guarda no se da por buena hasta
--   que se la ha hecho saltar a propósito (§3 de CLAUDE.md). El cerrojo 4 impide que
--   una migración maneje su propia transacción, y eso NO es un capricho: el modo
--   `ensayo` del workflow envuelve el fichero en `BEGIN; … ROLLBACK;` para poder
--   deshacerlo. Si al fichero se le cuela un `END;` —sinónimo de COMMIT fuera de
--   PL/pgSQL— ese END comitea DE VERDAD, el ROLLBACK final solo recibe un WARNING
--   (que no es error, así que ON_ERROR_STOP no salta), psql sale 0 y el job diría
--   "ENSAYO correcto, NO se ha escrito nada" habiendo escrito.
--   Este fichero reproduce exactamente ese caso.
--
-- CÓMO SE USA. Lanzar `Moloka - Aplicar MIGRACION` con:
--     entorno = staging      (nunca produccion: el cerrojo 6 lo prohíbe de plano)
--     fichero = _PRUEBA_guarda_transaccion_NO_APLICAR.sql
--     modo    = ensayo
--   🔑 EL JOB TIENE QUE SALIR EN ROJO, y parar en el paso 4 con el mensaje de que el
--      fichero maneja su propia transacción. Si sale VERDE, el cerrojo 4 miente y hay
--      que arreglarlo antes de fiarse de él para nada.
--
-- POR QUÉ ES INOFENSIVO AUNQUE FALLEN TODAS LAS GUARDAS. Solo tiene dos SELECT de un
--   número. No crea, no borra, no altera, no lee ninguna tabla. El peor caso posible
--   es que se ejecuten dos `select` contra staging y no pase absolutamente nada. Está
--   escrito así a posta: un fixture tiene que poder REVELAR sin poder ROMPER.
--
-- SE QUEDA AQUÍ PARA SIEMPRE. Es un test de regresión: el día que alguien toque el
--   regex del cerrojo 4, esto vuelve a lanzarse y demuestra en un minuto si sigue
--   cerrando. Si se borra, habrá que reinventarlo — y probablemente peor.
-- ============================================================================

select 1 as prueba_antes;

-- 🔴 LA LÍNEA DEL DELITO. `END;` fuera de un bloque PL/pgSQL es un COMMIT.
-- El cerrojo 4 tiene que cazarla y abortar ANTES de conectarse a la base.
END;

select 2 as prueba_despues;
