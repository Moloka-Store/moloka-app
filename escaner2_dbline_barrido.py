#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL BARRIDO DEL ESCANEO PRO DE DBLINE (encargo DB3, 09-oct-2026).

Lo lanzan los botones de la v2 (Escaneo PRO · tarjeta DBLine: «Barrer DBLine», «… · todas las marcas» y «… · marcas
elegidas») por el workflow escaner2-dbline-barrido.yml, con el input `modo` (marcas | todas | elegidas) y, en el modo
'elegidas', la lista de marcas (JSON). NO entra en la web de DBLine ni baja el fichero: trabaja sobre la FOTO DE
DISPONIBILIDAD que ya esta en la base (escaner2_dbline_disponibilidad.py, encargo DB2). Cero Keepa.

QUE HACE, EN ORDEN:
  1. abre una pasada en `escaner2_pasada` (proveedor DBLINE, su modo, estado 'descargando') con el id del run;
  2. lee la ULTIMA pasada APLICADA de DBLine en `disp_pasada` y sus filas en `disp_estado` (las vistas en ella,
     `ausencias = 0`): tienen que ser tantas como leyo (`n_leidas`), de esa pasada, y con las sin EAN dar el fichero
     (`n_crudo`), o no se sigue;
  3. modo 'marcas': las marcas de la fila DBLINE de `reglas_director` (SOLO LECTURA); 'todas' y 'elegidas', ni la lee;
  4. construye la foto con `escaner2_dbline_pro.construir_foto` (con unidades hoy, sin chase suelto, con precio de
     compra, la promo solo hasta su fin, un EAN con su codigo mas barato; crudo = previas + foto) y la guarda en
     `escaner2_foto`, y las listas de las puertas previas en `escaner2_apartado`, y lo CUENTA en la base;
  5. deja en el almacen cerrado `escaner2`: `dbline/<pasada>/eans.txt` (y, si pasa de una tanda, `eans_1.txt`…) para
     los CUATRO Visualizadores (ES, IT, FR, DE), y `barrido.json` (de que foto sale y las promos);
  6. cierra la pasada en 'esperando_csv' o en 'fallida' con el motivo.

🔴 REPO PUBLICO: LOS REGISTROS LOS VE CUALQUIERA. Solo se imprimen estados y recuentos: NUNCA precios, EAN, nombres,
   codigos de DBLine ni el texto de un error (va a `escaner2_pasada.motivo_fallo`: la base es privada).
🔒 SOLO ESCRIBE `escaner2_pasada`, `escaner2_foto`, `escaner2_apartado` y `escaner2/dbline/<pasada>/`. Ni disp_*, ni
   reglas_director, ni productos, ni escaner_memoria, ni nada del escaner viejo.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: sin ella aborta antes de crear ningun cliente.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar. `motivo` lo escribe este
    programa: nunca un precio, un EAN ni el texto de un error."""
    print(f"ESCANER2_NO_EJECUTADO: {motivo}")
    sys.exit(1)


_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
MODO = (os.environ.get('MODO_BARRIDO') or 'marcas').strip().lower()
if MODO not in ('marcas', 'todas', 'elegidas'):
    abortar(f'modo de barrido desconocido: {MODO!r} (marcas | todas | elegidas)')

import escaner2_motor as e2  # noqa: E402
import escaner2_dbline_pro as edb  # noqa: E402

# 🔴 La seleccion del modo 'elegidas' se valida AQUI, antes de abrir ningun cliente (la MISMA regla que HEO). El
#    selector de DBLine no tiene casilla de ofertas: tiene que llegar a 'false'.
ELEGIDAS = None
if MODO == 'elegidas':
    try:
        ELEGIDAS, _ofertas = e2.validar_seleccion(os.environ.get('MARCAS_ELEGIDAS'), os.environ.get('OFERTAS_ELEGIDAS'))
    except e2.SeleccionInvalida as ex:
        abortar(f'selección de marcas no válida: {ex}')
    if _ofertas:
        abortar('selección de marcas no válida: el selector de DBLine no tiene casilla de ofertas (tiene que ir a false)')
    if not ELEGIDAS:
        abortar('selección de marcas no válida: ni una marca')

from supabase import create_client  # noqa: E402

BUCKET = 'escaner2'
LOTE = 500
RUN_ID = os.environ.get('GITHUB_RUN_ID')

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


class Fallo(Exception):
    """La pasada queda 'fallida' con este motivo (privado, en la base) y los recuentos que se llegaron a hacer."""

    def __init__(self, motivo, recuentos=None):
        super().__init__(motivo)
        self.recuentos = recuentos or {}


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _hoy_madrid():
    """El dia del barrido en Madrid: el que decide si una promo sigue vigente («solo hasta su fin»)."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Madrid')).date()


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
    pasada = str(uuid.uuid4())
    abrir = {'id': pasada, 'proveedor': edb.PROVEEDOR, 'estado': 'descargando', 'modo': MODO,
             'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None}
    if MODO == 'elegidas':
        # La base no admite una pasada 'elegidas' sin su lista (check escaner2_pasada_elegidas_con_lista).
        abrir.update(marcas=ELEGIDAS, ofertas=False)
    sb.table('escaner2_pasada').insert(abrir).execute()
    print(f">>> Pasada {pasada} abierta (descargando) · DBLine · modo {MODO}.", flush=True)
    try:
        cierre, n_lista = barrer(pasada)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza (el check del cuadre), la pasada queda 'fallida'.
        sb.table('escaner2_pasada').update(cierre).eq('id', pasada).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, (Fallo, edb.FalloDBLine)) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo[:1000],
                                                 'terminada_en': _ahora()},
                                                **getattr(ex, 'recuentos', {}))).eq('id', pasada).execute()
        # Al log, solo el tipo: el motivo puede llevar precios o EAN y el repo es publico.
        abortar(f'pasada {pasada} fallida ({type(ex).__name__}); el motivo está en escaner2_pasada.motivo_fallo')
    print(f">>> PASADA LISTA: {cierre['n_foto']} en la foto · {n_lista} códigos para el Visualizador en "
          f"{cierre['n_tandas']} tanda(s). Esperando los CSV de Keepa de ES, IT, FR y DE.", flush=True)


