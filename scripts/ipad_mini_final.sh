#!/bin/bash
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git diff --exit-code HEAD --
echo "Final tested tree: $(git rev-parse 'HEAD^{tree}')"
shasum -a 256 .github/workflows/apple-platforms.yml
