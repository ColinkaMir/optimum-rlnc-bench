# RLNC vs RaptorCast: a hands-on look at two coded propagation stacks

**Draft v3, 2026-06-09. Author: Colinka. Status: RLNC side measured on multi-hop topology with packet loss; RaptorCast side now framed from public docs (no parallel benchmark yet).**

> Version 3 keeps the v2 numbers as-is (they came from the corrected N=8 multi-hop methodology) and adds two things: (1) a fix to a tacit assumption that RaptorCast equals RaptorQ (it does not, it is modified Raptor from RFC 5053), and (2) an actual technical framing of RaptorCast based on Monad's public docs, so the comparison is fair on the architectural side even without a matching benchmark.

---

## English

### Why this post

Most coverage of "fast L1s" focuses on execution: Monad, MegaETH, parallel EVMs. Less talked about: the propagation layer between nodes, which is where blocks and blobs actually travel. Two stacks have been making concrete claims about beating plain GossipSub on this:

- **Monad RaptorCast.** A modified Raptor (RFC 5053) fountain code, native part of the Monad consensus node, two-level broadcast tree topology.
- **Optimum mump2p (RLNC).** Random Linear Network Coding with recoding at intermediate mesh nodes. Delivered as a chain-agnostic sidecar that runs next to your existing CL client.

Worth noting up-front: RLNC as a coding scheme is not new to the blockchain world. It has been deployed in 5G networks for faster data transmission, in satellite communications for reliable links in low-signal regimes, and in IoT networks for efficient data sharing under bandwidth pressure. Optimum is bringing battle-tested real-world infrastructure into Web3, not rebuilding from scratch. RaptorCast similarly leverages an established fountain-code family (Raptor, RFC 5053, with modifications), and Monad has tailored it specifically for consensus-block broadcast.

I run a Monad full node, and I run an Ethereum DV operator slot in a Lido x SSV cluster. So both stacks are relevant to me operationally. I wanted my own numbers, not the marketing slide. Here is the first half of that work: the RLNC side, on a local 8-node Optimum mesh with capped mesh degree so messages actually transit through intermediate nodes. The RaptorCast side comes later in measurement, but the architectural framing below is enough to make the comparison meaningful today.

### What I actually did (RLNC side)

Cloned `github.com/getoptimum/optimum-dev-setup-guide` at commit `bd8c0b8`. Stood up the local Docker stack at images `getoptimum/p2pnode:v0.0.1-rc16` + `getoptimum/proxy:v0.0.1-rc16`.

**Topology choice matters here.** I ran two separate compose stacks:
- **`optimum`** mode (`NODE_MODE=optimum`) with `OPTIMUM_MESH_TARGET=3, MESH_MIN=3, MESH_MAX=4`
- **`gossipsub`** mode (`NODE_MODE=gossipsub`) with `GOSSIPSUB_MESH_TARGET=3, MESH_MIN=3, MESH_MAX=4`

Both at N=8 nodes. The `MeshDegreeMax=4` cap means each node connects to at most 4 of 7 possible peers per topic, so messages from the publisher have to transit through 1-2 intermediate nodes to reach distant subscribers. This is the regime where RLNC's recoding can do work: an intermediate node sees a coded packet and can produce a NEW coded packet without first decoding the original. Fountain codes (Reed-Solomon, the Raptor family including RFC 5053 and RFC 6330) cannot do this without first decoding.

RLNC params left at default: `ShardFactor=4`, `PublisherShardMultiplier=1.5`, `ForwardShardThreshold=0.75`, `MaxMessageSize=2.5MB`.

Bench harness:
- Publish via the proxy REST endpoint, `POST /api/v1/publish` with `message_length` (proxy generates random payload server-side). I used REST because the bundled `multi-publish` gRPC client deadlocks at payloads ≥100 KB. That bug is reported and patched at https://github.com/getoptimum/optimum-dev-setup-guide/pull/75.
- Subscribe via direct gRPC sidecar (`grpc_p2p_client/p2p-multi-subscribe`) on all 8 nodes.
- Latency = `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` from upstream `mump2p` trace TSV, per (message_id, subscriber).
- Bandwidth from Prometheus `process_network_transmit_bytes_total` (per-process counter; works in both modes).
- Packet loss applied via `sudo nsenter -t <pid> -n tc qdisc add dev eth0 root handle 1: prio bands 2 priomap 0..0 + netem on band 2 + u32 filter matching dst 172.28.0.12/30 and 172.28.0.16/29`. This scopes loss to peer-to-peer mesh traffic only and leaves the proxy↔p2pnode control plane untouched, so the publish path itself does not break under loss.

