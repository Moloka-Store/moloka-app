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

# ---------------------------------------------------------------------------
# LA HUELLA: lo que distingue EXISTE de VIGENTE.
#
# 🔬 De los 61 objetos censados, **9 los tocan DOS migraciones** — v_escaner_ultimo,
#    v_amazon_se_despierta, v_trackeador_cola, v_velocidad_ventas, v_keepa_bb_envio,
#    v_demanda_asin_ultima, v_rentabilidad_transacciones, frescura_informes y
#    moloka_buzones_fase0. En todos ellos la SEGUNDA es invisible a una comprobacion de
#    existencia: el objeto ya estaba, lo que cambio es su contenido.
#
# Una huella es un trozo de texto que TIENE que aparecer en la definicion viva
# (`pg_get_viewdef` de una vista, `prosrc` de una funcion). Si esta declarada y no
# aparece → el objeto existe pero es VIEJO.
#
#   -- @huella: es_case
#
# 🔒 POR QUE LAS VIEJAS SE DECLARAN AQUI Y NO DENTRO DE SU .sql: una migracion **ya
#    aplicada no se edita**. `aplicar-migracion.yml` imprime su sha256 en el log de
#    Actions como rastro de que se corrio exactamente; tocarle una linea -aunque sea un
#    comentario- rompe para siempre el contraste `git show origin/main:... | sha256sum`.
#    Es la misma regla que obligo a crear `2026-08-11_bb_envio_dos_fotos.sql` en vez de
#    editar el fichero donde nacio aquel comentario.
#    ⇒ **Las migraciones NUEVAS declaran su huella en linea. Las ya aplicadas, aqui.**
#
# ⚠️ Y solo se apunta lo que se ha COMPROBADO. Rellenar las nueve de memoria seria
#    inventarse la prueba: las que no tienen huella salen listadas como punto ciego vivo,
#    que es informacion, no un hueco escondido.
HUELLAS_RETRO = {
    # Verificado en produccion el 11-ago-2026: la vista lleva la clave real de dedup
    # (proveedor, ean, es_case) en vez de la corta (ean, proveedor).
    ('2026-08-10_v_escaner_ultimo_clave_real', 'v_escaner_ultimo'): 'es_case',
    # Verificado en produccion el 12-ago-2026 (Fernando, mirando pg_get_viewdef):
    # compara por dominio y devuelve NULL donde no hay con que comparar.
    ('2026-08-11_v_amazon_se_despierta_sin_previo', 'v_amazon_se_despierta'):
        'dias_desde_foto_anterior',
}

RE_HUELLA = re.compile(r'^--\s*@huella:\s*(\S.*?)\s*$', re.I | re.M)

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


#: Solo estos tipos tienen un cuerpo que pueda quedarse viejo. Una columna o un indice
#: existen o no existen: no hay version antigua que distinguir.
TIPOS_CON_CUERPO = ('vista', 'funcion')


def huella_de(migracion, texto, objetos):
    """{nombre_objeto: huella} de esta migracion. Vacio = no hay huella declarada.

    Prioridad: la tabla de retro (migraciones ya aplicadas, que NO se editan) y luego
    el `-- @huella:` en linea.

    ⚠️ El `@huella` en linea solo se aplica si la migracion deja UN objeto con cuerpo.
       Con dos, cual de los dos le toca es una conjetura, y aqui no se conjetura: se
       ignora y se avisa. Para ese caso se usa la tabla de retro, que nombra el objeto.
    """
    out = {}
    for (mig, nom), h in HUELLAS_RETRO.items():
        if mig == migracion:
            out[nom] = h
    enlinea = RE_HUELLA.findall(texto)
    if enlinea:
        conCuerpo = [n for t, n in objetos if t in TIPOS_CON_CUERPO]
        if len(conCuerpo) == 1:
            out.setdefault(conCuerpo[0], enlinea[0])
        else:
            out['__ambigua__'] = (
                f"@huella en linea ignorada: la migracion deja {len(conCuerpo)} objetos "
                f"con cuerpo y no dice a cual toca")
    return out


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
        filas.append((f[:-4], objs, origen, huella_de(f[:-4], texto, objs)))
    return filas


