# -*- coding: utf-8 -*-
"""`archivar_foto()` y las columnas GENERADAS.

🔴 POR QUE ESTE FICHERO EXISTE, Y ES UN CASO QUE TODAVIA NO PUEDE DARSE. Hoy no hay ni
   una columna generada en la base, asi que este test es INERTE: no protege de nada
   que este pasando. Se escribe ANTES porque la migracion que las anade
   (`keepa_escaparate.asin_k` / `.dominio_k`) tumbaria la carga de Keepa si esto no
   estuviera puesto -- y no con un error que mencione la palabra "generada", sino con
   un `faltan_en_hist` que habla de otra cosa.

🔑 LA REGLA: una columna `GENERATED ALWAYS AS (...) STORED` no es un dato, es una
   lectura del dato de al lado. Archivarla seria guardar dos veces lo mismo, y encima
   congelada con la formula del dia en que se archivo.

🔒 Y va en `archivar_foto` y no en el parametro `excluir` de cada llamada: `excluir` es
   para DECISIONES (el `crudo` de Keepa se excluye porque vive en Storage); esto es una
   REGLA, y una regla que hay que acordarse de pasar en cada llamada es una regla que
   se olvida.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import archivar_foto, Aborta  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK  ' if ok else 'XX  ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


class CursorFalso:
    """Contesta lo que `archivar_foto` pregunta, y APUNTA todo lo que se le manda.

    🔴 Sabe de `attgenerated`, que es la quinta columna que la funcion pide ahora. Un
       doble que devolviera cuatro campos haria que el codigo nuevo reventara con
       IndexError en vez de probar nada -- y eso saldria rojo, que es lo correcto, pero
       por el motivo equivocado."""

    def __init__(self, cols_viva, cols_hist, hist_existe=True):
        # cada col: (nombre, tipo, nullable, defecto, attgenerated)
        self.cols_viva = cols_viva
        self.cols_hist = cols_hist
        self.hist_existe = hist_existe
        self.ejecutadas = []
        self._ultimo_uno = None
        self._ultimo_muchos = []
        self.rowcount = 7

    @staticmethod
    def _es_hist(tabla):
        """🔴 El sufijo es `_hist`, NO `_historico`. La primera version de este doble
        puso `_historico` y devolvia las columnas de la FOTO para las dos tablas: o sea
        que comparaba la foto CONSIGO MISMA. Tres casos salieron verdes sin medir nada,
        y solo se vio porque los DOS que tenian que ponerse rojos no se pusieron.
        Es la comprobacion que no puede fallar, dentro del doble."""
        return (tabla or '').endswith('_hist')

    def execute(self, sql, args=None):
        self.ejecutadas.append(sql)
        s = ' '.join(sql.lower().split())
        if 'to_regclass' in s:
            tabla = (args or ('',))[0]
            existe = 'algo' if (not self._es_hist(tabla) or self.hist_existe) else None
            self._ultimo_uno = (existe,)
        elif 'from pg_attribute' in s:
            tabla = (args or ('',))[0]
            self._ultimo_muchos = (self.cols_hist if self._es_hist(tabla) else self.cols_viva)
        else:
            self._ultimo_uno = None
            self._ultimo_muchos = []

    def fetchone(self):
        return self._ultimo_uno

    def fetchall(self):
        return self._ultimo_muchos


def col(nombre, generada=False):
    return (nombre, 'text', True, None, 's' if generada else '')


def corre(cols_viva, cols_hist, **kw):
    """Devuelve (resultado o la excepcion, el SQL del INSERT, lo escrito)."""
    cur = CursorFalso(cols_viva, cols_hist)
    dichas = []
    original = print
    import builtins
    builtins.print = lambda *a, **k: dichas.append(' '.join(str(x) for x in a))
    try:
        r = archivar_foto(cur, 'keepa_escaparate', ['asin', 'dominio'], 'fecha_foto', **kw)
        err = None
    except Aborta as e:
        r, err = None, str(e)
    finally:
        builtins.print = original
    insert = next((e for e in cur.ejecutadas if 'insert into' in e.lower()), '')
    return r, err, insert, '\n'.join(dichas)


NORMALES = [col('asin'), col('dominio'), col('fecha_foto'), col('rank')]

print('== 1) SIN COLUMNAS GENERADAS: nada cambia ==')
r, err, insert, dichas = corre(NORMALES, NORMALES)
eq('(1) no aborta', err, None)
eq('(1) archiva las cuatro', all(c[0] in insert for c in NORMALES), True)
# 🔒 Y esta CALLADO: la mitad que se olvida. Un aviso que sale siempre no informa.
eq('(1) 🔒 y NO dice nada de columnas generadas', 'GENERADA' in dichas, False)

print('\n== 2) 🔴 UNA COLUMNA GENERADA NO SE ARCHIVA ==')
# La foto tiene asin_k generada; el historico NO la tiene. Es exactamente el estado
# en que quedaria la base tras la migracion de las columnas normalizadas.
viva = NORMALES + [col('asin_k', generada=True)]
r, err, insert, dichas = corre(viva, NORMALES)
eq('(2) 🔴 NO aborta por faltan_en_hist', err, None)
eq('(2) 🔴 … y la generada NO entra en el INSERT', 'asin_k' in insert, False)
eq('(2) 🔒 … mientras las normales SI', all(c[0] in insert for c in NORMALES), True)
# 🔒 Y lo dice: saltarse columnas en silencio es como se cuelan los huecos en un
#    historico. Se grita, aunque sea para decir que se hizo bien.
eq('(2) 🔒 … y lo GRITA', 'GENERADA' in dichas and 'asin_k' in dichas, True)

print('\n== 3) 🔴 LA GUARDA DE VERDAD SIGUE VIVA ==')
# 🔴 La mitad que prueba algo: que el arreglo NO haya apagado `faltan_en_hist`. Una
#    columna NORMAL que falte en el historico tiene que seguir PARANDO la carga --
#    si no, el arreglo habria cambiado un fallo ruidoso por uno mudo.
viva = NORMALES + [col('columna_nueva_de_verdad')]
r, err, insert, dichas = corre(viva, NORMALES)
eq('(3) 🔴 una columna NORMAL que falta en el historico SIGUE abortando', err is not None, True)
eq('(3) 🔴 … nombrandola', 'columna_nueva_de_verdad' in (err or ''), True)

print('\n== 4) 🔒 LAS DOS COSAS A LA VEZ ==')
# Una generada (se salta) y una normal que falta (aborta). Tiene que abortar por la
# normal y NO mencionar la generada como si fuera el problema.
viva = NORMALES + [col('asin_k', generada=True), col('otra_normal')]
r, err, insert, dichas = corre(viva, NORMALES)
eq('(4) 🔒 aborta por la normal', 'otra_normal' in (err or ''), True)
eq('(4) 🔒 … y NO culpa a la generada', 'asin_k' in (err or ''), False)

print('\n== 5) 🔒 EL PARAMETRO `excluir` SIGUE FUNCIONANDO ==')
# Es otra cosa distinta y no se ha tocado: `excluir` es para decisiones (el `crudo`
# de Keepa vive en Storage), no para reglas.
viva = NORMALES + [col('crudo')]
r, err, insert, dichas = corre(viva, NORMALES, excluir=('crudo',))
eq('(5) 🔒 lo excluido no entra', 'crudo' in insert, False)
eq('(5) 🔒 … y no aborta', err, None)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · archivar_foto y las columnas generadas')
