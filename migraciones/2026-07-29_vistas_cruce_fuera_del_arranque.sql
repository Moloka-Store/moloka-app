-- ============================================================================
-- MIGRACIÓN 2026-07-29 · Las vistas de cruce SALEN del arranque de los procesadores
-- ----------------------------------------------------------------------------
-- POR QUÉ. El 28-jul a las 15:47 la app se cayó ("Could not query the database for
-- the schema cache"). Causa: los 3 workflows arrancaron casi a la vez y cada
-- procesador RECREABA su vista al arrancar (keepa hacía DROP VIEW; CREATE VIEW).
-- Eso pide AccessExclusiveLock sobre una vista que cuelga de productos/salud_fba/
-- keepa_escaparate/listings_amazon → bloquea media base, y la v1 de Elena corre
-- sobre esa misma base. Recrear una vista en CADA carga es una migración disfrazada
-- de arranque.
--
-- QUÉ HACE. Deja las tres vistas definidas UNA vez, idempotente (CREATE OR REPLACE /
-- DROP+CREATE). A partir de aquí, los procesadores NO las recrean: solo comprueban
-- que existen (y abortan pidiendo esta migración si no). Cambiar una definición = una
-- migración nueva, no tocar el arranque.
--
-- 🔒 security_invoker se conserva TAL CUAL venía de cada procesador (la vista corre con
--    los permisos de quien la consulta, no del creador). Extraído VERBATIM del código
--    que ya corría en producción: el SQL es idéntico, solo cambia CUÁNDO se ejecuta.
-- ============================================================================

-- === v_keepa_cruce (de procesador_keepa_escaparate.py; {NUESTRO_SELLER_ID} resuelto) ===
DROP VIEW IF EXISTS v_keepa_cruce;
CREATE VIEW v_keepa_cruce
WITH (security_invoker = true) AS
SELECT
    'escaparate'::text AS origen,
    k.asin,
    k.dominio,
    k.titulo,
    k.tarifa_fba,
    k.bb_vendedor,
    k.bb_seller_id,
    -- §5.1 el EAN de la ficha NO aparece entre los que Keepa da para ese ASIN.
    -- Ambos lados por moloka_ean_norm(): solo dígitos, sin ceros a la izquierda.
    ( EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND moloka_ean_norm(p.ean) IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND moloka_ean_norm(p.ean) IN (
              SELECT moloka_ean_norm(e)
              FROM unnest(string_to_array(coalesce(k.ean_keepa_crudo, ''), ',')) AS e
              WHERE moloka_ean_norm(e) IS NOT NULL)) )
      AS ean_no_confirmado,
    -- §5.2 keepa_fba_fee del dominio != tarifa_fba del CSV (tolerancia 0,01 €).
    -- NULL fuera de es/fr/it: productos NO tiene keepa_fba_fee_de, así que en DE
    -- no hay nada que comparar y un `false` ahí sería un "cuadra" inventado.
    CASE WHEN k.dominio IN ('es', 'fr', 'it') THEN
      EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND k.tarifa_fba IS NOT NULL
          AND (CASE k.dominio WHEN 'es' THEN p.keepa_fba_fee_es
                              WHEN 'it' THEN p.keepa_fba_fee_it
                              WHEN 'fr' THEN p.keepa_fba_fee_fr END) IS NOT NULL
          AND abs((CASE k.dominio WHEN 'es' THEN p.keepa_fba_fee_es
                                  WHEN 'it' THEN p.keepa_fba_fee_it
                                  WHEN 'fr' THEN p.keepa_fba_fee_fr END) - k.tarifa_fba) > 0.01)
    END AS tarifa_discrepante,
    -- §5.3 ficha activa sin keepa_image y el CSV trae imágenes
    ( EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND coalesce(btrim(p.keepa_image), '') = '')
      AND coalesce(array_length(k.imagenes, 1), 0) > 0 )
      AS sin_foto_curable,
    -- §5.4 stock FBA propio en ese país y la buy box NO es nuestra (por SELLER ID).
    -- NULL donde salud_fba no cubra ese país: sin saber si tenemos stock allí, la
    -- pregunta "¿me están quitando la buy box teniendo yo stock?" no se puede
    -- contestar, y un `false` sería decir que no pasa nada sin haber mirado.
    -- La condición se deriva de salud_fba: el día que traiga IT, se enciende sola.
    CASE WHEN EXISTS (SELECT 1 FROM salud_fba s
                      WHERE upper(s.marketplace) = upper(k.dominio)) THEN
      ( EXISTS (SELECT 1 FROM salud_fba s
          WHERE btrim(s.asin) = btrim(k.asin)
            AND upper(s.marketplace) = upper(k.dominio)
            AND coalesce(s.available, 0) > 0)
        AND k.bb_seller_id IS NOT NULL
        AND k.bb_seller_id <> 'A2R25VOCZPEH8K' )
    END AS buybox_ajena_con_stock,
    -- §5.5 no aplica a filas del escaparate: NULL, no false (§tres estados)
    NULL::boolean AS activo_sin_export
