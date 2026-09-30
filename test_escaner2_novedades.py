# -*- coding: utf-8 -*-
"""Banco de la VALORACION DE LAS NOVEDADES DE FUNKO (encargo I, tramo 2, 29-sep-2026): escaner2_novedades.py.

SIN RED, SIN SECRETOS Y SIN BASE: el modulo de verdad contra una base de mentira (las tablas y vistas que lee, y
las cuatro funciones de la v2 imitadas en lo que al modulo le importa) y un Keepa de mentira (saldo y productos,
con su cuenta de tokens). TODOS los precios son inventados y redondos: el repo es publico y el coste de HEO no se
publica.

QUE PRUEBA:
  (A) LA FICHA DE KEEPA: caidas, puestos, tarifa y comision; sin dato no es cero (caidas -1 -> None; la tarifa que
      no viene o viene a 0 -> None, NUNCA 0).
  (B) EL INTERRUPTOR APAGADO: cero llamadas a Keepa (ni el saldo), solo el cierre 'apagada'.
  (C) LA RESERVA DE 20 NUNCA SE CRUZA: con saldo 0, ninguna peticion; con el saldo JUSTO (reserva + tope), UNA; lo
      que no cabe espera Keepa; y si una respuesta la cruza, se dice y el paso sale en rojo.
  (D) EL ORDEN DE LA COLA: con saldo para cinco peticiones, las cuatro de la primera (una bajada) y la primera de
      la segunda; y los paises en su orden (ES, IT, FR, DE).
  (E) LA CACHE y el ESCANEO PRO, con UNA ventana de 15 dias (encargo V): dentro, 0 tokens; fuera, se pregunta. Y
      de lo guardado solo las VENTAS: ni la tarifa ni la comision.
  (F) LAS NUESTRAS VAN POR EL MISMO CAMINO (encargo V), con SU ficha: de la cache y del Escaneo PRO solo sus ASIN, a
      Keepa se le pregunta por ASIN, y la ficha no pasa por la guarda de la marca.
  (G) KEEPA CAIDO: la pasada no se toca; lo que faltaba espera Keepa, el fallo se apunta y el paso sale en rojo;
      la llave no sale en ningun mensaje.
  (H) LAS PUERTAS DEL ESCANEO PRO con el dato de Keepa: se vende -> espera Amazon (con sus filas de ventas, SIN la
      tarifa ni la comision de Keepa: encargo V); no se vende -> NO SE VENDE; sin ficha -> SIN HISTORIAL; varias fichas
      sin poder elegir -> Sin datos. Y EL CUADRE del flujo que se manda a la base.
  (I) LA CUENTA de una novedad «lista», al centimo, con la formula del Escaneo PRO (numeros escritos a mano).
  (J) LA CUENTA COINCIDE CON LA DEL ESCANEO PRO: filas fabricadas (siempre) y, si NOV_CASOS_REALES apunta a un JSON
      con filas REALES de escaner2_resultado_pais (el CI de la v2, que es privado, lo hace), al menos 5 al centimo.
  (K) EL MODULO, POR ESTRUCTURA: que tablas lee, que escribe (solo inserta en nov_keepa y nov_excel) y a que funciones
      llama; y ni escaner_resultados ni el buzon `informes`.
  (X) EL EXCEL (encargo V): con un COMPRAR entre lo valorado en la ejecucion, el Excel del escaner nuevo (las hojas del
      viejo + «Novedades», con el origen de cada pais) al bucket escaner2 y su fila en nov_excel; sin COMPRAR, nada; si
      no se puede subir, rojo. Y LAS CUENTAS SUELTAS (y 40): la cuenta, el Excel y el Telegram, sin las ventas de
      Keepa, sin tocar nov_pasada, y nada con el interruptor apagado.
  (R) EL RESPALDO DE KEEPA (añadido 2): los paises en que Amazon fallo se piden a Keepa en ese momento (por ASIN, con
      buybox, 3 tokens; nunca la cache); la comision sobre el precio de Amazon; el ESCALON DE 20 €: precio base de Keepa
      y precio de venta del mismo lado, o «pendiente: cambia de escalon»; sin precio base, cruce.
  (T) EL TELEGRAM (añadido 3), con el formato del viejo: con COMPRAR, sin COMPRAR (no se manda), avalancha, incompleto;
      sin claves no manda y no falla; si Telegram falla, la corrida sigue; la llave no sale.
  (A) LA AVALANCHA: mas de 100 novedades en la pasada → el Excel se abre con el aviso arriba, y el Telegram lo dice.
"""
import ast
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import escaner2_motor as e2
import escaner2_novedades as nv

fallos = []
CENTIMO = 0.005


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


M = e2.cargar_motor()
AHORA = datetime(2026, 9, 29, 18, 5, tzinfo=timezone.utc)
LLAVE = 'LLAVE-DE-KEEPA-DE-MENTIRA-123'
DOM = {9: 'ES', 8: 'IT', 4: 'FR', 3: 'DE'}


def iso(d):
    return d.isoformat()


# ═══ LA BASE DE MENTIRA ═══════════════════════════════════════════════════════════════
class _Q:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.filtros, self.orden, self.desde, self.hasta, self.tope, self.fila = base, tabla, [], None, None, None, None, None
        self.accion = 'select'

    def select(self, *_a, **_k):
        self.accion = 'select'
        return self

    def insert(self, fila):
        self.accion, self.fila = 'insert', fila
        return self

    def update(self, fila):
        self.accion, self.fila = 'update', fila
        return self

    def delete(self):
        self.accion = 'delete'
        return self

    def eq(self, c, v):
        self.filtros.append(lambda r: r.get(c) == v)
        return self

    def in_(self, c, vs):
        vs = list(vs)
        self.filtros.append(lambda r: r.get(c) in vs)
        return self

    def gte(self, c, v):
        self.filtros.append(lambda r: r.get(c) is not None and nv._fecha(r.get(c)) >= nv._fecha(v))
        return self

    def order(self, c, desc=False):
        self.orden = (c, desc)
        return self

    def range(self, a, b):
        self.desde, self.hasta = a, b
        return self

    def limit(self, n):
        self.tope = n
        return self

    def execute(self):
        import types
        self.base.ops.append((self.tabla, self.accion))
        if self.accion == 'insert':
            if self.tabla in self.base.fallan:
                raise RuntimeError('la base de mentira falla al insertar en %s' % self.tabla)
            self.base.tablas.setdefault(self.tabla, []).append(dict(self.fila, consultada_en=iso(self.base.reloj())))
            return types.SimpleNamespace(data=[self.fila])
        filas = [r for r in self.base.leer(self.tabla) if all(f(r) for f in self.filtros)]
        if self.orden:
            c, desc = self.orden
            filas.sort(key=lambda r: (r.get(c) is None, r.get(c) if not isinstance(r.get(c), bool) else int(r.get(c))), reverse=desc)
        if self.desde is not None:
            filas = filas[self.desde:self.hasta + 1]
        if self.tope is not None:
            filas = filas[:self.tope]
        return types.SimpleNamespace(data=[dict(r) for r in filas])


