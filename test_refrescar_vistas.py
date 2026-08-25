# -*- coding: utf-8 -*-
"""El gancho del refresco de materializadas, visto ROJO y visto CALLADO.

🔴 POR QUE ESTE FICHERO EXISTE. `refrescar_vistas()` corre DESPUES del commit y no
   aborta nunca: si falla, la carga del informe ya esta escrita y lo unico que
   queda es el grito. O sea que un fallo suyo NO tumba el workflow -- se veria
   dias despues, cuando alguien mirase la pantalla y encontrase ventas viejas.
   Por eso lo que hay que probar aqui no es que funcione: es QUE GRITE, y que
   grite lo que hace falta para arreglarlo.

🔒 LAS DOS DIRECCIONES (§3 de CLAUDE.md): que hable cuando toca y que este callado
   cuando no. Un `return False` incondicional pasaria la mitad de arriba.

⚠️ Y la mitad mas facil de olvidar: **que NO avise a la app cuando el refresco
   fue mal**. Avisar entonces es peor que no avisar -- la app tira su cache,
   relee la copia VIEJA y la vuelve a cachear con sello nuevo: dato caducado
   disfrazado de fresco.
"""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import refrescar_vistas, REFRESCOS_POR_FUENTE  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK  ' if ok else 'XX  ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


class CursorFalso:
    """Se comporta como el cursor de psycopg2 en lo que esta funcion usa, y deja
    APUNTADO todo lo que se le pidio ejecutar."""

    def __init__(self, existe=True, dueno='postgres', quien='postgres', refresco_revienta=None):
        self.existe = existe
        self.dueno = dueno
        self.quien = quien
        self.refresco_revienta = refresco_revienta
        self.ejecutadas = []
        self._ultimo = None

    def execute(self, sql, args=None):
        self.ejecutadas.append(sql)
        s = sql.lower()
        if 'current_user' in s:
            self._ultimo = (self.quien,)
        elif 'to_regclass' in s:
            self._ultimo = ('algo' if self.existe else None,)
        elif 'pg_get_userbyid' in s:
            self._ultimo = (self.dueno,)
        elif 'refresh materialized view' in s:
            if self.refresco_revienta is not None:
                raise self.refresco_revienta
            self._ultimo = None
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo

    def close(self):
        pass


class ConexionFalsa:
    def __init__(self, cur):
        self._cur = cur
        self.autocommit = False

    def cursor(self):
        return self._cur


def corre(cur, fuente='ledger'):
    """Devuelve (resultado, lineas escritas)."""
    con = ConexionFalsa(cur)
    salida = []
    r = refrescar_vistas(con, fuente, escribir=salida.append)
    return r, '\n'.join(salida), con


print('== 1) EL CAMINO BUENO ==')
c = CursorFalso()
r, txt, con = corre(c)
eq('(1) devuelve True', r, True)
eq('(1) ha refrescado de verdad',
   any('refresh materialized view' in e.lower() for e in c.ejecutadas), True)
# 🔒 Sin el indice unico esto bloquearia a quien este leyendo la pantalla.
eq('(1) … sin bloquear a los lectores',
   any('concurrently' in e.lower() for e in c.ejecutadas), True)
# 🔴 Anclado en el ROTULO de esa linea, no en el valor: `postgres` sale TAMBIEN en la
#    linea del dueno, asi que buscarlo daba verde con la linea borrada. Cazado
#    rompiendolo. Es el patron de siempre: un assert que busca algo que aparece en dos
#    sitios no distingue cual de los dos falta.
eq('(1) 🔴 registra current_user SIEMPRE, no solo al fallar', 'conectado como' in txt, True)
eq('(1) … y dice cuanto tardo', 'ms' in txt, True)
eq('(1) 🔒 avisa a la app', '/api/cache/invalidar' in txt, True)
eq('(1) 🔒 y deja el autocommit como estaba', con.autocommit, False)

print('\n== 2) LA MV NO EXISTE TODAVIA (la migracion no se ha aplicado) ==')
c = CursorFalso(existe=False)
r, txt, _ = corre(c)
eq('(2) 🔴 devuelve False', r, False)
eq('(2) 🔴 … y NO intenta refrescar',
   any('refresh materialized view' in e.lower() for e in c.ejecutadas), False)
eq('(2) … diciendo que la migracion falta', 'no se ha aplicado' in txt.lower(), True)
# 🔴 Y lo que NO tiene que decir: que la carga haya fallado. El informe ya esta escrito.
eq('(2) 🔒 … y aclarando que la carga SI esta hecha',
   'el informe ya esta escrito' in txt.lower(), True)
