# ============================================================================
# ROBOT LOTE  -  Fabrica de fichas para la linea "Funkos TCG bajo pedido"
# ----------------------------------------------------------------------------
# Para TCG la VERDAD del producto es TCG (lo que pides por EAN = lo que llega).
# Por eso esta linea NO usa imagen ni nombre de Keepa (que pueden venir del ASIN
# equivocado) y NO pasa por el montaje M7 de Elena (la imagen de TCG es caja+
# figura, el recorte fallaria). En su lugar:
#   - nombre + imagen salen del CATALOGO de TCG (web_rank/catalogo.xlsx, que subio
#     el Paso 1), por EAN.
#   - la descripcion la redacta Claude con el MISMO prompt de la fabrica
#     (reutilizado de robot_preparar, sin reescribirlo), a partir del dato de TCG.
#   - se escribe un BORRADOR directamente en web_productos con origen='tcg' y
#     activo=false (oculto) -> se revisa y se activa cuando esta OK.
# NO toca robot_preparar / robot_generar / motor_fotos: la fabrica "joya" de
# Elena queda 100% intacta. Solo reutiliza de robot_preparar (lectura): el
# cliente de Anthropic, el PROMPT, el MODELO, las CATEGORIAS, slugify y sb.
# Resumible: si un EAN ya esta en web_productos, lo salta.
# Secrets (ya en fabrica-lote.yml): KEEPA_API_KEY, SUPABASE_URL, SUPABASE_KEY,
#   SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY
# ============================================================================
import json, datetime, sys, io, re, unicodedata, requests
import openpyxl
import robot_preparar as R   # reusa (solo lectura): cliente, PROMPT_SISTEMA, MODELO, CATEGORIAS, slugify, descargar_b64, sb

sys.stdout.reconfigure(line_buffering=True)

BUCKET      = 'informes'
RECADO_LOTE = 'fabrica_lote/_solicitud_lote.json'
CAT_PATH    = 'web_rank/catalogo.xlsx'   # el catalogo que dejo el Paso 1
FOTOS_PATH  = 'web_rank/ranking_tcg_fotos.xlsx'  # fotos Keepa (alta res) del corte

# Bloque legal GPSR de Funko (verbatim de robot_generar; obligatorio en Funkos).
GPSR_WEB = ("<br><br><b>Información de seguridad del producto (GPSR)</b><br>"
            "Responsable en la UE: Funko EU BV · Zuidplein 36, 1077 XV Ámsterdam (NL) · supportEMEA@funko.com")

# Normalizacion de franquicias: unifica grafias distintas del MISMO fandom para que
# el filtro de la web salga limpio. Solo fusiona duplicados claros (y las series de
# Star Wars bajo "Star Wars"). NO fusiona submarcas tipo Deadpool/X-Men en Marvel:
# eso es decision de taxonomia, se puede ampliar cuando quieras.
FANDOM_CANON = {
    'kimetsu no yaiba': 'Demon Slayer',
    'kimetsu no yaiba (demon slayer)': 'Demon Slayer',
    'demon slayer kimetsu no yaiba': 'Demon Slayer',
    'demon slayer': 'Demon Slayer',
    'bola de dragon': 'Dragon Ball', 'bola de dragón': 'Dragon Ball',
    'dragonball': 'Dragon Ball', 'dragon ball z': 'Dragon Ball',
    'dragon ball super': 'Dragon Ball', 'dragon ball gt': 'Dragon Ball',
    'masters of the universe': 'Masters del Universo',
    'masters del universo': 'Masters del Universo',
    'nightmare before christmas': 'Pesadilla antes de Navidad',
    'pesadilla antes de navidad 30th': 'Pesadilla antes de Navidad',
    'kaiju nº8': 'Kaiju No. 8', 'kaiju nº 8': 'Kaiju No. 8',
    'kaiju no 8': 'Kaiju No. 8', 'kaiju no. 8': 'Kaiju No. 8',
    'it': 'IT', 'nlf': 'NFL',
    'arcane': 'League of Legends', 'arcane: league of legends': 'League of Legends',
    'the mandalorian': 'Star Wars', 'ahsoka': 'Star Wars',
    'star wars the acolyte': 'Star Wars', 'star wars: the acolyte': 'Star Wars',
    'the acolyte': 'Star Wars',
}
def normaliza_fandom(f):
    if not f:
        return f
    return FANDOM_CANON.get(f.strip().lower(), f.strip())

