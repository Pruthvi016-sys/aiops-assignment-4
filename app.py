import io
import os
import threading
import time
import uuid
import zipfile

import pandas as pd
import streamlit as st
import torch
from PIL import Image, ImageOps, UnidentifiedImageError
from transformers import BlipForConditionalGeneration, BlipProcessor

import metrics as m

MODEL_NAME = "Salesforce/blip-image-captioning-base"
IMAGE_TYPES = ["jpg", "jpeg", "png", "bmp", "webp"]
MAX_ZIP_IMAGES = 100                  # protects the CPU from huge batches
MAX_IMAGE_BYTES = 20 * 1024 * 1024    # 20 MB per image
MAX_ZIP_UNCOMPRESSED = 500 * 1024 * 1024
MAX_SIDE = 1024                       # BLIP resizes to 384 anyway, so shrink big photos early

Image.MAX_IMAGE_PIXELS = 50_000_000   # decompression bomb guard

st.set_page_config(page_title="Image Captioning (CPU)", page_icon="🖼️", layout="wide")


@st.cache_resource
def init_metrics():
    m.start_metrics_server()
    return True


@st.cache_resource(show_spinner="Loading BLIP model on CPU (first time downloads ~1 GB)...")
def load_model():
    m.APP_STATE.state("loading_model")
    start = time.perf_counter()
    torch.set_num_threads(os.cpu_count() or 1)
    processor = BlipProcessor.from_pretrained(MODEL_NAME)
    model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME)
    model.eval()

    m.MODEL_LOAD_SECONDS.set(time.perf_counter() - start)
    m.MODEL_PARAMS.set(sum(p.numel() for p in model.parameters()))
    m.MODEL_LOADED.set(1)
    m.MODEL_INFO.info({
        "name": MODEL_NAME,
        "device": "cpu",
        "torch_version": torch.__version__,
        "threads": str(torch.get_num_threads()),
    })
    m.APP_STATE.state("idle")
    return processor, model


@st.cache_resource
def get_model_lock():
    # one inference at a time, so several users don't fight over the CPU and run out of RAM
    return threading.Lock()


def get_browser(user_agent):
    ua = user_agent.lower()
    if "edg/" in ua:
        return "edge"
    if "firefox" in ua:
        return "firefox"
    if "chrome" in ua or "chromium" in ua:
        return "chrome"
    if "safari" in ua:
        return "safari"
    if "python" in ua or "curl" in ua:
        return "script"
    return "other"


def get_client():
    headers = st.context.headers
    browser = get_browser(headers.get("User-Agent", ""))

    ip = getattr(st.context, "ip_address", None)
    if not ip:
        forwarded = headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() if forwarded else "127.0.0.1"

    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex[:8]
        m.SESSIONS_STARTED.labels(browser).inc()

    return {"ip": ip, "session": st.session_state.session_id, "browser": browser}


def classify_error(err):
    if isinstance(err, Image.DecompressionBombError):
        return "too_large"
    if isinstance(err, (UnidentifiedImageError, OSError, SyntaxError)):
        return "bad_image"
    if isinstance(err, MemoryError):
        return "out_of_memory"
    if isinstance(err, RuntimeError):
        return "inference"
    return "other"


def caption_bytes(data, mode, settings):
    """Decode one image, run BLIP on it and record all per-image metrics."""
    processor, model = load_model()
    m.BYTES_UPLOADED.labels(mode).inc(len(data))
    m.IMAGE_SIZE.labels(mode).observe(len(data))

    t0 = time.perf_counter()
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    m.IMAGE_MEGAPIXELS.labels(mode).observe(img.width * img.height / 1e6)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    inputs = processor(images=img, return_tensors="pt")
    m.PREPROCESS_TIME.labels(mode).observe(time.perf_counter() - t0)

    m.WAITING_FOR_MODEL.inc()
    with get_model_lock():
        m.WAITING_FOR_MODEL.dec()
        t1 = time.perf_counter()
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=settings["max_tokens"],
                                 num_beams=settings["beams"])
        infer_time = time.perf_counter() - t1
    m.INFERENCE_TIME.labels(mode).observe(infer_time)

    caption = processor.decode(out[0], skip_special_tokens=True).strip()
    words = len(caption.split())
    m.CAPTION_LENGTH.labels(mode).observe(words)
    m.CAPTION_WORDS.labels(mode).inc(words)
    m.IMAGES_PROCESSED.labels(mode, "success").inc()
    m.LAST_SUCCESS.set_to_current_time()
    return img, caption, infer_time


