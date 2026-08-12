# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS del censo de migraciones.

Que prueba y que NO:
  · SI: las tres trampas de la EXTRACCION, que es la parte fragil, cada una con el fallo
    real que la motivo. Se ejercita la funcion del guion, no una copia retecleada.
  · SI: que el SQL generado NO menciona `supabase_migrations` en ningun punto — que es la
    regla entera de esta herramienta.
  · NO: si los objetos estan o no en una base. Eso sale de correr el SQL contra el entorno
    (lo hace `censo-migraciones.yml`), no de aqui. Datos sinteticos no prueban eso (§3).

🔑 Y las tres se comprueban en LAS DOS DIRECCIONES, que es la regla que costo aprender
   ayer: no basta con que el caso bueno pase, hay que romperlo y verlo ponerse rojo.

Se lanza solo:  python test_censo_migraciones.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
import censo_migraciones as C

fallos = []


def eq(nombre, got, exp):
    if got == exp:
        print(f"  OK  {nombre}")
    else:
        fallos.append(nombre)
        print(f"  XX  {nombre}\n        got={got!r}\n        exp={exp!r}")


# ── 1. DIGITOS EN EL NOMBRE ────────────────────────────────────────────────
# 🔴 El fallo real: la primera version usaba `[a-z_.]+`, se comio el `0` de
#    `moloka_buzones_fase0` y dio la funcion por AUSENTE estando.
eq('1a. nombre con digitos: se extrae ENTERO',
   C.objetos_de("create or replace function public.moloka_buzones_fase0() returns int as $$ $$;")[0],
   [('funcion', 'moloka_buzones_fase0')])
eq('1b. y no se queda con el trozo sin digito',
   any(n == 'moloka_buzones_fase'
       for _, n in C.objetos_de("create function public.moloka_buzones_fase0() returns int as $$ $$;")[0]),
   False)

# ── 2. MENCIONES EN COMENTARIOS ────────────────────────────────────────────
# 🔴 El fallo real: `2026-08-11_default_acl_public.sql` MENCIONA tres `create table` en su
#    cabecera explicativa y no crea ninguna. Sin quitar comentarios, el censo buscaria
#    objetos que esa migracion nunca deja.
SOLO_COMENTARIO = """-- Esta migracion habla de `create table public._prueba_acl (id int);`
--   create view public.v_inventada as select 1;
/* create function public.f_inventada() returns int as $$ $$; */
revoke all on public.algo from anon;
"""
eq('2a. lo mencionado en comentarios NO cuenta como objeto',
   C.objetos_de(SOLO_COMENTARIO)[0], [])
eq('2b. pero lo REAL de ese mismo fichero si',
   C.objetos_de(SOLO_COMENTARIO + "create view public.v_de_verdad as select 1;")[0],
   [('vista', 'v_de_verdad')])

# ── 3. LA DECLARACION EXPLICITA MANDA ──────────────────────────────────────
# Para migraciones cuyo efecto no se puede adivinar del texto (ACL, datos, comentarios).
eq('3a. @objeto declarado se respeta',
   C.objetos_de("-- @objeto: vista v_salud_escaner\nrevoke all on x from anon;")[0],
   [('vista', 'v_salud_escaner')])
eq('3b. y GANA a lo extraido (el humano manda sobre el regex)',
   C.objetos_de("-- @objeto: tabla la_que_importa\ncreate view public.v_secundaria as select 1;")[0],
   [('tabla', 'la_que_importa')])

# ── 4. LO NO DETERMINABLE SE DECLARA, NO SE APRUEBA ────────────────────────
objs, origen = C.objetos_de("revoke all on public.x from anon;\ngrant select on public.x to authenticated;")
eq('4. una migracion de solo ACL no inventa objeto', objs, [])

