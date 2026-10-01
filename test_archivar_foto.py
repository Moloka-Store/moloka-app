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

print('\n== 6) 🔴 KEEPA ARCHIVA SIN LOS TEXTOS DE FICHA (encargo C, 01-oct-2026) ==')
# El orden obligatorio: el procesador deja de copiar los 16 textos ANTES de que la migracion
# de la v2 (20261001120000_keepa_hist_sin_textos_de_ficha.sql) los quite del historico.
# 🔑 Lo que se prueba es la LLAMADA DE VERDAD, no una tupla copiada aqui: se lee del
#    procesador por su arbol (ast), asi que un comentario o una cadena suelta no cuentan.
# 🔬 Las columnas son las de PRODUCCION medidas el 01-oct-2026 (pg_attribute, conector de
#    lectura): la foto viva con sus 3 generadas y el historico con `archivado_en` y sin `crudo`.
import ast  # noqa: E402
import re  # noqa: E402

TEXTOS = {'titulo', 'bullet_1', 'bullet_2', 'bullet_3', 'bullet_4', 'bullet_5', 'imagenes',
          'comprados_juntos', 'asins_variacion', 'atributos_variacion', 'slug_amazon',
          'ean_keepa_crudo', 'upc_keepa', 'fabricante', 'tipo_producto', 'subcategoria'}

_proc = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'procesador_keepa_escaparate.py')
with open(_proc, encoding='utf-8') as _f:
    _arbol = ast.parse(_f.read())
llamadas = [n for n in ast.walk(_arbol)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == 'archivar_foto']
eq('(6) el procesador llama UNA vez a archivar_foto', len(llamadas), 1)
kw = {k.arg: k.value for k in llamadas[0].keywords} if llamadas else {}
EXCLUIR_REAL = tuple(ast.literal_eval(kw['excluir'])) if 'excluir' in kw else ()
eq('(6) 🔴 excluye EXACTAMENTE crudo + los 16 textos (ni uno menos, ni uno de mas)',
   sorted(EXCLUIR_REAL), sorted({'crudo'} | TEXTOS))
eq('(6) … sin repetidos', len(EXCLUIR_REAL), len(set(EXCLUIR_REAL)))

VIVA_PROD = (
    'asin dominio ean_keepa_crudo upc_keepa titulo marca fabricante tipo_producto imagenes '
    'n_imagenes tarifa_fba comision_pct comision_eur_bb bb_precio bb_vendedor bb_es_fba bb_stock '
    'bb_pct_amazon_30d bb_disponibilidad fba_mas_barato fbm_mas_barato p3_fba_precio p3_fba_stock '
    'p3_fbm_stock ofertas_nuevas ofertas_nuevas_fba ofertas_nuevas_fbm ofertas_total '
    'umbral_competitivo amazon_precio amazon_disponibilidad rank rank_30d rank_90d rank_drops_30d '
    'rank_drops_90d categoria subcategoria monthly_sold_ultimo monthly_sold_ultimo_fecha '
    'comprados_mes_pasado asin_padre asins_variacion n_variaciones atributos_variacion paq_peso_g '
    'paq_largo_cm paq_ancho_cm paq_alto_cm fecha_lanzamiento keepa_actualizado listado_desde rating '
    'n_valoraciones comprados_juntos slug_amazon bullet_1 bullet_2 bullet_3 bullet_4 bullet_5 '
    'bb_seller_id fichero fecha_foto seller_id crudo procesado_at bb_envio bb_pais_envio '
    'bb_plazo_txt nuevo_precio').split()
GENERADAS_PROD = ['asin_k', 'dominio_k', 'imagen_principal']
viva = [col(c) for c in VIVA_PROD] + [col(c, generada=True) for c in GENERADAS_PROD]
# El historico de produccion: la foto sin `crudo` ni generadas, mas `archivado_en`.
hist_antes = [col(c) for c in VIVA_PROD if c != 'crudo'] + [col('archivado_en')]
hist_despues = [c for c in hist_antes if c[0] not in TEXTOS]
eq('(6) 🔬 los recuentos medidos: 74 en la foto, 71 en el historico, 55 tras el DROP',
   (len(viva), len(hist_antes), len(hist_despues)), (74, 71, 55))

ARCHIVA = set(VIVA_PROD) - {'crudo'} - TEXTOS
# Las columnas del historico que LEEN las vistas (pg_depend) y las funciones (prosrc, por su alias)
# de produccion, y `fichero` (el compresor), medido el 01-oct-2026. Si una de estas se colara en
# `excluir`, el trackeador se quedaria sin dato.
LEIDAS = {'asin', 'dominio', 'fecha_foto', 'procesado_at', 'bb_seller_id', 'bb_stock', 'bb_es_fba',
          'bb_precio', 'bb_vendedor', 'bb_plazo_txt', 'fba_mas_barato', 'p3_fba_precio', 'p3_fba_stock',
          'amazon_precio', 'amazon_disponibilidad', 'fichero'}


def columnas_del_insert(sql):
    m = re.search(r'INSERT INTO \w+ \(([^)]*)\)', sql)
    return set(c.strip() for c in m.group(1).split(',')) if m else None


r, err, insert, dichas = corre(viva, hist_antes, excluir=EXCLUIR_REAL)
eq('(6a) ANTES del DROP: no aborta', err, None)
eq('(6a) … archiva las 54 y `archivado_en`, y NINGUN texto (quedan a NULL)',
   columnas_del_insert(insert), ARCHIVA | {'archivado_en'})
eq('(6a) 🔬 … que son 54', len(ARCHIVA), 54)
eq('(6a) 🔒 … y entre ellas TODAS las que leen las vistas y funciones', LEIDAS <= ARCHIVA, True)

r, err, insert, dichas = corre(viva, hist_despues, excluir=EXCLUIR_REAL)
eq('(6b) DESPUES del DROP: no aborta', err, None)
eq('(6b) … y archiva lo mismo', columnas_del_insert(insert), ARCHIVA | {'archivado_en'})

# 🔴 La mitad que prueba el ORDEN: con el DROP puesto y la llamada de antes (`crudo` solo),
#    la carga de Keepa se PARA. Es lo que pasaria si la migracion fuera antes que este codigo.
r, err, insert, dichas = corre(viva, hist_despues, excluir=('crudo',))
eq('(6c) 🔴 con el DROP y la llamada VIEJA, archivar ABORTA', err is not None, True)
eq('(6c) 🔴 … nombrando los 16 textos', all(t in (err or '') for t in TEXTOS), True)
eq('(6c) 🔒 … y sin escribir nada', insert, '')

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · archivar_foto, las columnas generadas y los textos de Keepa')
