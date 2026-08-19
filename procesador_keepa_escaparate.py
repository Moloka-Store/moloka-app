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
# 🔒 LA REGLA QUE MATÓ AL PR #26: ningún encabezado se conjetura. Los
#   encabezados tipados están copiados LITERALMENTE del fichero real. Si al
#   ejecutar un encabezado tipado no aparece EXACTO en la cabecera → ABORTA sin
#   escribir. Nada se "resuelve por aproximación".
# ============================================================================

import os, sys, io, csv, re
from datetime import date, datetime

import psycopg2
from psycopg2.extras import Json, execute_values
from supabase import create_client

# El patrón de carga de FOTO, común a las cuatro cañerías de la Fase 0.
from foto_comun import (Aborta, conectar_bd, listar_buzon, descargar_buzon, guarda_anti_encogimiento, guarda_no_retroceder, claves_previas,
                        barrer_sobrantes, resumen_foto, archivar_foto)

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

# 🆕 A2 (19-ago-2026) · EL EXPORT DEL **VISUALIZADOR DE PRODUCTOS**, que es el del buzón
#    único: se pega la lista de ASIN del catálogo entero y Keepa devuelve UN CSV por país
#    con todo dentro, esté o no en el escaparate.
#
# 🔬 Verificado contra los seis ficheros reales del 17 y 18-ago-2026: 578 columnas, BOM
#    presente, y **las 62 cabeceras que este procesador busca están las 62**. El export del
#    Visualizador es un SUPERCONJUNTO del Resumen del Vendedor.
#
# 🔴 DEL NOMBRE SOLO SALE LA FECHA. No trae dominio ni seller, y ésa es la diferencia que
#    obliga a todo lo demás: el dominio pasa a leerse del DATO (Guarda 5 bis, en
#    `analizar`) y el `seller_id` se ESTAMPA con `NUESTRO_SELLER_ID`.
#
# 🔒 EL PATRÓN VIEJO SE QUEDA Y SU CAMINO NO CAMBIA NI UNA LÍNEA. Los ficheros del Resumen
#    del Vendedor tienen que seguir entrando exactamente igual que ayer.
#
# ⚠️ EL SUFIJO DEL NAVEGADOR SE TOLERA A PROPÓSITO: al repetir una descarga, Chrome deja
#    `… (1).csv`, `… (2).csv`. 🔬 Cuatro de los seis ficheros reales lo traen. Sin
#    tolerarlo, el segundo intento del día aborta por el nombre — y quien lo sufra
#    aprenderá a renombrar a mano, que es justo donde se cuela el error de país.
#
# ⚠️ Y OJO AL NOMBRE, QUE EL ENCARGO LO TRAÍA MAL: es `KeepaExport-2026-08-18-…`, CON
#    guiones. El encargo decía `KeepaExport20260818…` porque venía de un fichero al que se
#    le habían comido los guiones. Manda el fichero real.
RE_FICHERO_VIS = re.compile(
    r'^KeepaExport-(\d{4}-\d{2}-\d{2})-VisualizadorDeProductos'
    r'(?:\s*\(\d+\)|\s+\d+)?\.csv$'
)

