# AI prompt usage (PromQL attribution)


- The PromQL and label regexes in `prometheus/alert_rules.yml` and in the Grafana dashboard
  (`grafana/dashboards/image_captioning_dashboard.json`, exported copy `grafana/dashboard_export.json`) were
  generated with AI assistance (**Claude, Anthropic — model **). Both files carry a comment /
  `_ai_attribution` field pointing here.

- The **Prompt / requirement** column below is the specific requirement from that request each query was produced for.
- The **logic of every query is calculated by hand**, with real numbers from this app, in [`METRICS.md`](METRICS.md).

## 1. Alert rules (`prometheus/alert_rules.yml`)

| Rule | PromQL | Prompt / requirement |
|---|---|---|
| `CaptionAppDown` (critical) | `up{job="caption_app"} == 0` for 15 s | "Alert when the Streamlit app's /metrics target is down" |
| `ModelNotLoaded` (warning) | `imgcap_model_loaded == 0` for 2 m | "Alert if the app is up but the BLIP model has not loaded" |
| `HighInferenceLatency` (warning) | `histogram_quantile(0.95, sum by (le) (rate(imgcap_inference_seconds_bucket[1m]))) > 5` | "Alert when the p95 inference time per image is above 5 seconds" |
| `HighErrorRate` (warning) | `sum(rate(imgcap_images_processed_total{status="error"}[5m])) / sum(rate(imgcap_images_processed_total[5m])) > 0.2` | "Alert when more than 20 % of images fail" |
| `BulkJobStuck` (warning) | `imgcap_bulk_queue_remaining > 0 and changes(imgcap_bulk_queue_remaining[2m]) == 0` | "Alert when a bulk ZIP job stops making progress" |
| `NodeExporterDown` (critical) | `up{job="node"} == 0` for 15 s | "Alert when node_exporter is down" |
| `HighCPUUsage` (warning) | `100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))) > 90` for 1 m | "Alert when machine CPU is above 90 % for a minute" |
| `LowMemory` (warning) | `100 * node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 10` | "Alert when less than 10 % RAM is available" |
| `DiskAlmostFull` (warning) | `100 * node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs\|overlay"} / node_filesystem_size_bytes{…} < 10` | "Alert when the root disk is almost full, ignoring tmpfs and docker overlay filesystems" |

## 2. Grafana dashboard panels (`grafana/dashboards/image_captioning_dashboard.json`)

