"""读取项目配置，保持环境变量优先，不在代码中保存 API 密钥。"""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    """页面运行需要的最少配置。"""

    database_path: Path
    github_token: str


def load_settings() -> Settings:
    """相对数据库路径以项目根目录为基准，避免启动位置改变数据位置。"""
    load_dotenv(PROJECT_ROOT / '.env', override=False)
    path = Path(os.getenv('AI_RADAR_DB_PATH', 'data/hotspots.sqlite3')).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return Settings(database_path=path, github_token=os.getenv('GITHUB_TOKEN', '').strip())
