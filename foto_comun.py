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
# CÓMO SE USA (el orden NO es negociable)
#     previas = guarda_anti_encogimiento(cur, 'tabla', len(filas), ambito)
#     prev    = claves_previas(cur, 'tabla', ['pk1','pk2'], ambito)   # solo contar altas
#     borradas = barrer_sobrantes(cur, 'tabla', ['pk1','pk2'], claves_nuevas, ambito)
#     ... upsert de las filas ...
#     con.commit() si MODO == 'aplicar', si no con.rollback()
#   En ENSAYO el borrado se ejecuta igual (para poder decir cuántas se irían)
#   pero la transacción se revierte: no se escribe ni un byte.
# ============================================================================

import re
from datetime import datetime

from psycopg2.extras import execute_values


class Aborta(Exception):
    """Cualquier guarda que aborta lanza esto: se imprime, NO se escribe nada
    y el workflow sale en rojo."""
    pass


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
