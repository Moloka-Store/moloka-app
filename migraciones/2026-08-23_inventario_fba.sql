-- ============================================================================
-- inventario_fba — LA TABLA, y sólo la tabla.                    23-ago-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ. `salud_fba` está roto por parte de Amazon (sirve ficheros truncados y
--   los para su Guarda 9) y lleva congelado desde el 16-ago. Casi todo lo suyo lo
--   cubren ya otras tablas MENOS UNA COSA: las unidades EN TRÁNSITO
--   (`inbound_shipped`). Sin ese dato la app manda a preparar un envío que ya
--   salió. Medido el 23-ago-2026 en el fichero real (50632020686.txt): 363
--   unidades de camino en 17 ASIN, contra las 143 que era lo último que sabía
--   `salud_fba` (`select sum(inbound_shipped) from salud_fba` → 143 en 9 filas,
--   snapshot del 16-ago).
--
-- 🔴 QUÉ **NO** HACE ESTA MIGRACIÓN, Y POR QUÉ SE SACÓ (decisión de Fernando,
--    23-ago-2026). La primera versión traía además un `CREATE OR REPLACE` de
--    `public.moloka_buzones_fase0()` para autorizar la carpeta del buzón. **Se ha
--    sacado a su propia migración, que se verá aparte y con Fernando delante.**
--    El motivo, medido: de esa función cuelgan las CUATRO políticas
--    `buzones_v2_*` de `storage.objects`, y las cuatro la invocan en su expresión
--    (`(storage.foldername(name))[1] = ANY (moloka_buzones_fase0() || ARRAY['entrada','escaner'])`).
--    O sea que esa función ES la lista blanca de subida de Elena: si se rompe,
--    Elena no puede meter informes. Eso no viaja de polizón en la migración de
--    una tabla que no lee nadie.
--    ⚠️ CONSECUENCIA, dicha en alto para que no sorprenda: hasta que exista esa
--    segunda migración, **subir el informe a `informes/inventario_fba/` DESDE LA
--    APP dará «new row violates row-level security policy»**. La CARGA sí
--    funciona: el procesador lee el Storage con la clave de servicio, que salta la
--    RLS. Lo que falta es la puerta de la app, no la del robot.
--
-- QUÉ HACE, entonces:
--   1) CREA la tabla `inventario_fba`, CERRADA (RLS activa, 0 políticas, y el
--      revoke a cada rol POR SU NOMBRE — ver abajo).
--   2) Sus índices y sus comentarios.
--   3) Comprueba, DENTRO de la transacción, que ha nacido como se quería.
--   Ni una línea toca `storage`, ni `pg_policy` de otra tabla, ni ninguna función
--   existente. Si sale mal, se revierte limpia y no hay nada que dependa de ella:
--   la tabla nace vacía y NADIE la lee todavía.
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
--   así, el ACL se cuenta EN PRODUCCIÓN después de aplicar (bloque final).
--
-- ⚠️ EL ENSAYO DE ESTA MIGRACIÓN SÓLO PRUEBA ALGO SI LA TABLA **NO** EXISTE YA.
--   Es idempotente (IF NOT EXISTS), y un ensayo sobre un destino que ya está en el
--   estado final sale verde sin haber medido nada. El testigo, antes de fiarte:
--       select to_regclass('public.inventario_fba');   -- null = hay algo que probar
--   Medido el 23-ago-2026: `null` en staging Y en producción.
--
-- ESCALERA: restaurar staging → staging ensayo → staging aplicar → verificación SQL
--   → producción ensayo → producción aplicar → verificación SQL. Con
--   `aplicar-migracion.yml`.
-- ============================================================================

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
-- ── 3) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
-- Si algo no cuadra, el RAISE aborta y la tabla no llega a existir. Verificar
-- después de commitear sería enterarse tarde.
DO $$
DECLARE
  rls boolean; n_pol_tabla int; n_cols int; n_idx int;
BEGIN
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
  RAISE NOTICE 'Número de control OK: inventario_fba nace CERRADA (RLS on, 0 '
               'políticas, anon y authenticated sin SELECT) con sus 20 columnas y '
               '% índices.', n_idx;
END $$;
-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la verificación):
--
--   -- ¿existe y con qué forma?
--   select to_regclass('public.inventario_fba')                  as tabla,
--          (select count(*) from information_schema.columns
--            where table_schema='public' and table_name='inventario_fba') as n_columnas,
--          (select count(*) from pg_indexes
--            where schemaname='public' and tablename='inventario_fba')    as n_indices;
--   -- → inventario_fba · 20 · 3   (2 índices propios + el de la PK)
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
--   -- 🔒 Y LO QUE ESTA MIGRACIÓN **NO** DEBE HABER TOCADO. Se cuenta a propósito:
--   --    el buzón se sacó a otra migración, así que aquí todo esto tiene que salir
--   --    EXACTAMENTE igual que antes de aplicar.
--   select array_length(public.moloka_buzones_fase0(),1)          as n_carpetas,
--          'inventario_fba' = any(public.moloka_buzones_fase0())  as buzon_autorizado,
--          (select count(*) from pg_policy
--            where polrelid='storage.objects'::regclass
--              and polname like 'buzones_v2%')                    as politicas_buzon;
--   -- → 8 · false · 4     (los MISMOS de antes: esta migración no toca el buzón)
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
