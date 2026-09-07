-- ============================================================================
-- inventario_fba · EL RELLENO RETROACTIVO del disponible estimado.   7-sep-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ EXISTE. Las tres columnas del puente (`disponible_estimado`,
--   `disponible_origen`, `disponible_fuente_fecha`) nacieron con la migración
--   `2026-09-07_inventario_fba_disponible_estimado.sql`, que es SOLO DDL y no
--   mueve una fila: las llena el procesador en su siguiente pasada. Pero esa
--   pasada no llega, porque la Guarda 12 mantiene la carga cerrada mientras las
--   cuatro vistas lean el NULO como cero. Resultado medido en producción el
--   7-sep-2026: **0 filas escritas de 4.423** (381 en la foto viva y 4.042 en el
--   histórico). Con las columnas vacías no hay nada que auditar y el puente no se
--   puede medir. Esto las llena hacia atrás con lo que el procesador habría escrito.
--
-- 🔑 LA REGLA, la misma que el procesador (`estimar_disponible`), por ASIN y sobre
--   la `fecha_foto` de cada fotograma:
--       estimado_asin = available_asin + max(0, intl_asin - entrantes_asin - available_asin)
--   El vendible es el suelo; el internacional sólo puede AÑADIR por encima. Los
--   entrantes se restan porque el internacional los cuenta y el vendible no.
--
-- 🔴 DE QUÉ FOTO SALE `intl_asin`, QUE ES LO QUE SE CORRIGIÓ HOY. De UNA sola foto
--   del internacional: la más reciente cuya `fecha_foto` no sea posterior al día
--   que se rellena, la MISMA para todos los ASIN de ese día. No de «la última
--   lectura de cada ASIN».
--   `inventario_internacional` es cajón FOTO: lo que no viene en la hoja, se BORRA.
--   Que un ASIN no esté en la foto no es «no lo sé», es «el internacional dice que
--   ahí no queda nada». Rescatarle una lectura de hace semanas resucita unidades
--   que ya no existen.
--   🔬 MEDIDO en producción el 7-sep-2026 sobre los 11 días del histórico (4.042
--   filas, con el tránsito LEÍDO y por tanto con verdad contra la que medir), a
--   nivel de ASIN-día:
--         una foto (esto)            → error 549 uds · clava 2.414 · se pasa 78
--         la última lectura del ASIN → error 2.204 uds · clava 2.456 · se pasa 715
--   Cuatro veces peor, y siempre por arriba: de los 71 ASIN que el 6-sep tiraban de
--   una lectura vieja, 68 se pasaban (el más viejo, de hace 45 días).
--   ⚠️ Y las cifras que justificaron el puente en la migración de esta mañana
--   (error 549, se pasa en 78 fichas con 487 uds, corta en 27 con 62) están medidas
--   ASÍ, con una foto. La medición era buena; el código hacía otra cosa. Este
--   fichero y el procesador ya hacen las dos lo mismo.
--
-- EL REPARTO ENTRE SKU de un mismo ASIN va en proporción al vendible de cada uno,
--   por restos mayores y con ARITMÉTICA ENTERA (resto exacto = (excedente*av) mod
--   av_asin, desempate por `sku`), exactamente como `_reparto` en el procesador. La
--   suma por ASIN es el estimado del ASIN, y ninguna ficha pierde su vendible.
--   🔬 Medido: 13 casos commingled en los 11 días (2 ASIN, 26 filas de 4.042) y
--   NINGUNO con excedente, así que hoy este reparto no mueve un solo dato.
--   🔴 Varios SKU y ninguno con vendible: no hay proporción con la que repartir y
--   NO se parte a ojo — queda a NULO, igual que en el procesador.
--
-- EL ORIGEN, y por qué después de rellenar sale 'leido' en las 4.423 filas:
--     'leido'       el informe de ese día trajo `afn-fc-transfer-quantity`
--     'estimado'    no lo trajo y sí hay internacional de ese ASIN
--     'desconocido' no lo trajo y tampoco hay internacional
--   🔬 Medido: los 11 días del histórico y la foto viva traen `fc_transfer` en las
--   4.423 filas, sin un solo hueco. O sea que todo el relleno es 'leido' — y la
--   estimación se guarda IGUAL, al lado de la verdad. Eso no es un adorno: es el
--   FALSADOR del puente, lo único que permite medir su error hacia atrás. Es
--   exactamente para lo que existe la columna del histórico.
--   🔴 `disponible_estimado` queda a NULO, nunca a 0, cuando no se ha podido
--   estimar. Un 0 diría «no hay» y esto es «no se sabe» (Stock 8).
--
-- 🔴 LO QUE ESTO **NO** TOCA, y conviene que esté escrito aquí:
--     · Ninguna vista. Ni una sola. (Hay seis que pierden `security_invoker` al
--       recrearse, y ésa es razón de sobra para no acercarse.)
--     · Ninguna otra columna de las dos tablas: el número de control compara la
--       huella de TODO lo demás antes y después, fila a fila.
--     · Ningún precio, ninguna decisión, nada del escáner ni de envíos.
--     · La lista `VISTAS_QUE_LEEN_NULO_COMO_CERO` (el cerrojo de la Guarda 12) se
--       queda como está: esto no abre la carga, sólo llena columnas que hoy no lee
--       nadie.
--   🔬 Comprobado el 7-sep-2026: los ÚNICOS objetos de la base que mencionan
--   `disponible_estimado` son las vistas `salud_fba` y `v_salud_asin`, y ninguna
--   otra vista, función o pantalla lee lo que aquí se escribe.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI FALTA ALGO. El testigo, antes de lanzarlo:
--       select count(disponible_origen) as escritas, count(*) as filas
--         from public.inventario_fba;
--   Medido en producción el 7-sep-2026: 0 de 381. Y 0 de 4.042 en el histórico.
--   🔒 Es IDEMPOTENTE: relanzarla vuelve a calcular lo mismo sobre los mismos
--   datos. No suma, no apila y no depende de cuántas veces se haya lanzado.
--
-- 🔴 SIN UNA SOLA CIFRA ABSOLUTA EN LAS GUARDAS, y por cuarta vez el mismo aviso:
--   la escalera empieza por STAGING, donde hay 362 fichas y 1.440 fotogramas contra
--   las 381 y 4.042 de producción. Lo que se exige no es un número: es que nada más
--   se mueva, y que lo escrito cuadre con lo recalculado EN ESE ENTORNO. Se
--   fotografía el antes y se compara contra él.
--
-- VUELTA ATRÁS: `2026-09-07_inventario_fba_relleno_vuelta_atras.sql` (deja las tres
--   columnas a NULO otra vez y comprueba que no ha movido nada más).
-- ESCALERA: restaurar staging → staging ensayo → staging aplicar → verificación por
--   SQL → producción ensayo → producción aplicar → verificación por SQL, con
--   `aplicar-migracion.yml`.
-- ============================================================================