# 🔴 GUARDA 12 · CUÁNTOS DE LOS ASIN DEL FICHERO TIENEN QUE ESTAR EN `productos`.
#
# Existe porque al pasar el escaparate al Visualizador **los dos ficheros dejan de
# distinguirse por el nombre**: hoy `…ResumenDelVendedor…` y `…VisualizadorDeProductos…`
# los separan solos; mañana los dos son «VisualizadorDeProductos». Y el Visualizador es la
# herramienta con la que se escanean CATÁLOGOS DE PROVEEDOR: soltar uno de ésos en este
# buzón por un despiste borraría la foto del país y metería miles de productos ajenos.
# 🔬 La guarda del 50 % de `foto_comun` NO lo caza: solo aborta cuando el fichero trae
#    MENOS de la mitad de lo que había. CRECER pasa limpio.
# Es el mismo error que ya costó caro una vez (los ~3.374 Funko marcados agotados por
# subir un fichero al director equivocado).
#
# 🔬 EL UMBRAL ESTÁ MEDIDO, no puesto a ojo. Contra los diez ficheros reales que había en
#    Descargas el 18-ago-2026, el porcentaje de sus ASIN presentes en `productos`:
#      · los CUATRO del Resumen del Vendedor (11-ago, dominios 3/4/8/9) → **100,0 %**
#      · los SEIS del Visualizador, todos escaneos de proveedor (de 4 a 2.792 filas)
#        → **0,0 % · 3,4 % · 5,2 % · 5,2 % · 5,3 % · 6,2 %**
#    O sea un foso de 74 puntos entre lo legítimo y lo ajeno. El 80 % deja 20 puntos de
#    holgura para los ASIN que se den de baja entre generar la semilla y subir el CSV, y
#    sigue a 74 puntos del peor caso malo.
# 🔒 Lo aprobó Fernando el 19-ago-2026 con esa medición delante.
#
# ⚠️ Y lo que este número NO es: un juicio sobre la calidad del fichero. Un export legítimo
#    da 100 % porque la semilla SALE de `productos` (`lib/buzones/semilla-asin.ts`, en
#    moloka-app-v2). El día que la semilla se genere de otra cosa, este umbral hay que
#    volver a MEDIRLO, no heredarlo.
UMBRAL_PERTENENCIA = 0.80

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
    # 🔴 LOS TRES QUE VIVÍAN SÓLO EN `crudo` Y EL ARCHIVADO TIRABA (11-ago-2026).
    #    `keepa_escaparate_hist` no guarda `crudo` —a propósito: el CSV está en Storage—,
    #    así que estos tres campos no tenían serie histórica y no podían tenerla. Cada
    #    archivado los perdía para siempre. Promovidos a columna, el archivado se los
    #    lleva solo (copia todo menos `crudo`).
    #    🔬 Hoy: 22 fichas con envío, 102 con plazo, 75 con país.
    ('Caja de Compra: Gastos de envío', 'bb_envio', 'n'),
    ('Caja de Compra: País de envío', 'bb_pais_envio', 't'),
    # ⚠️ El plazo va como TEXTO tal cual lo da Keepa ("1 dia", "13 - 24 días", "190 días"):
    #    no se parsea a número aquí. Convertir "13 - 24 días" en un entero obliga a elegir
    #    13 o 24, y esa elección es de quien lo use, no del procesador. Además hay 31
    #    fichas con plazo y sin precio que nadie ha explicado todavía.
    ('Caja de Compra: Tiempo de envío', 'bb_plazo_txt', 't'),
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
# ---------------------------------------------------------------------------
# EL INVENTARIO: las columnas que TIPADAS tiene que declarar, POR NOMBRE.
#
# 🔴 POR QUÉ NO ES UN CONTADOR — y esto no lo pagó un test, lo pagó una carga real.
#    Hasta el 11-ago-2026 aquí ponía `assert len(TIPADAS) == 61`. Ese día se
#    promovieron a columna bb_envio, bb_pais_envio y bb_plazo_txt, nadie subió el
#    61 a 64, y la guarda tumbó los CUATRO exports de Keepa seguidos. El fallo era
#    de un minuto; verlo costó diez entre dos personas, porque el mensaje
#    —«Se esperaban 61 columnas tipadas, hay 64»— decía CUÁNTAS había, no CUÁLES.
#
#    Un contador tiene dos defectos que NO se arreglan subiendo el número:
#      · No nombra. Con 64 columnas, «sobra una» es un acertijo.
#      · Y el peor: **da por bueno un renombrado**. Quita una y añade otra y la
#        cuenta sigue cuadrando, mientras el dato se escribe en otra columna. Ese
#        es el error caro de verdad, y el contador es ciego justo a ése.
#
# 🔒 SÍ, ES UNA SEGUNDA COPIA DE LOS NOMBRES, Y ESE ES EL PUNTO. Generarla a
#    partir de TIPADAS no comprobaría nada: cuadraría siempre. Es el «sí, quiero»
#    explícito de quien toca TIPADAS. Mantenerla cuesta una línea; no tenerla
#    costó cuatro ficheros rebotados.
#
# ⚠️ Se compara como CONJUNTO, no en orden: mover una columna de sitio no rompe
#    nada (`cols` y las tuplas del volcado salen las dos de TIPADAS, así que van
#    siempre en el mismo orden ENTRE SÍ). El orden de aquí abajo es el de TIPADAS
#    sólo para que un diff se lea de un vistazo.
# ---------------------------------------------------------------------------
COLUMNAS_ESPERADAS = (
    'asin', 'dominio', 'ean_keepa_crudo', 'upc_keepa',
    'titulo', 'marca', 'fabricante', 'tipo_producto',
    'imagenes', 'n_imagenes', 'tarifa_fba', 'comision_pct',
    'comision_eur_bb', 'bb_precio', 'bb_vendedor', 'bb_es_fba',
    'bb_stock', 'bb_pct_amazon_30d', 'bb_disponibilidad', 'bb_envio',
    'bb_pais_envio', 'bb_plazo_txt', 'fba_mas_barato', 'fbm_mas_barato',
    'p3_fba_precio', 'p3_fba_stock', 'p3_fbm_stock', 'ofertas_nuevas',
    'ofertas_nuevas_fba', 'ofertas_nuevas_fbm', 'ofertas_total', 'umbral_competitivo',
    'amazon_precio', 'amazon_disponibilidad', 'rank', 'rank_30d',
    'rank_90d', 'rank_drops_30d', 'rank_drops_90d', 'categoria',
    'subcategoria', 'monthly_sold_ultimo', 'monthly_sold_ultimo_fecha', 'comprados_mes_pasado',
    'asin_padre', 'asins_variacion', 'n_variaciones', 'atributos_variacion',
    'paq_peso_g', 'paq_largo_cm', 'paq_ancho_cm', 'paq_alto_cm',
    'fecha_lanzamiento', 'keepa_actualizado', 'listado_desde', 'rating',
    'n_valoraciones', 'comprados_juntos', 'slug_amazon', 'bullet_1',
    'bullet_2', 'bullet_3', 'bullet_4', 'bullet_5',
)


