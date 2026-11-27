#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA VALORACION DE LAS NOVEDADES DE TCG DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026).

La lectura horaria de TCG de laborables corre en la maquina de la oficina (escaner2_tcg_disponibilidad.py con
MAQUINA=oficina, desde el repo privado de la v2), que no tiene las llaves de Keepa ni de Telegram y no lanza nada en
GitHub (quien dirige, 27-nov-2026). Esa lectura deja hecha en el acto la SELECCION de novedades, que solo vale para la
ULTIMA pasada aplicada de TCG (va por precio_pa: nov_seleccionar_pasada lanza PASADA_NO_ES_LA_ULTIMA si ya hay otra). La
seleccion es UNA llamada a la base (una transaccion): la fila de nov_pasada y sus novedades aparecen juntas, nunca «a
medias». La VALORACION la hace este programa, y tiene que ser correcta por si sola. Cada corrida, EN ESTE ORDEN:

  1. LAS AVALANCHAS, ANTES DE TOCAR KEEPA. Regla de Fernando (encargo NV): mas de AVALANCHA cambios en una pasada no se
     valoran; se cierran, se avisa una vez y el pasa un Escaneo PRO. Cada valoracion recorre TODA la cola de TCG (nov_cola
     solo se filtra por proveedor), asi que la primera cosa es cerrar (`cerrar_por_avalancha`: sus «pendiente» pasan a
     «caducada»; idempotente y sin Telegram) las novedades de TODA pasada de TCG con avalancha de los ultimos
     MIRAR_AVALANCHAS_D dias, tenga la edad que tenga y este cerrada o no su valoracion: una recien seleccionada que aun no
     toca recoger tampoco pasa por Keepa. El aviso «⚠️ Avalancha» sale UNA vez por pasada: al cerrar su valoracion
     (valorar_pasada), y solo se cierra una pasada sin cerrar; una que cerro (o fallo) no se vuelve a valorar.
  2. LO VIEJO SE CIERRA SIN VALORAR. Una pasada seleccionada hace mas de TOPE_PENDIENTE_H y aun sin valorar: sus «pendiente»
     pasan a «caducada» con el motivo, y su valoracion se cierra como 'fallida' con ese motivo (a la vista en la base). Sin
     Keepa ni Telegram: no se avisa de algo pasado.
  3. LA VALORACION (Keepa, el Excel «TCG · Funko» y el Telegram de novedades: escaner2_novedades.valorar_pasada, la misma
     de la horaria) de lo pendiente, de la mas vieja a la mas nueva, las avalanchas primero:
       · la seleccion hecha y la valoracion SIN CERRAR, con mas de PENDIENTE_MIN_S (la horaria del fin de semana y el PRO
         valoran las suyas en el acto, y no hay que pisarlas) o la de PASADA (a mano);
       · las que cerraron 'fallida', si su SELECCION es de hace menos de RECOGER_FALLIDAS_H (el plazo cuenta desde la
         seleccion, no desde el ultimo cierre, que se renueva en cada intento): se reintentan, A LA VISTA en la base y en el
         registro. Las avalanchas fallidas no se reintentan (sus novedades ya estan cerradas en el paso 1; el aviso, una vez).

QUIEN LO LANZA: escaner2-tcg-valorar.yml, con un reloj de cron-job.org a y 35 en laborables (15 min despues de cada lectura
de la oficina), y como RED escaner2-tcg-novedades-cuentas.yml antes de sus cuentas (cron-job.org: a y 45). Los dos jobs van
en el grupo `escaner2-tcg` (el de la lectura horaria de GitHub, el PRO de TCG y las cuentas): valoracion y cuentas nunca a
la vez. Si el reloj llega antes de que la lectura acabe, no hay nada pendiente y sale VERDE sin hacer nada.
🔑 LA RED EMPIEZA A VALORAR EN CUANTO SE FUSIONE LA V1, antes de encender la oficina: lo pendiente de TCG que haya (medido el
   27-nov-2026: ninguna pasada de TCG con la valoracion vacia ni fallida en 7 dias) y, desde entonces, cada fallida de la
   horaria del fin de semana o del PRO.

