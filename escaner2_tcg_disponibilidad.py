#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE TCG, EN SOMBRA, Y SU LECTOR DE TRAMOS (encargo T2, 13-oct-2026, piezas
(a) y (b) del plano del parte T1).

La lanza escaner2-tcg-disponibilidad.yml. El esqueleto es el de escaner2_dbline_disponibilidad.py (pasada → lectura →
disp_aplicar_pasada), con la web de TCG (escaner2_tcg_web.py), las reglas de escaner2_tcg.py y las del lector de
escaner2_tcg_tramos.py.

🔴 DEPENDE DE LA MIGRACION 20261013190000_disp_tcg_en_sombra.sql DE LA V2 (la fila TCG de disp_parametros y la tabla
   disp_tramo). Sin ella sale en ROJO al leer los parametros (no hay minimo) y la pasada queda 'fallida'.
🔴 (Encargo T4) Y DE 20261014150000_nov_novedades_tcg.sql (la fila TCG de nov_parametros y la carpeta tcg/novedades/ de
   nov_excel): sin ella, la seleccion de novedades falla (SIN_PARAMETROS_NOV) y el run sale en ROJO al final, con la
   pasada aplicada. Se aplica ANTES de fusionar esto.

QUE HACE, EN ORDEN:
  1. abre una pasada en `disp_pasada` (proveedor TCG, 'leyendo', con el id del run) y lee el minimo de filas y de
     disponibles (`disp_parametros`) y la huella de contenido de la ultima pasada APLICADA;
  2. entra en la web de TCG con TCG_USER/TCG_PASS y baja el Excel (lo mismo que el director viejo);
  3. lee los cocientes guardados (`disp_tramo`) y convierte el Excel con escaner2_tcg.convertir: si no se entiende →
     'fallida' con recuentos; filas (sin repetidas) por debajo del minimo, o disponibles por debajo del suyo →
     'rechazada_vaciado';
  3 bis. 🆕 (encargo T4, 14-oct-2026) LA WEB DE FUNKO, ANTES DE LA FOTO, CADA HORA (`funko_antes_de_la_foto`), con la
     misma sesion: el listado filtrado a la marca Funko y Disponible/Oferta/Saldo (8 paginas, ~40 s: sonda T4) y las
     fichas de Funko que tocan YA (las nunca leidas, las que el listado da por desajustadas y las que tienen otro Precio
     en el Excel que al leerlas: escaner2_tcg_tramos.pendientes_antes_de_la_foto, hasta FICHAS_FUNKO_MAX). Despues el
     Excel se vuelve a convertir con los cocientes recien leidos y con la web ENCIMA en lo disponible de Funko
     (escaner2_tcg, regla 9): lo que la web da disponible lo es; lo que el Excel da disponible y la web no (con el
     listado entero), no. Asi una novedad la detecta lo primero que la vea, la web o el Excel, y sale una sola vez y ya
     con el precio de su tramo. 🔴 Al primer bloqueo, captcha, HTML o listado que no se entienda (o un listado con menos
     de la mitad de lo que el Excel da disponible): para, lo leido queda guardado, la pasada 'fallida' (la foto se queda
     como estaba: ni Excel solo, que desharia lo que vio la web), Telegram y ROJO;
  4. «AL DIA» POR CONTENIDO: si la huella de lo que se subiria es la de la ultima pasada aplicada → 'rechazada' «al
     día» y VERDE (TCG_AL_DIA);
  5. sube las filas a `disp_lectura` en lotes de 500, deja los recuentos y llama a `disp_aplicar_pasada`; lo que vale es
     lo que relee de la base;
  5 bis. 🆕 (encargo T4) LAS NOVEDADES DE FUNKO, con la pasada APLICADA (no «al día»), como paso aparte y ANTES del lector
     de tramos (para no esperar a sus fichas): `escaner2_novedades.novedades_tras_la_pasada(proveedor='TCG')`, como
     DBLine y OcioStock: la seleccion en la base (nov_seleccionar_pasada con nov_parametros de TCG: marca Funko, el precio
     de compra de la foto —el del tramo mas barato— contra el que se vio la ultima vez, sin preventas) y su valoracion
     (Keepa con KEEPA_API_KEY; el Excel «TCG · Funko» si hay un COMPRAR y el Telegram «Novedades TCG Funko»). Con el
     interruptor apagado (nov_parametros.valorar de TCG: asi nace), cero llamadas a Keepa. Si falla, o el vigia de la
     marca salta, la pasada sigue aplicada y el run sale en ROJO al final;
  6. EL LECTOR DE TRAMOS, con la misma sesion (solo si la pasada se ha aplicado o esta «al día»: con un Excel que no
     se entiende, no se sabe que hay disponible):
       a) el LISTADO FILTRADO (16 paginas): de lunes a viernes en la pasada de las 09 (Madrid), o si se pide
          (LISTADO=si). Las tarjetas cuyo «desde» o suelto ya no cuadran con lo guardado quedan marcadas
          (`disp_tramo.pide_relectura`);
       b) las FICHAS que tocan (escaner2_tcg_tramos.pendientes): las disponibles nunca leidas, las marcadas y las
          leidas hace mas de 7 dias, hasta FICHAS_MAX por corrida (150 por defecto; la primera lectura, a mano, con
          mas). Cada ficha leida se guarda al momento en `disp_tramo` (suelto, tramos, el mas barato exacto, sus uds, el
          Precio del Excel de ese momento, el cociente y la fecha).
     El cociente nuevo lo usa la PASADA SIGUIENTE (la foto va primero: si la web se pone dificil, la foto ya esta).
  🔴 AL PRIMER BLOQUEO (403/429/503, captcha, fallo de red) O HTML QUE NO SE ENTIENDA: para de pedir, lo leido ya esta
     guardado, ni un cociente inventado, aviso por Telegram (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID, como el resto del escaner)
     y ROJO al final. Si para en el login o en el Excel, la pasada queda 'fallida' y el mismo aviso.

