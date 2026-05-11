# Smart-Eye — Graduation Project: Complete Documentation

Branch: `dev`  ·  Last updated: 2026-05-12

Overview
--------

Smart-Eye is an intelligent safety surveillance desktop application that captures video from multiple cameras, runs object detection and face recognition, raises alerts based on rules, records detection logs, and provides analytics (heatmaps, reports) via a PySide6 GUI. This document is written to help you (and your professor) understand the entire system: how to run it, how models are used, how data flows, where to find code, and how to answer common viva questions.

Table of contents
- Elevator pitch
- Quick setup (Windows & Linux)
- How to run and configure
- High-level architecture and data flow
- Database schema and stored data (key tables)
- Models: what is shipped, how inference runs, and how to inspect/replace models
- Face recognition pipeline and thresholds
- Training & reproducibility (how to retrain and export to ONNX)
- Code walkthrough (module-by-module summary)
- Performance, optimization and deployment notes
- Security, privacy & ethics
- Troubleshooting & common issues
- Viva Q&A — likely questions and suggested short answers
- Appendix: useful commands and inspection snippets

Elevator pitch
--------------

- Problem solved: centralized, offline-capable surveillance for small installations (retail, labs, small campuses). It supports live monitoring, rule-based alerts, face recognition against a local known-faces store, and basic analytics.
- Strengths: simple local operation (single SQLite DB), extensible model plugin architecture, modular frontend/backed separation for maintainability.

Quick setup
-----------

Prerequisites
- Python 3.10+ (3.11 recommended)
- Windows recommended for GPU DirectML (`onnxruntime-directml`); Linux with CUDA also supported via appropriate ONNX Runtime build.

