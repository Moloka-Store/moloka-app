# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR KEEPA_ESCAPARATE — Pieza nueva de la Fase 0 de la v2
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el export "Resumen del vendedor" de Keepa (.csv) del buzón
#   informes/keepa_escaparate/ (Supabase Storage de PRODUCCIÓN) y lo vuelca a
#   la tabla `keepa_escaparate`, que es una FOTO de lo que Amazon/Keepa dicen
#   del escaparate, NO una verdad de Moloka.
#
#   - Guarda lo que Keepa declara, TAL CUAL llega. Se tipan 61 columnas y la
#     fila entera (516 columnas) queda además en `crudo jsonb`. Nada se tira.
#   - 🔒 NO escribe en `productos`, ni en `canales_producto`, ni en NINGUNA
#     tabla de la v1. Cero UPDATE fuera de `keepa_escaparate`. Solo FOTOGRAFÍA.
#   - 🔒 Keepa NUNCA escribe identidad (principio A3CON). El EAN que trae es
#     CONTRASTE: un mismo ASIN puede traer VARIOS EAN. `ean_keepa_crudo` se
#     guarda crudo; quien escriba identidad desde aquí rompe el catálogo.
#   - El descuadre vive en el DATO, no en un log: la vista de solo lectura
#     v_keepa_cruce (§5, security_invoker) cruza esta foto con `productos` y
#     `salud_fba` y saca las banderas de descuadre.
#
# LA CLAVE es (asin, dominio). Cada pasada deja SOLO la última foto.
#   - PK (asin, dominio). Idempotente: correr dos veces el mismo fichero deja
#     el mismo resultado.
#   - 🔒 ES UNA FOTO, NO UN COLLAGE (patrón común en foto_comun.py): los
#     (asin, dominio) que ya no vienen en el export se BORRAN, no se quedan de
#     fantasmas. El borrado va acotado AL DOMINIO del export (cada fichero es
#     de un país) y en la MISMA transacción que la carga: o todo o nada.
#
# 🔒 EL NOMBRE DEL FICHERO ES DATO, no decoración. Del nombre salen la fecha de
#   la foto, el dominio (3=DE, 4=FR, 8=IT, 9=ES) y el seller id. La columna
#   'Última actualización' abarca 80 h y NO es la foto de un instante: sin el
#   nombre no se sabe de qué día ni de qué país es → si el nombre no casa con el
#   patrón, se ABORTA.
#
# Precedente a imitar: procesador_salud_fba.py y procesador_all_listings.py
# (ya en producción). Misma escalera (ENTORNO staging|produccion,
# MODO ensayo|aplicar), misma disciplina de guardas.
#
# 🔒 LA REGLA QUE MATÓ AL PR #26: ningún encabezado se conjetura. Los 61
#   encabezados tipados están copiados LITERALMENTE del fichero real. Si al
#   ejecutar un encabezado tipado no aparece EXACTO en la cabecera → ABORTA sin
#   escribir. Nada se "resuelve por aproximación".
# ============================================================================

import os, sys, io, csv, re
from datetime import date, datetime

import psycopg2
from psycopg2.extras import Json
from supabase import create_client

# El patrón de carga de FOTO, común a las cuatro cañerías de la Fase 0.
from foto_comun import (Aborta, guarda_anti_encogimiento, claves_previas,
                        barrer_sobrantes, resumen_foto)

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

# FICHERO (opcional): nombre EXACTO del .csv del buzón que se quiere procesar.
# Vacío = el más reciente, que es el comportamiento de siempre y sigue siendo el
# de por defecto. Existe porque cada export de Keepa es de UN país: con los cuatro
# (DE/FR/IT/ES) subidos a la vez, "el más reciente" procesaría siempre el mismo y
# no habría manera de cargar los otros tres sin ir subiéndolos de uno en uno.
# 🔒 Si se pide un nombre que no está en el buzón se ABORTA: JAMÁS se cae al más
#    reciente de reserva. Procesar en silencio un país distinto del que pediste es
#    exactamente el error que este parámetro viene a evitar.
FICHERO      = os.environ.get('FICHERO', '').strip()

BUCKET, CARPETA = 'informes', 'keepa_escaparate'

