-- ============================================================================
-- MIGRACIÓN · ÍNDICE para el LATERAL de Keepa que tumba la pestaña Inventario
-- ----------------------------------------------------------------------------
-- 🔴 ESTO ES UNA CAÍDA EN PRODUCCIÓN, no una mejora. El 24-ago-2026 por la
--    mañana `https://moloka-app-v2.vercel.app/inventario` devuelve
--    «No se pudo leer salud_fba: canceling statement due to statement timeout»
--    en dos cargas seguidas. Elena bloqueada.
--
-- EL FALLO, medido con EXPLAIN (ANALYZE, BUFFERS) sobre PRODUCCIÓN — no
-- deducido. La vista `salud_fba` (nace el 23-ago-2026) cierra con un LATERAL:
--
--        LEFT JOIN LATERAL (SELECT ke.rank FROM keepa_escaparate ke
--                            WHERE btrim(ke.asin) = btrim(i.asin)
--                              AND lower(ke.dominio) = 'es'
--                            ORDER BY ke.fecha_foto DESC LIMIT 1) k ON true
--
--    `btrim()` y `lower()` envuelven las dos columnas del filtro, y una columna
--    envuelta en una función NO puede usar un índice normal. Los cuatro índices
--    que ya tiene la tabla —incluido su PK `UNIQUE (asin, dominio)`— quedan
--    ciegos, y el planificador se cae al único plan que le queda: recorrer la
--    tabla ENTERA de Keepa una vez por producto.
--
-- 🔬 LAS CIFRAS (producción, 24-ago-2026). Las dos lecturas, la de Fernando bajo
--    carga y la mía en frío, dan **exactamente los mismos buffers**:
--
--        ->  Seq Scan on keepa_escaparate ke   (loops=353)
--              Filter: (lower(dominio)='es' AND btrim(asin)=btrim(i.asin))
--              Rows Removed by Filter: 1652
--              Buffers: shared hit=204.034      <- de 206.212 del total = 98,9 %
--
--    353 vueltas x 578 páginas (la tabla ocupa 4.624 kB para 1.653 filas: son
--    filas anchas) = las 204.034. El tiempo SÍ varía —2.257 ms bajo carga,
--    474 ms en frío—, los buffers no. **Por eso el testigo de abajo mide
--    buffers y plan, no milisegundos**: es la única cifra que no depende de
--    quién más esté trabajando en ese momento.
--
-- 🔴 Y CUÁNTO SE PASÓ, que es peor de lo que parece. La app lee `salud_fba`
--    como `authenticated` —medido: `has_table_privilege('anon', …)` es FALSE,
--    `authenticated` TRUE—, y ese rol tiene `statement_timeout = 8s`. O sea que
--    el error de Elena no es una consulta de 2,8 s rozando un techo de 3: es una
--    consulta que **se pasó de OCHO segundos**. Las dos lecturas de EXPLAIN
--    (2.257 ms bajo carga, 474 ms en frío) se tomaron en momentos MÁS tranquilos
--    que el del fallo, así que ninguna de las dos ve el pico que lo tumbó.
--    🔑 Lo que eso significa para el arreglo: con 206.212 buffers la consulta
--       queda a merced de lo que haga el resto de la base, y por eso falla «dos
--       veces seguidas» sin que nadie haya cambiado nada. Bajar a ~3.555 no la
--       hace un 58 % más rápida: la saca de la zona en la que la carga ajena
--       decide si Elena puede trabajar.
--
-- EL ARREGLO: un índice funcional cuyas expresiones son LAS MISMAS que las del
-- LATERAL, para que el planificador pueda casarlas. Ni una línea de la vista se
-- toca, ni un dato se mueve, y se deshace con un `DROP INDEX`.
--
-- 🔬 LO QUE SE MIDIÓ ANTES DE ELEGIR ESTE CAMINO Y NO OTRO, porque cambia la
--    lectura del problema y merece quedar escrito:
--      · `btrim()` y `lower()` HOY NO HACEN NADA. Medido sobre las 1.653 filas:
--        **0** asin con espacios sobrantes y **0** dominios que no estén ya en
--        minúscula. O sea que la vista paga un recorrido completo de la tabla
--        por dos funciones defensivas que no corrigen ni una fila.
--      · Y el PK **`UNIQUE (asin, dominio)`** ya existe: sin los envoltorios,
--        este LATERAL lo usaría tal cual y no haría falta índice ninguno.
--    ⚠️ Aun así, el arreglo de hoy es el ÍNDICE y no tocar la vista, y es una
--       decisión, no una pereza: quitar `btrim`/`lower` cambia el resultado si
--       algún día entra un ASIN con un espacio (y quien escribe esa tabla es un
--       CSV de Keepa, que es exactamente de donde salen esas sorpresas),
--       mientras que el índice es aditivo y no puede cambiar nada. Con la
--       pestaña caída se elige lo que no puede tener efectos laterales.
--       **La simplificación de la vista queda ANOTADA para decidirse en frío**,
--       que es donde se deciden las de diseño, no en una caída.
--
-- ⚠️ LO QUE ESTA MIGRACIÓN NO ARREGLA, dicho para que nadie lo dé por hecho:
--    el segundo coste de la vista es `v_ventas_ventanas` (2.175 buffers, 1 % —
--    aunque bajo carga se llevaba 1.163 ms de los 2.257). Un índice compuesto
--    `(event_type, fecha)` sobre `ledger_movimientos` lo mejoraría. **NO entra
--    aquí a propósito**: un PR, una cosa, y primero que Elena pueda trabajar.
--
-- ⚠️ Y EL `Planning Time: 542 ms` que se vio bajo carga NO SE HA PODIDO
--    REPRODUCIR: en frío mide **6,1 ms**, noventa veces menos, con
--    `Planning: Buffers: shared hit=805 read=1`. Eso apunta a caché de catálogo
--    fría en la primera consulta de una conexión, no a estadísticas viejas. Se
--    deja el `ANALYZE` igualmente porque es gratis y porque el índice de
--    expresión LO NECESITA (ver paso 3), pero **no se vende como el arreglo del
--    planificado**: eso no está medido y no se finge que lo esté.
-- ============================================================================

