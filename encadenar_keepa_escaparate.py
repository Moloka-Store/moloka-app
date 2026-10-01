# -*- coding: utf-8 -*-
# ============================================================================
# EL ENCADENADO DE KEEPA (encargo del 01-oct-2026) · la red de DEBAJO de la cola de la página
# ----------------------------------------------------------------------------
# Qué pasaba: los CSV de Keepa (uno por país) se cargan de uno en uno, porque el workflow
#   tiene un `concurrency` y la ruta de disparo de la v2 devuelve 409 si hay una corrida en
#   marcha. Quien los ponía en fila era la PÁGINA de Buzones (`dispararGrupo` → `disparo-cola`),
#   y esa fila solo vive mientras la página está abierta. El 01-oct-2026 se subieron cuatro y
#   se lanzaron dos: DE e IT se quedaron en el buzón sin cargar y sin aviso.
#
# Qué hace esto: corre como ÚLTIMO JOB de `procesar-keepa-escaparate.yml` (job `encadenar`),
#   al acabar una carga en `aplicar`, y:
#     1. lista el buzón `informes/keepa_escaparate/` (los .csv con nombre de Keepa subidos en
#        las últimas 48 h);
#     2. quita los YA CARGADOS: filas en `keepa_escaparate` o `keepa_escaparate_hist` con ese
#        `fichero` y `procesado_at` posterior a su subida (la identidad es nombre + hora de
#        subida: ver la cabecera del encadenado en procesador_keepa_escaparate.py);
#     3. quita los YA TRATADOS por una corrida verde de después de su subida. Hace falta además
#        del 2 porque una foto que se repite el mismo día NO llega al histórico (el archivado es
#        idempotente por asin+dominio+fecha) y, al caer de la viva, desaparece de las dos tablas;
#        y porque un salto en verde (ya cargado / superado) no deja filas;
#     4. quita los que ya han fallado DOS veces (el intento de la página o de quien sea, y un
#        reintento del encadenado). Nunca más de un reintento solo: no hay bucle;
#     5. si queda alguno y NO hay otra corrida en marcha, lanza el MÁS ANTIGUO (por hora de
#        subida) con `modo=aplicar`, `fichero=<ese>` y `encadenado=true`;
#     6. espera a VER la corrida nueva en la lista de GitHub antes de acabar. Mientras este job
#        corre, su corrida está «en marcha» y la ruta de la v2 da 409; si acabara antes de que
#        GitHub enseñe la nueva, habría unos segundos en los que la página vería el carril libre.
#
# 🔑 LA MEMORIA DE «QUÉ SE HA INTENTADO» VIVE EN GITHUB, NO EN UNA TABLA. Cada corrida lleva el
#    fichero en su título (`run-name: Keepa · <modo> · <fichero>`), así que contar intentos de
#    un fichero es contar corridas con ese título. Sin tabla nueva y sin tocar la base.
# 🔒 La corrida que lanza ESTE job todavía está en marcha cuando se mira la lista: su resultado
#    llega por `PROPIO_RESULTADO` y se cuenta como si ya hubiera acabado. Sin eso, un fichero que
#    se SALTA en verde (no deja filas) se volvería a lanzar: ése sí sería un bucle.
# 🔒 Solo LEE la base (sesión read-only). Las llaves son las que el workflow ya tenía; para
#    lanzar la corrida usa el GITHUB_TOKEN del propio run, con `actions: write` SOLO en este job.
# 🔒 Un fallo aquí NO pone en rojo la carga: el job lleva `continue-on-error`. La red de debajo
#    de esta red es el aviso de la tarjeta de Keepa en Buzones (v2).
# ============================================================================

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from procesador_keepa_escaparate import (BUCKET, CARPETA, DOMINIO_NUM, instante, leer_nombre)
from foto_comun import Aborta

DOMINIOS = sorted(set(DOMINIO_NUM.values()))   # los cuatro países de Keepa: de, es, fr, it

