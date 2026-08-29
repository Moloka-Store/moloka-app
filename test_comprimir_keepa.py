# -*- coding: utf-8 -*-
"""Banco de `comprimir_keepa_antiguos.py`: a quien toca, a quien NO, y la guarda.

🔴 EL CASO QUE JUSTIFICA ESTE FICHERO, Y NO ES LA VENTANA DE DIAS.
   Lo obvio es "no toques el CSV de hoy, que lo esta leyendo el procesador". Eso
   lo cubre la ventana. Lo que NO es obvio -- y es lo que romperia el historico
   sin que nadie se entere -- es que `archivar_foto()` (foto_comun.py:459) apila
   la foto viva ENTERA al empezar la siguiente pasada del procesador. O sea: el
   nombre que hoy vive en `keepa_escaparate.fichero` lo COPIARA el procesador al
   historico manana. Si hoy lo comprimimos, manana el propio procesador escribe
   en el historico un nombre que ya no existe, y ningun UPDATE nuestro llega a
   tiempo.
   🔬 Medido el 29-ago-2026: la tabla viva citaba los 4 ficheros del 2026-08-29,
      y el historico de ese dia solo tenia 3 dominios (faltaba `it`, que fue el
      ultimo cargado, a las 09:46:31). Ese `it` se archivara en la proxima
      pasada -- con su nombre de fichero. Por eso la exclusion por tabla viva es
      una guarda aparte y no un cinturon de sobra.

🔒 Y LAS DOS DIRECCIONES: cada guarda se prueba tambien ROTA. Un test que solo
   ve verde no distingue "protege" de "no mira".
"""
import gzip
import sys
from datetime import datetime, timedelta, timezone

from comprimir_keepa_antiguos import (SQL_GUARDA, es_comprimible, nombre_gz,
                                      seleccionar_antiguos,
                                      veredicto_guarda, verificar_ida_y_vuelta)

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(f'{"OK " if ok else "XX "} {nombre}'
          + ('' if ok else f'   got={obtenido!r} exp={esperado!r}'))


AHORA = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)


def obj(nombre, dias_atras=None, sin_fecha=False):
    o = {'name': nombre}
    if not sin_fecha:
        o['updated_at'] = (AHORA - timedelta(days=dias_atras)).isoformat()
    return o


# --- (A) Que cuenta como comprimible ---------------------------------------
eq('(A) un .csv se comprime', es_comprimible('KeepaExport-2026-07-16-X.csv'), True)
eq('(A) 🔴 un .csv.gz NO se recomprime', es_comprimible('KeepaExport-2026-07-16-X.csv.gz'), False)
eq('(A) un .txt no es asunto de este script', es_comprimible('50465020654.txt'), False)
eq('(A) mayusculas: .CSV tambien', es_comprimible('X.CSV'), True)
eq('(A) el nombre se conserva entero', nombre_gz('KeepaExport-2026-07-16-X.csv'),
   'KeepaExport-2026-07-16-X.csv.gz')

# --- (B) La ventana de dias -------------------------------------------------
objetos = [obj('viejo.csv', 30), obj('justo_fuera.csv', 3), obj('de_ayer.csv', 1),
           obj('de_hoy.csv', 0)]
elegidos, descartes = seleccionar_antiguos(objetos, set(), AHORA, dias=2)
eq('(B) entran los de mas de 2 dias', sorted(elegidos), ['justo_fuera.csv', 'viejo.csv'])
eq('(B) 🔴 el de hoy se queda fuera', 'de_hoy.csv' in elegidos, False)
eq('(B) 🔴 el de ayer tambien (1 dia < 2)', 'de_ayer.csv' in elegidos, False)
eq('(B) y se dice por que', dict(descartes)['de_hoy.csv'].startswith('reciente'), True)

# --- (C) 🔴 LA GUARDA DE LA TABLA VIVA — el caso del `it` del 29-ago --------
# Un fichero ANTIQUISIMO pero citado en la tabla viva NO se toca. Si esta
# comprobacion cae, el procesador escribira manana un nombre muerto.
objetos = [obj('archi_viejo_pero_vivo.csv', 90), obj('archi_viejo.csv', 90)]
elegidos, descartes = seleccionar_antiguos(
    objetos, {'archi_viejo_pero_vivo.csv'}, AHORA, dias=2)