class Base:
    def __init__(self, valorar=True, novedades=(), keepa_cache=(), cruces=(), fotos=(), res_ean=(), res_pais=(),
                 valoraciones=(), productos=None, fallan=()):
        self.ops, self.rpcs, self.fallan, self.subidos = [], [], set(fallan), []
        self.reloj = lambda: AHORA
        self.tablas = {
            'nov_parametros': [{'proveedor': 'HEO', 'marca': 'Funko', 'valorar': valorar, 'keepa_reserva': 20,
                                'keepa_tope_peticion': 3, 'keepa_horas_nuevo': 360, 'keepa_dias_precio': 15, 'escaneo_pro_dias': 15}],
            'escaner2_parametros': [{'proveedor': 'HEO', 'umbral_caidas_30d': 8, 'paises_filtro': ['ES', 'IT', 'FR', 'DE'],
                                     'paises_calculo': ['ES', 'IT', 'FR', 'DE']}],
            'nov_novedad': [dict(n) for n in novedades],
            'nov_keepa': [dict(k) for k in keepa_cache],
            'escaner2_cruce': list(cruces), 'escaner2_foto': list(fotos), 'escaner2_resultado_ean': list(res_ean),
            'escaner2_resultado_pais': list(res_pais), 'nov_valoracion': [dict(v) for v in valoraciones],
            'productos': productos if productos is not None else [{'id': 'p1', 'ean': '8412345678905', 'asin': 'B0NUESTRO1',
                                                                   'iva_pct': 0.21, 'activo': True}],
            'disp_estado': [{'proveedor': 'HEO', 'producto_prov': n['producto_prov'], 'ean_core': n['ean_norm'],
                             'ean_norm': n['ean_norm'], 'nombre': n['nombre'], 'disponible': True, 'ausencias': 0,
                             'es_chase': n['es_chase'], 'precio_catalogo': n['precio_ahora']} for n in novedades],
        }

    def leer(self, tabla):
        if tabla == 'nov_cola':
            # 🔑 Como la vista de la base (encargo V): pendientes y esperando Keepa, las nuestras también si traen sus fichas.
            vivas = [n for n in self.tablas['nov_novedad'] if n['estado'] in ('pendiente', 'espera_keepa')
                     and (not n['nuestro'] or n.get('asins_nuestros'))]
            vivas.sort(key=lambda n: (n['prioridad'], n.get('cambio_pct') if n['prioridad'] == 1 else 0, n['creada_en'], n['id']))
            return [dict(n, puesto=i + 1) for i, n in enumerate(vivas)]
        return self.tablas.get(tabla, [])

    def table(self, nombre):
        return _Q(self, nombre)

    @property
    def storage(self):
        base = self

        class _Cubo:
            def __init__(self, cubo):
                self.cubo = cubo

            def upload(self, ruta, contenido, opciones):
                if 'storage' in base.fallan:
                    raise RuntimeError('StorageException de mentira: 429 too_many_connections')
                base.subidos.append((self.cubo, ruta, contenido, opciones))
                return {'Key': ruta}

        class _Storage:
            def from_(self, cubo):
                return _Cubo(cubo)
        return _Storage()

    def rpc(self, nombre, params):
        import types
        base = self

        class _Llamada:
            def execute(self):
                base.rpcs.append((nombre, params))
                if nombre in base.fallan:
                    raise RuntimeError('APIError de mentira en %s' % nombre)
                if nombre == 'nov_guardar_keepa':
                    n = next(x for x in base.tablas['nov_novedad'] if x['id'] == params['p_novedad'])
                    # 🔴 Como la base (encargo V): la tarifa y la comisión de Keepa ya no entran; y una nuestra, con SU ficha.
                    if any('fee_fba' in f or 'ref_pct' in f for f in params['p_filas'] or []):
                        raise RuntimeError('KEEPA_SIN_TARIFA de mentira')
                    if n['nuestro'] and any(f['asin'] not in n['asins_nuestros'] for f in params['p_filas'] or []):
                        raise RuntimeError('FICHA_NO_NUESTRA de mentira')
                    n['estado'] = params['p_destino']
                    for f in params['p_filas'] or []:
                        base.tablas['nov_valoracion'].append(dict(f, novedad_id=n['id']))
                    return types.SimpleNamespace(data={'estado': params['p_destino']})
                if nombre == 'nov_guardar_cuenta':
                    return types.SimpleNamespace(data={'estado': 'valorada'})
                if nombre == 'nov_cerrar_valoracion':
                    return types.SimpleNamespace(data={'estado': params['p_datos']['estado']})
                raise RuntimeError('función inesperada %s' % nombre)
        return _Llamada()

    def llamadas(self, nombre):
        return [p for n, p in self.rpcs if n == nombre]


def novedad(i, motivo='baja_precio', ean='889698100002', nuestro=False, estado='pendiente', precio=8.0, creada=None, es_chase=False,
            asins=None):
    pri = 1 if motivo == 'baja_precio' else 3 if motivo == 'sube_precio' else 2
    return {'id': 'nov-%d' % i, 'proveedor': 'HEO', 'producto_prov': 'FK%05d' % i, 'ean_norm': ean, 'nombre': 'Funko Pop! Figura %d' % i,
            'motivo': motivo, 'prioridad': pri, 'cambio_pct': -20.0 + i if pri == 1 else None, 'precio_ahora': precio,
            'precio_antes': precio * 1.25 if pri == 1 else None,
            'es_chase': es_chase, 'nuestro': nuestro, 'asins_nuestros': asins, 'estado': estado,
            'creada_en': iso(creada or AHORA - timedelta(minutes=10 - i))}


def prod(asin, caidas=12, fee=350, ref=15.0, rank=5000, rank90=6000, titulo='Funko Pop! Figura'):
    p = {'asin': asin, 'title': titulo, 'stats': {'current': [-1, 1999, -1, rank], 'avg90': [-1, 1999, -1, rank90],
                                                'salesRankDrops30': caidas}, 'referralFeePercentage': ref}
    if fee is not None:
        p['fbaFees'] = {'pickAndPackFee': fee}
    return p


class KeepaFalso:
    """El Keepa de mentira: saldo, productos por (pais, codigo) y cuanto cuesta cada peticion (1 por producto)."""

    def __init__(self, saldo=300, productos=None, caido=False, coste_extra=0):
        self.saldo, self.productos, self.caido, self.coste_extra = saldo, productos or {}, caido, coste_extra
        self.llamadas = []

    def __call__(self, url, params, timeout):
        self.llamadas.append((url.rsplit('/', 1)[-1], DOM.get(params.get('domain')),
                              params.get('code') or (('asin:' + params['asin'] + ('+bb' if params.get('buybox') else '')) if params.get('asin') else None)))
        if params.get('key') != LLAVE:
            return 401, {'error': {'message': 'bad key'}}
        if self.caido:
            raise ConnectionError('Read timed out (key=%s)' % LLAVE)
        if url.endswith('/token'):
            return 200, {'tokensLeft': self.saldo, 'refillRate': 5}
        pais = DOM[params['domain']]
        ps = []
        if params.get('asin'):
            # Por ASIN (las nuestras): el producto de ese ASIN, venga de donde venga en la lista de mentira.
            for a in params['asin'].split(','):
                ps += [x for (pp, _c), v in self.productos.items() if pp in (pais, None) for x in v if x['asin'] == a][:1]
        else:
            for code in params['code'].split(','):
                ps += self.productos.get((pais, code), self.productos.get((None, code), []))
        coste = len(ps) * (3 if params.get('buybox') else 1) + self.coste_extra
        self.saldo -= coste
        return 200, {'products': ps, 'tokensLeft': self.saldo, 'tokensConsumed': coste}

    def de_producto(self):
        return [(d, c) for q, d, c in self.llamadas if q == 'product']


TELEGRAM = []


def post_falso(url, data, timeout):
    import types
    TELEGRAM.append((url, data))
    return types.SimpleNamespace(status_code=200)


def correr(base, keepa=None, llave=LLAVE, novedades_pasada=None, env=None):
    salida = []
    ok, res = nv.valorar_pasada(base, 'PASADA-1', keepa_llave=llave, http=keepa or KeepaFalso(), dormir=lambda s: None,
                                ahora=lambda: AHORA, imprimir=lambda *a, **k: salida.append(' '.join(str(x) for x in a)),
                                run_id='36700000001', novedades_pasada=novedades_pasada, env=env if env is not None else {},
                                post=post_falso)
    return ok, res, '\n'.join(salida)


def cierre(base):
    return base.llamadas('nov_cerrar_valoracion')[-1]['p_datos']


def cuadra(d):
    """El cuadre del flujo, el mismo que exige la base (nov_pasada_valoracion_cuadra)."""
    return (d['v_en_cola'] == d['v_keepa'] + d['v_keepa_cache'] + d['v_escaneo_pro'] + d['v_espera_saldo'] + d['v_espera_fallo']
            and d['v_keepa'] + d['v_keepa_cache'] + d['v_escaneo_pro'] == d['v_no_se_vende'] + d['v_sin_historial']
            + d['v_varias_fichas'] + d['v_a_amazon']
            and d['v_listas'] == d['v_cuentas'] + d['v_cuenta_fallo'])


# ── (A) LA FICHA DE KEEPA ────────────────────────────────────────────────────────────────
f = nv.ficha_de_keepa(prod('B0KEEPA001', caidas=12, fee=412, ref=15.02, rank=5000, rank90=6100))
eq('(A) caídas, puestos, tarifa en euros (pickAndPackFee/100) y comisión', (f['asin'], f['caidas_30d'], f['rank'], f['rank_90d'], f['fee_fba'], f['ref_pct']),
   ('B0KEEPA001', 12, 5000, 6100, 4.12, 15.02))
f = nv.ficha_de_keepa(prod('B0KEEPA002', caidas=-1, fee=None, rank=-1, rank90=-1))
eq('(A) 🔴 sin dato no es cero: caídas -1 → None, sin puesto → None, SIN TARIFA → None (nunca 0)', (f['caidas_30d'], f['rank'], f['rank_90d'], f['fee_fba']), (None, None, None, None))
eq('(A) 🔴 una tarifa a 0 → None, nunca 0', nv.ficha_de_keepa(prod('B0KEEPA003', fee=0))['fee_fba'], None)
eq('(A) 0 caídas son 0 (un dato), no None', nv.ficha_de_keepa(prod('B0KEEPA004', caidas=0))['caidas_30d'], 0)

# ── (B) EL INTERRUPTOR APAGADO: CERO LLAMADAS A KEEPA ────────────────────────────────────
b = Base(valorar=False, novedades=[novedad(1), novedad(2, 'nuevo', ean='889698100019')])
k = KeepaFalso()
ok, res, txt = correr(b, k)
eq('(B) apagado: CERO llamadas a Keepa (ni el saldo), y verde', (k.llamadas, ok), ([], True))
eq('(B) …solo cierra la valoración como apagada, sin tocar la cola', ([n for n, _p in b.rpcs], cierre(b), [n['estado'] for n in b.tablas['nov_novedad']]),
   (['nov_cerrar_valoracion'], {'estado': 'apagada'}, ['pendiente', 'pendiente']))
