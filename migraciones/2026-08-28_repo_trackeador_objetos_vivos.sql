-- ============================================================================
-- MIGRACION - EL TRACKEADOR ENTRA EN EL REPO: 8 objetos vivos que no crea nadie
-- ----------------------------------------------------------------------------
-- QUE ES ESTO. Una FOTO, no una mejora. Ocho objetos que llevan meses vivos en
-- produccion y que NINGUN fichero de los dos repos crea -- medido el 28-ago-2026
-- buscando `create ... <nombre>` en .sql, .py, .yml y .ts de moloka-app y de
-- moloka-app-v2: cero apariciones. El texto de cada uno esta copiado LITERAL de
-- `pg_get_viewdef(oid, true)` y `pg_get_functiondef(oid)` de PRODUCCION, sin
-- tocar una coma.
--
-- 🔴 NO SE ARREGLA NADA AQUI, Y ES DELIBERADO. Dos de las funciones son
--    SECURITY DEFINER con EXECUTE para PUBLIC, y `v_sondas_pendientes` (que va
--    en la migracion hermana) no lleva security_invoker. Eso choca con la
--    seccion 4, esta anotado como frente propio y se arregla en SU PR. Si esta
--    migracion los escribiera "arreglados" dejaria de reproducir produccion, y
--    el dia que se aplicara cambiaria el comportamiento sin que nadie lo espere.
--
-- POR QUE IMPORTA, dicho con precision. El volcado de `backup-bd.yml` es
-- `pg_dump --schema=public`, asi que un restore SI devuelve estos objetos: se
-- comprobo en staging, que es un restore, y ocho de ellos estan alli. Lo que NO
-- se puede hoy es reconstruir la base desde el repo, revisar en un PR un cambio
-- en ellos, ni detectar que el objeto vivo se ha desviado de su texto -- que es
-- exactamente lo que paso con 7 de las 9 RPC de escritura.
--
-- 🔬 EL ALCANCE, dicho sin adornos: esto NO hace que la base se pueda levantar
--    de cero. De las 19 tablas de las que cuelga este arbol, 17 tampoco estan en
--    ninguna migracion (`productos`, `keepa_escaparate`, `ledger_movimientos`,
--    `listings_amazon`...). El esquema de tablas nunca ha estado en el repo, y
--    eso es otro frente. Esta migracion cubre el CODIGO -- vistas,
--    materializada y funciones -- y exige que las tablas existan, cosa que la
--    primera guarda comprueba y dice por su nombre.
--
-- 🔴 LOS INDICES NO SON UN ADORNO. `mv_trackeador_pantalla` tiene cuatro, y uno
--    es UNIQUE sobre (asin, dominio). Sin ese indice `refresh materialized view
--    CONCURRENTLY` -- que es como la refresca `fn_trackeador_refrescar` en cada
--    carga de cada informe -- NO ARRANCA. Transcribir la vista sin sus indices
--    dejaria el Trackeador roto en el proximo restore, callando.
--
-- ORDEN DE CREACION, que es el que impone el arbol de dependencias medido:
--    secuencia -> trackeador_refrescos -> v_trackeador_precio_pais ->
--    v_trackeador_precio_pais_full -> v_trackeador_pantalla ->
--    mv_trackeador_pantalla (+4 indices) -> fn_fee_override_refresh ->
--    fn_trackeador_frescura -> v_trackeador_frescura -> fn_trackeador_refrescar
--
-- IDEMPOTENTE A PROPOSITO: `create or replace` en vistas y funciones (conserva
-- OID y ACL, no tira lo que cuelga) y `if not exists` en tabla, secuencia,
-- materializada e indices. Sobre produccion esta migracion no cambia NADA: ese
-- es el resultado que se busca. Lo que prueba que el fichero sirve es el ensayo
-- en staging CON LOS OBJETOS TIRADOS ANTES, no una pasada en verde sobre un
-- destino que ya estaba en el estado final.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    falta      text;
    k          char;
    ya_estaban int := 0;
    n          int;
BEGIN
    -- 1) Las fuentes tienen que existir. Si falta una, el fallo se explica aqui
    --    y no en mitad de un `create view` con un mensaje de Postgres.
    SELECT string_agg(x.nombre, ', ' ORDER BY x.nombre) INTO falta
      FROM (VALUES ('productos'),('keepa_escaparate'),('listings_amazon'),
                   ('inventario_fba'),('inventario_internacional'),('paneu_aptos'),
                   ('paneu_oferta_pais'),('compras'),('transacciones_movimientos'),
                   ('escaner_memoria'),('fee_override'),('v_demanda_asin_ultima'),
                   ('v_presencia_pais'),('v_producto_amazon'),('v_salud_asin')) x(nombre)
     WHERE to_regclass('public.' || x.nombre) IS NULL;
    IF falta IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: faltan las fuentes %. Esta migracion transcribe CODIGO y da por hecho que el esquema de tablas ya existe; no levanta la base de cero.', falta;
    END IF;

    -- 2) Si el objeto ya existe, tiene que ser de la clase que esta migracion
    --    cree. Una materializada donde se espera una vista (o al reves) no se
    --    resuelve con `or replace`: reventaria a medias.
    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.mv_trackeador_pantalla');
    IF k IS NOT NULL AND k <> 'm' THEN
        RAISE EXCEPTION 'ABORTA: mv_trackeador_pantalla existe con relkind=% y se esperaba una MATERIALIZADA.', k;
    END IF;
    FOR falta IN SELECT x.n FROM (VALUES ('v_trackeador_precio_pais'),('v_trackeador_precio_pais_full'),
                                         ('v_trackeador_pantalla'),('v_trackeador_frescura')) x(n)
    LOOP
        SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.' || falta);
        IF k IS NOT NULL AND k <> 'v' THEN
            RAISE EXCEPTION 'ABORTA: % existe con relkind=% y se esperaba una VISTA.', falta, k;
        END IF;
    END LOOP;

    -- 3) 🔴 EL AVISO QUE EVITA EL VERDE PRESTADO. Si los ocho ya estaban, esta
    --    pasada no demuestra que el fichero sepa crearlos: solo que el destino
    --    ya estaba como se queria. Grita y sigue -- sobre produccion esto es lo
    --    NORMAL y esperado; en un ensayo de staging significa que no se tiraron
    --    antes y que el verde no vale.
    SELECT count(*) INTO ya_estaban FROM (
        SELECT 1 FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE ns.nspname = 'public' AND c.relname IN
               ('v_trackeador_precio_pais','v_trackeador_precio_pais_full','v_trackeador_pantalla',
                'mv_trackeador_pantalla','v_trackeador_frescura','trackeador_refrescos')
        UNION ALL
        SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
         WHERE ns.nspname = 'public' AND p.proname IN
               ('fn_fee_override_refresh','fn_trackeador_frescura','fn_trackeador_refrescar')) z;
    IF ya_estaban >= 9 THEN
        RAISE WARNING 'AVISO: los 9 objetos YA EXISTIAN antes de esta migracion. Sobre produccion es lo esperado (esto es una foto). En un ENSAYO de staging significa que no se tiraron antes, y entonces este verde NO prueba que el fichero sepa crearlos.';
    ELSE
        RAISE NOTICE 'Guardas OK. Existian % de 9; se van a crear las que falten.', ya_estaban;
    END IF;
END
$guardas$;

