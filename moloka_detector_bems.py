#!/usr/bin/env python3
# ============================================================
# MOLOKA - Detector de oportunidades BEMS  (NUBE / GitHub Actions)
# ------------------------------------------------------------
# Vigila varias marcas de BEMS en modo "NUEVOS" (novedades + reposiciones +
# cambio de precio) y, si algun producto sale COMPRAR, avisa al instante por
# TELEGRAM. SILENCIOSO: no genera Excel ni ensucia la biblioteca de la app
# (eso lo hace el escaner normal y el repaso semanal). Aqui solo: detectar y
# avisar. Tambien ACTUALIZA la memoria viva del proveedor, igual que el escaner.
#
# Reutiliza el MISMO motor validado del escaner (moloka_escaner_nube.py):
#   - descarga BEMS por API (solo AVAILABLE=1)
#   - Fase 1 filtro de rank (Keepa ES, 1 token/producto)
#   - Fase 2 ES/IT/FR (3 tok/pais, buybox sin offers)
#   - formula de rentabilidad al centimo, semaforo por MARGEN
#   - memoria viva en escaner_memoria (nuevo/reaparicion/cambio/agotado)
# La logica de calculo es IDENTICA a la del escaner; lo unico distinto es la
# SALIDA (Telegram en vez de Excel) y que recorre VARIAS marcas de un tiron.
#
# QUE MARCAS: se leen de Supabase app_datos['bems_marcas_vigiladas'] para poder
# cambiarlas sin tocar codigo. Si no existe la clave, cae a una lista por defecto.
#
# Variables de entorno (GitHub Secrets):
#   KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY,
#   BEMS_LOGIN, BEMS_PASSWORD, BEMS_SECRET_KEY,
#   TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
# ============================================================

import os, sys, time, json
from datetime import datetime, timezone
from collections import Counter

import keepa
from supabase import create_client

# Salida sin buffer: que cada print salga al log de Actions al instante
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# ============================================================
# PARAMETROS FIJOS DEL DETECTOR
# ============================================================
PROVEEDOR   = 'BEMS'
MODO        = 'nuevos'          # nuevo + reaparicion + cambio de precio
RANK_MAXIMO = int(os.environ.get('DET_RANK_MAXIMO', '30000'))
INCLUIR_SIN_RANK = False

# Marcas por defecto si Supabase no tiene la lista (se usa el ID_MAN de la API
# de BEMS, que NO siempre coincide con el nombre: 'Pyramid' -> 'Pyramid Int.').
MARCAS_DEFAULT = ['Funko', 'Bandai Model Kit', 'Pyramid Int.']

# Parametros de calculo (IDENTICOS al escaner)
IVA_DEFAULT_ES, IVA_IT, IVA_FR = 0.21, 0.22, 0.20
ALMACEN, COM_DIGITALES = 0.15, 1.03
LOTE_FASE1 = 100
IDX_RANK, IDX_NEW = 3, 1

KEEPA_MAX_INTENTOS = 4
KEEPA_ESPERAS = [5, 15, 40, 90]

# ============================================================
# CLIENTES
# ============================================================
print(">>> ARRANCANDO detector BEMS. Cliente Keepa...", flush=True)
api = keepa.Keepa(os.environ['KEEPA_API_KEY'])
print(">>> Keepa OK. Conectando Supabase...", flush=True)
sb  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
api.update_status()
print(f">>> Tokens Keepa AHORA: {api.tokens_left}", flush=True)

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# ============================================================
# TELEGRAM
# ------------------------------------------------------------
# Envia un mensaje al chat configurado. Usa requests (ya disponible via supabase).
# No revienta la corrida si Telegram falla: avisa en el log y sigue.
# ============================================================
import requests as _rq

def enviar_telegram(texto):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("AVISO: faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID; no se envia aviso.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = _rq.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': texto,
            'parse_mode': 'HTML',
            'disable_web_page_preview': 'true',
        }, timeout=20)
        if r.status_code == 200:
            return True
        print(f"AVISO Telegram HTTP {r.status_code}: {(r.text or '')[:200]}")
        return False
    except Exception as ex:
        print("AVISO Telegram (red):", ex)
        return False

# ============================================================
# LLAMADA ROBUSTA A KEEPA (igual que el escaner)
# ============================================================
def keepa_query(items, **kwargs):
    kwargs.setdefault('progress_bar', False)
    for intento in range(KEEPA_MAX_INTENTOS):
        try:
            return api.query(items, **kwargs) or []
        except Exception as ex:
            if intento < KEEPA_MAX_INTENTOS - 1:
                espera = KEEPA_ESPERAS[intento]
                print(f"  [Keepa] intento {intento+1}/{KEEPA_MAX_INTENTOS} fallo: {ex} -> reintento en {espera}s")
                time.sleep(espera)
            else:
                print(f"  [Keepa] AGOTADOS {KEEPA_MAX_INTENTOS} intentos: {ex} -> se salta")
    return None

