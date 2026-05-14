#!/usr/bin/env bash
# Refresh the Subresource Integrity (SRI) hashes for vendored CDN scripts
# referenced from src/dashboard/static/index.html.
#
# Usage:
#   ./scripts/update_sri.sh
#
# Output: prints `sha384-...` for each vendored asset so you can paste it
# into the `<script>` tag's `integrity=` attribute. Also patches the HTML
# in place if the placeholder pattern matches.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT/src/dashboard/static/vendor"
HTML="$ROOT/src/dashboard/static/index.html"

compute() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "MISSING: $file" >&2
    return 1
  fi
  local hash
  hash="$(openssl dgst -sha384 -binary "$file" | base64)"
  echo "sha384-$hash"
}

main() {
  declare -A hashes
  for f in "$VENDOR_DIR"/*.js; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    hash="$(compute "$f")"
    hashes["$name"]="$hash"
    printf '%-60s %s\n' "$name" "$hash"
  done

  # Patch in place if HTML still references the old hash pattern.
  for name in "${!hashes[@]}"; do
    new="${hashes[$name]}"
    # We assume the HTML sets `this.integrity='sha384-...'` in the onerror
    # handler; pick that token and replace it with the new hash.
    if grep -q "$name" "$HTML" 2>/dev/null; then
      python3 - "$HTML" "$name" "$new" <<'PY'
import re, sys
path, name, newhash = sys.argv[1:]
src = open(path).read()
# Find any `integrity='sha384-...'` adjacent to this asset's URL.
pattern = re.compile(
    r"(this\.src='[^']*" + re.escape(name) + r"';?\s*this\.integrity=')sha384-[^']+(')"
)
new = pattern.sub(rf"\1{newhash}\2", src)
if new != src:
    open(path, "w").write(new)
    print(f"  patched {name}")
PY
    fi
  done
}

main "$@"
