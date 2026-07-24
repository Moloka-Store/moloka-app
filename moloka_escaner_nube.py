#!/usr/bin/env python3
# ============================================================
# MOLOKA - Escaner solo-Keepa  (NUBE / GitHub Actions)
# ------------------------------------------------------------
# Generado a partir de Moloka_Escaner_soloKeepa.ipynb y adaptado para correr
# SIN Colab. FUENTE UNICA DE VERDAD: este .py se edita directo (sin notebook).
#
# QUE HACE:
#   - Lee el RECADO del buzon (informes/escaner/_solicitud_escaner.json):
#       { proveedor, marca, modo, rank_maximo, incluir_sin_rank }
#   - Carga el catalogo:
#       * TCG / DBLINE / BEMS -> el fichero crudo que la app subio al buzon.
#       * MOLOKA              -> lee el inventario propio DIRECTO de Supabase.
#   - Escanea con Keepa (Fase 1 rank + Fase 2 ES/IT/FR), calcula rentabilidad.
#   - Genera el Excel, lo SUBE a Storage (informes/resultados/) y registra el
#     escaneo en la tabla 'escaner_resultados' (la biblioteca de la app).
#   - Actualiza la memoria viva del proveedor (presentes / agotados).
#   - Limpia el buzon del escaner (VERIFICADO).
#
# Variables de entorno (GitHub Secrets): KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY
# ============================================================

import os, sys, time, json, re
import pandas as pd
import keepa
from supabase import create_client
from datetime import datetime, timezone
from collections import Counter

# Salida SIN BUFFER: que cada print aparezca en el log de Actions al instante
# (antes los print quedaban atrapados en el buffer y el log parecia "mudo";
#  solo se veian los 'Waiting...' de la libreria keepa, que van por otro canal).
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# ============================================================
# CREDENCIALES (entorno, no Colab)
# ============================================================
print(">>> ARRANCANDO escaner. Creando cliente Keepa...", flush=True)
api = keepa.Keepa(os.environ['KEEPA_API_KEY'])
print(">>> Cliente Keepa creado. Conectando a Supabase...", flush=True)
sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print(">>> Supabase conectado. Consultando saldo real de tokens...", flush=True)
api.update_status()   # consulta el saldo REAL al servidor (el cliente nace con 0)
print(f">>> Tokens Keepa disponibles AHORA: {api.tokens_left}", flush=True)

# ============================================================
# LLAMADA ROBUSTA A KEEPA (reintentos + backoff)
# ------------------------------------------------------------
# Keepa a veces tiene un hipo (Read timed out, corte de red, 5xx). Antes una
# sola peticion fallida mataba TODA la corrida (caso 15-jun: timeout en Fase 2
# a los 44 min -> exit code 1, corrida entera perdida).
# Aqui reintentamos hasta KEEPA_MAX_INTENTOS veces con esperas crecientes.
# Si tras todos los intentos sigue fallando, devolvemos None y el llamador
# decide: Fase 2 SALTA ese producto; Fase 1 SALTA ese lote. NUNCA se mata la
# corrida entera por un fallo transitorio.
# progress_bar=False -> no ensucia el log de Actions con barras 0%|.
# ============================================================
KEEPA_MAX_INTENTOS = 4
KEEPA_ESPERAS = [5, 15, 40, 90]   # segundos entre intentos (backoff)

def keepa_query(items, **kwargs):
    """Llama a api.query con reintentos. Devuelve la lista de productos, o None
    si tras KEEPA_MAX_INTENTOS sigue fallando (el llamador lo gestiona)."""
    kwargs.setdefault('progress_bar', False)
    for intento in range(KEEPA_MAX_INTENTOS):
        try:
            return api.query(items, **kwargs) or []
        except Exception as ex:
            if intento < KEEPA_MAX_INTENTOS - 1:
                espera = KEEPA_ESPERAS[intento]
                print(f"  [Keepa] intento {intento+1}/{KEEPA_MAX_INTENTOS} fallo: {ex} "
                      f"-> reintento en {espera}s")
                time.sleep(espera)
            else:
                print(f"  [Keepa] AGOTADOS {KEEPA_MAX_INTENTOS} intentos: {ex} -> se salta")
    return None

# ============================================================
# BUZON DEL ESCANER: leer recado + descargar catalogo
# ============================================================
BUCKET = 'informes'
# Buzon y checkpoint configurables por entorno: cada director usa su PROPIA carpeta
# (escaner_tcg/, escaner_heo/, ...) para no pisarse entre ellos. Por defecto, las de
# siempre -> la app de Elena y los escaneos manuales NO cambian.
CARPETA_ESCANER = os.environ.get('CARPETA_ESCANER') or 'escaner'   # recado + catalogo del proveedor
CARPETA_CKPT    = os.environ.get('CARPETA_CKPT') or 'escaner_ckpt'  # checkpoint (carpeta aparte)
CARPETA_RESULTADOS = 'resultados'  # Excel de salida
RECADO = '_solicitud_escaner.json'

SOLICITUD = {}
catalogo_local = None
catalogo_nombre = None
N_CRUDO = None            # nº de filas del catalogo crudo (para el blindaje anti-vaciado)
UMBRAL_PARCIAL = 0.35     # si el catalogo crudo trae <35% de lo que hay en memoria -> NO marcar agotados
try:
    objs = sb.storage.from_(BUCKET).list(CARPETA_ESCANER) or []
    for o in objs:
        nombre = o.get('name')
        if not nombre or nombre.startswith('.'):
            continue
        ruta = f'{CARPETA_ESCANER}/{nombre}'
        if nombre == RECADO:
            try:
                d = sb.storage.from_(BUCKET).download(ruta)
                SOLICITUD = json.loads(d.decode('utf-8'))
            except Exception as _e:
                print('AVISO recado:', _e)
        else:
            try:
                d = sb.storage.from_(BUCKET).download(ruta)
                catalogo_nombre = nombre
                catalogo_local = f'/tmp/{nombre}'
                with open(catalogo_local, 'wb') as fp:
                    fp.write(d)
                # El boton sube los catalogos COMPRIMIDOS en gzip (para que el CSV gordo
                # de OcioStock quepa en Storage). pd.read_csv descomprime .gz solo, pero
                # pd.read_excel NO -> aqui descomprimimos cualquier gzip y dejamos el
                # fichero PLANO, asi la lectura (excel o csv) recibe siempre el original.
                with open(catalogo_local, 'rb') as _fp:
                    _magic = _fp.read(2)
                if _magic == b'\x1f\x8b':
                    import gzip as _gz, shutil as _sh
                    _plano = catalogo_local[:-3] if catalogo_local.endswith('.gz') else catalogo_local + '.plano'
                    with _gz.open(catalogo_local, 'rb') as _src, open(_plano, 'wb') as _dst:
                        _sh.copyfileobj(_src, _dst)
                    catalogo_local = _plano
                    print(">>> Catalogo descomprimido (venia en gzip).")
            except Exception as _e:
                print('AVISO catalogo:', _e)
except Exception as ex:
    print('AVISO buzon escaner:', ex)

# --- Parametros desde el recado ---
PROVEEDOR        = (SOLICITUD.get('proveedor') or '').upper()
MARCA            = SOLICITUD.get('marca') or 'Funko'
RANK_MAXIMO      = int(SOLICITUD.get('rank_maximo') or 30000)
MODO             = (SOLICITUD.get('modo') or 'nuevos').lower()
INCLUIR_SIN_RANK = bool(SOLICITUD.get('incluir_sin_rank', False))
# Motor de filtros (lo usa el DIRECTOR automatico): si el recado trae 'filtros', el
# escaner aplica reglas finas (varias marcas + idioma + estado) en vez del filtro de
# marca simple. Si NO trae 'filtros' (escaneo manual de Fernando), todo va como siempre.
FILTROS = SOLICITUD.get('filtros') or None

# --- Autorrelanzamiento (lo activa SOLO el director): si el escaneo se acerca al corte
# de GitHub (6h), guarda el progreso y se relanza solo para seguir la noche entera.
# AUTORELANZAR_MIN ausente o 0 lo DESACTIVA -> el escaneo manual NUNCA se relanza solo.
_T_INICIO = time.time()
_LIMITE_MIN = int(os.environ.get('AUTORELANZAR_MIN', '0') or '0')
_GH_PAT = os.environ.get('GH_PAT')
_GH_REPO = os.environ.get('GH_REPO', 'Moloka-Store/moloka-app')
_WF_RELANZAR = os.environ.get('AUTORELANZAR_WORKFLOW', 'director-tcg.yml')
_TIPO_RELANZAR = os.environ.get('AUTORELANZAR_TIPO', 'completo')

def _cerca_del_corte():
    return _LIMITE_MIN > 0 and (time.time() - _T_INICIO) > _LIMITE_MIN * 60

def _relanzarme():
    if not _GH_PAT:
        print("AVISO: sin GH_PAT no puedo relanzarme. Guardo y salgo; relanza a mano.")
        return False
    try:
        import requests as _rq
        url = f'https://api.github.com/repos/{_GH_REPO}/actions/workflows/{_WF_RELANZAR}/dispatches'
        r = _rq.post(url, json={'ref': 'main', 'inputs': {'tipo': _TIPO_RELANZAR}}, timeout=30,
                     headers={'Authorization': f'Bearer {_GH_PAT}',
                              'Accept': 'application/vnd.github+json',
                              'X-GitHub-Api-Version': '2022-11-28'})
        print(f">>> Autorrelanzamiento: dispatch {_WF_RELANZAR} ({_TIPO_RELANZAR}) -> {r.status_code}")
        return r.status_code in (200, 201, 204)
    except Exception as _e:
        print("AVISO: no pude relanzarme:", _e); return False

# --- Guardados de arranque: sin recado o sin catalogo no se hace nada ---
if not SOLICITUD or not PROVEEDOR:
    print('Buzon del escaner SIN recado valido: nada que escanear. Fin.')
    sys.exit(0)

