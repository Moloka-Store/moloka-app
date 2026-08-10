-- ============================================================================
-- LA SECUENCIA DE monitor_doctrina VA POR DETRÁS DE SUS PROPIAS FILAS
-- ----------------------------------------------------------------------------
-- QUÉ PASA. `monitor_doctrina.id` es un `serial` clásico (default
-- `nextval('monitor_doctrina_id_seq')`, secuencia ligada por
-- `pg_get_serial_sequence`). Y el contador de esa secuencia se ha quedado ATRÁS
-- respecto a los ids que ya hay en la tabla. Medido en PRODUCCIÓN el 10-ago-2026:
--
--     last_value = 100  ·  is_called = true  ·  max(id) = 112  ·  111 filas
--
-- O sea: el próximo `nextval` devolverá 101, y 101 YA EXISTE. Son **12 colisiones
-- esperando** (los ids 101…112), cada una un `duplicate key value violates unique
-- constraint` en el momento en que el trackeador intente escribir.
--
-- 🔴 Y ESTO EMPEORA SOLO. El trackeador escribe en `monitor_doctrina` a diario. El
--    9-ago-2026 la misma medición daba `max(id) = 108`, o sea 8 colisiones; hoy son
--    12. Cada fila nueva que entra por una vía que NO usa la secuencia añade una
--    colisión más al montón. No es una bomba que se pueda dejar para el mes que
--    viene: es una bomba que engorda.
--
-- ⚠️ POR QUÉ SE DESINCRONIZÓ, dicho honestamente: NO SE SABE. Una secuencia se
--    queda atrás cuando se insertan filas con el `id` puesto a mano (un `INSERT ...
--    (id, …) VALUES (112, …)`, una carga masiva, una restauración parcial), porque
--    eso no consume `nextval`. Cuál de las tres fue aquí no consta en ninguna
--    parte, y esta migración no lo investiga: arregla el contador. Si vuelve a
--    pasar, entonces habrá que mirar QUIÉN escribe con id explícito.
--
-- ----------------------------------------------------------------------------
-- 🔴 POR QUÉ `ALTER SEQUENCE … RESTART WITH` Y NO `setval()`. ESTO NO ES ESTILO.
--
--   `aplicar-migracion.yml` corre el fichero envuelto en UNA transacción, y en modo
--   `ensayo` lo termina con ROLLBACK para poder decir «no se ha escrito nada».
--   Pues bien, MEDIDO en staging el 10-ago-2026, dentro de un bloque que aborta:
--
--       setval('…', 500, true)                    → last_value = 500  SOBREVIVIÓ
--       ALTER SEQUENCE … RESTART WITH 700         → last_value = 500  se deshizo
--
--   `setval()` NO es transaccional. Una migración escrita con `setval` habría
--   ESCRITO DE VERDAD en producción durante el ensayo, y el veredicto del workflow
--   habría dicho «ENSAYO OK … NO se ha escrito nada» mintiendo. Es exactamente la
--   familia de fallos de §1.4: no da información incompleta, da información FALSA.
--   `ALTER SEQUENCE … RESTART` sí se deshace con la transacción, así que el ensayo
--   de esta migración significa lo que dice.
--
-- 🔒 `RESTART WITH n` deja `is_called = false`, así que el PRÓXIMO `nextval`
--    devuelve exactamente `n`. Con `setval(n, true)` habría devuelto `n+1`. Por eso
--    el objetivo que se calcula abajo es «el próximo id que quiero», no «el último
--    usado».
--
-- 🔒 NUNCA VA HACIA ATRÁS, y por eso es idempotente. El objetivo es
--    `GREATEST(max(id) + 1, el próximo que ya iba a salir)`: si alguien la aplica
--    dos veces, la segunda no mueve nada; y si entre medias han entrado ids más
--    altos, se ajusta a ellos. Bajar el contador crearía colisiones nuevas, que es
--    justo lo que se viene a arreglar.
--
-- 🔒 SE APLICA A LAS DOS BASES CON EL MISMO TEXTO. El número no está escrito en el
--    fichero: se calcula en el momento contra la tabla que haya delante. Producción
--    tiene max(id)=112 y staging 106 (medido hoy), así que un número fijo habría
--    servido para una y roto la otra.
-- ============================================================================

DO $$
DECLARE
  v_max      bigint;
  v_last     bigint;
  v_called   boolean;
  v_proximo  bigint;   -- el próximo id que la secuencia daría HOY
  v_objetivo bigint;   -- el próximo id que queremos que dé
BEGIN
  SELECT coalesce(max(id), 0) INTO v_max FROM public.monitor_doctrina;
  SELECT last_value, is_called INTO v_last, v_called FROM public.monitor_doctrina_id_seq;

  v_proximo  := v_last + CASE WHEN v_called THEN 1 ELSE 0 END;
  v_objetivo := GREATEST(v_max + 1, v_proximo, 1);

  RAISE NOTICE 'monitor_doctrina: max(id)=%, secuencia daría %, se deja en %.',
               v_max, v_proximo, v_objetivo;

  IF v_objetivo = v_proximo THEN
    RAISE NOTICE 'La secuencia ya iba por delante: no se toca (idempotente).';
  ELSE
    RAISE NOTICE 'Se adelanta la secuencia % posiciones: había % colisiones esperando.',
                 v_objetivo - v_proximo, GREATEST(v_max - v_last, 0);
    EXECUTE format('ALTER SEQUENCE public.monitor_doctrina_id_seq RESTART WITH %s',
                   v_objetivo);
  END IF;
END $$;


-- ============================================================================
-- VERIFICACIÓN (§3 de CLAUDE.md: la prueba es SQL, nunca el log). Correr esto
-- después de aplicar, en staging y en producción, y pegar la salida en el PR.
-- ----------------------------------------------------------------------------
-- 1) Cero colisiones esperando: no puede quedar ningún id >= el próximo valor.
--    Tiene que dar 0.
--   WITH s AS (SELECT last_value, is_called FROM public.monitor_doctrina_id_seq)
--   SELECT count(*) AS colisiones_pendientes
--     FROM public.monitor_doctrina m, s
--    WHERE m.id >= s.last_value + CASE WHEN s.is_called THEN 1 ELSE 0 END;
--
-- 2) El próximo id sale por encima del máximo actual:
--   WITH s AS (SELECT last_value, is_called FROM public.monitor_doctrina_id_seq)
--   SELECT (SELECT max(id) FROM public.monitor_doctrina)                   AS max_id,
--          s.last_value, s.is_called,
--          s.last_value + CASE WHEN s.is_called THEN 1 ELSE 0 END          AS proximo
--     FROM s;
--   -- producción: max_id=112 → proximo=113
--   -- staging:    max_id=106 → proximo=107
--
-- 3) 🔒 LA PRUEBA QUE DE VERDAD CIERRA ESTO no es leer el contador: es GASTARLO.
--    Insertar una fila de verdad y ver que no revienta. Se hace a mano DESPUÉS de
--    aplicar, y se borra lo insertado — es una tabla de monitorización, no un libro
--    de asientos:
--   INSERT INTO public.monitor_doctrina (…) VALUES (…) RETURNING id;   -- debe dar 113
--   DELETE FROM public.monitor_doctrina WHERE id = 113;
--    ⚠️ Ojo: ese INSERT/DELETE NO va en esta migración. Meterlo aquí lo haría correr
--    también en el ENSAYO, y aunque el DELETE lo limpiara, el `nextval` que gasta NO
--    es transaccional (misma razón que el setval de arriba): el ensayo dejaría el
--    contador movido. Se hace aparte y a conciencia.
-- ============================================================================
