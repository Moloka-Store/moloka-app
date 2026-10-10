#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# MOLOKA - CENTINELA DEL PROVEEDOR MUDO
# ------------------------------------------------------------
# QUE VIGILA: la ULTIMA escritura de cada proveedor. Si uno lleva mas horas que su
# umbral sin escribir, avisa por Telegram y el run sale en ROJO.
#   - TCG (escaner viejo): el MAXIMO de `fecha` en `escaner_memoria`.
#   - HEO y OSMA (escaner 2, desde el 03-oct-2026): la ultima pasada 'aplicada'
#     de `disp_pasada` (`terminada_en`). El director viejo de HEO se apago a
#     proposito el 01-oct y `escaner_memoria` ya no se mueve para HEO ni para OSMA:
#     mirarla daria MUDO para siempre, y mirarla es mirar el sitio equivocado.
#     Cada fila de HORARIOS dice su `fuente`.
#   - OCIOSTOCK (escaner 2, encargo OC5, 07-oct-2026): tambien `disp_pasada`, la
#     foto del catalogo entero. Su director viejo sigue en .github/workflows hasta
#     que se apague, pero lo que leen Reponer y el Trackeador al pulsar el
#     interruptor es la foto: el centinela vigila lo que se lee.
#   - DBLINE (escaner 2, encargo DB6, 10-oct-2026): tambien `disp_pasada`, la foto
#     del catalogo general, el dia que se pulsa su interruptor y se apaga su
#     director viejo (`reglas_director` DBLINE inactivo): su `escaner_memoria` deja
#     de moverse, y mirarla daria MUDO a las 26 h.
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
#   OCIOSTOCK  | 07-15, L a S         |   ~5    |   40,00 h   |   18,00 h   | 22
#   (HEO, OSMA y, desde el 07-oct-2026, OCIOSTOCK y, desde el 10-oct-2026, DBLINE:
#   tabla propia, mas abajo; ya no salen de `escaner_memoria`. Las filas de OCIOSTOCK
#   y DBLINE de aqui son las del escaner viejo.)
#
# Con esas X, en los 28 dias medidos NO habria saltado ni un aviso falso:
# ningun hueco descontado llego a la X de su proveedor (DBLine tuvo 2 por encima
# de 22 h y ninguno de 24; OcioStock y TCG, ninguno de mas de 18).
#
# 🆕 HEO Y OSMA EN EL ESCANER 2 (03-oct-2026). Medido el 03-oct a las 13:3x (Madrid)
#    en `disp_pasada`, estado 'aplicada' -- la PELICULA del escaner 2, una fila por
#    pasada --, y contrastado con `disp_parametros` (el horario que usa la base).
#    🔴 LA PELICULA ES CORTA y hay que decirlo: HEO solo tiene 4,5 dias (desde el
#    29-sep) y OSMA 2 (desde el 01-oct). No son las cuatro semanas del 10-sep: donde
#    el dato no llega, la cifra sale del horario de `disp_parametros` y esta marcada.
#
#    HEO  · 55 'aplicadas' del 29-sep 09:03 UTC al 03-oct 07:05 UTC. Una por hora, a
#           los :05-:06 (terminada_en), de 06:06 a 19:06 UTC (08-21 h Madrid en
#           verano), de lunes a viernes: huecos medidos de 1 h y, de noche (19:06 a
#           06:06), de 10,99 a 11,02 h en cuatro noches. Sabado 03-oct: 06:06 y 07:06
#           UTC (08 y 09 h Madrid), como dice `disp_parametros.horario_finde`.
#           LO QUE NO ESTA MEDIDO: las noches del sabado y del domingo (el primer
#           domingo es el 04-oct). Salen del horario: ultima pasada del fin de
#           semana a las 09:06 Madrid, primera del dia siguiente a las 08:06 = 23 h.
#           HEO SI trabaja el domingo (a diferencia del escaner viejo, que lo
#           descansaba): NO se descuenta ningun dia, y la X es la del hueco de fin de
#           semana (23 h) + 3 h = 26 h. Repasar con la pelicula del primer fin de
#           semana (lunes 05-oct).
#    OSMA · UNA pasada al dia, 07:15 Madrid (05:15 UTC en verano), de lunes a viernes.
#           Medido: 2 'aplicadas' (01-oct 12:01 UTC, una prueba con Fernando delante,
#           y 02-oct 05:15 UTC) y una 'rechazada' del 01-oct (fichero ya aplicado).
#           Con dos pasadas no hay cadencia que medir: el hueco normal es de 24 h
#           (un dia habil al siguiente; el viernes al lunes salen 72 h de reloj y
#           24 h sin sabado ni domingo) y viene de `horario_laborables=[7]`,
#           `horario_minuto=15`, `horario_finde=[]` y `horario_margen_min=30`. X = 24 +
#           2 h de margen = 26 h: la pasada de las 06:00 UTC (45 min despues de la
#           esperada) no avisa, y la de las 10:00 UTC si, si no ha habido pasada ese
#           dia (28,7 h).
#
#      proveedor | fuente           | franja (UTC)       | hueco mayor | descontando | X
#      ----------+------------------+--------------------+-------------+-------------+----
#      HEO       | disp_pasada      | 06-19, todos       |  23,00 h *  |  (ninguno)  | 26
#      OSMA      | disp_pasada      | 05, L a V          |  24,00 h *  |  sab y dom  | 26
#      OCIOSTOCK | disp_pasada      | 07, todos          |  24,00 h *  |  (ninguno)  | 26
#      DBLINE    | disp_pasada      | 05-19, L a S       |  24,00 h *  |  domingo    | 26
#      (* derivado del horario, no medido en la pelicula: ver arriba y abajo.)
#
# 🆕 DBLINE EN EL ESCANER 2 (10-oct-2026, encargo DB6). Medido el 10-oct a las
#    14:46 UTC en `disp_pasada`: 7 'aplicadas' en total (9-oct 17:37 y 17:39 UTC, a
#    mano; y desde el 10-oct 10:06 UTC una por hora, a los :06, todas con cambios,
#    ninguna «al dia» todavia). 🔴 SIN PELICULA: el reloj es cron-job.org (tarea
#    8613521), a las :05 de 07 a 21 h Madrid (05-19 UTC en verano), de lunes a
#    sabado; el domingo no hay pasadas.
#    Si el catalogo cambia cada hora, como hoy, el hueco normal es la noche: 19:06 a
#    05:06 UTC = 10 h (y el sabado al lunes, 34 h menos el domingo = 10 h). Pero una
#    pasada «al dia» (mismo contenido) no cuenta como escritura, y no se sabe aun
#    cuantas seguidas puede dar DBLine: el peor caso que se admite sin aviso es un
#    dia entero sin cambio de contenido, 24 h de una aplicada a la del dia
#    siguiente (de ahi los 24,00 h, derivados). X = 26 h, como HEO, OSMA y
#    OcioStock; bajarla cuando haya pelicula de «al dia».
#    Escribe 14 h seguidas, como HEO: lleva `ventana_ancha` (ver abajo). El domingo
#    SE DESCUENTA (DBLine no pasa el domingo) y el sabado NO (si pasa). Con el cambio
#    de hora del 25-oct la franja se corre a 06-20 UTC.
#
# 🆕 OCIOSTOCK EN EL ESCANER 2 (07-oct-2026, encargo OC5). Medido el 07-oct a las
#    15:02 UTC en `disp_pasada`: UNA sola 'aplicada' (10:50:59 UTC, la primera,
#    lanzada a mano). 🔴 SIN PELICULA: la cifra sale del reloj, como OSMA el 03-oct.
#    El reloj es cron-job.org (tarea 8598562, `12 9,13,17 * * *` Europe/Madrid,
#    los siete dias). OcioStock rehace su fichero UNA vez por noche (38 dias del
#    director viejo, parte OC1): la de las 09:12 Madrid (07:12 UTC en verano) se
#    APLICA, y las de 13:12 y 17:12 encuentran el mismo fichero y se cierran
#    'rechazada' «al dia», que aqui NO cuentan como escritura (no han escrito).
#    Hueco normal: de una 09:12 a la del dia siguiente = 24 h, todos los dias
#    (tambien sabado y domingo: el fichero se rehace las siete noches). X = 24 + 2
#    = 26 h, como OSMA. Avisa, por tanto, si una mañana no se aplica fichero
#    nuevo y la del dia siguiente tampoco ha llegado a las 09:12 + 2 h: que
#    OcioStock no rehaga el fichero una noche no ha pasado en 38 dias, y si pasa
#    es justo lo que hay que saber (Reponer veria el catalogo de ayer).
#
#    Por que no se pone la X mas baja para HEO (11 h medidas + margen): porque el
#    fin de semana HEO calla 23 h de por si y una X de 14 daria un aviso falso cada
#    sabado y cada domingo. Se paga con una deteccion lenta de entre semana (26 h);
#    el aviso rapido (dos pasadas horarias falladas) ya lo calcula la base en
#    `v_disp_frescura.avisar`, que hoy solo lee Reponer y no manda Telegram.
#
# 🔬 Y DE AQUI SALE EL RELOJ DEL CENTINELA (06/10/14/18 UTC). La franja en la que
#    cada uno escribe, mas su X, da la ventana en la que su plazo puede vencerse.
#    Las cuatro ventanas caen dentro de 04:00-15:00 UTC, asi que mirar cuatro
#    veces entre las 06:00 y las 18:00 basta, y el hueco de noche no retrasa nada:
#
#      proveedor  | escribe (UTC) |  X   | su plazo vence entre | demora | detectado en
#      -----------+---------------+------+----------------------+--------+-------------
#      TCG        | 06-16         | 22 h |   04:00 y 14:00      |  ≤ 4 h |   ≤ 26 h
#      OCIOSTOCK  | 07 (una)      | 26 h |   09:00 y 09:00      |  ≤ 1 h |   ≤ 27 h
#      OSMA       | 05 (una)      | 26 h |   07:00 y 07:00      |  ≤ 3 h |   ≤ 29 h
#      HEO        | 06-19         | 26 h |   08:00 y 21:00      | ≤ 12 h |   ≤ 38 h  <- ver abajo
#      DBLINE     | 05-19         | 26 h |   07:00 y 21:00      | ≤ 12 h |   ≤ 38 h  <- como HEO (DB6)
#      (Hasta el 10-oct-2026, DBLINE en escaner_memoria: 06-11 UTC, vencia 08:00-13:00.)
#
#    🔴 HEO ES LA EXCEPCION y se dice: escribe 13 h seguidas (06-19 UTC), asi que su
#       plazo puede vencerse en CUALQUIER hora entre las 08:00 y las 21:00 UTC, una
#       ventana de 13 h que no cabe en las 11 h (04:00-15:00) de las otras. Los
#       vencimientos de 08:00 a 18:00 se avisan en 4 h como siempre; los de 18:00 a
#       21:00 caen en el hueco de noche del cron y esperan a la pasada de las 06:00
#       UTC (hasta 12 h): a proposito, porque un Telegram a las 22:00 UTC (00:00 en
#       Madrid) no lo puede atender nadie y es justo el "aviso a deshora" que el
#       cron esta hecho para no dar. Si Cowork prefiere una quinta pasada a las 22:00
#       UTC, es una linea en el cron y el banco lo comprueba. En invierno (UTC+1) la
#       franja de HEO y de OSMA se corre 1 h hacia delante, y la demora no empeora.
#       El banco marca a HEO con `ventana_ancha` y le exige <= 12 h (y <= 4 h en la
#       parte diurna), no le quita la comprobacion. DBLINE (desde el 10-oct-2026, DB6)
#       lleva la misma marca y por lo mismo: escribe 05-19 UTC y su plazo vence entre
#       las 07:00 y las 21:00. Y como descansa el domingo, el banco le exige lo mismo
#       en la ventana del lunes.
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
# `fuente` dice DE DONDE sale la fecha: 'escaner_memoria' (el MAXIMO de `fecha`) o
# 'disp_pasada' (la ultima pasada 'aplicada'). `descansa_sabado` descuenta ademas
# los sabados (OSMA: de lunes a viernes). `ventana_ancha` (HEO y DBLINE): ver arriba.
HORARIOS = {
    'TCG':       {'fuente': 'escaner_memoria', 'umbral_h': 22, 'descansa_domingo': False,
                  'descansa_sabado': False, 'medido_h': 18.00,
                  'primera_h': 6, 'ultima_h': 16, 'dias': 'todos los dias'},
    'DBLINE':    {'fuente': 'disp_pasada', 'umbral_h': 26, 'descansa_domingo': True,
                  'descansa_sabado': False, 'medido_h': 24.00, 'ventana_ancha': True,
                  'primera_h': 5, 'ultima_h': 19, 'dias': 'L a S (cada hora, :05 de 07 a 21 Madrid)'},
    'HEO':       {'fuente': 'disp_pasada', 'umbral_h': 26, 'descansa_domingo': False,
                  'descansa_sabado': False, 'medido_h': 23.00, 'ventana_ancha': True,
                  'primera_h': 6, 'ultima_h': 19, 'dias': 'todos los dias'},
    'OCIOSTOCK': {'fuente': 'disp_pasada', 'umbral_h': 26, 'descansa_domingo': False,
                  'descansa_sabado': False, 'medido_h': 24.00,
                  'primera_h': 7, 'ultima_h': 7, 'dias': 'todos los dias (una aplicada, 09:12 Madrid)'},
    'OSMA':      {'fuente': 'disp_pasada', 'umbral_h': 26, 'descansa_domingo': True,
                  'descansa_sabado': True, 'medido_h': 24.00,
                  'primera_h': 5, 'ultima_h': 5, 'dias': 'L a V (una pasada, 07:15 Madrid)'},
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

def horas_en_dia(desde, hasta, dia_semana):
    """Cuantas de las horas del intervalo [desde, hasta) caen en ese dia de la
    semana (UTC; weekday(): lunes 0 ... sabado 5, domingo 6).

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
        if tramo_ini.weekday() == dia_semana:
            total += (tramo_fin - tramo_ini).total_seconds() / 3600.0
        tramo_ini = tramo_fin
    return total


def horas_en_domingo(desde, hasta):
    """Cuantas de las horas del intervalo [desde, hasta) caen en domingo (UTC)."""
    return horas_en_dia(desde, hasta, 6)                # 6 = domingo


def horas_de_silencio(ultima, ahora, descansa_domingo, descansa_sabado=False):
    """Horas que lleva callado un proveedor, en SU calendario.

    Al que no trabaja los domingos no se le cuentan las horas del domingo: si se
    le contaran, el umbral tendria que subir a 50 h para aguantar el
    sabado-a-lunes, y con 50 h de margen un apagon de verdad se pasa dos dias sin
    que nadie lo note. Que es lo que paso. Al que tampoco trabaja los sabados
    (OSMA: de lunes a viernes) se le descuentan tambien: su viernes-a-lunes son
    72 h de reloj y 24 h de las suyas."""
    if ahora <= ultima:
        return 0.0
    brutas = (ahora - ultima).total_seconds() / 3600.0
    descuento = 0.0
    if descansa_domingo:
        descuento += horas_en_domingo(ultima, ahora)
    if descansa_sabado:
        descuento += horas_en_dia(ultima, ahora, 5)     # 5 = sabado
    return max(brutas - descuento, 0.0)


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
    if cfg['primera_h'] == cfg['ultima_h']:             # una sola pasada al dia
        return '%02d UTC, %s' % (cfg['primera_h'], cfg['dias'])
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
        plazo = ('%.0f h sin contar %s, que es lo que se compara con su plazo '
                 'de %d h. ' % (fila['horas'], fila.get('descontado', 'los domingos'),
                                fila['umbral']))
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
# DE DONDE SALE LA FECHA: UNA FUENTE POR PROVEEDOR
# ============================================================
def _fecha(valor):
    return datetime.fromisoformat(str(valor).replace('Z', '+00:00'))


def ultima_escritura(sb, proveedor, fuente):
    """Devuelve (ultima, motivo): la fecha UTC de la ultima escritura de ese
    proveedor segun su `fuente`, o (None, por_que_no_hay). Si no se puede leer,
    LANZA: quien llama lo apunta como fallo de lectura (no saber no es estar bien).

    'escaner_memoria': el MAXIMO de `fecha` (el escaner viejo).
    'disp_pasada': la ultima pasada 'aplicada' del escaner 2 (`terminada_en`).
       🔴 SOLO 'aplicada': una pasada 'rechazada' o 'fallida' es el escaner 2
       hablando pero SIN haber escrito, que es justo el silencio que se vigila.
       Se piden unas filas y se coge el maximo aqui, no `limit(1)`: ordenado en
       descendente Postgres pone los NULL primero, y un `terminada_en` vacio no es
       una fecha."""
    if fuente == 'disp_pasada':
        res = (sb.table('disp_pasada')
                 .select('terminada_en')
                 .eq('proveedor', proveedor)
                 .eq('estado', 'aplicada')
                 .order('terminada_en', desc=True)
                 .limit(20).execute())
        fechas = [_fecha(r['terminada_en']) for r in (res.data or [])
                  if r.get('terminada_en')]
        if not fechas:
            return None, 'ni una pasada aplicada en disp_pasada'
        return max(fechas), None
    res = (sb.table('escaner_memoria')
             .select('fecha')
             .eq('proveedor', proveedor)
             .order('fecha', desc=True)
             .limit(1).execute())
    if res.data:
        return _fecha(res.data[0]['fecha']), None
    return None, 'ni una fila en escaner_memoria'


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
            ultima, motivo = ultima_escritura(sb, proveedor, cfg['fuente'])
        except Exception as ex:
            motivo = 'no se pudo leer: %s' % ex
            fallo_lectura = True

        horas = None if ultima is None else horas_de_silencio(
            ultima, ahora, cfg['descansa_domingo'], cfg['descansa_sabado'])
        brutas = None if ultima is None else (ahora - ultima).total_seconds() / 3600.0
        filas.append({'proveedor': proveedor, 'ultima': ultima, 'horas': horas,
                      'brutas': brutas, 'umbral': cfg['umbral_h'], 'motivo': motivo,
                      'mudo': esta_mudo(horas, cfg['umbral_h']), 'franja': franja_de(cfg),
                      'fuente': cfg['fuente'],
                      'descontado': ('los sábados y domingos' if cfg['descansa_sabado']
                                     else 'los domingos')})

    # 🔴 LOS CUATRO SIEMPRE AL LOG, hablen o callen. Misma disciplina que el
    #    blindaje anti-vaciado del escaner: un centinela que solo escribe cuando
    #    salta no se puede auditar -- el dia que calla no se distingue "estan
    #    todos al dia" de "no llego a mirar".
    for f in filas:
        if f['ultima'] is None:
            print('  %-10s SIN DATO (%s) | umbral %d h -> MUDO | fuente %s'
                  % (f['proveedor'], f['motivo'], f['umbral'], f['fuente']))
        else:
            print('  %-10s ultima %s UTC | silencio %5.1f h (bruto %5.1f) | umbral %d h -> %s'
                  ' | fuente %s'
                  % (f['proveedor'], f['ultima'].strftime('%Y-%m-%d %H:%M'),
                     f['horas'], f['brutas'], f['umbral'],
                     'MUDO' if f['mudo'] else 'al dia', f['fuente']))

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
    del_escaner2 = [f['proveedor'] for f in mudos
                    if f['proveedor'] in a_avisar and f['fuente'] == 'disp_pasada']
    if del_escaner2:
        lineas.append('%s es del escáner 2: la fecha es la de la última pasada aplicada '
                      '(disp_pasada), y el reloj es cron-job.org, no GitHub.'
                      % ', '.join(del_escaner2))
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