def _comprobar_inventario_tipadas():
    """TIPADAS contra el inventario. NO cuenta: NOMBRA lo que sobra y lo que falta.

    🔑 Y dice DE QUIÉN es el problema, que es la otra mitad del arreglo. Esto salta
       ANTES de hablar con Storage — o sea, sin haber abierto siquiera el CSV—, así
       que un fallo aquí NUNCA es culpa del fichero. Si el log no lo dice, la
       reacción natural de quien lo mira es volver a exportar de Keepa: gasta
       tokens, tarda, y no arregla nada porque el fichero ya estaba bien.
    """
    declaradas = [c for _, c, _ in TIPADAS]
    vistas, duplicadas = set(), []
    for c in declaradas:
        if c in vistas and c not in duplicadas:
            duplicadas.append(c)
        vistas.add(c)
    # dict.fromkeys = únicas conservando el orden de aparición.
    sobran = [c for c in dict.fromkeys(declaradas) if c not in COLUMNAS_ESPERADAS]
    faltan = [c for c in COLUMNAS_ESPERADAS if c not in vistas]
    if not (duplicadas or sobran or faltan):
        return

    def bloque(titulo, cols):
        if not cols:
            return ''
        return '\n   ' + titulo + '\n' + '\n'.join('     · ' + c for c in cols)

    print(
        '\n' + '=' * 72
        + '\n❌ EL PROCESADOR NO CUADRA CONSIGO MISMO. No se ha escrito NADA.'
        + '\n' + '-' * 72
        + '\n🟢 EL FICHERO DE KEEPA ESTÁ BIEN. Ni siquiera se ha llegado a abrir.'
        + '\n   NO vuelvas a exportarlo de Keepa: gastarías tokens para nada. El que'
        + '\n   ya tienes descargado sirve tal cual — cuando esto se arregle, sueltas'
        + '\n   EL MISMO fichero y entra.'
        + '\n   El que no está listo es el PROCESADOR. Lo arregla quien programa.'
        + bloque('Columnas DECLARADAS en TIPADAS que NO están en el inventario:', sobran)
        + bloque('Columnas del INVENTARIO que TIPADAS ya no declara:', faltan)
        + bloque('Columnas DUPLICADAS dentro de TIPADAS:', duplicadas)
        + '\n\n🔧 Arreglo: cuadrar COLUMNAS_ESPERADAS con TIPADAS en este mismo fichero.'
        + '\n   Y si las columnas son NUEVAS, comprobar además que la migración que las'
        + '\n   añade a keepa_escaparate Y a keepa_escaparate_hist está APLICADA: si no,'
        + '\n   el volcado fallaría más tarde, ya con el fichero abierto.'
        + '\n' + '=' * 72 + '\n',
        flush=True)
    # SystemExit y no assert: `python -O` borra los assert, y una guarda que se apaga
    # con una bandera no es una guarda. Además sale limpio, sin traceback encima.
    raise SystemExit(1)


