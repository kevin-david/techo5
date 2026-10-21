#!/bin/bash
# Compare source archives for build-host paths; usable independently after packaging.
set -euo pipefail
if [ "$#" -ne 4 ]; then
    echo "usage: check-source-paths.sh SOURCE BASELINE WORK KTREE" >&2
    exit 2
fi
SRCTAR=$1
BASELINE=$2
WORK=$3
KTREE=$4

# Require a directory boundary: /work must not match Linux workqueue.h or working-state.rst.
esc() { printf '%s' "$1" | sed 's/[][\.*^$+?(){}|]/\\&/g'; }
boundary='(/|$|[^[:alnum:]_.-])'
pat="/home/|relbuild|$(esc "$WORK")$boundary|$(esc "$KTREE")$boundary"
for n in "$(id -un)" "${USER:-}" "${SUDO_USER:-}"; do
	case "$n" in ""|root|techo5) ;; *) pat="$pat|\b$(esc "$n")\b";; esac
done
count() { grep -aoiE "$pat" | tr 'A-Z' 'a-z' | sort | uniq -c; }
ours=$(tar -xJOf "$SRCTAR" | count || true)
theirs=$(tar -xJOf "$BASELINE" | count || true)
names=$(tar -tJf "$SRCTAR" | grep -iE "$pat" || true)
if [ -n "$names" ] || [ "$ours" != "$theirs" ]; then
	echo "$SRCTAR carries something of this computer:" >&2
	echo "  kernel.org's: $theirs" >&2; echo "  ours: $ours" >&2
	[ -z "$names" ] || echo "  in names: $(echo "$names" | head -5)" >&2
	exit 1
fi
echo "OK: source paths match the baseline; no build-host path found"