# 🔒 "¿la buy box es mía?" se resuelve por SELLER ID, JAMÁS por el nombre.
NUESTRO_SELLER_ID = 'A2R25VOCZPEH8K'

# Patrón del nombre: KeepaExport-{YYYY-MM-DD}-ResumenDelVendedor-{dominio}-{sellerid}.csv
RE_FICHERO = re.compile(
    r'^KeepaExport-(\d{4}-\d{2}-\d{2})-ResumenDelVendedor-(\d+)-([A-Za-z0-9]+)\.csv$'
)
# Dominio Keepa (numérico en el nombre) → Localización esperada en el fichero.
# 🔒 ESTOS PARES SON EL ESTÁNDAR DE KEEPA, no una convención de Moloka:
#     3=DE · 4=FR · 8=IT · 9=ES   (el 10 es India, NO Italia)
# Estuvieron mal hasta el 20-jul-2026: el mapa decía {'9':'es','10':'it','8':'fr'}.
# Con aquél, el fichero de IT (el 8) se guardaba etiquetado 'fr' —dato bueno, país
# equivocado— y los de DE (3) y FR (4) ni existían en el dict: abortaban en la
# Guarda 4 como "dominio desconocido". Solo no rompía porque únicamente se cargaba
# ES. Medido contra los cuatro ficheros reales del 20-jul (DE 86 · FR 89 · IT 89 ·
# ES 212), todos del seller A2R25VOCZPEH8K.
DOMINIO_NUM = {'3': 'de', '4': 'fr', '8': 'it', '9': 'es'}

