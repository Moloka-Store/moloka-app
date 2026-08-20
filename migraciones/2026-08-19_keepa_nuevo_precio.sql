-- ============================================================================
-- `keepa_escaparate.nuevo_precio` · el precio del MÁS BARATO, sea FBA o FBM.  19-ago-2026
-- ============================================================================
--
-- 🔴 QUÉ FALTABA. La cascada de precio del Cockpit cae, cuando nadie tiene la caja, al
--    `p3_fba_precio` — el «Nuevo, de Vendedor Externo FBA: Actual» de Keepa. Y ése es el
--    más barato **de los FBA**, que no es contra quien se compite: Moloka compite contra el
--    más barato, lo mande Amazon o lo mande el vendedor desde su casa.
--
-- 🔬 EL CASO QUE LO DESTAPÓ, medido en producción el 19-ago-2026 · `B01MYNI1W6`:
--      | dominio | bb_precio | p3_fba_precio | «Nuevo: Actual» | ofertas FBA / FBM |
--      |---------|-----------|---------------|-----------------|-------------------|
--      | it      | —         | —             | **21,92**       | 4 / 22            |
--      | de      | —         | —             | **18,65**       | 4 / 22            |
--    Nadie tiene la caja y no hay precio FBA de tercero, pero hay 22 ofertas FBM y un
--    precio de mercado. Hoy esas dos casillas salen VACÍAS en «Caja de compra» y en
--    «Margen a la caja» — y no es que no haya precio: es que se mira la columna que no es.
--
-- 🔬 LO QUE GANA, medido sobre las 1.593 filas de la foto del 19-ago:
--      | dominio | con caja | solo p3_fba | **ganan con «Nuevo»** | siguen sin precio |
--      |---------|----------|-------------|-----------------------|-------------------|
--      | es      | 321      | 43          | **29**                | 8                 |
--      | it      | 344      | 26          | **23**                | 5                 |
--      | fr      | 320      | 44          | **29**                | 3                 |
--      | de      | 323      | 23          | **42**                | 10                |
--    123 casillas de precio que hoy están en blanco y no deberían estarlo.
--
-- ⚠️ LO QUE ESTA COLUMNA **NO** TRAE, y hay que saberlo antes de usarla: **el envío**.
--    🔬 Medido sobre las claves del `crudo` de la foto real: el CSV de Keepa tiene UNA sola
--       columna de gastos de envío, `Caja de Compra: Gastos de envío` (que ya se guarda en
--       `bb_envio`). NO existe ninguna variante de «Nuevo: Actual» con el envío dentro.
--    👉 Consecuencia para la regla de la casa («el precio es el PUESTO EN CASA»): la caja
--       se puede aterrizar y este precio NO. Si el más barato es un FBM que cobra el envío
--       aparte, este número se queda corto — o sea, es CONSERVADOR para el margen (un
--       precio de referencia más bajo da un margen más bajo), que es el lado bueno por el
--       que equivocarse. Queda dicho aquí para que nadie lo lea como «puesto en casa».
--
-- 🔒 ADITIVA y sin efectos: `ADD COLUMN IF NOT EXISTS`, sin `NOT NULL` y sin default. Las
--    filas existentes se quedan a `null` hasta la siguiente pasada del procesador; una
--    columna nueva a null es «no lo sé», que es exactamente lo que se sabe de ellas.
--
-- 🔴 VA A LAS DOS TABLAS, y no es simetría gratuita: el procesador vuelca la foto en
--    `keepa_escaparate` Y apila la misma fila en `keepa_escaparate_hist` (Película). Con la
--    columna en una sola, el volcado revienta a mitad, ya con el fichero abierto — lo avisa
--    el propio procesador en su guarda de arranque. 🔬 Medido el 19-ago-2026: las dos
--    tienen 70 columnas y ninguna tiene `nuevo_precio`.
--
-- 🔒 El ACL NO se toca a propósito: `ALTER TABLE ... ADD COLUMN` conserva el de la tabla
--    (CLAUDE.md §4: el que se pierde es el de `DROP` + `CREATE`, y aquí no hay ninguno).
--    Se comprueba al final que no se ha movido.
-- ============================================================================

do $$
declare
  v_acl_antes text;
  v_acl_despues text;
  v_filas bigint;
begin
  -- 🔒 EL INVARIANTE, no una cifra: «el ACL de la tabla es el mismo antes y después». Un
  --    número fijo de privilegios daría rojo en staging por el alcance del backup, no por
  --    la migración (CLAUDE.md §3).
  select coalesce(array_to_string(relacl, '|'), '(sin acl)') into v_acl_antes
  from pg_class where oid = 'public.keepa_escaparate'::regclass;
  select count(*) into v_filas from public.keepa_escaparate;

  alter table public.keepa_escaparate add column if not exists nuevo_precio numeric;
  alter table public.keepa_escaparate_hist add column if not exists nuevo_precio numeric;

  comment on column public.keepa_escaparate_hist.nuevo_precio is
    'Keepa «Nuevo: Actual» — ver el comentario de keepa_escaparate.nuevo_precio.';

  comment on column public.keepa_escaparate.nuevo_precio is
    'Keepa «Nuevo: Actual»: el precio de la oferta NUEVA más barata, sea FBA o FBM. Es '
    'contra quien se compite de verdad cuando nadie tiene la caja. ⚠️ SIN el envío dentro: '
    'el CSV de Keepa solo trae gastos de envío para la Caja de Compra (`bb_envio`), así que '
    'si el más barato es un FBM que lo cobra aparte, este número se queda corto — '
    'conservador para el margen, que es el lado bueno por el que equivocarse.';

  select coalesce(array_to_string(relacl, '|'), '(sin acl)') into v_acl_despues
  from pg_class where oid = 'public.keepa_escaparate'::regclass;

  if v_acl_antes is distinct from v_acl_despues then
    raise exception 'El ACL de keepa_escaparate cambio: antes [%] despues [%]', v_acl_antes, v_acl_despues;
  end if;

  -- 🔒 Y que la columna EXISTE y es del tipo que se pidió: comprobar que el `ADD COLUMN` no
  --    dio error no demuestra que la columna esté; el `IF NOT EXISTS` se traga el caso.
  -- 🔒 LAS DOS, contadas: si sólo estuviera en una, el volcado fallaría a mitad y esta
  --    migración habría salido verde. Se exige 2, no «existe».
  if (
    select count(*) from information_schema.columns
    where table_schema = 'public' and table_name in ('keepa_escaparate', 'keepa_escaparate_hist')
      and column_name = 'nuevo_precio' and data_type = 'numeric'
  ) <> 2 then
    raise exception 'nuevo_precio no esta en LAS DOS tablas como numeric';
  end if;

  raise notice 'keepa_escaparate.nuevo_precio lista. Filas en la tabla: % (todas a null hasta la proxima pasada del procesador).', v_filas;
end $$;