eq('(2) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)

print('\n== 3) NO ES DUENO: REFRESH exige propiedad, no permisos ==')
c = CursorFalso(quien='otro_usuario', dueno='postgres',
                refresco_revienta=psycopg2.errors.InsufficientPrivilege(
                    'must be owner of materialized view mv_ventas_ventanas'))
r, txt, con = corre(c)
eq('(3) 🔴 devuelve False', r, False)
eq('(3) 🔴 dice QUIEN es', 'otro_usuario' in txt, True)
eq('(3) 🔴 … y QUIEN es el dueno', 'postgres' in txt, True)
eq('(3) … y el error exacto', 'must be owner' in txt, True)
eq('(3) 🔒 … y como se arregla', 'SECURITY' in txt, True)
eq('(3) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
eq('(3) 🔒 y deja el autocommit como estaba', con.autocommit, False)

print('\n== 4) UNA FUENTE QUE NO TIENE MATERIALIZADAS ==')
c = CursorFalso()
r, txt, _ = corre(c, fuente='keepa')
eq('(4) devuelve True (no hay nada que hacer)', r, True)
eq('(4) 🔒 y esta CALLADO: ni una linea', txt, '')
eq('(4) 🔒 … y no ha tocado la base', c.ejecutadas, [])

print('\n== 5) EL MAPA FUENTE -> MATERIALIZADAS ==')
# 🔴 Anclado sobre lo que tiene que estar: las dos fuentes de v_ventas_ventanas.
#    Si alguien anade una mv y olvida su fuente, el refresco no corre y no chilla
#    nadie -- este assert es el unico sitio donde eso se ve.
eq('(5) el ledger refresca las ventanas',
   'mv_ventas_ventanas' in REFRESCOS_POR_FUENTE.get('ledger', ()), True)
eq('(5) las transacciones tambien',
   'mv_ventas_ventanas' in REFRESCOS_POR_FUENTE.get('transacciones', ()), True)

print('\n== 6) LOS DOS PROCESADORES LO LLAMAN DE VERDAD ==')
# 🔴 Un CI verde no prueba que una feature este viva. `refrescar_vistas` puede estar
#    perfecta y no ejecutarse nunca.
# ⚠️ Sobre el codigo SIN comentarios: la cabecera del gancho NOMBRA la funcion, asi
#    que un grep sobre el fichero crudo daria verde con la llamada borrada.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
from censo_migraciones import sin_comentarios  # noqa: E402


def sin_almohadillas(texto):
    return '\n'.join(l for l in texto.split('\n') if not l.lstrip().startswith('#'))


for fichero, fuente in (('procesador_ledger.py', 'ledger'),
                        ('procesador_transacciones.py', 'transacciones')):
    with open(fichero, encoding='utf-8') as fh:
        codigo = sin_almohadillas(fh.read())
    eq('(6) %s llama al refresco con su fuente' % fichero,
       "refrescar_vistas(con, '%s')" % fuente in codigo, True)
    # 🔴 Y DENTRO DE LA RAMA DE `aplicar`, NO SOLO "DESPUES DEL COMMIT".
    #    Aqui hubo un assert mio que comparaba POSICIONES (`pos_refresco > pos_commit`)
    #    y habria pasado igual con el gancho puesto tras el `con.rollback()` de la rama
    #    de ENSAYO -- que es exactamente el error contra el que se escribio. Un ensayo
    #    con efectos secundarios deja de ser un ensayo: refrescaria y avisaria a la app
    #    por una corrida que no aplico nada.
    #    Se recorta la rama de `aplicar` y se mira DENTRO.
    ini = codigo.find("if MODO == 'aplicar':")
    fin = codigo.find('con.rollback()', ini)
    rama_aplicar = codigo[ini:fin] if ini != -1 and fin != -1 else ''
    eq('(6) el recorte de la rama aplicar trae codigo', len(rama_aplicar) > 0, True)
    eq('(6) 🔴 … y el refresco esta DENTRO de esa rama',
       'refrescar_vistas(' in rama_aplicar, True)
    # 🔒 Anclado sobre lo que NO debe haber: ni una llamada fuera de esa rama.
    eq('(6) 🔒 … y NO hay ninguna otra llamada suelta',
       codigo.count('refrescar_vistas(') , 1)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · gancho del refresco de materializadas')
