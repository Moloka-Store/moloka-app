-- ============================================================================
-- MIGRACION · UNA materializada para las DOS vistas de rentabilidad
-- ----------------------------------------------------------------------------
-- EL PROBLEMA: las dos agregan TODO el historico de `transacciones_movimientos`
-- (16.744 filas) en CADA carga de pantalla, y lo hacen DOS VECES porque cada una
-- lo calcula por su cuenta. Medido con el rol de la app, media REAL por delta de
-- una tanda controlada:
--     v_rentabilidad_transacciones  1.892 ms   <- la consulta mas cara de la carga
--     v_rentabilidad_producto_mes     867 ms x2 (1.314 filas: cruza el techo de
--                                                1.000 y se lee en dos paginas)
--
-- 🔑 SON LA MISMA CUENTA A DOS NIVELES. Comprobado, no supuesto: la de pais/mes es
--    la de pais/mes/sku sumada. Asi que una sola materializada por sku sirve a las
--    dos, y desaparece la agregacion duplicada del historico entero.
--
-- 🔴 EL REPARTO ES POR VOLATILIDAD, NO POR VISTA. Es la misma regla que dejo
--    `dias_desde_ultimo_dato` fuera de `mv_ventas_ventanas`: se materializa lo
--    PESADO Y ESTABLE, y lo LIGERO Y VOLATIL se queda vivo arriba.
--      · a la mv : el agregado de transacciones, CRUDO y por (pais, mes, sku)
--      · en vivo : TODO lo que sale de `productos` -- y eso incluye EL PVD
--
--    🔴 EL PVD ES EL MOTIVO DE TODO ESTE REPARTO. Es el coste, y de el sale el
--       margen. Si `coste_pvd` viviera dentro de la mv, el pvd quedaria CONGELADO
--       hasta el siguiente informe: un coste caducado es una cifra falsa, y con el
--       lo serian `beneficio` y `margen_pct`.
--       ⚠️ Y no bastaba con sacar `productos`: `coste_pvd` LLEVA EL PVD DENTRO
--          (`sum(cantidad * pvd)`). Sale de la mv y se calcula arriba como
--          `unidades x pvd`, que es identico porque `prod` es DISTINCT ON (sku) y
--          por tanto el pvd es constante dentro del grupo.
--          🔬 MEDIDO en produccion: `coste_pvd = unidades x pvd` en 1.314 de 1.314
--             filas, diferencia maxima 0,0000. Y el filtro de `unidades` es el
--             MISMO que el de `coste_pvd`, asi que los 64 grupos con unidades NULL
--             tienen coste NULL tambien.
--       Lo mismo `coste_almacen`, que lleva `producto_id`:
--          `coste_almacen = unidades x coste_almacen_ud(producto_id, mes)`.
--          🔬 MEDIDO: 1.314 de 1.314, diferencia maxima 0,00.
--
--    🔴 Y `con_ficha` TAMBIEN SALE, que es lo que casi se me pasa. Es
--       `p.sku IS NOT NULL`, o sea que depende de `productos`, y es el FILTRO de
--       nueve de las diez medidas. Como es constante dentro del grupo --un sku o
--       tiene ficha o no la tiene--, aplicarlo ARRIBA es identico a aplicarlo fila
--       a fila. Si se hubiera quedado dentro, crear una ficha nueva no se
--       reflejaria hasta el siguiente refresco.
--
-- 🔒 LA CLAVE BAJA A TRES COLUMNAS, y es una consecuencia directa de sacar
--    `productos`. La vista de hoy agrupa por NUEVE (pais, mes, sku, con_ficha,
--    producto_id, asin, nombre, ean, es_chase) --seis de ellas de `productos`, y
--    una, `producto_id`, ni siquiera se proyecta--. Sin ellas, el GROUP BY es
--    (pais, mes, sku) y la clave es unica POR EL PROPIO GROUP BY, no por el dato
--    de hoy.
--    ⚠️ `sku` admite NULL (1.007 transacciones, 21 grupos), y un indice unico NO
--       enforcea sobre NULL --cada NULL es distinto de los demas-- y
--       `REFRESH ... sin bloquear` usa ese indice para casar filas. Por eso se
--       materializa `sku_k` como COLUMNA REAL: el indice va sobre columnas, no
--       sobre expresiones, asi que el COALESCE no puede vivir dentro del indice.
--    🔒 Y EL CENTINELA ES LA CADENA VACIA, EN ASCII PURO, A PROPOSITO. Aqui hubo
--       un `'∅'` y se quito antes de aplicar nada: es un DATO que tiene que
--       casar entre la mv y la guarda, y en esta casa el encoding ya ha mordido
--       mas de una vez. Un centinela que se transcodifique a medias no da error:
--       da una clave que no casa.
--       🔬 Y no puede chocar con un SKU real, medido en produccion: 0 SKU vacios,
--          0 SKU con un solo caracter no-ASCII, y el mas corto tiene 12 caracteres.
--          Aun asi lleva guarda abajo -- "0 hoy" no es "0 manana", y si un dia
--          apareciera un SKU vacio la clave dejaria de ser unica.
--
-- 🔒 LAS DOS VISTAS CONSERVAN SU CONTRATO EXACTO: 21 columnas
--    `v_rentabilidad_producto_mes` y 14 `v_rentabilidad_transacciones`, con los
--    mismos nombres, tipos y ORDEN. `CREATE OR REPLACE VIEW` conserva el OID, asi
--    que nada de lo que cuelga se entera y los ACL se mantienen.
--
-- 🔬 VERIFICADO ANTES DE ESCRIBIR ESTO, corriendo la reconstruccion contra
--    produccion y comparando huellas md5 columna a columna:
--      v_rentabilidad_producto_mes   1.314 filas  e106bc95001130eadc105490642250bc
--      v_rentabilidad_transacciones     22 filas  a22690ab9386ec7eed54c75c4e8f46cd
--    Las dos identicas a lo que devuelven hoy. **No se mueve un centimo.**
--
-- ⚠️ EL DETALLE QUE COSTO ENCONTRAR, y sin el la de pais/mes fallaba en 9 de 22:
--    `beneficio` y `margen_pct` NO se pueden sumar ni recalcular desde lo crudo.
--    `v_rentabilidad_transacciones` los calcula desde las componentes YA
--    REDONDEADAS, y `v_rentabilidad_producto_mes` desde las crudas. Cada una se
--    reproduce como la hace hoy.
--    🔒 Que el total por pais/mes no sea la suma exacta del detalle por 1-2
--       centimos es un criterio contable PREEXISTENTE, no un efecto de esta
--       migracion, y NO SE TOCA aqui: esto es una optimizacion de velocidad.
--
-- 🔒 EL REFRESCO no vive aqui: va en `procesador_transacciones.py`, atado al
--    evento que cambia el dato. Refrescar sin bloquear lectores no puede correr
--    dentro de una transaccion, y este fichero corre entero dentro de una.
--    🔑 UNA SOLA FUENTE: `transacciones_movimientos`. `productos` NO es fuente de
--       la mv --se cruza en vivo--, asi que no necesita gancho ni ancla. Eso es
--       justo lo que se gana con el reparto por volatilidad.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k1 char; k2 char;
    n_pm bigint; n_tx bigint; n_grupos bigint;
    n_cols_pm int; n_cols_tx int;
