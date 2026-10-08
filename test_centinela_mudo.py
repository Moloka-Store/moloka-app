# -*- coding: utf-8 -*-
"""Banco: el centinela avisa cuando un director lleva horas sin escribir.

EL FALLO QUE CIERRA (9 y 10-sep-2026). Los cuatro directores se quedaron sin
poder leer `productos` y empezaron a morir en el arranque. DBLine dejo de
escribir el 9-sep a las 10:31 UTC y OcioStock a las 15:01; no se supo hasta el
10-sep por la tarde. DOS DIAS con «Que reponer» y el trackeador ensenando el
catalogo de anteayer con toda la cara de estar al dia. El run de cada director
salia rojo en Actions, pero un rojo en Actions no llega a donde esta Fernando.

LA TRAMPA DE ESTE CONTROL, Y COMO SE ESQUIVA. Los tres proveedores de fichero NO
trabajan los domingos (medido: cero pasadas en cuatro domingos seguidos), asi que
su hueco normal mas largo es el del sabado al lunes: 44 h en DBLine. Un umbral en
horas BRUTAS tendria que ser de 50 h para no dar un aviso falso cada lunes -- o
sea, justo los dos dias de silencio que se vienen a evitar. Descontando las horas
de domingo, ese mismo hueco son 23 h y la X puede bajar a 26.

LA SEGUNDA TRAMPA: EL RUIDO (10-sep-2026). El centinela arranca 8 veces al dia y
un mudo lo es durante horas, asi que sin freno el movil suena 8 veces por el
mismo silencio -- y un aviso que suena ocho veces se aprende a ignorar en quince
dias. El freno es una marca en Storage, un aviso por proveedor y dia. Y el freno
tiene DOS condiciones que este banco exige:
  🔴 FALLA EN ABIERTO. Si la marca no se puede leer o no se puede escribir, se
     avisa IGUAL. Un mecanismo hecho para hablar menos no puede convertirse en
     uno que se calla cuando algo va mal: esa es exactamente la clase de silencio
     que costo dos dias (`productos` devolviendo cero filas sin error).
  🔴 EL AVISO DICE DESDE CUANDO. No «DBLine mudo», sino «DBLine lleva 27 h sin
     escribir (ultima: 2026-09-09 10:31 UTC)». Con un aviso al dia, saber si
     acaba de empezar o si lleva dos dias es la mitad de la informacion.

QUE SE PRUEBA, Y COMO:
  (A) LAS FUNCIONES REALES, sacadas de `centinela_escaner.py` con `ast` (POR
      ESTRUCTURA, no con un grep) y EJECUTADAS con las fechas del apagon de
      verdad y con un sabado-a-lunes de verdad.
  (B) POR ESTRUCTURA: que la tabla de horarios cubra EXACTAMENTE los directores
      que existen en `.github/workflows`. Un director nuevo que naciera sin su
      linea aqui seria un proveedor sin centinela, y el centinela saldria verde
      sin mirarlo -- que es la forma que tiene esta clase de control de mentir.
      Y que la X de cada uno este POR ENCIMA del hueco mayor medido: una X por
      debajo es un aviso falso cada semana, y un aviso falso semanal se aprende a
      ignorar en quince dias.
  (C) DE PUNTA A PUNTA, ocho veces, cada una en su PROCESO, con `supabase` y
      `requests` sustituidos por dobles en memoria (sin red, sin secretos).
      Los tres primeros son el centinela de siempre; los cinco ultimos, el freno:
        1. [al_dia]              -> exit 0, CERO Telegram.
        2. [mudo]                -> exit 1, UN Telegram, y la marca queda escrita.
        3. [ilegible]            -> exit 1: no saber no es estar bien.
        4. [ya_avisado]          -> exit 1 y CERO Telegram: ya sono hoy.
        5. [ayer]                -> exit 1 y UN Telegram: la marca es de AYER.
        6. [marca_ilegible]      -> exit 1 y UN Telegram: FALLA EN ABIERTO.
        7. [marca_no_escribible] -> exit 1, UN Telegram y aviso en el log.
        8. [telegram_falla]      -> exit 1 y la marca INTACTA: si no sono, no se
                                    apunta como sonado.
      Y en TODOS, las cuatro lineas del informe. Un centinela que solo escribe
      cuando salta no se puede auditar: el dia que calla no se distingue "estan
      todos al dia" de "no llego a mirar".
  (D) LAS DOS DIRECCIONES del descuento del domingo: el MISMO sabado-a-lunes sale
      "al dia" para quien descansa el domingo y MUDO para quien no. Sin ese
      contraste, (A) saldria verde tambien con un descuento que no descontara
      nada.
  (E) EL REPARTO del freno, como funcion pura, incluida la marca vacia.
  (F) LA LINEA DEL AVISO, como funcion pura: que empiece por las horas, que lleve
      la fecha de la ultima escritura, y que solo nombre el descuento del domingo
      cuando de verdad cambia el numero.
  (G) EL RELOJ. El cron se lee del .yml de VERDAD y la ventana en la que el plazo
      de cada proveedor puede vencerse sale de las cifras de HORARIOS (su franja
      de escritura + su X). Se exige que las cuatro pasadas cubran esa ventana con
      4 h de demora como mucho, y que ninguna ventana caiga de noche -- que es lo
      que permite no mirar entre las 18:00 y las 06:00 sin retrasar nada. Sin
      esto, «no hay pasadas de noche porque ningun plazo vence de noche» seria una
      frase bonita en un comentario; asi, si manana se mueve una franja, una X o
      una hora del cron, el banco se pone rojo solo.

  (H) 🆕 HEO Y OSMA EN EL ESCANER 2 (03-oct-2026). Dejan de vigilarse en
      `escaner_memoria` (el director viejo de HEO se apago a proposito el 01-oct) y
      pasan a la ultima pasada 'aplicada' de `disp_pasada`. Seis escenarios de punta
      a punta con el RELOJ FIJO (el banco no cambia segun el dia en que se corra) y
      señuelos en los dos almacenes: [foto_hoy] con la foto de produccion del
      03-oct, todo al dia; [heo_30h_martes], [osma_miercoles_10], [osma_sabado],
      [osma_lunes_06h] y [osma_lunes_10h].
  (R) ROTURAS A MANO, dentro del banco: se estropea una copia del centinela por
      estructura (HEO mirado otra vez en escaner_memoria, OSMA igual, OSMA sin el
      descuento del sabado) y se exige que la foto de hoy se ponga ROJA; mas la copia
      sin estropear como control. Un banco que no sabe ponerse rojo no prueba nada.

Las horas del caso [mudo] son 200 a proposito (mas de ocho dias) y no 40: con 40,
este banco cambiaria de resultado segun el dia de la semana en que se corriera.
"""
import ast
import io
import json
import os
import re
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone

import yaml

RUTA = 'centinela_escaner.py'