🔑 LA VALORACION VA POR LA COLA (nov_cola): valorar una pasada vieja despues de otra mas nueva no pierde nada. Las
   novedades que esperan las valora quien valore primero, y cada pasada cierra su fila (nov_cerrar_valoracion cuadra
   con todas las del proveedor y no mira el orden; leido entero el 27-nov-2026).
🔴 REPO PUBLICO: al registro, solo estados y recuentos. De la valoracion, lo que devuelve la base SIN su motivo (que
   puede llevar el texto de un error); el motivo queda en nov_pasada.valoracion_motivo.
🔒 SIN LAS LLAVES (la base y Keepa), NO SE CORRE: aborta antes de tocar nada.
🔒 Escribe lo que escribe la valoracion de siempre, y lo de los pasos 1 y 2: nov_novedad (de «pendiente» a «caducada», con
   su motivo, como cerrar_por_avalancha) y el cierre de la valoracion (nov_cerrar_valoracion).

Uso:  python escaner2_tcg_valorar.py   (PASADA, opcional, por el entorno: la pone el workflow desde su input)
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

PROVEEDOR = 'TCG'
# 5 min: la horaria del fin de semana y el PRO valoran su pasada en el mismo proceso, justo despues de la seleccion. Medido el
# 27-nov-2026 en nov_pasada de TCG (30 dias, 218 valoradas): de la seleccion al cierre de la valoracion, mediana 1,5 s, p99 84 s
# y maximo 227 s. Con 5 min no se pisa ninguna en marcha, y la de la oficina (seleccionada hacia y 22-y 25) la coge el reloj
# de y 35; con mas margen, ese reloj no cogeria casi nunca nada y todo esperaria a la red de y 45.
PENDIENTE_MIN_S = 300
# 24 h DESDE LA SELECCION: una valoracion fallida (Keepa caido, una cuenta que no cuadra) se reintenta en cada corrida durante
# un dia; si sigue fallando, cada corrida sale en ROJO y lo dice. Pasado el dia se deja: su motivo sigue en la base.
RECOGER_FALLIDAS_H = 24
# 24 h: lo seleccionado y sin valorar en un dia ya no es una novedad: se cierra sin valorar y sin avisar (paso 2).
TOPE_PENDIENTE_H = 24
# 7 dias: hasta donde se mira si hay avalanchas con novedades aun «pendiente» (paso 1). Mas alla, todo cerro hace tiempo.
MIRAR_AVALANCHAS_D = 7
_RE_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_COLUMNAS = 'pasada_id,creada_en,valoracion_estado,valoracion_en,n_novedades,n_subidas_fuera'


def abortar(motivo):
    print(f"TCG_VALORAR_NO_EJECUTADO: {motivo}")
    sys.exit(1)


def _fecha(v):
    if not v:
        return None
    t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _novedades(f):
    """Lo que entra a valorar de una pasada (como escaner2_novedades.novedades_a_valorar): novedades menos subidas fuera."""
    return max(int(f.get('n_novedades') or 0) - int(f.get('n_subidas_fuera') or 0), 0)


def _antes_de(f, t):
    c = _fecha(f.get('creada_en'))
    return c is not None and c < t


def plan(sb, pasada, ahora, avalancha):
    """Lo que hace esta corrida (ver la cabecera): {'avalanchas': [...] (paso 1, se cierran sus novedades),
    'viejas': [...] (paso 2), 'valorar': [...] (paso 3, en orden)}."""
    sin_cerrar = (sb.table('nov_pasada').select(_COLUMNAS).eq('proveedor', PROVEEDOR).eq('estado', 'hecha')
                    .is_('valoracion_estado', 'null').order('creada_en').execute().data or [])
    recientes = (sb.table('nov_pasada').select(_COLUMNAS).eq('proveedor', PROVEEDOR).eq('estado', 'hecha')
                   .gte('creada_en', (ahora - timedelta(days=MIRAR_AVALANCHAS_D)).isoformat()).order('creada_en')
                   .execute().data or [])
    tope, limite = ahora - timedelta(hours=TOPE_PENDIENTE_H), ahora - timedelta(seconds=PENDIENTE_MIN_S)
    fallidas_desde = ahora - timedelta(hours=RECOGER_FALLIDAS_H)
    vistos, avalanchas = set(), []
    for f in recientes + sin_cerrar:
        if _novedades(f) > avalancha and f['pasada_id'] not in vistos:
            vistos.add(f['pasada_id'])
            avalanchas.append(f)
    viejas = [f for f in sin_cerrar if _antes_de(f, tope) and f['pasada_id'] != pasada]
    viejo = {f['pasada_id'] for f in viejas}
    cola = [f for f in sin_cerrar if f['pasada_id'] not in viejo and (f['pasada_id'] == pasada or _antes_de(f, limite))]
    cola += [f for f in recientes if f.get('valoracion_estado') == 'fallida' and not _antes_de(f, fallidas_desde)
             and _novedades(f) <= avalancha]
    cola.sort(key=lambda f: str(f.get('creada_en') or ''))
    return {'avalanchas': avalanchas, 'viejas': viejas,
            'valorar': [f for f in cola if _novedades(f) > avalancha] + [f for f in cola if _novedades(f) <= avalancha]}


