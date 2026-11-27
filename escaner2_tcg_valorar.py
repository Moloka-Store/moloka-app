#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA VALORACION DE LAS NOVEDADES DE TCG DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026).

La lectura horaria de TCG de laborables corre en la maquina de la oficina (escaner2_tcg_disponibilidad.py con
MAQUINA=oficina, desde el repo privado de la v2), que no tiene las llaves de Keepa ni de Telegram y no lanza nada en
GitHub (quien dirige, 27-nov-2026). Esa lectura deja hecha en el acto la SELECCION de novedades, que solo vale para la
ULTIMA pasada aplicada de TCG (va por precio_pa: nov_seleccionar_pasada lanza PASADA_NO_ES_LA_ULTIMA si ya hay otra). La
VALORACION (Keepa, el Excel «TCG · Funko» y el Telegram de novedades: escaner2_novedades.valorar_pasada, la misma de la
horaria) la hace este programa, de TODO lo pendiente de TCG (`pendientes`):
  · las pasadas con la seleccion hecha y la valoracion SIN CERRAR (nov_pasada.valoracion_estado vacio): la de PASADA (a
    mano) siempre, y las demas si llevan mas de PENDIENTE_MIN_S (la horaria del fin de semana y el PRO valoran las suyas
    en el acto, y no hay que pisarlas);
  · las que cerraron con la valoracion 'fallida' hace menos de RECOGER_FALLIDAS_H: se vuelven a intentar. Una fallida queda
    A LA VISTA en la base (valoracion_estado 'fallida' y su motivo) y en el registro, y se recoge sola.
🔑 LAS AVALANCHAS PRIMERO, sea cual sea el orden: cada valoracion recorre TODA la cola de TCG (nov_cola solo se filtra por
   proveedor), asi que una pasada normal valorada antes que una con avalancha pasaria por Keepa las novedades de la
   avalancha. Regla de Fernando (encargo NV): mas de AVALANCHA cambios en una pasada no se valoran; se cierran
   (`cerrar_por_avalancha`), se avisa y el pasa un Escaneo PRO. Por eso las pasadas con avalancha se valoran (= se cierran
   sin Keepa) antes que ninguna otra; luego, el resto de la mas vieja a la mas nueva.
QUIEN LO LANZA: escaner2-tcg-valorar.yml, con un reloj de cron-job.org unos minutos despues de cada lectura de la oficina, y
como RED escaner2-tcg-novedades-cuentas.yml antes de sus cuentas (cron-job.org: a y 45). Los dos jobs van en el grupo
`escaner2-tcg` (el de la lectura horaria de GitHub, el PRO de TCG y las cuentas): valoracion y cuentas nunca a la vez. Si el
reloj llega antes de que la lectura acabe, no hay nada pendiente y sale VERDE sin hacer nada; la recoge la red o el reloj
siguiente.

🔑 LA VALORACION VA POR LA COLA (nov_cola): valorar una pasada vieja despues de otra mas nueva no pierde nada. Las
   novedades que esperan las valora quien valore primero, y cada pasada cierra su fila (nov_cerrar_valoracion cuadra
   con todas las del proveedor y no mira el orden; leido entero el 27-nov-2026).
🔴 REPO PUBLICO: al registro, solo estados y recuentos. De la valoracion, lo que devuelve la base SIN su motivo (que
   puede llevar el texto de un error); el motivo queda en nov_pasada.valoracion_motivo.
🔒 SIN LAS LLAVES (la base y Keepa), NO SE CORRE: aborta antes de tocar nada.

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
# 24 h: una valoracion fallida (Keepa caido, una cuenta que no cuadra) se reintenta en cada corrida durante un dia; si sigue
# fallando, cada corrida sale en ROJO y lo dice. Pasado el dia se deja: su motivo sigue en la base.
RECOGER_FALLIDAS_H = 24
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


def pendientes(sb, pasada, ahora, avalancha=None):
    """Lo que toca valorar ahora, en el orden en que se valora: primero las pasadas con avalancha (se cierran sin Keepa),
    luego el resto de la mas vieja a la mas nueva. Ver la cabecera."""
    if avalancha is None:
        import escaner2_novedades as nv
        avalancha = nv.AVALANCHA
    sin_cerrar = (sb.table('nov_pasada').select(_COLUMNAS).eq('proveedor', PROVEEDOR).eq('estado', 'hecha')
                    .is_('valoracion_estado', 'null').order('creada_en').execute().data or [])
    fallidas = (sb.table('nov_pasada').select(_COLUMNAS).eq('proveedor', PROVEEDOR).eq('estado', 'hecha')
                  .eq('valoracion_estado', 'fallida').gte('valoracion_en',
                                                          (ahora - timedelta(hours=RECOGER_FALLIDAS_H)).isoformat())
                  .order('creada_en').execute().data or [])
    limite = ahora - timedelta(seconds=PENDIENTE_MIN_S)
    cola = [f for f in sin_cerrar if f['pasada_id'] == pasada or (_fecha(f.get('creada_en')) and _fecha(f['creada_en']) < limite)]
    vistos = {f['pasada_id'] for f in cola}
    cola += [f for f in fallidas if f['pasada_id'] not in vistos]
    cola.sort(key=lambda f: str(f.get('creada_en') or ''))
    return [f for f in cola if _novedades(f) > avalancha] + [f for f in cola if _novedades(f) <= avalancha]


def _discreto(*a, **k):
    """El registro discreto de las novedades (escaner2_novedades.imprimir_discreto) SIN la linea «>>> VALORACION DE
    NOVEDADES: {…}», que lleva el motivo de la base: la cuenta de cada pasada la dice `valorar`, sin motivo."""
    import escaner2_novedades as nv
    if ' '.join(str(x) for x in a).strip().startswith('>>> VALORACION DE NOVEDADES'):
        return
    nv.imprimir_discreto(*a, **k)


_CIFRAS = ('novedades', 'nuestras', 'pendientes', 'espera_keepa', 'espera_amazon', 'listas', 'valoradas', 'descartadas',
           'caducadas')


def valorar(sb, pasada, env, ahora=None, valorar_pasada=None, post=None):
    """Valora lo pendiente (`pendientes`). Devuelve (codigo, recuentos). 🔴 Solo estados y recuentos al registro."""
    import escaner2_novedades as nv
    ahora = ahora or datetime.now(timezone.utc)
    hacer = valorar_pasada or nv.valorar_pasada
    cola = pendientes(sb, pasada, ahora)
    bien = mal = 0
    for f in cola:
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
              f"{res.get('estado') or '¿?'}{' · ' + cifras if cifras else ''} · {'bien' if ok else 'EN ROJO (el motivo, en nov_pasada.valoracion_motivo)'}.",
              flush=True)
        bien, mal = bien + bool(ok), mal + (not ok)
    suya = any(f['pasada_id'] == pasada for f in cola)
    print(f">>> VALORAR TCG: pendientes {len(cola)} (la encargada {'sí' if suya else 'no'} está entre ellas"
          f"{'' if suya or not pasada else ': ya valorada, sin selección hecha o no es de TCG'}) · bien {bien} · en "
          f"ROJO {mal}.", flush=True)
    return (1 if mal else 0), {'pendientes': len(cola), 'bien': bien, 'mal': mal, 'suya': suya}


def principal(env=None, sb=None, valorar_pasada=None, post=None, ahora=None):
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
    return valorar(sb, pasada, env, ahora=ahora, valorar_pasada=valorar_pasada, post=post)[0]


if __name__ == '__main__':
    try:
        codigo = principal()
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar una fila de la base
        print(f"TCG_VALORAR_NO_EJECUTADO: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
