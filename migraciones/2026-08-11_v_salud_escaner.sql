-- ============================================================================
-- MIGRACIÓN 2026-08-11 · v_salud_escaner — «¿está vivo el escáner de X?»
-- ----------------------------------------------------------------------------
-- PARA QUÉ, y el porqué de que esto sea un OBJETO y no una nota en un documento.
--
-- La pregunta «¿se está escaneando este proveedor?» tiene una respuesta correcta y una
-- trampa, y la trampa es la que sale primero:
--
--   🔴 `max(fecha)` A SECAS MIENTE. Una fila de `escaner_memoria` que ya está a
--      `presente = false` **no se vuelve a tocar nunca**: el bloque de «ausentes»
--      (`moloka_escaner_nube.py`, ≈línea 1185) sólo mira las que están a `presente =
--      true`, así que una vez marcada agotada su `fecha` queda **congelada para
--      siempre**. Esa fecha vieja arrastra el máximo hacia atrás y hace parecer parado
--      un proveedor que se escanea todos los días.
--
--   ✅ LO QUE SÍ RESPONDE: `max(fecha) filter (where presente)`. Si eso avanza, el
--      escáner corre. Si no, no.
--
-- 🔬 Y no es una sutileza teórica: el 11-ago-2026 el diagnóstico de por qué «BEMS, DBLINE
--    y otros estaban parados» se hizo con `max(fecha)` a secas y **dio un hallazgo falso**
--    — DBLine/Pyramid parecía muerto desde el 1-jul y lo que pasaba es que sus 272 EAN
--    estaban agotados desde entonces, congelados. Con la medida buena, DBLINE lleva 1.554
--    EAN presentes actualizados **hoy**.
--
-- 🔑 POR ESO ESTO ES UNA VISTA Y NO UN APUNTE: una nota en un documento se olvida y el
--    siguiente que pregunte volverá a escribir `max(fecha)`. Una vista con el nombre de
--    la pregunta —«salud del escáner»— da la respuesta correcta sin que haya que saber
--    nada de todo lo anterior. La regla deja de depender de que alguien se acuerde.
--
-- CÓMO SE LEE:
--   · `presentes` / `ultima_de_presentes` / `dias` → lo que de verdad mide si corre.
--   · `tiene_director` → si NO lo tiene, que esté parado es lo NORMAL: nadie lo dispara.
--     🔬 Sólo hay 4 directores (TCG, DBLINE, HEO, OCIOSTOCK) en `reglas_director`.
--     Decir que BEMS o DINOTOYS «están parados» sin mirar esto es contar como avería lo
--     que es una ausencia de proceso.
--   · `veredicto` → junta las dos cosas, que es lo que hace la vista útil como canario:
--     **un proveedor CON director y más de 2 días de retraso es una alarma**; sin
--     director, es información.
--
-- ⚠️ LO QUE ESTA VISTA NO DICE, y conviene saberlo antes de fiarse:
--   · **No mide qué MARCAS se escanean.** `escaner_memoria.marca` escribe una constante
--     (`MARCA`, con default 'Funko') en vez de la marca de la fila, así que esa columna
--     no sirve de medida. Medido: hay EAN de Bandai y de Magic guardados como 'Funko'.
--   · **No mide si el dato es bueno**, sólo si es reciente.
--
-- 🔒 Seguridad, patrón de la casa (§4): `security_invoker`, `authenticated` sí, `anon` no.
--    🔬 `escaner_memoria` tiene RLS con políticas que dejan leer a `authenticated`, así
--    que la vista con invoker devuelve lo suyo (comprobado con `set role`).
--
-- 🔴 PERO `reglas_director` NO: es una de las 20 tablas con RLS activa y CERO políticas,
--    así que con invoker el join a ella devuelve NADA para `authenticated`. Al ensayar
--    esta vista en staging salieron los diez proveedores como «sin director», incluidos
--    los cuatro que sí lo tienen — la misma trampa que esta vista existe para evitar,
--    cometida al construirla.
--    ✅ Resuelto SIN abrir nada: si `reglas_director` se ve vacía, `tiene_director` va a
--       **NULL** y el veredicto lo dice con esas palabras. La vista prefiere confesar que
--       no sabe antes que afirmar un «sin director» falso. El día que esa tabla tenga
--       política, la columna empieza a responder sola y no hay que tocar la vista.
--    🔒 NO se le da política aquí: ese frente está congelado hasta jubilar la v1.
--
-- CIFRAS DE CONTROL del 11-ago-2026 (para el primer contraste tras aplicar):
--   TCG 3.019 presentes hoy · DBLINE 1.554 hoy · HEO 2.339 hoy · OCIOSTOCK 4.089 hoy ·
--   OSMA 933 (5 d) · ZENTRADA 229 (5 d) · BEMS 7.451 (46 d) · STOCKLIST 2.182 (33 d) ·
--   DINOTOYS 968 (55 d) · MOLOKA 173 (38 d).
--   🔒 Los cuatro CON director tienen que salir a 0 días. Si uno se va a 3+, es alarma.
-- ============================================================================

