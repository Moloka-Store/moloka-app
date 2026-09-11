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

# --- (I) 🔴 EL AUTOMATICO APLICA, PERO SOLO SI LA GUARDA DIJO QUE SI ----------
# 🔬 ESTA SECCION CAMBIO DE INVARIANTE EL 11-SEP-2026, Y EL CAMBIO ES LA MITAD
#    QUE HAY QUE ENTENDER:
#    · ANTES exigia "el disparo automatico no puede aplicar NUNCA". El fallo que
#      cazaba era real: la primerisima version resolvia MODO con
#      `github.event.inputs.modo` y un respaldo al modo de aplicar, y en
#      `workflow_run` no hay inputs, asi que ganaba el respaldo y la noche
#      siguiente a fusionar habria borrado su primera tanda sin que nadie mirase.
#    · Pero el arreglo se paso de largo por el otro lado: `workflow_run` caia a
#      'ensayo' SIEMPRE, asi que el automatico no comprimio NADA en 21 corridas
#      seguidas (run 34574217878) y el run salia verde. La limpieza que el
#      workflow existe para hacer no se hacia.
#    · AHORA el invariante es: el automatico aplica SI Y SOLO SI el paso de la
#      guarda dejo `guarda_verde` valiendo EXACTAMENTE 'true'. Y por ningun
#      camino hay un respaldo a 'aplicar' -- eso es lo que se conserva del
#      fallo viejo.
#
# 🔒 SE MIRA POR ESTRUCTURA (jobs -> steps -> env), no con un grep sobre el
#    texto. No es estilo: lo que hay que comprobar es que la condicion este en
#    EL PASO QUE APLICA, y un grep no distingue ese paso del de al lado. Ademas
#    el motivo esta escrito largo en los comentarios del propio .yml, y contarlo
#    como codigo es la trampa del 440px.
import contextlib                                                    # noqa: E402
import importlib                                                     # noqa: E402
import io                                                            # noqa: E402
import os                                                            # noqa: E402
import re                                                            # noqa: E402
import shutil                                                        # noqa: E402
import subprocess                                                    # noqa: E402
import tempfile                                                      # noqa: E402
import types                                                         # noqa: E402

import yaml                                                          # noqa: E402

_RUTA_WF = os.path.join('.github', 'workflows', 'comprimir-keepa-antiguos.yml')
with io.open(_RUTA_WF, encoding='utf-8') as fh:
    _wf_crudo = fh.read()
_wf = '\n'.join(l for l in _wf_crudo.split('\n') if not l.lstrip().startswith('#'))

_N_GUARDA = '4) La guarda ANTES (si ya venimos rotos, no se toca nada)'
_N_PASADA = '5) La pasada'
_N_VEREDICTO = '7) EL VEREDICTO, en la PRIMERA linea del resumen de la corrida'


def pasos_de(doc):
    """{nombre del paso: el paso}, del job que comprime. Sin `or {}`
    complaciente en el nombre: un paso renombrado desaparece del diccionario y
    lo que dependa de el se cae, que es justo lo que se quiere."""
    job = ((doc.get('jobs') or {}).get('comprimir') or {})
    return {(p.get('name') or ''): p for p in (job.get('steps') or [])}


def exige_la_guarda(doc):
    """True si el paso que APLICA esta condicionado a lo que midio la guarda."""
    modo = ((pasos_de(doc).get(_N_PASADA) or {}).get('env') or {}).get('MODO', '')
    return "steps.guarda.outputs.guarda_verde == 'true'" in modo


_DOC = yaml.safe_load(_wf_crudo) or {}
_JOB = (_DOC.get('jobs') or {}).get('comprimir') or {}
_PASOS = pasos_de(_DOC)
_P_GUARDA = _PASOS.get(_N_GUARDA) or {}
_P_PASADA = _PASOS.get(_N_PASADA) or {}
_P_VEREDICTO = _PASOS.get(_N_VEREDICTO) or {}
_MODO = (_P_PASADA.get('env') or {}).get('MODO', '')

# Contra el verde vacio: si el barrido no encuentra los pasos, todo lo de abajo
# saldria verde midiendo el aire.
eq('(I) los tres pasos que se miran existen, con su nombre exacto',
   [bool(_P_GUARDA), bool(_P_PASADA), bool(_P_VEREDICTO)], [True, True, True])

eq('(I) 🔴 el paso que aplica exige que la guarda haya dicho `true`',
   exige_la_guarda(_DOC), True)
eq('(I) 🔴 … y la guarda es el paso 4, que es quien lo escribe (`id: guarda`)',
   _P_GUARDA.get('id'), 'guarda')
