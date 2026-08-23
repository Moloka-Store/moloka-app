-- ============================================================================
-- inventario_fba — la tabla del informe «Gestión de inventario de Logística de
-- Amazon», y su buzón autorizado.                              23-ago-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ. `salud_fba` está roto por parte de Amazon (sirve ficheros truncados y
--   los para su Guarda 9) y lleva congelado desde el 16-ago. Casi todo lo suyo lo
--   cubren ya otras tablas MENOS UNA COSA: las unidades EN TRÁNSITO
--   (`inbound_shipped`). Sin ese dato la app manda a preparar un envío que ya
--   salió. Medido el 23-ago-2026 en el fichero real (50632020686.txt): 363
--   unidades de camino en 17 ASIN, contra las 143 que era lo último que sabía
--   `salud_fba` (`select sum(inbound_shipped) from salud_fba` → 143, snapshot del
--   16-ago).
--
-- 🔒 ESTO SÓLO AÑADE. No toca `salud_fba`, ni su procesador, ni ninguna tabla
--   existente, ni ninguna vista. Nadie lee `inventario_fba` todavía, así que no
--   roza la operativa de Elena: la tabla nace vacía y cerrada, y hasta que algo la
--   consulte no cambia ni una pantalla.
--
-- QUÉ HACE, en tres cosas:
--   1) CREA la tabla `inventario_fba`, CERRADA (RLS activa, 0 políticas, y el
--      revoke a cada rol POR SU NOMBRE — ver el bloque de abajo).
--   2) Sus índices.
--   3) AÑADE 'inventario_fba' a `public.moloka_buzones_fase0()`, que es lo que
--      autoriza a subir el informe al buzón desde la app.
--
-- 🔴 POR QUÉ EL `REVOKE` VA AUNQUE LA TABLA SEA NUEVA, Y NO ES DECORACIÓN.
--   «Nace cerrado» NO es el estado por defecto en esta base. Medido el 30-jul-2026
--   en `pg_default_acl` de las DOS bases: en `public`, toda tabla nueva nace con
--   **`arwdDxtm` concedido a `anon` Y a `authenticated`** por los DEFAULT
--   PRIVILEGES de Supabase. Un `revoke ... from public` NO los quita (son grants
--   explícitos a un rol, no a `public`), así que hay que revocar a cada rol por su
--   nombre. Y el `revoke` va DESPUÉS del `create`, en esta misma migración.
--   ⚠️ RLS activa sin políticas ya deja la tabla ilegible para `anon`, pero las dos
--   cosas se ponen igual: son dos cierres distintos y el día que alguien añada una
--   política, el ACL es lo único que queda debajo.
--
-- 🔒 CÓMO SE VERIFICA EL ACL, que no es aquí. Un test de ACL en STAGING no prueba
--   nada sobre producción: staging viene de un dump con `--no-privileges` y sus ACL
--   son los de Supabase por defecto. La ÚNICA excepción es justo el objeto que crea
--   la migración que se está ensayando —éste—, porque lleva su `revoke` dentro. Aun
--   así, el ACL se cuenta EN PRODUCCIÓN después de aplicar (bloque de verificación
--   del final).
--
-- 🔴 `CREATE OR REPLACE` PARA LA FUNCIÓN DEL BUZÓN, JAMÁS `DROP`. Las CUATRO
--   políticas `buzones_v2_*` de `storage.objects` cuelgan de ella: un DROP ... CASCADE
--   se las llevaría por delante. Y la guarda del final compara el recuento de
--   políticas contra el de ANTES (paso 1b), NO contra un 4 fijo: `backup-bd.yml`
--   vuelca con `--schema=public`, así que esas políticas NO están en la copia y
--   `restaurar-staging.yml` no las repone — un `<> 4` daría ROJO en staging por el
--   alcance del backup, no por la migración. El invariante real de un REPLACE es
--   «no se llevó ninguna por delante», y eso es cierto valgan 4 o valga otra cosa.
--
-- ⚠️ EL ENSAYO DE ESTA MIGRACIÓN SÓLO PRUEBA ALGO SI LA TABLA **NO** EXISTE YA EN
--   staging. Es idempotente (IF NOT EXISTS / OR REPLACE), y un ensayo sobre un
--   destino que ya está en el estado final sale verde sin haber medido nada. Mira en
--   qué estado está staging antes de fiarte del verde:
--       select to_regclass('public.inventario_fba');   -- null = hay algo que probar
--
-- ESCALERA: restaurar staging → staging ensayo → staging aplicar → verificación SQL
--   → producción ensayo → producción aplicar → verificación SQL. Con
--   `aplicar-migracion.yml`.
-- ============================================================================

