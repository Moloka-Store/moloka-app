#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# moloka_escaner_pro_nube.py  —  ROBOT PRO EN LA NUBE (GitHub Actions)
# Segunda mitad del flujo Pro: Fernando ya subio en la app el Excel del proveedor y el/los
# CSV del Visualizador (uno por pais). Este robot los lee del buzon, corre el MOTOR VALIDADO
# (moloka_escaner_pro.py, mismas formulas/decision que el escaner de tokens, 22/22), compone
# el Excel de siempre, lo deja en la Biblioteca (escaner_resultados) y actualiza la memoria
# del proveedor (escaner_memoria) — igual que el Escaner API. CERO tokens de Keepa.
#
# Buzon: informes/escaner_pro/  con:
#   _solicitud_pro.json  -> {proveedor, marca, rank_maximo, catalogo,
#                            csv_paises:{ES:["a.csv","b.csv",..], IT:[..], ..}}
#   <catalogo>           -> Excel/CSV del proveedor
#   <csv por pais>       -> uno o VARIOS CSV del Visualizador por pais (Keepa exporta de
#                           5.000 en 5.000); el robot los FUNDE -> UN solo Excel por escaneo.
#
# Secrets (GitHub -> env): SUPABASE_URL, SUPABASE_KEY (o SUPABASE_SERVICE_KEY).

import os, sys, json, tempfile
from datetime import datetime, timezone
from collections import Counter
from supabase import create_client

# Motor validado (mismo repo). No re-implementamos formulas: se reutilizan tal cual.
from moloka_escaner_pro import (leer_proveedor, escanear_pro, escribir_excel, norm)

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']
BUCKET = 'informes'
BUZON = 'escaner_pro'
CARPETA_RESULTADOS = 'resultados'
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def _bajar(ruta_buzon, destino):
    data = sb.storage.from_(BUCKET).download(ruta_buzon)
    # La app comprime en gzip los ficheros grandes al subir (catalogos/CSV). Aqui los
    # descomprimimos si vienen gzip (magic bytes 1f 8b), igual que el escaner API.
    if len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b:
        import gzip
        data = gzip.decompress(data)
        if destino.endswith('.gz'): destino = destino[:-3]
    with open(destino, 'wb') as f: f.write(data)
    return destino

def leer_recado():
    data = sb.storage.from_(BUCKET).download(f'{BUZON}/_solicitud_pro.json')
    return json.loads(data.decode('utf-8'))

def leer_productos_propios():
    sup = {}
    try:
        d = 0
        while True:
            res = sb.table('productos').select('ean,stock_moloka,stock_fba').eq('activo', True).range(d, d+999).execute()
            if not res.data: break
            for p in res.data:
                if p.get('ean'): sup[norm(p['ean'])] = p
            if len(res.data) < 1000: break
            d += 1000
    except Exception as ex:
        print('AVISO: no se pudieron leer productos propios:', ex)
    return sup

def leer_memoria(prov):
    mem = {}
    try:
        d = 0
        while True:
            res = (sb.table('escaner_memoria').select('ean,es_case,pa,presente')
                     .eq('proveedor', prov).range(d, d+999).execute())
            if not res.data: break
            for m in res.data:
                mem[(norm(m['ean']), bool(m['es_case']))] = {
                    'pa': m.get('pa'), 'presente': bool(m.get('presente', True)), 'ean_db': m['ean']}
            if len(res.data) < 1000: break
            d += 1000
    except Exception as ex:
        print('AVISO: no se pudo leer la memoria (se trata todo como nuevo):', ex)
    print(f"Memoria {prov}: {len(mem)} EANs conocidos")
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

