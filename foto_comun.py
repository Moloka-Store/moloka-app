# -*- coding: utf-8 -*-
# ============================================================================
# FOTO_COMUN — el patrón de carga de FOTO que heredan las cuatro cañerías de
# la Fase 0 (all_listings, salud_fba, paneu_aptos, keepa_escaparate).
# ----------------------------------------------------------------------------
# EL PROBLEMA QUE RESUELVE
#   Las cuatro hacían UPSERT y nada más: añadían y actualizaban, pero NUNCA
#   daban de baja lo que desaparecía del fichero de origen. Resultado: filas
#   fantasma conviviendo con las nuevas (medido: salud_fba pasó de 195 a 188
#   SKU en dos días y las 7 viejas se quedaron dentro). Una tabla con filas de
#   dos días distintos no es una foto: es un collage, y miente.
#
# LAS TRES REGLAS DEL PATRÓN
#   1) LA FOTO TIRA LA HOJA VIEJA. Tras cargar el fichero, las claves (la PK)
#      que ya NO aparecen en él se BORRAN. No se marcan, no se archivan: se
#      borran. La memoria histórica vive en movimientos/ledger/productos,
#      JAMÁS en una Foto.
#   2) NUNCA SE BORRA ANTES DE VALIDAR. La guarda anti-encogimiento (fichero
#      con menos del 50% de las filas que ya había → ABORTA) corre ANTES del
#      borrado, y el borrado y la carga van en la MISMA transacción: o todo o
#      nada.
#   3) LA FECHA ES LA DEL DATO, JAMÁS now(). Cuando el fichero no trae fecha
#      interna ni en el nombre, la fecha del dato es CUÁNDO SE SUBIÓ LA FOTO AL
#      BUZÓN. `procesado_en`/`procesado_at` (cuándo corrió el robot) sí es
#      now(): son dos cosas distintas y no se confunden.
#
# EL ÁMBITO DEL BORRADO (decisión de 20-jul, Fernando)
#   Se borra SOLO dentro del ámbito que el fichero declara cubrir:
#     · all_listings y paneu → sin ámbito: el fichero ES la tabla entera.
#     · keepa_escaparate     → ámbito ('dominio', ['es']): cada export es de UN
#                              país. Sin acotar, cargar el de ES borraría IT y FR.
#     · salud_fba            → ámbito ('marketplace', [los del fichero]).
#   Coste asumido y consciente: si un país desaparece ENTERO del informe, sus
#   filas se quedan. Es indistinguible de "hoy no me han dado ese informe", y
#   ese caso lo canta la fecha del dato, que es lo que se mira.
#
# EL HISTÓRICO — la PELÍCULA que la Foto no puede guardar (§1.6)
#   `archivar_foto()` apila la foto viva ACTUAL en su histórico `<tabla>_hist`
#   ANTES de que la carga la sobrescriba, en la MISMA transacción. Es el cajón
#   PELÍCULA (§1.6): apila, NUNCA borra. La garantía es transaccional: ninguna
#   foto se sobrescribe sin haberla archivado primero — si la carga se revierte,
#   el archivado también. Es OPT-IN: una cañería lo usa solo si tiene histórico.
#
# CÓMO SE USA (el orden NO es negociable)
#     previas = guarda_anti_encogimiento(cur, 'tabla', len(filas), ambito)
#     prev    = claves_previas(cur, 'tabla', ['pk1','pk2'], ambito)   # solo contar altas
#     ... crear tabla viva si no existe ...
#     arch = archivar_foto(cur, 'tabla', ['pk1','pk2'], 'fecha_foto')  # ANTES de barrer
#     borradas = barrer_sobrantes(cur, 'tabla', ['pk1','pk2'], claves_nuevas, ambito)
#     ... upsert de las filas ...
#     con.commit() si MODO == 'aplicar', si no con.rollback()
#   En ENSAYO el borrado y el archivado se ejecutan igual (para poder decir
#   cuántas se irían / se archivarían) pero la transacción se revierte: no se
#   escribe ni un byte.
# ============================================================================

import re
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values


class Aborta(Exception):
    """Cualquier guarda que aborta lanza esto: se imprime, NO se escribe nada
    y el workflow sale en rojo."""
    pass


# ---------------------------------------------------------------------------
# LECTURAS de Storage con reintento — SOLO lecturas (listar la carpeta, descargar
# el fichero). Añadido tras el 28-jul: un "[Errno 104] Connection reset by peer"
# tumbó el procesador de PanEU. No fue el fichero: fue la RED. Y con la Fase 2
# disparando varios workflows casi a la vez, esto va a pasar MÁS, no menos.
#
# 🔒 El reintento va AQUÍ y solo aquí: en la conversación con Storage. JAMÁS en la
#    escritura a la BD — esos procesadores escriben en TRANSACCIÓN y un reintento a
#    ciegas podría DUPLICAR. Las escrituras no pasan por estos helpers.
#
# Se distinguen DOS fallos que hoy acaban igual (exit 1):
#    · "no pude hablar con Storage" (red) → se REINTENTA; si persiste, aborta diciéndolo.
#    · "el fichero está mal" (ausente, permiso, ruta) → NO se reintenta: aborta ya.
# ---------------------------------------------------------------------------
import re as _re
import time

# Espera entre intentos: CRECIENTE (1s, 3s, 6s), no tres golpes seguidos. Un hipo de red se
# cura en el primer segundo; un corte no se arregla reintentando a los 100 ms. La suma (10s)
# es el TOPE de espera total: el workflow no se queda colgado. → 4 intentos como mucho.
_ESPERAS_REINTENTO = (1, 3, 6)


