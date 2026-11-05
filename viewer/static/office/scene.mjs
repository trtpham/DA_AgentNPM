// Low-poly office drawn with Three.js. Rendering only; trace logic lives in events.mjs and main.mjs.
// Every shape is built from primitives here: no model files, no textures fetched from anywhere.
import * as THREE from "../vendor/three.module.min.js";
import { OrbitControls } from "../vendor/OrbitControls.js";
import { ROOMS } from "./events.mjs";

// U-shaped plan that follows the agent's four steps; the hallway runs along z = 0.
const LAYOUT = {
  reception: [-7, -4.6], code: [0, -4.6], intel: [7, -4.6],
  lab: [7, 4.6], evidence: [0, 4.6], decision: [-7, 4.6],
  hallway: [0, 0],
};
const ROOM_SIZE = [6, 4.6];
const VIEW_DIRECTION = new THREE.Vector3(-0.35, 22, 16).normalize();
export const ACCENT = {
  reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8",
  evidence: "#ffd08a", decision: "#ff8e83", hallway: "#6f8597",
};
const ACTION_COLORS = { approve: "#61e8c2", review: "#ffd08a", deny: "#ff6b5e" };

function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(value || fallback);
}

function mesh(geometry, color, options = {}) {
  const material = new THREE.MeshStandardMaterial({
    color, roughness: options.roughness ?? 0.8, metalness: options.metalness ?? 0,
    transparent: (options.opacity ?? 1) < 1, opacity: options.opacity ?? 1,
    emissive: options.emissive ?? 0x000000, emissiveIntensity: options.emissiveIntensity ?? 1,
  });
  const item = new THREE.Mesh(geometry, material);
  item.castShadow = options.shadow ?? true;
  item.receiveShadow = true;
  return item;
}

const box = (w, h, d, color, options) => mesh(new THREE.BoxGeometry(w, h, d), color, options);
const at = (item, x, y, z) => { item.position.set(x, y, z); return item; };
const ease = (value) => 1 - (1 - value) ** 3;

// --- props -------------------------------------------------------------------------------------
function plant() {
  const group = new THREE.Group();
  group.add(at(mesh(new THREE.CylinderGeometry(0.22, 0.17, 0.35, 10), "#9a6b4f"), 0, 0.18, 0));
  group.add(at(mesh(new THREE.IcosahedronGeometry(0.38, 0), "#3f9a6b", { roughness: 1 }), 0, 0.62, 0));
  group.add(at(mesh(new THREE.IcosahedronGeometry(0.26, 0), "#57b884", { roughness: 1 }), 0.15, 0.9, 0.05));
  return group;
}

function chair(color) {
  const group = new THREE.Group();
  group.add(at(box(0.5, 0.08, 0.5, color), 0, 0.45, 0));
  group.add(at(box(0.5, 0.5, 0.08, color), 0, 0.72, 0.22));
  group.add(at(mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.42, 6), "#26384a"), 0, 0.21, 0));
  return group;
}

function workstation(accent) {
  const group = new THREE.Group();
  group.add(at(box(1.6, 0.08, 0.8, "#c9b48f"), 0, 0.74, 0));
  for (const x of [-0.72, 0.72]) group.add(at(box(0.08, 0.72, 0.7, "#26384a"), x, 0.36, 0));
  const screen = box(0.9, 0.55, 0.05, "#0d1622", { emissive: accent, emissiveIntensity: 0.35 });
  group.add(at(screen, 0, 1.12, -0.22));
  group.add(at(box(0.08, 0.3, 0.08, "#26384a"), 0, 0.9, -0.22));
  group.add(at(box(0.5, 0.03, 0.18, "#26384a"), 0, 0.8, 0.1));
  const seat = chair("#26384a");
  seat.position.set(0, 0, 0.75);
  seat.rotation.y = Math.PI;
  group.add(seat);
  group.userData.screen = screen;
  return group;
}

function shelf(accent) {
  const group = new THREE.Group();
  group.add(at(box(1.8, 1.9, 0.45, "#5b4636"), 0, 0.95, 0));
  const books = ["#7cc4ff", "#ffd08a", "#ff8e83", "#61e8c2", accent, "#e8e1d4"];
  for (let row = 0; row < 3; row += 1) {
    let x = -0.75;
    for (let index = 0; x < 0.75; index += 1) {
      const width = 0.1 + ((index * 7 + row * 3) % 4) * 0.025;
      const height = 0.36 + ((index + row) % 3) * 0.05;
      group.add(at(box(width, height, 0.3, books[(index + row) % books.length], { shadow: false }),
                   x + width / 2, 0.22 + row * 0.6 + height / 2, 0.08));
      x += width + 0.015;
    }
  }
  return group;
}

