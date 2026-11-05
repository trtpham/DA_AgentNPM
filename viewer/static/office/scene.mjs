// Low-poly office drawn with Three.js. Rendering only; trace logic lives in events.mjs and main.mjs.
import * as THREE from "../vendor/three.module.min.js";
import { OrbitControls } from "../vendor/OrbitControls.js";
import { ROOMS } from "./events.mjs";

// U-shaped floor plan that follows the agent's four steps; the hallway runs along z = 0.
const LAYOUT = {
  reception: [-7, -4.6], code: [0, -4.6], intel: [7, -4.6],
  lab: [7, 4.6], evidence: [0, 4.6], decision: [-7, 4.6],
  hallway: [0, 0],
};
const ROOM_SIZE = [6, 4.6];
const VIEW_DIRECTION = new THREE.Vector3(0, 22, 17).normalize();

function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(value || fallback);
}

function box(width, height, depth, color, opacity = 1) {
  const material = new THREE.MeshStandardMaterial({ color, roughness: 0.85, transparent: opacity < 1, opacity });
  return new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), material);
}

export function createOffice(canvas, labelLayer) {
  const colors = {
    bg: token("--bg", "#09111d"), surface: token("--surface", "#111e2d"), surface2: token("--surface-2", "#172638"),
    line: token("--line", "#395165"), mint: token("--mint", "#61e8c2"), amber: token("--amber", "#ffd08a"),
    red: token("--red", "#ff8e83"), muted: token("--muted", "#b8cbd0"),
  };
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  // A-LLM shares the 6 GB GPU with this page: cap the pixel ratio (plan §1, O-0).
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  const scene = new THREE.Scene();
  scene.background = colors.bg;
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200);
  camera.position.set(0, 22, 20);
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.42; // never go under the floor

  scene.add(new THREE.HemisphereLight(0xdfefff, 0x0b1420, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(8, 18, 6);
  scene.add(sun);

  const ground = box(24, 0.2, 15, colors.surface);
  ground.position.y = -0.15;
  scene.add(ground);
  const hallway = box(22, 0.05, 3, colors.surface2);
  scene.add(hallway);

  const rooms = {};
  for (const [id, info] of Object.entries(ROOMS)) {
    const [x, z] = LAYOUT[id];
    const group = new THREE.Group();
    group.position.set(x, 0, z);
    if (id === "hallway") {
      // The hallway label sits at its far-left end so it never hides the walking worker.
      rooms[id] = { group, floor: hallway, base: colors.surface2.clone(), x, z, labelAt: [-10.2, 0.4, 0] };
    } else {
      const floor = box(ROOM_SIZE[0], 0.1, ROOM_SIZE[1], info.locked ? colors.line : colors.surface2);
      group.add(floor);
      const away = Math.sign(z); // back wall on the side away from the hallway
      const back = box(ROOM_SIZE[0], 1.1, 0.15, colors.line);
      back.position.set(0, 0.55, away * ROOM_SIZE[1] / 2);
      const left = box(0.15, 1.1, ROOM_SIZE[1], colors.line);
      left.position.set(-ROOM_SIZE[0] / 2, 0.55, 0);
      const right = left.clone();
      right.position.x = ROOM_SIZE[0] / 2;
      const desk = box(1.8, 0.75, 0.9, info.locked ? colors.muted : colors.amber, info.locked ? 0.35 : 1);
      desk.position.set(0, 0.4, away * 1.1);
      group.add(back, left, right, desk);
      if (info.locked) {
        const door = box(ROOM_SIZE[0] - 0.3, 1.1, 0.12, colors.muted, 0.55);
        door.position.set(0, 0.55, -away * ROOM_SIZE[1] / 2);
        group.add(door);
      }
      rooms[id] = { group, floor, base: floor.material.color.clone(), x, z, labelAt: [x, 1.5, z + away * ROOM_SIZE[1] / 2] };
      scene.add(group);
    }
    const label = document.createElement("div");
    label.className = "room-label" + (info.locked ? " locked" : "");
    const title = document.createElement("strong");
    title.textContent = info.name;
    const step = document.createElement("small");
    step.textContent = info.step;
    label.append(title, step);
    labelLayer.append(label);
    rooms[id].label = label;
  }

  // The worker: a capsule body and a head, moved along hallway waypoints.
  const worker = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.35, 0.7, 4, 12),
                              new THREE.MeshStandardMaterial({ color: colors.mint, roughness: 0.5 }));
  body.position.y = 0.75;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.28, 16, 12),
                              new THREE.MeshStandardMaterial({ color: colors.mint.clone().offsetHSL(0, 0, 0.15) }));
  head.position.y = 1.55;
  worker.add(body, head);
  worker.position.set(LAYOUT.reception[0], 0, LAYOUT.reception[1]);
  scene.add(worker);

  let path = [];
  let active = "reception";
  let dirty = true;
  const projected = new THREE.Vector3();

  function setActive(id) {
    for (const [roomId, room] of Object.entries(rooms)) {
      room.floor.material.color.copy(roomId === id ? colors.mint.clone().multiplyScalar(0.45) : room.base);
      room.label.classList.toggle("active", roomId === id);
    }
    active = id;
    dirty = true;
  }

  function walkTo(id) {
    const [x, z] = LAYOUT[id];
    const here = worker.position;
    if (id === active) {  // same room: keep walking the current path, if any
      dirty = true;
      return;
    }
    path = [];
    // Leave the room into the hallway, walk along it, then enter the target room.
    if (Math.abs(here.z) > 0.5) path.push(new THREE.Vector3(here.x, 0, 0));
    path.push(new THREE.Vector3(x, 0, 0));
    if (id !== "hallway") path.push(new THREE.Vector3(x, 0, z));
    setActive(id);
  }

  function resize() {
    const { clientWidth: width, clientHeight: height } = canvas.parentElement;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    // Fit the whole floor (about a 13.5 unit radius) whatever the aspect ratio; narrow screens back off.
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    const distance = 13.5 / Math.sin(Math.min(vertical, horizontal) / 2);
    camera.position.copy(VIEW_DIRECTION).multiplyScalar(distance).add(controls.target);
    controls.maxDistance = distance * 1.6;
    controls.minDistance = distance * 0.45;
    dirty = true;
  }

  function placeLabels() {
    const { clientWidth: width, clientHeight: height } = canvas;
    for (const room of Object.values(rooms)) {
      projected.set(...room.labelAt).project(camera);
      room.label.style.transform = `translate(-50%, -50%) translate(${(projected.x + 1) / 2 * width}px, ${(1 - projected.y) / 2 * height}px)`;
    }
  }

  // Render only while something moves; an idle office costs the GPU nothing (Ollama shares it).
  const stats = { frames: 0, fps: 0, since: performance.now(), continuous: false };
  const clock = new THREE.Clock();
  function frame() {
    const delta = Math.min(clock.getDelta(), 0.1);
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (path.length) {
      const target = path[0];
      const step = reduced ? Infinity : 6 * delta * speed.value;
      const offset = target.clone().sub(worker.position);
      if (offset.length() <= step) {
        worker.position.copy(target);
        path.shift();
      } else {
        worker.position.add(offset.setLength(step));
        worker.rotation.y = Math.atan2(offset.x, offset.z);
      }
      body.position.y = 0.75 + (reduced ? 0 : Math.abs(Math.sin(performance.now() / 120)) * 0.08);
      dirty = true;
    }
    if (stats.continuous) {
      controls.autoRotate = true;
      dirty = true;
    }
    if (controls.update(delta)) dirty = true;
    if (dirty && !document.hidden) {
      renderer.render(scene, camera);
      placeLabels();
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
  const speed = { value: 1 };
  controls.addEventListener("change", () => { dirty = true; });
  addEventListener("resize", resize);
  resize();
  setActive("reception");
  requestAnimationFrame(frame);
  return {
    walkTo, speed, stats,
    info: () => ({ fps: stats.fps, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
                   pixelRatio: renderer.getPixelRatio() }),
    isWalking: () => path.length > 0,
  };
}
