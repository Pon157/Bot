from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass
class RequiredChannel:
    chat_id: str  # @username или -100...
    title: str
    invite_link: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    owner_id: int

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    required_channels_raw: str = ""
    support_group_id: int
    support_topic_id: int | None = None

    channel_url: str = ""
    anketa_bot_url: str = ""
    reviews_webapp_url: str = ""
    online_webapp_url: str = ""
    profile_webapp_url: str = ""
    dialogs_webapp_url: str = ""

    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen-2.5-72b-instruct"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    miniapp_secret: str = "change-me"
    miniapp_host: str = "0.0.0.0"
    miniapp_port: int = 8080

    online_timeout_minutes: int = 5

    class Config:
        env_prefix = ""

    @property
    def required_channels(self) -> list[RequiredChannel]:
        result: list[RequiredChannel] = []
        if not self.required_channels_raw:
            return result
        for part in self.required_channels_raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "|" in part:
                chat_id, title = part.split("|", 1)
            else:
                chat_id, title = part, part
            result.append(RequiredChannel(chat_id=chat_id.strip(), title=title.strip()))
        return result


settings = Settings()  # type: ignore[call-arg]
