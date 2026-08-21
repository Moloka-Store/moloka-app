-- ===========================================================================
-- «NUNCA HE MANDADO ESTO A FBA» · el suelo de la historia, en el dato
-- ===========================================================================
--
-- 🔴 QUÉ RESUELVE. La regla del PRIMER ENVÍO manda el almacén entero, y hasta hoy se
--    disparaba con «este producto no tiene fila en el informe Pan-EU». Eso es una propiedad
--    del CALENDARIO DE DESCARGAS, no del negocio: el mismo producto perdía la regla —y con
--    ella 289 unidades sobre 730— por el simple hecho de que alguien cargara un informe.
--    Lo que Fernando quiere decir con «primer envío» es del pasado: *nunca he mandado esto
--    a FBA*. Y eso no depende de informes ni de fichas, sino de historia.
--
-- ── LO QUE ESTA MIGRACIÓN CREA ─────────────────────────────────────────────
--   1. `productos.historia_previa_desconocida` — el SUELO de lo que podemos saber.
--   2. `v_nunca_enviado_fba` — la respuesta, calculada donde viven los datos.
--
-- ── 1 · POR QUÉ HACE FALTA MARCAR EL SUELO ─────────────────────────────────
-- 🔬 MEDIDO el 21-ago-2026, y es la razón de ser de la columna. Las tres fuentes que saben
--    de historia tienen FONDO, y ninguna llega al principio del negocio:
--      transacciones (pedidos)   desde 2026-01-01
--      ledger_movimientos        desde 2026-04-23
--      salud_fba_historico       desde 2026-07-22   ← sólo 26 días
--    Un producto vendido y agotado antes de esas fechas no aparece en ninguna, y la
--    condición lo llamaría «nunca enviado» siendo falso.
--
-- 🔬 Y EL CATÁLOGO TIENE UN SUELO PROPIO, más alto todavía: **202 de los 470 productos
--    tienen `created_at` = 2026-04-29 exacto** — la carga inicial de la tabla. Para ésos, lo
--    que pasara antes NO ESTÁ EN NINGUNA DE NUESTRAS FUENTES. Los otros 268 entraron después
--    y su historia sí está entera.
--
-- ⚠️ POR QUÉ UNA COLUMNA Y NO UNA FECHA CALCULADA (decisión de Fernando, y es la buena):
--    · No se mueve. Es un hecho escrito UNA VEZ; una comparación contra `created_at` se
--      recalcularía sola el día que alguien recargue el catálogo o toque esa columna.
--    · Cubre a los 202, no a los 9 que hoy van por la regla. Mañana entrará otro del mismo
--      lote y una lista corta no lo tendría.
--    · Y NO ES PARA ESTA REGLA. «¿Ha vendido alguna vez?», «¿cuánto lleva parado?», «¿es
--      nuevo?» tienen todas el mismo suelo y todas van a tropezar con él. En el dato, la
--      próxima pregunta no lo redescubre.
--
-- 🔒 Y un aviso contra el atajo obvio: comparar `created_at > '2026-01-01'` NO distingue
--    nada — `created_at` arranca el 29-abr, DESPUÉS que las transacciones, así que la
--    comparación da `true` para los 470. Sería una comprobación que no puede fallar.
--
-- ── 2 · LA VISTA ───────────────────────────────────────────────
-- 🔑 CUATRO FUENTES, PORQUE NINGUNA SOLA BASTA. 🔬 Medido el 21-ago-2026 sobre los 117
--    productos activos con stock propio: **60 no aparecen en `salud_fba_historico`** — y de
--    ésos **8 SÍ han estado en FBA**. Siete los caza el ledger; al octavo (`B0D6CN1884`) no
--    lo caza ni el ledger, sólo sus 18 unidades vendidas. Con una sola fuente, esos ocho
--    serían «nunca enviado» — y la regla les mandaría el almacén entero.
--
--    | fuente | qué prueba | arranca |
--    |---|---|---|
--    | `salud_fba_historico` | ha habido inventario en FBA | 22-jul-2026 |
--    | `ledger_movimientos`  | Amazon movió unidades suyas | 23-abr-2026 |
--    | ventas (`transacciones_movimientos` × `listings_amazon`) | se vendió por Amazon | 1-ene-2026 |
--    | `envios_fba`          | **nosotros lo mandamos** | 2-may-2026 |
--
-- 🔒 EL CERO DE `envios_fba` ESTÁ MEDIDO, NO ES CIEGO: hoy rescata **0 de los 52**, pero
--    casa con **42 de los 117**, o sea que el cruce funciona y lo que dice es que sus 182
--    ASIN ya estaban cazados por las otras tres. Entra igual porque es la única que
--    responde LITERALMENTE a la pregunta — las otras tres son consecuencias — y porque el
--    día que el ledger llegue tarde, es la que queda.
-- ⚠️ Y NO SE FILTRA POR `estado`: la columna dejó de mantenerse el 20-may-2026 y hoy hay
--    **228 de 260 filas atascadas en `preparado`** contra 32 en `enviado`. Filtrar por
--    «enviado» dejaría la fuente viendo sólo tres semanas de mayo. (Es un hallazgo suelto,
--    no de esta migración: la pestaña v1 dejó de marcar los envíos como enviados.)
--
-- 🔬 UNA QUINTA SE MIDIÓ Y SE DESCARTÓ: `movimientos` conoce **292 ASIN** con movimiento
--    de FBA y rescata **0 de los 52**. Se queda fuera porque para detectarlo hay que casar
--    TEXTO (`tipo/motivo/ubicacion ilike '%fba%'`) y eso es justo el tipo de ancla que se
--    pudre; las otras cuatro son estructurales. Las CINCO coinciden en los mismos 52.
--
-- ADITIVA E INERTE sobre lo que ya hay: la columna nace en `false` para todos y luego se
-- marca el lote; la vista es nueva y no sustituye a nada.
-- ===========================================================================

