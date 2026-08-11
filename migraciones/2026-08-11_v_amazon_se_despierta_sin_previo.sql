-- ============================================================================
-- MIGRACIÓN 2026-08-11 · v_amazon_se_despierta — no inventar un «antes» que no existe
-- ----------------------------------------------------------------------------
-- QUÉ HACE ESTA VISTA. Avisa de cuándo Amazon (el vendedor, no el marketplace) vuelve a
-- tener stock de un ASIN: compara su disponibilidad de HOY contra la de la última vez que
-- lo vimos. Es de las señales más accionables que hay, porque Amazon despertando cambia
-- el precio de la caja de un día para otro.
--
-- 🔴 EL FALLO. La comparación se apoyaba en:
--
--       COALESCE(p.amazon_disponibilidad, '') <> 'La oferta de Amazon está en stock…'
--
--    Cuando NO hay observación anterior de ese ASIN, `p.amazon_disponibilidad` es NULL, el
--    COALESCE lo convierte en cadena vacía, y la comparación da TRUE. O sea: **«no sé si
--    antes estaba» se convierte en «antes NO estaba»**, y si hoy está, la vista canta
--    `AMAZON_SE_HA_DESPERTADO` sin tener con qué compararlo.
--    Es el mismo NULL-tratado-como-cero de siempre, disfrazado de cadena vacía.
--
-- 🔬 IMPACTO MEDIDO HOY (11-ago-2026), y hay que decirlo entero: **HOY NO CAMBIA NI UNA
--    FILA.** La vista tiene **73** filas y las 73 tienen observación anterior, todas de
--    hace 1 día. Este PR no arregla ningún dato de hoy.
--    (⚠️ Y una corrección mía: primero conté 221 y era la población equivocada. 221 son los
--     ASIN españoles de `keepa_escaparate`; la vista se queda en 73 porque exige
--     `amazon_precio is not null`. El `join v_trackeador_cola` no descarta ninguno de esos
--     73. Embudo: 221 → 73 → 73.)
--
--    🔑 LO QUE SÍ ES EL ARGUMENTO: de esas 73 filas, **66 (el 90%) tienen a Amazon en stock
--    ahora mismo**. O sea que el estado «Amazon está» es el NORMAL, no la excepción. En
--    cuanto un ASIN entre nuevo al escaparate con precio de Amazon —lo que pasa cada vez
--    que Fernando amplía el seguimiento— la vista vieja lo anuncia como
--    `AMAZON_SE_HA_DESPERTADO` con nueve de cada diez papeletas, sin haberlo observado
--    nunca antes. No es un caso exótico: es el caso probable, esperando a que pase.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 🔑 CÓMO FUNCIONA EL HISTÓRICO DE VERDAD — medido, porque de esto había dos premisas
--    falsas dando vueltas (una mía y una de Fernando) y las dos se han caído.
--
--    `archivar_foto` (foto_comun.py) NO archiva el fichero que entra: archiva **la foto
--    viva ENTERA, los cuatro dominios**, justo antes de cargar, y es IDEMPOTENTE por
--    `(asin, dominio, fecha_foto)`. De ahí sale lo que despista al mirarlo:
--
--      · **Cada `archivado_en` enseña UN SOLO dominio.** No es que archive fichero a
--        fichero: es que los otros tres YA estaban archivados y el `NOT EXISTS` los salta.
--      · **El último archivado de un dominio ES la foto viva**, no la anterior. 🔬 ES:
--        221 filas, mismos 221 ASIN, misma fecha que la viva. Quien tome «el último
--        archivado» como el «antes» estaría comparando la foto contra sí misma.
--      · Y una misma `fecha_foto` aparece repartida en varios `archivado_en`.
--
--    🔒 LA UNIDAD BUENA ES `(dominio, fecha_foto)`: eso, y sólo eso, es UN FICHERO.
--       🔬 Comprobado que es atómica: de las 31 fotos del histórico, **0** están repartidas
--       entre varios archivados. `fecha_foto` sale del nombre del fichero (`leer_nombre`).
--
--    🔬 Y con la unidad buena, el censo real de 9 fechas (20-jul → 10-ago) es:
--       seis fechas con los 4 dominios · 20-jul con 3 (de,fr,it) · 10-ago con 3 (de,es,it)
--       · **25-jul con UNO solo (es)**. O sea que sí: una carga puede traer un país o
--       cuatro, y entre el 31-jul y el 7-ago hay un hueco de 7 días. **La carga de Keepa
--       no es diaria ni completa**, y una vista que compare «contra ayer» sin decir contra
--       qué día compara está mintiendo por omisión (§1.4).
-- ─────────────────────────────────────────────────────────────────────────────
--
-- 🔒 LA DECISIÓN, ya con los números delante. Medido sobre los 221 ASIN españoles de la
--    foto (la población ancha, para que la elección se decida donde el caso EXISTE — dentro
--    de las 73 de la vista hoy no se da ninguno, y elegir sobre cero casos no es elegir):
--      · **217** están en la foto anterior de verdad (09-ago) → comparación limpia.
--      · **3** no están en la de 09-ago pero sí en una más vieja.
--      · **1** no aparece en ninguna foto anterior.
--    Con esos 3 hay dos caminos, y se coge el segundo:
--      (a) Clavar «la foto anterior» a una sola fecha y dar los 3 por incomparables.
--      (b) Comparar cada ASIN contra **su última observación real**, y ENSEÑAR de cuándo es.
--    Se elige (b) porque de esos 3 SÍ sabemos algo —los vimos hace 3 días—, y la regla de
--    la casa es conservar toda comparación buena y decir «no sé» sólo donde de verdad no se
--    sabe. Lo que hace honesto a (b) NO es el criterio: es `dias_desde_foto_anterior`, que
--    pone el hueco a la vista. Sin esa columna, (b) sería un collage disfrazado de foto.
--
-- ⚠️ Y OJO AL FILTRO `fecha_foto < la viva`, que no es cosmético: el 10-ago se cargó ES
--    DOS VECES, así que el histórico tiene un es/10-ago (el primer fichero) y la viva es
--    el segundo. Con `<` se compara **día contra día** (10-ago vs 09-ago) en vez de dos
--    ficheros del mismo día, que sólo daría ruido. Además `(asin,dominio,fecha_foto)` no
--    sabe distinguir dos ficheros de la misma fecha: ordenarlos no es posible.
--
-- QUÉ CAMBIA, en concreto:
--   1. `alerta` pasa a **NULL** cuando no hay NINGUNA observación anterior de ese ASIN, en
--      vez de un `AMAZON_SE_HA_DESPERTADO` que nadie ha observado.
--   2. Se añade `motivo_sin_comparar`, que lo dice con esas palabras.
--   3. Se añade `dias_desde_foto_anterior` — la columna que sostiene la decisión (b).
--   4. El `previo` se empareja por **(asin, dominio)**, no sólo por asin.
--   5. 🔒 El `dominio = 'es'` se conserva TAL CUAL: esta vista es de España y lo era antes.
--      Cambiarla a multi-país sería otro PR y otra decisión. El par va explícito de todos
--      modos: el día que mire cuatro países, comparar España contra Italia sería el gordo.
--
-- CIFRAS DE CONTROL (contrastadas en producción en SOLO LECTURA antes de aplicar, corriendo
-- el SELECT nuevo al lado del viejo):
--   · **73** filas · las mismas 73 que la vista vieja.
--   · **0** con `alerta` NULL — hoy no hay ningún ASIN sin pasado dentro de la vista.
--   · **0** filas con `alerta` NULL y sin motivo. 🔒 Este es el invariante que no puede
--     romperse nunca: una raya sin explicación se lee como «no pasa nada».
--   · **0** despertares, igual que la vista vieja. Ni uno se pierde ni uno se inventa.
--   · `dias_desde_foto_anterior` = 1 en las 73.
--   ⚠️ La lectura correcta de esto NO es «el arreglo no vale»: es que hoy la red está
--      vacía. Sube en cuanto entre un ASIN nuevo, y ahí es donde la vista vieja mentía.
--   ⚠️ Si tras una carga suben las de alerta NULL, es que la foto nueva trajo ASIN que no
--      estaban antes — eso es información, no un fallo.
--
-- DESPLIEGUE. `create or replace view`: AccessShareLock, instantáneo, sólo lectura.
--   🔒 Conserva el ACL, así que sigue CERRADA a `anon` (se cerró el 11-ago). Se re-afirma
--      abajo de todos modos: cuesta nada y cubre un DROP+CREATE futuro.
-- ============================================================================

