-- ============================================================================
-- `activo_sin_export` → `pedido_sin_respuesta` · la alerta cambia de significado
-- porque el buzón único le cambió el suelo debajo.  19-ago-2026
-- ============================================================================
--
-- 🔴 QUÉ PASÓ. Hasta hoy `keepa_escaparate` era «lo que vendo»: el Resumen del Vendedor de
--    Keepa, 490 filas, solo los ASIN con oferta abierta. Desde el buzón único es «mi
--    catálogo»: el Visualizador con la semilla de `productos` pegada — 1.593 filas, los
--    cuatro dominios de las 401 referencias.
--
--    Con aquel suelo, `activo_sin_export` («listing Active que no sale en el export de ES»)
--    era RUIDO: el export no pretendía cubrirlos a todos, así que faltar de él no
--    significaba nada. Con el suelo nuevo pasa a significar algo concreto y útil:
--    **se lo pediste a Keepa y Keepa no lo conoce**, que es la firma de un ASIN muerto.
--
-- 🔬 MEDIDO EN PRODUCCIÓN EL 19-ago-2026, tras la primera carga del buzón único:
--      · 228 listings Active · 0 fuera de la semilla · 0 fuera de `productos`
--      · 1 sin export: B08HGXZQ7P (Funko Pop! MLS Inter Miami — Lionel Messi), que está en
--        `productos`, está Active, iba en la semilla de 402 y Keepa NO lo devolvió en
--        NINGUNO de los cuatro países.
--
-- ⚠️ ESTO CORRIGE UNA PREVISIÓN QUE ERA FALSA. El encargo del 18-ago daba por hecho que con
--    la semilla nueva «no puede existir ninguno», que la alerta se quedaría en `false` para
--    siempre y que había que RETIRARLA. La medición dice lo contrario: vale 1. No se
--    retira — se REDEFINE, que es otra cosa.
--
-- ============================================================================
-- 🔴 DE DÓNDE SALE ESTE SQL, Y POR QUÉ IMPORTA
-- ============================================================================
-- El cuerpo de la vista está copiado de `pg_get_viewdef('v_keepa_cruce', true)` EN
-- PRODUCCIÓN (19-ago-2026, 3.265 caracteres), no del fichero de migración que la creó.
--
-- 🔬 No es celo: la versión del repo (`2026-07-29_vistas_cruce_fuera_del_arranque.sql`) ya
--    NO es la que corre. Difieren en lo esencial —el `origen` de la primera rama es
--    'escaparate' y no 'keepa_escaparate'; `ean_no_confirmado` cruza con `moloka_ean_norm`
--    contra `ean_keepa_crudo`; `tarifa_discrepante` mira `productos.keepa_fba_fee_*` y no
--    `salud_fba`—. Un `CREATE OR REPLACE` escrito desde el repo habría sustituido en
--    silencio la lógica viva por una vieja, y las tres columnas habrían empezado a mentir
--    sin que nada fallara.
--
-- 🔒 REGLA: para tocar UNA rama de una vista se parte de su definición VIVA. El repo dice
--    cómo se creó, no cómo está.
--
-- ============================================================================
-- LOS DOS CAMBIOS DE LA CONDICIÓN (y solo la segunda rama del UNION se toca)
-- ============================================================================
--
-- 1) 🔴 SE EXIGE QUE ESTUVIERA EN LA SEMILLA. Sin esto, la alerta también saltaría por un
--    listing Active que NO está en `productos` — y eso es otra cosa (una ficha huérfana en
--    el Seller, que se arregla dando de alta el producto, no investigando a Keepa). Dos
--    causas bajo una alerta hacen que la alerta no diga qué hacer.
--    🔬 Hoy no hay ninguno (0 de 228), así que este filtro NO cambia el resultado de hoy:
--    cambia lo que la alerta significará el día que lo haya, que es cuando importa.
--    Lo pidió Fernando explícitamente.
--
-- 2) 🔴 SE MIRAN LOS CUATRO DOMINIOS, no solo `es`. Antes acotar a ES era correcto: solo se
--    bajaba de verdad el export español. Ahora se bajan los cuatro con la MISMA lista, así
--    que faltar solo en ES es un dato de ese mercado, y faltar en los CUATRO es el producto
--    entero desaparecido de Keepa. La alerta se queda con el segundo, que es el grave.
--
-- ============================================================================
-- EL RENOMBRADO, Y POR QUÉ NO ES COSMÉTICO
-- ============================================================================
-- `activo_sin_export` describe la condición VIEJA. Dejarlo puesto sobre la nueva es la
-- trampa de esta casa: un nombre que se queda mintiendo y que alguien leerá dentro de dos
-- meses dando por buena su descripción. Pasa a `pedido_sin_respuesta`, y el `origen` de la
-- fila igual.
-- ⚠️ Arrastra a `procesador_keepa_escaparate.py`, que la lee por su nombre — va en el MISMO
--    PR, porque aplicados por separado uno de los dos revienta.
--
-- ============================================================================
-- ESCALERA (§5) · restaurar staging → staging ensayo → staging aplicar → verificación SQL
--               → producción ensayo → producción aplicar → verificación SQL.
-- ============================================================================