def barrer(pasada):
    # ── 1 · La foto de la que sale la pasada: la ultima APLICADA ───────────────────────────────
    ult = (sb.table('disp_pasada').select('id,creada_en,terminada_en,n_leidas,n_crudo,n_sin_gtin,fichero_md5')
           .eq('proveedor', edb.PROVEEDOR).eq('estado', 'aplicada').order('creada_en', desc=True).limit(1)
           .execute().data or [None])[0]
    if not ult:
        raise Fallo('no hay ninguna pasada de DBLine aplicada en disp_pasada')
    filas = _todas('disp_estado', 'producto_prov,ean_original,ean_core,marca,nombre,categoria,precio_unidad,'
                   'precio_catalogo,en_oferta,fin_oferta,es_chase,disponible,regla,pasada_id,ausencias',
                   'producto_prov', proveedor=edb.PROVEEDOR, ausencias=0)
    ajenas = sum(1 for f in filas if f.get('pasada_id') != ult['id'])
    print(f">>> Foto de DBLine aplicada: leyó {ult.get('n_leidas')} · vistas en ella en disp_estado {len(filas)} · "
          f"de otra pasada {ajenas} · fichero {ult.get('n_crudo')} filas ({ult.get('n_sin_gtin')} sin EAN fuera)",
          flush=True)
    if ult.get('n_leidas') is None or len(filas) != int(ult['n_leidas']) or ajenas:
        raise Fallo('la foto de DBLine no es la de su última pasada aplicada (%s): leyó %s y disp_estado tiene %d '
                    'vistas en ella (%d de otra pasada)' % (ult['id'], ult.get('n_leidas'), len(filas), ajenas))
    if ult.get('n_crudo') is None or ult.get('n_sin_gtin') is None:
        raise Fallo('la pasada %s de disp_pasada no trae n_crudo o n_sin_gtin' % ult['id'])

    # ── 2 · El filtro de marca ──────────────────────────────────────────────────────────────
    marcas_director = None
    if MODO == 'marcas':
        regla = (sb.table('reglas_director').select('marcas').eq('proveedor', edb.PROVEEDOR).limit(1).execute().data
                 or [None])[0]
        if not regla:
            raise Fallo('no hay fila DBLINE en reglas_director: sin ella no se sabe qué marcas barrer')
        marcas_director = regla.get('marcas') or []
    quiere, info = edb.filtro_marca(MODO, marcas_director, ELEGIDAS)
    n_marcas = len(info['marcas_reales']) if info['marcas_reales'] is not None else None
    print(f">>> Modo {MODO}: " + (f"{n_marcas} marca(s)" if n_marcas is not None else 'todas las marcas, sin leer '
                                  'reglas_director'), flush=True)

    # ── 3 · La foto de la pasada y el cuadre desde el fichero ───────────────────────────────
    M = e2.cargar_motor()
    tanda = e2.tanda_visualizador()
    hoy = _hoy_madrid()
    foto, apartados, cuentas = edb.construir_foto(filas, quiere, M, int(ult['n_crudo']), int(ult['n_sin_gtin']), hoy,
                                                  MODO)
    previas = cuentas['previas']
    recuentos = dict({'n_crudo': int(ult['n_crudo'])}, **{'p_' + p: v for p, v in previas.items()})
    print(">>> CUADRE PREVIO [DBLINE]: fichero %d = " % int(ult['n_crudo'])
          + ' + '.join(f'{p} {previas[p]}' for p in e2.PUERTAS_PREVIAS)
          + f" + foto {cuentas['n_foto']} → {'CUADRA' if cuentas['cuadra_previo'] else 'NO CUADRA'}", flush=True)
    if not cuentas['cuadra_previo']:
        raise Fallo('NO CUADRA antes de la foto: ' + cuentas['motivo_previo'], recuentos)
    if not foto:
        raise Fallo('la foto sale vacía: nada de DBLine con unidades pasa el filtro del modo %s' % MODO, recuentos)
    print(f">>> En la foto: {len(foto)} EAN · con promo vigente {cuentas['n_en_oferta']} · promos caducadas desde la "
          f"foto (con el precio normal) {cuentas['n_promo_caducada']}", flush=True)

    filas_foto = []
    for f in foto:
        f['id'] = str(uuid.uuid4())
        filas_foto.append(dict({k: f[k] for k in (
            'producto_heo', 'ean_original', 'ean_core', 'variantes', 'codigos_keepa', 'nombre', 'marca', 'categoria',
            'precio_catalogo', 'precio_unidad', 'es_caja', 'uds_caja', 'es_chase', 'en_oferta', 'campana',
            'disponibilidad', 'fin_de_vida', 'preorder', 'imagen', 'aviso_caja', 'origen_ean', 'aviso_ean')},
            id=f['id'], pasada_id=pasada))
    _en_lotes('escaner2_foto', filas_foto)
    _en_lotes('escaner2_apartado', [dict(a, pasada_id=pasada) for a in apartados])
    # 🔴 LO QUE HAY EN LA BASE, NO LO QUE DICE EL CLIENTE: se cuenta despues de escribir.
    n_foto_bd = _contar('escaner2_foto', pasada_id=pasada)
    listas_bd = {mo: _contar('escaner2_apartado', pasada_id=pasada, motivo=mo) for mo in e2.MOTIVOS_APARTADO}
    print(f"CUADRE foto [DBLINE]: escritas {len(filas_foto)} | en la tabla {n_foto_bd} · listas de las puertas "
          f"previas en la tabla {listas_bd}", flush=True)
    if n_foto_bd != len(filas_foto):
        raise Fallo('la foto no quedó entera en la base (%s de %s)' % (n_foto_bd, len(filas_foto)), recuentos)
    distintas = {mo: (listas_bd[mo], previas[mo]) for mo in e2.MOTIVOS_APARTADO if listas_bd[mo] != previas[mo]}
    if distintas:
        raise Fallo('las listas de las puertas previas no son su recuento: %s' % distintas, recuentos)

    # ── 4 · La lista y lo que el cruce necesita, en el almacen cerrado ──────────────────────────
    codigos = e2.lista_para_keepa(foto)
    tandas = e2.partir_en_tandas(codigos, tanda)
    base = f'{edb.CARPETA}/{pasada}'
    texto = {'content-type': 'text/plain; charset=utf-8', 'upsert': 'true'}
    sb.storage.from_(BUCKET).upload(f'{base}/eans.txt', '\n'.join(codigos).encode('utf-8'), texto)
    if len(tandas) > 1:
        for i, t in enumerate(tandas, 1):
            sb.storage.from_(BUCKET).upload(f'{base}/eans_{i}.txt', '\n'.join(t).encode('utf-8'), texto)
    sidecar = {'pasada': pasada, 'modo': MODO, 'disp_pasada': ult['id'],
               'foto_en': ult.get('terminada_en') or ult.get('creada_en'), 'fichero_md5': ult.get('fichero_md5'),
               'hoy': hoy.isoformat(), 'n_en_oferta': cuentas['n_en_oferta'],
               'n_promo_caducada': cuentas['n_promo_caducada']}
    sb.storage.from_(BUCKET).upload(f'{base}/barrido.json', json.dumps(sidecar, ensure_ascii=False, default=str)
                                    .encode('utf-8'), {'content-type': 'application/json', 'upsert': 'true'})

    cierre = {'estado': 'esperando_csv', 'terminada_en': _ahora(), 'regla_activa': None,
              'marcas': info['marcas_reales'], 'ofertas': (False if MODO != 'todas' else None),
              'n_crudo': int(ult['n_crudo']), 'n_foto': cuentas['n_foto'], 'ruta_lista': edb.ruta_lista(pasada),
              'n_eans_lista': len(codigos), 'n_tandas': len(tandas), 'tanda': tanda}
    for p in e2.PUERTAS_PREVIAS:
        cierre['p_' + p] = previas[p]
    return cierre, len(codigos)


if __name__ == '__main__':
    main()
