// Harmless sandbox probe: waits 120 seconds; the 60 second sandbox timeout must stop it first.
console.log('W5RESULT waiting=120');
setTimeout(() => console.log('W5RESULT timeout=completed'), 120000);