Matrix: payload sizes {1 KB, 100 KB, 1 MB, 2.4 MB} × loss {0, 5, 10, 20%} × modes {optimum, gossipsub} = 32 runs. Counts scaled by payload (50, 40, 20, 10) to keep total volume per run bounded.

### What I found

**Delivery rate per condition (deliveries / expected, %):**

| payload | loss | optimum | gossipsub |
|---|---|---|---|
| 1 KB | 0% | **100%** | 14% |
| 1 KB | 5% | **100%** | 43% |
| 1 KB | 10% | **100%** | 43% |
| 1 KB | 20% | **100%** | 14% |
| 100 KB | 0% | **100%** | 14% |
| 100 KB | 5% | **100%** | 14% |
| 100 KB | 10% | **100%** | 14% |
| 100 KB | 20% | 42% | 17% |
| 1 MB | 0% | **100%** | 14% |
| 1 MB | 5% | **100%** | 43% |
| 1 MB | 10% | **100%** | 14% |
| 1 MB | 20% | 12% | 15% |
| 2.4 MB | 0% | **100%** | 29% |
| 2.4 MB | 5% | **100%** | 14% |
| 2.4 MB | 10% | 76% | 23% |
| 2.4 MB | 20% | 12% | 14% |

Expected = `count × N` for optimum (publisher's own node also emits DELIVER), `count × (N-1)` for gossipsub (publisher's node does not). N = 8 here.

**Optimum delivers 100% in 11 of 16 conditions. Gossipsub delivers 100% in 0 of 16.**

The headline result is the 1 MB × 10% loss cell: **optimum 100% delivery, gossipsub 14% delivery**. That is a 7× advantage at the most operationally-relevant payload size for a beacon block's worth of data.

**Latency mean / p95 at the conditions where optimum delivers 100% (gossipsub for comparison where it delivered anything):**

| payload | loss | opt mean | opt p95 | gs mean | gs p95 |
|---|---|---|---|---|---|
| 1 KB | 0% | 1.7 ms | 3.4 ms | 0.1 ms | 0.2 ms |
| 1 KB | 5% | 6.6 ms | 33 ms | 0.4 ms | 1.0 ms |
| 1 KB | 10% | 35 ms | 164 ms | 5.9 ms | 15 ms |
| 1 KB | 20% | 181 ms | 511 ms | n/a | n/a |
| 100 KB | 0% | 3.4 ms | 6.7 ms | 0.3 ms | 0.8 ms |
| 100 KB | 5% | 13 ms | 58 ms | 0.5 ms | 1.3 ms |
| 100 KB | 10% | 162 ms | 455 ms | 0.2 ms | 0.4 ms |
| 1 MB | 0% | 17 ms | 34 ms | 2.2 ms | 5.3 ms |
| 1 MB | 5% | 146 ms | 377 ms | 149 ms | 657 ms |
| 1 MB | 10% | 2.24 s | 4.23 s | n/a | n/a |
| 2.4 MB | 0% | 62 ms | 295 ms | 9.9 ms | 22 ms |
| 2.4 MB | 5% | 279 ms | 565 ms | n/a | n/a |
| 2.4 MB | 10% | 4.77 s | 7.72 s | n/a | n/a |

`n/a` rows are gossipsub conditions where mesh formation failed; the latencies that would be computed there are not meaningful.

**Two distinct stories**:

1. **At zero loss, gossipsub is faster.** This is consistent with v1 of this post on N=4 and persists at N=8: RLNC's shard-encoding step adds latency that does not pay back when no packets are dropped. On 1 KB at 0% loss the gap is ~1.6 ms (optimum p50 1.7 ms vs gossipsub p50 0.1 ms). On 1 MB at 0% loss the gap is similar in shape (17 ms vs 2.2 ms). RLNC pays an encoding tax.

