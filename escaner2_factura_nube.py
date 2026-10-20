# -*- coding: utf-8 -*-
"""ESCANER 2 · EL ESCANEO DE UNA FACTURA, EN LA NUBE (encargo F2, 16-oct-2026).

Lo lanza escaner2-factura.yml (workflow_dispatch), y a ese lo dispara la v2 al pulsar «Escanear» en Entrada de
facturas (app/(protegido)/entrada-facturas/escanear.ts). La v2 deja ANTES la peticion en la base
(`escaner2_factura_pasada`: la factura, sus lineas con su coste y la ejecucion) y le pasa al workflow solo la
`ejecucion`: el repo es PUBLICO y lo que viaja en el disparo se ve; el coste de una compra no.

  python escaner2_factura_nube.py --ejecucion <ejecucion>
      1. lee la pasada (tiene que estar «pedida»: dos corridas no la toman a la vez) y la pone «en_marcha»;
      2. escanea (escaner2_factura.escanear: app de hoy o Keepa en el momento, la cuenta del viejo, NL/BE al 12 %);
      3. (encargo P1, 19-oct-2026) escribe en `sondeo_keepa`, con `lote` = la ejecucion, TODOS los candidatos que
         Keepa dio para el codigo de barras de cada linea sin ASIN (y un centinela si no dio ninguno), y comprueba
         cuantos hay: la v2 los clasifica y pone el ASIN en la ficha cuando es claro (`asignar_asin_sondeo`);
      4. escribe TODAS las filas de una vez en `escaner2_factura_pais` (la tabla que lee la factura) y comprueba
         cuantas hay; 5. pone la pasada «terminada» con los tokens de Keepa. Si algo falla, «fallida» con su motivo.
      🔑 El sondeo va ANTES que las filas de la factura: la v2 da el escaneo por listo en cuanto ve filas, y para
         entonces los candidatos tienen que estar todos. Si el sondeo no se puede escribir, la pasada es «fallida»:
         una factura escaneada sin candidatos es justo lo que dejo cuatro dias sin ASIN automatico (15-18 oct).

  python escaner2_factura_nube.py --sombra <ejecucion vieja> [<ejecucion vieja> …]
      🔴 NO ESCRIBE NADA. Repite con el programa nuevo las facturas que ya escaneo el viejo (sus lineas y su coste,
      reconstruidos de `escaner_detalle`) y saca por el log SOLO recuentos (lineas, paises de la app y de Keepa,
      tokens) y la GRABACION de lo que contesto Keepa CIFRADA con la clave publica que llega en
      SOMBRA_CLAVE_PUBLICA (Fernando, 16-oct-2026: la lista de ASIN y EAN de nuestras facturas dice que compramos,
      a quien y cuando, y el repo es publico). Sin esa clave, la sombra no corre. En local, con la privada, se
      descifra y se repite la sombra para compararla con el viejo linea a linea.

🔒 LA LLAVE DE SERVICIO, O NO SE CORRE: lee `productos` (el IVA de la ficha) y las tablas de Amazon desatendido
   (test_escaner_llave_servicio.py, lista PROGRAMAS). KEEPA_API_KEY solo llega a este paso.
🔒 Ni escaner_detalle, ni escaner_resultados, ni el buzon `informes`, ni Excel en la biblioteca: el escaneo de una
   factura deja SU tabla y los candidatos de Keepa en `sondeo_keepa` (la pelicula del EAN->ASIN), y nada mas. No
   escribe ASIN en ninguna ficha: eso lo hace la v2, con sesion y con las guardas de la RPC.
🔴 UN FALLO NO SE CUENTA EN EL LOG (devolucion de Cowork, 16-oct-2026): el log de Actions es PUBLICO, y el texto de una
   excepcion puede llevar una fila entera («Failing row contains (…)») con EAN, ASIN y coste. En el log va solo el TIPO
   de la excepcion y donde salto (`_fallo_en_log`); el detalle, solo en `escaner2_factura_pasada.motivo_fallo`, que es
   privado. Ni `traceback.print_exc()` ni excepciones sin capturar: `main` lo envuelve todo.
"""
import os
import sys
import traceback
from datetime import datetime, timezone


