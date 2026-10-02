# Deploying PaperAid to Google Cloud

This guide covers the production setup:

- **Website:** Firebase Hosting, with `/api` routed to Cloud Run.
- **Backend:** one image deployed as two Cloud Run services:
  - `paperaid-api` — public;
  - `paperaid-worker` — internal, reachable only by Cloud Tasks.
- **Data and queue:** Firestore for job records, Cloud Storage for files, and Cloud Tasks for the job queue (5 jobs processed at a time).

Everything runs in **europe-west1**.

Run the commands from a terminal where the Google Cloud SDK and Firebase CLI are installed and signed in (`gcloud auth login`, `firebase login`). Replace `PROJECT` with your project ID.

## 1. Project and services

```bash
gcloud config set project PROJECT
gcloud services enable run.googleapis.com cloudtasks.googleapis.com firestore.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com firebaseappcheck.googleapis.com
firebase projects:addfirebase PROJECT
gcloud firestore databases create --location=europe-west1   # permanent: the location cannot be changed later
gcloud storage buckets create gs://PROJECT-papers --location=europe-west1 --uniform-bucket-level-access
```

Retention backstop: storage deletes any job file (under `users/`) older than 31 days, even if the app's cleanup never ran. Proposal projects live under `projects/` and are deliberately outside this rule: they are kept while the student works on them and deleted by the app 30 days after the student's last action (`cleanup_expired_projects`), which a fixed object-age rule cannot express (object age follows creation time, not renewal).

Projects created before that change kept their files under `users/{uid}/projects/`. The scheduled cleanup (`/tasks/cleanup`) moves them to `projects/` (`migrate_legacy_project_files`, resumable and safe to repeat) and copies wallets' earlier entries into the complete credit history (`backfill_ledgers`). After the first deploy with these, run the cleanup once by hand (or wait for its schedule) and check its response: `projectsMigrated` and `ledgersBackfilled` go to 0 on later runs.

```bash
cat > lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 31, "matchesPrefix": ["users/"]}}]}
EOF
gcloud storage buckets update gs://PROJECT-papers --lifecycle-file=lifecycle.json
```

## 2. Identities (least privilege)

```bash
gcloud iam service-accounts create paperaid-api
gcloud iam service-accounts create paperaid-worker
gcloud iam service-accounts create paperaid-tasks   # the only identity allowed to call the worker

for SA in paperaid-api paperaid-worker; do
  gcloud projects add-iam-policy-binding PROJECT --member=serviceAccount:$SA@PROJECT.iam.gserviceaccount.com --role=roles/datastore.user
  gcloud storage buckets add-iam-policy-binding gs://PROJECT-papers --member=serviceAccount:$SA@PROJECT.iam.gserviceaccount.com --role=roles/storage.objectAdmin
  gcloud projects add-iam-policy-binding PROJECT --member=serviceAccount:$SA@PROJECT.iam.gserviceaccount.com --role=roles/cloudtasks.enqueuer
  gcloud iam service-accounts add-iam-policy-binding paperaid-tasks@PROJECT.iam.gserviceaccount.com \
    --member=serviceAccount:$SA@PROJECT.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
done
# The API signs short-lived download links and verifies sign-ins:
gcloud iam service-accounts add-iam-policy-binding paperaid-api@PROJECT.iam.gserviceaccount.com \
  --member=serviceAccount:paperaid-api@PROJECT.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator
gcloud projects add-iam-policy-binding PROJECT --member=serviceAccount:paperaid-api@PROJECT.iam.gserviceaccount.com --role=roles/firebaseauth.admin
```

## 3. Secrets (the model keys)

Both keys are required: GPT-6 Sol (OpenAI) is the lead model and Claude Opus 5.5 (Anthropic) the writer. Only the worker calls the providers; the API also mounts the keys because it reports whether the AI services are available ("Not set up" otherwise), but it never uses them.

