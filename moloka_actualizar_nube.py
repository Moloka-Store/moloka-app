# ============================================================
# MOLOKA - Actualizar App  ::  VERSION NUBE (GitHub Actions)
# Generado a partir de Moloka_ActualizarApp.ipynb (NO editar a mano: regenerar con ensamblar.py).
# Diferencias con Colab:
#   - Sin Google Drive. Los informes se descargan del buzon (Supabase Storage 'informes/entrada').
#   - Credenciales desde variables de entorno (GitHub Secrets), no Colab Secrets.
#   - El modo (rapida/completa) se lee del _solicitud.json que deja la app.
#   - RAPIDA: 1 sola pasada de Espana con Keepa (~570 tok). COMPLETA: ES+IT+FR.
# ============================================================
import os, re, csv, json, shutil
from datetime import datetime, timedelta, date
from collections import defaultdict
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ogfbjjdxcltzpygzuyla.supabase.co')
SUPABASE_KEY = os.environ['SUPABASE_KEY']

BASE = os.path.abspath('./moloka_run')
INPUTS = f'{BASE}/inputs'
PROCESSED = f'{BASE}/inputs/processed'
OUT_JSON = f'{BASE}/output/json'
OUT_SQL = f'{BASE}/output/sql'
for _r in (INPUTS, PROCESSED, OUT_JSON, OUT_SQL):
    os.makedirs(_r, exist_ok=True)

COSTE_ALMACEN_UD = 0.15
IVA_GENERAL = 1.21
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
MESES_ES = {'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,
            'jul':7,'ago':8,'sep':9,'oct':10,'nov':11,'dic':12}
MESES_NOMBRE = ['enero','febrero','marzo','abril','mayo','junio',
                'julio','agosto','septiembre','octubre','noviembre','diciembre']

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Recado (patron buzon): el _solicitud.json es la senal de "hay trabajo".
#     Asomada automatica (schedule) SIN recado -> salir sin gastar nada.
#     Lanzamiento manual (workflow_dispatch / local) -> procesa siempre (para pruebas). ---
BUCKET, CARPETA_BUZON = 'informes', 'entrada'
SOLICITUD_MODO = 'rapida'
EVENTO = os.environ.get('GITHUB_EVENT_NAME', 'manual')
try:
    _chk = sb.storage.from_(BUCKET).list(CARPETA_BUZON) or []
    HAY_RECADO = any(o.get('name') == '_solicitud.json' for o in _chk)
except Exception as _e:
    HAY_RECADO = False
    print('AVISO al comprobar recado:', _e)
if EVENTO == 'schedule' and not HAY_RECADO:
    print('Asomada automatica: sin recado en el buzon, nada que hacer. Fin.')
    import sys; sys.exit(0)
print(f"Evento={EVENTO} | recado={'SI' if HAY_RECADO else 'NO'} -> se procesa")

# --- Descargar informes del buzon a INPUTS y leer el modo ---
_descargados = []
n_inf = 0
try:
    objs = sb.storage.from_(BUCKET).list(CARPETA_BUZON) or []
    for o in objs:
        nombre = o['name']
        if not nombre or nombre.startswith('.'):   # placeholder de carpeta vacia u ocultos
            continue
        ruta = f'{CARPETA_BUZON}/{nombre}'
        if nombre == '_solicitud.json':
            try:
                d = sb.storage.from_(BUCKET).download(ruta)
                SOLICITUD_MODO = json.loads(d.decode('utf-8')).get('modo', 'rapida')
            except Exception as _e:
                print('AVISO solicitud:', _e)
            continue
        d = sb.storage.from_(BUCKET).download(ruta)
        with open(f'{INPUTS}/{nombre}', 'wb') as _f:
            _f.write(d)
        _descargados.append(nombre)
        n_inf += 1
    print(f'Buzon: {n_inf} informe(s) descargado(s). Modo solicitado: {SOLICITUD_MODO}')
except Exception as _ex:
    print('AVISO buzon (sin informes nuevos?):', _ex)

# GUARDADO ANTI-VACIO: sin informes no se procesa NADA (evita machacar los JSON
# buenos de app_datos con datos vacios, como paso el 12-jun). No toca la app ni
# el buzon; sale limpio para que subas los informes y vuelvas a lanzar.
if n_inf == 0:
    print('Buzon SIN informes: no hay nada que procesar. No se ha tocado la app ni el '
          'buzon. Sube los informes al buzon y vuelve a lanzar.')
    import sys; sys.exit(0)


# --- Cargar productos desde Supabase (igual que el notebook) ---
print('=== Cargando productos desde Supabase ===')
todos_productos = []
_desde, PAGE = 0, 1000
while True:
    r = sb.table('productos').select(
        'id, sku, asin, ean, fnsku, nombre, proveedor, pvd, marca, activo, estado, keepa_image'
    ).range(_desde, _desde + PAGE - 1).execute()
    if not r.data: break
    todos_productos.extend(r.data)
    if len(r.data) < PAGE: break
    _desde += PAGE

MAPA_SKU, MAPA_ASIN_SIN_SKU = {}, {}
for p in todos_productos:
    if p.get('sku'):
        MAPA_SKU[p['sku']] = {'id': p['id'],'asin': p.get('asin'),'ean': p.get('ean'),
            'fnsku': p.get('fnsku'),'nombre': p.get('nombre','') or '','proveedor': p.get('proveedor','') or '',
            'pvd': float(p.get('pvd') or 0),'marca': p.get('marca','') or '','activo': p.get('activo', True),
            'estado': p.get('estado','') or ''}
    elif p.get('asin') and p.get('activo', True):
        a = p['asin'].strip()
        if a:
            MAPA_ASIN_SIN_SKU[a] = {'id': p['id'],'ean': p.get('ean'),'nombre': p.get('nombre','') or '',
                'proveedor': p.get('proveedor','') or '','pvd': float(p.get('pvd') or 0),
                'marca': p.get('marca','') or '','estado': p.get('estado','') or ''}
print(f'Productos: {len(todos_productos)} | Con SKU: {len(MAPA_SKU)} | Sin SKU con ASIN: {len(MAPA_ASIN_SIN_SKU)}')


# ============================================================
# Moloka — Actualizar App
# ============================================================

# ============================================================
# 1. Configuración inicial
# ============================================================

# ============================================================
# 2. Detector automático de informes
# ============================================================

def detectar_tipo(filepath):
    """Detecta el tipo de informe Amazon segun cabecera."""
    try:
        with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
            primeras = []
            for i in range(20):
                try: primeras.append(next(f))
                except StopIteration: break
            contenido = '\n'.join(primeras).lower()

        # FBA Inventory (TXT tab-separated)
        if 'snapshot-date' in contenido and 'inbound-quantity' in contenido:
            return 'inventario_fba'
        # Transacciones (Custom Transaction Report) - ES / IT / FR
        es_trans = (('ventas de productos' in contenido)
                    or ('ventes de produits' in contenido)
                    or ('vendite' in contenido and 'numero ordine' in contenido)
                    or ('product sales' in contenido))
        if es_trans:
            return 'transacciones'
        # Customer Returns
        if 'return-date' in contenido and 'detailed-disposition' in contenido:
            return 'customer_returns'
        # Removal Orders (NO debe matchear con shipments - este NO tiene tracking-number ni shipment-date)
        if 'request-date' in contenido and 'order-status' in contenido and 'requested-quantity' in contenido:
            return 'removal_orders'
        # Removal Shipments (incluye tracking-number y shipment-date)
        if 'shipment-date' in contenido and 'tracking-number' in contenido:
            return 'removal_shipments'
        # Reimbursements (Amazon te paga)
        if 'reimbursement-id' in contenido and 'amount-total' in contenido:
            return 'reimbursements'
        return None
    except Exception as e:
        print(f"Error leyendo {filepath}: {e}")
        return None


print(f"=== Escaneando {INPUTS} ===")
archivos_detectados = {}
for nombre in os.listdir(INPUTS):
    ruta = os.path.join(INPUTS, nombre)
    if os.path.isdir(ruta) or nombre.startswith('.'): continue
    if not (nombre.lower().endswith('.csv') or nombre.lower().endswith('.txt')): continue

    tipo = detectar_tipo(ruta)
    if tipo:
        archivos_detectados[ruta] = tipo
        print(f"OK {nombre} -> {tipo}")
    else:
        print(f"-- {nombre} -> tipo desconocido (ignorado)")

if not archivos_detectados:
    print(f"\nNO HAY INFORMES PARA PROCESAR. Sube CSV/TXT a {INPUTS}")
else:
    print(f"\nTotal: {len(archivos_detectados)} informes a procesar")


# ============================================================
# 3. Procesador: Transacciones
# ============================================================

# MESES_ES y MESES_NOMBRE estan definidos en celda 2 (config inicial)

# ============================================================
# TRANSACCIONES MULTIPAIS (ES + IT + FR)
# ------------------------------------------------------------
# Cada informe Custom Transactions viene en el idioma de su
# marketplace. Este procesador detecta el pais por las columnas,
# normaliza filas al formato canonico y ACUMULA por pais.
# Los JSON (velocidades + rentabilidad) se regeneran con TODO lo
# acumulado tras procesar cada archivo -> da igual el orden y
# re-procesar un informe no duplica (reemplaza su pais).
#
# velocidades.json: totales EU (como siempre) + 'por_pais' por
#   producto (la pestaña Rotacion IT/FR lo lee tal cual).
# rentabilidad.json: raiz IDENTICA a la actual (solo ES, para no
#   tocar la pestaña Rentabilidad de hoy) + claves nuevas
#   'por_pais' (IT/FR) y 'total_eu' para la futura pestaña.
# venta_actual: SOLO ventas ES (la Rotacion ES la consume; IT/FR
#   usan canales_producto).
# Formula de rentabilidad: LA VALIDADA de ES tal cual. Las ventas
# de cada informe ya vienen en base imponible con el IVA de su
# pais en columna aparte; las tarifas llevan IVA 21% espanol
# (validado con pedidos reales IT/FR el 10-jun) -> /1.21 igual.
# ============================================================

import unicodedata

