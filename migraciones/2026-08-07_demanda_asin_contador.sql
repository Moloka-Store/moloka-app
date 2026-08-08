-- ============================================================================
-- MIGRACIÓN 2026-08-07 · demanda_asin: de "FOTO POR VENTANA" a CONTADOR ACUMULADO
-- ----------------------------------------------------------------------------
-- QUÉ CAMBIA Y POR QUÉ. La migración del 31-jul asumió que el export de Custom
--   Analytics cubre una VENTANA que declara quien sube (periodo_desde/periodo_hasta).
--   Es falso. Medido el 7-ago-2026 comparando el export de ES del 30-jul 18:06 con el
--   del 7-ago 18:03, ASIN por ASIN: 1.605 comparaciones ASIN×métrica, CERO bajadas y
--   CERO ASIN desaparecidos (321 comunes, 25 nuevos).
--
--   🔑 El informe es un CUENTAKILÓMETROS: un contador acumulado desde un punto de
--   partida fijo y DESCONOCIDO. A un cuentakilómetros no se le pregunta de qué periodo
--   son sus kilómetros: se anota la lectura, se anota CUÁNDO se tomó, y los kilómetros
--   del viaje son la RESTA entre dos lecturas.
--
--   Consecuencia para el esquema: la ventana declarada desaparece y el eje del dato
--   pasa a ser `leido_at` = wb.properties.created del .xlsx. La fecha sale del
--   CONTENIDO del fichero, jamás de "hoy" ni de nadie (regla de la casa, la misma que
--   fecha_del_dato_por_subida() de foto_comun).
--
-- 🔴 ALTER, NUNCA DROP + CREATE. Un DROP de la tabla se llevaría por delante la
--   política `inventario_read_authenticated` y el GRANT del Cockpit, y habría que
--   rehacerlos y coordinarlos con otra sesión. Con la tabla a 0 filas en producción
--   (medido hoy) el ALTER es trivial y no toca la seguridad de la TABLA.
--
-- 🔴 LAS DOS VISTAS SÍ HAY QUE RECREARLAS — y eso NO estaba en el encargo.
--   Medido en pg_depend contra producción: cuelgan de las columnas que se van.
--       demanda_asin.periodo_desde / periodo_hasta / dias
--         └── v_demanda_asin_ultima          (authenticated=r)
--               └── v_trackeador_cola        (authenticated=r)
--   · El primer `ALTER … DROP COLUMN dias` YA falla ("cannot drop column … because
--     other objects depend on it"): Postgres SÍ registra las dependencias de vistas.
--   · `CREATE OR REPLACE VIEW` no sirve para la vista nueva: REPLACE solo deja AÑADIR
--     columnas al final, y aquí se QUITAN tres. Hay que DROP + CREATE.
--   · Y por §4 de CLAUDE.md, **DROP + CREATE PIERDE EL ACL**: las dos vistas renacerían
--     con el default de Supabase (anon Y authenticated con arwdDxtm). Por eso el
--     revoke+grant va DESPUÉS de cada CREATE, en esta misma migración, y se MIDE al
--     terminar. Hoy las dos tienen `authenticated=r` y así se quedan.
--
-- 🔴 Y frescura_informes() SE ROMPE EN SILENCIO — tampoco estaba en el encargo.
--   Su cuerpo lleva `(select max(periodo_hasta) from demanda_asin)`. Es LANGUAGE sql
--   con cuerpo en cadena: Postgres NO registra dependencias de columnas ahí, así que
--   el ALTER pasa tan contento y la RPC revienta la PRÓXIMA VEZ QUE ALGUIEN LA LLAMA.
--   Quien la llama es lib/buzones/query.ts de la v2, que ante un error de la RPC lanza
--   BuzonesRpcError: no es "una tarjeta gris", es la pantalla de Buzones de Elena
--   ENTERA caída, las 8 tarjetas. Por eso la línea se arregla AQUÍ y no en otro PR:
--   partirlo dejaría la pantalla rota entre dos merges.
--   El fecha_dato nuevo del informe es `max(leido_at)::date` — el instante de la última
--   lectura, que es exactamente hasta dónde llega el dato.
--   (La otra función que toca la tabla, frescura_custom_analytics_pais(), solo usa
--    `pais` y `procesado_at`: sobrevive intacta y NO se toca.)
--
-- 🔒 ALCANCE ("una cosa" = cambiar el eje de fechado, contado entero): la tabla, las
--   dos vistas que leen sus columnas y la RPC que lee la que se va. Ni un objeto más.
--
-- 🔒 LO QUE NO CAMBIA: las 18 columnas de métricas, los ratios 0-1, `crudo NOT NULL`,
--   `pais`, `asin`, `fichero`, `procesado_at`, la RLS de la tabla, su política
--   `inventario_read_authenticated` y su ACL (`authenticated=r`). El ALTER los conserva.
--
-- 🔒 ESCALERA: staging (ensayo → aplicar) → verificación SQL → producción (ensayo →
--   aplicar) → verificación SQL. Advisors después.
--   Se aplica con `.github/workflows/aplicar-migracion.yml`, que ya pone
--   `lock_timeout=5s` por PGOPTIONS y envuelve todo en UNA transacción: no hay que
--   teclear nada suelto antes. (El riesgo real de lock es nulo: 0 filas y nadie
--   escribe todavía.)
--
-- 🔒 IDEMPOTENTE: DROP … IF EXISTS, DROP COLUMN IF EXISTS, DROP CONSTRAINT IF EXISTS,
--   CREATE VIEW tras DROP, REVOKE/GRANT y COMMENT. Aplicarla dos veces = no-op.
--   La excepción es el RENAME (§ más abajo), que se hace condicional a propósito.
-- ============================================================================


-- ── 0) LAS FILAS DEL MODELO VIEJO SE VAN ────────────────────────────────────
-- 🔴 Esto era un `TRUNCATE` comentado, para descomentar a mano al aplicar en staging.
--    YA NO VALE, y el motivo importa: desde el 8-ago-2026 las migraciones se aplican
--    con `.github/workflows/aplicar-migracion.yml`, que corre el fichero de `main`
--    TAL CUAL y publica su sha256 como prueba de qué se aplicó. Un paso manual
--    "descomenta esta línea antes de correr" no existe en ese mundo — y si alguien lo
--    hiciera, el hash dejaría de cuadrar, que es justo lo que el hash impide.
--    Así que el vaciado deja de ser una instrucción para el operador y pasa a ser
--    parte de la migración, que es donde se puede razonar y auditar.
--
-- POR QUÉ UN DELETE INCONDICIONAL ES SEGURO AQUÍ (medido el 7-ago-2026):
--   · PRODUCCIÓN tiene 0 filas → es un no-op, no borra nada.
--   · STAGING tiene ~950 filas del modelo viejo, cuyas "ventanas" eran etiquetas
--     inventadas. No son lecturas de un contador, no se pueden reinterpretar como
--     acumulados, y además ROMPERÍAN la llave nueva: varias ventanas cargadas del
--     mismo fichero comparten `exportado_at`, así que darían duplicado en
--     (pais, leido_at, asin). O se van, o la migración no entra.
--
-- 🔒 Y POR QUÉ NO PUEDE BORRAR DATOS BUENOS EL DÍA DE MAÑANA: va dentro del IF de que
--    TODAVÍA exista `periodo_desde`. En cuanto esta migración corre una vez, esa
--    columna ya no está, así que una segunda pasada no entra aquí y no toca una fila.
--    El borrado solo alcanza a filas del modelo viejo, por construcción.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='demanda_asin'
                AND column_name='periodo_desde') THEN
    DELETE FROM demanda_asin;
    RAISE NOTICE 'Borradas las filas del modelo viejo (ventanas declaradas: no son lecturas de un contador y no se pueden reinterpretar).';
  END IF;