PERFILES = {
    'TCG': {
        'tipo':'excel', 'sheet':'Catálogo', 'header':0,
        'col_marca':'Marca', 'col_ean':'EAN', 'col_nombre':'Cabecera',
        'col_pa':'Precio', 'col_stock':'Stock', 'col_estado':'Estado producto',
        'estados_ok':['Disponible','Oferta','Saldo'],   # PreOrder / Backorder quedan FUERA
    },
    'DBLINE': {
        'tipo':'excel', 'sheet':0, 'header':2,
        'col_marca':'Publisher', 'col_ean':'EAN', 'col_nombre':'Descrizione',
        'col_pa':'Prezzo (€)', 'col_pa_promo':'Prezzo promo (€)', 'col_stock':'Disponibili',
        'col_estado':None, 'estados_ok':None,
    },
    'BEMS': {
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'FABRICANT', 'col_ean':'EAN', 'col_nombre':'TITRE UK',
        'col_pa':'PA', 'col_stock':'STOCK', 'col_estado':None, 'estados_ok':None,
    },
    'OSMA': {
        # Mayorista aleman de drogueria/cosmetica (primera necesidad Moloka).
        # Excel .xls, cabecera fila 1 (header=0). Precio UNITARIO con coma decimal
        # alemana (1,099 = 1,099 EUR). Stock 'verfügbar' a veces viene como '>3.000'
        # (punto de MILLAR, no decimal) -> trato especial via stock_especial.
        # Sin filtro de estado (todo lo que tenga stock>0 entra). CHASE no aplica.
        'tipo':'excel', 'sheet':0, 'header':0,
        'col_marca':'Bezeichnung', 'col_ean':'EAN 1', 'col_nombre':'Bezeichnung',
        'col_pa':'Preis_', 'col_stock':'verfügbar', 'col_estado':None, 'estados_ok':None,
        'stock_especial':'osma',        # usa _stock_osma() para parsear '>3.000'
        'col_extra_liq':'wird ausgelistet',   # 'wird ausverkauft' = se liquida (info de compra)
    },
    'BIEDRO': {
        # Mayorista aleman de drogueria (primera necesidad Moloka), misma familia que OSMA.
        # Excel .xlsx; la cabecera de datos esta en la FILA 4 (header=3): las 3 primeras
        # son el formulario de pedido (Kunden-Nr, Kundenname, Anschrift).
        # Precio UNITARIO neto con PUNTO decimal (3.40) -> _num() lo parsea directo.
        # NO trae columna de stock -> sin_columna_stock=True (se asume disponible).
        # Sin marca propia (va en el nombre) ni estado. CHASE no aplica.
        # Validado contra catalogo real: 3.316 productos con EAN+precio.
        'tipo':'excel', 'sheet':0, 'header':3,
        'col_marca':None, 'col_ean':'Stück-EAN', 'col_nombre':'Artikelbezeichnung',
        'col_pa':'Stückpreis\nnetto', 'col_stock':None, 'col_estado':None, 'estados_ok':None,
        'sin_columna_stock':True,
    },
    'OCIOSTOCK': {
        # Mayorista espanol de licencias (Funko, Banpresto, Pyramid, Cerda...).
        # Feed CSV diario con URL FIJA que se autoactualiza (el token va en GitHub
        # Secrets, NUNCA en codigo). Separador ';', campos entrecomillados, BOM
        # (utf-8-sig) -> solo afecta a la 1a columna 'id_producto', que no usamos.
        # TIENE columna de marca limpia -> se puede filtrar por marca (FUNKO, etc.).
        # Stock real en 'stock_disponible' (>0).
        # 🔒 PA = 'precio_distribuidores' (coste del distribuidor). NO usar
        # 'precio_neto'/'precio_bruto': son PVP recomendado, no el coste.
        # OJO dropshipping: el precio puede venir mas alto que el mayorista real
        # -> contrastar Funko contra BEMS/TCG antes de fiarse.
        # Validado contra feed real: 13.412 con stock+EAN+precio (3.475 Funko).
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'marca', 'col_ean':'ean', 'col_nombre':'nombre',
        'col_pa':'precio_distribuidores', 'col_stock':'stock_disponible',
        'col_estado':None, 'estados_ok':None,
        'col_volumen':'txt_precios_volumen',   # descuentos por volumen -> pestana "Precio por lote"
        'col_url':'product_url',   # enlace a la ficha de OcioStock (verificar volumen/precio en su web)
    },
    'STOCKLIST': {
        # Mayorista nordico GENERALISTA (Toys, Games and consoles, Beauty, Movies, Pet...).
        # Stocklist Excel .xlsx, hoja 'Sheet1', cabecera fila 1 (header=0). 43.174 refs, TODAS
        # con stock real. Multimoneda (EUR/GBP/USD/DKK) -> usamos EUR como coste, con PUNTO
        # decimal (17.99) -> _num() lo parsea directo. Marca limpia en 'Brand' (contains) ->
        # filtrable: Funko, Paladone, Numskull, Nemesis Now, LEGO, Ravensburger, Nintendo...
        # Stock en 'Available' (>0). Sin columna de estado (todo lo con stock entra).
        # 🔒 PENDIENTE VERIFICAR: que 'EUR' es el COSTE de proveedor y no el PVP recomendado.
        # Validado contra catalogo real: 42.878 productos con EAN(12/13)+precio+stock.
        'tipo':'excel', 'sheet':'Sheet1', 'header':0,
        'col_marca':'Brand', 'col_ean':'CodeBars', 'col_nombre':'ItemName',
        'col_pa':'EUR', 'col_stock':'Available', 'col_estado':None, 'estados_ok':None,
    },
    # ============================================================
    # PROVEEDORES DE CLAUDE-IN-CHROME (formato VARIABLE) -> DETECCION TOLERANTE
    # ------------------------------------------------------------
    # Estos catalogos se extraen a mano y cada extraccion puede salir con columnas
    # distintas (nombres, orden, xlsx/csv). En vez de fijar nombres de columna, se
    # usa 'deteccion':'tolerante': el motor detecta solo la columna de EAN (numeros
    # de 12-13 digitos), la de precio (importe, con o sin 'EUR'), la de nombre (texto
    # largo) y, si existen, marca y stock. EAN no-12/13 -> a descartados (NO se
    # inventan EANs). Stock ausente -> se asume disponible. CHASE no aplica.
    # Anadir un proveedor nuevo de Claude-in-Chrome = una linea aqui + el desplegable.
    # ============================================================
    'DINOTOYS': {'tipo':'auto', 'deteccion':'tolerante'},   # mayorista holandes (Logic4)
    'ZENTRADA': {'tipo':'auto', 'deteccion':'tolerante'},   # marketplace mayorista (xlsx/csv)
    'MIS_COMPRAS': {'tipo':'auto', 'deteccion':'tolerante', 'efimero':True},   # compras ad-hoc: deteccion tolerante y NO toca la memoria de ningun proveedor
    'HEO': {
        # heoGATE Retailer API -> catalogo cruzado por descargar_heo.py (CSV ';', columnas
        # fijas). El director de HEO PRE-FILTRA a Funko+Ultimate Guard+ofertas y sube el
        # resultado, asi que aqui se escanea con marca=TODAS. Sin stock numerico: el estado
        # 'disponible' (availableToOrder + AVAILABLE) filtra lo servible. PA = 'precio' (coste
        # de hoy, con oferta si la hay; el escaneo diario se autocorrige si la oferta acaba).
        'tipo':'csv', 'sep':';', 'header':0,
        'col_marca':'marca', 'col_ean':'ean', 'col_nombre':'nombre',
        'col_pa':'precio', 'col_stock':None,
        'col_estado':'estado', 'estados_ok':['disponible'],
        'sin_columna_stock':True,   # HEO no da stock numerico -> estado 'disponible' ya filtra
    },
    'MOLOKA': {'tipo':'supabase'},   # inventario propio: se lee de la tabla productos
}
if PROVEEDOR not in PERFILES:
    print(f'Proveedor desconocido: {PROVEEDOR}. Validos: {list(PERFILES)}. Fin.')
    sys.exit(0)
PERFIL = PERFILES[PROVEEDOR]
if PERFIL.get('efimero'):
    MODO = 'todo'   # las compras ad-hoc se escanean enteras (no hay memoria previa que filtre)