eq('(I) … corriendo el script en MODO=guarda',
   (_P_GUARDA.get('env') or {}).get('MODO'), 'guarda')
eq('(I) 🔴 en workflow_dispatch sigue mandando el input, sin tocar su semantica',
   "github.event_name == 'workflow_dispatch' && (github.event.inputs.modo || 'ensayo')"
   in _MODO, True)
# El ULTIMO literal de la expresion es el que gana cuando todo lo demas es
# falso. Que sea 'ensayo' es lo que hace que esto falle CERRADO.
_LITERALES = re.findall(r"'([a-z_]+)'", _MODO)
eq('(I) 🔴 … y el ultimo respaldo de la expresion es ensayo, no aplicar',
   _LITERALES[-1] if _LITERALES else None, 'ensayo')
eq('(I) 🔴 (el fallo del principio) ningun respaldo a aplicar en el CODIGO',
   _wf.count("|| 'aplicar'"), 0)
# La otra mitad de ese ancla: el crudo SI nombra la palabra. Sin esto, el 0 de
# arriba podria salir verde simplemente porque nadie la escribio nunca.
eq('(I) el fichero crudo SI habla de aplicar', 'aplicar' in _wf_crudo, True)

# 🔴 Y QUE NADIE DEVUELVA MODO AL `env` DEL JOB. Ahi no se ve `steps.*`: la
#    expresion se resolveria en vacio y el automatico volveria a no aplicar
#    nunca. O sea, el fallo de las 21 corridas otra vez, y otra vez en silencio.
eq('(I) 🔴 MODO no vuelve al env del job (ahi todavia no existen los pasos)',
   'MODO' in (_JOB.get('env') or {}), False)

# La direccion ROJA del detector: el .yml de ayer -- el que dejo 21 simulacros --
# tiene que SUSPENDER. Sin esto, `exige_la_guarda` podria estar diciendo que si
# a cualquier cosa.
_DOC_DE_AYER = yaml.safe_load(yaml.safe_dump(_DOC))
_AYER = pasos_de(_DOC_DE_AYER)[_N_PASADA]
_AYER['env']['MODO'] = ("${{ github.event_name == 'workflow_dispatch' "
                        "&& github.event.inputs.modo || 'ensayo' }}")
eq('(I) 🔴 … y el MODO de ayer NO pasa este banco', exige_la_guarda(_DOC_DE_AYER), False)

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
eq('(J) el motivo dice que estan fuera A PROPOSITO, no por descuido',
   'FUERA DEL PLAN A PROPOSITO' in dict(descartes)[CERO_16], True)

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

# --- (K) 🔴 Y EL WORKFLOW TAMPOCO PUEDE CAER EN `incluir` --------------------
# La decision de Fernando (29-ago-2026) es que los 3 se quedan en .csv PARA
# SIEMPRE, porque son los unicos reprocesables y el procesador filtra por
# `.endswith('.csv')`. `posponer` no es un "de momento": es el modo permanente.
# Se ancla en el fichero SIN COMENTARIOS, que es donde el motivo esta escrito
# largo y contaria como codigo en un grep crudo.
eq('(K) el input nace en posponer', _wf.count('default: posponer'), 1)
eq('(K) 🔴 y sin input (disparo automatico) tambien',
   _wf.count("SIN_HIST: ${{ github.event.inputs.sin_hist || 'posponer' }}"), 1)
eq('(K) 🔴 ningun respaldo a incluir en el CODIGO', _wf.count("|| 'incluir'"), 0)
# La otra mitad del ancla: el fichero crudo SI nombra `incluir` (en el motivo
# escrito). Sin esto, el 0 de arriba podria ser verde por no mencionarse nunca.
eq('(K) el crudo SI habla de incluir (el motivo, en los comentarios)',
   'incluir' in _wf_crudo, True)

# --- (L) 🔴 LA PRIMERA LINEA DEL RESUMEN NO PUEDE MENTIR ----------------------
# Lo que se arregla aqui NO es que el workflow hiciera algo malo: es que hiciera
# NADA y no se notara. 21 corridas automaticas seguidas fueron simulacros, y lo
# unico que lo decia era el `env` del paso 5 (hay que desplegarlo para verlo) y
# la ultima linea de su log. Desde el 11-sep-2026 el paso 7 lo pone en la
# PRIMERA linea del resumen de la corrida.
#
# 🔒 SE EJECUTA EL BASH DE VERDAD, sacado del .yml por estructura. Copiar aqui
#    la cadena de `if` seria probar la copia: el dia que alguien cambie el
#    workflow, el banco seguiria verde sobre el texto viejo.
print("\n(L) el veredicto del paso 7, ejecutando SU bash")

