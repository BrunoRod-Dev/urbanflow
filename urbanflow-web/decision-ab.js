"use strict";

const decisionTime = new Intl.NumberFormat("es-UY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const decisionDelta = new Intl.NumberFormat("es-UY", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const decisionPercent = new Intl.NumberFormat("es-UY", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const decisionCount = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 });
const decisionCountDelta = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0, signDisplay: "exceptZero" });

function decisionAmount(value, decimals, unit) {
  if (value == null) return "—";
  const formatted = decimals == null ? decisionCount.format(value) : decisionTime.format(value);
  return unit ? `${formatted} ${unit}` : formatted;
}

function decisionChange(value, decimals, unit) {
  if (value == null) return "—";
  const formatted = decimals == null ? decisionCountDelta.format(value) : decisionDelta.format(value);
  return unit ? `${formatted} ${unit}` : formatted;
}

function decisionPair(left, right, suffix) {
  const unit = suffix ? ` ${suffix}` : "";
  return `${decisionCount.format(left)}${unit} · ${decisionCount.format(right)}${unit}`;
}

function renderDemand(data) {
  const card = element("decision-demand-card");
  if (!data || data.experimental !== true || data.calibrated !== false || data.seasonal !== false) {
    card.hidden = true;
    return;
  }
  element("decision-demand-note").textContent = `${data.note} ${data.criterion}`;
  const rows = element("decision-demand-rows");
  rows.replaceChildren();
  for (const level of data.levels) {
    const row = rows.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = `${decisionCount.format(level.demand)} vehículos`;
    row.append(label);
    row.insertCell().textContent = decisionPair(level.completed.a, level.completed.b, "");
    row.insertCell().textContent = decisionPair(level.unfinished.a, level.unfinished.b, "");
    const travel = row.insertCell();
    const wait = row.insertCell();
    const cohort = level.cohort;
    if (!cohort.meanTravel) {
      travel.textContent = "—";
      wait.textContent = "—";
    } else {
      travel.textContent = `${decisionAmount(cohort.meanTravel.a, 2, "s")} · ${decisionAmount(cohort.meanTravel.b, 2, "s")} · ${decisionChange(cohort.meanTravel.absolute, 2, "s")} (n=${cohort.count})`;
      wait.textContent = `${decisionAmount(cohort.meanWait.a, 2, "s")} · ${decisionAmount(cohort.meanWait.b, 2, "s")} · ${decisionChange(cohort.meanWait.absolute, 2, "s")}`;
    }
    const cap = row.insertCell();
    const cuts = level.cap.cutByCap;
    cap.textContent = `${decisionCount.format(cuts)} alineado${cuts === 1 ? "" : "s"} · B al tope en ${decisionCount.format(level.cap.bAtCap)}`;
  }
  element("decision-demand-conclusion").textContent = data.conclusion;
  card.hidden = false;
}

function decisionClearance(value) {
  return value == null ? "no despeja" : decisionAmount(value, 2, "s");
}