# ---------- FRENO difuso: nombre TCG vs nombre Keepa ----------
# Nunca son identicos, asi que comparamos por palabras del PERSONAJE: quitamos
# morralla y la franquicia de ambos; si comparten algun token -> mismo producto
# (foto Keepa OK). Si no comparten NADA -> freno (foto TCG, por seguridad).
_STOP = set("""funko pop vinyl figura figure de del la el los las y e and the a un una uno para con sin
coleccionable coleccionables coleccionistas coleccion idea regalo gift mercancia oficial official
merchandise juguetes toys ninos adultos kids fans tv anime animation games game movies movie video
muneco modelo model display exhibicion exposicion collectable collectible special edition exclusive
exclusivo vinilo serie bobble head bobblehead nuevo new standard std emea usa eu glow chase ride
cabeza oscilante tete figurine vol""".split())

def _sin_acentos(x):
    return ''.join(c for c in unicodedata.normalize('NFD', str(x)) if unicodedata.category(c) != 'Mn')

def _tokens_personaje(nombre, fandom=''):
    s = _sin_acentos((nombre or '').lower())
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    fset = set(_sin_acentos((fandom or '').lower()).split())
    toks = set()
    for w in s.split():
        if len(w) < 3 or w in _STOP or w in fset or w.isdigit():
            continue
        toks.add(w)
    return toks

def freno_ok(nombre_tcg, nombre_keepa, fandom):
    t1 = _tokens_personaje(nombre_tcg, fandom)
    t2 = _tokens_personaje(nombre_keepa, fandom)
    if not t1 or not t2:
        return True          # nombre demasiado corto para juzgar -> no frenamos
    return len(t1 & t2) >= 1 # comparten al menos el personaje

def cargar_fotos_keepa():
    """{ean: {nombre_keepa, img_figura, img_caja}} del ranking_tcg_fotos.xlsx. Si no
    existe, {} (todo ira por fallback TCG)."""
    data = R._bajar(BUCKET, FOTOS_PATH)
    if data is None:
        return {}
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    idx = {(str(c).strip() if c is not None else ''): i for i, c in enumerate(rows[0])}
    iE, iNk, iIf, iIc = idx.get('EAN'), idx.get('Nombre Keepa'), idx.get('Img figura'), idx.get('Img caja')
    if iE is None or iIf is None:
        return {}
    m = {}
    for r in rows[1:]:
        ean = str(r[iE] or '').strip()
        if not ean:
            continue
        m[ean] = {'nombre_keepa': str(r[iNk] or '') if iNk is not None else '',
                  'img_figura':   str(r[iIf] or '') if iIf is not None else '',
                  'img_caja':     str(r[iIc] or '') if iIc is not None else ''}
    return m

# ---------------------------------------------------------------------------
def cargar_catalogo_tcg():
    """Devuelve {ean: (cabecera, [urls_imagen])} leido del catalogo de TCG."""
    data = R.sb.storage.from_(BUCKET).download(CAT_PATH)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c is not None else '' for c in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    iE   = idx['EAN']
    iCab = idx['Cabecera']
    iImg = idx.get('Imágenes', idx.get('Imagenes'))
    m = {}
    for r in rows[1:]:
        ean = str(r[iE] or '').strip()
        if not ean:
            continue
        cab = str(r[iCab] or '').strip()
        imgs = []
        if iImg is not None:
            raw = str(r[iImg] or '').strip()
            imgs = [u.strip() for u in raw.split(';') if u.strip().lower().startswith('http')]
        m[ean] = (cab, imgs)
    return m