def _sin_acentos(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

MESES_IT = {'gen':1,'feb':2,'mar':3,'apr':4,'mag':5,'giu':6,'lug':7,'ago':8,'set':9,'ott':10,'nov':11,'dic':12}
MESES_FR = {'janv':1,'fevr':2,'mars':3,'avr':4,'mai':5,'juin':6,'juil':7,'aout':8,'sept':9,'oct':10,'nov':11,'dec':12}

def parse_fecha_pais(s, pais):
    """'8 gen 2026 03:21:31 UTC' / '7 avr. 2026 ...' / '9 jun 2026 ...' -> datetime (solo fecha)."""
    if not s: return None
    m = re.match(r'(\d+)\s+([^\s]+)\s+(\d{4})', str(s).strip())
    if not m: return None
    dia, mes_tok, anyo = m.groups()
    tok = _sin_acentos(mes_tok).lower().strip('.').strip()
    if pais == 'ES':
        mm = MESES_ES.get(tok[:3])
    elif pais == 'IT':
        mm = MESES_IT.get(tok[:3])
    else:  # FR: 'juin'/'juil' comparten prefijo 3 -> match por token completo o prefijo
        mm = MESES_FR.get(tok)
        if not mm:
            for clave, num in MESES_FR.items():
                if tok.startswith(clave) or clave.startswith(tok):
                    mm = num; break
    if not mm: return None
    try: return datetime(int(anyo), mm, int(dia))
    except: return None

def parse_fecha_es(s):
    # se mantiene por compatibilidad con otras celdas
    return parse_fecha_pais(s, 'ES')

def parse_num(s):
    if not s or str(s).strip() in ('', '-'): return 0.0
    s = str(s).strip()
    if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

# Definicion por pais: como detectarlo y que columna es que.
# Los alias se comparan SIN acentos y en minusculas (cabeceras reales validadas
# contra informes de los 3 paises el 10-jun-2026).
PAISES_TRANS = {
    'ES': {
        'firma': ['ventas de productos'],
        'tipos': {'pedido': 'Pedido', 'reembolso': 'Reembolso'},
        'cols': {
            'fecha':    ['fecha y hora'],
            'tipo':     ['tipo'],
            'sku':      ['sku'],
            'cantidad': ['cantidad'],
            'ventas':   ['ventas de productos'],
            'impuesto': ['impuesto de ventas de productos'],
            't_venta':  ['tarifas de venta'],
            't_fba':    ['tarifas de logistica de amazon'],
            't_otras':  ['tarifas de otras transacciones'],
        },
    },
    'IT': {
        'firma': ['vendite', 'numero ordine'],
        'tipos': {'ordine': 'Pedido', 'rimborso': 'Reembolso'},
        'cols': {
            'fecha':    ['data/ora:', 'data/ora'],
            'tipo':     ['tipo'],
            'sku':      ['sku'],
            'cantidad': ['quantita'],
            'ventas':   ['vendite'],
            'impuesto': ['imposta sulle vendite dei prodotti'],
            't_venta':  ['commissioni di vendita'],
            't_fba':    ['costi del servizio logistica di amazon'],
            't_otras':  ['altri costi relativi alle transazioni'],
        },
    },
    'FR': {
        'firma': ['ventes de produits'],
        'tipos': {'commande': 'Pedido', 'remboursement': 'Reembolso'},
        'cols': {
            'fecha':    ['date/heure'],
            'tipo':     ['type'],
            'sku':      ['sku'],
            'cantidad': ['quantite'],
            'ventas':   ['ventes de produits'],
            'impuesto': ['taxes sur la vente des produits'],
            't_venta':  ['frais de vente'],
            't_fba':    ['frais expedie par amazon'],
            't_otras':  ['autres frais de transaction'],
        },
    },
}

# Acumulador global: pais -> lista de registros canonicos.
# REEMPLAZA por pais al procesar -> idempotente aunque se re-ejecute.
if 'TRANSACCIONES_PAIS' not in globals():
    TRANSACCIONES_PAIS = {}

def _detectar_pais_trans(cabecera_norm):
    for pais, cfg in PAISES_TRANS.items():
        if all(any(firma in c for c in cabecera_norm) for firma in cfg['firma']):
            return pais
    return None

def _col_real(cabecera, cabecera_norm, alias_list):
    for alias in alias_list:
        for real, norm in zip(cabecera, cabecera_norm):
            if norm == alias or norm.startswith(alias):
                return real
    return None

def procesar_transacciones(filepath):
    print(f"\n{'='*60}")
    print(f"TRANSACCIONES: {os.path.basename(filepath)}")
    print('='*60)

    with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
        lines = f.readlines()

    # Cabecera: primera fila con bastantes columnas que contenga una columna de tipo
    cabecera_idx, cabecera = None, None
    for i, ln in enumerate(lines[:30]):
        cols = next(csv.reader([ln]))
        if len(cols) >= 15:
            norm = [_sin_acentos(c).lower().strip() for c in cols]
            if any(n in ('tipo', 'type') for n in norm):
                cabecera_idx, cabecera = i, cols
                break
    if cabecera_idx is None:
        print("ERROR: no se encontro la cabecera del informe")
        return None

    cab_norm = [_sin_acentos(c).lower().strip() for c in cabecera]
    pais = _detectar_pais_trans(cab_norm)
    if not pais:
        print("ERROR: no reconozco el pais de este informe (ni ES ni IT ni FR). Avisa a Claude.")
        return None
    cfg = PAISES_TRANS[pais]
    print(f"Pais detectado: {pais}")

    # Resolver nombres reales de columnas para este archivo
    col = {}
    for canon, alias in cfg['cols'].items():
        col[canon] = _col_real(cabecera, cab_norm, alias)
        if col[canon] is None and canon in ('fecha', 'tipo', 'sku', 'ventas'):
            print(f"ERROR: no encuentro la columna '{canon}' ({alias}) en el informe {pais}")
            return None

    trans = list(csv.DictReader(lines[cabecera_idx+1:], fieldnames=cabecera))
    print(f"Transacciones: {len(trans)} (cabecera linea {cabecera_idx})")

    # Normalizar a registros canonicos
    registros, descartes_tipo = [], 0
    for t in trans:
        tipo_raw = _sin_acentos(t.get(col['tipo'], '') or '').lower().strip()
        tipo = cfg['tipos'].get(tipo_raw)
        if not tipo:
            descartes_tipo += 1
            continue
        f = parse_fecha_pais(t.get(col['fecha'], ''), pais)
        if not f: continue
        registros.append({
            'pais': pais, 'tipo': tipo, 'fecha': f,
            'sku': (t.get(col['sku'], '') or '').strip(),
            'cantidad': int(parse_num(t.get(col['cantidad'], 0)) or 0),
            'ventas': parse_num(t.get(col['ventas'], '0')),
            'impuesto': parse_num(t.get(col['impuesto'], '0')) if col['impuesto'] else 0.0,
            't_venta': parse_num(t.get(col['t_venta'], '0')) if col['t_venta'] else 0.0,
            't_fba': parse_num(t.get(col['t_fba'], '0')) if col['t_fba'] else 0.0,
            't_otras': parse_num(t.get(col['t_otras'], '0')) if col['t_otras'] else 0.0,
        })

    pedidos = [r for r in registros if r['tipo'] == 'Pedido']
    if not pedidos:
        print(f"ERROR: no hay pedidos en el informe {pais}")
        return None
    print(f"Registros utiles: {len(registros)} ({len(pedidos)} pedidos) | otras filas (tarifas de stock, etc.): {descartes_tipo}")

    TRANSACCIONES_PAIS[pais] = registros   # REEMPLAZA: idempotente
    resumen = _generar_jsons_transacciones()

    fechas = [r['fecha'] for r in pedidos]
    resumen.update({
        'archivo': os.path.basename(filepath),
        'pais': pais,
        'filas_leidas': len(trans),
        'fecha_desde': min(fechas).strftime('%Y-%m-%d'),
        'fecha_hasta': max(fechas).strftime('%Y-%m-%d'),
    })
    return resumen


def _rentabilidad_meses(registros):
    """Calcula la lista de meses (formula validada ES) para una lista de registros canonicos."""
    meses_data = defaultdict(lambda: {
        'unidades': 0, 'unidades_devueltas': 0, 'pedidos': 0,
        'productos': defaultdict(lambda: {
            'sku': '', 'asin': None, 'nombre': '',
            'unidades': 0, 'pedidos': 0,
            'facturado_sin_iva': 0, 'facturado_iva': 0,
            'tarifas_venta': 0, 'tarifas_fba': 0, 'tarifas_otras': 0,
            'reemb_ventas': 0,
            'reemb_tarifas_venta': 0, 'reemb_tarifas_fba': 0, 'reemb_tarifas_otras': 0,
            'reemb_unidades': 0,
        }),
        'reemb_sin_sku_ventas': 0,
        'reemb_sin_sku_tarifas_venta': 0,
        'reemb_sin_sku_tarifas_fba': 0,
        'reemb_sin_sku_tarifas_otras': 0,
    })
    skus_huerfanos = set()

    for r in registros:
        mes_key = r['fecha'].strftime('%Y-%m')
        sku = r['sku']
        if r['tipo'] == 'Pedido':
            meses_data[mes_key]['unidades'] += r['cantidad']
            meses_data[mes_key]['pedidos'] += 1
            if sku and sku in MAPA_SKU:
                d = meses_data[mes_key]['productos'][sku]
                d['sku'] = sku
                d['asin'] = MAPA_SKU[sku].get('asin')
                d['nombre'] = MAPA_SKU[sku].get('nombre', '')
                d['unidades'] += r['cantidad']
                d['pedidos'] += 1
                d['facturado_sin_iva'] += r['ventas']
                d['facturado_iva'] += (r['ventas'] + r['impuesto'])
                d['tarifas_venta'] += r['t_venta']
                d['tarifas_fba'] += r['t_fba']
                d['tarifas_otras'] += r['t_otras']
            elif sku:
                skus_huerfanos.add(sku)
        else:  # Reembolso
            meses_data[mes_key]['unidades_devueltas'] += r['cantidad']
            if sku and sku in MAPA_SKU:
                d = meses_data[mes_key]['productos'][sku]
                d['reemb_ventas'] += r['ventas']
                d['reemb_tarifas_venta'] += r['t_venta']
                d['reemb_tarifas_fba'] += r['t_fba']
                d['reemb_tarifas_otras'] += r['t_otras']
                d['reemb_unidades'] += r['cantidad']
            else:
                meses_data[mes_key]['reemb_sin_sku_ventas'] += r['ventas']
                meses_data[mes_key]['reemb_sin_sku_tarifas_venta'] += r['t_venta']
                meses_data[mes_key]['reemb_sin_sku_tarifas_fba'] += r['t_fba']
                meses_data[mes_key]['reemb_sin_sku_tarifas_otras'] += r['t_otras']

    meses_resumen = []
    for mes_key in sorted(meses_data.keys()):
        d = meses_data[mes_key]
        anyo, mn = mes_key.split('-')
        mes_nombre = MESES_NOMBRE[int(mn)-1]

        fact_iva = sum(p['facturado_iva'] for p in d['productos'].values())
        fact_sin_iva = sum(p['facturado_sin_iva'] for p in d['productos'].values())
        comision_amazon = sum(-p['tarifas_venta'] for p in d['productos'].values()) / IVA_GENERAL
        logistica_fba = sum(-p['tarifas_fba'] for p in d['productos'].values()) / IVA_GENERAL
        otras_tarifas = sum(-p['tarifas_otras'] for p in d['productos'].values()) / IVA_GENERAL
        coste_almacen = sum(p['unidades'] * COSTE_ALMACEN_UD for p in d['productos'].values())

        coste_pvd = 0
        for sku, p in d['productos'].items():
            pvd = MAPA_SKU.get(sku, {}).get('pvd', 0) or 0
            coste_pvd += p['unidades'] * pvd

        reemb_ventas = sum(p['reemb_ventas'] for p in d['productos'].values()) + d['reemb_sin_sku_ventas']
        reemb_t_venta = sum(p['reemb_tarifas_venta'] for p in d['productos'].values()) + d['reemb_sin_sku_tarifas_venta']
        reemb_t_fba = sum(p['reemb_tarifas_fba'] for p in d['productos'].values()) + d['reemb_sin_sku_tarifas_fba']
        reemb_t_otras = sum(p['reemb_tarifas_otras'] for p in d['productos'].values()) + d['reemb_sin_sku_tarifas_otras']
        reembolso_perdida_neta = reemb_ventas + (reemb_t_venta + reemb_t_fba + reemb_t_otras) / IVA_GENERAL

        coste_total = coste_pvd + comision_amazon + logistica_fba + otras_tarifas + coste_almacen
        beneficio_neto = fact_sin_iva - coste_total + reembolso_perdida_neta
        margen_pct = (beneficio_neto / fact_iva * 100) if fact_iva > 0 else 0

        productos_lista = []
        for sku, p in d['productos'].items():
            if p['unidades'] == 0: continue
            pvd_p = MAPA_SKU.get(sku, {}).get('pvd', 0) or 0
            cp = p['unidades'] * pvd_p
            ca = p['unidades'] * COSTE_ALMACEN_UD
            comm_p = (-p['tarifas_venta']) / IVA_GENERAL
            log_p = (-p['tarifas_fba']) / IVA_GENERAL
            otr_p = (-p['tarifas_otras']) / IVA_GENERAL
            reemb_p = p['reemb_ventas'] + (p['reemb_tarifas_venta'] + p['reemb_tarifas_fba'] + p['reemb_tarifas_otras']) / IVA_GENERAL
            ben_p = p['facturado_sin_iva'] - cp - comm_p - log_p - otr_p - ca + reemb_p
            roi = (ben_p / cp * 100) if cp > 0 else 0
            mar = (ben_p / p['facturado_iva'] * 100) if p['facturado_iva'] > 0 else 0
            productos_lista.append({
                'sku': sku, 'asin': p['asin'], 'nombre': p['nombre'],
                'unidades': p['unidades'],
                'facturado_iva': round(p['facturado_iva'], 2),
                'facturado_sin_iva': round(p['facturado_sin_iva'], 2),
                'comision_amazon': round(comm_p, 2),
                'logistica_fba': round(log_p, 2),
                'otras_tarifas': round(otr_p, 2),
                'coste_pvd': round(cp, 2),
                'coste_almacen': round(ca, 2),
                'pvd': round(pvd_p, 4),
                'beneficio': round(ben_p, 2),
                'roi': round(roi, 1),
                'margen': round(mar, 1),
            })
        productos_lista.sort(key=lambda x: -x['beneficio'])

        meses_resumen.append({
            'mes': mes_nombre,
            'facturacion_sin_iva': round(fact_sin_iva, 2),
            'facturacion_iva': round(fact_iva, 2),
            'unidades': d['unidades'],
            'unidades_devueltas': d['unidades_devueltas'],
            'pedidos': d['pedidos'],
            'productos_distintos': len(productos_lista),
            'comision_amazon': round(comision_amazon, 2),
            'logistica_fba': round(logistica_fba, 2),
            'otras_tarifas': round(otras_tarifas, 2),
            'coste_pvd': round(coste_pvd, 2),
            'coste_almacen': round(coste_almacen, 2),
            'coste_total': round(coste_total, 2),
            'reembolso_perdida_neta': round(reembolso_perdida_neta, 2),
            'beneficio_neto': round(beneficio_neto, 2),
            'margen_pct': round(margen_pct, 1),
            'productos': productos_lista,
        })
    return meses_resumen, skus_huerfanos


def _parsear_informe_transacciones(filepath):
    """Version silenciosa del parser: devuelve (pais, registros) o (None, [])."""
    try:
        with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        cabecera_idx, cabecera = None, None
        for i, ln in enumerate(lines[:30]):
            cols = next(csv.reader([ln]))
            if len(cols) >= 15:
                norm = [_sin_acentos(c).lower().strip() for c in cols]
                if any(n in ('tipo', 'type') for n in norm):
                    cabecera_idx, cabecera = i, cols
                    break
        if cabecera_idx is None: return None, []
        cab_norm = [_sin_acentos(c).lower().strip() for c in cabecera]
        pais = _detectar_pais_trans(cab_norm)
        if not pais: return None, []
        cfg = PAISES_TRANS[pais]
        col = {canon: _col_real(cabecera, cab_norm, alias) for canon, alias in cfg['cols'].items()}
        if any(col[c] is None for c in ('fecha', 'tipo', 'sku', 'ventas')): return pais, []
        registros = []
        for t in csv.DictReader(lines[cabecera_idx+1:], fieldnames=cabecera):
            tipo_raw = _sin_acentos(t.get(col['tipo'], '') or '').lower().strip()
            tipo = cfg['tipos'].get(tipo_raw)
            if not tipo: continue
            f = parse_fecha_pais(t.get(col['fecha'], ''), pais)
            if not f: continue
            registros.append({
                'pais': pais, 'tipo': tipo, 'fecha': f,
                'sku': (t.get(col['sku'], '') or '').strip(),
                'cantidad': int(parse_num(t.get(col['cantidad'], 0)) or 0),
                'ventas': parse_num(t.get(col['ventas'], '0')),
                'impuesto': parse_num(t.get(col['impuesto'], '0')) if col['impuesto'] else 0.0,
                't_venta': parse_num(t.get(col['t_venta'], '0')) if col['t_venta'] else 0.0,
                't_fba': parse_num(t.get(col['t_fba'], '0')) if col['t_fba'] else 0.0,
                't_otras': parse_num(t.get(col['t_otras'], '0')) if col['t_otras'] else 0.0,
            })
        return pais, registros
    except Exception:
        return None, []

def _rescatar_paises_faltantes():
    """Para cada pais sin datos en el acumulador, carga su informe mas reciente
    de INPUTS/PROCESSED (mismo criterio que la celda de velocidades multipais),
    para que la rentabilidad de IT/FR no desaparezca si solo se procesa ES."""
    candidatos = {}
    for carpeta in [INPUTS, PROCESSED]:
        if not os.path.isdir(carpeta): continue
        for nombre in os.listdir(carpeta):
            ruta = os.path.join(carpeta, nombre)
            if os.path.isdir(ruta) or not nombre.lower().endswith('.csv'): continue
            try: mt = os.path.getmtime(ruta)
            except OSError: continue
            candidatos.setdefault(ruta, mt)
    por_fecha = sorted(candidatos.items(), key=lambda x: x[1])
    for ruta, _mt in por_fecha:                # ascendente: el mas reciente acaba ganando
        pais, regs = _parsear_informe_transacciones(ruta)
        if pais and regs and pais not in TRANSACCIONES_PAIS:
            TRANSACCIONES_PAIS['_rescatado_' + pais] = ruta   # marca informativa
            TRANSACCIONES_PAIS[pais] = regs
    rescatados = [k.replace('_rescatado_', '') for k in list(TRANSACCIONES_PAIS) if k.startswith('_rescatado_')]
    for k in [k for k in TRANSACCIONES_PAIS if k.startswith('_rescatado_')]:
        ruta = TRANSACCIONES_PAIS.pop(k)
        print(f"[RESCATE] {k.replace('_rescatado_','')}: usando informe previo {os.path.basename(ruta)}")

def _generar_jsons_transacciones():
    """Regenera rentabilidad.json con TODO lo acumulado en TRANSACCIONES_PAIS."""
    _rescatar_paises_faltantes()
    todos = [r for regs in TRANSACCIONES_PAIS.values() for r in regs]
    pedidos = [r for r in todos if r['tipo'] == 'Pedido']
    fecha_max = max(r['fecha'] for r in pedidos)
    fecha_min = min(r['fecha'] for r in pedidos)
    paises_cargados = sorted(TRANSACCIONES_PAIS.keys())
    print(f"\n[ACUMULADO] paises: {', '.join(paises_cargados)} | periodo: {fecha_min.date()} -> {fecha_max.date()}")

    # ========================================================
    # VELOCIDADES (total EU + por_pais)
    # ========================================================
    limite_t7 = fecha_max - timedelta(days=6)
    limite_t30 = fecha_max - timedelta(days=29)
    limite_t90 = fecha_max - timedelta(days=89)

    ven = defaultdict(lambda: defaultdict(lambda: {'t7': 0, 't30': 0, 't90': 0}))  # sku -> pais -> ventanas
    for r in pedidos:
        sku = r['sku']
        if not sku or sku not in MAPA_SKU: continue
        v = ven[sku][r['pais']]
        if r['fecha'] >= limite_t90: v['t90'] += r['cantidad']
        if r['fecha'] >= limite_t30: v['t30'] += r['cantidad']
        if r['fecha'] >= limite_t7: v['t7'] += r['cantidad']

    productos_vel = []
    for sku, info in MAPA_SKU.items():
        por_pais_sku = ven.get(sku, {})
        t7 = sum(v['t7'] for v in por_pais_sku.values())
        t30 = sum(v['t30'] for v in por_pais_sku.values())
        t90 = sum(v['t90'] for v in por_pais_sku.values())
        v_d_7 = round(t7 / 7, 2)
        v_d_30 = round(t30 / 30, 2)
        v_d_90 = round(t90 / 90, 2)

        if v_d_30 == 0:
            tendencia = 'sin_ventas'
        else:
            ratio = v_d_7 / v_d_30
            if ratio > 1.15: tendencia = 'subiendo'
            elif ratio < 0.85: tendencia = 'bajando'
            else: tendencia = 'estable'

        reg = {
            'sku': sku,
            'asin': info['asin'] or None,
            'nombre': info['nombre'],
            'proveedor': info['proveedor'],
            'pvd': info['pvd'],
            'uds_7d': t7, 'uds_30d': t30, 'uds_90d': t90,
            'vel_diaria_7d': v_d_7, 'vel_diaria_30d': v_d_30, 'vel_diaria_90d': v_d_90,
            'tendencia': tendencia
        }
        # Desglose por pais (solo paises con alguna venta del SKU; la app lo lee tal cual)
        pp = {}
        for pais, v in por_pais_sku.items():
            if v['t90'] == 0 and v['t30'] == 0 and v['t7'] == 0: continue
            pp[pais] = {
                'uds_7d': v['t7'], 'uds_30d': v['t30'], 'uds_90d': v['t90'],
                'vel_diaria_7d': round(v['t7'] / 7, 2),
                'vel_diaria_30d': round(v['t30'] / 30, 2),
            }
        if pp: reg['por_pais'] = pp
        productos_vel.append(reg)

    productos_vel.sort(key=lambda x: x['vel_diaria_30d'], reverse=True)

    # NOTA: velocidades.json NO se escribe aqui. Su dueña unica es la celda
    # "VELOCIDADES MULTI-PAIS" (mas abajo), que ya estaba en produccion y es
    # robusta cuando solo se procesa un pais (rescata el resto de processed).
    # Aqui productos_vel se calcula solo para el resumen por consola.

    # ========================================================
    # RENTABILIDAD (raiz = solo ES, retrocompatible) + por_pais + total_eu
    # ========================================================
    regs_es = TRANSACCIONES_PAIS.get('ES', [])
    meses_es, huerfanos_es = _rentabilidad_meses(regs_es) if regs_es else ([], set())
    if huerfanos_es:
        print(f"SKUs huerfanos ES (sin ficha en BD): {len(huerfanos_es)}")
        for s in sorted(huerfanos_es): print(f"  - {s}")

    por_pais_rent = {}
    for pais in ('IT', 'FR'):
        regs = TRANSACCIONES_PAIS.get(pais, [])
        if not regs: continue
        meses_p, huerf_p = _rentabilidad_meses(regs)
        fechas_p = [r['fecha'] for r in regs if r['tipo'] == 'Pedido']
        por_pais_rent[pais] = {
            'fecha_desde': min(fechas_p).strftime('%Y-%m-%d'),
            'fecha_hasta': max(fechas_p).strftime('%Y-%m-%d'),
            'meses': meses_p,
        }
        if huerf_p:
            print(f"SKUs huerfanos {pais}: {sorted(huerf_p)}")

    meses_total, _ = _rentabilidad_meses(todos)
    # El total no necesita la lista de productos por mes (pesa mucho); solo agregados
    for m in meses_total:
        m.pop('productos', None)

    # ========================================================
    # VENTA ACTUAL (solo ES; la Rotacion ES la consume)
    # ========================================================
    from statistics import median
    ventas_asin = defaultdict(list)
    for r in regs_es:
        if r['tipo'] != 'Pedido': continue
        sku = r['sku']
        if not sku or sku not in MAPA_SKU: continue
        asin = MAPA_SKU[sku].get('asin')
        if not asin: continue
        c = r['cantidad']
        if c <= 0: continue
        precio_ud = (r['ventas'] + r['impuesto']) / c
        fba_ud = (-r['t_fba'] / IVA_GENERAL / c) if r['t_fba'] != 0 else None
        com_pct = ((-r['t_venta'] / IVA_GENERAL) / (r['ventas'] + r['impuesto']) * 100) if (r['ventas'] + r['impuesto']) > 0 and r['t_venta'] != 0 else None
        ventas_asin[asin].append((r['fecha'], precio_ud, fba_ud, com_pct))

    venta_actual = {}
    for asin, lst in ventas_asin.items():
        lst.sort(key=lambda x: x[0])
        fbas = [x[2] for x in lst if x[2] is not None][-10:]
        coms = [x[3] for x in lst if x[3] is not None][-10:]
        venta_actual[asin] = {
            'precio_ultima_venta': round(lst[-1][1], 2),
            'fecha_ultima_venta': lst[-1][0].strftime('%Y-%m-%d'),
            'envio_mediana': round(median(fbas), 2) if fbas else None,
            'comision_pct_mediana': round(median(coms), 2) if coms else None,
            'n_ventas': len(lst),
        }
    print(f"OK venta_actual: {len(venta_actual)} ASINs (solo ES)")

    fechas_es = [r['fecha'] for r in regs_es if r['tipo'] == 'Pedido'] or [fecha_min, fecha_max]
    rentabilidad_json = {
        'fecha_desde': min(fechas_es).strftime('%Y-%m-%d'),
        'fecha_hasta': max(fechas_es).strftime('%Y-%m-%d'),
        'meses': meses_es,
        'venta_actual': venta_actual,
        'por_pais': por_pais_rent,
        'total_eu': {
            'fecha_desde': fecha_min.strftime('%Y-%m-%d'),
            'fecha_hasta': fecha_max.strftime('%Y-%m-%d'),
            'paises': paises_cargados,
            'meses': meses_total,
        },
    }
    out_rent = f'{OUT_JSON}/rentabilidad.json'
    with open(out_rent, 'w', encoding='utf-8') as f:
        json.dump(rentabilidad_json, f, ensure_ascii=False, separators=(',', ':'))
    print(f"OK rentabilidad.json: {os.path.getsize(out_rent)/1024:.1f} KB (ES en raiz + por_pais: {', '.join(por_pais_rent.keys()) or 'ninguno'} + total_eu)")

    # Resumen por consola
    if meses_es:
        print(f"\n=== RESUMEN MENSUAL (ES) ===")
        print(f"{'Mes':<10} {'Fact IVA':>10} {'Benef':>10} {'Margen':>7}")
        for m in meses_es:
            print(f"{m['mes']:<10} {m['facturacion_iva']:>10.2f} {m['beneficio_neto']:>10.2f} {m['margen_pct']:>6.1f}%")
    for pais, bloc in por_pais_rent.items():
        tot_f = sum(m['facturacion_iva'] for m in bloc['meses'])
        tot_b = sum(m['beneficio_neto'] for m in bloc['meses'])
        print(f"{pais}: fact {tot_f:.2f} | beneficio {tot_b:.2f} | margen {(tot_b/tot_f*100 if tot_f else 0):.1f}%")

    print(f"\n=== TOP 5 VELOCIDAD T7 (EU) ===")
    for p in sorted(productos_vel, key=lambda x: -x['uds_7d'])[:5]:
        print(f"  {p['uds_7d']:>4}u T7 | {p['uds_30d']:>4}u T30 | {p['nombre'][:50]}")

    return {
        'tipo': 'transacciones',
        'paises_acumulados': paises_cargados,
        'meses_procesados': len(meses_es),
        'productos_t30': len([p for p in productos_vel if p['uds_30d'] > 0]),
        'beneficio_total': round(sum(m['beneficio_neto'] for m in meses_es), 2),
        'facturacion_total': round(sum(m['facturacion_iva'] for m in meses_es), 2),
    }

print("Procesador transacciones MULTIPAIS cargado (ES + IT + FR).")


# ============================================================
# 4. Procesador: Inventario FBA
# ============================================================

def procesar_inventario_fba(filepath):
    print(f"\n{'='*60}")
    print(f"INVENTARIO FBA: {os.path.basename(filepath)}")
    print('='*60)

    with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    print(f"Filas: {len(rows)}")

    snapshot = None
    if rows:
        try: snapshot = rows[0].get('snapshot-date','')[:10]
        except: pass
    if snapshot: print(f"Snapshot: {snapshot}")

    actualizaciones = []
    fnsku_nuevos = []
    skus_autoasignados = []  # productos sin SKU que reciben SKU desde el informe FBA (cruce por ASIN)
    suma_fba = 0
    suma_inbound = 0

    suma_reserved = 0

    def to_int(v):
        try: return int(v or 0)
        except: return 0

    # FC Transfer: Amazon esta renombrando 'Reserved FC Transfer' -> 'fc_transfer'
    # (aviso oficial may-2026; llegara a la API a finales de 2026). Detectamos el nombre
    # real de la columna UNA vez, por varios alias, para que la suma de stock NO se quede
    # coja el dia que Amazon cambie el nombre (esas unidades son el grueso del reservado).
    _ALIAS_FC = ['Reserved FC Transfer', 'reserved_fc_transfer', 'FC Transfer',
                 'fc_transfer', 'fc-transfer', 'FC transfer']
    col_fc_transfer = next((c for c in _ALIAS_FC if rows and c in rows[0]), None)
    if col_fc_transfer:
        print(f"Columna FC Transfer detectada: '{col_fc_transfer}'")
    else:
        print("*** AVISO: no se encontro la columna de FC Transfer en el informe. ***")
        print("*** Amazon pudo renombrarla; el stock_fba puede quedarse CORTO. Revisa columnas. ***")

    for r in rows:
        sku = r.get('sku','').strip()
        fnsku = r.get('fnsku','').strip()
        available = to_int(r.get('available'))
        inbound = to_int(r.get('inbound-quantity'))
        # Reserved REAL = suma de las columnas desglosadas.
        # OJO: NO usar 'Total Reserved Quantity' -> deja fuera las unidades en transferencia
        # entre centros (FC Transfer), que SI cuentan como stock en Amazon.
        # NO usar 'Inventory Supply at FBA' -> inflaba el stock.
        # - FC Transfer: en transito entre centros logisticos Amazon
        # - FC Processing: en preparacion en el FC
        # - Customer Order: ya vendido al cliente, pendiente de envio
        # - Staging: en colocacion
        fc_transfer = to_int(r.get(col_fc_transfer)) if col_fc_transfer else 0
        reserved = (fc_transfer
                    + to_int(r.get('Reserved FC Processing'))
                    + to_int(r.get('Reserved Customer Order'))
                    + to_int(r.get('Reserved Staging')))

        # stock_fba = todo lo que esta DENTRO de Amazon = disponible + reservado (todas las fases).
        # Validado vs ficha del Seller: funda 25+81=106, Gohan 39+0=39. Inbound (de camino) va aparte.
        stock_fba_final = available + reserved

        # Si no tiene SKU, descartamos (no podemos hacer nada)
        if not sku: continue

        # Si SKU no esta en MAPA_SKU, intentar autoasignacion por ASIN
        if sku not in MAPA_SKU:
            asin = (r.get('asin') or '').strip()
            if asin and asin in MAPA_ASIN_SIN_SKU:
                # Encontramos producto sin SKU cuyo ASIN coincide: autoasignar SKU
                info = MAPA_ASIN_SIN_SKU[asin]
                skus_autoasignados.append({
                    'sku': sku, 'asin': asin, 'id_producto': info['id'],
                    'nombre': info['nombre']
                })
                # Anyadirlo dinamicamente a MAPA_SKU para que siga el flujo normal
                MAPA_SKU[sku] = {
                    'id': info['id'],
                    'asin': asin,
                    'ean': info.get('ean'),
                    'fnsku': None,  # se rellenara abajo si el informe trae fnsku
                    'nombre': info['nombre'],
                    'proveedor': info['proveedor'],
                    'pvd': info['pvd'],
                    'marca': info['marca'],
                    'activo': True,
                    'estado': info['estado']
                }
                # Quitar del mapa de "sin SKU" para que no se autoasigne dos veces
                del MAPA_ASIN_SIN_SKU[asin]
            else:
                # No esta en MAPA_SKU ni se puede recuperar por ASIN: descartar
                continue

        actualizaciones.append({
            'sku': sku, 'fnsku': fnsku,
            'available': available,
            'reserved': reserved,
            'stock_fba_final': stock_fba_final,
            'inbound': inbound,
            'nombre': MAPA_SKU[sku]['nombre']
        })
        suma_fba += stock_fba_final
        suma_reserved += reserved
        suma_inbound += inbound

        if fnsku and not MAPA_SKU[sku].get('fnsku'):
            fnsku_nuevos.append((sku, fnsku))

    print(f"Productos cruzados: {len(actualizaciones)}")
    print(f"Stock FBA total: {suma_fba}u (incluye {suma_reserved}u reservadas)  |  Inbound: {suma_inbound}u")
    if skus_autoasignados:
        print(f"\n*** {len(skus_autoasignados)} SKUs AUTOASIGNADOS por ASIN ***")
        for s in skus_autoasignados[:10]:
            print(f"  + {s['sku']} -> ASIN {s['asin']} -> {s['nombre'][:60]}")
        if len(skus_autoasignados) > 10:
            print(f"  ... y {len(skus_autoasignados)-10} mas")

    sql_lines = [
        f"-- Sincronizacion stock FBA + inbound desde informe Amazon",
        f"-- Snapshot: {snapshot}",
        f"-- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"-- Productos: {len(actualizaciones)}",
        f"-- Total FBA: {suma_fba}u (incluye {suma_reserved}u reservadas) | Inbound: {suma_inbound}u",
        f"-- SKUs autoasignados por ASIN: {len(skus_autoasignados)}",
        "",
    ]
    if skus_autoasignados:
        sql_lines.append("-- Autoasignacion de SKU a productos sin SKU (cruce por ASIN del informe FBA)")
        for s in skus_autoasignados:
            sku_esc = s['sku'].replace("'", "''")
            asin_esc = s['asin'].replace("'", "''")
            nombre = (s['nombre'] or '')[:50].replace("'", "''")
            sql_lines.append(
                f"UPDATE productos SET sku = '{sku_esc}', updated_at = NOW() "
                f"WHERE id = '{s['id_producto']}' AND (sku IS NULL OR sku = '') AND activo = true; -- {nombre}"
            )
        sql_lines.append("")
    sql_lines.extend([
        "-- (Reset por ausencia ELIMINADO 6-jun: este informe FBA a veces omite productos SANOS",
        "--  -> ponerlos a 0 rompia su stock_fba (caso Anxiety/Gohan). Los agotados de verdad",
        "--  ya vienen en el informe con available=0, asi que sus UPDATE ya los dejan en 0.",
        "--  Solo se actualizan los productos PRESENTES en el informe; los ausentes no se tocan.)",
        "-- Actualizar productos del informe",
    ])

    for a in actualizaciones:
        sku_esc = a['sku'].replace("'", "''")
        nombre = (a['nombre'] or '')[:50].replace("'", "''")
        # stock_fba_final = available + reserved (todas las fases). Validado vs ficha Seller.
        comentario_reserved = f" [+{a['reserved']}res]" if a['reserved'] > 0 else ""
        sql_lines.append(
            f"UPDATE productos SET stock_fba = {a['stock_fba_final']}, stock_inbound = {a['inbound']} "
            f"WHERE sku = '{sku_esc}' AND activo = true; -- {nombre}{comentario_reserved}"
        )

    if fnsku_nuevos:
        sql_lines.append("")
        sql_lines.append(f"-- {len(fnsku_nuevos)} productos sin FNSKU en BD (rellenar):")
        for sku, fnsku in fnsku_nuevos:
            sku_esc = sku.replace("'", "''")
            sql_lines.append(f"UPDATE productos SET fnsku = '{fnsku}' WHERE sku = '{sku_esc}' AND activo = true;")

    sql_lines.extend([
        "",
        "-- Verificacion",
        "SELECT COUNT(*) AS productos_actualizados, SUM(stock_fba) AS total_fba, SUM(stock_inbound) AS total_inbound",
        "FROM productos WHERE activo = true AND (stock_fba > 0 OR stock_inbound > 0);"
    ])

    out_sql = f'{OUT_SQL}/update_stocks_{TIMESTAMP}.sql'
    with open(out_sql, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_lines))
    print(f"OK SQL: {out_sql}")

    return {
        'tipo': 'inventario_fba',
        'archivo': os.path.basename(filepath),
        'filas_leidas': len(rows),
        'productos_actualizados': len(actualizaciones),
        'skus_autoasignados': len(skus_autoasignados),
        'total_fba': suma_fba,
        'total_reserved': suma_reserved,
        'total_inbound': suma_inbound,
        'snapshot_date': snapshot,
        'sql_output': out_sql
    }

