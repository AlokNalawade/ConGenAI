# ConGenAI — Offline / Local-Only Operations Runbook

**Purpose:** rebuild, configure, operate, troubleshoot, and migrate ConGenAI without depending on ChatGPT/Claude or another coding assistant.

**Repository:** `AlokNalawade/ConGenAI`
**Primary development branch for the current Mac/H3 work:** `feature/minimal-h3-mac`
**Last updated:** 2026-10-01

---

## 1. What this document is for

This is the emergency/self-service manual for ConGenAI. Keep a local copy of this file and a copy of the repository.

The goal is that a future operator can:

1. install the operating-system dependencies;
2. configure PostgreSQL, Redis, Python, and FFmpeg;
3. configure local AI models;
4. configure local MiniMax H3 on Apple Silicon;
5. switch video providers without changing application code;
6. run ConGenAI in local-only mode;
7. optionally enable cloud providers later;
8. diagnose failures without an AI assistant;
9. move the system from a MacBook Air to an RTX 5090 workstation.

---

## 2. Operating modes

### Mode A — Fully local/private

Use this when there is no cloud AI access or when privacy is the priority.

```text
ConGenAI
  ├─ local LLM
  ├─ local embeddings/vector store
  ├─ local image generation
  ├─ local H3 video generation
  ├─ local TTS
  ├─ FFmpeg
  ├─ PostgreSQL
  └─ Redis
```

Set:

```env
ALLOW_EXTERNAL_GENERATION=false
VIDEO_MODEL=minimax-h3
```

### Mode B — Hybrid

Use local models for development/drafts and a cloud video provider for selected production renders.

```env
ALLOW_EXTERNAL_GENERATION=true
VIDEO_MODEL=higgsfield-h3
```

**Never commit API credentials.** Put secrets only in the local `.env` file or another secret store.

---

## 3. Hardware profiles

### MacBook Air 16 GB Apple Silicon

Use this primarily for development, pipeline testing, lightweight local inference, and low-memory H3 experiments.

Known working H3 diagnostics from the development setup:

```bash
.venv/bin/h3stream doctor --model-dir models
```

The expected profile is Apple Silicon with MLX available and BF16 matrix multiplication working. On a 16 GB machine, close other applications before generation.

Recommended first H3 test:

```bash
.venv/bin/h3stream plan \
  --width 640 \
  --height 384 \
  --seconds 5 \
  --steps 16
```

Start with audio disabled for the first successful generation. Audio adds another decode stage.

### RTX 5090 workstation

Use this as the intended high-performance local production machine. Reconfigure model/runtime paths and install the NVIDIA/CUDA-compatible versions of the chosen inference runtimes. Do not assume that Mac/MLX packages are the correct GPU stack.

Before migrating production, benchmark:

- generation time;
- VRAM peak;
- resolution;
- steps;
- video quality;
- audio quality;
- cost per finished minute;
- end-to-end pipeline time.

Do not delete the working Mac configuration until the GPU machine passes the full smoke test.

---

## 4. Required system software

Install and verify:

- Git
- Python 3.x compatible with the project dependencies
- PostgreSQL
- Redis
- FFmpeg
- Homebrew on Apple Silicon macOS
- the appropriate local model runtime (MLX/H3 on Mac; NVIDIA/CUDA runtime on the RTX workstation)

### Apple Silicon Homebrew

If `brew` is missing:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After installation, follow the Homebrew command printed by the installer to add `/opt/homebrew/bin` to your shell PATH.

Verify:

```bash
brew --version
which brew
```

Verify FFmpeg:

```bash
ffmpeg -version
which ffmpeg
```

The current Mac setup has used `/opt/homebrew/bin/ffmpeg`.

---

## 5. Clone and create the Python environment

```bash
git clone https://github.com/AlokNalawade/ConGenAI.git
cd ConGenAI
git checkout feature/minimal-h3-mac
```

Create/activate the API virtual environment according to the repository's current layout. If the project uses `.venv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install API dependencies:

```bash
pip install --upgrade pip
pip install -r apps/api/requirements.txt
```

The current requirements include FastAPI, Uvicorn, SQLAlchemy, async PostgreSQL support, Redis/ARQ, OpenAI-compatible client support, Edge TTS, FFmpeg bindings, Higgsfield client, and HTTPX.

Verify:

```bash
python --version
pip check
```

---

## 6. Environment configuration — master reference

Create the local environment file expected by the API (`.env`). Never commit the real file if it contains passwords or API keys.

### Core application

```env
PROJECT_NAME="AI Content Factory"
API_V1_STR=/api/v1
```

