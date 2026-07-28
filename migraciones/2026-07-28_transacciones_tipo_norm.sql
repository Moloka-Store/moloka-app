-- ============================================================================
-- Migración TRANSACCIONES — columna tipo_norm (tipo de movimiento CANÓNICO)
-- ----------------------------------------------------------------------------
-- El `tipo` se guarda crudo en el idioma del informe (Pedido/Ordine/Commande,
-- Reembolso/Rimborso/Remboursement…). La vista de rentabilidad cableaba los
-- reembolsos a los 3 literales → el día que entre DE, los reembolsos alemanes se
-- caen en silencio (el mismo techo de la v1 con `for pais in ('IT','FR')`).
--
-- `tipo_norm` guarda el canon (procesador_transacciones.py:TIPO_CANON), la vista
-- lee de ahí, y el `tipo` crudo queda intacto para auditar. Aditivo y NULLABLE.
--
-- Se PUEBLA recargando los 3 países por el procesador (reusa TIPO_CANON, una sola
-- fuente de verdad; NO se backfillea con un CASE en SQL que podría divergir del
-- mapa del código). Esa recarga es idempotente (carga por rango) y sirve de prueba:
-- los totales por país tienen que quedar al céntimo. Objetivos MEDIDOS en prod hoy,
-- antes del cambio (facturación s/IVA · uds · beneficio):
--   ES 136.956,56 · 13.306 · 15.583,03    IT 6.369,98 · 367 · 926,68
--   FR 3.870,82 · 236 · 508,50
-- Y reembolsos (por los 3 literales actuales = deben salir idénticos por tipo_norm):
--   ES 293 mov / −3.245,19 €   IT 6 / −99,07 €   FR 1 / −19,99 €
--
-- 🔴 Un literal SIN canon → tipo_norm NULL y el procesador GRITA en el resumen.
-- IDEMPOTENTE (IF NOT EXISTS).
-- ============================================================================

ALTER TABLE transacciones_movimientos ADD COLUMN IF NOT EXISTS tipo_norm text;
CREATE INDEX IF NOT EXISTS idx_trans_tipo_norm ON transacciones_movimientos(tipo_norm);
