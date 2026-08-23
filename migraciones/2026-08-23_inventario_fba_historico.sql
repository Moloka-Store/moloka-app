-- ============================================================================
-- inventario_fba_historico — la PELÍCULA de la foto FBA.            23-ago-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ, y por qué corre prisa. `inventario_fba` es cajón FOTO puro: cada
--   carga BORRA lo que no viene en el fichero y pisa lo que sí (§1.6). Eso está
--   bien —una foto contesta «¿cómo está esto AHORA?»— pero significa que **la
--   lectura de hoy desaparece en cuanto entre la de mañana, y no hay de dónde
--   sacarla**. Sin histórico no hay tendencias, no hay «qué cambió desde ayer»,
--   y sobre todo no hay forma de ver **cuándo salió y cuándo llegó** un envío:
--   `inbound_shipped` es una cifra que se mueve, y una cifra que se mueve sin
--   serie no cuenta una historia.
--   Medido el 23-ago-2026: la foto viva son 354 filas del 23-ago. Esa es la que
--   se pierde si mañana se carga sin esto puesto.
--
-- 🔑 LA MEMORIA HISTÓRICA NO VIVE EN UNA FOTO: VIVE EN UNA PELÍCULA. Es la misma
--   pareja que ya tiene `inventario_internacional` con su
--   `inventario_internacional_historico`, y este fichero está calcado de aquél:
--   append, jamás update destructivo, jamás DELETE.
--
-- LA CLAVE ES (sku, fecha_foto), y no es una copia mecánica de la del inventario:
--   · `sku` porque es la PK de la foto (356 únicos sobre 356 filas medidos el
--     23-ago; el ASIN NO es único — B07GRRYFL1 viene con dos SKU, uno etiquetado
--     y otro commingled).
--   · `fecha_foto` porque es lo que convierte la foto en fotograma. Sin ella no
--     hay serie, y con ella dos lecturas del mismo día se pisan a propósito: una
--     foto por día y SKU.
--
-- 🔴 QUÉ **NO** LLEVA, y es una decisión, no un olvido: **no lleva `crudo`.**
--   El mismo criterio que `inventario_internacional_historico`, y aquí además hay
--   una razón mejor: el `.txt` original **se conserva entero en el Storage**
--   (`informes/inventario_fba/`), así que la despensa común del histórico ya
--   existe fuera de la base — igual que con los CSV de Keepa desde el
--   29-jul-2026. Guardar `crudo` por fotograma sería duplicar en la base (500 MB)
--   lo que ya está en el Storage (1 GB) y por 26 columnas × 354 filas × cada día.
--   ⚠️ LA CONTRAPARTIDA, dicha en alto porque es la misma que la de Keepa:
--   **los .txt de `informes/inventario_fba/` NO SE BORRAN NUNCA.** El día que se
--   borren, el histórico se queda sin las columnas que no se tipan
--   (`per-unit-volume`, `afn-researching-quantity`, `afn-onhand-buyable-quantity`
--   …) y no hay vuelta atrás. El rescate se hace por
--   `inventario_fba_historico.fichero` → `informes/inventario_fba/<fichero>`.
--
-- 🔒 SOLO DDL. Esta migración **no mueve ni una fila**: crea la tabla y la deja
--   cerrada. Quien la llena es el procesador, en su siguiente pasada — que es
--   donde vive la escritura de datos en esta casa. Como el fichero del 23-ago
--   sigue siendo el más reciente del buzón, relanzar `procesar-inventario-fba`
--   en modo `aplicar` después de esto deja la foto de hoy dentro del histórico
--   sin haber inventado nada.
--
-- 🔴 POR QUÉ EL `REVOKE` AUNQUE LA TABLA SEA NUEVA. «Nace cerrado» NO es el
--   estado por defecto: medido el 30-jul-2026 en `pg_default_acl` de las dos
--   bases, toda tabla nueva de `public` nace con `arwdDxtm` para `anon` Y
--   `authenticated`, y un `revoke ... from public` NO lo quita (son grants a un
--   rol, no a `public`). Se revoca a cada rol por su nombre, después del create.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI LA TABLA NO EXISTE YA. Es idempotente
--   (`IF NOT EXISTS`), así que sobre un destino que ya está en el estado final
--   sale verde sin medir nada. El testigo, antes de fiarte:
--       select to_regclass('public.inventario_fba_historico');  -- null = hay algo que probar
--   Medido el 23-ago-2026: `null` en producción.
--
-- ESCALERA: restaurar staging → staging ensayo → aplicar → verificación SQL →
--   producción ensayo → aplicar → verificación SQL. Con `aplicar-migracion.yml`.
--   Y DESPUÉS, la pasada del procesador que la llena.
-- ============================================================================

