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

# --- (I) 🔴 EL DISPARO AUTOMATICO NO PUEDE APLICAR ---------------------------
# El fallo que esto caza es REAL y estuvo en el fichero: la primera version
# resolvia MODO con `github.event.inputs.modo` y un respaldo al modo de aplicar.
# En `workflow_run` no hay inputs, asi que ganaba el respaldo: la noche siguiente
# a fusionar, el workflow habria BORRADO su primera tanda en produccion sin que
# nadie mirase. Compila, pasa el YAML y no lo cazaba ningun test.
#
# 🔒 Y se mira el fichero SIN COMENTARIOS, que es la regla de la casa: el
#    comentario que hay ahi arriba EXPLICA el fallo, y un grep sobre el texto
#    crudo contaria esa explicacion como si fuera codigo. Es la trampa del 440px.
import io                                                            # noqa: E402

with io.open('.github/workflows/comprimir-keepa-antiguos.yml', encoding='utf-8') as fh:
    _wf_crudo = fh.read()
_wf = '\n'.join(l for l in _wf_crudo.split('\n') if not l.lstrip().startswith('#'))

_LINEA_MODO = ("MODO:   ${{ github.event_name == 'workflow_dispatch' "
               "&& github.event.inputs.modo || 'ensayo' }}")
eq('(I) 🔴 el MODO por defecto es ensayo, y va guardado por el evento',
   _wf.count(_LINEA_MODO), 1)
eq('(I) 🔴 (el fallo que hubo) ningun respaldo a aplicar en el CODIGO',
   _wf.count("|| 'aplicar'"), 0)
# Y que el ancla del despojado sirve de algo: el fichero crudo SI menciona la
# palabra en su comentario, el despojado no. Sin esto, el 0 de arriba podria
# estar saliendo verde simplemente porque nadie escribio nunca esa palabra.
eq('(I) el fichero crudo SI habla de aplicar (en el comentario)',
   'aplicar' in _wf_crudo, True)
eq('(I) 🔴 … y en el despojado solo queda como opcion del menu MANUAL',
   _wf.count('aplicar'), 2)   # medido: la `description:` y el `options:` del input `modo`

# --- (J) 🔴 LOS DE «0 FILAS» VAN A SU TANDA, Y NO A LA PRIMERA ---------------
# El caso es REAL y con nombres reales: el orden del script es por nombre, y el
# fichero del 16-jul -- que el historico NO cita -- es EL PRIMERO DE LOS 67. O
# sea que la primera tanda supervisada (LIMITE=3) habria empezado por el unico
# cuyo UPDATE toca 0 filas, que es justo el que no se puede distinguir de un
# fallo silencioso mirandolo. Medido el 29-ago-2026.
CERO_16 = 'KeepaExport-2026-07-16-ResumenDelVendedor-9-X.csv'
CERO_20 = 'KeepaExport-2026-07-20-ResumenDelVendedor-9-X.csv'
REALES = [obj(CERO_16, 40), obj(CERO_20, 40),
          obj('KeepaExport-2026-07-20-ResumenDelVendedor-3-X.csv', 40),
          obj('KeepaExport-2026-07-20-ResumenDelVendedor-4-X.csv', 40),
          obj('KeepaExport-2026-07-20-ResumenDelVendedor-8-X.csv', 40)]
SIN_H = {CERO_16, CERO_20}

# La direccion ROJA primero, que es la que enseña el problema: sin posponer, la
# primera tanda de 3 SE LLEVA al del 16-jul, que es el de 0 filas.
elegidos_mal, _ = seleccionar_antiguos(REALES, set(), AHORA, dias=2, limite=3,
                                       sin_hist=SIN_H, posponer_sin_hist=False)
eq('(J) 🔴 (el problema) sin posponer, la tanda de 3 empieza por el de 0 filas',
   elegidos_mal[0], CERO_16)

# Y con la guarda puesta: los tres que salen son los que Fernando aprobo.
elegidos, descartes = seleccionar_antiguos(REALES, set(), AHORA, dias=2, limite=3,
                                           sin_hist=SIN_H, posponer_sin_hist=True)
eq('(J) 🔴 posponiendo, la tanda de 3 son los CITADOS, en orden',
   elegidos, ['KeepaExport-2026-07-20-ResumenDelVendedor-3-X.csv',
              'KeepaExport-2026-07-20-ResumenDelVendedor-4-X.csv',
              'KeepaExport-2026-07-20-ResumenDelVendedor-8-X.csv'])
eq('(J) 🔴 … y NINGUNO de los de 0 filas se cuela',
   sorted(set(elegidos) & SIN_H), [])
eq('(J) el motivo dice que van a su tanda, y como pedirla',
   'SIN_HIST=incluir' in dict(descartes)[CERO_16], True)

# La tanda final: `incluir` es lo que los saca, y son solo ellos.
solo_ceros = [obj(CERO_16, 40), obj(CERO_20, 40)]
elegidos_fin, _ = seleccionar_antiguos(solo_ceros, set(), AHORA, dias=2, limite=0,
                                       sin_hist=SIN_H, posponer_sin_hist=False)
eq('(J) la tanda final los coge a los dos', sorted(elegidos_fin), sorted([CERO_16, CERO_20]))
elegidos_nada, _ = seleccionar_antiguos(solo_ceros, set(), AHORA, dias=2, limite=0,
                                        sin_hist=SIN_H, posponer_sin_hist=True)
eq('(J) 🔴 … y con posponer no quedaria ninguno (no es un silencio: es la guarda)',
   elegidos_nada, [])

# 🔒 Y el defecto por defecto: sin decir nada, se POSPONE. Un default permisivo
#    aqui es justo lo que Fernando pidio que no pasara.
elegidos_def, _ = seleccionar_antiguos(REALES, set(), AHORA, dias=2, limite=3,
                                       sin_hist=SIN_H)
eq('(J) 🔴 el defecto es POSPONER, no incluir', sorted(set(elegidos_def) & SIN_H), [])

print()
if fallos:
    print(f'❌ {len(fallos)} FALLOS: ' + ', '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
