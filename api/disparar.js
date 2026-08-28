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
//    LA DECISION NO CAMBIA: la v1 se queda asi, no se arregla aqui para no mezclar.
//    Lo que cambia es el MOTIVO escrito, porque el que habia CADUCO — y un motivo
//    caducado es peor que ninguno, porque tranquiliza. Decia: "se aguanta porque la
//    barrera real es la lista blanca (no se puede disparar cualquier cosa)". Era
//    cierto mientras la lista blanca solo abria procesos que gastaban tokens o
//    rehacian ficheros. Desde el 23-ago-2026 incluye procesar-inventario-fba.yml,
//    que ESCRIBE EN PRODUCCION con {entorno:'produccion', modo:'aplicar'}. La lista
//    blanca ya no es "la barrera real": es la puerta de la tabla que mira Elena.
//    🔑 Cualquier llamada NUEVA —la app v2, por ejemplo— debe hacerse DESDE EL
//    SERVIDOR, no desde el navegador: asi el secreto no sale de Vercel.
//
// DOS BARRERAS, Y DESDE EL 28-ago-2026 LAS DOS FAIL-CLOSED: secreto compartido
// (DISPARO_SECRET) + no disparar si ese workflow ya tiene una corrida en marcha
// (acota el gasto de tokens Keepa y evita dos cargas pisandose).
//
// 🔴 QUE TENIAN DE MALO, que no daba ningun error y por eso llevaba meses:
//    · Barrera 1: era `if (DISPARO_SECRET && secreto !== DISPARO_SECRET)`. Si la
//      variable de entorno faltaba o llegaba vacia, la condicion se cortaba en el
//      primer termino, NO se devolvia 401 y la llamada seguia hasta el disparo. O
//      sea que la unica forma de quedarse sin puerta era justo la mas probable: que
//      alguien tocase las variables de Vercel. Dos lineas mas arriba, GH_TOKEN ya
//      estaba fail-closed (falta -> 500). Misma funcion, patron contrario.
//    · Barrera 2: vivia DENTRO de `if (runsResp.ok)`, asi que un fallo de red o un
//      500 de GitHub la hacia desaparecer y se disparaba igual sin haber comprobado
//      nada. Ahora un "no lo se" es un 503, no un adelante.
//    🔑 La regla: entre romper una llamada y dejarla pasar sin comprobar, se ROMPE.
//
// Variables de entorno en Vercel: GH_TOKEN, DISPARO_SECRET
// ============================================================

import { timingSafeEqual } from 'node:crypto';

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

// Tope de inputs. NO es un numero inventado: son los dos extremos, medidos el
// 28-ago-2026. Por abajo, el workflow de la lista blanca que mas declara es
// procesar-inventario-fba.yml con 5 (entorno, modo, fichero, permitir_umbral_bajo,
// exigir_inbound); el resto tiene 0 o 1. Por arriba, el tope del propio GitHub para
// este endpoint es 25 ("The maximum number of properties is 25", REST API · create a
// workflow dispatch event). 10 deja el doble de sitio del que nadie usa y corta la
// basura antes de gastar una llamada. Si algun dia un workflow declara mas de 10, se
// sube AQUI y se dice.
const MAX_INPUTS = 10;

// Comparacion en tiempo constante. Longitudes distintas -> false SIN comparar:
// timingSafeEqual exige buffers del mismo tamano y con distintos LANZA, y una
// excepcion aqui se comeria el 401 y acabaria en el catch como error de servidor.
function secretoCoincide(recibido, esperado) {
  if (typeof recibido !== 'string' || typeof esperado !== 'string') return false;
  const a = Buffer.from(recibido, 'utf8');
  const b = Buffer.from(esperado, 'utf8');
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

// Los inputs viajan TAL CUAL a GitHub, asi que se miran antes: objeto plano, con
// tope de claves y solo valores escalares (texto, numero o si/no). Un objeto o un
// array anidado no lo entiende ningun workflow_dispatch y no tiene por que llegar.
function revisarInputs(inputs) {
  if (inputs === undefined || inputs === null) return { ok: true, valor: undefined };
  if (typeof inputs !== 'object' || Array.isArray(inputs)) {
    return { ok: false, error: 'El campo inputs tiene que ser un objeto de pares clave/valor.' };
  }
  const claves = Object.keys(inputs);
  if (claves.length > MAX_INPUTS) {
    return { ok: false, error: `Demasiados inputs: ${claves.length} (el tope es ${MAX_INPUTS}).` };
  }
  for (const clave of claves) {
    const valor = inputs[clave];
    const tipo = typeof valor;
    const escalar = tipo === 'string' || tipo === 'boolean' || (tipo === 'number' && Number.isFinite(valor));
    if (!escalar) {
      return { ok: false, error: `El input "${String(clave).slice(0, 40)}" no es texto, numero ni si/no.` };
    }
  }
  return { ok: true, valor: inputs };
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Metodo no permitido (usa POST).' });
  }

  const GH_TOKEN = process.env.GH_TOKEN;
  const DISPARO_SECRET = process.env.DISPARO_SECRET;

  if (!GH_TOKEN) {
    return res.status(500).json({ error: 'Falta GH_TOKEN en el servidor (Vercel).' });
  }
  // Mismo patron que GH_TOKEN, y por el mismo motivo: si falta la llave, la puerta
  // NO se queda abierta. Antes, faltar DISPARO_SECRET era la forma de no tener puerta.
  if (!DISPARO_SECRET) {
    return res.status(500).json({ error: 'Falta DISPARO_SECRET en el servidor (Vercel).' });
  }

  // --- Barrera 1: secreto compartido ---
  const body = (req.body && typeof req.body === 'object') ? req.body : {};
  const secreto = body.secreto || req.headers['x-moloka-secret'];
  if (!secretoCoincide(secreto, DISPARO_SECRET)) {
    return res.status(401).json({ error: 'No autorizado.' });
  }

  // --- Workflow a disparar (lista blanca; por defecto el de actualizar) ---
  const WORKFLOW = body.workflow || 'actualizar-app.yml';
  if (!WORKFLOWS_OK.includes(WORKFLOW)) {
    return res.status(400).json({ error: `Workflow no permitido: ${WORKFLOW}` });
  }

  // --- Los inputs, antes de gastar una llamada a GitHub ---
  const revision = revisarInputs(body.inputs);
  if (!revision.ok) {
    return res.status(400).json({ error: revision.error });
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
    if (!runsResp.ok) {
      // No se ha podido MIRAR. Eso no es "no hay ninguna en marcha": es no saberlo,
      // y no saberlo no autoriza a disparar.
      return res.status(503).json({
        error: 'No se ha podido comprobar si hay corrida en marcha; no se ha disparado nada. Vuelve a intentarlo.',
        detalle: `GitHub respondio HTTP ${runsResp.status} al listar las corridas de ${WORKFLOW}.`,
      });
    }
    const runsData = await runsResp.json();
    const activa = (runsData.workflow_runs || []).some(
      r => r.status === 'in_progress' || r.status === 'queued' || r.status === 'requested' || r.status === 'waiting'
    );
    if (activa) {
      return res.status(409).json({
        error: 'Ya hay una corrida de este proceso en marcha. Espera a que termine antes de lanzar otra.'
      });
    }

    // --- Disparar ---
    const dispUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
    const payload = { ref: 'main' };
    if (revision.valor !== undefined) payload.inputs = revision.valor;
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
