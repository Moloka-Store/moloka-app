#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL CRUCE DEL ESCANEO PRO DE OCIOSTOCK (encargo OC3, 07-oct-2026).

Lo lanza la v2 cuando el buzon de Keepa de la tarjeta OcioStock tiene los CUATRO CSV (ES, IT, FR, DE: Fernando,
28-sep-2026, «el cruce arranca solo al estar los 4 CSV») por el workflow escaner2-ociostock-cruce.yml, input `pasada`.
Cero tokens de Keepa: todo sale de los CSV.

QUE HACE, EN ORDEN (el cruce del PRO de HEO, escaner2_heo_cruce.py, sin la comparacion con el viejo):
  1. abre un cruce en `escaner2_cruce` con la FOTO de los parametros de OCIOSTOCK (`escaner2_parametros`: umbral 6 y
     ES·IT·FR·DE en el filtro y en el calculo): la recomendacion sale de los cuatro, se venda o no en cada uno;
  2. baja los CSV de `escaner2/ociostock/<pasada>/csv/` y de cada uno saca el PAIS del dato (como HEO);
  3. lee la foto de la pasada, su `barrido.json` (las unidades del escalon y el precio de la ficha de cada fila) y
     `productos` (SOLO LECTURA: el IVA de la ficha, como el viejo);
  4. decide la PUERTA de cada EAN con `escaner2_motor.decidir`, SIN TOCAR formula ni umbrales: el PA es el
     `precio_unidad` de la foto de la pasada, que el barrido pone al `precio_pa` de OcioStock (escalon × 0,99);
  5. guarda cada EAN con su puerta y cada pais con su cuenta, y CUADRA CONTRA LA BASE (entradas = suma de puertas, y
     fichero = previas + puertas). Si no cuadra, el cruce queda 'fallida';
  6. deja el Excel en `escaner2/ociostock/<pasada>/<cruce>/Escaner2_OCIOSTOCK_<sello>.xlsx`: el del PRO de HEO, con
     «Uds. escalón» y «Precio unidad» al final de «Análisis». La biblioteca de escaneos de la v2 lo enseña.

🔴 REPO PUBLICO: LOS REGISTROS LOS VE CUALQUIERA. Solo estados, recuentos y el nombre de los CSV que sube Fernando;
   NUNCA precios, EAN, ASIN, nombres de producto ni el texto de un error (va a `escaner2_cruce.motivo_fallo`).
