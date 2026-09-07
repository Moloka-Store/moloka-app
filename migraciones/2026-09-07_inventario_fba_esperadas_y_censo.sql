-- ============================================================================
-- inventario_fba — las ESPERADAS, la trazabilidad del tránsito
-- y el CENSO de la cabecera.                                        7-sep-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ, con la fecha y el fichero. El 7-sep-2026 Amazon sirvió el informe
--   «Gestión de inventario de Logística de Amazon» con **24 columnas en vez de
--   26** (`50740020703.txt`). Faltaban `afn-fc-transfer-quantity` y
--   `afn-onhand-buyable-quantity`, que Amazon había insertado meses antes sin
--   anunciarlo, delante de `store` (issue amzn/selling-partner-api-models #5289).
--   La Guarda 1 del procesador abortó por la primera —estaba en el contrato— y la
--   carga diaria del inventario se paró en seco.
--
-- 🔴 LO QUE SE INTENTÓ Y **ESTÁ MEDIDO QUE NO VALE**, escrito aquí para que no
--    haya que volver a descubrirlo:
--      · DEDUCIR el tránsito restando (almacén − vendible − inservible −
--        reservado − investigando): da **0 en las 381 filas** del fichero de 24
--        columnas, porque en esa versión el almacén tampoco trae ya el tránsito.
--        La identidad se cumplía sólo en el fichero que YA traía el dato: una
--        validación circular.
--      · RECONSTRUIRLO desde `inventario_internacional`: acierta en 298 de 313
--        fichas con tránsito, pero **INVENTA 2.107 unidades en 162 fichas que no
--        lo tienen** (medido sobre 2.519 casos ASIN-día, 11 días). Una fuente que
--        inventa más de lo que acierta no es una fuente.
--    🔑 CONCLUSIÓN: **el tránsito entre centros no se deduce. O lo dice un
--       informe, o no se sabe.** Y «no se sabe» se escribe NULL, nunca 0.
--
-- QUÉ HACE ESTA MIGRACIÓN, en tres piezas:
--   1) Dos columnas nuevas en la foto y en la película:
--        · `onhand_buyable`     — el disponible que calcula Amazon. Medido el
--          6-sep sobre las 381 filas: = vendible + tránsito, 381/381, desvío 0
--          (6.692 = 6.437 + 255). Testigo INDEPENDIENTE del criterio de la casa.
--          Llevaba meses llegando en el .txt y no se guardaba en ninguna columna.
--        · `fc_transfer_origen` — 'informe' | 'desconocido'. Sin esto, un tránsito
--          leído y un tránsito que nadie dijo son indistinguibles dentro de la
--          columna, y `fc_transfer` mentiría por omisión.
--   2) El relleno de `fc_transfer_origen` en lo que ya está (ver el punto 2).
--   3) `inventario_fba_cabecera`: el CENSO. Una fila por foto con los encabezados
--      que trajo el informe ese día.
--
-- 🔑 PARA QUÉ EL CENSO, que es la pieza menos obvia y la más importante. El 7-sep
--   `afn-warehouse-quantity` **cambió de significado sin cambiar de nombre**: el
--   6-sep incluía el tránsito entre centros y el 7-sep ya no. Medido:
--        6-sep (26 col): 6.881 = 6.437 + 27 + 134 + 28 + 255 (tránsito DENTRO)
--        7-sep (24 col): 6.635 = 6.453 + 27 + 125 + 30       (tránsito FUERA)
--   Comparar el almacén de una versión con el de la otra da una caída de 246
--   unidades que **no es una caída**. La Guarda 10 (continuidad) necesita saber si
--   las dos cargas son de la misma versión para elegir qué compara: el almacén si
--   lo son, el stock vendible si no. Sin censo, ese cambio de significado es
--   INVISIBLE, y ése es el fondo del fallo del 7-sep.
--
-- 🔴 POR QUÉ EL `REVOKE` AUNQUE LA TABLA SEA NUEVA. «Nace cerrado» NO es el estado
--    por defecto: medido el 30-jul-2026 en `pg_default_acl`, toda tabla nueva de
--    `public` nace con `arwdDxtm` para `anon` Y `authenticated`, y un
--    `revoke ... from public` NO lo quita (son grants a un rol, no a `public`). Se
--    revoca a cada rol por su nombre, después del create.
--
-- 🔒 `ENABLE RLS` sobre las tablas que YA existen NO se lanza aquí: pide
--    AccessExclusiveLock, y ésas ya la tienen puesta desde su migración del
--    23-ago. Sólo la tabla nueva la activa, que es cuando es barato.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI FALTA ALGO. Todo es idempotente
--    (`IF NOT EXISTS`), así que sobre un destino que ya esté en el estado final
--    sale verde sin medir nada. El testigo, antes de fiarte:
--        select to_regclass('public.inventario_fba_cabecera');  -- null = hay algo que probar
--    Medido el 7-sep-2026 en producción: `null`.
--
-- ESCALERA: restaurar staging → staging ensayo → aplicar → verificación SQL →
--   producción ensayo → aplicar → verificación SQL. Con `aplicar-migracion.yml`.
-- ============================================================================

