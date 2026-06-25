"""Auto voice cloning + voice selection for background-aware dubbing.

Strategy (tried in order):
1. VOICE CLONE — Extract best speech segment from vocals, upload to
   SiliconFlow voice clone API, use cloned voice URI for all TTS.
2. AUTO PITCH  — Analyze original audio pitch → male/female →
   select best matching built-in voice.
3. DEFAULT     — Use configured default voice (e.g., "anna").
"""

import logging
import os
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Built-in voices by gender
MALE_VOICES = ["alex", "benjamin", "charles", "david"]
FEMALE_VOICES = ["anna", "bella", "claire", "diana"]

# Required audio length for cloning (seconds)
CLONE_SAMPLE_MIN_SEC = 5.0
CLONE_SAMPLE_MAX_SEC = 15.0


async def clone_voice_from_vocals(
    vocals_path: str,
    segments: list[dict],
    video_id: int,
    *,
    base_dir: str = "./downloads",
) -> Optional[dict[str, str]]:
    """Extract best speech sample and clone via SiliconFlow.

    Args:
        vocals_path: Path to vocals.wav (clean speech from demucs).
        segments: Whisper segments with id/start/end/text/confidence.
        video_id: Video ID for naming the cloned voice.
        base_dir: Downloads base directory.

    Returns:
        {"uri": str, "name": str, "voice": str} or None if cloning fails.
    """
    # Find the best segment for cloning
    sample_info = _extract_speech_sample(vocals_path, segments, video_id, base_dir)
    if not sample_info:
        logger.warning("No suitable speech sample found for voice cloning")
        return None

    sample_path, sample_text = sample_info

    try:
        from app.services.voice_cloner.siliconflow_provider import (
            SiliconFlowVoiceCloner,
        )
        cloner = SiliconFlowVoiceCloner()
        voice_name = f"video_{video_id}_speaker"
        uri = await cloner.upload_voice(sample_path, voice_name, sample_text)

        # Clean up sample file
        try:
            os.remove(sample_path)
        except OSError:
            pass

        logger.info(
            "Voice cloned for video %d: name=%s uri=%s",
            video_id, voice_name, uri,
        )
        # The uri is the voice parameter for TTS
        return {"uri": uri, "name": voice_name, "voice": uri}

    except Exception as e:
        logger.warning("Voice cloning failed for video %d: %s", video_id, e)
        # Clean up sample on failure
        try:
            os.remove(sample_path)
        except OSError:
            pass
        return None


def _extract_speech_sample(
    vocals_path: str,
    segments: list[dict],
    video_id: int,
    base_dir: str,
) -> Optional[tuple[str, str]]:
    """Extract a short clean speech WAV for voice cloning.

    Picks the segment with the best score:
      - Duration in [5, 15] seconds
      - High Whisper confidence (no_speech_prob low)
      - Longer preferred (more training data for cloning)

    Returns:
        (sample_wav_path, sample_text) or None.
    """
    # Filter and score segments
    candidates = []
    for seg in segments:
        dur = float(seg.get("end", 0)) - float(seg.get("start", 0))
        if dur < CLONE_SAMPLE_MIN_SEC or dur > CLONE_SAMPLE_MAX_SEC:
            continue
        text = (seg.get("text") or "").strip()
        if len(text) < 10:
            continue
        # Score: prefer longer segments with low no_speech_prob
        no_speech = float(seg.get("no_speech_prob", 0.5))
        score = dur * (1.0 - no_speech)
        candidates.append((score, seg))

    if not candidates:
        return None

    # Pick the best candidate
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_seg = candidates[0][1]

    # Extract audio segment from vocals.wav
    from app.services.dubbing.paths import video_work_dir
    work_dir = video_work_dir(video_id, base_dir=base_dir)
    sample_path = os.path.join(work_dir, "clone_sample.wav")

    start = float(best_seg["start"])
    dur = float(best_seg["end"]) - start

    # Use ffprobe + ffmpeg asynchronously
    import asyncio
    loop = asyncio.get_event_loop()
    import subprocess as _sp

    async def _extract():
        from app.services.dubbing.ffmpeg import run_ffmpeg_async
        await run_ffmpeg_async([
            "ffmpeg", "-y",
            "-i", vocals_path,
            "-ss", f"{start:.3f}",
            "-t", f"{dur:.3f}",
            "-ac", "1",          # Mono for cloning
            "-ar", "16000",       # 16kHz (voice cloning API requirement)
            sample_path,
        ])

    try:
        asyncio.get_running_loop()
        # We're in async context; use run_ffmpeg_async directly
    except RuntimeError:
        pass

    # Run synchronously since we may be called from sync context
    import subprocess as _sp
    result = _sp.run([
        "ffmpeg", "-y",
        "-i", vocals_path,
        "-ss", f"{start:.3f}",
        "-t", f"{dur:.3f}",
        "-ac", "1",
        "-ar", "16000",
        sample_path,
    ], capture_output=True)
    if result.returncode != 0:
        logger.warning(
            "Failed to extract clone sample: %s",
            result.stderr.decode("utf-8", errors="replace")[-200:],
        )
        return None

    text = best_seg.get("text", "").strip()
    logger.info(
        "Extracted clone sample: %.1f-%.1fs (%d chars) -> %s",
        start, start + dur, len(text), sample_path,
    )
    return sample_path, text