do $$
declare
  antes_filas  bigint;
  antes_cols   int;
  despues_cols int;
  marcados     bigint;
  esperados    bigint;
begin
  select count(*) into antes_filas from public.productos;
  select count(*) into antes_cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'productos';

  -- Cuántos DEBERÍA marcar, calculado ANTES de tocar nada. 🔒 Se mide contra el propio
  -- dato y no contra un número escrito a mano: si el lote cambia de tamaño, la guarda
  -- sigue midiendo lo que dice medir en vez de dar un rojo por el número equivocado.
  select count(*) into esperados
    from public.productos where created_at::date = date '2026-04-29';

  alter table public.productos
    add column if not exists historia_previa_desconocida boolean not null default false;

  update public.productos
     set historia_previa_desconocida = true
   where created_at::date = date '2026-04-29'
     and historia_previa_desconocida is distinct from true;

  comment on column public.productos.historia_previa_desconocida is
    'El producto vino en la CARGA INICIAL del catálogo (created_at = 2026-04-29): lo que '
    'pasara con él antes de esa fecha no está en ninguna de nuestras fuentes. Las tres que '
    'saben de historia tienen fondo — transacciones 1-ene-2026, ledger 23-abr-2026, '
    'salud_fba_historico 22-jul-2026 — y el negocio es anterior. Con esto a true, una '
    'respuesta como «nunca ha ido a FBA» NO SE PUEDE AFIRMAR: se aplica igual, pero queda '
    'constancia de que ahí no lo sabemos. Escrito una vez el 21-ago-2026 sobre 202 de 470 '
    'productos; no se recalcula.';

  select count(*) into despues_cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'productos';
  select count(*) into marcados
    from public.productos where historia_previa_desconocida;

  -- 🔒 GUARDA 1 · una columna más, no dos. Se compara ANTES contra DESPUÉS, no contra un
  --    número fijo: el invariante es «se ha añadido una».
  if despues_cols <> antes_cols + 1 then
    raise exception 'Se esperaba UNA columna más (antes %, después %).', antes_cols, despues_cols;
  end if;

  -- 🔒 GUARDA 2 · no se ha creado ni borrado ninguna fila. Es aditiva.
  if (select count(*) from public.productos) <> antes_filas then
    raise exception 'El número de filas ha cambiado (antes %).', antes_filas;
  end if;

  -- 🔒 GUARDA 3 · se ha marcado EXACTAMENTE el lote, ni uno más ni uno menos.
  if marcados <> esperados then
    raise exception 'Marcados % y el lote del 29-abr son %.', marcados, esperados;
  end if;

  -- 🔒 GUARDA 4 · y el marcado DISCRIMINA. Si marcase a todos, la columna no diría nada y
  --    sería una comprobación que no puede fallar disfrazada de dato.
  if marcados = 0 or marcados = antes_filas then
    raise exception 'La marca no discrimina: % de % filas.', marcados, antes_filas;
  end if;

  raise notice 'OK · % filas intactas, columna añadida (% -> %), % marcadas de %.',
    antes_filas, antes_cols, despues_cols, marcados, antes_filas;
