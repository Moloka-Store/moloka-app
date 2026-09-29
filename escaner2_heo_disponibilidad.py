#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE HEO (encargo E, tramo 3, pieza 1, 29-sep-2026).

La lanza escaner2-heo-disponibilidad.yml. HOY A MANO: el reloj (cron-job.org, cada hora) lo
encienden Fernando y Cowork cuando esto este fusionado y la migracion de la v2 aplicada.

QUE HACE, EN ORDEN:
  1. abre una pasada en `disp_pasada` (proveedor HEO, estado 'leyendo', con el id del run);
  2. baja el catalogo con `descargar_catalogo_heo(con_chase=True)`, la MISMA funcion que el barrido y
     el director (copia literal en escaner2_heredado_descarga.py), y saca de su log, por endpoint, lo
     que HEO declara y lo que llego, y lo que tiro sin GTIN. 🔴 SI UNO DE LOS TRES ENDPOINTS (productos,
     precios, disponibilidades) NO LLEGO ENTERO, la pasada se cierra 'fallida' SIN llamar a la base:
     la descarga corta en silencio, y sin disponibilidades todo saldria agotado (revision de Cowork,
     29-sep-2026). La base lo vuelve a comprobar por su cuenta;
  3. convierte cada producto CON codigo de barras en una fila con las reglas del escaner 2
     (`escaner2_disponibilidad.construir_disponibilidad`): TODAS las marcas, disponibles y NO. Los sin
     GTIN (~1.155) los quita la descarga heredada y solo se cuentan;
  4. sube las filas a `disp_lectura` en lotes y deja en la pasada sus recuentos;
  5. llama a `disp_aplicar_pasada`, la funcion de la base que, de una vez: pasa el blindaje
     anti-vaciado, apunta los cambios contra el estado de antes, marca lo que falta y cuadra. Si la
     rechaza, disp_estado NO se toca y el run sale en ROJO con el motivo;
  6. relee la pasada en la base y la imprime: lo que vale es lo que hay alli, no lo que dice esto.

🔒 NO TOCA NADA DEL ESCANER VIEJO NI DEL ESCANER 2: ni `escaner_memoria`, ni `escaner_resultados`, ni
   `reglas_director`, ni `escaner2_*`, ni `productos`. Solo `disp_pasada`, `disp_lectura` y la funcion
   `disp_aplicar_pasada` (lo comprueba test_escaner2_disponibilidad.py sobre el propio fichero).
   Cero tokens de Keepa y cero llamadas a Amazon.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: escribe en tablas cerradas; sin ella aborta antes de nacer
   ningun cliente de red.

Uso:  python escaner2_heo_disponibilidad.py            (la pasada)
      python escaner2_heo_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

PROVEEDOR = 'HEO'
LOTE = 500


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"DISPONIBILIDAD_NO_EJECUTADA: {motivo}")
    sys.exit(1)


RESCATE = sys.argv[1:] == ['--rescate']
if sys.argv[1:] not in ([], ['--rescate']):
    abortar('uso: escaner2_heo_disponibilidad.py [--rescate]')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
if not RESCATE and not (os.environ.get('HEO_USER') and os.environ.get('HEO_PASS')):
    abortar('sin credenciales de HEO (HEO_USER y HEO_PASS)')
RUN_ID = os.environ.get('GITHUB_RUN_ID') or ''

from supabase import create_client  # noqa: E402

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


class DescargaCortada(RuntimeError):
    """Uno de los tres endpoints de HEO no llego entero: la pasada no se aplica."""


class _Eco(io.TextIOBase):
    """Deja pasar lo que se imprime Y se lo guarda: descargar_catalogo_heo dice lo que HEO declara, lo
    que se bajo y lo que tiro sin GTIN SOLO en su log (la misma pieza que el barrido)."""

    def __init__(self, destino):
        self.destino, self.trozos = destino, []

    def write(self, s):
        self.destino.write(s)
        self.trozos.append(s)
        return len(s)

    def flush(self):
        self.destino.flush()


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _cerrar_fallida(pasada, motivo):
    """La pasada queda 'fallida' con su motivo y sin nada leido colgando (disp_lectura es de paso)."""
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    (sb.table('disp_pasada').update({'estado': 'fallida', 'motivo': motivo[:1000], 'terminada_en': _ahora()})
       .eq('id', pasada).eq('estado', 'leyendo').execute())