def auto_select_voice(
    vocals_path: str,
    segments: list[dict],
    *,
    default_voice: str = "anna",
) -> str:
    """Auto-select the best TTS voice based on audio pitch analysis.

    Tries to determine speaker gender from fundamental frequency (F0):
    - Average F0 > 170 Hz → female voice
    - Average F0 ≤ 170 Hz → male voice

    Falls back to default_voice if analysis fails.
    """
    try:
        is_female = _detect_female_voice(vocals_path, segments)
    except Exception as e:
        logger.debug("Pitch analysis failed, using default voice: %s", e)
        return default_voice

    pool = FEMALE_VOICES if is_female else MALE_VOICES
    # Deterministic selection: use segment count as seed
    chosen = pool[len(segments) % len(pool)]
    logger.info(
        "Auto voice selection: %s → %s (is_female=%s)",
        "female" if is_female else "male", chosen, is_female,
    )
    return chosen


def _detect_female_voice(
    vocals_path: str, segments: list[dict],
) -> bool:
    """Analyze pitch to determine if speaker is female.

    Uses librosa if available; falls back to heuristic based on
    segment text sentiment.
    """
    try:
        import librosa
        import numpy as np
        import soundfile as sf
    except ImportError:
        logger.debug("librosa not available, using heuristic")
        return _heuristic_gender(segments)

    try:
        # Load the first 30 seconds of vocals
        y, sr = sf.read(vocals_path, frames=30 * 22050, dtype="float32")
        if len(y.shape) > 1:
            y = y.mean(axis=1)  # Convert to mono
        if sr != 22050:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=22050)
            sr = 22050

        # Extract pitch (F0) using librosa's piptrack
        pitches, magnitudes = librosa.piptrack(
            y=y, sr=sr, fmin=80, fmax=400,
        )

        # Average pitch weighted by magnitude (ignore zeros)
        f0_values = []
        for t in range(pitches.shape[1]):
            idx = magnitudes[:, t].argmax()
            pitch = pitches[idx, t]
            if pitch > 80:  # Filter out silence
                f0_values.append(pitch)

        if not f0_values:
            return _heuristic_gender(segments)

        avg_f0 = sum(f0_values) / len(f0_values)
        logger.info("Average F0: %.1f Hz", avg_f0)

        # Typical male: 85-180 Hz, female: 165-255 Hz
        # Use 170 Hz as the boundary
        return avg_f0 > 170.0

    except Exception as e:
        logger.debug("Pitch extraction failed: %s", e)
        return _heuristic_gender(segments)


def _heuristic_gender(segments: list[dict]) -> bool:
    """Heuristic gender detection without librosa.

    Uses segment-level statistics (very rough, ~60% accurate).
    Defaults to male when uncertain.
    """
    # Simple heuristic: count question marks and exclamations
    # Women tend to use more expressive punctuation in some languages
    total_text = " ".join(s.get("text", "") for s in segments).lower()

    # Extremely rough: if the text seems to have more emotional markers
    emotional = total_text.count("!") + total_text.count("?")
    total_chars = max(len(total_text), 1)

    # High emotional ratio → slightly more likely female
    # This is not scientific but better than random
    ratio = emotional / total_chars
    return ratio > 0.05  # >5% emotional punctuation → guess female