-- ── 0) LO QUE TIENE QUE ESTAR ANTES DE EMPEZAR ──────────────────────────────
DO $$
DECLARE
  n_cols int; n_av int;
BEGIN
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public'
     AND table_name IN ('inventario_fba', 'inventario_fba_historico')
     AND column_name IN ('disponible_estimado', 'disponible_origen',
                         'disponible_fuente_fecha');
  IF n_cols <> 6 THEN
    RAISE EXCEPTION 'ABORTA: hacen falta las 6 columnas del puente (3 en cada tabla) '
                    'y hay %. Aplica antes 2026-09-07_inventario_fba_disponible_estimado.sql.',
                    n_cols;
  END IF;

  -- 🔴 UN `available` A NULO NO ES UN 0. El procesador reventaría (suma en Python);
  --    aquí un COALESCE lo tragaría en silencio y las dos cañerías dejarían de
  --    escribir lo mismo. La Guarda 6 no deja entrar huecos en las cantidades, así
  --    que esto no debería pasar nunca — y si pasa, se para.
  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE available IS NULL OR inbound_working IS NULL
              OR inbound_shipped IS NULL OR inbound_receiving IS NULL)
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE available IS NULL OR inbound_working IS NULL
              OR inbound_shipped IS NULL OR inbound_receiving IS NULL)
    INTO n_av;
  IF n_av <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) traen una CANTIDAD a nulo (available o entrantes). '
                    'Un hueco en una cantidad no es un cero: hay que mirarlo antes de '
                    'estimar nada sobre el.', n_av;
  END IF;
