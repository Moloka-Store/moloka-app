-- ============================================================================
-- MIGRACION - LAS VISTAS DE ARRANQUE ENTRAN EN EL REPO: 6 objetos vivos
-- ----------------------------------------------------------------------------
-- QUE ES ESTO. La hermana de `2026-08-28_repo_trackeador_objetos_vivos.sql`,
-- misma naturaleza: una FOTO literal de lo que ya existe en produccion y que
-- ningun fichero de ningun repo crea (medido el 28-ago-2026 sobre .sql, .py,
-- .yml y .ts de los dos repos: cero apariciones de `create ... <nombre>`).
--
-- VAN SEPARADAS DE LAS DEL TRACKEADOR A PROPOSITO: son otra familia, no las lee
-- ningun codigo de la app, y su riesgo es distinto. Un PR, una cosa.
--
-- LAS FILAS: doctrina_madres SI, y aqui esta el criterio -- si la tabla vacia
-- hace que algo deje de funcionar, sus filas son CONFIGURACION y no historia.
--   · `doctrina_madres` (7 filas): SON la doctrina. Sin ellas
--     `v_doctrina_arranque` se crea y devuelve cero. El objeto existiria y no
--     serviria para nada, que es la peor de las dos formas de fallar.
--     Van con `on conflict (id) do nothing`: si alguien edito la doctrina en
--     produccion, esta migracion NO la pisa.
--   · `trackeador_refrescos` (41 filas, en la migracion hermana): es un log.
--     Historia, no configuracion. Eso lo devuelve el backup.
--
-- ⚠️ LO QUE ESTA FOTO CONSERVA Y NO ARREGLA, dicho para que no se lea como un
--    descuido: `v_sondas_pendientes` NO lleva `security_invoker`, o sea que
--    corre como su dueno, y `authenticated` tiene sobre ella permisos de
--    escritura (arwdDxtm), no solo lectura. Las dos cosas chocan con la
--    seccion 4 y se transcriben tal cual porque el encargo es reproducir, no
--    mejorar. Frente propio, con su PR.
--
-- ⚠️ Y UN EFECTO MEDIDO QUE CONVIENE SABER: `doctrina_madres` tiene RLS activo
--    y CERO politicas. `v_doctrina_arranque` es security_invoker, asi que un
--    `authenticated` que la lea vera CERO filas -- no porque no haya, sino
--    porque no puede verlas. Es el caso de "0 filas por RLS no es 0 filas
--    porque no hay". Se transcribe como esta; queda apuntado.
--
-- ORDEN: doctrina_madres -> v_sondas_pendientes -> v_reglas_arranque ->
--        v_doctrina_arranque -> v_sondas_arranque -> v_arranque_coste
--        (v_arranque_coste lee a las tres de arriba, por eso cierra.)
-- ============================================================================

-- -- GUARDAS -----------------------------------------------------------------
DO $guardas$
DECLARE
    falta      text;
    k          char;
    ya_estaban int;
BEGIN
    SELECT string_agg(x.nombre, ', ' ORDER BY x.nombre) INTO falta
      FROM (VALUES ('monitor_reglas'),('monitor_doctrina'),('monitor_analisis'),
                   ('monitor_resultados')) x(nombre)
     WHERE to_regclass('public.' || x.nombre) IS NULL;
    IF falta IS NOT NULL THEN
        RAISE EXCEPTION 'ABORTA: faltan las fuentes %. Esta migracion transcribe CODIGO y da por hecho que el esquema de tablas ya existe.', falta;
    END IF;

    FOR falta IN SELECT x.n FROM (VALUES ('v_sondas_pendientes'),('v_reglas_arranque'),
                                         ('v_doctrina_arranque'),('v_sondas_arranque'),
                                         ('v_arranque_coste')) x(n)
    LOOP
        SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.' || falta);
        IF k IS NOT NULL AND k <> 'v' THEN
            RAISE EXCEPTION 'ABORTA: % existe con relkind=% y se esperaba una VISTA.', falta, k;
        END IF;
    END LOOP;

    SELECT relkind INTO k FROM pg_class WHERE oid = to_regclass('public.doctrina_madres');
    IF k IS NOT NULL AND k <> 'r' THEN
        RAISE EXCEPTION 'ABORTA: doctrina_madres existe con relkind=% y se esperaba una TABLA.', k;
    END IF;

    -- El mismo aviso que en la hermana: un verde sobre un destino que ya estaba
    -- en el estado final no prueba nada.
    SELECT count(*) INTO ya_estaban FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
     WHERE ns.nspname = 'public' AND c.relname IN
           ('doctrina_madres','v_sondas_pendientes','v_reglas_arranque','v_doctrina_arranque',
            'v_sondas_arranque','v_arranque_coste');
    IF ya_estaban >= 6 THEN
        RAISE WARNING 'AVISO: los 6 objetos YA EXISTIAN. Sobre produccion es lo esperado. En un ENSAYO significa que no se tiraron antes, y ese verde no prueba que el fichero sepa crearlos.';
    ELSE
        RAISE NOTICE 'Guardas OK. Existian % de 6.', ya_estaban;
    END IF;
