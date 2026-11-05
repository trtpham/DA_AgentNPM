const fs = require('node:fs');
const path = require('node:path');

// Pick build options from npm config and CI variables; write them next to the package.
const options = {
  ci: Boolean(process.env.CI),
  debug: process.env.npm_config_debug === 'true',
  arch: process.env.npm_config_arch || process.arch,
};
fs.writeFileSync(path.join(__dirname, 'build-options.json'), JSON.stringify(options));