eq('(C) 🔴 citado en la tabla viva -> NO se toca, tenga 90 dias',
   elegidos, ['archi_viejo.csv'])
eq('(C) … y el motivo lo nombra',
   'VIVA' in dict(descartes)['archi_viejo_pero_vivo.csv'], True)
# La direccion ROJA: si se le quita la exclusion, el mismo fichero SI entraria.
# Sin esto, el OK de arriba tambien saldria verde con la funcion vacia.
elegidos_sin, _ = seleccionar_antiguos(objetos, set(), AHORA, dias=2)
eq('(C) 🔴 (roto a mano) sin la exclusion, ese fichero SI entraria',
   'archi_viejo_pero_vivo.csv' in elegidos_sin, True)

# --- (D) Sin fecha no se adivina la edad ------------------------------------
elegidos, descartes = seleccionar_antiguos([obj('sin_fecha.csv', sin_fecha=True)],
                                           set(), AHORA, dias=2)
eq('(D) 🔴 sin fecha NO se asume viejo', elegidos, [])
eq('(D) … y se dice', 'sin fecha' in dict(descartes)['sin_fecha.csv'], True)

# --- (E) Las tandas ---------------------------------------------------------
objetos = [obj(f'v{i}.csv', 30) for i in range(5)]
elegidos, descartes = seleccionar_antiguos(objetos, set(), AHORA, dias=2, limite=2)
eq('(E) LIMITE recorta la tanda', len(elegidos), 2)
eq('(E) 🔴 y los que quedan fuera se DICEN, no desaparecen',
   sum(1 for _, m in descartes if 'LIMITE' in m), 3)

# --- (F) La ida y vuelta ----------------------------------------------------
crudo = b'asin,dominio\nB0002TT3N4,es\n' * 500
import hashlib                                                       # noqa: E402
sha = hashlib.sha256(crudo).hexdigest()
recuperado = gzip.decompress(gzip.compress(crudo, 9))
ok, det = verificar_ida_y_vuelta(sha, len(crudo), recuperado)
eq('(F) ida y vuelta identica -> OK', ok, True)
# ROJA 1: un byte cambiado. Mismo tamano, distinto sha: el caso que un
# `len()` a secas NO cazaria.
tocado = bytearray(crudo); tocado[7] = (tocado[7] + 1) % 256
ok_b, det_b = verificar_ida_y_vuelta(sha, len(crudo), bytes(tocado))
eq('(F) 🔴 (roto) un byte distinto -> ROJO', ok_b, False)
eq('(F) 🔴 … aunque el tamano coincida', det_b['bytes_antes'] == det_b['bytes_despues'], True)
# ROJA 2: truncado.
ok_t, _ = verificar_ida_y_vuelta(sha, len(crudo), crudo[:-1])
eq('(F) 🔴 (roto) truncado -> ROJO', ok_t, False)

# --- (G) La guarda C --------------------------------------------------------
eq('(G) 0 y 0 -> VERDE', veredicto_guarda(0, 0), (True, 0))
eq('(G) 🔴 (roto) 1 huerfana en el historico -> ROJO', veredicto_guarda(1, 0), (False, 1))
eq('(G) 🔴 (roto) 1 huerfana en la tabla VIVA -> ROJO', veredicto_guarda(0, 1), (False, 1))
eq('(G) 🔴 (roto) las dos -> ROJO y suma', veredicto_guarda(16066, 4), (False, 16070))

# --- (H) La guarda mira las DOS tablas ---------------------------------------
# 🔒 Por estructura, no por un `in` suelto: se cuentan las apariciones de cada
#    tabla como origen de un `from`, porque `keepa_escaparate` casa DENTRO de
#    `keepa_escaparate_hist` y un `in` daria verde con una sola de las dos.
_sql = ' '.join(SQL_GUARDA.split())
eq('(H) la guarda cuenta sobre el historico',
   _sql.count('from public.keepa_escaparate_hist'), 1)
eq('(H) 🔴 … y sobre la tabla VIVA (no basta con que la cadena aparezca)',
   _sql.count('from public.keepa_escaparate k'), 1)
eq('(H) y cruza contra el bucket correcto',
   _sql.count("o.bucket_id = 'informes'"), 2)
eq('(H) con el prefijo de la carpeta a los dos lados',
   _sql.count("'keepa_escaparate/' ||"), 2)

print()
if fallos:
    print(f'❌ {len(fallos)} FALLOS: ' + ', '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
