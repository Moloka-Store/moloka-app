-- ============================================================================
-- MIGRACIÓN 2026-08-23 · v_ventas_ventanas — las ventanas de venta SIN Amazon
-- ----------------------------------------------------------------------------
-- POR QUÉ. `salud_fba.units_shipped_t7/t30/t60/t90` es lo que la app usa para
-- saber si algo vende, y por tanto para reponerlo. Ese dato viene roto de Amazon
-- desde el 16-ago-2026: de 219 filas, sólo 39 traen t30 > 0. Medido el 23-ago,
-- el resultado en la app es que **de 212 referencias que vendieron algo en 30
-- días, ve ventas en 39**: 174 referencias que venden salen como paradas, y una
-- referencia que la app cree parada no se repone nunca.
--
-- QUÉ HACE. Calcula las mismas cuatro ventanas desde fuentes NUESTRAS, que ya
-- están en la base y llegan sanas.
--
-- 🔒 ES ADITIVA. Crea UNA vista nueva. No toca `salud_fba`, ni sus cinco vistas,
--    ni `v_velocidad_ventas`, ni `v_velocidad_ventas_paneu` (que siguen igual y
--    las usa quien las use). Nadie la lee todavía.
--
-- DE DÓNDE SALE CADA CIFRA, y por qué esa y no otra:
--
--   · uds_7d/30d/60d/90d ← `ledger_movimientos` con event_type='Shipments'.
--     Es la SALIDA FÍSICA real de los almacenes de Amazon, que es exactamente lo
--     que medía `units_shipped_*`. La cantidad viene NEGATIVA (medido 23-ago:
--     2.733 filas, todas entre −10 y −1), por eso el abs().
--     🔬 Contrastado contra transacciones en la ventana de 30 días: 212 asin en
--        las dos fuentes, **162 idénticos y 209 dentro de ±2**. El ledger da
--        2.911 uds y transacciones 2.829 (+2,8%), y la diferencia tiene nombre:
--        transacciones sólo tiene ES, IT y FR.
--
--   · uds_30d_es/it/fr ← `transacciones_movimientos` (tipo_norm='pedido'), que
--     es lo único que sabe en QUÉ MERCADO se vendió. El ledger sabe de qué
--     almacén salió, que no es lo mismo.
--     ⚠️ Por eso `uds_30d_marketplace` puede ser MENOR que `uds_30d`: lo que se
--        vendió en Alemania o Países Bajos no está en transacciones. No es un
--        descuadre, es el alcance de cada fuente, y por eso van las dos.
--
--   · devoluciones_30d ← ledger 'CustomerReturns'. NO se resta de uds_30d:
--     `units_shipped_*` de Amazon tampoco las restaba, y mezclar las dos cosas
--     rompería la comparación. Se da aparte para que se vea.
--
-- 🔒 LAS VENTANAS SE ANCLAN AL DATO, NO A `now()`. Cada fuente cuenta hacia atrás
--    desde SU último día cargado. Si un informe se retrasa, la ventana no se
--    llena de días vacíos fingiendo que no se vendió nada — que es la forma más
--    tonta de repetir el error que estamos arreglando. `dias_desde_ultimo_dato`
--    dice a la cara cuánto retraso lleva cada fuente.
--
-- 🔒 sku → asin por `listings_amazon` (el traductor de SKU, §3.3), quedándose con
--    el listing más reciente de cada SKU. `salud_fba` NO se usa aquí a propósito:
--    es justo la tabla que está rota.
-- 🔴 PERMISOS: HAY QUE CONCEDERLOS A MANO, Y NO POR LA RAZON QUE PARECE.
--    MEDIDO EN PRODUCCION EL 23-ago-2026, no deducido de la doctrina:
--
--    1) En `public` hay DOS `pg_default_acl`, y el que aplica depende de QUIEN crea
--       el objeto:
--          creado por supabase_admin -> {postgres, anon, authenticated, service_role}
--          creado por postgres       -> {postgres, service_role}          <- SIN anon
--       Las migraciones corren como `postgres`, asi que por ESTE camino una vista
--       nueva NO nace abierta a `anon`. (La regla de §4 del CLAUDE.md sigue siendo
--       cierta para el otro camino — el editor de Supabase —, que es de donde
--       venian las vistas que hubo que cerrar en `revoke_anon_9_vistas`.)
--
--    2) 🔴 PERO NACE SIN `authenticated`, Y ESO ROMPE LA APP. `salud_fba` es
--       `security_invoker`: cuando la app pregunta, Postgres comprueba el permiso
--       sobre CADA objeto de debajo COMO `authenticated` — y esta vista es uno de
--       ellos. Sin el GRANT, la app se lleva un
--           permission denied for view v_ventas_ventanas
--       justo en la pantalla que esto viene a arreglar.
--       🔬 La prueba de que nace asi: `inventario_fba`, creada el mismo dia por este
--          mismo workflow, quedo con `{postgres=arwdDxtm, service_role=arwdDxtm}` —
--          `authenticated` NO estaba.
--       ⚠️ Y NO LO CAZA NINGUN TESTIGO DE LAS OTRAS MIGRACIONES, porque sus
--          `SELECT count(*)` corren como `postgres`, que lo puede todo. Es una
--          comprobacion que no puede fallar: sale verde y la app se cae despues.
--          Por eso el bloque del final pregunta explicitamente por el rol.
--
--    Se revoca a cada rol por su nombre y se concede lo minimo, como sus hermanas.
--
-- 🔒 Sobre los datos: `anon` no ve nada de aqui porque las tablas base tienen RLS
--    con politica solo para `authenticated`. Ojo, es la RLS quien lo para y no el
--    grant: medido, `listings_amazon` y `transacciones_movimientos` SI tienen
--    `anon=arwdDxtm` en su ACL; solo `ledger_movimientos` no.
-- ============================================================================

