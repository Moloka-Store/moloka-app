-- ============================================================================
-- MIGRACIÓN 2026-07-29 · RLS e ÍNDICES salen del arranque de los procesadores
-- ----------------------------------------------------------------------------
-- HERMANA de 2026-07-29_vistas_cruce_fuera_del_arranque.sql (#63). Aquella sacó
-- las VISTAS del arranque; ésta saca lo que quedaba: cada procesador seguía
-- lanzando en CADA carga, sobre la tabla que va a cargar:
--     ALTER TABLE <tabla> ENABLE ROW LEVEL SECURITY;   -- AccessExclusiveLock
--     CREATE INDEX IF NOT EXISTS ...;                   -- ShareLock
--     (all_listings) ALTER TABLE ... ADD COLUMN IF NOT EXISTS procesado_en ...  -- AccessExclusiveLock
--
-- POR QUÉ IMPORTA. El `ALTER TABLE ... ENABLE RLS` (y el `ADD COLUMN`) piden
-- AccessExclusiveLock sobre la tabla EN CADA carga. Ese es el lock que en la
-- prueba del 29-jul dejaba fuera al sondeo de la cola (que lee esas mismas tablas
-- vía frescura_informes()): el SELECT del sondeo se encolaba esperando
-- AccessShareLock y moría por statement_timeout. Con 5 informes en serie, cinco
-- minutos de esperas. Es la misma familia del lock que el 28-jul a las 15:47
-- tumbó la base. `ENABLE RLS` / `CREATE INDEX` / `ADD COLUMN` son MIGRACIÓN
-- (se hacen una vez), no arranque. `CREATE TABLE IF NOT EXISTS` es barato y se
-- queda en el procesador.
--
-- QUÉ HACE. Deja RLS activa, los índices y (en all_listings) la columna
-- procesado_en, UNA vez e IDEMPOTENTE. Extraído VERBATIM del código que ya corría
-- en producción: mismas tablas, mismos índices, misma columna — solo cambia CUÁNDO
-- se ejecuta. En una base ya curada (prod/staging) es una confirmación no-op: RLS
-- ya está activa y los índices ya existen. A partir de aquí, los procesadores NO
-- lo recrean: solo COMPRUEBAN que la RLS está activa (y abortan pidiendo esta
-- migración si no) — nunca cargan en una tabla abierta a anon.
--
-- 🔒 Sobre una base ya curada (patrón estrangulador: los datos se CURAN, no se
--    migran). `ALTER TABLE IF EXISTS` + `CREATE INDEX IF NOT EXISTS` +
--    `ADD COLUMN IF NOT EXISTS`: aplicarla dos veces no cambia nada.
-- 🔒 Aplicar por la escalera con lock_timeout corto (DDL con lock exclusivo:
--    falla rápido, no encola), como #63. Advisors después.
--
-- NO incluye:
--   · moloka_ean_norm() (keepa lo recrea al arrancar): es una FUNCIÓN, no bloquea
--     tablas, no fue el lock del 15:47 — su migración va en OTRO PR (así acordado).
--   · El índice idempotente del histórico dinámico de foto_comun (`<tabla>_hist`):
--     su RLS es de creación-única (no per-load) y su índice es ShareLock sobre el
--     histórico (no bloquea al sondeo); el nombre es dinámico y no se pre-migra.
-- ============================================================================

-- ── TABLAS-FOTO / PELÍCULA VIVAS (las que lee el sondeo) ─────────────────────

-- listings_amazon (procesador_all_listings.py)
ALTER TABLE IF EXISTS listings_amazon ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS listings_amazon
    ADD COLUMN IF NOT EXISTS procesado_en timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_listings_amazon_asin ON listings_amazon(asin);

-- inventario_internacional (procesador_internacional.py)
ALTER TABLE IF EXISTS inventario_internacional ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_inventario_internacional_asin    ON inventario_internacional(asin);
CREATE INDEX IF NOT EXISTS idx_inventario_internacional_country ON inventario_internacional(country);

-- keepa_escaparate (procesador_keepa_escaparate.py)
ALTER TABLE IF EXISTS keepa_escaparate ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_asin    ON keepa_escaparate(asin);
CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_dominio ON keepa_escaparate(dominio);

-- ledger_movimientos (procesador_ledger.py)
ALTER TABLE IF EXISTS ledger_movimientos ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_ledger_fecha        ON ledger_movimientos(fecha);
CREATE INDEX IF NOT EXISTS idx_ledger_event_type   ON ledger_movimientos(event_type);
CREATE INDEX IF NOT EXISTS idx_ledger_reference_id ON ledger_movimientos(reference_id);
CREATE INDEX IF NOT EXISTS idx_ledger_asin         ON ledger_movimientos(asin);
CREATE INDEX IF NOT EXISTS idx_ledger_country      ON ledger_movimientos(country);

-- paneu_aptos + paneu_oferta_pais (procesador_paneu_aptos.py)
ALTER TABLE IF EXISTS paneu_aptos       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS paneu_oferta_pais ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_paneu_aptos_asin         ON paneu_aptos(asin);
CREATE INDEX IF NOT EXISTS idx_paneu_oferta_pais_pais   ON paneu_oferta_pais(pais);
CREATE INDEX IF NOT EXISTS idx_paneu_oferta_pais_sku    ON paneu_oferta_pais(seller_sku);

-- salud_fba (procesador_salud_fba.py)
ALTER TABLE IF EXISTS salud_fba ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_salud_fba_asin ON salud_fba(asin);
CREATE INDEX IF NOT EXISTS idx_salud_fba_sku  ON salud_fba(sku);

-- transacciones_movimientos (procesador_transacciones.py)
ALTER TABLE IF EXISTS transacciones_movimientos ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_trans_pais_fecha ON transacciones_movimientos(pais, fecha);
CREATE INDEX IF NOT EXISTS idx_trans_fecha      ON transacciones_movimientos(fecha);
CREATE INDEX IF NOT EXISTS idx_trans_tipo       ON transacciones_movimientos(tipo);
CREATE INDEX IF NOT EXISTS idx_trans_sku        ON transacciones_movimientos(sku);
CREATE INDEX IF NOT EXISTS idx_trans_pedido     ON transacciones_movimientos(numero_pedido);

-- ── HISTÓRICOS de nombre estático (internacional y salud_fba llevan el suyo) ──
-- (all_listings y keepa archivan por foto_comun.archivar_foto → `<tabla>_hist`,
--  cuya RLS es de creación-única; ésos no se tocan aquí.)

-- inventario_internacional_historico (procesador_internacional.py)
ALTER TABLE IF EXISTS inventario_internacional_historico ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_inv_intl_hist_fecha ON inventario_internacional_historico(fecha_foto);
CREATE INDEX IF NOT EXISTS idx_inv_intl_hist_asin  ON inventario_internacional_historico(asin);

-- salud_fba_historico (procesador_salud_fba.py)
ALTER TABLE IF EXISTS salud_fba_historico ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_salud_fba_hist_snapshot ON salud_fba_historico(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_salud_fba_hist_asin     ON salud_fba_historico(asin, snapshot_date);
