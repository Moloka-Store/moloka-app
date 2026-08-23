-- ============================================================================
-- MIGRACIÓN · v_ventas_ventanas cierra sus ventanas en el ÚLTIMO DÍA COMPLETO
-- ----------------------------------------------------------------------------
-- EL FALLO. Las cuatro ventanas del ledger se anclan al último día CARGADO
-- (`max(fecha)`), y ese día está TRUNCADO: el informe se descarga a media
-- jornada, así que su última fecha trae unas pocas líneas y las demás llegan
-- mañana. La ventana cuenta un día a medias como si fuera entero, y el sesgo va
-- SIEMPRE en la misma dirección: unidades de menos → velocidad baja → cobertura
-- optimista → se repone tarde.
--
-- 🔬 EL TESTIGO QUE LO CONFIRMÓ (Fernando, madrugada del 24-ago-2026). Al entrar
--    el ledger nuevo, el 20-ago pasó de 53 a 88 unidades de catálogo, y en el
--    ASIN B085DNDLC1 de 9 a 22 — mientras el 17, el 18 y el 19 quedaron
--    IDÉNTICOS (111, 94, 102). Que los tres días anteriores no se muevan ni una
--    unidad es lo que separa «día truncado» de «día flojo»: un día flojo no se
--    rellena después.
--
-- 🔬 Y EL TAMAÑO, medido el 23-ago-2026 sobre el ledger real (hasta el 23-ago,
--    con 34 líneas de Shipments en ese último día):
--        ventana   hoy     con el arreglo   diferencia
--        7 días    575  →  628              +9,2 %
--        30 días   2.669 → 2.729            +2,2 %
--        90 días   8.555 → 8.612            +0,7 %
--    **63 ASIN cambian su t30.** El sesgo es mayor cuanto más corta la ventana,
--    que es justo donde más duele: t7 es el número con el que se decide reponer.
--
-- QUÉ CAMBIA, y nada más que esto: cada ventana del LEDGER pasa de
--        fecha > hasta - N
--   a    fecha > hasta - (N+1)  AND  fecha < hasta
--   en las cuatro (7/30/60/90) y en la de devoluciones.
--
-- 🔒 LA VENTANA SIGUE MIDIENDO N DÍAS, y conviene verlo escrito porque es donde
--    se cuela el off-by-one: `> hasta-31 AND < hasta` son los días hasta-30 …
--    hasta-1, que son treinta. Por eso los DIVISORES de `vel_dia_30d` y
--    `vel_dia_90d` NO se tocan: siguen siendo 30 y 90. Cambiar uno sin el otro
--    convertiría un arreglo de sesgo en un error de escala.
--
-- 🔴 `mercado` NO SE TOCA, y no es un olvido: cuenta sobre
--    `transacciones_movimientos`, anclado a SU propio `hasta_trans`, y ese último
--    día sí viene completo. Meterle el mismo desplazamiento le quitaría un día
--    bueno. Dos fuentes, dos anclas, dos verdades distintas — y el testigo de
--    abajo comprueba que sus cifras no se han movido ni un euro.
--
-- ⚠️ LO QUE ESTE ARREGLO NO ALCANZA: si mañana el ledger se descargara DOS veces
--    el mismo día, o si el corte de Amazon se moviera de hora, el último día
--    seguiría siendo el sospechoso y este desplazamiento seguiría siendo el
--    correcto — pero si algún día el informe pasara a venir cerrado, esto estaría
--    tirando un día bueno. La forma de saberlo es la misma que lo destapó: mirar
--    si una fecha ya cargada cambia al recargar. No hay guarda automática para
--    eso todavía y no se finge que la haya.
--
-- 🔒 ALCANCE REAL, medido antes de escribir esto: de `v_ventas_ventanas` cuelga
--    UNA sola vista, `salud_fba`, que expone `uds_7d/30d/60d/90d` como
--    `units_shipped_t7/t30/t60/t90`. Y de ahí SÍ come la app: la pestaña
--    Inventario los pide por nombre en `lib/inventory/query.ts` (COLS_SALUD).
--    O sea que esto mueve números que se pintan, no sólo los del trackeador.
--    La pestaña **Enviar** no se entera: bebe de `v_velocidad_ventas_paneu`.
-- ============================================================================