# ============================================================
# HELPERS EAN / NUM  (copiados del escaner, identicos)
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
# RENTABILIDAD (formula validada al centimo, identica al escaner)
# ============================================================
def calc_rentabilidad(precio_venta, pa, ref_pct, fee_fba, iva, almacen=0.15, com_digitales=1.03):
    base       = precio_venta / (1 + iva)
    com_amazon = precio_venta * (ref_pct/100) * com_digitales
    beneficio  = base - pa - com_amazon - fee_fba - almacen
    roi        = beneficio / pa if pa else 0
    margen     = beneficio / precio_venta if precio_venta else 0
    return dict(base=base, com_amazon=com_amazon, beneficio=beneficio, roi=roi, margen=margen)

# auto-test de la formula (debe dar beneficio -1.04 y comision 2.47 para el Rengoku)
_r = calc_rentabilidad(15.99, 8.12, 15, 3.51, 0.21)
print(">>> FORMULA OK <<<" if abs(_r['beneficio']+1.04)<0.01 and abs(_r['com_amazon']-2.47)<0.01
      else ">>> REVISAR FORMULA <<<")

def decision_de(margen):
    if margen is None: return 'Sin datos'
    if margen*100 >= 10: return 'COMPRAR'
    if margen*100 >= 1:  return 'VALORAR'
    return 'NO COMPRAR'

# ============================================================
# DESCARGA BEMS POR API (copiada del escaner, identica)
# ------------------------------------------------------------
# Baja los productos DISPONIBLES (AVAILABLE=1) de 'marca' y devuelve una lista de
# dicts con las claves que necesitamos: ean, nombre, pa. Si la marca no tiene
# productos (NO RESULT) devuelve []. Si hay error de red/credenciales -> None.
# ============================================================
def descargar_bems(marca):
    try:
        from curl_cffi import requests as _curl
    except Exception as ex:
        print("ERROR BEMS: curl_cffi no disponible:", ex); return None
    base = "https://www.probems.be/API"; imp = "chrome120"
    login = os.environ.get("BEMS_LOGIN"); pwd = os.environ.get("BEMS_PASSWORD"); sk = os.environ.get("BEMS_SECRET_KEY")
    if not (login and pwd and sk):
        print("ERROR BEMS: faltan credenciales BEMS_* en el entorno."); return None
    # token
    try:
        rt = _curl.post(f"{base}/TOKEN",
                        data={"login": login, "password": pwd, "secret_key": sk},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        impersonate=imp, timeout=30)
    except Exception as ex:
        print("ERROR BEMS token (red):", ex); return None
    tok = rt.json().get("access_token") if rt.status_code == 200 else None
    if not tok:
        print("ERROR BEMS token:", rt.status_code, (rt.text or "")[:150]); return None
    H = {"accept": "application/json", "authorization": f"Bearer {tok}"}
    params = {"AVAILABLE": "1", "DETAILS": "1", "LIMIT": "0"}
    if marca and marca.strip().upper() != "TODAS":
        params["MANUFACTURER"] = marca.strip()
    try:
        r = _curl.get(f"{base}/PRODUCT-LIST-FILTER", params=params,
                      headers=H, impersonate=imp, timeout=180)
    except Exception as ex:
        print("ERROR BEMS PRODUCT-LIST-FILTER (red):", ex); return None
    if r.status_code != 200:
        txt = (r.text or "")
        if "NO RESULT" in txt.upper():
            print(f"BEMS: '{marca}' sin resultados (NO RESULT) -> 0 productos.")
            return []
        print("ERROR BEMS lista:", r.status_code, txt[:150]); return None
    try:
        prods = r.json()
    except Exception as ex:
        print("ERROR BEMS: respuesta no es JSON:", ex); return None
    if not isinstance(prods, list):
        print("ERROR BEMS: respuesta no es una lista:", str(prods)[:150]); return None
    out = []
    for p in prods:
        ean = str(p.get("EAN") or "").strip()
        if not ean:
            continue
        out.append({
            'ean_in': ean,
            'nombre': str(p.get("NAME_PRODUCT") or "").strip(),
            'pa': _num(p.get("PRICE")),
        })
    return out

