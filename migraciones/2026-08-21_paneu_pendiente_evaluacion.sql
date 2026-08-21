-- ===========================================================================
-- paneu_aptos · «pendiente_evaluacion»: la ficha existe y Amazon no ha hablado
-- ===========================================================================
--
-- 🔴 QUÉ RESUELVE, con el caso que le da nombre. El 20-ago-2026 la carga de PanEU abortó
--    entera por UNA fila: `B0CQDG7Y94`, el Llavero Pocket POP Deadpool & Wolverine, de la
--    factura de OcioStock 26-17346-S1 que entró el 19-ago. Venía con 4 de 30 celdas
--    rellenas —sólo la identidad— y los veintiséis campos de país en blanco, porque el
--    programa paneuropeo todavía no se había pronunciado sobre ella.
--    La Guarda 5 hizo lo que debía (no interpretar una celda que no entiende), pero el
--    precio fue dejar `paneu_aptos` CINCO DÍAS sin actualizar — y con él los estados de
--    país de la pestaña Enviar, que salen de ahí.
--
-- 🔬 MEDIDO sobre los ONCE ficheros del buzón (16-jul → 20-ago): diez de once traen TODAS
--    las celdas legibles. El único con problema es el del 20-ago, y no es «una celda de un
--    país»: es una fila con los DIEZ países en blanco. Cero casos de celdas sueltas
--    ilegibles en trece meses.
--
-- 🔑 Y VA A REPETIRSE cada vez que entre mercancía nueva —el fichero pasó de 384 a 400
--    filas, y esas 16 son esa caja—, que en este negocio es lo normal. No es una rareza
--    que tolerar: es el funcionamiento esperado.
--
-- 🔒 POR QUÉ UNA COLUMNA Y NO UN AVISO EN EL LOG: es un estado del NEGOCIO —fichas nuevas
--    esperando el veredicto de Amazon—, no un incidente de carga. Tiene que poder
--    preguntarse «¿cuáles están pendientes de evaluar?» sin abrir el log de hace tres días.
--    El log dice «hoy han entrado éstas»; la columna contesta «¿cuáles siguen pendientes?».
--    Son dos preguntas distintas y hacen falta las dos.
--
-- ⚠️ LO QUE **NO** HACE: relajar la Guarda 5. Una fila con ALGUNOS países legibles y otros
--    no sigue abortando la carga igual que hoy. La distinción es comprobable y no es de
--    grado: CERO de diez = Amazon no ha hablado · ENTRE UNO Y NUEVE = el fichero dice unas
--    cosas y otras no, y eso no se interpreta.
--
-- ADITIVA. No borra, no reescribe, no cambia ni una fila existente: las 384 que hay se
-- quedan en `false`, que es lo que eran.
-- ===========================================================================

do $$
declare
  antes_filas   bigint;
  antes_cols    int;
  despues_cols  int;
  n_pendientes  bigint;
begin
  select count(*) into antes_filas from public.paneu_aptos;
  select count(*) into antes_cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'paneu_aptos';

  alter table public.paneu_aptos
    add column if not exists pendiente_evaluacion boolean not null default false;

  comment on column public.paneu_aptos.pendiente_evaluacion is
    'La ficha existe en el informe pero Amazon no se ha pronunciado sobre ella en NINGUNO '
    'de los diez países (las diez celdas de «Estado de la oferta» en blanco). Es el estado '
    'normal de la mercancía recién dada de alta, no un error de carga. Con esto a true la '
    'ficha NO tiene filas en paneu_oferta_pais: no se inventa un estado que Amazon no ha '
    'dado. Nació el 21-ago-2026 con B0CQDG7Y94 (Llavero Pocket POP Deadpool & Wolverine).';

  select count(*) into despues_cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'paneu_aptos';

  -- 🔒 GUARDA 1 · la columna está y es UNA sola más. Un `add column if not exists` que no
  --    hiciera nada dejaría esto igual, así que se compara el ANTES con el DESPUÉS en vez
  --    de un número fijo: el invariante es «se ha añadido una», no «hay 15».
  if despues_cols <> antes_cols + 1 then
    raise exception 'Se esperaba UNA columna más (antes %, después %).', antes_cols, despues_cols;
  end if;

  -- 🔒 GUARDA 2 · no se ha tocado ni una fila. Es aditiva: si el recuento cambia, algo
  --    más ha pasado en esta transacción y no es lo que dice el fichero.
  if (select count(*) from public.paneu_aptos) <> antes_filas then
    raise exception 'El número de filas ha cambiado (antes %).', antes_filas;
  end if;

  -- 🔒 GUARDA 3 · todo lo que ya estaba queda en `false`. El DEFAULT lo garantiza, pero
  --    comprobarlo es lo que separa «debería» de «es».
  select count(*) into n_pendientes
    from public.paneu_aptos where pendiente_evaluacion;
  if n_pendientes <> 0 then
    raise exception 'Las % filas previas debían quedar en false, y hay % en true.',
      antes_filas, n_pendientes;
  end if;

  raise notice 'OK · % filas intactas, columna añadida (% -> % columnas), 0 pendientes.',
    antes_filas, antes_cols, despues_cols;
end $$;
