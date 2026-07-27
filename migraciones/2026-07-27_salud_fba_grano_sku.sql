-- ============================================================================
-- Migración DOS VIDAS — el grano de salud_fba pasa a (asin, marketplace, sku)
-- ----------------------------------------------------------------------------
-- Un mismo ASIN puede tener DOS SKU vivos en el mismo país (vida commingled con
-- FNSKU=ASIN + vida etiquetada) desde que Amazon obliga a etiquetar. La PK
-- (asin, marketplace) solo dejaba caber una y hacía abortar la carga.
--
-- Se aplica por la ESCALERA: staging → SQL → producción → SQL. IDEMPOTENTE:
-- re-ejecutarla no hace nada si la PK ya es la nueva. Localiza la constraint por
-- su NOMBRE REAL (no un DROP a pelo) y la sustituye.
--
-- 🔴 ORDEN (no negociable, §5 del encargo): va DESPUÉS de que la app v2 sepa
-- AGREGAR salud por (asin, marketplace) — PR moloka-app-v2 #13, fusionado. Y no
-- se aplica en PRODUCCIÓN hasta CONFIRMAR que ese #13 está DESPLEGADO (si no, la
-- app en prod seguiría sin sumar y se abriría la ventana rota).
--
-- Medido antes de escribir esto (27-jul): 0 filas con sku nulo/vacío en las dos
-- tablas y los dos entornos, así que `set not null` entra limpio.
-- ============================================================================

-- ── salud_fba (la FOTO viva; sku es NULLABLE hoy) ──────────────────────────
do $$
declare pk_name text; pk_cols text;
begin
  select conname,
         (select string_agg(attname, ',' order by array_position(conkey, attnum))
            from pg_attribute where attrelid = conrelid and attnum = any(conkey))
    into pk_name, pk_cols
    from pg_constraint
   where conrelid = 'public.salud_fba'::regclass and contype = 'p';

  if pk_cols is distinct from 'asin,marketplace,sku' then
    alter table salud_fba alter column sku set not null;
    if pk_name is not null then
      execute format('alter table salud_fba drop constraint %I', pk_name);
    end if;
    alter table salud_fba
      add constraint salud_fba_pkey primary key (asin, marketplace, sku);
    raise notice 'salud_fba: PK -> (asin, marketplace, sku)';
  else
    raise notice 'salud_fba: PK ya es (asin, marketplace, sku); nada que hacer';
  end if;
end $$;

-- ── salud_fba_historico (la PELÍCULA) ─────────────────────────────────────
do $$
declare pk_name text; pk_cols text;
begin
  select conname,
         (select string_agg(attname, ',' order by array_position(conkey, attnum))
            from pg_attribute where attrelid = conrelid and attnum = any(conkey))
    into pk_name, pk_cols
    from pg_constraint
   where conrelid = 'public.salud_fba_historico'::regclass and contype = 'p';

  if pk_cols is distinct from 'asin,marketplace,sku,snapshot_date' then
    alter table salud_fba_historico alter column sku set not null;
    if pk_name is not null then
      execute format('alter table salud_fba_historico drop constraint %I', pk_name);
    end if;
    alter table salud_fba_historico
      add constraint salud_fba_historico_pkey
      primary key (asin, marketplace, sku, snapshot_date);
    raise notice 'salud_fba_historico: PK -> (asin, marketplace, sku, snapshot_date)';
  else
    raise notice 'salud_fba_historico: PK ya incluye sku; nada que hacer';
  end if;
end $$;
