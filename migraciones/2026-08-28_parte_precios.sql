-- ============================================================================
-- parte_precios — EL REGISTRO DE DECISIONES DE PRECIO              28-ago-2026
-- ----------------------------------------------------------------------------
-- QUÉ ES. El trackeador viejo queda jubilado y el sistema nuevo arranca VACÍO.
--   Esta tabla es el ÚNICO sitio donde se escribe una decisión de precio, la tome
--   una norma automática (`origen='norma'`) o la tomemos a mano en la sesión de la
--   mañana (`origen='sesion'`). No es una foto del mercado ni un cálculo: es lo que
--   se decidió, quién lo decidió, POR QUÉ, y QUÉ SE ESPERA que pase.
--
-- CAJÓN: **PELÍCULA** (§1.6). Se apila y NUNCA se borra. Cada fila es un asiento
--   del libro de decisiones; borrar una línea es falsificar el extracto. No hay
--   `UPDATE` previsto: si mañana se cambia de idea, se escribe OTRA fila.
--   ⚠️ Por eso el índice `(asin, pais, fecha)` **NO es único**: el mismo ASIN puede
--   decidirse dos veces el mismo día (una norma por la mañana y una corrección a
--   mano después), y las dos tienen que quedar escritas. La última es la que manda
--   y se distingue por `creado_en`.
--
-- 🔴 NO HAY COLUMNA «APLICADO», Y ES DELIBERADO. Si Elena puso el precio o no se
--   DEDUCE mirando `trackeador_hist` los días siguientes: `mi_precio` para ese
--   (asin, dominio) en las fechas posteriores a `fecha`. Una columna que alguien
--   tiene que acordarse de rellenar acaba mintiendo, y encima miente con autoridad.
--   🔬 Medido el 28-ago-2026 en producción, para que conste que ese cruce existe de
--      verdad y no es una intención: `trackeador_hist` tiene 2.942 filas por dominio
--      (es/it/fr/de), del 21 al 27-ago-2026, con `mi_precio` no nulo en 2.194 (es),
--      725 (fr), 721 (it) y 720 (de).
--   ⚠️ Y el detalle que rompe el cruce si se olvida: allí la columna se llama
--      `dominio`, aquí `pais`. Es el mismo eje y el mismo alfabeto —letras, no
--      números—, pero no el mismo nombre.
--
-- 🔴 POR QUÉ LA FOTO DE LA CAJA (`bb_*`, `stock_fba_antes`, `vendo_30d_antes`) VA
--   AQUÍ Y NO SE MIRA DESPUÉS. A los 7 días el mercado ya es otro: la buy box la
--   tiene otro, el precio del competidor cambió y el stock se movió. Sin la foto
--   del momento de decidir no se puede decir si acertamos — se estaría comparando
--   la decisión contra un mercado que no es el que la motivó. Es §1.4 aplicado a
--   una decisión: **una cifra sin la fecha del dato que la sostiene es una cifra
--   que miente.**
--
-- `porque` y `espero` son NOT NULL A PROPÓSITO, y además tienen que traer algo
--   escrito (no valen ni la cadena vacía ni tres espacios): una decisión sin
--   expectativa escrita no se puede medir, y si no se puede medir no entra. El NOT
--   NULL solo prohíbe el nulo; la cadena vacía es exactamente la columna-que-miente
--   de la que huye el párrafo anterior. Por eso van además los dos CHECK.
--
-- QUÉ HACE ESTA MIGRACIÓN, y nada más:
--   1) CREA la tabla `parte_precios` con sus restricciones.
--   2) La cierra: RLS activa, `revoke` a cada rol por su nombre, `grant select` a
--      `authenticated` y UNA política de lectura. Sin escritura para `anon`.
--   3) Sus dos índices y sus comentarios.
--   4) Se autocomprueba DENTRO de la transacción: forma, cierre, y las guardas
--      HECHAS SALTAR a propósito.
--   No toca ningún objeto existente. La tabla nace vacía y hoy no la lee nadie.
--
-- 🔴 POR QUÉ HAY POLÍTICA Y NO SOLO GRANT — se aparta de «todo lo nuevo nace con 0
--   políticas» (§4) y se dice en alto. El encargo pide `GRANT SELECT` a
--   `authenticated`. Con RLS activa y CERO políticas, ese grant es una mentira
--   educada: `has_table_privilege` diría `true` y la tabla se leería **VACÍA**, sin
--   error, sin aviso y sin que nadie lo note hasta que alguien abra la pantalla. El
--   permiso no es la puerta; la política sí. Así que van las dos cosas, y la
--   política es la MÁS ESTRECHA que cumple el encargo: solo `SELECT`, solo
--   `authenticated`, solo con sesión iniciada.
--   La forma `(SELECT auth.uid()) IS NOT NULL` —con el SELECT— no es un capricho de
--   estilo: sin él Postgres evalúa la función UNA VEZ POR FILA. Es la misma forma
--   que ya tienen `inventario_fba`, `keepa_escaparate`, `listings_amazon`,
--   `ledger_movimientos`, `paneu_aptos` y `transacciones_movimientos`.
--
-- 🔴 QUIÉN ESCRIBE, entonces: NADIE por RLS. No hay política de INSERT/UPDATE/DELETE
--   para ningún rol, así que solo escriben `postgres` (la conexión `DB_URL` de los
--   robots, que es el dueño y a quien la RLS no le aplica) y `service_role`. El día
--   que la sesión de la mañana quiera escribir desde la app como `authenticated`,
--   eso es un `GRANT INSERT` + su política, en SU migración y con su decisión — no
--   de polizón en la que crea la tabla.
--
-- 🔴 EL `REVOKE` VA AUNQUE LA TABLA SEA NUEVA. Medido el 28-ago-2026 en
--   `pg_default_acl` de producción: el default de `postgres` sobre tablas de
--   `public` es hoy `{postgres=arwdDxtm, service_role=arwdDxtm}` — ya NO trae ni
--   `anon` ni `authenticated`, así que por esa vía la tabla nace cerrada. Pero el
--   default de `supabase_admin` sobre el mismo esquema SÍ los trae
--   (`anon=arwdDxtm, authenticated=arwdDxtm`), o sea que QUIÉN crea el objeto decide
--   cómo nace. El `revoke` explícito hace que dé igual, y `from public` no bastaría:
--   son grants a un rol por su nombre.
--   ⚠️ Y si algún día esta tabla se recrea con DROP+CREATE, el ACL se pierde y hay
--      que volver a revocar. Aquí no hay drop.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI LA TABLA **NO** EXISTE YA. Es idempotente
--   (IF NOT EXISTS), y un ensayo sobre un destino que ya está en el estado final
--   sale verde sin haber medido nada. El testigo, antes de fiarte:
--       select to_regclass('public.parte_precios');   -- null = hay algo que probar
--   Medido el 28-ago-2026: `null` en producción Y en staging. Y si alguien la crea
--   antes, el primer bloque de guardas lo GRITA en vez de salir verde en silencio.
--
-- ESCALERA: restaurar staging → staging ensayo → staging aplicar → verificación SQL
--   → producción ensayo → producción aplicar → verificación SQL, con
--   `aplicar-migracion.yml`. La aplica Fernando, con él delante.
-- ============================================================================

