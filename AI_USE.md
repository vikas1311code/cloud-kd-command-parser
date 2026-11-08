# AI use

## Tools
- Claude (Anthropic chat assistant), used throughout the project.

## What I used it for
- Reading the handout and planning the order of the tasks.
- Drafting code and config: worker, clean.py, training script, service, Kubernetes manifests,
  evaluation scripts, make up / make down, the GitHub Actions workflow.
- Explaining errors from my terminal output and proposing fixes (for example the make up download
  failures described below).

## How I checked what it gave me
- I ran every script myself on my own laptop and read the real output. Nothing in results/ was
  produced by the assistant; all numbers (loss, scores, latency, load tests) come from my runs.
- Model integrity: I compared SHA-256 of the GitHub Release assets with model.sha256 (v1 and v2 matched).
- Code checks: ruff and the unit tests (18 tests) ran locally and in GitHub Actions.
- Quality gate: I ran the workflow with the untrained Pythia-70M on purpose and confirmed the gate fails.
- Reproducibility: I deleted the cluster, cloned the repository into a new folder and ran make up.
  The first two tries failed (HTTP 504 from GitHub, a bad partial download, a checksum mismatch);
  the logs are kept in results/make_up_attempt*.txt. Each failure was fixed from the real log.
- Where the assistant's suggestion did not match my setup I changed it, for example I confirmed
  the secret key names and the /parse request field in my own code before using them.

## Limits
- I did not copy results or claims I could not verify by running them.
