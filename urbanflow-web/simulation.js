"use strict";

function createTrafficMap(canvas, scenario) {
  const ctx = canvas.getContext("2d");
  const base = document.createElement("canvas");
  const ground = base.getContext("2d");
  const [centerX, centerY] = scenario.center;
  const geometry = scenario.geometry;
  let width = 0;
  let height = 0;
  let pixelRatio = 1;
  let zoom = 1;
  let dirty = true;
  const carColors = ["#76c7fe", "#e7f4ff", "#63dbc4", "#a8bfff", "#82aef5"];
  const signals = {
    N: [-8.7, 9], E: [9, 8.7], S: [8.7, -9], W: [-9, -8.7],
  };
  const signalColors = { g: "#66edaa", y: "#ffcf73", r: "#ff777e" };

  function distance(meters) {
    const scale = Math.min(width / 220, height / 159);
    const expansion = Math.max(-1, Math.min(1, meters / 7.2)) * 16;
    return zoom * (meters * scale + expansion);
  }

  function point(x, y) {
    if (geometry) {
      const [minX, minY, maxX, maxY] = geometry.bounds;
      const scale = geometryScale();
      return [width / 2 + (x + centerX - (minX + maxX) / 2) * scale,
        height / 2 - (y + centerY - (minY + maxY) / 2) * scale];
    }
    return [width / 2 + distance(x), height / 2 - distance(y)];
  }

  function geometryScale() {
    const [minX, minY, maxX, maxY] = geometry.bounds;
    const fit = Math.min((width - 60) / (maxX - minX), (height - 50) / (maxY - minY));
    return Math.max(.15, fit) * zoom;
  }

  function line(context, x1, y1, x2, y2, color, size = 1) {
    context.beginPath();
    context.moveTo(x1, y1);
    context.lineTo(x2, y2);
    context.strokeStyle = color;
    context.lineWidth = size;
    context.stroke();
  }

  function box(context, x, y, w, h, radius, color) {
    context.beginPath();
    context.roundRect(x, y, w, h, radius);
    context.fillStyle = color;
    context.fill();
  }

  function parcel(x, y, w, h, kind) {
    const [left, top] = point(x, y);
    const [right, bottom] = point(x + w, y - h);
    const pw = right - left;
    const ph = bottom - top;
    box(ground, left, top, pw, ph, 7, kind === "park" ? "#1b3a39" : "#23394b");
    if (kind === "park") {
      line(ground, left + pw * .2, top + ph * .8, left + pw * .73, top + ph * .2, "#405851", 3);
      line(ground, left + pw * .55, top + ph * .39, left + pw * .85, top + ph * .68, "#405851", 3);
      for (let i = 0; i < 12; i++) {
        const tx = left + pw * (.14 + (i * 37 % 73) / 100);
        const ty = top + ph * (.12 + (i * 47 % 75) / 100);
        const radius = Math.min(8, Math.max(3, pw / 25)) + i % 3;
        ground.beginPath();
        ground.arc(tx, ty + 2, radius, 0, 2 * Math.PI);
        ground.fillStyle = "#142b2d";
        ground.fill();
        ground.beginPath();
        ground.arc(tx - 1, ty, radius, 0, 2 * Math.PI);
        ground.fillStyle = ["#2c524a", "#355d4f", "#40665a"][i % 3];
        ground.fill();
      }
      return;
    }
    const columns = w > 45 ? 3 : 2;
    for (let col = 0; col < columns; col++) {
      const roofX = left + pw * (.09 + col * .87 / columns);
      const roofY = top + ph * (col % 2 ? .30 : .15);
      const roofW = pw * .69 / columns;
      const roofH = ph * (col % 2 ? .54 : .6);
      box(ground, roofX + 3, roofY + 4, roofW, roofH, 3, "#192b3c");
      box(ground, roofX, roofY, roofW, roofH, 3, col % 2 ? "#364d60" : "#3b5367");
      line(ground, roofX + 4, roofY + 4, roofX + roofW - 4, roofY + 4, "#60778980", 1);
      box(ground, roofX + roofW * .26, roofY + roofH * .32, roofW * .45, roofH * .22, 2, "#2d4256");
    }
  }

  function streetDetails(cx, cy, road) {
    const mark = "#9eb3c58e";
    ground.setLineDash([10 * zoom, 9 * zoom]);
    for (const [x1, y1, x2, y2] of [
      [0, cy, cx - road - 11, cy], [cx + road + 11, cy, width, cy],
      [cx, 0, cx, cy - road - 11], [cx, cy + road + 11, cx, height],
    ]) line(ground, x1, y1, x2, y2, "#d7bd8485", 1.3);
    ground.setLineDash([]);

    for (let turn = 0; turn < 4; turn++) {
      ground.save();
      ground.translate(cx, cy);
      ground.rotate(turn * Math.PI / 2);
      for (let stripe = 0; stripe < 6; stripe++) {
        ground.fillStyle = "#aec6d77d";
        ground.fillRect((-0.86 + stripe * .29) * road, -road - 7 * zoom, road * .17, 5 * zoom);
      }
      line(ground, -road + 3, -road - 11 * zoom, -3, -road - 11 * zoom, mark, 1.4 * zoom);
      const arrowX = -road / 2;
      const arrowY = -road - 27 * zoom;
      line(ground, arrowX, arrowY - 8 * zoom, arrowX, arrowY, mark, 1.3);
      line(ground, arrowX, arrowY, arrowX - 3 * zoom, arrowY - 3 * zoom, mark, 1.3);
      line(ground, arrowX, arrowY, arrowX + 3 * zoom, arrowY - 3 * zoom, mark, 1.3);
      ground.restore();
    }
  }

  function paintBase() {
    ground.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    const backdrop = ground.createRadialGradient(width / 2, height / 2, 12, width / 2, height / 2, width * .63);
    backdrop.addColorStop(0, "#253c50");
    backdrop.addColorStop(1, "#101e2d");
    ground.fillStyle = backdrop;
    ground.fillRect(0, 0, width, height);
    if (geometry) {
      paintPilot();
      dirty = false;
      return;
    }
    for (const [x, y, w, h, type] of [
      [-63, 53, 51, 41], [-108, 53, 40, 41, "park"], [12, 53, 53, 41, "park"],
      [70, 53, 47, 41], [-63, -12, 51, 41, "park"], [-108, -12, 40, 41],
      [12, -12, 53, 41], [70, -12, 47, 41, "park"], [-63, 95, 51, 36, "park"],
      [12, 95, 53, 36], [-63, -59, 51, 36], [12, -59, 53, 36, "park"],
    ]) parcel(x, y, w, h, type);

    const [cx, cy] = point(0, 0);
    const road = distance(3.2) + 2 * zoom;
    for (const [padding, color] of [[6, "#627c91"], [4, "#4a6175"], [0, "#192b3e"]]) {
      const halfWidth = road + padding * zoom;
      ground.fillStyle = color;
      ground.fillRect(0, cy - halfWidth, width, halfWidth * 2);
      ground.fillRect(cx - halfWidth, 0, halfWidth * 2, height);
    }
    streetDetails(cx, cy, road);
    ground.fillStyle = "#98aec4";
    ground.font = "600 10px system-ui";
    ground.textAlign = "center";
    ground.fillText("ACCESO NORTE", cx, 21);
    if (width > 550) {
      ground.fillText("ACCESO OESTE", 72, cy - road - 13);
      ground.fillText("ACCESO ESTE", width - 67, cy - road - 13);
    }
    dirty = false;
  }

  function pilotPath(points) {
    ground.beginPath();
    for (const [index, [x, y]] of points.entries()) {
      const [px, py] = point(x - centerX, y - centerY);
      if (index === 0) ground.moveTo(px, py);
      else ground.lineTo(px, py);
    }
  }

  function paintPilot() {
    const scale = geometryScale();
    const [originX, originY] = point(0, 0);
    const grid = 25 * scale;
    for (let x = originX % grid; x < width; x += grid) line(ground, x, 0, x, height, "#8ca9c119");
    for (let y = originY % grid; y < height; y += grid) line(ground, 0, y, width, y, "#8ca9c119");

    ground.lineJoin = "round";
    ground.lineCap = "round";
    for (const [laneWidth, points] of geometry.lanes) {
      pilotPath(points);
      ground.strokeStyle = "#7590a7";
      ground.lineWidth = laneWidth * scale + 1.8;
      ground.stroke();
    }
    for (const junction of geometry.junctions) {
      pilotPath(junction);
      ground.closePath();
      ground.fillStyle = "#3a5065";
      ground.strokeStyle = "#7590a7";
      ground.lineWidth = 1.4;
      ground.stroke();
      ground.fill();
    }
    for (const [laneWidth, points] of geometry.lanes) {
      pilotPath(points);
      ground.strokeStyle = "#3a5065";
      ground.lineWidth = laneWidth * scale;
      ground.stroke();
    }

    ground.font = "650 11px system-ui";
    ground.textAlign = "center";
    ground.textBaseline = "middle";
    for (const [label, x, y] of geometry.labels) {
      const [px, py] = point(x - centerX, y - centerY);
      ground.strokeStyle = "#142435";
      ground.lineWidth = 4;
      ground.strokeText(label, px, py);
      ground.fillStyle = "#d4e2ee";
      ground.fillText(label, px, py);
    }

    const meters = 50 * scale > 100 ? 25 : 50;
    const rulerEnd = 17 + meters * scale;
    line(ground, 17, 38, rulerEnd, 38, "#c0d4e7", 1.4);
    line(ground, 17, 35, 17, 40, "#c0d4e7", 1.4);
    line(ground, rulerEnd, 35, rulerEnd, 40, "#c0d4e7", 1.4);
    ground.fillStyle = "#c0d4e7";
    ground.fillText(`${meters} m`, (17 + rulerEnd) / 2, 25);
  }

  function resize() {
    const nextWidth = canvas.clientWidth;
    const nextHeight = canvas.clientHeight;
    const nextRatio = Math.min(window.devicePixelRatio || 1, 2);
    if (!nextWidth || !nextHeight) return false;
    if (nextWidth !== width || nextHeight !== height || nextRatio !== pixelRatio) {
      width = nextWidth;
      height = nextHeight;
      pixelRatio = nextRatio;
      canvas.width = base.width = Math.round(width * pixelRatio);
      canvas.height = base.height = Math.round(height * pixelRatio);
      dirty = true;
    }
    return true;
  }

  function draw(cars, phase, highlight) {
    if (!resize()) return;
    if (dirty) paintBase();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(base, 0, 0);
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

    for (const [approach, [x, y]] of Object.entries(geometry ? {} : signals)) {
      const [px, py] = point(x, y);
      const color = signalColors[phase[approach]] ?? signalColors.r;
      ctx.beginPath();
      ctx.arc(px, py, 7, 0, 2 * Math.PI);
      ctx.fillStyle = "#0d1b29";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(px, py, 3.5, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
    }

    for (const [id, x, y, angle, speed] of cars) {
      const [px, py] = point(x - centerX, y - centerY);
      if (px < -26 || py < -26 || px > width + 26 || py > height + 26) continue;
      const stopped = highlight && speed < .1;
      const scale = geometry ? Math.max(.5, geometryScale() / 3.2) : Math.min(1.35, zoom);
      ctx.save();
      ctx.translate(px, py);
      ctx.rotate(angle * Math.PI / 180);
      ctx.scale(scale, scale);
      if (stopped) box(ctx, -7, -12, 14, 24, 4, "#ffad5535");
      box(ctx, -5, -8, 10, 19, 3, "#0b1a2a");
      box(ctx, -4, -9, 8, 18, 3, stopped ? "#ffba66" : carColors[id % carColors.length]);
      box(ctx, -3, -5, 6, 3, 1, "#23405b");
      box(ctx, -3, 4, 6, 2, 1, "#23405b");
      ctx.restore();
    }
  }

  return {
    draw,
    changeZoom(amount) {
      zoom = amount ? Math.min(1.85, Math.max(.7, zoom + amount)) : 1;
      dirty = true;
      return zoom;
    },
  };
}
