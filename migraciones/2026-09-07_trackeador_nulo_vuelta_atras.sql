-- ============================================================================
-- VUELTA ATRÁS de `2026-09-07_trackeador_el_nulo_no_es_cero.sql`.  7-sep-2026
-- ----------------------------------------------------------------------------
-- 🔴 PARA QUÉ EXISTE Y CUÁNDO SE LANZA. Un solo motivo: **que Elena deje de ver
--   filas en el Trackeador** después de aplicar el paso 2b. Si eso pasa, esto se
--   lanza SIN CONSULTAR A NADIE: primero se devuelve la pantalla, luego se
--   investiga. Un almacén parado cuesta más que una hora de diagnóstico.
--
-- 🔑 QUÉ DESHACE: los ocho cambios del 2b, y nada más.
--     · Vuelven los dos `COALESCE(..., 0)` que tapaban el nulo del tránsito.
--     · Vuelven las seis decisiones a leer `stock_fba_eu` directo, sin el suelo.
--   Con eso la vista queda EXACTAMENTE como estaba antes del 2b, texto incluido.
--
-- 🔒 CÓMO SE ESCRIBIÓ, que importa para poder fiarse de ella: **no se ha vuelto a
--   copiar la vista a mano**. Este fichero se generó invirtiendo los ocho cambios
--   sobre el del 2b con un script, así que el resto del texto —las 1.237 líneas de
--   arrastre de columnas— es bit a bit el mismo que ya estaba en producción. Una
--   vuelta atrás transcrita a mano puede traer su propio error, y entonces no es
--   una vuelta atrás: es un tercer estado.
--
-- 🔴 NO TOCA `mv_trackeador_pantalla` (no hace falta: el 2b tampoco la tocó, y
--   recrear una materializada la deja VACÍA sin dar error), ni `security_invoker`,
--   ni los permisos, ni la Guarda 12 del procesador.
--
--
-- 🔬 COMPROBADO: el texto de la vista que deja este fichero es **idéntico** al que
--   producción devolvía antes del 2b — longitud 46.179 caracteres, md5
--   944763a901b1931faff1f0e131b07ace. No es «parecido»: es el mismo.
--
-- 🔴 `CREATE OR REPLACE VIEW` **BORRA LAS OPCIONES DE LA VISTA**, `security_invoker`
--   incluido. No es una suposición: lo cazó el número de control de este mismo
--   fichero en el ensayo de staging el 7-sep-2026, con `reloptions: (sin opciones)`
--   después del REPLACE. Por eso hay un `ALTER VIEW ... SET (security_invoker=true)`
--   justo detrás, y por eso la guarda lo comprueba.
--   ⚠️ Sin esa guarda, la vista habría vuelto a leer con los permisos de su dueño
--   (`postgres`) saltándose la RLS, en silencio y sin que nada fallara. Una opción
--   de seguridad que se pierde no da error: deja de proteger.
--
-- PROBADA EN STAGING el 7-sep-2026 con la secuencia completa: aplicar el 2b →
--   lanzar esto → comprobar por SQL que la vista vuelve a su texto de partida.
-- ============================================================================

