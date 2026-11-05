// Characters built from primitives: people (AI models and staff) and robots (deterministic code).
import * as THREE from "../vendor/three.module.min.js";

export function mesh(geometry, color, options = {}) {
  const material = new THREE.MeshStandardMaterial({
    color, roughness: options.roughness ?? 0.8, metalness: options.metalness ?? 0,
    transparent: (options.opacity ?? 1) < 1, opacity: options.opacity ?? 1,
    emissive: options.emissive ?? 0x000000, emissiveIntensity: options.emissiveIntensity ?? 1,
    map: options.map ?? null,
  });
  const item = new THREE.Mesh(geometry, material);
  item.castShadow = options.shadow ?? true;
  item.receiveShadow = true;
  return item;
}
export const box = (w, h, d, color, options) => mesh(new THREE.BoxGeometry(w, h, d), color, options);
export const at = (item, x, y, z) => { item.position.set(x, y, z); return item; };

const SKIN = ["#f2c9a0", "#d9a77c", "#b97f55", "#f5d3b3", "#8d5a3b"];

/**
 * A person. Options: shirt, pants, skin, hair ("short"|"long"|"bun"|"cap"|"bald"|"helmet"), hairColor,
 * vest (color), apron (color), glasses, tie (color), badge (color), hold ("folder"|"clipboard"|"mop"|"cup"|"tablet"|"none").
 */
export function personMesh(options = {}) {
  const person = new THREE.Group();
  const shirt = new THREE.Color(options.shirt || "#61e8c2");
  const pants = options.pants || "#26384a";
  const skin = options.skin || SKIN[0];
  const legs = [];
  const arms = [];
  for (const side of [-1, 1]) {
    const leg = new THREE.Group();
    leg.position.set(side * 0.13, 0.66, 0);
    leg.add(at(box(0.17, 0.58, 0.19, pants), 0, -0.3, 0));
    leg.add(at(box(0.19, 0.09, 0.3, "#1a1f26"), 0, -0.62, 0.05)); // shoe
    person.add(leg);
    legs.push(leg);
    const arm = new THREE.Group();
    arm.position.set(side * 0.37, 1.32, 0);
    arm.add(at(box(0.13, 0.42, 0.15, shirt), 0, -0.2, 0));
    arm.add(at(mesh(new THREE.SphereGeometry(0.075, 10, 8), skin), 0, -0.46, 0)); // hand
    person.add(arm);
    arms.push(arm);
  }
  person.add(at(box(0.36, 0.1, 0.22, "#1a1f26", { shadow: false }), 0, 0.7, 0)); // belt
  const torso = at(mesh(new THREE.CapsuleGeometry(0.28, 0.36, 4, 12), shirt, { roughness: 0.65 }), 0, 1.06, 0);
  torso.scale.set(1, 1, 0.78);
  person.add(torso);
  if (options.tie) person.add(at(box(0.07, 0.34, 0.03, options.tie, { shadow: false }), 0, 1.12, 0.22));
  if (options.vest) {
    const vest = at(mesh(new THREE.CapsuleGeometry(0.3, 0.3, 4, 12), options.vest, { roughness: 0.7 }), 0, 1.06, 0);
    vest.scale.set(1.04, 0.95, 0.82);
    person.add(vest);
    person.add(at(box(0.5, 0.05, 0.02, "#e8f4ff", { emissive: "#e8f4ff", emissiveIntensity: 0.6, shadow: false }), 0, 1.0, 0.25));
  }
  if (options.apron) person.add(at(box(0.44, 0.62, 0.03, options.apron, { shadow: false }), 0, 0.92, 0.23));
  if (options.badge) {
    person.add(at(box(0.13, 0.16, 0.02, options.badge, { emissive: options.badge, emissiveIntensity: 0.5, shadow: false }), 0.12, 1.2, 0.23));
  }
  person.add(at(mesh(new THREE.CylinderGeometry(0.08, 0.09, 0.12, 10), skin), 0, 1.47, 0)); // neck
  const head = new THREE.Group();
  head.position.set(0, 1.72, 0);
  head.add(mesh(new THREE.SphereGeometry(0.23, 18, 14), skin, { roughness: 0.7 }));
  for (const side of [-1, 1]) head.add(at(mesh(new THREE.SphereGeometry(0.028, 8, 6), "#1a1f26", { shadow: false }), side * 0.08, 0.02, 0.21));
  const hairColor = options.hairColor || "#2b2420";
  const hair = options.hair || "short";
  if (hair === "short" || hair === "long" || hair === "bun") {
    head.add(at(mesh(new THREE.SphereGeometry(0.245, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2.1), hairColor), 0, 0.03, -0.01));
  }
  if (hair === "long") head.add(at(box(0.44, 0.42, 0.14, hairColor), 0, -0.14, -0.15));
  if (hair === "bun") head.add(at(mesh(new THREE.SphereGeometry(0.11, 12, 10), hairColor), 0, 0.2, -0.17));
  if (hair === "cap" || hair === "helmet") {
    const color = options.capColor || (hair === "helmet" ? "#ffd08a" : "#26384a");
    head.add(at(mesh(new THREE.SphereGeometry(0.255, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), color, { roughness: 0.5 }), 0, 0.04, 0));
    head.add(at(box(0.3, 0.03, 0.2, color), 0, 0.06, 0.24));
  }
  if (options.glasses) {
    for (const side of [-1, 1]) {
      const lens = at(mesh(new THREE.TorusGeometry(0.055, 0.012, 6, 14), "#1a1f26", { shadow: false }), side * 0.085, 0.02, 0.215);
      head.add(lens);
    }
    head.add(at(box(0.06, 0.012, 0.012, "#1a1f26", { shadow: false }), 0, 0.03, 0.22));
  }
  person.add(head);

  let held = null;
  const hold = options.hold || "folder";
  if (hold === "folder") held = at(box(0.32, 0.4, 0.05, "#ffd08a"), 0.42, 0.95, 0.18);
  if (hold === "clipboard") { held = at(box(0.28, 0.36, 0.03, "#c9b48f"), 0.4, 1.0, 0.2); held.add(at(box(0.22, 0.26, 0.01, "#f4f1ea", { shadow: false }), 0, -0.02, 0.02)); }
  if (hold === "tablet") held = at(box(0.3, 0.22, 0.03, "#1a1f26", { emissive: "#7cc4ff", emissiveIntensity: 0.4 }), 0.38, 1.0, 0.22);
  if (hold === "cup") held = at(mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.14, 10), "#f4f1ea"), 0.4, 0.92, 0.12);
  if (hold === "mop") {
    held = new THREE.Group();
    held.add(at(mesh(new THREE.CylinderGeometry(0.025, 0.025, 1.5, 6), "#9a6b4f"), 0, 0.2, 0));
    held.add(at(box(0.36, 0.08, 0.14, "#7cc4ff"), 0, -0.55, 0));
    held.position.set(0.48, 0.75, 0.18);
    held.rotation.z = 0.15;
  }
  if (held) person.add(held);
  return { person, legs, arms, head, held, torso, shirt };
}

