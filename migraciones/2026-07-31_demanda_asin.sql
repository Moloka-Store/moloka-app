-- ============================================================================
-- MIGRACIÓN 2026-07-31 · demanda_asin — la cañería de la DEMANDA (Custom Analytics)
-- ----------------------------------------------------------------------------
-- QUÉ ES. La primera tabla del eje DEMANDA de la Fase 0. Hasta hoy el sistema sabe
--   qué stock hay (salud_fba/internacional), qué se vendió y a qué precio
--   (transacciones), pero NO sabe cuánta gente llegó (visitas/sesiones), qué hizo
--   (conversión) ni QUIÉN SE LLEVÓ LA CAJA (la buy box). Esto lo trae el export
--   "Custom Analytics" del Seller (Analytics → dimensión ASIN → un marketplace →
--   .xlsx), uno por país. La carga la hace procesador_custom_analytics.py.
--
-- 🔴 POR QUÉ ESTA MIGRACIÓN CREA LA TABLA Y NO EL PROCESADOR (huevo y gallina)
--   Desde el 29-jul (migración 2026-07-29_rls_indices_fuera_del_arranque.sql) los
--   procesadores YA NO activan RLS al arrancar: solo COMPRUEBAN que la tabla está
--   cerrada y ABORTAN si no lo está. En una tabla NUEVA eso gira en círculo: la
--   primera corrida crearía la tabla ABIERTA (CREATE TABLE) y abortaría acto seguido
--   por RLS ausente — y como aborta sin commit, ni la tabla queda. Por eso la tabla,
--   su RLS, sus índices y la vista nacen AQUÍ, por la escalera, una sola vez. El
--   procesador solo comprueba `relrowsecurity` (patrón de procesador_transacciones.py).
--
-- 🔴 EL CAJÓN: FOTO POR VENTANA (ni FOTO ni PELÍCULA)
--   Este informe no dice "cómo está esto AHORA" (eso sería FOTO, que tira la hoja
--   vieja). Dice "del día X al día Y pasó esto". Como FOTO, cada carga borraría la
--   anterior y nunca habría serie. Como PELÍCULA (append), recargar la MISMA ventana
--   duplicaría. La solución: la carga borra e inserta SOLO su ventana exacta, por
--   IGUALDAD de (pais, periodo_desde, periodo_hasta) — nunca BETWEEN:
--     · recargar la misma ventana la recierra (idempotente),
--     · ventanas distintas del mismo país CONVIVEN → la tabla ES el histórico, sin _hist.
--   El periodo NO viene en el fichero (ni dentro, ni en el nombre, ni deducible): lo
--   declara quien sube (inputs periodo_desde/periodo_hasta del workflow). Por eso son
--   columnas de primera clase, como el `pais` (que tampoco viene en el fichero: se
--   identifica cruzando con transacciones — la guarda §6.6 del encargo).
--
-- 🔒 crudo NOT NULL — la despensa. Las columnas del export CAMBIAN según lo que
--   Fernando marque en el panel (medido: 8 columnas el 28-jul, 18 el 30-jul). El día
--   que aparezca una métrica nueva, un ALTER TABLE + un relleno desde `crudo` la
--   recupera TAMBIÉN en las cargas viejas. Aquí la despensa vale más que en ningún
--   otro informe.
--
-- 🔒 SEGURIDAD (§4 de CLAUDE.md) — "nace cerrado" NO es el estado por defecto.
--   Toda tabla/vista nueva en `public` nace en Supabase con arwdDxtm concedido a
--   anon Y authenticated (default privileges). RLS on + 0 políticas YA bloquea a esos
--   roles, pero la regla de la casa es belt-and-suspenders: REVOCAR a cada rol por su
--   nombre y solo entonces conceder lo mínimo. Aquí no se concede NADA a anon/auth:
--   · el procesador escribe por DB_URL (conexión postgres = owner, no le afecta el revoke),
--   · la frescura la lee una RPC SECURITY DEFINER (PR 4), que también bypassa RLS,
--   · ninguna pantalla lee esta tabla/vista todavía. Cuando una la necesite, ESE PR
--     concede SELECT a authenticated Y añade la política RLS (hoy sería 0 filas).
--   ⚠️ NOTA para Fernando: las tablas Fase 0 que ya están en prod (transacciones_
--     movimientos, salud_fba) tienen anon/authenticated=arwdDxtm — NO llevan este
--     revoke, van con RLS-only. Medido el 31-jul. demanda_asin queda MÁS cerrada que
--     ellas (la dirección que pide §4); es una divergencia consciente, no un descuido.
--
-- 🔒 IDEMPOTENTE. CREATE TABLE/INDEX IF NOT EXISTS, CREATE OR REPLACE VIEW, REVOKE
--   (repetirlo no cambia nada), COMMENT (idem). Aplicarla dos veces = no-op.
-- 🔒 lock_timeout corto (criterio DDL de la casa). Aquí es precaución pura: la tabla
--   es NUEVA, nadie la referencia, ni ENABLE RLS ni CREATE VIEW encuentran con quién
--   competir por el lock. Aun así se aplica el criterio.
-- 🔒 Escalera: staging (apply) → verificación SQL → producción (apply) → SQL.
--   Advisors después. Elena parada al aplicar en prod (aunque el riesgo real es nulo).
-- ============================================================================

