#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# MOLOKA - CENTINELA DEL PROVEEDOR MUDO
# ------------------------------------------------------------
# QUE VIGILA: la ULTIMA escritura de cada director en `escaner_memoria`. Si un
# proveedor lleva mas horas que su umbral sin escribir, avisa por Telegram y el
# run sale en ROJO.
#
# CUANDO MIRA: 06:00, 10:00, 14:00 y 18:00 UTC. Cuatro pasadas, ninguna de noche
# -- el porque, y por que el hueco nocturno no retrasa nada, esta en el cron de
# `.github/workflows/centinela-escaner.yml`.
#
# EL AVISO, UNO POR PROVEEDOR Y DIA (10-sep-2026): un mudo lo es durante horas,
# asi que sin freno el movil suena en cada pasada por el mismo silencio. El run
# sigue saliendo ROJO en las cuatro: lo que se silencia es el movil, nunca el
# registro. Y el freno FALLA EN ABIERTO -- ver la marca, mas abajo.
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

import json
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
# 🔬 Y DE AQUI SALE EL RELOJ DEL CENTINELA (06/10/14/18 UTC). La franja en la que
#    cada uno escribe, mas su X, da la ventana en la que su plazo puede vencerse.
#    Las cuatro ventanas caen dentro de 04:00-15:00 UTC, asi que mirar cuatro
#    veces entre las 06:00 y las 18:00 basta, y el hueco de noche no retrasa nada:
#
#      proveedor  | escribe (UTC) |  X   | su plazo vence entre | demora | detectado en
#      -----------+---------------+------+----------------------+--------+-------------
#      TCG        | 06-16         | 22 h |   04:00 y 14:00      |  ≤ 4 h |   ≤ 26 h
#      DBLINE     | 06-11         | 26 h |   08:00 y 13:00      |  ≤ 4 h |   ≤ 30 h
#      HEO        | 05-13         | 26 h |   07:00 y 15:00      |  ≤ 4 h |   ≤ 30 h
#      OCIOSTOCK  | 07-15         | 22 h |   05:00 y 13:00      |  ≤ 4 h |   ≤ 26 h
#
#    Con un domingo por medio la ventana se corre al lunes (el reloj descontado
#    esta parado el domingo entero) y cae entre las 05:00 y las 15:00 UTC del
#    lunes: la misma franja, asi que la demora tampoco cambia.
#    🔒 Esto NO se queda en un comentario: el banco saca la ventana de estas
#       cifras, la cruza con el cron de verdad y exige que la demora no pase de
#       4 h. Si manana se toca una franja, una X o el cron, se pone rojo.
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
# `primera_h`/`ultima_h` son la franja en la que ese proveedor ESCRIBE, en horas
# UTC, y no son adorno: de ellas sale la ventana en la que su plazo puede
# vencerse, y de esa ventana sale a que horas tiene sentido que el centinela
# mire. El banco lo comprueba contra el cron del workflow.
HORARIOS = {
    'TCG':       {'umbral_h': 22, 'descansa_domingo': False, 'medido_h': 18.00,
                  'primera_h': 6, 'ultima_h': 16, 'dias': 'todos los dias'},
    'DBLINE':    {'umbral_h': 26, 'descansa_domingo': True, 'medido_h': 23.00,
                  'primera_h': 6, 'ultima_h': 11, 'dias': 'L a S'},
    'HEO':       {'umbral_h': 26, 'descansa_domingo': True, 'medido_h': 22.03,
                  'primera_h': 5, 'ultima_h': 13, 'dias': 'L a S'},
    'OCIOSTOCK': {'umbral_h': 22, 'descansa_domingo': True, 'medido_h': 18.00,
                  'primera_h': 7, 'ultima_h': 15, 'dias': 'L a S'},
}

