# optimum-rlnc-bench

Independent benchmark of the Optimum mump2p RLNC propagation layer against plain GossipSub. All measurements taken on the public `getoptimum/optimum-dev-setup-guide` Docker stack with no modifications to the upstream code (one bug-fix PR is open at upstream: getoptimum/optimum-dev-setup-guide#75). 32 datapoints total, results in `results-n8/combined/report-n8.md`.

## What this is

A reproducible bench that drives an 8-node Optimum mesh through a (payload-size × packet-loss%) matrix and records:
- per-message propagation latency (from upstream `mump2p` trace events)
- delivery rate to all subscribers
- per-node network egress
- shard counts (RLNC mode only)

Both `optimum` (RLNC) and `gossipsub` modes are tested. Topology is forced to multi-hop via `MeshDegreeMax=4` on N=8 so that intermediate nodes have a real chance to recode (or in gossipsub's case, forward) coded packets.

## What this is not

- Not a verdict on Optimum or RaptorCast or any other propagation layer.
- Not a marketing benchmark — payload mixes and loss profiles are chosen to surface where coded propagation matters, not to maximize headline numbers.
- Not measured on real validator load. All payloads are synthetic random data published via the proxy REST endpoint.

## Headline finding (from `results-n8/combined/report-n8.md`)

| payload | loss | optimum delivery | gossipsub delivery |
|---|---|---|---|
| 1 MB | 0% | 100% | 14% |
| **1 MB** | **5%** | **100%** | **43%** |
| **1 MB** | **10%** | **100%** | **14%** |
| 1 MB | 20% | 12% | 15% |
| 2.4 MB | 5% | 100% | 14% |
| 2.4 MB | 10% | 76% | 23% |

Optimum delivers 100% in 11 of 16 (mode × loss%) conditions. Gossipsub at the same topology (`MeshDegreeMax=4`, N=8) delivers 100% in 0 of 16. The clearest single condition is 1 MB / 10% loss: optimum 100% / gossipsub 14% — a 7× delivery gap.

At zero loss gossipsub is faster (1.7 ms vs 0.1 ms p50 on 1 KB). RLNC pays a shard-encoding tax that only pays back under loss.

Both modes collapse at ≥20% loss × ≥1 MB payload. RLNC has a real but higher ceiling.

Full numbers, methodology notes, and known limits in [`results-n8/combined/report-n8.md`](results-n8/combined/report-n8.md).

## Repository layout

```
.
├── README.md                       — this file
├── LICENSE                         — MIT
├── bench/
│   ├── bench.py                    — matrix runner (Python stdlib only)
│   └── report.py                   — CSV → markdown renderer
├── docker/
│   ├── docker-compose.override.yml — guard-rails (CPU/mem caps, log rotation, 127.0.0.1 binds)
│   ├── docker-compose.monitoring.yml — standalone Prometheus on optimum-network
│   └── docker-compose.n8.yml       — N=8 multi-hop with MeshDegreeMax=4
└── results-n8/
    ├── combined/
    │   ├── all-results.csv         — 32 rows of bench results
    │   └── report-n8.md            — generated report with A/B comparison
    ├── raw/                        — per-run summary.json files
    ├── config-optimum.json
    └── config-gossipsub.json
```

**Note on raw artefacts.** Only the per-run `summary.json` files are checked in; the underlying `trace.tsv` and `data.tsv` files from `p2p-multi-subscribe` are not, because their total size is roughly 100 MB and they bloat git history without adding much value beyond what `summary.json` already records (per-message latency stats, delivery counts, shard counters, Prometheus deltas). Full from-scratch reproduction is via running `bench/bench.py` against a fresh stack as described below. If you need the raw TSVs for a specific analysis (e.g. per-shard NEW_SHARD trace), open an issue and I will publish them as a release attachment.

## How to reproduce

### Prerequisites

- Linux host (tested on Ubuntu 22.04 LTS, x86_64)
- Docker + Docker Compose v2 (tested with 29.3.0)
- Go 1.25+ (tested with 1.26.3 from snap) for building the bench's gRPC client binaries
- `sudo` access for `tc` / `nsenter` (used to apply scoped packet loss via the host without modifying containers)
- Python 3.10+

### Steps

1. Clone the upstream Optimum dev setup repo:
   ```
   git clone https://github.com/getoptimum/optimum-dev-setup-guide
   cd optimum-dev-setup-guide
   ```
2. Copy this bench's docker compose files into that directory:
   ```
   cp /path/to/optimum-rlnc-bench/docker/*.yml .
   ```
3. Apply the multi-publish bug-fix from upstream PR getoptimum/optimum-dev-setup-guide#75 (or `git fetch origin pull/75/head:pr75 && git checkout pr75`).
4. Generate bootstrap identity:
   ```
   bash script/generate-identity.sh
   ```
5. Copy `.env.example → .env` and replace `BOOTSTRAP_PEER_ID` with the value printed by step 4. Pin image versions in `.env`:
   ```
   PROXY_VERSION=v0.0.1-rc16
   P2P_NODE_VERSION=v0.0.1-rc16
   ```
6. Build the bench's Go clients:
   ```
   make build
   ```
7. Write the 8-node ips file:
   ```
   for i in 1 2 3 4 5 6 7 8; do echo 127.0.0.1:$((33220+i)); done > ips.txt
   ```
8. Bring up the N=8 stack (choose mode):
   ```
   # optimum mode
   docker compose -f docker-compose-optimum.yml \
                  -f docker-compose.n8.yml \
                  -f docker-compose.monitoring.yml up -d

   # OR gossipsub mode
   docker compose -f docker-compose-gossipsub.yml \
                  -f docker-compose.n8.yml \
                  -f docker-compose.monitoring.yml up -d
   ```
9. Run the matrix:
   ```
   python3 /path/to/optimum-rlnc-bench/bench/bench.py \
       --mode optimum \
       --sizes 1KB,100KB,1MB,2.4MB \
       --loss 0,5,10,20 \
       --out my-results
   ```
   For the gossipsub side, set `--mode gossipsub` and use the gossipsub compose file in step 8.

10. Generate the report:
    ```
    python3 /path/to/optimum-rlnc-bench/bench/report.py my-results/<timestamp>/results.csv
    ```

### Configuration via env

`bench.py` looks for these env vars:

- `OPTIMUM_DEV_REPO` — path to the cloned `optimum-dev-setup-guide` directory (default: `./optimum-dev-setup-guide`, resolved against your current working directory)
- `BENCH_PROM_URL` — Prometheus URL (default: `http://127.0.0.1:9095`)
- `BENCH_PROXY_URL` — Optimum proxy REST URL (default: `http://127.0.0.1:8081`)

## Methodology summary

- **Topology**: 8 P2P nodes on a Docker bridge (`172.28.0.0/16`). Bootstrap from p2pnode-1. `MeshDegreeMax=4`, `MeshDegreeMin=3`, `MeshDegreeTarget=3` on every node, applied via env vars for both `OPTIMUM_MESH_*` and `GOSSIPSUB_MESH_*` to keep the cap consistent across modes.
- **Publisher**: REST `POST /api/v1/publish` to the Optimum proxy with `message_length` field — the proxy / p2pnode generates the random payload server-side. Bypasses the bidi-stream deadlock in the bundled `multi-publish` Go binary (see upstream PR #75).
- **Subscribers**: `grpc_p2p_client/p2p-multi-subscribe` connected to all 8 p2pnode sidecars in parallel.
- **Packet loss**: applied via `tc qdisc … prio` with a netem child on the impaired band, and `u32` filters matching dst addresses `172.28.0.12/30` (p2pnodes 1-4) and `172.28.0.16/29` (p2pnodes 5-8). Loss is symmetric (every p2pnode container has loss applied to its eth0 for outbound traffic to other p2pnodes). Proxy↔p2pnode traffic is NOT impaired, so the publish path itself is unaffected.
- **Latency**: per-(message_id, subscriber) `DELIVER_MESSAGE.timestamp - PUBLISH_MESSAGE.timestamp` from the upstream `mump2p` trace TSV.
- **Bandwidth**: Prometheus `process_network_transmit_bytes_total` delta per p2pnode container, summed.
- **Counts per run**: 50 (1 KB), 40 (100 KB), 20 (1 MB), 10 (2.4 MB). Scaled so each run produces comparable volume.

Full caveats and known limitations in [`results-n8/combined/report-n8.md`](results-n8/combined/report-n8.md).

## Versions tested

- `getoptimum/p2pnode:v0.0.1-rc16` (commit `1a02aec`)
- `getoptimum/proxy:v0.0.1-rc16` (commit `1a02aec`)
- upstream `optimum-dev-setup-guide@bd8c0b8` + PR #75 (multi-publish bidi deadlock fix)

## Related

- Multi-publish bidi deadlock bug report and patch: [upstream issue #74](https://github.com/getoptimum/optimum-dev-setup-guide/issues/74) / [PR #75](https://github.com/getoptimum/optimum-dev-setup-guide/pull/75).
- Companion content post (RLNC vs Monad RaptorCast) — pending; will link from this repo when published.

## License

MIT. See [`LICENSE`](LICENSE).
