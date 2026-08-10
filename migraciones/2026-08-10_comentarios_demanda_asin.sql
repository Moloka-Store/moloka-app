-- ============================================================================
-- DOS COMENTARIOS DE `demanda_asin`: uno que FALTABA y otro que HA DEJADO DE SER
-- CIERTO
-- ----------------------------------------------------------------------------
-- Los comentarios de columna son lo que lee quien se sienta a trabajar con la tabla
-- SIN haber leído el CLAUDE.md ni este fichero. Por eso valen, y por eso uno que
-- miente es peor que ninguno.
--
-- 🔴 `COMMENT ON` REEMPLAZA, NO AÑADE. No hay `COMMENT ... APPEND`. Así que el texto
--    de abajo lleva el comentario viejo ÍNTEGRO más lo nuevo. Escribir solo el
--    párrafo nuevo habría BORRADO el aviso de que el ratio es 0-1, que es justo lo
--    que evita el error del factor 100. Los dos textos viejos se sacaron de la base
--    con `col_description()` el 10-ago-2026 y se pegan literales, no de memoria.
--
-- 🔒 UN `COMMENT` NO CREA NI RECREA NINGÚN OBJETO, así que aquí NO hay bloque de
--    privilegios: no hay ACL que renazca con el default de Supabase (§4 de
--    CLAUDE.md). Se dice para que nadie eche de menos el `revoke`/`grant`.
--
-- ⚠️ SOBRE LA ESCALERA: esta migración se ensaya en staging, pero NO hace falta
--    restaurar staging antes. La regla existe porque un ensayo solo demuestra algo
--    si las dos bases se parecen — y un `COMMENT` no tiene comportamiento que
--    dependa del estado de la base: escribe un texto fijo en el catálogo. Restaurar
--    no probaría nada que el ensayo no pruebe ya. Se dice el motivo; no se salta la
--    regla en silencio.
-- ============================================================================


-- ── 1) buybox_ratio: HAY DOS MEDIAS Y NO SON LA MISMA ───────────────────────
-- Sale de medir el 10-ago-2026 sobre `v_demanda_asin_ultima` con las cuatro lecturas
-- ya cargadas. Las dos son correctas y contestan preguntas distintas; el problema es
-- que dos pantallas enseñen una cada una sin decir cuál, y las dos tengan razón.
COMMENT ON COLUMN demanda_asin.buybox_ratio IS
  'LA BUY BOX. RATIO 0-1 (visiones de ofertas destacadas/visitas). "Ratio de oferta '
  'destacada" en el fichero. Se guarda tal cual (0-1). La buy box se MIDE aquí, se '
  'trabaja en el trackeador (otro proyecto). '
  '🔴 HAY DOS MEDIAS Y NO SON LA MISMA. La PONDERADA por tráfico '
  '(sum(buybox_visiones)/sum(visitas)) y la MEDIA SIMPLE por ASIN (avg(buybox_ratio)). '
  'Medido el 10-ago-2026 sobre v_demanda_asin_ultima: ponderada ES 25,8% · IT 8,4% · '
  'FR 4,1%; simple ES 32,2% · IT 10,7% · FR 4,5%. '
  'LA DE NEGOCIO ES LA PONDERADA — es el 26% de ES que circula en las notas. La simple '
  'sale más alta porque pesa igual un ASIN con 3 visitas que uno con 30.000. '
  'Si dos pantallas enseñan cifras distintas de buy box, es esto, y las dos tienen '
  'razón: que cada una diga CUÁL usa.';