print("Procesador FBA cargado.")

# ============================================================
# 4.5 Procesadores: Devoluciones (4 tipos)
# ============================================================

# ============================================================
# PROCESADORES DE DEVOLUCIONES (4 tipos)
# Insertan filas en tabla devoluciones de Supabase con UPSERT idempotente.
# Decision 12-may: importe_eur SIN IVA (Amazon paga indemnizacion neta).
# ============================================================

def _to_int(v):
    try: return int((v or '').strip() or 0)
    except: return 0

def _to_float(v):
    try: return float((v or '').strip() or 0)
    except: return 0.0

def _norm_str(v):
    """Devuelve string limpio o None."""
    if v is None: return None
    s = str(v).strip()
    return s if s else None

def _leer_devol(filepath):
    """Lee un informe de devoluciones detectando el separador (tab o coma).
    Los .txt de FBA van por TAB; si algun dia llegan en CSV (coma), tambien."""
    with open(filepath, encoding='utf-8-sig') as f:
        muestra = f.readline()
        f.seek(0)
        sep = '\t' if muestra.count('\t') >= muestra.count(',') else ','
        return list(csv.DictReader(f, delimiter=sep))

def _resolver_producto(sku, asin=None):
    """Devuelve (producto_id, marca, nombre_bd) desde MAPA_SKU o None si no matchea."""
    if sku and sku in MAPA_SKU:
        p = MAPA_SKU[sku]
        return (p['id'], p.get('marca'), p.get('nombre'))
    # Fallback por ASIN si SKU no matchea
    if asin:
        for sku2, p in MAPA_SKU.items():
            if p.get('asin') == asin:
                return (p['id'], p.get('marca'), p.get('nombre'))
    return (None, None, None)

def _upsert_devoluciones(filas, label):
    """Inserta filas en bloque con on_conflict (idempotente).

    La tabla tiene CONSTRAINT devoluciones_dedup UNIQUE NULLS NOT DISTINCT
    sobre (tipo, fecha, sku, order_id, reimbursement_id, importe_eur).
    Usamos on_conflict='devoluciones_dedup' para evitar duplicar al reprocesar.
    """
    if not filas:
        print(f"  {label}: 0 filas a insertar")
        return 0, 0
    insertadas = 0
    duplicadas = 0
    # Insertar en bloques de 200 (Supabase tiene limite)
    BLOQUE = 200
    for i in range(0, len(filas), BLOQUE):
        bloque = filas[i:i+BLOQUE]
        try:
            r = sb.table('devoluciones').upsert(
                bloque,
                on_conflict='tipo,fecha,sku,order_id,reimbursement_id,importe_eur,lpn',
                ignore_duplicates=True
            ).execute()
            n = len(r.data) if r.data else 0
            insertadas += n
            duplicadas += (len(bloque) - n)
        except Exception as e:
            print(f"  ERROR bloque {i//BLOQUE}: {e}")
    print(f"  {label}: {insertadas} insertadas / {duplicadas} ya existian (idempotencia)")
    return insertadas, duplicadas