set local lock_timeout = '3s';

create or replace view public.v_amazon_se_despierta as
with foto as (
    select asin, dominio, fecha_foto, amazon_disponibilidad, amazon_precio,
           bb_precio, bb_pct_amazon_30d
    from keepa_escaparate
    where dominio = 'es'
), previo as (
    -- La ÚLTIMA observación de cada (asin, dominio) anterior a la foto viva. Ver arriba
    -- por qué (b) y no (a), y por qué el `<` es día-contra-día.
    select distinct on (h.asin, h.dominio)
           h.asin, h.dominio, h.fecha_foto, h.amazon_disponibilidad, h.amazon_precio
    from keepa_escaparate_hist h
    where h.dominio = 'es'
      and h.fecha_foto < (select max(k.fecha_foto) from keepa_escaparate k where k.dominio = 'es')
    order by h.asin, h.dominio, h.fecha_foto desc
)
select f.asin,
    c.nombre,
    c.disponible                                   as mi_stock,
    c.your_price_min                               as mi_precio,
    f.amazon_precio,
    round(c.your_price_min - f.amazon_precio, 2)   as cuanto_estoy_por_encima,
    p.amazon_disponibilidad                        as amazon_antes,
    f.amazon_disponibilidad                        as amazon_ahora,
    p.fecha_foto                                   as foto_anterior,
    f.fecha_foto                                   as foto_actual,
    f.bb_pct_amazon_30d,
    case
        -- 🔴 SIN OBSERVACIÓN ANTERIOR NO HAY COMPARACIÓN. Antes, el COALESCE convertía
        --    este caso en «antes no estaba» y cantaba un despertar que nadie vio.
        when p.asin is null then null
        when f.amazon_disponibilidad = 'La oferta de Amazon está en stock y se puede enviar'
             and coalesce(p.amazon_disponibilidad, '') <> 'La oferta de Amazon está en stock y se puede enviar'
            then 'AMAZON_SE_HA_DESPERTADO'
        when f.amazon_disponibilidad = 'El envío de la oferta de Amazon está retrasado'
            then 'amazon_presente_pero_lento'
        when f.amazon_disponibilidad = 'La oferta de Amazon está en stock y se puede enviar'
            then 'amazon_activo_ya_lo_estaba'
        else 'sin_amazon'
    end                                            as alerta,
    -- 🔒 LAS COLUMNAS NUEVAS VAN AL FINAL, y no es estética: `create or replace view` NO
    --    deja intercalar columnas («cannot change name of view column»). Ponerlas en medio
    --    obligaría a DROP + CREATE, que PIERDE el ACL — y esta vista se acaba de cerrar a
    --    `anon` (11-ago). Al final, el replace conserva los permisos.
    -- El porqué, con esas palabras, para que la raya no se lea como «no pasa nada».
    case
        when p.asin is null
            then 'nunca visto antes en el escaparate español: no hay con qué comparar'
        else null
    end                                            as motivo_sin_comparar,
    -- 🔑 LA COLUMNA QUE SOSTIENE LA DECISIÓN. Sin ella, comparar contra «la última vez que
    --    lo vimos» sería un collage disfrazado de foto. Con ella, el que lo lee ve si el
    --    «antes» es de ayer o de hace una semana. 🔬 Hoy: 217 a 1 día y 3 a 3 días.
    (f.fecha_foto - p.fecha_foto)                  as dias_desde_foto_anterior
