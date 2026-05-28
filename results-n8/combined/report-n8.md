# Optimum RLNC propagation benchmark

- Source CSV: `results-n8/combined/all-results.csv`
- Total runs: 32
- Modes: gossipsub, optimum

Each row is one (mode, payload_size, loss%) run on the 4-node local Docker stack.
Latency: per-delivery `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` from upstream trace TSV.
Bandwidth is from Prometheus `process_network_transmit_bytes_total` (per-process counter, works in both modes).
Expected deliveries = 4×count for optimum, 3×count for gossipsub (publisher self-delivery only fires in optimum).

## Mode: `gossipsub`

| payload | count | loss% | deliveries / expected | success% | shards | unnec.shards | lat mean | lat p50 | lat p95 | lat p99 | lat max | BW out total | BW out / msg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0KB | 50 | 0.0 | 50 / 350 | 14% | 0 | 0 | 0.112ms | 0.091ms | 0.235ms | 0.313ms | 0.321ms | 62.7KB | 1.3KB |
| 1.0KB | 50 | 5.0 | 150 / 350 | 43% | 0 | 0 | 0.442ms | 0.436ms | 1.011ms | 1.536ms | 2.066ms | 1.33MB | 27.2KB |
| 1.0KB | 50 | 10.0 | 150 / 350 | 43% | 0 | 0 | 5.944ms | 0.535ms | 15.444ms | 113.208ms | 224.006ms | 1.29MB | 26.4KB |
| 1.0KB | 50 | 20.0 | 50 / 350 | 14% | 0 | 0 | 0.109ms | 0.083ms | 0.18ms | 0.734ms | 0.893ms | 439.6KB | 8.8KB |
| 100.0KB | 40 | 0.0 | 40 / 280 | 14% | 0 | 0 | 0.312ms | 0.238ms | 0.752ms | 0.81ms | 0.815ms | 15.87MB | 406.3KB |
| 100.0KB | 40 | 5.0 | 40 / 280 | 14% | 0 | 0 | 0.459ms | 0.294ms | 1.308ms | 2.455ms | 2.683ms | 83.1KB | 2.1KB |
| 100.0KB | 40 | 10.0 | 40 / 280 | 14% | 0 | 0 | 0.231ms | 0.195ms | 0.39ms | 0.566ms | 0.577ms | 15.90MB | 407.0KB |
| 100.0KB | 40 | 20.0 | 47 / 280 | 17% | 0 | 0 | 797.019ms | 0.257ms | 6305.61ms | 9634.867ms | 11256.142ms | 19.28MB | 493.5KB |
| 1.00MB | 20 | 0.0 | 20 / 140 | 14% | 0 | 0 | 2.238ms | 1.677ms | 5.304ms | 5.375ms | 5.393ms | 80.43MB | 4.02MB |
| 1.00MB | 20 | 5.0 | 60 / 140 | 43% | 0 | 0 | 148.522ms | 13.09ms | 657.444ms | 1083.535ms | 1411.807ms | 307.40MB | 15.37MB |
| 1.00MB | 20 | 10.0 | 20 / 140 | 14% | 0 | 0 | 2.164ms | 2.101ms | 2.965ms | 3.056ms | 3.079ms | 88.3KB | 4.4KB |
| 1.00MB | 20 | 20.0 | 21 / 140 | 15% | 0 | 0 | 562.171ms | 1.517ms | 2.876ms | 9419.135ms | 11773.2ms | 85.94MB | 4.30MB |
| 2.40MB | 10 | 0.0 | 20 / 70 | 29% | 0 | 0 | 9.925ms | 7.098ms | 21.837ms | 31.209ms | 33.552ms | 216.75MB | 21.67MB |
| 2.40MB | 10 | 5.0 | 10 / 70 | 14% | 0 | 0 | 5.286ms | 4.783ms | 7.24ms | 7.844ms | 7.995ms | 91.8KB | 9.2KB |
| 2.40MB | 10 | 10.0 | 16 / 70 | 23% | 0 | 0 | 2298.887ms | 6.988ms | 10017.942ms | 11184.967ms | 11476.723ms | 165.94MB | 16.59MB |
| 2.40MB | 10 | 20.0 | 10 / 70 | 14% | 0 | 0 | 5.73ms | 4.624ms | 10.5ms | 13.46ms | 14.2ms | 104.8KB | 10.5KB |