# ----------------------------------------------------------------------------
# 1) CUSTOMER RETURNS - devoluciones de clientes
# ----------------------------------------------------------------------------
def procesar_customer_returns(filepath):
    print(f"\n{'='*60}")
    print(f"CUSTOMER RETURNS: {os.path.basename(filepath)}")
    print('='*60)

    rows = _leer_devol(filepath)
    print(f"Filas leidas: {len(rows)}")

    filas_a_insertar = []
    sin_match = 0
    fechas = []
    disposition_counter = defaultdict(int)

    for r in rows:
        sku   = _norm_str(r.get('sku'))
        asin  = _norm_str(r.get('asin'))
        fnsku = _norm_str(r.get('fnsku'))
        fecha = _norm_str(r.get('return-date'))
        if not fecha:
            continue
        fechas.append(fecha[:10])

        cantidad = _to_int(r.get('quantity'))
        disposition = _norm_str(r.get('detailed-disposition'))
        reason = _norm_str(r.get('reason'))
        order_id = _norm_str(r.get('order-id'))
        status = _norm_str(r.get('status'))

        lpn = _norm_str(r.get('license-plate-number'))

        producto_id, _, _ = _resolver_producto(sku, asin)
        if not producto_id: sin_match += 1
        disposition_counter[disposition or 'NULL'] += 1

        filas_a_insertar.append({
            'tipo': 'customer_return',
            'fecha': fecha,
            'producto_id': producto_id,
            'sku': sku,
            'asin': asin,
            'fnsku': fnsku,
            'cantidad': cantidad,
            'disposition': disposition,
            'reason': reason,
            'estado': status,
            'order_id': order_id,
            'lpn': lpn,
            'raw_data': r,
        })

    print(f"Productos sin matchear (huerfanos): {sin_match}")
    print(f"Dispositions: {dict(disposition_counter)}")

    insertadas, duplicadas = _upsert_devoluciones(filas_a_insertar, 'customer_returns')

    return {
        'filas_leidas': len(rows),
        'filas_validas': len(filas_a_insertar),
        'insertadas': insertadas,
        'duplicadas_ignoradas': duplicadas,
        'sin_matchear': sin_match,
        'dispositions': dict(disposition_counter),
        'fecha_desde': min(fechas) if fechas else None,
        'fecha_hasta': max(fechas) if fechas else None,
    }


# ----------------------------------------------------------------------------
# 2) REMOVAL ORDERS - solicitudes de retirada de inventario FBA
# ----------------------------------------------------------------------------
def procesar_removal_orders(filepath):
    print(f"\n{'='*60}")
    print(f"REMOVAL ORDERS: {os.path.basename(filepath)}")
    print('='*60)

    rows = _leer_devol(filepath)
    print(f"Filas leidas: {len(rows)}")

    filas_a_insertar = []
    sin_match = 0
    fechas = []
    estados = defaultdict(int)

    for r in rows:
        sku   = _norm_str(r.get('sku'))
        fnsku = _norm_str(r.get('fnsku'))
        fecha = _norm_str(r.get('request-date'))
        if not fecha:
            continue
        fechas.append(fecha[:10])

        requested = _to_int(r.get('requested-quantity'))
        cancelled = _to_int(r.get('cancelled-quantity'))
        shipped   = _to_int(r.get('shipped-quantity'))
        in_proc   = _to_int(r.get('in-process-quantity'))
        disposed  = _to_int(r.get('disposed-quantity'))

        # cantidad efectiva = lo realmente en juego (no cancelado)
        cantidad = max(requested - cancelled, shipped + in_proc + disposed)

        disposition = _norm_str(r.get('disposition'))
        order_id = _norm_str(r.get('order-id'))
        estado = _norm_str(r.get('order-status'))

        producto_id, _, _ = _resolver_producto(sku)
        if not producto_id: sin_match += 1
        estados[estado or 'NULL'] += 1

        filas_a_insertar.append({
            'tipo': 'removal_order',
            'fecha': fecha,
            'producto_id': producto_id,
            'sku': sku,
            'fnsku': fnsku,
            'cantidad': cantidad,
            'disposition': disposition,
            'estado': estado,
            'order_id': order_id,
            'raw_data': r,
        })

    print(f"Productos sin matchear: {sin_match}")
    print(f"Estados: {dict(estados)}")

    insertadas, duplicadas = _upsert_devoluciones(filas_a_insertar, 'removal_orders')

    return {
        'filas_leidas': len(rows),
        'filas_validas': len(filas_a_insertar),
        'insertadas': insertadas,
        'duplicadas_ignoradas': duplicadas,
        'sin_matchear': sin_match,
        'estados': dict(estados),
        'fecha_desde': min(fechas) if fechas else None,
        'fecha_hasta': max(fechas) if fechas else None,
    }


# ----------------------------------------------------------------------------
# 3) REMOVAL SHIPMENTS - envios fisicos de retirada (Amazon te devuelve producto)
# ----------------------------------------------------------------------------
def procesar_removal_shipments(filepath):
    print(f"\n{'='*60}")
    print(f"REMOVAL SHIPMENTS: {os.path.basename(filepath)}")
    print('='*60)

    rows = _leer_devol(filepath)
    print(f"Filas leidas: {len(rows)}")

    filas_a_insertar = []
    sin_match = 0
    fechas = []

    for r in rows:
        sku   = _norm_str(r.get('sku'))
        fnsku = _norm_str(r.get('fnsku'))
        # shipment-date prioritario, fallback request-date
        fecha = _norm_str(r.get('shipment-date')) or _norm_str(r.get('request-date'))
        if not fecha:
            continue
        fechas.append(fecha[:10])

        cantidad = _to_int(r.get('shipped-quantity'))
        disposition = _norm_str(r.get('disposition'))
        order_id = _norm_str(r.get('order-id'))
        tracking = _norm_str(r.get('tracking-number'))

        producto_id, _, _ = _resolver_producto(sku)
        if not producto_id: sin_match += 1

        filas_a_insertar.append({
            'tipo': 'removal_shipment',
            'fecha': fecha,
            'producto_id': producto_id,
            'sku': sku,
            'fnsku': fnsku,
            'cantidad': cantidad,
            'disposition': disposition,
            'order_id': order_id,
            'tracking_number': tracking,
            'raw_data': r,
        })

    print(f"Productos sin matchear: {sin_match}")

    insertadas, duplicadas = _upsert_devoluciones(filas_a_insertar, 'removal_shipments')

    return {
        'filas_leidas': len(rows),
        'filas_validas': len(filas_a_insertar),
        'insertadas': insertadas,
        'duplicadas_ignoradas': duplicadas,
        'sin_matchear': sin_match,
        'fecha_desde': min(fechas) if fechas else None,
        'fecha_hasta': max(fechas) if fechas else None,
    }


# ----------------------------------------------------------------------------
# 4) REIMBURSEMENTS - reembolsos economicos que te paga Amazon
# ----------------------------------------------------------------------------
def procesar_reimbursements(filepath):
    print(f"\n{'='*60}")
    print(f"REIMBURSEMENTS: {os.path.basename(filepath)}")
    print('='*60)

    rows = _leer_devol(filepath)
    print(f"Filas leidas: {len(rows)}")

    filas_a_insertar = []
    sin_match = 0
    fechas = []
    reasons = defaultdict(lambda: {'lineas':0, 'eur':0.0, 'uds':0})
    total_eur = 0.0
    total_uds = 0

    for r in rows:
        sku   = _norm_str(r.get('sku'))
        asin  = _norm_str(r.get('asin'))
        fnsku = _norm_str(r.get('fnsku'))
        fecha = _norm_str(r.get('approval-date'))
        if not fecha:
            continue
        fechas.append(fecha[:10])

        cantidad = _to_int(r.get('quantity-reimbursed-total'))
        importe = _to_float(r.get('amount-total'))
        # Amazon paga SIN IVA (decision Fernando 12-may). Lo guardamos tal cual.
        moneda = _norm_str(r.get('currency-unit'))
        if moneda and moneda != 'EUR':
            print(f"  AVISO: moneda no-EUR detectada ({moneda}) en reimbursement {r.get('reimbursement-id')}")

        reason = _norm_str(r.get('reason'))
        reimb_id = _norm_str(r.get('reimbursement-id'))
        order_id = _norm_str(r.get('amazon-order-id'))

        producto_id, _, _ = _resolver_producto(sku, asin)
        if not producto_id: sin_match += 1

        if reason:
            reasons[reason]['lineas'] += 1
            reasons[reason]['eur'] += importe
            reasons[reason]['uds'] += cantidad
        total_eur += importe
        total_uds += cantidad

        filas_a_insertar.append({
            'tipo': 'reimbursement',
            'fecha': fecha,
            'producto_id': producto_id,
            'sku': sku,
            'asin': asin,
            'fnsku': fnsku,
            'cantidad': cantidad,
            'reason': reason,
            'reimbursement_reason': reason,
            'importe_eur': round(importe, 2),
            'reimbursement_id': reimb_id,
            'order_id': order_id,
            'raw_data': r,
        })

    print(f"Productos sin matchear: {sin_match}")
    print(f"Total reembolsado: {total_eur:.2f} EUR ({total_uds}u)")
    print(f"Por motivo:")
    for reason, d in sorted(reasons.items(), key=lambda x: -x[1]['eur']):
        print(f"  {reason}: {d['lineas']} lineas, {d['uds']}u, {d['eur']:.2f} EUR")

    insertadas, duplicadas = _upsert_devoluciones(filas_a_insertar, 'reimbursements')

    return {
        'filas_leidas': len(rows),
        'filas_validas': len(filas_a_insertar),
        'insertadas': insertadas,
        'duplicadas_ignoradas': duplicadas,
        'sin_matchear': sin_match,
        'total_eur': round(total_eur, 2),
        'total_uds': total_uds,
        'por_motivo': {k: {'lineas': v['lineas'], 'uds': v['uds'], 'eur': round(v['eur'],2)} for k,v in reasons.items()},
        'fecha_desde': min(fechas) if fechas else None,
        'fecha_hasta': max(fechas) if fechas else None,
    }


# ============================================================
# 5. Procesar todo
# ============================================================

PROCESADORES = {
    'transacciones': procesar_transacciones,
    'inventario_fba': procesar_inventario_fba,
    'customer_returns': procesar_customer_returns,
    'removal_orders': procesar_removal_orders,
    'removal_shipments': procesar_removal_shipments,
    'reimbursements': procesar_reimbursements,
}

print("="*60)
print("EJECUTANDO PROCESADORES")
print("="*60)

resultados = []
for filepath, tipo in archivos_detectados.items():
    proc = PROCESADORES.get(tipo)
    if not proc:
        print(f"\nProcesador para '{tipo}' no implementado. Saltando {filepath}")
        continue
    try:
        resumen = proc(filepath)
        if resumen: resultados.append((filepath, tipo, resumen))
    except Exception as e:
        print(f"\nERROR procesando {filepath}: {e}")
        import traceback
        traceback.print_exc()

# ============================================================
# AUDIT TRAIL Y MOVER ARCHIVOS
# ============================================================
print("\n" + "="*60)
print("REGISTRO AUDIT Y MOVIMIENTO DE ARCHIVOS")
print("="*60)

for filepath, tipo, resumen in resultados:
    nombre = os.path.basename(filepath)
    try:
        registro = {
            'tipo': tipo,
            'archivo_nombre': nombre,
            'filas_procesadas': resumen.get('filas_leidas', 0),
            'filas_validas': resumen.get('filas_validas', resumen.get('filas_leidas', 0)),
            'fecha_dato_desde': resumen.get('fecha_desde') or resumen.get('snapshot_date'),
            'fecha_dato_hasta': resumen.get('fecha_hasta') or resumen.get('snapshot_date'),
            'resumen_json': resumen,
        }
        sb.table('informes_subidos').insert(registro).execute()
        print(f"OK Audit: {nombre}")
    except Exception as e:
        print(f"WARN audit {nombre}: {e}")

    nombre_base, ext = os.path.splitext(nombre)
    nuevo_nombre = f"{nombre_base}__{TIMESTAMP}{ext}"
    destino = os.path.join(PROCESSED, nuevo_nombre)
    try:
        shutil.move(filepath, destino)
        print(f"  -> processed/{nuevo_nombre}")
    except Exception as e:
        print(f"  WARN: {e}")

# ============================================================
# RESUMEN FINAL
# ============================================================
print("\n" + "="*60)
print("PROCESO COMPLETO")
print("="*60)

print(f"\nArchivos en {OUT_JSON}/:")
for f in sorted(os.listdir(OUT_JSON)):
    sz = os.path.getsize(os.path.join(OUT_JSON, f)) / 1024
    print(f"   {f} ({sz:.1f} KB)")

print(f"\nUltimos SQL en {OUT_SQL}/:")
sqls = sorted([f for f in os.listdir(OUT_SQL) if f.endswith('.sql')])
for f in sqls[-3:]:
    sz = os.path.getsize(os.path.join(OUT_SQL, f)) / 1024
    print(f"   {f} ({sz:.1f} KB)")

print("\nPROXIMOS PASOS:")
print(f"  1. Bajar JSONs de {OUT_JSON}/ y subirlos a GitHub")
print(f"  2. Pegar SQL mas reciente en Supabase -> SQL Editor")
print(f"  3. Hard reload (Ctrl+Shift+R) en moloka-app.vercel.app")


# ============================================================
# VELOCIDADES MULTI-PAIS (ES + IT + FR)  [añadido jun-2026]
# Recalcula velocidades.json sumando ventas de los 3 marketplaces.
# NO toca rentabilidad.json (ese sigue solo-ES hasta resolver IVA por pais).
# Busca los informes de transacciones (en cualquier idioma) en INPUTS y PROCESSED.
# ============================================================

# Meses en los 3 idiomas -> numero
_MESES_MULTI = {
 'ene':1,'gen':1,'jan':1,'janv':1,
 'feb':2,'fév':2,'fevr':2,'févr':2,
 'mar':3,'mars':3,
 'abr':4,'apr':4,'avr':4,
 'may':5,'mag':5,'mai':5,
 'jun':6,'giu':6,'juin':6,
 'jul':7,'lug':7,'juil':7,
 'ago':8,'aug':8,'aout':8,'août':8,
 'sep':9,'set':9,'sept':9,
 'oct':10,'ott':10,
 'nov':11,
 'dic':12,'dec':12,'déc':12,'dez':12,
}
_TIPOS_PEDIDO = {'pedido','ordine','commande'}

def _parse_fecha_multi(s):
    if not s: return None
    m = re.match(r'(\d+)\s+([^\s]+)\s+(\d{4})', str(s).strip())
    if not m: return None
    dia, mes, ano = m.groups()
    mm = _MESES_MULTI.get(mes.lower()[:4]) or _MESES_MULTI.get(mes.lower()[:3])
    if not mm: return None
    return datetime(int(ano), mm, int(dia))

def _cols_transacciones(cabecera):
    low = [c.strip().lower() for c in cabecera]
    def b(opts):
        for o in opts:
            if o in low: return cabecera[low.index(o)]
        return None
    return {
        'tipo': b(['tipo','type']),
        'sku': b(['sku']),
        'cant': b(['cantidad','quantità','quantita','quantité','quantite']),
        'fecha': b(['fecha y hora','data/ora:','data/ora','date/heure']),
    }

def _es_informe_transacciones(filepath):
    """Devuelve idioma ('ES'/'IT'/'FR') si el archivo es un informe de transacciones, o None."""
    try:
        with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
            cab = '\n'.join(f.readline() for _ in range(20)).lower()
    except Exception:
        return None
    if 'ventas de productos' in cab: return 'ES'
    if 'vendite' in cab or 'quantità' in cab: return 'IT'
    if 'ventes des produits' in cab or 'ventes' in cab or 'quantité' in cab: return 'FR'
    return None

def _leer_pedidos(filepath):
    with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
        lines = f.readlines()
    cab_idx = None
    for i, ln in enumerate(lines[:30]):
        l = ln.lower()
        if ('tipo' in l or 'type' in l) and 'sku' in l:
            cab_idx = i; break
    if cab_idx is None: return []
    cabecera = next(csv.reader([lines[cab_idx]]))
    cols = _cols_transacciones(cabecera)
    if not all([cols['tipo'], cols['sku'], cols['cant'], cols['fecha']]):
        return []
    pedidos = []
    for t in csv.DictReader(lines[cab_idx+1:], fieldnames=cabecera):
        if str(t.get(cols['tipo'],'')).strip().lower() not in _TIPOS_PEDIDO: continue
        f = _parse_fecha_multi(t.get(cols['fecha'],''))
        sku = str(t.get(cols['sku'],'')).strip()
        try: cant = int(float(str(t.get(cols['cant'],'0') or '0').replace(',','.')))
        except: cant = 0
        if f and sku: pedidos.append((f, sku, cant))
    return pedidos