def _fallo_en_log(ex):
    """Lo UNICO de una excepcion que puede ir al log publico: su tipo y el fichero y la linea donde salto. Nunca su
    texto (puede llevar una fila con el coste)."""
    tb = traceback.extract_tb(ex.__traceback__)
    donde = ' en %s:%d' % (os.path.basename(tb[-1].filename), tb[-1].lineno) if tb else ''
    return '%s%s' % (type(ex).__name__, donde)


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"ESCANEO_FACTURA_NO_EJECUTADO: {motivo}")
    sys.exit(1)


_args = sys.argv[1:]
if not _args or _args[0] not in ('--ejecucion', '--sombra') or len(_args) < 2 or (_args[0] == '--ejecucion' and len(_args) != 2):
    abortar('uso: escaner2_factura_nube.py --ejecucion <ejecucion> | --sombra <ejecucion vieja> [...]')
_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
_clave_publica = None
if _args[0] == '--sombra':
    import base64 as _b64
    try:
        _clave_publica = _b64.b64decode(os.environ.get('SOMBRA_CLAVE_PUBLICA', '').strip(), validate=True).decode('ascii')
    except Exception:
        _clave_publica = None
    if not _clave_publica or 'BEGIN PUBLIC KEY' not in _clave_publica:
        abortar('la sombra necesita SOMBRA_CLAVE_PUBLICA (PEM en base64): sin ella no saca nada')

from escaner2_base import cliente  # noqa: E402

import escaner2_factura as ef  # noqa: E402
import escaner2_motor as e2  # noqa: E402
import escaner2_novedades as nv  # noqa: E402

sb = cliente(os.environ['SUPABASE_URL'], _llave_svc)


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def de_verdad(ejecucion):
    base = ef.Base(sb)
    pasada = base.pasada(ejecucion)
    if not pasada:
        abortar('no hay pasada para la ejecución %s' % ejecucion)
    if pasada['estado'] != 'pedida':
        abortar('la pasada %s está «%s», no «pedida»: no se escanea dos veces' % (ejecucion, pasada['estado']))
    run = os.environ.get('GITHUB_RUN_ID')
    if base.marcar(pasada['id'], {'estado': 'en_marcha', 'empezada_en': _ahora(), 'run_id': int(run) if run else None},
                   estado_antes='pedida') != 1:
        abortar('otra corrida ha tomado la pasada %s' % ejecucion)
    keepa = nv.Keepa(os.environ.get('KEEPA_API_KEY'))
    try:
        try:
            keepa.leer_saldo()
        except nv.KeepaFalla as ex:
            keepa.caido = str(ex)
        antes = keepa.saldo
        hoy = ef.hoy_madrid()
        filas, resumen = ef.escanear(pasada['lineas'], base, keepa, e2.cargar_motor(), hoy)
        sondeo, descartadas = ef.filas_sondeo(ejecucion, resumen['sondeo'], hoy)
        n_snd = base.escribir_sondeo(ejecucion, sondeo)
        if n_snd != len(sondeo):
            raise RuntimeError('sondeo_keepa: hay %s filas con este lote y se esperaban %d' % (n_snd, len(sondeo)))
        n = base.escribir(pasada['id'], ejecucion, filas)
        if n != len(filas):
            raise RuntimeError('se escribieron %s filas y se esperaban %d' % (n, len(filas)))
        base.marcar(pasada['id'], {
            'estado': 'terminada', 'terminada_en': _ahora(), 'keepa_saldo_antes': antes,
            'keepa_saldo_despues': keepa.saldo, 'keepa_tokens': keepa.tokens, 'keepa_peticiones': keepa.peticiones,
            'n_paises_app': resumen['paises_app'], 'n_paises_keepa': resumen['paises_keepa'],
            'n_paises_sin_dato': resumen['paises_sin_dato'], 'motivo_fallo': keepa.caido})
        print('ESCANEO_FACTURA_HECHO: %d líneas · %d filas · países: %d de la app, %d de Keepa, %d sin dato · '
              'Keepa: %d peticiones, %d tokens (saldo %s → %s) · sondeo: %d filas (%d candidatos, %d repetidas fuera)'
              % (resumen['lineas'], len(filas), resumen['paises_app'], resumen['paises_keepa'],
                 resumen['paises_sin_dato'], keepa.peticiones, keepa.tokens, antes, keepa.saldo, len(sondeo),
                 sum(1 for x in sondeo if x['asin_candidato']), descartadas))
    except Exception as ex:
        # 🔒 El detalle, a la base (privada); al log, solo el tipo y la línea.
        try:
            base.marcar(pasada['id'], {'estado': 'fallida', 'terminada_en': _ahora(),
                                       'motivo_fallo': ('%s: %s' % (type(ex).__name__, ex))[:500],
                                       'keepa_tokens': keepa.tokens, 'keepa_peticiones': keepa.peticiones})
        except Exception as ex2:
            abortar('falló el escaneo de %s (%s) y tampoco se pudo apuntar como fallida (%s)'
                    % (ejecucion, _fallo_en_log(ex), _fallo_en_log(ex2)))
        abortar('falló el escaneo de %s: %s (el detalle, en escaner2_factura_pasada.motivo_fallo)'
                % (ejecucion, _fallo_en_log(ex)))


