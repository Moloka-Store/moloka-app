#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL BARRIDO DEL ESCANEO PRO DE OSMA (encargo AG, 02-oct-2026).

Lo lanza el boton «Barrer OSMA» de la v2 (Escaneo PRO · pestaña OSMA) por el workflow escaner2-osma-barrido.yml.
No entra en la web de OSMA: trabaja sobre la DESCARGA DIARIA que ya esta en la base (escaner2_osma_disponibilidad.py,
cada dia a las 07:15, encargo AE). Cero Keepa, cero Amazon.

QUE HACE, EN ORDEN:
  1. abre una pasada en `escaner2_pasada` (proveedor OSMA, modo 'todas', estado 'descargando') con el id del run;
  2. lee la ULTIMA pasada APLICADA de OSMA en `disp_pasada` y sus articulos en `disp_estado` (los vistos en ella,
     `ausencias = 0`): tienen que ser tantos como leyo (`n_leidas`) y de esa pasada, o no se sigue;
  3. comprueba que la puerta comun lee OSMA de la descarga (`disp_fuente` = 'disp') y saca el PORTE con su misma
     regla (`disp_parametros.pedido_previsto_eur` y la ultima factura de OSMA con `gastos_envio`);
  4. lee los enlaces de OSMA (`codigos_proveedor`, lista CERRADA) y las fichas de `productos` (SOLO LECTURA);
  5. construye la foto con `escaner2_osma.construir_foto` (con marca y disponible; crudo = previas + foto) y
     🔴 COMPRUEBA EL PORTE contra la puerta comun (`v_escaner_fuente`): mismo precio en las filas que estan en las
     dos, o la pasada falla (el porte se aplica UNA vez);
  6. guarda la foto en `escaner2_foto` y las listas de las puertas previas en `escaner2_apartado`, y lo CUENTA en la
     base;
  7. deja en el almacen cerrado `escaner2`: `osma/<pasada>/eans.txt` (LA lista, encargo AG2: los EAN de OSMA y el
     EAN de nuestra ficha de cada codigo enlazado que esta en la foto, uno por linea, sin repetir) y `barrido.json`
     (de que descarga sale, el porte, los enlaces y el EAN de cada ficha: lo que el cruce necesita para decidir igual);
  8. cierra la pasada en 'esperando_csv' (n_tandas = 1: una lista, un CSV del Visualizador, el de España) o en
     'fallida' con el motivo.

🔴 REPO PUBLICO: LOS REGISTROS LOS VE CUALQUIERA. Solo se imprimen estados y recuentos: NUNCA precios, EAN, ASIN,
   nombres, codigos de articulo ni el texto de un error (va a `escaner2_pasada.motivo_fallo`: la base es privada).
🔒 SOLO ESCRIBE `escaner2_pasada`, `escaner2_foto`, `escaner2_apartado` y `escaner2/osma/<pasada>/`. Ni disp_*, ni
   productos, ni codigos_proveedor, ni v_escaner_fuente, ni escaner_memoria.
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

import escaner2_motor as e2  # noqa: E402
import escaner2_osma as eo  # noqa: E402
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
    sb.table('escaner2_pasada').insert({
        'id': pasada, 'proveedor': eo.PROVEEDOR, 'estado': 'descargando', 'modo': eo.MODO,
        'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None}).execute()
    print(f">>> Pasada {pasada} abierta (descargando) · OSMA, artículos con marca y existencias.", flush=True)
    try:
        cierre, n_lista, n_fichas = barrer(pasada)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza (el check del cuadre), la pasada queda 'fallida'.
        sb.table('escaner2_pasada').update(cierre).eq('id', pasada).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, (Fallo, eo.FalloOsma)) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo[:1000],
                                                 'terminada_en': _ahora()},
                                                **getattr(ex, 'recuentos', {}))).eq('id', pasada).execute()
        # Al log, solo el tipo: el motivo puede llevar precios o EAN y el repo es publico.
        abortar(f'pasada {pasada} fallida ({type(ex).__name__}); el motivo está en escaner2_pasada.motivo_fallo')
    print(f">>> PASADA LISTA: {cierre['n_foto']} en la foto · una lista de {n_lista} códigos (de ellos, {n_fichas} "
          f"EAN de nuestras fichas que no traía OSMA). Esperando el CSV de Keepa de España.", flush=True)


