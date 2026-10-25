# Metrics and PromQL — explained and calculated by hand

This file lists every metric the app exposes, why it exists, and works through the logic of the PromQL used in
`prometheus/alert_rules.yml` and the Grafana dashboard, using **real values** from this app.
Who generated which query is listed in [`AI_prompt_usage.md`](AI_prompt_usage.md).

Sources of the numbers (all in [`evidence_screenshots/`](evidence_screenshots)):

- **Snapshot A — `/metrics` page** (screenshots 21, 22): taken after an app restart, then 1 single-image caption and
  1 `bulk_with_bad_files.zip` job (5 photos + `corrupt.jpg` + `notes.txt` + 2 hidden files).
- **Snapshot B — Grafana dashboard** (screenshots 12–16): a 15-minute window with 2 single captions and 3 bulk jobs
  (`bulk_20.zip`, `bulk_with_bad_files.zip`, `bulk_20.zip` again). Beam width 3, max 30 tokens.
- Machine: Ubuntu laptop, 12 CPU cores, 14.8 GiB RAM, CPU only (`torch 2.14.1+cpu`).

---

## 1. Custom application metrics (28)

Defined in [`metrics.py`](metrics.py), exposed on `http://localhost:8000/metrics` (separate port from Streamlit's 8501).
Every label combination is created at 0 on start-up, so panels show 0 instead of "No data".

### Counters — only go up (reset to 0 when the app restarts)

| Metric | Labels | Incremented when | Why it is monitored |
|---|---|---|---|
| `imgcap_images_processed_total` | `mode`, `status` | Each image finishes (success or error) | Throughput and error ratio |
| `imgcap_requests_total` | `mode`, `client_ip`, `session_id`, `browser` | A user clicks *Generate caption* (1) or *Caption all images* (1 per ZIP) | Who uses the app and how often (client metadata) |
| `imgcap_errors_total` | `mode`, `error_type` | An image or ZIP fails (`bad_image`, `too_large`, `inference`, `out_of_memory`, `bad_zip`, `other`) | Error types; `HighErrorRate` alert |
| `imgcap_zip_uploads_total` | – | A valid ZIP starts processing | Bulk usage |
| `imgcap_zip_files_skipped_total` | `reason` | A file in a ZIP is skipped (`not_image`, `hidden_file`, `too_large`, `over_limit`) | Shows bulk mode skips junk instead of crashing |
| `imgcap_bytes_uploaded_total` | `mode` | Bytes of every image received | Data volume |
| `imgcap_caption_words_total` | `mode` | Words in every caption | Output volume |
| `imgcap_sessions_started_total` | `browser` | A new browser session opens | Number of users |

### Gauges — current value, can go up and down

| Metric | Labels | Value | Why it is monitored |
|---|---|---|---|
| `imgcap_active_requests` | `mode` | Requests being processed now (`track_inprogress()`) | Concurrency |
| `imgcap_waiting_for_model` | – | Images waiting for the model lock | CPU queue: only one inference runs at a time |
| `imgcap_bulk_queue_remaining` | – | Images left in the running ZIP (0 when idle) | Progress; drives the orange "bulk job" bands |
| `imgcap_last_zip_images` | – | Images in the last ZIP | Job size |
| `imgcap_model_loaded` | – | 1 when BLIP is loaded, else 0 | Readiness; `ModelNotLoaded` alert |
| `imgcap_model_load_seconds` | – | Time to load the model at start-up | Cold-start cost |
| `imgcap_model_parameters` | – | Number of model parameters | Model size |
| `imgcap_last_success_timestamp_seconds` | – | Unix time of the last successful caption | Freshness |
| `imgcap_process_memory_bytes` | `type` (`rss`, `vms`) | psutil memory of the app process | RAM cost of the model |
| `imgcap_process_threads` | – | Threads of the app process | Torch thread usage |

### Histograms — distributions (`_bucket{le=…}`, `_sum`, `_count`)

| Metric | Labels | Buckets | Why it is monitored |
|---|---|---|---|
| `imgcap_inference_seconds` | `mode` | 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 13, 20 s | Latency per image; percentiles; alert |
| `imgcap_preprocess_seconds` | `mode` | 5 ms … 2 s | Decode + resize time, separate from model time |
| `imgcap_bulk_job_seconds` | – | 1 s … 20 min | Duration of a whole ZIP |
| `imgcap_image_size_bytes` | `mode` | 10 KB … 20 MB | What users upload |
| `imgcap_caption_length_words` | `mode` | 2, 4, 6, 8, 10, 12, 15, 20, 30 words | Output quality |

Buckets were chosen for this workload (BLIP base on CPU takes about 1–3 s per image), not left at library defaults.

### Summaries — `_sum` and `_count`

| Metric | Labels | Observed value | Why it is monitored |
|---|---|---|---|
| `imgcap_request_latency_seconds` | `mode` | End-to-end time per request (one image, or one whole ZIP) | What the user actually waits for |
| `imgcap_image_megapixels` | `mode` | Resolution of each image | Input size |
| `imgcap_zip_images` | – | Valid images per ZIP | Job size |

### Info and Enum

| Metric | Content |
|---|---|
| `imgcap_model_info` | `name="Salesforce/blip-image-captioning-base"`, `device="cpu"`, `threads="12"`, `torch_version="2.14.1+cpu"` — proves inference runs on CPU |
| `imgcap_app_state` | One of `starting`, `loading_model`, `idle`, `single`, `bulk` is 1 |

**Label cardinality note:** each distinct `(client_ip, session_id, browser)` creates new `imgcap_requests_total`
series. That is fine for a demo with a few browsers; in production `session_id` would not be a label.

---

## 2. Automatic metrics used

| Metric | Source | Used for |
|---|---|---|
| `process_cpu_seconds_total` | prometheus_client (app process) | CPU used by the app itself |
| `process_resident_memory_bytes` | prometheus_client | RAM of the app (BLIP in memory) |
| `process_start_time_seconds` | prometheus_client | App uptime |
| `node_cpu_seconds_total` | node_exporter | Machine CPU %, CPU breakdown, number of cores, `HighCPUUsage` |
| `node_memory_MemTotal_bytes`, `node_memory_MemAvailable_bytes` | node_exporter | RAM used; `LowMemory` |
| `node_load1`, `node_load5` | node_exporter | Load vs cores |
| `node_disk_read_bytes_total`, `node_disk_written_bytes_total` | node_exporter | Disk I/O |
| `node_filesystem_avail_bytes`, `node_filesystem_size_bytes` | node_exporter | Disk usage; `DiskAlmostFull` |
| `node_network_receive_bytes_total`, `node_network_transmit_bytes_total` | node_exporter | Network |
| `up` | Prometheus | Target health; `CaptionAppDown`, `NodeExporterDown` |
| `ALERTS` | Prometheus | "Firing alerts" panel |

---

## 3. PromQL building blocks — worked by hand

### 3.1 `rate()` on a counter → per-second speed

`rate(counter[w])` = (last value − first value in the window) ÷ window length.

**Throughput:** `sum by (mode) (rate(imgcap_images_processed_total{status="success"}[1m]))`

The `bulk_20.zip` job captioned 20 images and took **49.89 s** end to end (max of the bulk request-latency Summary,
snapshot B). When the 1-minute window covers the whole job, the counter grew by 20 in 60 s:

```
rate = 20 / 60 s = 0.33 images/s
```

The throughput panel peaked at **0.34 images/s**, matching this. While the job runs, the real speed is
20 / 49.89 s = 0.40 images/s; the 1-minute window averages it with the idle seconds around the job.

**Check of the job time:** the app showed an average inference of 2.47 s for those 20 images →
20 × 2.47 = 49.4 s of model time, plus about 20 × 0.017 s = 0.3 s of preprocessing → **≈ 49.7 s**,
close to the 49.89 s measured by the Summary.

**Machine CPU %:** `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))`

`node_cpu_seconds_total{mode="idle"}` counts how many seconds each core has been idle since boot. Its rate is the idle
fraction of that core (1 = fully idle). At the peak of the first bulk job the panel showed **84.8 %**:

```
average idle fraction = 1 − 0.848 = 0.152
busy cores            = 0.848 × 12 cores ≈ 10.2 cores
```

**App process CPU %:** `100 * rate(process_cpu_seconds_total{job="caption_app"}[1m]) / 12`

The app's own CPU peaked at **83.4 %** → 0.834 × 12 ≈ **10.0 cores**. So the captioning app explains
10.0 / 10.2 ≈ **98 %** of the machine's busy CPU at that moment. This is the system-vs-application corroboration
on the dashboard.

**Number of cores:** `count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))`
There is one idle series per core (`cpu="0"` … `cpu="11"`): the inner `count by (cpu)` gives 12 series and the
outer `count` gives **12**.

### 3.2 `increase()` on a counter → how many in a window

`increase(counter[w])` = rate × window, i.e. the count in that window.

**Errors & skipped entries** panel during the `bulk_with_bad_files.zip` job (snapshot B):

| Series | Value | File |
|---|---|---|
| `error: bad_image` | 1 | `corrupt.jpg` (text pretending to be a jpg) |
| `skipped: hidden_file` | 2 | `.hidden.png` and `__MACOSX/._photo_001.jpg` |
| `skipped: not_image` | 1 | `notes.txt` |

The `> 0` at the end of the query hides series that did not change, so the panel is empty when there are no errors.

### 3.3 `_sum / _count` → average

| Quantity | Calculation (real values) | Result |
|---|---|---|
| Mean inference time, bulk (snapshot A) | 11.62 s ÷ 5 | **2.32 s / image** |
| Mean inference time, single (snapshot A) | 3.95 s ÷ 1 | **3.95 s** |
| Mean preprocessing (snapshot B) | panel mean | **16.9 ms / image** |
| Mean inference (snapshot B) | panel mean | **2.19 s / image** |
| Mean image resolution | every test photo is 800 × 600 = 480 000 px | **0.48 MP** (panel: 0.480) |

So preprocessing is 0.0169 / (0.0169 + 2.19) ≈ **0.8 %** of the time per image; the rest is the model.

The dashboard uses the same idea over a window, e.g. *Average request latency*:
`rate(imgcap_request_latency_seconds_sum[5m]) / rate(imgcap_request_latency_seconds_count[5m])`.

### 3.4 Reading cumulative histogram buckets

Bucket counters are **cumulative**: `le="3.0"` counts every observation ≤ 3 s. Per-bucket counts are differences.

Bulk `imgcap_inference_seconds` (snapshot A):

| `le` | cumulative count | images in this bucket |
|---|---|---|
| 1.5 | 0 | – |
| 2.0 | 1 | 1 (1.5–2.0 s) |
| 3.0 | 5 | 5 − 1 = **4** (2.0–3.0 s) |
| 5.0 … +Inf | 5 | 0 |

Caption length `imgcap_caption_length_words` (snapshot B, 33 captions):

| `le` (words) | 4 | 6 | 8 | 10 | 12 | 15 | 20 | 30 |
|---|---|---|---|---|---|---|---|---|
| cumulative | 0 | 1 | 8 | 17 | 30 | 33 | 33 | 33 |
| in bucket | 0 | 1 | 7 | 9 | **13** | 3 | 0 | 0 |

Most captions have 10–12 words and none has more than 15, so no runaway / repeated captions.

### 3.5 `histogram_quantile()` → percentiles

Query: `histogram_quantile(0.95, sum by (le) (rate(imgcap_inference_seconds_bucket[1m])))`

Method: find the bucket that contains the target rank, then interpolate linearly inside it.

**p50 (bulk, snapshot A, 5 observations):**
1. Target rank = 0.50 × 5 = **2.5**
2. Cumulative: `le=2.0` → 1, `le=3.0` → 5, so rank 2.5 is in the **2.0–3.0 s** bucket (4 images)
3. 2.0 + (2.5 − 1) / (5 − 1) × (3.0 − 2.0) = 2.0 + 0.375 = **2.375 s**

**p95 (bulk, snapshot A):** rank = 0.95 × 5 = 4.75 → 2.0 + (4.75 − 1) / 4 × 1.0 = **2.94 s**

**Median caption length (snapshot B):** rank = 0.5 × 33 = 16.5 → bucket 8–10 words (8 below, 9 inside) →
8 + (16.5 − 8) / 9 × 2 = **9.9 words**

**Why percentiles are estimates — the photo_012 outlier.** In the first `bulk_20.zip` job, `photo_012.jpg` took
**10.0 s** (shown in the app table) while the other visible rows took 1.4–3.3 s. It fell in the **8–13 s** bucket. Because
`histogram_quantile` assumes values are spread evenly inside a bucket, it placed p99 at 8 + (fraction) × 5, which is why
the dashboard showed p99 = **12.55 s** and p95 = **10.75 s**, above the real maximum of 10.0 s. The accuracy depends on
the bucket boundaries; the averages from `_sum / _count` are exact.

---

## 4. Alert rules — logic and observed behaviour

| Alert | Expression | Logic | Observed |
|---|---|---|---|
| `CaptionAppDown` (critical) | `up{job="caption_app"} == 0` for 15 s | Prometheus sets `up = 0` when it cannot scrape `:8000` | Streamlit stopped → target DOWN, alert PENDING then FIRING after 15 s, received by Alertmanager, resolved on restart (screenshots 17–19) |
| `ModelNotLoaded` (warning) | `imgcap_model_loaded == 0` for 2 m | The metrics server starts before BLIP finishes loading | Not fired: model loads in **3.59 s** (`imgcap_model_load_seconds`) |
| `HighInferenceLatency` (warning) | p95 > 5 s for 30 s | Normal p95 ≈ 2–3 s, so 5 s ≈ 2× normal | p95 briefly reached 10.75 s from the photo_012 outlier; whether it stayed above 5 s for the full 30 s was not captured in the screenshots |
| `HighErrorRate` (warning) | errors / all images over 5 m > 0.2 | Error ratio | Not fired: snapshot A = 1 / (1 + 5 + 1) = **14.3 %** |
| `BulkJobStuck` (warning) | queue > 0 and no change in 2 m | Countdown frozen | Not fired: the queue drops every ~2.5 s |
| `NodeExporterDown` (critical) | `up{job="node"} == 0` | node_exporter unreachable | Not fired |
| `HighCPUUsage` (warning) | CPU > 90 % for 1 m | | Not fired: peak 84.8 %, and only for a few scrapes |
| `LowMemory` (warning) | available < 10 % | `MemAvailable / MemTotal` | Not fired: (14.8 − 5.09) / 14.8 = **65.6 %** available |
| `DiskAlmostFull` (warning) | free < 10 % | | Not fired: disk 73.4 % used → 26.6 % free |

---

## 5. Findings from the metrics

1. **The app causes the CPU spike.** During bulk jobs the app process uses ≈ 10.0 of the ≈ 10.2 busy cores (98 %),
   and machine CPU, CPU *user* time and load average all rise only inside the orange bulk-job bands.
2. **Memory stays flat.** The app holds ≈ 2.0–2.2 GB (model loaded once, `st.cache_resource`) and machine RAM stays near
   5 GB of 14.8 GB, because images are captioned one at a time behind a lock.
3. **Model time dominates.** Preprocessing is ≈ 17 ms per image against ≈ 2.2 s of inference, so speeding up the app
   means a faster model or fewer beams, not faster image loading.
4. **Bad input is handled, not crashed on.** The bad ZIP produced 5 captions, 1 `bad_image` error and 3 skipped files,
   all counted in metrics, with the app still UP.
5. **Percentiles can overstate outliers.** One 10.0 s image made p99 read 12.55 s because of the wide 8–13 s bucket
   (§3.5). A narrower bucket there would give a closer estimate.