# ── 4b. LA HUELLA: existir no es estar vigente ─────────────────────────────
# 🔴 El caso que la motiva: 9 de los 61 objetos los tocan DOS migraciones. Sin huella, el
#    censo dice `existe` para las dos y la segunda -la que arreglo algo- es invisible.
eq('4b1. la huella de retro se aplica a su objeto',
   C.huella_de('2026-08-10_v_escaner_ultimo_clave_real', 'create view v_escaner_ultimo as select 1;',
               [('vista', 'v_escaner_ultimo')]).get('v_escaner_ultimo'),
   'DISTINCT ON (ean, proveedor, es_case)')
# 🔴 Y la lección que costó: la huella se elige contra la version VIEJA. `es_case` a secas
#    salia en las dos -es una columna del SELECT en ambas- asi que daba `vigente` sobre una
#    vista vieja. Lo que cambio fue la CLAVE de dedup, no las columnas.
eq('4b1b. la huella NO puede ser un texto que la version vieja tambien tenga',
   C.HUELLAS_RETRO[('2026-08-10_v_escaner_ultimo_clave_real', 'v_escaner_ultimo')] == 'es_case',
   False)
eq('4b2. @huella en linea, con UN objeto con cuerpo: se aplica',
   C.huella_de('inventada', '-- @huella: marca_nueva\n', [('vista', 'v_x')]).get('v_x'),
   'marca_nueva')
# 🔒 Con dos objetos con cuerpo, a cual toca es una conjetura. Aqui no se conjetura.
amb = C.huella_de('inventada', '-- @huella: marca_nueva\n', [('vista', 'v_x'), ('vista', 'v_y')])
eq('4b3. con DOS objetos con cuerpo: se ignora y se avisa',
   ('v_x' in amb or 'v_y' in amb, '__ambigua__' in amb), (False, True))
eq('4b4. una columna no lleva huella (existe o no, sin version vieja)',
   C.huella_de('inventada', '-- @huella: x\n', [('columna', 't.c')]).get('t.c'), None)

# ── 4c. LOS PUNTOS CIEGOS SE DECLARAN, NO SE TAPAN ─────────────────────────
ciegos = dict(C.puntos_ciegos(C.censar()))
eq('4c1. v_trackeador_cola sale como punto ciego (2 migraciones, sin huella)',
   'v_trackeador_cola' in ciegos, True)
eq('4c2. v_escaner_ultimo NO sale: tiene huella declarada',
   'v_escaner_ultimo' in ciegos, False)
eq('4c3. v_amazon_se_despierta tampoco', 'v_amazon_se_despierta' in ciegos, False)

# ── 4d. LOS DROP: lo retirado a proposito no es un hueco ───────────────────
# 🔴 El fallo real, cazado en la primera pasada completa contra produccion: el censo dio
#    por AUSENTE `idx_demanda_asin_ventana`. No faltaba — lo borra a proposito
#    `2026-08-07_demanda_asin_contador.sql` porque el modelo paso de ventana a contador.
nombres = {n for _, objs, _, _ in C.censar() for _, n in objs}
eq('4d1. un objeto borrado por una migracion POSTERIOR sale del censo',
   'idx_demanda_asin_ventana' in nombres, False)
eq('4d2. y sus hermanos del mismo fichero siguen dentro',
   ('idx_demanda_asin_asin' in nombres, 'idx_demanda_asin_serie' in nombres), (True, True))
# 🔒 La otra direccion: un `drop ... if exists` DEFENSIVO justo antes de crear -que es lo
#    normal en esta casa- NO debe borrar nada. Si lo hiciera, el censo se vaciaria solo.
eq('4d3. drop-antes-de-crear en el MISMO fichero no descuenta',
   [n for _, n in C.objetos_de(
       "drop view if exists public.v_x;\ncreate or replace view public.v_x as select 1;")[0]],
   ['v_x'])

