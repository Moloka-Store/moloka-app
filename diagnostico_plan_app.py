# -*- coding: utf-8 -*-
"""DIAGNOSTICO · el plan de una consulta TAL COMO LA PAGA LA APP.

🔴 QUE AGUJERO CIERRA. Hasta hoy no habia forma de ver el plan real de la pantalla, y
   eso me llevo TRES VECES a dar por buena una cifra que no era. El MCP de lectura
   entra como `supabase_read_only_user`, que tiene `pg_read_all_data` y **salta la
   RLS**: sus EXPLAIN miden otra consulta. La diferencia medida el 25-ago-2026 sobre
   `salud_fba` es de **177x** (1.185 buffers contra ~210.000).

🔑 Y SI HAY VIA, al contrario de lo que llegue a escribir. `postgres` tiene
   `rolbypassrls = true` POR ATRIBUTO DE ROL, pero en cuanto hace `SET ROLE
   authenticated` el rol EFECTIVO es otro y la RLS aplica. Lo que no se puede es
   hacerlo desde el MCP: `supabase_read_only_user` NO es miembro de `authenticated`
   (`pg_has_role` = false), y por eso alli daba "permission denied to set role".
   Comprobado en produccion: postgres SI es miembro.

🔴 Y LAS CLAIMS NO SON OPCIONALES. Sin ellas `auth.uid()` es NULL, la politica da
   FALSO, y el plan sale sobre CERO FILAS -- rapido, verde, y midiendo nada. Es la
   comprobacion que no puede fallar en su forma mas facil de tragarse. Por eso este
   guion ABORTA si el rol efectivo no es `authenticated`, si `auth.uid()` viene nulo,
   o si el plan devuelve cero filas.

🔒 ES DE SOLO LECTURA Y SE DESHACE. Todo corre dentro de una transaccion que termina
   en ROLLBACK: el `SET LOCAL ROLE` y el `set_config(..., true)` mueren con ella.
   `EXPLAIN ANALYZE` ejecuta la consulta, pero son SELECT.

⚠️ LO QUE SI CUESTA: la consulta que se mide lee ~1,6 GB, y la base tiene 224 MB de
   `shared_buffers`. O sea que **vacia la cache**. Correrlo deja a Elena unos segundos
   con la base fria. Es una vez y a mano; no se pone en ningun reloj.

USO: workflow `diagnostico-plan-app.yml`, a mano. Sin schedule.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import conectar_bd  # noqa: E402

DB_URL = os.environ.get('DB_URL', '')
ENTORNO = os.environ.get('ENTORNO', 'staging').strip().lower()

# 🔒 Un uuid de mentira. NO es una credencial ni abre nada: `auth.uid()` solo se usa
#    en las politicas para preguntar "¿hay alguien dentro?" --son de la forma
#    `(SELECT auth.uid()) IS NOT NULL`--, asi que cualquier uuid vale y ninguno da mas
#    acceso que otro. Va aqui a la vista a proposito, para que quede claro que no hay
#    nada que esconder.
CLAIMS = '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}'

# La consulta EXACTA que la app hace sobre salud_fba, sacada de pg_stat_statements
# (queryid -5726156718328844774, rol authenticated) y con sus parametros puestos.
# 🔒 Se copia LITERAL. Reescribirla "equivalente" mediria otra cosa: el plan depende
#    del texto, y este envoltorio --la CTE, el ORDER BY de tres columnas, el json_agg--
#    es justo lo que se quiere medir.
CONSULTA_APP = """
WITH pgrst_source AS (
  SELECT "public"."salud_fba"."asin", "public"."salud_fba"."marketplace",
         "public"."salud_fba"."sku", "public"."salud_fba"."fnsku",
         "public"."salud_fba"."available", "public"."salud_fba"."fc_transfer",
         "public"."salud_fba"."inbound_shipped", "public"."salud_fba"."days_of_supply",
         "public"."salud_fba"."units_shipped_t7", "public"."salud_fba"."units_shipped_t30",
         "public"."salud_fba"."units_shipped_t90", "public"."salud_fba"."alert",
         "public"."salud_fba"."sales_rank", "public"."salud_fba"."snapshot_date",
         "public"."salud_fba"."your_price", "public"."salud_fba"."featuredoffer_price",
         "public"."salud_fba"."lowest_price_new_plus_shipping",
         "public"."salud_fba"."recommended_ship_in_quantity"
    FROM "public"."salud_fba"
   WHERE "public"."salud_fba"."marketplace" = 'ES'
   ORDER BY "public"."salud_fba"."asin" ASC, "public"."salud_fba"."marketplace" ASC,
            "public"."salud_fba"."sku" ASC
   LIMIT 1000 OFFSET 0
)
SELECT 0::bigint AS total_result_set,
       pg_catalog.count(_postgrest_t) AS page_total,
       coalesce(json_agg(_postgrest_t), '[]') AS body
  FROM ( SELECT * FROM pgrst_source ) _postgrest_t
