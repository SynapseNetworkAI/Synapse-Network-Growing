---
title: "Post-production runbook"
status: draft
created: 2026-04-30
---

# Post-production Runbook

Use this after recording local screen video with voiceover.

Working directory:

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing/content/synapse-workflows/2026-04-mcp-server-toolchain
```

## 1. Store Raw Recording

Place raw screen recordings here:

```text
assets/recordings/raw/
```

Recommended raw filename:

```text
assets/recordings/raw/synapse-workflow-demo-raw.mov
```

If you need a fully safe generated demo with synthetic screen frames, voiceover, external subtitles, and a burned-caption MP4, run:

```bash
python3 video/build_demo_video.py
```

This writes the same final artifact paths used by the manual workflow below.

## 2. Convert to Edited MP4

```bash
ffmpeg -i assets/recordings/raw/synapse-workflow-demo-raw.mov \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -preset medium \
  -c:a aac -b:a 160k \
  assets/recordings/edited/synapse-workflow-demo.mp4
```

## 3. Generate English Subtitles

```bash
whisper assets/recordings/edited/synapse-workflow-demo.mp4 \
  --language English \
  --task transcribe \
  --output_format srt \
  --output_dir assets/final
```

Rename the generated file to the stable expected name:

```bash
mv assets/final/synapse-workflow-demo.srt assets/final/synapse-workflow.en.srt
```

## 4. Copy Final MP4

```bash
cp assets/recordings/edited/synapse-workflow-demo.mp4 \
  assets/final/synapse-workflow-demo.mp4
```

## 5. Optional Burned-subtitle Version

Use this only if the publishing platform does not support external subtitles:

```bash
python3 video/build_demo_video.py
```

Note: this machine's ffmpeg build does not include the `subtitles` filter, so the generated demo builder burns captions by rendering text directly into the video frames instead of using `ffmpeg -vf subtitles=...`.

## 6. Final Checks

```bash
ffmpeg -v error -i assets/final/synapse-workflow-demo.mp4 -f null -
ffmpeg -v error -i assets/final/synapse-workflow-demo-subtitled.mp4 -f null -
test -s assets/final/synapse-workflow.en.srt
rg -i "private key|bearer|jwt|secret|token|api_key|password|mnemonic|gcloud secrets versions access|BEGIN .* KEY" .
```

The `rg` command may match this runbook and the safety checklist. It must not reveal real credentials or secret values.
