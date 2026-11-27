#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# MOLOKA - EL VIGILANTE DEL ESCANER 2
# ------------------------------------------------------------
# QUE VIGILA: que cada proveedor con horario en `disp_parametros` (hoy TCG, HEO, DBLine,
# OcioStock y OSMA; BEMS no tiene, lo sube Fernando a mano) siga LEYENDO. Si pierde
# las dos ultimas lecturas previstas de su horario -- o una, si ademas lleva mas de 26 h sin
# lectura buena --, avisa por Telegram.
#
# POR QUE (27-nov-2026). Del 26-nov a las 13:20 al 27-nov a las 08:54 (Madrid) fallaron
# TODAS las lecturas horarias de TCG y a Fernando no le llego nada: se entero al ver
# ofertas en la web de TCG. La regla de antes era «mas de 26 h sin escribir», mirada
# cuatro veces al dia por el `schedule:` de GitHub (que en esta cuenta llega horas
# tarde o no llega): no habria avisado hasta pasadas las 14:23 del 27-nov. Con esta,
# a las 14:55 del 26-nov. (La de antes nacio del apagon del 9-sep-2026, cuando DBLine y
# OcioStock se callaron dos dias sin que nadie lo supiera; el porque sigue en pie.)
#
# LA REGLA ES LA DE REPONER, Y LOS HORARIOS VIVEN EN UN SOLO SITIO. `disp_parametros`
# dice el horario de cada proveedor (`horario_laborables`, `horario_finde`,
# `horario_minuto`, `horario_margen_min`, `pasadas_para_avisar`) y aqui NO se copia
# ninguna hora: se lee en cada vuelta. La cuenta es la de `disp_frescura_en` (migracion
# 20260930160000 de la v2), paso por paso: las horas previstas de 15 dias atras a 8
# adelante en hora de Madrid; una prevista esta VENCIDA cuando su hora + el margen ya
# paso; el plazo es la N-esima vencida hacia atras (N = `pasadas_para_avisar`, hoy 2);
# CADUCADO = sin ninguna lectura buena, o la ultima buena es anterior al plazo.
# 🔴 LA REGLA DEL VIGILANTE ES LA DE REPONER *MAS UN SUELO DE 26 H*, NO LA MISMA. Tambien
#    esta caducado el que ha perdido AL MENOS UNA lectura prevista y lleva mas de SUELO_H
#    (26) horas sin lectura buena (quien dirige, revision del #403, 27-nov-2026). Por que: con
#    dos lecturas perdidas, un proveedor de UNA lectura al dia avisaria MAS TARDE que el
#    vigilante viejo de 26 h (OcioStock, unas 48 h; OSMA, el martes por un lunes perdido; TCG
#    el domingo por un sabado perdido), y eso no puede empeorar. Con el suelo, nadie avisa mas
#    tarde que antes, y los de cada hora siguen saltando a la segunda perdida. Lo de «al menos
#    una perdida» es lo que evita la falsa alarma del fin de semana: sin lectura prevista no
#    hay nada que perder (OSMA del viernes al lunes son 72 h, y no avisa hasta que se pierde
#    la del lunes). Reponer no lleva el suelo: su franja sigue siendo la de la base.
#    🔑 El suelo salta tambien con un INTENTO FALLIDO (una pasada 'fallida' o
#    'rechazada_vaciado'; una 'rechazada' a secas, como la de OSMA «no ha regenerado», no)
#    aunque no haya ninguna prevista perdida: el proveedor que pasa fuera de su horario de
#    la base y falla tambien cuenta. Es el sabado de DBLine: lee de 07 a 21, pero
#    `horario_finde` vale para el sabado y el domingo a la vez y lo tiene vacio. Muerto el
#    viernes por la noche y con las del sabado fallando, avisa el domingo a las 07:55, como el
#    viejo. Si el sabado ni arrancan, el lunes a las 07:55: eso es de la migracion del
#    horario del sabado, no de aqui.
# 🔑 Por que no se llama a la funcion de la base y ya: cuenta SOLO las 'aplicada' y no
#    devuelve el plazo, asi que no hay forma de sumarle las «al dia» (abajo). Cambiarla es
#    una migracion con Fernando delante; esta copia de la cuenta la clava el banco con los
#    casos de la propia migracion (su guarda (g)) y con el caso real de TCG del 26-nov.
#    Si un dia se toca una, se toca la otra.
#
# 🔑 «AL DIA» ES UNA LECTURA BUENA. Una pasada 'rechazada' cuyo contenido es el de la
#    ultima 'aplicada' (el proveedor contesto, con lo mismo) dice que la foto esta al dia.
#    Se reconoce POR ESTRUCTURA, no por el texto del motivo: la misma `huella_contenido`
#    (TCG, DBLine) o el mismo `fichero_md5` (OcioStock) que esa aplicada. Medido el
#    27-nov-2026 en `disp_pasada`: las 141 'rechazada' con motivo «al dia» de TCG, DBLine
#    y OcioStock casan asi, todas. La de OSMA no lleva ni huella ni md5 (es un relanzamiento
#    del mismo dia, despues de su aplicada: no adelanta nada), y su otra 'rechazada' («OSMA
#    no ha regenerado el fichero») NO es una lectura buena: no casa, bien. Una
#    'rechazada_vaciado' o una 'fallida', nunca.
# 🔴 PERO CON TOPE: una «al dia» vale como buena solo mientras la ultima 'aplicada' tenga
#    menos de TOPE_AL_DIA_H (96) horas (quien dirige, revision del #403, 27-nov-2026). Un
#    fichero que el proveedor deja de rehacer es un dato viejo aunque conteste: pasadas las
#    96 h sin ninguna aplicada, sale caducado con su propio texto («contesta, pero con el
#    mismo contenido desde…»), distinto del de «no lee».
#
# LOS TRES AVISOS, por Telegram (en UN mensaje por vuelta, si hay varios):
#   🔴 CADUCADO: desde cuando no hay lectura buena, cuantas lecturas previstas se han
#      perdido desde entonces, cuantos intentos fallaron, el motivo del ultimo fallo
#      (`disp_pasada.motivo`) y que el Escaneo PRO y Reponer estan con datos de esa hora.
#   ⏰ RECORDATORIO, mientras siga caducado: uno cada RECORDATORIO_H horas como mucho, no
#      cada hora (el que suena cada hora se aprende a ignorar).
#   ✅ VUELTA: «<proveedor> vuelve a leer, tras N h».
#   Y si contesta «al dia» pero sin ninguna aplicada en 96 h: «<proveedor> contesta, pero con
#   el mismo contenido desde el <fecha de la ultima aplicada>», con su recordatorio.
#   Y si la base no se puede leer, un aviso propio (el vigilante ciego no calla).
#
# LA MARCA, en Storage (`informes/centinela/ultimo_aviso.json`): por proveedor, desde que
# lectura buena esta caducado y cuando se aviso. Es lo que separa el primer aviso del
# recordatorio y lo que permite el de vuelta.
# 🔴 FALLA EN ABIERTO, Y ESTO NO SE NEGOCIA (condicion de Fernando, 10-sep-2026). Si la
#    marca no se puede leer, se avisa IGUAL de todo lo caducado, como si fuera la primera
#    vez. Si no se puede escribir, el aviso se repetira en la vuelta siguiente: se prefiere
#    repetir a callar. Lo unico que se pierde sin marca es el aviso de VUELTA (no se sabe
#    que se aviso): asimetria a proposito, porque perder un «ya funciona» no cuesta nada.
#    Y si Telegram no confirma el envio, la marca no se toca.
#
# EL RELOJ: cron-job.org, como las pasadas (el `schedule:` de GitHub llega horas tarde
# en esta cuenta). Cada hora a las :55, de 07 a 21 (Madrid), todos los dias: RELOJ, abajo,
# y el banco comprueba que con los horarios de hoy cada lectura vencida se mira en menos
# de una hora. El `schedule:` del workflow se queda de RESPALDO: si el trabajo de
# cron-job.org se para (lo desactiva solo tras varios fallos, o caduca su llave, y entonces
# se paran tambien las pasadas), algo sigue mirando; con la marca, una vuelta de mas no
# repite ningun aviso.
# 🔕 DE NOCHE NO SUENA: fuera de HORAS_DE_AVISAR (07:00-22:59 de Madrid) la vuelta mira y
#    escribe su informe, pero no manda nada ni toca la marca: lo pendiente sale en la
#    primera vuelta de la mañana. Por el respaldo: el de GitHub ha llegado a las 02:15.
#    De noche ningun horario tiene lecturas previstas, asi que no se retrasa nada.
#
# 🔴 REPO PUBLICO: el registro del run lo ve cualquiera. Aqui solo se imprimen estados,
#    horas y recuentos. El motivo de una pasada y el texto de un error van SOLO al
#    Telegram; al registro, como mucho, el TIPO del error.
#
# ENSAYO: con CENTINELA_ENSAYO=si (input `ensayo` del workflow) lee la base y escribe el
# informe, pero ni manda Telegram ni toca la marca.
#
# El run sale en ROJO mientras haya algo caducado o la base no se pueda leer: lo que se
# dosifica es el movil, no el registro.
#
# Variables de entorno: SUPABASE_URL, SUPABASE_SERVICE_KEY, TELEGRAM_TOKEN,
# TELEGRAM_CHAT_ID y, opcional, CENTINELA_ENSAYO.
# ============================================================

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MADRID = ZoneInfo('Europe/Madrid')

