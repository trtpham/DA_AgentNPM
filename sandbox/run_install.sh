#!/bin/sh
set -u

cp -R /input/. /work/ || exit 97
mkdir -p "$HOME/.ssh" "$HOME/.aws"
cp /opt/canary/.npmrc "$HOME/.npmrc"
cp /opt/canary/.ssh/id_rsa "$HOME/.ssh/id_rsa"
cp /opt/canary/.aws/credentials "$HOME/.aws/credentials"
cd /work || exit 97

timeout 60 strace -f -qq -e trace=file,network,process -o /work/strace.log \
  npm install --offline --no-audit --no-fund --userconfig=/dev/null \
  > /work/npm.stdout 2> /work/npm.stderr
status=$?
printf 'EXIT=%s\n' "$status"
if [ -f /work/strace.log ] && [ "$(wc -c < /work/strace.log)" -gt 2000000 ]; then
  printf 'TRACE_TRUNCATED=1\n'
else
  printf 'TRACE_TRUNCATED=0\n'
fi
printf 'TRACE='
tail -c 2000000 /work/strace.log 2>/dev/null | base64 -w0
printf '\nSTDOUT='
tail -c 4000 /work/npm.stdout 2>/dev/null | base64 -w0
printf '\nSTDERR='
tail -c 4000 /work/npm.stderr 2>/dev/null | base64 -w0
printf '\n'
