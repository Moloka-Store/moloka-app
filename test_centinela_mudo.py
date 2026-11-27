# -*- coding: utf-8 -*-
"""Banco: el vigilante del escaner avisa en cuanto un proveedor pierde dos lecturas de su horario.

EL FALLO QUE CIERRA (26 y 27-nov-2026). Del 26-nov a las 13:20 al 27-nov a las 08:54 (Madrid)
fallaron TODAS las lecturas horarias de TCG (la ultima aplicada, 26-nov 12:23) y a Fernando no le
llego nada. El vigilante de antes avisaba con «mas de 26 h sin escribir»: no habria dicho nada
hasta pasadas las 14:23 del 27-nov. El de ahora sigue el horario de cada proveedor, el de
`disp_parametros`, con la regla de Reponer (`disp_frescura_en`): caducado = las dos ultimas
lecturas previstas y vencidas sin ninguna buena. Con la historia real de TCG, a las 14:50 del 26.

QUE SE PRUEBA:
  (A) LA REGLA, con las funciones REALES sacadas de `centinela_escaner.py` con `ast` (por
      estructura) y ejecutadas: las tres horas que clava la propia migracion de la v2 (su guarda
      (g), con el horario de HEO de entonces: un sabado, el cambio de hora de octubre y el de
      marzo); y el caso real de TCG, al minuto (14:49:59 no, 14:50:00 si).
  (C) DE PUNTA A PUNTA, cada caso en su PROCESO, con `supabase` y `requests` sustituidos por
      dobles en memoria (sin red, sin secretos) y el reloj fijo: el caso real de TCG antes y
      despues de las 14:50; una «al dia» en medio cuenta como buena (por huella, TCG; por md5,
      OcioStock), y una con otro contenido no; los fines de semana de OSMA, DBLine y HEO sin
      falsas alarmas, y su contraste entre semana; el recordatorio (no antes de 6 h) y la vuelta
      («vuelve a leer, tras 21 h», con la historia real del 27-nov); la noche callada; la marca que
      FALLA EN ABIERTO (ilegible, no escribible, del formato viejo); Telegram que no confirma; la
      base que no se lee; ningun proveedor con horario; el ensayo; y que el motivo de una pasada va
      al Telegram (escapado) y NUNCA al registro (repo publico).
  (G) EL RELOJ de cron-job.org (RELOJ del .py) cruzado con los horarios de `disp_parametros`
      medidos el 27-nov-2026: cada lectura vencida se mira en menos de una hora, y ninguna vuelta
      del reloj cae en horas de silencio. Y el workflow: `workflow_dispatch` con su ensayo apagado
      por defecto y el `schedule:` de respaldo.
  (B) POR ESTRUCTURA: el .py no copia ningun horario ni nombra a ningun proveedor (los saca de la
      base).
  (R) ROTURAS DE LA REGLA, dentro del banco: se estropea una COPIA del vigilante por estructura
      (con `ast`) -- tres pasadas en vez de dos, sin el margen, sin las «al dia" -- y se exige que
      el caso que la vigila cambie de veredicto; mas la copia sin estropear como control. Un banco
      que no sabe ponerse rojo no prueba nada.
"""
import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import zoneinfo  # 🔑 antes de cambiar `datetime` en el hijo: zoneinfo se carga con el de verdad
from datetime import datetime, timedelta, timezone
import html as _html

import yaml

RUTA = 'centinela_escaner.py'
MAD = zoneinfo.ZoneInfo('Europe/Madrid')


def _u(txt):
    """Una hora UTC escrita a mano."""
    return datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)


def _m(txt):
    """Una hora de MADRID escrita a mano, en UTC."""
    return datetime.fromisoformat(txt).replace(tzinfo=MAD).astimezone(timezone.utc)


# ===========================================================================
# LOS HORARIOS DE `disp_parametros`, medidos en produccion el 27-nov-2026 (conector de lectura)
# ---------------------------------------------------------------------------
# El vigilante los LEE de la base en cada vuelta; aqui son la foto con la que corren los dobles.
# Si en la base cambian, este banco no se entera (no sale a la red): lo que clava es la REGLA y el
# reloj contra estos horarios. BEMS no tiene horario (lo sube Fernando a mano) y no se vigila.
# ===========================================================================
PARAMETROS = [
    {'proveedor': 'BEMS', 'horario_laborables': [], 'horario_finde': [], 'horario_minuto': 0,
     'horario_margen_min': 30, 'pasadas_para_avisar': 2},
    {'proveedor': 'DBLINE', 'horario_laborables': list(range(7, 22)), 'horario_finde': [],
     'horario_minuto': 0, 'horario_margen_min': 30, 'pasadas_para_avisar': 2},
    {'proveedor': 'HEO', 'horario_laborables': list(range(8, 19)), 'horario_finde': [8, 9],
     'horario_minuto': 0, 'horario_margen_min': 20, 'pasadas_para_avisar': 2},
    {'proveedor': 'OCIOSTOCK', 'horario_laborables': [9], 'horario_finde': [9], 'horario_minuto': 12,
     'horario_margen_min': 30, 'pasadas_para_avisar': 2},
    {'proveedor': 'OSMA', 'horario_laborables': [7], 'horario_finde': [], 'horario_minuto': 15,
     'horario_margen_min': 30, 'pasadas_para_avisar': 2},
    {'proveedor': 'TCG', 'horario_laborables': list(range(9, 20)), 'horario_finde': [12],
     'horario_minuto': 20, 'horario_margen_min': 30, 'pasadas_para_avisar': 2},
]
VIGILADOS = ['DBLINE', 'HEO', 'OCIOSTOCK', 'OSMA', 'TCG']
PAR = {r['proveedor']: r for r in PARAMETROS}

# LA HISTORIA REAL DE TCG, 26 y 27-nov-2026: `disp_pasada` leida con el conector de lectura el 27-nov
# (huella y md5, sus 8 primeros caracteres; el motivo, recortado). (estado, terminada_en UTC, huella,
# md5, motivo)
_LOGIN = 'la web de TCG no deja: login: no aparece el formulario de entrada'
_ESTADO = '1 fila(s) con «Estado producto» que no se entiende'
TCG_REAL = [
    ('aplicada', '2026-11-26T08:22:48.797756', 'f2578df9', '33de4540', None),
    ('aplicada', '2026-11-26T09:22:19.068253', '62f97c6e', 'd2fc302c', None),
    ('aplicada', '2026-11-26T10:22:40.973290', 'dde35a03', 'b04a3851', None),
    ('aplicada', '2026-11-26T11:23:27.594722', 'b714a805', 'f71a9488', None),
    ('fallida', '2026-11-26T12:21:23.137368', None, '6587b24a', _ESTADO),
    ('fallida', '2026-11-26T13:21:07.016316', None, None, _LOGIN),
    ('fallida', '2026-11-26T13:21:55.061497', None, 'ea6fcb4f', _ESTADO),
    ('fallida', '2026-11-26T14:21:23.346572', None, '43a03d20', _ESTADO),
    ('fallida', '2026-11-26T15:21:01.837320', None, None, _LOGIN),
    ('fallida', '2026-11-26T15:21:49.692213', None, '48ca1fdd', _ESTADO),
    ('fallida', '2026-11-26T16:21:03.262365', None, '2bd81235', _ESTADO),
    ('fallida', '2026-11-26T17:21:13.997534', None, '1f64867d', _ESTADO),
    ('fallida', '2026-11-26T18:21:03.748728', None, None, _LOGIN),
    ('fallida', '2026-11-26T18:21:59.584739', None, 'b2052f1d', _ESTADO),
    ('fallida', '2026-11-27T07:52:17.975367', None, None, _LOGIN),
    ('fallida', '2026-11-27T07:52:51.930990', None, None, _LOGIN),
    ('fallida', '2026-11-27T07:53:29.991705', None, None, _LOGIN),
    ('aplicada', '2026-11-27T08:17:10.973105', '4c3b3ded', '50dbc304', None),
    ('fallida', '2026-11-27T08:28:29.806560', None, None, _LOGIN),
    ('aplicada', '2026-11-27T08:36:09.240105', '0a7222ff', 'b5309a73', None),
]
TCG_REAL = [(e, _u(t), h, m, mo) for (e, t, h, m, mo) in TCG_REAL]
ULTIMA_BUENA_26 = _u('2026-11-26T11:23:27.594722')   # 12:23 de Madrid