BEGIN
    SELECT relkind INTO k1 FROM pg_class WHERE oid = 'public.v_rentabilidad_producto_mes'::regclass;
    SELECT relkind INTO k2 FROM pg_class WHERE oid = 'public.v_rentabilidad_transacciones'::regclass;
    IF k1 <> 'v' OR k2 <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: se esperaban dos VISTAS y hay relkind=% y %. Si ya son materializadas, esta migracion ya corrio y el ensayo no probaria nada.', k1, k2;
    END IF;
    IF to_regclass('public.mv_rentabilidad_sku') IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: mv_rentabilidad_sku YA existe. Un ensayo sobre el estado de destino sale verde sin demostrar nada.';
    END IF;

    -- Anti-cero: sin filas, todo lo de abajo saldria "bien" sin medir nada.
    SELECT count(*) INTO n_pm FROM v_rentabilidad_producto_mes;
    SELECT count(*) INTO n_tx FROM v_rentabilidad_transacciones;
    IF n_pm = 0 OR n_tx = 0 THEN
        RAISE EXCEPTION 'ABORTA: producto_mes=% filas, transacciones=% filas. No hay nada que materializar.', n_pm, n_tx;
    END IF;

    -- 🔴 LA UNICIDAD DE LA CLAVE NUEVA, MEDIDA. Es lo que permite refrescar sin
    --    bloquear lectores; si dejara de ser cierta, el refresco FALLA y la
    --    pantalla se queda con el dato viejo sin decir nada.
    SELECT count(*) INTO n_grupos FROM (
        SELECT t.pais, date_trunc('month', t.fecha::timestamp with time zone)::date AS mes,
               COALESCE(t.sku, '') AS sku_k
          FROM transacciones_movimientos t
         GROUP BY 1, 2, 3) g;
    IF n_grupos <> n_pm THEN
        RAISE EXCEPTION 'ABORTA: (pais, mes, sku_k) da % grupos y la vista tiene % filas. La clave del indice unico no reproduce el grano de la vista.', n_grupos, n_pm;
    END IF;

    -- 🔒 EL CENTINELA DE LOS SKU NULOS NO PUEDE CHOCAR CON UN SKU DE VERDAD.
    --    Si chocara, dos grupos distintos compartirian clave, el indice unico no se
    --    podria crear y esta migracion abortaria -- pero abortaria con un
    --    "duplicate key" que no dice de que va. Mejor decirlo aqui.
    IF EXISTS (SELECT 1 FROM transacciones_movimientos WHERE sku = '') THEN
        RAISE EXCEPTION 'ABORTA: hay transacciones con el SKU en cadena vacia, y la cadena vacia es el centinela que representa "sin SKU". Chocarian dos grupos distintos. Cambia el centinela por algo que no exista.';
    END IF;

    -- El contrato que hay que reproducir, columna a columna.
    SELECT count(*) INTO n_cols_pm FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_rentabilidad_producto_mes';
    SELECT count(*) INTO n_cols_tx FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_rentabilidad_transacciones';
    IF n_cols_pm <> 21 OR n_cols_tx <> 14 THEN
        RAISE EXCEPTION 'ABORTA: producto_mes tiene % columnas (se esperaban 21) y transacciones % (se esperaban 14). Alguna vista ha cambiado: revisa los CREATE OR REPLACE de abajo antes de seguir.', n_cols_pm, n_cols_tx;
    END IF;

    RAISE NOTICE 'Guardas OK. producto_mes=% filas / % columnas, transacciones=% filas / % columnas, clave (pais,mes,sku_k)=% grupos.', n_pm, n_cols_pm, n_tx, n_cols_tx, n_grupos;
