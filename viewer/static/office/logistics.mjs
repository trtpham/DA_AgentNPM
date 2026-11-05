// "Truck" mode props and motion: the npm registry warehouse, the user's machine (a developer and an AI
// coding assistant), the delivery truck and one parcel per package, plus the three outcome zones at
// the gate (ready-to-ship pallet, quarantine cage) and the review shelf at the reviewer's desk.
// State comes from truck.mjs (pure); this module only places and animates objects.
import * as THREE from "../vendor/three.module.min.js";
import { truck as truckMesh } from "./outdoor.mjs";
import { at, box, mesh, personMesh, robotMesh } from "./people.mjs";
import { desk, monitor, plant, rug, textures } from "./props.mjs";

export const SITES = {
  registry: { at: [60, 42], clearing: { minX: 47, maxX: 73, minZ: 30.5, maxZ: 52 } },
  house: { at: [-30, 43], clearing: { minX: -42, maxX: -18, minZ: 30.5, maxZ: 52 } },
};
const ACTION_COLORS = { approve: "#2fe0a8", review: "#ffaa1a", deny: "#ff4a3d" };
// Truck trips: registry -> main road (westbound lane) -> access road -> gate; gate -> user's house.
const TO_GATE = [[60, 36], [60, 23.8], [-42, 23.8], [-42, -3]];
const TO_HOUSE = [[-42, -3], [-42, 28.2], [-30, 28.2], [-30, 35.5]];
const ZONES = {
  stack: { origin: [-37.2, -0.7], columns: 3 },
  approved: { origin: [-32.3, 1.9], columns: 3 },
  quarantine: { origin: [-36.9, 2.7], columns: 3 },
  review: { origin: [-9.7, 4.0], columns: 4, shelf: true },
  reception: { origin: [-18.8, -6.6], columns: 1, height: 1.33 },
};

function polyline(points) {
  const nodes = points.map(([x, z]) => new THREE.Vector3(x, -0.33, z));
  const lengths = nodes.slice(1).map((node, index) => node.distanceTo(nodes[index]));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  return (progress) => {
    let distance = Math.max(0, Math.min(1, progress)) * total;
    for (let index = 0; index < lengths.length; index += 1) {
      if (distance <= lengths[index] || index === lengths.length - 1) {
        const from = nodes[index];
        const to = nodes[index + 1];
        const point = from.clone().lerp(to, Math.min(1, distance / lengths[index]));
        return { point, heading: Math.atan2(to.x - from.x, to.z - from.z) };
      }
      distance -= lengths[index];
    }
    return { point: nodes.at(-1).clone(), heading: 0 };
  };
}

function parcelMesh() {
  const group = new THREE.Group();
  group.add(box(0.6, 0.45, 0.5, "#c99a5b", { roughness: 0.9 }));
  group.add(at(box(0.62, 0.05, 0.1, "#e8e1d4", { shadow: false }), 0, 0.23, 0));
  const band = at(box(0.62, 0.12, 0.52, "#c99a5b", { emissive: "#000000", shadow: false }), 0, -0.05, 0);
  group.add(band);
  group.userData.band = band;
  return group;
}

function sign(text, color, width = 3.2) {
  const plane = mesh(new THREE.PlaneGeometry(width, width * 0.19), "#ffffff", { map: textures.sign(text, color), shadow: false });
  plane.material.emissive = new THREE.Color("#ffffff");
  plane.material.emissiveMap = plane.material.map;
  plane.material.emissiveIntensity = 0.85;
  return plane;
}