# Los de `disp_frescura_en`: las horas previstas se generan de 15 dias atras a 8 adelante.
DIAS_ATRAS = 15
DIAS_ADELANTE = 8

# Mientras un proveedor sigue caducado, un recordatorio cada 6 h como mucho: con el reloj
# de 07:55 a 21:55, un fallo de la mañana da el aviso, uno por la tarde y otro a primera
# hora del dia siguiente (el de la noche espera a las 07:55).
# El suelo: con una lectura prevista perdida, mas de estas horas sin lectura buena es
# caducado aunque la regla del horario aun no lo diga (ver la cabecera).
SUELO_H = 26

# El tope de las «al dia»: con la ultima aplicada de TOPE_AL_DIA_H horas o mas, una «al dia»
# deja de valer como lectura buena. 96 h cubre sin falsas alarmas los fines de semana
# normales: el de TCG (del viernes 19:20 al lunes 09:20, 62 h, con «al dia» el sabado y el
# domingo) y el de OSMA (del viernes al lunes, 72 h). Y un fichero que lleva cuatro dias sin
# cambiar es lo que hay que saber.
TOPE_AL_DIA_H = 96

RECORDATORIO_H = 6
# 🔑 Con holgura: la marca apunta la hora REAL de la vuelta, que se corre unos segundos o
#    minutos de una a otra (el dispatch no arranca al segundo). Sin ella, el recordatorio de
#    las 21:55 de un aviso de las 15:55 podria caer en 5 h 59 y saltar a las 07:55 del dia
#    siguiente.
HOLGURA_RECORDATORIO_MIN = 15

