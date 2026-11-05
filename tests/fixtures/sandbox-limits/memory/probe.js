// Harmless sandbox probe: touches about 512 MB in 32 MB steps; the 256 MB container limit must stop it.
const chunks = [];
for (let i = 1; i <= 16; i += 1) {
  chunks.push(Buffer.alloc(32 * 1024 * 1024, 1));
  console.log(`W5RESULT allocated_mb=${i * 32}`);
}
console.log('W5RESULT memory=completed');
