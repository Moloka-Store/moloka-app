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

import os, sys, time, json
import pandas as pd
import keepa
from supabase import create_client
from datetime import datetime, timezone
from collections import Counter

# ============================================================
# CREDENCIALES (entorno, no Colab)
# ============================================================
api = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print("Tokens Keepa:", api.tokens_left)

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
CARPETA_ESCANER = 'escaner'        # recado + catalogo crudo del proveedor
CARPETA_RESULTADOS = 'resultados'  # Excel de salida
RECADO = '_solicitud_escaner.json'

SOLICITUD = {}
catalogo_local = None
catalogo_nombre = None
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
    'MOLOKA': {'tipo':'supabase'},   # inventario propio: se lee de la tabla productos
}
if PROVEEDOR not in PERFILES:
    print(f'Proveedor desconocido: {PROVEEDOR}. Validos: {list(PERFILES)}. Fin.')
    sys.exit(0)
PERFIL = PERFILES[PROVEEDOR]

if PROVEEDOR != 'MOLOKA' and not catalogo_local:
    print(f'Falta el catalogo de {PROVEEDOR} en el buzon. Sube el fichero y vuelve a lanzar. Fin.')
    sys.exit(0)

IVA_DEFAULT_ES, IVA_IT, IVA_FR = 0.21, 0.22, 0.20
ALMACEN, COM_DIGITALES = 0.15, 1.03
UNIDADES_CASE_TCG = 6          # TCG vende CHASE en case 5+1 -> coste unitario = PA / 6. Solo TCG.
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

# ============================================================
# Celda 4 - carga del catalogo
#   MOLOKA -> Supabase (inventario propio).  Resto -> fichero crudo del buzon.
# ============================================================
problematicos = []
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
    if PERFIL['tipo'] == 'excel':
        cat = pd.read_excel(catalogo_local, sheet_name=PERFIL['sheet'],
                            header=PERFIL['header'], dtype=str).fillna('')
    else:
        cat = pd.read_csv(catalogo_local, sep=PERFIL.get('sep', ';'), dtype=str,
                          encoding='utf-8', on_bad_lines='skip').fillna('')
    cat.columns = [str(c).strip() for c in cat.columns]   # BEMS trae espacios en los nombres
    print(f"Catalogo crudo: {len(cat)} filas")

    cM, cE, cN, cP, cS = (PERFIL['col_marca'], PERFIL['col_ean'], PERFIL['col_nombre'],
                          PERFIL['col_pa'], PERFIL['col_stock'])

    # filtro 1: marca ('TODAS' o vacio = NO filtra)
    if MARCA and MARCA.strip().upper() != 'TODAS':
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
        stock = _num(row.get(cS, ''))
        if stock is None or stock <= 0:
            fuera_disp += 1; continue
        ean_in = str(row[cE]).strip()
        core = core_ean(ean_in)
        if (not core.isdigit()) or len(core) not in (12, 13):
            problematicos.append({'EAN':ean_in, 'Cabecera':row.get(cN,''),
                                  'Motivo':f'EAN forma rara (len={len(core)})'}); continue
        pa = _num(row.get(cP, ''))
        if PERFIL.get('col_pa_promo'):                    # DBLine: promo si >0, si no Listino
            promo = _num(row.get(PERFIL['col_pa_promo'], ''))
            if promo and promo > 0: pa = promo
        filas.append({'ean_in':ean_in, 'core':core, 'variantes':variantes_ean(core),
                      'nombre':row.get(cN,''), 'marca':MARCA, 'pa':pa,
                      'es_chase':es_chase_ean(ean_in)})
    print(f"Disponibles a escanear: {len(filas)} | fuera por estado/stock: {fuera_disp} | "
          f"EAN problematicos: {len(problematicos)} | CHASE: {sum(f['es_chase'] for f in filas)}")

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
                 .eq('proveedor', PROVEEDOR).eq('marca', MARCA)
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
# Celda 6 - FASE 1: filtro de rank (Keepa ES, 1 token)
# ============================================================
IDX_RANK, IDX_NEW = 3, 1
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
            prods = keepa_query(lote, product_code_is_asin=False, domain='ES', stats=90, history=0)
            if prods is None:
                print(f"  lote {n}/{len(lotes)} NO resuelto tras reintentos -> se salta este lote")
                continue
            for prod in prods: registra(prod, pool, vistos)
            print(f"  lote {n}/{len(lotes)} | tokens {api.tokens_left}")
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
    bb = st.get('buyBoxPrice')
    if bb and bb>0:
        precio = bb/100
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
            'vendidos':p.get('monthlySold')}

infos = []
lista = list(pasan.values())
print(f"Fase 2: {len(lista)} candidatos x 3 paises")
for i,c in enumerate(lista,1):
    f = c['fila']
    item = {'nombre':f['nombre'],'ean':c['ean_in'],'asin':c['asin'],'marca':f['marca'],
            'pa':f['pa'],'core':f['core'],'es_chase':f['es_chase'],'propio':c['propio'],
            'ambiguo':c['ean_in'] in amb_eans,'paises':{}}
    for dom in ('ES','IT','FR'):
        d = datos_pais(c['asin'], dom)
        if d: item['paises'][dom] = d
    infos.append(item)
    if i%50==0:
        print(f"  {i}/{len(lista)} | tokens {api.tokens_left}")