# Horas de Madrid en las que se manda Telegram: de las 07:00 a las 22:59.
HORAS_DE_AVISAR = (7, 23)

# El reloj que se da de alta en cron-job.org (Europe/Madrid, todos los dias). Aqui no lo
# usa nadie en marcha: esta para que el banco lo cruce con los horarios.
RELOJ = {'minuto': 55, 'desde_h': 7, 'hasta_h': 21}

MARCA_BUCKET = 'informes'
MARCA_RUTA = 'centinela/ultimo_aviso.json'

# La clave de la marca para «no se pudo leer la base» (no es un proveedor).
LECTURA = '_LECTURA'

MESES = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


# ============================================================
# LA REGLA, COMO FUNCIONES PURAS
# ------------------------------------------------------------
# No tocan red ni reloj: se les pasa todo. test_centinela_mudo.py las saca de ESTE
# fichero con `ast` y las ejecuta con la historia real de TCG del 26-nov-2026.
# Una pasada es {'estado', 't' (terminada_en, UTC), 'huella', 'md5', 'motivo'}.
# ============================================================

def previstas(par, ahora):
    """Las horas de pasada del horario de `par` (una fila de disp_parametros), en UTC,
    de DIAS_ATRAS dias atras a DIAS_ADELANTE adelante del dia de Madrid de `ahora`.
    De lunes a viernes, `horario_laborables`; sabado y domingo, `horario_finde`. La hora
    es de Madrid: el desfase de ESE dia lo pone zoneinfo, como Postgres en la base."""
    hoy = ahora.astimezone(MADRID).date()
    horas = set()
    for n in range(-DIAS_ATRAS, DIAS_ADELANTE + 1):
        dia = hoy + timedelta(days=n)
        lista = par['horario_laborables'] if dia.isoweekday() <= 5 else par['horario_finde']
        for h in (lista or []):
            local = datetime(dia.year, dia.month, dia.day, h, par['horario_minuto'], tzinfo=MADRID)
            horas.add(local.astimezone(timezone.utc))
    return sorted(horas)


