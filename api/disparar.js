// ============================================================
// Moloka - Funcion intermediaria (Vercel) para disparar workflows de GitHub
// Ruta en la app: POST  https://moloka-app.vercel.app/api/disparar
//
// Sirve para los workflows de la LISTA BLANCA de abajo. La app elige cual con el
// campo "workflow" del body; si no lo manda, va actualizar-app.yml (compatibilidad
// con el boton que ya existia). Los inputs del workflow viajan en body.inputs.
//
// 🔴 EL SECRETO VIAJA DESDE EL NAVEGADOR en la app v1 (body.secreto). Eso significa
//    que DISPARO_SECRET esta en el cliente y cualquiera que abra la consola lo ve.
//    Se aguanta porque la barrera real es la lista blanca (no se puede disparar
//    cualquier cosa) y la de corrida-en-marcha. Pero cualquier llamada NUEVA —la de
//    la app v2, por ejemplo— debe hacerse DESDE EL SERVIDOR, no desde el navegador:
//    asi el secreto no sale de Vercel. No se arregla la v1 aqui para no mezclar.
//
// DOS BARRERAS: secreto compartido (DISPARO_SECRET) + no disparar si ese
// workflow ya tiene una corrida en marcha (acota el gasto de tokens Keepa).
//
// Variables de entorno en Vercel: GH_TOKEN, DISPARO_SECRET
// ============================================================

const REPO = 'Moloka-Store/moloka-app';
const WORKFLOWS_OK = ['actualizar-app.yml', 'escaner-app.yml', 'escaner-pro.yml', 'fabrica-preparar.yml', 'fabrica-generar.yml', 'fabrica-redactar.yml', 'fabrica-rehacer.yml', 'web-rebuild.yml', 'web-rank.yml', 'fabrica-lote.yml', 'actualizar-tcg.yml', 'miravia-excel.yml', 'miravia-resultado.yml', 'sync-stock-web.yml', 'tracker-app.yml', 'tracker-cerebro.yml',
  // 23-ago-2026 · EL BUZON DE INVENTARIO_FBA. Es el primer informe de la Fase 0 que
  // se puede cargar DESDE la app, y nace por lo del 16-ago: Amazon rompio el informe
  // de salud, la tabla se quedo congelada siete dias y nadie tenia un boton para
  // meter el sustituto. El fichero de hoy lo subio una persona a mano al Storage.
  // 🔒 Este workflow escribe en PRODUCCION cuando se le pasa {entorno:'produccion',
  //    modo:'aplicar'}, igual que actualizar-app.yml lleva haciendo meses. Lo que lo
  //    hace seguro NO es la escalera —esa es para migraciones y para estrenar un
  //    procesador, y este la paso entera el 23-ago— sino sus guardas: cabecera exacta,
  //    filas dentadas, umbral de filas, PK duplicada, anti-cero, anti-encogimiento,
  //    anti-retroceso de fecha y el desplome del disponible. Un informe roto como los
  //    de salud_fba aborta solo y no escribe nada.
  'procesar-inventario-fba.yml'];   // lista blanca

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Metodo no permitido (usa POST).' });
  }

  const GH_TOKEN = process.env.GH_TOKEN;
  const DISPARO_SECRET = process.env.DISPARO_SECRET;

  if (!GH_TOKEN) {
    return res.status(500).json({ error: 'Falta GH_TOKEN en el servidor (Vercel).' });
  }

  // --- Barrera 1: secreto compartido ---
  const body = (req.body && typeof req.body === 'object') ? req.body : {};
  const secreto = body.secreto || req.headers['x-moloka-secret'];
  if (DISPARO_SECRET && secreto !== DISPARO_SECRET) {
    return res.status(401).json({ error: 'No autorizado.' });
  }

  // --- Workflow a disparar (lista blanca; por defecto el de actualizar) ---
  const WORKFLOW = body.workflow || 'actualizar-app.yml';
  if (!WORKFLOWS_OK.includes(WORKFLOW)) {
    return res.status(400).json({ error: `Workflow no permitido: ${WORKFLOW}` });
  }

  const ghHeaders = {
    'Authorization': `Bearer ${GH_TOKEN}`,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'moloka-app',
  };

  try {
    // --- Barrera 2: no disparar si ESE workflow ya tiene corrida en marcha ---
    const runsUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10`;
    const runsResp = await fetch(runsUrl, { headers: ghHeaders });
    if (runsResp.ok) {
      const runsData = await runsResp.json();
      const activa = (runsData.workflow_runs || []).some(
        r => r.status === 'in_progress' || r.status === 'queued' || r.status === 'requested' || r.status === 'waiting'
      );
      if (activa) {
        return res.status(409).json({
          error: 'Ya hay una corrida de este proceso en marcha. Espera a que termine antes de lanzar otra.'
        });
      }
    }

    // --- Disparar ---
    const dispUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
    const payload = { ref: 'main' };
    if (body.inputs && typeof body.inputs === 'object') payload.inputs = body.inputs;
    const dispResp = await fetch(dispUrl, {
      method: 'POST',
      headers: ghHeaders,
      body: JSON.stringify(payload),
    });

    if (dispResp.status === 204) {
      return res.status(200).json({ ok: true, mensaje: 'Lanzado en la nube.', workflow: WORKFLOW });
    }

    const detalle = await dispResp.text();
    return res.status(502).json({
      error: `GitHub rechazo el disparo (HTTP ${dispResp.status}).`,
      detalle: detalle.slice(0, 500),
    });
  } catch (e) {
    return res.status(500).json({ error: 'Error al contactar con GitHub.', detalle: String(e).slice(0, 300) });
  }
}
