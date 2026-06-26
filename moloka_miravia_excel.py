# ==========================================================================
# MOLOKA · Generador del Excel de carga de Miravia
# --------------------------------------------------------------------------
# Rellena la plantilla oficial de Miravia (miravia_juguetes.xlsm) por debajo,
# dejando intactas sus hojas ocultas con los códigos internos.
# Coge de web_productos los marcados en_miravia=true que aún NO se han subido
# (miravia_subido IS NULL). NO toca Miravia: solo deja el .xlsm listo.
#
# Para GitHub Actions. El .xlsm resultante se sube como artifact del run.
# ==========================================================================
import os, sys, json
import openpyxl
from supabase import create_client

sys.stdout.reconfigure(line_buffering=True)

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

PLANTILLA = 'miravia_juguetes.xlsm'
SALIDA    = 'carga_miravia.xlsm'
HOJA      = 'Juguetesyfigurascolecciona'
FILA_INI  = 5   # filas 1-4 son cabeceras; los datos empiezan en la 5

# --- Valores fijos de Funko (verificados en la ficha hecha a mano por Elena) ---
CATID      = '62207655'
LOCAL      = 'es_ES'
MONEDA     = 'EUR'
ENVIO      = 'Enviado por Miravia (DBM)'
EDAD       = '3 - 4 años'
BATERIA    = 'No'
MATERIAL   = 'Vinilo'
CERT       = 'Certificado CE'
ADVERTENCIA = 'Sí'
ADV_TEXTO  = 'No apto para niños menores de 36 meses.'
FABRICANTE = 'FUNKO LLC'
RESP_UE    = 'Funko EU BV'
PESO       = 0.2
LARGO      = 9
ANCHO      = 12
ALTO       = 16
PELIGROSOS = 'Ninguno'

def set(ws, fila, col, valor):
    if valor not in (None, ''):
        ws.cell(row=fila, column=col, value=valor)

def main():
    # 1) Productos pendientes de subir a Miravia
    r = (sb.table('web_productos')
           .select('*')
           .eq('en_miravia', True)
           .is_('miravia_subido', 'null')
           .order('id')
           .execute())
    productos = r.data or []
    print(f">>> Productos marcados para Miravia y aún no subidos: {len(productos)}")
    if not productos:
        print("    Nada que generar. (Marca 🛒 en alguna ficha y vuelve a lanzar.)")
        return

    # 2) Cargar la plantilla preservando macros y hojas ocultas
    wb = openpyxl.load_workbook(PLANTILLA, keep_vba=True)
    ws = wb[HOJA]
    print(f">>> Plantilla cargada: {PLANTILLA}")

    avisos = []
    fila = FILA_INI
    for p in productos:
        nombre = p.get('miravia_titulo') or p.get('nombre') or ''
        ean    = p.get('ean') or ''
        slug   = p.get('slug') or ''
        precio = p.get('precio_miravia')
        stock  = p.get('stock')
        imgs   = p.get('miravia_imagenes') or []
        if isinstance(imgs, str):
            try: imgs = json.loads(imgs)
            except Exception: imgs = []

        # Avisos de calidad (para que sepas qué revisar antes de subir)
        if not nombre:  avisos.append(f"{ean or slug}: sin título de Miravia")
        if not precio:  avisos.append(f"{ean or slug}: sin precio_miravia")
        if not imgs:    avisos.append(f"{ean or slug}: sin imágenes")
        if not p.get('foto_caja'): avisos.append(f"{ean or slug}: sin foto de la caja (GPSR)")
        if stock in (None, 0):     avisos.append(f"{ean or slug}: stock {stock} (¿sincronizar?)")

        # --- Mapeo a las columnas de la plantilla ---
        set(ws, fila, 2,  CATID)                    # catId
        set(ws, fila, 3,  nombre)                   # Nombre del producto
        # Imágenes de producto 1..8 (col 4..11). La 1ª es la PRINCIPAL (fondo blanco)
        for i, url in enumerate(imgs[:8]):
            set(ws, fila, 4 + i, url)
        set(ws, fila, 13, LOCAL)                    # originalLocalName
        set(ws, fila, 14, MONEDA)                   # currencyCode
        set(ws, fila, 16, p.get('miravia_desc'))    # Descripción
        set(ws, fila, 17, ENVIO)                    # Método de envío
        set(ws, fila, 18, p.get('licencia') or 'Funko')   # Marca
        set(ws, fila, 19, EDAD)                     # Edad recomendada
        set(ws, fila, 20, BATERIA)                  # Batería requerida
        set(ws, fila, 21, MATERIAL)                 # Material
        set(ws, fila, 22, CERT)                     # Certificaciones
        set(ws, fila, 23, p.get('miravia_atributos'))     # Atributos adicionales
        set(ws, fila, 24, p.get('foto_caja'))       # Foto etiqueta UE (GPSR)
        set(ws, fila, 30, ADVERTENCIA)              # ¿Advertencia de seguridad?
        set(ws, fila, 31, ADV_TEXTO)                # Contenido de la advertencia
        set(ws, fila, 34, str(ean))                 # Código EAN
        set(ws, fila, 35, slug)                     # SKU de vendedor (= slug)
        set(ws, fila, 36, precio)                   # Precio original
        set(ws, fila, 38, stock if stock is not None else 0)  # Stock
        set(ws, fila, 40, FABRICANTE)               # Fabricante
        set(ws, fila, 41, RESP_UE)                  # Persona Responsable de la UE
        set(ws, fila, 50, PESO)                     # Peso del paquete (kg)
        set(ws, fila, 51, LARGO)                    # Longitud (cm)
        set(ws, fila, 52, ANCHO)                    # Ancho (cm)
        set(ws, fila, 53, ALTO)                     # Altura (cm)
        set(ws, fila, 55, PELIGROSOS)               # Materiales peligrosos

        print(f"    fila {fila}: {nombre[:55]}  | EAN {ean} | SKU {slug}")
        fila += 1

    wb.save(SALIDA)
    print(f"\n>>> LISTO. {len(productos)} producto(s) escritos en {SALIDA}")
    if avisos:
        print("\n⚠️  REVISA antes de subir:")
        for a in avisos: print("   -", a)
    else:
        print("    Sin avisos: todas las fichas van completas.")

if __name__ == "__main__":
    main()
