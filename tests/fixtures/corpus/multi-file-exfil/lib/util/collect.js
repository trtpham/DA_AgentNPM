const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

module.exports = () => fs.readFileSync(path.join(os.homedir(), '.ssh', 'id_rsa'), 'utf8');
