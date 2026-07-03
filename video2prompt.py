"""
Video2Prompt — AJ Tech
Extracts a frame every 8 seconds from a video and uses Gemini vision to
generate structured 8-second AI-video-generation scene prompts
(for Veo / Kling / Flow style pipelines).

Output: <video_name>_segments.md and .csv next to the video (or chosen folder).

Requires: ffmpeg + ffprobe available on PATH (or placed next to this exe
in a folder named "ffmpeg\\bin\\ffmpeg.exe" and "ffmpeg\\bin\\ffprobe.exe").
"""

import os
import sys
import json
import csv
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

SEGMENT_SECONDS = 8
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Video2Prompt")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

SYSTEM_INSTRUCTION = (
    "You are a video-to-prompt assistant for an AI video generation pipeline "
    "(Veo, Kling, Flow). You will be shown a single video frame that represents "
    "an 8-second segment of a longer video. Write ONE concise, concrete, visual "
    "scene description (max 30 words) suitable as a text-to-video generation prompt. "
    "Describe: subject, action, setting, camera framing. No preamble, no quotes, "
    "no markdown, just the prompt sentence itself."
)


def resource_ffmpeg():
    """Find ffmpeg/ffprobe: PATH first, then bundled ffmpeg\\bin next to the exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidates_ffmpeg = ["ffmpeg", os.path.join(base, "ffmpeg", "bin", "ffmpeg.exe")]
    candidates_ffprobe = ["ffprobe", os.path.join(base, "ffmpeg", "bin", "ffprobe.exe")]

    ffmpeg_path = shutil.which("ffmpeg") or next(
        (c for c in candidates_ffmpeg if os.path.isfile(c)), None
    )
    ffprobe_path = shutil.which("ffprobe") or next(
        (c for c in candidates_ffprobe if os.path.isfile(c)), None
    )
    return ffmpeg_path, ffprobe_path


def load_config():
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_duration(ffprobe_path, video_path):
    out = subprocess.run(
        [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True, check=True
    )
    return float(out.stdout.strip())


def extract_frames(ffmpeg_path, video_path, out_dir, log):
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "seg_%04d.jpg")
    cmd = [
        ffmpeg_path, "-y", "-i", video_path,
        "-vf", f"fps=1/{SEGMENT_SECONDS}", "-q:v", "3", pattern
    ]
    log(f"Extracting a frame every {SEGMENT_SECONDS}s ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-2000:]}")
    frames = sorted(f for f in os.listdir(out_dir) if f.startswith("seg_"))
    log(f"Extracted {len(frames)} frames.")
    return [os.path.join(out_dir, f) for f in frames]


def caption_frame(model, image_path, retries=3):
    from PIL import Image
    img = Image.open(image_path)
    for attempt in range(retries):
        try:
            resp = model.generate_content([SYSTEM_INSTRUCTION, img])
            text = (resp.text or "").strip().replace("\n", " ")
            return text if text else "Scene unavailable — describe manually."
        except Exception as e:
            if attempt == retries - 1:
                return f"[caption failed: {e}]"
            time.sleep(2 * (attempt + 1))


def format_timestamp(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def run_pipeline(video_path, api_key, out_dir, log, progress_cb, done_cb):
    try:
        import google.generativeai as genai
    except ImportError:
        log("ERROR: google-generativeai package not installed.")
        done_cb(False)
        return

    ffmpeg_path, ffprobe_path = resource_ffmpeg()
    if not ffmpeg_path or not ffprobe_path:
        log("ERROR: ffmpeg/ffprobe not found on PATH or bundled ffmpeg\\bin folder.")
        done_cb(False)
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        work_dir = os.path.join(out_dir, f"{video_name}_frames")
        frames = extract_frames(ffmpeg_path, video_path, work_dir, log)

        results = []
        total = len(frames)
        for i, frame_path in enumerate(frames):
            ts = format_timestamp(i * SEGMENT_SECONDS)
            log(f"[{i+1}/{total}] {ts} -> captioning...")
            caption = caption_frame(model, frame_path)
            results.append({"segment": i + 1, "timestamp": ts, "prompt": caption})
            progress_cb(i + 1, total)
            time.sleep(1.1)  # stay under free-tier rate limits

        md_path = os.path.join(out_dir, f"{video_name}_segments.md")
        csv_path = os.path.join(out_dir, f"{video_name}_segments.csv")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {video_name} — {SEGMENT_SECONDS}s Segment Prompts\n\n")
            for r in results:
                f.write(f"{r['segment']} [{r['timestamp']}] — {r['prompt']}\n")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["segment", "timestamp", "prompt"])
            writer.writeheader()
            writer.writerows(results)

        log(f"\nDone. Wrote:\n{md_path}\n{csv_path}")
        done_cb(True)
    except Exception as e:
        log(f"ERROR: {e}")
        done_cb(False)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video2Prompt — AJ Tech")
        self.geometry("640x520")
        self.resizable(False, False)

        cfg = load_config()

        self.video_path = tk.StringVar()
        self.out_dir = tk.StringVar(value=cfg.get("out_dir", ""))
        self.api_key = tk.StringVar(value=cfg.get("api_key", ""))

        pad = {"padx": 10, "pady": 6}

        tk.Label(self, text="Video file:").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.video_path, width=55).grid(row=0, column=1, **pad)
        tk.Button(self, text="Browse", command=self.pick_video).grid(row=0, column=2, **pad)

        tk.Label(self, text="Output folder:").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.out_dir, width=55).grid(row=1, column=1, **pad)
        tk.Button(self, text="Browse", command=self.pick_out_dir).grid(row=1, column=2, **pad)

        tk.Label(self, text="Gemini API key:").grid(row=2, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.api_key, width=55, show="*").grid(row=2, column=1, **pad)

        tk.Label(self, text=f"Segment length: {SEGMENT_SECONDS}s (fixed)").grid(
            row=3, column=0, columnspan=2, sticky="w", **pad
        )

        self.run_btn = tk.Button(self, text="Run", width=20, command=self.run_clicked)
        self.run_btn.grid(row=4, column=0, columnspan=3, pady=10)

        self.progress = ttk.Progressbar(self, length=600, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, padx=10, pady=4)

        self.log_box = scrolledtext.ScrolledText(self, width=78, height=20, state="disabled")
        self.log_box.grid(row=6, column=0, columnspan=3, padx=10, pady=10)

    def pick_video(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")]
        )
        if path:
            self.video_path.set(path)
            if not self.out_dir.get():
                self.out_dir.set(os.path.dirname(path))

    def pick_out_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.out_dir.set(path)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def progress_cb(self, current, total):
        self.progress["maximum"] = total
        self.progress["value"] = current
        self.update_idletasks()

    def done_cb(self, success):
        self.run_btn.configure(state="normal")
        if success:
            messagebox.showinfo("Video2Prompt", "Segment prompts generated successfully.")
        else:
            messagebox.showerror("Video2Prompt", "Something went wrong — check the log.")

    def run_clicked(self):
        video = self.video_path.get().strip()
        out_dir = self.out_dir.get().strip()
        api_key = self.api_key.get().strip()

        if not video or not os.path.isfile(video):
            messagebox.showwarning("Video2Prompt", "Pick a valid video file first.")
            return
        if not out_dir:
            messagebox.showwarning("Video2Prompt", "Pick an output folder first.")
            return
        if not api_key:
            messagebox.showwarning("Video2Prompt", "Enter your Gemini API key.")
            return

        save_config({"out_dir": out_dir, "api_key": api_key})

        self.run_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress["value"] = 0

        t = threading.Thread(
            target=run_pipeline,
            args=(video, api_key, out_dir, self.log, self.progress_cb, self.done_cb),
            daemon=True,
        )
        t.start()


if __name__ == "__main__":
    App().mainloop()
