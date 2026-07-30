# -*- coding: utf-8 -*-
# ============================================================================
# BACKUP DEL STORAGE — las FACTURAS y los INFORMES, no solo los apuntes
# ----------------------------------------------------------------------------
# Qué hace:
#   Baja a un directorio local TODOS los objetos de los buckets de Supabase
#   Storage que se le pidan (por defecto `facturas-pdfs` e `informes`), para que
#   el workflow los suba después a R2 con `aws s3 sync`.
#
# 🔴 POR QUÉ EXISTE
#   `backup-bd.yml` hacía `pg_dump --schema=public`: copiaba los APUNTES, no las
#   FACTURAS. Fuera de la copia quedaban los PDF de proveedor y el buzón entero.
#   Y desde el 29-jul-2026 eso es crítico: el DROP de la columna `crudo` de
#   `keepa_escaparate_hist` (PR #74) dejó a ese histórico dependiendo de unos CSV
#   que viven SOLO en el bucket `informes`. Si el bucket desaparece, no hay de
#   dónde reconstruirlos. El bucket dejó de ser temporal: es el archivo permanente.
#
# 🔴 EL LISTADO DE SUPABASE ES POR CARPETA Y PAGINA — LAS DOS COSAS
#   `.list()` devuelve SOLO el nivel que le pides y, por defecto, las primeras 100
#   entradas. Quedarse ahí da una copia incompleta que no avisa de que lo es.
#   · RECURSIÓN: hace falta HOY. Medido el 30-jul: `informes` tiene 16 carpetas y
#     objetos a profundidad 3; `facturas-pdfs` lo tiene TODO bajo `2026/`, también
#     a profundidad 3. Sin recursión, `facturas-pdfs` se copiaría VACÍO.
#   · PAGINACIÓN: hará falta MAÑANA. Hoy la carpeta más poblada es
#     `informes/resultados/` con 33 objetos, pero `informes/keepa_escaparate/` es
#     el archivo histórico permanente y crece sin techo; el día que pase de 100 se
#     empezaría a perder en silencio.
#   🔒 Por eso este script NO usa `listar_buzon()` de foto_comun: ése llama a
#      `.list(carpeta)` a secas, sin recursión ni paginación. Le vale al buzón de
#      un procesador (una carpeta, pocos ficheros); NO vale para una copia.
#
# 🔒 UNA COPIA INCOMPLETA QUE DICE "OK" ES PEOR QUE NO TENER COPIA
#   Por eso el script CUENTA lo que lista y lo compara con lo que baja, comprueba
#   que cada fichero pesa lo que el listado dice que pesa, y si algo no cuadra
#   sale con código 1 para que el workflow entero falle y salte el Telegram.
#   Un bucket que lista CERO objetos también aborta: los dos tienen contenido, así
#   que un cero es un fallo de credenciales o de permisos disfrazado de éxito.
#
# 🔒 No lleva credenciales dentro: SUPABASE_URL y SUPABASE_KEY vienen del entorno
#    (los mismos secrets que ya usan los procesadores).
# ============================================================================

import os
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: los buckets son PRIVADOS
DESTINO      = os.environ.get('DESTINO', 'storage_backup')
BUCKETS      = [b.strip() for b in os.environ.get(
                    'BUCKETS', 'facturas-pdfs,informes').split(',') if b.strip()]

# 🔒 `fotos-fabrica` NO entra aquí a propósito: 2.531 objetos / 598 MB medidos el
#    30-jul. Copiarlo a diario no compensa y se decide aparte. Si algún día entra,
#    basta con añadirlo al input BUCKETS del workflow: el script no lo tiene cableado.

PAGINA = 100          # tamaño de página del listado de Supabase Storage
REINTENTOS = 3        # cortes de red del runner; el mismo criterio que foto_comun
ESPERA = 3            # segundos entre reintentos


def _con_reintentos(que, hacer):
    """Reintenta ante errores transitorios de red. Se escribe aquí y no se importa
    de foto_comun porque ese módulo arrastra psycopg2, y este job no toca Postgres:
    no se mete un cliente de base de datos en el runner del backup para nada."""
    ultimo = None
    for intento in range(1, REINTENTOS + 1):
        try:
            return hacer()
        except Exception as e:          # noqa: BLE001 — se reintenta y se relanza
            ultimo = e
            print(f"   ! {que}: intento {intento}/{REINTENTOS} falló ({type(e).__name__}: {e})",
                  flush=True)
            if intento < REINTENTOS:
                time.sleep(ESPERA * intento)
    raise ultimo


def _es_carpeta(entrada):
    """En Supabase Storage una CARPETA es un prefijo sintético: viene sin `id` y sin
    `metadata`. Un fichero trae los dos. Se comprueban ambos por si el SDK cambia uno."""
    return entrada.get('id') is None or not entrada.get('metadata')


