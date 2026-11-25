# -*- coding: utf-8 -*-
"""LA TABLA ÚNICA DE LOS NOMBRES DE COLUMNA DEL CSV DE KEEPA.

QUÉ PASA. El Visualizador de Keepa en español ha cambiado ya dos veces los nombres de sus columnas, sin añadir
ni quitar ninguna y sin cambiar su orden: una equivalencia 1 a 1, medida comparando por posición los export
reales de los cuatro países.
  · 9-nov-2026 (el 8-nov aún entró con los nombres de siempre): 124 columnas cambian de nombre («Caja de
    Compra» pasa a «Buy Box», «Lista de precio» a «Precio recomendado»…), desaparece una que venía vacía
    («Clasificación de Ventas: Histórico») y cambian dos formatos de valor. Comparados los cuatro del 6-nov
    (561 columnas) con los cuatro del 9-nov (560).
  · 25-nov-2026: 52 columnas más («Localización» pasa a «Mercado», «Opiniones» a «Reseñas», «A.G.» a
    «agotado», «Caja de Compra Usado» a «Buy Box usada»…). Seis de ellas ya habían cambiado el 9-nov y
    vuelven a cambiar («Buy Box: 90 días A.G.» → «Buy Box: 90 días agotado»). «Encuesta» → «Encuadernación»
    es la misma columna: lo de antes era una mala traducción de binding. Comparados los del 24-nov con los
    del 25-nov, las dos veces 560 columnas. Y un valor: el plazo en singular se escribe ahora con tilde
    («0 día», «1 día»; antes «0 dia», «1 dia») en «Tiempo de envío» de la caja y en el retraso de Amazon.
    ⚠️ BORRADOR: eso aún NO se normaliza aquí; espera decisión.

QUÉ HACE ESTO. Devuelve el fichero a LOS NOMBRES Y FORMATOS DE SIEMPRE (los de antes del 9-nov) justo al leerlo,
antes de mirar ninguna columna. Cada nombre de cualquier generación va directo al MÁS ANTIGUO, en un solo paso.
Por eso `TIPADAS`, las claves de `keepa_escaparate.crudo` y las vistas que leen `crudo ->> '…'` (v_escaparate,
v_suficiencia_decision) no cambian ni una letra, y el histórico sigue siendo homogéneo. Lo usan los dos sitios
que leen el CSV: procesador_keepa_escaparate.py y el escáner 2 (escaner2_motor._leer_crudo y el lector
heredado, por su desvío en escaner2_desvios.py).

🔒 LA TABLA ES LITERAL, NO UNA REGLA DE «CAMBIA BUY BOX POR CAJA DE COMPRA». Es la regla de la casa que mató al
   PR #26 («ningún encabezado se conjetura») y aquí además sería falsa: el nombre de siempre de la comisión,
   «Comisión de referencia basada en el precio actual de la Buy Box», ya decía «Buy Box», y «Buy Box usada: …»
   vuelve a «Caja de Compra Usado: …», no a «Caja de Compra usada: …». Una columna que Keepa añada mañana se
   guarda con su nombre, sin inventarle otro.

🔒 UN FICHERO DE CUALQUIER GENERACIÓN SIGUE ENTRANDO: ningún nombre de siempre es clave de la tabla, y las claves
   del 9-nov se quedan aunque el 25-nov vuelvan a cambiar seis de ellas.
"""
from decimal import Decimal, InvalidOperation