_comprobar_inventario_tipadas()

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
# GUARDA 12 · ¿ESTE FICHERO ES NUESTRO? (pertenencia)
# ---------------------------------------------------------------------------
def guarda_pertenencia(cur, filas, fichero, meta):
    """Aborta si una parte alta de los ASIN del fichero no está en `productos`.

    🔴 EL AGUJERO QUE TAPA. Hasta hoy, los dos exports de Keepa se distinguían solos por el
       nombre: `…ResumenDelVendedor…` era el escaparate y `…VisualizadorDeProductos…` era
       otra cosa. Con el buzón único los DOS son «VisualizadorDeProductos», y el
       Visualizador es justo la herramienta con la que se escanean catálogos de proveedor.
       Un despiste soltando uno de ésos aquí **borra la foto del país** y mete miles de
       productos ajenos.

    🔬 Y NO LO CAZA NADIE MÁS. La guarda del 50 % de `foto_comun` solo aborta cuando el
       fichero trae MENOS de la mitad de lo que había: crecer pasa limpio. El fichero real
       del 18-ago con el que se probó esto trae **2.762 filas** contra las **91** de FR.

    🔒 SE MIDE SOBRE `productos` ENTERA, no sobre la semilla (activos y no-chase). Es a
       propósito y es la lectura INCLUSIVA: un ASIN que se dio de baja entre generar la
       lista y subir el CSV sigue siendo nuestro, y no tiene por qué contar en contra.
    """
    asins = sorted({(f['asin'] or '').strip().upper()
                    for f in filas if (f.get('asin') or '').strip()})
    if not asins:
        raise Aborta("[Guarda 12] El fichero no trae ni un ASIN legible. Abortando.")

    # 🔴 `count(DISTINCT asin)`, no `count(*)`: un ASIN con dos fichas (los hay — 10
    #    repetidos medidos el 19-ago) contaría dos veces y el porcentaje podría pasar del
    #    100 %. Se cuenta cuántos de LOS DEL FICHERO existen, no cuántas fichas los citan.
    cur.execute("""
        select count(distinct upper(btrim(p.asin))) from productos p
         where upper(btrim(p.asin)) = any(%s)
    """, (asins,))
    dentro = cur.fetchone()[0]
    pct = dentro / len(asins)

    print(f"   · Guarda 12 (pertenencia): {dentro}/{len(asins)} ASIN del fichero están en "
          f"`productos` = {pct:.1%} (umbral {UMBRAL_PERTENENCIA:.0%})", flush=True)

    if pct < UMBRAL_PERTENENCIA:
        raise Aborta(
            f"[Guarda 12] Este fichero NO parece del catálogo de Moloka.\n"
            f"   Solo {dentro} de sus {len(asins)} ASIN están en `productos` "
            f"({pct:.1%}), por debajo del umbral del {UMBRAL_PERTENENCIA:.0%}.\n"
            f"   Fichero: {fichero!r} · dominio {meta['dominio']} · {len(filas)} filas.\n"
            f"   Lo más probable es que sea un ESCANEO DE PROVEEDOR bajado con el mismo\n"
            f"   Visualizador de Keepa: desde el buzón único los dos ficheros se llaman\n"
            f"   igual y ya no se distinguen por el nombre.\n"
            f"   🔴 Si entrara, BORRARÍA la foto de '{meta['dominio']}' y la sustituiría por\n"
            f"      productos que no son tuyos. La guarda del 50 % no lo caza porque el\n"
            f"      fichero CRECE, no encoge.\n"
            f"   👉 La lista buena se genera en la app (buzón de Keepa → «Generar lista de\n"
            f"      ASIN»); con ella, este porcentaje sale del 100 %.\n"
            f"   Abortando.")


