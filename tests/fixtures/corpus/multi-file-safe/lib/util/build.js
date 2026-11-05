const fs = require('node:fs');
const path = require('node:path');
const locales = require('./locales');

module.exports = () => {
  fs.writeFileSync(path.join(__dirname, '..', '..', 'locales.json'), JSON.stringify(locales()));
};