-- ── 1) GUARDA: la función del buzón tiene que ser la que creemos ────────────
-- Si alguien la cambió por otro camino, PARA antes de sobrescribirla: reemplazar a
-- ciegas una función que no es la que leímos es cómo se pierde trabajo ajeno.
DO $$
DECLARE n_carpetas int; es_inmutable boolean; sp text[];
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_proc
                  WHERE proname = 'moloka_buzones_fase0'
                    AND pronamespace = 'public'::regnamespace) THEN
    RAISE EXCEPTION 'ABORTA: public.moloka_buzones_fase0() no existe en esta base. '
                    'Aquí no se crea de cero: PARA y mira qué base es.';
  END IF;

  SELECT array_length(public.moloka_buzones_fase0(), 1) INTO n_carpetas;
  SELECT provolatile = 'i', proconfig INTO es_inmutable, sp
    FROM pg_proc WHERE proname = 'moloka_buzones_fase0'
                   AND pronamespace = 'public'::regnamespace;

  IF n_carpetas <> 8 THEN
    RAISE EXCEPTION 'ABORTA: esperaba 8 carpetas antes del cambio y hay %. La función '
                    'no es la que se leyó el 23-ago. PARA y compara.', n_carpetas;
  END IF;
  IF NOT es_inmutable THEN
    RAISE EXCEPTION 'ABORTA: la función ya no es IMMUTABLE. PARA: algo la cambió.';
  END IF;
  IF sp IS DISTINCT FROM ARRAY['search_path=""'] THEN
    RAISE EXCEPTION 'ABORTA: el search_path de la función no es el esperado (es %). PARA.', sp;
  END IF;

  RAISE NOTICE 'Guarda 1 OK: 8 carpetas, IMMUTABLE, search_path a vacío.';
END $$;

-- ── 1b) FOTO DE LAS POLÍTICAS **ANTES** ─────────────────────────────────────
-- Se guarda el RECUENTO PREVIO, no un número fijo (ver la cabecera).
CREATE TEMP TABLE _control_buzones AS
SELECT count(*)::int AS n_politicas_antes
  FROM pg_policy
 WHERE polrelid = 'storage.objects'::regclass
   AND polname LIKE 'buzones_v2%';

DO $$
DECLARE n int;
BEGIN
  SELECT n_politicas_antes INTO n FROM _control_buzones;
  RAISE NOTICE 'Políticas buzones_v2_* ANTES del cambio: %', n;
END $$;

-- ── 2) LA TABLA ─────────────────────────────────────────────────────────────
-- Cajón FOTO: cada carga tira la hoja vieja (lo que no viene en el fichero se
-- BORRA). La memoria histórica NO vive aquí.
--
-- PK = `sku`, y está MEDIDO en el fichero real del 23-ago-2026, no supuesto:
--   · sku   → 356 distintos sobre 356 filas. 0 duplicados.
--   · asin  → 355 sobre 356: B07GRRYFL1 viene DOS VECES, con dos SKU (uno con FNSKU
--             propio ⇒ etiquetado, otro con FNSKU = ASIN ⇒ commingled). Una PK por
--             ASIN reventaría hoy mismo.
-- ⚠️ Que la PK sea el SKU no lo asciende a llave maestra (§1.1): es la clave de esta
--    foto consigo misma, como (seller_sku, country) lo es de inventario_internacional.
--
-- 🔴 NO HAY COLUMNA DE PAÍS, Y ES DELIBERADO. La columna `store` del informe viene
--    VACÍA en las 356 filas: vacío no significa «España», significa «todas las
--    tiendas». El fichero trae el TOTAL EUROPEO. Medido contra la base el mismo día
--    con B0002TT3N4: internacional ES 1.233 + FR 18 + IT 493 = 1.744; este informe,
--    1.749. Etiquetar esto como ES metería 1.749 unidades en un país que tiene
--    1.233 — y ese error no da un aviso, da una cifra plausible. Por eso §1.2 (el
--    país es una FILA) no aplica aquí: no hay eje país, hay un total. La columna
--    `store` se conserva para que, si algún día llega con valor, se vea EN EL DATO.
CREATE TABLE IF NOT EXISTS public.inventario_fba (
    -- Identidad
    sku                     text,
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
    -- EN TRÁNSITO — la razón de ser de esta tabla
    inbound_working         integer,
    inbound_shipped         integer,
    inbound_receiving       integer,
    -- Precio
    your_price              numeric,
    -- El testigo de que el informe sigue siendo el total europeo
    store                   text,
    -- Trazabilidad
    fichero                 text,
    fecha_foto              date,
    crudo                   jsonb,
    procesado_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sku)
);

