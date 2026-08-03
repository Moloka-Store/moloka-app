-- ============================================================================
-- MIGRACIÓN 2026-08-03 · v_velocidad_ventas — velocidad REAL por ASIN desde
--   transacciones (ES + IT + FR)  ·  BLOQUE B1 del encargo Inventario
-- ----------------------------------------------------------------------------
-- EL BUG QUE ARREGLA (B1, medido en prod 3-ago). La cobertura estaba
-- sobreestimada ~17%: la app dividía STOCK europeo entre VELOCIDAD española.
-- El informe de Salud, aunque se baje de España, trae el pool de stock europeo
-- COMPLETO, pero sus `units_shipped` son SOLO las ventas de amazon.es. Resultado:
-- donde Elena leía 43 días de cobertura, quedaban ~36. Riesgo de rotura de stock.
--
-- ESTA VISTA da la velocidad de la manera correcta: unidades REALMENTE vendidas
-- en TODOS los países (ES+IT+FR), por ASIN, desde las transacciones ya cargadas.
-- No espera a ninguna descarga nueva (BLOQUE D).
--
-- DEFINICIONES (cerradas por Fernando 3-ago; no se reinterpretan):
--   · Venta = tipo_norm = 'pedido'. NO cuentan 'reembolso' ni 'reembolso_inventario'
--     (verificado: en la ventana no hay tipo_norm NULL, así que 'pedido' no se deja
--      ninguna venta fuera).
--   · Velocidad total = suma de ES + IT + FR (ventas DISTINTAS: SÍ se suman, no es
--     el pool de stock repetido). uds_30d_total es la suma de todos los países que
--     vendieron (hoy = ES+IT+FR; el día que DE venda, entra solo).
--   · Ventana = últimos 30 días contados desde MAX(fecha) de transacciones, NO
--     desde hoy: el informe va ~5 días por detrás. Ese desfase se PUBLICA en
--     `ventana_hasta` para que la interfaz lo ETIQUETE ("datos hasta 29-jul"), no
--     se disimula (§1.4: una cifra sin la fecha del dato que la sostiene miente).
--
-- 🔴 FRESCURA — que la velocidad NO envejezca en silencio (Fernando, 3-ago). Esta
--    velocidad depende de que se descarguen las transacciones. Si un día dejan de
--    bajarse, `ventana_hasta` se congela y la velocidad se vuelve la de hace semanas
--    SIN avisar — y una velocidad de hace 3 semanas engaña MÁS que la de solo-España
--    que estamos arreglando. Por eso la vista expone `dias_desde_ultimo_dato`
--    (= CURRENT_DATE − ventana_hasta): la ANTIGÜEDAD del dato, no un adorno. La
--    interfaz avisa a partir de un umbral (propuesto para v2: ámbar > 7 días,
--    "no fiable" > 14 — la mitad de la ventana de 30 d a ciegas, con margen antes
--    de los 21 d que Fernando marca como claramente engañosos). El umbral vive en
--    la UI; la vista solo da el dato.
--
-- EL PUENTE SKU→ASIN. Las transacciones traen SKU, no ASIN. El cruce va por
-- `listings_amazon` (All Listings), que es la FUENTE DE IDENTIDAD (§1.1) y ve los
-- SKU inactivos/muertos. Medido en prod (ventana 30-jun→29-jul):
--   · 213 SKU vendieron → los 213 cruzan a ASIN (0 huérfanos; por `productos` se
--     perderían 2 SKU / 14 uds, por eso el puente es listings, no productos).
--   · 0 SKU apuntan a >1 ASIN (sin ambigüedad). Aun así el puente se toma con
--     DISTINCT ON (seller_sku) ORDER BY fecha_informe DESC → si algún día un SKU
--     mapeara a dos ASIN, gana el listing más reciente y NUNCA se dobla el conteo.
--   · Un ASIN con dos SKU (dos vidas): el GROUP BY asin SUMA sus unidades al mismo
--     ASIN, que es lo correcto.
--
-- CIFRAS DE CONTROL reproducidas con ESTA lógica en prod (read-only, ANTES del DDL):
--   · Total 30d: 2.728 uds  (ES 2.238 · IT 324 · FR 166) · n_asin 213
--   · Sobre los 177 ASIN que también están en Salud: 2.356 (ES 1.964 + IT/FR 392),
--     frente a los 2.009 que dice hoy units_shipped_t30. (2.009 = síntoma del bug.)
--
-- RELACIÓN CON B3. Al no usar salud_fba.units_shipped para la velocidad, esta vista
-- deja fuera del cálculo las 121 uds de T30 rancio de las filas fantasma (B3): el
-- impacto de B3 sobre la cobertura que ve Elena queda neutralizado por aquí. La
-- higiene de esas filas en salud_fba se trata aparte (es un cambio de procesador que
-- roza la operativa; va en su PR con el visto bueno de Fernando).
--
-- 🔒 security_invoker = true: corre con permisos de quien consulta → respeta el RLS
--    de transacciones_movimientos y listings_amazon. Sin SECURITY DEFINER.
-- 🔒 NACE CERRADO (§4): un objeto nuevo en `public` nace con arwdDxtm a anon Y
--    authenticated por los DEFAULT PRIVILEGES de Supabase, y un revoke from public
--    NO los quita. Se revoca a CADA rol por su nombre y luego el grant mínimo.
--
-- DESPLIEGUE. CREATE OR REPLACE VIEW: AccessShareLock, no tumba nada. Aun así por la
--   escalera (staging → SQL → prod → SQL), con lock_timeout corto en prod. Advisors
--   después. Es solo LECTURA; no toca la operativa de Elena.
-- ============================================================================

create or replace view public.v_velocidad_ventas
with (security_invoker = true) as
with ventana as (
    select (max(fecha) - interval '30 days')::date as desde,
           max(fecha)                              as hasta
    from transacciones_movimientos
),
sku_asin as (   -- puente identidad SKU→ASIN (listings_amazon, fuente dura §1.1)
    select distinct on (btrim(seller_sku))
           btrim(seller_sku) as sku,
           btrim(asin)       as asin
    from listings_amazon
    where seller_sku is not null and asin is not null and btrim(asin) <> ''
    order by btrim(seller_sku), fecha_informe desc
),
ventas as (
    select sa.asin, t.pais, t.cantidad
    from transacciones_movimientos t
    join ventana  v  on t.fecha > v.desde            -- ventana desde max(fecha)
    join sku_asin sa on sa.sku = btrim(t.sku)
    where t.tipo_norm = 'pedido'                      -- venta; NO reembolsos
)
select
    asin,
    coalesce(sum(cantidad) filter (where pais = 'ES'), 0) as uds_30d_es,
    coalesce(sum(cantidad) filter (where pais = 'IT'), 0) as uds_30d_it,
    coalesce(sum(cantidad) filter (where pais = 'FR'), 0) as uds_30d_fr,
    sum(cantidad)                                         as uds_30d_total,
    round(sum(cantidad)::numeric / 30, 2)                 as vel_dia_total,
    (select desde from ventana)                          as ventana_desde,
    (select hasta from ventana)                          as ventana_hasta,
    (CURRENT_DATE - (select hasta from ventana))         as dias_desde_ultimo_dato
from ventas
group by asin;

-- Nace cerrado (§4): revocar los grants por defecto de Supabase a CADA rol por su
-- nombre y luego conceder el mínimo. Idempotente: se re-afirma en cada aplicación.
revoke all on public.v_velocidad_ventas from public, anon, authenticated;
grant select on public.v_velocidad_ventas to authenticated;
