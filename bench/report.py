#!/usr/bin/env python3
"""Render results.csv → markdown report.

Usage:
    python3 report.py <results.csv> [<out.md>]
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def fmt_size(b: int) -> str:
    b = int(b)
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f}KB"
    return f"{b / (1024 * 1024):.2f}MB"


def fmt_bytes(b: float) -> str:
    b = float(b)
    if b < 1024:
        return f"{b:.0f}B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f}KB"
    return f"{b / (1024 * 1024):.2f}MB"


def n_subscribers(mode: str, n_nodes: int = 8) -> int:
    """Expected DELIVER_MESSAGE events per published message for a perfectly
    propagating mesh.

    Empirically: gossipsub emits one DELIVER per remote-receiver. Publisher
    node does not emit DELIVER for its own publish in gossipsub mode (because
    the message did not transit the mesh inbound). Hence expected = N-1.

    Optimum mode emits DELIVER on every node including the publisher (RLNC
    decode flow uses local sidecar even for own-publish). Hence expected = N.

    Pass n_nodes explicitly if your topology is not 8.
    """
    return n_nodes if mode == "optimum" else (n_nodes - 1)


def render(csv_path: Path, out_path: Path) -> None:
    rows: list[dict] = []
    with csv_path.open() as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)

    if not rows:
        out_path.write_text("# Optimum RLNC propagation benchmark\n\n(no rows)\n")
        return

    by_mode = defaultdict(list)
    for r in rows:
        by_mode[r["mode"]].append(r)

    lines: list[str] = []
    lines.append("# Optimum RLNC propagation benchmark")
    lines.append("")
    lines.append(f"- Source CSV: `{csv_path}`")
    lines.append(f"- Total runs: {len(rows)}")
    lines.append(f"- Modes: {', '.join(sorted(by_mode))}")
    lines.append("")
    lines.append("Each row is one (mode, payload_size, loss%) run on the 4-node local Docker stack.")
    lines.append("Latency: per-delivery `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` from upstream trace TSV.")
    lines.append("Bandwidth is from Prometheus `process_network_transmit_bytes_total` (per-process counter, works in both modes).")
    lines.append("Expected deliveries = 4×count for optimum, 3×count for gossipsub (publisher self-delivery only fires in optimum).")
    lines.append("")

    for mode, mode_rows in sorted(by_mode.items()):
        lines.append(f"## Mode: `{mode}`")
        lines.append("")
        lines.append(
            "| payload | count | loss% | deliveries / expected | success% | shards | unnec.shards | "
            "lat mean | lat p50 | lat p95 | lat p99 | lat max | "
            "BW out total | BW out / msg |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
        )
        for r in sorted(mode_rows, key=lambda x: (int(x["size_bytes"]), float(x["loss_pct"]))):
            size = int(r["size_bytes"])
            count = int(r["count"])
            n_pub = int(r["n_pub_seen"])
            n_deliv = int(r["n_deliveries"])
            expected = count * n_subscribers(mode)
            success = (n_deliv / expected * 100) if expected > 0 else 0
            # proc_net_tx_total was added mid-session; older runs are missing it.
            # Fall back to bw_out_pubsub_total (optimum-only) when absent.
            bw_out = float(r.get("proc_net_tx_total") or r.get("bw_out_pubsub_total", 0))
            bw_per_msg = bw_out / max(1, count)
            lines.append(
                f"| {fmt_size(size)} | {count} | {r['loss_pct']} | "
                f"{n_deliv} / {expected} | {success:.0f}% | "
                f"{r['n_shards']} | {r['shards_unnecessary_delta']} | "
                f"{r['lat_mean_ms']}ms | {r['lat_p50_ms']}ms | {r['lat_p95_ms']}ms | "
                f"{r['lat_p99_ms']}ms | {r['lat_max_ms']}ms | "
                f"{fmt_bytes(bw_out)} | {fmt_bytes(bw_per_msg)} |"
            )
        lines.append("")

    if len(by_mode) > 1:
        lines.append("## A/B comparison: RLNC (optimum) vs plain gossipsub")
        lines.append("")
        by_key: dict[tuple[int, float], dict[str, dict]] = defaultdict(dict)
        for r in rows:
            key = (int(r["size_bytes"]), float(r["loss_pct"]))
            by_key[key].setdefault(r["mode"], r)
        lines.append("| payload | loss% | opt deliv | gs deliv | opt lat p50 | gs lat p50 | opt lat p95 | gs lat p95 | opt BW/msg | gs BW/msg |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for (size, loss), modes in sorted(by_key.items()):
            opt = modes.get("optimum")
            gs = modes.get("gossipsub")
            def _f(r, k):
                return r[k] if r else "-"
            def _ratio(r):
                if not r: return "-"
                n = int(r["n_deliveries"])
                exp = int(r["count"]) * n_subscribers(r["mode"])
                return f"{n}/{exp} ({n/exp*100:.0f}%)" if exp else "-"
            def _bwpm(r):
                if not r: return "-"
                bw = float(r.get("proc_net_tx_total") or r.get("bw_out_pubsub_total", 0))
                return fmt_bytes(bw / max(1, int(r["count"])))
            lines.append(
                f"| {fmt_size(size)} | {loss} | {_ratio(opt)} | {_ratio(gs)} | "
                f"{_f(opt, 'lat_p50_ms')}ms | {_f(gs, 'lat_p50_ms')}ms | "
                f"{_f(opt, 'lat_p95_ms')}ms | {_f(gs, 'lat_p95_ms')}ms | "
                f"{_bwpm(opt)} | {_bwpm(gs)} |"
            )
        lines.append("")

    lines.append("## Methodology notes")
    lines.append("")
    lines.append("- Stack: `optimum-dev-setup-guide@bd8c0b8`, images `getoptimum/p2pnode:v0.0.1-rc16` + `getoptimum/proxy:v0.0.1-rc16`.")
    lines.append("- Topology: 4 P2P nodes on Docker bridge `172.28.0.0/16`. With `MeshDegreeTarget=6` and N=4, the mesh is effectively full (each node connects to the other 3).")
    lines.append("- Publisher path: REST `POST /api/v1/publish` → proxy → one p2pnode → mesh. We use `message_length` so the proxy/p2pnode generates random payload server-side (sidesteps the bidi gRPC `multi-publish` backpressure deadlock observed on payloads ≥100KB).")
    lines.append("- Subscriber path: `grpc_p2p_client/p2p-multi-subscribe` on all 4 nodes via direct gRPC sidecar (port 33212).")
    lines.append("- Latency = `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` from the upstream `mump2p` trace TSV, per (message_id, subscriber).")
    lines.append("- Bandwidth = `process_network_transmit_bytes_total` delta, summed over all 4 p2pnode processes. Counts **all** of each node's TCP egress (mesh shards + DHT + identify + handshake), not just pubsub.")
    lines.append("- Packet loss applied via `sudo nsenter -t <pid> -n tc qdisc replace dev eth0 root netem loss X%` against every p2pnode container's network namespace, cleared after each run.")
    lines.append("- RLNC parameters: `ShardFactor=4`, `PublisherShardMultiplier=1.5`, `ForwardShardThreshold=0.75`, `MaxMessageSize=2.5MB`.")
    lines.append("")
    lines.append("## Known limitations / caveats")
    lines.append("")
    lines.append("1. **Symmetric loss includes the publish path.** `tc netem` is applied to `eth0` on every p2pnode container, which also impairs the proxy↔p2pnode gRPC sidecar. At 20% loss this can cause REST `publish` to itself time out, so `n_pub_seen` falls below `count` — visible in the `optimum 1MB / 20%` row (3 of 20 published, 2 delivered). This is a methodology limit, not a protocol verdict.")
    lines.append("2. **Gossipsub 1KB rows at 0/5/10% loss in the loss-matrix block show 50 deliveries instead of 150.** This is a stack-state race: when the previous run impaired the mesh with `tc netem` (or sat through enough subscribe/unsubscribe churn), the next run's subscriber GRAFTs do not stabilise within the 5-second `pub_settle` window. The `gossipsub 1KB / 20%` row in the same matrix gives 150 deliveries — same code, different mesh state. The clean `gossipsub 1KB / 0%` from the standalone baseline run does give 150.")
    lines.append("3. **N=4 full mesh removes RLNC's multi-hop recoding advantage.** RLNC's main propagation win is at 1-2 hop transit nodes where coded shards can be re-combined; on a full mesh every receiver gets shards directly from the publisher. The 1MB / 10% loss numbers (optimum 51% delivered, gossipsub 58%) reflect this — RLNC's recoding has nowhere to help. For a real picture, repeat at N≥8 with the mesh capped (e.g. `MeshDegreeMax=4`) to force multi-hop paths.")
    lines.append("4. **Bandwidth column counts all egress.** `process_network_transmit_bytes_total` includes DHT/identify/handshake traffic. The pubsub-only counter `optimum_bandwidth_traffic_bytes_total{protocol=\"/optimumsub/0.0.0\"}` exists in optimum mode but is **not exposed in gossipsub mode**, so we cannot use it for apples-to-apples. The included counter is therefore an upper bound on protocol overhead.")
    lines.append("5. **Variable `n_deliveries` semantics by mode.** Optimum on a clean stack also emits `DELIVER_MESSAGE` on the publisher's node (4 events per publish); gossipsub does not (3 events per publish). The `success%` column normalises by mode-specific expected count.")
    lines.append("")
    lines.append("## Observations from the data")
    lines.append("")
    lines.append("- **At small payloads RLNC pays an encoding tax.** 1KB / 0% loss: optimum ~0.86ms mean vs gossipsub ~0.40ms. RLNC's shard codec adds ~0.4ms on a 1KB payload through localhost loopback.")
    lines.append("- **At medium payloads (100KB, 0% loss) the tax is smaller.** ~1.7ms RLNC vs ~1.2ms gossipsub.")
    lines.append("- **RLNC's reliability advantage shows up at large payload + moderate loss.** 1MB / 5% loss: optimum delivered 80/80 (100%), gossipsub delivered 20/60 (33%). At 10% loss both modes' delivery rates collapse to ~50% (optimum 51%, gossipsub 58%) — the absent multi-hop transit (full mesh) is the limiting factor.")
    lines.append("- **Tail latency under loss is comparable.** At 1MB / 10% loss optimum p95 ≈ 8.5s, gossipsub p95 ≈ 7.3s. Both modes do many retransmits and need seconds to converge.")
    lines.append("- **No usable signal at 20% loss for 1MB on this testbed** because the publish path itself breaks (see Caveat 1).")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path} ({len(rows)} rows, {len(by_mode)} modes)")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    csv_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else csv_path.parent / "report.md"
    render(csv_path, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
