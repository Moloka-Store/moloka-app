-- ============================================================================
-- HUELLA DE LOS PERMISOS DE `public` — UNA SOLA FÓRMULA PARA LOS DOS LADOS
-- ----------------------------------------------------------------------------
-- QUE DEVUELVE. Una fila con tres campos:
--     huella      md5 del ACL de TODAS las relaciones de `public` (tablas y vistas)
--     relaciones  cuantas son
--     con_anon    cuantas de ellas tienen permiso para `anon`
--
-- POR QUE ES UN FICHERO Y NO UNA CONSULTA PEGADA EN UN WORKFLOW.
--   El 9-ago-2026 el simulacro imprimio `d87fd756…` para staging y una consulta a
--   mano sobre la MISMA base dio `161fde22…`. Aquella vez la diferencia era real -- la
--   del workflow se midio justo tras restaurar (83 relaciones abiertas) y la de mano
--   tras reaplicar la migracion (81) -- y las dos formulas resultaron idénticas al
--   contrastarlas contra produccion: las dos dan 518f466685756b6d78ad6c84632f3ab6.
--   Pero el susto enseño lo que importa:
--       UNA HUELLA QUE SE CALCULA CON DOS CODIGOS NO ES UNA HUELLA.
--   Con dos formulas, dos md5 distintos no prueban NADA aunque el estado sea el mismo:
--   basta otro separador, otro orden o otro texto para el `(sin acl)`. Y coincidir hoy
--   es una coincidencia, no una garantia: el dia que alguien retoque una de las dos,
--   la comparacion empieza a mentir sin que nadie lo note. Es el mismo problema que el
--   `LC_ALL=C` del veredicto, por otro camino.
--   Asi que la formula vive AQUI y la consumen los dos: `restaurar-staging.yml` y
--   quien la compruebe a mano. Es el mismo patron que
--   `sql/capturar_politicas_fuera_de_public.sql`.
--
-- COMO SE USA
--   · En un workflow:   psql "$URL" -At -F'|' -f sql/huella_acl.sql
--   · A mano:           se pega tal cual contra las dos bases y se comparan las filas.
--
-- 🔒 EL ORDEN ES `order by x` DENTRO DEL `string_agg`, no el de la tabla: sin el, el
--   md5 dependeria del orden en que Postgres devuelva las filas y cambiaria solo.
-- 🔒 `(sin acl)` no es lo mismo que un ACL vacio: un `relacl` NULL significa "solo el
--   dueño, sin concesiones explicitas". Se le da un texto propio para que no se
--   confunda con nada y para que dos bases con NULL en el mismo sitio casen.
-- ⚠️ MIRA SOLO `public` y solo relaciones (tablas, particionadas, vistas y vistas
--   materializadas). Las funciones, las secuencias y las politicas tienen sus propios
--   permisos y NO entran aqui: si algun dia hacen falta, se añaden a este fichero para
--   que sigan saliendo de un solo sitio.
-- ============================================================================

SELECT md5(string_agg(t.x, '|' ORDER BY t.x))         AS huella,
       count(*)                                       AS relaciones,
       count(*) FILTER (WHERE t.tiene_anon)           AS con_anon
  FROM (
    SELECT c.relname || ' :: ' ||
           coalesce(array_to_string(c.relacl, ' | '), '(sin acl)') AS x,
           EXISTS (SELECT 1 FROM aclexplode(c.relacl) a
                    WHERE a.grantee = 'anon'::regrole)             AS tiene_anon
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r','p','v','m')
  ) t;
