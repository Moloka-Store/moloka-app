-- ===========================================================================
-- LA HUELLA DEL CONTENIDO de las cuatro tablas-FOTO, para demostrar que un
-- cambio en la cañería NO mueve ni un dato.
-- ===========================================================================
--
-- 🔴 EL PROBLEMA QUE RESUELVE, y lo planteó Fernando el 21-ago-2026 mejor de lo que estaba
--    escrito: **un cambio INERTE no se puede verificar por su resultado.** Si el cambio no
--    mueve nada, la pantalla sale igual esté bien o mal, y «no ha cambiado nada» significa
--    las DOS cosas a la vez: que funciona y que no se ha ejecutado. Es el mismo cero de
--    siempre por otra puerta.
--
-- 🔑 LA SALIDA SON DOS COLUMNAS, Y HACEN FALTA LAS DOS:
--      · `huella`  — md5 del CONTENIDO, **excluyendo la columna de reloj**. Si no cambia,
--                    el cambio es inerte sobre el dato.
--      · `reloj`   — esa misma columna de reloj, que SÍ se mira aparte. Si se ha movido,
--                    el procesador CORRIÓ. Es lo que separa «funciona» de «no se ejecutó».
--    Una sola de las dos no contesta la pregunta. Con las dos, sí.
--
-- 🔒 SE CALCULA DESDE AQUÍ Y DE NINGÚN OTRO SITIO. Dos consultas de huella que hoy
--    coinciden es una coincidencia, no una garantía: el día que alguien retoque una, la
--    comparación empieza a mentir sin que nadie lo note. Es la regla del `LC_ALL=C`.
--
-- 🔒 SE ORDENA POR EL PROPIO CONTENIDO (`order by x`) y no por la PK: así no hace falta
--    conocer la clave de cada tabla y el resultado es estable entre bases que no comparten
--    los mismos identificadores — que es justo el caso de staging contra producción.
--
-- ⚠️ CADA TABLA TIENE SU COLUMNA DE RELOJ Y NO SE LLAMAN IGUAL:
--      salud_fba · paneu_aptos · listings_amazon  → `procesado_en`
--      inventario_internacional                   → `procesado_at`
--    Excluir la que no es deja la huella dependiendo de la hora: cambiaría siempre y la
--    comparación no probaría nada.
--
-- ── CÓMO SE USA ────────────────────────────────────────────────────────────
--   1. Se saca la huella en la base que tiene el dato hecho con el código VIEJO.
--   2. Se corre el procesador con el código NUEVO sobre EL MISMO FICHERO en la otra base.
--   3. Se saca la huella allí. Iguales + reloj movido = el cambio es inerte y se ejecutó.
--
-- 🔬 ESTRENADA EL 21-ago-2026 con el paso a `QUOTE_NONE` de los cuatro TSV:
--      inventario_internacional  514adda27e7d64f8da95f212bc7b3612  ✅ idéntica
--      listings_amazon           385a1c9a6582405075b01579cce19745  ✅ idéntica
--      paneu_aptos               98ae0ad3aab17fcdc9fed854d72d88c3  ✅ idéntica
--    La de paneu es la más fuerte de las tres: staging partía de OTRA huella
--    (21794bd669b513769c0a77d997d177fb, 384 filas del fichero anterior) y acabó
--    exactamente en la de producción, 400 filas. Ahí no hay ninguna duda de que corrió.
-- ===========================================================================

select 'salud_fba' as tabla, count(*) as filas,
       md5(string_agg(x, '|' order by x)) as huella,
       max(reloj)::text as reloj
  from (select (to_jsonb(t) - 'procesado_en')::text as x, t.procesado_en as reloj
          from public.salud_fba t) z
union all
select 'paneu_aptos', count(*), md5(string_agg(x, '|' order by x)), max(reloj)::text
  from (select (to_jsonb(t) - 'procesado_en')::text, t.procesado_en
          from public.paneu_aptos t) z(x, reloj)
union all
select 'inventario_internacional', count(*), md5(string_agg(x, '|' order by x)), max(reloj)::text
  from (select (to_jsonb(t) - 'procesado_at')::text, t.procesado_at
          from public.inventario_internacional t) z(x, reloj)
union all
select 'listings_amazon', count(*), md5(string_agg(x, '|' order by x)), max(reloj)::text
  from (select (to_jsonb(t) - 'procesado_en')::text, t.procesado_en
          from public.listings_amazon t) z(x, reloj)
order by 1;
