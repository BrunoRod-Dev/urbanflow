"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function controls() {
  const elements = new Map();
  const effects = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: "", checked: false, hidden: true, children: [],
      addEventListener(name, handler) { this[name] = handler; },
      replaceChildren(...children) { this.children = children; this.value = children[0].value; },
    });
    return elements.get(id);
  }
  const panel = element("#replay-qa");
  panel.querySelector = element;
  const roads = { ...element("roads"), dataset: { qaLayer: "roads" } };
  panel.querySelectorAll = () => [roads];
  const source = fs.readFileSync(path.join(__dirname, "../urbanflow-web/replay-qa.js"), "utf8");
  const create = vm.runInNewContext(`${source}\ncreateReplayQa`, {
    document: { querySelector: element },
    Option: function (label, value) { Object.assign(this, { label, value }); },
  });
  const map = Object.fromEntries(["qaConfigure", "qaFollow", "qaLocate", "qaLayer", "qaFit"]
    .map(name => [name, (...args) => effects.push([name, ...args])]));
  const views = Object.fromEntries(["qaConfigure", "qaFollow", "qaLocate", "qaLayer", "qaFit"]
    .map(name => [name, (...args) => effects.push([`3D:${name}`, ...args])]));
  return { element, effects, roads, qa: create(map, time => effects.push(["seek", time]), () => {}, views) };
}

test("static alerts can be located and only in-range recorded times can be selected", () => {
  const { qa, element, effects } = controls();
  qa.configure({ frames: [[0], [300]], vehicleIndex: [{ sumoId: "car" }] }, {
    events: [{ id: "static", time: null, coordinates: [1, 2], evidence: {} },
      { id: "recorded", time: 110.5, coordinates: [2, 3], evidence: {} },
      { id: "outside", time: 400, evidence: {} }],
  });
  const alerts = element("#qa-event");
  const jump = element("#qa-jump");
  alerts.value = "static";
  alerts.change();
  assert.equal(jump.disabled, true);
  element("#qa-locate").click();
  assert.deepEqual(effects.slice(-2), [["qaLocate", [1, 2]], ["3D:qaLocate", [1, 2]]]);
  alerts.value = "recorded";
  alerts.change();
  assert.equal(jump.disabled, false);
  jump.click();
  assert.deepEqual(effects.at(-1), ["seek", 110.5]);
  alerts.value = "outside";
  alerts.change();
  assert.equal(jump.disabled, true);
});

test("vehicle zero can be followed and raw mode resets when leaving QA", () => {
  const { qa, element, effects, roads } = controls();
  qa.configure({ frames: [[0], [1]], vehicleIndex: [{ sumoId: "car" }] });
  const vehicle = element("#qa-vehicle");
  vehicle.value = "0";
  vehicle.change();
  assert.deepEqual(effects.slice(-2), [["qaFollow", 0], ["3D:qaFollow", 0]]);
  roads.checked = false;
  roads.change();
  assert.deepEqual(effects.slice(-2), [["qaLayer", "roads", false], ["3D:qaLayer", "roads", false]]);
  element("#qa-raw").checked = true;
  assert.equal(qa.raw, true);
  qa.configure(null);
  assert.equal(qa.raw, false);
  assert.equal(element("#replay-qa").hidden, true);
});

test("QA distinguishes an inactive vehicle from active vehicles outside the frame", () => {
  const { qa, element } = controls();
  qa.configure({ frames: [[0], [1]], vehicleIndex: [{ sumoId: "car" }] });
  element("#qa-vehicle").value = "0";
  qa.updateStatus([], 2);
  assert.match(element("#qa-follow-status").textContent, /no está activo/);
  qa.updateStatus([[0]], 2);
  assert.match(element("#qa-follow-status").textContent, /2 vehículos activos/);
  qa.updateStatus([[0]], 0);
  assert.equal(element("#qa-follow-status").textContent, "");
});
