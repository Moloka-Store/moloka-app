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
  5. Lo que la horaria hace tras aplicar (las novedades, con su aviso de avalancha; en OSMA, las fechas de vuelta) se
     hace igual, porque si no se perderia: la seleccion de novedades lee los cambios de ESA pasada. Va en SU PASO del
     workflow (`python escaner2_pro_en_directo.py --despues <PROVEEDOR>`, `tras_la_lectura`), con su tope, que corre
     aunque el barrido falle o muera: recoge toda pasada APLICADA de ESTE run que no lo tenga hecho. Ese paso pasa a
     'fallida' tambien un vaciado que se quedo sin pasar (punto 1). En OSMA, la copia del Excel la guarda la lectura en
     el acto (la necesita la confirmacion de sabado a lunes).
  6. ¿Otra lectura en marcha? El job `abrir` (sin el grupo) decide ANTES de que la lectura entre en el grupo de la
     horaria (`previo`): con una lectura buena de hace menos de RECIENTE_MIN, se barre desde ella en un job sin grupo;
     con una pasada 'leyendo' viva, espera mirando la base hasta ESPERA_MAX_S a que acabe, y si no acaba, 'fallida' con
     el motivo (nunca un PRO esperando 20 min, ni pendiente en el grupo cancelando una horaria). Solo si no hay ninguna
     lectura en marcha, la lectura del PRO entra en el grupo de la horaria (`concurrency`), y sigue sin leer si hay una
     'leyendo' de menos de 1 h (`antes_de_leer`).
  7. Lo que el barrido deja escrito (barrido.json y el «Resumen» del Excel, `nota_de`): de que lectura sale y cuando se
     comprobo, en hora de Madrid («leída ahora…», «confirmada hoy a las HH:MM; el contenido es el de la lectura del…»,
     «leída hace N min…»).

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
    bien; el barrido no la llama: va en su paso, `tras_la_lectura`); `nota`, lo que el barrido deja escrito de la
    lectura de la que sale (`nota_de`). Del lector: `confirma`, la aplicada que su lectura confirma sin decir «al día» (OSMA), o `por_que`, el
    motivo de no seguir que el lector ya sabe, o `motivo_entero`, el motivo de la pantalla tal cual (TCG sin intentos)."""

    def __init__(self, pid=None, foto=None, motivo=None, pared=False, siguiente=None, despues=None, confirma=None,
                 por_que=None, nota=None, motivo_entero=None):
        self.pid, self.foto, self.motivo = pid, foto, motivo
        self.pared, self.siguiente, self.despues = pared, siguiente, despues
        self.confirma, self.por_que, self.nota = confirma, por_que, nota
        self.motivo_entero = motivo_entero


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


# ── Lo de despues de aplicar, como la horaria: SU PROPIO PASO del workflow (`--despues`) ─────────────────────────
def _despues_tcg(sb, env, run_id, pid, fila):
    import escaner2_tcg_disponibilidad as d
    return bool(d.novedades(sb, pid, run_id))


def _despues_dbline(sb, env, run_id, pid, fila):
    import escaner2_dbline_disponibilidad as d
    return d.tras_aplicar(sb, pid, fila, run_id) == 0


def _despues_ociostock(sb, env, run_id, pid, fila):
    import escaner2_ociostock_disponibilidad as d
    return d.tras_aplicar(sb, pid, fila, run_id) == 0


def _despues_osma(sb, env, run_id, pid, fila, sesion=None, ahora=None):
    """Las fechas de vuelta (la copia del Excel ya la guarda la lectura, justo tras aplicar: es lo que compara la
    confirmacion de sabado a lunes). Sin `sesion`, entra otra vez (un solo intento, como la horaria)."""
    import escaner2_osma_disponibilidad as d
    if sesion is None:
        import requests
        sesion = requests.Session()
        sesion.headers['User-Agent'] = d.AGENTE
        d.entrar(sesion, env['OSMA_USER'], env['OSMA_PASS'])
    codigo = d.fechas_de_vuelta(sb, sesion, ahora or datetime.now(timezone.utc), escribir=True)
    if (fila or {}).get('caida_aceptada'):
        codigo = 1
    return codigo == 0


DESPUES = {'TCG': _despues_tcg, 'DBLINE': _despues_dbline, 'OCIOSTOCK': _despues_ociostock, 'OSMA': _despues_osma}
CON_NOVEDADES = ('TCG', 'DBLINE', 'OCIOSTOCK')   # su «después» deja fila en nov_pasada: si la hay, ya esta hecho


def tras_la_lectura(sb, proveedor, run_id, env=None, despues=None):
    """EL PASO DE DESPUES DE LA LECTURA (`--despues`), que corre aunque el barrido falle o muera: lo que se tiene que
    hacer con las pasadas de disp_pasada de ESTE run, para que ninguna lo pierda. (a) Un vaciado que la funcion dejo
    'rechazada_vaciado' y el proceso murio antes de pasarlo a 'fallida' (GuardaPro.tras_aplicar): ahora. (b) Cada pasada
    APLICADA: lo de despues de aplicar, como la horaria (novedades; en OSMA, las fechas de vuelta), si no esta ya hecho
    (con novedades: si ya tiene fila en nov_pasada). Devuelve el codigo de salida. 🔴 Solo estados y recuentos."""
    env = os.environ if env is None else env
    nombre = PROVEEDORES[proveedor][0]
    if not str(run_id or '').isdigit():
        print(">>> TRAS LA LECTURA: sin GITHUB_RUN_ID no se sabe qué pasadas son de este run.", flush=True)
        return 1
    run = int(run_id)
    vaciadas = (sb.table('disp_pasada').select('id,motivo').eq('run_id', run).eq('proveedor', proveedor)
                .eq('estado', 'rechazada_vaciado').execute().data or [])
    g = GuardaPro(sb, proveedor)
    for p in vaciadas:
        g.tras_aplicar(p['id'], dict(p, estado='rechazada_vaciado'))
    aplicadas = (sb.table('disp_pasada').select('*').eq('run_id', run).eq('proveedor', proveedor)
                 .eq('estado', 'aplicada').execute().data or [])
    codigo, hechas, ya = 0, 0, 0
    for fila in aplicadas:
        if proveedor in CON_NOVEDADES and (sb.table('nov_pasada').select('pasada_id').eq('pasada_id', fila['id'])
                                           .limit(1).execute().data or []):
            ya += 1
            continue
        try:
            ok = (despues or DESPUES)[proveedor](sb, env, str(run), fila['id'], fila)
        except Exception as ex:  # noqa: BLE001 — 🔴 solo el tipo
            print(f">>> TRAS LA LECTURA de {nombre}: ha fallado ({type(ex).__name__}); la pasada sigue aplicada.",
                  flush=True)
            ok = False
        hechas += 1
        codigo = codigo or (0 if ok else 1)
    print(f">>> TRAS LA LECTURA de {nombre}: vaciados que pasan a «fallida» {len(vaciadas)} · aplicadas de este run "
          f"{len(aplicadas)} · lo de después hecho ahora {hechas} · ya hecho {ya} · {'bien' if codigo == 0 else 'en ROJO'}.",
          flush=True)
    return codigo


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
    if estado == 'fallida' and intento >= d.INTENTOS and pid:
        m = str(((sb.table('disp_pasada').select('motivo').eq('id', pid).limit(1).execute().data or [{}])[0]).get('motivo')
                 or '')
        if m.endswith(f'intento {d.INTENTOS} de {d.INTENTOS}'):   # la pagina anti-robots, por ultima vez
            return Lectura(pid=pid, motivo_entero=motivo_sin_intentos(sb, d.INTENTOS))
    return Lectura(pid=pid, despues=(lambda: _despues_tcg(sb, env, run_id, pid, None)) if estado == 'aplicada' else None)


def motivo_sin_intentos(sb, intentos):
    """(Quien dirige, 27-nov-2026) TCG ha enseñado su pagina anti-robots a las `intentos` maquinas de lectura: dicho
    claro, con la ultima lectura buena. No se reintenta mas ni mas deprisa."""
    ult = _ultima_aplicada(sb, 'TCG')
    t = _fecha(ult.get('terminada_en') or ult.get('creada_en')) if ult else None
    cola = f'la última lectura buena es del {_madrid(t)}' if t else 'y no hay ninguna lectura buena'
    return f'la web de TCG no deja entrar ahora a las máquinas de lectura ({intentos} intentos); {cola}'


def _leer_dbline(sb, env, run_id, intento, guarda):
    import escaner2_dbline_disponibilidad as d
    _c, pid, fila = d.aplicar(sb, run_id, d.hoy_madrid(), guarda=guarda)
    aplicada = (fila or {}).get('estado') == 'aplicada'
    return Lectura(pid=pid, despues=(lambda: _despues_dbline(sb, env, run_id, pid, fila)) if aplicada else None)


def _leer_ociostock(sb, env, run_id, intento, guarda):
    import requests
    import escaner2_ociostock_disponibilidad as d
    sesion = requests.Session()
    sesion.headers['User-Agent'] = d.AGENTE
    _c, pid, fila = d.aplicar(sb, sesion, env['OCIOSTOCK_FEED_URL'], run_id, guarda=guarda)
    aplicada = (fila or {}).get('estado') == 'aplicada'
    return Lectura(pid=pid, despues=(lambda: _despues_ociostock(sb, env, run_id, pid, fila)) if aplicada else None)


def _leer_osma(sb, env, run_id, intento, guarda, ahora=None):
    import requests
    import escaner2_osma_disponibilidad as d
    sesion = requests.Session()
    sesion.headers['User-Agent'] = d.AGENTE
    _c, pid, fila, contenido = d.aplicar(sb, sesion, env['OSMA_USER'], env['OSMA_PASS'], run_id, ahora, guarda=guarda)
    if (fila or {}).get('estado') == 'aplicada':
        # 🔑 La copia del Excel, YA (como la horaria, justo tras aplicar): la confirmacion de sabado a lunes la compara.
        try:
            d.guardar_copia(sb, contenido)
            print(f">>> Copia entera del Excel guardada en el almacén {d.BUCKET}: {d.RUTA_COPIA}", flush=True)
        except Exception as ex:  # noqa: BLE001 — la pasada sigue aplicada; sin copia, el fin de semana no confirmara
            print(f"OSMA_COPIA_NO_GUARDADA: la pasada {pid} está aplicada; la copia del Excel no se ha guardado "
                  f"({type(ex).__name__}).", flush=True)
        return Lectura(pid=pid, despues=lambda: _despues_osma(sb, env, run_id, pid, fila, sesion, ahora))
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


def nota_de(sb, foto, como, ahora, hace=None):
    """Lo que el barrido deja escrito de la lectura de la que sale (barrido.json y el «Resumen» del Excel): {'texto',
    'como', 'comprobada_en', 'contenido_de'}, en hora de Madrid. `como`: 'ahora' | 'confirmada' | 'reciente'."""
    f = (sb.table('disp_pasada').select('terminada_en,creada_en').eq('id', foto).limit(1).execute().data or [{}])[0]
    t = _fecha(f.get('terminada_en') or f.get('creada_en'))
    de = _madrid(t) if t else '—'
    if como == 'ahora':
        texto = f'leída ahora (la lectura del {de})'
    elif como == 'reciente':
        texto = f'leída hace {hace} min (la lectura del {de}); no se ha vuelto a leer'
    else:
        texto = f'confirmada hoy a las {_madrid(ahora)[-5:]}; el contenido es el de la lectura del {de}'
    return {'texto': texto, 'como': como, 'comprobada_en': ahora.isoformat(), 'contenido_de': t.isoformat() if t else None,
            'hace': hace}


def leer_en_directo(sb, proveedor, env=None, run_id='', intento=1, lectores=None, ahora=None):
    """La lectura del proveedor AHORA, para el barrido (ver la cabecera). Devuelve una `Lectura`: con `foto` se sigue
    (y `nota` dice de que lectura sale); sin ella, `motivo` es el de la pantalla (o `pared`, otro intento en otra
    maquina). NUNCA LANZA."""
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
        return Lectura(foto=reciente[0], nota=nota_de(sb, reciente[0], 'reciente', ahora, reciente[1]))
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
    if r.motivo_entero:
        r.foto, r.motivo = None, r.motivo_entero
        print(f">>> LECTURA EN DIRECTO de {nombre}: NO se sigue.", flush=True)
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
        if r.foto:
            r.nota = nota_de(sb, r.foto, 'ahora' if r.foto == r.pid else 'confirmada', datetime.now(timezone.utc))
    except Exception as ex:  # noqa: BLE001
        r.foto, por_que = None, f'no se ha podido comprobar la lectura ({type(ex).__name__})'
    if r.foto is None:
        r.motivo = motivo_de_fallo(sb, proveedor, por_que)
    print(f">>> LECTURA EN DIRECTO de {nombre}: {'sale la foto de esta lectura' if r.foto else 'NO se sigue'}.",
          flush=True)
    return r


ESPERA_MAX_S = 240   # 🔑 4 min: lo que puede esperar `abrir` a que acabe una pasada horaria en marcha (la mediana de la de
#                       TCG son 92 s; 23-33 min solo cuando lee muchos Funko antes de la foto: entonces, mejor fallar ya)
ESPERA_CADA_S = 15


def previo(sb, proveedor, ahora=None, dormir=None, espera_max_s=ESPERA_MAX_S):
    """LO QUE DECIDE EL JOB `abrir`, ANTES de que la lectura entre en el grupo de la horaria (y espere): ('reciente',
    foto, hace_min) si hay una lectura buena de hace menos de RECIENTE_MIN; ('leer', None, None) si no hay ninguna
    lectura del proveedor en marcha; si la hay (la horaria a medias), espera mirando la base hasta `espera_max_s` a que
    acabe (y vuelve a mirar), y si no acaba: ('fallida', motivo, None). `ahora` y `dormir`, los del banco."""
    import time
    ahora = ahora or (lambda: datetime.now(timezone.utc))
    dormir = dormir or time.sleep
    nombre = PROVEEDORES[proveedor][0]
    esperado = 0
    while True:
        t = ahora()
        rec = lectura_reciente(sb, proveedor, t)
        if rec:
            return 'reciente', rec[0], rec[1]
        leyendo = (sb.table('disp_pasada').select('id,creada_en').eq('proveedor', proveedor).eq('estado', 'leyendo')
                   .execute().data or [])
        vivas = [_fecha(p['creada_en']) for p in leyendo if _fecha(p.get('creada_en')) and t - _fecha(p['creada_en']) < TURNO]
        if not vivas:
            return 'leer', None, None
        if esperado >= espera_max_s:
            return ('fallida', f'{nombre} se está leyendo ahora (la lectura horaria, desde el {_madrid(min(vivas))}); vuelve '
                               f'a barrer en unos minutos', None)
        dormir(ESPERA_CADA_S)
        esperado += ESPERA_CADA_S


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


def _cerrar_fallida(sb, pasada, motivo, recuentos=None):
    sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo[:1000],
                                             'terminada_en': datetime.now(timezone.utc).isoformat()},
                                            **(recuentos or {}))).eq('id', pasada).execute()


def correr_barrido(sb, proveedor, fila, barrer, fallos, abortar, listo, env=None, argv=None, maximo_intentos=1,
                   lectores=None, dormir=None):
    """El `main` de los cuatro barridos. `fila`: la de escaner2_pasada que se abre; `barrer(pasada, foto, nota)` →
    (cierre, extra), con `foto` la pasada de disp_pasada de la lectura de ahora y `nota` lo que se deja escrito de ella;
    `fallos`, las excepciones cuyo texto es el motivo; `listo(cierre, extra)`, lo que se imprime al quedar lista.
      · `--abrir` (el job `abrir` del workflow, SIN el grupo de la horaria): abre la pasada, decide (`previo`) y deja en
        GITHUB_OUTPUT `pasada`, `camino` ('reciente' con `foto` y `hace`, o 'leer') para los jobs siguientes; si una
        lectura horaria a medias no acaba en ESPERA_MAX_S, la pasada queda 'fallida' con el motivo;
      · `--leer` (el paso de la lectura, SEPARABLE: se puede llevar a otro job u otra maquina sin tocar el barrido):
        retoma la pasada, lee al proveedor en directo y, si la lectura deja, NO barre: deja en GITHUB_OUTPUT `camino=foto`,
        `foto`, `como`, `comprobada` y `hace` para el paso del barrido; si no deja, la pasada queda 'fallida';
      · sin argumentos: retoma esa pasada (ESCANER2_PASADA; sin ella, abre una). Con FOTO (la que ha decidido `abrir` o
        el paso `--leer`, con FOTO_COMO, FOTO_HACE y FOTO_COMPROBADA), barre desde esa foto SIN leer; si no, lee al
        proveedor en directo y, si la lectura deja, barre (lo de los bancos y una corrida a mano). Si la
        web de TCG enseña su pagina anti-robots y queda intento, la pasada SIGUE 'descargando' y GITHUB_OUTPUT dice
        `pared=1`, `siguiente` y `pasada`: la retoma el job siguiente, en otra maquina, en el MISMO run.
    Lo de despues de aplicar NO va aqui: es el paso `--despues` de este modulo, que corre aunque el barrido falle."""
    env = os.environ if env is None else env
    argv = [] if argv is None else list(argv)
    nombre = PROVEEDORES[proveedor][0]
    if argv == ['--abrir']:
        sb.table('escaner2_pasada').insert(fila).execute()
        print(f">>> Pasada {fila['id']} abierta (descargando) · {nombre} · modo {fila.get('modo')}.", flush=True)
        try:
            espera = env.get('ESCANER2_ESPERA_MAX_S')
            camino, foto, hace = previo(sb, proveedor, dormir=dormir,
                                        espera_max_s=int(espera) if (espera or '').isdigit() else ESPERA_MAX_S)
        except Exception as ex:  # noqa: BLE001 — sin saberlo, se lee (la lectura vuelve a mirarlo todo)
            print(f">>> No se ha podido mirar antes de leer ({type(ex).__name__}): se lee.", flush=True)
            camino, foto, hace = 'leer', None, None
        if camino == 'fallida':
            _cerrar_fallida(sb, fila['id'], motivo_de_fallo(sb, proveedor, foto))
            abortar(f'pasada {fila["id"]} fallida: {nombre} se está leyendo ahora; el motivo está en escaner2_pasada')
        if not salida_github(env, pasada=fila['id'], camino=camino, foto=foto or '', hace='' if hace is None else hace):
            _cerrar_fallida(sb, fila['id'], 'sin GITHUB_OUTPUT no se puede pasar la pasada al job siguiente')
            abortar('sin GITHUB_OUTPUT no se puede pasar la pasada al job siguiente')
        print(f">>> {'Hay una lectura buena de hace ' + str(hace) + ' min: se barre desde ella, sin volver a leer' if camino == 'reciente' else 'Se lee a ' + nombre + ' en directo'}, en el job siguiente.",
              flush=True)
        return
    solo_leer = argv == ['--leer']
    if argv and not solo_leer:
        abortar('uso: <barrido>.py [--abrir | --leer]')
    try:
        intento = intento_de(env, maximo_intentos)
        pasada = abrir_o_retomar(sb, fila, env)
    except ValueError as ex:
        abortar(str(ex))
    print(f">>> Pasada {pasada} (descargando) · {nombre} · modo {fila.get('modo')} · intento {intento}.", flush=True)
    try:
        foto = (env.get('FOTO') or '').strip()
        if foto:
            # La foto que ya ha decidido otro paso o job de ESTE run (`abrir`, o la lectura con --leer): sin leer.
            como = (env.get('FOTO_COMO') or 'reciente').strip()
            hace = (env.get('FOTO_HACE') or '').strip() or None
            cuando = _fecha((env.get('FOTO_COMPROBADA') or '').strip() or None) or datetime.now(timezone.utc)
            print(f">>> Sale de la foto que ha decidido la lectura de este run ({como}): sin volver a leer.", flush=True)
            lectura = Lectura(foto=foto, nota=nota_de(sb, foto, como, cuando, hace or ('?' if como == 'reciente' else None)))
        else:
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
        if solo_leer:
            n = lectura.nota or {}
            if not salida_github(env, camino='foto', foto=lectura.foto, como=n.get('como') or '',
                                 comprobada=n.get('comprobada_en') or '', hace='' if n.get('hace') is None else n['hace']):
                raise FalloLectura('sin GITHUB_OUTPUT no se puede pasar la foto al paso del barrido')
            print(f">>> LECTURA LISTA: la foto de {nombre} sale de esta lectura ({n.get('como')}); la barre el paso siguiente.",
                  flush=True)
            return
        cierre, extra = barrer(pasada, lectura.foto, lectura.nota)
        # 🔒 El cierre DENTRO del try: si la base lo rechaza (el check del cuadre), la pasada queda 'fallida'.
        sb.table('escaner2_pasada').update(cierre).eq('id', pasada).execute()
    except Exception as ex:
        motivo = str(ex) if isinstance(ex, tuple(fallos) + (FalloLectura,)) else f'{type(ex).__name__}: {ex}'
        _cerrar_fallida(sb, pasada, motivo, getattr(ex, 'recuentos', {}))
        # Al log, solo el tipo: el motivo puede llevar precios o EAN y el repo es publico.
        abortar(f'pasada {pasada} fallida ({type(ex).__name__}); el motivo está en escaner2_pasada.motivo_fallo')
    listo(cierre, extra)


def principal(argv, env=None):
    """`python escaner2_pro_en_directo.py --despues <PROVEEDOR>`: el paso de despues de la lectura (tras_la_lectura)."""
    env = os.environ if env is None else env
    if len(argv) != 2 or argv[0] != '--despues' or argv[1] not in PROVEEDORES:
        print('ESCANER2_NO_EJECUTADO: uso: escaner2_pro_en_directo.py --despues TCG|DBLINE|OCIOSTOCK|OSMA')
        return 1
    if not (env.get('SUPABASE_URL') and env.get('SUPABASE_SERVICE_KEY')):
        print('ESCANER2_NO_EJECUTADO: sin llave de servicio')
        return 1
    from escaner2_base import cliente
    sb = cliente(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY'])
    return tras_la_lectura(sb, argv[1], env.get('GITHUB_RUN_ID') or '', env)


if __name__ == '__main__':
    import sys
    try:
        _codigo = principal(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as _ex:  # noqa: BLE001 — 🔴 nada de trazas
        print(f"ESCANER2_NO_EJECUTADO: error inesperado ({type(_ex).__name__})")
        _codigo = 1
    sys.exit(_codigo)