# 🔑 NUEVO → EL DE SIEMPRE. Generada de los ficheros reales, por generaciones y en el orden en que aparecen en el CSV.
EQUIVALENCIAS = {
    # ── 9-nov-2026 (export del 6-nov contra los del 9-nov) ──
    'Buy Box: Actual': 'Caja de Compra: Actual',
    'Buy Box: Gastos de envío': 'Caja de Compra: Gastos de envío',
    'Buy Box: Promedio de 30 días': 'Caja de Compra: Promedio de 30 días',
    'Buy Box: Promedio de 90 días': 'Caja de Compra: Promedio de 90 días',
    'Buy Box: Promedio de 180 días': 'Caja de Compra: Promedio de 180 días',
    'Buy Box: Promedio de 365 días': 'Caja de Compra: Promedio de 365 días',
    'Buy Box: Caída de 1 día %': 'Caja de Compra: Caída de 1 día %',
    'Buy Box: Caída de 7 días %': 'Caja de Compra: Caída de 7 días %',
    'Buy Box: Caída de 30 días %': 'Caja de Compra: Caída de 30 días %',
    'Buy Box: Caída de 90 días %': 'Caja de Compra: Caída de 90 días %',
    'Buy Box: Caída desde la última visita': 'Caja de Compra: Caída desde la última visita',
    'Buy Box: Caída % desde la última visita': 'Caja de Compra: Caída % desde la última visita',
    'Buy Box: Última visita': 'Caja de Compra: Última visita',
    'Buy Box: Es el mínimo': 'Caja de Compra: Es el mínimo',
    'Buy Box: Es el mínimo en 90 días': 'Caja de Compra: Es el mínimo en 90 días',
    'Buy Box: El más bajo': 'Caja de Compra: El más bajo',
    'Buy Box: El más alto': 'Caja de Compra: El más alto',
    'Buy Box: Stock': 'Caja de Compra: Stock',
    'Buy Box: 90 días A.G.': 'Caja de Compra: 90 días A.G.',
    'Buy Box: Vendedor Buy Box': 'Caja de Compra: Vendedor Caja de Compra',
    'Buy Box: País de envío': 'Caja de Compra: País de envío',
    'Buy Box: Disponibilidad de la Buy Box': 'Caja de Compra: Disponibilidad de la Caja de Compra',
    'Buy Box: Tiempo de envío': 'Caja de Compra: Tiempo de envío',
    'Buy Box: Precio tachado': 'Caja de Compra: Precio tachado',
    'Buy Box: Tipo de precio tachado': 'Caja de Compra: Tipo de precio tachado',
    'Buy Box: % Amazon 30 días': 'Caja de Compra: % Amazon 30 días',
    'Buy Box: % Amazon 90 días': 'Caja de Compra: % Amazon 90 días',
    'Buy Box: % Amazon 180 días': 'Caja de Compra: % Amazon 180 días',
    'Buy Box: % Amazon 365 días': 'Caja de Compra: % Amazon 365 días',
    'Buy Box: % Mejor vendedor 30 días': 'Caja de Compra: % Mejor vendedor 30 días',
    'Buy Box: % Mejor vendedor 90 días': 'Caja de Compra: % Mejor vendedor 90 días',
    'Buy Box: % Mejor vendedor 180 días': 'Caja de Compra: % Mejor vendedor 180 días',
    'Buy Box: % Mejor vendedor 365 días': 'Caja de Compra: % Mejor vendedor 365 días',
    'Buy Box: Recuento de ganadores 30 días': 'Caja de Compra: Recuento de ganadores 30 días',
    'Buy Box: Recuento de ganadores 90 días': 'Caja de Compra: Recuento de ganadores 90 días',
    'Buy Box: Recuento de ganadores 180 días': 'Caja de Compra: Recuento de ganadores 180 días',
    'Buy Box: Recuento de ganadores 365 días': 'Caja de Compra: Recuento de ganadores 365 días',
    'Buy Box: Desviación estándar 30 días': 'Caja de Compra: Desviación estándar 30 días',
    'Buy Box: Desviación estándar 90 días': 'Caja de Compra: Desviación estándar 90 días',
    'Buy Box: Desviación estándar 365 días': 'Caja de Compra: Desviación estándar 365 días',
    'Buy Box: Capacidad de cambio 30 días': 'Caja de Compra: Capacidad de cambio 30 días',
    'Buy Box: Capacidad de cambio 90 días': 'Caja de Compra: Capacidad de cambio 90 días',
    'Buy Box: Capacidad de cambio 365 días': 'Caja de Compra: Capacidad de cambio 365 días',
    'Buy Box: Es FBA': 'Caja de Compra: Es FBA',
    'Buy Box: No calificado': 'Caja de Compra: No calificado',
    'Buy Box: Pre-ordenado': 'Caja de Compra: Pre-ordenado',
    'Buy Box: Pedido pendiente': 'Caja de Compra: Pedido pendiente',
    'Buy Box: Exclusivo Prime': 'Caja de Compra: Exclusivo Prime',
    'Buy Box: Prime elegible': 'Caja de Compra: Prime elegible',
    'Buy Box: Compra recurrente': 'Caja de Compra: Compra recurrente',
    'Recuento de ofertas elegibles para la Buy Box: Nuevo FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Nuevo FBA',
    'Recuento de ofertas elegibles para la Buy Box: Nuevo FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Nuevo FBM',
    'Recuento de ofertas elegibles para la Buy Box: Usado FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Usado FBA',
    'Recuento de ofertas elegibles para la Buy Box: Usado FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Usado FBM',
    'Recuento de ofertas elegibles para la Buy Box: De coleccionista FBA': 'Recuento de ofertas elegibles para la Caja de Compra: De coleccionista FBA',
    'Recuento de ofertas elegibles para la Buy Box: De coleccionista FBM': 'Recuento de ofertas elegibles para la Caja de Compra: De coleccionista FBM',
    'Recuento de ofertas elegibles para la Buy Box: Reacondicionado FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Reacondicionado FBA',
    'Recuento de ofertas elegibles para la Buy Box: Reacondicionado FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Reacondicionado FBM',
    'Nuevo, terceros FBA: Actual': 'Nuevo, de Vendedor Externo FBA: Actual',
    'Nuevo, terceros FBA: Promedio de 30 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 30 días',
    'Nuevo, terceros FBA: Promedio de 90 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 90 días',
    'Nuevo, terceros FBA: Promedio de 180 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 180 días',
    'Nuevo, terceros FBA: Promedio de 365 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 365 días',
    'Nuevo, terceros FBA: Caída de 1 día %': 'Nuevo, de Vendedor Externo FBA: Caída de 1 día %',
    'Nuevo, terceros FBA: Caída de 7 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 7 días %',
    'Nuevo, terceros FBA: Caída de 30 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 30 días %',
    'Nuevo, terceros FBA: Caída de 90 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 90 días %',
    'Nuevo, terceros FBA: Caída desde la última visita': 'Nuevo, de Vendedor Externo FBA: Caída desde la última visita',
    'Nuevo, terceros FBA: Caída % desde la última visita': 'Nuevo, de Vendedor Externo FBA: Caída % desde la última visita',
    'Nuevo, terceros FBA: Última visita': 'Nuevo, de Vendedor Externo FBA: Última visita',
    'Nuevo, terceros FBA: Es el mínimo': 'Nuevo, de Vendedor Externo FBA: Es el mínimo',
    'Nuevo, terceros FBA: Es el mínimo en 90 días': 'Nuevo, de Vendedor Externo FBA: Es el mínimo en 90 días',
    'Nuevo, terceros FBA: El más bajo': 'Nuevo, de Vendedor Externo FBA: El más bajo',
    'Nuevo, terceros FBA: El más alto': 'Nuevo, de Vendedor Externo FBA: El más alto',
    'Nuevo, terceros FBA: Stock': 'Nuevo, de Vendedor Externo FBA: Stock',
    'Nuevo, terceros FBM: Actual': 'Nuevo, de Vendedor Externo FBM: Actual',
    'Nuevo, terceros FBM: Promedio de 30 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 30 días',
    'Nuevo, terceros FBM: Promedio de 90 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 90 días',
    'Nuevo, terceros FBM: Promedio de 180 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 180 días',
    'Nuevo, terceros FBM: Promedio de 365 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 365 días',
    'Nuevo, terceros FBM: Caída de 1 día %': 'Nuevo, de Vendedor Externo FBM: Caída de 1 día %',
    'Nuevo, terceros FBM: Caída de 7 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 7 días %',
    'Nuevo, terceros FBM: Caída de 30 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 30 días %',
    'Nuevo, terceros FBM: Caída de 90 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 90 días %',
    'Nuevo, terceros FBM: Caída desde la última visita': 'Nuevo, de Vendedor Externo FBM: Caída desde la última visita',
    'Nuevo, terceros FBM: Caída % desde la última visita': 'Nuevo, de Vendedor Externo FBM: Caída % desde la última visita',
    'Nuevo, terceros FBM: Última visita': 'Nuevo, de Vendedor Externo FBM: Última visita',
    'Nuevo, terceros FBM: Es el mínimo': 'Nuevo, de Vendedor Externo FBM: Es el mínimo',
    'Nuevo, terceros FBM: Es el mínimo en 90 días': 'Nuevo, de Vendedor Externo FBM: Es el mínimo en 90 días',
    'Nuevo, terceros FBM: El más bajo': 'Nuevo, de Vendedor Externo FBM: El más bajo',
    'Nuevo, terceros FBM: El más alto': 'Nuevo, de Vendedor Externo FBM: El más alto',
    'Nuevo, terceros FBM: Stock': 'Nuevo, de Vendedor Externo FBM: Stock',
    'Warehouse Deals: Actual': 'Oferta de almacén: Actual',
    'Warehouse Deals: Promedio de 30 días': 'Oferta de almacén: Promedio de 30 días',
    'Warehouse Deals: Promedio de 90 días': 'Oferta de almacén: Promedio de 90 días',
    'Warehouse Deals: Promedio de 180 días': 'Oferta de almacén: Promedio de 180 días',
    'Warehouse Deals: Promedio de 365 días': 'Oferta de almacén: Promedio de 365 días',
    'Warehouse Deals: Caída de 1 día %': 'Oferta de almacén: Caída de 1 día %',
    'Warehouse Deals: Caída de 7 días %': 'Oferta de almacén: Caída de 7 días %',
    'Warehouse Deals: Caída de 30 días %': 'Oferta de almacén: Caída de 30 días %',
    'Warehouse Deals: Caída de 90 días %': 'Oferta de almacén: Caída de 90 días %',
    'Warehouse Deals: Caída desde la última visita': 'Oferta de almacén: Caída desde la última visita',
    'Warehouse Deals: Caída % desde la última visita': 'Oferta de almacén: Caída % desde la última visita',
    'Warehouse Deals: Última visita': 'Oferta de almacén: Última visita',
    'Warehouse Deals: Es el mínimo': 'Oferta de almacén: Es el mínimo',
    'Warehouse Deals: Es el mínimo en 90 días': 'Oferta de almacén: Es el mínimo en 90 días',
    'Warehouse Deals: El más bajo': 'Oferta de almacén: El más bajo',
    'Warehouse Deals: El más alto': 'Oferta de almacén: El más alto',
    'Precio recomendado: Actual': 'Lista de precio: Actual',
    'Precio recomendado: Promedio de 30 días': 'Lista de precio: Promedio de 30 días',
    'Precio recomendado: Promedio de 90 días': 'Lista de precio: Promedio de 90 días',
    'Precio recomendado: Promedio de 180 días': 'Lista de precio: Promedio de 180 días',
    'Precio recomendado: Promedio de 365 días': 'Lista de precio: Promedio de 365 días',
    'Precio recomendado: Caída de 1 día %': 'Lista de precio: Caída de 1 día %',
    'Precio recomendado: Caída de 7 días %': 'Lista de precio: Caída de 7 días %',
    'Precio recomendado: Caída de 30 días %': 'Lista de precio: Caída de 30 días %',
    'Precio recomendado: Caída de 90 días %': 'Lista de precio: Caída de 90 días %',
    'Precio recomendado: Caída desde la última visita': 'Lista de precio: Caída desde la última visita',
    'Precio recomendado: Caída % desde la última visita': 'Lista de precio: Caída % desde la última visita',
    'Precio recomendado: Última visita': 'Lista de precio: Última visita',
    'Precio recomendado: Es el mínimo': 'Lista de precio: Es el mínimo',
    'Precio recomendado: Es el mínimo en 90 días': 'Lista de precio: Es el mínimo en 90 días',
    'Precio recomendado: El más bajo': 'Lista de precio: El más bajo',
    'Precio recomendado: El más alto': 'Lista de precio: El más alto',
    # ── 25-nov-2026 (export del 24-nov contra los del 25-nov) ──
    'Mercado': 'Localización',
    'Clasificación de Ventas: Clasificaciones de Ventas por subcategoría': 'Clasificación de Ventas: Subcategoría Clasificación de Ventas',
    'Reseñas: Valoraciones': 'Opiniones: Valoraciones',
    'Reseñas: Cantidad de valoraciones': 'Opiniones: Cantidad de valoraciones',
    'Reseñas: Cantidad de valoraciones - Promedio de 30 días': 'Opiniones: Cantidad de valoraciones - Promedio de 30 días',
    'Reseñas: Cantidad de valoraciones - Promedio de 90 días': 'Opiniones: Cantidad de valoraciones - Promedio de 90 días',
    'Reseñas: Cantidad de valoraciones - Promedio de 180 días': 'Opiniones: Cantidad de valoraciones - Promedio de 180 días',
    'Reseñas: Cantidad de valoraciones - Promedio de 365 días': 'Opiniones: Cantidad de valoraciones - Promedio de 365 días',
    'Reseñas: Cantidad de valoraciones - Caída de 1 día %': 'Opiniones: Cantidad de valoraciones - Caída de 1 día %',
    'Reseñas: Cantidad de valoraciones - Caída de 7 días %': 'Opiniones: Cantidad de valoraciones - Caída de 7 días %',
    'Reseñas: Cantidad de valoraciones - Caída de 30 días %': 'Opiniones: Cantidad de valoraciones - Caída de 30 días %',
    'Reseñas: Cantidad de valoraciones - Caída de 90 días %': 'Opiniones: Cantidad de valoraciones - Caída de 90 días %',
    'Reseñas: Recuento de reseñas - Específico del formato': 'Opiniones: Recuento de Revisiones - Específico del formato',
    'Buy Box: 90 días agotado': 'Caja de Compra: 90 días A.G.',
    'Buy Box: Flipability 30 días': 'Caja de Compra: Capacidad de cambio 30 días',
    'Buy Box: Flipability 90 días': 'Caja de Compra: Capacidad de cambio 90 días',
    'Buy Box: Flipability 365 días': 'Caja de Compra: Capacidad de cambio 365 días',
    'Buy Box: Preventa': 'Caja de Compra: Pre-ordenado',
    'Buy Box: Suscríbete y ahorra': 'Caja de Compra: Compra recurrente',
    'Amazon: 90 días agotado': 'Amazon: 90 días A.G.',
    'Amazon: Veces agotado 30 días': 'Amazon: Contador A.G. 30 días',
    'Amazon: Veces agotado 90 días': 'Amazon: Contador A.G. 90 días',
    'Nuevo: 90 días agotado': 'Nuevo: 90 días A.G.',
    '% de tarifa por referencia': '% de comisión de referencia',
    'Tarifa por referencia basada en el precio actual de la Buy Box': 'Comisión de referencia basada en el precio actual de la Buy Box',
    'Ofertas flash: Actual': 'Oferta flash: Actual',
    'Ofertas flash: Es el mínimo': 'Oferta flash: Es el mínimo',
    'Ofertas flash: Es el mínimo en 90 días': 'Oferta flash: Es el mínimo en 90 días',
    'Buy Box usada: Actual': 'Caja de Compra Usado: Actual',
    'Buy Box usada: Promedio de 30 días': 'Caja de Compra Usado: Promedio de 30 días',
    'Buy Box usada: Promedio de 90 días': 'Caja de Compra Usado: Promedio de 90 días',
    'Buy Box usada: Promedio de 180 días': 'Caja de Compra Usado: Promedio de 180 días',
    'Buy Box usada: Promedio de 365 días': 'Caja de Compra Usado: Promedio de 365 días',
    'Buy Box usada: Caída de 1 día %': 'Caja de Compra Usado: Caída de 1 día %',
    'Buy Box usada: Caída de 7 días %': 'Caja de Compra Usado: Caída de 7 días %',
    'Buy Box usada: Caída de 30 días %': 'Caja de Compra Usado: Caída de 30 días %',
    'Buy Box usada: Caída de 90 días %': 'Caja de Compra Usado: Caída de 90 días %',
    'Buy Box usada: Caída desde la última visita': 'Caja de Compra Usado: Caída desde la última visita',
    'Buy Box usada: Caída % desde la última visita': 'Caja de Compra Usado: Caída % desde la última visita',
    'Buy Box usada: Última visita': 'Caja de Compra Usado: Última visita',
    'Buy Box usada: Es el mínimo': 'Caja de Compra Usado: Es el mínimo',
    'Buy Box usada: Es el mínimo en 90 días': 'Caja de Compra Usado: Es el mínimo en 90 días',
    'Buy Box usada: El más bajo': 'Caja de Compra Usado: El más bajo',
    'Buy Box usada: El más alto': 'Caja de Compra Usado: El más alto',
    'Buy Box usada: Buy Box usada Vendedor': 'Caja de Compra Usado: Caja de Compra Usado Vendedor',
    'Buy Box usada: Es FBA': 'Caja de Compra Usado: Es FBA',
    'Buy Box usada: Condición': 'Caja de Compra Usado: Condición',
    'Usado: 90 días agotado': 'Usado: 90 días A.G.',
    'ASIN principal': 'ASIN Padre',
    'Frec. comprados juntos': 'Frecuencia comprados juntos',
    'Encuadernación': 'Encuesta',
    'Cupón de un sólo uso: Suscríbete y ahorra %': 'Cupón de un sólo uso: Compra recurrente %',
}

