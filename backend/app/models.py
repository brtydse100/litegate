from pydantic import BaseModel
from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Any, Literal
from datetime import datetime


class CurrentUser(BaseModel):
    user_id: str
    email: str
    role: str = "user"
    auth_source: str = "sso"
    team_ids: List[str] = Field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class KeyInfo(BaseModel):
    token: Optional[str] = None
    key_alias: Optional[str] = None
    spend: float = 0.0
    max_budget: Optional[float] = None
    expires: Optional[datetime] = None
    models: List[str] = Field(default_factory=list)
    tpm_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    budget_duration: Optional[str] = None
    created_at: Optional[datetime] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None


class KeyCreateResponse(BaseModel):
    key: str
    user_id: str
    expires: Optional[datetime] = None


class SpendLog(BaseModel):
    request_id: Optional[str] = None
    call_type: Optional[str] = None
    spend: float = 0.0
    total_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    model: Optional[str] = None
    cache_hit: Optional[str] = None


class SpendSummary(BaseModel):
    total_spend: float
    total_requests: int
    total_tokens: int
    spend_by_model: dict


class LocalUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)
    role: str = "user"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"user", "admin"}:
            raise ValueError("Role must be user or admin")
        return value


class LocalUserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, min_length=3, max_length=254)
    password: Optional[str] = Field(default=None, min_length=10, max_length=256)
    role: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("role")
    @classmethod
    def validate_optional_role(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"user", "admin"}:
            raise ValueError("Role must be user or admin")
        return value


class LocalUserInfo(BaseModel):
    username: str
    user_id: str
    email: str
    role: str
    active: bool
    created_at: str
    updated_at: str


class KeySettingsUpdate(BaseModel):
    key_alias: Optional[str] = Field(default=None, max_length=128)
    models: Optional[List[str]] = None
    max_budget: Optional[float] = Field(default=None, ge=0)
    budget_duration: Optional[str] = Field(default=None, max_length=32)
    tpm_limit: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    duration: Optional[str] = Field(default=None, max_length=32)
    blocked: Optional[bool] = None

    @field_validator("models")
    @classmethod
    def validate_models(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        cleaned = list(dict.fromkeys(model.strip() for model in value if model.strip()))
        if len(cleaned) > 100:
            raise ValueError("At most 100 models may be supplied")
        return cleaned

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one setting is required")
        return self


class BulkKeyUpdateRequest(BaseModel):
    keys: List[str] = Field(min_length=1, max_length=5000)
    settings: KeySettingsUpdate

    @field_validator("keys")
    @classmethod
    def validate_keys(cls, value: List[str]) -> List[str]:
        cleaned = list(dict.fromkeys(key.strip() for key in value if key.strip()))
        if not cleaned:
            raise ValueError("At least one key is required")
        return cleaned


class ApiKeyCreateRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    email: Optional[str] = Field(default=None, max_length=254)


class TeamCreateRequest(BaseModel):
    team_alias: str = Field(min_length=1, max_length=128)
    team_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    models: List[str] = Field(default_factory=list)
    max_budget: Optional[float] = Field(default=None, ge=0)
    budget_duration: Optional[str] = Field(default=None, max_length=32)
    tpm_limit: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    blocked: bool = False

    @field_validator("team_alias", "team_id", mode="before")
    @classmethod
    def clean_team_names(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else value

    @field_validator("models")
    @classmethod
    def clean_team_models(cls, value: List[str]) -> List[str]:
        cleaned = list(dict.fromkeys(model.strip() for model in value if model.strip()))
        if len(cleaned) > 100:
            raise ValueError("At most 100 models may be supplied")
        return cleaned


class TeamUpdateRequest(BaseModel):
    team_alias: Optional[str] = Field(default=None, min_length=1, max_length=128)
    models: Optional[List[str]] = None
    max_budget: Optional[float] = Field(default=None, ge=0)
    budget_duration: Optional[str] = Field(default=None, max_length=32)
    tpm_limit: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    blocked: Optional[bool] = None

    @field_validator("team_alias", mode="before")
    @classmethod
    def clean_team_alias(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else value

    @field_validator("models")
    @classmethod
    def clean_optional_team_models(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        cleaned = list(dict.fromkeys(model.strip() for model in value if model.strip()))
        if len(cleaned) > 100:
            raise ValueError("At most 100 models may be supplied")
        return cleaned

    @model_validator(mode="after")
    def require_team_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one team setting is required")
        return self


class TeamMemberMoveRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    destination_team_id: str = Field(min_length=1, max_length=128)
    confirm_policy_change: Literal[True]

    @field_validator("user_id", "destination_team_id", mode="before")
    @classmethod
    def clean_member_move_ids(cls, value: str) -> str:
        return value.strip()