/** A robot: deterministic code. Options: gavel, clipboard, magnifier, book, shield, robe (color). */
export function robotMesh(accent, options = {}) {
  const robot = new THREE.Group();
  const metal = { metalness: 0.55, roughness: 0.35 };
  robot.add(at(box(0.22, 0.55, 0.22, "#5c6b7a", metal), -0.17, 0.28, 0), at(box(0.22, 0.55, 0.22, "#5c6b7a", metal), 0.17, 0.28, 0));
  if (options.robe) {
    robot.add(at(mesh(new THREE.ConeGeometry(0.62, 1.25, 16, 1, true), options.robe, { roughness: 0.9 }), 0, 0.72, 0));
  }
  robot.add(at(box(0.78, 0.72, 0.5, "#c9d3dc", metal), 0, 0.92, 0));
  const chest = at(box(0.4, 0.2, 0.04, accent, { emissive: accent, emissiveIntensity: 0.8, shadow: false }), 0, 1.0, 0.26);
  robot.add(chest);
  const head = new THREE.Group();
  head.position.set(0, 1.5, 0);
  head.add(box(0.56, 0.42, 0.46, "#dde5ec", metal));
  for (const side of [-1, 1]) head.add(at(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.06, 12), "#9aa8b5", metal), side * 0.3, 0, 0).rotateZ(Math.PI / 2));
  const visor = box(0.44, 0.14, 0.04, accent, { emissive: accent, emissiveIntensity: 1.2, shadow: false });
  head.add(at(visor, 0, 0.02, 0.24));
  head.add(at(mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.26, 6), "#5c6b7a"), 0, 0.33, 0));
  const bulb = at(mesh(new THREE.SphereGeometry(0.07, 10, 8), accent, { emissive: accent, emissiveIntensity: 1.5, shadow: false }), 0, 0.48, 0);
  head.add(bulb);
  if (options.robe) head.add(at(box(0.62, 0.12, 0.52, "#1a1f26"), 0, 0.27, 0)); // judge cap
  robot.add(head);
  const arms = [];
  for (const side of [-1, 1]) {
    const arm = new THREE.Group();
    arm.position.set(side * 0.5, 1.2, 0);
    arm.add(at(box(0.16, 0.55, 0.16, "#9aa8b5", metal), 0, -0.27, 0));
    arm.add(at(mesh(new THREE.SphereGeometry(0.1, 10, 8), "#5c6b7a", metal), 0, -0.58, 0));
    robot.add(arm);
    arms.push(arm);
  }
  const tool = new THREE.Group();
  tool.position.set(0, -0.58, 0.12);
  if (options.gavel) {
    tool.add(at(mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.55, 6), "#7a5236"), 0, 0.05, 0));
    const hammer = at(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.3, 10), "#5b3a24", { roughness: 0.5 }), 0, -0.22, 0);
    hammer.rotation.z = Math.PI / 2;
    tool.add(hammer);
  }
  if (options.clipboard) { tool.add(box(0.3, 0.38, 0.03, "#c9b48f")); tool.add(at(box(0.24, 0.28, 0.01, "#f4f1ea", { shadow: false }), 0, -0.02, 0.02)); }
  if (options.magnifier) {
    tool.add(at(mesh(new THREE.TorusGeometry(0.13, 0.025, 8, 18), "#c9cdd2", metal), 0, 0.1, 0));
    tool.add(at(mesh(new THREE.CircleGeometry(0.12, 18), "#9fd8ff", { opacity: 0.4, shadow: false }), 0, 0.1, 0.005));
    tool.add(at(mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.25, 6), "#5b3a24"), 0, -0.12, 0));
  }
  if (options.book) tool.add(box(0.32, 0.4, 0.09, "#b79cff"));
  if (options.shield) {
    const shield = mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.05, 6), "#ffd08a", { metalness: 0.5, roughness: 0.4 });
    shield.rotation.x = Math.PI / 2;
    tool.add(shield);
  }
  arms[1].add(tool);
  return { robot, head, visor, bulb, arms, chest, accent: new THREE.Color(accent) };
}
