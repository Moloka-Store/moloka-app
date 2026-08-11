-- ============================================================================
-- MIGRACIÓN 2026-08-11 · v_keepa_bb_envio — el ENVÍO de la caja de compra
--   ·  PR 1 del encargo «La verdad del dinero en el Cockpit» (Parte 1)
--   ·  + arregla el `security_invoker` de v_presencia_pais (§1.6 del encargo)
-- ----------------------------------------------------------------------------
-- PARA QUÉ. La buy box del Cockpit está mal medida: le falta el envío.
--
-- `keepa_escaparate.bb_precio` es el precio A SECAS. El envío que cobra el dueño de la
-- caja viene en un campo APARTE dentro del `jsonb crudo` —`Caja de Compra: Gastos de
-- envío`— y **ninguna pantalla lo lee**. El dato está pagado, descargado y guardado en la
-- base desde hace tiempo, y nadie lo mira.
--
-- 🔬 EL TAMAÑO DEL AGUJERO, medido hoy sobre las 494 fichas:
--      · 22 fichas traen envío, por un total de 112,94 €.
--      · 🔑 LAS 22 SON FBM. Ninguna es FBA — y tiene todo el sentido: la oferta FBA lleva
--        el envío dentro y la FBM lo cobra aparte. Es decir, el error aparece justo donde
--        el rival es un vendedor que envía él mismo.
--      · 🔒 Y 0 de esas 22 tiene `bb_precio` a NULL, así que donde hay envío SIEMPRE se
--        puede sumar: no hay que inventarse un caso «envío sin precio».
--      · El peor: B0DSWFBQ73 (DE), 13,33 € + 4,99 = 18,32 € — la pantalla se queda un
--        37,4 % por debajo del precio que paga el cliente.
--
-- Comparar nuestro precio FBA (que lleva el envío dentro) contra el `bb_precio` pelado de
-- un FBM es comparar peras con manzanas. El número bueno para decidir a cuánto listar es
-- el precio «puesto en casa»: bb_precio + envío.
--
-- 🎁 DE REGALO, dos campos más del `crudo` que tampoco lee nadie y que esta vista expone
--    para que dejen de perderse: 🔬 102 fichas traen `Tiempo de envío` y 75 `País de
--    envío`. Ahí dentro hay rivales con **190 días** de plazo, que no son rivales: son un
--    hueco. **Se GUARDAN pero NO se pintan todavía** (ver el aviso de abajo).
--
-- ⚠️ EL AVISO QUE VIAJA CON EL DATO, y por eso está aquí y no solo en el encargo:
--    🔬 hay **31 fichas con `Tiempo de envío` y `bb_precio` a NULL**. No se sabe por qué.
--    La hipótesis razonable —que Keepa arrastre el plazo del último dueño de una caja hoy
--    vacía— es RAZONAMIENTO, no medición. Hasta que se entienda, `bb_plazo_txt` y
--    `bb_pais_envio` se traen y se guardan, pero NO se pintan como señal.
--    🔒 El envío no tiene ese problema (0 casos), así que ése sí se usa ya.
--
-- POR QUÉ UNA VISTA Y NO PROMOCIONAR LOS CAMPOS A COLUMNAS. Promocionarlos es lo limpio a
-- medio plazo, y la tabla ya tiene 67 columnas casi todas sacadas del `crudo`. Pero eso
-- obliga a un ALTER TABLE sobre `keepa_escaparate` y **no consta leído** cómo inserta el
-- procesador de Keepa (si con lista explícita de columnas o no). Si insertara con todas,
-- un ALTER TABLE revienta la carga.
-- 🔴 La carga de Keepa alimenta la operativa de Elena: no se arriesga por ahorrarse un
--    join de 494 filas. La promoción a columnas va en su propio PR, después, y empieza por
--    LEER ese procesador entero.
--
-- 🔒 `security_invoker = true`: la vista corre con los permisos de quien consulta.
--    🔬 Medido con `set role authenticated` y un JWT con `sub`: `keepa_escaparate` tiene
--    RLS activa con política de lectura para `authenticated` y devuelve las 494 filas. La
--    vista hereda esa RLS en vez de saltársela.
--
-- CIFRAS DE CONTROL (read-only, reproducidas ANTES del DDL):
--   · 494 filas · 22 con `bb_envio` · 102 con `bb_plazo_txt` · 75 con `bb_pais_envio`.
--   🔒 El 22 es criterio: ni 21 ni 23. Si sube, hay fichas nuevas con envío y hay que
--      mirarlas; si baja, se ha perdido dato por el camino.
-- ============================================================================

set local lock_timeout = '3s';

create or replace view public.v_keepa_bb_envio
with (security_invoker = true) as
select
    k.asin,
    k.dominio,
    -- 🔴 El importe que el dueño de la caja cobra APARTE del precio. Sumado a `bb_precio`
    --    da el precio «puesto en casa», que es el que paga el cliente de verdad.
    nullif(k.crudo->>'Caja de Compra: Gastos de envío', '')::numeric as bb_envio,
    -- ⚠️ Los dos siguientes se GUARDAN pero NO se pintan: ver el aviso del NULL arriba.
    nullif(k.crudo->>'Caja de Compra: País de envío', '')            as bb_pais_envio,
    nullif(k.crudo->>'Caja de Compra: Tiempo de envío', '')          as bb_plazo_txt
