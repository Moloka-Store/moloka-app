-- ============================================================================
-- LA HUELLA DEL ACL DE `public` — una línea por privilegio, ordenada y estable
-- ----------------------------------------------------------------------------
-- QUÉ HACE. Imprime una línea por cada privilegio concedido dentro de `public`:
-- relaciones, columnas, funciones y el propio esquema. Nada más. Quien la llama
-- ordena, hace `md5sum` y compara: si las dos huellas son iguales, las dos bases
-- dan a cada rol exactamente lo mismo; si no, el `diff` dice QUÉ cambia, que es
-- lo que hace falta para arreglarlo.
--
-- 🔑 POR QUÉ LÍNEAS Y NO SOLO UN md5. Un md5 dice «no cuadra» y ahí se acaba.
--    Estas líneas dan las dos cosas: el md5 lo calcula quien llama (`md5sum`) y
--    el `comm`/`diff` señala la relación y el rol concretos.
--
-- 🔒 SE IGNORA EL GRANTOR a propósito: importa quién puede qué, no quién lo
--    concedió. (Medido el 17-sep-2026: en producción los 3.990 privilegios de
--    `public` los concedió `postgres`; pero una restauración puede hacerla otro
--    usuario y eso no cambia los permisos efectivos.)
--
-- 🔴 GEMELO EN LA v2: `scripts/backup/huella_acl_public.sql` de
--    Moloka-Store/moloka-app-v2 es ESTE MISMO fichero, y tiene que seguir
--    siéndolo. La comparación del paso 5b NO depende de ello —el veredicto
--    calcula las dos huellas, la de staging y la de producción, con ESTA copia,
--    así que siempre compara lo mismo con lo mismo—; de lo que sí depende es de
--    que «la huella» signifique lo mismo cuando se hable de ella en un parte, y
--    de que el banco de pruebas del CI de allí mida lo que aquí se juzga. Si
--    cambias uno, cambia el otro.
--
-- Uso:
--   psql "$URL" -X -At -v ON_ERROR_STOP=1 -f huella_acl_public.sql
--   psql "$URL" -X -At -v excluir='moloka_copias,moloka_cargadores' -f …
--     · `excluir`: roles que NO se miran (los que no existen en el destino, que
--       sin esto darían rojo siempre y por una razón que no es un fallo).
--     · `excluir_rel`: relaciones que no se miran. Por defecto
--       `staging_restauraciones`, que vive SOLO en staging y no viene del backup.
-- ============================================================================

\if :{?excluir}
\else
\set excluir ''
\endif
\if :{?excluir_rel}
\else
\set excluir_rel 'staging_restauraciones'
\endif

SET search_path = public;

WITH fuera AS (
  SELECT string_to_array(:'excluir', ',')     AS roles,
         string_to_array(:'excluir_rel', ',') AS relaciones
),
lineas AS (
  SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END AS rol,
         c.relname AS relacion,
         format('r|%s|%s|%s|%s', c.relkind, c.relname,
                CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
                a.privilege_type || CASE WHEN a.is_grantable THEN '*' ELSE '' END) AS linea
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS a
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r','p','v','m','S','f')
     AND c.relacl IS NOT NULL
  UNION ALL
  SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
         c.relname,
         format('c|%s|%s|%s|%s', c.relname, at.attname,
                CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
                a.privilege_type || CASE WHEN a.is_grantable THEN '*' ELSE '' END)
    FROM pg_catalog.pg_attribute at
    JOIN pg_catalog.pg_class c ON c.oid = at.attrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(at.attacl) AS a
   WHERE n.nspname = 'public' AND at.attacl IS NOT NULL
  UNION ALL
  SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
         NULL,
         format('f|%s|%s|%s',
                format('%I.%I(%s)', 'public', p.proname,
                       pg_catalog.pg_get_function_identity_arguments(p.oid)),
                CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
                a.privilege_type || CASE WHEN a.is_grantable THEN '*' ELSE '' END)
    FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) AS a
   WHERE n.nspname = 'public' AND p.proacl IS NOT NULL
  UNION ALL
  SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
         NULL,
         format('n|public|%s|%s',
                CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
                a.privilege_type || CASE WHEN a.is_grantable THEN '*' ELSE '' END)
    FROM pg_catalog.pg_namespace n
    CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) AS a
   WHERE n.nspname = 'public' AND n.nspacl IS NOT NULL
)
SELECT l.linea
  FROM lineas l, fuera f
 WHERE NOT (l.rol = ANY (f.roles))
   AND (l.relacion IS NULL OR NOT (l.relacion = ANY (f.relaciones)))
 ORDER BY l.linea COLLATE "C";