END $$;


-- ── 1) FUERA LAS DOS VISTAS (en orden: la de arriba primero) ────────────────
-- Se recrean más abajo, en esta misma migración, con su revoke+grant detrás.
DROP VIEW IF EXISTS public.v_trackeador_cola;
DROP VIEW IF EXISTS public.v_demanda_asin_ultima;


-- ── 2) GUARDA: no dejar la tabla a medias ───────────────────────────────────
-- `leido_at` pasa a ser NOT NULL. Si quedan filas del modelo viejo sin exportado_at,
-- el ALTER de más abajo falla a mitad del script y deja las vistas caídas. Mejor
-- abortar aquí, antes de tocar nada, y decir exactamente qué hacer. (La casa no
-- elige: o aborta o grita.)
DO $$
DECLARE n_huerfanas bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='demanda_asin'
                AND column_name='exportado_at') THEN
    EXECUTE 'SELECT count(*) FROM demanda_asin WHERE exportado_at IS NULL'
       INTO n_huerfanas;
    IF n_huerfanas > 0 THEN
      RAISE EXCEPTION
        'ABORTA: quedan % filas en demanda_asin sin exportado_at. leido_at va a ser '
        'NOT NULL y no se puede inventar la fecha de una lectura. El paso 0 debería '
        'haberlas borrado ya; si has llegado aquí es que periodo_desde ya no existía '
        'y estas filas son del modelo NUEVO. PARA y mira qué son antes de tocar nada.',
        n_huerfanas;
    END IF;
  END IF;