# ── 4e. LOS CUBOS: el caso REAL que tiro un reparto entero ─────────────────
# 🔴 El 12-ago-2026 se clasificaron los objetos con un regex escrito a mano en SQL, y casó
#    la palabra «ventas» dentro de la PROSA ESPAÑOLA de un `comment on column` de
#    sondeo_keepa.rank_drops_30d: "Mide ventas reales; ORDENA, no decide". La tabla `ventas`
#    -herencia de la v1- quedo clasificada como creada por el conector. Hubo que tirar el
#    reparto entero porque no se sabia cuantos mas habia asi (habia al menos otro:
#    incidencias_juguetes.ventas_riesgo).
# 🔑 Con el extractor del censo -el mismo, con sus mismos tests- no cuela. Ese es el motivo
#    de que haya UNA sola implementacion y no dos.
CASO_REAL = """comment on column public.sondeo_keepa.rank_drops_30d is
  'Caidas de rank en 30 dias (Keepa stats.salesRankDrops30). NULL = no se sabe. Mide ventas reales; '
  'ORDENA, no decide.';
create table public.sondeo_keepa (id int);"""
objs_real = [n for _, n in C.objetos_de(CASO_REAL)[0]]
eq('4e1. la palabra suelta en la prosa de un comentario NO cuela como objeto',
   'ventas' in objs_real, False)
eq('4e2. y el objeto que SI se crea, se pilla', 'sondeo_keepa' in objs_real, True)

_res = C.cubos(['ventas', 'sondeo_keepa', 'v_producto_amazon', 'tabla_fantasma'],
               [('sondeo_keepa_senales_identidad', CASO_REAL)])
eq('4e3. cubo 1 = lo que tiene fichero detras',
   [o for o, _ in _res[1]], ['v_producto_amazon'])
eq('4e4. cubo 2 = creado por el CONECTOR (sin fichero, con SQL en el registro)',
   [o for o, _ in _res[2]], ['sondeo_keepa'])
eq('4e5. cubo 3 = sin rastro en ninguna de las dos fuentes',
   [o for o, _ in _res[3]], ['tabla_fantasma', 'ventas'])
# 🔒 Y que el cubo 2 diga QUIEN lo aplico: sin eso es una acusacion sin firma.
eq('4e6. el cubo 2 nombra la entrada del registro que lo creo',
   _res[2][0][1], 'sondeo_keepa_senales_identidad')

# ── 5. LA REGLA DE LA CASA, EN EL PROPIO SQL ───────────────────────────────
sql = C.sql_del_censo(C.censar())
eq('5a. el SQL del censo NO menciona supabase_migrations',
   'supabase_migrations' in sql, False)
eq('5b. ni schema_migrations',
   'schema_migrations' in sql, False)
eq('5d. el SQL trae la rama de la huella (pg_get_viewdef / prosrc)',
   all(t in sql for t in ('pg_get_viewdef', 'prosrc', "'VIEJA'", "'vigente'")), True)
eq('5c. y consulta el catalogo real',
   all(t in sql for t in ('pg_class', 'pg_proc', 'information_schema.columns', 'pg_indexes')),
   True)

# ── 6. SOBRE LOS FICHEROS REALES: que haya material ────────────────────────
# 🔒 Si el parseo se rompiera del todo, todo saldria "no determinable" y el censo pasaria
#    sin comprobar nada: un verde vacio. Se afirma que hay material ANTES de fiarse.
filas = C.censar()
eq('6a. hay migraciones reales que censar', len(filas) > 20, True)
eq('6b. y la mayoria deja objeto localizable', sum(1 for f in filas if f[1]) > 15, True)
eq('6c. los _PRUEBA_ quedan fuera',
   any(m.startswith('_PRUEBA') for m, _, _, _ in filas), False)

print("\n" + "=" * 66)
if fallos:
    print(f"❌ {len(fallos)} FALLOS: " + ", ".join(fallos))
    sys.exit(1)
print("✅ Las tres trampas de la extraccion saltan, y el SQL no toca el registro.")
print("=" * 66)
