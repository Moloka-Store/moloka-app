-- ============================================================================
-- MIGRACIÓN 2026-08-23 · EL RELEVO DEL BUZÓN: sale SALUD_FBA, entra INVENTARIO_FBA
-- ----------------------------------------------------------------------------
-- DECISIÓN DE FERNANDO, 23-ago-2026: **el informe «Estado del inventario FBA»
-- no se vuelve a descargar.** Lleva ocho días llegando roto desde Amazon y su
-- relevo ya está en producción. Esta migración cierra la puerta por el lado de
-- la base; el borrado de los ficheros del repo va en el mismo PR.
--
-- 🔒 LO QUE ESTA MIGRACIÓN **NO** TOCA, Y NO ES UN OLVIDO:
--
--   · **La VISTA `salud_fba` SE QUEDA.** Es el nombre que leen la app y sus
--     cuatro vistas dependientes. Lo que se jubila es el INFORME, no la palabra.
--     Renombrarla a algo honesto es otro trabajo y toca la app.
--   · **`salud_fba_historico` NO SE BORRA.** Dos motivos, los dos medidos:
--       1) lo lee `v_nunca_enviado_fba` (417 filas hoy). Sin él, esa vista cae.
--       2) son 1.984 filas y 9 fechas, y es la serie que permitió datar la
--          avería al día exacto: del 32 % de refs sin ventas al **83,7 % el
--          16-ago**, de golpe. El informe se jubila; su memoria se queda.
--   · **`salud_fba_amazon` tampoco se borra hoy.** 219 filas del 16-ago, ya no
--     la lee nadie salvo su procesador. Ocupa nada y es el único registro de lo
--     último que dijo Amazon. Se borra en otro PR si en una semana nadie la
--     echa de menos. Borrar datos es de lo poco que no tiene vuelta atrás.
--
-- QUÉ HACE, entonces, exactamente dos cosas:
--
--   1. `moloka_buzones_fase0()`: **fuera `salud_fba`, dentro `inventario_fba`.**
--      Esa función es la lista blanca de las políticas `buzones_v2_*` del
--      Storage. Al sacar `salud_fba`, la app deja de poder subir ese informe
--      —la puerta se cierra de verdad, no por convención—; al meter
--      `inventario_fba`, la app **puede por fin subir el relevo**, que hoy no
--      podía: el fichero del 23 lo subió una persona a mano al Storage.
--
--   2. `frescura_informes()`: la fila `salud_fba` pasa a ser `inventario_fba`.
--      🔴 ESTO NO ES COSMÉTICO. Esa función alimenta el semáforo de frescura, y
--      su columna `subido_buzon` mira `storage.objects` con el prefijo
--      `salud_fba/%`. Si se deja como está, el semáforo vigilará para siempre
--      un buzón donde ya no va a entrar nada y dirá «lleva días sin recibir»
--      sin que nadie pueda hacer nada. El dato bueno vive ahora en
--      `inventario_fba` (fecha_foto / procesado_at) y en `inventario_fba/%`.
--
-- 🔒 Idempotente: dos `CREATE OR REPLACE FUNCTION`. Aplicarla dos veces no
--    cambia nada. Vuelta atrás = volver a poner las dos definiciones de antes.
-- ============================================================================

SET lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 0) GUARDAS PREVIAS. No se cierra la puerta si el relevo no está dentro.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_inv int; f_inv date; k_salud char;
BEGIN
    IF to_regclass('public.inventario_fba') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: `inventario_fba` no existe. No se jubila un informe sin su relevo en pie.';
    END IF;
    SELECT count(*), max(fecha_foto) INTO n_inv, f_inv FROM public.inventario_fba;
    IF n_inv < 100 THEN
        RAISE EXCEPTION 'ABORTA: `inventario_fba` tiene % filas. El relevo no está cargado.', n_inv;
    END IF;
    IF f_inv < CURRENT_DATE - 3 THEN
        RAISE EXCEPTION 'ABORTA: la foto de `inventario_fba` es del %. Antes de cerrar la puerta, que el relevo esté fresco.', f_inv;
    END IF;

    SELECT relkind INTO k_salud FROM pg_class WHERE oid = 'public.salud_fba'::regclass;
    IF k_salud <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba` es relkind=%, esperaba una VISTA. Aplica antes 2026-08-23_salud_fba_pasa_a_vista.sql.', k_salud;
    END IF;

    IF to_regclass('public.salud_fba_historico') IS NULL THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba_historico` no existe. Esta migración NO lo borra; si ya no está, alguien se adelantó y hay que mirarlo.';
    END IF;

    RAISE NOTICE 'Guardas previas OK: relevo con % filas (foto %), salud_fba es vista, histórico en pie.', n_inv, f_inv;