end $$;

-- ---------------------------------------------------------------------------
-- LA VISTA · ¿ha estado este ASIN en FBA alguna vez, hasta donde sabemos?
-- ---------------------------------------------------------------------------
-- 🔒 `security_invoker` como sus hermanas (`v_presencia_pais`, `v_velocidad_ventas_paneu`):
--    quien consulta ve lo que sus permisos le dejan ver, no los del dueño.
-- 🔒 Y las CUATRO fuentes están comprobadas (21-ago-2026): RLS activa CON política, y
--    `authenticated` las lee. Sin eso la vista diría «nunca enviado» de todo — que es
--    justo el falso que la regla del primer envío convierte en «manda el almacén entero».
--    Ninguna de las cuatro está en la lista de tablas tapadas de `sql/canario_rls.sql`.
create or replace view public.v_nunca_enviado_fba
with (security_invoker = true) as
with cat as (
  -- Un ASIN puede venir de varias fichas. Si CUALQUIERA de ellas es del lote inicial, la
  -- historia del ASIN es incierta: basta una para no poder afirmar «nunca».
  select btrim(asin) as asin,
         bool_or(historia_previa_desconocida) as incierta
    from public.productos
   where asin is not null and btrim(asin) <> ''
   group by 1
),
vistos as (
  -- Cualquiera de las cuatro basta para decir «este ASIN YA ha estado en FBA».
  select distinct btrim(asin) as asin
    from public.salud_fba_historico where asin is not null
  union
  select distinct btrim(asin)
    from public.ledger_movimientos where asin is not null
  union
  select distinct btrim(la.asin)
    from public.transacciones_movimientos t
    join public.listings_amazon la on btrim(la.seller_sku) = btrim(t.sku)
   where t.tipo_norm = 'pedido' and la.asin is not null
  union
  -- ⚠️ `jsonb_typeof` no es adorno: `jsonb_array_elements` revienta si una fila trae un
  --    objeto en vez de una lista, y esa columna la escribe la v1.
  select distinct btrim(li->>'asin')
    from public.envios_fba ef,
         lateral jsonb_array_elements(
           case when jsonb_typeof(ef.productos) = 'array' then ef.productos else '[]'::jsonb end) li
   where li->>'asin' is not null and btrim(li->>'asin') <> ''
)
select c.asin,
       (v.asin is null) as nunca_enviado,
       -- 🔑 EL SUELO VIAJA CON LA RESPUESTA, no aparte. `nunca_enviado = true` con
       --    `historia_incierta = true` significa «no consta que se enviara», NO «no se
       --    envió». Son dos cosas distintas y quien consulte tiene que poder separarlas sin
       --    ir a buscar otra tabla — la app las separa: con la historia incierta NO aplica
       --    la regla nueva y se queda con la de siempre.
       c.incierta as historia_incierta
  from cat c
  left join vistos v on v.asin = c.asin;

comment on view public.v_nunca_enviado_fba is
  '¿Este ASIN ha estado en FBA alguna vez, HASTA DONDE SABEMOS? Alimenta la regla del '
  'primer envío (mandar el almacén entero) y cualquier otra pregunta histórica. Junta las '
  'CUATRO fuentes que saben de historia porque ninguna sola basta: medido el 21-ago-2026, '
  'de los 60 productos con stock que no están en salud_fba_historico, OCHO sí habían '
  'estado en FBA (7 por el ledger, 1 sólo por sus ventas). `historia_incierta` dice si el '
  'producto viene de la carga inicial del catálogo: con ella a true, `nunca_enviado` '
  'significa «no consta», no «no pasó».';

-- 🔴 REVOCAR ANTES DE CONCEDER: en `public` un objeto nuevo puede nacer con permisos para
--    `anon`, y un `grant` encima no quita nada. Se revoca a cada rol por su nombre.
revoke all on public.v_nunca_enviado_fba from public, anon, authenticated;
grant select on public.v_nunca_enviado_fba to authenticated;
