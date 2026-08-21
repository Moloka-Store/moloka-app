# -*- coding: utf-8 -*-
"""¿Le falta a STAGING algo que PRODUCCION ya tiene? Compara dos censos por objeto.

🔴 POR QUE EXISTE, y lo destapo un procesador el 21-ago-2026. Esa manana se restauro
   staging para ensayar una migracion. La restauracion trae el backup de ANOCHE, asi que
   **deshizo una migracion aplicada ese mismo dia** (`paneu_aptos.pendiente_evaluacion`,
   que SI estaba en produccion). El procesador de PanEU murio despues con
   `column "pendiente_evaluacion" does not exist`.

   Tuvimos suerte: choco con una columna que no existia y grito. Fernando lo dijo mejor:

     🔑 «La proxima vez puede ser una migracion que se aplique LIMPIAMENTE en un staging al
        que le falta la columna con la que iba a chocar en produccion.»

   Ese ensayo saldria VERDE sin probar nada, y el verde de un ensayo es la unica red que
   hay para no romper la operativa de Elena. No es una molestia: es la escalera mintiendo.

🔑 LA DISTINCION QUE HACE ESTO, y es la que decide si el aviso sirve o es ruido:

     · falta en staging **y tambien en produccion**  → NORMAL. Es la migracion que vas a
       ensayar ahora mismo, o una fusionada y aun sin aplicar en ningun sitio. Callado.
     · falta en staging **y produccion SI la tiene** → 🔴 PELIGRO. Staging va por detras y
       cualquier ensayo encima corre sobre una base que no se parece al destino.

   Sin mirar produccion no se pueden separar, y entonces el aviso saltaria SIEMPRE —
   incluida la migracion en vuelo— y se dejaria de leer en dos semanas. Es la cara B de
   CLAUDE.md §3: una alarma que siempre esta roja tampoco informa.

🔒 Y COMPARA POR OBJETO, no por el registro de migraciones: `supabase_migrations` es ciego
   justo a lo que entra por el canal correcto (38 ficheros contra 50 entradas, casan 5).
   El censo lo hace ya `scripts/censo_migraciones.py`; aqui solo se restan sus dos salidas.
   Una sola implementacion del censo, dos entornos.

USO
     python scripts/comparar_censos.py <censo_produccion.txt> <censo_staging.txt>

   Cada fichero es la salida de `psql -t -A -F'|'` sobre el SQL que imprime
   `censo_migraciones.py`: migracion|tipo|nombre|veredicto.
"""
import io
import sys

from anti_cero import exigir_poblacion

# ⚠️ LA SALIDA VA EN ASCII PELADO, y no es descuido de estilo: los emoji revientan en
#    una consola cp1252 y el `print` muere A MEDIAS — con lo que los NOMBRES de las
#    migraciones, que son lo unico que hace util este aviso, se quedan sin imprimir.
#    Un aviso que se corta antes de decir que falta no avisa de nada. En los
#    comentarios se quedan: esos no se imprimen.

# Veredictos que el censo puede dar. `existe`/`vigente` = esta; el resto, no o no se sabe.
PRESENTES = ('existe', 'vigente')
AUSENTES = ('FALTA',)


def leer(ruta):
    """Las filas del censo, indexadas por objeto. Devuelve {(mig,tipo,nombre): veredicto}."""
    fuera = {}
    with io.open(ruta, encoding='utf-8') as fh:
        for linea in fh:
            partes = [p.strip() for p in linea.rstrip('\n').split('|')]
            if len(partes) < 4:
                continue
            mig, tipo, nombre, veredicto = partes[0], partes[1], partes[2], partes[3]
            if not mig or mig.startswith('('):   # el pie de psql («(N rows)»)
                continue
            fuera[(mig, tipo, nombre)] = veredicto
    return fuera


def main():
    if len(sys.argv) < 3:
        sys.exit('Uso: comparar_censos.py <censo_produccion.txt> <censo_staging.txt>')
    prod = leer(sys.argv[1])
    stg = leer(sys.argv[2])

    # 🔴 LA COMPROBACION DE QUE HAY ALGO QUE COMPARAR, que es la que convierte esto en una
    #    medida y no en un tramite. Un censo vacio —porque el psql fallo, porque el SQL no
    #    se genero, porque el fichero quedo a cero bytes— haria que la resta diera CERO
    #    diferencias y el paso saliera verde sin haber mirado nada. Es el `bash -n` sobre
    #    0 bytes, otra vez.
    # 🔒 Por `exigir_poblacion`, no a mano: esta comprobacion se habia escrito tres
    #    veces en un dia y la tercera es la que no se ve venir. Ver `docs/guion-anti-cero.md`.
    exigir_poblacion('objetos en el censo de PRODUCCION', prod)
    exigir_poblacion('objetos en el censo de STAGING', stg)

    faltan = []      # 🔴 produccion lo tiene y staging no
    viejas = []      # 🟠 los dos lo tienen, pero el de staging es la version vieja
    en_vuelo = []    # normal: no esta en ninguno de los dos

    for clave, v_prod in sorted(prod.items()):
        v_stg = stg.get(clave)
        mig, tipo, nombre = clave
        if v_prod in PRESENTES and v_stg in AUSENTES:
            faltan.append((mig, tipo, nombre))
        elif v_prod == 'vigente' and v_stg == 'VIEJA':
            viejas.append((mig, tipo, nombre))
        elif v_prod in AUSENTES and v_stg in AUSENTES:
            en_vuelo.append(mig)

    print('== STAGING contra PRODUCCION, por objeto ==')
    print('   objetos censados      produccion %d  ·  staging %d' % (len(prod), len(stg)))
    # 🔒 Se dice en alto lo que se ha decidido NO avisar. Un filtro silencioso es
    #    indistinguible de un filtro que no funciona.
    if en_vuelo:
        print('   en vuelo (no estan en NINGUNO de los dos, y eso es normal): %d objeto(s)'
              % len(en_vuelo))
        for m in sorted(set(en_vuelo)):
            print('     · %s' % m)

    if not faltan and not viejas:
        print('')
        print('   OK · staging no va por detras de produccion en ningun objeto.')
        return 0

    print('')
    print('  ==================================================================')
    print('  STAGING VA POR DETRAS DE PRODUCCION. NO LANCES UN ENSAYO ENCIMA.')
    print('  ==================================================================')
    if faltan:
        print('')
        print('  FALTAN en staging y produccion SI las tiene:')
        for mig, tipo, nombre in faltan:
            print('    · %-52s (%s %s)' % (mig, tipo, nombre))
    if viejas:
        print('')
        print('  ESTAN pero con la version VIEJA en staging:')
        for mig, tipo, nombre in viejas:
            print('    · %-52s (%s %s)' % (mig, tipo, nombre))
    print('')
    print('  POR QUE IMPORTA: un ensayo sobre una base a la que le falta algo puede salir')
    print('  VERDE sin probar nada — se aplicaria limpiamente aqui y chocaria en')
    print('  produccion contra el objeto que aqui no existe. El verde de un ensayo es la')
    print('  unica red que hay para no romper la operativa de Elena.')
    print('')
    print('  QUE HACER: aplicar a staging las de arriba, una por una, con')
    print('  `aplicar-migracion.yml` (entorno=staging, modo=aplicar), y volver a mirar.')
    print('  No se reaplican solas a proposito: cual toca y en que orden lo decide quien')
    print('  lo lanza, y una cadena automatica sobre la base de otro es peor problema.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