SET LOCAL lock_timeout = '5s';

-- ── LA TABLA ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS demanda_asin (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pais                   text    NOT NULL,        -- del SELECTOR del workflow, JAMÁS del fichero
    periodo_desde          date    NOT NULL,        -- del SELECTOR (el fichero no lo trae)
    periodo_hasta          date    NOT NULL,        -- del SELECTOR
    dias                   integer GENERATED ALWAYS AS ((periodo_hasta - periodo_desde) + 1) STORED,
    asin                   text    NOT NULL,
    nombre_producto        text,
    resenas                integer,
    estrellas              numeric,
    visitas                integer,
    sesiones               integer,
    conversion             numeric,   -- RATIO 0-1 (uds_pedidas/visitas). La cabecera dice (%) y miente.
    unidades_pedidas       integer,
    unidades_enviadas      integer,
    precio_venta_medio     numeric,
    ventas_enviadas_eur    numeric,
    facturacion_pedida_eur numeric,
    buybox_ratio           numeric,   -- RATIO 0-1 (visiones_bb/visitas). LA BUY BOX.
    buybox_visiones        integer,
    reembolsado_eur        numeric,
    unidades_reembolsadas  integer,
    reembolsos_ratio       numeric,   -- RATIO 0-1
    inventario_disponible  integer,   -- 🔴 NO ES STOCK. Despensa, la vista NO lo expone.
    fichero                text,
    exportado_at           timestamptz,   -- properties.created del .xlsx (cuándo se exportó)
    crudo                  jsonb   NOT NULL,
    procesado_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT demanda_asin_ventana_ok CHECK (periodo_desde <= periodo_hasta),
    CONSTRAINT demanda_asin_unica UNIQUE (pais, periodo_desde, periodo_hasta, asin)
);

-- ── ÍNDICES ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_demanda_asin_asin    ON demanda_asin(asin);
CREATE INDEX IF NOT EXISTS idx_demanda_asin_ventana ON demanda_asin(pais, periodo_hasta DESC);

-- ── RLS: nace CERRADA (activa, cero políticas) ──────────────────────────────
ALTER TABLE demanda_asin ENABLE ROW LEVEL SECURITY;

