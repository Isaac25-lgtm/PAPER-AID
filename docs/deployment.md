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

Retention backstop: storage deletes any file older than 31 days, even if the app's cleanup never ran.

```bash
cat > lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 31}}]}
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

Only the worker calls AI providers. If a required setting is missing (including either model key), the app refuses to start rather than running insecurely. That includes `SERVICE_ROLE`: each service must say whether it is `api` or `worker`. The worker also re-verifies the Google-signed identity token of `paperaid-tasks` on every call, in addition to Cloud Run IAM.

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

## Alerts worth creating (Cloud Monitoring)

- API 5xx rate above 2% for 5 minutes.
- Log entries with `message="stage failed"` and `willRetry=false`, more than 3 in 15 minutes.
- Cloud Tasks queue depth above 20 for 15 minutes.
- A billing budget alert on the project, and monthly spend limits set in the Anthropic and OpenAI consoles.