def barrer(pasada):
    # ── 1 · La descarga de la que sale la foto: la ultima APLICADA ─────────────────────────────
    ult = (sb.table('disp_pasada').select('id,creada_en,terminada_en,n_leidas').eq('proveedor', eo.PROVEEDOR)
           .eq('estado', 'aplicada').order('creada_en', desc=True).limit(1).execute().data or [None])[0]
    if not ult:
        raise Fallo('no hay ninguna descarga de OSMA aplicada en disp_pasada')
    filas = _todas('disp_estado', 'producto_prov,ean_original,ean_core,marca,nombre,categoria,precio_unidad,'
                   'disponible,en_oferta,fin_de_vida,regla,pasada_id,ausencias,visto_en', 'producto_prov',
                   proveedor=eo.PROVEEDOR, ausencias=0)
    ajenas = sum(1 for f in filas if f.get('pasada_id') != ult['id'])
    print(f">>> Descarga de OSMA aplicada: leyó {ult.get('n_leidas')} · vistas en ella en disp_estado {len(filas)}"
          f" · de otra pasada {ajenas}", flush=True)
    if ult.get('n_leidas') is None or len(filas) != int(ult['n_leidas']) or ajenas:
        raise Fallo('la foto de OSMA no es la de su última descarga aplicada (%s): leyó %s y disp_estado tiene %d '
                    'vistas en ella (%d de otra pasada)' % (ult['id'], ult.get('n_leidas'), len(filas), ajenas))

    # ── 2 · La puerta comun y el porte ─────────────────────────────────────────────────────
    fuente = (sb.table('disp_fuente').select('fuente').eq('proveedor', eo.PROVEEDOR).execute().data or [{}])[0]
    if fuente.get('fuente') != 'disp':
        raise Fallo("la puerta común no lee OSMA de la descarga (disp_fuente = %r, no 'disp'): el precio con el "
                    "porte no se puede sacar de ella" % fuente.get('fuente'))
    par = (sb.table('disp_parametros').select('pedido_previsto_eur').eq('proveedor', eo.PROVEEDOR).execute().data
           or [None])[0]
    if par is None:
        raise Fallo('disp_parametros no tiene la fila de OSMA')
    facturas = _todas('facturas', 'id,fecha,created_at,gastos_envio', 'id', proveedor=eo.PROVEEDOR)
    porte = eo.porte_de(facturas, par.get('pedido_previsto_eur'))
    print(f">>> PORTE: {'en el precio, el de la puerta común' if porte['pct'] is not None else 'SIN porte'} · "
          f"facturas de OSMA leídas {len(facturas)}", flush=True)

    # ── 3 · Los enlaces por codigo (lista CERRADA) y las fichas ─────────────────────────────────
    codigos = _todas('codigos_proveedor', 'codigo_proveedor,producto_id', 'id', proveedor=eo.PROVEEDOR)
    productos = _todas('productos', 'id,asin,ean,activo,es_chase', 'id')
    if not productos:
        raise Fallo('productos devolvió 0 filas: sin las fichas no se saben los enlaces por código')
    enlaces, avisos_enl = eo.enlaces_de(codigos, productos)
    print(f">>> ENLACES de OSMA: {len(codigos)} códigos · con ficha viva {len(enlaces)} · avisos {len(avisos_enl)}",
          flush=True)

    # ── 4 · La foto y el cuadre desde el catalogo crudo ─────────────────────────────────────────
    M = e2.cargar_motor()
    foto, apartados, cuentas = eo.construir_foto(filas, enlaces, M, porte['pct'])
    previas = cuentas['previas']
    recuentos = dict({'n_crudo': cuentas['n_crudo']}, **{'p_' + p: v for p, v in previas.items()})
    print(">>> CUADRE PREVIO [OSMA]: catálogo %d = " % cuentas['n_crudo']
          + ' + '.join(f'{p} {previas[p]}' for p in e2.PUERTAS_PREVIAS)
          + f" + foto {cuentas['n_foto']} → {'CUADRA' if cuentas['cuadra_previo'] else 'NO CUADRA'}", flush=True)
    if not cuentas['cuadra_previo']:
        raise Fallo('NO CUADRA antes de la foto: catálogo %d ≠ previas %d + foto %d'
                    % (cuentas['n_crudo'], cuentas['n_previas'], cuentas['n_foto']), recuentos)
    if not foto:
        raise Fallo('la foto sale vacía: ningún artículo de OSMA con marca, existencias y EAN', recuentos)

    # 🔴 El porte, UNA vez: lo que dice la puerta comun de cada articulo que esta en la foto, al centimo.
    puerta = _todas('v_escaner_fuente', 'ean,es_case,pa,presente', 'ean', proveedor=eo.PROVEEDOR)
    comprobadas, mal = eo.comprobar_porte(foto, enlaces, puerta)
    print(f">>> PORTE contra la puerta común: filas de OSMA en ella {len(puerta)} · comprobadas {comprobadas} · "
          f"descuadres {len(mal)}", flush=True)
    if mal:
        raise Fallo('el precio de la foto no es el de la puerta común (el porte, ¿dos veces o ninguna?): '
                    + ' | '.join(mal[:20]), recuentos)
    if comprobadas == 0:
        raise Fallo('ninguna fila de OSMA de la puerta común está en la foto: no se puede comprobar el porte',
                    recuentos)

    # (AG2) UNA lista: los EAN de OSMA + el EAN de nuestra ficha de cada codigo enlazado de la foto, sin repetir.
    lista, eans_fichas = eo.lista_para_keepa_osma(foto, enlaces, M)
    n_fichas_nuevos = len(lista) - len(e2.lista_para_keepa(foto))
    if len(lista) > eo.TOPE_LISTA:
        raise Fallo('la lista tiene %d códigos y el Visualizador admite %d' % (len(lista), eo.TOPE_LISTA), recuentos)
    if len(lista) > eo.AVISO_LISTA:
        print(f"AVISO: la lista pasa de {eo.AVISO_LISTA} ({len(lista)})", flush=True)

    # ── 5 · La foto y las listas de las puertas previas, en la base, y CONTADAS ─────────────────
    filas_foto = []
    for f in foto:
        f['id'] = str(uuid.uuid4())
        filas_foto.append(dict({k: f[k] for k in (
            'producto_heo', 'ean_original', 'ean_core', 'variantes', 'codigos_keepa', 'nombre', 'marca', 'categoria',
            'precio_catalogo', 'precio_unidad', 'es_caja', 'uds_caja', 'es_chase', 'en_oferta', 'fin_de_vida',
            'preorder', 'aviso_caja', 'origen_ean', 'aviso_ean')},
            id=f['id'], pasada_id=pasada, campana=None, disponibilidad=None, imagen=None))
    _en_lotes('escaner2_foto', filas_foto)
    _en_lotes('escaner2_apartado', [dict(a, pasada_id=pasada) for a in apartados])
    n_foto_bd = _contar('escaner2_foto', pasada_id=pasada)
    listas_bd = {mo: _contar('escaner2_apartado', pasada_id=pasada, motivo=mo) for mo in e2.MOTIVOS_APARTADO}
    print(f"CUADRE foto [OSMA]: escritas {len(filas_foto)} | en la tabla {n_foto_bd} · listas de las puertas previas "
          f"en la tabla {listas_bd}", flush=True)
    if n_foto_bd != len(filas_foto):
        raise Fallo('la foto no quedó entera en la base (%s de %s)' % (n_foto_bd, len(filas_foto)), recuentos)
    distintas = {mo: (listas_bd[mo], previas[mo]) for mo in e2.MOTIVOS_APARTADO if listas_bd[mo] != previas[mo]}
    if distintas:
        raise Fallo('las listas de las puertas previas no son su recuento: %s' % distintas, recuentos)

    # ── 6 · La lista y lo que el cruce necesita, en el almacen cerrado ──────────────────────────
    base = f'{eo.CARPETA}/{pasada}'
    texto = {'content-type': 'text/plain; charset=utf-8', 'upsert': 'true'}
    sb.storage.from_(BUCKET).upload(f'{base}/eans.txt', '\n'.join(lista).encode('utf-8'), texto)
    en_foto = {f['producto_heo'] for f in foto}
    sidecar = {
        'pasada': pasada, 'disp_pasada': ult['id'], 'descarga_en': ult.get('terminada_en') or ult.get('creada_en'),
        'porte': dict(porte, pct=None if porte['pct'] is None else str(porte['pct'])),
        'enlaces': {c: e for c, e in enlaces.items() if c in en_foto},
        'eans_fichas': eans_fichas, 'n_eans_fichas_nuevos': n_fichas_nuevos, 'n_lista': len(lista),
        'avisos': avisos_enl, 'porte_comprobado': comprobadas,
    }
    sb.storage.from_(BUCKET).upload(f'{base}/barrido.json', json.dumps(sidecar, ensure_ascii=False, default=str)
                                    .encode('utf-8'), {'content-type': 'application/json', 'upsert': 'true'})

    cierre = {'estado': 'esperando_csv', 'terminada_en': _ahora(), 'regla_activa': None, 'marcas': None,
              'ofertas': None, 'n_crudo': cuentas['n_crudo'], 'n_foto': cuentas['n_foto'],
              'ruta_lista': f'{base}/eans.txt', 'n_eans_lista': len(lista), 'n_tandas': 1, 'tanda': max(len(lista), 1)}
    for p in e2.PUERTAS_PREVIAS:
        cierre['p_' + p] = previas[p]
    return cierre, len(lista), n_fichas_nuevos


if __name__ == '__main__':
    main()
