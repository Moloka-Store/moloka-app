-- ============================================================================
-- CANARIO RLS · EL CHECKLIST POST-RESTORE
--   Distingue «0 filas porque no hay datos» de «0 filas porque la RLS las tapa»,
--   y grita EN LOS DOS SENTIDOS contra un censo fijado.
-- ----------------------------------------------------------------------------
-- 🔴 ESTE FICHERO ES EL PASO OBLIGATORIO DESPUÉS DE CUALQUIER RESTAURACIÓN.
--    No hay otro checklist: se buscó el de «las 8 relaciones» y no existe — se había
--    dado por hecho. Éste lo sustituye y se corre entero, no a ojo.
--
-- PARA QUÉ. Una tabla con RLS ACTIVA y CERO POLÍTICAS es invisible para la app y no
-- avisa: no da error, da vacío. Una vista que la lea con `security_invoker` devuelve 0
-- filas con la misma cara de normalidad. Es el fallo más silencioso de esta base.
--
-- 🔑 LA CLAVE, y por eso no hace falta ejecutar como `authenticated`: **RLS activa + cero
--    políticas ⟹ invisible, POR DEFINICIÓN.** Si no hay política que permita, no permite.
--    Lo único que hay que medir es CUÁNTAS FILAS HAY DENTRO, que es lo que separa «vacía»
--    (inofensivo) de «tapada» (13.781 filas que nadie ve).
--
-- ⚠️ Y POR QUÉ NO VALE MEDIRLO CON EL CONECTOR: corre como `postgres`, que tiene
--    BYPASSRLS — cuenta todo y no se entera de nada. Es la trampa que hubo que esquivar
--    al pasar `v_presencia_pais` a invoker: el conector decía 508 filas mientras la app
--    habría visto 0. Aquí se cuenta lo que hay y se DEDUCE la visibilidad del catálogo.
--
-- 🔒 NO CREA NADA y NO ARREGLA NADA: informa. Decidir qué tabla se abre y a quién es una
--    decisión de negocio, y el frente de `monitor_*` y `productos` frente a `anon` está
--    CONGELADO hasta jubilar la v1.
-- ============================================================================


-- ════════════════════════════════════════════════════════════════════════════
-- 1) EL GRITO EN LOS DOS SENTIDOS, contra el censo fijado del 11-ago-2026
-- ════════════════════════════════════════════════════════════════════════════
-- Las 20 tablas que ese día estaban tapadas Y con datos. Es la lista que hay que
-- comparar, no un recuento.
--
-- ⚠️ POR QUÉ LA LISTA Y NO LOS RECUENTOS: varias de estas tablas CRECEN solas
--    (`keepa_escaparate_hist` suma ~420 filas por foto, `salud_fba_hist` y
--    `listings_amazon_hist` igual). Fijar su recuento haría saltar el canario todos los
--    días por lo que es normal, y un canario que grita siempre se deja de leer. Los
--    recuentos van abajo como REFERENCIA fechada, para mirar de reojo si algo se ha
--    desplomado; la LISTA es el criterio.
-- 🔴 SON 21, Y ANTES ERAN 20 POR UN ERROR MIO QUE HACIA GRITAR AL CANARIO SIEMPRE.
--    El censo se armó el 11-ago-2026 con «las 20 tapadas CON DATOS DENTRO», dejando fuera
--    `web_formato` por estar vacía. Pero el censo no mide datos: mide QUÉ TABLAS ESTÁN
--    TAPADAS. Con ella fuera, cada ejecución la reportaba como **🔴 TAPADA NUEVA** — una
--    alarma permanente por diseño, que es justo como un canario se deja de leer.
--    🔬 Medido el 12-ago-2026: `web_formato` sigue con RLS on, 0 políticas y 0 filas.
--    🔑 Y la lección, que vale para cualquier censo: **estar vacía hoy no es motivo para
--       excluir nada.** Una tabla vacía puede llenarse mañana y entonces estaría tapada
--       CON datos y sin que nadie se enterara, porque ya se la había sacado de la lista.
--       «Con datos» y «tapada» son dos estadísticas distintas y no se mezclan: el recuento
--       de filas ya lo da la propia consulta, columna a columna.
with censo(tabla) as (values
  ('keepa_escaparate_hist'), ('paneu_oferta_pais'), ('inventario_internacional_historico'),
  ('listings_amazon_hist'), ('bb_observaciones'), ('paneu_aptos'),
  ('productos_backup_20260609_1525'), ('incidencias_juguetes'), ('monitor_analisis'),
  ('salud_fba_hist'), ('zentrada_captura'), ('monitor_doctrina'), ('escaner_chase_asin'),
  ('seller_observaciones'), ('ficha_observaciones'),
  ('productos_backup_consolidacion_05may2026'), ('incidencias_contador'),
  ('monitor_reponibilidad_manual'), ('reglas_director'), ('incidencias_lecturas'),
  ('web_formato')   -- vacía hoy; en el censo igual que las demás (ver arriba)
),
hoy as (
  select c.relname as tabla,
         (select count(*) from pg_policies p
           where p.schemaname='public' and p.tablename=c.relname) as politicas,
         (xpath('/row/c/text()', query_to_xml(
            format('select count(*) as c from public.%I', c.relname), false, true, '')))[1]::text::bigint as filas
  from pg_class c
  where c.relnamespace='public'::regnamespace and c.relkind='r' and c.relrowsecurity
)
select
  coalesce(h.tabla, c.tabla) as tabla,
  h.filas,
  h.politicas,
  case
    -- 🔴 SENTIDO 1: apareció una tapada que NO estaba en el censo. Casi siempre significa
    --    que una política NO ha vuelto tras un restore. Es el caso que mata en silencio.
    when c.tabla is null and h.politicas = 0 and h.filas > 0
      then '🔴🔴 TAPADA NUEVA · no estaba en el censo: ¿se ha perdido una política?'
    -- 🔴 SENTIDO 2: estaba en el censo y ahora tiene políticas. Puede ser bueno (alguien
    --    la abrió a propósito) pero hay que ENTERARSE: si no, el censo se queda mintiendo.
    when c.tabla is not null and coalesce(h.politicas, 0) > 0
      then '🟡 YA NO ESTÁ TAPADA · alguien le puso política: confírmalo y actualiza el censo'
    -- Y la tercera: estaba en el censo y ha desaparecido de la base.
    when h.tabla is null
      then '🟡 DESAPARECIDA · la tabla del censo ya no existe: actualiza el censo'
    when h.politicas = 0 and h.filas = 0 then 'vacía · tapada pero no esconde nada'
    when h.politicas = 0 then 'ok · tapada y en el censo (' || h.filas || ' filas)'
    else 'ok · con políticas'
  end as veredicto
