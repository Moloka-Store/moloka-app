-- ============================================================================
-- MIGRACIÓN 2026-08-11 · cerrar a `anon` las 9 vistas definer huérfanas
--   🔴 NO APLICADA: espera decisión de Fernando (ver «LO QUE HAY QUE DECIDIR»)
-- ----------------------------------------------------------------------------
-- QUÉ SON ESTAS NUEVE. Vistas `security definer` que leen una tabla con RLS activa y
-- CERO políticas, y que además están abiertas a `anon`. O sea: **la RLS de esas tablas no
-- protege nada**, porque sus datos salen sin sesión por una vista que se salta esa misma
-- RLS. Son las dos caras del mismo patrón — lo único que las hace funcionar es lo que las
-- abre.
--
--   v_amazon_se_despierta     → keepa_escaparate_hist
--   v_analisis_auditable      → monitor_analisis
--   v_auditoria_tarifas       → seller_observaciones
--   v_decisiones_estado       → monitor_analisis
--   v_incidencias_movimientos → incidencias_juguetes, incidencias_lecturas
--   v_incidencias_resumen     → incidencias_juguetes, incidencias_lecturas
--   v_incidencias_ultima      → incidencias_juguetes, incidencias_lecturas
--   v_scoreboard_reglas       → monitor_analisis
--   v_sondas_pendientes       → monitor_analisis
--
-- 🔒 `v_estado_asin` es la décima del censo pero **NO entra aquí**: ya está cerrada a
--    `anon`. Se la deja como está.
--
-- 🔑 POR QUÉ SE PUEDE CERRAR SIN ESPERAR A JUBILAR LA v1, que era la razón por la que
--    este frente estaba congelado. Porque **no las lee nadie**, y está medido por cuatro
--    vías independientes:
--      1. `index.html` (la v1): ninguna aparece. La v1 lee 17 tablas, con la clave
--         publishable, y ninguna de estas nueve está entre ellas.
--      2. Todo el Python del repo: ninguna. Es más — NINGUNA vista `v_*` aparece en
--         ningún script. Los procesadores leen las tablas base directamente.
--      3. `moloka-app-v2`: ninguna (sólo se menciona en un .md de documentación).
--      4. `pg_depend` en producción: ninguna es leída por otra vista. Son hojas.
--
-- ⚠️ Y LA QUINTA VÍA, que es la que hay que leer con cuidado porque NO da un cero limpio:
--    `pg_stat_statements`, con **105 días** de histórico (desde el 29-abr-2026), sí
--    registra consultas sobre nueve de las diez. Pero mirando el patrón:
--
--      · 29 lecturas de `v_sondas_pendientes` repartidas en **28 consultas distintas**.
--      · En 8 de las 9, **el máximo de llamadas de una misma consulta es 1**. El máximo
--        absoluto es **2**.
--      · Y el texto es `select * from …`, `… order by 1`, `… limit $1`.
--
--    🔑 Eso no es un consumidor: es exploración. Una aplicación repite LA MISMA consulta
--       miles de veces; aquí hay casi una llamada por consulta distinta, que es la huella
--       de alguien mirando la vista a mano. `v_decisiones_estado` no tiene ni una.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ✅ Y EL FILTRO QUE DISUELVE LA DUDA, que no es cuántas llamadas hubo sino CON QUÉ ROL.
--    Este revoke sólo toca `anon`: una consulta hecha con otro rol no se ve afectada, así
--    que da igual cuántas haya. `pg_stat_statements` guarda el `userid`, y cruzándolo con
--    `pg_roles` sobre esos 105 días:
--
--        postgres ................. 56 llamadas   ← el conector
--        supabase_read_only_user ...  3 llamadas   ← el panel de Supabase
--        authenticated .............  1 llamada
--        🔑 anon ...................  **0**
--
--    Ni una sola con `anon`. No hay juicio que hacer: el patrón de exploración de arriba
--    era la pista, pero esto es la prueba.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- 🕐 CUÁNDO APLICARLO. Por principio no se toca producción mientras Elena opera, aunque
--    aquí el riesgo sea nulo. 🔬 Su ventana real, medida sobre los movimientos de 30 días:
--    **de 10:00 a 20:00 peninsular**, y fuera de eso ni un movimiento en todo el mes.
--    → Aplicar **antes de las 10:00 o después de las 21:00**.
--    (El 11-ago a las 13:17 no se aplicó por esto: había un movimiento suyo de hacía 67
--     segundos.)
--
-- 👁️ VIGILANCIA 24 h tras aplicar: cualquier error nuevo en los logs que mencione una de
--    las diez → rollback inmediato (está al final) y contarlo.
--
-- 🔒 EL ROLLBACK, ESCRITO Y PROBADO **ANTES** DEL REVOKE (condición de Fernando). Se
--    ensayó el ciclo entero en staging dentro de una transacción deshecha:
--        inicial 9 vistas con anon → tras el revoke 0 → tras el grant de vuelta 9.
--    O sea: el revoke corta y el grant devuelve, comprobado, sin dejar rastro.
--    El SQL de vuelta está al final de este fichero, listo para copiar y pegar.
--
-- ⏳ ESTO ES UN EXPERIMENTO, NO UN FINAL. Si a **30 días** del revoke nadie ha reportado
--    nada, las nueve (y `v_estado_asin`) **se borran**. Una vista que no llama nadie no es
--    inocente: aparece en cada censo, confunde a quien audita y ya ha costado medio día de
--    trabajo. Pero el borrado va DESPUÉS de que el revoke demuestre que nadie las usa.
--    📌 Anotado en el README, sección «Las nueve vistas cerradas a anon».
--
-- 🔒 LO QUE ESTA MIGRACIÓN NO TOCA: ni una tabla, ni una política, ni la RLS de nada, ni
--    `productos` ni `monitor_*` frente a `anon`. Sólo quita un `grant` a nueve vistas.
-- ============================================================================