WORKFLOW = 'procesar-keepa-escaparate.yml'
VENTANA_HORAS = 48          # «los CSV de Keepa de los últimos 2 días» (el encargo)
MAX_FALLOS = 2              # el intento original + UN reintento del encadenado
ESTADOS_ACTIVOS = {'queued', 'in_progress', 'requested', 'waiting', 'pending'}
# Lo que cuenta como intento fallido. `cancelled` también (un corte por tope sale así):
# contar de más solo hace que se reintente MENOS, nunca más.
CONCLUSIONES_FALLIDAS = {'failure', 'cancelled', 'timed_out', 'startup_failure'}
SIN_FICHERO = '(el más reciente)'


def titulo_corrida(fichero, modo='aplicar'):
    """🔒 EL MISMO TEXTO QUE `run-name:` EN procesar-keepa-escaparate.yml. Lo comprueba
    test_encadenar_keepa.py leyendo el YAML, y lo copia la v2 en lib/buzones/catalogo.ts
    (`porFichero.tituloCorrida`): si cambia aquí, cambia en los tres sitios."""
    return f"Keepa · {modo} · {fichero or SIN_FICHERO}"


def es_csv_de_keepa(nombre):
    if not nombre.lower().endswith('.csv'):
        return False
    try:
        leer_nombre(nombre)
        return True
    except Aborta:
        return False


def decidir(objetos, cargas, corridas, propio, ahora, fotos_vivas):
    """LA DECISIÓN, PURA (sin red ni base) para poder EJECUTARLA en un test.

    objetos  = [{'name', 'updated_at'}] del buzón.
    cargas   = {nombre: último procesado_at de sus filas (viva ∪ histórico)} — None si ninguna.
    corridas = [{'id', 'status', 'conclusion', 'display_title', 'created_at'}] de GitHub.
    propio   = {'run_id', 'fichero', 'resultado'}: la corrida que está acabando (success|failure).
    ahora    = datetime con zona.
    fotos_vivas = {dominio: fecha_foto más reciente en keepa_escaparate}.

    🔑 EL FILTRO DE «MÁS VIEJO QUE TODO». Del nombre de un CSV del Visualizador no sale el país,
       así que aquí no se sabe si un fichero de ayer pisaría una foto de hoy. Pero si LOS CUATRO
       países ya tienen una foto de un día posterior, da igual cuál sea: no hay nada que cargar.
       Se descarta sin lanzarlo. (Medido el 01-oct-2026: los cuatro del 29-sep resubidos a las
       14:11 con el mismo nombre se cargaron, pero sus filas no llegaron al histórico — repetían
       foto del día — y ya no están en la viva; sin este filtro, el primer encadenado los
       lanzaría los cuatro para que el procesador los saltara.)

    Devuelve {'siguiente': nombre|None, 'motivo': texto, 'filas': [(nombre, subido, estado)]}.
    """
    filas = []
    limite = ahora - timedelta(hours=VENTANA_HORAS)
    # La corrida propia, como si ya hubiera acabado con su resultado (ver la cabecera).
    vistas = [c for c in corridas if str(c.get('id')) != str(propio.get('run_id'))]
    otra_activa = [c for c in vistas if c.get('status') in ESTADOS_ACTIVOS]
    acabadas = [(c.get('display_title'), instante(c.get('created_at')), c.get('conclusion'))
                for c in vistas if c.get('status') == 'completed']
    # Con la hora a la que se CREÓ la propia (no «ahora»): si su fichero se resubió mientras
    # corría, esa versión nueva no la ha tratado nadie.
    creada = next((instante(c.get('created_at')) for c in corridas
                   if str(c.get('id')) == str(propio.get('run_id'))), None) or ahora
    acabadas.append((titulo_corrida(propio.get('fichero')), creada, propio.get('resultado')))

    pendientes = []
    for o in sorted(objetos, key=lambda o: (instante(o.get('updated_at')) or limite, o['name'])):
        nombre, subido = o['name'], instante(o.get('updated_at'))
        if subido is None or subido < limite or not es_csv_de_keepa(nombre):
            continue
        fecha = leer_nombre(nombre)['fecha_foto']
        if all(fotos_vivas.get(d) is not None and fotos_vivas[d] > fecha for d in DOMINIOS):
            filas.append((nombre, subido, 'más viejo que la foto viva de los cuatro países'))
            continue
        carga = instante(cargas.get(nombre))
        if carga is not None and carga >= subido:
            filas.append((nombre, subido, f'cargado ({carga:%d-%m %H:%M} UTC)'))
            continue
        # Solo cuentan las corridas de DESPUÉS de esta subida: un mismo nombre resubido es
        # otro fichero (el caso del 27-sep), y sus intentos empiezan de cero.
        suyas = [(t, cr, k) for t, cr, k in acabadas
                 if t == titulo_corrida(nombre) and cr is not None and cr >= subido]
        if any(k == 'success' for _, _, k in suyas):
            filas.append((nombre, subido, 'tratado por una corrida verde (cargado o saltado)'))
            continue
        fallos = sum(1 for _, _, k in suyas if k in CONCLUSIONES_FALLIDAS)
        if fallos >= MAX_FALLOS:
            filas.append((nombre, subido, f'falló {fallos} veces: no se reintenta solo'))
            continue
        pendientes.append(nombre)
        filas.append((nombre, subido, 'pendiente' + (f' ({fallos} fallo)' if fallos else '')))

    if not pendientes:
        return {'siguiente': None, 'motivo': 'no queda nada por cargar', 'filas': filas}
    if otra_activa:
        ids = ', '.join(str(c.get('id')) for c in otra_activa)
        return {'siguiente': None, 'filas': filas,
                'motivo': f'hay otra corrida en marcha ({ids}); al acabar, ella encadena'}
    return {'siguiente': pendientes[0], 'motivo': 'el más antiguo de los pendientes',
            'filas': filas}