_BASH = shutil.which('bash')
eq('(L) hay un bash con el que correr el paso 7 (en ubuntu del CI, siempre)',
   bool(_BASH), True)

_VACIO = {'EVENTO': '', 'MODO_USADO': '', 'GUARDA_VERDE': '', 'HUERFANAS_H': '',
          'HUERFANAS_V': '', 'COMPRIMIDOS': '', 'RESULTADO': '', 'GUARDA_FINAL': '',
          'DIAS': '2', 'LIMITE': '20', 'SIN_HIST': 'posponer'}


def veredicto(**entorno):
    """La PRIMERA linea que el paso 7 deja en el resumen, para ese estado."""
    guion = _P_VEREDICTO.get('run') or ''
    if not _BASH or not guion:
        return '(no se ha podido ejecutar el paso 7)'
    tmp = tempfile.mkdtemp()
    try:
        resumen = os.path.join(tmp, 'resumen.md')
        sh = os.path.join(tmp, 'paso7.sh')
        with io.open(sh, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(guion)
        env = dict(os.environ, **_VACIO)
        env['GITHUB_STEP_SUMMARY'] = resumen
        env.update({k: str(v) for k, v in entorno.items()})
        # `-e` como el shell por defecto de Actions en linux (`bash -e {0}`).
        p = subprocess.run([_BASH, '-e', sh], env=env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        if p.returncode != 0:
            return 'EL PASO 7 SE CAYO: ' + ((p.stderr or '') + (p.stdout or '')).strip()
        with io.open(resumen, encoding='utf-8') as fh:
            return fh.readline().rstrip('\n')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# La corrida buena: automatico, guarda verde, pasada aplicada.
eq('(L) 🔴 aplicando, la primera linea dice APLICADO y CUANTOS',
   veredicto(EVENTO='workflow_run', MODO_USADO='aplicar', GUARDA_VERDE='true',
             COMPRIMIDOS='20', RESULTADO='success', GUARDA_FINAL='success'),
   'APLICADO: 20 ficheros comprimidos')

# 🔴 Y una pasada que arranco en aplicar y murio NO puede leerse como simulacro:
#    puede haber ficheros ya comprimidos y originales ya borrados.
eq('(L) 🔴 … y si la pasada murio a mitad, NO dice simulacro',
   veredicto(EVENTO='workflow_run', MODO_USADO='aplicar', GUARDA_VERDE='true',
             RESULTADO='failure').startswith('APLICADO A MEDIAS'), True)

# La guarda roja: el paso 5 ni corre, asi que MODO_USADO llega vacio.
eq('(L) 🔴 guarda roja: lo dice, y dice el motivo',
   veredicto(EVENTO='workflow_run', GUARDA_VERDE='false', RESULTADO='skipped',
             HUERFANAS_H='7', HUERFANAS_V='0'),
   'SIMULACRO: no se ha escrito nada (motivo: guarda roja)')

# Y la guarda que ni llego a medir (secreto que falta, base que no responde):
# es OTRA cosa que una guarda roja, y se dice distinto.
eq('(L) 🔴 … y "no pudo medir" no se disfraza de "guarda roja"',
   veredicto(EVENTO='workflow_run', RESULTADO='failure'),
   'SIMULACRO: no se ha escrito nada (motivo: la guarda no llego a medir)')

eq('(L) ensayo manual: lo dice, y dice que es manual',
   veredicto(EVENTO='workflow_dispatch', MODO_USADO='ensayo', GUARDA_VERDE='true',
             RESULTADO='success', GUARDA_FINAL='success'),
   'SIMULACRO: no se ha escrito nada (motivo: lanzamiento manual en ensayo)')

eq('(L) el modo guarda a mano tambien es un simulacro, y con su motivo',
   veredicto(EVENTO='workflow_dispatch', MODO_USADO='guarda', GUARDA_VERDE='true',
             RESULTADO='success', GUARDA_FINAL='success'),
   'SIMULACRO: no se ha escrito nada (motivo: lanzamiento manual en modo guarda)')

# 🔴 EL CASO QUE ORIGINO TODO ESTO, PUESTO A MANO: automatico, guarda VERDE y
#    aun asi el paso 5 corriendo en ensayo. Con el arreglo eso no puede pasar,
#    asi que si pasa es que la expresion del MODO se volvio a caer sola -- y
#    entonces la primera linea tiene que GRITARLO, no decir "lanzamiento manual".
_RECAIDA = veredicto(EVENTO='workflow_run', MODO_USADO='ensayo', GUARDA_VERDE='true',
                     RESULTADO='success', GUARDA_FINAL='success')
eq('(L) 🔴 si el automatico recae en ensayo con la guarda verde, se GRITA',
   'el disparo automatico cayo a ensayo' in _RECAIDA, True)
eq('(L) 🔴 … y NO se hace pasar por un lanzamiento manual',
   'lanzamiento manual' in _RECAIDA, False)

# 🔒 Y LO QUE HACE QUE SEA LA PRIMERA LINEA: que no escriba nadie antes. No se
#    fuerza con un `>` (borraria lo que escribiera otro paso): se MIDE.
_ANTES_DEL_7 = []
for _p in (_JOB.get('steps') or []):
    if (_p.get('name') or '') == _N_VEREDICTO:
        break
    if 'GITHUB_STEP_SUMMARY' in (_p.get('run') or ''):
        _ANTES_DEL_7.append(_p.get('name'))
eq('(L) 🔴 ningun paso anterior escribe en el resumen (por eso el 7 es el primero)',
   _ANTES_DEL_7, [])
eq('(L) … y el 7 SI escribe en el (si no, la linea de arriba seria verde por nada)',
   'GITHUB_STEP_SUMMARY' in (_P_VEREDICTO.get('run') or ''), True)


# --- (M) 🔴 CON LA GUARDA ROJA NO SE ESCRIBE NADA, DIGA LO QUE DIGA EL MODO ---
# Ahora que el automatico PUEDE aplicar, esta es la guarda que aguanta el peso:
# el propio script vuelve a correr la guarda al empezar y ABORTA si esta roja,
# en CUALQUIER modo. Aqui se ejecuta el main() REAL -- de mentira solo estan la
# base y Storage -- y se comprueba que no sale ni un UPDATE, ni un DELETE, ni
# un cliente de Supabase.
print("\n(M) la guarda roja frena la pasada, con el main() de verdad")


class CursorDeMentira:
    """Contesta a las consultas reales del script y GRABA todo lo que pasa."""

    def __init__(self, huerfanas_hist, huerfanas_viva):
        self.h, self.v = huerfanas_hist, huerfanas_viva
        self.sql, self._ret, self.rowcount = [], [], 0

    def execute(self, q, args=None):
        limpio = ' '.join(str(q).split())
        self.sql.append(limpio)
        ql = limpio.lower()
        if 'huerfanas_hist' in ql:
            self._ret = [(self.h, self.v)]
        else:
            self._ret = []

    def fetchone(self):  return self._ret[0] if self._ret else None
    def fetchall(self):  return list(self._ret)
    def close(self):     pass


class ConexionDeMentira:
    def __init__(self, cur):
        self.cur, self.commits, self.rollbacks = cur, 0, 0

    def cursor(self):   return self.cur
    def commit(self):   self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self):    pass


def montar_stubs(huerfanas_hist, huerfanas_viva, objetos):
    """psycopg2 y supabase de mentira. Devuelve el cuaderno de lo que paso."""
    marcas = {'cur': CursorDeMentira(huerfanas_hist, huerfanas_viva),
              'clientes': 0, 'subidas': [], 'borrados': [], 'descargas': []}

    class _Bucket:
        def list(self, carpeta, options=None):
            o = {'limit': 100, 'offset': 0, **(options or {})}
            return objetos[o['offset']:o['offset'] + o['limit']]

        def download(self, ruta):
            marcas['descargas'].append(ruta); return b''

        def upload(self, ruta, datos, cabeceras=None):
            marcas['subidas'].append(ruta)

        def remove(self, rutas):
            marcas['borrados'].extend(rutas)

    class _Cliente:
        storage = types.SimpleNamespace(from_=lambda b: _Bucket())

    def _create_client(url, key):
        marcas['clientes'] += 1
        return _Cliente()

    supabase = types.ModuleType('supabase')
    supabase.create_client = _create_client
    sys.modules['supabase'] = supabase

    psycopg2 = types.ModuleType('psycopg2')
    psycopg2.connect = lambda *a, **k: ConexionDeMentira(marcas['cur'])
    class _Err(Exception): pass
    psycopg2.Error = _Err
    psycopg2.OperationalError = type('OperationalError', (_Err,), {})
    sys.modules['psycopg2'] = psycopg2
    extras = types.ModuleType('psycopg2.extras')
    extras.Json = lambda v: v
    extras.execute_values = lambda *a, **k: None
    sys.modules['psycopg2.extras'] = extras
    psycopg2.extras = extras
    return marcas


def correr_main(modo, huerfanas_hist=0, huerfanas_viva=0, objetos=()):
    """Importa el script de cero con ese MODO y ejecuta su main() REAL.
    Devuelve (codigo, salida, marcas, lineas de $GITHUB_OUTPUT)."""
    for m in ('comprimir_keepa_antiguos', 'foto_comun', 'supabase',
              'psycopg2', 'psycopg2.extras'):
        sys.modules.pop(m, None)
    tmp = tempfile.mkdtemp()
    salida_gh = os.path.join(tmp, 'salida.txt')
    os.environ.update({'MODO': modo, 'DIAS': '2', 'LIMITE': '20',
                       'SIN_HIST': 'posponer', 'SUPABASE_URL': 'http://de-mentira',
                       'SUPABASE_KEY': 'de-mentira', 'DB_URL': 'de-mentira',
                       'GITHUB_OUTPUT': salida_gh})
    marcas = montar_stubs(huerfanas_hist, huerfanas_viva, list(objetos))
    mod = importlib.import_module('comprimir_keepa_antiguos')
    buf, codigo = io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else 1
    apuntes = []
    if os.path.exists(salida_gh):
        with io.open(salida_gh, encoding='utf-8') as fh:
            apuntes = [l.strip() for l in fh if l.strip()]
    shutil.rmtree(tmp, ignore_errors=True)
    return codigo, buf.getvalue(), marcas, apuntes


def toco_algo(marcas):
    """Cualquier huella de escritura: SQL que muta, o Storage tocado."""
    muta = [s for s in marcas['cur'].sql
            if s.lower().startswith(('update', 'insert', 'delete'))]
    return muta + marcas['subidas'] + marcas['borrados']


# --- La guarda ROJA, en los tres modos ---
for _modo in ('guarda', 'ensayo', 'aplicar'):
    _cod, _txt, _m, _ap = correr_main(_modo, huerfanas_hist=7, huerfanas_viva=0)
    eq(f'(M) 🔴 guarda ROJA + MODO={_modo}: el script termina en ROJO', _cod != 0, True)
    eq(f'(M) 🔴 guarda ROJA + MODO={_modo}: NO se ha escrito nada', toco_algo(_m), [])
    eq(f'(M) 🔴 guarda ROJA + MODO={_modo}: ni se llega a abrir Storage',
       _m['clientes'], 0)

# Y lo que el paso 4 le cuenta al workflow cuando esta roja.
_cod, _txt, _m, _ap = correr_main('guarda', huerfanas_hist=7, huerfanas_viva=2)
eq('(M) 🔴 la guarda roja escribe guarda_verde=false', 'guarda_verde=false' in _ap, True)
eq('(M) … con las dos cifras, para que el resumen no tenga que adivinarlas',
   sorted(_ap), ['guarda_verde=false', 'huerfanas_hist=7', 'huerfanas_viva=2'])

# --- Y la direccion VERDE, que es lo que distingue "protege" de "no mira" ---
_cod, _txt, _m, _ap = correr_main('guarda')
eq('(M) guarda VERDE: el paso 4 sale en 0', _cod, 0)
eq('(M) 🔴 … y escribe guarda_verde=true, que es el permiso del automatico',
   'guarda_verde=true' in _ap, True)

# Con la guarda verde el script SI pasa de la guarda. Con el buzon vacio no hay
# nada que tocar, asi que se ve que pasa sin que se escriba nada de verdad.
_cod, _txt, _m, _ap = correr_main('aplicar')
eq('(M) guarda VERDE + aplicar: pasa de la guarda y termina bien', _cod, 0)
eq('(M) … con el buzon vacio no toca nada', toco_algo(_m), [])
eq('(M) 🔴 … y apunta los comprimidos para la primera linea del resumen',
   'comprimidos=0' in _ap, True)
eq('(M) 🔴 y el veredicto de esa corrida no dice APLICADO a lo loco',
   veredicto(EVENTO='workflow_run', MODO_USADO='aplicar', GUARDA_VERDE='true',
             COMPRIMIDOS='0', RESULTADO='success'),
   'APLICADO: 0 ficheros comprimidos')

_cod, _txt, _m, _ap = correr_main('ensayo')
eq('(M) guarda VERDE + ensayo: termina bien y lo dice', _cod, 0)
eq('(M) … y no escribe nada', toco_algo(_m), [])
eq('(M) … y sigue diciendolo en el log, como siempre',
   'ENSAYO: no se ha escrito nada' in _txt, True)

print()
if fallos:
    print(f'❌ {len(fallos)} FALLOS: ' + ', '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
