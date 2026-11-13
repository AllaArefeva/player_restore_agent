# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Domain models and schemas for MyPlayer Restoration Agent."""

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def normalize_length_to_inches(length_str: str) -> int | None:
    """Normalizes length strings like 6'6, 6'6\", 6ft 6in, 78, 78in into integer inches."""
    if not length_str:
        return None
    cleaned = length_str.strip().lower()
    # Match 6'6, 6'6", 6ft 6in, 6ft 6, 6 ft 6 in
    match = re.match(r"^(\d+)\s*(?:'|ft|feet)\s*(\d+)?\s*(?:\"|in|inches)?$", cleaned)
    if match:
        feet = int(match.group(1))
        inches = int(match.group(2)) if match.group(2) else 0
        return feet * 12 + inches
    # Match raw inches: 78, 78", 78in
    match_inches = re.match(r"^(\d+)\s*(?:\"|in|inches)?$", cleaned)
    if match_inches:
        return int(match_inches.group(1))
    return None


def format_inches_to_display(inches: int) -> str:
    """Formats inches into 6'6\" display string."""
    feet = inches // 12
    rem_inches = inches % 12
    return f"{feet}'{rem_inches}\""


class AttributePanel(BaseModel):
    """The 25-attribute panel distinguishing as-created baseline from current (post-Cap Breakers)."""

    as_created: dict[str, int] = Field(
        default_factory=dict,
        description="Attributes at initial creation time (pre-Cap Breaker baseline).",
    )
    current: dict[str, int] = Field(
        default_factory=dict,
        description="Current attribute values including any earned Cap Breakers.",
    )


class PlayerSave(BaseModel):
    """Save record representation matching 2K AdminWeb schema."""

    save_id: str
    player_id: str
    slot: int = 1
    generation: Literal["GEN_4", "GEN_5"] = "GEN_5"
    ovr: int = 60
    position: str = "PG"
    height: str = "6'6\""
    weight: int = 200  # in pounds
    wingspan: str = "6'11\""
    archetype: str = "2-Way Floor-Spacing Slasher"
    template_id: int = 0
    has_upgraded_attributes: bool = False
    is_rebirth: bool = False
    badge_points: int = 0  # 17,250 points on Gen 5 indicates rebirth
    xp_progress: int = 0
    xp_points: int = 0
    has_build_specialization: bool = False
    quest_unlocks: list[str] = Field(default_factory=list)
    status: Literal["active", "orphaned_cloud_only", "deleted", "locked"] = "active"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    vc_history_count: int = 0
    game_history_count: int = 0
    attributes: AttributePanel = Field(default_factory=AttributePanel)


class QuotaStatus(BaseModel):
    """Player restoration eligibility and quota status from BigQuery."""

    player_id: str
    generation: Literal["GEN_4", "GEN_5"] = "GEN_5"
    lifetime_restorations_used: int = 0
    lifetime_limit: int = 10
    trailing_30_days_used: int = 0
    trailing_30_days_limit: int = 5
    is_eligible: bool = True
    ineligibility_reason: str | None = None


class ValidationResult(BaseModel):
    """Deterministic server-side pre-check result for POST /restorations:validate."""

    valid: bool
    failures: list[str] = Field(default_factory=list)
    checked_rules: dict[str, str] = Field(default_factory=dict)


class RestorationCaseArtifact(BaseModel):
    """Immutable case artifact staged for Human CS 1-click review."""

    ticket_id: str
    player_id: str
    generation: str
    source_save_id: str
    target_placeholder_id: str
    target_ovr: int
    vc_delta: int
    validation_result: ValidationResult
    status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED"] = "PENDING_REVIEW"
    recommendation: str = "APPROVE"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sla_hours: int = 48


class RestorationExecutionPayload(BaseModel):
    """Payload sent to downstream 2K backend for POST /restorations."""

    operation: str = "CLONE_SAVE_STATE"
    ticket_id: str
    actor_id: str
    idempotency_key: str
    player_id: str
    generation: str
    source_save_id: str
    target_placeholder_id: str
    target_ovr: int
    vc_refund_amount: int
    reason_code: str = "ACCIDENTAL_UPGRADE_RESTORE"
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
