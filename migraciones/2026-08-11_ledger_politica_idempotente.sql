-- ============================================================================
-- MIGRACIÓN 2026-08-11 · la política de lectura del ledger, IDEMPOTENTE
--   ·  Condición (1) de Fernando para pasar `v_presencia_pais` a security_invoker
-- ----------------------------------------------------------------------------
-- PARA QUÉ, y por qué es condición y no un extra.
--
-- `v_presencia_pais` pasa a `security_invoker` en la migración hermana
-- (`2026-08-11_v_keepa_bb_envio.sql`). Con eso, la vista deja de saltarse la RLS — que es
-- lo que se busca — pero **empieza a depender de que exista la política de lectura de
-- `ledger_movimientos`**. Si esa política no está, la vista devuelve 0 filas y el Cockpit
-- pierde la presencia por país **en silencio**: no da error, da vacío.
--
-- 🔬 Y no es hipotético: se midió el 11-ago-2026 en el ensayo. Staging, recién restaurado
--    del backup de anoche, **NO tenía esa política** — se creó después del backup. Con
--    invoker, la vista daba **0 filas** allí y **508** en producción. El mismo código, dos
--    resultados, y ninguno de los dos avisa.
--
-- 🔑 POR ESO ESTA MIGRACIÓN EXISTE: para que la política sea **reaplicable**. Hasta ahora
--    vivía sólo en el estado de la base; si un restore la deja fuera, no había un fichero
--    que volver a pasar. Ahora sí: se ejecuta este .sql y la política vuelve, esté o no.
--
-- 🔒 IDEMPOTENTE de verdad, no «suele funcionar»: `drop policy if exists` + `create`. Se
--    hace así y no con un `if not exists` a secas para que, si alguien la ha modificado a
--    mano, quede EXACTAMENTE la que dice este fichero. Una política con el mismo nombre y
--    otro `using` sería peor que no tenerla: parecería que está bien.
--
-- ⚠️ LO QUE ESTA MIGRACIÓN NO HACE, y conviene que se lea: NO abre el ledger a nadie
--    nuevo. Reproduce la política que YA está en producción, tal cual —lectura para
--    `authenticated` con sesión—, para poder volver a ponerla. `anon` sigue fuera, y el
--    ledger sigue cerrado.
--
-- 📌 CONTEXTO QUE HAY QUE MIRAR AL APLICAR ESTO: el ledger es sólo una de **21 tablas con
--    RLS activa y CERO políticas** en producción (medido el 11-ago), de las cuales **20
--    tienen datos dentro: 13.781 filas invisibles para la app**. Este fichero arregla la
--    reaplicabilidad de UNA. Para ver el estado de las 21 —y distinguir «vacía» de
--    «tapada»— está `sql/canario_rls.sql`, que se corre después de cada restauración.
--    🔒 Decidir cuáles de esas 21 deben abrirse, y a quién, NO es materia de esta
--       migración: el frente de `monitor_*` y `productos` frente a `anon` está CONGELADO
--       por decisión de Fernando hasta jubilar la v1.
--
-- CIFRAS DE CONTROL:
--   · Antes en producción: `ledger_movimientos` con RLS activa y 1 política.
--   · Después: la misma, 1 política, con idéntico `qual`.
--   · 🔬 Como la app (`set role authenticated` + claims con `sub`): 18.461 filas.
--   🔒 Si tras aplicar salen 0 filas, la política no ha quedado bien y `v_presencia_pais`
--      estará vacía: NO seguir.
-- ============================================================================

set local lock_timeout = '3s';

-- La RLS ya está activa; se re-afirma por si se aplica sobre una base restaurada donde
-- el estado no sea el esperado. `enable` sobre una tabla que ya la tiene no hace nada.
alter table public.ledger_movimientos enable row level security;

drop policy if exists inventario_read_authenticated on public.ledger_movimientos;

create policy inventario_read_authenticated
  on public.ledger_movimientos
  for select
  to authenticated
  using (auth.uid() is not null);

comment on table public.ledger_movimientos is
  'Película (append-only) de movimientos. RLS activa: lectura sólo para authenticated con '
  'sesión (política inventario_read_authenticated, reaplicable desde '
  'migraciones/2026-08-11_ledger_politica_idempotente.sql). anon NO entra. '
  'v_presencia_pais depende de esta política desde que pasó a security_invoker: si '
  'desaparece, esa vista se queda a 0 filas SIN dar error.';


-- ── VERIFICACIÓN, a mano y COMO LA APP (el conector se salta la RLS) ─────────
--   begin;
--   set local role authenticated;
--   set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
--   select count(*) from public.ledger_movimientos;   -- 18.461 el 11-ago-2026
--   select count(*) from public.v_presencia_pais;     -- 508 el 11-ago-2026
--   rollback;
--
-- Y el estado de las 21:  \i sql/canario_rls.sql
