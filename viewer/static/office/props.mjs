// Office furniture and canvas-drawn textures. Every texture is painted here from fixed text and shapes;
// nothing is downloaded and no trace or package text is ever painted into a texture.
import * as THREE from "../vendor/three.module.min.js";
import { at, box, mesh } from "./people.mjs";

function canvasTexture(width, height, paint, repeat = [1, 1]) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  paint(canvas.getContext("2d"), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  if (repeat[0] !== 1 || repeat[1] !== 1) {
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(...repeat);
  }
  return texture;
}

// A small deterministic random so textures look the same on every load.
function seeded(seed) {
  let value = seed;
  return () => { value = (value * 16807) % 2147483647; return (value - 1) / 2147483646; };
}

export const textures = {
  wood: (repeat) => canvasTexture(256, 256, (g, w, h) => {
    const random = seeded(7);
    for (let row = 0; row < 8; row += 1) {
      const tone = 120 + Math.floor(random() * 30);
      g.fillStyle = `rgb(${tone + 40},${tone + 8},${tone - 30})`;
      g.fillRect(0, row * 32, w, 32);
      g.strokeStyle = "rgba(60,35,15,.45)";
      g.strokeRect(0, row * 32, w, 32);
      const joint = Math.floor(random() * w);
      g.beginPath(); g.moveTo(joint, row * 32); g.lineTo(joint, row * 32 + 32); g.stroke();
      g.strokeStyle = "rgba(80,50,25,.18)";
      for (let line = 0; line < 4; line += 1) { g.beginPath(); g.moveTo(0, row * 32 + 6 + line * 7); g.bezierCurveTo(w / 3, row * 32 + random() * 30, w * 2 / 3, row * 32 + random() * 30, w, row * 32 + 6 + line * 7); g.stroke(); }
    }
  }, repeat),
  carpet: (color, repeat) => canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = color; g.fillRect(0, 0, w, h);
    const random = seeded(11);
    for (let index = 0; index < 1400; index += 1) {
      g.fillStyle = `rgba(255,255,255,${random() * 0.07})`;
      g.fillRect(random() * w, random() * h, 1.5, 1.5);
      g.fillStyle = `rgba(0,0,0,${random() * 0.12})`;
      g.fillRect(random() * w, random() * h, 1.5, 1.5);
    }
  }, repeat),
  tiles: (repeat) => canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = "#cfd6dc"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#b9c2ca"; g.fillRect(0, 0, w / 2, h / 2); g.fillRect(w / 2, h / 2, w / 2, h / 2);
    g.strokeStyle = "#9aa6b1"; g.lineWidth = 2; g.strokeRect(0, 0, w, h); g.strokeRect(0, 0, w / 2, h / 2); g.strokeRect(w / 2, h / 2, w / 2, h / 2);
  }, repeat),
  code: (accent) => canvasTexture(256, 160, (g, w, h) => {
    g.fillStyle = "#0b1220"; g.fillRect(0, 0, w, h);
    const random = seeded(accent.length * 13);
    const colors = [accent, "#e8f4ff", "#ffd08a", "#b79cff", "#7a8a99"];
    for (let line = 0; line < 12; line += 1) {
      let x = 10 + (line % 4 === 0 ? 0 : 14 * (1 + Math.floor(random() * 2)));
      while (x < w - 20) {
        const length = 10 + random() * 46;
        g.fillStyle = colors[Math.floor(random() * colors.length)];
        g.fillRect(x, 8 + line * 12.5, length, 5);
        x += length + 6;
        if (random() < 0.25) break;
      }
    }
  }),
  poster: (title, lines, accent) => canvasTexture(256, 340, (g, w, h) => {
    g.fillStyle = "#f4f1ea"; g.fillRect(0, 0, w, h);
    g.fillStyle = accent; g.fillRect(0, 0, w, 64);
    g.fillStyle = "#09111d"; g.font = "bold 24px Segoe UI, Arial"; g.textAlign = "center";
    g.fillText(title, w / 2, 42);
    g.font = "18px Segoe UI, Arial"; g.fillStyle = "#26384a";
    lines.forEach((line, index) => g.fillText(line, w / 2, 110 + index * 34));
    g.strokeStyle = accent; g.lineWidth = 6; g.strokeRect(3, 3, w - 6, h - 6);
  }),
  whiteboard: () => canvasTexture(512, 256, (g, w, h) => {
    g.fillStyle = "#fbfbf7"; g.fillRect(0, 0, w, h);
    g.font = "bold 26px Segoe UI, Arial"; g.textAlign = "center";
    const steps = [["NGUỒN", "#2b7de9"], ["HÀNH ĐỘNG", "#e0892b"], ["ĐÍCH", "#d6453d"]];
    steps.forEach(([label, color], index) => {
      const x = 90 + index * 165;
      g.strokeStyle = color; g.lineWidth = 4; g.strokeRect(x - 70, 70, 140, 70);
      g.fillStyle = color; g.fillText(label, x, 115);
      if (index < 2) { g.beginPath(); g.moveTo(x + 74, 105); g.lineTo(x + 92, 105); g.stroke(); g.fillText("→", x + 83, 114); }
    });
    g.fillStyle = "#26384a"; g.font = "20px Segoe UI, Arial";
    g.fillText("đọc ~/.npmrc  →  mã hóa  →  gửi HTTP máy chủ lạ ?", w / 2, 190);
    g.fillText("Không có file:dòng thì không kết luận", w / 2, 225);
  }),
  skyline: () => canvasTexture(1024, 256, (g, w, h) => {
    const sky = g.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, "#0d1b2e"); sky.addColorStop(1, "#24476a");
    g.fillStyle = sky; g.fillRect(0, 0, w, h);
    const random = seeded(5);
    for (let x = 0; x < w;) {
      const width = 30 + random() * 70;
      const height = 60 + random() * 160;
      g.fillStyle = `rgb(${18 + random() * 14},${30 + random() * 18},${46 + random() * 20})`;
      g.fillRect(x, h - height, width, height);
      for (let y = h - height + 8; y < h - 8; y += 12) {
        for (let wx = x + 5; wx < x + width - 6; wx += 10) {
          if (random() < 0.45) { g.fillStyle = random() < 0.8 ? "rgba(255,214,140,.85)" : "rgba(140,210,255,.8)"; g.fillRect(wx, y, 4, 6); }
        }
      }
      x += width + 4;
    }
  }),
  sign: (text, accent) => canvasTexture(512, 96, (g, w, h) => {
    g.fillStyle = "#0b1622"; g.fillRect(0, 0, w, h);
    g.fillStyle = accent; g.font = "bold 46px Segoe UI, Arial"; g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = accent; g.shadowBlur = 14; g.fillText(text, w / 2, h / 2 + 2);
  }),
};