-- -- 1) LA SECUENCIA Y LA TABLA DE REFRESCOS ---------------------------------
-- `trackeador_refrescos` es el log que escribe fn_trackeador_refrescar en cada
-- pasada. Va aqui el ESQUEMA, no las filas: 41 apuntes de historia que devuelve
-- el backup y que se regeneran solos en cuanto vuelva a correr el refresco.
-- Y por eso tampoco lleva `setval`: sobre una tabla vacia el contador correcto
-- es el 1, y clavar aqui el 42 de hoy seria escribir historia en una migracion.
create sequence if not exists public.trackeador_refrescos_id_seq;

create table if not exists public.trackeador_refrescos (
  id bigint default nextval('trackeador_refrescos_id_seq'::regclass) not null,
  empezo_el timestamp with time zone default now() not null,
  acabo_el timestamp with time zone,
  filas integer,
  ok boolean default false not null,
  error text,
  constraint trackeador_refrescos_pkey PRIMARY KEY (id)
);

alter sequence public.trackeador_refrescos_id_seq owned by public.trackeador_refrescos.id;
alter table public.trackeador_refrescos enable row level security;

revoke all on public.trackeador_refrescos from public, anon, authenticated;
grant all    on public.trackeador_refrescos to service_role;
grant select on public.trackeador_refrescos to authenticated;
revoke all on sequence public.trackeador_refrescos_id_seq from public, anon, authenticated;
grant usage, select, update on sequence public.trackeador_refrescos_id_seq to service_role;

-- La politica, tal cual esta viva. `create policy` no admite `if not exists`.
DO $pol$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'trackeador_refrescos'
                      AND policyname = 'tr_refrescos_lectura') THEN
        CREATE POLICY tr_refrescos_lectura ON public.trackeador_refrescos
            FOR SELECT TO authenticated USING (auth.uid() IS NOT NULL);
    END IF;
END
$pol$;

