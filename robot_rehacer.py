# -*- coding: utf-8 -*-
"""
MOLOKA · FÁBRICA · ROBOT REHACER FOTOS
Vuelve a montar los montajes (portada/neón/regla/caja/figura/protector) de una ficha
usando la CAJA y la FIGURA que el usuario eligió a mano en la app, SIN pisar las fotos
que el usuario ya hubiera subido con "cambiar por la mía" (carpeta /propias/).
Lee el recado fabrica/_solicitud_rehacer.json {id, caja, figura}.
"""
import os, io, json, time, requests
import numpy as np
from PIL import Image
from supabase import create_client
import motor_fotos as M

def cuadrar_foto(data):
    """Recorta el blanco sobrante de una foto y la centra en un lienzo cuadrado blanco,
    para que las fotos propias (verticales, con márgenes) salgan como las de Keepa."""
    img = Image.open(io.BytesIO(data)).convert('RGB')
    arr = np.array(img)
    nf = ~((arr[:,:,0] >= 240) & (arr[:,:,1] >= 240) & (arr[:,:,2] >= 240))
    ys, xs = np.where(nf)
    if len(xs) and len(ys):
        img = img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    w, h = img.size
    lado = int(max(w, h) * 1.08)  # margen del 8% alrededor
    lienzo = Image.new('RGB', (lado, lado), (255, 255, 255))
    lienzo.paste(img, ((lado - w) // 2, (lado - h) // 2))
    buf = io.BytesIO(); lienzo.save(buf, "JPEG", quality=94); return buf.getvalue()

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
BUCKET = 'fotos-fabrica'
HEADERS = {"User-Agent": "Mozilla/5.0"}

sb       = create_client(SUPABASE_URL, SUPABASE_KEY)
sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
admin    = sb_admin

def descargar(url):
    r = requests.get(url, headers=HEADERS, timeout=20); r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert('RGB')

def a_jpg_bytes(img, q=94):
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=q); return buf.getvalue()

def subir(admin, ruta, data):
    """Sube (o reemplaza) un jpg al bucket y devuelve su URL pública con rompe-caché
    (?v=timestamp) para que el navegador y el CDN no muestren la versión vieja al rehacer."""
    admin.storage.from_(BUCKET).upload(
        ruta, data,
        {"content-type": "image/jpeg", "upsert": "true"}  # upsert: si ya existe, lo reemplaza
    )
    url = admin.storage.from_(BUCKET).get_public_url(ruta)
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}v={int(time.time())}"

def descargar_asset(nombre):
    """Baja un asset fijo (fondo_neon / regla_10cm) del Storage en vez de /content."""
    url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/assets/{nombre}"
    r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
    return Image.open(io.BytesIO(r.content))

def generar_fotos(f, fondo, regla, prot=None):
    """Recorta la figura, control de calidad, monta neón/regla/portada y sube a Storage.
    Devuelve (fotos_generadas, error_o_None). La caja y la figura se reutilizan de los
    inputs Keepa para que la galería web salga completa (portada/caja/figura/neon/regla)."""
    ean = f.get('ean','sinEAN')
    fe  = f.get('fotos_elegidas') or {}
    url_fig  = fe.get('recorte_moloka') or fe.get('principal')
    url_caja = fe.get('caja')                       # costura: la caja es 'caja' (no 'portada')
    if not url_fig:
        return None, "sin foto de figura (recorte)"
    figura = descargar(url_fig)
    rec = M.recortar(figura)
    ok, motivo = M.test_calidad(rec)
    if not ok:
        return None, f"recorte sucio ({motivo})"
    enlaces = {}
    enlaces['ficha'] = subir(admin, f"{ean}/ficha.jpg", a_jpg_bytes(M.montar_m7(rec, f)))
    if url_caja:
        caja = descargar(url_caja)
        enlaces['portada'] = subir(admin, f"{ean}/portada.jpg", a_jpg_bytes(M.montar_portada(caja, figura)))
        enlaces['caja']    = url_caja               # input reutilizado para la galería
    enlaces['figura'] = url_fig                      # input reutilizado para la galería
    # PROTECTOR: solo si la ficha lo lleva y tenemos plantilla + caja
    if f.get('con_protector') and prot is not None and url_caja:
        try:
            caja_img = descargar(url_caja)
            enlaces['protector'] = subir(admin, f"{ean}/protector.jpg", a_jpg_bytes(M.montar_protector(caja_img, prot)))
        except Exception as e:
            print(f"   (aviso: no pude montar el protector: {e})")
    return enlaces, None