-- ── 0) LA FOTO DEL «ANTES» ──────────────────────────────────────────────────
-- 🔴 AQUÍ TAMBIÉN HABÍA CIFRAS DE PRODUCCIÓN A PELO, y por tercera vez el mismo
--    error: la escalera pasa por STAGING primero, donde la vista devuelve 1.708
--    filas y no 1.776, así que la guarda abortaba por una diferencia de entornos.
--    Lo que hay que exigir no es un número: es que **la vuelta atrás no mueva
--    ningún dato**. Hoy el tránsito se conoce en todas las fichas, luego revertir
--    tiene que dejar exactamente las mismas cifras, sean las que sean aquí.
CREATE TEMP TABLE _pantalla_antes ON COMMIT DROP AS
SELECT count(*) AS filas,
       md5(string_agg(t::text, E'
' ORDER BY t.asin, t.dominio)) AS huella,
       sum(t.stock_fba_eu) AS suma_stock_fba_eu
  FROM public.v_trackeador_pantalla t;

CREATE OR REPLACE VIEW public.v_trackeador_pantalla AS
 WITH ven_pais AS (
         SELECT COALESCE(p.asin, l.asin) AS asin,
            lower(t.pais) AS dominio,
            sum(t.cantidad) FILTER (WHERE t.fecha >= ((( SELECT max(transacciones_movimientos.fecha) AS max
                   FROM transacciones_movimientos)) - 29)) AS t30,
            sum(t.cantidad) FILTER (WHERE t.fecha >= ((( SELECT max(transacciones_movimientos.fecha) AS max
                   FROM transacciones_movimientos)) - 6)) AS t7
           FROM transacciones_movimientos t
             LEFT JOIN productos p ON p.sku = t.sku
             LEFT JOIN listings_amazon l ON l.seller_sku = t.sku
          WHERE t.tipo_norm = 'pedido'::text AND t.cantidad > 0
          GROUP BY (COALESCE(p.asin, l.asin)), (lower(t.pais))
        ), ven_glob AS (
         SELECT ven_pais.asin,
            sum(ven_pais.t30) AS t30_global
           FROM ven_pais
          GROUP BY ven_pais.asin
        ), repo AS (
         SELECT e.ean,
            min(escaner_pa_unitario(e.pa, e.es_case, e.proveedor)) FILTER (WHERE e.presente) AS repone_pvp,
            (array_agg(e.proveedor ORDER BY e.fecha DESC) FILTER (WHERE e.presente))[1] AS repone_proveedor,
            max(e.fecha) FILTER (WHERE e.presente)::date AS repone_leido_el
           FROM escaner_memoria e
          WHERE e.proveedor <> 'MOLOKA'::text
          GROUP BY e.ean
        ), compra AS (
         SELECT DISTINCT ON (p.asin) p.asin,
            c.precio_unitario,
            c.fecha AS compre_el
           FROM compras c
             JOIN productos p ON p.id = c.producto_id
          WHERE c.precio_unitario IS NOT NULL AND p.asin IS NOT NULL
          ORDER BY p.asin, c.fecha DESC, c.id DESC
        ), alm AS (
         SELECT p.asin,
            sum(COALESCE(( SELECT sum(v.value::numeric) AS sum
                   FROM jsonb_each_text(p.ubicaciones_cant) v(key, value)
                  WHERE v.key <> 'Miravia'::text), 0::numeric)) AS stock_moloka
           FROM productos p
          WHERE p.asin IS NOT NULL
          GROUP BY p.asin
        ), esc AS (
         SELECT k_1.asin,
            lower(k_1.dominio) AS dominio,
            k_1.bb_es_fba,
            k_1.rank_drops_30d,
            k_1.rank_drops_90d
           FROM keepa_escaparate k_1
        ), bloq AS (
         SELECT COALESCE(l.asin, pr.asin) AS asin,
            lower(o.pais) AS dominio,
            (array_agg(o.motivo_bloqueo ORDER BY o.motivo_bloqueo) FILTER (WHERE o.motivo_bloqueo IS NOT NULL))[1] AS motivo_bloqueo
           FROM paneu_oferta_pais o
             LEFT JOIN listings_amazon l ON l.seller_sku = o.seller_sku
             LEFT JOIN productos pr ON pr.sku = o.seller_sku
          WHERE o.snapshot_date = (( SELECT max(paneu_oferta_pais.snapshot_date) AS max
                   FROM paneu_oferta_pais)) AND NOT COALESCE(o.tiene_oferta, false)
          GROUP BY (COALESCE(l.asin, pr.asin)), (lower(o.pais))
        ), stock_fba AS (
         SELECT i.asin,
            sum(COALESCE(i.available, 0)) AS uds_vendibles,
            sum(COALESCE(i.fc_transfer, 0)) AS uds_fc_transfer,
            sum(COALESCE(i.inbound_working, 0) + COALESCE(i.inbound_shipped, 0) + COALESCE(i.inbound_receiving, 0)) AS uds_en_camino,
            sum(COALESCE(i.total_reserved_quantity, 0)) AS uds_reservadas,
            sum(COALESCE(i.unfulfillable_quantity, 0)) AS uds_inservibles,
            sum(COALESCE(NULLIF(i.crudo ->> 'afn-researching-quantity'::text, ''::text)::integer, 0)) AS uds_investigando
           FROM inventario_fba i
          WHERE i.fecha_foto = (( SELECT max(inventario_fba.fecha_foto) AS max
                   FROM inventario_fba)) AND i.asin IS NOT NULL
          GROUP BY i.asin
        ), intl_fuera AS (
         SELECT ii.asin,
            sum(ii.quantity) AS uds
           FROM inventario_internacional ii
          WHERE ii.fecha_foto = (( SELECT max(inventario_internacional.fecha_foto) AS max
                   FROM inventario_internacional)) AND (lower(ii.country) <> ALL (ARRAY['es'::text, 'it'::text, 'fr'::text, 'de'::text]))
          GROUP BY ii.asin
        ), base AS (
         SELECT n.asin,
            n.ean,
            n.dominio,
            n.nombre,
            n.pais_operativo,
            n.bb_precio,
            n.bb_vendedor,
            n.bb_seller_id,
            n.bb_es_mio,
            n.bb_stock,
            n.bb_pct_amazon_30d,
            n.fba_min,
            n.ofertas_nuevas_fba,
            n.umbral_competitivo,
            n.amazon_precio,
            n.mi_precio,
            n.margen_hoy,
            n.margen_al_bb,
            n.eur_ud_al_bb,
            n.break_even,
            n.fee,
            n.fee_origen,
            n.comision_pct,
            n.iva_pais,
            n.isd_regla,
            n.almacenamiento_eur,
            n.almacenamiento_origen,
            n.pvd,
            n.pvd_sospechoso,
            n.t7_es,
            n.t30_es,
            n.disponible_es,
            n.cobertura_dias_es,
            n.saldo_uds_pais,
            n.visitas,
            n.sesiones,
            n.conversion_pct,
            n.ratio_oferta_destacada,
            n.veredicto,
            n.motivo_sin_datos,
            n.foto_keepa_el,
            n.demanda_leida_el,
            n.fee_riesgo_acantilado,
            n.categoria,
            n.stock_pais_uds,
            n.tengo_oferta_pais,
            n.sin_listing_pais,
            n.mi_precio_pais,
            n.presencia,
            n.stock_leido_el,
            n.oferta_leida_el,
            COALESCE(vp.t30, 0::bigint) AS vendo_30d,
            COALESCE(vp.t7, 0::bigint) AS vendo_7d,
            COALESCE(vg.t30_global, 0::numeric) AS vendo_30d_global,
            sum(COALESCE(n.stock_pais_uds, 0::bigint)) OVER (PARTITION BY n.asin) AS stock_fba_eu_raw,
            max(COALESCE(n.disponible_es, 0::bigint)) OVER (PARTITION BY n.asin) AS disp_es_max,
            COALESCE(a.stock_moloka, 0::numeric) AS stock_moloka,
            r.repone_pvp,
            r.repone_proveedor,
            r.repone_leido_el,
            c.precio_unitario AS compre_a,
            c.compre_el,
            c.compre_el AS coste_leido_el,
                CASE
                    WHEN c.compre_el IS NULL THEN NULL::date
                    ELSE LEAST(n.foto_keepa_el, c.compre_el)
                END AS margen_datado_el,
                CASE
                    WHEN c.compre_el IS NULL THEN 'sin_compra'::text
                    WHEN round(n.pvd, 2) = round(c.precio_unitario, 2) THEN 'compra'::text
                    ELSE 'ficha_a_mano'::text
                END AS coste_origen,
            e.bb_es_fba,
            e.rank_drops_30d,
            e.rank_drops_90d,
            bq.motivo_bloqueo AS motivo_bloqueo_paneu,
            COALESCE(sf.uds_vendibles, 0::bigint) AS stock_vendible,
            COALESCE(sf.uds_fc_transfer, 0::bigint) AS stock_fc_transfer,
            COALESCE(sf.uds_en_camino, 0::bigint) AS stock_en_camino,
            COALESCE(sf.uds_reservadas, 0::bigint) AS stock_reservado,
            COALESCE(sf.uds_inservibles, 0::bigint) AS stock_inservible,
            COALESCE(sf.uds_investigando, 0::bigint) AS stock_investigando,
            COALESCE(ifu.uds, 0::bigint) AS stock_fuera_de_dominio,
            bool_or(lower(translate(COALESCE(n.categoria, ''::text), 'áéíóúàèìòùâêîôûäëïöüãõçñÁÉÍÓÚÄÖÜÑ'::text, 'aeiouaeiouaeiouaeiouaocnAEIOUAOUN'::text)) ~ '(salud|salute|sante|hygiene|drogerie|korperpflege|beaut|belle|bellezz|alimenta|epicerie|lebensmittel|getrank|cura della persona|grocery)'::text) OVER (PARTITION BY n.asin) AS es_consumible
           FROM v_trackeador_precio_pais_full n
             LEFT JOIN ven_pais vp ON vp.asin = n.asin AND vp.dominio = n.dominio
             LEFT JOIN ven_glob vg ON vg.asin = n.asin
             LEFT JOIN repo r ON r.ean = n.ean
             LEFT JOIN compra c ON c.asin = n.asin
             LEFT JOIN alm a ON a.asin = n.asin
             LEFT JOIN esc e ON e.asin = n.asin AND e.dominio = n.dominio
             LEFT JOIN bloq bq ON bq.asin = n.asin AND bq.dominio = n.dominio
             LEFT JOIN stock_fba sf ON sf.asin = n.asin
             LEFT JOIN intl_fuera ifu ON ifu.asin = n.asin
        ), calc AS (
         SELECT b.asin,
            b.ean,
            b.dominio,
            b.nombre,
            b.pais_operativo,
            b.bb_precio,
            b.bb_vendedor,
            b.bb_seller_id,
            b.bb_es_mio,
            b.bb_stock,
            b.bb_pct_amazon_30d,
            b.fba_min,
            b.ofertas_nuevas_fba,
            b.umbral_competitivo,
            b.amazon_precio,
            b.mi_precio,
            b.margen_hoy,
            b.margen_al_bb,
            b.eur_ud_al_bb,
            b.break_even,
            b.fee,
            b.fee_origen,
            b.comision_pct,
            b.iva_pais,
            b.isd_regla,
            b.almacenamiento_eur,
            b.almacenamiento_origen,
            b.pvd,
            b.pvd_sospechoso,
            b.t7_es,
            b.t30_es,
            b.disponible_es,
            b.cobertura_dias_es,
            b.saldo_uds_pais,
            b.visitas,
            b.sesiones,
            b.conversion_pct,
            b.ratio_oferta_destacada,
            b.veredicto,
            b.motivo_sin_datos,
            b.foto_keepa_el,
            b.demanda_leida_el,
            b.fee_riesgo_acantilado,
            b.categoria,
            b.stock_pais_uds,
            b.tengo_oferta_pais,
            b.sin_listing_pais,
            b.mi_precio_pais,
            b.presencia,
            b.stock_leido_el,
            b.oferta_leida_el,
            b.vendo_30d,
            b.vendo_7d,
            b.vendo_30d_global,
            b.stock_fba_eu_raw,
            b.disp_es_max,
            b.stock_moloka,
            b.repone_pvp,
            b.repone_proveedor,
            b.repone_leido_el,
            b.compre_a,
            b.compre_el,
            b.coste_leido_el,
            b.margen_datado_el,
            b.coste_origen,
            b.bb_es_fba,
            b.rank_drops_30d,
            b.rank_drops_90d,
            b.motivo_bloqueo_paneu,
            b.stock_vendible,
            b.stock_fc_transfer,
            b.stock_en_camino,
            b.stock_reservado,
            b.stock_inservible,
            b.stock_investigando,
            b.stock_fuera_de_dominio,
            b.es_consumible,
            (b.stock_vendible + b.stock_fc_transfer)::numeric AS stock_fba_eu,
            (b.presencia = ANY (ARRAY['NI_LISTING'::text, 'SIN_OFERTA'::text, 'SIN_PAGINA'::text])) AND COALESCE(b.vendo_30d, 0::bigint) = 0 AND NOT COALESCE(b.bb_es_mio, false) AND NOT (b.dominio = 'es'::text AND b.motivo_bloqueo_paneu IS NOT NULL AND NOT COALESCE(b.sin_listing_pais, true)) AS es_no_estas,
                CASE
                    WHEN b.repone_pvp IS NOT NULL AND b.pvd > 0::numeric THEN round((b.repone_pvp - b.pvd) / b.pvd * 100::numeric)
                    ELSE NULL::numeric
                END AS repone_vs_coste_pct,
                CASE
                    WHEN COALESCE(b.vendo_30d, 0::bigint) > 0 THEN round((b.vendo_7d::numeric / 7::numeric * 30::numeric - b.vendo_30d::numeric) / b.vendo_30d::numeric * 100::numeric)
                    ELSE NULL::numeric
                END AS caida_pct,
                CASE
                    WHEN b.bb_precio IS NOT NULL AND b.bb_precio > 0.01 THEN round(((b.bb_precio - 0.01) / (1::numeric + b.iva_pais) - b.pvd - fn_fee_escalon_20(b.dominio, b.fee, b.bb_precio - 0.01) - (b.bb_precio - 0.01) * (b.comision_pct / 100::numeric) *
                    CASE
                        WHEN b.isd_regla ~~ 'com%'::text THEN 1.03
                        ELSE 1.00
                    END - fn_fee_escalon_20(b.dominio, b.fee, b.bb_precio - 0.01) *
                    CASE
                        WHEN b.isd_regla = 'com_y_fba_3pct'::text THEN 0.03
                        ELSE 0::numeric
                    END - b.almacenamiento_eur) / (b.bb_precio - 0.01) * 100::numeric, 2)
                    ELSE NULL::numeric
                END AS margen_al_bb_1c,
            b.bb_stock >= 1000 AS bb_stock_es_techo,
            b.bb_vendedor = 'Amazon'::text AS bb_es_amazon,
            b.bb_stock IS NOT NULL AND b.bb_stock < 1000 AND (b.vendo_30d > 0 AND b.bb_stock < (b.vendo_30d * 2) OR b.vendo_30d = 0 AND b.bb_stock <= 5) AS rival_flojo
           FROM base b
        ), acc AS (
         SELECT c.asin,
            c.ean,
            c.dominio,
            c.nombre,
            c.pais_operativo,
            c.bb_precio,
            c.bb_vendedor,
            c.bb_seller_id,
            c.bb_es_mio,
            c.bb_stock,
            c.bb_pct_amazon_30d,
            c.fba_min,
            c.ofertas_nuevas_fba,
            c.umbral_competitivo,
            c.amazon_precio,
            c.mi_precio,
            c.margen_hoy,
            c.margen_al_bb,
            c.eur_ud_al_bb,
            c.break_even,
            c.fee,
            c.fee_origen,
            c.comision_pct,
            c.iva_pais,
            c.isd_regla,
            c.almacenamiento_eur,
            c.almacenamiento_origen,
            c.pvd,
            c.pvd_sospechoso,
            c.t7_es,
            c.t30_es,
            c.disponible_es,
            c.cobertura_dias_es,
            c.saldo_uds_pais,
            c.visitas,
            c.sesiones,
            c.conversion_pct,
            c.ratio_oferta_destacada,
            c.veredicto,
            c.motivo_sin_datos,
            c.foto_keepa_el,
            c.demanda_leida_el,
            c.fee_riesgo_acantilado,
            c.categoria,
            c.stock_pais_uds,
            c.tengo_oferta_pais,
            c.sin_listing_pais,
            c.mi_precio_pais,
            c.presencia,
            c.stock_leido_el,
            c.oferta_leida_el,
            c.vendo_30d,
            c.vendo_7d,
            c.vendo_30d_global,
            c.stock_fba_eu_raw,
            c.disp_es_max,
            c.stock_moloka,
            c.repone_pvp,
            c.repone_proveedor,
            c.repone_leido_el,
            c.compre_a,
            c.compre_el,
            c.coste_leido_el,
            c.margen_datado_el,
            c.coste_origen,
            c.bb_es_fba,
            c.rank_drops_30d,
            c.rank_drops_90d,
            c.motivo_bloqueo_paneu,
            c.stock_vendible,
            c.stock_fc_transfer,
            c.stock_en_camino,
            c.stock_reservado,
            c.stock_inservible,
            c.stock_investigando,
            c.stock_fuera_de_dominio,
            c.es_consumible,
            c.stock_fba_eu,
            c.es_no_estas,
            c.repone_vs_coste_pct,
            c.caida_pct,
            c.margen_al_bb_1c,
            c.bb_stock_es_techo,
            c.bb_es_amazon,
            c.rival_flojo,
                CASE
                    WHEN c.repone_pvp IS NULL OR c.repone_vs_coste_pct IS NULL THEN 'sin_dato'::text
                    WHEN c.repone_vs_coste_pct > 15::numeric THEN 'caro'::text
                    WHEN c.repone_vs_coste_pct > 0::numeric THEN 'medio'::text
                    ELSE 'barato'::text
                END AS repone_semaforo,
                CASE
                    WHEN NOT c.es_no_estas THEN NULL::text
                    WHEN c.motivo_bloqueo_paneu IS NOT NULL THEN 'bloqueado por Amazon: '::text || c.motivo_bloqueo_paneu
                    WHEN c.presencia = 'SIN_PAGINA'::text AND (c.stock_moloka > 0::numeric OR c.stock_fba_eu > 0::numeric OR c.vendo_30d > 0) THEN ('tenías ficha y Amazon la retiró: '::text ||
                    CASE
                        WHEN c.stock_fba_eu > 0::numeric THEN c.stock_fba_eu || ' uds en FBA pagando almacenaje'::text
                        ELSE 'sin uds en FBA'::text
                    END) ||
                    CASE
                        WHEN c.stock_moloka > 0::numeric THEN (' y '::text || c.stock_moloka) || ' en el almacén'::text
                        ELSE ''::text
                    END
                    WHEN c.presencia = 'SIN_PAGINA'::text THEN 'el ASIN no existe en el catálogo de este país'::text
                    WHEN c.presencia = 'NI_LISTING'::text THEN 'la página existe, falta tu oferta'::text
                    WHEN c.motivo_bloqueo_paneu IS NULL THEN 'el informe Pan-EU no trae este ASIN: sin fuente, no sin oferta'::text
                    ELSE 'sin oferta activa'::text
                END AS no_estas_causa,
                CASE
                    WHEN c.es_no_estas THEN 'NO_ESTAS'::text
                    WHEN c.bb_precio IS NULL OR c.margen_al_bb IS NULL OR c.mi_precio IS NULL OR GREATEST(c.stock_fba_eu, c.stock_moloka) = 0::numeric THEN 'COMPROBAR'::text
                    WHEN c.vendo_30d > 0 AND c.margen_hoy < 0::numeric THEN 'SUBE'::text
                    WHEN c.vendo_30d_global = 0::numeric AND c.mi_precio > c.bb_precio AND c.stock_fba_eu > 0::numeric THEN 'LIQUIDA'::text
                    WHEN c.bb_es_mio AND c.margen_hoy < 8::numeric THEN 'SUBE'::text
                    WHEN c.bb_es_mio THEN 'AGUANTA'::text
                    WHEN c.repone_vs_coste_pct > 15::numeric AND c.vendo_30d > 0 THEN 'AGUANTA'::text
                    WHEN c.repone_vs_coste_pct > 15::numeric THEN 'NO PELEES'::text
                    WHEN c.margen_al_bb_1c >= 8::numeric THEN 'ATACA'::text
                    WHEN c.margen_al_bb_1c > 0::numeric AND c.repone_pvp IS NOT NULL AND c.vendo_30d >= 5 AND c.rival_flojo AND c.es_consumible THEN 'DESGASTA'::text
                    WHEN c.vendo_30d > 0 AND c.margen_hoy >= 8::numeric THEN 'AGUANTA'::text
                    ELSE 'NO PELEES'::text
                END AS accion
           FROM calc c
        ), pre AS (
         SELECT a.asin,
            a.ean,
            a.dominio,
            a.nombre,
            a.pais_operativo,
            a.bb_precio,
            a.bb_vendedor,
            a.bb_seller_id,
            a.bb_es_mio,
            a.bb_stock,
            a.bb_pct_amazon_30d,
            a.fba_min,
            a.ofertas_nuevas_fba,
            a.umbral_competitivo,
            a.amazon_precio,
            a.mi_precio,
            a.margen_hoy,
            a.margen_al_bb,
            a.eur_ud_al_bb,
            a.break_even,
            a.fee,
            a.fee_origen,
            a.comision_pct,
            a.iva_pais,
            a.isd_regla,
            a.almacenamiento_eur,
            a.almacenamiento_origen,
            a.pvd,
            a.pvd_sospechoso,
            a.t7_es,
            a.t30_es,
            a.disponible_es,
            a.cobertura_dias_es,
            a.saldo_uds_pais,
            a.visitas,
            a.sesiones,
            a.conversion_pct,
            a.ratio_oferta_destacada,
            a.veredicto,
            a.motivo_sin_datos,
            a.foto_keepa_el,
            a.demanda_leida_el,
            a.fee_riesgo_acantilado,
            a.categoria,
            a.stock_pais_uds,
            a.tengo_oferta_pais,
            a.sin_listing_pais,
            a.mi_precio_pais,
            a.presencia,
            a.stock_leido_el,
            a.oferta_leida_el,
            a.vendo_30d,
            a.vendo_7d,
            a.vendo_30d_global,
            a.stock_fba_eu_raw,
            a.disp_es_max,
            a.stock_moloka,
            a.repone_pvp,
            a.repone_proveedor,
            a.repone_leido_el,
            a.compre_a,
            a.compre_el,
            a.coste_leido_el,
            a.margen_datado_el,
            a.coste_origen,
            a.bb_es_fba,
            a.rank_drops_30d,
            a.rank_drops_90d,
            a.motivo_bloqueo_paneu,
            a.stock_vendible,
            a.stock_fc_transfer,
            a.stock_en_camino,
            a.stock_reservado,
            a.stock_inservible,
            a.stock_investigando,
            a.stock_fuera_de_dominio,
            a.es_consumible,
            a.stock_fba_eu,
            a.es_no_estas,
            a.repone_vs_coste_pct,
            a.caida_pct,
            a.margen_al_bb_1c,
            a.bb_stock_es_techo,
            a.bb_es_amazon,
            a.rival_flojo,
            a.repone_semaforo,
            a.no_estas_causa,
            a.accion,
                CASE a.accion
                    WHEN 'ATACA'::text THEN round(a.bb_precio - 0.01, 2)
                    WHEN 'DESGASTA'::text THEN round(a.bb_precio - 0.01, 2)
                    WHEN 'LIQUIDA'::text THEN fn_precio_al_margen_escalon_20(a.dominio, a.fee, a.pvd, a.iva_pais, a.comision_pct,
                    CASE
                        WHEN a.isd_regla ~~ 'com%'::text THEN 1.03
                        ELSE 1.00
                    END,
                    CASE
                        WHEN a.isd_regla = 'com_y_fba_3pct'::text THEN 0.03
                        ELSE 0::numeric
                    END, a.almacenamiento_eur, 0::numeric, 'ceil_desde_break_even'::text)
                    WHEN 'AGUANTA'::text THEN a.mi_precio
                    WHEN 'NO PELEES'::text THEN a.mi_precio
                    WHEN 'SUBE'::text THEN fn_precio_al_margen_escalon_20(a.dominio, a.fee, a.pvd, a.iva_pais, a.comision_pct,
                    CASE
                        WHEN a.isd_regla ~~ 'com%'::text THEN 1.03
                        ELSE 1.00
                    END,
                    CASE
                        WHEN a.isd_regla = 'com_y_fba_3pct'::text THEN 0.03
                        ELSE 0::numeric
                    END, a.almacenamiento_eur, 0.08, 'ceil_centimo'::text)
                    ELSE NULL::numeric
                END AS precio_recomendado,
                CASE
                    WHEN a.bb_stock IS NULL THEN ''::text
                    WHEN a.bb_stock >= 1000 THEN ' · al rival le sobra stock (Keepa corta en 1.000)'::text
                    ELSE (' · al rival le quedan '::text || a.bb_stock) || ' uds'::text
                END AS coletilla_rival
           FROM acc a
        ), pre2 AS (
         SELECT p.asin,
            p.ean,
            p.dominio,
            p.nombre,
            p.pais_operativo,
            p.bb_precio,
            p.bb_vendedor,
            p.bb_seller_id,
            p.bb_es_mio,
            p.bb_stock,
            p.bb_pct_amazon_30d,
            p.fba_min,
            p.ofertas_nuevas_fba,
            p.umbral_competitivo,
            p.amazon_precio,
            p.mi_precio,
            p.margen_hoy,
            p.margen_al_bb,
            p.eur_ud_al_bb,
            p.break_even,
            p.fee,
            p.fee_origen,
            p.comision_pct,
            p.iva_pais,
            p.isd_regla,
            p.almacenamiento_eur,
            p.almacenamiento_origen,
            p.pvd,
            p.pvd_sospechoso,
            p.t7_es,
            p.t30_es,
            p.disponible_es,
            p.cobertura_dias_es,
            p.saldo_uds_pais,
            p.visitas,
            p.sesiones,
            p.conversion_pct,
            p.ratio_oferta_destacada,
            p.veredicto,
            p.motivo_sin_datos,
            p.foto_keepa_el,
            p.demanda_leida_el,
            p.fee_riesgo_acantilado,
            p.categoria,
            p.stock_pais_uds,
            p.tengo_oferta_pais,
            p.sin_listing_pais,
            p.mi_precio_pais,
            p.presencia,
            p.stock_leido_el,
            p.oferta_leida_el,
            p.vendo_30d,
            p.vendo_7d,
            p.vendo_30d_global,
            p.stock_fba_eu_raw,
            p.disp_es_max,
            p.stock_moloka,
            p.repone_pvp,
            p.repone_proveedor,
            p.repone_leido_el,
            p.compre_a,
            p.compre_el,
            p.coste_leido_el,
            p.margen_datado_el,
            p.coste_origen,
            p.bb_es_fba,
            p.rank_drops_30d,
            p.rank_drops_90d,
            p.motivo_bloqueo_paneu,
            p.stock_vendible,
            p.stock_fc_transfer,
            p.stock_en_camino,
            p.stock_reservado,
            p.stock_inservible,
            p.stock_investigando,
            p.stock_fuera_de_dominio,
            p.es_consumible,
            p.stock_fba_eu,
            p.es_no_estas,
            p.repone_vs_coste_pct,
            p.caida_pct,
            p.margen_al_bb_1c,
            p.bb_stock_es_techo,
            p.bb_es_amazon,
            p.rival_flojo,
            p.repone_semaforo,
            p.no_estas_causa,
            p.accion,
            p.precio_recomendado,
            p.coletilla_rival,
                CASE p.accion
                    WHEN 'ATACA'::text THEN 'igualar la caja menos un céntimo'::text || p.coletilla_rival
                    WHEN 'DESGASTA'::text THEN ((('bajar del 8% a propósito: al rival le quedan '::text || p.bb_stock) || ' uds (menos de 2 meses) y tú vendes '::text) || p.vendo_30d) || '/mes'::text
                    WHEN 'LIQUIDA'::text THEN 'no vende en ningún mercado y paga almacén'::text
                    WHEN 'SUBE'::text THEN
                    CASE
                        WHEN p.margen_hoy < 0::numeric THEN 'estás vendiendo a pérdida: este precio deja el 8%'::text
                        ELSE 'precio que deja el 8% — confirmar escalera antes (regla 25)'::text
                    END
                    WHEN 'AGUANTA'::text THEN
                    CASE
                        WHEN p.repone_vs_coste_pct > 15::numeric THEN ('repones '::text || p.repone_vs_coste_pct) || '% más caro: es last-stock, no lo regales'::text
                        WHEN p.bb_es_mio THEN 'tienes la caja y tu precio deja margen'::text || p.coletilla_rival
                        WHEN p.bb_vendedor IS NOT NULL THEN (((((('vendes a tu precio; la caja la tiene '::text || split_part(p.bb_vendedor, ' ('::text, 1)) || ' a '::text) || replace(to_char(p.bb_precio, 'FM999990.00'::text), '.'::text, ','::text)) || ' €, e igualarla dejaría '::text) || replace(to_char(p.margen_al_bb, 'FM999990.0'::text), '.'::text, ','::text)) || '%'::text) || p.coletilla_rival
                        ELSE 'tu precio es correcto y vendes a ese precio'::text
                    END
                    WHEN 'NO PELEES'::text THEN
                    CASE
                        WHEN p.repone_vs_coste_pct > 15::numeric THEN ('repones '::text || p.repone_vs_coste_pct) || '% más caro: es last-stock y aquí no vendes'::text
                        WHEN p.margen_al_bb < 0::numeric THEN 'igualar esa caja está por debajo de tu suelo'::text || p.coletilla_rival
                        ELSE 'atacar no llega al 8% y no vendes a tu precio'::text || p.coletilla_rival
                    END
                    WHEN 'COMPROBAR'::text THEN
                    CASE p.motivo_sin_datos
                        WHEN 'SIN_PRECIO_DE_CAJA_EN_LA_FOTO'::text THEN 'la última foto de Keepa no trae precio de caja'::text
                        WHEN 'IVA_REDUCIDO_NO_MAPEADO_FUERA_DE_ES'::text THEN 'IVA reducido sin mapear fuera de España'::text
                        ELSE COALESCE(p.motivo_sin_datos, 'falta un dato: hay que abrir la ficha'::text)
                    END
                    ELSE COALESCE(p.no_estas_causa, 'no estás ofertado en este país'::text)
                END AS porque
           FROM pre p
        ), fin AS (
         SELECT q.asin,
            q.ean,
            q.dominio,
            q.nombre,
            q.pais_operativo,
            q.bb_precio,
            q.bb_vendedor,
            q.bb_seller_id,
            q.bb_es_mio,
            q.bb_stock,
            q.bb_pct_amazon_30d,
            q.fba_min,
            q.ofertas_nuevas_fba,
            q.umbral_competitivo,
            q.amazon_precio,
            q.mi_precio,
            q.margen_hoy,
            q.margen_al_bb,
            q.eur_ud_al_bb,
            q.break_even,
            q.fee,
            q.fee_origen,
            q.comision_pct,
            q.iva_pais,
            q.isd_regla,
            q.almacenamiento_eur,
            q.almacenamiento_origen,
            q.pvd,
            q.pvd_sospechoso,
            q.t7_es,
            q.t30_es,
            q.disponible_es,
            q.cobertura_dias_es,
            q.saldo_uds_pais,
            q.visitas,
            q.sesiones,
            q.conversion_pct,
            q.ratio_oferta_destacada,
            q.veredicto,
            q.motivo_sin_datos,
            q.foto_keepa_el,
            q.demanda_leida_el,
            q.fee_riesgo_acantilado,
            q.categoria,
            q.stock_pais_uds,
            q.tengo_oferta_pais,
            q.sin_listing_pais,
            q.mi_precio_pais,
            q.presencia,
            q.stock_leido_el,
            q.oferta_leida_el,
            q.vendo_30d,
            q.vendo_7d,
            q.vendo_30d_global,
            q.stock_fba_eu_raw,
            q.disp_es_max,
            q.stock_moloka,
            q.repone_pvp,
            q.repone_proveedor,
            q.repone_leido_el,
            q.compre_a,
            q.compre_el,
            q.coste_leido_el,
            q.margen_datado_el,
            q.coste_origen,
            q.bb_es_fba,
            q.rank_drops_30d,
            q.rank_drops_90d,
            q.motivo_bloqueo_paneu,
            q.stock_vendible,
            q.stock_fc_transfer,
            q.stock_en_camino,
            q.stock_reservado,
            q.stock_inservible,
            q.stock_investigando,
            q.stock_fuera_de_dominio,
            q.es_consumible,
            q.stock_fba_eu,
            q.es_no_estas,
            q.repone_vs_coste_pct,
            q.caida_pct,
            q.margen_al_bb_1c,
            q.bb_stock_es_techo,
            q.bb_es_amazon,
            q.rival_flojo,
            q.repone_semaforo,
            q.no_estas_causa,
            q.accion,
            q.precio_recomendado,
            q.coletilla_rival,
            q.porque,
            round((q.precio_recomendado / (1::numeric + q.iva_pais) - q.pvd - fn_fee_escalon_20(q.dominio, q.fee, q.precio_recomendado) - q.precio_recomendado * (q.comision_pct / 100::numeric) *
                CASE
                    WHEN q.isd_regla ~~ 'com%'::text THEN 1.03
                    ELSE 1.00
                END - fn_fee_escalon_20(q.dominio, q.fee, q.precio_recomendado) *
                CASE
                    WHEN q.isd_regla = 'com_y_fba_3pct'::text THEN 0.03
                    ELSE 0::numeric
                END - q.almacenamiento_eur) / NULLIF(q.precio_recomendado, 0::numeric) * 100::numeric, 2) AS margen_recomendado,
                CASE q.accion
                    WHEN 'SUBE'::text THEN 1
                    WHEN 'ATACA'::text THEN 2
                    WHEN 'DESGASTA'::text THEN 3
                    WHEN 'LIQUIDA'::text THEN 4
                    WHEN 'NO PELEES'::text THEN 5
                    WHEN 'COMPROBAR'::text THEN 6
                    WHEN 'AGUANTA'::text THEN 7
                    ELSE 8
                END AS prio_accion
           FROM pre2 q
        ), fila AS (
         SELECT f.asin,
            f.ean,
            f.dominio,
            f.nombre,
            f.pais_operativo,
            f.bb_precio,
            f.bb_vendedor,
            f.bb_seller_id,
            f.bb_es_mio,
            f.bb_stock,
            f.bb_pct_amazon_30d,
            f.fba_min,
            f.ofertas_nuevas_fba,
            f.umbral_competitivo,
            f.amazon_precio,
            f.mi_precio,
            f.margen_hoy,
            f.margen_al_bb,
            f.eur_ud_al_bb,
            f.break_even,
            f.fee,
            f.fee_origen,
            f.comision_pct,
            f.iva_pais,
            f.isd_regla,
            f.almacenamiento_eur,
            f.almacenamiento_origen,
            f.pvd,
            f.pvd_sospechoso,
            f.t7_es,
            f.t30_es,
            f.disponible_es,
            f.cobertura_dias_es,
            f.saldo_uds_pais,
            f.visitas,
            f.sesiones,
            f.conversion_pct,
            f.ratio_oferta_destacada,
            f.veredicto,
            f.motivo_sin_datos,
            f.foto_keepa_el,
            f.demanda_leida_el,
            f.fee_riesgo_acantilado,
            f.categoria,
            f.stock_pais_uds,
            f.tengo_oferta_pais,
            f.sin_listing_pais,
            f.mi_precio_pais,
            f.presencia,
            f.stock_leido_el,
            f.oferta_leida_el,
            f.vendo_30d,
            f.vendo_7d,
            f.vendo_30d_global,
            f.stock_fba_eu_raw,
            f.disp_es_max,
            f.stock_moloka,
            f.repone_pvp,
            f.repone_proveedor,
            f.repone_leido_el,
            f.compre_a,
            f.compre_el,
            f.coste_leido_el,
            f.margen_datado_el,
            f.coste_origen,
            f.bb_es_fba,
            f.rank_drops_30d,
            f.rank_drops_90d,
            f.motivo_bloqueo_paneu,
            f.stock_vendible,
            f.stock_fc_transfer,
            f.stock_en_camino,
            f.stock_reservado,
            f.stock_inservible,
            f.stock_investigando,
            f.stock_fuera_de_dominio,
            f.es_consumible,
            f.stock_fba_eu,
            f.es_no_estas,
            f.repone_vs_coste_pct,
            f.caida_pct,
            f.margen_al_bb_1c,
            f.bb_stock_es_techo,
            f.bb_es_amazon,
            f.rival_flojo,
            f.repone_semaforo,
            f.no_estas_causa,
            f.accion,
            f.precio_recomendado,
            f.coletilla_rival,
            f.porque,
            f.margen_recomendado,
            f.prio_accion,
            min(f.prio_accion) FILTER (WHERE f.pais_operativo) OVER (PARTITION BY f.asin) AS prio_fila,
            sum(f.vendo_7d) FILTER (WHERE f.pais_operativo) OVER (PARTITION BY f.asin) AS v7_fila,
            sum(f.vendo_30d) FILTER (WHERE f.pais_operativo) OVER (PARTITION BY f.asin) AS v30_fila,
            sum(COALESCE(f.eur_ud_al_bb, 0::numeric) * f.vendo_30d::numeric) FILTER (WHERE f.pais_operativo) OVER (PARTITION BY f.asin) AS impacto_fila
           FROM fin f
        ), fila2 AS (
         SELECT g.asin,
            g.ean,
            g.dominio,
            g.nombre,
            g.pais_operativo,
            g.bb_precio,
            g.bb_vendedor,
            g.bb_seller_id,
            g.bb_es_mio,
            g.bb_stock,
            g.bb_pct_amazon_30d,
            g.fba_min,
            g.ofertas_nuevas_fba,
            g.umbral_competitivo,
            g.amazon_precio,
            g.mi_precio,
            g.margen_hoy,
            g.margen_al_bb,
            g.eur_ud_al_bb,
            g.break_even,
            g.fee,
            g.fee_origen,
            g.comision_pct,
            g.iva_pais,
            g.isd_regla,
            g.almacenamiento_eur,
            g.almacenamiento_origen,
            g.pvd,
            g.pvd_sospechoso,
            g.t7_es,
            g.t30_es,
            g.disponible_es,
            g.cobertura_dias_es,
            g.saldo_uds_pais,
            g.visitas,
            g.sesiones,
            g.conversion_pct,
            g.ratio_oferta_destacada,
            g.veredicto,
            g.motivo_sin_datos,
            g.foto_keepa_el,
            g.demanda_leida_el,
            g.fee_riesgo_acantilado,
            g.categoria,
            g.stock_pais_uds,
            g.tengo_oferta_pais,
            g.sin_listing_pais,
            g.mi_precio_pais,
            g.presencia,
            g.stock_leido_el,
            g.oferta_leida_el,
            g.vendo_30d,
            g.vendo_7d,
            g.vendo_30d_global,
            g.stock_fba_eu_raw,
            g.disp_es_max,
            g.stock_moloka,
            g.repone_pvp,
            g.repone_proveedor,
            g.repone_leido_el,
            g.compre_a,
            g.compre_el,
            g.coste_leido_el,
            g.margen_datado_el,
            g.coste_origen,
            g.bb_es_fba,
            g.rank_drops_30d,
            g.rank_drops_90d,
            g.motivo_bloqueo_paneu,
            g.stock_vendible,
            g.stock_fc_transfer,
            g.stock_en_camino,
            g.stock_reservado,
            g.stock_inservible,
            g.stock_investigando,
            g.stock_fuera_de_dominio,
            g.es_consumible,
            g.stock_fba_eu,
            g.es_no_estas,
            g.repone_vs_coste_pct,
            g.caida_pct,
            g.margen_al_bb_1c,
            g.bb_stock_es_techo,
            g.bb_es_amazon,
            g.rival_flojo,
            g.repone_semaforo,
            g.no_estas_causa,
            g.accion,
            g.precio_recomendado,
            g.coletilla_rival,
            g.porque,
            g.margen_recomendado,
            g.prio_accion,
            g.prio_fila,
            g.v7_fila,
            g.v30_fila,
            g.impacto_fila,
                CASE COALESCE(g.prio_fila, 8)
                    WHEN 1 THEN 'SUBE'::text
                    WHEN 2 THEN 'ATACA'::text
                    WHEN 3 THEN 'DESGASTA'::text
                    WHEN 4 THEN 'LIQUIDA'::text
                    WHEN 5 THEN 'NO PELEES'::text
                    WHEN 6 THEN 'COMPROBAR'::text
                    WHEN 7 THEN 'AGUANTA'::text
                    ELSE 'NO_ESTAS'::text
                END AS accion_fila,
                CASE
                    WHEN COALESCE(g.prio_fila, 8) <= 4 THEN 1
                    WHEN COALESCE(g.prio_fila, 8) <= 6 THEN 2
                    WHEN COALESCE(g.prio_fila, 8) = 7 THEN 3
                    ELSE 4
                END AS bloque,
                CASE
                    WHEN COALESCE(g.v30_fila, 0::numeric) > 0::numeric THEN round((g.v7_fila / 7::numeric * 30::numeric - g.v30_fila) / g.v30_fila * 100::numeric)
                    ELSE NULL::numeric
                END AS caida_fila_pct
           FROM fila g
        ), fila3 AS (
         SELECT h.asin,
            h.ean,
            h.dominio,
            h.nombre,
            h.pais_operativo,
            h.bb_precio,
            h.bb_vendedor,
            h.bb_seller_id,
            h.bb_es_mio,
            h.bb_stock,
            h.bb_pct_amazon_30d,
            h.fba_min,
            h.ofertas_nuevas_fba,
            h.umbral_competitivo,
            h.amazon_precio,
            h.mi_precio,
            h.margen_hoy,
            h.margen_al_bb,
            h.eur_ud_al_bb,
            h.break_even,
            h.fee,
            h.fee_origen,
            h.comision_pct,
            h.iva_pais,
            h.isd_regla,
            h.almacenamiento_eur,
            h.almacenamiento_origen,
            h.pvd,
            h.pvd_sospechoso,
            h.t7_es,
            h.t30_es,
            h.disponible_es,
            h.cobertura_dias_es,
            h.saldo_uds_pais,
            h.visitas,
            h.sesiones,
            h.conversion_pct,
            h.ratio_oferta_destacada,
            h.veredicto,
            h.motivo_sin_datos,
            h.foto_keepa_el,
            h.demanda_leida_el,
            h.fee_riesgo_acantilado,
            h.categoria,
            h.stock_pais_uds,
            h.tengo_oferta_pais,
            h.sin_listing_pais,
            h.mi_precio_pais,
            h.presencia,
            h.stock_leido_el,
            h.oferta_leida_el,
            h.vendo_30d,
            h.vendo_7d,
            h.vendo_30d_global,
            h.stock_fba_eu_raw,
            h.disp_es_max,
            h.stock_moloka,
            h.repone_pvp,
            h.repone_proveedor,
            h.repone_leido_el,
            h.compre_a,
            h.compre_el,
            h.coste_leido_el,
            h.margen_datado_el,
            h.coste_origen,
            h.bb_es_fba,
            h.rank_drops_30d,
            h.rank_drops_90d,
            h.motivo_bloqueo_paneu,
            h.stock_vendible,
            h.stock_fc_transfer,
            h.stock_en_camino,
            h.stock_reservado,
            h.stock_inservible,
            h.stock_investigando,
            h.stock_fuera_de_dominio,
            h.es_consumible,
            h.stock_fba_eu,
            h.es_no_estas,
            h.repone_vs_coste_pct,
            h.caida_pct,
            h.margen_al_bb_1c,
            h.bb_stock_es_techo,
            h.bb_es_amazon,
            h.rival_flojo,
            h.repone_semaforo,
            h.no_estas_causa,
            h.accion,
            h.precio_recomendado,
            h.coletilla_rival,
            h.porque,
            h.margen_recomendado,
            h.prio_accion,
            h.prio_fila,
            h.v7_fila,
            h.v30_fila,
            h.impacto_fila,
            h.accion_fila,
            h.bloque,
            h.caida_fila_pct,
                CASE
                    WHEN COALESCE(h.v30_fila, 0::numeric) >= 10::numeric THEN 1
                    WHEN COALESCE(h.v30_fila, 0::numeric) > 0::numeric THEN 2
                    ELSE 3
                END AS tramo_caida,
            COALESCE(h.v30_fila, 0::numeric) >= 10::numeric AS caida_fiable,
            h.motivo_bloqueo_paneu IS NOT NULL AS es_bloqueo_amazon,
                CASE
                    WHEN h.accion <> 'NO_ESTAS'::text THEN 'ofertado'::text
                    WHEN h.motivo_bloqueo_paneu IS NOT NULL THEN 'bloqueado'::text
                    WHEN h.presencia = 'SIN_PAGINA'::text AND (h.stock_moloka > 0::numeric OR h.stock_fba_eu > 0::numeric OR h.vendo_30d > 0) THEN 'ficha_retirada'::text
                    WHEN h.presencia = 'SIN_PAGINA'::text THEN 'sin_pagina'::text
                    WHEN h.presencia = 'NI_LISTING'::text THEN 'ficha_por_crear'::text
                    WHEN h.presencia = 'SIN_OFERTA'::text THEN 'sin_dato_paneu'::text
                    ELSE 'ofertado'::text
                END AS presencia_detalle,
                CASE
                    WHEN h.accion <> 'NO_ESTAS'::text THEN NULL::text
                    WHEN h.motivo_bloqueo_paneu IS NOT NULL THEN 'asumir solo-España'::text
                    WHEN h.presencia = 'SIN_PAGINA'::text AND (h.stock_moloka > 0::numeric OR h.stock_fba_eu > 0::numeric OR h.vendo_30d > 0) THEN 'reclamar la ficha'::text
                    WHEN h.presencia = 'SIN_PAGINA'::text THEN 'crear producto'::text
                    WHEN h.presencia = 'NI_LISTING'::text THEN 'crear oferta'::text
                    WHEN h.presencia = 'SIN_OFERTA'::text THEN 'comprobar en Seller'::text
                    ELSE NULL::text
                END AS trabajo_pendiente,
            dense_rank() OVER (PARTITION BY h.bloque ORDER BY (
                CASE
                    WHEN COALESCE(h.v30_fila, 0::numeric) >= 10::numeric THEN 1
                    WHEN COALESCE(h.v30_fila, 0::numeric) > 0::numeric THEN 2
                    ELSE 3
                END), (COALESCE(h.caida_fila_pct, 9999::numeric)), (COALESCE(h.impacto_fila, 0::numeric)) DESC, h.asin) AS orden_en_bloque,
                CASE
                    WHEN h.margen_recomendado IS NULL THEN 'sin_dato'::text
                    WHEN h.accion = ANY (ARRAY['LIQUIDA'::text, 'SUBE'::text, 'DESGASTA'::text]) THEN 'objetivo'::text
                    WHEN h.margen_recomendado < 0::numeric THEN 'perdida'::text
                    WHEN h.margen_recomendado >= 8::numeric THEN 'bueno'::text
                    ELSE 'flojo'::text
                END AS margen_semaforo
           FROM fila2 h
        )
 SELECT asin,
    ean,
    dominio,
    nombre,
    pais_operativo,
    bb_precio,
    bb_vendedor,
    bb_seller_id,
    bb_es_mio,
    bb_stock,
    bb_pct_amazon_30d,
    fba_min,
    ofertas_nuevas_fba,
    umbral_competitivo,
    amazon_precio,
    mi_precio,
    margen_hoy,
    margen_al_bb,
    eur_ud_al_bb,
    break_even,
    fee,
    fee_origen,
    comision_pct,
    iva_pais,
    isd_regla,
    almacenamiento_eur,
    almacenamiento_origen,
    pvd,
    pvd_sospechoso,
    t7_es,
    t30_es,
    disponible_es,
    cobertura_dias_es,
    saldo_uds_pais,
    visitas,
    sesiones,
    conversion_pct,
    ratio_oferta_destacada,
    veredicto,
    motivo_sin_datos,
    foto_keepa_el,
    demanda_leida_el,
    fee_riesgo_acantilado,
    categoria,
    stock_pais_uds,
    tengo_oferta_pais,
    sin_listing_pais,
    mi_precio_pais,
    presencia,
    stock_leido_el,
    oferta_leida_el,
    vendo_30d,
    vendo_7d,
    vendo_30d_global,
    stock_fba_eu_raw,
    disp_es_max,
    stock_moloka,
    repone_pvp,
    repone_proveedor,
    repone_leido_el,
    compre_a,
    compre_el,
    coste_leido_el,
    margen_datado_el,
    coste_origen,
    bb_es_fba,
    rank_drops_30d,
    rank_drops_90d,
    motivo_bloqueo_paneu,
    stock_vendible,
    stock_fc_transfer,
    stock_en_camino,
    stock_reservado,
    stock_inservible,
    stock_investigando,
    stock_fuera_de_dominio,
    es_consumible,
    stock_fba_eu,
    es_no_estas,
    repone_vs_coste_pct,
    caida_pct,
    margen_al_bb_1c,
    bb_stock_es_techo,
    bb_es_amazon,
    rival_flojo,
    repone_semaforo,
    no_estas_causa,
    accion,
    precio_recomendado,
    coletilla_rival,
    porque,
    margen_recomendado,
    prio_accion,
    prio_fila,
    v7_fila,
    v30_fila,
    impacto_fila,
    accion_fila,
    bloque,
    caida_fila_pct,
    tramo_caida,
    caida_fiable,
    es_bloqueo_amazon,
    presencia_detalle,
    trabajo_pendiente,
    orden_en_bloque,
    margen_semaforo,
        CASE min(
            CASE trabajo_pendiente
                WHEN 'reclamar la ficha'::text THEN 1
                WHEN 'abrir caso'::text THEN 2
                WHEN 'crear oferta'::text THEN 3
                WHEN 'crear producto'::text THEN 4
                WHEN 'comprobar en Seller'::text THEN 5
                ELSE 9
            END) FILTER (WHERE trabajo_pendiente IS NOT NULL AND pais_operativo) OVER (PARTITION BY asin)
            WHEN 1 THEN 'reclamar la ficha'::text
            WHEN 2 THEN 'abrir caso'::text
            WHEN 3 THEN 'crear oferta'::text
            WHEN 4 THEN 'crear producto'::text
            WHEN 5 THEN 'comprobar en Seller'::text
            ELSE NULL::text
        END AS trabajo_fila
   FROM fila3 k;

-- 🔴 IMPRESCINDIBLE: el REPLACE de arriba se ha llevado por delante las
--    opciones de la vista. Sin esta linea, `security_invoker` se pierde y la
--    vista vuelve a leer como su dueno, saltandose la RLS, en silencio.
ALTER VIEW public.v_trackeador_pantalla SET (security_invoker = true);

-- ── EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ──────────────────────────
DO $$
DECLARE
  n int; huella text; tapones int; suelos int;
BEGIN
  -- 1 · 🔑 LA COMPROBACIÓN DE VERDAD ES SOBRE EL TEXTO, no sobre los datos: hoy el
  --     tránsito se conoce en todas las fichas, así que la version del 2b y esta
  --     dan LAS MISMAS CIFRAS. Una huella de datos no distinguiria una de otra.
  SELECT count(*) FILTER (WHERE l LIKE '%COALESCE(sf.uds_fc_transfer%'),
         count(*) FILTER (WHERE l LIKE '%COALESCE(c.stock_fba_eu%'
                             OR l LIKE '%COALESCE(h.stock_fba_eu%')
    INTO tapones, suelos
    FROM regexp_split_to_table(
           pg_get_viewdef('public.v_trackeador_pantalla'::regclass, true), E'\n') l;
  IF tapones <> 1 THEN
    RAISE EXCEPTION 'ABORTA: el COALESCE que tapa el transito aparece % veces y '
                    'tenia que volver 1 vez. La vuelta atras no ha hecho su '
                    'trabajo.', tapones;
  END IF;
  IF suelos <> 0 THEN
    RAISE EXCEPTION 'ABORTA: quedan % suelos COALESCE(stock_fba_eu, stock_vendible) '
                    'y tenian que irse los 6.', suelos;
  END IF;

  -- 2 · Y no se ha movido ni un dato respecto a como estaba al empezar.
  SELECT count(*), md5(string_agg(t::text, E'
' ORDER BY t.asin, t.dominio))
    INTO n, huella FROM public.v_trackeador_pantalla t;
  IF n IS DISTINCT FROM (SELECT filas FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: la vista devuelve % filas y antes devolvia %.',
                    n, (SELECT filas FROM _pantalla_antes);
  END IF;
  IF huella IS DISTINCT FROM (SELECT p.huella FROM _pantalla_antes p) THEN
    RAISE EXCEPTION 'ABORTA: revertir ha movido datos, y hoy no puede mover ninguno: '
                    'el transito se conoce en todas las fichas.';
  END IF;
  IF (SELECT sum(t.stock_fba_eu) FROM public.v_trackeador_pantalla t)
     IS DISTINCT FROM (SELECT suma_stock_fba_eu FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: la suma de stock_fba_eu ha cambiado al revertir.';
  END IF;

  -- 3 · No se ha perdido el SELECT ni la materializada.
  IF NOT has_table_privilege('authenticated', 'public.v_trackeador_pantalla', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` se ha quedado sin SELECT sobre la vista.';
  END IF;
  SELECT count(*) INTO n FROM public.mv_trackeador_pantalla;
  IF n = 0 THEN
    RAISE EXCEPTION 'ABORTA: mv_trackeador_pantalla esta VACIA. Deja la pantalla en '
                    'blanco sin dar error, y esta migracion no la toca.';
  END IF;

  RAISE NOTICE 'Numero de control OK: ha vuelto el COALESCE del transito, se han ido '
               'los 6 suelos, % filas sin mover un dato, el SELECT en su '
               'sitio y la materializada llena.', n;
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job):
--
--   select count(*) filter (where l like '%COALESCE(sf.uds_fc_transfer%') as tapon_vuelto,
--          count(*) filter (where l like '%COALESCE(c.stock_fba_eu%'
--                              or l like '%COALESCE(h.stock_fba_eu%')     as suelos_que_quedan
--     from regexp_split_to_table(
--            pg_get_viewdef('public.v_trackeador_pantalla'::regclass, true), E'\n') l;
--   -- → 1 · 0
--
--   -- Y LO QUE NO SE PUEDE COMPROBAR DESDE AQUI: que Elena vea filas. Se mira
--   -- abriendo el Trackeador. Es el motivo por el que existe este fichero.
-- ============================================================================