END
$guardas$;

-- -- 1) LA MATERIALIZADA · agregado CRUDO por (pais, mes, sku), sin productos --
CREATE MATERIALIZED VIEW public.mv_rentabilidad_sku AS
SELECT t.pais,
       date_trunc('month'::text, t.fecha::timestamp with time zone)::date AS mes,
       t.sku,
       -- 🔒 La clave del indice unico, como COLUMNA REAL: el indice del refresco
       --    tiene que ser sobre columnas, no sobre expresiones, y `sku` admite NULL.
       COALESCE(t.sku, ''::text) AS sku_k,
       max(t.fecha) AS fecha_hasta,
       -- 🔴 SIN el filtro `con_ficha`: depende de `productos` y se aplica arriba.
       --    Es constante dentro del grupo, asi que filtrar por grupo es identico a
       --    filtrar fila a fila.
       sum(t.ventas_producto + t.impuesto_producto)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS facturacion_iva,
       sum(t.ventas_producto)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS facturacion_sin_iva,
       sum(t.cantidad)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS unidades,
       sum((- t.tarifa_venta) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS comision_amazon,
       sum((- t.tarifa_fba) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS logistica_fba,
       sum((- t.tarifa_otras) / 1.21)
           FILTER (WHERE t.cantidad > 0 AND t.ventas_producto > 0::numeric) AS otras_tarifas,
       -- Los reembolsos NO llevan `con_ficha` hoy tampoco: se copian tal cual.
       COALESCE(sum(t.ventas_producto) FILTER (WHERE t.tipo_norm = 'reembolso'::text), 0::numeric)
       + COALESCE(sum((t.tarifa_venta + t.tarifa_fba + t.tarifa_otras) / 1.21)
                  FILTER (WHERE t.tipo_norm = 'reembolso'::text), 0::numeric) AS reembolsos_netos
  FROM transacciones_movimientos t
 GROUP BY t.pais, date_trunc('month'::text, t.fecha::timestamp with time zone)::date, t.sku
WITH DATA;

-- -- 2) EL INDICE UNICO ------------------------------------------------------
CREATE UNIQUE INDEX mv_rentabilidad_sku_uk
    ON public.mv_rentabilidad_sku (pais, mes, sku_k);

COMMENT ON MATERIALIZED VIEW public.mv_rentabilidad_sku IS
    'Agregado CRUDO de transacciones_movimientos por (pais, mes, sku), materializado el 25-ago-2026. Sirve a v_rentabilidad_producto_mes y a v_rentabilidad_transacciones, que son la misma cuenta a dos niveles. NO lleva NADA de productos --ni el pvd, ni producto_id, ni con_ficha-- a proposito: eso cambia mientras Elena trabaja y se cruza en vivo en las vistas de encima. Un coste congelado es una cifra falsa. Se refresca desde procesador_transacciones.py.';

-- -- 3) LA PUERTA · una mv no aplica RLS, asi que el GRANT es todo -----------
-- Se revoca antes de conceder. `transacciones_movimientos` tiene el GRANT heredado
-- de la v1 pero su RLS no tiene ninguna politica que alcance a `anon`, asi que hoy
-- devuelve CERO filas para el rol anonimo. Una materializada no tiene RLS detras:
-- si esta naciera abierta, los EUROS del negocio serian legibles anonimamente POR
-- PRIMERA VEZ. Agujero nuevo, no heredado.
REVOKE ALL ON public.mv_rentabilidad_sku FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.mv_rentabilidad_sku TO authenticated;