-- Criterio de la casa para todo DDL en producción: fallar rápido en vez de
-- encolarse. `CREATE INDEX` toma un SHARE sobre la tabla y bloquea a quien
-- escriba —el procesador de Keepa—; si justo está corriendo, que reviente en 3 s
-- y se reintente, que es lo contrario de lo que tumbó la app el 28-jul.
SET lock_timeout = '3s';

-- ---------------------------------------------------------------------------
-- 1) GUARDAS PREVIAS y FOTO DEL ANTES.
--    🔴 La primera guarda es la que evita el peor de los falsos verdes: si el
--       índice YA existiera, el «antes» ya sería un Index Scan, el testigo del
--       final saldría verde y no habría demostrado nada (§3 de CLAUDE.md, «un
--       ensayo sobre un estado que ya es el de destino no prueba nada»). Aquí
--       se exige ver el Seq Scan ANTES: si no está, esto no mide.
-- ---------------------------------------------------------------------------
DO $guardas$
DECLARE
    k char; n_keepa bigint; n_inv bigint;
    v_plan json; v_nodo jsonb; v_tipo text;
BEGIN
    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.salud_fba');
    IF k IS NULL OR k <> 'v' THEN
        RAISE EXCEPTION 'ABORTA: `salud_fba` no existe o no es una vista (relkind=%). Esta migracion arregla el LATERAL de esa vista.', k;
    END IF;

    SELECT count(*) INTO n_keepa FROM public.keepa_escaparate;
    SELECT count(*) INTO n_inv   FROM public.inventario_fba;
    -- Sin filas en las dos, cualquier EXPLAIN de abajo seria un tramite: no
    -- habria ni tabla que recorrer ni vueltas que dar. Es el «mirar que habia
    -- algo que comprobar» de §3.
    IF n_keepa = 0 OR n_inv = 0 THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate=% filas, inventario_fba=% filas. Con alguna a cero el testigo no podria medir nada.', n_keepa, n_inv;
    END IF;

    EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM public.salud_fba' INTO v_plan;
    v_nodo := jsonb_path_query_first(v_plan::jsonb, '$.** ? (@."Relation Name" == "keepa_escaparate")');
    IF v_nodo IS NULL THEN
        RAISE EXCEPTION 'ABORTA: el plan de salud_fba no toca keepa_escaparate. La vista no es la que esta migracion cree.';
    END IF;
    v_tipo := v_nodo->>'Node Type';

    IF v_tipo <> 'Seq Scan' THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate ya se lee con «%», no con «Seq Scan». O el indice ya esta puesto o alguien arreglo la vista: en los dos casos este ensayo saldria verde SIN demostrar nada, que es justo el falso verde que se quiere evitar. Mira el estado antes de relanzar.', v_tipo;
    END IF;

    CREATE TEMP TABLE _antes ON COMMIT DROP AS
    SELECT (v_nodo->>'Shared Hit Blocks')::bigint                     AS buffers_keepa,
           ((v_plan::jsonb)->0->'Plan'->>'Shared Hit Blocks')::bigint AS buffers_total,
           (SELECT md5(string_agg(t::text, '|' ORDER BY t.sku, t.marketplace))
              FROM public.salud_fba t)                                AS huella_datos,
           (SELECT count(*) FROM public.salud_fba)                    AS filas;

    RAISE NOTICE 'ANTES: keepa_escaparate se lee con Seq Scan · % buffers de % totales (% %%). keepa=% filas, inventario=% filas.',
        (SELECT buffers_keepa FROM _antes), (SELECT buffers_total FROM _antes),
        round(100.0 * (SELECT buffers_keepa FROM _antes) / nullif((SELECT buffers_total FROM _antes), 0), 1),
        n_keepa, n_inv;
