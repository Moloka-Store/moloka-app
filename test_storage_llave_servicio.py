# -*- coding: utf-8 -*-
"""Banco: ningun workflow entra en los almacenes cerrados con la llave PUBLICABLE.

POR QUE EXISTE (12-nov-2026). El PR #389 (fusionado en 1374d94) paso 21
workflows que leen o escriben en `informes` y `facturas-pdfs` de la llave
publicable (`secrets.SUPABASE_KEY`, rol anon) a la de servicio: 24 lineas
`SUPABASE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}`. Ese mismo dia, a las
10:21, se cerraron en produccion `informes`, `facturas-pdfs` y `fotos-fabrica`
a anon y public. Desde entonces, con la publicable, LISTAR DEVUELVE `[]` y
SUBIR DA 403.

🔴 EL PELIGRO NO ES EL 403: ES EL LISTADO VACIO. Un workflow que volviera a la
publicable no abriria nada, pero leeria el buzon VACIO y saldria en VERDE sin
procesar. El caso que mas importa es la carga diaria de Keepa
(`procesar-keepa-escaparate`): «no habia ficheros» se lee igual que «no hay
nada nuevo». La revision del #389 dejo dicho que ningun test lo impedia. Este
es ese test.

QUE MIRA, Y POR ESTRUCTURA (no con una lista a mano que se quede vieja):
  1. Cada paso de cada workflow de `.github/workflows/`: que guion lanza su
     `run:` (`python [-u] X.py`), con el env que le llega (workflow + job +
     paso, ganando el mas cercano, como en Actions).
  2. Cada guion, con `ast` sobre el fichero real (nunca importandolo: estos
     guiones se conectan al importarse): toda llamada `<cliente>.storage.from_(
     <almacen>)`, siguiendo:
       - el almacen hasta su valor: literal, constante de modulo (tambien en
         tupla, `BUCKET, CARPETA = 'informes', ...`), variable de bucle, o el
         valor por defecto de un `os.environ.get('BUCKETS', '...')`;
       - las funciones auxiliares que reciben el cliente o el almacen como
         PARAMETRO (`listar_buzon(sb, BUCKET, ...)` de foto_comun,
         `fichero_en_storage`, `_bajar` de robot_preparar, `subir(admin, ...)`):
         se resuelven en cada sitio que las llama, con sus argumentos. Sin
         esto, los 8 procesadores no tocan el Storage «a la vista»;
       - los imports locales, tambien los de dentro de `main()`, y los
         clientes de otro modulo (`R.sb` de robot_lote);
       - el cliente hasta su `create_client(url, LLAVE)` (o `cliente(...)` de
         escaner2_base, o una funcion que lo devuelve), y la LLAVE hasta las
         variables de entorno que lee, en su orden de preferencia
         (`os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']`
         = primero la de servicio, luego la publicable).
  3. EL JUICIO VA POR CLIENTE, NO POR GUION. `robot_rehacer.py` tiene `sb` con
     la publicable (solo para tablas) y `admin` con la de servicio (el que
     toca el Storage): el que cuenta es el que llega al almacen.
  4. Con la variable que ese cliente lee PRIMERO de las que el paso le pasa,
     el secreto tiene que ser EXACTAMENTE `${{ secrets.SUPABASE_SERVICE_KEY }}`.
     Cualquier otra cosa es ROJO: la publicable, ninguna llave, o una
     expresion que no se sabe leer.

LOS TRES DEL `or` (moloka_actualizar_tcg, moloka_tracker_snapshot_nube,
moloka_tracker_cerebro) NO estan en ninguna lista: pasan por lo que hacen. Su
cliente lee primero `SUPABASE_SERVICE_KEY`, el paso se la pasa, y por eso entra
con la de servicio. Si el paso dejara de pasarla, el `or` caeria a la
publicable y este banco se pondria rojo; si alguien invirtiera el `or`, tambien.
Las dos cosas se comprueban abajo, en (C).

🔴 LO QUE NO SE SABE CLASIFICAR SALE ROJO, NUNCA «NO TOCA». Un almacen que no se
puede resolver, un cliente cuyo origen no se ve, una llave que no se sabe de
donde sale, un `run:` con Python en linea que nombra el Storage, o un paso que
lanza un guion que no esta en el repo: todo eso es «sin clasificar» y para el
banco. Si un dia hace falta una excepcion, se anade aqui a proposito, con su
motivo; mientras no la haya, lo nuevo no pasa en silencio.
  Lo que SI se ignora, y por que: un cliente construido con una CLASE del
  propio repo (los dobles de los bancos) no es un cliente de Supabase, y un
  almacen resuelto que no es uno de los tres (escaner2, amz-crudos) no es
  asunto de este banco.

QUE NO MIRA: `index.html` (la v1 congelada, con la publicable escrita en la
pagina; fuera a proposito, ver el parte del #389) ni lo que un workflow haga
con `curl` sin Python (hoy ninguno toca `storage/v1`; si aparece, sale rojo).

LAS SECCIONES:
  (A) El censo de hoy, impreso: cada paso vigilado, su guion, sus almacenes,
      la variable que lee y el secreto que recibe. Rojo si alguno no es la de
      servicio o algo queda sin clasificar.
  (B) Contra el verde vacio: si el barrido no ve los dos pasos de
      `procesar-keepa-escaparate`, un paso que llegue a `facturas-pdfs` y otro
      a `fotos-fabrica`, el detector esta ciego y eso es un fallo. Cero
      incumplidores de cero pasos mirados es como miente esta clase de test.
  (C) Las dos direcciones, en memoria en cada pasada: el mismo detector,
      contra copias rotas a proposito, tiene que salir rojo y nombrar el
      workflow y el paso. Asi el CI demuestra en cada PR que el banco muerde.

Sin red, sin secretos y sin tocar la base: lee ficheros del repo. La raiz se
puede cambiar con la variable MOLOKA_RAIZ (los ensayos sobre copias de disco
corren ESTE MISMO fichero contra otra carpeta).
"""
import ast
import copy
import os
import re
import sys

