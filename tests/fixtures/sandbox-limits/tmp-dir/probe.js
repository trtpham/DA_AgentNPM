// Harmless sandbox probe: makes a temp folder (EROFS before 2026-11-20), then tries to execute a file there.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
let folder;
try {
  folder = fs.mkdtempSync(path.join(os.tmpdir(), 'w5-'));
  console.log('W5RESULT mkdtemp=ok');
} catch (error) {
  console.log(`W5RESULT mkdtemp=${error.code}`);
  process.exit(0);
}
const file = path.join(folder, 'run.sh');
fs.writeFileSync(file, '#!/bin/sh\necho executed\n', { mode: 0o755 });
const result = spawnSync(file, { encoding: 'utf8' });
console.log(`W5RESULT exec=${result.error ? result.error.code : (result.stdout.includes('executed') ? 'ran' : 'other')}`);
