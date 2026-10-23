# EcoSignal: growth form and coverage on Render

This is a new, standalone **photo-analysis backend** for EcoSignal. Both trained models are included. It generates a binary mask, an aligned overlay, full-photo coverage, growth-form classification, confidence, model versions, and review warnings from a JPEG, PNG, or WebP photograph.

The separate `site-integration/` folder connects your existing EcoSignal frontend. Deploying this API alone does not change the live website.

## 1. Commit this folder to a GitHub repository

Extract the download. Put the **contents of `ecosignal-render/`** in the root of a new repository. You should see `Dockerfile`, `render.yaml`, `requirements.txt`, `api/`, and `models/` at the repository root.

Use GitHub Desktop or Git to commit and push the files. The coverage model is about 98 MB and the growth-form model is about 29 MB. Both exceed GitHub's **25 MiB browser-upload limit**, but both are below its **100 MiB per-file Git limit**. Do not upload the ZIP itself and do not use Git LFS for this package: the actual model files must be present in Render's checkout.

GitHub Desktop: create or clone the repository, copy these contents into its local folder, commit, then publish/push. A private repository is fine.

## 2. Host it on Render

1. In Render select **New → Blueprint** and select the GitHub repository.
2. Render reads `render.yaml`, builds the Docker image, and starts the API.
3. The supplied Blueprint selects **2 CPUs / 4 GB RAM (`2c-4g`)**, a paid compute plan, to leave room for TensorFlow and PyTorch together. Review the cost before creating it. No service or charge has been created by this package. Memory needs must be verified on Render; increase resources if its logs show an out-of-memory exit.
4. Wait for the service to report Live. Open its `/health` URL. Expect `status: "ok"` and both model versions. Startup verifies both model hashes and loads both models; a bad model/runtime prevents readiness.
5. In the service's **Environment** settings find the generated `ECOSIGNAL_API_TOKEN`. Keep it secret. You will use it in the website's server configuration, not in browser code.

The Docker service uses Render's `PORT`, a single server worker, CPU inference, and one active inference at a time. A busy server returns 503 with a retry hint. The API stores no observations: it removes its temporary photo and generated images after returning the result. Your existing site's save/export flow retains the returned data.

## 3. Connect your existing EcoSignal website

Use your **latest** EcoSignal site source, including any current unified-score work. Do not replace it with an old full-site backup.

Run the focused installer from a terminal with Node installed:

```text
node path/to/ecosignal-render/site-integration/install.mjs path/to/latest/EcoSignal
```

Use quoted absolute paths if either contains spaces. The installer checks the existing handlers before editing. It backs up `app/page.tsx` and `worker/index.ts` with a `.before-photo-analysis` suffix, adds two small library files, and leaves the scoring engine unchanged. It was prepared against the source checkpoint available locally (v22); if the latest site's relevant handlers differ, it stops before writing and asks for a manual merge. Check your diff before committing. Exclude the two backup files from the site commit.

Configure these **server-side** environment secrets on the existing site hosting service:

| Name | Value |
|---|---|
| `ECOSIGNAL_ANALYSIS_URL` | The Render service's HTTPS base URL |
| `ECOSIGNAL_ANALYSIS_TOKEN` | The generated Render `ECOSIGNAL_API_TOKEN` value |

The site is currently hosted through ChatGPT Sites. These two values belong to that site's server/Worker configuration, not Render's frontend settings and not `NEXT_PUBLIC_*`. If your editor does not expose server secrets, provide the Render URL and configure the token through the host's secrets interface before publishing. Do not paste the token into source control or a public conversation.

Commit the resulting site changes, run its normal checks/build, and republish it through its current host. The integration adds `POST /api/analyze` to the existing Worker. That route forwards the photo to Render using the secret token. The browser never receives the token. Requests from another browser origin are rejected; preserve the existing site's access restrictions because origin checks are not user authentication or rate limiting.

The frontend now offers **Analyze photograph** after photo/context selection, displays progress and retry errors, shows the returned overlay, provides a downloadable binary mask, and saves/exports the mask and original model results with the observation. New photo selections cancel the previous browser request and ignore stale results. Low-confidence output remains in the raw result for review; rejected predictions are not displayed as accepted measurements. No coordinates are required for image inference.

## 4. Test the hosted connection

1. Open LichenLens, upload a photograph, continue to Context, then select **Analyze photograph**.
2. Check that progress ends with your photo's overlay and results, or explicit review warnings. The API does not promise that either model will accept every field photograph.
3. Download the mask and confirm its outline matches the photograph. Processing corrects EXIF orientation and limits the long edge to 1600 pixels; the returned mask matches that analyzed size and aspect ratio.
4. Save, refresh, and export the observation. Confirm the overlay, mask, raw output, versions, and confidence survive. Existing browser storage can fill; export observations if the site reports this.
5. Try another photograph and confirm the previous result is cleared. Disconnect the API temporarily and verify a visible error and Retry analysis button.

Coverage is the percentage of the **whole photograph**, not an automatically isolated tree-bark surface. Growth form is a dominant class with probabilities, not percentages of each growth form or a pollution measurement. Existing mask cleanup and confidence thresholds are retained from your supplied model adapters. Growth form remains unweighted in the existing unified score.

## Local API tests

Create a Python 3.12 virtual environment, install `requirements.txt`, then install `pytest` and `httpx` for tests:

```text
python -m pytest -q
```

To run the API locally, set `ECOSIGNAL_API_TOKEN` to a secret in your terminal environment and run:

```text
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

`POST /analyze` takes multipart field `image` and requires `Authorization: Bearer <token>`. It returns inline PNG data URLs, so no persistent disk or public photo bucket is needed. `/health` is public. Browser calls should go through the website proxy; this backend intentionally has no permissive cross-origin policy.

## Source models

The exact artifacts and adapters came from your downloaded `EcoSignal_Complete_Backend_v1.0.0_2026-07-18.zip`:

| File | SHA-256 |
|---|---|
| `models/best_model_tuned.pt` | `6cd686722b70aae0290175125848f317d75e593b0f7b93ddefb0d202fe47fefc` |
| `models/growthform_effnet_filtered_highacc.keras` | `e8a1bc9033e9f0eada2aaf756abc15a73adf1e60ab082cf38b39f1314290e077` |

This package contains the saved ResNet34 U-Net coverage model and EfficientNet growth-form model. It does not retrain them or replace them with heuristics. Newer retraining notebooks found locally do not establish that newer trained weights are available.

## Hosting references

- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render environment variables and secrets](https://render.com/docs/configure-environment-variables)
- [GitHub file upload limits](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

See `VERIFICATION.md` for checks performed and remaining deployment checks.