-- 🔒 NACE CERRADA. RLS activa y CERO políticas: ni `anon` ni `authenticated` ven una
--    fila. El procesador escribe por DB_URL (conexión `postgres` = owner, a quien la
--    RLS no le aplica), así que cerrarla no le estorba.
ALTER TABLE public.inventario_fba ENABLE ROW LEVEL SECURITY;

-- 🔴 Y el ACL, a cada rol POR SU NOMBRE (ver la cabecera: el default de Supabase le
--    concede `arwdDxtm` a anon y authenticated al nacer, y `from public` no lo quita).
REVOKE ALL ON public.inventario_fba FROM PUBLIC, anon, authenticated;

-- Índices. Por ASIN porque es por donde cruzará la vista que venga (el puente a la
-- identidad va por ASIN, jamás por SKU: §1.1). Por fecha_foto para poder preguntar
-- «¿de cuándo es esta foto?» sin leer la tabla entera.
CREATE INDEX IF NOT EXISTS idx_inventario_fba_asin       ON public.inventario_fba(asin);
CREATE INDEX IF NOT EXISTS idx_inventario_fba_fecha_foto ON public.inventario_fba(fecha_foto);

COMMENT ON TABLE public.inventario_fba IS
  'FOTO del informe «Gestión de inventario de Logística de Amazon» (Seller → Informes '
  '→ Logística de Amazon). Cajón FOTO: cada carga borra lo que no viene en el fichero. '
  'NO tiene país: la columna `store` viene vacía y eso significa «todas las tiendas», '
  'o sea que las cifras son el TOTAL EUROPEO (medido 23-ago-2026: B0002TT3N4 → 1.749 '
  'aquí contra ES 1.233 + FR 18 + IT 493 = 1.744 en inventario_internacional). Existe '
  'por `inbound_shipped`: es el único sitio donde vive lo que está EN TRÁNSITO desde '
  'que salud_fba se congeló el 16-ago-2026. La carga es procesador_inventario_fba.py.';

COMMENT ON COLUMN public.inventario_fba.sku IS
  'seller-sku del informe. Es la PK DE ESTA FOTO (356 únicos sobre 356 filas, medido '
  '23-ago-2026) porque el ASIN NO es único aquí: B07GRRYFL1 viene con dos SKU, uno '
  'etiquetado y otro commingled. NO es llave maestra ni cruza catálogos (§1.1).';
COMMENT ON COLUMN public.inventario_fba.inbound_shipped IS
  'afn-inbound-shipped-quantity: unidades YA ENVIADAS a Amazon y todavía no recibidas '
  '— lo que está en el camión. Es la razón de ser de esta tabla: sin este dato la app '
  'manda a preparar un envío que ya salió.';
COMMENT ON COLUMN public.inventario_fba.available IS
  'afn-fulfillable-quantity: en la estantería y vendible. NO incluye lo que viene de '
  'camino (eso es inbound_shipped) ni lo reservado.';
COMMENT ON COLUMN public.inventario_fba.warehouse_quantity IS
  'afn-warehouse-quantity: lo que Amazon tiene físicamente en almacén, sumando toda '
  'Europa (ver el comentario de la tabla sobre `store`).';
