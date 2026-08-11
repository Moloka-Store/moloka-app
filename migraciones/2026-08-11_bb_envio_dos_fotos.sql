-- ============================================================================
-- MIGRACIÓN 2026-08-11 (b) · bb_envio: DOS FOTOS CONSECUTIVAS, en el comentario del dato
-- ----------------------------------------------------------------------------
-- QUÉ ES ESTO Y POR QUÉ VA EN UNA MIGRACIÓN NUEVA. Sólo cambia `comment on column`. No
-- toca ni un dato, ni un permiso, ni un esquema.
--
-- 🔒 Y NO se edita el comentario dentro de `2026-08-11_v_keepa_bb_envio.sql`, que es donde
--    nació y donde daría menos trabajo. Ese fichero YA SE APLICÓ a producción, y
--    `aplicar-migracion.yml` imprimió su **sha256** en el log de Actions como rastro de qué
--    se corrió exactamente. Cambiarlo —aunque fuera sólo un comentario— rompe para siempre
--    el contraste `git show origin/main:migraciones/<fichero>.sql | sha256sum` contra aquel
--    run. Una migración aplicada es un asiento: se añade otro encima, no se reescribe.
--    Es la misma regla de la Película (§1.6), aplicada al historial de migraciones.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 🔴 EL AVISO, que es todo el contenido de esta migración.
--
--    El comentario original decía, para justificar por qué el importe no se puede tomar
--    como «lo que se pierde»: *«El importe se mueve con el stock; el error, no.»* Era un
--    argumento. **Ya no hace falta argumentarlo: hay dos medidas consecutivas.**
--
--    | | foto 10-ago | foto 11-ago | |
--    |---|---|---|---|
--    | fichas con envío       | 22 | **90** | ×4,1 |
--    | suma de `bb_envio`     | 112,94 € | **513,77 €** | ×4,5 |
--    | techo (× uds en stock) | 574,21 € | **3.288,86 €** | **×5,7** |
--
--    **Veinticuatro horas.** Nadie cambió una fórmula ni corrigió un dato: cambió qué
--    ofertas tenían envío ese día y cuánto stock había debajo.
--
--    🔑 LO QUE HAY QUE LEER DE AHÍ, dentro de seis meses igual que hoy:
--      · **Ninguna de las dos cifras es «LA» cifra.** El importe es del DÍA QUE LO MIRES.
--        Citar «3.288,86 €» sin la fecha es exactamente el error de §1.4.
--      · **El sesgo, en cambio, es ESTRUCTURAL y no se mueve**: `bb_precio` es el precio
--        pelado y el envío va aparte, así que comparar contra él subestima SIEMPRE, en las
--        dos fotos y en la que venga. Eso es lo que justifica la columna; el importe sólo
--        dice cuánto abulta hoy.
--      · Y por eso el techo se recalcula, no se copia: la consulta está abajo.
--
--    🔬 Desglose del techo de hoy (11-ago), cruzando por país con `inventario_internacional`:
--      · **ES** 34 fichas con envío, de las que **33** tienen unidades · 544 uds → 2.709,31 €
--      · **IT** 21 fichas, 10 con unidades · 64 uds → 442,84 €
--      · **FR**  9 fichas,  5 con unidades · 29 uds → 136,71 €
--      · **DE** 26 fichas, **0** con unidades → **0,00 €** (seguimos con cero uds en Alemania)
--    ⚠️ Ojo al detalle que se cuenta mal solo: «34 casos» en ES son fichas CON ENVÍO, no
--       fichas que aporten euros. Una de ellas está a cero unidades y no suma nada.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- DESPLIEGUE. `comment on column`: no toca datos, no toma locks de escritura, instantáneo.
-- ============================================================================

set local lock_timeout = '3s';

comment on column public.keepa_escaparate.bb_envio is
  'Lo que el dueño de la caja cobra de envío APARTE del precio. bb_precio + bb_envio = '
  'precio puesto en casa, que es lo que paga el cliente. Sale del crudo de Keepa. '
  '🔴 EL IMPORTE ES DEL DÍA QUE LO MIRES, y no es una advertencia teórica: en 24 horas pasó '
  'de 22 fichas / 112,94 € (foto 10-ago) a 90 fichas / 513,77 € (foto 11-ago), y el techo '
  'cruzado con el stock por país, de 574,21 € a 3.288,86 € — ×5,7 sin que nadie tocara una '
  'fórmula. Lo que NO se mueve es el sesgo: comparar contra bb_precio pelado subestima '
  'SIEMPRE. El sesgo justifica la columna; el importe sólo dice cuánto abulta hoy, y se '
  'RECALCULA, nunca se cita de memoria.';

comment on column public.keepa_escaparate.bb_pais_envio is
  'Desde qué país envía el dueño de la caja. NO se pinta todavía: ver bb_plazo_txt.';

comment on column public.keepa_escaparate.bb_plazo_txt is
  'Plazo de envío del dueño de la caja, tal cual lo da Keepa (texto: "1 dia", "190 días"). '
  '⚠️ NO se pinta como señal: hay fichas con plazo y con bb_precio a NULL, y no se sabe por '
  'qué. Guardar el dato sí; convertirlo en señal, cuando se entienda ese NULL.';

-- Los tres campos existen también en el histórico, y allí la serie arranca el 10-ago:
-- lo anterior está a NULL a propósito (su `crudo` ya no está; el dato vive en los CSV de
-- Storage). El 10-ago se completó con la excepción única de moloka-app#154.
comment on column public.keepa_escaparate_hist.bb_envio is
  'Serie histórica del envío de la caja. ARRANCA EL 10-ago-2026: lo anterior está a NULL a '
  'propósito, porque el crudo de esas fotos ya no está en la base (vive en los CSV de '
  'Storage). Un 0 aquí en fechas viejas significa "no se copió", NUNCA "no había envío".';


-- ── VERIFICACIÓN / cómo se RECALCULA el techo (no se copia el número) ────────
--   with uds as (
--     select asin, lower(country) dom, sum(quantity) uds
--     from inventario_internacional group by 1,2
--   )
--   select k.dominio,
--          count(*) filter (where k.bb_envio is not null) fichas_con_envio,
--          count(*) filter (where k.bb_envio is not null and coalesce(u.uds,0) > 0) con_unidades,
--          coalesce(sum(u.uds) filter (where k.bb_envio is not null), 0) uds,
--          round(coalesce(sum(k.bb_envio * u.uds) filter (where k.bb_envio is not null), 0), 2) techo_eur
--     from keepa_escaparate k
--     left join uds u on u.asin = k.asin and u.dom = k.dominio
--    group by 1 order by 1;
--
-- 🔒 Y que los comentarios quedaron puestos:
--   select c.relname, a.attname, col_description(a.attrelid, a.attnum) texto
--     from pg_attribute a join pg_class c on c.oid = a.attrelid
--     join pg_namespace n on n.oid = c.relnamespace
--    where n.nspname='public' and c.relname in ('keepa_escaparate','keepa_escaparate_hist')
--      and a.attname in ('bb_envio','bb_pais_envio','bb_plazo_txt')
--    order by 1, 2;
