# -*- coding: utf-8 -*-
"""GENERA escaner2_heredado_*.py: las piezas del escaner viejo que usa el escaner 2, COPIADAS LITERALMENTE
(encargo B7, 25-sep-2026).

Uso, desde la raiz del repo:   python scripts/generar_escaner2_heredado.py . <commit>
  (el B7 los genero con el commit 2f9c06ae79b0a71cb7a3ee73127969546627f372)

Lee cada fichero del viejo del commit dado (`git show <commit>:<fichero>`) y copia cada pieza por
estructura (ast): sus lineas exactas y el bloque de comentarios pegado encima, con el origen (fichero,
lineas, commit, blob) y el md5 de su texto en una cabecera `# ── ORIGEN`. Nada se teclea.

🔴 SOLO CUANDO FERNANDO DECIDE HEREDAR UN CAMBIO DEL VIEJO: test_escaner2_heredado.py avisa si el viejo
   cambia; regenerar con un commit nuevo es la forma de heredarlo, y el diff del PR ensena que cambia.
   Necesita la historia de git (no corre en un checkout de profundidad 1) y el viejo en ese commit.
"""
import ast, hashlib, subprocess, sys, os

REPO = sys.argv[1]
COMMIT = sys.argv[2]
os.chdir(REPO)


def fuente(fichero):
    return subprocess.run(['git', 'show', '%s:%s' % (COMMIT, fichero)], capture_output=True, check=True).stdout.decode('utf-8')


def blob(fichero):
    return subprocess.run(['git', 'rev-parse', '%s:%s' % (COMMIT, fichero)], capture_output=True, check=True,
                          text=True).stdout.strip()


def nombres_asignados(n):
    out = []
    for t in n.targets:
        if isinstance(t, ast.Name):
            out.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            out += [e.id for e in t.elts if isinstance(e, ast.Name)]
    return out


def comentarios_encima(lineas, i0):
    """Indices (0-based) del bloque de comentarios pegado encima de la linea i0 (sin linea en blanco)."""
    i = i0 - 1
    while i >= 0 and lineas[i].lstrip().startswith('#'):
        i -= 1
    return i + 1


def pieza(fichero, texto, lineas, nodo, sha_blob, nota=None, desindentar=0):
    ini = comentarios_encima(lineas, nodo.lineno - 1)
    fin = nodo.end_lineno
    cuerpo = lineas[ini:fin]
    if desindentar:
        cuerpo = [l[desindentar:] if l.startswith(' ' * desindentar) else l for l in cuerpo]
    cab = '# ── ORIGEN: %s, líneas %d-%d · commit %s · blob %s · md5 %s ──' % (
        fichero, ini + 1, fin, COMMIT[:7], sha_blob[:10], md5_pieza(cuerpo))
    if nota:
        cab += '\n# ── ' + nota
    return (nodo.lineno, cab + '\n' + '\n'.join(cuerpo) + '\n')


def md5_pieza(lineas):
    """La huella del texto de la pieza TAL COMO QUEDA en el heredado (sin sus lineas de cabecera `# ──`):
    con ella el banco distingue «el heredado se ha tocado a mano» de «el viejo ha cambiado»."""
    return hashlib.md5('\n'.join(l.rstrip() for l in lineas).encode('utf-8')).hexdigest()


def superiores(texto):
    return ast.parse(texto).body


def por_nombre(fichero, defs, nombres, anidadas=(), extra=None):
    texto = fuente(fichero)
    lineas = texto.split('\n')
    sha = blob(fichero)
    arbol = ast.parse(texto)
    salida, vistos = [], set()
    for n in arbol.body:
        if isinstance(n, ast.FunctionDef) and n.name in defs:
            salida.append(pieza(fichero, texto, lineas, n, sha)); vistos.add(n.name)
        elif isinstance(n, ast.Assign) and set(nombres_asignados(n)) & set(nombres):
            salida.append(pieza(fichero, texto, lineas, n, sha)); vistos |= set(nombres_asignados(n)) & set(nombres)
    for nombre in anidadas:
        ns = [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.Assign)) and
              (getattr(n, 'name', None) == nombre or (isinstance(n, ast.Assign) and nombre in nombres_asignados(n)))]
        assert len(ns) == 1, (fichero, nombre, len(ns))
        n = ns[0]
        salida.append(pieza(fichero, texto, lineas, n, sha, desindentar=n.col_offset,
                            nota='(anidada en el original: aquí va sin su sangría de %d espacios, nada más)' % n.col_offset))
        vistos.add(nombre)
    faltan = (set(defs) | set(nombres) | set(anidadas)) - vistos
    assert not faltan, (fichero, faltan)
    if extra:
        salida += extra(texto, lineas, sha)
    return sorted(salida, key=lambda x: x[0]), sha