# ============================================================
# BEMS POR API (cliente integrado)
# ------------------------------------------------------------
# BEMS no se sube como fichero: se baja de su API. Cuando el proveedor es BEMS
# y NO hay catalogo en el buzon, pedimos a la API de BEMS los productos
# DISPONIBLES (AVAILABLE=1) de la marca elegida y los dejamos en un CSV temporal
# con EXACTAMENTE las columnas que el perfil BEMS ya espera
# (FABRICANT;EAN;TITRE UK;PA;STOCK). Asi el resto del motor (2 fases, calculo,
# Excel, memoria) NO cambia nada: BEMS pasa a comportarse como MOLOKA.
# Si SI hay fichero en el buzon (CSV manual antiguo), se respeta y NO se baja
# por API (compatibilidad hacia atras).
# Credenciales por entorno: BEMS_LOGIN, BEMS_PASSWORD, BEMS_SECRET_KEY.
# Mapeo API -> columnas del perfil BEMS:
#   FABRICANT <- NAME_MAN | EAN <- EAN | TITRE UK <- NAME_PRODUCT
#   PA        <- PRICE    | STOCK <- STOCK
# ============================================================
def descargar_catalogo_bems(marca, ruta_csv):
    """Baja de BEMS los productos DISPONIBLES de 'marca' (o de todo el catalogo si
    marca == 'TODAS') y los escribe como CSV ';' con las columnas del perfil BEMS.
    Devuelve el nº de productos escritos, o -1 si hubo error."""
    import csv as _csv
    try:
        from curl_cffi import requests as _curl
    except Exception as ex:
        print("ERROR BEMS: curl_cffi no disponible:", ex); return -1
    base = "https://www.probems.be/API"; imp = "chrome120"
    login = os.environ.get("BEMS_LOGIN"); pwd = os.environ.get("BEMS_PASSWORD"); sk = os.environ.get("BEMS_SECRET_KEY")
    if not (login and pwd and sk):
        print("ERROR BEMS: faltan credenciales BEMS_* en el entorno."); return -1
    # 1) token (24h, no cuesta tokens)
    try:
        rt = _curl.post(f"{base}/TOKEN",
                        data={"login": login, "password": pwd, "secret_key": sk},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        impersonate=imp, timeout=30)
    except Exception as ex:
        print("ERROR BEMS token (red):", ex); return -1
    tok = rt.json().get("access_token") if rt.status_code == 200 else None
    if not tok:
        print("ERROR BEMS token:", rt.status_code, (rt.text or "")[:150]); return -1
    H = {"accept": "application/json", "authorization": f"Bearer {tok}"}
    # 2) lista de productos DISPONIBLES de la marca (DETAILS=1 trae EAN/precio/nombre;
    #    LIMIT=0 = sin limite). Si marca == TODAS, no filtramos por fabricante.
    params = {"AVAILABLE": "1", "DETAILS": "1", "LIMIT": "0"}
    if marca and marca.strip().upper() != "TODAS":
        params["MANUFACTURER"] = marca.strip()
    try:
        r = _curl.get(f"{base}/PRODUCT-LIST-FILTER", params=params,
                      headers=H, impersonate=imp, timeout=180)
    except Exception as ex:
        print("ERROR BEMS PRODUCT-LIST-FILTER (red):", ex); return -1
    if r.status_code != 200:
        # BEMS devuelve 400 {"error":"NO RESULT"} cuando la marca no tiene productos
        # (o el filtro no casa). NO es un fallo del escaner: es "0 productos".
        # Lo tratamos como vacio limpio (return 0), no como error fatal.
        txt = (r.text or "")
        if "NO RESULT" in txt.upper():
            print(f"BEMS: '{marca}' sin resultados (NO RESULT). Se trata como 0 productos.")
            # escribir CSV solo con cabecera para que el flujo siga limpio
            with open(ruta_csv, "w", newline="", encoding="utf-8") as fp:
                _csv.writer(fp, delimiter=";").writerow(["FABRICANT", "EAN", "TITRE UK", "PA", "STOCK"])
            return 0
        print("ERROR BEMS lista:", r.status_code, txt[:150]); return -1
    try:
        prods = r.json()
    except Exception as ex:
        print("ERROR BEMS: respuesta no es JSON:", ex); return -1
    if not isinstance(prods, list):
        print("ERROR BEMS: respuesta no es una lista:", str(prods)[:150]); return -1
    # 3) escribir el CSV con el formato del perfil BEMS
    # OJO: el motor, tras leer el CSV, VUELVE a filtrar por marca sobre la columna
    # FABRICANT (contains). Como ya filtramos por marca en la propia API, ponemos en
    # FABRICANT el MISMO valor que pedimos (el id de marca) para que ese 2º filtro pase
    # trivialmente. En modo TODAS no se filtra, asi que conservamos el NAME_MAN real.
    fab_fijo = marca.strip() if (marca and marca.strip().upper() != "TODAS") else None
    n = 0
    with open(ruta_csv, "w", newline="", encoding="utf-8") as fp:
        w = _csv.writer(fp, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
        w.writerow(["FABRICANT", "EAN", "TITRE UK", "PA", "STOCK"])
        for p in prods:
            ean = str(p.get("EAN") or "").strip()
            if not ean:
                continue
            w.writerow([
                fab_fijo if fab_fijo else str(p.get("NAME_MAN") or "").strip(),
                ean,
                str(p.get("NAME_PRODUCT") or "").strip(),
                str(p.get("PRICE") or "").strip(),
                str(p.get("STOCK") or "").strip(),
            ])
            n += 1
    return n

if PROVEEDOR == 'BEMS' and not catalogo_local:
    _ruta_bems = f'/tmp/BEMS_{MARCA}_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    print(f">>> BEMS por API: bajando '{MARCA}' (solo disponible)...")
    _n_bems = descargar_catalogo_bems(MARCA, _ruta_bems)
    if _n_bems is None or _n_bems < 0:
        print("ERROR: no se pudo bajar el catalogo de BEMS por API. Fin.")
        sys.exit(1)
    if _n_bems == 0:
        print(f"BEMS: la marca '{MARCA}' no devolvio productos disponibles. Nada que escanear. Fin.")
        sys.exit(0)
    catalogo_local = _ruta_bems
    catalogo_nombre = os.path.basename(_ruta_bems)
    print(f">>> BEMS por API: {_n_bems} productos disponibles -> CSV temporal listo.")

if PROVEEDOR != 'MOLOKA' and not catalogo_local:
    print(f'Falta el catalogo de {PROVEEDOR} en el buzon. Sube el fichero y vuelve a lanzar. Fin.')
    sys.exit(0)

IVA_DEFAULT_ES, IVA_IT, IVA_FR = 0.21, 0.22, 0.20
ALMACEN, COM_DIGITALES = 0.15, 1.03
UNIDADES_CASE_TCG = 6          # CHASE en case de 6 (5+1) -> coste unitario = PA / 6. TCG y chase HEO.
LOTE_FASE1 = 100
TS = datetime.now().strftime('%Y%m%d_%H%M')
ARCHIVO_SALIDA = f'/tmp/Escaneo_{PROVEEDOR}_{MARCA}_{TS}.xlsx'
print(f"{PROVEEDOR} | Marca {MARCA} | Rank max {RANK_MAXIMO} | Modo {MODO}")

# ============================================================
# Celda 0 - formula de rentabilidad (validada al centimo)
# ============================================================
def calc_rentabilidad(precio_venta, pa, ref_pct, fee_fba, iva, almacen=0.15, com_digitales=1.03):
    base       = precio_venta / (1 + iva)
    com_amazon = precio_venta * (ref_pct/100) * com_digitales
    beneficio  = base - pa - com_amazon - fee_fba - almacen
    roi        = beneficio / pa if pa else 0
    margen     = beneficio / precio_venta if precio_venta else 0
    return dict(base=base, com_amazon=com_amazon, beneficio=beneficio, roi=roi, margen=margen)

_r = calc_rentabilidad(15.99, 8.12, 15, 3.51, 0.21)
print(">>> FORMULA OK <<<" if abs(_r['beneficio']+1.04)<0.01 and abs(_r['com_amazon']-2.47)<0.01 else ">>> REVISAR FORMULA <<<")

# ============================================================
# Funciones de EAN
# ============================================================
def core_ean(e):
    e = str(e).strip().upper()
    return e[:-1] if e.endswith('C') else e
def es_chase_ean(e):
    return str(e).strip().upper().endswith('C')

# ---- REGLA DE NEGOCIO DEL CHASE (todos los proveedores) --------------------
# El chase SOLO se compra en CAJA DE 6 (5+1): coste unitario = PA / 6.
# El chase SUELTO es un atraco -> se DESCARTA (no se escanea, no gasta tokens).
# OJO AL ORDEN: el sufijo del EAN manda sobre el nombre, porque en TCG la 'C'
# pegada al EAN YA significa la caja 5+1; si mirasemos el nombre primero,
# descartariamos por error los cases de TCG que se llaman "... Chase".
# De paso corta el bucle de OcioStock: alli el mismo EAN llega como figura
# normal, como caja 5+1 y como chase suelto, con precios muy distintos; al
# descartar el suelto y separar normal/caja en claves de memoria distintas,
# deja de haber 'cambio_precio' perpetuo.
_RE_CAJA6 = re.compile(r'5\s*\+\s*1', re.I)
# "chase" SOLO cuenta cuando es MARCADOR DE VARIANTE: al FINAL del nombre
# ("... Dilophosaurus Chase") o entre PARENTESIS ("... Pink Batman (CHASE) 18 cm").
# Si aparece en MEDIO es, casi siempre, un NOMBRE PROPIO: Chase es el perro de la
# Patrulla Canina, y sin esta restriccion se tiraban paraguas, gorros, mochilas y
# peluches perfectamente legitimos ("Peluche Chase Patrulla Canina Paw Patrol").
# Medido en el ensayo del 24-jul-2026 contra el feed real de OcioStock.
_RE_CHASE_NOM = re.compile(r'\bchase\b\s*$|\([^)]*\bchase\b[^)]*\)', re.I)

def clasificar_chase(nombre, ean_in):
    """Devuelve (es_case, es_caja6, descartar)."""
    if es_chase_ean(ean_in):
        return True, True, False       # convencion TCG: la 'C' del EAN ya es la caja
    n = str(nombre or '')
    if _RE_CAJA6.search(n):
        return True, True, False       # caja de 6 -> entra y se valora /6
    if _RE_CHASE_NOM.search(n):
        return False, False, True      # chase SUELTO -> descartar
    return False, False, False         # figura normal
def variantes_ean(core):
    c, vs = core.strip(), set()
    if c.isdigit():
        vs.add(c); vs.add(c.lstrip('0'))
        if len(c)==12: vs.add('0'+c)
        if len(c)==13 and c.startswith('0'): vs.add(c[1:])
    return [v for v in vs if v]
def norm(code): return str(code).strip().lstrip('0')
def _num(x):
    try: return float(str(x).replace(',', '.').strip())
    except Exception: return None

def _num_eur(x):
    """Precio tipo '1,77 EUR' o '2.01 €' (ZENTRADA) -> float. Quita el sufijo de moneda."""
    s = str(x).upper().replace('EUR', '').replace('€', '').strip()
    return _num(s)

def _mejor_volumen(s):
    """Parsea los descuentos por volumen de OcioStock y devuelve (uds_minimas, precio)
    del tramo MAS BARATO. Formato: tramos separados por '|', cada tramo
    'lower:upper:precio' (upper puede ir vacio). Ej: '6:12:8.99|12::8.59' -> (12, 8.59).
    Devuelve None si no hay ningun tramo valido."""
    if not s:
        return None
    mejor = None
    for parte in str(s).split('|'):
        parte = parte.strip()
        if not parte:
            continue
        campos = parte.split(':')
        if len(campos) < 3:
            continue
        try:
            uds = int(float(campos[0]))
            precio = float(campos[-1])
        except Exception:
            continue
        if precio <= 0:
            continue
        if mejor is None or precio < mejor[1]:
            mejor = (uds, precio)
    return mejor

# Umbral anti-basura de volumen: OcioStock mete valores fijos absurdos (p.ej. 5.99 de
# volumen en un casco de 109.99). Un descuento por volumen REAL rara vez baja del 50%
# del precio suelto; por debajo lo tratamos como basura y lo ignoramos.
MIN_RATIO_LOTE = 0.5

# Salvavidas de titulo: compara el nombre del proveedor con el titulo de Amazon para
# detectar EANs mal catalogados en Amazon (p.ej. un peluche cuyo ASIN es un juego de PS4).
import unicodedata as _ud, re as _reT
_STOP_TIT = {'the','and','with','de','del','la','el','los','las','un','una','uno','con','para','por',
             'pop','figura','figure','set','pack','edition','deluxe','vinilo','vinyl',
             'peluche','plush','muneco','doll','juguete','juguetes','toy','coche','coches','car'}
def _tokens_tit(t):
    t = _ud.normalize('NFKD', str(t or '')).encode('ascii','ignore').decode()
    t = _reT.sub(r'[^a-zA-Z0-9]+',' ', t).lower()
    return {w for w in t.split() if len(w) >= 3 and w not in _STOP_TIT}
def _coincide_titulo(nombre_prov, titulo_amz):
    # '?' = sin titulo (no marcamos). SI = comparten palabra distintiva. NO = nada en comun.
    if not str(titulo_amz or '').strip(): return '?'
    a = _tokens_tit(nombre_prov); b = _tokens_tit(titulo_amz)
    if not a or not b: return '?'
    return 'SÍ' if (a & b) else '⚠ NO'

def _es_ean_valido(s):
    """True si s es un EAN/UPC utilizable: 12 o 13 digitos."""
    s = str(s).strip()
    return s.isdigit() and len(s) in (12, 13)

def _parse_precio_libre(x):
    """Precio en cualquier formato razonable: '1,77 EUR', '2.01 €', '8,62', '11.34'."""
    s = str(x)
    tiene_moneda = ('eur' in s.lower()) or ('€' in s)
    return _num_eur(x) if tiene_moneda else _num(x)

def detectar_columnas(cat):
    """Detecta por NOMBRE (pistas multiidioma) y, si falla, por CONTENIDO las columnas
    de ean / precio / nombre / marca / stock en un catalogo de formato desconocido
    (ficheros de Claude-in-Chrome). Devuelve los nombres REALES de columna (o None).
    No inventa nada: si no encuentra EAN o precio con confianza, el llamante aborta."""
    cols = list(cat.columns)
    low  = {c: str(c).strip().lower() for c in cols}

    def por_nombre(claves, excluir=()):
        for c in cols:
            if c in excluir:
                continue
            if any(k in low[c] for k in claves):
                return c
        return None

    # ---- EAN: nombre primero, si no, columna con mas valores de 12-13 digitos ----
    ean = por_nombre(['ean', 'gtin', 'barcode', 'codigo de barras', 'código de barras', 'upc'])
    if ean is None:
        mejor, mejor_score = None, 0.0
        for c in cols:
            score = cat[c].astype(str).str.strip().apply(_es_ean_valido).mean()
            if score > mejor_score:
                mejor, mejor_score = c, score
        if mejor_score >= 0.30:          # al menos 30% parecen EAN reales
            ean = mejor

    # ---- PRECIO: nombre primero, si no, columna 'tipo importe' (con decimales/moneda) ----
    precio = por_nombre(['precio', 'price', 'preis', 'prezzo', 'pvd', 'coste', 'cost', 'tarifa', 'eur', '€'],
                        excluir=(ean,))
    if precio is None:
        mejor, mejor_score = None, 0.0
        for c in cols:
            if c == ean:
                continue
            vals = cat[c].astype(str)
            parseables   = vals.apply(lambda v: _parse_precio_libre(v) is not None).mean()
            con_decimal  = vals.apply(lambda v: (',' in v or '.' in v or 'eur' in v.lower() or '€' in v)).mean()
            score = parseables * (0.4 + 0.6 * con_decimal)   # premia decimales/moneda (evita indices N°)
            if score > mejor_score:
                mejor, mejor_score = c, score
        if mejor_score >= 0.50:
            precio = mejor

    # ---- NOMBRE: nombre primero, si no, columna de texto mas largo ----
    nombre = por_nombre(['nombre', 'name', 'descrip', 'titre', 'title', 'producto', 'product',
                         'bezeichnung', 'articolo', 'artikel', 'designation'], excluir=(ean, precio))
    if nombre is None:
        mejor, mejor_len = None, 0.0
        for c in cols:
            if c in (ean, precio):
                continue
            avg = cat[c].astype(str).str.len().mean()
            if avg > mejor_len:
                mejor, mejor_len = c, avg
        nombre = mejor

    # ---- MARCA y STOCK: opcionales (solo por nombre) ----
    marca = por_nombre(['marca', 'brand', 'licencia', 'license', 'licens', 'fabricante',
                        'manufacturer', 'publisher', 'fabricant'], excluir=(ean, precio, nombre))
    stock = por_nombre(['stock', 'disponib', 'verfüg', 'verfug', 'qty', 'cantidad', 'quantity', 'quantità'],
                       excluir=(ean, precio, nombre, marca))

    return {'ean': ean, 'precio': precio, 'nombre': nombre, 'marca': marca, 'stock': stock}

def _stock_osma(x):
    """Stock de OSMA: numeros normales (910), '>3.000' (punto de MILLAR, 112) y '0' (42).
    '>3.000' -> 3000 (mas de 3000 unidades). El punto es separador de millar, NO decimal."""
    s = str(x).strip()
    if not s: return None
    s = s.lstrip('>').strip()       # quita el '>' de '>3.000'
    s = s.replace('.', '')          # quita el punto de millar: '3.000' -> '3000'
    try: return float(s)
    except Exception: return None

# ============================================================
# Celda 4 - carga del catalogo
#   MOLOKA -> Supabase (inventario propio).  Resto -> fichero crudo del buzon.
# ============================================================
problematicos = []
chase_sueltos = []   # chase suelto descartado por la regla de negocio (va a la hoja Descartados)
filas = []
fuera_disp = 0

if PROVEEDOR == 'MOLOKA':
    print("=== MOLOKA: leyendo inventario propio de Supabase ===")
    _rows = []; _d = 0
    while True:
        res = sb.table('productos').select('ean,nombre,marca,pvd,es_chase,asin') \
                .eq('activo', True).range(_d, _d+999).execute()
        if not res.data: break
        _rows.extend(res.data)
        if len(res.data) < 1000: break
        _d += 1000
    print(f"Inventario propio (activos): {len(_rows)} filas")
    for p in _rows:
        marca_p = str(p.get('marca','') or '')
        if MARCA and MARCA.strip().upper() != 'TODAS':
            if MARCA.lower() not in marca_p.lower():
                continue
        ean_in = str(p.get('ean') or '').strip()
        if not ean_in:
            continue
        core = core_ean(ean_in)
        if (not core.isdigit()) or len(core) not in (12, 13):
            problematicos.append({'EAN':ean_in, 'Cabecera':p.get('nombre',''),
                                  'Motivo':f'EAN forma rara (len={len(core)})'}); continue
        filas.append({'ean_in':ean_in, 'core':core, 'variantes':variantes_ean(core),
                      'nombre':p.get('nombre','') or '', 'marca':marca_p or MARCA,
                      'pa':_num(p.get('pvd')), 'es_chase':bool(p.get('es_chase'))})
    print(f"A escanear: {len(filas)} | EAN problematicos: {len(problematicos)} | "
          f"CHASE: {sum(f['es_chase'] for f in filas)}")
else:
    if PERFIL['tipo'] == 'auto':
        # ZENTRADA: el extracto puede llegar como .xlsx o como .csv. Se detecta por
        # los bytes (un .xlsx es un ZIP -> empieza por 'PK'); el resto se trata como
        # CSV. Asi no depende del nombre ni de la extension del fichero subido.
        try:
            with open(catalogo_local, 'rb') as _fp:
                _es_excel = _fp.read(2) == b'PK'
        except Exception:
            _es_excel = False
        if _es_excel:
            cat = pd.read_excel(catalogo_local, sheet_name=PERFIL.get('sheet', 0),
                                header=PERFIL.get('header', 0), dtype=str).fillna('')
        else:
            cat = pd.read_csv(catalogo_local, sep=PERFIL.get('sep', ','), dtype=str,
                              encoding='utf-8-sig', on_bad_lines='skip').fillna('')
    elif PERFIL['tipo'] == 'excel':
        cat = pd.read_excel(catalogo_local, sheet_name=PERFIL['sheet'],
                            header=PERFIL['header'], dtype=str).fillna('')
    else:
        cat = pd.read_csv(catalogo_local, sep=PERFIL.get('sep', ';'), dtype=str,
                          encoding='utf-8', on_bad_lines='skip').fillna('')
    cat.columns = [str(c).strip() for c in cat.columns]   # BEMS trae espacios en los nombres
    print(f"Catalogo crudo: {len(cat)} filas")
    N_CRUDO = len(cat)

    if PERFIL.get('deteccion') == 'tolerante':
        det = detectar_columnas(cat)
        print(f"Deteccion tolerante -> EAN={det['ean']!r} precio={det['precio']!r} "
              f"nombre={det['nombre']!r} marca={det['marca']!r} stock={det['stock']!r}")
        if not det['ean'] or not det['precio']:
            print("ERROR: no pude detectar la columna de EAN o de precio en este fichero.")
            print("Revisa el catalogo (o pasaselo a Claude para normalizarlo). Fin.")
            sys.exit(0)
        cM, cE, cN, cP, cS = (det['marca'], det['ean'], det['nombre'] or det['ean'],
                              det['precio'], det['stock'])
        _tolerante = True
    else:
        cM, cE, cN, cP, cS = (PERFIL['col_marca'], PERFIL['col_ean'], PERFIL['col_nombre'],
                              PERFIL['col_pa'], PERFIL['col_stock'])
        _tolerante = False

    # filtro 1: marca. Si el recado trae 'filtros' (director), NO filtramos aqui por
    # marca: el motor decide fila a fila mas abajo (varias marcas + idioma + estado).
    # Si no, filtro de marca simple de siempre (escaneo manual de Fernando).
    def _pasa_filtros(row):
        # Reglas del director. Para TCG: Oferta/Saldo entran SIEMPRE (cualquier marca);
        # Disponible entra solo si la marca esta en 'marcas', o en 'marcas_es' Y ademas
        # el idioma es Espanol (Magic / Yu-Gi-Oh solo en espanol explicito).
        est = str(row.get(PERFIL.get('col_estado'), '')).strip()
        if est in (FILTROS.get('incluir_estados') or []):
            return True
        marca_row = str(row.get(cM, '')).lower() if cM else ''
        for m in (FILTROS.get('marcas') or []):
            if m.lower() in marca_row:
                return True
        marcas_es = FILTROS.get('marcas_es') or []
        if marcas_es:
            col_idi = FILTROS.get('col_idioma')
            idi = str(row.get(col_idi, '')).strip().lower() if col_idi else ''
            if idi in ('español', 'espanol'):
                for m in marcas_es:
                    if m.lower() in marca_row:
                        return True
        return False

    if FILTROS:
        sel = cat.copy()
        print(f"Motor de filtros activo (director): {len(sel)} filas a evaluar")
    elif MARCA and MARCA.strip().upper() != 'TODAS' and cM is not None:
        sel = cat[cat[cM].str.contains(MARCA, case=False, na=False)].copy()
        print(f"Marca '{MARCA}': {len(sel)} filas")
    else:
        sel = cat.copy()
        print(f"Sin filtro de marca (TODAS): {len(sel)} filas")

    # filtro 2: disponibilidad (estado permitido si aplica + stock>0) + EAN valido
    for _, row in sel.iterrows():
        if PERFIL.get('estados_ok'):
            if str(row.get(PERFIL['col_estado'], '')).strip() not in PERFIL['estados_ok']:
                fuera_disp += 1; continue
        if FILTROS and not _pasa_filtros(row):
            fuera_disp += 1; continue
        if PERFIL.get('sin_columna_stock') or (_tolerante and cS is None):
            stock = 1.0     # sin columna de stock -> se asume disponible
        elif PERFIL.get('stock_especial') == 'osma':
            stock = _stock_osma(row.get(cS, ''))
        else:
            stock = _num(row.get(cS, ''))
        if stock is None or stock <= 0:
            fuera_disp += 1; continue
        ean_in = str(row[cE]).strip()
        # Regla del chase: el SUELTO se descarta (solo se compra en caja de 6).
        _es_case, _es_caja6, _descartar = clasificar_chase(row.get(cN, ''), ean_in)
        if _descartar:
            chase_sueltos.append({'EAN': ean_in, 'Cabecera': row.get(cN, ''),
                                  'Motivo': 'Chase SUELTO descartado (solo se compra en caja de 6)'})
            continue
        core = core_ean(ean_in)
        if (not core.isdigit()) or len(core) not in (12, 13):
            problematicos.append({'EAN':ean_in, 'Cabecera':row.get(cN,''),
                                  'Motivo':f'EAN forma rara (len={len(core)})'}); continue
        if _tolerante:
            pa = _parse_precio_libre(row.get(cP, ''))
        elif PERFIL.get('precio_especial') == 'eur':
            pa = _num_eur(row.get(cP, ''))
        else:
            pa = _num(row.get(cP, ''))
        if PERFIL.get('col_pa_promo'):                    # DBLine: promo si >0, si no Listino
            promo = _num(row.get(PERFIL['col_pa_promo'], ''))
            if promo and promo > 0: pa = promo
        vol = None
        if PERFIL.get('col_volumen'):
            try:
                mv = _mejor_volumen(row.get(PERFIL['col_volumen'], ''))
                # solo si es un descuento REAL: rebaja el suelto pero no es un valor basura absurdo
                if mv and pa and (pa*MIN_RATIO_LOTE) <= mv[1] < pa:
                    vol = {'uds': mv[0], 'pa': round(mv[1], 4)}
            except Exception:
                vol = None
        _cu = PERFIL.get('col_url')
        url = str(row.get(_cu,'')).strip() if _cu else ''
        filas.append({'ean_in':ean_in, 'core':core, 'variantes':variantes_ean(core),
                      'nombre':row.get(cN,''), 'marca':MARCA, 'pa':pa,
                      'es_chase':_es_case, 'es_caja6':_es_caja6, 'volumen':vol, 'url':url})
    print(f"Disponibles a escanear: {len(filas)} | fuera por estado/stock: {fuera_disp} | "
          f"EAN problematicos: {len(problematicos)} | CHASE: {sum(f['es_chase'] for f in filas)}")
    if chase_sueltos:
        print(f"Chase SUELTO descartado (solo se compra en caja de 6): {len(chase_sueltos)} "
              f"-> listados en la hoja 'Descartados'")

# ============================================================
# DEDUP del proveedor: UNA sola fila por clave de memoria
# ------------------------------------------------------------
# Tras la regla del chase todavia puede haber VARIAS filas con la misma clave
# (mismo EAN + misma categoria) y precios distintos. Eso ya NO es chase: es
# BASURA DE DATOS del proveedor. Caso real de OcioStock: el mismo producto,
# con el MISMO nombre, mandado 3 veces a 37,99 / 8,50 / 6,99.
# La memoria guarda un solo precio por clave, asi que sin deduplicar siempre
# habria una fila que no cuadra -> 'cambio_precio' eterno y re-escaneo.
# Nos quedamos con la MAS BARATA: es el mejor coste y, sobre todo, es
# DETERMINISTA, que es lo que corta el bucle. Las descartadas se listan.
# ============================================================
_uni, _dups = {}, []
for f in filas:
    k = (norm(f['core']), bool(f['es_chase']))
    prev = _uni.get(k)
    if prev is None:
        _uni[k] = f
        continue
    if f['pa'] is not None and (prev['pa'] is None or f['pa'] < prev['pa']):
        barato, caro = f, prev
    else:
        barato, caro = prev, f
    _uni[k] = barato
    _dups.append({'EAN': caro['ean_in'], 'Cabecera': caro.get('nombre', ''),
                  'Motivo': f"Duplicado del proveedor: me quedo con {barato['pa']} "
                            f"(esta venia a {caro['pa']})"})
if _dups:
    filas = list(_uni.values())
    print(f"Duplicados del proveedor: {len(_dups)} filas descartadas (misma clave, "
          f"varios precios) -> me quedo con la MAS BARATA. Van a la hoja 'Descartados'.")

# ============================================================
# Celda 5 - cruce con Supabase (productos propios + stock para 'En mi BD')
# ============================================================
sup = {}
try:
    _rows = []; _d = 0
    while True:
        res = sb.table('productos').select('ean,asin,iva_pct,stock_moloka,stock_fba').eq('activo',True).range(_d, _d+999).execute()
        if not res.data: break
        _rows.extend(res.data)
        if len(res.data) < 1000: break
        _d += 1000
    for p in _rows:
        if p.get('ean'): sup[norm(p['ean'])] = p
    print(f"Supabase: {len(sup)} EANs propios")
except Exception as ex:
    print("AVISO sin cruce Supabase:", ex)

def _sup(core):
    for v in [norm(core), core, '0'+core]:
        if v in sup: return sup[v]
    return None
def iva_es_de(core):
    s = _sup(core)
    if s and s.get('iva_pct') not in (None,''):
        try: return float(s['iva_pct'])
        except Exception: pass
    return IVA_DEFAULT_ES
def es_propio(core): return _sup(core) is not None
def en_bd_txt(core):
    s = _sup(core)
    if not s: return ''
    return f"OK Alm:{s.get('stock_moloka',0)} FBA:{s.get('stock_fba',0)}"

# ============================================================
# Celda 5b - memoria viva del proveedor (nuevos / reaparicion / cambio / agotado)
# ============================================================
mem = {}   # (ean_norm, es_case) -> {'pa':, 'presente':, 'ean_db':}
try:
    _rows = []; _d = 0
    while True:
        res = (sb.table('escaner_memoria')
                 .select('ean,es_case,pa,presente')
                 .eq('proveedor', PROVEEDOR)
                 .range(_d, _d+999).execute())
        if not res.data: break
        _rows.extend(res.data)
        if len(res.data) < 1000: break
        _d += 1000
    for m in _rows:
        mem[(norm(m['ean']), bool(m['es_case']))] = {
            'pa': m.get('pa'),
            'presente': bool(m.get('presente', True)),
            'ean_db': m['ean'],
        }
    print(f"Memoria {PROVEEDOR}/{MARCA}: {len(mem)} EANs conocidos")
except Exception as ex:
    print("AVISO: no se pudo leer la memoria, se trata todo como NUEVO:", ex)

filas_hoy = list(filas)
claves_hoy = {(norm(f['core']), bool(f['es_chase'])) for f in filas_hoy}

def estado_mem(f):
    k = (norm(f['core']), bool(f['es_chase']))
    if k not in mem: return 'nuevo'
    info = mem[k]
    if not info['presente']: return 'reaparicion'
    pa_ant = info['pa']
    if f['pa'] is None or pa_ant is None: return 'sin_cambios'
    if abs(float(f['pa']) - float(pa_ant)) > 0.01: return 'cambio_precio'
    return 'sin_cambios'

for f in filas:
    f['_estado_mem'] = estado_mem(f)
cnt = Counter(f['_estado_mem'] for f in filas)
print(f"Nuevos: {cnt.get('nuevo',0)} | Reaparecidos: {cnt.get('reaparicion',0)} | "
      f"Cambio precio: {cnt.get('cambio_precio',0)} | Sin cambios: {cnt.get('sin_cambios',0)}")

ausentes = [(k, info) for k, info in mem.items() if info['presente'] and k not in claves_hoy]
print(f"Agotados/desaparecidos desde la ultima vez: {len(ausentes)}")

if MODO == 'nuevos':
    filas = [f for f in filas if f['_estado_mem'] in ('nuevo','reaparicion','cambio_precio')]
print(f"A escanear (modo '{MODO}'): {len(filas)} productos")

# ============================================================
# CHECKPOINT: id comun para la cache de rank (Fase 1) y el progreso (Fase 2).
# El id identifica ESTE escaneo (mismo catalogo + mismos parametros). Al relanzar un
# escaneo cortado reanuda; con otro catalogo empieza limpio. TODO CON RED: si la cache
# falla, se consulta Keepa normal y el escaner funciona como hoy.
# ============================================================
import hashlib
_eans_filas = sorted(str(f['ean_in']) for f in filas)
_ckpt_id = hashlib.md5(('|'.join([PROVEEDOR, str(MARCA), MODO, str(RANK_MAXIMO)] + _eans_filas)).encode()).hexdigest()[:16]

# --- Cache de rank (Fase 1): lo unico caro de la Fase 1 es consultar el rank a Keepa.
# Guardamos por lote lo minimo que usa registra() (asin, rank actual, rank 90, EANs).
# Si el escaneo se corta y se relanza, la Fase 1 se rehace LEYENDO de aqui: 0 tokens.
RANKCACHE_PATH = f'{CARPETA_CKPT}/_rankcache_{_ckpt_id}.json'
_rankcache = {}
try:
    _d = sb.storage.from_(BUCKET).download(RANKCACHE_PATH)
    _rankcache = json.loads(_d.decode('utf-8')) or {}
    if _rankcache:
        print(f">>> Cache de rank: {len(_rankcache)} lotes ya consultados (reanudo Fase 1 sin re-pagar).")
except Exception:
    _rankcache = {}

def _clave_lote(codigos, domain):
    return hashlib.md5((domain + '|' + '|'.join(map(str, codigos))).encode()).hexdigest()[:16]

def _reduce_prod(prod):
    # Solo lo que necesita registra(): asin, stats(current/avg90), eanList, upcList.
    st = prod.get('stats') or {}
    return {'asin': prod.get('asin'),
            'stats': {'current': st.get('current'), 'avg90': st.get('avg90')},
            'eanList': prod.get('eanList'), 'upcList': prod.get('upcList')}

def keepa_rank(codigos, domain='ES'):
    clave = _clave_lote(codigos, domain)
    if clave in _rankcache:
        return _rankcache[clave]                 # de la caja: 0 tokens
    prods = keepa_query(codigos, product_code_is_asin=False, domain=domain, stats=90, history=0)
    if prods is None:
        return None
    _rankcache[clave] = [_reduce_prod(p) for p in prods]
    return _rankcache[clave]

def _guardar_rankcache():
    try:
        sb.storage.from_(BUCKET).upload(RANKCACHE_PATH, json.dumps(_rankcache).encode(),
                                        {'upsert': 'true', 'content-type': 'application/json'})
    except Exception as _e:
        print("AVISO cache de rank (no guardada, sigo igual):", _e)

# ============================================================
# Celda 6 - FASE 1: filtro de rank (Keepa ES, 1 token)
# ============================================================
IDX_RANK, IDX_NEW, IDX_BBOX_LAND = 3, 1, 18   # 18 = BUY_BOX_SHIPPING (buy box CON envio = aterrizada, como el v1)
candidatos, ambiguos = {}, []
pasan, sin_rank, no_encontrados = {}, [], []

if filas:
    def pasa_filtro(r_act, r_90):
        return any(r and r>0 and r<=RANK_MAXIMO for r in (r_act, r_90))

    var_norm = {f['ean_in']: {norm(v) for v in f['variantes']} for f in filas}
    fila_por_ean = {f['ean_in']: f for f in filas}

    def cod_pref(f): return f['core']
    def cods_reserva(f): return [v for v in f['variantes'] if v != cod_pref(f)]

    def keyrank(c): return c['r_90'] if c['r_90'] and c['r_90']>0 else 10**12
    def registra(prod, pool, vistos):
        asin = prod.get('asin')
        if not asin: return
        st = prod.get('stats') or {}
        cur, a90 = st.get('current') or [], st.get('avg90') or []
        r_act = cur[IDX_RANK] if len(cur)>IDX_RANK else -1
        r_90  = a90[IDX_RANK] if len(a90)>IDX_RANK else -1
        eans = {norm(str(e)) for e in (prod.get('eanList') or [])+(prod.get('upcList') or [])}
        for ein in pool:
            if not (var_norm[ein] & eans): continue
            f = fila_por_ean[ein]
            cand = {'ean_in':ein,'asin':asin,'r_act':r_act,'r_90':r_90,'fila':f,'propio':es_propio(f['core'])}
            if ein in candidatos:
                prev = candidatos[ein]
                ambiguos.append({'EAN':ein,'asin_elegido':cand['asin'] if keyrank(cand)<keyrank(prev) else prev['asin']})
                if keyrank(cand)<keyrank(prev): candidatos[ein]=cand
            else: candidatos[ein]=cand
            vistos.add(ein)

    def pasada(cod_por_ean, etiqueta):
        pool = list(cod_por_ean.keys())
        codigos = sorted({cod_por_ean[e] for e in pool})
        lotes = [codigos[i:i+LOTE_FASE1] for i in range(0,len(codigos),LOTE_FASE1)]
        vistos = set()
        print(f"{etiqueta}: {len(pool)} productos, {len(codigos)} codigos, {len(lotes)} lotes")
        for n,lote in enumerate(lotes,1):
            prods = keepa_rank(lote, domain='ES')
            if prods is None:
                print(f"  lote {n}/{len(lotes)} NO resuelto tras reintentos -> se salta este lote")
                continue
            for prod in prods: registra(prod, pool, vistos)
            if n % 5 == 0: _guardar_rankcache()
            print(f"  lote {n}/{len(lotes)} | tokens {api.tokens_left}")
            if _cerca_del_corte():
                _guardar_rankcache()
                print(">>> Cerca del corte de GitHub: guardo el rank y me relanzo para seguir.")
                _relanzarme(); sys.exit(0)
        _guardar_rankcache()
        return vistos

    vistos = pasada({f['ean_in']: cod_pref(f) for f in filas}, "Fase 1 (1 codigo/producto)")
    for ronda in (0, 1):
        faltan = {f['ean_in'] for f in filas} - vistos
        rint = {}
        for f in filas:
            if f['ean_in'] in faltan:
                rs = cods_reserva(f)
                if len(rs) > ronda: rint[f['ean_in']] = rs[ronda]
        if rint:
            vistos |= pasada(rint, f"Fase 1 reintento {ronda+1} (variante alternativa)")

    for ein,c in candidatos.items():
        tiene = (c['r_act'] and c['r_act']>0) or (c['r_90'] and c['r_90']>0)
        if c['propio'] or pasa_filtro(c['r_act'],c['r_90']): pasan[ein]=c
        elif (not tiene) and INCLUIR_SIN_RANK: pasan[ein]=c
        elif not tiene: sin_rank.append(c)
    for f in filas:
        if f['ean_in'] not in vistos:
            no_encontrados.append({'EAN':f['ean_in'],'Cabecera':f['nombre'],'Motivo':'Keepa sin ASIN'})
amb_eans = {a['EAN'] for a in ambiguos}
print(f"\nCon ASIN: {len(candidatos)} | PASAN: {len(pasan)} | sin rank: {len(sin_rank)} | "
      f"no encontrados: {len(no_encontrados)} | ambiguos: {len(ambiguos)}")

# ============================================================
# Celda 7 - FASE 2: informe ES/IT/FR (3 tok/pais, buybox sin offers)
# ============================================================
def datos_pais(asin, dom):
    res = keepa_query([asin], product_code_is_asin=True, domain=dom, stats=90, history=0, buybox=True)
    if not res: return None
    p = res[0]; st = p.get('stats') or {}
    cur, a90 = st.get('current') or [], st.get('avg90') or []
    # Buy box ATERRIZADA: current[18] (BUY_BOX_SHIPPING) es el precio CON envio,
    # lo que paga el cliente. Fallback a buyBoxPrice (pelado) si el 18 no viene.
    # Mismo mecanismo que el v1 en produccion (moloka_actualizar_nube.py, 1932-1943).
    bb_land = cur[IDX_BBOX_LAND] if len(cur)>IDX_BBOX_LAND else None
    bb_pel  = st.get('buyBoxPrice')
    if bb_land and bb_land>0:
        precio = bb_land/100
        canal = 'BB-FBA' if st.get('buyBoxIsFBA') else 'BB-FBM'
    elif bb_pel and bb_pel>0:
        precio = bb_pel/100
        canal = 'BB-FBA' if st.get('buyBoxIsFBA') else 'BB-FBM'
    else:
        new = cur[IDX_NEW] if len(cur)>IDX_NEW else -1
        precio = new/100 if new and new>0 else None
        canal = 'SIN BB' if precio else 'sin precio'
    fba = p.get('fbaFees') or {}
    fee = fba.get('pickAndPackFee')
    def _pos(x): return x if (x is not None and x>=0) else None
    return {'precio':precio,'canal':canal,'ref_pct':p.get('referralFeePercentage'),
            'fee':fee/100 if fee else None,
            'rank_act':cur[IDX_RANK] if len(cur)>IDX_RANK else -1,
            'rank90':a90[IDX_RANK] if len(a90)>IDX_RANK else -1,
            'n_of':_pos(st.get('totalOfferCount')),
            'vendidos':p.get('monthlySold'),
            'titulo':(p.get('title') or '')}

lista = list(pasan.values())

# === CHECKPOINT: reanudar la Fase 2 si un escaneo grande se corto a medias ===
# Guarda el progreso cada CKPT_CADA candidatos en una carpeta APARTE (escaner_ckpt/,
# que el boton NO vacia al relanzar). Al arrancar, si hay checkpoint de ESTE mismo
# escaneo (mismos candidatos), reanuda desde donde quedo. Todo CON RED: si algo del
# checkpoint falla, el escaner sigue como siempre (empieza de cero, no se rompe).
import hashlib
CKPT_CADA = 50
CKPT_PATH = f'{CARPETA_CKPT}/_ckpt_{_ckpt_id}.json'   # _ckpt_id: el mismo de la Fase 1

infos = []
_eans_hechos = set()
try:
    _d = sb.storage.from_(BUCKET).download(CKPT_PATH)
    _prev = json.loads(_d.decode('utf-8'))
    if isinstance(_prev, list) and _prev:
        infos = _prev
        _eans_hechos = {str(it.get('ean')) for it in infos}
        print(f">>> CHECKPOINT: reanudo un escaneo a medias ({len(infos)} de {len(lista)} ya hechos).")
except Exception:
    pass   # sin checkpoint o ilegible -> empezar de cero, exactamente como hoy

def _guardar_ckpt():
    try:
        sb.storage.from_(BUCKET).upload(CKPT_PATH, json.dumps(infos).encode('utf-8'),
                                        {'upsert': 'true', 'content-type': 'application/json'})
    except Exception as _e:
        print("AVISO checkpoint (no se guardo, sigo igual):", _e)

print(f"Fase 2: {len(lista)} candidatos x 3 paises"
      + (f" | {len(infos)} ya hechos, faltan {len(lista)-len(infos)}" if infos else ""))
_nuevos = 0
for i,c in enumerate(lista,1):
    if c['ean_in'] in _eans_hechos:
        continue                       # ya escaneado en una pasada anterior -> saltar
    f = c['fila']
    item = {'nombre':f['nombre'],'ean':c['ean_in'],'asin':c['asin'],'marca':f['marca'],
            'pa':f['pa'],'core':f['core'],'es_chase':f['es_chase'],'propio':c['propio'],
            'volumen':f.get('volumen'),'url':f.get('url',''),'titulo_amz':'',
            'ambiguo':c['ean_in'] in amb_eans,'paises':{},
            'case_de_6':bool(f.get('es_caja6'))}
    for dom in ('ES','IT','FR'):
        d = datos_pais(c['asin'], dom)
        if d:
            item['paises'][dom] = d
            if dom=='ES' and not item['titulo_amz']:
                item['titulo_amz'] = d.get('titulo','')
    item['coincide'] = _coincide_titulo(item['nombre'], item['titulo_amz'])
    infos.append(item)
    _nuevos += 1
    if i%50==0:
        print(f"  {i}/{len(lista)} | tokens {api.tokens_left}")
    if _nuevos % CKPT_CADA == 0:
        _guardar_ckpt()
    if _cerca_del_corte():
        _guardar_ckpt()
        print(">>> Cerca del corte de GitHub: guardo el progreso y me relanzo para seguir.")
        _relanzarme(); sys.exit(0)
print(f"Fase 2 completa: {len(infos)} productos")
# Escaneo completo: el checkpoint ya no hace falta -> borrar
try: sb.storage.from_(BUCKET).remove([CKPT_PATH, RANKCACHE_PATH])
except Exception: pass

# ============================================================
# Celda 7.5 - CHASE FUNKO de HEO: puente escaner_chase_asin (ASIN a mano)
# Los que ya tienen ASIN se ESCANEAN (valorados /6, como una caja de 6); los
# pendientes van a la pestana Chase_manual. La puente esta CERRADA (RLS): se lee
# con SERVICE_KEY, NUNCA con la anon (lleva el precio de coste).
# ============================================================
chase_pendientes = []
if PROVEEDOR == 'HEO':
    _svc = os.environ.get('SUPABASE_SERVICE_KEY')
    if not _svc:
        print("AVISO: sin SUPABASE_SERVICE_KEY -> no leo la puente de chase (ni ASIN ni pestana).")
    else:
        try:
            sb_svc = create_client(os.environ['SUPABASE_URL'], _svc)
            _rows = (sb_svc.table('escaner_chase_asin')
                     .select('producto_heo,nombre,ean_caja,precio_caja,estado,imagen,link_amazon,asin')
                     .execute().data) or []
            _con_asin = [x for x in _rows if (x.get('asin') or '').strip() and x.get('estado') == 'disponible']
            chase_pendientes = [x for x in _rows if not (x.get('asin') or '').strip()]
            print(f">>> Puente chase: {len(_rows)} total | {len(_con_asin)} con ASIN disponibles | "
                  f"{len(chase_pendientes)} pendientes de ASIN.")
            for x in _con_asin:
                _as = x['asin'].strip()
                item = {'nombre': x.get('nombre', ''), 'ean': str(x.get('ean_caja') or ''), 'asin': _as,
                        'marca': 'Funko', 'pa': _num(x.get('precio_caja')), 'core': str(x.get('ean_caja') or ''),
                        'es_chase': True, 'propio': False, 'volumen': None, 'url': x.get('link_amazon', ''),
                        'titulo_amz': '', 'ambiguo': False, 'paises': {}, 'case_de_6': True}
                for dom in ('ES', 'IT', 'FR'):
                    d = datos_pais(_as, dom)
                    if d:
                        item['paises'][dom] = d
                        if dom == 'ES' and not item['titulo_amz']:
                            item['titulo_amz'] = d.get('titulo', '')
                item['coincide'] = _coincide_titulo(item['nombre'], item['titulo_amz'])
                infos.append(item)
            if _con_asin:
                print(f">>> Chase con ASIN escaneados y anadidos a resultados: {len(_con_asin)} (valorados /6).")
        except Exception as _e:
            print("AVISO: no se pudo leer/escanear la puente de chase (sigo con el escaneo normal):", _e)

# ============================================================
# Celda 8 - calculo (decision + orden por margen ES)
# ============================================================
def decision_de(margen):
    if margen is None: return 'Sin datos'
    if margen*100 >= 10: return 'COMPRAR'
    if margen*100 >= 1:  return 'VALORAR'
    return 'NO COMPRAR'

registros = []
for item in infos:
    iva = {'ES':iva_es_de(item['core']),'IT':IVA_IT,'FR':IVA_FR}
    pa = item['pa']
    if item.get('case_de_6') and pa:
        pa = pa / UNIDADES_CASE_TCG
    item['_pa_efectivo'] = pa
    margen_es = None; paises_out = {}
    for dom in ('ES','IT','FR'):
        d = item['paises'].get(dom)
        if d and d.get('precio') and pa and d.get('ref_pct') is not None and d.get('fee') is not None:
            r = calc_rentabilidad(d['precio'], pa, d['ref_pct'], d['fee'], iva[dom],
                                  almacen=ALMACEN, com_digitales=COM_DIGITALES)
            paises_out[dom] = {**d,'iva':iva[dom],'beneficio':r['beneficio'],
                               'roi':r['roi'],'margen':r['margen'],'decision':decision_de(r['margen'])}
            if dom == 'ES': margen_es = r['margen']
        elif d:
            paises_out[dom] = {**d,'iva':iva[dom],'beneficio':None,'roi':None,'margen':None,'decision':'Sin datos'}
    item['_paises_calc'] = paises_out
    item['_margen_es'] = margen_es
    registros.append(item)

registros.sort(key=lambda x: x['_margen_es'] if x['_margen_es'] is not None else -10**9, reverse=True)
n_mandar = sum(1 for it in registros for d in it['_paises_calc'].values() if d['decision'] == 'COMPRAR')
print(f"Productos: {len(registros)} | filas COMPRAR (algun pais): {n_mandar}")

# ============================================================
# Celda 9 - Excel final (1 fila por pais, formulas vivas, semaforo)
# ============================================================
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.formatting.rule import FormulaRule, CellIsRule

COLS = ['Nombre','EAN','ASIN','Marca','PA (€)','País','Rank actual','Rank 90d','Vendidos/mes',
        'Precio venta (€)','Canal BB','Nº ofertas','% Comisión',
        'Com. Amazon (€)','Fee Logística (€)','Almacén (€)','Promo activa',
        'Beneficio (€)','ROI','Margen','Decisión','En mi BD','EAN ambiguo','Amazon (título)','Coincide','OcioStock']
L = {name:get_column_letter(i+1) for i,name in enumerate(COLS)}
DOM_AMZ = {'ES':'amazon.es','IT':'amazon.it','FR':'amazon.fr'}

wb = Workbook(); ws = wb.active; ws.title='Análisis'
ws.append(COLS)

r = 1
for item in registros:
    en_bd = en_bd_txt(item['core'])
    amb = 'AMBIGUO' if item['ambiguo'] else ''
    for dom in ('ES','IT','FR'):
        d = item['_paises_calc'].get(dom)
        if not d:
            d = {'rank_act':None,'rank90':None,'vendidos':None,'precio':None,'canal':'sin datos',
                 'n_of':None,'ref_pct':None,'fee':None,'iva':None,'decision':'Sin datos'}
        r += 1
        pct = (d['ref_pct']/100*COM_DIGITALES) if d.get('ref_pct') is not None else None
        div = (1+d['iva']) if d.get('iva') else None
        ws.append([
            item['nombre'], item['ean'], item['asin'], item['marca'], item['_pa_efectivo'], dom,
            d['rank_act'] if d['rank_act'] and d['rank_act']>0 else None,
            d['rank90'] if d['rank90'] and d['rank90']>0 else None,
            d['vendidos'], d['precio'], d['canal'], d['n_of'], pct,
            f"={L['Precio venta (€)']}{r}*{L['% Comisión']}{r}" if pct is not None else None,
            d['fee'], ALMACEN, None,
            (f"=({L['Precio venta (€)']}{r}/{div})-{L['PA (€)']}{r}-{L['Com. Amazon (€)']}{r}"
             f"-{L['Fee Logística (€)']}{r}-{L['Almacén (€)']}{r}") if (div and d['precio'] and pct is not None) else None,
            f"={L['Beneficio (€)']}{r}/{L['PA (€)']}{r}" if (div and d['precio'] and pct is not None and item['pa']) else None,
            f"={L['Beneficio (€)']}{r}/{L['Precio venta (€)']}{r}" if (div and d['precio'] and pct is not None) else None,
            d['decision'], en_bd, amb,
            item.get('titulo_amz',''), item.get('coincide','?'),
            ('Ver ficha ↗' if item.get('url') else '')])
        cell = ws.cell(row=r, column=3)
        cell.hyperlink = f"https://www.{DOM_AMZ[dom]}/dp/{item['asin']}"
        cell.font = Font(color='0563C1', underline='single')
        if item.get('url'):
            cocel = ws.cell(row=r, column=len(COLS))   # ultima columna = OcioStock
            cocel.hyperlink = item['url']
            cocel.font = Font(color='0563C1', underline='single')

last = ws.max_row
def fmt(colname, code):
    c = L[colname]
    for row in range(2,last+1):
        ws[f'{c}{row}'].number_format = code
for nm in ['PA (€)','Precio venta (€)','Com. Amazon (€)','Fee Logística (€)','Almacén (€)','Beneficio (€)']:
    fmt(nm,'0.00')
fmt('% Comisión','0.00%'); fmt('ROI','0.0%'); fmt('Margen','0.0%')

for c in range(1,len(COLS)+1):
    ws.cell(row=1,column=c).font = Font(bold=True)
anchos = {'Nombre':50,'EAN':14,'ASIN':12,'Marca':12,'En mi BD':20,'Decisión':15,
          'Amazon (título)':50,'Coincide':11,'OcioStock':13}
for nm,w in anchos.items(): ws.column_dimensions[L[nm]].width = w

ws.freeze_panes = 'A2'

def _cf_fill(hexcolor): return PatternFill(start_color=hexcolor, end_color=hexcolor, fill_type='solid')
# Tabla + semaforo SOLO si hay al menos una fila de datos. Un escaneo 'nuevos' sin
# novedades deja registros vacio -> last=1 -> rango invertido (U2:U1) que PETA openpyxl.
if last >= 2:
    tab = Table(displayName='T_Analisis', ref=f"A1:{get_column_letter(len(COLS))}{last}")
    tab.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=False,
                                        showColumnStripes=False, showFirstColumn=False, showLastColumn=False)
    ws.add_table(tab)
    dec = L['Decisión']; rng_dec = f'{dec}2:{dec}{last}'
    ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO COMPRAR",{dec}2))'],
        fill=_cf_fill('FFC7CE'), font=Font(color='9C0006'), stopIfTrue=True))
    ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("VALORAR",{dec}2))'],
        fill=_cf_fill('FFEB9C'), font=Font(color='9C6500'), stopIfTrue=True))
    ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("COMPRAR",{dec}2))'],
        fill=_cf_fill('C6EFCE'), font=Font(color='006100'), stopIfTrue=True))
    ws.conditional_formatting.add(rng_dec, FormulaRule(formula=[f'ISNUMBER(SEARCH("Sin datos",{dec}2))'],
        fill=_cf_fill('E7E6E6'), font=Font(color='808080'), stopIfTrue=True))
    ws.conditional_formatting.add(f"{L['Margen']}2:{L['Margen']}{last}",
        CellIsRule(operator='greaterThan', formula=['0.1'], font=Font(color='006100')))
    coi = L['Coincide']; rng_coi = f'{coi}2:{coi}{last}'
    ws.conditional_formatting.add(rng_coi, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO",{coi}2))'],
        fill=_cf_fill('FFC7CE'), font=Font(color='9C0006')))
    ws.conditional_formatting.add(f'A2:{get_column_letter(len(COLS))}{last}',
        FormulaRule(formula=['ISODD(INT((ROW()-2)/3))'], fill=_cf_fill('D9D9D9')))