def leer_recado():
    try:
        r = admin.storage.from_('informes').download('fabrica/_solicitud_rehacer.json')
        return json.loads(r.decode('utf-8'))
    except Exception as e:
        print(f"No hay recado de rehacer (o no se pudo leer): {e}")
        return None

def limpiar_recado():
    try: admin.storage.from_('informes').remove(['fabrica/_solicitud_rehacer.json'])
    except Exception: pass

def main():
    recado = leer_recado()
    if not recado or not recado.get('id'):
        print("Sin recado válido. Nada que rehacer."); return
    fid  = recado['id']
    caja = recado.get('caja')
    figura = recado.get('figura')
    print(f"Rehacer fotos de ficha id={fid}")
    print(f"   CAJA   recibida del recado: {caja}")
    print(f"   FIGURA recibida del recado: {figura}")
    propias = recado.get('propias') or {}
    if propias:
        print(f"   FOTOS PROPIAS pendientes: {list(propias.keys())}")

    fila = (sb.table('fabrica_fichas').select('*').eq('id', fid).limit(1).execute().data or [None])[0]
    if not fila:
        print("Ficha no encontrada."); limpiar_recado(); return

    # Lo que el usuario subió a mano (carpeta /propias/) NO se pisa
    actuales = fila.get('fotos_generadas') or {}
    mias = {k: v for k, v in actuales.items() if isinstance(v, str) and '/propias/' in v}
    if mias:
        print(f"   conservando tus fotos: {', '.join(mias.keys())}")

    # PROMOCIONAR FOTOS PROPIAS: la app las subió a 'informes' (sin RLS para ella);
    # el robot las mueve a fotos-fabrica (con service key, saltándose el RLS) y obtiene
    # su URL pública. Caja/figura propias se usan como input del montaje; las demás
    # (portada/neon/regla/protector) sustituyen directamente al montaje final.
    propias_pub = {}
    for tipo, ruta_informes in propias.items():
        try:
            data = admin.storage.from_('informes').download(ruta_informes)
            data = cuadrar_foto(data)   # recorta blanco sobrante + lienzo cuadrado (como Keepa)
            destino = f"{fila.get('ean','sinEAN')}/propias/{tipo}_{int(time.time())}.jpg"
            url = subir(admin, destino, data)
            propias_pub[tipo] = url
            print(f"   foto propia '{tipo}' cuadrada y movida a fotos-fabrica -> {url}")
        except Exception as e:
            print(f"   (aviso: no pude mover la foto propia '{tipo}': {e})")

    # Montar con la caja/figura elegidas (si subiste caja/figura propia, manda esa)
    fe = dict(fila.get('fotos_elegidas') or {})
    if caja:   fe['caja'] = caja
    if figura: fe['recorte_moloka'] = figura
    if propias_pub.get('caja'):   fe['caja'] = propias_pub['caja']
    if propias_pub.get('figura'): fe['recorte_moloka'] = propias_pub['figura']
    if propias_pub.get('silueta'): fe['recorte_moloka'] = propias_pub['silueta']
    fila['fotos_elegidas'] = fe

    print("Descargando assets...")
    fondo = descargar_asset('fondo_neon.png')
    regla = descargar_asset('regla_10cm.png')
    try: prot = descargar_asset('protector_funko.png')
    except Exception: prot = None

    enlaces, err = generar_fotos(fila, fondo, regla, prot)
    if err:
        print(f"❌ No se pudo rehacer: {err}"); limpiar_recado(); return
    print("   --- URLs montadas ---")
    for k in ('portada','ficha','caja','figura','protector'):
        if k in enlaces: print(f"   {k}: {enlaces[k]}")

    # Mezclar: lo montado, respetando lo que ya tenías propio (/propias/)
    final = dict(enlaces)
    final.update(mias)
    # Secundarias propias: van a la galería de secundarias (ya cuadradas), NO como montaje
    sec_propias = [u for t, u in propias_pub.items() if t.startswith('secundaria')]
    if sec_propias:
        fe['secundarias'] = (fe.get('secundarias') or []) + sec_propias
    # Las fotos propias que son montaje FINAL (portada/neon/regla/protector/caja/figura)
    # sustituyen directamente a lo montado (van tal cual a web/Miravia).
    for tipo, url in propias_pub.items():
        if tipo.startswith('secundaria'):
            continue
        final[tipo] = url

    sb.table('fabrica_fichas').update({'fotos_generadas': final, 'fotos_elegidas': fe}).eq('id', fid).execute()
    print(f"✅ Fotos rehechas: {', '.join(final.keys())}")
    # Limpiar las fotos propias ya procesadas del bucket informes
    for ruta in propias.values():
        try: admin.storage.from_('informes').remove([ruta])
        except Exception: pass
    limpiar_recado()

if __name__ == '__main__':
    main()
