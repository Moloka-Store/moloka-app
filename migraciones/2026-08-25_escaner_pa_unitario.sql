-- ============================================================================
-- MIGRACION · `v_escaner_ultimo` publica el precio UNITARIO
-- ----------------------------------------------------------------------------
-- 🔴 QUE PROBLEMA RESUELVE. `escaner_memoria.pa` NO significa lo mismo en todas las
--    filas: en las de CAJA de TCG y HEO es el precio de la CAJA ENTERA. Comparar
--    ese numero con el precio de una unidad de otro proveedor no da un margen malo:
--    compara dos cosas distintas.
--
-- 🔑 LA REGLA NO ES NUEVA Y NO SE REINVENTA AQUI. Vive medida y documentada en
--    `lib/inventory/build.ts` de la v2 (`PRECIO_CAJA_ES_BRUTO` y `UNIDADES_CASE`), y
--    el divisor 6 lo confirman LAS FACTURAS DE COMPRA, que es la mejor prueba que
--    hay porque no depende de ningun razonamiento sobre el feed:
--      B0F44BYT7C  pa/6 = 5,88 EUR  ·  factura 17-jun  5,8417 EUR
--      B0797M3JHM  pa/6 = 8,40 EUR  ·  factura 28-jul  5,7625 EUR
--    Sin dividir, esos productos "costarian" de 35 a 60 EUR.
--
-- 🔴 POR QUE BAJA A SQL AHORA, Y NO DESPUES. Dos motivos, y el segundo es el que
--    manda:
--      1. Hoy la regla esta escrita SOLO en el navegador. Cualquier otra cosa que
--         mire `v_escaner_ultimo` --una consulta a mano, un informe, la v1-- ve el
--         `pa` crudo y saca una conclusion falsa sin enterarse.
--      2. Esta vista va a MATERIALIZARSE. Una vez materializada, anadirle una
--         columna obliga al baile de renombrar-crear-reapuntar-borrar. Se le da su
--         forma definitiva ANTES.
--
-- 🔒 NO SE MUEVE NINGUN NUMERO. `pa` se queda tal cual --es el dato crudo del feed y
--    es lo que se pago-- y `pa_unitario` se ANADE al final. `CREATE OR REPLACE VIEW`
--    solo deja anadir columnas al final, que es justo lo que se hace: las 7 de hoy
--    intactas, en su orden, con sus tipos.
--
-- 🔬 MEDIDO EN PRODUCCION antes de escribir esto, sobre las 1.027 filas de la vista:
--      TCG        193 filas ·  15 de caja · 35,28-60,36 EUR  -> se dividen
--      HEO         99 filas ·   0 de caja                    -> regla INERTE hoy
--      MOLOKA     327 filas ·  15 de caja ·  5,04- 8,90 EUR  -> NO se dividen
--      OCIOSTOCK  254 filas ·  14 de caja ·  8,50-14,99 EUR  -> NO se dividen
--    O sea: 44 filas de caja en total y solo 15 afectadas. Y el contraste que hace
--    creible el reparto: las cajas de TCG estan en otro orden de magnitud que sus
--    propios sueltos (2,68-22,63), y las de MOLOKA y OCIOSTOCK no -- las suyas ya
--    vienen por unidad.
--
-- ⚠️ QUE HEO NO TENGA CAJAS HOY NO ES MOTIVO PARA QUITARLO DE LA LISTA. La regla
--    describe como publica cada proveedor, no lo que hay en el fichero de esta
--    semana. Quitarlo seria dejar la trampa armada para el dia que vuelva a haber
--    una.
--
-- ⚠️ ANOTADO, NO ARREGLADO AQUI: el 6 sigue viviendo TAMBIEN en la v2, porque alli
--    se usa ademas para decir cuantas unidades obliga a comprar una caja
--    (`udsPorCaja`), que es otra pregunta. Son el mismo hecho escrito dos veces y
--    conviene unificarlo; no entra en este PR porque exportar `uds_por_caja` desde
--    aqui meteria en la base un supuesto que HOY solo esta medido para TCG.
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    k char; n bigint; cols text; n_caja bigint; n_div bigint;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid = 'public.v_escaner_ultimo'::regclass;
    IF k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: v_escaner_ultimo tiene relkind=%. Si ya es materializada, esta migracion llega TARDE: anadir una columna ya no es un CREATE OR REPLACE.', k;
    END IF;

    SELECT count(*) INTO n FROM v_escaner_ultimo;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista esta vacia. Sobre cero filas cualquier comprobacion de abajo sale bien sin medir nada.';
    END IF;

    -- El contrato de hoy, con TIPOS: la columna nueva va DETRAS de estas siete.
    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_escaner_ultimo';
    IF cols <> 'ean:text,proveedor:text,pa:numeric,presente:boolean,fecha:timestamp with time zone,es_case:boolean,marca:text' THEN
        RAISE EXCEPTION 'ABORTA: v_escaner_ultimo no tiene el contrato esperado. Ahora: %', cols;
    END IF;

    SELECT count(*) FILTER (WHERE es_case),
           count(*) FILTER (WHERE es_case AND upper(proveedor) IN ('TCG','HEO'))
      INTO n_caja, n_div FROM v_escaner_ultimo;
    RAISE NOTICE 'Guardas OK. % filas, % de caja, % de ellas con precio de caja BRUTO (se dividiran).', n, n_caja, n_div;
END
$guardas$;