def hoja(nombre, regs):
    w = wb.create_sheet(nombre)
    if regs:
        ks = list(regs[0].keys()); w.append(ks)
        for x in regs: w.append([x.get(k) for k in ks])
    else: w.append(['(vacio)'])
hoja('Descartados', problematicos + no_encontrados + chase_sueltos + _dups)
hoja('Ambiguos', ambiguos)
hoja('Sin_rank', [{'EAN':c['ean_in'],'ASIN':c['asin'],'Nombre':c['fila']['nombre'],
                   'rank_act':c['r_act'],'rank90':c['r_90']} for c in sin_rank])

# ============================================================
# Pestana "Precio por lote": escenario con descuento por VOLUMEN (OcioStock).
# La hoja Analisis se queda igual (precio unitario). Aqui recalculamos el beneficio
# con el precio del LOTE y ponemos a la derecha del todo las unidades minimas para
# lograr ese precio. Solo entran los productos cuyo lote REBAJA el precio suelto.
# ============================================================
COLS_LOTE = ['Nombre','EAN','ASIN','Marca','País','Precio venta (€)','PA suelto (€)',
             'PA lote (€)','Ahorro/ud (€)','Beneficio lote (€)','Margen lote','Decisión lote',
             'Uds. para ese precio']
filas_lote = []
for item in registros:
    vol = item.get('volumen')
    if not vol:
        continue
    pa_lote = vol['pa']; uds = vol['uds']
    pa_suelto = item.get('_pa_efectivo')
    for dom in ('ES','IT','FR'):
        d = item['_paises_calc'].get(dom)
        if not d or not d.get('precio') or d.get('ref_pct') is None or d.get('fee') is None:
            continue
        rr = calc_rentabilidad(d['precio'], pa_lote, d['ref_pct'], d['fee'], d['iva'],
                               almacen=ALMACEN, com_digitales=COM_DIGITALES)
        filas_lote.append([
            item['nombre'], item['ean'], item['asin'], item['marca'], dom,
            round(d['precio'], 2),
            round(pa_suelto, 2) if pa_suelto else None,
            round(pa_lote, 2),
            round(pa_suelto - pa_lote, 2) if pa_suelto else None,
            round(rr['beneficio'], 2),
            round(rr['margen'], 4),
            decision_de(rr['margen']),
            uds,
        ])
