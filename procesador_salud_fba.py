# -*- coding: utf-8 -*-
# ============================================================================
# PROCESADOR SALUD_FBA — Pieza 2 de la Fase 0 de la v2
# ----------------------------------------------------------------------------
# Qué hace:
#   Lee el informe SALUD_FBA (MANAGE_INVENTORY_HEALTH) del buzón
#   informes/salud_fba/ (Supabase Storage de PRODUCCIÓN) y lo vuelca a la
#   tabla `salud_fba`, que es una FOTO de Amazon (no un trozo del inventario
#   de Moloka).
#
#   - Guarda lo que Amazon declara, TAL CUAL llega.
#   - NO escribe en `productos`. NO escribe en ninguna tabla de la v1.
#     Cero UPDATE fuera de `salud_fba` y de su histórico.
#
#   Además APILA una copia fechada y LEAN en `salud_fba_historico` (PELÍCULA,
#   §1.6): la foto viva no cambia ni un byte por ello. Ver el bloque HISTORICO.
#   - El cruce con las fichas de Moloka vive en la VISTA de solo lectura
#     v_salud_fba_cruce (§5). La conciliación es otro asiento, no este.
#
# LA CLAVE es (asin, marketplace), NO el SKU (ese fue el error de la v1).
#   - PK (asin, marketplace). Cada pasada deja SOLO la última foto.
#   - Idempotente: correr dos veces el mismo fichero deja el mismo resultado.
#   - 🔒 ES UNA FOTO, NO UN COLLAGE (patrón común en foto_comun.py): los
#     (asin, marketplace) que ya no vienen en el informe se BORRAN. Es la
#     decisión que faltaba sobre las filas fantasma (medido: 195→188 SKU en dos
#     días dejaba 7 filas viejas conviviendo con las nuevas). El borrado va
#     acotado a los marketplaces del informe y en la MISMA transacción que la
#     carga: o todo o nada.
#
# Precedente a imitar: procesador_all_listings.py (ya en producción).
# Mismo estilo, misma escalera (ENTORNO staging|produccion, MODO ensayo|aplicar),
# misma disciplina de guardas.
#
# Principio de la despensa (Diseño §3.5): si el informe entra, TODAS sus
# columnas quedan disponibles. Las que tienen comensal se tipan; la fila
# entera (92 columnas) se guarda además en `crudo jsonb`. Nada se tira.
# ============================================================================

import os, sys, io, csv, json
from datetime import date, datetime

import psycopg2
from psycopg2.extras import Json, execute_values
from supabase import create_client

# El patrón de carga de FOTO, común a las cuatro cañerías de la Fase 0.
from foto_comun import (Aborta, conectar_bd, listar_buzon, descargar_buzon, guarda_anti_encogimiento, guarda_no_retroceder, claves_previas,
                        barrer_sobrantes, resumen_foto, describir_ambito)

# ---------------------------------------------------------------------------
# 0) Configuración (secrets de GitHub; jamás credenciales en el código)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')   # llave de servicio: LEER el Storage cerrado
DB_URL       = os.environ.get('DB_URL', '')         # postgres del ENTORNO (staging o prod)
MODO         = os.environ.get('MODO', 'ensayo').strip().lower()       # ensayo | aplicar
ENTORNO      = os.environ.get('ENTORNO', 'staging').strip().lower()   # staging | produccion

# FICHERO (opcional): nombre EXACTO del .txt del buzón que se quiere procesar.
# Vacío = el más reciente (comportamiento de siempre). Igual que en keepa: existe
# para poder recargar un informe concreto (p. ej. el original de las dos guillotinas
# salud_fba/50497020659.txt) sin depender de cuál es el más reciente del buzón.
# 🔒 Si se pide un nombre que no está en el buzón se ABORTA: JAMÁS se cae al más
#    reciente de reserva. Cargar en silencio un informe distinto del que pediste es
#    exactamente el error que este parámetro viene a evitar.
FICHERO      = os.environ.get('FICHERO', '').strip()

BUCKET, CARPETA = 'informes', 'salud_fba'

# ---------------------------------------------------------------------------
# Columnas OBLIGATORIAS: si falta el encabezado de alguna → ABORTA (Guarda 1).
# (Amazon renombra columnas: mejor parar que adivinar.) Nombre humano tal cual
# aparece en el informe; la comprobación es tolerante a mayúsculas/espacios.
# ---------------------------------------------------------------------------
OBLIGATORIAS = [
    'snapshot-date', 'sku', 'fnsku', 'asin', 'marketplace',
    'available', 'fc-transfer', 'Total Reserved Quantity',
    'inbound-quantity', 'Inventory Supply at FBA',
]

# Columnas necesarias para las ecuaciones de cuadre (Guardas 4 y 5) que no
# están en la lista obligatoria. Si faltan, tampoco se puede comprobar → ABORTA.
SOPORTE_ECUACIONES = [
    'Reserved FC Processing', 'Reserved Customer Order', 'Reserved Staging',
    'inbound-working', 'inbound-shipped', 'inbound-received',
]

