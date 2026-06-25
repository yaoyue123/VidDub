"""
Whisper speech-to-text service.

Manages model loading, audio extraction, and transcription.
All heavy operations run via asyncio.to_thread (Whisper is blocking).
"""

import os
import json
import logging
import subprocess
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds to VTT timestamp: HH:MM:SS.mmm."""
    return format_srt_timestamp(seconds).replace(",", ".")


def segments_to_srt(segments: list[dict[str, Any]]) -> str:
    """Convert Whisper segments to SRT format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_srt_timestamp(seg.get("start", 0))
        end = format_srt_timestamp(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments: list[dict[str, Any]]) -> str:
    """Convert segments to WebVTT."""
    vtt_lines = ["WEBVTT", ""]
    for seg in segments:
        start = format_vtt_timestamp(seg.get("start", 0))
        end = format_vtt_timestamp(seg.get("end", 0))
        text = seg.get("text", "").strip()
        vtt_lines.append(f"{start} --> {end}")
        vtt_lines.append(text)
        vtt_lines.append("")
    return "\n".join(vtt_lines)


class WhisperService:
    """Whisper speech-to-text service wrapper.

    Lazy-loads the model on first use. All transcription runs
    in executor threads to avoid blocking the asyncio event loop.
    """

    SUPPORTED_MODELS = ("tiny", "base", "small", "medium", "large", "turbo")

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "float32",
        download_root: Optional[str] = None,
    ):
        if model_name not in self.SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model '{model_name}'. Choose from {self.SUPPORTED_MODELS}")
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model = None

    # ── Model management ──

    def _load_model_sync(self) -> None:
        """Synchronously load the Whisper model (blocking)."""
        if self._model is not None:
            return

        import whisper

        logger.info("Loading Whisper model '%s' on %s...", self.model_name, self.device)
        kwargs = {"device": self.device}
        if self.download_root is not None:
            kwargs["download_root"] = self.download_root
        self._model = whisper.load_model(self.model_name, **kwargs)
        logger.info("Whisper model '%s' loaded", self.model_name)

    async def load_model(self) -> None:
        """Ensure model is loaded (async)."""
        if self._model is not None:
            return
        import asyncio
        await asyncio.to_thread(self._load_model_sync)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # ── Audio extraction ──

    async def extract_audio(self, video_path: str, output_dir: Optional[str] = None) -> str:
        """Extract audio from video file using ffmpeg.

        Returns path to extracted 16kHz WAV file.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if output_dir is None:
            output_dir = os.path.dirname(video_path)

        base = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(output_dir, f"{base}.wav")

        if os.path.exists(output_path):
            logger.info("Audio already extracted: %s", output_path)
            return output_path

        import asyncio

        def _extract():
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vn",                    # no video
                "-acodec", "pcm_s16le",    # PCM 16-bit
                "-ar", "16000",            # 16kHz sample rate
                "-ac", "1",                # mono
                "-y",                      # overwrite
                output_path,
            ]
            logger.info("Extracting audio: %s", " ".join(cmd))
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed (code {result.returncode}): {result.stderr}"
                )
            if not os.path.exists(output_path):
                raise RuntimeError(f"Audio file not created: {output_path}")
            logger.info("Audio extracted: %s", output_path)

        await asyncio.to_thread(_extract)
        return output_path

    # ── Transcription ──

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
        **whisper_kwargs,
    ) -> dict[str, Any]:
        """Transcribe audio file.

        Args:
            audio_path: Path to audio file (WAV/MP3).
            language: Language code (e.g. 'en', 'zh'). Auto-detected if None.
            task: 'transcribe' or 'translate' (translate to English).
            progress_callback: Called with status dicts during transcription.

        Returns:
            Dict with keys: text, segments, language.
            Each segment: {id, seek, start, end, text, tokens, temperature, avg_logprob, compression_ratio, no_speech_prob}
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        await self.load_model()

        if progress_callback:
            progress_callback({"status": "loading", "progress": 0, "message": "开始转写..."})

        import asyncio

        def _transcribe() -> dict[str, Any]:
            nonlocal whisper_kwargs
            model = self._model
            assert model is not None, "Model not loaded after load_model()"
            result = model.transcribe(
                audio_path,
                language=language,
                task=task,
                verbose=False,
                **whisper_kwargs,
            )
            return result

        result = await asyncio.to_thread(_transcribe)

        if progress_callback:
            progress_callback({"status": "completed", "progress": 100, "message": "转写完成"})

        return result

    # ── Subtitle format generation ──

    @staticmethod
    def segments_to_srt(segments: list[dict[str, Any]]) -> str:
        """Convert Whisper segments to SRT format."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp(seg.get("start", 0))
            end = _format_timestamp(seg.get("end", 0))
            text = seg.get("text", "").strip()
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def segments_to_vtt(segments: list[dict[str, Any]]) -> str:
        """Convert Whisper segments to WebVTT format."""
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = _format_timestamp(seg.get("start", 0)).replace(",", ".")
            end = _format_timestamp(seg.get("end", 0)).replace(",", ".")
            text = seg.get("text", "").strip()
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def segments_to_json(segments: list[dict[str, Any]]) -> str:
        """Convert segments to JSON for frontend editing."""
        data = []
        for seg in segments:
            data.append({
                "id": seg.get("id", 0),
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
            })
        return json.dumps(data, ensure_ascii=False, indent=2)


def _format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