END
$guardas$;

-- -- 1) LA TABLA DE LA DOCTRINA Y SUS 7 FILAS --------------------------------
create table if not exists public.doctrina_madres (
  id smallint not null,
  nombre text not null,
  cuerpo text not null,
  orden smallint not null,
  constraint doctrina_madres_pkey PRIMARY KEY (id)
);

alter table public.doctrina_madres enable row level security;

revoke all on public.doctrina_madres from public, anon, authenticated;
grant all on public.doctrina_madres to service_role;

-- Las 7 madres. `do nothing` para no pisar una doctrina editada en produccion.
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (1, 'Cómo se arranca', 'No se habla de precios sin haber leído la memoria. Se leen las siete madres enteras y el índice del resto; lo que haga falta se trae completo con fn_doctrina_buscar. Se comprueba que el dato es de HOY antes de recomendar nada: si la foto de Keepa no es de hoy, se para y se dice. Y se abre el primer mensaje diciendo cuántas normas y reglas se han leído y cuántas sondas hay vencidas DE VERDAD (filtrando las que nunca arrancaron el reloj).', 1) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (2, 'Cómo se decide un precio', 'Se prioriza por la CAÍDA (T7 vs T30), nunca por volumen. Ante una caída, se investiga la causa en el histórico ANTES de recomendar. NINGÚN precio sin su margen calculado y sin reglas_aplicadas. Ningún precio sin contrastarlo contra umbral_competitivo: el motor no lo mira en ninguna acción. Con guerra activa no se baja. La fórmula de margen es intocable e incluye el acantilado de 20 € en ES.', 2) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (3, 'Cómo se lee a un rival', 'La caja se adjudica por velocidad > cuenta > céntimo, no por precio. Un rival con stock congelado repone, no se agota. Del % de Amazon manda la tendencia, no el nivel. La banda alta de Keepa no es nivel de mercado si la caja no está ahí. El popup es referencia, no techo. Un FBM con poco stock es transitorio: se espera.', 3) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (4, 'Qué significa cada dato', 'Antes de creerse un cero, se pide el control. Un cero puede venir de la clave y no del mundo: un dominio mal escrito, una categoría traducida, un id regenerado, un catálogo que solo enseña lo que te deja ver. Cada dato tiene una fuente, una fecha y un alcance, y los tres se dicen antes de opinar. Si un dato no se puede datar, se dice que no se puede.', 4) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (5, 'Los cuatro mercados', 'ES, IT, FR y DE son cuatro negocios distintos con la misma mercancía: cambian el IVA, la tarifa FBA, la regla ISD y la presencia. España es solo el 44% de las fichas en juego. La comisión es la misma en toda la UE para una categoría dada; la tarifa FBA no. Ante una tarifa desconocida se usa la más cara conocida, por precaución. Y hay seis mercados más en el informe Pan-EU que casi nadie mira.', 5) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (6, 'Cómo trabajamos', 'Quién ejecuta no es quien decide, y ninguno de los dos puede a diario: Fernando no tiene Seller entre semana y Elena pica precios cuando puede, sin reportar. NINGÚN mecanismo puede depender de que alguien confirme, cierre o reporte: lo que no se deduzca solo de la base, no existe. Las sondas se revisan los fines de semana. En la web, ritmo humano y parada al primer error, sin reintentar nunca.', 6) on conflict (id) do nothing;
insert into public.doctrina_madres (id, nombre, cuerpo, orden) values (7, 'Cómo se toca la base', 'Se despliega lo que se ha medido, no lo que se ha escrito. Una comprobación que nunca se ha visto en rojo es una hipótesis con formato de test. Una alarma encendida todos los días deja de leerse. La misma regla escrita en dos sitios es de donde salen los fallos. Y una garantía que depende de que el llamado sea educado no es una garantía.', 7) on conflict (id) do nothing;