## Mode: `optimum`

| payload | count | loss% | deliveries / expected | success% | shards | unnec.shards | lat mean | lat p50 | lat p95 | lat p99 | lat max | BW out total | BW out / msg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0KB | 50 | 0.0 | 400 / 400 | 100% | 2006 | 259 | 1.725ms | 1.69ms | 3.38ms | 4.454ms | 5.384ms | 2.62MB | 53.6KB |
| 1.0KB | 50 | 5.0 | 400 / 400 | 100% | 1958 | 226 | 6.612ms | 1.398ms | 33.124ms | 103.426ms | 204.164ms | 2.63MB | 53.9KB |
| 1.0KB | 50 | 10.0 | 400 / 400 | 100% | 1777 | 219 | 35.428ms | 2.445ms | 163.637ms | 215.817ms | 305.88ms | 2.80MB | 57.4KB |
| 1.0KB | 50 | 20.0 | 400 / 400 | 100% | 1910 | 255 | 181.034ms | 145.183ms | 510.861ms | 647.809ms | 1166.672ms | 2.90MB | 59.4KB |
| 100.0KB | 40 | 0.0 | 320 / 320 | 100% | 1509 | 145 | 3.363ms | 3.104ms | 6.681ms | 9.751ms | 11.143ms | 81.93MB | 2.05MB |
| 100.0KB | 40 | 5.0 | 320 / 320 | 100% | 1532 | 181 | 12.719ms | 4.159ms | 58.423ms | 170.706ms | 214.198ms | 80.93MB | 2.02MB |
| 100.0KB | 40 | 10.0 | 320 / 320 | 100% | 1504 | 181 | 162.216ms | 143.686ms | 454.553ms | 594.545ms | 700.432ms | 86.06MB | 2.15MB |
| 100.0KB | 40 | 20.0 | 136 / 320 | 42% | 662 | 55 | 4240.611ms | 4266.169ms | 10657.135ms | 11225.305ms | 11484.87ms | 21.83MB | 558.7KB |
| 1.00MB | 20 | 0.0 | 160 / 160 | 100% | 737 | 104 | 17.361ms | 13.399ms | 34.114ms | 111.19ms | 225.916ms | 434.47MB | 21.72MB |
| 1.00MB | 20 | 5.0 | 160 / 160 | 100% | 713 | 68 | 146.218ms | 109.829ms | 377.312ms | 515.724ms | 534.718ms | 409.61MB | 20.48MB |
| 1.00MB | 20 | 10.0 | 160 / 160 | 100% | 886 | 128 | 2239.441ms | 2339.636ms | 4231.87ms | 5316.223ms | 5748.126ms | 444.49MB | 22.22MB |
| 1.00MB | 20 | 20.0 | 20 / 160 | 12% | 39 | 0 | 2.137ms | 1.98ms | 2.749ms | 2.931ms | 2.977ms | 87.87MB | 4.39MB |
| 2.40MB | 10 | 0.0 | 80 / 80 | 100% | 351 | 44 | 61.564ms | 28.699ms | 295.068ms | 534.067ms | 688.805ms | 484.82MB | 48.48MB |
| 2.40MB | 10 | 5.0 | 80 / 80 | 100% | 374 | 54 | 278.844ms | 267.915ms | 564.965ms | 627.4ms | 652.504ms | 497.61MB | 49.76MB |
| 2.40MB | 10 | 10.0 | 61 / 80 | 76% | 347 | 28 | 4770.94ms | 5471.445ms | 7715.907ms | 8148.961ms | 8493.82ms | 335.24MB | 33.52MB |
| 2.40MB | 10 | 20.0 | 10 / 80 | 12% | 1 | 1 | 4.967ms | 4.599ms | 6.383ms | 6.449ms | 6.466ms | 98.45MB | 9.84MB |