### Database

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=CHANGE_ME
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=congen
```

### Redis

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### External generation gate

```env
ALLOW_EXTERNAL_GENERATION=false
```

Keep this `false` for local-only operation.

### Higgsfield

Only needed when using Higgsfield:

```env
ALLOW_EXTERNAL_GENERATION=true
HIGGSFIELD_API_KEY_ID=YOUR_KEY_ID
HIGGSFIELD_API_KEY_SECRET=YOUR_KEY_SECRET
HIGGSFIELD_VIDEO_MODEL=minimax/h3/text-to-video
VIDEO_MODEL=higgsfield-h3
```

Do not commit real credentials.

### Local H3

```env
VIDEO_MODEL=minimax-h3
H3_COMMAND=/absolute/path/to/minimax-h3-stream-mac/.venv/bin/h3stream
H3_MODEL_DIR=/absolute/path/to/minimax-h3-stream-mac/models
H3_MEMORY_LIMIT_GIB=12.5
```

Use absolute paths on the Mac. Replace the username/path with the actual installation location.

---

## 7. Video provider selection

The intended configuration switch is:

### Local MiniMax H3

```env
ALLOW_EXTERNAL_GENERATION=false
VIDEO_MODEL=minimax-h3
```

### Higgsfield MiniMax H3

```env
ALLOW_EXTERNAL_GENERATION=true
VIDEO_MODEL=higgsfield-h3
```

The application should treat these as provider choices, not as separate content pipelines.

Recommended architecture:

```text
Content/scene planner
        |
        v
   Video model router
     /          \
local H3     Higgsfield H3
     \          /
      v        v
       video asset
           |
      local FFmpeg
           |
     QA / publish
```

---

## 8. MiniMax H3 on the Mac

### Verify the installation

```bash
.venv/bin/h3stream doctor --model-dir models
```

Expected checks include:

- Apple Silicon detected;
- MLX importable;
- BF16 matrix multiplication working;
- sufficient disk space;
- FFmpeg available.

PyTorch/MPS is optional for the current MLX path.

### Verify model integrity

```bash
.venv/bin/h3stream verify \
  --model-dir models \
  --audio \
  --sha256
```

The current verified model set includes transformer, text encoder, video VAE, tokenizer, and audio VAE weights.

### First video

Use a small test first:

```bash
.venv/bin/h3stream plan \
  --width 640 \
  --height 384 \
  --seconds 5 \
  --steps 16
```

Then run the generation command provided by the installed `h3stream` CLI for that plan.

For a 16 GB Mac, avoid jumping directly to long/high-resolution generation. Increase one variable at a time.

### Mac troubleshooting

If generation is slow:

1. close browsers and other memory-heavy applications;
2. disable audio for the first test;
3. reduce width/height;
4. reduce duration;
5. reduce steps;
6. verify free disk space;
7. rerun `doctor`.

If `mlx` cannot import:

```bash
source .venv/bin/activate
python -c "import mlx; print('MLX OK')"
```

If FFmpeg is missing:

```bash
brew install ffmpeg
ffmpeg -version
```

---

## 9. PostgreSQL

Create the database/user expected by `.env`.

Verify the server:

```bash
pg_isready -h localhost -p 5432
```

Verify login:

```bash
psql -h localhost -U postgres -d congen
```

If migrations are present in the repository, run the project's Alembic migration command before starting the API. Do not manually alter production tables unless the migration system requires it.

---

## 10. Redis

Verify:

```bash
redis-cli ping
```

Expected:

```text
PONG
```

If Redis is not running, start it using the service manager used by the host OS/Homebrew.

---

## 11. FFmpeg

FFmpeg is a critical part of the local media pipeline.

Verify:

```bash
ffmpeg -version
ffprobe -version
```

ConGenAI uses Python FFmpeg bindings and local FFmpeg for media processing. Keep FFmpeg available even when the video model itself is cloud-hosted.

---

## 12. Running the API

From the API environment, use the repository's configured FastAPI entry point. A standard development invocation is:

```bash
uvicorn app.main:app --reload
```

Run it from the directory where the `app` Python package is importable (normally `apps/api`).

If import errors occur, check:

```bash
pwd
python -c "import sys; print(sys.path)"
python -c "import app; print(app.__file__)"
```

Do not blindly reinstall packages until the working directory/PYTHONPATH issue is ruled out.

---

## 13. Local-only AI strategy

The project should be configured so the orchestration layer does not require ChatGPT or Claude.

Recommended local stack:

```text
Research sources / local documents
          |
          v
    Research agent
          |
          v
       local LLM
          |
   strategy / scripts
          |
   scene generation
      /        \
 local image   local H3
      \        /
       narration
          |
       FFmpeg
          |
       final MP4
