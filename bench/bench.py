#!/usr/bin/env python3
"""Optimum RLNC propagation benchmark.

Drives the local docker-compose mump2p stack (4 P2P nodes, optimum mode)
through a matrix of payload sizes / protocol modes / packet-loss profiles,
collects per-message latency from the official trace TSV and per-node
bandwidth from Prometheus, and emits a CSV + markdown report.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO = Path(os.environ.get(
    "OPTIMUM_DEV_REPO",
    "./optimum-dev-setup-guide",
)).resolve()
P2P_CLIENT = REPO / "grpc_p2p_client"
IPS_FILE = REPO / "ips.txt"
PROM_URL = os.environ.get("BENCH_PROM_URL", "http://127.0.0.1:9095")
PROXY_URL = os.environ.get("BENCH_PROXY_URL", "http://127.0.0.1:8081")
# Default = N=8 topology (multi-hop). Override via env if running N=4 stack.
NODES = [f"127.0.0.1:{33220+i}" for i in range(1, 9)]
NODE_CONTAINERS = [f"optimum-dev-setup-guide-p2pnode-{i}-1" for i in range(1, 9)]
NODE_API = {f"127.0.0.1:{33220+i}": f"http://127.0.0.1:{19090+i}" for i in range(1, 9)}


# ---------------------------------------------------------------------------
# Trace parsing
# ---------------------------------------------------------------------------

@dataclass
class TraceRow:
    event: str
    peer: str
    received_from: str
    message_id: str
    topic: str
    ts_ns: int


def read_trace(path: Path) -> list[TraceRow]:
    rows: list[TraceRow] = []
    with path.open() as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            try:
                ts = int(parts[5])
            except ValueError:
                continue
            rows.append(TraceRow(parts[0], parts[1], parts[2], parts[3], parts[4], ts))
    return rows


def latencies_from_trace(rows: list[TraceRow]) -> dict[str, dict]:
    publish: dict[str, int] = {}
    deliveries: dict[str, list[tuple[str, int]]] = {}
    shards_seen: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        if r.event == "PUBLISH_MESSAGE":
            publish[r.message_id] = r.ts_ns
        elif r.event == "DELIVER_MESSAGE":
            deliveries.setdefault(r.message_id, []).append((r.peer, r.ts_ns))
        elif r.event == "NEW_SHARD":
            shards_seen.setdefault(r.message_id, []).append((r.peer, r.ts_ns))

    out: dict[str, dict] = {}
    for mid, pub_ts in publish.items():
        deliv = deliveries.get(mid, [])
        latencies_ms = [(ts - pub_ts) / 1e6 for _, ts in deliv]
        out[mid] = {
            "publish_ts": pub_ts,
            "deliveries": len(deliv),
            "shards": len(shards_seen.get(mid, [])),
            "latencies_ms": latencies_ms,
        }
    return out


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    values = sorted(values)
    def pct(p: float) -> float:
        if len(values) == 1:
            return values[0]
        k = (len(values) - 1) * p
        f = int(k)
        c = min(f + 1, len(values) - 1)
        return values[f] + (values[c] - values[f]) * (k - f)
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": max(values),
    }


# ---------------------------------------------------------------------------
# Prometheus snapshots
# ---------------------------------------------------------------------------

PROM_TARGETS = {
    # Universal: per-process network counters (work in both optimum + gossipsub modes).
    "proc_net_tx_total": (
        'sum by (job, instance) (process_network_transmit_bytes_total{job="p2p-nodes"})'
    ),
    "proc_net_rx_total": (
        'sum by (job, instance) (process_network_receive_bytes_total{job="p2p-nodes"})'
    ),
    # Optimum-only: pubsub-protocol-attributed bandwidth (empty in gossipsub mode).
    "bandwidth_out_optimumsub": (
        'sum by (job, instance) (optimum_bandwidth_traffic_bytes_total'
        '{direction="outgoing",protocol="/optimumsub/0.0.0"})'
    ),
    "bandwidth_in_optimumsub": (
        'sum by (job, instance) (optimum_bandwidth_traffic_bytes_total'
        '{direction="incoming",protocol="/optimumsub/0.0.0"})'
    ),
    # Optimum-only RLNC shard counters (zero in gossipsub mode).
    "shards_total": "sum by (job, instance) (optimum_mump2p_shards_total)",
    "shards_unnecessary": "sum by (job, instance) (optimum_mump2p_shards_unnecessary_total)",
    "delivered_messages_count": (
        'sum by (job, instance) (optimum_mump2p_delivered_messages_count)'
    ),
    "delivered_messages_bytes": (
        'sum by (job, instance) (optimum_mump2p_delivered_messages_bytes)'
    ),
    "messages_published": "sum by (job, instance) (optimum_p2p_messages_published_total)",
}


def prom_query(expr: str) -> dict:
    url = PROM_URL + "/api/v1/query?query=" + urllib.parse.quote(expr)
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


def snapshot_prom() -> dict[str, dict[str, float]]:
    snap: dict[str, dict[str, float]] = {}
    for label, expr in PROM_TARGETS.items():
        res = prom_query(expr)
        per_instance: dict[str, float] = {}
        for item in res.get("data", {}).get("result", []):
            instance = item["metric"].get("instance", "?")
            per_instance[instance] = float(item["value"][1])
        snap[label] = per_instance
    return snap


def diff_prom(pre: dict, post: dict) -> dict[str, dict[str, float]]:
    delta: dict[str, dict[str, float]] = {}
    for label in PROM_TARGETS:
        delta[label] = {}
        pre_lab = pre.get(label, {})
        post_lab = post.get(label, {})
        instances = set(pre_lab) | set(post_lab)
        for inst in sorted(instances):
            delta[label][inst] = post_lab.get(inst, 0.0) - pre_lab.get(inst, 0.0)
    return delta


# ---------------------------------------------------------------------------
# Network impairment (tc netem via nsenter)
# ---------------------------------------------------------------------------

def container_pid(name: str) -> int:
    out = subprocess.check_output(
        ["docker", "inspect", "-f", "{{.State.Pid}}", name], text=True
    ).strip()
    return int(out)


def apply_netem(container: str, loss_pct: float, interface: str = "eth0") -> None:
    """Apply packet loss only to traffic destined for other p2pnode containers.

    Avoids impairing proxy↔p2pnode (control plane) and client↔p2pnode (REST
    publish path), which was a methodology limitation of the earlier N=4 runs
    where simple `tc qdisc replace root netem` broke the publish path at 20%
    loss. The p2pnodes live in 172.28.0.12-19 (.12-.15 covered by /30, .16-.19
    by the lower half of /29). Proxies on .10-.11 and bench client on
    docker_gwbridge are not in the impaired classes.
    """
    if loss_pct <= 0:
        return
    pid = container_pid(container)
    cmds = [
        # prio qdisc with 2 bands; priomap directs everything to band 0 (1:1)
        # unless a filter steers it to band 1 (1:2).
        ["tc", "qdisc", "add", "dev", interface, "root", "handle", "1:",
         "prio", "bands", "2", "priomap"] + ["0"] * 16,
        # netem with loss on band 2 (1:2)
        ["tc", "qdisc", "add", "dev", interface, "parent", "1:2",
         "handle", "20:", "netem", "loss", f"{loss_pct}%"],
        # Filter outbound packets whose dst is 172.28.0.12/30 (covers .12-.15) to 1:2
        ["tc", "filter", "add", "dev", interface, "parent", "1:0", "prio", "1",
         "protocol", "ip", "u32", "match", "ip", "dst", "172.28.0.12/30",
         "flowid", "1:2"],
        # Filter outbound packets whose dst is 172.28.0.16/29 (covers .16-.23, of
        # which .16-.19 are p2pnode-5..8) to 1:2
        ["tc", "filter", "add", "dev", interface, "parent", "1:0", "prio", "1",
         "protocol", "ip", "u32", "match", "ip", "dst", "172.28.0.16/29",
         "flowid", "1:2"],
    ]
    for cmd in cmds:
        subprocess.run(
            ["sudo", "-n", "nsenter", "-t", str(pid), "-n"] + cmd,
            check=True,
        )


def clear_netem(container: str, interface: str = "eth0") -> None:
    pid = container_pid(container)
    subprocess.run(
        ["sudo", "-n", "nsenter", "-t", str(pid), "-n",
         "tc", "qdisc", "del", "dev", interface, "root"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def clear_all_netem() -> None:
    for c in NODE_CONTAINERS:
        clear_netem(c)


# ---------------------------------------------------------------------------
# Publisher / subscriber drivers
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    topic: str
    datasize: int
    count: int
    sleep_ms: int = 200
    subscriber_idx: tuple[int, int] = (0, 8)  # subscribe on all 8 nodes in N=8 stack
    pub_settle_s: float = 20.0  # gossipsub mesh formation at N=8 with capped degree needs ~15s
    post_pub_settle_s: float = 8.0


def proxy_post(path: str, body: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        PROXY_URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def publish_via_proxy(topic: str, client_id: str, datasize: int, count: int,
                      sleep_s: float, pub_log: Path) -> int:
    """Publish via REST POST /api/v1/publish — sidesteps the multi-publish bidi deadlock.

    Uses `message_length` so the proxy/p2pnode generates random payload of the
    requested size internally. Returns the number of successful POSTs.
    """
    n_ok = 0
    with pub_log.open("w") as log:
        for i in range(count):
            t0 = time.time()
            try:
                resp = proxy_post(
                    "/api/v1/publish",
                    {"client_id": client_id, "topic": topic, "message_length": datasize},
                    timeout=60.0,
                )
                elapsed = (time.time() - t0) * 1000
                log.write(f"[{i+1}/{count}] {elapsed:.2f}ms {resp}\n")
                n_ok += 1
            except Exception as e:
                log.write(f"[{i+1}/{count}] ERROR: {e!r}\n")
            log.flush()
            if i < count - 1 and sleep_s > 0:
                time.sleep(sleep_s)
    return n_ok


def run_one(cfg: RunConfig, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.tsv"
    data_path = out_dir / "data.tsv"
    sub_log = out_dir / "subscriber.log"
    pub_log = out_dir / "publisher.log"

    client_id = f"bench-{int(time.time() * 1000)}"

    # Subscribe to topic via proxy (otherwise REST publish returns "topic not assigned")
    try:
        proxy_post("/api/v1/subscribe",
                   {"client_id": client_id, "topic": cfg.topic, "threshold": 0.1})
    except Exception as e:
        print(f"warning: proxy subscribe failed: {e!r}", flush=True)

    # Start trace subscriber on all 4 nodes (gRPC sidecar streams, separate from proxy)
    sub_proc = subprocess.Popen(
        [str(P2P_CLIENT / "p2p-multi-subscribe"),
         "-topic", cfg.topic,
         "-ipfile", str(IPS_FILE),
         "-start-index", str(cfg.subscriber_idx[0]),
         "-end-index", str(cfg.subscriber_idx[1]),
         "-output-data", str(data_path),
         "-output-trace", str(trace_path)],
        cwd=str(REPO),
        stdout=sub_log.open("wb"),
        stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(cfg.pub_settle_s)  # let GRAFTs happen
        pre = snapshot_prom()
        t_pub_start = time.time()
        n_published = publish_via_proxy(
            topic=cfg.topic,
            client_id=client_id,
            datasize=cfg.datasize,
            count=cfg.count,
            sleep_s=cfg.sleep_ms / 1000.0,
            pub_log=pub_log,
        )
        t_pub_end = time.time()
        time.sleep(cfg.post_pub_settle_s)
        post = snapshot_prom()
    finally:
        sub_proc.send_signal(signal.SIGINT)
        try:
            sub_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            sub_proc.kill()

    delta = diff_prom(pre, post)
    rows = read_trace(trace_path) if trace_path.exists() else []
    per_message = latencies_from_trace(rows)
    all_lat = [v for m in per_message.values() for v in m["latencies_ms"]]
    deliveries = sum(m["deliveries"] for m in per_message.values())
    shards = sum(m["shards"] for m in per_message.values())
    n_msgs_seen = len(per_message)

    return {
        "publisher_posts_ok": n_published,
        "duration_s": t_pub_end - t_pub_start,
        "n_messages_published": n_msgs_seen,
        "n_deliveries": deliveries,
        "n_shards_traced": shards,
        "latency_ms": summarize(all_lat),
        "prom_delta": delta,
    }


# ---------------------------------------------------------------------------
# Stack control
# ---------------------------------------------------------------------------

def docker_compose(args: list[str], compose: list[str]) -> None:
    cmd = ["docker", "compose"]
    for f in compose:
        cmd += ["-f", f]
    cmd += args
    subprocess.run(cmd, cwd=str(REPO), check=True)


def set_mode(mode: str) -> list[str]:
    """Return the compose file list for the chosen mode."""
    if mode == "optimum":
        return ["docker-compose-optimum.yml",
                "docker-compose.override.yml",
                "docker-compose.monitoring.yml"]
    if mode == "gossipsub":
        return ["docker-compose-gossipsub.yml",
                "docker-compose.override.yml",
                "docker-compose.monitoring.yml"]
    raise ValueError(f"unknown mode: {mode}")


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------

def run_matrix(
    out_root: Path,
    sizes: list[int],
    counts: list[int],
    sleeps: list[str],
    loss_pcts: list[float],
    mode: str,
    topic_prefix: str = "bench",
) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    csv_path = out_root / "results.csv"
    new_csv = not csv_path.exists()
    fields = [
        "ts", "mode", "size_bytes", "count", "sleep", "loss_pct",
        "n_pub_seen", "n_deliveries", "n_shards",
        "lat_n", "lat_mean_ms", "lat_p50_ms", "lat_p95_ms", "lat_p99_ms", "lat_max_ms",
        "proc_net_tx_total", "proc_net_rx_total",
        "bw_out_pubsub_total", "bw_in_pubsub_total",
        "shards_total_delta", "shards_unnecessary_delta",
        "delivered_msgs_delta", "delivered_bytes_delta",
        "raw_dir",
    ]
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if new_csv:
            writer.writeheader()

        for size, count, sleep in zip(sizes, counts, sleeps, strict=True):
            sleep_ms = _sleep_to_ms(sleep)
            for loss in loss_pcts:
                tag = f"{mode}_s{size}_l{loss:g}_{int(time.time())}"
                run_dir = out_root / "raw" / tag
                topic = f"{topic_prefix}-{tag}"

                clear_all_netem()
                if loss > 0:
                    # apply loss to all 4 nodes' eth0 (symmetric)
                    for c in NODE_CONTAINERS:
                        apply_netem(c, loss)

                try:
                    res = run_one(
                        RunConfig(topic=topic, datasize=size, count=count,
                                  sleep_ms=sleep_ms),
                        run_dir,
                    )
                finally:
                    clear_all_netem()

                delta = res["prom_delta"]
                row = {
                    "ts": int(time.time()),
                    "mode": mode,
                    "size_bytes": size,
                    "count": count,
                    "sleep": sleep,
                    "loss_pct": loss,
                    "n_pub_seen": res["n_messages_published"],
                    "n_deliveries": res["n_deliveries"],
                    "n_shards": res["n_shards_traced"],
                    "lat_n": res["latency_ms"]["n"],
                    "lat_mean_ms": round(res["latency_ms"]["mean"], 3),
                    "lat_p50_ms": round(res["latency_ms"]["p50"], 3),
                    "lat_p95_ms": round(res["latency_ms"]["p95"], 3),
                    "lat_p99_ms": round(res["latency_ms"]["p99"], 3),
                    "lat_max_ms": round(res["latency_ms"]["max"], 3),
                    "proc_net_tx_total": int(sum(delta.get("proc_net_tx_total", {}).values())),
                    "proc_net_rx_total": int(sum(delta.get("proc_net_rx_total", {}).values())),
                    "bw_out_pubsub_total": int(sum(delta.get("bandwidth_out_optimumsub", {}).values())),
                    "bw_in_pubsub_total": int(sum(delta.get("bandwidth_in_optimumsub", {}).values())),
                    "shards_total_delta": int(sum(delta.get("shards_total", {}).values())),
                    "shards_unnecessary_delta": int(sum(delta.get("shards_unnecessary", {}).values())),
                    "delivered_msgs_delta": int(sum(delta.get("delivered_messages_count", {}).values())),
                    "delivered_bytes_delta": int(sum(delta.get("delivered_messages_bytes", {}).values())),
                    "raw_dir": str(run_dir.relative_to(out_root)),
                }
                writer.writerow(row)
                f.flush()

                # Persist per-run summary as JSON
                (run_dir / "summary.json").write_text(json.dumps(
                    {**row, "prom_delta": delta, "latency_ms_full": res["latency_ms"]},
                    indent=2,
                ))
                print(
                    f"[{mode} size={size} loss={loss}] "
                    f"pub_seen={res['n_messages_published']} "
                    f"deliveries={res['n_deliveries']} "
                    f"shards={res['n_shards_traced']} "
                    f"lat_mean={row['lat_mean_ms']:.2f}ms "
                    f"lat_p95={row['lat_p95_ms']:.2f}ms "
                    f"bw_out={row['bw_out_pubsub_total']}B "
                    f"shards_unnecessary={row['shards_unnecessary_delta']}",
                    flush=True,
                )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _sleep_to_ms(s: str | int) -> int:
    if isinstance(s, int):
        return s
    s = s.strip().lower()
    if s.endswith("ms"):
        return int(float(s[:-2]))
    if s.endswith("s"):
        return int(float(s[:-1]) * 1000)
    return int(s)


def parse_size(s: str) -> int:
    s = s.strip().lower()
    if s.endswith("kb"):
        return int(float(s[:-2]) * 1024)
    if s.endswith("mb"):
        return int(float(s[:-2]) * 1024 * 1024)
    if s.endswith("b"):
        return int(s[:-1])
    return int(s)


def main() -> int:
    ap = argparse.ArgumentParser(description="Optimum RLNC propagation benchmark")
    ap.add_argument("--out", default="results", help="output root directory")
    ap.add_argument("--mode", default="optimum", choices=["optimum", "gossipsub"])
    ap.add_argument("--sizes", default="1KB,100KB,1MB,2.4MB",
                    help="comma-separated payload sizes (e.g. 1KB,100KB,1MB,2.4MB)")
    ap.add_argument("--counts", default=None,
                    help="comma-separated msg counts per size (default 50,40,20,10)")
    ap.add_argument("--sleeps", default=None,
                    help="comma-separated sleeps per size (default 100ms,200ms,400ms,600ms)")
    ap.add_argument("--loss", default="0", help="comma-separated loss percentages (e.g. 0,5,10)")
    ap.add_argument("--smoke", action="store_true", help="quick smoke: 1KB only, 5 msgs, no loss")
    args = ap.parse_args()

    sizes = [parse_size(s) for s in args.sizes.split(",")]
    if args.counts is None:
        # default counts per size: more iterations for small payloads
        defaults = {1024: 50, 102400: 40, 1048576: 20, 2516582: 10}
        counts = [defaults.get(s, max(5, 100 // max(1, s // 1024))) for s in sizes]
    else:
        counts = [int(x) for x in args.counts.split(",")]
    if args.sleeps is None:
        # default sleep scales with payload to avoid in-flight congestion
        def _default_sleep(s: int) -> str:
            if s <= 2048: return "100ms"
            if s <= 200_000: return "200ms"
            if s <= 1_200_000: return "400ms"
            return "600ms"
        sleeps = [_default_sleep(s) for s in sizes]
    else:
        sleeps = args.sleeps.split(",")
    loss_pcts = [float(x) for x in args.loss.split(",")]

    if args.smoke:
        sizes = [1024]
        counts = [5]
        sleeps = ["100ms"]
        loss_pcts = [0.0]

    if not (len(sizes) == len(counts) == len(sleeps)):
        sys.exit(f"length mismatch: sizes={len(sizes)} counts={len(counts)} sleeps={len(sleeps)}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    # Resolve to absolute path: bench subprocesses run with cwd=REPO and
    # relative output paths would otherwise resolve under the repo dir.
    out_root = (Path(args.out) / ts).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "config.json").write_text(json.dumps({
        "mode": args.mode,
        "sizes": sizes,
        "counts": counts,
        "sleeps": sleeps,
        "loss": loss_pcts,
        "timestamp": ts,
    }, indent=2))

    run_matrix(out_root, sizes, counts, sleeps, loss_pcts, args.mode)
    print(f"\nresults: {out_root}/results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