# EL DE SIEMPRE → los nombres que ha tenido después, por orden de generación. Solo para los avisos.
_NUEVOS_DE = {}
for _nuevo, _antiguo in EQUIVALENCIAS.items():
    _NUEVOS_DE.setdefault(_antiguo, []).append(_nuevo)
del _nuevo, _antiguo

# La que desaparece. 🔬 Vacía en las 2.405 filas de los cuatro export del 6-nov: nadie la lee, y `crudo` conserva la clave.
COLUMNA_RETIRADA = 'Clasificación de Ventas: Histórico'

# Los dos valores que cambian de formato, por su nombre de siempre (la cabecera ya viene traducida).
COL_PLAZO_CAJA = 'Caja de Compra: Tiempo de envío'
COL_PRECIO_INFERIOR = 'Precio inferior sugerido'
PLAZO_SIN_DATO_NUEVO = '0 dia'

_BOM, _NBSP = chr(0xFEFF), chr(0xA0)


class CabeceraAmbigua(ValueError):
    """Dos columnas del fichero acaban con el mismo nombre al traducirlo (p. ej. el nombre nuevo y el antiguo de
    una misma columna, o los de dos generaciones): no se elige."""


def _limpia(texto):
    return ('' if texto is None else str(texto)).replace(_BOM, '').replace(_NBSP, ' ').strip()