END $$;


-- ── 3) EL ESQUEMA ───────────────────────────────────────────────────────────
-- `dias` primero: es GENERATED sobre periodo_hasta/periodo_desde y bloquearía su DROP.
ALTER TABLE demanda_asin DROP COLUMN IF EXISTS dias;

ALTER TABLE demanda_asin DROP CONSTRAINT IF EXISTS demanda_asin_unica;
ALTER TABLE demanda_asin DROP CONSTRAINT IF EXISTS demanda_asin_ventana_ok;

ALTER TABLE demanda_asin DROP COLUMN IF EXISTS periodo_desde;
ALTER TABLE demanda_asin DROP COLUMN IF EXISTS periodo_hasta;

-- exportado_at pasa a ser EL EJE del dato: se renombra a lo que de verdad es.
-- Condicional para que la migración sea idempotente (RENAME no tiene IF EXISTS).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='demanda_asin'
                AND column_name='exportado_at') THEN
    ALTER TABLE demanda_asin RENAME COLUMN exportado_at TO leido_at;
  END IF;
END $$;

ALTER TABLE demanda_asin ALTER COLUMN leido_at SET NOT NULL;

-- La llave nueva: una lectura por (país, instante de lectura, ASIN).
-- El procesador recarga por IGUALDAD de (pais, leido_at) → idempotente.
ALTER TABLE demanda_asin
  ADD CONSTRAINT demanda_asin_unica UNIQUE (pais, leido_at, asin);

-- El índice de la ventana ya no significa nada; el de la SERIE sí.
DROP INDEX IF EXISTS idx_demanda_asin_ventana;
CREATE INDEX IF NOT EXISTS idx_demanda_asin_serie
    ON demanda_asin(pais, asin, leido_at DESC);
-- (idx_demanda_asin_asin se queda tal cual.)


-- ── 4) COMMENTS: el cajón cambió, el comentario de la tabla también ─────────
COMMENT ON TABLE demanda_asin IS
  'DEMANDA por ASIN del export Custom Analytics del Seller (Fase 0). PELÍCULA DE '
  'LECTURAS: cada carga apila UNA lectura de un país, fechada con leido_at. Nunca se '
  'borra nada; recargar una lectura ya presente la recierra por IGUALDAD de '
  '(pais, leido_at) → idempotente. El informe es un CONTADOR ACUMULADO desde un punto '
  'de partida fijo y desconocido: las cifras de un periodo NO se leen de una fila, '
  'salen de RESTAR dos lecturas (ver v_demanda_asin_ultima). `pais` lo declara el '
  'selector del workflow: el fichero no lo trae.';

COMMENT ON COLUMN demanda_asin.leido_at IS
  'LA FECHA DEL DATO. Instante de la lectura = wb.properties.created del .xlsx (cuándo '
  'lo generó Amazon). El informe es un CONTADOR ACUMULADO desde un punto de partida '
  'fijo y desconocido: no cubre una ventana declarable. Las cifras de un periodo salen '
  'de RESTAR dos lecturas, nunca de leer una sola. Medido el 7-ago-2026: 1.605 '
  'comparaciones ASIN×métrica entre las lecturas del 30-jul y del 7-ago, CERO bajadas.';


