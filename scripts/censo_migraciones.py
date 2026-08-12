# -*- coding: utf-8 -*-
"""CENSO DE MIGRACIONES **POR OBJETO**. Nunca por el registro.

🔴 POR QUE EXISTE. El 11-ago-2026 se descubrio, por casualidad y buscandola a mano, que
   `v_salud_escaner` estaba fusionada desde hacia horas y NO existia en produccion. La
   pregunta obvia -"¿cuantas mas hay asi?"- no se podia contestar, porque el instrumento
   que parecia servir no sirve:

     🔬 38 ficheros de migracion en main · 50 entradas en supabase_migrations · CASAN 5.
        33 ficheros sin entrada. 45 entradas sin fichero.

   `aplicar-migracion.yml` -el canal correcto- aplica con `psql` crudo y NO escribe una
   sola linea en ese registro; solo queda anotado lo que entra por el conector, a menudo
   con nombres libres que no corresponden a ningun fichero. O sea que **el registro es
   ciego justo a lo que sigue el procedimiento**. Un censo contra el habria dado 33 falsas
   ausencias, y las 33 habrian enterrado la unica real.

🔑 LA REGLA QUE APLICA ESTE GUION: se comprueba EL OBJETO. `pg_class`, `pg_proc`,
   `information_schema.columns`, `pg_indexes`. El registro no se lee en ningun punto —
   ni para decidir, ni para informar.

⚠️ Y LO QUE NO PUEDE COMPROBAR, LO DICE. Una migracion que solo cambia ACL, comentarios o
   datos no deja un objeto que buscar. Esas salen como **NO DETERMINABLE**, nunca como
   correctas. Un censo que llama "bien" a lo que no ha mirado es peor que no tenerlo.

   🔒 Es el patron del NULL confesor (CLAUDE.md §3) aplicado a una herramienta: tres
      estados -existe, FALTA, no lo se- y jamas dos.

🔴 EL PUNTO CIEGO, DICHO ANTES DE QUE MUERDA: esto comprueba que el objeto EXISTE, no que
   este AL DIA. Por eso la columna dice `existe` y no `presente` — una vista puede estar ahi
   con la definicion vieja y este censo la da por buena.

   🔬 Y no es teorico: se ve en la salida del propio censo. `v_escaner_ultimo` aparece DOS
      veces, una por cada migracion que lo toca —`2026-08-10_v_escaner_ultimo` y
      `..._clave_real`, que arreglo la clave de deduplicacion de (ean,proveedor) a
      (proveedor,ean,es_case)— y las dos filas dicen lo mismo. **La segunda es invisible
      aqui.** Durante las horas en que produccion tuvo la vista con la clave mal, este censo
      habria dicho `existe`.

   ⇒ Lo que cierra ese hueco es una HUELLA declarada (`-- @huella: es_case`) que se busque
     en `pg_get_viewdef` / `prosrc`. No esta hecho: es el siguiente escalon, y va en su PR.
     Mientras tanto, `existe` significa existe y nada mas.

USO
     python scripts/censo_migraciones.py            # imprime el SQL del censo
     python scripts/censo_migraciones.py --resumen  # solo el recuento de la extraccion

   El SQL que imprime se ejecuta contra el entorno que se quiera (lo hace
   `censo-migraciones.yml`). El guion NO se conecta a ninguna base: separa extraer de
   consultar a proposito, para que la parte fragil -el parseo- se pueda probar sola.
"""
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, 'migraciones')

# Ficheros que NUNCA se aplican: son bancos de pruebas con el aviso en el nombre.
PREFIJOS_IGNORADOS = ('_PRUEBA',)

# ---------------------------------------------------------------------------
# EXTRACCION
#
# 🔴 EL FALLO QUE ESTE REGEX YA COMETIO, para que no vuelva: la primera version usaba
#    `[a-z_.]+` y se comio el `0` final de `moloka_buzones_fase0`. El censo dio la funcion
#    por AUSENTE cuando estaba. **Un nombre de objeto puede llevar digitos.** De ahi el
#    `[a-z0-9_]` de abajo, y el caso con nombre en el banco de pruebas.
# ---------------------------------------------------------------------------
RE_OBJETO = re.compile(
    r'^\s*create\s+(?:or\s+replace\s+)?'
    r'(view|materialized\s+view|table|function|index|unique\s+index)\s+'
    r'(?:if\s+not\s+exists\s+)?'
    r'(?:public\.)?"?([a-z0-9_]+)"?',
    re.I | re.M)

RE_COLUMNA = re.compile(
    r'^\s*alter\s+table\s+(?:public\.)?"?([a-z0-9_]+)"?\s*'
    r'(?:.|\n)*?add\s+column\s+(?:if\s+not\s+exists\s+)?"?([a-z0-9_]+)"?',
    re.I | re.M)