// --- furniture ---------------------------------------------------------------------------------
export function plant(size = 1) {
  const group = new THREE.Group();
  group.add(at(mesh(new THREE.CylinderGeometry(0.22, 0.17, 0.35, 10), "#9a6b4f"), 0, 0.18, 0));
  group.add(at(mesh(new THREE.IcosahedronGeometry(0.38, 0), "#3f9a6b", { roughness: 1 }), 0, 0.62, 0));
  group.add(at(mesh(new THREE.IcosahedronGeometry(0.26, 0), "#57b884", { roughness: 1 }), 0.15, 0.9, 0.05));
  group.add(at(mesh(new THREE.IcosahedronGeometry(0.2, 0), "#2f7d55", { roughness: 1 }), -0.14, 0.82, -0.08));
  group.scale.setScalar(size);
  return group;
}

export function chair(color = "#26384a") {
  const group = new THREE.Group();
  group.add(at(box(0.5, 0.08, 0.5, color), 0, 0.45, 0));
  group.add(at(box(0.5, 0.5, 0.08, color), 0, 0.72, 0.22));
  group.add(at(mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.42, 6), "#1a1f26"), 0, 0.21, 0));
  for (let index = 0; index < 5; index += 1) {
    const angle = index / 5 * Math.PI * 2;
    group.add(at(box(0.04, 0.03, 0.26, "#1a1f26", { shadow: false }), Math.cos(angle) * 0.12, 0.03, Math.sin(angle) * 0.12).rotateY(-angle));
  }
  return group;
}

export function desk(width = 1.6, depth = 0.8, top = "#c9b48f") {
  const group = new THREE.Group();
  group.add(at(box(width, 0.06, depth, top), 0, 0.75, 0));
  for (const x of [-1, 1]) group.add(at(box(0.06, 0.72, depth - 0.1, "#26384a"), x * (width / 2 - 0.06), 0.37, 0));
  return group;
}

export function monitor(accent, wide = 0.9) {
  const group = new THREE.Group();
  const screen = box(wide, wide * 0.6, 0.05, "#0b1220", { map: textures.code(accent), emissive: "#ffffff", emissiveIntensity: 0.35 });
  screen.material.emissiveMap = screen.material.map;
  group.add(at(screen, 0, 0.36, 0));
  group.add(at(box(0.07, 0.3, 0.07, "#26384a"), 0, 0.02, -0.04));
  group.add(at(box(0.32, 0.03, 0.2, "#26384a"), 0, -0.13, -0.04));
  group.userData.screen = screen;
  return group;
}

export function workstation(accent) {
  const group = desk();
  const display = monitor(accent);
  display.position.set(0, 0.92, -0.22);
  group.add(display);
  group.add(at(box(0.5, 0.03, 0.18, "#26384a"), 0, 0.8, 0.1));
  group.add(at(mesh(new THREE.CylinderGeometry(0.05, 0.04, 0.1, 10), "#f4f1ea"), 0.55, 0.83, 0.15));
  const seat = chair();
  seat.position.set(0, 0, 0.75);
  seat.rotation.y = Math.PI;
  group.add(seat);
  group.userData.screen = display.userData.screen;
  return group;
}

