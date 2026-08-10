-- ============================================================================
-- MIGRACIÓN 2026-08-10 · GATE DE SEGURIDAD — cerrar a `anon` las tres vistas con
--   puerta trasera  ·  §6 del encargo Cockpit multi-país
-- ----------------------------------------------------------------------------
-- LA FUGA, MEDIDA HOY con `set local role anon` (o sea: lo que puede leer
-- cualquiera con la clave publicable, que viaja en el JavaScript de la app):
--     v_salud_asin    224 filas   ← catálogo, stock, ventas T7/T30/T60/T90, precios
--     v_escaparate    498 filas   ← buy box, quién la tiene, competencia, diagnóstico
--     v_estado_asin   205 filas   ← acciones, precios implicados, márgenes implicados
--
-- Las tres corren como su dueño (no tienen `security_invoker`), así que se saltan la
-- RLS de las tablas de debajo; y además tienen GRANT a `anon`. La combinación de las
-- dos cosas es la puerta trasera. 🔒 El problema NO es «definer»: es `anon` — hay
-- vistas definer perfectamente cerradas (v_presencia_pais) porque no se lo dan.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- 🔴 LO QUE CAMBIÓ EL PLAN AL MEDIR: `v_trackeador_cola` DEPENDE DE DOS DE ELLAS
-- ══════════════════════════════════════════════════════════════════════════════
-- `v_trackeador_cola` (la cola de decisión del trackeador, 390 filas) se construye
-- SOBRE `v_salud_asin` y `v_escaparate`. Eso tiene dos consecuencias:
--
--   1. Un `DROP VIEW` de cualquiera de las dos FALLA por dependencia — y con
--      `CASCADE` se llevaría por delante `v_trackeador_cola`, que hoy está bien
--      hecha (ya es `security_invoker`, con `authenticated=r` y sin `anon`).
--      Por eso aquí NO se recrea nada: se usa `ALTER VIEW … SET (security_invoker)`,
--      que cambia SOLO esa opción sin tocar la definición, ni el ACL, ni las
--      dependencias. Es la vía canónica de Postgres para este cambio concreto y no
--      tiene el riesgo del DROP+CREATE.
--
--   2. Al pasar las dos de abajo a `invoker`, la cadena entera pasa a correr con los
--      permisos de quien consulta. 🔬 MEDIDO ANTES DE TOCAR, con sesión real
--      (`role authenticated` + claims con `sub`): las tablas base devuelven TODO
--      (`salud_fba` 225, `keepa_escaparate` 498, sus políticas son
--      `auth.uid() IS NOT NULL`), así que las vistas seguirán dando 224 y 498, y
--      `v_trackeador_cola` seguirá dando sus 390. Y si el trackeador se conecta con
--      `service_role`, ese rol tiene `rolbypassrls`: la RLS no le afecta en absoluto.
--      🔒 `anon` NO puede leer `v_trackeador_cola` hoy, así que el trackeador no la
--      lee como anónimo — no hay por dónde romperse.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- 🔴 POR QUÉ `v_estado_asin` SE QUEDA SIN `security_invoker`
-- ══════════════════════════════════════════════════════════════════════════════
-- Sus tablas de debajo NO están como las otras dos:
--     monitor_analisis    → RLS activa y CERO políticas  → 0 filas para TODO el mundo
--     monitor_resultados  → 1 política `ALL` a PUBLIC con `using (true)` → abierta
-- Y la vista arranca en `FROM monitor_analisis a LEFT JOIN LATERAL …`: la tabla
-- conductora es la que está a cero. 🔬 Medido: `monitor_analisis` devuelve 0 filas
-- incluso CON sesión válida, porque sin políticas no pasa nadie. Ponerle
-- `security_invoker` la dejaría en 0 filas: se arreglaría la fuga y se rompería la
-- vista. Aquí solo se le cierra `anon`, que es lo que urge, y la defensa en
-- profundidad espera a decidir qué se hace con esas dos tablas.
--
-- ⚠️ HALLAZGO COLATERAL, que NO se toca aquí y merece su propia decisión:
--    `monitor_resultados` deja leer 🔬 234 filas a `anon` DIRECTAMENTE (política
--    `ALL` a PUBLIC con `using (true)` + grant a anon). No es una de las tres vistas
--    del gate, así que no entra en esta migración — pero es la misma clase de
--    agujero y hay que cerrarlo. Igual que `productos`, con 455 filas a anon.
--
-- QUIÉN CONSUME LAS TRES (barrido de los dos repos, antes de tocar):
--   · El Cockpit v2: NO las usa.
--   · La v1 de Elena (`index.html`, 10.342 líneas): 0 menciones.
--   · El trackeador (`moloka_tracker_*.py`, los tres): 0 menciones.
--   · La única dependencia en la BASE es `v_trackeador_cola`, tratada arriba.
--   ⚠️ Lo que este barrido NO cubre: algo fuera de estos dos repos (un Colab, un
--      script suelto). No consta, pero no se puede demostrar que no exista.
--
-- DESPLIEGUE: `REVOKE` y `ALTER VIEW … SET` son cambios de catálogo, instantáneos y
--   sin reescritura de datos. Reversible: el `ALTER` se deshace con
--   `SET (security_invoker = off)` y el grant con `GRANT SELECT … TO anon`.
--   Por la escalera igual (staging → SQL → prod → SQL), con lock_timeout corto.
--
-- 🔒 LA VERIFICACIÓN VA EN PRODUCCIÓN, NO EN STAGING, y no es un capricho: el
--    backup se vuelca con `--no-privileges`, así que staging viene del restore con
--    los ACL por defecto de Supabase y sus permisos NO son los de producción (ver
--    CLAUDE.md §4). Para objetos PREEXISTENTES como estos tres, un test de ACL en
--    staging no prueba nada. En staging se ensaya que el DDL corre y que las vistas
--    siguen devolviendo filas; el ACL se mide en prod, después de aplicar.
-- ============================================================================

set local lock_timeout = '3s';

-- ── 1) LO QUE CIERRA EL AGUJERO HOY, en las tres ────────────────────────────
-- Sin DROP y sin recrear: solo se retira el permiso. `public` va incluido porque un
-- grant a PUBLIC alcanzaría también a anon, aunque hoy no lo haya.
revoke all on public.v_salud_asin  from anon, public;
revoke all on public.v_escaparate  from anon, public;
revoke all on public.v_estado_asin from anon, public;

-- Se reafirma lo que la app SÍ necesita. Es idempotente y deja el permiso escrito en
-- la migración, en vez de depender de que alguien recuerde que estaba.
grant select on public.v_salud_asin  to authenticated;
grant select on public.v_escaparate  to authenticated;
grant select on public.v_estado_asin to authenticated;

-- ── 2) DEFENSA EN PROFUNDIDAD, solo donde las tablas de debajo lo soportan ──
-- Con esto, aunque alguien volviera a conceder `anon` por descuido (o tras un
-- restore, que devuelve los ACL abiertos), la RLS de las tablas base seguiría
-- filtrando: sin sesión válida no hay filas. El REVOKE de arriba vive en el ACL y
-- un restore se lo lleva; esto vive en el DDL de la vista y sobrevive.
alter view public.v_salud_asin set (security_invoker = on);
alter view public.v_escaparate set (security_invoker = on);

-- 🔒 `v_estado_asin` NO lleva `security_invoker`: la dejaría a 0 filas (ver arriba).
--    Queda pendiente, y depende de qué se decida con monitor_analisis/monitor_resultados.