# ===========================================================================
# LOS ESCENARIOS CON RELOJ FIJO (HEO y OSMA en el escaner 2, 03-oct-2026)
# ---------------------------------------------------------------------------
# Cada uno fija el "ahora" y lo que hay en `escaner_memoria` y en `disp_pasada`, y
# el hijo corre el centinela REAL de punta a punta con ese reloj. Asi el banco no
# cambia de resultado segun el dia de la semana en que se corra (un martes y un
# sabado no son lo mismo para OSMA). Los DOS almacenes llevan señuelos a proposito:
#   - `escaner_memoria` de HEO y de OSMA lleva fechas que, de leerse, darian el
#     veredicto CONTRARIO al de `disp_pasada`;
#   - `disp_pasada` lleva pasadas 'rechazada'/'fallida' mas nuevas que la ultima
#     'aplicada': el doble solo las devuelve si el centinela NO filtra por estado.
# ===========================================================================
def _u(txt):
    return datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)


def _escenario(ahora, memoria, disp):
    # 🆕 07-oct-2026 (OC5): OCIOSTOCK tambien se vigila en `disp_pasada`. Un escenario
    #    que no hable de OcioStock lo trae al dia (una 'aplicada' de hace 2 h), para que
    #    no opine; los suyos lo ponen a mano.
    disp = dict(disp)
    disp.setdefault('OCIOSTOCK', [('aplicada', _u(ahora) - timedelta(hours=2))])
    return {'ahora': _u(ahora), 'memoria': memoria, 'disp': disp}


def _fresco(ahora, horas):
    return _u(ahora) - timedelta(hours=horas)


def _tres_al_dia(ahora):
    """DBLINE, OCIOSTOCK y TCG con 2 h de silencio en escaner_memoria: que no opinen.
    (Desde el 07-oct-2026 la de OCIOSTOCK es un señuelo: se le mira `disp_pasada`.)"""
    return {p: _fresco(ahora, 2) for p in ('DBLINE', 'OCIOSTOCK', 'TCG')}


# LA FOTO DE VERDAD: produccion, miercoles 07-oct-2026 a las 17:02 Madrid (15:02 UTC),
# leida con SQL de solo lectura (conector de lectura, encargo OC5). HEO lleva seis dias
# sin tocar escaner_memoria (el director viejo se apago el 01-oct) y OSMA dos meses: de
# mirarlas ahi saldrian MUDOS, y estan vivas en el escaner 2. OCIOSTOCK tiene UNA pasada
# aplicada de la foto (la primera, 10:50:59 UTC) y su director viejo sigue escribiendo
# escaner_memoria (15:01 UTC): aqui los dos dicen «al dia», asi que la foto NO distingue
# la fuente de OcioStock; eso lo prueban `ocio_jueves_10h` y su rotura (R).
# (Hasta el 07-oct esta foto era la del sabado 03-oct, 11:36 UTC, sin pasadas de OcioStock.)
_FOTO = _escenario(
    '2026-10-07T15:02:52',
    {'DBLINE': _u('2026-10-07T10:32:10'), 'OCIOSTOCK': _u('2026-10-07T15:01:31'),
     'TCG': _u('2026-10-07T14:02:44'), 'HEO': _u('2026-10-01T05:34:35'),
     'OSMA': _u('2026-08-06T15:37:51')},
    {'HEO': [('aplicada', _u('2026-10-07T14:06:29')), ('aplicada', _u('2026-10-07T13:06:24'))],
     'OSMA': [('aplicada', _u('2026-10-07T05:15:56')), ('aplicada', _u('2026-10-06T05:16:31')),
              ('aplicada', _u('2026-10-05T05:15:56'))],
     'OCIOSTOCK': [('aplicada', _u('2026-10-07T10:50:59'))]})


def _escenario_de(caso):
    if caso == 'foto_hoy':
        return _FOTO
    # Martes 6-oct 13:00 UTC. HEO: su ultima aplicada es del lunes a las 07:00 = 30 h.
    # Su escaner_memoria (señuelo) esta FRESCO: si se mira ahi, HEO sale al dia.
    if caso == 'heo_30h_martes':
        a = '2026-10-06T13:00:00'
        m = _tres_al_dia(a)
        m['HEO'] = _fresco(a, 1)
        return _escenario(a, m, {'HEO': [('aplicada', _fresco(a, 30))],
                                 'OSMA': [('aplicada', _u('2026-10-06T05:15:46'))]})
    # Miercoles 7-oct 10:00 UTC: la pasada de OSMA de las 05:15 no ha llegado. La ultima
    # aplicada es la del martes (28,7 h). Señuelos: una 'rechazada' de hoy y un
    # escaner_memoria fresco.
    if caso == 'osma_miercoles_10':
        a = '2026-10-07T10:00:00'
        m = _tres_al_dia(a)
        m['OSMA'] = _fresco(a, 1)
        return _escenario(a, m, {'HEO': [('aplicada', _fresco(a, 1))],
                                 'OSMA': [('aplicada', _u('2026-10-06T05:15:46')),
                                          ('rechazada', _u('2026-10-07T08:00:00'))]})
    # Sabado 10-oct 10:00 UTC: OSMA no trabaja. Su ultima es del viernes: 28,7 h de
    # reloj y 18,7 h sin el sabado. VERDE.
    if caso == 'osma_sabado':
        a = '2026-10-10T10:00:00'
        return _escenario(a, _tres_al_dia(a),
                          {'HEO': [('aplicada', _fresco(a, 1))],
                           'OSMA': [('aplicada', _u('2026-10-09T05:15:46'))]})
    # Lunes 12-oct. Del viernes 05:15 al lunes 06:00 son 72,7 h de reloj y 24,7 h sin
    # sabado ni domingo: VERDE. A las 10:00 sin pasada son 76,7 y 28,7: ROJO.
    if caso in ('osma_lunes_06h', 'osma_lunes_10h'):
        a = '2026-10-12T06:00:00' if caso == 'osma_lunes_06h' else '2026-10-12T10:00:00'
        return _escenario(a, _tres_al_dia(a),
                          {'HEO': [('aplicada', _fresco(a, 1))],
                           'OSMA': [('aplicada', _u('2026-10-09T05:15:46'))]})
    # 🆕 OCIOSTOCK (07-oct-2026, OC5): una aplicada al dia, a las 09:12 Madrid (07:12 UTC).
    # Jueves 8-oct: la del miercoles 07:13 UTC es la ultima aplicada; la de hoy 07:13 salio
    # 'rechazada' (mismo fichero: «al dia», no cuenta). A las 09:00 UTC van 25,8 h: VERDE.
    # A las 10:00 UTC, 26,8 h: ROJO. Señuelo: su escaner_memoria (el director viejo), fresco.
    if caso in ('ocio_jueves_09h', 'ocio_jueves_10h'):
        a = '2026-10-08T09:00:00' if caso == 'ocio_jueves_09h' else '2026-10-08T10:00:00'
        m = _tres_al_dia(a)
        m['OCIOSTOCK'] = _fresco(a, 1)
        return _escenario(a, m, {'HEO': [('aplicada', _fresco(a, 1))],
                                 'OSMA': [('aplicada', _u('2026-10-08T05:15:46'))],
                                 'OCIOSTOCK': [('aplicada', _u('2026-10-07T07:13:00')),
                                               ('rechazada', _u('2026-10-08T07:13:00'))]})
    # Domingo 11-oct 10:00 UTC: OcioStock trabaja los siete dias. La ultima aplicada es la
    # del sabado 07:13 UTC: 26,8 h, y el domingo NO se descuenta. ROJO.
    if caso == 'ocio_domingo_10h':
        a = '2026-10-11T10:00:00'
        return _escenario(a, _tres_al_dia(a),
                          {'HEO': [('aplicada', _fresco(a, 1))],
                           'OSMA': [('aplicada', _u('2026-10-09T05:15:46'))],
                           'OCIOSTOCK': [('aplicada', _u('2026-10-10T07:13:00'))]})
    return None


