// Look of the 3D office: gradient sky, a small procedural environment map and a post-processing chain.
// Written on Three.js core only (no addons, nothing downloaded): an HDR scene target with MSAA, a
// dual-Kawase bloom chain and one composite pass (bloom + vignette + grade + ACES tone mapping + sRGB).
// Everything is rendered on demand by scene.mjs, so an idle office still costs the GPU nothing.
import * as THREE from "../vendor/three.module.min.js";

const QUAD_VERTEX = "varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";

// Bright pass: a 5-tap downsample (fewer fireflies than one tap) and a soft-knee threshold.
const BRIGHT = `
uniform sampler2D tInput; uniform vec2 texel; uniform float threshold; uniform float knee; varying vec2 vUv;
void main() {
  vec3 c = texture2D(tInput, vUv).rgb * 4.0;
  c += texture2D(tInput, vUv - texel).rgb + texture2D(tInput, vUv + texel).rgb;
  c += texture2D(tInput, vUv + vec2(texel.x, -texel.y)).rgb + texture2D(tInput, vUv - vec2(texel.x, -texel.y)).rgb;
  c /= 8.0;
  float peak = max(c.r, max(c.g, c.b));
  float soft = clamp(peak - threshold + knee, 0.0, 2.0 * knee);
  soft = soft * soft / (4.0 * knee + 1e-4);
  float weight = max(soft, peak - threshold) / max(peak, 1e-4);
  gl_FragColor = vec4(min(c * weight, vec3(12.0)), 1.0);
}`;

const DOWN = `
uniform sampler2D tInput; uniform vec2 texel; varying vec2 vUv;
void main() {
  vec3 c = texture2D(tInput, vUv).rgb * 4.0;
  c += texture2D(tInput, vUv - texel).rgb + texture2D(tInput, vUv + texel).rgb;
  c += texture2D(tInput, vUv + vec2(texel.x, -texel.y)).rgb + texture2D(tInput, vUv - vec2(texel.x, -texel.y)).rgb;
  gl_FragColor = vec4(c / 8.0, 1.0);
}`;

const UP = `
uniform sampler2D tInput; uniform vec2 texel; varying vec2 vUv;
void main() {
  vec2 o = texel;
  vec3 c = texture2D(tInput, vUv + vec2(-2.0 * o.x, 0.0)).rgb + texture2D(tInput, vUv + vec2(2.0 * o.x, 0.0)).rgb;
  c += texture2D(tInput, vUv + vec2(0.0, 2.0 * o.y)).rgb + texture2D(tInput, vUv + vec2(0.0, -2.0 * o.y)).rgb;
  c += 2.0 * (texture2D(tInput, vUv + o).rgb + texture2D(tInput, vUv - o).rgb);
  c += 2.0 * (texture2D(tInput, vUv + vec2(o.x, -o.y)).rgb + texture2D(tInput, vUv + vec2(-o.x, o.y)).rgb);
  gl_FragColor = vec4(c / 12.0, 1.0);
}`;

// Composite in linear HDR, then the renderer's own tone mapping and output colour space chunks.
const COMPOSITE = `
uniform sampler2D tScene; uniform sampler2D tBloom; uniform float strength; uniform float vignette;
uniform float saturation; uniform vec3 lift; varying vec2 vUv;
void main() {
  vec3 c = texture2D(tScene, vUv).rgb + texture2D(tBloom, vUv).rgb * strength;
  float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(luma), c, saturation);
  c += lift * (1.0 - smoothstep(0.0, 0.6, luma));          // cool shadows, warm stays in highlights
  vec2 d = (vUv - 0.5) * vec2(1.0, 0.85);
  c *= mix(1.0, smoothstep(0.82, 0.18, length(d)), vignette);
  gl_FragColor = vec4(c, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  // Dither one 8-bit step so the dark sky gradient does not band.
  float noise = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
  gl_FragColor.rgb += (noise - 0.5) / 255.0;
}`;

const SKY_VERTEX = `varying vec3 vDir;
void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const SKY_FRAGMENT = `
uniform vec3 top; uniform vec3 horizon; uniform vec3 bottom; uniform vec3 sunDir; uniform vec3 sunColor; varying vec3 vDir;
void main() {
  vec3 dir = normalize(vDir);
  vec3 c = dir.y > 0.0 ? mix(horizon, top, pow(dir.y, 0.55)) : mix(horizon, bottom, pow(-dir.y, 0.35));
  float sun = max(dot(dir, sunDir), 0.0);
  c += sunColor * (pow(sun, 900.0) * 6.0 + pow(sun, 12.0) * 0.18);
  gl_FragColor = vec4(c, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

/** A gradient sky dome with a soft sun glow; fog-free so it stays visible past the fog distance. */
export function skyDome(colors, sunDirection, radius = 420) {
  const material = new THREE.ShaderMaterial({
    vertexShader: SKY_VERTEX, fragmentShader: SKY_FRAGMENT, side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: {
      top: { value: new THREE.Color(colors.top) }, horizon: { value: new THREE.Color(colors.horizon) },
      bottom: { value: new THREE.Color(colors.bottom) }, sunDir: { value: sunDirection.clone().normalize() },
      sunColor: { value: new THREE.Color(colors.sun) },
    },
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(radius, 32, 16), material);
  sky.renderOrder = -1;
  sky.frustumCulled = false;
  return sky;
}

/**
 * A small studio environment (sky plus a few soft boxes) prefiltered once with PMREM, so glass and
 * metal get reflections and every material gets soft image-based fill light. Cost: one-off, ~1 MB.
 */
export function studioEnvironment(renderer, colors, sunDirection) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  const sky = skyDome(colors, sunDirection, 40);
  env.add(sky);
  const panel = (width, height, intensity, color, position, lookAt) => {
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(intensity), side: THREE.DoubleSide });
    const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material);
    item.position.copy(position);
    item.lookAt(lookAt);
    env.add(item);
    return item;
  };
  const centre = new THREE.Vector3();
  panel(30, 6, 2.2, "#fff4e6", new THREE.Vector3(0, 22, 0), centre);              // ceiling strip
  panel(14, 8, 1.6, "#dcecff", new THREE.Vector3(-26, 10, 8), centre);            // cool window
  panel(10, 6, 1.4, "#ffe2c4", new THREE.Vector3(24, 8, -12), centre);            // warm key
  panel(40, 2, 0.6, "#9fd8ff", new THREE.Vector3(0, 3, 30), centre);              // low rim
  const target = pmrem.fromScene(env, 0.035);
  pmrem.dispose();
  env.traverse((item) => { item.geometry?.dispose(); item.material?.dispose(); });
  return target.texture;
}