-- -- 4) LAS DOS VISTAS · mismo nombre, mismo OID, mismo contrato -------------
-- 🔴 `productos` se cruza AQUI, en vivo. Las 368 filas del DISTINCT ON cuestan
--    0,95 ms medidos: el 0,1 % de lo que costaba la vista entera.
CREATE OR REPLACE VIEW public.v_rentabilidad_producto_mes AS
WITH prod AS (
    SELECT DISTINCT ON (p.sku) p.sku, p.id, p.pvd, p.asin, p.nombre, p.ean, p.es_chase
      FROM productos p
     WHERE p.sku IS NOT NULL
     ORDER BY p.sku, (p.activo IS TRUE) DESC, p.id DESC
)
SELECT m.pais,
       m.mes,
       m.sku,
       (p.sku IS NOT NULL) AS con_ficha,
       CASE WHEN p.es_chase IS TRUE THEN NULL::text ELSE p.asin END AS asin,
       p.nombre,
       p.ean,
       COALESCE(p.es_chase, false) AS es_chase,
       p.nombre ~* '\mpack'::text AS es_pack,
       NULLIF(COALESCE((regexp_match(p.nombre, 'pack\s*de\s*(\d+)'::text, 'i'::text))[1],
                       (regexp_match(p.nombre, 'pack\s*(\d+)'::text, 'i'::text))[1],
                       (regexp_match(p.nombre, '(\d+)\s*-?\s*pack'::text, 'i'::text))[1]),
              ''::text)::integer AS factor_pack,
       m.fecha_hasta,
       -- 🔴 `con_ficha` como filtro, aplicado por grupo. Identico a filtrar fila a
       --    fila porque es constante dentro del grupo.
       CASE WHEN p.sku IS NOT NULL THEN m.unidades END AS unidades,
       CASE WHEN p.sku IS NOT NULL THEN m.facturacion_iva END AS facturacion_iva,
       CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END AS facturacion_sin_iva,
       -- 🔴 EL PVD, EN VIVO. `coste_pvd = unidades x pvd`: medido identico en las
       --    1.314 filas, diferencia maxima 0,0000.
       CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END AS coste_pvd,
       CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END AS comision_amazon,
       CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END AS logistica_fba,
       CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END AS otras_tarifas,
       -- Igual con el almacen, que lleva `producto_id` dentro.
       COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
           * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric) AS coste_almacen,
       m.reembolsos_netos,
       -- 🔒 `beneficio` desde las componentes CRUDAS, como lo hace hoy esta vista.
       COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END, 0::numeric)
       - (COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END, 0::numeric)
          + COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
            * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric))
       + COALESCE(m.reembolsos_netos, 0::numeric) AS beneficio
  FROM public.mv_rentabilidad_sku m
  LEFT JOIN prod p ON p.sku = m.sku;

