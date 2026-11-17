"use strict";

function createReplayQa(map, seek, redraw, views) {
  const panel = document.querySelector("#replay-qa");
  const vehicle = panel.querySelector("#qa-vehicle");
  const alerts = panel.querySelector("#qa-event");
  const locate = panel.querySelector("#qa-locate");
  const jump = panel.querySelector("#qa-jump");
  const raw = panel.querySelector("#qa-raw");
  const detail = panel.querySelector("#qa-detail");
  const followStatus = panel.querySelector("#qa-follow-status");
  const layers = [...panel.querySelectorAll("[data-qa-layer]")];
  let events = [];
  let firstTime;
  let lastTime;

  const selected = () => events.find(event => event.id === alerts.value);
  const hasPoint = event => Array.isArray(event?.coordinates) && event.coordinates.length === 2
    && event.coordinates.every(Number.isFinite);
  const hasTime = event => Number.isFinite(event?.time) && event.time >= firstTime && event.time <= lastTime;
  const option = (label, value) => new Option(label, value);

  function updateSelection() {
    const event = selected();
    locate.disabled = !hasPoint(event);
    jump.disabled = !hasTime(event);
    detail.textContent = event ? [event.label, event.vehicleId, event.lane, event.node && `Nodo ${event.node}`,
      Number.isFinite(event.time) ? `${event.time.toLocaleString("es-UY")} s` : "Sin instante registrado",
      event.evidence.signedMeters != null ? `${event.evidence.signedMeters.toLocaleString("es-UY")} m proyectados` : null,
      event.evidence.backwardsMeters != null ? `${event.evidence.backwardsMeters.toLocaleString("es-UY")} m en la geometría` : null,
      event.evidence.sampledSeconds != null ? `${event.evidence.sampledSeconds} s detenido` : null,
    ].filter(Boolean).join(" · ") : "";
  }

  function stopFollowing() {
    vehicle.value = "";
    map.qaFollow(null);
    views?.qaFollow(null);
    followStatus.textContent = "";
  }

  panel.querySelector("#qa-fit").addEventListener("click", () => {
    stopFollowing();
    map.qaFit();
    views?.qaFit();
  });
  for (const input of layers) {
    input.addEventListener("change", () => {
      map.qaLayer(input.dataset.qaLayer, input.checked);
      views?.qaLayer(input.dataset.qaLayer, input.checked);
    });
  }
  vehicle.addEventListener("change", () => {
    const id = vehicle.value === "" ? null : Number(vehicle.value);
    map.qaFollow(id);
    views?.qaFollow(id);
    redraw();
  });
  alerts.addEventListener("change", updateSelection);
  locate.addEventListener("click", () => {
    const event = selected();
    if (!hasPoint(event)) return;
    stopFollowing();
    map.qaLocate(event.coordinates);
    views?.qaLocate(event.coordinates);
  });
  jump.addEventListener("click", () => {
    const event = selected();
    if (!hasTime(event)) return;
    stopFollowing();
    if (hasPoint(event)) {
      map.qaLocate(event.coordinates);
      views?.qaLocate(event.coordinates);
    }
    seek(event.time);
  });
  raw.addEventListener("change", redraw);

  return {
    get raw() { return !panel.hidden && raw.checked; },
    updateStatus(cars, outside) {
      if (panel.hidden) return;
      const absent = vehicle.value !== "" && !cars.some(car => car[0] === Number(vehicle.value));
      const outsideLabel = outside === 1
        ? "1 vehículo activo fuera de la cámara. Sigue en la simulación."
        : outside > 1 ? `${outside} vehículos activos fuera de la cámara. Siguen en la simulación.` : "";
      const status = absent ? "El vehículo seleccionado no está activo en este instante." : outsideLabel;
      if (followStatus.textContent !== status) followStatus.textContent = status;
    },
    configure(data, payload = null) {
      panel.hidden = !data;
      raw.checked = false;
      events = payload?.events ?? [];
      firstTime = data?.frames[0]?.[0];
      lastTime = data?.frames.at(-1)?.[0];
      vehicle.replaceChildren(option("Ninguno", ""), ...(data?.vehicleIndex ?? [])
        .map((item, index) => option(item.sumoId, String(index))));
      alerts.replaceChildren(option("Elegir alerta", ""), ...events.map(event => option(
        [event.label, event.vehicleId, event.time != null ? `${event.time} s` : null].filter(Boolean).join(" · "), event.id)));
      for (const input of layers) input.checked = true;
      map.qaConfigure(payload?.connections ?? null);
      views?.qaConfigure(payload?.connections ?? null);
      stopFollowing();
      updateSelection();
    },
    async load(data, id, isCurrent) {
      try {
        const response = await fetch("/qa-sector.json", { cache: "no-store" });
        if (!response.ok) return;
        const payload = await response.json();
        if (!isCurrent() || payload.schemaVersion !== 1 || payload.studyId !== id) return;
        this.configure(data, payload);
        redraw();
      } catch (error) {
        if (isCurrent()) console.warn("UrbanFlow: no se pudieron cargar las alertas QA.", error);
      }
    },
  };
}