-- ── 5) LA VISTA: aquí vive la resta ─────────────────────────────────────────
-- Una fila por (pais, asin): LA ÚLTIMA lectura, con su delta contra la anterior.
-- 🔒 Los CASE no son adorno: si un acumulado bajó, el delta sale NULL, no negativo.
--    Un número negativo de visitas se pintaría como si fuera un dato; un hueco se ve
--    como lo que es.
-- 🔒 leido_anterior viaja en la vista: un delta sin saber contra qué fecha se mide no
--    significa nada. Es la misma regla que llevaba `dias`.
-- 🔒 Los ASIN que aparecen por primera vez no tienen lectura anterior → sus deltas son
--    NULL (no cero: no se sabe qué hicieron antes). Por eso la SUMA de los deltas de la
--    vista NO tiene por qué coincidir con la resta de los TOTALES: la suma solo cubre
--    los ASIN comunes. Son dos cifras distintas y las dos son verdad (ver §9 del PR).
-- 🔒 inventario_disponible sigue sin salir: NO es stock (la fuente única es salud_fba).
CREATE VIEW public.v_demanda_asin_ultima
WITH (security_invoker = true) AS
WITH ranked AS (
  SELECT d.*,
         row_number() OVER (PARTITION BY pais, asin ORDER BY leido_at DESC) AS rn,
         lag(leido_at)            OVER (PARTITION BY pais, asin ORDER BY leido_at) AS leido_anterior,
         lag(visitas)             OVER (PARTITION BY pais, asin ORDER BY leido_at) AS visitas_ant,
         lag(sesiones)            OVER (PARTITION BY pais, asin ORDER BY leido_at) AS sesiones_ant,
         lag(unidades_pedidas)    OVER (PARTITION BY pais, asin ORDER BY leido_at) AS uds_ant,
         lag(ventas_enviadas_eur) OVER (PARTITION BY pais, asin ORDER BY leido_at) AS ventas_ant
  FROM demanda_asin
)
SELECT pais, asin, nombre_producto, leido_at, leido_anterior,
       -- ACUMULADOS TAL CUAL. No dicen de qué periodo son: son el cuentakilómetros.
       visitas, sesiones, unidades_pedidas, unidades_enviadas,
       ventas_enviadas_eur, facturacion_pedida_eur,
       precio_venta_medio, buybox_ratio, buybox_visiones,
       conversion, reembolsos_ratio, resenas, estrellas,
       -- LO QUE SÍ ES DE UN PERIODO: la resta contra la lectura anterior.
       CASE WHEN visitas             >= visitas_ant  THEN visitas             - visitas_ant  END AS visitas_periodo,
       CASE WHEN sesiones            >= sesiones_ant THEN sesiones            - sesiones_ant END AS sesiones_periodo,
       CASE WHEN unidades_pedidas    >= uds_ant      THEN unidades_pedidas    - uds_ant      END AS uds_periodo,
       CASE WHEN ventas_enviadas_eur >= ventas_ant   THEN ventas_enviadas_eur - ventas_ant   END AS ventas_periodo,
       procesado_at
FROM ranked WHERE rn = 1;

COMMENT ON VIEW public.v_demanda_asin_ultima IS
  'Última lectura por (pais, asin) con su delta contra la anterior. Las columnas SIN '
  'sufijo son ACUMULADOS (contador desde un origen desconocido): no son de ningún '
  'periodo. Las columnas *_periodo son la RESTA leido_anterior→leido_at, y son NULL '
  '—nunca negativas, nunca cero por defecto— si el acumulado bajó o si el ASIN no '
  'tenía lectura anterior.';

-- Nace cerrada otra vez (§4): el DROP se llevó el ACL y renació con el default de
-- Supabase (anon Y authenticated con arwdDxtm). Se revoca a cada rol POR SU NOMBRE y
-- se devuelve el `authenticated=r` que tenía antes de esta migración.
REVOKE ALL ON public.v_demanda_asin_ultima FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_demanda_asin_ultima TO authenticated;