def rescatar():
    """🔴 Si el run muere a medias (tope de tiempo, cancelacion), su pasada no se queda 'leyendo' para
    siempre: SOLO la de ESTE run, y solo si sigue leyendo."""
    if not RUN_ID.isdigit():
        abortar('sin GITHUB_RUN_ID: no se sabe qué pasada es de este run')
    res = (sb.table('disp_pasada').select('id').eq('run_id', int(RUN_ID)).eq('estado', 'leyendo').execute())
    for fila in res.data or []:
        _cerrar_fallida(fila['id'], 'el run %s terminó sin cerrar la pasada (tope de tiempo, cancelación o '
                                    'caída); mira su log en Actions' % RUN_ID)
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de este run pasan de 'leyendo' a 'fallida'.")


def main():
    import escaner2_motor as e2
    import escaner2_disponibilidad as dp

    abrir = {'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(RUN_ID) if RUN_ID.isdigit() else None}
    pasada = sb.table('disp_pasada').insert(abrir).execute().data[0]['id']
    print(f">>> Pasada de disponibilidad {pasada} abierta (leyendo).", flush=True)
    try:
        # 1 · El catalogo, con la MISMA funcion que el barrido (import tardio: lee HEO_USER al cargar).
        from escaner2_heredado_descarga import descargar_catalogo_heo
        eco = _Eco(sys.stdout)
        with redirect_stdout(eco):
            filas_heo, chase = descargar_catalogo_heo(con_chase=True)
        rec = dp.recuentos_del_log(''.join(eco.trozos))
        # Los recuentos, a la pasada en cuanto se saben: tambien una fallida los necesita.
        sb.table('disp_pasada').update(rec).eq('id', pasada).execute()
        cortada = dp.descarga_cortada(rec)
        if cortada:
            raise DescargaCortada('descarga cortada, no se aplica: ' + ' · '.join(cortada))

        # 2 · Las filas, con las reglas del escaner 2. Todas las marcas, disponibles y no.
        M = e2.cargar_motor()
        filas, cuentas = dp.construir_disponibilidad(filas_heo, chase, M)
        print(f">>> HEO declara {rec['n_declarado']} productos, {rec['n_declarado_precios']} precios y "
              f"{rec['n_declarado_disponibilidades']} disponibilidades · llegaron {rec['n_crudo']}, {rec['n_precios']} y "
              f"{rec['n_disponibilidades']} · sin GTIN {rec['n_sin_gtin']} · "
              f"leídas {cuentas['n_leidas']} (disponibles {cuentas['n_disponibles']}, agotados {cuentas['n_agotados']}) · "
              f"con regla del escáner 2 {cuentas['por_regla']}", flush=True)

        # 3 · Lo leido, a la base, en lotes; y los recuentos en la pasada. La base los contrasta.
        for i in range(0, len(filas), LOTE):
            sb.table('disp_lectura').insert([dict(f, pasada_id=pasada) for f in filas[i:i + LOTE]]).execute()
        (sb.table('disp_pasada').update({
            'n_leidas': cuentas['n_leidas'], 'n_disponibles': cuentas['n_disponibles'],
            'n_agotados': cuentas['n_agotados'],
        }).eq('id', pasada).execute())

        # 4 · La base la aplica (o la rechaza) de una vez.
        resultado = sb.rpc('disp_aplicar_pasada', {'p_pasada': pasada}).execute().data
    except Exception as ex:
        motivo = f'{type(ex).__name__}: {ex}'
        _cerrar_fallida(pasada, motivo)
        abortar(f'pasada {pasada} fallida: {motivo[:500]}')

    # 5 · Lo que vale es lo que hay en la base.
    fila = sb.table('disp_pasada').select('*').eq('id', pasada).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila[k]}' for k in (
        'estado', 'primera', 'n_crudo', 'n_leidas', 'n_disponibles', 'n_agotados', 'n_entran', 'n_vuelven',
        'n_salen', 'n_a_disponible', 'n_a_agotado', 'n_cambio_precio', 'n_ausentes', 'n_en_catalogo',
        'n_disponibles_estado')), flush=True)
    if fila['estado'] != 'aplicada':
        abortar(f"pasada {pasada} {fila['estado']}: {fila.get('motivo')} · la función dijo {resultado}")
    print(f">>> PASADA APLICADA: {fila['n_en_catalogo']} productos de HEO en el catálogo, "
          f"{fila['n_disponibles_estado']} disponibles.", flush=True)


if __name__ == '__main__':
    rescatar() if RESCATE else main()
