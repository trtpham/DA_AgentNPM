const fs = require('node:fs');
const path = require('node:path');

// The icon font ships inline to keep the tarball small; decode it into the package folder.
const FONT = 'U0lNRk9OVAAAAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYn';
fs.writeFileSync(path.join(__dirname, 'icons.woff2'), Buffer.from(FONT, 'base64'));