# Declaracion explicita, para cuando la extraccion no llega o el objeto no se crea aqui:
#     -- @objeto: vista v_salud_escaner
#     -- @objeto: columna keepa_escaparate.bb_envio
RE_DECLARADO = re.compile(r'^--\s*@objeto:\s*(\w+)\s+([a-z0-9_.]+)\s*$', re.I | re.M)

TIPO_SQL = {'view': 'vista', 'materialized view': 'vista', 'table': 'tabla',
            'function': 'funcion', 'index': 'indice', 'unique index': 'indice'}


def sin_comentarios(texto):
    """🔒 Sin esto el censo es un adorno, y esta comprobado haciendolo saltar: el patron
    casa igual dentro de un comentario, asi que una migracion que MENCIONA
    `create view x` en su cabecera explicativa -cosa que aqui hacen todas- declararia un
    objeto que no crea. Es el mismo vicio que ya se cazo en tests/alertas-alcanzables
    del repo de la v2: lo que se lee como texto no distingue codigo de comentario."""
    fuera = re.sub(r'/\*[\s\S]*?\*/', '', texto)
    return '\n'.join(l for l in fuera.split('\n') if not l.lstrip().startswith('--'))


def objetos_de(texto):
    """(tipo, nombre) que esta migracion deja detras. Vacio = no determinable."""
    declarados = [(t.lower(), n.lower()) for t, n in RE_DECLARADO.findall(texto)]
    if declarados:
        return declarados, 'declarado'          # lo explicito manda sobre lo adivinado
    cuerpo = sin_comentarios(texto)
    out = [(TIPO_SQL[t.lower().replace('  ', ' ')], n.lower())
           for t, n in RE_OBJETO.findall(cuerpo)]
    out += [('columna', f'{t.lower()}.{c.lower()}') for t, c in RE_COLUMNA.findall(cuerpo)]
    # únicos conservando el orden
    return list(dict.fromkeys(out)), 'extraido'


def censar():
    filas = []
    for f in sorted(os.listdir(DIR)):
        if not f.endswith('.sql') or f.startswith(PREFIJOS_IGNORADOS):
            continue
        texto = io.open(os.path.join(DIR, f), encoding='utf-8').read()
        objs, origen = objetos_de(texto)
        filas.append((f[:-4], objs, origen))
    return filas


def sql_del_censo(filas):
    """Un SELECT que dice, por objeto, si esta. Sin tocar supabase_migrations."""
    vals = []
    for mig, objs, _ in filas:
        for tipo, nombre in objs:
            vals.append("('{}','{}','{}')".format(
                mig.replace("'", "''"), tipo, nombre.replace("'", "''")))
    if not vals:
        return "select 'sin objetos que censar' aviso;"
    return """with o(migracion, tipo, nombre) as (values
  """ + ",\n  ".join(vals) + """
)
select o.migracion, o.tipo, o.nombre,
       case
         when o.tipo = 'columna' then
           case when exists (select 1 from information_schema.columns
                              where table_schema='public'
                                and table_name = split_part(o.nombre,'.',1)
                                and column_name = split_part(o.nombre,'.',2))
                then 'existe' else 'FALTA' end
         when o.tipo = 'funcion' then
           case when exists (select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                              where n.nspname='public' and p.proname=o.nombre)
                then 'existe' else 'FALTA' end
         when o.tipo = 'indice' then
           case when exists (select 1 from pg_indexes
                              where schemaname='public' and indexname=o.nombre)
                then 'existe' else 'FALTA' end
         else
           case when exists (select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
                              where n.nspname='public' and c.relname=o.nombre)
                then 'existe' else 'FALTA' end
       end as estado
from o
order by estado, o.migracion, o.nombre;"""


if __name__ == '__main__':
    filas = censar()
    con = [f for f in filas if f[1]]
    sin = [f for f in filas if not f[1]]
    if '--resumen' in sys.argv:
        print(f"migraciones: {len(filas)}")
        print(f"  con objeto censable : {len(con)}  ({sum(len(f[1]) for f in con)} objetos)")
        print(f"  NO DETERMINABLES    : {len(sin)}  (solo ACL, comentarios o datos)")
        for m, _, _ in sin:
            print(f"      · {m}")
        sys.exit(0)
    print(sql_del_censo(filas))
    # ⚠️ Las no determinables van al SQL como aviso, para que no desaparezcan del informe:
    #    lo que no se censa tiene que verse igual que lo que se censa.
    if sin:
        print("\n-- NO DETERMINABLES (solo ACL, comentarios o datos): "
              + ", ".join(m for m, _, _ in sin))
