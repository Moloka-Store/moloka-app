-- ============================================================================
-- MIGRACIÓN 2026-08-11 · completar los tres campos de envío en keepa_escaparate_hist,
--                        SÓLO en la foto del 10-ago-2026
-- ----------------------------------------------------------------------------
-- 🔴 ESTO ES UN `UPDATE` SOBRE UNA PELÍCULA (§1.6). Es una EXCEPCIÓN ÚNICA, con nombre y
--    fecha, NO una práctica. Léase entero antes de copiarlo para otra cosa.
--
-- QUÉ PASÓ. El 11-ago se promovieron a columna `bb_envio`, `bb_pais_envio` y
-- `bb_plazo_txt`, que hasta entonces sólo vivían dentro de `crudo`. Pero `crudo` NO se
-- archiva —a propósito: el CSV entero está en Storage—, así que el histórico nunca los
-- tuvo. La tabla viva se rellenó desde `crudo` al migrar; el histórico no, porque sus
-- filas del 10-ago ya estaban archivadas **horas antes de que las columnas existieran**.
--
-- Y no se arreglan solas: `archivar_foto` es IDEMPOTENTE por `(asin, dominio, fecha_foto)`,
-- así que esas filas **no se reescribirán jamás**. Sin esto, la foto del 10-ago queda con
-- `fr` relleno —porque `fr` aún no estaba archivado y se archivará ya con los campos— y
-- `de`/`es`/`it` a NULL. **Una incoherencia dentro de una misma fecha**, que es la trampa
-- que dentro de tres meses produce un hallazgo falso: alguien lee «el 10-ago DE no tenía
-- gastos de envío» cuando lo que pasa es que nadie los copió.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 🔒 POR QUÉ SE PUEDE TOCAR AQUÍ, Y LA REGLA QUE QUEDA PARA LA PRÓXIMA
--
--    El histórico no es intocable por dogma: es intocable porque **normalmente no puedes
--    demostrar que un cambio sea fiel**. Aquí sí se puede, y está medido:
--      🔬 Las **404** parejas del 10-ago (de, es, it) son **IDÉNTICAS**: comparada la fila
--         ENTERA como jsonb —no cinco columnas elegidas a mano— salen **404 idénticas y 0
--         distintas**, y con el **mismo nombre de fichero**. Es el mismo CSV.
--      🔬 Las 404 tienen los tres campos a NULL en el histórico. **106** recibirán un valor
--         de verdad; las otras 298 están a NULL también en la viva (Keepa no dio nada), y
--         quedarán como estaban.
--    No se reconstruye nada: se **completa una copia que salió incompleta** por un accidente
--    de calendario.
--
--    ⚖️ LA REGLA QUE QUEDA: se completa el histórico **sólo cuando se pueda demostrar que la
--       fuente es la misma y la copia exacta**. En cualquier otro caso, el hueco se DECLARA
--       y se queda. Las 3.380 filas de fechas anteriores no se tocan: su dato vive en los
--       CSV de Storage por si algún día hace falta, y eso ya estaba decidido.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- LAS GUARDAS, que son el motivo de que esto sea un bloque y no un UPDATE a pelo:
--   1. **Fila a fila.** La condición de identidad va DENTRO del `WHERE` del UPDATE, no en un
--      `IF` previo. Una fila que difiera en una sola columna NO se toca, aunque las demás
--      sí. Nada de `UPDATE … WHERE fecha_foto = '2026-08-10'` a pelo.
--   2. **Las saltadas se NOMBRAN**, con asin y dominio, en el resumen. Una fila que no se
--      toca en silencio es un hueco que nadie sabrá que existe.
--   3. **Sólo se rellenan NULL.** Si el histórico ya tuviera un valor, no se pisa.
--   4. **Huella md5 del resto del histórico**, antes y después. Prueba que de las 3.380
--      filas de otras fechas no se movió ni un byte — no que sigan siendo 3.380, que eso
--      no demuestra nada (§3).
--   5. **Cuadre exacto**: si las filas actualizadas no son las que el censo predijo,
--      EXCEPTION y se deshace todo.
--
-- ⏳ VENTANA. Esto sólo funciona **mientras la tabla viva siga teniendo la foto del
--    10-ago**. En cuanto entre la carga del 11-ago, la viva pasa a 11-ago y desaparece la
--    fuente: quedaría sólo el CSV de Storage, que es otro trabajo y otro PR.
--
-- CIFRAS DE CONTROL, escritas ANTES (medidas en producción en solo lectura, 11-ago):
--   parejas 404 · idénticas 404 · distintas 0 · actualizadas 404 · con valor nuevo 106
--   · otras fechas 3.380, huella md5 IDÉNTICA antes y después.
--
-- 🔬 ENSAYO EN STAGING (11-ago), sobre un espejo EXACTO de producción — mismas 494 filas
--    vivas, mismas 3.784 archivadas, mismas 404 parejas del 10-ago:
--      · Resultado: de 92 → 10/19/26 · es 221 → 6/36/37 · it 91 → 5/11/21, y las 404
--        cuadrando VALOR A VALOR con la tabla viva. Otras fechas: 3.380 filas, los tres
--        campos a 0. Nada fuera del corralito.
--      · Y LA GUARDA, HECHA SALTAR A PROPÓSITO — las dos mitades, que es lo que vale:
--          - `B01MYNI1W6`/de: se le ponen los tres a NULL y NADA más → se RELLENA.
--          - `B071VTS65Y`/de: los tres a NULL **y `bb_stock` cambiado de 20 a 1019** →
--            **NO se toca** (su plazo sigue NULL con la viva diciendo «1 - 2 días») y sale
--            nombrada en el resumen. La guarda no sólo salta: discrimina.
--
-- ⚠️ Y una advertencia de método, cara: al ir a ensayar, staging tenía **cero** de las tres
--    columnas y no existían `v_keepa_bb_envio` ni `v_salud_escaner` — pero su
--    `supabase_migrations.schema_migrations` declaraba **8 migraciones del 11-ago
--    aplicadas**. Una restauración devolvió el esquema de anoche sin limpiar el registro.
--    🔑 **Tras restaurar staging, su registro de migraciones MIENTE.** Comprobar el objeto,
--    no el registro (§3: el estado vive en el repo y en la base, no en las notas).
--
-- DESPLIEGUE. UPDATE sobre 404 filas de una tabla de 8 MB sin triggers. `lock_timeout`
--   corto: si hay un archivado en curso, falla rápido en vez de encolarse (§ADR del lock).
--   🔄 REVERSIBLE en una línea, si hiciera falta: poner los tres campos a NULL donde
--      `fecha_foto = '2026-08-10'`. No se pisa ningún dato preexistente (sólo se rellenan
--      huecos), así que no hay nada que restaurar.
-- ============================================================================

