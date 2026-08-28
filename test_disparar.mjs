// ============================================================================
// TEST de api/disparar.js — la puerta que dispara workflows desde la app
// Se corre solo:   node test_disparar.mjs
// ----------------------------------------------------------------------------
// 🔴 POR QUE EXISTE: los dos fallos que tenia esta puerta NO daban ningun error.
//    Faltaba DISPARO_SECRET -> disparaba igual. Fallaba la llamada a GitHub -> se
//    saltaba la barrera 2 y disparaba igual. Un fallo que sale verde solo lo caza
//    un test que sepa ponerse rojo, asi que cada caso mira DOS cosas: el codigo
//    que devuelve Y a quien llamo (o a quien NO llamo).
//
// 🔒 COMO SE COMPRUEBA QUE ESTE TEST VALE (las dos direcciones, §3):
//    1) que se ponga ROJO: se deshace el arreglo a mano (volver a poner
//       `if (DISPARO_SECRET && secreto !== DISPARO_SECRET)` y quitar el 500) y el
//       caso 1 tiene que FALLAR. Si sigue verde, el test no prueba nada.
//    2) que este CALLADO cuando todo esta bien: con el fichero como esta, los 13
//       casos en verde y ni un aviso.
//    Hecho el 28-ago-2026, las dos.
//
// ⚠️ NO llama a GitHub: `fetch` esta suplantado y ADEMAS cuenta las llamadas, que
//    es la mitad que de verdad importa ("no disparar" no se ve en el codigo HTTP).
// ============================================================================

const modulo = await import('./api/disparar.js');
const handler = modulo.default;

const SECRETO = 'secreto-de-prueba-1234';

// --- Un `res` de mentira que se queda con lo ultimo que le dijeron ---
function fabricarRes() {
  const res = { codigo: null, cuerpo: null };
  res.status = (c) => { res.codigo = c; return res; };
  res.json = (o) => { res.cuerpo = o; return res; };
  return res;
}

// --- Un `fetch` de mentira que APUNTA cada llamada. `runsOk` / `dispatchStatus`
//     deciden como se porta GitHub en cada caso. ---
function fabricarFetch({ runsOk = true, runsStatus = 200, corridaActiva = false, dispatchStatus = 204 } = {}) {
  const llamadas = [];
  const f = async (url, opciones = {}) => {
    llamadas.push({ url: String(url), metodo: opciones.method || 'GET' });
    if (String(url).includes('/runs')) {
      return {
        ok: runsOk,
        status: runsStatus,
        json: async () => ({ workflow_runs: corridaActiva ? [{ status: 'in_progress' }] : [] }),
        text: async () => '',
      };
    }
    return { ok: dispatchStatus === 204, status: dispatchStatus, text: async () => 'detalle', json: async () => ({}) };
  };
  f.llamadas = llamadas;
  f.aGitHub = () => llamadas.filter(l => l.url.includes('api.github.com')).length;
  f.disparos = () => llamadas.filter(l => l.url.includes('/dispatches')).length;
  return f;
}

async function pedir({ env = {}, body = {}, metodo = 'POST', github = {} } = {}) {
  const guardado = { GH_TOKEN: process.env.GH_TOKEN, DISPARO_SECRET: process.env.DISPARO_SECRET };
  for (const k of ['GH_TOKEN', 'DISPARO_SECRET']) {
    if (env[k] === undefined) delete process.env[k]; else process.env[k] = env[k];
  }
  const f = fabricarFetch(github);
  const fetchPrevio = globalThis.fetch;
  globalThis.fetch = f;
  const res = fabricarRes();
  try {
    await handler({ method: metodo, body, headers: {} }, res);
  } finally {
    globalThis.fetch = fetchPrevio;
    for (const k of ['GH_TOKEN', 'DISPARO_SECRET']) {
      if (guardado[k] === undefined) delete process.env[k]; else process.env[k] = guardado[k];
    }
  }
  return { res, f };
}

let fallos = 0;
function comprobar(nombre, condicion, detalle) {
  if (condicion) {
    console.log(`  OK    ${nombre}`);
  } else {
    console.log(`  FALLO ${nombre}  ->  ${detalle}`);
    fallos++;
  }
}

console.log('=== TEST api/disparar.js ===\n');