# ===========================================================================
# EL HIJO: monta los dobles y corre el centinela de punta a punta
# ===========================================================================
def hijo(caso):
    import atexit

    ESC = _escenario_de(caso)
    ENVIADOS = []
    if ESC is not None:
        # El reloj del centinela: `from datetime import datetime` encontrara esta
        # subclase, cuyo now() devuelve el instante del escenario.
        import datetime as _dtm

        class _Reloj(_dtm.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromisoformat(ESC['ahora'].isoformat())

        _falso = types.ModuleType('datetime')
        _falso.__dict__.update({k: getattr(_dtm, k) for k in dir(_dtm)
                                if not k.startswith('__')})
        _falso.datetime = _Reloj
        sys.modules['datetime'] = _falso
        ADELANTE = ESC['ahora']
    else:
        ADELANTE = datetime.now(timezone.utc)
    HOY = ADELANTE.strftime('%Y-%m-%d')
    AYER = (ADELANTE - timedelta(days=1)).strftime('%Y-%m-%d')
    MUDO = {'DBLINE': 200, 'HEO': 2, 'OCIOSTOCK': 2, 'OSMA': 2, 'TCG': 2}
    HORAS = {'al_dia': {'DBLINE': 2, 'HEO': 2, 'OCIOSTOCK': 2, 'OSMA': 2, 'TCG': 2}
             }.get(caso, MUDO)
    # La marca de partida, y como se porta Storage en cada caso.
    MARCA = {'ya_avisado': {'DBLINE': HOY}, 'ayer': {'DBLINE': AYER}}.get(caso, {})
    ALMACEN = {'marca': json.dumps(MARCA).encode('utf-8')} if MARCA else {}
    ESCRITA = {}

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, tabla):
            self.tabla = tabla
            self.proveedor = None
            self.filtros = {}

        def eq(self, col, val):
            self.filtros[col] = val
            if col == 'proveedor':
                self.proveedor = val
            return self

        def __getattr__(self, nombre):
            return lambda *a, **k: self       # select, order, limit…

        def execute(self):
            if caso == 'ilegible':
                raise Exception('doble: la lectura revienta a proposito')
            if ESC is not None:
                if self.tabla == 'disp_pasada':
                    # Solo las pasadas del estado pedido: sin `.eq('estado', ...)` el
                    # centinela recibiria tambien las 'rechazada' y 'fallida'.
                    estado = self.filtros.get('estado')
                    return _Resp([{'terminada_en': t.isoformat()}
                                  for (e, t) in ESC['disp'].get(self.proveedor, [])
                                  if estado is None or e == estado])
                t = ESC['memoria'].get(self.proveedor)
                return _Resp([] if t is None else [{'fecha': t.isoformat()}])
            horas = HORAS.get(self.proveedor)
            if horas is None:
                return _Resp([])
            fecha = ADELANTE - timedelta(hours=horas)
            return _Resp([{'fecha': fecha.isoformat(), 'terminada_en': fecha.isoformat()}])

    class _Bucket:
        def download(self, ruta):
            if caso == 'marca_ilegible':
                raise Exception('doble: Storage no responde a proposito')
            if 'marca' not in ALMACEN:
                raise Exception('404 ' + ruta)      # la marca aun no existe
            return ALMACEN['marca']

        def upload(self, ruta, data, opts=None):
            if caso == 'marca_no_escribible':
                raise Exception('doble: Storage no deja escribir a proposito')
            ALMACEN['marca'] = data
            ESCRITA.update(json.loads(data.decode('utf-8')))
            return {'path': ruta}

    class _Cliente:
        def __init__(self):
            self.storage = types.SimpleNamespace(from_=lambda _b: _Bucket())

        def table(self, nombre):
            return _Query(nombre)

    def _post(url, data=None, timeout=None):
        if caso == 'telegram_falla':
            raise Exception('doble: Telegram no contesta a proposito')
        ENVIADOS.append({'url': url, 'texto': (data or {}).get('text', '')})
        return types.SimpleNamespace(status_code=200)

    sys.modules['supabase'] = types.ModuleType('supabase')
    sys.modules['supabase'].create_client = lambda url, key: _Cliente()
    sys.modules['requests'] = types.ModuleType('requests')
    sys.modules['requests'].post = _post

    os.environ['SUPABASE_URL'] = 'https://doble.local'
    os.environ['SUPABASE_SERVICE_KEY'] = 'FAKE-SERVICE'
    os.environ['TELEGRAM_TOKEN'] = 'FAKE-TG'
    os.environ['TELEGRAM_CHAT_ID'] = '123'

    @atexit.register
    def _informe():
        print('HOY=%s' % HOY)
        print('TELEGRAMS=%d' % len(ENVIADOS))
        print('TELEGRAM_TEXTO=%s' % json.dumps('\n'.join(e['texto'] for e in ENVIADOS)))
        print('MARCA_ESCRITA=%s' % json.dumps(ESCRITA, sort_keys=True))

    import runpy
    # `CENTINELA_RUTA`: las ROTURAS A MANO (ver (R)) corren una copia estropeada.
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
    print(('OK ' if ok else 'XX ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def _nodo(nombre):
    for n in ARBOL.body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return n
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return n
    print('XX %s ya no esta en %s (o dejo de ser de nivel superior)' % (nombre, RUTA))
    sys.exit(1)


NOMBRES = ('horas_en_dia', 'horas_en_domingo', 'horas_de_silencio', 'esta_mudo',
           'avisos_de_hoy', 'linea_de_aviso', 'franja_de')
_ns = {'timedelta': timedelta}
exec(compile(ast.fix_missing_locations(ast.Module(body=[_nodo(n) for n in NOMBRES],
                                                  type_ignores=[])), RUTA, 'exec'), _ns)
horas_en_dia = _ns['horas_en_dia']
horas_en_domingo = _ns['horas_en_domingo']
horas_de_silencio = _ns['horas_de_silencio']
esta_mudo = _ns['esta_mudo']
avisos_de_hoy = _ns['avisos_de_hoy']
linea_de_aviso = _ns['linea_de_aviso']
franja_de = _ns['franja_de']
HORARIOS = ast.literal_eval(_nodo('HORARIOS').value)
print('extraidas de %s: %s, HORARIOS' % (RUTA, ', '.join(NOMBRES)))
print()


def utc(txt):
    return datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# (A) Las funciones REALES, con las fechas de verdad
# ---------------------------------------------------------------------------
# El sabado-a-lunes de DBLine, tal cual: sabado 5-sep 11:00 -> lunes 7-sep 06:00.
SAB, LUN = utc('2026-09-05T11:00:00'), utc('2026-09-07T06:00:00')
eq('(A) el sabado-a-lunes son 43 h de reloj',
   round((LUN - SAB).total_seconds() / 3600.0, 2), 43.0)
eq('(A) 🔴 y 24 de ellas caen en domingo', horas_en_domingo(SAB, LUN), 24.0)
eq('(A) 🔴 asi que para quien descansa el domingo son 19 h de silencio',
   horas_de_silencio(SAB, LUN, True), 19.0)
eq('(A) un tramo sin domingo por medio no descuenta nada',
   horas_en_domingo(utc('2026-09-09T10:00:00'), utc('2026-09-10T15:00:00')), 0.0)
eq('(A) un tramo dentro del propio domingo se descuenta entero',
   horas_en_domingo(utc('2026-09-06T02:00:00'), utc('2026-09-06T08:30:00')), 6.5)
eq('(A) tres semanas descuentan tres domingos',
   horas_en_domingo(utc('2026-08-17T00:00:00'), utc('2026-09-07T00:00:00')), 72.0)
eq('(A) el reloj al reves no da horas negativas',
   horas_de_silencio(LUN, SAB, True), 0.0)
eq('(A) sin dato, mudo: no saber no es estar bien', esta_mudo(None, 26), True)

# EL APAGON DE VERDAD. DBLine escribio por ultima vez el miercoles 9-sep a las
# 10:31 UTC. Sin domingo por medio: horas brutas = horas de silencio.
APAGON = utc('2026-09-09T10:31:00')
_x_dbline = HORARIOS['DBLINE']['umbral_h']
eq('(A) 🔴 [apagon] el 10-sep a las 12:00 UTC aun no ha vencido el plazo',
   esta_mudo(horas_de_silencio(APAGON, utc('2026-09-10T12:00:00'), True), _x_dbline), False)
eq('(A) 🔴 [apagon] y a las 14:00 UTC del 10-sep SI: 27,5 h > 26',
   (round(horas_de_silencio(APAGON, utc('2026-09-10T14:00:00'), True), 2),
    esta_mudo(horas_de_silencio(APAGON, utc('2026-09-10T14:00:00'), True), _x_dbline)),
   (27.48, True))

# OSMA (escaner 2, 03-oct-2026): de lunes a viernes, una pasada a las 05:15 UTC. El
# viernes-a-lunes: 72 h de reloj, 48 de fin de semana, 24 de las suyas.
VIE, LUN2 = utc('2026-10-09T05:15:00'), utc('2026-10-12T05:15:00')
eq('(A) 🔴 [OSMA] el viernes-a-lunes son 72 h de reloj y 24 h SIN sabado ni domingo',
   (round((LUN2 - VIE).total_seconds() / 3600.0, 2),
    horas_de_silencio(VIE, LUN2, True, True)), (72.0, 24.0))
eq('(A) [OSMA] el sabado se descuenta aparte del domingo',
   (horas_en_dia(VIE, LUN2, 5), horas_en_dia(VIE, LUN2, 6), horas_en_dia(VIE, LUN2, 2)),
   (24.0, 24.0, 0.0))
eq('(A) 🔴 sin `descansa_sabado` el mismo hueco descuenta SOLO el domingo (48 h)',
   horas_de_silencio(VIE, LUN2, True), 48.0)
eq('(A) 🔴 [OSMA] un dia habil al siguiente son 24 h, y a las 06:00 no ha vencido nada',
   (horas_de_silencio(utc('2026-10-06T05:15:00'), utc('2026-10-07T06:00:00'), True, True),
    esta_mudo(horas_de_silencio(utc('2026-10-06T05:15:00'), utc('2026-10-07T06:00:00'),
                                True, True), HORARIOS['OSMA']['umbral_h'])),
   (24.75, False))
eq('(A) 🔴 [OSMA] y a las 10:00 sin pasada ese dia, 28,75 h: MUDO',
   esta_mudo(horas_de_silencio(utc('2026-10-06T05:15:00'), utc('2026-10-07T10:00:00'),
                               True, True), HORARIOS['OSMA']['umbral_h']), True)
eq('(A) 🔴 [OSMA] un sabado entero sin pasada NO es mudo (viernes 05:15 a sabado 23:00)',
   esta_mudo(horas_de_silencio(utc('2026-10-09T05:15:00'), utc('2026-10-10T23:00:00'),
                               True, True), HORARIOS['OSMA']['umbral_h']), False)
# HEO (escaner 2): trabaja TODOS los dias, no se descuenta ninguno.
eq('(A) 🔴 [HEO] 30 h de silencio un martes: MUDO (X = 26 h, nada descontado)',
   esta_mudo(horas_de_silencio(utc('2026-10-05T07:00:00'), utc('2026-10-06T13:00:00'),
                               False, False), HORARIOS['HEO']['umbral_h']), True)
eq('(A) [HEO] la noche del sabado al domingo medida por horario (09:06 a 08:06 Madrid, 23 h)'
   ' NO es mudo',
   esta_mudo(horas_de_silencio(utc('2026-10-03T07:06:00'), utc('2026-10-04T06:06:00'),
                               False, False), HORARIOS['HEO']['umbral_h']), False)
eq('(A) [HEO] la noche de entre semana medida (19:06 a 06:06 UTC, 11 h) NO es mudo',
   esta_mudo(horas_de_silencio(utc('2026-10-01T19:06:00'), utc('2026-10-02T06:06:00'),
                               False, False), HORARIOS['HEO']['umbral_h']), False)
eq('(A) 🔴 [HEO] el domingo NO se descuenta (HEO lo trabaja): el hueco entero cuenta',
   horas_de_silencio(utc('2026-10-03T07:06:00'), utc('2026-10-04T06:06:00'),
                     HORARIOS['HEO']['descansa_domingo'], HORARIOS['HEO']['descansa_sabado']),
   23.0)

# ---------------------------------------------------------------------------
# (D) Las dos direcciones del descuento: el MISMO hueco, los DOS calendarios
# ---------------------------------------------------------------------------
print()
eq('(D) 🔴 el sabado-a-lunes NO es mudo para quien descansa el domingo (19 h)',
   esta_mudo(horas_de_silencio(SAB, LUN, True), _x_dbline), False)
eq('(D) 🔴 y el MISMO hueco SI es mudo para quien no descansa (43 h)',
   esta_mudo(horas_de_silencio(SAB, LUN, False), HORARIOS['TCG']['umbral_h']), True)

# ---------------------------------------------------------------------------
# (E) El reparto del freno, como funcion pura
# ---------------------------------------------------------------------------
print()
HOY, AYER = '2026-09-10', '2026-09-09'
eq('(E) el que ya sono hoy no vuelve a sonar',
   avisos_de_hoy({'DBLINE': HOY}, HOY, ['DBLINE']), ([], ['DBLINE']))
eq('(E) 🔴 pero el de AYER si: el freno es por dia, no para siempre',
   avisos_de_hoy({'DBLINE': AYER}, HOY, ['DBLINE']), (['DBLINE'], []))
eq('(E) 🔴 es por PROVEEDOR: que hoy sonara DBLine no calla a HEO',
   avisos_de_hoy({'DBLINE': HOY}, HOY, ['DBLINE', 'HEO']), (['HEO'], ['DBLINE']))
eq('(E) 🔴 FALLA EN ABIERTO: con la marca vacia salen TODOS a avisar',
   avisos_de_hoy({}, HOY, ['DBLINE', 'HEO', 'TCG']), (['DBLINE', 'HEO', 'TCG'], []))
eq('(E) y sin mudos no hay nada que repartir', avisos_de_hoy({'DBLINE': HOY}, HOY, []),
   ([], []))

# ---------------------------------------------------------------------------
# (F) La linea del aviso: empieza por CUANTO lleva callado
# ---------------------------------------------------------------------------
print()


def fila(brutas, horas, ultima=APAGON, proveedor='DBLINE'):
    return {'proveedor': proveedor, 'ultima': ultima, 'brutas': brutas, 'horas': horas,
            'umbral': 26, 'franja': franja_de(HORARIOS['DBLINE']), 'motivo': None}


_sin_domingo = linea_de_aviso(fila(27.48, 27.48))
eq('(F) 🔴 empieza por las horas y lleva la fecha de la ultima escritura',
   _sin_domingo,
   '• <b>DBLINE</b> — lleva 27 h sin escribir (última: 2026-09-09 10:31 UTC). '
   'Su plazo son 26 h. Horario: 06-11 UTC, L a S.')
_con_domingo = linea_de_aviso(fila(51.0, 27.0))
eq('(F) 🔴 con un domingo por medio se dicen los DOS numeros',
   _con_domingo,
   '• <b>DBLINE</b> — lleva 51 h sin escribir (última: 2026-09-09 10:31 UTC). '
   '27 h sin contar los domingos, que es lo que se compara con su plazo de 26 h. '
   'Horario: 06-11 UTC, L a S.')
eq('(F) …y sin domingo por medio NO se nombra el descuento (seria ruido)',
   'sin contar los domingos' in _sin_domingo, False)
_sin_dato = dict(fila(0, 0), ultima=None, motivo='ni una fila en escaner_memoria')
eq('(F) 🔴 [OSMA] con sabado y domingo por medio se dicen los DOS numeros y que se descuenta',
   linea_de_aviso(dict(fila(76.7, 28.7, proveedor='OSMA'), umbral=26,
                       franja=franja_de(HORARIOS['OSMA']),
                       descontado='los sábados y domingos')),
   '• <b>OSMA</b> — lleva 77 h sin escribir (última: 2026-09-09 10:31 UTC). '
   '29 h sin contar los sábados y domingos, que es lo que se compara con su plazo de 26 h. '
   'Horario: 05 UTC, L a V (una pasada, 07:15 Madrid).')
eq('(F) el que no tiene ni una fila lo dice, y dice su plazo',
   linea_de_aviso(_sin_dato),
   '• <b>DBLINE</b> — sin dato (ni una fila en escaner_memoria). Su plazo son 26 h.')

# ---------------------------------------------------------------------------
# (B) La tabla cubre los directores que existen, y con margen
# ---------------------------------------------------------------------------
print()
_dir = os.path.join('.github', 'workflows')
_directores = sorted(f[len('director-'):-len('.yml')].upper()
                     for f in os.listdir(_dir)
                     if f.startswith('director-') and f.endswith('.yml'))
print('    directores en .github/workflows: %s' % ', '.join(_directores))
eq('(B) 🔴 hay directores que mirar, no cero', len(_directores) > 0, True)
# 🆕 03-oct-2026: HEO y OSMA salen de `escaner_memoria` y se vigilan en `disp_pasada`.
#    El director viejo de HEO sigue en .github/workflows (apagado en cron-job.org) y
#    OSMA nunca tuvo director viejo (nacio en el escaner 2): por eso la regla ya no es
#    "la tabla == los directores", sino "todo director tiene su linea, y la unica
#    linea sin director es una de `disp_pasada`".
_de_disp = sorted(p for p in HORARIOS if HORARIOS[p]['fuente'] == 'disp_pasada')
eq('(B) 🔴 todo director que existe tiene su linea en la tabla (si no, saldria verde sin mirarlo)',
   [p for p in _directores if p not in HORARIOS], [])
eq('(B) 🔴 y toda linea sin director es del escaner 2 (`disp_pasada`), no un despiste',
   sorted(p for p in HORARIOS if p not in _directores and p not in _de_disp), [])
eq('(B) 🔴 las fuentes son dos y se escriben bien (una fuente mal escrita leeria la otra)',
   sorted(set(c['fuente'] for c in HORARIOS.values())), ['disp_pasada', 'escaner_memoria'])
# 🆕 07-oct-2026 (OC5): OCIOSTOCK pasa a `disp_pasada`. Su director viejo SIGUE en
#    .github/workflows (director-ociostock.yml) y tiene su linea: la regla de arriba se
#    cumple igual (todo director tiene linea; las lineas sin director son de disp_pasada).
eq('(B) 🔴 HEO, OCIOSTOCK y OSMA se vigilan en `disp_pasada` (lo que leen Reponer y el Trackeador)',
   _de_disp, ['HEO', 'OCIOSTOCK', 'OSMA'])
eq('(B) 🔴 DBLINE y TCG siguen EXACTAMENTE como estaban: `escaner_memoria`',
   sorted(p for p in HORARIOS if HORARIOS[p]['fuente'] == 'escaner_memoria'),
   ['DBLINE', 'TCG'])
eq('(B) 🔴 …con sus plazos de siempre (26 y 22 h) y el domingo descontado como antes',
   [(p, HORARIOS[p]['umbral_h'], HORARIOS[p]['descansa_domingo'], HORARIOS[p]['descansa_sabado'])
    for p in ('DBLINE', 'TCG')],
   [('DBLINE', 26, True, False), ('TCG', 22, False, False)])
eq('(B) 🔴 OCIOSTOCK: una aplicada al dia los siete dias -> 26 h y ningun dia descontado',
   (HORARIOS['OCIOSTOCK']['umbral_h'], HORARIOS['OCIOSTOCK']['descansa_sabado'],
    HORARIOS['OCIOSTOCK']['descansa_domingo']), (26, False, False))
eq('(B) 🔴 …y su director viejo sigue existiendo y con linea (mientras no se apague)',
   'OCIOSTOCK' in _directores and 'OCIOSTOCK' in HORARIOS, True)
eq('(B) 🔴 OSMA: de lunes a viernes, el sabado Y el domingo no cuentan',
   (HORARIOS['OSMA']['descansa_sabado'], HORARIOS['OSMA']['descansa_domingo']), (True, True))
eq('(B) 🔴 HEO trabaja los siete dias: no se le descuenta ninguno',
   (HORARIOS['HEO']['descansa_sabado'], HORARIOS['HEO']['descansa_domingo']), (False, False))
for _p in sorted(HORARIOS):
    _cfg = HORARIOS[_p]
    eq('(B) [%s] 🔴 la X (%d h) esta por encima del hueco mayor medido (%.2f h)'
       % (_p, _cfg['umbral_h'], _cfg['medido_h']), _cfg['umbral_h'] > _cfg['medido_h'], True)
    eq('(B) [%s] …y el margen no pasa de 6 h (una X floja no avisa a tiempo)' % _p,
       _cfg['umbral_h'] - _cfg['medido_h'] <= 6, True)

# ---------------------------------------------------------------------------
# (G) EL RELOJ: que las cuatro pasadas del cron cubran de verdad la ventana en la
#     que cada plazo puede vencerse, con 4 h de demora como mucho.
# ---------------------------------------------------------------------------
# 🔴 ESTO ES LO QUE IMPIDE QUE EL HORARIO SEA UNA AFIRMACION. El cron se leyo
#    del .yml de verdad y la ventana sale de las cifras de HORARIOS: si manana
#    alguien mueve una franja, una X o una hora del cron, esto se pone rojo solo.
#    Sin esto, «no hay pasadas de noche porque ningun plazo vence de noche» seria
#    una frase bonita en un comentario.
print()
_doc = yaml.safe_load(io.open(os.path.join('.github', 'workflows', 'centinela-escaner.yml'),
                              encoding='utf-8'))
# 🔑 En un .yml, `on:` se lee como el BOOLEANO True (el problema de Noruega).
_on = _doc.get('on', _doc.get(True)) or {}
_crons = [x['cron'] for x in (_on.get('schedule') or [])]
eq('(G) hay UN cron, no cero ni tres', len(_crons), 1)
_horas_cron = sorted(int(h) for h in _crons[0].split()[1].split(','))
print('    el cron del workflow mira a las: %s UTC'
      % ', '.join('%02d:00' % h for h in _horas_cron))
eq('(G) 🔴 son CUATRO pasadas al dia', len(_horas_cron), 4)
eq('(G) 🔴 la primera, a primera hora española (06:00 UTC = 07:00/08:00 en casa)',
   _horas_cron[0], 6)
eq('(G) 🔴 y la ultima no pasa de las 18:00 UTC: ningun aviso a deshora',
   _horas_cron[-1] <= 18, True)
eq('(G) el cron corre TODOS los dias (un mudo del domingo se caza el lunes)',
   _crons[0].split()[2:], ['*', '*', '*'])


def ventana_de_vencimiento(cfg):
    """Horas UTC (inicio, fin) en las que el plazo de ese proveedor puede vencerse.

    Escribe entre `primera_h` y `ultima_h`; si deja de escribir, su plazo vence
    `umbral_h` despues de la ultima que llego a hacer. Se devuelve en horas del
    dia, que es lo que hay que cruzar con el cron."""
    return ((cfg['primera_h'] + cfg['umbral_h']) % 24,
            (cfg['ultima_h'] + cfg['umbral_h']) % 24)


def ventana_tras_domingo(cfg):
    """La misma ventana cuando hay un domingo por medio: el reloj descontado esta
    parado el domingo entero, asi que lo que faltaba se consume el lunes desde las
    00:00. Escribio el sabado a la hora h -> le faltan `umbral - (24 - h)` horas."""
    return (cfg['umbral_h'] - 24 + cfg['primera_h'],
            cfg['umbral_h'] - 24 + cfg['ultima_h'])


def demora_maxima(ini, fin, horas_cron):
    """Cuanto puede tardar el aviso desde que el plazo vence, en horas, si el
    vencimiento cae en cualquier minuto de [ini, fin]. Se mira minuto a minuto:
    con horas redondas se podria colar un caso de borde justo despues de una
    pasada, que es exactamente el que importa."""
    peor = 0.0
    minuto = ini * 60
    while minuto <= fin * 60:
        espera = min(((h * 60 - minuto) % (24 * 60)) or 24 * 60 for h in horas_cron)
        # Un vencimiento JUSTO en la hora del cron se avisa en esa pasada: 0 h.
        if any(h * 60 == minuto for h in horas_cron):
            espera = 0
        peor = max(peor, espera / 60.0)
        minuto += 1
    return peor


for _p in sorted(HORARIOS):
    _cfg = HORARIOS[_p]
    _ini, _fin = ventana_de_vencimiento(_cfg)
    _dem = demora_maxima(_ini, _fin, _horas_cron)
    print('    %-10s escribe %02d-%02d UTC, X=%d h -> vence entre %02d:00 y %02d:00, demora %.2f h'
          % (_p, _cfg['primera_h'], _cfg['ultima_h'], _cfg['umbral_h'], _ini, _fin, _dem))
    if _cfg.get('ventana_ancha'):
        # HEO (escaner 2): escribe 13 h seguidas, su ventana (13 h) no cabe en las 11 h
        # de 04:00-15:00. Se le exige OTRA cosa, no se le quita la comprobacion:
        #  - que de verdad no quepa (si cupiera, la marca seria un pase gratis),
        #  - que lo diurno (hasta la ultima pasada del cron) se avise en 4 h,
        #  - y que lo que cae en el hueco de noche espere como mucho a la pasada de
        #    las 06:00 (el hueco 18:00-06:00 son 12 h).
        _dia = demora_maxima(_ini, min(_fin, _horas_cron[-1]), _horas_cron)
        eq('(G) [%s] 🔴 la marca `ventana_ancha` no es un pase gratis: con las reglas '
           'normales NO cabria' % _p, (4 <= _ini <= 15 and 4 <= _fin <= 15), False)
        eq('(G) [%s] 🔴 la parte diurna de la ventana (hasta las %02d:00) se avisa en 4 h'
           % (_p, _horas_cron[-1]), _dia <= 4.0, True)
        eq('(G) [%s] 🔴 y el peor caso, el del hueco de noche, no pasa de 12 h' % _p,
           _dem <= 12.0, True)
    else:
        eq('(G) [%s] 🔴 el aviso no se retrasa mas de 4 h' % _p, _dem <= 4.0, True)
        eq('(G) [%s] 🔴 su plazo NUNCA vence de noche (04:00-15:00 UTC)' % _p,
           (4 <= _ini <= 15, 4 <= _fin <= 15), (True, True))
    if _cfg['descansa_domingo']:
        _i2, _f2 = ventana_tras_domingo(_cfg)
        _d2 = demora_maxima(_i2, _f2, _horas_cron)
        eq('(G) [%s] …y con un domingo por medio tampoco (vence el lunes entre %02d:00 y %02d:00)'
           % (_p, _i2, _f2), (_d2 <= 4.0, 4 <= _i2 and _f2 <= 15), (True, True))

# La otra direccion: un cron que se dejara la tarde SI tendria que salir mal.
eq('(G) 🔴 …y un cron que se dejara la tarde daria una demora enorme',
   demora_maxima(*ventana_de_vencimiento(HORARIOS['HEO']), horas_cron=[6, 8]) > 4.0, True)


# ---------------------------------------------------------------------------
# (C) De punta a punta, ocho veces, cada una en su proceso
# ---------------------------------------------------------------------------
print()


def correr(caso, ruta=None):
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--hijo', caso]
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if ruta:
        env['CENTINELA_RUTA'] = ruta
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=env)
    out = (p.stdout or '') + (p.stderr or '')

    def campo(clave, patron=r'(.*)'):
        m = re.search(r'^%s=%s$' % (clave, patron), out, re.M)
        return m.group(1) if m else None

    _n = campo('TELEGRAMS', r'(\d+)')
    def veredicto(proveedor):
        m = re.search(r'^  %s +(?:ultima .*-> (MUDO|al dia)|SIN DATO .*-> (MUDO))' % proveedor,
                      out, re.M)
        return None if not m else (m.group(1) or m.group(2))

    return {'codigo': p.returncode, 'salida': out,
            'veredicto': {p_: veredicto(p_) for p_ in HORARIOS},
            'hoy': campo('HOY'),
            'telegrams': int(_n) if _n else -1,
            'texto': json.loads(campo('TELEGRAM_TEXTO') or '""'),
            'marca': json.loads(campo('MARCA_ESCRITA') or '{}'),
            'lineas': len(re.findall(r'^  \w+ *(?:ultima|SIN DATO)', out, re.M))}


_ok = correr('al_dia')
eq('(C) [al_dia] 🔴 el run sale VERDE (exit 0)', _ok['codigo'], 0)
eq('(C) [al_dia] 🔴 y NO se manda ningun Telegram', _ok['telegrams'], 0)
eq('(C) [al_dia] las CINCO lineas del informe estan en el log', _ok['lineas'], len(HORARIOS))
eq('(C) [al_dia] con su linea de conforme',
   'CENTINELA OK: los %d directores han escrito dentro de su plazo.' % len(HORARIOS) in _ok['salida'], True)
eq('(C) [al_dia] y la marca no se toca', _ok['marca'], {})

_mudo = correr('mudo')
eq('(C) [mudo] 🔴 el run sale en ROJO (exit 1)', _mudo['codigo'], 1)
eq('(C) [mudo] 🔴 con la etiqueta grepable, y nombrando a DBLINE',
   'CENTINELA_MUDO: DBLINE' in _mudo['salida'], True)
eq('(C) [mudo] 🔴 se manda UN Telegram, ni cero ni dos', _mudo['telegrams'], 1)
eq('(C) [mudo] 🔴 y el aviso dice DESDE CUANDO, no solo que esta mudo',
   ('DBLINE' in _mudo['texto'] and 'sin escribir' in _mudo['texto']
    and 'última:' in _mudo['texto']), True)
eq('(C) [mudo] …y NO nombra a los que estan al dia',
   ('HEO' in _mudo['texto'], 'TCG' in _mudo['texto']), (False, False))
eq('(C) [mudo] las CINCO lineas siguen estando: tambien las de los que hablan',
   _mudo['lineas'], len(HORARIOS))
eq('(C) [mudo] 🔴 la marca queda escrita con la fecha de hoy',
   _mudo['marca'], {'DBLINE': _mudo['hoy']})

_ileg = correr('ilegible')
eq('(C) [ilegible] 🔴 el run sale en ROJO (exit 1)', _ileg['codigo'], 1)
eq('(C) [ilegible] 🔴 y el log dice que no se pudo leer',
   'no se pudo leer' in _ileg['salida'], True)
eq('(C) [ilegible] los cinco salen como SIN DATO, no como al dia',
   _ileg['salida'].count('SIN DATO'), len(HORARIOS))
eq('(C) [ilegible] y se avisa por Telegram: un centinela ciego no puede callarse',
   _ileg['telegrams'], 1)

# --- El freno -------------------------------------------------------------
print()
_ya = correr('ya_avisado')
eq('(C) [ya_avisado] 🔴 CERO Telegram: hoy ya sono', _ya['telegrams'], 0)
eq('(C) [ya_avisado] 🔴 pero el run sigue ROJO: lo que se calla es el movil',
   _ya['codigo'], 1)
eq('(C) [ya_avisado] y el log lo dice, con nombre',
   'ya avisados hoy (no se repite el Telegram): DBLINE' in _ya['salida'], True)
eq('(C) [ya_avisado] las cinco lineas siguen en el log', _ya['lineas'], len(HORARIOS))

_ayer = correr('ayer')
eq('(C) [ayer] 🔴 con la marca de AYER vuelve a avisar', _ayer['telegrams'], 1)
eq('(C) [ayer] y la marca se pone a hoy', _ayer['marca'], {'DBLINE': _ayer['hoy']})

_mi = correr('marca_ilegible')
eq('(C) [marca_ilegible] 🔴 FALLA EN ABIERTO: se avisa igual', _mi['telegrams'], 1)
eq('(C) [marca_ilegible] 🔴 y el log dice por que avisa de todas formas',
   'Se avisa IGUAL' in _mi['salida'], True)
eq('(C) [marca_ilegible] el run, rojo', _mi['codigo'], 1)

_mne = correr('marca_no_escribible')
eq('(C) [marca_no_escribible] 🔴 el aviso sale igual', _mne['telegrams'], 1)
eq('(C) [marca_no_escribible] 🔴 y se avisa de que hoy puede repetirse',
   'no se pudo guardar la marca' in _mne['salida'], True)
eq('(C) [marca_no_escribible] el run, rojo', _mne['codigo'], 1)

_tgf = correr('telegram_falla')
eq('(C) [telegram_falla] 🔴 la marca queda INTACTA: si no sono, no se apunta',
   _tgf['marca'], {})
eq('(C) [telegram_falla] 🔴 y el log lo dice', 'la marca queda intacta' in _tgf['salida'], True)
eq('(C) [telegram_falla] el run, rojo', _tgf['codigo'], 1)

# --- HEO y OSMA en el escaner 2: de punta a punta, con el reloj FIJO -------
print()
_AL_DIA = {p: 'al dia' for p in HORARIOS}

_foto = correr('foto_hoy')
eq('(C) [foto_hoy] 🔴 con la foto de PRODUCCION de hoy, nada en rojo (exit 0)', _foto['codigo'], 0)
eq('(C) [foto_hoy] 🔴 los cinco al dia, HEO y OSMA incluidos', _foto['veredicto'], _AL_DIA)
eq('(C) [foto_hoy] cero Telegram', _foto['telegrams'], 0)
eq('(C) [foto_hoy] y el log dice DE DONDE sale la fecha de HEO, OCIOSTOCK y OSMA',
   [bool(re.search(r'^  %s .*fuente disp_pasada$' % p, _foto['salida'], re.M))
    for p in ('HEO', 'OCIOSTOCK', 'OSMA')], [True, True, True])
eq('(C) [foto_hoy] …y la de los otros dos sigue siendo escaner_memoria',
   [bool(re.search(r'^  %s .*fuente escaner_memoria$' % p, _foto['salida'], re.M))
    for p in ('DBLINE', 'TCG')], [True, True])
eq('(C) [foto_hoy] 🔴 OCIOSTOCK lee SU pasada aplicada (10:50 UTC), no la memoria del viejo (15:01)',
   bool(re.search(r'^  OCIOSTOCK +ultima 2026-10-07 10:50 UTC .*fuente disp_pasada$',
                  _foto['salida'], re.M)), True)

_oc9 = correr('ocio_jueves_09h')
eq('(C) [ocio_jueves_09h] 🔴 OcioStock con 25,8 h y su pasada de hoy «al dia» (rechazada): VERDE',
   (_oc9['codigo'], _oc9['telegrams'], _oc9['veredicto']), (0, 0, _AL_DIA))
_oc10 = correr('ocio_jueves_10h')
eq('(C) [ocio_jueves_10h] 🔴 …a las 10:00 UTC (26,8 h): ROJO y SOLO OCIOSTOCK',
   (_oc10['codigo'], _oc10['veredicto']), (1, dict(_AL_DIA, OCIOSTOCK='MUDO')))
eq('(C) [ocio_jueves_10h] 🔴 un Telegram que dice cuanto lleva y que es del escaner 2',
   (_oc10['telegrams'], 'OCIOSTOCK' in _oc10['texto'], 'lleva 27 h sin escribir' in _oc10['texto'],
    'disp_pasada' in _oc10['texto']), (1, True, True, True))
eq('(C) [ocio_jueves_10h] 🔴 la \'rechazada\' de hoy NO cuenta, y su escaner_memoria FRESCO no lo salva',
   _oc10['marca'], {'OCIOSTOCK': _oc10['hoy']})
_ocd = correr('ocio_domingo_10h')
eq('(C) [ocio_domingo_10h] 🔴 OcioStock trabaja el domingo: 26,8 h sin pasada un domingo es ROJO',
   (_ocd['codigo'], _ocd['veredicto']), (1, dict(_AL_DIA, OCIOSTOCK='MUDO')))

_heo30 = correr('heo_30h_martes')
eq('(C) [heo_30h_martes] 🔴 HEO con 30 h sin pasada aplicada un martes: ROJO y SOLO HEO',
   (_heo30['codigo'], _heo30['veredicto']), (1, dict(_AL_DIA, HEO='MUDO')))
eq('(C) [heo_30h_martes] 🔴 un Telegram, que dice cuanto lleva y de donde sale la fecha',
   (_heo30['telegrams'], 'HEO' in _heo30['texto'], 'lleva 30 h sin escribir' in _heo30['texto'],
    'disp_pasada' in _heo30['texto']), (1, True, True, True))
eq('(C) [heo_30h_martes] 🔴 y su escaner_memoria FRESCO (señuelo) no lo salva',
   _heo30['marca'], {'HEO': _heo30['hoy']})

_osma_mi = correr('osma_miercoles_10')
eq('(C) [osma_miercoles_10] 🔴 OSMA sin pasada un miercoles a las 10:00: ROJO y SOLO OSMA',
   (_osma_mi['codigo'], _osma_mi['veredicto']), (1, dict(_AL_DIA, OSMA='MUDO')))
eq('(C) [osma_miercoles_10] 🔴 un Telegram a OSMA, y no nombra a HEO',
   (_osma_mi['telegrams'], 'OSMA' in _osma_mi['texto'], 'HEO' in _osma_mi['texto']),
   (1, True, False))
eq('(C) [osma_miercoles_10] 🔴 una pasada \'rechazada\' de hoy NO cuenta como pasada',
   _osma_mi['veredicto']['OSMA'], 'MUDO')

_osma_sa = correr('osma_sabado')
eq('(C) [osma_sabado] 🔴 un sabado sin pasada de OSMA: VERDE (exit 0), cero Telegram',
   (_osma_sa['codigo'], _osma_sa['telegrams'], _osma_sa['veredicto']), (0, 0, _AL_DIA))

_osma_l6 = correr('osma_lunes_06h')
eq('(C) [osma_lunes_06h] 🔴 el lunes a las 06:00, antes de su pasada: VERDE (el finde no cuenta)',
   (_osma_l6['codigo'], _osma_l6['veredicto']), (0, _AL_DIA))
_osma_l10 = correr('osma_lunes_10h')
eq('(C) [osma_lunes_10h] 🔴 …y el lunes a las 10:00 sin pasada: ROJO, con los DOS numeros',
   (_osma_l10['codigo'], _osma_l10['veredicto']['OSMA'], _osma_l10['telegrams'],
    'lleva 77 h sin escribir' in _osma_l10['texto'],
    'sin contar los sábados y domingos' in _osma_l10['texto']), (1, 'MUDO', 1, True, True))

# --- (R) ROTURAS A MANO: estropear el centinela y ver que el banco se pone rojo
# 🔴 Un banco que no sabe ponerse rojo no prueba nada. Se estropea una COPIA del
#    centinela por ESTRUCTURA (con `ast`, no con un replace de texto: el ancla
#    `'fuente': 'disp_pasada'` sale dos veces) y se corre la foto de hoy.
print()
import tempfile


def estropeado(cambia):
    """Copia de centinela_escaner.py con HORARIOS cambiado por `cambia(horarios)`."""
    arbol = ast.parse(FUENTE, RUTA)
    for n in arbol.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HORARIOS'
                                             for t in n.targets):
            tabla = ast.literal_eval(n.value)
            cambia(tabla)
            n.value = ast.parse(repr(tabla), mode='eval').body
    ruta = os.path.join(tempfile.mkdtemp(), 'centinela_estropeado.py')
    with io.open(ruta, 'w', encoding='utf-8') as f:
        f.write(ast.unparse(ast.fix_missing_locations(arbol)))
    return ruta