def nombre_para_aviso(antiguo):
    """Cómo se nombra una columna que falta: con todos los nombres que ha tenido, para que el aviso sirva con
    un fichero de cualquier generación."""
    nuevos = _NUEVOS_DE.get(antiguo)
    if not nuevos:
        return "'%s'" % antiguo
    return "'%s' (o %s)" % (antiguo, ', '.join("'%s'" % n for n in nuevos))


def normalizar_cabecera(cabecera):
    """La cabecera con los nombres de siempre. Sin BOM ni espacios sobrantes.

    🔴 Si al traducirla un nombre sale repetido, CabeceraAmbigua: dos columnas con el mismo nombre y una
       taparía a la otra sin que nadie se enterase. Pasa con el nombre nuevo y el antiguo de una columna, con
       los de dos generaciones, y también con un nombre que venga dos veces tal cual. Las celdas de cabecera
       vacías no cuentan."""
    limpias = [_limpia(h) for h in cabecera]
    salida = [EQUIVALENCIAS.get(h, h) for h in limpias]
    origenes = {}
    for h, t in zip(limpias, salida):
        if t:
            origenes.setdefault(t, []).append(h)
    choques = [hs for hs in origenes.values() if len(hs) > 1]
    if choques:
        raise CabeceraAmbigua('El CSV trae la misma columna dos veces, con su nombre nuevo y con el antiguo o '
                              'repetida: '
                              + ', '.join(' y '.join("'%s'" % h for h in hs) for hs in choques)
                              + '. No se elige ninguna: vuelve a exportarlo de Keepa.')
    return salida