def plazo(par, ahora):
    """{'vencidas': [...] de la mas nueva a la mas vieja, 'ultima_prevista',
    'siguiente_prevista', 'umbral'}. Vencida = su hora + `horario_margen_min` ya paso;
    `umbral` es la vencida numero `pasadas_para_avisar` hacia atras (None si no hay
    tantas), como en `disp_frescura_en`."""
    margen = timedelta(minutes=par['horario_margen_min'])
    todas = previstas(par, ahora)
    vencidas = sorted((t for t in todas if t + margen <= ahora), reverse=True)
    n = par['pasadas_para_avisar']
    futuras = [t for t in todas if t > ahora]
    return {'vencidas': vencidas,
            'ultima_prevista': vencidas[0] if vencidas else None,
            'siguiente_prevista': futuras[0] if futuras else None,
            'umbral': vencidas[n - 1] if len(vencidas) >= n else None}


def esta_caducado(ultima_buena, umbral):
    """Sin ninguna lectura buena, caducado: no saber no es estar bien. Con ella, caducado
    si es anterior al plazo (las N ultimas previstas vencidas, sin ninguna buena)."""
    if ultima_buena is None:
        return True
    return umbral is not None and ultima_buena < umbral


INTENTOS_FALLIDOS = ('fallida', 'rechazada_vaciado')


def suelo_vencido(ultima_buena, perdidas, fallidos, ahora):
    """El suelo de 26 h: AL MENOS una lectura prevista perdida O un intento fallido
    (INTENTOS_FALLIDOS) desde la ultima buena, y mas de SUELO_H horas desde ella. Sin ninguna
    de las dos cosas (un fin de semana sin horario y sin pasadas) no salta, lleve las horas que
    lleve."""
    if ultima_buena is None:
        return False
    if not (perdidas or fallidos):
        return False
    return (ahora - ultima_buena).total_seconds() / 3600.0 > SUELO_H


def es_al_dia(pasada, aplicada):
    """Una 'rechazada' con el mismo contenido que la ultima aplicada: por la huella o por el
    md5 del fichero, nunca por el texto. Un valor vacio no casa con otro vacio."""
    if aplicada is None or pasada['estado'] != 'rechazada':
        return False
    for campo in ('huella', 'md5'):
        if pasada.get(campo) and pasada.get(campo) == aplicada.get(campo):
            return True
    return False


def al_dia_vale(ultima_aplicada, ahora):
    """Si una «al dia» vale todavia como lectura buena: solo mientras la ultima aplicada
    tenga menos de TOPE_AL_DIA_H horas."""
    return ahora - ultima_aplicada < timedelta(hours=TOPE_AL_DIA_H)


def lectura_buena(pasadas, ahora):
    """(ultima lectura buena, ultima aplicada, [horas de las «al dia» posteriores a ella]).
    La buena es la ultima 'aplicada' terminada hasta `ahora`, o la ultima «al dia» posterior
    si todavia vale (`al_dia_vale`). (None, None, []) sin ninguna aplicada."""
    hechas = [p for p in pasadas if p['t'] is not None and p['t'] <= ahora]
    aplicadas = [p for p in hechas if p['estado'] == 'aplicada']
    if not aplicadas:
        return None, None, []
    aplicada = max(aplicadas, key=lambda p: p['t'])
    al_dias = sorted(p['t'] for p in hechas if p['t'] > aplicada['t'] and es_al_dia(p, aplicada))
    if al_dias and al_dia_vale(aplicada['t'], ahora):
        return al_dias[-1], aplicada['t'], al_dias
    return aplicada['t'], aplicada['t'], al_dias


def diagnostico(par, pasadas, ahora):
    """Todo lo que hace falta para decidir y para contarlo: si esta caducado, desde que
    lectura buena, las previstas perdidas desde entonces y los intentos que fallaron."""
    ultima_buena, ultima_aplicada, al_dias = lectura_buena(pasadas, ahora)
    p = plazo(par, ahora)
    # El tope: hay «al dia» despues de la ultima aplicada, pero ya no valen (96 h o mas).
    mismo_contenido = bool(al_dias) and not al_dia_vale(ultima_aplicada, ahora)
    fallos = sorted((x for x in pasadas if x['t'] is not None and x['t'] <= ahora
                     and (ultima_buena is None or x['t'] > ultima_buena) and x['t'] not in al_dias),
                    key=lambda x: x['t'])
    perdidas = sorted(t for t in p['vencidas'] if ultima_buena is None or t > ultima_buena)
    fallidos = [x for x in fallos if x['estado'] in INTENTOS_FALLIDOS]
    return {'caducado': (mismo_contenido or esta_caducado(ultima_buena, p['umbral'])
                         or suelo_vencido(ultima_buena, perdidas, fallidos, ahora)),
            'mismo_contenido': mismo_contenido, 'al_dias': al_dias,
            'ultima_buena': ultima_buena, 'ultima_aplicada': ultima_aplicada,
            'ultima_prevista': p['ultima_prevista'], 'siguiente_prevista': p['siguiente_prevista'],
            'umbral': p['umbral'], 'perdidas': perdidas, 'fallos': fallos}


