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
const ACCENT = {
  reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8",
  evidence: "#ffd08a", decision: "#ff8e83", hallway: "#395165",
};
const ACTION_COLORS = { approve: "#61e8c2", review: "#ffd08a", deny: "#ff8e83" };

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

// --- room shells -------------------------------------------------------------------------------
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
  const back = box(ROOM_SIZE[0], wallHeight, 0.16, "#22344a");
  group.add(at(back, 0, wallHeight / 2, away * ROOM_SIZE[1] / 2));
  group.add(at(box(ROOM_SIZE[0], 0.08, 0.18, accent, { emissive: accent, emissiveIntensity: 0.6, shadow: false }),
               0, wallHeight + 0.02, away * ROOM_SIZE[1] / 2));
  const glass = { opacity: 0.18, roughness: 0.1, metalness: 0.2, shadow: false };
  for (const side of [-1, 1]) {
    group.add(at(box(0.08, 1.3, ROOM_SIZE[1], "#9fd8ff", glass), side * ROOM_SIZE[0] / 2, 0.65, 0));
    group.add(at(box(0.12, 0.08, ROOM_SIZE[1], "#22344a", { shadow: false }), side * ROOM_SIZE[0] / 2, 1.32, 0));
  }
  // Front glass with a doorway in the middle, facing the hallway.
  for (const side of [-1, 1]) {
    group.add(at(box(2.1, 1.3, 0.06, "#9fd8ff", glass), side * 1.95, 0.65, -away * ROOM_SIZE[1] / 2));
  }
  return { group, floor, away, accent, base: floor.material.color.clone(), x, z };
}