set local lock_timeout = '3s';

create or replace view public.v_salud_escaner
with (security_invoker = true) as
with m as (
  select proveedor,
         count(*)                                          as filas,
         count(*) filter (where presente)                  as presentes,
         count(*) filter (where not presente)              as agotados,
         max(fecha) filter (where presente)                as ultima_de_presentes,
         max(fecha)                                        as ultima_cualquiera
  from escaner_memoria
  where proveedor is not null
  group by proveedor
)
select
  m.proveedor,
  m.filas,
  m.presentes,
  m.agotados,
  m.ultima_de_presentes,
  -- Se expone TAMBIÉN la medida mala, a propósito, para poder compararlas de un vistazo.
  -- ⚠️ HONESTIDAD SOBRE ESTA COLUMNA: **a nivel de PROVEEDOR las dos suelen coincidir**,
  --    porque basta un solo EAN presente actualizado hoy para que el máximo sea de hoy.
  --    🔬 Comprobado: en los diez proveedores coinciden. Sólo difieren si un proveedor
  --    pasa una ronda entera sin ningún presente nuevo y sí agotados.
  --    🔑 El engaño que costó un hallazgo falso el 11-ago NO fue por proveedor: fue al
  --    agrupar POR MARCA (Pyramid agotado el 1-jul contra Funko presente hoy, dentro del
  --    mismo DBLINE). Y agrupar por marca no tiene arreglo aquí, porque esa columna
  --    guarda una constante. Se deja la comparación como red, no como la prueba.
  m.ultima_cualquiera                                       as ultima_enganosa,
  (current_date - m.ultima_de_presentes::date)              as dias,
  -- `null` = no se puede saber (la tabla está tapada por RLS); true/false = se sabe.
  case when (select count(*) from reglas_director) = 0 then null
       else (r.proveedor is not null) end                    as tiene_director,
  r.activo                                                  as director_activo,
  case
    -- 🔴 «0 filas por RLS» NO ES «0 filas porque no hay». `reglas_director` es una de las
    --    20 tablas con RLS activa y CERO políticas, así que con `security_invoker` este
    --    join devuelve NADA para `authenticated` — y sin esta rama la vista diría «sin
    --    director» de los cuatro que SÍ lo tienen, que es justo la clase de mentira
    --    silenciosa que esta vista existe para evitar.
    --    🔬 Pasó al ensayarla en staging: los diez proveedores salieron «sin director».
    when (select count(*) from reglas_director) = 0
      then '⚠️ no puedo leer reglas_director (RLS sin políticas): no sé si tiene director'
    when r.proveedor is null
      then 'sin director · que no avance es lo normal: nadie lo dispara'
    when r.activo is not true
      then 'director DESACTIVADO en reglas_director'
    when (current_date - m.ultima_de_presentes::date) <= 2
      then 'ok · al día'
    else '🔴 ALARMA · tiene director y lleva '
         || (current_date - m.ultima_de_presentes::date) || ' días sin actualizar presentes'
  end                                                       as veredicto
from m
left join reglas_director r on upper(r.proveedor) = upper(m.proveedor)
order by
  -- las alarmas arriba: con director y retrasado
  (r.proveedor is not null and coalesce(r.activo, false)
   and (current_date - m.ultima_de_presentes::date) > 2) desc,
  m.presentes desc;

comment on view public.v_salud_escaner is
  '¿Está vivo el escáner de cada proveedor? Mide con max(fecha) FILTRADO POR presente, '
  'que es lo único que responde: una fila ya agotada no se vuelve a tocar y su fecha '
  'queda congelada, así que max(fecha) a secas hace parecer parado lo que corre a diario. '
  'Expone las dos medidas para que la diferencia se vea. Cruza con reglas_director porque '
  'un proveedor SIN director no está averiado: es que nadie lo dispara. Alarma = con '
  'director y más de 2 días. NO mide qué marcas se escanean (esa columna guarda una '
  'constante). anon NO tiene acceso.';

-- Nace cerrado (§4): los objetos nuevos de `public` nacen con arwdDxtm para anon Y
-- authenticated por los DEFAULT PRIVILEGES de Supabase, y un `revoke from public` NO los
-- quita. Se revoca a cada rol por su nombre y luego el grant mínimo.
revoke all on public.v_salud_escaner from public, anon, authenticated;
grant select on public.v_salud_escaner to authenticated;
