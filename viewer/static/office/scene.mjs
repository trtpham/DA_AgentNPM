// The 3D office drawn with Three.js. Rendering only; trace logic lives in events.mjs/explain.mjs/main.mjs.
// People are the AI models (workers) and office staff; robots are deterministic code (tools, checks, rules).
import * as THREE from "../vendor/three.module.min.js";
import { OrbitControls } from "../vendor/OrbitControls.js";
import { ROOMS } from "./events.mjs";
import { at, box, mesh, personMesh, robotMesh } from "./people.mjs";
import { barrierGate, chair, coffeeBar, desk, monitor, plant, printer, rug, serverRack, shelf, sofa,
         textures, waterCooler, wallPoster, workstation } from "./props.mjs";

// An irregular floor: every area has its own size, rows are staggered, two wings are turned a little,
// and walls come in three kinds (glass, solid, open plan). The hallway runs along z = HALL_Z.
// The six step rooms follow the agent; the four wings hold the npm gate, the local GPU server,
// the human reviewer and the pantry.
const HALL_Z = 0.3;
const AREAS = {
  gate: { at: [-15.2, -4.0], size: [4.8, 5.2], walls: "glass" },
  reception: { at: [-9.0, -4.4], size: [6.6, 5.0], walls: "glass" },
  code: { at: [-1.2, -5.0], size: [8.2, 6.0], walls: "glass" },
  intel: { at: [6.4, -4.2], size: [4.6, 4.4], walls: "glass" },
  server: { at: [12.6, -5.2], size: [5.6, 5.6], walls: "solid" },
  reviewer: { at: [-15.0, 4.6], size: [4.6, 4.2], walls: "open", turn: 0.08 },
  decision: { at: [-8.6, 5.2], size: [7.0, 5.8], walls: "glass" },
  evidence: { at: [-1.0, 4.4], size: [5.6, 4.4], walls: "glass" },
  lab: { at: [5.6, 4.9], size: [5.0, 5.0], walls: "solid" },
  pantry: { at: [12.8, 4.3], size: [6.2, 4.6], walls: "open", turn: -0.1 },
};
const LAYOUT = { ...Object.fromEntries(Object.entries(AREAS).map(([id, area]) => [id, area.at])), hallway: [0, HALL_Z] };
const BOUNDS = { minX: -18, maxX: 16, minZ: -8.7, maxZ: 8.4 };
const WINGS = {
  gate: { name: "Cổng npm", step: "npm pack · barie theo quyết định" },
  server: { name: "Máy chủ Ollama", step: "Mô hình chạy cục bộ trên GPU" },
  reviewer: { name: "Bàn người xem", step: "Ca R7/R8 cần duyệt tay" },
  pantry: { name: "Pantry", step: "Nghỉ giải lao" },
};
// A three-quarter view from the south-west reads less like a floor plan than a straight front view.
const VIEW_DIRECTION = new THREE.Vector3(-5, 17, 15).normalize();
const inside = (id, dx, dz) => [AREAS[id].at[0] + dx, AREAS[id].at[1] + dz];
export const ACCENT = {
  reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8", evidence: "#ffd08a",
  decision: "#ff8e83", hallway: "#6f8597", gate: "#f4b860", server: "#ff7ad9", reviewer: "#e8f4ff", pantry: "#c99a5b",
};
const FLOORS = {
  gate: "tiles", reception: "wood", code: "#2c4a6b", intel: "#43386b", server: "tiles",
  reviewer: "#3a4656", decision: "wood", evidence: "#5a4a2c", lab: "tiles", pantry: "wood",
};
const ACTION_COLORS = { approve: "#2fe0a8", review: "#ffaa1a", deny: "#ff4a3d" }; // saturated: ACES tone mapping washes pale tints to white
const ease = (value) => 1 - (1 - value) ** 3;

function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(value || fallback);
}

function floorMaterial(kind) {
  if (kind === "wood") return { map: textures.wood([2, 2]) };
  if (kind === "tiles") return { map: textures.tiles([4, 3]) };
  return { map: textures.carpet(kind, [3, 3]) };
}

function roomShell(id) {
  const info = ROOMS[id] || WINGS[id];
  const area = AREAS[id];
  const [x, z] = area.at;
  const [width, depth] = area.size;
  const away = Math.sign(z - HALL_Z); // the back wall is on the side away from the hallway
  const accent = new THREE.Color(ACCENT[id]);
  const group = new THREE.Group();
  group.position.set(x, 0, z);
  group.rotation.y = area.turn || 0;
  const floor = box(width, 0.1, depth, "#ffffff", { shadow: false, ...floorMaterial(FLOORS[id]) });
  if (info.locked) floor.material.color.set("#8a96a3");
  group.add(floor);
  if (area.walls === "open") {
    // Open plan: no walls, only a thin accent border on the floor.
    for (const side of [-1, 1]) {
      group.add(at(box(width, 0.03, 0.08, accent, { emissive: accent, emissiveIntensity: 0.5, shadow: false }), 0, 0.07, side * depth / 2));
      group.add(at(box(0.08, 0.03, depth, accent, { emissive: accent, emissiveIntensity: 0.5, shadow: false }), side * width / 2, 0.07, 0));
    }
    return { group, floor, away, accent, base: floor.material.color.clone(), x, z, info, width, depth };
  }
  // Rooms whose back wall faces the camera get a low cut-away wall, as in isometric games.
  const wallHeight = away > 0 ? 0.4 : 1.7;
  group.add(at(box(width, wallHeight, 0.16, "#2a3d52"), 0, wallHeight / 2, away * depth / 2));
  group.add(at(box(width, 0.08, 0.18, accent, { emissive: accent, emissiveIntensity: 0.6, shadow: false }), 0, wallHeight + 0.02, away * depth / 2));
  const solid = area.walls === "solid";
  const pane = solid ? ["#34495f", { roughness: 0.7 }] : ["#9fd8ff", { opacity: 0.16, roughness: 0.1, metalness: 0.2, shadow: false }];
  const height = solid ? 1.1 : 1.3;
  for (const side of [-1, 1]) {
    group.add(at(box(0.1, height, depth, pane[0], pane[1]), side * width / 2, height / 2, 0));
    group.add(at(box(0.14, 0.08, depth, "#22344a", { shadow: false }), side * width / 2, height + 0.02, 0));
    // Front wall with an off-centre doorway, so no two rooms look the same.
    const door = 1.3;
    const doorAt = (id.length % 3 - 1) * width * 0.18;
    const left = doorAt - door / 2 + width / 2;
    const right = width / 2 - (doorAt + door / 2);
    const piece = side < 0 ? left : right;
    const centre = side < 0 ? -width / 2 + left / 2 : width / 2 - right / 2;
    if (piece > 0.2) group.add(at(box(piece, height, 0.07, pane[0], pane[1]), centre, height / 2, -away * depth / 2));
  }
  return { group, floor, away, accent, base: floor.material.color.clone(), x, z, info, width, depth };
}

