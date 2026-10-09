#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE DBLINE (encargo DB2-A, 09-oct-2026).

La lanza escaner2-dbline-disponibilidad.yml, HOY SOLO A MANO. El esqueleto es el de escaner2_ociostock_disponibilidad.py,
con la descarga de DBLine y las reglas de escaner2_dbline.py.

🔴 TODAVIA NO PUEDE CORRER: depende de la migracion de la v2 (pendiente) que añade `fin_oferta` a `disp_lectura` y a
   `disp_estado`, `huella_contenido` a `disp_pasada` y la fila DBLINE de `disp_parametros`. Sin ella, sale en ROJO al
   leer los parametros (no hay minimo) o al subir las filas, y la pasada queda 'fallida'.

QUE HACE, EN ORDEN:
  1. abre una pasada en `disp_pasada` (proveedor DBLINE, 'leyendo', con el id del run) y lee el minimo de filas
     (`disp_parametros.crudo_minimo`) y la huella de contenido de la ultima pasada APLICADA;
  2. baja el catalogo con `descargar_dbline.descargar_catalogo_dbline()` TAL CUAL (el mismo que usa el director viejo),
     con su salida TRAGADA: ese modulo imprime la respuesta del login y, si no llega un .xlsx, el principio de la
     respuesta y una URL. Al registro no llega nada suyo;
  3. lee con escaner2_dbline.convertir (la fecha de «hoy», la de Madrid): si no se entiende → 'fallida' con recuentos;
     filas por debajo del minimo o disponibles por debajo de escaner2_dbline.MIN_DISPONIBLES → 'rechazada_vaciado';
  4. «AL DIA» POR CONTENIDO: si la huella de contenido es la de la ultima pasada aplicada → 'rechazada' «al día» y
     VERDE (DBLINE_AL_DIA). El md5 del fichero cambia en cada descarga (la hora va pegada a las fechas) y no sirve;
  5. sube las filas a `disp_lectura` en lotes de 500, deja los recuentos y llama a `disp_aplicar_pasada`; lo que vale
     es lo que relee de la base.

🔴 REPO PUBLICO: SOLO estados y recuentos. NUNCA la respuesta de DBLine, una URL, cabeceras, precios, nombres,
   codigos o EAN, ni el texto de un error (al registro, solo su tipo; el detalle, limpio, a `disp_pasada.motivo`). Lo
   comprueba test_escaner2_dbline_disponibilidad.py ejecutando el programa con una descarga y una base de mentira.
🔑 EN SOMBRA: sin fila en `disp_fuente`; el director viejo sigue como siempre y este programa no lo toca.
🔒 SOLO TOCA `disp_pasada`, `disp_lectura`, la funcion `disp_aplicar_pasada`, y LEE `disp_parametros`.
🔒 SIN LOS SECRETOS (DBLINE_USER/DBLINE_PASS y la base), NO SE CORRE: aborta antes de abrir ninguna pasada.

Uso:  python escaner2_dbline_disponibilidad.py            (la pasada)
      python escaner2_dbline_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import contextlib