-- ── 1) LA TABLA (cajón PELÍCULA: se apila, NUNCA se borra) ──────────────────
CREATE TABLE IF NOT EXISTS public.inventario_fba_historico (
    -- La clave: un fotograma por SKU y día
    sku                     text NOT NULL,
    fecha_foto              date NOT NULL,
    -- Identidad (se repite en cada fotograma a propósito: un SKU puede cambiar
    -- de ASIN o de FNSKU, y el histórico tiene que decir qué era ENTONCES)
    fnsku                   text,
    asin                    text,
    product_name            text,
    condition               text,
    -- Stock en la estantería
    warehouse_quantity      integer,
    available               integer,
    unfulfillable_quantity  integer,
    total_reserved_quantity integer,
    total_quantity          integer,
    fc_transfer             integer,
    -- EN TRÁNSITO — la serie que motiva todo esto
    inbound_working         integer,
    inbound_shipped         integer,
    inbound_receiving       integer,
    -- Precio
    your_price              numeric,
    -- El testigo del ámbito del informe
    store                   text,
    -- Trazabilidad: por aquí se rescata el .txt del Storage
    fichero                 text,
    capturado_en            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sku, fecha_foto)
);

-- 🔒 NACE CERRADA. RLS activa y CERO políticas.
ALTER TABLE public.inventario_fba_historico ENABLE ROW LEVEL SECURITY;

-- 🔴 Y el ACL, a cada rol POR SU NOMBRE (ver la cabecera).
REVOKE ALL ON public.inventario_fba_historico FROM PUBLIC, anon, authenticated;

-- Índices. Por fecha_foto porque toda pregunta a una película empieza por
-- «¿entre qué fechas?»; por ASIN porque el puente a la identidad va por ASIN,
-- jamás por SKU (§1.1).
CREATE INDEX IF NOT EXISTS idx_inventario_fba_hist_fecha ON public.inventario_fba_historico(fecha_foto);
CREATE INDEX IF NOT EXISTS idx_inventario_fba_hist_asin  ON public.inventario_fba_historico(asin);

COMMENT ON TABLE public.inventario_fba_historico IS
  'PELÍCULA del informe «Gestión de inventario de Logística de Amazon»: un '
  'fotograma por (sku, fecha_foto). Se APILA, nunca se borra — borrar una línea '
  'de aquí es falsificar el extracto. Su pareja viva es inventario_fba, que es '
  'FOTO y tira la hoja vieja en cada carga. NO guarda `crudo` a propósito: el '
  '.txt original se conserva entero en informes/inventario_fba/, y ésa es la '
  'despensa común. 🔴 CONTRAPARTIDA: esos .txt NO SE BORRAN NUNCA; el rescate se '
  'hace por la columna `fichero`. La llena procesador_inventario_fba.py.';

COMMENT ON COLUMN public.inventario_fba_historico.fecha_foto IS
  'LA FECHA DEL DATO: cuándo se subió el informe al buzón (el fichero no trae '
  'fecha ni dentro ni en el nombre). Es lo que convierte la foto en fotograma. '
  'NO confundir con capturado_en, que es cuándo corrió el robot.';
COMMENT ON COLUMN public.inventario_fba_historico.inbound_shipped IS
  'Unidades ya enviadas a Amazon y todavía no recibidas. La serie de esta columna '
  'es la razón de ser del histórico: una cifra que se mueve sin serie no cuenta '
  'cuándo salió ni cuándo llegó un envío.';
COMMENT ON COLUMN public.inventario_fba_historico.fichero IS
  'El .txt del que salió este fotograma. Es la llave del rescate: '
  'informes/inventario_fba/<fichero> en el Storage. Por eso esos ficheros no se '
  'borran nunca.';
COMMENT ON COLUMN public.inventario_fba_historico.asin IS
  'El ASIN que tenía ESE SKU en ESA fecha. Se repite en cada fotograma a '
  'propósito: un SKU puede cambiar de ficha, y el histórico tiene que decir qué '
  'era entonces, no qué es hoy.';