FROM keepa_escaparate k

UNION ALL

-- §5.5 ASIN 'Active' en listings_amazon que NO aparece en el export (la red del reverso).
-- El dominio es 'es' EXPLÍCITO, no NULL: listings_amazon no tiene columna de país
-- porque ES el listado de ES. Decirlo permite desglosar el log por dominio sin un
-- cajón "sin país" que en realidad sí tiene país.
SELECT
    'listing_sin_export'::text AS origen,
    l.asin,
    'es'::text    AS dominio,
    l.item_name   AS titulo,
    NULL::numeric AS tarifa_fba,
    NULL::text    AS bb_vendedor,
    NULL::text    AS bb_seller_id,
    NULL::boolean AS ean_no_confirmado,
    NULL::boolean AS tarifa_discrepante,
    NULL::boolean AS sin_foto_curable,
    NULL::boolean AS buybox_ajena_con_stock,
    true          AS activo_sin_export
FROM (
    SELECT btrim(asin) AS asin, max(item_name) AS item_name
    FROM listings_amazon
    WHERE status = 'Active' AND asin IS NOT NULL AND btrim(asin) <> ''
    GROUP BY btrim(asin)
) l
-- 🔒 ACOTADO A dominio='es'. Sin esto, un ASIN que falta del export de ES pero
-- aparece en el de IT/FR/DE se escapaba de la alerta: la pregunta es "¿falta del
-- export DE SU PAÍS?", no "¿existe en algún sitio?".
WHERE NOT EXISTS (SELECT 1 FROM keepa_escaparate k
                  WHERE btrim(k.asin) = l.asin AND k.dominio = 'es');

-- === v_salud_fba_cruce (de procesador_salud_fba.py) ===
CREATE OR REPLACE VIEW v_salud_fba_cruce
WITH (security_invoker = true) AS
SELECT
    s.asin,
    s.marketplace,
    s.sku,
    s.product_name,
    s.available,
    (SELECT count(*) FROM productos p
       WHERE p.activo AND btrim(p.asin) = btrim(s.asin)) AS fichas_activas,
    NOT EXISTS (SELECT 1 FROM productos p
       WHERE p.activo AND btrim(p.asin) = btrim(s.asin)) AS sin_ficha,
    (EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(s.asin))
     AND NOT EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(s.asin)
          AND btrim(p.sku) = btrim(s.sku))) AS sku_discrepante,
    -- ▼▼ Añadido para Dos Vidas (§4.3). ADITIVO: `sku_discrepante` queda EXACTO.
    --    (Semántica derivada de los nombres que pidió el trackeador; a confirmar.)
    -- Cuántas vidas (SKU vivos) tiene este (asin, marketplace) en la foto.
    (SELECT count(*) FROM salud_fba s2
       WHERE btrim(s2.asin) = btrim(s.asin) AND s2.marketplace = s.marketplace) AS n_skus_vivos,
    -- Este SKU concreto del informe no está en NINGUNA ficha activa con ese ASIN.
    NOT EXISTS (SELECT 1 FROM productos p
       WHERE p.activo AND btrim(p.asin) = btrim(s.asin)
         AND btrim(p.sku) = btrim(s.sku)) AS sku_sin_ficha,
    -- Hay ficha activa para el ASIN pero NINGUNA de sus vidas del informe casa con
    -- un SKU fichado (la lectura "revisada" de discrepante: no es este SKU, es que
    -- no casa ninguno). Con esto, un ASIN de una sola vida fichada NO sale marcado.
    (EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(s.asin))
     AND NOT EXISTS (SELECT 1 FROM salud_fba s2
        JOIN productos p ON p.activo AND btrim(p.asin) = btrim(s2.asin)
                        AND btrim(p.sku) = btrim(s2.sku)
        WHERE btrim(s2.asin) = btrim(s.asin) AND s2.marketplace = s.marketplace))
       AS asin_sin_ningun_sku_fichado