-- 🔴 Y LA DE PAIS/MES SE CONSTRUYE SOBRE LA MISMA mv, no desde cero. Ahi estaba la
--    agregacion duplicada del historico entero: 1.892 ms, la consulta mas cara de
--    la carga, calculando lo que ya calculaba la otra.
CREATE OR REPLACE VIEW public.v_rentabilidad_transacciones AS
WITH prod AS (
    SELECT DISTINCT ON (p.sku) p.sku, p.id, p.pvd
      FROM productos p
     WHERE p.sku IS NOT NULL
     ORDER BY p.sku, (p.activo IS TRUE) DESC, p.id DESC
), por_sku AS (
    SELECT m.pais, m.mes, m.fecha_hasta,
           CASE WHEN p.sku IS NOT NULL THEN m.facturacion_iva END AS f_iva,
           CASE WHEN p.sku IS NOT NULL THEN m.facturacion_sin_iva END AS f_sin,
           CASE WHEN p.sku IS NOT NULL THEN m.unidades END AS uds,
           CASE WHEN p.sku IS NOT NULL THEN m.unidades::numeric * p.pvd END AS pvd,
           CASE WHEN p.sku IS NOT NULL THEN m.comision_amazon END AS com,
           CASE WHEN p.sku IS NOT NULL THEN m.logistica_fba END AS fba,
           CASE WHEN p.sku IS NOT NULL THEN m.otras_tarifas END AS otras,
           COALESCE(CASE WHEN p.sku IS NOT NULL THEN m.unidades END, 0::bigint)::numeric
               * COALESCE(coste_almacen_ud(p.id, m.mes), 0::numeric) AS alm,
           m.reembolsos_netos AS reem
      FROM public.mv_rentabilidad_sku m
      LEFT JOIN prod p ON p.sku = m.sku
), agr AS (
    -- 🔒 SE REDONDEA UNA SOLA VEZ, AQUI. Sumar lo crudo y redondear al final es
    --    identico a agregar directo desde las transacciones, porque cada
    --    transaccion cae en exactamente un sku (las que no tienen SKU forman su
    --    propio grupo): la particion es completa.
    SELECT pais, mes, max(fecha_hasta) AS fecha_hasta,
           round(sum(f_iva), 2) AS facturacion_iva,
           round(sum(f_sin), 2) AS facturacion_sin_iva,
           -- 🔴 EL CAST NO ES ADORNO: `sum(bigint)` devuelve NUMERIC, y esta columna
           --    es BIGINT en el contrato (el original suma `cantidad`, que es integer,
           --    y `sum(integer)` si da bigint). Sin el, `CREATE OR REPLACE VIEW`
           --    rechaza la vista entera. Es exacto porque son unidades enteras.
           sum(uds)::bigint AS unidades,
           round(sum(pvd), 2) AS coste_pvd,
           round(sum(com), 2) AS comision_amazon,
           round(sum(fba), 2) AS logistica_fba,
           round(sum(otras), 2) AS otras_tarifas,
           round(sum(alm), 2) AS coste_almacen,
           round(sum(reem), 2) AS reembolsos_netos
      FROM por_sku
     GROUP BY pais, mes
)
SELECT pais,
       mes,
       facturacion_iva,
       facturacion_sin_iva,
       unidades,
       coste_pvd,
       comision_amazon,
       logistica_fba,
       otras_tarifas,
       coste_almacen,
       reembolsos_netos,
       -- 🔴 `beneficio` y `margen_pct` DESDE LAS COMPONENTES YA REDONDEADAS, que es
       --    como lo hace hoy esta vista. Calcularlos desde lo crudo daba 9 de 22
       --    filas distintas por 1-2 centimos.
       round(COALESCE(facturacion_sin_iva, 0::numeric)
             - (COALESCE(coste_pvd, 0::numeric) + COALESCE(comision_amazon, 0::numeric)
                + COALESCE(logistica_fba, 0::numeric) + COALESCE(otras_tarifas, 0::numeric)
                + COALESCE(coste_almacen, 0::numeric))
             + COALESCE(reembolsos_netos, 0::numeric), 2) AS beneficio,
       CASE WHEN COALESCE(facturacion_iva, 0::numeric) <> 0::numeric
            THEN round((COALESCE(facturacion_sin_iva, 0::numeric)
                        - (COALESCE(coste_pvd, 0::numeric) + COALESCE(comision_amazon, 0::numeric)
                           + COALESCE(logistica_fba, 0::numeric) + COALESCE(otras_tarifas, 0::numeric)
                           + COALESCE(coste_almacen, 0::numeric))
                        + COALESCE(reembolsos_netos, 0::numeric)) / facturacion_iva * 100::numeric, 2)
       END AS margen_pct,
       fecha_hasta
  FROM agr;