def _es_transitorio(exc):
    """True SOLO si el error es TRANSITORIO (reintentarlo puede ayudar): corte de red, timeout,
    o un 5xx de Storage. Un 404 (el fichero no está) o un 403 (permisos) NO es transitorio:
    reintentarlo es perder el tiempo del runner y tapar un problema real → False. Ante la duda,
    False (conservador: no se reintenta lo que no se reconoce como transitorio)."""
    # Excepciones de TRANSPORTE: la conversación con Storage se cortó.
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)):
        return True
    try:
        # supabase-py habla por httpx; TransportError = connect/read/write/pool/network/timeout.
        import httpx
        if isinstance(exc, httpx.TransportError):
            return True
    except ImportError:
        pass
    # HTTP: el código lo trae el error de la API de Storage (status/code/…) o el texto.
    codigo = None
    for attr in ('status', 'status_code', 'code', 'statusCode'):
        v = getattr(exc, attr, None)
        if v is not None:
            try:
                codigo = int(v)
                break
            except (ValueError, TypeError):
                pass
    txt = str(exc).lower()
    if codigo is None:
        m = _re.search(r'\b([45]\d\d)\b', txt)  # rescatar "… 503 …" del texto
        if m:
            codigo = int(m.group(1))
    if codigo is not None:
        return 500 <= codigo <= 599  # 5xx transitorio; 4xx (404/403/400) NO
    # Sin código: solo firmas CLARAS de red en el texto. Lo demás → False.
    return any(s in txt for s in ('connection reset', 'reset by peer', 'errno 104', 'broken pipe',
                                  'timed out', 'read timeout', 'server disconnected',
                                  'remotedisconnected', 'connection aborted', 'incompleteread'))


def _leer_con_reintentos(descripcion, fn, esperas=_ESPERAS_REINTENTO):
    """Ejecuta una LECTURA de Storage con reintentos ante errores TRANSITORIOS (red/5xx), con
    espera creciente y tope total. Un fichero mal (404/403) aborta al primer intento.

    🔒 Cuando un reintento SALE BIEN, lo GRITA en el log. Es la regla de la casa —o grita, o no
       pinta veredicto— aplicada AL ÉXITO, no solo al fallo: un reintento silencioso convierte
       una degradación creciente en invisible (Storage puede empezar a fallar el 30% de las
       veces y nadie enterarse hasta que revienta del todo).
    """
    intentos = len(esperas) + 1
    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            r = fn()
            if intento > 1:
                print(f"⚠️  [Storage] {descripcion}: falló {intento - 1} vez/veces "
                      f"({ultimo}); intento {intento} OK.", flush=True)
            return r
        except Aborta:
            raise  # una guarda de dentro: no es cosa de la red, sube tal cual
        except Exception as e:
            ultimo = e
            if not _es_transitorio(e):
                raise Aborta(
                    f"[Storage] {descripcion}: falló y NO es transitorio → {e}. Reintentar no lo "
                    f"arregla (fichero ausente [404], permiso [403] o ruta mala). Míralo y relanza. "
                    f"No se ha escrito nada.")
            if intento <= len(esperas):
                espera = esperas[intento - 1]
                print(f"⚠️  [Storage] {descripcion}: fallo transitorio ({e}). "
                      f"Reintento {intento}/{len(esperas)} en {espera}s…", flush=True)
                time.sleep(espera)
    raise Aborta(
        f"[Storage] {descripcion}: NO pude hablar con Storage tras {intentos} intentos → {ultimo}. "
        f"Es transitorio (corte/timeout/5xx) pero no cesó en {sum(esperas)}s. No se ha escrito "
        f"nada; relanza cuando la conexión vaya.")


def listar_buzon(sb, bucket, carpeta):
    """Lista una carpeta del buzón con reintento ante errores transitorios. [] si vacía."""
    return _leer_con_reintentos(
        f"listar {bucket}/{carpeta}/",
        lambda: sb.storage.from_(bucket).list(carpeta) or [])


def descargar_buzon(sb, bucket, ruta):
    """Descarga un objeto del buzón (bytes) con reintento ante errores transitorios.
    🔒 Cada reintento EMPIEZA DE CERO: storage3 `.download()` hace un GET nuevo y devuelve el
       contenido entero (`response.content`); NO continúa sobre un buffer anterior (verificado
       en el código del SDK). Un corte a media descarga se rehace limpio, no se concatena."""
    return _leer_con_reintentos(
        f"descargar {bucket}/{ruta}",
        lambda: sb.storage.from_(bucket).download(ruta))


# ---------------------------------------------------------------------------
# CONEXIÓN a Postgres con reintento — el hermano de los helpers de Storage, para
# el OTRO extremo del cable. Añadido tras el 31-jul: un `connection … timed out`
# contra el pooler de Supabase tiró un procesador que ya había leído y validado el
# fichero entero — no fue el dato, fue la RED, y el mismo transitorio se curó solo
# al relanzar 15 min después.
#
# 🔒 El reintento va SOLO en el connect, JAMÁS envolviendo la escritura. connect() es
#    idempotente (aún no ha tocado nada), así que reintentarlo es seguro; una transacción
#    a medias NO se reintenta (duplicaría). Por eso el procesador llama a esto ANTES de
#    escribir el primer byte, y una vez con la conexión en la mano ya no hay más reintentos.
#
# 🔒 connect_timeout es imprescindible para que el reintento SIRVA de algo: sin él, un
#    pooler que no responde tarda el timeout de TCP del SO en rendirse (el 31-jul fueron
#    6m57s = 3 IPs × ~139s para UN intento) y el reintento llegaba tarde o nunca. Con él,
#    cada intento se rinde en `connect_timeout`s por host (libpq lo aplica POR host) y el
#    reintento puede pillar la red ya recuperada.
# ---------------------------------------------------------------------------

