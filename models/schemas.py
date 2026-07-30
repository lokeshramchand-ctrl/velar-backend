from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CoreModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class User(CoreModel):
    """Persisted shape of a `users` document. `hashed_password` never leaves
    this model - API responses use `UserPublic` instead (see below)."""
    id: str | None = Field(alias="_id", default=None)
    email: EmailStr
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserPublic(BaseModel):
    """Safe, external-facing view of a User - deliberately a separate model
    (not User with a field excluded) so a future field added to User can
    never leak into a response by accident."""
    id: str
    email: EmailStr
    is_active: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        # Prevents "Foo@x.com" and "foo@x.com" from registering as two
        # distinct accounts against the case-sensitive unique index on email.
        return v.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=1024)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=1024)

class Transaction(CoreModel):
    id: str | None = Field(alias="_id", default=None)
    raw_text: str
    merchant: str | None = None
    amount: float
    category: str | None = None
    user_id: str = "system_user"
    is_mock: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Feedback(CoreModel):
    id: str | None = Field(alias="_id", default=None)
    transaction_id: str
    merchant_name: str | None = None
    prediction: str
    corrected_category: str
    confidence: float
    is_correction: bool = False
    user_id: str = "system_user"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CategorizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Raw transaction SMS or bank statement text")

class CategorizeResponse(BaseModel):
    merchant: str
    category: str
    confidence: float
    transaction_id: str | None = None

class ResolutionResult(BaseModel):
    raw_text: str
    cleaned_text: str
    canonical_merchant: str
    confidence: float
    is_resolved: bool
    resolution_method: str = Field(description="exact_alias, substring, or none")


class MemoryState(str, Enum):
    EPHEMERAL = "EPHEMERAL"
    TEMPORARY = "TEMPORARY"
    PERMANENT = "PERMANENT"
    ARCHIVED = "ARCHIVED"

class MerchantProfile(BaseModel):
    id: str | None = Field(alias="_id", default=None)
    canonical_name: str
    display_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    entity_type: str = "Unknown"  # e.g., "Individual", "Business"

    # Phase 4 Core Variables
    memory_state: MemoryState = MemoryState.EPHEMERAL
    frequency: int = 1
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))

    notes: str | None = None
    confidence: float = 0.0
    category: str | None = None
    subcategory: str | None = None



class TransactionCategory(str, Enum):
    FOOD = "Food"
    TRAVEL = "Travel"
    ENTERTAINMENT = "Entertainment"
    BILLS = "Bills"
    FRIENDS = "Friends"
    EDUCATION = "Education"
    HEALTHCARE = "Healthcare"
    SUBSCRIPTION = "Subscription"
    SHOPPING = "Shopping"
    UTILITY = "Utility"
    UNKNOWN = "Unknown"

class ConfidenceEvaluation(BaseModel):
    raw_category: str
    final_category: TransactionCategory
    confidence: float
    is_hallucination_risk: bool
    calibration_applied: str

class BehaviorPattern(BaseModel):
    id: str | None = Field(alias="_id", default=None)
    merchant_name: str  # Can be a resolved name or an "Unknown" entity string

    # Statistical Amount Metrics
    avg_amount: float
    median_amount: float
    variance: float
    std_dev: float

    # Temporal & Frequency Metrics
    preferred_hour: int
    time_bucket_distribution: dict[str, float]  # e.g., {"morning": 0.7, "night": 0.3}
    weekday_distribution: list[float]          # Length 7 array representing normalized frequency per day
    daily_frequency: float                     # Average number of times seen per day
    weekly_frequency: float                    # Average number of times seen per week

    # Advanced Intelligence Metrics
    periodicity_score: float                   # 0.0 (highly random) to 1.0 (perfectly predictable interval)
    entropy_score: float                       # Measures predictability of spending amounts
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