FROM salud_fba s;

-- === v_canal_amazon_es (de procesador_canal_amazon_es.py) ===
CREATE OR REPLACE VIEW v_canal_amazon_es
WITH (security_invoker = true) AS
WITH prod AS (
    SELECT DISTINCT ON (sku) sku, id AS producto_id, ean
    FROM productos WHERE sku IS NOT NULL
    ORDER BY sku, (activo IS TRUE) DESC, id DESC
),
ventas AS (
    SELECT t.sku, t.fecha, t.fecha_hora, t.id,
        (t.ventas_producto + t.impuesto_producto) / t.cantidad AS precio_ud,
        CASE WHEN t.tarifa_fba <> 0
             THEN (-t.tarifa_fba / 1.21 / t.cantidad) END AS fba_ud,
        CASE WHEN (t.ventas_producto + t.impuesto_producto) > 0 AND t.tarifa_venta <> 0
             THEN (-t.tarifa_venta / 1.21) / (t.ventas_producto + t.impuesto_producto) * 100 END AS com_pct
    FROM transacciones_movimientos t
    WHERE t.pais = 'ES' AND t.cantidad > 0 AND t.ventas_producto > 0
      AND t.sku IS NOT NULL AND t.sku <> ''
),
precio AS (
    SELECT DISTINCT ON (sku) sku, round(precio_ud, 2) AS precio_venta
    FROM ventas ORDER BY sku, fecha DESC, fecha_hora DESC NULLS LAST, id DESC
),
com10 AS (
    SELECT sku, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY com_pct)::numeric, 2) AS comision_pct
    FROM (SELECT sku, com_pct,
                 row_number() OVER (PARTITION BY sku ORDER BY fecha DESC, fecha_hora DESC NULLS LAST, id DESC) rn
          FROM ventas WHERE com_pct IS NOT NULL) x
    WHERE rn <= 10 GROUP BY sku
),
fba10 AS (
    SELECT sku, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fba_ud)::numeric, 2) AS envio
    FROM (SELECT sku, fba_ud,
                 row_number() OVER (PARTITION BY sku ORDER BY fecha DESC, fecha_hora DESC NULLS LAST, id DESC) rn
          FROM ventas WHERE fba_ud IS NOT NULL) x
    WHERE rn <= 10 GROUP BY sku
),
skus AS (SELECT DISTINCT sku FROM ventas)
SELECT
    'amazon_es'::text AS canal,
    s.sku             AS item_id_canal,
    pr.producto_id,
    pr.ean,
    pe.precio_venta,
    c.comision_pct,
    21::numeric       AS iva_pct,
    f.envio,
    true              AS activo
FROM skus s
JOIN prod pr ON pr.sku = s.sku          -- solo SKUs CON ficha (huérfanos fuera)
LEFT JOIN precio pe ON pe.sku = s.sku
LEFT JOIN com10 c  ON c.sku  = s.sku
LEFT JOIN fba10 f  ON f.sku  = s.sku;