set local lock_timeout = '5s';

do $$
declare
    k_fecha    constant date := date '2026-08-10';
    n_parejas  int;
    n_identicas int;
    n_distintas int;
    n_previstas int;
    n_hechas   int;
    n_con_valor int;
    txt_saltadas text;
    md5_antes  text;
    md5_despues text;
    n_otras    int;
begin
    -- ── Huella del RESTO del histórico. Es el testigo de que esto no se sale de su
    --    corralito. Se ordena explícitamente: sin ORDER BY, string_agg no es determinista.
    select count(*),
           md5(coalesce(string_agg(t.j::text, '|' order by t.asin, t.dominio, t.fecha_foto), ''))
      into n_otras, md5_antes
      from (select h.asin, h.dominio, h.fecha_foto, to_jsonb(h) j
              from keepa_escaparate_hist h where h.fecha_foto <> k_fecha) t;

    -- ── Censo de las parejas (histórico ↔ viva) de esa fecha. La identidad se mide sobre
    --    la fila ENTERA: `to_jsonb` menos lo que sólo tiene una de las dos y menos los tres
    --    campos que precisamente vamos a rellenar. Así no depende de que yo acierte a
    --    enumerar las columnas, y si mañana nace una columna nueva, entra sola en el cotejo.
    select count(*), count(*) filter (where t.identica),
           count(*) filter (where t.identica and t.hist_vacia and t.viva_tiene)
      into n_parejas, n_identicas, n_con_valor
      from (
        select ((to_jsonb(h) - 'archivado_en' - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt')
                = (to_jsonb(v) - 'crudo'      - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt')) as identica,
               (h.bb_envio is null and h.bb_pais_envio is null and h.bb_plazo_txt is null) as hist_vacia,
               (v.bb_envio is not null or v.bb_pais_envio is not null or v.bb_plazo_txt is not null) as viva_tiene
          from keepa_escaparate_hist h
          join keepa_escaparate v
            on v.asin = h.asin and v.dominio = h.dominio and v.fecha_foto = h.fecha_foto
         where h.fecha_foto = k_fecha) t;
    n_distintas := n_parejas - n_identicas;

    -- Cuántas cumplen TODAS las condiciones para tocarse. Es lo que tiene que salir del
    -- UPDATE, ni una más ni una menos.
    select count(*) into n_previstas
      from keepa_escaparate_hist h
      join keepa_escaparate v
        on v.asin = h.asin and v.dominio = h.dominio and v.fecha_foto = h.fecha_foto
     where h.fecha_foto = k_fecha
       and h.bb_envio is null and h.bb_pais_envio is null and h.bb_plazo_txt is null
       and ((to_jsonb(h) - 'archivado_en' - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt')
            = (to_jsonb(v) - 'crudo'      - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt'));

    -- ── Las que NO son idénticas se nombran. No se tocan, pero NO se callan.
    select string_agg(x.asin || '/' || x.dominio, ', ' order by x.dominio, x.asin)
      into txt_saltadas
      from (select h.asin, h.dominio
              from keepa_escaparate_hist h
              join keepa_escaparate v
                on v.asin = h.asin and v.dominio = h.dominio and v.fecha_foto = h.fecha_foto
             where h.fecha_foto = k_fecha
               and ((to_jsonb(h) - 'archivado_en' - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt')
                    <> (to_jsonb(v) - 'crudo'     - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt'))
             limit 50) x;

    -- ── EL UPDATE. La guarda de identidad va en el WHERE: es lo que lo hace fila a fila.
    update keepa_escaparate_hist h
       set bb_envio      = v.bb_envio,
           bb_pais_envio = v.bb_pais_envio,
           bb_plazo_txt  = v.bb_plazo_txt
      from keepa_escaparate v
     where v.asin = h.asin and v.dominio = h.dominio and v.fecha_foto = h.fecha_foto
       and h.fecha_foto = k_fecha
       -- sólo huecos: si el histórico ya tuviera valor, no se pisa
       and h.bb_envio is null and h.bb_pais_envio is null and h.bb_plazo_txt is null
       -- 🔒 y sólo si la fila archivada y la viva son la MISMA fila
       and ((to_jsonb(h) - 'archivado_en' - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt')
            = (to_jsonb(v) - 'crudo'      - 'bb_envio' - 'bb_pais_envio' - 'bb_plazo_txt'));
    get diagnostics n_hechas = row_count;

    -- ── Y el testigo: que fuera del 10-ago no se movió NI UN BYTE.
    select md5(coalesce(string_agg(t.j::text, '|' order by t.asin, t.dominio, t.fecha_foto), ''))
      into md5_despues
      from (select h.asin, h.dominio, h.fecha_foto, to_jsonb(h) j
              from keepa_escaparate_hist h where h.fecha_foto <> k_fecha) t;

    raise notice ' ';
    raise notice '=== HISTÓRICO KEEPA · completar los tres campos de envío del % ===', k_fecha;
    raise notice 'Parejas histórico<->viva de esa fecha : %', n_parejas;
    raise notice '  idénticas (fila entera)             : %', n_identicas;
    raise notice '  DISTINTAS (no se tocan)             : %', n_distintas;
    if n_distintas > 0 then
        raise notice '  >> saltadas (hasta 50)             : %', coalesce(txt_saltadas, '—');
        raise notice '  >> Estas filas se quedan con el hueco, y el hueco queda DECLARADO aquí.';
    end if;
    raise notice 'Filas actualizadas                    : % (previstas: %)', n_hechas, n_previstas;
    raise notice '  de ellas, con valor no nulo         : %', n_con_valor;
    raise notice 'Otras fechas: % filas · huella %', n_otras,
        case when md5_antes = md5_despues then 'IDÉNTICA ✅' else 'CAMBIADA ❌' end;
    raise notice ' ';

    -- ── Guardas de cierre. Cualquiera de las dos deshace la transacción entera.
    if md5_antes <> md5_despues then
        raise exception 'El histórico fuera del % ha cambiado (md5 % -> %). Se deshace todo.',
            k_fecha, md5_antes, md5_despues;
    end if;
    if n_hechas <> n_previstas then
        raise exception 'Cuadre roto: el UPDATE tocó % filas y el censo preveía %. Se deshace todo.',
            n_hechas, n_previstas;
    end if;
    if n_parejas = 0 then
        raise exception 'No hay ninguna pareja del % entre histórico y viva. O ya entró la carga '
                        'del 11-ago (y entonces la ventana se cerró: la fuente son los CSV de '
                        'Storage, otro PR), o esto se está aplicando donde no toca. No se escribe nada.',
            k_fecha;
    end if;
end $$;


-- ── VERIFICACIÓN tras aplicar ────────────────────────────────────────────────
--   select dominio, count(*) filas,
--          count(bb_envio) c_envio, count(bb_pais_envio) c_pais, count(bb_plazo_txt) c_plazo
--     from keepa_escaparate_hist where fecha_foto = date '2026-08-10'
--    group by 1 order by 1;
--   -- esperado:  de 92 → 10/19/26 · es 221 → 6/36/37 · it 91 → 5/11/21
--   -- (los mismos que la tabla viva tiene hoy para esa fecha; fr entrará solo con la
--   --  próxima carga, porque fr/10-ago todavía no está archivado)
--
-- 🔒 Y que ninguna otra fecha tenga los campos rellenos (sólo el 10-ago se ha tocado):
--   select count(*) from keepa_escaparate_hist
--    where fecha_foto <> date '2026-08-10'
--      and (bb_envio is not null or bb_pais_envio is not null or bb_plazo_txt is not null);
--   -- tiene que dar 0