# ---------------------------------------------------------------------------
# El nombre del fichero es DATO (Guarda 4): fecha de la foto, dominio, seller.
# ---------------------------------------------------------------------------
def leer_nombre(fichero):
    # 🆕 A2 · EL EXPORT DEL VISUALIZADOR VA PRIMERO porque es el del buzón único y pasará a
    #    ser el caso normal. Del nombre solo sale la FECHA: ni dominio ni seller.
    mv = RE_FICHERO_VIS.match(fichero)
    if mv:
        try:
            fecha_foto = date.fromisoformat(mv.group(1))
        except ValueError:
            raise Aborta(f"[Guarda 4] La fecha del nombre no es válida: {mv.group(1)!r}.")
        return {
            'fecha_foto': fecha_foto,
            # 🔴 `None` NO ES UN HUECO QUE SE RELLENE LUEGO CON CUALQUIER COSA: es la señal
            #    de que el dominio TIENE que salir del dato, y la Guarda 5 bis lo exige. Si
            #    alguien lo pusiera a `'es'` «por defecto», un export francés se guardaría
            #    entero como español sin que nada fallase.
            'dominio': None,
            # 🔴 SE ESTAMPA, Y ES EL PUNTO QUE ROMPE EN SILENCIO SI FALTA. «¿La buy box es
            #    mía?» se resuelve comparando `bb_seller_id` con `seller_id` fila a fila.
            #    Con `seller_id` a NULL esa comparación pasa a `null` en TODAS las filas y
            #    el Cockpit se queda ciego de buy box sin un solo error: la columna BB, la
            #    alerta de la caja perdida y los motivos LA_PIERDES / RECUPERADA se apagan
            #    a la vez. Un verde falso de manual.
            'seller_id': NUESTRO_SELLER_ID,
            'origen': 'visualizador',
        }

    m = RE_FICHERO.match(fichero)
    if not m:
        raise Aborta(
            f"[Guarda 4] El nombre del fichero no casa con ninguno de los dos patrones:\n"
            f"     · 'KeepaExport-YYYY-MM-DD-ResumenDelVendedor-DOMINIO-SELLERID.csv'\n"
            f"     · 'KeepaExport-YYYY-MM-DD-VisualizadorDeProductos.csv'"
            f" (admite el sufijo del navegador: ' (1)', ' 2'…)\n"
            f"   Visto: {fichero!r}. Sin nombre válido no se sabe de qué día es la foto "
            f"(la columna 'Última actualización' abarca 80 h y NO es un instante). "
            f"Abortando.")
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
            'seller_id': seller, 'origen': 'resumen'}


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

    # Guarda 1: los encabezados tipados existen EXACTOS (§0: no se conjetura).
    # ⚠️ Sin el número a mano: el «61» que ponía aquí se quedó mintiendo el día que
    #    fueron 64, igual que el contador de arriba. Una cifra escrita en prosa
    #    envejece sola; la lista es la que manda.
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

    # 🔴 GUARDA 5 BIS · EL DOMINIO SALE DEL DATO CUANDO EL NOMBRE NO LO TRAE.
    #
    # Con el export del Visualizador el nombre solo dice la fecha, así que el país lo dice
    # la columna `Localización`. Se exige que sea **UNO SOLO en todo el fichero**: si hay
    # dos, se aborta.
    #
    # 🔑 Es MÁS ROBUSTO que lo de antes, no menos: deja de depender de cómo se llame el
    #    fichero. Un renombrado a mano —o el sufijo del navegador mal puesto— ya no puede
    #    hacer que un export francés se guarde como español.
    # 🔒 Y PARA EL RESUMEN DEL VENDEDOR NO CAMBIA NADA: allí `meta['dominio']` viene del
    #    nombre y la Guarda 5 de siempre sigue confirmando fila a fila que el dato le da la
    #    razón. Nombre manda, filas confirman.
    if dom_esperado is None:
        vistos = set()
        for pos, fila in enumerate(filas_datos):
            loc = celda(fila, 'Localización').lower()
            if loc == '':
                raise Aborta(
                    f"[Guarda 5 bis] Fila {pos + 2}: 'Localización' vacía. Este fichero no "
                    f"trae el país en el nombre, así que la columna es la ÚNICA fuente de "
                    f"país que hay. Sin ella no se sabe qué foto se está sustituyendo. "
                    f"Abortando.")
            vistos.add(loc)
        if len(vistos) != 1:
            raise Aborta(
                f"[Guarda 5 bis] El fichero mezcla {len(vistos)} países en 'Localización': "
                f"{sorted(vistos)}. Cada export de Keepa es de UN país y sustituye la foto "
                f"de ESE país; con dos dentro, cargarlo dejaría medio país sin borrar y "
                f"medio país con datos del otro. Baja un CSV por dominio. Abortando.")
        dom_esperado = vistos.pop()
        # 🔴 SE DEVUELVE POR `meta` porque el ÁMBITO del borrado se calcula con él. Si esto
        #    se quedara solo dentro de esta función, el `DELETE` de la foto se haría sobre
        #    `dominio = None` y no borraría nada: la carga nueva se APILARÍA sobre la vieja
        #    y la Foto se convertiría en un collage de dos días — el error de §1.6 exacto.
        meta['dominio'] = dom_esperado
        print(f"   · dominio LEÍDO DEL DATO (el nombre no lo trae): {dom_esperado}",
              flush=True)

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

# Normalización de EAN/GTIN/UPC para CONTRASTE (§5.1): la función moloka_ean_norm()
# (misma regla validada por la v1, Diseño §11.8; Keepa da el EAN con cero a la
# izquierda y productos.ean sin él, y en crudo encienden ean_no_confirmado en falso).
# 🔒 keepa YA NO la recrea: su definición vive en
# migraciones/2026-07-29_moloka_ean_norm_fuera_del_arranque.sql y se COMPRUEBA que
# existe (abajo). Recrearla en cada carga revertía en silencio cualquier migración
# que la cambiara: la fuente de verdad tiene que ser UNA.

