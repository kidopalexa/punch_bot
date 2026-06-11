"""
voice.py — розпізнавання голосу через Groq Whisper API (безкоштовно).
"""
import os
import tempfile
import aiohttp

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


async def transcribe_voice(file_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Повертає розпізнаний текст або порожній рядок при помилці."""
    if not GROQ_API_KEY:
        return ""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    data = aiohttp.FormData()
    data.add_field("file", file_bytes, filename=filename, content_type="audio/ogg")
    data.add_field("model", "whisper-large-v3")
    data.add_field("language", "uk")
    data.add_field("response_format", "text")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return (await resp.text()).strip()
    except Exception:
        pass
    return ""
