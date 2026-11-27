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
    confirmada como la de ahora: el motivo nombra la pasada aplicada y no puede haber otra aplicada despues, o
  · (solo OSMA) quedo 'rechazada' «OSMA no ha regenerado…», pero el fichero de ahora es EXACTAMENTE el de la ultima
    aplicada (el md5 de su copia en el almacen) y desde ella no ha vencido ninguna lectura prevista de su horario
    (`disp_frescura_en`: ultima_aplicada >= ultima_prevista). Es el fin de semana y el lunes antes de las 07:15: OSMA
    no publica y ese fichero ES lo que tiene. Si ha vencido una prevista sin aplicar: «OSMA no ha publicado fichero
    nuevo hoy; el último es del <fecha>».
En cualquier otro caso (fallida, rechazada_vaciado, otra rechazada, la web no deja, no se pudo lanzar) devuelve el
motivo, para que Fernando lo lea en la pantalla de la v2:
«no he podido leer a TCG ahora (<por que>); no se valora con la lectura del <dia y hora de Madrid>».
NUNCA se cae a la ultima lectura guardada.

🔑 LA LECTURA DE HACE MENOS DE RECIENTE_MIN MINUTOS (quien dirige, 27-nov-2026): si el proveedor tiene una lectura buena
   (aplicada, o «al día» de la ultima aplicada) TERMINADA hace menos de 15 min, el PRO no vuelve a leer: barre desde
   esa y lo dice («leída hace N min»). A todos los efectos es «en directo», y quita el doble recuento de dos PRO
   seguidos, una entrada mas en la web de TCG (su pagina anti-robots) y hace barato el reintento.

LOS CONTADORES POR PASADA (disp_aplicar_pasada no tiene reloj: cuenta pasadas, no horas):
  1. EL FRENO DEL 90 % (`rechazos_para_aceptar`) cuenta las 'rechazada_vaciado' desde la ultima aplicada. Una lectura
     del PRO que sale vaciada queda 'fallida', con el motivo «vaciado en la lectura del Escaneo PRO (no cuenta para el
     freno): …», y no suma (`GuardaPro`, que la pasada recibe como `guarda`; sin ella, la horaria de siempre). Y si ya
     hay tantos rechazos como para aceptar la caida, el PRO NO LEE (`antes_de_leer`): una caida la acepta la lectura
     horaria, nunca un boton.
  2. LAS AUSENCIAS Y LA FALTA DE DATO (`ausencias_para_salir`, `sin_dato_para_agotar`): una lectura del PRO cuenta como
     cualquier otra (quien dirige, 27-nov-2026). Lo peor: un producto que el proveedor ha quitado de su fichero sale del
     catalogo unos minutos antes, y vuelve cuando reaparece. El doble recuento de dos PRO seguidos lo quita la regla de
     los RECIENTE_MIN minutos. Contarlas por tiempo es una migracion de la v2: el siguiente paso, no este.
  3. «Al día» y 'fallida' no mueven ningun contador: la funcion de la base ni las ve.
OTRAS:
  4. TCG lee como mucho FICHAS_FUNKO_PRO fichas de Funko antes de la foto, y nunca el lector de tramos de despues.
  5. Lo que la horaria hace tras aplicar (las novedades, con su aviso de avalancha; en OSMA, la copia del Excel y las
     fechas de vuelta) se hace igual, porque si no se perderia: la seleccion de novedades lee los cambios de ESA pasada.
     Pero DESPUES de cerrar la pasada del barrido (`Lectura.despues`), para que la pantalla no espere.
  6. ¿Otra lectura en marcha? El workflow del barrido comparte el grupo de `concurrency` de la lectura horaria.
     Ademas, por si acaso, el PRO no lee si hay una pasada 'leyendo' del proveedor de hace menos de 1 h
     (`antes_de_leer`).

🔴 REPO PUBLICO: este modulo solo imprime estados y recuentos. Los motivos (pueden llevar el de la base) van a
   `escaner2_pasada.motivo_fallo`, que es privada.
🔒 No escribe nada suyo. Lo que se escribe lo escriben la pasada (disp_*) y el barrido (escaner2_*). La unica
   escritura propia es poner en 'fallida' una pasada de ESTE run que la funcion ha dejado 'rechazada_vaciado'
   (punto 1). Lee, ademas, `disp_frescura_en` y la copia del ultimo Excel de OSMA (solo OSMA).