SET lock_timeout = '5s';

CREATE OR REPLACE VIEW v_ventas_ventanas
WITH (security_invoker = true) AS
WITH ancla AS (
    SELECT (SELECT max(fecha) FROM ledger_movimientos)        AS hasta_ledger,
           (SELECT max(fecha) FROM transacciones_movimientos) AS hasta_trans
), salidas AS (
    SELECT l.asin,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger -  7) AS uds_7d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 30) AS uds_30d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 60) AS uds_60d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 90) AS uds_90d
    FROM ledger_movimientos l CROSS JOIN ancla a
    WHERE l.event_type = 'Shipments' AND l.asin IS NOT NULL
      AND l.fecha > a.hasta_ledger - 90
    GROUP BY l.asin
), devueltas AS (
    SELECT l.asin, sum(abs(l.quantity)) AS devoluciones_30d
    FROM ledger_movimientos l CROSS JOIN ancla a
    WHERE l.event_type = 'CustomerReturns' AND l.asin IS NOT NULL
      AND l.fecha > a.hasta_ledger - 30
    GROUP BY l.asin
), sku_asin AS (
    SELECT DISTINCT ON (btrim(seller_sku)) btrim(seller_sku) AS sku, btrim(asin) AS asin
    FROM listings_amazon
    WHERE seller_sku IS NOT NULL AND asin IS NOT NULL AND btrim(asin) <> ''
    ORDER BY btrim(seller_sku), fecha_informe DESC
), mercado AS (
    SELECT sa.asin,
        coalesce(sum(t.cantidad) FILTER (WHERE t.pais = 'ES'), 0) AS uds_30d_es,
        coalesce(sum(t.cantidad) FILTER (WHERE t.pais = 'IT'), 0) AS uds_30d_it,
        coalesce(sum(t.cantidad) FILTER (WHERE t.pais = 'FR'), 0) AS uds_30d_fr,
        coalesce(sum(t.cantidad), 0)                              AS uds_30d_marketplace,
        round(coalesce(sum(t.ventas_producto), 0), 2)             AS eur_30d_marketplace
    FROM transacciones_movimientos t
    CROSS JOIN ancla a
    JOIN sku_asin sa ON sa.sku = btrim(t.sku)
    WHERE t.tipo_norm = 'pedido' AND t.fecha > a.hasta_trans - 30
    GROUP BY sa.asin
)
SELECT
    coalesce(s.asin, m.asin)                       AS asin,
    coalesce(s.uds_7d,  0)                         AS uds_7d,
    coalesce(s.uds_30d, 0)                         AS uds_30d,
    coalesce(s.uds_60d, 0)                         AS uds_60d,
    coalesce(s.uds_90d, 0)                         AS uds_90d,
    round(coalesce(s.uds_30d, 0)::numeric / 30, 3) AS vel_dia_30d,
    round(coalesce(s.uds_90d, 0)::numeric / 90, 3) AS vel_dia_90d,
    coalesce(m.uds_30d_es, 0)                      AS uds_30d_es,
    coalesce(m.uds_30d_it, 0)                      AS uds_30d_it,
    coalesce(m.uds_30d_fr, 0)                      AS uds_30d_fr,
    coalesce(m.uds_30d_marketplace, 0)             AS uds_30d_marketplace,
    coalesce(m.eur_30d_marketplace, 0)             AS eur_30d_marketplace,
    coalesce(d.devoluciones_30d, 0)                AS devoluciones_30d,
    a.hasta_ledger                                 AS ventana_hasta_ledger,
    a.hasta_trans                                  AS ventana_hasta_marketplace,
    CURRENT_DATE - a.hasta_ledger                  AS dias_desde_ultimo_dato