eq('(B) …y lo dice', 'APAGADA' in txt, True)

# ── (C) LA RESERVA DE 20 NUNCA SE CRUZA ─────────────────────────────────────────────────
PRODS = {(None, '889698100002'): [prod('B0NOVEDA01', caidas=20)], (None, '889698100019'): [prod('B0NOVEDA02', caidas=3)]}
b = Base(novedades=[novedad(1), novedad(2, 'nuevo', ean='889698100019')])
k = KeepaFalso(saldo=0, productos=PRODS)
ok, res, txt = correr(b, k)
eq('(C) saldo 0: se lee el saldo UNA vez y NINGUNA petición de producto', ([q for q, _d, _c in k.llamadas]), ['token'])
eq('(C) …las dos esperan Keepa, con su motivo, y el paso cuadra (verde: esperar saldo no es un fallo)',
   ([n['estado'] for n in b.tablas['nov_novedad']], cierre(b)['v_espera_saldo'], cuadra(cierre(b)), ok,
    b.llamadas('nov_guardar_keepa')[0]['p_motivo'].startswith('sin saldo de Keepa: quedaban 0 tokens, reserva 20')),
   (['espera_keepa', 'espera_keepa'], 2, True, True, True))
b = Base(novedades=[novedad(1), novedad(2, 'nuevo', ean='889698100019')])
k = KeepaFalso(saldo=23, productos=PRODS)
ok, res, txt = correr(b, k)
eq('(C) saldo JUSTO (20 de reserva + 3 que puede costar una): UNA petición (la primera de la cola, ES), y para',
   k.de_producto(), [('ES', '889698100002')])
eq('(C) …el saldo queda en 22 (nunca por debajo de 20), la respuesta queda en la caché y las dos esperan',
   (k.saldo, cierre(b)['keepa_saldo_despues'], cierre(b)['keepa_reserva_cruzada'], len(b.tablas['nov_keepa']),
    [n['estado'] for n in b.tablas['nov_novedad']]), (22, 22, False, 1, ['espera_keepa', 'espera_keepa']))
eq('(C) …y lo gastado, apuntado: saldo antes 23, 1 petición, 1 token', (cierre(b)['keepa_saldo_antes'], cierre(b)['keepa_peticiones'], cierre(b)['keepa_tokens']),
   (23, 1, 1))
b = Base(novedades=[novedad(1)])
k = KeepaFalso(saldo=23, productos=PRODS, coste_extra=3)
ok, res, txt = correr(b, k)
eq('(C) 🔴 si una respuesta cuesta más de lo previsto y cruza la reserva (23 → 19), se dice y el paso sale en ROJO',
   (k.saldo, cierre(b)['keepa_reserva_cruzada'], ok, 'la reserva de 20 tokens se ha cruzado' in cierre(b)['motivo']), (19, True, False, True))

# ── (D) EL ORDEN DE LA COLA ─────────────────────────────────────────────────────────────
b = Base(novedades=[novedad(2, 'nuevo', ean='889698100019'), novedad(1)])   # la bajada, aunque llegue después, va primero
k = KeepaFalso(saldo=27, productos=PRODS)
ok, res, txt = correr(b, k)
eq('(D) la cola en su orden: las cuatro de la bajada (ES, IT, FR, DE) y la primera de la «nuevo», y para en 22',
   (k.de_producto(), k.saldo), ([('ES', '889698100002'), ('IT', '889698100002'), ('FR', '889698100002'), ('DE', '889698100002'),
                                 ('ES', '889698100019')], 22))
eq('(D) …la bajada, entera, se vende (20 caídas): a Amazon; la otra espera Keepa',
   {n['id']: n['estado'] for n in b.tablas['nov_novedad']}, {'nov-1': 'espera_amazon', 'nov-2': 'espera_keepa'})

# ── (E) LA CACHÉ (72 h / 7 días) Y EL ESCANEO PRO (14 días) ──────────────────────────────
def cache(ean, horas, fichas=None):
    return [{'ean_norm': ean, 'pais': p, 'fichas': fichas if fichas is not None else [nv.ficha_de_keepa(prod('B0CACHE001', caidas=15))],
             'consultada_en': iso(AHORA - timedelta(hours=horas))} for p in nv.PAISES]


b = Base(novedades=[novedad(2, 'nuevo', ean='889698100019')], keepa_cache=cache('889698100019', 14 * 24))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) «nuevo» con Keepa de hace 14 días (< 15, la ventana única): 0 llamadas a Keepa, y el dato es de la caché',
   (k.llamadas, cierre(b)['v_keepa_cache'], {v['ventas_origen'] for v in b.tablas['nov_valoracion']}), ([], 1, {'keepa_cache'}))
b = Base(novedades=[novedad(2, 'nuevo', ean='889698100019')], keepa_cache=cache('889698100019', 16 * 24))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) «nuevo» con Keepa de hace 16 días (> 15): se pregunta a Keepa (4 países)', len(k.de_producto()), 4)
b = Base(novedades=[novedad(1)], keepa_cache=cache('889698100002', 14 * 24))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) una BAJADA con Keepa de hace 14 días: la MISMA ventana, 0 llamadas', (k.llamadas, cierre(b)['v_keepa_cache']), ([], 1))
b = Base(novedades=[novedad(1)], keepa_cache=cache('889698100002', 16 * 24))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) una BAJADA con Keepa de hace 16 días (> 15): se pregunta', len(k.de_producto()), 4)


def escaneo_pro(dias, puerta='d', paises_usados=('ES', 'IT', 'FR', 'DE')):
    cuando = iso(AHORA - timedelta(days=dias))
    cruces = [{'id': 'cr1', 'pasada_id': 'pa1', 'estado': 'lista', 'creado_en': cuando, 'fecha_datos': cuando, 'paises_usados': list(paises_usados)}]
    fotos = [{'id': 'fo1', 'pasada_id': 'pa1', 'ean_norm': '889698100002', 'es_chase': False}]
    res_ean = [{'id': 're1', 'cruce_id': 'cr1', 'foto_id': 'fo1', 'puerta': puerta, 'asin': 'B0ESCPRO01'}]
    res_pais = [{'resultado_ean_id': 're1', 'pais': p, 'asin': 'B0ESCPRO01', 'titulo': 'Funko Pop! Figura', 'caidas_30d': c,
                 'rank': 5000, 'rank_90d': 6000, 'ref_pct': 15.0, 'fee_fba': 3.51} for p, c in (('ES', 11), ('DE', 2))]
    return dict(cruces=cruces, fotos=fotos, res_ean=res_ean, res_pais=res_pais)


b = Base(novedades=[novedad(1)], **escaneo_pro(10))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) una bajada de un Funko con Escaneo PRO de hace 10 días (< 15): 0 llamadas a Keepa, dato «escaneo_pro», y SIN su tarifa ni su comisión',
   (k.llamadas, cierre(b)['v_escaneo_pro'], sorted((v['pais'], v['ventas_origen'], v['caidas_30d'], 'fee_fba' in v or 'ref_pct' in v)
                                                   for v in b.tablas['nov_valoracion'])),
   ([], 1, [('DE', 'escaneo_pro', 2, False), ('ES', 'escaneo_pro', 11, False)]))
eq('(E) …se vende (11 caídas en ES > 8): a Amazon, con la ficha del Escaneo PRO', [n['estado'] for n in b.tablas['nov_novedad']], ['espera_amazon'])
b = Base(novedades=[novedad(1)], **escaneo_pro(16))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) con Escaneo PRO de hace 16 días (> 15): se pregunta a Keepa', len(k.de_producto()), 4)
b = Base(novedades=[novedad(1)], **escaneo_pro(10, paises_usados=('ES', 'DE')))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(E) un Escaneo PRO sin los cuatro países no vale como dato entero: se pregunta', len(k.de_producto()), 4)

# ── (F) LAS NUESTRAS, POR EL MISMO CAMINO, CON SU FICHA (encargo V) ─────────────────────
b = Base(novedades=[novedad(1, nuestro=True)])
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(F) una nuestra de ANTES (sin sus fichas): no está en la cola, y Keepa ni se toca', (k.llamadas, cierre(b)['v_en_cola'], ok), ([], 0, True))
PRODS_N = {(None, '889698100002'): [prod('B0OTRAFICH', caidas=30), prod('B0NUESTRO1', caidas=20, titulo='Figura de vinilo Harry Potter')]}
b = Base(novedades=[novedad(1, nuestro=True, asins=['B0NUESTRO1'])])
k = KeepaFalso(productos=PRODS_N)
ok, res, txt = correr(b, k)
g = b.llamadas('nov_guardar_keepa')[0]
eq('(F) 🔑 una nuestra con su ficha: a Keepa por SU ASIN (no por el EAN), en los cuatro países',
   k.de_producto(), [('ES', 'asin:B0NUESTRO1'), ('IT', 'asin:B0NUESTRO1'), ('FR', 'asin:B0NUESTRO1'), ('DE', 'asin:B0NUESTRO1')])
