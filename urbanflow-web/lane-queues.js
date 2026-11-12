import * as THREE from "three";

export function addLaneQueueLabels(scene, links, controller, coordinates) {
  const lanes = new Set(links.filter(link => link.controller === controller).map(link => link.fromLane));
  const labels = new Map();
  const group = new THREE.Group();
  group.name = "lane-queue-labels";
  group.visible = false;
  scene.add(group);
  let previous;

  function labelFor(lane) {
    const canvas = document.createElement("canvas");
    canvas.width = 200;
    canvas.height = 58;
    const context = canvas.getContext("2d");
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const label = new THREE.Sprite(new THREE.SpriteMaterial({
      map: texture, transparent: true, depthWrite: false, depthTest: false, sizeAttenuation: false, toneMapped: false,
    }));
    label.name = `queue-${lane}`;
    label.scale.set(.214, .062, 1);
    label.renderOrder = 3;
    group.add(label);
    const item = { label, context, count: 0 };
    labels.set(lane, item);
    return item;
  }

  return {
    show(visible) {
      group.visible = visible;
    },
    update(snapshot) {
      if (!group.visible || snapshot === previous) return;
      previous = snapshot;
      const stopped = new Map();
      for (const [, lon, lat, , speed, , lane] of snapshot) {
        if (speed >= .1 || !lanes.has(lane)) continue;
        if (!stopped.has(lane)) stopped.set(lane, [0, 0, 0]);
        const entry = stopped.get(lane);
        entry[0]++;
        entry[1] += lon;
        entry[2] += lat;
      }
      for (const { label } of labels.values()) label.visible = false;
      for (const [lane, [count, lon, lat]] of stopped) {
        if (count < 2) continue;
        const item = labels.get(lane) ?? labelFor(lane);
        const { label, context } = item;
        if (item.count !== count) {
          context.clearRect(0, 0, 200, 58);
          context.beginPath();
          context.roundRect(2, 2, 196, 48, 13);
          context.fillStyle = "#28303b";
          context.fill();
          context.strokeStyle = "#ffd28b";
          context.lineWidth = 3;
          context.stroke();
          context.fillStyle = "#ffe4b6";
          context.font = "bold 25px system-ui";
          context.textAlign = "center";
          context.textBaseline = "middle";
          context.fillText(`${count} detenidos`, 100, 26);
          label.material.map.needsUpdate = true;
          item.count = count;
        }
        const [x, y] = coordinates.fromGeo([lon / count, lat / count]);
        label.position.set(x, 3.4, -y);
        label.userData.count = count;
        label.visible = true;
      }
    },
  };
}