COMMENT ON COLUMN public.inventario_fba.store IS
  'La columna `store` del informe. VACÍA en las 356 filas del 23-ago-2026, y vacío '
  'significa «todas las tiendas». Si algún día llega con valor, el informe está '
  'contando OTRA COSA y estas cifras dejan de ser comparables con las anteriores: el '
  'procesador lo GRITA, y queda aquí para que se vea en el dato y no sólo en el log.';
COMMENT ON COLUMN public.inventario_fba.fecha_foto IS
  'LA FECHA DEL DATO: cuándo se subió el informe al buzón. El fichero no trae fecha ni '
  'dentro ni en el nombre (es un ID numérico de Amazon). NO confundir con procesado_at, '
  'que es cuándo corrió el robot.';
COMMENT ON COLUMN public.inventario_fba.crudo IS
  'Las 26 columnas del informe tal cual, aunque hoy sólo se tipen 16. La despensa '
  'común: el sales-rank de keepa llevaba semanas sin mirarse y resultó ser el detector '
  'de ASIN muertos.';

-- ── 3) EL BUZÓN: autorizar la carpeta ───────────────────────────────────────
-- Sin esto, subir el informe desde la app da «new row violates row-level security
-- policy» — es el último eslabón de la cadena y el único que se olvidó con
-- custom_analytics el 10-ago. Firma idéntica, para que las cuatro políticas sigan
-- colgando de ella sin enterarse.
CREATE OR REPLACE FUNCTION public.moloka_buzones_fase0()
 RETURNS text[]
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select array['salud_fba','internacional','keepa_escaparate',
               'all_listings','ledger','paneu_aptos','transacciones',
               'custom_analytics','inventario_fba']
$function$;

-- ── 4) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
-- Si algo no cuadra, el RAISE aborta y el cambio entero se deshace. Verificar
-- después de commitear sería enterarse tarde.
DO $$
DECLARE
  n_carpetas int; n_politicas int; n_antes int; es_inmutable boolean; sp text[];
  faltan text; rls boolean; n_pol_tabla int; n_cols int; n_idx int;