-- ── 2) leido_at: el punto de partida NO es fijo ─────────────────────────────
-- 🔴 EL COMENTARIO VIEJO AFIRMABA ALGO QUE HOY SABEMOS FALSO. Decía, literal:
--       "El informe es un CONTADOR ACUMULADO desde un punto de partida fijo y
--        desconocido"
--    La captura del panel del Seller (10-ago-2026) lo desmiente: el periodo se ELIGE.
--    Viene por defecto en «Desde el inicio de año» —1-ene, inicio fijo, fin móvil, que
--    es lo que hace que el modelo funcione— pero hay un «Custom date range» con tope
--    de 92 días. El punto de partida es el que tenga puesto el selector.
--    No es un matiz: es la premisa que se cayó con el `metric-data (14)`, un export de
--    rango corto que traía 246 ASIN contra los 321 de la lectura anterior y cifras al
--    ~1%.
-- 🔒 LO DEMÁS DEL COMENTARIO SE QUEDA, y una parte gana sentido: las 1.605
--    comparaciones con CERO bajadas del 7-ago siguen siendo verdad, y ahora se sabe
--    POR QUÉ — las dos lecturas se exportaron con el mismo inicio.
COMMENT ON COLUMN demanda_asin.leido_at IS
  'LA FECHA DEL DATO. Instante de la lectura = wb.properties.created del .xlsx '
  '(cuándo lo generó Amazon). El informe es un CONTADOR ACUMULADO: las cifras de un '
  'periodo salen de RESTAR dos lecturas, nunca de leer una sola. '
  '🔴 PERO EL PUNTO DE PARTIDA NO ES FIJO: es el que tenga puesto el selector de '
  'periodo del panel del Seller — «Desde el inicio de año» por defecto (1-ene, inicio '
  'fijo, fin móvil), pero cambiable a un rango personalizado de hasta 92 días. '
  'SOLO SON COMPARABLES ENTRE SÍ LAS LECTURAS EXPORTADAS CON EL MISMO PERIODO. La '
  'regla operativa (exportar SIEMPRE con «Desde el inicio de año») está en §2 de '
  'CLAUDE.md, y la guarda 6.14 del procesador ABORTA si una lectura retrocede, que es '
  'la señal de que traía otro inicio. Caso real del 10-ago-2026: un export de rango '
  'corto traía 246 ASIN contra 321 y cifras al ~1%. '
  '⚠️ Y `leido_at` es CUÁNDO SE EXPORTÓ, no la fecha de los datos: Amazon publica con '
  'días de retraso (NUEVE el 10-ago-2026, que avisaba "datos disponibles hasta el '
  '1/8/2026"). Así que el fin de la ventana no se sabe ni siquiera siguiendo la regla, '
  'y la resta entre dos lecturas mide la CADENCIA DE AMAZON, no el mercado: sirve para '
  'tendencia y para comparar ASIN, no para decir "en agosto se vendieron X". '
  'Medido el 7-ago-2026: 1.605 comparaciones ASIN×métrica entre las lecturas del '
  '30-jul y del 7-ago, CERO bajadas — las dos exportadas con el mismo inicio.';


-- ============================================================================
-- VERIFICACIÓN (§3 de CLAUDE.md: la prueba es SQL, nunca el log).
-- ----------------------------------------------------------------------------
-- 1) Los dos comentarios están y dicen lo que tienen que decir:
--   SELECT a.attname,
--          col_description(a.attrelid, a.attnum) AS comentario
--     FROM pg_attribute a
--    WHERE a.attrelid = 'public.demanda_asin'::regclass
--      AND a.attname IN ('buybox_ratio','leido_at')
--    ORDER BY a.attname;
--
-- 2) 🔒 LO QUE DE VERDAD HAY QUE COMPROBAR EN buybox_ratio: que NO se ha perdido el
--    aviso del 0-1 al reemplazar. Tiene que dar `true` en las dos:
--   SELECT col_description(a.attrelid, a.attnum) LIKE '%RATIO 0-1%'        AS conserva_0_1,
--          col_description(a.attrelid, a.attnum) LIKE '%PONDERADA%'        AS trae_lo_nuevo
--     FROM pg_attribute a
--    WHERE a.attrelid='public.demanda_asin'::regclass AND a.attname='buybox_ratio';
--
-- 3) Y que en leido_at ya no queda rastro de la afirmación falsa. Tiene que dar
--    `false` la primera y `true` la segunda:
--   SELECT col_description(a.attrelid, a.attnum) LIKE '%partida fijo%'     AS queda_lo_falso,
--          col_description(a.attrelid, a.attnum) LIKE '%NO ES FIJO%'       AS trae_lo_corregido
--     FROM pg_attribute a
--    WHERE a.attrelid='public.demanda_asin'::regclass AND a.attname='leido_at';
--
-- 4) Y las siete huellas del esquema NO deben moverse: un COMMENT no cambia la forma
--    de la base. Se calculan con sql/huellas_esquema.sql y sql/huella_acl.sql.
--    Al 10-ago-2026 producción está en: columnas 8be441ff · indices 413cb344 ·
--    restricciones 4380d0c4 · funciones 4248c7d4 · politicas b9f1aa5e ·
--    def_vistas 2e4c0764 · ACL 518f4666.
--    ⚠️ Ojo: `def_vistas` es el md5 del SQL de las VISTAS, no de los comentarios, así
--    que tampoco se mueve por esto. Si alguna cambia, esta migración ha hecho más de
--    lo que dice.
-- ============================================================================