-- ── 1) GUARDAS ──────────────────────────────────────────────────────────────
DO $guardas$
DECLARE
    k char;
BEGIN
    -- ¿Hay algo que probar? Si la tabla ya está, este ensayo no demuestra que se
    -- cree bien: demuestra que ya estaba. Se avisa, no se aborta — la migración es
    -- idempotente a propósito y puede relanzarse.
    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.parte_precios');
    IF k IS NOT NULL AND k <> 'r' THEN
        RAISE EXCEPTION 'ABORTA: public.parte_precios ya existe con relkind=% y aquí se espera una TABLA. Mira qué es antes de seguir.', k;
    END IF;
    IF k = 'r' THEN
        RAISE WARNING 'AVISO: parte_precios YA EXISTE antes de esta migración. Lo que venga a continuación NO demuestra que se cree bien; a lo sumo, que el destino ya estaba en el estado final. Si esperabas crearla ahora, para y mira quién la creó.';
    END IF;

    -- La tabla contra la que se DEDUCE si el precio se aplicó. No es una dependencia
    -- dura (esta migración no la toca), pero si no está, el «no hay columna
    -- aplicado» de la cabecera se queda sin la otra mitad y hay que saberlo.
    IF to_regclass('public.trackeador_hist') IS NULL THEN
        RAISE WARNING 'AVISO: no existe public.trackeador_hist en esta base. La tabla se crea igual, pero AQUÍ no se podrá deducir si una decisión se aplicó, y ese cruce es la razón por la que parte_precios no lleva columna «aplicado».';
    END IF;
