#!/usr/bin/env bash
# Publish every package whose version is not on npm yet.
#
# Auth is npm Trusted Publishing (GitHub Actions OIDC), so no NPM_TOKEN is needed.
# `pnpm pack` rewrites `workspace:*` to real versions; `npm publish` then uploads
# that tarball (npm >= 11.5.1 does the OIDC exchange and adds provenance).
#
#   scripts/publish-npm.sh            # publish
#   DRY_RUN=1 scripts/publish-npm.sh  # pack and show what would be published
set -euo pipefail
cd "$(dirname "$0")/.."

out=$(mktemp -d)
# core first: the framework packages and synonyms depend on it
for dir in packages/core packages/react packages/vue packages/angular synonyms/*/*; do
  [ -f "$dir/package.json" ] || continue
  name=$(node -p "require('./$dir/package.json').name")
  version=$(node -p "require('./$dir/package.json').version")
  if npm view "$name@$version" version >/dev/null 2>&1; then
    echo "skip    $name@$version (already on npm)"
    continue
  fi
  tarball=$(cd "$dir" && pnpm pack --pack-destination "$out" | tail -1)
  if grep -q '"workspace:' <(tar -xOzf "$tarball" package/package.json); then
    echo "$name: workspace: protocol left in the packed package.json" >&2
    exit 1
  fi
  if [ -n "${DRY_RUN:-}" ]; then
    echo "would publish $name@$version ($tarball)"
  else
    echo "publish $name@$version"
    npm publish "$tarball" --access public --provenance
  fi
done
