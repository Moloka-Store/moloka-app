-- ============================================================================
-- MIGRACIÓN 2026-08-11 · `seller_observaciones.precio_tarifado`
--   A qué precio corresponden las tarifas que devolvió el popup del Seller.
--
-- 🔴 PROPUESTA. NO APLICADA.
-- ----------------------------------------------------------------------------
-- PARA QUÉ: habilita el nivel intermedio de la prelación de tarifas
--     factura > seller_estimado_a_precio > desconocido
-- El popup da la tarifa AL PRECIO QUE SE LE PONGA, así que se puede conocer el
-- lado alto del escalón de 20 € sin esperar a que haya una venta facturada. Pero
-- una tarifa sin el precio al que aplica no sirve para nada: es justo el dato que
-- faltaba.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- 🔴 POR QUÉ **NO** SE AÑADE UN `es_simulacion` — y por qué NO es el motivo que
--    yo había escrito
-- ══════════════════════════════════════════════════════════════════════════════
-- Mi primera propuesta decía: «no hace falta un booleano porque es derivable de
-- `precio_tarifado <> precio`». 🔬 **ESO ES FALSO, y lo refuta una fila real:**
-- la id 62 (`J9-W3W1-31V3`, 2-ago) tiene `precio = 20,49` cuando la ficha estaba a
-- 19,99. O sea que en esa captura `precio` guarda el precio CONSULTADO, no el del
-- listing. Con la regla derivada, esa simulación se clasificaría como observación
-- real — exactamente al revés de lo que es.
--
-- 🔑 El booleano no se añade por otra razón, que es mejor: **operativamente no hace
-- falta saber si fue simulación.** Lo que el cálculo de margen pregunta es «¿tengo
-- una tarifa del Seller para este SKU a un precio >= 20?», y eso lo contesta
-- `precio_tarifado` solo. Una estimación del popup a 20,49 vale lo mismo tanto si
-- el listing estaba a 20,49 como si estaba a 19,99: en los dos casos es la
-- estimación de Amazon para ese precio. La procedencia (estimación, no factura) ya
-- viaja a nivel de TABLA — todo lo de `seller_observaciones` es `seller_estimado`.
--
-- Y si algún día hiciera falta la distinción, se resuelve sin columna nueva:
-- comparando `precio_tarifado` con el precio de ficha de ese día en
-- `listings_amazon_hist`. Es como se auditaron estas 65 filas.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- EL RELLENO — auditado fila a fila, no supuesto
-- ══════════════════════════════════════════════════════════════════════════════
-- Contrastadas las 65 observaciones contra `listings_amazon_hist` del mismo SKU en
-- la fecha más cercana anterior:
--   · 63 coinciden al céntimo  -> captura al precio vigente -> `precio_tarifado = precio`
--   · id 62 -> 20,49 con ficha a 19,99, `tarifa_fba` 3,80: SIMULACIÓN del lado alto
--   · id  5 -> 4,78 con ficha a 4,60 (18 cts sobre un producto de 4,60): SIN RESOLVER
--
-- 🔒 La id 5 se queda en NULL A PROPÓSITO. NULL aquí significa «no consta a qué
--    precio», que es la verdad, y no rompe nada: la vista trata el NULL como
--    desconocido y esa fila simplemente no aporta tarifa. Rellenarla con `precio`
--    sería inventar el dato que esta migración existe para dejar de inventar.
-- ============================================================================

set local lock_timeout = '3s';

-- ── 1) La columna ───────────────────────────────────────────────────────────
alter table public.seller_observaciones
  add column if not exists precio_tarifado numeric;

comment on column public.seller_observaciones.precio_tarifado is
'Precio al que corresponden tarifa_fba / comision_eur / comision_pct_* / tarifas_totales,
tal y como los devolvió el popup del Seller. NO es necesariamente el precio del listing:
el popup permite consultar a un precio hipotético, y así se conoce el lado alto del
escalón de 20 EUR sin esperar a una venta facturada.
NULL = no consta a qué precio se leyeron las tarifas; esa fila NO aporta tarifa.
Para saber si una lectura fue simulación, comparar con el precio de ficha de ese día en
listings_amazon_hist. No se guarda como booleano: operativamente no hace falta, y
`precio_tarifado <> precio` NO sirve para deducirlo (ver la fila id 62).';

-- ── 2) Relleno de las 63 auditadas ──────────────────────────────────────────
update public.seller_observaciones
   set precio_tarifado = precio
 where id not in (5, 62)
   and precio_tarifado is null;

-- ── 3) La simulación del lado alto, explícita ───────────────────────────────
-- Es la primera captura del método que esta migración generaliza: se preguntó al
-- popup por 20,49 EUR teniendo la ficha a 19,99, y devolvió tarifa_fba = 3,80 —
-- la mitad ALTA del par 3,28 <-> 3,80 de la doctrina 7. O sea que el escalón de
-- los 20 EUR ya estaba medido aquí y nadie lo había leído como tal.
update public.seller_observaciones
   set precio_tarifado = 20.49
 where id = 62;

-- ── 4) La id 5 NO se toca: queda NULL hasta que Fernando la revise ──────────

-- ── VERIFICACIÓN (en producción, después de aplicar) ────────────────────────
--   select count(*) filter (where precio_tarifado is not null) as con_precio,  -- 64
--          count(*) filter (where precio_tarifado is null)     as sin_precio,  --  1 (id 5)
--          count(*) filter (where id = 62 and precio_tarifado = 20.49) as la_simulacion  -- 1
--     from public.seller_observaciones;
--
-- ── VUELTA ATRÁS ────────────────────────────────────────────────────────────
--   alter table public.seller_observaciones drop column precio_tarifado;
--   🔴 Ojo: DROP+CREATE de una tabla PIERDE el ACL (CLAUDE.md §4). Aquí no aplica
--      porque es ADD/DROP COLUMN, que conserva el ACL de la tabla.
