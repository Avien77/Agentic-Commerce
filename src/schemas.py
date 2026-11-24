"""Shared Pydantic schemas for listings, queries, and evaluations."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Condition = Literal["NM", "LP", "MP", "HP", "DMG", "unknown"]
Variant = Literal["normal", "holo", "reverse", "1st edition", "unknown"]
DeliveryType = Literal["in_person", "shipping", "unknown"]
Persona = Literal["budget_parent", "serious_collector", "cautious_buyer"]


class CardListing(BaseModel):
    """Anonymized, structured single-card listing schema (Section 4 & 14)."""

    listing_id: str
    raw_title: str
    raw_description: str = ""
    price: float = Field(ge=0.0)
    location_city: str = ""
    delivery_type: DeliveryType = "unknown"
    has_clear_photo: bool = True

    # Extracted card identity fields
    card_name: str = "unknown"
    set_code: str = "unknown"
    number: str = "unknown"
    variant: Variant = "unknown"
    condition: Condition = "unknown"
    graded: bool = False
    grade: Optional[str] = None
    language: str = "en"
    is_lot: bool = False
    shipping: Optional[float] = Field(default=None, ge=0.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Evaluation metadata (traps & decoys)
    synthetic: bool = False
    split: Optional[Literal["dev", "test"]] = None
    label: Optional[Literal["clean", "trap", "decoy"]] = None
    label_reason: Optional[str] = None


class ParsedQuery(BaseModel):
    """Structured buyer request produced by the Consumer Agent in INTENT."""

    card_name: Optional[str] = None
    set_code: Optional[str] = None
    budget: Optional[float] = Field(default=None, gt=0.0)
    min_condition: Optional[Condition] = None
    excluded_variants: list[str] = Field(default_factory=list)
    persona: Persona = "cautious_buyer"
    is_consultative: bool = False


class LandedCostResult(BaseModel):
    """Output of the deterministic landed cost tool."""

    price: float
    shipping: float
    tax: float
    total: float
    shipping_estimated: bool


class EvaluatedListing(BaseModel):
    """Listing enriched with Merchant reflection and Consumer scoring."""

    listing: CardListing
    market_price: Optional[float] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_reasons: list[str] = Field(default_factory=list)
    warning: Optional[str] = None
    landed_cost: Optional[LandedCostResult] = None
    utility_score: Optional[float] = None
    rejected: bool = False
    rejection_reason: Optional[str] = None