"""

CONSULTA_PELADA = """
SELECT * FROM public.salud_fba WHERE marketplace = 'ES'
"""

# 🔴 EL LATERAL AISLADO, QUE ES DONDE ESTA EL 99,8% DEL COSTE.
#    🔒 La columna es `ke.rank`, y va copiada de `pg_get_viewdef('salud_fba')`, no de
#       la memoria: la primera version puso `ke.sales_rank` --que es como se llama en
#       la VISTA-- y los tres casos reventaron con "column does not exist". El nombre
#       de una columna se lee, no se recuerda. Las dos versiones son
#    la MISMA consulta salvo en una cosa: si el cruce lleva `btrim`/`lower` o va crudo.
#    Con eso se contesta, ANTES de tocar nada, si el arreglo funciona.
# 🔒 Y el `count(*)` de las dos tiene que salir IGUAL: si no, no son la misma consulta y
#    la comparacion no vale. Esta comprobado aparte que los envoltorios son inertes
#    (0 filas cambian sobre 1.653 + 362), pero aqui se vuelve a mirar en la misma
#    corrida -- una comparacion entre dos cosas que devuelven distinto no mide nada.
LATERAL_CON_ENVOLTORIOS = """
SELECT count(k.rank) AS casan
  FROM public.inventario_fba i
  LEFT JOIN LATERAL (
    SELECT ke.rank
      FROM public.keepa_escaparate ke
     WHERE btrim(ke.asin) = btrim(i.asin) AND lower(ke.dominio) = 'es'
     ORDER BY ke.fecha_foto DESC
     LIMIT 1) k ON true
"""

LATERAL_CRUDO = """
SELECT count(k.rank) AS casan
  FROM public.inventario_fba i
  LEFT JOIN LATERAL (
    SELECT ke.rank
      FROM public.keepa_escaparate ke
     WHERE ke.asin = i.asin AND ke.dominio = 'es'
     ORDER BY ke.fecha_foto DESC
     LIMIT 1) k ON true