END $$;

-- ---------------------------------------------------------------------------
-- 1) LA LISTA BLANCA DEL BUZÓN
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.moloka_buzones_fase0()
 RETURNS text[]
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  -- 23-ago-2026: fuera 'salud_fba' (informe jubilado; Amazon lo servía roto
  -- desde el 16 y no se vuelve a descargar), dentro 'inventario_fba' (su
  -- relevo, que hasta hoy no se podía subir desde la app).
  select array['inventario_fba','internacional','keepa_escaparate',
               'all_listings','ledger','paneu_aptos','transacciones',
               'custom_analytics']
$function$;

-- ---------------------------------------------------------------------------
-- 2) EL SEMÁFORO DE FRESCURA
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.frescura_informes()
 RETURNS TABLE(informe text, fecha_dato date, subido_buzon timestamp with time zone, procesado_tabla timestamp with time zone)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public', 'storage'
AS $function$
  -- 23-ago-2026: la fila 'salud_fba' pasa a 'inventario_fba'. La vieja miraba el
  -- buzón salud_fba/, donde ya no va a entrar nada nunca más: se habría quedado
  -- en rojo permanente sin que nadie pudiera arreglarlo.
  select 'inventario_fba'::text, (select max(fecha_foto) from inventario_fba),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'inventario_fba/%'),
    (select max(procesado_at) from inventario_fba)
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
  union all select 'custom_analytics', (select max(leido_at)::date from demanda_asin),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'custom_analytics/%'),
    (select max(procesado_at) from demanda_asin);
$function$;

-- ---------------------------------------------------------------------------
-- 3) TESTIGOS. Si algo no cuadra, la transacción deja la base como estaba.
-- ---------------------------------------------------------------------------
DO $$
DECLARE bz text[]; n_fr int; f_inv date; hist int; k char;
BEGIN
    SELECT public.moloka_buzones_fase0() INTO bz;
    IF 'salud_fba' = ANY(bz) THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba` sigue en la lista blanca del buzón.';
    END IF;
    IF NOT ('inventario_fba' = ANY(bz)) THEN
        RAISE EXCEPTION 'ABORTA: `inventario_fba` no ha entrado en la lista blanca del buzón.';
    END IF;
    IF array_length(bz,1) <> 8 THEN
        RAISE EXCEPTION 'ABORTA: la lista blanca tiene % carpetas, esperaba 8. Es un relevo, no un alta ni una baja.', array_length(bz,1);
    END IF;

    -- La comprobación es de la LISTA, no del recuento de políticas.
    SELECT count(*) INTO n_fr FROM public.frescura_informes() WHERE informe = 'inventario_fba';
    IF n_fr <> 1 THEN
        RAISE EXCEPTION 'ABORTA: frescura_informes() devuelve % filas para inventario_fba.', n_fr;
    END IF;
    IF EXISTS (SELECT 1 FROM public.frescura_informes() WHERE informe = 'salud_fba') THEN
        RAISE EXCEPTION 'ABORTA: frescura_informes() sigue devolviendo la fila salud_fba.';
    END IF;
    SELECT fecha_dato INTO f_inv FROM public.frescura_informes() WHERE informe = 'inventario_fba';
    IF f_inv IS NULL THEN
        RAISE EXCEPTION 'ABORTA: la fila inventario_fba de frescura_informes() no trae fecha.';
    END IF;

    -- Y lo que NO debía tocarse:
    SELECT count(*) INTO hist FROM public.salud_fba_historico;
    IF hist = 0 THEN RAISE EXCEPTION 'ABORTA: salud_fba_historico está vacío. Esta migración no lo toca.'; END IF;
    SELECT relkind INTO k FROM pg_class WHERE oid = 'public.salud_fba'::regclass;
    IF k <> 'v' THEN RAISE EXCEPTION 'ABORTA: la vista salud_fba ha dejado de ser vista.'; END IF;

    RAISE NOTICE 'Relevo hecho. Buzones: %', array_to_string(bz, ', ');
    RAISE NOTICE 'frescura_informes(): inventario_fba con fecha %. salud_fba fuera.', f_inv;
    RAISE NOTICE 'INTACTOS: salud_fba_historico % filas · la vista salud_fba sigue siendo vista.', hist;
END $$;