-- ── 1) LAS DOS COLUMNAS NUEVAS, en la foto y en la película ─────────────────
ALTER TABLE public.inventario_fba
  ADD COLUMN IF NOT EXISTS onhand_buyable     integer,
  ADD COLUMN IF NOT EXISTS fc_transfer_origen text;

ALTER TABLE public.inventario_fba_historico
  ADD COLUMN IF NOT EXISTS onhand_buyable     integer,
  ADD COLUMN IF NOT EXISTS fc_transfer_origen text;

COMMENT ON COLUMN public.inventario_fba.onhand_buyable IS
  'El disponible CALCULADO POR AMAZON (afn-onhand-buyable-quantity). Medido el '
  '6-sep-2026: = available + fc_transfer en las 381 filas, desvío 0. Es un TESTIGO '
  'independiente del criterio de la casa, no una fuente: si discrepa de esa suma, '
  'el procesador lo GRITA con las dos cifras. NULL cuando el informe no trae la '
  'columna — que es lo que pasó el 7-sep-2026.';

COMMENT ON COLUMN public.inventario_fba.fc_transfer_origen IS
  'De dónde sale fc_transfer en esta fila: ''informe'' (lo dijo Amazon en el .txt '
  'de ese día) o ''desconocido'' (el informe no traía la columna, y entonces '
  'fc_transfer es NULL). 🔴 NULL en fc_transfer NO ES CERO: el tránsito entre '
  'centros no se deduce ni se reconstruye — se midió que restar da 0 y que '
  'reconstruir desde el internacional inventa 2.107 uds. Quien lea esta tabla '
  'tiene que tratar el NULL como desconocido, jamás como 0.';

COMMENT ON COLUMN public.inventario_fba_historico.onhand_buyable IS
  'Igual que en inventario_fba: el disponible que calculaba Amazon ESE día.';
COMMENT ON COLUMN public.inventario_fba_historico.fc_transfer_origen IS
  'De dónde salía fc_transfer en ESE fotograma: ''informe'' o ''desconocido''. Es '
  'lo que permite leer la serie sin confundir «cero tránsito» con «aquel día el '
  'informe no lo dijo».';

-- ── 2) EL RELLENO DE LO QUE YA ESTÁ ─────────────────────────────────────────
-- 🔴 ESTA MIGRACIÓN SÍ MUEVE FILAS, y es una excepción con motivo. Si estas
--    columnas se quedaran a NULL en lo ya cargado, el NULL de `fc_transfer_origen`
--    significaría DOS cosas a la vez —«fila anterior a la columna» y «origen
--    desconocido»— y eso es exactamente el fallo que la columna viene a evitar.
-- 🔑 Y el valor no se conjetura: hasta hoy **la única fuente que ha existido es el
--    informe**. Toda fila que ya tiene un `fc_transfer` no nulo lo tiene porque el
--    .txt lo traía. Por eso el WHERE mira `fc_transfer IS NOT NULL` y no rellena
--    nada más: donde no hay cifra, no se inventa un origen.
UPDATE public.inventario_fba
   SET fc_transfer_origen = 'informe'
 WHERE fc_transfer IS NOT NULL AND fc_transfer_origen IS NULL;