function renderClearance(data) {
  const card = element("decision-clearance-card");
  if (!data || data.experimental !== true || data.calibrated !== false || data.seasonal !== false) {
    card.hidden = true;
    return;
  }
  element("decision-clearance-note").textContent = `${data.note} ${data.criterion}`;
  const rows = element("decision-clearance-rows");
  rows.replaceChildren();
  for (const level of data.levels) {
    const row = rows.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = `${decisionCount.format(level.demand)} vehículos`;
    row.append(label);
    row.insertCell().textContent = decisionPair(level.completedAtGeneration.a, level.completedAtGeneration.b, "");
    row.insertCell().textContent = decisionPair(level.pendingAtGeneration.a, level.pendingAtGeneration.b, "");
    row.insertCell().textContent = `${decisionClearance(level.clearanceSeconds.a)} · ${decisionClearance(level.clearanceSeconds.b)}`;
    const travel = row.insertCell();
    const wait = row.insertCell();
    const cohort = level.cohort;
    if (!cohort.meanTravel) {
      travel.textContent = "—";
      wait.textContent = "—";
    } else {
      travel.textContent = `${decisionAmount(cohort.meanTravel.a, 2, "s")} · ${decisionAmount(cohort.meanTravel.b, 2, "s")} · ${decisionChange(cohort.meanTravel.absolute, 2, "s")} (n=${cohort.count})`;
      wait.textContent = `${decisionAmount(cohort.meanWait.a, 2, "s")} · ${decisionAmount(cohort.meanWait.b, 2, "s")} · ${decisionChange(cohort.meanWait.absolute, 2, "s")}`;
    }
    row.insertCell().textContent = decisionPair(level.stillUnfinished.a, level.stillUnfinished.b, "");
  }
  element("decision-clearance-warning").textContent = data.detector.interpretation;
  element("decision-clearance-conclusion").textContent = data.conclusion;
  card.hidden = false;
}

function renderDecision(data) {
  element("decision-title").textContent = data.title;
  element("decision-intro").textContent = data.intro;
  element("decision-notice").textContent = data.notice;
  const variants = element("decision-variants");
  variants.replaceChildren();
  for (const key of ["a", "b"]) {
    const variant = data.variants[key];
    const card = document.createElement("article");
    card.className = "card comparison-run";
    const heading = document.createElement("h2");
    heading.textContent = variant.label;
    const detail = document.createElement("p");
    detail.className = "muted";
    detail.textContent = variant.detail;
    card.append(heading, detail);
    variants.append(card);
  }
  const rows = element("decision-rows");
  rows.replaceChildren();
  for (const metric of Object.values(data.metrics)) {
    const row = rows.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = metric.label;
    row.append(label);
    for (const key of ["a", "b"]) {
      const cell = row.insertCell();
      cell.textContent = decisionAmount(metric[key], metric.decimals, metric.unit);
    }
    const absolute = row.insertCell();
    absolute.textContent = decisionChange(metric.absolute, metric.decimals, metric.unit);
    const percent = row.insertCell();
    percent.textContent = metric.percent == null ? "—" : `${decisionPercent.format(metric.percent)} %`;
  }
  element("decision-queues").textContent = data.queues.note;
  element("decision-limitation").textContent = data.limitation;
  renderExecutive(data);
  const method = element("decision-method");
  method.replaceChildren();
  for (const paragraph of data.method) {
    const line = document.createElement("p");
    line.textContent = paragraph;
    method.append(line);
  }
}

function executiveSentence(data) {
  const limitation = String(data.limitation || "");
  const start = limitation.lastIndexOf("La demanda de muestra");
  return start >= 0 ? limitation.slice(start) : limitation;
}

function renderExecutive(data) {
  const compared = element("decision-compared");
  const variants = data.variants || {};
  compared.textContent = variants.a && variants.b
    ? `${variants.a.label} frente a ${variants.b.label}.`
    : "";
  element("decision-conclusion").textContent = executiveSentence(data);
  const host = element("decision-highlights");
  host.replaceChildren();
  const windowLabel = document.createElement("p");
  windowLabel.className = "executive-window";
  windowLabel.textContent = "Resultados a 240 s";
  const note = document.createElement("p");
  note.textContent = "Promedio de quienes llegaron en esa ventana. No incluye el despeje posterior.";
  const grid = document.createElement("div");
  grid.className = "executive-metrics";
  const labels = {
    meanTravel: "Tiempo de viaje",
    meanWait: "Espera",
    completed: "Viajes completados",
  };
  for (const id of ["meanTravel", "meanWait", "completed"]) {
    const metric = data.metrics?.[id];
    if (!metric || typeof metric.a !== "number" || typeof metric.b !== "number") continue;
    const article = document.createElement("article");
    article.className = "executive-metric";
    const title = document.createElement("h3");
    title.textContent = labels[id];
    const values = document.createElement("p");
    values.textContent = `A ${decisionAmount(metric.a, metric.decimals, metric.unit)} · B ${decisionAmount(metric.b, metric.decimals, metric.unit)}`;
    const delta = document.createElement("p");
    delta.className = "executive-delta";
    const percent = metric.percent == null ? "" : ` (${decisionPercent.format(metric.percent)} %)`;
    delta.textContent = `B − A ${decisionChange(metric.absolute, metric.decimals, metric.unit)}${percent}`;
    article.append(title, values, delta);
    grid.append(article);
  }
  host.append(windowLabel, note, grid);
}

