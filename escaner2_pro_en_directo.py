#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL ESCANEO PRO LEE AL PROVEEDOR EN ESE MOMENTO (encargo PD, 27-nov-2026).

Fernando, 27-nov-2026: «El PRO tiene que ser en directo». Hasta hoy el barrido del Escaneo PRO de TCG, DBLine,
OcioStock y OSMA cogia «la ultima pasada aplicada» de disp_pasada sin mirar su edad: el 27-nov el de TCG valoro con
la lectura del dia anterior, sin decirlo, porque las lecturas horarias llevaban 20 h fallando.

Desde este encargo, el barrido (escaner2_<proveedor>_barrido.py) llama a `leer_en_directo` ANTES de construir la foto.
Esa funcion corre LA MISMA PASADA que la lectura horaria (escaner2_<proveedor>_disponibilidad.py: las mismas guardas y
`disp_aplicar_pasada`), dentro del mismo run, y solo deja seguir al barrido si la pasada de ESTE run:
  · quedo 'aplicada' (la foto de la que sale el barrido es ESA pasada), o
  · quedo 'rechazada' con motivo «al día…», porque el contenido es el de la ultima aplicada. Esa foto queda
    confirmada como la de ahora: el motivo nombra la pasada aplicada y no puede haber otra aplicada despues.
En cualquier otro caso (fallida, rechazada_vaciado, otra rechazada, la web no deja, no se pudo lanzar) devuelve el
motivo, para que Fernando lo lea en la pantalla de la v2:
«no he podido leer a TCG ahora (<por que>); no se valora con la lectura del <dia y hora de Madrid>».
NUNCA se cae a la ultima lectura guardada.

LO QUE LA PASADA DEL PRO HACE DISTINTO DE LA HORARIA (todo por `GuardaPro`, que la pasada recibe como parametro
`guarda`; sin ella, la pasada horaria es la de siempre):
  1. EL FRENO DEL 90 % (`rechazos_para_aceptar` de disp_parametros) cuenta las 'rechazada_vaciado' desde la ultima
     aplicada. Una lectura del PRO que sale vaciada queda 'fallida', con el motivo «vaciado en la lectura del
     Escaneo PRO (no cuenta para el freno): …», y no suma rechazos. Y si ya hay tantos rechazos como para aceptar la
     caida, el PRO NO LEE (`antes_de_leer`): una caida del catalogo la acepta la lectura horaria, nunca un boton.
  2. LAS AUSENCIAS Y LA FALTA DE DATO (`ausencias_para_salir`, `sin_dato_para_agotar`) cuentan pasadas aplicadas, no
     horas. Si la ultima aplicada es de hace menos de PISO_MIN minutos y aplicar la lectura del PRO sacaria a alguien
     del catalogo o lo agotaria por falta de dato, el PRO no la aplica (`antes_de_aplicar`): queda 'fallida' con el
     motivo, y no suma nada. Asi, dos PRO seguidos en un minuto no sacan a nadie por «2 ausencias».
  3. «Al día» y 'fallida' no mueven ningun contador: la funcion de la base ni las ve.
  4. TCG lee como mucho FICHAS_FUNKO_PRO fichas de Funko antes de la foto, y nunca el lector de tramos de despues.
  5. Lo que la horaria hace tras aplicar (las novedades; en OSMA, la copia del Excel y las fechas de vuelta) se hace
     igual, porque si no se perderia: la seleccion de novedades lee los cambios de ESA pasada. Pero se hace DESPUES de
     cerrar la pasada del barrido (`Lectura.despues`), para que la pantalla no espere.
  6. ¿Otra lectura en marcha? El workflow del barrido comparte el grupo de `concurrency` de la lectura horaria.
     Ademas, por si acaso, el PRO no lee si hay una pasada 'leyendo' del proveedor de hace menos de 1 h
     (`antes_de_leer`).

🔴 REPO PUBLICO: este modulo solo imprime estados y recuentos. Los motivos (pueden llevar el de la base) van a
   `escaner2_pasada.motivo_fallo`, que es privada.
🔒 No escribe nada suyo. Lo que se escribe lo escriben la pasada (disp_*) y el barrido (escaner2_*). La unica
   escritura propia es poner en 'fallida' una pasada de ESTE run que la funcion ha dejado 'rechazada_vaciado'
   (punto 1).