-- ── 6) v_trackeador_cola — SE RECREA IGUAL, salvo lo que obliga el cambio ────
-- 🔴 Esta vista es de OTRA SESIÓN (el trackeador) y NO se reinterpreta aquí. Se copia
--    verbatim de migraciones/2026-07-31_v_trackeador_cola.sql y solo cambia el bloque
--    `dem` y las dos columnas de fecha, que es lo único que el cambio de esquema
--    obliga a tocar. La fórmula del margen, el veredicto, motivo_sin_datos y prioridad
--    van SIN TOCAR una coma.
--
-- ⚠️ LA DECISIÓN QUE NO ES MÍA (leer antes de aprobar):
--    Antes, `fecha_desde`/`fecha_hasta` eran la ventana declarada que sostenía las
--    cifras de demanda ("el RANGO viaja SIEMPRE con el dato: un ratio sin su ventana
--    engaña", §DEMANDA de su migración). En el modelo nuevo esa ventana NO EXISTE:
--      · `visitas` y `sesiones` son ACUMULADOS desde un origen desconocido,
--      · `conversion_pct` y `ratio_oferta_destacada` son ratios DE ese acumulado.
--    Las cuatro columnas cubren [origen desconocido → leido_at]. No hay ningún par de
--    fechas que las etiquete honradamente, porque el origen no se sabe y —§11.1 del
--    encargo— no se rellena con una suposición.
--    Lo que se hace aquí, que es lo ÚNICO que no afirma nada falso:
--      · fecha_hasta = leido_at::date   → hasta dónde llega el dato. Es un hecho.
--      · fecha_desde = NULL             → el origen del contador no se sabe. Un hueco
--        se ve como lo que es (misma regla que los CASE→NULL de la vista de arriba).
--    Poner `leido_anterior` en fecha_desde sería justo la mentira que este encargo
--    viene a matar: diría que un contador acumulado de toda la vida cubre una semana.
--    🔑 Si el trackeador prefiere OTRA cosa (p. ej. exponer visitas_periodo/
--    sesiones_periodo contra leido_anterior→leido_at, que sí sería un par honrado pero
--    CAMBIA las magnitudes que la vista publica), es una línea y se decide con esa
--    sesión. Hoy no cambia nada observable: demanda_asin está a 0 filas, así que las
--    seis columnas de demanda son NULL en las 371 filas, y no consta ningún consumidor
--    de v_trackeador_cola en ninguno de los dos repos (grep del 7-ago-2026).
CREATE VIEW public.v_trackeador_cola
WITH (security_invoker = true) AS
WITH prod AS (
  SELECT asin, nombre, pvd, iva_pct,
         comision_pct_keepa_es, keepa_fba_fee_es, pvd_sospechoso
  FROM v_producto_amazon
),
sal AS (
  SELECT asin, product_name, n_skus, disponible, t7, t30, t90,
         cobertura_dias_t7, sales_rank, your_price_min
  FROM v_salud_asin WHERE marketplace = 'ES'
),
esc AS (
  SELECT asin, bb_precio, caja_mia, bb_es_fba, bb_tiempo_envio, fba_min, fbm_min,
         fba_elegibles, fbm_elegibles, pct_lider_30d, amazon_precio, amazon_disp, diagnostico
  FROM v_escaparate WHERE dominio = 'es'
),
dem AS (
  -- CAMBIO: periodo_desde/periodo_hasta → leido_at. Lo demás, igual.
  SELECT asin, visitas, sesiones, conversion, buybox_ratio, leido_at
  FROM v_demanda_asin_ultima WHERE upper(pais) = 'ES'
),
ana AS (
  SELECT DISTINCT ON (asin) asin, id, accion, precio_implicado, revisar_en
  FROM monitor_analisis WHERE pais = 'ES'
  ORDER BY asin, analisis_ts DESC
),
med AS (
  SELECT analisis_id, count(*) AS n FROM monitor_resultados GROUP BY analisis_id
),
j AS (
  SELECT
    p.asin, 'es'::text AS dominio, p.nombre, p.pvd, p.iva_pct, p.pvd_sospechoso,
    p.keepa_fba_fee_es AS fee, p.comision_pct_keepa_es AS com_pct,
    s.product_name, s.n_skus, s.disponible, s.t7, s.t30, s.t90,
    s.cobertura_dias_t7, s.sales_rank, s.your_price_min,
    e.bb_precio, e.caja_mia, e.bb_es_fba, e.bb_tiempo_envio, e.fba_min, e.fbm_min,
    e.fba_elegibles, e.fbm_elegibles, e.pct_lider_30d, e.amazon_precio, e.amazon_disp, e.diagnostico,
    (e.asin IS NOT NULL) AS tiene_escaparate,
    d.visitas, d.sesiones, d.conversion, d.buybox_ratio, d.leido_at,
    a.accion, a.precio_implicado, a.revisar_en, coalesce(m.n, 0) AS n_mediciones
  FROM prod p
  LEFT JOIN sal s ON s.asin = p.asin
  LEFT JOIN esc e ON e.asin = p.asin
  LEFT JOIN dem d ON d.asin = p.asin
  LEFT JOIN ana a ON a.asin = p.asin
  LEFT JOIN med m ON m.analisis_id = a.id
),
calc AS (
  SELECT *,
    round((your_price_min/(1+iva_pct) - pvd - fee - your_price_min*(com_pct/100)*1.03 - 0.15)
          / nullif(your_price_min,0) * 100, 2) AS margen_hoy,
    round((bb_precio/(1+iva_pct) - pvd - fee - bb_precio*(com_pct/100)*1.03 - 0.15)
          / nullif(bb_precio,0) * 100, 2) AS margen_al_bb,
    round((fba_min/(1+iva_pct) - pvd - fee - fba_min*(com_pct/100)*1.03 - 0.15)
          / nullif(fba_min,0) * 100, 2) AS margen_al_fba_min,
    round((pvd + fee + 0.15) / nullif(1/(1+iva_pct) - com_pct/100*1.03, 0), 4) AS break_even
  FROM j
),
vd AS (
  SELECT *,
    CASE
      WHEN NOT tiene_escaparate THEN 'SIN_DATOS'
      WHEN coalesce(caja_mia, false) THEN 'CAJA_MIA'
      WHEN fba_min IS NULL THEN 'SIN_RIVAL_FBA'
      WHEN margen_al_fba_min IS NULL THEN 'SIN_DATOS'
      WHEN margen_al_fba_min >= 0 AND coalesce(disponible, 0) = 0 THEN 'SIN_DATOS'
      WHEN margen_al_fba_min >= 8 THEN 'ATACABLE_8'
      WHEN margen_al_fba_min >= 0 THEN 'ATACABLE_FLOJO'
      ELSE 'ES_COSTE_NO_PRECIO'
    END AS veredicto,
    (tiene_escaparate AND NOT coalesce(caja_mia, false) AND fba_min IS NOT NULL
       AND your_price_min IS NOT NULL AND abs(your_price_min - fba_min) < 0.005) AS ya_al_minimo_sin_caja
  FROM calc
)
SELECT
  asin, dominio,
  coalesce(product_name, nombre) AS nombre,
  n_skus, disponible, t7, t30, t90, cobertura_dias_t7, sales_rank, your_price_min,
  bb_precio, caja_mia, bb_es_fba, bb_tiempo_envio, fba_min, fbm_min,
  fba_elegibles, fbm_elegibles, pct_lider_30d, amazon_precio, amazon_disp, diagnostico,
  margen_hoy, margen_al_bb, margen_al_fba_min, break_even, pvd_sospechoso,
  visitas, sesiones, conversion AS conversion_pct, buybox_ratio AS ratio_oferta_destacada,
  -- CAMBIO (ver el aviso de arriba): el origen del contador NO se sabe → NULL. El
  -- final del dato sí es un hecho → el instante de la lectura.
  NULL::date AS fecha_desde,
  leido_at::date AS fecha_hasta,
  accion AS ultima_accion, precio_implicado AS precio_decidido, revisar_en, n_mediciones,
  (your_price_min IS NOT NULL AND precio_implicado IS NOT NULL
     AND abs(your_price_min - precio_implicado) < 0.005) AS precio_aplicado,
  veredicto,
  ya_al_minimo_sin_caja,
  CASE
    WHEN veredicto <> 'SIN_DATOS' THEN NULL
    WHEN coalesce(disponible, 0) = 0 THEN 'SIN_STOCK'
    WHEN NOT tiene_escaparate THEN 'SIN_FOTO_KEEPA'
    ELSE 'SIN_COSTE'
  END AS motivo_sin_datos,
  CASE
    WHEN t30 >= 10 AND t7*4.3 < t30*0.6 THEN 1
    WHEN margen_hoy < 8 AND coalesce(t7,0) > 0 THEN 2
    WHEN cobertura_dias_t7 < 21 THEN 3
    ELSE 4
  END AS prioridad
FROM vd;

-- Nace cerrada otra vez (§4): el DROP se llevó el ACL. Mismo trato que tenía.
REVOKE ALL ON public.v_trackeador_cola FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_trackeador_cola TO authenticated;


-- ── 7) frescura_informes(): la fecha del dato de custom_analytics ───────────
-- 🔒 COPIA VERBATIM del cuerpo actual (pg_get_functiondef contra producción, medido el
--    7-ago-2026). NO se reescribe de memoria. Cambia UNA expresión: el fecha_dato de
--    'custom_analytics' pasa de max(periodo_hasta) —columna que ya no existe— a
--    max(leido_at)::date. Se conservan SECURITY DEFINER, el search_path y la firma.
-- 🔒 frescura_informes_sondeo() NO se toca: su cuerpo es `select * from
--    public.frescura_informes();` y hereda el cambio solo.
CREATE OR REPLACE FUNCTION public.frescura_informes()
 RETURNS TABLE(informe text, fecha_dato date, subido_buzon timestamp with time zone, procesado_tabla timestamp with time zone)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public', 'storage'
