#!/usr/bin/env bash
# Fails the build if dist contains syntax or CSS Safari 12 cannot handle.
set -euo pipefail
cd "$(dirname "$0")/.."
js=dist/assets/app.js
css=$(ls dist/assets/*.css | head -1)
fail=0
check() { # $1 file, $2 pattern (grep -E), $3 label
  if grep -Eq "$2" "$1"; then echo "GATE: $3 found in $1"; fail=1; fi
}
check "$js" '\?\.[A-Za-z_$\[(]' "optional chaining"
check "$js" '[^?]\?\?[^?]' "nullish coalescing"
check "$js" 'import\.meta' "import.meta"
check "$js" '\(\?<[=!]' "regex lookbehind"
check "$js" '[0-9]n\b' "BigInt literal"
check "$js" '\.replaceAll\(' "String.replaceAll"
check "$js" 'Object\.fromEntries' "Object.fromEntries"
check "$js" '\.arrayBuffer\(\)' "Blob.arrayBuffer"
check "$js" 'queueMicrotask' "queueMicrotask"
check "$js" 'structuredClone' "structuredClone"
check "$js" 'ResizeObserver' "ResizeObserver"
check "$js" 'IntersectionObserver' "IntersectionObserver"
check "$js" '\.at\(' "Array.prototype.at"
check "$js" '\.text\(\)' "Blob.text"
check "$css" '(^|[;{[:space:]])gap:' "flex/grid gap"
check "$css" 'column-gap:' "column-gap"
check "$css" 'row-gap:' "row-gap"
check "$css" '(^|[;{[:space:]])inset:' "inset shorthand"
check "$css" 'clamp\(' "clamp()"
check "$css" 'aspect-ratio' "aspect-ratio"
check "$css" 'overscroll-behavior' "overscroll-behavior"
check "$css" ':focus-visible' ":focus-visible"
if grep -Eq 'position:[[:space:]]*sticky' "$css" && ! grep -Eq 'position:[[:space:]]*-webkit-sticky' "$css"; then
  echo "GATE: sticky without -webkit-sticky in $css"; fail=1
fi
if [ "$fail" -ne 0 ]; then exit 1; fi
echo "GATE: ok"