def main():
    rec = leer_recado()
    prov = rec['proveedor']; marca = rec.get('marca', 'TODAS')
    rank_max = int(rec.get('rank_maximo') or 30000)
    catalogo = rec['catalogo']            # nombre del fichero del proveedor en el buzon
    csv_paises = rec['csv_paises']        # {'ES':['a.csv','b.csv',..], ...}  (acepta str por compat)
    print(f"PRO | {prov} | Marca {marca} | Rank max {rank_max} | "
          f"Paises {{ {', '.join(f'{p}:{len(v) if isinstance(v,list) else 1}csv' for p,v in csv_paises.items())} }}")

    tmp = tempfile.mkdtemp()
    excel_path = _bajar(f'{BUZON}/{catalogo}', os.path.join(tmp, catalogo))
    paises = {}
    for p, nombres in csv_paises.items():
        if isinstance(nombres, str): nombres = [nombres]
        paises[p] = [_bajar(f'{BUZON}/{n}', os.path.join(tmp, n)) for n in nombres]

    # 1) Escaneo (motor validado) + productos propios para "En mi BD"
    sup = leer_productos_propios()
    res = escanear_pro(prov, marca, excel_path, paises, rank_maximo=rank_max, sup=sup)
    filas = res['filas']

    # 2) Memoria: estado de cada fila + agotados
    mem = leer_memoria(prov)
    for f in filas: f['_estado_mem'] = estado_mem(f, mem)
    cnt = Counter(f['_estado_mem'] for f in filas)
    claves_hoy = {(norm(f['core']), bool(f['es_chase'])) for f in filas}
    ausentes = [(k, info) for k, info in mem.items() if info['presente'] and k not in claves_hoy]
    print(f"Nuevos {cnt.get('nuevo',0)} | Reaparecidos {cnt.get('reaparicion',0)} | "
          f"Cambio precio {cnt.get('cambio_precio',0)} | Agotados {len(ausentes)}")

    # 3) Excel (identico al escaner de tokens) -> Storage
    nombre = f"Escaneo_PRO_{prov}_{marca}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    out = os.path.join(tmp, nombre)
    info = escribir_excel(res, out)
    ruta_storage = f'{CARPETA_RESULTADOS}/{nombre}'
    subido_ok = False
    try:
        with open(out, 'rb') as fp:
            sb.storage.from_(BUCKET).upload(ruta_storage, fp.read(),
                {'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 'upsert': 'true'})
        _r = sb.storage.from_(BUCKET).list(CARPETA_RESULTADOS) or []
        subido_ok = any(o.get('name') == nombre for o in _r)
        print(f"Excel subido: {ruta_storage} | verificado: {subido_ok}")
    except Exception as ex:
        print('ATENCION: no se pudo subir el Excel:', ex)

    # 4) Registrar en la Biblioteca
    n_comprar = sum(1 for it in res['registros'] for d in it['paises'].values() if d.get('decision') == 'COMPRAR')
    try:
        sb.table('escaner_resultados').insert({
            'proveedor': prov, 'marca': marca, 'modo': 'pro', 'rank_maximo': rank_max,
            'n_productos': len(res['registros']), 'n_comprar': n_comprar,
            'n_nuevos': cnt.get('nuevo', 0), 'n_reaparecidos': cnt.get('reaparicion', 0),
            'n_cambios': cnt.get('cambio_precio', 0), 'n_agotados': len(ausentes),
            'fichero': ruta_storage if subido_ok else None, 'tokens_restantes': None}).execute()
        print("Registrado en la Biblioteca (escaner_resultados).")
    except Exception as ex:
        print('AVISO: no se pudo registrar en la Biblioteca (el Excel SI esta en Storage):', ex)

    # 5) Memoria del proveedor (decision de Fernando: SI guardar). Mismo seguro que el escaner:
    #    agotados SOLO si el catalogo de hoy trajo productos (evita falso vaciado).
    ahora = datetime.now(timezone.utc).isoformat()
    regs = []; vistos = set()
    for f in filas:
        k = (prov, norm(f['core']), bool(f['es_chase']))
        if k in vistos: continue
        vistos.add(k)
        regs.append({'proveedor': prov, 'ean': f['core'], 'es_case': bool(f['es_chase']), 'marca': marca,
                     'pa': float(f['pa']) if f['pa'] is not None else None, 'presente': True, 'fecha': ahora})
    if filas:
        for (ean_norm, es_case), inf in ausentes:
            k = (prov, ean_norm, es_case)
            if k in vistos: continue
            vistos.add(k)
            pa_ant = inf.get('pa')
            regs.append({'proveedor': prov, 'ean': inf['ean_db'], 'es_case': es_case, 'marca': marca,
                         'pa': float(pa_ant) if pa_ant is not None else None, 'presente': False, 'fecha': ahora})
    else:
        print("Catalogo vacio: NO se marcan agotados (evita falso vaciado de la memoria).")
    n_ok = 0
    for i in range(0, len(regs), 500):
        try:
            sb.table('escaner_memoria').upsert(regs[i:i+500], on_conflict='proveedor,ean,es_case').execute()
            n_ok += len(regs[i:i+500])
        except Exception as ex:
            print(f'  AVISO lote memoria {i//500+1}: {ex}')
    print(f"Memoria actualizada: {n_ok}/{len(regs)} [{prov}/{marca}]")

    # 6) Limpiar el buzon SOLO si el Excel se subio bien (si no, se deja para reintentar)
    if subido_ok:
        try:
            objs = sb.storage.from_(BUCKET).list(BUZON) or []
            borrar = [f'{BUZON}/{o["name"]}' for o in objs if not o['name'].startswith('.')]
            if borrar: sb.storage.from_(BUCKET).remove(borrar)
            print(f"Buzon limpiado: {len(borrar)} ficheros.")
        except Exception as ex:
            print('AVISO: no se pudo limpiar el buzon:', ex)

    print(f"PRO OK | productos {len(res['registros'])} | COMPRAR {n_comprar} | "
          f"lote {info['lote_filas']} | Excel {ruta_storage if subido_ok else 'NO SUBIDO'}")

if __name__ == '__main__':
    main()