FROM salidas s
FULL JOIN mercado m  ON m.asin = s.asin
LEFT JOIN devueltas d ON d.asin = coalesce(s.asin, m.asin)
CROSS JOIN ancla a;

COMMENT ON VIEW v_ventas_ventanas IS
  'Las ventanas de venta por ASIN (7/30/60/90 dias) calculadas SIN Amazon. Nace el 23-ago-2026 '
  'porque salud_fba.units_shipped_* llega roto desde el 16-ago y eso hace que la app de por '
  'paradas 174 referencias que si venden. uds_* = salida fisica del ledger (event Shipments, '
  'todos los mercados); uds_30d_es/it/fr = transacciones (unica fuente que sabe el marketplace, '
  'y solo tiene ES/IT/FR, por eso uds_30d_marketplace puede ser menor que uds_30d). Las ventanas '
  'se anclan al ultimo dia CARGADO de cada fuente, nunca a now(): un informe retrasado no debe '
  'rellenar la ventana de dias vacios. Contrastadas las dos fuentes a 30 dias: 162 asin identicos '
  'y 209 dentro de +-2 sobre 212.';

-- ---------------------------------------------------------------------------
-- PERMISOS. Revocar ANTES de conceder, y a cada rol por su nombre (§4).
-- ---------------------------------------------------------------------------
REVOKE ALL ON public.v_ventas_ventanas FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_ventas_ventanas TO authenticated;

-- ---------------------------------------------------------------------------
-- TESTIGOS, dentro de la transaccion. Si esto no cuadra, no se escribe nada.
-- 🔑 Va aqui y no solo en la migracion siguiente: una migracion que no deja
--    rastro en el log no se distingue de una que no aplico nada.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_30 int; n_7 int; n_total int; f_led date; f_tra date; retraso int;
BEGIN
    SELECT count(*) FILTER (WHERE uds_30d > 0), count(*) FILTER (WHERE uds_7d > 0),
           count(*), max(ventana_hasta_ledger), max(ventana_hasta_marketplace),
           max(dias_desde_ultimo_dato)
      INTO n_30, n_7, n_total, f_led, f_tra, retraso
      FROM public.v_ventas_ventanas;

    IF n_total = 0 THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas devuelve 0 filas. Sin entrada no hay nada que medir.';
    END IF;
    -- El mismo suelo que exige la migracion siguiente, aqui y no dentro de tres
    -- pasos: si no llega, la vista no arregla lo que viene a arreglar.
    IF n_30 < 100 THEN
        RAISE EXCEPTION 'ABORTA: solo % referencias con venta en 30 dias. Medido el 23-ago-2026: 211. Por debajo de 100 esto no cura la app.', n_30;
    END IF;
    IF has_table_privilege('anon', 'public.v_ventas_ventanas', 'SELECT') THEN
        RAISE EXCEPTION 'ABORTA: `anon` puede leer v_ventas_ventanas. El revoke no ha hecho su trabajo (default privileges de Supabase).';
    END IF;
    IF NOT has_table_privilege('authenticated', 'public.v_ventas_ventanas', 'SELECT') THEN
        RAISE EXCEPTION 'ABORTA: `authenticated` NO puede leer v_ventas_ventanas: la app se quedaria sin ventas.';
    END IF;

    RAISE NOTICE 'v_ventas_ventanas OK: % filas · % con venta 30d · % con venta 7d · ledger hasta % · marketplace hasta % · % dias de retraso · anon fuera, authenticated dentro',
                 n_total, n_30, n_7, f_led, f_tra, retraso;
END $$;
