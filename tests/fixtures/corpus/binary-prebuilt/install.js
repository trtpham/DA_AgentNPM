const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const crypto = require('node:crypto');

// Download the prebuilt native addon for this platform into the package folder.
const target = path.join(__dirname, 'build', `addon-${process.platform}-${process.arch}.node`);
const url = `https://github.com/sim-org/fast-image/releases/download/v3.1.0/addon-${process.platform}-${process.arch}.node`;
const expected = require('./checksums.json')[`${process.platform}-${process.arch}`];
fs.mkdirSync(path.dirname(target), { recursive: true });
https.get(url, (response) => {
  const chunks = [];
  response.on('data', (chunk) => chunks.push(chunk));
  response.on('end', () => {
    const body = Buffer.concat(chunks);
    const digest = crypto.createHash('sha256').update(body).digest('hex');
    if (digest !== expected) throw new Error('checksum mismatch');
    fs.writeFileSync(target, body);
  });
});