SET lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 0) GUARDAS PREVIAS y FOTO DEL ANTES. No se cambia una vista sin saber de qué
--    se parte: el testigo final compara contra estas cifras, no contra una
--    expectativa escrita a mano.
-- ---------------------------------------------------------------------------
DO $$
DECLARE k char; n int;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.v_ventas_ventanas');
    IF k IS NULL OR k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: `v_ventas_ventanas` no existe o no es una vista (relkind=%).', k;
    END IF;
    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.salud_fba');
    IF k IS NULL OR k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba` no es una vista. Esta migración da por hecho que cuelga de aquí.';
    END IF;
    SELECT count(*) INTO n FROM public.v_ventas_ventanas;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: v_ventas_ventanas devuelve 0 filas. Sin entrada, cualquier testigo saldría verde sin medir nada.';
    END IF;
    RAISE NOTICE 'Guardas previas OK: v_ventas_ventanas es vista con % filas y salud_fba cuelga de ella.', n;
END $$;

CREATE TEMP TABLE _antes ON COMMIT DROP AS
SELECT count(*)                     AS filas,
       sum(uds_7d)                  AS t7,
       sum(uds_30d)                 AS t30,
       sum(uds_60d)                 AS t60,
       sum(uds_90d)                 AS t90,
       sum(devoluciones_30d)        AS devol,
       sum(uds_30d_marketplace)     AS mkt_uds,
       sum(eur_30d_marketplace)     AS mkt_eur
FROM public.v_ventas_ventanas;

-- ---------------------------------------------------------------------------
-- 1) LA VISTA, con las ventanas del ledger cerradas en el último día completo.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_ventas_ventanas
WITH (security_invoker = true) AS
WITH ancla AS (
    SELECT (SELECT max(fecha) FROM ledger_movimientos)        AS hasta_ledger,
           (SELECT max(fecha) FROM transacciones_movimientos) AS hasta_trans
), salidas AS (
    -- 24-ago-2026 · `AND l.fecha < a.hasta_ledger` en las cuatro: el último día
    -- cargado está a medias y contarlo entero baja la velocidad siempre.
    SELECT l.asin,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger -  8 AND l.fecha < a.hasta_ledger) AS uds_7d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 31 AND l.fecha < a.hasta_ledger) AS uds_30d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 61 AND l.fecha < a.hasta_ledger) AS uds_60d,
        sum(abs(l.quantity)) FILTER (WHERE l.fecha > a.hasta_ledger - 91 AND l.fecha < a.hasta_ledger) AS uds_90d
    FROM ledger_movimientos l CROSS JOIN ancla a
    WHERE l.event_type = 'Shipments' AND l.asin IS NOT NULL
      AND l.fecha > a.hasta_ledger - 91 AND l.fecha < a.hasta_ledger
    GROUP BY l.asin
), devueltas AS (
    SELECT l.asin, sum(abs(l.quantity)) AS devoluciones_30d
    FROM ledger_movimientos l CROSS JOIN ancla a
    WHERE l.event_type = 'CustomerReturns' AND l.asin IS NOT NULL
      AND l.fecha > a.hasta_ledger - 31 AND l.fecha < a.hasta_ledger
    GROUP BY l.asin
), sku_asin AS (
    SELECT DISTINCT ON (btrim(seller_sku)) btrim(seller_sku) AS sku, btrim(asin) AS asin
    FROM listings_amazon
    WHERE seller_sku IS NOT NULL AND asin IS NOT NULL AND btrim(asin) <> ''
    ORDER BY btrim(seller_sku), fecha_informe DESC
), mercado AS (
    -- 🔴 SIN TOCAR. Otra fuente, otra ancla, y su último día sí viene completo.
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
    -- Divisores INTACTOS: la ventana sigue midiendo 30 y 90 días (ver cabecera).
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
    -- ⚠️ MIDE CONTRA EL ÚLTIMO DÍA CARGADO, NO CONTRA EL ÚLTIMO DÍA USADO. Desde
    --    hoy los datos de las ventanas acaban en `hasta_ledger - 1`, así que esta
    --    columna diría «0 días» sobre cifras de ayer. NO se cambia porque su
    --    pregunta es otra —«¿cuánto lleva sin cargarse el ledger?»— y esa sigue
    --    contestándose contra el último día cargado. Se deja dicho aquí y en el
    --    COMMENT porque hoy no la lee nadie (`salud_fba`, su único dependiente, no
    --    la expone) y el día que alguien la pinte se va a creer el 0.
    CURRENT_DATE - a.hasta_ledger                  AS dias_desde_ultimo_dato
FROM salidas s
FULL JOIN mercado m  ON m.asin = s.asin
LEFT JOIN devueltas d ON d.asin = coalesce(s.asin, m.asin)
CROSS JOIN ancla a;

-- ---------------------------------------------------------------------------
-- 2) LOS COMENTARIOS. `ventana_hasta_ledger` ya NO es el último día de la
--    ventana, y eso hay que decirlo DONDE se consulta: la columna se queda con
--    su nombre y su valor (no se puede renombrar sin romper a quien la lee), y
--    el comentario deja escrito que la ventana acaba el día ANTERIOR.
-- ---------------------------------------------------------------------------
COMMENT ON VIEW public.v_ventas_ventanas IS
  'Las ventanas de venta por ASIN (7/30/60/90 dias) calculadas SIN Amazon. Nace el 23-ago-2026 '
  'porque salud_fba.units_shipped_* llega roto desde el 16-ago. uds_* = salida fisica del ledger '
  '(event Shipments, todos los mercados); uds_30d_es/it/fr = transacciones (unica fuente que sabe '
  'el marketplace, y solo tiene ES/IT/FR, por eso uds_30d_marketplace puede ser menor que uds_30d). '
  'Las ventanas se anclan al ultimo dia CARGADO de cada fuente, nunca a now(). '
  '24-ago-2026: las ventanas del LEDGER cierran en el ultimo dia COMPLETO (excluyen max(fecha), '
  'que llega truncado a media jornada); las de transacciones no, porque su ultimo dia si viene '
  'entero. Medido: el sesgo era de +9,2% en 7 dias y +2,2% en 30, siempre hacia velocidad baja.';

COMMENT ON COLUMN public.v_ventas_ventanas.ventana_hasta_ledger IS
  'Ultimo dia CARGADO del ledger. OJO: desde el 24-ago-2026 NO es el ultimo dia de la ventana — '
  'las ventanas del ledger acaban el dia ANTERIOR a este, porque este llega truncado. Para saber '
  'hasta cuando cuentan de verdad: ventana_hasta_ledger - 1.';

COMMENT ON COLUMN public.v_ventas_ventanas.dias_desde_ultimo_dato IS
  'Dias desde el ultimo dia CARGADO del ledger: contesta «cuanto lleva sin cargarse», no «que '
  'antiguedad tienen las cifras». OJO si algun dia se pinta: desde el 24-ago-2026 las ventanas '
  'acaban en ventana_hasta_ledger - 1, asi que un 0 aqui significa cifras de AYER, no de hoy.';

COMMENT ON COLUMN public.v_ventas_ventanas.ventana_hasta_marketplace IS
  'Ultimo dia cargado de transacciones, y SI es el ultimo dia de las ventanas de marketplace: esa '
  'fuente llega con el dia cerrado.';

-- ---------------------------------------------------------------------------
-- 3) PERMISOS. `CREATE OR REPLACE` conserva el ACL, pero se re-afirma y se MIDE:
--    suponerlo es justo lo que §4 prohibe.
-- ---------------------------------------------------------------------------
REVOKE ALL ON public.v_ventas_ventanas FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_ventas_ventanas TO authenticated;

-- ---------------------------------------------------------------------------
-- 4) TESTIGOS. La prueba fuerte no es «el número ha subido» —eso podria ser
--    cualquier cosa— sino que la vista devuelve EXACTAMENTE lo que devuelve un
--    recuento independiente de la ventana que se queria. Dos caminos, un numero.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_t7 bigint; v_t30 bigint; v_t90 bigint; v_dev bigint;
    e_t7 bigint; e_t30 bigint; e_t90 bigint; e_dev bigint;
    a_t7 bigint; a_t30 bigint; a_mkt bigint; a_eur numeric; a_filas int; dev_fuera bigint;
    n_filas int; n_mkt bigint; n_eur numeric; ultimo date; ultimo_completo date;
BEGIN
    SELECT filas, t7, t30, mkt_uds, mkt_eur INTO a_filas, a_t7, a_t30, a_mkt, a_eur FROM _antes;

    SELECT count(*), sum(uds_7d), sum(uds_30d), sum(uds_90d), sum(devoluciones_30d),
           sum(uds_30d_marketplace), sum(eur_30d_marketplace)
      INTO n_filas, v_t7, v_t30, v_t90, v_dev, n_mkt, n_eur
      FROM public.v_ventas_ventanas;

    SELECT max(fecha) INTO ultimo FROM ledger_movimientos;
    SELECT max(fecha) INTO ultimo_completo FROM ledger_movimientos WHERE fecha < ultimo;

    -- 🔴 EL RECUENTO INDEPENDIENTE. Escrito aparte y a mano, no reutilizando la
    --    vista: si los dos caminos se escribieran una sola vez, el testigo
    --    estaria comparando la vista consigo misma.
    SELECT
        coalesce(sum(abs(quantity)) FILTER (WHERE event_type='Shipments' AND fecha > ultimo -  8 AND fecha < ultimo), 0),
        coalesce(sum(abs(quantity)) FILTER (WHERE event_type='Shipments' AND fecha > ultimo - 31 AND fecha < ultimo), 0),
        coalesce(sum(abs(quantity)) FILTER (WHERE event_type='Shipments' AND fecha > ultimo - 91 AND fecha < ultimo), 0)
      INTO e_t7, e_t30, e_t90
      FROM ledger_movimientos WHERE asin IS NOT NULL;

    IF v_t7 <> e_t7 OR v_t30 <> e_t30 OR v_t90 <> e_t90 THEN
        RAISE EXCEPTION 'ABORTA: la vista y el recuento independiente NO cuadran. vista 7/30/90 = %/%/% · recuento = %/%/%',
            v_t7, v_t30, v_t90, e_t7, e_t30, e_t90;
    END IF;

    -- 🔴 LAS DEVOLUCIONES SE COMPARAN CON EL MISMO ALCANCE, y esto no es hacer
    --    trampa: `devueltas` entra por LEFT JOIN, así que una devolución de un
    --    ASIN que NO tenga salidas en 90 días NI fila de marketplace no aparece
    --    en la vista — con este arreglo o sin él. Comparar el total crudo contra
    --    la vista sería una guarda que se pone roja por una causa que no tiene
    --    nada que ver con la migración, o sea ruido futuro (§3).
    --    🔬 Medido el 24-ago-2026: 32 ASIN con devolución, **0 huérfanas**. Hoy
    --       daría igual; el día que no dé igual, esto seguiría midiendo lo suyo.
    SELECT coalesce(sum(x.uds), 0),
           coalesce(sum(x.uds) FILTER (WHERE NOT EXISTS (SELECT 1 FROM public.v_ventas_ventanas v WHERE v.asin = x.asin)), 0)
      INTO e_dev, dev_fuera
      FROM (
        SELECT l.asin, sum(abs(l.quantity)) AS uds
          FROM ledger_movimientos l
         WHERE l.event_type = 'CustomerReturns' AND l.asin IS NOT NULL
           AND l.fecha > ultimo - 31 AND l.fecha < ultimo
         GROUP BY l.asin
      ) x;

    IF v_dev <> e_dev - dev_fuera THEN
        RAISE EXCEPTION 'ABORTA: las devoluciones no cuadran. vista=% · recuento dentro de la vista=% (total % con % fuera).',
            v_dev, e_dev - dev_fuera, e_dev, dev_fuera;
    END IF;

    -- El marketplace NO se ha movido: misma fuente, misma ancla, mismas cifras.
    IF n_mkt <> a_mkt OR n_eur <> a_eur THEN
        RAISE EXCEPTION 'ABORTA: las cifras de marketplace han cambiado (% -> % uds, % -> % EUR). Esta migracion no debia tocarlas.',
            a_mkt, n_mkt, a_eur, n_eur;
    END IF;

    -- 🔴 LAS FILAS PUEDEN BAJAR LEGITIMAMENTE, y por eso esto AVISA en vez de
    --    abortar: un ASIN cuya UNICA salida en 90 dias cayera en el dia truncado
    --    sale de `salidas` y, si tampoco tiene fila de marketplace, desaparece de
    --    la vista. Eso no es un fallo del arreglo: es el arreglo. Abortar por ahi
    --    seria una guarda que se pone roja por su propio efecto.
    --    🔬 Medido el 24-ago-2026: 292 ASIN con salidas antes y 292 despues, 0 se
    --       caen. Hoy no pasa; el dia que pase, se lee en el log y no bloquea.
    --    ⚠️ Lo que si aborta es un DERRUMBE, que ya no seria este efecto sino otra
    --       cosa: el mismo 50% de la guarda anti-encogimiento de las tablas-foto.
    IF n_filas < a_filas / 2 THEN
        RAISE EXCEPTION 'ABORTA: la vista ha pasado de % a % filas. Eso no lo explica un dia menos de ventana.', a_filas, n_filas;
    END IF;
    IF n_filas <> a_filas THEN
        RAISE NOTICE 'AVISO: la vista pasa de % a % filas. Es el efecto esperado si algun ASIN solo tenia salidas en el dia truncado; miralo si el numero es grande.', a_filas, n_filas;
    END IF;

    IF has_table_privilege('anon', 'public.v_ventas_ventanas', 'SELECT') THEN
        RAISE EXCEPTION 'ABORTA: `anon` puede leer v_ventas_ventanas.';
    END IF;
    IF NOT has_table_privilege('authenticated', 'public.v_ventas_ventanas', 'SELECT') THEN
        RAISE EXCEPTION 'ABORTA: `authenticated` NO puede leer v_ventas_ventanas: la app se quedaria sin ventas.';
    END IF;

    RAISE NOTICE 'Ventanas cerradas en el ultimo dia completo: ledger cargado hasta % , ventanas hasta %.', ultimo, ultimo_completo;
    RAISE NOTICE 'Vista == recuento independiente: 7d=% · 30d=% · 90d=% · devoluciones=%.', v_t7, v_t30, v_t90, v_dev;
    RAISE NOTICE 'Movimiento respecto al ANTES: 7d % -> % · 30d % -> %.', a_t7, v_t7, a_t30, v_t30;
    RAISE NOTICE 'INTACTO el marketplace: % uds y % EUR, iguales que antes. Filas % -> %.', n_mkt, n_eur, a_filas, n_filas;
END $$;