export function shelf(accent) {
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

export function sofa(color) {
  const group = new THREE.Group();
  group.add(at(box(2, 0.4, 0.9, color), 0, 0.25, 0));
  group.add(at(box(2, 0.6, 0.22, color), 0, 0.6, -0.36));
  for (const x of [-1, 1]) group.add(at(box(0.22, 0.55, 0.9, color), x * 0.98, 0.42, 0));
  for (const x of [-0.5, 0.5]) group.add(at(box(0.85, 0.12, 0.7, new THREE.Color(color).offsetHSL(0, 0, 0.08)), x, 0.5, 0.05));
  return group;
}

export function serverRack(accent) {
  const group = new THREE.Group();
  group.add(at(box(0.9, 2.2, 0.8, "#1a2230", { metalness: 0.4, roughness: 0.4 }), 0, 1.1, 0));
  const leds = [];
  for (let unit = 0; unit < 9; unit += 1) {
    group.add(at(box(0.8, 0.16, 0.02, "#2b3646", { shadow: false }), 0, 0.35 + unit * 0.21, 0.41));
    for (let index = 0; index < 4; index += 1) {
      const led = box(0.04, 0.04, 0.02, accent, { emissive: accent, emissiveIntensity: 0.4, shadow: false });
      leds.push(at(led, -0.3 + index * 0.07, 0.35 + unit * 0.21, 0.43));
      group.add(led);
    }
  }
  group.userData.leds = leds;
  return group;
}

export function coffeeBar() {
  const group = new THREE.Group();
  group.add(at(box(2.6, 0.95, 0.7, "#5b4636", { roughness: 0.5 }), 0, 0.48, 0));
  group.add(at(box(2.7, 0.06, 0.8, "#e8e1d4"), 0, 0.98, 0));
  const machine = new THREE.Group();
  machine.add(at(box(0.5, 0.55, 0.4, "#c9cdd2", { metalness: 0.6, roughness: 0.3 }), 0, 0.28, 0));
  machine.add(at(box(0.3, 0.12, 0.05, "#1a1f26", { emissive: "#ffd08a", emissiveIntensity: 0.8, shadow: false }), 0, 0.42, 0.21));
  machine.position.set(-0.7, 1.01, -0.05);
  group.add(machine);
  for (const x of [0.3, 0.55, 0.8]) group.add(at(mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.13, 10), "#f4f1ea"), x, 1.08, 0.1));
  return group;
}

export function waterCooler() {
  const group = new THREE.Group();
  group.add(at(box(0.45, 1, 0.45, "#e8eef3"), 0, 0.5, 0));
  group.add(at(mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.5, 14), "#9fd8ff", { opacity: 0.55, roughness: 0.1 }), 0, 1.25, 0));
  return group;
}

export function printer() {
  const group = new THREE.Group();
  group.add(at(box(0.8, 0.7, 0.6, "#9aa8b5"), 0, 0.35, 0));
  group.add(at(box(0.75, 0.32, 0.55, "#dde5ec"), 0, 0.86, 0));
  group.add(at(box(0.5, 0.02, 0.3, "#f4f1ea", { shadow: false }), 0, 1.03, 0.1));
  group.add(at(box(0.12, 0.06, 0.02, "#61e8c2", { emissive: "#61e8c2", emissiveIntensity: 1, shadow: false }), 0.25, 0.9, 0.28));
  return group;
}

export function wallPoster(title, lines, accent, width = 1.1) {
  return box(width, width * 1.33, 0.03, "#ffffff", { map: textures.poster(title, lines, accent), shadow: false });
}

export function barrierGate() {
  const group = new THREE.Group();
  group.add(at(box(0.35, 1.1, 0.35, "#26384a", { metalness: 0.4 }), 0, 0.55, 0));
  const lamp = at(mesh(new THREE.SphereGeometry(0.11, 12, 10), "#ffd08a", { emissive: "#ffd08a", emissiveIntensity: 0.6, shadow: false }), 0, 1.2, 0);
  group.add(lamp);
  const arm = new THREE.Group();
  arm.position.set(0, 0.95, 0);
  const stripes = new THREE.Group();
  for (let index = 0; index < 6; index += 1) stripes.add(at(box(0.4, 0.1, 0.08, index % 2 ? "#f4f1ea" : "#ff5a4f", { shadow: false }), 0.2 + index * 0.4, 0, 0));
  arm.add(stripes);
  group.add(arm);
  group.userData = { arm, lamp };
  return group;
}

export function ceilingLight(width = 1.8) {
  const panel = box(width, 0.05, 0.4, "#ffffff", { emissive: "#fff6e0", emissiveIntensity: 1.4, shadow: false });
  return panel;
}

export function rug(width, depth, color) {
  return box(width, 0.02, depth, color, { map: textures.carpet(color, [2, 2]), shadow: false });
}
