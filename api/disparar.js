// ============================================================
// Moloka - Funcion intermediaria (Vercel) para disparar el workflow
// Ruta en la app: POST  https://moloka-app.vercel.app/api/disparar
//
// QUE HACE: recibe la orden de la app y le dice a GitHub que lance el
// workflow "actualizar-app.yml". La llave de GitHub (GH_TOKEN) vive
// ESCONDIDA en las variables de entorno de Vercel; nunca pisa la app publica.
//
// DOS BARRERAS:
//   1. Secreto compartido (DISPARO_SECRET): disuasion basica.
//   2. PROTECCION REAL: antes de disparar, pregunta a GitHub si ya hay una
//      corrida en marcha; si la hay, NO lanza otra. Asi nunca se apilan
//      corridas ni se vacian los tokens de Keepa por pulsar de mas.
//
// Variables de entorno necesarias en Vercel:
//   GH_TOKEN        -> el token fine-grained de GitHub (ya creado)
//   DISPARO_SECRET  -> el secreto compartido (mismo valor que en la app)
// ============================================================

const REPO = 'Moloka-Store/moloka-app';
const WORKFLOW = 'actualizar-app.yml';

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

  const ghHeaders = {
    'Authorization': `Bearer ${GH_TOKEN}`,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'moloka-app',
  };

  try {
    // --- Barrera 2 (la importante): no disparar si ya hay corrida en marcha ---
    const runsUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10`;
    const runsResp = await fetch(runsUrl, { headers: ghHeaders });
    if (runsResp.ok) {
      const runsData = await runsResp.json();
      const activa = (runsData.workflow_runs || []).some(
        r => r.status === 'in_progress' || r.status === 'queued' || r.status === 'requested' || r.status === 'waiting'
      );
      if (activa) {
        return res.status(409).json({
          error: 'Ya hay una actualizacion en marcha. Espera a que termine antes de lanzar otra.'
        });
      }
    }
    // Si la consulta de runs fallara, seguimos igualmente al disparo
    // (no bloqueamos por no poder comprobar; el peor caso es una corrida de mas).

    // --- Disparar el workflow ---
    // Sin inputs: el modo (rapida/completa) viaja en el recado _solicitud.json del buzon.
    const dispUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
    const dispResp = await fetch(dispUrl, {
      method: 'POST',
      headers: ghHeaders,
      body: JSON.stringify({ ref: 'main' }),
    });

    if (dispResp.status === 204) {
      return res.status(200).json({ ok: true, mensaje: 'Procesado lanzado en la nube.' });
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