-- -- LA VISTA · las 7 de hoy intactas + `pa_unitario` al final ----------------
CREATE OR REPLACE VIEW public.v_escaner_ultimo AS
 SELECT DISTINCT ON (ean, proveedor, es_case) ean,
    proveedor,
    -- 🔒 `pa` SE QUEDA CRUDO. Es lo que dice el feed y lo que se paga por la caja:
    --    borrarlo o pisarlo perderia el dato de compra. La lectura se anade al lado.
    pa,
    presente,
    fecha,
    es_case,
    marca,
    -- 🔴 EL PRECIO DE UNA UNIDAD, que es lo unico comparable entre proveedores.
    --    `upper()` porque el escaner escribe el proveedor sin normalizar y la regla
    --    es sobre QUIEN publica, no sobre como se escribio ese dia.
    --    El divisor es 6 y lo confirman las facturas (ver la cabecera).
    CASE WHEN es_case AND upper(proveedor) IN ('TCG', 'HEO') THEN pa / 6
         ELSE pa
    END AS pa_unitario
   FROM escaner_memoria m
  WHERE ean IS NOT NULL AND proveedor IS NOT NULL AND (EXISTS ( SELECT 1
           FROM productos p
          WHERE p.ean = m.ean AND p.asin IS NOT NULL AND p.es_chase = false))
  ORDER BY ean, proveedor, es_case, fecha DESC, id DESC;

COMMENT ON COLUMN public.v_escaner_ultimo.pa IS
    'Precio tal cual lo publica el proveedor. OJO: en las filas de CAJA de TCG y HEO es el precio de la CAJA ENTERA, no de una unidad. Para comparar entre proveedores usa pa_unitario.';
COMMENT ON COLUMN public.v_escaner_ultimo.pa_unitario IS
    'Precio por UNIDAD. Igual a pa salvo en las filas de caja de TCG y HEO, donde es pa/6. El divisor lo confirman las facturas de compra (ver la migracion 2026-08-25_escaner_pa_unitario.sql). Es la unica columna comparable entre proveedores.';

-- -- TESTIGO ------------------------------------------------------------------
DO $testigo$
DECLARE
    cols text;
    n bigint; n_igual bigint; n_div bigint; n_mal bigint; n_nulos bigint;
    max_desvio numeric;
BEGIN
    SELECT count(*) INTO n FROM v_escaner_ultimo;
    IF n = 0 THEN
        RAISE EXCEPTION 'ABORTA: la vista se ha quedado vacia.';
    END IF;

    -- El contrato: las 7 de antes, en su orden y con sus tipos, mas la nueva DETRAS.
    SELECT string_agg(column_name || ':' || data_type, ',' ORDER BY ordinal_position)
      INTO cols FROM information_schema.columns
     WHERE table_schema='public' AND table_name='v_escaner_ultimo';
    IF cols <> 'ean:text,proveedor:text,pa:numeric,presente:boolean,fecha:timestamp with time zone,es_case:boolean,marca:text,pa_unitario:numeric' THEN
        RAISE EXCEPTION 'ABORTA: el contrato no es el esperado. Ahora: %', cols;
    END IF;

    -- 🔴 LAS DOS DIRECCIONES, Y LA SEGUNDA ES LA QUE PRUEBA ALGO.
    --    (a) que la columna DIVIDA donde tiene que dividir
    SELECT count(*) FILTER (WHERE es_case AND upper(proveedor) IN ('TCG','HEO')),
           count(*) FILTER (WHERE es_case AND upper(proveedor) IN ('TCG','HEO')
                              AND pa_unitario IS DISTINCT FROM pa / 6)
      INTO n_div, n_mal FROM v_escaner_ultimo;
    IF n_mal > 0 THEN
        RAISE EXCEPTION 'ABORTA: % fila(s) de caja de TCG/HEO NO llevan pa/6.', n_mal;
    END IF;
    -- 🔴 …y (b) que NO toque NINGUNA otra. Sin esto, un `pa/6` a todo saldria verde en (a).
    SELECT count(*) FILTER (WHERE NOT (es_case AND upper(proveedor) IN ('TCG','HEO'))
                              AND pa_unitario IS DISTINCT FROM pa)
      INTO n_igual FROM v_escaner_ultimo;
    IF n_igual > 0 THEN
        RAISE EXCEPTION 'ABORTA: % fila(s) que NO son caja de TCG/HEO tienen pa_unitario distinto de pa. La regla se ha ido de madre.', n_igual;
    END IF;

    -- 🔒 ANTI-CERO: si no hubiera ninguna fila que dividir, los dos asserts de arriba
    --    saldrian verdes sin haber medido NADA. Es el caso mas facil de tragarse.
    IF n_div = 0 THEN
        RAISE WARNING 'ATENCION: no hay NI UNA fila de caja de TCG/HEO en este entorno, asi que la mitad que divide NO se ha comprobado. En produccion habia 15 el 25-ago-2026.';
    END IF;

    -- El dato crudo no se toca, y los nulos se propagan como nulos (no como ceros).
    SELECT count(*) FILTER (WHERE pa IS NULL AND pa_unitario IS NOT NULL) INTO n_nulos
      FROM v_escaner_ultimo;
    IF n_nulos > 0 THEN
        RAISE EXCEPTION 'ABORTA: % fila(s) con pa nulo tienen pa_unitario NO nulo. Un precio que no existe no puede convertirse en un numero.', n_nulos;
    END IF;

    SELECT max(pa_unitario) FILTER (WHERE es_case AND upper(proveedor) IN ('TCG','HEO'))
      INTO max_desvio FROM v_escaner_ultimo;
    RAISE NOTICE 'Testigo OK. % filas · % de caja de TCG/HEO divididas (el mas caro queda en %) · el resto intacto · contrato de 8 columnas con sus tipos.', n, n_div, max_desvio;
END
$testigo$;