-- -- 2) LA CADENA DE VISTAS DEL PRECIO POR PAIS ------------------------------
create or replace view public.v_trackeador_precio_pais with (security_invoker = true) as
WITH param AS (
         SELECT t.dominio,
            t.iva_pais,
            t.k_com,
            t.k_fee,
            t.isd_regla,
            t.pais_operativo
           FROM ( VALUES ('es'::text,0.21,1.03,0.00,'com_3pct'::text,true), ('it'::text,0.22,1.03,0.00,'com_3pct'::text,true), ('fr'::text,0.20,1.03,0.03,'com_y_fba_3pct'::text,true), ('de'::text,0.19,1.03,0.00,'com_3pct_precaucion'::text,true)) t(dominio, iva_pais, k_com, k_fee, isd_regla, pais_operativo)
        ), ult AS (
         SELECT DISTINCT ON (keepa_escaparate.asin, keepa_escaparate.dominio) keepa_escaparate.asin,
            keepa_escaparate.dominio,
            keepa_escaparate.ean_keepa_crudo,
            keepa_escaparate.upc_keepa,
            keepa_escaparate.titulo,
            keepa_escaparate.marca,
            keepa_escaparate.fabricante,
            keepa_escaparate.tipo_producto,
            keepa_escaparate.imagenes,
            keepa_escaparate.n_imagenes,
            keepa_escaparate.tarifa_fba,
            keepa_escaparate.comision_pct,
            keepa_escaparate.comision_eur_bb,
            keepa_escaparate.bb_precio,
            keepa_escaparate.bb_vendedor,
            keepa_escaparate.bb_es_fba,
            keepa_escaparate.bb_stock,
            keepa_escaparate.bb_pct_amazon_30d,
            keepa_escaparate.bb_disponibilidad,
            keepa_escaparate.fba_mas_barato,
            keepa_escaparate.fbm_mas_barato,
            keepa_escaparate.p3_fba_precio,
            keepa_escaparate.p3_fba_stock,
            keepa_escaparate.p3_fbm_stock,
            keepa_escaparate.ofertas_nuevas,
            keepa_escaparate.ofertas_nuevas_fba,
            keepa_escaparate.ofertas_nuevas_fbm,
            keepa_escaparate.ofertas_total,
            keepa_escaparate.umbral_competitivo,
            keepa_escaparate.amazon_precio,
            keepa_escaparate.amazon_disponibilidad,
            keepa_escaparate.rank,
            keepa_escaparate.rank_30d,
            keepa_escaparate.rank_90d,
            keepa_escaparate.rank_drops_30d,
            keepa_escaparate.rank_drops_90d,
            keepa_escaparate.categoria,
            keepa_escaparate.subcategoria,
            keepa_escaparate.monthly_sold_ultimo,
            keepa_escaparate.monthly_sold_ultimo_fecha,
            keepa_escaparate.comprados_mes_pasado,
            keepa_escaparate.asin_padre,
            keepa_escaparate.asins_variacion,
            keepa_escaparate.n_variaciones,
            keepa_escaparate.atributos_variacion,
            keepa_escaparate.paq_peso_g,
            keepa_escaparate.paq_largo_cm,
            keepa_escaparate.paq_ancho_cm,
            keepa_escaparate.paq_alto_cm,
            keepa_escaparate.fecha_lanzamiento,
            keepa_escaparate.keepa_actualizado,
            keepa_escaparate.listado_desde,
            keepa_escaparate.rating,
            keepa_escaparate.n_valoraciones,
            keepa_escaparate.comprados_juntos,
            keepa_escaparate.slug_amazon,
            keepa_escaparate.bullet_1,
            keepa_escaparate.bullet_2,
            keepa_escaparate.bullet_3,
            keepa_escaparate.bullet_4,
            keepa_escaparate.bullet_5,
            keepa_escaparate.bb_seller_id,
            keepa_escaparate.fichero,
            keepa_escaparate.fecha_foto,
            keepa_escaparate.seller_id,
            keepa_escaparate.crudo,
            keepa_escaparate.procesado_at,
            keepa_escaparate.bb_envio,
            keepa_escaparate.bb_pais_envio,
            keepa_escaparate.bb_plazo_txt
           FROM keepa_escaparate
          ORDER BY keepa_escaparate.asin, keepa_escaparate.dominio, keepa_escaparate.fecha_foto DESC
        ), dem AS (
         SELECT v_demanda_asin_ultima.asin,
            lower(v_demanda_asin_ultima.pais) AS dominio,
            v_demanda_asin_ultima.visitas,
            v_demanda_asin_ultima.sesiones,
            v_demanda_asin_ultima.conversion,
            v_demanda_asin_ultima.buybox_ratio,
            v_demanda_asin_ultima.leido_at
           FROM v_demanda_asin_ultima
        ), sal AS (
         SELECT v_salud_asin.asin,
            v_salud_asin.t7,
            v_salud_asin.t30,
            v_salud_asin.disponible,
            v_salud_asin.your_price_min,
            v_salud_asin.cobertura_dias_t7
           FROM v_salud_asin
          WHERE v_salud_asin.marketplace = 'ES'::text
        ), pres AS (
         SELECT v_presencia_pais.asin,
            lower(v_presencia_pais.pais) AS dominio,
            COALESCE(v_presencia_pais.uds_recibidas, 0::bigint) - COALESCE(v_presencia_pais.uds_vendidas, 0::bigint) AS saldo_uds
           FROM v_presencia_pais
        ), inv AS (
         SELECT inventario_internacional.asin,
            lower(inventario_internacional.country) AS dominio,
            sum(inventario_internacional.quantity) AS stock_uds,
            max(inventario_internacional.fecha_foto) AS stock_foto
           FROM inventario_internacional
          WHERE inventario_internacional.fecha_foto = (( SELECT max(inventario_internacional_1.fecha_foto) AS max
                   FROM inventario_internacional inventario_internacional_1))
          GROUP BY inventario_internacional.asin, (lower(inventario_internacional.country))
        ), ofer AS (
         SELECT a.asin,
            lower(o.pais) AS dominio,
            bool_or(o.tiene_oferta) AS tiene_oferta,
            min(o.precio) FILTER (WHERE o.tiene_oferta) AS mi_precio_pais,
            bool_and(COALESCE(o.sin_listing, false)) AS sin_listing,
            max(o.snapshot_date) AS oferta_foto
           FROM paneu_oferta_pais o
             JOIN ( SELECT DISTINCT paneu_aptos.seller_sku,
                    paneu_aptos.asin
                   FROM paneu_aptos
                  WHERE paneu_aptos.snapshot_date = (( SELECT max(paneu_aptos_1.snapshot_date) AS max
                           FROM paneu_aptos paneu_aptos_1)) AND paneu_aptos.asin IS NOT NULL) a ON a.seller_sku = o.seller_sku
          WHERE o.snapshot_date = (( SELECT max(paneu_oferta_pais.snapshot_date) AS max
                   FROM paneu_oferta_pais))
          GROUP BY a.asin, (lower(o.pais))
        ), base AS (
         SELECT p.asin,
            p.ean,
            COALESCE(k.titulo, p.nombre) AS nombre,
            k.dominio,
            k.categoria,
            par.iva_pais,
            par.k_com,
            par.k_fee,
            par.isd_regla,
            par.pais_operativo,
            p.pvd,
            p.iva_pct AS iva_es_producto,
            p.pvd_sospechoso,
            COALESCE(( SELECT o.fee_eur
                   FROM fee_override o
                  WHERE o.asin = k.asin AND o.dominio = k.dominio),
                CASE k.dominio
                    WHEN 'es'::text THEN COALESCE(p.keepa_fba_fee_es, k.tarifa_fba)
                    WHEN 'it'::text THEN COALESCE(p.keepa_fba_fee_it, k.tarifa_fba)
                    WHEN 'fr'::text THEN COALESCE(p.keepa_fba_fee_fr, k.tarifa_fba)
                    ELSE k.tarifa_fba
                END) AS fee,
            COALESCE(( SELECT o.origen
                   FROM fee_override o
                  WHERE o.asin = k.asin AND o.dominio = k.dominio),
                CASE k.dominio
                    WHEN 'es'::text THEN
                    CASE
                        WHEN p.keepa_fba_fee_es IS NOT NULL THEN 'maestro'::text
                        WHEN k.tarifa_fba IS NOT NULL THEN 'keepa'::text
                        ELSE 'ninguno'::text
                    END
                    WHEN 'it'::text THEN
                    CASE
                        WHEN p.keepa_fba_fee_it IS NOT NULL THEN 'maestro'::text
                        WHEN k.tarifa_fba IS NOT NULL THEN 'keepa'::text
                        ELSE 'ninguno'::text
                    END
                    WHEN 'fr'::text THEN
                    CASE
                        WHEN p.keepa_fba_fee_fr IS NOT NULL THEN 'maestro'::text
                        WHEN k.tarifa_fba IS NOT NULL THEN 'keepa'::text
                        ELSE 'ninguno'::text
                    END
                    ELSE
                    CASE
                        WHEN k.tarifa_fba IS NOT NULL THEN 'keepa'::text
                        ELSE 'ninguno'::text
                    END
                END) AS fee_origen,
                CASE k.dominio
                    WHEN 'es'::text THEN COALESCE(p.comision_pct_keepa_es, k.comision_pct)
                    WHEN 'it'::text THEN COALESCE(p.comision_pct_it, k.comision_pct)
                    WHEN 'fr'::text THEN COALESCE(p.comision_pct_fr, k.comision_pct)
                    ELSE k.comision_pct
                END AS com_pct,
            k.bb_precio,
            k.bb_vendedor,
            k.bb_seller_id,
            k.bb_stock,
            k.bb_pct_amazon_30d,
            k.fba_mas_barato AS fba_min,
            k.ofertas_nuevas_fba,
            k.umbral_competitivo,
            k.amazon_precio,
            k.fecha_foto,
            k.bb_vendedor ~~* '%MOLOKA%'::text AS bb_es_mio,
            s.t7 AS t7_es,
            s.t30 AS t30_es,
            s.disponible AS disponible_es,
            s.your_price_min AS mi_precio_es,
            s.cobertura_dias_t7 AS cobertura_dias_es,
            d.visitas,
            d.sesiones,
            round(d.conversion * 100::numeric, 2) AS conversion_pct,
            d.buybox_ratio AS ratio_oferta_destacada,
            d.leido_at,
            pr.saldo_uds AS saldo_uds_pais,
            iv.stock_uds AS stock_pais_uds,
            iv.stock_foto,
            of.tiene_oferta,
            of.mi_precio_pais,
            of.sin_listing,
            of.oferta_foto,
            pm.updated_at AS coste_leido_el
           FROM v_producto_amazon p
             JOIN ult k ON k.asin = p.asin
             JOIN param par ON par.dominio = k.dominio
             LEFT JOIN sal s ON s.asin = p.asin
             LEFT JOIN dem d ON d.asin = p.asin AND d.dominio = k.dominio
             LEFT JOIN pres pr ON pr.asin = p.asin AND pr.dominio = k.dominio
             LEFT JOIN inv iv ON iv.asin = p.asin AND iv.dominio = k.dominio
             LEFT JOIN ofer of ON of.asin = p.asin AND of.dominio = k.dominio
             LEFT JOIN productos pm ON pm.asin = p.asin AND pm.estado = 'OK'::text
        ), calc AS (
         SELECT b.asin,
            b.ean,
            b.nombre,
            b.dominio,
            b.categoria,
            b.iva_pais,
            b.k_com,
            b.k_fee,
            b.isd_regla,
            b.pais_operativo,
            b.pvd,
            b.iva_es_producto,
            b.pvd_sospechoso,
            b.fee,
            b.fee_origen,
            b.com_pct,
            b.bb_precio,
            b.bb_vendedor,
            b.bb_seller_id,
            b.bb_stock,
            b.bb_pct_amazon_30d,
            b.fba_min,
            b.ofertas_nuevas_fba,
            b.umbral_competitivo,
            b.amazon_precio,
            b.fecha_foto,
            b.bb_es_mio,
            b.t7_es,
            b.t30_es,
            b.disponible_es,
            b.mi_precio_es,
            b.cobertura_dias_es,
            b.visitas,
            b.sesiones,
            b.conversion_pct,
            b.ratio_oferta_destacada,
            b.leido_at,
            b.saldo_uds_pais,
            b.stock_pais_uds,
            b.stock_foto,
            b.tiene_oferta,
            b.mi_precio_pais,
            b.sin_listing,
            b.oferta_foto,
            b.coste_leido_el,
                CASE
                    WHEN b.dominio = 'es'::text THEN b.iva_es_producto
                    WHEN b.iva_es_producto = 0.21 THEN b.iva_pais
                    ELSE NULL::numeric
                END AS iva_aplicado,
                CASE
                    WHEN b.dominio = 'es'::text THEN COALESCE(b.mi_precio_es, b.mi_precio_pais)
                    ELSE COALESCE(b.mi_precio_pais,
                    CASE
                        WHEN b.bb_es_mio THEN b.bb_precio
                        ELSE NULL::numeric
                    END)
                END AS mi_precio
           FROM base b
        ), m AS (
         SELECT c.asin,
            c.ean,
            c.nombre,
            c.dominio,
            c.categoria,
            c.iva_pais,
            c.k_com,
            c.k_fee,
            c.isd_regla,
            c.pais_operativo,
            c.pvd,
            c.iva_es_producto,
            c.pvd_sospechoso,
            c.fee,
            c.fee_origen,
            c.com_pct,
            c.bb_precio,
            c.bb_vendedor,
            c.bb_seller_id,
            c.bb_stock,
            c.bb_pct_amazon_30d,
            c.fba_min,
            c.ofertas_nuevas_fba,
            c.umbral_competitivo,
            c.amazon_precio,
            c.fecha_foto,
            c.bb_es_mio,
            c.t7_es,
            c.t30_es,
            c.disponible_es,
            c.mi_precio_es,
            c.cobertura_dias_es,
            c.visitas,
            c.sesiones,
            c.conversion_pct,
            c.ratio_oferta_destacada,
            c.leido_at,
            c.saldo_uds_pais,
            c.stock_pais_uds,
            c.stock_foto,
            c.tiene_oferta,
            c.mi_precio_pais,
            c.sin_listing,
            c.oferta_foto,
            c.coste_leido_el,
            c.iva_aplicado,
            c.mi_precio,
            round((c.bb_precio / (1::numeric + c.iva_aplicado) - c.pvd - c.fee - c.bb_precio * (c.com_pct / 100::numeric) * c.k_com - c.fee * c.k_fee - 0.15) / NULLIF(c.bb_precio, 0::numeric) * 100::numeric, 2) AS margen_al_bb,
            round(c.bb_precio / (1::numeric + c.iva_aplicado) - c.pvd - c.fee - c.bb_precio * (c.com_pct / 100::numeric) * c.k_com - c.fee * c.k_fee - 0.15, 4) AS eur_ud_al_bb,
            round((c.mi_precio / (1::numeric + c.iva_aplicado) - c.pvd - c.fee - c.mi_precio * (c.com_pct / 100::numeric) * c.k_com - c.fee * c.k_fee - 0.15) / NULLIF(c.mi_precio, 0::numeric) * 100::numeric, 2) AS margen_hoy,
            round((c.pvd + c.fee + c.fee * c.k_fee + 0.15) / NULLIF(1::numeric / (1::numeric + c.iva_aplicado) - c.com_pct / 100::numeric * c.k_com, 0::numeric), 4) AS break_even,
                CASE
                    WHEN c.dominio <> 'es'::text THEN NULL::boolean
                    WHEN c.bb_precio IS NULL OR c.fee IS NULL THEN NULL::boolean
                    ELSE c.bb_precio >= 20::numeric AND c.fee < 4.00 AND COALESCE(c.mi_precio, 0::numeric) < 20::numeric
                END AS riesgo_acantilado
           FROM calc c
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
    com_pct AS comision_pct,
    iva_aplicado AS iva_pais,
    isd_regla,
    0.15 AS almacenamiento_eur,
    'constante_0_15'::text AS almacenamiento_origen,
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
        CASE
            WHEN bb_precio IS NULL THEN 'SIN_CAJA_ADJUDICADA'::text
            WHEN margen_al_bb IS NULL THEN 'SIN_MARGEN'::text
            WHEN bb_es_mio THEN 'CAJA_MIA'::text
            WHEN COALESCE(riesgo_acantilado, false) AND margen_al_bb >= 8::numeric THEN 'ATACABLE_REVISAR_FEE'::text
            WHEN margen_al_bb >= 8::numeric THEN 'ATACABLE_8'::text
            WHEN margen_al_bb >= 0::numeric THEN 'ATACABLE_FLOJO'::text
            ELSE 'ES_COSTE_NO_PRECIO'::text
        END AS veredicto,
        CASE
            WHEN bb_precio IS NOT NULL AND margen_al_bb IS NOT NULL THEN NULL::text
            WHEN bb_precio IS NULL THEN 'SIN_PRECIO_DE_CAJA_EN_LA_FOTO'::text
            WHEN pvd IS NULL THEN 'SIN_COSTE'::text
            WHEN fee IS NULL THEN 'SIN_FEE'::text
            WHEN com_pct IS NULL THEN 'SIN_COMISION'::text
            WHEN iva_aplicado IS NULL THEN 'IVA_REDUCIDO_NO_MAPEADO_FUERA_DE_ES'::text
            ELSE 'SIN_DATOS'::text
        END AS motivo_sin_datos,
    fecha_foto AS foto_keepa_el,
    leido_at::date AS demanda_leida_el,
    coste_leido_el::date AS coste_leido_el,
    LEAST(fecha_foto, coste_leido_el::date) AS margen_datado_el,
    riesgo_acantilado AS fee_riesgo_acantilado,
    categoria,
    stock_pais_uds,
    tiene_oferta AS tengo_oferta_pais,
    sin_listing AS sin_listing_pais,
    mi_precio_pais,
        CASE
            WHEN COALESCE(tiene_oferta, false) AND COALESCE(stock_pais_uds, 0::bigint) > 0 THEN 'OFERTA_Y_STOCK_ALLI'::text
            WHEN COALESCE(tiene_oferta, false) THEN 'OFERTA_SIN_STOCK_ALLI'::text
            WHEN COALESCE(sin_listing, false) THEN 'NI_LISTING'::text
            ELSE 'SIN_OFERTA'::text
        END AS presencia,
    stock_foto AS stock_leido_el,
    oferta_foto AS oferta_leida_el
   FROM m;

comment on view public.v_trackeador_precio_pais is 'Trackeador -> Cockpit. Grano ASIN x dominio (es/it/fr/de). Publica margen_al_bb, margen_hoy y break_even por pais con el IVA del mercado y el ISD correcto (ES/IT 3% sobre comision; FR 3% sobre comision Y tarifa FBA; DE sin medir - cero pedidos alemanes). pais_operativo=false en DE: sin NIF aleman a 13-ago-2026 (Fernando). El precio de la caja viaja SIEMPRE con su dueno (bb_vendedor, bb_es_mio). fee_origen dice si el fee es del maestro o estimado de Keepa. La frescura va desglosada: foto_keepa_el, demanda_leida_el, coste_leido_el y margen_datado_el = la mas vieja. Aditiva y security_invoker. El fee de Keepa sirve para PRIORIZAR, no para firmar un precio (doctrinas 74, 76 y 90).';

revoke all on public.v_trackeador_precio_pais from public, anon, authenticated;
grant all    on public.v_trackeador_precio_pais to service_role;
grant select on public.v_trackeador_precio_pais to authenticated;

create or replace view public.v_trackeador_precio_pais_full with (security_invoker = true) as
WITH paises(dominio, pais_operativo, iva_pais) AS (
         VALUES ('es'::text,true,0.21), ('it'::text,true,0.22), ('fr'::text,true,0.20), ('de'::text,true,0.19)
        ), nom AS (
         SELECT v_trackeador_precio_pais.asin,
            (array_agg(v_trackeador_precio_pais.nombre ORDER BY (v_trackeador_precio_pais.nombre IS NULL), v_trackeador_precio_pais.dominio))[1] AS nombre,
            (array_agg(v_trackeador_precio_pais.ean ORDER BY (v_trackeador_precio_pais.ean IS NULL), v_trackeador_precio_pais.dominio))[1] AS ean
           FROM v_trackeador_precio_pais
          WHERE v_trackeador_precio_pais.asin IS NOT NULL
          GROUP BY v_trackeador_precio_pais.asin
        ), coste AS (
         SELECT productos.asin,
            min(productos.pvd) AS pvd
           FROM productos
          WHERE productos.asin IS NOT NULL AND productos.pvd IS NOT NULL
          GROUP BY productos.asin
        ), catalogo AS (
         SELECT p.asin,
            COALESCE(n.nombre, min(p.nombre)) AS nombre,
            COALESCE(n.ean, min(p.ean)) AS ean
           FROM productos p
             LEFT JOIN nom n ON n.asin = p.asin
          WHERE p.asin IS NOT NULL AND p.estado = 'OK'::text
          GROUP BY p.asin, n.nombre, n.ean
        UNION
         SELECT nom.asin,
            nom.nombre,
            nom.ean
           FROM nom
        ), inv AS (
         SELECT inventario_internacional.asin,
            lower(inventario_internacional.country) AS dominio,
            sum(inventario_internacional.quantity) AS uds,
            max(inventario_internacional.fecha_foto) AS foto
           FROM inventario_internacional
          WHERE inventario_internacional.fecha_foto = (( SELECT max(inventario_internacional_1.fecha_foto) AS max
                   FROM inventario_internacional inventario_internacional_1))
          GROUP BY inventario_internacional.asin, (lower(inventario_internacional.country))
        ), fba_es AS (
         SELECT inventario_fba.asin,
            sum(inventario_fba.available) AS disponible,
            max(inventario_fba.fecha_foto) AS foto
           FROM inventario_fba
          WHERE inventario_fba.fecha_foto = (( SELECT max(inventario_fba_1.fecha_foto) AS max
                   FROM inventario_fba inventario_fba_1)) AND inventario_fba.asin IS NOT NULL
          GROUP BY inventario_fba.asin
        ), g AS (
         SELECT c.asin,
            p.dominio,
            p.pais_operativo,
            p.iva_pais,
            c.nombre,
            c.ean,
            iv.uds AS stock_pais_uds,
                CASE
                    WHEN p.dominio = 'es'::text THEN fe.disponible
                    ELSE NULL::bigint
                END AS disponible_es,
            COALESCE(iv.foto, fe.foto) AS stock_leido_el,
            co.pvd
           FROM catalogo c
             CROSS JOIN paises p
             LEFT JOIN inv iv ON iv.asin = c.asin AND iv.dominio = p.dominio
             LEFT JOIN fba_es fe ON fe.asin = c.asin
             LEFT JOIN coste co ON co.asin = c.asin
          WHERE NOT (EXISTS ( SELECT 1
                   FROM v_trackeador_precio_pais v
                  WHERE v.asin = c.asin AND v.dominio = p.dominio))
        )
 SELECT v_trackeador_precio_pais.asin,
    v_trackeador_precio_pais.ean,
    v_trackeador_precio_pais.dominio,
    v_trackeador_precio_pais.nombre,
    v_trackeador_precio_pais.pais_operativo,
    v_trackeador_precio_pais.bb_precio,
    v_trackeador_precio_pais.bb_vendedor,
    v_trackeador_precio_pais.bb_seller_id,
    v_trackeador_precio_pais.bb_es_mio,
    v_trackeador_precio_pais.bb_stock,
    v_trackeador_precio_pais.bb_pct_amazon_30d,
    v_trackeador_precio_pais.fba_min,
    v_trackeador_precio_pais.ofertas_nuevas_fba,
    v_trackeador_precio_pais.umbral_competitivo,
    v_trackeador_precio_pais.amazon_precio,
    v_trackeador_precio_pais.mi_precio,
    v_trackeador_precio_pais.margen_hoy,
    v_trackeador_precio_pais.margen_al_bb,
    v_trackeador_precio_pais.eur_ud_al_bb,
    v_trackeador_precio_pais.break_even,
    v_trackeador_precio_pais.fee,
    v_trackeador_precio_pais.fee_origen,
    v_trackeador_precio_pais.comision_pct,
    v_trackeador_precio_pais.iva_pais,
    v_trackeador_precio_pais.isd_regla,
    v_trackeador_precio_pais.almacenamiento_eur,
    v_trackeador_precio_pais.almacenamiento_origen,
    v_trackeador_precio_pais.pvd,
    v_trackeador_precio_pais.pvd_sospechoso,
    v_trackeador_precio_pais.t7_es,
    v_trackeador_precio_pais.t30_es,
    v_trackeador_precio_pais.disponible_es,
    v_trackeador_precio_pais.cobertura_dias_es,
    v_trackeador_precio_pais.saldo_uds_pais,
    v_trackeador_precio_pais.visitas,
    v_trackeador_precio_pais.sesiones,
    v_trackeador_precio_pais.conversion_pct,
    v_trackeador_precio_pais.ratio_oferta_destacada,
    v_trackeador_precio_pais.veredicto,
    v_trackeador_precio_pais.motivo_sin_datos,
    v_trackeador_precio_pais.foto_keepa_el,
    v_trackeador_precio_pais.demanda_leida_el,
    v_trackeador_precio_pais.coste_leido_el,
    v_trackeador_precio_pais.margen_datado_el,
    v_trackeador_precio_pais.fee_riesgo_acantilado,
    v_trackeador_precio_pais.categoria,
    v_trackeador_precio_pais.stock_pais_uds,
    v_trackeador_precio_pais.tengo_oferta_pais,
    v_trackeador_precio_pais.sin_listing_pais,
    v_trackeador_precio_pais.mi_precio_pais,
    v_trackeador_precio_pais.presencia,
    v_trackeador_precio_pais.stock_leido_el,
    v_trackeador_precio_pais.oferta_leida_el
   FROM v_trackeador_precio_pais
UNION ALL
 SELECT g.asin,
    g.ean,
    g.dominio,
    g.nombre,
    g.pais_operativo,
    NULL::numeric AS bb_precio,
    NULL::text AS bb_vendedor,
    NULL::text AS bb_seller_id,
    NULL::boolean AS bb_es_mio,
    NULL::integer AS bb_stock,
    NULL::numeric AS bb_pct_amazon_30d,
    NULL::text AS fba_min,
    NULL::integer AS ofertas_nuevas_fba,
    NULL::numeric AS umbral_competitivo,
    NULL::numeric AS amazon_precio,
    NULL::numeric AS mi_precio,
    NULL::numeric AS margen_hoy,
    NULL::numeric AS margen_al_bb,
    NULL::numeric AS eur_ud_al_bb,
    NULL::numeric AS break_even,
    NULL::numeric AS fee,
    NULL::text AS fee_origen,
    NULL::numeric AS comision_pct,
    g.iva_pais,
    NULL::text AS isd_regla,
    NULL::numeric AS almacenamiento_eur,
    NULL::text AS almacenamiento_origen,
    g.pvd,
    NULL::boolean AS pvd_sospechoso,
    NULL::bigint AS t7_es,
    NULL::bigint AS t30_es,
    g.disponible_es,
    NULL::numeric AS cobertura_dias_es,
    NULL::bigint AS saldo_uds_pais,
    NULL::integer AS visitas,
    NULL::integer AS sesiones,
    NULL::numeric AS conversion_pct,
    NULL::numeric AS ratio_oferta_destacada,
    NULL::text AS veredicto,
    'el ASIN no existe en el catalogo de este pais'::text AS motivo_sin_datos,
    NULL::date AS foto_keepa_el,
    NULL::date AS demanda_leida_el,
    NULL::date AS coste_leido_el,
    NULL::date AS margen_datado_el,
    NULL::boolean AS fee_riesgo_acantilado,
    NULL::text AS categoria,
    g.stock_pais_uds,
    false AS tengo_oferta_pais,
    true AS sin_listing_pais,
    NULL::numeric AS mi_precio_pais,
    'SIN_PAGINA'::text AS presencia,
    g.stock_leido_el,
    NULL::date AS oferta_leida_el
   FROM g;

revoke all on public.v_trackeador_precio_pais_full from public, anon, authenticated;
grant all    on public.v_trackeador_precio_pais_full to service_role;
grant select on public.v_trackeador_precio_pais_full to authenticated;

-- La gorda: 46.026 caracteres de definicion, copiados literales.
create or replace view public.v_trackeador_pantalla with (security_invoker = true) as
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
            min(e.pa) FILTER (WHERE e.presente) AS repone_pvp,
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
                    WHEN b.bb_precio IS NOT NULL AND b.bb_precio > 0.01 THEN round(((b.bb_precio - 0.01) / (1::numeric + b.iva_pais) - b.pvd - b.fee - (b.bb_precio - 0.01) * (b.comision_pct / 100::numeric) *
                    CASE
                        WHEN b.isd_regla ~~ 'com%'::text THEN 1.03
                        ELSE 1.00
                    END - b.fee *
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
                    WHEN 'LIQUIDA'::text THEN ceil(a.break_even * 100::numeric) / 100::numeric
                    WHEN 'AGUANTA'::text THEN a.mi_precio
                    WHEN 'NO PELEES'::text THEN a.mi_precio
                    WHEN 'SUBE'::text THEN ceil((a.pvd + a.fee + a.fee *
                    CASE
                        WHEN a.isd_regla = 'com_y_fba_3pct'::text THEN 0.03
                        ELSE 0::numeric
                    END + a.almacenamiento_eur) / NULLIF(1::numeric / (1::numeric + a.iva_pais) - a.comision_pct / 100::numeric *
                    CASE
                        WHEN a.isd_regla ~~ 'com%'::text THEN 1.03
                        ELSE 1.00
                    END - 0.08, 0::numeric) * 100::numeric) / 100::numeric
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
            round((q.precio_recomendado / (1::numeric + q.iva_pais) - q.pvd - (q.fee +
                CASE
                    WHEN q.dominio = 'es'::text AND q.precio_recomendado >= 20::numeric AND COALESCE(q.mi_precio, 0::numeric) < 20::numeric THEN 0.50
                    ELSE 0::numeric
                END) - q.precio_recomendado * (q.comision_pct / 100::numeric) *
                CASE
                    WHEN q.isd_regla ~~ 'com%'::text THEN 1.03
                    ELSE 1.00
                END - (q.fee +
                CASE
                    WHEN q.dominio = 'es'::text AND q.precio_recomendado >= 20::numeric AND COALESCE(q.mi_precio, 0::numeric) < 20::numeric THEN 0.50
                    ELSE 0::numeric
                END) *
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

revoke all on public.v_trackeador_pantalla from public, anon, authenticated;
grant all    on public.v_trackeador_pantalla to service_role;
grant select on public.v_trackeador_pantalla to authenticated;

-- -- 3) LA MATERIALIZADA Y SUS CUATRO INDICES -------------------------------
-- Es la copia de v_trackeador_pantalla + clock_timestamp(). La lee la app v2.
create materialized view if not exists public.mv_trackeador_pantalla as
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
    trabajo_fila,
    clock_timestamp() AS refrescada_el
   FROM v_trackeador_pantalla v;

-- 🔴 mv_tp_pk es el UNIQUE sin el cual `refresh ... concurrently` NO ARRANCA.
create unique index if not exists mv_tp_pk     on public.mv_trackeador_pantalla using btree (asin, dominio);
create        index if not exists mv_tp_orden  on public.mv_trackeador_pantalla using btree (bloque, orden_en_bloque);
create        index if not exists mv_tp_accion on public.mv_trackeador_pantalla using btree (accion);
create        index if not exists mv_tp_asin   on public.mv_trackeador_pantalla using btree (asin);

revoke all on public.mv_trackeador_pantalla from public, anon, authenticated;
grant all    on public.mv_trackeador_pantalla to service_role;
grant select on public.mv_trackeador_pantalla to authenticated;

-- -- 4) LAS FUNCIONES Y LA VISTA DE FRESCURA ---------------------------------
-- 🔴 Las dos DEFINER van con EXECUTE a PUBLIC porque es lo que hay vivo hoy.
--    Frente propio, no se toca aqui.
CREATE OR REPLACE FUNCTION public.fn_fee_override_refresh()
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare n integer;
begin
  delete from public.fee_override;
  insert into public.fee_override (asin, dominio, fee_eur, origen, medido_el, nota)
  select k.asin, lower(k.dominio), round(k.tarifa_fba + 3.47, 2), 'efn_fuera_de_paneu', current_date,
         'no inscrito en Pan-EU en este pais: se sirve por EFN desde Espana. Delta +3,47 EUR = 6,71 (8,12 de factura de amazon.de sin el 21% de IVA) menos 3,24 de tarifa domestica.'
  from public.keepa_escaparate k
  left join (
    select coalesce(l.asin, pr.asin) asin, lower(o.pais) dominio,
           bool_or(coalesce(o.beneficios_paneu,false)) paneu
    from public.paneu_oferta_pais o
    left join public.listings_amazon l on l.seller_sku = o.seller_sku
    left join public.productos pr on pr.sku = o.seller_sku
    where o.snapshot_date = (select max(snapshot_date) from public.paneu_oferta_pais)
    group by 1,2
  ) i on i.asin = k.asin and i.dominio = lower(k.dominio)
  where lower(k.dominio) in ('it','fr','de')
    and not coalesce(i.paneu, false)
    and k.tarifa_fba is not null;
  get diagnostics n = row_count;
  return n;
end $function$;

revoke all on function public.fn_fee_override_refresh() from public, anon, authenticated;
grant execute on function public.fn_fee_override_refresh() to public;
grant execute on function public.fn_fee_override_refresh() to service_role;

CREATE OR REPLACE FUNCTION public.fn_trackeador_frescura(p_horas_refresco numeric DEFAULT 26, p_dias_normal integer DEFAULT 2, p_dias_demanda integer DEFAULT 14, p_dias_compra integer DEFAULT 120, p_dias_copia integer DEFAULT 0)
 RETURNS TABLE(refrescada_el timestamp with time zone, horas_refresco numeric, foto_keepa_el date, dias_keepa integer, demanda_leida_el date, dias_demanda integer, margen_datado_el date, dias_margen integer, stock_leido_el date, dias_stock integer, oferta_leida_el date, dias_oferta integer, historico_hasta date, ultimo_refresco_ok boolean, ultimo_refresco_error text, ventas_copia_hasta date, ventas_dias_por_detras integer, stock_fuente_hasta date, stock_dias_por_detras integer, hay_aviso boolean, aviso text)
 LANGUAGE sql
 STABLE
AS $function$
  with p as materialized (
    select max(refrescada_el) as refrescada_el, max(foto_keepa_el) as foto_keepa_el,
           max(demanda_leida_el) as demanda_leida_el, max(margen_datado_el) as margen_datado_el,
           max(stock_leido_el) as stock_leido_el, max(oferta_leida_el) as oferta_leida_el
    from public.mv_trackeador_pantalla
  ), c as materialized (
    select max(ventana_hasta_ledger) as copia_ledger, max(ventana_hasta_marketplace) as copia_mkt
    from public.mv_ventas_ventanas
  ), r as materialized (
    select ok, error from public.trackeador_refrescos order by id desc limit 1
  ), f as materialized (
    select p.*, c.copia_ledger, c.copia_mkt,
           (select max(h.fecha) from public.trackeador_hist h)           as historico_hasta,
           (select ok    from r)                                         as ultimo_refresco_ok,
           (select error from r)                                         as ultimo_refresco_error,
           (select max(l.fecha) from public.ledger_movimientos l)        as vivo_ledger,
           (select max(t.fecha) from public.transacciones_movimientos t) as vivo_mkt,
           (select max(i.fecha_foto) from public.inventario_fba i)       as vivo_stock
    from p, c
  ), d as materialized (
    select f.*,
      round(extract(epoch from now()-f.refrescada_el)/3600,1) as horas_refresco,
      (current_date - f.foto_keepa_el) as dias_keepa, (current_date - f.demanda_leida_el) as dias_demanda,
      (current_date - f.margen_datado_el) as dias_margen, (current_date - f.stock_leido_el) as dias_stock,
      (current_date - f.oferta_leida_el) as dias_oferta,
      greatest(coalesce(f.vivo_ledger - f.copia_ledger,0), coalesce(f.vivo_mkt - f.copia_mkt,0)) as dias_copia_detras,
      coalesce(f.vivo_stock - f.stock_leido_el, 0) as dias_stock_detras
    from f
  ), a as materialized (
    select d.*, array_remove(array[
      case when d.horas_refresco > p_horas_refresco or coalesce(d.ultimo_refresco_ok,false) = false
           then 'la pantalla no se ha refrescado (' || d.horas_refresco || ' h)' end,
      case when d.dias_keepa  > p_dias_normal then 'la foto de Keepa es de hace ' || d.dias_keepa  || ' días' end,
      case when d.dias_stock  > p_dias_normal then 'el stock es de hace '         || d.dias_stock  || ' días' end,
      case when d.dias_oferta > p_dias_normal then 'las ofertas son de hace '     || d.dias_oferta || ' días' end,
      case when d.dias_demanda > p_dias_demanda then 'la demanda de Amazon lleva ' || d.dias_demanda || ' días sin actualizarse (suele tardar 7-10)' end,
      case when d.dias_margen > p_dias_compra then 'la última compra registrada es del '
             || to_char(d.margen_datado_el,'DD-MM-YYYY') || ' (' || d.dias_margen
             || ' días): o se dejó de comprar, o el fichero de compras no está entrando' end,
      case when d.dias_copia_detras > p_dias_copia
           then 'la copia de ventas va ' || d.dias_copia_detras
                || ' días por detrás del dato vivo: esta pantalla se recalculó sobre ventas viejas aunque su sello diga que está fresca' end,
      case when d.dias_stock_detras > 0
           then 'HAY STOCK MÁS NUEVO SIN USAR: el informe de inventario de la base es del '
                || to_char(d.vivo_stock,'DD-MM') || ' y la pantalla decide con el del '
                || to_char(d.stock_leido_el,'DD-MM') || '. Refrescar antes de recomendar nada' end
    ], null) as avisos
    from d
  )
  select a.refrescada_el, a.horas_refresco, a.foto_keepa_el, a.dias_keepa, a.demanda_leida_el, a.dias_demanda,
         a.margen_datado_el, a.dias_margen, a.stock_leido_el, a.dias_stock, a.oferta_leida_el, a.dias_oferta,
         a.historico_hasta, a.ultimo_refresco_ok, a.ultimo_refresco_error,
         least(a.copia_ledger, a.copia_mkt), a.dias_copia_detras,
         a.vivo_stock, a.dias_stock_detras,
         (cardinality(a.avisos) > 0), nullif(array_to_string(a.avisos, ' · '), '')
  from a;
$function$;

revoke all on function public.fn_trackeador_frescura(numeric, integer, integer, integer, integer) from public, anon, authenticated;
grant execute on function public.fn_trackeador_frescura(numeric, integer, integer, integer, integer) to public;
grant execute on function public.fn_trackeador_frescura(numeric, integer, integer, integer, integer) to service_role;

-- v_trackeador_frescura es SOLO un envoltorio de la funcion de arriba.
create or replace view public.v_trackeador_frescura with (security_invoker = true) as
SELECT refrescada_el,
    horas_refresco,
    foto_keepa_el,
    dias_keepa,
    demanda_leida_el,
    dias_demanda,
    margen_datado_el,
    dias_margen,
    stock_leido_el,
    dias_stock,
    oferta_leida_el,
    dias_oferta,
    historico_hasta,
    ultimo_refresco_ok,
    ultimo_refresco_error,
    ventas_copia_hasta,
    ventas_dias_por_detras,
    stock_fuente_hasta,
    stock_dias_por_detras,
    hay_aviso,
    aviso
   FROM fn_trackeador_frescura() fn_trackeador_frescura(refrescada_el, horas_refresco, foto_keepa_el, dias_keepa, demanda_leida_el, dias_demanda, margen_datado_el, dias_margen, stock_leido_el, dias_stock, oferta_leida_el, dias_oferta, historico_hasta, ultimo_refresco_ok, ultimo_refresco_error, ventas_copia_hasta, ventas_dias_por_detras, stock_fuente_hasta, stock_dias_por_detras, hay_aviso, aviso);

revoke all on public.v_trackeador_frescura from public, anon, authenticated;
grant all    on public.v_trackeador_frescura to service_role;
grant select on public.v_trackeador_frescura to authenticated;

CREATE OR REPLACE FUNCTION public.fn_trackeador_refrescar(p_relanzar boolean DEFAULT true)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
-- UNA sola funcion, DOS comportamientos. No dos funciones que hacen casi lo mismo:
-- eso seria la misma regla escrita en dos sitios, que es de donde salen los fallos.
--   p_relanzar = true  (cron 19:45): si falla, GRITA. Quiero que el cron se vea rojo.
--   p_relanzar = false (llamada desde refrescar_vistas del chat de la App): si falla,
--     registra, devuelve 'ERROR: ...' y NO relanza, para que su log tenga el texto
--     de nuestro fallo en vez de una excepcion tragada.
-- OJO: que ellos NO dependan de esto. Su refrescar_vistas() se traga cualquier
-- excepcion de cualquier cosa que llame, y hace bien: una garantia que depende de
-- que el llamado sea educado no es una garantia. Esto es diagnostico, no proteccion.
declare n integer; id_log bigint; t0 timestamptz := clock_timestamp();
begin
  insert into public.trackeador_refrescos default values returning id into id_log;
  begin
    perform public.fn_fee_override_refresh();
    refresh materialized view concurrently public.mv_trackeador_pantalla;
    select count(*) into n from public.mv_trackeador_pantalla;
    if n < 1000 then
      raise exception 'refresco sospechoso: solo % filas', n;
    end if;
    update public.trackeador_refrescos
       set acabo_el = clock_timestamp(), filas = n, ok = true where id = id_log;
    return n || ' filas en ' || round(extract(epoch from clock_timestamp()-t0)::numeric,1) || ' s';
  exception when others then
    update public.trackeador_refrescos
       set acabo_el = clock_timestamp(), ok = false, error = sqlerrm where id = id_log;
    if p_relanzar then raise; end if;
    return 'ERROR: ' || sqlerrm;
  end;
end $function$;

revoke all on function public.fn_trackeador_refrescar(boolean) from public, anon, authenticated;
grant execute on function public.fn_trackeador_refrescar(boolean) to public;
grant execute on function public.fn_trackeador_refrescar(boolean) to service_role;

-- -- TESTIGOS ----------------------------------------------------------------
DO $testigo$
DECLARE
    n_obj   int;
    n_idx   int;
    n_uni   int;
    n_def   int;
    tiene   boolean;
BEGIN
    SELECT count(*) INTO n_obj FROM (
        SELECT 1 FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE ns.nspname = 'public' AND c.relname IN
               ('v_trackeador_precio_pais','v_trackeador_precio_pais_full','v_trackeador_pantalla',
                'mv_trackeador_pantalla','v_trackeador_frescura','trackeador_refrescos')
        UNION ALL
        SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
         WHERE ns.nspname = 'public' AND p.proname IN
               ('fn_fee_override_refresh','fn_trackeador_frescura','fn_trackeador_refrescar')) z;
    IF n_obj <> 9 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban 9 objetos y hay %.', n_obj;
    END IF;

    SELECT count(*) INTO n_idx FROM pg_indexes
     WHERE schemaname = 'public' AND tablename = 'mv_trackeador_pantalla';
    SELECT count(*) INTO n_uni FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
     WHERE i.indrelid = 'public.mv_trackeador_pantalla'::regclass
       AND i.indisunique AND c.relname = 'mv_tp_pk';
    IF n_uni <> 1 THEN
        RAISE EXCEPTION 'ABORTA: mv_trackeador_pantalla NO tiene el indice UNIQUE mv_tp_pk. Sin el, `refresh materialized view concurrently` no arranca y fn_trackeador_refrescar falla en cada carga de cada informe.';
    END IF;
    IF n_idx <> 4 THEN
        RAISE EXCEPTION 'ABORTA: mv_trackeador_pantalla tiene % indices y se esperaban 4.', n_idx;
    END IF;

    -- La foto incluye el SECURITY DEFINER: si alguna dejara de serlo, este
    -- fichero ya no reproduce produccion y hay que enterarse.
    SELECT count(*) INTO n_def FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname = 'public' AND p.proname IN ('fn_fee_override_refresh','fn_trackeador_refrescar')
       AND p.prosecdef;
    IF n_def <> 2 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban 2 funciones SECURITY DEFINER y hay %.', n_def;
    END IF;

    -- Y el default de p_relanzar, que es lo que separa el cron (grita) de la
    -- llamada de la app (registra y devuelve el texto). Se ancla en el DEFAULT,
    -- no en el nombre del parametro: el nombre esta en las dos versiones.
    SELECT pg_get_function_arguments(p.oid) LIKE '%DEFAULT true%' INTO tiene
      FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
     WHERE ns.nspname = 'public' AND p.proname = 'fn_trackeador_refrescar';
    IF NOT tiene THEN
        RAISE EXCEPTION 'ABORTA: fn_trackeador_refrescar ha perdido el DEFAULT true de p_relanzar.';
    END IF;

    RAISE NOTICE 'Testigo OK. 9 objetos, 4 indices (mv_tp_pk UNIQUE puesto), 2 DEFINER, default de p_relanzar vivo.';
END
$testigo$;

-- La puerta, EJERCIDA. El catalogo dice lo que esta escrito; esto dice lo que
-- pasa. `limit 0` basta: el permiso se comprueba al abrir la relacion, antes de
-- calcular una sola fila -- y estas vistas son caras.
DO $puerta_anon$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_trackeador_pantalla' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_trackeador_pantalla (% filas). La puerta esta abierta.', n;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA en mv_trackeador_pantalla.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM (SELECT 1 FROM public.mv_trackeador_pantalla LIMIT 1) z' INTO n;
    EXECUTE 'SELECT count(*) FROM (SELECT * FROM public.v_trackeador_pantalla LIMIT 0) z' INTO n;
    EXECUTE 'SELECT count(*) FROM (SELECT * FROM public.v_trackeador_frescura LIMIT 0) z' INTO n;
    RESET ROLE;
    RAISE NOTICE 'Testigo OK (puerta). authenticated entra en la materializada, en la vista y en la frescura.';
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer. La pantalla del Trackeador se quedaria vacia.';
END
$puerta_auth$;

-- ============================================================================
-- COMO COMPROBAR QUE ESTO SIGUE SIENDO LA FOTO
-- ----------------------------------------------------------------------------
-- Estas huellas son las de PRODUCCION medidas el 28-ago-2026. Si manana alguien
-- cambia un objeto vivo sin pasar por aqui, este fichero deja de reproducirlo y
-- la unica forma de enterarse es contrastar. El md5 es el juez.
--
--   select c.relname, md5(pg_get_viewdef(c.oid,true)) , length(pg_get_viewdef(c.oid,true))
--     from pg_class c join pg_namespace n on n.oid=c.relnamespace
--    where n.nspname='public' and c.relname in (<las vistas de abajo>)
--   union all
--   select p.proname, md5(p.prosrc), length(p.prosrc)
--     from pg_proc p join pg_namespace n on n.oid=p.pronamespace
--    where n.nspname='public' and p.proname in (<las funciones de abajo>);
--
-- ⚠️ AL COMPARAR CONTRA EL FICHERO, NORMALIZA CRLF -> LF. Y ojo: un CR SUELTO
--    no es un final de linea, es DATO -- `v_reglas_arranque` y
--    `v_sondas_arranque` llevan uno dentro de una cadena. Convertirlo cambia la
--    vista. Por eso el repo lleva `migraciones/*.sql -text` en .gitattributes.
--
-- | objeto | md5 | largo |
-- |---|---|---|
-- | `v_trackeador_precio_pais` | `66319d0826ba4ccc62ac5391daff619b` | 17046 |
-- | `v_trackeador_precio_pais_full` | `71a2888d749a6586cc656e3ce812393a` | 7203 |
-- | `v_trackeador_pantalla` | `8cc855a9d7d3fff92c54ca7d0d387ecf` | 46026 |
-- | `mv_trackeador_pantalla` | `ca8e0c1c319d916a51acfd651f311383` | 2070 |
-- | `v_trackeador_frescura` | `d1f613c471881da9ffa9bf3083f04c70` | 831 |
-- | `fn_fee_override_refresh` | `54ef7e432e687adb0d9a3f1402f231c8` | 1094 |
-- | `fn_trackeador_frescura` | `3f9741b060abe2352d437c8ae59c9477` | 3954 |
-- | `fn_trackeador_refrescar` | `3a6351e01be5d37ffaeb03d282fff5a1` | 1638 |
-- ============================================================================
