#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA VALORACION DE LAS NOVEDADES DE TCG Y LOS AVISOS DE LA LECTURA DESDE LA OFICINA (encargo TO, 27-nov-2026).

La lanza escaner2-tcg-valorar.yml, y a ese workflow lo lanza (workflow_dispatch) la lectura de TCG que corre en la maquina
de la oficina (escaner2_tcg_disponibilidad.py con MAQUINA=oficina, desde el repo privado de la v2). Esa maquina no tiene
las llaves de Keepa ni de Telegram. Por eso la lectura deja hecha en el acto la SELECCION de novedades, que solo vale
para la ULTIMA pasada aplicada de TCG (va por precio_pa: nov_seleccionar_pasada lanza PASADA_NO_ES_LA_ULTIMA si ya hay otra).
Lo demas lo encarga aqui:
  · AVISO=valorar · la VALORACION (Keepa, el Excel «TCG · Funko» y el Telegram de novedades: escaner2_novedades.
    valorar_pasada, la misma de la horaria) de TODAS las pasadas de TCG con la seleccion hecha y la valoracion sin cerrar
    (nov_pasada: estado 'hecha', valoracion_estado vacio), de la mas vieja a la mas nueva. Es decir, la de PASADA y
    cualquiera que se quedara sin valorar: porque el encargo no llego (la lectura lo dice en su registro y sale en ROJO:
    TCG_VALORACION_NO_ENCARGADA) o porque una corrida de este workflow fallo. Asi ninguna novedad seleccionada se queda
    sin valorar en silencio: el hueco esta en la base (valoracion_estado vacio) y lo cierra la corrida siguiente.
    Las que no son la de PASADA, solo si llevan mas de PENDIENTE_MIN_S sin cerrar: la horaria del fin de semana y el
    Escaneo PRO valoran las suyas en el acto, justo despues de seleccionarlas (hasta 227 s medidos), y no hay que pisarlas.
  · AVISO=parada · ademas, el Telegram de una pasada que se ha parado porque la web de TCG no deja (el motivo lo lee de
    disp_pasada, que es privada), como el de la horaria.
  · AVISO=tramos · ademas, el Telegram del lector de tramos parado. El detalle queda en el registro de la corrida de la v2.

🔑 LA VALORACION VA POR LA COLA (nov_cola): valorar una pasada vieja despues de otra mas nueva no pierde nada. Las
   novedades que esperan las valora quien valore primero, y cada pasada cierra su fila (nov_cerrar_valoracion cuadra
   con todas las del proveedor).
🔴 REPO PUBLICO: solo estados y recuentos al registro (imprimir_discreto). El texto de un error queda en
   nov_pasada.valoracion_motivo.
🔒 SIN LAS LLAVES (la base y Keepa), NO SE CORRE: aborta antes de valorar nada.

Uso:  python escaner2_tcg_valorar.py   (AVISO y PASADA por el entorno; los pone el workflow desde sus inputs)
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

PROVEEDOR = 'TCG'
AVISOS = ('valorar', 'parada', 'tramos')
# 15 min: la horaria del fin de semana y el PRO valoran su pasada en el mismo proceso, justo despues de la seleccion. Medido el
# 27-nov-2026 en nov_pasada de TCG (30 dias, 218 valoradas): de la seleccion al cierre de la valoracion, mediana 1,5 s, p99 84 s
# y maximo 227 s. Con 15 min no se pisa ninguna en marcha, y lo atrasado se recoge igual: la siguiente corrida es en una hora.
PENDIENTE_MIN_S = 900
_RE_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def abortar(motivo):
    print(f"TCG_VALORAR_NO_EJECUTADO: {motivo}")
    sys.exit(1)


def _fecha(v):
    if not v:
        return None
    t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def pendientes(sb, pasada, ahora):
    """Las filas de nov_pasada de TCG con la seleccion hecha y la valoracion sin cerrar que tocan ahora, de la mas vieja a
    la mas nueva: la de `pasada` siempre, las demas si llevan mas de PENDIENTE_MIN_S."""
    filas = (sb.table('nov_pasada').select('pasada_id,creada_en,n_novedades,n_subidas_fuera').eq('proveedor', PROVEEDOR)
               .eq('estado', 'hecha').is_('valoracion_estado', 'null').order('creada_en').execute().data or [])
    limite = ahora - timedelta(seconds=PENDIENTE_MIN_S)
    return [f for f in filas if f['pasada_id'] == pasada or (_fecha(f.get('creada_en')) and _fecha(f['creada_en']) < limite)]


