#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL CRUCE DE HEO (pasos 4, 5 y 6 del encargo B, 24-sep-2026) — EN SOMBRA.

Lo lanza la v2 al subir los CSV del Visualizador (workflow escaner2-heo-cruce.yml, input
`pasada`). Cero tokens de Keepa: todo sale de los CSV.

QUE HACE, EN ORDEN:
  1. abre un cruce en `escaner2_cruce` para esa pasada, con una FOTO de los parametros
     (umbral de caidas y paises de `escaner2_parametros`): el cruce se puede rehacer igual;
  2. baja los CSV de `escaner2/heo/<pasada>/csv/`, y de cada uno deduce el PAIS del propio
     dato (columna `Localización`, o la URL de Amazon); los lee con el lector del Escaner Pro
     (`leer_csv_visualizador`) y le anade las caidas de 30 dias, que ese lector no trae;
  3. lee la foto de la pasada y `productos` (SOLO LECTURA: el IVA de la ficha, como el viejo);
  4. decide la PUERTA de cada EAN (escaner2_motor.decidir) con `calc_rentabilidad` del viejo;
  5. guarda cada EAN con su puerta y cada pais con su cuenta, y CUADRA CONTRA LA BASE:
     entradas (filas de la foto) = suma de puertas. Si no cuadra, el cruce queda 'fallida';
  6. compara con el escaner viejo (ultimo Excel completo de HEO + novedades posteriores) y
     deja un Excel con todo en `escaner2/heo/<pasada>/<cruce>/`.

🔒 NO TOCA NADA DEL ESCANER VIEJO: `productos`, `escaner_resultados` y los Excel de
   `informes/resultados/` se LEEN; no se escribe en ninguna tabla ni carpeta que ya existiera.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: lee `productos` desatendido (ver
   test_escaner_llave_servicio.py, donde este programa esta en la lista PROGRAMAS).