function roomShell(id, colors) {
  const info = ROOMS[id];
  const [x, z] = LAYOUT[id];
  const away = Math.sign(z); // the back wall is on the side away from the hallway
  const accent = new THREE.Color(ACCENT[id]);
  const group = new THREE.Group();
  group.position.set(x, 0, z);
  const floorColor = info.locked ? "#2a3644" : colors.surface2.clone().lerp(accent, 0.12);
  const floor = box(ROOM_SIZE[0], 0.1, ROOM_SIZE[1], floorColor, { shadow: false });
  group.add(floor);
  // Rooms whose back wall faces the camera get a low cut-away wall, as in isometric games.
  const wallHeight = away > 0 ? 0.4 : 1.6;
  group.add(at(box(ROOM_SIZE[0], wallHeight, 0.16, "#22344a"), 0, wallHeight / 2, away * ROOM_SIZE[1] / 2));
  group.add(at(box(ROOM_SIZE[0], 0.08, 0.18, accent, { emissive: accent, emissiveIntensity: 0.6, shadow: false }),
               0, wallHeight + 0.02, away * ROOM_SIZE[1] / 2));
  const glass = { opacity: 0.18, roughness: 0.1, metalness: 0.2, shadow: false };
  for (const side of [-1, 1]) {
    group.add(at(box(0.08, 1.3, ROOM_SIZE[1], "#9fd8ff", glass), side * ROOM_SIZE[0] / 2, 0.65, 0));
    group.add(at(box(0.12, 0.08, ROOM_SIZE[1], "#22344a", { shadow: false }), side * ROOM_SIZE[0] / 2, 1.32, 0));
    group.add(at(box(2.1, 1.3, 0.06, "#9fd8ff", glass), side * 1.95, 0.65, -away * ROOM_SIZE[1] / 2));
  }
  return { group, floor, away, accent, base: floor.material.color.clone(), x, z };
}

// --- people ------------------------------------------------------------------------------------
function personMesh(color) {
  const person = new THREE.Group();
  const shirt = new THREE.Color(color);
  const legs = [];
  const arms = [];
  for (const side of [-1, 1]) {
    const leg = new THREE.Group();
    leg.position.set(side * 0.14, 0.62, 0);
    leg.add(at(box(0.16, 0.6, 0.18, "#26384a"), 0, -0.3, 0));
    person.add(leg);
    legs.push(leg);
    const arm = new THREE.Group();
    arm.position.set(side * 0.38, 1.25, 0);
    arm.add(at(box(0.12, 0.5, 0.14, shirt), 0, -0.25, 0));
    person.add(arm);
    arms.push(arm);
  }
  person.add(at(mesh(new THREE.CapsuleGeometry(0.3, 0.4, 4, 12), shirt, { roughness: 0.6 }), 0, 1.05, 0));
  person.add(at(mesh(new THREE.SphereGeometry(0.24, 18, 14), "#f2c9a0", { roughness: 0.7 }), 0, 1.68, 0));
  person.add(at(mesh(new THREE.SphereGeometry(0.25, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), "#2b2420"), 0, 1.72, 0));
  const folder = at(box(0.32, 0.4, 0.05, "#ffd08a"), 0.4, 0.95, 0.18);
  person.add(folder);
  // A soft halo under the feet in the worker's color keeps several workers apart at a glance.
  const halo = mesh(new THREE.RingGeometry(0.42, 0.58, 28), shirt, { emissive: shirt, emissiveIntensity: 0.9, shadow: false });
  halo.rotation.x = -Math.PI / 2;
  halo.position.y = 0.06;
  person.add(halo);
  return { person, legs, arms, folder };
}