import yaml

RAIZ = os.environ.get('MOLOKA_RAIZ') or os.path.dirname(os.path.abspath(__file__))
CARPETA_WF = os.path.join('.github', 'workflows')

ALMACENES_CERRADOS = frozenset({'informes', 'facturas-pdfs', 'fotos-fabrica'})
SECRETO_SERVICIO = 'SUPABASE_SERVICE_KEY'

# Los constructores de un cliente de Supabase: (modulo del import, nombre).
# `cliente` de escaner2_base es `create_client(url, llave)` con el reintento de
# PostgREST, mismos dos argumentos. Solo con ESE import cuenta: `cliente` de
# fabrica_cerebro es otra cosa (el de Anthropic).
CONSTRUCTORES = {('supabase', 'create_client'), ('escaner2_base', 'cliente')}

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_AMBITOS = _FUNCS + (ast.Lambda,)


# ===========================================================================
# EL MODELO DE UN FICHERO: ambitos, nombres y de donde sale cada uno
# ===========================================================================
class Modulo:
    def __init__(self, proyecto, nombre, fuente):
        self.proyecto = proyecto
        self.nombre = nombre
        self.arbol = ast.parse(fuente)
        # UNA sola pasada por el arbol: de cada nodo, su ambito; de cada ambito,
        # sus llamadas y sus ambitos anidados. Recorrer el arbol entero por cada
        # funcion resumida costaba 40 segundos.
        self.amb_de = {}                      # nodo -> ambito que lo encierra
        self.amb_padre = {}                   # ambito -> ambito que lo encierra
        self.llamadas_en = {self.arbol: []}   # ambito -> llamadas directas
        self.anidados = {self.arbol: []}      # ambito -> ambitos de dentro
        pila = [(self.arbol, self.arbol)]
        while pila:
            n, amb = pila.pop()
            for h in ast.iter_child_nodes(n):
                self.amb_de[h] = amb
                if isinstance(h, _AMBITOS):
                    self.amb_padre[h] = amb
                    self.anidados[amb].append(h)
                    self.llamadas_en[h] = []
                    self.anidados[h] = []
                    pila.append((h, h))
                else:
                    if isinstance(h, ast.Call):
                        self.llamadas_en[amb].append(h)
                    pila.append((h, amb))
        self._ambitos = {}
        self._cadenas = {}

    def _cadena_de_ambito(self, amb):
        if amb not in self._cadenas:
            self._cadenas[amb] = ([amb] + self._cadena_de_ambito(self.amb_padre[amb])
                                  if amb is not self.arbol else [self.arbol])
        return self._cadenas[amb]

    def cadena(self, nodo):
        """Los ambitos que encierran a `nodo`, de dentro a fuera, acabando en el modulo."""
        if nodo is self.arbol:
            return [self.arbol]
        return self._cadena_de_ambito(self.amb_de[nodo])

    def cadena_desde(self, ambito):
        return self._cadena_de_ambito(ambito)

    def llamadas(self, ambito):
        """Todas las llamadas de un ambito, las de sus funciones anidadas incluidas."""
        out, pila = [], [ambito]
        while pila:
            a = pila.pop()
            out.extend(self.llamadas_en[a])
            pila.extend(self.anidados[a])
        return out

    def ambito(self, nodo):
        """{nombre: [entradas]}, {param: indice} y los `global` de un ambito."""
        if nodo in self._ambitos:
            return self._ambitos[nodo]
        nombres, params, globales = {}, {}, set()
        if isinstance(nodo, _AMBITOS):
            a = nodo.args
            for i, p in enumerate(list(a.posonlyargs) + list(a.args)):
                params[p.arg] = i
            for p in a.kwonlyargs:
                params[p.arg] = None
        cuerpo = nodo.body if isinstance(nodo.body, list) else [nodo.body]

        def poner(nombre, entrada):
            nombres.setdefault(nombre, []).append(entrada)

        def destino(t, valor):
            if isinstance(t, ast.Name):
                poner(t.id, ('expr', valor, nodo) if valor is not None else ('opaco', 'destino sin valor'))
            elif isinstance(t, (ast.Tuple, ast.List)):
                if isinstance(valor, (ast.Tuple, ast.List)) and len(valor.elts) == len(t.elts):
                    for tt, vv in zip(t.elts, valor.elts):
                        destino(tt, vv)
                else:
                    for tt in t.elts:
                        destino(tt, None)

        pila = list(cuerpo)
        while pila:
            n = pila.pop()
            if isinstance(n, _FUNCS):
                poner(n.name, ('def', n))
                continue
            if isinstance(n, ast.ClassDef):
                poner(n.name, ('clase', n))
                continue
            if isinstance(n, ast.Lambda):
                continue
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    destino(t, n.value)
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                destino(n.target, n.value)
            elif isinstance(n, ast.NamedExpr):
                destino(n.target, n.value)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                if isinstance(n.target, ast.Name):
                    poner(n.target.id, ('iter', n.iter, nodo))
                else:
                    destino(n.target, None)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for it in n.items:
                    if it.optional_vars is not None:
                        destino(it.optional_vars, None)
            elif isinstance(n, ast.Import):
                for al in n.names:
                    if al.asname:
                        poner(al.asname, ('modulo', al.name))
                    else:
                        poner(al.name.split('.')[0], ('modulo', al.name.split('.')[0]))
            elif isinstance(n, ast.ImportFrom) and n.module:
                for al in n.names:
                    poner(al.asname or al.name, ('de', n.module, al.name))
            elif isinstance(n, ast.Global):
                globales.update(n.names)
            pila.extend(ast.iter_child_nodes(n))
        r = (nombres, params, globales)
        self._ambitos[nodo] = r
        return r

    def buscar(self, nombre, cadena):
        """Las entradas de `nombre` en el primer ambito de `cadena` que lo define."""
        for amb in cadena:
            nombres, params, globales = self.ambito(amb)
            if nombre in globales:
                continue
            if nombre in params:
                if isinstance(amb, _FUNCS) and params[nombre] is not None:
                    return [('param', amb, params[nombre], nombre)]
                return [('opaco', 'parametro %s de una lambda o solo-clave' % nombre)]
            if nombre in nombres:
                return nombres[nombre]
        return None

    def de_arriba(self, nombre):
        """Un nombre del nivel de modulo (para `R.sb` y `from M import x`)."""
        return self.ambito(self.arbol)[0].get(nombre)


