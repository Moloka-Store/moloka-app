# ============================================================================
# ROBOT ACTUALIZADOR TCG  -  Mantenimiento diario de la web (linea origen='tcg')
# ----------------------------------------------------------------------------
# QUE HACE (NO da altas; eso es el lote del Paso 2). Repasa lo YA publicado de
# TCG contra el Excel recien subido (web_rank/catalogo.xlsx) y:
#   - RE-FIJA precios y ofertas (misma regla EXACTA que el lote, sin gastar Keepa:
#     formato/PVPR/estado salen del Excel crudo, no de Keepa).
#   - DESPUBLICA (activo=false, NO borra) lo que ya no se puede servir:
#     estado != Disponible/Oferta/Saldo, o stock < 2, o el EAN desaparecio.
#   - REACTIVA (activo=true) lo que vuelve a cumplir.
#
# BLINDAJE A FUEGO:
#   - SOLO toca filas con origen='tcg'. JAMAS origen='fabrica' (las joyas de Elena
#     se filtran en la propia consulta -> imposible tocarlas).
#   - FRENO: si una pasada fuera a despublicar mas del UMBRAL_FRENO_PCT de las
#     fichas ACTIVAS de origen='tcg', NO despublica nada de eso y avisa (Excel
#     corrupto / a medias). El freno es SOLO de la retirada: precios y
#     reactivaciones se aplican igual, siempre (medido el 10-sep-2026: pararlos
#     tambien dejo la web sin refrescar precios un dia entero).
#   - MODO 'preview': calcula y avisa lo que HARIA, sin tocar la web (para la
#     primera pasada de prueba). MODO 'aplicar': ejecuta de verdad.
#
# Recado: informes/actualizar_tcg/_solicitud.json -> {"modo": "preview"|"aplicar"}
# Secrets (en el workflow): SUPABASE_URL, SUPABASE_KEY (o SUPABASE_SERVICE_KEY),
#   TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
# NO usa Keepa ni Anthropic: es solo comparacion de datos. Rapido.
# ============================================================================
import os, io, json, math, sys
import openpyxl
from supabase import create_client

sys.stdout.reconfigure(line_buffering=True)

# ---- Conexion Supabase (service key si esta, para poder escribir en web_productos) ----
SB_URL = os.environ['SUPABASE_URL']
SB_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']
sb = create_client(SB_URL, SB_KEY)

BUCKET   = 'informes'
CAT_PATH = 'web_rank/catalogo.xlsx'                 # el MISMO Excel que sube el Paso 1
RECADO   = 'actualizar_tcg/_solicitud.json'

# ---- Reglas de precio (IDENTICAS al lote; ver index.html lanzarRankWeb / robot_lote) ----
COSTE_ESTANDAR        = 8.55     # coste normal fijo de un Funko Pop! estandar (PVPR 17)
MARGEN                = 1.75
SUELO_OFERTA_ESTANDAR = 11.95
STOCK_MIN             = 2        # < 2 (0 o 1) NO se publica: una unidad es jugarsela
# UMBRAL_FRENO_PCT: % de las fichas ACTIVAS de origen='tcg' que se pueden
# despublicar de golpe antes de frenar la retirada. Un numero fijo (el viejo
# UMBRAL_FRENO=40) salta con cualquier limpieza normal de catalogo: el
# 10-sep-2026, con el proveedor de mudanza de almacen, 103 de 475 activas
# (21,7%) eran limpieza real y un freno fijo las habria bloqueado igual que a
# un Excel corrupto. No hay serie diaria de despublicaciones con la que medir
# un corte propio (verificado 10-sep-2026: sin tabla de log para este robot),
# asi que se usa el mismo corte que el blindaje del escaner
# (UMBRAL_PARCIAL en moloka_escaner_nube.py): 35%.
UMBRAL_FRENO_PCT      = 0.35
ESTADOS_OK            = ('disponible', 'oferta', 'saldo')   # PreOrder/Backorder = fuera

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def avisar(texto):
    import requests as _rq
    print(">>> TELEGRAM:", texto.replace('\n', ' | '))
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("AVISO: faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID; no se envia."); return
    try:
        _rq.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                 data={'chat_id': TELEGRAM_CHAT_ID, 'text': texto, 'parse_mode': 'HTML'}, timeout=20)
    except Exception as ex:
        print("AVISO: fallo enviando Telegram:", ex)

