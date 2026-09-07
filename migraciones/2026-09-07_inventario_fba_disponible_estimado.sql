-- ============================================================================
-- inventario_fba — EL PUENTE: el disponible estimado cuando el informe
-- no trae el tránsito.                                              7-sep-2026
-- ----------------------------------------------------------------------------
-- POR QUÉ. Desde el 7-sep-2026 Amazon sirve el informe FBA sin
--   `afn-fc-transfer-quantity`, así que `fc_transfer` queda a NULO y el
--   disponible de esa carga es «al menos el vendible». Medido sobre la verdad
--   guardada (11 días, 4.042 filas sku-día del histórico, cuando el tránsito sí
--   venía leído): quedarse en el vendible deja el disponible **3.080 unidades
--   corto, y siempre corto**. Eso decide reposiciones.
--
-- 🔑 LA FÓRMULA, y el porqué de cada trozo:
--        disponible_estimado = available + max(0, internacional − entrantes − available)
--   que es `max(available, internacional − entrantes)` escrito de forma que se vea
--   el suelo: **el vendible del informe nunca se pierde**; el internacional sólo
--   puede añadir por encima.
--     · se restan los ENTRANTES porque el internacional los cuenta y el vendible
--       no: sin esa resta se sumaría dos veces la mercancía que va de camino;
--     · se toma el máximo con `available` porque el internacional puede ir
--       atrasado, y el vendible del propio informe es siempre un suelo cierto.
--   Con eso el error baja de 3.080 a **549 unidades**: de las 2.530 filas con
--   estimación CLAVA 2.425 (95,8%), se pasa en 78 (487 uds, máximo 23 en una
--   ficha) y se queda corta en 27 (62 uds).
--
-- 🔬 Y LO QUE PARECÍA «INFLADO» NO LO ES, comprobado ficha a ficha:
--     · `B08KJTM337` — el informe dice 84 los once días y el internacional
--       84 (ES) + 23 (DE). Son las 23 de ALEMANIA, que el informe FBA no reporta.
--     · `B0D6CXB8J1` — el informe decía 4 y el internacional 16 hasta el 1-sep; el
--       2-sep el informe empieza a contar esas 12 como `fc_transfer` y coinciden;
--       el 7-sep las vuelve a perder y el internacional sigue en 12, que es
--       exactamente lo que enseña la pantalla del Seller.
--   El puente CORRIGE, no infla.
--
-- 🔴 LO QUE ESTO **NO** ES, y conviene que esté escrito en la propia migración:
--     · NO es una fuente de stock. `inventario_internacional` no manda sobre
--       `inventario_fba` (Stock 6 sigue vigente).
--     · NO sustituye a nada: `available` y `fc_transfer` se siguen guardando tal
--       cual y en columnas separadas (Stock 1-2).
--     · **EL PRECIO NO LO TOCA.** La sesión de precios usa el disponible LEÍDO, y
--       si no lo hay, la ficha no entra. Esta columna la leen la pantalla de
--       reposición y la de cobertura, y nadie más.
--     · Lo que no se puede estimar se DICE: sin fila de ese ASIN en el
--       internacional, la columna queda a NULO y el origen es 'desconocido'.
--       Nunca un 0 (Stock 8). Medido: de las 1.512 filas que caen ahí, **sólo 3
--       tienen stock**. El puente falta justo donde no hace falta.
--
-- LAS TRES COLUMNAS, y por qué son tres y no una:
--     · `disponible_estimado`     — la cifra.
--     · `disponible_origen`       — 'leido' (el informe trajo el tránsito y manda
--       él) | 'estimado' | 'desconocido'. Sin esto, una cifra leída y una estimada
--       son indistinguibles dentro de la columna, y la pantalla no podría marcar
--       la diferencia que Elena tiene que ver de un vistazo.
--     · `disponible_fuente_fecha` — la `fecha_foto` del internacional que se usó.
--       Es lo que delata a los tres días que se está tirando de un dato viejo.
--
-- 🔒 SE ESTIMA TAMBIÉN LOS DÍAS EN QUE EL TRÁNSITO SÍ VIENE. Entonces el origen es
--   'leido' —manda el dato leído— pero la estimación se guarda igual, al lado de la
--   verdad. Es el falsador permanente del puente: permite medir su error CADA DÍA
--   en vez de descubrirlo el día que haga falta.
--
-- 🔴 POR QUÉ NO HAY `REVOKE` NI `ENABLE RLS` AQUÍ: no se crea ninguna tabla. Las
--   dos que se tocan ya nacieron cerradas (migraciones del 23-ago y del 7-sep) y
--   añadir una columna no cambia su ACL. Lanzar `ENABLE RLS` sobre una tabla que ya
--   la tiene pediría un AccessExclusiveLock para nada, y ése es el lock que tumbó
--   la base el 28-jul.
--
-- ⚠️ SOLO DDL: esta migración **no mueve ni una fila**. Las columnas nacen a NULO y
--   las llena el procesador en su siguiente pasada. Y hoy esa pasada no llega a
--   escribir, porque la Guarda 12 mantiene la carga cerrada mientras las cuatro
--   vistas lean el NULO como cero — eso se abre en el paso 4 del plan.
--
-- ⚠️ EL ENSAYO SOLO PRUEBA ALGO SI FALTA ALGO (es idempotente). El testigo:
--       select count(*) from information_schema.columns
--        where table_schema='public' and table_name='inventario_fba'
--          and column_name like 'disponible_%';   -- 0 = hay algo que probar
--   Medido el 7-sep-2026 en producción: 0.
--
-- ESCALERA: staging ensayo → staging aplicar → verificación por SQL → producción
--   ensayo → producción aplicar → verificación por SQL. Con `aplicar-migracion.yml`.
-- ============================================================================