# ===========================================================================
# LOS ESCENARIOS (cada uno corre el vigilante REAL de punta a punta, con el reloj fijo)
# ===========================================================================
def _escenario(ahora, disp, **extra):
    """Los proveedores que el escenario no nombra traen una aplicada de hace 5 minutos: al dia
    con cualquier horario, para que no opinen."""
    disp = dict(disp)
    for p in VIGILADOS:
        disp.setdefault(p, [('aplicada', ahora - timedelta(minutes=5), 'h-' + p, 'm-' + p, None)])
    esc = {'ahora': ahora, 'params': PARAMETROS, 'disp': disp, 'marca': None}
    esc.update(extra)
    return esc


def _hasta(historia, ahora):
    return [x for x in historia if x[1] <= ahora]


def _marca_tcg(avisado_en, desde=ULTIMA_BUENA_26):
    return {'TCG': {'desde': desde.isoformat(), 'avisado_en': avisado_en.isoformat()}}


A_1445, A_1455 = _m('2026-11-26T14:45:00'), _m('2026-11-26T14:55:00')


def _escenario_de(caso):
    # --- El caso real de TCG -------------------------------------------------------------------
    if caso == 'todo_al_dia':
        return _escenario(_m('2026-11-25T12:55:00'), {})
    if caso == 'tcg_26nov_1445':
        return _escenario(A_1445, {'TCG': _hasta(TCG_REAL, A_1445)})
    if caso in ('tcg_26nov_1455', 'marca_ilegible', 'marca_no_escribible', 'telegram_falla',
                'telegram_400', 'ensayo'):
        return _escenario(A_1455, {'TCG': _hasta(TCG_REAL, A_1455)},
                          marca={'HEO': {'desde': None, 'avisado_en': None}} if caso == 'marca_ilegible' else None,
                          ensayo=(caso == 'ensayo'), fallo=caso)
    if caso == 'marca_vieja':
        return _escenario(A_1455, {'TCG': _hasta(TCG_REAL, A_1455)}, marca={'TCG': '2026-11-26'})
    if caso == 'tcg_26nov_1655_ya_avisado':
        a = _m('2026-11-26T16:55:00')
        return _escenario(a, {'TCG': _hasta(TCG_REAL, a)}, marca=_marca_tcg(A_1455))
    if caso == 'tcg_26nov_2055_recordatorio':
        a = _m('2026-11-26T20:55:00')
        return _escenario(a, {'TCG': _hasta(TCG_REAL, a)}, marca=_marca_tcg(A_1455))
    if caso == 'tcg_26nov_2330_noche':
        a = _m('2026-11-26T23:30:00')
        return _escenario(a, {'TCG': _hasta(TCG_REAL, a)})
    if caso == 'tcg_27nov_0955_vuelta':
        a = _m('2026-11-27T09:55:00')
        return _escenario(a, {'TCG': _hasta(TCG_REAL, a)}, marca=_marca_tcg(_m('2026-11-27T07:55:00')))
    # --- Una «al dia» en medio ------------------------------------------------------------------
    # TCG el 26-nov: aplicada a las 12:23 (Madrid); la de las 13:20 sale «al dia» (misma huella) y
    # la de las 14:20 falla. A las 14:55 el plazo es la de las 13:20 y la «al dia» de las 13:21 lo
    # cumple: AL DIA. Con otra huella (contenido distinto que no se aplica), CADUCADO.
    if caso in ('tcg_al_dia_medio', 'tcg_al_dia_otra_huella'):
        h = 'b714a805' if caso == 'tcg_al_dia_medio' else 'otra-huella'
        return _escenario(A_1455, {'TCG': [
            ('aplicada', ULTIMA_BUENA_26, 'b714a805', 'f71a9488', None),
            ('rechazada', _m('2026-11-26T13:21:40'), h, 'md5-de-hoy', 'al día: el contenido es el mismo'),
            ('fallida', _m('2026-11-26T14:21:23'), None, None, _LOGIN)]})
    # OcioStock, una al dia a las 09:12: su «al dia» se reconoce por el md5 del fichero (no lleva
    # huella). Martes aplicada; miercoles «al dia»; jueves 09:55 sin nada. El plazo es la del
    # miercoles: AL DIA. Con otro md5, CADUCADO.
    if caso in ('ocio_al_dia_md5', 'ocio_md5_distinto'):
        m = 'f-martes' if caso == 'ocio_al_dia_md5' else 'f-otro'
        return _escenario(_m('2026-11-26T09:55:00'), {'OCIOSTOCK': [
            ('aplicada', _m('2026-11-24T09:13:10'), None, 'f-martes', None),
            ('rechazada', _m('2026-11-25T09:12:35'), None, m, 'al día: el fichero es el mismo')]})
    # --- Fines de semana ------------------------------------------------------------------------
    # OSMA, de lunes a viernes a las 07:15: aplicada el viernes 20-nov. El domingo, AL DIA (sin ninguna
    # prevista perdida el suelo no salta). El lunes a las 07:44, con la de las 07:15 sin vencer, AL DIA.
    # El lunes a las 07:55, perdida la del lunes y 72 h sin lectura buena: CADUCADO por el suelo (sin
    # el, el martes). El martes a las 07:55, CADUCADO por el horario.
    osma_vie = [('aplicada', _m('2026-11-20T07:16:02'), None, None, None)]
    if caso == 'osma_domingo':
        return _escenario(_m('2026-11-22T13:00:00'), {'OSMA': osma_vie})
    if caso == 'osma_lunes_0744':
        return _escenario(_m('2026-11-23T07:44:00'), {'OSMA': osma_vie})
    if caso == 'osma_lunes_0755':
        return _escenario(_m('2026-11-23T07:55:00'), {'OSMA': osma_vie})
    if caso == 'osma_martes_0755':
        return _escenario(_m('2026-11-24T07:55:00'), {'OSMA': osma_vie})
    # DBLine, de lunes a viernes de 07 a 21 (el sabado no esta en su horario): aplicada el viernes a
    # las 21:06. El sabado y el domingo, AL DIA (sin prevista perdida). El lunes a las 07:25, sin vencer
    # la de las 07:00, AL DIA. El lunes a las 07:55, perdida la de las 07:00 y 58,8 h sin lectura buena:
    # CADUCADO por el suelo. A las 09:55, por el horario.
    db_vie = [('aplicada', _m('2026-11-20T21:06:12'), 'h-db', None, None)]
    if caso == 'dbline_sabado':
        return _escenario(_m('2026-11-21T13:00:00'), {'DBLINE': db_vie})
    if caso == 'dbline_domingo':
        return _escenario(_m('2026-11-22T21:55:00'), {'DBLINE': db_vie})
    # DBLine muerto el viernes por la noche, con las del SABADO arrancando y fallando (lee el sabado,
    # aunque `horario_finde` este vacio): el suelo salta por los intentos fallidos -> el domingo a
    # las 07:55 (34,8 h). Sin ninguna pasada el sabado, el domingo a las 07:55 AL DIA (el lunes a las
    # 07:55, ya CADUCADO: dbline_lunes_0755).
    db_sab_falla = db_vie + [('fallida', _m('2026-11-21T%02d:06:00' % h), None, None, 'x') for h in range(7, 22)]
    if caso == 'dbline_sabado_fallidas_domingo_0755':
        return _escenario(_m('2026-11-22T07:55:00'), {'DBLINE': db_sab_falla})
    if caso == 'dbline_sabado_fallidas_sabado_2155':
        return _escenario(_m('2026-11-21T21:55:00'), {'DBLINE': _hasta(db_sab_falla, _m('2026-11-21T21:55:00'))})
    if caso == 'dbline_sin_pasadas_domingo_0755':
        return _escenario(_m('2026-11-22T07:55:00'), {'DBLINE': db_vie})
    # OSMA del viernes al lunes con una 'rechazada' «no ha regenerado» el sabado: no es un intento
    # fallido. El domingo a las 13:00, AL DIA.
    if caso == 'osma_rechazada_finde':
        return _escenario(_m('2026-11-22T13:00:00'), {'OSMA': osma_vie + [
            ('rechazada', _m('2026-11-21T07:16:00'), None, None, 'OSMA no ha regenerado el fichero')]})
    if caso == 'dbline_lunes_0725':
        return _escenario(_m('2026-11-23T07:25:00'), {'DBLINE': db_vie})
    if caso == 'dbline_lunes_0755':
        return _escenario(_m('2026-11-23T07:55:00'), {'DBLINE': db_vie})
    if caso == 'dbline_lunes_0955':
        return _escenario(_m('2026-11-23T09:55:00'), {'DBLINE': db_vie})
    # HEO, el fin de semana a las 08 y a las 09: aplicada el sabado a las 09:06. El domingo a las
    # 07:55, antes de su primera, AL DIA.
    if caso == 'heo_domingo_0755':
        return _escenario(_m('2026-11-22T07:55:00'),
                          {'HEO': [('aplicada', _m('2026-11-21T09:06:30'), None, None, None)]})
    # --- EL SUELO DE 26 H (quien dirige, revision del #403): nadie avisa mas tarde que el viejo ---
    # OcioStock, una al dia a las 09:12: aplicada el martes 24 a las 09:13; el miercoles fallan la de
    # las 09:12 y sus repasos de las 13 y las 17. Sin el suelo, el plazo seria la del martes hasta el
    # jueves a las 09:42 (avisaria el jueves a las 09:55, ~48 h). Con el: el miercoles a las 10:55
    # van 25,7 h -> AL DIA; a las 11:55, 26,7 h y una perdida -> CADUCADO.
    ocio_d1 = [('aplicada', _m('2026-11-24T09:13:10'), None, 'f-mar', None),
               ('fallida', _m('2026-11-25T09:13:00'), None, None, 'x'),
               ('fallida', _m('2026-11-25T13:13:00'), None, None, 'x'),
               ('fallida', _m('2026-11-25T17:13:00'), None, None, 'x')]
    if caso in ('ocio_d1_1055', 'ocio_d1_1155'):
        a = _m('2026-11-25T10:55:00' if caso == 'ocio_d1_1055' else '2026-11-25T11:55:00')
        return _escenario(a, {'OCIOSTOCK': _hasta(ocio_d1, a)})
    # TCG el fin de semana (una a las 12:20): ultima buena el viernes 20 a las 19:22; el sabado falla
    # la de las 12:20. A las 20:55, 25,6 h -> AL DIA; a las 21:55, 26,6 h -> CADUCADO (sin el suelo,
    # el domingo a las 12:55).
    tcg_sab = [('aplicada', _m('2026-11-20T19:22:00'), 'h-vie', None, None),
               ('fallida', _m('2026-11-21T12:21:00'), None, None, 'x')]
    if caso in ('tcg_sabado_2055', 'tcg_sabado_2155'):
        a = _m('2026-11-21T20:55:00' if caso == 'tcg_sabado_2055' else '2026-11-21T21:55:00')
        return _escenario(a, {'TCG': tcg_sab})
    # OSMA, un martes normal: aplicada el lunes 23 a las 07:16, el martes falla. A las 07:55, 24,7 h
    # -> AL DIA; a las 09:55, 26,7 h -> CADUCADO (sin el suelo, el miercoles a las 07:55).
    if caso in ('osma_martes_tras_lunes_0755', 'osma_martes_tras_lunes_0955'):
        a = _m('2026-11-24T07:55:00' if caso.endswith('0755') else '2026-11-24T09:55:00')
        return _escenario(a, {'OSMA': [('aplicada', _m('2026-11-23T07:16:00'), None, None, None),
                                       ('fallida', _m('2026-11-24T07:16:00'), None, None, 'x')]})
    # HEO con UNA fallida suelta: sabado 21 a las 08:00 (ultima buena, el viernes a las 18:06: 14,8 h)
    # y lunes 23 a las 08:00 (ultima buena, el domingo a las 09:06: 23,8 h). A las 08:55, AL DIA.
    if caso == 'heo_sabado_suelta':
        return _escenario(_m('2026-11-21T08:55:00'), {'HEO': [
            ('aplicada', _m('2026-11-20T18:06:00'), None, None, None),
            ('fallida', _m('2026-11-21T08:01:00'), None, None, 'x')]})
    if caso == 'heo_lunes_suelta':
        return _escenario(_m('2026-11-23T08:55:00'), {'HEO': [
            ('aplicada', _m('2026-11-22T09:06:00'), None, None, None),
            ('fallida', _m('2026-11-23T08:01:00'), None, None, 'x')]})
    # --- EL TOPE DE LAS «AL DIA» (96 h desde la ultima aplicada; quien dirige, revision del #403) ---
    # TCG, el fin de semana: aplicada el viernes 20 a las 19:22 (huella h-vie) y «al dia» el sabado y el
    # domingo a las 12:21 y el lunes a las 09:21. El lunes a las 09:55 van 62,6 h desde la aplicada:
    # las «al dia» valen -> AL DIA.
    if caso == 'tcg_finde_al_dia':
        return _escenario(_m('2026-11-23T09:55:00'), {'TCG': [
            ('aplicada', _m('2026-11-20T19:22:00'), 'h-vie', None, None),
            ('rechazada', _m('2026-11-21T12:21:00'), 'h-vie', None, 'al día'),
            ('rechazada', _m('2026-11-22T12:21:00'), 'h-vie', None, 'al día'),
            ('rechazada', _m('2026-11-23T09:21:00'), 'h-vie', None, 'al día')]})
    # OcioStock con el MISMO md5 cuatro dias seguidos: aplicada el lunes 23 a las 09:13 y «al dia» de
    # martes a viernes a las 09:12. El jueves a las 09:55 (72,7 h), AL DIA; el viernes a las 09:55
    # (96,7 h), CADUCADO con su texto propio.
    ocio_igual = [('aplicada', _m('2026-11-23T09:13:00'), None, 'f-lun', None)] + [
        ('rechazada', _m('2026-11-%02dT09:12:40' % d), None, 'f-lun', 'al día') for d in (24, 25, 26, 27)]
    if caso in ('ocio_igual_jueves', 'ocio_igual_viernes'):
        a = _m('2026-11-26T09:55:00' if caso == 'ocio_igual_jueves' else '2026-11-27T09:55:00')
        return _escenario(a, {'OCIOSTOCK': _hasta(ocio_igual, a)})
    # --- El motivo, solo al Telegram -------------------------------------------------------------
    if caso == 'motivo_secreto':
        return _escenario(A_1455, {'TCG': [
            ('aplicada', ULTIMA_BUENA_26, 'b714a805', None, None),
            ('fallida', _m('2026-11-26T13:21:00'), None, None, 'x'),
            ('fallida', _m('2026-11-26T14:21:00'), None, None, 'MOTIVO-SECRETO <b>Tom & Jerry</b> "fila 7"')]})
    # --- La base -------------------------------------------------------------------------------
    if caso == 'lectura_falla':
        return _escenario(A_1455, {}, fallo=caso)
    if caso == 'lectura_vuelve':
        return _escenario(A_1455, {}, marca={'_LECTURA': {'desde': None, 'avisado_en': _m('2026-11-26T10:55:00').isoformat()}})
    if caso == 'sin_horario':
        return _escenario(A_1455, {}, params=[PARAMETROS[0]])
    return None