🔴 REPO PUBLICO: SOLO estados y recuentos al registro. NUNCA la respuesta de la web, una URL, el usuario, la clave,
   precios, nombres, EAN ni el texto de un error (al registro, su tipo; el detalle, limpio, a `disp_pasada.motivo`). Lo
   comprueba test_escaner2_tcg_disponibilidad.py ejecutando el programa con una web y una base de mentira.
🔑 EN SOMBRA: TCG NO tiene fila en `disp_fuente` y este programa no la lee ni la toca: Reponer, el Trackeador y la lista
   de precios siguen con la memoria del escaner viejo (director-tcg.yml, que sigue igual). El interruptor es otro
   encargo, con Fernando delante.
🔒 SOLO TOCA `disp_pasada`, `disp_lectura`, la funcion `disp_aplicar_pasada` y `disp_tramo`; LEE `disp_parametros`. Ni
   escaner_memoria, ni reglas_director, ni sondeo_keepa (Fernando, 13-oct: TCG no alimenta «Amazon sin ficha»). (Encargo
   T4) Las novedades van por escaner2_novedades.py (nov_*, Keepa, el Excel y el Telegram), con su registro DISCRETO
   (`imprimir_discreto`: ni EAN, ni ASIN, ni el texto de un error, que queda en nov_pasada.valoracion_motivo).
🔒 SIN LOS SECRETOS (TCG_USER/TCG_PASS y la base), NO SE CORRE: aborta antes de abrir ninguna pasada.

Uso:  python escaner2_tcg_disponibilidad.py            (la pasada; FICHAS_MAX y LISTADO por el entorno)
      python escaner2_tcg_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