def normalizar_valor(cabecera_antigua, valor):
    """El valor con el formato de siempre. Solo toca las dos columnas que han cambiado; el resto, tal cual.

    · «Tiempo de envío» de la caja: antes vacío si no había plazo, ahora '0 dia'. 🔴 Solo ESTA columna:
      «Amazon: Retraso en el envío…» ya traía '0 dia' antes del cambio, y ahí es un dato.
    · «Precio inferior sugerido»: antes céntimos enteros (1898) y vacío; ahora euros (18.98) y '-'.
      Lo que no sean céntimos exactos se deja como viene: aquí no se redondea ni se adivina."""
    if cabecera_antigua == COL_PLAZO_CAJA:
        return '' if _limpia(valor) == PLAZO_SIN_DATO_NUEVO else valor
    if cabecera_antigua == COL_PRECIO_INFERIOR:
        texto = _limpia(valor)
        if texto == '-':
            return ''
        if '.' in texto:
            try:
                centimos = Decimal(texto) * 100
            except InvalidOperation:
                return valor
            if centimos == centimos.to_integral_value():
                return str(int(centimos))
        return valor
    return valor


def normalizar_export(cabecera, filas):
    """(cabecera, filas) del CSV, devueltas con los nombres y los formatos de siempre.

    Con un fichero de los de antes solo se limpia la cabecera. Con uno de los nuevos, además se añade al final
    la columna retirada, vacía: así la fila guardada tiene las mismas claves que las de antes."""
    limpias = [_limpia(h) for h in cabecera]
    es_nueva = any(h in EQUIVALENCIAS for h in limpias)
    salida = normalizar_cabecera(limpias)
    a_tocar = [(i, h) for i, h in enumerate(salida) if h in (COL_PLAZO_CAJA, COL_PRECIO_INFERIOR)]
    anadir_retirada = es_nueva and COLUMNA_RETIRADA not in salida
    n = len(salida)
    resultado = []
    for fila in filas:
        nueva = list(fila)
        for i, h in a_tocar:
            if i < len(nueva):
                nueva[i] = normalizar_valor(h, nueva[i])
        if anadir_retirada:
            # Primero a la medida de la cabecera, para que el vacío caiga en SU columna.
            nueva = (nueva + [''] * n)[:n] + ['']
        resultado.append(nueva)
    if anadir_retirada:
        salida = salida + [COLUMNA_RETIRADA]
    return salida, resultado