# ---------------------------------------------------------------------------
# Columnas TIPADAS: (encabezado EXACTO del CSV, columna Postgres, tipo).
#   tipo: 't' text · 'i' integer · 'n' numeric · 'b' boolean · 'd' date ·
#         'ts' timestamptz · 'as' text[] (split por ';') · 'ac' text[] (split por ',').
# 🔒 El encabezado se compara EXACTO (sin BOM, sin espacios sobrantes). Si uno
#    no aparece → Guarda 1 ABORTA. No se adivina, no se aproxima.
# ---------------------------------------------------------------------------
TIPADAS = [
    ('ASIN', 'asin', 't'),
    ('Localización', 'dominio', 't'),
    ('Códigos de producto: EAN', 'ean_keepa_crudo', 't'),      # CONTRASTE, nunca identidad
    ('Códigos de producto: UPC', 'upc_keepa', 't'),
    ('Título', 'titulo', 't'),
    ('Marca', 'marca', 't'),
    ('Fabricante', 'fabricante', 't'),
    ('Tipo', 'tipo_producto', 't'),
    ('Imagen', 'imagenes', 'as'),                              # split por ";"
    ('Recuento de imágenes', 'n_imagenes', 'i'),
    ('Tarifa FBA Pick&Pack', 'tarifa_fba', 'n'),               # EL PREMIO
    ('% de comisión de referencia', 'comision_pct', 'n'),      # quitar " %"
    ('Comisión de referencia basada en el precio actual de la Buy Box', 'comision_eur_bb', 'n'),
    ('Caja de Compra: Actual', 'bb_precio', 'n'),
    ('Caja de Compra: Vendedor Caja de Compra', 'bb_vendedor', 't'),   # + bb_seller_id aparte
    ('Caja de Compra: Es FBA', 'bb_es_fba', 'b'),
    ('Caja de Compra: Stock', 'bb_stock', 'i'),
    ('Caja de Compra: % Amazon 30 días', 'bb_pct_amazon_30d', 'n'),
    ('Caja de Compra: Disponibilidad de la Caja de Compra', 'bb_disponibilidad', 't'),
    ('Vendedor FBA más barato', 'fba_mas_barato', 't'),
    ('Vendedor FBM más barato', 'fbm_mas_barato', 't'),
    ('Nuevo, de Vendedor Externo FBA: Actual', 'p3_fba_precio', 'n'),
    ('Nuevo, de Vendedor Externo FBA: Stock', 'p3_fba_stock', 'i'),
    ('Nuevo, de Vendedor Externo FBM: Stock', 'p3_fbm_stock', 'i'),
    ('Recuento ofertas nuevas: Actual', 'ofertas_nuevas', 'i'),
    ('Recuento ofertas nuevas FBA: Actual', 'ofertas_nuevas_fba', 'i'),
    ('Recuento ofertas nuevas FBM: Actual', 'ofertas_nuevas_fbm', 'i'),
    ('Recuento total de Ofertas', 'ofertas_total', 'i'),
    ('Umbral de precio competitivo', 'umbral_competitivo', 'n'),   # RECADO para el trackeador
    ('Amazon: Actual', 'amazon_precio', 'n'),
    ('Amazon: Disponibilidad de la oferta de Amazon', 'amazon_disponibilidad', 't'),
    ('Clasificación de Ventas: Actual', 'rank', 'i'),
    ('Clasificación de Ventas: Promedio de 30 días', 'rank_30d', 'i'),
    ('Clasificación de Ventas: Promedio de 90 días', 'rank_90d', 'i'),
    ('Clasificación de Ventas: Descensos en los últimos 30 días', 'rank_drops_30d', 'i'),
    ('Clasificación de Ventas: Descensos en los últimos 90 días', 'rank_drops_90d', 'i'),
    ('Categorías: Principal', 'categoria', 't'),
    ('Categorías: Subcategoría', 'subcategoria', 't'),
    ('Tendencias de ventas mensuales: Ventas mensuales (Último conocido)', 'monthly_sold_ultimo', 'i'),
    ('Tendencias de ventas mensuales: Fecha de ventas mensuales (Último conocido)', 'monthly_sold_ultimo_fecha', 'd'),
    ('Tendencias de ventas mensuales: Comprados el mes pasado', 'comprados_mes_pasado', 'i'),
    ('ASIN Padre', 'asin_padre', 't'),
    ('ASIN de variación', 'asins_variacion', 'ac'),           # split por ","
    ('Recuento de variaciones', 'n_variaciones', 'i'),
    ('Atributos de variación', 'atributos_variacion', 't'),
    ('Paquete: Peso (g)', 'paq_peso_g', 'n'),
    ('Paquete: Longitud (cm)', 'paq_largo_cm', 'n'),
    ('Paquete: Anchura (cm)', 'paq_ancho_cm', 'n'),
    ('Paquete: Altura (cm)', 'paq_alto_cm', 'n'),
    ('Fecha de lanzamiento', 'fecha_lanzamiento', 'd'),       # fecha PASADA de salida
    ('Última actualización', 'keepa_actualizado', 'ts'),      # por producto, NO la foto
    ('Listado desde', 'listado_desde', 'd'),
    ('Opiniones: Valoraciones', 'rating', 'n'),
    ('Opiniones: Cantidad de valoraciones', 'n_valoraciones', 'i'),
    ('Frecuencia comprados juntos', 'comprados_juntos', 't'),
    ('URL: Slug de URL', 'slug_amazon', 't'),
    ('Descripción & Características: Característica 1', 'bullet_1', 't'),
    ('Descripción & Características: Característica 2', 'bullet_2', 't'),
    ('Descripción & Características: Característica 3', 'bullet_3', 't'),
    ('Descripción & Características: Característica 4', 'bullet_4', 't'),
    ('Descripción & Características: Característica 5', 'bullet_5', 't'),
]
assert len(TIPADAS) == 61, f"Se esperaban 61 columnas tipadas, hay {len(TIPADAS)}"

TIPO_SQL = {
    't': 'text', 'i': 'integer', 'n': 'numeric', 'b': 'boolean',
    'd': 'date', 'ts': 'timestamptz', 'as': 'text[]', 'ac': 'text[]',
}


# Aborta vive ahora en foto_comun (misma clase para las cuatro cañerías): una
# guarda que aborta se imprime, NO escribe nada y el workflow sale en rojo.


# ---------------------------------------------------------------------------
# Helpers de limpieza y parseo
# ---------------------------------------------------------------------------
def _clean(v):
    """Sin BOM, NBSP→espacio, recortado."""
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()

def txt(v):
    # '-' es el marcador universal de "sin dato" de Keepa → NULL, igual que en
    # ent()/dec(). El parser numérico ya lo trata porque float('-') casca; el de
    # texto no casca y por eso se olvidaba, guardando "hay un vendedor llamado -"
    # donde no hay vendedor. El crudo conserva el '-' original: la despensa no pierde.
    s = _clean(v)
    if s in ('', '-'):
        return None
    return s

