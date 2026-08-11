-- ============================================================================
-- MIGRACIÓN 2026-08-11 · QUE LAS TABLAS NUEVAS NAZCAN CERRADAS DE VERDAD
--   Revocar el DEFAULT ACL de `public` por ROL NOMBRADO  ·  Bloque D2 del encargo
--
-- 🔴 PROPUESTA. NO APLICADA. Es la más delicada de las dos: cambia cómo NACE
--    todo objeto futuro. Se revisa y se decide antes de ejecutar.
-- ----------------------------------------------------------------------------
-- LO MEDIDO en producción el 11-ago-2026 (`pg_default_acl`):
--
--   esquema  concedido_por   objeto        acl
--   public   postgres        tabla/vista   postgres=arwdDxtm | anon=arwdDxtm |
--                                          authenticated=arwdDxtm | service_role=arwdDxtm
--   public   postgres        función       postgres=X | anon=X | authenticated=X | service_role=X
--   public   postgres        secuencia     postgres=rwU | anon=rwU | authenticated=rwU | service_role=rwU
--   public   supabase_admin  tabla/vista   (el mismo juego, pero concedido por supabase_admin)
--
-- `arwdDxtm` = INSERT, SELECT, UPDATE, DELETE, **TRUNCATE**, REFERENCES, TRIGGER,
-- MAINTAIN. O sea: toda tabla y toda vista nueva nace con TRUNCATE para `anon`.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- POR QUÉ EL EVENT TRIGGER NO BASTA (y por qué esto no es duplicar su trabajo)
-- ══════════════════════════════════════════════════════════════════════════════
-- `ensure_rls` → `rls_auto_enable()` activa RLS al vuelo en las tablas nuevas. Es
-- una defensa buena, pero tiene TRES huecos medidos hoy:
--   1. Solo dispara con `CREATE TABLE` / `CREATE TABLE AS` / `SELECT INTO`.
--      **`CREATE VIEW` no está en su lista** — y una vista no tiene RLS propia.
--      Así nacieron abiertas `v_analisis_auditable` y `v_scoreboard_reglas`.
--   2. **TRUNCATE no está sujeto a RLS en ningún caso.** Activar RLS no protege
--      de un TRUNCATE; solo el ACL lo hace.
--   3. Es UNA capa, y no es la capa de permisos: basta una política permisiva
--      "para que funcione la app" y la tabla queda abierta desde el primer segundo.
-- 🔑 El trigger arregla la RLS. Esto arregla el PERMISO. Son cosas distintas.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- ⚠️ LOS TRES LÍMITES DE ESTA MIGRACIÓN — hay que saberlos antes de aplicarla
-- ══════════════════════════════════════════════════════════════════════════════
-- 1. **NO toca ni un objeto existente.** `ALTER DEFAULT PRIVILEGES` solo afecta a
--    lo que se cree DESPUÉS. Las 53 tablas que hoy tienen el grant a `anon` siguen
--    igual: ésas son el Bloque D3 y van tabla a tabla, en su propio PR.
--
-- 2. **Solo puede revocar el default de `postgres`, no el de `supabase_admin`.**
--    `ALTER DEFAULT PRIVILEGES` es por rol concedente, y esta migración corre como
--    `postgres`. Es el que importa —las migraciones y los procesadores crean como
--    `postgres`—, pero conviene saber que la fila de `supabase_admin` se queda.
--
-- 3. 🔴 **Un restore se lo lleva.** El backup se vuelca con `--no-privileges`, que
--    también deja fuera los DEFAULT PRIVILEGES. O sea: esto protege producción a
--    partir de mañana, pero el día del incendio la base vuelve con el default de
--    Supabase otra vez. Es el mismo frente abierto de CLAUDE.md §4 y **esta
--    migración no lo cierra**; solo deja de empeorarlo.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- 🔴 EL EFECTO SECUNDARIO QUE HAY QUE ACEPTAR A PROPÓSITO
-- ══════════════════════════════════════════════════════════════════════════════
-- Después de esto, **toda tabla nueva necesitará su `grant` explícito** o la app no
-- la verá. Eso es exactamente lo que se busca ("todo lo NUEVO nace CERRADO"), pero
-- es un cambio real de operativa y muerde en un sitio concreto:
--
--   🔬 Los procesadores crean tablas. `procesador_salud_fba.py:433` hace
--      `CREATE TABLE IF NOT EXISTS salud_fba_historico (...)`. Esas tablas nacerán
--      cerradas. Los procesadores escriben con `DB_URL` (rol `postgres`), así que
--      **seguirán funcionando**; lo que se rompería es la app leyéndolas con
--      `anon`/`authenticated` si alguien no pone el grant.
--
-- 🔑 Recomendación de despliegue: aplicar esto **el mismo día** que se revise la
--    lista de tablas que los procesadores crean, y añadir el `grant` que cada una
--    necesite en su propia migración. No aplicar y olvidarse.
--
-- DESPLIEGUE: cambio de catálogo, instantáneo. Reversible con el `grant` simétrico
--   (ver al final). Por la escalera completa, con Elena avisada.
-- ============================================================================

set local lock_timeout = '3s';

-- ── Tablas y vistas ─────────────────────────────────────────────────────────
alter default privileges in schema public
  revoke all on tables from anon, authenticated;

-- ── Secuencias ──────────────────────────────────────────────────────────────
alter default privileges in schema public
  revoke all on sequences from anon, authenticated;

-- ── Funciones ───────────────────────────────────────────────────────────────
-- 🔴 Ojo: esto quita el EXECUTE por defecto a `anon` en toda función nueva. Es lo
--    correcto ("funciones sin SECURITY DEFINER y sin anon"), pero si mañana nace
--    una RPC que la app deba poder llamar, su migración tendrá que conceder el
--    EXECUTE a mano. Hoy no hay ninguna función SECURITY DEFINER que escriba y sea
--    ejecutable por `anon`, así que no rompe nada vivo.
alter default privileges in schema public
  revoke all on functions from anon, authenticated;

-- ── Verificación (en PRODUCCIÓN, después de aplicar) ────────────────────────
-- Las filas de `defaclrole = postgres` en el esquema public NO deben mencionar ya
-- ni a `anon` ni a `authenticated`:
--
--   select pg_get_userbyid(d.defaclrole) as concedido_por,
--          d.defaclobjtype, array_to_string(d.defaclacl, ' | ') as acl
--   from pg_default_acl d
--   join pg_namespace n on n.oid = d.defaclnamespace
--   where n.nspname = 'public'
--   order by 1, 2;
--
-- Y la prueba de que hace lo que dice — crear una tabla de usar y tirar y mirar su
-- ACL (en STAGING, nunca en producción):
--   create table public._prueba_acl (id int);
--   select relacl from pg_class where relname = '_prueba_acl';   -- sin anon
--   drop table public._prueba_acl;
--
-- ── VUELTA ATRÁS ────────────────────────────────────────────────────────────
--   alter default privileges in schema public
--     grant all on tables to anon, authenticated;
--   alter default privileges in schema public
--     grant all on sequences to anon, authenticated;
--   alter default privileges in schema public
--     grant execute on functions to anon, authenticated;
