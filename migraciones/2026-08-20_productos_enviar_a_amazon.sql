-- ============================================================================
-- `productos.enviar_a_amazon` · el interruptor que lleva cuatro chats sin hacerse
-- ============================================================================
--
-- 🔴 POR QUÉ NO SE HABÍA HECHO, que es la parte interesante. El Drawer YA tiene un
--    interruptor llamado «Disponible para Amazon» (`Drawer.tsx:442`)… enchufado a `es_chase`,
--    que es otra cosa. Y lleva encima un comentario que dice «NO SE CABLEA» con una decisión
--    de Fernando del 13-ago. Quien coge el encargo lee eso, ve que tiene razón, y lo deja.
--    Cuatro veces. El interruptor no estaba pendiente: estaba **enchufado al campo
--    equivocado**, y el aviso protegía el cable malo.
--
-- 🔒 EL DEFAULT HACE EL DESPLIEGUE INERTE. `not null default true`: todas las fichas nacen
--    disponibles, así que al aplicar esto NO cambia ni una fila de ninguna pantalla. La
--    pestaña «Enviar» solo empezará a filtrar cuando Fernando marque algo a mano.
--
-- 🔒 Y SOLO LA PESTAÑA ENVIAR LO MIRA. Ni el Cockpit, ni Reponer, ni el trackeador, ni los
--    envíos. Es una decisión comercial de Fernando sobre qué mandar a FBA — no toca
--    identidad, ni ASIN, ni cruces, ni stock, ni la operativa de Elena.
--
-- 🔒 ADITIVA: `ADD COLUMN IF NOT EXISTS`. El ACL se comprueba por INVARIANTE (mismo antes y
--    después), no por un número fijo de privilegios — un recuento fijo daría rojo en staging
--    por el alcance del backup y no por la migración (CLAUDE.md §3).
-- ============================================================================

do $$
declare
  v_acl_antes text;
  v_acl_despues text;
  v_filas bigint;
  v_false bigint;
begin
  select coalesce(array_to_string(relacl, '|'), '(sin acl)') into v_acl_antes
  from pg_class where oid = 'public.productos'::regclass;
  select count(*) into v_filas from public.productos;

  alter table public.productos
    add column if not exists enviar_a_amazon boolean not null default true;

  comment on column public.productos.enviar_a_amazon is
    'Decisión de Fernando: ¿esta referencia se manda a FBA? `false` la saca de la pestaña '
    '«Enviar» y de NINGUNA otra vista. No es identidad ni estado del producto: es una '
    'decisión comercial, y se cambia desde el propio Cockpit (interruptor del Drawer). '
    'Default `true` para que el despliegue sea inerte.';

  select coalesce(array_to_string(relacl, '|'), '(sin acl)') into v_acl_despues
  from pg_class where oid = 'public.productos'::regclass;

  if v_acl_antes is distinct from v_acl_despues then
    raise exception 'El ACL de productos cambio: antes [%] despues [%]', v_acl_antes, v_acl_despues;
  end if;

  -- 🔒 QUE LA COLUMNA EXISTA Y SEA INERTE. Comprobar que el `ADD COLUMN` no dio error no
  --    demuestra nada: el `IF NOT EXISTS` se traga el caso. Se exige el tipo Y que NINGUNA
  --    fila haya nacido en `false` — si alguna lo estuviera, el despliegue no sería inerte
  --    y habría que mirarlo antes de que la pestaña empiece a esconder cosas.
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'productos'
      and column_name = 'enviar_a_amazon' and data_type = 'boolean'
      and is_nullable = 'NO'
  ) then
    raise exception 'enviar_a_amazon no existe, no es boolean o admite nulos';
  end if;

  select count(*) into v_false from public.productos where enviar_a_amazon is false;
  if v_false <> 0 then
    raise exception 'Hay % fichas con enviar_a_amazon = false recien creada la columna: el despliegue NO es inerte', v_false;
  end if;

  raise notice 'productos.enviar_a_amazon lista. % filas, todas a true (despliegue inerte).', v_filas;
end $$;