set local lock_timeout = '3s';

revoke select on
    public.v_amazon_se_despierta,
    public.v_analisis_auditable,
    public.v_auditoria_tarifas,
    public.v_decisiones_estado,
    public.v_incidencias_movimientos,
    public.v_incidencias_resumen,
    public.v_incidencias_ultima,
    public.v_scoreboard_reglas,
    public.v_sondas_pendientes
from anon;


-- ── VERIFICACIÓN tras aplicar (tiene que dar 0) ──────────────────────────────
--   select count(*) as siguen_abiertas_a_anon
--     from pg_class c
--    where c.relnamespace = 'public'::regnamespace and c.relkind = 'v'
--      and c.relname in ('v_amazon_se_despierta','v_analisis_auditable','v_auditoria_tarifas',
--          'v_decisiones_estado','v_incidencias_movimientos','v_incidencias_resumen',
--          'v_incidencias_ultima','v_scoreboard_reglas','v_sondas_pendientes')
--      and has_table_privilege('anon', 'public.'||c.relname, 'select');
--
-- 🔒 Y que `authenticated` NO se ha visto afectado (esta migración no le toca):
--   select count(*) from pg_class c
--    where c.relnamespace='public'::regnamespace and c.relkind='v'
--      and c.relname like 'v_%'
--      and has_table_privilege('authenticated','public.'||c.relname,'select');


-- ═════════════════════════════════════════════════════════════════════════════
-- ROLLBACK · probado en staging ANTES de aplicar el revoke (9 → 0 → 9)
-- Si algo deja de funcionar, se pega esto y vuelve al estado anterior.
-- ═════════════════════════════════════════════════════════════════════════════
--   grant select on
--       public.v_amazon_se_despierta,
--       public.v_analisis_auditable,
--       public.v_auditoria_tarifas,
--       public.v_decisiones_estado,
--       public.v_incidencias_movimientos,
--       public.v_incidencias_resumen,
--       public.v_incidencias_ultima,
--       public.v_scoreboard_reglas,
--       public.v_sondas_pendientes
--   to anon;
--
-- ⚠️ Y si el rollback hace falta, **eso ES el hallazgo**: significa que hay un consumidor
--    no versionado. Antes de volver a cerrarlas, hay que encontrarlo y anotarlo.
