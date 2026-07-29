-- ============================================================================
-- MIGRACIÓN 2026-07-29 · moloka_ean_norm() sale del arranque de keepa
-- ----------------------------------------------------------------------------
-- HERMANA de 2026-07-29_rls_indices_fuera_del_arranque.sql (#64), que YA anotó
-- que esta función iba en OTRO PR. Aquí está.
--
-- POR QUÉ IMPORTA — y esto NO es rendimiento, es CORRECCIÓN. keepa recreaba la
-- función con `CREATE OR REPLACE FUNCTION` EN CADA carga (procesador_keepa_
-- escaparate.py, antes L611). Mientras keepa la recree, cualquier migración que
-- cambie `moloka_ean_norm` queda **revertida en silencio** en la siguiente carga:
-- la versión del procesador pisa a la de la migración sin avisar. La fuente de
-- verdad de la función tiene que ser UNA (esta migración), no dos.
--
-- (A diferencia del #64, esto NO era el lock del 15:47: una FUNCIÓN no bloquea
--  tablas. El motivo de sacarla es la fuente-de-verdad única, no el candado.)
--
-- QUÉ HACE. Deja `moloka_ean_norm(text)` como la tiene validada la v1 (Diseño
-- §11.8): normaliza EAN/GTIN/UPC para el CONTRASTE del cruce (§5.1) — solo
-- dígitos, sin ceros a la izquierda; así Keepa (0889698946933) y productos.ean
-- (889698946933) se comparan sin encender ean_no_confirmado en falso. Extraída
-- VERBATIM del `SQL_FUNCION` que keepa ejecutaba: misma definición, solo cambia
-- QUIÉN es su dueño (la migración, no el arranque). IMMUTABLE, sin SECURITY
-- DEFINER, en `public` (regla §1.1 de CLAUDE.md). `CREATE OR REPLACE` es
-- idempotente: aplicarla dos veces no cambia nada.
--
-- A partir de aquí, keepa NO la recrea: solo COMPRUEBA que existe (y aborta
-- pidiendo esta migración si no), igual que con la RLS y con v_keepa_cruce.
--
-- 🔒 No pide locks sobre tablas de Elena; se puede aplicar por la escalera sin
--    ventana especial. (El WARN `function_search_path_mutable` del linter sobre
--    esta función NO se toca aquí a propósito: la función solo usa built-ins de
--    pg_catalog —NULLIF/ltrim/regexp_replace/coalesce—, así que el search_path no
--    la puede secuestrar; fijarlo sería reescribir una función validada, y eso se
--    decide aparte.)
-- ============================================================================

CREATE OR REPLACE FUNCTION moloka_ean_norm(cod text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(ltrim(regexp_replace(coalesce(cod, ''), '[^0-9]', '', 'g'), '0'), '')
$$;