from foto f
join v_trackeador_cola c on c.asin = f.asin and c.dominio = 'es'
left join previo p on p.asin = f.asin and p.dominio = f.dominio
where f.amazon_precio is not null
  and coalesce(c.disponible, 0::bigint) >= 0;

comment on view public.v_amazon_se_despierta is
  'Avisa de cuándo Amazon vuelve a tener stock, comparando la foto de hoy contra la última '
  'observación anterior del MISMO dominio. Si de un ASIN no hay ninguna, `alerta` va a NULL '
  'y `motivo_sin_comparar` lo dice: antes se inventaba un AMAZON_SE_HA_DESPERTADO que nadie '
  'había observado. `dias_desde_foto_anterior` enseña de cuándo es el «antes», porque la '
  'carga de Keepa no es diaria ni trae siempre los cuatro países (9 fechas en 22 días, una '
  'con un solo dominio, un hueco de 7 días). anon NO tiene acceso.';

-- Se re-afirma el cierre: `create or replace` conserva el ACL, pero un DROP+CREATE futuro
-- lo perdería y el objeto renacería con `anon` dentro (§4). Idempotente.
revoke all on public.v_amazon_se_despierta from public, anon;
grant select on public.v_amazon_se_despierta to authenticated;


-- ── VERIFICACIÓN tras aplicar ────────────────────────────────────────────────
--   select count(*) filas,                                          -- 73
--          count(*) filter (where alerta is null) sin_comparar,      -- 0
--          count(*) filter (where alerta = 'AMAZON_SE_HA_DESPERTADO') despertares,  -- 0
--          count(*) filter (where dias_desde_foto_anterior = 1) a_1_dia,   -- 73
--          count(*) filter (where dias_desde_foto_anterior > 1) mas_viejas -- 0
--     from public.v_amazon_se_despierta;
--
-- 🔒 Y que ninguna fila con alerta NULL se quede sin explicación:
--   select count(*) from public.v_amazon_se_despierta
--    where alerta is null and motivo_sin_comparar is null;           -- tiene que dar 0
