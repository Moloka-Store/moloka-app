-- ============================================================================
-- MIGRACIÓN 2026-08-03 · Índices en fecha_foto
--   (keepa_escaparate + inventario_internacional)  ·  BLOQUE E4 del encargo Inventario
-- ----------------------------------------------------------------------------
-- POR QUÉ. La pantalla Inventario (Cockpit) resuelve la "foto vigente" de cada
-- informe con MAX(fecha_foto). Medido con EXPLAIN ANALYZE (BLOQUE E del encargo
-- del 3-ago): el MAX(fecha_foto) sobre keepa_escaparate hace un SEQ SCAN completo
-- de ~106 ms — el único punto caro que la BD aporta al cruce (el resto del cruce
-- de los 429 productos: ~380 ms totales). Un índice B-tree convierte ese MAX en
-- un Index Only Scan (lee la última hoja del árbol): de ~106 ms a microsegundos.
-- inventario_internacional se indexa por lo mismo (el cruce también toma su
-- MAX(fecha_foto)).
--
-- QUÉ HACE. Dos índices, ADITIVOS e IDEMPOTENTES. No borra, no reescribe, no toca
-- datos, RLS ni políticas. Es el hermano de
-- 2026-07-29_rls_indices_fuera_del_arranque.sql, que ya indexó asin/dominio/country
-- de estas mismas tablas VIVAS pero dejó fuera fecha_foto. Los históricos
-- (`*_historico`) ya tenían su índice de fecha desde aquella migración; esto es
-- para las tablas VIVAS, que son las que el Cockpit consulta en cada carga.
--
-- 🔒 fecha_foto verificada como columna `date` en las DOS tablas (prod, 3-ago).
--    Un índice B-tree ascendente sirve el MAX sin necesidad de DESC.
--
-- 🔒 ESCALERA + lock_timeout corto (§4 CLAUDE.md · criterio "DDL en prod":
--    falla rápido, no encola). Un CREATE INDEX toma ShareLock: bloquea las
--    ESCRITURAS de la tabla mientras construye (los SELECT siguen). Las dos tablas
--    son pequeñas (<1.000 filas) → el build es de milisegundos, pero el lock_timeout
--    garantiza que, si algo tiene la tabla tomada, este DDL FALLA RÁPIDO en vez de
--    encolarse detrás (la familia de lock que tumbó la base el 28-jul 15:47).
--    Se aplica por la escalera: staging → PR → prod. Advisors después.
-- ============================================================================

SET lock_timeout = '3s';

CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_fecha_foto
    ON keepa_escaparate (fecha_foto);

CREATE INDEX IF NOT EXISTS idx_inventario_internacional_fecha_foto
    ON inventario_internacional (fecha_foto);