# ---------------------------------------------------------------------------
# Columnas TIPADAS (las que ya tienen comensal). (db_col, tipo).
#   tipo: 't' text · 'i' integer · 'n' numeric.
# El encabezado de origen se localiza normalizando: db_col con '_'→'-' casa
# con 'Total Reserved Quantity', 'fc-transfer', 'Inventory Supply at FBA', etc.
# Cuando el snake_case NO se deduce del encabezado real (Amazon abrevia, o pone
# paréntesis o signos de interrogación), el encabezado LITERAL va en ALIAS.
# 🔒 Regla de Fernando (15-jul): NO hay cabos sueltos. Si un encabezado tipado
# no casa, NUNCA se guarda NULL en silencio: se ABORTA (Guarda 10). Un NULL
# calladito haría creer al módulo consumidor que Amazon no da el dato; que el
# valor siga en `crudo` no consuela a quien lee la columna tipada.
# ---------------------------------------------------------------------------
TIPADAS = [
    # Identidad
    ('sku', 't'), ('fnsku', 't'), ('asin', 't'), ('product_name', 't'),
    ('condition', 't'), ('marketplace', 't'),
    # Stock → maestro
    ('available', 'i'), ('fc_transfer', 'i'), ('total_reserved_quantity', 'i'),
    ('reserved_fc_processing', 'i'), ('reserved_customer_order', 'i'),
    ('reserved_staging', 'i'), ('inbound_quantity', 'i'), ('inbound_working', 'i'),
    ('inbound_shipped', 'i'), ('inbound_received', 'i'), ('unfulfillable_quantity', 'i'),
    ('pending_removal_quantity', 'i'), ('inventory_supply_at_fba', 'i'),
    # Cobertura → alertas
    ('days_of_supply', 'n'), ('total_days_of_supply_incl_open_shipments', 'n'),
    ('weeks_of_cover_t30', 'n'), ('weeks_of_cover_t90', 'n'), ('sell_through', 'n'),
    ('units_shipped_t7', 'i'), ('units_shipped_t30', 'i'), ('units_shipped_t60', 'i'),
    ('units_shipped_t90', 'i'), ('historical_days_of_supply', 'n'),
    # Reposición (2ª opinión de Amazon) → capa 5
    ('recommended_action', 't'), ('recommended_ship_in_quantity', 'i'),
    ('recommended_ship_in_date', 't'), ('healthy_inventory_level', 'n'), ('alert', 't'),
    # Exceso → capa 4
    ('estimated_excess_quantity', 'i'), ('recommended_removal_quantity', 'i'),
    ('estimated_cost_savings_of_recommended_actions', 'n'),
    # LIL → alertas
    ('fba_minimum_inventory_level', 'i'), ('fba_inventory_level_health_status', 't'),
    ('low_inventory_fee_applied_current_week', 't'), ('exempted_from_low_inventory_fee', 't'),
    # Coste / antigüedad → costes
    ('estimated_storage_cost_next_month', 'n'), ('storage_type', 't'),
    ('storage_volume', 'n'), ('item_volume', 'n'), ('inventory_age_snapshot_date', 't'),
    # Competencia → la consume el trackeador desde SU proyecto
    ('featuredoffer_price', 'n'), ('lowest_price_new_plus_shipping', 'n'),
    ('your_price', 'n'), ('sales_price', 'n'), ('sales_rank', 'i'),
    # Estacionalidad → capa 3
    ('is_seasonal_in_next_3_months', 't'), ('season_name', 't'),
    ('season_start_date', 't'), ('season_end_date', 't'),
]
TIPO_SQL = {'t': 'text', 'i': 'integer', 'n': 'numeric'}

# ---------------------------------------------------------------------------
# ALIAS: encabezado LITERAL del informe para las columnas tipadas cuyo nombre
# snake_case se abrevió respecto al real (medido el 16-jul contra el fichero
# real). La resolución es: alias si existe → si no, la regla '_'→'-'.
# La comparación es tolerante (norm(): minúsculas, espacios/'_'→'-'), así que
# el literal se escribe tal cual aparece en la cabecera de Amazon.
# ⚠️ 'Total Days of Supply (...)' es la métrica de cobertura marcada 🟢 en el
# Diseño §14.9: no es decorativa.
# ---------------------------------------------------------------------------
ALIAS = {
    'total_days_of_supply_incl_open_shipments':
        'Total Days of Supply (including units from open shipments)',
    'low_inventory_fee_applied_current_week':
        'Low-Inventory cost coverage fee applied in current week?',
    'exempted_from_low_inventory_fee':
        'Exempted from Low-Inventory cost coverage fee?',
}

# ---------------------------------------------------------------------------
# EL HISTÓRICO — la PELÍCULA que la Foto no puede guardar (§1.6)
# ---------------------------------------------------------------------------
# `salud_fba` es una FOTO: cada pasada tira la hoja vieja, y con ella la única
# copia que había del dato de ayer. Eso está bien (una foto contesta "¿cómo está
# esto AHORA?"), pero deja sin contestar la otra pregunta: ¿el stock BAJA?, ¿la
# cobertura se hunde?, ¿el rank se está muriendo? Para eso hay que apilar.
#
# `salud_fba_historico` es PELÍCULA, no Foto. Reglas, y no se reinterpretan:
#   · Se APILA y NUNCA se borra. Aquí no entra `barrer_sobrantes` ni nada que
#     se le parezca: borrar una línea de una Película es falsificar el extracto.
#   · PK (asin, marketplace, snapshot_date) → un asiento por producto y día.
#   · Solo se apilan las filas DEL FICHERO. Las que la salvaguarda anti-omisión
#     protege en la foto viva (ausentes del informe pero con stock) NO se
#     apilan: ese día Amazon no dijo nada de ellas, y un histórico que rellena
#     el hueco con el dato de ayer fechado hoy MIENTE.
#   · LEAN: solo las columnas que dibujan una curva. NADA de `crudo jsonb`
#     (92 columnas × N días engordan la base sin añadir tendencia). La despensa
#     completa del día de hoy sigue entera en `salud_fba.crudo`.
#   · Idempotente: reprocesar el mismo fichero REESCRIBE la fila de ese día; ni
#     la duplica ni inventa un día nuevo.
#
# 🔒 NO toca la foto viva. Se escribe DESPUÉS del upsert de `salud_fba` y en la
# MISMA transacción: si algo revienta, no queda ni foto ni histórico.
# El tipo de cada columna se HEREDA de TIPADAS: el histórico no puede guardar un
# `numeric` donde la foto guarda un `integer`.
# ---------------------------------------------------------------------------
HISTORICO = [
    # (El SKU ya NO vive aquí: con el grano Dos Vidas entra en la PK del histórico,
    #  declarado aparte como asin/marketplace/snapshot_date.)
    # Stock
    'available', 'fc_transfer', 'total_reserved_quantity', 'inbound_quantity',
    'unfulfillable_quantity', 'pending_removal_quantity', 'inventory_supply_at_fba',
    # Cobertura
    'days_of_supply', 'total_days_of_supply_incl_open_shipments',
    'weeks_of_cover_t30', 'weeks_of_cover_t90', 'sell_through',
    'historical_days_of_supply',
    # Salida (la curva de ventas)
    'units_shipped_t7', 'units_shipped_t30', 'units_shipped_t60', 'units_shipped_t90',
    # Exceso y alerta
    'estimated_excess_quantity', 'recommended_removal_quantity', 'alert',
    # LIL (nivel mínimo de inventario)
    'fba_minimum_inventory_level', 'fba_inventory_level_health_status',
    # Coste de almacenamiento REAL. El 'estimated cost savings' NO entra: es
    # marketing (§1.5), y apilar marketing durante meses no lo vuelve un dato.
    'estimated_storage_cost_next_month',
    # Mercado / competencia
    'featuredoffer_price', 'lowest_price_new_plus_shipping', 'your_price',
    'sales_price', 'sales_rank',
]