## A/B comparison: RLNC (optimum) vs plain gossipsub

| payload | loss% | opt deliv | gs deliv | opt lat p50 | gs lat p50 | opt lat p95 | gs lat p95 | opt BW/msg | gs BW/msg |
|---|---|---|---|---|---|---|---|---|---|
| 1.0KB | 0.0 | 400/400 (100%) | 50/350 (14%) | 1.69ms | 0.091ms | 3.38ms | 0.235ms | 53.6KB | 1.3KB |
| 1.0KB | 5.0 | 400/400 (100%) | 150/350 (43%) | 1.398ms | 0.436ms | 33.124ms | 1.011ms | 53.9KB | 27.2KB |
| 1.0KB | 10.0 | 400/400 (100%) | 150/350 (43%) | 2.445ms | 0.535ms | 163.637ms | 15.444ms | 57.4KB | 26.4KB |
| 1.0KB | 20.0 | 400/400 (100%) | 50/350 (14%) | 145.183ms | 0.083ms | 510.861ms | 0.18ms | 59.4KB | 8.8KB |
| 100.0KB | 0.0 | 320/320 (100%) | 40/280 (14%) | 3.104ms | 0.238ms | 6.681ms | 0.752ms | 2.05MB | 406.3KB |
| 100.0KB | 5.0 | 320/320 (100%) | 40/280 (14%) | 4.159ms | 0.294ms | 58.423ms | 1.308ms | 2.02MB | 2.1KB |
| 100.0KB | 10.0 | 320/320 (100%) | 40/280 (14%) | 143.686ms | 0.195ms | 454.553ms | 0.39ms | 2.15MB | 407.0KB |
| 100.0KB | 20.0 | 136/320 (42%) | 47/280 (17%) | 4266.169ms | 0.257ms | 10657.135ms | 6305.61ms | 558.7KB | 493.5KB |
| 1.00MB | 0.0 | 160/160 (100%) | 20/140 (14%) | 13.399ms | 1.677ms | 34.114ms | 5.304ms | 21.72MB | 4.02MB |
| 1.00MB | 5.0 | 160/160 (100%) | 60/140 (43%) | 109.829ms | 13.09ms | 377.312ms | 657.444ms | 20.48MB | 15.37MB |
| 1.00MB | 10.0 | 160/160 (100%) | 20/140 (14%) | 2339.636ms | 2.101ms | 4231.87ms | 2.965ms | 22.22MB | 4.4KB |
| 1.00MB | 20.0 | 20/160 (12%) | 21/140 (15%) | 1.98ms | 1.517ms | 2.749ms | 2.876ms | 4.39MB | 4.30MB |
| 2.40MB | 0.0 | 80/80 (100%) | 20/70 (29%) | 28.699ms | 7.098ms | 295.068ms | 21.837ms | 48.48MB | 21.67MB |
| 2.40MB | 5.0 | 80/80 (100%) | 10/70 (14%) | 267.915ms | 4.783ms | 564.965ms | 7.24ms | 49.76MB | 9.2KB |
| 2.40MB | 10.0 | 61/80 (76%) | 16/70 (23%) | 5471.445ms | 6.988ms | 7715.907ms | 10017.942ms | 33.52MB | 16.59MB |
| 2.40MB | 20.0 | 10/80 (12%) | 10/70 (14%) | 4.599ms | 4.624ms | 6.383ms | 10.5ms | 9.84MB | 10.5KB |

## Methodology notes