Install and run (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

If you don't have GPU support, replace `onnxruntime-directml` with `onnxruntime` (CPU) in your environment.

Configuration and runtime flags
- Environment: set `SMARTEYE_DEBUG=1` for debug logs.
- Key DB-config flags (stored in `app_settings` table):
  - `auto_start_cameras` — start enabled cameras on launch.
  - `face_similarity_threshold` — default 0.45 (used for face match decisions).
  - `limit_resources`, `max_cpu_cores`, `max_ram_mb` — resource-limiting options used by `utils/resource_limiter.py`.

How to run headless tests / sanity checks
- Validate ONNX model:

```python
import onnx
onnx.checker.check_model('data/models/Obj-Detection.onnx')

import onnxruntime as ort
sess = ort.InferenceSession('data/models/Obj-Detection.onnx')
print([i.name for i in sess.get_inputs()], [o.name for o in sess.get_outputs()])
```

High-level architecture & data flow
----------------------------------

1. Cameras are managed by `camera/` code: each camera runs in a thread/process (capture → frame queue).
2. Frames go to the pipeline: `pipeline/detector_manager` picks an appropriate model plugin and performs inference.
3. `pipeline/analyzer` takes raw detection outputs, applies rules (from `rules` and `rule_conditions` tables), generates alarms and stores logs in `detection_logs`.
4. Alerts trigger actions (email, webhook) via `backend/notifications` and are visible in the GUI (frontend pages / alert popup).
5. Analytics modules (`backend/analytics`) aggregate historic detection logs and create heatmaps / PDF reports.

Database schema and stored data (key tables)
-------------------------------------------

The repository creates a local SQLite DB (`data/smarteye.db`). Key tables (see `backend/database/schema.sql`):

- `cameras`: camera definitions (id, name, source URL/RTSP, resolution, fps_limit, face_recognition flag).
- `zones`: per-camera polygon/rectangular regions to focus detection and trigger zone-specific rules.
- `model_plugins` / `plugin_classes`: a plugin abstraction that lets you register detection models and classes (name, weight path, default confidence).
- `camera_plugins` / `camera_plugin_classes`: mapping of camera → enabled model plugins and which classes to watch.
- `rules` / `rule_conditions` / `alarm_actions`: user-defined rules applied to detections (logic, action, priority).
- `known_faces`: locally stored face records (embedding BLOB, metadata, image path) used for face recognition.
- `detection_logs`: chronological evidence of detections (timestamp, camera_id, zone_id, identity if matched, face_confidence, detections JSON, snapshot path).
- `clips`: stored video clips for events.
- `accounts`: UI accounts and authentication data.
- `app_settings`: application-level settings (many defaults are inserted on DB initialization, e.g. `face_similarity_threshold`, `insightface_model_name` etc.).

You can inspect `backend/database/schema.sql` at any time to see default values and indices. Important defaults:
- `face_similarity_threshold` default: 0.45
- `snapshot_on_alarm` default: enabled
- `insightface_model_name` default: `buffalo_l` (stored in `app_settings`)

Models — what is shipped and how to inspect
-----------------------------------------

Shipped artifacts:
- `data/models/Obj-Detection.onnx` — pre-exported ONNX object detection model used by the default pipeline.
- `insightface` models are not stored directly in the repo but the app references `insightface` via the `insightface_model_name` setting and caches downloads locally per `insightface_model_dir`.

How inference is executed (summary):

1. `models/model_loader.py` selects the plugin/provider (ONNX, InsightFace, etc.).
2. For ONNX-based models, `models/onnx_object_model.py` sets up an `onnxruntime.InferenceSession` with desired `SessionOptions`, converts frames to the model's input size/format, and runs `session.run(...)`.
3. Post-processing (NMS, thresholding, class mapping) is performed in the model wrapper before the results are passed to `pipeline/analyzer`.

How to inspect an ONNX file quickly

- Use Netron (GUI) for a visual inspection: https://netron.app
- Or quick CLI introspection:

```python
import onnx
m = onnx.load('data/models/Obj-Detection.onnx')
print([i.name + ':' + str(i.type) for i in m.graph.input])
print([o.name + ':' + str(o.type) for o in m.graph.output])
```

If you are asked in the viva "what architecture is the ONNX model?", answer honestly: "The repo ships an ONNX artifact; you can inspect the nodes with Netron or the Python snippet above to determine whether it is YOLO-like or another architecture. The code treats it as a generic detector with fixed preprocessing/postprocessing wrappers."

Face recognition pipeline (explainable steps)
-------------------------------------------

1. Detection: either the object detector detects a person/face class, or a dedicated face detector runs (depending on config).
2. Crop & align: a face patch is cropped and, if available, aligned to canonical eye/nose positions.
3. Embedding: the face patch is fed into an embedding model (via `insightface`) to produce a fixed-size vector.
4. Matching: the vector is compared (cosine distance or L2) against embeddings in `known_faces`. If the distance is below `face_similarity_threshold` (DB default 0.45), a match is considered.
5. Decision: the pipeline records `identity`, `face_confidence` and triggers rules if configured.

Notes about thresholds
- Default `face_similarity_threshold` is 0.45 (DB default), which is a conservative starting point. You should calibrate this with a labeled test set and pick the threshold that balances false accepts vs false rejects for your deployment.

Training & reproducibility
--------------------------

This repository is focused on inference and integration. If asked how to reproduce training, use this recommended procedure:

Object detection training (example):
1. Prepare dataset (COCO, Pascal VOC, or custom). Annotate bounding boxes for needed classes.
2. Choose a framework (PyTorch + Ultralytics YOLOv5/YOLOX, Detectron2 for Faster R-CNN, etc.).
3. Train with standard augmentation (flip, color, mosaic/letterbox when using YOLO families), suitable optimizer (SGD or AdamW) and LR schedule. Save checkpoints and export final model.
4. Export to ONNX with appropriate opset (>=11 recommended) and perform inference consistency checks.

Face embedding training (example):
1. Use ArcFace / a similar margin-based loss with a large face dataset (MS1M, VGGFace2) or fine-tune a pre-trained backbone.
2. Export the embedding network for inference; optionally keep a smaller backbone for on-device speed.

Evaluation metrics to report (if asked):
- Object detection: mAP@0.5 and mAP@0.5:0.95, per-class precision/recall curves.
- Face recognition: verification accuracy, TAR@FAR (True Accept Rate at fixed False Accept Rate), ROC curve.

Code walkthrough — important modules and responsibilities
------------------------------------------------------

I. Top-level files
- `main.py` — app bootstrap, logging, DB initialization, resource limiting and starting `QApplication` + `MainWindow`.
- `requirements.txt` — runtime dependencies to install.

II. Config
- `config/settings.py` — sets up `BASE_DIR`, `DATA_DIR`, logging handlers (rotating files), thread exception hooks, OpenCV thread/CL settings, DB initialization call (`db.init(...)`), default data subdirectories, and resource limiter invocation (reads DB flags: `limit_resources`, `max_cpu_cores`/`max_threads`, `max_ram_mb`).

III. Backend
- `backend/camera/*` — camera threads, capture and playback threads.
- `backend/pipeline/detector_manager.py` — model plugin manager; creates model instances per camera or shared pool and schedules inference.
- `backend/pipeline/analyzer.py` — transforms detections to high-level events, logs them to `detection_logs`, and triggers alarms.
- `backend/analytics/*` — heatmap and report generation using detection logs.
- `backend/repository/db.py` — thin wrapper over SQLite to manage DB connections, migrations, and convenience helpers.

IV. Models
- `models/model_loader.py` — picks ONNX or InsightFace provider and sets session options.
- `models/onnx_object_model.py` — wraps ONNX Runtime calls, does preprocessing and postprocessing (NMS, class mapping).
- `models/face_model.py` — wrapper around InsightFace embeddings and alignment utilities.

V. Frontend
- `frontend/main_window.py` — primary GUI container. Builds pages, sidebar, auth overlay, manages session and page lifecycle.
- `frontend/pages/*` — dashboard, camera manager, playback, settings and others. Each page has `on_activated` hooks for lifecycle.
- `frontend/widgets/*` — reusable widgets (alerts, login cards, sidebars, overlays, etc.).

Where to look for exact behavior
- For exact preprocessing (resize, normalization) see `models/onnx_object_model.py`.
- For face matching logic and thresholds, see DB defaults in `backend/database/schema.sql` and `models/face_model.py`.

Performance and optimization notes
---------------------------------

- ONNX Runtime options: prefer using a GPU-enabled runtime (`onnxruntime-directml` on Windows or `onnxruntime-gpu` with CUDA on Linux) for real-time throughput.
- Control CPU/thread usage via `cv2.setNumThreads(...)` and the `resource_limiter` module (the app already sets `cv2.setNumThreads(1)` on startup when possible).
- Use batched inference if you need to process multiple frames together (trade-off latency vs throughput).
- For edge deployment, consider quantizing models (INT8) or using FP16 if supported by provider.

Security, privacy & ethics
-------------------------

- Personal data (faces) is stored locally in `known_faces`. If you will deploy this where privacy laws apply, ensure informed consent, data minimization, retention policies (DB has `log_retention_days` default 90), and encryption-at-rest for sensitive fields.
- Consider encrypting `data/` volumes and credentials (SMTP password, webhooks) before production usage.
- Provide an audit mechanism: `access_log` + `detection_logs` track accesses and decisions.

Packaging & deployment
----------------------

- For a Windows deliverable use `PyInstaller` to create a single exe and bundle the `data/` folder next to it.
- Ensure `onnxruntime-directml` and GPU drivers are installed on the target machine. If not, ship with the CPU ONNX runtime.

Troubleshooting & common issues
-------------------------------

- If GUI doesn't start: check logs in `data/logs/smarteye.latest.log` and run `python main.py` from a terminal to view traceback.
- If models fail to load: verify `data/models` contains file paths referenced by `model_plugins` and that file permissions are correct.
- If face matching is too permissive/strict: tune `face_similarity_threshold` in settings or by adding a small evaluation set.

Viva Q&A — likely professor questions and suggested concise answers
----------------------------------------------------------------

Q: What model(s) does the project use?
A: The repo ships a pre-exported ONNX object detector `data/models/Obj-Detection.onnx`. For faces we use `insightface` for embeddings (model name configurable via `app_settings`). The code is model-agnostic via a plugin interface in `model_plugins` / `models/*` wrappers.

Q: How were the models trained?
A: Training code is not in the repo. The ONNX artifacts were produced elsewhere. To reproduce training I would train a detector (YOLOX/Detectron/Ultralytics pipeline) on a labeled dataset, then export to ONNX using framework exporters — verifying opset and output shapes.

Q: How do you evaluate detection quality?
A: Using standard object-detection metrics: mAP@0.5 and mAP@0.5:0.95, precision/recall per class and confusion analysis for false positives/negatives.

Q: How does face recognition work and how do you pick thresholds?
A: We compute embeddings (via InsightFace), compare with stored embeddings in `known_faces` using cosine distance/L2. The `face_similarity_threshold` (default 0.45) is tuned on a validation set to balance false accept/reject rates.

Q: How do you handle multiple cameras and resource constraints?
A: `camera_manager` spawns per-camera capture threads; `resource_limiter` can reduce CPU cores, threads and RAM usage; ONNX Runtime GPU usage is limited by the hardware and session settings.

Q: How are rules defined and applied?
A: Rules are stored in `rules` and `rule_conditions` tables. `pipeline/analyzer` evaluates rule logic (AND/OR) against detection attributes and triggers `alarm_actions` when conditions are met.

Q: How do you prevent data leaks / protect privacy?
A: Keep the DB and `data/` directory on encrypted disks; limit retention via `log_retention_days`; require authentication (`accounts`) to access logs; consider encrypting sensitive DB fields.

Q: Is the system real-time? What latency can you achieve?
A: Latency depends on model complexity and hardware. With a lightweight detector and GPU-accelerated ONNX Runtime, sub-100ms per frame on modern GPUs is possible; on CPU-only systems expect 200–500ms or higher. Benchmarking should be done on target hardware.

Q: What would you improve given more time?
A: add automated training scripts, continuous integration for model export tests, adaptive threshold tuning, privacy-preserving methods (on-device encryption), and deployable installers for Windows/Mac.

Q: How do you test the pipeline end-to-end?
A: Unit tests for model wrappers (mock inputs/outputs), integration tests for camera → pipeline → DB writes (use recorded video streams), and manual QA on live cameras.

Appendix — quick commands and model inspection
------------------------------------------------

Validate ONNX:

```python
import onnx
onnx.checker.check_model('data/models/Obj-Detection.onnx')
```

Inspect ONNX inputs/outputs with ONNX Runtime:

```python
import onnxruntime as ort
sess = ort.InferenceSession('data/models/Obj-Detection.onnx')
print('inputs:', [i.name + str(i.shape) for i in sess.get_inputs()])
print('outputs:', [o.name for o in sess.get_outputs()])
```

Open with Netron for visual graph inspection: https://netron.app

Final notes and next steps
-------------------------

I expanded this documentation to include the database schema, explicit runtime keys, an explanation of how inference and face recognition work, and a curated list of viva Q&A with suggested concise answers. If you want, I can:

- produce a short 4-slide deck for your defense with screen captures and talking points;
- create a one-page cheat-sheet PDF with the Q&A and important file references for quick review;
- extract a line-by-line summary for 3 files you expect to be questioned on (e.g., `main.py`, `backend/pipeline/analyzer.py`, `models/onnx_object_model.py`).

File updated: [docs/GRADUATION_PROJECT.md](docs/GRADUATION_PROJECT.md)

Detailed training examples and backend deep-dive
------------------------------------------------

Worked example — train YOLOv8 (Ultralytics) and export to ONNX
------------------------------------------------------------

This worked example shows a reproducible path from dataset → train → export ONNX → register plugin in Smart-Eye.

1) Prepare environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install ultralytics onnx onnxruntime onnxruntime-tools
```

2) Prepare dataset

- Option A — YOLO format (simple): images in `images/train`, `images/val`; labels in `labels/train`, `labels/val` where each label file is `class x_center y_center width height` (all normalized 0..1).
- Option B — COCO format: `train/annotations/instances_train.json` + images. COCO is recommended for larger workflows and mAP evaluation.

Create a `data.yaml` for Ultralytics (YOLOv8) like:

```yaml
train: /abs/path/to/images/train
val: /abs/path/to/images/val
nc: 3
names: ['person','bag','phone']
```

3) Train with Ultralytics YOLOv8 (example)

```powershell
# small model for fast iteration
yolo task=detect mode=train model=yolov8n.pt data=data.yaml epochs=100 imgsz=640 batch=16 device=0
```

Key points:
- Use `yolov8n.pt`/`yolov8s.pt` for quick experiments; move to `yolov8m`/`yolov8l` for accuracy.
- Monitor `runs/detect/train` folder for `best.pt` and `last.pt` checkpoints.

4) Export to ONNX (Ultralytics helper)

Ultralytics includes an `export` helper that handles many model quirks:

```powershell
# export best checkpoint to ONNX
yolo export model=runs/detect/train/weights/best.pt format=onnx opset=12 dynamic=True
```

This produces `best.onnx` (or `best.onnx` inside an `export` folder). The `dynamic=True` flag allows variable batch size/dimensions — useful for desktop runtime.

5) Validate ONNX & quick inference check

```python
import onnx, onnxruntime as ort, numpy as np
onnx.checker.check_model('best.onnx')
sess = ort.InferenceSession('best.onnx')
inp = sess.get_inputs()[0]
print('input:', inp.name, inp.shape)
dummy = np.zeros((1,3,640,640), dtype=np.float32)
outs = sess.run(None, {inp.name: dummy})
print('outs shapes:', [o.shape for o in outs])
```

6) Convert model into Smart-Eye plugin

- Copy the exported ONNX to the project `data/models/obj-detect-yolov8.onnx` (or other stable location).
- Register plugin via the app UI (Models page) or programmatically:

```python
from backend.repository import db
db.init('data/smarteye.db')  # only if running from outside app; otherwise the app already initialized DB
db.add_plugin('YOLOv8 Small', 'onnx', 'data/models/obj-detect-yolov8.onnx', confidence=0.4)
```

Notes on preprocessing
- `onnx_object_model.py` uses `cv2.dnn.blobFromImage(..., scalefactor=1/255.0, swapRB=True, crop=False)` and expects the ONNX input to be `[N,3,H,W]` float32 normalized to 0..1. Ensure your exported model receives data in this format.

Manual PyTorch → ONNX export (if needed)

```python
import torch
from ultralytics import YOLO

