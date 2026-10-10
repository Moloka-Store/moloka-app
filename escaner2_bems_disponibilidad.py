#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE BEMS, DESDE EL CSV SUBIDO AL ALMACEN (encargo BE2, 10-oct-2026).

La lanza escaner2-bems-disponibilidad.yml, SOLO A MANO (workflow_dispatch), con el input `pasada`: el id de la
carpeta del almacen donde esta el CSV. El esqueleto es el de escaner2_dbline_disponibilidad.py; la diferencia es que el
fichero NO se baja de la web del proveedor: lo baja Fernando a mano de la web de BEMS y lo sube (encargo BE3, el buzon
de la v2) a `escaner2/bems/foto/<pasada>/BEMS_EXPORT_DD_MM_AAAA.csv`. Este programa lo lee de ahi con la llave de
servicio. Las reglas de lectura son las de escaner2_bems.py.

🔴 DEPENDE DE LA MIGRACION 20261010133000_disp_bems_en_sombra.sql DE LA V2 (encargo BE2; se aplica antes de fusionar
   esto): la fila BEMS de `disp_parametros` (sin ella, la pasada no se puede abrir: FK de disp_pasada.proveedor) y la
   politica de subida `escaner2_subir_foto_bems`.

QUE HACE, EN ORDEN:
  0. Sin PASADA con forma de uuid, o sin los secretos de la base: ROJO sin crear ningun cliente de red. Si ya hay una
     disp_pasada con ese id (ese CSV ya se leyo): ROJO sin tocar nada.
  1. abre la pasada en `disp_pasada` CON ESE ID (proveedor BEMS, 'leyendo', run del workflow). Desde ese momento la
     politica del almacen ya no deja subir nada mas a esa carpeta;
  2. lista la carpeta `bems/foto/<pasada>/`: tiene que haber UN solo fichero y llamarse BEMS_EXPORT_DD_MM_AAAA.csv.
     Lo baja (con el reintento de foto_comun) y guarda su md5, sus bytes y la fecha de su nombre
     (`fichero_fecha_max`);
  3. lee con escaner2_bems.convertir: si no se entiende → 'fallida' con recuentos y numeros de fila;
  4. el blindaje de la base, antes de subir nada: articulos distintos por debajo de `disp_parametros.crudo_minimo` o
     disponibles por debajo de `disponibles_minimo` → 'rechazada_vaciado' (un CSV exportado con filtros);
  5. «AL DIA» POR CONTENIDO: si la huella de contenido es la de la ultima pasada aplicada de BEMS → 'rechazada' «al
     día» y VERDE (BEMS_AL_DIA), sin subir nada;
  6. sube las filas a `disp_lectura` en lotes de 500, deja los recuentos y llama a `disp_aplicar_pasada`; lo que vale
     es lo que relee de la base.

🔴 REPO PUBLICO: SOLO estados y recuentos. NUNCA un precio, un EAN, una REF, un titulo, la URL de la base ni el texto
   de un error (al registro, solo su tipo; el detalle, limpio, a `disp_pasada.motivo`, que es privada). Lo que imprime
   foto_comun mientras lista y baja (sus avisos de reintento) se TRAGA y al registro solo va cuantos hubo. Lo comprueba
   test_escaner2_bems_disponibilidad.py ejecutando el programa con un almacen y una base de mentira.
🔑 EN SOMBRA: sin fila en `disp_fuente`; Reponer, el Trackeador y la lista de precios no leen esta foto.
🔒 SOLO TOCA `disp_pasada`, `disp_lectura`, la funcion `disp_aplicar_pasada`, y LEE `disp_parametros` y el almacen.
   No borra ni mueve el CSV.

Uso:  PASADA=<uuid> python escaner2_bems_disponibilidad.py            (la pasada)
      PASADA=<uuid> python escaner2_bems_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import contextlib
import io
import os
import re
import sys
from datetime import datetime, timezone