# ---------------------------------------------------------------------------
def redactar_tcg(nombre_tcg, img_url, rarezas):
    """Misma redaccion que la fabrica (MISMO PROMPT_SISTEMA), pero con datos de TCG.
    Le pasa la imagen de TCG (caja+figura) para que Claude lea el numero de la caja."""
    datos = {"titulo_origen_solo_para_identificar": nombre_tcg,
             "marca": "Funko", "tamano": "aprox. 10 cm"}
    datos.update({k: v for k, v in (rarezas or {}).items() if v})
    contenido = [{"type": "text", "text":
        "DATOS (verificados, no anadas nada que no este aqui):\n" +
        json.dumps(datos, ensure_ascii=False, indent=2) +
        "\n\nLee el numero de coleccion de la imagen de la caja (esquina sup. derecha). "
        "Si no se ve claro, no pongas numero."}]
    if img_url:
        try:
            b64 = R.descargar_b64(img_url)
            contenido.insert(0, {"type": "image",
                                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
        except Exception as e:
            print(f"    (aviso: no pude bajar la imagen TCG, redacto sin ella: {e})")
    msg = R.cliente.messages.create(model=R.MODELO, max_tokens=1800,
                                    system=R.PROMPT_SISTEMA,
                                    messages=[{"role": "user", "content": contenido}])
    texto = msg.content[0].text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    return json.loads(texto)

# ---------------------------------------------------------------------------
def rehospedar_imagen(url, ean, i):
    """Descarga la imagen de TCG y la SUBE a Supabase Storage (fotos-fabrica/tcg/).
    Asi la web sirve la imagen desde Moloka y NO enlaza a tcgfactory.com (oculta el
    proveedor y no depende de ellos). Devuelve la URL publica de Moloka, o None."""
    try:
        r = requests.get(url, timeout=30); r.raise_for_status()
        datos = r.content
    except Exception as e:
        print(f"      AVISO: no pude descargar la imagen TCG ({e})")
        return None
    nombre = f"tcg/{ean}_{i}.jpg"
    try:
        R.sb_admin.storage.from_(R.BUCKET_FOTOS).upload(
            nombre, datos, {"content-type": "image/jpeg", "upsert": "true"})
    except Exception as e:
        print(f"      AVISO: no pude subir la imagen a Supabase ({e})")
        return None
    pub = R.sb_admin.storage.from_(R.BUCKET_FOTOS).get_public_url(nombre)
    if isinstance(pub, dict):
        pub = pub.get('publicUrl') or pub.get('publicURL')
    return pub

# ---------------------------------------------------------------------------
def ya_en_web(ean):
    try:
        r = R.sb.table('web_productos').select('id').eq('ean', str(ean)).limit(1).execute().data
        return bool(r)
    except Exception:
        return False

# ---------------------------------------------------------------------------
def main():
    crudo = R._bajar(BUCKET, RECADO_LOTE)
    if crudo is None:
        print("SIN recado de lote. Nada que hacer."); return
    recado = json.loads(crudo.decode('utf-8'))
    tanda  = recado.get('tanda') or datetime.datetime.now().strftime('%Y%m%d_%H%M')
    items  = recado.get('items') or []
    print(f"Recado LOTE TCG: tanda {tanda}, {len(items)} EAN(s).")

    try:
        catalogo = cargar_catalogo_tcg()
        print(f"Catalogo TCG cargado: {len(catalogo)} EANs con nombre/imagen.")
    except Exception as e:
        print(f"ERROR: no pude cargar el catalogo TCG ({CAT_PATH}): {e}")
        return

    ok, err, saltados, sin_dato = [], [], [], []
    for i, it in enumerate(items, 1):
        ean = str(it.get('ean') or '').strip()
        if not ean:
            continue
        if ya_en_web(ean):
            print(f"[{i}/{len(items)}] {ean} ya esta en web -> salto")
            saltados.append(ean); continue
        nombre_tcg, imgs = catalogo.get(ean, (None, []))
        if not nombre_tcg or not imgs:
            print(f"[{i}/{len(items)}] {ean} sin nombre/imagen en catalogo TCG -> salto")
            sin_dato.append(ean); continue

        print(f"\n[{i}/{len(items)}] TCG {ean} | {nombre_tcg[:55]}")
        try:
            # Re-alojar las fotos de TCG en Supabase (fondo blanco -> recorte fiable).
            # Convencion TCG: imgs[0]=figura sola, imgs[1]=caja.
            imgs_web = []
            for k, u in enumerate(imgs):
                pub = rehospedar_imagen(u, ean, k)
                if pub: imgs_web.append(pub)
            if not imgs_web:
                print(f"   {ean}: no pude re-alojar ninguna imagen -> salto")
                err.append(ean); continue
            img_fig  = imgs_web[0]
            img_caja = imgs_web[1] if len(imgs_web) > 1 else imgs_web[0]

            rarezas = {"es_chase": it.get('es_chase'),
                       "es_vaulted": it.get('es_vaulted'),
                       "es_exclusivo": it.get('es_exclusivo')}
            out = redactar_tcg(nombre_tcg, img_caja, rarezas)   # la caja lleva el #numero
            categoria    = out.get('categoria') if out.get('categoria') in R.CATEGORIAS else None
            nombre_corto = (out.get('nombre_corto') or '').strip() or nombre_tcg
            slug         = R.slugify(out.get('slug') or nombre_corto)
            fandom_norm  = normaliza_fandom(out.get('fandom'))
            formato      = (it.get('formato') or '').strip() or None

            web_desc = (out.get('web_desc') or '').rstrip()
            if web_desc and 'GPSR' not in web_desc:
                web_desc += GPSR_WEB

            # ---- IMAGENES: montaje Moloka (portada + M7) recortando de la figura TCG ----
            filaf = {'ean': ean, 'nombre_corto': nombre_corto, 'fandom': fandom_norm,
                     'formato': formato,
                     'fotos_elegidas': {'caja': img_caja, 'recorte_moloka': img_fig},
                     'con_protector': False}
            enlaces, errf = R.generar_fotos(filaf, None, None, None)
            if errf or not enlaces:
                print(f"   sin montaje ({errf or 'sin enlaces'}) -> fotos TCG planas")
                imagen_principal = img_fig
                imagenes = imgs_web
                fuente = 'plano'
            else:
                # Orden pedido: PRINCIPAL = portada (caja+figura); el M7 al FINAL.
                gal = [enlaces.get('portada'), enlaces.get('figura'), enlaces.get('caja'), enlaces.get('ficha')]
                imagenes = [g for g in gal if g]
                imagen_principal = enlaces.get('portada') or enlaces.get('ficha') or img_fig
                fuente = 'montaje'

            fila = {
                'ean': ean, 'slug': slug,
                'origen': 'tcg', 'origen_id': ean,          # id del producto dentro de TCG = su EAN
                'seccion': 'funko',
                'titulo_seo': out.get('web_titulo'),
                'nombre': nombre_corto,
                'descripcion_html': web_desc or None,
                'licencia': 'Funko',
                'categoria': categoria, 'fandom': fandom_norm,
                'es_chase': bool(it.get('es_chase')),
                'es_vaulted': bool(it.get('es_vaulted')),
                'es_exclusivo': bool(it.get('es_exclusivo')),
                'precio': it.get('precio_web'), 'precio_web': it.get('precio_web'),
                'imagen_principal': imagen_principal, 'imagenes': imagenes,
                'formato': formato,
                'activo': False,                            # BORRADOR oculto hasta aprobar
                'en_web': False, 'en_miravia': False,
                'stock': 0, 'disponibilidad': 'pedido',     # literal EXACTO de la cinta (NO 'bajo pedido')
            }
            fila = {k: v for k, v in fila.items() if v is not None}
            R.sb.table('web_productos').insert(fila).execute()
            print(f"      OK [{fuente}] -> web_productos (borrador, activo=false) | {nombre_corto[:40]} "
                  f"| cat={categoria} | fmt={fila.get('formato')}")
            ok.append(ean)
        except Exception as e:
            print(f"   ERROR procesando {ean}: {e}")
            err.append(ean)

    # Borra el recado SOLO al terminar (si se corta antes, al relanzar retoma).
    try:
        R.sb.storage.from_(BUCKET).remove([RECADO_LOTE])
    except Exception:
        pass

    print(f"\n==== RESUMEN LOTE TCG {tanda} ====")
    print(f"  Creados (borrador): {len(ok)} | ya en web: {len(saltados)} "
          f"| sin dato TCG: {len(sin_dato)} | errores: {len(err)}")
    if err:      print(f"  EAN con error: {err}")
    if sin_dato: print(f"  EAN sin nombre/imagen: {sin_dato}")
    print("Fin.")

if __name__ == '__main__':
    main()
