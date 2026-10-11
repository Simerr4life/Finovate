#!/usr/bin/env python3
"""Compose the Finovate product demo from title cards + screen recordings."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "source" / "cards"
RAW = ROOT / "source" / "raw"
EXPORT = ROOT / "export"
EXPORT.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 30
OUT = EXPORT / "finovate_product_demo.mp4"

# Prefer artifacts copies, fall back to repo raw/
SEGMENTS = [
    "finovate_demo_segment1_landing_dashboard.mp4",
    "finovate_demo_segment2_savings_goals.mp4",
    "finovate_demo_segment3_investing_insights.mp4",
]


def find_segment(name: str) -> Path:
    for base in (Path("/opt/cursor/artifacts"), RAW):
        path = base / name
        if path.exists():
            return path
    raise FileNotFoundError(name)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd[:8]), "...")
    subprocess.run(cmd, check=True)


def still_to_clip(png: Path, dest: Path, seconds: float) -> None:
    fade = min(0.55, seconds / 3)
    out_start = max(0.01, seconds - fade)
    run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(png),
            "-vf", (
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={FPS},format=yuv420p,"
                f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={out_start:.2f}:d={fade:.2f}"
            ),
            "-t", f"{seconds:.2f}", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an", str(dest),
        ]
    )


def normalize_screen(src: Path, dest: Path, speed: float = 1.0) -> None:
    """Letterbox 1920x1200 (or any) into 1920x1080 @ 30fps. Optional speed-up."""
    setpts = f"setpts=PTS/{speed}" if abs(speed - 1.0) > 1e-3 else "setpts=PTS-STARTPTS"
    run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", (
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x112b2b,"
                f"fps={FPS},format=yuv420p,{setpts}"
            ),
            "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            str(dest),
        ]
    )


def concat(paths: list[Path], dest: Path) -> None:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in paths))
    run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-r", str(FPS), "-pix_fmt", "yuv420p",
            str(dest),
        ]
    )


def burn_captions(src: Path, srt: Path, dest: Path) -> None:
    # Escape path for ffmpeg subtitles filter
    escaped = str(srt.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    style = (
        "FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00112B2B,BorderStyle=1,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=48"
    )
    run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", f"subtitles='{escaped}':force_style='{style}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            str(dest),
        ]
    )


def mix_audio(video: Path, audio: Path, dest: Path) -> None:
    run(
        [
            "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
            "-filter_complex",
            "[1:a]volume=1.0,afade=t=in:d=1.2,afade=t=out:st=125:d=3.5,alimiter=limit=0.95[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            str(dest),
        ]
    )


def write_srt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    def ts(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    lines = []
    for i, (start, end, text) in enumerate(cues, 1):
        lines.append(str(i))
        lines.append(f"{ts(start)} --> {ts(end)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="finovate-compose-"))
    print("work dir", work)

    intro = work / "01_intro.mp4"
    card_fi = work / "02_first_impressions.mp4"
    card_core = work / "03_core_walkthrough.mp4"
    card_diff = work / "04_differentiators.mp4"
    card_journey = work / "05_journey.mp4"
    closing = work / "06_closing.mp4"

    still_to_clip(CARDS / "01_intro.png", intro, 4.5)
    still_to_clip(CARDS / "02_first_impressions.png", card_fi, 2.8)
    still_to_clip(CARDS / "03_core_walkthrough.png", card_core, 2.8)
    still_to_clip(CARDS / "04_differentiators.png", card_diff, 2.8)
    still_to_clip(CARDS / "05_journey.png", card_journey, 2.8)
    still_to_clip(CARDS / "06_closing.png", closing, 4.5)

    # Slight speed-up on the longest segment to keep the cut concise
    speeds = [1.05, 1.08, 1.15]
    norms = []
    for name, speed in zip(SEGMENTS, speeds):
        dest = work / f"norm_{name}"
        normalize_screen(find_segment(name), dest, speed=speed)
        norms.append(dest)

    # Timeline: intro → first impressions → seg1 → core → seg2 → diff → journey → seg3 → close
    pieces = [
        intro, card_fi, norms[0],
        card_core, norms[1],
        card_diff, card_journey, norms[2],
        closing,
    ]
    silent = work / "silent.mp4"
    concat(pieces, silent)

    # Build caption cues based on measured durations
    t = 0.0
    cues: list[tuple[float, float, str]] = []
    labels = [
        (intro, "Finovate — personal finance, made clear"),
        (card_fi, "First impressions: a calm place to see your money"),
        (norms[0], "Landing page → sample dashboard with real recorded totals"),
        (card_core, "Track spending, plan savings, and watch goals grow"),
        (norms[1], "Transactions, savings plan, goals, and pools — on your data"),
        (card_diff, "Explainable plans. Simulated investing — clearly labeled"),
        (card_journey, "Insights and a responsive experience, desktop to mobile"),
        (norms[2], "Investing tools are simulated. Insights highlight spending patterns."),
        (closing, "Clarity over complexity. Track. Budget. Save. Preview."),
    ]
    for clip, text in labels:
        dur = probe_duration(clip)
        # Show caption for most of the clip, skipping short fades
        start = t + 0.35
        end = t + max(1.0, dur - 0.35)
        cues.append((start, end, text))
        t += dur

    srt = ROOT / "project" / "finovate_product_demo.srt"
    write_srt(srt, cues)

    captioned = work / "captioned.mp4"
    # silent has no audio track; burn captions first
    run(
        [
            "ffmpeg", "-y", "-i", str(silent),
            "-vf",
            "subtitles='"
            + str(srt.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            + "':force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00112B2B,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=48'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an",
            str(captioned),
        ]
    )

    audio = Path("/tmp/finovate-demo/audio/ambient_soft.m4a")
    if not audio.exists():
        audio = Path("/tmp/finovate-demo/audio/ambient.m4a")
    # Copy audio into project for reproducibility
    audio_dest = ROOT / "source" / "audio"
    audio_dest.mkdir(parents=True, exist_ok=True)
    project_audio = audio_dest / "ambient_soft.m4a"
    if audio.exists() and not project_audio.exists():
        project_audio.write_bytes(audio.read_bytes())

    mix_audio(captioned, project_audio if project_audio.exists() else audio, OUT)

    # Also place a copy in artifacts
    artifact = Path("/opt/cursor/artifacts/finovate_product_demo.mp4")
    artifact.write_bytes(OUT.read_bytes())

    dur = probe_duration(OUT)
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"Exported {OUT} ({dur:.1f}s, {size_mb:.1f} MB)")
    print(f"Copied to {artifact}")


if __name__ == "__main__":
    main()
