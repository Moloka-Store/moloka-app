#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# NOVEDADES WEB TCG  -  Altas automaticas de la web (linea origen='tcg')
# ----------------------------------------------------------------------------
# Detecta EANs SERVIBLES del catalogo de TCG que aun NO estan en la web ni se han
# evaluado antes, les saca el RANK (solo a esos pocos), y a los que pasan el corte
# (<= CORTE) los deja en un recado para robot_lote -> que genera la ficha BORRADOR
# (activo=false). NO publica nada: Fernando revisa fotos/montaje y activa, igual
# que con los 500.
#
# Memoria propia (web_rank/_vistas_web.json): cada EAN se rankea UNA sola vez.
# FRENO: si aparecen muchos de golpe (1a vez o volcado de TCG) -> se marcan como
#   baseline y NO se genera nada (aviso), para no llenar la web sin querer.
#
# Entrada: web_rank/catalogo.xlsx (lo deja el Paso 1 del director) + web_productos.
# Salida:  fabrica_lote/_solicitud_auto.json (recado para robot_lote con RECADO_LOTE_PATH).
# Secrets: KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY,
#          (TELEGRAM_TOKEN/CHAT_ID opcionales).
# ============================================================================
import os, io, json, sys, datetime
import openpyxl, keepa, requests
from supabase import create_client

sys.stdout.reconfigure(line_buffering=True)

BUCKET      = 'informes'
CAT_PATH    = 'web_rank/catalogo.xlsx'
VISTAS      = 'web_rank/_vistas_web.json'
RECADO_AUTO = 'fabrica_lote/_solicitud_auto.json'

CORTE      = int(os.environ.get('NOV_CORTE', '30000'))   # mismo corte que robot_fotos_tcg (los ~580)
FRENO      = int(os.environ.get('NOV_FRENO', '40'))      # si hay mas candidatos de golpe -> baseline, no genera
IDX_RANK   = 3
ESTADOS_OK = ('disponible', 'oferta', 'saldo')           # mismo criterio que el actualizador
STOCK_MIN  = 2

api  = keepa.Keepa(os.environ['KEEPA_API_KEY'])
sb   = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
_svc = os.environ.get('SUPABASE_SERVICE_KEY')
sb_w = create_client(os.environ['SUPABASE_URL'], _svc) if _svc else sb   # para escribir Storage


def _num(x):
    try: return float(str(x).replace(',', '.').strip())
    except Exception: return None


def tg(texto):
    tok = os.environ.get('TELEGRAM_TOKEN'); chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not (tok and chat): return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={'chat_id': chat, 'text': texto, 'parse_mode': 'HTML',
                            'disable_web_page_preview': 'true'}, timeout=20)
    except Exception as e:
        print("  (aviso telegram:", e, ")")


def servibles():
    """{ean: estado} de los EANs servibles del catalogo TCG (mismo criterio que el actualizador)."""
    data = sb.storage.from_(BUCKET).download(CAT_PATH)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c is not None else '' for c in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    iE, iS, iEst = idx.get('EAN'), idx.get('Stock'), idx.get('Estado producto')
    out = {}
    for r in rows[1:]:
        ean = str(r[iE] or '').strip()
        if not ean:
            continue
        stock = _num(r[iS]) or 0
        estado = str(r[iEst] or '').strip().lower()
        if estado in ESTADOS_OK and stock >= STOCK_MIN:
            out[ean] = estado
    return out


def eans_en_web():
    """Todos los EANs ya presentes en web_productos (cualquier origen: robot_lote los saltaria igual)."""
    s, desde = set(), 0
    while True:
        lote = sb.table('web_productos').select('ean').range(desde, desde + 999).execute().data or []
        for f in lote:
            e = str(f.get('ean') or '').strip()
            if e:
                s.add(e)
        if len(lote) < 1000:
            break
        desde += 1000
    return s


def cargar_vistas():
    try:
        d = sb.storage.from_(BUCKET).download(VISTAS)
        return json.loads(d.decode('utf-8'))
    except Exception:
        return {}


def guardar_vistas(v):
    sb_w.storage.from_(BUCKET).upload(
        VISTAS, json.dumps(v, ensure_ascii=False).encode('utf-8'),
        {'upsert': 'true', 'content-type': 'application/json'})


