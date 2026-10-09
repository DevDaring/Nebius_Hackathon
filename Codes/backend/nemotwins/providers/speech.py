"""Speech (ASR / TTS): not available in NemoTwins.

NemoTwins calls models only through Nebius Token Factory, which offers no speech model, so both
functions always raise ``SpeechUnavailable``. The API answers 501 and the Talk page is text-only. When a verified NVIDIA
speech route on Nebius exists (``NVIDIA_SPEECH_ENABLED``), implement it here; never add a fallback
to another provider.
"""

from __future__ import annotations

REASON = "No speech (ASR/TTS) model is available on Nebius Token Factory; voice is disabled."


class SpeechUnavailable(RuntimeError):
    """Speech is not available (no Token Factory speech model)."""


def stt(audio: bytes, lang: str, filename: str = "speech.webm", mime: str = "audio/webm") -> tuple[str, str]:
    raise SpeechUnavailable(REASON)


def tts(text: str, lang: str) -> tuple[bytes, str, str]:
    raise SpeechUnavailable(REASON)


def status() -> dict:
    return {"enabled": False, "reason": REASON}
