#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · LA PASADA DE DISPONIBILIDAD DE HEO (encargo E, tramo 3, pieza 1, 29-sep-2026).

La lanza escaner2-heo-disponibilidad.yml. HOY A MANO: el reloj (cron-job.org, cada hora) lo
encienden Fernando y Cowork cuando esto este fusionado y la migracion de la v2 aplicada.

QUE HACE, EN ORDEN:
  1. abre una pasada en `disp_pasada` (proveedor HEO, estado 'leyendo', con el id del run), y lee la
     tolerancia de la descarga en `disp_parametros` (HEO: 10);
  2. baja el catalogo con `descargar_catalogo_heo(con_chase=True)`, la MISMA funcion que el barrido y
     el director (copia literal en escaner2_heredado_descarga.py), y saca de su log, por endpoint, lo
     que HEO declara y lo que llego, y lo que tiro sin GTIN. 🔴 SI UNO DE LOS TRES ENDPOINTS (productos,
     precios, disponibilidades) NO LLEGO ENTERO (mas diferencia que la tolerancia), la pasada se
     cierra 'fallida' SIN llamar a la base: la descarga corta en silencio, y sin disponibilidades todo
     saldria agotado (revision de Cowork, 29-sep-2026). La base lo vuelve a comprobar por su cuenta;
     🔑 mientras baja, se queda con la LISTA CRUDA de precios y de disponibilidades: envuelve
     `_paginar` de la heredada EN TIEMPO DE EJECUCION (el fichero no se toca) y la deja como estaba
     al terminar. Con ellas se sabe que producto llego SIN dato (Fernando, 29-sep-2026: «sin dato
     no es agotado») y cuantas copias REPETIDAS trae cada listado (HEO repite filas mientras se
     pagina): la tolerancia de productos se mide sobre los distintos, y un repetido con copias
     distintas deja la pasada 'fallida' sin subir nada (remates, 29-sep-2026);
  3. convierte cada producto CON codigo de barras en una fila con las reglas del escaner 2
     (`escaner2_disponibilidad.construir_disponibilidad`): TODAS las marcas, disponibles y NO, cada una
     marcada si vino sin dato de disponibilidad o de precio. Los sin GTIN (~1.155) los quita la
     descarga heredada y solo se cuentan;
     🆕 3 bis (encargo H1, 8-oct-2026): LOS TRAMOS, EN SOMBRA. Con la lista cruda de products (la misma, sin pedir
     nada nuevo a HEO), cada fila con precio lleva `precio_escalon`, `uds_escalon` y `precio_pa` con el tramo mas
     barato (`escaner2_disponibilidad.poner_escalones`). Nadie los lee todavia para HEO. Si falla, van vacios, la
     pasada sigue y el run acaba en ROJO al final;
  4. sube las filas a `disp_lectura` en lotes y deja en la pasada sus recuentos;
  5. llama a `disp_aplicar_pasada`, la funcion de la base que, de una vez: pasa el blindaje
     anti-vaciado, apunta los cambios contra el estado de antes, marca lo que falta y cuadra. Si la
     rechaza, disp_estado NO se toca y el run sale en ROJO con el motivo;
  6. relee la pasada en la base y la imprime: lo que vale es lo que hay alli, no lo que dice esto.
     🔴 Si la base la aplico como CAIDA ACEPTADA (la salida del freno del 90 %), el run sale en ROJO
     con un aviso: esta aplicada, pero alguien tiene que mirar si HEO ha caido de verdad.
  7. 🆕 NOVEDADES DE FUNKO (encargo H, tramo 1, 29-sep-2026): con la pasada YA APLICADA, llama a
     `nov_seleccionar_pasada` (migracion 20260929134500 de la v2), que aparta las novedades de Funko
     y llena su cola. Es un PASO APARTE: si falla, la pasada sigue aplicada, el fallo se apunta en
     `nov_pasada` ('fallida', con el motivo) y en el log, NO se reintenta, lo que venga despues se
     ejecuta igual, y el run acaba en ROJO para que se vea. Sin Keepa ni Amazon.
  8. 🆕 VALORAR LAS NOVEDADES (encargo I, tramo 2, 29-sep-2026): otro PASO APARTE, detras de la seleccion
     (escaner2_novedades.valorar_pasada): con el interruptor de la base encendido (nov_parametros.valorar), la
     cuenta de las novedades a las que el cartero ya dio precio y tarifa de Amazon (con el codigo del Escaneo PRO)
     y Keepa para la cola (saldo leido antes, reserva de 20, cache de 72 h / 7 dias y el Escaneo PRO de 14 dias).
     Apagado: cero llamadas a Keepa. Si falla, la pasada y la seleccion siguen aplicadas, el fallo queda en
     nov_pasada.valoracion_* y el run acaba en ROJO al final. Y el VIGIA DE LA MARCA: si la seleccion cuenta
     productos con una marca parecida a 'Funko' y distinta (HEO ha cambiado la grafia), rojo al final.