def cerrar_vieja(sb, f, ahora):
    """Paso 2: las «pendiente» de una pasada seleccionada hace mas de TOPE_PENDIENTE_H pasan a «caducada» con el motivo, y su
    valoracion se cierra 'fallida' con ese motivo. Sin Keepa ni Telegram. Devuelve cuantas novedades caducan."""
    pid = f['pasada_id']
    motivo = (f'sin valorar a tiempo: la pasada {pid} de TCG se seleccionó hace más de {TOPE_PENDIENTE_H} h y nadie la '
              f'valoró; no se valora algo pasado')
    filas = (sb.table('nov_novedad').update({'estado': 'caducada', 'estado_en': ahora.isoformat(), 'motivo_estado': motivo})
               .eq('pasada_id', pid).eq('proveedor', PROVEEDOR).eq('estado', 'pendiente').execute().data or [])
    sb.rpc('nov_cerrar_valoracion', {'p_pasada': pid, 'p_datos': {
        'estado': 'fallida', 'motivo': f'{motivo} ({len(filas)} novedad(es) caducadas)'}}).execute()
    return len(filas)


def _discreto(*a, **k):
    """El registro discreto de las novedades (escaner2_novedades.imprimir_discreto) SIN la linea «>>> VALORACION DE
    NOVEDADES: {…}», que lleva el motivo de la base: la cuenta de cada pasada la dice `valorar`, sin motivo."""
    import escaner2_novedades as nv
    if ' '.join(str(x) for x in a).strip().startswith('>>> VALORACION DE NOVEDADES'):
        return
    nv.imprimir_discreto(*a, **k)


_CIFRAS = ('novedades', 'nuestras', 'pendientes', 'espera_keepa', 'espera_amazon', 'listas', 'valoradas', 'descartadas',
           'caducadas')


