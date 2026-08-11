-- ============================================================================
-- MIGRACIÓN 2026-08-11 · CUATRO NORMAS NUEVAS EN `monitor_doctrina`
--
-- 🔴 PROPUESTA. NO APLICADA.
-- ----------------------------------------------------------------------------
-- Las cuatro salen de medir en producción el 11-ago-2026. Cada una lleva el
-- enunciado corto primero y el caso real detrás, porque una norma sin el caso
-- que la produjo se discute; con el caso, no.
--
-- El `id` se omite a propósito: la columna tiene `nextval('monitor_doctrina_id_seq')`
-- y la secuencia está sana (valor 113 sobre un máximo de 112, medido hoy). Las
-- cuatro filas cogerán 113-116. Escribir el id a mano es como se rompen las
-- secuencias.
-- ============================================================================

set local lock_timeout = '3s';

insert into public.monitor_doctrina (ambito, norma, porque, zanjado_por, fecha, activa) values

-- ── 113 ─────────────────────────────────────────────────────────────────────
('grupo_de_control_para_aislar_un_escalon',
'🔒 PARA SEPARAR UN ESCALÓN DE PRECIO DE UNA SUBIDA GENERAL DE TARIFAS, EL GRUPO DE CONTROL SON LOS QUE NUNCA CRUZAN. Antes de atribuir una diferencia a la causa que buscas, mide el mismo periodo en un grupo donde esa causa NO PUEDA actuar. Si allí también aparece, no era tu causa.

CASO REAL (11-ago-2026): al medir el acantilado de 20 EUR sobre las facturas, 33 de 39 SKU subían la tarifa al cruzar. Pero eso no descarta que Amazon hubiera subido las tarifas a todos durante el periodo. El control: 55 SKU vendidos SIEMPRE por debajo de 20 EUR (9.267 movimientos, o sea sin acantilado posible). Mediana ene-mar 3,63 EUR; jun-ago 3,69 EUR. +0,06 EUR en SEIS MESES. El calendario de tarifas es estable, luego el salto es del escalón. Con el control puesto: 18 de 21 SKU suben, media +0,55 EUR.

🔴 Y EL MISMO MÉTODO DESTAPÓ UN FALSO MÁXIMO: el salto de +2,53 EUR de 68-SW97-Z5WF comparaba UNA venta del 19-mar contra ventas de may-jun. Con n=1 y meses de por medio no mide el escalón, mide el ruido. El máximo honesto es +0,79 EUR. Exigir n>=2 a cada lado y una ventana corta es parte del método, no un refinamiento.',
'Sin grupo de control, una diferencia medida a lo largo de meses mezcla la causa que buscas con todo lo que cambió en ese tiempo. Y los extremos son justo donde más se cuela el ruido: son los que menos muestra tienen.',
'Fernando + Claude', '2026-08-11', true),

-- ── 114 ─────────────────────────────────────────────────────────────────────
('el_or_cero_convierte_no_lo_se_en_un_numero',
'🔴 `|| 0` CONVIERTE «NO LO SÉ» EN UN NÚMERO. ANTES DE PERMITIR QUE UN CAMPO QUEDE VACÍO, HAY QUE IR A VER QUÉ HACE EL CÁLCULO CON ESE VACÍO. Un hueco solo es honesto si quien lo lee sabe tratarlo. Vale para `|| 0`, `|| 21`, `|| 3.74` y cualquier valor por defecto puesto en el punto de lectura.

CASO REAL (11-ago-2026): al quitar el relleno de 15,5% de la calculadora de Buy Box de la v1, la línea del cálculo era
    const comisionPct = (parseFloat(document.getElementById(''bb-comision-pct'').value) || 0) / 100;
Con la caja vacía, `|| 0` hacía la comisión CERO y el margen salía INFLADO ~15 PUNTOS. Verificado en el DOM real: con comisión 0 el cálculo da 0,00 EUR de comisión y 3,97 EUR de tarifas totales en vez de 7,85 EUR.

🔑 Vaciar el campo sin tocar esa línea habría cambiado un relleno del 15,5% por un CERO SILENCIOSO — mucho peor, porque el 15,5 al menos acertaba en 142 de 160 productos (los del tramo del 15%) y el cero no acierta en ninguno. Se arregló con una guarda explícita: sin comisión, el margen sale como «no calculable», no se calcula.',
'Quitar un valor por defecto parece que deja un hueco visible, y no siempre: si el consumidor tiene su propio valor por defecto, el hueco se rellena solo más abajo y con un número peor. El relleno no desaparece, se mueve.',
'Fernando + Claude', '2026-08-11', true),