class Proyecto:
    def __init__(self, raiz, fuentes_extra=None, base=None):
        """`base`: otro Proyecto ya leido cuyos modulos se reutilizan (los ensayos
        de (C) no vuelven a leer 170 ficheros). ⚠️ Un modulo sustituido en
        `fuentes_extra` solo se ve al LANZARLO; quien lo importe sigue viendo el
        original. Para los ensayos de (C) basta: ninguno sustituye un modulo
        que otro importe."""
        self.raiz = raiz
        self.extra = dict(fuentes_extra or {})
        self._mods = {}
        self._resumen = {}
        if base is not None:
            quitar = {k[:-3].replace('/', '.') for k in self.extra}
            self._mods = {k: v for k, v in base._mods.items() if k not in quitar}

    def modulo(self, nombre):
        """El modulo local `nombre` (fichero del repo), o None si no es nuestro."""
        if nombre in self._mods:
            return self._mods[nombre]
        rel = nombre.replace('.', '/') + '.py'
        m = None
        if rel in self.extra:
            m = Modulo(self, nombre, self.extra[rel])
        else:
            for base in ('', 'scripts'):
                ruta = os.path.join(self.raiz, base, rel)
                if os.path.isfile(ruta):
                    with open(ruta, encoding='utf-8') as fh:
                        m = Modulo(self, nombre, fh.read())
                    break
        self._mods[nombre] = m
        return m

    def modulo_por_ruta(self, rel):
        rel = rel.replace('\\', '/')
        if rel.startswith('./'):
            rel = rel[2:]
        if rel not in self.extra and not os.path.isfile(os.path.join(self.raiz, rel)):
            return None
        return self.modulo(rel[:-3].replace('/', '.'))


# ===========================================================================
# RESOLVER: cliente, llave, almacen y funcion llamada
# ===========================================================================
# Un cliente resuelto es una de estas tuplas:
#   ('cli', [variables de entorno en orden de preferencia] | None, sitio)
#   ('param', funcion, indice)     -> se resuelve en quien llama a la funcion
#   ('doble', sitio)               -> una clase del repo: no es Supabase
#   ('opaco', motivo)              -> SIN CLASIFICAR
# Un almacen resuelto:
#   ('nombres', frozenset), ('param', funcion, indice), ('opaco', motivo)
_PROF = 12


def _sitio(mod, nodo):
    return '%s.py:%d' % (mod.nombre.replace('.', '/'), getattr(nodo, 'lineno', 0))


def _es_constructor(mod, func, cadena):
    if isinstance(func, ast.Name):
        for e in mod.buscar(func.id, cadena) or []:
            if e[0] == 'de' and (e[1], e[2]) in CONSTRUCTORES:
                return True
    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
        for e in mod.buscar(func.value.id, cadena) or []:
            if e[0] == 'modulo' and (e[1], func.attr) in CONSTRUCTORES:
                return True
    return False


def resolver_funcion(mod, func, cadena, prof=0):
    """('def', modulo, nodo) | ('clase', modulo, nodo) | None."""
    if prof > _PROF:
        return None
    if isinstance(func, ast.Name):
        for e in mod.buscar(func.id, cadena) or []:
            if e[0] == 'def':
                return ('def', mod, e[1])
            if e[0] == 'clase':
                return ('clase', mod, e[1])
            if e[0] == 'de':
                m2 = mod.proyecto.modulo(e[1])
                if m2 is not None:
                    for e2 in m2.de_arriba(e[2]) or []:
                        if e2[0] in ('def', 'clase'):
                            return (e2[0], m2, e2[1])
            if e[0] == 'expr':
                r = resolver_funcion(mod, e[1], mod.cadena_desde(e[2]), prof + 1)
                if r:
                    return r
        return None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        for e in mod.buscar(func.value.id, cadena) or []:
            if e[0] == 'modulo':
                m2 = mod.proyecto.modulo(e[1])
                if m2 is not None:
                    for e2 in m2.de_arriba(func.attr) or []:
                        if e2[0] in ('def', 'clase'):
                            return (e2[0], m2, e2[1])
    return None


def _es_environ(mod, nodo, cadena, prof=0):
    if prof > _PROF:
        return False
    if isinstance(nodo, ast.Attribute) and nodo.attr == 'environ' and isinstance(nodo.value, ast.Name):
        return any(e[0] == 'modulo' and e[1] == 'os' for e in (mod.buscar(nodo.value.id, cadena) or []))
    if isinstance(nodo, ast.Name):
        ents = mod.buscar(nodo.id, cadena) or []
        if ents and all(e[0] == 'de' and e[1] == 'os' and e[2] == 'environ' for e in ents):
            return True
        return bool(ents) and all(e[0] == 'expr' and _es_environ(mod, e[1], mod.cadena_desde(e[2]), prof + 1)
                                  for e in ents)
    return False