def _heo_a_memoria(tabla):
    tabla['HEO']['fuente'] = 'escaner_memoria'


def _osma_a_memoria(tabla):
    tabla['OSMA']['fuente'] = 'escaner_memoria'


def _osma_sin_sabado(tabla):
    tabla['OSMA']['descansa_sabado'] = False


_r1 = correr('foto_hoy', ruta=estropeado(_heo_a_memoria))
eq('(R) 🔴 HEO mirado otra vez en escaner_memoria: la foto de hoy se pone ROJA, y por HEO',
   (_r1['codigo'], _r1['veredicto']['HEO'], _r1['telegrams']), (1, 'MUDO', 1))
_r2 = correr('foto_hoy', ruta=estropeado(_osma_a_memoria))
eq('(R) 🔴 OSMA mirado en escaner_memoria (06-ago): la foto de hoy se pone ROJA, y por OSMA',
   (_r2['codigo'], _r2['veredicto']['OSMA']), (1, 'MUDO'))
_r3 = correr('osma_sabado', ruta=estropeado(_osma_sin_sabado))
eq('(R) 🔴 OSMA sin el descuento del sabado: el sabado de OSMA daria aviso falso (ROJO)',
   (_r3['codigo'], _r3['veredicto']['OSMA']), (1, 'MUDO'))
