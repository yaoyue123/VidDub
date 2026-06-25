"""Audio source separation via demucs (Meta).

Splits audio into vocals (for cleaner transcription + voice cloning)
and background (preserved for final mix).

Uses demucs htdemucs 4-stem model:
    vocals, drums, bass, other → background = drums + bass + other
"""

import logging
import os
from typing import Optional

from app.services.dubbing.ffmpeg import run_ffmpeg_async

logger = logging.getLogger(__name__)

# demucs model: htdemucs (best quality) or htdemucs_ft (fine-tuned)
DEFAULT_MODEL = "htdemucs"


async def separate_audio(
    audio_path: str,
    output_dir: str,
    *,
    model: str = DEFAULT_MODEL,
    device: str = "cpu",
) -> tuple[str, str]:
    """Separate audio into vocals and background using demucs.

    Args:
        audio_path: Path to stereo WAV (44.1kHz recommended).
        output_dir: Directory for demucs output.
        model: demucs model name (htdemucs, htdemucs_ft).
        device: "cpu" or "cuda".

    Returns:
        (vocals_path, background_path) — both absolute paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Run demucs (two-stem: vocals + no_vocals for efficiency)
    # Use subprocess since demucs CLI is the stable API
    cmd = [
        "python", "-m", "demucs",
        "--two-stems", "vocals",     # Only separate vocals, rest is "no_vocals"
        "-n", model,
        "-d", device,
        "--out", output_dir,
        audio_path,
    ]

    logger.info("demucs separating: %s (model=%s, device=%s)", audio_path, model, device)

    # demucs output structure: {output_dir}/{model}/{filename_stem}/
    #   vocals.wav + no_vocals.wav
    try:
        import subprocess as _sp
        result = await _run_subprocess(cmd)
    except Exception as e:
        raise RuntimeError(f"demucs separation failed: {e}") from e

    # Locate output files
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    demucs_out = os.path.join(output_dir, model, stem)

    vocals_path = os.path.join(demucs_out, "vocals.wav")
    background_path = os.path.join(demucs_out, "background.wav")

    if not os.path.exists(vocals_path):
        raise RuntimeError(
            f"demucs did not produce vocals.wav at {vocals_path}"
        )

    # demucs "no_vocals.wav" is the background; rename for clarity
    no_vocals_path = os.path.join(demucs_out, "no_vocals.wav")
    if os.path.exists(no_vocals_path):
        os.replace(no_vocals_path, background_path)
    else:
        # Fallback: if no_vocals missing, generate silence
        await _generate_silence_background(audio_path, background_path)

    logger.info(
        "demucs done: vocals=%s background=%s",
        vocals_path, background_path,
    )
    return vocals_path, background_path


async def _generate_silence_background(
    reference_path: str, output_path: str,
) -> None:
    """Generate a silent background track matching reference duration."""
    from app.services.dubbing.ffmpeg import ffprobe_duration
    dur = await ffprobe_duration(reference_path)
    await run_ffmpeg_async([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{dur:.3f}",
        "-ar", "44100", "-ac", "2",
        output_path,
    ])


async def _run_subprocess(cmd: list[str]) -> int:
    """Run demucs subprocess, streaming output to logger."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _stream(stream, level):
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.log(level, "demucs: %s", text)

    import asyncio
    await asyncio.gather(
        _stream(proc.stdout, logging.DEBUG),
        _stream(proc.stderr, logging.WARNING),
    )
    await proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"demucs exited with code {proc.returncode}")

    return proc.returncode


def mix_background_audio(
    dubbing_path: str,
    background_path: str,
    output_path: str,
    background_volume: float = 0.3,
) -> list[str]:
    """Build ffmpeg command to mix dubbing + background.

    Args:
        dubbing_path: Dubbed speech audio.
        background_path: Original background audio (no_vocals).
        output_path: Mixed output path.
        background_volume: Background volume ratio (0.0-1.0).

    Returns:
        ffmpeg command list (for run_ffmpeg_async).
    """
    # Use amix to combine dubbed speech + background at reduced volume
    # weights: speech=1.0, background=background_volume
    filter_complex = (
        f"[0:a]volume=1.0[speech];"
        f"[1:a]volume={background_volume:.2f}[bg];"
        f"[speech][bg]amix=inputs=2:duration=longest:normalize=0[out]"
    )

    return [
        "ffmpeg", "-y",
        "-i", dubbing_path,
        "-i", background_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", "44100",
        "-ac", "2",
        output_path,
    ]