model = YOLO('runs/detect/train/weights/best.pt')
model.export(format='onnx', opset=12, dynamic=True, imgsz=640)

# or raw torch export (when using plain torch models)
# dummy = torch.randn(1,3,640,640)
# torch.onnx.export(model, dummy, 'model.onnx', opset_version=12, input_names=['images'], output_names=['output'], dynamic_axes={'images': {0: 'batch'}})
```

Face model — InsightFace (how to prepare)
-----------------------------------------

- Smart-Eye expects InsightFace-style ONNX models under an InsightFace root (see `backend/models/face_model.py` for the search logic). The `insightface` package can prepare and cache models (default `insightface_model_name` = `buffalo_l`).
- If you need to train or fine-tune embeddings: use a face recognition pipeline (ArcFace margin loss) trained on VGGFace2 / MS1M or a domain-specific dataset. After training, export the recognition model to ONNX (example export snippet below).

Example ONNX export for a face embedding network (conceptual)

```python
# after training your PyTorch model (embedding network)
model.eval()
dummy = torch.randn(1,3,112,112)  # typical face crop size
torch.onnx.export(model, dummy, 'face_recog.onnx', opset_version=11, input_names=['input'], output_names=['embedding'], dynamic_axes={'input': {0: 'batch'}})
```

Place the ONNX files under a folder structure like `<insightface_root>/models/<model_name>/*.onnx` so `FaceModel` can discover and load detection+recognition submodels.

Backend architecture — deep dive (call flow & concurrency)
--------------------------------------------------------

This section describes how runtime components interact and where to look in the code when answering deeper professor questions.

1) Camera management
- `backend/camera/camera_manager.py` — responsible for starting/stopping camera threads and tracking active threads. Use `start_all_enabled()` to auto-start configured cameras.
- `backend/camera/camera_thread.py` — each thread captures frames, enforces `fps_limit`, resizes/preprocesses if needed, and calls/dispatches frames to the pipeline service. (Open `camera_thread.py` to inspect capture loop and how frames are handed off.)

2) Inference orchestration
- `backend/pipeline/detector_manager.py` — central component that:
  - loads face model asynchronously via `model_loader.load_face_model_async()`;
  - loads ONNX plugin models via `model_loader.load_plugin()`;
  - scales frames (to `_MAX_INFER_DIM` or aggressive mode) before inference for throughput/latency trade-offs;
  - uses a `ThreadPoolExecutor` to run face detection and multiple plugin inferences in parallel (`_submit_inference_futures()`);
  - collects futures (`_collect_futures()`), merges results, smooths bounding boxes and tracks objects/faces per-camera.

3) Model loading and provider selection
- `backend/models/model_loader.py` and `backend/models/onnx_object_model.py`:
  - probe available ONNX ExecutionProviders (`ort.get_available_providers()`), choose GPU provider (DML/CUDA) if allowed, otherwise fall back to CPU;
  - warm up the ONNX session with a dummy input; if warmup fails, persist a CPU fallback to avoid repeated failures;
  - inspect ONNX metadata to populate `plugin_classes` automatically when available.

4) Result merging and rules
- `backend/pipeline/analyzer.py` — converts raw detections into a normalized `state` structure with `all_faces`, `object_bboxes`, `detections` dict and identity/gender fields.
- `backend/pipeline/rule_engine.py` — compiles `rule_conditions` into evaluator functions and applies rule logic (AND/OR), returning triggered rules.

5) Actions, logging and escalation
- `backend/pipeline/escalation_manager.py` (manages escalation state over time).
- `backend/pipeline/alarm_handler.py` — dispatches actions (email/webhook/sound), writes detection logs via a worker queue and saves snapshots when required. The alarm handler offloads I/O work to a worker thread to avoid blocking capture/inference.

6) Persistence & DB write model
- `backend/database/db.py` implements a dedicated DB writer thread pattern:
  - writes are queued to `_write_queue` and executed by `_writer_loop()` in a single writer thread to avoid concurrent SQLite writes from many threads;
  - helper `_write_execute()` submits SQL/operations to the writer thread and waits for completion — this keeps capture and inference threads responsive while guarantees DB integrity.

7) Service bridge
- `backend/services/pipeline_service.py` — glue between the detector results and backend services: it hands off triggered rules to the `escalation_manager`, runs `AlarmHandler.handle_alarms()`, triggers inbox capture and heatmap generation if requested, and returns an augmented result that the UI consumes.

8) Concurrency summary
- Capture threads push frames continuously.
- Per-camera detection work is handled by `DetectorManager` using a `ThreadPoolExecutor` sized around `max_cpu_cores` / `max_threads` config.
- Long-running I/O (DB writes, alarm actions, heatmap writes) are queued to dedicated worker threads (DB writer, `AlarmHandler` worker) to avoid blocking the hot path.

How to add a new model plugin (summary)
--------------------------------------

1. Train & export to ONNX (`.onnx`) following the examples above.
2. Copy ONNX file into a stable location (e.g., `data/models/new-detector.onnx`).
3. Register the plugin:

```python
from backend.repository import db
db.init('data/smarteye.db')
plugin_id = db.add_plugin('My Detector', 'onnx', 'data/models/new-detector.onnx', confidence=0.5)
# model_loader will sync class names from ONNX metadata to plugin_classes when loading.
```

4. Assign the plugin to cameras via the UI (Models page) or the DB (`assign_plugin_to_camera(camera_id, plugin_id)`).

Testing and validation
----------------------

- Run offline tests using saved frames or recorded video (use `backend/camera/playback_thread.py`) to exercise the pipeline without live cameras.
- Create small labeled datasets for threshold tuning: compute embedding similarity distributions to pick `face_similarity_threshold`, tune per-camera thresholds if needed.
- Measure latency: log `face_time_ms` / `object_time_ms` values aggregated in `analyzer.merge_results()` to know per-model runtime.

Wrap-up
-------

I added the step-by-step training example (Ultralytics YOLOv8) with ONNX export, face-model export guidance, registration steps for Smart-Eye, and a backend architecture deep-dive to help prepare for oral questions. If you want, I can now:

- add a ready-to-print one-page cheat-sheet with the most likely viva questions and one-line answers; or
- generate a 4-slide deck summarizing architecture, models, and demo steps; or
- produce three one-page file summaries for `main.py`, `backend/pipeline/detector_manager.py`, and `backend/models/onnx_object_model.py` for rapid review.


