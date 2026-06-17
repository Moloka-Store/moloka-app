# ==========================================================================
# MOLOKA — DEMO: 20 fichas web automáticas desde la API de BEMS
# Versión para GITHUB ACTIONS (BEMS pasa desde Actions; desde Colab lo bloquea
# Cloudflare). Lee las credenciales de los Secrets del repo, genera el HTML de
# las fichas y lo deja en el disco para subirlo como artifact descargable.
# ==========================================================================
import os, sys, html as _html
from curl_cffi import requests as curl_requests

sys.stdout.reconfigure(line_buffering=True)   # log en vivo (como el detector)

# ---------- 1) CONFIGURACIÓN ----------------------------------------------
# 👉 Mete aquí los EANs que quieras ver (tus rarezas o lo que venderías).
#    Dejo 3 reales de ejemplo para que arranque ya.
EANS = [
    "889698919654",   # Toy Story - Buzz GW (ejemplo real, está en BEMS)
    "889698836890",   # Bitty POP! Rachel Green
    "889698907729",
    # "tu_ean_4",
    # ... hasta 20
]

MARGEN_PCT = 35      # margen sobre el coste BEMS
IVA_PCT    = 21      # IVA Funko

# ---------- 2) TOKEN BEMS ---------------------------------------------------
LOGIN      = os.environ['BEMS_LOGIN']
PASSWORD   = os.environ['BEMS_PASSWORD']
SECRET_KEY = os.environ['BEMS_SECRET_KEY']

print(">>> Pidiendo token a BEMS...")
r = curl_requests.post(
    'https://www.probems.be/API/TOKEN',
    data={'login': LOGIN, 'password': PASSWORD, 'secret_key': SECRET_KEY},
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
    impersonate='chrome120', timeout=30
)
if r.status_code != 200 or 'access_token' not in r.text:
    print(f"!!! BEMS no dio token. status={r.status_code}")
    print("    Primeros 300 car.:", r.text[:300])
    sys.exit(1)
TOKEN = r.json()['access_token']
HEADERS = {'accept': 'application/json', 'authorization': f'Bearer {TOKEN}'}
BASE = 'https://www.probems.be/API'
print(f">>> Token BEMS OK ({TOKEN[:18]}...)")

# ---------- 3) FUNCIONES (flujo validado EAN -> ID -> detalles) ------------
def detalles_por_ean(ean):
    r1 = curl_requests.get(f'{BASE}/PRODUCT-REF-BEMS?IDENTIFIER={ean}&METHOD=EANTOBEMS',
                           headers=HEADERS, impersonate='chrome120', timeout=30)
    if r1.status_code != 200:
        return None
    id_bems = r1.json().get('ID_BEMS')
    if not id_bems:
        return None
    r2 = curl_requests.get(f'{BASE}/PRODUCT-DETAILS?IDENTIFIER={id_bems}&LANGUE=EN',
                           headers=HEADERS, impersonate='chrome120', timeout=30)
    if r2.status_code != 200:
        return None
    raw = r2.json()
    if isinstance(raw, list) and raw:
        return raw[0]
    return raw if isinstance(raw, dict) else None

def precio_venta(coste):
    if coste is None:
        return None
    try:
        coste = float(coste)
    except Exception:
        return None
    pvp = coste * (1 + IVA_PCT/100) * (1 + MARGEN_PCT/100)
    return round(pvp) - 0.05

def titulo_seo(nombre, licencia):
    base = f"Funko Pop! {nombre}"
    if licencia and licencia.strip() and licencia.lower() not in (nombre or '').lower():
        base += f" – {licencia.title()}"
    return base + " – Figura Coleccionable Original – Caja Protegida"

# ---------- 4) RECOGER FICHAS ----------------------------------------------
fichas = []
for ean in EANS:
    d = detalles_por_ean(ean)
    if not d:
        print(f"  x {ean}: no está en BEMS o sin datos")
        continue
    coste = d.get('PRICE')
    img   = next((d.get(k) for k in ('IMAGE1','IMAGE2','IMAGE3') if d.get(k)), None)
    fichas.append({
        'nombre':   d.get('MODELE', '(sin nombre)'),
        'licencia': d.get('NAME_LICENSE', '') or '',
        'ean':      d.get('EAN', ean),
        'coste':    coste,
        'pvp':      precio_venta(coste),
        'imagen':   img,
        'titulo':   titulo_seo(d.get('MODELE',''), d.get('NAME_LICENSE','')),
    })
    print(f"  ok {ean}: {str(d.get('MODELE',''))[:45]}  coste {coste} -> PVP {precio_venta(coste)}")

print(f">>> Fichas montadas: {len(fichas)}/{len(EANS)}")

# ---------- 5) GENERAR HTML -------------------------------------------------
def card(f):
    img = f['imagen'] or 'https://via.placeholder.com/300x300?text=Sin+imagen'
    pvp = f"{f['pvp']:.2f}".replace('.', ',') if f['pvp'] is not None else '—'
    lic = _html.escape(f['licencia'] or '')
    return f"""
    <div class="card">
      <div class="imgwrap"><img src="{_html.escape(img)}" loading="lazy"></div>
      <div class="body">
        {f'<span class="lic">{lic}</span>' if lic else ''}
        <div class="title">{_html.escape(f['titulo'])}</div>
        <div class="price">{pvp} €</div>
        <div class="ean">EAN {_html.escape(str(f['ean']))}</div>
      </div>
    </div>"""

doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Moloka — fichas demo</title>
<style>
  body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#fafafa;margin:0;padding:32px;color:#1a1a1a}}
  h1{{font-weight:800;letter-spacing:-.5px}} .sub{{color:#888;margin-bottom:28px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px}}
  .card{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);transition:.2s}}
  .card:hover{{box-shadow:0 8px 24px rgba(0,0,0,.12);transform:translateY(-3px)}}
  .imgwrap{{aspect-ratio:1;background:#f3f3f3;display:flex;align-items:center;justify-content:center}}
  .imgwrap img{{width:100%;height:100%;object-fit:contain;padding:14px;box-sizing:border-box}}
  .body{{padding:14px 16px 18px}}
  .lic{{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#fff;background:#111;padding:3px 8px;border-radius:6px;margin-bottom:8px}}
  .title{{font-size:13px;line-height:1.35;font-weight:600;min-height:54px}}
  .price{{font-size:22px;font-weight:800;margin-top:10px}}
  .ean{{font-size:11px;color:#aaa;margin-top:4px}}
</style></head><body>
  <h1>Moloka — vista previa de fichas</h1>
  <div class="sub">{len(fichas)} fichas generadas automáticamente desde la API de BEMS · precio = coste + IVA + {MARGEN_PCT}% margen</div>
  <div class="grid">{''.join(card(f) for f in fichas)}</div>
</body></html>"""

with open('moloka_fichas_demo.html', 'w', encoding='utf-8') as fp:
    fp.write(doc)
print(">>> HTML guardado: moloka_fichas_demo.html")
print("=== DEMO FICHAS FIN ===")