def resolver_llave(mod, nodo, cadena, prof=0):
    """Las variables de entorno que lee la llave, en orden de preferencia, o None."""
    if prof > _PROF or nodo is None:
        return None
    if (isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant)
            and isinstance(nodo.slice.value, str) and _es_environ(mod, nodo.value, cadena)):
        return [nodo.slice.value]
    if isinstance(nodo, ast.Call) and nodo.args and isinstance(nodo.args[0], ast.Constant) \
            and isinstance(nodo.args[0].value, str):
        f = nodo.func
        if isinstance(f, ast.Attribute) and f.attr == 'get' and _es_environ(mod, f.value, cadena):
            return [nodo.args[0].value]
        if isinstance(f, ast.Attribute) and f.attr == 'getenv' and isinstance(f.value, ast.Name) \
                and any(e[0] == 'modulo' and e[1] == 'os' for e in (mod.buscar(f.value.id, cadena) or [])):
            return [nodo.args[0].value]
    if isinstance(nodo, ast.BoolOp) and isinstance(nodo.op, ast.Or):
        out = []
        for v in nodo.values:
            if isinstance(v, ast.Constant):
                continue                      # `... or ''`: no es una llave
            r = resolver_llave(mod, v, cadena, prof + 1)
            if r is None:
                return None
            out.extend(r)
        return out or None
    if isinstance(nodo, ast.Name):
        ents = mod.buscar(nodo.id, cadena)
        if not ents:
            return None
        rs = []
        for e in ents:
            if e[0] != 'expr':
                return None
            rs.append(resolver_llave(mod, e[1], mod.cadena_desde(e[2]), prof + 1))
        if any(r is None for r in rs) or any(r != rs[0] for r in rs):
            return None                       # dos asignaciones distintas: no se sabe cual gana
        return rs[0]
    return None


def resolver_cliente(mod, nodo, cadena, prof=0):
    if prof > _PROF:
        return [('opaco', 'demasiados saltos al seguir el cliente en ' + _sitio(mod, nodo))]
    if isinstance(nodo, ast.Name):
        ents = mod.buscar(nodo.id, cadena)
        if not ents:
            return [('opaco', 'no se ve de donde sale el cliente `%s` (%s)' % (nodo.id, _sitio(mod, nodo)))]
        out = []
        for e in ents:
            if e[0] == 'param':
                out.append(('param', e[1], e[2]))
            elif e[0] == 'expr':
                out.extend(resolver_cliente(mod, e[1], mod.cadena_desde(e[2]), prof + 1))
            elif e[0] == 'de':
                m2 = mod.proyecto.modulo(e[1])
                ents2 = m2.de_arriba(e[2]) if m2 is not None else None
                if ents2:
                    out.extend(resolver_cliente(m2, ast.Name(id=e[2], ctx=ast.Load(), lineno=0),
                                                [m2.arbol], prof + 1))
                else:
                    out.append(('opaco', 'cliente `%s` importado de fuera (%s)' % (nodo.id, _sitio(mod, nodo))))
            elif e[0] == 'clase':
                out.append(('doble', _sitio(mod, e[1])))
            else:
                out.append(('opaco', 'cliente `%s` sin clasificar (%s, %s)' % (nodo.id, e[0], _sitio(mod, nodo))))
        return out
    if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name):
        for e in mod.buscar(nodo.value.id, cadena) or []:
            if e[0] == 'modulo':
                m2 = mod.proyecto.modulo(e[1])
                if m2 is not None and m2.de_arriba(nodo.attr):
                    return resolver_cliente(m2, ast.Name(id=nodo.attr, ctx=ast.Load(), lineno=0),
                                            [m2.arbol], prof + 1)
        return [('opaco', 'cliente `%s.%s` sin clasificar (%s)' % (nodo.value.id, nodo.attr, _sitio(mod, nodo)))]
    if isinstance(nodo, ast.Call):
        if _es_constructor(mod, nodo.func, cadena):
            llave = nodo.args[1] if len(nodo.args) >= 2 else next(
                (k.value for k in nodo.keywords if k.arg in ('supabase_key', 'key', 'llave')), None)
            return [('cli', resolver_llave(mod, llave, cadena), _sitio(mod, nodo))]
        r = resolver_funcion(mod, nodo.func, cadena)
        if r and r[0] == 'clase':
            return [('doble', _sitio(r[1], r[2]))]
        if r and r[0] == 'def':
            m2, f2 = r[1], r[2]
            rets = [n for n in _descendientes_propios(f2) if isinstance(n, ast.Return) and n.value is not None]
            if not rets:
                return [('opaco', 'la funcion %s no devuelve cliente (%s)' % (f2.name, _sitio(mod, nodo)))]
            out = []
            for ret in rets:
                for c in resolver_cliente(m2, ret.value, m2.cadena(ret), prof + 1):
                    if c[0] == 'param' and c[1] is f2:
                        arg = _argumento(f2, c[2], nodo)
                        out.extend(resolver_cliente(mod, arg, cadena, prof + 1) if arg is not None
                                   else [('opaco', 'argumento %d de %s sin pasar' % (c[2], f2.name))])
                    else:
                        out.append(c)
            return out
    return [('opaco', 'cliente sin clasificar en ' + _sitio(mod, nodo))]