END $guardas$;

-- ---------------------------------------------------------------------------
-- 2) EL ÍNDICE. Las expresiones son CALCADAS a las del LATERAL —`btrim(asin)` y
--    `lower(dominio)`, en ese orden, que es el de las igualdades— y `fecha_foto
--    DESC` al final para que el `ORDER BY … LIMIT 1` salga del propio índice sin
--    ordenar nada.
--    🔒 Las dos funciones son IMMUTABLE (`provolatile='i'`, comprobado en
--       `pg_proc`), que es el requisito para poder indexarlas.
--    ⚠️ SIN `CONCURRENTLY` a propósito: 1.653 filas se indexan en milisegundos,
--       y `CONCURRENTLY` no puede correr dentro de una transacción — o sea que
--       dejaría a esta migración sin su testigo y sin su vuelta atrás.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_keepa_asin_dominio_foto
    ON public.keepa_escaparate (btrim(asin), lower(dominio), fecha_foto DESC);

COMMENT ON INDEX public.idx_keepa_asin_dominio_foto IS
  'Da vista al LATERAL de salud_fba, que filtra por btrim(asin) y lower(dominio). Un indice normal '
  'no vale: las columnas van envueltas en funciones y el PK (asin, dominio) queda ciego. Nace el '
  '24-ago-2026 porque la pestana Inventario caia por statement timeout — el LATERAL recorria las '
  '1.653 filas de Keepa una vez por producto (204.034 buffers, el 98,9% del coste de la vista). '
  'Si algun dia se quitan btrim()/lower() de la vista, este indice sobra y el PK hace el trabajo.';

-- ---------------------------------------------------------------------------
-- 3) ANALYZE. No es cosmético: un índice de EXPRESIÓN estrena su propia entrada
--    de estadísticas, y hasta que no se analiza la tabla el planificador no
--    tiene ni idea de la selectividad de `btrim(asin)`. Sin esto el índice
--    existe pero puede no elegirse.
--    Las otras dos tablas del plan van de propina: es gratis y no mueve datos.
-- ---------------------------------------------------------------------------
ANALYZE public.keepa_escaparate;
ANALYZE public.inventario_fba;
ANALYZE public.ledger_movimientos;