END
$guardas$;

-- ── 2) LA TABLA ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.parte_precios (
    id                 bigserial   PRIMARY KEY,
    creado_en          timestamptz NOT NULL DEFAULT now(),

    -- QUÉ se decide y DÓNDE
    fecha              date        NOT NULL,   -- el día de la sesión
    asin               text        NOT NULL,   -- la capa Amazon; jamás el SKU (§1.1)
    pais               text        NOT NULL,   -- una FILA por país, nunca un sufijo (§1.2)

    -- QUIÉN lo decide
    origen             text        NOT NULL,   -- 'norma' | 'sesion'
    norma_id           text,                   -- null cuando origen='sesion'

    -- EL NÚMERO
    precio_antes       numeric,
    precio_propuesto   numeric     NOT NULL,
    margen_antes       numeric,
    margen_propuesto   numeric,

    -- EL CONTRATO CON EL FUTURO. Sin esto la decisión no se puede medir.
    porque             text        NOT NULL,
    espero             text        NOT NULL,
    medir_el           date        NOT NULL,   -- normalmente fecha + 7 días

    -- LA FOTO DE LA CAJA EN EL MOMENTO DE DECIDIR. A los 7 días el mercado ya es
    -- otro: sin esto no se puede saber después si acertamos.
    bb_precio_antes    numeric,
    bb_envio_antes     numeric,
    bb_vendedor_antes  text,
    bb_es_mio_antes    boolean,
    stock_fba_antes    integer,
    vendo_30d_antes    numeric,

    -- El país en LETRAS y minúsculas, como `trackeador_hist.dominio` y
    -- `keepa_escaparate.dominio`. Un 'ES' o un 9 no darían error: darían un cruce a
    -- cero, que es peor, porque parece un hallazgo.
    CONSTRAINT parte_precios_pais_valido
        CHECK (pais IN ('es','it','fr','de')),

    CONSTRAINT parte_precios_origen_valido
        CHECK (origen IN ('norma','sesion')),

    -- La norma que decide tiene nombre; la mano no. Es lo que dice el encargo,
    -- escrito donde no se puede olvidar.
    CONSTRAINT parte_precios_norma_coherente
        CHECK ((origen = 'norma'  AND norma_id IS NOT NULL)
            OR (origen = 'sesion' AND norma_id IS NULL)),

    -- NOT NULL no basta: la cadena vacía pasa el NOT NULL y no se puede medir.
    CONSTRAINT parte_precios_porque_escrito CHECK (btrim(porque) <> ''),
    CONSTRAINT parte_precios_espero_escrito CHECK (btrim(espero) <> ''),

    -- Medir antes de decidir no significa nada. No se exige exactamente +7 días a
    -- propósito: hay decisiones que piden 14 y no se les cierra la puerta.
    CONSTRAINT parte_precios_medir_despues CHECK (medir_el >= fecha),

    -- Un precio de 0 € no es una decisión, es un bug con forma de dato.
    CONSTRAINT parte_precios_precio_positivo CHECK (precio_propuesto > 0)
);

-- ── 3) EL CIERRE ────────────────────────────────────────────────────────────
ALTER TABLE public.parte_precios ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.parte_precios FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.parte_precios_id_seq FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.parte_precios TO authenticated;

