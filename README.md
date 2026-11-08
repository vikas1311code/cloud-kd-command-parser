# Knowledge Distillation and Deployment of a Lightweight Command-Parsing LM on a Local Cloud

CS3081 Cloud Computing mini project.
Name: Vikas Pandey | Roll no.: 230101004 | Section A | B.Tech CSE, Indian Institute of Information Technology

## Links
- GitHub repository: https://github.com/vikas1311code/cloud-kd-command-parser
- Release with model v1, tokenizer, version info, checksums: https://github.com/vikas1311code/cloud-kd-command-parser/releases/tag/model-v1
- Release with model v2: https://github.com/vikas1311code/cloud-kd-command-parser/releases/tag/model-v2
- CI run that fails the quality gate (untrained Pythia-70M): https://github.com/vikas1311code/cloud-kd-command-parser/actions/runs/42463158533
- Passing CI run (model v1): https://github.com/vikas1311code/cloud-kd-command-parser/actions/runs/42462903229
- Final submission commit is tagged `final`.
- Report: report/report.pdf. AI use: AI_USE.md. Run links: results/ci_runs.txt.

## What this is
A teacher (phi3.5 via Ollama, temperature 0, seed 42) labels 3,000 commands as JSON with the keys intent, date, time, place.
After cleaning, Pythia-70M is trained on the first 1,500 cleaned replies (sequence-level distillation, CPU).
The model is stored in SeaweedFS (S3), served by a FastAPI service and deployed on k3d (Kubernetes).

## Layout
- cluster/k3d.yaml, k8s/: cluster and Kubernetes manifests (SeaweedFS, labelling jobs, Deployment, Service, Ingress, HPA)
- worker/: labelling worker and clean.py. prompts/: teacher prompt
- training/: train.py, config.yaml (v1), config_v2.yaml (v2), loss.csv, loss_v2.csv, Dockerfile
- eval/: gen_teacher.py, gen_student.py, make_table.py. tools/score.py: official scorer
- service/: FastAPI app and Dockerfile. tools/locustfile.py: load test
- network/: subnets.md, nacl.json. tools/nacl_sim.py: NACL checker
- scripts/: make_up.py, upload_model.py, setup_buckets.py and the Task 3/4 test scripts
- tests/: unit tests. .github/workflows/ci.yml: CI
- results/: all logs, score reports, Locust output, command outputs

## Prerequisites
Docker Desktop, k3d, kubectl, make, Python 3.12 or newer. Ollama and phi3.5 are only needed to re-run the teacher.

## Build and deploy (two commands from a fresh clone)
    pip install -r requirements-dev.txt
    make up

make up creates the k3d cluster, a random S3 secret (nothing secret is stored in Git), SeaweedFS, the buckets,
downloads model v1 from the GitHub Release (checksum verified) into the bucket, builds and imports the image,
deploys, and checks /readyz and /parse. The service is reachable at http://localhost:8081 (Ingress).
To also upload v2 (needed for the rolling-update test): python scripts/make_up.py --versions v1 v2

## Test
    ruff check .
    python -m unittest discover -s tests -v
    python tools/score.py PREDICTIONS.jsonl data/validation.jsonl --min-validity 95
    locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8081 --csv results/loadtest
    python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
Example request:
    curl -X POST http://localhost:8081/parse -H "Content-Type: application/json" -d "{\"text\": \"set an alarm for seven thirty am tomorrow\"}"
The Task 4 scripts (cold start, load balancing, pod delete, rolling update, scale test) are in scripts/task4_*.py.

## Train and evaluate
    make train                                   (v1, seed 42, 3 epochs)
    make train CONFIG=training/config_v2.yaml    (v2, seed 43, 4 epochs)
    make train SUBSET=50                         (quick smoke run)
    python eval/gen_student.py --model artifacts/v1 --out results/pred_student_v1.jsonl
    python tools/score.py results/pred_student_v1.jsonl data/validation.jsonl

## Shut down
    make down
This deletes the k3d cluster (and with it SeaweedFS data). Models stay in the GitHub Releases.

## Credentials
No credentials are committed. make up creates a random SeaweedFS key and secret inside the cluster.
A gitleaks job in CI scans the whole history.

## Data
Commands are from SLURP (Bastianelli et al., EMNLP 2020), licensed CC BY 4.0. https://github.com/pswietojanski/slurp