_TIPO_DE = dict(TIPADAS)
_SUELTAS = [c for c in HISTORICO if c not in _TIPO_DE]
if _SUELTAS:
    raise RuntimeError(
        "[HISTORICO] Columnas que no existen en TIPADAS: " + ", ".join(_SUELTAS)
        + ". El histórico HEREDA el tipo de la foto; una columna suelta guardaría "
          "un tipo distinto al de salud_fba o un KeyError en runtime.")
if any(c in HISTORICO for c in ('asin', 'marketplace', 'sku', 'snapshot_date')):
    raise RuntimeError("[HISTORICO] asin/marketplace/sku/snapshot_date son la PK y se "
                       "declaran aparte: no pueden repetirse en HISTORICO.")


# Aborta vive ahora en foto_comun (misma clase para las cuatro cañerías): una
# guarda que aborta se imprime, NO escribe nada y el workflow sale en rojo.


# ---------------------------------------------------------------------------
# Helpers de normalización y parseo
# ---------------------------------------------------------------------------
def norm(s):
    """Clave canónica de encabezado: sin BOM, minúsculas, espacios/guion_bajo → '-'."""
    return (s or '').replace('﻿', '').strip().lower().replace(' ', '-').replace('_', '-')

def clave(db_col):
    return db_col.replace('_', '-')

def txt(v):
    v = ('' if v is None else str(v)).strip()
    return v or None

def ent(v):
    v = ('' if v is None else str(v)).strip()
    if v == '':
        return None
    try:
        return int(round(float(v)))
    except ValueError:
        return None   # el crudo conserva el valor original; la despensa no pierde

def dec(v):
    v = ('' if v is None else str(v)).strip()
    if v == '':
        return None
    try:
        return float(v)
    except ValueError:
        return None

def parse_val(tipo, raw):
    return txt(raw) if tipo == 't' else ent(raw) if tipo == 'i' else dec(raw)


