from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import json
import os
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parent.parent  # …/backend/

def _load_yaml_config() -> None:
    """Load config.yaml if present. Priority: os.environ (Docker -e flags) > config.yaml > defaults."""
    try:
        import yaml
        import json as _json
    except ImportError:
        return

    for candidate in [_BACKEND_DIR / "config.yaml", _BACKEND_DIR.parent / "config.yaml"]:
        if candidate.exists():
            data = yaml.safe_load(candidate.read_text()) or {}
            for k, v in data.items():
                env_key = k.upper()
                if env_key not in os.environ and v is not None and str(v).strip() != "":
                    os.environ[env_key] = _json.dumps(v) if isinstance(v, list) else str(v)
            break


_load_yaml_config()


class Settings(BaseSettings):
    model_config = SettingsConfigDict()
    litellm_url: str = "http://localhost:4000"
    litellm_master_key: str

    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid email profile"
    oidc_groups_claim: str = "groups"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    key_max_budget: Optional[float] = None
    key_budget_duration: Optional[str] = None
    key_models: str = "[]"
    key_tpm_limit: Optional[int] = None
    key_rpm_limit: Optional[int] = None
    key_duration: Optional[str] = None
    key_team_id: Optional[str] = None

    root_url: str = "http://localhost"
    cors_origins: str = "http://localhost,http://localhost:5173,http://localhost:3000"

    local_auth_username: Optional[str] = None
    local_auth_password: Optional[str] = None
    local_users_enabled: bool = True
    local_users_db_path: str = "data/litegate.db"
    admin_emails: str = ""
    admin_groups: str = ""
    management_api_key: Optional[str] = None

    support_ticket_url: str = ""
    logo_url: str = ""
    litellm_ui_url: str = ""

    @property
    def local_auth_enabled(self) -> bool:
        return bool(self.local_auth_username and self.local_auth_password)

    @property
    def admin_emails_set(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    def is_admin_email(self, email: str) -> bool:
        return bool(email) and email.strip().lower() in self.admin_emails_set

    @property
    def admin_groups_set(self) -> set[str]:
        return {group.strip().casefold() for group in self.admin_groups.split(",") if group.strip()}

    def is_admin_identity(self, email: str, claims: dict) -> bool:
        if self.is_admin_email(email):
            return True
        value: object = claims
        for segment in self.oidc_groups_claim.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(segment)
        if isinstance(value, str):
            groups = {value.casefold()}
        elif isinstance(value, list):
            groups = {str(group).strip().casefold() for group in value if str(group).strip()}
        else:
            groups = set()
        return bool(groups & self.admin_groups_set)

    @property
    def key_models_list(self) -> List[str]:
        try:
            parsed = json.loads(self.key_models)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