-- -- TESTIGO DEL CONTRATO · las dos huellas, sobre las mismas columnas -------
DO $testigo$
DECLARE
    -- 🔬 Medidas contra PRODUCCION antes de escribir esta migracion, corriendo la
    --    reconstruccion y la vista original lado a lado. Valores PERECEDEROS:
    --    despues de aplicar ya no se pueden recalcular contra el original.
    HUELLA_PM constant text := 'e106bc95001130eadc105490642250bc';
    HUELLA_TX constant text := 'a22690ab9386ec7eed54c75c4e8f46cd';
    FILAS_PM  constant bigint := 1314;
    FILAS_TX  constant bigint := 22;
    n_pm bigint; n_tx bigint; n_cols_pm int; n_cols_tx int;
    h_pm text; h_tx text;
    cols_pm text; cols_tx text;
BEGIN
    SELECT count(*) INTO n_pm FROM v_rentabilidad_producto_mes;
    SELECT count(*) INTO n_tx FROM v_rentabilidad_transacciones;
    IF n_pm = 0 OR n_tx = 0 THEN
        RAISE EXCEPTION 'ABORTA: producto_mes=% filas y transacciones=% filas. Algo se ha quedado vacio.', n_pm, n_tx;
    END IF;

    -- El contrato: mismas columnas, mismos TIPOS, en el mismo orden.
    -- 🔴 LOS TIPOS VAN AQUI PORQUE LA HUELLA md5 ES CIEGA A ELLOS. `t::text` imprime
    --    `1234::numeric` y `1234::bigint` exactamente igual, asi que las dos huellas
    --    casaban con `unidades` cambiada de bigint a numeric. Quien lo cazo fue
    --    `CREATE OR REPLACE VIEW`, que se niega a cambiar el tipo de una columna --no
    --    este testigo--. Medido el 25-ago-2026 en el ensayo de staging.
    -- 🔑 La regla: una huella sobre el TEXTO de las filas prueba los VALORES, no la
    --    forma. Si el contrato incluye tipos, el testigo tiene que mirarlos aparte.
    SELECT count(*), string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO n_cols_pm, cols_pm FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_rentabilidad_producto_mes';
    IF cols_pm <> 'pais:text,mes:date,sku:text,con_ficha:boolean,asin:text,nombre:text,ean:text,es_chase:boolean,es_pack:boolean,factor_pack:integer,fecha_hasta:date,unidades:bigint,facturacion_iva:numeric,facturacion_sin_iva:numeric,coste_pvd:numeric,comision_amazon:numeric,logistica_fba:numeric,otras_tarifas:numeric,coste_almacen:numeric,reembolsos_netos:numeric,beneficio:numeric' THEN
        RAISE EXCEPTION 'ABORTA: v_rentabilidad_producto_mes cambio de columnas o de orden. Ahora: %', cols_pm;
    END IF;
    SELECT count(*), string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO n_cols_tx, cols_tx FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_rentabilidad_transacciones';
    IF cols_tx <> 'pais:text,mes:date,facturacion_iva:numeric,facturacion_sin_iva:numeric,unidades:bigint,coste_pvd:numeric,comision_amazon:numeric,logistica_fba:numeric,otras_tarifas:numeric,coste_almacen:numeric,reembolsos_netos:numeric,beneficio:numeric,margen_pct:numeric,fecha_hasta:date' THEN
        RAISE EXCEPTION 'ABORTA: v_rentabilidad_transacciones cambio de columnas o de orden. Ahora: %', cols_tx;
    END IF;

    -- 🔴 LAS HUELLAS. Es el testigo que de verdad dice si se ha movido un numero.
    -- ⚠️ Solo valen sobre la base en la que se midieron (PRODUCCION). En staging hay
    --    otros datos: alli se GRITA que no se ha comprobado, no se aborta por el dato.
    SELECT md5(string_agg(t::text, '|' ORDER BY t.pais, t.mes, COALESCE(t.sku, '~')))
      INTO h_pm
      FROM (SELECT pais, mes, sku, con_ficha, fecha_hasta, unidades, facturacion_iva,
                   facturacion_sin_iva, coste_pvd, comision_amazon, logistica_fba,
                   otras_tarifas, coste_almacen, reembolsos_netos
              FROM v_rentabilidad_producto_mes) t;
    SELECT md5(string_agg(t::text, '|' ORDER BY t.pais, t.mes))
      INTO h_tx
      FROM (SELECT pais, mes, facturacion_iva, facturacion_sin_iva, unidades, coste_pvd,
                   comision_amazon, logistica_fba, otras_tarifas, coste_almacen,
                   reembolsos_netos, beneficio, margen_pct, fecha_hasta
              FROM v_rentabilidad_transacciones) t;

    IF n_pm <> FILAS_PM OR n_tx <> FILAS_TX THEN
        RAISE WARNING 'HUELLAS NO COMPROBADAS EN ESTE ENTORNO: se midieron sobre PRODUCCION con % y % filas, y aqui hay % y %. No es un fallo: son bases con datos distintos. Lo que este ensayo NO ha comprobado es que las dos vistas devuelvan lo mismo que antes; ESO SE VERIFICA EN PRODUCCION, al aplicar.', FILAS_PM, FILAS_TX, n_pm, n_tx;
    ELSE
        IF h_pm <> HUELLA_PM THEN
            RAISE EXCEPTION 'ABORTA: la huella de v_rentabilidad_producto_mes es % y antes era %. Se ha movido un numero.', h_pm, HUELLA_PM;
        END IF;
        IF h_tx <> HUELLA_TX THEN
            RAISE EXCEPTION 'ABORTA: la huella de v_rentabilidad_transacciones es % y antes era %. Se ha movido un numero.', h_tx, HUELLA_TX;
        END IF;
    END IF;

    -- 🔒 Y el indice unico, que es lo que permite refrescar sin bloquear lectores.
    IF NOT EXISTS (SELECT 1 FROM pg_index i
                    WHERE i.indrelid = 'public.mv_rentabilidad_sku'::regclass AND i.indisunique) THEN
        RAISE EXCEPTION 'ABORTA: mv_rentabilidad_sku no tiene indice UNICO. Sin el, el refresco bloquea a quien este leyendo.';
    END IF;

    RAISE NOTICE 'Testigo OK (contrato). producto_mes=% filas (huella %), transacciones=% filas (huella %), columnas y orden intactos, indice unico puesto.', n_pm, h_pm, n_tx, h_tx;
