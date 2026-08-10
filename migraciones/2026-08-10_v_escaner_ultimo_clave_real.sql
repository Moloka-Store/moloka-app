-- ============================================================================
-- MIGRACIÓN 2026-08-10 · v_escaner_ultimo — DEDUPLICAR POR LA CLAVE REAL
--   ·  Corrige la migración `2026-08-10_v_escaner_ultimo.sql` (PR #130), del mismo día
-- ----------------------------------------------------------------------------
-- QUÉ ESTABA MAL. La vista hacía `distinct on (ean, proveedor)`. La clave real de
-- `escaner_memoria` NO es ésa: es **(proveedor, ean, es_case)**, y no es una deducción
-- —está escrita en el propio escáner, que la usa para escribir:
--
--     sb.table('escaner_memoria').upsert(lote, on_conflict='proveedor,ean,es_case')
--                                                            ^^^^^^^^^^^^^^^^^^^^^
--     (moloka_escaner_nube.py, moloka_escaner_pro_nube.py, moloka_detector_bems.py)
--
-- `es_case` distingue **dos presentaciones del mismo EAN**: comprarlo suelto o comprarlo
-- por caja. Son dos ofertas distintas del mismo proveedor, cada una con SU precio y SU
-- disponibilidad. Deduplicar por (ean, proveedor) las mete en el mismo saco y deja pasar
-- una sola, elegida por `fecha desc, id desc` — pero es que **las dos suelen ser del
-- MISMO día**, así que quien gana lo decide el `id`. O sea: al azar.
--
-- 🔴 Es exactamente lo que CLAUDE.md §2 prohíbe por escrito: *«dedup por la clave REAL de
--    cada tabla, nunca una "colapsada" que dependa de un supuesto»*. El supuesto aquí era
--    «un proveedor tiene un precio por EAN», y es falso: tiene hasta dos.
--
-- 🔬 EL DAÑO, MEDIDO sobre los 383 ASIN con proveedor comprable (desempatando el precio
--    de forma estable en las dos versiones, para no contar como cambio lo que solo era
--    un empate resuelto en distinto orden):
--
--      · 30 pares (ean, proveedor) tienen las DOS presentaciones, y en **21** la vista
--        vieja devolvía la de CAJA.
--      · **5 ASIN** cambian de precio de compra.
--      · **2 ASIN** cambian de proveedor elegido.
--      · **4 ASIN** cambian el «¿lo tiene?» — de los cuales **1 decía que lo tiene y
--        NO lo tiene**. Ése es el que duele: es la pantalla mandando a Fernando a
--        comprar a un proveedor que no lo tiene.
--
--    Ejemplo real (ean 889698715560, MOLOKA, las dos filas del 4-jul):
--        es_case = false → 10,00 €, presente = true    ← la unidad, que es lo que se pinta
--        es_case = true  →  8,50 €, presente = false   ← la caja, y encima no la tiene
--    La vista vieja podía devolver la segunda. Precio de caja y «no lo tiene» en una fila
--    que va de unidades.
--
-- ⚠️ Y OJO A LO QUE `pa` NO ES: en las filas de caja **no es el precio de la caja**, es el
--    precio POR UNIDAD comprando caja (por eso 8,50 < 10,00). Medido en las 34 filas con
--    `es_case = true`. Así que no hay que dividir nada por el tamaño de la caja — pero
--    tampoco se pueden mezclar, porque comprar caja obliga a llevarse la caja entera.
--
-- QUÉ HACE ESTA MIGRACIÓN. Dos cosas y ninguna más:
--   1. `distinct on (m.ean, m.proveedor, m.es_case)` — la clave real, las dos filas viven.
--   2. `es_case` ya estaba en el SELECT, así que quien consulta puede elegir. Y elige el
--      código, no la vista: el Cockpit pinta productos UNIDAD (`es_chase = false`), así
--      que se queda con `es_case = false` y solo cae en la de caja si no hay otra.
--
-- 🔒 LO QUE SIGUE IGUAL, que es todo lo demás: el filtro al catálogo, el `security_invoker`,
--    el `revoke` a `anon`, y que la vista **no decide** (no excluye proveedores ni calcula
--    márgenes; eso vive en el código, en constantes con nombre).
--
-- CIFRAS DE CONTROL (read-only, reproducidas ANTES del DDL):
--   · La vista pasa de 🔬 957 a 🔬 **987** filas: **+30**, que son exactamente los 30
--     pares (ean, proveedor) que tienen las DOS presentaciones y hasta hoy sólo dejaban
--     pasar una.
--     ⚠️ Ojo al cálculo fácil y equivocado, porque quien verifique lo va a hacer: NO es
--     957 + 34 (las filas con `es_case = true` de la vista) = 991. De esas 34, **4** son
--     pares donde la caja es la ÚNICA oferta de ese proveedor: ya estaban contadas en las
--     957 y no añaden fila. Sólo suman las 30 que tienen pareja. 957 + 30 = 987.
--     Si sale otro número, el `distinct on` no agrupa por lo que se cree.
--   · La invariante de §3 NO se mueve: **383 con proveedor comprable + 10 sin ninguno =
--     393 ASIN**. Esta migración cambia QUÉ fila gana, no CUÁNTOS productos tienen oferta.
--   ⚠️ Las cifras exactas bailan en el día (el catálogo se mueve y el escáner corre varias
--     veces): se re-miden al aplicar. Las invariantes sí son criterio.
--
-- DESPLIEGUE. `create or replace view`: AccessShareLock, instantáneo, solo lectura.
--   Por la escalera igual (staging → SQL → prod → SQL), con lock_timeout corto.
--   🔒 `create or replace` CONSERVA el ACL, así que el `revoke`/`grant` de la migración
--      anterior sigue vigente. Se re-afirma abajo de todos modos: cuesta nada y cubre el
--      día que alguien la recree con DROP + CREATE (CLAUDE.md §4).
-- ============================================================================

set local lock_timeout = '3s';

create or replace view public.v_escaner_ultimo
with (security_invoker = true) as
select distinct on (m.ean, m.proveedor, m.es_case)
    m.ean,
    m.proveedor,
    m.pa,                       -- precio de compra POR UNIDAD (también en las de caja)
    m.presente,                 -- 🔴 BOOLEANO: «lo tiene / no lo tiene», NO una cantidad
    m.fecha,                    -- de cuándo es ese precio: va SIEMPRE al lado del importe
    m.es_case,                  -- 🔴 parte de la CLAVE: suelto (false) vs por caja (true)
    m.marca
from escaner_memoria m
where m.ean is not null
  and m.proveedor is not null
  -- Solo lo que el Cockpit puede pintar: sus productos.
  and exists (
    select 1 from productos p
    where p.ean = m.ean and p.asin is not null and p.es_chase = false
  )
order by m.ean, m.proveedor, m.es_case, m.fecha desc, m.id desc;  -- empate del día → la última cargada

comment on view public.v_escaner_ultimo is
  'El precio VIGENTE de cada proveedor para cada EAN del catálogo: la fila más reciente '
  'de escaner_memoria por su clave REAL (ean, proveedor, es_case) — suelto y por caja son '
  'dos ofertas distintas y las dos viven. Da el dato, no la decisión: no elige proveedor, '
  'no excluye a ninguno y no elige presentación. anon NO tiene acceso.';

-- Se re-afirma el cierre (§4): `create or replace` conserva el ACL, pero un DROP+CREATE
-- futuro lo perdería y el objeto renacería con `anon` dentro por los DEFAULT PRIVILEGES
-- de Supabase. Idempotente.
revoke all on public.v_escaner_ultimo from public, anon, authenticated;
grant select on public.v_escaner_ultimo to authenticated;