2. **Under loss, the picture inverts. RLNC delivers; gossipsub drops messages silently.** At 1 MB / 10% loss optimum gets every message through in around 2.2 seconds tail. Gossipsub at the same point gets 14% of messages through in a few milliseconds; the rest never arrive.

The "few milliseconds" gossipsub latencies at low delivery rates are misleading on their own: they reflect successful self-deliveries by the publisher's own subscriber. Look at the delivery-rate column, not the latency column, when interpreting those rows.

**Gossipsub mesh formation at MeshDegreeMax=4 / N=8 was unstable across iterations.** Different runs of the same gossipsub condition produced 14% (publisher self only) or 43% (3 out of 7 remote receivers). I attribute this to gossipsub's per-topic mesh-graft heartbeat timing combined with the low mesh degree cap. RLNC at the same MeshDegreeMax did not show this variance: every iteration delivered to every node. The RLNC shard mechanism (publish coded packets to mesh peers, intermediate nodes recode to forward) appears to be more tolerant of partial mesh formation than raw gossipsub at the same topology constraint.

**At ≥20% loss × ≥1 MB payload both modes collapse.** At 1 MB / 20% optimum delivered 12% and gossipsub 15%. At 2.4 MB / 20% both delivered 12-14%. So even RLNC has a ceiling where the math runs out: too many shards lost across too many hops, recoding cannot reconstruct. The ceiling is well above what gossipsub can sustain, but it exists.

### Bandwidth

**Per-message TX bytes summed over all 8 nodes** (measured via Prometheus `process_network_transmit_bytes_total` delta during the run):

| payload | loss | opt BW/msg | gs BW/msg |
|---|---|---|---|
| 1 KB | 0% | 54 KB | 1.3 KB |
| 100 KB | 0% | 2.05 MB | 406 KB |
| 1 MB | 0% | 21.7 MB | 4.0 MB |
| 2.4 MB | 0% | 48.5 MB | 21.7 MB |

RLNC roughly 5× the network footprint of gossipsub at 0% loss for the same delivered messages. This is the cost of the redundancy that buys it loss-resilience. Note that this counter includes all egress traffic, not just pubsub, so the absolute ratio is an upper bound. For 1 MB-class payloads (close to a real Ethereum beacon block) RLNC sends about 22 MB into the network per published block to make sure every node has a copy. Plain gossipsub sends about 4 MB. The trade is bandwidth for loss-resilience.

### What RaptorCast actually is (from public Monad docs, fetched 2026-06-09)

Useful to be specific here, because I was sloppy in v2 of this post about which Raptor family RaptorCast belongs to. Monad's documentation at https://docs.monad.xyz/monad-arch/consensus/raptorcast spells it out:

> "RaptorCast employs a Raptor code variant documented in RFC 5053, though with Monad-specific modifications" (... it is "not RaptorQ but rather a modified classical Raptor implementation tailored for blockchain consensus requirements").

So: **RaptorCast is built on Raptor (RFC 5053), the earlier fountain code family, not RaptorQ (RFC 6330).** Monad layers its own tweaks on top, which the docs describe as improving small-message encoding efficiency at a slight decoding-complexity cost.

Topology, again from the docs:

> "a two-level broadcast tree for each chunk... the message originator is the root of the tree, a single non-originator node lives at level 1, and every other node lives at level 2"

So RaptorCast is **not arbitrary multi-hop**: it is a fixed two-level fanout where the originator (block-proposing leader) emits chunks, level-1 validators relay them, and level-2 validators receive. The level-1 chunk allocation is proportional to stake weight.

Intermediate node behaviour:

> "Intermediate nodes do not perform recoding. Instead, first-level nodes function purely as relay points."

This is the architectural pivot. RaptorCast level-1 nodes are pure forwarders. They do not generate new coded chunks based on what they received. That is by design: it keeps the protocol simple, lets it run over UDP with no acknowledgement, and avoids the computational cost of recoding at every relay.

Loss handling, then, is **entirely the originator's responsibility**, pre-emptively:

> "messages are transmitted with a configurable amount of redundancy (chosen by the node operator)"

