#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# MOLOKA - CENTINELA DEL PROVEEDOR MUDO
# ------------------------------------------------------------
# QUE VIGILA: la ULTIMA escritura de cada director en `escaner_memoria`. Si un
# proveedor lleva mas horas que su umbral sin escribir, avisa por Telegram y el
# run sale en ROJO.
#
# POR QUE EXISTE. El 9-sep-2026 por la manana los cuatro directores se quedaron
# sin poder leer `productos` y empezaron a morir en el arranque. DBLine dejo de
# escribir el 9-sep a las 10:31 UTC y OcioStock a las 15:01; no se supo hasta el
# 10-sep por la tarde. DOS DIAS. Nadie avisa cuando un proveedor se calla: el run
# sale rojo en Actions, si, pero un rojo en Actions no llega a donde esta
# Fernando, y "Que reponer" y el trackeador siguen ensenando el catalogo de
# anteayer con toda la cara de estar al dia.
#
# 🔴 SE MIRA LA TABLA, NO EL COLOR DEL RUN. Un run verde que no ha escrito nada
#    es exactamente el fallo que se viene a cazar: la unica cifra que no opina es
#    la fecha que hay en `escaner_memoria`.
#
# Variables de entorno: SUPABASE_URL, SUPABASE_SERVICE_KEY, TELEGRAM_TOKEN,
# TELEGRAM_CHAT_ID.
# ============================================================

import os
import sys
from datetime import datetime, timedelta, timezone

# ============================================================
# LOS HORARIOS, MEDIDOS -- no supuestos
# ------------------------------------------------------------
# Medido el 10-sep-2026 en produccion sobre `escaner_resultados` (28 dias,
# 11-ago a 7-sep, antes del apagon), que es la PELICULA: una fila por pasada.
# 🔴 NO se mide la cadencia en `escaner_memoria`: es un MAESTRO y se sobrescribe
#    fila a fila, asi que las pasadas viejas desaparecen y salen 49 donde hubo
#    93. Para lo que SI vale `escaner_memoria` es para el MAXIMO, que es lo que
#    este centinela mira: la ultima vez que ese proveedor toco la tabla.
#
# LO QUE SALIO. Los tres proveedores de fichero NO trabajan los domingos (cero
# pasadas en cuatro domingos seguidos); TCG si. De ahi que el hueco normal mas
# largo de DBLine sean 44 h -- el sabado por la manana al lunes por la manana --
# sin que pase nada raro.
#
#   proveedor  | franja diaria (UTC)  | pasadas | hueco mayor | descontando | X
#              |                      |  al dia |   (bruto)   |  el domingo |
#   -----------+----------------------+---------+-------------+-------------+----
#   TCG        | 06-16, todos los dias|   ~6    |   18,00 h   |   18,00 h   | 22
#   DBLINE     | 06-11, L a S         |   ~4    |   44,00 h   |   23,00 h   | 26
#   HEO        | 05-13, L a S         |   ~4    |   40,13 h   |   22,03 h   | 26
#   OCIOSTOCK  | 07-15, L a S         |   ~5    |   40,00 h   |   18,00 h   | 22
#
# Con esas cuatro X, en los 28 dias medidos NO habria saltado ni un aviso falso:
# ningun hueco descontado llego a la X de su proveedor (DBLine tuvo 2 por encima
# de 22 h y ninguno de 24; HEO, 1; OcioStock y TCG, ninguno de mas de 18).
#
# 🔑 POR ESO SE DESCUENTA EL DOMINGO, y no es un adorno. Con el hueco BRUTO, el
#    umbral de DBLine tendria que ser 50 h para no dar un falso aviso cada lunes
#    -- o sea, exactamente los dos dias de silencio que costo el apagon del
#    9-sep, que es lo que se viene a evitar. Descontando las horas de domingo, el
#    mismo sabado-a-lunes son 23 h y la X puede bajar a 26.
#
# X = hueco mayor medido (descontando domingo) + un margen de 3-4 h. El margen no
# es "por si acaso": es para que un retraso del cron de GitHub -- que puede irse
# 15-20 min -- o una pasada que empiece tarde no disparen el aviso.
#
# 🔬 LO QUE ESTO HABRIA HECHO CON EL APAGON DEL 9-sep. DBLine escribio por ultima
#    vez el 9 a las 10:31 UTC (miercoles, sin domingo por medio): pasa de 26 h el
#    10 a las 12:31, y la pasada del centinela de las 14:00 UTC lo habria contado
#    y avisado. Se supo por la tarde del dia 10. No es inmediato -- ni puede
#    serlo: DBLine se calla 23 h de por si entre el sabado y el lunes --, pero
#    son horas en vez de dos dias.
HORARIOS = {
    'TCG':       {'umbral_h': 22, 'descansa_domingo': False,
                  'franja': '06-16 UTC, todos los dias', 'medido_h': 18.00},
    'DBLINE':    {'umbral_h': 26, 'descansa_domingo': True,
                  'franja': '06-11 UTC, L a S', 'medido_h': 23.00},
    'HEO':       {'umbral_h': 26, 'descansa_domingo': True,
                  'franja': '05-13 UTC, L a S', 'medido_h': 22.03},
    'OCIOSTOCK': {'umbral_h': 22, 'descansa_domingo': True,
                  'franja': '07-15 UTC, L a S', 'medido_h': 18.00},
}