# SQLSTATE que, AL CONECTAR, son transitorios (merece reintentar). Toda la clase 08
# (Connection Exception) se trata como transitoria vía el prefijo; estos son los del
# servidor arrancando/saturado/cerrándose, que también lo son.
_SQLSTATE_CONEXION_TRANSITORIA = {'57P03', '53300', '57P01'}


def _es_transitorio_conexion(exc):
    """Como `_es_transitorio` pero para el CONNECT. Un `psycopg2.OperationalError` SIN
    `pgcode` = no llegamos ni a hablar con el servidor (red / pooler / timeout de conexión):
    transitorio. CON `pgcode`, el servidor RESPONDIÓ: solo la clase 08 (conexión) y el
    "servidor arrancando/saturado" son transitorios; un 28xxx (credenciales) o 3D000 (base
    inexistente) NO lo son — reintentar no los arregla. Lo que no sea OperationalError cae en
    `_es_transitorio` (mismo criterio que Storage). Ante la duda, conservador."""
    if isinstance(exc, psycopg2.OperationalError):
        code = getattr(exc, 'pgcode', None)
        if not code:
            return True
        return code.startswith('08') or code in _SQLSTATE_CONEXION_TRANSITORIA
    return _es_transitorio(exc)


def conectar_bd(db_url, esperas=_ESPERAS_REINTENTO, connect_timeout=10):
    """Abre la conexión a Postgres con REINTENTO ante cortes de red TRANSITORIOS, con espera
    creciente y tope (igual que las lecturas de Storage). Devuelve la conexión ya abierta; el
    procesador sigue como siempre (autocommit, cursor). Un fallo que NO es de red (credenciales,
    host mal, base inexistente) aborta al PRIMER intento diciéndolo: reintentar no lo arregla.

    🔒 SOLO el connect se reintenta. La escritura, jamás (ver cabecera de esta sección)."""
    intentos = len(esperas) + 1
    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            con = psycopg2.connect(db_url, connect_timeout=connect_timeout)
            if intento > 1:
                print(f"⚠️  [BD] conexión: falló {intento - 1} vez/veces "
                      f"({ultimo}); intento {intento} OK.", flush=True)
            return con
        except Exception as e:
            ultimo = e
            if not _es_transitorio_conexion(e):
                raise Aborta(
                    f"[BD] No pude conectar y NO es un corte de red → {e}. Reintentar no lo "
                    f"arregla (credenciales, host/puerto mal, base inexistente o la base rechaza "
                    f"la conexión). Míralo y relanza. No se ha escrito nada.")
            if intento <= len(esperas):
                espera = esperas[intento - 1]
                print(f"⚠️  [BD] no pude conectar ({e}). "
                      f"Reintento {intento}/{len(esperas)} en {espera}s…", flush=True)
                time.sleep(espera)
    raise Aborta(
        f"[BD] NO pude conectar a Postgres tras {intentos} intentos → {ultimo}. Es transitorio "
        f"(corte/timeout de red) pero no cesó en {sum(esperas)}s de esperas. No se ha escrito "
        f"nada; relanza cuando la conexión vaya.")


# Los nombres de tabla/columna de este repo son literales del código, nunca
# entrada del usuario. Aun así se validan: un f-string con un identificador es
# la puerta por la que entra una inyección el día que alguien lo parametrice.
_RE_IDENT = re.compile(r'^[a-z_][a-z0-9_]*$')


def _ident(nombre):
    n = (nombre or '').strip()
    if not _RE_IDENT.match(n):
        raise Aborta(f"[foto_comun] Identificador SQL no válido: {nombre!r}.")
    return n


