#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESCANER 2 · EL BARRIDO DE HEO (pasos 1 y 2 del encargo B, 24-sep-2026) — EN SOMBRA.

Lo lanza el boton «Barrer HEO» de la v2 (moloka-app-v2, /escaner/barrido-heo) por el
workflow escaner2-heo-barrido.yml. Aqui viven las credenciales de HEO.

QUE HACE, EN ORDEN:
  1. abre una pasada en `escaner2_pasada` (estado 'descargando') con el id del run;
  2. lee la regla HEO de `reglas_director` (SOLO LECTURA) y saca de director_heo_prep.py SU
     filtro (`_quiere`), sin ejecutar aquel fichero;
  3. baja el catalogo con `descargar_heo.descargar_catalogo_heo(con_chase=True)`, la MISMA
     funcion que usa el director;
  4. construye la foto con `escaner2_motor.construir_foto` (reglas de EAN/chase/caja del
     escaner viejo, sacadas de su fichero) y la guarda en `escaner2_foto`. 🔴 EL CUADRE EMPIEZA
     EN EL CATALOGO CRUDO (Fernando, 24-sep-2026): cada producto que devuelve HEO sale por una
     PUERTA PREVIA (Funko chase, sin GTIN, no disponible, marca fuera, estado no servible, chase
     suelto, EAN raro, duplicado) o entra en la foto, y crudo = previas + foto o la pasada
     queda fallida. Los recuentos van a `escaner2_pasada.p_*`; las listas, a `escaner2_apartado`;
  5. deja en Storage (bucket `escaner2`, cerrado) la lista de EAN para el Visualizador, uno por
     linea: `heo/<pasada>/eans.txt` y, si pasa de una tanda, `eans_1.txt`, `eans_2.txt`…;
  6. cierra la pasada en 'esperando_csv' con sus cuentas, o en 'fallida' con el motivo.

🔒 NO TOCA NADA DEL ESCANER VIEJO: ni `reglas_director` (se lee), ni `escaner_chase_asin` (el
   director la refresca con los Funko chase; aqui solo se APARTAN y se cuentan), ni
   `escaner_memoria`, ni `escaner_resultados`, ni el buzon `informes/escaner_heo/`. Cero tokens
   de Keepa: esto no habla con Keepa ni con Amazon.
