#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL BARRIDO DEL ESCANEO PRO DE ZENTRADA (encargo de la tarjeta de Zentrada, 05-oct-2026).

Lo lanza la v2 (Escaneo PRO · tarjeta de Zentrada) cuando Fernando suelta el Excel del dia, por el workflow
escaner2-zentrada-barrido.yml con el input `pasada`: la v2 ya ha pasado las guardas, ha elegido el id de la pasada y
ha dejado el Excel en `escaner2/zentrada/<pasada>/`. NO entra en zentrada.com (lo bloquea; el catalogo lo lee Cowork
con la sesion de Moloka). Cero Keepa, cero Amazon.

QUE HACE, EN ORDEN:
  1. comprueba que esa pasada NO existe todavia y que en su carpeta hay UN Excel;
  2. lo baja y le pasa OTRA VEZ las guardas (`escaner2_zentrada.leer_excel`, las mismas que la v2). 🔴 Si falla una,
     NO se crea la pasada: el run sale en rojo y el Excel se queda donde esta (sin pasada no lo enseña nadie);
  3. abre la pasada en `escaner2_pasada` (proveedor ZENTRADA, modo 'excel', estado 'descargando') con el id del run;
  4. construye la foto (`construir_foto`: una fila por EAN con su oferta mas barata que se puede pedir; crudo =
     ofertas = previas + foto), la guarda en `escaner2_foto` y las listas de las puertas previas en
     `escaner2_apartado`, y lo CUENTA en la base;
  5. deja en el almacen cerrado `escaner2`: `zentrada/<pasada>/eans.txt` (los EAN con alguna oferta que se puede pedir),
     `asins.txt` (los ASIN de «Fichas» de un EAN que se puede pedir, para el modo «ASIN» del Visualizador) y
     `barrido.json` (lo de la compra de cada EAN, las fichas de «Fichas» y lo que el cruce necesita);
  6. cierra la pasada en 'esperando_csv' (n_tandas = 1: la lista de EAN; la de ASIN va aparte, como en OSMA) o en
     'fallida' con el motivo.

🔴 REPO PUBLICO: LOS REGISTROS LOS VE CUALQUIERA. Solo se imprimen estados, recuentos y los motivos de las guardas
   (que dicen hojas, filas y fechas: nunca un precio, un EAN, un ASIN ni un nombre de producto).
