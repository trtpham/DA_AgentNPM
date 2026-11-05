const https = require('node:https');

// Library code: only runs when the user calls it, not at install.
module.exports = (url) => new Promise((resolve) => https.get(url, resolve));