# ============================================================
# LA MARCA: UN AVISO POR PROVEEDOR Y DIA
# ------------------------------------------------------------
# El centinela arranca 4 veces al dia. Un proveedor mudo de verdad lo esta
# durante horas, asi que sin freno el movil sonaria en las cuatro por el mismo
# silencio -- y un aviso que suena cuatro veces al dia se aprende a ignorar en
# quince dias, que es la manera mas cara de perder un centinela.
#
# La marca es un JSON en Storage, {proveedor: 'AAAA-MM-DD' del ultimo aviso}. En
# el bucket `informes`, que es donde el escaner ya escribe: ni tabla nueva, ni
# migracion, ni un secreto mas.
#
# 🔴 FALLA EN ABIERTO, Y ESTO NO SE NEGOCIA (condicion de Fernando, 10-sep-2026).
#    Si la marca no se puede leer, se avisa IGUAL. Si no se puede escribir, el
#    aviso puede repetirse hoy, y se prefiere repetir. Un mecanismo hecho para
#    hablar MENOS no puede convertirse en uno que se CALLA cuando algo va mal:
#    esa es exactamente la clase de silencio que costo dos dias el 9-sep
#    (`productos` devolviendo cero filas sin error).
#
# El dia es el UTC. Con el centinela corriendo de 06:00 a 18:00 UTC, ese dia y el
# de Espana son siempre el mismo (06:00 UTC son las 07:00/08:00; 18:00 UTC, las
# 19:00/20:00), asi que no hay que elegir entre dos calendarios.
MARCA_BUCKET = 'informes'
MARCA_RUTA = 'centinela/ultimo_aviso.json'


# ============================================================
# LAS DECISIONES, COMO FUNCIONES PURAS
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


def franja_de(cfg):
    """El horario del proveedor, en texto, para el aviso: '06-11 UTC, L a S'.

    Sale de las MISMAS cifras que usa el banco para comprobar el cron. Si se
    escribiera a mano en un campo aparte, un dia diria una cosa y el calculo
    otra, y el aviso mentiria sobre el horario justo del que se queja."""
    return '%02d-%02d UTC, %s' % (cfg['primera_h'], cfg['ultima_h'], cfg['dias'])


def avisos_de_hoy(marca, hoy, mudos):
    """Reparte los mudos en (los que TOCA avisar, los que ya se avisaron hoy).

    `marca` es {proveedor: 'AAAA-MM-DD' del ultimo aviso} y `mudos`, una lista de
    nombres. Es por PROVEEDOR: que hoy ya se avisara de DBLine no calla a HEO si
    se cae dentro de un rato.

    🔴 FALLA EN ABIERTO: si la marca no se pudo leer, quien llama pasa {} y aqui
    salen TODOS a avisar. Nunca al reves."""
    a_avisar, ya_avisados = [], []
    for proveedor in mudos:
        if marca.get(proveedor) == hoy:
            ya_avisados.append(proveedor)
        else:
            a_avisar.append(proveedor)
    return a_avisar, ya_avisados


def linea_de_aviso(fila):
    """La linea que llega al movil. Empieza por CUANTO lleva callado, no por el
    nombre del estado: con un aviso al dia, saber si acaba de empezar o si lleva
    dos dias es la mitad de la informacion (Fernando, 10-sep-2026).

    Las horas BRUTAS son las que se ven en un reloj y las que uno espera leer.
    Las descontadas son las que se comparan con el plazo, y solo se nombran
    cuando difieren -- si no, la frase seria ruido en el 95% de los avisos y una
    contradiccion aparente en el resto ("lleva 34 h y su plazo son 26, ¿por que
    avisa ahora?")."""
    if fila['ultima'] is None:
        return ('• <b>%s</b> — sin dato (%s). Su plazo son %d h.'
                % (fila['proveedor'], fila['motivo'], fila['umbral']))
    cabeza = ('• <b>%s</b> — lleva %.0f h sin escribir (última: %s UTC). '
              % (fila['proveedor'], fila['brutas'],
                 fila['ultima'].strftime('%Y-%m-%d %H:%M')))
    if fila['brutas'] - fila['horas'] > 0.05:
        plazo = ('%.0f h sin contar los domingos, que es lo que se compara con su plazo '
                 'de %d h. ' % (fila['horas'], fila['umbral']))
    else:
        plazo = 'Su plazo son %d h. ' % fila['umbral']
    return cabeza + plazo + 'Horario: %s.' % fila['franja']


# ============================================================
# LA MARCA EN STORAGE (lo unico de aqui que toca la red aparte de la consulta)
# ============================================================

