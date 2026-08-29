# -*- coding: utf-8 -*-
# ============================================================================
# COMPRIMIR LOS CSV ANTIGUOS DE informes/keepa_escaparate/
# ----------------------------------------------------------------------------
# QUE HACE
#   Sustituye cada `<nombre>.csv` ANTIGUO del buzon de Keepa por su
#   `<nombre>.csv.gz`, y arregla el nombre en `keepa_escaparate_hist.fichero`
#   para que el historico siga apuntando a algo que existe.
#
# 🔴 POR QUE HACE FALTA, Y POR QUE NO ES UNA LIMPIEZA UNICA
#   El bucket va al 85,3% de 1 GiB (medido 29-ago-2026: 915.853.209 B / 3.102
#   objetos). Estos CSV comprimen 5,45x medido sobre los 71 ficheros reales, uno
#   a uno -- no sobre una muestra. Pero el CSV de hoy es el viejo de manana: si
#   esto se corre a mano una vez, en septiembre estamos igual. Por eso el
#   procedimiento vive aqui y lo dispara un workflow, no una sesion.
#
# 🔴 ESTE BUZON NO ES UN BUZON: ES EL ARCHIVO
#   Desde el PR #74 (migraciones/2026-07-29_keepa_hist_drop_crudo.sql:20-22), al
#   quitar la columna `crudo` de `keepa_escaparate_hist`, ese historico depende
#   de estos CSV. Medido el 29-ago-2026: 16.066 filas citan 67 ficheros POR SU
#   NOMBRE, y los 67 existen. Renombrar sin arreglar el historico deja 16.066
#   filas apuntando al vacio -- y NO GRITARIA NADIE, porque ningun codigo recorre
#   esa ruta: el rescate es manual, y se descubriria el dia que hiciera falta.
#   Por eso el paso 4 de abajo no es opcional y por eso existe `MODO=guarda`.
#
# 🔒 EL ORDEN ES LA SEGURIDAD, Y NO SE REORDENA
#   Por cada fichero, y verificando ANTES de pasar al siguiente:
#     1. bajar el original -> sha256 + tamano
#     2. gzip -9 -> subir el .csv.gz
#     3. bajar el .gz, descomprimirlo y comprobar que sha256 Y tamano coinciden
#        con los del paso 1. Si no coinciden: SE PARA TODO. No se reintenta.
#     4. UPDATE de keepa_escaparate_hist.fichero, y las filas afectadas tienen
#        que ser EXACTAMENTE las contadas antes. Si no: rollback y se para.
#     5. y SOLO ENTONCES borrar el original.
#   Entre el 2 y el 5 conviven los dos ficheros: en ningun instante el historico
#   apunta a algo que no este. El coste de esa ventana es espacio, y el espacio
#   se recupera; un borrado, no.
#
# 🔒 QUE NO SE TOCA, Y POR QUE
#   · Los ficheros con menos de DIAS dias (por defecto 2). El procesador coge
#     "el mas reciente" (procesador_keepa_escaparate.py:875) y filtra por
#     `.endswith('.csv')` (:870): un `.csv.gz` desaparece de su listado. La
#     ventana existe para que esta pasada NUNCA alcance al fichero que el
#     procesador podria estar leyendo.
#   · 🔴 Y ADEMAS, CUALQUIER FICHERO CITADO EN LA TABLA VIVA `keepa_escaparate`.
#     Esto NO es redundante con la ventana de dias, y es la guarda que faltaba:
#     `archivar_foto()` (foto_comun.py:459) apila la foto viva ENTERA al empezar
#     la siguiente pasada, asi que el nombre que hoy esta en la tabla viva se
#     COPIARA al historico manana. Si lo comprimimos hoy, el archivado de manana
#     escribiria en el historico un nombre que ya no existe -- y esta vez sin que
#     ningun UPDATE nuestro pueda arreglarlo, porque lo escribe el procesador.
#     Medido 29-ago-2026: la tabla viva cita 4 ficheros, los 4 del 2026-08-29.
#
# 🔒 NO LLEVA CREDENCIALES DENTRO: SUPABASE_URL / SUPABASE_KEY / DB_URL vienen
#    del entorno, como todos los procesadores de este repo.
#
# MODOS
#   MODO=ensayo   (por defecto) lista lo que haria y no escribe NADA.
#   MODO=aplicar  ejecuta la pasada.
#   MODO=guarda   solo el chequeo de integridad. Codigo 1 si hay huerfanas.
# ============================================================================

import gzip
import hashlib
import io
import os
import sys
from datetime import datetime, timedelta, timezone

BUCKET, CARPETA = 'informes', 'keepa_escaparate'