# ---------------------------------------------------------------------------
# La fecha del DATO cuando el fichero no la trae dentro ni en el nombre
# ---------------------------------------------------------------------------
def fecha_del_dato_por_subida(obj, que_informe):
    """Fecha del DATO = cuándo se subió esta foto al buzón (Storage).

    Se usa SOLO en los informes que no traen fecha ninguna: ni columna dentro
    (salud_fba tiene 'snapshot-date') ni en el nombre (keepa lo lleva ahí).
    Hoy: all_listings y paneu_aptos.

    🔴 Si el sello de subida no se puede leer, ABORTA. NO cae a today(): un
    today() de reserva es exactamente el now() que esta regla prohíbe, y
    dejaría una foto vieja fechada hoy — información FALSA, no incompleta.
    """
    sello = obj.get('updated_at') or obj.get('created_at') or ''
    try:
        return datetime.fromisoformat(str(sello).replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        raise Aborta(
            f"[fecha del dato] El objeto de {que_informe} en el buzón no trae un sello "
            f"de subida legible (updated_at/created_at vistos: {sello!r}). Sin fecha del "
            f"dato no se carga: una cifra sin la fecha que la sostiene es una cifra que "
            f"miente. Vuelve a subir el fichero al buzón y relanza.")


# ---------------------------------------------------------------------------
# Ámbito: (columna, [valores]) o None para "la tabla entera"
# ---------------------------------------------------------------------------
def _clausula_ambito(ambito, alias):
    if ambito is None:
        return "TRUE", []
    col, valores = ambito
    col = _ident(col)
    valores = list(valores)
    if not valores:
        raise Aborta(f"[foto_comun] Ámbito sobre {col!r} sin ningún valor. "
                     "Un ámbito vacío borraría todo o nada según el humor del día.")
    return f"{alias}.{col} = ANY(%s)", [valores]


def describir_ambito(ambito):
    if ambito is None:
        return "la tabla entera"
    col, valores = ambito
    return f"{col} ∈ {sorted(set(valores))}"


# ---------------------------------------------------------------------------
# Guarda anti-encogimiento — corre ANTES de borrar y ANTES de escribir
# ---------------------------------------------------------------------------
def guarda_anti_encogimiento(cur, tabla, n_filas_nuevas, ambito=None, etiqueta='anti-encogimiento'):
    """Si el fichero trae MENOS DEL 50% de las filas que ya había en el ámbito
    → ABORTA sin tocar nada. Devuelve cuántas filas había (0 si la tabla aún
    no existe).

    Es la guarda que hace seguro el borrado: sin ella, un fichero truncado a
    medias vaciaría la tabla en silencio.
    """
    tabla = _ident(tabla)
    cur.execute("SELECT to_regclass(%s);", (f'public.{tabla}',))
    if cur.fetchone()[0] is None:
        return 0

    clausula, args = _clausula_ambito(ambito, 't')
    cur.execute(f"SELECT count(*) FROM {tabla} AS t WHERE {clausula};", args)
    previas = cur.fetchone()[0]

    if n_filas_nuevas < previas * 0.5:
        raise Aborta(
            f"[Guarda {etiqueta}] El fichero trae {n_filas_nuevas} filas y en {tabla} "
            f"({describir_ambito(ambito)}) ya hay {previas}: menos del 50%. "
            f"Un informe a medias no da información incompleta, da información FALSA. "
            f"No se borra ni se escribe nada.")
    return previas


# ---------------------------------------------------------------------------
# Guarda no-retroceder — corre DESPUÉS de la anti-encogimiento y ANTES de borrar
# ---------------------------------------------------------------------------
def guarda_no_retroceder(cur, tabla, col_fecha, fecha_nueva, ambito=None):
    """Si la foto que entra es MÁS VIEJA que la máxima ya presente en el ámbito
    → ABORTA sin tocar nada.

    Compara la FECHA DEL DATO (la que escribe el upsert), no la de subida: subir
    hoy un informe de la semana pasada es retroceder en el tiempo, y una foto
    caducada no da información incompleta, da información FALSA.

    Válvula de escape para recargas deliberadas: PERMITIR_RETROCESO=1.
    """
    import os
    if os.environ.get('PERMITIR_RETROCESO') == '1':
        return

    tabla = _ident(tabla)
    cur.execute("SELECT to_regclass(%s);", (f'public.{tabla}',))
    if cur.fetchone()[0] is None:
        return  # tabla aún no creada: no hay pasado contra el que retroceder

    clausula, args = _clausula_ambito(ambito, 't')
    cur.execute(
        f"SELECT MAX(t.{_ident(col_fecha)}) FROM {tabla} AS t WHERE {clausula};", args)

    # Comparación date-vs-date: `listings_amazon.fecha_informe` es timestamptz
    # (MAX devuelve datetime) y el resto son date. Sin normalizar, comparar
    # date con datetime revienta en runtime (TypeError).
    def _a_fecha(v):
        return v.date() if isinstance(v, datetime) else v

    fecha_max = _a_fecha(cur.fetchone()[0])
    fecha_nueva = _a_fecha(fecha_nueva)

    if fecha_max is not None and fecha_nueva is not None and fecha_nueva < fecha_max:
        raise Aborta(
            f"[Guarda no-retroceder] La foto que entra es del {fecha_nueva} y en {tabla} "
            f"({describir_ambito(ambito)}) ya hay dato del {fecha_max}: sería retroceder "
            f"en el tiempo. No se escribe nada. "
            f"(Si de verdad quieres recargar una foto vieja: PERMITIR_RETROCESO=1.)")


# ---------------------------------------------------------------------------
# Claves que ya estaban (solo para contar altas vs actualizaciones en el log)
# ---------------------------------------------------------------------------
def claves_previas(cur, tabla, pk_cols, ambito=None):
    tabla = _ident(tabla)
    pk = [_ident(c) for c in pk_cols]
    cur.execute("SELECT to_regclass(%s);", (f'public.{tabla}',))
    if cur.fetchone()[0] is None:
        return set()
    clausula, args = _clausula_ambito(ambito, 't')
    cur.execute(f"SELECT {', '.join('t.' + c for c in pk)} FROM {tabla} AS t "
                f"WHERE {clausula};", args)
    return {tuple(row) for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# EL BORRADO: lo que ya no está en el fichero, fuera
# ---------------------------------------------------------------------------
def barrer_sobrantes(cur, tabla, pk_cols, claves_nuevas, ambito=None):
    """Borra de `tabla` las filas del ámbito cuya PK NO viene en el fichero.

    `claves_nuevas` son tuplas con los MISMOS valores que el upsert va a
    escribir (no normalizados aparte: si aquí se compara en mayúsculas y allí
    se escribe en minúsculas, el barrido borra filas que sí venían).

    Devuelve el nº de filas borradas. Va DESPUÉS de la guarda anti-encogimiento
    y DENTRO de la misma transacción que el upsert.
    """
    tabla = _ident(tabla)
    pk = [_ident(c) for c in pk_cols]

    claves = {tuple(k) for k in claves_nuevas}
    if not claves:
        raise Aborta(f"[foto_comun] Barrido de {tabla} con 0 claves nuevas: eso vaciaría "
                     "el ámbito entero. Abortando (lo tapa el anti-vacío de cada informe, "
                     "pero aquí no se pasa ni por error).")
    for k in claves:
        if len(k) != len(pk):
            raise Aborta(f"[foto_comun] Clave {k!r} con {len(k)} valores para una PK de "
                         f"{len(pk)} columnas en {tabla}.")
        # Un NULL en la PK no puede llegar aquí: el upsert lo rechazaría después,
        # pero para entonces ya se habría BORRADO. Se para antes de tocar nada.
        if any(v is None for v in k):
            raise Aborta(f"[foto_comun] Clave con NULL en la PK de {tabla}: {k!r} "
                         f"(columnas {pk}). Una clave incompleta no puede decidir qué "
                         f"se borra. Abortando.")

    tmp = f"_foto_{tabla}"
    cur.execute(f"DROP TABLE IF EXISTS {tmp};")
    # WITH NO DATA hereda los tipos exactos de la PK: nada que declarar a mano.
    cur.execute(f"CREATE TEMP TABLE {tmp} AS SELECT {', '.join(pk)} FROM {tabla} WITH NO DATA;")
    execute_values(cur, f"INSERT INTO {tmp} ({', '.join(pk)}) VALUES %s", list(claves))

    clausula, args = _clausula_ambito(ambito, 't')
    enlace = " AND ".join(f"k.{c} = t.{c}" for c in pk)
    cur.execute(
        f"DELETE FROM {tabla} AS t "
        f"WHERE {clausula} "
        f"  AND NOT EXISTS (SELECT 1 FROM {tmp} AS k WHERE {enlace});", args)
    borradas = cur.rowcount
    cur.execute(f"DROP TABLE {tmp};")
    return borradas


# ---------------------------------------------------------------------------
# EL HISTÓRICO: apilar la foto viva ANTES de que la carga la sobrescriba
# ---------------------------------------------------------------------------
def archivar_foto(cur, tabla_viva, pk_cols, col_fecha, etiqueta='HISTORICO', excluir=()):
    """Apila la foto viva ACTUAL en su histórico `<tabla_viva>_hist` ANTES de que
    el barrido/upsert la sobrescriban. Cajón PELÍCULA (§1.6): apila, NUNCA borra.

    `excluir` = columnas de la foto viva que NO se archivan (por defecto (): nada
    se excluye, comportamiento idéntico al de siempre para todas las cañerías).
    Sirve para sacar del histórico datos que ya viven en otro sitio con más margen
    —el caso de keepa: `crudo` es una copia del CSV que ya está en Storage—. Las
    columnas excluidas se quitan de `cols_viva` ANTES de la guarda `faltan_en_hist`,
    así que el histórico puede NO tener esas columnas sin que esto aborte. Una
    columna de la clave de idempotencia NUNCA puede excluirse (se comprueba).

    Va DENTRO de la misma transacción que la carga: si la carga se revierte, el
    archivado también. La garantía es "ninguna foto se sobrescribe sin haberla
    guardado primero".

    - IDEMPOTENTE por (PK de la foto + `col_fecha`): correr dos veces la misma
      foto no duplica. La clave lleva la PK ENTERA, no solo (asin, fecha): un
      mismo ASIN en dos dominios el mismo día son DOS asientos, y una clave corta
      archivaría solo uno (la trampa que trae el SQL del recado, medida contra el
      escaparate multi-país).
    - El histórico se CREA si no existe, clonado de la foto viva + `archivado_en`,
      y nace CERRADO (RLS on, cero políticas). Si ya existe (lo creó otra mano),
      NO se toca su seguridad ni su esquema: solo se le asegura el índice.
    - ROBUSTO AL ESQUEMA (el «Aviso de diseño» del recado, hecho dato): las
      columnas se derivan de la intersección real viva∩hist. Si la foto viva
      tiene una columna que el histórico no → ABORTA en vez de desalinear un
      `SELECT *` en silencio.

    Devuelve el nº de filas archivadas (0 si la foto de hoy ya estaba).
    """
    tabla_viva = _ident(tabla_viva)
    tabla_hist = _ident(f'{tabla_viva}_hist')
    pk = [_ident(c) for c in pk_cols]
    col_fecha = _ident(col_fecha)
    idem = pk + [col_fecha]

    # Columnas a excluir del archivado (identificadores validados). Una columna de
    # la clave de idempotencia JAMÁS se excluye: sin ella el NOT EXISTS archivaría
    # duplicados o mal. Si se pide, se ABORTA (no se elige en silencio).
    excluir_id = {_ident(c) for c in excluir}
    conflicto = excluir_id & set(idem)
    if conflicto:
        raise Aborta(f"[{etiqueta}] No se puede excluir del archivado una columna de la "
                     f"clave de idempotencia {idem}: {sorted(conflicto)}. Abortando.")

    # ¿Existe la foto viva? Si no, no hay pasado que archivar (primera corrida).
    cur.execute("SELECT to_regclass(%s);", (f'public.{tabla_viva}',))
    if cur.fetchone()[0] is None:
        return 0

    # Asegurar el histórico. Se CREA cerrado SOLO si no existía; si ya está, no se
    # toca su RLS ni su esquema (puede ser de otra cañería/otra mano).
    cur.execute("SELECT to_regclass(%s);", (f'public.{tabla_hist}',))
    if cur.fetchone()[0] is None:
        cur.execute(f"CREATE TABLE {tabla_hist} (LIKE {tabla_viva});")   # columnas + NOT NULL, sin PK
        cur.execute(f"ALTER TABLE {tabla_hist} "
                    f"ADD COLUMN archivado_en timestamptz NOT NULL DEFAULT now();")
        cur.execute(f"ALTER TABLE {tabla_hist} ENABLE ROW LEVEL SECURITY;")   # nace CERRADA
    # El índice de la clave idempotente sí se asegura siempre (es inocuo: ni toca
    # datos ni seguridad, y es lo que hace barato el NOT EXISTS de cada pasada).
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabla_hist}_idem "
                f"ON {tabla_hist} ({', '.join(idem)});")

    # Columnas reales de viva e histórico, leídas AHORA (dentro de la txn: la DDL
    # de arriba ya es visible). Nada de SELECT *: se enumeran, se validan y se
    # guarda el TIPO SQL exacto de cada una (format_type) para poder dar el remedio.
    def _cols(tabla):
        cur.execute(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), "
            "       (NOT a.attnotnull) AS nullable, "
            "       pg_get_expr(ad.adbin, ad.adrelid) AS defecto "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum "
            "WHERE n.nspname = 'public' AND c.relname = %s "
            "  AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY a.attnum;", (tabla,))
        return cur.fetchall()

    viva_rows = _cols(tabla_viva)
    # Se quitan las excluidas AQUÍ, antes de todo lo demás: así ni se copian (INSERT)
    # ni se exigen en el histórico (guarda faltan_en_hist). El resto de la función
    # no las ve.
    cols_viva = [_ident(r[0]) for r in viva_rows if _ident(r[0]) not in excluir_id]
    tipo_viva = {r[0]: r[1] for r in viva_rows}     # columna → tipo SQL exacto ('text', 'text[]', 'jsonb'…)
    hist_rows = _cols(tabla_hist)
    hist_cols = {r[0] for r in hist_rows}

    # La clave de idempotencia tiene que existir en la foto viva.
    faltan_clave = [c for c in idem if c not in cols_viva]
    if faltan_clave:
        raise Aborta(f"[{etiqueta}] La clave de idempotencia {idem} referencia columnas que "
                     f"{tabla_viva} no tiene: {faltan_clave}. Abortando.")

    # Robustez al esquema, en los DOS sentidos, RUIDOSA:
    #   · la foto trae una columna que el histórico no puede guardar → ABORTA, y
    #     el mensaje trae el ALTER TABLE EXACTO para copiar y pegar. El riesgo
    #     domesticado: parar la carga sí (mejor eso que archivar mal), pero sin
    #     dejarte con un susto y una cañería parada sin remedio a mano.
    faltan_en_hist = [c for c in cols_viva if c not in hist_cols]
    if faltan_en_hist:
        remedio = "\n".join(
            f"    ALTER TABLE {tabla_hist} ADD COLUMN {c} {tipo_viva[c]};"
            for c in faltan_en_hist)
        raise Aborta(
            f"[{etiqueta}] La foto {tabla_viva} tiene {len(faltan_en_hist)} columna(s) que "
            f"{tabla_hist} NO tiene: {faltan_en_hist}. Se PARA la carga (mejor parar que "
            f"archivar mal). Remedio para copiar y pegar en el entorno, y relanzar:\n"
            f"{remedio}\n"
            f"Se añaden NULLABLE a propósito: las filas históricas viejas no traen ese dato. "
            f"No se ha archivado ni cargado nada.")
    #   · el histórico exige una columna NOT NULL sin defecto que la foto no llena.
    obligatorias_sin_cubrir = [
        r[0] for r in hist_rows
        if r[0] not in cols_viva and r[0] != 'archivado_en' and not r[2] and r[3] is None]
    if obligatorias_sin_cubrir:
        raise Aborta(
            f"[{etiqueta}] {tabla_hist} exige columnas NOT NULL sin defecto que {tabla_viva} "
            f"no rellena: {obligatorias_sin_cubrir}. El INSERT reventaría. No se archiva nada.")

    # Apilar: la foto viva entera que aún NO esté archivada (por PK + fecha).
    cond = " AND ".join(f"h.{c} IS NOT DISTINCT FROM v.{c}" for c in idem)
    cur.execute(
        f"INSERT INTO {tabla_hist} ({', '.join(cols_viva)}, archivado_en) "
        f"SELECT {', '.join('v.' + c for c in cols_viva)}, now() "
        f"FROM {tabla_viva} AS v "
        f"WHERE NOT EXISTS (SELECT 1 FROM {tabla_hist} AS h WHERE {cond});")
    return cur.rowcount


