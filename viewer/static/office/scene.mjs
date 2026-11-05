// The 3D office drawn with Three.js. Rendering only; trace logic lives in events.mjs/explain.mjs/main.mjs.
// People are the AI models (workers) and office staff; robots are deterministic code (tools, checks, rules).
import * as THREE from "../vendor/three.module.min.js";
import { OrbitControls } from "../vendor/OrbitControls.js";
import { ROOMS } from "./events.mjs";
import { at, box, mesh, personMesh, robotMesh } from "./people.mjs";
import { barrierGate, chair, coffeeBar, desk, monitor, plant, printer, rug, serverRack, shelf, sofa,
         textures, waterCooler, wallPoster, workstation } from "./props.mjs";

// Two rows of five areas around one hallway (z = 0). The six inner rooms follow the agent's steps;
// the four wings hold the parts around it: npm gate, local GPU server, human reviewer, pantry.
const LAYOUT = {
  gate: [-14, -4.6], reception: [-7, -4.6], code: [0, -4.6], intel: [7, -4.6], server: [14, -4.6],
  reviewer: [-14, 4.6], decision: [-7, 4.6], evidence: [0, 4.6], lab: [7, 4.6], pantry: [14, 4.6],
  hallway: [0, 0],
};
const WINGS = {
  gate: { name: "Cổng npm", step: "npm pack · barie theo quyết định" },
  server: { name: "Máy chủ Ollama", step: "Mô hình chạy cục bộ trên GPU" },
  reviewer: { name: "Bàn người xem", step: "Ca R7/R8 cần duyệt tay" },
  pantry: { name: "Pantry", step: "Nghỉ giải lao" },
};
const ROOM_SIZE = [6, 4.6];
const VIEW_DIRECTION = new THREE.Vector3(0, 22, 15.5).normalize();
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
  const [x, z] = LAYOUT[id];
  const away = Math.sign(z); // the back wall is on the side away from the hallway
  const accent = new THREE.Color(ACCENT[id]);
  const group = new THREE.Group();
  group.position.set(x, 0, z);
  const floor = box(ROOM_SIZE[0], 0.1, ROOM_SIZE[1], "#ffffff", { shadow: false, ...floorMaterial(FLOORS[id]) });
  if (info.locked) floor.material.color.set("#8a96a3");
  group.add(floor);
  // Rooms whose back wall faces the camera get a low cut-away wall, as in isometric games.
  const wallHeight = away > 0 ? 0.4 : 1.7;
  group.add(at(box(ROOM_SIZE[0], wallHeight, 0.16, "#2a3d52"), 0, wallHeight / 2, away * ROOM_SIZE[1] / 2));
  group.add(at(box(ROOM_SIZE[0], 0.08, 0.18, accent, { emissive: accent, emissiveIntensity: 0.6, shadow: false }),
               0, wallHeight + 0.02, away * ROOM_SIZE[1] / 2));
  const glass = { opacity: 0.16, roughness: 0.1, metalness: 0.2, shadow: false };
  for (const side of [-1, 1]) {
    group.add(at(box(0.08, 1.3, ROOM_SIZE[1], "#9fd8ff", glass), side * ROOM_SIZE[0] / 2, 0.65, 0));
    group.add(at(box(0.12, 0.08, ROOM_SIZE[1], "#22344a", { shadow: false }), side * ROOM_SIZE[0] / 2, 1.32, 0));
    group.add(at(box(2.1, 1.3, 0.06, "#9fd8ff", glass), side * 1.95, 0.65, -away * ROOM_SIZE[1] / 2));
  }
  return { group, floor, away, accent, base: floor.material.color.clone(), x, z, info };
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

  // Building: slab, city skyline behind the north windows, hallway with a runner and planters.
  scene.add(at(box(36, 0.3, 17, "#0e1824", { shadow: false }), 0, -0.2, 0));
  const glowing = (item, strength) => {
    item.material.emissive = new THREE.Color("#ffffff");
    item.material.emissiveMap = item.material.map;
    item.material.emissiveIntensity = strength;
    return item;
  };
  scene.add(at(glowing(mesh(new THREE.PlaneGeometry(40, 7), "#ffffff", { map: textures.skyline(), shadow: false }), 0.55), 0, 3, -7.6));
  for (let x = -16.5; x <= 16.6; x += 3.3) scene.add(at(box(0.18, 3.4, 0.18, "#2a3d52"), x, 1.7, -7.3));
  scene.add(at(box(34, 0.18, 0.2, "#2a3d52"), 0, 3.4, -7.3));
  const hallway = box(34, 0.06, 2.6, "#9aa0a8", { shadow: false, map: textures.wood([10, 1]) });
  scene.add(hallway);
  scene.add(at(rug(30, 1.1, "#2b4a5c"), 0, 0.05, 0));
  for (const x of [-10.5, -3.5, 3.5, 10.5]) scene.add(at(plant(0.9), x, 0, -1.05));
  scene.add(at(waterCooler(), 16.4, 0, -0.9));
  scene.add(at(glowing(mesh(new THREE.PlaneGeometry(4.2, 0.8), "#ffffff", { map: textures.sign("NPM AGENT HQ", "#61e8c2"), shadow: false }), 0.8),
               -14, 2.6, -6.75));

  const rooms = {};
  for (const id of [...Object.keys(ROOMS), ...Object.keys(WINGS)]) {
    if (id === "hallway") {
      rooms[id] = { floor: hallway, base: hallway.material.color.clone(), x: 0, z: 0, accent: new THREE.Color(ACCENT.hallway),
                    labelAt: [-16, 0.5, 0], info: ROOMS.hallway };
      continue;
    }
    const room = roomShell(id);
    room.labelAt = room.away > 0 ? [room.x, 0.6, room.z + ROOM_SIZE[1] / 2 + 0.3] : [room.x, 2.15, room.z - ROOM_SIZE[1] / 2];
    scene.add(room.group);
    rooms[id] = room;
  }
  const add = (room, item, x, y, z, turn = 0) => { item.position.set(x, y, z); item.rotation.y = turn; rooms[room].group.add(item); return item; };

  // Gate: door, barrier, parcels and a desk for the guard.
  add("gate", box(0.12, 2.2, 1.6, "#3a5068"), -2.95, 1.1, 0);
  add("gate", box(0.06, 2, 1.4, "#9fd8ff", { opacity: 0.35, shadow: false }), -2.92, 1, 0);
  const gate = add("gate", barrierGate(), 1.4, 0, 1.9, Math.PI);
  add("gate", desk(1.2, 0.6), 1.7, 0, -1.2);
  add("gate", monitor("#f4b860", 0.6), 1.7, 0.92, -1.35);
  add("gate", plant(1.1), -2.4, 0, -1.8);
  for (let index = 0; index < 3; index += 1) add("gate", box(0.5, 0.4, 0.45, "#c99a5b"), -1.9 + index * 0.15, 0.2 + index * 0.4, -1.4);

  // Reception: counter, sign strip, plants and a safety poster.
  const counter = mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.95, 24, 1, true, Math.PI * 0.15, Math.PI * 0.7), "#e8e1d4", { roughness: 0.6 });
  counter.material.side = THREE.DoubleSide;
  add("reception", counter, 0, 0.48, 0.3);
  add("reception", box(2.4, 0.06, 0.5, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 0.4 }), 0, 0.98, -1.05);
  add("reception", plant(), -2.3, 0, -1.6);
  add("reception", plant(), 2.3, 0, -1.6);
  add("reception", wallPoster("AN TOÀN", ["Không chạy mã gói", "trên máy thật.", "Chỉ npm pack", "+ đọc file."], "#61e8c2"), -1.6, 1.15, -2.2);
  const parcel = new THREE.Group();
  parcel.add(box(0.7, 0.5, 0.55, "#c99a5b", { roughness: 0.9 }));
  parcel.add(at(box(0.72, 0.06, 0.12, "#e8e1d4", { shadow: false }), 0, 0.25, 0));
  add("reception", parcel, 1.2, 1.25, 0.4);

  // Code room: workstations whose screens show code; a whiteboard with source -> action -> sink.
  const screens = [];
  for (const x of [-1.6, 1.6]) screens.push(add("code", workstation(ACCENT.code), x, 0, -1.25).userData.screen);
  add("code", mesh(new THREE.PlaneGeometry(2.4, 1.2), "#ffffff", { map: textures.whiteboard(), shadow: false }), 0, 1.0, -2.2);

  // Intel room: shelves, a globe on a stand, a reading chair.
  add("intel", shelf(ACCENT.intel), -1.5, 0, -1.9);
  add("intel", shelf(ACCENT.intel), 0.4, 0, -1.9);
  add("intel", mesh(new THREE.CylinderGeometry(0.06, 0.25, 0.7, 8), "#5b4636"), -0.6, 0.35, 0.5);
  const globe = add("intel", mesh(new THREE.IcosahedronGeometry(0.42, 1), "#7cc4ff", { roughness: 0.4, metalness: 0.1 }), -0.6, 1.05, 0.5);
  add("intel", chair("#5b4636"), 1.6, 0, 0.6, -0.6);

  // Server room: GPU racks whose lights follow the models that are thinking, and an operator desk.
  const racks = [-1.9, -0.7, 0.5].map((x) => add("server", serverRack(ACCENT.server), x, 0, -1.7));
  add("server", glowing(mesh(new THREE.PlaneGeometry(2.6, 0.5), "#ffffff", { map: textures.sign("OLLAMA · GPU 6 GB", "#ff7ad9"), shadow: false }), 0.9),
      -0.7, 2.45, -2.15);
  add("server", desk(1.3, 0.7), 1.9, 0, -0.6, -Math.PI / 2);
  add("server", monitor("#ff7ad9", 0.7), 1.75, 0.92, -0.6, -Math.PI / 2);
  const leds = racks.flatMap((rack) => rack.userData.leds);
  const gpuGlow = add("server", new THREE.PointLight(0xff7ad9, 0, 6, 1.6), -0.7, 1.6, -0.6);

  // Sandbox lab: sealed until W5-6 connects the sandbox to the agent.
  add("lab", box(2.6, 1.6, 1.8, "#9fd8ff", { opacity: 0.25, roughness: 0.05, metalness: 0.3, shadow: false }), 0.4, 0.85, 0.7);
  add("lab", box(1, 0.6, 0.7, "#5c6b7a"), 0.4, 0.35, 0.7);
  for (let index = 0; index < 6; index += 1) {
    add("lab", box(0.45, 0.06, 0.12, index % 2 ? "#141c26" : "#ffd08a", { shadow: false }), -1.1 + index * 0.45, 0.06, -2.05);
  }
  const lock = new THREE.Group();
  lock.add(box(0.36, 0.3, 0.12, "#ffd08a", { metalness: 0.6, roughness: 0.3 }));
  lock.add(at(mesh(new THREE.TorusGeometry(0.12, 0.035, 8, 16, Math.PI), "#c9cdd2", { metalness: 0.8 }), 0, 0.15, 0));
  add("lab", lock, 0, 1.1, -2.32);

  // Evidence room: a long table where one sheet per evidence check appears, plus a file cabinet.
  add("evidence", box(3.6, 0.08, 1.2, "#c9b48f"), 0, 0.76, 0.6);
  for (const x of [-1.6, 1.6]) for (const z of [0.1, 1.1]) add("evidence", box(0.08, 0.74, 0.08, "#26384a"), x, 0.37, z);
  add("evidence", box(0.6, 1.3, 0.55, "#5c6b7a", { metalness: 0.4 }), 2.5, 0.65, 1.5);
  const papers = add("evidence", new THREE.Group(), 0, 0.81, 0.6);

  // Decision room: a raised bench and three lamps.
  add("decision", box(3.2, 0.25, 1.6, "#2b3b4e"), 0, 0.12, 1.1);
  add("decision", box(2.8, 1.05, 0.7, "#5b4636", { roughness: 0.5 }), 0, 0.77, 0.9);
  const lamps = {};
  Object.entries(ACTION_COLORS).forEach(([action, color], index) => {
    add("decision", mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8), "#26384a"), -0.9 + index * 0.9, 1.5, 0.9);
    lamps[action] = add("decision", mesh(new THREE.SphereGeometry(0.22, 18, 14), color, { emissive: color, emissiveIntensity: 0.05, roughness: 0.3 }),
                        -0.9 + index * 0.9, 1.85, 0.9);
  });
  const lampLight = new THREE.PointLight(0xffffff, 0, 7, 1.6);
  lampLight.position.set(LAYOUT.decision[0], 2.4, LAYOUT.decision[1] + 0.4);
  scene.add(lampLight);
  const alarm = new THREE.SpotLight(0xff3b30, 0, 14, Math.PI / 7, 0.5, 1.2);
  alarm.position.set(LAYOUT.decision[0], 3.4, LAYOUT.decision[1]);
  scene.add(alarm, alarm.target);

  // Reviewer: a desk with two screens, an inbox tray and a printer for cases sent to a human.
  add("reviewer", desk(2, 0.8, "#e8e1d4"), 0, 0, 0.5, Math.PI);
  add("reviewer", monitor("#e8f4ff", 0.7), -0.45, 0.92, 0.7, Math.PI);
  add("reviewer", monitor("#ffd08a", 0.7), 0.45, 0.92, 0.7, Math.PI);
  add("reviewer", printer(), 2.3, 0, 1.3);
  add("reviewer", plant(1.2), -2.4, 0, 1.6);
  const inbox = add("reviewer", new THREE.Group(), 0.9, 0.8, 0.3);

  // Pantry: coffee bar, sofa, a round table and a poster.
  add("pantry", coffeeBar(), 0, 0, 1.6, Math.PI);
  add("pantry", sofa("#7a5c8f"), -1.4, 0, -1.2);
  add("pantry", mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.05, 20), "#e8e1d4"), 1.2, 0.72, -0.6);
  add("pantry", mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.7, 8), "#26384a"), 1.2, 0.36, -0.6);
  add("pantry", wallPoster("NGHỈ 5'", ["Trace vẫn chạy,", "luật vẫn canh."], "#c99a5b", 0.9), 2.3, 0.75, 2.2, Math.PI);

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
  const screenAt = { code: [0, 2.4, -4.6], evidence: [0, 1.7, 5.4], reception: [-7, 2.5, -4.0], server: [13.3, 2.9, -5.5], reviewer: [-14, 2.1, 5.2] };

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
    reception: { name: "read_manifest", at: [-8.4, -5.5], face: 0, gear: { clipboard: true } },
    code: { name: "read_file · extract_indicators · deobfuscate", at: [0, -6.1], face: 0, gear: {} },
    intel: { name: "OSV · npm Registry (chạy trước)", at: [8.9, -5.3], face: -0.5, gear: { book: true } },
    lab: { name: "Sandbox (khóa đến W5-6)", at: [5.0, 3.2], face: Math.PI, gear: { shield: true } },
    evidence: { name: "Kiểm chứng file:dòng", at: [0, 6.15], face: Math.PI, gear: { magnifier: true } },
    decision: { name: "Luật R1–R8 (thẩm phán)", at: [-7, 6.35], face: Math.PI, lift: 0.25, gear: { gavel: true, robe: "#1a1f26" } },
  };
  const STAFF = {
    courier: { role: "📦 Giao hàng npm", at: [-15.6, -3.6], face: Math.PI / 2,
               look: { shirt: "#c99a5b", pants: "#5b4636", hair: "cap", capColor: "#8a5a2b", hold: "none", skin: "#d9a77c" } },
    guard: { role: "🛡️ Bảo vệ cổng", at: [-12.2, -3.0], face: Math.PI,
             look: { shirt: "#22344a", pants: "#1a1f26", hair: "cap", capColor: "#1a1f26", vest: "#30475f", hold: "none", skin: "#b97f55" } },
    tech: { role: "🧑‍💻 Kỹ thuật GPU", at: [15.2, -4.9], face: -Math.PI / 2,
            look: { shirt: "#3a2b4f", hair: "short", hairColor: "#5b3a24", glasses: true, hold: "tablet", badge: "#ff7ad9" } },
    reviewer: { role: "👁 Người xem (duyệt tay)", at: [-14, 3.5], face: 0,
                look: { shirt: "#f4f8f5", tie: "#2b7de9", hair: "short", hairColor: "#1a1f26", glasses: true, hold: "clipboard", skin: "#f5d3b3" } },
    po: { role: "⭐ PO (trưởng nhóm)", at: [12.7, 3.6], face: -0.4,
          look: { shirt: "#61e8c2", pants: "#26384a", hair: "long", hairColor: "#2b2420", hold: "cup", badge: "#ffd08a" } },
    barista: { role: "☕ Barista", at: [14.4, 6.6], face: Math.PI,
               look: { shirt: "#e8e1d4", apron: "#5b4636", hair: "bun", hairColor: "#8a5a2b", hold: "none", skin: "#d9a77c" } },
    janitor: { role: "🧹 Lao công", at: [-15, -1.2], face: Math.PI / 2,
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
  cart.position.set(-14.15, 0, -1.2);
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

  function laneOffset(lane) { return (lane - (laneCount - 1) / 2) * 0.85; }

  function spotFor(id, lane) {
    const [x, z] = LAYOUT[id];
    const offset = laneOffset(lane);
    if (id === "hallway") return new THREE.Vector3(x + offset * 2, 0, offset);
    return new THREE.Vector3(x + offset * 1.8, 0, z - Math.sign(z) * 0.5);
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

  function fit() {
    const { clientWidth: width, clientHeight: height } = canvas.parentElement;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    // Seen from above at an angle, depth is foreshortened, so the floor fits a smaller radius vertically.
    fitDistance = Math.max(18.4 / Math.tan(horizontal / 2), 8.2 / Math.tan(vertical / 2));
    controls.maxDistance = fitDistance * 1.5;
    controls.minDistance = fitDistance * 0.22;
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
    if (!room) { director.target.set(0, 0, 0); director.distance = fitDistance * closeness; return; }
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
      const x = forward ? -15.5 + patrol : 14.5 - (patrol - 30);
      staff.janitor.person.position.set(x, 0, -1.2);
      staff.janitor.person.rotation.y = forward ? Math.PI / 2 : -Math.PI / 2;
      walkCycle(staff.janitor, idleTime * 7, 0.35);
      cart.position.set(x + (forward ? 0.85 : -0.85), 0, -1.2);
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
                   pixelRatio: renderer.getPixelRatio(), workers: workers.size,
                   positions: [...workers.values()].map((worker) => [worker.room, +worker.person.position.x.toFixed(2),
                                                                      +worker.person.position.z.toFixed(2), worker.path.length]) }),
  };
}