def _valores(mod, nodo, cadena, prof):
    """Los nombres de almacen que puede valer una expresion, o None si no se sabe.

    🔴 No vale «todos los textos que aparezcan dentro»: en `os.environ['ALMACEN']`
       el unico texto es el nombre de la VARIABLE, y tomarlo por el almacen daria
       «no toca» a un guion que no se sabe lo que toca. Por eso cada forma se lee
       por lo que es, y lo que no se reconoce devuelve None (sin clasificar)."""
    if prof > _PROF or nodo is None:
        return None
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return {x.strip() for x in nodo.value.split(',') if x.strip()}
    if isinstance(nodo, (ast.Name, ast.Attribute)):
        r = resolver_almacen(mod, nodo, cadena, prof + 1)
        return set(r[1]) if r[0] == 'nombres' else None
    if isinstance(nodo, (ast.List, ast.Tuple, ast.Set)):
        out = set()
        for e in nodo.elts:
            v = _valores(mod, e, cadena, prof + 1)
            if v is None:
                return None
            out |= v
        return out
    if isinstance(nodo, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        return _valores(mod, nodo.generators[0].iter, cadena, prof + 1)
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
        f = nodo.func
        if f.attr == 'get' and _es_environ(mod, f.value, cadena):
            # `os.environ.get('BUCKETS', 'facturas-pdfs,informes')`: se toma el valor
            # por defecto. Si el workflow pasara otra lista, este banco no la ve.
            return _valores(mod, nodo.args[1], cadena, prof + 1) if len(nodo.args) >= 2 else None
        if f.attr in ('split', 'strip', 'lower', 'upper', 'rstrip', 'lstrip'):
            return _valores(mod, f.value, cadena, prof + 1)
    return None


def _constantes(mod, nodo, cadena, prof):
    return _valores(mod, nodo, cadena, prof) or set()


def resolver_almacen(mod, nodo, cadena, prof=0):
    if prof > _PROF or nodo is None:
        return ('opaco', 'almacen sin argumento o demasiados saltos')
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return ('nombres', frozenset(x.strip() for x in nodo.value.split(',') if x.strip()))
    if isinstance(nodo, ast.Name):
        ents = mod.buscar(nodo.id, cadena)
        if not ents:
            return ('opaco', 'no se ve de donde sale el almacen `%s` (%s)' % (nodo.id, _sitio(mod, nodo)))
        nombres = set()
        for e in ents:
            if e[0] == 'param':
                if len(ents) == 1:
                    return ('param', e[1], e[2])
                return ('opaco', 'almacen `%s` mezcla parametro y valor' % nodo.id)
            if e[0] == 'expr':
                r = resolver_almacen(mod, e[1], mod.cadena_desde(e[2]), prof + 1)
            elif e[0] == 'iter':
                c = _constantes(mod, e[1], mod.cadena_desde(e[2]), prof)
                r = ('nombres', frozenset(c)) if c else ('opaco', 'bucle sin valores (%s)' % _sitio(mod, e[1]))
            elif e[0] == 'de':
                m2 = mod.proyecto.modulo(e[1])
                r = (resolver_almacen(m2, ast.Name(id=e[2], ctx=ast.Load(), lineno=0), [m2.arbol], prof + 1)
                     if m2 is not None and m2.de_arriba(e[2]) else ('opaco', 'almacen importado de fuera'))
            else:
                r = ('opaco', 'almacen `%s` sin clasificar (%s)' % (nodo.id, e[0]))
            if r[0] != 'nombres':
                return r
            nombres |= r[1]
        return ('nombres', frozenset(nombres))
    if isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name):
        for e in mod.buscar(nodo.value.id, cadena) or []:
            if e[0] == 'modulo':
                m2 = mod.proyecto.modulo(e[1])
                if m2 is not None and m2.de_arriba(nodo.attr):
                    return resolver_almacen(m2, ast.Name(id=nodo.attr, ctx=ast.Load(), lineno=0),
                                            [m2.arbol], prof + 1)
        return ('opaco', 'almacen `%s.%s` sin clasificar (%s)' % (nodo.value.id, nodo.attr, _sitio(mod, nodo)))
    c = _valores(mod, nodo, cadena, prof)
    if c:
        return ('nombres', frozenset(c))
    return ('opaco', 'almacen sin clasificar en ' + _sitio(mod, nodo))


def _argumento(f, indice, llamada):
    """La expresion que llega al parametro `indice` de `f` en `llamada` (o su default)."""
    a = f.args
    posicionales = list(a.posonlyargs) + list(a.args)
    nombre = posicionales[indice].arg
    if any(isinstance(x, ast.Starred) for x in llamada.args[:indice + 1]):
        return None
    if indice < len(llamada.args):
        return llamada.args[indice]
    for k in llamada.keywords:
        if k.arg == nombre:
            return k.value
    sin_default = len(posicionales) - len(a.defaults)
    if indice >= sin_default:
        return a.defaults[indice - sin_default]
    return None


def _descendientes_propios(f):
    """Los nodos del cuerpo de `f` sin bajar a funciones anidadas."""
    pila = list(f.body)
    while pila:
        n = pila.pop()
        yield n
        if isinstance(n, _FUNCS + (ast.ClassDef, ast.Lambda)):
            continue
        pila.extend(ast.iter_child_nodes(n))


def _llamada_storage(n):
    """`<cliente>.storage.from_(<almacen>)` -> (cliente, almacen) o None."""
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'from_'
            and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == 'storage'):
        return n.func.value.value, (n.args[0] if n.args else None)
    return None


# ===========================================================================
# LOS EFECTOS: que almacen toca cada funcion, con que cliente
# ===========================================================================
# Un efecto es (cliente_resuelto, almacen_resuelto, sitio). Con 'param' cuando
# depende de lo que le pase quien la llama.

