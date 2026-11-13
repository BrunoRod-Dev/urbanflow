"use strict";

function trafficCsvTemplate(movements) {
  const quote = value => `"${String(value).replaceAll('"', '""')}"`;
  const label = value => value.replace(/\s+/g, " ").trim().replace(/^[=+\-@]/, first => `'${first}`);
  return ["movimiento;vehiculos;recorrido", ...movements.map(movement =>
    `${quote(movement.id)};;${quote(label(movement.label))}`)].join("\r\n");
}

function parseTrafficCsv(csv, movements) {
  const lines = csv.replace(/^\uFEFF/, "").split(/\r\n|\r|\n/);
  const header = lines.shift();
  const separator = header.includes(";") ? ";" : ",";
  const field = value => value?.trim().replace(/^"(.*)"$/, "$1");
  const [idHeader, countHeader] = header.split(separator, 2).map(field);
  if (idHeader?.toLowerCase() !== "movimiento" || countHeader?.toLowerCase() !== "vehiculos") {
    throw new Error("El CSV debe tener las columnas movimiento y vehiculos. Usá la plantilla de este estudio.");
  }

  const expected = new Set(movements.map(movement => movement.id));
  const counts = new Map();
  for (const [index, row] of lines.entries()) {
    if (!row.trim()) continue;
    const [id, count] = row.split(separator, 2).map(field);
    const line = index + 2;
    if (!expected.has(id)) throw new Error(`Fila ${line}: el movimiento no pertenece a este estudio.`);
    if (counts.has(id)) throw new Error(`Fila ${line}: el movimiento aparece más de una vez.`);
    if (!/^\d+$/.test(count ?? "") || !Number.isSafeInteger(Number(count))) {
      throw new Error(`Fila ${line}: ingresá un número entero de vehículos. Usá 0 cuando corresponda.`);
    }
    counts.set(id, Number(count));
  }
  if (counts.size !== expected.size) throw new Error("Faltan movimientos. Completá todas las filas de la plantilla.");
  return counts;
}
