-- ============================================================================
-- Migración TRANSACCIONES — el buzón transacciones/ gana permiso de subida
-- ----------------------------------------------------------------------------
-- La subida del buzón va con la SESIÓN del usuario (los objetos de storage llevan
-- su owner_id), así que la controla RLS. Las tres políticas de storage.objects
-- para `authenticated` — buzones_v2_insert / _select / _update — permiten la
-- primera carpeta del nombre solo si está en:
--     moloka_buzones_fase0() || ARRAY['entrada']
-- y hoy la función devuelve {salud_fba, internacional, keepa_escaparate,
-- all_listings, ledger, paneu_aptos}: `transacciones` NO está en ninguna de las
-- dos, luego RLS RECHAZA subir a transacciones/. (El procesador lee con la llave
-- de servicio y se salta RLS; esto es solo para la SUBIDA del usuario.)
--
-- Arreglo: añadir 'transacciones' a moloka_buzones_fase0(). Las tres políticas lo
-- cogen solas (leen la función, no una lista propia). Es ADITIVO: no toca 'entrada'
-- ni quita nada a anon; solo suma un buzón permitido.
--
-- IDEMPOTENTE: CREATE OR REPLACE deja la función en su forma final corras las veces
-- que corras. Se conserva la firma exacta (IMMUTABLE, search_path '').
--
-- Escalera: staging → SQL → producción → SQL. Verificado en staging el 28-jul:
--   moloka_buzones_fase0() incluye 'transacciones' y la expresión de política
--   permite transacciones/ Y entrada/ (permite_transacciones = permite_entrada = true).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.moloka_buzones_fase0()
RETURNS text[]
LANGUAGE sql
IMMUTABLE
SET search_path TO ''
AS $function$
  select array['salud_fba','internacional','keepa_escaparate',
               'all_listings','ledger','paneu_aptos','transacciones']
$function$;

-- Verificación (no altera nada): debe devolver la lista con 'transacciones' al final
-- y true en las dos comprobaciones de política.
--   select moloka_buzones_fase0() as buzones,
--          (storage.foldername('transacciones/x.csv'))[1]
--            = ANY (moloka_buzones_fase0() || ARRAY['entrada']) as permite_transacciones,
--          (storage.foldername('entrada/x.csv'))[1]
--            = ANY (moloka_buzones_fase0() || ARRAY['entrada']) as permite_entrada;