END $$;

-- ── 1) LA FOTO DEL «ANTES» ──────────────────────────────────────────────────
-- 🔑 La huella se calcula sobre la fila SIN las tres columnas del puente: es lo que
--    permite exigir «no se ha movido NADA más» sin escribir un solo número de
--    producción. `to_jsonb` menos las tres claves, no una lista de columnas a mano:
--    una lista se queda vieja el día que la tabla gane una columna.
CREATE TEMP TABLE _antes_fba ON COMMIT DROP AS
SELECT count(*) AS filas,
       count(t.disponible_origen) AS con_origen,
       md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                       - 'disponible_fuente_fecha')::text, ',' ORDER BY t.sku)) AS huella_resto
  FROM public.inventario_fba t;

CREATE TEMP TABLE _antes_hist ON COMMIT DROP AS
SELECT count(*) AS filas,
       count(t.disponible_origen) AS con_origen,
       md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                       - 'disponible_fuente_fecha')::text, ','
                      ORDER BY t.fecha_foto, t.sku)) AS huella_resto
  FROM public.inventario_fba_historico t;

-- ── 2) EL RELLENO · el histórico (cajón PELÍCULA, once fotogramas) ──────────
WITH foto AS (
    -- LA foto del internacional que le toca a cada día del FBA: una por día, la
    -- misma para todos sus ASIN. Sin foto anterior, ese día no se estima.
    SELECT d.fecha_foto AS dia,
           (SELECT max(h.fecha_foto)
              FROM public.inventario_internacional_historico h
             WHERE h.fecha_foto <= d.fecha_foto) AS f_intl
      FROM (SELECT DISTINCT fecha_foto FROM public.inventario_fba_historico) d
), intl AS (
    -- TODOS los países, sin filtrar: el internacional cuenta el ASIN entero.
    SELECT f.dia, f.f_intl, h.asin, sum(h.quantity) AS uds
      FROM foto f
      JOIN public.inventario_internacional_historico h ON h.fecha_foto = f.f_intl
     GROUP BY f.dia, f.f_intl, h.asin
), grupo AS (
    SELECT i.fecha_foto AS dia, i.asin, count(*) AS n_sku,
           sum(i.available) AS av_asin,
           sum(i.inbound_working + i.inbound_shipped + i.inbound_receiving) AS ent_asin
      FROM public.inventario_fba_historico i
     GROUP BY 1, 2
), exc AS (
    SELECT g.*, t.f_intl,
           CASE WHEN t.uds IS NULL THEN NULL
                ELSE greatest(0, t.uds - g.ent_asin - g.av_asin) END AS excedente
      FROM grupo g
      LEFT JOIN intl t ON t.dia = g.dia AND t.asin = g.asin
), trozo AS (
    -- El reparto en ENTEROS: parte0 = (excedente*av) / av_asin y
    -- resto = (excedente*av) mod av_asin. Exacto, y el mismo criterio que `_reparto`.
    SELECT i.sku, i.fecha_foto AS dia, i.asin, i.available AS av, e.f_intl, e.excedente,
           CASE WHEN e.excedente IS NULL THEN NULL
                WHEN e.excedente = 0     THEN 0
                WHEN e.av_asin > 0       THEN (e.excedente * i.available) / e.av_asin
                WHEN e.n_sku = 1         THEN e.excedente
                ELSE NULL END AS parte0,
           CASE WHEN e.excedente IS NULL OR e.excedente = 0 OR e.av_asin = 0 THEN 0
                ELSE (e.excedente * i.available) % e.av_asin END AS resto
      FROM public.inventario_fba_historico i
      JOIN exc e ON e.dia = i.fecha_foto AND e.asin = i.asin
), reparto AS (
    SELECT t.*,
           row_number() OVER (PARTITION BY t.dia, t.asin
                              ORDER BY t.resto DESC, t.sku) AS rn,
           t.excedente - sum(t.parte0) OVER (PARTITION BY t.dia, t.asin) AS faltan
      FROM trozo t
), fin AS (
    SELECT r.sku, r.dia, r.av, r.f_intl,
           CASE WHEN r.parte0 IS NULL THEN NULL
                ELSE r.parte0 + CASE WHEN r.rn <= r.faltan THEN 1 ELSE 0 END END AS parte
      FROM reparto r
)
UPDATE public.inventario_fba_historico t
   SET disponible_estimado     = CASE WHEN f.parte IS NULL THEN NULL ELSE f.av + f.parte END,
       disponible_fuente_fecha = CASE WHEN f.parte IS NULL THEN NULL ELSE f.f_intl END,
       disponible_origen       = CASE WHEN t.fc_transfer IS NOT NULL THEN 'leido'
                                      WHEN f.parte IS NOT NULL       THEN 'estimado'
                                      ELSE 'desconocido' END
  FROM fin f
 WHERE t.sku = f.sku AND t.fecha_foto = f.dia;

