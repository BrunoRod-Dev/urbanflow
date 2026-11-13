import * as THREE from "three";

export function createMotorcycleModel() {
  const model = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ color: 0xcf421d, roughness: .36 });
  const rubber = new THREE.MeshStandardMaterial({ color: 0x1f2428, roughness: .92 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x8d9ca5, metalness: .47, roughness: .44 });
  const rider = new THREE.MeshStandardMaterial({ color: 0x2c4048, roughness: .84 });
  const helmet = new THREE.MeshStandardMaterial({ color: 0xf6f3e6, roughness: .4 });
  const headlight = new THREE.MeshStandardMaterial({ color: 0xffeed0, emissive: 0x695034 });
  const taillight = new THREE.MeshStandardMaterial({ color: 0xd92e26, emissive: 0x52140d });
  const up = new THREE.Vector3(0, 1, 0);

  function add(geometry, material, x, y, z) {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    model.add(mesh);
    return mesh;
  }

  function shell(material, position, size) {
    const mesh = add(new THREE.SphereGeometry(1, 12, 8), material, ...position);
    mesh.scale.set(...size);
  }

  function bar(material, start, end, radius) {
    const from = new THREE.Vector3(...start);
    const axis = new THREE.Vector3(...end).sub(from);
    const center = from.addScaledVector(axis, .5);
    const mesh = add(new THREE.CylinderGeometry(radius, radius, axis.length(), 8), material, ...center);
    mesh.quaternion.setFromUnitVectors(up, axis.normalize());
  }

  for (const axle of [-.77, .77]) {
    add(new THREE.CylinderGeometry(.31, .31, .13, 20), rubber, 0, .31, axle).rotation.z = Math.PI / 2;
    add(new THREE.CylinderGeometry(.21, .21, .139, 16), metal, 0, .31, axle).rotation.z = Math.PI / 2;
    add(new THREE.CylinderGeometry(.09, .09, .16, 12), rubber, 0, .31, axle).rotation.z = Math.PI / 2;
  }

  shell(paint, [0, .68, -.22], [.235, .20, .36]);
  shell(rubber, [0, .76, .29], [.19, .085, .31]);
  shell(paint, [0, .66, .69], [.16, .11, .29]);
  shell(paint, [0, .58, -.79], [.095, .075, .25]);
  shell(metal, [0, .46, .09], [.20, .165, .26]);
  shell(headlight, [0, .79, -.64], [.115, .10, .105]);
  shell(taillight, [0, .67, .95], [.09, .045, .04]);
  bar(metal, [.20, .40, .08], [.23, .41, .77], .042);
  bar(metal, [-.37, .93, -.50], [.37, .93, -.50], .026);

  shell(rider, [0, 1.05, .05], [.19, .26, .15]);
  shell(helmet, [0, 1.36, -.14], [.117, .14, .15]);
  shell(rubber, [0, 1.38, -.248], [.111, .065, .055]);
  for (const side of [-1, 1]) {
    const offset = value => side * value;
    bar(metal, [offset(.1), .31, -.77], [offset(.1), .90, -.50], .027);
    bar(metal, [offset(.12), .31, .77], [offset(.14), .52, .20], .026);
    bar(metal, [offset(.26), .93, -.50], [offset(.42), 1.05, -.48], .015);
    shell(rubber, [offset(.42), 1.05, -.48], [.047, .039, .032]);
    bar(rider, [offset(.15), 1.19, .02], [offset(.27), 1.06, -.24], .059);
    bar(rider, [offset(.27), 1.06, -.24], [offset(.33), .94, -.48], .048);
    bar(rider, [offset(.13), .87, .22], [offset(.22), .66, -.13], .079);
    bar(rider, [offset(.22), .66, -.13], [offset(.19), .43, .14], .063);
    shell(rubber, [offset(.19), .43, .10], [.075, .047, .115]);
  }
  return model;
}