PROVEEDOR = 'BEMS'
BUCKET = 'escaner2'
CARPETA = 'bems/foto'
LOTE = 500
_RE_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_RE_HEX = re.compile(r'[0-9a-fA-F]{24,}')
_RE_URL = re.compile(r'https?://\S+')
_RE_EAN = re.compile(r'(?<![0-9])[0-9]{8,14}(?![0-9])')
# Lo que el almacen pone solo en una carpeta y no es un fichero de nadie.
_MARCADOR_CARPETA = '.emptyFolderPlaceholder'


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO. `motivo` es SIEMPRE un texto escrito por este programa."""
    print(f"BEMS_NO_EJECUTADA: {motivo}")
    sys.exit(1)


class Rechazo(Exception):
    """La pasada no se aplica: `estado` y un `motivo` escrito por este programa (estados y recuentos), que va al
    registro y a disp_pasada.motivo."""

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


def limpio(texto, secretos=()):
    """El texto de un error sin URLs, sin los secretos, sin cadenas hexadecimales largas y sin nada con forma de EAN."""
    t = str(texto)
    for s in secretos:
        if s:
            t = t.replace(s, '<secreto>')
    return _RE_EAN.sub('<n>', _RE_HEX.sub('<hex>', _RE_URL.sub('<url>', t)))


def leer_pasada_del_entorno():
    """El id de la pasada (input del workflow, por env:), en minusculas, o None si no tiene forma de uuid."""
    p = (os.environ.get('PASADA') or '').strip().lower()
    return p if _RE_UUID.fullmatch(p) else None


def _callado(fn, *a):
    """(resultado, avisos) de fn(*a) con su salida TRAGADA: foto_comun imprime el texto del error en cada reintento, y
    ese texto no sale al registro de un repo publico. Se devuelve cuantas lineas imprimio."""
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
        r = fn(*a)
    return r, len([l for l in salida.getvalue().splitlines() if l.strip()])


def bajar(sb, pid):
    """(nombre, bytes) del UNICO CSV de `bems/foto/<pid>/`. Rechazo 'fallida' si no hay ninguno, hay mas de uno o no se
    llama BEMS_EXPORT_DD_MM_AAAA.csv."""
    import escaner2_bems as eb
    import foto_comun
    carpeta = f'{CARPETA}/{pid}'
    objetos, avisos = _callado(foto_comun.listar_buzon, sb, BUCKET, carpeta)
    nombres = sorted(o.get('name') or '' for o in objetos or [] if (o.get('name') or '') != _MARCADOR_CARPETA)
    if avisos:
        print(f">>> Storage: {avisos} línea(s) de aviso de reintento al listar (su texto no sale aquí).", flush=True)
    if len(nombres) != 1:
        raise Rechazo('fallida', f'la carpeta del almacén tiene {len(nombres)} fichero(s) y tiene que tener uno: '
                                 f'el CSV que subió Fernando')
    nombre = nombres[0]
    try:
        eb.fecha_del_nombre(nombre)
    except eb.LecturaInvalida as ex:
        raise Rechazo('fallida', str(ex)) from None
    contenido, avisos = _callado(foto_comun.descargar_buzon, sb, BUCKET, f'{carpeta}/{nombre}')
    if avisos:
        print(f">>> Storage: {avisos} línea(s) de aviso de reintento al bajar (su texto no sale aquí).", flush=True)
    return nombre, contenido


def _cerrar(sb, pasada, estado, motivo, extra=None):
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    datos = dict(extra or {}, estado=estado, motivo=motivo[:1000], terminada_en=_ahora())
    sb.table('disp_pasada').update(datos).eq('id', pasada).eq('estado', 'leyendo').execute()


def _minimo(par, col):
    v = par.get(col)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise Rechazo('fallida', f'sin mínimo: disp_parametros no da un {col} válido para BEMS; no se lee nada')
    return v


def pasada(sb, pid, run_id):
    """La pasada entera. Devuelve el codigo de salida del programa."""
    import escaner2_bems as eb

    ya = sb.table('disp_pasada').select('id, estado').eq('id', pid).execute().data or []
    if ya:
        print(f"BEMS_NO_EJECUTADA: la pasada {pid} ya existe (estado «{ya[0].get('estado')}»): ese CSV ya se leyó. "
              f"Para otra foto, otra subida.", flush=True)
        return 1
    abrir = {'id': pid, 'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(run_id) if run_id.isdigit() else None}
    sb.table('disp_pasada').insert(abrir).execute()
    print(f">>> Pasada de disponibilidad de BEMS {pid} abierta (leyendo).", flush=True)
    rec = None
    try:
        par = (sb.table('disp_parametros').select('crudo_minimo, disponibles_minimo').eq('proveedor', PROVEEDOR)
                 .execute().data or [{}])[0]
        minimo, minimo_disp = _minimo(par, 'crudo_minimo'), _minimo(par, 'disponibles_minimo')
        ult = (sb.table('disp_pasada').select('id, huella_contenido').eq('proveedor', PROVEEDOR).eq('estado', 'aplicada')
                 .order('creada_en', desc=True).limit(1).execute().data or [{}])

        nombre, contenido = bajar(sb, pid)
        md5, n_bytes = eb.huella_fichero(contenido)
        fecha = eb.fecha_del_nombre(nombre)
        sb.table('disp_pasada').update({'fichero_md5': md5, 'fichero_bytes': n_bytes,
                                        'fichero_fecha_max': fecha.isoformat() + 'T00:00:00'}).eq('id', pid).execute()
        print(f">>> Fichero bajado del almacén: {n_bytes} bytes, exportado el {fecha:%d-%m-%Y}.", flush=True)

        try:
            lectura, c = eb.convertir(contenido, nombre)
        except eb.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        n = c['n_leidas']
        rec = {'n_declarado': n, 'n_crudo': c['n_crudo'], 'n_declarado_precios': n, 'n_precios': n,
               'n_declarado_disponibilidades': n, 'n_disponibilidades': n, 'n_sin_gtin': 0,
               'n_duplicados': c['n_duplicados'], 'n_duplicados_precios': 0, 'n_duplicados_disponibilidades': 0,
               'huella_contenido': c['huella_contenido']}
        pm = c['por_marca']
        print(f">>> Leídas {n} de {c['n_crudo']} filas ({c['n_duplicados']} repetidas idénticas, fuera) · "
              f"{c['columnas']} columnas · disponibles {c['n_disponibles']} (en el techo de 100: {c['n_stock_techo']}), "
              f"sin stock {c['n_agotados']} · sin dato de stock {c['n_sin_dato_disponibilidad']}, de precio "
              f"{c['n_sin_dato_precio']} · EAN de forma rara {c['n_ean_forma_rara']} (vacíos {c['n_ean_vacio']}; con "
              f"stock {c['n_ean_forma_rara_disponibles']}) · con EAN ASSOC {c['n_ean_assoc']} · parecen chase suelto "
              f"{c['n_parece_chase']} (entran como figura) · sin fabricante con stock {c['n_sin_marca_disponibles']} · "
              f"Funko {pm['funko']['filas']} (disponibles {pm['funko']['disponibles']}) · Bandai Model Kit "
              f"{pm['bandai_model_kit']['filas']} (disponibles {pm['bandai_model_kit']['disponibles']}) · Pyramid "
              f"{pm['pyramid']['filas']} (disponibles {pm['pyramid']['disponibles']})", flush=True)
        if n < minimo:
            raise Rechazo('rechazada_vaciado', f'vaciado: {n} artículos distintos en el CSV, por debajo del mínimo '
                                               f'{minimo} (¿exportado con filtros? Disponibilidad y Catálogo, «Todos»)')
        if c['n_disponibles'] < minimo_disp:
            raise Rechazo('rechazada_vaciado', f"vaciado: {c['n_disponibles']} con stock, por debajo del mínimo "
                                               f"{minimo_disp}")
        if ult[0].get('huella_contenido') == c['huella_contenido']:
            raise AlDia(ult[0].get('id'))
        print(">>> Contenido nuevo (la huella no es la de la última pasada aplicada): se sube.", flush=True)

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
            print(f"BEMS_AL_DIA: el contenido es el de la pasada aplicada {ex.pasada_aplicada}; nada nuevo.", flush=True)
            return 0
        print(f"BEMS_NO_APLICADA: pasada {pid} {ex.estado}: {ex.motivo}", flush=True)
        return 1
    except Exception as ex:
        # 🔴 REPO PÚBLICO: el texto de un error puede llevar una URL o una fila de la base.
        motivo_log = f'error inesperado ({type(ex).__name__}); el detalle queda en disp_pasada.motivo'
        try:
            _cerrar(sb, pid, 'fallida', limpio(f'{type(ex).__name__}: {ex}', (os.environ.get('SUPABASE_SERVICE_KEY'),)),
                    rec)
        except Exception as ex2:
            motivo_log += f'; tampoco se ha podido cerrar la pasada ({type(ex2).__name__})'
        print(f"BEMS_NO_APLICADA: pasada {pid} fallida: {motivo_log}", flush=True)
        return 1

    fila = sb.table('disp_pasada').select('*').eq('id', pid).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila.get(k)}' for k in (
        'estado', 'primera', 'caida_aceptada', 'n_crudo', 'n_duplicados', 'n_leidas', 'n_disponibles', 'n_agotados',
        'n_sin_dato_precio', 'n_entran', 'n_vuelven', 'n_salen', 'n_a_disponible', 'n_a_agotado', 'n_cambio_precio',
        'n_ausentes', 'n_en_catalogo', 'n_disponibles_estado')), flush=True)
    if fila.get('estado') != 'aplicada':
        # El motivo de la base lo escribe disp_aplicar_pasada con recuentos; aun asi, limpio.
        print(f"BEMS_NO_APLICADA: pasada {pid} {fila.get('estado')}: {limpio(fila.get('motivo'))}", flush=True)
        return 1
    print(f">>> PASADA APLICADA: {fila.get('n_en_catalogo')} artículos de BEMS en el catálogo, "
          f"{fila.get('n_disponibles_estado')} con stock.", flush=True)
    if fila.get('caida_aceptada'):
        print(f"CAIDA_ACEPTADA: la pasada {pid} se ha aplicado como NUEVA REFERENCIA tras varios rechazos estables por "
              f"el freno del 90 %: hay que mirar si el catálogo de BEMS ha caído de verdad.", flush=True)
        return 1
    return 0


def rescatar(sb, pid):
    """Si el run muere a medias, SOLO esta pasada (la del input), de BEMS, y solo si sigue leyendo, queda 'fallida'."""
    res = (sb.table('disp_pasada').select('id').eq('id', pid).eq('proveedor', PROVEEDOR).eq('estado', 'leyendo')
             .execute())
    for f in res.data or []:
        _cerrar(sb, f['id'], 'fallida', 'el run terminó sin cerrar la pasada (tope de tiempo, cancelación o caída); '
                                        'mira su log en Actions')
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de BEMS pasan de 'leyendo' a 'fallida'.")


def principal(argv):
    rescate = argv == ['--rescate']
    if argv not in ([], ['--rescate']):
        abortar('uso: PASADA=<uuid> escaner2_bems_disponibilidad.py [--rescate]')
    # 🔒 LAS GUARDAS, ANTES DE CUALQUIER CLIENTE DE RED.
    pid = leer_pasada_del_entorno()
    if pid is None:
        abortar('falta PASADA o no tiene forma de uuid (el id de la carpeta bems/foto/<pasada>/); no se abre nada')
    if not (os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_KEY')):
        abortar('faltan SUPABASE_URL/SUPABASE_SERVICE_KEY (secretos del repo); no se abre ninguna pasada')
    run_id = os.environ.get('GITHUB_RUN_ID') or ''
    from supabase import create_client
    sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
    if rescate:
        try:
            rescatar(sb, pid)
        except Exception as ex:
            abortar(f'el rescate ha fallado ({type(ex).__name__})')
        return 0
    return pasada(sb, pid, run_id)


if __name__ == '__main__':
    try:
        codigo = principal(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar una fila de la base
        print(f"BEMS_NO_EJECUTADA: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