def recalcular_velocidades_multipais():
    print("\n" + "="*60)
    print("VELOCIDADES MULTI-PAIS (ES + IT + FR)")
    print("="*60)

    # Buscar el informe de transacciones mas reciente de CADA idioma, en INPUTS y PROCESSED
    candidatos = {}  # idioma -> (mtime, ruta)
    for carpeta in [INPUTS, PROCESSED]:
        if not os.path.isdir(carpeta): continue
        for nombre in os.listdir(carpeta):
            ruta = os.path.join(carpeta, nombre)
            if os.path.isdir(ruta) or nombre.startswith('.'): continue
            if not nombre.lower().endswith('.csv'): continue
            idioma = _es_informe_transacciones(ruta)
            if not idioma: continue
            mt = os.path.getmtime(ruta)
            if idioma not in candidatos or mt > candidatos[idioma][0]:
                candidatos[idioma] = (mt, ruta)

    if not candidatos:
        print("No se encontraron informes de transacciones. (Sin cambios en velocidades.json)")
        return

    print("Informes encontrados:")
    todos = []
    for idioma, (mt, ruta) in candidatos.items():
        peds = _leer_pedidos(ruta)
        uds = sum(p[2] for p in peds)
        print(f"  {idioma}: {os.path.basename(ruta)} -> {len(peds)} pedidos, {uds} uds")
        todos += [(idioma,) + p for p in peds]

    if 'ES' not in candidatos:
        print("AVISO: no hay informe de ESPANA. Revisa los archivos antes de subir el JSON.")
    for falta in ('IT','FR'):
        if falta not in candidatos:
            print(f"AVISO: no se encontro informe de {falta}. Velocidades sin ese pais.")

    if not todos:
        print("No hay pedidos. Sin cambios.")
        return

    fecha_max = max(p[1] for p in todos)
    l7  = fecha_max - timedelta(days=6)
    l30 = fecha_max - timedelta(days=29)
    l90 = fecha_max - timedelta(days=89)

    # Acumular TOTAL (para alertas) y POR PAIS (para pestanas Rotacion IT/FR + total en ES)
    v7  = defaultdict(int); v30 = defaultdict(int); v90 = defaultdict(int)
    p7  = defaultdict(int); p30 = defaultdict(int); p90 = defaultdict(int)  # clave (pais, sku)
    for idioma, f, sku, cant in todos:
        if sku not in MAPA_SKU: continue
        if f >= l90: v90[sku]+=cant; p90[(idioma,sku)]+=cant
        if f >= l30: v30[sku]+=cant; p30[(idioma,sku)]+=cant
        if f >= l7:  v7[sku] +=cant; p7[(idioma,sku)] +=cant

    PAISES = sorted(candidatos.keys())   # los paises realmente presentes (ES/IT/FR)

    productos_vel = []
    for sku, info in MAPA_SKU.items():
        t7, t30, t90 = v7.get(sku,0), v30.get(sku,0), v90.get(sku,0)
        vd7, vd30, vd90 = round(t7/7,2), round(t30/30,2), round(t90/90,2)
        if vd30 == 0:
            tendencia = 'sin_ventas'
        else:
            r = vd7/vd30
            tendencia = 'subiendo' if r>1.15 else ('bajando' if r<0.85 else 'estable')
        # Desglose por pais (uds y velocidad de CADA mercado por separado)
        por_pais = {}
        for pais in PAISES:
            e7  = p7.get((pais,sku),0)
            e30 = p30.get((pais,sku),0)
            e90 = p90.get((pais,sku),0)
            por_pais[pais] = {
                'uds_7d': e7, 'uds_30d': e30, 'uds_90d': e90,
                'vel_diaria_7d': round(e7/7,2),
                'vel_diaria_30d': round(e30/30,2),
                'vel_diaria_90d': round(e90/90,2),
            }
        productos_vel.append({
            'sku': sku, 'asin': info['asin'] or None, 'nombre': info['nombre'],
            'proveedor': info['proveedor'], 'pvd': info['pvd'],
            # TOTAL Europa (lo que usan las alertas; NO cambia)
            'uds_7d': t7, 'uds_30d': t30, 'uds_90d': t90,
            'vel_diaria_7d': vd7, 'vel_diaria_30d': vd30, 'vel_diaria_90d': vd90,
            'tendencia': tendencia,
            # Desglose por mercado (para las pestanas de Rotacion)
            'por_pais': por_pais,
        })
    productos_vel.sort(key=lambda x: x['vel_diaria_30d'], reverse=True)

    velocidades_json = {
        'fecha_calculo': fecha_max.strftime('%Y-%m-%d'),
        'paises_incluidos': sorted(candidatos.keys()),
        'ventana_t7_desde': l7.strftime('%Y-%m-%d'),
        'ventana_t30_desde': l30.strftime('%Y-%m-%d'),
        'ventana_t90_desde': l90.strftime('%Y-%m-%d'),
        'total_productos': len(productos_vel),
        'productos': productos_vel,
    }
    out_vel = f'{OUT_JSON}/velocidades.json'
    with open(out_vel, 'w', encoding='utf-8') as f:
        json.dump(velocidades_json, f, ensure_ascii=False, separators=(',',':'))
    print(f"\nOK velocidades.json RECALCULADO con {sorted(candidatos.keys())}: {os.path.getsize(out_vel)/1024:.1f} KB")
    print("TOP 5 velocidad T7 (multipais):")
    for p in sorted(productos_vel, key=lambda x: -x['uds_7d'])[:5]:
        print(f"  {p['uds_7d']:>4}u T7 | {p['uds_30d']:>4}u T30 | {p['nombre'][:50]}")

recalcular_velocidades_multipais()


# ============================================================
# 6. Cruce Rentabilidad x Devoluciones
# ============================================================

# ============================================================
# 6. CRUCE RENTABILIDAD x DEVOLUCIONES
# ============================================================
# Aplica los 3 escenarios contables del briefing (sec 3.7) al
# rentabilidad.json ya generado, leyendo datos reales de la tabla
# devoluciones de Supabase.
#
# Escenarios:
#   1. SELLABLE: producto vuelve a stock vendible
#      Ajuste = uds_sellable × PVD (recupera coste imputado en caja)
#
#   2. DEFECTIVE + CUSTOMER_DAMAGED: revender 2a mano al 50%
#      Ajuste = uds_dañadas × PVD × 0.5
#
#   3. CARRIER_DAMAGED + reimbursements Amazon (cash only):
#      Ajuste = SUM(importe_eur) cuando quantity-reimbursed-cash > 0
#
# El JSON original (beneficio_neto = criterio caja) se mantiene intacto.
# Se añaden 5 campos nuevos por mes:
#   - ajuste_sellable
#   - ajuste_segunda_mano
#   - ajuste_amazon
#   - ajuste_total_devoluciones
#   - beneficio_neto_real
#   - margen_real_pct
# ============================================================

print("="*60)
print("CRUCE RENTABILIDAD x DEVOLUCIONES")
print("="*60)

# Cargar rentabilidad.json ya generado
out_rent = f'{OUT_JSON}/rentabilidad.json'
if not os.path.exists(out_rent):
    print(f"AVISO: {out_rent} no existe, no se hizo cruce (procesa transacciones primero)")
else:
    with open(out_rent, 'r', encoding='utf-8') as f:
        rent = json.load(f)

    fecha_desde = rent['fecha_desde']
    fecha_hasta = rent['fecha_hasta']
    print(f"Periodo del JSON: {fecha_desde} -> {fecha_hasta}")

    # ----------------------------------------------------------
    # Leer devoluciones de Supabase en el periodo del JSON
    # ----------------------------------------------------------
    print(f"\nLeyendo tabla devoluciones desde Supabase...")
    todas_devs = []
    desde = 0
    PAGE = 1000
    while True:
        r = sb.table('devoluciones').select(
            'tipo, fecha, sku, producto_id, cantidad, disposition, importe_eur, raw_data'
        ).gte('fecha', fecha_desde).lte('fecha', fecha_hasta + 'T23:59:59+00:00').range(desde, desde + PAGE - 1).execute()
        if not r.data: break
        todas_devs.extend(r.data)
        if len(r.data) < PAGE: break
        desde += PAGE

    print(f"Devoluciones cargadas: {len(todas_devs)}")

    # ----------------------------------------------------------
    # Clasificar y agregar por mes
    # ----------------------------------------------------------
    # Estructura: ajustes_mes[mes_key] = {
    #     'sellable_uds_pvd': float (sum de uds * PVD)
    #     'segunda_mano_uds_pvd': float (sum de uds * PVD)
    #     'amazon_cash': float (sum de importe_eur de cash > 0)
    # }
    ajustes_mes = defaultdict(lambda: {
        'sellable_uds_pvd': 0.0,
        'segunda_mano_uds_pvd': 0.0,
        'amazon_cash': 0.0,
        # Contadores para reporte
        'sellable_uds': 0, 'segunda_mano_uds': 0, 'amazon_lineas': 0, 'amazon_uds': 0,
    })

    # Mapa SKU -> PVD para lookup rapido (MAPA_SKU ya esta cargado de celda 2)
    def get_pvd(sku):
        if sku and sku in MAPA_SKU:
            return float(MAPA_SKU[sku].get('pvd') or 0)
        return 0.0

    def mes_key_de(fecha_iso):
        """Convierte '2026-03-25T14:50:40+00:00' a 'marzo'."""
        try:
            dt = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
            return MESES_NOMBRE[dt.month - 1]
        except:
            return None

    sin_pvd = []  # productos sin PVD que no podemos ajustar

    for dev in todas_devs:
        mes = mes_key_de(dev['fecha'])
        if not mes: continue
        sku = dev.get('sku')

        if dev['tipo'] == 'customer_return':
            disp = dev.get('disposition')
            uds = int(dev.get('cantidad') or 0)
            pvd = get_pvd(sku)

            if disp == 'SELLABLE':
                if pvd > 0:
                    ajustes_mes[mes]['sellable_uds_pvd'] += uds * pvd
                    ajustes_mes[mes]['sellable_uds'] += uds
                elif sku:
                    sin_pvd.append(sku)
            elif disp in ('DEFECTIVE', 'CUSTOMER_DAMAGED'):
                if pvd > 0:
                    ajustes_mes[mes]['segunda_mano_uds_pvd'] += uds * pvd * 0.5
                    ajustes_mes[mes]['segunda_mano_uds'] += uds
                elif sku:
                    sin_pvd.append(sku)
            # CARRIER_DAMAGED no genera ajuste aqui (se cubre via reimbursement Amazon)

        elif dev['tipo'] == 'reimbursement':
            # Solo cash: leer raw_data para mirar quantity-reimbursed-cash
            raw = dev.get('raw_data') or {}
            try:
                cash_qty = int((raw.get('quantity-reimbursed-cash') or '0').strip() or 0)
            except:
                cash_qty = 0

            if cash_qty > 0:
                # Tomar el importe total (Amazon paga toda la linea junta, lo de cash es solo info)
                importe = float(dev.get('importe_eur') or 0)
                ajustes_mes[mes]['amazon_cash'] += importe
                ajustes_mes[mes]['amazon_lineas'] += 1
                ajustes_mes[mes]['amazon_uds'] += cash_qty

    if sin_pvd:
        sin_pvd_unique = sorted(set(sin_pvd))
        print(f"\nProductos sin PVD (no se pueden ajustar): {len(sin_pvd_unique)}")
        for s in sin_pvd_unique[:10]:
            print(f"  - {s}")
        if len(sin_pvd_unique) > 10:
            print(f"  ... y {len(sin_pvd_unique) - 10} mas")

    # ----------------------------------------------------------
    # Aplicar ajustes al JSON
    # ----------------------------------------------------------
    print(f"\n=== AJUSTES POR MES ===")
    print(f"{'Mes':<10} {'Bnf orig':>10} {'+ Sellable':>10} {'+ 2a mano':>10} {'+ Amazon':>10} {'= Real':>10} {'Mg orig':>8} {'Mg real':>8}")

    for m in rent['meses']:
        mes_nombre = m['mes']
        adj = ajustes_mes.get(mes_nombre, None)
        if adj is None:
            adj = {'sellable_uds_pvd':0.0,'segunda_mano_uds_pvd':0.0,'amazon_cash':0.0,
                   'sellable_uds':0,'segunda_mano_uds':0,'amazon_lineas':0,'amazon_uds':0}

        ajuste_sellable = round(adj['sellable_uds_pvd'], 2)
        ajuste_2mano = round(adj['segunda_mano_uds_pvd'], 2)
        ajuste_amazon = round(adj['amazon_cash'], 2)
        ajuste_total = round(ajuste_sellable + ajuste_2mano + ajuste_amazon, 2)

        bnf_orig = m['beneficio_neto']
        bnf_real = round(bnf_orig + ajuste_total, 2)
        fact_iva = m['facturacion_iva']
        mg_orig = m['margen_pct']
        mg_real = round((bnf_real / fact_iva * 100) if fact_iva > 0 else 0, 1)

        # Anyadir campos al mes
        m['ajuste_sellable'] = ajuste_sellable
        m['ajuste_segunda_mano'] = ajuste_2mano
        m['ajuste_amazon'] = ajuste_amazon
        m['ajuste_total_devoluciones'] = ajuste_total
        m['beneficio_neto_real'] = bnf_real
        m['margen_real_pct'] = mg_real

        # Contadores para auditoria (no se serializan al JSON, solo log)
        print(f"{mes_nombre:<10} {bnf_orig:>10.2f} {ajuste_sellable:>10.2f} {ajuste_2mano:>10.2f} {ajuste_amazon:>10.2f} {bnf_real:>10.2f} {mg_orig:>7.1f}% {mg_real:>7.1f}%")

    # Totales
    total_orig = sum(m['beneficio_neto'] for m in rent['meses'])
    total_real = sum(m['beneficio_neto_real'] for m in rent['meses'])
    total_fact = sum(m['facturacion_iva'] for m in rent['meses'])
    total_sellable = sum(m['ajuste_sellable'] for m in rent['meses'])
    total_2mano = sum(m['ajuste_segunda_mano'] for m in rent['meses'])
    total_amazon = sum(m['ajuste_amazon'] for m in rent['meses'])
    mg_orig_tot = (total_orig/total_fact*100) if total_fact else 0
    mg_real_tot = (total_real/total_fact*100) if total_fact else 0

    print(f"{'-'*88}")
    print(f"{'TOTAL':<10} {total_orig:>10.2f} {total_sellable:>10.2f} {total_2mano:>10.2f} {total_amazon:>10.2f} {total_real:>10.2f} {mg_orig_tot:>7.1f}% {mg_real_tot:>7.1f}%")

    # Anyadir metadatos del cruce al JSON
    rent['cruce_devoluciones'] = {
        'aplicado_at': datetime.now().isoformat(),
        'total_ajuste_sellable': round(total_sellable, 2),
        'total_ajuste_segunda_mano': round(total_2mano, 2),
        'total_ajuste_amazon': round(total_amazon, 2),
        'total_ajuste': round(total_sellable + total_2mano + total_amazon, 2),
        'beneficio_total_original': round(total_orig, 2),
        'beneficio_total_real': round(total_real, 2),
        'margen_pct_original': round(mg_orig_tot, 2),
        'margen_pct_real': round(mg_real_tot, 2),
        'productos_sin_pvd_ignorados': sorted(set(sin_pvd)) if sin_pvd else [],
    }

    # Sobreescribir el JSON con los campos nuevos
    with open(out_rent, 'w', encoding='utf-8') as f:
        json.dump(rent, f, ensure_ascii=False, separators=(',',':'))
    print(f"\nOK rentabilidad.json actualizado: {os.path.getsize(out_rent)/1024:.1f} KB")
    print(f"   Beneficio fantasma recuperado: {(total_real - total_orig):.2f} EUR")


# ============================================================
# 7. Buy Box desde Keepa (productos Moloka, ES)
# ============================================================

# ============================================================
# 7. KEEPA -> Supabase  (con INTERRUPTOR DE MODO)
#
#   MODO = "BASICA"   -> solo Buy Box ES. ~560 tokens (~2h con 300/h). Para el dia a dia / cada 2 dias.
#   MODO = "COMPLETA" -> ES+IT+FR: Buy Box + ventas-mes + imagenes + COSTES estimados IT/FR.
#                        ~1680 tokens (~5-6h con 300/h). Para un dia que NO vayas a escanear.
#
#   Los costes IT/FR (comision y logistica) salen del MISMO objeto que el Buy Box:
#   NO cuestan tokens extra. Son ESTIMACION de Keepa -> la app los pinta en ROJO hasta
#   que haya ventas reales en ese pais (entonces manda el dato real y se vuelve negro).
#
# Keepa = datos publicos de Amazon, NO toca la SP-API de nadie.
# Ejecuta ANTES la celda 2 (define sb y todos_productos). NO uses "Ejecutar todo".
# ============================================================
MODO = "COMPLETA" if SOLICITUD_MODO == "completa" else "BASICA"

import keepa, time

KEEPA_API_KEY = os.environ['KEEPA_API_KEY']
api = keepa.Keepa(KEEPA_API_KEY)

DOMINIOS = ['ES'] if MODO == "BASICA" else ['ES', 'IT', 'FR']
print(f"MODO = {MODO}  ->  dominios: {DOMINIOS}")

# ASINs de productos activos no descatalogados (los que se ven en Rotacion)
asins_map = {}   # asin -> id de producto
for p in todos_productos:
    if p.get('activo', True) and p.get('estado') != 'DESCATALOGADO' and p.get('asin'):
        a = p['asin'].strip()
        if a and a not in asins_map:
            asins_map[a] = p['id']
asins = list(asins_map.keys())
print(f"Consultando Keepa de {len(asins)} ASINs...")

buybox  = {'ES': {}, 'IT': {}, 'FR': {}}   # asin -> precio Buy Box EUR
monthly = {'ES': {}, 'IT': {}, 'FR': {}}   # asin -> uds/mes (todos los sellers)
com_est = {'ES': {}, 'IT': {}, 'FR': {}}   # asin -> % comision estimada (referralFeePercentage). ES incluida (fusion celda 24).
env_est = {'IT': {}, 'FR': {}}             # asin -> logistica estimada EUR (pickAndPackFee/100)
fba_fee = {'ES': {}, 'FR': {}, 'IT': {}}   # asin -> tarifa FBA Pick&Pack de Keepa EUR (3 mercados) -> alerta envio anomalo
imagenes = {}                              # asin -> URL imagen (comun, de ES)
BATCH = 100