def escribir(nombre, doc, piezas, cabecera_codigo=''):
    with open(nombre, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# -*- coding: utf-8 -*-\n')
        fh.write('"""' + doc + '"""\n')
        if cabecera_codigo:
            fh.write(cabecera_codigo)
        for _l, t in piezas:
            fh.write('\n\n' + t)
    print(nombre, len(piezas), 'piezas')


# ───────────────────────── moloka_escaner_nube.py ─────────────────────────
DEFS_MOTOR = ('norm', '_num', 'partir_ean', 'clasificar', 'core_ean', 'clasificar_chase',
              '_chk13', '_ean_ok', '_gtin14_ok', 'rescatar_gtin', 'variantes_ean', 'aviso_caja_incoherente',
              'calc_rentabilidad', 'decision_de',
              '_sup', 'iva_es_con_origen', 'iva_es_de', 'origen_iva_fila', 'es_propio')
NOMBRES_MOTOR = ('PAISES', 'IVA_DEFAULT_ES', 'IVA_IT', 'IVA_FR', 'IVA_DE', 'ALMACEN',
                 'COM_DIGITALES', 'UNIDADES_CASE_TCG', 'ISD_PAIS', 'SIN_ISD_HISTORICO',
                 '_RE_SUFIJO', '_RE_CAJA6', '_RE_CHASE_NOM', '_RE_CON_CHASE',
                 'UMBRAL_CAJA_VS_SUELTA', 'ORIGEN_IVA_FICHA', 'ORIGEN_IVA_ASUMIDO', 'PERFILES')
DEFS_EXCEL = ('pct_comision_celda', 'en_bd_txt')
DEFS_ELECCION = ('_tok_cot', 'construir_idf', '_idf', '_distintivo', 'cotejar', 'elegir_candidato')
NOMBRES_ELECCION = ('UMBRAL_COTEJO',)
PARAMS_EXCEL = ('registros', 'problematicos', 'no_encontrados', 'chase_sueltos', '_dups', 'ambiguos', 'sin_rank',
                'chase_pendientes', 'cotejo_info', 'PROVEEDOR')


def celda9(texto, lineas, sha):
    """La Celda 9: desde los `import` de openpyxl que preceden a `COLS = …` hasta la sentencia anterior a
    `_sin_excel = …` (las mismas dos anclas que usaba escaner2_motor.sacar_bloque_excel), como FUNCION:
    una linea `def`, el cuerpo con 4 espacios mas de sangria y `return wb` al final."""
    cuerpo = ast.parse(texto).body
    def ancla(nombre):
        idx = [i for i, n in enumerate(cuerpo) if isinstance(n, ast.Assign) and nombre in nombres_asignados(n)]
        assert len(idx) == 1, nombre
        return idx[0]
    ini, fin = ancla('COLS'), ancla('_sin_excel')
    while ini > 0 and isinstance(cuerpo[ini - 1], (ast.Import, ast.ImportFrom)):
        ini -= 1
    l_ini = comentarios_encima(lineas, cuerpo[ini].lineno - 1)      # la cabecera «# Celda 9 - Excel final»
    l_fin = cuerpo[fin].lineno - 1                                  # hasta la linea anterior a `_sin_excel = …`
    while lineas[l_fin - 1].lstrip().startswith('#') or not lineas[l_fin - 1].strip():
        l_fin -= 1                                                  # sin la NOTA del guardado, que no es del bloque
    bloque = lineas[l_ini:l_fin]
    defl = 'def excel_del_viejo(%s):' % ', '.join(PARAMS_EXCEL)
    ind = ['    ' + l if l.strip() else '' for l in bloque]
    cuerpo_fn = [defl] + ind + ['    return wb']
    cab = ('# ── ORIGEN: moloka_escaner_nube.py, líneas %d-%d · commit %s · blob %s · md5 %s ──\n'
           '# ── La «Celda 9» del viejo, hecha FUNCION (encargo B7). Lo UNICO que cambia respecto al original:\n'
           '# ──   1) esta linea `def` con sus parametros (los datos que el bloque leia como globales);\n'
           '# ──   2) cada linea del bloque lleva 4 espacios mas de sangria (las vacias siguen vacias);\n'
           '# ──   3) `return wb` al final.\n'
           '# ── Todo lo demas (texto, formulas, formatos, anchos, semaforo, comentarios) es el del original.'
           % (l_ini + 1, l_fin, COMMIT[:7], sha[:10], md5_pieza(cuerpo_fn)))
    return [(cuerpo[ini].lineno, cab + '\n' + '\n'.join(cuerpo_fn) + '\n')]


piezas, sha_nube = por_nombre('moloka_escaner_nube.py', DEFS_MOTOR + DEFS_EXCEL + DEFS_ELECCION,
                              NOMBRES_MOTOR + NOMBRES_ELECCION, anidadas=('keyrank',), extra=celda9)
escribir('escaner2_heredado_nube.py',
         'ESCANER 2 · LO HEREDADO DE moloka_escaner_nube.py (el escaner viejo), COPIADO LITERALMENTE.\n\n'
         'Encargo B7 (25-sep-2026): el escaner 2 deja de leer el fichero del viejo. Cada pieza de aqui es el\n'
         'texto EXACTO del original en el commit %s (fichero con blob %s): mismas lineas, mismos nombres y\n'
         'mismos comentarios, con su origen encima. Generado por script desde `git show`, no tecleado.\n\n'
         '🔴 NO SE TOCA A MANO. Las formulas estan validadas (la rentabilidad empieza dividiendo las tarifas\n'
         '   de Amazon entre 1,21). Si el viejo cambia, test_escaner2_heredado.py lo avisa y decide Fernando.\n'
         '🔑 No se importa: escaner2_motor.py saca las piezas por nombre (`sacar_piezas`) y las ejecuta en un\n'
         '   espacio de nombres propio, igual que antes hacia con el fichero del viejo.\n'
         '   Unicas diferencias con el original: `keyrank` va sin su sangria (en el viejo esta dentro de un\n'
         '   `if`) y la Celda 9 es la funcion `excel_del_viejo` (ver su cabecera).\n' % (COMMIT[:7], sha_nube[:10]),
         piezas)

# ───────────────────────── moloka_escaner_pro.py ─────────────────────────
piezas, sha_pro = por_nombre('moloka_escaner_pro.py', ('norm', '_num_csv', 'leer_csv_visualizador'), ('CSV_COLS',))
escribir('escaner2_heredado_pro.py',
         'ESCANER 2 · LO HEREDADO DEL ESCANER PRO (moloka_escaner_pro.py), COPIADO LITERALMENTE.\n\n'
         'Encargo B7 (25-sep-2026). El lector del CSV del Visualizador de Keepa: `CSV_COLS`, `norm`, `_num_csv`\n'
         'y `leer_csv_visualizador`, texto EXACTO del commit %s (blob %s), generado por script.\n'
         'SI se importa (`import escaner2_heredado_pro as pro`), como antes el Escaner Pro.\n\n'
         '🔑 Del original solo se trae `csv` de su linea 9 (`import pandas as pd, csv`): es lo unico que usan\n'
         '   estas cuatro piezas, y asi el escaner 2 no necesita pandas para leer un CSV.\n'
         '🔴 NO SE TOCA A MANO: si el Pro cambia, test_escaner2_heredado.py lo avisa y decide Fernando.\n'
         % (COMMIT[:7], sha_pro[:10]),
         piezas, cabecera_codigo='\nimport csv  # ← moloka_escaner_pro.py, línea 9 (`import pandas as pd, csv`): solo `csv`\n')

# ───────────────────────── director_heo_prep.py ─────────────────────────
piezas, sha_dir = por_nombre('director_heo_prep.py', ('_quiere',), ('marcas', 'quiere_ofertas', 'marcas_reales', 'rank_max'))
escribir('escaner2_heredado_director.py',
         'ESCANER 2 · LO HEREDADO DEL DIRECTOR DE HEO (director_heo_prep.py), COPIADO LITERALMENTE.\n\n'
         'Encargo B7 (25-sep-2026). El filtro del modo «marcas»: las marcas de la regla y `_quiere`, texto\n'
         'EXACTO del commit %s (blob %s), generado por script. No se importa: escaner2_motor.py lo saca por\n'
         'nombre con la regla (`regla`) en su espacio de nombres, como antes hacia con el director.\n'
         '🔴 NO SE TOCA A MANO: si el director cambia, test_escaner2_heredado.py lo avisa y decide Fernando.\n'
         % (COMMIT[:7], sha_dir[:10]), piezas)


# ───────────────────────── descargar_heo.py ─────────────────────────
def descarga_extra(texto, lineas, sha):
    """Las sentencias de nivel superior desde la primera `import` hasta el final de
    `descargar_catalogo_heo` (el modulo que importa el barrido), y `TANDA`, que en el original vive
    dentro del `if __name__ == '__main__':`."""
    cuerpo = ast.parse(texto).body
    out = []
    for n in cuerpo:
        if isinstance(n, ast.FunctionDef) and n.name == 'descargar_catalogo_heo':
            out.append(pieza('descargar_heo.py', texto, lineas, n, sha))
            break
        if isinstance(n, ast.Expr) and isinstance(getattr(n, 'value', None), ast.Constant):
            continue                                                  # el docstring del modulo, si lo hubiera
        out.append(pieza('descargar_heo.py', texto, lineas, n, sha))
    tanda = [n for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.Assign) and 'TANDA' in nombres_asignados(n)]
    assert len(tanda) == 1
    out.append(pieza('descargar_heo.py', texto, lineas, tanda[0], sha, desindentar=tanda[0].col_offset,
                     nota='(en el original, dentro de `if __name__ == \'__main__\':` y `if HEO_FULL`: aquí va sin su '
                          'sangría de %d espacios, nada más; solo lo LEE `tanda_visualizador`)' % tanda[0].col_offset))
    return out