```bash
printf '%s' 'sk-ant-...' | gcloud secrets create anthropic-api-key --data-file=-
printf '%s' 'sk-...'     | gcloud secrets create openai-api-key --data-file=-
for S in anthropic-api-key openai-api-key; do
  for SA in paperaid-worker paperaid-api; do
    gcloud secrets add-iam-policy-binding $S --member=serviceAccount:$SA@PROJECT.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
  done
done
```

## 4. Queue

```bash
gcloud tasks queues create paper-jobs --location=europe-west1 \
  --max-concurrent-dispatches=5 --max-attempts=3 --min-backoff=10s --max-backoff=300s
```

PaperAid handles its own retries, so the queue only retries failed deliveries. To raise concurrency later, increase `--max-concurrent-dispatches` together with the worker's `--max-instances`.

## 5. Backend (one image, two services)

```bash
cd backend
IMAGE=europe-west1-docker.pkg.dev/PROJECT/paperaid/backend:$(date +%Y%m%d-%H%M)
gcloud artifacts repositories create paperaid --repository-format=docker --location=europe-west1
gcloud builds submit --tag $IMAGE

# CREDITS_ENABLED=false is testing mode: no balance needed, nothing charged. Set it to true when credits go live.
COMMON="ENV=production,AUTH_MODE=firebase,STORE_BACKEND=firestore,STORAGE_BACKEND=gcs,QUEUE_BACKEND=cloud_tasks,REQUIRE_APP_CHECK=true,CREDITS_ENABLED=false,GCP_PROJECT=PROJECT,GCS_BUCKET=PROJECT-papers,TASKS_INVOKER_EMAIL=paperaid-tasks@PROJECT.iam.gserviceaccount.com,ALLOWED_ORIGINS=[\"https://PROJECT.web.app\"]"

gcloud run deploy paperaid-worker --image $IMAGE --region europe-west1 --no-allow-unauthenticated --ingress internal \
  --service-account paperaid-worker@PROJECT.iam.gserviceaccount.com --concurrency 1 --cpu 2 --memory 2Gi \
  --timeout 1800 --max-instances 5 \
  --set-env-vars "SERVICE_ROLE=worker,$COMMON,WORKER_URL=https://placeholder" \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest,OPENAI_API_KEY=openai-api-key:latest
WORKER_URL=$(gcloud run services describe paperaid-worker --region europe-west1 --format='value(status.url)')
gcloud run services update paperaid-worker --region europe-west1 --update-env-vars WORKER_URL=$WORKER_URL
gcloud run services add-iam-policy-binding paperaid-worker --region europe-west1 \
  --member=serviceAccount:paperaid-tasks@PROJECT.iam.gserviceaccount.com --role=roles/run.invoker

gcloud run deploy paperaid-api --image $IMAGE --region europe-west1 --allow-unauthenticated \
  --service-account paperaid-api@PROJECT.iam.gserviceaccount.com --concurrency 40 --memory 1Gi --timeout 120 \
  --set-env-vars "SERVICE_ROLE=api,$COMMON,WORKER_URL=$WORKER_URL"   --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest,OPENAI_API_KEY=openai-api-key:latest
```

Only the worker calls AI providers. If a required security setting is missing, the app refuses to start rather than running insecurely. The model keys are the exception: without both, the AI services show as "Not set up" and cannot be quoted or run, while APA/Harvard formatting keeps working. That includes `SERVICE_ROLE`: each service must say whether it is `api` or `worker`. The worker also re-verifies the Google-signed identity token of `paperaid-tasks` on every call, in addition to Cloud Run IAM.

Downloads need no bucket CORS setup. The API returns a 10-minute signed link, and the browser opens it directly rather than fetching it.

## 6. Scheduled maintenance

Two scheduled jobs call the worker:

- **reconcile**, every 5 minutes: re-queues any job that lost its task.
- **cleanup**, daily: deletes files past the retention period.