def extraer_url_imagen(prod):
    # Keepa marco imagesCSV como DEPRECATED. El campo bueno ahora es 'images'
    # (lista de objetos con hasta 2 resoluciones: large y medium). Probamos varias
    # claves posibles por robustez y caemos a imagesCSV si hiciera falta.
    imgs = prod.get('images')
    if isinstance(imgs, list) and imgs:
        el = imgs[0]
        nombre = None
        if isinstance(el, dict):
            for k in ('l', 'large', 'hiRes', 'm', 'medium', 'image', 'name'):
                if el.get(k):
                    nombre = el[k]; break
        elif isinstance(el, str):
            nombre = el
        if nombre:
            nombre = str(nombre)
            return nombre if nombre.startswith('http') else ('https://m.media-amazon.com/images/I/' + nombre)
    csv = prod.get('imagesCSV')   # fallback al campo viejo
    if csv:
        primer = str(csv).split(',')[0].strip()
        if primer:
            return 'https://m.media-amazon.com/images/I/' + primer
    return None

for dom in DOMINIOS:
    print(f"\n--- Dominio {dom} ---")
    DIAG = True   # imprime los primeros productos del dominio para validar
    for i in range(0, len(asins), BATCH):
        lote = asins[i:i+BATCH]
        try:
            productos = api.query(lote, domain=dom, stats=90, history=False, buybox=True, to_datetime=False)
        except Exception as e:
            print(f"  Error lote {i} ({dom}): {e}")
            time.sleep(15)
            continue

        if DIAG:
            for pd in productos[:3]:
                stx = pd.get('stats') or {}
                curx = stx.get('current') or []
                c18 = curx[18] if len(curx) > 18 else 'n/a'
                fba = (pd.get('fbaFees') or {}).get('pickAndPackFee')
                print(f"  [DIAG {dom}] {pd.get('asin')}: BB[18]={c18}  monthlySold={pd.get('monthlySold')}  "
                      f"refFee%={pd.get('referralFeePercentage')}  pickPack={fba}")
            DIAG = False

        for prod in productos:
            a = prod.get('asin')
            if not a:
                continue
            # Buy Box (current[18] = BUY_BOX_SHIPPING; fallback buyBoxPrice)
            st = prod.get('stats') or {}
            cur = st.get('current') or []
            precio = None
            if len(cur) > 18 and cur[18] is not None and cur[18] > 0:
                precio = round(cur[18] / 100.0, 2)
            else:
                bb = st.get('buyBoxPrice')
                if bb is not None and bb > 0:
                    precio = round(bb / 100.0, 2)
            if precio is not None:
                buybox[dom][a] = precio
            # Ventas mensuales (todos los sellers). Keepa devuelve -1 si no hay dato.
            ms = prod.get('monthlySold')
            if ms is not None and ms >= 0:
                monthly[dom][a] = int(ms)
            # Imagen: solo de ES (es comun a los 3 marketplaces, mismo ASIN)
            if dom == 'ES' and a not in imagenes:
                u = extraer_url_imagen(prod)
                if u:
                    imagenes[a] = u
            # Tarifa FBA Pick&Pack de Keepa (los 3 mercados) -> para la alerta de envio anomalo.
            # Es lo que Amazon DEBERIA cobrar; se compara contra lo que cobra de verdad.
            pp_all = (prod.get('fbaFees') or {}).get('pickAndPackFee')
            if pp_all is not None and pp_all > 0 and dom in fba_fee:
                fba_fee[dom][a] = round(pp_all / 100.0, 2)
            # Comision estimada (referralFeePercentage): mismo objeto, 0 tokens extra.
            # ES incluida -> ya NO hace falta la 2a pasada de Espana (celda 24 eliminada).
            ref = prod.get('referralFeePercentage')
            if ref is not None and ref > 0 and dom in com_est:
                com_est[dom][a] = round(float(ref), 2)
            # Logistica estimada solo IT/FR (la de ES ya esta en fba_fee['ES']).
            if dom in ('IT', 'FR'):
                pp = (prod.get('fbaFees') or {}).get('pickAndPackFee')
                if pp is not None and pp > 0:
                    env_est[dom][a] = round(pp / 100.0, 2)
        print(f"  {dom} lote {i//BATCH+1}: BB={len(buybox[dom])}  monthly={len(monthly[dom])}"
              + (f"  com={len(com_est[dom])} env={len(env_est[dom])}" if dom in ('IT','FR') else ""))
        time.sleep(2)

# Escribir en Supabase
actualizados = 0
for asin, pid in asins_map.items():
    payload = {}
    if MODO == "BASICA":
        # RAPIDA: TODO lo de Espana (viene en 1 sola pasada, ~570 tok). Sin IT/FR.
        if asin in buybox['ES']:   payload['buy_box'] = buybox['ES'][asin]
        if asin in com_est['ES']:  payload['comision_pct_keepa_es'] = com_est['ES'][asin]
        if asin in monthly['ES']:  payload['keepa_monthly_sold_es'] = monthly['ES'][asin]
        if asin in fba_fee['ES']:  payload['keepa_fba_fee_es'] = fba_fee['ES'][asin]
        if asin in imagenes:       payload['keepa_image'] = imagenes[asin]
    else:
        # COMPLETA: Buy Box + ventas-mes + imagen + costes estimados IT/FR
        if asin in buybox['ES']:  payload['buy_box'] = buybox['ES'][asin]
        if asin in com_est['ES']: payload['comision_pct_keepa_es'] = com_est['ES'][asin]
        if asin in buybox['IT']:  payload['buy_box_it'] = buybox['IT'][asin]
        if asin in buybox['FR']:  payload['buy_box_fr'] = buybox['FR'][asin]
        if asin in monthly['ES']: payload['keepa_monthly_sold_es'] = monthly['ES'][asin]
        if asin in monthly['IT']: payload['keepa_monthly_sold_it'] = monthly['IT'][asin]
        if asin in monthly['FR']: payload['keepa_monthly_sold_fr'] = monthly['FR'][asin]
        if asin in imagenes:      payload['keepa_image'] = imagenes[asin]
        if asin in com_est['IT']: payload['comision_pct_it'] = com_est['IT'][asin]
        if asin in com_est['FR']: payload['comision_pct_fr'] = com_est['FR'][asin]
        if asin in env_est['IT']: payload['envio_it'] = env_est['IT'][asin]
        if asin in env_est['FR']: payload['envio_fr'] = env_est['FR'][asin]
        # Tarifa FBA Pick&Pack de Keepa (3 mercados) para la alerta de envio anomalo
        if asin in fba_fee['ES']: payload['keepa_fba_fee_es'] = fba_fee['ES'][asin]
        if asin in fba_fee['IT']: payload['keepa_fba_fee_it'] = fba_fee['IT'][asin]
        if asin in fba_fee['FR']: payload['keepa_fba_fee_fr'] = fba_fee['FR'][asin]
    if not payload:
        continue
    try:
        sb.table('productos').update(payload).eq('asin', asin).execute()  # todas las fichas del mismo ASIN
        actualizados += 1
    except Exception as e:
        print(f"  Error guardando {asin}: {e}")

if MODO == "COMPLETA":
    # --- ASIN + IMAGENES POR EAN para productos SIN ASIN ---
    # Los productos sin ASIN no entran en la consulta por ASIN de arriba. Keepa permite
    # buscar por EAN (product_code_is_asin=False) y en la MISMA respuesta trae el ASIN
    # y la imagen. Asi rellenamos el ASIN que faltaba (antes solo se cogia la foto).
    # Pedimos los que NO tienen ASIN (con EAN). La imagen se escribe solo si aun no tiene.
    def norm_ean(e): return str(e).strip().lstrip('0')
    sin_asin = {}   # ean_norm -> [ids de fichas sin asin]
    necesita_img = set()   # ids que ademas no tienen foto (para no regastar)
    for p in todos_productos:
        if (p.get('activo', True) and p.get('estado') != 'DESCATALOGADO'
                and not (p.get('asin') or '').strip()
                and (p.get('ean') or '').strip()):
            en = norm_ean(p['ean'])
            sin_asin.setdefault(en, []).append(p['id'])
            if not (p.get('keepa_image') or '').strip():
                necesita_img.add(p['id'])
    eans_pedir = list(sin_asin.keys())
    print(f"\n--- ASIN+Imagen por EAN (fichas sin ASIN): {len(eans_pedir)} EANs ---")
    asin_por_ean = {}   # ean_norm -> asin que devuelve Keepa
    img_por_ean = {}    # ean_norm -> url imagen
    multi_asin = []     # EANs que devolvieron varios ASIN (para que Fernando los revise)
    if eans_pedir:
        for i in range(0, len(eans_pedir), BATCH):
            lote = eans_pedir[i:i+BATCH]
            try:
                prods = api.query(lote, domain='ES', history=False, stats=None,
                                  buybox=False, product_code_is_asin=False, to_datetime=False)
            except Exception as e:
                print(f"  Error lote EAN {i}: {e}"); time.sleep(15); continue
            for prod in (prods or []):
                if not isinstance(prod, dict):
                    continue
                a = (prod.get('asin') or '').strip()
                u = extraer_url_imagen(prod)
                # Keepa puede devolver varios EAN por producto: casar con los pedidos
                for e in (prod.get('eanList') or []):
                    en = norm_ean(e)
                    if en not in sin_asin:
                        continue
                    if a:
                        if en in asin_por_ean and asin_por_ean[en] != a:
                            # mismo EAN -> dos ASIN distintos: lo dejamos sin tocar y avisamos
                            if en not in [m[0] for m in multi_asin]:
                                multi_asin.append((en, asin_por_ean[en], a))
                        elif en not in asin_por_ean:
                            asin_por_ean[en] = a
                    if u and en not in img_por_ean:
                        img_por_ean[en] = u
            print(f"  EAN lote {i//BATCH+1}: {len(asin_por_ean)} ASIN / {len(img_por_ean)} imagenes acumulados")
            time.sleep(2)
        # Escribir ASIN (solo a fichas que siguen sin ASIN) + imagen (solo si no tenia).
        # EANs con ASIN ambiguo (varios) NO se escriben: se listan para revision manual.
        ambiguos = {m[0] for m in multi_asin}
        asin_escritos = 0
        img_escritas = 0
        for en, ids in sin_asin.items():
            asin_e = asin_por_ean.get(en)
            url_e = img_por_ean.get(en)
            if en in ambiguos:
                asin_e = None   # no escribir ASIN si es ambiguo
            for pid in ids:
                payload2 = {}
                if asin_e:
                    payload2['asin'] = asin_e
                if url_e and pid in necesita_img:
                    payload2['keepa_image'] = url_e
                if not payload2:
                    continue
                try:
                    sb.table('productos').update(payload2).eq('id', pid).execute()
                    if 'asin' in payload2: asin_escritos += 1
                    if 'keepa_image' in payload2: img_escritas += 1
                except Exception as e:
                    print(f"  Error guardando id {pid}: {e}")
        print(f"  ASIN rellenados por EAN: {asin_escritos} fichas")
        print(f"  Imagenes por EAN guardadas: {img_escritas} fichas")
        if multi_asin:
            print(f"\n  [!] {len(multi_asin)} EAN con VARIOS ASIN (NO se han tocado, revisa a mano en Amazon):")
            for en, a1, a2 in multi_asin:
                print(f"      EAN {en}: {a1} vs {a2}")

print(f"\nOK ({MODO}): {actualizados} productos actualizados en Supabase.")
print(f"Buy Box:    ES={len(buybox['ES'])}  IT={len(buybox['IT'])}  FR={len(buybox['FR'])}")
if MODO == "COMPLETA":
    print(f"Ventas/mes: ES={len(monthly['ES'])}  IT={len(monthly['IT'])}  FR={len(monthly['FR'])}")
    print(f"Costes est: IT(com={len(com_est['IT'])} env={len(env_est['IT'])})  FR(com={len(com_est['FR'])} env={len(env_est['FR'])})")
    print(f"Imagenes:   {len(imagenes)}")
print("Valida en Amazon un par de precios antes de fiarte del resto.")


# ============================================================
# 8. Canales IT / FR → canales_producto (calculadora Rotación)
# ============================================================

# ============================================================
# CANALES IT / FR  ->  tabla canales_producto (calculadora Rotacion)
# ------------------------------------------------------------
# Replica EXACTAMENTE la logica de venta_actual de ES (celda 6):
#   - precio_venta = precio de la ULTIMA venta (con IVA).
#   - envio        = MEDIANA de las ultimas 10 ventas FBA (sin IVA, por ud).
#   - comision_pct = MEDIANA del % de las ultimas 10 ventas.
# Las tarifas (comision y envio) se dividen SIEMPRE por IVA_GENERAL (1.21):
#   Amazon factura sus tarifas al autonomo espanol con IVA espanol del 21%
#   en los 3 marketplaces. El iva_pct (22 IT / 20 FR) lo usa la app solo
#   para la BASE de la venta, NO para las tarifas.
# Clave unica de canales_producto: (canal, item_id_canal). item_id_canal = SKU.
# Solo escribe SKUs que existan en BD (rellena producto_id + ean).
#
# DRY_RUN = True  -> solo imprime lo que escribiria, NO toca la BD.
# Requiere: celda 2 ejecutada (MAPA_SKU, sb, IVA_GENERAL, INPUTS).
# ============================================================
from statistics import median
from collections import Counter
import glob

DRY_RUN = False  # <<<<<  ACTIVADO: escribe IT/FR en canales_producto

# --- Parser de fecha multiidioma (ES + IT + FR) ---
MESES_MULTI = {
    'ene':1,'gen':1,'jan':1,
    'feb':2,'fev':2,
    'mar':3,'mars':3,
    'abr':4,'apr':4,'avr':4,
    'may':5,'mag':5,'mai':5,
    'jun':6,'giu':6,'juin':6,
    'jul':7,'lug':7,'juil':7,
    'ago':8,'aug':8,'aou':8,
    'sep':9,'set':9,
    'oct':10,'ott':10,
    'nov':11,
    'dic':12,'dec':12,
}

def _mes_num(tok):
    tok = tok.lower().strip().rstrip('.')
    # normalizar acentos comunes (fevr., aout, dec.)
    tok = (tok.replace('\u00e9','e').replace('\u00e8','e')
              .replace('\u00fb','u').replace('\u00f4','o').replace('\u00ea','e'))
    for k in (tok, tok[:4], tok[:3]):
        if k in MESES_MULTI:
            return MESES_MULTI[k]
    return None

def parse_fecha_multi(s):
    if not s: return None
    m = re.match(r'(\d+)\s+([^\s]+)\s+(\d{4})', s.strip())
    if not m: return None
    dia, mes, ano = m.groups()
    mm = _mes_num(mes)
    if not mm: return None
    return datetime(int(ano), mm, int(dia))

def _num_local(s):
    if s is None: return 0.0
    s = str(s).strip()
    if s in ('', '-'): return 0.0
    if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

CANAL_POR_PAIS = {'it': 'amazon_it', 'fr': 'amazon_fr'}
IVA_POR_PAIS   = {'it': 22, 'fr': 20}

def _detectar_pais(rows, c_mkt):
    vals = Counter((r.get(c_mkt) or '').lower() for r in rows if (r.get(c_mkt) or '').strip())
    if not vals: return None
    top = vals.most_common(1)[0][0]   # ej: amazon.es / amazon.it / amazon.fr
    for p in ('es', 'it', 'fr'):
        if top.endswith('.' + p):
            return p
    return None

def procesar_canal_amazon(filepath):
    """Devuelve (pais, registros, huerfanos). registros=[] si es ES o no aplica."""
    with open(filepath, encoding='utf-8-sig', errors='ignore') as f:
        lineas = f.readlines()
    idx = None
    for i, ln in enumerate(lineas[:40]):
        if len(next(csv.reader([ln]))) > 10:
            idx = i; break
    if idx is None:
        return None, [], []
    cab = next(csv.reader([lineas[idx]]))
    if len(cab) < 24:
        return None, [], []
    rows = list(csv.DictReader(lineas[idx + 1:], fieldnames=cab))
    # Indices fijos (estructura identica en ES/IT/FR)
    C_FECHA, C_SKU, C_CANT, C_MKT, C_GEST = cab[0], cab[4], cab[6], cab[7], cab[8]
    C_VENTAS, C_IMP, C_COM, C_LOG = cab[13], cab[14], cab[22], cab[23]

    pais = _detectar_pais(rows, C_MKT)
    if pais not in CANAL_POR_PAIS:        # ES o desconocido -> ignorar (ES lo hace celda 6)
        return pais, [], []

    canal = CANAL_POR_PAIS[pais]
    iva_pct = IVA_POR_PAIS[pais]

    # Filtro = toda VENTA real (cantidad>0 y ventas>0). Esto descarta
    # reembolsos (ventas<0) y tarifas/ajustes (ventas=0) sin depender del
    # idioma de la columna 'tipo'. Igual que ES (celda 6), el envio se limita
    # a FBA mas abajo (t_log!=0 -> None), no aqui. C_GEST se conserva por si
    # se quisiera filtrar en el futuro.
    ventas_sku = defaultdict(list)
    for r in rows:
        c = int(_num_local(r.get(C_CANT, 0)))
        if c <= 0:
            continue
        ventas = _num_local(r.get(C_VENTAS, 0))
        if ventas <= 0:
            continue
        sku = (r.get(C_SKU, '') or '').strip()
        if not sku:
            continue
        f = parse_fecha_multi(r.get(C_FECHA, ''))
        if not f:
            continue
        iva_v = _num_local(r.get(C_IMP, 0))
        t_com = _num_local(r.get(C_COM, 0))
        t_log = _num_local(r.get(C_LOG, 0))
        precio_ud = (ventas + iva_v) / c
        fba_ud = (-t_log / IVA_GENERAL / c) if t_log != 0 else None
        com_pct = ((-t_com / IVA_GENERAL) / (ventas + iva_v) * 100) if (ventas + iva_v) > 0 and t_com != 0 else None
        ventas_sku[sku].append((f, precio_ud, fba_ud, com_pct))

    registros, huerfanos = [], []
    for sku, lst in ventas_sku.items():
        lst.sort(key=lambda x: x[0])
        fbas = [x[2] for x in lst if x[2] is not None][-10:]
        coms = [x[3] for x in lst if x[3] is not None][-10:]
        if sku not in MAPA_SKU:
            huerfanos.append(sku)
            continue
        info = MAPA_SKU[sku]
        registros.append({
            'canal': canal,
            'item_id_canal': sku,
            'ean': info.get('ean'),
            'producto_id': info.get('id'),
            'precio_venta': round(lst[-1][1], 2),
            'comision_pct': round(median(coms), 2) if coms else None,
            'iva_pct': iva_pct,
            'envio': round(median(fbas), 2) if fbas else None,
            'activo': True,
            '_nombre': info.get('nombre', ''),   # solo impresion
            '_n': len(lst),
        })
    return pais, registros, huerfanos