def puntos_ciegos(filas):
    """Objetos que tocan DOS o mas migraciones y NO tienen huella declarada.

    🔴 Ahi el censo dice `existe` y no puede saber si es la version nueva o la vieja. Se
       listan a proposito: un punto ciego declarado es informacion; uno callado es un
       verde falso esperando.
    """
    por_obj = {}
    for mig, objs, _, _ in filas:
        for tipo, nom in objs:
            if tipo in TIPOS_CON_CUERPO:
                por_obj.setdefault(nom, []).append(mig)
    conHuella = {n for (_, n) in HUELLAS_RETRO}
    for _, _, _, hs in filas:
        conHuella |= {k for k in hs if k != '__ambigua__'}
    return sorted((n, ms) for n, ms in por_obj.items()
                  if len(ms) > 1 and n not in conHuella)


def sql_del_censo(filas):
    """Un SELECT que dice, por objeto, si esta — y si la huella declarada sigue dentro.

    Sin tocar supabase_migrations en ningun punto.
    """
    vals = []
    for mig, objs, _, huellas in filas:
        for tipo, nombre in objs:
            h = huellas.get(nombre)
            vals.append("('{}','{}','{}',{})".format(
                mig.replace("'", "''"), tipo, nombre.replace("'", "''"),
                "'{}'".format(h.replace("'", "''")) if h else 'null'))
    if not vals:
        return "select 'sin objetos que censar' aviso;"
    return """with o(migracion, tipo, nombre, huella) as (values
  """ + ",\n  ".join(vals) + """
)
select o.migracion, o.tipo, o.nombre,
       case
         -- 🔑 LA HUELLA PRIMERO: existir no es estar vigente. Si la migracion declara un
         --    trozo que su version tiene que dejar en la definicion viva y no aparece, el
         --    objeto esta pero es el VIEJO — y eso es lo que una comprobacion de
         --    existencia no ve. Solo aplica a lo que tiene cuerpo (vistas y funciones).
         when o.huella is not null and o.tipo = 'vista' then
           case when not exists (select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
                                  where n.nspname='public' and c.relname=o.nombre)
                     then 'FALTA'
                when pg_get_viewdef(('public.'||o.nombre)::regclass, true) like '%'||o.huella||'%'
                     then 'vigente'
                else 'VIEJA' end
         when o.huella is not null and o.tipo = 'funcion' then
           case when not exists (select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                                  where n.nspname='public' and p.proname=o.nombre)
                     then 'FALTA'
                when exists (select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                              where n.nspname='public' and p.proname=o.nombre
                                and p.prosrc like '%'||o.huella||'%')
                     then 'vigente'
                else 'VIEJA' end
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
    ciegos = puntos_ciegos(filas)
    nHuellas = sum(len([k for k in f[3] if k != '__ambigua__']) for f in filas)
    ambiguas = [m for m, _, _, hs in filas if '__ambigua__' in hs]
    if '--resumen' in sys.argv:
        print(f"migraciones: {len(filas)}")
        print(f"  con objeto censable : {len(con)}  ({sum(len(f[1]) for f in con)} objetos)")
        print(f"  NO DETERMINABLES    : {len(sin)}  (solo ACL, comentarios o datos)")
        for m, _, _, _ in sin:
            print(f"      · {m}")
        print(f"  con HUELLA declarada: {nHuellas}  (se distingue vigente de VIEJA)")
        print(f"  PUNTOS CIEGOS VIVOS : {len(ciegos)}  (2+ migraciones y sin huella)")
        for n, ms in ciegos:
            print(f"      · {n:30} <- {', '.join(ms)}")
        for m in ambiguas:
            print(f"  ⚠️ {m}: @huella en linea IGNORADA (varios objetos con cuerpo)")
        sys.exit(0)
    print(sql_del_censo(filas))
    # ⚠️ Lo que el censo NO cubre va en el mismo informe, para que se vea igual que lo que
    #    si cubre. Un hueco callado se lee como un verde.
    if sin:
        print("\n-- NO DETERMINABLES (solo ACL, comentarios o datos): "
              + ", ".join(m for m, _, _, _ in sin))
    if ciegos:
        print("-- PUNTO CIEGO (2+ migraciones tocan el objeto y no hay huella: 'existe' NO "
              "dice si es la version nueva): "
              + ", ".join(n for n, _ in ciegos))
    for m in ambiguas:
        print(f"-- AVISO {m}: @huella en linea ignorada (varios objetos con cuerpo)")