export function createLogistics({ scene, overlay }) {
  const group = new THREE.Group();
  scene.add(group);
  const tags = [];
  const tag = (className, text, accent, point) => {
    const element = overlay(className, text, accent);
    tags.push({ element, point });
    return element;
  };

  // npm registry warehouse, south of the road, with a driveway.
  const [rx, rz] = SITES.registry.at;
  group.add(at(box(16, 7, 10, "#7a8796", { roughness: 0.7 }), rx, 3.5, rz));
  group.add(at(box(16.6, 0.4, 10.6, "#4a5563"), rx, 7.2, rz));
  group.add(at(box(6, 4.6, 0.1, "#1a1f26"), rx, 2.3, rz - 5.02));
  for (let index = 0; index < 8; index += 1) group.add(at(box(0.9, 0.7, 0.8, ["#c99a5b", "#b98a4b", "#d9aa6b"][index % 3]), rx - 2.2 + (index % 4) * 1.2, 0.35 + Math.floor(index / 4) * 0.7, rz - 4.2));
  const registrySign = sign("npm REGISTRY", "#ff5a5f", 6);
  group.add(at(registrySign, rx, 5.8, rz - 5.06).rotateY(Math.PI));
  group.add(at(box(4, 0.04, 5.6, "#2b2f36", { shadow: false }), rx, -0.32, 33.6));
  tag("site-tag", "🏬 npm Registry — kho gói công khai", "#ff5a5f", [rx, 8.4, rz]);

  // The user's machine: a small house with a patio desk, the developer and the AI coding assistant.
  const [hx, hz] = SITES.house.at;
  group.add(at(box(9, 3.2, 7, "#e8e1d4"), hx, 1.6, hz + 1.5));
  const roof = at(mesh(new THREE.ConeGeometry(6.6, 2.6, 4), "#8a5a2b", { roughness: 0.8 }), hx, 4.5, hz + 1.5);
  roof.rotation.y = Math.PI / 4;
  roof.scale.set(1, 1, 0.8);
  group.add(roof);
  group.add(at(box(1.2, 2.1, 0.1, "#5b3a24"), hx + 2.6, 1.05, hz - 2.02));
  for (const x of [-2.6, -0.6]) group.add(at(box(1.3, 1, 0.08, "#ffe1a0", { emissive: "#ffd08a", emissiveIntensity: 0.7, shadow: false }), hx + x, 1.8, hz - 2.04));
  group.add(at(box(4, 0.04, 6, "#2b2f36", { shadow: false }), hx, -0.32, 33.8));
  // The patio sits on the west side, which the south-west camera can see (the north side hides behind the house).
  const [px, pz] = [hx - 7.4, hz + 1.2];
  group.add(at(rug(6, 4.4, "#3a4656"), px, -0.3, pz));
  const patio = new THREE.Group();
  patio.position.set(px, -0.33, pz);
  group.add(patio);
  const table = desk(1.8, 0.8, "#e8e1d4");
  patio.add(table);
  const laptop = monitor("#61e8c2", 0.7);
  laptop.position.set(0, 0.92, -0.15);
  patio.add(laptop);
  patio.add(at(plant(1.1), 2.6, 0, 1.4), at(plant(0.8), -2.6, 0, 1.6));
  const developer = personMesh({ shirt: "#2b7de9", hair: "short", hairColor: "#2b2420", glasses: true, hold: "none", skin: "#f2c9a0" });
  developer.person.position.set(px, -0.33, pz + 0.9);
  developer.person.rotation.y = Math.PI;
  group.add(developer.person);
  const assistant = robotMesh("#61e8c2", {});
  assistant.robot.scale.setScalar(0.85);
  assistant.robot.position.set(px + 1.8, -0.33, pz + 0.7);
  assistant.robot.rotation.y = Math.PI - 0.4;
  group.add(assistant.robot);
  tag("site-tag", "💻 Máy người dùng — đang vibe-code", "#61e8c2", [hx, 6.6, hz + 1.5]);
  tag("npc-tag", "🧑‍💻 Lập trình viên", "#b8cbd0", [px, 2.0, pz + 0.9]);
  tag("robot-tag", "🤖 Trợ lý AI lập trình", "#61e8c2", [px + 1.8, 2.0, pz + 0.7]);
  const houseScreen = overlay("room-screen", "", "#61e8c2");
  houseScreen.hidden = true;
  tags.push({ element: houseScreen, point: [px, 2.7, pz - 0.3] });

  // Outcome zones at the gate and the review shelf.
  const cage = new THREE.Group();
  const [cx, cz] = [ZONES.quarantine.origin[0] + 0.7, ZONES.quarantine.origin[1] + 0.9];
  for (const [dx, dz] of [[-1.3, -1.2], [1.3, -1.2], [-1.3, 1.2], [1.3, 1.2]]) cage.add(at(box(0.1, 1.5, 0.1, "#ff4a3d", { metalness: 0.5 }), dx, 0.75, dz));
  for (const [dx, dz, w, d] of [[0, -1.2, 2.6, 0.04], [0, 1.2, 2.6, 0.04], [-1.3, 0, 0.04, 2.4], [1.3, 0, 0.04, 2.4]]) {
    cage.add(at(box(w, 1.4, d, "#ff6b5e", { opacity: 0.22, shadow: false }), dx, 0.75, dz));
  }
  cage.add(at(sign("CÁCH LY", "#ff4a3d", 2.4), 0, 1.85, -1.25));
  cage.position.set(cx, 0, cz);
  group.add(cage);
  const pallet = new THREE.Group();
  pallet.add(at(box(2.4, 0.14, 2.2, "#9a6b4f"), 0, 0.07, 0));
  pallet.add(at(box(2.5, 0.04, 2.3, "#2fe0a8", { emissive: "#2fe0a8", emissiveIntensity: 0.6, shadow: false }), 0, 0.02, 0));
  pallet.add(at(sign("SẴN SÀNG GIAO", "#2fe0a8", 2.4), 0, 1.5, -1.2));
  pallet.position.set(ZONES.approved.origin[0] + 0.7, 0, ZONES.approved.origin[1] + 0.75);
  group.add(pallet);
  const shelf = new THREE.Group();
  shelf.add(at(box(2.9, 0.06, 0.7, "#5b4636"), 0, 0.3, 0), at(box(2.9, 0.06, 0.7, "#5b4636"), 0, 0.9, 0));
  for (const x of [-1.4, 1.4]) shelf.add(at(box(0.08, 1.4, 0.7, "#5b4636"), x, 0.7, 0));
  shelf.add(at(sign("CHỜ DUYỆT", "#ffaa1a", 2.2), 0, 1.75, -0.3));
  shelf.position.set(ZONES.review.origin[0] + 0.95, 0, ZONES.review.origin[1]);
  group.add(shelf);

  // The truck and its trips.
  const truck = truckMesh();
  group.add(truck);
  const toGate = polyline(TO_GATE);
  const toHouse = polyline(TO_HOUSE);
  const truckTag = tag("truck-tag", "🚚 Xe hàng", "#f4b860", null);
  const truckState = { leg: "toGate", progress: 1, target: { leg: "toGate", progress: 1 } };

  let parcels = [];
  function setup(names) {
    for (const parcel of parcels) { group.remove(parcel.mesh); parcel.tag.remove(); }
    parcels = names.map((name) => {
      const parcelBody = parcelMesh();
      parcelBody.visible = false;
      group.add(parcelBody);
      const element = overlay("parcel-tag", `📦 ${name}`, "#c99a5b");
      element.hidden = true;
      return { mesh: parcelBody, tag: element, zone: "truck", target: new THREE.Vector3(), action: null };
    });
  }

  // Slot n of a zone: a small grid, stacked in layers; the review shelf uses its two boards.
  function slot(zone, index) {
    const spec = ZONES[zone];
    if (spec.shelf) {
      const level = Math.floor(index / spec.columns) % 2;
      return new THREE.Vector3(spec.origin[0] + (index % spec.columns) * 0.65, 0.58 + level * 0.6, spec.origin[1]);
    }
    const column = index % spec.columns;
    const row = Math.floor(index / spec.columns) % 3;
    const layer = Math.floor(index / (spec.columns * 3));
    return new THREE.Vector3(spec.origin[0] + column * 0.7, (spec.height ?? 0.28) + layer * 0.48, spec.origin[1] + row * 0.75);
  }

  function setState({ phase, items, truckLabel, houseText }, instant = false) {
    const leg = phase.where === "toHouse" || phase.where === "house" ? "toHouse" : "toGate";
    const progress = phase.where === "registry" ? 0 : phase.where === "gate" ? 1 : phase.progress;
    truckState.target = { leg, progress };
    if (instant || truckState.leg !== leg) Object.assign(truckState, { leg, progress });
    truckTag.textContent = truckLabel || "🚚 Xe hàng";
    houseScreen.textContent = houseText || "";
    houseScreen.hidden = !houseText;
    const counters = {};
    items.forEach((item, index) => {
      const parcel = parcels[index];
      if (!parcel) return;
      const order = counters[item.zone] = (counters[item.zone] ?? -1) + 1;
      parcel.zone = item.zone;
      parcel.mesh.visible = item.zone !== "truck" && item.zone !== "loaded";
      if (parcel.mesh.visible) parcel.target.copy(slot(item.zone, item.zone === "reception" ? 0 : order));
      if (instant && parcel.mesh.visible) parcel.mesh.position.copy(parcel.target);
      if (!parcel.wasVisible && parcel.mesh.visible && !instant) parcel.mesh.position.copy(truck.position).add(new THREE.Vector3(0, 1.6, 0));
      parcel.wasVisible = parcel.mesh.visible;
      if (parcel.action !== item.action) {
        parcel.action = item.action;
        const band = parcel.mesh.userData.band.material;
        band.color.set(item.action ? ACTION_COLORS[item.action] : "#c99a5b");
        band.emissive.set(item.action ? ACTION_COLORS[item.action] : "#000000");
        band.emissiveIntensity = item.action ? 0.8 : 0;
      }
      parcel.tag.hidden = !parcel.mesh.visible;
      parcel.tag.classList.toggle("hot", Boolean(item.hot));
      parcel.tag.dataset.action = item.action || "";
    });
  }

  function placeTruck() {
    const { point, heading } = (truckState.leg === "toHouse" ? toHouse : toGate)(truckState.progress);
    truck.position.copy(point);
    truck.rotation.y = heading;
  }
  placeTruck();

  function update(delta, speed) {
    let moving = false;
    const target = truckState.target;
    if (Math.abs(target.progress - truckState.progress) > 0.0005) {
      truckState.progress += (target.progress - truckState.progress) * Math.min(1, delta * 3 * speed);
      moving = true;
    }
    placeTruck();
    for (const parcel of parcels) {
      if (!parcel.mesh.visible) continue;
      const distance = parcel.mesh.position.distanceTo(parcel.target);
      if (distance > 0.01) {
        parcel.mesh.position.lerp(parcel.target, Math.min(1, delta * 4 * speed));
        parcel.mesh.position.y += Math.min(0.6, distance * 0.08); // a small hop while it travels
        moving = true;
      }
    }
    return moving;
  }

  function placeTags(place) {
    for (const { element, point } of tags) {
      if (element.hidden) continue;
      place(element, point || [truck.position.x, 3.6, truck.position.z]);
    }
    for (const parcel of parcels) if (!parcel.tag.hidden) {
      const { x, y, z } = parcel.mesh.position;
      place(parcel.tag, [x, y + 0.55, z]);
    }
  }

  const headOf = (object, lift) => object.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, lift, 0));
  return {
    setup, setState, update, placeTags,
    truckPoint: () => truck.position.clone().add(new THREE.Vector3(0, 2.2, 0)),
    registryPoint: () => new THREE.Vector3(rx, 3, rz - 5.5),
    housePoint: () => headOf(assistant.robot, 1.6),
    developer, assistant,
  };
}
