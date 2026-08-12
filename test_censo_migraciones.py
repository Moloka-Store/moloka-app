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

# ── 5. LA REGLA DE LA CASA, EN EL PROPIO SQL ───────────────────────────────
sql = C.sql_del_censo(C.censar())
eq('5a. el SQL del censo NO menciona supabase_migrations',
   'supabase_migrations' in sql, False)
eq('5b. ni schema_migrations',
   'schema_migrations' in sql, False)
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
   any(m.startswith('_PRUEBA') for m, _, _ in filas), False)

print("\n" + "=" * 66)
if fallos:
    print(f"❌ {len(fallos)} FALLOS: " + ", ".join(fallos))
    sys.exit(1)
print("✅ Las tres trampas de la extraccion saltan, y el SQL no toca el registro.")
print("=" * 66)