-- `CREATE POLICY` no admite IF NOT EXISTS, y esta migración tiene que poder
-- relanzarse. Se pregunta antes, y se dice cuando ya estaba.
DO $politica$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_policy
                WHERE polrelid = 'public.parte_precios'::regclass
                  AND polname  = 'parte_precios_lectura') THEN
        RAISE NOTICE 'La política parte_precios_lectura ya existía: no se toca.';
    ELSE
        EXECUTE 'CREATE POLICY parte_precios_lectura ON public.parte_precios '
                'FOR SELECT TO authenticated '
                'USING ((SELECT auth.uid()) IS NOT NULL)';
    END IF;
END
$politica$;

-- ── 4) ÍNDICES ──────────────────────────────────────────────────────────────
-- Por `medir_el`: la pregunta de cada mañana es «¿qué toca medir hoy?».
CREATE INDEX IF NOT EXISTS idx_parte_precios_medir_el
    ON public.parte_precios (medir_el);
-- Por (asin, pais, fecha): la historia de decisiones de una ficha en un país.
-- NO es único: dos decisiones el mismo día son legítimas (ver la cabecera).
CREATE INDEX IF NOT EXISTS idx_parte_precios_asin_pais_fecha
    ON public.parte_precios (asin, pais, fecha);

-- ── 5) COMENTARIOS ──────────────────────────────────────────────────────────
COMMENT ON TABLE public.parte_precios IS
  'PELÍCULA (append, nunca se borra) de DECISIONES DE PRECIO del sistema nuevo, el '
  'que releva al trackeador jubilado. Es el ÚNICO sitio donde se escribe una decisión '
  'de precio, la tome una norma automática (origen=norma, con su norma_id) o se tome '
  'a mano en la sesión de la mañana (origen=sesion). Cada fila lleva su POR QUÉ, su '
  'expectativa escrita (espero), la fecha en que toca comprobarla (medir_el) y la '
  'FOTO de la caja en el momento de decidir (bb_*, stock_fba_antes, vendo_30d_antes), '
  'que es lo que permite juzgar después si se acertó. NO tiene columna «aplicado» a '
  'propósito: que Elena pusiera el precio o no se DEDUCE de trackeador_hist.mi_precio '
  'en los días siguientes (cruce por asin y pais = dominio). La escriben las normas y '
  'la sesión de la mañana por DB_URL/service_role; la lee la app v2 como '
  'authenticated, y solo SELECT.';

COMMENT ON COLUMN public.parte_precios.fecha IS
  'El día de la SESIÓN en que se decide. No es cuándo se escribió la fila (eso es '
  'creado_en) ni cuándo cambió el precio en Amazon (eso no lo sabe esta tabla: se '
  'deduce de trackeador_hist).';
COMMENT ON COLUMN public.parte_precios.pais IS
  'es | it | fr | de, en LETRAS y minúsculas — el mismo alfabeto que '
  'trackeador_hist.dominio y keepa_escaparate.dominio, con los que cruza. Ojo al '
  'nombre distinto: allí es `dominio`, aquí `pais`. Lo fija un CHECK porque un ES en '
  'mayúsculas no daría error, daría un cruce a cero.';
COMMENT ON COLUMN public.parte_precios.origen IS
  'norma = lo decidió una norma automática (y entonces norma_id dice cuál). '
  'sesion = lo decidimos a mano en la sesión de la mañana (y norma_id va a null). '
  'Un CHECK obliga a que las dos cosas se correspondan.';
COMMENT ON COLUMN public.parte_precios.norma_id IS
  'Identificador de la norma que tomó la decisión, en texto y SIN clave ajena: hoy no '
  'existe la tabla de normas del sistema nuevo. El día que exista, la FK va en su '
  'migración.';
COMMENT ON COLUMN public.parte_precios.porque IS
  'Por qué se decide esto, en prosa. NOT NULL y además no puede venir en blanco: una '
  'decisión sin motivo escrito no se puede revisar dentro de un mes.';
COMMENT ON COLUMN public.parte_precios.espero IS
  'Qué debería pasar, en una frase. NOT NULL y no puede venir en blanco A PROPÓSITO: '
  'es el contrato con el futuro. Sin expectativa escrita la decisión no se puede '
  'medir, y si no se puede medir no entra.';
