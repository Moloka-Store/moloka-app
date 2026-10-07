#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE OCIOSTOCK (encargo OC2, pieza (a) del plano de OC1, 07-oct-2026).

La lanza escaner2-ociostock-disponibilidad.yml. HOY A MANO: el reloj (cron-job.org) lo dan de alta Fernando y Cowork
cuando esto este fusionado y la migracion de la v2 aplicada: una pasada a las 09:00 de Madrid y dos comprobaciones a
las 13:00 y a las 17:00, los siete dias (parte OC1: el fichero se rehace una vez por noche, tambien en fin de semana).

QUE HACE, EN ORDEN (el esqueleto de escaner2_osma_disponibilidad.py, con la descarga de OcioStock):
  1. abre una pasada en `disp_pasada` (proveedor OCIOSTOCK, estado 'leyendo', con el id del run), y lee en la base
     el minimo de filas (`disp_parametros.crudo_minimo`) y la huella de la ultima pasada APLICADA;
  2. baja el fichero con el secreto OCIOSTOCK_FEED_URL (el mismo que usa el director viejo; un GET sin entrar en
     ninguna web), lo descomprime si viene en gzip y deja en la pasada su HUELLA: md5, bytes y, si la respuesta los
     trae, Last-Modified y ETag (regla 8);
  3. «AL DIA»: si el md5 es el de la ultima pasada aplicada, la pasada se cierra 'rechazada' con motivo «al día» y el
     run sale en VERDE (OCIOSTOCK_AL_DIA). Es lo normal en las comprobaciones de las 13 y las 17. Una 'rechazada' no
     cuenta en ningun sitio (el freno de disp_aplicar_pasada solo cuenta 'rechazada_vaciado');
  4. VALIDA antes de subir nada: la cabecera, las 54 columnas con su nombre y en su orden (si no → 'fallida' con el
     nombre de la columna); filas >= el minimo (si no → 'rechazada_vaciado'); y las reglas de lectura de
     escaner2_ociostock.py (llave unica, precios, tramos, stock y marcas de reserva que se entienden; si no →
     'fallida' con los recuentos);
  5. convierte cada fila con las ocho reglas de escaner2_ociostock.py, sube las filas a `disp_lectura` en lotes de
     500 y deja en la pasada sus recuentos (declarado = llegados = filas del fichero: OcioStock no tiene «tres
     endpoints»; la integridad la dan las guardas del paso 4) y el maximo de `fecha_ultima_modificacion`;
  6. llama a `disp_aplicar_pasada` (la funcion comun) y relee la pasada en la base: lo que vale es lo que hay alli;
  7. 🆕 (encargo OC4, 07-oct-2026) LAS NOVEDADES DE FUNKO: con la pasada APLICADA (no «al día», no rechazada), como paso
     aparte, `escaner2_novedades.novedades_tras_la_pasada(proveedor='OCIOSTOCK')`: la seleccion en la base
     (nov_seleccionar_pasada: entra, pasa a disponible o BAJA su precio_pa; sin preventas ni chase sueltos) y su
     valoracion (Keepa con KEEPA_API_KEY, la misma llave y saldo que HEO; Amazon lo pone el cartero de la v2; el Excel,
     si hay un COMPRAR, y el Telegram con TELEGRAM_TOKEN/TELEGRAM_CHAT_ID). Si falla, la pasada sigue aplicada y el run
     sale en ROJO al final; el vigia de la marca (algo que se parece a FUNKO sin serlo), tambien ROJO. Con el
     interruptor apagado (nov_parametros.valorar de OCIOSTOCK), cero llamadas a Keepa. Las cuentas que llegan despues
     del cartero las hace escaner2_ociostock_novedades_cuentas.py.