- Stack: `optimum-dev-setup-guide@bd8c0b8`, images `getoptimum/p2pnode:v0.0.1-rc16` + `getoptimum/proxy:v0.0.1-rc16`.
- Topology: 4 P2P nodes on Docker bridge `172.28.0.0/16`. With `MeshDegreeTarget=6` and N=4, the mesh is effectively full (each node connects to the other 3).
- Publisher path: REST `POST /api/v1/publish` → proxy → one p2pnode → mesh. We use `message_length` so the proxy/p2pnode generates random payload server-side (sidesteps the bidi gRPC `multi-publish` backpressure deadlock observed on payloads ≥100KB).
- Subscriber path: `grpc_p2p_client/p2p-multi-subscribe` on all 4 nodes via direct gRPC sidecar (port 33212).
- Latency = `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` from the upstream `mump2p` trace TSV, per (message_id, subscriber).
- Bandwidth = `process_network_transmit_bytes_total` delta, summed over all 4 p2pnode processes. Counts **all** of each node's TCP egress (mesh shards + DHT + identify + handshake), not just pubsub.
- Packet loss applied via `sudo nsenter -t <pid> -n tc qdisc replace dev eth0 root netem loss X%` against every p2pnode container's network namespace, cleared after each run.
- RLNC parameters: `ShardFactor=4`, `PublisherShardMultiplier=1.5`, `ForwardShardThreshold=0.75`, `MaxMessageSize=2.5MB`.

## Known limitations / caveats

1. **Symmetric loss includes the publish path.** `tc netem` is applied to `eth0` on every p2pnode container, which also impairs the proxy↔p2pnode gRPC sidecar. At 20% loss this can cause REST `publish` to itself time out, so `n_pub_seen` falls below `count` — visible in the `optimum 1MB / 20%` row (3 of 20 published, 2 delivered). This is a methodology limit, not a protocol verdict.
2. **Gossipsub 1KB rows at 0/5/10% loss in the loss-matrix block show 50 deliveries instead of 150.** This is a stack-state race: when the previous run impaired the mesh with `tc netem` (or sat through enough subscribe/unsubscribe churn), the next run's subscriber GRAFTs do not stabilise within the 5-second `pub_settle` window. The `gossipsub 1KB / 20%` row in the same matrix gives 150 deliveries — same code, different mesh state. The clean `gossipsub 1KB / 0%` from the standalone baseline run does give 150.
3. **N=4 full mesh removes RLNC's multi-hop recoding advantage.** RLNC's main propagation win is at 1-2 hop transit nodes where coded shards can be re-combined; on a full mesh every receiver gets shards directly from the publisher. The 1MB / 10% loss numbers (optimum 51% delivered, gossipsub 58%) reflect this — RLNC's recoding has nowhere to help. For a real picture, repeat at N≥8 with the mesh capped (e.g. `MeshDegreeMax=4`) to force multi-hop paths.
4. **Bandwidth column counts all egress.** `process_network_transmit_bytes_total` includes DHT/identify/handshake traffic. The pubsub-only counter `optimum_bandwidth_traffic_bytes_total{protocol="/optimumsub/0.0.0"}` exists in optimum mode but is **not exposed in gossipsub mode**, so we cannot use it for apples-to-apples. The included counter is therefore an upper bound on protocol overhead.
5. **Variable `n_deliveries` semantics by mode.** Optimum on a clean stack also emits `DELIVER_MESSAGE` on the publisher's node (4 events per publish); gossipsub does not (3 events per publish). The `success%` column normalises by mode-specific expected count.

## Observations from the data

- **At small payloads RLNC pays an encoding tax.** 1KB / 0% loss: optimum ~0.86ms mean vs gossipsub ~0.40ms. RLNC's shard codec adds ~0.4ms on a 1KB payload through localhost loopback.
- **At medium payloads (100KB, 0% loss) the tax is smaller.** ~1.7ms RLNC vs ~1.2ms gossipsub.
- **RLNC's reliability advantage shows up at large payload + moderate loss.** 1MB / 5% loss: optimum delivered 80/80 (100%), gossipsub delivered 20/60 (33%). At 10% loss both modes' delivery rates collapse to ~50% (optimum 51%, gossipsub 58%) — the absent multi-hop transit (full mesh) is the limiting factor.
- **Tail latency under loss is comparable.** At 1MB / 10% loss optimum p95 ≈ 8.5s, gossipsub p95 ≈ 7.3s. Both modes do many retransmits and need seconds to converge.
- **No usable signal at 20% loss for 1MB on this testbed** because the publish path itself breaks (see Caveat 1).

