#!/usr/bin/env bash
# PaperAid backend release (2026-10-07). Run from Git Bash at the repository root, signed in to gcloud
# with an account that can deploy to paperaid-ca172:
#   ./release.sh            build and deploy the committed HEAD of main
#   ./release.sh --check    verify only: clean tree, tests, lint, web build; no build or deploy
#
# What it guarantees:
# - The image is built from `git archive HEAD`, never from the working tree, so the release is exactly
#   the recorded commit (uncommitted or untracked files cannot slip in).
# - It builds with backend/cloudbuild.yaml: LibreOffice for rendered page counts and the in-image
#   rendering self-test (a plain `gcloud builds submit --tag` skips both).
# - Both services are deployed by image digest. Only the Vertex target is set (--update-env-vars):
#   every other setting, secret binding and service identity stays as it is. No model route is forced;
#   the Gemini workflow and its models are the code's defaults (app/core/config.py).
# - Application resources stay in paperaid-ca172 (europe-west1); Vertex inference targets VERTEX_PROJECT.
set -euo pipefail

APP_PROJECT=paperaid-ca172
REGION=europe-west1
VERTEX_PROJECT=paperaid
VERTEX_LOCATION=global
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

[ "$(git branch --show-current)" = main ] || { echo "Release from main." >&2; exit 1; }
git diff --quiet HEAD -- backend web || { echo "Commit or stash the backend/web changes first: the release is HEAD." >&2; exit 1; }
COMMIT="$(git rev-parse --short HEAD)"

echo "== checks for $COMMIT"
(cd backend && .venv/Scripts/python -m ruff check app tests \
  && .venv/Scripts/python -m pytest -q -p no:cacheprovider -n 8 --basetemp="$(mktemp -d)")
(cd web && npm test && npx tsc --noEmit && npx vite build --mode production --outDir "$(mktemp -d)" --emptyOutDir)  # backend release: the build is a check
[ "${1:-}" = "--check" ] && { echo "Checks passed; nothing built or deployed."; exit 0; }

echo "== build $COMMIT from the commit itself"
SRC="$(mktemp -d)"
git archive HEAD backend | tar -x -C "$SRC"
IMAGE="europe-west1-docker.pkg.dev/$APP_PROJECT/paperaid/backend:release-$COMMIT"
(cd "$SRC/backend" && gcloud builds submit --project "$APP_PROJECT" --config cloudbuild.yaml --substitutions "_IMAGE=$IMAGE")
DIGEST="$(gcloud artifacts docker images describe "$IMAGE" --project "$APP_PROJECT" --format='value(image_summary.digest)')"
[ -n "$DIGEST" ] || { echo "No digest for $IMAGE" >&2; exit 1; }
BY_DIGEST="${IMAGE%%:*}@$DIGEST"

before() { gcloud run services describe "$1" --project "$APP_PROJECT" --region "$REGION" --format='value(status.latestReadyRevisionName)'; }
OLD_WORKER="$(before paperaid-worker)"; OLD_API="$(before paperaid-api)"

echo "== deploy $BY_DIGEST (worker first: it runs the AI)"
for SERVICE in paperaid-worker paperaid-api; do
  gcloud run deploy "$SERVICE" --project "$APP_PROJECT" --region "$REGION" --image "$BY_DIGEST" \
    --update-env-vars "VERTEX_PROJECT=$VERTEX_PROJECT,VERTEX_LOCATION=$VERTEX_LOCATION"
done

echo "== released $COMMIT"
echo "worker: $(before paperaid-worker) (was $OLD_WORKER)"
echo "api:    $(before paperaid-api) (was $OLD_API)"
echo "Rollback:"
echo "  gcloud run services update-traffic paperaid-worker --project $APP_PROJECT --region $REGION --to-revisions=$OLD_WORKER=100"
echo "  gcloud run services update-traffic paperaid-api --project $APP_PROJECT --region $REGION --to-revisions=$OLD_API=100"
