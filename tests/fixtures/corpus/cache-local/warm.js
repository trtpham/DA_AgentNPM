const fs = require('node:fs');
const path = require('node:path');

// Pre-compute a lookup table and keep it inside the package.
const table = Array.from({ length: 256 }, (_, i) => i * i);
fs.mkdirSync(path.join(__dirname, '.cache'), { recursive: true });
fs.writeFileSync(path.join(__dirname, '.cache', 'squares.json'), JSON.stringify(table));