MODO   = os.environ.get('MODO', 'ensayo').strip().lower()
DIAS   = int(os.environ.get('DIAS', '2'))
LIMITE = int(os.environ.get('LIMITE', '0'))          # 0 = sin limite (tandas)

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
DB_URL       = os.environ.get('DB_URL', '') or os.environ.get('SUPABASE_DB_URL', '')


class Aborta(Exception):
    """Se para y no se ha escrito nada (o se ha revertido)."""


# ---------------------------------------------------------------------------
# 1) LA LOGICA PURA — sin red y sin base, para que tenga banco de pruebas
#    (test_comprimir_keepa.py). Todo lo que decide QUE se toca vive aqui.
# ---------------------------------------------------------------------------

def nombre_gz(nombre):
    """`X.csv` -> `X.csv.gz`. Se conserva el nombre entero: el historico y el
    rescate manual se apoyan en el, y un renombrado "bonito" perderia la fecha
    y el dominio que el nombre lleva dentro (leer_nombre() del procesador)."""
    return nombre + '.gz'


def es_comprimible(nombre):
    """Solo .csv de verdad. Un .gz NO se recomprime (seria una pasada infinita
    que ademas engorda), y cualquier otra extension no es asunto de este script:
    si aparece algo raro, se DICE, no se toca."""
    n = (nombre or '').lower()
    return n.endswith('.csv') and not n.endswith('.gz')


def seleccionar_antiguos(objetos, citados_en_viva, ahora, dias=2, limite=0):
    """Decide QUE ficheros entran en la pasada. Devuelve (elegidos, descartes).

    `objetos`        : [{'name','updated_at'|'created_at'}, ...] tal cual los da
                       storage `.list()`.
    `citados_en_viva`: set de nombres citados HOY en la tabla viva
                       `keepa_escaparate`. Se excluyen SIEMPRE, tengan la edad
                       que tengan (ver la cabecera: archivar_foto los copiara al
                       historico en la proxima pasada del procesador).
    `ahora`          : datetime con tz. Se pasa, no se lee del reloj, para que
                       el test pueda fijarlo.

    `descartes` lleva el motivo de cada exclusion: una pasada que dice "he
    tocado 40" sin decir por que dejo 31 no se puede auditar.
    """
    corte = ahora - timedelta(days=dias)
    elegidos, descartes = [], []
    for o in sorted(objetos, key=lambda x: (x.get('name') or '')):
        nombre = o.get('name') or ''
        if not nombre:
            continue
        if not es_comprimible(nombre):
            descartes.append((nombre, 'no es un .csv (o ya esta comprimido)'))
            continue
        if False:  # ROTO A PROPOSITO — se revierte en el commit siguiente
            descartes.append((nombre, 'CITADO EN LA TABLA VIVA keepa_escaparate'))
            continue
        cuando = _fecha_de(o)
        if cuando is None:
            # Sin fecha no se puede decidir la edad. NO se asume "es viejo":
            # se descarta y se dice. Un default optimista aqui borra un fichero
            # de hoy.
            descartes.append((nombre, 'sin fecha en el listado: no se puede medir la edad'))
            continue
        if cuando > corte:
            descartes.append((nombre, f'reciente ({cuando.date()}, corte {corte.date()})'))
            continue
        elegidos.append(nombre)
    if limite and len(elegidos) > limite:
        descartes.extend((n, f'fuera de esta tanda (LIMITE={limite})') for n in elegidos[limite:])
        elegidos = elegidos[:limite]
    return elegidos, descartes


def _fecha_de(o):
    """La fecha del objeto segun el listado de Storage. Prefiere updated_at."""
    for clave in ('updated_at', 'created_at'):
        v = o.get(clave)
        if not v:
            continue
        try:
            return datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        except ValueError:
            continue
    return None


def verificar_ida_y_vuelta(sha_antes, bytes_antes, crudo_recuperado):
    """El paso 3. Devuelve (ok, detalle). Compara las DOS cosas -- sha y tamano --
    a proposito: un sha igual con tamano distinto es imposible, pero si algun dia
    lo vemos, quiero que el mensaje lo diga en vez de que el script decida cual
    de los dos se cree."""
    sha_despues = hashlib.sha256(crudo_recuperado).hexdigest()
    bytes_despues = len(crudo_recuperado)
    ok = (sha_despues == sha_antes) and (bytes_despues == bytes_antes)
    return ok, {'sha_antes': sha_antes, 'sha_despues': sha_despues,
                'bytes_antes': bytes_antes, 'bytes_despues': bytes_despues}


