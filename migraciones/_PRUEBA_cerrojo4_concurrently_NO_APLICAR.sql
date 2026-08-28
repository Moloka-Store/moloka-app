-- ============================================================================
-- FIXTURE - NO ES UNA MIGRACION. Existe para HACER SALTAR el cerrojo 4.
-- ----------------------------------------------------------------------------
-- El 28-ago-2026 el cerrojo 4 paso a mirar el SQL de nivel superior en vez del
-- fichero crudo. Relajar un cerrojo es facil; lo que hay que demostrar es que
-- DESPUES sigue cazando lo suyo. Este fichero es esa demostracion: tiene un
-- CONCURRENTLY de verdad, a nivel superior, y el cerrojo TIENE que abortar.
--
-- 🔴 SI ESTE FICHERO PASA EL CERROJO, EL CERROJO MIENTE.
--
-- Lleva ademas, a proposito, las tres formas que NO deben disparar nada, para
-- que el fixture distinga: un comentario, un cuerpo y una cadena.
-- Se llama `_PRUEBA*` porque el cerrojo 6 prohibe esos nombres contra
-- produccion: ni en ensayo, ni con confirmacion.
-- ============================================================================

-- concurrently en un comentario: NO debe disparar
create table if not exists public.zz_fixture_cerrojo4 (a int);

do $cuerpo$
begin
  -- concurrently dentro de un cuerpo: NO debe disparar
  refresh materialized view concurrently public.zz_no_existe;
end
$cuerpo$;

select 'concurrently dentro de una cadena: NO debe disparar'::text;

-- Y esta si: CONCURRENTLY de verdad, a nivel superior.
create index concurrently if not exists zz_fixture_cerrojo4_idx on public.zz_fixture_cerrojo4 (a);