def _iso(t):
    return None if t is None else t.astimezone(timezone.utc).isoformat()


def eventos(estados, marca, ahora, recordatorio_h):
    """[(tipo, proveedor)] de lo que toca contar en esta vuelta: 'caducado' (nuevo, o con
    otra lectura buena de partida que la avisada), 'recordatorio' (sigue igual y el ultimo
    aviso tiene `recordatorio_h` horas o mas, menos la holgura) o 'vuelta' (ya no lo esta y se habia avisado).

    🔴 FALLA EN ABIERTO: con la marca vacia (no se pudo leer) todo lo caducado sale como
    'caducado'. Una entrada de la marca que no se entienda (el formato de antes del
    27-nov-2026, {proveedor: 'AAAA-MM-DD'}) cuenta como no avisada."""
    salida = []
    for prov in sorted(estados):
        d = estados[prov]
        st = marca.get(prov)
        if not (isinstance(st, dict) and st.get('avisado_en')):
            st = None
        if d['caducado']:
            if st is None or st.get('desde') != _iso(d['ultima_buena']):
                salida.append(('caducado', prov))
            else:
                try:
                    avisado = datetime.fromisoformat(st['avisado_en'])
                except (TypeError, ValueError):
                    avisado = None
                if avisado is None or ahora - avisado >= (timedelta(hours=recordatorio_h)
                                                          - timedelta(minutes=HOLGURA_RECORDATORIO_MIN)):
                    salida.append(('recordatorio', prov))
        elif st is not None:
            salida.append(('vuelta', prov))
    return salida


def marca_tras(marca, enviados, estados, ahora):
    """La marca despues de un envio confirmado: lo avisado se apunta (desde que lectura
    buena y cuando), lo que ha vuelto se borra, y el resto se queda como estaba. Las
    entradas del formato viejo se tiran."""
    nueva = {k: v for k, v in marca.items() if isinstance(v, dict)}
    for tipo, prov in enviados:
        if tipo == 'vuelta':
            nueva.pop(prov, None)
        else:
            nueva[prov] = {'desde': _iso(estados[prov]['ultima_buena']),
                           'avisado_en': ahora.isoformat()}
    return nueva


def hora_de_avisar(ahora):
    """Si a esta hora de Madrid se manda Telegram (HORAS_DE_AVISAR)."""
    return HORAS_DE_AVISAR[0] <= ahora.astimezone(MADRID).hour < HORAS_DE_AVISAR[1]


def fecha_madrid(t):
    """'26-nov 12:23', en hora de Madrid."""
    m = t.astimezone(MADRID)
    return '%d-%s %02d:%02d' % (m.day, MESES[m.month - 1], m.hour, m.minute)


def hora_madrid(t):
    m = t.astimezone(MADRID)
    return '%02d:%02d' % (m.hour, m.minute)


def _motivo(texto):
    """El motivo de una pasada para el Telegram: escapado (va en HTML) y corto."""
    if not texto:
        return 'sin motivo escrito'
    texto = ' '.join(str(texto).split())
    if len(texto) > 200:
        texto = texto[:199] + '…'
    return html.escape(texto)


def _detalle(prov, d):
    """Las lineas que explican un caducado (en el aviso y en el recordatorio)."""
    perdidas = d['perdidas']
    if perdidas:
        horas = ', '.join(hora_madrid(t) for t in perdidas[-6:])
        lineas = ['Desde entonces, %d lectura(s) prevista(s) sin ninguna buena (%s%s) y %d intento(s) '
                  'fallido(s).' % (len(perdidas), '… ' if len(perdidas) > 6 else '', horas,
                                   len(d['fallos']))]
    else:
        lineas = ['%d intento(s) fallido(s).' % len(d['fallos'])]
    if d['fallos']:
        ultimo = d['fallos'][-1]
        lineas.append('Último fallo (%s, %s): «%s»'
                      % (fecha_madrid(ultimo['t']), html.escape(ultimo['estado']), _motivo(ultimo['motivo'])))
    else:
        lineas.append('Ninguna pasada registrada desde entonces: no han llegado a arrancar '
                      '(mira el trabajo de cron-job.org y Actions).')
    if d['ultima_buena'] is not None:
        lineas.append('El Escaneo PRO y Reponer de %s están con los datos del %s.'
                      % (prov, fecha_madrid(d['ultima_buena'])))
    else:
        lineas.append('El Escaneo PRO y Reponer de %s no tienen ninguna lectura buena suya.' % prov)
    return lineas