COMMENT ON COLUMN public.parte_precios.medir_el IS
  'Cuándo toca volver a mirar. Normalmente fecha + 7 días; el CHECK solo exige que no '
  'sea anterior a `fecha`, para no cerrarle la puerta a una ventana de 14.';
COMMENT ON COLUMN public.parte_precios.bb_precio_antes IS
  'La buy box EN EL MOMENTO DE DECIDIR. Se guarda aquí porque a los 7 días ya es '
  'otra, y sin la foto de entonces la comparación no mide la decisión: mide el '
  'mercado. Lo mismo vale para bb_envio_antes, bb_vendedor_antes y bb_es_mio_antes.';
COMMENT ON COLUMN public.parte_precios.bb_envio_antes IS
  'El ENVÍO de la buy box, aparte del precio. Van separados porque lo que ve el '
  'cliente es la suma, y una caja que se gana por el envío no se explica con el '
  'precio solo.';
COMMENT ON COLUMN public.parte_precios.stock_fba_antes IS
  'Unidades en FBA en el momento de decidir. Sin esto, «no vendió nada» no distingue '
  'entre un precio malo y una ficha sin stock.';
COMMENT ON COLUMN public.parte_precios.vendo_30d_antes IS
  'Lo vendido en los 30 días previos a la decisión, tal y como se leyó ese día. Es la '
  'línea de salida contra la que se compara al medir.';

-- ── 6) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
-- Si algo no cuadra, el RAISE aborta y la tabla no llega a existir. Verificar
-- después de commitear sería enterarse tarde.
DO $control$
DECLARE
    rls        boolean;
    n_pol      int;
    pol_qual   text;
    pol_roles  text;
    n_cols     int;
    n_nn       int;
    n_idx      int;
    n_chk      int;
