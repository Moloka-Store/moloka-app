# ==========================================================================
# MOLOKA · Sincronizador de stock de la WEB desde el inventario físico
# --------------------------------------------------------------------------
# Cruza el inventario (tabla 'productos') con las fichas de la web
# (web_productos, SOLO origen='fabrica') por la pareja (EAN normalizado, es_chase)
# y actualiza 'stock' y 'disponibilidad'. Refleja ENTRADAS y SALIDAS:
#   - hay stock  -> disponibilidad='inmediato'
#   - no hay      -> disponibilidad='agotado' (la web oculta los agotados del listado,
#                    así NO se ofrece ni se vende lo que no tienes).
#
# 🔒 SOLO toca origen='fabrica'. TCG y BEMS son BAJO PEDIDO: su stock/disponibilidad
#    la gobiernan sus propios procesos (no el inventario físico); tocarlos los borraría.
#
# 🔒 FRENO: si fuera a marcar agotadas más del 40% de las fichas, ABORTA sin tocar nada
#    (protege contra un inventario mal cargado/vacío que ocultaría medio catálogo).
#
# Al final dispara el deploy hook de Vercel para que los cambios salgan online.
# Para GitHub Actions. Lo lanza el botón "Sincronizar stock" de la app.
# ==========================================================================
import os, sys, urllib.request
from supabase import create_client

sys.stdout.reconfigure(line_buffering=True)

UMBRAL_FRENO = 0.40   # si >40% de las fichas pasarían a agotado, no aplicar

def norm_ean(ean):
    # IDÉNTICO al del volcado (robot_generar) para que el cruce case igual
    return (str(ean) or '').strip().lstrip('0')

def _paginar(sb, tabla, cols, filtro_origen=None):
    filas, desde = [], 0
    while True:
        q = sb.table(tabla).select(cols)
        if filtro_origen:
            q = q.eq('origen', filtro_origen)
        r = q.range(desde, desde + 999).execute()
        lote = r.data or []
        filas += lote
        if len(lote) < 1000:
            break
        desde += 1000
    return filas

def main():
    sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

    # 1) Stock físico desde el inventario, sumado por (ean_norm, es_chase)
    inv = {}
    for p in _paginar(sb, 'productos', 'ean,es_chase,stock_moloka'):
        k = (norm_ean(p.get('ean')), bool(p.get('es_chase')))
        inv[k] = inv.get(k, 0) + (p.get('stock_moloka') or 0)
    print(f">>> Inventario: {len(inv)} claves (ean,chase) con stock físico")

    # 2) Fichas de la web de FÁBRICA (las que tienen stock real en el almacén)
    fichas = _paginar(sb, 'web_productos', 'id,ean,es_chase,stock,disponibilidad,nombre', filtro_origen='fabrica')
    print(f">>> Fichas de fábrica en web: {len(fichas)}")
    if not fichas:
        print("    Nada que sincronizar.")
        return

    # 3) Calcular cambios (sin aplicar todavía)
    cambios, nuevos_agotados = [], 0
    for w in fichas:
        k = (norm_ean(w.get('ean')), bool(w.get('es_chase')))
        stock_real = inv.get(k, 0)
        disp = 'inmediato' if stock_real > 0 else 'agotado'
        if (w.get('stock') or 0) != stock_real or (w.get('disponibilidad') or '') != disp:
            cambios.append((w, stock_real, disp))
            if disp == 'agotado' and (w.get('disponibilidad') or '') != 'agotado':
                nuevos_agotados += 1

    # 4) FRENO de seguridad
    if nuevos_agotados > UMBRAL_FRENO * len(fichas):
        print(f"🛑 ABORTADO: {nuevos_agotados} de {len(fichas)} fichas pasarían a AGOTADO "
              f"(más del {int(UMBRAL_FRENO*100)}%). Huele a inventario mal cargado. No he tocado NADA. "
              f"Revisa el inventario y vuelve a lanzar.")
        return

    # 5) Aplicar
    n = 0
    for w, stock_real, disp in cambios:
        try:
            sb.table('web_productos').update(
                {'stock': stock_real, 'disponibilidad': disp}).eq('id', w['id']).execute()
            flecha = '↑' if stock_real > (w.get('stock') or 0) else '↓'
            print(f"   {flecha} {str(w.get('nombre') or '')[:45]}: {w.get('stock')} -> {stock_real} ({disp})")
            n += 1
        except Exception as e:
            print(f"   (ERR {w.get('ean')}: {e})")
    print(f"\n>>> {n} fichas actualizadas de {len(fichas)}.")

    # 6) Reconstruir la web para que salga online
    hook = os.environ.get('VERCEL_DEPLOY_HOOK')
    if n and hook:
        try:
            urllib.request.urlopen(hook, data=b'', timeout=30)
            print(">>> Web reconstruyéndose (deploy hook disparado).")
        except Exception as e:
            print(f"   (aviso: no pude disparar el rebuild: {e})")
    elif not n:
        print("    Sin cambios: la web ya estaba al día.")

if __name__ == "__main__":
    main()
