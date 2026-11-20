"""FPS of the 3D office, see do-fps-van-phong-3d.md. Usage: py -3.14 viewer/docs/do_fps_van_phong.py <out-dir>

Write one playwright-cli run-code script per batch: each loads the office in truck mode for one demo
scenario and one theme, waits out the opening camera shot, presses play and samples real renders."""
import json, pathlib, sys

IDS = ["safe", "malicious-dep", "osv", "obfuscated", "native", "model-fail", "fake-evidence",
       "osv-disagree", "sandbox", "typosquat", "unreachable", "installed-before"]
out = pathlib.Path(sys.argv[1])
SAMPLE_MS = 8000

TEMPLATE = r"""async page => {
  const jobs = __JOBS__;
  const results = [];
  for (const [theme, id] of jobs) {
    await page.goto('http://localhost:8765/');
    await page.evaluate(t => localStorage.setItem('viewer.theme', t), theme);
    const started = Date.now();
    await page.goto(`http://localhost:8765/office?fps=${started}#mode=truck&scenario=${id}`);
    await page.waitForFunction(() => window.__office && document.getElementById('caption-who').textContent !== 'Đang tải…' &&
                               !document.getElementById('play').disabled, null, {timeout: 30000});
    const load = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const api = performance.getEntriesByType('resource').filter(e => e.name.includes('/api/'));
      return {domLoaded: Math.round(nav.domContentLoadedEventEnd), loaded: Math.round(nav.loadEventEnd),
              dataReady: Math.round(Math.max(0, ...api.map(e => e.responseEnd))), ready: Math.round(performance.now())};
    });
    await page.waitForTimeout(3200);                       // opening camera shot (2.8 s) finishes
    await page.selectOption('#rate', '4');                 // 4x: the sample falls inside the story, not after it
    await page.click('#play');
    await page.waitForTimeout(800);
    const sample = await page.evaluate(async (ms) => {
      const office = window.__office;
      const raf = [], renders = [];
      let lastRaf = performance.now(), lastFrames = office.stats.frames, lastRender = lastRaf;
      const end = lastRaf + ms;
      await new Promise(done => {
        function tick(now) {
          raf.push(now - lastRaf); lastRaf = now;
          if (office.stats.frames !== lastFrames) { renders.push(now - lastRender); lastRender = now; lastFrames = office.stats.frames; }
          if (now < end) requestAnimationFrame(tick); else done();
        }
        requestAnimationFrame(tick);
      });
      const info = office.info();
      return {raf, renders, clock: document.getElementById('clock').textContent, playing: document.getElementById('play').textContent,
              calls: info.calls, triangles: info.triangles, fxMemoryMB: info.fxMemoryMB, canvas: [document.getElementById('office-canvas').width, document.getElementById('office-canvas').height],
              visible: document.visibilityState, theme: document.documentElement.dataset.theme || 'auto'};
    }, __SAMPLE__);
    const pct = (list, p) => { const s = [...list].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))] || 0; };
    const fps = (list) => list.length ? 1000 * list.length / list.reduce((a, b) => a + b, 0) : 0;
    results.push({theme, id, load,
      renderFps: +fps(sample.renders).toFixed(1), renderP5: +(1000 / (pct(sample.renders, 0.95) || 1)).toFixed(1),
      renderMin: +(1000 / (Math.max(...sample.renders, 1))).toFixed(1), renders: sample.renders.length,
      rafFps: +fps(sample.raf.slice(1)).toFixed(1), rafP5: +(1000 / (pct(sample.raf.slice(1), 0.95) || 1)).toFixed(1),
      clock: sample.clock, playing: sample.playing.trim(), calls: sample.calls, triangles: sample.triangles,
      fxMemoryMB: sample.fxMemoryMB, canvas: sample.canvas, visible: sample.visible, themeSeen: sample.theme});
    await page.click('#play').catch(() => {});
  }
  return JSON.stringify(results);
}"""

jobs = [(theme, i) for theme in ["dark", "light"] for i in IDS]
out.mkdir(parents=True, exist_ok=True)
for n in range(0, len(jobs), 4):
    body = TEMPLATE.replace("__JOBS__", json.dumps(jobs[n:n + 4])).replace("__SAMPLE__", str(SAMPLE_MS))
    (out / f"batch{n // 4:02d}.js").write_text(body, encoding="utf-8")
print(len(jobs), "jobs in", (len(jobs) + 3) // 4, "batches")