eq('(F) …se vende con SU ficha (aunque el título no diga «Funko»: la ficha es la nuestra), y va a Amazon',
   (g['p_destino'], sorted({f['asin'] for f in g['p_filas']}), 'ficha dudosa' in g['p_motivo'], ok), ('espera_amazon', ['B0NUESTRO1'], False, True))
eq('(F) …y la caché apunta que se preguntó por ASIN', sorted({tuple(x['codigos']) for x in b.tablas['nov_keepa']}), [('B0NUESTRO1',)])
b = Base(novedades=[novedad(1, nuestro=True, asins=['B0NUESTRO1'])],
         keepa_cache=cache('889698100002', 24, fichas=[nv.ficha_de_keepa(prod('B0OTRAFICH', caidas=30))]))
k = KeepaFalso(productos=PRODS_N)
ok, res, txt = correr(b, k)
eq('(F) 🔴 la caché de su EAN con OTRA ficha no le vale: se pregunta por su ASIN (nunca el ASIN adivinado por EAN)',
   (len(k.de_producto()), sorted({f['asin'] for f in b.llamadas('nov_guardar_keepa')[0]['p_filas']})), (4, ['B0NUESTRO1']))
b = Base(novedades=[novedad(1, nuestro=True, asins=['B0NUESTRO1'])],
         keepa_cache=cache('889698100002', 24, fichas=[nv.ficha_de_keepa(prod('B0OTRAFICH', caidas=30)),
                                                     nv.ficha_de_keepa(prod('B0NUESTRO1', caidas=12))]))
k = KeepaFalso(productos=PRODS_N)
ok, res, txt = correr(b, k)
eq('(F) …y si la caché trae SU ficha (entre otras), vale, solo esa, y 0 tokens',
   (k.llamadas, sorted({f['asin'] for f in b.llamadas('nov_guardar_keepa')[0]['p_filas']}), cierre(b)['v_keepa_cache']), ([], ['B0NUESTRO1'], 1))

# ── (G) KEEPA CAÍDO ─────────────────────────────────────────────────────────────────────
b = Base(novedades=[novedad(1), novedad(2, 'nuevo', ean='889698100019')])
k = KeepaFalso(productos=PRODS, caido=True)
ok, res, txt = correr(b, k)
eq('(G) 🔴 Keepa caído: las dos esperan Keepa, el fallo se apunta y el paso sale en ROJO',
   ([n['estado'] for n in b.tablas['nov_novedad']], cierre(b)['v_espera_fallo'], cierre(b)['estado'], ok, cuadra(cierre(b))),
   (['espera_keepa', 'espera_keepa'], 2, 'hecha', False, True))
eq('(G) …con el motivo en la valoración de la pasada, reintentado una vez (2 intentos del saldo) y sin volver a probar con la segunda',
   ('Keepa falló: ConnectionError' in cierre(b)['motivo'], [q for q, _d, _c in k.llamadas]), (True, ['token', 'token']))
eq('(G) 🔒 la llave de Keepa no sale en ningún mensaje', LLAVE in (cierre(b)['motivo'] + txt + json.dumps(b.rpcs, default=str)), False)
b = Base(novedades=[novedad(1)])
ok, res, txt = correr(b, KeepaFalso(productos=PRODS), llave=None)
eq('(G) sin KEEPA_API_KEY con el interruptor encendido: espera Keepa y rojo, sin lanzar', (ok, 'sin KEEPA_API_KEY' in cierre(b)['motivo']), (False, True))
b = Base(novedades=[novedad(1)], fallan={'nov_cerrar_valoracion'})
ok, res, txt = correr(b, KeepaFalso(productos=PRODS))
eq('(G) si ni siquiera se puede cerrar la valoración: rojo, dicho, y sin lanzar', (ok, 'NOVEDADES_VALORACION_SIN_CERRAR' in txt), (False, True))

# ── (H) LAS PUERTAS, CON EL DATO DE KEEPA, Y EL CUADRE ───────────────────────────────────
PRODS_H = {('ES', '889698100002'): [prod('B0SEVENDE1', caidas=20, fee=350)], ('FR', '889698100002'): [prod('B0SEVENDE1', caidas=4, fee=None)],
           ('ES', '889698100019'): [prod('B0NOVENDE1', caidas=2)], ('IT', '889698100019'): [prod('B0NOVENDE1', caidas=5)],
           ('DE', '889698100026'): [prod('B0VARIAS01', caidas=30), prod('B0VARIAS02', caidas=20)]}
b = Base(novedades=[novedad(1), novedad(2, 'nuevo', ean='889698100019'), novedad(3, 'vuelve', ean='889698100026'),
                    novedad(4, 'nuevo', ean='889698100033')])
k = KeepaFalso(productos=PRODS_H)
ok, res, txt = correr(b, k)
dest = {p['p_novedad']: (p['p_destino'], p['p_decision']) for p in b.llamadas('nov_guardar_keepa')}
eq('(H) se vende → espera Amazon; no se vende → NO SE VENDE; varias fichas sin ninguna en ES → Sin datos; sin ficha → SIN HISTORIAL',
   dest, {'nov-1': ('espera_amazon', None), 'nov-2': ('valorada', 'NO SE VENDE'), 'nov-3': ('valorada', 'Sin datos'),
          'nov-4': ('valorada', 'SIN HISTORIAL')})
filas1 = sorted((v['pais'], v['asin'], v['caidas_30d'], v['vende_aqui'], v.get('fee_fba'), v['ventas_origen'])
                for v in b.tablas['nov_valoracion'] if v['novedad_id'] == 'nov-1')
eq('(H) la que va a Amazon lleva el dato de ventas de cada país donde está su ficha, SIN la tarifa de Keepa (encargo V)',
   filas1, [('ES', 'B0SEVENDE1', 20, True, None, 'keepa'), ('FR', 'B0SEVENDE1', 4, False, None, 'keepa')])
eq('(H) las «varias fichas» y «sin historial» no dejan filas', [v['novedad_id'] for v in b.tablas['nov_valoracion'] if v['novedad_id'] in ('nov-3', 'nov-4')], [])
d = cierre(b)
eq('(H) el flujo que va a la base: 4 en la cola, 4 con Keepa nuevo; 1 no se vende, 1 sin historial, 1 varias fichas, 1 a Amazon; y CUADRA',
   (d['v_en_cola'], d['v_keepa'], d['v_no_se_vende'], d['v_sin_historial'], d['v_varias_fichas'], d['v_a_amazon'], cuadra(d), ok),
   (4, 4, 1, 1, 1, 1, True, True))
eq('(H) …16 peticiones (4 países × 4 novedades), los tokens que dijo Keepa y cuántas fichas traían tarifa',
   (d['keepa_peticiones'], d['keepa_tokens'], d['keepa_fichas'], d['keepa_con_tarifa']), (16, 6, 6, 5))

# ── (I) LA CUENTA DE UNA «LISTA», AL CÉNTIMO ─────────────────────────────────────────────
VALS = [{'novedad_id': 'nov-9', 'pais': 'ES', 'asin': 'B0LISTA001', 'titulo': 'Funko', 'caidas_30d': 12, 'rank': 5000, 'rank_90d': 6000,
         'precio_venta': 20.0, 'canal': 'BB-FBA', 'ref_pct': 15.0, 'fee_fba': 3.6, 'decision': 'Sin datos'},
        {'novedad_id': 'nov-9', 'pais': 'DE', 'asin': 'B0LISTA001', 'titulo': 'Funko', 'caidas_30d': 3, 'rank': 9000, 'rank_90d': 9000,
         'precio_venta': None, 'canal': 'sin precio', 'ref_pct': 15.01, 'fee_fba': None, 'decision': 'Sin datos'}]
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS)
ok, res, txt = correr(b, KeepaFalso())
c = b.llamadas('nov_guardar_cuenta')[0]
es = next(p for p in c['p_paises'] if p['pais'] == 'ES')
de = next(p for p in c['p_paises'] if p['pais'] == 'DE')
# A mano: 20/1,21 − 8 − (20 × 15 % + 3 % de eso) − 3,60 − 0,15 = 16,528926 − 8 − 3,09 − 3,60 − 0,15 = 1,688926.
eq('(I) ES: VALORAR, beneficio 1,6889 = 20/1,21 − 8 − 3,09 − 3,60 − 0,15 (la tarifa tal cual, sin ÷1,21), margen 8,44 %',
   (c['p_decision'], c['p_mejor_pais'], es['decision'], round(es['beneficio'], 4), round(es['margen'], 4), round(es['com_amazon'], 4), es['iva_origen']),
   ('VALORAR', 'ES', 'VALORAR', 1.6889, 0.0844, 3.09, 'asumido 21%'))