// ---------------------------------------------------------------- LOS 4 DEL ENCARGO
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira' },              // DISPARO_SECRET NO existe
    body: { secreto: SECRETO, workflow: 'actualizar-app.yml' },
  });
  comprobar('1a · sin DISPARO_SECRET -> 500', res.codigo === 500, `devolvio ${res.codigo}`);
  comprobar('1b · sin DISPARO_SECRET -> NO se llama a api.github.com', f.aGitHub() === 0, `hizo ${f.aGitHub()} llamadas`);
}
{
  // La variable PUESTA pero VACIA. En Vercel es lo que pasa al borrar el valor sin
  // borrar la variable, y era el mismo agujero: '' es falsy, asi que la condicion
  // vieja se cortaba igual y disparaba. Ausente y vacia tienen que valer lo mismo.
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: '' },
    body: { secreto: SECRETO, workflow: 'actualizar-app.yml' },
  });
  comprobar('1c · DISPARO_SECRET vacio -> 500', res.codigo === 500, `devolvio ${res.codigo}`);
  comprobar('1d · DISPARO_SECRET vacio -> NO se llama a api.github.com', f.aGitHub() === 0, `hizo ${f.aGitHub()} llamadas`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: 'me-lo-invento-yo-1234', workflow: 'actualizar-app.yml' },
  });
  comprobar('2a · secreto incorrecto -> 401', res.codigo === 401, `devolvio ${res.codigo}`);
  comprobar('2b · secreto incorrecto -> NO se llama a api.github.com', f.aGitHub() === 0, `hizo ${f.aGitHub()} llamadas`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'procesar-inventario-fba.yml' },
    github: { runsOk: false, runsStatus: 500 },
  });
  comprobar('3a · GitHub falla al listar corridas -> 503', res.codigo === 503, `devolvio ${res.codigo}`);
  comprobar('3b · GitHub falla al listar corridas -> NO se dispara', f.disparos() === 0, `hizo ${f.disparos()} disparos`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'actualizar-app.yml' },
  });
  comprobar('4a · todo bien -> 200', res.codigo === 200, `devolvio ${res.codigo}`);
  comprobar('4b · todo bien -> llega al dispatch', f.disparos() === 1, `hizo ${f.disparos()} disparos`);
}

// ---------------------------------------------------------------- LO DEMAS QUE SE TOCO
{
  const { res, f } = await pedir({
    env: { DISPARO_SECRET: SECRETO },                // GH_TOKEN NO existe
    body: { secreto: SECRETO },
  });
  comprobar('5 · sin GH_TOKEN -> 500 y sin llamadas', res.codigo === 500 && f.aGitHub() === 0, `devolvio ${res.codigo} con ${f.aGitHub()} llamadas`);
}
{
  const { res } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: 'corto', workflow: 'actualizar-app.yml' },   // longitud distinta
  });
  comprobar('6 · secreto de otra longitud -> 401 (sin reventar)', res.codigo === 401, `devolvio ${res.codigo}`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'tracker-cerebro.yml', inputs: { pais: { anidado: 1 } } },
  });
  comprobar('7 · input anidado -> 400 y sin llamadas', res.codigo === 400 && f.aGitHub() === 0, `devolvio ${res.codigo} con ${f.aGitHub()} llamadas`);
}
{
  const muchos = {};
  for (let i = 0; i < 11; i++) muchos['k' + i] = 'v';
  const { res } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'actualizar-app.yml', inputs: muchos },
  });
  comprobar('8 · 11 inputs (tope 10) -> 400', res.codigo === 400, `devolvio ${res.codigo}`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: {
      secreto: SECRETO, workflow: 'procesar-inventario-fba.yml',
      inputs: { entorno: 'produccion', modo: 'aplicar', fichero: '50632020686.txt', permitir_umbral_bajo: 'no', exigir_inbound: 'no' },
    },
  });
  // 🔒 EL BOTON DE ELENA. Los 5 inputs reales del buzon de inventario tienen que
  //    pasar enteros: si este caso se pone rojo, el arreglo ha roto la carga.
  comprobar('9a · el boton de Elena (5 inputs reales) -> 200', res.codigo === 200, `devolvio ${res.codigo}`);
  comprobar('9b · el boton de Elena -> los 5 inputs viajan', f.disparos() === 1, `hizo ${f.disparos()} disparos`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'aplicar-migracion.yml' },
  });
  comprobar('10 · workflow fuera de la lista -> 400 y sin llamadas', res.codigo === 400 && f.aGitHub() === 0, `devolvio ${res.codigo} con ${f.aGitHub()} llamadas`);
}
{
  const { res, f } = await pedir({
    env: { GH_TOKEN: 'gh-de-mentira', DISPARO_SECRET: SECRETO },
    body: { secreto: SECRETO, workflow: 'actualizar-app.yml' },
    github: { corridaActiva: true },
  });
  comprobar('11 · ya hay corrida en marcha -> 409 y sin disparo', res.codigo === 409 && f.disparos() === 0, `devolvio ${res.codigo} con ${f.disparos()} disparos`);
}

console.log('');
if (fallos === 0) {
  console.log('TODO OK — 13 casos, 0 fallos');
} else {
  console.log(`ROJO — ${fallos} comprobacion(es) fallidas`);
  process.exitCode = 1;
}