-- ── 2) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  rls boolean; n_pol int; n_cols int; n_idx int; pk text;
BEGIN
  SELECT relrowsecurity INTO rls
    FROM pg_class WHERE oid = 'public.inventario_fba_historico'::regclass;
  IF NOT rls THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba_historico se ha creado con la RLS APAGADA.';
  END IF;

  SELECT count(*) INTO n_pol
    FROM pg_policy WHERE polrelid = 'public.inventario_fba_historico'::regclass;
  IF n_pol <> 0 THEN
    RAISE EXCEPTION 'ABORTA: tiene % política(s) y tiene que nacer con CERO.', n_pol;
  END IF;

  IF has_table_privilege('anon', 'public.inventario_fba_historico', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `anon` puede hacer SELECT. El revoke no ha hecho su '
                    'trabajo (default privileges de Supabase).';
  END IF;
  IF has_table_privilege('authenticated', 'public.inventario_fba_historico', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` puede hacer SELECT.';
  END IF;

  -- Las 19 columnas que el procesador va a escribir, POR NOMBRE (un count(*)=19
  -- saldría igual con una mal escrita y otra de más).
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'inventario_fba_historico'
     AND column_name IN ('sku','fecha_foto','fnsku','asin','product_name','condition',
                         'warehouse_quantity','available','unfulfillable_quantity',
                         'total_reserved_quantity','total_quantity','fc_transfer',
                         'inbound_working','inbound_shipped','inbound_receiving',
                         'your_price','store','fichero','capturado_en');
  IF n_cols <> 19 THEN
    RAISE EXCEPTION 'ABORTA: de las 19 columnas esperadas existen %. La tabla y '
                    'procesador_inventario_fba.py han dejado de cuadrar.', n_cols;
  END IF;

  -- 🔑 La PK, comprobada de verdad: si fuera solo (sku), la segunda foto pisaría
  --    a la primera y esto dejaría de ser una película sin que nadie se entere.
  SELECT string_agg(a.attname, ',' ORDER BY k.ord) INTO pk
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
   WHERE c.conrelid = 'public.inventario_fba_historico'::regclass AND c.contype = 'p';
  IF pk IS DISTINCT FROM 'sku,fecha_foto' THEN
    RAISE EXCEPTION 'ABORTA: la PK es (%) y tiene que ser (sku,fecha_foto). Sin '
                    'fecha_foto en la clave, cada carga pisaría la anterior y esto '
                    'no sería una película.', pk;
  END IF;

  SELECT count(*) INTO n_idx FROM pg_indexes
   WHERE schemaname = 'public' AND tablename = 'inventario_fba_historico';

  RAISE NOTICE 'Número de control OK: inventario_fba_historico nace CERRADA (RLS on, '
               '0 políticas, anon y authenticated sin SELECT), PK (sku,fecha_foto), '
               '19 columnas y % índices.', n_idx;
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   select to_regclass('public.inventario_fba_historico')          as tabla,
--          (select count(*) from information_schema.columns
--            where table_schema='public'
--              and table_name='inventario_fba_historico')          as n_columnas,
--          relrowsecurity                                          as rls,
--          (select count(*) from pg_policy
--            where polrelid='public.inventario_fba_historico'::regclass) as n_politicas,
--          relacl                                                  as acl,
--          has_table_privilege('anon','public.inventario_fba_historico','SELECT') as anon_lee
--     from pg_class where oid='public.inventario_fba_historico'::regclass;
--   -- → inventario_fba_historico · 19 · true · 0 · (sin anon) · false
--
--   -- Y DESPUÉS de relanzar el procesador en modo aplicar, la foto de hoy salvada:
--   select fecha_foto, count(*) as filas, sum(inbound_shipped) as transito, max(fichero)
--     from public.inventario_fba_historico group by 1 order by 1;
--   -- esperado con 50638020688.txt: 2026-08-23 · 354 · 363
--
--   -- el fotograma tiene que cuadrar con la foto viva, al dígito:
--   select (select count(*) from public.inventario_fba)                          as foto,
--          (select count(*) from public.inventario_fba_historico
--            where fecha_foto=(select max(fecha_foto) from public.inventario_fba)) as fotograma;
--   -- → 354 · 354
-- ============================================================================