import io
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PROVEEDOR = 'DBLINE'
LOTE = 500
_RE_HEX = re.compile(r'[0-9a-fA-F]{24,}')
_RE_URL = re.compile(r'https?://\S+')


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO. `motivo` es SIEMPRE un texto escrito por este programa."""
    print(f"DBLINE_NO_EJECUTADA: {motivo}")
    sys.exit(1)


class Rechazo(Exception):
    """La pasada no se aplica: `estado` y un `motivo` escrito por este programa (estados y recuentos)."""

    def __init__(self, estado, motivo):
        super().__init__(motivo)
        self.estado, self.motivo = estado, motivo


class AlDia(Rechazo):
    def __init__(self, pasada_aplicada):
        super().__init__('rechazada', f'al día: el contenido es el mismo que el de la pasada aplicada {pasada_aplicada}; '
                                      f'nada nuevo')
        self.pasada_aplicada = pasada_aplicada


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def hoy_madrid():
    return datetime.now(ZoneInfo('Europe/Madrid')).date()


def limpio(texto, secretos=()):
    """El texto de un error sin URLs, sin los secretos y sin cadenas hexadecimales largas."""
    t = str(texto)
    for s in secretos:
        if s:
            t = t.replace(s, '<secreto>')
    return _RE_HEX.sub('<hex>', _RE_URL.sub('<url>', t))


def bajar():
    """Los bytes del catalogo, con descargar_dbline TAL CUAL y su salida tragada (imprime la respuesta del login)."""
    import descargar_dbline
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return descargar_dbline.descargar_catalogo_dbline()


def _cerrar(sb, pasada, estado, motivo, extra=None):
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    datos = dict(extra or {}, estado=estado, motivo=motivo[:1000], terminada_en=_ahora())
    sb.table('disp_pasada').update(datos).eq('id', pasada).eq('estado', 'leyendo').execute()


def pasada(sb, run_id, hoy):
    """La pasada entera. Devuelve el codigo de salida del programa."""
    import escaner2_dbline as db

    abrir = {'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(run_id) if run_id.isdigit() else None}
    pid = sb.table('disp_pasada').insert(abrir).execute().data[0]['id']
    print(f">>> Pasada de disponibilidad de DBLine {pid} abierta (leyendo).", flush=True)
    rec = None
    try:
        par = sb.table('disp_parametros').select('crudo_minimo').eq('proveedor', PROVEEDOR).execute().data or [{}]
        minimo = par[0].get('crudo_minimo')
        if not isinstance(minimo, int) or isinstance(minimo, bool) or minimo <= 0:
            raise Rechazo('fallida', 'sin mínimo: disp_parametros no da un crudo_minimo válido para DBLINE; no se baja nada')
        ult = (sb.table('disp_pasada').select('id, huella_contenido').eq('proveedor', PROVEEDOR).eq('estado', 'aplicada')
                 .order('creada_en', desc=True).limit(1).execute().data or [{}])

        contenido = bajar()
        md5, n_bytes = db.huella_fichero(contenido)
        sb.table('disp_pasada').update({'fichero_md5': md5, 'fichero_bytes': n_bytes}).eq('id', pid).execute()
        print(f">>> Fichero bajado: {n_bytes} bytes.", flush=True)

        try:
            lectura, c = db.convertir(contenido, hoy, min_filas=0, min_disponibles=0)
        except db.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        n = c['n_crudo']
        rec = {'n_declarado': n, 'n_crudo': n, 'n_declarado_precios': n, 'n_precios': n,
               'n_declarado_disponibilidades': n, 'n_disponibilidades': n, 'n_sin_gtin': 0,
               'n_duplicados': 0, 'n_duplicados_precios': 0, 'n_duplicados_disponibilidades': 0,
               'huella_contenido': c['huella_contenido']}
        pm = c['por_marca']
        print(f">>> Leídas {c['n_leidas']} (disponibles {c['n_disponibles']}, agotados {c['n_agotados']}) · cabecera "
              f"{c['idioma_cabecera']} · catálogo del {c['fecha_catalogo']} · sin dato de stock "
              f"{c['n_sin_dato_disponibilidad']}, de precio {c['n_sin_dato_precio']} · preventa {c['n_preventa']} (con "
              f"stock {c['n_preventa_con_stock']}) · en oferta {c['n_en_oferta']}, promo caducada {c['n_promo_caducada']} "
              f"· chase sueltos {c['n_chase_suelto']} · EAN de forma rara {c['n_ean_forma_rara']} (de 11 cifras a UPC "
              f"{c['n_ean_11_upc']}) · Funko {pm['funko']['filas']} (disponibles {pm['funko']['disponibles']}) · "
              f"Pyramid {pm['pyramid']['filas']} (disponibles {pm['pyramid']['disponibles']})", flush=True)
        if n < minimo:
            raise Rechazo('rechazada_vaciado', f'vaciado: {n} filas en el fichero, por debajo del mínimo {minimo}')
        if c['n_disponibles'] < db.MIN_DISPONIBLES:
            raise Rechazo('rechazada_vaciado', f"vaciado: {c['n_disponibles']} disponibles, por debajo del mínimo "
                                               f"{db.MIN_DISPONIBLES}")
        if ult[0].get('huella_contenido') == c['huella_contenido']:
            raise AlDia(ult[0].get('id'))

        sb.table('disp_pasada').update(rec).eq('id', pid).execute()
        # `fecha_salida` no tiene columna en disp_lectura (no la pide nadie): fuera antes de subir.
        filas = [{k: v for k, v in f.items() if k != 'fecha_salida'} for f in lectura]
        for i in range(0, len(filas), LOTE):
            sb.table('disp_lectura').insert([dict(f, pasada_id=pid) for f in filas[i:i + LOTE]]).execute()
        sb.table('disp_pasada').update({
            'n_leidas': c['n_leidas'], 'n_disponibles': c['n_disponibles'], 'n_agotados': c['n_agotados'],
            'n_sin_dato_disponibilidad': c['n_sin_dato_disponibilidad'], 'n_sin_dato_precio': c['n_sin_dato_precio'],
        }).eq('id', pid).execute()
        sb.rpc('disp_aplicar_pasada', {'p_pasada': pid}).execute()
    except Rechazo as ex:
        _cerrar(sb, pid, ex.estado, ex.motivo, rec)
        if isinstance(ex, AlDia):
            print(f"DBLINE_AL_DIA: el contenido es el de la pasada aplicada {ex.pasada_aplicada}; nada nuevo.", flush=True)
            return 0
        print(f"DBLINE_NO_APLICADA: pasada {pid} {ex.estado}: {ex.motivo}", flush=True)
        return 1
    except Exception as ex:
        # 🔴 REPO PÚBLICO: el texto de un error puede llevar una URL, la respuesta de DBLine o una fila de la base.
        motivo_log = f'error inesperado ({type(ex).__name__}); el detalle queda en disp_pasada.motivo'
        try:
            _cerrar(sb, pid, 'fallida', limpio(f'{type(ex).__name__}: {ex}',
                                               (os.environ.get('DBLINE_USER'), os.environ.get('DBLINE_PASS'))), rec)
        except Exception as ex2:
            motivo_log += f'; tampoco se ha podido cerrar la pasada ({type(ex2).__name__})'
        print(f"DBLINE_NO_APLICADA: pasada {pid} fallida: {motivo_log}", flush=True)
        return 1

    fila = sb.table('disp_pasada').select('*').eq('id', pid).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila.get(k)}' for k in (
        'estado', 'primera', 'caida_aceptada', 'n_crudo', 'n_leidas', 'n_disponibles', 'n_agotados',
        'n_sin_dato_precio', 'n_entran', 'n_vuelven', 'n_salen', 'n_a_disponible', 'n_a_agotado', 'n_cambio_precio',
        'n_ausentes', 'n_en_catalogo', 'n_disponibles_estado')), flush=True)
    if fila.get('estado') != 'aplicada':
        print(f"DBLINE_NO_APLICADA: pasada {pid} {fila.get('estado')}: {fila.get('motivo')}", flush=True)
        return 1
    print(f">>> PASADA APLICADA: {fila.get('n_en_catalogo')} productos de DBLine en el catálogo, "
          f"{fila.get('n_disponibles_estado')} disponibles.", flush=True)
    if fila.get('caida_aceptada'):
        print(f"CAIDA_ACEPTADA: la pasada {pid} se ha aplicado como NUEVA REFERENCIA tras varios rechazos estables por "
              f"el freno del 90 %: hay que mirar si DBLine ha caído de verdad.", flush=True)
        return 1
    return 0


def rescatar(sb, run_id):
    """Si el run muere a medias, SOLO la pasada de ESTE run, de DBLine, y solo si sigue leyendo, queda 'fallida'."""
    if not run_id.isdigit():
        abortar('sin GITHUB_RUN_ID: no se sabe qué pasada es de este run')
    res = (sb.table('disp_pasada').select('id').eq('run_id', int(run_id)).eq('proveedor', PROVEEDOR)
             .eq('estado', 'leyendo').execute())
    for f in res.data or []:
        _cerrar(sb, f['id'], 'fallida', f'el run {run_id} terminó sin cerrar la pasada (tope de tiempo, cancelación o '
                                         f'caída); mira su log en Actions')
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de DBLine de este run pasan de 'leyendo' a 'fallida'.")


def principal(argv):
    rescate = argv == ['--rescate']
    if argv not in ([], ['--rescate']):
        abortar('uso: escaner2_dbline_disponibilidad.py [--rescate]')
    if not rescate and not (os.environ.get('DBLINE_USER') and os.environ.get('DBLINE_PASS')):
        abortar('faltan DBLINE_USER/DBLINE_PASS (secretos del repo); no se abre ninguna pasada')
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
    return pasada(sb, run_id, hoy_madrid())


if __name__ == '__main__':
    try:
        codigo = principal(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar la respuesta de DBLine
        print(f"DBLINE_NO_EJECUTADA: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