def efectos(mod, ambito):
    """Los efectos de un ambito (una funcion, o el modulo entero), memorizados."""
    clave = (mod.nombre, id(ambito))
    pr = mod.proyecto
    if clave in pr._resumen:
        return pr._resumen[clave]
    pr._resumen[clave] = []                   # contra la recursion
    out = []
    for n in mod.llamadas(ambito):
        cadena = mod.cadena(n)
        st = _llamada_storage(n)
        if st is not None:
            alm = resolver_almacen(mod, st[1], cadena)
            for cli in resolver_cliente(mod, st[0], cadena):
                out.append((cli, alm, _sitio(mod, n)))
            continue
        r = resolver_funcion(mod, n.func, cadena)
        if not r or r[0] != 'def':
            continue
        m2, f2 = r[1], r[2]
        for cli, alm, sitio in efectos(m2, f2):
            if alm[0] == 'param' and alm[1] is f2:
                arg = _argumento(f2, alm[2], n)
                alm = (resolver_almacen(mod, arg, cadena) if arg is not None
                       else ('opaco', 'almacen: argumento %d de %s sin pasar' % (alm[2], f2.name)))
            if cli[0] == 'param' and cli[1] is f2:
                arg = _argumento(f2, cli[2], n)
                clis = (resolver_cliente(mod, arg, cadena) if arg is not None
                        else [('opaco', 'cliente: argumento %d de %s sin pasar' % (cli[2], f2.name))])
            else:
                clis = [cli]
            for c in clis:
                out.append((c, alm, '%s <- %s' % (sitio, _sitio(mod, n))))
    # Solo quedan los parametros de ESTE ambito. Un efecto que depende de un
    # parametro de OTRA funcion (una definida dentro de este cuerpo) ya aparece
    # resuelto en el sitio donde este cuerpo la llama; si nadie la llama, es
    # codigo muerto.
    limpio = [(cli, alm, sitio) for cli, alm, sitio in out
              if not (cli[0] == 'param' and cli[1] is not ambito)
              and not (alm[0] == 'param' and alm[1] is not ambito)]
    pr._resumen[clave] = limpio
    return limpio


def efectos_del_guion(mod):
    """Lo que hace el guion al lanzarse: todo su fichero (el `main()` incluido).
    Un efecto que aun depende de un parametro de una funcion del propio guion se
    descarta AQUI porque ya aparece resuelto en cada sitio que la llama; si
    nadie la llama, es codigo muerto."""
    out = []
    for cli, alm, sitio in efectos(mod, mod.arbol):
        if cli[0] == 'param' or alm[0] == 'param':
            continue
        if cli[0] == 'doble':
            continue
        if alm[0] == 'nombres' and not (alm[1] & ALMACENES_CERRADOS):
            continue
        out.append((cli, alm, sitio))
    return out


# ===========================================================================
# LOS WORKFLOWS: que lanza cada paso y con que env
# ===========================================================================
_LANZA = re.compile(r'(?:^|[\s;&|(])python3?(?:\s+-[A-Za-z]+)*\s+([\w./-]+\.py)\b')
_EN_LINEA = re.compile(r'(?:^|[\s;&|(])python3?(?:\s+-[A-Za-z]+)*\s+(?:-c\b|-\s)')
_SECRETO = re.compile(r'^\$\{\{\s*secrets\.(\w+)\s*\}\}$')


def _sin_comentarios_shell(texto):
    lineas = []
    for l in texto.splitlines():
        m = re.search(r'(^|\s)#', l)
        lineas.append(l[:m.start()] if m else l)
    return '\n'.join(lineas)


def _env(*capas):
    out = {}
    for c in capas:
        if isinstance(c, dict):
            out.update({str(k): v for k, v in c.items()})
    return out


# ---------------------------------------------------------------------------
# LAS EXCEPCIONES: lo que el banco no sabe clasificar y se ha mirado a mano.
# ---------------------------------------------------------------------------
# Clave: (guion que lanza el paso, motivo sin numeros de linea). Solo tapan un
# SIN CLASIFICAR, nunca un ROJO con la llave resuelta. Y si una deja de hacer
# falta, el banco se pone rojo tambien: una excepcion que no tapa nada es una
# puerta abierta para el siguiente.
EXCEPCIONES = {
    ('test_verificar_subida.py', 'almacen: argumento 1 de fichero_en_storage sin pasar'):
        'el banco de verificar_subida envuelve fichero_en_storage en una lambda `*a, **k` para '
        'ejecutar un trozo del escaner con un cliente de mentira (`Sb`, una clase del propio test); '
        'el workflow que lo lanza es el CI, sin ningun secreto.',
}


def _motivo(texto):
    return re.sub(r'\s*\([^()]*\.py:\d+[^()]*\)', '', texto).strip()