| Row | Panel | PromQL | Prompt / requirement |
|---|---|---|---|
| ① Health | Target health | `up{job=~"caption_app\|node\|prometheus\|alertmanager"}` | "Stat panel showing UP/DOWN for every scrape target" |
| ① Health | Model status | `imgcap_model_loaded` | "Show whether the model is loaded" |
| ① Health | App uptime | `time() - process_start_time_seconds{job="caption_app"}` | "Uptime of the app process" |
| ① Health | In progress | `sum(imgcap_active_requests)`<br>`imgcap_waiting_for_model` | "Requests in progress and images queued for the CPU" |
| ① Health | Firing alerts | `count(ALERTS{alertstate="firing"}) or vector(0)` | "Count firing Prometheus alerts, show 0 instead of no data" |
| ① Health | Images captioned | `sum by (mode) (imgcap_images_processed_total{status="success", mode=~"$mode"})` | "Total images captioned split by single vs bulk" |
| ① Health | Error ratio | `(sum(rate(…{status="error"}[5m])) / sum(rate(imgcap_images_processed_total[5m]))) or vector(0)` | "Share of failed images over 5 minutes" |
| ① Health | Avg request latency | `sum by (mode) (rate(imgcap_request_latency_seconds_sum[5m])) / sum by (mode) (rate(imgcap_request_latency_seconds_count[5m]))` | "Average request latency from the Summary using _sum and _count" |
| ① Health | Sessions & ZIP uploads | `sum(imgcap_sessions_started_total)`<br>`imgcap_zip_uploads_total` | "Total sessions and ZIP uploads" |
| ② Throughput & latency | Throughput | `sum by (mode) (rate(imgcap_images_processed_total{status="success"}[1m]))`<br>`sum(rate(…{status="error"}[1m]))` | "Images captioned per second by mode, with errors per second" |
| ② Throughput & latency | Inference latency p50/p95/p99 | `histogram_quantile(0.50 \| 0.95 \| 0.99, sum by (le) (rate(imgcap_inference_seconds_bucket[1m])))` | "p50, p95 and p99 of the inference histogram over 1 minute" |
| ② Throughput & latency | Request latency single vs ZIP | `sum by (mode) (rate(imgcap_request_latency_seconds_sum[1m])) / sum by (mode) (rate(…_count[1m]))` | "Compare single-image vs whole-ZIP latency from the Summary" |
| ② Throughput & latency | Preprocess vs inference | `sum(rate(imgcap_preprocess_seconds_sum[1m])) / sum(rate(imgcap_preprocess_seconds_count[1m]))` (and same for `imgcap_inference_seconds`) | "Average time per image in preprocessing vs model inference" |
| ② Throughput & latency | Latency heatmap | `sum by (le) (increase(imgcap_inference_seconds_bucket[$__rate_interval]))` | "Heatmap of the inference histogram buckets" |
| ③ Workload | Bulk progress | `imgcap_bulk_queue_remaining`<br>`sum by (mode) (imgcap_active_requests)` | "Images left in the running ZIP and active requests" |
| ③ Workload | Errors & skipped entries | `sum by (error_type) (increase(imgcap_errors_total[1m])) > 0`<br>`sum by (reason) (increase(imgcap_zip_files_skipped_total[1m])) > 0` | "Errors per minute by type and skipped ZIP files by reason, hiding zero series" |
| ③ Workload | Caption length | `sort(sum by (le) (imgcap_caption_length_words_bucket{le!="+Inf"}))` | "Distribution of caption word counts from the histogram, without the +Inf bucket" |
| ③ Workload | Input size | `sum(rate(imgcap_image_size_bytes_sum[1m])) / sum(rate(…_count[1m]))`<br>`sum(rate(imgcap_image_megapixels_sum[1m])) / sum(rate(…_count[1m]))` | "Average image size in bytes and megapixels" |
| ③ Workload | ZIP jobs | `histogram_quantile(0.95, sum by (le) (rate(imgcap_bulk_job_seconds_bucket[5m])))`<br>`rate(imgcap_zip_images_sum[5m]) / rate(imgcap_zip_images_count[5m])` | "p95 ZIP job duration and average images per ZIP" |
| ③ Workload | Model footprint | `imgcap_model_parameters`, `imgcap_model_load_seconds`, `imgcap_process_memory_bytes{type="rss"}` | "Show model size, load time and process RAM" |
| ④ Clients | Requests per client IP | `sort_desc(sum by (client_ip) (imgcap_requests_total))` | "Requests grouped by the client_ip label" |
| ④ Clients | Top 10 sessions | `sort_desc(topk(10, sum by (session_id, client_ip) (imgcap_requests_total)))` | "Ten busiest sessions with their IP" |
| ④ Clients | Request rate by browser | `sum by (browser, mode) (increase(imgcap_requests_total[1m]))` | "Requests per minute by browser and mode" |
| ⑤ System | CPU vs throughput | `100 * (1 - avg(rate(node_cpu_seconds_total{job="node", mode="idle"}[1m])))`<br>`100 * rate(process_cpu_seconds_total{job="caption_app"}[1m]) / scalar(count(count by (cpu) (node_cpu_seconds_total{job="node", mode="idle"})))`<br>`sum(rate(imgcap_images_processed_total{status="success"}[1m]))` | "Machine CPU %, the app process's share of all cores, and throughput on a second axis, to correlate the app with the hardware" |
| ⑤ System | Memory | `node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes`<br>`process_resident_memory_bytes{job="caption_app"}`<br>`node_memory_MemTotal_bytes` | "Machine RAM used vs app RAM vs total RAM" |
| ⑤ System | CPU breakdown | `100 * sum by (mode) (rate(node_cpu_seconds_total{mode=~"user\|system\|iowait"}[1m])) / scalar(<cores>)` | "CPU time split into user, system and iowait" |
| ⑤ System | Load vs cores | `node_load1`, `node_load5`, `count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))` | "Load average compared with the number of cores" |
| ⑤ System | Disk I/O | `sum(rate(node_disk_read_bytes_total{device!~"loop.*\|ram.*\|dm-.*"}[1m]))` (and `written`) | "Disk read/write bytes per second, ignoring loop, ram and LVM mapper devices" |
| ⑤ System | Disk usage | `100 * (1 - node_filesystem_avail_bytes{mountpoint="/", fstype!~"tmpfs\|overlay"} / node_filesystem_size_bytes{…})` | "Percent of the root disk used" |
| ⑤ System | Network | `sum(rate(node_network_receive_bytes_total{device!~"lo\|veth.*\|docker.*\|br-.*"}[1m]))` (and `transmit`) | "Network bytes per second, ignoring loopback and Docker interfaces" |
| ⑤ System | Machine facts | `count(count by (cpu) (…))`, `node_memory_MemTotal_bytes`, CPU % query | "Number of cores, total RAM and current CPU" |

`$mode` is the dashboard's Mode filter (`single`, `bulk` or `.*` for All).

## 3. Annotations

| Where | PromQL | Prompt / requirement |
|---|---|---|
| "Bulk ZIP job running" (orange bands) | `imgcap_bulk_queue_remaining > 0` | "Annotation that shades every graph while a bulk ZIP job is running" |
| "App down" (red) | `up{job="caption_app"} == 0` | "Annotation marking when the app was down" |