filas_lote.sort(key=lambda x: (x[10] if x[10] is not None else -9), reverse=True)

wl = wb.create_sheet('Precio por lote')
wl.append(COLS_LOTE)
for fl in filas_lote:
    wl.append(fl)
for c in range(1, len(COLS_LOTE)+1):
    wl.cell(row=1, column=c).font = Font(bold=True)
if filas_lote:
    LL = {name: get_column_letter(i+1) for i, name in enumerate(COLS_LOTE)}
    lastL = wl.max_row
    for nm in ['Precio venta (€)','PA suelto (€)','PA lote (€)','Ahorro/ud (€)','Beneficio lote (€)']:
        for row in range(2, lastL+1):
            wl[f'{LL[nm]}{row}'].number_format = '0.00'
    for row in range(2, lastL+1):
        wl[f'{LL["Margen lote"]}{row}'].number_format = '0.0%'
    decL = LL['Decisión lote']; rngL = f'{decL}2:{decL}{lastL}'
    wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("NO COMPRAR",{decL}2))'],
        fill=_cf_fill('FFC7CE'), font=Font(color='9C0006'), stopIfTrue=True))
    wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("VALORAR",{decL}2))'],
        fill=_cf_fill('FFEB9C'), font=Font(color='9C6500'), stopIfTrue=True))
    wl.conditional_formatting.add(rngL, FormulaRule(formula=[f'ISNUMBER(SEARCH("COMPRAR",{decL}2))'],
        fill=_cf_fill('C6EFCE'), font=Font(color='006100'), stopIfTrue=True))
    wl.column_dimensions[LL['Nombre']].width = 50
    wl.column_dimensions[LL['Uds. para ese precio']].width = 18
    wl.freeze_panes = 'A2'