def sombra(ejecuciones):
    base = ef.Base(sb)
    grabadora = ef.Grabadora()
    keepa = nv.Keepa(os.environ.get('KEEPA_API_KEY'), http=grabadora)
    M = e2.cargar_motor()
    hoy = ef.hoy_madrid()
    keepa.leer_saldo()
    print('SOMBRA: hoy %s · saldo de Keepa al empezar %s' % (hoy, keepa.saldo))
    for i, ej in enumerate(ejecuciones, 1):
        detalle = base.detalle_viejo(ej)
        if not detalle:
            abortar('la ejecución vieja F%d no tiene filas en escaner_detalle' % i)
        productos = base.productos(sorted({d['producto_id'] for d in detalle if d.get('producto_id')}))
        lineas = ef.lineas_de_la_pasada_vieja(detalle, productos)
        t0, p0 = keepa.tokens, keepa.peticiones
        _filas, r = ef.escanear(lineas, base, keepa, M, hoy, productos=productos)
        # 🔒 Solo recuentos: ni EAN, ni ASIN, ni precios, ni costes. La factura va por su número de orden.
        print('SOMBRA F%d: %d líneas (%d con todo de la app) · países: %d de la app, %d de Keepa, %d sin dato · '
              'Keepa: %d peticiones, %d tokens'
              % (i, r['lineas'], r['lineas_todo_app'], r['paises_app'], r['paises_keepa'], r['paises_sin_dato'],
                 keepa.peticiones - p0, keepa.tokens - t0))
    print('SOMBRA: saldo de Keepa al terminar %s' % keepa.saldo)
    paquete = grabadora.cifrar(_clave_publica)
    print('GRABACION_CIFRADA: %d peticiones, %d caracteres en trozos de 4000' % (len(grabadora.peticiones), len(paquete)))
    for j in range(0, len(paquete), 4000):
        print('GRABACION_CIFRADA_%03d %s' % (j // 4000, paquete[j:j + 4000]))


def main():
    if _args[0] == '--ejecucion':
        de_verdad(_args[1].strip())
    else:
        sombra([a.strip() for a in _args[1:] if a.strip()])


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as _ex:
        # 🔒 Ni la sombra ni nada deja una excepción sin capturar: Python imprimiría su texto en el log público.
        abortar('fallo sin capturar: %s' % _fallo_en_log(_ex))
