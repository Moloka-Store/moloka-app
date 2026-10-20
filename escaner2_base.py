# -*- coding: utf-8 -*-
"""ESCANER 2 · EL CLIENTE DE LA BASE, CON REINTENTO ANTE UN CORTE BREVE DE POSTGREST (encargo D, 20-oct-2026).

POR QUE. Run 39419090368 (escaner2-heo-disponibilidad, 20-oct 12:01 UTC): bajo y cruzo el catalogo entero de HEO
y, al subir a `disp_lectura`, la base contesto 503 PGRST002 a las 12:07:30, once segundos despues de aplicarse una
migracion (12:07:19). PostgREST estaba recargando su cache del esquema: no ejecuto nada y al rato volvia. supabase-py
no reintenta, asi que fallaron la subida, el `_cerrar_fallida` y el `--rescate`, y la pasada se quedo 'leyendo' con
17.000 filas hasta que la cerro como huerfana la pasada de las 13:01.

LO UNICO QUE CAMBIA. Los 26 programas del escaner 2 que hablan con la base crean su cliente con `cliente(url, llave)`
en vez de `create_client(url, llave)`: es el MISMO cliente de supabase (mismas llamadas, mismas cabeceras, mismo
resultado), con una pieza metida en la capa HTTP de PostgREST (solo `sb.table(...)` y `sb.rpc(...)`: Storage,
Auth y Functions no se tocan) que decide si una respuesta fallida se repite. La regla, la misma que la del cartero
(encargo C):

  🔑 SE REINTENTA, haga lo que haga la llamada (leer o escribir):
       una respuesta HTTP 503 cuyo codigo es PGRST002 (no pudo leer la cache del esquema) o PGRST001 (no pudo
       conectar con la base). En los dos PostgREST NO ha ejecutado nada, asi que repetir no duplica.
  🔑 SE REINTENTA SOLO SI ES UNA LECTURA (GET o HEAD):
       un fallo de red SIN respuesta (no conecta, se corta, tope de tiempo).
  🔴 NO SE REINTENTA NUNCA:
       una escritura (POST, PATCH, PUT, DELETE; tambien las `rpc`, que van por POST) con fallo de red: puede
       haberse ejecutado y no sabemos si si o si no; cualquier otro 5xx (500, 502, 504, o un 503 con otro codigo);
       ningun 4xx. Todo eso sale EXACTAMENTE como hoy.

  ⏱ ESPERAS CRECIENTES (5, 10, 20 y luego 30 s, las del cartero) CON UN TOPE POR RUN de TOPE_SEGUNDOS (240 s = 4 min),
     sumado entre TODAS las llamadas del programa (el run entero, no cada llamada); la espera que cruza el tope se
     recorta a lo que queda. 🔴 A DIFERENCIA DEL CARTERO, el tope cuenta tambien lo que TARDARON los intentos que
     fallaron, no solo las esperas: una lectura que muere por tope de tiempo de httpx (120 s en PostgREST) se comeria
     si no varios minutos fuera de la cuenta, y el paso del workflow tiene su propio tope. Agotado el tope, la respuesta o el error del ultimo intento sale tal cual, como hoy:
     la pasada se cierra fallida y el rescate (otro proceso, con su propio tope) actua.
  📣 Cada reintento deja una linea `REINTENTO_BASE:` en el log (metodo, tabla o funcion, motivo, espera y lo
     gastado del tope). Sin la consulta ni el cuerpo: el repo es publico.

COMO SE ENGANCHA. `supabase.create_client` crea el cliente de PostgREST la primera vez que se usa
(`_init_postgrest_client`, y otra vez si cambia la sesion); se envuelve ese metodo EN ESTE cliente para que el
transporte HTTP de su sesion pase por `_Reintento`. Version fijada: supabase==2.31.0 (requirements.txt y los
workflows). 🔴 Si una version nueva mueve esas piezas, `cliente()` LANZA en vez de devolver un cliente sin reintento
(lo vigila test_escaner2_base.py). Con un cliente de mentira (los bancos de cada programa cambian `supabase` por un
doble), se devuelve el doble tal cual: no hay transporte que envolver.

Lo prueba test_escaner2_base.py con un PostgREST de mentira en 127.0.0.1 y el supabase-py de verdad.
"""
import json
import time

TOPE_SEGUNDOS = 240.0
ESPERAS = (5, 10, 20, 30)                # las del cartero (encargo C, #766); la ultima se repite mientras quede tope
CODIGOS_NO_EJECUTADO = ('PGRST001', 'PGRST002')
LECTURAS = ('GET', 'HEAD')
_MINIMO_PARA_REINTENTAR = 1.0             # si queda menos de 1 s de tope, no vale la pena

# Lo que el banco cambia para no dormir de verdad ni depender del reloj.
_dormir = time.sleep
_reloj = time.monotonic


class _Tope:
    """Los segundos gastados en reintentos en ESTE proceso (= este run): esperas + intentos que fallaron."""

    def __init__(self, segundos):
        self.segundos, self.gastado = segundos, 0.0

    def restante(self):
        return self.segundos - self.gastado