def mejor_rank(ean):
    """Rank de Espana (Fase 1, indice 3, igual que robot_rank_web) del EAN. None si no hay."""
    try:
        prods = api.query([ean], product_code_is_asin=False, domain='ES', stats=90, history=0) or []
    except Exception as e:
        print(f"   Keepa error {ean}: {e}")
        return None
    mejor = None
    for p in prods:
        st = p.get('stats') or {}
        cur, a90 = st.get('current') or [], st.get('avg90') or []
        r_act = cur[IDX_RANK] if len(cur) > IDX_RANK else -1
        r_90  = a90[IDX_RANK] if len(a90) > IDX_RANK else -1
        for r in (r_act, r_90):
            if isinstance(r, (int, float)) and r > 0 and (mejor is None or r < mejor):
                mejor = r
    return mejor


def main():
    print(">>> NOVEDADES WEB TCG — arrancando", flush=True)
    try:
        serv = servibles()
    except Exception as e:
        print(f"!!! No pude leer el catalogo TCG ({CAT_PATH}): {e}")
        return
    web    = eans_en_web()
    vistas = cargar_vistas()
    print(f">>> Servibles: {len(serv)} | ya en web: {len(web)} | ya vistos: {len(vistas)}")

    candidatos = [e for e in serv if e not in web and e not in vistas]
    print(f">>> Candidatos nuevos (servibles, no en web, no vistos): {len(candidatos)}")
    if not candidatos:
        print(">>> Nada nuevo. Fin.")
        return

    # FRENO / BASELINE: demasiados de golpe (1a vez o volcado) -> marcar y NO generar.
    if len(candidatos) > FRENO:
        for e in candidatos:
            vistas[e] = {'verdict': 'baseline', 'fecha': datetime.date.today().isoformat()}
        guardar_vistas(vistas)
        print(f">>> FRENO: {len(candidatos)} candidatos (>{FRENO}) -> marcados BASELINE, no se generan fichas.")
        tg(f"🟡 <b>Novedades web TCG</b>: {len(candidatos)} candidatos de golpe (>{FRENO}). "
           f"Marcados como baseline; NO se generan fichas automaticas. Si quieres cargar esos, "
           f"lanza la cadena manual (rank -> fotos -> lote).")
        return

    # Rankear los candidatos (pocos) y filtrar al corte.
    pasan = []
    for i, ean in enumerate(candidatos, 1):
        rk = mejor_rank(ean)
        pasa = rk is not None and rk <= CORTE
        vistas[ean] = {'verdict': ('pasa' if pasa else ('rank' if rk else 'sin_rank')),
                       'rank': rk, 'fecha': datetime.date.today().isoformat()}
        print(f"   [{i}/{len(candidatos)}] {ean} rank={rk} -> {'PASA' if pasa else 'fuera'}")
        if pasa:
            pasan.append(ean)

    guardar_vistas(vistas)

    # Recado = TODOS los 'pasa' conocidos que siguen servibles y aun NO estan en web.
    # Asi, si robot_lote se corta a medias, se reintentan solos hasta que la ficha exista
    # (cuando robot_lote crea el borrador, el EAN entra en web -> sale de esta lista).
    pendientes = [e for e, info in vistas.items()
                  if info.get('verdict') == 'pasa' and e in serv and e not in web]
    if not pendientes:
        print(">>> Sin novedades pendientes de ficha. Fin.")
        return
    tanda  = 'auto_' + datetime.datetime.now().strftime('%Y%m%d_%H%M')
    recado = {'tanda': tanda, 'items': [{'ean': e} for e in pendientes]}
    sb_w.storage.from_(BUCKET).upload(
        RECADO_AUTO, json.dumps(recado, ensure_ascii=False).encode('utf-8'),
        {'upsert': 'true', 'content-type': 'application/json'})
    print(f">>> {len(pendientes)} novedad(es) pendientes (nuevas este pase: {len(pasan)}) "
          f"con rank <= {CORTE}. Recado en {RECADO_AUTO} -> robot_lote generara los borradores.")


if __name__ == '__main__':
    main()
