import psutil
from prometheus_client import (Counter, Enum, Gauge, Histogram, Info, Summary,
                               start_http_server)

METRICS_PORT = 8000
MODES = ["single", "bulk"]

# ---------------- Counters ----------------
IMAGES_PROCESSED = Counter(
    "imgcap_images_processed",
    "Images processed, split by mode (single/bulk) and result (success/error)",
    ["mode", "status"],
)
REQUESTS = Counter(
    "imgcap_requests",
    "Caption requests (a single upload or one ZIP job) per client",
    ["mode", "client_ip", "session_id", "browser"],
)
ERRORS = Counter("imgcap_errors", "Errors by mode and error type", ["mode", "error_type"])
ZIP_UPLOADS = Counter("imgcap_zip_uploads", "ZIP files accepted for bulk processing")
ZIP_FILES_SKIPPED = Counter("imgcap_zip_files_skipped", "Files inside ZIPs that were skipped", ["reason"])
BYTES_UPLOADED = Counter("imgcap_bytes_uploaded", "Bytes of image data received", ["mode"])
CAPTION_WORDS = Counter("imgcap_caption_words", "Words generated in captions", ["mode"])
SESSIONS_STARTED = Counter("imgcap_sessions_started", "New browser sessions opened", ["browser"])

# ---------------- Gauges ----------------
ACTIVE_REQUESTS = Gauge("imgcap_active_requests", "Requests being processed right now", ["mode"])
WAITING_FOR_MODEL = Gauge("imgcap_waiting_for_model", "Images waiting for the model lock (CPU queue)")
BULK_QUEUE = Gauge("imgcap_bulk_queue_remaining", "Images still left in the running ZIP job")
LAST_ZIP_SIZE = Gauge("imgcap_last_zip_images", "Number of images in the most recent ZIP")
MODEL_LOADED = Gauge("imgcap_model_loaded", "1 if the captioning model is loaded, else 0")
MODEL_LOAD_SECONDS = Gauge("imgcap_model_load_seconds", "Seconds it took to load the model")
MODEL_PARAMS = Gauge("imgcap_model_parameters", "Number of parameters of the loaded model")
LAST_SUCCESS = Gauge("imgcap_last_success_timestamp_seconds", "Unix time of last successful caption")
PROCESS_MEMORY = Gauge("imgcap_process_memory_bytes", "Memory of the app process", ["type"])
PROCESS_THREADS = Gauge("imgcap_process_threads", "Threads used by the app process")

# ---------------- Histograms ----------------
INFERENCE_TIME = Histogram(
    "imgcap_inference_seconds", "Model inference (generate) time per image", ["mode"],
    buckets=(0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 13, 20),
)
PREPROCESS_TIME = Histogram(
    "imgcap_preprocess_seconds", "Image decode + resize + tensor conversion time per image", ["mode"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
BULK_JOB_TIME = Histogram(
    "imgcap_bulk_job_seconds", "Total time to caption a whole ZIP",
    buckets=(1, 5, 10, 20, 30, 60, 120, 300, 600, 1200),
)
IMAGE_SIZE = Histogram(
    "imgcap_image_size_bytes", "Size of each uploaded image", ["mode"],
    buckets=(10e3, 50e3, 100e3, 250e3, 500e3, 1e6, 2.5e6, 5e6, 10e6, 20e6),
)
CAPTION_LENGTH = Histogram(
    "imgcap_caption_length_words", "Words per generated caption", ["mode"],
    buckets=(2, 4, 6, 8, 10, 12, 15, 20, 30),
)

# ---------------- Summaries (_count and _sum) ----------------
REQUEST_LATENCY = Summary("imgcap_request_latency_seconds", "End-to-end latency of a request (single image or full ZIP job)", ["mode"])
IMAGE_MEGAPIXELS = Summary("imgcap_image_megapixels", "Resolution of uploaded images in megapixels", ["mode"])
ZIP_IMAGES = Summary("imgcap_zip_images", "Number of valid images per ZIP upload")

# ---------------- Info / Enum ----------------
MODEL_INFO = Info("imgcap_model", "Details of the captioning model")
APP_STATE = Enum("imgcap_app_state", "What the app is doing right now",
                 states=["starting", "loading_model", "idle", "single", "bulk"])

_proc = psutil.Process()
PROCESS_MEMORY.labels("rss").set_function(lambda: _proc.memory_info().rss)
PROCESS_MEMORY.labels("vms").set_function(lambda: _proc.memory_info().vms)
PROCESS_THREADS.set_function(lambda: _proc.num_threads())

# create every label combination at 0 so panels show 0 instead of "No data"
for _m in MODES:
    for _s in ["success", "error"]:
        IMAGES_PROCESSED.labels(_m, _s)
    for _e in ["bad_image", "too_large", "inference", "out_of_memory", "other"]:
        ERRORS.labels(_m, _e)
    ACTIVE_REQUESTS.labels(_m)
    BYTES_UPLOADED.labels(_m)
    CAPTION_WORDS.labels(_m)
    INFERENCE_TIME.labels(_m)
    PREPROCESS_TIME.labels(_m)
    IMAGE_SIZE.labels(_m)
    CAPTION_LENGTH.labels(_m)
    REQUEST_LATENCY.labels(_m)
    IMAGE_MEGAPIXELS.labels(_m)
ERRORS.labels("bulk", "bad_zip")
for _r in ["not_image", "hidden_file", "too_large", "over_limit"]:
    ZIP_FILES_SKIPPED.labels(_r)

_server_started = False


def start_metrics_server(port=METRICS_PORT):
    global _server_started
    if _server_started:
        return
    try:
        start_http_server(port)
    except OSError:
        print(f"metrics port {port} already in use, assuming server is running")
    _server_started = True
    APP_STATE.state("starting")