```bash
for JOB in "reconcile:*/5 * * * *" "cleanup:0 3 * * *"; do
  NAME=${JOB%%:*}; CRON=${JOB#*:}
  gcloud scheduler jobs create http paperaid-$NAME --location europe-west1 --schedule "$CRON" \
    --uri "$WORKER_URL/tasks/$NAME" --http-method POST \
    --oidc-service-account-email paperaid-tasks@PROJECT.iam.gserviceaccount.com --oidc-token-audience "$WORKER_URL"
done
```

## 7. Firebase: sign-in, App Check, website

1. In the Firebase console:
   - under Authentication, enable **Email/Password** and **Google**;
   - under App Check, register the web app with **reCAPTCHA Enterprise** and enforce it.
2. Create `web/.env.production` with the web app config (public values) and the App Check site key. See `web/.env.example`.
3. Deploy the website and the rules:

```bash
cd web && npm ci && npx vite build --mode production --outDir hosting --emptyOutDir && cd ..   # firebase.json serves web/hosting
firebase deploy --only hosting,firestore:rules,firestore:indexes --project PROJECT   # files go through the API, so no Storage rules are deployed
```

4. Make yourself an admin: sign in on the website once, run `gcloud auth application-default login`, then `python scripts/set_admin.py you@example.com`, and sign out and in again.

## 8. After every deployment

- Run one real job end to end on the live site: upload, submit, download.
- Check the admin console and Cloud Logging for errors. Search logs by `jsonPayload.jobId="job_…"`.
- Rollback:

  ```bash
  gcloud run services update-traffic paperaid-api --to-revisions=PREVIOUS=100 --region europe-west1
  ```

  Do the same for the worker, then run `firebase hosting:rollback` if the website also needs to go back.

### Rolling back the four-model release

Checked on 2026-09-29 by reading records the new code writes with the models of the release before it
(`1d573b6`, image `studio-1d573b6`, `sha256:be9c08f6828ed8913bb70b3ea0dfa2df1269071e595ebb7800016b56045e6b83`):