🔴 REPO PUBLICO: LOS REGISTROS DE EJECUCION LOS VE CUALQUIERA. Este programa SOLO imprime estados y recuentos. NUNCA:
   la URL del fichero (lleva el token del enlace), cabeceras, precios, stock, nombres, codigos o EAN, ni el texto de un
   error (puede llevar la URL o una fila de la base): un error inesperado sale SOLO por su tipo y su detalle va a
   `disp_pasada.motivo`, LIMPIO de la URL y de cualquier cadena hexadecimal larga (la base la leen mas personas que
   Fernando). Lo comprueba test_escaner2_ociostock.py ejecutando el programa contra respuestas falsas.

🔑 EN SOMBRA: OcioStock NO tiene fila en `disp_fuente`; Reponer y el Trackeador siguen leyendo la memoria del escaner
   viejo, que sigue corriendo como siempre. Este programa no lo toca.
🔒 SOLO TOCA: `disp_pasada`, `disp_lectura`, la funcion `disp_aplicar_pasada`, y para LEER `disp_parametros`. Ni
   escaner_memoria, ni reglas_director, ni escaner2_*, ni productos. Cero Amazon. (Encargo OC4) Las novedades van por
   escaner2_novedades.py (nov_*, Keepa, el Excel y el Telegram), con su registro DISCRETO (`imprimir_discreto`: ni EAN,
   ni ASIN, ni el texto de un error, que queda en nov_pasada.valoracion_motivo).
🔒 SIN LOS SECRETOS, NO SE CORRE: sin OCIOSTOCK_FEED_URL (o sin la base) aborta antes de abrir ninguna pasada.

Uso:  python escaner2_ociostock_disponibilidad.py            (la pasada)
      python escaner2_ociostock_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import gzip
import os
import re
import sys
from datetime import datetime, timezone