def valorar(sb, pasada, env, ahora=None, valorar_pasada=None, post=None, cerrar_avalancha=None):
    """Los tres pasos de la cabecera. Devuelve (codigo, recuentos). 🔴 Solo estados y recuentos al registro."""
    import escaner2_novedades as nv
    ahora = ahora or datetime.now(timezone.utc)
    hacer = valorar_pasada or nv.valorar_pasada
    cerrar = cerrar_avalancha or (lambda sb_, pid, n: nv.cerrar_por_avalancha(sb_, pid, n, proveedor=PROVEEDOR))
    p = plan(sb, pasada, ahora, nv.AVALANCHA)
    mal = 0
    # 1 · Las avalanchas, antes de tocar Keepa.
    cerradas = 0
    for f in p['avalanchas']:
        try:
            cerradas += int(cerrar(sb, f['pasada_id'], _novedades(f)) or 0)
        except Exception as ex:  # noqa: BLE001 — sin cerrarlas, la cola las llevaria a Keepa: no se valora nada. 🔴 Solo el tipo.
            print(f"TCG_AVALANCHA_SIN_CERRAR: no se han podido cerrar las novedades de una avalancha ({type(ex).__name__}); "
                  f"no se valora nada en esta corrida.", flush=True)
            return 1, {'avalanchas': len(p['avalanchas']), 'viejas': 0, 'pendientes': 0, 'bien': 0, 'mal': 1, 'suya': False}
    print(f">>> AVALANCHAS DE TCG (últimos {MIRAR_AVALANCHAS_D} días): {len(p['avalanchas'])} · novedades cerradas sin valorar "
          f"ahora {cerradas}.", flush=True)
    # 2 · Lo viejo, cerrado sin valorar.
    for f in p['viejas']:
        try:
            n = cerrar_vieja(sb, f, ahora)
            print(f">>> SIN VALORAR A TIEMPO: la pasada {f['pasada_id']} (seleccionada hace más de {TOPE_PENDIENTE_H} h) se "
                  f"cierra sin valorar · {n} novedad(es) caducadas · sin aviso.", flush=True)
        except Exception as ex:  # noqa: BLE001 — 🔴 solo el tipo
            print(f">>> SIN VALORAR A TIEMPO: la pasada {f['pasada_id']} no se ha podido cerrar ({type(ex).__name__}).",
                  flush=True)
            mal += 1
    # 3 · La valoracion.
    bien = 0
    for f in p['valorar']:
        n = _novedades(f)
        try:
            ok, res = hacer(sb, f['pasada_id'], keepa_llave=env.get('KEEPA_API_KEY'), imprimir=_discreto,
                            run_id=env.get('GITHUB_RUN_ID') or None, novedades_pasada=n, env=env, post=post,
                            proveedor=PROVEEDOR)
        except Exception as ex:  # noqa: BLE001 — valorar_pasada no lanza; esto es por si acaso. 🔴 Solo el tipo.
            ok, res = False, {'estado': f'sin cerrar ({type(ex).__name__})'}
        res = res if isinstance(res, dict) else {}
        cifras = ' · '.join(f'{k} {res[k]}' for k in _CIFRAS if res.get(k) is not None)
        print(f">>> VALORACION de la pasada {f['pasada_id']} ({'avalancha, ' if n > nv.AVALANCHA else ''}"
              f"{'reintento de una fallida' if f.get('valoracion_estado') == 'fallida' else 'pendiente'}): "
              f"{res.get('estado') or '¿?'}{' · ' + cifras if cifras else ''} · "
              f"{'bien' if ok else 'EN ROJO (el motivo, en nov_pasada.valoracion_motivo)'}.", flush=True)
        bien, mal = bien + bool(ok), mal + (not ok)
    suya = any(f['pasada_id'] == pasada for f in p['valorar'])
    print(f">>> VALORAR TCG: pendientes {len(p['valorar'])}"
          f"{'' if not pasada else ' (la pedida ' + ('sí' if suya else 'no: ya valorada, vieja, sin selección hecha o no es de TCG') + ')'}"
          f" · cerradas por viejas {len(p['viejas'])} · bien {bien} · en ROJO {mal}.", flush=True)
    return (1 if mal else 0), {'avalanchas': len(p['avalanchas']), 'viejas': len(p['viejas']),
                               'pendientes': len(p['valorar']), 'bien': bien, 'mal': mal, 'suya': suya}


def principal(env=None, sb=None, valorar_pasada=None, post=None, ahora=None, cerrar_avalancha=None):
    env = os.environ if env is None else env
    pasada = (env.get('PASADA') or '').strip().lower()
    if pasada and not _RE_UUID.match(pasada):
        abortar('PASADA tiene que ser el id (uuid) de una pasada, o nada')
    if not (env.get('SUPABASE_URL') and env.get('SUPABASE_SERVICE_KEY')):
        abortar('faltan SUPABASE_URL/SUPABASE_SERVICE_KEY; no se hace nada')
    if not env.get('KEEPA_API_KEY'):
        abortar('falta KEEPA_API_KEY; no se valora nada')
    if sb is None:
        from escaner2_base import cliente
        sb = cliente(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY'])
    return valorar(sb, pasada, env, ahora=ahora, valorar_pasada=valorar_pasada, post=post,
                   cerrar_avalancha=cerrar_avalancha)[0]


if __name__ == '__main__':
    try:
        codigo = principal()
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar una fila de la base
        print(f"TCG_VALORAR_NO_EJECUTADO: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
