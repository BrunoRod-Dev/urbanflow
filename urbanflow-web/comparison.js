"use strict";

const comparisonChange = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 1, signDisplay: "exceptZero" });

function comparisonHash(first, second) {
  return `#comparar/${first}/${second}`;
}

function comparisonTime(seconds) {
  const tenths = Math.round(seconds * 10);
  const fraction = tenths % 10;
  return `${formatTime(tenths / 10)}${fraction ? `,${fraction}` : ""}`;
}

function comparisonCards(runs, studies) {
  const cards = element("comparison-runs");
  cards.replaceChildren();
  for (const [index, run] of runs.entries()) {
    const card = document.createElement("article");
    card.className = "card comparison-run";
    const heading = document.createElement("h2");
    heading.textContent = `Corrida ${index === 0 ? "A" : "B"}`;
    const context = document.createElement("p");
    context.className = "muted";
    context.textContent = studyDetails(studies.get(run.id) ?? { traffic: run.traffic, trips: run.planned });
    const total = document.createElement("strong");
    total.textContent = `${number.format(run.completed)} viajes completados`;
    const replay = document.createElement("a");
    replay.className = "text-link";
    replay.href = `#estudio/${run.id}`;
    replay.textContent = `Abrir corrida ${index === 0 ? "A" : "B"}`;
    card.append(heading, context, total, replay);
    cards.append(card);
  }
}

function comparisonMetric(row, values, unit, addDetails) {
  const cell = row.insertCell();
  for (const [index, value] of values.entries()) {
    const line = document.createElement("div");
    line.className = "comparison-value";
    const label = document.createElement("b");
    label.textContent = index === 0 ? "A" : "B";
    const amount = document.createElement("span");
    amount.textContent = value == null ? "—" : `${number.format(value)}${unit}`;
    line.append(label, amount);
    addDetails?.(line, index);
    cell.append(line);
  }
  if (values.every(value => value != null)) {
    const change = document.createElement("small");
    change.className = "comparison-delta";
    change.textContent = `Cambio ${comparisonChange.format(values[1] - values[0])}${unit}`;
    cell.append(change);
  }
}

function renderComparison(data, studies) {
  const { runs, seconds, title } = data;
  element("comparison-location").textContent = title;
  element("comparison-window").textContent = `Resultados desde el inicio hasta ${comparisonTime(seconds)} en ambas corridas. Los volúmenes programados corresponden al período cargado en cada una.`;
  comparisonCards(runs, studies);
  const rows = element("comparison-rows");
  rows.replaceChildren();
  const byAccess = runs.map(run => new Map(run.accesses.map(access => [access.id, access])));
  const allAccesses = new Map(byAccess.flatMap(accesses => [...accesses]));
  let largestIncrease = 0;
  let highlight = "La cola máxima se mantuvo o bajó en los accesos con datos de ambas corridas.";
  for (const [id, access] of allAccesses) {
    const compared = byAccess.map(accesses => accesses.get(id));
    const row = rows.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = access.name;
    row.append(label);
    comparisonMetric(row, compared.map(value => value?.meanWaitSeconds), " s");
    comparisonMetric(row, compared.map(value => value?.peakQueueMeters), " m", (line, index) => {
      const result = compared[index];
      if (result?.peakQueueSeconds == null) return;
      const replay = document.createElement("a");
      replay.href = `#estudio/${runs[index].id}?t=${result.peakQueueSeconds}`;
      replay.textContent = comparisonTime(result.peakQueueSeconds);
      replay.setAttribute("aria-label", `Ver pico de cola de la corrida ${index === 0 ? "A" : "B"} en ${access.name} a los ${replay.textContent}`);
      line.append(replay);
      if (result.queueReachedStart) {
        const edge = document.createElement("small");
        edge.className = "queue-edge";
        edge.textContent = "Cerca del borde del tramo";
        line.append(edge);
      }
    });
    comparisonMetric(row, compared.map(value => value?.completed), "", (line, index) => {
      const result = compared[index];
      if (!result) return;
      const planned = document.createElement("small");
      planned.textContent = `de ${number.format(result.planned)} programados`;
      line.append(planned);
    });
    const increase = compared[1]?.peakQueueMeters - compared[0]?.peakQueueMeters;
    if (increase > largestIncrease) {
      largestIncrease = increase;
      highlight = `La cola más larga aumentó ${number.format(Math.round(increase * 10) / 10)} m en ${access.name}. El pico de la corrida B fue a los ${comparisonTime(compared[1].peakQueueSeconds)}.`;
    }
  }
  element("comparison-highlight").textContent = highlight;
  element("comparison-result").hidden = false;
}

async function showComparison(first, second, version) {
  const status = element("comparison-status");
  const form = element("comparison-form");
  element("comparison-location").textContent = "";
  element("comparison-result").hidden = true;
  form.hidden = true;
  status.textContent = "Midiendo las dos corridas…";
  try {
    await verifyGenerator();
    if (version !== viewVersion) return;
    const { studies } = await studyRequest("");
    if (version !== viewVersion) return;
    const byId = new Map(studies.map(study => [study.id, study]));
    const group = groupSavedStudies(studies).find(item => item.runs.some(run => run.id === first));
    const choices = group?.runs.some(run => run.id === second) ? group.runs : [first, second].map(id => byId.get(id)).filter(Boolean);
    if (choices.length >= 2) {
      for (const [id, selected] of [["comparison-a", first], ["comparison-b", second]]) {
        const select = element(id);
        select.replaceChildren();
        select.setCustomValidity("");
        for (const run of choices) {
          const option = document.createElement("option");
          option.value = run.id;
          option.textContent = `${run.parentId ? "Corrida" : "Estudio original"} · ${studyDetails(run)}`;
          select.append(option);
        }
        select.value = selected;
      }
      form.hidden = false;
    }
    element("comparison-location").textContent = byId.get(first)?.title ?? "";
    const data = await studyRequest(`/${first}/compare/${second}`);
    if (version !== viewVersion) return;
    renderComparison(data, byId);
    status.textContent = "";
  } catch (error) {
    if (version === viewVersion) status.textContent = error.message;
  }
}