# ============================================================
# CRUCE SUPABASE (productos propios: IVA real por producto + 'En mi BD')
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

# ============================================================
# LISTA DE MARCAS A VIGILAR (de Supabase app_datos, editable sin tocar codigo)
# ============================================================
def leer_marcas_vigiladas():
    try:
        res = sb.table('app_datos').select('contenido').eq('clave','bems_marcas_vigiladas').execute()
        if res.data:
            cont = res.data[0]['contenido']
            # admitimos dos formatos: {"marcas":[...]} o directamente [...]
            if isinstance(cont, dict) and isinstance(cont.get('marcas'), list):
                marcas = [str(m).strip() for m in cont['marcas'] if str(m).strip()]
            elif isinstance(cont, list):
                marcas = [str(m).strip() for m in cont if str(m).strip()]
            else:
                marcas = []
            if marcas:
                print(f"Marcas vigiladas (Supabase): {marcas}")
                return marcas
    except Exception as ex:
        print("AVISO: no se pudo leer bems_marcas_vigiladas, uso lista por defecto:", ex)
    print(f"Marcas vigiladas (por defecto): {MARCAS_DEFAULT}")
    return MARCAS_DEFAULT

# ============================================================
# MEMORIA VIVA (por marca): leer estado + clasificar nuevos/cambios
# ============================================================
def leer_memoria(marca):
    mem = {}
    try:
        _rows = []; _d = 0
        while True:
            res = (sb.table('escaner_memoria')
                     .select('ean,es_case,pa,presente')
                     .eq('proveedor', PROVEEDOR).eq('marca', marca)
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
    except Exception as ex:
        print(f"AVISO memoria {marca}: se trata todo como NUEVO:", ex)
    return mem

def estado_mem(f, mem):
    k = (norm(f['core']), bool(f['es_chase']))
    if k not in mem: return 'nuevo'
    info = mem[k]
    if not info['presente']: return 'reaparicion'
    pa_ant = info['pa']
    if f['pa'] is None or pa_ant is None: return 'sin_cambios'
    if abs(float(f['pa']) - float(pa_ant)) > 0.01: return 'cambio_precio'
    return 'sin_cambios'

def actualizar_memoria(marca, filas_hoy, ausentes):
    ahora = datetime.now(timezone.utc).isoformat()
    regs = []; vistos = set()
    for f in filas_hoy:
        k = (PROVEEDOR, norm(f['core']), bool(f['es_chase']))
        if k in vistos: continue
        vistos.add(k)
        regs.append({'proveedor':PROVEEDOR, 'ean':f['core'], 'es_case':bool(f['es_chase']),
                     'marca':marca, 'pa': float(f['pa']) if f['pa'] is not None else None,
                     'presente':True, 'fecha':ahora})
    if filas_hoy:
        for (ean_norm, es_case), info in ausentes:
            k = (PROVEEDOR, ean_norm, es_case)
            if k in vistos: continue
            vistos.add(k)
            pa_ant = info.get('pa')
            regs.append({'proveedor':PROVEEDOR, 'ean':info['ean_db'], 'es_case':es_case,
                         'marca':marca, 'pa': float(pa_ant) if pa_ant is not None else None,
                         'presente':False, 'fecha':ahora})
    else:
        print("  Catalogo vacio: NO se marcan agotados (evita falso vaciado).")
    if not regs:
        print("  Memoria sin cambios."); return
    n_ok = 0
    for i in range(0, len(regs), 500):
        lote = regs[i:i+500]
        try:
            sb.table('escaner_memoria').upsert(lote, on_conflict='proveedor,ean,es_case').execute()
            n_ok += len(lote)
        except Exception as ex:
            print(f"  AVISO lote memoria {i//500+1}: {ex}")
    n_pres = sum(1 for x in regs if x['presente'])
    print(f"  Memoria {marca}: {n_ok}/{len(regs)} ({n_pres} presentes, {len(regs)-n_pres} agotados)")

# ============================================================
# FASE 1 (filtro rank) + FASE 2 (ES/IT/FR) sobre UNA lista de filas
# Devuelve la lista de items con sus calculos por pais.
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
    return {'precio':precio,'canal':canal,'ref_pct':p.get('referralFeePercentage'),
            'fee':fee/100 if fee else None,
            'rank_act':cur[IDX_RANK] if len(cur)>IDX_RANK else -1,
            'rank90':a90[IDX_RANK] if len(a90)>IDX_RANK else -1,
            'vendidos':p.get('monthlySold')}

def escanear_filas(filas):
    """Fase 1 + Fase 2 sobre 'filas'. Devuelve lista de items con _paises_calc."""
    candidatos, ambiguos = {}, []
    pasan = {}
    if not filas:
        return []

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
                if keyrank(cand)<keyrank(prev): candidatos[ein]=cand
            else:
                candidatos[ein]=cand
            vistos.add(ein)

    def pasada(cod_por_ean, etiqueta):
        pool = list(cod_por_ean.keys())
        codigos = sorted({cod_por_ean[e] for e in pool})
        lotes = [codigos[i:i+LOTE_FASE1] for i in range(0,len(codigos),LOTE_FASE1)]
        vistos = set()
        print(f"  {etiqueta}: {len(pool)} prod, {len(codigos)} cod, {len(lotes)} lotes")
        for n,lote in enumerate(lotes,1):
            prods = keepa_query(lote, product_code_is_asin=False, domain='ES', stats=90, history=0)
            if prods is None:
                print(f"    lote {n}/{len(lotes)} NO resuelto -> se salta")
                continue
            for prod in prods: registra(prod, pool, vistos)
        return vistos

    vistos = pasada({f['ean_in']: cod_pref(f) for f in filas}, "Fase 1")
    for ronda in (0, 1):
        faltan = {f['ean_in'] for f in filas} - vistos
        rint = {}
        for f in filas:
            if f['ean_in'] in faltan:
                rs = cods_reserva(f)
                if len(rs) > ronda: rint[f['ean_in']] = rs[ronda]
        if rint:
            vistos |= pasada(rint, f"Fase 1 reintento {ronda+1}")

    for ein,c in candidatos.items():
        tiene = (c['r_act'] and c['r_act']>0) or (c['r_90'] and c['r_90']>0)
        if c['propio'] or pasa_filtro(c['r_act'],c['r_90']): pasan[ein]=c
        elif (not tiene) and INCLUIR_SIN_RANK: pasan[ein]=c

    print(f"  PASAN filtro rank: {len(pasan)}")

    # FASE 2
    infos = []
    for c in pasan.values():
        f = c['fila']
        item = {'nombre':f['nombre'],'ean':c['ean_in'],'asin':c['asin'],
                'pa':f['pa'],'core':f['core'],'es_chase':f['es_chase'],'paises':{}}
        for dom in ('ES','IT','FR'):
            d = datos_pais(c['asin'], dom)
            if d: item['paises'][dom] = d
        infos.append(item)

    # CALCULO
    registros = []
    for item in infos:
        iva = {'ES':iva_es_de(item['core']),'IT':IVA_IT,'FR':IVA_FR}
        pa = item['pa']           # BEMS: CHASE sueltos, NO se divide (solo TCG /6)
        paises_out = {}; margen_es = None
        for dom in ('ES','IT','FR'):
            d = item['paises'].get(dom)
            if d and d.get('precio') and pa and d.get('ref_pct') is not None and d.get('fee') is not None:
                r = calc_rentabilidad(d['precio'], pa, d['ref_pct'], d['fee'], iva[dom],
                                      almacen=ALMACEN, com_digitales=COM_DIGITALES)
                paises_out[dom] = {**d,'beneficio':r['beneficio'],'roi':r['roi'],
                                   'margen':r['margen'],'decision':decision_de(r['margen'])}
                if dom == 'ES': margen_es = r['margen']
        item['_paises_calc'] = paises_out
        item['_margen_es'] = margen_es
        registros.append(item)
    return registros

# ============================================================
# PROCESAR UNA MARCA: bajar -> clasificar nuevos -> escanear -> COMPRAR?
# Devuelve (lista_de_avisos, hubo_error_bems)
# ============================================================
def procesar_marca(marca):
    print(f"\n===== MARCA: {marca} =====")
    crudo = descargar_bems(marca)
    if crudo is None:
        print(f"  ERROR bajando BEMS '{marca}' -> se salta esta marca.")
        return [], True
    # construir filas (mismo formato que el escaner)
    filas_all = []
    for p in crudo:
        ean_in = p['ean_in']
        core = core_ean(ean_in)
        if (not core.isdigit()) or len(core) not in (12, 13):
            continue
        filas_all.append({'ean_in':ean_in, 'core':core, 'variantes':variantes_ean(core),
                          'nombre':p['nombre'], 'pa':p['pa'], 'es_chase':es_chase_ean(ean_in)})
    print(f"  Disponibles BEMS: {len(filas_all)}")

    mem = leer_memoria(marca)
    print(f"  Memoria {marca}: {len(mem)} EANs conocidos")
    claves_hoy = {(norm(f['core']), bool(f['es_chase'])) for f in filas_all}
    for f in filas_all:
        f['_estado'] = estado_mem(f, mem)
    cnt = Counter(f['_estado'] for f in filas_all)
    print(f"  Nuevos:{cnt.get('nuevo',0)} Reaparecidos:{cnt.get('reaparicion',0)} "
          f"Cambio precio:{cnt.get('cambio_precio',0)} Sin cambios:{cnt.get('sin_cambios',0)}")
    ausentes = [(k, info) for k, info in mem.items() if info['presente'] and k not in claves_hoy]

    # modo nuevos: solo nuevo/reaparicion/cambio_precio
    filas_nuevos = [f for f in filas_all if f['_estado'] in ('nuevo','reaparicion','cambio_precio')]
    print(f"  A escanear (nuevos): {len(filas_nuevos)}")

    avisos = []
    if filas_nuevos:
        registros = escanear_filas(filas_nuevos)
        for it in registros:
            # buscar la MEJOR decision COMPRAR entre los paises
            for dom in ('ES','IT','FR'):
                d = it['_paises_calc'].get(dom)
                if d and d['decision'] == 'COMPRAR':
                    avisos.append({
                        'nombre': it['nombre'], 'ean': it['ean'], 'asin': it['asin'],
                        'pais': dom, 'pa': it['pa'], 'precio': d['precio'],
                        'margen': d['margen'], 'beneficio': d['beneficio'],
                        'estado': next((f['_estado'] for f in filas_nuevos if f['ean_in']==it['ean']), '?'),
                        'marca': marca,
                    })
                    break   # un aviso por producto (el primer pais que sea COMPRAR)

    # actualizar memoria SIEMPRE (haya o no avisos), igual que el escaner
    actualizar_memoria(marca, filas_all, ausentes)
    return avisos, False

# ============================================================
# MAIN
# ============================================================
def main():
    marcas = leer_marcas_vigiladas()
    todos_avisos = []
    marcas_con_error = []
    for marca in marcas:
        try:
            avisos, err = procesar_marca(marca)
            todos_avisos.extend(avisos)
            if err: marcas_con_error.append(marca)
        except Exception as ex:
            print(f"  ERROR inesperado en marca {marca}: {ex}")
            marcas_con_error.append(marca)

    print(f"\n===== RESUMEN: {len(todos_avisos)} oportunidades COMPRAR =====")
    if todos_avisos:
        # ordenar por margen desc (las mejores primero)
        todos_avisos.sort(key=lambda a: a['margen'] if a['margen'] is not None else -9, reverse=True)
        DOMINIO = {'ES':'es','IT':'it','FR':'fr'}
        ETIQ = {'nuevo':'🆕 nuevo','reaparicion':'♻️ reposición','cambio_precio':'💲 cambio precio'}
        lineas = [f"<b>💰 BEMS: {len(todos_avisos)} para COMPRAR</b>", ""]
        for a in todos_avisos[:30]:   # tope para no mandar un tocho gigante
            url = f"https://www.amazon.{DOMINIO[a['pais']]}/dp/{a['asin']}"
            etiq = ETIQ.get(a['estado'], a['estado'])
            margen_pct = a['margen']*100 if a['margen'] is not None else 0
            lineas.append(
                f"<b>{a['nombre'][:60]}</b>\n"
                f"  {a['marca']} · {etiq}\n"
                f"  {a['pais']}: compra {a['pa']:.2f}€ → vende {a['precio']:.2f}€ · "
                f"margen {margen_pct:.0f}% (benef {a['beneficio']:.2f}€)\n"
                f"  <a href=\"{url}\">ver en Amazon.{DOMINIO[a['pais']]}</a>"
            )
        if len(todos_avisos) > 30:
            lineas.append(f"\n…y {len(todos_avisos)-30} más.")
        if marcas_con_error:
            lineas.append(f"\n⚠️ marcas con error de descarga: {', '.join(marcas_con_error)}")
        ok = enviar_telegram("\n".join(lineas))
        print("Aviso Telegram enviado." if ok else "NO se pudo enviar el aviso Telegram.")
    else:
        print("Nada para comprar en esta pasada. No se envia Telegram.")
        if marcas_con_error:
            # si NO hubo oportunidades pero SI fallo alguna marca, avisar discretamente
            enviar_telegram(f"⚠️ Detector BEMS: no pude descargar {', '.join(marcas_con_error)} en esta pasada.")

    print(f"Tokens Keepa al terminar: {api.tokens_left}")
    print("=== DETECTOR BEMS FIN ===")

if __name__ == '__main__':
    main()
