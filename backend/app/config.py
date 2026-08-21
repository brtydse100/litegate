from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from typing import Optional, List
import json
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parent.parent  # …/backend/

def _load_yaml_config() -> dict:
    """Read the first project config file without mutating process state."""
    try:
        import yaml
    except ImportError:
        return {}

    for candidate in [_BACKEND_DIR / "config.yaml", _BACKEND_DIR.parent / "config.yaml"]:
        if candidate.exists():
            data = yaml.safe_load(candidate.read_text()) or {}
            if not isinstance(data, dict):
                raise ValueError(f"Configuration root must be a mapping: {candidate}")
            return {key: value for key, value in data.items() if value is not None}
    return {}


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source with environment variables taking precedence."""

    def get_field_value(self, field: FieldInfo, field_name: str):
        data = _load_yaml_config()
        value = data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict:
        data = _load_yaml_config()
        if isinstance(data.get("key_models"), list):
            data["key_models"] = json.dumps(data["key_models"])
        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    litellm_url: str = "http://localhost:4000"
    litellm_master_key: str

    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid email profile"
    oidc_groups_claim: str = "groups"
    oidc_group_team_mapping: dict[str, str | list[str]] = Field(default_factory=dict)
    oidc_require_team_mapping: bool = False

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

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

    def oidc_groups(self, claims: dict) -> list[str]:
        """Read the configured (optionally dotted) OIDC groups claim."""
        value: object = claims
        for segment in self.oidc_groups_claim.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(segment)

        raw_groups = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        groups: list[str] = []
        seen: set[str] = set()
        for raw_group in raw_groups:
            group = str(raw_group).strip()
            normalized = group.casefold()
            if group and normalized not in seen:
                seen.add(normalized)
                groups.append(group)
        return groups

    def mapped_team_ids(self, claims: dict) -> list[str]:
        """Resolve SSO groups to team IDs in mapping declaration order."""
        claimed_groups = {group.casefold() for group in self.oidc_groups(claims)}
        team_ids: list[str] = []
        seen: set[str] = set()
        for configured_group, configured_team_ids in self.oidc_group_team_mapping.items():
            if configured_group.strip().casefold() not in claimed_groups:
                continue
            values = (
                [configured_team_ids]
                if isinstance(configured_team_ids, str)
                else configured_team_ids
            )
            for raw_team_id in values:
                team_id = raw_team_id.strip()
                if team_id and team_id not in seen:
                    seen.add(team_id)
                    team_ids.append(team_id)
        return team_ids

    def is_admin_identity(self, email: str, claims: dict) -> bool:
        if self.is_admin_email(email):
            return True
        groups = {group.casefold() for group in self.oidc_groups(claims)}
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