from hoy h
full join censo c on c.tabla = h.tabla
order by
  (c.tabla is null and coalesce(h.politicas,0) = 0 and coalesce(h.filas,0) > 0) desc,  -- las nuevas primero
  (c.tabla is not null and coalesce(h.politicas,0) > 0) desc,
  h.filas desc nulls last;


-- ════════════════════════════════════════════════════════════════════════════
-- 2) RESUMEN de una línea, para pegar en el parte
-- ════════════════════════════════════════════════════════════════════════════
with hoy as (
  select c.relname,
         (select count(*) from pg_policies p where p.schemaname='public' and p.tablename=c.relname) politicas,
         (xpath('/row/c/text()', query_to_xml(
            format('select count(*) as c from public.%I', c.relname), false, true, '')))[1]::text::bigint filas
  from pg_class c
  where c.relnamespace='public'::regnamespace and c.relkind='r' and c.relrowsecurity
)
select count(*) filter (where politicas = 0)                as tablas_tapadas,
       count(*) filter (where politicas = 0 and filas > 0)  as tapadas_con_datos,
       coalesce(sum(filas) filter (where politicas = 0), 0) as filas_invisibles,
       count(*) filter (where politicas > 0)                as tablas_con_politicas
from hoy;
-- 🔬 REFERENCIA del 11-ago-2026 en producción:
--    21 tapadas · **20 con datos** (sólo `web_formato` vacía) · **13.781 filas
--    invisibles** · 39 tablas con políticas.
--    Recuentos de ese día (informativos, varias CRECEN solas):
--      keepa_escaparate_hist 3.784 · paneu_oferta_pais 3.720 ·
--      inventario_internacional_historico 1.891 · listings_amazon_hist 1.683 ·
--      bb_observaciones 623 · paneu_aptos 372 · productos_backup_20260609_1525 341 ·
--      incidencias_juguetes 291 · monitor_analisis 284 · salud_fba_hist 227 ·
--      zentrada_captura 200 · monitor_doctrina 111 · escaner_chase_asin 105 ·
--      seller_observaciones 65 · ficha_observaciones 50 ·
--      productos_backup_consolidacion_05may2026 16 · incidencias_contador 8 ·
--      monitor_reponibilidad_manual 4 · reglas_director 4 · incidencias_lecturas 2