BEGIN
    -- 6a) LA FORMA: las 20 columnas, POR NOMBRE Y POR TIPO. Un count(*)=20 saldría
    --     igual con una columna mal escrita y otra de más, y un nombre correcto con
    --     el tipo cambiado se lee igual de bien y guarda otra cosa.
    SELECT count(*) INTO n_cols
      FROM information_schema.columns c
      JOIN (VALUES
              ('id','bigint'),
              ('creado_en','timestamp with time zone'),
              ('fecha','date'),
              ('asin','text'),
              ('pais','text'),
              ('origen','text'),
              ('norma_id','text'),
              ('precio_antes','numeric'),
              ('precio_propuesto','numeric'),
              ('margen_antes','numeric'),
              ('margen_propuesto','numeric'),
              ('porque','text'),
              ('espero','text'),
              ('medir_el','date'),
              ('bb_precio_antes','numeric'),
              ('bb_envio_antes','numeric'),
              ('bb_vendedor_antes','text'),
              ('bb_es_mio_antes','boolean'),
              ('stock_fba_antes','integer'),
              ('vendo_30d_antes','numeric')
           ) AS esperado(nombre, tipo)
        ON esperado.nombre = c.column_name AND esperado.tipo = c.data_type
     WHERE c.table_schema = 'public' AND c.table_name = 'parte_precios';
    IF n_cols <> 20 THEN
        RAISE EXCEPTION 'ABORTA: de las 20 columnas esperadas (nombre Y tipo) solo casan %. La tabla no ha nacido con la forma que dice la cabecera.', n_cols;
    END IF;

    -- 6b) LOS NOT NULL. Son la mitad del encargo: `espero` opcional no es esta misma
    --     tabla con una columna más floja, es otra cosa.
    SELECT count(*) INTO n_nn
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'parte_precios'
       AND is_nullable = 'NO'
       AND column_name IN ('id','creado_en','fecha','asin','pais','origen',
                           'precio_propuesto','porque','espero','medir_el');
    IF n_nn <> 10 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban 10 columnas NOT NULL y hay %. Falta alguna obligación.', n_nn;
    END IF;

    -- 6c) LOS CHECK, por su nombre. Siete.
    SELECT count(*) INTO n_chk
      FROM pg_constraint
     WHERE conrelid = 'public.parte_precios'::regclass AND contype = 'c'
       AND conname IN ('parte_precios_pais_valido','parte_precios_origen_valido',
                       'parte_precios_norma_coherente','parte_precios_porque_escrito',
                       'parte_precios_espero_escrito','parte_precios_medir_despues',
                       'parte_precios_precio_positivo');
    IF n_chk <> 7 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban los 7 CHECK con nombre y hay %.', n_chk;
    END IF;

    -- 6d) EL CIERRE: RLS, UNA política de SELECT para authenticated y en la forma
    --     rápida. Se ancla sobre lo que NO debe aparecer (la forma lenta), que es la
    --     única mitad que se mueve.
    SELECT relrowsecurity INTO rls FROM pg_class WHERE oid = 'public.parte_precios'::regclass;
    IF NOT rls THEN
        RAISE EXCEPTION 'ABORTA: parte_precios se ha creado con la RLS APAGADA.';
    END IF;

    SELECT count(*) INTO n_pol FROM pg_policy WHERE polrelid = 'public.parte_precios'::regclass;
    IF n_pol <> 1 THEN
        RAISE EXCEPTION 'ABORTA: parte_precios tiene % políticas y se esperaba exactamente 1 (solo lectura).', n_pol;
    END IF;

    SELECT p.qual, p.roles::text INTO pol_qual, pol_roles
      FROM pg_policies p
     WHERE p.schemaname = 'public' AND p.tablename = 'parte_precios'
       AND p.policyname = 'parte_precios_lectura';
    IF pol_qual IS NULL THEN
        RAISE EXCEPTION 'ABORTA: no existe la política parte_precios_lectura.';
    END IF;
    IF pol_roles <> '{authenticated}' THEN
        RAISE EXCEPTION 'ABORTA: la política es para % y tenía que ser solo para authenticated.', pol_roles;
    END IF;
    IF position('SELECT auth.uid()' in pol_qual) = 0 THEN
        RAISE EXCEPTION 'ABORTA: la política dice [%] y le falta el SELECT envolviendo a auth.uid(): así Postgres la evalúa una vez POR FILA.', pol_qual;
    END IF;

    -- 6e) EL ACL, POR NIVELES Y NO SOLO POR «PUEDE LEER». Lo que hay que vigilar no
    --     es que authenticated lea: es que NO pueda escribir, y que anon no pueda
    --     nada.
    IF NOT has_table_privilege('authenticated', 'public.parte_precios', 'SELECT') THEN
        RAISE EXCEPTION 'ABORTA: authenticated NO puede leer parte_precios; el GRANT no ha hecho su trabajo.';
    END IF;
    IF has_table_privilege('authenticated', 'public.parte_precios', 'INSERT')
       OR has_table_privilege('authenticated', 'public.parte_precios', 'UPDATE')
       OR has_table_privilege('authenticated', 'public.parte_precios', 'DELETE') THEN
        RAISE EXCEPTION 'ABORTA: authenticated puede ESCRIBIR en parte_precios. Esta tabla es una Película: se apila desde los robots, no desde el navegador.';
    END IF;
    IF has_table_privilege('anon', 'public.parte_precios', 'SELECT')
       OR has_table_privilege('anon', 'public.parte_precios', 'INSERT')
       OR has_table_privilege('anon', 'public.parte_precios', 'UPDATE')
       OR has_table_privilege('anon', 'public.parte_precios', 'DELETE') THEN
        RAISE EXCEPTION 'ABORTA: anon tiene algún privilegio sobre parte_precios.';
    END IF;
    IF has_sequence_privilege('anon', 'public.parte_precios_id_seq', 'USAGE')
       OR has_sequence_privilege('authenticated', 'public.parte_precios_id_seq', 'USAGE') THEN
        RAISE EXCEPTION 'ABORTA: la secuencia de parte_precios ha quedado abierta a anon o a authenticated.';
    END IF;

    SELECT count(*) INTO n_idx FROM pg_indexes
     WHERE schemaname = 'public' AND tablename = 'parte_precios';
    IF n_idx <> 3 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban 3 índices (la PK y los dos del encargo) y hay %.', n_idx;
    END IF;

    RAISE NOTICE 'Forma y cierre OK: 20 columnas con su tipo, 10 NOT NULL, 7 CHECK, RLS activa, 1 política de lectura para authenticated y 3 índices.';
