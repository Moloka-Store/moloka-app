-- ============================================================================
-- MIGRACIÓN 2026-07-31 · v_trackeador_cola — una fila por (asin, dominio) con el
--                        margen ya calculado y el veredicto de ataque resuelto
-- ----------------------------------------------------------------------------
-- POR QUÉ. Para decidir UN precio hoy hay que cruzar a mano v_salud_asin ×
-- v_escaparate × v_producto_amazon × monitor_analisis y TECLEAR la fórmula del
-- margen en cada consulta. Cinco cruces y una fórmula, cada vez — y ahí se cuelan
-- los errores (los tres del 25-jul salieron de reconstruir esto a mano). Esta vista
-- lo hace UNA vez.
--
-- GRANO Y ALCANCE. Conduce v_producto_amazon (1 fila/asin → 371) y cuelga el resto
-- por LEFT JOIN. Hoy es ES: v_salud_asin, monitor_* y la demanda solo tienen ES, y
-- your_price_min (el ancla del margen) vive SOLO en v_salud_asin (ES). Por eso
-- dominio='es' fijo y el escaparate se acota a 'es'. El día que salud/monitor traigan
-- IT/FR, la fórmula ya lee el fee y la comisión del país de la fila (aquí, ES) — solo
-- habrá que ensanchar el conductor. Grano (asin,'es') → 0 fan-out por construcción.
--
-- 🔒 LA FÓRMULA DEL MARGEN ES INTOCABLE (validada al céntimo el 31-jul sobre 6 ASINs):
--     base   = precio / (1 + iva_pct)              -- iva_pct es FRACCIÓN (0,21 / 0,10)
--     com    = precio * (comision_pct/100) * 1.03  -- comision_pct es PORCENTAJE (15,0)
--     benef  = base - pvd - fee - com - 0.15
--     margen = benef / precio * 100
--   El fee (keepa_fba_fee_es) y la comisión (comision_pct_keepa_es) son DEL PAÍS de la
--   fila. Si falta cualquiera → la columna va NULL, NUNCA un fallback (§2.3). Tres
--   precios: margen_hoy (a your_price_min) · margen_al_bb (a bb_precio) · margen_al_fba_min.
--   break_even = (pvd+fee+0.15) / (1/(1+iva) - com_pct/100*1.03).
--
-- VEREDICTO (Opción 2, decidida por Fernando el 31-jul). Cubos CRUDOS de margen +
--   bandera aparte, NO carve-out. Motivo: "estar ya al mínimo sin caja" y "puedo
--   igualar con un 8%" son DOS preguntas distintas (¿cuánto margen si igualo? vs ¿ya
--   estoy igualado?) y se necesitan las dos a la vez. Además, con la bandera el reparto
--   sigue siendo comprobable contra lo medido — que es lo que cazó este fallo.
--     · veredicto: CAJA_MIA · SIN_RIVAL_FBA · ATACABLE_8 (m_fba>=8) · ATACABLE_FLOJO
--       (0<=m_fba<8) · ES_COSTE_NO_PRECIO (m_fba<0) · SIN_DATOS.
--     · ya_al_minimo_sin_caja (bool): abs(your_price_min - fba_min) < 0.005 y sin caja.
--       Aísla los "no-op" (Regla 19: bajar no hace nada, es problema de ficha no de
--       precio) SIN sacarlos del cubo de atacables. `where veredicto='ATACABLE_8' and
--       not ya_al_minimo_sin_caja` = los que de verdad tienen hueco.
--   pct_lider_30d NO es la cuota de caja de Moloka: mide cuánto domina el líder sea
--   quien sea. No se renombra a nada que suene a "mi cuota".
--
-- SIN_DATOS con MOTIVO (Fernando: un null no se puede filtrar ni contar, y son casi la
--   mitad de las filas). motivo_sin_datos dice por qué no hay veredicto:
--     · SIN_STOCK      — no lo tienes (disponible 0 / sin foto de salud): nada que decidir.
--     · SIN_FOTO_KEEPA — lo tienes en stock pero no hay escaparate: no ves el mercado.
--     · SIN_COSTE      — ves el mercado pero falta fee o comisión: no puedes cerrar el margen.
--
-- DEMANDA (§2.4). LEFT JOIN OBLIGATORIO: v_demanda_asin_ultima está HOY VACÍA y la
--   vista no puede romperse por eso (§3.5: 371 filas igual, demanda a NULL). Y el
--   RANGO (fecha_desde/hasta) viaja SIEMPRE con el dato: un ratio sin su ventana engaña.
--
-- 🔴 caja_mia puede ser NULL (ganador de la caja desconocido, ~32 filas): se trata como
--   "no es mía" (atacable) para el veredicto — es el default seguro de una cola de
--   ataque y reproduce lo medido. La columna caja_mia se expone CRUDA (null = no se sabe).
--
-- 🔒 security_invoker=true, sin SECURITY DEFINER. Nace CERRADA (§4): revoke a
--    public/anon/authenticated, grant select solo a authenticated (igual que #85).
-- DESPLIEGUE: CREATE OR REPLACE VIEW (AccessShareLock), por la escalera, lock_timeout
--   corto en prod, DETRÁS de Custom Analytics, con Elena parada.
-- ============================================================================

create or replace view public.v_trackeador_cola
with (security_invoker = true) as
with prod as (
  select asin, nombre, pvd, iva_pct,
         comision_pct_keepa_es, keepa_fba_fee_es, pvd_sospechoso
  from v_producto_amazon
),
sal as (
  select asin, product_name, n_skus, disponible, t7, t30, t90,
         cobertura_dias_t7, sales_rank, your_price_min
  from v_salud_asin where marketplace = 'ES'
),
esc as (
  select asin, bb_precio, caja_mia, bb_es_fba, bb_tiempo_envio, fba_min, fbm_min,
         fba_elegibles, fbm_elegibles, pct_lider_30d, amazon_precio, amazon_disp, diagnostico
  from v_escaparate where dominio = 'es'
),
dem as (
  select asin, visitas, sesiones, conversion, buybox_ratio, periodo_desde, periodo_hasta
  from v_demanda_asin_ultima where upper(pais) = 'ES'
),
ana as (
  select distinct on (asin) asin, id, accion, precio_implicado, revisar_en
  from monitor_analisis where pais = 'ES'
  order by asin, analisis_ts desc
),
med as (
  select analisis_id, count(*) as n from monitor_resultados group by analisis_id
),
j as (
  select
    p.asin, 'es'::text as dominio, p.nombre, p.pvd, p.iva_pct, p.pvd_sospechoso,
    p.keepa_fba_fee_es as fee, p.comision_pct_keepa_es as com_pct,
    s.product_name, s.n_skus, s.disponible, s.t7, s.t30, s.t90,
    s.cobertura_dias_t7, s.sales_rank, s.your_price_min,
    e.bb_precio, e.caja_mia, e.bb_es_fba, e.bb_tiempo_envio, e.fba_min, e.fbm_min,
    e.fba_elegibles, e.fbm_elegibles, e.pct_lider_30d, e.amazon_precio, e.amazon_disp, e.diagnostico,
    (e.asin is not null) as tiene_escaparate,
    d.visitas, d.sesiones, d.conversion, d.buybox_ratio, d.periodo_desde, d.periodo_hasta,
    a.accion, a.precio_implicado, a.revisar_en, coalesce(m.n, 0) as n_mediciones
  from prod p
  left join sal s on s.asin = p.asin
  left join esc e on e.asin = p.asin
  left join dem d on d.asin = p.asin
  left join ana a on a.asin = p.asin
  left join med m on m.analisis_id = a.id
),
calc as (
  select *,
    round((your_price_min/(1+iva_pct) - pvd - fee - your_price_min*(com_pct/100)*1.03 - 0.15)
          / nullif(your_price_min,0) * 100, 2) as margen_hoy,
    round((bb_precio/(1+iva_pct) - pvd - fee - bb_precio*(com_pct/100)*1.03 - 0.15)
          / nullif(bb_precio,0) * 100, 2) as margen_al_bb,
    round((fba_min/(1+iva_pct) - pvd - fee - fba_min*(com_pct/100)*1.03 - 0.15)
          / nullif(fba_min,0) * 100, 2) as margen_al_fba_min,
    round((pvd + fee + 0.15) / nullif(1/(1+iva_pct) - com_pct/100*1.03, 0), 4) as break_even
  from j
),
vd as (
  select *,
    -- Veredicto: cubos CRUDOS de margen, sin carve-out (los at-min siguen en su cubo).
    case
      when not tiene_escaparate then 'SIN_DATOS'
      when coalesce(caja_mia, false) then 'CAJA_MIA'
      when fba_min is null then 'SIN_RIVAL_FBA'
      when margen_al_fba_min is null then 'SIN_DATOS'
      -- Corrección #87.1: sin stock no hay ataque. Un margen>=0 sin disponible NO es
      -- atacable: cae a SIN_DATOS (el motivo será SIN_STOCK). ES_COSTE (margen<0) no se
      -- toca: es problema de coste con o sin stock.
      when margen_al_fba_min >= 0 and coalesce(disponible, 0) = 0 then 'SIN_DATOS'
      when margen_al_fba_min >= 8 then 'ATACABLE_8'
      when margen_al_fba_min >= 0 then 'ATACABLE_FLOJO'
      else 'ES_COSTE_NO_PRECIO'
    end as veredicto,
    -- Bandera aparte: ya estoy al mínimo FBA y no tengo la caja (no-op de precio).
    (tiene_escaparate and not coalesce(caja_mia, false) and fba_min is not null
       and your_price_min is not null and abs(your_price_min - fba_min) < 0.005) as ya_al_minimo_sin_caja
  from calc
)
select
  asin, dominio,
  coalesce(product_name, nombre) as nombre,
  n_skus, disponible, t7, t30, t90, cobertura_dias_t7, sales_rank, your_price_min,
  bb_precio, caja_mia, bb_es_fba, bb_tiempo_envio, fba_min, fbm_min,
  fba_elegibles, fbm_elegibles, pct_lider_30d, amazon_precio, amazon_disp, diagnostico,
  margen_hoy, margen_al_bb, margen_al_fba_min, break_even, pvd_sospechoso,
  visitas, sesiones, conversion as conversion_pct, buybox_ratio as ratio_oferta_destacada,
  periodo_desde as fecha_desde, periodo_hasta as fecha_hasta,
  accion as ultima_accion, precio_implicado as precio_decidido, revisar_en, n_mediciones,
  (your_price_min is not null and precio_implicado is not null
     and abs(your_price_min - precio_implicado) < 0.005) as precio_aplicado,
  veredicto,
  ya_al_minimo_sin_caja,
  -- Por qué no hay veredicto (solo en SIN_DATOS). Prioridad: sin stock manda (no lo
  -- tienes → da igual el resto); si lo tienes, falta la foto; si la tienes, el coste.
  case
    when veredicto <> 'SIN_DATOS' then null
    when coalesce(disponible, 0) = 0 then 'SIN_STOCK'
    when not tiene_escaparate then 'SIN_FOTO_KEEPA'
    else 'SIN_COSTE'
  end as motivo_sin_datos,
  -- Prioridad del briefing (§2.7), en ESTE orden exacto:
  case
    when t30 >= 10 and t7*4.3 < t30*0.6 then 1  -- caída T7 vs T30 (NUNCA por volumen T30).
                                                -- Corrección #87.2: suelo t30>=10; por debajo
                                                -- es ruido estadístico (50 de 64 filas).
    when margen_hoy < 8 and coalesce(t7,0) > 0 then 2   -- liquidando sin querer
    when cobertura_dias_t7 < 21 then 3         -- cobertura corta
    else 4
  end as prioridad
from vd;

-- Nace cerrada (§4): revocar los grants por defecto de Supabase a cada rol y conceder
-- el mínimo. Idempotente: se re-afirma en cada aplicación.
revoke all on public.v_trackeador_cola from public, anon, authenticated;
grant select on public.v_trackeador_cola to authenticated;
