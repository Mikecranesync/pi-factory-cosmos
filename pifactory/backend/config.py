"""Pi-Factory configuration — loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Central configuration loaded from env vars / .env file."""

    # NVIDIA Cosmos NIM
    nvidia_api_key: str = ""
    cosmos_model: str = "nvidia/cosmos-reason2-8b"
    cosmos_fallback: str = "meta/llama-3.1-70b-instruct"
    cosmos_base_url: str = "https://integrate.api.nvidia.com/v1"
    cosmos_temperature: float = 0.6
    cosmos_top_p: float = 0.95
    cosmos_max_tokens: int = 4096

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    allowed_chat_ids: list[str] = field(default_factory=list)

    # Hardware
    anybus_hardware: bool = False

    # Video
    video_source: str = ""

    # VFD Modbus TCP
    vfd_host: str = ""
    vfd_port: int = 502
    vfd_slave_id: int = 1
    vfd_poll_interval_sec: float = 1.0
    vfd_register_map: str = ""
    vfd_brand: str = "generic"

    # Server
    port: int = 8080
    host: str = "0.0.0.0"

    @classmethod
    def from_env(cls) -> Config:
        """Build Config from environment variables."""
        allowed_raw = os.getenv("ALLOWED_CHAT_IDS", "")
        allowed = [c.strip() for c in allowed_raw.split(",") if c.strip()]

        return cls(
            nvidia_api_key=os.getenv("NVIDIA_COSMOS_API_KEY", ""),
            cosmos_model=os.getenv("COSMOS_MODEL", "nvidia/cosmos-reason2-8b"),
            cosmos_fallback=os.getenv("COSMOS_FALLBACK", "meta/llama-3.1-70b-instruct"),
            cosmos_base_url=os.getenv("COSMOS_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            cosmos_temperature=float(os.getenv("COSMOS_TEMPERATURE", "0.6")),
            cosmos_top_p=float(os.getenv("COSMOS_TOP_P", "0.95")),
            cosmos_max_tokens=int(os.getenv("COSMOS_MAX_TOKENS", "4096")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            allowed_chat_ids=allowed,
            anybus_hardware=os.getenv("ANYBUS_HARDWARE", "false").lower() == "true",
            video_source=os.getenv("VIDEO_SOURCE", ""),
            vfd_host=os.getenv("VFD_HOST", ""),
            vfd_port=int(os.getenv("VFD_PORT", "502")),
            vfd_slave_id=int(os.getenv("VFD_SLAVE_ID", "1")),
            vfd_poll_interval_sec=float(os.getenv("VFD_POLL_INTERVAL_SEC", "1.0")),
            vfd_register_map=os.getenv("VFD_REGISTER_MAP", ""),
            vfd_brand=os.getenv("VFD_BRAND", "generic"),
            port=int(os.getenv("PORT", "8080")),
            host=os.getenv("HOST", "0.0.0.0"),
        )

    @property
    def has_nim_key(self) -> bool:
        return bool(self.nvidia_api_key)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def has_vfd(self) -> bool:
        return bool(self.vfd_host)
