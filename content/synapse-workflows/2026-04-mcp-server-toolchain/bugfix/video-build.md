---
title: "Video build bugfix log"
status: fixed
created: 2026-04-30
---

# Video Build Bugfix Log

## BUG-001: ffmpeg subtitles filter failed on absolute SRT path

Status: superseded by BUG-002

Stage:
`video/build_demo_video.py` burned-subtitle generation.

Failure:

```text
No option name near '/Users/cliff/workspace/agent/Synapse-Network-Growing/.../assets/final/synapse-workflow.en.srt'
Error parsing filterchain 'subtitles=...'
```

Cause:
`ffmpeg`'s `subtitles=` filter is fragile with quoted absolute macOS paths. The final MP4 and external SRT had already been generated, but the optional burned-subtitle MP4 failed.

Attempted fix:
Use a content-pack-relative subtitle path from the content root:

```text
subtitles=assets/final/synapse-workflow.en.srt
```

Validation:
Re-run:

```bash
python3 video/build_demo_video.py
```

Expected artifacts:

- `assets/final/synapse-workflow-demo.mp4`
- `assets/final/synapse-workflow.en.srt`
- `assets/final/synapse-workflow-demo-subtitled.mp4`

## BUG-002: local ffmpeg build has no subtitles filter

Status: fixed

Stage:
`video/build_demo_video.py` burned-subtitle generation.

Failure:

```text
[AVFilterGraph ...] No such filter: 'subtitles'
Error opening output file assets/final/test-subtitled.mp4.
```

Cause:
The local ffmpeg binary does not include the subtitle burn-in filter. External SRT generation is fine, but hard-subtitle rendering cannot depend on ffmpeg/libass on this machine.

Fix:
Render caption text directly into each synthetic screen frame with PIL, build a second captioned segment track, then concatenate those captioned segments into:

```text
assets/final/synapse-workflow-demo-subtitled.mp4
```

Validation:

```bash
python3 video/build_demo_video.py
ffmpeg -v error -i assets/final/synapse-workflow-demo.mp4 -f null -
ffmpeg -v error -i assets/final/synapse-workflow-demo-subtitled.mp4 -f null -
test -s assets/final/synapse-workflow.en.srt
```