# ---------------------------------------------------------------------------
# 1) Parseo + guardas estructurales (1..8). Sin tocar la base todavía.
#    Devuelve la lista de filas ya tipadas + su `crudo`, o lanza Aborta.
# ---------------------------------------------------------------------------
def analizar(texto, fichero):
    lector = csv.reader(io.StringIO(texto), delimiter='\t')
    filas = [f for f in lector if any((c or '').strip() for c in f)]

    # Guarda 8: anti-vacío
    if len(filas) < 2:
        raise Aborta("[Guarda 8] 0 filas de datos (fichero vacío o no es TSV). Abortando.")

    cabecera = [(c or '').strip() for c in filas[0]]
    cab_norm = [norm(c) for c in cabecera]
    idx_por_norm = {}
    for i, cn in enumerate(cab_norm):
        idx_por_norm.setdefault(cn, i)   # primera aparición

    # Guarda 1: columnas obligatorias presentes
    faltan = [c for c in OBLIGATORIAS if norm(c) not in idx_por_norm]
    if faltan:
        raise Aborta("[Guarda 1] Faltan columnas obligatorias en el informe: "
                     + ", ".join(faltan) + f". Cabecera vista: {cabecera[:12]}...")

    # Soporte de ecuaciones presente (habilita Guardas 4 y 5)
    faltan_eq = [c for c in SOPORTE_ECUACIONES if norm(c) not in idx_por_norm]
    if faltan_eq:
        raise Aborta("[Guarda 1] Faltan columnas necesarias para las comprobaciones "
                     "de cuadre (§4.4/§4.5): " + ", ".join(faltan_eq) + ".")

    # Guarda 10: TODA columna tipada resuelve su encabezado en la cabecera, o
    # ABORTA. Mata la clase entera de fallo "columna tipada que se guarda NULL
    # en silencio porque Amazon renombró el encabezado". Comprueba que el
    # ENCABEZADO exista, no que traiga valor: las columnas de estacionalidad
    # existen aunque vengan vacías (0/195), así que NO hacen abortar.
    col_a_norm = {}
    no_resuelven = []
    for db_col, _ in TIPADAS:
        k = norm(ALIAS[db_col]) if db_col in ALIAS else norm(db_col)
        if k in idx_por_norm:
            col_a_norm[db_col] = k
        else:
            no_resuelven.append(f"{db_col} (buscaba encabezado: "
                                f"{ALIAS.get(db_col, clave(db_col))!r})")
    if no_resuelven:
        raise Aborta("[Guarda 10] Columnas tipadas cuyo encabezado NO aparece en el "
                     "informe (Amazon lo renombró; se ABORTA en vez de guardar NULL "
                     "en silencio):\n   · " + "\n   · ".join(no_resuelven)
                     + f"\n   Cabecera real vista ({len(cabecera)} cols): {cabecera}")

    def celda_norm(fila, cn):
        i = idx_por_norm.get(cn)
        if i is None or i >= len(fila):
            return ''
        return (fila[i] or '').strip()

    def eq_int(fila, db_col, num_fila, humano):
        raw = celda_norm(fila, col_a_norm[db_col])
        if raw == '':
            raise Aborta(f"[Guarda 4/5/6] Fila {num_fila}: '{humano}' vacía; no se puede cuadrar.")
        try:
            return int(round(float(raw)))
        except ValueError:
            raise Aborta(f"[Guarda 4/5/6] Fila {num_fila}: valor no numérico en '{humano}' ({raw!r}).")

    filas_datos = filas[1:]
    snapshots = set()
    claves_vistas = {}
    duplicadas = []
    salida = []

    for pos, fila in enumerate(filas_datos):
        num_fila = pos + 2   # +1 por cabecera, +1 para numerar desde 1

        asin_v = celda_norm(fila, 'asin')
        sku_v  = celda_norm(fila, 'sku')
        mk_v   = celda_norm(fila, 'marketplace')

        # Guarda 3: asin o sku vacío
        if asin_v == '' or sku_v == '':
            cual = 'asin' if asin_v == '' else 'sku'
            raise Aborta(f"[Guarda 3] Fila {num_fila}: '{cual}' vacío. Abortando.")

        snapshots.add(celda_norm(fila, 'snapshot-date'))

        # Guarda 2: trío (asin, marketplace, sku) duplicado (se recopilan todos).
        # 🔴 El SKU entra en la clave: un mismo ASIN con dos SKU vivos en el mismo
        # país (dos vidas) ya NO es un duplicado — es lo normal desde que Amazon
        # obliga a etiquetar. Solo un trío repetido de verdad sería informe corrupto.
        k = (asin_v.upper(), mk_v.upper(), sku_v.upper())
        if k in claves_vistas:
            duplicadas.append(f"({asin_v}, {mk_v}, {sku_v}) — filas {claves_vistas[k]} y {num_fila}")
        else:
            claves_vistas[k] = num_fila

        # Guardas 4, 5, 6: ecuaciones internas (verificadas fila a fila)
        trq = eq_int(fila, 'total_reserved_quantity', num_fila, 'Total Reserved Quantity')
        rfp = eq_int(fila, 'reserved_fc_processing', num_fila, 'Reserved FC Processing')
        rco = eq_int(fila, 'reserved_customer_order', num_fila, 'Reserved Customer Order')
        rst = eq_int(fila, 'reserved_staging', num_fila, 'Reserved Staging')
        if trq != rfp + rco + rst:
            raise Aborta(f"[Guarda 4] Fila {num_fila} (asin {asin_v}): Total Reserved "
                         f"Quantity ({trq}) ≠ FC Processing+Customer Order+Staging "
                         f"({rfp}+{rco}+{rst}={rfp+rco+rst}).")

        iq = eq_int(fila, 'inbound_quantity', num_fila, 'inbound-quantity')
        iw = eq_int(fila, 'inbound_working', num_fila, 'inbound-working')
        ish = eq_int(fila, 'inbound_shipped', num_fila, 'inbound-shipped')
        ir = eq_int(fila, 'inbound_received', num_fila, 'inbound-received')
        if iq != iw + ish + ir:
            raise Aborta(f"[Guarda 5] Fila {num_fila} (asin {asin_v}): inbound-quantity "
                         f"({iq}) ≠ working+shipped+received ({iw}+{ish}+{ir}={iw+ish+ir}).")

        av = eq_int(fila, 'available', num_fila, 'available')
        fct = eq_int(fila, 'fc_transfer', num_fila, 'fc-transfer')
        isf = eq_int(fila, 'inventory_supply_at_fba', num_fila, 'Inventory Supply at FBA')
        # ⚠️ NO incluye el reservado (comprobado fila a fila). No "corregir".
        if isf != av + fct + iq:
            raise Aborta(f"[Guarda 6] Fila {num_fila} (asin {asin_v}): Inventory Supply "
                         f"at FBA ({isf}) ≠ available+fc-transfer+inbound-quantity "
                         f"({av}+{fct}+{iq}={av+fct+iq}).")

        # Fila tipada (encabezado resuelto vía col_a_norm) + crudo (fila entera)
        registro = {}
        for db_col, tipo in TIPADAS:
            registro[db_col] = parse_val(tipo, celda_norm(fila, col_a_norm[db_col]))
        crudo = {}
        for i, h in enumerate(cabecera):
            crudo[h] = (fila[i].strip() if i < len(fila) and fila[i] is not None else '')

        salida.append({
            'asin': asin_v, 'marketplace': mk_v, 'sku': sku_v,
            'registro': registro, 'crudo': crudo,
        })

    # Guarda 2 (informe final si hubo duplicados)
    if duplicadas:
        raise Aborta("[Guarda 2] Tríos (asin, marketplace, sku) duplicados (el procesador "
                     "NO elige; esto sí sería un informe corrupto):\n   · " + "\n   · ".join(duplicadas))

    # Guarda 7: más de una snapshot-date distinta
    snapshots = {s for s in snapshots if s}
    if len(snapshots) > 1:
        raise Aborta(f"[Guarda 7] Más de una snapshot-date en el fichero: {sorted(snapshots)}.")
    if not snapshots:
        raise Aborta("[Guarda 7] Ninguna snapshot-date en las filas. Abortando.")

    snap_txt = next(iter(snapshots))
    try:
        snap = date.fromisoformat(snap_txt)
    except ValueError:
        raise Aborta(f"[Guarda 7] snapshot-date no es una fecha ISO válida: {snap_txt!r}.")

    return {'filas': salida, 'snapshot': snap, 'fichero': fichero}


# ---------------------------------------------------------------------------
# DDL: la tabla nace CERRADA (RLS on, cero políticas) y la vista de cruce
# ---------------------------------------------------------------------------
def sql_crear_tabla():
    cols = ",\n    ".join(f"{c} {TIPO_SQL[t]}" for c, t in TIPADAS)
    return f"""
    CREATE TABLE IF NOT EXISTS salud_fba (
        {cols},
        snapshot_date  date,
        fichero        text,
        crudo          jsonb,
        procesado_en   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asin, marketplace, sku)
    );
    """

def sql_crear_historico():
    """La PELÍCULA. Nace CERRADA igual que la foto: RLS on y cero políticas."""
    cols = ",\n        ".join(f"{c} {TIPO_SQL[_TIPO_DE[c]]}" for c in HISTORICO)
    return f"""
    CREATE TABLE IF NOT EXISTS salud_fba_historico (
        asin           text NOT NULL,
        marketplace    text NOT NULL,
        sku            text NOT NULL,
        snapshot_date  date NOT NULL,
        {cols},
        fichero        text,
        procesado_en   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (asin, marketplace, sku, snapshot_date)
    );
    """