BEGIN
  -- 4a) El buzón
  SELECT array_length(public.moloka_buzones_fase0(), 1) INTO n_carpetas;
  IF NOT ('inventario_fba' = any(public.moloka_buzones_fase0())) THEN
    RAISE EXCEPTION 'ABORTA: tras el REPLACE, inventario_fba sigue sin estar autorizado.';
  END IF;
  IF n_carpetas <> 9 THEN
    RAISE EXCEPTION 'ABORTA: esperaba 9 carpetas y hay %.', n_carpetas;
  END IF;
  SELECT string_agg(c, ', ') INTO faltan
    FROM unnest(ARRAY['salud_fba','internacional','keepa_escaparate','all_listings',
                      'ledger','paneu_aptos','transacciones','custom_analytics']) AS c
   WHERE NOT (c = any(public.moloka_buzones_fase0()));
  IF faltan IS NOT NULL THEN
    RAISE EXCEPTION 'ABORTA: han desaparecido carpetas que estaban: %', faltan;
  END IF;

  SELECT provolatile = 'i', proconfig INTO es_inmutable, sp
    FROM pg_proc WHERE proname = 'moloka_buzones_fase0'
                   AND pronamespace = 'public'::regnamespace;
  IF NOT es_inmutable THEN
    RAISE EXCEPTION 'ABORTA: la función ha dejado de ser IMMUTABLE.';
  END IF;
  IF sp IS DISTINCT FROM ARRAY['search_path=""'] THEN
    RAISE EXCEPTION 'ABORTA: se ha perdido el search_path a vacío (es %).', sp;
  END IF;

  -- 🔴 Lo que un DROP se habría llevado: las políticas. Contra el recuento PREVIO,
  --    no contra un 4 fijo (ver la cabecera).
  SELECT count(*) INTO n_politicas
    FROM pg_policy WHERE polrelid = 'storage.objects'::regclass
                     AND polname LIKE 'buzones_v2%';
  SELECT n_politicas_antes INTO n_antes FROM _control_buzones;
  IF n_politicas <> n_antes THEN
    RAISE EXCEPTION 'ABORTA: había % políticas buzones_v2_* antes y ahora hay %. El '
                    'CREATE OR REPLACE se ha llevado alguna por delante — eso sólo pasa '
                    'con un DROP. PARA y mira qué se ha ejecutado.', n_antes, n_politicas;
  END IF;

  -- 4b) La tabla, y que nace CERRADA
  SELECT relrowsecurity INTO rls
    FROM pg_class WHERE oid = 'public.inventario_fba'::regclass;
  IF NOT rls THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba se ha creado con la RLS APAGADA.';
  END IF;
  SELECT count(*) INTO n_pol_tabla
    FROM pg_policy WHERE polrelid = 'public.inventario_fba'::regclass;
  IF n_pol_tabla <> 0 THEN
    RAISE EXCEPTION 'ABORTA: inventario_fba tiene % política(s) y tiene que nacer con '
                    'CERO.', n_pol_tabla;
  END IF;
  IF has_table_privilege('anon', 'public.inventario_fba', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `anon` puede hacer SELECT sobre inventario_fba. El revoke '
                    'no ha hecho su trabajo (default privileges de Supabase).';
  END IF;
  IF has_table_privilege('authenticated', 'public.inventario_fba', 'SELECT') THEN
    RAISE EXCEPTION 'ABORTA: `authenticated` puede hacer SELECT sobre inventario_fba.';
  END IF;

  -- 4c) La forma de la tabla: las 20 columnas que el procesador va a escribir.
  --     🔑 Se cuentan por NOMBRE, no el total: un `count(*) = 20` saldría igual con
  --     una columna mal escrita y otra de más.
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'inventario_fba'
     AND column_name IN ('sku','fnsku','asin','product_name','condition',
                         'warehouse_quantity','available','unfulfillable_quantity',
                         'total_reserved_quantity','total_quantity','fc_transfer',
                         'inbound_working','inbound_shipped','inbound_receiving',
                         'your_price','store','fichero','fecha_foto','crudo',
                         'procesado_at');
  IF n_cols <> 20 THEN
    RAISE EXCEPTION 'ABORTA: de las 20 columnas que el procesador escribe, sólo existen '
                    '%. La tabla y procesador_inventario_fba.py han dejado de cuadrar.',
                    n_cols;
  END IF;

  SELECT count(*) INTO n_idx FROM pg_indexes
   WHERE schemaname = 'public' AND tablename = 'inventario_fba';
  RAISE NOTICE 'Número de control OK: 9 carpetas (inventario_fba dentro), las % '
               'políticas buzones_v2_* siguen en pie, y la tabla nace CERRADA '
               '(RLS on, 0 políticas, anon y authenticated sin SELECT) con sus 20 '
               'columnas y % índices.', n_politicas, n_idx;
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la verificación):
--
--   -- el buzón
--   select 'inventario_fba' = any(public.moloka_buzones_fase0()) as autorizado,
--          array_length(public.moloka_buzones_fase0(), 1)        as n_carpetas;
--   -- → true · 9
--
--   -- 🔴 EL ACL SE CUENTA EN PRODUCCIÓN, NO EN EL ENSAYO (ver la cabecera)
--   select relrowsecurity                                        as rls_activa,
--          (select count(*) from pg_policy
--            where polrelid = 'public.inventario_fba'::regclass)  as n_politicas,
--          relacl                                                as acl,
--          has_table_privilege('anon','public.inventario_fba','SELECT')          as anon_lee,
--          has_table_privilege('authenticated','public.inventario_fba','SELECT') as auth_lee
--     from pg_class where oid = 'public.inventario_fba'::regclass;
--   -- → true · 0 · (sin anon ni authenticated) · false · false
--
--   -- y cuando el procesador haya cargado, LO QUE IMPORTA:
--   select count(*)                                        as filas,
--          sum(inbound_shipped)                            as en_transito,
--          count(distinct asin) filter (where inbound_shipped > 0) as asin_en_transito,
--          max(fecha_foto)                                 as foto
--     from public.inventario_fba;
--   -- esperado con 50632020686.txt: 356 · 363 · 17
--
--   select sku, asin, available, inbound_shipped, total_quantity
--     from public.inventario_fba where asin = 'B0BVK34G8X';
--   -- el testigo: available 1 · inbound_shipped 36 · total 38
-- ============================================================================