def _ocio_a_memoria(tabla):
    tabla['OCIOSTOCK']['fuente'] = 'escaner_memoria'


def _ocio_descansa_domingo(tabla):
    tabla['OCIOSTOCK']['descansa_domingo'] = True


# 🆕 07-oct-2026 (OC5) · Las roturas de OcioStock, sobre SUS escenarios: en la foto de hoy
#    las dos fuentes dicen «al dia» y una rotura ahi no se veria (ver el comentario de _FOTO).
_r5 = correr('ocio_jueves_10h', ruta=estropeado(_ocio_a_memoria))
eq('(R) 🔴 OCIOSTOCK mirado otra vez en escaner_memoria: el mudo del jueves sale VERDE (el banco lo caza)',
   (_r5['codigo'], _r5['veredicto']['OCIOSTOCK']), (0, 'al dia'))
_r6 = correr('ocio_domingo_10h', ruta=estropeado(_ocio_descansa_domingo))
eq('(R) 🔴 OCIOSTOCK descontando el domingo: el mudo del domingo sale VERDE (el banco lo caza)',
   (_r6['codigo'], _r6['veredicto']['OCIOSTOCK']), (0, 'al dia'))
_r4 = correr('foto_hoy', ruta=estropeado(lambda t: None))
eq('(R) …y la copia SIN estropear (control) sale verde: las roturas no son un banco roto',
   (_r4['codigo'], _r4['veredicto']), (0, _AL_DIA))

# ---------------------------------------------------------------------------
print()
if fallos:
    print('❌ %d FALLOS: %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('✅ TODO OK (el mudo se detecta, el domingo no da falsos avisos, y el freno falla en abierto)')