# ============================================================
# LAS TRES DECISIONES, COMO FUNCIONES PURAS
# ------------------------------------------------------------
# No tocan red, ni reloj, ni globales: se les pasa todo. Tienen banco --
# test_centinela_mudo.py las saca de ESTE fichero con `ast` (por estructura, no
# por texto) y las EJECUTA con las fechas del apagon de verdad.
# ============================================================

def horas_en_domingo(desde, hasta):
    """Cuantas de las horas del intervalo [desde, hasta) caen en domingo (UTC).

    Se recorre tramo a tramo por dias, no hora a hora: asi un hueco de tres
    semanas se cuenta igual de bien y sin dar vueltas."""
    if hasta <= desde:
        return 0.0
    total = 0.0
    tramo_ini = desde
    while tramo_ini < hasta:
        siguiente_dia = (tramo_ini + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        tramo_fin = min(siguiente_dia, hasta)
        if tramo_ini.weekday() == 6:                    # 6 = domingo
            total += (tramo_fin - tramo_ini).total_seconds() / 3600.0
        tramo_ini = tramo_fin
    return total


def horas_de_silencio(ultima, ahora, descansa_domingo):
    """Horas que lleva callado un proveedor, en SU calendario.

    Al que no trabaja los domingos no se le cuentan las horas del domingo: si se
    le contaran, el umbral tendria que subir a 50 h para aguantar el
    sabado-a-lunes, y con 50 h de margen un apagon de verdad se pasa dos dias sin
    que nadie lo note. Que es lo que paso."""
    if ahora <= ultima:
        return 0.0
    brutas = (ahora - ultima).total_seconds() / 3600.0
    if not descansa_domingo:
        return brutas
    return max(brutas - horas_en_domingo(ultima, ahora), 0.0)


def esta_mudo(horas, umbral_h):
    """Un proveedor del que no se sabe NADA (`horas` a None: nunca ha escrito, o
    no se ha podido leer) cuenta como mudo. No saber no es estar bien."""
    if horas is None:
        return True
    return horas > umbral_h


# ============================================================
# EL CENTINELA
# ============================================================
def main():
    # 🔒 La misma regla que el escaner desde el 10-sep-2026: la llave de
    #    servicio, o no se corre. Un centinela que lee con la anonima puede
    #    recibir 200 con cero filas y declarar mudos a los cuatro -- o, peor, no
    #    ver la tabla y callarse.
    llave = os.environ.get('SUPABASE_SERVICE_KEY')
    if not llave:
        print('CENTINELA_NO_EJECUTADO: sin llave de servicio')
        return 1

    from supabase import create_client
    sb = create_client(os.environ['SUPABASE_URL'], llave)

    ahora = datetime.now(timezone.utc)
    print('CENTINELA escaner | %s UTC' % ahora.strftime('%Y-%m-%d %H:%M'))

    filas, fallo_lectura = [], False
    for proveedor in sorted(HORARIOS):
        cfg = HORARIOS[proveedor]
        ultima, motivo = None, None
        try:
            res = (sb.table('escaner_memoria')
                     .select('fecha')
                     .eq('proveedor', proveedor)
                     .order('fecha', desc=True)
                     .limit(1).execute())
            if res.data:
                ultima = datetime.fromisoformat(str(res.data[0]['fecha']).replace('Z', '+00:00'))
            else:
                motivo = 'ni una fila en escaner_memoria'
        except Exception as ex:
            motivo = 'no se pudo leer: %s' % ex
            fallo_lectura = True

        horas = None if ultima is None else horas_de_silencio(
            ultima, ahora, cfg['descansa_domingo'])
        brutas = None if ultima is None else (ahora - ultima).total_seconds() / 3600.0
        filas.append({'proveedor': proveedor, 'ultima': ultima, 'horas': horas,
                      'brutas': brutas, 'umbral': cfg['umbral_h'], 'motivo': motivo,
                      'mudo': esta_mudo(horas, cfg['umbral_h']), 'franja': cfg['franja']})

    # 🔴 LOS CUATRO SIEMPRE AL LOG, hablen o callen. Misma disciplina que el
    #    blindaje anti-vaciado del escaner: un centinela que solo escribe cuando
    #    salta no se puede auditar -- el dia que calla no se distingue "estan
    #    todos al dia" de "no llego a mirar".
    for f in filas:
        if f['ultima'] is None:
            print('  %-10s SIN DATO (%s) | umbral %d h -> MUDO'
                  % (f['proveedor'], f['motivo'], f['umbral']))
        else:
            print('  %-10s ultima %s UTC | silencio %5.1f h (bruto %5.1f) | umbral %d h -> %s'
                  % (f['proveedor'], f['ultima'].strftime('%Y-%m-%d %H:%M'),
                     f['horas'], f['brutas'], f['umbral'],
                     'MUDO' if f['mudo'] else 'al dia'))

    mudos = [f for f in filas if f['mudo']]
    if not mudos:
        print('CENTINELA OK: los %d directores han escrito dentro de su plazo.' % len(filas))
        return 1 if fallo_lectura else 0

    lineas = ['🔴 <b>Escaner: %d proveedor(es) callado(s)</b>' % len(mudos)]
    for f in mudos:
        if f['ultima'] is None:
            lineas.append('• <b>%s</b> — sin dato (%s)' % (f['proveedor'], f['motivo']))
        else:
            lineas.append('• <b>%s</b> — última escritura %s UTC, hace %.0f h '
                          '(su plazo son %d h; su horario, %s)'
                          % (f['proveedor'], f['ultima'].strftime('%d-%m %H:%M'),
                             f['horas'], f['umbral'], f['franja']))
    lineas.append('Mira el run del director en Actions: si sale verde y la fecha no se '
                  'mueve, es que escribe en el vacío.')
    texto = '\n'.join(lineas)
    print('CENTINELA_MUDO: ' + ', '.join(f['proveedor'] for f in mudos))

    tg_token = os.environ.get('TELEGRAM_TOKEN')
    tg_chat = os.environ.get('TELEGRAM_CHAT_ID')
    if tg_token and tg_chat:
        try:
            import requests
            requests.post('https://api.telegram.org/bot%s/sendMessage' % tg_token,
                          data={'chat_id': tg_chat, 'text': texto, 'parse_mode': 'HTML',
                                'disable_web_page_preview': 'true'}, timeout=20)
            print('>>> Telegram enviado.')
        except Exception as ex:
            print('AVISO Telegram (no se envio):', ex)
    else:
        print('>>> Telegram: sin claves en este paso -> no se envia.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
