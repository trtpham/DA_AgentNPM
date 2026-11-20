// Harmless sandbox probe: looks up many missing paths outside the package so the trace passes the 2 MB cap.
const fs = require('node:fs');
for (let i = 0; i < 40000; i += 1) fs.existsSync(`/nonexistent/w5-big-trace-probe-path-${i}`);
console.log('W5RESULT lookups=40000');