AS $function$
  select 'salud_fba'::text, (select max(snapshot_date) from salud_fba),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'salud_fba/%'),
    (select max(procesado_en) from salud_fba)
  union all select 'internacional', (select max(fecha_foto) from inventario_internacional),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'internacional/%'),
    (select max(procesado_at) from inventario_internacional)
  union all select 'keepa_escaparate', (select max(fecha_foto) from keepa_escaparate),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'keepa_escaparate/%'),
    (select max(procesado_at) from keepa_escaparate)
  union all select 'all_listings', (select max(fecha_informe)::date from listings_amazon),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'all_listings/%'),
    (select max(procesado_en) from listings_amazon)
  union all select 'ledger', (select max(fecha) from ledger_movimientos),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'ledger/%'),
    (select max(procesado_at) from ledger_movimientos)
  union all select 'paneu_aptos', (select max(snapshot_date) from paneu_aptos),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'paneu_aptos/%'),
    (select max(procesado_en) from paneu_aptos)
  union all select 'transacciones', (select max(fecha_dato_hasta) from informes_subidos where tipo='transacciones'),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'transacciones/%'),
    (select max(procesado_at) from informes_subidos where tipo='transacciones')
  union all select 'custom_analytics', (select max(leido_at)::date from demanda_asin),
    (select max(updated_at) from storage.objects where bucket_id='informes' and name like 'custom_analytics/%'),
    (select max(procesado_at) from demanda_asin);
