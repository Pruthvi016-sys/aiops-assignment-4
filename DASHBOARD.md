# Dashboard, alerting and app design

Screenshots referenced here are in [`evidence_screenshots/`](evidence_screenshots).

## 1. Grafana dashboard

File: `grafana/dashboards/image_captioning_dashboard.json` — 32 panels, refresh **5 s**, last 15 min.
To import manually: *Dashboards → New → Import → Upload JSON* and pick the Prometheus datasource.

**Logical flow (high level → low level):**

| Row | Question it answers | Panels |
|---|---|---|
| ① Service health | Is everything up? | Target UP/DOWN per job, model loaded, uptime, in-progress requests, firing alerts, total images, error ratio, avg latency (Summary), sessions & ZIPs |
| ② Throughput & latency | How fast is it? | Images/s by mode, p50/p95/p99 inference latency (Histogram), request latency single vs ZIP (Summary), preprocess vs inference, latency heatmap |
| ③ Workload & model | What is it processing? | Bulk queue countdown, errors & skipped files by reason, caption length distribution, image size & megapixels, ZIP duration vs size, model footprint |
| ④ Clients | Who is using it? | Requests per client IP, top sessions, request rate by browser |
| ⑤ System resources | What does it cost the machine? | **CPU vs throughput (dual axis)**, machine vs app RAM, CPU user/system/iowait, load vs cores, disk I/O, disk usage, network, machine facts |

**Correlating app and system metrics:** an annotation draws an **orange band on every graph while a bulk
ZIP job is running** (`imgcap_bulk_queue_remaining > 0`), and the crosshair is shared across panels — so a
CPU / RAM spike can be matched to the bulk upload that caused it. A red marker appears if the app goes down.

**7 Commandments of Plotting — how each is met:**
1. **Colour-blind safe palette** — every colour is from the Okabe-Ito palette (blue `#0072B2`, orange `#E69F00`, vermillion `#D55E00`, green, sky, pink…), heatmap uses Viridis; status panels also show text (`UP ✔` / `DOWN ✖`) so colour is never the only signal.
2. **Markers work across media** — data points are always drawn and series differ by **line style** (solid / dashed / dotted), so graphs stay readable in grayscale print or PDF.
3. **Named axes** — every time-series has an axis label, e.g. *"Latency per image (seconds, log₂ scale)"*.
4. **Scale & units explicit** — units set on every panel (s, bytes, %, bytes/s) and the scale is written in the axis label (*linear* or *log₂*); log scale is used where values span orders of magnitude (latency).
5. **Legends** — table legends (last / mean / max) on every multi-series panel.
6. **Title + subtitle** — every panel title is *"Title — subtitle"*, e.g. *"Throughput — images captioned per second"*.
7. **Story** — every panel has a description (ⓘ icon) explaining what it shows and how to read it, plus a "How to read this dashboard" note at the top.

Screenshots: 12–16 (all five rows with live data), video: see README.

## 2. Alerting pipeline

`prometheus/alert_rules.yml` → evaluated by Prometheus every 5 s → sent to Alertmanager (`:9093`).

| Alert | Fires when |
|---|---|
| CaptionAppDown | `up{job="caption_app"} == 0` for 15 s |
| NodeExporterDown | node_exporter unreachable for 15 s |
| ModelNotLoaded | app up but model not loaded for 2 min |
| HighInferenceLatency | p95 inference > 5 s for 30 s |
| HighErrorRate | > 20 % of images failing |
| BulkJobStuck | ZIP queue not moving for 2 min |
| HighCPUUsage | CPU > 90 % for 1 min |
| LowMemory | < 10 % RAM available |
| DiskAlmostFull | < 10 % disk free |

Quick test: stop Streamlit (Ctrl+C) → within ~20 s the health panel shows **DOWN**, *Firing alerts* becomes 1,
and `CaptionAppDown` appears on http://localhost:9090/alerts and http://localhost:9093.

To get notifications, add a receiver (email / Slack / webhook) in `alertmanager/alertmanager.yml`.

Screenshots: 17 (Grafana shows DOWN ✖ and 1 firing alert), 18 (Prometheus FIRING), 19 (Alertmanager received).

## 3. How the app stays stable on CPU (Application Logic)
- Model is loaded **once** (`st.cache_resource`) and shared by all sessions.
- A lock allows **one inference at a time** so parallel users don't overload the CPU/RAM (queue is visible as `imgcap_waiting_for_model`).
- Images are EXIF-rotated and shrunk to max 1024 px before inference; decompression-bomb guard (50 MP).
- ZIP limits: max 100 images, 20 MB per image, 500 MB uncompressed; non-images, hidden and `__MACOSX` files are skipped.
- Every image is captioned inside its own `try/except` — one bad file never stops the batch.
- Results live in `st.session_state` so they survive reruns (e.g. clicking *Download CSV*).

Screenshots: 09–11 (20-image ZIP, preview gallery, bad-files ZIP handled with no crash).