def revisar(proyecto, workflows, usadas=None):
    """workflows = {nombre: dict de yaml}. Devuelve (filas, fallos).

    Una fila por (workflow, paso, guion, cliente) que llega a un almacen cerrado.
    `usadas`, si se pasa, recoge las EXCEPCIONES que han tapado algo."""
    filas, fallos = [], []
    usadas = set() if usadas is None else usadas

    def sin_clasificar(etiqueta, guion, motivo):
        clave = (guion, _motivo(motivo))
        if clave in EXCEPCIONES:
            usadas.add(clave)
            return
        msg = 'SIN CLASIFICAR: %s -> %s: %s' % (etiqueta, guion, motivo)
        if msg not in fallos:
            fallos.append(msg)
    for wf_nombre in sorted(workflows):
        wf = workflows[wf_nombre]
        if not isinstance(wf, dict):
            continue
        for job_id, job in (wf.get('jobs') or {}).items():
            if not isinstance(job, dict):
                continue
            for i, paso in enumerate(job.get('steps') or [], 1):
                if not isinstance(paso, dict) or not isinstance(paso.get('run'), str):
                    continue
                etiqueta = '%s · job %s · paso «%s»' % (wf_nombre, job_id, paso.get('name') or paso.get('id') or '#%d' % i)
                run = _sin_comentarios_shell(paso['run'])
                if _EN_LINEA.search(run) and ('storage' in run or any(a in run for a in ALMACENES_CERRADOS)):
                    fallos.append('SIN CLASIFICAR: %s lleva Python en linea que nombra el Storage' % etiqueta)
                if 'storage/v1' in run:
                    fallos.append('SIN CLASIFICAR: %s llama a la API del Storage sin guion' % etiqueta)
                env = _env(wf.get('env'), job.get('env'), paso.get('env'))
                for guion in _LANZA.findall(run):
                    mod = proyecto.modulo_por_ruta(guion)
                    if mod is None:
                        fallos.append('SIN CLASIFICAR: %s lanza %s, que no esta en el repo' % (etiqueta, guion))
                        continue
                    vistos = {}
                    for cli, alm, sitio in efectos_del_guion(mod):
                        if alm[0] != 'nombres':
                            sin_clasificar(etiqueta, guion, alm[1])
                            continue
                        toca = '/'.join(sorted(alm[1] & ALMACENES_CERRADOS))
                        if cli[0] != 'cli':
                            sin_clasificar(etiqueta, guion, 'toca %s: %s' % (toca, cli[1]))
                            continue
                        if cli[1] is None:
                            sin_clasificar(etiqueta, guion, 'toca %s con un cliente cuya llave no se sabe leer (%s)'
                                           % (toca, cli[2]))
                            continue
                        k = (tuple(cli[1]), cli[2])
                        vistos.setdefault(k, set()).update(alm[1] & ALMACENES_CERRADOS)
                    for (prefs, ctor), almacenes in sorted(vistos.items()):
                        var = next((v for v in prefs if v in env), None)
                        valor = env.get(var) if var else None
                        m = _SECRETO.match(str(valor).strip()) if valor is not None else None
                        secreto = m.group(1) if m else None
                        fila = {'wf': wf_nombre, 'job': job_id, 'paso': etiqueta, 'guion': guion,
                                'almacenes': sorted(almacenes), 'prefs': list(prefs), 'cliente': ctor,
                                'var': var, 'secreto': secreto}
                        filas.append(fila)
                        if var is None:
                            fallos.append('ROJO: %s -> %s entra en %s con un cliente que lee %s, y el paso no le '
                                          'pasa ninguna' % (etiqueta, guion, '/'.join(fila['almacenes']),
                                                            ' o '.join(prefs)))
                        elif secreto != SECRETO_SERVICIO:
                            fallos.append('ROJO: %s -> %s entra en %s con %s = %s (cliente de %s); tiene que ser '
                                          '${{ secrets.%s }}' % (etiqueta, guion, '/'.join(fila['almacenes']), var,
                                                                  valor, ctor, SECRETO_SERVICIO))
    return filas, fallos


def cargar_workflows(raiz):
    carpeta = os.path.join(raiz, CARPETA_WF)
    out = {}
    for f in sorted(os.listdir(carpeta)):
        if f.endswith(('.yml', '.yaml')):
            with open(os.path.join(carpeta, f), encoding='utf-8') as fh:
                out[f] = yaml.safe_load(fh)
    return out


# ===========================================================================
# LOS ASSERTS
# ===========================================================================
FALLOS = []


def ok(nombre, cond, detalle=''):
    print(('  OK  ' if cond else '  FALLA  ') + nombre + ('' if cond or not detalle else '\n        ' + detalle))
    if not cond:
        FALLOS.append(nombre)


