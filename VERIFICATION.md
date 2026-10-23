# Verification — October 23, 2026

## Completed locally

- Both supplied model files matched their recorded SHA-256 checksums.
- Both real models loaded and ran using Python 3.12, PyTorch 2.14.1, TensorFlow 2.21.0, and Keras 3.15.1.
- Both Apex Nature Park photos returned HTTP 200 through the actual FastAPI `/analyze` endpoint with both real adapters; no fixture predictions were used for these runs.
- Both photos produced binary masks and overlays at 1200 × 1600 pixels, matching the EXIF-corrected analyzed images. Original oriented dimensions: 3024 × 4032.
- The iPhone photographs decode as MPO JPEGs; support for this actual input format was added after the first run exposed it.
- 5 API contract tests passed: readiness/auth, invalid/large input, inline masks and partial output, independent component failures, and bounded inference concurrency. These tests use explicitly synthetic outputs where needed and do not measure scientific accuracy.
- 4 site connection tests passed: response validation, proxy configuration/origin rejection, file and secret forwarding, and upload/error handling.
- The installer applied successfully to the locally available v22 checkpoint. The updated page and its imported frontend components passed strict TypeScript checking. All four edited/added TypeScript and TSX files passed syntax transpilation. The existing unified scoring engine was not edited.

## Real-photo results

| Photograph | Coverage model output | Growth-form model output |
|---|---|---|
| `IMG_0790.jpeg` | Candidate 51.65%; **rejected for low quality**, confidence metric 0.454 | Crustose, **tentative**, model probability 0.731 |
| `IMG_0792 (1).jpeg` | 45.55%; **manual review required** for uncertain boundaries, confidence metric 0.490 | **Uncertain / retake required**; highest class probability 0.553 |

These are model outputs, not ground truth. Visual inspection of the second overlay showed highlighted exposed wood and background as well as potential lichen; that output is not verified as an accurate lichen mask. Successful execution does not establish model accuracy. Coverage refers to the full image, and confidence metrics are not calibrated probabilities of correct coverage or environmental health. The frontend withholds rejected values from its accepted measurement fields and retains raw candidates and review reasons in exported results.

## Still requires deployment verification

- Build and start the Docker image on Render's Linux runtime. Local execution used Windows CPU packages; Docker/Render execution has not been run here.
- Review the paid compute plan and actual memory use on Render.
- Configure the site server URL/token, apply the installer to the latest site source, build and publish the site, and test its browser upload/save/reload/export flow.
- Full site production build and browser layout testing were not performed. The live site's hosting tools were unavailable in this chat; no deployment was attempted.
- No independent accuracy study, new annotations, retraining, or unified-score validation was performed.

The repository contains no Apex photographs or private observations. The application uses temporary files only and returns PNG data URLs to the existing browser observation storage.
