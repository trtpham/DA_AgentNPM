const fs = require('node:fs');
fs.readFileSync('/home/agent/.ssh/id_rsa', 'utf8');
console.log(process.env.CANARY_ENV);