PROVEEDOR = 'OCIOSTOCK'
LOTE = 500
ESPERA_S = 180
TAM_MAXIMO = 400 * 1024 * 1024
AGENTE = 'Mozilla/5.0 (compatible; Moloka-escaner2/1.0)'
_RE_HEX = re.compile(r'[0-9a-fA-F]{24,}')


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar. `motivo` es SIEMPRE un texto
    escrito por este programa."""
    print(f"OCIOSTOCK_NO_EJECUTADA: {motivo}")
    sys.exit(1)


class Rechazo(Exception):
    """La pasada no se aplica: `estado` ('fallida', 'rechazada' o 'rechazada_vaciado') y un `motivo` que escribe este
    programa (estados y recuentos; se puede imprimir)."""

    def __init__(self, estado, motivo):
        super().__init__(motivo)
        self.estado, self.motivo = estado, motivo


class AlDia(Rechazo):
    """El fichero es el de la ultima pasada aplicada: 'rechazada' «al día», que no cuenta en ningun sitio, y verde."""

    def __init__(self, pasada_aplicada):
        super().__init__('rechazada', f'al día: el fichero es el mismo (md5) que el de la pasada aplicada {pasada_aplicada}; '
                                      f'nada nuevo')
        self.pasada_aplicada = pasada_aplicada


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def limpio(texto, url):
    """El texto de un error sin la URL del fichero ni cadenas hexadecimales largas (el token del enlace)."""
    t = str(texto)
    if url:
        t = t.replace(url, '<OCIOSTOCK_FEED_URL>')
    return _RE_HEX.sub('<hex>', t)


def bajar(sesion, url):
    """(contenido, cabeceras) del fichero, descomprimido si viene en gzip. Rechazo('fallida') si no llega bien."""
    r = sesion.get(url, timeout=ESPERA_S)
    if r.status_code != 200:
        raise Rechazo('fallida', f'la descarga respondió {r.status_code}')
    contenido = r.content or b''
    if contenido[:2] == b'\x1f\x8b':
        try:
            contenido = gzip.decompress(contenido)
        except OSError:
            raise Rechazo('fallida', 'lo bajado viene en gzip y no se descomprime') from None
    if not contenido:
        raise Rechazo('fallida', 'lo bajado está vacío')
    if len(contenido) > TAM_MAXIMO:
        raise Rechazo('fallida', f'lo bajado pesa {len(contenido)} bytes, más del tope de {TAM_MAXIMO}')
    cab = {str(k).lower(): v for k, v in (r.headers or {}).items()}
    return contenido, {'http_last_modified': (cab.get('last-modified') or None), 'http_etag': (cab.get('etag') or None)}


def _cerrar(sb, pasada, estado, motivo, extra=None):
    """La pasada queda cerrada con su estado y su motivo, y sin nada leido colgando (disp_lectura es de paso)."""
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    datos = dict(extra or {}, estado=estado, motivo=motivo[:1000], terminada_en=_ahora())
    sb.table('disp_pasada').update(datos).eq('id', pasada).eq('estado', 'leyendo').execute()


def pasada(sb, sesion, url, run_id):
    """La pasada entera. Devuelve el codigo de salida del programa."""
    import escaner2_ociostock as oc

    abrir = {'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(run_id) if run_id.isdigit() else None}
    pid = sb.table('disp_pasada').insert(abrir).execute().data[0]['id']
    print(f">>> Pasada de disponibilidad de OcioStock {pid} abierta (leyendo).", flush=True)
    rec = None
    try:
        par = sb.table('disp_parametros').select('crudo_minimo').eq('proveedor', PROVEEDOR).execute().data or [{}]
        minimo = par[0].get('crudo_minimo')
        if not isinstance(minimo, int) or isinstance(minimo, bool) or minimo <= 0:
            raise Rechazo('fallida', 'sin mínimo: disp_parametros no da un crudo_minimo válido para OCIOSTOCK; no se baja nada')
        ult = (sb.table('disp_pasada').select('id, fichero_md5').eq('proveedor', PROVEEDOR).eq('estado', 'aplicada')
                 .order('creada_en', desc=True).limit(1).execute().data or [{}])

        contenido, http = bajar(sesion, url)
        md5, n_bytes = oc.huella(contenido)
        huella = dict(http, fichero_md5=md5, fichero_bytes=n_bytes)
        sb.table('disp_pasada').update(huella).eq('id', pid).execute()
        print(f">>> Fichero bajado: {n_bytes} bytes, md5 {md5}; Last-Modified {'sí' if http['http_last_modified'] else 'no'}, "
              f"ETag {'sí' if http['http_etag'] else 'no'}.", flush=True)
        if ult[0].get('fichero_md5') == md5:
            raise AlDia(ult[0].get('id'))

        try:
            cabecera, filas = oc.leer_csv(contenido)
            oc.comprobar_cabecera(cabecera)
        except oc.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        n = len(filas)
        print(f">>> Fichero: {n} filas; cabecera conforme ({len(oc.COLUMNAS)} columnas).", flush=True)
        if n < minimo:
            rec = {'n_declarado': n, 'n_crudo': n}
            raise Rechazo('rechazada_vaciado', f'vaciado: {n} filas en el fichero, por debajo del mínimo {minimo}')
        try:
            lectura, c = oc.convertir(cabecera, filas)
        except oc.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        rec = {'n_declarado': n, 'n_crudo': n, 'n_declarado_precios': n, 'n_precios': n,
               'n_declarado_disponibilidades': n, 'n_disponibilidades': n, 'n_sin_gtin': c['n_sin_gtin'],
               'n_duplicados': 0, 'n_duplicados_precios': 0, 'n_duplicados_disponibilidades': 0,
               'fichero_fecha_max': c['fecha_max']}
        print(f">>> Leídas {c['n_leidas']} (disponibles {c['n_disponibles']}, agotados {c['n_agotados']}) · sin EAN "
              f"{c['n_sin_gtin']} · sin dato de stock {c['n_sin_dato_disponibilidad']}, de precio {c['n_sin_dato_precio']} · "
              f"preventa {c['n_preventa']} (con stock {c['n_preventa_con_stock']}) · cajas de 6 {c['n_cajas']} (disponibles "
              f"{c['n_cajas_disponibles']}; «5 + 1» sin C6 disponibles {c['n_cajas_cinco_mas_uno_sin_c6_disponibles']}) · "
              f"chase sueltos {c['n_chase_suelto']} (disponibles {c['n_chase_suelto_disponibles']}) · EAN de forma rara "
              f"{c['n_ean_forma_rara']} · GTIN-14 {c['n_gtin14']} · el escalón gana en {c['n_escalon_gana']} · fichero "
              f"modificado hasta {c['fecha_max']}", flush=True)
        sb.table('disp_pasada').update(rec).eq('id', pid).execute()
        for i in range(0, len(lectura), LOTE):
            sb.table('disp_lectura').insert([dict(f, pasada_id=pid) for f in lectura[i:i + LOTE]]).execute()
        sb.table('disp_pasada').update({
            'n_leidas': c['n_leidas'], 'n_disponibles': c['n_disponibles'], 'n_agotados': c['n_agotados'],
            'n_sin_dato_disponibilidad': c['n_sin_dato_disponibilidad'], 'n_sin_dato_precio': c['n_sin_dato_precio'],
        }).eq('id', pid).execute()
        sb.rpc('disp_aplicar_pasada', {'p_pasada': pid}).execute()
    except Rechazo as ex:
        _cerrar(sb, pid, ex.estado, ex.motivo, rec)
        if isinstance(ex, AlDia):
            print(f"OCIOSTOCK_AL_DIA: el fichero es el de la pasada aplicada {ex.pasada_aplicada}; nada nuevo.", flush=True)
            return 0
        print(f"OCIOSTOCK_NO_APLICADA: pasada {pid} {ex.estado}: {ex.motivo}", flush=True)
        return 1
    except Exception as ex:
        # 🔴 REPO PÚBLICO: el texto de un error puede llevar la URL del fichero o una fila de la base. Al registro,
        #    SOLO su tipo; el detalle, limpio, a la base.
        motivo_log = f'error inesperado ({type(ex).__name__}); el detalle queda en disp_pasada.motivo'
        try:
            _cerrar(sb, pid, 'fallida', limpio(f'{type(ex).__name__}: {ex}', url), rec)
        except Exception as ex2:
            motivo_log += f'; tampoco se ha podido cerrar la pasada ({type(ex2).__name__})'
        print(f"OCIOSTOCK_NO_APLICADA: pasada {pid} fallida: {motivo_log}", flush=True)
        return 1

    # Lo que vale es lo que hay en la base.
    fila = sb.table('disp_pasada').select('*').eq('id', pid).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila.get(k)}' for k in (
        'estado', 'primera', 'caida_aceptada', 'n_crudo', 'n_sin_gtin', 'n_leidas', 'n_disponibles', 'n_agotados',
        'n_sin_dato_precio', 'n_entran', 'n_vuelven', 'n_salen', 'n_a_disponible', 'n_a_agotado', 'n_cambio_precio',
        'n_ausentes', 'n_en_catalogo', 'n_disponibles_estado')), flush=True)
    if fila.get('estado') != 'aplicada':
        # Los motivos de disp_aplicar_pasada son recuentos (los escribe la función, no el fichero).
        print(f"OCIOSTOCK_NO_APLICADA: pasada {pid} {fila.get('estado')}: {fila.get('motivo')}", flush=True)
        return 1
    print(f">>> PASADA APLICADA: {fila.get('n_en_catalogo')} productos de OcioStock en el catálogo, "
          f"{fila.get('n_disponibles_estado')} disponibles.", flush=True)
    codigo = 0
    if fila.get('caida_aceptada'):
        print(f"CAIDA_ACEPTADA: la pasada {pid} se ha aplicado como NUEVA REFERENCIA tras varios rechazos estables por "
              f"el freno del 90 %: hay que mirar si OcioStock ha caído de verdad.", flush=True)
        codigo = 1
    # 7 · LAS NOVEDADES DE FUNKO (encargo OC4): paso aparte con la pasada ya aplicada; no lanza nunca. Si falla, ROJO al final.
    if not novedades(sb, pid, run_id):
        codigo = 1
    return codigo


def novedades(sb, pid, run_id):
    """Las novedades de Funko de la pasada aplicada `pid` (encargo OC4). NUNCA LANZA. Devuelve True si todo fue bien
    (sin el vigia de la marca). 🔴 Repo publico: el registro, discreto (solo estados y recuentos)."""
    try:
        import escaner2_novedades as nv
        ok, seleccion = nv.novedades_tras_la_pasada(sb, pid, PROVEEDOR, keepa_llave=os.environ.get('KEEPA_API_KEY'),
                                                    imprimir=nv.imprimir_discreto, run_id=run_id or None)
    except Exception as ex:
        print(f"OCIOSTOCK_NOVEDADES_NO_HECHAS: la pasada {pid} sigue aplicada; las novedades han fallado antes de poder "
              f"apuntarse ({type(ex).__name__})", flush=True)
        return False
    marca_parecida = (seleccion or {}).get('marca_parecida') or 0
    if marca_parecida:
        print(f"MARCA_PARECIDA: {marca_parecida} producto(s) de OcioStock tienen una marca que se parece a FUNKO y no es "
              f"ella: si OcioStock cambia la grafía, las novedades de Funko se quedarían a cero en silencio "
              f"(nov_pasada.n_marca_parecida de la pasada {pid}).", flush=True)
    if not ok:
        print(f"OCIOSTOCK_NOVEDADES_EN_ROJO: la pasada {pid} sigue aplicada; las novedades no han salido bien (el detalle, "
              f"en nov_pasada de esa pasada).", flush=True)
    return ok and not marca_parecida


def rescatar(sb, run_id):
    """🔴 Si el run muere a medias (tope de tiempo, cancelacion), su pasada no se queda 'leyendo' para siempre: SOLO
    la de ESTE run, de OcioStock, y solo si sigue leyendo."""
    if not run_id.isdigit():
        abortar('sin GITHUB_RUN_ID: no se sabe qué pasada es de este run')
    res = (sb.table('disp_pasada').select('id').eq('run_id', int(run_id)).eq('proveedor', PROVEEDOR)
             .eq('estado', 'leyendo').execute())
    for f in res.data or []:
        _cerrar(sb, f['id'], 'fallida', f'el run {run_id} terminó sin cerrar la pasada (tope de tiempo, cancelación o '
                                         f'caída); mira su log en Actions')
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de OcioStock de este run pasan de 'leyendo' a 'fallida'.")


def principal(argv):
    rescate = argv == ['--rescate']
    if argv not in ([], ['--rescate']):
        abortar('uso: escaner2_ociostock_disponibilidad.py [--rescate]')
    if not rescate and not os.environ.get('OCIOSTOCK_FEED_URL'):
        abortar('falta OCIOSTOCK_FEED_URL (secreto del repo); no se abre ninguna pasada')
    if not (os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_KEY')):
        abortar('faltan SUPABASE_URL/SUPABASE_SERVICE_KEY; no se abre ninguna pasada')
    run_id = os.environ.get('GITHUB_RUN_ID') or ''
    from supabase import create_client
    sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
    if rescate:
        try:
            rescatar(sb, run_id)
        except Exception as ex:
            abortar(f'el rescate ha fallado ({type(ex).__name__})')
        return 0
    import requests
    sesion = requests.Session()
    sesion.headers['User-Agent'] = AGENTE
    return pasada(sb, sesion, os.environ['OCIOSTOCK_FEED_URL'], run_id)


if __name__ == '__main__':
    try:
        codigo = principal(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar la URL del fichero
        print(f"OCIOSTOCK_NO_EJECUTADA: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
