#!/usr/bin/env bash
set -euo pipefail

repo="${1:-basil/bible}"
prefix="Linux-page-fill-v1-valkyrie-"

cache_ids="$(gh cache list \
	--repo "$repo" \
	--limit 100 \
	--json id,key \
	--jq ".[] | select(.key | startswith(\"$prefix\")) | .id")"

if [[ -n $cache_ids ]]; then
	while IFS= read -r cache_id; do
		[[ -n $cache_id ]] && gh cache delete "$cache_id" --repo "$repo"
	done <<<"$cache_ids"
fi

remaining="$(gh cache list \
	--repo "$repo" \
	--limit 100 \
	--json id,key \
	--jq ".[] | select(.key | startswith(\"$prefix\")) | .id")"

if [[ -n $remaining ]]; then
	echo 'Some page-filler caches remain:' >&2
	echo "${remaining}" >&2
	exit 1
fi

echo "Page-filler caches cleared for ${repo}."
