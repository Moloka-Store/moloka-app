-- ============================================================================
-- MIGRACIÓN 2026-09-02 · medida_base — la serie diaria del tamaño de la base
-- ----------------------------------------------------------------------------
-- QUÉ ES Y POR QUÉ. Encargo "que la base deje de crecer sin techo" (§4, PR A). Moloka
--   sigue en el plan gratuito de Supabase (500 MB de base, 1 GB de Storage — DOS
--   cajones distintos). Hasta hoy el tamaño de la base se conocía por una medición
--   suelta cuando alguien la pedía (la del 2-sep: 252 MB de 500, con
--   transacciones_movimientos a 58 MB en disco y ledger_movimientos a 29 MB). Sin
--   una serie, cualquier decisión sobre qué recortar se toma con una foto de un
--   día, no con una tendencia. Esta tabla es esa serie: una fila por día, escrita
--   al final de backup-bd.yml (PR A, mismo encargo), NUNCA por un procesador de
--   negocio ni por el conector de Supabase.
--
-- 🔒 EL CAJÓN: FOTO POR DÍA (una fila por `fecha`, PK). Recargar el mismo día lo
--   recierra (ON CONFLICT (fecha) DO UPDATE, en el paso de backup-bd.yml); días
--   distintos conviven → esta tabla ES la serie, no hay _hist.
--
-- 🔒 `tablas` guarda SOLO las 12 tablas más grandes de `public` en el momento de la
--   medición (nombre, disco_bytes, vivo_bytes, filas, dead_tup), no el catálogo
--   entero: es una foto de dónde está el peso, no un censo de esquema (eso ya lo
--   contesta censo_migraciones.py).
-- 🔴 `vivo_bytes` (sum(pg_column_size(t.*)) por tabla) es un barrido COMPLETO de
--   cada una de esas 12 tablas, no una consulta de catálogo: a los ~250 MB de hoy
--   sale barato. Si la base pasa de 1 GB, el paso de backup-bd.yml que llena esta
--   columna hay que sustituirlo por algo que no recorra la tabla entera (o
--   dejarla NULL y quedarse solo con `disco_bytes`, que sí sale del catálogo).
--
-- 🔒 SEGURIDAD (§4 de CLAUDE.md) — "nace cerrado" NO es el estado por defecto: toda
--   tabla nueva en `public` nace con arwdDxtm concedido a anon Y authenticated
--   (default privileges de Supabase). Se REVOCA a cada rol por su nombre y se
--   concede solo SELECT a authenticated (esta tabla no tiene datos de Elena ni de
--   ningún cliente: es telemetría de infraestructura, pero tampoco hace falta
--   abrirla a anon). Nadie escribe por RLS/política: el único escritor es el paso
--   de backup-bd.yml, que se conecta con SUPABASE_DB_URL (owner de la base, no le
--   afecta el revoke).
--
-- 🔒 IDEMPOTENTE. CREATE TABLE IF NOT EXISTS, REVOKE (repetirlo no cambia nada).
--   Aplicarla dos veces = no-op.
-- 🔒 Escalera: staging (apply) → verificación SQL → producción (apply) → SQL.
--   Elena no se entera de esto (tabla nueva, sin tráfico de la app).
-- ============================================================================

CREATE TABLE IF NOT EXISTS medida_base (
    fecha              date PRIMARY KEY,
    base_bytes         bigint NOT NULL,
    storage_bytes      bigint,
    storage_por_bucket jsonb,
    tablas             jsonb NOT NULL,
    creado_en          timestamptz NOT NULL DEFAULT now()
);

-- ── SEGURIDAD: REVOCAR antes de conceder (§4). Solo SELECT para authenticated. ──
REVOKE ALL ON medida_base FROM PUBLIC, anon, authenticated;
GRANT SELECT ON medida_base TO authenticated;

-- ── MEDIR EL RESULTADO (§4: no suponer el ACL, medirlo). Tras aplicar, correr:
--   select relname, relrowsecurity,
--          coalesce(array_to_string(relacl,' | '),'(sin acl explícito)') acl
--     from pg_class where oid = 'public.medida_base'::regclass;
--   -- se espera relacl SIN anon y con authenticated=r (SELECT) solamente.