-- ════════════════════════════════════════════════════════════════════════════
-- 3) CENSO DE VISTAS DEFINER · cuáles viven de una tabla tapada
-- ════════════════════════════════════════════════════════════════════════════
-- 🔴 Una vista definer sobre una tabla TAPADA está funcionando SOLO PORQUE es definer.
--    Pasarla a `security_invoker` la dejaría a cero filas, en silencio. Es el caso de
--    `v_presencia_pais` repetido: aquella se creó definer a propósito porque el ledger
--    tenía RLS sin políticas, y hasta que el ledger no tuvo una no se pudo cambiar.
--
-- 🔒 ESTO ES UN CENSO, NO UNA LISTA DE TAREAS. No se toca ninguna. Decidir qué hacer con
--    cada una exige saber a quién debe ver esa tabla, y eso no se decide leyendo un
--    catálogo. Lista primero, decisión después.
with tapadas as (
  select c.relname from pg_class c
  where c.relnamespace='public'::regnamespace and c.relkind='r' and c.relrowsecurity
    and not exists (select 1 from pg_policies p where p.schemaname='public' and p.tablename=c.relname)),
definer as (
  select v.oid, v.relname from pg_class v
  where v.relnamespace='public'::regnamespace and v.relkind='v'
    -- 🔴 `security_invoker` SE GUARDA DE DOS FORMAS Y LAS DOS VALEN: Postgres acepta
    --    `true` y `on` como sinónimos y almacena LITERALMENTE lo que se escribió. Este
    --    canario buscaba sólo `=true` y contaba como DEFINER cuatro vistas que sí son
    --    invoker: v_escaparate, v_factura_cuadre, v_factura_escaneo y v_salud_asin.
    --    🔬 Reparto real de las 30 vistas (12-ago-2026): 13 sin poner · 13 `true` · 4 `on`.
    --       El censo decía 18 definer. Son 13.
    --    ⚠️ Y no es un fallo de nadie en concreto: Fernando y yo escribimos el mismo
    --       `<> 'true'` por separado y los dos contamos 18. Un catálogo que admite dos
    --       escrituras del mismo valor va a seguir engañando a quien lo consulte, así que
    --       la comprobación se hace por OPCIÓN, no por texto.
    and not exists (
      select 1 from unnest(coalesce(v.reloptions, '{}')) o
      where lower(split_part(o, '=', 1)) = 'security_invoker'
        and lower(split_part(o, '=', 2)) in ('true', 'on', 'yes', '1')))
select d.relname as vista,
       -- 🔴 LA SEGUNDA CARA: ¿además la sirve `anon`, o sea SIN SESIÓN?
       has_table_privilege('anon', 'public.' || d.relname, 'select') as anon_lee,
       (select string_agg(distinct t.relname, ', ') from pg_depend dp
          join pg_rewrite rw on rw.oid = dp.objid
          join pg_class t on t.oid = dp.refobjid
         where rw.ev_class = d.oid and dp.classid = 'pg_rewrite'::regclass
           and t.relkind = 'r' and t.relname in (select relname from tapadas)) as bases_tapadas
from definer d
order by bases_tapadas nulls last, anon_lee desc, 1;
-- 🔬 REFERENCIA del 12-ago-2026: **13 vistas definer** (el censo decia 18: contaba como
--    definer las 4 con `security_invoker=on`, que SI son invoker). De esas 13, las que
--    ademas se apoyan en tabla tapada:
--      v_estado_asin, v_scoreboard_reglas, v_decisiones_estado, v_sondas_pendientes,
--      v_analisis_auditable  → monitor_analisis
--      v_incidencias_resumen, v_incidencias_movimientos, v_incidencias_ultima
--                            → incidencias_juguetes, incidencias_lecturas
--      v_auditoria_tarifas   → seller_observaciones
--      v_amazon_se_despierta → keepa_escaparate_hist
--    Las otras 8 son definer sobre tablas que sí tienen políticas: cambiarlas sería
--    inocuo, pero tampoco urge.
--
-- 🔴🔴 Y LA CAPA QUE CIERRA EL CÍRCULO: **9 de esas 10 están abiertas a `anon`** — todas
--    menos `v_estado_asin`. O sea que la RLS de `monitor_analisis`, `incidencias_*`,
--    `seller_observaciones` y `keepa_escaparate_hist` **no protege nada**: sus datos se
--    sirven SIN SESIÓN a través de vistas definer que se saltan esa misma RLS.
--
--    Son las dos caras del mismo patrón, y por eso se miran juntas: **lo único que hace
--    que esas vistas funcionen es exactamente lo que las abre.** Poner invoker las deja a
--    cero; quitar el grant a `anon` puede romper la v1, que es quien probablemente las
--    lee.
--
--    🔒 POR ESO ESTO ES CENSO Y NO UNA LISTA DE TAREAS. No se toca ninguna. Para poder
--       cerrarlas hace falta antes saber QUIÉN las lee — y eso es el censo de lectura de
--       la app v1, que es otro trabajo. Sin ese censo, cerrar una es apagar una luz sin
--       saber qué habitación deja a oscuras.