-- ── 3) EL RELLENO · la foto viva (cajón FOTO, un solo día) ──────────────────
WITH foto AS (
    SELECT d.fecha_foto AS dia,
           (SELECT max(h.fecha_foto)
              FROM public.inventario_internacional_historico h
             WHERE h.fecha_foto <= d.fecha_foto) AS f_intl
      FROM (SELECT DISTINCT fecha_foto FROM public.inventario_fba) d
), intl AS (
    SELECT f.dia, f.f_intl, h.asin, sum(h.quantity) AS uds
      FROM foto f
      JOIN public.inventario_internacional_historico h ON h.fecha_foto = f.f_intl
     GROUP BY f.dia, f.f_intl, h.asin
), grupo AS (
    SELECT i.fecha_foto AS dia, i.asin, count(*) AS n_sku,
           sum(i.available) AS av_asin,
           sum(i.inbound_working + i.inbound_shipped + i.inbound_receiving) AS ent_asin
      FROM public.inventario_fba i
     GROUP BY 1, 2
), exc AS (
    SELECT g.*, t.f_intl,
           CASE WHEN t.uds IS NULL THEN NULL
                ELSE greatest(0, t.uds - g.ent_asin - g.av_asin) END AS excedente
      FROM grupo g
      LEFT JOIN intl t ON t.dia = g.dia AND t.asin = g.asin
), trozo AS (
    SELECT i.sku, i.fecha_foto AS dia, i.asin, i.available AS av, e.f_intl, e.excedente,
           CASE WHEN e.excedente IS NULL THEN NULL
                WHEN e.excedente = 0     THEN 0
                WHEN e.av_asin > 0       THEN (e.excedente * i.available) / e.av_asin
                WHEN e.n_sku = 1         THEN e.excedente
                ELSE NULL END AS parte0,
           CASE WHEN e.excedente IS NULL OR e.excedente = 0 OR e.av_asin = 0 THEN 0
                ELSE (e.excedente * i.available) % e.av_asin END AS resto
      FROM public.inventario_fba i
      JOIN exc e ON e.dia = i.fecha_foto AND e.asin = i.asin
), reparto AS (
    SELECT t.*,
           row_number() OVER (PARTITION BY t.dia, t.asin
                              ORDER BY t.resto DESC, t.sku) AS rn,
           t.excedente - sum(t.parte0) OVER (PARTITION BY t.dia, t.asin) AS faltan
      FROM trozo t
), fin AS (
    SELECT r.sku, r.dia, r.av, r.f_intl,
           CASE WHEN r.parte0 IS NULL THEN NULL
                ELSE r.parte0 + CASE WHEN r.rn <= r.faltan THEN 1 ELSE 0 END END AS parte
      FROM reparto r
)
UPDATE public.inventario_fba t
   SET disponible_estimado     = CASE WHEN f.parte IS NULL THEN NULL ELSE f.av + f.parte END,
       disponible_fuente_fecha = CASE WHEN f.parte IS NULL THEN NULL ELSE f.f_intl END,
       disponible_origen       = CASE WHEN t.fc_transfer IS NOT NULL THEN 'leido'
                                      WHEN f.parte IS NOT NULL       THEN 'estimado'
                                      ELSE 'desconocido' END
  FROM fin f
 WHERE t.sku = f.sku AND t.fecha_foto = f.dia;