def veredicto_guarda(huerfanas_hist, huerfanas_viva):
    """La guarda C. ROJO si alguna tabla cita un fichero que no esta en el bucket.

    🔒 Mira las DOS tablas, no solo el historico. Un nombre colgado en la tabla
    VIVA es una fila colgada del historico esperando turno: `archivar_foto()` lo
    copiara tal cual en la proxima pasada del procesador. Cazarlo en la viva es
    cazarlo un dia antes, y con arreglo posible."""
    total = int(huerfanas_hist) + int(huerfanas_viva)
    return (total == 0), total


SQL_GUARDA = """
select
  (select count(*) from public.keepa_escaparate_hist h
    where not exists (select 1 from storage.objects o
                       where o.bucket_id = 'informes'
                         and o.name = 'keepa_escaparate/' || h.fichero)) as huerfanas_hist,
  (select count(*) from public.keepa_escaparate k
    where not exists (select 1 from storage.objects o
                       where o.bucket_id = 'informes'
                         and o.name = 'keepa_escaparate/' || k.fichero)) as huerfanas_viva;
"""


# ---------------------------------------------------------------------------
# 2) LA PARTE QUE TOCA EL MUNDO
# ---------------------------------------------------------------------------

def _sb():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Aborta("Faltan SUPABASE_URL / SUPABASE_KEY. Revisa los secrets del workflow.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def correr_guarda(cur):
    cur.execute(SQL_GUARDA)
    hist, viva = cur.fetchone()
    ok, total = veredicto_guarda(hist, viva)
    print(f"\n--- GUARDA · nombres citados que NO estan en el bucket ---", flush=True)
    print(f"    keepa_escaparate_hist : {hist}", flush=True)
    print(f"    keepa_escaparate (viva): {viva}", flush=True)
    if ok:
        print("    ✅ VERDE: 0 huerfanas.", flush=True)
    else:
        print(f"    🔴 ROJO: {total} fila(s) citan un fichero que no existe en "
              f"informes/keepa_escaparate/.", flush=True)
    return ok, hist, viva


def main():
    if MODO not in ('ensayo', 'aplicar', 'guarda'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo', 'aplicar' o 'guarda')")

    from foto_comun import conectar_bd, listar_buzon, descargar_buzon

    if not DB_URL:
        sys.exit("Falta DB_URL (o SUPABASE_DB_URL). Revisa los secrets del workflow.")
    con = conectar_bd(DB_URL)
    cur = con.cursor()

    # --- La guarda, SIEMPRE, y antes de nada -------------------------------
    # Si ya venimos rotos, esta pasada no arregla nada y ademas enmascararia el
    # roto anterior. Se para.
    ok, hist0, viva0 = correr_guarda(cur)
    if MODO == 'guarda':
        cur.close(); con.close()
        sys.exit(0 if ok else 1)
    if not ok:
        cur.close(); con.close()
        sys.exit("\n❌ ABORTA (no se ha tocado nada): la guarda ya estaba ROJA antes de "
                 "empezar. Hay que arreglar eso primero.")

    sb = _sb()

    # --- Que hay, y que se cita en la tabla viva ---------------------------
    objetos = listar_buzon(sb, BUCKET, CARPETA)
    cur.execute("select distinct fichero from public.keepa_escaparate where fichero is not null;")
    citados_viva = {r[0] for r in cur.fetchall()}

    ahora = datetime.now(timezone.utc)
    elegidos, descartes = seleccionar_antiguos(objetos, citados_viva, ahora, DIAS, LIMITE)

    print(f"\n--- ALCANCE (MODO={MODO}, DIAS={DIAS}, LIMITE={LIMITE or 'sin limite'}) ---", flush=True)
    print(f"    en el buzon: {len(objetos)} · se tocan: {len(elegidos)} · se dejan: {len(descartes)}", flush=True)
    print(f"    citados en la tabla viva (excluidos siempre): {sorted(citados_viva)}", flush=True)
    for n, motivo in descartes:
        print(f"      · SE DEJA  {n}  ({motivo})", flush=True)

    # 🔴 Lo que no es del Visualizador NO se borra ni se esconde: se dice.
    raros = [n for n in elegidos if 'Visualizador' not in n]
    if raros:
        print(f"\n⚠️  {len(raros)} fichero(s) del alcance NO son del Visualizador. Se "
              f"comprimen como los demas (NO se borran), pero quede dicho:", flush=True)
        for n in raros:
            print(f"      · {n}", flush=True)

    if MODO == 'ensayo':
        print("\nENSAYO: no se ha escrito nada.", flush=True)
        cur.close(); con.close()
        return

    # --- La pasada ---------------------------------------------------------
    hechos = []
    for i, nombre in enumerate(elegidos, 1):
        ruta, ruta_gz = f'{CARPETA}/{nombre}', f'{CARPETA}/{nombre_gz(nombre)}'
        print(f"\n[{i}/{len(elegidos)}] {nombre}", flush=True)

        # 1) original + sha
        crudo = descargar_buzon(sb, BUCKET, ruta)
        sha_antes, bytes_antes = hashlib.sha256(crudo).hexdigest(), len(crudo)
        print(f"    1) original: {bytes_antes} B · sha256 {sha_antes}", flush=True)

        # 2) gzip -9 y subida. mtime=0 para que el .gz sea reproducible: dos
        #    pasadas del mismo CSV dan el mismo .gz, y eso hace comparable la copia.
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as g:
            g.write(crudo)
        comprimido = buf.getvalue()
        sb.storage.from_(BUCKET).upload(
            ruta_gz, comprimido,
            {'content-type': 'application/gzip', 'x-upsert': 'true'})
        print(f"    2) subido {nombre_gz(nombre)}: {len(comprimido)} B "
              f"({bytes_antes / max(len(comprimido), 1):.2f}x)", flush=True)

        # 3) ida y vuelta REAL: se vuelve a bajar de Storage, no se compara
        #    contra lo que tenemos en memoria (eso solo probaria que gzip
        #    funciona, no que la subida llego entera).
        recuperado = gzip.decompress(descargar_buzon(sb, BUCKET, ruta_gz))
        bien, det = verificar_ida_y_vuelta(sha_antes, bytes_antes, recuperado)
        if not bien:
            _quitar(sb, ruta_gz, 'la verificacion fallo; se retira el .gz recien subido')
            cur.close(); con.close()
            sys.exit(f"\n❌ SE PARA TODO. {nombre} no vuelve identico:\n    {det}\n"
                     f"    El original NO se ha tocado. No se reintenta: si un fichero "
                     f"no cuadra, lo que falla es el procedimiento, no ese fichero.")
        print(f"    3) ida y vuelta OK · sha256 {det['sha_despues']}", flush=True)

        # 4) el historico, contando antes y despues
        cur.execute("select count(*) from public.keepa_escaparate_hist where fichero = %s;",
                    (nombre,))
        esperadas = cur.fetchone()[0]
        cur.execute("update public.keepa_escaparate_hist set fichero = %s where fichero = %s;",
                    (nombre_gz(nombre), nombre))
        tocadas = cur.rowcount
        if tocadas != esperadas:
            con.rollback()
            _quitar(sb, ruta_gz, 'el UPDATE no cuadro; se retira el .gz recien subido')
            cur.close(); con.close()
            sys.exit(f"\n❌ SE PARA TODO. El UPDATE de {nombre} toco {tocadas} filas y se "
                     f"esperaban {esperadas}. Revertido. El original NO se ha tocado.")
        con.commit()
        print(f"    4) historico: {tocadas} fila(s) -> {nombre_gz(nombre)}", flush=True)

        # 5) y SOLO ENTONCES, el original
        sb.storage.from_(BUCKET).remove([ruta])
        print(f"    5) borrado el original", flush=True)
        hechos.append({'fichero': nombre, 'sha256': sha_antes, 'bytes': bytes_antes,
                       'bytes_gz': len(comprimido), 'filas_hist': tocadas})

    # --- La guarda otra vez, que es lo unico que prueba que quedo bien ------
    ok, hist1, viva1 = correr_guarda(cur)
    print(f"\n--- RESUMEN ---", flush=True)
    print(f"    ficheros comprimidos: {len(hechos)}", flush=True)
    print(f"    bytes antes: {sum(h['bytes'] for h in hechos)} · despues: "
          f"{sum(h['bytes_gz'] for h in hechos)}", flush=True)
    print(f"    filas de historico reapuntadas: {sum(h['filas_hist'] for h in hechos)}", flush=True)
    for h in hechos:
        print(f"      {h['fichero']} · {h['bytes']} B · sha256 {h['sha256']} · "
              f"{h['filas_hist']} fila(s)", flush=True)
    cur.close(); con.close()
    if not ok:
        sys.exit("\n❌ La guarda quedo ROJA despues de la pasada.")


def _quitar(sb, ruta, motivo):
    """Retirar un .gz que acabamos de subir y cuyo original SIGUE estando. Es el
    unico borrado que este script hace fuera del paso 5, y es seguro justo por
    eso: se quita lo que sobra, nunca lo que es la unica copia."""
    print(f"    ↩️  {motivo}: {ruta}", flush=True)
    try:
        sb.storage.from_(BUCKET).remove([ruta])
    except Exception as e:                                   # noqa: BLE001
        print(f"    ⚠️  no pude retirarlo ({e}). Queda un .gz de mas; el original "
              f"sigue en su sitio. NO es perdida de datos.", flush=True)


if __name__ == '__main__':
    try:
        main()
    except Aborta as e:
        sys.exit(f"\n❌ ABORTA: {e}")
