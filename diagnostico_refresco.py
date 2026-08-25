# -*- coding: utf-8 -*-
"""DIAGNOSTICO · ¿puede el usuario de los procesadores refrescar las materializadas?

🔴 LA PREGUNTA QUE CONTESTA, Y POR QUE NINGUN TESTIGO DE LA MIGRACION LA ALCANZA.
   `REFRESH MATERIALIZED VIEW` no se resuelve con permisos: EXIGE SER DUENO. Ni
   SELECT ni ALL PRIVILEGES valen. La mv nace con dueno `postgres`, pero el
   refresco lo lanza el PROCESADOR, que se conecta con `DB_URL` del ENTORNO --otra
   conexion, en otro momento, y posiblemente con otro usuario--.
   Los testigos de la migracion corren DENTRO de la migracion, con el rol de la
   migracion. No pueden contestar por el procesador.

   Si eso no cuadrara, el fallo seria mudo: migracion limpia, todos los verdes
   verdes, y el primer informe que entre no refresca nada. Mv congelada, pantalla
   con ventas viejas.

🔴 AQUI EL FALLO ES RUIDOSO, Y ES LO CONTRARIO DE LO QUE HACE EL PROCESADOR.
   Dentro de `procesador_ledger.py` y compania, `refrescar_vistas()` se traga la
   excepcion y devuelve False A PROPOSITO: el commit ya paso, el informe esta
   escrito, y tumbar la corrida haria que alguien volviera a subirlo.
   AQUI NO HAY NINGUNA CARGA QUE PROTEGER. Esto es un diagnostico, y **un verde
   que no ha refrescado no vale para nada**: si `refrescar_vistas()` devuelve
   False, este job sale en ROJO.

🔒 NUNCA SE IMPRIME `DB_URL` NI UN TROZO DE ELLA. Los logs de Actions se ven.
   `current_user` si --es el dato que se busca--, la cadena de conexion no.

🔒 SE PUEDE LANZAR CUANDO SEA: refrescar una materializada que ya esta al dia no
   cambia ni un dato. Lo unico que produce es el log.

USO:  workflow `diagnostico-refresco.yml`, a mano. Sin reloj.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import conectar_bd, refrescar_vistas, REFRESCOS_POR_FUENTE  # noqa: E402

DB_URL = os.environ.get('DB_URL', '')
ENTORNO = os.environ.get('ENTORNO', 'staging').strip().lower()
FUENTE = os.environ.get('FUENTE', 'ledger').strip().lower()

# Las que el mapa conoce mas las que solo mueven la copia del Trackeador.
FUENTES_VALIDAS = set(REFRESCOS_POR_FUENTE) | {'keepa'}


def main():
    print("=== DIAGNOSTICO DEL REFRESCO DE MATERIALIZADAS ===", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print(f"FUENTE simulada: {FUENTE}", flush=True)
    print("=" * 70, flush=True)

    if not DB_URL:
        sys.exit("Falta DB_URL. Revisa los secrets del workflow.")
    # 🔴 UNA FUENTE VALIDA NO ES "una que esta en el mapa de materializadas". Desde el
    #    25-ago-2026, `refrescar_vistas` refresca TAMBIEN la copia del Trackeador, y eso
    #    corre para CUALQUIER fuente --tenga materializadas propias o no--. `keepa` es
    #    justo ese caso: no tiene ninguna nuestra y si alimenta la suya.
    #    Este guardarrail rechazaba `keepa` y habria hecho creer que no se puede
    #    diagnosticar el camino que mas falta hacia comprobar.
    if FUENTE not in FUENTES_VALIDAS:
        sys.exit(f"FUENTE desconocida: {FUENTE!r}. Conocidas: "
                 f"{', '.join(sorted(FUENTES_VALIDAS))}")

    # 🔒 La MISMA puerta que usan los procesadores. Si se conectara de otra forma,
    #    este diagnostico contestaria sobre una conexion que no es la que importa.
    con = conectar_bd(DB_URL)
    cur = con.cursor()

    cur.execute("SELECT current_user, current_database(), version()")
    quien, base, version = cur.fetchone()
    print(f"\n--- QUIEN SE CONECTA ---", flush=True)
    print(f"   · current_user     : {quien}", flush=True)
    print(f"   · base             : {base}", flush=True)
    print(f"   · arquitectura     : "
          f"{'aarch64' if 'aarch64' in version else 'x86_64' if 'x86_64' in version else '?'}",
          flush=True)

    print(f"\n--- ¿ES DUENO DE LAS MATERIALIZADAS DE ESTA FUENTE? ---", flush=True)
    puede_todas = True
    for vista in REFRESCOS_POR_FUENTE.get(FUENTE, ()):
        cur.execute("SELECT to_regclass(%s)", (f'public.{vista}',))
        if cur.fetchone()[0] is None:
            print(f"   · {vista}: NO EXISTE en {ENTORNO}. La migracion que la crea no "
                  f"se ha aplicado aqui.", flush=True)
            puede_todas = False
            continue
        # 🔑 `pg_has_role(..., 'MEMBER')` y no una comparacion de nombres: ser dueno
        #    o ser MIEMBRO del rol dueno valen los dos para REFRESH, y compararlos
        #    por igualdad daria un falso rojo con un usuario que si puede.
        cur.execute("""
            SELECT pg_get_userbyid(c.relowner),
                   pg_has_role(current_user, c.relowner, 'MEMBER')
              FROM pg_class c WHERE c.oid = %s::regclass
        """, (f'public.{vista}',))
        dueno, es_dueno = cur.fetchone()
        marca = 'SI' if es_dueno else 'NO'
        print(f"   · {vista}: dueno={dueno} · {quien} es dueno o miembro: {marca}", flush=True)
        if not es_dueno:
            puede_todas = False

    if not puede_todas:
        print(f"\n⚠️  Segun el catalogo, {quien} NO puede refrescar todo. Se intenta "
              f"igual: el catalogo dice lo que esta escrito, y lo que decide es "
              f"ejercerlo.", flush=True)

    # 🔴 CERRAR LA TRANSACCION QUE ABRIERON MIS PROPIOS SELECT. psycopg2 abre una
    #    transaccion implicita en la primera sentencia, asi que los `SELECT` de arriba
    #    han dejado una abierta. `refrescar_vistas()` ya se defiende de eso --lo aprendio
    #    aqui, con un rojo de este mismo workflow-- pero el que ensucia debe limpiar:
    #    si este diagnostico le pasa una conexion sucia, esta midiendo su propio desorden
    #    y no la pregunta que dice medir. Rollback y no commit: aqui solo se ha leido.
    con.rollback()

    # --- Y ahora la prueba de verdad: intentarlo ---
    t0 = time.time()
    ok = refrescar_vistas(con, FUENTE)
    ms = (time.time() - t0) * 1000
    print(f"\n--- RESULTADO ---", flush=True)
    print(f"   · refrescar_vistas('{FUENTE}') tardo {ms:.0f} ms en total", flush=True)

    cur.close()
    con.close()

    # 🔴 EL FALLO ES RUIDOSO AQUI. Ver la cabecera: es lo contrario de lo que hace
    #    dentro del procesador, y a proposito.
    if not ok:
        print(f"\n❌ EL REFRESCO NO HA IDO BIEN. Arriba esta el motivo exacto "
              f"(quien se conecta, quien es el dueno, y el error).", flush=True)
        print(f"   Esto NO significa que ninguna carga haya fallado: este workflow no "
              f"carga nada. Significa que, cuando entre un informe de verdad, la copia "
              f"NO se pondria al dia -- y la pantalla lo diria por su centinela.", flush=True)
        sys.exit(1)

    print(f"\n✅ {quien} PUEDE refrescar las materializadas de '{FUENTE}' en {ENTORNO}.",
          flush=True)


if __name__ == '__main__':
    main()