$function$;

-- Intención escrita: la frescura NO la puede pedir un anónimo (§4). No-op hoy
-- (CREATE OR REPLACE conserva el ACL), pero sobrevive a un futuro DROP+CREATE.
REVOKE EXECUTE ON FUNCTION public.frescura_informes() FROM PUBLIC, anon;


-- ============================================================================
-- VERIFICACIÓN (§3 de CLAUDE.md: la prueba es SQL, nunca el log). Correr TODO
-- esto después de aplicar, en staging y en producción, y pegar la salida en el PR.
-- ----------------------------------------------------------------------------
-- 1) El esquema quedó como toca (no debe salir periodo_desde/periodo_hasta/dias/
--    exportado_at; sí leido_at NOT NULL):
--   select column_name, data_type, is_nullable from information_schema.columns
--    where table_schema='public' and table_name='demanda_asin' order by ordinal_position;
--
-- 2) La llave y los índices:
--   select conname, pg_get_constraintdef(oid) from pg_constraint
--    where conrelid='public.demanda_asin'::regclass;         -- demanda_asin_unica (pais, leido_at, asin)
--   select indexname from pg_indexes
--    where schemaname='public' and tablename='demanda_asin'; -- serie sí, ventana no
--
-- 3) 🔒 SEGURIDAD INTACTA (§9.8 del encargo). RLS activa, la política del Cockpit
--    sigue ahí, y las DOS vistas recuperaron authenticated=r SIN anon:
--   select relname, relkind, relrowsecurity,
--          coalesce(array_to_string(relacl,' | '),'(sin acl)') acl
--     from pg_class where oid in ('public.demanda_asin'::regclass,
--                                 'public.v_demanda_asin_ultima'::regclass,
--                                 'public.v_trackeador_cola'::regclass);
--   select policyname from pg_policies
--    where schemaname='public' and tablename='demanda_asin';  -- inventario_read_authenticated
--
-- 4) 🔴 LA RPC NO SE HA ROTO (esto es lo que tumbaba la pantalla de Elena).
--    Tiene que devolver 8 filas y la de custom_analytics sin reventar:
--   select * from frescura_informes();
--   select * from frescura_informes_sondeo() where informe='custom_analytics';
--
-- 5) Las dos vistas responden (vacías hoy, pero sin error de columna):
--   select count(*) from v_demanda_asin_ultima;   -- 0 hasta la primera carga
--   select count(*) from v_trackeador_cola;       -- 371 (la demanda va a NULL por LEFT JOIN)
--
-- 6) Advisors de Supabase después de aplicar, por si el security_invoker cambió algo.
-- ============================================================================