def texto_de(tipo, prov, d, st, ahora):
    """El trozo de Telegram de un evento. `st` es lo que decia la marca (para la vuelta)."""
    if prov == LECTURA:
        if tipo == 'vuelta':
            return '✅ <b>El vigilante del escáner vuelve a leer la base.</b>'
        cabeza = ('🔴 <b>El vigilante del escáner no puede leer la base</b>' if tipo == 'caducado'
                  else '⏰ <b>El vigilante del escáner sigue sin poder leer la base</b>')
        return (cabeza + ': %s\nSin leerla no sabe si los proveedores leen: míralo en Actions.'
                % _motivo(d.get('error')))
    if tipo == 'vuelta':
        desde = None
        try:
            desde = datetime.fromisoformat(st['desde']) if st and st.get('desde') else None
        except (TypeError, ValueError):
            desde = None
        if desde is not None and d['ultima_buena'] is not None:
            return ('✅ <b>%s vuelve a leer, tras %.0f h</b> (la última buena antes del corte, %s; '
                    'la de ahora, %s).' % (prov, (d['ultima_buena'] - desde).total_seconds() / 3600.0,
                                           fecha_madrid(desde), fecha_madrid(d['ultima_buena'])))
        return '✅ <b>%s vuelve a leer</b> (lectura buena del %s).' % (prov, fecha_madrid(d['ultima_buena']))
    if d.get('mismo_contenido'):
        desde = fecha_madrid(d['ultima_aplicada'])
        if tipo == 'caducado':
            cabeza = '🔴 <b>%s contesta, pero con el mismo contenido desde el %s</b>' % (prov, desde)
        else:
            cabeza = ('⏰ <b>%s sigue contestando con el mismo contenido</b>, desde el %s (%.0f h)'
                      % (prov, desde, (ahora - d['ultima_aplicada']).total_seconds() / 3600.0))
        return '\n'.join([
            cabeza,
            'Desde entonces, %d lectura(s) «al día» (la última, el %s) y %d intento(s) fallido(s), sin '
            'ninguna aplicada en %d h: un fichero que el proveedor no rehace es un dato viejo aunque '
            'conteste.' % (len(d['al_dias']), fecha_madrid(d['al_dias'][-1]), len(d['fallos']), TOPE_AL_DIA_H),
            'El Escaneo PRO y Reponer de %s están con los datos del %s.' % (prov, desde)])
    if d['ultima_buena'] is None:
        cabeza = '<b>%s no tiene ninguna lectura buena</b>' % prov
    elif tipo == 'caducado':
        cabeza = '<b>%s no lee desde el %s</b>' % (prov, fecha_madrid(d['ultima_buena']))
    else:
        cabeza = ('<b>%s sigue sin leer</b>, desde el %s (%.0f h)'
                  % (prov, fecha_madrid(d['ultima_buena']),
                     (ahora - d['ultima_buena']).total_seconds() / 3600.0))
    return '\n'.join([('🔴 ' if tipo == 'caducado' else '⏰ ') + cabeza] + _detalle(prov, d))


# ============================================================
# LA BASE Y STORAGE (lo unico que toca la red, ademas de Telegram)
# ============================================================
COLUMNAS_HORARIO = ('horario_laborables', 'horario_finde', 'horario_minuto',
                    'horario_margen_min', 'pasadas_para_avisar')


def leer_parametros(sb):
    """{proveedor: fila de disp_parametros} de los que tienen horario (algun laborable o
    algun dia de finde). Sin ninguno, LANZA: un vigilante que no vigila a nadie no es un
    vigilante en verde."""
    res = (sb.table('disp_parametros')
             .select('proveedor,' + ','.join(COLUMNAS_HORARIO))
             .execute())
    salida = {}
    for r in (res.data or []):
        if not (r.get('horario_laborables') or r.get('horario_finde')):
            continue
        for c in ('horario_minuto', 'horario_margen_min', 'pasadas_para_avisar'):
            if not isinstance(r.get(c), int):
                raise ValueError('disp_parametros de %s sin %s' % (r.get('proveedor'), c))
        salida[r['proveedor']] = r
    if not salida:
        raise ValueError('ningún proveedor con horario en disp_parametros')
    return salida