-- 🔴 SIN `begin;` NI `commit;` — Y NO ES UN OLVIDO, ES UN CERROJO DEL WORKFLOW.
--    `aplicar-migracion.yml` ya envuelve el fichero en UNA transacción
--    (`--single-transaction`), y su cerrojo 4 ABORTA cualquier migración que maneje la
--    suya. El motivo es exacto: en modo ENSAYO el workflow hace `rollback` al final, así
--    que un `commit;` dentro del fichero **escribiría de verdad** y el ensayo dejaría de
--    ser un ensayo. Se descubrió aquí, en el primer intento (run 32239546538).
--    🔒 La atomicidad no se pierde: la pone el workflow, que es quien debe ponerla.

-- 🔒 TESTIGO PREVIO. No se guarda un número fijo (eso salta por el entorno, §3): se mide lo
--    que hay ANTES para poder contrastarlo, y se aborta si no hay NADA que comprobar — una
--    verificación sobre cero filas sale bien siempre.
do $$
declare n_antes int; n_activos int;
begin
  select count(*) into n_antes from v_keepa_cruce where origen = 'listing_sin_export';
  select count(distinct upper(btrim(asin))) into n_activos
    from listings_amazon where status = 'Active' and asin is not null and btrim(asin) <> '';
  raise notice 'ANTES · listings Active: % · filas listing_sin_export: %', n_activos, n_antes;
  if n_activos = 0 then
    raise exception 'ABORTA: no hay ni un listing Active. O `listings_amazon` está vacía o no '
      'se puede leer, y en los dos casos esta migración no se puede comprobar.';
  end if;
end $$;

create or replace view v_keepa_cruce as
 SELECT 'escaparate'::text AS origen,
    k.asin,
    k.dominio,
    k.titulo,
    k.tarifa_fba,
    k.bb_vendedor,
    k.bb_seller_id,
    (EXISTS ( SELECT 1
           FROM productos p
          WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND moloka_ean_norm(p.ean) IS NOT NULL)) AND NOT (EXISTS ( SELECT 1
           FROM productos p
          WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND (moloka_ean_norm(p.ean) IN ( SELECT moloka_ean_norm(e.e) AS moloka_ean_norm
                   FROM unnest(string_to_array(COALESCE(k.ean_keepa_crudo, ''::text), ','::text)) e(e)
                  WHERE moloka_ean_norm(e.e) IS NOT NULL)))) AS ean_no_confirmado,
        CASE
            WHEN k.dominio = ANY (ARRAY['es'::text, 'fr'::text, 'it'::text]) THEN (EXISTS ( SELECT 1
               FROM productos p
              WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND k.tarifa_fba IS NOT NULL AND
                    CASE k.dominio
                        WHEN 'es'::text THEN p.keepa_fba_fee_es
                        WHEN 'it'::text THEN p.keepa_fba_fee_it
                        WHEN 'fr'::text THEN p.keepa_fba_fee_fr
                        ELSE NULL::numeric
                    END IS NOT NULL AND abs(
                    CASE k.dominio
                        WHEN 'es'::text THEN p.keepa_fba_fee_es
                        WHEN 'it'::text THEN p.keepa_fba_fee_it
                        WHEN 'fr'::text THEN p.keepa_fba_fee_fr
                        ELSE NULL::numeric
                    END - k.tarifa_fba) > 0.01))
            ELSE NULL::boolean
        END AS tarifa_discrepante,
    (EXISTS ( SELECT 1
           FROM productos p
          WHERE p.activo AND btrim(p.asin) = btrim(k.asin) AND COALESCE(btrim(p.keepa_image), ''::text) = ''::text)) AND COALESCE(array_length(k.imagenes, 1), 0) > 0 AS sin_foto_curable,
        CASE
            WHEN (EXISTS ( SELECT 1
               FROM salud_fba s
              WHERE upper(s.marketplace) = upper(k.dominio))) THEN (EXISTS ( SELECT 1
               FROM salud_fba s
              WHERE btrim(s.asin) = btrim(k.asin) AND upper(s.marketplace) = upper(k.dominio) AND COALESCE(s.available, 0) > 0)) AND k.bb_seller_id IS NOT NULL AND k.bb_seller_id <> 'A2R25VOCZPEH8K'::text
            ELSE NULL::boolean
        END AS buybox_ajena_con_stock,
    NULL::boolean AS pedido_sin_respuesta
   FROM keepa_escaparate k
