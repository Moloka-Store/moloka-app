-- ============================================================================
-- MIGRACIÓN 2026-08-10 · v_escaner_ultimo — el precio VIGENTE de cada proveedor
--   ·  §3 del encargo «Encender las columnas que ya tienen dato»
-- ----------------------------------------------------------------------------
-- PARA QUÉ. El Cockpit va a encender las columnas de reposición (€ compra, ¿lo
-- tiene?, margen de reposición, días→pedido…). La fuente es `escaner_memoria`, que
-- es lo que el escáner deja cada día de los 10 proveedores.
--
-- 🔴 POR QUÉ UNA VISTA Y NO LEERLA DIRECTA, que son dos razones y las dos matan:
--
--   1. `escaner_memoria` es un HISTÓRICO, no una foto: 🔬 46.378 filas hoy, y crece
--      cada vez que corre el escáner. La app tiene un tope defensivo de 5.000 filas.
--      No cabe, y no es que no quepa hoy: es que no puede caber por diseño.
--
--   2. Y aunque cupiera, leerla cruda sería LEER PRECIOS VIEJOS. Hay 🔬 46.257 pares
--      (ean, proveedor) y de cada uno interesa UNA fila: la más reciente. Sin ese
--      `distinct on`, un producto con seis meses de histórico trae seis precios y el
--      que gane depende del orden en que lleguen. Un precio viejo no es un precio.
--
-- Agregado a lo que la pantalla cruza —los EAN del catálogo— quedan 🔬 **957 filas**.
-- Eso sí cabe, y sobra.
--
-- 🔒 LO QUE ESTA VISTA NO HACE, A PROPÓSITO: no elige proveedor, no excluye a nadie y
--    no calcula márgenes. Da el DATO (qué precio tiene cada proveedor y de cuándo es)
--    y nada más. Las decisiones de negocio —a quién NO se le compra, quién gana por
--    precio, qué plazo tiene cada uno— viven en el código, en constantes con nombre,
--    porque cambian con una conversación y no con una migración. Meter aquí un
--    «excluye a STOCKLIST» obligaría a una migración el día que Fernando vuelva a
--    comprarle.
--
-- 🔒 `security_invoker = true`: corre con los permisos de quien consulta, que es el
--    patrón de la casa (§4). 🔬 Medido: `escaner_memoria` tiene RLS activa con política
--    de lectura para `authenticated`, así que la app la lee sin problema y la vista
--    hereda esa RLS en vez de saltársela. NO hace falta `definer` aquí — al revés que
--    en `v_presencia_pais`, donde la tabla base no dejaba entrar a nadie.
--
-- ⚠️ NOTA, no acción: 🔬 `escaner_memoria` tiene 4 políticas, 3 de ellas para `anon`.
--    Es del frente de seguridad que Fernando tiene APARCADO hasta jubilar la v1, y este
--    encargo no lo toca. Se deja dicho para que conste, no para arreglarlo aquí. Lo que
--    sí se hace es lo de siempre: esta vista nace SIN `anon`.
--
-- POR QUÉ SE FILTRA POR EL CATÁLOGO. `where exists (… productos …)` no es un capricho
-- de rendimiento: es lo que mantiene la vista pequeña y estable. Lo que el Cockpit
-- puede pintar son sus propios productos; el resto del escáner (miles de EAN de
-- catálogos de proveedor) es materia del escaneo de oportunidades, no de la reposición.
--
-- CIFRAS DE CONTROL, reproducidas ANTES del DDL (read-only, hoy):
--   · 957 filas · 10 proveedores · 393 ASIN del catálogo con EAN.
--   · 383 ASIN con algún proveedor comprable y 10 sin ninguno → **383 + 10 = 393**.
--     🔒 Ésa es la invariante que hay que re-comprobar el día que se toque: si no
--     cuadra, el cruce por EAN está duplicando o perdiendo filas.
--   ⚠️ Las cifras exactas BAILAN en el mismo día (el catálogo se mueve mientras se
--     trabaja): no son criterio de aceptación, se re-miden. La invariante sí lo es.
--
-- DESPLIEGUE. `create or replace view`: AccessShareLock, instantáneo, solo lectura.
--   Por la escalera igual (staging → SQL → prod → SQL), con lock_timeout corto.
-- ============================================================================

set local lock_timeout = '3s';

create or replace view public.v_escaner_ultimo
with (security_invoker = true) as
select distinct on (m.ean, m.proveedor)
    m.ean,
    m.proveedor,
    m.pa,                       -- precio de compra del proveedor
    m.presente,                 -- 🔴 BOOLEANO: «lo tiene / no lo tiene», NO una cantidad
    m.fecha,                    -- de cuándo es ese precio: va SIEMPRE al lado del importe
    m.es_case,                  -- si el precio es de una caja, no de una unidad
    m.marca
from escaner_memoria m
where m.ean is not null
  and m.proveedor is not null
  -- Solo lo que el Cockpit puede pintar: sus productos. Ver el porqué arriba.
  and exists (
    select 1 from productos p
    where p.ean = m.ean and p.asin is not null and p.es_chase = false
  )
order by m.ean, m.proveedor, m.fecha desc, m.id desc;   -- empate del mismo día → la última cargada

comment on view public.v_escaner_ultimo is
  'El precio VIGENTE de cada proveedor para cada EAN del catálogo: la fila más reciente '
  'de escaner_memoria por (ean, proveedor). Da el dato, no la decisión: no elige '
  'proveedor ni excluye a ninguno — eso vive en el código. anon NO tiene acceso.';

-- Nace cerrado (§4): los objetos nuevos de `public` nacen con arwdDxtm para anon Y
-- authenticated por los DEFAULT PRIVILEGES de Supabase, y un `revoke from public` NO los
-- quita. Se revoca a cada rol por su nombre y luego el grant mínimo. Idempotente: hace
-- falta que se re-afirme, porque un DROP+CREATE futuro perdería el ACL.
revoke all on public.v_escaner_ultimo from public, anon, authenticated;
grant select on public.v_escaner_ultimo to authenticated;