from keepa_escaparate k;

comment on view public.v_keepa_bb_envio is
  'Los tres campos de la caja de compra que viven SOLO dentro del jsonb crudo de '
  'keepa_escaparate y que ninguna pantalla leía: el envío que cobra el dueño de la caja '
  '(22 fichas, todas FBM), su plazo y su país de origen. bb_precio + bb_envio = precio '
  'puesto en casa. Plazo y país se guardan pero NO se pintan: hay 31 fichas con plazo y '
  'sin precio y no se sabe por qué. anon NO tiene acceso.';

-- Nace cerrado (§4 de CLAUDE.md): en `public` todo objeto nuevo nace con `arwdDxtm` para
-- `anon` Y `authenticated` por los DEFAULT PRIVILEGES de Supabase, y un `revoke from
-- public` NO los quita. Se revoca a cada rol por su nombre y luego el grant mínimo.
revoke all on public.v_keepa_bb_envio from public, anon, authenticated;
grant select on public.v_keepa_bb_envio to authenticated;


-- ============================================================================
-- Y DE PASO: v_presencia_pais pasa a `security_invoker`
-- ----------------------------------------------------------------------------
-- 🔴 ESTA VISTA SE CREÓ DEFINER A PROPÓSITO, Y NO ERA UN DESCUIDO. El 10-ago-2026
--    `ledger_movimientos` tenía RLS activa y **CERO políticas**: con `security_invoker`
--    la vista habría devuelto 0 filas a la app. Definer era la única forma de que el
--    Cockpit viera la presencia por país sin abrir el ledger a nadie.
--
-- ✅ LO QUE HA CAMBIADO, y por eso ahora sí se puede: el ledger ya tiene una política de
--    lectura para `authenticated` (`inventario_read_authenticated`, `auth.uid() IS NOT
--    NULL`), puesta al cerrarlo a `anon`. 🔬 Comprobado como la app —`set role
--    authenticated` con un JWT que trae `sub`—: la tabla base devuelve **18.461 filas**.
--    Así que con invoker la vista sigue viendo todo lo que tiene que ver.
--
-- 🔒 POR QUÉ MERECE LA PENA CAMBIARLA AUNQUE HOY NO ABRA NADA: una vista definer es una
--    puerta que no depende de la RLS de su tabla base. Hoy da lo mismo porque
--    `authenticated` ya puede leer el ledger y `anon` no ve la vista; el día que alguien
--    endurezca la RLS del ledger, la vista definer seguiría dando los datos igual y nadie
--    se enteraría. Con invoker, endurecer el ledger endurece también la vista. Es el
--    patrón de la casa y aquí ya no cuesta nada.
--
-- ⚠️ VERIFICACIÓN OBLIGATORIA, y NO vale hacerla con el conector: éste corre como
--    `postgres`, que se salta la RLS, así que daría 508 filas con definer y con invoker.
--    **La prueba que vale es `set local role authenticated` + claims con `sub`**, y tiene
--    que dar el MISMO recuento antes y después. Está abajo, comentada, para ejecutarla a
--    mano tras aplicar.
--
-- 🔬 ENSAYO EN STAGING: LA PRUEBA SALIÓ MEJOR DE LO PREVISTO, porque staging resultó NO
--    tener la política del ledger (el backup de anoche es anterior a que se creara). Eso
--    permitió medir LAS DOS MITADES del cambio en vez de una:
--
--      · En staging, SIN la política → la vista con invoker devuelve **0 filas** a
--        `authenticated`. El invoker NO es cosmético: sin permiso en la tabla base, corta.
--      · En producción, CON la política → la tabla base da 18.461 filas al mismo rol, así
--        que la vista sigue viendo lo suyo.
--
--    🔴 Y DE AHÍ SALE EL RIESGO QUE HAY QUE DECIR EN ALTO, porque el encargo no lo
--       anticipaba y cambia el perfil del cambio: **con invoker, esta vista pasa a
--       depender de una política RLS creada el 10-ago-2026.** Si algún día se restaura
--       producción desde un backup anterior a esa fecha, `v_presencia_pais` se queda a
--       CERO filas y el Cockpit pierde la presencia por país **en silencio** — no da
--       error, da vacío. Con definer eso no pasaba.
--       No es motivo para no hacerlo (endurecer el ledger debe endurecer la vista, que es
--       justo lo que se busca), pero sí para que conste junto al frente ya abierto de §4:
--       *el simulacro de restauración no reproduce producción*.
--
-- ⚠️ Y LA TRAMPA DE MEDIRLO MAL, demostrada en el mismo ensayo: tras aplicar en staging,
--    el conector (que corre como `postgres` y se salta la RLS) seguía devolviendo **508**
--    filas mientras la app habría visto **0**. Verificar esto con el conector da un VERDE
--    FALSO. La única prueba válida es `set local role authenticated` + claims con `sub`.
--
-- 🔬 Filas antes de tocar nada: 508.
-- ============================================================================

alter view public.v_presencia_pais set (security_invoker = true);

-- Verificación posterior, A MANO y como la app (no como postgres):
--   begin;
--   set local role authenticated;
--   set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
--   select count(*) from public.v_presencia_pais;   -- tiene que seguir dando 508
--   rollback;