UNION ALL
-- ── LA RAMA REDEFINIDA · «se lo pediste a Keepa y Keepa no lo conoce» ────────
 SELECT 'pedido_sin_respuesta'::text AS origen,
    l.asin,
    NULL::text AS dominio,        -- 🔒 NULL y no 'es': ya no es de un país, es del producto
    l.item_name AS titulo,
    NULL::numeric AS tarifa_fba,
    NULL::text AS bb_vendedor,
    NULL::text AS bb_seller_id,
    NULL::boolean AS ean_no_confirmado,
    NULL::boolean AS tarifa_discrepante,
    NULL::boolean AS sin_foto_curable,
    NULL::boolean AS buybox_ajena_con_stock,
    true AS pedido_sin_respuesta
   FROM ( SELECT btrim(listings_amazon.asin) AS asin,
            max(listings_amazon.item_name) AS item_name
           FROM listings_amazon
          WHERE listings_amazon.status = 'Active'::text AND listings_amazon.asin IS NOT NULL AND btrim(listings_amazon.asin) <> ''::text
          GROUP BY (btrim(listings_amazon.asin))) l
  -- (1) ESTABA EN LA SEMILLA. Si no, es una ficha huérfana del Seller: otro problema.
  WHERE EXISTS ( SELECT 1
           FROM productos p
          WHERE p.activo AND NOT COALESCE(p.es_chase, false)
            AND upper(btrim(p.asin)) = upper(l.asin))
  -- (2) Y KEEPA NO LO DEVOLVIÓ EN NINGÚN DOMINIO.
    AND NOT (EXISTS ( SELECT 1
           FROM keepa_escaparate k
          WHERE upper(btrim(k.asin)) = upper(l.asin)));

comment on view v_keepa_cruce is
  'Cruce de keepa_escaparate contra el resto de fuentes. La rama `pedido_sin_respuesta` '
  '(antes `listing_sin_export`) dice: se pidió ese ASIN a Keepa con la semilla del buzón '
  'único y Keepa no lo devolvió en ninguno de los cuatro dominios. Firma de ASIN muerto.';

-- 🔴 LA VERIFICACIÓN, Y QUE PUEDA PONERSE ROJA. No comprueba «que haya N filas» —un número
--    fijo salta por el entorno— sino los INVARIANTES de la definición nueva. El segundo
--    salta solo si la vista se quedó con la condición vieja y aparece un ASIN que está en
--    IT/FR/DE y no en ES, que es justo lo que aquélla dejaba pasar.
do $$
declare n_fuera int; n_con_keepa int; n_ahora int; n_col int;
begin
  select count(*) into n_ahora from v_keepa_cruce where origen = 'pedido_sin_respuesta';

  select count(*) into n_col from information_schema.columns
   where table_schema = 'public' and table_name = 'v_keepa_cruce'
     and column_name = 'activo_sin_export';
  if n_col <> 0 then
    raise exception 'ABORTA: la columna `activo_sin_export` sigue existiendo. El renombrado '
      'no se aplicó y el procesador leería la vieja.';
  end if;

  select count(*) into n_fuera from v_keepa_cruce v
   where v.origen = 'pedido_sin_respuesta'
     and not exists ( select 1 from productos p
                       where p.activo and not coalesce(p.es_chase, false)
                         and upper(btrim(p.asin)) = upper(btrim(v.asin)));
  if n_fuera <> 0 then
    raise exception 'ABORTA: % filas de `pedido_sin_respuesta` con un ASIN que NO está en la '
      'semilla (activo + no chase). El filtro (1) no se aplicó.', n_fuera;
  end if;

  select count(*) into n_con_keepa from v_keepa_cruce v
   where v.origen = 'pedido_sin_respuesta'
     and exists ( select 1 from keepa_escaparate k
                   where upper(btrim(k.asin)) = upper(btrim(v.asin)));
  if n_con_keepa <> 0 then
    raise exception 'ABORTA: % filas de `pedido_sin_respuesta` con ficha de Keepa en algún '
      'dominio. El filtro (2) no se aplicó — la vista sigue mirando solo `es`.', n_con_keepa;
  end if;

  raise notice 'DESPUES · filas pedido_sin_respuesta: %', n_ahora;

  -- 🔒 La mitad que se olvida (§3, «las dos direcciones»): que la alerta no se haya quedado
  --    MUDA. Con cero filas los tres asserts de arriba pasan tan contentos.
  if n_ahora = 0 then
    raise warning 'La alerta `pedido_sin_respuesta` devuelve CERO filas. Puede ser cierto '
      '(Keepa devolvió todo lo pedido), pero compruébalo: el 19-ago-2026 valía 1. Cero es '
      'también lo que devolvería una condición rota.';
  end if;
end $$;