END
$testigo$;

-- -- TESTIGO DE LA PUERTA · en bloques propios (un `END;` suelto lo rechaza el cerrojo)
DO $puerta_anon$
DECLARE
    n_anon bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM public.mv_rentabilidad_sku' INTO n_anon;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha LEIDO mv_rentabilidad_sku y ha contado % filas. Ahi estan los EUROS del negocio, y hoy anon no puede llegar a ellos por ningun camino. Una materializada no tiene RLS detras: el GRANT es la unica puerta.', n_anon;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA al leer mv_rentabilidad_sku.';
END
$puerta_anon$;

DO $puerta_auth$
DECLARE
    n_auth bigint; n_mv bigint;
BEGIN
    SELECT count(*) INTO n_mv FROM mv_rentabilidad_sku;
    SET LOCAL ROLE authenticated;
    EXECUTE 'SELECT count(*) FROM public.mv_rentabilidad_sku' INTO n_auth;
    RESET ROLE;
    IF n_auth <> n_mv THEN
        RAISE EXCEPTION 'ABORTA: authenticated ve % filas y la mv tiene %.', n_auth, n_mv;
    END IF;
    RAISE NOTICE 'Testigo OK (puerta). authenticated ve las % filas.', n_auth;
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer mv_rentabilidad_sku. La pantalla de rentabilidad se quedaria vacia.';
END
$puerta_auth$;
