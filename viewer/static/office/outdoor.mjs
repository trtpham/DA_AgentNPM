// Campus around the building: lawn, roads with markings, a parking lot, a plaza with a fountain,
// trees, bushes, street lamps and traffic. Repeated things (trees, bushes, dashes, lamps) are
// instanced so hundreds of them cost a handful of draw calls; cars only move while a replay plays.
import * as THREE from "../vendor/three.module.min.js";
import { at, box, mesh } from "./people.mjs";

function seeded(seed) {
  let value = seed;
  return () => { value = (value * 16807) % 2147483647; return (value - 1) / 2147483646; };
}

function canvasTexture(size, paint, repeat) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  paint(canvas.getContext("2d"), size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(...repeat);
  texture.anisotropy = 4;
  return texture;
}

const grassTexture = (repeat) => canvasTexture(128, (g, size) => {
  g.fillStyle = "#3f6b3a"; g.fillRect(0, 0, size, size);
  const random = seeded(3);
  for (let index = 0; index < 2600; index += 1) {
    const tone = random();
    g.fillStyle = tone < 0.5 ? "rgba(90,140,70,.35)" : tone < 0.8 ? "rgba(40,80,40,.35)" : "rgba(150,170,90,.25)";
    g.fillRect(random() * size, random() * size, 1.5, 2.5);
  }
}, repeat);

const asphaltTexture = (repeat) => canvasTexture(128, (g, size) => {
  g.fillStyle = "#2b2f36"; g.fillRect(0, 0, size, size);
  const random = seeded(9);
  for (let index = 0; index < 1800; index += 1) {
    g.fillStyle = `rgba(${random() < 0.5 ? "255,255,255" : "0,0,0"},${random() * 0.08})`;
    g.fillRect(random() * size, random() * size, 1.5, 1.5);
  }
}, repeat);

const pavingTexture = (repeat) => canvasTexture(128, (g, size) => {
  g.fillStyle = "#b8b2a6"; g.fillRect(0, 0, size, size);
  g.strokeStyle = "#9c968a"; g.lineWidth = 2;
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 4; column += 1) g.strokeRect(column * 32 + (row % 2) * 16, row * 32, 32, 32);
  }
}, repeat);

function flat(width, depth, material, y) {
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), material);
  plane.rotation.x = -Math.PI / 2;
  plane.position.y = y;
  plane.receiveShadow = true;
  return plane;
}

function instanced(geometry, material, transforms, shadow = true) {
  const item = new THREE.InstancedMesh(geometry, material, transforms.length);
  const matrix = new THREE.Matrix4();
  const quaternion = new THREE.Quaternion();
  transforms.forEach(({ position, scale = [1, 1, 1], turn = 0, color }, index) => {
    quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), turn);
    matrix.compose(new THREE.Vector3(...position), quaternion, new THREE.Vector3(...scale));
    item.setMatrixAt(index, matrix);
    if (color) item.setColorAt(index, new THREE.Color(color));
  });
  item.castShadow = shadow;
  item.receiveShadow = true;
  return item;
}

function car(color) {
  const group = new THREE.Group();
  group.add(at(box(1.9, 0.55, 4.2, color, { metalness: 0.3, roughness: 0.4 }), 0, 0.55, 0));
  group.add(at(box(1.7, 0.5, 2.2, color, { metalness: 0.3, roughness: 0.4 }), 0, 1.05, -0.2));
  group.add(at(box(1.72, 0.38, 2.0, "#1a2a3a", { metalness: 0.6, roughness: 0.1 }), 0, 1.08, -0.2));
  for (const x of [-0.95, 0.95]) for (const z of [-1.35, 1.35]) {
    const wheel = at(mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.22, 14), "#111418"), x, 0.34, z);
    wheel.rotation.z = Math.PI / 2;
    group.add(wheel);
  }
  for (const x of [-0.6, 0.6]) group.add(at(box(0.3, 0.12, 0.05, "#fff4c8", { emissive: "#fff4c8", emissiveIntensity: 1.2, shadow: false }), x, 0.65, 2.11));
  for (const x of [-0.6, 0.6]) group.add(at(box(0.3, 0.12, 0.05, "#ff3b30", { emissive: "#ff3b30", emissiveIntensity: 0.8, shadow: false }), x, 0.65, -2.11));
  return group;
}

