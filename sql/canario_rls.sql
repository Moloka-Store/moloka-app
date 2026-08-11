-- ============================================================================
-- CANARIO RLS · distinguir «0 filas porque no hay datos» de «0 filas porque la RLS
--               las está tapando»
-- ----------------------------------------------------------------------------
-- PARA QUÉ. Una tabla con RLS ACTIVA y CERO POLÍTICAS es invisible para la app, y no
-- avisa: no da error, da vacío. Y una vista que la lea con `security_invoker` devuelve 0
-- filas con la misma cara de normalidad. Es el fallo más silencioso que hay en esta base:
-- todo funciona, nada peta, y la pantalla dice que no hay nada.
--
-- 🔬 Medido el 11-ago-2026 en producción, con recuento REAL (no `reltuples`): **21 tablas**
--    están así, y **20 de ellas tienen datos dentro** — sólo una está vacía. Son
--    **13.781 filas invisibles**. Las gordas:
--      keepa_escaparate_hist 3.784 · paneu_oferta_pais 3.720 ·
--      inventario_internacional_historico 1.891 · listings_amazon_hist 1.683 ·
--      bb_observaciones 623 · paneu_aptos 372 · monitor_analisis 284 …
--
-- 🔑 LA CLAVE DEL CANARIO, y por eso no hace falta ejecutar como `authenticated`:
--    **RLS activa + cero políticas ⟹ invisible, POR DEFINICIÓN.** Postgres no necesita
--    consultarse: si no hay ninguna política que permita, no permite. Lo único que hay
--    que medir de verdad es CUÁNTAS FILAS HAY DENTRO, porque eso es lo que separa
--    «vacía» (inofensivo) de «tapada» (13.600 filas que nadie ve).
--
-- ⚠️ POR QUÉ NO SE PUEDE MEDIR CON EL CONECTOR A SECAS. El conector corre como `postgres`,
--    que tiene BYPASSRLS: cuenta todo y no se entera de nada. Ésa es justamente la trampa
--    que hizo falta esquivar al pasar `v_presencia_pais` a invoker — el conector decía
--    508 filas mientras la app habría visto 0. Aquí se esquiva contando las filas reales
--    (con el privilegio que haga falta) y DEDUCIENDO la visibilidad del catálogo, en vez
--    de preguntarle a un rol que no representa a la app.
--
-- CUÁNDO SE CORRE:
--   · **Después de CADA restauración** (es donde más duele: una política que no vuelve
--     deja la tabla tapada y nadie se entera hasta que falta un dato en pantalla).
--   · Antes de pasar cualquier vista a `security_invoker`: si su tabla base sale aquí,
--     la vista se quedará a cero.
--   · Cuando una pantalla enseñe vacío y no se sepa por qué. Empieza por aquí.
--
-- 🔒 NO CREA NADA. Es solo lectura y no deja objetos en la base: se pega y se lee.
--    Tampoco propone arreglos — decir qué tabla debe abrirse y a quién es una decisión de
--    negocio, y el frente de `monitor_*` y `productos` frente a `anon` está CONGELADO por
--    decisión de Fernando hasta jubilar la v1. Este guion informa; no toca.
-- ============================================================================

-- `query_to_xml` permite contar filas de tablas nombradas dinámicamente dentro de un
-- SELECT normal, sin PL/pgSQL y sin crear funciones. El recuento es REAL (count(*)), no
-- la estimación de `reltuples` — que en tablas nunca analizadas vale −1 y engañaría.
with tablas as (
  select c.oid, c.relname,
         c.relrowsecurity                                   as rls_activa,
         (select count(*) from pg_policies p
           where p.schemaname = 'public' and p.tablename = c.relname) as politicas
  from pg_class c
  where c.relnamespace = 'public'::regnamespace
    and c.relkind = 'r'
),
contadas as (
  select t.*,
         (xpath('/row/c/text()',
                query_to_xml(format('select count(*) as c from public.%I', t.relname),
                             false, true, '')))[1]::text::bigint as filas
  from tablas t
  where t.rls_activa            -- solo las que tienen RLS: las demás no pueden tapar nada
)
select
  relname                                            as tabla,
  filas,
  politicas,
  case
    when politicas > 0            then 'ok · tiene políticas'
    when filas = 0                then 'vacía · RLS sin políticas, pero no tapa nada'
    else                               '🔴 TAPADA · ' || filas || ' filas que la app NO ve'
  end                                                as veredicto
from contadas
order by (politicas = 0 and filas > 0) desc, filas desc;


-- ── RESUMEN, para pegarlo en el parte y comparar entre restauraciones ────────
with tablas as (
  select c.relname, c.relrowsecurity,
         (select count(*) from pg_policies p
           where p.schemaname = 'public' and p.tablename = c.relname) as politicas
  from pg_class c
  where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' and c.relrowsecurity
),
contadas as (
  select t.*, (xpath('/row/c/text()',
                query_to_xml(format('select count(*) as c from public.%I', t.relname),
                             false, true, '')))[1]::text::bigint as filas
  from tablas t
)
select
  count(*) filter (where politicas = 0)                     as tablas_sin_politicas,
  count(*) filter (where politicas = 0 and filas > 0)       as 🔴_tapadas_con_datos,
  coalesce(sum(filas) filter (where politicas = 0), 0)      as filas_invisibles,
  count(*) filter (where politicas > 0)                     as tablas_con_politicas,
  -- 🔒 Y las vistas DEFINER que quedan: cada una es una puerta que NO depende de la RLS
  --    de su tabla base. No son un fallo por sí mismas, pero conviene saber cuántas hay.
  (select count(*) from pg_class v
    where v.relnamespace = 'public'::regnamespace and v.relkind = 'v'
      and coalesce(v.reloptions::text, '') not like '%security_invoker=true%')
                                                            as vistas_definer
from contadas;
-- 🔬 Referencia del 11-ago-2026 en producción, para comparar:
--    21 tablas sin políticas · **20 TAPADAS con datos** (sólo 1 vacía) ·
--    **13.781 filas invisibles** · 39 tablas con políticas · 18 vistas definer.
--    🔒 Si tras un restore el número de TAPADAS sube, una política no ha vuelto.