```

The exact local LLM/image runtime can change. Keep provider-specific settings isolated in configuration instead of embedding them throughout the agents.

**Important distinction:** “local AI only” does not necessarily mean “no Internet.” Fresh market/trend research requires Internet access to retrieve current public information. The inference model can still remain local.

If the Internet is unavailable, research is limited to already-downloaded documents, feeds, databases, or cached data.

---

## 14. Research/trend discovery

For autonomous market/content discovery, the intended future flow is:

```text
Public sources / feeds / APIs
          |
          v
   Research collector
          |
          v
   source normalization
          |
          v
      local LLM
          |
          v
 trend/opportunity ranking
          |
          v
 content strategy
```

Do not confuse research collection with the LLM itself. The LLM can be completely local while the collector uses public web sources.

When replacing an external research API with a local collector, document the source URL/API, authentication requirements, rate limits, parser, and cache location in the project.

---

## 15. Secrets and GitHub safety

Never commit:

- `.env` containing real secrets;
- API keys;
- passwords;
- private tokens;
- cookies/session tokens;
- cloud provider credentials.

Safe to commit:

- `.env.example` with placeholders;
- model names;
- non-secret paths when they are portable;
- setup instructions;
- scripts;
- tests;
- documentation.

Before pushing:

```bash
git status
git diff --cached
git diff
```

Search for accidental secrets before committing.

---

## 16. First-run smoke test

Do not start with the entire content factory. Validate components in this order:

### Test 1 — OS

```bash
git --version
python --version
ffmpeg -version
```

### Test 2 — PostgreSQL

```bash
pg_isready -h localhost -p 5432
```

### Test 3 — Redis

```bash
redis-cli ping
```

### Test 4 — Python dependencies

```bash
source .venv/bin/activate
pip check
```

### Test 5 — H3

```bash
.venv/bin/h3stream doctor --model-dir models
.venv/bin/h3stream verify --model-dir models --sha256
```

### Test 6 — API

Start Uvicorn and verify its health/root endpoint as defined by the current API.

### Test 7 — One generated image

Run a single image generation through the configured image backend.

### Test 8 — One 5-second video

Generate one H3 scene.

### Test 9 — Audio mux

Attach one narration track using FFmpeg.

### Test 10 — Complete pipeline

Only after the individual tests pass, run one complete content item.

---

## 17. Troubleshooting decision tree

### `brew: command not found`

Homebrew is not installed or is not on PATH. Install Homebrew or add `/opt/homebrew/bin` to PATH, then open a new terminal.

### `No module named ...`

Check that the correct virtual environment is active:

```bash
which python
which pip
```

Then:

```bash
pip install -r apps/api/requirements.txt
pip check
```

### H3 doctor fails

Run:

```bash
.venv/bin/h3stream doctor --model-dir models
```

Fix failures in this order:

1. platform/runtime;
2. MLX;
3. model path;
4. model integrity;
5. disk space;
6. FFmpeg;
7. memory pressure.

### H3 is out of memory

Reduce resolution, duration, or steps. Close other applications. Do not immediately increase swap and assume the workload is safe; sustained swapping can make generation impractically slow.

### Higgsfield fails

Check:

```env
ALLOW_EXTERNAL_GENERATION=true
HIGGSFIELD_API_KEY_ID=...
HIGGSFIELD_API_KEY_SECRET=...
VIDEO_MODEL=higgsfield-h3
```

Then verify that the API credentials are valid and that the selected model is available to the account. If cloud generation is unavailable, switch back to:

```env
ALLOW_EXTERNAL_GENERATION=false
VIDEO_MODEL=minimax-h3
```

### Video exists but has no narration

Check the audio file and run FFmpeg/ffprobe against both inputs. The video provider and narration provider are independent stages.

### API cannot connect to PostgreSQL

Check:

```bash
pg_isready -h localhost -p 5432
```

Then verify every `POSTGRES_*` value in `.env`.

### API cannot connect to Redis

Check:

```bash
redis-cli ping
```

Then verify `REDIS_HOST`, `REDIS_PORT`, and `REDIS_DB`.

---

## 18. Mac → RTX 5090 migration

Do not copy the entire Mac Python environment to the NVIDIA machine.

Instead:

1. clone the same Git commit/branch;
2. install the appropriate NVIDIA driver;
3. install the CUDA-compatible inference runtime required by the selected local models;
4. create a new virtual environment;
5. install project requirements;
6. install the GPU-specific model/runtime packages;
7. download/verify model weights;
8. update `.env` paths and provider settings;
9. run health checks;
10. benchmark one scene;
11. benchmark a complete content item;
12. only then switch production workloads.

Keep the Mac as a known-good fallback until the RTX machine is stable.

---

## 19. Model replacement procedure

When replacing any AI model:

1. identify the model's runtime;
2. identify required VRAM/RAM;
3. download weights to a dedicated model directory;
4. verify checksums when provided;
5. run a standalone model test;
6. add configuration to `.env.example`;
7. add provider/model routing;
8. run one pipeline smoke test;
9. benchmark quality and speed;
10. document the new model here.

Do not hard-code a model path into multiple agents.

---

## 20. Backup procedure

Back up at least:

```text
ConGenAI source code
.env.example
local .env (securely, NOT in Git)
model manifest/checksum list
model configuration notes
PostgreSQL database dump
important generated assets
research data/cache if valuable
```

For PostgreSQL, use the standard PostgreSQL dump utilities appropriate to the installed version, for example:

```bash
pg_dump -h localhost -U postgres -d congen > congen_backup.sql
```

Store secrets separately from the source backup.

Do not put large model weights into the Git repository. Store them on dedicated model storage and keep a manifest/checksum in Git.

---

## 21. Disaster recovery — from zero

If the machine is lost:

```text
1. Install OS updates
2. Install Git
3. Install Homebrew/system packages
4. Clone ConGenAI
5. Checkout the known-good commit
6. Install Python
7. Create .venv
8. Install requirements
9. Install PostgreSQL
10. Restore/create database
11. Install Redis
12. Install FFmpeg
13. Install local model runtime
14. Restore/download model weights
15. Create .env from .env.example
16. Configure local paths
17. Run dependency checks
18. Run H3 doctor/verify
19. Start API
20. Generate one image
21. Generate one video
22. Run one complete content pipeline
```

Record the known-good Git commit in your own backup notes after each stable release.

---

## 22. Configuration change matrix

| Goal | Change | Code change? |
|---|---|---|
| Run local H3 | `VIDEO_MODEL=minimax-h3` | No |
| Run Higgsfield H3 | `VIDEO_MODEL=higgsfield-h3` + external generation | No |
| Move H3 model directory | `H3_MODEL_DIR` | No |
| Move H3 executable | `H3_COMMAND` | No |
| Change PostgreSQL host | `POSTGRES_HOST` | No |
| Change Redis host | `REDIS_HOST` | No |
| Disable all cloud generation | `ALLOW_EXTERNAL_GENERATION=false` | No |
| Move from Mac to RTX | GPU runtime + model paths + environment | Usually no application-code change |
| Add a completely new provider | Provider adapter + routing | Yes |
| Replace an LLM runtime | Runtime/model configuration; adapter only if API differs | Maybe |
| Change generated content strategy | Strategy configuration/agent logic | Usually yes |

---

## 23. Golden rules

1. **Keep a known-good Git commit.**
2. **Keep Mac H3 working until the RTX 5090 setup is proven.**
3. **Keep provider selection in configuration.**
4. **Never hard-code secrets.**
5. **Never put model weights in Git.**
6. **Test one component before testing the entire pipeline.**
7. **Do not increase resolution and duration simultaneously during troubleshooting.**
8. **Local inference and Internet research are separate concerns.**
9. **Treat cloud video as optional, not as a dependency of the core architecture.**
10. **Every new model should have a documented runtime, path, memory requirement, smoke test, and rollback path.**

---

## 24. Current known-good Mac H3 state

At the time this runbook was created, the MacBook Air 16 GB setup had successfully reached the following state:

```text
Apple Silicon detected       PASS
MLX import                   PASS
BF16 MLX test                PASS
Disk capacity                PASS
FFmpeg                       PASS
H3 model SHA-256             PASS
Transformer weights          verified
Text encoder                 verified
Video VAE                    verified
Tokenizer                    verified
Audio VAE                    verified
```

The machine is a **development/experimental low-memory path**, not the final high-performance production target.

---

## 25. Future improvements to this runbook

When the project evolves, update this document whenever any of these change:

- model runtime;
- model name/version;
- environment variables;
- database schema;
- queue system;
- provider API;
- hardware profile;
- installation commands;
- startup commands;
- security requirements;
- backup procedure.

The runbook should always describe the latest known-good configuration, while Git history remains the source of truth for code.