# ---------------------------------------------------------------------------
# Entrada/salida: Storage, base (solo lectura) y GitHub.
# ---------------------------------------------------------------------------
def _gh(metodo, ruta, token, cuerpo=None):
    req = urllib.request.Request(
        f"https://api.github.com{ruta}", method=metodo,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'moloka-encadenar-keepa'})
    with urllib.request.urlopen(req, timeout=30) as r:
        datos = r.read()
        return r.status, (json.loads(datos) if datos else None)


def _corridas(repo, token, desde):
    q = urllib.parse.urlencode({'per_page': 100, 'created': f'>={desde:%Y-%m-%dT%H:%M:%SZ}'})
    _, datos = _gh('GET', f'/repos/{repo}/actions/workflows/{WORKFLOW}/runs?{q}', token)
    return [{k: r.get(k) for k in ('id', 'status', 'conclusion', 'display_title', 'created_at')}
            for r in (datos or {}).get('workflow_runs', [])]


def _resumen(texto):
    print(texto, flush=True)
    ruta = os.environ.get('GITHUB_STEP_SUMMARY')
    if ruta:
        with open(ruta, 'a', encoding='utf-8') as fh:
            fh.write(texto + '\n')


def main():
    from supabase import create_client
    from foto_comun import conectar_bd, listar_buzon

    env = os.environ
    falta = [k for k in ('SUPABASE_KEY', 'DB_URL', 'GH_TOKEN', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID')
             if not env.get(k)]
    if falta:
        sys.exit(f"Faltan {falta} en el entorno del job: sin eso no se puede encadenar.")
    repo, token = env['GITHUB_REPOSITORY'], env['GH_TOKEN']
    propio = {'run_id': env['GITHUB_RUN_ID'], 'fichero': env.get('PROPIO_FICHERO', '').strip(),
              'resultado': env.get('PROPIO_RESULTADO', '').strip()}
    ahora = datetime.now(timezone.utc)

    sb = create_client(env.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co'),
                       env['SUPABASE_KEY'])
    objetos = [{'name': o['name'], 'updated_at': o.get('updated_at') or o.get('created_at')}
               for o in listar_buzon(sb, BUCKET, CARPETA) if o.get('name')]

    # Solo se pregunta a la base por los candidatos (ventana + nombre de Keepa).
    limite = ahora - timedelta(hours=VENTANA_HORAS)
    candidatos = [o['name'] for o in objetos
                  if (instante(o['updated_at']) or limite) >= limite and es_csv_de_keepa(o['name'])]
    cargas, fotos_vivas = {}, {}
    if candidatos:
        con = conectar_bd(env['DB_URL'])
        con.set_session(readonly=True, autocommit=True)
        with con.cursor() as cur:
            cur.execute("SELECT dominio, max(fecha_foto) FROM keepa_escaparate GROUP BY dominio;")
            fotos_vivas = dict(cur.fetchall())
            for nombre in candidatos:
                fecha = leer_nombre(nombre)['fecha_foto']
                cur.execute(
                    "SELECT max(procesado_at) FROM ("
                    " SELECT procesado_at FROM keepa_escaparate WHERE fichero = %s AND fecha_foto = %s"
                    " UNION ALL"
                    " SELECT procesado_at FROM keepa_escaparate_hist WHERE fichero = %s AND fecha_foto = %s"
                    ") t;", (nombre, fecha, nombre, fecha))
                cargas[nombre] = cur.fetchone()[0]
        con.close()

    corridas = _corridas(repo, token, ahora - timedelta(hours=VENTANA_HORAS + 24))
    d = decidir(objetos, cargas, corridas, propio, ahora, fotos_vivas)

    _resumen(f"### 🔗 Encadenado de Keepa\n\nCorrida que acaba: `{titulo_corrida(propio['fichero'])}` "
             f"→ **{propio['resultado']}**\n")
    if d['filas']:
        _resumen('| fichero | subido (UTC) | estado |\n|---|---|---|')
        for nombre, subido, estado in d['filas']:
            _resumen(f"| `{nombre}` | {subido:%d-%m %H:%M} | {estado} |")
    else:
        _resumen(f"No hay CSV de Keepa en el buzón de las últimas {VENTANA_HORAS} h.")
    for nombre, _, estado in d['filas']:
        if estado.startswith('falló'):
            print(f"::warning title=Keepa · {nombre} no se reintenta::{estado}. Míralo a mano.",
                  flush=True)

    if not d['siguiente']:
        _resumen(f"\n**No se lanza nada:** {d['motivo']}.")
        return

    sig = d['siguiente']
    ref = env.get('GITHUB_REF_NAME') or 'main'
    lanzado = datetime.now(timezone.utc)
    estado, _ = _gh('POST', f'/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches', token, {
        'ref': ref,
        'inputs': {'entorno': 'produccion', 'modo': 'aplicar', 'fichero': sig, 'encadenado': 'true'},
    })
    if estado != 204:
        sys.exit(f"GitHub no aceptó el disparo de {sig!r} (HTTP {estado}).")
    _resumen(f"\n**Lanzado:** `{sig}` ({d['motivo']}).")

    # Esperar a VER la corrida nueva (cabecera, punto 6). Un minuto de sobra: suele tardar 2-5 s.
    titulo = titulo_corrida(sig)
    for _ in range(20):
        time.sleep(3)
        vistas = _corridas(repo, token, lanzado - timedelta(seconds=10))
        nueva = next((c for c in vistas if c['display_title'] == titulo
                      and str(c['id']) != str(propio['run_id'])), None)
        if nueva:
            _resumen(f"Corrida nueva: {nueva['id']} ({nueva['status']}).")
            return
    print(f"::warning title=Encadenado::Lanzado {sig!r}, pero GitHub no enseña su corrida tras 60 s.",
          flush=True)


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub respondió HTTP {e.code}: {e.read()[:300]!r}")