print(f"Pestana 'Precio por lote': {len(filas_lote)} filas con descuento por volumen")

# ============================================================
# Pestana "Chase_manual": Funko chase de HEO SIN ASIN todavia. Pega el ASIN en
# Supabase (tabla escaner_chase_asin) usando el enlace de busqueda; la proxima
# corrida ya lo cruza sola y desaparece de aqui.
# ============================================================
if PROVEEDOR == 'HEO':
    wc = wb.create_sheet('Chase_manual')
    COLS_CHASE = ['Nombre', 'Código HEO', 'EAN caja', 'Precio caja (€)', 'Precio /6 (€)',
                  'Estado', 'Imagen', 'Buscar en Amazon', 'ASIN (pégalo en Supabase)']
    wc.append(COLS_CHASE)
    for c in range(1, len(COLS_CHASE) + 1):
        wc.cell(row=1, column=c).font = Font(bold=True)
    rc = 1
    for x in chase_pendientes:
        rc += 1
        _pc = _num(x.get('precio_caja'))
        wc.append([x.get('nombre', ''), x.get('producto_heo', ''), str(x.get('ean_caja') or ''),
                   round(_pc, 2) if _pc else None,
                   round(_pc / UNIDADES_CASE_TCG, 2) if _pc else None,
                   x.get('estado', ''),
                   'Ver imagen ↗' if x.get('imagen') else '',
                   'Buscar ↗' if x.get('link_amazon') else '', ''])
        if x.get('imagen'):
            _ci = wc.cell(row=rc, column=7); _ci.hyperlink = x['imagen']; _ci.font = Font(color='0563C1', underline='single')
        if x.get('link_amazon'):
            _cl = wc.cell(row=rc, column=8); _cl.hyperlink = x['link_amazon']; _cl.font = Font(color='0563C1', underline='single')
    for _cw, _w in ((1, 55), (2, 16), (3, 16), (7, 14), (8, 16), (9, 26)):
        wc.column_dimensions[get_column_letter(_cw)].width = _w
    for _col in (4, 5):
        for _row in range(2, wc.max_row + 1):
            wc.cell(row=_row, column=_col).number_format = '0.00'
    wc.freeze_panes = 'A2'
    print(f"Pestana 'Chase_manual': {len(chase_pendientes)} Funko chase pendientes de ASIN.")