-- ── 1) LAS TRES COLUMNAS, en la foto y en la película ───────────────────────
ALTER TABLE public.inventario_fba
  ADD COLUMN IF NOT EXISTS disponible_estimado     integer,
  ADD COLUMN IF NOT EXISTS disponible_origen       text,
  ADD COLUMN IF NOT EXISTS disponible_fuente_fecha date;

ALTER TABLE public.inventario_fba_historico
  ADD COLUMN IF NOT EXISTS disponible_estimado     integer,
  ADD COLUMN IF NOT EXISTS disponible_origen       text,
  ADD COLUMN IF NOT EXISTS disponible_fuente_fecha date;

COMMENT ON COLUMN public.inventario_fba.disponible_estimado IS
  'El disponible ESTIMADO: available + max(0, internacional del ASIN − entrantes '
  'del ASIN − available). El vendible es siempre el suelo; el internacional solo '
  'puede anadir por encima. 🔴 NO es una fuente de stock y EL PRECIO NO LA TOCA: '
  'la leen la pantalla de reposicion y la de cobertura. NULL cuando no hay fila de '
  'ese ASIN en el internacional — nunca 0. Medido sobre 11 dias: clava 2.425 de '
  '2.530, error 549 uds, contra 3.080 si solo se mira el vendible.';

