#!/bin/sh
# Offline install, inside the restricted container only (sandbox/run.py docker_command).
# 2026-11-20 (Gate B0): install the package the way a user does -- an empty project runs
# `npm install --offline <package tarball>` -- so devDependencies are never needed and the
# production dependencies come from the npm cache that cache_deps.sh filled (read-only /cache).
# Before, `npm install` inside the package folder stopped at ENOTCACHED and no script ran.
# --foreground-scripts only sends a dependency's script output to stdout (npm hides it otherwise), so
# canary values printed by the script are still seen; the scripts run the same either way.
set -u

mkdir -p "$HOME/.ssh" "$HOME/.aws"
cp /opt/canary/.npmrc "$HOME/.npmrc"
cp /opt/canary/.ssh/id_rsa "$HOME/.ssh/id_rsa"
cp /opt/canary/.aws/credentials "$HOME/.aws/credentials"
# C2 (2026-11-07): more fake canaries; an image built before them simply has fewer files.
mkdir -p "$HOME/.docker" "$HOME/.kube" "$HOME/.config/gh" "$HOME/.config/solana"
for item in .git-credentials .docker/config.json .kube/config .config/gh/hosts.yml .config/solana/id.json; do
  cp "/opt/canary/$item" "$HOME/$item" 2>/dev/null || true
done

# Tarball of the package as npm would fetch it (top folder "package/"); built with tar, no npm, no script.
tar -czf /work/package.tgz -C /input --transform 's,^\.,package,' . || exit 97
# npm writes temp files inside its cache even offline (EROFS on a read-only /cache, 2026-11-20), so the
# read-only copy from the volume is copied into the /tmp tmpfs (noexec; the cache only holds data).
cache=/tmp/npm-cache
mkdir -p "$cache" || exit 97
if [ -d /cache ]; then cp -R /cache/. "$cache/" || exit 97; fi
mkdir -p /work/project && cd /work/project || exit 97
printf '{"name":"sandbox-project","version":"1.0.0","private":true}\n' > package.json

timeout 60 strace -f -qq -e trace=file,network,process -o /work/strace.log \
  npm install --offline --foreground-scripts --no-audit --no-fund --userconfig=/dev/null --cache "$cache" \
  --logs-max=0 /work/package.tgz > /work/npm.stdout 2> /work/npm.stderr
status=$?
printf 'EXIT=%s\n' "$status"

# Trace size (2026-11-20): node reads thousands of its own and the package's files. Drop single-path
# file calls under /work (the package and the project) or npm's own install folder: they never count as
# outside files, canaries or persistence. execve, clone, connect, rename/link and everything else stay.
NOISE='^[0-9]+ +(<\.\.\. )?(open|openat|openat2|stat|lstat|newfstatat|statx|access|faccessat|faccessat2|readlink|readlinkat|mkdir|mkdirat|unlink|unlinkat|rmdir|chmod|fchmodat|chown|fchownat|lchown|utimensat|getxattr|lgetxattr|statfs)\((AT_FDCWD, )?"(/work/|/usr/local/lib/node_modules/npm/)'
touch /work/strace.log
grep -avE "$NOISE" /work/strace.log > /work/trace.txt
# Still over the cap: keep the head (the root of the process tree) and the tail, never only the tail.
# TRACE_TRUNCATED=1 keeps the run from ever counting as a clean, complete install.
LIMIT=1900000
HALF=950000
if [ "$(wc -c < /work/trace.txt)" -gt "$LIMIT" ]; then
  printf 'TRACE_TRUNCATED=1\n'
  { head -c "$HALF" /work/trace.txt | sed '$d'
    printf '... trace cut: middle removed ...\n'
    tail -c "$HALF" /work/trace.txt | sed '1d'; } > /work/trace.cut
  mv /work/trace.cut /work/trace.txt
else
  printf 'TRACE_TRUNCATED=0\n'
fi
printf 'TRACE='
base64 -w0 /work/trace.txt
printf '\nSTDOUT='
tail -c 4000 /work/npm.stdout 2>/dev/null | base64 -w0
printf '\nSTDERR='
tail -c 4000 /work/npm.stderr 2>/dev/null | base64 -w0
printf '\n'