export function createOffice(canvas, labelLayer, workerLayer) {
  const colors = {
    bg: token("--bg", "#09111d"), surface: token("--surface", "#111e2d"), surface2: token("--surface-2", "#172638"),
    line: token("--line", "#395165"), mint: token("--mint", "#61e8c2"),
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

  // Building slab, grid and hallway runner.
  scene.add(at(box(25, 0.3, 16, "#0e1824", { shadow: false }), 0, -0.2, 0));
  const grid = new THREE.GridHelper(24, 48, 0x24384c, 0x182736);
  grid.position.y = -0.04;
  scene.add(grid);
  const hallway = box(22.5, 0.06, 2.6, "#1d2c3d", { shadow: false });
  scene.add(hallway);
  scene.add(at(box(21, 0.02, 0.9, "#2b4a5c", { shadow: false }), 0, 0.04, 0));
  for (const x of [-11, 11]) scene.add(at(plant(), x, 0, -1));

  const rooms = {};
  for (const id of Object.keys(ROOMS)) {
    if (id === "hallway") {
      rooms[id] = { floor: hallway, base: hallway.material.color.clone(), x: 0, z: 0, accent: new THREE.Color(ACCENT.hallway),
                    labelAt: [-10.4, 0.5, 0] };
      continue;
    }
    const room = roomShell(id, colors);
    const { group, away } = room;
    room.labelAt = away > 0 ? [room.x, 0.6, room.z + ROOM_SIZE[1] / 2 + 0.3] : [room.x, 2.05, room.z - ROOM_SIZE[1] / 2];
    scene.add(group);
    rooms[id] = room;
  }

  // Reception: curved counter, plant and a sign.
  const counter = mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.95, 24, 1, true, Math.PI * 0.15, Math.PI * 0.7),
                       "#e8e1d4", { roughness: 0.6 });
  counter.material.side = THREE.DoubleSide;
  rooms.reception.group.add(at(counter, 0, 0.48, 0.3));
  rooms.reception.group.add(at(box(2.4, 0.06, 0.5, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.4 }), 0, 0.98, -1.05));
  rooms.reception.group.add(at(plant(), -2.3, 0, -1.6), at(plant(), 2.3, 0, -1.6));

  // Code room: two workstations whose screens glow while the agent reads.
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

  // Sandbox lab: a sealed glass container, locked until W5-6 connects the sandbox to the agent.
  rooms.lab.group.add(at(box(2.6, 1.6, 1.8, "#9fd8ff", { opacity: 0.25, roughness: 0.05, metalness: 0.3, shadow: false }), 0, 0.85, 0.7));
  rooms.lab.group.add(at(box(1, 0.6, 0.7, "#5c6b7a"), 0, 0.35, 0.7));
  for (let index = 0; index < 6; index += 1) {
    rooms.lab.group.add(at(box(0.45, 0.06, 0.12, index % 2 ? "#141c26" : "#ffd08a", { shadow: false }),
                           -1.1 + index * 0.45, 0.06, -2.05));
  }
  const lock = new THREE.Group();
  lock.add(at(box(0.36, 0.3, 0.12, "#ffd08a", { metalness: 0.6, roughness: 0.3 }), 0, 0, 0));
  lock.add(at(mesh(new THREE.TorusGeometry(0.12, 0.035, 8, 16, Math.PI), "#c9cdd2", { metalness: 0.8 }), 0, 0.15, 0));
  rooms.lab.group.add(at(lock, 0, 1.1, -2.32));

  // Evidence room: a long table where one sheet per evidence check appears.
  rooms.evidence.group.add(at(box(3.6, 0.08, 1.2, "#c9b48f"), 0, 0.76, 0.6));
  for (const x of [-1.6, 1.6]) for (const z of [0.1, 1.1]) rooms.evidence.group.add(at(box(0.08, 0.74, 0.08, "#26384a"), x, 0.37, z));
  for (const x of [-1.2, 0, 1.2]) {
    const seat = chair("#26384a");
    seat.position.set(x, 0, -0.2);
    rooms.evidence.group.add(seat);
  }
  const papers = new THREE.Group();
  papers.position.set(0, 0.81, 0.6);
  rooms.evidence.group.add(papers);

  // Decision room: a raised bench with three lamps; the final action lights one of them.
  rooms.decision.group.add(at(box(3.2, 0.25, 1.6, "#2b3b4e"), 0, 0.12, 1.1));
  rooms.decision.group.add(at(box(2.8, 1.05, 0.7, "#5b4636", { roughness: 0.5 }), 0, 0.77, 0.9));
  const lamps = {};
  const lampLight = new THREE.PointLight(0xffffff, 0, 6, 1.6);
  lampLight.position.set(0, 2.2, 0.6);
  rooms.decision.group.add(lampLight);
  Object.entries(ACTION_COLORS).forEach(([action, color], index) => {
    rooms.decision.group.add(at(mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8), "#26384a"), -0.9 + index * 0.9, 1.5, 0.9));
    const bulb = mesh(new THREE.SphereGeometry(0.22, 18, 14), color, { emissive: color, emissiveIntensity: 0.05, roughness: 0.3 });
    lamps[action] = at(bulb, -0.9 + index * 0.9, 1.85, 0.9);
    rooms.decision.group.add(bulb);
  });

  // --- worker: body, swinging legs and arms, a folder, and a DOM name tag with a speech bubble ---
  const worker = new THREE.Group();
  const shirt = new THREE.Color(colors.mint);
  const legs = [];
  const arms = [];
  for (const side of [-1, 1]) {
    const leg = new THREE.Group();
    leg.position.set(side * 0.14, 0.62, 0);
    leg.add(at(box(0.16, 0.6, 0.18, "#26384a"), 0, -0.3, 0));
    worker.add(leg);
    legs.push(leg);
    const arm = new THREE.Group();
    arm.position.set(side * 0.38, 1.25, 0);
    arm.add(at(box(0.12, 0.5, 0.14, shirt), 0, -0.25, 0));
    worker.add(arm);
    arms.push(arm);
  }
  worker.add(at(mesh(new THREE.CapsuleGeometry(0.3, 0.4, 4, 12), shirt, { roughness: 0.6 }), 0, 1.05, 0));
  worker.add(at(mesh(new THREE.SphereGeometry(0.24, 18, 14), "#f2c9a0", { roughness: 0.7 }), 0, 1.68, 0));
  worker.add(at(mesh(new THREE.SphereGeometry(0.25, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), "#2b2420"), 0, 1.72, 0));
  const folder = at(box(0.32, 0.4, 0.05, "#ffd08a"), 0.4, 0.95, 0.18);
  worker.add(folder);
  worker.position.set(LAYOUT.reception[0], 0, LAYOUT.reception[1] + 1);
  scene.add(worker);

  // Room labels and the worker tag are DOM nodes (textContent only) placed over the canvas.
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
  }
  const tag = document.createElement("div");
  tag.className = "worker-tag";
  const bubble = document.createElement("span");
  bubble.className = "worker-bubble";
  const name = document.createElement("strong");
  tag.append(bubble, name);
  workerLayer.append(tag);

  let path = [];
  let active = null;
  let dirty = true;
  let walkPhase = 0;
  let lampTarget = null;
  const projected = new THREE.Vector3();
  const speed = { value: 1 };

  function setActive(id) {
    for (const [roomId, room] of Object.entries(rooms)) {
      const on = roomId === id;
      room.floor.material.color.copy(on ? room.base.clone().lerp(room.accent, 0.45) : room.base);
      room.label.classList.toggle("active", on);
    }
    for (const screen of screens) screen.material.emissiveIntensity = id === "code" ? 1.1 : 0.35;
    active = id;
    dirty = true;
  }

  // instant: jump straight there (scrubbing the timeline); otherwise walk along the hallway.
  function walkTo(id, instant = false) {
    const [x, z] = LAYOUT[id];
    const spot = new THREE.Vector3(x + (id === "hallway" ? 0 : 0.6), 0, id === "hallway" ? 0 : z - Math.sign(z) * 0.4);
    if (instant) {
      path = [];
      worker.position.copy(spot);
      setActive(id);
      return;
    }
    if (id === active) {  // same room: keep walking the current path, if any
      dirty = true;
      return;
    }
    const here = worker.position;
    path = [];
    if (Math.abs(here.z) > 0.5) path.push(new THREE.Vector3(here.x, 0, 0));
    path.push(new THREE.Vector3(x, 0, 0));
    if (id !== "hallway") path.push(spot);
    setActive(id);
  }

  function setEvidence(checks) {
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

  function setDecision(action) {
    for (const [key, bulb] of Object.entries(lamps)) bulb.material.emissiveIntensity = key === action ? 2.4 : 0.05;
    lampTarget = action ? new THREE.Color(ACTION_COLORS[action] || "#ffffff") : null;
    lampLight.color.copy(lampTarget || new THREE.Color("#ffffff"));
    lampLight.intensity = lampTarget ? 6 : 0;
    dirty = true;
  }

  function setWorker(label, text) {
    name.textContent = label;
    bubble.textContent = text;
    bubble.hidden = !text;
    dirty = true;
  }

  function resize() {
    const { clientWidth: width, clientHeight: height } = canvas.parentElement;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    // Fit the whole floor (about a 13.5 unit radius) whatever the aspect ratio; narrow screens back off.
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    // Seen from above at an angle, depth is foreshortened, so the floor fits a smaller radius vertically.
    const distance = Math.max(12.6 / Math.tan(horizontal / 2), 7.4 / Math.tan(vertical / 2));
    controls.target.set(0, 0, 0.4);
    camera.position.copy(VIEW_DIRECTION).multiplyScalar(distance).add(controls.target);
    controls.maxDistance = distance * 1.6;
    controls.minDistance = distance * 0.4;
    dirty = true;
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
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (path.length) {
      const target = path[0];
      const step = reduced ? Infinity : 5.5 * delta * speed.value;
      const offset = target.clone().sub(worker.position);
      if (offset.length() <= step) {
        worker.position.copy(target);
        path.shift();
      } else {
        worker.position.add(offset.clone().setLength(step));
        worker.rotation.y = Math.atan2(offset.x, offset.z);
      }
      walkPhase += delta * 11 * speed.value;
      dirty = true;
    } else if (walkPhase) {
      walkPhase = 0;
      worker.rotation.y = active === "hallway" ? 0 : Math.PI * (LAYOUT[active][1] > 0 ? 0 : 1);
      dirty = true;
    }
    const swing = reduced || !path.length ? 0 : Math.sin(walkPhase) * 0.55;
    legs[0].rotation.x = swing;
    legs[1].rotation.x = -swing;
    arms[0].rotation.x = -swing * 0.8;
    arms[1].rotation.x = swing * 0.8;
    folder.rotation.x = swing * 0.3;
    if (!reduced && active === "intel") {
      globe.rotation.y += delta * 0.8;
      dirty = true;
    }
    if (stats.continuous) {
      controls.autoRotate = true;
      dirty = true;
    }
    if (controls.update(delta)) dirty = true;
    if (dirty && !document.hidden) {
      renderer.render(scene, camera);
      for (const room of Object.values(rooms)) place(room.label, room.labelAt);
      place(tag, [worker.position.x, 2.25, worker.position.z]);
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
  new ResizeObserver(resize).observe(canvas.parentElement);
  resize();
  setActive("reception");
  setDecision(null);
  setWorker("agent", "");
  requestAnimationFrame(frame);
  return {
    walkTo, setEvidence, setDecision, setWorker, speed, stats,
    resetView: resize,
    info: () => ({ fps: stats.fps, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
                   pixelRatio: renderer.getPixelRatio(), active, walking: path.length,
                   worker: [+worker.position.x.toFixed(2), +worker.position.z.toFixed(2)] }),
  };
}