eq('(I) DE sin precio: Sin datos, sin margen (ni un número inventado)', (de['decision'], de['margen'], de['beneficio']), ('Sin datos', None, None))
eq('(I) …y el flujo: 1 lista, 1 cuenta', (cierre(b)['v_listas'], cierre(b)['v_cuentas'], cierre(b)['v_cuenta_fallo'], ok), (1, 1, 0, True))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS, productos=[])
ok, res, txt = correr(b, KeepaFalso())
eq('(I) 🔴 sin poder leer el catálogo propio (el IVA de la ficha), la cuenta NO se hace a ciegas: valoración fallida',
   (b.llamadas('nov_guardar_cuenta'), cierre(b)['estado'], ok), ([], 'fallida', False))

# (I) FK76102 (encargo T): con la caja bien puesta en la foto (expositor de 12), la base deja en precio_ahora el precio
#     POR UNIDAD (la caja ÷ 12; nov_novedad.precio_ahora: «quien lea no divide nada»), y la cuenta lo compara con la ficha
#     de UNA unidad («1 of 12»). Precios inventados: 60 el expositor → 5 la unidad; la ficha, a 10.
VALS_EXPO = [{'novedad_id': 'nov-7', 'pais': p, 'asin': 'B0UNIDAD12', 'titulo': 'Funko Mystery Mini: Spongebob 25th Anniversary - 1 of 12',
              'caidas_30d': 20, 'rank': 3000, 'rank_90d': 6000, 'precio_venta': 10.0, 'canal': 'BB-FBA', 'ref_pct': 15.0,
              'fee_fba': 3.0, 'decision': 'Sin datos'} for p in ('ES', 'IT', 'FR', 'DE')]
expo = dict(novedad(7, estado='lista', precio=60.0 / 12, ean='889698761024'), producto_prov='FK76102', es_caja=True, uds_caja=12,
            nombre='SpongeBob SquarePants Mystery Minis Minifiguras 5 cm Expositor 25th Anniversary (12)')
b = Base(novedades=[expo], valoraciones=VALS_EXPO)
ok, res, txt = correr(b, KeepaFalso())
c = b.llamadas('nov_guardar_cuenta')[0]
es = next(p for p in c['p_paises'] if p['pais'] == 'ES')
# A mano: 10/1,21 − 5 − (10 × 15 % + 3 % de eso) − 3,00 − 0,15 = 8,264463 − 5 − 1,545 − 3 − 0,15 = −1,430537.
eq('(I) FK76102: la cuenta compara la UNIDAD de la caja (5 = 60 ÷ 12) con la ficha de una unidad, no el expositor entero',
   (es['pa'], round(es['beneficio'], 4)), (5.0, -1.4305))


# ── (L) LA FICHA TIENE QUE SER DE LA MARCA (encargo T, 30-sep-2026: FK93061 y el casco B08HH6GYRP) ─────────
CASCO = ('Mezzo Retro Fronte Aperto Uomini e Le Donne Helmet DOT Certificato Motociclo di Harley Casco Cavaliere Militare '
         'Aviator Visiera Casco Mezzo con Visiera Occhiali, 55-62CM')
eq('(L) el título es de la marca si lleva «Funko» o «Pop», sin distinguir mayúsculas; el casco, no; sin título, tampoco',
   [nv.ficha_de_la_marca(t) for t in ('Funko Mystery Mini: Spongebob 25th Anniversary - 1 of 12', 'NFL Figura POP! Vinyl : Eagles',
                                      'FUNKO pocket', CASCO, '', None)],
   [True, True, True, False, False, False])
eq('(L) 🔑 (encargo V) como PALABRA entera: «Popcorn», «Lollipop» o «Funkology» NO; «Pop!», «POP-Vinyl», «Funko\'s» y «(Pop)» sí',
   [nv.ficha_de_la_marca(t) for t in ('Popcorn machine 1200W', 'Lollipop chupa chups x50', 'Funkology Vol. 2',
                                      'Pop! Heroes', 'POP-Vinyl Batman', "Funko's Pocket Pop", 'Figura (Pop) Marvel')],
   [False, False, False, True, True, True, True])
nov93061 = dict(novedad(1, 'nuevo', ean='889698930611'), producto_prov='FK93061',
                nombre='NFL Figura POP! Vinyl : Eagles- Saquon Barkley 9 cm')
b = Base(novedades=[nov93061])
k = KeepaFalso(productos={('IT', '889698930611'): [prod('B08HH6GYRP', caidas=0, fee=None, titulo=CASCO)]})
ok, res, txt = correr(b, k)
g = b.llamadas('nov_guardar_keepa')[0]
eq('(L) 🔴 FK93061: el casco de IT no se usa; los cuatro países quedan sin dato y NO sale «NO SE VENDE» (sale SIN HISTORIAL)',
   (g['p_destino'], g['p_decision'], g['p_filas']), ('valorada', 'SIN HISTORIAL', []))
eq('(L) …y el motivo dice qué ficha se apartó y por qué',
   ('IT sin dato (ficha dudosa: Mezzo Retro Fronte Aperto' in g['p_motivo'], 'c_pocas_caidas' in g['p_motivo']), (True, False))
eq('(L) …la respuesta de Keepa queda igual en la caché (la película no se toca; se aparta al usarla)',
   [f['asin'] for x in b.tablas['nov_keepa'] for f in x['fichas']], ['B08HH6GYRP'])
b = Base(novedades=[nov93061])
k = KeepaFalso(productos={('ES', '889698930611'): [prod('B0FUNKO930', caidas=20, titulo='Funko Pop! NFL: Eagles - Saquon Barkley')],
                          ('IT', '889698930611'): [prod('B08HH6GYRP', caidas=0, fee=None, titulo=CASCO)]})
ok, res, txt = correr(b, k)
g = b.llamadas('nov_guardar_keepa')[0]
eq('(L) con la ficha buena en ES y el casco en IT: NO son «varias fichas»; sigue con la de ES, e IT sin dato',
   (g['p_destino'], sorted((f['pais'], f['asin']) for f in g['p_filas']), 'IT sin dato (ficha dudosa' in g['p_motivo']),
   ('espera_amazon', [('ES', 'B0FUNKO930')], True))
b = Base(novedades=[novedad(1)], keepa_cache=cache('889698100002', 1, fichas=[nv.ficha_de_keepa(prod('B08HH6GYRP', caidas=30, titulo=CASCO))]))
k = KeepaFalso(productos=PRODS)
ok, res, txt = correr(b, k)
eq('(L) también con el dato de la caché: la ficha dudosa no se usa, aunque venda (30 caídas)',
   (b.llamadas('nov_guardar_keepa')[0]['p_decision'], len(k.de_producto())), ('SIN HISTORIAL', 0))


# ── (J) LA CUENTA COINCIDE CON LA DEL ESCANEO PRO ────────────────────────────────────────
def cotejar(fila):
    """None si la cuenta de las novedades da lo mismo que guardó el Escaneo PRO (escaner2_resultado_pais); si no, por qué."""
    c = nv.cuenta_de_pais(fila['pais'], fila, fila['pa'], '0000000000000', M)
    if (c['precio_venta'], c['canal'], c['decision']) != (fila['precio_venta'], fila['canal'], fila['decision']):
        return 'precio/canal/decisión: %r frente a %r' % ((c['precio_venta'], c['canal'], c['decision']),
                                                         (fila['precio_venta'], fila['canal'], fila['decision']))
    if abs(c['iva'] - fila['iva']) > 1e-9:
        return 'iva %r frente a %r' % (c['iva'], fila['iva'])
    for k2, tol in (('com_amazon', CENTIMO), ('beneficio', CENTIMO), ('roi', CENTIMO / 100), ('margen', CENTIMO / 100)):
        if (c[k2] is None) != (fila[k2] is None) or (c[k2] is not None and abs(c[k2] - fila[k2]) >= tol):
            return '%s %r frente a %r' % (k2, c[k2], fila[k2])
    return None


def fabricada(pais, precio, canal, ref, fee, pa):
    iva = M.iva_por_pais('0000000000000')[pais]
    r = M.calc_rentabilidad(precio, pa, ref, fee, iva, almacen=M.ALMACEN, com_digitales=M.COM_DIGITALES, isd=M.ISD_PAIS[pais])
    return {'pais': pais, 'precio_venta': precio, 'canal': canal, 'ref_pct': ref, 'fee_fba': fee, 'iva': iva, 'pa': pa,
            'com_amazon': r['com_amazon'], 'beneficio': r['beneficio'], 'roi': r['roi'], 'margen': r['margen'],
            'decision': M.decision_de(r['margen'])}


FABRICADAS = [fabricada('ES', 24.0, 'BB-FBA', 15.0, 3.51, 8.0), fabricada('FR', 18.0, 'BB-FBM', 15.0, 4.37, 6.0),
              fabricada('IT', 16.0, 'SIN BB', 15.0, 3.64, 8.0), fabricada('DE', 21.0, 'BB-FBM', 15.0, 3.45, 9.0)]
eq('(J) filas fabricadas con la fórmula del viejo (ES, FR con el recargo sobre la FBA, IT, DE): todas cuadran',
   [cotejar(x) for x in FABRICADAS], [None, None, None, None])