def _num_str(v):
    """String listo para float(): sin ' %', sin símbolos de moneda ni espacios."""
    s = _clean(v).replace('%', '').replace('€', '').replace('$', '').strip()
    return s

def ent(v):
    s = _num_str(v)
    if s in ('', '-'):
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None   # el crudo conserva el valor original; la despensa no pierde

def dec(v):
    s = _num_str(v)
    if s in ('', '-'):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def boole(v):
    s = _clean(v).lower()
    if s in ('', '-'):
        return None
    if s in ('yes', 'y', 'sí', 'si', 'true', '1'):
        return True
    if s in ('no', 'n', 'false', '0'):
        return False
    return None

def fecha(v):
    """YYYY/MM/DD o YYYY-MM-DD (conviven ambas). Timestamps: se toma la fecha."""
    s = _clean(v)
    if s in ('', '-'):
        return None
    s = s.split(' ')[0].replace('/', '-')
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None

def marca_tiempo(v):
    """timestamps 'YYYY/MM/DD HH:MM' (con o sin segundos) o solo fecha."""
    s = _clean(v)
    if s in ('', '-'):
        return None
    s = s.replace('/', '-')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def lista(v, sep):
    """Split por sep, recorta cada trozo y descarta vacíos. [] si no hay nada."""
    s = _clean(v)
    if s in ('', '-'):
        return []
    return [t.strip() for t in s.split(sep) if t.strip()]

def parse_val(tipo, raw):
    if tipo == 't':
        return txt(raw)
    if tipo == 'i':
        return ent(raw)
    if tipo == 'n':
        return dec(raw)
    if tipo == 'b':
        return boole(raw)
    if tipo == 'd':
        return fecha(raw)
    if tipo == 'ts':
        return marca_tiempo(raw)
    if tipo == 'as':
        return lista(raw, ';')
    if tipo == 'ac':
        return lista(raw, ',')
    raise ValueError(f"tipo desconocido: {tipo!r}")

def extraer_seller(raw):
    """bb_vendedor/fba/fbm vienen como 'NOMBRE (99%) / SELLERID' o el literal
    'Amazon'. Devuelve el seller id (o 'AMAZON' si es Amazon, None si no hay
    buy box o no se puede extraer). El texto crudo se guarda igualmente."""
    r = _clean(raw)
    if r in ('', '-'):
        return None
    if r.lower() == 'amazon':
        return 'AMAZON'
    m = re.search(r'/\s*([A-Za-z0-9]{9,})\s*$', r)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# El nombre del fichero es DATO (Guarda 4): fecha de la foto, dominio, seller.