# ------------------------------------------------------------
# Ejecucion
# ------------------------------------------------------------
print("=" * 70)
print(f"  CANALES IT/FR -> canales_producto    (DRY_RUN = {DRY_RUN})")
print("=" * 70)

try:
    actual = sb.table('canales_producto').select('canal').execute().data
    print("Canales ya existentes en la tabla:", dict(Counter(c['canal'] for c in actual)))
except Exception as e:
    print("Aviso: no pude leer canales_producto ->", e)

# Buscar CSV en INPUTS y PROCESSED; quedarse con el mas reciente de cada pais
# (igual criterio que la celda de velocidad multipais).
candidatos = []
for carpeta in [INPUTS, PROCESSED]:
    for fp in glob.glob(f'{carpeta}/*.csv'):
        try:
            candidatos.append((os.path.getmtime(fp), fp))
        except OSError:
            pass
candidatos.sort()   # ascendente por fecha de modificacion

por_pais = {}   # pais -> (registros, huerfanos, filepath)  (el mas reciente gana)
for _mt, fp in candidatos:
    try:
        pais, reg, huer = procesar_canal_amazon(fp)
    except Exception as e:
        print(f"[SKIP] {os.path.basename(fp)} -> {e}")
        continue
    if pais in CANAL_POR_PAIS:
        por_pais[pais] = (reg, huer, fp)

todos = []
for pais in ('it', 'fr'):
    if pais not in por_pais:
        print(f"\n--- {pais.upper()}: no se encontro CSV de transacciones ---")
        continue
    reg, huer, fp = por_pais[pais]
    print(f"\n--- {os.path.basename(fp)}  =>  {pais.upper()} ({CANAL_POR_PAIS[pais]})  | {len(reg)} productos ---")
    print(f"  {'SKU':14} {'Precio':>8} {'Envio':>7} {'Com%':>6}  Producto")
    for r in sorted(reg, key=lambda x: -x['_n']):
        print(f"  {r['item_id_canal']:14} {r['precio_venta']:>8.2f} "
              f"{(r['envio'] if r['envio'] is not None else 0):>7.2f} "
              f"{(r['comision_pct'] if r['comision_pct'] is not None else 0):>6.2f}  {r['_nombre'][:40]}")
    if huer:
        print(f"  [!] SKUs con ventas pero SIN ficha en BD (no se escriben): {huer}")
    todos.extend(reg)

if not todos:
    print("\nNo se encontraron ventas IT/FR en los CSV de INPUTS.")
elif not DRY_RUN:
    payload = [{k: v for k, v in r.items() if not k.startswith('_')} for r in todos]
    sb.table('canales_producto').upsert(payload, on_conflict='canal,item_id_canal').execute()
    print(f"\nOK -> UPSERT de {len(payload)} filas en canales_producto (IT/FR).")
else:
    print(f"\nDRY_RUN activo: NO se ha escrito nada. {len(todos)} filas listas.")
    print("Revisa los numeros y, si cuadran, pon DRY_RUN = False y re-ejecuta esta celda.")


# ============================================================
# 8b. Canal Miravia → canales_producto (API: precio + comisión + envío + velocidad reales)
# ============================================================

# ============================================================
# CANAL MIRAVIA  ->  tabla canales_producto (calculadora Rotacion)
# ------------------------------------------------------------
# Lee la API de Miravia (datos REALES, sin descargar ningun Excel):
#   - /products/get            -> precio de venta actual + EAN + stock disponible + item_id.
#   - /finance/transaction/details/get (90d) -> comision % real y envio real (datos liquidados).
#   - /orders/get (30d) + /order/items/get   -> ventas reales por producto -> velocidad uds_7d / uds_30d.
# Cruza con tu BD por EAN y hace UPSERT en canales_producto (canal='miravia'):
#   precio_venta, comision_pct (real si ha vendido; si no, 13), envio (real; si no, 3,10),
#   iva 21, uds_7d, uds_30d.
#
# La comision y el envio de Miravia van SIN IVA (facturas Singapur + reverse charge NL),
# por eso la app (calcMargenMiravia) NO los divide entre 1,21. El precio SI lleva IVA.
# NO toca 'coste_almacen' (lo gestiona Fernando desde la app, en la columna Almacen).
# Clave unica de canales_producto: (canal, item_id_canal). Aqui item_id_canal = item_id de Miravia.
#
# Miravia es de Moloka: NO toca la SP-API de nadie. Solo LECTURA de Miravia + escritura en
# canales_producto (no toca 'productos' ni stock). Requiere celda 2 (sb, todos_productos)
# y los 3 Secrets MIRAVIA_* con su toggle de acceso en ESTE notebook.
# ============================================================
import time, hmac, hashlib
from statistics import median
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil import parser as _dateparser

MRV_APP_KEY      = os.environ['MIRAVIA_APP_KEY']
MRV_APP_SECRET   = os.environ['MIRAVIA_APP_SECRET']
MRV_ACCESS_TOKEN = os.environ['MIRAVIA_ACCESS_TOKEN']
MRV_GATEWAY = 'https://api.miravia.es/rest'
MRV_DIAS_FIN = 90      # ventana de transacciones financieras (comision/envio)
MRV_DIAS_VEL = 30      # ventana de pedidos para la velocidad
COMISION_DEFECTO = 13      # % si el producto aun no ha vendido en Miravia
ENVIO_DEFECTO    = 3.10    # EUR si el producto aun no ha vendido

import requests as _rq

