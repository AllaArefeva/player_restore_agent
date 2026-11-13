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

"""Unit tests for the deterministic 10-rule restoration engine."""

from app.models import (
    AttributePanel,
    PlayerSave,
    QuotaStatus,
    normalize_length_to_inches,
)
from app.rule_engine import validate_restoration_rules


def create_base_source_save() -> PlayerSave:
    return PlayerSave(
        save_id="save_original_123",
        player_id="2K-USR-984210",
        slot=1,
        generation="GEN_5",
        ovr=95,
        position="PG",
        height="6'6\"",
        weight=200,
        wingspan="6'11\"",
        archetype="2-Way Floor-Spacing Slasher",
        template_id=0,
        has_upgraded_attributes=True,
        is_rebirth=False,
        status="orphaned_cloud_only",
        created_at="2026-08-01T12:00:00Z",
        last_updated="2026-08-15T18:00:00Z",
        attributes=AttributePanel(
            as_created={"three_point": 90, "driving_dunk": 85, "speed": 88},
            current={"three_point": 95, "driving_dunk": 90, "speed": 88},
        ),
    )


def create_base_placeholder_save() -> PlayerSave:
    ts = "2026-08-18T20:00:00Z"
    return PlayerSave(
        save_id="save_placeholder_456",
        player_id="2K-USR-984210",
        slot=3,
        generation="GEN_5",
        ovr=60,
        position="PG",
        height="6'6\"",
        weight=200,
        wingspan="6'11\"",
        archetype="2-Way Floor-Spacing Slasher",
        template_id=0,
        has_upgraded_attributes=False,
        is_rebirth=False,
        badge_points=0,
        xp_progress=0,
        xp_points=0,
        has_build_specialization=False,
        quest_unlocks=[],
        status="active",
        created_at=ts,
        last_updated=ts,
        vc_history_count=0,
        game_history_count=0,
        attributes=AttributePanel(
            as_created={"three_point": 90, "driving_dunk": 85, "speed": 88},
            current={"three_point": 90, "driving_dunk": 85, "speed": 88},
        ),
    )


def test_happy_path_validation():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    quota = QuotaStatus(
        player_id="2K-USR-984210",
        lifetime_restorations_used=2,
        lifetime_limit=10,
        trailing_30_days_used=1,
        trailing_30_days_limit=5,
    )
    result = validate_restoration_rules(source, placeholder, quota)
    assert result.valid is True
    assert len(result.failures) == 0
    assert all(status == "PASSED" for status in result.checked_rules.values())


def test_rule_1_ovr_and_progress_failure():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.ovr = 68
    placeholder.has_upgraded_attributes = True

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_1_ovr_and_progress"] == "FAILED"
    assert any("Placeholder OVR must be 60" in f for f in result.failures)


def test_rule_2_wingspan_and_height_mismatch():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.wingspan = "6'10\""
    placeholder.height = "6'5\""

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_2_physical_match"] == "FAILED"
    assert any("Wingspan mismatch" in f for f in result.failures)
    assert any("Height mismatch" in f for f in result.failures)


def test_rule_3_attribute_mismatch():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.attributes.as_created["three_point"] = 85  # Original was 90

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_3_attribute_match"] == "FAILED"
    assert any(
        "Attribute mismatch against as-created baseline" in f for f in result.failures
    )


def test_rule_4_rebirth_detection():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.badge_points = 17250  # Gen 5 rebirth flag

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_4_rebirth_check"] == "FAILED"
    assert any("17,250 badge points" in f for f in result.failures)


def test_rule_5_template_mismatch():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.template_id = 99  # Source was 0

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_5_template_conformity"] == "FAILED"
    assert any("Template mismatch" in f for f in result.failures)


def test_rule_6_build_specialization():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.quest_unlocks = ["2K26.UNLOCKS.BUILD_SPECIALIZATION"]

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_6_build_specialization"] == "FAILED"
    assert any("2K26.UNLOCKS.BUILD_SPECIALIZATION" in f for f in result.failures)


def test_rule_7_timestamp_mismatch():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.last_updated = "2026-08-18T20:45:00Z"  # Different from created_at

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_7_timestamp_consistency"] == "FAILED"
    assert any("Timestamp mismatch" in f for f in result.failures)


def test_rule_8_vc_history():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.vc_history_count = 2

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_8_vc_history"] == "FAILED"
    assert any("VC transaction ledger" in f for f in result.failures)


def test_rule_9_game_history():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    placeholder.game_history_count = 1

    result = validate_restoration_rules(source, placeholder)
    assert result.valid is False
    assert result.checked_rules["rule_9_game_history"] == "FAILED"
    assert any("game history rows" in f for f in result.failures)


def test_rule_10_quota_limit():
    source = create_base_source_save()
    placeholder = create_base_placeholder_save()
    quota = QuotaStatus(
        player_id="2K-USR-984210",
        lifetime_restorations_used=10,  # Limit is 10
        lifetime_limit=10,
        trailing_30_days_used=1,
        trailing_30_days_limit=5,
    )

    result = validate_restoration_rules(source, placeholder, quota)
    assert result.valid is False
    assert result.checked_rules["rule_10_restoration_quota"] == "FAILED"
    assert any("Lifetime restoration limit reached" in f for f in result.failures)


def test_length_normalization():
    assert normalize_length_to_inches("6'6\"") == 78
    assert normalize_length_to_inches("6'6") == 78
    assert normalize_length_to_inches("6ft 6in") == 78
    assert normalize_length_to_inches("78") == 78
    assert normalize_length_to_inches("6'11\"") == 83
    assert normalize_length_to_inches("6'10\"") == 82
