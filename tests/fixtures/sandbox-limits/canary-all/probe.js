// Harmless sandbox probe: reads every fake canary and prints the fake environment value.
const fs = require('node:fs');
for (const target of ['.npmrc', '.ssh/id_rsa', '.aws/credentials']) {
  try {
    fs.readFileSync(`${process.env.HOME}/${target}`, 'utf8');
    console.log(`W5RESULT read ${target}=ok`);
  } catch (error) {
    console.log(`W5RESULT read ${target}=${error.code}`);
  }
}
console.log(`W5RESULT env=${process.env.CANARY_ENV}`);
