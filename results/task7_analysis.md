# Task 7: Performance, cost and review

All numbers below are MEASURED unless marked (assumption). Source files are in results/.
Load test: tools/locustfile.py, 4 users, spawn rate 4, run time 2 min, against the Ingress
(http://localhost:8081) instead of 8080, so that load reaches both replicas. 2 replicas of kd-parser, model v1.

## 1. Measurements (results/task7_loadtest_*.csv, task7_loadtest_console.txt, task7_top_pods.txt)

| Measurement | Value | Source |
|---|---|---|
| Requests | 315 | task7_loadtest_stats.csv |
| Failures / error rate | 0 / 0.00 % (limit 1 %) | task7_loadtest_failures.csv (empty) |
| p50 latency | 1,400 ms | stats.csv (Locust approximated percentiles) |
| p95 latency | 2,300 ms (limit 5,000 ms) | stats.csv |
| p99 latency | 2,400 ms | stats.csv |
| Average / max latency | 1,508 ms / 3,320 ms | stats.csv |
| Throughput | 2.64 requests/s | stats.csv |
| CPU per pod (kubectl top, 4 samples) | 777m to 999m (limit 1000m) | task7_top_pods.txt |
| Memory per pod | 358 Mi to 520 Mi (limit 1 GiB) | task7_top_pods.txt |
| Cold start (median of 3, from Task 4) | 17 s (runs: 14, 17, 17 s) | task4_cold_start.txt |
| Requests per replica | 195 and 120 (61.9 % / 38.1 %) | console, "per_replica" |

Note: in sample 1 (25 s after start) metrics-server listed only one pod; samples 2 to 5 list both.

## 2. Cost per 1,000 requests (rate_card.json: 3.50 INR per vCPU-hour, 0.45 INR per GiB-hour)

Each replica is billed for its limits (1 CPU, 1 GiB) for every hour it runs.

1. Cost of one replica per hour = 1 vCPU x 3.50 + 1 GiB x 0.45 = 3.50 + 0.45 = 3.95 INR
2. Running replicas = 2 (deployment.yaml replicas: 2; both pods seen Running in kubectl top)
3. Hourly cost of all replicas = 2 x 3.95 = 7.90 INR
4. Requests served per hour = 2.6408 req/s x 3600 s = 9,506.9 requests
   (assumption: the measured rate would hold for a full hour)
5. Cost per 1,000 requests = 7.90 / 9,506.9 x 1000 = 0.831 INR

Estimated cost only; no real cloud charge. The replicas are billed whether or not they are busy.

## 3. SLO and error budget

- SLO: 99 % of /parse requests succeed (HTTP 200).
- Window: one load-test run (315 requests).
- Error budget = (100 % - 99 %) x 315 = 3.15 requests, i.e. at most 3 failed requests.
- Used: 0 failed requests = 0 of 3.15 (0 %). Remaining: 100 %.
- Latency check (handout threshold, not a second SLO): p95 2,300 ms against 5,000 ms.

## 4. Review table

| Component or concern | Limitation you found | Improvement you propose | Evidence (a measured number) |
|---|---|---|---|
| Data and storage | One SeaweedFS replica on a 5 Gi volume; deleting the cluster deletes the models bucket | Keep the model in the GitHub Release (done) and re-seed on make up; use replicated storage in a real cloud | model.safetensors = 281,715,176 bytes; rebuilding from scratch with make up took 456 s |
| Model quality | Student copies the teacher's mistakes (e.g. V003 place/time swapped); cleaning only checks format | Filter or correct teacher labels, add more data | Student v1: json_validity 100.0, full_frame 52.0 (teacher 50.0), date accuracy 81.0 |
| Latency and throughput | CPU-only generation of up to 64 tokens per request | Stop generation at the closing brace, quantise or export the model, batch requests | p50 1,400 ms, p95 2,300 ms, 2.64 req/s with 4 users |
| Resource utilisation | CPU sits at the limit under load (throttling); memory only half used | Raise the CPU limit or add replicas; lower the memory request | CPU 999m of 1000m; memory 520 Mi of 1024 Mi |
| Reliability and recovery | Cold start after losing all pods is slow; traffic split between pods is uneven | Keep at least 2 ready pods, add a startup probe, a smaller model download | Cold start median 17 s; requests split 195 / 120 |
| Security and cost | Billed for limits when idle; secrets must stay out of the repo | Scale to 1 replica when idle, faster inference lowers cost per request; secret is random per cluster and gitleaks reports nothing | 0.831 INR per 1,000 requests at 2 replicas; CI secrets job green |

## 5. Measured vs assumed
- Measured: everything in section 1, the CI gitleaks result, the 456 s make up time.
- Assumed: the one-hour extrapolation in step 4, that both replicas ran for the whole test, and the rate card prices (hypothetical).
