import * as THREE from "three";

export function addContactShadows(scene, name, capacity) {
  const size = 48;
  const pixels = new Uint8Array(size * size * 4);
  for (let index = 0; index < size * size; index++) {
    const x = Math.abs((index % size + .5) / size * 2 - 1);
    const y = Math.abs((Math.floor(index / size) + .5) / size * 2 - 1);
    const radius = Math.hypot(x ** 1.7, y ** 1.7);
    const alpha = 1 - THREE.MathUtils.smoothstep(radius, .32, .98);
    pixels.set([255, 255, 255, Math.round(alpha * 255)], index * 4);
  }
  const texture = new THREE.DataTexture(pixels, size, size);
  texture.magFilter = texture.minFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  const material = new THREE.MeshBasicMaterial({ map: texture, color: 0x172228, opacity: .5,
    transparent: true, depthWrite: false, toneMapped: false });
  const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), material, capacity);
  mesh.name = name;
  mesh.count = 0;
  mesh.frustumCulled = false;
  mesh.renderOrder = -1;
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(mesh);
  return mesh;
}