ERROR_MESSAGES = {
    "bad_image": "not a valid image file",
    "too_large": "image resolution is too large",
    "out_of_memory": "ran out of memory",
    "inference": "model failed on this image",
    "other": "unexpected error",
}


def record_error(mode, err):
    kind = classify_error(err)
    m.IMAGES_PROCESSED.labels(mode, "error").inc()
    m.ERRORS.labels(mode, kind).inc()
    print(f"[{mode}] {kind}: {err!r}")
    return ERROR_MESSAGES[kind]


def run_single(file, client, settings):
    mode = "single"
    m.REQUESTS.labels(mode, client["ip"], client["session"], client["browser"]).inc()
    m.APP_STATE.state(mode)
    try:
        with m.ACTIVE_REQUESTS.labels(mode).track_inprogress(), m.REQUEST_LATENCY.labels(mode).time():
            img, caption, secs = caption_bytes(file.getvalue(), mode, settings)
        st.session_state.single_result = {"name": file.name, "img": img, "caption": caption, "secs": secs}
    except Exception as err:
        msg = record_error(mode, err)
        st.session_state.single_result = {"name": file.name, "error": msg}
    finally:
        m.APP_STATE.state("idle")


def read_zip_entries(zf):
    """Return the image entries we will caption, counting everything we skip."""
    entries = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename)
        if info.filename.startswith("__MACOSX") or base.startswith("."):
            m.ZIP_FILES_SKIPPED.labels("hidden_file").inc()
        elif base.split(".")[-1].lower() not in IMAGE_TYPES:
            m.ZIP_FILES_SKIPPED.labels("not_image").inc()
        elif info.file_size > MAX_IMAGE_BYTES:
            m.ZIP_FILES_SKIPPED.labels("too_large").inc()
        else:
            entries.append(info)
    if len(entries) > MAX_ZIP_IMAGES:
        m.ZIP_FILES_SKIPPED.labels("over_limit").inc(len(entries) - MAX_ZIP_IMAGES)
        st.warning(f"ZIP has {len(entries)} images, only the first {MAX_ZIP_IMAGES} will be captioned.")
        entries = entries[:MAX_ZIP_IMAGES]
    return entries


def run_bulk(file, client, settings):
    mode = "bulk"
    try:
        zf = zipfile.ZipFile(io.BytesIO(file.getvalue()))
    except zipfile.BadZipFile:
        m.ERRORS.labels(mode, "bad_zip").inc()
        st.error("That file is not a valid ZIP archive.")
        return

    if sum(i.file_size for i in zf.infolist()) > MAX_ZIP_UNCOMPRESSED:
        m.ERRORS.labels(mode, "bad_zip").inc()
        st.error("ZIP is too large when extracted (limit 500 MB).")
        return

    entries = read_zip_entries(zf)
    if not entries:
        st.warning("No images (jpg, jpeg, png, bmp, webp) found inside the ZIP.")
        return

    m.REQUESTS.labels(mode, client["ip"], client["session"], client["browser"]).inc()
    m.ZIP_UPLOADS.inc()
    m.ZIP_IMAGES.observe(len(entries))
    m.LAST_ZIP_SIZE.set(len(entries))
    m.APP_STATE.state(mode)

    results, gallery = [], []
    progress = st.progress(0.0, text="Starting...")
    try:
        with m.ACTIVE_REQUESTS.labels(mode).track_inprogress(), \
                m.REQUEST_LATENCY.labels(mode).time(), m.BULK_JOB_TIME.time():
            for i, info in enumerate(entries):
                m.BULK_QUEUE.set(len(entries) - i)
                name = os.path.basename(info.filename)
                try:
                    img, caption, secs = caption_bytes(zf.read(info), mode, settings)
                    results.append({"file": name, "caption": caption, "inference_s": round(secs, 3), "status": "ok"})
                    if len(gallery) < 12:
                        gallery.append((img, name, caption))
                except Exception as err:
                    msg = record_error(mode, err)
                    results.append({"file": name, "caption": "", "inference_s": None, "status": f"error: {msg}"})
                progress.progress((i + 1) / len(entries), text=f"{i + 1}/{len(entries)} done - {name}")
    finally:
        m.BULK_QUEUE.set(0)
        m.APP_STATE.state("idle")

    st.session_state.bulk_result = {"name": file.name, "rows": results, "gallery": gallery}


