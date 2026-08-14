from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass
class RequiredChannel:
    chat_id: str  # @username или -100...
    title: str
    invite_link: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",  # Перенесли сюда из class Config
    )

    bot_token: str
    owner_id: int

    database_url: str

    required_channels_raw: str = ""
    support_group_id: int
    support_topic_id: int | None = None

    start_photo_url: str = "/root/Bot/img/start.jpg"
    agreement_photo_url: str = "/root/Bot/img/rules.jpg"
    questionnaire_nickname_photo_url: str = "/root/Bot/img/name.jpg"
    questionnaire_about_photo_url: str = "/root/Bot/img/about.jpg"
    questionnaire_hobbies_photo_url: str = "/root/Bot/img/hobbies.jpg"
    stats_photo_url: str = "/root/Bot/img/stats.jpg"
    dialogs_photo_url: str = "/root/Bot/img/history.jpg"
    online_photo_url: str = "/root/Bot/img/online.jpg"
    reviews_photo_url: str = "/root/Bot/img/reviews.jpg"

    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen-2.5-72b-instruct"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    miniapp_secret: str = "change-me"
    miniapp_host: str = "0.0.0.0"
    miniapp_port: int = 8080

    online_timeout_minutes: int = 5

    # === Ссылки на фотографии/баннеры (необязательные — если не заполнены,
    # соответствующее сообщение/страница просто не показывает картинку) ===
    start_photo_url: str = ""
    agreement_photo_url: str = ""
    questionnaire_nickname_photo_url: str = ""
    questionnaire_about_photo_url: str = ""
    questionnaire_hobbies_photo_url: str = ""
    stats_photo_url: str = ""
    dialogs_photo_url: str = ""
    online_photo_url: str = ""
    reviews_photo_url: str = ""

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