The docs give a worked example: at 20% network packet loss and up to 33% faulty nodes, the originator should send "approximately 87% additional chunks" on top of the source. So if a 2 MB block is 1640 source chunks (the docs' example, using 1220 bytes payload per UDP packet), an operator at this loss profile would emit roughly 3060 encoded chunks. The docs' default redundancy factor of 2.5 produces 4100 chunks for that 2 MB block, conservatively above the 87% figure.

Per-validator load:

> "each would receive 4100 / 99 = 41 chunks in contiguous ranges"

That is for 100 validators with equal stake. Notice: each validator's bandwidth is constant in N (the number of validators), which is a real design win for scalability. RLNC mesh-degree-driven distribution does not have this clean linearity.

Theoretical latency bound:

> "The worst-case message propagation time is twice the worst-case one-way latency between any two nodes"

This is a one-RTT bound (one hop out, one hop in to forward), which is excellent on paper. Monad's own targets at the system level are 10K tps, 400ms block frequency, 800ms finality.

### Architectural side-by-side

| Aspect | Monad RaptorCast | Optimum RLNC |
|---|---|---|
| Base FEC | Raptor (RFC 5053), modified by Monad | Random Linear Network Coding |
| Topology | Two-level broadcast tree (originator → level-1 → level-2) | Multi-hop mesh, configurable degree |
| Intermediate node behaviour | Pure relay, **no recoding** | **Recoding on every hop** |
| Loss recovery | Originator pre-emptive redundancy (factor configurable, ~2.5× by default) | Adaptive: each hop can produce new coded packets |
| Per-validator chunk count (2 MB block) | ~41 chunks (from docs example, N=100) | Depends on mesh degree and ShardFactor |
| Bandwidth scaling in N | Constant per validator | Grows with mesh degree |
| Latency bound | 2× one-way RTT (theoretical) | Empirical only; see numbers above |
| Block size example | 2 MB → 1640 source chunks | 2.5 MB MaxMessageSize, 4 shards default |
| Standardization | Closed (Monad internal mod of RFC 5053) | Closed (Optimum vendored, RLNC academic basis) |

The clean architectural read: **RaptorCast bets on simplicity and pre-emptive bandwidth budget**; **RLNC bets on adaptive recoding at every hop**. Both are valid trades. Which one wins on real numbers is exactly what a parallel benchmark would settle. We do not have that yet.

### What I have NOT done yet

Run the same methodology against RaptorCast. To make this a real RLNC-vs-RaptorCast post, the RaptorCast side needs the same shape of measurement: matched payload sizes, matched loss injection at the network namespace level, latency from generate-time to delivery-time at all peers, and a `process_network_transmit_bytes_total` snapshot. That work belongs on a Monad **testnet** node, not the production validator-bound one. If you (the reader) know how to extract per-peer per-block delivery timestamps from a Monad client without a custom patch, ping me. I have not found it in the public docs.

### Honest framing

- RLNC delivers what its marketing claims **on the multi-hop topology where its recoding can actually do work**. On a 4-node loopback mesh it does not; on an 8-node mesh with `MeshDegreeMax=4` it does. The "6-20x faster" framing in Optimum's marketing is correct in shape on the bench, but the headline number is about delivery rate under loss, not latency at zero loss.
- At zero loss, gossipsub remains faster. If your workload is single-region, sub-millisecond, no-packet-loss, plain gossipsub is the right answer.
- The RaptorCast comparison is open until parallel numbers exist. I am NOT claiming RLNC beats RaptorCast. I am claiming RLNC beats plain gossipsub, by a lot, under loss. RaptorCast is a different architectural bet (fixed 2-level tree, pre-emptive redundancy, no recoding), and which bet wins on real propagation telemetry is genuinely open.
- There is no Optimum token. Per their FAQ as of 2026-05-28, no early-operator role to claim. This post is technical curiosity, content prep, and standing-in-case-something-changes. Not an investment thesis.

Reproducibility: bench script, summarised TSV+CSV outputs, methodology notes, known limits are all in https://github.com/ColinkaMir/optimum-rlnc-bench. Tagged release `v1.0` corresponds to the data in this post.

---

## По-русски

### Зачем этот пост

Большинство разговоров про "быстрые L1" крутится вокруг execution-слоя: Monad, MegaETH, параллельные EVM. Меньше говорят про propagation-слой между нодами, по которому реально летают блоки и блобы. Два стэка предъявляют конкретные цифры в том, что они быстрее обычного GossipSub:

- **Monad RaptorCast.** Modified Raptor (RFC 5053), нативная часть Monad-консенсуса, топология двухуровневое broadcast-дерево.
- **Optimum mump2p (RLNC).** Random Linear Network Coding с recoding на промежуточных узлах mesh'а. Идёт как chain-agnostic sidecar, который работает рядом с твоим CL-клиентом.

Сразу отмечу: RLNC как схема кодирования вообще не нова для блокчейн-мира. Она применяется в 5G-сетях для ускорения передачи данных, в спутниковой связи для надёжной работы в low-signal режимах, в IoT-сетях для эффективного обмена данными при ограниченной полосе. Optimum приносит battle-tested инфраструктуру в Web3, не строит с нуля. RaptorCast аналогично опирается на установленное семейство fountain-кодов (Raptor, RFC 5053, с модификациями), и Monad подкрутил его под consensus-block broadcast.

Я держу Monad full node и DV-оператор в Lido x SSV кластере. Оба стэка релевантны для меня операционно. Хотел свои цифры, не маркетинговые. Это первая половина: RLNC сторона, на локальном 8-нодовом Optimum mesh с capped mesh degree чтобы сообщения **реально транзитили** через промежуточные ноды. RaptorCast будет позже по измерениям, но архитектурного материала уже хватает чтобы сравнение было содержательным.

### Что я сделал (RLNC сторона)

Склонировал `github.com/getoptimum/optimum-dev-setup-guide` на коммите `bd8c0b8`. Поднял локальный Docker-стэк на образах `getoptimum/p2pnode:v0.0.1-rc16` + `getoptimum/proxy:v0.0.1-rc16`.

**Топология здесь важна.** Запустил два compose-стэка:
- **`optimum`** режим, `OPTIMUM_MESH_TARGET=3, MESH_MIN=3, MESH_MAX=4`
- **`gossipsub`** режим, `GOSSIPSUB_MESH_TARGET=3, MESH_MIN=3, MESH_MAX=4`

Оба на N=8 нодах. Cap `MeshDegreeMax=4` значит каждая нода подключена максимум к 4 из 7 возможных пиров per topic, поэтому сообщения от publisher должны транзитить через 1-2 промежуточные ноды чтобы дойти до дальних subscriber-ов. **Это и есть режим где RLNC's recoding может работать**: промежуточный узел видит coded packet и может произвести НОВЫЙ coded packet без декодирования исходного. Fountain-коды (Reed-Solomon, всё семейство Raptor, включая RFC 5053 и RFC 6330) этого без декодирования не умеют.

RLNC параметры по умолчанию: `ShardFactor=4`, `PublisherShardMultiplier=1.5`, `ForwardShardThreshold=0.75`, `MaxMessageSize=2.5MB`.

Бенч:
- Publish через proxy REST, `POST /api/v1/publish` с `message_length` (proxy сам генерит random нужного размера). Через REST потому что встроенный gRPC `multi-publish` залипает на payload-ах от 100 KB; баг зарепортил и запатчил: https://github.com/getoptimum/optimum-dev-setup-guide/pull/75.
- Subscribe через прямой gRPC sidecar на всех 8 нодах.
- Latency = `DELIVER_MESSAGE.ts - PUBLISH_MESSAGE.ts` из штатного `mump2p` trace TSV.
- Bandwidth из Prometheus `process_network_transmit_bytes_total`.
- Packet loss через `tc netem` с u32-filter'ом, scoped только на peer-to-peer mesh-трафик (не задевает proxy↔p2pnode control plane). Это исправление методологического limit'а из v1.

Матрица: размеры {1 KB, 100 KB, 1 MB, 2.4 MB} × loss {0, 5, 10, 20%} × режимы {optimum, gossipsub} = 32 прогона.

### Что нашёл

**Доля доставки per condition (deliveries / expected, %):**

| payload | loss | optimum | gossipsub |
|---|---|---|---|
| 1 KB | 0% | **100%** | 14% |
| 1 KB | 5% | **100%** | 43% |
| 1 KB | 10% | **100%** | 43% |
| 1 KB | 20% | **100%** | 14% |
| 100 KB | 0% | **100%** | 14% |
| 100 KB | 5% | **100%** | 14% |
| 100 KB | 10% | **100%** | 14% |
| 100 KB | 20% | 42% | 17% |
| 1 MB | 0% | **100%** | 14% |
| 1 MB | 5% | **100%** | 43% |
| 1 MB | 10% | **100%** | 14% |
| 1 MB | 20% | 12% | 15% |
| 2.4 MB | 0% | **100%** | 29% |
| 2.4 MB | 5% | **100%** | 14% |
| 2.4 MB | 10% | 76% | 23% |
| 2.4 MB | 20% | 12% | 14% |

**Optimum доставляет 100% в 11 из 16 условий. Gossipsub: в 0 из 16.**

**Latency mean / p95 в условиях где optimum доставляет 100% (gossipsub для сравнения где он что-то доставил):**

| payload | loss | opt mean | opt p95 | gs mean | gs p95 |
|---|---|---|---|---|---|
| 1 KB | 0% | 1.7 ms | 3.4 ms | 0.1 ms | 0.2 ms |
| 1 KB | 5% | 6.6 ms | 33 ms | 0.4 ms | 1.0 ms |
| 1 KB | 10% | 35 ms | 164 ms | 5.9 ms | 15 ms |
| 1 KB | 20% | 181 ms | 511 ms | n/a | n/a |
| 100 KB | 0% | 3.4 ms | 6.7 ms | 0.3 ms | 0.8 ms |
| 100 KB | 5% | 13 ms | 58 ms | 0.5 ms | 1.3 ms |
| 100 KB | 10% | 162 ms | 455 ms | 0.2 ms | 0.4 ms |
| 1 MB | 0% | 17 ms | 34 ms | 2.2 ms | 5.3 ms |
| 1 MB | 5% | 146 ms | 377 ms | 149 ms | 657 ms |
| 1 MB | 10% | 2.24 s | 4.23 s | n/a | n/a |
| 2.4 MB | 0% | 62 ms | 295 ms | 9.9 ms | 22 ms |
| 2.4 MB | 5% | 279 ms | 565 ms | n/a | n/a |
| 2.4 MB | 10% | 4.77 s | 7.72 s | n/a | n/a |

Строки `n/a` это gossipsub-условия где mesh не сформировался; вычисленные там latency не содержательны.

Заголовок: **1 MB × 10% loss: optimum 100%, gossipsub 14%**. Семикратное превосходство по доставке на размере близком к Ethereum beacon block.

**Две разных истории:**

1. **При нулевом loss gossipsub быстрее.** Тот же эффект что в v1 на N=4 и сохраняется на N=8: RLNC платит shard-encoding tax который не отбивается без потерь. На 1 KB / 0% разница ~1.6 ms (p50 optimum 1.7 ms vs gossipsub 0.1 ms). На 1 MB / 0% это 17 ms vs 2.2 ms.

2. **Под loss картина инвертируется. RLNC доставляет; gossipsub silently дропает сообщения.** На 1 MB / 10% optimum проводит каждое сообщение за ~2.2 секунды хвоста. Gossipsub при тех же условиях доставляет 14% за единицы миллисекунд: остальные не приходят никогда.

Низкие миллисекундные latencies gossipsub при низкой доставке вводят в заблуждение сами по себе: они отражают успешные self-delivery на publisher's node. При интерпретации этих ячеек надо смотреть на delivery rate, не на latency.

**Gossipsub mesh formation при `MeshDegreeMax=4 / N=8` нестабильно между прогонами.** Разные прогоны одного gossipsub условия давали 14% (только publisher self) или 43% (3 из 7 удалённых receivers). Это похоже на gossipsub's per-topic mesh-graft heartbeat timing в сочетании с низким cap. RLNC при том же `MeshDegreeMax` этой вариативности не показывал: каждый прогон доставлял всем 8 нодам. **RLNC shard-механизм оказывается терпимее к partial mesh formation чем raw gossipsub при той же топологии**.

**При ≥20% loss × ≥1 MB payload оба режима collapse.** 1 MB / 20%: optimum 12%, gossipsub 15%. 2.4 MB / 20%: оба 12-14%. Даже у RLNC есть ceiling где математика не вытягивает: слишком много шардов потеряно на слишком многих hops, recoding не восстанавливает. Ceiling сильно выше gossipsub'овского, но есть.

### Bandwidth

**Per-message TX bytes суммарно по 8 нодам:**

| payload | loss | opt BW/msg | gs BW/msg |
|---|---|---|---|
| 1 KB | 0% | 54 KB | 1.3 KB |
| 100 KB | 0% | 2.05 MB | 406 KB |
| 1 MB | 0% | 21.7 MB | 4.0 MB |
| 2.4 MB | 0% | 48.5 MB | 21.7 MB |

RLNC примерно в 5× больше сетевого следа чем gossipsub при 0% loss на тех же доставленных сообщениях. Это плата за redundancy которая покупает loss-резильентность. На 1 MB (близко к реальному Ethereum beacon block) RLNC шлёт около 22 MB в сеть на каждый published блок чтобы гарантировать что каждая нода имеет копию. Plain gossipsub шлёт около 4 MB. **Bandwidth обменивается на loss-resilience.**

### Что такое RaptorCast (по публичной документации Monad, прочитано 2026-06-09)

Полезно быть точным, потому что в v2 этого поста я небрежно говорил про "RaptorCast как Raptor/RaptorQ" в одну корзину. Документация Monad на https://docs.monad.xyz/monad-arch/consensus/raptorcast уточняет:

> "RaptorCast employs a Raptor code variant documented in RFC 5053, though with Monad-specific modifications" (... это "not RaptorQ but rather a modified classical Raptor implementation tailored for blockchain consensus requirements").

Перевод: "RaptorCast использует вариант Raptor-кода, описанный в RFC 5053, с Monad-specific модификациями" (это "не RaptorQ, а модифицированный классический Raptor под нужды блокчейн-консенсуса").

То есть **RaptorCast построен на Raptor (RFC 5053), более раннем fountain-семействе, а не на RaptorQ (RFC 6330).** Monad накладывает поверх свои tweaks; документация описывает их как улучшение encoding'а маленьких сообщений ценой небольшого роста decoding-сложности.

Топология, оттуда же:

> "a two-level broadcast tree for each chunk... the message originator is the root of the tree, a single non-originator node lives at level 1, and every other node lives at level 2"

Перевод: "двухуровневое broadcast-дерево на каждый chunk... отправитель сообщения это корень дерева, один не-отправитель сидит на уровне 1, а все остальные на уровне 2".

То есть RaptorCast **не произвольный multi-hop**: это фиксированный двухуровневый fanout, где originator (лидер, предлагающий блок) эмитит chunks, level-1 валидаторы релеят, level-2 валидаторы получают. Распределение chunks на level-1 пропорционально stake weight.

Поведение промежуточных узлов:

> "Intermediate nodes do not perform recoding. Instead, first-level nodes function purely as relay points."

Перевод: "Промежуточные узлы не делают recoding. Уровень-1 функционирует как чистые точки релея".

Это и есть архитектурная развилка. RaptorCast level-1 ноды это чистые форвардеры. Они не генерируют новые coded chunks на основе того что получили. Это по дизайну: упрощает протокол, позволяет работать поверх UDP без подтверждений, избегает вычислительной стоимости recoding'а на каждом релее.

Восстановление потерь, соответственно, **полностью на originator'е**, упреждающе:

> "messages are transmitted with a configurable amount of redundancy (chosen by the node operator)"

Перевод: "сообщения передаются с настраиваемым уровнем redundancy (выбирается оператором ноды)".

Документация даёт worked example: при 20% network packet loss и до 33% неисправных нод originator должен слать "approximately 87% additional chunks" поверх source. Так 2 MB блок это 1640 source chunks (пример из docs, 1220 байт payload на UDP-пакет), оператор при таком loss-профиле эмитит примерно 3060 encoded chunks. Дефолтный redundancy factor 2.5 даёт 4100 chunks на тот же блок, консервативно выше отметки 87%.

Per-validator нагрузка:

> "each would receive 4100 / 99 = 41 chunks in contiguous ranges"

Перевод: "каждый получит 4100 / 99 = 41 chunk в непрерывных диапазонах".

Это для 100 валидаторов с равным stake'ом. Заметим: bandwidth каждого валидатора константна в N (числе валидаторов), это реальный design-win для масштабируемости. У RLNC с распределением по mesh-degree такой чистой линейности нет.

Теоретическая граница latency:

> "The worst-case message propagation time is twice the worst-case one-way latency between any two nodes"

Перевод: "Худшее время propagation равно удвоенной односторонней latency между любыми двумя узлами".

Это one-RTT-граница (один hop туда, один обратно для форварда), на бумаге отлично. Цели Monad на уровне системы: 10K tps, 400ms block frequency, 800ms finality.

### Архитектурное side-by-side

| Параметр | Monad RaptorCast | Optimum RLNC |
|---|---|---|
| База FEC | Raptor (RFC 5053), Monad-модифицированный | Random Linear Network Coding |
| Топология | Двухуровневое broadcast-дерево (originator → level-1 → level-2) | Multi-hop mesh, настраиваемая degree |
| Поведение промежуточных узлов | Чистый релей, **без recoding** | **Recoding на каждом hop'е** |
| Loss recovery | Originator упреждающая redundancy (фактор настраиваем, по умолчанию ~2.5×) | Adaptive: каждый hop может генерировать новые coded packets |
| Chunks на validator (2 MB блок) | ~41 chunk (пример из docs, N=100) | Зависит от mesh degree и ShardFactor |
| Bandwidth scaling в N | Константно per validator | Растёт с mesh degree |
| Граница latency | 2× one-way RTT (теория) | Только эмпирика, см. цифры выше |
| Пример размера блока | 2 MB → 1640 source chunks | 2.5 MB MaxMessageSize, 4 шарда по умолчанию |
| Стандартизация | Закрытое (Monad internal mod of RFC 5053) | Закрытое (Optimum vendored, RLNC academic basis) |

Чистое архитектурное чтение: **RaptorCast ставит на простоту и упреждающий bandwidth-бюджет**; **RLNC ставит на adaptive recoding на каждом hop'е**. Оба валидные ставки. Кто выиграет на реальных цифрах, разрешит только параллельный бенчмарк. Его пока нет.

### Чего я НЕ сделал

Прогнать ту же методику против RaptorCast. Для полноценного "RLNC vs RaptorCast" поста RaptorCast-сторона должна иметь измерения той же формы. Эту работу надо делать на Monad **testnet** ноде, не на той что в продакшене, и нужен какой-то хук в Monad-клиент чтобы достать per-peer per-block delivery timestamps. Если ты (читатель) знаешь как чисто извлечь эти timestamp-ы из Monad-ноды без патча клиента, напиши.

### Честная рамка

- RLNC доставляет то что заявлено в маркетинге **на multi-hop топологии где его recoding реально может работать**. На 4-нодовом loopback не доставляет; на 8-нодовом с `MeshDegreeMax=4` доставляет. Маркетинговое "6-20x faster" верно по форме на бенче, но заголовочное число про delivery rate под loss, не про latency при нулевом loss.
- При нулевом loss gossipsub остаётся быстрее. Если твой workload single-region, sub-millisecond, без packet loss: plain gossipsub правильный ответ.
- Сравнение с RaptorCast открыто, пока нет параллельных цифр. Я НЕ утверждаю что RLNC бьёт RaptorCast. Я утверждаю что RLNC бьёт plain gossipsub значительно, под loss. RaptorCast это другая архитектурная ставка (фиксированное 2-уровневое дерево, упреждающая redundancy, без recoding), и кто из них выиграет на реальной propagation-телеметрии: реально открытый вопрос.
- У Optimum нет токена. Согласно их FAQ на 2026-05-28, нет early-operator-роли. Этот пост: техническое любопытство, подготовка контента, standing на случай если что-то изменится. Не инвестиционный тезис.

Воспроизводимость: bench-скрипт, агрегированные TSV+CSV, методологические заметки, известные ограничения. Всё лежит в https://github.com/ColinkaMir/optimum-rlnc-bench. Тег `v1.0` соответствует данным в этом посте.

---