piezas, sha_des = por_nombre('descargar_heo.py', (), (), extra=descarga_extra)
escribir('escaner2_heredado_descarga.py',
         'ESCANER 2 · LO HEREDADO DE descargar_heo.py (la API de HEO), COPIADO LITERALMENTE.\n\n'
         'Encargo B7 (25-sep-2026). Todo el modulo hasta `descargar_catalogo_heo` incluida (imports, credenciales\n'
         'de Secrets, paginacion, traducciones, chase y el cruce de los tres endpoints) y la `TANDA` del\n'
         'Visualizador, texto EXACTO del commit %s (blob %s), generado por script. SI se importa: el barrido\n'
         'hace `from escaner2_heredado_descarga import descargar_catalogo_heo`, y cuenta el crudo y los sin GTIN\n'
         'con las MISMAS lineas de log de siempre.\n'
         'No se trae `COLS` ni `a_csv_bytes` (son del director viejo) ni el bloque `__main__` (solo su `TANDA`).\n'
         '🔴 NO SE TOCA A MANO: si descargar_heo.py cambia, test_escaner2_heredado.py lo avisa y decide Fernando.\n'
         % (COMMIT[:7], sha_des[:10]), piezas)

# ───────────────────────── procesador_keepa_escaparate.py ─────────────────────────
piezas, sha_esc = por_nombre('procesador_keepa_escaparate.py', (), ('TIPADAS',))
escribir('escaner2_heredado_escaparate.py',
         'ESCANER 2 · LO HEREDADO DEL PROCESADOR DEL ESCAPARATE (procesador_keepa_escaparate.py), COPIADO\n'
         'LITERALMENTE.\n\n'
         'Encargo B7 (25-sep-2026). `TIPADAS`: las cabeceras del export del Visualizador, copiadas de los exports\n'
         'reales; de aqui salen la del pais (`Localización`) y la de las caidas de 30 dias. Texto EXACTO del commit\n'
         '%s (blob %s), generado por script. No se importa: escaner2_motor.columnas_keepa lo saca por nombre.\n'
         '🔴 NO SE TOCA A MANO: si el procesador cambia, test_escaner2_heredado.py lo avisa y decide Fernando.\n'
         % (COMMIT[:7], sha_esc[:10]), piezas)
