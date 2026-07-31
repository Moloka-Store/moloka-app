-- ============================================================================
-- MIGRACIÓN 2026-07-31 · frescura_informes() aprende el informe 'custom_analytics'
-- ----------------------------------------------------------------------------
-- QUÉ HACE. Añade UN bloque `union all` a frescura_informes() para que la tarjeta
-- de Custom Analytics (demanda) deje de salir gris. Pasa de 7 informes a 8.
--
--   · fecha_dato   = max(periodo_hasta) de demanda_asin  ← la FECHA DEL DATO es el
--     fin de la ventana, NO procesado_at (§9.5). Una demanda "hasta el 27-jul" no
--     es fresca porque se procesara hoy: es fresca hasta el 27-jul.
--   · subido_buzon = max(updated_at) de storage.objects en informes/custom_analytics/
--   · procesado    = max(procesado_at) de demanda_asin
--
-- 🔒 CÓPIA VERBATIM del cuerpo actual (pg_get_functiondef, medido el 31-jul) + el
--    bloque nuevo. NO se reescribe de memoria. Se conserva:
--      · SECURITY DEFINER  (para poder leer demanda_asin —cerrada por RLS— y
--        storage.objects; la RPC la llama el rol `authenticated`, que no tiene
--        acceso directo a esas tablas: por eso es DEFINER),
--      · SET search_path = 'public','storage',
--      · el EXECUTE revocado a anon (medido antes: proacl = postgres/authenticated/
--        service_role; anon fuera).
--
-- 🔒 CREATE OR REPLACE conserva el ACL (§4): anon sigue sin EXECUTE tras esto. Aun
--    así se REVOCA explícito al final —idempotente— para que la intención quede
--    escrita y sobreviva a un futuro DROP+CREATE (donde el ACL se PIERDE, §4).
--
-- 🔒 frescura_informes_sondeo() NO se toca: su cuerpo es
--    `select * from public.frescura_informes();` y hereda el bloque nuevo solo.
--
-- 🔒 IDEMPOTENTE (CREATE OR REPLACE + REVOKE). Escalera: staging → SQL → prod → SQL.
--    Advisors después.
-- 🔴 ORDEN (§9.4, abrazo mortal): esta RPC se aplica DESPUÉS de que la v2 esté
--    desplegada con la ficha marcada `pendienteRpc: true` (PR 3). Si se aplica antes,
--    el guardián 2 de query.ts vería la clave 'custom_analytics' que el catálogo aún
--    no conoce y tumbaría la pantalla de Buzones de Elena. Con la v2 ya desplegada
--    con el flag, aplicar esto es seguro; luego PR 5 quita el flag.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.frescura_informes()
 RETURNS TABLE(informe text, fecha_dato date, subido_buzon timestamp with time zone, procesado_tabla timestamp with time zone)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public', 'storage'
AS $function$
  select 'salud_fba'::text, (select max(snapshot_date) from salud_fba),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'salud_fba/%'),
    (select max(procesado_en) from salud_fba)
  union all select 'internacional', (select max(fecha_foto) from inventario_internacional),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'internacional/%'),
    (select max(procesado_at) from inventario_internacional)
  union all select 'keepa_escaparate', (select max(fecha_foto) from keepa_escaparate),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'keepa_escaparate/%'),
    (select max(procesado_at) from keepa_escaparate)
  union all select 'all_listings', (select max(fecha_informe)::date from listings_amazon),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'all_listings/%'),
    (select max(procesado_en) from listings_amazon)
  union all select 'ledger', (select max(fecha) from ledger_movimientos),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'ledger/%'),
    (select max(procesado_at) from ledger_movimientos)
  union all select 'paneu_aptos', (select max(snapshot_date) from paneu_aptos),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'paneu_aptos/%'),
    (select max(procesado_en) from paneu_aptos)
  union all select 'transacciones', (select max(fecha_dato_hasta) from informes_subidos where tipo='transacciones'),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'transacciones/%'),
    (select max(procesado_at) from informes_subidos where tipo='transacciones')
  union all select 'custom_analytics', (select max(periodo_hasta) from demanda_asin),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'custom_analytics/%'),
    (select max(procesado_at) from demanda_asin);
$function$;

-- Intención escrita: la frescura NO la puede pedir un anónimo (§4). No-op hoy
-- (CREATE OR REPLACE conservó el ACL sin anon), pero sobrevive a un DROP+CREATE.
REVOKE EXECUTE ON FUNCTION public.frescura_informes() FROM PUBLIC, anon;

-- ── MEDIR (§4): tras aplicar, comprobar que sigue cerrada a anon y que hay 8 filas:
--   select proname, prosecdef, array_to_string(proacl,' | ') from pg_proc
--    where proname='frescura_informes' and pronamespace='public'::regnamespace;
--   select * from frescura_informes() where informe='custom_analytics';