def show_single_result():
    res = st.session_state.get("single_result")
    if not res:
        return
    if "error" in res:
        st.error(f"Could not caption {res['name']}: {res['error']}")
        return
    col1, col2 = st.columns([1, 1])
    col1.image(res["img"], caption=res["name"])
    col2.subheader("Caption")
    col2.success(res["caption"])
    col2.metric("Inference time", f"{res['secs']:.2f} s")


def show_bulk_result():
    res = st.session_state.get("bulk_result")
    if not res:
        return
    df = pd.DataFrame(res["rows"])
    ok = (df["status"] == "ok").sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Images captioned", int(ok))
    c2.metric("Failed", int(len(df) - ok))
    c3.metric("Avg inference", f"{df['inference_s'].mean():.2f} s" if ok else "-")

    st.dataframe(df, hide_index=True)
    st.download_button("Download captions (CSV)", df.to_csv(index=False).encode(),
                       file_name=res["name"].rsplit(".", 1)[0] + "_captions.csv", mime="text/csv")

    if res["gallery"]:
        st.subheader("Preview")
        cols = st.columns(4)
        for i, (img, name, caption) in enumerate(res["gallery"]):
            cols[i % 4].image(img, caption=f"{name}: {caption}")


def main():
    init_metrics()
    client = get_client()
    load_model()

    with st.sidebar:
        st.header("Settings")
        beams = st.slider("Beam search width", 1, 5, 3, help="More beams = better captions but slower on CPU")
        max_tokens = st.slider("Max caption length (tokens)", 10, 50, 30)
        st.divider()
        st.caption("Client info (sent as metric labels)")
        st.code(f"session : {client['session']}\nip      : {client['ip']}\nbrowser : {client['browser']}")
        st.caption(f"Metrics: http://localhost:{m.METRICS_PORT}/metrics")
    settings = {"beams": beams, "max_tokens": max_tokens}

    st.title("🖼️ CPU Image Captioning")
    st.write(f"Model: `{MODEL_NAME}` running on CPU with {torch.get_num_threads()} threads.")

    single_tab, bulk_tab = st.tabs(["Single image", "Bulk (ZIP)"])

    with single_tab:
        file = st.file_uploader("Upload an image", type=IMAGE_TYPES, key="single_file")
        if st.button("Generate caption", type="primary", disabled=file is None):
            with st.spinner("Captioning..."):
                run_single(file, client, settings)
        show_single_result()

    with bulk_tab:
        st.write(f"Upload a ZIP of images (max {MAX_ZIP_IMAGES} images, {MAX_IMAGE_BYTES // 2**20} MB each). "
                 "Non-image files are skipped.")
        zfile = st.file_uploader("Upload a ZIP file", type=["zip"], key="bulk_file")
        if st.button("Caption all images", type="primary", disabled=zfile is None):
            run_bulk(zfile, client, settings)
        show_bulk_result()


main()