print(f"Fase 2 completa: {len(infos)} productos")

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
    if PROVEEDOR == 'TCG' and item['es_chase'] and pa:
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
        'Beneficio (€)','ROI','Margen','Decisión','En mi BD','EAN ambiguo']
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
            d['decision'], en_bd, amb])
        cell = ws.cell(row=r, column=3)
        cell.hyperlink = f"https://www.{DOM_AMZ[dom]}/dp/{item['asin']}"
        cell.font = Font(color='0563C1', underline='single')

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
anchos = {'Nombre':50,'EAN':14,'ASIN':12,'Marca':12,'En mi BD':20,'Decisión':15}
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
    ws.conditional_formatting.add(f'A2:{get_column_letter(len(COLS))}{last}',
        FormulaRule(formula=['ISODD(INT((ROW()-2)/3))'], fill=_cf_fill('D9D9D9')))

def hoja(nombre, regs):
    w = wb.create_sheet(nombre)
    if regs:
        ks = list(regs[0].keys()); w.append(ks)
        for x in regs: w.append([x.get(k) for k in ks])
    else: w.append(['(vacio)'])
hoja('Descartados', problematicos + no_encontrados)
hoja('Ambiguos', ambiguos)
hoja('Sin_rank', [{'EAN':c['ean_in'],'ASIN':c['asin'],'Nombre':c['fila']['nombre'],
                   'rank_act':c['r_act'],'rank90':c['r_90']} for c in sin_rank])

wb.save(ARCHIVO_SALIDA)
print("Guardado local:", ARCHIVO_SALIDA, "| filas:", last-1)

# ============================================================
# SUBIR EL EXCEL A STORAGE + REGISTRAR EN LA BIBLIOTECA (escaner_resultados)
# ============================================================
nombre_xlsx = os.path.basename(ARCHIVO_SALIDA)
ruta_storage = f'{CARPETA_RESULTADOS}/{nombre_xlsx}'
subido_ok = False
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

try:
    sb.table('escaner_resultados').insert({
        'proveedor': PROVEEDOR, 'marca': MARCA, 'modo': MODO,
        'rank_maximo': RANK_MAXIMO,
        'n_productos': len(registros), 'n_comprar': n_mandar,
        'n_nuevos': cnt.get('nuevo',0), 'n_reaparecidos': cnt.get('reaparicion',0),
        'n_cambios': cnt.get('cambio_precio',0), 'n_agotados': len(ausentes),
        'fichero': ruta_storage if subido_ok else None,
        'tokens_restantes': int(api.tokens_left),
    }).execute()
    print("Escaneo registrado en la biblioteca (escaner_resultados).")
except Exception as ex:
    print("AVISO: no se pudo registrar en escaner_resultados (el Excel SI esta en Storage):", ex)

# ============================================================
# Celda 10 - actualizar la memoria del proveedor (presentes / agotados)
# ============================================================
ahora = datetime.now(timezone.utc).isoformat()
regs = []; vistos_up = set()
for f in filas_hoy:
    k = (PROVEEDOR, norm(f['core']), bool(f['es_chase']))
    if k in vistos_up: continue
    vistos_up.add(k)
    regs.append({'proveedor':PROVEEDOR, 'ean':f['core'], 'es_case':bool(f['es_chase']),
                 'marca':MARCA, 'pa': float(f['pa']) if f['pa'] is not None else None,
                 'presente':True, 'fecha':ahora})
# Agotados SOLO si el catalogo de hoy trajo productos. Si vino vacio (fichero
# equivocado, marca que no existe...), NO marcar todo como agotado: seria un
# falso vaciado que ensucia la memoria. Mejor no tocar nada.
if filas_hoy:
    for (ean_norm, es_case), info in ausentes:
        k = (PROVEEDOR, ean_norm, es_case)
        if k in vistos_up: continue
        vistos_up.add(k)
        pa_ant = info.get('pa')
        regs.append({'proveedor':PROVEEDOR, 'ean':info['ean_db'], 'es_case':es_case,
                     'marca':MARCA, 'pa': float(pa_ant) if pa_ant is not None else None,
                     'presente':False, 'fecha':ahora})
else:
    print("Catalogo vacio (0 productos): NO se marcan agotados (evita falso vaciado de la memoria).")
if not regs:
    print("Memoria sin cambios.")
else:
    n_ok = 0
    for i in range(0, len(regs), 500):
        lote = regs[i:i+500]
        try:
            sb.table('escaner_memoria').upsert(lote, on_conflict='proveedor,ean,es_case').execute()
            n_ok += len(lote)
        except Exception as ex:
            print(f"  AVISO lote memoria {i//500+1}: {ex}")
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

if subido_ok:
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
