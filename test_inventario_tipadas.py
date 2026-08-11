# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS del inventario de columnas de procesador_keepa_escaparate.

Qué prueba y qué NO:
  · SÍ: que la guarda SALTA en los cuatro estropicios posibles y que **nombra** el
        culpable en cada uno. Ejecuta el TEXTO REAL extraído del .py por anclas —
        no una copia retecleada, que es la trampa clásica de este tipo de banco.
  · SÍ: que con el fichero como está HOY no salta (si no, el procesador no arranca).
  · NO: nada del CSV ni de la base. Esta guarda se dispara antes de tocar los dos.

🔑 EL CASO QUE JUSTIFICA TODO ESTO es el 5: el RENOMBRADO. La cuenta sigue dando 64
   y el contador viejo lo daba por bueno, mientras el dato se escribía en otra
   columna. Es el único de los cinco que el `assert len(TIPADAS) == 61` no veía —
   y es el caro, porque no rebota: entra mal.

Se lanza solo:  python test_inventario_tipadas.py
"""
import io, os, sys, contextlib

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_keepa_escaparate.py')

# ── El texto REAL, por anclas. Si alguien mueve el bloque, esto revienta aquí y no
#    en silencio: un test que no encuentra lo que prueba tiene que gritar.
lineas = io.open(RUTA, encoding='utf-8').read().split('\n')
ini = [i for i, l in enumerate(lineas) if l.startswith('TIPADAS = [')][0]
fin = [i for i, l in enumerate(lineas) if l.startswith('_comprobar_inventario_tipadas()')][0]
BLOQUE = '\n'.join(lineas[ini:fin])
print(f"Bloque extraído del fichero real: líneas {ini+1}..{fin} "
      f"({BLOQUE.count(chr(10))} líneas)\n")

NS = {}
exec(compile(BLOQUE, '<inventario>', 'exec'), NS)
TIPADAS_REAL = list(NS['TIPADAS'])
comprobar = NS['_comprobar_inventario_tipadas']

fallos = []


def correr(titulo, tipadas, debe_saltar, tiene_que_nombrar=()):
    """Pone TIPADAS como se le diga, llama a la guarda y mira lo que dice."""
    NS['TIPADAS'] = tipadas
    salida = io.StringIO()
    salto = False
    with contextlib.redirect_stdout(salida):
        try:
            comprobar()
        except SystemExit:
            salto = True
    texto = salida.getvalue()

    if salto != debe_saltar:
        fallos.append(f"{titulo}: se esperaba salto={debe_saltar} y fue {salto}")
        print(f"  ❌ {titulo}: salto={salto}, se esperaba {debe_saltar}")
        return
    perdidos = [n for n in tiene_que_nombrar if n not in texto]
    if perdidos:
        fallos.append(f"{titulo}: no nombró {perdidos}")
        print(f"  ❌ {titulo}: la guarda saltó pero NO nombró {perdidos}")
        return
    # 🔒 Y que no eche la culpa al fichero: es la mitad del arreglo del 11-ago.
    if salto and 'EL FICHERO DE KEEPA ESTÁ BIEN' not in texto:
        fallos.append(f"{titulo}: no exculpa al fichero")
        print(f"  ❌ {titulo}: saltó sin decir que el fichero está bien")
        return
    print(f"  ✅ {titulo}"
          + (f" → nombra {list(tiene_que_nombrar)}" if tiene_que_nombrar else ""))


print(f"TIPADAS declara {len(TIPADAS_REAL)} columnas · el inventario espera "
      f"{len(NS['COLUMNAS_ESPERADAS'])}\n")

# 1. La verdad de hoy: con el fichero tal cual, la guarda NO salta.
correr("1. Como está hoy: no salta", list(TIPADAS_REAL), False)

# 2. SOBRA una: alguien añade a TIPADAS y no toca el inventario. Es LITERALMENTE
#    lo que pasó el 11-ago con bb_envio, bb_pais_envio y bb_plazo_txt.
correr("2. Sobra una en TIPADAS",
       TIPADAS_REAL + [('Cabecera Inventada', 'columna_intrusa', 't')],
       True, ('columna_intrusa',))

# 3. FALTA una: alguien la borra de TIPADAS y el inventario la sigue esperando.
correr("3. Falta una en TIPADAS",
       [t for t in TIPADAS_REAL if t[1] != 'tarifa_fba'],
       True, ('tarifa_fba',))

# 4. DUPLICADA: el conjunto cuadra y aun así está mal. Un `set` lo taparía.
correr("4. Duplicada dentro de TIPADAS",
       TIPADAS_REAL + [('Otra Cabecera', 'bb_precio', 'n')],
       True, ('bb_precio',))

# 5. 🔑 RENOMBRADO — el que el contador daba por bueno. Siguen siendo 64.
renombrado = [(h, 'bb_envio_typo' if c == 'bb_envio' else c, t) for h, c, t in TIPADAS_REAL]
assert len(renombrado) == len(TIPADAS_REAL), "el renombrado no debe cambiar la cuenta"
correr("5. RENOMBRADO (misma cuenta, columna distinta)",
       renombrado, True, ('bb_envio_typo', 'bb_envio'))

# 6. Y que el mensaje sirva para arreglarlo: dice dónde se toca.
NS['TIPADAS'] = TIPADAS_REAL + [('X', 'columna_intrusa', 't')]
salida = io.StringIO()
with contextlib.redirect_stdout(salida):
    try:
        comprobar()
    except SystemExit:
        pass
texto = salida.getvalue()
for exigido in ('COLUMNAS_ESPERADAS', 'NO vuelvas a exportarlo de Keepa',
                'keepa_escaparate_hist'):
    if exigido in texto:
        print(f"  ✅ 6. El mensaje dice «{exigido}»")
    else:
        fallos.append(f"6. el mensaje no dice «{exigido}»")
        print(f"  ❌ 6. El mensaje NO dice «{exigido}»")

print("\n" + "=" * 72)
if fallos:
    print(f"❌ {len(fallos)} FALLOS:")
    for f in fallos:
        print("   · " + f)
    sys.exit(1)
print("✅ Los seis casos pasan. La guarda salta cuando debe y NOMBRA al culpable.")
print("=" * 72)