-- ── 115 ─────────────────────────────────────────────────────────────────────
('una_escritura_sin_boton_no_parece_una_escritura',
'🔴 AL AUDITAR DE DÓNDE SALE UN VALOR SUCIO, BARRER TODOS LOS `onchange`/`oninput`, NO SOLO LOS FORMULARIOS CON BOTÓN DE GUARDAR. Un campo que escribe en el maestro sin que nadie pulse nada no se parece a una escritura, y por eso no se busca.

CASO REAL (11-ago-2026): buscando de dónde salía el 15,50% de relleno de productos.comision_pct se encontró el formulario de edición (index.html:5710) y se dio por cerrado. Pero había una SEGUNDA vía, y menos visible:
    <input id="bb-comision-pct" ... onchange="guardarComisionProducto()">
`guardarComisionProducto()` hace un UPDATE directo sobre productos.comision_pct. NO HAY BOTÓN DE GUARDAR: basta con modificar el campo y salir de él. Y el campo venía pre-rellenado con 15,5, igual que el otro.

🔑 Regla práctica: el barrido no es «buscar el formulario», es `grep -n "onchange=\\|oninput="` sobre el fichero entero y mirar qué hace cada handler. En la v1 son pocos; en cualquier pantalla nueva, que no nazcan.',
'Un formulario con botón declara que va a escribir. Un `onchange` no declara nada: parece interfaz, y es persistencia. Al auditar se buscan las escrituras donde se espera encontrarlas.',
'Fernando + Claude', '2026-08-11', true),

-- ── 116 ─────────────────────────────────────────────────────────────────────
('ventas_producto_no_declara_su_escala',
'🔴 `transacciones_movimientos.ventas_producto` VIENE SIN IVA. El IVA está aparte, en `impuesto_producto`. El nombre no lo dice, y el error NO DA ERROR: da un número plausible. Hermana de la norma 13 (las dos columnas de comisión en escalas distintas).

🔒 FORMA CORRECTA: el precio de venta por unidad es
    (ventas_producto + impuesto_producto) / cantidad
NUNCA `ventas_producto / cantidad` si lo vas a comparar contra un precio de escaparate, de ficha o de Keepa, que van CON IVA.

MEDIDO (11-ago-2026): sobre los 13.146 movimientos de tipo pedido de ES, el ratio (ventas+impuesto)/ventas es 1,21 clavado en 12.997; los otros 142 son IVA reducido del 10% (alimentación). Testigo J9-W3W1-31V3: ventas_producto 16,52 + impuesto_producto 3,47 = 19,99, exactamente el precio de su ficha.

CONSECUENCIA CONCRETA: el acantilado de 20 EUR está definido sobre el precio CON IVA. Partir por 20 sobre `ventas_producto` equivale a partir por 24,20 EUR — un umbral que no existe. Medido: el corte correcto da 21 SKU a ambos lados y 18 subiendo; el corte con la escala cruzada da 7 y 2. Son dos poblaciones distintas y la conclusión cambia.

🔑 La regla general de la que ésta y la 13 son casos: ANTES DE COMPARAR DOS NÚMEROS DE FUENTES DISTINTAS, COMPRUEBA QUE ESTÁN EN LA MISMA ESCALA. El nombre de la columna no es prueba.',
'Un campo llamado `ventas_producto` al lado de otro llamado `impuesto_producto` sugiere que el primero es el total y el segundo un desglose. Es al revés, y no hay nada en el esquema que lo diga.',
'Fernando + Claude', '2026-08-11', true);

-- ── VERIFICACIÓN (después de aplicar) ───────────────────────────────────────
--   select id, ambito, left(norma, 70) from public.monitor_doctrina
--    where fecha = '2026-08-11' order by id;      -- 4 filas, ids 113-116
--
-- ── VUELTA ATRÁS ────────────────────────────────────────────────────────────
--   delete from public.monitor_doctrina where fecha = '2026-08-11';
--   (o mejor, si ya se han leído: update ... set activa = false)