def avisar_parada(sb, pasada, env=None, post=None):
    """El Telegram de una pasada de la oficina que se ha parado porque la web no deja (el de la horaria, con el motivo de la
    base). Devuelve True si se ha mandado."""
    import escaner2_tcg_disponibilidad as d
    fila = ((sb.table('disp_pasada').select('id,proveedor,estado,motivo').eq('id', pasada).limit(1).execute().data
             or [None])[0] if pasada else None)
    if not fila or fila.get('proveedor') != PROVEEDOR:
        texto = ('⚠️ Escáner 2 · TCG: la lectura desde la oficina se ha parado porque la web de TCG no deja, pero su pasada '
                 'no está en la base. Mira el registro de la corrida en la v2.')
    else:
        texto = (f"⚠️ Escáner 2 · TCG: la pasada de la foto (lectura desde la oficina) se ha parado porque la web de TCG no "
                 f"deja ({fila.get('motivo') or fila.get('estado')}). Nada inventado; el escáner viejo sigue como siempre.")
    return d.avisar(texto, env=env, post=post)


def avisar_tramos(env=None, post=None):
    import escaner2_tcg_disponibilidad as d
    return d.avisar('⚠️ Escáner 2 · TCG: el lector de tramos de la lectura desde la oficina se ha parado. Lo leído queda '
                    'guardado; ningún cociente inventado; la foto de TCG sigue con lo que tenía. El detalle, en el '
                    'registro de la corrida de la v2.', env=env, post=post)


def valorar(sb, pasada, env, ahora=None, valorar_pasada=None, post=None):
    """Valora las pendientes (`pendientes`). Devuelve (codigo, recuentos)."""
    import escaner2_novedades as nv
    ahora = ahora or datetime.now(timezone.utc)
    hacer = valorar_pasada or nv.valorar_pasada
    cola = pendientes(sb, pasada, ahora)
    bien = mal = 0
    for f in cola:
        n = max(int(f.get('n_novedades') or 0) - int(f.get('n_subidas_fuera') or 0), 0)
        try:
            ok, _res = hacer(sb, f['pasada_id'], keepa_llave=env.get('KEEPA_API_KEY'), imprimir=nv.imprimir_discreto,
                             run_id=env.get('GITHUB_RUN_ID') or None, novedades_pasada=n, env=env, post=post,
                             proveedor=PROVEEDOR)
        except Exception as ex:  # noqa: BLE001 — valorar_pasada no lanza; esto es por si acaso. 🔴 Solo el tipo.
            print(f">>> VALORAR: una pasada ha fallado ({type(ex).__name__}); queda sin cerrar para la siguiente corrida.",
                  flush=True)
            ok = False
        bien, mal = bien + bool(ok), mal + (not ok)
    suya = any(f['pasada_id'] == pasada for f in cola)
    print(f">>> VALORAR TCG: pendientes {len(cola)} (la encargada {'sí' if suya else 'no'} está entre ellas"
          f"{'' if suya or not pasada else ': ya valorada, sin selección hecha o no es de TCG'}) · bien {bien} · en "
          f"ROJO {mal}.", flush=True)
    return (1 if mal else 0), {'pendientes': len(cola), 'bien': bien, 'mal': mal, 'suya': suya}


def principal(env=None, sb=None, valorar_pasada=None, post=None, ahora=None):
    env = os.environ if env is None else env
    aviso = (env.get('AVISO') or 'valorar').strip()
    pasada = (env.get('PASADA') or '').strip().lower()
    if aviso not in AVISOS:
        abortar(f'AVISO tiene que ser {", ".join(AVISOS)}')
    if pasada and not _RE_UUID.match(pasada):
        abortar('PASADA tiene que ser el id (uuid) de una pasada, o nada')
    if not (env.get('SUPABASE_URL') and env.get('SUPABASE_SERVICE_KEY')):
        abortar('faltan SUPABASE_URL/SUPABASE_SERVICE_KEY; no se valora nada')
    if not env.get('KEEPA_API_KEY'):
        abortar('falta KEEPA_API_KEY; no se valora nada')
    if sb is None:
        from escaner2_base import cliente
        sb = cliente(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY'])
    codigo = 0
    if aviso == 'parada' and not avisar_parada(sb, pasada, env=env, post=post):
        codigo = 1
    if aviso == 'tramos' and not avisar_tramos(env=env, post=post):
        codigo = 1
    c, _r = valorar(sb, pasada, env, ahora=ahora, valorar_pasada=valorar_pasada, post=post)
    return codigo or c


if __name__ == '__main__':
    try:
        codigo = principal()
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar una fila de la base
        print(f"TCG_VALORAR_NO_EJECUTADO: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
