# -*- coding: utf-8 -*-
# ============================================================================
# BANCO DE `sql_de_nivel_superior()` -- el despojador del cerrojo 4
# ----------------------------------------------------------------------------
# POR QUE EXISTE. El 28-ago-2026 el cerrojo 4 de `aplicar-migracion.yml` aborto
# una migracion buena por dos falsos positivos: un `end;` de plpgsql DENTRO del
# cuerpo de una funcion, y `CONCURRENTLY` en comentarios, dentro de un cuerpo
# `$function$` y dentro de un mensaje de `RAISE EXCEPTION`. El propio workflow
# habia predicho el primero por escrito meses antes.
#
# 🔑 El arreglo no fue un regex mas listo: fue QUITAR el texto antes de mirar.
#    Y una regla que se convierte en funcion necesita su test, o vuelve a ser
#    una nota que alguien tiene que recordar.
#
# 🔴 LAS DOS DIRECCIONES, y la segunda es la que importa. Relajar un cerrojo es
#    facil; lo dificil es demostrar que DESPUES DE RELAJARLO sigue cazando lo
#    suyo. Aqui la mitad de los casos son cosas que TIENEN que seguir saltando.
#    Un cerrojo que se relaja sin eso es peor que no tenerlo.
# ============================================================================
import io, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
from censo_migraciones import sql_de_nivel_superior  # noqa: E402

# Los MISMOS regex que usa el cerrojo. Si alli cambian y aqui no, este banco deja
# de medir el cerrojo y pasa a medir una copia suya -- por eso van citados tal cual.
RE_TX = re.compile(
    r'^[ \t]*(begin|commit|rollback|abort|end)[ \t]*(work|transaction)?[ \t]*'
    r'(and[ \t]+(no[ \t]+)?chain[ \t]*)?;|^[ \t]*start[ \t]+transaction', re.I | re.M)
RE_CC = re.compile(r'\bconcurrently\b', re.I)


def mide(sql):
    limpio = sql_de_nivel_superior(sql)
    return len(RE_TX.findall(limpio)), len(RE_CC.findall(limpio))


# (nombre, sql, (tx_esperados, concurrently_esperados))
CASOS = [
    # ── TIENE que seguir saltando ────────────────────────────────────────────
    ("CONCURRENTLY de verdad, nivel superior",
     "create unique index concurrently mi_idx on public.t (a);\n", (0, 1)),
    ("REFRESH CONCURRENTLY de verdad",
     "refresh materialized view concurrently public.mv;\n", (0, 1)),
    ("COMMIT de verdad",
     "create table t(a int);\ncommit;\n", (1, 0)),
    ("BEGIN de verdad",
     "begin;\ncreate table t(a int);\n", (1, 0)),
    ("END; de verdad a nivel superior",
     "end;\n", (1, 0)),
    ("ABORT; de verdad",
     "abort;\n", (1, 0)),
    ("COMMIT AND CHAIN; de verdad",
     "commit and chain;\n", (1, 0)),
    ("START TRANSACTION de verdad",
     "start transaction;\n", (1, 0)),
    ("CONCURRENTLY detras de codigo en la misma linea (falla CERRADO a proposito)",
     "create table t(a int); -- concurrently\n", (0, 1)),

    # ── NO debe saltar: es texto, no SQL ─────────────────────────────────────
    ("CONCURRENTLY solo en un comentario de linea",
     "-- ojo con concurrently aqui\ncreate table t(a int);\n", (0, 0)),
    ("CONCURRENTLY en un comentario de bloque",
     "/* concurrently\n   y commit; */\ncreate table t(a int);\n", (0, 0)),
    ("CONCURRENTLY dentro de un cuerpo $$",
     "create function f() returns void as $$\nbegin\n"
     "  refresh materialized view concurrently public.mv;\nend;\n$$ language plpgsql;\n", (0, 0)),
    ("CONCURRENTLY dentro de una cadena",
     "select 'usa concurrently'::text;\n", (0, 0)),
    ("end; dentro de un cuerpo $function$",
     "create function f() returns void as $function$\nbegin\n  null;\nend;\n"
     "end $function$ language plpgsql;\n", (0, 0)),
    ("commit; dentro de un cuerpo con etiqueta rara",
     "do $guardas_2$\nbegin\ncommit;\nend\n$guardas_2$;\n", (0, 0)),
    ("dos cuerpos seguidos, cada uno con su etiqueta",
     "do $a$ begin null; end $a$;\ndo $b$ begin commit; end $b$;\n", (0, 0)),
    ("cadena con comilla escapada dentro",
     "select 'no es un commit; ni un ''concurrently'' de verdad';\n", (0, 0)),
]

fallos = 0
for nombre, sql, esperado in CASOS:
    got = mide(sql)
    ok = got == esperado
    fallos += (not ok)
    print("  %-4s %-62s esperado TX=%d CC=%d | obtenido TX=%d CC=%d"
          % ("OK" if ok else "MAL", nombre[:62], esperado[0], esperado[1], got[0], got[1]))

# 🔒 Y el caso real que lo motivo todo: la migracion de verdad, no un ejemplo.
#    Un banco que solo prueba casos inventados no demuestra que el fichero que
#    fallaba deje de fallar.
REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'migraciones', '2026-08-28_repo_trackeador_objetos_vivos.sql')
if os.path.exists(REAL):
    crudo = io.open(REAL, encoding='utf-8', newline='').read()
    tx_crudo, cc_crudo = len(RE_TX.findall(crudo)), len(RE_CC.findall(crudo))
    tx_lim, cc_lim = mide(crudo)
    # Sobre el fichero CRUDO tiene que verse el falso positivo (si no, este caso
    # no discrimina y estaria midiendo cualquier cosa).
    if (tx_crudo, cc_crudo) != (1, 4):
        print("  MAL  el fichero real ya no dispara el falso positivo (TX=%d CC=%d, se esperaba 1 y 4):"
              " este caso ha dejado de medir nada" % (tx_crudo, cc_crudo))
        fallos += 1
    elif (tx_lim, cc_lim) != (0, 0):
        print("  MAL  la migracion real sigue disparando el cerrojo tras despojar (TX=%d CC=%d)"
              % (tx_lim, cc_lim))
        fallos += 1
    else:
        print("  OK   la migracion real: crudo TX=1 CC=4 -> nivel superior TX=0 CC=0")
else:
    print("  MAL  no esta la migracion real en %s: el caso que motivo todo esto no se ha probado" % REAL)
    fallos += 1

print()
print('TODO OK' if fallos == 0 else '%d FALLOS' % fallos)
raise SystemExit(1 if fallos else 0)