🔒 SOLO ESCRIBE `escaner2_pasada`, `escaner2_foto`, `escaner2_apartado` y `escaner2/zentrada/<pasada>/`.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: sin ella aborta antes de crear ningun cliente.
"""
import json
import os
import re
import sys
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
    abortar('la pasada no es un id válido')

import escaner2_motor as e2  # noqa: E402
import escaner2_zentrada as ez  # noqa: E402
from foto_comun import descargar_buzon, listar_buzon  # noqa: E402
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
    return datetime.now(timezone.utc)


def _en_lotes(tabla, filas):
    for i in range(0, len(filas), LOTE):
        sb.table(tabla).insert(filas[i:i + LOTE]).execute()


def _contar(tabla, **filtros):
    q = sb.table(tabla).select('id', count='exact')
    for k, v in filtros.items():
        q = q.eq(k, v)
    return q.limit(1).execute().count


def main():
    base = f'{ez.CARPETA}/{PASADA}'
    # ── 0 · La pasada no existe todavia, y en su carpeta hay UN Excel ──────────────────────────
    if sb.table('escaner2_pasada').select('id').eq('id', PASADA).limit(1).execute().data:
        abortar(f'la pasada {PASADA} ya existe: este Excel ya se barrió')
    excels = [o for o in listar_buzon(sb, BUCKET, base) if (o.get('name') or '').lower().endswith('.xlsx')]
    if len(excels) != 1:
        abortar(f'en {base}/ tiene que haber UN Excel y hay {len(excels)}')
    nombre = excels[0]['name']
    contenido = descargar_buzon(sb, BUCKET, f'{base}/{nombre}')
    print(f">>> Excel de Zentrada: {len(contenido)} bytes.", flush=True)

    # ── 1 · Las guardas, otra vez: si falla una, NO hay pasada ────────────────────────────────
    try:
        excel = ez.leer_excel(contenido, _ahora())
    except ez.FalloZentrada as ex:
        abortar(f'el Excel no pasa sus guardas, no se crea la pasada: {ex}')
    print(f">>> GUARDAS: bien · ofertas {len(excel['ofertas'])} · fichas {len(excel['fichas'])}", flush=True)

    sb.table('escaner2_pasada').insert({
        'id': PASADA, 'proveedor': ez.PROVEEDOR, 'estado': 'descargando', 'modo': ez.MODO,
        'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None}).execute()
    print(f">>> Pasada {PASADA} abierta (descargando) · Zentrada, el Excel del día.", flush=True)
    try:
        cierre, n_lista, n_asin = barrer(base, nombre, excel)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza (el check del cuadre), la pasada queda 'fallida'.
        sb.table('escaner2_pasada').update(cierre).eq('id', PASADA).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, (Fallo, ez.FalloZentrada)) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo[:1000],
                                                 'terminada_en': _ahora().isoformat()},
                                                **getattr(ex, 'recuentos', {}))).eq('id', PASADA).execute()
        abortar(f'pasada {PASADA} fallida ({type(ex).__name__}); el motivo está en escaner2_pasada.motivo_fallo')
    print(f">>> PASADA LISTA: {cierre['n_foto']} EAN en la foto · lista de {n_lista} códigos y {n_asin} ASIN de "
          f"«Fichas». Esperando los CSV de Keepa de España.", flush=True)


def barrer(base, nombre, excel):
    M = e2.cargar_motor()
    foto, apartados, cuentas, compra = ez.construir_foto(excel['ofertas'], M)
    previas = cuentas['previas']
    recuentos = dict({'n_crudo': cuentas['n_crudo']}, **{'p_' + p: v for p, v in previas.items()})
    print(">>> CUADRE PREVIO [ZENTRADA]: ofertas %d = " % cuentas['n_crudo']
          + ' + '.join(f'{p} {previas[p]}' for p in e2.PUERTAS_PREVIAS)
          + f" + foto {cuentas['n_foto']} → {'CUADRA' if cuentas['cuadra_previo'] else 'NO CUADRA'}", flush=True)
    if not cuentas['cuadra_previo']:
        raise Fallo('NO CUADRA antes de la foto: ofertas %d ≠ previas %d + foto %d'
                    % (cuentas['n_crudo'], cuentas['n_previas'], cuentas['n_foto']), recuentos)
    if not foto:
        raise Fallo('la foto sale vacía: ninguna oferta que se pueda pedir con un EAN válido', recuentos)

    lista = ez.lista_para_keepa(foto)
    if len(lista) > ez.TOPE_LISTA:
        raise Fallo('la lista tiene %d códigos y el Visualizador admite %d' % (len(lista), ez.TOPE_LISTA), recuentos)
    disponibles, agotados = ez.mapa_de_fichas(excel['fichas'], foto)
    asins = ez.lista_asin(disponibles)
    print(f">>> FICHAS: {len(excel['fichas'])} · de EAN que se pueden pedir {len(disponibles)} ({len(asins)} ASIN en su "
          f"lista) · sin oferta que se pueda pedir {len(agotados)}", flush=True)

    # ── La foto y las listas de las puertas previas, en la base, y CONTADAS ─────────────────────
    import uuid
    filas_foto = []
    for f in foto:
        f['id'] = str(uuid.uuid4())
        filas_foto.append(dict({k: f[k] for k in (
            'producto_heo', 'ean_original', 'ean_core', 'variantes', 'codigos_keepa', 'nombre', 'marca', 'categoria',
            'precio_catalogo', 'precio_unidad', 'es_caja', 'uds_caja', 'es_chase', 'en_oferta', 'fin_de_vida',
            'preorder', 'aviso_caja', 'origen_ean', 'aviso_ean')},
            id=f['id'], pasada_id=PASADA, campana=None, disponibilidad=None, imagen=None))
    _en_lotes('escaner2_foto', filas_foto)
    _en_lotes('escaner2_apartado', [dict(a, pasada_id=PASADA) for a in apartados])
    n_foto_bd = _contar('escaner2_foto', pasada_id=PASADA)
    listas_bd = {mo: _contar('escaner2_apartado', pasada_id=PASADA, motivo=mo) for mo in e2.MOTIVOS_APARTADO}
    print(f"CUADRE foto [ZENTRADA]: escritas {len(filas_foto)} | en la tabla {n_foto_bd} · listas de las puertas "
          f"previas en la tabla {listas_bd}", flush=True)
    if n_foto_bd != len(filas_foto):
        raise Fallo('la foto no quedó entera en la base (%s de %s)' % (n_foto_bd, len(filas_foto)), recuentos)
    distintas = {mo: (listas_bd[mo], previas[mo]) for mo in e2.MOTIVOS_APARTADO if listas_bd[mo] != previas[mo]}
    if distintas:
        raise Fallo('las listas de las puertas previas no son su recuento: %s' % distintas, recuentos)

    # ── Las listas y lo que el cruce necesita, en el almacen cerrado ────────────────────────────
    texto = {'content-type': 'text/plain; charset=utf-8', 'upsert': 'true'}
    sb.storage.from_(BUCKET).upload(f'{base}/eans.txt', '\n'.join(lista).encode('utf-8'), texto)
    # Siempre, aunque vaya vacia: la v2 la lee para saber si espera uno o dos CSV.
    sb.storage.from_(BUCKET).upload(f'{base}/asins.txt', '\n'.join(asins).encode('utf-8'), texto)
    sidecar = {
        'pasada': PASADA, 'excel': nombre, 'leido': ez._madrid(excel['leido']) if excel.get('leido') else None,
        'compra': compra, 'n_lista': len(lista), 'n_lista_asin': len(asins),
        'mapa': {'disponibles': disponibles, 'agotados': agotados},
        'precios_sin_pedir': ez.precios_sin_pedir(excel['ofertas']),
        'resumen_excel': [[d, v] for d, v in excel.get('resumen') or []],
    }
    sb.storage.from_(BUCKET).upload(f'{base}/barrido.json', json.dumps(sidecar, ensure_ascii=False, default=str)
                                    .encode('utf-8'), {'content-type': 'application/json', 'upsert': 'true'})

    cierre = {'estado': 'esperando_csv', 'terminada_en': _ahora().isoformat(), 'regla_activa': None, 'marcas': None,
              'ofertas': None, 'n_crudo': cuentas['n_crudo'], 'n_foto': cuentas['n_foto'],
              'ruta_lista': f'{base}/eans.txt', 'n_eans_lista': len(lista), 'n_tandas': 1, 'tanda': max(len(lista), 1)}
    for p in e2.PUERTAS_PREVIAS:
        cierre['p_' + p] = previas[p]
    return cierre, len(lista), len(asins)


if __name__ == '__main__':
    main()
