# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR CUSTOM ANALYTICS — el eje de la DEMANDA (Fase 0, MULTIPAÍS)
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el export "Custom Analytics" del Seller (Analytics → panel dimensión ASIN
#   → UN SOLO marketplace → Descargar .xlsx) del buzón informes/custom_analytics/ y
#   carga en `demanda_asin` la demanda por ASIN: visitas, sesiones, conversión,
#   unidades pedidas/enviadas, ventas, reembolsos y —lo que ningún otro informe
#   trae— LA BUY BOX (ratio de oferta destacada). Hasta hoy el sistema sabía qué
#   stock hay y qué se vendió; NO sabía cuánta gente llegó ni quién se llevó la caja.
#
# 🔴 EL CAJÓN: FOTO POR VENTANA (ni FOTO ni PELÍCULA) — §5 del encargo
#   Este informe no dice "cómo está esto AHORA", dice "del día X al día Y pasó esto".
#   Se carga por IGUALDAD de (pais, periodo_desde, periodo_hasta), NUNCA por BETWEEN:
#     1) el país y el periodo los da el SELECTOR (el fichero no los trae),
#     2) en UNA transacción:
#          DELETE FROM demanda_asin
#           WHERE pais=<sel> AND periodo_desde=<sel> AND periodo_hasta=<sel>;  -- IGUALDAD
#          INSERT de todas las filas;
#     3) commit si aplicar, rollback si ensayo.
#   Con igualdad: recargar la MISMA ventana la recierra (idempotente) y ventanas
#   distintas del mismo país CONVIVEN → la tabla ES el histórico, sin `_hist`. Con
#   BETWEEN (como el ledger) cargar 1-ene→30-jul borraría la ventana 1-jul→27-jul,
#   que es OTRA medición y también es verdad.
#
# 🔴 EL PAÍS Y EL PERIODO LOS MANDA EL SELECTOR (§3.5, §6.6)
#   El fichero no dice de qué marketplace es (cabeceras en español los tres, URLs a
#   amazon.com los tres) ni de qué periodo (ni dentro, ni en el nombre, ni deducible).
#   El país entra por el input PAIS y se VERIFICA cruzando las unidades por ASIN con
#   transacciones_movimientos (guarda 6.6): si el declarado no es el de menor error,
#   ABORTA. El periodo entra por PERIODO_DESDE/PERIODO_HASTA y sin él se ABORTA.
#
# 🔒 EL CARGADOR NO INTERPRETA (§3.2)
#   Los tres RATIOS (conversión, ratio de oferta destacada = buy box, ratio de
#   reembolsos) vienen 0-1 AUNQUE la cabecera de Amazon diga "(%)". Se guardan TAL
#   CUAL. Nada de multiplicar por 100 al cargar: quien lo pinte decide.
#
# 🔴 CÓMO SE ABRE EL .xlsx (§0.1 — el fallo grave de la v1 de este encargo)
#   Amazon escribe el ASIN como fórmula `=HYPERLINK("…/dp/B0…","B0…")` SIN valor
#   cacheado. `data_only=True` pide el valor cacheado y devuelve None → TODOS los ASIN
#   saldrían vacíos. Se abre con data_only=False (por defecto) y el ASIN se saca de la
#   fórmula con regex. Medido byte a byte contra los 3 ficheros reales el 31-jul.
#
# 🔒 Escritura por lotes (execute_values), calcado del patrón de la casa. Ni comisión
#   ni ratios se tocan. Encoding: no aplica (openpyxl lee el .xlsx binario).
#
# 🔒 SELLO DE FRESCURA: al aplicar escribe una fila en informes_subidos
#   (tipo='custom_analytics') con los 10 totales del cuadre en resumen_json — donde
#   vive lo que no es una fila. Ojo: la RPC frescura_informes() lee la fecha del dato
#   de demanda_asin.periodo_hasta, NO de aquí (el sello es registro/auditoría).
# ============================================================================

import os, sys, io, re, unicodedata
from datetime import date, datetime, timezone
from collections import Counter, defaultdict
from statistics import median

import psycopg2
from psycopg2.extras import Json, execute_values
import openpyxl

# Del patrón común solo se reutiliza lo de FOTO que aplica: Aborta y las lecturas de
# Storage con reintento. NO barrer_sobrantes/archivar_foto (esto es FOTO POR VENTANA,
# no FOTO: el borrado es por ventana exacta, no "lo que no viene en el fichero").
from foto_comun import Aborta, listar_buzon, descargar_buzon

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL  = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY  = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL        = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO          = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO       = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion
PAIS          = os.environ.get('PAIS', '').strip().upper()             # ES | IT | FR (selector)
FICHERO       = os.environ.get('FICHERO', '').strip()                  # nombre EXACTO; vacío = más reciente
PERIODO_DESDE = os.environ.get('PERIODO_DESDE', '').strip()            # YYYY-MM-DD (selector)
PERIODO_HASTA = os.environ.get('PERIODO_HASTA', '').strip()            # YYYY-MM-DD (selector)

BUCKET, CARPETA = 'informes', 'custom_analytics'
# 🔒 Escalabilidad (§8): la lista de países vive en UN solo sitio por lado. Añadir DE
# o PL es tocar esto + el choice del .yml + las opciones de la ficha v2. Nada más.
PAISES_VALIDOS = ('ES', 'IT', 'FR')

VENTANA_MAX_DIAS = 400   # guarda 6.5: una ventana mayor huele a error de tecleo

# ---------------------------------------------------------------------------
# Las 18 columnas medidas (§3.1). canon → cabecera NORMALIZada (sin acentos, minúsculas,
# espacios colapsados: la col 18 trae DOS espacios antes del paréntesis). Resolución por
# NOMBRE, jamás por posición (§4.4): el panel del 28-jul traía 8 columnas y estos 18.
# ---------------------------------------------------------------------------
CANON_A_CABECERA = {
    'asin':                 'asin',
    'nombre_producto':      'nombre del producto',
    'resenas':              'recuento de resenas de producto',
    'estrellas':            'valoraciones en estrellas generales',
    'visitas':              'visitas',
    'conversion':           'tasa de conversion (%)',
    'unidades_enviadas':    'unidades enviadas',
    'precio_venta_medio':   'precio de venta medio (€)',
    'ventas_enviadas_eur':  'ventas de unidades enviadas (€)',
    'inventario_disponible':'unidades de inventario disponibles',
    'buybox_ratio':         'ratio de oferta destacada',
    'buybox_visiones':      'visiones de ofertas destacadas',
    'reembolsado_eur':      'importe reembolsado (€)',
    'unidades_reembolsadas':'unidades reembolsadas',
    'reembolsos_ratio':     'ratio de reembolsos (%)',
    'sesiones':             'sesiones',
    'unidades_pedidas':     'unidades pedidas',
    'facturacion_pedida_eur':'facturacion neta de productos pedidos (€)',
}
# Tipo de cada columna (para tipar y para el cuadre). El ASIN y el nombre son texto.
COLS_ENTERAS = {'resenas', 'visitas', 'unidades_enviadas', 'inventario_disponible',
                'buybox_visiones', 'unidades_reembolsadas', 'sesiones', 'unidades_pedidas'}
COLS_NUMERICAS = {'estrellas', 'conversion', 'precio_venta_medio', 'ventas_enviadas_eur',
                  'buybox_ratio', 'reembolsado_eur', 'reembolsos_ratio', 'facturacion_pedida_eur'}
# Las 10 ADITIVAS: su suma tiene que cuadrar con la fila Total al céntimo (§3.3).
COLS_ADITIVAS = ('visitas', 'unidades_enviadas', 'ventas_enviadas_eur', 'inventario_disponible',
                 'buybox_visiones', 'reembolsado_eur', 'unidades_reembolsadas', 'sesiones',
                 'unidades_pedidas', 'facturacion_pedida_eur')

# Columnas de la tabla en el orden del INSERT (id/dias/procesado_at aparte).
COLS_DB = ['pais', 'periodo_desde', 'periodo_hasta', 'asin', 'nombre_producto',
           'resenas', 'estrellas', 'visitas', 'sesiones', 'conversion',
           'unidades_pedidas', 'unidades_enviadas', 'precio_venta_medio',
           'ventas_enviadas_eur', 'facturacion_pedida_eur', 'buybox_ratio',
           'buybox_visiones', 'reembolsado_eur', 'unidades_reembolsadas',
           'reembolsos_ratio', 'inventario_disponible', 'fichero', 'exportado_at', 'crudo']

RE_ASIN = re.compile(r'/dp/([A-Z0-9]{10})')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(v):
    return ('' if v is None else str(v)).replace('﻿', '').replace('\xa0', ' ').strip()

def _sin_acentos(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def _norm(s):
    """Cabecera normalizada: sin acentos, minúsculas, espacios colapsados a uno (la col 18
    trae DOS espacios), sin ':' final. Comparar literal fallaría por esos dos espacios."""
    t = _sin_acentos(_clean(s)).lower().rstrip(':').strip()
    return re.sub(r'\s+', ' ', t)

def _txt(v):
    s = _clean(v)
    return s or None

def _num(v):
    """Valor del .xlsx → (float|None, fallo_bool). openpyxl ya devuelve número; se acepta
    también cadena europea por si Amazon cambia el formato (lo caza la guarda 6.4)."""
    if v is None:
        return None, False
    if isinstance(v, bool):   # True/False no es un número aquí
        return None, True
    if isinstance(v, (int, float)):
        return float(v), False
    s = _clean(v)
    if s in ('', '-'):
        return None, False
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s), False
    except ValueError:
        return None, True

def _ent(v):
    f, fallo = _num(v)
    return (int(round(f)) if f is not None else None), fallo

def _fecha_iso(s, etiqueta):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise Aborta(f"[Guarda 6.5] {etiqueta} {s!r} no es una fecha YYYY-MM-DD válida. "
                     f"El periodo lo declara el selector y sin él bien escrito no se carga.")

def _bt(s):
    return _clean(s)


# ---------------------------------------------------------------------------
# 1) PARSEO — recibe BYTES, devuelve filas + totales. NO toca Storage ni la base.
#    Así se ejecuta contra los 3 ficheros locales las veces que haga falta (§2.1).
# ---------------------------------------------------------------------------
def analizar(bytes_xlsx, pais, periodo_desde, periodo_hasta, fichero):
    if pais not in PAISES_VALIDOS:
        raise Aborta(f"[PAIS] {pais!r} no es ES/IT/FR. El país lo manda el selector y no se "
                     f"asume: sin país determinado, se ABORTA (§3.5).")

    # 🔴 data_only=False (por defecto): con True el ASIN sale None (§0.1). read_only para
    # no cargar la hoja entera en memoria; con read_only, max_row/max_col pueden ser None,
    # así que se ITERA y se cuenta a mano (§4.1).
    wb = openpyxl.load_workbook(io.BytesIO(bytes_xlsx), read_only=True)
    ws = wb['metric-data'] if 'metric-data' in wb.sheetnames else wb.active
    creator = _clean(getattr(wb.properties, 'creator', '') or '')
    exportado_at = getattr(wb.properties, 'created', None)
    if isinstance(exportado_at, datetime) and exportado_at.tzinfo is None:
        exportado_at = exportado_at.replace(tzinfo=timezone.utc)   # Amazon exporta en UTC
    filas = list(ws.iter_rows(values_only=True))
    wb.close()

    avisos = []

    # Guarda 6.1: origen. No aborta (el exportador podría cambiar de nombre), grita.
    if 'custom analytics' not in _norm(creator):
        avisos.append(f"[Guarda 6.1] El creator del .xlsx es {creator!r}, sin 'Custom "
                      f"Analytics'. ¿Es de verdad un export de Custom Analytics? (Entra igual.)")

    if not filas or not any(_clean(c) for c in (filas[0] or ())):
        raise Aborta("[Guarda 6.3] El fichero no tiene ni cabecera legible. "
                     "¿Export de Custom Analytics? Abortando.")

    cabecera = list(filas[0])
    cab_norm = [_norm(c) for c in cabecera]

    # Resolver cada columna canónica por NOMBRE normalizado (§4.4).
    canon_idx = {}
    for canon, cab_esperada in CANON_A_CABECERA.items():
        for i, n in enumerate(cab_norm):
            if n == cab_esperada:
                canon_idx[canon] = i
                break

    # Guarda 6.2: sin ASIN no hay nada que cargar → ABORTA con la cabecera real entera.
    if 'asin' not in canon_idx:
        raise Aborta(
            f"[Guarda 6.2] No aparece la columna 'ASIN' en el fichero. NO se aproxima: se "
            f"ABORTA.\n   Cabecera real ({len(cabecera)} cols): {cabecera}")
    idx_asin = canon_idx['asin']

    # Columnas del canon que NO vienen (quedan NULL, no aborta) y columnas del fichero que
    # NO conocemos (se GRITAN: una métrica nueva que nadie ve es una métrica perdida, §4.4).
    ausentes = [c for c in CANON_A_CABECERA if c not in canon_idx]
    conocidas = {CANON_A_CABECERA[c] for c in CANON_A_CABECERA}
    desconocidas = [cabecera[i] for i, n in enumerate(cab_norm) if n not in conocidas]
    if ausentes:
        avisos.append(f"[columnas ausentes] No vienen en el panel (quedan NULL): "
                      f"{sorted(ausentes)}. (El panel se configuró con otras métricas.)")
    if desconocidas:
        avisos.append(f"[columna NUEVA sin canon] El fichero trae columnas que NO conozco → "
                      f"NO se tipan (viven solo en `crudo`): {desconocidas}. Añádelas al "
                      f"procesador si hacen falta como columna.")

    # --- Recorrer las filas de datos (la 2 en adelante). La fila 'Total' se aparta. ---
    datos = []
    total_declarado = None
    fallos = Counter()      # canon → nº de valores que no parsean
    intentos = Counter()    # canon → nº de valores no vacíos (para el % de la guarda 6.4)

    for pos, fila in enumerate(filas[1:], start=2):   # 'pos' = nº de fila real del .xlsx
        a_raw = fila[idx_asin] if idx_asin < len(fila) else None
        a_clean = _clean(a_raw)

        # La fila Total (primera fila de datos, ASIN='Total', nombre vacío): se aparta.
        if a_clean.lower() == 'total':
            total_declarado = fila
            continue

        m = RE_ASIN.search(str(a_raw or ''))
        if not m:
            # Colas de filas totalmente vacías que openpyxl a veces devuelve: se ignoran.
            if not any(_clean(c) for c in fila):
                continue
            raise Aborta(
                f"[Guarda 6.2] Fila {pos}: ASIN no reconocible en la celda {a_raw!r}. "
                f"No se descarta en silencio: se ABORTA. (Se esperaba una fórmula "
                f"=HYPERLINK(\"…/dp/B0…\") o la fila 'Total'.)")
        asin = m.group(1)

        registro = {'pais': pais, 'periodo_desde': periodo_desde, 'periodo_hasta': periodo_hasta,
                    'asin': asin, 'fichero': fichero, 'exportado_at': exportado_at}
        crudo = {}
        for i, h in enumerate(cabecera):     # crudo = fila ENTERA (despensa, §5): todo, tal cual
            crudo[str(h)] = fila[i] if i < len(fila) else None

        for canon, ci in canon_idx.items():
            if canon in ('asin',):
                continue
            val = fila[ci] if ci < len(fila) else None
            if canon == 'nombre_producto':
                registro[canon] = _txt(val)
            elif canon in COLS_ENTERAS:
                v, fallo = _ent(val)
                registro[canon] = v
                if _clean(val) not in ('', '-'):
                    intentos[canon] += 1
                    if fallo:
                        fallos[canon] += 1
            elif canon in COLS_NUMERICAS:
                v, fallo = _num(val)
                registro[canon] = v
                if _clean(val) not in ('', '-'):
                    intentos[canon] += 1
                    if fallo:
                        fallos[canon] += 1
        registro['crudo'] = crudo
        datos.append(registro)

    # Guarda 6.3: anti-vacío (el del 28-jul vino así: cabecera y cero filas).
    if not datos:
        raise Aborta("[Guarda 6.3] 0 filas de datos bajo la cabecera: el export vino VACÍO. "
                     "Vuelve a generarlo en el Seller con el panel de la dimensión ASIN.")

    # Guarda 6.4: valores que no parsean → se CUENTAN; si alguna columna pasa del 5% de
    # fallos, se GRITA (señal de que Amazon cambió el formato). Hoy sale a cero.
    for canon in sorted(set(fallos) | set(intentos)):
        n_int = intentos[canon]
        n_fal = fallos[canon]
        if n_int and n_fal / n_int > 0.05:
            avisos.append(f"[Guarda 6.4] La columna {canon!r} tiene {n_fal}/{n_int} valores que "
                          f"NO parsean ({100*n_fal/n_int:.1f}%). ¿Cambió Amazon el formato? "
                          f"(Esos valores quedan NULL.)")
        elif n_fal:
            avisos.append(f"[valores no numéricos] {canon!r}: {n_fal}/{n_int} no parsean (NULL).")

    # --- Totales del fichero (suma de las 10 aditivas sobre las filas de datos) ---
    totales_fichero = {}
    for canon in COLS_ADITIVAS:
        if canon in canon_idx:
            totales_fichero[canon] = round(sum((r.get(canon) or 0) for r in datos), 2)

    # Guarda 6.7: cuadre contra la fila Total (§3.3). La firma de Amazon: si alguna aditiva
    # no cuadra al céntimo, se ha leído mal el fichero → ABORTA.
    if total_declarado is None:
        avisos.append("[Guarda 6.7] El fichero NO trae fila 'Total': no se ha podido hacer el "
                      "cuadre de control contra la suma. (Se carga igual; la firma de Amazon "
                      "falta.)")
    else:
        descuadres = []
        for canon in COLS_ADITIVAS:
            if canon not in canon_idx:
                continue
            ci = canon_idx[canon]
            declarado, _ = _num(total_declarado[ci] if ci < len(total_declarado) else None)
            declarado = round(declarado or 0, 2)
            calculado = totales_fichero.get(canon, 0)
            if abs(declarado - calculado) > 0.01:
                descuadres.append(f"{canon}: fila Total={declarado} vs suma={calculado} "
                                  f"(dif {round(declarado - calculado, 2)})")
        if descuadres:
            raise Aborta(
                "[Guarda 6.7] El cuadre contra la fila 'Total' de Amazon NO da. Se ha leído mal "
                "el fichero (columnas desplazadas, filas perdidas…). NO se carga:\n        · "
                + "\n        · ".join(descuadres))

    return {
        'datos': datos,
        'n_asin': len(datos),
        'totales_fichero': totales_fichero,
        'creator': creator,
        'exportado_at': exportado_at,
        'avisos': avisos,
        'columnas_ausentes': sorted(ausentes),
        'columnas_desconocidas': desconocidas,
    }


# ---------------------------------------------------------------------------
# 2) GUARDA 6.6 — EL PAÍS: cruzar la DEMANDA por ASIN con transacciones_movimientos.
#    El fichero no dice de qué marketplace es; el riesgo real es subir el de IT y
#    marcar ES. Se identifica por CUÁL de ES/IT/FR tiene menor error mediano.
#
#    🔴 SE COMPARAN CUOTAS, NO UNIDADES ABSOLUTAS (corrección de Fernando, 31-jul).
#    transacciones NO cubre la ventana declarada (acaba unos días antes; IT/FR
#    empiezan tarde), así que exigir cobertura total saltaba la guarda SIEMPRE en el
#    caso real. En su lugar se cruza sobre la INTERSECCIÓN de la ventana con lo que
#    cubre transacciones del país declarado, y se compara la CUOTA de cada ASIN
#    (uds_asin / total del conjunto): robusta al desfase de ventana. Medido con un
#    desfase del 15% — por cuotas el país correcto queda en 0,4-3,4% y el incorrecto
#    nunca baja del 74%; por absolutos el correcto subía a 14-15% y se confundía.
#    Se SALTA la guarda (y se dice) si: el fichero no trae 'Unidades pedidas', o la
#    intersección es < 40% de la ventana. NO caza una MEZCLA (esa la para el
#    procedimiento: un marketplace por fichero).
# ---------------------------------------------------------------------------
def _puente_sku_asin(cur):
    """SKU→ASIN: listings_amazon ∪ productos(es_chase=false). El chase nace SIN ASIN,
    así que ya queda fuera. Listings manda si un SKU apareciera en los dos."""
    sku2asin = {}
    cur.execute(
        "SELECT sku, asin FROM productos "
        " WHERE coalesce(es_chase,false)=false AND asin IS NOT NULL AND btrim(asin)<>'' "
        "   AND sku IS NOT NULL AND btrim(sku)<>''")
    for sku, asin in cur.fetchall():
        sku2asin[_bt(sku)] = _bt(asin)
    cur.execute(
        "SELECT seller_sku, asin FROM listings_amazon "
        " WHERE asin IS NOT NULL AND btrim(asin)<>'' "
        "   AND seller_sku IS NOT NULL AND btrim(seller_sku)<>''")
    for sku, asin in cur.fetchall():
        sku2asin[_bt(sku)] = _bt(asin)   # listings pisa a productos (fuente dura del ASIN)
    return sku2asin


def guarda_pais(cur, pais_declarado, desde, hasta, uds_fichero):
    """Devuelve (veredicto, detalle). veredicto ∈ {'ok','grita','salta'}; si el país
    declarado NO gana, lanza Aborta. `uds_fichero` = {asin: unidades_pedidas} del fichero.
    Compara CUOTAS (no unidades) sobre la INTERSECCIÓN de la ventana con lo que cubre
    transacciones del país declarado — robusto al desfase de ventana."""
    # 0) Sin 'Unidades pedidas' en el fichero (el panel puede no traerla: el export del
    #    28-jul tenía 8 columnas) → uds_fichero todo a cero: no hay con qué cruzar.
    total_fichero = sum(uds_fichero.values())
    if total_fichero <= 0:
        return ('salta', "el fichero no trae 'Unidades pedidas' (columna ausente o suman 0): "
                         "no hay con qué cruzar el país. Guarda SALTADA.")

    # 1) Intersección de la ventana declarada con lo que cubre transacciones del declarado.
    cur.execute("SELECT min(fecha), max(fecha) FROM transacciones_movimientos WHERE pais=%s;",
                (pais_declarado,))
    fmin, fmax = cur.fetchone()
    if fmin is None:
        return ('salta', f"transacciones no tiene datos de {pais_declarado}: no hay con qué "
                         f"cruzar. Guarda SALTADA.")
    ini, fin = max(desde, fmin), min(hasta, fmax)
    dias_ventana = (hasta - desde).days + 1
    dias_inter = (fin - ini).days + 1 if fin >= ini else 0
    if dias_inter < 0.40 * dias_ventana:
        return ('salta', f"transacciones de {pais_declarado} solo cruza {dias_inter} de los "
                         f"{dias_ventana} días de la ventana ({fmin}→{fmax} ∩ {desde}→{hasta}): "
                         f"menos del 40%, demasiado corta para fiarse. Guarda SALTADA.")

    sku2asin = _puente_sku_asin(cur)

    # 2) Unidades pedidas por (país, asin) sobre la INTERSECCIÓN, para TODOS los candidatos.
    cur.execute(
        "SELECT pais, sku, sum(cantidad)::numeric FROM transacciones_movimientos "
        " WHERE tipo_norm='pedido' AND fecha BETWEEN %s AND %s "
        "   AND cantidad IS NOT NULL AND sku IS NOT NULL "
        " GROUP BY pais, sku;", (ini, fin))
    trans = defaultdict(lambda: defaultdict(float))   # pais → asin → uds
    for p, sku, uds in cur.fetchall():
        asin = sku2asin.get(_bt(sku))
        if asin:
            trans[p][asin] += float(uds)

    # 3) CUOTAS: cuota de cada ASIN en el fichero (sobre la ventana) y en cada candidato
    #    (sobre la intersección). Comparar cuotas neutraliza que las ventanas no coincidan.
    cuota_fichero = {a: u / total_fichero for a, u in uds_fichero.items()}
    errores = {}
    for cand in PAISES_VALIDOS:
        total_cand = sum(trans[cand].values())
        if total_cand <= 0:
            errores[cand] = None
            continue
        # Los 12 ASIN de más unidades del candidato; error relativo de su CUOTA vs el fichero.
        top = sorted(trans[cand].items(), key=lambda kv: kv[1], reverse=True)[:12]
        errs = []
        for asin, tu in top:
            if tu <= 0:                       # no dividir por cero (medido: qty mín = 1)
                continue
            ts = tu / total_cand
            errs.append(abs(cuota_fichero.get(asin, 0.0) - ts) / ts)
        errores[cand] = median(errs) if errs else None

    tabla = " · ".join(
        f"{c}={'s/d' if errores[c] is None else format(100*errores[c], '.1f')+'%'}"
        for c in PAISES_VALIDOS)

    if errores.get(pais_declarado) is None:
        return ('salta', f"no hay unidades cruzables para {pais_declarado} en la intersección "
                         f"(cuota por país: {tabla}). Guarda SALTADA.")

    ganador = min((c for c in PAISES_VALIDOS if errores[c] is not None), key=lambda c: errores[c])
    if ganador != pais_declarado:
        raise Aborta(
            f"[Guarda 6.6 · PAÍS] Se declaró {pais_declarado} pero el fichero cuadra con "
            f"{ganador}. Error mediano de CUOTA vs transacciones [{ini}→{fin}]: {tabla}. "
            f"O el selector de país va equivocado o subiste el fichero de otro marketplace. "
            f"NO se carga.")

    if errores[pais_declarado] > 0.25:
        return ('grita',
                f"{pais_declarado} GANA (cuota por país: {tabla}) pero su error pasa del 25%: "
                f"puede ser la VENTANA mal declarada. Revísala. (Entra igual.)")
    return ('ok', f"{pais_declarado} identificado por CUOTA (error mediano: {tabla}; "
                  f"intersección {ini}→{fin} = {dias_inter}/{dias_ventana} días).")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== PROCESADOR CUSTOM ANALYTICS (DEMANDA · FOTO POR VENTANA) ===", flush=True)
    print(f"MODO: {MODO}  ·  ENTORNO: {ENTORNO}  ·  PAIS: {PAIS or '(sin selector)'}  ·  "
          f"periodo: {PERIODO_DESDE or '?'} → {PERIODO_HASTA or '?'}", flush=True)
    print("=" * 60, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if PAIS not in PAISES_VALIDOS:
        sys.exit(f"PAIS desconocido: {PAIS!r}. El país lo manda el selector (ES/IT/FR) y NO "
                 f"se asume: sin país no se carga (§3.5).")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Guarda 6.5: el periodo (lo declara el selector; sin él se ABORTA) ---
    if not PERIODO_DESDE or not PERIODO_HASTA:
        sys.exit("[Guarda 6.5] Falta PERIODO_DESDE y/o PERIODO_HASTA. El fichero no trae el "
                 "periodo: lo declara quien sube (YYYY-MM-DD). Sin periodo no se carga (§3.5).")
    try:
        desde = _fecha_iso(PERIODO_DESDE, 'PERIODO_DESDE')
        hasta = _fecha_iso(PERIODO_HASTA, 'PERIODO_HASTA')
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)
    if desde > hasta:
        sys.exit(f"[Guarda 6.5] PERIODO_DESDE ({desde}) es posterior a PERIODO_HASTA ({hasta}).")
    if (hasta - desde).days + 1 > VENTANA_MAX_DIAS:
        sys.exit(f"[Guarda 6.5] La ventana {desde}→{hasta} son {(hasta-desde).days+1} días "
                 f"(> {VENTANA_MAX_DIAS}). Huele a error de tecleo. Revísala.")
    if hasta > date.today():
        sys.exit(f"[Guarda 6.5] PERIODO_HASTA ({hasta}) es futuro (hoy {date.today()}). "
                 f"No se declara una ventana que aún no ha terminado.")

    # --- Bajar el fichero del buzón (Storage de PRODUCCIÓN) ---
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)
    xlsxs = [o for o in objs if (o.get('name') or '').lower().endswith('.xlsx')]
    if not xlsxs:
        sys.exit(f"No hay ningún .xlsx en {BUCKET}/{CARPETA}/. Sube el export de Custom "
                 f"Analytics de {PAIS} y relanza.")
    xlsxs.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)

    # Con ES/IT/FR en la misma carpeta "el más reciente" es una lotería: aquí pedir el
    # nombre EXACTO es lo NORMAL. Si se pide y no está → ABORTA (no cae al más reciente).
    if FICHERO:
        nombres = [o['name'] for o in xlsxs]
        if FICHERO not in nombres:
            print(f"\n❌ ABORTA (no se ha escrito nada):\n"
                  f"[Guarda fichero] Se pidió {FICHERO!r} y no está en {BUCKET}/{CARPETA}/.\n"
                  f"   Hay {len(nombres)} .xlsx en el buzón: {nombres}\n"
                  f"   No se cae al más reciente: cargaría un país/periodo distinto.", flush=True)
            sys.exit(1)
        fichero = FICHERO
        print(f"Fichero elegido (pedido a dedo): {fichero}", flush=True)
    else:
        fichero = xlsxs[0]['name']
        print(f"Fichero elegido (el más reciente de {len(xlsxs)}): {fichero}", flush=True)

    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")

    # --- Parseo + guardas estructurales (antes de tocar la base) ---
    try:
        info = analizar(crudo_bytes, PAIS, desde, hasta, fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    datos = info['datos']
    exportado_at = info['exportado_at']
    print(f"\nASIN leídos: {info['n_asin']}  ·  país {PAIS}  ·  ventana {desde}→{hasta}  "
          f"({(hasta-desde).days+1} días)", flush=True)
    print(f"   exportado_at (properties.created): {exportado_at}", flush=True)
    print(f"   totales del fichero: " + " · ".join(
        f"{k}={v}" for k, v in info['totales_fichero'].items()), flush=True)
    for a in info['avisos']:
        print(f"⚠️  {a}", flush=True)

    # Guarda 6.5 (cont.): la ventana no puede acabar DESPUÉS de cuándo se exportó.
    if isinstance(exportado_at, datetime) and hasta > exportado_at.date():
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 6.5] PERIODO_HASTA ({hasta}) es posterior a cuándo se exportó el "
              f"fichero ({exportado_at.date()}). El fichero no puede cubrir una ventana que "
              f"aún no había pasado cuando se generó.", flush=True)
        sys.exit(1)

    # --- Conectar al ENTORNO ---
    con = psycopg2.connect(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # Guarda 6.13: la tabla tiene que EXISTIR y estar CERRADA (RLS). NO se crea ni se
    # activa aquí (huevo y gallina §10): la crea la migración 2026-07-31_demanda_asin.sql.
    cur.execute("SELECT to_regclass('public.demanda_asin');")
    if cur.fetchone()[0] is None:
        print("\n❌ ABORTA: la tabla demanda_asin NO existe. La crea la migración "
              "2026-07-31_demanda_asin.sql (huevo y gallina §10): aplícala por la escalera y "
              "relanza. El procesador NO crea tablas nuevas.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.demanda_asin'::regclass;")
    if not cur.fetchone()[0]:
        print("\n❌ ABORTA: RLS no está activa en demanda_asin. La activa la migración "
              "(regla del 29-jul: el procesador no toca la seguridad en cada carga). "
              "Aplica la migración y relanza.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Guarda 6.6: EL PAÍS ---
    uds_fichero = {r['asin']: (r.get('unidades_pedidas') or 0) for r in datos}
    try:
        veredicto, detalle = guarda_pais(cur, PAIS, desde, hasta, uds_fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)
    marca = {'ok': '✅', 'grita': '⚠️', 'salta': '⏭️'}[veredicto]
    print(f"\n{marca} [Guarda 6.6 · país] {detalle}", flush=True)

    # --- Guarda 6.9: ASIN huérfanos (cuenta, no aborta) ---
    cur.execute("SELECT btrim(asin) FROM productos "
                " WHERE coalesce(es_chase,false)=false AND asin IS NOT NULL AND btrim(asin)<>'';")
    asin_prod = {r[0] for r in cur.fetchall()}
    huerfanos = [r['asin'] for r in datos if r['asin'] not in asin_prod]
    print(f"   ASIN huérfanos (no en productos, no chase): {len(huerfanos)} de {len(datos)} "
          f"(normal: ASIN que ya no listas o de otro vendedor en la misma ficha).", flush=True)

    # --- Guarda 6.11: país nuevo (radar fiscal; no aborta) ---
    cur.execute("SELECT DISTINCT pais FROM demanda_asin;")
    paises_bd = {r[0] for r in cur.fetchall()}
    if not paises_bd:
        print(f"\n1ª carga (tabla vacía): país inicial → {PAIS}", flush=True)
    elif PAIS not in paises_bd:
        print(f"\n🆕 PAÍS NUEVO en demanda_asin: {PAIS}. Posible NUEVA OBLIGACIÓN DE IVA — "
              f"revisar. (Entra igual.)", flush=True)

    # --- Guarda 6.8: solapamiento de ventanas del mismo país (grita, no borra) ---
    cur.execute(
        "SELECT periodo_desde, periodo_hasta, dias, count(*), coalesce(sum(unidades_pedidas),0) "
        "  FROM demanda_asin "
        " WHERE pais=%s AND NOT (periodo_desde=%s AND periodo_hasta=%s) "
        "   AND periodo_desde <= %s AND periodo_hasta >= %s "
        " GROUP BY periodo_desde, periodo_hasta, dias "
        " ORDER BY periodo_hasta DESC;", (PAIS, desde, hasta, hasta, desde))
    solapes = cur.fetchall()
    if solapes:
        total_nuevo = int(info['totales_fichero'].get('unidades_pedidas', 0))
        print(f"\n⚠️  [Guarda 6.8] La ventana {desde}→{hasta} SOLAPA con otras de {PAIS} ya "
              f"presentes (no se borran; conviven):", flush=True)
        for pd, ph, dd, n, su in solapes:
            inter = (min(ph, hasta) - max(pd, desde)).days + 1
            menor = min((ph - pd).days + 1, (hasta - desde).days + 1)
            pct = 100 * inter / menor if menor else 0
            aviso_extra = ""
            if pct > 90 and int(su) == total_nuevo:
                aviso_extra = ("  🔴 solapa >90% y el total de unidades COINCIDE: "
                               "¿te has equivocado al escribir el periodo?")
            print(f"        · {pd}→{ph} ({dd} días): {n} filas, {int(su)} uds pedidas."
                  f"{aviso_extra}", flush=True)

    # --- Guarda 6.10: anti-encogimiento POR VENTANA ---
    cur.execute("SELECT count(*) FROM demanda_asin "
                " WHERE pais=%s AND periodo_desde=%s AND periodo_hasta=%s;", (PAIS, desde, hasta))
    previas = cur.fetchone()[0]
    if previas and len(datos) < previas * 0.5:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n"
              f"[Guarda 6.10] En {PAIS} [{desde}→{hasta}] ya había {previas} filas y el fichero "
              f"trae {len(datos)}: menos del 50%. Un informe a medias no da información "
              f"incompleta, da información FALSA. No se borra ni se escribe nada.", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # --- Carga FOTO POR VENTANA: DELETE por IGUALDAD + INSERT (misma transacción) ---
    cur.execute("DELETE FROM demanda_asin "
                " WHERE pais=%s AND periodo_desde=%s AND periodo_hasta=%s;", (PAIS, desde, hasta))
    borradas = cur.rowcount

    plantilla = "(" + ", ".join(['%s'] * len(COLS_DB)) + ")"
    valores = [[(Json(r['crudo']) if c == 'crudo' else r.get(c)) for c in COLS_DB] for r in datos]
    execute_values(cur, f"INSERT INTO demanda_asin ({', '.join(COLS_DB)}) VALUES %s",
                   valores, template=plantilla, page_size=1000)
    insertadas = len(valores)

    # --- SELLO DE FRESCURA en informes_subidos (los 10 totales del cuadre) ---
    resumen = {
        'pais': PAIS, 'tipo': 'custom_analytics', 'archivo': fichero,
        'periodo_desde': desde.isoformat(), 'periodo_hasta': hasta.isoformat(),
        'dias': (hasta - desde).days + 1,
        'asin': len(datos), 'huerfanos': len(huerfanos),
        'totales': info['totales_fichero'],
        'exportado_at': exportado_at.isoformat() if isinstance(exportado_at, datetime) else None,
        'guarda_pais': detalle, 'columnas_ausentes': info['columnas_ausentes'],
        'columnas_desconocidas': [str(c) for c in info['columnas_desconocidas']],
        'avisos': info['avisos'],
        'fuente': 'procesador_custom_analytics (Fase 0)',
    }
    cur.execute(
        "INSERT INTO informes_subidos "
        "(tipo, archivo_nombre, filas_procesadas, filas_validas, filas_descartadas, "
        " fecha_dato_desde, fecha_dato_hasta, resumen_json, procesado_at, notas) "
        "VALUES ('custom_analytics', %s, %s, %s, 0, %s, %s, %s, now(), %s);",
        (fichero, len(datos), insertadas, desde, hasta, Json(resumen),
         f'procesador_custom_analytics Fase 0 · {PAIS} · {desde}→{hasta}'))

    # --- Resumen ---
    verbo = 'se han' if MODO == 'aplicar' else 'se habrían'
    print(f"\n--- DEMANDA {PAIS} [{desde}→{hasta}] (FOTO POR VENTANA) ---")
    print(f"   · ASIN del fichero:            {len(datos)}")
    print(f"   · ya había en esa ventana:     {previas}")
    print(f"   · BORRADOS de la ventana ({verbo}): {borradas}")
    print(f"   · INSERTADOS ({verbo}):        {insertadas}")
    print(f"   · otras ventanas y países:     intactos (borrado por IGUALDAD, no BETWEEN)")
    print(f"   · sello en informes_subidos ({verbo}): 1 fila (tipo='custom_analytics')")

    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: {insertadas} filas de {PAIS} [{desde}→{hasta}] en "
              f"demanda_asin (ventana recerrada por igualdad; RLS activo sin políticas; sello "
              f"escrito).")
    else:
        con.rollback()
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. (El borrado por "
              f"ventana, el volcado y el sello se han probado dentro de una transacción revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · pais={PAIS} · "
          f"ventana={desde}→{hasta} · asin={len(datos)} · borrados={borradas} · "
          f"insertados={insertadas} · huerfanos={len(huerfanos)} ===", flush=True)


if __name__ == '__main__':
    main()