# 🔒 Sin security_invoker una vista sobre tabla cerrada es una puerta trasera de
# lectura. El descuadre vive en el DATO: una fila por ASIN del escaparate con las
# banderas §5.1-§5.4, más las filas §5.5 (Active en listings sin export).
#
# ---------------------------------------------------------------------------
# TRES ESTADOS, NO DOS (decisión de 20-jul-2026, con el escaparate ya multi-país)
# ---------------------------------------------------------------------------
#   true  = hay descuadre
#   false = se ha podido comprobar y NO hay descuadre
#   NULL  = NO APLICA a este dominio: no hay con qué comparar
#
# 🔴 El false y el NULL NO son lo mismo, y confundirlos es el error caro. Hasta
#    hoy las banderas eran booleanas a secas y devolvían `false` allí donde no
#    había NADA que comparar: DE salía con 0 tarifas discrepantes no porque
#    cuadrara, sino porque `productos` ni siquiera tiene columna de tarifa para
#    DE. Un "0 problemas" que en realidad es "no lo he mirado" es exactamente
#    una cifra que miente (§1.4).
#
# Qué aplica dónde, MEDIDO contra staging el 20-jul (no supuesto):
#   · §5.1 EAN  → los CUATRO países. `productos.ean` es el producto FÍSICO, y
#     casa con los ASIN de los cuatro (de 80/86 · es 199/212 · fr 81/89 · it 82/89).
#   · §5.2 tarifa → SOLO es/fr/it. `productos` tiene keepa_fba_fee_es/_it/_fr y
#     NO tiene _de. En DE no es que cuadre: es que no hay con qué comparar.
#     (Que el país viva en un sufijo de columna contradice §1.2, pero eso es
#     deuda de la v1 y no se toca aquí.)
#   · §5.3 foto → los CUATRO. `keepa_image` es la foto del producto, universal,
#     y una foto sacada del export de cualquier país cura la ficha igual.
#   · §5.4 buy box → SOLO donde `salud_fba` cubra ese país. Hoy salud_fba es solo
#     ES (195 filas, marketplace='ES'), así que hoy es solo ES. La condición se
#     DERIVA de salud_fba en vez de escribir 'es' a fuego: el día que salud_fba
#     traiga IT, la bandera se enciende sola en vez de quedarse en NULL callada.
#   · §5.5 sin export → SOLO ES: `listings_amazon` no tiene columna de país, es
#     el listado de ES. Antes cruzaba contra el escaparate SIN filtrar dominio,
#     así que un ASIN que faltaba del export de ES pero salía en el de otro país
#     se escapaba de la alerta (medido: 1 caso real hoy, y crece con cada país).
# La definición de v_keepa_cruce se movió a migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql (es una migración, no arranque).
# El procesador ya no la ejecuta; solo la consulta.


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
    objs = listar_buzon(sb, BUCKET, CARPETA)  # reintenta cortes de red; aborta si no lo es
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
    # 🔒 Con el export del Visualizador el dominio TODAVÍA no se sabe aquí: lo dice el dato,
    #    y el dato aún no se ha bajado. Se dice así en vez de pintar un `None` que se leería
    #    como «no tiene país».
    print(f"   · origen={meta['origen']} · fecha_foto={meta['fecha_foto']} · "
          f"dominio={meta['dominio'] or '(lo dirá el dato)'} · "
          f"seller_id={meta['seller_id']}", flush=True)

    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")
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
    con = conectar_bd(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # 🔒 ÁMBITO DE LA FOTO: cada export de Keepa es de UN país. La foto que este
    # fichero sustituye es la de SU dominio, no la tabla entera: sin acotar,
    # cargar el de ES borraría IT y FR enteros.
    AMBITO = ('dominio', [meta['dominio']])

    # Guarda 12: PERTENENCIA. Corre ANTES que ninguna otra que toque la base, porque es la
    # que decide si este fichero es NUESTRO. Las demás (encogimiento, no-retroceder) dan
    # por hecho que lo es y comparan volúmenes; con un catálogo de proveedor delante,
    # comparar volúmenes no significa nada.
    try:
        guarda_pertenencia(cur, filas, fichero, meta)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # Guarda 10: anti-encogimiento. Corre ANTES de borrar y ANTES de escribir.
    try:
        previas = guarda_anti_encogimiento(cur, 'keepa_escaparate', len(filas),
                                           ambito=AMBITO, etiqueta='10')
        # Guarda 11: no-retroceder. Un export más viejo que el ya cargado no entra
        # (foto caducada = información FALSA). PERMITIR_RETROCESO=1 la salta.
        guarda_no_retroceder(cur, 'keepa_escaparate', 'fecha_foto',
                             meta['fecha_foto'], ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # Claves que ya estaban (solo para contar altas). Antes del barrido.
    prev = claves_previas(cur, 'keepa_escaparate', ['asin', 'dominio'], ambito=AMBITO)

    # --- Crear tabla + vista y volcar (todo dentro de la transacción) ---
    cur.execute(sql_crear_tabla())
    # 🔒 RLS + índices fuera del arranque (migración): el ENABLE RLS pedía
    # AccessExclusiveLock sobre keepa_escaparate EN CADA carga (el lock que dejaba
    # fuera al sondeo de la cola). Viven en
    # migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql. Solo se comprueba
    # que la tabla está CERRADA (RLS activa); si no, ABORTA pidiéndola.
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.keepa_escaparate'::regclass;")
    if not cur.fetchone()[0]:
        raise Aborta(
            "RLS no está activa en keepa_escaparate. Ya NO la activa el procesador (era un lock "
            "exclusivo en cada carga). Aplica migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql y relanza.")
    # moloka_ean_norm(): normaliza EAN para el cruce §5.1. Ya NO se recrea aquí
    # (fuente de verdad única = la migración); solo se comprueba que existe.
    cur.execute("SELECT to_regprocedure('public.moloka_ean_norm(text)');")
    if cur.fetchone()[0] is None:
        raise Aborta(
            "La función moloka_ean_norm(text) no existe. Ya NO la crea el procesador "
            "(recrearla en cada carga revertía en silencio cualquier migración que la "
            "cambiara). Aplica migraciones/2026-07-29_moloka_ean_norm_fuera_del_arranque.sql y relanza.")
    # La vista v_keepa_cruce YA NO se recrea aquí (recrearla en cada carga pedía lock
    # exclusivo sobre media base y tumbó la app el 28-jul 15:47). Su definición vive en
    # migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql. Solo se comprueba que existe.
    cur.execute("SELECT to_regclass('public.v_keepa_cruce');")
    if cur.fetchone()[0] is None:
        raise Aborta(
            "La vista v_keepa_cruce no existe en este entorno. Ya NO la crea el procesador "
            "(era un lock que tumbaba la base). Aplica migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql y relanza.")

    # 🎞️ EL HISTÓRICO: apila la foto viva ANTERIOR en keepa_escaparate_hist ANTES
    # de que el barrido/upsert la sobrescriban (Película §1.6, misma txn). Clave
    # idempotente (asin, dominio, fecha_foto): un ASIN en dos dominios el mismo
    # día son DOS asientos. Corre antes de barrer: captura la foto que va a morir.
    try:
        # 🔒 `crudo` NO se archiva: es copia del CSV de Keepa, que ya vive en Storage
        # (informes/keepa_escaparate/, archivo histórico permanente). El rescate de
        # cualquiera de las 512 claves que solo viven en `crudo` se hace por `fichero`
        # contra ese CSV. Las 63 columnas propias del histórico (bb_*, p3_*, ofertas_*,
        # rank_*, monthly_sold, rating…) SÍ se archivan: son la munición del trackeador.
        arch = archivar_foto(cur, 'keepa_escaparate', ['asin', 'dominio'], 'fecha_foto',
                             excluir=('crudo',))
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    cols = [c for _, c, _ in TIPADAS] + ['bb_seller_id', 'fichero', 'fecha_foto', 'seller_id', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    set_upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ('asin', 'dominio'))
    sql_upsert = (f"INSERT INTO keepa_escaparate ({', '.join(cols)}) VALUES %s "
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

    # 🔒 Volcado por LOTES (execute_values), no fila a fila. SIN dedup a propósito,
    # como salud_fba (y a diferencia de paneu/all_listings): un par (asin, dominio)
    # repetido NO es "la última gana", es un informe corrupto, y la Guarda 2 ya
    # ABORTA por él en analizar() ("el procesador NO elige"); la Guarda 5 obliga a un
    # solo dominio por fichero. Entre las dos, la clave del ON CONFLICT es única
    # antes del volcado: execute_values no puede recibir clave repetida.
    vals_foto = []
    for f in filas:
        r = f['registro']
        vals_foto.append(tuple([r[c] for _, c, _ in TIPADAS] + [
            r['bb_seller_id'], fichero, meta['fecha_foto'], meta['seller_id'], Json(f['crudo'])]))
    execute_values(cur, sql_upsert, vals_foto, template=f"({ph})", page_size=500)

    altas = [f for f in filas
             if (f['registro']['asin'], f['registro']['dominio']) not in prev]

    # --- El descuadre vive en el DATO: se lee de la vista (dentro de la txn) ---
    # 🔒 DESGLOSADO POR DOMINIO. Un "97" a secas, con cuatro países en la tabla, no
    # dice de qué país es y por tanto no es accionable: nadie sabe dónde mirar.
    # Por cada bandera y dominio se cuentan TRES cosas, porque son tres cosas
    # distintas: cuántas dan descuadre (true), cuántas se han comprobado y están
    # bien (false), y cuántas NO APLICAN a ese país (NULL).
    BANDERAS = [('§5.1 ean_no_confirmado',       'ean_no_confirmado'),
                ('§5.2 tarifa_discrepante',      'tarifa_discrepante'),
                ('§5.3 sin_foto_curable',        'sin_foto_curable'),
                ('§5.4 buybox_ajena_con_stock',  'buybox_ajena_con_stock'),
                ('§5.5 activo_sin_export',       'activo_sin_export')]

    # Por dominio: total de filas + (nº de true, nº de NULL) de cada bandera.
    sel = ", ".join(
        f"count(*) FILTER (WHERE {c} IS TRUE), count(*) FILTER (WHERE {c} IS NULL)"
        for _, c in BANDERAS)
    cur.execute(f"SELECT dominio, count(*), {sel} FROM v_keepa_cruce "
                f"GROUP BY dominio ORDER BY dominio;")
    filas_vista = cur.fetchall()
    dominios = [r[0] for r in filas_vista]
    total_dom = {r[0]: r[1] for r in filas_vista}     # filas de la vista por dominio
    por_dominio = {r[0]: r[2:] for r in filas_vista}  # pares (true, null) por bandera

    # Totales del dominio que se ACABA de cargar: son los que van al === FIN ===,
    # porque son los únicos que esta pasada ha podido cambiar.
    # 🔒 'n/a' también aquí: si el === FIN === dijera 'tarifa_discrepante=0' para DE
    # estaría cantando un cero que en realidad es un "no lo he mirado", que es
    # justo lo que este desglose viene a quitar de en medio.
    dom_actual = meta['dominio']

    def cuenta_actual(i):
        if dom_actual not in por_dominio:
            return '0'
        n_true, n_null = por_dominio[dom_actual][i * 2], por_dominio[dom_actual][i * 2 + 1]
        return 'n/a' if n_null == total_dom[dom_actual] else str(n_true)

    n_ean, n_tarifa, n_foto, n_bb, n_sinexport = (cuenta_actual(i) for i in range(5))

    # --- Resumen (se imprime siempre) ---
    print(resumen_foto('keepa_escaparate', AMBITO, previas, len(filas),
                       len(altas), borradas, MODO), flush=True)

    verbo_h = 'archivadas' if MODO == 'aplicar' else 'que se archivarían'
    print(f"\n--- HISTÓRICO keepa_escaparate_hist (Película §1.6: apila, NUNCA borra) ---")
    print(f"   · filas {verbo_h} de la foto anterior: {arch}"
          f"{'   (la foto anterior ya estaba archivada)' if arch == 0 else ''}", flush=True)

    print(f"\n--- El descuadre POR DOMINIO (vista v_keepa_cruce · NO aborta · vive en el dato) ---")
    print(f"    'n/a' = la bandera NO APLICA a ese país (no hay con qué comparar).")
    print(f"    NO es un cero: un cero dice 'lo he mirado y cuadra'.\n")
    print(f"   {'bandera':<32}" + "".join(f"{d:>8}" for d in dominios))
    print(f"   {'-' * (32 + 8 * len(dominios))}")
    for i, (etiqueta, _col) in enumerate(BANDERAS):
        celdas = []
        for d in dominios:
            n_true, n_null = por_dominio[d][i * 2], por_dominio[d][i * 2 + 1]
            # La bandera NO APLICA a este dominio si TODAS sus filas son NULL.
            celdas.append('n/a' if n_null == total_dom[d] else str(n_true))
        print(f"   {etiqueta:<32}" + "".join(f"{c:>8}" for c in celdas))
    print(f"\n   (el dominio recién cargado es {dom_actual!r}; el === FIN === resume ESE)")

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
          f"altas={len(altas)} · bajas={borradas} · hist_archivadas={arch} · "
          f"ean_no_confirmado={n_ean} · tarifa_discrepante={n_tarifa} · "
          f"sin_foto_curable={n_foto} · buybox_ajena={n_bb} · activo_sin_export={n_sinexport} ===",
          flush=True)


if __name__ == '__main__':
    main()
