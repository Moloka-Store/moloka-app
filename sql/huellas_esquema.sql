-- ============================================================================
-- HUELLAS DEL ESQUEMA DE `public` — SEIS FÓRMULAS, UN SOLO SITIO
-- ----------------------------------------------------------------------------
-- QUE DEVUELVE. Seis filas, SIEMPRE en el mismo orden, con tres campos:
--     que         nombre de la huella
--     huella      md5 del estado de esa poblacion
--     poblacion   cuantos objetos entran en ese md5
--
-- 🔴 POR QUE EXISTE ESTE FICHERO, Y POR QUE SE ESCRIBIO EL 10-AGO-2026.
--   Estas seis formulas NO estaban en el repo: vivian en una conversacion. El
--   9-ago-2026 se verifico staging con ellas y se anotaron los numeros de
--   control con los que habia que contrastar produccion al dia siguiente:
--       columnas 8be441ff…  indices 413cb344…  restricciones 4380d0c4…
--       def_vistas 2e4c0764…
--   El 10-ago por la mañana se perdio uno de los chats del portatil, y quedo a
--   la vista lo que eso significaba: **cuatro cifras sin instrumento**. Un md5
--   que nadie puede volver a calcular no es un ancla, es un numero bonito.
--   Es el mismo patron que ya habia mordido dos veces esa misma semana --
--   `v_amazon_se_despierta` viviendo solo en la base, las politicas de storage
--   fuera del backup -- solo que aqui el sitio efimero era una conversacion.
--       LAS ANCLAS DE UNA VERIFICACION NO PUEDEN DEPENDER DE QUE UNA
--       CONVERSACION SIGA VIVA.
--   Por eso viven aqui, en el repo, donde cualquiera puede repetir mañana la
--   verificacion de hoy.
--
-- 🔒 Y POR ESO SE ESCRIBEN UNA SOLA VEZ. Es la regla que ya documenta
--   `sql/huella_acl.sql` y que aqui aplica igual:
--       UNA HUELLA QUE SE CALCULA CON DOS CODIGOS NO ES UNA HUELLA.
--   Con dos formulas, dos md5 distintos no prueban NADA aunque el estado sea el
--   mismo: basta otro separador, otro orden o otro texto para el NULL. Si algun
--   dia hay que cambiar una formula, cambia AQUI y se re-anclan los numeros --
--   nunca se reescribe la formula en el sitio donde se compara.
--
-- ⚠️ LA SEPTIMA HUELLA NO ESTA AQUI. La de los PERMISOS (ACL) vive en
--   `sql/huella_acl.sql` y se queda alli: la consume `restaurar-staging.yml` en
--   cada ejecucion y tiene su propio motivo de existir. Las siete juntas son la
--   foto completa de un esquema; estan en dos ficheros, no en uno, porque se
--   miran en momentos distintos.
--
-- ----------------------------------------------------------------------------
-- COMO SE RECUPERARON, Y LOS DOS DETALLES QUE NO SE PUEDEN ADIVINAR
--   Estas formulas se reconstruyeron desde la especificacion de las seis
--   poblaciones y se CONTRASTARON, una a una, contra los seis md5 conocidos.
--   Las seis reproducen exacto. Dos detalles NO estaban en la especificacion y
--   solo aparecieron midiendo contra el ancla -- se dejan escritos aqui para
--   que nadie los vuelva a adivinar:
--
--   1) `columnas`: el `string_agg` interno va `ORDER BY attnum` y con `,` de
--      separador. No es indiferente: `ORDER BY attname` da otro md5 con el MISMO
--      esquema (medido: c022a0bc… en vez de 8be441ff…), y `, ` o `|` de
--      separador dan otros dos. Y `attnum` no es un capricho: hace que la huella
--      note un cambio de ORDEN de columnas, no solo de nombres y tipos.
--
--   2) `politicas`: el testigo de un `qual`/`with_check` NULL es un GUION `-`.
--      Ni cadena vacia ni la palabra 'null'. Importa mas de lo que parece: 28 de
--      las 59 politicas de `public` tienen algun NULL ahi (medido el
--      10-ago-2026), asi que el testigo entra en casi la mitad del agregado.
--      🔴 Y sin `coalesce` NO habria huella util: en SQL `texto || NULL = NULL`,
--      con lo que esas 28 politicas se volverian NULL enteras y `string_agg` las
--      DESCARTARIA en silencio. La huella seguiria saliendo -- y estaria ciega a
--      la mitad de las politicas.
--
-- ----------------------------------------------------------------------------
-- COMO SE USA
--   · A mano / en un workflow:  psql "$URL" -At -F'|' -f sql/huellas_esquema.sql
--   · Se pega tal cual contra las dos bases y se comparan las seis filas.
--
-- 🔒 EL ORDEN ES `order by x` DENTRO DEL `string_agg`, no el de la tabla: sin el,
--   el md5 dependeria del orden en que Postgres devuelva las filas y cambiaria
--   solo. Es el mismo cuidado del veredicto de `restaurar-staging.yml`.
-- ⚠️ El `ORDER BY` sobre texto usa la intercalacion (collation) de la base. Las
--   dos bases traen la misma hoy (medido el 10-ago-2026); si algun dia una se
--   creara con otra, dos bases identicas podrian dar md5 distintos. Es el mismo
--   riesgo que el `LC_ALL` del veredicto, por otro camino.
--
-- ============================================================================
-- LAS SEIS POBLACIONES, DICHAS EN VOZ ALTA (que entra y que NO)
--   1 columnas       Relaciones de `public` (tablas 'r', particionadas 'p',
--                    vistas 'v', materializadas 'm') con sus columnas vivas
--                    (attnum>0, sin las borradas). UNA x POR RELACION: las
--                    columnas van dentro de la x, no son x cada una. Por eso
--                    `poblacion` cuenta RELACIONES.
--   2 indices        `pg_indexes` de `public`, con su definicion entera. Incluye
--                    los que respaldan una PK o un UNIQUE (a diferencia de un
--                    dump, donde esos NO salen como CREATE INDEX).
--   3 restricciones  `pg_constraint` de `public`: PK, UNIQUE, FK y CHECK, con su
--                    definicion. Es la huella de las GARANTIAS -- la que decide
--                    si un ensayo en staging demuestra algo sobre produccion.
--   4 funciones      `pg_proc` de `public`, por NOMBRE Y FIRMA. Excluye las que
--                    pertenecen a una extension (`pg_depend.deptype='e'`), que no
--                    son nuestras. ⚠️ Ese filtro HOY es inerte: no hay ninguna
--                    funcion de extension en `public` (medido el 10-ago-2026: 16
--                    funciones, mismo md5 con filtro y sin el). Se deja escrito
--                    para el dia que alguien instale una extension en `public`,
--                    que es justo el dia en que la huella empezaria a moverse
--                    sola. NO mira el cuerpo: un `CREATE OR REPLACE` que cambie
--                    la logica sin tocar la firma NO mueve esta huella.
--   5 politicas      `pg_policies` de `public`: tabla, nombre, comando, roles y
--                    las dos expresiones (`qual`, `with_check`). Es el RLS.
--                    ⚠️ `roles` se rinde tal cual lo devuelve `pg_policies`, sin
--                    reordenar; hoy las dos bases coinciden (medido).
--   6 def_vistas     `pg_views` de `public`: nombre + md5 del TEXTO de la vista.
--                    Se guarda el md5 del cuerpo, no el cuerpo, para que la
--                    salida quepa en una linea. Complementa a la 1: la 1 ve que
--                    una vista cambio de columnas, la 6 ve que cambio de logica
--                    aunque devuelva las mismas columnas.
-- ============================================================================

