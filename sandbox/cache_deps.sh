#!/bin/sh
# Prepare step, network ON, no package code (2026-11-20, Gate B0): fetch the production dependencies of
# the package in /vol/pkg into /vol/npm-cache, which the offline sandbox later mounts read-only.
# --ignore-scripts: no lifecycle script of the package or of any dependency runs here.
set -u
mkdir -p /vol/npm-cache /tmp/project || exit 97
tar -czf /tmp/package.tgz -C /vol/pkg --transform 's,^\.,package,' . || exit 97
cd /tmp/project || exit 97
printf '{"name":"sandbox-project","version":"1.0.0","private":true}\n' > package.json
npm install --ignore-scripts --no-audit --no-fund --userconfig=/dev/null --cache /vol/npm-cache --logs-max=0 \
  /tmp/package.tgz > /tmp/npm.out 2>&1
status=$?
printf 'EXIT=%s\n' "$status"
printf 'OUTPUT='
tail -c 600 /tmp/npm.out | base64 -w0
printf '\n'