def listar_recursivo(sb, bucket, prefijo=''):
    """TODOS los objetos del bucket: entra en las subcarpetas y PAGINA hasta agotar.
    Devuelve [{'ruta', 'bytes', 'sello'}]."""
    encontrados = []
    offset = 0
    while True:
        pagina = _con_reintentos(
            f"listar {bucket}/{prefijo}",
            lambda: sb.storage.from_(bucket).list(
                prefijo,
                {'limit': PAGINA, 'offset': offset,
                 'sortBy': {'column': 'name', 'order': 'asc'}}) or [])

        for e in pagina:
            nombre = (e.get('name') or '').strip()
            # El placeholder que Supabase crea para que una carpeta vacía exista no
            # es un fichero de nadie: no se copia.
            if not nombre or nombre == '.emptyFolderPlaceholder':
                continue
            ruta = f"{prefijo}/{nombre}" if prefijo else nombre
            if _es_carpeta(e):
                encontrados.extend(listar_recursivo(sb, bucket, ruta))
            else:
                meta = e.get('metadata') or {}
                try:
                    tam = int(meta.get('size') or 0)
                except (TypeError, ValueError):
                    tam = 0
                encontrados.append({
                    'ruta': ruta,
                    'bytes': tam,
                    'sello': e.get('updated_at') or e.get('created_at') or '',
                })

        # Última página cuando el servidor devuelve menos de lo que se le pidió.
        if len(pagina) < PAGINA:
            break
        offset += PAGINA

    return encontrados


def _fecha_del_sello(sello):
    """'2026-07-29T06:32:43.576940+00:00' → epoch, o None si no se puede leer."""
    if not sello:
        return None
    try:
        return datetime.fromisoformat(str(sello).replace('Z', '+00:00')).timestamp()
    except (ValueError, AttributeError, TypeError):
        return None


def bajar(sb, bucket, obj, raiz):
    """Baja un objeto a raiz/<bucket>/<ruta>. Devuelve los bytes escritos.
    Lanza si el tamaño no coincide con el que anunció el listado."""
    destino = os.path.join(raiz, bucket, *obj['ruta'].split('/'))
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    datos = _con_reintentos(f"bajar {bucket}/{obj['ruta']}",
                            lambda: sb.storage.from_(bucket).download(obj['ruta']))
    if datos is None:
        raise IOError("la descarga devolvió None")

    # Un fichero a medias es peor que un fichero ausente: al menos el ausente se ve.
    if obj['bytes'] and len(datos) != obj['bytes']:
        raise IOError(f"tamaño distinto del anunciado: bajados {len(datos)} B, "
                      f"el listado decía {obj['bytes']} B")

    with open(destino, 'wb') as f:
        f.write(datos)

    # Se copia la fecha de Supabase al fichero local para que `aws s3 sync` pueda
    # saltarse lo que no ha cambiado. Sin esto, cada copia diaria reescribiría los
    # 46 MB enteros (recién bajado = siempre "más nuevo" que lo que hay en R2).
    epoca = _fecha_del_sello(obj['sello'])
    if epoca:
        try:
            os.utime(destino, (epoca, epoca))
        except OSError:
            pass    # que no se pueda tocar la fecha no invalida la copia

    return len(datos)


def main():
    print("=== BACKUP DEL STORAGE (facturas e informes → disco → R2) ===", flush=True)
    print(f"Buckets: {', '.join(BUCKETS)}", flush=True)
    print(f"Destino local: {DESTINO}", flush=True)
    print("=" * 60, flush=True)

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Faltan credenciales (SUPABASE_URL / SUPABASE_KEY). "
                 "Revisa los secrets del workflow.")

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    total_objetos = 0
    total_bytes = 0
    problemas = []

    for bucket in BUCKETS:
        print(f"\n--- {bucket} ---", flush=True)
        objetos = listar_recursivo(sb, bucket)
        print(f"   listados: {len(objetos)} objeto(s)", flush=True)

        # Un bucket vacío no es "nada que copiar": los dos tienen contenido. Un cero
        # aquí es credencial o permiso mal puestos, y sin esto pasaría por éxito.
        if not objetos:
            problemas.append(f"{bucket}: el listado ha salido VACÍO (0 objetos). "
                             f"Con la llave de servicio no debería. No se copia nada.")
            continue

        bajados = 0
        bytes_bucket = 0
        for obj in objetos:
            try:
                bytes_bucket += bajar(sb, bucket, obj, DESTINO)
                bajados += 1
            except Exception as e:      # noqa: BLE001 — se anota y se sigue
                # No se corta en el primer fallo: se intentan todos para que el
                # informe final diga QUÉ falta, no solo que algo falló.
                problemas.append(f"{bucket}/{obj['ruta']}: {type(e).__name__}: {e}")

        mb = bytes_bucket / 1048576
        print(f"   bajados:  {bajados} de {len(objetos)}  ·  {bytes_bucket} B ({mb:.1f} MB)",
              flush=True)
        if bajados != len(objetos):
            problemas.append(f"{bucket}: se listaron {len(objetos)} objetos y solo se "
                             f"bajaron {bajados}. Faltan {len(objetos) - bajados}.")

        total_objetos += bajados
        total_bytes += bytes_bucket

    print("\n" + "=" * 60, flush=True)
    print(f"TOTAL copiado: {total_objetos} objeto(s) · {total_bytes} B "
          f"({total_bytes / 1048576:.1f} MB)", flush=True)

    # El workflow lee esto para meterlo en el Telegram de OK.
    ruta_env = os.environ.get('GITHUB_ENV')
    if ruta_env:
        with open(ruta_env, 'a', encoding='utf-8') as f:
            f.write(f"STORAGE_OBJETOS={total_objetos}\n")
            f.write(f"STORAGE_BYTES={total_bytes}\n")

    if problemas:
        print("\n❌ LA COPIA NO ESTÁ COMPLETA (no se da por buena):", flush=True)
        for p in problemas:
            print(f"   · {p}", flush=True)
        print("\nUna copia incompleta que dice OK es peor que no tener copia.", flush=True)
        sys.exit(1)

    print("\n✅ Copia COMPLETA: todo lo listado se ha bajado y pesa lo que debía.",
          flush=True)


if __name__ == '__main__':
    main()
