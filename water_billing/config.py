from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

from water_billing.domain.rules import BillingError


@dataclass
class AppConfig:
    data_root: Path
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    use_tls: bool
    treasurer_email: str


def _warn_if_env_tracked() -> None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            capture_output=True,
        )
        if result.returncode == 0:
            import sys
            print(
                "VAROITUS: .env-tiedosto on git-seurannassa. "
                "Lisää se .gitignore-tiedostoon heti.",
                file=sys.stderr,
            )
    except FileNotFoundError:
        pass


def load_config(data_root_override: Optional[Path] = None) -> AppConfig:
    load_dotenv()
    _warn_if_env_tracked()

    data_root_str = os.getenv("DATA_ROOT", "")
    if data_root_override is not None:
        data_root = data_root_override
    elif data_root_str:
        data_root = Path(data_root_str)
    else:
        data_root = Path.cwd()

    smtp_port_str = os.getenv("SMTP_PORT", "587")
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    return AppConfig(
        data_root=data_root,
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(smtp_port_str),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        use_tls=use_tls,
        treasurer_email=os.getenv("TREASURER_EMAIL", ""),
    )


def require_smtp_config(config: AppConfig) -> None:
    missing = [
        field
        for field in ("smtp_host", "smtp_user", "smtp_password")
        if not getattr(config, field)
    ]
    if missing:
        raise BillingError("SMTP-asetukset puuttuvat .env-tiedostosta")