# ===========================================================================
# EL HIJO: monta los dobles y corre el vigilante de punta a punta
# ===========================================================================
def hijo(caso):
    import atexit

    ESC = _escenario_de(caso)
    if ESC is None:
        print('XX caso desconocido: %s' % caso)
        sys.exit(2)
    FALLO = ESC.get('fallo')
    ENVIADOS, SUBIDAS = [], []

    # El reloj: `from datetime import datetime` encontrara esta subclase.
    import datetime as _dtm

    class _Reloj(_dtm.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(ESC['ahora'].isoformat())

    _falso = types.ModuleType('datetime')
    _falso.__dict__.update({k: getattr(_dtm, k) for k in dir(_dtm) if not k.startswith('__')})
    _falso.datetime = _Reloj
    sys.modules['datetime'] = _falso

    ALMACEN = {}
    if ESC['marca'] is not None:
        ALMACEN['marca'] = json.dumps(ESC['marca']).encode('utf-8')

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Query:
        """Estricto a proposito: un filtro que no este aqui revienta (AttributeError) en vez de
        tragarse en silencio, que es como un doble deja pasar un vigilante que pregunta mal."""
        def __init__(self, tabla):
            self.tabla, self.eqs, self.gts, self.desc, self.n = tabla, {}, {}, False, None

        def select(self, columnas):
            self.columnas = columnas
            return self

        def eq(self, col, val):
            self.eqs[col] = val
            return self

        def gt(self, col, val):
            self.gts[col] = val
            return self

        def order(self, col, desc=False):
            assert col == 'terminada_en', col
            self.desc = desc
            return self

        def limit(self, n):
            self.n = n
            return self

        def execute(self):
            if FALLO == 'lectura_falla' and self.tabla == 'disp_pasada':
                raise RuntimeError('SECRETO-DE-LA-BASE: la lectura revienta a proposito')
            if self.tabla == 'disp_parametros':
                return _Resp([dict(r) for r in ESC['params']])
            assert self.tabla == 'disp_pasada', self.tabla
            filas = []
            for (estado, t, huella, md5, motivo) in ESC['disp'].get(self.eqs.get('proveedor'), []):
                if 'estado' in self.eqs and estado != self.eqs['estado']:
                    continue
                if 'terminada_en' in self.gts and not t > datetime.fromisoformat(
                        self.gts['terminada_en'].replace('Z', '+00:00')):
                    continue
                filas.append({'estado': estado, 'terminada_en': t.isoformat(), 'huella_contenido': huella,
                              'fichero_md5': md5, 'motivo': motivo, '_t': t})
            filas.sort(key=lambda r: r['_t'], reverse=self.desc)
            if self.n is not None:
                filas = filas[:self.n]
            for r in filas:
                del r['_t']
            return _Resp(filas)

    class _Bucket:
        def download(self, ruta):
            if FALLO == 'marca_ilegible':
                raise Exception('doble: Storage no responde a proposito')
            if 'marca' not in ALMACEN:
                raise Exception('404 ' + ruta)
            return ALMACEN['marca']

        def upload(self, ruta, data, opts=None):
            if FALLO == 'marca_no_escribible':
                raise Exception('doble: Storage no deja escribir a proposito')
            ALMACEN['marca'] = data
            SUBIDAS.append(1)
            return {'path': ruta}

    class _Cliente:
        def __init__(self):
            self.storage = types.SimpleNamespace(from_=lambda _b: _Bucket())

        def table(self, nombre):
            return _Query(nombre)

    def _post(url, data=None, timeout=None):
        if FALLO == 'telegram_falla':
            raise Exception('doble: Telegram no contesta a proposito')
        ENVIADOS.append((data or {}).get('text', ''))
        codigo = 400 if FALLO == 'telegram_400' else 200
        return types.SimpleNamespace(status_code=codigo, json=lambda: {'ok': codigo == 200})

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda url, key: _Cliente()
    sys.modules['requests'] = types.ModuleType('requests')
    sys.modules['requests'].post = _post

    os.environ['SUPABASE_URL'] = 'https://doble.local'
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    os.environ['TELEGRAM_TOKEN'] = 'FAKE-TG'
    os.environ['TELEGRAM_CHAT_ID'] = '123'
    os.environ['CENTINELA_ENSAYO'] = 'si' if ESC.get('ensayo') else ''

    @atexit.register
    def _informe():
        print('@@FIN_DEL_VIGILANTE@@')
        print('TELEGRAMS=%d' % len(ENVIADOS))
        print('TELEGRAM_TEXTO=%s' % json.dumps('\n=====\n'.join(ENVIADOS)))
        print('SUBIDAS=%d' % len(SUBIDAS))
        print('MARCA_FINAL=%s' % (ALMACEN['marca'].decode('utf-8').replace('\n', ' ')
                                  if 'marca' in ALMACEN else 'null'))

    import runpy
    # `CENTINELA_RUTA`: las ROTURAS (R) corren una copia estropeada.
    runpy.run_path(os.environ.get('CENTINELA_RUTA', RUTA), run_name='__main__')


if len(sys.argv) > 2 and sys.argv[1] == '--hijo':
    hijo(sys.argv[2])
    sys.exit(0)


# ===========================================================================
# EL PADRE: los asserts
# ===========================================================================
FUENTE = io.open(RUTA, encoding='utf-8').read()
ARBOL = ast.parse(FUENTE, RUTA)
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def _nodo(nombre):
    for n in ARBOL.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return n
    print('XX %s ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


CONSTANTES = ('DIAS_ATRAS', 'DIAS_ADELANTE', 'SUELO_H', 'INTENTOS_FALLIDOS', 'TOPE_AL_DIA_H', 'RECORDATORIO_H', 'HOLGURA_RECORDATORIO_MIN', 'HORAS_DE_AVISAR', 'RELOJ', 'MESES', 'LECTURA')
FUNCIONES = ('previstas', 'plazo', 'esta_caducado', 'suelo_vencido', 'es_al_dia', 'al_dia_vale', 'lectura_buena', 'diagnostico', '_iso',
             'eventos', 'marca_tras', 'hora_de_avisar', 'fecha_madrid', 'hora_madrid', '_motivo', '_detalle',
             'texto_de')
_ns = {'timedelta': timedelta, 'datetime': datetime, 'timezone': timezone, 'MADRID': MAD, 'html': _html}
exec(compile(ast.fix_missing_locations(ast.Module(body=[_nodo(n) for n in CONSTANTES + FUNCIONES],
                                                  type_ignores=[])), RUTA, 'exec'), _ns)
eq('(A) MADRID es Europe/Madrid', ast.unparse(_nodo('MADRID').value), "ZoneInfo('Europe/Madrid')")
plazo, esta_caducado, diagnostico = _ns['plazo'], _ns['esta_caducado'], _ns['diagnostico']
eventos, marca_tras, hora_de_avisar = _ns['eventos'], _ns['marca_tras'], _ns['hora_de_avisar']
print('extraidas de %s: %s' % (RUTA, ', '.join(CONSTANTES + FUNCIONES)))
print()


def _pasadas(historia):
    return [{'estado': e, 't': t, 'huella': h, 'md5': m, 'motivo': mo} for (e, t, h, m, mo) in historia]


def _fm(t):
    return None if t is None else t.astimezone(MAD).strftime('%Y-%m-%d %H:%M')


# ---------------------------------------------------------------------------
# (A) La regla, contra la propia migracion y contra el caso real
# ---------------------------------------------------------------------------
eq('(A) como en disp_frescura_en: de 15 dias atras a 8 adelante, y 2 pasadas para avisar',
   (_ns['DIAS_ATRAS'], _ns['DIAS_ADELANTE']), (15, 8))
# La guarda (g) de 20260930160000_disp_frescura_segun_horario.sql (v2), con el horario de HEO de
# aquel dia (de 8 a 21 entre semana, 8 y 9 el fin de semana, en punto, 20 min de margen):
_HEO_MIG = {'horario_laborables': list(range(8, 22)), 'horario_finde': [8, 9], 'horario_minuto': 0,
            'horario_margen_min': 20, 'pasadas_para_avisar': 2}
for _ahora, _ultima, _sig in (('2026-10-03 14:00', '2026-10-03 09:00', '2026-10-04 08:00'),
                              ('2026-10-25 12:00', '2026-10-25 09:00', '2026-10-26 08:00'),
                              ('2027-03-29 08:10', '2027-03-28 09:00', '2027-03-29 09:00')):
    _p = plazo(_HEO_MIG, _m(_ahora.replace(' ', 'T')))
    eq('(A) 🔴 [guarda (g) de la migracion] a las %s de Madrid, ultima prevista %s y siguiente %s'
       % (_ahora, _ultima, _sig), (_fm(_p['ultima_prevista']), _fm(_p['siguiente_prevista'])), (_ultima, _sig))

# El caso real de TCG: la ultima buena, las 12:23 del 26-nov; previstas a las :20, 30 min de margen.
_tcg = _pasadas(TCG_REAL)
_d1449 = diagnostico(PAR['TCG'], _tcg, _m('2026-11-26T14:49:59'))
_d1450 = diagnostico(PAR['TCG'], _tcg, _m('2026-11-26T14:50:00'))
eq('(A) 🔴 [TCG 26-nov] a las 14:49:59 la de las 14:20 aun no ha vencido: plazo, la de las 12:20 -> AL DIA',
   (_fm(_d1449['umbral']), _d1449['caducado']), ('2026-11-26 12:20', False))
eq('(A) 🔴 [TCG 26-nov] a las 14:50:00 han vencido la de las 13:20 y la de las 14:20 sin ninguna buena -> CADUCADO',
   (_fm(_d1450['umbral']), _d1450['caducado'], [_fm(t) for t in _d1450['perdidas']]),
   ('2026-11-26 13:20', True, ['2026-11-26 13:20', '2026-11-26 14:20']))
eq('(A) [TCG 26-nov] …desde la ultima buena de las 12:23, con 3 intentos fallidos (13:21, 14:21 y 14:21)',
   (_fm(_d1450['ultima_buena']), len(_d1450['fallos'])), ('2026-11-26 12:23', 3))
# Y la regla de antes (mas de 26 h desde la ultima escritura), para que conste el porque:
_viejo = ULTIMA_BUENA_26 + timedelta(hours=26)
eq('(A) [la regla de antes] no habria saltado hasta las 14:23 del 27-nov', _fm(_viejo), '2026-11-27 14:23')
eq('(A) …es decir, %.1f h mas tarde que esta' % ((_viejo - _m('2026-11-26T14:50:00')).total_seconds() / 3600),
   round((_viejo - _m('2026-11-26T14:50:00')).total_seconds() / 3600, 1), 23.6)
_d0918 = diagnostico(PAR['TCG'], _tcg, _m('2026-11-27T09:18:00'))
eq('(A) [TCG 27-nov] con la aplicada de las 09:17, AL DIA', (_d0918['caducado'], _fm(_d0918['ultima_buena'])),
   (False, '2026-11-27 09:17'))
eq('(A) sin ninguna lectura buena, CADUCADO: no saber no es estar bien', esta_caducado(None, None), True)
eq('(A) con lectura buena y sin plazo todavia (un horario recien nacido), no', esta_caducado(_u('2026-11-01T00:00:00'), None),
   False)
eq('(A) 🔴 una rechazada SIN huella ni md5 no casa con una aplicada sin huella ni md5 (vacio no es igual)',
   _ns['es_al_dia']({'estado': 'rechazada', 'huella': None, 'md5': None}, {'huella': None, 'md5': None}), False)
eq('(A) 🔴 una rechazada_vaciado con la misma huella NO es «al dia» (es otro estado)',
   _ns['es_al_dia']({'estado': 'rechazada_vaciado', 'huella': 'h', 'md5': None}, {'huella': 'h', 'md5': None}), False)

# Los eventos y la marca, como funciones puras
_ah = _m('2026-11-26T20:55:00')
_cad = {'TCG': {'caducado': True, 'ultima_buena': ULTIMA_BUENA_26}}
eq('(A) 🔴 FALLA EN ABIERTO: con la marca vacia, lo caducado sale como aviso nuevo',
   eventos(_cad, {}, _ah, 6), [('caducado', 'TCG')])
eq('(A) con la marca de hace 6 h y la misma lectura de partida, recordatorio',
   eventos(_cad, _marca_tcg(_m('2026-11-26T14:55:00')), _ah, 6), [('recordatorio', 'TCG')])
eq('(A) 🔴 con la de hace 5 h 59 (la vuelta anterior arranco un minuto tarde), recordatorio igual: la holgura',
   eventos(_cad, _marca_tcg(_m('2026-11-26T14:56:00')), _ah, 6), [('recordatorio', 'TCG')])
eq('(A) con la de hace 5 h 44, nada (la holgura es de 15 min, no de horas)',
   eventos(_cad, _marca_tcg(_m('2026-11-26T15:11:00')), _ah, 6), [])
eq('(A) 🔴 con otra lectura de partida (volvio y se volvio a caer sin que se viera), aviso nuevo',
   eventos(_cad, _marca_tcg(_m('2026-11-26T20:00:00'), desde=_u('2026-11-20T10:00:00')), _ah, 6),
   [('caducado', 'TCG')])
eq('(A) la marca del formato de antes ({proveedor: dia}) cuenta como no avisada',
   eventos(_cad, {'TCG': '2026-11-26'}, _ah, 6), [('caducado', 'TCG')])
eq('(A) al dia y avisado antes: vuelta', eventos({'TCG': {'caducado': False, 'ultima_buena': _ah}},
                                                 _marca_tcg(_ah), _ah, 6), [('vuelta', 'TCG')])
eq('(A) al dia y sin avisar: nada', eventos({'TCG': {'caducado': False, 'ultima_buena': _ah}}, {}, _ah, 6), [])
eq('(A) la marca tras enviar: lo que vuelve se borra, lo avisado se apunta, lo demas se queda y lo viejo se tira',
   marca_tras({'TCG': {'desde': 'x', 'avisado_en': 'y'}, 'HEO': {'desde': 'a', 'avisado_en': 'b'}, 'OSMA': '2026-11-26'},
              [('vuelta', 'TCG'), ('caducado', 'DBLINE')],
              {'TCG': {'ultima_buena': _ah}, 'DBLINE': {'ultima_buena': ULTIMA_BUENA_26}}, _ah),
   {'HEO': {'desde': 'a', 'avisado_en': 'b'},
    'DBLINE': {'desde': ULTIMA_BUENA_26.isoformat(), 'avisado_en': _ah.isoformat()}})
eq('(A) suena de 07:00 a 22:59 de Madrid, y no a las 06:59 ni a las 23:00',
   [hora_de_avisar(_m(t)) for t in ('2026-11-26T06:59:00', '2026-11-26T07:00:00', '2026-11-26T22:59:00',
                                    '2026-11-26T23:00:00')], [False, True, True, False])

# ---------------------------------------------------------------------------
# (B) Por estructura: ni un horario ni un proveedor escritos en el vigilante
# ---------------------------------------------------------------------------
print()
_textos = [n.value for n in ast.walk(ARBOL) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
eq('(B) 🔴 el vigilante no nombra a ningun proveedor: los saca de disp_parametros',
   sorted(set(_textos) & set(VIGILADOS + ['BEMS'])), [])
eq('(B) 🔴 ni queda la tabla de horarios copiada a mano (HORARIOS)',
   [n.targets[0].id for n in ARBOL.body if isinstance(n, ast.Assign)
    and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'HORARIOS'], [])

# ---------------------------------------------------------------------------
# (G) El reloj de cron-job.org contra los horarios, y el workflow
# ---------------------------------------------------------------------------
print()
RELOJ = _ns['RELOJ']
_ticks = [h * 60 + RELOJ['minuto'] for h in range(RELOJ['desde_h'], RELOJ['hasta_h'] + 1)]
print('    el reloj de cron-job.org: a las :%02d de %02d a %02d (Madrid), todos los dias'
      % (RELOJ['minuto'], RELOJ['desde_h'], RELOJ['hasta_h']))
for _p in VIGILADOS:
    _r = PAR[_p]
    _peor = 0
    _sin = []
    for _h in sorted(set(_r['horario_laborables']) | set(_r['horario_finde'])):
        _vence = _h * 60 + _r['horario_minuto'] + _r['horario_margen_min']
        _sig = [t for t in _ticks if t >= _vence]
        if not _sig:
            _sin.append(_h)
        else:
            _peor = max(_peor, _sig[0] - _vence)
    print('    %-10s su lectura mas tardia que vence se mira, como mucho, %d min despues' % (_p, _peor))
    eq('(G) 🔴 [%s] toda lectura vencida de su horario se mira en menos de una hora' % _p,
       (_sin, _peor < 60), ([], True))
eq('(G) 🔴 ninguna vuelta del reloj cae en horas de silencio (si no, el aviso esperaria a la mañana)',
   all(_ns['HORAS_DE_AVISAR'][0] <= h < _ns['HORAS_DE_AVISAR'][1]
       for h in range(RELOJ['desde_h'], RELOJ['hasta_h'] + 1)), True)
eq('(G) el recordatorio, cada 6 h como mucho', _ns['RECORDATORIO_H'], 6)
_doc = yaml.safe_load(io.open(os.path.join('.github', 'workflows', 'centinela-escaner.yml'), encoding='utf-8'))
_on = _doc.get('on', _doc.get(True)) or {}   # 🔑 `on:` se lee como el booleano True
_disp = _on.get('workflow_dispatch') or {}
eq('(G) 🔴 se lanza con workflow_dispatch (cron-job.org), con el ensayo APAGADO por defecto',
   (_disp.get('inputs', {}).get('ensayo', {}).get('default'),
    _disp.get('inputs', {}).get('ensayo', {}).get('options')), ('no', ['no', 'si']))
eq('(G) y el schedule: de GitHub se queda de respaldo, UNO', len(_on.get('schedule') or []), 1)
_paso = [s for s in _doc['jobs']['centinela']['steps'] if 'centinela_escaner.py' in str(s.get('run'))]
eq('(G) 🔴 el paso que lanza el vigilante le pasa la llave de servicio y el ensayo, FORZADO fuera de main',
   (len(_paso), _paso[0]['env'].get('CENTINELA_ENSAYO'), 'SUPABASE_SERVICE_KEY' in _paso[0]['env']),
   (1, "${{ github.ref != 'refs/heads/main' && 'si' || inputs.ensayo }}", True))

# ---------------------------------------------------------------------------
# (C) De punta a punta, cada caso en su proceso
# ---------------------------------------------------------------------------
print()


def correr(caso, ruta=None):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if ruta:
        env['CENTINELA_RUTA'] = ruta
    p = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', env=env)
    out = (p.stdout or '') + (p.stderr or '')
    registro = out.split('@@FIN_DEL_VIGILANTE@@')[0]      # lo que escribe el vigilante, sin el informe del doble

    def campo(clave):
        m = re.search(r'^%s=(.*)$' % clave, out, re.M)
        return m.group(1) if m else None

    return {'codigo': p.returncode, 'salida': out, 'registro': registro,
            'veredicto': {v: (re.search(r'^  %s +ultima buena .*-> (CADUCADO|al dia)$' % v, registro, re.M)
                              or [None, None])[1] for v in VIGILADOS},
            'telegrams': int(campo('TELEGRAMS') or -1),
            'texto': json.loads(campo('TELEGRAM_TEXTO') or '""'),
            'subidas': int(campo('SUBIDAS') or -1),
            'marca': json.loads(campo('MARCA_FINAL') or 'null')}


_AL_DIA = {p: 'al dia' for p in VIGILADOS}

_r = correr('todo_al_dia')
eq('(C) [todo_al_dia] VERDE, cero Telegram, la marca sin tocar, los cinco al dia',
   (_r['codigo'], _r['telegrams'], _r['subidas'], _r['veredicto']), (0, 0, 0, _AL_DIA))
eq('(C) [todo_al_dia] 🔴 los cinco en el registro, y BEMS (sin horario) no',
   (len(re.findall(r'^  \w+ +ultima buena', _r['registro'], re.M)), 'BEMS' in _r['registro']), (5, False))

# --- El caso real de TCG ---------------------------------------------------------
print()
_r = correr('tcg_26nov_1445')
eq('(C) 🔴 [tcg_26nov_1445] a las 14:45 del 26-nov (13:20 perdida, 14:20 sin vencer): VERDE, cero Telegram',
   (_r['codigo'], _r['telegrams'], _r['veredicto']['TCG']), (0, 0, 'al dia'))
_r = correr('tcg_26nov_1455')
eq('(C) 🔴 [tcg_26nov_1455] a las 14:55 (la primera vuelta del reloj tras las 14:50): ROJO, SOLO TCG, UN Telegram',
   (_r['codigo'], _r['veredicto'], _r['telegrams']), (1, dict(_AL_DIA, TCG='CADUCADO'), 1))
_t = _r['texto']
eq('(C) 🔴 [tcg_26nov_1455] el aviso dice desde cuando, cuantas se han perdido y cuantos intentos fallaron',
   ['TCG no lee desde el 26-nov 12:23' in _t, '2 lectura(s) prevista(s) sin ninguna buena (13:20, 14:20)' in _t,
    '3 intento(s) fallido(s)' in _t], [True] * 3)
eq('(C) 🔴 [tcg_26nov_1455] …el motivo del ultimo fallo, y que el Escaneo PRO y Reponer estan con datos de esa hora',
   ['Último fallo (26-nov 14:21, fallida): «%s»' % _html.escape(_ESTADO) in _t,
    'El Escaneo PRO y Reponer de TCG están con los datos del 26-nov 12:23.' in _t], [True, True])
eq('(C) [tcg_26nov_1455] la marca queda escrita: TCG, desde las 12:23, avisado a las 14:55',
   _r['marca'], {'TCG': {'desde': ULTIMA_BUENA_26.isoformat(), 'avisado_en': A_1455.isoformat()}})
eq('(C) 🔴 [tcg_26nov_1455] REPO PUBLICO: el motivo no sale en el registro',
   ('Estado producto' in _r['registro'], 'formulario' in _r['registro']), (False, False))

_r = correr('tcg_26nov_1655_ya_avisado')
eq('(C) 🔴 [tcg_26nov_1655_ya_avisado] avisado hace 2 h: CERO Telegram, pero el run sigue ROJO y lo dice',
   (_r['telegrams'], _r['codigo'], 'TCG: ya avisado hace menos de 6 h' in _r['registro'], _r['subidas']),
   (0, 1, True, 0))
_r = correr('tcg_26nov_2055_recordatorio')
eq('(C) 🔴 [tcg_26nov_2055_recordatorio] a las 6 h, UN recordatorio que dice cuanto lleva',
   (_r['telegrams'], 'TCG sigue sin leer</b>, desde el 26-nov 12:23 (9 h)' in _r['texto'],
    _r['marca']['TCG']['avisado_en']), (1, True, _m('2026-11-26T20:55:00').isoformat()))
_r = correr('tcg_26nov_2330_noche')
eq('(C) 🔴 [tcg_26nov_2330_noche] a las 23:30 no suena ni toca la marca, pero el run es ROJO y lo dice',
   (_r['telegrams'], _r['subidas'], _r['codigo'], 'fuera de hora (23:30 Madrid)' in _r['registro']), (0, 0, 1, True))
_r = correr('tcg_27nov_0955_vuelta')
eq('(C) 🔴 [tcg_27nov_0955_vuelta] con la historia real del 27-nov: VERDE y UN «TCG vuelve a leer, tras 21 h»',
   (_r['codigo'], _r['telegrams'], '✅ <b>TCG vuelve a leer, tras 21 h</b>' in _r['texto']), (0, 1, True))
eq('(C) [tcg_27nov_0955_vuelta] …y TCG sale de la marca', _r['marca'], {})

# --- Las «al dia» ---------------------------------------------------------------
print()
_r = correr('tcg_al_dia_medio')
eq('(C) 🔴 [tcg_al_dia_medio] una «al dia» (misma huella) en la de las 13:20 cuenta como buena: VERDE',
   (_r['codigo'], _r['telegrams'], _r['veredicto']['TCG']), (0, 0, 'al dia'))
eq('(C) [tcg_al_dia_medio] …y la ultima buena que dice el registro es la «al dia» (12:21 UTC)',
   bool(re.search(r'^  TCG +ultima buena 2026-11-26 12:21 UTC', _r['registro'], re.M)), True)
_r = correr('tcg_al_dia_otra_huella')
eq('(C) 🔴 [tcg_al_dia_otra_huella] la misma rechazada con OTRO contenido no cuenta: ROJO',
   (_r['codigo'], _r['veredicto']['TCG'], _r['telegrams']), (1, 'CADUCADO', 1))
_r = correr('ocio_al_dia_md5')
eq('(C) 🔴 [ocio_al_dia_md5] la «al dia» de OcioStock (mismo md5, sin huella) cuenta: VERDE',
   (_r['codigo'], _r['veredicto']['OCIOSTOCK']), (0, 'al dia'))
_r = correr('ocio_md5_distinto')
eq('(C) 🔴 [ocio_md5_distinto] con otro md5, no: ROJO', (_r['codigo'], _r['veredicto']['OCIOSTOCK']), (1, 'CADUCADO'))

# --- Fines de semana -------------------------------------------------------------
print()
for _caso, _esperado in (('osma_domingo', 'al dia'), ('osma_lunes_0744', 'al dia'), ('osma_martes_0755', 'CADUCADO'),
                         ('dbline_sabado', 'al dia'), ('dbline_domingo', 'al dia'), ('dbline_lunes_0725', 'al dia'),
                         ('dbline_lunes_0955', 'CADUCADO'), ('heo_domingo_0755', 'al dia')):
    _prov = _caso.split('_')[0].upper()
    _r = correr(_caso)
    eq('(C) 🔴 [%s] %s %s' % (_caso, _prov, 'sin falsa alarma: VERDE' if _esperado == 'al dia'
                              else 'entre semana, sin sus dos lecturas: ROJO'),
       (_r['codigo'], _r['veredicto']), (0 if _esperado == 'al dia' else 1, dict(_AL_DIA, **{_prov: _esperado})))

# --- El suelo de 26 h: nadie avisa mas tarde que el vigilante viejo ------------------
print()
for _caso, _prov, _esperado, _dice in (
        ('ocio_d1_1055', 'OCIOSTOCK', 'al dia', 'el dia siguiente a las 10:55 (25,7 h): aun no'),
        ('ocio_d1_1155', 'OCIOSTOCK', 'CADUCADO', 'a las 11:55 (26,7 h, una perdida): SI, y no el D+2 a las 09:55'),
        ('osma_lunes_0755', 'OSMA', 'CADUCADO', 'el lunes perdido avisa el lunes a las 07:55 (72 h), no el martes'),
        ('osma_martes_tras_lunes_0755', 'OSMA', 'al dia', 'un martes perdido, a las 07:55 (24,7 h): aun no'),
        ('osma_martes_tras_lunes_0955', 'OSMA', 'CADUCADO', '...a las 09:55 (26,7 h): SI'),
        ('tcg_sabado_2055', 'TCG', 'al dia', 'el sabado perdido, a las 20:55 (25,6 h): aun no'),
        ('tcg_sabado_2155', 'TCG', 'CADUCADO', '...a las 21:55 (26,6 h): SI, y no el domingo a las 12:55'),
        ('heo_sabado_suelta', 'HEO', 'al dia', 'una fallida suelta el sabado a las 08:00 (14,8 h): NO avisa'),
        ('heo_lunes_suelta', 'HEO', 'al dia', 'una fallida suelta el lunes a las 08:00 (23,8 h): NO avisa'),
        ('dbline_lunes_0755', 'DBLINE', 'CADUCADO',
         'la primera del lunes perdida (58,8 h desde el viernes): avisa a las 07:55')):
    _r = correr(_caso)
    eq('(C) 🔴 [%s] %s: %s' % (_caso, _prov, _dice),
       (_r['codigo'], _r['veredicto']), (0 if _esperado == 'al dia' else 1, dict(_AL_DIA, **{_prov: _esperado})))
eq('(A) el suelo son 26 h, las del vigilante viejo', _ns['SUELO_H'], 26)
eq('(A) 🔴 el suelo NO salta sin ninguna prevista perdida, lleve las horas que lleve (el fin de semana de OSMA)',
   _ns['suelo_vencido'](_m('2026-11-20T07:16:00'), [], [], _m('2026-11-23T07:44:00')), False)
eq('(A) ...ni sin lectura buena (eso ya es caducado por la otra regla)',
   _ns['suelo_vencido'](None, [1], [], _m('2026-11-23T07:44:00')), False)
eq('(A) con una perdida: 26 h justas no, 26 h y un minuto si (mas de 26)',
   [_ns['suelo_vencido'](_m('2026-11-24T09:13:00'), [1], [], _m(t))
    for t in ('2026-11-25T11:13:00', '2026-11-25T11:14:00')], [False, True])

eq('(A) 🔴 sin prevista perdida pero con un intento fallido, el suelo SI salta pasadas las 26 h',
   _ns['suelo_vencido'](_m('2026-11-20T21:06:00'), [], [1], _m('2026-11-22T07:55:00')), True)
eq('(A) los intentos fallidos son las fallida y las rechazada_vaciado; una rechazada a secas, no',
   tuple(_ns['INTENTOS_FALLIDOS']), ('fallida', 'rechazada_vaciado'))
for _caso, _prov, _esperado, _dice in (
        ('dbline_sabado_fallidas_sabado_2155', 'DBLINE', 'al dia', 'muerto el viernes 21:06 y el sabado fallando, '
         'el sabado a las 21:55 (24,8 h): aun no'),
        ('dbline_sabado_fallidas_domingo_0755', 'DBLINE', 'CADUCADO', '…el domingo a las 07:55 (34,8 h, intentos '
         'fallidos): SI, como el viejo, sin copiar ningun horario'),
        ('dbline_sin_pasadas_domingo_0755', 'DBLINE', 'al dia', 'el mismo viernes sin NINGUNA pasada el sabado: el '
         'domingo a las 07:55, aun no (el lunes a las 07:55, si)'),
        ('osma_rechazada_finde', 'OSMA', 'al dia', 'una rechazada «no ha regenerado» el sabado no es un intento '
         'fallido: el domingo, sin aviso')):
    _r = correr(_caso)
    eq('(C) 🔴 [%s] %s: %s' % (_caso, _prov, _dice),
       (_r['codigo'], _r['veredicto']), (0 if _esperado == 'al dia' else 1, dict(_AL_DIA, **{_prov: _esperado})))

# --- El tope de las «al dia»: 96 h sin ninguna aplicada es un dato viejo ------------
print()
eq('(A) el tope de las «al dia» son 96 h desde la ultima aplicada', _ns['TOPE_AL_DIA_H'], 96)
eq('(A) 🔴 95 h 59 min, la «al dia» vale; 96 h justas, ya no',
   [_ns['al_dia_vale'](_m('2026-11-23T09:13:00'), _m(t)) for t in ('2026-11-27T09:12:00', '2026-11-27T09:13:00')],
   [True, False])
_r = correr('tcg_finde_al_dia')
eq('(C) 🔴 [tcg_finde_al_dia] TCG con «al dia» el sabado, el domingo y el lunes (62,6 h desde la aplicada): '
   'NO avisa', (_r['codigo'], _r['telegrams'], _r['veredicto']['TCG']), (0, 0, 'al dia'))
_r = correr('ocio_igual_jueves')
eq('(C) 🔴 [ocio_igual_jueves] OcioStock con el mismo md5 tres dias (72,7 h): AL DIA',
   (_r['codigo'], _r['veredicto']['OCIOSTOCK']), (0, 'al dia'))
_r = correr('ocio_igual_viernes')
eq('(C) 🔴 [ocio_igual_viernes] …el cuarto dia (96,7 h sin ninguna aplicada): ROJO, SOLO OcioStock, UN Telegram',
   (_r['codigo'], _r['veredicto'], _r['telegrams']), (1, dict(_AL_DIA, OCIOSTOCK='CADUCADO'), 1))
eq('(C) 🔴 [ocio_igual_viernes] con su texto propio, no el de «no lee»',
   ['OCIOSTOCK contesta, pero con el mismo contenido desde el 23-nov 09:13' in _r['texto'],
    '4 lectura(s) «al día» (la última, el 27-nov 09:12) y 0 intento(s) fallido(s)' in _r['texto'],
    'El Escaneo PRO y Reponer de OCIOSTOCK están con los datos del 23-nov 09:13.' in _r['texto'],
    'no lee desde' in _r['texto']], [True, True, True, False])
eq('(C) [ocio_igual_viernes] el registro lo dice, sin motivos',
   bool(re.search(r'^  OCIOSTOCK .*4 al dia \| MISMO CONTENIDO desde 2026-11-23 08:13 UTC -> CADUCADO$',
                  _r['registro'], re.M)), True)
eq('(C) [ocio_igual_viernes] la marca apunta desde la ultima aplicada',
   _r['marca']['OCIOSTOCK']['desde'], _m('2026-11-23T09:13:00').isoformat())

# --- El motivo, solo al Telegram ---------------------------------------------------
print()
_r = correr('motivo_secreto')
eq('(C) 🔴 [motivo_secreto] el motivo llega al Telegram ESCAPADO (va en HTML: un < suelto da un 400)',
   '«MOTIVO-SECRETO &lt;b&gt;Tom &amp; Jerry&lt;/b&gt; &quot;fila 7&quot;»' in _r['texto'], True)
eq('(C) 🔴 [motivo_secreto] REPO PUBLICO: y no sale en el registro del run', 'MOTIVO-SECRETO' in _r['registro'], False)

# --- La marca falla en abierto, y Telegram tiene que confirmar ---------------------
print()
_r = correr('marca_ilegible')
eq('(C) 🔴 [marca_ilegible] FALLA EN ABIERTO: se avisa igual, ROJO, y el registro dice por que',
   (_r['telegrams'], _r['codigo'], 'Se avisa IGUAL' in _r['registro']), (1, 1, True))
_r = correr('marca_no_escribible')
eq('(C) 🔴 [marca_no_escribible] el aviso sale igual, y se dice que se repetira',
   (_r['telegrams'], 'no se pudo guardar la marca' in _r['registro'], _r['marca']), (1, True, None))
_r = correr('marca_vieja')
eq('(C) 🔴 [marca_vieja] la marca de antes ({TCG: dia}) no calla el aviso, y se pasa al formato nuevo',
   (_r['telegrams'], _r['marca']), (1, {'TCG': {'desde': ULTIMA_BUENA_26.isoformat(), 'avisado_en': A_1455.isoformat()}}))
_r = correr('telegram_falla')
eq('(C) 🔴 [telegram_falla] si Telegram no contesta, la marca queda INTACTA y el run ROJO',
   (_r['subidas'], _r['marca'], _r['codigo'], 'la marca queda intacta' in _r['registro']), (0, None, 1, True))
_r = correr('telegram_400')
eq('(C) 🔴 [telegram_400] si Telegram contesta 400, tampoco se apunta como avisado',
   (_r['telegrams'], _r['subidas'], _r['codigo'], 'HTTP 400' in _r['registro']), (1, 0, 1, True))
_r = correr('ensayo')
eq('(C) 🔴 [ensayo] lee y lo dice, pero ni Telegram ni marca',
   (_r['telegrams'], _r['subidas'], _r['codigo'], 'CENTINELA ENSAYO' in _r['registro'],
    _r['veredicto']['TCG']), (0, 0, 1, True, 'CADUCADO'))

# --- La base ------------------------------------------------------------------------
print()
_r = correr('lectura_falla')
eq('(C) 🔴 [lectura_falla] la base no se lee: ROJO y UN Telegram (el vigilante ciego no calla)',
   (_r['codigo'], _r['telegrams'], 'no puede leer la base' in _r['texto'], 'SECRETO-DE-LA-BASE' in _r['texto']),
   (1, 1, True, True))
eq('(C) 🔴 [lectura_falla] REPO PUBLICO: el registro da el TIPO del error, no su texto',
   ('RuntimeError' in _r['registro'], 'SECRETO-DE-LA-BASE' in _r['registro']), (True, False))
_r = correr('lectura_vuelve')
eq('(C) [lectura_vuelve] cuando vuelve a leer, se dice, y sale de la marca',
   (_r['codigo'], _r['telegrams'], 'vuelve a leer la base' in _r['texto'], _r['marca']), (0, 1, True, {}))
_r = correr('sin_horario')
eq('(C) 🔴 [sin_horario] ningun proveedor con horario: ROJO y Telegram, nunca un verde que no vigila a nadie',
   (_r['codigo'], _r['telegrams'], 'ningún proveedor con horario' in _r['texto']), (1, 1, True))

# ---------------------------------------------------------------------------
# (R) Roturas de la regla: una copia estropeada por estructura tiene que cambiar el veredicto
# ---------------------------------------------------------------------------
print()


def estropeado(funcion, cambia):
    """Copia del vigilante con la funcion `funcion` cambiada por `cambia(nodo)`."""
    arbol = ast.parse(FUENTE, RUTA)
    hechos = [cambia(n) for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == funcion]
    assert hechos == [True], 'la rotura de %s no encontro lo que romper' % funcion
    ruta = os.path.join(tempfile.mkdtemp(), 'centinela_estropeado.py')
    with io.open(ruta, 'w', encoding='utf-8') as f:
        f.write(ast.unparse(ast.fix_missing_locations(arbol)))
    return ruta


def _tres_pasadas(fn):
    """`vencidas[n - 1]` -> `vencidas[n]`: hacen falta tres lecturas perdidas, no dos."""
    for nodo in ast.walk(fn):
        if (isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.BinOp)
                and isinstance(nodo.slice.op, ast.Sub)):
            nodo.slice = nodo.slice.left
            return True
    return False


def _sin_margen(fn):
    """`t + margen <= ahora` -> `t <= ahora`: una lectura vence en cuanto llega su hora."""
    for nodo in ast.walk(fn):
        if (isinstance(nodo, ast.Compare) and isinstance(nodo.left, ast.BinOp)
                and isinstance(nodo.left.op, ast.Add)):
            nodo.left = nodo.left.left
            return True
    return False


def _sin_al_dia(fn):
    """La funcion siempre falsa: con `es_al_dia`, una «al dia» deja de contar; con
    `suelo_vencido`, desaparece el suelo de 26 h."""
    fn.body = [ast.Return(value=ast.Constant(value=False))]
    return True


_r = correr('tcg_26nov_1455', ruta=estropeado('plazo', _tres_pasadas))
eq('(R) 🔴 con TRES lecturas perdidas en vez de dos, el caso real de las 14:55 sale VERDE (el banco lo caza)',
   (_r['codigo'], _r['veredicto']['TCG']), (0, 'al dia'))
_r = correr('tcg_26nov_1445', ruta=estropeado('plazo', _sin_margen))
eq('(R) 🔴 sin el margen, a las 14:45 ya saldria ROJO (el banco lo caza)', (_r['codigo'], _r['veredicto']['TCG']),
   (1, 'CADUCADO'))
_r = correr('tcg_al_dia_medio', ruta=estropeado('es_al_dia', _sin_al_dia))
eq('(R) 🔴 sin contar las «al dia», la de en medio daria un aviso falso (el banco lo caza)',
   (_r['codigo'], _r['veredicto']['TCG']), (1, 'CADUCADO'))
_r = correr('ocio_d1_1155', ruta=estropeado('suelo_vencido', _sin_al_dia))
eq('(R) 🔴 sin el suelo de 26 h, OcioStock el dia siguiente a las 11:55 sale VERDE (el banco lo caza)',
   (_r['codigo'], _r['veredicto']['OCIOSTOCK']), (0, 'al dia'))
def _siempre_vale(fn):
    """`al_dia_vale` siempre cierto: el tope de 96 h desaparece."""
    fn.body = [ast.Return(value=ast.Constant(value=True))]
    return True


def _sin_intentos(fn):
    """`perdidas or fallidos` -> `perdidas`: el suelo deja de saltar por los intentos fallidos."""
    for nodo in ast.walk(fn):
        if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.operand, ast.BoolOp) and isinstance(nodo.operand.op, ast.Or):
            nodo.operand = nodo.operand.values[0]
            return True
    return False


_r = correr('dbline_sabado_fallidas_domingo_0755', ruta=estropeado('suelo_vencido', _sin_intentos))
eq('(R) 🔴 sin la rama de los intentos fallidos, DBLine muerto el viernes sale VERDE el domingo (el banco lo caza)',
   (_r['codigo'], _r['veredicto']['DBLINE']), (0, 'al dia'))
_r = correr('ocio_igual_viernes', ruta=estropeado('al_dia_vale', _siempre_vale))
eq('(R) 🔴 sin el tope de 96 h, OcioStock con el mismo md5 cuatro dias sale VERDE (el banco lo caza)',
   (_r['codigo'], _r['veredicto']['OCIOSTOCK']), (0, 'al dia'))
_r = correr('tcg_26nov_1455', ruta=estropeado('plazo', lambda fn: True))
eq('(R) …y la copia SIN estropear (control) da lo mismo que el original: ROJO por TCG',
   (_r['codigo'], _r['veredicto']), (1, dict(_AL_DIA, TCG='CADUCADO')))

# ---------------------------------------------------------------------------
print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK (avisa a las dos lecturas perdidas de su horario, una «al dia» cuenta, el fin de semana no da '
      'falsas alarmas, y la marca falla en abierto)')