"""
import hashlib
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
# 🔑 15 min: lo que tarda en cambiar algo que importe para comprar (la horaria de TCG y DBLine es cada hora; OcioStock y
#    OSMA, un fichero al dia) y lo que cubre dos clics seguidos y el reintento de la pagina anti-robots de TCG.
RECIENTE_MIN = 15
PREFIJO_VACIADO = 'vaciado en la lectura del Escaneo PRO (no cuenta para el freno): '
REGENERADO_OSMA = 'OSMA no ha regenerado'


class Lectura:
    """Lo que devuelve `leer_en_directo` (y cada lector): `foto` es la pasada de disp_pasada de la que sale el barrido
    (None si no se sigue), con `motivo` el porque; `pared`, la web de TCG ha enseñado su pagina anti-robots y queda
    otro intento en otra maquina (`siguiente`); `despues`, lo que la horaria hace tras aplicar (devuelve True si fue
    bien). Del lector: `confirma`, la aplicada que su lectura confirma sin decir «al día» (OSMA), o `por_que`, el
    motivo de no seguir que el lector ya sabe."""

    def __init__(self, pid=None, foto=None, motivo=None, pared=False, siguiente=None, despues=None, confirma=None,
                 por_que=None):
        self.pid, self.foto, self.motivo = pid, foto, motivo
        self.pared, self.siguiente, self.despues = pared, siguiente, despues
        self.confirma, self.por_que = confirma, por_que


def _fecha(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
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
    par = (sb.table('disp_parametros').select('rechazos_para_aceptar').eq('proveedor', proveedor).limit(1).execute()
           .data or [{}])[0]
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
    """Lo que la pasada de disponibilidad hace distinto cuando la lanza el Escaneo PRO (cabecera, punto 1: el vaciado del
    PRO no cuenta para el freno). La pasada la recibe como `guarda`; sin ella (la horaria), no cambia nada."""

    def __init__(self, sb, proveedor):
        self.sb, self.proveedor = sb, proveedor

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


def decidir(sb, proveedor, pid):
    """(foto, None) si el barrido puede salir de la pasada `pid`, o (None, por_que)."""
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


def lectura_reciente(sb, proveedor, ahora, minutos=RECIENTE_MIN):
    """(foto, hace_min) de la lectura buena del proveedor (aplicada, o «al día» de la ultima aplicada) TERMINADA hace
    menos de `minutos`, o None. La buena es la que `decidir` daria por buena hoy (si despues se ha aplicado otra, no)."""
    filas = (sb.table('disp_pasada').select('id,estado,motivo,terminada_en').eq('proveedor', proveedor)
             .order('terminada_en', desc=True).limit(20).execute().data or [])
    for f in filas:
        t = _fecha(f.get('terminada_en'))
        if t is None or not (timedelta(0) <= ahora - t < timedelta(minutes=minutos)):
            continue
        if f.get('estado') == 'aplicada' or (f.get('estado') == 'rechazada'
                                             and str(f.get('motivo') or '').startswith('al día')):
            foto, _por_que = decidir(sb, proveedor, f['id'])
            if foto:
                return foto, int((ahora - t).total_seconds() // 60)
    return None


def confirmar_osma(sb, contenido, ahora, ruta_copia, bucket='escaner2', creado=None):
    """(aplicada, None) si el fichero de OSMA de ahora confirma la ultima aplicada (cabecera: el mismo fichero, y sin
    ninguna lectura prevista vencida desde ella), o (None, por_que). NUNCA LANZA."""
    ult = _ultima_aplicada(sb, 'OSMA')
    if not ult:
        return None, 'OSMA no ha regenerado su fichero y no hay ninguna lectura aplicada que confirmar'
    try:
        copia = sb.storage.from_(bucket).download(ruta_copia)
    except Exception as ex:  # noqa: BLE001
        return None, f'no se ha podido leer la copia del último fichero aplicado para compararlo ({type(ex).__name__})'
    if not contenido or hashlib.md5(copia).hexdigest() != hashlib.md5(contenido).hexdigest():
        return None, 'OSMA da un fichero que no es más nuevo que la última lectura aplicada ni es el mismo'
    try:
        filas = sb.rpc('disp_frescura_en', {'p_ahora': ahora.isoformat()}).execute().data or []
        f = next(x for x in filas if x.get('proveedor') == 'OSMA')
    except Exception as ex:  # noqa: BLE001
        return None, f'no se ha podido mirar el horario de OSMA (disp_frescura_en: {type(ex).__name__})'
    u, p = _fecha(f.get('ultima_aplicada')), _fecha(f.get('ultima_prevista'))
    if u is None or (p is not None and u < p):
        del_fichero = f'del {_madrid(creado)}' if creado else 'de antes de la última lectura prevista'
        return None, f'OSMA no ha publicado fichero nuevo hoy; el último es {del_fichero}'
    return ult['id'], None


# ── Los cuatro lectores: la pasada de cada proveedor, con la guarda del PRO ─────────────────────────────────────
def _leer_tcg(sb, env, run_id, intento, guarda, sesion=None, dormir=None):
    """`sesion` y `dormir`: los de mentira del banco (como `principal` de la pasada); en el workflow, los de verdad."""
    import escaner2_tcg_disponibilidad as d
    from escaner2_tcg_web import Web, sesion_de_verdad
    web = Web(sesion if sesion is not None else sesion_de_verdad(), **({'dormir': dormir} if dormir else {}))
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


def _leer_osma(sb, env, run_id, intento, guarda, ahora=None):
    import requests
    import escaner2_osma_disponibilidad as d
    sesion = requests.Session()
    sesion.headers['User-Agent'] = d.AGENTE
    _c, pid, fila, contenido = d.aplicar(sb, sesion, env['OSMA_USER'], env['OSMA_PASS'], run_id, ahora, guarda=guarda)
    if (fila or {}).get('estado') == 'aplicada':
        return Lectura(pid=pid, despues=lambda: d.tras_aplicar(sb, sesion, pid, fila, contenido, ahora) == 0)
    p = (sb.table('disp_pasada').select('estado,motivo').eq('id', pid).limit(1).execute().data or [{}])[0] if pid else {}
    if p.get('estado') == 'rechazada' and str(p.get('motivo') or '').startswith(REGENERADO_OSMA) and contenido:
        try:
            creado = d.fecha_de_creacion(contenido)
        except Exception:  # noqa: BLE001
            creado = None
        conf, por_que = confirmar_osma(sb, contenido, ahora or datetime.now(timezone.utc), d.RUTA_COPIA, d.BUCKET,
                                       creado)
        print(f">>> OSMA: el fichero de ahora {'CONFIRMA la última lectura aplicada (el mismo, sin lectura prevista vencida)' if conf else 'NO confirma la última lectura aplicada'}.",
              flush=True)
        return Lectura(pid=pid, confirma=conf, por_que=por_que)
    return Lectura(pid=pid)


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
        reciente = lectura_reciente(sb, proveedor, ahora)
    except Exception as ex:  # noqa: BLE001 — sin saberlo, se lee
        print(f">>> LECTURA EN DIRECTO de {nombre}: no se ha podido mirar la última lectura ({type(ex).__name__}).",
              flush=True)
        reciente = None
    if reciente:
        print(f">>> LECTURA EN DIRECTO de {nombre}: leída hace {reciente[1]} min (menos de {RECIENTE_MIN}): no se vuelve a "
              f"leer; sale de esa lectura.", flush=True)
        return Lectura(foto=reciente[0])
    try:
        no = antes_de_leer(sb, proveedor, ahora)
    except Exception as ex:  # noqa: BLE001
        no = f'no se ha podido mirar si se puede leer ({type(ex).__name__})'
    if no:
        return Lectura(motivo=motivo_de_fallo(sb, proveedor, no))
    print(f">>> LECTURA EN DIRECTO de {nombre} (intento {intento}): la misma pasada que la horaria.", flush=True)
    try:
        r = (lectores or LECTORES)[proveedor](sb, env, str(run_id or ''), intento, GuardaPro(sb, proveedor))
    except (Exception, SystemExit) as ex:  # noqa: BLE001 — 🔴 solo el tipo al registro
        print(f">>> LECTURA EN DIRECTO de {nombre}: se ha caído ({type(ex).__name__}).", flush=True)
        return Lectura(motivo=motivo_de_fallo(sb, proveedor, f'la lectura se ha caído ({type(ex).__name__})'))
    if r.pared:
        r.motivo = motivo_de_fallo(sb, proveedor, f'la web ha enseñado su página anti-robots a esta máquina; va el '
                                                  f'intento {r.siguiente} en otra')
        return r
    try:
        if r.confirma:
            ult = _ultima_aplicada(sb, proveedor)
            r.foto, por_que = ((r.confirma, None) if ult and ult.get('id') == r.confirma else
                               (None, 'la lectura confirma una aplicada que ya no es la última'))
        elif r.por_que:
            r.foto, por_que = None, r.por_que
        else:
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
