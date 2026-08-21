-- ============================================================================
-- `entorno()` · que cada base diga su nombre, y que no pueda mentir.  20-ago-2026
-- ============================================================================
--
-- 🔴 POR QUÉ. Hoy distinguir producción de staging es «cuenta objetos y compara»: hay que
--    acordarse de hacerlo, y una nota con la respuesta caduca. 🔬 El 20-ago-2026 la nota
--    tenía el testigo INVERTIDO (decía que staging era aarch64; es al revés) y por poco se
--    aplica una migración contra la base equivocada. Se salvó porque el número no cuadraba.
--    De los cuatro despistes de ese día por fiarse de una copia en vez de la fuente, éste
--    era el único que podía acabar escribiendo donde no toca.
--
-- 🔴 POR QUÉ DOS TESTIGOS Y NO UNO. Una tabla con el literal `'staging'` viaja en el dump
--    (`pg_dump --schema=public`), así que staging vuelve del restore diciendo
--    **'produccion'** hasta que alguien la reescriba. Si la restauración se corta entre el
--    dump y ese `UPDATE`, la base se queda haciéndose pasar por producción — mintiendo
--    hacia el lado peligroso, que es justo el fallo que no se puede permitir. Lo vio
--    Fernando.
--    👉 Por eso `entorno()` exige DOS testigos que coincidan: el literal y uno que el dump
--       NO PUEDE copiar. Si discrepan, no devuelve nada: ABORTA.
--
-- 🔑 EL SEGUNDO TESTIGO, y no es un umbral inventado. No se cuentan objetos («¿2.949 o 2?»
--    sería un número que caduca): se pregunta por un INVARIANTE que solo producción cumple —
--    **¿el Storage respalda los ficheros que la propia base dice tener?** `keepa_escaparate_hist`
--    cita ficheros CSV que en producción existen en `informes/keepa_escaparate/` (y que
--    CLAUDE.md prohíbe borrar, porque son el archivo histórico). El backup vuelca
--    `--schema=public`, así que staging vuelve SIN Storage y ese cruce da vacío.
--    🔒 Es la misma regla que protege el `DROP COLUMN crudo`: si un día ese cruce fallara en
--       producción, no sería un falso rojo — sería que se han borrado los CSV, y eso hay que
--       verlo.
--
-- 🔒 Y los DOS ceros se distinguen (la regla de `v_salud_escaner`): si el rol que llama no
--    puede leer `storage.objects`, eso NO es «soy staging» — es «no puedo comprobarlo», y se
--    dice con esas palabras en vez de devolver un veredicto que no se ha medido.
--
-- ⚠️ ESTA MIGRACIÓN SE APLICA EN LAS DOS BASES CON UN VALOR DISTINTO. Es la única de la casa
--    que no es idéntica a los dos lados: en producción escribe 'produccion' y en staging
--    'staging'. Lo resuelve leyendo el segundo testigo AL APLICAR, para que ni siquiera eso
--    dependa de que quien la lanza elija bien el entorno.
-- ============================================================================

create table if not exists public._entorno (
  id           int primary key generated always as identity check (id = 1),
  nombre       text not null check (nombre in ('produccion', 'staging')),
  escrito_at   timestamptz not null default now(),
  escrito_por  text not null default current_user
);

comment on table public._entorno is
  'El nombre de esta base, en literal. NUNCA se lee sola: se pregunta por `entorno()`, que '
  'la contrasta con un segundo testigo que el backup no puede copiar. Una sola fila (id=1).';

-- 🔒 Nace CERRADA (CLAUDE.md §4): RLS activo y cero políticas, y se REVOCA a cada rol por su
--    nombre antes de conceder nada — un `revoke ... from public` no quita los grants
--    explícitos que Supabase da por defecto a `anon` y `authenticated`.
alter table public._entorno enable row level security;
revoke all on public._entorno from public, anon, authenticated;

do $$
declare
  v_respalda boolean;
  v_nombre   text;
begin
  -- ── EL SEGUNDO TESTIGO ────────────────────────────────────────────────────
  -- ¿El Storage contiene los CSV que `keepa_escaparate_hist` dice haber procesado?
  select exists (
    select 1
    from public.keepa_escaparate_hist h
    join storage.objects o
      on o.bucket_id = 'informes'
     and o.name = 'keepa_escaparate/' || h.fichero
  ) into v_respalda;

  v_nombre := case when v_respalda then 'produccion' else 'staging' end;

  delete from public._entorno;
  insert into public._entorno (nombre) values (v_nombre);

  raise notice 'Esta base se declara: %  (el Storage respalda el histórico de Keepa: %)',
    v_nombre, v_respalda;
end $$;

-- ── LA FUNCIÓN ──────────────────────────────────────────────────────────────
-- 🔒 `security invoker` y `stable` (lee tablas, así que no puede ser `immutable`).
create or replace function public.entorno()
returns text
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  v_literal  text;
  v_respalda boolean;
begin
  select nombre into v_literal from public._entorno where id = 1;
  if v_literal is null then
    raise exception 'entorno(): la tabla _entorno esta vacia. Esta base no dice quien es.';
  end if;

  begin
    select exists (
      select 1
      from public.keepa_escaparate_hist h
      join storage.objects o
        on o.bucket_id = 'informes'
       and o.name = 'keepa_escaparate/' || h.fichero
    ) into v_respalda;
  exception when insufficient_privilege then
    -- 🔴 «No puedo leerlo» NO es «soy staging»: son dos ceros distintos y confundirlos
    --    devolveria un veredicto que nadie ha medido.
    raise exception 'entorno(): no puedo leer storage.objects con el rol %, asi que no puedo '
      'contrastar el segundo testigo. La tabla dice [%], pero eso solo no basta.',
      current_user, v_literal;
  end;

  if (v_literal = 'produccion') <> v_respalda then
    raise exception 'entorno(): LOS DOS TESTIGOS NO COINCIDEN. La tabla dice [%] y el Storage '
      '%respalda el historico de Keepa. Una restauracion a medias deja la base haciendose '
      'pasar por otra: NO se escribe aqui hasta aclararlo.',
      v_literal, case when v_respalda then '' else 'NO ' end;
  end if;

  return v_literal;
end $$;

comment on function public.entorno() is
  'Devuelve ''produccion'' o ''staging'', contrastando DOS testigos: el literal de _entorno '
  '(que viaja en el dump) y si el Storage respalda el historico de Keepa (que el dump no '
  'copia). Si discrepan, ABORTA — una restauracion cortada a medias dejaria la base '
  'haciendose pasar por produccion, que es el lado peligroso por el que mentir.';

revoke all on function public.entorno() from public, anon, authenticated;

-- ── LA COMPROBACIÓN ─────────────────────────────────────────────────────────
do $$
declare v text;
begin
  v := public.entorno();
  raise notice 'entorno() responde: %  (los dos testigos coinciden)', v;
end $$;