"""
import os
from datetime import datetime, timedelta, timezone

# El nombre que se le dice a Fernando y los secretos que necesita la lectura de cada uno (los de su workflow horario).
PROVEEDORES = {
    'TCG': ('TCG', ('TCG_USER', 'TCG_PASS')),
    'DBLINE': ('DBLine', ('DBLINE_USER', 'DBLINE_PASS')),
    'OCIOSTOCK': ('OcioStock', ('OCIOSTOCK_FEED_URL',)),
    'OSMA': ('OSMA', ('OSMA_USER', 'OSMA_PASS')),
}
TURNO = timedelta(hours=1)   # una 'leyendo' de menos de 1 h es una lectura viva (disp_aplicar_pasada da por muerta la de mas)
PISO_MIN = 15                # minutos: por debajo, el PRO no saca a nadie del catalogo ni lo agota por falta de dato
PAGINA = 1000
PREFIJO_VACIADO = 'vaciado en la lectura del Escaneo PRO (no cuenta para el freno): '


class Lectura:
    """Lo que devuelve `leer_en_directo` (y cada lector): `foto` es la pasada de disp_pasada de la que sale el barrido
    (None si no se sigue), con `motivo` el porque; `pared`, la web de TCG ha enseñado su pagina anti-robots y queda
    otro intento en otra maquina (`siguiente`); `despues`, lo que la horaria hace tras aplicar (devuelve True si fue
    bien)."""

    def __init__(self, pid=None, foto=None, motivo=None, pared=False, siguiente=None, despues=None):
        self.pid, self.foto, self.motivo = pid, foto, motivo
        self.pared, self.siguiente, self.despues = pared, siguiente, despues


def _fecha(v):
    if not v:
        return None
    t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _madrid(t):
    from zoneinfo import ZoneInfo
    return t.astimezone(ZoneInfo('Europe/Madrid')).strftime('%d-%m-%Y a las %H:%M')


def _ultima_aplicada(sb, proveedor):
    return (sb.table('disp_pasada').select('id,creada_en,terminada_en').eq('proveedor', proveedor)
            .eq('estado', 'aplicada').order('creada_en', desc=True).limit(1).execute().data or [None])[0]


def motivo_de_fallo(sb, proveedor, por_que):
    """El motivo para la pantalla de la v2: que no se ha podido leer, por que, y con que lectura NO se valora."""
    nombre = PROVEEDORES[proveedor][0]
    try:
        ult = _ultima_aplicada(sb, proveedor)
        t = _fecha(ult.get('terminada_en') or ult.get('creada_en')) if ult else None
        cola = (f'no se valora con la lectura del {_madrid(t)}' if t else
                'y no hay ninguna lectura anterior aplicada')
    except Exception:  # noqa: BLE001 — el motivo sale igual, sin la fecha
        cola = 'no se valora con ninguna lectura guardada'
    return f'no he podido leer a {nombre} ahora ({por_que}); {cola}'


def _parametros(sb, proveedor):
    return (sb.table('disp_parametros').select('rechazos_para_aceptar,ausencias_para_salir,sin_dato_para_agotar')
            .eq('proveedor', proveedor).limit(1).execute().data or [{}])[0]


def antes_de_leer(sb, proveedor, ahora):
    """El porque de NO abrir la lectura, o None. (a) Otra lectura del proveedor en marcha (una 'leyendo' de menos de
    TURNO). (b) El freno: tantas 'rechazada_vaciado' desde la ultima aplicada como para que esta aceptase la caida."""
    nombre = PROVEEDORES[proveedor][0]
    leyendo = (sb.table('disp_pasada').select('id,creada_en').eq('proveedor', proveedor).eq('estado', 'leyendo')
               .execute().data or [])
    vivas = [p for p in leyendo if _fecha(p.get('creada_en')) and ahora - _fecha(p['creada_en']) < TURNO]
    if vivas:
        desde = min(_fecha(p['creada_en']) for p in vivas)
        return (f'otra lectura de {nombre} está en marcha desde el {_madrid(desde)}; no se lee a la vez: vuelve a '
                f'barrer cuando acabe')
    par = _parametros(sb, proveedor)
    k = par.get('rechazos_para_aceptar')
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        return 'disp_parametros no da un rechazos_para_aceptar válido; sin él no se sabe si la lectura aceptaría una caída'
    ult = _ultima_aplicada(sb, proveedor)
    desde = _fecha(ult.get('creada_en')) if ult else None
    rechazos = (sb.table('disp_pasada').select('id,creada_en').eq('proveedor', proveedor)
                .eq('estado', 'rechazada_vaciado').order('creada_en', desc=True).limit(k + 1).execute().data or [])
    n = sum(1 for r in rechazos if desde is None or (_fecha(r.get('creada_en')) and _fecha(r['creada_en']) > desde))
    if n >= k:
        return (f'{nombre} lleva {n} lecturas rechazadas por vaciado desde la última buena: la siguiente podría aceptar '
                f'la caída del catálogo, y eso lo decide la lectura horaria, no el Escaneo PRO')
    return None


class GuardaPro:
    """Lo que la pasada de disponibilidad hace distinto cuando la lanza el Escaneo PRO (ver la cabecera, puntos 1 y 2).
    La pasada la recibe como `guarda` y la llama en tres sitios; sin ella (la horaria), no cambia nada."""

    def __init__(self, sb, proveedor, ahora=None, piso_min=PISO_MIN):
        self.sb, self.proveedor, self.piso = sb, proveedor, timedelta(minutes=piso_min)
        self.ahora = ahora or datetime.now(timezone.utc)

    def sin_freno(self, estado, motivo):
        """(estado, motivo) con que se cierra una pasada que el programa rechaza: el vaciado del PRO, 'fallida'."""
        if estado == 'rechazada_vaciado':
            return 'fallida', PREFIJO_VACIADO + motivo
        return estado, motivo

    def tras_aplicar(self, pid, fila):
        """La fila de disp_pasada tras `disp_aplicar_pasada`: si la funcion la ha dejado 'rechazada_vaciado', pasa a
        'fallida' (solo esa pasada, y solo si sigue asi) y se devuelve como queda."""
        if fila.get('estado') != 'rechazada_vaciado':
            return fila
        motivo = PREFIJO_VACIADO + str(fila.get('motivo') or '')
        (self.sb.table('disp_pasada').update({'estado': 'fallida', 'motivo': motivo[:1000]}).eq('id', pid)
         .eq('estado', 'rechazada_vaciado').execute())
        return dict(fila, estado='fallida', motivo=motivo[:1000])

    def antes_de_aplicar(self, filas):
        """El porque de NO llamar a disp_aplicar_pasada con `filas` (las de disp_lectura de la pasada), o None: con la
        ultima aplicada de hace menos de `piso`, que esta lectura sacase a alguien del catalogo (otra ausencia) o lo
        agotase por falta de dato. 🔑 La MISMA regla que la funcion (`ausencias + 1 >= ausencias_para_salir`,
        `pasadas_sin_dato + 1 >= sin_dato_para_agotar`), leida, no inventada."""
        ult = _ultima_aplicada(self.sb, self.proveedor)
        t = _fecha(ult.get('creada_en')) if ult else None
        if t is None or self.ahora - t >= self.piso:
            return None
        par = _parametros(self.sb, self.proveedor)
        a, s = par.get('ausencias_para_salir'), par.get('sin_dato_para_agotar')
        if not all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in (a, s)):
            return 'disp_parametros no da ausencias_para_salir y sin_dato_para_agotar válidos'
        leidas = {f['producto_prov']: f for f in filas}
        salen = agotan = desde = 0
        while True:
            pag = (self.sb.table('disp_estado').select('producto_prov,ausencias,disponible,pasadas_sin_dato')
                   .eq('proveedor', self.proveedor).eq('en_catalogo', True).order('producto_prov')
                   .range(desde, desde + PAGINA - 1).execute().data or [])
            for e in pag:
                f = leidas.get(e['producto_prov'])
                if f is None:
                    salen += int(e.get('ausencias') or 0) + 1 >= a
                elif f.get('sin_dato_disponibilidad') and e.get('disponible'):
                    agotan += int(e.get('pasadas_sin_dato') or 0) + 1 >= s
            if len(pag) < PAGINA:
                break
            desde += PAGINA
        if not (salen or agotan):
            return None
        minutos = int((self.ahora - t).total_seconds() // 60)
        partes = ([f'sacaría del catálogo {salen} producto(s) por {a} ausencias'] if salen else []) + \
                 ([f'agotaría {agotan} por {s} lecturas sin dato'] if agotan else [])
        return (f'la última lectura aplicada es de hace {minutos} min y esta {" y ".join(partes)}: tan seguidas no '
                f'cuentan como lecturas distintas; vuelve a barrer pasados {int(self.piso.total_seconds() // 60)} min')


def decidir(sb, proveedor, pid):
    """(foto, None) si el barrido puede salir de la pasada `pid` de ESTE run, o (None, por_que)."""
    if not pid:
        return None, 'la lectura no llegó a abrir su pasada'
    fila = (sb.table('disp_pasada').select('id,proveedor,estado,motivo,creada_en').eq('id', pid).limit(1).execute()
            .data or [None])[0]
    if not fila or fila.get('proveedor') != proveedor:
        return None, 'la pasada de la lectura no está en la base'
    estado, motivo = fila.get('estado'), str(fila.get('motivo') or '')
    ult = _ultima_aplicada(sb, proveedor)
    if estado == 'aplicada':
        if not ult or ult.get('id') != pid:
            return None, 'la lectura se aplicó, pero después se ha aplicado otra'
        return pid, None
    if estado == 'rechazada' and motivo.startswith('al día'):
        # 🔑 «Al día»: el motivo nombra la aplicada que se confirma, y no puede haber otra aplicada despues de esta pasada.
        if not ult or str(ult.get('id')) not in motivo:
            return None, 'la lectura dice «al día», pero la última aplicada no es la que nombra'
        t_ult, t_esta = _fecha(ult.get('creada_en')), _fecha(fila.get('creada_en'))
        if t_ult is None or t_esta is None or t_ult > t_esta:
            return None, 'la lectura dice «al día», pero hay una aplicada posterior'
        return ult['id'], None
    return None, f'{estado}: {motivo}' if motivo else str(estado)


# ── Los cuatro lectores: la pasada de cada proveedor, con la guarda del PRO ─────────────────────────────────────
def _leer_tcg(sb, env, run_id, intento, guarda):
    import escaner2_tcg_disponibilidad as d
    from escaner2_tcg_web import Web, sesion_de_verdad
    web = Web(sesion_de_verdad())
    _c, estado, _cat, _g, pid, _p = d.pasada(sb, web, run_id, env['TCG_USER'], env['TCG_PASS'], d._ahora(),
                                             fichas_funko=d.FICHAS_FUNKO_PRO, intento=intento, guarda=guarda)
    if estado == 'pared':
        return Lectura(pid=pid, pared=True, siguiente=intento + 1)
    return Lectura(pid=pid, despues=(lambda: d.novedades(sb, pid, run_id)) if estado == 'aplicada' else None)


def _leer_dbline(sb, env, run_id, intento, guarda):
    import escaner2_dbline_disponibilidad as d
    _c, pid, fila = d.aplicar(sb, run_id, d.hoy_madrid(), guarda=guarda)
    aplicada = (fila or {}).get('estado') == 'aplicada'
    return Lectura(pid=pid, despues=(lambda: d.tras_aplicar(sb, pid, fila, run_id) == 0) if aplicada else None)


def _leer_ociostock(sb, env, run_id, intento, guarda):
    import requests
    import escaner2_ociostock_disponibilidad as d
    sesion = requests.Session()
    sesion.headers['User-Agent'] = d.AGENTE
    _c, pid, fila = d.aplicar(sb, sesion, env['OCIOSTOCK_FEED_URL'], run_id, guarda=guarda)
    aplicada = (fila or {}).get('estado') == 'aplicada'
    return Lectura(pid=pid, despues=(lambda: d.tras_aplicar(sb, pid, fila, run_id) == 0) if aplicada else None)


def _leer_osma(sb, env, run_id, intento, guarda):
    import requests
    import escaner2_osma_disponibilidad as d
    sesion = requests.Session()
    sesion.headers['User-Agent'] = d.AGENTE
    _c, pid, fila, contenido = d.aplicar(sb, sesion, env['OSMA_USER'], env['OSMA_PASS'], run_id, guarda=guarda)
    aplicada = (fila or {}).get('estado') == 'aplicada'
    return Lectura(pid=pid, despues=(lambda: d.tras_aplicar(sb, sesion, pid, fila, contenido) == 0) if aplicada else None)


LECTORES = {'TCG': _leer_tcg, 'DBLINE': _leer_dbline, 'OCIOSTOCK': _leer_ociostock, 'OSMA': _leer_osma}


def leer_en_directo(sb, proveedor, env=None, run_id='', intento=1, lectores=None, ahora=None):
    """La lectura del proveedor AHORA, para el barrido (ver la cabecera). Devuelve una `Lectura`: con `foto` se sigue;
    sin ella, `motivo` es el de la pantalla (o `pared`, otro intento en otra maquina). NUNCA LANZA."""
    env = os.environ if env is None else env
    nombre, secretos = PROVEEDORES[proveedor]
    ahora = ahora or datetime.now(timezone.utc)
    falta = [s for s in secretos if not env.get(s)]
    if falta:
        return Lectura(motivo=motivo_de_fallo(sb, proveedor, f'faltan los secretos {"/".join(falta)} en el workflow'))
    try:
        no = antes_de_leer(sb, proveedor, ahora)
    except Exception as ex:  # noqa: BLE001
        no = f'no se ha podido mirar si se puede leer ({type(ex).__name__})'
    if no:
        return Lectura(motivo=motivo_de_fallo(sb, proveedor, no))
    print(f">>> LECTURA EN DIRECTO de {nombre} (intento {intento}): la misma pasada que la horaria.", flush=True)
    try:
        r = (lectores or LECTORES)[proveedor](sb, env, str(run_id or ''), intento, GuardaPro(sb, proveedor, ahora))
    except (Exception, SystemExit) as ex:  # noqa: BLE001 — 🔴 solo el tipo al registro
        print(f">>> LECTURA EN DIRECTO de {nombre}: se ha caído ({type(ex).__name__}).", flush=True)
        return Lectura(motivo=motivo_de_fallo(sb, proveedor, f'la lectura se ha caído ({type(ex).__name__})'))
    if r.pared:
        r.motivo = motivo_de_fallo(sb, proveedor, f'la web ha enseñado su página anti-robots a esta máquina; va el '
                                                  f'intento {r.siguiente} en otra')
        return r
    try:
        r.foto, por_que = decidir(sb, proveedor, r.pid)
    except Exception as ex:  # noqa: BLE001
        r.foto, por_que = None, f'no se ha podido comprobar la lectura ({type(ex).__name__})'
    if r.foto is None:
        # `despues` se queda: si la pasada se aplico, sus novedades se hacen igual (si no, se perderian).
        r.motivo = motivo_de_fallo(sb, proveedor, por_que)
    print(f">>> LECTURA EN DIRECTO de {nombre}: {'sale la foto de esta lectura' if r.foto else 'NO se sigue'}.",
          flush=True)
    return r


# ── Lo comun de los cuatro barridos ────────────────────────────────────────────────────────────────────────────
def abrir_o_retomar(sb, fila, env=None):
    """La pasada de escaner2_pasada de este barrido: la que abrio el job `abrir` de ESTE run (ESCANER2_PASADA, tiene
    que seguir 'descargando', ser del proveedor y del run) o, sin ella, una nueva con `fila`. Devuelve su id."""
    env = os.environ if env is None else env
    previa = (env.get('ESCANER2_PASADA') or '').strip()
    if not previa:
        sb.table('escaner2_pasada').insert(fila).execute()
        return fila['id']
    p = (sb.table('escaner2_pasada').select('id,proveedor,estado,run_id').eq('id', previa).limit(1).execute().data
         or [None])[0]
    if not p or p.get('proveedor') != fila['proveedor'] or p.get('estado') != 'descargando' \
            or str(p.get('run_id')) != str(fila.get('run_id')):
        raise ValueError('ESCANER2_PASADA no es una pasada «descargando» de este proveedor y de este run')
    return previa


def salida_github(env=None, **valores):
    """Deja `valores` en GITHUB_OUTPUT (el workflow los lee). False si no hay donde."""
    env = os.environ if env is None else env
    ruta = env.get('GITHUB_OUTPUT')
    if not ruta:
        return False
    with open(ruta, 'a', encoding='utf-8') as fh:
        for k, v in valores.items():
            fh.write(f'{k}={v}\n')
    return True


def intento_de(env=None, maximo=1):
    env = os.environ if env is None else env
    t = (env.get('INTENTO') or '1').strip()
    if not (t.isdigit() and 1 <= int(t) <= maximo):
        raise ValueError(f'INTENTO tiene que ser un número de 1 a {maximo}')
    return int(t)


class FalloLectura(Exception):
    """La pasada del barrido queda 'fallida' con este motivo: la lectura en directo no deja seguir."""


def _despues(lectura):
    """Lo de despues de aplicar (novedades…), si la lectura se aplico. NUNCA LANZA. True si fue bien o no tocaba."""
    if lectura is None or lectura.despues is None:
        return True
    try:
        ok = bool(lectura.despues())
    except Exception as ex:  # noqa: BLE001 — 🔴 solo el tipo
        print(f">>> TRAS LA LECTURA: lo de después de aplicar ha fallado ({type(ex).__name__}); la pasada sigue aplicada.",
              flush=True)
        return False
    print(f">>> TRAS LA LECTURA: lo de después de aplicar (novedades…) {'bien' if ok else 'en ROJO (el detalle, en la base)'}.",
          flush=True)
    return ok


def correr_barrido(sb, proveedor, fila, barrer, fallos, abortar, listo, env=None, argv=None, maximo_intentos=1,
                   lectores=None):
    """El `main` de los cuatro barridos. `fila`: la de escaner2_pasada que se abre; `barrer(pasada, foto)` →
    (cierre, extra), con `foto` la pasada de disp_pasada de la lectura de ahora; `fallos`, las excepciones cuyo texto
    es el motivo; `listo(cierre, extra)`, lo que se imprime al quedar lista.
      · `--abrir` (el job `abrir` del workflow): solo abre la pasada y deja su id en GITHUB_OUTPUT (`pasada`), para que
        la pantalla la vea antes de que la lectura espere su turno;
      · sin argumentos: retoma esa pasada (ESCANER2_PASADA; sin ella, abre una), lee al proveedor en directo y, si la
        lectura deja, barre. Si la web de TCG enseña su pagina anti-robots y queda intento, la pasada SIGUE
        'descargando' y GITHUB_OUTPUT dice `pared=1`, `siguiente` y `pasada`: la retoma el job siguiente, en otra
        maquina, en el MISMO run (la pantalla no la pierde)."""
    env = os.environ if env is None else env
    argv = [] if argv is None else list(argv)
    nombre = PROVEEDORES[proveedor][0]
    if argv == ['--abrir']:
        sb.table('escaner2_pasada').insert(fila).execute()
        if not salida_github(env, pasada=fila['id']):
            abortar('sin GITHUB_OUTPUT no se puede pasar la pasada al job de la lectura')
        print(f">>> Pasada {fila['id']} abierta (descargando) · {nombre} · modo {fila.get('modo')}. La lectura en "
              f"directo, en el job siguiente.", flush=True)
        return
    if argv:
        abortar('uso: <barrido>.py [--abrir]')
    try:
        intento = intento_de(env, maximo_intentos)
        pasada = abrir_o_retomar(sb, fila, env)
    except ValueError as ex:
        abortar(str(ex))
    print(f">>> Pasada {pasada} (descargando) · {nombre} · modo {fila.get('modo')} · intento {intento}.", flush=True)
    lectura = None
    try:
        lectura = leer_en_directo(sb, proveedor, env, env.get('GITHUB_RUN_ID') or '', intento, lectores)
        if lectura.pared:
            if salida_github(env, pared=1, siguiente=lectura.siguiente, pasada=pasada):
                print(f"ESCANER2_PARED_REINTENTO: la web de {nombre} ha enseñado su página anti-robots a esta máquina; la "
                      f"pasada {pasada} sigue «descargando» y la retoma el intento {lectura.siguiente} en otra máquina.",
                      flush=True)
                return
            raise FalloLectura(lectura.motivo + '; y sin GITHUB_OUTPUT no se puede pedir el siguiente intento')
        if lectura.foto is None:
            raise FalloLectura(lectura.motivo)
        cierre, extra = barrer(pasada, lectura.foto)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza (el check del cuadre), la pasada queda 'fallida'.
        sb.table('escaner2_pasada').update(cierre).eq('id', pasada).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, tuple(fallos) + (FalloLectura,)) else f'{type(ex).__name__}: {ex}'
        sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo[:1000],
                                                 'terminada_en': datetime.now(timezone.utc).isoformat()},
                                                **getattr(ex, 'recuentos', {}))).eq('id', pasada).execute()
        _despues(lectura)
        # Al log, solo el tipo: el motivo puede llevar precios o EAN y el repo es publico.
        abortar(f'pasada {pasada} fallida ({type(ex).__name__}); el motivo está en escaner2_pasada.motivo_fallo')
    listo(cierre, extra)
    if not _despues(lectura):
        abortar(f'pasada {pasada} lista, pero lo de después de la lectura ha salido en rojo (novedades…)')