export function createOffice(canvas, labelLayer, overlayLayer) {
  const colors = { bg: token("--bg", "#09111d") };
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  // A-LLM shares the 6 GB GPU with this page: cap the pixel ratio and keep one shadow map.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  const scene = new THREE.Scene();
  scene.background = colors.bg;
  scene.fog = new THREE.Fog(colors.bg, 48, 95);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 220);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.42; // never under the floor
  controls.enablePan = false;

  scene.add(new THREE.HemisphereLight(0xe6f2ff, 0x101a26, 1.3));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
  sun.position.set(-10, 22, -8);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1536, 1536);
  Object.assign(sun.shadow.camera, { left: -19, right: 19, top: 10, bottom: -10, near: 1, far: 60 });
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  // Building: slab, city skyline behind the north windows, an uneven hallway with an atrium.
  scene.add(at(box(BOUNDS.maxX - BOUNDS.minX + 0.8, 0.3, BOUNDS.maxZ - BOUNDS.minZ + 0.4, "#0e1824", { shadow: false }),
               (BOUNDS.minX + BOUNDS.maxX) / 2, -0.2, (BOUNDS.minZ + BOUNDS.maxZ) / 2));
  const glowing = (item, strength) => {
    item.material.emissive = new THREE.Color("#ffffff");
    item.material.emissiveMap = item.material.map;
    item.material.emissiveIntensity = strength;
    return item;
  };
  scene.add(at(glowing(mesh(new THREE.PlaneGeometry(40, 7), "#ffffff", { map: textures.skyline(), shadow: false }), 0.55), -1, 3, -9.1));
  for (let x = -17.6; x <= 15.8; x += 2.6 + Math.abs(Math.sin(x)) * 1.4) scene.add(at(box(0.18, 3.4, 0.18, "#2a3d52"), x, 1.7, -8.75));
  scene.add(at(box(34, 0.18, 0.2, "#2a3d52"), -1, 3.4, -8.75));
  const hallway = box(34, 0.06, 3.4, "#9aa0a8", { shadow: false, map: textures.wood([10, 1]) });
  hallway.position.set(-1, 0, HALL_Z);
  scene.add(hallway);
  scene.add(at(rug(9, 1.1, "#2b4a5c"), -11.5, 0.05, HALL_Z));
  scene.add(at(rug(7.5, 1.1, "#3a2f4f"), 9.6, 0.05, HALL_Z + 0.1));
  const atrium = mesh(new THREE.CircleGeometry(1.7, 40), "#ffffff", { map: textures.carpet("#2f5b55", [2, 2]), shadow: false });
  atrium.rotation.x = -Math.PI / 2;
  scene.add(at(atrium, 2.6, 0.05, HALL_Z));
  const tree = plant(1.9);
  scene.add(at(tree, 2.6, 0, -1.15));
  scene.add(at(sofa("#2f5b55"), -4.2, 0, 1.75).rotateY(Math.PI));
  for (const [x, z, size] of [[-12.6, -1.15, 1], [-6.1, 1.8, 0.7], [7.8, -1.1, 1.2], [11.4, 1.85, 0.8], [-17.2, 1.6, 1.3]]) scene.add(at(plant(size), x, 0, z));
  scene.add(at(waterCooler(), 15.6, 0, 1.6));
  for (const [x, z] of [[-2.2, -1.2], [8.9, 1.85]]) scene.add(at(mesh(new THREE.CylinderGeometry(0.2, 0.17, 0.45, 12), "#5c6b7a"), x, 0.22, z));
  scene.add(at(glowing(mesh(new THREE.PlaneGeometry(4.2, 0.8), "#ffffff", { map: textures.sign("NPM AGENT HQ", "#61e8c2"), shadow: false }), 0.8),
               -15.2, 2.6, -6.5));

  const rooms = {};
  for (const id of [...Object.keys(ROOMS), ...Object.keys(WINGS)]) {
    if (id === "hallway") {
      rooms[id] = { floor: hallway, base: hallway.material.color.clone(), x: 0, z: HALL_Z, accent: new THREE.Color(ACCENT.hallway),
                    labelAt: [-17.3, 0.5, HALL_Z], info: ROOMS.hallway };
      continue;
    }
    const room = roomShell(id);
    room.labelAt = room.away > 0 ? [room.x, 0.6, room.z + room.depth / 2 + 0.3] : [room.x, 2.2, room.z - room.depth / 2];
    scene.add(room.group);
    rooms[id] = room;
  }
  const add = (room, item, x, y, z, turn = 0) => { item.position.set(x, y, z); item.rotation.y = turn; rooms[room].group.add(item); return item; };

  // Gate: a door in the west wall, the barrier, parcels and the guard's desk.
  add("gate", box(0.12, 2.2, 1.6, "#3a5068"), -2.35, 1.1, -0.4);
  add("gate", box(0.06, 2, 1.4, "#9fd8ff", { opacity: 0.35, shadow: false }), -2.32, 1, -0.4);
  const gate = add("gate", barrierGate(), 0.8, 0, 2.0, Math.PI);
  add("gate", desk(1.2, 0.6), 1.3, 0, -1.6, 0.15);
  add("gate", monitor("#f4b860", 0.6), 1.3, 0.92, -1.75, 0.15);
  add("gate", plant(1.1), -1.9, 0, -2.1);
  for (let index = 0; index < 3; index += 1) add("gate", box(0.5, 0.4, 0.45, "#c99a5b"), -1.5 + index * 0.12, 0.2 + index * 0.4, -1.3, index * 0.3);

  // Reception: a curved counter, a waiting sofa, plants and a safety poster.
  const counter = mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.95, 24, 1, true, Math.PI * 0.15, Math.PI * 0.7), "#e8e1d4", { roughness: 0.6 });
  counter.material.side = THREE.DoubleSide;
  add("reception", counter, 0.4, 0.48, 0.2);
  add("reception", box(2.4, 0.06, 0.5, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.4 }), 0.4, 0.98, -1.1);
  add("reception", plant(), -2.8, 0, -1.9);
  add("reception", plant(0.8), 2.9, 0, -1.7);
  add("reception", sofa("#4a6a7a"), -2.1, 0, 1.1, 0.35);
  add("reception", wallPoster("AN TOÀN", ["Không chạy mã gói", "trên máy thật.", "Chỉ npm pack", "+ đọc file."], "#61e8c2"), -1.7, 1.15, -2.42);
  const parcel = new THREE.Group();
  parcel.add(box(0.7, 0.5, 0.55, "#c99a5b", { roughness: 0.9 }));
  parcel.add(at(box(0.72, 0.06, 0.12, "#e8e1d4", { shadow: false }), 0, 0.25, 0));
  add("reception", parcel, 1.6, 1.25, 0.3, 0.4);

  // Code room: an open-plan cluster of four desks, a whiteboard and a tall plant.
  const screens = [];
  for (const [x, z, turn] of [[-2.7, -1.9, 0], [-0.7, -2.0, 0.06], [2.0, -1.4, -0.4], [2.9, 0.7, -1.35]]) {
    screens.push(add("code", workstation(ACCENT.code), x, 0, z, turn).userData.screen);
  }
  add("code", mesh(new THREE.PlaneGeometry(2.4, 1.2), "#ffffff", { map: textures.whiteboard(), shadow: false }), -1.6, 1.05, -2.9);
  add("code", plant(1.4), 3.6, 0, -2.5);
  add("code", mesh(new THREE.CylinderGeometry(0.18, 0.15, 0.4, 12), "#5c6b7a"), -3.6, 0.2, 0.9);

  // Intel room: a small library with two shelves, a globe and a reading chair.
  add("intel", shelf(ACCENT.intel), -1.0, 0, -1.75);
  add("intel", shelf(ACCENT.intel), 1.0, 0, -1.75);
  add("intel", mesh(new THREE.CylinderGeometry(0.06, 0.25, 0.7, 8), "#5b4636"), -1.1, 0.35, 0.6);
  const globe = add("intel", mesh(new THREE.IcosahedronGeometry(0.42, 1), "#7cc4ff", { roughness: 0.4, metalness: 0.1 }), -1.1, 1.05, 0.6);
  add("intel", chair("#5b4636"), 1.3, 0, 0.8, -0.7);

  // Server room: GPU racks whose lights follow the models that are thinking, and an operator desk.
  const racks = [[-2.0, -2.1, 0], [-0.9, -2.1, 0], [0.2, -2.15, 0.04]].map(([x, z, turn]) => add("server", serverRack(ACCENT.server), x, 0, z, turn));
  add("server", glowing(mesh(new THREE.PlaneGeometry(2.6, 0.5), "#ffffff", { map: textures.sign("OLLAMA · GPU 6 GB", "#ff7ad9"), shadow: false }), 0.9),
      -0.9, 2.5, -2.7);
  add("server", desk(1.3, 0.7), 1.9, 0, -0.4, -Math.PI / 2);
  add("server", monitor("#ff7ad9", 0.7), 1.75, 0.92, -0.4, -Math.PI / 2);
  for (let index = 0; index < 4; index += 1) add("server", box(0.08, 0.05, 2.2, "#ffd08a", { shadow: false }), -2.0 + index * 0.75, 0.07, -0.6);
  const leds = racks.flatMap((rack) => rack.userData.leds);
  const gpuGlow = add("server", new THREE.PointLight(0xff7ad9, 0, 6, 1.6), -0.9, 1.6, -0.8);

  // Sandbox lab: sealed until W5-6 connects the sandbox to the agent.
  add("lab", box(2.4, 1.6, 1.6, "#9fd8ff", { opacity: 0.25, roughness: 0.05, metalness: 0.3, shadow: false }), 0.3, 0.85, 0.7);
  add("lab", box(1, 0.6, 0.7, "#5c6b7a"), 0.3, 0.35, 0.7);
  for (let index = 0; index < 7; index += 1) {
    add("lab", box(0.45, 0.06, 0.12, index % 2 ? "#141c26" : "#ffd08a", { shadow: false }), -1.6 + index * 0.45, 0.06, -2.2);
  }
  const lock = new THREE.Group();
  lock.add(box(0.36, 0.3, 0.12, "#ffd08a", { metalness: 0.6, roughness: 0.3 }));
  lock.add(at(mesh(new THREE.TorusGeometry(0.12, 0.035, 8, 16, Math.PI), "#c9cdd2", { metalness: 0.8 }), 0, 0.15, 0));
  add("lab", lock, 1.4, 1.1, -2.5);

  // Evidence room: a long table where one sheet per evidence check appears, plus a file cabinet.
  add("evidence", box(3.6, 0.08, 1.2, "#c9b48f"), -0.2, 0.76, 0.5, 0.05);
  for (const x of [-1.8, 1.4]) for (const z of [0, 1.0]) add("evidence", box(0.08, 0.74, 0.08, "#26384a"), x, 0.37, z);
  add("evidence", box(0.6, 1.3, 0.55, "#5c6b7a", { metalness: 0.4 }), 2.3, 0.65, 1.5, -0.2);
  const papers = add("evidence", new THREE.Group(), -0.2, 0.81, 0.5, 0.05);

  // Decision room: a courtroom with a raised bench, three lamps and benches for the public.
  add("decision", box(3.6, 0.25, 1.8, "#2b3b4e"), 0, 0.12, 1.3);
  add("decision", box(3.0, 1.05, 0.7, "#5b4636", { roughness: 0.5 }), 0, 0.77, 1.1);
  const lamps = {};
  Object.entries(ACTION_COLORS).forEach(([action, color], index) => {
    add("decision", mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8), "#26384a"), -0.9 + index * 0.9, 1.5, 1.1);
    lamps[action] = add("decision", mesh(new THREE.SphereGeometry(0.22, 18, 14), color, { emissive: color, emissiveIntensity: 0.05, roughness: 0.3 }),
                        -0.9 + index * 0.9, 1.85, 1.1);
  });
  for (const [x, z, turn] of [[-2.4, -1.1, 0], [2.3, -0.9, 0.12]]) {
    const pew = new THREE.Group();
    pew.add(at(box(1.8, 0.1, 0.5, "#7a5236"), 0, 0.45, 0), at(box(1.8, 0.5, 0.08, "#7a5236"), 0, 0.72, -0.22));
    add("decision", pew, x, 0, z, turn);
  }
  add("decision", plant(1.2), 3.0, 0, 2.3);
  const lampLight = new THREE.PointLight(0xffffff, 0, 7, 1.6);
  lampLight.position.set(LAYOUT.decision[0], 2.4, LAYOUT.decision[1] + 1.0);
  scene.add(lampLight);
  const alarm = new THREE.SpotLight(0xff3b30, 0, 14, Math.PI / 7, 0.5, 1.2);
  alarm.position.set(LAYOUT.decision[0], 3.4, LAYOUT.decision[1]);
  scene.add(alarm, alarm.target);

  // Reviewer (open plan): a desk with two screens, an inbox tray, a printer and a rug.
  add("reviewer", rug(3.6, 3.0, "#3a4656"), 0, 0.06, 0.3);
  add("reviewer", desk(2, 0.8, "#e8e1d4"), 0, 0, 0.4, Math.PI);
  add("reviewer", monitor("#e8f4ff", 0.7), -0.45, 0.92, 0.6, Math.PI);
  add("reviewer", monitor("#ffd08a", 0.7), 0.45, 0.92, 0.6, Math.PI - 0.15);
  add("reviewer", printer(), 1.8, 0, 1.3, -0.3);
  add("reviewer", plant(1.2), -1.9, 0, 1.5);
  const inbox = add("reviewer", new THREE.Group(), 0.9, 0.8, 0.25);

  // Pantry (open plan): coffee bar, sofa, a round table with stools.
  add("pantry", coffeeBar(), 0.3, 0, 1.6, Math.PI);
  add("pantry", sofa("#7a5c8f"), -1.7, 0, -0.9, 0.2);
  add("pantry", mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.05, 20), "#e8e1d4"), 1.6, 0.72, -0.4);
  add("pantry", mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.7, 8), "#26384a"), 1.6, 0.36, -0.4);
  for (const angle of [0.4, 2.3, 4.1]) add("pantry", mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.45, 12), "#c99a5b"), 1.6 + Math.cos(angle) * 0.8, 0.22, -0.4 + Math.sin(angle) * 0.8);
  add("pantry", plant(1.5), 2.7, 0, -1.8);

  // Room labels and DOM screens (textContent only) placed over the canvas.
  const screensDom = {};
  for (const [id, room] of Object.entries(rooms)) {
    const label = document.createElement("div");
    label.className = "room-label" + (room.info.locked ? " locked" : "") + (WINGS[id] ? " wing" : "");
    label.style.setProperty("--accent", ACCENT[id]);
    const title = document.createElement("strong");
    title.textContent = room.info.name + (room.info.locked ? " 🔒" : "");
    const step = document.createElement("small");
    step.textContent = room.info.step;
    label.append(title, step);
    labelLayer.append(label);
    room.label = label;
    const screen = document.createElement("div");
    screen.className = "room-screen";
    screen.style.setProperty("--accent", ACCENT[id]);
    screen.hidden = true;
    overlayLayer.append(screen);
    screensDom[id] = screen;
  }
  const screenAt = { code: [AREAS.code.at[0] - 0.6, 2.6, AREAS.code.at[1] - 1.6],
                     evidence: [AREAS.evidence.at[0], 1.7, AREAS.evidence.at[1] + 1.0], reception: [AREAS.reception.at[0] + 0.4, 2.5, AREAS.reception.at[1] + 0.5],
                     server: [AREAS.server.at[0] - 0.6, 3.1, AREAS.server.at[1] - 1.8], reviewer: [AREAS.reviewer.at[0], 2.2, AREAS.reviewer.at[1] + 0.6] };

  const overlay = (className, text, accent) => {
    const tag = document.createElement("div");
    tag.className = className;
    tag.style.setProperty("--accent", accent);
    tag.textContent = text;
    overlayLayer.append(tag);
    return tag;
  };

  // --- staff: robots for deterministic code, people for the human roles around it ----------------
  const ROBOTS = {
    reception: { name: "read_manifest", at: inside("reception", -1.2, -0.8), face: 0.2, gear: { clipboard: true } },
    code: { name: "read_file · extract_indicators · deobfuscate", at: inside("code", 0.6, -0.4), face: -0.3, gear: {} },
    intel: { name: "OSV · npm Registry (chạy trước)", at: inside("intel", 1.0, -0.5), face: -0.5, gear: { book: true } },
    lab: { name: "Sandbox (khóa đến W5-6)", at: inside("lab", -1.6, -1.4), face: Math.PI + 0.3, gear: { shield: true } },
    evidence: { name: "Kiểm chứng file:dòng", at: inside("evidence", -0.2, 1.6), face: Math.PI, gear: { magnifier: true } },
    decision: { name: "Luật R1–R8 (thẩm phán)", at: inside("decision", 0, 2.15), face: Math.PI, lift: 0.25, gear: { gavel: true, robe: "#1a1f26" } },
  };
  const STAFF = {
    courier: { role: "📦 Giao hàng npm", at: inside("gate", -1.6, 0.9), face: Math.PI / 2,
               look: { shirt: "#c99a5b", pants: "#5b4636", hair: "cap", capColor: "#8a5a2b", hold: "none", skin: "#d9a77c" } },
    guard: { role: "🛡️ Bảo vệ cổng", at: inside("gate", 0.2, 1.2), face: 0.4,
             look: { shirt: "#22344a", pants: "#1a1f26", hair: "cap", capColor: "#1a1f26", vest: "#30475f", hold: "none", skin: "#b97f55" } },
    tech: { role: "🧑‍💻 Kỹ thuật GPU", at: inside("server", 2.5, -0.4), face: -Math.PI / 2,
            look: { shirt: "#3a2b4f", hair: "short", hairColor: "#5b3a24", glasses: true, hold: "tablet", badge: "#ff7ad9" } },
    reviewer: { role: "👁 Người xem (duyệt tay)", at: inside("reviewer", 0, 1.25), face: Math.PI,
                look: { shirt: "#f4f8f5", tie: "#2b7de9", hair: "short", hairColor: "#1a1f26", glasses: true, hold: "clipboard", skin: "#f5d3b3" } },
    po: { role: "⭐ PO (trưởng nhóm)", at: inside("pantry", -0.3, -0.5), face: -0.6,
          look: { shirt: "#61e8c2", pants: "#26384a", hair: "long", hairColor: "#2b2420", hold: "cup", badge: "#ffd08a" } },
    barista: { role: "☕ Barista", at: inside("pantry", 0.5, 2.15), face: Math.PI,
               look: { shirt: "#e8e1d4", apron: "#5b4636", hair: "bun", hairColor: "#8a5a2b", hold: "none", skin: "#d9a77c" } },
    janitor: { role: "🧹 Lao công", at: [-16, HALL_Z + 1.45], face: Math.PI / 2,
               look: { shirt: "#2f7d55", pants: "#26384a", hair: "cap", capColor: "#2f7d55", hold: "mop", vest: "#3f9a6b", skin: "#8d5a3b" } },
  };

  const robots = {};
  for (const [room, spec] of Object.entries(ROBOTS)) {
    const body = robotMesh(ACCENT[room], spec.gear);
    body.robot.position.set(spec.at[0], spec.lift || 0, spec.at[1]);
    body.robot.rotation.y = spec.face;
    scene.add(body.robot);
    robots[room] = { ...body, tag: overlay("robot-tag", `🤖 ${spec.name}`, ACCENT[room]), lift: spec.lift || 0, action: null, actionAge: 0, slammed: false };
  }
  const staff = {};
  for (const [id, spec] of Object.entries(STAFF)) {
    const body = personMesh(spec.look);
    body.person.position.set(spec.at[0], 0, spec.at[1]);
    body.person.rotation.y = spec.face;
    scene.add(body.person);
    staff[id] = { ...body, tag: overlay("npc-tag", spec.role, "#b8cbd0"), action: null, actionAge: 0 };
  }
  // The courier carries a parcel; the janitor pushes a cart along the hallway.
  staff.courier.person.add(at(box(0.5, 0.36, 0.4, "#c99a5b"), 0, 1.0, 0.35));
  const cart = new THREE.Group();
  cart.add(at(box(0.7, 0.5, 0.45, "#3f9a6b"), 0, 0.45, 0), at(box(0.62, 0.3, 0.38, "#7cc4ff"), 0, 0.85, 0));
  for (const x of [-0.28, 0.28]) cart.add(at(mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.06, 10), "#1a1f26"), x, 0.08, 0.2).rotateX(Math.PI / 2));
  cart.position.set(-15.15, 0, HALL_Z + 1.45);
  scene.add(cart);

  let animating = false; // idle motion only while a replay plays: a paused office leaves the GPU idle
  let idleTime = 0;
  let thinkingColors = [];
  let gateAction = null;
  let gateAngle = 0;
  let dirty = true;
  const speed = { value: 1 };
  const projected = new THREE.Vector3();
  const effects = [];
  const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  let shake = 0;

  function robotReact(room, action) {
    const robot = robots[room];
    if (!robot) return;
    Object.assign(robot, { action, actionAge: 0, slammed: false });
    dirty = true;
  }

  function staffReact(id, action) {
    const person = staff[id];
    if (!person) return;
    Object.assign(person, { action, actionAge: 0 });
    dirty = true;
  }

  function robotHead(room) { return (robots[room] || robots.decision).head.getWorldPosition(new THREE.Vector3()); }
  function staffHead(id) { return staff[id].head.getWorldPosition(new THREE.Vector3()); }

  function setThinking(colorList) {
    if (colorList.join(",") === thinkingColors.join(",")) return;
    thinkingColors = colorList;
    gpuGlow.intensity = colorList.length ? 4 + colorList.length * 2 : 0;
    if (colorList.length) gpuGlow.color.set(colorList[0]);
    else for (const led of leds) { led.material.emissive.set(ACCENT.server); led.material.emissiveIntensity = 0.4; }
    dirty = true;
  }

  function setGate(action) {
    if (action === gateAction) return;
    gateAction = action;
    dirty = true;
  }

  // Data packets: a glowing orb with a short trail on an arc; input flows to a robot, output comes back.
  const packetGeometry = new THREE.SphereGeometry(0.16, 14, 10);
  function sendPacket(from, to, color, onArrive, label) {
    const tint = new THREE.Color(color);
    const orb = new THREE.Mesh(packetGeometry, new THREE.MeshBasicMaterial({ color: tint }));
    orb.add(new THREE.PointLight(tint, 3, 3, 2));
    const trail = Array.from({ length: 6 }, (_, index) => {
      const dot = new THREE.Mesh(packetGeometry, new THREE.MeshBasicMaterial({ color: tint, transparent: true, opacity: 0.5 - index * 0.07 }));
      dot.scale.setScalar(0.75 - index * 0.1);
      dot.position.copy(from);
      scene.add(dot);
      return dot;
    });
    orb.position.copy(from);
    scene.add(orb);
    const chip = label ? overlay("packet-chip", label, color) : null;
    const middle = from.clone().lerp(to, 0.5);
    middle.y += 1.4 + from.distanceTo(to) * 0.12;
    const curve = new THREE.QuadraticBezierCurve3(from.clone(), middle, to.clone());
    const history = [];
    effects.push({ life: Math.max(0.4, (0.7 + from.distanceTo(to) * 0.03) / speed.value), age: 0, step() {
      const point = curve.getPoint(ease(Math.min(1, this.age / this.life)));
      orb.position.copy(point);
      history.unshift(point.clone());
      trail.forEach((dot, index) => dot.position.copy(history[Math.min(history.length - 1, (index + 1) * 2)]));
      if (chip) place(chip, [point.x, point.y + 0.35, point.z]);
    }, end() {
      scene.remove(orb, ...trail);
      orb.material.dispose();
      trail.forEach((dot) => dot.material.dispose());
      chip?.remove();
      onArrive?.();
    } });
    dirty = true;
  }

  // --- workers (AI models) ---------------------------------------------------------------------
  const workers = new Map();
  let laneCount = 1;
  const HAIR = ["short", "bun", "long"];

  function laneOffset(lane) { return HALL_Z + (lane - (laneCount - 1) / 2) * 0.85; }

  function spotFor(id, lane) {
    const offset = laneOffset(lane) - HALL_Z;
    if (id === "hallway") return new THREE.Vector3(offset * 2, 0, HALL_Z + offset);
    const [x, z] = AREAS[id].at;
    const away = Math.sign(z - HALL_Z);
    return new THREE.Vector3(x + offset * 1.8, 0, z - away * (AREAS[id].size[1] / 2 - 1.1));
  }

  function addWorker({ id, name, color, lane }) {
    const body = personMesh({ shirt: color, hair: HAIR[lane % HAIR.length], hairColor: ["#2b2420", "#5b3a24", "#1a1f26"][lane % 3],
                              glasses: lane === 0, badge: "#f4f8f5", skin: ["#f2c9a0", "#d9a77c", "#f5d3b3"][lane % 3] });
    const halo = mesh(new THREE.RingGeometry(0.42, 0.58, 28), color, { emissive: color, emissiveIntensity: 0.9, shadow: false });
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.06;
    body.person.add(halo);
    const thought = new THREE.Group();
    for (let index = 0; index < 8; index += 1) {
      const angle = index / 8 * Math.PI * 2;
      thought.add(at(mesh(new THREE.SphereGeometry(0.06 + index * 0.008, 8, 6), color, { emissive: color, emissiveIntensity: 1.4, shadow: false }),
                     Math.cos(angle) * 0.42, 0, Math.sin(angle) * 0.42));
    }
    thought.position.y = 2.2;
    thought.visible = false;
    body.person.add(thought);
    body.person.position.copy(spotFor("reception", lane));
    scene.add(body.person);
    const tag = document.createElement("div");
    tag.className = "worker-tag";
    tag.style.setProperty("--worker", color);
    const stamp = document.createElement("span");
    stamp.className = "worker-stamp";
    stamp.hidden = true;
    const bubble = document.createElement("span");
    bubble.className = "worker-bubble";
    bubble.hidden = true;
    const label = document.createElement("strong");
    label.textContent = `🧑 ${name}`;
    tag.append(stamp, bubble, label);
    overlayLayer.append(tag);
    const worker = { ...body, thought, tag, bubble, stamp, lane, path: [], room: "reception", phase: 0 };
    workers.set(id, worker);
    dirty = true;
    return {
      walkTo(room, instant = false) {
        const spot = spotFor(room, lane);
        if (instant) {
          worker.path = [];
          worker.person.position.copy(spot);
        } else if (room !== worker.room) {
          const here = worker.person.position;
          const corridor = laneOffset(lane);
          worker.path = [];
          if (Math.abs(here.z - corridor) > 0.3) worker.path.push(new THREE.Vector3(here.x, 0, corridor));
          worker.path.push(new THREE.Vector3(spot.x, 0, corridor), spot);
        }
        worker.room = room;
        refreshRooms();
      },
      say(text, thinking = false) {
        worker.bubble.textContent = text;
        worker.bubble.hidden = !text;
        worker.bubble.classList.toggle("thinking", thinking);
        dirty = true;
      },
      stamp(action, text, animate = false) {
        worker.stamp.hidden = !action;
        worker.stamp.textContent = text || "";
        worker.stamp.dataset.action = action || "";
        worker.stamp.classList.remove("slam");
        if (action && animate) { void worker.stamp.offsetWidth; worker.stamp.classList.add("slam"); }
        dirty = true;
      },
      think(on) { if (worker.thought.visible !== on) { worker.thought.visible = on; dirty = true; } },
      head: () => worker.person.position.clone().add(new THREE.Vector3(0, 1.7, 0)),
    };
  }

  function clearWorkers(count = 1) {
    for (const worker of workers.values()) {
      scene.remove(worker.person);
      worker.tag.remove();
    }
    workers.clear();
    laneCount = count;
    refreshRooms();
  }

  function refreshRooms() {
    const occupied = new Set([...workers.values()].map((worker) => worker.room));
    for (const [id, room] of Object.entries(rooms)) {
      const on = occupied.has(id);
      room.floor.material.color.copy(on ? room.base.clone().lerp(room.accent, 0.35) : room.base);
      room.label.classList.toggle("active", on);
    }
    for (const screen of screens) screen.material.emissiveIntensity = occupied.has("code") ? 1 : 0.35;
    dirty = true;
  }

  function setScreen(room, text) {
    const screen = screensDom[room];
    if (!screen || (screen.textContent === (text || "") && screen.hidden === !text)) return;
    screen.textContent = text || "";
    screen.hidden = !text;
    dirty = true;
  }

  let evidenceKey = "";
  function setEvidence(checks) {
    const key = JSON.stringify((checks || []).map((check) => check.exists));
    if (key === evidenceKey) return;
    evidenceKey = key;
    papers.clear();
    (checks || []).slice(0, 8).forEach((check, index) => {
      const color = check.exists ? "#61e8c2" : "#ff8e83";
      const sheet = box(0.34, 0.02, 0.46, "#f4f1ea", { shadow: false });
      sheet.add(at(box(0.3, 0.025, 0.06, color, { emissive: color, emissiveIntensity: 0.6, shadow: false }), 0, 0.005, -0.17));
      sheet.position.set(-1.4 + index * 0.4, 0, (index % 2) * 0.1);
      sheet.rotation.y = (index % 3 - 1) * 0.12;
      papers.add(sheet);
    });
    dirty = true;
  }

  let inboxCount = -1;
  function setInbox(count) {
    if (count === inboxCount) return;
    inboxCount = count;
    inbox.clear();
    for (let index = 0; index < Math.min(count, 6); index += 1) inbox.add(at(box(0.36, 0.04, 0.46, index % 2 ? "#ffd08a" : "#f4f1ea"), 0, index * 0.05, 0));
    dirty = true;
  }

  let lampKey = "";
  function setLamps(actions) {
    const key = actions.join(",");
    if (key === lampKey) return;
    lampKey = key;
    const lit = new Set(actions.filter(Boolean));
    for (const [name, bulb] of Object.entries(lamps)) bulb.material.emissiveIntensity = lit.has(name) ? 2.4 : 0.05;
    const main = actions.find(Boolean);
    lampLight.color.set(main ? ACTION_COLORS[main] : "#ffffff");
    lampLight.intensity = main ? 6 : 0;
    dirty = true;
  }

  // --- effects: confetti for approve, alarm and shake for deny, amber pulse for review ----------
  function celebrate(action) {
    if (reducedMotion()) return;
    const [x, z] = LAYOUT.decision;
    if (action === "approve") {
      const count = 180;
      const positions = new Float32Array(count * 3);
      const tints = new Float32Array(count * 3);
      const velocities = [];
      const palette = ["#61e8c2", "#7cc4ff", "#ffd08a", "#f4f8f5", "#ff7ad9"].map((hex) => new THREE.Color(hex));
      for (let index = 0; index < count; index += 1) {
        positions.set([x, 1.8, z + 0.8], index * 3);
        velocities.push(new THREE.Vector3((Math.random() - 0.5) * 5, 3 + Math.random() * 4, (Math.random() - 0.5) * 5));
        palette[index % palette.length].toArray(tints, index * 3);
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute("color", new THREE.BufferAttribute(tints, 3));
      const points = new THREE.Points(geometry, new THREE.PointsMaterial({ size: 0.16, vertexColors: true, transparent: true }));
      scene.add(points);
      effects.push({ life: 2.6, age: 0, step(delta) {
        const array = geometry.attributes.position.array;
        velocities.forEach((velocity, index) => {
          velocity.y -= 9.8 * delta;
          array[index * 3] += velocity.x * delta;
          array[index * 3 + 1] = Math.max(0.05, array[index * 3 + 1] + velocity.y * delta);
          array[index * 3 + 2] += velocity.z * delta;
        });
        geometry.attributes.position.needsUpdate = true;
        points.material.opacity = 1 - ease(this.age / this.life);
      }, end() { scene.remove(points); geometry.dispose(); } });
    } else if (action === "deny") {
      effects.push({ life: 3, age: 0, step() {
        const sweep = this.age * 5;
        alarm.intensity = 60 * (0.6 + 0.4 * Math.sin(this.age * 18));
        alarm.target.position.set(x + Math.cos(sweep) * 3, 0, z + Math.sin(sweep) * 2);
        shake = Math.max(shake, this.age < 0.45 ? (0.45 - this.age) * 0.5 : 0);
      }, end() { alarm.intensity = 0; shake = 0; } });
    } else if (action === "review") {
      effects.push({ life: 2.4, age: 0, step() {
        lamps.review.material.emissiveIntensity = 1.2 + Math.abs(Math.sin(this.age * 7)) * 2.5;
      }, end() { lamps.review.material.emissiveIntensity = 2.4; } });
    }
    dirty = true;
  }

  // --- camera: fitted overview, or a director that follows the workers --------------------------
  let fitDistance = 30;
  const director = { on: false, target: new THREE.Vector3(), distance: 30 };

  const fitTarget = new THREE.Vector3((BOUNDS.minX + BOUNDS.maxX) / 2, 0, (BOUNDS.minZ + BOUNDS.maxZ) / 2 + 0.6);
  const corners = [];
  for (const x of [BOUNDS.minX, BOUNDS.maxX]) for (const y of [0, 2.4]) for (const z of [BOUNDS.minZ + 1.2, BOUNDS.maxZ]) corners.push(new THREE.Vector3(x, y, z));

  function fit() {
    const { clientWidth: width, clientHeight: height } = canvas.parentElement;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    // Find the closest distance at which every corner of the building stays on screen (binary search).
    const probe = camera.clone();
    let near = 4;
    let far = 200;
    for (let step = 0; step < 24; step += 1) {
      const distance = (near + far) / 2;
      probe.position.copy(VIEW_DIRECTION).multiplyScalar(distance).add(fitTarget);
      probe.lookAt(fitTarget);
      probe.updateMatrixWorld();
      const fits = corners.every((corner) => {
        const point = corner.clone().project(probe);
        return Math.abs(point.x) <= 0.97 && Math.abs(point.y) <= 0.95;
      });
      if (fits) far = distance; else near = distance;
    }
    fitDistance = far;
    controls.maxDistance = fitDistance * 1.5;
    controls.minDistance = fitDistance * 0.22;
    dirty = true;
  }

  function resetView() {
    controls.target.copy(fitTarget);
    camera.position.copy(VIEW_DIRECTION).multiplyScalar(fitDistance).add(controls.target);
    camera.lookAt(controls.target);
    dirty = true;
  }

  function setDirector(on) {
    director.on = on;
    if (!on) resetView();
    dirty = true;
  }

  function focus(room, closeness = 0.55) {
    if (!director.on) return;
    if (!room) { director.target.set(0, 0, 0); director.distance = fitDistance * closeness; return; }  // follow everyone
    const [x, z] = LAYOUT[room];
    director.target.set(x, 0.6, HALL_Z + (z - HALL_Z) * 0.75);
    director.distance = fitDistance * closeness;
  }

  function followWorkers() {
    if (!director.on || !workers.size) return false;
    const center = new THREE.Vector3();
    for (const worker of workers.values()) center.add(worker.person.position);
    center.divideScalar(workers.size);
    const goal = director.target.lengthSq() ? director.target : center;
    const before = controls.target.clone();
    controls.target.lerp(goal, 0.06);
    const direction = camera.position.clone().sub(before).normalize();
    const distance = THREE.MathUtils.lerp(camera.position.distanceTo(before), director.distance, 0.05);
    camera.position.copy(controls.target).addScaledVector(direction, distance);
    return before.distanceTo(controls.target) > 0.002 || Math.abs(distance - director.distance) > 0.02;
  }

  function place(element, point) {
    projected.set(...point).project(camera);
    const { clientWidth: width, clientHeight: height } = canvas;
    element.style.transform = `translate(-50%, -100%) translate(${(projected.x + 1) / 2 * width}px, ${(1 - projected.y) / 2 * height}px)`;
  }

  function walkCycle(body, phase, amount) {
    const swing = Math.sin(phase) * amount;
    body.legs[0].rotation.x = swing;
    body.legs[1].rotation.x = -swing;
    body.arms[0].rotation.x = -swing * 0.8;
    body.arms[1].rotation.x = swing * 0.8;
  }

  // --- frame loop: render only while something moves, so an idle office costs the GPU nothing -----
  const stats = { frames: 0, fps: 0, since: performance.now(), continuous: false };
  const clock = new THREE.Clock();
  function frame() {
    const delta = Math.min(clock.getDelta(), 0.5);
    const reduced = reducedMotion();
    for (const worker of workers.values()) {
      if (worker.path.length) {
        const target = worker.path[0];
        const step = reduced ? Infinity : 5.5 * delta * speed.value;
        const offset = target.clone().sub(worker.person.position);
        if (offset.length() <= step) {
          worker.person.position.copy(target);
          worker.path.shift();
        } else {
          worker.person.position.add(offset.clone().setLength(step));
          worker.person.rotation.y = Math.atan2(offset.x, offset.z);
        }
        worker.phase += delta * 11 * speed.value;
        dirty = true;
      } else if (worker.phase) {
        worker.phase = 0;
        worker.person.rotation.y = worker.room === "hallway" ? 0 : (LAYOUT[worker.room][1] > 0 ? 0 : Math.PI);
        dirty = true;
      }
      walkCycle(worker, worker.phase, reduced || !worker.path.length ? 0 : 0.55);
    }

    if (animating && !reduced) {
      idleTime += delta;
      for (const [room, robot] of Object.entries(robots)) {
        if (!robot.action) robot.head.rotation.y = Math.sin(idleTime * 0.9 + room.length) * 0.25;
        robot.bulb.material.emissiveIntensity = 0.6 + Math.abs(Math.sin(idleTime * 3 + room.length)) * 1.6;
      }
      for (const worker of workers.values()) {
        if (worker.thought.visible) {
          worker.thought.rotation.y += delta * 3.2;
          worker.thought.position.y = 2.2 + Math.sin(idleTime * 4) * 0.06;
        }
      }
      // Staff idle: heads turn, the barista wipes, the technician taps the tablet, the janitor patrols.
      for (const [id, person] of Object.entries(staff)) {
        if (!person.action) person.head.rotation.y = Math.sin(idleTime * 0.7 + id.length * 1.3) * 0.35;
      }
      staff.barista.arms[1].rotation.x = -0.9 + Math.sin(idleTime * 5) * 0.35;
      if (!staff.tech.action) staff.tech.arms[1].rotation.x = thinkingColors.length ? -1 + Math.sin(idleTime * 16) * 0.2 : -0.7;
      const patrol = (idleTime * 0.9) % 60;
      const forward = patrol < 30;
      const x = forward ? -16.5 + patrol : 13.5 - (patrol - 30);
      staff.janitor.person.position.set(x, 0, HALL_Z + 1.45);
      staff.janitor.person.rotation.y = forward ? Math.PI / 2 : -Math.PI / 2;
      walkCycle(staff.janitor, idleTime * 7, 0.35);
      cart.position.set(x + (forward ? 0.85 : -0.85), 0, HALL_Z + 1.45);
      // GPU racks: lights flicker in the colours of the models that are thinking right now.
      if (thinkingColors.length) {
        leds.forEach((led, index) => {
          const on = Math.sin(idleTime * (9 + (index % 7)) + index * 1.7) > 0.1;
          led.material.emissive.set(thinkingColors[index % thinkingColors.length]);
          led.material.emissiveIntensity = on ? 2.4 : 0.2;
        });
      }
      dirty = true;
    }

    // Robots react to work: receive, work, ok (nod, green), bad (shake, red), gavel.
    for (const robot of Object.values(robots)) {
      if (!robot.action) continue;
      robot.actionAge += delta * Math.max(1, speed.value);
      const age = robot.actionAge;
      const pulse = Math.max(0, 1 - age / 0.9);
      const color = robot.action === "bad" ? "#ff5a4f" : robot.action === "ok" ? "#61e8c2" : null;
      robot.visor.material.emissive.copy(color ? new THREE.Color(color) : robot.accent);
      robot.visor.material.emissiveIntensity = 1.2 + pulse * 3;
      if (robot.action === "work") robot.arms.forEach((arm, index) => { arm.rotation.x = -Math.abs(Math.sin(age * 14 + index * 1.7)) * 0.9 * pulse; });
      if (robot.action === "ok") robot.head.rotation.x = Math.sin(age * 12) * 0.3 * pulse;
      if (robot.action === "bad") robot.head.rotation.y = Math.sin(age * 16) * 0.5 * pulse;
      if (robot.action === "receive") robot.robot.position.y = robot.lift + Math.abs(Math.sin(age * 8)) * 0.15 * pulse;
      if (robot.action === "gavel") {
        robot.arms[1].rotation.x = age < 0.35 ? -2.4 * (age / 0.35) : Math.min(0.3, -2.4 + (age - 0.35) / 0.1 * 2.7);
        if (age >= 0.45 && !robot.slammed) { robot.slammed = true; shake = Math.max(shake, 0.2); }
      }
      if (age >= 0.95) {
        robot.action = null;
        robot.visor.material.emissive.copy(robot.accent);
        robot.visor.material.emissiveIntensity = 1.2;
        robot.head.rotation.x = 0;
        robot.robot.position.y = robot.lift;
        robot.arms.forEach((arm) => { arm.rotation.x = 0; });
        if (robot.slammed && !effects.length) shake = 0;
      }
      dirty = true;
    }

    // Staff reactions: raise (reviewer takes a case), thumbs (PO), handover (courier), salute (guard).
    for (const person of Object.values(staff)) {
      if (!person.action) continue;
      person.actionAge += delta * Math.max(1, speed.value);
      const age = person.actionAge;
      const up = Math.sin(Math.min(1, age / 1.2) * Math.PI);
      if (person.action === "raise" || person.action === "thumbs") person.arms[1].rotation.x = -2.6 * up;
      if (person.action === "thumbs") person.person.position.y = Math.abs(Math.sin(age * 9)) * 0.12 * up;
      if (person.action === "handover") person.arms.forEach((arm) => { arm.rotation.x = -1.3 * up; });
      if (person.action === "salute") { person.arms[1].rotation.x = -2.2 * up; person.arms[1].rotation.z = 0.6 * up; }
      if (age >= 1.25) {
        person.action = null;
        person.arms.forEach((arm) => { arm.rotation.set(0, 0, 0); });
        person.person.position.y = 0;
      }
      dirty = true;
    }

    // Barrier: up and green on approve, down and red on deny, down and amber on review.
    const targetAngle = gateAction === "approve" ? 1.35 : 0;
    if (Math.abs(gateAngle - targetAngle) > 0.005) {
      gateAngle += (targetAngle - gateAngle) * Math.min(1, delta * 4);
      dirty = true;
    }
    gate.userData.arm.rotation.z = gateAngle;
    const gateColor = gateAction ? ACTION_COLORS[gateAction] : "#ffd08a";
    gate.userData.lamp.material.emissive.set(gateColor);
    gate.userData.lamp.material.color.set(gateColor);
    gate.userData.lamp.material.emissiveIntensity = gateAction === "review" && animating ? 0.6 + Math.abs(Math.sin(idleTime * 6)) * 2 : gateAction ? 2.2 : 0.4;

    if (!reduced && [...workers.values()].some((worker) => worker.room === "intel")) {
      globe.rotation.y += delta * 0.8;
      dirty = true;
    }
    for (let index = effects.length - 1; index >= 0; index -= 1) {
      const effect = effects[index];
      effect.age += delta;
      effect.step(delta);
      if (effect.age >= effect.life) {
        effect.end();
        effects.splice(index, 1);
      }
      dirty = true;
    }
    if (stats.continuous) {
      controls.autoRotate = true;
      dirty = true;
    }
    if (followWorkers()) dirty = true;
    if (controls.update(delta)) dirty = true;
    if (dirty && !document.hidden) {
      const rest = camera.position.clone();
      if (shake) camera.position.add(new THREE.Vector3((Math.random() - 0.5) * shake, (Math.random() - 0.5) * shake, 0));
      renderer.render(scene, camera);
      camera.position.copy(rest);
      for (const room of Object.values(rooms)) place(room.label, room.labelAt);
      for (const [id, point] of Object.entries(screenAt)) place(screensDom[id], point);
      for (const robot of Object.values(robots)) {
        const head = robot.head.getWorldPosition(new THREE.Vector3());
        place(robot.tag, [head.x, head.y + 0.75, head.z]);
      }
      for (const person of Object.values(staff)) {
        const { x, y, z } = person.person.position;
        place(person.tag, [x, y + 2.25, z]);
      }
      for (const worker of workers.values()) {
        const { x, z } = worker.person.position;
        // Tags of several workers are stacked by lane so stamps and bubbles never cover each other.
        place(worker.tag, [x, 2.3 + worker.lane * 0.95, z]);
      }
      stats.frames += 1;
      dirty = false;
    }
    const now = performance.now();
    if (now - stats.since >= 1000) {
      stats.fps = Math.round(stats.frames * 1000 / (now - stats.since));
      stats.frames = 0;
      stats.since = now;
    }
    requestAnimationFrame(frame);
  }
  controls.addEventListener("change", () => { dirty = true; });
  new ResizeObserver(() => { fit(); if (!director.on) resetView(); }).observe(canvas.parentElement);
  fit();
  resetView();
  setLamps([]);
  requestAnimationFrame(frame);
  return {
    addWorker, clearWorkers, setScreen, setEvidence, setLamps, setInbox, setThinking, setGate, celebrate,
    setDirector, focus, resetView, robotReact, robotHead, staffReact, staffHead, sendPacket,
    setAnimating: (on) => { animating = on; dirty = true; },
    speed, stats,
    info: () => ({ fps: stats.fps, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
                   pixelRatio: renderer.getPixelRatio(), workers: workers.size, fitDistance: +fitDistance.toFixed(2),
                   camera: camera.position.toArray().map((value) => +value.toFixed(2)), target: controls.target.toArray().map((value) => +value.toFixed(2)),
                   positions: [...workers.values()].map((worker) => [worker.room, +worker.person.position.x.toFixed(2),
                                                                      +worker.person.position.z.toFixed(2), worker.path.length]) }),
  };
}