function truck() {
  const group = new THREE.Group();
  group.add(at(box(2.3, 2.4, 5, "#e8e1d4"), 0, 1.6, -0.8));
  group.add(at(box(2.2, 1.6, 1.8, "#c99a5b", { metalness: 0.2 }), 0, 1.15, 2.6));
  group.add(at(box(2.1, 0.7, 0.05, "#1a2a3a", { metalness: 0.6, roughness: 0.1 }), 0, 1.6, 3.51));
  for (const x of [-1.1, 1.1]) for (const z of [-2.4, 0.6, 2.6]) {
    const wheel = at(mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.3, 14), "#111418"), x, 0.42, z);
    wheel.rotation.z = Math.PI / 2;
    group.add(wheel);
  }
  // A logo panel: a parcel icon in the building's accent colour.
  group.add(at(box(0.05, 1, 1.2, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.4, shadow: false }), 1.18, 1.8, -0.8));
  return group;
}

/**
 * Build the campus. `keepOut` is the building's rectangle, where nothing may stand.
 * Returns { group, update(delta) } — update moves the traffic.
 */
export function createCampus(keepOut) {
  const group = new THREE.Group();
  const random = seeded(21);
  const inside = (x, z, margin = 0) => x > keepOut.minX - margin && x < keepOut.maxX + margin && z > keepOut.minZ - margin && z < keepOut.maxZ + margin;

  // Ground, main road (z = 26), access road to the gate (x = -42), parking lot, plaza.
  group.add(flat(260, 200, new THREE.MeshStandardMaterial({ map: grassTexture([60, 46]), roughness: 1 }), -0.36));
  const asphalt = (width, depth) => new THREE.MeshStandardMaterial({ map: asphaltTexture([width / 6, depth / 6]), roughness: 0.95 });
  const road = flat(240, 10, asphalt(240, 10), -0.33);
  road.position.z = 26;
  group.add(road);
  for (const z of [20.4, 31.6]) group.add(at(flat(240, 2.2, new THREE.MeshStandardMaterial({ color: "#8e939a", roughness: 0.9 }), -0.32), 0, 0, z));
  const access = flat(7, 40, asphalt(7, 40), -0.33);
  access.position.set(-42, 0, 4);
  group.add(access);
  const parking = flat(22, 26, asphalt(22, 26), -0.33);
  parking.position.set(-56, 0, 4);
  group.add(parking);
  const plaza = flat(10, 22, new THREE.MeshStandardMaterial({ map: pavingTexture([4, 8]), roughness: 0.9 }), -0.32);
  plaza.position.set(-33.5, 0, 0);
  group.add(plaza);
  const frontWalk = flat(64, 3, new THREE.MeshStandardMaterial({ map: pavingTexture([22, 1]), roughness: 0.9 }), -0.32);
  frontWalk.position.set(2.5, 0, keepOut.maxZ + 2.2);
  group.add(frontWalk);

  // Road markings: dashed centre line, edge lines, parking stalls, a zebra crossing.
  const white = new THREE.MeshStandardMaterial({ color: "#f4f1ea", roughness: 0.6 });
  const yellow = new THREE.MeshStandardMaterial({ color: "#f4c430", roughness: 0.6 });
  const dash = new THREE.BoxGeometry(2.4, 0.02, 0.22);
  const dashes = [];
  for (let x = -118; x < 118; x += 5) dashes.push({ position: [x, -0.31, 26] });
  group.add(instanced(dash, yellow, dashes, false));
  for (const z of [21.4, 30.6]) group.add(at(box(240, 0.02, 0.16, "#f4f1ea", { shadow: false }), 0, -0.31, z));
  // Unit box scaled per instance: stall lines are 0.15 x 5 m between the parking slots.
  const unit = new THREE.BoxGeometry(1, 0.02, 1);
  const stalls = [];
  for (let row = 0; row < 2; row += 1) for (let index = 0; index < 9; index += 1) {
    stalls.push({ position: [-64.5 + index * 3, -0.31, row ? 10.8 : -2.8], scale: [0.15, 1, 5] });
  }
  group.add(instanced(unit, white, stalls, false));
  // Zebra crossing where the sidewalk crosses the access road.
  const zebra = [];
  for (let index = 0; index < 7; index += 1) zebra.push({ position: [-44.7 + index * 0.9, -0.31, 20.4], scale: [0.5, 1, 2.2] });
  group.add(instanced(unit, white, zebra, false));

  // Parked cars in the lot; the courier's truck at the gate.
  const carColors = ["#c0392b", "#2b7de9", "#f4f1ea", "#1a1f26", "#8e939a", "#f4c430", "#3f9a6b", "#7a5c8f", "#e67e22", "#5c6b7a"];
  [[0, 0], [1, 0], [3, 0], [4, 0], [6, 0], [0, 1], [2, 1], [3, 1], [5, 1], [7, 1]].forEach(([slot, row], index) => {
    const parked = car(carColors[index % carColors.length]);
    parked.position.set(-63 + slot * 3, -0.33, row ? 10.8 : -2.8);
    parked.rotation.y = row ? Math.PI : 0;
    group.add(parked);
  });
  const delivery = truck();
  delivery.position.set(-42, -0.33, -3);
  group.add(delivery);

  // Plaza: fountain, flagpole, benches.
  const fountain = new THREE.Group();
  fountain.add(at(mesh(new THREE.CylinderGeometry(2.2, 2.4, 0.6, 28), "#9c968a"), 0, -0.05, 0));
  fountain.add(at(mesh(new THREE.CylinderGeometry(1.9, 1.9, 0.1, 28), "#5fb8e8", { emissive: "#2b7de9", emissiveIntensity: 0.25, roughness: 0.1, metalness: 0.3 }), 0, 0.22, 0));
  fountain.add(at(mesh(new THREE.CylinderGeometry(0.25, 0.4, 1.4, 12), "#b8b2a6"), 0, 0.6, 0));
  const spray = at(mesh(new THREE.ConeGeometry(0.6, 1.2, 16, 1, true), "#bfe6ff", { opacity: 0.45, emissive: "#9fd8ff", emissiveIntensity: 0.5, shadow: false }), 0, 1.6, 0);
  spray.rotation.x = Math.PI;
  fountain.add(spray);
  fountain.position.set(-34.5, -0.33, 8);
  group.add(fountain);
  group.add(at(mesh(new THREE.CylinderGeometry(0.08, 0.1, 9, 8), "#c9cdd2", { metalness: 0.6 }), -35.5, 4.2, -7.5));
  const flag = at(box(2.2, 1.3, 0.05, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.25 }), -34.3, 7.8, -7.5);
  group.add(flag);
  const bench = () => {
    const seat = new THREE.Group();
    seat.add(at(box(2, 0.1, 0.6, "#7a5236"), 0, 0.45, 0), at(box(2, 0.5, 0.08, "#7a5236"), 0, 0.75, -0.26));
    for (const x of [-0.85, 0.85]) seat.add(at(box(0.08, 0.45, 0.5, "#26384a"), x, 0.22, 0));
    return seat;
  };
  for (const [x, z, turn] of [[-31.5, 6.5, -Math.PI / 2], [-31.5, 9.5, -Math.PI / 2], [-37.5, 8, Math.PI / 2]]) {
    const seat = bench();
    seat.position.set(x, -0.33, z);
    seat.rotation.y = turn;
    group.add(seat);
  }

  // Trees: avenue along the road, a park to the north, groves to the east and around the lot.
  const trees = [];
  const plant = (x, z, scale) => { if (!inside(x, z, 3) && Math.abs(z - 26) > 6.5 && !(x > -68 && x < -44 && z > -10 && z < 18)) trees.push({ x, z, scale }); };
  for (let x = -110; x <= 110; x += 9) { plant(x + random() * 2, 18.6, 0.9 + random() * 0.3); plant(x + 4 + random() * 2, 33.6, 0.9 + random() * 0.3); }
  for (let index = 0; index < 120; index += 1) plant(-80 + random() * 160, -22 - random() * 50, 0.8 + random() * 0.8);
  for (let index = 0; index < 45; index += 1) plant(38 + random() * 50, -18 + random() * 34, 0.8 + random() * 0.7);
  for (let index = 0; index < 30; index += 1) plant(-100 + random() * 30, -20 + random() * 40, 0.8 + random() * 0.6);
  for (const x of [-46, -66.5]) for (let z = -10; z <= 18; z += 5) plant(x, z, 0.75);
  const round = trees.filter((_, index) => index % 3 !== 0);
  const pointed = trees.filter((_, index) => index % 3 === 0);
  const greens = ["#3f9a6b", "#2f7d55", "#57b884", "#4a8f3c", "#6aa84f"];
  group.add(instanced(new THREE.CylinderGeometry(0.22, 0.3, 2.2, 7), new THREE.MeshStandardMaterial({ color: "#6b4a2f", roughness: 1 }),
                      trees.map(({ x, z, scale }) => ({ position: [x, 0.75 * scale, z], scale: [scale, scale, scale] }))));
  group.add(instanced(new THREE.IcosahedronGeometry(1.7, 0), new THREE.MeshStandardMaterial({ roughness: 1, flatShading: true }),
                      round.map(({ x, z, scale }) => ({ position: [x, 2.9 * scale, z], scale: [scale, scale * 1.05, scale], turn: x, color: greens[Math.floor(Math.abs(x * 7 + z)) % greens.length] }))));
  group.add(instanced(new THREE.ConeGeometry(1.5, 3.8, 7), new THREE.MeshStandardMaterial({ roughness: 1, flatShading: true }),
                      pointed.map(({ x, z, scale }) => ({ position: [x, 3.2 * scale, z], scale: [scale, scale, scale], turn: z, color: greens[Math.floor(Math.abs(x + z * 3)) % greens.length] }))));

  // Bushes hugging the building and lining the front walk.
  const bushes = [];
  for (let x = keepOut.minX + 2; x < keepOut.maxX; x += 2.4 + random() * 1.6) {
    bushes.push({ position: [x, 0.25, keepOut.maxZ + 0.9], scale: [0.8 + random() * 0.5, 0.7, 0.8], color: greens[Math.floor(random() * 5)] });
    bushes.push({ position: [x, 0.25, keepOut.minZ - 0.9], scale: [0.8 + random() * 0.5, 0.7, 0.8], color: greens[Math.floor(random() * 5)] });
  }
  for (let z = keepOut.minZ + 2; z < keepOut.maxZ; z += 2.6) bushes.push({ position: [keepOut.maxX + 0.9, 0.25, z], scale: [0.9, 0.7, 0.9], color: greens[Math.floor(random() * 5)] });
  group.add(instanced(new THREE.IcosahedronGeometry(0.9, 0), new THREE.MeshStandardMaterial({ roughness: 1, flatShading: true }), bushes));

  // Street lamps along the road and the access road.
  const lamps = [];
  for (let x = -104; x <= 104; x += 16) lamps.push([x, 20.2]);
  for (let z = -6; z <= 16; z += 8) lamps.push([-38.4, z]);
  group.add(instanced(new THREE.CylinderGeometry(0.08, 0.1, 5, 6), new THREE.MeshStandardMaterial({ color: "#3a4656", metalness: 0.5 }),
                      lamps.map(([x, z]) => ({ position: [x, 2.2, z] }))));
  group.add(instanced(new THREE.SphereGeometry(0.32, 10, 8), new THREE.MeshStandardMaterial({ color: "#fff1c8", emissive: "#ffe1a0", emissiveIntensity: 1.6 }),
                      lamps.map(([x, z]) => ({ position: [x, 4.8, z] })), false));

  // Distant city skyline beyond the park.
  const skylineCanvas = canvasTexture(512, (g, size) => {
    const sky = g.createLinearGradient(0, 0, 0, size);
    sky.addColorStop(0, "#0d1b2e"); sky.addColorStop(1, "#2b4c6e");
    g.fillStyle = sky; g.fillRect(0, 0, size, size);
    const rnd = seeded(5);
    for (let x = 0; x < size;) {
      const width = 14 + rnd() * 30;
      const height = size * (0.25 + rnd() * 0.5);
      g.fillStyle = `rgb(${16 + rnd() * 12},${28 + rnd() * 14},${44 + rnd() * 18})`;
      g.fillRect(x, size - height, width, height);
      for (let y = size - height + 6; y < size - 6; y += 9) for (let wx = x + 3; wx < x + width - 4; wx += 7) {
        if (rnd() < 0.4) { g.fillStyle = rnd() < 0.8 ? "rgba(255,214,140,.85)" : "rgba(140,210,255,.8)"; g.fillRect(wx, y, 3, 4); }
      }
      x += width + 2;
    }
  }, [3, 1]);
  const skyline = new THREE.Mesh(new THREE.PlaneGeometry(320, 40), new THREE.MeshBasicMaterial({ map: skylineCanvas }));
  skyline.position.set(0, 18, -95);
  group.add(skyline);

  // Traffic: cars loop along the two lanes of the main road.
  const traffic = [];
  for (let index = 0; index < 8; index += 1) {
    const moving = car(carColors[(index * 3) % carColors.length]);
    const eastbound = index % 2 === 0;
    moving.position.set(-110 + index * 29, -0.33, eastbound ? 28.2 : 23.8);
    moving.rotation.y = eastbound ? Math.PI / 2 : -Math.PI / 2;
    group.add(moving);
    traffic.push({ car: moving, speed: (eastbound ? 1 : -1) * (9 + (index % 3) * 2.5) });
  }
  return {
    group,
    update(delta) {
      for (const { car: moving, speed } of traffic) {
        moving.position.x += speed * delta;
        if (moving.position.x > 120) moving.position.x = -120;
        if (moving.position.x < -120) moving.position.x = 120;
      }
      spray.rotation.y += delta * 2;
    },
  };
}
