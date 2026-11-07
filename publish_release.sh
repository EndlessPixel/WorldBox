#!/usr/bin/env bash
# 默认覆盖 latest 发布；传入 MANUAL_VERSION 时创建新的版本发布。
set -euo pipefail

MANUAL_VERSION="${MANUAL_VERSION:-}"
NOTES="RELEASE_NOTES.md"
FILES=(release/*)

if [ -n "$MANUAL_VERSION" ]; then
    TAG="v${MANUAL_VERSION#v}"
    echo "Creating new release: $TAG"
    gh release create "$TAG" "${FILES[@]}" \
        --title "WorldBox $TAG" \
        --notes-file "$NOTES" \
        --target "$GITHUB_SHA"
else
    TAG="latest"
    if gh release view "$TAG" >/dev/null 2>&1; then
        echo "Overwriting $TAG release"
        # 删除旧资源，避免同名/旧版本文件残留
        gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TAG" \
            --jq '.assets[].id' | while read -r asset_id; do
            [ -z "$asset_id" ] && continue
            gh api -X DELETE "repos/$GITHUB_REPOSITORY/releases/assets/$asset_id" >/dev/null
        done
        gh release edit "$TAG" \
            --title "WorldBox Latest" \
            --notes-file "$NOTES"
        gh release upload "$TAG" "${FILES[@]}" --clobber
    else
        echo "Creating $TAG release"
        gh release create "$TAG" "${FILES[@]}" \
            --title "WorldBox Latest" \
            --notes-file "$NOTES" \
            --target "$GITHUB_SHA"
    fi
fi

echo "Published: $TAG"