# Uno por proceso, compartido por todos los clientes que cree el programa (el rescate es otro proceso).
TOPE = _Tope(TOPE_SEGUNDOS)


def _codigo_postgrest(respuesta):
    """El `code` del cuerpo JSON de PostgREST, o None si no lo hay o no es JSON."""
    try:
        cuerpo = json.loads(respuesta.content)
    except (ValueError, TypeError):
        return None
    return cuerpo.get('code') if isinstance(cuerpo, dict) else None


def _que(request):
    """Tabla o funcion de la llamada, para el log: el ultimo trozo de la ruta, sin la consulta."""
    return request.url.path.rstrip('/').rsplit('/', 1)[-1] or '?'


def _espera(intento):
    return ESPERAS[min(intento, len(ESPERAS) - 1)]


_CLASE = []


def _clase_reintento():
    """La clase del transporte con reintento, creada una vez (httpx se importa tarde: lo trae supabase)."""
    if _CLASE:
        return _CLASE[0]
    import httpx

    class _Reintento(httpx.BaseTransport):
        """El transporte HTTP de la sesion de PostgREST, con la regla de arriba. Lo que no se reintenta pasa tal cual."""

        def __init__(self, interior, tope):
            self.interior, self.tope = interior, tope

        def handle_request(self, request):
            intento = 0
            while True:
                inicio = _reloj()
                try:
                    respuesta = self.interior.handle_request(request)
                except httpx.TransportError as ex:
                    if request.method not in LECTURAS:
                        raise                       # escritura con fallo de red: puede haberse ejecutado
                    motivo, ultimo_error, respuesta = 'fallo de red sin respuesta (%s)' % type(ex).__name__, ex, None
                else:
                    if respuesta.status_code != 503:
                        return respuesta
                    respuesta.read()
                    codigo = _codigo_postgrest(respuesta)
                    if codigo not in CODIGOS_NO_EJECUTADO:
                        return respuesta            # otro 503: como hoy
                    motivo, ultimo_error = '503 %s (no ejecutado)' % codigo, None
                self.tope.gastado += _reloj() - inicio
                espera = min(_espera(intento), self.tope.restante())
                if espera < _MINIMO_PARA_REINTENTAR:
                    print(f"REINTENTO_BASE_AGOTADO: {request.method} {_que(request)} · {motivo} · tope de "
                          f"{self.tope.segundos:.0f} s agotado ({self.tope.gastado:.0f} s gastados en este run): "
                          f"sale el error como siempre.", flush=True)
                    if ultimo_error is not None:
                        raise ultimo_error
                    return respuesta
                if respuesta is not None:
                    respuesta.close()
                print(f"REINTENTO_BASE: {request.method} {_que(request)} · {motivo} · intento {intento + 2} en "
                      f"{espera:.0f} s · tope gastado {self.tope.gastado:.0f}/{self.tope.segundos:.0f} s", flush=True)
                _dormir(espera)
                self.tope.gastado += espera
                intento += 1

        def close(self):
            self.interior.close()

    _CLASE.append(_Reintento)
    return _Reintento


def _poner_reintento(postgrest, tope):
    """Envuelve el transporte de la sesion httpx de este cliente de PostgREST (y el de sus `mounts`, si los hay)."""
    import httpx
    Reintento = _clase_reintento()
    sesion = postgrest.session
    if not isinstance(sesion, httpx.Client) or not isinstance(getattr(sesion, '_transport', None), httpx.BaseTransport):
        raise RuntimeError('escaner2_base: la sesion de PostgREST no es la esperada (¿otra version de supabase?); '
                           'no se crea un cliente sin reintento')
    if not isinstance(sesion._transport, Reintento):
        sesion._transport = Reintento(sesion._transport, tope)
    for patron, transporte in list(getattr(sesion, '_mounts', {}).items()):
        if transporte is not None and not isinstance(transporte, Reintento):
            sesion._mounts[patron] = Reintento(transporte, tope)
    return postgrest


def cliente(url, llave, options=None):
    """`supabase.create_client(url, llave)` con el reintento de PostgREST. Mismo cliente, mismas llamadas."""
    import supabase
    sb = supabase.create_client(url, llave) if options is None else supabase.create_client(url, llave, options)
    if type(sb).__module__.split('.')[0] != 'supabase':
        return sb                                   # un doble de los bancos: nada que envolver
    crear = getattr(sb, '_init_postgrest_client', None)
    if not callable(crear) or not hasattr(sb, '_postgrest'):
        raise RuntimeError('escaner2_base: supabase ya no crea PostgREST con _init_postgrest_client (¿otra version?); '
                           'no se crea un cliente sin reintento')

    def _crear_con_reintento(*a, **kw):
        return _poner_reintento(crear(*a, **kw), TOPE)

    sb._init_postgrest_client = _crear_con_reintento
    if sb._postgrest is not None:
        _poner_reintento(sb._postgrest, TOPE)
    return sb