UPDATE public.inventario_fba_historico
   SET fc_transfer_origen = 'informe'
 WHERE fc_transfer IS NOT NULL AND fc_transfer_origen IS NULL;

-- ── 3) EL CENSO DE LA CABECERA (cajón PELÍCULA: se apila, nunca se borra) ────
CREATE TABLE IF NOT EXISTS public.inventario_fba_cabecera (
    -- Una fila por FOTO. Lo que se censa es el informe, no el inventario.
    fecha_foto    date NOT NULL,
    fichero       text,
    n_encabezados integer NOT NULL,
    encabezados   text[] NOT NULL,
    -- 🔑 Bajo qué regla se leyó el disponible ese día: 'transito_aparte' (el
    --    tránsito se suma al vendible), 'transito_dentro' (ya lo lleva dentro) o
    --    'transito_desconocido' (el informe no lo dice). Sin esto la serie del
    --    histórico no se puede releer: dos fotogramas con las mismas columnas
    --    significan cosas distintas a un lado y otro del cambio de Amazon.
    modelo_disponible text,
    capturado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fecha_foto)
);

-- 🔒 NACE CERRADA. RLS activa y CERO políticas.
ALTER TABLE public.inventario_fba_cabecera ENABLE ROW LEVEL SECURITY;

-- 🔴 Y el ACL, a cada rol POR SU NOMBRE (ver la cabecera).
REVOKE ALL ON public.inventario_fba_cabecera FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.inventario_fba_cabecera IS
  'CENSO de la cabecera del informe FBA: qué encabezados trajo el .txt cada día. '
  'Contesta dos preguntas que ninguna otra tabla contesta: «¿desde cuándo llega '
  'esta columna?» y «¿es esta carga de la misma versión que la anterior?». La '
  'segunda la usa la Guarda 10 para decidir si puede comparar el almacén — el '
  '7-sep-2026 afn-warehouse-quantity cambió de significado sin cambiar de nombre, '
  'y sin este censo eso es invisible. La llena procesador_inventario_fba.py.';

COMMENT ON COLUMN public.inventario_fba_cabecera.encabezados IS
  'Los encabezados EXACTOS del .txt de ese día, en el orden en que venían. El '
  'orden se guarda aunque el procesador lea por nombre y no por posición: cuando '
  'Amazon mueve una columna, esto es lo único que lo dice.';

-- ── 4) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  rls boolean; n_pol int; n_cols int; pk text;
  sin_origen_foto int; sin_origen_hist int;
