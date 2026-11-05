// Harmless sandbox probe: tries one HTTPS request and one DNS lookup; both must fail offline.
const dns = require('node:dns');
const https = require('node:https');
dns.lookup('example.com', (error) => console.log(`W5RESULT dns=${error ? error.code : 'resolved'}`));
const request = https.get('https://93.184.215.14/', { timeout: 5000 }, () => console.log('W5RESULT https=connected'));
request.on('error', (error) => console.log(`W5RESULT https=${error.code}`));
request.on('timeout', () => { console.log('W5RESULT https=timeout'); request.destroy(); });