-- ── 4) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  n bigint; txt text;
BEGIN
  -- 4.1 · NO SE HA MOVIDO NADA MÁS. Ni una fila de más o de menos, y el resto de
  --       cada fila bit a bit igual que antes del UPDATE.
  SELECT a.filas INTO n FROM _antes_fba a;
  IF n <> (SELECT count(*) FROM public.inventario_fba) THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba tenia % filas y ahora tiene otra cosa.', n;
  END IF;
  SELECT a.filas INTO n FROM _antes_hist a;
  IF n <> (SELECT count(*) FROM public.inventario_fba_historico) THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba_historico tenia % filas y ahora tiene otra cosa.', n;
  END IF;

  SELECT a.huella_resto INTO txt FROM _antes_fba a;
  IF txt IS DISTINCT FROM (
        SELECT md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                               - 'disponible_fuente_fecha')::text, ',' ORDER BY t.sku))
          FROM public.inventario_fba t) THEN
    RAISE EXCEPTION 'ABORTA: en inventario_fba ha cambiado alguna columna que NO es del '
                    'puente. Esta migracion solo puede tocar las tres.';
  END IF;
  SELECT a.huella_resto INTO txt FROM _antes_hist a;
  IF txt IS DISTINCT FROM (
        SELECT md5(string_agg((to_jsonb(t) - 'disponible_estimado' - 'disponible_origen'
                               - 'disponible_fuente_fecha')::text, ','
                              ORDER BY t.fecha_foto, t.sku))
          FROM public.inventario_fba_historico t) THEN
    RAISE EXCEPTION 'ABORTA: en inventario_fba_historico ha cambiado alguna columna que NO '
                    'es del puente.';
  END IF;

  -- 4.2 · NO QUEDA NI UNA FILA SIN ESCRIBIR. El origen siempre se sabe: como
  --       minimo es 'desconocido', que tambien es una respuesta.
  SELECT (SELECT count(*) FROM public.inventario_fba WHERE disponible_origen IS NULL)
       + (SELECT count(*) FROM public.inventario_fba_historico WHERE disponible_origen IS NULL)
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) se han quedado sin disponible_origen.', n;
  END IF;

  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE disponible_origen NOT IN ('leido', 'estimado', 'desconocido'))
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE disponible_origen NOT IN ('leido', 'estimado', 'desconocido'))
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) con un disponible_origen que no es ninguno de los tres.', n;
  END IF;

  -- 4.3 · LA CIFRA Y SU FUENTE VAN JUNTAS O NO VAN. Un estimado sin fecha de fuente
  --       no se puede auditar, y una fecha sin cifra no significa nada.
  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE (disponible_estimado IS NULL) <> (disponible_fuente_fecha IS NULL))
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE (disponible_estimado IS NULL) <> (disponible_fuente_fecha IS NULL))
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) tienen cifra sin fuente o fuente sin cifra.', n;
  END IF;

  -- 4.4 · 🔴 'desconocido' SIGNIFICA NULO, NUNCA 0 (Stock 8).
  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE disponible_origen = 'desconocido' AND disponible_estimado IS NOT NULL)
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE disponible_origen = 'desconocido' AND disponible_estimado IS NOT NULL)
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) marcadas «desconocido» traen un numero. '
                    'Desconocido es NULO, no un cero.', n;
  END IF;

  -- 4.5 · EL VENDIBLE ES EL SUELO. El internacional solo puede anadir por encima:
  --       si una fila estimada quedara por debajo de su propio available, la formula
  --       se ha escrito al reves.
  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE disponible_estimado IS NOT NULL AND disponible_estimado < available)
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE disponible_estimado IS NOT NULL AND disponible_estimado < available)
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) con un estimado POR DEBAJO de su vendible. '
                    'El vendible es el suelo.', n;
  END IF;

  -- 4.6 · 🔴 JAMAS UNA FUENTE DEL FUTURO: estimar un dia con el internacional de un
  --       dia posterior daria un numero que ese dia no existia.
  SELECT (SELECT count(*) FROM public.inventario_fba
           WHERE disponible_fuente_fecha > fecha_foto)
       + (SELECT count(*) FROM public.inventario_fba_historico
           WHERE disponible_fuente_fecha > fecha_foto)
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) estimadas con un internacional POSTERIOR a su foto.', n;
  END IF;

  -- 4.7 · 🔑 UNA FOTO POR DIA, Y ES LA QUE TOCA. Esta es la guarda de la regla que
  --       se corrige hoy: si alguien vuelve a «la ultima lectura de cada ASIN», un
  --       mismo dia acabaria con fuentes de varios dias distintos y esto salta.
  SELECT count(*) INTO n FROM (
      SELECT fecha_foto FROM public.inventario_fba_historico
       WHERE disponible_fuente_fecha IS NOT NULL
       GROUP BY fecha_foto HAVING count(DISTINCT disponible_fuente_fecha) > 1
      UNION ALL
      SELECT fecha_foto FROM public.inventario_fba
       WHERE disponible_fuente_fecha IS NOT NULL
       GROUP BY fecha_foto HAVING count(DISTINCT disponible_fuente_fecha) > 1) z;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % dia(s) tienen filas estimadas con fotos del internacional '
                    'de fechas DISTINTAS. La foto es una sola por dia.', n;
  END IF;

  SELECT count(*) INTO n FROM (
      SELECT min(t.disponible_fuente_fecha) AS usada,
             (SELECT max(h.fecha_foto) FROM public.inventario_internacional_historico h
               WHERE h.fecha_foto <= t.fecha_foto) AS toca
        FROM public.inventario_fba_historico t
       WHERE t.disponible_fuente_fecha IS NOT NULL
       GROUP BY t.fecha_foto
      UNION ALL
      SELECT min(t.disponible_fuente_fecha),
             (SELECT max(h.fecha_foto) FROM public.inventario_internacional_historico h
               WHERE h.fecha_foto <= t.fecha_foto)
        FROM public.inventario_fba t
       WHERE t.disponible_fuente_fecha IS NOT NULL
       GROUP BY t.fecha_foto) z
   WHERE z.usada IS DISTINCT FROM z.toca;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % dia(s) se han estimado con una foto del internacional que no '
                    'es la mas reciente anterior a ese dia.', n;
  END IF;

  -- 4.8 · LA SUMA POR ASIN ES EL ESTIMADO DEL ASIN, recalculado APARTE y con la
  --       formula escrita de la otra manera —max(av, intl-ent) en vez de
  --       av+max(0,intl-ent-av)— para que no sea la misma expresion comparandose
  --       consigo misma. Solo donde TODAS las fichas del ASIN llevan cifra.
  SELECT count(*) INTO n FROM (
      SELECT sum(t.disponible_estimado) AS escrito,
             greatest(sum(t.available),
                      (SELECT sum(h.quantity)
                         FROM public.inventario_internacional_historico h
                        WHERE h.asin = t.asin
                          AND h.fecha_foto = (SELECT max(h2.fecha_foto)
                                                FROM public.inventario_internacional_historico h2
                                               WHERE h2.fecha_foto <= t.fecha_foto))
                      - sum(t.inbound_working + t.inbound_shipped + t.inbound_receiving)
             ) AS recalculado
        FROM public.inventario_fba_historico t
       GROUP BY t.fecha_foto, t.asin
      HAVING count(*) = count(t.disponible_estimado)) z
   WHERE z.escrito IS DISTINCT FROM z.recalculado;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: en % ASIN-dia del historico la suma escrita no es el estimado '
                    'del ASIN recalculado.', n;
  END IF;

  SELECT count(*) INTO n FROM (
      SELECT sum(t.disponible_estimado) AS escrito,
             greatest(sum(t.available),
                      (SELECT sum(h.quantity)
                         FROM public.inventario_internacional_historico h
                        WHERE h.asin = t.asin
                          AND h.fecha_foto = (SELECT max(h2.fecha_foto)
                                                FROM public.inventario_internacional_historico h2
                                               WHERE h2.fecha_foto <= t.fecha_foto))
                      - sum(t.inbound_working + t.inbound_shipped + t.inbound_receiving)
             ) AS recalculado
        FROM public.inventario_fba t
       GROUP BY t.fecha_foto, t.asin
      HAVING count(*) = count(t.disponible_estimado)) z
   WHERE z.escrito IS DISTINCT FROM z.recalculado;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: en % ASIN de la foto viva la suma escrita no es el estimado '
                    'del ASIN recalculado.', n;
  END IF;

  -- 4.9 · Y EL ASIN QUE NO ESTA EN LA FOTO NO SE ESTIMA. Es la otra mitad de 4.7:
  --       sin esto, «una sola fecha» se cumpliria tambien rellenando de mas.
  SELECT (SELECT count(*) FROM public.inventario_fba_historico t
           WHERE t.disponible_estimado IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM public.inventario_internacional_historico h
                              WHERE h.asin = t.asin
                                AND h.fecha_foto = t.disponible_fuente_fecha))
       + (SELECT count(*) FROM public.inventario_fba t
           WHERE t.disponible_estimado IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM public.inventario_internacional_historico h
                              WHERE h.asin = t.asin
                                AND h.fecha_foto = t.disponible_fuente_fecha))
    INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) llevan estimacion sin estar su ASIN en la foto del '
                    'internacional que dicen haber usado.', n;
  END IF;

  RAISE NOTICE 'Relleno OK: % filas en la foto viva y % en el historico, todas con origen; '
               'nada mas se ha movido.',
               (SELECT count(*) FROM public.inventario_fba),
               (SELECT count(*) FROM public.inventario_fba_historico);
  RAISE NOTICE 'Origen (viva): % leido / % estimado / % desconocido · '
               '(historico): % / % / %.',
    (SELECT count(*) FROM public.inventario_fba WHERE disponible_origen = 'leido'),
    (SELECT count(*) FROM public.inventario_fba WHERE disponible_origen = 'estimado'),
    (SELECT count(*) FROM public.inventario_fba WHERE disponible_origen = 'desconocido'),
    (SELECT count(*) FROM public.inventario_fba_historico WHERE disponible_origen = 'leido'),
    (SELECT count(*) FROM public.inventario_fba_historico WHERE disponible_origen = 'estimado'),
    (SELECT count(*) FROM public.inventario_fba_historico WHERE disponible_origen = 'desconocido');
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   -- 1) ya no queda nada sin escribir:
--   select count(*) filas, count(disponible_origen) escritas,
--          count(disponible_estimado) con_cifra
--     from public.inventario_fba;
--
--   -- 2) el FALSADOR del puente: los dias que el transito viene LEIDO, el estimado
--   --    y la verdad conviven. Esto es lo que mide el error hacia atras:
--   select count(*) filter (where disponible_estimado = available + fc_transfer) clava,
--          count(*) filter (where disponible_estimado > available + fc_transfer) se_pasa,
--          count(*) filter (where disponible_estimado < available + fc_transfer) corto,
--          sum(abs(disponible_estimado - (available + fc_transfer)))             error_uds
--     from public.inventario_fba_historico
--    where disponible_origen = 'leido' and disponible_estimado is not null;
--
--   -- 3) la fuente, dia a dia (una sola por dia, y nunca futura):
--   select fecha_foto, count(distinct disponible_fuente_fecha) fuentes,
--          min(disponible_fuente_fecha) usada
--     from public.inventario_fba_historico group by 1 order by 1;
-- ============================================================================