def resumen_foto(tabla, ambito, previas, nuevas, altas, borradas, modo):
    """Las cuatro cañerías imprimen lo mismo, con las mismas palabras."""
    verbo = 'se ha' if modo == 'aplicar' else 'se habría'
    return (
        f"\n--- FOTO {tabla} ({describir_ambito(ambito)}) ---\n"
        f"   · filas que había antes:    {previas}\n"
        f"   · filas del fichero:        {nuevas}\n"
        f"   · altas (clave nueva):      {altas}\n"
        f"   · actualizaciones:          {nuevas - altas}\n"
        f"   · BAJAS ({verbo} borrado):{'':<{max(0, 10 - len(verbo))}}{borradas}")


# ---------------------------------------------------------------------------
# EL REFRESCO DE LAS VISTAS MATERIALIZADAS
# ---------------------------------------------------------------------------
# 🔴 SE ATA AL EVENTO, NO AL RELOJ. Estas materializadas solo pueden cambiar
#    cuando cambia su fuente, y su fuente solo cambia cuando entra un informe.
#    Un cron las refrescaria a ciegas: la mayoria de las veces sin nada que
#    hacer, y las que importan con horas de retraso.
#
# 🔴 VA DESPUES DEL COMMIT, Y FUERA DE LA TRANSACCION. Refrescar sin bloquear a
#    quien este leyendo la pantalla NO se puede hacer dentro de un bloque de
#    transaccion: Postgres lo prohibe. Por eso esto se llama con el volcado ya
#    confirmado y pone la conexion en autocommit.
#    ⚠️ Y por eso mismo NO puede vivir en la migracion (que corre entera dentro
#       de una transaccion). El SQL crea la materializada; el refresco es de aqui.
#
# 🔒 EL ORDEN ES REFRESCAR -> COMPROBAR -> AVISAR, y el aviso SOLO si el
#    refresco fue bien. Al reves, la app tiraria su cache, releeria la copia
#    VIEJA y la volveria a cachear con sello nuevo: dato caducado disfrazado de
#    fresco, que es peor que no avisar.
#
# 🔴 `current_user` SE REGISTRA SIEMPRE, no solo cuando falla. `REFRESH
#    MATERIALIZED VIEW` no se resuelve con permisos: EXIGE SER DUENO. Y la
#    conexion del procesador (DB_URL del ENTORNO) puede no ser la misma que la
#    de la migracion: staging contesta sobre staging. Si esto no se registrara,
#    un refresco que no puede correr en produccion se descubriria cuando alguien
#    mirase la pantalla y viera ventas viejas.