# NOTA: la pestana viaja dentro del Excel, y el Excel solo se guarda si hay
# algun COMPRAR (ver mas abajo). Decidido asi a proposito: los pendientes
# viven en la tabla escaner_chase_asin, que es donde se pegan los ASIN.
# Si no hay ningun COMPRAR, NO se genera ni se sube el Excel (limpieza: un escaneo
# sin chollos no aporta nada y cada Excel ocupa ~2 MB). El REGISTRO en la biblioteca
# se guarda IGUAL (n_comprar=0, fichero=NULL) para no romper la alarma de persistencia.
_sin_excel = (n_mandar == 0)
if _sin_excel:
    print(f"Sin COMPRAR en esta pasada ({n_mandar}): NO genero ni subo el Excel. "
          "El registro en la biblioteca se guarda igual (fichero vacio).")
else:
    wb.save(ARCHIVO_SALIDA)
    print("Guardado local:", ARCHIVO_SALIDA, "| filas:", last-1)

# ============================================================
# SUBIR EL EXCEL A STORAGE + REGISTRAR EN LA BIBLIOTECA (escaner_resultados)
# ============================================================
nombre_xlsx = os.path.basename(ARCHIVO_SALIDA)
ruta_storage = f'{CARPETA_RESULTADOS}/{nombre_xlsx}'
subido_ok = False
if not _sin_excel:
    try:
        with open(ARCHIVO_SALIDA, 'rb') as fp:
            sb.storage.from_(BUCKET).upload(
                ruta_storage, fp.read(),
                {'content-type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 'upsert':'true'})
        # verificar que esta en Storage
        _res = sb.storage.from_(BUCKET).list(CARPETA_RESULTADOS) or []
        subido_ok = any(o.get('name') == nombre_xlsx for o in _res)
        print(f"Excel subido a Storage: {ruta_storage} | verificado: {subido_ok}")
    except Exception as ex:
        print("ATENCION: no se pudo subir el Excel a Storage:", ex)

# RED DE SEGURIDAD: un insert puede devolver OK sin que la fila llegue a persistir.
# No nos fiamos del insert ni del print: releemos la fila por su id (la verdad es la
# BD, no el log) y gritamos si no esta. Hoy NO se conoce ningun caso real: las filas
# que parecian faltar resultaron ser limpieza MANUAL desde la app (comprobado con
# pg_stat_user_tables: 451 insertadas / 435 borradas). Esto cubre el dia que falle
# de verdad. NO tumba la corrida: solo avisa.
_biblioteca_ok = False
_biblioteca_id = None
try:
    _resp_bib = sb.table('escaner_resultados').insert({
        'proveedor': PROVEEDOR, 'marca': MARCA, 'modo': MODO,
        'rank_maximo': RANK_MAXIMO,
        'n_productos': len(registros), 'n_comprar': n_mandar,
        'n_nuevos': cnt.get('nuevo',0), 'n_reaparecidos': cnt.get('reaparicion',0),
        'n_cambios': cnt.get('cambio_precio',0), 'n_agotados': len(ausentes),
        'fichero': ruta_storage if subido_ok else None,
        'tokens_restantes': int(api.tokens_left),
    }).execute()
    _filas_bib = getattr(_resp_bib, 'data', None) or []
    _biblioteca_id = _filas_bib[0].get('id') if _filas_bib else None
    if _biblioteca_id is not None:
        # Verificacion DURA contra la BD (no el objeto del insert, no el log).
        # Va en su PROPIO try: si lo que falla es la RELECTURA, el insert ya fue bien
        # y decir "no se pudo registrar" seria mentira en el log. En ese caso avisamos
        # de que no se pudo verificar y NO damos falsa alarma.
        try:
            _chk_bib = sb.table('escaner_resultados').select('id').eq('id', _biblioteca_id).limit(1).execute()
            _biblioteca_ok = bool(getattr(_chk_bib, 'data', None))
        except Exception as _e_chk:
            print(f"AVISO: el insert SI fue bien (id={_biblioteca_id}) pero no pude releer "
                  f"la fila para verificarla: {_e_chk}")
            _biblioteca_ok = True
    if _biblioteca_ok:
        print(f"Escaneo registrado y VERIFICADO en la biblioteca (escaner_resultados), id={_biblioteca_id}.")
    else:
        print("!!! CRITICO: el insert en escaner_resultados dijo OK pero la BD NO devuelve la fila "
              f"(id={_biblioteca_id}). El escaneo NO quedo en la biblioteca: revisalo.")
except Exception as ex:
    print("!!! CRITICO: no se pudo registrar en escaner_resultados (el Excel puede estar en Storage):", ex)

# ============================================================
# Celda 10 - actualizar la memoria del proveedor (presentes / agotados)
# ============================================================
ahora = datetime.now(timezone.utc).isoformat()
regs = []; vistos_up = set()
if PERFIL.get('efimero'):
    print(f"Perfil EFIMERO ({PROVEEDOR}): NO se escribe en escaner_memoria; ningun proveedor real se ve afectado.")
else:
    for f in filas_hoy:
        k = (PROVEEDOR, norm(f['core']), bool(f['es_chase']))
        if k in vistos_up: continue
        vistos_up.add(k)
        regs.append({'proveedor':PROVEEDOR, 'ean':f['core'], 'es_case':bool(f['es_chase']),
                     'marca':MARCA, 'pa': float(f['pa']) if f['pa'] is not None else None,
                     'presente':True, 'fecha':ahora})
    # Agotados SOLO si el catalogo llego COMPLETO. Blindaje anti-vaciado:
    #  - catalogo vacio (0 filas) -> no marcar (fichero equivocado / marca inexistente)
    #  - catalogo PARCIAL (crudo < UMBRAL_PARCIAL de lo que hay en memoria) -> no marcar
    #    (descarga incompleta). Una REBAJA no reduce el nº de filas crudas -> NO salta aqui.
    if not filas_hoy:
        print("Catalogo vacio (0 productos): NO se marcan agotados (evita falso vaciado de la memoria).")
    elif N_CRUDO is not None and len(mem) > 0 and N_CRUDO < UMBRAL_PARCIAL * len(mem):
        print(f"BLINDAJE: catalogo PARCIAL ({N_CRUDO} filas crudas vs {len(mem)} en memoria, "
              f"<{int(UMBRAL_PARCIAL*100)}%): NO se marcan agotados. Huele a descarga incompleta o "
              f"fichero equivocado; la memoria queda intacta.")
    else:
        for (ean_norm, es_case), info in ausentes:
            k = (PROVEEDOR, ean_norm, es_case)
            if k in vistos_up: continue
            vistos_up.add(k)
            pa_ant = info.get('pa')
            regs.append({'proveedor':PROVEEDOR, 'ean':info['ean_db'], 'es_case':es_case,
                         'marca':MARCA, 'pa': float(pa_ant) if pa_ant is not None else None,
                         'presente':False, 'fecha':ahora})
    if not regs:
        print("Memoria sin cambios.")
    else:
        n_ok = 0
        for i2 in range(0, len(regs), 500):
            lote = regs[i2:i2+500]
            try:
                sb.table('escaner_memoria').upsert(lote, on_conflict='proveedor,ean,es_case').execute()
                n_ok += len(lote)
            except Exception as ex:
                print(f"  AVISO lote memoria {i2//500+1}: {ex}")
        n_pres = sum(1 for x in regs if x['presente']); n_aus = len(regs) - n_pres
        print(f"Memoria actualizada: {n_ok}/{len(regs)} ({n_pres} presentes, {n_aus} agotados) [{PROVEEDOR}/{MARCA}]")

# ============================================================
# LIMPIAR EL BUZON DEL ESCANER (recado + catalogo) - VERIFICADO
# Solo si el Excel se subio bien (si no, se deja para reintentar).
# ============================================================
def _buzon_escaner_pendiente():
    try:
        objs = sb.storage.from_(BUCKET).list(CARPETA_ESCANER) or []
        return [o['name'] for o in objs if o.get('name') and not o['name'].startswith('.')]
    except Exception as _e:
        print('AVISO al listar el buzon del escaner:', _e)
        return None

# Se limpia el buzon si el Excel subio BIEN o si deliberadamente no se genero
# (sin COMPRAR). Lo que NO se limpia es un fallo real de subida: eso se reintenta.
if subido_ok or _sin_excel:
    pend = _buzon_escaner_pendiente()
    if pend:
        for intento in (1, 2, 3):
            try:
                sb.storage.from_(BUCKET).remove([f'{CARPETA_ESCANER}/{n}' for n in pend])
            except Exception as _e:
                print(f'AVISO remove buzon escaner (intento {intento}):', _e)
            rest = _buzon_escaner_pendiente()
            if rest is None: break
            if not rest:
                print('Buzon del escaner limpiado y VERIFICADO.')
                break
            pend = rest
        else:
            print(f'ATENCION: el buzon del escaner NO quedo limpio: {pend}. Borralos a mano.')
else:
    print('El Excel no se subio: dejo el buzon del escaner intacto para reintentar.')

print("=== ESCANER FIN ===")

# ============================================================
# AVISO TELEGRAM: chollos de la pasada (productos COMPRAR). Se dispara SOLO si el
# workflow pasa TELEGRAM_TOKEN/CHAT_ID en el paso de escaneo (o sea, en los directores
# que quieran aviso: DBLine, OcioStock). TCG no las pasa aqui -> no duplica su aviso.
# Envuelto en try/except: si Telegram falla, la corrida ya termino igual.
# ============================================================
try:
    _tg_token = os.environ.get('TELEGRAM_TOKEN')
    _tg_chat  = os.environ.get('TELEGRAM_CHAT_ID')
    if _tg_token and _tg_chat:
        _compras = []
        for _it in registros:
            _mejor = None
            for _dom, _d in (_it.get('_paises_calc') or {}).items():
                if _d.get('decision') == 'COMPRAR' and _d.get('margen') is not None:
                    if _mejor is None or _d['margen'] > _mejor[1]:
                        _mejor = (_dom, _d['margen'], _d.get('precio'))
            if _mejor:
                _compras.append((_it, _mejor))
        if _compras:
            _lineas = [f"🟢 <b>Director {PROVEEDOR}</b> ({MODO}): {len(_compras)} para COMPRAR"]
            for _it, (_dom, _mg, _pv) in _compras[:20]:
                _nom = str(_it.get('nombre') or '')[:45]
                _pvs = f"{_pv:.2f}€" if _pv else "s/precio"
                _lineas.append(f"• {_nom} — {_mg*100:.0f}% — {_pvs} ({_dom}) — {_it.get('marca','')}")
            if len(_compras) > 20:
                _lineas.append(f"…y {len(_compras)-20} más (mira el Excel de la Biblioteca).")
            import requests as _rq_tg
            _rq_tg.post(f"https://api.telegram.org/bot{_tg_token}/sendMessage",
                        data={'chat_id': _tg_chat, 'text': "\n".join(_lineas),
                              'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}, timeout=20)
            print(f">>> Telegram enviado: {len(_compras)} COMPRAR.")
        else:
            print(">>> Telegram: 0 COMPRAR en esta pasada -> no se envia aviso.")
    else:
        print(">>> Telegram: sin claves en este paso -> no se envia (normal en TCG o app).")
except Exception as _e_tg:
    print("AVISO Telegram (no se envio, la corrida ya termino igual):", _e_tg)
