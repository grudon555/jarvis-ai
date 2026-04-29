from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    cloud_model: str = "claude-sonnet-4-6"
    router_threshold: int = 3

    # Voice output (ElevenLabs)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    # Voice input (faster-whisper)
    whisper_model: str = "base"
    whisper_language: str = "de"

    # WhatsApp / Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = "+14155238886"   # Sandbox default
    whatsapp_authorized_numbers: str = ""           # comma-separated E.164, empty = allow all
    whatsapp_rate_limit: int = 20                   # max messages per minute per number

    # Telegram
    telegram_bot_token: str = ""

    # Webhook server
    server_host: str = "0.0.0.0"
    server_port: int = 8000


settings = Settings()