def _fecha(valor):
    return datetime.fromisoformat(str(valor).replace('Z', '+00:00'))


def _pasada(r):
    return {'estado': r.get('estado'), 't': _fecha(r['terminada_en']) if r.get('terminada_en') else None,
            'huella': r.get('huella_contenido'), 'md5': r.get('fichero_md5'), 'motivo': r.get('motivo')}


COLUMNAS_PASADA = 'estado,terminada_en,huella_contenido,fichero_md5,motivo'


def leer_pasadas(sb, proveedor):
    """Las ultimas aplicadas y TODO lo que vino despues de la ultima (hasta 500 filas): las
    «al dia» que adelantan la lectura buena y los intentos que fallaron."""
    res = (sb.table('disp_pasada').select(COLUMNAS_PASADA)
             .eq('proveedor', proveedor).eq('estado', 'aplicada')
             .order('terminada_en', desc=True).limit(10).execute())
    aplicadas = [_pasada(r) for r in (res.data or []) if r.get('terminada_en')]
    q = sb.table('disp_pasada').select(COLUMNAS_PASADA).eq('proveedor', proveedor)
    if aplicadas:
        ultima = max(p['t'] for p in aplicadas).astimezone(timezone.utc)
        q = q.gt('terminada_en', ultima.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
    res = q.order('terminada_en', desc=True).limit(500).execute()
    return aplicadas + [_pasada(r) for r in (res.data or [])]


def leer_marca(sb):
    """({...}, se_pudo_leer). 🔴 FALLA EN ABIERTO: cualquier tropiezo -- que no exista
    todavia, que Storage no responda, que el JSON este roto -- devuelve marca vacia, y con
    marca vacia se avisa de todo lo caducado."""
    try:
        crudo = sb.storage.from_(MARCA_BUCKET).download(MARCA_RUTA)
        marca = json.loads(crudo.decode('utf-8'))
        if not isinstance(marca, dict):
            raise ValueError('el JSON de la marca no es un objeto')
        return marca, True
    except Exception as ex:
        print('  AVISO: la marca de avisos no se pudo leer (%s). Se avisa IGUAL de lo caducado;'
              ' lo que no se puede avisar sin ella es una vuelta.' % type(ex).__name__)
        return {}, False


def escribir_marca(sb, marca):
    """Si falla, el aviso se repetira en la vuelta siguiente: se prefiere repetir a callar."""
    try:
        sb.storage.from_(MARCA_BUCKET).upload(
            MARCA_RUTA, json.dumps(marca, indent=1, sort_keys=True).encode('utf-8'),
            {'upsert': 'true', 'content-type': 'application/json'})
        return True
    except Exception as ex:
        print('  AVISO: no se pudo guardar la marca (%s). Consecuencia: el aviso se repetira en'
              ' la vuelta siguiente. Se prefiere repetir a callar.' % type(ex).__name__)
        return False


def enviar_telegram(token, chat, texto):
    """True solo si Telegram confirma el envio (HTTP 200 y ok). Un 400 (un HTML que no
    entiende, por ejemplo) es un aviso que no ha llegado."""
    import requests
    r = requests.post('https://api.telegram.org/bot%s/sendMessage' % token,
                      data={'chat_id': chat, 'text': texto, 'parse_mode': 'HTML',
                            'disable_web_page_preview': 'true'}, timeout=20)
    if r.status_code != 200:
        return False, 'HTTP %s' % r.status_code
    try:
        ok = bool(r.json().get('ok'))
    except Exception:
        ok = False
    return ok, 'HTTP 200' + ('' if ok else ' sin ok')


def _linea(prov, d):
    """La linea del registro: estados, horas UTC y recuentos. NUNCA el motivo."""
    def h(t):
        return '-' if t is None else t.strftime('%Y-%m-%d %H:%M')
    return ('  %-10s ultima buena %s UTC | plazo %s UTC | %d prevista(s) perdida(s), %d intento(s) '
            'fallido(s), %d al dia%s -> %s'
            % (prov, h(d['ultima_buena']), h(d['umbral']), len(d['perdidas']), len(d['fallos']),
               len(d['al_dias']), ' | MISMO CONTENIDO desde %s UTC' % h(d['ultima_aplicada'])
               if d['mismo_contenido'] else '', 'CADUCADO' if d['caducado'] else 'al dia'))


# ============================================================
# EL VIGILANTE
# ============================================================
def main():
    # 🔒 La llave de servicio, o no se corre: con la anonima se pueden recibir cero filas
    #    sin error y declarar caducados a todos -- o no ver nada y callarse.
    llave = os.environ.get('SUPABASE_SERVICE_KEY')
    if not llave:
        print('CENTINELA_NO_EJECUTADO: sin llave de servicio')
        return 1
    ensayo = os.environ.get('CENTINELA_ENSAYO', '').strip().lower() == 'si'

    from supabase import create_client
    sb = create_client(os.environ['SUPABASE_URL'], llave)

    ahora = datetime.now(timezone.utc)
    print('CENTINELA escaner | %s UTC | %s Madrid%s'
          % (ahora.strftime('%Y-%m-%d %H:%M'), ahora.astimezone(MADRID).strftime('%H:%M'),
             ' | ENSAYO' if ensayo else ''))

    estados, error = {}, None
    try:
        parametros = leer_parametros(sb)
    except Exception as ex:
        parametros, error = {}, ex
        print('  NO SE PUDO LEER disp_parametros (%s)' % type(ex).__name__)
    for prov in sorted(parametros):
        try:
            pasadas = leer_pasadas(sb, prov)
        except Exception as ex:
            error = error or ex
            print('  %-10s NO SE PUDO LEER disp_pasada (%s)' % (prov, type(ex).__name__))
            continue
        estados[prov] = diagnostico(parametros[prov], pasadas, ahora)
        # 🔴 TODOS al registro, hablen o callen: el dia que calla tiene que distinguirse
        #    «estan todos al dia» de «no llego a mirar».
        print(_linea(prov, estados[prov]))
    estados[LECTURA] = {'caducado': error is not None, 'ultima_buena': None,
                        'error': None if error is None else '%s: %s' % (type(error).__name__, error)}

    caducados = sorted(p for p, d in estados.items() if d['caducado'])
    codigo = 1 if caducados else 0
    print('CENTINELA_CADUCADO: ' + ', '.join(caducados) if caducados
          else 'CENTINELA OK: los %d proveedores con horario leen dentro de su plazo.'
               % (len(estados) - 1))

    marca, marca_leida = leer_marca(sb)
    evs = eventos(estados, marca, ahora, RECORDATORIO_H)
    for p in caducados:
        if not any(prov == p for _t, prov in evs):
            print('  %s: ya avisado hace menos de %d h (no se repite el Telegram)' % (p, RECORDATORIO_H))
    if not evs:
        print('CENTINELA: nada que enviar.')
        return codigo
    print('CENTINELA_AVISOS: ' + ', '.join('%s %s' % (t, p) for t, p in evs))
    if not hora_de_avisar(ahora):
        print('CENTINELA: fuera de hora (%s Madrid): los avisos esperan a la primera vuelta desde'
              ' las %02d:00; la marca no se toca.' % (ahora.astimezone(MADRID).strftime('%H:%M'),
                                                      HORAS_DE_AVISAR[0]))
        return codigo

    texto = '\n\n'.join(texto_de(t, p, estados[p], marca.get(p), ahora) for t, p in evs)
    if ensayo:
        print('CENTINELA ENSAYO: no se envia el Telegram (%d caracteres) ni se toca la marca.' % len(texto))
        return codigo

    tg_token = os.environ.get('TELEGRAM_TOKEN')
    tg_chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not (tg_token and tg_chat):
        print('>>> Telegram: sin claves en este paso -> no se envia (y la marca no se toca).')
        return 1
    try:
        ok, como = enviar_telegram(tg_token, tg_chat, texto)
    except Exception as ex:
        ok, como = False, type(ex).__name__
    if not ok:
        # 🔒 La marca NO se toca: el aviso no ha llegado, y apuntarlo como enviado seria callar.
        print('AVISO Telegram (no se envio: %s); la marca queda intacta.' % como)
        return 1
    print('>>> Telegram enviado: ' + ', '.join('%s %s' % (t, p) for t, p in evs))
    escribir_marca(sb, marca_tras(marca, evs, estados, ahora))
    return codigo


if __name__ == '__main__':
    sys.exit(main())