# --- redondeo comercial al ,95 (replica EXACTA de la JS redondea95 = Math.round(x-0.95)+0.95) ---
def redondea95(x):
    return math.floor(x - 0.95 + 0.5) + 0.95

# --- redondeo al ,95 arriba (verbatim de robot_lote._redondea_95_arriba; lo usa la oferta) ---
def _redondea_95_arriba(x):
    e = math.floor(x)
    return e + 0.95 if x <= e + 0.95 + 1e-9 else e + 1.95

# --- formato (verbatim de robot_rank_web.formato_de): decide si es Funko Pop! estandar ---
def formato_de(tipo, cab):
    c = cab.lower()
    if 'Keychain' in tipo: return 'Llavero'
    if 'Bitty' in tipo or 'bitty' in c: return 'Bitty Pop'
    if 'pocket' in c: return 'Bitty Pop'
    if ' ride' in c or ' town' in c or 'moment' in c: return 'Diorama'
    if 'deluxe' in c: return 'Deluxe'
    if '6"' in c or '6 "' in c or '15 cm' in c or '15cm' in c or 'oversized' in c: return 'Deluxe'
    return 'Funko Pop!'

# --- oferta (verbatim de robot_lote.calcular_oferta) ---
def calcular_oferta(es_estandar, precio_web, precio_tcg, estado):
    if not es_estandar:
        return None
    if (estado or '').strip().lower() not in ('oferta', 'saldo'):
        return None
    if precio_web is None or precio_tcg is None:
        return None
    ahorro = COSTE_ESTANDAR - precio_tcg
    if ahorro <= 0:
        return None
    bruto = precio_web - ahorro
    oferta = max(SUELO_OFERTA_ESTANDAR, _redondea_95_arriba(bruto))
    if oferta >= precio_web:
        return None
    return round(oferta, 2)

def _num(x):
    try: return float(str(x).replace(',', '.').strip())
    except (TypeError, ValueError, AttributeError): return None

# --- decide el freno: PORCENTAJE de las activas, no un numero fijo ---
def decidir_freno(n_despublicar, n_activas, umbral_pct=UMBRAL_FRENO_PCT):
    """(frenado, pct_baja) - pct_baja es None si no hay activas con que medir."""
    if not n_activas:
        return (False, None)
    pct = n_despublicar / n_activas
    return (pct > umbral_pct, round(pct * 100, 1))

# --- hasta N ejemplos con nombre, para que el Telegram no obligue a abrir el log ---
def ejemplos_despublicar(lista, n=8):
    out = []
    for f, motivo in lista[:n]:
        nombre = str(f.get('nombre') or f.get('ean') or '?')[:60]
        out.append(f"  • {nombre} ({motivo})")
    return "\n".join(out)

# --- lee el Excel crudo de TCG con TODO lo que necesita el mantenimiento ---
def cargar_catalogo_tcg():
    """{ean: {stock, precio, pvpr, tipo, cab, estado}} del Excel de TCG."""
    data = sb.storage.from_(BUCKET).download(CAT_PATH)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c is not None else '' for c in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    iE  = idx['EAN']; iS = idx['Stock']; iP = idx['Precio']; iV = idx['PVPR']
    iT  = idx['Tipo Producto']; iEst = idx['Estado producto']; iC = idx['Cabecera']
    m = {}
    for r in rows[1:]:
        ean = str(r[iE] or '').strip()
        if not ean:
            continue
        m[ean] = {
            'stock':  _num(r[iS]),
            'precio': _num(r[iP]),
            'pvpr':   _num(r[iV]),
            'tipo':   str(r[iT] or '').strip(),
            'cab':    str(r[iC] or '').strip(),
            'estado': str(r[iEst] or '').strip(),
        }
    return m