"""

# 🔑 LOS CASOS SON UNA COMPARACION, NO TRES MEDICIONES SUELTAS. El orden importa:
#    el que de verdad interesa va PRIMERO, con la cache tal como se la encuentra la app.
#    Los otros dos van despues, y hay que leerlos sabiendo que corren con la cache ya
#    caliente por el primero -- o sea que si aun asi salen BAJOS, la diferencia es real
#    y no un efecto de cache.
CASOS = [
    ('1. LA DE LA APP, con RLS (authenticated)', CONSULTA_APP, True),
    ('2. La misma pelada, con RLS (authenticated)', CONSULTA_PELADA, True),
    ('3. La misma pelada, SIN RLS (postgres) -- el contraste', CONSULTA_PELADA, False),
    ('4. EL LATERAL solo, con btrim/lower, con RLS', LATERAL_CON_ENVOLTORIOS, True),
    ('5. EL LATERAL solo, con cruce CRUDO, con RLS', LATERAL_CRUDO, True),
    ('6. EL LATERAL con btrim/lower, SIN RLS -- el contraste', LATERAL_CON_ENVOLTORIOS, False),
]


# 🔴 EL BARRIDO. La pregunta que sale del hallazgo y que nadie habia hecho: ¿donde MAS
#    pasa esto? Cualquier cruce VIVO bajo RLS que envuelva una columna en btrim/lower/
#    upper pierde su indice igual, exista el indice o no.
# 🔑 El filtro que decide NO es "tiene envoltorios": son TRES condiciones a la vez.
#      1. la vista es `security_invoker` (si es definer corre como el dueno y la RLS ni
#         se evalua),
#      2. la app la lee VIVA (las que solo se leen a traves de una copia estan a salvo:
#         la copia la refresca `postgres`, que salta la RLS),
#      3. y hay un indice que se pudiera usar.
#    El censo por texto da 11 vistas vivas con envoltorios; cruzando las tres quedan DOS.
BARRIDO = [
    ('v_producto_proveedor', 'invoker · 90 llamadas de la app'),
    ('v_escaner_ultimo', 'definer · 173 llamadas -- se espera que NO le afecte'),
    ('v_nunca_enviado_fba', 'definer · 80 llamadas -- se espera que NO le afecte'),
]


def explicar(cur, sql):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + sql)
    return [f[0] for f in cur.fetchall()]


def total_buffers(plan):
    """Los buffers de la RAIZ del plan, que es el total de la sentencia."""
    for linea in plan:
        if 'Buffers:' in linea:
            trozo = linea.split('Buffers:')[1]
            total = 0
            for parte in trozo.replace(',', ' ').split():
                if '=' in parte:
                    try:
                        total += int(parte.split('=')[1])
                    except ValueError:
                        pass
            return total
    return None


def main():
    print("=== EL PLAN, TAL COMO LO PAGA LA APP ===", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 78, flush=True)

    if not DB_URL:
        sys.exit("Falta DB_URL. Revisa los secrets del workflow.")

    con = conectar_bd(DB_URL)
    cur = con.cursor()

    cur.execute("SELECT current_user, current_setting('shared_buffers'), "
                "pg_has_role(current_user, 'authenticated', 'MEMBER')")
    quien, cache, es_miembro = cur.fetchone()
    print(f"   · current_user      : {quien}", flush=True)
    print(f"   · shared_buffers    : {cache}", flush=True)
    print(f"   · miembro de authenticated: {es_miembro}", flush=True)
    if not es_miembro:
        con.rollback(); cur.close(); con.close()
        sys.exit(f"ABORTA: {quien} NO es miembro de `authenticated`, asi que no puede "
                 f"hacer SET ROLE. Sin eso este diagnostico mediria con la RLS SALTADA, "
                 f"que es exactamente el error que viene a corregir.")

    salidas = {}
    for titulo, sql, con_rls in CASOS:
        print(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}", flush=True)
        try:
            if con_rls:
                cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (CLAIMS,))
                cur.execute("SET LOCAL ROLE authenticated")

                # 🔴 LAS TRES GUARDAS QUE IMPIDEN UN PLAN QUE NO MIDE NADA.
                cur.execute("SELECT current_user")
                efectivo = cur.fetchone()[0]
                if efectivo != 'authenticated':
                    raise RuntimeError(
                        f"el rol efectivo es {efectivo!r} y tenia que ser 'authenticated'. "
                        f"El plan estaria midiendo SIN la RLS.")
                cur.execute("SELECT auth.uid()")
                uid = cur.fetchone()[0]
                if uid is None:
                    raise RuntimeError(
                        "auth.uid() ha salido NULO. Las politicas son "
                        "`(SELECT auth.uid()) IS NOT NULL`, asi que darian FALSO y el "
                        "plan saldria sobre CERO FILAS: rapido, verde, y midiendo nada.")
                print(f"   · rol efectivo: {efectivo} · auth.uid(): {uid}", flush=True)

            plan = explicar(cur, sql)
            for linea in plan:
                print("   " + linea, flush=True)

            # 🔴 UN PLAN SOBRE CERO FILAS NO PRUEBA NADA, y es el fallo mas facil de
            #    tragarse porque sale rapido y verde.
            filas = None
            for linea in plan:
                if 'actual rows=' in linea:
                    filas = int(linea.split('actual rows=')[1].split()[0])
                    break
            if filas == 0:
                raise RuntimeError(
                    "el plan ha salido sobre CERO FILAS. Eso no mide el coste de nada: "
                    "o la RLS ha tapado la tabla o el filtro no casa.")

            b = total_buffers(plan)
            salidas[titulo] = (b, filas)
            if b is not None:
                print(f"\n   >>> BUFFERS TOTALES: {b:,} = {b * 8192 / 1048576:,.0f} MB "
                      f"· filas: {filas}", flush=True)
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {str(e).strip()}", flush=True)
            salidas[titulo] = None
        finally:
            # 🔒 Se deshace SIEMPRE: el SET LOCAL ROLE y el set_config mueren con la
            #    transaccion, tambien si el EXPLAIN reventó.
            con.rollback()

    # ── EL BARRIDO ────────────────────────────────────────────────────────
    print(f"\n{'=' * 78}\nBARRIDO · ¿donde MAS pasa esto?\n{'=' * 78}", flush=True)
    barrido = {}
    for vista, nota in BARRIDO:
        sql = f"SELECT * FROM public.{vista}"
        pareja = {}
        for etiqueta, con_rls in (('con RLS', True), ('sin RLS', False)):
            try:
                if con_rls:
                    cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (CLAIMS,))
                    cur.execute("SET LOCAL ROLE authenticated")
                    cur.execute("SELECT current_user, auth.uid()")
                    efectivo, uid = cur.fetchone()
                    # 🔴 Las mismas guardas: sin rol efectivo o sin uid, el plan no mide nada.
                    if efectivo != 'authenticated' or uid is None:
                        raise RuntimeError(
                            f"rol efectivo {efectivo!r}, auth.uid()={uid!r}. El plan no "
                            f"mediria con la RLS puesta.")
                plan = explicar(cur, sql)
                pareja[etiqueta] = total_buffers(plan)
                pareja[etiqueta + ' plan'] = plan
            except Exception as e:
                print(f"   ❌ {vista} ({etiqueta}): {type(e).__name__}: {str(e).strip()[:160]}",
                      flush=True)
                pareja[etiqueta] = None
            finally:
                con.rollback()
        a, b = pareja.get('con RLS'), pareja.get('sin RLS')
        barrido[vista] = (a, b, nota)
        if a is None or b is None or b == 0:
            print(f"   · {vista}: sin medida ({nota})", flush=True)
            continue
        veces = a / b
        marca = '🔴' if veces >= 2 else '·'
        print(f"   {marca} {vista}: con RLS {a:,} buffers · sin RLS {b:,} · "
              f"x{veces:.1f}   ({nota})", flush=True)
        # 🔒 El plan entero solo se imprime si hay diferencia: si las dos mitades salen
        #    iguales no hay nada que leer, y un muro de texto tapa lo que si.
        if veces >= 2:
            print("      --- el plan CON RLS ---", flush=True)
            for linea in pareja.get('con RLS plan', []):
                print("      " + linea, flush=True)

    print(f"\n{'=' * 78}\nRESUMEN\n{'=' * 78}", flush=True)
    for titulo, _, _ in CASOS:
        v = salidas.get(titulo)
        if v is None or v[0] is None:
            print(f"   · {titulo}: sin medida", flush=True)
        else:
            b, filas = v
            print(f"   · {titulo}: {b:,} buffers = {b * 8192 / 1048576:,.0f} MB "
                  f"({filas} filas)", flush=True)

    print("\n   --- BARRIDO ---", flush=True)
    for vista, (a, b, nota) in barrido.items():
        if a is None or b is None or b == 0:
            print(f"   · {vista}: sin medida", flush=True)
        else:
            print(f"   · {vista}: x{a/b:.1f}  ({a:,} con RLS / {b:,} sin RLS)", flush=True)

    cur.close()
    con.close()

    # 🔴 Si el caso 1 --el unico que importa-- no se pudo medir, esto sale ROJO. Un
    #    diagnostico que no mide lo que venia a medir no vale como verde.
    if salidas.get(CASOS[0][0]) is None or salidas[CASOS[0][0]][0] is None:
        sys.exit(1)


if __name__ == '__main__':
    main()