COMMENT ON COLUMN public.inventario_fba.disponible_origen IS
  '''leido'' = el informe trajo fc_transfer y manda available + fc_transfer · '
  '''estimado'' = no lo trajo y se ha estimado desde el internacional · '
  '''desconocido'' = no lo trajo y tampoco hay internacional de ese ASIN. Es lo que '
  'permite a la pantalla marcar un numero estimado, que Elena tiene que poder '
  'distinguir de un vistazo de uno leido. Con ''leido'' la estimacion se guarda '
  'igual, al lado de la verdad: es el falsador permanente del puente.';

COMMENT ON COLUMN public.inventario_fba.disponible_fuente_fecha IS
  'La fecha_foto del internacional que se uso para estimar. Sirve para ver a los '
  'tres dias que se esta tirando de un dato viejo: si no se mueve, el internacional '
  'tambien se ha parado y lo que se estima con el ya no es de hoy.';

COMMENT ON COLUMN public.inventario_fba_historico.disponible_estimado IS
  'Lo que se estimo ESE dia, con el internacional de ESE dia. Congelado: es lo que '
  'permite medir hacia atras el error del puente.';
COMMENT ON COLUMN public.inventario_fba_historico.disponible_origen IS
  'Bajo que regla se escribio el disponible de ese fotograma: ''leido'', ''estimado'' '
  'o ''desconocido''. Sin esto la serie no se puede releer.';
COMMENT ON COLUMN public.inventario_fba_historico.disponible_fuente_fecha IS
  'La fecha_foto del internacional que se uso en ESE fotograma.';

-- ── 2) EL NÚMERO DE CONTROL, DENTRO DE LA TRANSACCIÓN ───────────────────────
DO $$
DECLARE
  n_cols int; n_rls int; escritas int;
BEGIN
  -- 2.1 · Las seis columnas (tres en cada tabla) existen, POR NOMBRE. Un count
  --       a secas saldría igual con una mal escrita y otra de más.
  SELECT count(*) INTO n_cols FROM information_schema.columns
   WHERE table_schema = 'public'
     AND table_name IN ('inventario_fba', 'inventario_fba_historico')
     AND column_name IN ('disponible_estimado', 'disponible_origen',
                         'disponible_fuente_fecha');
  IF n_cols <> 6 THEN
    RAISE EXCEPTION 'ABORTA: se esperaban 6 columnas nuevas (3 en cada tabla) y hay %.', n_cols;
  END IF;

  -- 2.2 · Nacen VACÍAS. Esta migración no llena nada: si algo tiene valor, es que
  --       ha movido datos sin querer.
  SELECT (SELECT count(*) FROM public.inventario_fba WHERE disponible_origen IS NOT NULL)
       + (SELECT count(*) FROM public.inventario_fba_historico WHERE disponible_origen IS NOT NULL)
    INTO escritas;
  IF escritas <> 0 THEN
    RAISE EXCEPTION 'ABORTA: % fila(s) tienen ya disponible_origen. Esta migracion es '
                    'SOLO DDL y no debe escribir nada; las llena el procesador.', escritas;
  END IF;

  -- 2.3 · Las dos tablas siguen CERRADAS. Anadir una columna no cambia el ACL,
  --       pero comprobarlo es barato y el dia que no se cumpla hay que enterarse.
  SELECT count(*) INTO n_rls FROM pg_class
   WHERE oid IN ('public.inventario_fba'::regclass,
                 'public.inventario_fba_historico'::regclass)
     AND relrowsecurity;
  IF n_rls <> 2 THEN
    RAISE EXCEPTION 'ABORTA: solo % de las 2 tablas tienen la RLS activa.', n_rls;
  END IF;

  RAISE NOTICE 'Numero de control OK: 6 columnas nuevas puestas, 0 filas escritas '
               '(solo DDL) y las 2 tablas siguen con la RLS activa.';
END $$;

-- ============================================================================
-- VERIFICACIÓN POSTERIOR (por SQL, aparte del job — el log no es la prueba):
--
--   select table_name, column_name, data_type
--     from information_schema.columns
--    where table_schema='public'
--      and table_name in ('inventario_fba','inventario_fba_historico')
--      and column_name like 'disponible_%'
--    order by 1,2;
--   -- → 6 filas: estimado integer · fuente_fecha date · origen text, en las dos
--
--   -- nacen vacías (las llena el procesador, no la migración):
--   select count(*) filter (where disponible_origen is not null) as escritas,
--          count(*)                                              as filas
--     from public.inventario_fba;
--   -- → 0 · 381
--
--   -- y las dos tablas siguen cerradas:
--   select relname, relrowsecurity,
--          has_table_privilege('authenticated','public.'||relname,'INSERT') as auth_escribe
--     from pg_class
--    where oid in ('public.inventario_fba'::regclass,
--                  'public.inventario_fba_historico'::regclass);
--   -- → true/false en las dos. 🔴 has_table_privilege, NO role_table_grants:
--   --   esa vista se filtra por el rol de la sesion y devuelve vacio sin avisar.
-- ============================================================================