def _mrv_firmar(api, params):
    base = api + ''.join('%s%s' % (k, params[k]) for k in sorted(params))
    return hmac.new(MRV_APP_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()

def _mrv(api, bp=None):
    p = dict(bp or {})
    p.update({'app_key': MRV_APP_KEY, 'access_token': MRV_ACCESS_TOKEN,
              'timestamp': str(int(time.time() * 1000)), 'sign_method': 'sha256'})
    p['sign'] = _mrv_firmar(api, p)
    return _rq.get(MRV_GATEWAY + api, params=p, timeout=30).json()

def _mrv_num(s):
    s = str(s).strip().replace('.', '').replace(',', '.')   # '1.234,56'->1234.56 ; '-3,10'->-3.10
    try: return float(s)
    except: return 0.0

def _norm_ean(e): return str(e).strip().lstrip('0')

def _fecha(v):
    """Parsea created_at de Miravia de forma robusta (string ISO o epoch ms/s). Devuelve date o None."""
    if v is None or v == '':
        return None
    try:
        if isinstance(v, (int, float)) or str(v).strip().isdigit():
            n = int(v)
            if n > 10_000_000_000:   # epoch en milisegundos
                n //= 1000
            return datetime.fromtimestamp(n, tz=ZoneInfo('Europe/Madrid')).date()
        return _dateparser.parse(str(v)).date()
    except Exception:
        return None

print("=" * 70)
print("  CANAL MIRAVIA -> canales_producto")
print("=" * 70)

# --- 1) Productos de Miravia (precio + EAN + stock + item_id), paginado ---
def _stock_sku(sku):
    """Stock disponible del SKU. La API de Miravia no documenta el campo; probamos los habituales."""
    for k in ('quantity', 'SellableQuantity', 'sellable_quantity', 'Available', 'available',
              'fulfillable_quantity', 'stock', 'Stock'):
        v = sku.get(k)
        if v is not None:
            try: return int(float(v))
            except: pass
    return None

prods_mrv = {}   # item_id(str) -> {'ean', 'precio', 'stock'}
_diag_sku = True
offset = 0
while True:
    d = _mrv('/products/get', {'limit': '50', 'offset': str(offset)})
    if str(d.get('code')) != '0':
        print("  [products/get] respuesta:", d.get('code'), d.get('message')); break
    lote = (d.get('data') or {}).get('products', [])
    if not lote: break
    for p in lote:
        sku0 = (p.get('skus') or [{}])[0]
        if _diag_sku:   # diagnostico: ver las claves del SKU una vez (para confirmar el campo de stock)
            print("[DIAG] claves del SKU:", list(sku0.keys())); _diag_sku = False
        try: precio = float(sku0.get('price') or 0) or None
        except: precio = None
        prods_mrv[str(p.get('item_id'))] = {'ean': sku0.get('ean_code', ''),
                                            'precio': precio, 'stock': _stock_sku(sku0)}
    offset += 50
    if offset >= ((d.get('data') or {}).get('total_products') or 0): break
print(f"Productos en Miravia: {len(prods_mrv)}")

# --- 2) Transacciones financieras (comision% + envio reales) ---
# OJO: finance solo trae lo YA LIQUIDADO. NO sirve para velocidad (las ventas recientes
# aun no liquidadas no aparecen). Aqui se usa SOLO para comision% y envio reales.
tz = ZoneInfo('Europe/Madrid')
hasta = datetime.now(tz); desde = hasta - timedelta(days=MRV_DIAS_FIN)
ventas, comis, envios = defaultdict(float), defaultdict(float), defaultdict(list)
offset = 0
while True:
    d = _mrv('/finance/transaction/details/get', {
        'start_time': desde.strftime('%Y-%m-%d'),
        'end_time':   hasta.strftime('%Y-%m-%d'),
        'limit': '50', 'offset': str(offset)})
    if str(d.get('code')) != '0':
        print("  [finance] respuesta:", d.get('code'), d.get('message')); break
    lote = d.get('data') or []
    if not isinstance(lote, list) or not lote: break
    for t in lote:
        iid = str(t.get('miravia_sku', '')).split('_')[0]
        fn, amt = t.get('fee_name', ''), _mrv_num(t.get('amount', 0))
        if fn == 'Item Price Credit':              ventas[iid] += amt
        elif fn == 'Commission':                   comis[iid]  += abs(amt)
        elif fn == 'Shipping Fee Paid by Seller':   envios[iid].append(abs(amt))
    offset += 50
    if len(lote) < 50: break
print(f"Comision/envio: {sum(1 for k in comis)} productos con datos liquidados")

# --- 3) Velocidad REAL desde pedidos (/orders/get + /order/items/get) ---
# Los pedidos traen TODAS las ventas (liquidadas o no) con su fecha real -> velocidad fiable.
def _item_id_linea(li):
    ms = str(li.get('miravia_sku', '')).split('_')[0]
    return ms or str(li.get('product_id', '') or li.get('item_id', ''))

created_after = (hasta - timedelta(days=MRV_DIAS_VEL)).replace(microsecond=0).isoformat()
pedidos = []
offset = 0
while True:
    d = _mrv('/orders/get', {'created_after': created_after, 'limit': '50', 'offset': str(offset)})
    if str(d.get('code')) != '0':
        print("  [orders/get] respuesta:", d.get('code'), d.get('message')); break
    bloque = d.get('data') or {}
    lote = bloque.get('orders', []) if isinstance(bloque, dict) else []
    if not lote: break
    pedidos.extend(lote)
    offset += 50
    if offset >= (bloque.get('countTotal') or 0): break

hoy = hasta.date()
uds7, uds30 = defaultdict(int), defaultdict(int)
crudos_diag, lineas_total, sin_fecha = [], 0, 0
for o in pedidos:
    dt = _fecha(o.get('created_at'))
    if len(crudos_diag) < 3:
        crudos_diag.append((o.get('created_at'), dt))
    if not dt:
        sin_fecha += 1; continue
    dias = (hoy - dt).days
    # lineas del pedido = unidades (en Miravia cada unidad es una linea)
    di = _mrv('/order/items/get', {'order_id': str(o.get('order_id'))})
    items = di.get('data') or []
    if isinstance(items, dict):
        items = items.get('orderItems') or items.get('order_items') or []
    for li in items:
        iid = _item_id_linea(li)
        if not iid: continue
        lineas_total += 1
        if 0 <= dias <= 30: uds30[iid] += 1
        if 0 <= dias <= 7:  uds7[iid]  += 1
    time.sleep(0.25)   # no saturar la API de Miravia

print(f"\n[DIAG] pedidos ({MRV_DIAS_VEL}d): {len(pedidos)} | lineas/unidades: {lineas_total} | sin fecha: {sin_fecha}")
print("[DIAG fecha] created_at crudo -> parseado:")
for crudo, parsed in crudos_diag:
    print(f"   {crudo!r} -> {parsed}")
print(f"[DIAG] total unidades 30d: {sum(uds30.values())} | total unidades 7d: {sum(uds7.values())}")

# --- 4) Indexar BD por EAN (elige ficha activa) ---
por_ean = {}
for p in todos_productos:
    if p.get('ean'):
        por_ean.setdefault(_norm_ean(p['ean']), []).append(p)
def _ficha(fichas):
    act = [f for f in fichas if f.get('activo', True)]
    return (act or fichas)[0]

# --- 5) Construir filas para canales_producto ---
filas, sin_ficha = [], []
for iid, info in prods_mrv.items():
    fichas = por_ean.get(_norm_ean(info['ean']), [])
    if not fichas:
        sin_ficha.append((iid, info['ean'])); continue
    f = _ficha(fichas)
    v = ventas.get(iid, 0)
    com_real = round(comis[iid] / v * 100, 2) if (v > 0 and comis.get(iid)) else None
    env_real = round(median(envios[iid]), 2) if envios.get(iid) else None
    filas.append({
        'producto_id':   f['id'],
        'canal':         'miravia',
        'ean':           str(info['ean']),
        'item_id_canal': iid,
        'precio_venta':  info['precio'],
        'comision_pct':  com_real if com_real is not None else COMISION_DEFECTO,
        'iva_pct':       21,
        'envio':         env_real if env_real is not None else ENVIO_DEFECTO,
        'uds_7d':        int(uds7.get(iid, 0)),
        'uds_30d':       int(uds30.get(iid, 0)),
        'stock_canal':   info.get('stock'),
        'activo':        True,
    })

# --- 6) Log + escritura ---
print(f"\n{'EAN':>14} | {'precio':>7} | {'com%':>6} | {'envio':>6} | {'stk':>3} | {'7d':>3} | {'30d':>3} | producto")
print('-' * 96)
for fila in filas:
    p = next((x for x in todos_productos if x['id'] == fila['producto_id']), {})
    real = '' if (ventas.get(fila['item_id_canal'], 0) > 0) else '  (estimado)'
    stk = '?' if fila['stock_canal'] is None else fila['stock_canal']
    print(f"{fila['ean']:>14} | {str(fila['precio_venta']):>7} | {fila['comision_pct']:>6} | "
          f"{fila['envio']:>6} | {str(stk):>3} | {fila['uds_7d']:>3} | {fila['uds_30d']:>3} | {str(p.get('nombre',''))[:30]}{real}")

if filas:
    sb.table('canales_producto').upsert(filas, on_conflict='canal,item_id_canal').execute()
    print(f"\nOK -> UPSERT de {len(filas)} filas en canales_producto (Miravia).")
else:
    print("\nNo hay productos de Miravia que cruzen con la BD.")

if sin_ficha:
    print(f"\n[!] Vendes en Miravia {len(sin_ficha)} productos que NO tienes en la BD (no se escriben, solo aviso):")
    for iid, ean in sin_ficha:
        print(f"     item_id {iid} | EAN {ean}")


# ============================================================
# 8c. Rentabilidad mensual Miravia → rentabilidad_miravia.json (Opción A: liquidado)
# ============================================================

# ============================================================
# RENTABILIDAD MENSUAL MIRAVIA  ->  rentabilidad_miravia.json
# ------------------------------------------------------------
# OPCION A: se calcula desde /finance/transaction/details/get (SOLO liquidado).
# Cuadra al centimo con lo que Miravia ha pagado. Los pedidos cancelados no
# generan 'Item Price Credit', asi que se filtran SOLOS (no aparecen en finance).
#
# Formula Miravia validada (briefing 3.x / calcMargenMiravia):
#   base      = venta_iva / 1,21         (IVA Espana 21%; el precio cliente lleva IVA)
#   comision  = SUM |Commission|         (SIN /1,21 -> factura Singapur, sin IVA)
#   envio     = SUM |Shipping Fee Paid by Seller|  (SIN /1,21)
#   coste_pvd = unidades * pvd de la ficha
#   coste_alm = unidades * coste_almacen Miravia (0,30 por defecto o el de canales_producto)
#   beneficio = base - comision - envio - coste_pvd - coste_alm
#   NO se aplica el 3% de servicios digitales (eso es solo Amazon).
#
# Cruce item_id (de miravia_sku) -> producto: via canales_producto (canal='miravia'),
# que la celda 21 rellena con item_id_canal + producto_id + coste_almacen. Cae a
# todos_productos por id para nombre/pvd. Si un item_id liquidado no tiene fila en
# canales_producto todavia, se avisa y se cuenta aparte (no rompe).
#
# Escribe SOLO rentabilidad_miravia.json en OUT_JSON. NO toca productos/stock/
# rentabilidad.json. Requiere celda 2 (sb, todos_productos, OUT_JSON, IVA_GENERAL,
# MESES_NOMBRE) y los Secrets MIRAVIA_*.
# ============================================================
import time, hmac, hashlib, json, os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests as _rq

MRV_APP_KEY      = os.environ['MIRAVIA_APP_KEY']
MRV_APP_SECRET   = os.environ['MIRAVIA_APP_SECRET']
MRV_ACCESS_TOKEN = os.environ['MIRAVIA_ACCESS_TOKEN']
MRV_GATEWAY = 'https://api.miravia.es/rest'
MRV_DIAS_FIN   = 400      # ventana de finance a barrer (cubre todo el ano en curso)
ALMACEN_MIRAVIA_DEF = 0.30

def _mrv_firmar(api, params):
    base = api + ''.join('%s%s' % (k, params[k]) for k in sorted(params))
    return hmac.new(MRV_APP_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()

def _mrv(api, bp=None):
    p = dict(bp or {})
    p.update({'app_key': MRV_APP_KEY, 'access_token': MRV_ACCESS_TOKEN,
              'timestamp': str(int(time.time() * 1000)), 'sign_method': 'sha256'})
    p['sign'] = _mrv_firmar(api, p)
    return _rq.get(MRV_GATEWAY + api, params=p, timeout=30).json()

def _mrv_num(s):
    s = str(s).strip().replace('.', '').replace(',', '.')   # '1.234,56'->1234.56 ; '-3,10'->-3.10
    try: return float(s)
    except: return 0.0

# transaction_date viene como "24 Apr 2026" (ingles). Lo parseamos sin depender de locale.
_MES_EN = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
           'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}

def _fecha_finance(s):
    """'24 Apr 2026' -> (anio, mes_int) o None."""
    try:
        partes = str(s).strip().split()
        if len(partes) != 3:
            return None
        dia = int(partes[0])
        mes = _MES_EN.get(partes[1][:3].lower())
        anio = int(partes[2])
        if not mes:
            return None
        return (anio, mes)
    except Exception:
        return None

print("=" * 70)
print("  RENTABILIDAD MENSUAL MIRAVIA  ->  rentabilidad_miravia.json")
print("=" * 70)

# --- 1) Cruce item_id -> producto, leyendo canales_producto (canal='miravia') ---
# canales_producto: item_id_canal, producto_id, coste_almacen (puede no existir la columna
# o venir null -> usamos 0,30 por defecto).
cp_rows = []
desde = 0
PAGE = 1000
while True:
    r = sb.table('canales_producto').select('*').eq('canal', 'miravia').range(desde, desde + PAGE - 1).execute()
    if not r.data:
        break
    cp_rows.extend(r.data)
    if len(r.data) < PAGE:
        break
    desde += PAGE

prod_por_id = {p['id']: p for p in todos_productos}
# item_id -> {'pvd', 'nombre', 'asin', 'sku', 'almacen'}
mapa_item = {}
for row in cp_rows:
    iid = str(row.get('item_id_canal', '')).strip()
    if not iid:
        continue
    p = prod_por_id.get(row.get('producto_id'), {})
    # coste_almacen: el de canales_producto si Fernando lo toco; si no, 0,30
    alm = row.get('coste_almacen')
    try:
        alm = float(alm) if alm is not None else ALMACEN_MIRAVIA_DEF
    except (TypeError, ValueError):
        alm = ALMACEN_MIRAVIA_DEF
    mapa_item[iid] = {
        'pvd':     float(p.get('pvd') or 0),
        'nombre':  p.get('nombre', '') or '',
        'asin':    p.get('asin'),
        'sku':     p.get('sku', '') or '',
        'almacen': alm,
    }
print(f"Fichas Miravia mapeadas (item_id -> producto): {len(mapa_item)}")

# --- 2) Barrer finance (liquidado) y agrupar por mes + por producto ---
tz = ZoneInfo('Europe/Madrid')
hasta = datetime.now(tz)

# meses[(anio,mes)][item_id] = {'venta_iva','comision','envio','unidades'}
meses_acum = defaultdict(lambda: defaultdict(lambda: {
    'venta_iva': 0.0, 'comision': 0.0, 'envio': 0.0, 'unidades': 0
}))
sin_ficha_items = set()      # item_ids liquidados que no estan en canales_producto
n_trans = 0
_vistas = set()   # dedupe de transacciones (por si dos tramos se solapan)

# La API de Miravia limita finance a < 180 dias por peticion. Barremos en tramos
# de 175 dias hacia atras hasta cubrir MRV_DIAS_FIN.
VENTANA = 175
tramo_fin = hasta
dias_restantes = MRV_DIAS_FIN
while dias_restantes > 0:
    paso = min(VENTANA, dias_restantes)
    tramo_ini = tramo_fin - timedelta(days=paso)
    offset = 0
    while True:
        d = _mrv('/finance/transaction/details/get', {
            'start_time': tramo_ini.strftime('%Y-%m-%d'),
            'end_time':   tramo_fin.strftime('%Y-%m-%d'),
            'limit': '50', 'offset': str(offset)})
        if str(d.get('code')) != '0':
            print(f"  [finance {tramo_ini.date()}->{tramo_fin.date()}] respuesta:", d.get('code'), d.get('message')); break
        lote = d.get('data') or []
        if not isinstance(lote, list) or not lote:
            break
        for t in lote:
            # clave unica de la transaccion para no contarla dos veces si tramos solapan
            _clave = (t.get('order_no'), t.get('orderItem_no'), t.get('fee_name'),
                      t.get('transaction_date'), str(t.get('amount')))
            if _clave in _vistas:
                continue
            _vistas.add(_clave)
            n_trans += 1
            ym = _fecha_finance(t.get('transaction_date'))
            if not ym:
                continue
            iid = str(t.get('miravia_sku', '')).split('_')[0]
            if not iid:
                continue
            fn = t.get('fee_name', '')
            amt = _mrv_num(t.get('amount', 0))
            bucket = meses_acum[ym][iid]
            if fn == 'Item Price Credit':
                bucket['venta_iva'] += amt
                bucket['unidades']  += 1          # cada credito de precio = 1 unidad liquidada
                if iid not in mapa_item:
                    sin_ficha_items.add(iid)
            elif fn == 'Commission':
                bucket['comision'] += abs(amt)
            elif fn == 'Shipping Fee Paid by Seller':
                bucket['envio'] += abs(amt)
        offset += 50
        if len(lote) < 50:
            break
    tramo_fin = tramo_ini - timedelta(days=1)   # siguiente tramo, sin solapar el dia limite
    dias_restantes -= paso
    time.sleep(0.3)
print(f"Transacciones finance barridas: {n_trans} | meses con datos: {len(meses_acum)}")

# --- 3) Construir el JSON con la MISMA estructura que IT/FR (meses -> productos) ---
IVA = IVA_GENERAL  # 1.21 (de la celda 2)
meses_json = []
ym_ordenados = sorted(meses_acum.keys())   # (anio, mes) ascendente
for (anio, mes) in ym_ordenados:
    items = meses_acum[(anio, mes)]
    productos_json = []
    tot_fact_iva = tot_fact_sin = tot_com = tot_env = tot_pvd = tot_alm = 0.0
    tot_uds = 0
    for iid, b in items.items():
        if b['unidades'] == 0 and b['venta_iva'] == 0:
            continue
        info = mapa_item.get(iid, {'pvd': 0.0, 'nombre': '', 'asin': None, 'sku': '', 'almacen': ALMACEN_MIRAVIA_DEF})
        venta_iva = round(b['venta_iva'], 2)
        base      = venta_iva / IVA
        comision  = round(b['comision'], 2)
        envio     = round(b['envio'], 2)
        uds       = b['unidades']
        coste_pvd = uds * info['pvd']
        coste_alm = uds * info['almacen']
        beneficio = base - comision - envio - coste_pvd - coste_alm
        roi    = (beneficio / coste_pvd * 100) if coste_pvd > 0 else None
        margen = (beneficio / venta_iva * 100) if venta_iva > 0 else None
        productos_json.append({
            'sku': info['sku'],
            'asin': info['asin'],
            'nombre': info['nombre'],
            'item_id': iid,
            'unidades': uds,
            'facturado_iva': venta_iva,
            'facturado_sin_iva': round(base, 2),
            'comision_amazon': comision,      # mismo nombre de campo que IT/FR para que el index lo lea igual
            'logistica_fba': envio,           # idem: aqui es el envio Miravia
            'otras_tarifas': 0.0,             # Miravia no tiene 3% digitales
            'coste_pvd': round(coste_pvd, 2),
            'coste_almacen': round(coste_alm, 2),
            'pvd': info['pvd'],
            'beneficio': round(beneficio, 2),
            'roi': round(roi, 1) if roi is not None else None,
            'margen': round(margen, 1) if margen is not None else None,
        })
        tot_fact_iva += venta_iva
        tot_fact_sin += base
        tot_com += comision
        tot_env += envio
        tot_pvd += coste_pvd
        tot_alm += coste_alm
        tot_uds += uds

    productos_json.sort(key=lambda p: p['beneficio'], reverse=True)
    coste_total = tot_com + tot_env + tot_pvd + tot_alm
    beneficio_neto = tot_fact_sin - coste_total
    margen_pct = (beneficio_neto / tot_fact_iva * 100) if tot_fact_iva > 0 else 0
    meses_json.append({
        'mes': MESES_NOMBRE[mes - 1],
        'anio': anio,
        'facturacion_sin_iva': round(tot_fact_sin, 2),
        'facturacion_iva': round(tot_fact_iva, 2),
        'unidades': tot_uds,
        'unidades_devueltas': 0,              # devoluciones Miravia: pendiente (no hay dato)
        'pedidos': tot_uds,                   # en Miravia 1 linea = 1 unidad
        'productos_distintos': len(productos_json),
        'comision_amazon': round(tot_com, 2),
        'logistica_fba': round(tot_env, 2),
        'otras_tarifas': 0.0,
        'coste_pvd': round(tot_pvd, 2),
        'coste_almacen': round(tot_alm, 2),
        'coste_total': round(coste_total, 2),
        'reembolso_perdida_neta': 0.0,        # devoluciones Miravia pendientes de desarrollar
        'beneficio_neto': round(beneficio_neto, 2),
        'margen_pct': round(margen_pct, 1),
        'productos': productos_json,
    })

fechas_min = min(ym_ordenados) if ym_ordenados else None
fechas_max = max(ym_ordenados) if ym_ordenados else None
miravia_json = {
    'canal': 'miravia',
    'fuente': 'finance/transaction/details (liquidado)',
    'fecha_desde': f"{fechas_min[0]}-{fechas_min[1]:02d}" if fechas_min else None,
    'fecha_hasta': f"{fechas_max[0]}-{fechas_max[1]:02d}" if fechas_max else None,
    'generado_at': datetime.now(tz).isoformat(),
    'meses': meses_json,
}

# --- 4) Escribir SOLO rentabilidad_miravia.json (no toca nada mas) ---
out_path = f'{OUT_JSON}/rentabilidad_miravia.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(miravia_json, f, ensure_ascii=False, separators=(',', ':'))
print(f"\nOK -> {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")

# --- 5) Resumen legible ---
print(f"\n{'Mes':<12} {'Fact c/IVA':>11} {'Beneficio':>10} {'Margen':>7} {'Uds':>5}")
print('-' * 50)
for m in meses_json:
    print(f"{m['mes']+' '+str(m['anio']):<12} {m['facturacion_iva']:>11.2f} "
          f"{m['beneficio_neto']:>10.2f} {m['margen_pct']:>6.1f}% {m['unidades']:>5}")

if sin_ficha_items:
    print(f"\n[!] {len(sin_ficha_items)} item_id liquidados en Miravia SIN fila en canales_producto "
          f"(no se reparte su PVD; corre antes la celda 21 para mapearlos):")
    for iid in sorted(sin_ficha_items):
        print(f"     item_id {iid}")


# (celda 24 "comision ES suelta" ELIMINADA: su dato ya lo trae la pasada ES de la celda 17)

# ============================================================
# SUBIR LOS JSON A app_datos  (la app los lee de Supabase, no de GitHub)
# Lee los ficheros ya generados en OUT_JSON y los vuelca a la tabla app_datos.
# Claves que espera la app: rentabilidad / velocidades / rentabilidad_miravia.
# ============================================================
_MAP_APP = {
    'rentabilidad.json': 'rentabilidad',
    'velocidades.json': 'velocidades',
    'rentabilidad_miravia.json': 'rentabilidad_miravia',
}
print("\n=== Subiendo JSON a app_datos (Supabase) ===")
for _fname, _clave in _MAP_APP.items():
    _ruta = f'{OUT_JSON}/{_fname}'
    if not os.path.exists(_ruta):
        print(f"  AVISO: no existe {_fname}; no se sube '{_clave}'")
        continue
    try:
        with open(_ruta, encoding='utf-8') as _f:
            _cont = json.load(_f)
        # GUARDADO ANTI-ENCOGIMIENTO: no machacar un JSON bueno con uno mucho mas
        # pequeno (caso 12-jun: faltaba un informe y rentabilidad cayo 230KB -> 15KB).
        _nuevo_bytes = len(json.dumps(_cont))
        try:
            _prev = sb.table('app_datos').select('contenido').eq('clave', _clave).execute()
            _prev_bytes = len(json.dumps(_prev.data[0]['contenido'])) if _prev.data else 0
        except Exception:
            _prev_bytes = 0
        if _prev_bytes > 5000 and _nuevo_bytes < _prev_bytes * 0.5:
            print(f"  ATENCION: '{_clave}' nuevo ({_nuevo_bytes} bytes) es menos de la mitad "
                  f"del actual ({_prev_bytes} bytes). NO se sobreescribe (posible informe "
                  f"incompleto). Revisa que subiste TODOS los informes y vuelve a lanzar.")
            continue
        sb.table('app_datos').upsert(
            {'clave': _clave, 'contenido': _cont,
             'actualizado': datetime.now().astimezone().isoformat()},
            on_conflict='clave').execute()
        print(f"  app_datos OK: '{_clave}' ({_nuevo_bytes} bytes)")
    except Exception as _e:
        print(f"  ERROR app_datos '{_clave}': {_e}")

# ============================================================
# RECADO CONSUMIDO: limpiar el buzon (recado + informes procesados)
# ROBUSTO: borra TODO lo real del buzon y VERIFICA re-listando. No se fia de
# remove() (que puede fallar en silencio con nombres con espacios/parentesis):
# comprueba que el buzon queda vacio de verdad; si no, reintenta y, si aun asi
# queda algo, AVISA con la verdad en vez de fingir exito.
# ============================================================
def _buzon_pendiente():
    """Ficheros reales del buzon (ignora placeholders y ocultos). None si no se pudo listar."""
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA_BUZON) or []
        return [o['name'] for o in objs if o.get('name') and not o['name'].startswith('.')]
    except Exception as _e:
        print('AVISO al listar el buzon:', _e)
        return None

def _limpiar_buzon():
    pendientes = _buzon_pendiente()
    if pendientes is None:
        print('AVISO: no se pudo listar el buzon; se reintentara en la proxima corrida.')
        return
    if not pendientes:
        print('Buzon ya estaba vacio.')
        return
    total = len(pendientes)
    for intento in (1, 2, 3):
        try:
            sb.storage.from_(BUCKET).remove([f'{CARPETA_BUZON}/{n}' for n in pendientes])
        except Exception as _e:
            print(f'AVISO en remove del buzon (intento {intento}):', _e)
        restantes = _buzon_pendiente()                 # VERIFICAR de verdad, no fiarse de remove()
        if restantes is None:
            print('AVISO: no se pudo verificar la limpieza del buzon.')
            return
        if not restantes:
            print(f'Buzon limpiado y VERIFICADO: {total} fichero(s) borrado(s).')
            return
        pendientes = restantes                          # reintentar solo lo que aun queda
    print(f'ATENCION: el buzon NO quedo limpio tras 3 intentos. Siguen {len(pendientes)} '
          f'fichero(s): {pendientes}. Borralos a mano en Supabase Storage para que la '
          f'proxima corrida no los reprocese.')

_limpiar_buzon()
