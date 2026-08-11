-- ============================================================================
-- MIGRACIÓN 2026-08-11 · promocionar el envío de la caja a COLUMNAS
--   ·  BLOQUEANTE del PR de `v_keepa_bb_envio`: sin esto se pierde histórico cada día
-- ----------------------------------------------------------------------------
-- EL PROBLEMA, que lo cazó Fernando y es de los que no avisan.
--
-- `keepa_escaparate_hist` **no tiene `crudo`**: el archivado lo excluye a propósito
-- (`archivar_foto(..., excluir=('crudo',))`), porque el CSV vive en Storage y duplicarlo
-- en la base costaba 25× más espacio. Decisión correcta y documentada.
--
-- 🔴 Pero tiene una consecuencia que hasta hoy no se había visto: **el envío de la caja,
--    su país y su plazo viven SÓLO dentro de ese `crudo`**. Así que cada archivado los
--    tira, y la serie histórica de esos tres campos **no existe y no puede existir**
--    mientras sigan sin columna. 🔬 Ya hay 3.784 filas archivadas en 9 fotos sin ellos.
--
-- Y no es un dato menor: es el techo de precio. 🔬 Por foto hay entre 18 y 38 cajas FBM
-- ajenas cobrando envío; poder ver esa serie es poder ver si el rival sube o baja.
--
-- ⚠️ LO YA ARCHIVADO NO SE RECUPERA CON ESTA MIGRACIÓN, y conviene decirlo sin adornos:
--    las 3.784 filas del histórico se quedan con los tres campos a NULL. 🔑 Recuperarlas
--    SÍ es posible —los CSV de Keepa siguen en `informes/keepa_escaparate/`, que es
--    archivo permanente y por eso no se borra nunca (CLAUDE.md §2)— pero es otro trabajo:
--    leer los ficheros y rellenar hacia atrás. Esta migración corta la hemorragia; el
--    rescate de lo perdido va aparte.
--
-- 🔒 POR QUÉ AHORA SÍ SE PUEDE HACER EL `ALTER TABLE`, que era la duda que bloqueaba la
--    Opción B del encargo. Ya está LEÍDO el procesador, no supuesto:
--
--        cols = [c for _, c, _ in TIPADAS] + ['bb_seller_id', 'fichero', 'fecha_foto', …]
--        sql_upsert = f"INSERT INTO keepa_escaparate ({', '.join(cols)}) VALUES %s …"
--
--    **Inserta con lista EXPLÍCITA de columnas.** Añadir columnas nuevas no le afecta:
--    las ignora hasta que se le enseñe a rellenarlas. El riesgo que hacía preferir la
--    vista —«si insertara con todas, un ALTER revienta la carga»— no existe aquí.
--    🔴 Aun así, esta migración va acompañada del cambio en el procesador EN EL MISMO PR:
--       una columna que nadie rellena es peor que no tenerla, porque parece que hay dato.
--
-- QUÉ HACE, en este orden y por una razón:
--   1. Añade las tres columnas a la tabla VIVA y al HISTÓRICO. `add column if not exists`
--      con default NULL: no reescribe la tabla y no bloquea.
--   2. RELLENA la viva desde el `crudo` que ya tiene, para que la vista no se quede a
--      cero hasta la próxima carga de Keepa.
--   3. Repunta `v_keepa_bb_envio` a las columnas en vez de al `crudo`.
--
-- CIFRAS DE CONTROL (medidas antes, read-only):
--   · `keepa_escaparate`: 494 filas, de las que **22 traen envío**, 102 plazo y 75 país.
--   · Tras el backfill, `select count(*) from keepa_escaparate where bb_envio is not null`
--     tiene que dar **22**. Ni 21 ni 23.
--   · `keepa_escaparate_hist`: 3.784 filas y las tres columnas a NULL en todas — es lo
--     esperado, no un fallo. Empezarán a poblarse con el PRÓXIMO archivado.
-- ============================================================================

set local lock_timeout = '3s';

-- 1) Las columnas. `if not exists` para que la migración se pueda repasar sin miedo.
alter table public.keepa_escaparate
  add column if not exists bb_envio      numeric,
  add column if not exists bb_pais_envio text,
  add column if not exists bb_plazo_txt  text;

alter table public.keepa_escaparate_hist
  add column if not exists bb_envio      numeric,
  add column if not exists bb_pais_envio text,
  add column if not exists bb_plazo_txt  text;

comment on column public.keepa_escaparate.bb_envio is
  'Lo que el dueño de la caja cobra de envío APARTE del precio. bb_precio + bb_envio = '
  'precio puesto en casa, que es lo que paga el cliente. Sale del crudo de Keepa.';
comment on column public.keepa_escaparate.bb_pais_envio is
  'Desde qué país envía el dueño de la caja. NO se pinta todavía: ver bb_plazo_txt.';
comment on column public.keepa_escaparate.bb_plazo_txt is
  'Plazo de envío del dueño de la caja, tal cual lo da Keepa (texto: "1 dia", "190 días"). '
  '⚠️ NO se pinta como señal: hay 31 fichas con plazo y con bb_precio a NULL, y no se '
  'sabe por qué. Guardar el dato sí; convertirlo en señal, cuando se entienda ese NULL.';

-- 2) Backfill de la VIVA desde su propio `crudo`. Sin esto, la vista se queda a cero
--    hasta la próxima carga de Keepa y parecería que el dato no existe.
--    🔒 El histórico NO se rellena: su `crudo` se tiró al archivar y no hay de dónde.
update public.keepa_escaparate
   set bb_envio      = nullif(crudo->>'Caja de Compra: Gastos de envío', '')::numeric,
       bb_pais_envio = nullif(crudo->>'Caja de Compra: País de envío', ''),
       bb_plazo_txt  = nullif(crudo->>'Caja de Compra: Tiempo de envío', '')
 where crudo is not null;

-- 3) La vista pasa a leer las COLUMNAS. Mismo contrato, misma seguridad; lo que cambia es
--    que ahora hay una serie histórica detrás en vez de un jsonb que se tira al archivar.
create or replace view public.v_keepa_bb_envio
with (security_invoker = true) as
select
    k.asin,
    k.dominio,
    k.bb_envio,
    k.bb_pais_envio,
    k.bb_plazo_txt
from keepa_escaparate k;

revoke all on public.v_keepa_bb_envio from public, anon, authenticated;
grant select on public.v_keepa_bb_envio to authenticated;


-- ── VERIFICACIÓN tras aplicar ────────────────────────────────────────────────
--   select count(*) filter (where bb_envio is not null)      as con_envio,   -- 22
--          count(*) filter (where bb_plazo_txt is not null)  as con_plazo,   -- 102
--          count(*) filter (where bb_pais_envio is not null) as con_pais     -- 75
--     from public.keepa_escaparate;
--
--   -- 🔒 Y que el backfill coincida EXACTAMENTE con lo que decía el crudo, fila a fila:
--   select count(*) as discrepancias from public.keepa_escaparate
--    where bb_envio is distinct from nullif(crudo->>'Caja de Compra: Gastos de envío','')::numeric;
--   -- tiene que dar 0
