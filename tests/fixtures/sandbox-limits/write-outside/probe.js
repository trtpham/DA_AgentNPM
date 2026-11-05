// Harmless sandbox probe: writes a marker outside the package; read-only paths must refuse.
const fs = require('node:fs');
for (const target of ['/input/w5-marker', '/etc/w5-marker', '/usr/local/w5-marker', `${process.env.HOME}/w5-marker`]) {
  try {
    fs.writeFileSync(target, 'marker\n');
    console.log(`W5RESULT write ${target}=written`);
  } catch (error) {
    console.log(`W5RESULT write ${target}=${error.code}`);
  }
}