- **Records stay readable.** Jobs priced on the new engine, a source check on its own, a "Finish chapter"
  job (stored as its chapter's step with a `finish` flag for this reason) and a chapter with sections not
  yet written are all read by the older code: it ignores the fields it does not know. History pages and
  the admin console keep working after a rollback.
- **Work in flight cannot run on the older image.** A job priced on the new engine names prompt versions
  the older image does not have (`analyse-v3`, `finalise-v4`, `guide-v1`, `review-v3` and others), and a
  finish's step input (`COMPLETE`) is unknown to it. The older worker treats that as an unexpected error:
  it retries, then fails the job and refunds it. Nothing is charged, but the student must start again.
- **Chapters with sections not yet written** exist only if `PARTIAL_CHAPTERS` was turned on. It ships off
  (owner decision 2026-09-30) because the older release would let such a chapter be approved. While it is
  off, a rollback affects no chapter. Before turning it on, accept that a later rollback to `1d573b6` would
  show those chapters without their "Finish chapter" button (the complete proposal still refuses them).

Procedure:

1. In the admin console, **Pause processing**. Nothing new starts; running stages finish.
2. Wait until the admin list shows no job PROCESSING. Jobs still QUEUED will fail and be refunded after the
   rollback (step 4); tell those students to start again, or leave them paused until you roll forward.
3. Move traffic back, worker first:

   ```bash
   gcloud run services update-traffic paperaid-worker --to-revisions=paperaid-worker-00017-szd=100 --region europe-west1
   gcloud run services update-traffic paperaid-api --to-revisions=paperaid-api-00017-6wr=100 --region europe-west1
   firebase hosting:rollback --project paperaid-ca172
   ```

   The model settings travel with each revision, so the older revisions keep their own (Sol and Opus).
4. **Resume processing.** Check one AI Check and one Refine on the live site.
5. To roll forward again, move traffic back to the new revisions and deploy hosting again; nothing else
   needs undoing.

### Releasing works (concept notes, coursework, funding proposals) and rolling back

Two releases, in this order:

1. **The tolerant release** (the rollback point): the new records are readable (the `works` collection,
   work steps in `jobs`, the new service ids, `goal` on proposal projects); a work step fails at once with
   its credits returned; works are deleted with their accounts and expire after 30 days; a concept-note
   project never prices or starts Chapter One; the work services show as "soon". Checked on 2026-09-30
   against records written by the full release (a finished plan step, a queued draft step holding
   credits, a concept-note project): every record read, the queued step failed and its hold came back,
   and account deletion removed the work, its steps and its files.
2. **The full release**, on the same image settings plus:
   - the Gemini key: `printf '%s' 'KEY' | gcloud secrets create GEMINI_API_KEY --replication-policy=user-managed --locations=europe-west1 --data-file=-`,
     readable by both service accounts, and `--update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest` on both services;
   - `WORKS_ENABLED` left empty until the owner sets each service's token prices in `FIXED_TOKENS`
     (`WORK_PRICE_KEYS` in `app/pricing/quote.py`); a service without every price stays "coming soon";
   - `RENDER_PAGES=false` until the owner approves the larger image. Turning it on needs an image built with
     `--build-arg WITH_LIBREOFFICE=true`, which `gcloud builds submit --tag` cannot pass: use a
     `cloudbuild.yaml` with a `docker build` step instead.

Rollback from the full release: pause processing, wait for no job PROCESSING, move the worker then the
API to the tolerant revisions, roll hosting back to the tolerant release, resume processing. Work steps
still queued then fail with a refund; every record stays readable; nothing else needs undoing.

### Releasing one accountable final reviewer (2026-09-30) and rolling back

- **Build** with LibreOffice through `backend/cloudbuild.yaml` (the plain `--tag` build cannot pass the build argument). Its second step renders a Word file inside the built image and counts the pages; the build fails if LibreOffice cannot:
  `cd backend && gcloud builds submit --project paperaid-ca172 --config cloudbuild.yaml --substitutions _IMAGE=europe-west1-docker.pkg.dev/paperaid-ca172/paperaid/backend:TAG`
- **Deploy** the worker, then the API, by digest, with `--update-env-vars RENDER_PAGES=true,FRONTIER_GUIDANCE=false` (the live services had `FRONTIER_GUIDANCE=true` set explicitly). `SINGLE_REVIEWER` defaults to true; `REQUIRE_DUAL_APPROVAL=true` stays (it now means "nothing generated without approval"). `TESTER_EMAILS`, `WORKS_ENABLED`, `CREDITS_ENABLED=false` are unchanged; `WORKS_PUBLIC` stays unset (tester-only, fail-closed). Then the website.
- **Rollback**: pause processing, wait for no job PROCESSING, move the worker then the API back to the previous revisions (`paperaid-worker-00024-dvd`, `paperaid-api-00024-25d`) and roll hosting back, resume. The previous release reads every record this one writes (plan reviews, acknowledgments, stored Word paths, readiness reasons and the engine's `singleReviewer` are extra fields it ignores). A step priced on the new engine and run by the old code is reviewed by both reviewers, which is stricter, never looser. `RENDER_PAGES=true` is harmless on the old image: without LibreOffice the page count stays "Needs review".

## Release log

| Date | Commit | Image | API revision | Worker revision | Hosting release |
|---|---|---|---|---|---|
| 2026-10-02 | `1405cc2` | `release-1405cc2` (`sha256:49a99175ab18018f9d2c8b23861006ed491bea57bde0b7cb00b8734930d5d856`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00036-kz7` | `paperaid-worker-00037-tfb` | Codex's audit of 9239dd0: Start in one transaction (submitted, started and reserved together), page 1 kept in line with the saved work, context documents in file storage, replaceable funding call, firm read ceiling, `w-plan-v3` and `w-results-v2`; hosting deployed. Live check: one real coursework essay (1,500-word limit) through Start, plan approved and drafted by itself, Ready with warnings, 1,467 words, then deleted |
| 2026-10-01 | `9239dd0` | `release-patience` (`sha256:daeb9f3cafcf51fd82f4596a7ac93532d52edcdb1b73c05184964cd059209601`, with LibreOffice) | `paperaid-api-00035-qqk` | `paperaid-worker-00036-mdq` | stages wait out provider outages longer (`STAGE_MAX_ATTEMPTS` 6); a step out of retries says it stopped; hosting unchanged (recorded 2026-10-02: deployed without a log row) |
| 2026-10-01 | `820f862` | `release-planv2` (`sha256:5dbfa9064f3294558c27fef6d6fa3b8b74c0d06732d957896d99e9a31f2ea1d5`, with LibreOffice) | `paperaid-api-00034-w52` | `paperaid-worker-00035-7sx` | `w-plan-v2`: plans keep claims within the evidence, a repair changes only what was raised; hosting unchanged (recorded 2026-10-02: deployed without a log row) |
| 2026-10-01 | `0fde362` | `release-durable` (`sha256:8594396508d76613ec2101e5489230bc8b20513c9be3113b6aae26f1712a7cf4`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00033-vnq` | `paperaid-worker-00034-mts` | Codex's second verification: durable one-Start continuation (`auto_next`, finished by the 5-minute reconcile), one reservation per Start attempt, page 1 reuses its work and page 2 offers reading again, reads for unstarted works capped per day, length rechecked when figures are added, copy, older work opens in the workspace once written. Hosting deployed from `0fde362`; the earlier website fix `ca9b9f0` (unstarted work reopens on its Start page) had been deployed to hosting on 2026-10-01 after `a181710` and is included. Tests: 680 passed plus a timing fix in test_profiles; six browser journeys passed. Settings unchanged (credits off, works tester-only). Rollback: worker 00033-jjj, API 00032-2tr |
| 2026-10-01 | `8059175` | `release-verified` (`sha256:59ead3952497f9486715f4d8421f260f4ca9f6a27e577f9ba422b2f4fe9b748f`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00032-2tr` | `paperaid-worker-00033-jjj` | Codex's verification of one Start (credits checked before AI and reserved at Start, failed reads, proposal finishing, figures-only, no plan pages for new work, sampling tick, no duplicate proposals, PDF compiler on Windows, public copy); optional coursework word limit; failures name the problem; a short assignment question no longer blocks Start (live check: a seven-word question passes, 2,000 words assumed). Hosting deployed from `8059175`. Tests: 677 passed, six browser journeys passed. Settings unchanged (credits off, works tester-only). Rollback: worker 00032-kx5, API 00031-9wk |
| 2026-10-01 | `bc41a7c` | `release-onestart2` (`sha256:466331bebcee86d1df0ed6177538b12fd1371060cec4fb6daf530852aec53469`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00031-9wk` | `paperaid-worker-00032-kx5` | One Start (`83d5c91`): two pages to a finished document, workspace, credits instead of tokens, minimum credits (unset), bundled read and plan, funding gaps filled in without AI, framework figure, new top bar, New page, dashboard and Your work; hosting deployed from `83d5c91`. Also: the figure-check false alarms that refused prj_18519f00596d (`2281da4`, api 00029-ppc, worker 00030-mjm; its Chapter One then completed live, 11 sections, "6–24" kept) and Codex's audit of c6ba362 (`886c29c`). Live one-Start checks, real models: coursework 1 of 2 delivered (Ready with warnings, 1,343 words, cover printed, Word and PDF; the other failed DOCUMENT_NOT_READY, not charged); research proposal 1 of 2 (Chapter One, 11 sections, "6–24" kept 12 times, framework figure; the other's plan failed PLAN_INVALID, not charged); funding 0 of 1 (plan approved, Results Model not approved by the final review after two repairs: stopped without charge as designed). Settings unchanged (credits off, works tester-only). Rollback: worker 00029-89x, API 00028-wdg, hosting from 37e5e42 |
| 2026-10-01 | `c6ba362` | `release-length` (`sha256:dbc2a143883adbaac4cb4088c3f7e0ec406385658da8fb788e3010e0f632efa3`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00028-wdg` | `paperaid-worker-00029-89x` | Works repairs get the section's evidence (`w-repair-v2`, `bac84f1`) and a draft well under its word limit is developed before delivery; each final-review round kept in the job's internal files. Settings unchanged (RENDER_PAGES=true, FRONTIER_GUIDANCE=false, credits off, works tester-only); web unchanged, hosting not redeployed. Live tester journey after the OpenAI top-up: before the fixes 2 of 3 coursework drafts failed without charge and 1 was delivered Not ready (1,259 of 1,500 words); on this release two runs both completed (1,416 and 1,361 words), Ready with warnings, Word identical on repeat, PDF converted. Intermediate releases: `bac84f1` (api 00027-h55, worker 00028-hmm) and a diagnostic worker (00027-dvl). Rollback: worker 00026-n25, API 00026-btn |
| 2026-10-01 | `37e5e42` | `audit-37e5e42` (`sha256:fe00959369590b05bd0d7c495c8b46e426997d8185fa517e2c2740f72dc54756`, with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00026-btn` | `paperaid-worker-00026-n25` | Codex's audit of the one-final-reviewer release (7 fixes); validators-v2 and render-v2 (older works steps refused and refunded); settings unchanged (RENDER_PAGES=true, FRONTIER_GUIDANCE=false, credits off, works tester-only); hosting deployed. A live job is still blocked by the OpenAI account's empty balance (insufficient_quota). Rollback: worker 00025-hcg, API 00025-zwh |
| 2026-10-01 | `80fdf80` | `review-80fdf80` (`sha256:61af43177e0080109d505ba8aa3aa4d25f013429fc458fd8b9a502f771c1b4af`, built with LibreOffice; the build rendered a test file to 13 pages) | `paperaid-api-00025-zwh` | `paperaid-worker-00025-hcg` | one accountable final reviewer (Sol), repair and re-review, coursework questions fixed, RENDER_PAGES=true, FRONTIER_GUIDANCE=false; credits off, works tester-only (fail-closed), AI score and partial chapters off; hosting deployed. Live check as a tester: access and the saved word limit verified; the plan step failed PROVIDER_UNAVAILABLE because the OpenAI account had no credit (insufficient_quota), refunded; the full live journey and downloads remain to be checked after the top-up. Rollback: worker 00024-dvd, API 00024-25d, hosting rollback |
| 2026-09-30 | `bbfeb63` | `audit2-bbfeb63` (`sha256:00c552b56e7207d8ec1bdddd2998ad6181ea0106a0f1cf9853fd4a73cd68baa0`) | `paperaid-api-00024-25d` | `paperaid-worker-00024-dvd` | Codex's second works audit (12 fixes); works pilot fails closed (`WORKS_PUBLIC` unset = testers and admins only); settings unchanged |
| 2026-09-30 | `20969b4` | `works-20969b4` (`sha256:465574b1967f36573dc247f665ab19b213785aeb92d052a451ca6239680b96ea`) | `paperaid-api-00023-g5x` | `paperaid-worker-00023-w4k` | coursework, concept notes and funding proposals on for invited testers (`WORKS_ENABLED` all three, testing prices, credits still off); fixes from the real-model pilot (required section names, missed sections re-asked, withheld sentences no longer hold a draft at Not ready) |
| 2026-09-30 | `d5285b9` | `hotfix-d5285b9` (`sha256:d168a72d8fd1c7e437a199e57779857ec820b047cab27f7c621cb40a6691f714`) | `paperaid-api-00022-gkj` | `paperaid-worker-00022-scc` | hotfix: proposal plans no longer fail on a sampling margin or proportion of 0 (every live plan had failed PLAN_INVALID); coursework on for testers |
| 2026-09-30 | `48e5b75` | `works-48e5b75` (`sha256:2d029c8880874c0d50ed459f756e588f6280e4a88ccf8a8dc50b9375b77ddc82`) | `paperaid-api-00021-tm7` | `paperaid-worker-00021-9mj` | full works release with Codex's 11 audit fixes; GEMINI_API_KEY mounted (both service accounts can read it); WORKS_ENABLED empty (work services "soon"), RENDER_PAGES off; hosting deployed |
| 2026-09-30 | `0530f86` | `tolerant-0530f86` (`sha256:1dceb89baf96a218f2455b7357e320e1d28f18450968e3a2b588dcb3a24eec8a`) | `paperaid-api-00020-fvs` | `paperaid-worker-00020-5t2` | tolerant release: the rollback point for works (records readable, work steps refunded); hosting deployed from the tolerant worktree |
| 2026-09-30 | `2f0a2d1` | `followup-2f0a2d1` (`sha256:c3d63d4cedc43661367fac48350eae1813aa030bb86bebe6b8c1232aa2e2adfe`) | `paperaid-api-00019-ttn` | `paperaid-worker-00019-4xl` | scores hidden from student responses, steps bound to their guide, PDF omission guard, finish context; SHOW_AI_SCORE and PARTIAL_CHAPTERS still off; hosting deployed |
| 2026-09-30 | `5277491` | `four-models-5277491` (`sha256:419a89bf3c83c51907c2a0c72635b86e7aef2155a1e7a9e7a4fc0d9035126b05`) | `paperaid-api-00018-fx8` | `paperaid-worker-00018-9cx` | four-model algorithm, writing feedback only (SHOW_AI_SCORE off), three sections, PARTIAL_CHAPTERS off; hosting deployed |
| 2026-09-29 | `1d573b6` | `studio-1d573b6` (`sha256:be9c08f6828ed8913bb70b3ea0dfa2df1269071e595ebb7800016b56045e6b83`) | `paperaid-api-00017-6wr` | `paperaid-worker-00017-szd` | studio reliability fixes; hosting deployed |
| 2026-09-29 | `6f39072` | `backend:v16` (`sha256:c6fec6d7673b8bfa562f85d0fdb39007cffe8696aff59b450fbf7ef140fe9c79`) | `paperaid-api-00016-w25` | `paperaid-worker-00016-4h7` | live channel, 2026-09-29 02:4x EAT; one screen from upload to final draft, AI-likeness percentage |
| 2026-09-29 | `c60cece` | `backend:v15` (`sha256:1740fd5137aa8e8132fbddc7097cdd5282e6b770e05778e4719eec6f156a4741`) | `paperaid-api-00015-5zv` | `paperaid-worker-00015-7c9` | live channel, 2026-09-29 00:1x EAT; firestore rules and indexes (new `ledger` at/id); cleanup run by hand: 200, no legacy projects to migrate |
| 2026-09-28 | `748ccd8` | `backend:v14` (`sha256:213c3499ad414f85e1db932f97bd66637fc47f0f70f09ece91aabb2be5adc7e6`) | `paperaid-api-00014-t7v` | `paperaid-worker-00014-fvd` | live channel, 2026-09-28 16:5x EAT |
| 2026-09-28 | `7cd6a5a` | `backend:v13` (`sha256:7f7a7296a6d438805fce0f2d37a90bd0734c8886f066e97fab725f3c999fdb86`) | `paperaid-api-00013-zh5` | `paperaid-worker-00013-rbq` | live channel, 2026-09-28 14:57:56 EAT; bucket lifecycle scoped to `users/` |
| 2026-09-27 | `898aa1c` | `backend:v11` (`sha256:114fb0dbd3284f417879b6eb3cb6327ee7d281ad7ab65bd674467eccc54aea0e`) | `paperaid-api-00012-prd` | `paperaid-worker-00012-gfv` | live channel, 2026-09-27 22:40 EAT (web unchanged since `b150929`) |

## Alerts worth creating (Cloud Monitoring)

- API 5xx rate above 2% for 5 minutes.
- Log entries with `message="stage failed"` and `willRetry=false`, more than 3 in 15 minutes.
- Cloud Tasks queue depth above 20 for 15 minutes.
- A billing budget alert on the project, and monthly spend limits set in the Anthropic and OpenAI consoles.