-- ---------------------------------------------------------------------------
-- 4) TESTIGOS. Tres, y cada uno mide algo que los otros no:
--      a) EL PLAN cambió — ya no es un Seq Scan. Es la pregunta de Fernando
--         escrita como guarda: «si sigue saliendo Seq Scan, el indice no esta
--         casando con las expresiones y hay que mirarlo, no darlo por bueno».
--      b) LOS BUFFERS cayeron un orden de magnitud. Que el plan cambie sin que
--         el coste baje seria un arreglo de mentira.
--      c) LOS DATOS NO SE MOVIERON. Un indice no puede cambiar un resultado; si
--         lo cambia, es que el LATERAL estaba eligiendo fila por azar entre
--         empates, y eso es un hallazgo, no un detalle.
-- ---------------------------------------------------------------------------
DO $testigo$
DECLARE
    v_plan json; v_nodo jsonb; v_tipo text;
    b_keepa bigint; b_total bigint; h_datos text; n_filas bigint;
    a_keepa bigint; a_total bigint; a_datos text; a_filas bigint;
    factor numeric;
BEGIN
    SELECT buffers_keepa, buffers_total, huella_datos, filas
      INTO a_keepa, a_total, a_datos, a_filas FROM _antes;

    EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM public.salud_fba' INTO v_plan;
    v_nodo := jsonb_path_query_first(v_plan::jsonb, '$.** ? (@."Relation Name" == "keepa_escaparate")');
    IF v_nodo IS NULL THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate ha desaparecido del plan. Algo mas ha cambiado aparte de esta migracion.';
    END IF;
    v_tipo  := v_nodo->>'Node Type';
    b_keepa := (v_nodo->>'Shared Hit Blocks')::bigint;
    b_total := ((v_plan::jsonb)->0->'Plan'->>'Shared Hit Blocks')::bigint;

    -- (a) EL PLAN
    IF v_tipo = 'Seq Scan' THEN
        RAISE EXCEPTION 'ABORTA: keepa_escaparate SIGUE con Seq Scan (% buffers). El indice no esta casando con las expresiones del LATERAL — revisalo, no lo des por bueno.', b_keepa;
    END IF;

    -- (b) EL COSTE
    factor := a_keepa::numeric / nullif(b_keepa, 0);
    IF factor < 10 THEN
        RAISE EXCEPTION 'ABORTA: el plan es «%» pero los buffers de keepa solo bajan de % a % (x%). Se esperaba al menos un orden de magnitud; un plan nuevo que no abarata nada no arregla la caida.',
            v_tipo, a_keepa, b_keepa, round(factor, 1);
    END IF;

    -- (c) LOS DATOS
    SELECT md5(string_agg(t::text, '|' ORDER BY t.sku, t.marketplace)), count(*)
      INTO h_datos, n_filas FROM public.salud_fba t;
    IF h_datos IS DISTINCT FROM a_datos OR n_filas <> a_filas THEN
        RAISE EXCEPTION 'ABORTA: salud_fba devuelve datos DISTINTOS tras el indice (% filas -> %, huella % -> %). Un indice no cambia resultados: si cambia, el LATERAL desempataba por azar y eso hay que mirarlo antes de seguir.',
            a_filas, n_filas, a_datos, h_datos;
    END IF;

    RAISE NOTICE 'VERDE (a) el plan: keepa_escaparate pasa de «Seq Scan» a «%».', v_tipo;
    RAISE NOTICE 'VERDE (b) el coste: keepa % -> % buffers (x% menos) · total de la vista % -> % (x% menos).',
        a_keepa, b_keepa, round(factor, 1), a_total, b_total, round(a_total::numeric / nullif(b_total, 0), 1);
    RAISE NOTICE 'VERDE (c) los datos: % filas y huella % IDENTICAS antes y despues.', n_filas, h_datos;
END $testigo$;
