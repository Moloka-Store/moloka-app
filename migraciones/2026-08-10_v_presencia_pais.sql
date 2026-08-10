-- ============================================================================
-- MIGRACIÓN 2026-08-10 · v_presencia_pais — ¿ha estado alguna vez este producto
--   en este país?  ·  FASE C del encargo Cockpit multi-país
-- ----------------------------------------------------------------------------
-- PARA QUÉ. La alerta `CAJA_SIN_STOCK_PAIS` del Cockpit avisa de los productos
-- donde la buy box es TUYA en un país y no tienes allí ni una unidad (medido hoy:
-- 32 casos · FR 18 · IT 13 · DE 1). Pero el aviso a secas no sirve: hay DOS
-- conversaciones distintas detrás, y la alerta tiene que decir cuál es.
--   · «Amazon no consta que haya repartido unidades allí» → 22 casos. Nunca ha
--     estado. La pregunta es si forzar presencia.
--   · «Vendiste allí y se agotó»                          → 8 casos (55 uds).
--     Ya funcionó. La pregunta es reponer.
--   · «Recibió unidades pero nunca vendió ninguna»        → 2 casos. Es su propia
--     conversación: llegó, no se movió. Ni «nunca estuvo» ni «se agotó».
-- Sin esta vista, los 32 quedan mudos, que es justo lo que la casa no permite.
--
-- 🔴 POR QUÉ ES UNA VISTA Y NO SE LEE EL LEDGER DESDE LA APP. El agregado son
--    496 pares (asin, país) — nada. Pero en crudo, el ledger fuera de España son
--    1.922 filas y CRECE: 🔬 1.036 solo en los últimos 30 días. Con el tope
--    defensivo de 5.000 filas que usa la app, leerlo directo aguantaría unos
--    meses y luego reventaría. Un agregado estable se agrega en la base.
--
-- 🔴🔴 POR QUÉ ESTA VISTA ES «DEFINER» A PROPÓSITO — Y NO ES EL AGUJERO DE LAS OTRAS
--    `ledger_movimientos` tiene RLS ACTIVA y CERO POLÍTICAS: 🔬 medido, la app NO
--    lee de ahí ni una fila, hoy. Eso deja dos caminos:
--      (a) `security_invoker = true` → la vista hereda ese bloqueo y devuelve 0
--          filas. La alerta nacería VACÍA y EN SILENCIO, que es exactamente el
--          pecado del «verde falso»: un cero que parece un dato.
--      (b) Abrirle política de lectura al ledger entero → 18.257 filas con
--          `reference_id`, centros logísticos y `crudo` jsonb, para contestar
--          «¿movió Amazon unidades a Italia?». Desproporcionado.
--    Se elige un tercer camino, que expone MENOS que los dos: la vista corre como
--    su dueño (definer, el modo por defecto de Postgres) y publica SOLO el
--    agregado — asin, país, cuántas entraron, cuántas se vendieron y las fechas.
--    Ni un `reference_id`, ni un centro, ni una línea suelta. La tabla base SIGUE
--    CERRADA: esta migración NO toca la RLS de `ledger_movimientos`.
--
--    ⚠️ NO CONFUNDIR con `v_salud_asin` / `v_escaparate` / `v_estado_asin`, que sí
--    son una fuga pendiente. Aquello no es un problema de «definer»: es que tienen
--    GRANT A ANON. El problema nunca fue el modo de ejecución — fue `anon`. Aquí
--    `anon` se revoca explícitamente abajo, y eso es lo innegociable.
--
-- QUÉ CUENTA CADA COLUMNA (decidido con el dato delante, no por analogía):
--   · uds_recibidas = entradas de unidades a ese país: `WhseTransfers` positivos
--     (Amazon las movió desde otro centro) MÁS `Receipts` positivos (llegaron ahí
--     directamente). 🔬 Incluir Receipts NO mueve la clasificación (22/8/2 sale
--     igual con y sin ellos): se incluyen porque la pregunta es «¿estuvo alguna vez
--     allí?», no «¿por qué vía llegó?».
--   · uds_vendidas  = `Shipments` negativos, con el signo cambiado. En el ledger una
--     venta sale como cantidad negativa; aquí se publica en positivo.
--   · Los demás eventos (CustomerReturns, Adjustments, VendorReturns) NO entran:
--     una devolución no prueba presencia comercial y un ajuste no es un reparto.
--
-- 🔴 `ledger_desde` VA EN CADA FILA, Y NO ES REDUNDANCIA. El ledger empieza el
--    🔬 23-abr-2026: NO cubre «toda la vida» del producto. Sin esa fecha al lado,
--    la app diría «Amazon nunca ha repartido allí» cuando lo que el dato sostiene
--    es «no consta desde el 23-abr». Es §1.4 al pie de la letra: una cifra sin la
--    fecha del dato que la sostiene es una cifra que miente. La app la PINTA.
--
-- CIFRAS DE CONTROL, reproducidas con ESTA lógica en prod (read-only, ANTES del DDL):
--   · 496 pares (asin, país) · ledger 2026-04-23 → 2026-08-08.
--   · Sobre los 32 casos de la alerta: 22 sin reparto · 8 vendieron (55 uds) · 2
--     recibieron sin vender nunca.
--
-- DESPLIEGUE. `create or replace view`: AccessShareLock, no tumba nada, y es solo
--   LECTURA — no roza la operativa de Elena. Aun así por la escalera
--   (restaurar staging → staging → SQL → prod → SQL), con lock_timeout corto.
-- ============================================================================

create or replace view public.v_presencia_pais as
with ventana as (
    select min(fecha) as desde, max(fecha) as hasta from ledger_movimientos
)
select
    btrim(l.asin)                as asin,
    upper(btrim(l.country))      as pais,
    coalesce(sum(l.quantity) filter (
        where l.event_type in ('WhseTransfers', 'Receipts') and l.quantity > 0), 0)::bigint as uds_recibidas,
    coalesce(-sum(l.quantity) filter (
        where l.event_type = 'Shipments' and l.quantity < 0), 0)::bigint                    as uds_vendidas,
    min(l.fecha)                 as primer_movimiento,
    max(l.fecha)                 as ultimo_movimiento,
    -- La VENTANA del libro, al lado de cada cifra: sin ella, «nunca» es mentira.
    (select desde from ventana)  as ledger_desde,
    (select hasta from ventana)  as ledger_hasta
from ledger_movimientos l
where l.asin is not null and btrim(l.asin) <> ''
  and l.country is not null and btrim(l.country) <> ''
group by btrim(l.asin), upper(btrim(l.country));

comment on view public.v_presencia_pais is
  'Agregado por (ASIN, país) del ledger: unidades que ENTRARON y unidades VENDIDAS, '
  'con la ventana del libro. Alimenta el motivo de la alerta CAJA_SIN_STOCK_PAIS. '
  'DEFINER a propósito: publica el agregado sin abrir ledger_movimientos, que sigue '
  'con RLS y sin políticas. anon NO tiene acceso.';

-- Nace cerrado (§4): un objeto nuevo en `public` nace con arwdDxtm para anon Y
-- authenticated por los DEFAULT PRIVILEGES de Supabase, y un `revoke from public` NO
-- los quita (son grants explícitos a un rol). Se revoca a CADA rol por su nombre y
-- luego el grant mínimo. Idempotente: se re-afirma en cada aplicación — y hace falta,
-- porque un DROP+CREATE futuro perdería el ACL y volvería a nacer con anon dentro.
revoke all on public.v_presencia_pais from public, anon, authenticated;
grant select on public.v_presencia_pais to authenticated;
