-- ============================================================================
-- MIGRACIÓN 2026-08-03 · Un índice en keepa_escaparate.fecha_foto
--   BLOQUE E4 del encargo Inventario
-- ----------------------------------------------------------------------------
-- UN índice, uno solo. No "por si acaso".
--
-- POR QUÉ. El Cockpit resuelve la "foto vigente" de Keepa con MAX(fecha_foto).
-- Medido con EXPLAIN ANALYZE:
--   · PROD, hoy (sin índice):  Seq Scan de 476 filas → 177 ms de ejecución.
--     (El encargo lo midió en 106 ms; el tiempo de un seq scan baila con la caché,
--      pero SIEMPRE es un escaneo completo.)
--   · Con índice (medido en staging): Index Only Scan Backward + Limit 1 → 0,8 ms.
-- keepa_escaparate es CARÍSIMA de escanear porque sus filas son ANCHÍSIMAS (~90
-- columnas de mercado de Keepa): el seq scan arrastra muchas páginas de heap. El
-- índice sobre una sola columna lo convierte en leer la última hoja del árbol.
-- Mejora clara y grande (177 ms → 0,8 ms). Se queda.
--
-- POR QUÉ *NO* inventario_internacional (el borrador del encargo lo pedía también,
-- pero se MIDIÓ y no pasa el listón):
--   · PROD: MAX(fecha_foto) = Seq Scan de 306 filas → 2,3 ms. Ya es rápido.
--   · Con índice: 0,3 ms. Ahorra ~2 ms sobre una tabla-FOTO que no crece (se
--     reescribe entera en cada carga, ~306 filas). Un índice que ahorra 2 ms pero
--     cuesta en CADA reescritura de esa foto no compensa. Regla de Fernando: si no
--     baja de forma clara, el índice sobra. → fuera.
--   · (Su histórico `inventario_internacional_historico`, que SÍ crece, ya tiene su
--      índice de fecha desde 2026-07-29_rls_indices_fuera_del_arranque.sql.)
--   Si el filtro por-mercado (BLOQUE D, cuando entre) lo necesitara, es una línea.
--
-- 🔒 CREATE INDEX A SECAS (no CONCURRENTLY), y es seguro AQUÍ, medido:
--   · keepa_escaparate = 476 filas. Un CREATE INDEX normal toma ShareLock (bloquea
--     ESCRITURAS de la tabla mientras construye; los SELECT siguen). Construir un
--     B-tree de 476 filas es de milisegundos.
--   · Quién escribe keepa_escaparate: solo el procesador_keepa_escaparate.py, a
--     ráfagas (no la app de Elena en vivo). La probabilidad de que el build coincida
--     con una escritura es casi nula, y si coincide, espera milisegundos.
--   · CONCURRENTLY evita el ShareLock pero NO puede correr dentro de una transacción,
--     tarda más y deja índice inválido si falla. Para 476 filas es pólvora para matar
--     moscas. El precedente de la casa (2026-07-29_rls_indices) también usa CREATE
--     INDEX a secas para estas mismas tablas.
--   · lock_timeout corto: si algo tuviera la tabla tomada, este DDL FALLA RÁPIDO en
--     vez de encolarse detrás (§4 CLAUDE.md). Es la base que usa Elena.
--
-- IDEMPOTENTE (IF NOT EXISTS). Aditivo: no toca datos, RLS ni políticas.
-- Escalera: staging → PR → prod. Advisors después.
-- ============================================================================

SET lock_timeout = '3s';

CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_fecha_foto
    ON keepa_escaparate (fecha_foto);
