-- ============================================================================
-- MIGRACIÓN 2026-08-11 · GATE (3ª tanda) — quitar el residuo de `anon` en las
--   CATORCE vistas que aún tienen DML
-- ----------------------------------------------------------------------------
-- ORIGEN: Fernando detectó que `v_auditoria_tarifas` y `v_sondas_pendientes`
-- conservaban DELETE/INSERT/UPDATE/TRUNCATE para `anon` — residuo del gate
-- anterior, que les quitó el SELECT y dejó el resto.
--
-- 🔬 AL BARRER LA CLASE ENTERA EN VEZ DE ESAS DOS, SALIERON **14**, y una de
--    ellas NO es residuo inofensivo: es una puerta trasera VIVA.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- 🔴 `v_salud_fba_cruce` — la que sí muerde
-- ══════════════════════════════════════════════════════════════════════════════
-- Medido en producción el 11-ago-2026:
--   · `is_updatable = YES`  → su FROM es UNA sola tabla base (`salud_fba`); las
--     consultas escalares sobre `productos` van en la lista del SELECT y no
--     bloquean la auto-actualizabilidad.
--   · Sin `security_invoker` → corre como su dueño, `postgres`, que es también
--     el dueño de `salud_fba`. Un dueño IGNORA la RLS de su propia tabla.
--   · `anon = arwdDxtm` → completo, incluido DELETE y TRUNCATE.
--   · Y `salud_fba` tiene RLS con UNA política, `inventario_read_authenticated [r]`:
--     lectura para `authenticated` y NADA para `anon`. O sea que por la vía directa
--     está cerrada… y por la vista está abierta de par en par.
--
-- Sumado: un DELETE contra /rest/v1/v_salud_fba_cruce con la clave publicable
-- **borra `salud_fba`**. Es exactamente el mismo mecanismo que `v_analisis_auditable`
-- (gate del 11-ago), en otra tabla y sin que nadie lo hubiera visto.
--
-- Las otras 13 tienen `is_updatable = NO`, así que hoy no se puede escribir por
-- ellas. Se limpian igual: el grant es real y lo que hoy no muerde muerde el día
-- que alguien simplifique un JOIN.
--
-- ── LAS CATORCE, con lo que tiene `anon` hoy ────────────────────────────────
--   arwdDxtm (grant completo, nunca tocado):
--     v_canal_amazon_es · v_keepa_cruce · v_reglas_scoreboard ·
--     v_rentabilidad_transacciones · v_salud_fba_cruce 🔴 · v_suficiencia_decision ·
--     v_trackeador_scoreboard
--   awdDxtm (sin SELECT: residuo del gate anterior):
--     v_amazon_se_despierta · v_auditoria_tarifas · v_decisiones_estado ·
--     v_incidencias_movimientos · v_incidencias_resumen · v_incidencias_ultima ·
--     v_sondas_pendientes
--
-- QUIÉN LAS CONSUME (barrido de los dos repos, antes de tocar):
--   · v1 de Elena (`index.html`) y `api/`      → 0 menciones
--   · Cockpit v2 (`app/`, `lib/`)              → 0 menciones
--   · Trackeador (`moloka_tracker_*.py`)       → 0 menciones
--   → Nadie las lee. Por eso se revoca entero y no se reafirma nada para `anon`.
--   ⚠️ No cubre un Colab o un script fuera de los dos repos. No consta, pero la
--      ausencia no se demuestra.
--
-- 🔒 `authenticated` NO SE TOCA AQUÍ, a propósito. Las 14 tienen también
--    `authenticated=arwdDxtm`, que es el mismo residuo del DEFAULT ACL y merece
--    su propia limpieza — pero `authenticated` sí tiene consumidores potenciales
--    (la v2 con Auth) y mezclar las dos cosas en un PR es cómo se rompe una app
--    sin saber cuál de los dos cambios fue.
--
-- DESPLIEGUE: `REVOKE` es catálogo puro, instantáneo, sin reescritura. Reversible
--   con `grant all on <vista> to anon`. Escalera completa.
-- 🔒 La verificación va en PRODUCCIÓN, no en staging: el backup se vuelca con
--    `--no-privileges`, así que los ACL de staging no son los de prod (§4).
-- ============================================================================

set local lock_timeout = '3s';

revoke all on public.v_salud_fba_cruce          from anon, public;  -- 🔴 la viva
revoke all on public.v_canal_amazon_es          from anon, public;
revoke all on public.v_keepa_cruce              from anon, public;
revoke all on public.v_reglas_scoreboard        from anon, public;
revoke all on public.v_rentabilidad_transacciones from anon, public;
revoke all on public.v_suficiencia_decision     from anon, public;
revoke all on public.v_trackeador_scoreboard    from anon, public;
revoke all on public.v_amazon_se_despierta      from anon, public;
revoke all on public.v_auditoria_tarifas        from anon, public;
revoke all on public.v_decisiones_estado        from anon, public;
revoke all on public.v_incidencias_movimientos  from anon, public;
revoke all on public.v_incidencias_resumen      from anon, public;
revoke all on public.v_incidencias_ultima       from anon, public;
revoke all on public.v_sondas_pendientes        from anon, public;

-- ── VERIFICACIÓN (en PRODUCCIÓN, después de aplicar) ────────────────────────
-- Debe devolver CERO filas:
--
--   select c.relname,
--          has_table_privilege('anon', c.oid, 'SELECT')   as lee,
--          has_table_privilege('anon', c.oid, 'DELETE')   as borra,
--          has_table_privilege('anon', c.oid, 'TRUNCATE') as trunca
--   from pg_class c join pg_namespace n on n.oid = c.relnamespace
--   where n.nspname = 'public' and c.relkind = 'v'
--     and (has_table_privilege('anon', c.oid, 'SELECT')
--       or has_table_privilege('anon', c.oid, 'INSERT')
--       or has_table_privilege('anon', c.oid, 'UPDATE')
--       or has_table_privilege('anon', c.oid, 'DELETE')
--       or has_table_privilege('anon', c.oid, 'TRUNCATE'));
--
-- Y que la tabla que estaba expuesta siga entera:
--   select count(*) from public.salud_fba;   -- 223 el 11-ago-2026
