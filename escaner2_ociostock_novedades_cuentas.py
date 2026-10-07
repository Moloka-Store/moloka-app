# -*- coding: utf-8 -*-
"""ESCANER 2 · NOVEDADES DE FUNKO DE OCIOSTOCK: LAS CUENTAS SUELTAS (encargo OC4, 07-oct-2026).

El molde: escaner2_heo_novedades_cuentas.py, con proveedor='OCIOSTOCK'. Lo lanza escaner2-ociostock-novedades-cuentas.yml
(workflow_dispatch; lo despertara cron-job.org a y 45 de 09 a 13, cuando lo creen Fernando y Cowork: despues de los
reintentos del cartero de la v2 de y 20, que pide a Amazon lo de HEO y lo de OcioStock en la misma corrida). Con
escaner2_novedades.solo_cuentas:
  1. LA CUENTA de las novedades de OcioStock «lista» (el cartero ya les dio precio y tarifa de Amazon), con el mismo
     codigo que el Escaneo PRO (escaner2_motor) y el PA de OcioStock (el precio con escalon × 0,99); los paises en que
     Amazon fallo, con el RESPALDO de Keepa del momento (la misma llave, saldo y reserva que HEO);
  2. EL EXCEL de las que ha valorado, si al menos una sale COMPRAR: al bucket escaner2 (ociostock/novedades/) y a
     nov_excel (lo que lee la biblioteca de escaneos de la v2), con «Uds. escalón» y «Precio unidad» al final;
  3. EL TELEGRAM, «Novedades OcioStock Funko», como el de HEO.
Sin las ventas de Keepa, sin bajar el fichero de OcioStock y sin tocar nov_pasada: la pasada de las 09:00 sigue
haciendo sus cuentas al empezar.

🆕 A MANO, LAS NOVEDADES DE UNA PASADA (NOVEDADES_PASADA, la entrada `pasada` del workflow): en vez de las cuentas, la
   seleccion y la valoracion de ESA pasada aplicada de OcioStock (escaner2_novedades.novedades_tras_la_pasada, lo
   mismo que hace la foto tras aplicar). Para rehacer una pasada cuya seleccion fallo, o la primera vez. Un id que
   no es un uuid, no se corre.

🔴 REPO PUBLICO: el registro, DISCRETO (escaner2_novedades.imprimir_discreto): ni EAN, ni ASIN, ni el texto de un error.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: lee `productos` desatendido (el IVA de la ficha; ver
   test_escaner_llave_servicio.py, donde este programa esta en la lista PROGRAMAS).
🔒 Ni escaner_resultados, ni el buzon `informes`, ni ninguna llave de disparo. KEEPA_API_KEY (el respaldo) y
   TELEGRAM_TOKEN/TELEGRAM_CHAT_ID (el aviso) llegan solo a este paso; sin ellas, no se piden ni se mandan.

Uso:  python escaner2_ociostock_novedades_cuentas.py
"""
import os
import re
import sys


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"NOVEDADES_CUENTAS_NO_EJECUTADAS: {motivo}")
    sys.exit(1)


if sys.argv[1:]:
    abortar('uso: escaner2_ociostock_novedades_cuentas.py (sin argumentos; la pasada, si acaso, en NOVEDADES_PASADA)')
PASADA = (os.environ.get('NOVEDADES_PASADA') or '').strip().lower()
if PASADA and not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', PASADA):
    abortar('NOVEDADES_PASADA no es el id de una pasada (uuid)')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')

from supabase import create_client  # noqa: E402

import escaner2_novedades as nv  # noqa: E402

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


def main():
    if PASADA:
        ok, seleccion = nv.novedades_tras_la_pasada(sb, PASADA, 'OCIOSTOCK', keepa_llave=os.environ.get('KEEPA_API_KEY'),
                                                    imprimir=nv.imprimir_discreto, run_id=os.environ.get('GITHUB_RUN_ID'))
        if not ok or (seleccion or {}).get('marca_parecida'):
            print(f"NOVEDADES_PASADA_EN_ROJO: la pasada {PASADA}: las novedades no han salido bien o el vigía de la marca "
                  f"ha saltado (el detalle, en nov_pasada de esa pasada)")
            sys.exit(1)
        return
    ok, res = nv.solo_cuentas(sb, run_id=os.environ.get('GITHUB_RUN_ID'), keepa_llave=os.environ.get('KEEPA_API_KEY'),
                              imprimir=nv.imprimir_discreto, proveedor='OCIOSTOCK')
    if not ok:
        # 🔴 Repo publico: cuantos avisos y el estado, no su texto (puede llevar una fila de la base).
        print(f"NOVEDADES_CUENTAS_EN_ROJO: estado {res.get('estado')} · {len(res.get('avisos') or [])} aviso(s); "
              f"el detalle no sale en el registro público")
        sys.exit(1)


if __name__ == '__main__':
    main()