mala = dict(FABRICADAS[1], beneficio=FABRICADAS[1]['beneficio'] + 0.01)
eq('(J) …y una fila MALA (un céntimo de más) se caza: el cotejador no dice «cuadra» a todo', cotejar(mala) is not None, True)
eq('(J) …y una FR calculada SIN el recargo sobre la FBA se caza (el ISD de Francia cuenta)',
   cotejar(dict(FABRICADAS[1], **{k2: M.calc_rentabilidad(18.0, 6.0, 15.0, 4.37, 0.2, almacen=0.15, com_digitales=1.03,
                                                         isd=M.ISD_PAIS['ES'])[k2] for k2 in ('com_amazon', 'beneficio', 'roi', 'margen')})) is not None, True)
RUTA_REALES = os.environ.get('NOV_CASOS_REALES')
if RUTA_REALES:
    with open(RUTA_REALES, encoding='utf-8') as fh:
        reales = json.load(fh)
    malos = [(i, cotejar(x)) for i, x in enumerate(reales) if cotejar(x)]
    eq('(J) 🔑 CASOS REALES del Escaneo PRO (%d filas de escaner2_resultado_pais): al menos 5, y la cuenta de las novedades '
       'da lo mismo AL CÉNTIMO en todas (decisión, precio, canal, IVA, comisión, beneficio, ROI y margen)' % len(reales),
       (len(reales) >= 5, sorted({x['pais'] for x in reales}), malos), (True, ['DE', 'ES', 'FR', 'IT'], []))
else:
    print('-- (J) casos reales: no en este entorno (el repo es público y el coste de HEO no se publica); los coteja el CI de la '
          'v2 (privado) con NOV_CASOS_REALES')

# ── (X) EL EXCEL DE NOVEDADES Y LAS CUENTAS SUELTAS (encargo V) ────────────────────────────
import io as _io
from openpyxl import load_workbook

VALS_COMPRA = [
    {'novedad_id': 'nov-9', 'pais': 'ES', 'asin': 'B0LISTA001', 'titulo': 'Funko Pop! Figura', 'caidas_30d': 12, 'rank': 5000,
     'rank_90d': 6000, 'precio_venta': 30.0, 'canal': 'BB-FBA', 'ref_pct': 15.0, 'fee_fba': 3.6, 'decision': 'Sin datos',
     'amazon_estado': 'dato', 'error_amazon': None},
    {'novedad_id': 'nov-9', 'pais': 'DE', 'asin': 'B0LISTA001', 'titulo': 'Funko Pop! Figur', 'caidas_30d': 9, 'rank': 7000,
     'rank_90d': 8000, 'precio_venta': 31.0, 'canal': 'BB-FBM', 'ref_pct': None, 'fee_fba': None, 'decision': 'Sin datos',
     'amazon_estado': 'no_dado', 'error_amazon': 'tarifas: ServerError · InternalError'},
    {'novedad_id': 'nov-9', 'pais': 'FR', 'asin': 'B0LISTA001', 'titulo': 'Funko Pop! Figurine', 'caidas_30d': 2, 'rank': 90000,
     'rank_90d': 90000, 'precio_venta': None, 'canal': None, 'ref_pct': None, 'fee_fba': None, 'decision': 'Sin datos',
     'amazon_estado': 'no_se_vende', 'error_amazon': 'ofertas: HTTP 404 · NotFound: Item not found'}]
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA)
ok, res, txt = correr(b, KeepaFalso())
c = b.llamadas('nov_guardar_cuenta')[0]
eq('(X) la novedad sale COMPRAR en ES (30 € de Amazon, su tarifa y su comisión); DE sin la tarifa y FR «no se vende aquí»: Sin datos',
   (c['p_decision'], c['p_mejor_pais'], sorted((p['pais'], p['decision']) for p in c['p_paises'])),
   ('COMPRAR', 'ES', [('DE', 'Sin datos'), ('ES', 'COMPRAR'), ('FR', 'Sin datos')]))
eq('(X) 🔑 con un COMPRAR: UN Excel al bucket escaner2, en heo/novedades/<día>/, con el nombre de la hora de Madrid (20:05)',
   [(cubo, ruta, op['content-type']) for cubo, ruta, _c, op in b.subidos],
   [('escaner2', 'heo/novedades/2026-09-29/Novedades_HEO_Funko_2026-09-29_2005.xlsx', nv.XLSX)])
fila_x = b.tablas['nov_excel'][0]
eq('(X) …y su fila en nov_excel (lo que lee la biblioteca de la v2): de la pasada, con el run, 1 valorada, 1 COMPRAR',
   (fila_x['origen'], fila_x['pasada_id'], fila_x['run_id'], fila_x['ruta_excel'], fila_x['n_novedades'], fila_x['n_comprar'],
    fila_x['n_valorar'], fila_x['novedades'], ok),
   ('pasada', 'PASADA-1', 36700000001, 'heo/novedades/2026-09-29/Novedades_HEO_Funko_2026-09-29_2005.xlsx', 1, 1, 0, ['nov-9'], True))
wb = load_workbook(_io.BytesIO(b.subidos[0][2]))
analisis = [list(r) for r in wb['Análisis'].iter_rows(values_only=True)]
eq('(X) es el Excel del escáner nuevo: las hojas del viejo delante (Análisis con la columna «Ventas» del 28-sep) y «Novedades» al final',
   (wb.sheetnames[0], wb.sheetnames[-1], 'Ventas' in analisis[0], any('889698100002' in str(x) for r in analisis[1:] for x in r)),
   ('Análisis', 'Novedades', True, True))
hoja = [list(r) for r in wb['Novedades'].iter_rows(values_only=True)]
cab = hoja[0]
eq('(X) la hoja «Novedades» dice el origen de cada uno de los 4 países (sin cifra inventada donde no la hay)',
   {p: hoja[1][cab.index('Amazon ' + p)] for p in nv.PAISES},
   {'ES': 'Amazon', 'IT': 'no está en Amazon IT', 'FR': 'no está en Amazon FR',
    'DE': 'Amazon no ha dado la tarifa (tarifas: ServerError · InternalError)'})
eq('(X) …con el motivo de la novedad y sus dos precios por unidad', (hoja[1][cab.index('Novedad')], hoja[1][cab.index('Precio ahora (ud)')],
                                                                    hoja[1][cab.index('Decisión')]), ('baja_precio', 8.0, 'COMPRAR'))

b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS)
ok, res, txt = correr(b, KeepaFalso())
eq('(X) sin ningún COMPRAR (la de (I) sale VALORAR): NI Excel ni fila, verde, y lo dice',
   (b.subidos, b.tablas.get('nov_excel', []), ok, 'ninguna COMPRAR' in txt), ([], [], True, True))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA, fallan={'storage'})
ok, res, txt = correr(b, KeepaFalso())
eq('(X) 🔴 si el Excel no se puede subir: sin fila en nov_excel, y ROJO con el motivo (la cuenta sí queda hecha)',
   (b.tablas.get('nov_excel', []), ok, 'el Excel de novedades no se pudo dejar' in cierre(b)['motivo'], len(b.llamadas('nov_guardar_cuenta'))),
   ([], False, True, 1))
b = Base(novedades=[dict(novedad(9, estado='lista', nuestro=True, asins=['B0LISTA001']))], valoraciones=VALS_COMPRA)
ok, res, txt = correr(b, KeepaFalso())
eq('(X) una NUESTRA lista también se cuenta (y sale en el Excel, marcada)',
   (len(b.llamadas('nov_guardar_cuenta')), [list(r) for r in load_workbook(_io.BytesIO(b.subidos[0][2]))['Novedades'].iter_rows(values_only=True)][1][6]),
   (1, 'sí'))


def cuentas_sueltas(base, keepa=None, env=None):
    salida = []
    ok_, res_ = nv.solo_cuentas(base, run_id='36700000002', ahora=lambda: AHORA + timedelta(minutes=22),
                                imprimir=lambda *a, **k: salida.append(' '.join(str(x) for x in a)),
                                keepa_llave=LLAVE, http=keepa or KeepaFalso(), dormir=lambda s: None,
                                env=env if env is not None else {}, post=post_falso)
    return ok_, res_, '\n'.join(salida)


b = Base(valorar=False, novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA)
ok, res, txt = cuentas_sueltas(b)
eq('(X) cuentas sueltas con el interruptor APAGADO: nada (ni cuenta, ni Excel), verde, y lo dice',
   (b.rpcs, b.subidos, ok, 'APAGADO' in txt), ([], [], True, True))
b = Base(novedades=[novedad(9, estado='lista'), novedad(3, 'nuevo', ean='889698100033')], valoraciones=VALS_COMPRA)
ok, res, txt = cuentas_sueltas(b)
eq('(X) 🔑 cuentas sueltas (y 27): SOLO la cuenta de las «lista» y el Excel: ni Keepa, ni la cola, ni nov_cerrar_valoracion',
   ([n for n, _p in b.rpcs], [op for op in b.ops if op[0] in ('nov_cola', 'nov_keepa')], ok, res['cuentas'], res['comprar']),
   (['nov_guardar_cuenta'], [], True, 1, 1))