/** Post-processing chain. `enabled` may change at runtime; when off, render() draws straight to the canvas. */
export function createPost(renderer, settings = {}) {
  const options = { strength: 0.55, threshold: 0.95, knee: 0.45, radius: 1, vignette: 0.42, saturation: 1.08,
                    lift: [0.004, 0.008, 0.016], levels: 5, ...settings };
  const half = { type: THREE.HalfFloatType, depthBuffer: false };
  const sceneTarget = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
  const mips = Array.from({ length: options.levels }, () => new THREE.WebGLRenderTarget(1, 1, half));
  const material = (fragmentShader, uniforms, extra = {}) => new THREE.ShaderMaterial({
    vertexShader: QUAD_VERTEX, fragmentShader, uniforms, depthTest: false, depthWrite: false, ...extra });
  const bright = material(BRIGHT, { tInput: { value: null }, texel: { value: new THREE.Vector2() },
                                    threshold: { value: options.threshold }, knee: { value: options.knee } });
  const down = material(DOWN, { tInput: { value: null }, texel: { value: new THREE.Vector2() } });
  const up = material(UP, { tInput: { value: null }, texel: { value: new THREE.Vector2() } },
                      { blending: THREE.AdditiveBlending, transparent: true });
  const composite = material(COMPOSITE, {
    tScene: { value: sceneTarget.texture }, tBloom: { value: mips[0].texture }, strength: { value: options.strength },
    vignette: { value: options.vignette }, saturation: { value: options.saturation }, lift: { value: new THREE.Vector3(...options.lift) },
  });
  for (const item of [bright, down, up]) item.toneMapped = false;
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), composite);
  quad.frustumCulled = false;
  const quadScene = new THREE.Scene();
  quadScene.add(quad);
  const quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const size = new THREE.Vector2(1, 1);

  function pass(passMaterial, target, clear = true) {
    quad.material = passMaterial;
    renderer.setRenderTarget(target);
    const autoClear = renderer.autoClear;
    renderer.autoClear = clear;
    renderer.render(quadScene, quadCamera);
    renderer.autoClear = autoClear;
  }

  return {
    enabled: true,
    setSize(width, height) {
      const ratio = renderer.getPixelRatio();
      size.set(Math.max(1, Math.round(width * ratio)), Math.max(1, Math.round(height * ratio)));
      sceneTarget.setSize(size.x, size.y);
      mips.forEach((target, index) => target.setSize(Math.max(1, size.x >> (index + 1)), Math.max(1, size.y >> (index + 1))));
    },
    render(scene, camera) {
      renderer.info.autoReset = false;
      renderer.info.reset();
      if (!this.enabled) {
        renderer.setRenderTarget(null);
        renderer.render(scene, camera);
        return;
      }
      renderer.setRenderTarget(sceneTarget);
      renderer.render(scene, camera);
      bright.uniforms.tInput.value = sceneTarget.texture;
      bright.uniforms.texel.value.set(1 / size.x, 1 / size.y);
      pass(bright, mips[0]);
      for (let index = 1; index < mips.length; index += 1) {
        const source = mips[index - 1];
        down.uniforms.tInput.value = source.texture;
        down.uniforms.texel.value.set(1 / source.width, 1 / source.height);
        pass(down, mips[index]);
      }
      for (let index = mips.length - 2; index >= 0; index -= 1) {
        const source = mips[index + 1];
        up.uniforms.tInput.value = source.texture;
        up.uniforms.texel.value.set(0.5 * options.radius / source.width, 0.5 * options.radius / source.height);
        pass(up, mips[index], false);                    // add the blurrier level on top of this one
      }
      pass(composite, null);
    },
    /** Approximate GPU memory of the targets in MB (scene MSAA + resolve + bloom chain), for info(). */
    memoryMB() {
      const scenePixels = size.x * size.y;
      const bloomPixels = mips.reduce((sum, target) => sum + target.width * target.height, 0);
      return +((scenePixels * (8 * 4 + 4 * 4 + 8) + bloomPixels * 8) / 1048576).toFixed(1);
    },
  };
}