# ---------------------------------------------------------------------------
def leer_nombre(fichero):
    m = RE_FICHERO.match(fichero)
    if not m:
        raise Aborta(
            f"[Guarda 4] El nombre del fichero no casa con el patrón "
            f"'KeepaExport-YYYY-MM-DD-ResumenDelVendedor-DOMINIO-SELLERID.csv'.\n"
            f"   Visto: {fichero!r}. Sin nombre válido no se sabe de qué día ni "
            f"de qué país es la foto (la columna 'Última actualización' abarca 80 h "
            f"y NO es un instante). Abortando.")
    fecha_txt, dom_num, seller = m.group(1), m.group(2), m.group(3)
    try:
        fecha_foto = date.fromisoformat(fecha_txt)
    except ValueError:
        raise Aborta(f"[Guarda 4] La fecha del nombre no es válida: {fecha_txt!r}.")
    if dom_num not in DOMINIO_NUM:
        # La lista de conocidos se DERIVA del dict: un mensaje con los pares
        # escritos a mano es el que se queda mintiendo cuando el dict cambia
        # (fue justo lo que pasó hasta el 20-jul-2026).
        conocidos = ", ".join(f"{n}={d.upper()}" for n, d in sorted(DOMINIO_NUM.items(),
                                                                    key=lambda kv: int(kv[0])))
        raise Aborta(f"[Guarda 4] Dominio Keepa desconocido en el nombre: {dom_num!r} "
                     f"(conocidos: {conocidos}).")
    return {'fecha_foto': fecha_foto, 'dominio': DOMINIO_NUM[dom_num],
            'seller_id': seller}


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..9). Sin tocar la base todavía.
# ---------------------------------------------------------------------------
def analizar(texto, fichero, meta):
    lector = csv.reader(io.StringIO(texto), delimiter=',')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 9: anti-vacío
    if len(filas) < 2:
        raise Aborta("[Guarda 9] 0 filas de datos (fichero vacío o no es CSV). Abortando.")

    cabecera = [_clean(c) for c in filas[0]]
    idx = {}
    for i, h in enumerate(cabecera):
        idx.setdefault(h, i)   # primera aparición

    # Guarda 1: los 61 encabezados tipados existen EXACTOS (§0: no se conjetura)
    faltan = [h for h, _, _ in TIPADAS if h not in idx]
    if faltan:
        raise Aborta(
            "[Guarda 1] Encabezados tipados que NO aparecen EXACTOS en el CSV "
            "(regla que mató al PR #26: se ABORTA, no se aproxima):\n   · "
            + "\n   · ".join(repr(h) for h in faltan)
            + f"\n   Cabecera real ({len(cabecera)} cols), primeras 20: {cabecera[:20]}")

    def celda(fila, h):
        i = idx.get(h)
        if i is None or i >= len(fila):
            return ''
        return _clean(fila[i])

    def intp(fila, h):
        """int o None (leniente); se usa en las guardas de cuadre."""
        return ent(celda(fila, h))

    filas_datos = filas[1:]
    claves_vistas = {}
    duplicadas = []
    salida = []
    dom_esperado = meta['dominio']

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 cabecera, +1 para numerar desde 1

        asin_v = celda(fila, 'ASIN')
        loc_v  = celda(fila, 'Localización').lower()

        # Guarda 3: asin vacío
        if asin_v == '':
            raise Aborta(f"[Guarda 3] Fila {num_fila}: 'ASIN' vacío. Abortando.")

        # Guarda 5: el dominio del nombre casa con Localización en TODAS las filas
        if loc_v != dom_esperado:
            raise Aborta(
                f"[Guarda 5] Fila {num_fila} (asin {asin_v}): Localización {loc_v!r} "
                f"no casa con el dominio del nombre del fichero ({dom_esperado!r}). "
                f"El fichero mezcla países o el nombre miente. Abortando.")

        # Guarda 2: par (asin, dominio) duplicado
        k = (asin_v.upper(), dom_esperado)
        if k in claves_vistas:
            duplicadas.append(f"({asin_v}, {dom_esperado}) — filas {claves_vistas[k]} y {num_fila}")
        else:
            claves_vistas[k] = num_fila

        # Guarda 6: ofertas nuevas = FBA + FBM (solo si las tres están, como se midió: 199/199)
        on  = intp(fila, 'Recuento ofertas nuevas: Actual')
        onf = intp(fila, 'Recuento ofertas nuevas FBA: Actual')
        onm = intp(fila, 'Recuento ofertas nuevas FBM: Actual')
        if on is not None and onf is not None and onm is not None:
            if on != onf + onm:
                raise Aborta(
                    f"[Guarda 6] Fila {num_fila} (asin {asin_v}): ofertas nuevas ({on}) "
                    f"≠ FBA+FBM ({onf}+{onm}={onf + onm}).")

        # Guarda 7: total de ofertas >= ofertas nuevas (203/203)
        ot = intp(fila, 'Recuento total de Ofertas')
        if on is not None and ot is not None and ot < on:
            raise Aborta(
                f"[Guarda 7] Fila {num_fila} (asin {asin_v}): total de ofertas ({ot}) "
                f"< ofertas nuevas ({on}).")

        # Guarda 8: recuento de imágenes = nº de URLs tras split por ';' (203/203)
        imgs = lista(celda(fila, 'Imagen'), ';')
        ni = intp(fila, 'Recuento de imágenes')
        if ni is not None and ni != len(imgs):
            raise Aborta(
                f"[Guarda 8] Fila {num_fila} (asin {asin_v}): 'Recuento de imágenes' "
                f"({ni}) ≠ nº de URLs tras split por ';' ({len(imgs)}).")

        # Fila tipada + crudo (fila entera, 516 columnas)
        registro = {}
        for h, db_col, tipo in TIPADAS:
            registro[db_col] = parse_val(tipo, celda(fila, h))
        registro['dominio'] = dom_esperado   # normalizado, ya validado contra Localización
        registro['bb_seller_id'] = extraer_seller(celda(fila, 'Caja de Compra: Vendedor Caja de Compra'))

        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = _clean(fila[i]) if i < len(fila) else ''

        salida.append({'asin': asin_v, 'dominio': dom_esperado,
                       'registro': registro, 'crudo': crudo})

    # Guarda 2 (informe final si hubo duplicados)
    if duplicadas:
        raise Aborta("[Guarda 2] Pares (asin, dominio) duplicados (el procesador NO "
                     "elige):\n   · " + "\n   · ".join(duplicadas))

    return {'filas': salida, 'fichero': fichero, 'meta': meta}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas) y la vista de cruce
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n    ".join(f"{c} {TIPO_SQL[t]}" for _, c, t in TIPADAS)
    return f"""
    CREATE TABLE IF NOT EXISTS keepa_escaparate (
        {cols},
        bb_seller_id  text,
        fichero       text,
        fecha_foto    date,
        seller_id     text,
        crudo         jsonb,
        procesado_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asin, dominio)
    );
    """