END
$control$;

-- ── 7) LAS GUARDAS, HECHAS SALTAR A PROPÓSITO ───────────────────────────────
-- Un CHECK que solo se ha visto escrito no se ha probado. Aquí se le mete a la
-- tabla exactamente lo que tiene que rechazar, y si ALGUNO pasa, la migración
-- aborta. Todo dentro de la misma transacción: no queda ni una fila.
DO $falsadores$
DECLARE
    colados text := '';
BEGIN
    -- `espero` en blanco: el caso que motiva el NOT NULL, y el que el NOT NULL solo
    -- NO caza.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'sesion', 9.99, 'sonda', '   ', current_date + 7);
        colados := colados || 'espero-en-blanco ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- País en mayúsculas: no daría error nunca, daría un cruce a cero.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'ES', 'sesion', 9.99, 'sonda', 'sonda', current_date + 7);
        colados := colados || 'pais-en-mayusculas ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Decisión a mano con norma_id puesto: o lo decidió una norma, o lo decidimos
    -- nosotros.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, norma_id, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'sesion', 'N-01', 9.99, 'sonda', 'sonda', current_date + 7);
        colados := colados || 'sesion-con-norma ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Norma sin nombre: la otra mitad del mismo CHECK. Se prueba también, porque una
    -- restricción con dos ramas se rompe por la rama que nadie mira.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'norma', 9.99, 'sonda', 'sonda', current_date + 7);
        colados := colados || 'norma-sin-id ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Medir antes de decidir.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'sesion', 9.99, 'sonda', 'sonda', current_date - 1);
        colados := colados || 'medir-antes-de-decidir ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Precio a cero.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'sesion', 0, 'sonda', 'sonda', current_date + 7);
        colados := colados || 'precio-cero ';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- Decisión sin porqué: aquí el que tiene que saltar es el NOT NULL, no un CHECK.
    BEGIN
        INSERT INTO public.parte_precios (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
        VALUES (current_date, 'SONDA00001', 'es', 'sesion', 9.99, NULL, 'sonda', current_date + 7);
        colados := colados || 'porque-nulo ';
    EXCEPTION WHEN not_null_violation THEN NULL;
    END;

    IF colados <> '' THEN
        RAISE EXCEPTION 'ABORTA: la tabla ha ACEPTADO lo que tenía que rechazar (%). Las restricciones están escritas pero no muerden.', colados;
    END IF;
    RAISE NOTICE 'Falsadores OK: los 7 intentos malos han sido rechazados por la tabla.';
END
$falsadores$;

-- ── 8) EL TESTIGO DE LA PUERTA: se EJERCE, no se lee ────────────────────────
-- `has_table_privilege` ya se miró arriba, y no basta: el permiso no es la puerta.
-- Con RLS activa, un GRANT sin política deja la tabla legible y VACÍA, sin error y
-- sin aviso. La única forma de saberlo es meter una fila y mirarla con el rol de la
-- app. La fila se borra y la secuencia se deja como estaba: la tabla tiene que
-- quedar vacía y con el id 1 libre para la primera decisión de verdad.
DO $puerta$
DECLARE
    n_auth        bigint;
    n_final       bigint;
    anon_ha_leido boolean := false;
