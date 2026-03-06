from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYNCER_", env_file=".env", extra="ignore")

    cache_dir: Path = Path.home() / ".syncer"
    db_path: Path = Path.home() / ".syncer" / "cache.db"
    whisperx_model: str = "base"  # or large-v2 for quality
    whisperx_device: str = "cpu"
    whisperx_compute_type: str = "float32"
    demucs_model: str = "htdemucs"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    temp_dir: Path | None = None  # uses system temp if None
    max_song_duration: int = 600  # 10 min hard limit
