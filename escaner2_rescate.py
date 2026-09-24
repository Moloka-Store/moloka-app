#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL RESCATE: si el run muere a medias, su fila no se queda colgada.

Lo corren los dos workflows del escaner 2 como ULTIMO paso, solo si el run ha fallado o se ha
cancelado (`if: failure() || cancelled()`): el tope de tiempo, una cancelacion a mano o un
fallo que el propio programa no llego a apuntar dejan la pasada en 'descargando' o el cruce en
'cruzando' PARA SIEMPRE, y la pantalla de la v2 se quedaria esperando sin poder volver a barrer.

Marca como 'fallida' SOLO las filas de ESTE run (run_id = GITHUB_RUN_ID) que sigan a medias.
Lo demas no lo toca: ni filas de otros runs, ni las que ya cerraron (lista, esperando_csv,
fallida).

Uso:  python escaner2_rescate.py pasada|cruce
"""
import os
import sys
from datetime import datetime, timezone

QUE = {'pasada': ('escaner2_pasada', 'descargando', 'terminada_en'),
       'cruce': ('escaner2_cruce', 'cruzando', 'terminado_en')}


def abortar(motivo):
    print(f"ESCANER2_NO_EJECUTADO: {motivo}")
    sys.exit(1)


if len(sys.argv) != 2 or sys.argv[1] not in QUE:
    abortar('uso: escaner2_rescate.py pasada|cruce')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
_run = os.environ.get('GITHUB_RUN_ID') or ''
if not _run.isdigit():
    abortar('sin GITHUB_RUN_ID: no se sabe qué filas son de este run')

from supabase import create_client  # noqa: E402

tabla, a_medias, campo_fin = QUE[sys.argv[1]]
sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)
res = (sb.table(tabla).update({
    'estado': 'fallida', campo_fin: datetime.now(timezone.utc).isoformat(),
    'motivo_fallo': 'el run %s terminó sin cerrar esta fila (tope de tiempo, cancelación o caída); '
                    'mira su log en Actions' % _run,
}).eq('run_id', int(_run)).eq('estado', a_medias).execute())
print(f">>> RESCATE {tabla}: {len(res.data or [])} fila(s) de este run pasan de '{a_medias}' a 'fallida'.")
