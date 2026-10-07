"""
Microphone recorder: capture audio from the system mic and save to file.

Pairs naturally with the audio/ transcription module:

    from record import record_to_file
    from audio import transcribe_chunked

    path = record_to_file("session.wav")      # records until Ctrl-C
    result = transcribe_chunked(path)
    print(result.merged_text)

Requires PortAudio (sounddevice depends on it):
    macOS:   brew install portaudio
    Debian:  sudo apt install libportaudio2
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    import soundfile as sf

    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False
    logger.debug("sounddevice/soundfile not installed; Recorder unavailable.")

# Whisper resamples internally but expects 16 kHz; record at native rate.
DEFAULT_SAMPLERATE = 16_000
DEFAULT_CHANNELS = 1


def _require_sound() -> None:
    if not SOUND_AVAILABLE:
        raise ImportError(
            "sounddevice and soundfile are required. "
            "Install with: pip install -r record/requirements.txt\n"
            "Also needs PortAudio: brew install portaudio  (macOS)"
        )


class Recorder:
    """
    Buffered microphone recorder.

    Context manager (recommended)::

        with Recorder() as rec:
            rec.record(duration=5, path="clip.wav")

    Manual start/stop::

        rec = Recorder()
        rec.start()
        time.sleep(5)
        audio = rec.stop()
        rec.save("clip.wav", audio)
    """

    def __init__(
        self,
        samplerate: int = DEFAULT_SAMPLERATE,
        channels: int = DEFAULT_CHANNELS,
        device: Optional[Union[int, str]] = None,
    ) -> None:
        _require_sound()
        self.samplerate = samplerate
        self.channels = channels
        self.device = device
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None  # type: ignore[name-defined]
        self._recording = False

    # ── stream control ───────────────────────────────────────────────────────

    def start(self) -> "Recorder":
        """Begin capturing audio (non-blocking). Returns self for chaining."""
        if self._recording:
            raise RuntimeError("Already recording — call stop() first.")
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            device=self.device,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        logger.debug(
            "Recording started (sr=%d, ch=%d, device=%s)",
            self.samplerate,
            self.channels,
            self.device,
        )
        return self

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:  # noqa: ARG002
        if status:
            logger.warning("sounddevice: %s", status)
        self._frames.append(indata.copy())

    def stop(self) -> np.ndarray:
        """
        Stop capturing. Returns the full recording as a ``(N, channels)`` float32 array.
        The data is also kept internally so ``save()`` can be called afterward.
        """
        if not self._recording:
            raise RuntimeError("Not recording.")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._recording = False
        if not self._frames:
            return np.zeros((0, self.channels), dtype="float32")
        audio = np.concatenate(self._frames, axis=0)
        logger.info("Stopped: %.2f s  (%d samples)", len(audio) / self.samplerate, len(audio))
        return audio

    # ── file I/O ─────────────────────────────────────────────────────────────

    def save(
        self,
        path: Union[str, Path],
        audio: Optional[np.ndarray] = None,
    ) -> Path:
        """
        Write audio to *path*. If *audio* is omitted the most recent recording
        buffer is used. Parent directories are created if needed.
        """
        if audio is None:
            if not self._frames:
                raise RuntimeError("No audio recorded yet.")
            audio = np.concatenate(self._frames, axis=0)
        out = Path(path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), audio, self.samplerate)
        duration = len(audio) / self.samplerate
        logger.info("Saved %s  (%.2f s)", out, duration)
        print(f"  Saved → {out}  ({duration:.1f} s)", flush=True)
        return out

    # ── blocking convenience ─────────────────────────────────────────────────

    def record(
        self,
        duration: Optional[float] = None,
        *,
        path: Optional[Union[str, Path]] = None,
        show_level: bool = True,
    ) -> Optional[Path]:
        """
        Blocking record with optional auto-save.

        duration=None
            Record until **Ctrl-C**.
        path
            Save file automatically when done.
        show_level
            Print a live RMS level bar to the terminal.
        """
        self.start()
        audio: Optional[np.ndarray] = None
        try:
            if duration is not None:
                print(f"Recording for {duration:.1f} s…  (Ctrl-C to stop early)", flush=True)
                end = time.monotonic() + duration
                while time.monotonic() < end and self._recording:
                    if show_level:
                        _print_level(self._frames)
                    time.sleep(0.05)
            else:
                print("Recording…  (Ctrl-C to stop)", flush=True)
                while self._recording:
                    if show_level:
                        _print_level(self._frames)
                    time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            if self._recording:
                audio = self.stop()
            else:
                audio = np.concatenate(self._frames, axis=0) if self._frames else None
            print(flush=True)

        if audio is not None:
            dur = len(audio) / self.samplerate
            print(f"Captured {dur:.1f} s of audio.", flush=True)

        if path is not None and audio is not None:
            return self.save(path, audio)
        return None

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *_) -> None:
        if self._recording:
            self.stop()


# ── module-level helpers ─────────────────────────────────────────────────────


def record_to_file(
    path: Union[str, Path],
    duration: Optional[float] = None,
    *,
    samplerate: int = DEFAULT_SAMPLERATE,
    channels: int = DEFAULT_CHANNELS,
    device: Optional[Union[int, str]] = None,
    show_level: bool = True,
) -> Path:
    """
    One-call record-and-save.

    duration=None → record until Ctrl-C.

    Returns the saved path so you can pass it straight to ``transcribe_chunked()``.

    Example::

        from record import record_to_file
        from audio import transcribe_chunked

        path = record_to_file("session.wav", duration=10)
        result = transcribe_chunked(path)
        print(result.merged_text)
    """
    rec = Recorder(samplerate=samplerate, channels=channels, device=device)
    saved = rec.record(duration=duration, path=path, show_level=show_level)
    if saved is None:
        raise RuntimeError("Nothing was recorded.")
    return saved


def list_devices() -> None:
    """Print available audio input/output devices to stdout."""
    _require_sound()
    print(sd.query_devices())


# ── internal helpers ─────────────────────────────────────────────────────────


def _print_level(frames: list[np.ndarray]) -> None:
    if not frames:
        return
    rms = float(np.sqrt(np.mean(frames[-1] ** 2)))
    filled = min(int(rms * 80), 30)
    bar = ("█" * filled).ljust(30, "░")
    print(f"\r  [{bar}]  {rms:.4f}", end="", flush=True)
