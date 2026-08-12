-- ============================================================================
-- HUELLA DE LAS VISTAS, PARA COMPARAR UN ENTORNO CONTRA OTRO
-- ----------------------------------------------------------------------------
-- PARA QUE. El censo por objeto (`scripts/censo_migraciones.py`) dice si algo EXISTE,
-- no si esta VIGENTE. De los 61 objetos censados, **9 los tocan dos migraciones**, y en
-- esos la segunda es invisible a una comprobacion de existencia. Donde no hay huella
-- declarada en el fichero, queda este puente: **si staging y produccion dan el mismo
-- hash, las dos tienen la misma definicion**.
--
-- 🔴 ESTE FICHERO EXISTE PARA QUE LOS DOS LADOS EJECUTEN EL MISMO TEXTO. Se lanza tal
--    cual en los dos entornos y se comparan las columnas. Si cada uno escribe su propia
--    consulta, el cruce no vale nada — que es exactamente lo que paso el 12-ago-2026 y
--    costo media hora de conclusiones falsas.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ⚠️ LAS DOS TRAMPAS QUE INVALIDAN LA COMPARACION, las dos medidas ese dia:
--
--   1. **`pg_get_viewdef` CUALIFICA LOS NOMBRES SEGUN EL `search_path` DE QUIEN
--      PREGUNTA.** La MISMA vista, la MISMA base, el MISMO instante:
--          search_path = '"$user", public, extensions'  →  2.405 car · md5 5991916f…
--          search_path = ''                             →  2.433 car · md5 dc22b443…
--      Dos hashes distintos por quien pregunta. Sin fijarlo, comparar dos entornos
--      compara dos sesiones. 🔬 Asi salieron SEIS de seis vistas "distintas" que no lo
--      estaban: la señal del 100 %, que nunca es un resultado.
--
--   2. **`set_config` EN LA LISTA DEL SELECT NO SE EVALUA ANTES.** El planificador puede
--      resolver `pg_get_viewdef` primero y el pin no toma efecto — sin error, con un
--      resultado plausible. Por eso va en un CTE `MATERIALIZED`, que fuerza el orden.
--      🔒 Se pilla porque el valor no cuadra con uno ya conocido. De ahi la fila de
--         autocomprobacion del final: si esa no cuadra, no te fies de ninguna.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- ⚠️ Y LO QUE ESTE HASH NO ES: es de la definicion **normalizada por Postgres**, no del
--    texto del `.sql`. Sirve para comparar ENTORNO contra ENTORNO. **No se compara contra
--    el fichero**, y no tiene nada que ver con el sha256 que imprime
--    `aplicar-migracion.yml`, que mide otra cosa (que se aplico exactamente ese fichero).
--    Mezclarlos da conclusiones invertidas.
--
-- ⚠️ Y coincidir NO significa "las dos al dia": significa "las dos IGUALES". Si los dos
--    entornos estan viejos de la misma forma, coinciden. Lo decisivo es la DIFERENCIA.
-- ============================================================================

with pin as materialized (
    -- 🔒 MATERIALIZED no es adorno: sin el, el pin no se aplica. Ver trampa 2.
    select set_config('search_path', '', true) as s
)
select c.relname                                          as vista,
       md5(pg_get_viewdef(c.oid, true))                   as md5_definicion,
       length(pg_get_viewdef(c.oid, true))                as caracteres,
       -- 🔴 La opcion se lee POR OPCION, nunca por `like` sobre su texto: Postgres
       --    acepta `true` y `on` como sinonimos y guarda literalmente lo que se escribio.
       --    Un `like '%security_invoker=true%'` cuenta las de `on` como definer — nos
       --    engaño a los dos por separado y nos hizo contar 18 definer donde hay 13.
       exists (select 1 from unnest(coalesce(c.reloptions, '{}')) o
                where lower(split_part(o, '=', 1)) = 'security_invoker'
                  and lower(split_part(o, '=', 2)) in ('true', 'on', 'yes', '1'))
                                                          as es_invoker,
       coalesce(array_to_string(c.reloptions, ','), '(sin opciones)') as reloptions,
       -- 🔒 LA AUTOCOMPROBACION VIAJA CON EL DATO, no en una consulta aparte que se
       --    olvide de lanzar. Con `search_path` vacio, Postgres NO PUEDE abreviar y
       --    cualifica todo con `public.`; con el search_path normal, no aparece.
       --    ⇒ Si esta columna sale FALSE, el pin no se aplico y **el md5 de esa fila NO
       --      es comparable con el del otro entorno**. No es un aviso: es la fila
       --      diciendo que no se fie nadie de ella.
       --    🔬 Medido en staging el 12-ago-2026 sobre v_escaner_ultimo:
       --         con pin → true, 379 car · sin pin → false, 365 car.
       (pg_get_viewdef(c.oid, true) like '%public.%')     as pin_aplicado
from pin, pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'v'
order by c.relname;

-- ⚠️ POR QUE LA COMPROBACION NO ES "comparar la longitud con y sin pin en la misma
--    consulta": porque NO FUNCIONA, y lo comprobe escribiendolo mal primero.
--    `set_config(..., true)` es de TRANSACCION: en cuanto se fija en la primera rama de
--    un UNION, la segunda ya lo tiene puesto. Las dos filas salian 379 y 379 — iguales
--    SIEMPRE, dijera lo que dijera el pin. Una comprobacion que no puede fallar no
--    comprueba nada. La de `public.` no depende del orden ni del entorno.