BEGIN
  -- 4.1 · Las columnas nuevas existen en las DOS tablas, por nombre.
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public'
     AND table_name IN ('inventario_fba', 'inventario_fba_historico')
     AND column_name IN ('onhand_buyable', 'fc_transfer_origen');
  IF n_cols <> 4 THEN
    RAISE EXCEPTION 'ABORTA: se esperaban 4 columnas nuevas (2 en cada tabla) y hay %.', n_cols;
  END IF;

  -- 4.2 · El relleno no ha dejado ninguna fila con cifra y sin origen. Si quedara
  --       una, el NULL de la columna volvería a significar dos cosas.
  SELECT count(*) INTO sin_origen_foto FROM public.inventario_fba
   WHERE fc_transfer IS NOT NULL AND fc_transfer_origen IS NULL;
  SELECT count(*) INTO sin_origen_hist FROM public.inventario_fba_historico
   WHERE fc_transfer IS NOT NULL AND fc_transfer_origen IS NULL;
  IF sin_origen_foto <> 0 OR sin_origen_hist <> 0 THEN
    RAISE EXCEPTION 'ABORTA: quedan filas con fc_transfer y sin origen (foto %, historico %).',
                    sin_origen_foto, sin_origen_hist;
  END IF;

  -- 4.3 · El censo nace CERRADO.
  SELECT relrowsecurity INTO rls
    FROM pg_class WHERE oid = 'public.inventario_fba_cabecera'::regclass;
  IF NOT rls THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba_cabecera se ha creado con la RLS APAGADA.';
  END IF;

  SELECT count(*) INTO n_pol
    FROM pg_policy WHERE polrelid = 'public.inventario_fba_cabecera'::regclass;
  IF n_pol <> 0 THEN
    RAISE EXCEPTION 'ABORTA: el censo tiene % política(s) y tiene que nacer con CERO.', n_pol;
  END IF;

  IF has_table_privilege('anon', 'public.inventario_fba_cabecera', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `anon` puede hacer SELECT sobre el censo. El revoke no ha '
                    'hecho su trabajo (default privileges de Supabase).';
  END IF;
  IF has_table_privilege('authenticated', 'public.inventario_fba_cabecera', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` puede hacer SELECT sobre el censo.';
  END IF;

  -- 4.4 · La PK del censo es la fecha, no un serial: una foto, un censo. Con otra
  --       clave, dos cargas del mismo día dejarían dos versiones y la Guarda 10
  --       no sabría cuál es «la anterior».
  SELECT string_agg(a.attname, ',' ORDER BY k.ord) INTO pk
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
   WHERE c.conrelid = 'public.inventario_fba_cabecera'::regclass AND c.contype = 'p';
  IF pk IS DISTINCT FROM 'fecha_foto' THEN
    RAISE EXCEPTION 'ABORTA: la PK del censo es (%) y tiene que ser (fecha_foto).', pk;
  END IF;

  RAISE NOTICE 'Numero de control OK: 4 columnas nuevas puestas, 0 filas con cifra y '
               'sin origen, y inventario_fba_cabecera nace CERRADA (RLS on, 0 '
               'politicas, anon y authenticated sin SELECT), PK (fecha_foto).';
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   -- las columnas, y que el relleno ha hecho su trabajo:
--   select count(*)                                              as filas,
--          count(onhand_buyable)                                 as con_onhand,
--          count(*) filter (where fc_transfer_origen='informe')   as origen_informe,
--          count(*) filter (where fc_transfer_origen is null)     as sin_origen
--     from public.inventario_fba;
--   -- esperado el 7-sep-2026 (foto del 6-sep, aún sin recargar):
--   --   381 · 0 (la columna es nueva y aún no se ha cargado nada) · 381 · 0
--
--   select count(*) as fotogramas,
--          count(*) filter (where fc_transfer_origen='informe') as origen_informe
--     from public.inventario_fba_historico;
--   -- esperado: 4.042 · 4.042
--
--   -- el censo nace cerrado y VACÍO (lo llena el procesador, no la migración):
--   select to_regclass('public.inventario_fba_cabecera')          as tabla,
--          relrowsecurity                                         as rls,
--          (select count(*) from pg_policy
--            where polrelid='public.inventario_fba_cabecera'::regclass) as n_politicas,
--          has_table_privilege('anon','public.inventario_fba_cabecera','SELECT') as anon_lee,
--          (select count(*) from public.inventario_fba_cabecera)  as filas
--     from pg_class where oid='public.inventario_fba_cabecera'::regclass;
--   -- → inventario_fba_cabecera · true · 0 · false · 0
--
--   -- Y DESPUÉS de la primera pasada del procesador, el censo del día:
--   select fecha_foto, n_encabezados, fichero from public.inventario_fba_cabecera
--    order by fecha_foto desc limit 3;
-- ============================================================================