"""
import gzip
import io
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"ESCANER2_NO_EJECUTADO: {motivo}")
    sys.exit(1)


_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
PASADA = (os.environ.get('PASADA') or '').strip().lower()
if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', PASADA):
    abortar(f'la pasada no es un id válido: {PASADA!r}')

from supabase import create_client  # noqa: E402

import escaner2_motor as e2  # noqa: E402
import moloka_escaner_pro as pro  # noqa: E402
from foto_comun import descargar_buzon, listar_buzon  # noqa: E402

BUCKET = 'escaner2'
BUCKET_VIEJO = 'informes'
LOTE = 500
RUN_ID = os.environ.get('GITHUB_RUN_ID')

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


class Fallo(Exception):
    """Algo que impide cruzar: el cruce queda 'fallida' con este motivo, en la base y en pantalla."""


def _ahora():
    return datetime.now(timezone.utc)


def _entero(x):
    return None if x is None else int(round(x))


def _en_lotes(tabla, filas):
    for i in range(0, len(filas), LOTE):
        sb.table(tabla).insert(filas[i:i + LOTE]).execute()


def _contar(tabla, **filtros):
    q = sb.table(tabla).select('id', count='exact')
    for k, v in filtros.items():
        q = q.eq(k, v)
    return q.limit(1).execute().count


def _todas(tabla, columnas, orden, **filtros):
    """Todas las filas, paginando de 1.000 en 1.000 (el tope por defecto de la API)."""
    salida, desde = [], 0
    while True:
        q = sb.table(tabla).select(columnas)
        for k, v in filtros.items():
            q = q.eq(k, v)
        pagina = q.order(orden).range(desde, desde + 999).execute().data or []
        salida.extend(pagina)
        if len(pagina) < 1000:
            return salida
        desde += 1000


def main():
    res = sb.table('escaner2_pasada').select('*').eq('id', PASADA).limit(1).execute()
    pasada = (res.data or [None])[0]
    if not pasada:
        abortar(f'no existe la pasada {PASADA}')
    if pasada.get('estado') != 'esperando_csv':
        abortar(f"la pasada {PASADA} está en '{pasada.get('estado')}', no en 'esperando_csv'")
    res = sb.table('escaner2_parametros').select('*').eq('proveedor', e2.PROVEEDOR).limit(1).execute()
    par = (res.data or [None])[0]
    if not par:
        abortar('no hay fila HEO en escaner2_parametros (umbral y países)')
    params = {'umbral': int(par['umbral_caidas_30d']), 'paises': list(par['paises'])}

    cruce = str(uuid.uuid4())
    sb.table('escaner2_cruce').insert({
        'id': cruce, 'pasada_id': PASADA, 'estado': 'cruzando',
        'umbral_caidas_30d': params['umbral'], 'paises': params['paises'],
        'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None,
    }).execute()
    print(f">>> Cruce {cruce} de la pasada {PASADA} abierto · umbral > {params['umbral']} caídas "
          f"en {' o '.join(params['paises'])}.", flush=True)
    try:
        cierre, rojo = cruzar(cruce, params)
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, Fallo) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_cruce').update({'estado': 'fallida', 'motivo_fallo': motivo[:2000],
                                           'terminado_en': _ahora().isoformat()}).eq('id', cruce).execute()
        abortar(f'cruce {cruce} fallido: {motivo}')
    sb.table('escaner2_cruce').update(cierre).eq('id', cruce).execute()
    if cierre['estado'] != 'lista':
        abortar(f"cruce {cruce} fallido: {cierre.get('motivo_fallo')}")
    print(f">>> CRUCE LISTO · entradas {cierre['n_entradas']} = "
          + ' + '.join(f"{p}:{cierre['n_' + p]}" for p in e2.PUERTAS), flush=True)
    if rojo:
        # Lo guardado vale; lo que falto (la comparacion) se ve en pantalla y el run sale ROJO.
        abortar('cruce guardado, pero con aviso: ' + cierre['aviso'])


def cruzar(cruce, params):
    M = e2.cargar_motor()
    col_pais, col_caidas = e2.columnas_keepa()
    avisos, rojo = [], False

    # ── 1 · Los CSV subidos, y el pais de cada uno (del dato) ───────────────────────────
    carpeta = f'heo/{PASADA}/csv'
    objetos = [o for o in listar_buzon(sb, BUCKET, carpeta)
               if (o.get('name') or '').lower().endswith(('.csv', '.csv.gz'))]
    if not objetos:
        raise Fallo('no hay ningún CSV subido para esta pasada')
    tmp = tempfile.mkdtemp(prefix='escaner2_')
    ficheros, errores, rutas_por_pais, caidas_por_pais, fecha_datos = [], [], {}, {}, None
    for o in sorted(objetos, key=lambda x: x['name']):
        datos = descargar_buzon(sb, BUCKET, f"{carpeta}/{o['name']}")
        if datos[:2] == b'\x1f\x8b':
            datos = gzip.decompress(datos)
        ruta = os.path.join(tmp, re.sub(r'[^A-Za-z0-9._-]+', '_', o['name']))
        with open(ruta, 'wb') as fh:
            fh.write(datos)
        subido = o.get('created_at') or o.get('updated_at')
        try:
            ex = e2.examinar_csv(ruta, pro, col_pais, col_caidas)
        except e2.CsvIlegible as err:
            errores.append(f"{o['name']}: {err}")
            ficheros.append({'nombre': o['name'], 'pais': None, 'filas': None, 'usado': False,
                             'error': str(err), 'subido': subido})
            continue
        usado = ex['pais'] in params['paises']
        ficheros.append({'nombre': o['name'], 'pais': ex['pais'], 'filas': ex['filas'], 'usado': usado,
                         'fuente_pais': ex['fuente_pais'], 'choques_caidas': ex['choques_caidas'],
                         'error': None, 'subido': subido})
        print(f"    CSV {o['name']}: {ex['pais']} ({ex['fuente_pais']}), {ex['filas']} filas"
              + ('' if usado else ' → IGNORADO: el barrido solo mira ' + ', '.join(params['paises'])),
              flush=True)
        if not usado:
            avisos.append(f"CSV de {ex['pais']} ignorado ({o['name']})")
            continue
        rutas_por_pais.setdefault(ex['pais'], []).append(ruta)
        for asin, v in ex['caidas'].items():
            caidas_por_pais.setdefault(ex['pais'], {}).setdefault(asin, v)
        if subido and (fecha_datos is None or subido > fecha_datos):
            fecha_datos = subido
    if errores:
        raise Fallo('CSV que no se pueden usar → ' + ' | '.join(errores))
    usados = [p for p in params['paises'] if p in rutas_por_pais]
    if not usados:
        raise Fallo('ningún CSV es de %s' % ' ni de '.join(params['paises']))
    for p in params['paises']:
        if p not in usados:
            avisos.append(f'Falta el CSV de {p}: se decide solo con {", ".join(usados)}')
    datos_por_pais = {p: pro.leer_csv_visualizador(rutas_por_pais[p]) for p in usados}

    # ── 2 · La foto y el catalogo propio (el IVA de la ficha) ──────────────────────────
    foto = _todas('escaner2_foto', 'id,ean_original,ean_core,variantes,nombre,marca,precio_unidad,'
                  'es_caja,uds_caja', 'id', pasada_id=PASADA)
    if not foto:
        raise Fallo('la pasada no tiene foto')
    productos = _todas('productos', 'ean,asin,iva_pct,stock_moloka,stock_fba', 'id', activo=True)
    con_iva = sum(1 for p in productos if p.get('iva_pct') not in (None, ''))
    print(f"CATALOGO_PROPIO: filas={len(productos)} | con_iva={con_iva}", flush=True)
    if not productos:
        # 0 filas no es «no tengo fichas»: es «no he podido leerlas» (10-sep-2026). Sin ellas
        # todo el IVA de ES saldria asumido y nadie lo notaria.
        raise Fallo('productos devolvió 0 filas con activo=true: el IVA de la ficha no se puede leer')
    M.poner_catalogo_propio(productos)

    # ── 3 · Las puertas ───────────────────────────────────────────────────────────────
    resultados = []
    for f in foto:
        cands = {p: e2.candidatos(f, datos_por_pais[p]) for p in usados}
        r = e2.decidir(f, cands, caidas_por_pais, params, M)
        r['foto_id'], r['id'] = f['id'], str(uuid.uuid4())
        resultados.append(r)
    cq = e2.cuadre([f['id'] for f in foto], resultados)

    filas_ean, filas_pais = [], []
    for r in resultados:
        mejor = r.get('mejor') or {}
        filas_ean.append({
            'id': r['id'], 'cruce_id': cruce, 'foto_id': r['foto_id'], 'puerta': r['puerta'],
            'motivo': r['motivo'], 'detalle': r['detalle'], 'asin': r['asin'],
            'mejor_pais': mejor.get('pais'), 'mejor_margen': mejor.get('margen'),
            'mejor_beneficio': mejor.get('beneficio'), 'mejor_precio_venta': mejor.get('precio_venta'),
            'fichas': [dict(fi, rank=_entero(fi['rank']), rank_90d=_entero(fi['rank_90d']),
                            caidas_30d=_entero(fi['caidas_30d'])) for fi in r['fichas']] if r['fichas'] else None,
        })
        for p, c in (r.get('paises') or {}).items():
            filas_pais.append({
                'cruce_id': cruce, 'resultado_ean_id': r['id'], 'foto_id': r['foto_id'], 'pais': p,
                'asin': c['asin'], 'titulo': c['titulo'] or None, 'caidas_30d': _entero(c.get('caidas_30d')),
                'rank': _entero(c['rank']), 'rank_90d': _entero(c['rank_90d']),
                'precio_venta': c['precio_venta'], 'canal': c['canal'], 'ref_pct': c['ref_pct'],
                'fee_fba': c['fee_fba'], 'iva': c['iva'], 'iva_origen': c['iva_origen'],
                'almacen': c['almacen'], 'com_digitales': c['com_digitales'], 'isd_pct': c['isd_pct'],
                'isd_incluye_fba': c['isd_incluye_fba'], 'pa': c['pa'], 'com_amazon': c['com_amazon'],
                'beneficio': c['beneficio'], 'roi': c['roi'], 'margen': c['margen'],
                'decision': c['decision'],
            })
    _en_lotes('escaner2_resultado_ean', filas_ean)
    _en_lotes('escaner2_resultado_pais', filas_pais)

    # ── 4 · EL CUADRE, CONTANDO EN LA BASE ─────────────────────────────────────────────
    n_entradas = _contar('escaner2_foto', pasada_id=PASADA)
    n_bd = {p: _contar('escaner2_resultado_ean', cruce_id=cruce, puerta=p) for p in e2.PUERTAS}
    n_c_pocas = _contar('escaner2_resultado_ean', cruce_id=cruce, motivo='c_pocas_caidas')
    n_c_sin = _contar('escaner2_resultado_ean', cruce_id=cruce, motivo='c_sin_dato')
    suma = sum(n_bd.values())
    cuadra = (n_entradas == suma)
    print(f"CUADRE puertas [HEO]: entradas={n_entradas} | suma de puertas={suma} ("
          + ' '.join(f'{p}={n_bd[p]}' for p in e2.PUERTAS) + f") | en memoria {cq['suma']} de "
          f"{cq['n_entradas']} → {'CUADRA' if (cuadra and cq['cuadra']) else 'NO CUADRA'}", flush=True)
    motivo_fallo = None
    if not cq['cuadra']:
        motivo_fallo = ('NO CUADRA en el cálculo: faltan %d, sobran %d, repetidos %d, puertas raras %s'
                        % (len(cq['faltan']), len(cq['sobran']), len(cq['repetidos']), cq['puerta_rara']))
    elif not cuadra:
        motivo_fallo = f'NO CUADRA en la base: {n_entradas} entradas y {suma} en las puertas'
    elif n_bd != cq['conteo']:
        motivo_fallo = f'la base no guarda lo calculado: {n_bd} frente a {cq["conteo"]}'

    # ── 5 · La comparacion con el viejo (si falla, se avisa y el run sale rojo al final) ─
    cmp_filas, cmp_resumen, viejos_meta, rank_max = [], {}, [], None
    try:
        cmp_filas, cmp_resumen, viejos_meta, rank_max = comparar_con_el_viejo(
            M, foto, resultados, params, fecha_datos)
        _en_lotes('escaner2_comparacion', [dict(c, cruce_id=cruce, fecha_viejo=_iso(c['fecha_viejo']),
                                                fecha_nuevo=_iso(c['fecha_nuevo'])) for c in cmp_filas])
    except Exception as ex:
        rojo = True
        avisos.append(f'Comparación con el viejo no disponible: {type(ex).__name__}: {ex}')
        print('!!! ' + avisos[-1], flush=True)

    # ── 6 · El Excel ───────────────────────────────────────────────────────────────────
    ruta_excel = None
    try:
        sello = _ahora().astimezone(_zona_madrid()).strftime('%Y%m%d_%H%M')
        ruta_excel = f'heo/{PASADA}/{cruce}/Escaner2_HEO_{sello}.xlsx'
        contenido = escribir_excel(foto, resultados, cmp_filas, {
            'pasada': PASADA, 'cruce': cruce, 'params': params, 'usados': usados, 'ficheros': ficheros,
            'n_entradas': n_entradas, 'n_bd': n_bd, 'cuadra': cuadra and not motivo_fallo,
            'resumen': cmp_resumen, 'viejos': viejos_meta, 'avisos': avisos})
        sb.storage.from_(BUCKET).upload(ruta_excel, contenido, {
            'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'upsert': 'true'})
    except Exception as ex:
        rojo, ruta_excel = True, None
        avisos.append(f'No se pudo dejar el Excel: {type(ex).__name__}: {ex}')
        print('!!! ' + avisos[-1], flush=True)

    cierre = {
        'estado': 'lista' if (cuadra and not motivo_fallo) else 'fallida',
        'motivo_fallo': motivo_fallo, 'terminado_en': _ahora().isoformat(),
        'ficheros': ficheros, 'paises_usados': usados, 'fecha_datos': fecha_datos,
        'n_entradas': n_entradas, 'n_c_pocas': n_c_pocas, 'n_c_sin_dato': n_c_sin,
        'cuadra': cuadra, 'viejo_excels': viejos_meta, 'rank_max_viejo': rank_max,
        'ruta_excel': ruta_excel, 'aviso': ' · '.join(avisos) or None,
    }
    for p in e2.PUERTAS:
        cierre['n_' + p] = n_bd[p]
    cierre.update(cmp_resumen)
    return cierre, rojo


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def _zona_madrid():
    from zoneinfo import ZoneInfo
    return ZoneInfo('Europe/Madrid')


def comparar_con_el_viejo(M, foto, resultados, params, fecha_datos):
    """El paso 6. Lee (SOLO LECTURA) las filas de HEO de `escaner_resultados` y sus Excel de
    `informes/resultados/`: el ultimo completo y las novedades posteriores."""
    filas = (sb.table('escaner_resultados').select('id,fecha,modo,fichero,rank_maximo')
             .eq('proveedor', e2.PROVEEDOR).order('fecha', desc=True).limit(300).execute().data) or []
    elegidas, hay_completo = e2.elegir_excels_viejos(filas)
    if not elegidas:
        raise RuntimeError('no hay ningún Excel del escáner viejo de HEO en la biblioteca')
    excels, meta = [], []
    for f in elegidas:
        fecha = e2.fecha_del_excel_viejo(f['fichero']) or datetime.fromisoformat(
            str(f['fecha']).replace('Z', '+00:00'))
        datos = e2.leer_excel_viejo(descargar_buzon(sb, BUCKET_VIEJO, f['fichero']), M)
        m = {'fichero': f['fichero'], 'fecha': fecha, 'modo': f.get('modo'), 'eans': len(datos)}
        excels.append((m, datos))
        meta.append(dict(m, fecha=fecha.isoformat()))
    base = [f for f in elegidas if (f.get('modo') or '').lower() == 'todo']
    rank_max = int((base[0] if base else elegidas[-1]).get('rank_maximo') or 30000)
    viejo = e2.fusionar_viejos(excels)
    apartados = {}
    for a in _todas('escaner2_apartado', 'ean_original,motivo,detalle', 'id', pasada_id=PASADA):
        k = M.norm(M.core_ean(a['ean_original'] or ''))
        if k:
            apartados.setdefault(k, 'apartado antes de la foto: ' + (a['detalle'] or a['motivo']))
    nuevo = e2.nuevo_por_ean(foto, {r['foto_id']: r for r in resultados}, M)
    fecha_nuevo = datetime.fromisoformat(str(fecha_datos).replace('Z', '+00:00')) if fecha_datos else _ahora()
    cmp = e2.comparar(viejo, nuevo, {'umbral': params['umbral'], 'paises': params['paises'],
                                      'rank_max': rank_max, 'apartados': apartados,
                                      'fecha_nuevo': fecha_nuevo}, M)
    if not hay_completo:
        print('AVISO: en las 300 filas de HEO de la biblioteca no hay ningún escaneo completo; '
              'se compara con las novedades que hay.', flush=True)
    resumen = e2.resumen_comparacion(cmp)
    print('COMPARACION con el viejo: ' + ' | '.join(f'{k[6:]}={v}' for k, v in resumen.items())
          + f" · Excel viejos: {', '.join(m['fichero'].split('/')[-1] for m in meta)}", flush=True)
    return cmp, resumen, meta, rank_max


def escribir_excel(foto, resultados, cmp_filas, info):
    """El Excel del cruce: Resumen, COMPRAR y VALORAR, Comparación, Varias fichas y Puertas.
    Solo lo que ya esta calculado y guardado: aqui no se decide nada."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    por_foto = {f['id']: f for f in foto}
    wb = Workbook()

    def hoja(nombre, cabecera, filas, anchos=None):
        ws = wb.create_sheet(nombre) if wb.worksheets[0].title != 'Sheet' else wb.worksheets[0]
        ws.title = nombre
        ws.append(cabecera)
        for c in ws[1]:
            c.font = Font(bold=True)
        for fila in filas:
            ws.append(fila)
        for letra, ancho in (anchos or {}).items():
            ws.column_dimensions[letra].width = ancho
        ws.freeze_panes = 'A2'
        return ws

    r = info['resumen'] or {}
    filas_res = [['Pasada', info['pasada']], ['Cruce', info['cruce']],
                 ['Umbral de caídas (30 días)', '> %d' % info['params']['umbral']],
                 ['Países configurados', ', '.join(info['params']['paises'])],
                 ['Países con CSV', ', '.join(info['usados'])],
                 ['Entradas (filas de la foto)', info['n_entradas']]]
    filas_res += [['Puerta %s · %s' % (p, e2.NOMBRE_PUERTA[p]), info['n_bd'][p]] for p in e2.PUERTAS]
    filas_res += [['Suma de puertas', sum(info['n_bd'].values())], ['Cuadra', 'SÍ' if info['cuadra'] else 'NO']]
    filas_res += [['Comparación · COMPRAR/VALORAR en los dos', r.get('n_cmp_ambos')],
                  ['Comparación · solo en el viejo', r.get('n_cmp_solo_viejo')],
                  ['Comparación · solo en el nuevo', r.get('n_cmp_solo_nuevo')],
                  ['Comparación · diferencia de criterio', r.get('n_cmp_criterio')],
                  ['Comparación · sin explicar', r.get('n_cmp_sin_explicar')]]
    filas_res += [['Excel viejo', '%s (%s, %s)' % (m['fichero'], m.get('modo'), m['fecha'])] for m in info['viejos']]
    filas_res += [['CSV', '%s · %s · %s filas%s' % (f['nombre'], f.get('pais') or '¿?', f.get('filas') or 0,
                                                     '' if f.get('usado') else ' · NO USADO')] for f in info['ficheros']]
    filas_res += [['Aviso', a] for a in info['avisos']]
    hoja('Resumen', ['Qué', 'Valor'], filas_res, {'A': 44, 'B': 90})

    compras = []
    for res in resultados:
        if res['puerta'] not in ('e', 'f'):
            continue
        f, m = por_foto[res['foto_id']], res['mejor']
        caidas = res.get('caidas') or {}
        compras.append([f['ean_original'], f['nombre'], f['marca'], e2.NOMBRE_PUERTA[res['puerta']],
                        m['pais'], round(m['margen'], 4), round(m['beneficio'], 2), m['precio_venta'],
                        round(f['precio_unidad'], 2) if f['precio_unidad'] is not None else None,
                        caidas.get('ES'), caidas.get('DE'), res['asin'],
                        (res['paises'].get(m['pais']) or {}).get('iva_origen')])
    compras.sort(key=lambda x: (x[3] != 'COMPRAR', -(x[5] or 0)))
    ws = hoja('COMPRAR y VALORAR', ['EAN', 'Nombre', 'Marca', 'Decisión', 'Mejor país', 'Margen',
                                    'Beneficio (€)', 'Precio venta (€)', 'Precio compra (€)',
                                    'Caídas 30 d ES', 'Caídas 30 d DE', 'ASIN', 'Origen IVA'],
              compras, {'A': 15, 'B': 55, 'C': 16, 'L': 12, 'M': 14})
    for fila in ws.iter_rows(min_row=2, min_col=6, max_col=6):
        for c in fila:
            c.number_format = '0.0%'

    hoja('Comparación', ['EAN', 'Nombre', 'Categoría', 'Viejo', 'País viejo', 'Fecha viejo (UTC)',
                         'Excel viejo', 'Puerta nuevo', 'Nuevo', 'País nuevo', 'Fecha nuevo (UTC)',
                         'Diferencia de criterio', 'Explicación'],
         [[c['ean'], c['nombre'], {'ambos': 'En los dos', 'solo_viejo': 'Solo en el viejo',
                                   'solo_nuevo': 'Solo en el nuevo'}[c['categoria']],
           c['decision_viejo'], c['pais_viejo'], _iso(c['fecha_viejo']),
           (c['excel_viejo'] or '').split('/')[-1] or None, c['puerta_nuevo'], c['decision_nuevo'],
           c['pais_nuevo'], _iso(c['fecha_nuevo']), 'SÍ' if c['diferencia_criterio'] else 'no',
           c['explicacion']] for c in cmp_filas],
         {'A': 15, 'B': 50, 'C': 16, 'G': 36, 'M': 110})

    varias = []
    for res in resultados:
        if res['puerta'] == 'b':
            f = por_foto[res['foto_id']]
            for fi in res['fichas']:
                varias.append([f['ean_original'], f['nombre'], fi['pais'], fi['asin'], fi['titulo'],
                               fi['rank'], fi['caidas_30d'], fi['precio_venta']])
    hoja('Varias fichas', ['EAN', 'Nombre HEO', 'País', 'ASIN', 'Título Amazon', 'Puesto',
                           'Caídas 30 d', 'Precio venta (€)'], varias, {'A': 15, 'B': 50, 'E': 60})

    hoja('Puertas', ['EAN', 'Nombre', 'Marca', 'Precio compra (€)', 'Caja', 'Puerta', 'Motivo', 'Detalle'],
         [[por_foto[res['foto_id']]['ean_original'], por_foto[res['foto_id']]['nombre'],
           por_foto[res['foto_id']]['marca'], por_foto[res['foto_id']]['precio_unidad'],
           'caja x%s' % por_foto[res['foto_id']]['uds_caja'] if por_foto[res['foto_id']]['es_caja'] else '',
           '%s · %s' % (res['puerta'], e2.NOMBRE_PUERTA[res['puerta']]), res['motivo'], res['detalle']]
          for res in resultados],
         {'A': 15, 'B': 55, 'C': 16, 'F': 24, 'G': 16, 'H': 70})
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


if __name__ == '__main__':
    main()