🔒 SOLO ESCRIBE `escaner2_cruce`, `escaner2_resultado_ean`, `escaner2_resultado_pais` y el Excel de su carpeta.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: lee `productos` desatendido (test_escaner_llave_servicio.py, PROGRAMAS).
"""
import gzip
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone


def abortar(motivo):
    print(f"ESCANER2_NO_EJECUTADO: {motivo}")
    sys.exit(1)


_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
PASADA = (os.environ.get('PASADA') or '').strip().lower()
if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', PASADA):
    abortar('la pasada no es un id válido')

from supabase import create_client  # noqa: E402

import escaner2_motor as e2  # noqa: E402
import escaner2_ociostock_pro as eoc  # noqa: E402
import en_mi_bd  # noqa: E402
import escaner2_heredado_pro as pro  # noqa: E402
from foto_comun import descargar_buzon, listar_buzon  # noqa: E402

BUCKET = 'escaner2'
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
    pasada = (sb.table('escaner2_pasada').select('*').eq('id', PASADA).limit(1).execute().data or [None])[0]
    if not pasada:
        abortar(f'no existe la pasada {PASADA}')
    if pasada.get('proveedor') != eoc.PROVEEDOR:
        abortar(f'la pasada {PASADA} no es de OcioStock')
    if pasada.get('estado') != 'esperando_csv':
        abortar(f"la pasada {PASADA} está en '{pasada.get('estado')}', no en 'esperando_csv'")
    par = (sb.table('escaner2_parametros').select('*').eq('proveedor', eoc.PROVEEDOR).limit(1).execute().data
           or [None])[0]
    if not par:
        abortar('no hay fila OCIOSTOCK en escaner2_parametros (umbral y países)')
    # 🔑 DOS listas distintas (Fernando, 24-sep-2026): donde se mira si SE VENDE (filtro) y donde se CALCULA.
    params = {'umbral': int(par['umbral_caidas_30d']), 'paises_filtro': list(par['paises_filtro']),
              'paises_calculo': list(par['paises_calculo'])}
    cruce = str(uuid.uuid4())
    sb.table('escaner2_cruce').insert({
        'id': cruce, 'pasada_id': PASADA, 'estado': 'cruzando', 'umbral_caidas_30d': params['umbral'],
        'paises_filtro': params['paises_filtro'], 'paises_calculo': params['paises_calculo'],
        'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None}).execute()
    print(f">>> Cruce {cruce} de la pasada {PASADA} (OcioStock) abierto · se vende = "
          f"{e2.texto_corte(params['umbral'])} en {' o '.join(params['paises_filtro'])} · se calcula en los de "
          f"{', '.join(params['paises_calculo'])} que traigan CSV.", flush=True)
    try:
        cierre, rojo = cruzar(cruce, params, pasada)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza, el cruce queda 'fallida', no colgado en 'cruzando'.
        sb.table('escaner2_cruce').update(cierre).eq('id', cruce).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, (Fallo, eoc.FalloOcioStock)) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_cruce').update({'estado': 'fallida', 'motivo_fallo': motivo[:2000],
                                           'terminado_en': _ahora().isoformat()}).eq('id', cruce).execute()
        abortar(f'cruce {cruce} fallido ({type(ex).__name__}); el motivo está en escaner2_cruce.motivo_fallo')
    if cierre['estado'] != 'lista':
        abortar(f'cruce {cruce} fallido: no cuadra (el motivo está en escaner2_cruce.motivo_fallo)')
    print(f">>> CRUCE LISTO · fichero {cierre['n_crudo']} = previas {cierre['n_previas']} + entradas "
          f"{cierre['n_entradas']} = " + ' + '.join(f"{p}:{cierre['n_' + p]}" for p in e2.PUERTAS), flush=True)
    if rojo:
        abortar('cruce guardado, pero sin Excel (el aviso está en escaner2_cruce.aviso)')


def cruzar(cruce, params, pasada):
    M = e2.cargar_motor()
    faltan = [k for k in ['n_crudo'] + ['p_' + p for p in e2.PUERTAS_PREVIAS] if pasada.get(k) is None]
    if faltan:
        raise Fallo('la pasada no trae el recuento de: ' + ', '.join(faltan))
    n_crudo = int(pasada['n_crudo'])
    previas = {p: int(pasada['p_' + p]) for p in e2.PUERTAS_PREVIAS}
    n_previas = sum(previas.values())
    col_pais, col_caidas = e2.columnas_keepa()
    cols_ficha = e2.columnas_ficha_compartida()
    avisos, rojo = [], False

    # ── 0 · Lo que dejo el barrido: de que foto sale y el escalon de cada fila ─────────────────
    base = f'{eoc.CARPETA}/{PASADA}'
    try:
        barrido = json.loads(descargar_buzon(sb, BUCKET, f'{base}/barrido.json').decode('utf-8'))
    except Exception as ex:
        raise Fallo(f'no se puede leer {base}/barrido.json ({type(ex).__name__}): vuelve a barrer')
    escalon = barrido.get('escalon') or {}

    # ── 1 · Los CSV subidos, y el pais de cada uno (del dato) ───────────────────────────────
    carpeta = f'{base}/csv'
    objetos = [o for o in listar_buzon(sb, BUCKET, carpeta) if (o.get('name') or '').lower().endswith(('.csv', '.csv.gz'))]
    if not objetos:
        raise Fallo('no hay ningún CSV subido para esta pasada')
    tmp = tempfile.mkdtemp(prefix='escaner2_ociostock_')
    ficheros, errores, rutas, caidas_por_pais, fichas_por_pais, sin_ficha, fecha_datos = [], [], {}, {}, {}, {}, None
    # 🔑 EL MAS RECIENTE MANDA (el nombre empieza por el sello de la subida), como en HEO.
    for o in sorted(objetos, key=lambda x: x['name'], reverse=True):
        datos = descargar_buzon(sb, BUCKET, f"{carpeta}/{o['name']}")
        if datos[:2] == b'\x1f\x8b':
            datos = gzip.decompress(datos)
        ruta = os.path.join(tmp, re.sub(r'[^A-Za-z0-9._-]+', '_', o['name']))
        with open(ruta, 'wb') as fh:
            fh.write(datos)
        subido = o.get('created_at') or o.get('updated_at')
        try:
            ex = e2.examinar_csv(ruta, pro, col_pais, col_caidas, cols_ficha)
        except e2.CsvIlegible as err:
            errores.append(f"{o['name']}: {err}")
            ficheros.append({'nombre': o['name'], 'pais': None, 'filas': None, 'usado': False, 'error': str(err),
                             'subido': subido})
            continue
        usado = ex['pais'] in params['paises_calculo']
        ficheros.append({'nombre': o['name'], 'pais': ex['pais'], 'filas': ex['filas'], 'usado': usado,
                         'fuente_pais': ex['fuente_pais'], 'choques_caidas': ex['choques_caidas'], 'error': None,
                         'subido': subido})
        print(f"    CSV {o['name']}: {ex['pais']} · {ex['filas']} filas" + ('' if usado else ' → IGNORADO'), flush=True)
        if not usado:
            avisos.append(f"CSV de {ex['pais']} ignorado ({o['name']}): se calcula solo en "
                          f"{', '.join(params['paises_calculo'])}")
            continue
        rutas.setdefault(ex['pais'], []).append(ruta)
        for asin, v in ex['caidas'].items():
            caidas_por_pais.setdefault(ex['pais'], {}).setdefault(asin, v)
        for asin, v in ex['fichas'].items():
            fichas_por_pais.setdefault(ex['pais'], {}).setdefault(asin, v)
        if ex['sin_columnas_ficha']:
            sin_ficha.setdefault(ex['pais'], []).append('%s (le falta %s)' % (o['name'], ', '.join(ex['sin_columnas_ficha'])))
        # La fecha del dato es la del CSV MAS VIEJO que se usa.
        if subido and (fecha_datos is None or subido < fecha_datos):
            fecha_datos = subido
    usados = [p for p in params['paises_calculo'] if p in rutas]
    if not usados:
        raise Fallo('ningún CSV es de %s' % ' ni de '.join(params['paises_calculo'])
                    + ((' · CSV que no se pueden usar → ' + ' | '.join(errores)) if errores else ''))
    for p in params['paises_filtro']:
        if p not in usados:
            avisos.append(f'Falta el CSV de {p}: «se vende» se mira solo en '
                          f'{", ".join(x for x in params["paises_filtro"] if x in usados) or "ningún país"}')
    datos_por_pais = {p: pro.leer_csv_visualizador(rutas[p]) for p in usados}
    compartidas = e2.fichas_compartidas(fichas_por_pais)
    for p, fs in sin_ficha.items():
        avisos.append('Sin ASIN padre/variaciones/puesto en %s (%s): ahí no se detecta la ficha compartida'
                      % (p, '; '.join(fs)))
    n_compartidas = {p: len(compartidas.get(p) or {}) for p in usados}
    print('FICHAS COMPARTIDAS: ' + ' · '.join('%s %d' % (p, n_compartidas[p]) for p in usados), flush=True)

    # ── 2 · La foto y el catalogo propio (el IVA de la ficha y «En mi BD») ───────────────────
    foto = _todas('escaner2_foto', 'id,producto_heo,ean_original,ean_core,variantes,nombre,marca,precio_unidad,'
                  'precio_catalogo,es_caja,uds_caja,es_chase,en_oferta,origen_ean,aviso_ean,aviso_caja', 'id',
                  pasada_id=PASADA)
    if not foto:
        raise Fallo('la pasada no tiene foto')
    sin_escalon = sum(1 for f in foto if str(f.get('producto_heo') or '') not in escalon)
    if sin_escalon:
        avisos.append('%d filas de la foto sin su escalón en barrido.json: van sin «Uds. escalón» ni «Precio unidad»'
                      % sin_escalon)
    productos = _todas('productos', 'ean,asin,iva_pct,stock_moloka,es_chase', 'id', activo=True)
    print(f"CATALOGO_PROPIO: filas={len(productos)}", flush=True)
    if not productos:
        raise Fallo('productos devolvió 0 filas con activo=true: el IVA de la ficha no se puede leer')
    M.poner_catalogo_propio(productos)
    M.poner_foto_fba(en_mi_bd.leer_foto_fba(sb, imprimir=lambda linea: print(linea, flush=True)))

    # ── 3 · Las puertas, con las reglas del PRO de HEO ─────────────────────────────────────────
    apartados = _todas('escaner2_apartado', 'ean_original,nombre,marca,precio_catalogo,motivo,detalle,producto_heo',
                       'id', pasada_id=PASADA)
    # La eleccion de ficha del viejo mide sus palabras sobre el catalogo del escaneo (la foto + lo apartado por marca,
    # para que no dependa de las marcas elegidas). `e2.corpus_cotejo` es del perfil de HEO: este, el de OcioStock.
    corpus = eoc.corpus_cotejo(foto, apartados)
    eleccion = e2.cargar_eleccion_viejo(corpus)
    resultados = []
    for f in foto:
        cands = {p: e2.candidatos(f, datos_por_pais[p]) for p in usados}
        r = e2.decidir(f, cands, caidas_por_pais, params, M, eleccion, compartidas)
        r['foto_id'], r['id'] = f['id'], str(uuid.uuid4())
        resultados.append(r)
    cq = e2.cuadre([f['id'] for f in foto], resultados)

    filas_ean, filas_pais = [], []
    for r in resultados:
        mejor = r.get('mejor') or {}
        filas_ean.append({
            'id': r['id'], 'cruce_id': cruce, 'foto_id': r['foto_id'], 'puerta': r['puerta'], 'motivo': r['motivo'],
            'detalle': r['detalle'], 'asin': r['asin'], 'mejor_pais': mejor.get('pais'),
            'mejor_margen': mejor.get('margen'), 'mejor_beneficio': mejor.get('beneficio'),
            'mejor_precio_venta': mejor.get('precio_venta'),
            'fichas': [dict(fi, rank=_entero(fi['rank']), rank_90d=_entero(fi['rank_90d']),
                            caidas_30d=_entero(fi['caidas_30d'])) for fi in r['fichas']] if r['fichas'] else None,
        })
        for p, c in (r.get('paises') or {}).items():
            filas_pais.append({
                'cruce_id': cruce, 'resultado_ean_id': r['id'], 'foto_id': r['foto_id'], 'pais': p,
                'asin': c['asin'], 'titulo': c['titulo'] or None, 'caidas_30d': _entero(c.get('caidas_30d')),
                'rank': _entero(c['rank']), 'rank_90d': _entero(c['rank_90d']), 'precio_venta': c['precio_venta'],
                'canal': c['canal'], 'ref_pct': c['ref_pct'], 'fee_fba': c['fee_fba'], 'iva': c['iva'],
                'iva_origen': c['iva_origen'], 'almacen': c['almacen'], 'com_digitales': c['com_digitales'],
                'isd_pct': c['isd_pct'], 'isd_incluye_fba': c['isd_incluye_fba'], 'pa': c['pa'],
                'com_amazon': c['com_amazon'], 'beneficio': c['beneficio'], 'roi': c['roi'], 'margen': c['margen'],
                'decision': c['decision'], 'vende_aqui': c['vende_aqui'],
            })
    _en_lotes('escaner2_resultado_ean', filas_ean)
    _en_lotes('escaner2_resultado_pais', filas_pais)

    # ── 4 · EL CUADRE, CONTANDO EN LA BASE ─────────────────────────────────────────────────
    n_entradas = _contar('escaner2_foto', pasada_id=PASADA)
    n_bd = {p: _contar('escaner2_resultado_ean', cruce_id=cruce, puerta=p) for p in e2.PUERTAS}
    n_c_pocas = _contar('escaner2_resultado_ean', cruce_id=cruce, motivo='c_pocas_caidas')
    n_c_sin = _contar('escaner2_resultado_ean', cruce_id=cruce, motivo='c_sin_dato')
    suma = sum(n_bd.values())
    cuadra = (n_entradas == suma and n_crudo == n_previas + suma)
    listas_bd = {mo: _contar('escaner2_apartado', pasada_id=PASADA, motivo=mo) for mo in e2.MOTIVOS_APARTADO}
    print(f"CUADRE [OCIOSTOCK]: fichero={n_crudo} | previas={n_previas} | entradas={n_entradas} | suma de puertas="
          f"{suma} (" + ' '.join(f'{p}={n_bd[p]}' for p in e2.PUERTAS)
          + f") → {'CUADRA' if (cuadra and cq['cuadra']) else 'NO CUADRA'}", flush=True)
    motivo_fallo = None
    if not cq['cuadra']:
        motivo_fallo = ('NO CUADRA en el cálculo: faltan %d, sobran %d, repetidos %d, puertas raras %s'
                        % (len(cq['faltan']), len(cq['sobran']), len(cq['repetidos']), cq['puerta_rara']))
    elif n_entradas != suma:
        motivo_fallo = f'NO CUADRA en la base: {n_entradas} entradas y {suma} en las puertas'
    elif n_crudo != n_previas + suma:
        motivo_fallo = (f'NO CUADRA desde el fichero: {n_crudo} filas y {n_previas} en puertas previas + {suma} en '
                        f'las seis puertas = {n_previas + suma}')
    elif any(listas_bd[mo] != previas[mo] for mo in e2.MOTIVOS_APARTADO):
        motivo_fallo = f'las listas de las puertas previas no son su recuento: {listas_bd} frente a {previas}'
    elif n_bd != cq['conteo']:
        motivo_fallo = f'la base no guarda lo calculado: {n_bd} frente a {cq["conteo"]}'

    # ── 5 · El Excel ─────────────────────────────────────────────────────────────────────
    ruta = None
    try:
        from zoneinfo import ZoneInfo
        sello = _ahora().astimezone(ZoneInfo('Europe/Madrid')).strftime('%Y%m%d_%H%M')
        ruta = eoc.ruta_excel(PASADA, cruce, sello)
        contenido = eoc.escribir_excel(foto, resultados, apartados, M, {
            'pasada': PASADA, 'cruce': cruce, 'params': params, 'usados': usados, 'ficheros': ficheros,
            'n_entradas': n_entradas, 'n_bd': n_bd, 'cuadra': cuadra and not motivo_fallo, 'n_crudo': n_crudo,
            'previas': previas, 'modo': pasada.get('modo'), 'marcas': pasada.get('marcas'), 'eleccion': eleccion,
            'n_compartidas': n_compartidas, 'avisos': avisos, 'escalon': escalon,
            'foto': '%s · %s' % (barrido.get('disp_pasada') or '—', barrido.get('foto_en') or '—')})
        sb.storage.from_(BUCKET).upload(ruta, contenido, {
            'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'upsert': 'true'})
    except Exception as ex:
        rojo, ruta = True, None
        avisos.append(f'No se pudo dejar el Excel: {type(ex).__name__}: {ex}')
        print(f'!!! No se pudo dejar el Excel ({type(ex).__name__})', flush=True)

    cierre = {
        'estado': 'lista' if (cuadra and not motivo_fallo) else 'fallida',
        'motivo_fallo': motivo_fallo, 'terminado_en': _ahora().isoformat(), 'ficheros': ficheros,
        'paises_usados': usados, 'fecha_datos': fecha_datos, 'n_crudo': n_crudo, 'n_previas': n_previas,
        'n_entradas': n_entradas, 'n_c_pocas': n_c_pocas, 'n_c_sin_dato': n_c_sin, 'cuadra': cuadra,
        'viejo_excels': None, 'rank_max_viejo': None, 'ruta_excel': ruta, 'aviso': ' · '.join(avisos) or None,
    }
    for p in e2.PUERTAS:
        cierre['n_' + p] = n_bd[p]
    return cierre, rojo


if __name__ == '__main__':
    main()