# La definición de v_salud_fba_cruce se movió a migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql (es una migración, no arranque).
# El procesador ya no la ejecuta; solo la consulta.


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 🔒 PRIMERA línea del log, bien visible (el desplegable de Actions se queda
    # donde lo dejaste — ya mordió una vez).
    print(f"=== PROCESADOR SALUD_FBA ===", flush=True)
    print(f"MODO: {MODO}", flush=True)
    print(f"ENTORNO: {ENTORNO}", flush=True)
    print("=" * 40, flush=True)

    if MODO not in ('ensayo', 'aplicar'):
        sys.exit(f"MODO desconocido: {MODO!r} (usa 'ensayo' o 'aplicar')")
    if ENTORNO not in ('staging', 'produccion'):
        sys.exit(f"ENTORNO desconocido: {ENTORNO!r} (usa 'staging' o 'produccion')")
    if not SUPABASE_KEY or not DB_URL:
        sys.exit("Faltan credenciales (SUPABASE_KEY / DB_URL). Revisa los secrets del workflow.")

    # --- Bajar el informe más reciente del buzón (Storage de PRODUCCIÓN) ---
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    objs = listar_buzon(sb, BUCKET, CARPETA)
    txts = [o for o in objs if (o.get('name') or '').lower().endswith('.txt')]
    if not txts:
        sys.exit(f"No hay ningún .txt en {BUCKET}/{CARPETA}/. "
                 "Sube el informe SALUD_FBA (MANAGE_INVENTORY_HEALTH) en .txt y relanza.")
    txts.sort(key=lambda o: (o.get('updated_at') or o.get('created_at') or ''), reverse=True)

    if FICHERO:
        # Pedido a dedo: tiene que estar, EXACTO. Sin fallback al más reciente.
        nombres = [o['name'] for o in txts]
        if FICHERO not in nombres:
            print(f"\n❌ ABORTA (no se ha escrito nada):\n"
                  f"[Guarda fichero] Se pidió procesar {FICHERO!r} y no está en "
                  f"{BUCKET}/{CARPETA}/.\n"
                  f"   Hay {len(nombres)} .txt en el buzón: {nombres}\n"
                  f"   No se cae al más reciente: cargaría un informe distinto del que "
                  f"pediste sin avisar.", flush=True)
            sys.exit(1)
        fichero = FICHERO
        print(f"Informe elegido (pedido a dedo por FICHERO): {fichero}", flush=True)
    else:
        fichero = txts[0]['name']
        print(f"Informe elegido (el más reciente de {len(txts)}): {fichero}", flush=True)
    crudo_bytes = descargar_buzon(sb, BUCKET, f"{CARPETA}/{fichero}")

    # Encoding: el real trae UTF-8 con BOM (utf-8-sig). Fallback cp1252.
    try:
        texto = crudo_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = crudo_bytes.decode('cp1252')

    # --- Guardas estructurales 1..8 (antes de tocar la base) ---
    try:
        info = analizar(texto, fichero)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        sys.exit(1)

    filas = info['filas']
    snap = info['snapshot']
    print(f"\nFilas leídas y cuadradas: {len(filas)} · snapshot {snap} · "
          f"marketplaces {sorted({f['marketplace'] for f in filas})}", flush=True)

    # --- Conectar al ENTORNO ---
    con = conectar_bd(DB_URL)
    con.autocommit = False
    cur = con.cursor()

    # 🔒 ÁMBITO DE LA FOTO: los marketplaces que ESTE informe declara cubrir
    # (hoy solo ES). La foto que sustituye es la de esos marketplaces, no la
    # tabla entera: el día que llegue un informe de otro país, cargarlo no
    # puede borrar el de ES.
    AMBITO = ('marketplace', sorted({f['registro']['marketplace'] for f in filas}))

    # Guarda 9: anti-encogimiento. Corre ANTES de borrar y ANTES de escribir.
    try:
        previas = guarda_anti_encogimiento(cur, 'salud_fba', len(filas),
                                           ambito=AMBITO, etiqueta='9')
        # Guarda 10: no-retroceder. Una foto más vieja que la que ya hay no se
        # carga (informe caducado = información FALSA). PERMITIR_RETROCESO=1 la salta.
        guarda_no_retroceder(cur, 'salud_fba', 'snapshot_date', snap, ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # Claves que ya estaban (solo para contar altas). Antes del barrido.
    prev = claves_previas(cur, 'salud_fba', ['asin', 'marketplace', 'sku'], ambito=AMBITO)

    # --- Cruce en memoria contra `productos` (para los avisos §4.2 y el premio §5) ---
    cur.execute("SELECT btrim(asin), btrim(sku) FROM productos WHERE activo AND asin IS NOT NULL;")
    asins_activos = set()
    skus_por_asin = {}
    for a, s in cur.fetchall():
        if not a:
            continue
        au = a.upper()
        asins_activos.add(au)
        if s:
            skus_por_asin.setdefault(au, set()).add(s)

    sin_ficha, sku_discrepante = [], []
    for f in filas:
        au = f['asin'].strip().upper()
        if au not in asins_activos:
            sin_ficha.append(f"{f['asin']} · sku informe {f['sku']}")
        elif f['sku'].strip() not in skus_por_asin.get(au, set()):
            sku_discrepante.append(f"{f['asin']} · BD {sorted(skus_por_asin.get(au, set()))} "
                                   f"vs informe {f['sku']}")

    # Aviso DOS VIDAS (§4.2, NO aborta): un (asin, marketplace) con más de un SKU
    # vivo. La Guarda 2 ya no lo mata, pero NO puede volverse invisible: si esto
    # desaparece del log, hemos cambiado un aborto ruidoso por un silencio.
    por_asin_mk = {}
    for f in filas:
        por_asin_mk.setdefault((f['asin'], f['marketplace']), []).append(
            (f['sku'], f['registro'].get('fnsku')))
    dos_vidas = {k: v for k, v in por_asin_mk.items() if len(v) > 1}

    altas = [f for f in filas
             if (f['registro']['asin'], f['registro']['marketplace'],
                 f['registro']['sku']) not in prev]

    # --- Crear tabla + volcar (todo dentro de la transacción) ---
    cur.execute(sql_crear_tabla())
    # 🔒 RLS + índices fuera del arranque (migración): el ENABLE RLS pedía
    # AccessExclusiveLock sobre salud_fba (relation 20505 en el log del 29-jul) EN
    # CADA carga. Viven en migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql.
    # Solo se comprueba que la tabla está CERRADA (RLS activa); si no, ABORTA.
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.salud_fba'::regclass;")
    if not cur.fetchone()[0]:
        raise Aborta(
            "RLS no está activa en salud_fba. Ya NO la activa el procesador (era un lock exclusivo "
            "en cada carga). Aplica migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql y relanza.")
    # La vista v_salud_fba_cruce YA NO se recrea aquí (recrearla en cada carga pedía lock
    # exclusivo sobre media base y tumbó la app el 28-jul 15:47). Su definición vive en
    # migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql. Solo se comprueba que existe.
    cur.execute("SELECT to_regclass('public.v_salud_fba_cruce');")
    if cur.fetchone()[0] is None:
        raise Aborta(
            "La vista v_salud_fba_cruce no existe en este entorno. Ya NO la crea el procesador "
            "(era un lock que tumbaba la base). Aplica migraciones/2026-07-29_vistas_cruce_fuera_del_arranque.sql y relanza.")

    cols = [c for c, _ in TIPADAS] + ['snapshot_date', 'fichero', 'crudo']
    ph = ", ".join(['%s'] * len(cols))
    set_upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ('asin', 'marketplace', 'sku'))
    sql_upsert = (f"INSERT INTO salud_fba ({', '.join(cols)}) VALUES %s "
                  f"ON CONFLICT (asin, marketplace, sku) DO UPDATE SET {set_upd}, procesado_en=now();")

    # 🔒 LA FOTO TIRA LA HOJA VIEJA: los (asin, marketplace) del ámbito que ya no
    # vienen en el informe se BORRAN (los 7 SKU fantasma de 195→188 dejan de
    # existir). Mismo commit que la carga: o todo o nada. Las claves son
    # EXACTAMENTE los valores que el upsert va a escribir.
    claves_nuevas = [(f['registro']['asin'], f['registro']['marketplace'], f['registro']['sku'])
                     for f in filas]

    # ── SALVAGUARDA anti-omisión (CAMINO A · B3, 3-ago-2026) ────────────────
    # El informe FBA a veces OMITE productos SANOS (con stock). El patrón foto los
    # borraría. Antes de barrer, PROTEGEMOS las vidas (asin, mk, sku) que ya están en
    # salud_fba, NO vienen en el informe de hoy, y AÚN tienen stock REAL.
    #
    # 🔴 CAMBIO 3-ago (B3): la ÚNICA evidencia de stock que vale es la ACTUAL. Antes se
    # protegía también por el available+fc_transfer de la PROPIA fila vieja — un dato
    # RANCIO que mantenía vivas filas de productos ya vacíos. Medido en prod: 7 filas
    # con stock 0 hoy en internacional, sostenidas por su self-stock de hace 2-3 semanas,
    # inflaban 121 uds de T30. Ahora la evidencia es SOLO inventario_internacional (la
    # foto del inventario = el estado de HOY): si internacional dice 0, es un fantasma y
    # se da de baja. (El impacto sobre la velocidad ya lo quitó v_velocidad_ventas; esto
    # es higiene de la foto para el resto de consumidores.)
    en_fichero = {(a.upper(), mk.upper(), sku.upper()) for (a, mk, sku) in claves_nuevas}
    cur.execute("SELECT DISTINCT btrim(asin) FROM inventario_internacional WHERE quantity > 0;")
    intl_con_stock = {r[0].upper() for r in cur.fetchall() if r[0]}

    # 🔒 Guarda A-intl (2a): la protección ahora DEPENDE de internacional. Si esa foto
    # viene vacía o hundida, muchos productos sanos perderían el respaldo y se darían de
    # baja EN MASA. Antes de fiarnos de ella, se comprueba que está sana:
    #   · vacía (0 ASIN con stock) → ABORTA.
    #   · < 50% de su foto ANTERIOR (idioma anti-encogimiento) → ABORTA.
    cur.execute("SELECT max(fecha_foto) FROM inventario_internacional;")
    intl_fecha = cur.fetchone()[0]
    cur.execute(
        "SELECT count(*) FROM ("
        "  SELECT btrim(asin) a FROM inventario_internacional_historico "
        "  WHERE fecha_foto = (SELECT max(fecha_foto) FROM inventario_internacional_historico "
        "                      WHERE fecha_foto < %s) AND quantity > 0 "
        "  GROUP BY btrim(asin)) t;", (intl_fecha,))
    intl_prev = cur.fetchone()[0]
    intl_ahora = len(intl_con_stock)
    if intl_ahora == 0:
        raise Aborta(
            "[Guarda A-intl] inventario_internacional no tiene ni un ASIN con stock: la red que "
            "protege a salud_fba de dar de baja productos omitidos-pero-con-stock DEPENDE de esa "
            "foto. Vacía, no puedo distinguir un fantasma de un omitido. No se borra nada en salud.")
    if intl_prev and intl_ahora < intl_prev * 0.5:
        raise Aborta(
            f"[Guarda A-intl] inventario_internacional cayó a {intl_ahora} ASIN con stock (su foto "
            f"anterior tenía {intl_prev}): menos del 50%. Parece una carga incompleta; no se da de "
            f"baja nada en salud hasta que internacional vuelva a estar sana.")

    # Candidatas a baja = vidas del ámbito ausentes del informe y SIN respaldo en
    # internacional. Se traen con DETALLE (nombre, uds, T30, fecha) para poder ENSEÑAR
    # la lista antes de aplicar: una baja NUNCA se cierra en silencio.
    cur.execute(
        "SELECT asin, marketplace, sku, product_name, "
        "       COALESCE(available,0)+COALESCE(fc_transfer,0), units_shipped_t30, snapshot_date "
        "FROM salud_fba WHERE marketplace = ANY(%s);", (AMBITO[1],))
    protegidas, bajas = [], []
    for asin_p, mk_p, sku_p, nombre_p, disp_p, t30_p, snap_p in cur.fetchall():
        if (asin_p.upper(), mk_p.upper(), sku_p.upper()) in en_fichero:
            continue  # esta vida sí viene en el informe: no es candidata a baja
        if asin_p.upper() in intl_con_stock:
            protegidas.append((asin_p, mk_p, sku_p))                       # respaldo ACTUAL → NO borrar
        else:
            bajas.append((asin_p, mk_p, sku_p, nombre_p, disp_p, t30_p, snap_p))  # fantasma → baja

    # 🔒 Guarda A-tope (2b): si una carga daría de baja MÁS de N vidas, PARA y avisa en
    # vez de aplicar. N = max(15, 10% de las filas previas): la limpieza inicial son ~7
    # y el régimen normal 0-3; pasar de ~15-22 solo ocurre si internacional falló o el
    # informe de salud vino raro. Válvula para una descatalogación masiva legítima ya
    # revisada: PERMITIR_BAJAS_MASIVAS=1.
    n_tope = max(15, int(previas * 0.10))
    if len(bajas) > n_tope:
        if os.environ.get('PERMITIR_BAJAS_MASIVAS') != '1':
            raise Aborta(
                f"[Guarda A-tope] Esta carga daría de baja {len(bajas)} vidas de salud_fba (tope {n_tope}). "
                f"Es demasiado para ser churn normal: casi siempre significa que internacional vino "
                f"incompleto o que el informe de salud llegó raro. No se borra nada. Míralo; si es una "
                f"descatalogación masiva de verdad ya revisada: PERMITIR_BAJAS_MASIVAS=1.")
        # 🔓 VÁLVULA ABIERTA a propósito → queda ESCRITO en el log (nº de bajas + fechas).
        # Por defecto está APAGADA; solo se entra aquí si alguien puso PERMITIR_BAJAS_MASIVAS=1
        # en ESE run (es de un solo uso: no persiste). Una puerta trasera sin rastro acaba
        # abierta (Fernando, 3-ago), así que se grita con el número y la fecha.
        print(f"\n⚠️⚠️  [Guarda A-tope · VÁLVULA ABIERTA] PERMITIR_BAJAS_MASIVAS=1 → se SALTA el "
              f"tope de {n_tope} y se dan de baja {len(bajas)} vidas de salud_fba. "
              f"snapshot del informe {snap} · ejecutado {datetime.now().isoformat(timespec='seconds')} · "
              f"ámbito {describir_ambito(AMBITO)}. La lista completa va justo debajo.", flush=True)

    # CONDICIÓN (Fernando, 3-ago): la lista de bajas se IMPRIME ENTERA (ensayo y aplicar),
    # nunca en silencio. En ENSAYO se ve lo que SE BORRARÍA, para revisarlo antes de aplicar.
    if bajas:
        print(f"\n--- 🗑️  BAJAS de salud_fba ({describir_ambito(AMBITO)}): {len(bajas)} vida(s) "
              f"ausentes del informe y SIN stock en internacional HOY ---", flush=True)
        print(f"   {'ASIN':<12} {'uds':>4} {'T30':>4} {'omit':>5}  producto", flush=True)
        for asin_b, mk_b, sku_b, nombre_b, disp_b, t30_b, snap_b in sorted(
                bajas, key=lambda r: (r[6] or date.min)):
            dias = (snap - snap_b).days if snap_b else '?'
            print(f"   {asin_b:<12} {disp_b or 0:>4} "
                  f"{(t30_b if t30_b is not None else '—'):>4} {str(dias)+'d':>5}  "
                  f"{(nombre_b or '')[:70]}", flush=True)
    if protegidas:
        print(f"   · 🛡️ Salvaguarda: {len(protegidas)} vida(s) ausentes del informe PROTEGIDAS "
              f"(con stock en internacional HOY): "
              f"{', '.join(a for a, _, _ in protegidas[:10])}"
              f"{' …' if len(protegidas) > 10 else ''}", flush=True)
    claves_barrido = claves_nuevas + protegidas
    # ────────────────────────────────────────────────────────────────────────

    try:
        borradas = barrer_sobrantes(cur, 'salud_fba', ['asin', 'marketplace', 'sku'],
                                    claves_barrido, ambito=AMBITO)
    except Aborta as e:
        print(f"\n❌ ABORTA (no se ha escrito nada):\n{e}", flush=True)
        con.rollback(); cur.close(); con.close(); sys.exit(1)

    # 🔒 Volcado por LOTES (execute_values), no fila a fila. SIN dedup a propósito:
    # a diferencia de paneu/internacional (donde un duplicado se define como "la
    # última gana"), aquí un trío (asin, marketplace, sku) repetido es un INFORME
    # CORRUPTO y la Guarda 2 ya ABORTA por él en analizar(), antes de llegar aquí
    # (y la Guarda 7 garantiza un solo snapshot_date). Entre las dos, la clave del
    # ON CONFLICT de las dos tablas es única antes del volcado: execute_values no
    # puede recibir clave repetida. Deduplicar ("elegir la última") enmascararía
    # justo lo que Guarda 2 manda gritar.
    vals_foto = [tuple([f['registro'][c] for c, _ in TIPADAS] + [snap, fichero, Json(f['crudo'])])
                 for f in filas]
    execute_values(cur, sql_upsert, vals_foto, template=f"({ph})", page_size=500)

    # ── EL HISTÓRICO: apilar la copia fechada (PELÍCULA, §1.6) ──────────────
    # Va DESPUÉS del upsert de la foto viva y DENTRO de la misma transacción.
    # No borra nada: aquí no hay barrido ni ámbito que valga.
    cur.execute(sql_crear_historico())
    # 🔒 RLS + índices del histórico también fuera del arranque (misma migración).
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.salud_fba_historico'::regclass;")
    if not cur.fetchone()[0]:
        raise Aborta(
            "RLS no está activa en salud_fba_historico. Ya NO la activa el procesador. "
            "Aplica migraciones/2026-07-29_rls_indices_fuera_del_arranque.sql y relanza.")

    # Qué había YA de este día (para distinguir apilar de reescribir en el log:
    # si reprocesas el mismo fichero, todo tiene que salir como 'reescritas').
    cur.execute("SELECT asin, marketplace, sku FROM salud_fba_historico "
                "WHERE snapshot_date = %s AND marketplace = ANY(%s);",
                (snap, AMBITO[1]))
    ya_del_dia = {tuple(r) for r in cur.fetchall()}

    cols_h = ['asin', 'marketplace', 'sku', 'snapshot_date'] + HISTORICO + ['fichero']
    ph_h = ", ".join(['%s'] * len(cols_h))
    set_h = ", ".join(f"{c}=EXCLUDED.{c}" for c in HISTORICO + ['fichero'])
    sql_hist = (f"INSERT INTO salud_fba_historico ({', '.join(cols_h)}) VALUES %s "
                f"ON CONFLICT (asin, marketplace, sku, snapshot_date) DO UPDATE SET "
                f"{set_h}, procesado_en=now();")

    # 🔒 SOLO las filas del fichero. Las protegidas NO se apilan. Por LOTES; sin
    # dedup por lo mismo que la Foto (Guarda 2 + Guarda 7 garantizan la clave única).
    vals_hist = [tuple([f['registro']['asin'], f['registro']['marketplace'],
                        f['registro']['sku'], snap]
                       + [f['registro'][c] for c in HISTORICO] + [fichero])
                 for f in filas]
    execute_values(cur, sql_hist, vals_hist, template=f"({ph_h})", page_size=500)

    hist_reescritas = sum(
        1 for f in filas
        if (f['registro']['asin'], f['registro']['marketplace'],
            f['registro']['sku']) in ya_del_dia)
    hist_apiladas = len(filas) - hist_reescritas

    cur.execute("SELECT count(*), count(DISTINCT snapshot_date), "
                "       min(snapshot_date), max(snapshot_date) "
                "FROM salud_fba_historico;")
    h_filas, h_dias, h_min, h_max = cur.fetchone()
    # ────────────────────────────────────────────────────────────────────────

    # --- Resumen (se imprime siempre) ---
    print(resumen_foto('salud_fba', AMBITO, previas, len(filas),
                       len(altas), borradas, MODO), flush=True)

    # --- Cuadre de la foto (el log no puede mentir) ---
    # `len(filas)` es lo que trae el FICHERO; la tabla tiene además las filas que
    # la salvaguarda protegió (ausentes del informe pero con stock). Se imprime el
    # count REAL para que las dos cifras no se confundan nunca más.
    cur.execute("SELECT count(*) FROM salud_fba WHERE marketplace = ANY(%s);",
                (AMBITO[1],))
    en_tabla = cur.fetchone()[0]
    # De las protegidas, las que llevan >3 días sin aparecer en ningún informe:
    # su snapshot_date se quedó atrás porque no se refrescan. Son las "rancias".
    cur.execute("SELECT count(*) FROM salud_fba WHERE marketplace = ANY(%s) "
                "AND snapshot_date < %s - INTERVAL '3 days';", (AMBITO[1], snap))
    rancias = cur.fetchone()[0]

    print(f"\n--- Cuadre de la foto ({describir_ambito(AMBITO)}) ---")
    print(f"   · filas del fichero:                    {len(filas)}")
    print(f"   · filas en la tabla (count real):       {en_tabla}")
    print(f"   · protegidas (no venían en el informe): {len(protegidas)}")
    print(f"        · de ellas, >3 días sin aparecer:  {rancias}", flush=True)

    print(f"\n--- Histórico salud_fba_historico (Película: apila, NUNCA borra) ---")
    print(f"   · apiladas de esta pasada (nuevas):     {hist_apiladas}")
    print(f"   · reescritas (mismo día ya cargado):    {hist_reescritas}")
    print(f"   · días distintos en el histórico:       {h_dias}"
          f"{f'  (de {h_min} a {h_max})' if h_dias else ''}")
    print(f"   · filas totales en el histórico:        {h_filas}", flush=True)

    print(f"\n--- Avisos (§4.2 · NO abortan · viven en la vista v_salud_fba_cruce) ---")
    print(f"   · ASIN sin ficha activa en productos (red del reverso): {len(sin_ficha)}")
    for s in sin_ficha[:50]:
        print(f"        · {s}")
    if len(sin_ficha) > 50:
        print(f"        … y {len(sin_ficha) - 50} más")
    print(f"   · SKU discrepante informe≠BD (el premio §5): {len(sku_discrepante)}")
    for s in sku_discrepante[:50]:
        print(f"        · {s}")

    print(f"\n--- 🎭 DOS VIDAS (§4.2 · NO aborta · un ASIN con >1 SKU vivo en el país) ---")
    print(f"   · ASIN con más de un SKU vivo: {len(dos_vidas)}")
    for (asin_dv, mk_dv), vidas_dv in list(dos_vidas.items())[:50]:
        detalle = ", ".join(f"{sku_dv} (FNSKU {fn_dv or '—'})" for sku_dv, fn_dv in vidas_dv)
        print(f"        · {asin_dv} [{mk_dv}]: {detalle}")

    # --- Escritura (o no) ---
    if MODO == 'aplicar':
        con.commit()
        print(f"\n✅ APLICADO en {ENTORNO}: salud_fba queda con {en_tabla} filas "
              f"({len(filas)} del informe + {len(protegidas)} protegidas) "
              f"(tabla y vista listas, RLS activo sin políticas).")
        print(f"   · salud_fba_historico: {h_filas} filas en {h_dias} día(s) "
              f"(RLS activo sin políticas).")
    else:
        con.rollback()   # 🔒 ensayo: no se escribe ni un byte
        print(f"\n🔎 ENSAYO: TODAS las guardas pasaron, NO se ha escrito nada. "
              f"(La tabla/vista y el volcado se han probado dentro de una transacción "
              f"revertida.)")

    cur.close(); con.close()
    print(f"\n=== FIN · entorno={ENTORNO} · modo={MODO} · "
          f"filas_fichero={len(filas)} · filas_tabla={en_tabla} · "
          f"protegidas={len(protegidas)} · protegidas_rancias={rancias} · "
          f"altas={len(altas)} · bajas={borradas} · dos_vidas={len(dos_vidas)} · "
          f"sin_ficha={len(sin_ficha)} · sku_discrepante={len(sku_discrepante)} · "
          f"hist_apiladas={hist_apiladas} · hist_reescritas={hist_reescritas} · "
          f"hist_dias={h_dias} · hist_filas={h_filas} ===", flush=True)


if __name__ == '__main__':
    main()
