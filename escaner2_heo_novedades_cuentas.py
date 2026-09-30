# -*- coding: utf-8 -*-
"""ESCANER 2 · NOVEDADES DE FUNKO: LAS CUENTAS SUELTAS DE Y 27 (encargo V, 30-sep-2026).

Lo lanza escaner2-heo-novedades-cuentas.yml (workflow_dispatch; lo despertara cron-job.org a y 27, cuando lo creen
Fernando y Cowork). Hace SOLO dos cosas, con escaner2_novedades.solo_cuentas:
  1. LA CUENTA de las novedades «lista» (el cartero de novedades, a su hora, ya les dio precio y tarifa de Amazon), con
     el mismo codigo que el Escaneo PRO (escaner2_motor);
  2. EL EXCEL de las que ha valorado, si al menos una sale COMPRAR: al bucket escaner2 y a nov_excel (lo que lee la
     biblioteca de escaneos de la v2).
Sin Keepa, sin bajar HEO y sin tocar nov_pasada: la pasada en punto sigue haciendo sus cuentas al empezar y cuadra la
foto de todas las novedades. Asi una novedad a la que el cartero da precio a y 20 se valora a y 27, y no una hora
despues.

🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: lee `productos` desatendido (el IVA de la ficha; ver
   test_escaner_llave_servicio.py, donde este programa esta en la lista PROGRAMAS).
🔒 Ni escaner_resultados, ni el buzon `informes`, ni ninguna llave de disparo.

Uso:  python escaner2_heo_novedades_cuentas.py
"""
import os
import sys


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"NOVEDADES_CUENTAS_NO_EJECUTADAS: {motivo}")
    sys.exit(1)


if sys.argv[1:]:
    abortar('uso: escaner2_heo_novedades_cuentas.py (sin argumentos)')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')

from supabase import create_client  # noqa: E402

import escaner2_novedades as nv  # noqa: E402

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


def main():
    ok, res = nv.solo_cuentas(sb, run_id=os.environ.get('GITHUB_RUN_ID'))
    if not ok:
        print(f"NOVEDADES_CUENTAS_EN_ROJO: {res.get('avisos') or res}")
        sys.exit(1)


if __name__ == '__main__':
    main()