# 🔴 UNA ENTRADA POR CADA FUENTE DE CADA MATERIALIZADA, no por cada fuente "obvia".
#    `v_ventas_ventanas` bebe de TRES tablas, no de dos: ademas del ledger y las
#    transacciones lee `listings_amazon`, y no de adorno -- es el MAPA SKU -> ASIN
#    (`sku_asin AS (SELECT DISTINCT ON (btrim(seller_sku)) ... FROM listings_amazon)`).
#    Las ventas de marketplace llegan por SKU y esa tabla dice a que ASIN pertenecen.
#    Si entra un informe de listings sin que entre uno de ledger o transacciones --una
#    referencia nueva, un SKU que cambia de ASIN--, la copia se queda con el mapa viejo
#    y las ventas de ese SKU dejan de sumarse a su ASIN: el numero sale BAJO.
# 🔒 La lista de fuentes NO se escribe de memoria: se deriva con el mapeador recursivo
#    de `pg_depend` (con freno de ciclos). Escribirla a mano es como se perdio listings
#    en la primera version de este mapa.
REFRESCOS_POR_FUENTE = {
    # fuente que cambia  ->  materializadas que dependen de ella
    'ledger':        ('mv_ventas_ventanas',),
    'transacciones': ('mv_ventas_ventanas', 'mv_rentabilidad_sku'),
    'listings':      ('mv_ventas_ventanas',),
}