eq('(X) …su Excel, a las 20:27 y de origen «cuentas», sin pasada (el reloj de la prueba; el disparo real es a y 40)', (b.subidos[0][1], b.tablas['nov_excel'][0]['origen'],
                                                                     b.tablas['nov_excel'][0]['pasada_id'], b.tablas['nov_excel'][0]['run_id']),
   ('heo/novedades/2026-09-29/Novedades_HEO_Funko_2026-09-29_2027.xlsx', 'cuentas', None, 36700000002))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA, fallan={'nov_guardar_cuenta'})
ok, res, txt = cuentas_sueltas(b)
eq('(X) 🔴 cuentas sueltas con una cuenta que falla: ROJO, dicho, y sin Excel (no hay COMPRAR guardado)',
   (ok, 'la cuenta de nov-9 falló' in txt, b.subidos), (False, True, []))

# ── (R) EL RESPALDO DE KEEPA Y EL ESCALÓN DE LOS 20 € (añadido 2) ───────────────────────────
def prod_bb(asin, fee=410, ref=15.0, caja=2100, nuevo=1990, fba=True):
    """Un producto de Keepa pedido con buybox: stats.current con «nuevo» (1) y la caja de compra (18), en céntimos."""
    cur = [-1] * 19
    cur[1], cur[18] = (nuevo if nuevo is not None else -1), (caja if caja is not None else -1)
    p = {'asin': asin, 'title': 'Funko Pop! Figura', 'referralFeePercentage': ref, 'stats': {'current': cur, 'buyBoxIsFBA': fba}}
    if fee is not None:
        p['fbaFees'] = {'pickAndPackFee': fee}
    return p


rd = nv.respaldo_de_producto
eq('(R) del mismo lado de 20 € (Keepa a 21,00, Amazon a 21,50): de Keepa, su logística y su %, con el PRECIO DE AMAZON',
   rd(prod_bb('B0R1'), 21.5, 'BB-FBA'),
   {'estado': 'keepa', 'precio_venta': 21.5, 'canal': 'BB-FBA', 'ref_pct': 15.0, 'fee_fba': 4.1, 'keepa_precio_base': 21.0})
eq('(R) 🔴 a lados distintos (Keepa a 18,99, Amazon a 21,50): pendiente, CAMBIA DE ESCALÓN, con los dos precios',
   rd(prod_bb('B0R1', caja=1899), 21.5, 'BB-FBA'),
   {'estado': 'repedir', 'tipo': 'escalon', 'motivo': 'cambia de escalón: Keepa calculó su tarifa a 18,99 € y el precio es 21,50 €'})
eq('(R) 🔴 20,00 € exactos pagan la alta: Keepa a 20,00 y Amazon a 19,99 cruzan', rd(prod_bb('B0R1', caja=2000), 19.99, 'SIN BB')['estado'], 'repedir')
eq('(R) sin caja de compra, el precio base es «nuevo»', rd(prod_bb('B0R1', caja=None, nuevo=1850), 17.9, 'SIN BB')['keepa_precio_base'], 18.5)
eq('(R) 🔴 sin ningún precio actual en Keepa no se sabe con qué precio calculó: se trata como CRUCE',
   rd(prod_bb('B0R1', caja=None, nuevo=None), 17.9, 'SIN BB')['motivo'],
   'cambia de escalón: no se sabe con qué precio calculó Keepa su tarifa (sin precio actual en Keepa)')
eq('(R) si Amazon no dio precio: el de Keepa, como el viejo (la caja de compra, con su logística; si no, «nuevo»)',
   [(x['precio_venta'], x['canal']) for x in (rd(prod_bb('B0R1'), None, None), rd(prod_bb('B0R1', fba=False), None, None),
                                               rd(prod_bb('B0R1', caja=None), None, None))],
   [(21.0, 'BB-FBA'), (21.0, 'BB-FBM'), (19.9, 'SIN BB')])
eq('(R) Keepa sin la logística, o sin el producto: pendiente (Keepa no lo tiene), sin cifra',
   [rd(prod_bb('B0R1', fee=None), 21.5, 'BB-FBA')['tipo'], rd(prod_bb('B0R1', fee=0), 21.5, 'BB-FBA')['tipo'], rd(None, 21.5, 'BB-FBA')['tipo']],
   ['keepa_sin_dato', 'keepa_sin_dato', 'keepa_sin_dato'])

VALS_FALLA = [dict(VALS_COMPRA[0]),
              dict(VALS_COMPRA[1], pais='DE', amazon_estado='falta_amazon', precio_venta=31.0, canal='BB-FBM', ref_pct=None, fee_fba=None,
                   error_amazon='tarifas: ServerError · InternalError (igual en los 4 reintento(s))'),
              dict(VALS_COMPRA[2], pais='IT', amazon_estado='falta_amazon', precio_venta=18.5, canal='SIN BB', ref_pct=None, fee_fba=None,
                   error_amazon='tarifas: ServerError', caidas_30d=12)]
KEEPA_R = {(None, 'x1'): [prod_bb('B0LISTA001', fee=405, ref=15.0, caja=3050)]}
TELEGRAM.clear()
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_FALLA)
k = KeepaFalso(productos={('DE', 'x'): [prod_bb('B0LISTA001', fee=405, ref=15.0, caja=3050)],
                          ('IT', 'x'): [prod_bb('B0LISTA001', fee=364, ref=15.0, caja=1990, nuevo=1990)]})
ok, res, txt = correr(b, k, env={'TELEGRAM_TOKEN': 'TOKEN-TG-DE-MENTIRA', 'TELEGRAM_CHAT_ID': '42'})
c = b.llamadas('nov_guardar_cuenta')[0]
por_pais = {x['pais']: x for x in c['p_paises']}
eq('(R) 🔑 los dos países en que Amazon falló, a Keepa EN ESE MOMENTO: por ASIN, con buybox (3 tokens cada uno), y nada a la caché',
   (sorted(k.de_producto()), cierre(b)['keepa_tokens'], len(b.tablas['nov_keepa'])),
   ([('DE', 'asin:B0LISTA001+bb'), ('IT', 'asin:B0LISTA001+bb')], 6, 0))
eq('(R) DE: de Keepa, con el precio de Amazon (31) y su precio base (30,50) del mismo lado de 20 €',
   por_pais['DE']['respaldo'], {'estado': 'keepa', 'precio_venta': 31.0, 'canal': 'BB-FBM', 'ref_pct': 15.0, 'fee_fba': 4.05, 'keepa_precio_base': 30.5})
eq('(R) IT: Keepa calculó a 19,90 y Amazon vende a 18,50: del mismo lado (los dos por debajo de 20), de Keepa',
   (por_pais['IT']['respaldo']['estado'], por_pais['IT']['respaldo']['keepa_precio_base']), ('keepa', 19.9))
eq('(R) …y los dos países CUENTAN (tienen cifra), con la fórmula de siempre', (por_pais['DE']['decision'] != 'Sin datos', por_pais['IT']['decision'] != 'Sin datos',
                                                                             por_pais['ES']['decision'], 'respaldo' in por_pais['ES']),
   (True, True, 'COMPRAR', False))
hoja = [list(r) for r in load_workbook(_io.BytesIO(b.subidos[0][2]))['Novedades'].iter_rows(values_only=True)]
eq('(R) el Excel marca cada país con su origen', {p: hoja[1][hoja[0].index('Amazon ' + p)] for p in nv.PAISES},
   {'ES': 'Amazon', 'IT': 'de Keepa (Amazon falló)', 'FR': 'no está en Amazon FR', 'DE': 'de Keepa (Amazon falló)'})
eq('(T) 🔑 con COMPRAR, el Telegram con el formato del viejo: 🟢, una línea por COMPRAR (nombre, margen, precio, país)',
   (len(TELEGRAM), TELEGRAM[0][1]['text'].split('\n')[0], TELEGRAM[0][1]['text'].split('\n')[1].startswith('• Funko Pop! Figura 9 — '),
    TELEGRAM[0][1]['parse_mode'], TELEGRAM[0][1]['chat_id']),
   (1, '🟢 <b>Novedades HEO Funko</b>: 1 para COMPRAR', True, 'HTML', '42'))
eq('(T) 🔒 la llave de Telegram no sale en el log', 'TOKEN-TG-DE-MENTIRA' in txt, False)

TELEGRAM.clear()
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=[dict(VALS_FALLA[0], precio_venta=12.0), VALS_FALLA[1]])
k = KeepaFalso(productos={('DE', 'x'): [prod_bb('B0LISTA001', fee=405, ref=15.0, caja=1899)]})
ok, res, txt = correr(b, k, env={'TELEGRAM_TOKEN': 'T', 'TELEGRAM_CHAT_ID': '42'})
de = next(x for x in b.llamadas('nov_guardar_cuenta')[0]['p_paises'] if x['pais'] == 'DE')
eq('(R) 🔴 DE cruza el escalón (Keepa a 18,99, Amazon a 31): pendiente con su motivo, y ese país sin cifra',
   (de['respaldo'], de['decision']),
   ({'estado': 'repedir', 'motivo': 'cambia de escalón: Keepa calculó su tarifa a 18,99 € y el precio es 31,00 €'}, 'Sin datos'))
