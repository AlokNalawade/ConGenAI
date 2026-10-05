# Minimal MiniMax H3 on a 16 GB MacBook Air

ConGenAI now has an isolated H3 smoke-test path for Apple Silicon.

## Backend

The integration uses the external `minimax-h3-stream-mac` MLX runner. It is intentionally not embedded into the FastAPI process because the 16 GB path depends on layer-by-layer weight streaming.

Install the runner separately:

```bash
git clone https://github.com/AIXF666/minimax-h3-stream-mac.git
cd minimax-h3-stream-mac
./scripts/install.command
```

Install/check the model according to that project's license and README. A complete video+audio model set is about 37.6 GiB, so an external SSD is a good option.

## ConGenAI environment

Add to `.env`:

```env
PROFILE=mac
H3_COMMAND=h3stream
H3_MODEL_DIR=/absolute/path/to/minimax-h3-stream-mac/models
H3_MEMORY_LIMIT_GIB=12.5
```

## Smoke test

The API endpoint is:

`POST /api/v1/video/h3/generate`

Request:

```json
{
  "content_id": "<existing-content-uuid>",
  "prompt": "A cinematic red panda walking through a misty bamboo forest, natural lighting, gentle camera movement",
  "width": 640,
  "height": 384,
  "seconds": 5,
  "steps": 16,
  "seed": 21,
  "audio": true
}
```

The endpoint intentionally starts at 640x384 / 5 seconds / 16 steps for the 16 GB Mac profile. It writes the MP4 into ConGenAI's normal asset directory and records it as an H3 video asset.

The normal scene compositor is unchanged. This lets us validate H3 independently before making it part of the full production pipeline.

## Why this configuration

The low-memory runner has reported an end-to-end 640x384, 5.17-second, 24 fps, stereo-audio run on a 16 GB Apple Silicon Mac at roughly 50-52 minutes. Treat that as a smoke-test benchmark, not a guaranteed runtime.

Do not commit model weights or generated media to ConGenAI.
