const fs = require('node:fs');
const path = require('node:path');

// Write a build marker next to the package.
fs.writeFileSync(path.join(__dirname, 'build-marker.txt'), 'built');