PROVEEDOR = 'TCG'
LOTE = 500
PAGINA = 1000  # PostgREST devuelve como mucho 1.000 filas por consulta
FICHAS_MAX = 150
# (Encargo T4) La marca de las novedades (Fernando, 13-oct: «el escnear automatico solo de Funko»), la categoria de la web
# donde vive (sonda T4: las 2.122 de la marca Funko de la web estan en «merchandising», como las 2.122 de la foto), cuantas
# fichas suyas se leen como mucho antes de la foto, y el listado mas corto que se cree (frente a lo que el Excel da disponible).
MARCA_NOVEDADES = 'Funko'
CATEGORIA_FUNKO = 'distribucion-merchandising'
FICHAS_FUNKO_MAX = 300
WEB_MINIMO = 0.5
SIN_FICHA_SEGUIDAS = 5  # tantas fichas seguidas sin producto (404 o a otra pagina) ya no son casualidad: se para
HORA_LISTADO = 9  # Madrid, de lunes a viernes: la pasada de las 09:00
_RE_HEX = re.compile(r'[0-9a-fA-F]{24,}')
_RE_URL = re.compile(r'https?://\S+')


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO. `motivo` es SIEMPRE un texto escrito por este programa."""
    print(f"TCG_NO_EJECUTADA: {motivo}")
    sys.exit(1)


class Rechazo(Exception):
    """La pasada no se aplica: `estado` y un `motivo` escrito por este programa (estados y recuentos)."""

    def __init__(self, estado, motivo, bloqueo=False):
        super().__init__(motivo)
        self.estado, self.motivo, self.bloqueo = estado, motivo, bloqueo


class AlDia(Rechazo):
    def __init__(self, pasada_aplicada):
        super().__init__('rechazada', f'al día: el contenido es el mismo que el de la pasada aplicada {pasada_aplicada}; '
                                      f'nada nuevo')
        self.pasada_aplicada = pasada_aplicada


def _ahora():
    return datetime.now(timezone.utc)


def limpio(texto, secretos=()):
    """El texto de un error sin URLs, sin los secretos y sin cadenas hexadecimales largas."""
    t = str(texto)
    for s in secretos:
        if s:
            t = t.replace(s, '<secreto>')
    return _RE_HEX.sub('<hex>', _RE_URL.sub('<url>', t))


def _num(d):
    """Un Decimal para la base (texto: sin perder decimales); None tal cual."""
    return None if d is None else format(d, 'f')


def _cerrar(sb, pasada, estado, motivo, extra=None):
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    datos = dict(extra or {}, estado=estado, motivo=motivo[:1000], terminada_en=_ahora().isoformat())
    sb.table('disp_pasada').update(datos).eq('id', pasada).eq('estado', 'leyendo').execute()


def leer_tramos(sb):
    """{producto_prov: fila} de disp_tramo de TCG, de PAGINA en PAGINA y en orden fijo."""
    filas, desde = [], 0
    while True:
        lote = (sb.table('disp_tramo').select('*').eq('proveedor', PROVEEDOR).order('producto_prov')
                  .range(desde, desde + PAGINA - 1).execute().data or [])
        filas.extend(lote)
        if len(lote) < PAGINA:
            return {f['producto_prov']: f for f in filas}
        desde += PAGINA


def cocientes(guardados):
    """Lo que la foto necesita de cada tramo leido: {producto_prov: {'cociente', 'uds', 'leido_en'}}."""
    return {k: {'cociente': Decimal(str(g['cociente'])), 'uds': g.get('uds_mas_barato'), 'leido_en': g.get('leido_en')}
            for k, g in guardados.items() if g.get('cociente') is not None and g.get('leido_en')}


def avisar(texto, env=None, post=None):
    """El Telegram de una parada, como el del resto del escaner (escaner2_novedades.enviar_telegram). NUNCA LANZA y no
    imprime nada suyo: el registro solo dice si se ha mandado."""
    try:
        import escaner2_novedades as nv
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            ok = nv.enviar_telegram(texto, env=env, post=post, imprimir=lambda *a, **k: None)
    except Exception:  # noqa: BLE001
        ok = False
    print(f">>> Telegram de la parada: {'enviado' if ok else 'NO enviado (sin claves o Telegram falla)'}.", flush=True)
    return ok


# ── La foto ───────────────────────────────────────────────────────────────────────────────
def _minimos(c, minimo, min_disp):
    n = c['n_crudo'] - c['n_duplicados']
    if n < minimo:
        raise Rechazo('rechazada_vaciado', f'vaciado: {n} filas distintas en el Excel, por debajo del mínimo {minimo}')
    if c['n_disponibles'] < min_disp:
        raise Rechazo('rechazada_vaciado', f"vaciado: {c['n_disponibles']} disponibles, por debajo del mínimo {min_disp}")


def pasada(sb, web, run_id, usuario, clave, ahora, fichas_funko=FICHAS_FUNKO_MAX):
    """La pasada de la foto. Devuelve (codigo, estado, catalogo, guardados, pid): `estado` 'aplicada', 'al_dia' u otro;
    `catalogo` y `guardados` para el lector de tramos (None si la pasada no ha llegado a entender el Excel)."""
    import escaner2_tcg as tcg
    import escaner2_tcg_tramos as tr
    from escaner2_tcg_web import Bloqueo

    abrir = {'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(run_id) if run_id.isdigit() else None}
    pid = sb.table('disp_pasada').insert(abrir).execute().data[0]['id']
    print(f">>> Pasada de disponibilidad de TCG {pid} abierta (leyendo).", flush=True)
    rec = None
    catalogo = guardados = None
    try:
        par = (sb.table('disp_parametros').select('crudo_minimo, disponibles_minimo').eq('proveedor', PROVEEDOR)
                 .execute().data or [{}])
        minimo, min_disp = par[0].get('crudo_minimo'), par[0].get('disponibles_minimo')
        for m in (minimo, min_disp):
            if not isinstance(m, int) or isinstance(m, bool) or m <= 0:
                raise Rechazo('fallida', 'sin mínimos: disp_parametros no da crudo_minimo y disponibles_minimo válidos '
                                         'para TCG; no se baja nada')
        ult = (sb.table('disp_pasada').select('id, huella_contenido').eq('proveedor', PROVEEDOR).eq('estado', 'aplicada')
                 .order('creada_en', desc=True).limit(1).execute().data or [{}])

        try:
            web.entrar(usuario, clave)
            contenido = web.excel()
        except Bloqueo as ex:
            raise Rechazo('fallida', f'la web de TCG no deja: {ex}', bloqueo=True) from None
        md5, n_bytes = tcg.huella_fichero(contenido)
        sb.table('disp_pasada').update({'fichero_md5': md5, 'fichero_bytes': n_bytes}).eq('id', pid).execute()
        print(f">>> Excel bajado: {n_bytes} bytes.", flush=True)

        guardados = leer_tramos(sb)
        try:
            _l0, c0, catalogo0 = tcg.convertir(contenido, cocientes(guardados), ahora)
        except tcg.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        _minimos(c0, minimo, min_disp)  # un Excel vaciado no lleva a pedir nada a la web
        # 3 bis · (encargo T4) la web de Funko, ANTES de la foto.
        try:
            vista, rf = funko_antes_de_la_foto(sb, web, catalogo0, guardados, run_id, fichas_funko)
        except (Bloqueo, tr.FichaNoEntendida, tr.ListadoNoEntendido) as ex:
            raise Rechazo('fallida', f'la web de TCG no deja leer los {MARCA_NOVEDADES} antes de la foto ({ex})',
                          bloqueo=True) from None
        print(f">>> WEB {MARCA_NOVEDADES.upper()}: listado {rf['paginas']} páginas, {rf['tarjetas']} tarjetas (la web dice "
              f"{rf['total_web']}{', entero' if vista['completo'] else ', A MEDIAS: no se quita nada'}), {rf['desajustes']} ya "
              f"no cuadran · fichas antes de la foto: pendientes {rf['pendientes']}, pedidas {rf['pedidas']} (máximo "
              f"{fichas_funko}), leídas bien {rf['ok']}, sin ficha {rf['sin_ficha']}, de otro EAN {rf['otro_ean']}, sin precio "
              f"en el Excel {rf['sin_precio_excel']}", flush=True)
        guardados = leer_tramos(sb)
        try:
            lectura, c, catalogo_leido = tcg.convertir(contenido, cocientes(guardados), ahora, web=vista)
        except tcg.LecturaInvalida as ex:
            raise Rechazo('fallida', str(ex)) from None
        n = c['n_crudo'] - c['n_duplicados']
        rec = {'n_declarado': n, 'n_crudo': c['n_crudo'], 'n_declarado_precios': n, 'n_precios': n,
               'n_declarado_disponibilidades': n, 'n_disponibilidades': n, 'n_sin_gtin': c['n_sin_gtin'],
               'n_duplicados': c['n_duplicados'], 'n_duplicados_precios': 0, 'n_duplicados_disponibilidades': 0,
               'huella_contenido': c['huella_contenido']}
        print(f">>> Leídas {c['n_leidas']} (disponibles {c['n_disponibles']}, agotados {c['n_agotados']}) · repetidas "
              f"{c['n_duplicados']} · sin EAN {c['n_sin_gtin']} · sin precio {c['n_sin_dato_precio']} · en reposición "
              f"{c['n_reposicion']} · preventa {c['n_preventa']} · oferta {c['n_oferta']} · saldo {c['n_saldo']} · "
              f"disponible sin stock {c['n_disponible_sin_stock']} · cajas de 6 {c['n_cajas']} (disponibles "
              f"{c['n_cajas_disponibles']}) · EAN de forma rara {c['n_ean_forma_rara']} · sin URL de ficha {c['n_sin_url']} "
              f"(disponibles {c['n_disponibles_sin_url']}) · con tramo {c['n_con_tramo']} (disponibles "
              f"{c['n_disponibles_con_tramo']}; disponibles sin tramo leído {c['n_disponibles_sin_tramo']}; tramo de hace "
              f"más de 7 días {c['n_tramo_viejo']}) · con la web de {MARCA_NOVEDADES}: a disponible {c['n_web_a_disponible']}, "
              f"a agotado {c['n_web_a_agotado']}, en la web y aún no en el Excel {c['n_web_sin_excel']}", flush=True)
        _minimos(c, minimo, min_disp)
        catalogo = catalogo_leido
        if ult[0].get('huella_contenido') == c['huella_contenido']:
            raise AlDia(ult[0].get('id'))
        print(">>> Contenido nuevo (la huella no es la de la última pasada aplicada): se sube.", flush=True)

        sb.table('disp_pasada').update(rec).eq('id', pid).execute()
        for i in range(0, len(lectura), LOTE):
            sb.table('disp_lectura').insert([dict(f, pasada_id=pid) for f in lectura[i:i + LOTE]]).execute()
        sb.table('disp_pasada').update({
            'n_leidas': c['n_leidas'], 'n_disponibles': c['n_disponibles'], 'n_agotados': c['n_agotados'],
            'n_sin_dato_disponibilidad': 0, 'n_sin_dato_precio': c['n_sin_dato_precio'],
        }).eq('id', pid).execute()
        sb.rpc('disp_aplicar_pasada', {'p_pasada': pid}).execute()
    except Rechazo as ex:
        _cerrar(sb, pid, ex.estado, ex.motivo, rec)
        if isinstance(ex, AlDia):
            print(f"TCG_AL_DIA: el contenido es el de la pasada aplicada {ex.pasada_aplicada}; nada nuevo.", flush=True)
            return 0, 'al_dia', catalogo, guardados, pid
        print(f"TCG_NO_APLICADA: pasada {pid} {ex.estado}: {ex.motivo}", flush=True)
        if ex.bloqueo:
            avisar(f'⚠️ Escáner 2 · TCG: la pasada de la foto se ha parado porque la web de TCG no deja ({ex.motivo}). '
                   f'Nada inventado; el escáner viejo sigue como siempre.')
        return 1, ex.estado, None, None, pid
    except Exception as ex:
        # 🔴 REPO PÚBLICO: el texto de un error puede llevar una URL, la respuesta de la web o una fila de la base.
        motivo_log = f'error inesperado ({type(ex).__name__}); el detalle queda en disp_pasada.motivo'
        try:
            _cerrar(sb, pid, 'fallida', limpio(f'{type(ex).__name__}: {ex}', (usuario, clave)), rec)
        except Exception as ex2:
            motivo_log += f'; tampoco se ha podido cerrar la pasada ({type(ex2).__name__})'
        print(f"TCG_NO_APLICADA: pasada {pid} fallida: {motivo_log}", flush=True)
        return 1, 'fallida', None, None, pid

    fila = sb.table('disp_pasada').select('*').eq('id', pid).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila.get(k)}' for k in (
        'estado', 'primera', 'caida_aceptada', 'n_crudo', 'n_duplicados', 'n_leidas', 'n_disponibles', 'n_agotados',
        'n_sin_dato_precio', 'n_entran', 'n_vuelven', 'n_salen', 'n_a_disponible', 'n_a_agotado', 'n_cambio_precio',
        'n_ausentes', 'n_en_catalogo', 'n_disponibles_estado')), flush=True)
    if fila.get('estado') != 'aplicada':
        print(f"TCG_NO_APLICADA: pasada {pid} {fila.get('estado')}: {fila.get('motivo')}", flush=True)
        return 1, fila.get('estado'), None, None, pid
    print(f">>> PASADA APLICADA: {fila.get('n_en_catalogo')} productos de TCG en el catálogo, "
          f"{fila.get('n_disponibles_estado')} disponibles.", flush=True)
    codigo = 0
    if fila.get('caida_aceptada'):
        print(f"CAIDA_ACEPTADA: la pasada {pid} se ha aplicado como NUEVA REFERENCIA tras varios rechazos estables por "
              f"el freno del 90 %: hay que mirar si TCG ha caído de verdad.", flush=True)
        codigo = 1
    return codigo, 'aplicada', catalogo, guardados, pid


def novedades(sb, pid, run_id):
    """(Encargo T4) Las novedades de Funko de la pasada aplicada `pid` (como DBLine y OcioStock). NUNCA LANZA. Devuelve
    True si todo fue bien (sin el vigia de la marca). 🔴 Repo publico: el registro, discreto (solo estados y recuentos)."""
    try:
        import escaner2_novedades as nv
        ok, seleccion = nv.novedades_tras_la_pasada(sb, pid, PROVEEDOR, keepa_llave=os.environ.get('KEEPA_API_KEY'),
                                                    imprimir=nv.imprimir_discreto, run_id=run_id or None)
    except Exception as ex:
        print(f"TCG_NOVEDADES_NO_HECHAS: la pasada {pid} sigue aplicada; las novedades han fallado antes de poder "
              f"apuntarse ({type(ex).__name__})", flush=True)
        return False
    marca_parecida = (seleccion or {}).get('marca_parecida') or 0
    if marca_parecida:
        print(f"MARCA_PARECIDA: {marca_parecida} producto(s) de TCG tienen una marca que se parece a {MARCA_NOVEDADES} y no "
              f"lo es: si TCG cambia la grafía, sus novedades se quedarían a cero en silencio (nov_pasada.n_marca_parecida "
              f"de la pasada {pid}).", flush=True)
    if not ok:
        print(f"TCG_NOVEDADES_EN_ROJO: la pasada {pid} sigue aplicada; las novedades no han salido bien (el detalle, en "
              f"nov_pasada de esa pasada).", flush=True)
    return ok and not marca_parecida


# ── El lector de tramos ───────────────────────────────────────────────────────────────────
def toca_listado(listado, ahora_madrid):
    if listado == 'si':
        return True
    if listado == 'no':
        return False
    return ahora_madrid.weekday() < 5 and ahora_madrid.hour == HORA_LISTADO


def _guardar(sb, fila):
    sb.table('disp_tramo').upsert(fila, on_conflict='proveedor,producto_prov').execute()


def _marcar_desajustes(sb, guardados, malas, reloj):
    """Las fichas que el listado da por desajustadas quedan marcadas (`pide_relectura`) en la base y en `guardados`."""
    marca = reloj().isoformat()
    for i in range(0, len(malas), 200):
        (sb.table('disp_tramo').update({'pide_relectura': marca}).eq('proveedor', PROVEEDOR)
           .in_('producto_prov', malas[i:i + 200]).execute())
    for k in malas:
        guardados[k] = dict(guardados[k], pide_relectura=marca)


def _leer_fichas(sb, web, cola, run, r, reloj):
    """Lee las fichas de `cola`, una a una, y guarda cada una al momento en disp_tramo; deja los recuentos en `r`.
    LANZA al primer bloqueo (Bloqueo, tambien con SIN_FICHA_SEGUIDAS sin producto) o ficha que no se entienda
    (FichaNoEntendida): lo leido ya esta guardado. NUNCA deja un cociente que no salga de una ficha leida entera."""
    import escaner2_tcg_tramos as tr
    from escaner2_tcg_web import Bloqueo

    seguidas = 0
    for e in cola:
        html = web.ficha(e['url'])
        r['pedidas'] += 1
        base = {'proveedor': PROVEEDOR, 'producto_prov': e['producto_prov'], 'url': e['url'],
                'intento_en': reloj().isoformat(), 'run_id': run}
        try:
            ficha = None if html is None else tr.leer_ficha(html)
        except tr.FichaNoEntendida:
            _guardar(sb, dict(base, intento_resultado='no_entendida'))
            raise
        except tr.FichaNoEsProducto:
            ficha = None
        if ficha is None:
            _guardar(sb, dict(base, intento_resultado='sin_ficha'))
            r['sin_ficha'] += 1
            seguidas += 1
            if seguidas >= SIN_FICHA_SEGUIDAS:
                raise Bloqueo(f'{seguidas} fichas seguidas sin producto (404 o a otra página): algo ha cambiado en la web')
            continue
        seguidas = 0
        if not tr.ean_casa(ficha['eans'], e['producto_prov'], e['ean_core'], e['es_caja']):
            _guardar(sb, dict(base, intento_resultado='otro_ean'))
            r['otro_ean'] += 1
            continue
        t = tr.tramo_de_ficha(ficha, e['precio_excel'])
        if t['cociente'] is None:
            _guardar(sb, dict(base, intento_resultado='sin_precio_excel'))
            r['sin_precio_excel'] += 1
            continue
        _guardar(sb, dict(base, intento_resultado='ok', leido_en=base['intento_en'], pide_relectura=None,
                          suelto_web=_num(t['suelto_web']), suelto_exacto=_num(t['suelto_exacto']),
                          rel=_num(t['rel']), tramos=t['tramos'], mas_barato=_num(t['mas_barato']),
                          uds_mas_barato=t['uds_mas_barato'], precio_excel=_num(t['precio_excel']),
                          cociente=_num(t['cociente'])))
        r['ok'] += 1
        r['con_tramo'] += t['uds_mas_barato'] > 1


def funko_antes_de_la_foto(sb, web, catalogo, guardados, run_id, fichas_max, reloj=_ahora):
    """(Encargo T4, paso 3 bis) El listado de la marca de las novedades y sus fichas que tocan YA. Devuelve (web, r):
    `web` es lo que escaner2_tcg.convertir se pone encima ({'marca', 'disponibles': {url: estado}, 'completo'}) y `r`, los
    recuentos. LANZA (Bloqueo, FichaNoEntendida, ListadoNoEntendido) al primer bloqueo o forma que no se entienda, o si
    el listado trae menos de WEB_MINIMO de lo que el Excel da disponible de la marca (no se cree). `guardados` queda con
    las marcas de relectura puestas."""
    import escaner2_tcg as tcg
    import escaner2_tcg_tramos as tr

    r = {'paginas': 0, 'tarjetas': 0, 'total_web': None, 'desajustes': 0, 'pendientes': 0, 'pedidas': 0, 'ok': 0,
         'con_tramo': 0, 'sin_ficha': 0, 'otro_ean': 0, 'sin_precio_excel': 0}
    run = int(run_id) if run_id.isdigit() else None
    trozos, r['paginas'] = web.listado(CATEGORIA_FUNKO, marca=MARCA_NOVEDADES)
    cards, vistas = [], set()
    for trozo in trozos:
        for t in tr.tarjetas(trozo):
            if t['url'] and t['url'] not in vistas:
                vistas.add(t['url'])
                cards.append(t)
    r['tarjetas'], r['total_web'] = len(cards), web.total_listado
    del_excel = sum(1 for e in catalogo if e.get('marca') == MARCA_NOVEDADES and e['disponible'])
    if r['total_web'] is None:
        raise tr.ListadoNoEntendido('el listado no dice cuántos productos tiene (products_num)')
    if len(cards) < WEB_MINIMO * del_excel:
        raise tr.ListadoNoEntendido(f'el listado de {MARCA_NOVEDADES} trae {len(cards)} tarjetas y el Excel da {del_excel} '
                                    f'disponibles: no se pone encima de la foto')
    vista = {'marca': MARCA_NOVEDADES, 'completo': len(cards) >= r['total_web'],
             'disponibles': {t['url']: (t['estado'] if t['estado'] in tr.ESTADOS_BUENOS else 'Disponible') for t in cards}}
    por_url = {g['url']: g for g in guardados.values() if g.get('cociente') is not None and g.get('url')}
    malas = sorted(tr.desajustes(cards, por_url))
    r['desajustes'] = len(malas)
    _marcar_desajustes(sb, guardados, malas, reloj)
    con_web = [dict(e, disponible=tcg.veredicto_web(e['disponible'], e['url'], e.get('marca'), vista)[0]) for e in catalogo]
    cola, r['pendientes'] = tr.pendientes_antes_de_la_foto(con_web, guardados, set(malas), reloj(), fichas_max,
                                                           MARCA_NOVEDADES)
    _leer_fichas(sb, web, cola, run, r, reloj)
    return vista, r


def leer_tramos_web(sb, web, catalogo, guardados, run_id, fichas_max, hacer_listado, reloj=_ahora):
    """El lector (paso 6). Devuelve un dict de recuentos con 'parada' (None si no ha parado). NUNCA deja un cociente
    que no salga de una ficha leida entera."""
    import escaner2_tcg_tramos as tr
    from escaner2_tcg_web import CATEGORIAS, Bloqueo

    r = {'listado_paginas': 0, 'tarjetas': 0, 'desajustes': 0, 'pendientes': 0, 'pedidas': 0, 'ok': 0,
         'con_tramo': 0, 'sin_ficha': 0, 'otro_ean': 0, 'sin_precio_excel': 0, 'parada': None, 'segundos': 0}
    t0 = time.monotonic()
    run = int(run_id) if run_id.isdigit() else None
    try:
        if hacer_listado:
            cards = []
            for cat in CATEGORIAS:
                trozos, paginas = web.listado(cat)
                r['listado_paginas'] += paginas
                for t in trozos:
                    cards.extend(tr.tarjetas(t))
            r['tarjetas'] = len(cards)
            por_url = {g['url']: g for g in guardados.values() if g.get('cociente') is not None}
            malas = sorted(tr.desajustes(cards, por_url))
            r['desajustes'] = len(malas)
            _marcar_desajustes(sb, guardados, malas, reloj)

        cola, r['pendientes'] = tr.pendientes(catalogo, guardados, reloj(), fichas_max)
        _leer_fichas(sb, web, cola, run, r, reloj)
    except (Bloqueo, tr.FichaNoEntendida, tr.ListadoNoEntendido) as ex:
        r['parada'] = str(ex)
    r['segundos'] = round(time.monotonic() - t0, 1)
    return r


def principal(argv, env=None, sb=None, sesion=None, dormir=None):
    env = os.environ if env is None else env
    rescate = argv == ['--rescate']
    if argv not in ([], ['--rescate']):
        abortar('uso: escaner2_tcg_disponibilidad.py [--rescate]')
    if not rescate and not (env.get('TCG_USER') and env.get('TCG_PASS')):
        abortar('faltan TCG_USER/TCG_PASS (secretos del repo); no se abre ninguna pasada')
    if not (env.get('SUPABASE_URL') and env.get('SUPABASE_SERVICE_KEY')):
        abortar('faltan SUPABASE_URL/SUPABASE_SERVICE_KEY; no se abre ninguna pasada')
    fichas_txt = (env.get('FICHAS_MAX') or str(FICHAS_MAX)).strip()
    listado = (env.get('LISTADO') or 'auto').strip()
    if not fichas_txt.isdigit() or listado not in ('auto', 'si', 'no'):
        abortar('FICHAS_MAX tiene que ser un número entero y LISTADO auto, si o no')
    run_id = env.get('GITHUB_RUN_ID') or ''
    if sb is None:
        from supabase import create_client
        sb = create_client(env['SUPABASE_URL'], env['SUPABASE_SERVICE_KEY'])
    if rescate:
        try:
            rescatar(sb, run_id)
        except Exception as ex:
            abortar(f'el rescate ha fallado ({type(ex).__name__})')
        return 0

    from escaner2_tcg_web import Web, sesion_de_verdad
    web = Web(sesion if sesion is not None else sesion_de_verdad(), **({'dormir': dormir} if dormir else {}))
    ahora = _ahora()
    codigo, estado, catalogo, guardados, pid = pasada(sb, web, run_id, env['TCG_USER'], env['TCG_PASS'], ahora)
    if estado not in ('aplicada', 'al_dia') or catalogo is None:
        print(">>> TRAMOS: no se leen (la pasada no ha entendido el Excel o la web no deja).", flush=True)
        return codigo or 1
    # 5 bis · (encargo T4) las novedades de Funko, con la pasada aplicada y antes del lector (no esperan a sus fichas).
    if estado == 'aplicada' and not novedades(sb, pid, run_id):
        codigo = 1

    hacer_listado = toca_listado(listado, ahora.astimezone(ZoneInfo('Europe/Madrid')))
    try:
        r = leer_tramos_web(sb, web, catalogo, guardados, run_id, int(fichas_txt), hacer_listado)
    except Exception as ex:  # noqa: BLE001 — 🔴 solo el tipo: el texto puede llevar una URL o una fila
        print(f"TCG_TRAMOS_NO_HECHOS: la foto sigue como ha quedado; el lector ha fallado ({type(ex).__name__}).",
              flush=True)
        return 1
    print(f">>> TRAMOS: listado {'sí' if hacer_listado else 'no'} ({r['listado_paginas']} páginas, {r['tarjetas']} "
          f"tarjetas, {r['desajustes']} ya no cuadran) · fichas pendientes {r['pendientes']}, pedidas {r['pedidas']} "
          f"(máximo {fichas_txt}) · leídas bien {r['ok']} (con tramo de más de 1 ud {r['con_tramo']}) · sin ficha "
          f"{r['sin_ficha']} · de otro EAN {r['otro_ean']} · sin precio en el Excel {r['sin_precio_excel']} · "
          f"{r['segundos']} s · peticiones a la web en la corrida {web.peticiones}", flush=True)
    if r['parada']:
        print(f"TCG_TRAMOS_PARADO: {r['parada']}. Lo leído queda guardado; ningún cociente inventado.", flush=True)
        avisar(f"⚠️ Escáner 2 · TCG: el lector de tramos se ha parado ({r['parada']}). Fichas leídas bien en esta "
               f"corrida: {r['ok']} (guardadas). Ningún cociente inventado; la foto de TCG sigue con lo que tenía.")
        return 1
    return codigo


def rescatar(sb, run_id):
    """Si el run muere a medias, SOLO la pasada de ESTE run, de TCG, y solo si sigue leyendo, queda 'fallida'."""
    if not run_id.isdigit():
        abortar('sin GITHUB_RUN_ID: no se sabe qué pasada es de este run')
    res = (sb.table('disp_pasada').select('id').eq('run_id', int(run_id)).eq('proveedor', PROVEEDOR)
             .eq('estado', 'leyendo').execute())
    for f in res.data or []:
        _cerrar(sb, f['id'], 'fallida', f'el run {run_id} terminó sin cerrar la pasada (tope de tiempo, cancelación o '
                                         f'caída); mira su log en Actions')
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de TCG de este run pasan de 'leyendo' a 'fallida'.")


if __name__ == '__main__':
    try:
        codigo = principal(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as ex:  # noqa: BLE001 — 🔴 nada de trazas: pueden llevar la respuesta de la web
        print(f"TCG_NO_EJECUTADA: error inesperado ({type(ex).__name__})")
        sys.exit(1)
    sys.exit(codigo)