export function createOffice(canvas, labelLayer, overlayLayer) {
  const colors = {
    bg: token("--bg", "#09111d"), surface2: token("--surface-2", "#172638"), mint: token("--mint", "#61e8c2"),
  };
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  // A-LLM shares the 6 GB GPU with this page: cap the pixel ratio and keep one small shadow map.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  scene.background = colors.bg;
  scene.fog = new THREE.Fog(colors.bg, 40, 80);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.42; // never under the floor
  controls.enablePan = false;

  scene.add(new THREE.HemisphereLight(0xdfefff, 0x101a26, 1.25));
  const sun = new THREE.DirectionalLight(0xfff4e0, 2.2);
  sun.position.set(-9, 20, -7);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -14, right: 14, top: 10, bottom: -10, near: 1, far: 50 });
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  scene.add(at(box(25, 0.3, 16, "#0e1824", { shadow: false }), 0, -0.2, 0));
  const grid = new THREE.GridHelper(24, 48, 0x24384c, 0x182736);
  grid.position.y = -0.04;
  scene.add(grid);
  const hallway = box(22.5, 0.06, 2.6, "#1d2c3d", { shadow: false });
  scene.add(hallway);
  for (const z of [-0.8, 0, 0.8]) scene.add(at(box(21, 0.02, 0.08, "#2b4a5c", { shadow: false }), 0, 0.04, z));
  for (const x of [-11, 11]) scene.add(at(plant(), x, 0, -1));

  const rooms = {};
  for (const id of Object.keys(ROOMS)) {
    if (id === "hallway") {
      rooms[id] = { floor: hallway, base: hallway.material.color.clone(), x: 0, z: 0,
                    accent: new THREE.Color(ACCENT.hallway), labelAt: [-10.4, 0.5, 0] };
      continue;
    }
    const room = roomShell(id, colors);
    room.labelAt = room.away > 0 ? [room.x, 0.6, room.z + ROOM_SIZE[1] / 2 + 0.3] : [room.x, 2.05, room.z - ROOM_SIZE[1] / 2];
    scene.add(room.group);
    rooms[id] = room;
  }

  // Reception: curved counter and plants.
  const counter = mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.95, 24, 1, true, Math.PI * 0.15, Math.PI * 0.7),
                       "#e8e1d4", { roughness: 0.6 });
  counter.material.side = THREE.DoubleSide;
  rooms.reception.group.add(at(counter, 0, 0.48, 0.3));
  rooms.reception.group.add(at(box(2.4, 0.06, 0.5, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.4 }), 0, 0.98, -1.05));
  rooms.reception.group.add(at(plant(), -2.3, 0, -1.6), at(plant(), 2.3, 0, -1.6));
  // The package arrives at reception as a parcel.
  const parcel = new THREE.Group();
  parcel.add(box(0.7, 0.5, 0.55, "#c99a5b", { roughness: 0.9 }));
  parcel.add(at(box(0.72, 0.06, 0.12, "#e8e1d4", { shadow: false }), 0, 0.25, 0));
  rooms.reception.group.add(at(parcel, 1.2, 1.25, 0.4));

  // Code room: workstations whose screens glow while an agent reads.
  const screens = [];
  for (const x of [-1.4, 1.4]) {
    const station = workstation(ACCENT.code);
    station.position.set(x, 0, -1.2);
    rooms.code.group.add(station);
    screens.push(station.userData.screen);
  }

  // Intel room: shelves and a globe.
  for (const x of [-1.5, 1.5]) rooms.intel.group.add(at(shelf(ACCENT.intel), x, 0, -1.9));
  rooms.intel.group.add(at(mesh(new THREE.CylinderGeometry(0.06, 0.25, 0.7, 8), "#5b4636"), 0, 0.35, 0.4));
  const globe = mesh(new THREE.IcosahedronGeometry(0.42, 1), "#7cc4ff", { roughness: 0.4, metalness: 0.1 });
  rooms.intel.group.add(at(globe, 0, 1.05, 0.4));

  // Sandbox lab: sealed until W5-6 connects the sandbox to the agent.
  rooms.lab.group.add(at(box(2.6, 1.6, 1.8, "#9fd8ff", { opacity: 0.25, roughness: 0.05, metalness: 0.3, shadow: false }), 0, 0.85, 0.7));
  rooms.lab.group.add(at(box(1, 0.6, 0.7, "#5c6b7a"), 0, 0.35, 0.7));
  for (let index = 0; index < 6; index += 1) {
    rooms.lab.group.add(at(box(0.45, 0.06, 0.12, index % 2 ? "#141c26" : "#ffd08a", { shadow: false }),
                           -1.1 + index * 0.45, 0.06, -2.05));
  }
  const lock = new THREE.Group();
  lock.add(box(0.36, 0.3, 0.12, "#ffd08a", { metalness: 0.6, roughness: 0.3 }));
  lock.add(at(mesh(new THREE.TorusGeometry(0.12, 0.035, 8, 16, Math.PI), "#c9cdd2", { metalness: 0.8 }), 0, 0.15, 0));
  rooms.lab.group.add(at(lock, 0, 1.1, -2.32));

  // Evidence room: one sheet per evidence check appears on the long table.
  rooms.evidence.group.add(at(box(3.6, 0.08, 1.2, "#c9b48f"), 0, 0.76, 0.6));
  for (const x of [-1.6, 1.6]) for (const z of [0.1, 1.1]) rooms.evidence.group.add(at(box(0.08, 0.74, 0.08, "#26384a"), x, 0.37, z));
  const papers = new THREE.Group();
  papers.position.set(0, 0.81, 0.6);
  rooms.evidence.group.add(papers);

  // Decision room: a raised bench and three lamps.
  rooms.decision.group.add(at(box(3.2, 0.25, 1.6, "#2b3b4e"), 0, 0.12, 1.1));
  rooms.decision.group.add(at(box(2.8, 1.05, 0.7, "#5b4636", { roughness: 0.5 }), 0, 0.77, 0.9));
  const lamps = {};
  Object.entries(ACTION_COLORS).forEach(([action, color], index) => {
    rooms.decision.group.add(at(mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8), "#26384a"), -0.9 + index * 0.9, 1.5, 0.9));
    lamps[action] = at(mesh(new THREE.SphereGeometry(0.22, 18, 14), color, { emissive: color, emissiveIntensity: 0.05, roughness: 0.3 }),
                       -0.9 + index * 0.9, 1.85, 0.9);
    rooms.decision.group.add(lamps[action]);
  });
  const lampLight = new THREE.PointLight(0xffffff, 0, 7, 1.6);
  lampLight.position.set(LAYOUT.decision[0], 2.4, LAYOUT.decision[1] + 0.4);
  scene.add(lampLight);
  // Alarm: a red beam that sweeps the decision room after a deny.
  const alarm = new THREE.SpotLight(0xff3b30, 0, 14, Math.PI / 7, 0.5, 1.2);
  alarm.position.set(LAYOUT.decision[0], 3.4, LAYOUT.decision[1]);
  scene.add(alarm, alarm.target);

  // Room labels and DOM screens (textContent only) placed over the canvas.
  const screensDom = {};
  for (const [id, info] of Object.entries(ROOMS)) {
    const label = document.createElement("div");
    label.className = "room-label" + (info.locked ? " locked" : "");
    label.style.setProperty("--accent", ACCENT[id]);
    const title = document.createElement("strong");
    title.textContent = info.name + (info.locked ? " 🔒" : "");
    const step = document.createElement("small");
    step.textContent = info.step;
    label.append(title, step);
    labelLayer.append(label);
    rooms[id].label = label;
    const screen = document.createElement("div");
    screen.className = "room-screen";
    screen.style.setProperty("--accent", ACCENT[id]);
    screen.hidden = true;
    overlayLayer.append(screen);
    screensDom[id] = screen;
  }
  const screenAt = { code: [0, 2.3, -4.6], evidence: [0, 1.7, 5.4], reception: [-7, 2.4, -4.0] };

  // --- workers -------------------------------------------------------------------------------
  const workers = new Map();
  let laneCount = 1;
  let dirty = true;
  const speed = { value: 1 };
  const projected = new THREE.Vector3();

  function laneOffset(lane) {
    return (lane - (laneCount - 1) / 2) * 0.85;
  }

  function spotFor(id, lane) {
    const [x, z] = LAYOUT[id];
    const offset = laneOffset(lane);
    if (id === "hallway") return new THREE.Vector3(x + offset * 2, 0, offset);
    return new THREE.Vector3(x + offset * 1.8, 0, z - Math.sign(z) * 0.5);
  }

  function addWorker({ id, name, color, lane }) {
    const body = personMesh(color);
    const start = spotFor("reception", lane);
    body.person.position.copy(start);
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
    label.textContent = name;
    tag.append(stamp, bubble, label);
    overlayLayer.append(tag);
    const worker = { ...body, tag, bubble, stamp, lane, path: [], room: "reception", phase: 0 };
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
      position: () => worker.person.position,
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
      room.floor.material.color.copy(on ? room.base.clone().lerp(room.accent, 0.45) : room.base);
      room.label.classList.toggle("active", on);
    }
    for (const screen of screens) screen.material.emissiveIntensity = occupied.has("code") ? 1.1 : 0.35;
    dirty = true;
  }

  function setScreen(room, text) {
    const screen = screensDom[room];
    if (screen.textContent === (text || "") && screen.hidden === !text) return;
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

  let lampKey = "";
  function setLamps(actions) {
    const key = actions.join(",");
    if (key === lampKey) return;
    lampKey = key;
    const lit = new Set(actions.filter(Boolean));
    for (const [key, bulb] of Object.entries(lamps)) bulb.material.emissiveIntensity = lit.has(key) ? 2.4 : 0.05;
    const main = actions.find(Boolean);
    lampLight.color.set(main ? ACTION_COLORS[main] : "#ffffff");
    lampLight.intensity = main ? 6 : 0;
    dirty = true;
  }

  // --- effects: confetti for approve, alarm and shake for deny, amber pulse for review ----------
  const effects = [];
  const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

  function celebrate(action) {
    if (reducedMotion()) return;
    const [x, z] = LAYOUT.decision;
    if (action === "approve") {
      const count = 160;
      const positions = new Float32Array(count * 3);
      const velocities = [];
      const palette = ["#61e8c2", "#7cc4ff", "#ffd08a", "#f4f8f5"].map((hex) => new THREE.Color(hex));
      const tints = new Float32Array(count * 3);
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
        shake = this.age < 0.45 ? (0.45 - this.age) * 0.5 : 0;
      }, end() { alarm.intensity = 0; shake = 0; } });
    } else if (action === "review") {
      effects.push({ life: 2.4, age: 0, step() {
        lamps.review.material.emissiveIntensity = 1.2 + Math.abs(Math.sin(this.age * 7)) * 2.5;
      }, end() { lamps.review.material.emissiveIntensity = 2.4; } });
    }
    dirty = true;
  }

  // --- camera: fitted overview, or a director that follows the workers --------------------------
  let shake = 0;
  let fitDistance = 30;
  const director = { on: false, target: new THREE.Vector3(), distance: 30 };

  function fit() {
    const { clientWidth: width, clientHeight: height } = canvas.parentElement;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    // Seen from above at an angle, depth is foreshortened, so the floor fits a smaller radius vertically.
    fitDistance = Math.max(12.6 / Math.tan(horizontal / 2), 7.4 / Math.tan(vertical / 2));
    controls.maxDistance = fitDistance * 1.6;
    controls.minDistance = fitDistance * 0.3;
    dirty = true;
  }

  function resetView() {
    controls.target.set(0, 0, 0.4);
    camera.position.copy(VIEW_DIRECTION).multiplyScalar(fitDistance).add(controls.target);
    dirty = true;
  }

  function setDirector(on) {
    director.on = on;
    if (!on) resetView();
    dirty = true;
  }

  function focus(room, closeness = 0.55) {
    if (!director.on) return;
    if (!room) {  // follow the centre of all workers
      director.target.set(0, 0, 0);
      director.distance = fitDistance * closeness;
      return;
    }
    const [x, z] = LAYOUT[room];
    director.target.set(x, 0.6, z * 0.75);
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

  // Render only while something moves; an idle office costs the GPU nothing (Ollama shares it).
  const stats = { frames: 0, fps: 0, since: performance.now(), continuous: false };
  const clock = new THREE.Clock();
  function frame() {
    const delta = Math.min(clock.getDelta(), 0.1);
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
      const swing = reduced || !worker.path.length ? 0 : Math.sin(worker.phase) * 0.55;
      worker.legs[0].rotation.x = swing;
      worker.legs[1].rotation.x = -swing;
      worker.arms[0].rotation.x = -swing * 0.8;
      worker.arms[1].rotation.x = swing * 0.8;
      worker.folder.rotation.x = swing * 0.3;
    }
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
      for (const worker of workers.values()) {
        const { x, z } = worker.person.position;
        // Tags of several workers are stacked by lane so stamps and bubbles never cover each other.
        place(worker.tag, [x, 2.2 + worker.lane * 0.95, z]);
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
    addWorker, clearWorkers, setScreen, setEvidence, setLamps, celebrate, setDirector, focus, resetView,
    speed, stats,
    info: () => ({ fps: stats.fps, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
                   pixelRatio: renderer.getPixelRatio(), workers: workers.size,
                   positions: [...workers.values()].map((worker) => [worker.room, +worker.person.position.x.toFixed(2),
                                                                      +worker.person.position.z.toFixed(2), worker.path.length]) }),
  };
}
