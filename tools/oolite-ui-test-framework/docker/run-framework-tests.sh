#!/bin/sh
# Run the framework's whole offline test suite (tests/) inside a Docker image that has tesseract, so nothing skips.
# Usage: docker/run-framework-tests.sh [image] [pytest args]   (image default: oolite-uitest-debian, or OCR_TEST_IMAGE)
#
# Mounts the WHOLE repository read-only, not just this framework folder: the plugin tests read the game's UI tests in
# <repo>/tests/ui, and with only the framework mounted they fail with FileNotFoundError '/tests/ui/...'. Nothing is written
# to the host (-p no:cacheprovider; pytest's temp dirs are inside the container).
IMAGE="${1:-${OCR_TEST_IMAGE:-oolite-uitest-debian}}"; [ $# -gt 0 ] && shift
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
[ -d "$REPO/tests/ui" ] || { echo "no tests/ui under $REPO: this script must stay at tools/oolite-ui-test-framework/docker/"; exit 2; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "image $IMAGE not found: build it first (docker build -f docker/Dockerfile.<name> -t $IMAGE .)"; exit 2; }
exec docker run --rm -v "$REPO":/repo:ro -w /repo/tools/oolite-ui-test-framework --entrypoint python3 "$IMAGE" \
    -m pytest -p no:cacheprovider tests -q -rs "$@"