🔒 LA LLAVE DE SERVICIO, O NO SE CORRE (la regla del #292, ver test_escaner_llave_servicio.py):
   corre desatendido y escribe en tablas cerradas; sin la llave, aborta antes de nacer ningun
   cliente de red.
"""
import io
import os
import re
import sys
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone


def abortar(motivo):
    """Un run que no hace su trabajo sale en ROJO y con una linea que se puede buscar."""
    print(f"ESCANER2_NO_EJECUTADO: {motivo}")
    sys.exit(1)


_llave_svc = os.environ.get('SUPABASE_SERVICE_KEY')
if not _llave_svc:
    abortar('sin llave de servicio')
if not (os.environ.get('HEO_USER') and os.environ.get('HEO_PASS')):
    abortar('sin credenciales de HEO (HEO_USER y HEO_PASS)')

from supabase import create_client  # noqa: E402

import escaner2_motor as e2  # noqa: E402

BUCKET = 'escaner2'
LOTE = 500
RUN_ID = os.environ.get('GITHUB_RUN_ID')

sb = create_client(os.environ['SUPABASE_URL'], _llave_svc)


class _Eco(io.TextIOBase):
    """Deja pasar lo que se imprime Y se lo guarda: `descargar_catalogo_heo` dice cuantos
    productos le dio HEO y cuantos tiro sin GTIN SOLO en el log, y aqui se rescatan los dos
    numeros sin tocar aquella funcion."""

    def __init__(self, destino):
        self.destino, self.trozos = destino, []

    def write(self, s):
        self.destino.write(s)
        self.trozos.append(s)
        return len(s)

    def flush(self):
        self.destino.flush()


class FalloPasada(RuntimeError):
    """Un fallo que trae los recuentos que se llegaron a hacer, para guardarlos en la pasada
    fallida (el check de cuadre de la base solo se aplica a 'esperando_csv')."""

    def __init__(self, motivo, recuentos):
        super().__init__(motivo)
        self.recuentos = recuentos


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _en_lotes(tabla, filas):
    for i in range(0, len(filas), LOTE):
        sb.table(tabla).insert(filas[i:i + LOTE]).execute()


def _contar(tabla, **filtros):
    q = sb.table(tabla).select('id', count='exact')
    for k, v in filtros.items():
        q = q.eq(k, v)
    return q.limit(1).execute().count


def main():
    pasada = str(uuid.uuid4())
    sb.table('escaner2_pasada').insert({
        'id': pasada, 'proveedor': e2.PROVEEDOR, 'estado': 'descargando',
        'run_id': int(RUN_ID) if (RUN_ID or '').isdigit() else None,
    }).execute()
    print(f">>> Pasada {pasada} abierta (descargando).", flush=True)
    try:
        cierre = barrer(pasada)
        # 🔒 El cierre va DENTRO del try: si la base lo rechaza (p. ej. el cuadre previo no
        #    cumple su check), la pasada queda 'fallida' con el motivo, no colgada en
        #    'descargando' para siempre.
        sb.table('escaner2_pasada').update(cierre).eq('id', pasada).execute()
    except Exception as ex:
        motivo = f'{type(ex).__name__}: {ex}'[:1000]
        sb.table('escaner2_pasada').update(dict({'estado': 'fallida', 'motivo_fallo': motivo,
                                                 'terminada_en': _ahora()},
                                                **getattr(ex, 'recuentos', {}))).eq('id', pasada).execute()
        abortar(f'pasada {pasada} fallida: {motivo}')
    print(f">>> PASADA LISTA: {cierre['n_foto']} en la foto, {cierre['n_eans_lista']} códigos para el "
          f"Visualizador en {cierre['n_tandas']} tanda(s). Esperando los CSV de Keepa.", flush=True)


def barrer(pasada):
    # 1 · La regla HEO (solo lectura) y el filtro del director, el suyo.
    res = sb.table('reglas_director').select('*').eq('proveedor', e2.PROVEEDOR).limit(1).execute()
    regla = (res.data or [None])[0]
    if not regla:
        raise RuntimeError('no hay fila HEO en reglas_director: sin ella no se sabe qué marcas barrer')
    quiere, info = e2.cargar_filtro_director(regla)
    M = e2.cargar_motor()
    tanda = e2.tanda_visualizador()
    print(f">>> Regla HEO (activa={regla.get('activo')}): marcas {info['marcas_reales']} | "
          f"ofertas {info['quiere_ofertas']} | tanda del Visualizador {tanda}", flush=True)

    # 2 · El catalogo, con la MISMA funcion que el director (import tardio: lee HEO_USER al cargar).
    from descargar_heo import descargar_catalogo_heo
    eco = _Eco(sys.stdout)
    with redirect_stdout(eco):
        filas, chase = descargar_catalogo_heo(con_chase=True)
    log = ''.join(eco.trozos)
    m = re.search(r'Cruzando: (\d+) productos', log)
    n_crudo = int(m.group(1)) if m else None
    m = re.search(r'descartadas (\d+) sin GTIN', log)
    n_sin_gtin = int(m.group(1)) if m else None
    m = re.search(r'catalog/products: (\d+) items', log)
    n_declarado = int(m.group(1)) if m else None

    # 3 · La foto, y el cuadre desde el catalogo crudo. Sin uno de los dos numeros del log no se
    #     puede afirmar que cuadra: la pasada falla diciendo cual falta (NULL no es cero).
    foto, apartados, cuentas = e2.construir_foto(filas, chase, quiere, M, n_crudo=n_crudo, n_sin_gtin=n_sin_gtin,
                                                 n_declarado=n_declarado)
    previas = cuentas['previas']
    print(f">>> CUADRE PREVIO [HEO]: catálogo crudo {n_crudo} = "
          + ' + '.join(f'{p} {previas[p]}' for p in e2.PUERTAS_PREVIAS)
          + f" + foto {cuentas['n_foto']} → {'CUADRA' if cuentas['cuadra_previo'] else 'NO CUADRA'}", flush=True)
    if not cuentas['cuadra_previo']:
        # Los recuentos viajan con el fallo: justo cuando no cuadra es cuando hacen falta.
        raise FalloPasada('NO CUADRA antes de la foto: ' + cuentas['motivo_previo'],
                          dict({'n_crudo': n_crudo}, **{'p_' + p: v for p, v in previas.items()}))
    if not foto:
        raise RuntimeError('la foto sale vacía: nada de HEO pasa el filtro del director')

    filas_foto = []
    for f in foto:
        f['id'] = str(uuid.uuid4())
        filas_foto.append({
            'id': f['id'], 'pasada_id': pasada, 'producto_heo': f['producto_heo'],
            'ean_original': f['ean_original'], 'ean_core': f['ean_core'],
            'variantes': f['variantes'], 'codigos_keepa': f['codigos_keepa'],
            'nombre': f['nombre'], 'marca': f['marca'], 'categoria': f['categoria'],
            'precio_catalogo': f['precio_catalogo'], 'precio_unidad': f['precio_unidad'],
            'es_caja': f['es_caja'], 'uds_caja': f['uds_caja'], 'es_chase': f['es_chase'],
            'en_oferta': f['en_oferta'], 'campana': f['campana'] or None,
            'disponibilidad': f['disponibilidad'] or None, 'fin_de_vida': f['fin_de_vida'],
            'preorder': f['preorder'], 'imagen': f['imagen'] or None, 'aviso_caja': f['aviso_caja'],
        })
    _en_lotes('escaner2_foto', filas_foto)
    _en_lotes('escaner2_apartado', [dict(a, pasada_id=pasada) for a in apartados])

    # 🔴 LO QUE HAY EN LA BASE, NO LO QUE DICE EL CLIENTE: se cuenta despues de escribir.
    n_foto_bd = _contar('escaner2_foto', pasada_id=pasada)
    listas_bd = {mo: _contar('escaner2_apartado', pasada_id=pasada, motivo=mo) for mo in e2.MOTIVOS_APARTADO}
    print(f"CUADRE foto [HEO]: escritas {len(filas_foto)} | en la tabla {n_foto_bd} · listas de las "
          f"puertas previas en la tabla {listas_bd}", flush=True)
    if n_foto_bd != len(filas_foto):
        raise RuntimeError('la foto no quedó entera en la base (%s de %s)' % (n_foto_bd, len(filas_foto)))
    distintas = {mo: (listas_bd[mo], previas[mo]) for mo in e2.MOTIVOS_APARTADO if listas_bd[mo] != previas[mo]}
    if distintas:
        raise RuntimeError('las listas de las puertas previas no son su recuento (en la base, contadas): %s'
                           % distintas)

    # 4 · La lista para el Visualizador, uno por linea.
    codigos = e2.lista_para_keepa(foto)
    tandas = e2.partir_en_tandas(codigos, tanda)
    base = f'heo/{pasada}'
    opciones = {'content-type': 'text/plain; charset=utf-8', 'upsert': 'true'}
    sb.storage.from_(BUCKET).upload(f'{base}/eans.txt', '\n'.join(codigos).encode('utf-8'), opciones)
    if len(tandas) > 1:
        for i, t in enumerate(tandas, 1):
            sb.storage.from_(BUCKET).upload(f'{base}/eans_{i}.txt', '\n'.join(t).encode('utf-8'), opciones)

    cierre = {'estado': 'esperando_csv', 'terminada_en': _ahora(),
              'regla_activa': bool(regla.get('activo')), 'marcas': info['marcas_reales'],
              'ofertas': info['quiere_ofertas'], 'n_crudo': n_crudo, 'n_foto': cuentas['n_foto'],
              'ruta_lista': f'{base}/eans.txt', 'n_eans_lista': len(codigos), 'n_tandas': len(tandas),
              'tanda': tanda}
    for p in e2.PUERTAS_PREVIAS:
        cierre['p_' + p] = previas[p]
    return cierre


if __name__ == '__main__':
    main()