-- ── LA VISTA: la ventana más reciente por (pais, asin) ──────────────────────
-- A igualdad de fin, la más CORTA (más específica); a igualdad de todo, la última
-- procesada. `dias` viaja en la vista: una cifra de "visitas" sin la ventana que la
-- sostiene miente. inventario_disponible NO sale, a propósito (no es stock).
CREATE OR REPLACE VIEW v_demanda_asin_ultima
WITH (security_invoker = true) AS
SELECT DISTINCT ON (pais, asin)
       pais, asin, periodo_desde, periodo_hasta, dias, nombre_producto,
       visitas, sesiones, conversion, unidades_pedidas, unidades_enviadas,
       precio_venta_medio, ventas_enviadas_eur, facturacion_pedida_eur,
       buybox_ratio, buybox_visiones, reembolsos_ratio, resenas, estrellas,
       exportado_at, procesado_at
FROM   demanda_asin
ORDER  BY pais, asin, periodo_hasta DESC, dias ASC, procesado_at DESC;

-- ── COMMENTS: donde se equivoca uno por un factor de 100 (los ratios) y donde
--    alguien "aprovecharía" dentro de tres meses un dato que no es lo que parece.
COMMENT ON TABLE demanda_asin IS
  'DEMANDA por ASIN del export Custom Analytics del Seller (Fase 0). FOTO POR VENTANA: '
  'una carga borra e inserta SOLO su (pais, periodo_desde, periodo_hasta) por IGUALDAD; '
  'ventanas distintas conviven → esta tabla ES el histórico, no hay _hist. pais y periodo '
  'los declara el selector del workflow: el fichero no los trae.';
COMMENT ON COLUMN demanda_asin.conversion IS
  'RATIO 0-1 (unidades_pedidas/visitas). Se guarda TAL CUAL: la cabecera de Amazon dice '
  '"Tasa de conversión (%)" pero el valor viene 0-1, NO en porcentaje. Multiplicar por 100 '
  'es cosa de quien lo pinta, no del cargador.';
COMMENT ON COLUMN demanda_asin.buybox_ratio IS
  'LA BUY BOX. RATIO 0-1 (visiones de ofertas destacadas/visitas). "Ratio de oferta '
  'destacada" en el fichero. Se guarda tal cual (0-1). La buy box se MIDE aquí, se trabaja '
  'en el trackeador (otro proyecto).';
COMMENT ON COLUMN demanda_asin.reembolsos_ratio IS
  'RATIO 0-1. La cabecera dice "Ratio de reembolsos (%)" pero viene 0-1. Se guarda tal cual.';
COMMENT ON COLUMN demanda_asin.inventario_disponible IS
  '🔴 NO ES STOCK. "Unidades de inventario disponibles" de Custom Analytics es el peor de '
  'los tres informes para stock (§6.12 del encargo). La fuente única del stock es salud_fba '
  '(available + fc_transfer). Se guarda como despensa; la vista v_demanda_asin_ultima NO lo '
  'expone. No usarlo como stock.';
COMMENT ON COLUMN demanda_asin.dias IS
  'Longitud de la ventana en días, calculada (periodo_hasta - periodo_desde + 1). La cifra '
  'de demanda solo se lee junto a la ventana que la sostiene.';
COMMENT ON COLUMN demanda_asin.crudo IS
  'La fila entera del fichero (cabecera→valor). Despensa: las columnas del export cambian '
  'según el panel; una métrica nueva se recupera con ALTER TABLE + relleno desde aquí, '
  'también en cargas viejas.';

-- ── SEGURIDAD: REVOCAR antes de conceder (§4). No se concede nada a anon/auth. ──
REVOKE ALL ON demanda_asin        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON v_demanda_asin_ultima FROM PUBLIC, anon, authenticated;

-- ── MEDIR EL RESULTADO (§4: no suponer el ACL, medirlo). Tras aplicar, correr:
--   select relname, relrowsecurity,
--          coalesce(array_to_string(relacl,' | '),'(sin acl explícito)') acl
--     from pg_class
--    where oid in ('public.demanda_asin'::regclass, 'public.v_demanda_asin_ultima'::regclass);
--   select count(*) from pg_policies where schemaname='public' and tablename='demanda_asin';  -- 0