BEGIN
    INSERT INTO public.parte_precios
        (fecha, asin, pais, origen, precio_propuesto, porque, espero, medir_el)
    VALUES (current_date, 'SONDAPUERT', 'es', 'sesion', 9.99,
            'sonda de la migración: comprueba que authenticated ve las filas',
            'que esta fila se borre antes de terminar la transacción',
            current_date + 7);

    -- 8a) authenticated CON sesión: tiene que ver la fila. Sin fila, este testigo no
    --     distinguiría «la política deja pasar» de «no había nada que ver».
    SET LOCAL ROLE authenticated;
    PERFORM set_config('request.jwt.claims',
                       '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}',
                       true);
    SELECT count(*) INTO n_auth FROM public.parte_precios;
    RESET ROLE;
    IF n_auth <> 1 THEN
        RAISE EXCEPTION 'ABORTA: como authenticated se ven % filas y tenía que ver 1. El GRANT está pero la política no deja pasar: la tabla se leería VACÍA desde la app, sin error.', n_auth;
    END IF;

    -- 8b) anon: tiene que chocar. Se espera el error de permiso; si en vez de eso
    --     devuelve un número, la puerta está abierta.
    BEGIN
        SET LOCAL ROLE anon;
        PERFORM count(*) FROM public.parte_precios;
        anon_ha_leido := true;
        RESET ROLE;
    EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
    END;
    IF anon_ha_leido THEN
        RAISE EXCEPTION 'ABORTA: anon ha podido leer parte_precios.';
    END IF;

    -- 8c) Se recoge la sonda. La tabla nace vacía, y la secuencia también: la
    --     primera decisión de verdad tiene que ser el id 1.
    DELETE FROM public.parte_precios WHERE asin = 'SONDAPUERT';
    PERFORM setval('public.parte_precios_id_seq', 1, false);

    SELECT count(*) INTO n_final FROM public.parte_precios;
    IF n_final <> 0 THEN
        RAISE EXCEPTION 'ABORTA: quedan % filas en parte_precios y tiene que nacer VACÍA. La sonda no se ha recogido.', n_final;
    END IF;

    RAISE NOTICE 'Testigo de la puerta OK: authenticated con sesión ve la fila, anon choca con el permiso, y la tabla queda vacía con el id 1 libre.';
END
$puerta$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL contra la base, aparte del job — el log NO es
-- la verificación):
--
--   -- ¿existe, con qué forma y vacía?
--   select to_regclass('public.parte_precios')                                as tabla,
--          (select count(*) from information_schema.columns
--            where table_schema='public' and table_name='parte_precios')      as n_columnas,
--          (select count(*) from pg_indexes
--            where schemaname='public' and tablename='parte_precios')         as n_indices,
--          (select count(*) from public.parte_precios)                        as n_filas;
--   -- → parte_precios · 20 · 3 · 0
--
--   -- 🔴 EL ACL SE CUENTA EN PRODUCCIÓN, NO EN EL ENSAYO: staging viene de un dump
--   --    con --no-privileges y sus ACL son los de Supabase por defecto.
--   select relrowsecurity                                                      as rls_activa,
--          relacl::text                                                        as acl,
--          has_table_privilege('authenticated','public.parte_precios','SELECT') as auth_lee,
--          has_table_privilege('authenticated','public.parte_precios','INSERT') as auth_escribe,
--          has_table_privilege('anon','public.parte_precios','SELECT')          as anon_lee
--     from pg_class where oid = 'public.parte_precios'::regclass;
--   -- → true · {postgres=arwdDxtm/postgres,service_role=arwdDxtm/postgres,
--   --           authenticated=r/postgres} · true · false · false
--   -- (es el mismo ACL que ya tienen trackeador_hist, trackeador_contrato,
--   --  inventario_fba y parametro_coste, medido el 28-ago-2026 en producción)
--
--   select policyname, cmd, roles::text, qual from pg_policies
--    where schemaname='public' and tablename='parte_precios';
--   -- → parte_precios_lectura · SELECT · {authenticated} ·
--   --   (( SELECT auth.uid() AS uid) IS NOT NULL)
--
--   -- Y LO QUE ESTA MIGRACIÓN NO DEBE HABER TOCADO: el resto de políticas de
--   -- public, que tienen que quedarse en el número de antes MÁS UNA.
--   select count(*) from pg_policies where schemaname='public';
--
--   -- Cuando haya decisiones dentro, la pregunta de cada mañana:
--   select fecha, asin, pais, origen, precio_antes, precio_propuesto, espero
--     from public.parte_precios where medir_el = current_date order by asin, pais;
--
--   -- Y la deducción del «aplicado», que es por lo que no hay columna:
--   select p.fecha, p.asin, p.pais, p.precio_propuesto,
--          h.fecha as mirado_el, h.mi_precio
--     from public.parte_precios p
--     join public.trackeador_hist h
--       on h.asin = p.asin and h.dominio = p.pais and h.fecha > p.fecha
--    order by p.fecha desc, p.asin, h.fecha;
-- ============================================================================
