-- ============================================================================
-- v_trackeador_pantalla — LA ESCALERA DEL DISPONIBLE: leido → estimado →
-- vendible en las SEIS decisiones.                                 7-sep-2026
-- (paso 2c de los cuatro del plan; el 2a fue salud y el 2b esta misma vista)
-- ----------------------------------------------------------------------------
-- POR QUE. El 2b puso un SUELO provisional en las seis decisiones que dependen de
--   `stock_fba_eu`: `COALESCE(stock_fba_eu, stock_vendible)`. Nacio con fecha de
--   caducidad escrita en sus propios comentarios, porque el vendible SIEMPRE se
--   queda corto: deja fuera el transito entre centros. Medido sobre los 11 dias
--   del historico, quedarse en el vendible pierde 3.080 unidades, y siempre por
--   debajo. Eso decide reposiciones y, desde hoy, tambien precios.
--   El paso 1 construyo el puente —`inventario_fba.disponible_estimado`— y ya
--   esta relleno en produccion (aplicado el 7-sep a las 15:47:47: 381 filas con
--   origen 'leido' y 244 con cifra en la foto viva; 4.042 y 2.530 en el
--   historico). Este fichero mete ese puente como PELDAÑO DE EN MEDIO.
--
-- LA ESCALERA, y que significa cada peldaño:
--       COALESCE(stock_fba_eu, stock_estimado, stock_vendible)
--     1) `stock_fba_eu`   — vendible + transito LEIDO. Si el informe lo trae, manda
--                           el dato leido y la escalera no baja.
--     2) `stock_estimado` — el puente: available + max(0, internacional − entrantes
--                           − available), agregado por ASIN. Solo se pisa cuando no
--                           hay lectura del transito.
--     3) `stock_vendible` — 🔴 EL ULTIMO PELDAÑO, NO EL UNICO. Se pisa cuando no hay
--                           ni lectura ni puente, y entonces la cifra se queda corta
--                           a sabiendas. Queda dicho en los seis sitios del codigo y
--                           en el COMMENT de la columna, para que dentro de tres
--                           meses nadie lo lea como «el vendible es el suelo».
--
-- 🔴 DECIDIDO POR FERNANDO EL 7-SEP, Y ESCRITO AQUI PARA QUE NO SE REDISCUTA: la
--   escalera va en LAS SEIS, tambien en las dos que mueven PRECIO (COMPROBAR y
--   LIQUIDA). Por la mañana se propuso lo contrario —que el precio exigiera dato
--   CIERTO— y la medicion lo tumbo: con el informe recortado NINGUNA ficha tendra
--   disponible leido, asi que exigir dato cierto dejaria la pantalla ENTERA en
--   COMPROBAR durante el mes que dura el transito a la API.
--   El riesgo que se acepta esta medido, no supuesto: el estimado se pasa en 7
--   fichas de 243 (33 uds), y una bajada de precio sobre stock que no existe no
--   vende nada. El daño de lo contrario si es real: fichas CON stock que dejan de
--   defenderse en precio, y reposiciones falsas.
--
-- ⚠️ ESTO CAMBIA UNA FRASE ESCRITA HOY MISMO, y se dice en voz alta en vez de
--   dejarla contradicha en silencio. `2026-09-07_inventario_fba_disponible_estimado.sql`
--   dice: «EL PRECIO NO LO TOCA. La sesion de precios usa el disponible LEIDO […]
--   Esta columna la leen la pantalla de reposicion y la de cobertura, y nadie mas».
--   Desde este fichero la lee TAMBIEN la pantalla de precios, por la decision de
--   arriba y MIENTRAS DURE EL TRANSITO. El liston de este trabajo es un mes —la
--   conexion a la API—, no el diseño definitivo.
--
-- 🔴 CÓMO SE REVISA ESTE FICHERO, porque son 1.309 lineas de vista y casi todas
--   son arrastre de columnas entre los diez CTE encadenados. **El texto es el de
--   `pg_get_viewdef('public.v_trackeador_pantalla', true)` de produccion del
--   7-sep-2026 —46.643 caracteres, md5 d059326d6c53cdc0c3c39e7143408822— mas
--   QUINCE cambios, todos con la marca `⇐ CAMBIO`:**
--       grep -n 'CAMBIO' migraciones/2026-09-07_trackeador_escalera_disponible.sql
--
--   GRUPO A · el peldaño nuevo y su viaje hasta las decisiones (CAMBIO 1..9)
--     · CAMBIO 1 — el agregado por ASIN en el CTE `stock_fba`, con el MISMO
--       guardado que ya usa `v_salud_asin` para el suyo:
--           CASE WHEN count(*) = count(disponible_estimado)
--                THEN sum(disponible_estimado) END
--       Si a una sola fila del ASIN le falta el estimado, el total del ASIN es
--       NULO y la escalera baja al vendible. 🔴 No se usa GREATEST: GREATEST y
--       LEAST **ignoran los nulos**, o sea que convierten un «no lo se» en una
--       afirmacion y no lo caza ninguna guarda. Es el mismo cuchillo que obligo a
--       poner los seis suelos en el 2b.
--     · CAMBIO 2 — el peldaño entra en el CTE `base` como `stock_estimado`.
--     · CAMBIO 3..9 — el arrastre por `calc`, `acc`, `pre`, `pre2`, `fin`, `fila`
--       y `fila2`. Sin el, la columna no llega a donde se decide.
--
--   GRUPO B · las seis decisiones (CAMBIO 10..15), que son SIETE usos:
--       10-11 · `no_estas_causa` — la condicion y el texto del almacenaje (2 usos)
--       12    · `accion` → COMPROBAR (dentro del GREATEST con `stock_moloka`)
--       13    · `accion` → LIQUIDA
--       14    · `presencia_detalle` → 'ficha_retirada'
--       15    · `trabajo_pendiente` → 'reclamar la ficha'
--     Los comentarios de «SUELO TEMPORAL» del 2b se han ido: ya no hay suelo, hay
--     escalera. Lo que queda escrito en su sitio es que el vendible es el ULTIMO
--     peldaño, no el unico.
--
-- 🔒 NO SE AÑADE NINGUNA COLUMNA A LA VISTA, y es deliberado. `stock_estimado`
--   viaja por dentro de los CTE y muere en `fila3`: no sale al SELECT final. Dos
--   motivos: (1) `mv_trackeador_pantalla` cuelga de esta vista —medido con
--   `pg_depend` el 7-sep, y es la UNICA que cuelga—, y añadir columnas obliga a
--   tocarla; una materializada recreada **nace VACIA sin dar error** y dejaria el
--   Trackeador de Elena en blanco. (2) Con las columnas intactas, la huella de las
--   filas ENTERAS vale como guarda, y es la prueba mas fuerte que hay aqui.
--   Marcar en pantalla lo estimado es el paso 3 y va en su propio encargo.
--
-- 🔬 LA TRANSCRIPCION ESTA PROBADA BYTE A BYTE, no «revisada». El fichero se genero
--   con un script a partir del viewdef de produccion, y despues se INVIRTIERON los
--   quince cambios sobre el resultado: el texto que sale es identico al de
--   produccion —1.243 lineas, 46.643 caracteres, md5
--   d059326d6c53cdc0c3c39e7143408822—. O sea que esto es el viewdef de produccion
--   MAS los quince cambios marcados, y nada mas. Si se hubiera movido una coma por
--   descuido, ese md5 no cuadraria. La vuelta atras es ese mismo texto, literal.
--
-- 🔬 LA PRUEBA DE QUE HOY NO PUEDE CAMBIAR NADA. El transito viene LEIDO en las 381
--   filas de la foto viva, asi que `stock_fba_eu` no es nulo en ningun ASIN y la
--   escalera NUNCA baja de peldaño. La vista nueva tiene que dar exactamente lo
--   mismo que la vieja: mismas filas, misma huella de la fila entera, mismo
--   recuento de acciones POR DOMINIO y mismas fichas POR BLOQUE. Si algo se mueve,
--   el cambio esta mal y esto ABORTA. Y no hay ni un numero de produccion escrito a
--   mano: se fotografia el ANTES en el bloque 0 y se compara contra el. Es la
--   leccion del 2b, que abortaba en staging por tener 1.708 filas y no 1.776.
--
-- 🔬 Y EL PELDAÑO SE HA PROBADO APARTE, con una simulacion que finge el informe
--   recortado (`fc_transfer` a NULO) sobre la foto viva del 6-sep en PRODUCCION,
--   sin escribir nada:
--     · Con el SUELO del 2b, 4 ASIN pasan de «tiene stock» a «no tiene», porque
--       todo su stock esta en transito y su vendible es 0:
--           B003UWY00Q (1 ud) · B09V85CK5Q (6) · B0BCFMZ8WR (12) · B0CDJGVPCL (2)
--     · Con la ESCALERA el puente recupera TRES de los cuatro:
--           B003UWY00Q (estimado 1) · B0BCFMZ8WR (12) · B0CDJGVPCL (2)
--       ⚠️ El encargo esperaba DOS (B0BCFMZ8WR y B0CDJGVPCL). Son tres, medido el
--       7-sep contra la tabla ya rellenada: `B003UWY00Q` tiene un unico SKU con
--       available 0, fc_transfer 1 y disponible_estimado 1.
--     · El que NO se recupera es `B09V85CK5Q`, y por un motivo correcto: sus 6
--       unidades estan en `inbound_shipped` y el puente RESTA los entrantes para no
--       contarlos dos veces, asi que su estimado es 0. El puente no se inventa nada.
--     La consulta esta al final del fichero, para poder repetirla.
--
-- 🔬 Y SE HA CORRIDO EN STAGING ANTES DE ABRIR EL PR, con los quince cambios
--   aplicados dentro de una transaccion terminada en ROLLBACK y sin dejar nada
--   detras (comprobado despues: el viewdef de staging sigue en su md5 de partida).
--   Paso todo: 1.708 filas con la huella intacta, las acciones por dominio y los
--   bloques sin mover una ficha, 6 escaleras y 0 suelos, la vista dependiendo de
--   `inventario_fba.disponible_estimado`, y 27 vistas con `security_invoker`, las
--   mismas de antes. Con la misma secuencia se probo la VUELTA ATRAS: aplicar esto
--   y revertirlo devuelve el texto de la vista a su md5 exacto de partida.
--   ⚠️ Esto NO sustituye a la escalera —el ensayo que vale es el del workflow desde
--   `main`, contra el fichero, y va igual—. Solo adelanta los errores tontos, y
--   adelanto uno: la columna `n` de la tabla temporal chocaba con la variable `n`
--   del bloque DO y Postgres abortaba con «column reference "n" is ambiguous».
--   Leyendo el fichero no se ve; corriendolo, si.
--
-- 🔒 QUE **NO** TOCA ESTE FICHERO:
--     · `mv_trackeador_pantalla`. Ni se recrea ni se refresca: no cambia ninguna
--       columna y hoy no cambia ningun valor, asi que lo que tiene guardado ya es
--       lo que produce la vista nueva. Lo recogera en su refresco de siempre.
--     · La Guarda 12 del procesador. La carga sigue CERRADA. Se abre en el paso 4
--       (encargo F), y ese paso no se hace hasta que este este dentro: abrir con el
--       suelo puesto y sin el estimado daria reposiciones con un disponible corto.
--     · Los permisos, la RLS, `inventario_fba` y el procesador. De
--       `security_invoker` solo se hace lo que dice el parrafo siguiente.
--
-- 🔴 `CREATE OR REPLACE VIEW` **BORRA LAS OPCIONES DE LA VISTA**, `security_invoker`
--   incluido. No es una suposicion: lo cazo el numero de control del 2b en el
--   ensayo de staging del 7-sep-2026, con `reloptions: (sin opciones)` despues del
--   REPLACE. Por eso hay un `ALTER VIEW ... SET (security_invoker=true)` justo
--   detras, y por eso la guarda lo comprueba —y comprueba ademas que el numero de
--   vistas del esquema con la opcion puesta sigue siendo el de antes. En produccion
--   son 27 de 54; en staging es otro numero, y por eso se FOTOGRAFIA en vez de
--   escribirlo a mano.
--   ⚠️ Sin esa guarda, la vista volveria a leer con los permisos de su dueño
--   (`postgres`) saltandose la RLS, en silencio y sin que nada fallara. Una opcion
--   de seguridad que se pierde no da error: deja de proteger.
--
-- ESCALERA: staging ensayo → staging aplicar → verificacion por SQL → produccion
--   ensayo → produccion aplicar → verificacion por SQL → Fernando abre la pantalla.
--   ⚠️ SIN RESTAURAR STAGING, y con la medicion delante, que es lo unico que
--   permite saltarselo: el ultimo volcado es de esta mañana (09:19) y todo lo que
--   esta migracion NECESITA nacio despues —`inventario_fba.disponible_estimado`
--   (PR #287, fusionado a las 15:33) y la vista con los seis suelos del 2b (PR
--   #283, 13:30)—. Restaurar borraria el suelo sobre el que se iba a ensayar y la
--   guarda 0 abortaria por una causa que no tiene nada que ver con este cambio.
--   🔑 La regla no se desactiva: se esquiva el dia en que el volcado va POR DETRAS
--   de la base, y vuelve entera en cuanto haya un volcado posterior.
-- ============================================================================

-- ── 0) LA FOTO DEL «ANTES», que es lo que hace verificable la transcripcion ──
-- 🔑 Ni una cifra de produccion escrita a mano. La invariante no es «1.776 filas»:
--    es «EXACTAMENTE LO MISMO QUE ANTES, sea lo que sea en esta base». Hoy el
--    transito se conoce en todas las fichas, asi que la escalera no baja de peldaño
--    y la vista nueva tiene que dar lo mismo que la vieja en CUALQUIER entorno.
--    Escribir aqui las 1.776 filas de produccion es lo que hizo abortar el ensayo
--    del 2b en staging, que tiene 1.708. Una guarda que salta por una causa
--    distinta de la que dice medir no es una guarda.
CREATE TEMP TABLE _pantalla_antes ON COMMIT DROP AS
SELECT count(*) AS filas,
       md5(string_agg(t::text, chr(10) ORDER BY t.asin, t.dominio)) AS huella,
       sum(t.stock_fba_eu) AS suma_stock_fba_eu,
       sum(t.stock_fc_transfer) AS suma_fc_transfer,
       count(*) FILTER (WHERE t.accion = 'COMPROBAR') AS n_comprobar,
       count(*) FILTER (WHERE t.accion = 'LIQUIDA') AS n_liquida,
       count(*) FILTER (WHERE t.presencia_detalle = 'ficha_retirada') AS n_retirada,
       count(*) FILTER (WHERE t.trabajo_pendiente = 'reclamar la ficha') AS n_reclamar
  FROM public.v_trackeador_pantalla t;