WITH cols AS (
  SELECT c.relkind::text                             AS rk,
         c.relname::text                             AS rel,
         a.attnum                                    AS attnum,
         a.attname::text                             AS att,
         format_type(a.atttypid, a.atttypmod)        AS tipo
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','p','v','m')
     AND a.attnum > 0
     AND NOT a.attisdropped
),
h_columnas AS (
  SELECT rk || ' ' || rel || ' ' ||
         string_agg(att || ':' || tipo, ',' ORDER BY attnum) AS x
    FROM cols
   GROUP BY rk, rel
),
h_indices AS (
  SELECT indexname || ' ' || indexdef AS x
    FROM pg_catalog.pg_indexes
   WHERE schemaname = 'public'
),
h_restricciones AS (
  SELECT conname || ' ' || pg_get_constraintdef(oid) AS x
    FROM pg_catalog.pg_constraint
   WHERE connamespace = 'public'::regnamespace
),
h_funciones AS (
  SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS x
    FROM pg_catalog.pg_proc p
   WHERE p.pronamespace = 'public'::regnamespace
     AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d
                      WHERE d.objid = p.oid AND d.deptype = 'e')
),
h_politicas AS (
  SELECT tablename || ' ' || policyname || ' ' || cmd || ' ' || roles::text || ' ' ||
         coalesce(qual, '-') || ' ' || coalesce(with_check, '-') AS x
    FROM pg_catalog.pg_policies
   WHERE schemaname = 'public'
),
h_def_vistas AS (
  SELECT viewname || ' ' || md5(definition) AS x
    FROM pg_catalog.pg_views
   WHERE schemaname = 'public'
)
SELECT t.que, t.huella, t.poblacion
  FROM (
    SELECT 1 AS orden, 'columnas'::text      AS que,
           md5(string_agg(x, '|' ORDER BY x)) AS huella, count(*) AS poblacion FROM h_columnas
    UNION ALL
    SELECT 2, 'indices',
           md5(string_agg(x, '|' ORDER BY x)),          count(*) FROM h_indices
    UNION ALL
    SELECT 3, 'restricciones',
           md5(string_agg(x, '|' ORDER BY x)),          count(*) FROM h_restricciones
    UNION ALL
    SELECT 4, 'funciones',
           md5(string_agg(x, '|' ORDER BY x)),          count(*) FROM h_funciones
    UNION ALL
    SELECT 5, 'politicas',
           md5(string_agg(x, '|' ORDER BY x)),          count(*) FROM h_politicas
    UNION ALL
    SELECT 6, 'def_vistas',
           md5(string_agg(x, '|' ORDER BY x)),          count(*) FROM h_def_vistas
  ) t
 ORDER BY t.orden;