def main():
    print('Raiz: %s' % RAIZ)
    workflows = cargar_workflows(RAIZ)
    proyecto = Proyecto(RAIZ)
    usadas = set()
    filas, fallos = revisar(proyecto, workflows, usadas)

    # ── (A) El censo de hoy ────────────────────────────────────────────────
    print('\n(A) Pasos que llegan a un almacen cerrado (%s):' % ', '.join(sorted(ALMACENES_CERRADOS)))
    for f in filas:
        print('  %-34s %-32s %-26s lee %-38s <- %s'
              % (f['wf'], f['guion'], '+'.join(f['almacenes']), ' or '.join(f['prefs']),
                 'secrets.%s' % f['secreto'] if f['secreto'] else '(nada)'))
    wfs = sorted({f['wf'] for f in filas})
    pasos = sorted({(f['wf'], f['paso']) for f in filas})
    por_supabase_key = sorted({(f['wf'], f['paso']) for f in filas
                               if f['var'] == 'SUPABASE_KEY' and f['secreto'] == SECRETO_SERVICIO})
    print('\n  Vigilados: %d workflows, %d pasos.' % (len(wfs), len(pasos)))
    print('  De ellos, con la variable SUPABASE_KEY apuntando a la de servicio (los del #389): '
          '%d workflows, %d pasos.' % (len({w for w, _ in por_supabase_key}), len(por_supabase_key)))
    for x in fallos:
        print('    ' + x)
    ok('(A) ningun paso entra en un almacen cerrado sin la llave de servicio, y nada queda sin clasificar',
       not fallos, '%d problemas (arriba)' % len(fallos))
    for clave, porque in sorted(EXCEPCIONES.items()):
        print('  excepcion %s: %s' % ('usada' if clave in usadas else 'SIN USO', ' · '.join(clave)))
    sobran = sorted(set(EXCEPCIONES) - usadas)
    ok('(A) toda excepcion sigue tapando algo (una que sobra se quita)', not sobran, 'sobran: %r' % sobran)

    # ── (B) Contra el verde vacio ──────────────────────────────────────────
    keepa = [f for f in filas if f['wf'] == 'procesar-keepa-escaparate.yml']
    ok('(B) ve los DOS pasos de procesar-keepa-escaparate (procesador y encadenar)',
       {f['guion'] for f in keepa} >= {'procesador_keepa_escaparate.py', 'encadenar_keepa_escaparate.py'},
       'visto: %r' % sorted({f['guion'] for f in keepa}))
    for alm in sorted(ALMACENES_CERRADOS):
        ok('(B) ve al menos un paso que llega a `%s`' % alm, any(alm in f['almacenes'] for f in filas))

    # ── (C) Las dos direcciones, en memoria ────────────────────────────────
    def rojo(nombre, wfs_mod, extra=None, debe_nombrar=()):
        _, fs = revisar(Proyecto(RAIZ, extra, base=proyecto), wfs_mod)
        nombra = [x for x in fs if all(t in x for t in debe_nombrar)]
        ok(nombre, bool(nombra), 'fallos vistos: %r' % fs)
        if nombra:
            print('        -> ' + nombra[0])

    def paso_que_lanza(wfdict, guion):
        for job in wfdict['jobs'].values():
            for p in job.get('steps') or []:
                if isinstance(p, dict) and guion in str(p.get('run', '')):
                    return p
        raise AssertionError('no hay paso que lance ' + guion)

    k = 'procesar-keepa-escaparate.yml'
    w = copy.deepcopy(workflows)
    p = paso_que_lanza(w[k], 'procesador_keepa_escaparate.py')
    p['env']['SUPABASE_KEY'] = '${{ secrets.SUPABASE_KEY }}'
    rojo('(C1) keepa con la publicable -> ROJO, nombrando workflow y paso', w,
         debe_nombrar=('ROJO', k, p.get('name', ''), 'secrets.SUPABASE_KEY'))

    w = copy.deepcopy(workflows)
    del paso_que_lanza(w[k], 'encadenar_keepa_escaparate.py')['env']['SUPABASE_KEY']
    rojo('(C2) keepa (encadenar) sin ninguna llave -> ROJO', w, debe_nombrar=('ROJO', k, 'ninguna'))

    t = 'tracker-app.yml'
    w = copy.deepcopy(workflows)
    p = paso_que_lanza(w[t], 'moloka_tracker_snapshot_nube.py')
    p['env'].pop('SUPABASE_SERVICE_KEY', None)
    rojo('(C3) un `or` sin la de servicio en el paso cae a la publicable -> ROJO', w,
         debe_nombrar=('ROJO', t, 'secrets.SUPABASE_KEY'))

    g = 'moloka_actualizar_tcg.py'
    with open(os.path.join(RAIZ, g), encoding='utf-8') as fh:
        fuente = fh.read()
    invertida = fuente.replace("os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']",
                               "os.environ.get('SUPABASE_KEY') or os.environ['SUPABASE_SERVICE_KEY']")
    ok('(C4) [preparacion] el `or` de %s existe tal cual para invertirlo' % g, invertida != fuente)
    rojo('(C4) el mismo `or` al reves (prefiere la publicable) -> ROJO', workflows, extra={g: invertida},
         debe_nombrar=('ROJO', 'actualizar-tcg.yml', 'secrets.SUPABASE_KEY'))

    nuevo_guion = (
        "import os\n"
        "from supabase import create_client\n"
        "from foto_comun import listar_buzon\n"
        "ALMACEN = 'informes'\n"
        "def main():\n"
        "    sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])\n"
        "    print(listar_buzon(sb, ALMACEN, 'nuevo'))\n"
        "main()\n")
    w = copy.deepcopy(workflows)
    w['ensayo-nuevo.yml'] = {'jobs': {'j': {'steps': [{'name': 'lee el buzon', 'run': 'python -u ensayo_nuevo.py',
                                                         'env': {'SUPABASE_KEY': '${{ secrets.SUPABASE_KEY }}'}}]}}}
    rojo('(C5) un workflow nuevo que lee `informes` por listar_buzon con la publicable -> ROJO', w,
         extra={'ensayo_nuevo.py': nuevo_guion}, debe_nombrar=('ROJO', 'ensayo-nuevo.yml', 'lee el buzon'))

    w = copy.deepcopy(workflows)
    w['ensayo-opaco.yml'] = {'jobs': {'j': {'steps': [{'name': 'opaco', 'run': 'python ensayo_opaco.py'}]}}}
    opaco = ("import os, supabase\n"
             "def dame(): return supabase.create_client(os.environ['U'], llave_de_algun_sitio())\n"
             "dame().storage.from_(os.environ['ALMACEN']).list('x')\n")
    rojo('(C6) un almacen que no se sabe resolver -> SIN CLASIFICAR (rojo, no «no toca»)', w,
         extra={'ensayo_opaco.py': opaco}, debe_nombrar=('SIN CLASIFICAR', 'ensayo-opaco.yml'))

    # Y la otra direccion de (C): con todo en orden, callado. Es (A) en verde.
    print()
    if FALLOS:
        print('FALLAN %d:' % len(FALLOS))
        for f in FALLOS:
            print('  - ' + f)
        sys.exit(1)
    print('TODO OK: test_storage_llave_servicio')


if __name__ == '__main__':
    main()