-- Las dos tablas que pide el encargo por su nombre: el recuento de acciones POR
-- DOMINIO y las fichas de CADA BLOQUE. La huella de arriba ya las cubre, pero
-- separadas dicen QUE se ha movido, no solo que algo se ha movido.
-- 🔴 La columna se llama `fichas` y no `n` a proposito: dentro del bloque DO hay
--    una variable `n`, y Postgres aborta con «column reference "n" is ambiguous».
--    Lo cazo el ensayo en staging del 7-sep, no la lectura.
CREATE TEMP TABLE _acciones_antes ON COMMIT DROP AS
SELECT t.dominio, t.accion, count(*) AS fichas
  FROM public.v_trackeador_pantalla t GROUP BY 1, 2;

CREATE TEMP TABLE _bloques_antes ON COMMIT DROP AS
SELECT t.bloque, count(*) AS fichas
  FROM public.v_trackeador_pantalla t GROUP BY 1;

-- Y las vistas del esquema que llevan `security_invoker` puesto, ANTES de tocar
-- nada. 🔴 Se fotografia en vez de escribir «27»: en produccion son 27 de 54 y en
-- staging es otro numero, y un numero a pelo abortaria por diferencia de entornos.
CREATE TEMP TABLE _invoker_antes ON COMMIT DROP AS
SELECT count(*) FILTER (WHERE c.relkind = 'v') AS vistas,
       count(*) FILTER (WHERE c.relkind = 'v'
                          AND array_to_string(c.reloptions, ',') LIKE '%security_invoker=true%') AS con_invoker
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public';

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
                CASE
                    WHEN count(*) = count(i.fc_transfer) THEN sum(i.fc_transfer)
                    ELSE NULL::bigint
                END AS uds_fc_transfer,
                -- ⇐ CAMBIO 1 · EL PELDAÑO NUEVO: el estimado agregado por ASIN, con el
                --   mismo guardado que el transito. Si a UNA de las filas del ASIN le falta
                --   el estimado, el total del ASIN NO SE SABE: sum() ignora los nulos en
                --   silencio y daria la suma parcial como si fuera el total.
                --   🔴 Y por eso no se usa GREATEST, que tambien ignora los nulos: convierte
                --   un «no lo se» en una afirmacion y no lo caza ninguna guarda.
                CASE
                    WHEN count(*) = count(i.disponible_estimado) THEN sum(i.disponible_estimado)
                    ELSE NULL::bigint
                END AS uds_disponible_estimado,
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
                CASE
                    WHEN sf.asin IS NULL THEN 0::bigint
                    ELSE sf.uds_fc_transfer
                END AS stock_fc_transfer,
            -- ⇐ CAMBIO 2 · el peldaño de en medio entra en `base`. Aqui NO hace falta el
            --   `CASE WHEN sf.asin IS NULL` que lleva el transito: si el ASIN no esta en
            --   FBA no hay estimacion, y NULO es exactamente lo que hay que decir. Ademas
            --   la escalera no llega a este peldaño en ese caso, porque cuando el LEFT
            --   JOIN no casa `stock_fba_eu` vale 0 y no nulo.
            sf.uds_disponible_estimado AS stock_estimado,
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
            -- ⇐ CAMBIO 3 · el peldaño viaja por el CTE `calc`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            b.stock_estimado,
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
            -- ⇐ CAMBIO 4 · el peldaño viaja por el CTE `acc`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            c.stock_estimado,
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
                    -- ⇐ CAMBIO 10 · `no_estas_causa`, el aviso de almacenaje: la CONDICION.
                    --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                    --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                    --   del transito ni puente para estimarlo, y entonces se queda corto.
                    WHEN c.presencia = 'SIN_PAGINA'::text AND (c.stock_moloka > 0::numeric OR COALESCE(c.stock_fba_eu, c.stock_estimado::numeric, c.stock_vendible::numeric) > 0::numeric OR c.vendo_30d > 0) THEN ('tenías ficha y Amazon la retiró: '::text ||
                    CASE
                        -- ⇐ CAMBIO 11 · el mismo aviso, el TEXTO (dos usos en esta linea).
                        --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                        --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                        --   del transito ni puente para estimarlo, y entonces se queda corto.
                        WHEN COALESCE(c.stock_fba_eu, c.stock_estimado::numeric, c.stock_vendible::numeric) > 0::numeric THEN COALESCE(c.stock_fba_eu, c.stock_estimado::numeric, c.stock_vendible::numeric) || ' uds en FBA pagando almacenaje'::text
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
                    -- ⇐ CAMBIO 12 · el veredicto COMPROBAR. 🔴 Aqui es donde mas muerde:
                    --   GREATEST(NULL, 0) devuelve 0 en Postgres, asi que sin escalera un «no
                    --   lo se» sale convertido en «no tiene stock» y la ficha cae a COMPROBAR.
                    --   Con el informe recortado eso seria TODA la pantalla, todo el mes.
                    --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                    --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                    --   del transito ni puente para estimarlo, y entonces se queda corto.
                    WHEN c.bb_precio IS NULL OR c.margen_al_bb IS NULL OR c.mi_precio IS NULL OR GREATEST(COALESCE(c.stock_fba_eu, c.stock_estimado::numeric, c.stock_vendible::numeric), c.stock_moloka) = 0::numeric THEN 'COMPROBAR'::text
                    WHEN c.vendo_30d > 0 AND c.margen_hoy < 0::numeric THEN 'SUBE'::text
                    -- ⇐ CAMBIO 13 · el veredicto LIQUIDA. Decidido por Fernando el 7-sep:
                    --   tambien las dos decisiones que mueven PRECIO bajan la escalera mientras
                    --   dure el transito. El motivo, entero, en la cabecera del fichero.
                    --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                    --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                    --   del transito ni puente para estimarlo, y entonces se queda corto.
                    WHEN c.vendo_30d_global = 0::numeric AND c.mi_precio > c.bb_precio AND COALESCE(c.stock_fba_eu, c.stock_estimado::numeric, c.stock_vendible::numeric) > 0::numeric THEN 'LIQUIDA'::text
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
            -- ⇐ CAMBIO 5 · el peldaño viaja por el CTE `pre`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            a.stock_estimado,
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
            -- ⇐ CAMBIO 6 · el peldaño viaja por el CTE `pre2`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            p.stock_estimado,
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
            -- ⇐ CAMBIO 7 · el peldaño viaja por el CTE `fin`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            q.stock_estimado,
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
            -- ⇐ CAMBIO 8 · el peldaño viaja por el CTE `fila`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            f.stock_estimado,
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
            -- ⇐ CAMBIO 9 · el peldaño viaja por el CTE `fila2`. Sin este arrastre
            --   `stock_estimado` no llega a las seis decisiones.
            g.stock_estimado,
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
                    -- ⇐ CAMBIO 14 · `presencia_detalle` → 'ficha_retirada'.
                    --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                    --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                    --   del transito ni puente para estimarlo, y entonces se queda corto.
                    WHEN h.presencia = 'SIN_PAGINA'::text AND (h.stock_moloka > 0::numeric OR COALESCE(h.stock_fba_eu, h.stock_estimado::numeric, h.stock_vendible::numeric) > 0::numeric OR h.vendo_30d > 0) THEN 'ficha_retirada'::text
                    WHEN h.presencia = 'SIN_PAGINA'::text THEN 'sin_pagina'::text
                    WHEN h.presencia = 'NI_LISTING'::text THEN 'ficha_por_crear'::text
                    WHEN h.presencia = 'SIN_OFERTA'::text THEN 'sin_dato_paneu'::text
                    ELSE 'ofertado'::text
                END AS presencia_detalle,
                CASE
                    WHEN h.accion <> 'NO_ESTAS'::text THEN NULL::text
                    WHEN h.motivo_bloqueo_paneu IS NOT NULL THEN 'asumir solo-España'::text
                    -- ⇐ CAMBIO 15 · `trabajo_pendiente` → 'reclamar la ficha'.
                    --   Escalera de tres peldaños: leido → estimado → vendible. El vendible
                    --   es el ULTIMO peldaño, NO el unico: se pisa cuando no hay ni lectura
                    --   del transito ni puente para estimarlo, y entonces se queda corto.
                    WHEN h.presencia = 'SIN_PAGINA'::text AND (h.stock_moloka > 0::numeric OR COALESCE(h.stock_fba_eu, h.stock_estimado::numeric, h.stock_vendible::numeric) > 0::numeric OR h.vendo_30d > 0) THEN 'reclamar la ficha'::text
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

-- 🔴 IMPRESCINDIBLE: el REPLACE de arriba se ha llevado por delante las opciones
--    de la vista. Sin esta linea, `security_invoker` se pierde y la vista vuelve a
--    leer como su dueño, saltandose la RLS, en silencio.
ALTER VIEW public.v_trackeador_pantalla SET (security_invoker = true);

COMMENT ON COLUMN public.v_trackeador_pantalla.stock_fba_eu IS
  'Vendible + transferencia entre centros. NULO cuando el transito no se sabe, '
  'porque NULL + n es NULL. 🔴 Las decisiones de esta misma vista NO usan este nulo: '
  'bajan la ESCALERA COALESCE(stock_fba_eu, stock_estimado, stock_vendible), o sea '
  'leido → estimado → vendible. El vendible es el ULTIMO peldaño, NO el unico: solo '
  'se pisa cuando no hay ni lectura del transito ni puente con el que estimarlo, y '
  'entonces la cifra se queda corta a sabiendas. Ver los CAMBIO 10..15 de '
  'migraciones/2026-09-07_trackeador_escalera_disponible.sql.';

-- ── EL NUMERO DE CONTROL, DENTRO DE LA TRANSACCION ──────────────────────────
DO $$
DECLARE
  n int; huella text; opciones text; tapones int; suelos int; escaleras int;
  usa_estimado int; movidas int;
BEGIN
  -- 1 · 🔴 LA COMPROBACION QUE HACE SEGURAS 1.309 LINEAS. Hoy el transito se
  --     conoce en todas las fichas, asi que la vista nueva TIENE que producir
  --     exactamente lo mismo que la vieja. Se compara contra la foto del bloque 0,
  --     nunca contra un numero escrito aqui.
  SELECT count(*), md5(string_agg(t::text, chr(10) ORDER BY t.asin, t.dominio))
    INTO n, huella
    FROM public.v_trackeador_pantalla t;
  IF n IS DISTINCT FROM (SELECT filas FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: la vista devuelve % filas y antes devolvia %.',
                    n, (SELECT filas FROM _pantalla_antes);
  END IF;
  IF huella IS DISTINCT FROM (SELECT p.huella FROM _pantalla_antes p) THEN
    RAISE EXCEPTION 'ABORTA: la huella de las % filas ha cambiado. Con el transito '
                    'leido en todas las fichas la escalera no baja de peldaño, asi '
                    'que esta migracion NO puede mover ni un valor: si lo mueve, hay '
                    'un error de transcripcion.', n;
  END IF;

  -- 2 · EL RECUENTO DE ACCIONES POR DOMINIO, que es lo que mira Elena. La huella
  --     ya lo cubre, pero esto dice QUE se ha movido y no solo que algo se movio.
  -- 🔴 Los parentesis NO son adorno: EXCEPT y UNION ALL tienen la MISMA precedencia
  --    y asocian por la izquierda, asi que sin ellos esto seria
  --    ((A EXCEPT B) UNION ALL B) EXCEPT A, que no es la diferencia simetrica y
  --    dejaria pasar cambios sin avisar.
  SELECT count(*) INTO movidas FROM (
    (SELECT dominio, accion, fichas FROM _acciones_antes
     EXCEPT
     SELECT t.dominio, t.accion, count(*) FROM public.v_trackeador_pantalla t GROUP BY 1, 2)
    UNION ALL
    (SELECT t.dominio, t.accion, count(*) FROM public.v_trackeador_pantalla t GROUP BY 1, 2
     EXCEPT
     SELECT dominio, accion, fichas FROM _acciones_antes)) d;
  IF movidas <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % combinaciones (dominio, accion) han cambiado de '
                    'recuento. La escalera no puede mover ninguna decision hoy.', movidas;
  END IF;

  -- 3 · Y LAS FICHAS DE CADA BLOQUE.
  SELECT count(*) INTO movidas FROM (
    (SELECT bloque, fichas FROM _bloques_antes
     EXCEPT
     SELECT t.bloque, count(*) FROM public.v_trackeador_pantalla t GROUP BY 1)
    UNION ALL
    (SELECT t.bloque, count(*) FROM public.v_trackeador_pantalla t GROUP BY 1
     EXCEPT
     SELECT bloque, fichas FROM _bloques_antes)) d;
  IF movidas <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % bloques han cambiado de numero de fichas.', movidas;
  END IF;

  -- 4 · Las cifras sueltas que dicen QUE se habria movido, por si la huella
  --     cambiara por un motivo tonto. Las cuatro de las decisiones que tocamos.
  IF (SELECT sum(t.stock_fba_eu) FROM public.v_trackeador_pantalla t)
     IS DISTINCT FROM (SELECT suma_stock_fba_eu FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: la suma de stock_fba_eu ha cambiado.';
  END IF;
  IF (SELECT sum(t.stock_fc_transfer) FROM public.v_trackeador_pantalla t)
     IS DISTINCT FROM (SELECT suma_fc_transfer FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: la suma de stock_fc_transfer ha cambiado.';
  END IF;
  IF (SELECT count(*) FROM public.v_trackeador_pantalla t WHERE t.accion = 'COMPROBAR')
     IS DISTINCT FROM (SELECT n_comprobar FROM _pantalla_antes)
  OR (SELECT count(*) FROM public.v_trackeador_pantalla t WHERE t.accion = 'LIQUIDA')
     IS DISTINCT FROM (SELECT n_liquida FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: han cambiado COMPROBAR o LIQUIDA, que son las dos '
                    'decisiones de PRECIO. Hoy no pueden moverse.';
  END IF;
  IF (SELECT count(*) FROM public.v_trackeador_pantalla t WHERE t.presencia_detalle = 'ficha_retirada')
     IS DISTINCT FROM (SELECT n_retirada FROM _pantalla_antes)
  OR (SELECT count(*) FROM public.v_trackeador_pantalla t WHERE t.trabajo_pendiente = 'reclamar la ficha')
     IS DISTINCT FROM (SELECT n_reclamar FROM _pantalla_antes) THEN
    RAISE EXCEPTION 'ABORTA: han cambiado las fichas retiradas o las de reclamar.';
  END IF;

  -- 5 · EL TEXTO DE LA VISTA. 🔑 Los datos de hoy NO distinguen la version vieja de
  --     la nueva —por eso la de arriba no basta—: si la escalera no se hubiera
  --     escrito, todas las guardas anteriores pasarian igual.
  SELECT count(*) FILTER (WHERE l LIKE '%COALESCE(sf.uds_fc_transfer%'),
         count(*) FILTER (WHERE l LIKE '%COALESCE(c.stock_fba_eu, c.stock_vendible%'
                             OR  l LIKE '%COALESCE(h.stock_fba_eu, h.stock_vendible%'),
         count(*) FILTER (WHERE l LIKE '%stock_fba_eu, %stock_estimado%stock_vendible%')
    INTO tapones, suelos, escaleras
    FROM unnest(string_to_array(
           pg_get_viewdef('public.v_trackeador_pantalla'::regclass, true), chr(10))) AS l;
  IF tapones <> 0 THEN
    RAISE EXCEPTION 'ABORTA: ha vuelto el COALESCE que tapa el transito (% veces). '
                    'Eso es el 2a/2b deshecho, no esta migracion.', tapones;
  END IF;
  IF suelos <> 0 THEN
    RAISE EXCEPTION 'ABORTA: quedan % suelos de dos peldaños COALESCE(stock_fba_eu, '
                    'stock_vendible). Tenian que pasar los SEIS a la escalera.', suelos;
  END IF;
  IF escaleras <> 6 THEN
    RAISE EXCEPTION 'ABORTA: hay % lineas con la escalera de tres peldaños y tenian '
                    'que ser 6, una por decision.', escaleras;
  END IF;

  -- 6 · 🔑 Y QUE LA VISTA LEE DE VERDAD LA COLUMNA DEL PUENTE, medido POR
  --     ESTRUCTURA (pg_depend) y no por texto: la dependencia solo existe si la
  --     columna esta realmente en la consulta. Antes de esta migracion era 0.
  SELECT count(*) INTO usa_estimado
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
   WHERE r.ev_class = 'public.v_trackeador_pantalla'::regclass
     AND d.refobjid = 'public.inventario_fba'::regclass
     AND d.refobjsubid = (SELECT attnum FROM pg_attribute
                           WHERE attrelid = 'public.inventario_fba'::regclass
                             AND attname = 'disponible_estimado');
  IF usa_estimado = 0 THEN
    RAISE EXCEPTION 'ABORTA: la vista NO depende de inventario_fba.disponible_estimado. '
                    'El peldaño de en medio no ha entrado.';
  END IF;

  -- 7 · La vista conserva `security_invoker`, y el esquema conserva las suyas.
  SELECT array_to_string(reloptions, ',') INTO opciones
    FROM pg_class WHERE oid = 'public.v_trackeador_pantalla'::regclass;
  IF coalesce(opciones, '') NOT LIKE '%security_invoker=true%' THEN
    RAISE EXCEPTION 'ABORTA: v_trackeador_pantalla ha perdido security_invoker '
                    '(reloptions: %).', coalesce(opciones, '(sin opciones)');
  END IF;
  SELECT count(*) FILTER (WHERE c.relkind = 'v'
                            AND array_to_string(c.reloptions, ',') LIKE '%security_invoker=true%')
    INTO n
    FROM pg_class c JOIN pg_namespace n2 ON n2.oid = c.relnamespace
   WHERE n2.nspname = 'public';
  IF n IS DISTINCT FROM (SELECT con_invoker FROM _invoker_antes) THEN
    RAISE EXCEPTION 'ABORTA: las vistas con security_invoker han pasado de % a %.',
                    (SELECT con_invoker FROM _invoker_antes), n;
  END IF;

  -- 8 · 🔴 Y NO SE HA PERDIDO EL SELECT, que es lo que apaga la pantalla de Elena.
  IF NOT has_table_privilege('authenticated', 'public.v_trackeador_pantalla', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` se ha quedado sin SELECT sobre la vista.';
  END IF;
  IF has_table_privilege('authenticated', 'public.v_trackeador_pantalla', 'INSERT')
     OR has_table_privilege('authenticated', 'public.v_trackeador_pantalla', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.v_trackeador_pantalla', 'DELETE') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` tiene escritura sobre la vista. El '
                    '`warmer` es un authenticated.';
  END IF;

  -- 9 · La materializada sigue en pie y LLENA. Esta migracion no la toca, pero una
  --     materializada vacia deja la pantalla en blanco SIN dar error.
  SELECT count(*) INTO n FROM public.mv_trackeador_pantalla;
  IF n = 0 THEN
    RAISE EXCEPTION 'ABORTA: mv_trackeador_pantalla esta VACIA.';
  END IF;

  RAISE NOTICE 'Numero de control OK: las % filas con la huella EXACTA de antes, '
               'las acciones por dominio y los bloques sin mover una ficha, 0 suelos '
               'de dos peldaños y 6 escaleras de tres, la vista dependiendo de '
               'inventario_fba.disponible_estimado, security_invoker y el SELECT en '
               'su sitio, y la materializada con datos.',
               (SELECT filas FROM _pantalla_antes);
END $$;

-- ============================================================================
-- VERIFICACION POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   -- 1) el texto: 0 suelos de dos peldaños, 6 escaleras de tres, 0 tapones:
--   select count(*) filter (where l like '%COALESCE(sf.uds_fc_transfer%')            as tapones,
--          count(*) filter (where l like '%COALESCE(c.stock_fba_eu, c.stock_vendible%'
--                              or l like '%COALESCE(h.stock_fba_eu, h.stock_vendible%') as suelos_viejos,
--          count(*) filter (where l like '%stock_fba_eu, %stock_estimado%stock_vendible%') as escaleras
--     from unnest(string_to_array(
--            pg_get_viewdef('public.v_trackeador_pantalla'::regclass, true), chr(10))) as l;
--   -- → 0 · 0 · 6
--
--   -- 2) y no se ha movido nada (hoy el transito se conoce en todas las fichas).
--   -- En PRODUCCION, medido el 7-sep antes de aplicar:
--   select count(*) as filas, sum(stock_fba_eu) as suma, sum(stock_fc_transfer) as fc,
--          count(*) filter (where accion = 'COMPROBAR') as comprobar,
--          count(*) filter (where accion = 'LIQUIDA')   as liquida,
--          count(*) filter (where presencia_detalle = 'ficha_retirada') as retiradas
--     from public.v_trackeador_pantalla;
--   -- → 1776 · 26768 · 1020 · 204 · 86 · 15
--
--   -- 3) LA SIMULACION DEL PELDAÑO, que es lo unico que demuestra que la escalera
--   --    sirve para algo: se finge el informe recortado poniendo el transito a NULO.
--   with sf as (
--     select i.asin,
--            sum(coalesce(i.available, 0)) as vendible,
--            case when count(*) = count(i.fc_transfer) then sum(i.fc_transfer) end as fc,
--            case when count(*) = count(i.disponible_estimado)
--                 then sum(i.disponible_estimado) end as estimado
--       from public.inventario_fba i
--      where i.fecha_foto = (select max(fecha_foto) from public.inventario_fba)
--        and i.asin is not null
--      group by i.asin)
--   select asin, vendible, fc, estimado,
--          (vendible > 0)                    as con_suelo_tiene_stock,
--          (coalesce(estimado, vendible) > 0) as con_escalera_tiene_stock
--     from sf where (vendible + fc) > 0 and vendible = 0 order by asin;
--   -- → 4 ASIN; el suelo pierde los 4, la escalera recupera 3 (B003UWY00Q,
--   --   B0BCFMZ8WR, B0CDJGVPCL). B09V85CK5Q no, porque sus 6 uds son entrantes.
--
--   -- LO QUE NO SE PUEDE COMPROBAR DESDE AQUI: que Elena vea filas. Se mira
--   -- abriendo el Trackeador. Es la unica prueba que vale.
-- ============================================================================