# Normalización de EAN/GTIN/UPC para CONTRASTE (§5.1). Vive en una FUNCIÓN, no
# copiada inline en el SQL: la misma regla que la v1 ya tiene validada (UPC-12
# sin cero inicial, Diseño §11.8). Keepa da el EAN con cero a la izquierda
# (0889698946933) y productos.ean va sin él (889698946933); comparados en crudo
# encienden ean_no_confirmado en 183/203 en falso. Se comparan sin ceros a la
# izquierda y solo dígitos.
SQL_FUNCION = """
CREATE OR REPLACE FUNCTION moloka_ean_norm(cod text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(ltrim(regexp_replace(coalesce(cod, ''), '[^0-9]', '', 'g'), '0'), '')
$$;
"""

# 🔒 Sin security_invoker una vista sobre tabla cerrada es una puerta trasera de
# lectura. El descuadre vive en el DATO: una fila por ASIN del escaparate con las
# banderas §5.1-§5.4, más las filas §5.5 (Active en listings sin export).
SQL_VISTA = f"""
CREATE OR REPLACE VIEW v_keepa_cruce
WITH (security_invoker = true) AS
SELECT
    k.asin,
    k.dominio,
    k.titulo,
    k.tarifa_fba,
    k.bb_vendedor,
    k.bb_seller_id,
    -- §5.1 el EAN de la ficha NO aparece entre los que Keepa da para ese ASIN.
    -- Ambos lados por moloka_ean_norm(): solo dígitos, sin ceros a la izquierda.
    ( EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND moloka_ean_norm(p.ean) IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND moloka_ean_norm(p.ean) IN (
              SELECT moloka_ean_norm(e)
              FROM unnest(string_to_array(coalesce(k.ean_keepa_crudo, ''), ',')) AS e
              WHERE moloka_ean_norm(e) IS NOT NULL)) )
      AS ean_no_confirmado,
    -- §5.2 keepa_fba_fee del dominio != tarifa_fba del CSV (tolerancia 0,01 €)
    EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND k.tarifa_fba IS NOT NULL
          AND (CASE k.dominio WHEN 'es' THEN p.keepa_fba_fee_es
                              WHEN 'it' THEN p.keepa_fba_fee_it
                              WHEN 'fr' THEN p.keepa_fba_fee_fr END) IS NOT NULL
          AND abs((CASE k.dominio WHEN 'es' THEN p.keepa_fba_fee_es
                                  WHEN 'it' THEN p.keepa_fba_fee_it
                                  WHEN 'fr' THEN p.keepa_fba_fee_fr END) - k.tarifa_fba) > 0.01)
      AS tarifa_discrepante,
    -- §5.3 ficha activa sin keepa_image y el CSV trae imágenes
    ( EXISTS (SELECT 1 FROM productos p
        WHERE p.activo AND btrim(p.asin) = btrim(k.asin)
          AND coalesce(btrim(p.keepa_image), '') = '')
      AND coalesce(array_length(k.imagenes, 1), 0) > 0 )
      AS sin_foto_curable,
    -- §5.4 stock FBA propio en ese país y la buy box NO es nuestra (por SELLER ID)
    ( EXISTS (SELECT 1 FROM salud_fba s
        WHERE btrim(s.asin) = btrim(k.asin)
          AND upper(s.marketplace) = upper(k.dominio)
          AND coalesce(s.available, 0) > 0)
      AND k.bb_seller_id IS NOT NULL
      AND k.bb_seller_id <> '{NUESTRO_SELLER_ID}' )
      AS buybox_ajena_con_stock,
    -- §5.5 no aplica a filas del escaparate
    false AS activo_sin_export
FROM keepa_escaparate k

UNION ALL

-- §5.5 ASIN 'Active' en listings_amazon que NO aparece en el export (la red del reverso)
SELECT
    l.asin,
    NULL::text    AS dominio,
    l.item_name   AS titulo,
    NULL::numeric AS tarifa_fba,
    NULL::text    AS bb_vendedor,
    NULL::text    AS bb_seller_id,
    NULL::boolean AS ean_no_confirmado,
    NULL::boolean AS tarifa_discrepante,
    NULL::boolean AS sin_foto_curable,
    NULL::boolean AS buybox_ajena_con_stock,
    true          AS activo_sin_export
FROM (
    SELECT btrim(asin) AS asin, max(item_name) AS item_name
    FROM listings_amazon
    WHERE status = 'Active' AND asin IS NOT NULL AND btrim(asin) <> ''
    GROUP BY btrim(asin)
) l
WHERE NOT EXISTS (SELECT 1 FROM keepa_escaparate k WHERE btrim(k.asin) = l.asin);
"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 🔒 PRIMERA línea del log, bien visible.
    print("=== PROCESADOR KEEPA_ESCAPARATE ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print(f"FICHERO: {FICHERO or '(vacío → el más reciente del buzón)'}", flush=True)
    print("=" * 40, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el export más reciente del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA) or []
    except Exception as e:
        sys.exit(f"No se pudo listar {BUCKET}/{CARPETA}/ ({e}). "
                 "¿Existe la carpeta? Créala y sube el export de Keepa en .csv.")
    csvs = [o for o in objs if (o.get('name') or '').lower().endswith('.csv')]
    if not csvs:
        sys.exit(f"No hay ningún .csv en {BUCKET}/{CARPETA}/. "
                 "Sube el export 'Resumen del vendedor' de Keepa (.csv) y relanza.")
    csvs.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)

    if FICHERO:
        # Pedido a dedo: tiene que estar, EXACTO. Sin fallback al más reciente.
        nombres = [o['name'] for o in csvs]
        if FICHERO not in nombres:
            print(f"\n❌ ABORTA (no se ha escrito nada):\n"
                  f"[Guarda fichero] Se pidió procesar {FICHERO!r} y no está en "
                  f"{BUCKET}/{CARPETA}/.\n"
                  f"   Hay {len(nombres)} .csv en el buzón: {nombres}\n"
                  f"   No se cae al más reciente: cargaría un país distinto del que "
                  f"pediste sin avisar.", flush=True)
            sys.exit(1)
        fichero = FICHERO
        print(f"Export elegido (pedido a dedo por FICHERO): {fichero}", flush=True)
    else:
        fichero = csvs[0]['name']
        print(f"Export elegido (el más reciente de {len(csvs)}): {fichero}", flush=True)

    # --- El nombre es DATO (Guarda 4) ---
    try:
        meta = leer_nombre(fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)
    print(f"   · fecha_foto={meta['fecha_foto']} · dominio={meta['dominio']} · "
          f"seller_id={meta['seller_id']}", flush=True)

    crudo_bytes = sb.storage.from_(BUCKET).download(f"{CARPETA}/{fichero}")
    # El real trae UTF-8 con BOM (utf-8-sig). Fallback cp1252.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales 1..9 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero, meta)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    filas = info['filas']
    print(f"\nFilas leídas y cuadradas: {len(filas)} · dominio {meta['dominio']} · "
          f"fecha_foto {meta['fecha_foto']}", flush=True)

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # 🔒 ÁMBITO DE LA FOTO: cada export de Keepa es de UN país. La foto que este
    # fichero sustituye es la de SU dominio, no la tabla entera: sin acotar,
    # cargar el de ES borraría IT y FR enteros.
    AMBITO = ('dominio', [meta['dominio']])

    # Guarda 10: anti-encogimiento. Corre ANTES de borrar y ANTES de escribir.
    try:
        previas = guarda_anti_encogimiento(cur, 'keepa_escaparate', len(filas),
                                           ambito=AMBITO, etiqueta='10')
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # Claves que ya estaban (solo para contar altas). Antes del barrido.
    prev = claves_previas(cur, 'keepa_escaparate', ['asin', 'dominio'], ambito=AMBITO)

    # --- Crear tabla + vista y volcar (todo dentro de la transacción) ---
    cur.execute(sql_crear_tabla())
    cur.execute("CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_asin ON keepa_escaparate(asin);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_keepa_escaparate_dominio ON keepa_escaparate(dominio);")
    cur.execute("ALTER TABLE keepa_escaparate ENABLE ROW LEVEL SECURITY;")   # nace CERRADA
    cur.execute(SQL_FUNCION)   # moloka_ean_norm(): normaliza EAN para el cruce §5.1
    cur.execute(SQL_VISTA)

    cols = [c for _, c, _ in TIPADAS] + ['bb_seller_id', 'fichero', 'fecha_foto', 'seller_id', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    set_upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ('asin', 'dominio'))
    sql_upsert = (f"INSERT INTO keepa_escaparate ({', '.join(cols)}) VALUES ({ph}) "
                  f"ON CONFLICT (asin, dominio) DO UPDATE SET {set_upd}, procesado_at=now();")

    # 🔒 LA FOTO TIRA LA HOJA VIEJA: los (asin, dominio) de ESTE dominio que ya
    # no vienen en el export se BORRAN. Mismo commit que la carga: o todo o nada.
    # Las claves son EXACTAMENTE los valores que el upsert va a escribir.
    claves_nuevas = [(f['registro']['asin'], f['registro']['dominio']) for f in filas]
    try:
        borradas = barrer_sobrantes(cur, 'keepa_escaparate', ['asin', 'dominio'],
                                    claves_nuevas, ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    for f in filas:
        r = f['registro']
        vals = [r[c] for _, c, _ in TIPADAS] + [
            r['bb_seller_id'], fichero, meta['fecha_foto'], meta['seller_id'], Json(f['crudo'])]
        cur.execute(sql_upsert, vals)

    altas = [f for f in filas
             if (f['registro']['asin'], f['registro']['dominio']) not in prev]

    # --- El descuadre vive en el DATO: se lee de la vista (dentro de la txn) ---
    def cuenta_bandera(bandera):
        cur.execute(f"SELECT count(*) FROM v_keepa_cruce WHERE {bandera} IS TRUE;")
        return cur.fetchone()[0]

    n_ean = cuenta_bandera('ean_no_confirmado')
    n_tarifa = cuenta_bandera('tarifa_discrepante')
    n_foto = cuenta_bandera('sin_foto_curable')
    n_bb = cuenta_bandera('buybox_ajena_con_stock')
    n_sinexport = cuenta_bandera('activo_sin_export')

    # --- Resumen (se imprime siempre) ---
    print(resumen_foto('keepa_escaparate', AMBITO, previas, len(filas),
                       len(altas), borradas, MODO), flush=True)

    print(f"\n--- El descuadre (vista v_keepa_cruce · NO aborta · vive en el dato) ---")
    print(f"   · §5.1 ean_no_confirmado (ficha≠Keepa):       {n_ean}")
    print(f"   · §5.2 tarifa_discrepante (>0,01 €):          {n_tarifa}")
    print(f"   · §5.3 sin_foto_curable (ficha sin foto):     {n_foto}")
    print(f"   · §5.4 buybox_ajena_con_stock (no es nuestra):{n_bb}")
    print(f"   · §5.5 activo_sin_export (Active sin export):  {n_sinexport}")

    # --- Escritura (o no) ---
    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {len(filas)} filas en keepa_escaparate "
              f"(tabla y vista listas, RLS activo sin políticas).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(La tabla/vista y el volcado se han probado dentro de una transacción "
              f"revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · filas={len(filas)} · "
          f"altas={len(altas)} · bajas={borradas} · ean_no_confirmado={n_ean} · tarifa_discrepante={n_tarifa} · "
          f"sin_foto_curable={n_foto} · buybox_ajena={n_bb} · activo_sin_export={n_sinexport} ===",
          flush=True)


if __name__ == '__main__':
    main()