def leer_marca(sb):
    """Devuelve ({proveedor: 'AAAA-MM-DD'}, se_pudo_leer).

    🔴 FALLA EN ABIERTO: cualquier tropiezo -- que el fichero no exista todavia,
    que Storage no responda, que el JSON este roto -- devuelve marca vacia, y con
    marca vacia se avisa de todos. El coste de equivocarse por este lado es un
    Telegram de mas; por el otro, dos dias de silencio."""
    try:
        crudo = sb.storage.from_(MARCA_BUCKET).download(MARCA_RUTA)
        marca = json.loads(crudo.decode('utf-8'))
        if not isinstance(marca, dict):
            raise ValueError('el JSON de la marca no es un objeto')
        return marca, True
    except Exception as ex:
        print('  AVISO: la marca de avisos no se pudo leer (no existe todavia, o: %s).' % ex)
        print('         Se avisa IGUAL. Callar por un fallo de la marca seria el silencio')
        print('         que este centinela viene a cerrar.')
        return {}, False


def escribir_marca(sb, marca):
    """Guarda la marca. Si falla, el aviso podra repetirse hoy: se prefiere
    repetir a callar, asi que no cambia el resultado del run."""
    try:
        sb.storage.from_(MARCA_BUCKET).upload(
            MARCA_RUTA, json.dumps(marca, indent=1, sort_keys=True).encode('utf-8'),
            {'upsert': 'true', 'content-type': 'application/json'})
        return True
    except Exception as ex:
        print('  AVISO: no se pudo guardar la marca (%s). Consecuencia: hoy puede volver a'
              ' avisar de lo mismo. Se prefiere repetir a callar.' % ex)
        return False


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
                      'mudo': esta_mudo(horas, cfg['umbral_h']), 'franja': franja_de(cfg)})

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

    print('CENTINELA_MUDO: ' + ', '.join(f['proveedor'] for f in mudos))

    # 🔴 EL RUN SALE EN ROJO EN LAS CUATRO, avise o no. Lo que se silencia es el
    #    movil, nunca el registro: un proveedor mudo que se viera VERDE en
    #    Actions el resto del dia seria el mismo silencio con otra cara.
    hoy = ahora.strftime('%Y-%m-%d')
    marca, marca_leida = leer_marca(sb)
    a_avisar, ya_avisados = avisos_de_hoy(marca if marca_leida else {}, hoy,
                                          [f['proveedor'] for f in mudos])
    if ya_avisados:
        print('  ya avisados hoy (no se repite el Telegram): ' + ', '.join(ya_avisados))
    if not a_avisar:
        print('CENTINELA: nada que enviar, de los %d mudos ya se avisó hoy.' % len(mudos))
        return 1

    lineas = ['🔴 <b>Escaner: %d proveedor(es) callado(s)</b>' % len(a_avisar)]
    lineas += [linea_de_aviso(f) for f in mudos if f['proveedor'] in a_avisar]
    lineas.append('Mira el run del director en Actions: si sale verde y la fecha no se '
                  'mueve, es que escribe en el vacío.')
    texto = '\n'.join(lineas)

    tg_token = os.environ.get('TELEGRAM_TOKEN')
    tg_chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not (tg_token and tg_chat):
        print('>>> Telegram: sin claves en este paso -> no se envia (y la marca no se toca).')
        return 1
    try:
        import requests
        requests.post('https://api.telegram.org/bot%s/sendMessage' % tg_token,
                      data={'chat_id': tg_chat, 'text': texto, 'parse_mode': 'HTML',
                            'disable_web_page_preview': 'true'}, timeout=20)
        print('>>> Telegram enviado: ' + ', '.join(a_avisar))
    except Exception as ex:
        # 🔒 La marca NO se toca: si el envio fallo, el aviso no ha llegado, y
        #    apuntarlo como enviado seria callarse el resto del dia.
        print('AVISO Telegram (no se envio, la marca queda intacta):', ex)
        return 1

    for proveedor in a_avisar:
        marca[proveedor] = hoy
    escribir_marca(sb, marca)
    return 1


if __name__ == '__main__':
    sys.exit(main())
