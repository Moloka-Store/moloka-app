-- ============================================================================
-- GENERADOR DE `CREATE POLICY` PARA TODO LO QUE VIVE FUERA DE `public`
-- ----------------------------------------------------------------------------
-- QUE HACE. Deja una tabla temporal `moloka_politicas_fuera_public(sentencia)` con
-- el `CREATE POLICY` reconstruido de CADA politica RLS que no esta en `public`.
-- No escribe nada en la base: solo lee `pg_policies`.
--
-- POR QUE EXISTE, Y POR QUE ES UN FICHERO Y NO CODIGO PEGADO EN UN WORKFLOW.
--   El 9-ago-2026 el simulacro de restauracion (run 31299419508) descubrio que el
--   vaciado de `public` se llevaba por delante, via CASCADE, CUATRO politicas de
--   `storage.objects` -- `buzones_v2_select/insert/update/delete` --, porque su
--   clausula usa `public.moloka_buzones_fase0()`. Y el backup NO puede devolverlas:
--   se hace con `pg_dump --schema=public`, asi que las politicas de `storage` no
--   estan dentro. Aquella vez se salvaron de milagro: la restauracion fallo despues
--   por otra cosa y la transaccion entera hizo rollback.
--
--   Este fichero lo consumen DOS sitios, y por eso se escribe UNA vez:
--     · `restaurar-staging.yml` — captura las politicas ANTES de vaciar y las
--       vuelve a crear DESPUES de restaurar, dentro de la MISMA transaccion. O sea:
--       lo que el backup no cubre, el restore lo CONSERVA en vez de destruirlo.
--     · `backup-bd.yml` — para que la copia deje de tener ese agujero y las traiga
--       de verdad. Cuando eso este, el restore ya no tendra que conservar nada
--       porque sabra devolverlas, y el problema desaparece de raiz en vez de
--       taparse.
--
-- 🔒 SE RECONSTRUYE, NO SE INVENTA. Los cinco trozos de una politica salen tal cual
--   de `pg_policies`: `permissive`, `cmd`, `roles`, `qual` y `with_check`. La
--   expresion no se toca: ni una coma.
--
-- 🔴 PERO `qual` Y `with_check` NO VIENEN CUALIFICADOS -- LEER ESTO ANTES DE
--   REUTILIZAR EL FICHERO, PORQUE ES DONDE SE INCUBA EL BUG.
--   Postgres los devuelve RENDERIZADOS CON EL `search_path` DEL MOMENTO, asi que un
--   nombre que estuviera en el path cuando se creo la politica sale SIN esquema.
--   Medido el 9-ago-2026 contra produccion: en 4 de las 13 politicas,
--   `moloka_buzones_fase0()` sale desnuda (`storage.foldername()`, en cambio, sale
--   cualificada, porque `storage` no estaba en el path).
--   Lo que muerde: si capturas con un `search_path` y recreas con otro, esa expresion
--   NO RESUELVE y la politica no se puede volver a crear. Y no es hipotetico: el dump
--   hace `set_config('search_path','')` por su cuenta.
--   👉 LA REGLA: se fija el MISMO `search_path` al capturar y al recrear (hoy
--   `SET LOCAL search_path = public`), y la expresion se deja intacta. Cualificar la
--   funcion a mano en el texto seria reinterpretar una politica que no es nuestra.
--   🔴 QUIEN LLEVE ESTA PIEZA A `backup-bd.yml`: sin ese `SET LOCAL` al capturar, la
--   copia guardaria politicas QUE NO SE PUEDEN RESTAURAR -- y saldria verde. Aqui
--   vivio una frase que decia justo lo contrario ("Postgres ya las devuelve con los
--   nombres cualificados"), escrita el mismo dia en que se habia medido que no. Asi
--   es exactamente como esta casa se ha comido ya una nota que mintio diez dias.
-- 🔒 `%I` para los identificadores (aplica la regla de comillas de Postgres: solo
--   entrecomilla cuando hace falta) y los roles uno por uno con `quote_ident`, que
--   deja `public` sin tocar -- que es lo correcto para un `TO public`.
-- ⚠️ `qual`/`with_check` pueden ser NULL y entonces su clausula NO se escribe: un
--   INSERT no tiene USING y un SELECT no tiene WITH CHECK. Escribir `USING (null)`
--   seria una politica distinta.
-- ============================================================================

CREATE TEMP TABLE moloka_politicas_fuera_public AS
SELECT format(
         'CREATE POLICY %I ON %I.%I AS %s FOR %s TO %s%s%s;',
         p.policyname,
         p.schemaname,
         p.tablename,
         p.permissive,                      -- PERMISSIVE | RESTRICTIVE
         p.cmd,                             -- ALL | SELECT | INSERT | UPDATE | DELETE
         (SELECT string_agg(quote_ident(r), ', ' ORDER BY r)
            FROM unnest(p.roles) AS r),
         CASE WHEN p.qual       IS NOT NULL THEN ' USING (' || p.qual || ')'            ELSE '' END,
         CASE WHEN p.with_check IS NOT NULL THEN ' WITH CHECK (' || p.with_check || ')' ELSE '' END
       ) AS sentencia,
       p.schemaname,
       p.tablename,
       p.policyname
  FROM pg_catalog.pg_policies p
 WHERE p.schemaname <> 'public';
