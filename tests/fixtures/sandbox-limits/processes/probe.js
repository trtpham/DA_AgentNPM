// Harmless sandbox probe: starts up to 200 short `sleep` children; the PID limit must stop it.
const { spawn } = require('node:child_process');
let started = 0;
let refused = 0;
for (let i = 0; i < 200; i += 1) {
  try {
    const child = spawn('sleep', ['3']);
    child.on('error', () => { refused += 1; });
    started += 1;
  } catch (error) {
    refused += 1;
  }
}
setTimeout(() => console.log(`W5RESULT spawned=${started} refused=${refused}`), 1000);
