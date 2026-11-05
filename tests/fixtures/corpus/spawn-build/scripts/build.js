const { spawnSync } = require('node:child_process');
const path = require('node:path');

// Compile the bundled TypeScript sources with the package's own compiler script.
const result = spawnSync(process.execPath, [path.join(__dirname, 'tsc-lite.js'), '--outDir', 'dist'], {
  cwd: path.join(__dirname, '..'),
  stdio: 'inherit',
});
process.exitCode = result.status;
