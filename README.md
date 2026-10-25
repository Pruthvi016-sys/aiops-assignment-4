# DA3408 A4 — Application Monitoring: Observability with Prometheus & Grafana

A CPU-only **image captioning** app (Streamlit + `Salesforce/blip-image-captioning-base`) instrumented with
`prometheus_client`, scraped by **Prometheus** together with **node_exporter**, with alerts sent to
**Alertmanager** and a **Grafana** dashboard that flows from high-level health down to hardware.

| Video | Link |
|---|---|
| 🎥 Demo + explanation (2–5 min) | _add Google Drive link here_ |
| 🎥 Dashboard recording (~1 min, 5 s refresh) | _add Google Drive link here_ |

---

## Where to find each requirement

| Assignment requirement | Where it is answered | Evidence |
|---|---|---|
| **1. Streamlit app, CPU-friendly model** (BLIP base, CPU only) | [`app.py`](app.py) | screenshots 02, 07, 08 |
| Single mode — upload an image, get a caption | [`app.py`](app.py) → `run_single()` | 07, 08 |
| Bulk mode — upload a ZIP of images | [`app.py`](app.py) → `run_bulk()`, `read_zip_entries()` | 09, 10 |
| `/metrics` endpoint on a separate port (8000) | [`metrics.py`](metrics.py) → `start_metrics_server()` | 05, 21, 22 |
| **2A. Counters** | [`metrics.py`](metrics.py); explained in [`METRICS.md` §1](METRICS.md#1-custom-application-metrics-28) | 21 |
| **2A. Gauges** | [`metrics.py`](metrics.py); [`METRICS.md` §1](METRICS.md#1-custom-application-metrics-28) | 22 |
| **2A. Histograms** | [`metrics.py`](metrics.py); [`METRICS.md` §1, §3.4–3.5](METRICS.md#34-reading-cumulative-histogram-buckets) | 22 |
| **2A. Summaries** (`_sum`, `_count`) | [`metrics.py`](metrics.py); [`METRICS.md` §3.3](METRICS.md#33-_sum--_count--average) | 05 |
| **2A. Custom labels** (client IP, session ID, browser) | [`app.py`](app.py) → `get_client()`; [`METRICS.md` §1](METRICS.md#1-custom-application-metrics-28) | 21, 14 |
| **2B. node_exporter + Prometheus scrape config** | [`prometheus/prometheus.yml`](prometheus/prometheus.yml), [`docker-compose.yml`](docker-compose.yml) | 03, 06 |
| **2B. Correlation of system and app metrics** | [`METRICS.md` §3.1, §5](METRICS.md#31-rate-on-a-counter--per-second-speed); [`DASHBOARD.md` §1](DASHBOARD.md#1-grafana-dashboard) | 15 |
| **Alerting pipeline** (objective) | [`prometheus/alert_rules.yml`](prometheus/alert_rules.yml), [`alertmanager/alertmanager.yml`](alertmanager/alertmanager.yml); [`DASHBOARD.md` §2](DASHBOARD.md#2-alerting-pipeline) | 17, 18, 19 |
| **2D. Grafana dashboard** — health, throughput, latency, system resources | [`grafana/dashboard_export.json`](grafana/dashboard_export.json); [`DASHBOARD.md` §1](DASHBOARD.md#1-grafana-dashboard) | 12–16 |
| **7 Commandments of Plotting** | [`DASHBOARD.md` §1](DASHBOARD.md#1-grafana-dashboard) | 12–16 |
| **Rubric: App handles single & ZIP without crashing on CPU** | [`DASHBOARD.md` §3](DASHBOARD.md#3-how-the-app-stays-stable-on-cpu-application-logic) | 09, 11 |
| **Black Box rule** — logic of every metric calculated by hand | [`METRICS.md`](METRICS.md) | 15, 21, 22 |
| **Attribution** — prompt for AI-generated PromQL / regex | [`AI_prompt_usage.md`](AI_prompt_usage.md), comments in [`alert_rules.yml`](prometheus/alert_rules.yml), `_ai_attribution` in the dashboard JSON | – |
| **Deliverable: GitHub repo with app + `prometheus.yml`** | this repository | – |
| **Deliverable: Grafana dashboard JSON export** | [`grafana/dashboard_export.json`](grafana/dashboard_export.json) | 20 |
| **Deliverable: dashboard video (~1 min, 5 s refresh)** | link at the top | – |
| **Submission: setup and run guide** | [How to run end to end](#how-to-run-end-to-end) below | – |

---

## Repository structure

```
.
├── app.py                          # Streamlit app: single image + bulk ZIP captioning
├── metrics.py                      # all Prometheus metrics + /metrics server on port 8000
├── requirements.txt
├── .streamlit/config.toml          # port 8501, upload size, file watcher off
├── scripts/make_sample_zip.py      # downloads 20 test photos, builds test ZIPs
├── prometheus/
│   ├── prometheus.yml              # scrape config: app, node_exporter, prometheus, alertmanager
│   └── alert_rules.yml             # 9 alert rules (commented with AI prompt + logic)
├── alertmanager/alertmanager.yml   # alert routing
├── grafana/
│   ├── dashboard_export.json       # dashboard JSON exported from Grafana
│   ├── dashboards/image_captioning_dashboard.json   # same dashboard, auto-loaded by Grafana
│   └── provisioning/               # auto-adds Prometheus datasource + dashboard
├── docker-compose.yml              # Prometheus, node_exporter, Alertmanager, Grafana
├── METRICS.md                      # every metric + PromQL logic calculated by hand
├── AI_prompt_usage.md              # prompt used for every AI-generated query
├── DASHBOARD.md                    # dashboard layout, 7 commandments, alerting, app design
└── evidence_screenshots/           # 22 screenshots of the end-to-end run
```

---

## How to run end to end

Tested on Ubuntu with Python 3.14, Docker 29, 12-core CPU, 14.8 GB RAM. Needs internet once to download the model (~1 GB).

**1. Install**
```bash
git clone https://github.com/Pruthvi016-sys/aiops-assignment-4.git
cd aiops-assignment-4
python3 -m venv venv
source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

**2. Start the monitoring stack**
```bash
docker compose up -d
docker compose ps        # prometheus, node_exporter, alertmanager, grafana → Up
```
If Docker is missing: `sudo apt install -y docker.io docker-compose-v2`.
If it says a container name is already in use: `docker rm -f grafana prometheus node_exporter alertmanager` and run again.

**3. Start the app** (keep this terminal open)
```bash
streamlit run app.py
```
Open **http://localhost:8501** once — this loads the model and starts the metrics server.

**4. Check everything is connected**

| URL | Expect |
|---|---|
| http://localhost:8000/metrics | `imgcap_…` metrics |
| http://localhost:9090/targets | caption_app, node, prometheus, alertmanager all **UP** |
| http://localhost:3000 (admin / admin) | dashboard *Image Captioning — Application & System Observability* |

**5. Generate traffic** (second terminal)
```bash
source venv/bin/activate
python scripts/make_sample_zip.py --count 20
```
- **Single image** tab: upload a photo from `samples/images/` → *Generate caption*
- **Bulk (ZIP)** tab: upload `samples/bulk_20.zip` → *Caption all images*, then `samples/bulk_with_bad_files.zip`
- Watch the dashboard: CPU rises inside the orange "bulk job" bands.

**6. Test the alert**
Press **Ctrl+C** in the Streamlit terminal → after ~20 s the dashboard shows **DOWN ✖**, and `CaptionAppDown` fires at
http://localhost:9090/alerts and http://localhost:9093. Start the app again and reload the page → back to **UP ✔**.

**7. Stop**
```bash
docker compose stop        # or: docker compose down
```

---

## Evidence screenshots

All in [`evidence_screenshots/`](evidence_screenshots).

| # | Shows |
|---|---|
| [01](evidence_screenshots/01_terminal_pip_install_ok.png) | Dependencies installed |
| [02](evidence_screenshots/02_terminal_blip_model_cpu_test.png) | BLIP model tested on CPU (1.15 s per caption) |
| [03](evidence_screenshots/03_terminal_docker_stack_up_ports.png) | Prometheus, node_exporter, Alertmanager, Grafana running |
| [04](evidence_screenshots/04_terminal_streamlit_running.png) | Streamlit running |
| [05](evidence_screenshots/05_metrics_endpoint_before_traffic.png) | `/metrics` on port 8000, all series initialised |
| [06](evidence_screenshots/06_prometheus_targets_all_up.png) | Prometheus targets — app and node_exporter UP |
| [07](evidence_screenshots/07_streamlit_single_caption_pier.png) | Single mode caption |
| [08](evidence_screenshots/08_streamlit_single_caption_snow.png) | Single mode caption |
| [09](evidence_screenshots/09_streamlit_bulk_zip_20_results.png) | Bulk ZIP: 20 / 20 captioned |
| [10](evidence_screenshots/10_streamlit_bulk_zip_preview_gallery.png) | Bulk ZIP preview gallery |
| [11](evidence_screenshots/11_streamlit_bulk_zip_bad_files_handled.png) | Bad ZIP handled — 5 ok, 1 error, junk skipped, no crash |
| [12](evidence_screenshots/12_grafana_row1_health_row2_throughput_latency.png) | Dashboard ① health, ② throughput & latency |
| [13](evidence_screenshots/13_grafana_row2_latency_row3_workload.png) | Dashboard ② latency, ③ workload |
| [14](evidence_screenshots/14_grafana_row3_model_row4_clients.png) | Dashboard ③ model, ④ clients |
| [15](evidence_screenshots/15_grafana_row5_system_cpu_ram_correlation.png) | Dashboard ⑤ CPU vs throughput — app ↔ system correlation |
| [16](evidence_screenshots/16_grafana_row5_disk_network_machine.png) | Dashboard ⑤ disk, network, machine |
| [17](evidence_screenshots/17_alert_grafana_app_down_alert_firing.png) | App stopped → DOWN ✖, 1 firing alert |
| [18](evidence_screenshots/18_alert_prometheus_CaptionAppDown_firing.png) | Prometheus: CaptionAppDown FIRING |
| [19](evidence_screenshots/19_alert_alertmanager_received.png) | Alertmanager received the alert |
| [20](evidence_screenshots/20_terminal_sample_zips_and_dashboard_export.png) | Test ZIPs created, dashboard JSON exported |
| [21](evidence_screenshots/21_metrics_requests_total_client_labels.png) | Counters with client_ip / session_id / browser labels |
| [22](evidence_screenshots/22_metrics_inference_histogram_buckets.png) | Histogram buckets, `_sum`, `_count`, gauges |

---

# AI Assistance and Contribution

### AI Tool
Claude

### Areas of AI Assistance

**1. Conceptual Understanding and Query Development**

AI was used to understand the monitoring system, the roles of its components, and how metrics are collected and analyzed. It also assisted in writing some PromQL queries and interpreting their results. The prompts associated with AI-assisted queries are documented in [`Ai_prompt_usage.md`](Ai_prompt_usage.md).

**Impact:** Improved my understanding of the system and accelerated query development, leaving more time for testing and validating the results.

**2. Debugging and Troubleshooting**

AI was consulted to investigate issues encountered during implementation, including repetitive words in image captions, Docker container naming conflicts, and dashboard layout problems.

**Impact:** Helped identify possible causes of errors and determine appropriate fixes during development.

**3. Execution and Documentation Support**

AI helped explain terminal commands used to run the application and monitoring components. It also assisted in organizing the `README.md`, which I reviewed before submission.

**Impact:** Made the execution process easier to follow and improved the clarity of the project documentation.


- I reviewed and executed the code, configurations, and commands included in the final submission.
- The application, monitoring infrastructure, and alerts were run and tested locally on my laptop.
- All submitted screenshots, metric snapshots, and performance measurements were collected from actual executions and were not generated or fabricated by AI.
- I verified the manual calculations in `METRICS.md` against the corresponding values displayed in Prometheus and Grafana.