-- -- 2) LAS CINCO VISTAS ------------------------------------------------------
-- v_sondas_pendientes va SIN security_invoker: es como esta viva. Ver el aviso
-- de la cabecera.
create or replace view public.v_sondas_pendientes as
SELECT r.id AS resultado_id,
    a.codigo,
    r.asin,
    a.accion,
    r.precio_observado AS precio_antes,
    r.precio_decidido AS precio_puesto,
    a.margen_implicado_pct AS margen_esperado,
    r.nueva_sonda AS vence,
    CURRENT_DATE - r.nueva_sonda AS dias_vencida,
    a.autor AS decidio,
    a.reglas_aplicadas AS reglas_a_validar,
    r.experimento,
    r.hipotesis,
    r.notas AS que_medir
   FROM monitor_resultados r
     JOIN monitor_analisis a ON a.id = r.analisis_id
  WHERE r.veredicto IS NULL
  ORDER BY r.nueva_sonda, a.codigo;

revoke all on public.v_sondas_pendientes from public, anon, authenticated;
grant all on public.v_sondas_pendientes to service_role;
grant all on public.v_sondas_pendientes to authenticated;

create or replace view public.v_reglas_arranque with (security_invoker = true) as
SELECT id,
    categoria,
    COALESCE(ambito_pais, 'todos'::text) AS pais,
    activa,
    COALESCE(estado_validacion, 'SIN_PROBAR'::text) AS validacion,
    veces_aplicada,
    veces_confirmada,
    veces_refutada,
    "left"(regexp_replace(regexp_replace(COALESCE(descripcion, ''::text), '[🔴🟢🔒📌⚠️⛔🔑⏱️✅]'::text, ''::text, 'g'::text), '[
]+'::text, ' '::text, 'g'::text), 150) AS enunciado,
        CASE
            WHEN condicion IS NULL THEN NULL::text
            WHEN jsonb_typeof(condicion) = 'object'::text THEN ( SELECT string_agg(k.k, ', '::text ORDER BY k.k) AS string_agg
               FROM jsonb_object_keys(r.condicion) k(k))
            ELSE "left"(condicion::text, 80)
        END AS aplica_sobre,
    length(COALESCE(descripcion, ''::text)) > 150 OR condicion IS NOT NULL AS hay_mas_texto
   FROM monitor_reglas r
  ORDER BY activa DESC, categoria, id;

revoke all on public.v_reglas_arranque from public, anon, authenticated;
grant all    on public.v_reglas_arranque to service_role;
grant select on public.v_reglas_arranque to authenticated;

create or replace view public.v_doctrina_arranque with (security_invoker = true) as
SELECT orden,
    id AS madre,
    nombre,
    cuerpo,
    ( SELECT count(*) AS count
           FROM monitor_doctrina d
          WHERE d.activa AND d.madre = m.id) AS derivaciones,
    ( SELECT string_agg((d.id || ' · '::text) || regexp_replace(regexp_replace("left"(d.norma, 200), '[🔴🟢🔒📌⚠️⛔🔑⏱️✅]'::text, ''::text, 'g'::text), '[\n\r]+'::text, ' '::text, 'g'::text), '
'::text ORDER BY d.id) AS string_agg
           FROM monitor_doctrina d
          WHERE d.activa AND d.madre = m.id) AS indice
   FROM doctrina_madres m
  ORDER BY orden;

revoke all on public.v_doctrina_arranque from public, anon, authenticated;
grant all    on public.v_doctrina_arranque to service_role;
grant select on public.v_doctrina_arranque to authenticated;

create or replace view public.v_sondas_arranque with (security_invoker = true) as
SELECT codigo,
    asin,
    accion,
    precio_puesto,
    margen_esperado,
    vence,
    dias_vencida,
    "left"(regexp_replace(regexp_replace(COALESCE(hipotesis, ''::text), '[🔴🟢🔒📌⚠️⛔]'::text, ''::text, 'g'::text), '[
]+'::text, ' '::text, 'g'::text), 90) AS hipotesis_corta,
    que_medir ~~* '%ARRANCAR EL RELOJ%'::text AS reloj_sin_arrancar
   FROM v_sondas_pendientes
  WHERE que_medir !~~* '%ARRANCAR EL RELOJ%'::text AND dias_vencida > 0
  ORDER BY dias_vencida DESC;

revoke all on public.v_sondas_arranque from public, anon, authenticated;
grant all    on public.v_sondas_arranque to service_role;
grant select on public.v_sondas_arranque to authenticated;

create or replace view public.v_arranque_coste with (security_invoker = true) as
WITH piezas AS (
         SELECT 'doctrina · 7 madres + índice'::text AS pieza,
            1 AS orden,
            ( SELECT round(sum(length((v_doctrina_arranque.nombre || v_doctrina_arranque.cuerpo) || v_doctrina_arranque.indice))::numeric / 4.0) AS round
                   FROM v_doctrina_arranque) AS tokens
        UNION ALL
         SELECT 'reglas · índice de 43'::text,
            2,
            ( SELECT round(sum(length((((COALESCE(v_reglas_arranque.categoria, ''::text) || COALESCE(v_reglas_arranque.pais, ''::text)) || COALESCE(v_reglas_arranque.validacion, ''::text)) || COALESCE(v_reglas_arranque.enunciado, ''::text)) || COALESCE(v_reglas_arranque.aplica_sobre, ''::text)))::numeric / 4.0) AS round
                   FROM v_reglas_arranque) AS round
        UNION ALL
         SELECT 'sondas vencidas · índice'::text,
            3,
            ( SELECT round(sum(length(((COALESCE(v_sondas_arranque.codigo, ''::text) || COALESCE(v_sondas_arranque.asin, ''::text)) || COALESCE(v_sondas_arranque.accion, ''::text)) || COALESCE(v_sondas_arranque.hipotesis_corta, ''::text)))::numeric / 4.0) AS round
                   FROM v_sondas_arranque) AS round
        UNION ALL
         SELECT 'frescura + salud (una fila cada una)'::text,
            4,
            200
        ), t AS (
         SELECT sum(piezas.tokens) AS total
           FROM piezas
        )
 SELECT p.pieza,
    p.tokens,
    round(100.0 * p.tokens / NULLIF(t.total, 0::numeric)) AS pct,
    t.total AS total_arranque,
    25000 AS techo,
    round(100.0 * t.total / 25000::numeric) AS pct_del_techo,
        CASE
            WHEN t.total > 25000::numeric THEN 'PASADO DEL TECHO: hay que podar, no ampliar la ventana'::text
            WHEN t.total > 20000::numeric THEN 'cerca del techo: medir cada semana'::text
            ELSE 'holgado'::text
        END AS veredicto
   FROM piezas p,
    t
  ORDER BY p.orden;

revoke all on public.v_arranque_coste from public, anon, authenticated;
grant all    on public.v_arranque_coste to service_role;
grant select on public.v_arranque_coste to authenticated;

-- -- TESTIGOS ----------------------------------------------------------------
DO $testigo$
DECLARE
    n_obj   int;
    n_filas int;
    n_inv   int;
    n_coste int;
BEGIN
    SELECT count(*) INTO n_obj FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
     WHERE ns.nspname = 'public' AND c.relname IN
           ('doctrina_madres','v_sondas_pendientes','v_reglas_arranque','v_doctrina_arranque',
            'v_sondas_arranque','v_arranque_coste');
    IF n_obj <> 6 THEN
        RAISE EXCEPTION 'ABORTA: se esperaban 6 objetos y hay %.', n_obj;
    END IF;

    SELECT count(*) INTO n_filas FROM public.doctrina_madres;
    IF n_filas < 7 THEN
        RAISE EXCEPTION 'ABORTA: doctrina_madres tiene % filas y las 7 madres son configuracion, no historia. v_doctrina_arranque saldria vacia.', n_filas;
    END IF;

    -- 🔴 La foto incluye que v_sondas_pendientes NO es invoker. Se ancla en lo
    --    que NO debe aparecer, que es la mitad que se mueve: si alguien le
    --    pusiera security_invoker, este fichero dejaria de reproducir
    --    produccion y hay que enterarse por aqui, no por una pantalla rara.
    SELECT count(*) INTO n_inv FROM pg_class c
     WHERE c.oid = 'public.v_sondas_pendientes'::regclass
       AND EXISTS (SELECT 1 FROM unnest(coalesce(c.reloptions,'{}')) o
                    WHERE lower(split_part(o,'=',1)) = 'security_invoker'
                      AND lower(split_part(o,'=',2)) IN ('true','on','yes','1'));
    IF n_inv <> 0 THEN
        RAISE EXCEPTION 'ABORTA: v_sondas_pendientes ha pasado a security_invoker. Esta migracion es una foto de lo que hay, y ya no lo reproduce.';
    END IF;

    -- Y que la vista de coste devuelve sus 4 piezas: es la unica que cruza a
    -- las otras tres, asi que si alguna se creo mal, se cae aqui.
    SELECT count(*) INTO n_coste FROM public.v_arranque_coste;
    IF n_coste <> 4 THEN
        RAISE EXCEPTION 'ABORTA: v_arranque_coste devuelve % piezas y se esperaban 4.', n_coste;
    END IF;

    RAISE NOTICE 'Testigo OK. 6 objetos, % madres, v_sondas_pendientes sigue definer (como en produccion), v_arranque_coste da sus 4 piezas.', n_filas;
END
$testigo$;

DO $puerta_anon$
DECLARE n bigint;
BEGIN
    SET LOCAL ROLE anon;
    EXECUTE 'SELECT count(*) FROM (SELECT * FROM public.v_arranque_coste LIMIT 0) z' INTO n;
    RESET ROLE;
    RAISE EXCEPTION 'ABORTA: anon ha entrado en v_arranque_coste. La puerta esta abierta.';
EXCEPTION
    WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'Testigo OK (puerta). anon REBOTA en v_arranque_coste.';
END
$puerta_anon$;

-- ============================================================================
-- COMO COMPROBAR QUE ESTO SIGUE SIENDO LA FOTO
-- ----------------------------------------------------------------------------
-- Estas huellas son las de PRODUCCION medidas el 28-ago-2026. Si manana alguien
-- cambia un objeto vivo sin pasar por aqui, este fichero deja de reproducirlo y
-- la unica forma de enterarse es contrastar. El md5 es el juez.
--
--   select c.relname, md5(pg_get_viewdef(c.oid,true)) , length(pg_get_viewdef(c.oid,true))
--     from pg_class c join pg_namespace n on n.oid=c.relnamespace
--    where n.nspname='public' and c.relname in (<las vistas de abajo>)
--   union all
--   select p.proname, md5(p.prosrc), length(p.prosrc)
--     from pg_proc p join pg_namespace n on n.oid=p.pronamespace
--    where n.nspname='public' and p.proname in (<las funciones de abajo>);
--
-- ⚠️ AL COMPARAR CONTRA EL FICHERO, NORMALIZA CRLF -> LF. Y ojo: un CR SUELTO
--    no es un final de linea, es DATO -- `v_reglas_arranque` y
--    `v_sondas_arranque` llevan uno dentro de una cadena. Convertirlo cambia la
--    vista. Por eso el repo lleva `migraciones/*.sql -text` en .gitattributes.
--
-- | objeto | md5 | largo |
-- |---|---|---|
-- | `v_sondas_pendientes` | `a92d435f77895df2e2c531009f87b9b8` | 549 |
-- | `v_reglas_arranque` | `80c5efe6d418474c1749cdc51c5f2171` | 871 |
-- | `v_doctrina_arranque` | `1e6ad5908460f8ca4638b8c823a1cdf9` | 542 |
-- | `v_sondas_arranque` | `b4f164b054a8169baecb17e080e3635c` | 479 |
-- | `v_arranque_coste` | `bc2e65814ea23d3784e3976936ed025e` | 1922 |
--
-- ⚠️ OJO CON ESA ULTIMA, QUE NO ES LA QUE MIDIO PRODUCCION EL 28-ago-2026.
--    Produccion daba `3c33ce292563114bee1759c85642ebc8` (1.898) y esta migracion,
--    aplicada, deja `bc2e65814ea23d3784e3976936ed025e` (1.922). NO es una
--    transcripcion mal hecha: es que POSTGRES RE-RENDERIZA. Al recrear la vista
--    desde su propio texto, anade `AS text` a las ramas 2, 3 y 4 del `UNION ALL`:
--
--        -  SELECT 'reglas · indice de 43'::text,
--        +  SELECT 'reglas · indice de 43'::text AS text,
--
--    Tres veces por 8 caracteres = los 24 exactos de diferencia. Es inerte: los
--    nombres de columna de un UNION los fija la PRIMERA rama, y el dato no cambia.
--    Y `bc2e6581...` es PUNTO FIJO -- comprobado recreando la vista dos veces desde
--    su propio texto: da siempre lo mismo. Aplicar esto a produccion cambiaria ese
--    md5 UNA vez y despues se quedaria quieto.
--
--    Se anota aqui el valor de DESPUES, no el de antes, para que el proximo que
--    compare no se lleve un susto por nada. El de antes queda escrito arriba para
--    que se sepa de donde viene.
-- 🔬 Medido el 28-ago-2026 en el ensayo de staging (runs 33165975056 y siguientes),
--    con `diff` contra el texto capturado de produccion, no a ojo.
-- ============================================================================