🔒 NO TOCA NADA DEL ESCANER VIEJO NI DEL ESCANER 2: ni `escaner_memoria`, ni `escaner_resultados`, ni
   `reglas_director`, ni `escaner2_*`, ni `productos`. Solo `disp_pasada`, `disp_lectura`, la funcion
   `disp_aplicar_pasada` y, para LEER su tolerancia, `disp_parametros`; y, para las novedades, la
   funcion `nov_seleccionar_pasada` y `nov_pasada` (solo para apuntar un fallo) (lo comprueba
   test_escaner2_disponibilidad.py sobre el propio fichero). Lo que toca la valoracion (paso 8) vive en
   escaner2_novedades.py y lo censa test_escaner2_novedades.py. Cero llamadas a Amazon: Amazon es del cartero.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: escribe en tablas cerradas; sin ella aborta antes de nacer
   ningun cliente de red.

Uso:  python escaner2_heo_disponibilidad.py            (la pasada)
      python escaner2_heo_disponibilidad.py --rescate  (ultimo paso del workflow si el run fallo)
"""
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

PROVEEDOR = 'HEO'
LOTE = 500


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"DISPONIBILIDAD_NO_EJECUTADA: {motivo}")
    sys.exit(1)


RESCATE = sys.argv[1:] == ['--rescate']
if sys.argv[1:] not in ([], ['--rescate']):
    abortar('uso: escaner2_heo_disponibilidad.py [--rescate]')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
if not RESCATE and not (os.environ.get('HEO_USER') and os.environ.get('HEO_PASS')):
    abortar('sin credenciales de HEO (HEO_USER y HEO_PASS)')
RUN_ID = os.environ.get('GITHUB_RUN_ID') or ''

from supabase import create_client  # noqa: E402

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


class DescargaCortada(RuntimeError):
    """Uno de los tres endpoints de HEO no llego entero: la pasada no se aplica."""


class _Eco(io.TextIOBase):
    """Deja pasar lo que se imprime Y se lo guarda: descargar_catalogo_heo dice lo que HEO declara, lo
    que se bajo y lo que tiro sin GTIN SOLO en su log (la misma pieza que el barrido)."""

    def __init__(self, destino):
        self.destino, self.trozos = destino, []

    def write(self, s):
        self.destino.write(s)
        self.trozos.append(s)
        return len(s)

    def flush(self):
        self.destino.flush()


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _descargar_con_crudos(hd, eco):
    """`descargar_catalogo_heo(con_chase=True)` tal cual, pero quedandose con lo que devuelve `_paginar`
    para cada endpoint. La heredada busca `_paginar` en su modulo cada vez que la llama: se cambia ahi
    por una que guarda y llama a la de verdad, y se deja como estaba pase lo que pase."""
    crudos = {}
    paginar = hd._paginar

    def _paginar_que_guarda(endpoint, max_paginas=None):
        crudos[endpoint] = lista = paginar(endpoint, max_paginas)
        return lista

    hd._paginar = _paginar_que_guarda
    try:
        with redirect_stdout(eco):
            filas_heo, chase = hd.descargar_catalogo_heo(con_chase=True)
    finally:
        hd._paginar = paginar
    return filas_heo, chase, crudos


def _cerrar_fallida(pasada, motivo):
    """La pasada queda 'fallida' con su motivo y sin nada leido colgando (disp_lectura es de paso)."""
    sb.table('disp_lectura').delete().eq('pasada_id', pasada).execute()
    (sb.table('disp_pasada').update({'estado': 'fallida', 'motivo': motivo[:1000], 'terminada_en': _ahora()})
       .eq('id', pasada).eq('estado', 'leyendo').execute())


def rescatar():
    """🔴 Si el run muere a medias (tope de tiempo, cancelacion), su pasada no se queda 'leyendo' para
    siempre: SOLO la de ESTE run, y solo si sigue leyendo."""
    if not RUN_ID.isdigit():
        abortar('sin GITHUB_RUN_ID: no se sabe qué pasada es de este run')
    res = (sb.table('disp_pasada').select('id').eq('run_id', int(RUN_ID)).eq('estado', 'leyendo').execute())
    for fila in res.data or []:
        _cerrar_fallida(fila['id'], 'el run %s terminó sin cerrar la pasada (tope de tiempo, cancelación o '
                                    'caída); mira su log en Actions' % RUN_ID)
    print(f">>> RESCATE disp_pasada: {len(res.data or [])} pasada(s) de este run pasan de 'leyendo' a 'fallida'.")


def seleccionar_novedades(pasada):
    """NOVEDADES DE FUNKO (encargo H, tramo 1): con la pasada YA APLICADA, la base aparta las novedades de
    Funko y llena su cola (`nov_seleccionar_pasada`, idempotente). 🔴 PASO APARTE E INDEPENDIENTE: no lanza
    nunca. Si falla, la pasada SIGUE APLICADA (ya esta confirmada en la base), el fallo se apunta en
    `nov_pasada` ('fallida', con su motivo; si la pasada ya tenia fila no se toca) y en el log, y NO se
    reintenta: se rehace a mano llamando otra vez a la funcion con esa pasada. Devuelve (ok, lo que devolvio la
    base), y lo segundo None si fallo."""
    try:
        res = sb.rpc('nov_seleccionar_pasada', {'p_pasada': pasada}).execute().data
        print(f">>> NOVEDADES DE FUNKO: {res}", flush=True)
        return True, res
    except Exception as ex:
        motivo = f'{type(ex).__name__}: {ex}'
        print(f"NOVEDADES_NO_SELECCIONADAS: la pasada {pasada} sigue aplicada; la selección de novedades ha "
              f"fallado y se apunta en nov_pasada: {motivo[:500]}", flush=True)
        try:
            (sb.table('nov_pasada')
               .upsert({'pasada_id': pasada, 'proveedor': PROVEEDOR, 'estado': 'fallida', 'motivo': motivo[:1000]},
                       on_conflict='pasada_id', ignore_duplicates=True)
               .execute())
        except Exception as ex2:
            print(f"NOVEDADES_FALLO_SIN_APUNTAR: tampoco se ha podido apuntar en nov_pasada: "
                  f"{type(ex2).__name__}: {str(ex2)[:500]}", flush=True)
        return False, None


def valorar_novedades(pasada, seleccion=None):
    """VALORAR LAS NOVEDADES (encargo I, tramo 2): Keepa y la cuenta, en escaner2_novedades.py. 🔴 PASO APARTE: no
    lanza nunca (ni si el modulo no importa), la pasada y la seleccion ya estan aplicadas, y el fallo queda apuntado
    en nov_pasada.valoracion_*. Con el interruptor apagado, cero llamadas a Keepa. Devuelve True si salio bien."""
    try:
        import escaner2_novedades as nv
        # (Encargo V) Las que entran a valorar (novedades − subidas fuera): más de 100 es una AVALANCHA.
        ok, _res = nv.valorar_pasada(sb, pasada, keepa_llave=os.environ.get('KEEPA_API_KEY'),
                                     novedades_pasada=nv.novedades_a_valorar(seleccion))
        if not ok:
            print(f"NOVEDADES_NO_VALORADAS: la pasada {pasada} sigue aplicada y sus novedades seleccionadas; la valoración "
                  f"no ha salido bien y queda apuntada en nov_pasada (valoracion_estado y valoracion_motivo).", flush=True)
        return ok
    except Exception as ex:
        print(f"NOVEDADES_NO_VALORADAS: la pasada {pasada} sigue aplicada; la valoración ha fallado antes de poder "
              f"apuntarse: {type(ex).__name__}: {str(ex)[:500]}", flush=True)
        return False


def poner_escalones(dp, filas, crudos, M):
    """LOS TRAMOS DE HEO, EN SOMBRA (encargo H1, 8-oct-2026): `dp.poner_escalones` rellena precio_escalon, uds_escalon
    y precio_pa de cada fila con el tramo mas barato. 🔴 PASO QUE NO TUMBA LA PASADA: si falla, las tres columnas van
    VACIAS en todas las filas (la base admite las tres vacias), la pasada se sube y se aplica igual, y el run acaba en
    ROJO al final. En el log, solo recuentos: el repo es publico. Devuelve True si salio bien."""
    try:
        c = dp.poner_escalones(filas, crudos['catalog/products'], crudos['catalog/prices'], M)
        print(f">>> TRAMOS (en sombra, nadie los lee): {c['n_con_tramo']} productos con tramo · el tramo gana en "
              f"{c['n_escalon_gana']} · con descuento propio y tramo {c['n_propio_y_tramo']} · tramos raros ignorados {c['n_tramos_raros']} · repetidos con tramos distintos "
              f"(vacíos) {c['n_tramos_dudosos']} · sin precio (vacíos) {c['n_sin_precio']}", flush=True)
        return True
    except Exception as ex:
        for f in filas:
            f.update(precio_escalon=None, uds_escalon=None, precio_pa=None)
        print(f"ESCALONES_NO_CALCULADOS: los tramos han fallado y van vacíos; la pasada sigue: {type(ex).__name__}",
              flush=True)
        return False


def main():
    import escaner2_motor as e2
    import escaner2_disponibilidad as dp

    abrir = {'proveedor': PROVEEDOR, 'estado': 'leyendo', 'run_id': int(RUN_ID) if RUN_ID.isdigit() else None}
    pasada = sb.table('disp_pasada').insert(abrir).execute().data[0]['id']
    print(f">>> Pasada de disponibilidad {pasada} abierta (leyendo).", flush=True)
    try:
        # 0 · La tolerancia de la descarga, la de la base (la misma que aplica disp_aplicar_pasada).
        par = (sb.table('disp_parametros').select('tolerancia_endpoint').eq('proveedor', PROVEEDOR).execute().data or [{}])
        tolerancia = par[0].get('tolerancia_endpoint')
        if not isinstance(tolerancia, int) or isinstance(tolerancia, bool) or tolerancia < 0:
            raise DescargaCortada(f'sin tolerancia: disp_parametros no da una tolerancia_endpoint válida para {PROVEEDOR} '
                                  f'({tolerancia!r}); no se baja nada')

        # 1 · El catalogo, con la MISMA funcion que el barrido (import tardio: lee HEO_USER al cargar),
        #     y las listas crudas de precios y disponibilidades, cogidas al paso.
        import escaner2_heredado_descarga as hd
        eco = _Eco(sys.stdout)
        filas_heo, chase, crudos = _descargar_con_crudos(hd, eco)
        rec = dp.recuentos_del_log(''.join(eco.trozos))
        # Los repetidos de cada listado y el sin GTIN contado UNA vez (el log cuenta cada copia), antes
        # de guardar nada: la pasada lleva los buenos también si acaba fallida (revisión de Cowork).
        problemas = []
        try:
            conteos, problemas = dp.duplicados_de_los_crudos(crudos)
            rec.update(conteos)
            if rec.get('n_sin_gtin') is not None:
                unicos, copias = dp.sin_gtin_de_los_crudos(
                    [x.get('productNumber') for x in crudos['catalog/products']], filas_heo, chase)
                if copias != rec['n_sin_gtin']:
                    problemas.append('sin GTIN: el log cuenta %s y el listado crudo %s' % (rec['n_sin_gtin'], copias))
                rec['n_sin_gtin'] = unicos
        except dp.LecturaInvalida as ex:
            problemas = problemas + [str(ex)]
        # Los recuentos, a la pasada en cuanto se saben: también una fallida los necesita.
        sb.table('disp_pasada').update(rec).eq('id', pasada).execute()
        if problemas:
            raise dp.LecturaInvalida(' · '.join(problemas))
        cortada = dp.descarga_cortada(rec, tolerancia)
        if cortada:
            raise DescargaCortada('descarga cortada, no se aplica: ' + ' · '.join(cortada))
        con_precio, con_disponibilidad = dp.listas_de_los_crudos(crudos, rec)

        # 2 · Las filas, con las reglas del escaner 2. Todas las marcas, disponibles y no, y marcadas
        #     si vinieron sin dato.
        M = e2.cargar_motor()
        filas, cuentas = dp.construir_disponibilidad(
            filas_heo, chase, M, con_precio=con_precio, con_disponibilidad=con_disponibilidad,
            numeros_crudos=[x.get('productNumber') for x in crudos['catalog/products']])
        # 🔑 El cuadre con repetidos: cada copia repetida o tiene fila (y se quedo una) o no tiene GTIN
        #    (y el log la conto como sin GTIN). Sin GTIN, contado UNA vez por producto.
        if cuentas['n_duplicados_filas'] + cuentas['n_duplicados_sin_gtin'] != rec['n_duplicados']:
            raise dp.LecturaInvalida('repetidos: %s en el listado y %s con fila + %s sin GTIN'
                                     % (rec['n_duplicados'], cuentas['n_duplicados_filas'], cuentas['n_duplicados_sin_gtin']))
        n_sin_gtin = rec['n_sin_gtin']
        if rec['n_crudo'] != n_sin_gtin + cuentas['n_leidas'] + rec['n_duplicados']:
            raise dp.LecturaInvalida('no cuadra: crudo %s ≠ sin GTIN %s + leídas %s + repetidos %s'
                                     % (rec['n_crudo'], n_sin_gtin, cuentas['n_leidas'], rec['n_duplicados']))
        print(f">>> HEO declara {rec['n_declarado']} productos, {rec['n_declarado_precios']} precios y "
              f"{rec['n_declarado_disponibilidades']} disponibilidades · llegaron {rec['n_crudo']}, {rec['n_precios']} y "
              f"{rec['n_disponibilidades']} (tolerancia {tolerancia}) · repetidos {rec['n_duplicados']}, "
              f"{rec['n_duplicados_precios']} y {rec['n_duplicados_disponibilidades']} · sin GTIN {n_sin_gtin} · "
              f"leídas {cuentas['n_leidas']} (disponibles {cuentas['n_disponibles']}, agotados {cuentas['n_agotados']}) · "
              f"sin dato de disponibilidad {cuentas['n_sin_dato_disponibilidad']}, de precio {cuentas['n_sin_dato_precio']} · "
              f"con regla del escáner 2 {cuentas['por_regla']}", flush=True)

        # 2 bis · 🆕 LOS TRAMOS, EN SOMBRA (encargo H1): las tres columnas de OC2 con el tramo mas barato, de la lista
        #     cruda de products que ya se bajo. No cambia nada de lo que se sube ni de como se aplica, y no lanza.
        escalones_ok = poner_escalones(dp, filas, crudos, M)

        # 3 · Lo leido, a la base, en lotes; y los recuentos en la pasada. La base los contrasta.
        for i in range(0, len(filas), LOTE):
            sb.table('disp_lectura').insert([dict(f, pasada_id=pasada) for f in filas[i:i + LOTE]]).execute()
        (sb.table('disp_pasada').update({
            'n_leidas': cuentas['n_leidas'], 'n_disponibles': cuentas['n_disponibles'],
            'n_agotados': cuentas['n_agotados'], 'n_sin_dato_disponibilidad': cuentas['n_sin_dato_disponibilidad'],
            'n_sin_dato_precio': cuentas['n_sin_dato_precio'],
        }).eq('id', pasada).execute())

        # 4 · La base la aplica (o la rechaza) de una vez.
        resultado = sb.rpc('disp_aplicar_pasada', {'p_pasada': pasada}).execute().data
    except Exception as ex:
        motivo = f'{type(ex).__name__}: {ex}'
        _cerrar_fallida(pasada, motivo)
        abortar(f'pasada {pasada} fallida: {motivo[:500]}')

    # 5 · Lo que vale es lo que hay en la base.
    fila = sb.table('disp_pasada').select('*').eq('id', pasada).execute().data[0]
    print(">>> EN LA BASE: " + ' · '.join(f'{k} {fila.get(k)}' for k in (
        'estado', 'primera', 'caida_aceptada', 'n_crudo', 'n_duplicados', 'dif_productos', 'dif_precios',
        'dif_disponibilidades', 'n_sin_gtin', 'n_leidas', 'n_disponibles', 'n_agotados', 'n_sin_dato_disponibilidad',
        'n_sin_dato_precio', 'n_entran', 'n_vuelven', 'n_salen', 'n_a_disponible', 'n_a_agotado',
        'n_agotados_sin_dato', 'n_recuperan_dato', 'n_cambio_precio', 'n_ausentes', 'n_en_catalogo',
        'n_disponibles_estado')), flush=True)
    if fila['estado'] != 'aplicada':
        abortar(f"pasada {pasada} {fila['estado']}: {fila.get('motivo')} · la función dijo {resultado}")
    print(f">>> PASADA APLICADA: {fila['n_en_catalogo']} productos de HEO en el catálogo, "
          f"{fila['n_disponibles_estado']} disponibles.", flush=True)

    # 7 · NOVEDADES DE FUNKO (encargo H): paso aparte con la pasada ya aplicada; no lanza nunca, y lo que
    #     venga despues se ejecuta aunque falle. Si falla, el run acaba en rojo, pero AL FINAL.
    novedades_ok, seleccion = seleccionar_novedades(pasada)
    # 8 · VALORAR (encargo I): otro paso aparte, detrás; tampoco lanza. Si falla, rojo AL FINAL.
    valoracion_ok = valorar_novedades(pasada, seleccion)
    # 🔴 EL VIGÍA DE LA MARCA (encargo I, paso 0 d): lo cuenta la base en cada selección.
    marca_parecida = (seleccion or {}).get('marca_parecida') or 0

    rojo = False
    if fila.get('caida_aceptada'):
        # 🔴 Aplicada, pero NO es una pasada normal: el run en rojo para que se vea en Actions.
        print(f"CAIDA_ACEPTADA: la pasada {pasada} se ha aplicado como NUEVA REFERENCIA tras varios rechazos "
              f"estables por el freno del 90 %. Puede ser una caída real de HEO o un fallo estable de su API: "
              f"hay que mirarlo. {fila.get('motivo')}", flush=True)
        rojo = True
    if marca_parecida > 0:
        print(f"MARCA_PARECIDA: {marca_parecida} producto(s) de HEO tienen una marca que se parece a la de las novedades "
              f"y no es ella (marca ilike '%funko%' y distinta de 'Funko'). Si HEO ha cambiado la grafía, las novedades de "
              f"Funko se quedarían a cero en silencio: hay que mirarlo (nov_pasada.n_marca_parecida de la pasada {pasada}). "
              f"Todo lo demás de la pasada está aplicado.", flush=True)
        rojo = True
    if not novedades_ok or not valoracion_ok:
        rojo = True
    if not escalones_ok:
        # (Encargo H1) La pasada esta aplicada con las tres columnas vacias; los tramos hay que mirarlos.
        rojo = True
    if rojo:
        sys.exit(1)


if __name__ == '__main__':
    rescatar() if RESCATE else main()