function renderClearanceHighlight(data, completed) {
  const host = element("decision-clearance-highlight");
  host.replaceChildren();
  const level = data?.experimental === true && data?.calibrated === false
    ? (data.levels || []).find(item => item.generationEnd === 240
      && item.clearanceEnd === 2400
      && item.completedAtGeneration?.a === completed?.a
      && item.completedAtGeneration?.b === completed?.b)
    : null;
  if (!level) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  const title = document.createElement("p");
  title.className = "executive-window";
  title.textContent = "Despeje completo a 2400 s";
  const note = document.createElement("p");
  note.textContent = `Demanda de ${decisionCount.format(level.demand)} vehículos, generada hasta el segundo ${decisionCount.format(level.generationEnd)}. Este indicador no se mezcla con los tiempos a 240 s.`;
  const values = document.createElement("p");
  values.className = "executive-values";
  values.textContent = `A ${decisionClearance(level.clearanceSeconds.a)} · B ${decisionClearance(level.clearanceSeconds.b)}`;
  const delta = document.createElement("p");
  delta.className = "executive-delta";
  const difference = level.clearanceSeconds.a == null || level.clearanceSeconds.b == null
    ? null
    : level.clearanceSeconds.b - level.clearanceSeconds.a;
  delta.textContent = `B − A ${decisionChange(difference, 2, "s")}`;
  host.append(title, note, values, delta);
}

function setDecisionDetails(open) {
  const body = element("decision-body");
  const toggle = element("decision-details-toggle");
  body.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  toggle.textContent = open ? "Ocultar detalles" : "Detalles técnicos";
}

async function showDecision(version) {
  const status = element("decision-status");
  const executive = element("decision-executive");
  status.hidden = false;
  status.textContent = "Cargando la comparación…";
  executive.hidden = true;
  setDecisionDetails(false);
  try {
    const response = await fetch("assets/decision-roosevelt.json?v=1", { cache: "no-store" });
    if (!response.ok) throw new Error("No se pudo leer la comparación experimental.");
    const data = await response.json();
    if (version !== viewVersion) return;
    if (data.experimental !== true || data.calibrated !== false) {
      throw new Error("La comparación no está marcada como experimental.");
    }
    renderDecision(data);
    try {
      const demandResponse = await fetch("assets/decision-demand.json?v=1", { cache: "no-store" });
      if (version !== viewVersion) return;
      renderDemand(demandResponse.ok ? await demandResponse.json() : null);
    } catch {
      if (version === viewVersion) renderDemand(null);
    }
    let clearance = null;
    try {
      const clearanceResponse = await fetch("assets/decision-clearance.json?v=1", { cache: "no-store" });
      if (version !== viewVersion) return;
      clearance = clearanceResponse.ok ? await clearanceResponse.json() : null;
      renderClearance(clearance);
    } catch {
      if (version !== viewVersion) return;
      renderClearance(null);
    }
    renderClearanceHighlight(clearance, data.metrics.completed);
    status.hidden = true;
    executive.hidden = false;
  } catch (error) {
    if (version !== viewVersion) return;
    status.textContent = error.message;
  }
}

document.querySelector("#decision-details-toggle").addEventListener("click", () => {
  setDecisionDetails(document.querySelector("#decision-body").hidden);
});