eq('(T) 🔴 incompleto y SIN COMPRAR: el Telegram se manda igual, en rojo, diciendo que falta un país',
   (len(TELEGRAM), TELEGRAM[0][1]['text'].split('\n')[0], 'NOVEDADES INCOMPLETAS</b>: 1 país(es) pendiente(s): cambia de escalón' in TELEGRAM[0][1]['text']),
   (1, '🔴 <b>Novedades HEO Funko</b>: 0 para COMPRAR', True))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_FALLA)
ok, res, txt = correr(b, KeepaFalso(productos={}), llave=None)
eq('(R) sin KEEPA_API_KEY: los dos países pendientes (repedir), la cuenta hecha con lo que hay, y verde (se vuelve a pedir)',
   ([x['respaldo']['estado'] for x in b.llamadas('nov_guardar_cuenta')[0]['p_paises'] if 'respaldo' in x], len(b.llamadas('nov_guardar_cuenta'))),
   (['repedir', 'repedir'], 1))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_FALLA)
ok, res, txt = cuentas_sueltas(b, KeepaFalso(saldo=22, productos={}))
eq('(R) sin saldo por encima de la reserva (22 − 20 < 3): ni una petición, pendientes, y se dice',
   ([x['respaldo']['motivo'] for x in b.llamadas('nov_guardar_cuenta')[0]['p_paises'] if 'respaldo' in x], res['keepa_peticiones'], res['incompletos']),
   (['Keepa sin saldo: quedaban 22 tokens y la reserva es 20'] * 2, 0, 2))

# ── (T) EL TELEGRAM, PURO ────────────────────────────────────────────────────────────────
def v_compra(i, margen=0.25, precio=19.9, pais='ES', origen='dato'):
    return {'nov': {'nombre': 'Funko Pop! Figura con un nombre larguísimo número %02d que se corta' % i}, 'foto': {},
            'decision': 'COMPRAR', 'mejor': pais, 'amazon': {pais: (origen, None)},
            'r': {'paises': {pais: {'margen': margen, 'precio_venta': precio}}}}


m = nv.mensaje_telegram([v_compra(1, pais='DE', origen='keepa')])
eq('(T) la línea: nombre en 45 caracteres, margen, precio, país y «de Keepa» si ese país salió del respaldo',
   m.split('\n')[1], '• Funko Pop! Figura con un nombre larguísimo nú — 25% — 19.90€ (DE) de Keepa')
m = nv.mensaje_telegram([v_compra(i) for i in range(25)])
eq('(T) tope de 20 líneas y «…y X más»', (len(m.split('\n')), m.split('\n')[-1]), (22, '…y 5 más (mira el Excel de la Biblioteca).'))
eq('(T) sin COMPRAR, sin avalancha y completo: NO se manda', nv.mensaje_telegram([dict(v_compra(1), decision='VALORAR')]), None)
eq('(T) avalancha sin COMPRAR: se manda, con el aviso tal cual', nv.mensaje_telegram([], avalancha=150),
   '⚠️ <b>Avalancha</b>: 150 cambios en HEO Funko — lanza un Escaneo PRO')
m = nv.mensaje_telegram([], incompletos=[{'tipo': 'reserva'}, {'tipo': 'keepa_sin_dato'}])
eq('(T) incompleto por la reserva de Keepa y por un país sin dato: rojo y lo dice', (m.split('\n')[0].startswith('🔴'),
   '1 país(es) sin dato (Amazon falló y Keepa tampoco) y 1 consulta(s) que Keepa no hizo por la reserva' in m), (True, True))
salida_tg = []
eq('(T) sin claves: no manda, no falla y lo dice', (nv.enviar_telegram('x', env={}, post=post_falso, imprimir=lambda *a, **k: salida_tg.append(a[0])),
                                                   'sin claves' in salida_tg[-1]), (False, True))


def post_roto(url, data, timeout):
    raise ConnectionError('Max retries exceeded with url: /botTOKEN-SECRETO/sendMessage')


eq('(T) 🔒 si Telegram falla: la corrida sigue, lo dice, y la llave no sale',
   (nv.enviar_telegram('x', env={'TELEGRAM_TOKEN': 'TOKEN-SECRETO', 'TELEGRAM_CHAT_ID': '1'}, post=post_roto,
                       imprimir=lambda *a, **k: salida_tg.append(a[0])), 'no se envió' in salida_tg[-1], 'TOKEN-SECRETO' in salida_tg[-1]),
   (False, True, False))

# ── (A) LA AVALANCHA ─────────────────────────────────────────────────────────────────────
TELEGRAM.clear()
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA)
ok, res, txt = correr(b, KeepaFalso(), novedades_pasada=150, env={'TELEGRAM_TOKEN': 'T', 'TELEGRAM_CHAT_ID': '42'})
wb = load_workbook(_io.BytesIO(b.subidos[0][2]))
eq('(A) más de 100 novedades: el Excel se abre en «Novedades» con el aviso arriba, y el run y el Telegram lo dicen',
   (wb.active.title, wb['Novedades']['A1'].value, 'AVALANCHA: 150 cambios' in txt,
    '⚠️ <b>Avalancha</b>: 150 cambios en HEO Funko — lanza un Escaneo PRO' in TELEGRAM[0][1]['text']),
   ('Novedades', 'Avalancha: 150 cambios — lanza un Escaneo PRO', True, True))
b = Base(novedades=[novedad(9, estado='lista')], valoraciones=VALS_COMPRA)
ok, res, txt = correr(b, KeepaFalso(), novedades_pasada=100)
eq('(A) con 100 justas no es avalancha', (load_workbook(_io.BytesIO(b.subidos[0][2])).active.title, 'AVALANCHA' in txt), ('Análisis', False))

# ── (K) EL MÓDULO, POR ESTRUCTURA ────────────────────────────────────────────────────────
AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, 'escaner2_novedades.py'), encoding='utf-8') as fh:
    arbol = ast.parse(fh.read())
tablas, funciones, escrituras = set(), set(), set()
for nodo in ast.walk(arbol):
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in ('table', 'rpc') and nodo.args \
            and isinstance(nodo.args[0], ast.Constant):
        (tablas if nodo.func.attr == 'table' else funciones).add(nodo.args[0].value)
    if isinstance(nodo, ast.Attribute) and nodo.attr in ('insert', 'update', 'upsert', 'delete') and isinstance(nodo.value, ast.Call) \
            and isinstance(nodo.value.func, ast.Attribute) and nodo.value.func.attr == 'table':
        escrituras.add((nodo.value.args[0].value if nodo.value.args and isinstance(nodo.value.args[0], ast.Constant) else '?', nodo.attr))
leidas = {c.value for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('_todas', '_en_trozos')
          for c in n.args[1:2] if isinstance(c, ast.Constant)}
eq('(K) lee lo suyo: parámetros, la cola, las novedades y sus filas, la caché, la foto de HEO, productos y el Escaneo PRO',
   sorted(tablas | leidas), sorted({'nov_parametros', 'escaner2_parametros', 'nov_keepa', 'escaner2_cruce', 'nov_cola', 'nov_novedad',
                                    'productos', 'disp_estado', 'nov_valoracion', 'escaner2_foto', 'escaner2_resultado_ean',
                                    'escaner2_resultado_pais', 'nov_excel'}))
eq('(K) 🔒 y solo ESCRIBE insertando en nov_keepa (la película de Keepa) y en nov_excel (el Excel, encargo V): ni update, ni upsert, ni delete',
   escrituras, {('nov_keepa', 'insert'), ('nov_excel', 'insert')})
_fuente_sin_comentarios = '\n'.join(l.split('#', 1)[0] for l in open(os.path.join(AQUI, 'escaner2_novedades.py'), encoding='utf-8').read().split('\n'))
eq('(K) 🔒 (encargo V) el Excel NO va a escaner_resultados ni al buzón `informes` del viejo (sus Excel los leen otros programas)',
   ['escaner_resultados' in _fuente_sin_comentarios.split('"""', 2)[-1], "'informes'" in _fuente_sin_comentarios], [False, False])
eq('(K) …el resto, por las funciones de la base: guardar Keepa, guardar la cuenta y cerrar', sorted(funciones),
   ['nov_cerrar_valoracion', 'nov_guardar_cuenta', 'nov_guardar_keepa'])
eq('(K) 🔒 ni Amazon ni el escáner viejo: ni sellingpartnerapi, ni escaner_memoria, ni una llave de disparo',
   any(s in open(os.path.join(AQUI, 'escaner2_novedades.py'), encoding='utf-8').read()
       for s in ('sellingpartnerapi', 'escaner_memoria', 'dispatches', 'GH_TOKEN')), False)

print()
if fallos:
    print('ROJO: %d fallo(s): %s' % (len(fallos), '; '.join(fallos)))
    sys.exit(1)
print('VERDE: la valoración de las novedades respeta el interruptor, la reserva de Keepa, la caché y el Escaneo PRO, y '
      'cuenta con el código del Escaneo PRO.')
