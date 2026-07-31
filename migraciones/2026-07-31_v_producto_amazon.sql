-- ============================================================================
-- MIGRACIÓN 2026-07-31 · v_producto_amazon — la fila CANÓNICA por ASIN del maestro
-- ----------------------------------------------------------------------------
-- EL BUG, MEDIDO (31-jul-2026, en PRODUCCIÓN). Cruzar por productos.asin DUPLICA
-- filas y devuelve DOS márgenes para el mismo producto: el Padrino B09HLD893M sale
-- a la vez con 15,64% y 16,81% al mismo precio, según qué fila coja el JOIN. Causa:
-- un mismo ASIN tiene varias filas en `productos` (la ficha principal y una o más
-- secundarias: consolidadas o descatalogadas), con `pvd` distinto.
--
-- Esta vista NO borra esas filas. `productos` es MAESTRO (CLAUDE.md §1.6): se MARCA,
-- no se borra — cada ficha secundaria tiene su compra con su factura (compras.
-- producto_id + factura_id) y borrarla dejaría la factura huérfana. La vista solo
-- ELIGE la fila buena, en un ÚNICO sitio canónico, para que ninguna consulta tenga
-- que acordarse de filtrar tres cosas a mano.
--
-- LOS TRES FILTROS (medidos contra el dato, no supuestos):
--   · es_chase = false        → fuera la capa CHASE (regla de Moloka, §1.1).
--   · estado <> 'CONSOLIDADO'  → fuera la ficha secundaria de una consolidación.
--   · activo = true            → 🔴 AÑADIDO respecto al borrador del encargo (§2).
--       Con SOLO los dos primeros filtros quedaban 2 ASINs duplicados (medido en
--       prod el 31-jul):
--         · B0DNRSF3J6 (Solo Leveling): OK/pvd 7,8317 y DESCATALOGADO/pvd 8,6217
--           conviven → EXACTAMENTE el mismo bug de doble margen que el Padrino, que
--           el borrador dejaba sin resolver.
--         · B089G8S9QZ (Funko Protector): OK y DESCATALOGADO (mismo pvd; dup igual).
--       `activo` es el campo que la casa YA usa para excluir fichas muertas (lo usan
--       v_keepa_cruce / v_salud_fba_cruce / v_canal_amazon_es con `p.activo`).
--       Añadirlo NO pierde a nadie: count(distinct asin) = 371 CON y SIN el filtro;
--       solo retira las filas-fantasma que causaban el duplicado. `activo` no tiene
--       NULLs en el maestro. El §2 del encargo lo pedía explícitamente: "si hay un
--       campo de actividad… que hoy se use para excluir fichas muertas, añádelo al
--       where — pero compruébalo antes con SQL, no lo asumas".
--
-- ACEPTACIÓN VERIFICADA EN PROD (read-only, ANTES del DDL):
--   §3.1 duplicados = 0
--   §3.2 esperados 371 = en_la_vista 371
--   §3.3 los 3 ASINs → pvd 8,0818 / 8,0380 / 7,9212 (las filas OK, no las de 8,3500).
--
-- pvd_sospechoso: MARCA el valor de relleno 8,3500 (misma familia que el 15,50% de
--   comisión de la doctrina 39: relleno que se cuela como si fuera medición). NO lo
--   corrige — solo lo señala, para que quien firme un margen ajustado sobre uno de
--   esos productos sepa que el coste puede no ser real. Ojo: hoy 8,3500 aparece en
--   37 filas del maestro, NO en 33 como decía el borrador (medido 31-jul; dato).
--
-- 🔒 security_invoker = true: la vista corre con los permisos de QUIEN la consulta,
--    así respeta el RLS de `productos`. Sin SECURITY DEFINER.
-- 🔒 NACE CERRADO (CLAUDE.md §4). Un objeto nuevo en `public` nace con `arwdDxtm`
--    concedido a anon Y a authenticated por los DEFAULT PRIVILEGES de Supabase
--    (medido 30-jul), y un `revoke … from public` NO los quita. Por eso se revoca a
--    CADA rol por su nombre ANTES de conceder, y luego el grant mínimo: SELECT solo
--    para authenticated. (Las vistas hermanas v_* siguen abiertas a anon — es la
--    deuda que el propio §4 describe; se cierra en su PR, no en éste: un PR, una cosa.)
--
-- DESPLIEGUE. Es CREATE OR REPLACE VIEW: pide AccessShareLock sobre `productos`, no
--   AccessExclusiveLock — no tumba nada. Aun así, por la escalera
--   (staging → SQL → prod → SQL), con lock_timeout corto en la sesión de prod, y
--   DETRÁS de la migración de Custom Analytics de la otra sesión: nunca a la vez, y
--   con Elena parada.
-- ============================================================================

create or replace view public.v_producto_amazon
with (security_invoker = true) as
select
  p.asin,
  p.ean,
  p.sku,
  p.nombre,
  p.pvd,
  p.iva_pct,
  p.comision_pct_keepa_es,
  p.comision_pct_it,
  p.comision_pct_fr,
  p.keepa_fba_fee_es,
  p.keepa_fba_fee_it,
  p.keepa_fba_fee_fr,
  p.estado,
  (p.pvd = 8.35) as pvd_sospechoso
from productos p
where p.asin is not null
  and coalesce(p.es_chase, false) = false
  and coalesce(p.estado, '') <> 'CONSOLIDADO'
  and p.activo;

-- Nace cerrado (§4): revocar los grants por defecto de Supabase a CADA rol por su
-- nombre y luego conceder el mínimo. Idempotente: se re-afirma en cada aplicación.
revoke all on public.v_producto_amazon from public, anon, authenticated;
grant select on public.v_producto_amazon to authenticated;