# Que hay que tirar de la cache de la app cuando una materializada se pone al dia.
# 🔑 Va por MATERIALIZADA y no por fuente: un informe de ledger no toca la
#    rentabilidad, y mandar su etiqueta seria invalidar una cache que estaba bien.
#    Sobra-invalidar no da un dato falso, pero si da trabajo que nadie pidio.
ETIQUETAS_POR_VISTA = {
    'mv_ventas_ventanas':  ('inventario', 'ventas'),
    'mv_rentabilidad_sku': ('rentabilidad',),
}


def avisar_a_la_app(etiquetas, escribir=print):
    """Invalida la cache de datos de la app para esas etiquetas.

    🔒 HOY NO HACE NADA MAS QUE REGISTRARLO, y la ruta del otro lado devuelve 200
       sin trabajar. Es a proposito: un no-op que nunca se ejecuta es codigo
       muerto, y el dia que se encienda falla por una variable mal escrita. Asi
       el camino se recorre entero desde el primer dia y encenderlo es cambiar el
       cuerpo de la ruta, no volver a tocar nueve procesadores.
    """
    escribir(f"   · aviso a la app (etiquetas: {', '.join(etiquetas)}): "
             f"pendiente de encender, ver /api/cache/invalidar")
    return True


def refrescar_vistas(con, fuente, escribir=print):
    """Refresca las materializadas que dependen de `fuente`. Devuelve True si TODAS
    quedaron al dia.

    `con` es la conexion del procesador CON EL COMMIT YA HECHO. Esta funcion la
    pone en autocommit, refresca, comprueba y la deja como estaba.

    🔴 NO ABORTA NUNCA. La carga del informe --que es lo que importa-- ya esta
       confirmada; el refresco es aguas abajo. Un fallo aqui se GRITA con todo lo
       que hace falta para arreglarlo (quien es, quien es el dueno, y el error
       exacto), y el centinela de la pantalla lo dira tambien en el dato.
    """
    vistas = REFRESCOS_POR_FUENTE.get(fuente, ())
    if not vistas:
        return True

    # 🔴 TODO LO QUE PUEDE FALLAR VA DENTRO DEL `try`, Y `con.autocommit = True` PUEDE
    #    FALLAR. Aqui vivio un bug que hacia FALSA la garantia de la linea de abajo: esa
    #    asignacion estaba FUERA, y con una transaccion abierta psycopg2 lanza
    #    `ProgrammingError: set_session cannot be used inside a transaction`. En un
    #    procesador real eso habria TUMBADO LA CARGA DEL INFORME -- exactamente lo que
    #    este arreglo existe para impedir. Y la mesa de pruebas no lo cazo porque la
    #    conexion de mentira siempre llegaba a esa linea en estado limpio.
    #
    # 🔴 Y SI LLEGA UNA TRANSACCION ABIERTA, NO SE TOCA: SE RENUNCIA AL REFRESCO.
    #    No se da por hecho que el caller llame justo despues del commit --es verdad en el
    #    camino que se escribio y falso en cualquier otro: basta un SELECT despues para
    #    que psycopg2 abra una transaccion implicita--.
    #    ⚠️ AQUI HUBO UN ROLLBACK, Y ERA UN ERROR. Se justificaba con "sobre una
    #       transaccion de solo lectura no deshace nada", que es cierto y DA POR HECHO
    #       justo lo que no se puede saber en este punto. Una transaccion abierta
    #       significa que quien llamo tenia trabajo SIN CONFIRMAR, y hacerle rollback se
    #       lo DESTRUYE.
    #    🔑 La opcion conservadora de verdad es no tocarla: se grita, se devuelve False y
    #       no se refresca. Lo que se pierde es que la copia se quede vieja, Y ESO LO CAZA
    #       EL CENTINELA. Lo que se evitaria perder con un rollback no lo caza nadie.
    antes = con.autocommit
    cur = None
    todo_bien = True
    try:
        if not antes and con.info.transaction_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            escribir("   · ❌ NO SE REFRESCA: me han llamado con una TRANSACCION ABIERTA.")
            escribir("        Refrescar exige salir de la transaccion, y salir de ella "
                     "significaria")
            escribir("        confirmar o deshacer trabajo que NO es mio. No se toca.")
            escribir("        Quien llame debe hacer commit (o rollback) ANTES de pedir el "
                     "refresco.")
            escribir("        La copia se queda vieja, y eso lo dice la pantalla por su "
                     "centinela.")
            return False
        con.autocommit = True
        cur = con.cursor()
        cur.execute("SELECT current_user")
        quien = cur.fetchone()[0]
        escribir(f"\n--- REFRESCO DE MATERIALIZADAS (fuente: {fuente}) ---")
        escribir(f"   · conectado como: {quien}")

        for vista in vistas:
            cur.execute("SELECT to_regclass(%s)", (f'public.{vista}',))
            if cur.fetchone()[0] is None:
                escribir(f"   · ⚠️  {vista} NO EXISTE todavia: no se refresca nada.")
                escribir(f"        No es un fallo de esta carga --el informe ya esta escrito--")
                escribir(f"        sino que la migracion que la crea aun no se ha aplicado en")
                escribir(f"        este entorno. Aplicala y el proximo informe la pondra al dia.")
                todo_bien = False
                continue

            cur.execute("SELECT pg_get_userbyid(relowner) FROM pg_class "
                        "WHERE oid = %s::regclass", (f'public.{vista}',))
            dueno = cur.fetchone()[0]
            t0 = time.time()
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY public.{_ident(vista)}")
            except psycopg2.Error as e:
                escribir(f"   · ❌ {vista}: NO SE HA PODIDO REFRESCAR.")
                escribir(f"        conectado como : {quien}")
                escribir(f"        dueno de la mv : {dueno}")
                escribir(f"        error          : {str(e).strip()}")
                escribir(f"        REFRESH exige SER DUENO: ni SELECT ni ALL PRIVILEGES valen.")
                escribir(f"        Si {quien} no es {dueno} ni miembro suyo, hay que darle la")
                escribir(f"        propiedad o envolver el refresco en una funcion SECURITY")
                escribir(f"        DEFINER de {dueno} con EXECUTE para {quien}.")
                todo_bien = False
                continue
            ms = (time.time() - t0) * 1000
            escribir(f"   · {vista} refrescada en {ms:.0f} ms (dueno: {dueno})")

    except Exception as e:
        # 🔴 NO SE DEJA SUBIR LA EXCEPCION, NUNCA. El commit ya paso: el informe esta
        #    escrito y a salvo. Si esto tumbara la corrida, el workflow saldria ROJO y
        #    quien lo mirase pensaria que la carga fallo -- y volveria a subir el
        #    informe, que es el dano de verdad. Se grita y se sigue.
        # 🔒 Y es seguro hacerlo asi precisamente porque el centinela de la pantalla ya
        #    esta desplegado: si el refresco se cae callado, la pantalla lo DICE. Sin ese
        #    centinela, tragarse el fallo aqui seria esconderlo.
        escribir(f"   · ❌ EL REFRESCO HA REVENTADO: {type(e).__name__}: {str(e).strip()}")
        escribir(f"        La CARGA DEL INFORME NO se ve afectada: el commit ya se hizo y")
        escribir(f"        el dato esta escrito. NO vuelvas a subir el informe.")
        escribir(f"        Lo que queda viejo es la copia materializada, y la pantalla lo")
        escribir(f"        dira por su cuenta (centinela de frescura).")
        return False
    finally:
        # 🔒 SE RESTAURA SIEMPRE, tambien si reventamos: dejar la conexion en autocommit
        #    cambiaria el comportamiento del procesador que nos llamo -- sus siguientes
        #    escrituras se confirmarian solas, sin transaccion. Y el propio restablecer
        #    puede fallar (conexion caida), asi que tampoco puede propagar.
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            con.autocommit = antes
        except Exception:
            pass

    # 🔒 AVISAR SOLO SI FUE BIEN. Ver la cabecera: al reves se cachea dato viejo
    #    con sello nuevo.
    if todo_bien:
        etiquetas = tuple(sorted({e for v in vistas for e in ETIQUETAS_POR_VISTA.get(v, ())}))
        avisar_a_la_app(etiquetas, escribir=escribir)
    else:
        escribir("   · aviso a la app: NO se manda, porque el refresco no ha ido bien. "
                 "Tirar la cache ahora releeria la copia vieja y la sellaria como fresca.")
    return todo_bien
