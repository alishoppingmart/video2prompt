# Video2Prompt

Turns any video into a list of 8-second AI-video-generation scene prompts
(for Veo / Kling / Flow pipelines). Extracts one frame every 8 seconds via
ffmpeg, sends each frame to Gemini 2.5 Flash (vision) for captioning, and
writes `<video>_segments.md` and `<video>_segments.csv`.

## One-time setup (to build the .exe yourself)

1. Push this folder to a GitHub repo.
2. GitHub Actions (`.github/workflows/build.yml`) builds `Video2Prompt.exe`
   automatically on every push to `main` — grab it from the **Actions** tab
   → latest run → **Artifacts** → `Video2Prompt-windows`.
3. Or run locally without building an exe:
   ```
   pip install -r requirements.txt
   python video2prompt.py
   ```

## Requirements on the machine running the exe

- **ffmpeg + ffprobe** on PATH (download from ffmpeg.org, or drop
  `ffmpeg/bin/ffmpeg.exe` and `ffmpeg/bin/ffprobe.exe` next to the exe).
- A free **Gemini API key** — https://aistudio.google.com/apikey
  (same key type you're already using for the Replit shot-card tool).

## Usage

1. Open `Video2Prompt.exe`.
2. Browse to your video file.
3. Pick an output folder (defaults to the video's folder).
4. Paste your Gemini API key (saved locally for next time, in
   `%APPDATA%\Video2Prompt\config.json`).
5. Click **Run**. Progress bar + log show frame-by-frame captioning.
6. Output lands as `<video>_segments.md` and `<video>_segments.csv`.

## Notes / limits

- Segment length is fixed at 8s.
- ~1.1s delay between Gemini calls to stay under free-tier rate limits —
  a 25-minute video (~185 segments) takes roughly 4–5 minutes to process.
- If a frame caption fails (rate limit, network), it retries 3x then
  writes `[caption failed: ...]` for that segment so the run doesn't stop.
- API key is stored in plaintext locally — fine for personal use, don't
  share the config.json.