def precio_objetivo(info):
    """Devuelve (precio_web, precio_oferta) con la regla EXACTA del lote."""
    pvpr = info['pvpr'] or 0
    es_estandar = (formato_de(info['tipo'], info['cab']) == 'Funko Pop!' and round(pvpr) == 17)
    coste = info['precio']
    if es_estandar:
        precio_web = redondea95(COSTE_ESTANDAR * MARGEN)
    else:
        if coste is None:
            return (None, None)
        precio_web = redondea95(coste * MARGEN)
    precio_oferta = calcular_oferta(es_estandar, precio_web, coste, info['estado'])
    return (round(precio_web, 2), precio_oferta)

def main():
    # --- modo (preview / aplicar) ---
    modo = 'preview'
    try:
        crudo = sb.storage.from_(BUCKET).download(RECADO)
        modo = (json.loads(crudo.decode('utf-8')).get('modo') or 'preview').strip().lower()
    except Exception:
        print("Sin recado; asumo modo 'preview' (no toca nada).")
    if modo not in ('preview', 'aplicar'):
        modo = 'preview'
    print(f">>> ACTUALIZADOR TCG | modo: {modo.upper()}")

    # --- catalogo TCG del Excel recien subido ---
    try:
        catalogo = cargar_catalogo_tcg()
    except Exception as e:
        avisar(f"⚠️ Actualizador TCG: no pude leer el catalogo ({e}). No se toca nada.")
        return
    print(f"Catalogo TCG: {len(catalogo)} EANs.")

    # --- fichas publicadas de TCG (SOLO origen='tcg' -> joyas intactas) ---
    fichas = sb.table('web_productos').select(
        'id,ean,nombre,activo,precio,precio_web,precio_oferta'
    ).eq('origen', 'tcg').execute().data or []
    print(f"Fichas origen='tcg' en web: {len(fichas)}")

    despublicar, reactivar, recios = [], [], []   # 'recios' = cambios de precio/oferta
    for f in fichas:
        ean = str(f.get('ean') or '').strip()
        info = catalogo.get(ean)
        servible = bool(info) and (info['estado'].lower() in ESTADOS_OK) \
                   and (info['stock'] is not None and info['stock'] >= STOCK_MIN)
        activo = bool(f.get('activo'))

        if not servible:
            if activo:
                motivo = ('desaparecio' if not info else
                          f"estado {info['estado']}" if info['estado'].lower() not in ESTADOS_OK else
                          f"stock {info['stock']}")
                despublicar.append((f, motivo))
            continue

        # servible: precio objetivo + (si estaba off) reactivar
        pw, pof = precio_objetivo(info)
        if pw is None:
            continue
        cambio_precio = (round(f.get('precio_web') or -1, 2) != pw or
                         (round(f.get('precio_oferta'), 2) if f.get('precio_oferta') is not None else None) != pof)
        if not activo:
            reactivar.append((f, pw, pof))
        elif cambio_precio:
            recios.append((f, pw, pof))

    # --- resumen ---
    activas_hoy = sum(1 for f in fichas if f.get('activo'))
    frenado, pct_baja = decidir_freno(len(despublicar), activas_hoy)
    resumen_baja = f"{len(despublicar)}/{activas_hoy}" + (f" ({pct_baja}%)" if pct_baja is not None else "")
    print(f"\n>>> Despublicaria: {resumen_baja} | Reactivaria: {len(reactivar)} | Reprecaria: {len(recios)}")
    for f, m in despublicar[:60]:
        print(f"   [OFF] {f.get('ean')} {str(f.get('nombre') or '')[:42]} ({m})")
    for f, pw, pof in recios[:60]:
        ofe = f" oferta {pof}" if pof else ""
        print(f"   [€]   {f.get('ean')} {str(f.get('nombre') or '')[:36]} -> {pw}{ofe}")
    for f, pw, pof in reactivar[:60]:
        print(f"   [ON]  {f.get('ean')} {str(f.get('nombre') or '')[:42]} -> {pw}")
    if frenado:
        print(f"\n🛑 FRENO: {resumen_baja} supera el limite del {UMBRAL_FRENO_PCT*100:.0f}% de las activas.")

    if modo == 'preview':
        cuerpo = (f"👁️ <b>Actualizador TCG (PRUEBA, sin tocar nada)</b>\n"
                  f"Despublicaria: {resumen_baja}\nReactivaria: {len(reactivar)}\n"
                  f"Ajustaria precio: {len(recios)}\n")
        if frenado:
            cuerpo += (f"\n🛑 Supera el limite del freno ({UMBRAL_FRENO_PCT*100:.0f}% de las activas): "
                       f"en modo APLICAR no se despublicaria nada de esto; precios y reactivaciones si.\n")
        if despublicar:
            cuerpo += f"\nEjemplos a despublicar:\n{ejemplos_despublicar(despublicar)}\n"
        cuerpo += "\nSi te cuadra, lo paso a automatico."
        avisar(cuerpo)
        print("\nMODO PREVIEW: no se ha tocado la web.")
        return

    # --- APLICAR (solo origen='tcg', fila a fila por id) ---
    # El freno para SOLO la retirada: precios y reactivaciones se aplican igual.
    if frenado:
        avisar(f"🛑 <b>Actualizador TCG: freno por porcentaje</b>\n"
               f"Despublicaria {resumen_baja} de las activas (limite {UMBRAL_FRENO_PCT*100:.0f}%). "
               f"NO se despublica nada de esto; precios y reactivaciones se aplican igual. "
               f"Revisa el Excel de TCG (¿incompleto o mal descargado?) o confirma que es limpieza real.\n\n"
               f"Ejemplos:\n{ejemplos_despublicar(despublicar)}")

    n_off = n_on = n_eur = 0
    for f, _m in ([] if frenado else despublicar):
        try: sb.table('web_productos').update({'activo': False}).eq('id', f['id']).eq('origen', 'tcg').execute(); n_off += 1
        except Exception as ex: print("ERR off", f.get('ean'), ex)
    for f, pw, pof in reactivar:
        upd = {'activo': True, 'precio': pw, 'precio_web': pw, 'precio_oferta': pof}
        try: sb.table('web_productos').update(upd).eq('id', f['id']).eq('origen', 'tcg').execute(); n_on += 1
        except Exception as ex: print("ERR on", f.get('ean'), ex)
    for f, pw, pof in recios:
        upd = {'precio': pw, 'precio_web': pw, 'precio_oferta': pof}
        try: sb.table('web_productos').update(upd).eq('id', f['id']).eq('origen', 'tcg').execute(); n_eur += 1
        except Exception as ex: print("ERR eur", f.get('ean'), ex)

    # Reconstruir la web: Astro es estatico (el precio va "horneado" en el HTML),
    # asi que sin esto los cambios quedan en Supabase pero la web sigue mostrando lo
    # viejo. Solo si hubo cambios reales. Da un toque al deploy hook de Vercel (lo
    # mismo que hace web-rebuild.yml).
    web_reconstruida = False
    if (n_off + n_on + n_eur) > 0:
        hook = os.environ.get('VERCEL_DEPLOY_HOOK')
        if hook:
            try:
                import requests as _rq
                _rq.post(hook, timeout=20)
                web_reconstruida = True
                print(">>> Web: rebuild disparado (deploy hook de Vercel).")
            except Exception as ex:
                print("AVISO: no pude disparar el rebuild de la web:", ex)
        else:
            print("AVISO: falta el secret VERCEL_DEPLOY_HOOK; la web NO se reconstruira sola.")

    avisar(f"✅ <b>Actualizador TCG</b>\n"
           f"Despublicados: {n_off}\nReactivados: {n_on}\nPrecios ajustados: {n_eur}"
           + (f"\n🛑 Freno: {len(despublicar)} fichas NO despublicadas (ver aviso anterior)." if frenado else "")
           + ("\n🔄 Reconstruyendo la web…" if web_reconstruida else
              ("\n⚠️ Cambios guardados, pero reconstruye la web a mano (faltó el deploy hook)." if (n_off+n_on+n_eur) > 0 else "")))
    print(f"\nAPLICADO: off={n_off} on={n_on} eur={n_eur} | frenado={frenado} | web_rebuild={web_reconstruida}")

if __name__ == '__main__':
    main()
