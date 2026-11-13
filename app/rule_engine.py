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

"""Deterministic server-side rule engine implementing all 10 restoration checks."""

from app.models import (
    PlayerSave,
    QuotaStatus,
    ValidationResult,
    format_inches_to_display,
    normalize_length_to_inches,
)


def validate_restoration_rules(
    source_save: PlayerSave,
    target_placeholder: PlayerSave,
    quota_status: QuotaStatus | None = None,
) -> ValidationResult:
    """Evaluates all 10 validation rules atomically.

    Returns:
        ValidationResult containing overall pass/fail boolean, structured
        list of failure strings, and individual rule status breakdown.
    """
    failures: list[str] = []
    checked_rules: dict[str, str] = {}

    # Rule 1: OVR & Progression Check
    r1_failed = False
    if target_placeholder.ovr != 60 or target_placeholder.has_upgraded_attributes:
        failures.append(
            f"Placeholder OVR must be 60 with no attribute upgrades (found {target_placeholder.ovr} OVR, "
            f"has_upgraded_attributes={target_placeholder.has_upgraded_attributes})."
        )
        r1_failed = True
    if source_save.ovr <= 65:
        failures.append(
            f"Original build OVR is {source_save.ovr}; restorations require original build above 65 OVR."
        )
        r1_failed = True
    checked_rules["rule_1_ovr_and_progress"] = "FAILED" if r1_failed else "PASSED"

    # Rule 2: Physical & Geometry Match
    r2_failed = False
    if (
        source_save.position.strip().upper()
        != target_placeholder.position.strip().upper()
    ):
        failures.append(
            f"Position mismatch: Target placeholder has {target_placeholder.position} vs Original {source_save.position}."
        )
        r2_failed = True

    src_height_in = normalize_length_to_inches(source_save.height)
    tgt_height_in = normalize_length_to_inches(target_placeholder.height)
    if (
        src_height_in is not None
        and tgt_height_in is not None
        and src_height_in != tgt_height_in
    ):
        failures.append(
            f"Height mismatch: Target placeholder has {format_inches_to_display(tgt_height_in)} "
            f"vs Original {format_inches_to_display(src_height_in)}."
        )
        r2_failed = True

    if source_save.weight != target_placeholder.weight:
        failures.append(
            f"Weight mismatch: Target placeholder has {target_placeholder.weight} lbs vs Original {source_save.weight} lbs."
        )
        r2_failed = True

    src_wingspan_in = normalize_length_to_inches(source_save.wingspan)
    tgt_wingspan_in = normalize_length_to_inches(target_placeholder.wingspan)
    if (
        src_wingspan_in is not None
        and tgt_wingspan_in is not None
        and src_wingspan_in != tgt_wingspan_in
    ):
        failures.append(
            f"Wingspan mismatch: Target placeholder has {format_inches_to_display(tgt_wingspan_in)} "
            f"vs Original {format_inches_to_display(src_wingspan_in)}."
        )
        r2_failed = True

    if (
        source_save.archetype.strip().lower()
        != target_placeholder.archetype.strip().lower()
    ):
        failures.append(
            f"Archetype mismatch: Target placeholder has '{target_placeholder.archetype}' "
            f"vs Original '{source_save.archetype}'."
        )
        r2_failed = True

    checked_rules["rule_2_physical_match"] = "FAILED" if r2_failed else "PASSED"

    # Rule 3: As-Created Attribute Match (pre-Cap Breaker baseline)
    r3_failed = False
    if source_save.attributes and target_placeholder.attributes:
        src_attrs = source_save.attributes.as_created
        tgt_attrs = target_placeholder.attributes.as_created
        if src_attrs and tgt_attrs:
            mismatched_attrs = []
            for attr_name, src_val in src_attrs.items():
                if attr_name in tgt_attrs and tgt_attrs[attr_name] != src_val:
                    mismatched_attrs.append(
                        f"{attr_name} (target {tgt_attrs[attr_name]} vs original {src_val})"
                    )
            if mismatched_attrs:
                failures.append(
                    f"Attribute mismatch against as-created baseline: {', '.join(mismatched_attrs)}."
                )
                r3_failed = True
    checked_rules["rule_3_attribute_match"] = "FAILED" if r3_failed else "PASSED"

    # Rule 4: Rebirth Verification
    r4_failed = False
    if target_placeholder.is_rebirth:
        failures.append(
            "Placeholder is marked as Rebirth. Restorations require a non-rebirth save."
        )
        r4_failed = True
    if target_placeholder.generation == "GEN_4":
        if target_placeholder.xp_progress > 0 or target_placeholder.xp_points > 0:
            failures.append(
                "Placeholder on Gen 4 has XP progress/points. Fresh save must have zero XP."
            )
            r4_failed = True
    elif target_placeholder.generation == "GEN_5":
        if target_placeholder.badge_points == 17250:
            failures.append(
                "Placeholder on Gen 5 has 17,250 badge points, indicating an unauthorized Rebirth file."
            )
            r4_failed = True
    checked_rules["rule_4_rebirth_check"] = "FAILED" if r4_failed else "PASSED"

    # Rule 5: Template Conformity
    r5_failed = False
    if (
        target_placeholder.template_id != 0
        and target_placeholder.template_id != source_save.template_id
    ):
        failures.append(
            f"Template mismatch: Target template ID {target_placeholder.template_id} "
            f"does not match original template ID {source_save.template_id} (or 0)."
        )
        r5_failed = True
    checked_rules["rule_5_template_conformity"] = "FAILED" if r5_failed else "PASSED"

    # Rule 6: Build Specialization (2K26+)
    r6_failed = False
    if target_placeholder.has_build_specialization:
        failures.append(
            "Placeholder has Build Specialization active. Must be unspecialized."
        )
        r6_failed = True
    if "2K26.UNLOCKS.BUILD_SPECIALIZATION" in target_placeholder.quest_unlocks:
        failures.append(
            "Placeholder contains 2K26.UNLOCKS.BUILD_SPECIALIZATION in Quest Progress."
        )
        r6_failed = True
    checked_rules["rule_6_build_specialization"] = "FAILED" if r6_failed else "PASSED"

    # Rule 7: Timestamp Consistency
    r7_failed = False
    if target_placeholder.created_at != target_placeholder.last_updated:
        failures.append(
            f"Timestamp mismatch: Created at ({target_placeholder.created_at}) "
            f"does not equal Last Updated ({target_placeholder.last_updated})."
        )
        r7_failed = True
    checked_rules["rule_7_timestamp_consistency"] = "FAILED" if r7_failed else "PASSED"

    # Rule 8: VC History Cleanliness
    r8_failed = False
    if target_placeholder.vc_history_count > 0:
        failures.append(
            f"Placeholder has {target_placeholder.vc_history_count} VC transaction ledger entries. Must be 0."
        )
        r8_failed = True
    checked_rules["rule_8_vc_history"] = "FAILED" if r8_failed else "PASSED"

    # Rule 9: Game History Cleanliness
    r9_failed = False
    if target_placeholder.game_history_count > 0:
        failures.append(
            f"Placeholder has {target_placeholder.game_history_count} game history rows. Must be 0."
        )
        r9_failed = True
    checked_rules["rule_9_game_history"] = "FAILED" if r9_failed else "PASSED"

    # Rule 10: Restoration Quotas
    r10_failed = False
    if quota_status is not None:
        if quota_status.lifetime_restorations_used >= quota_status.lifetime_limit:
            failures.append(
                f"Lifetime restoration limit reached ({quota_status.lifetime_restorations_used}/"
                f"{quota_status.lifetime_limit} used for {quota_status.generation})."
            )
            r10_failed = True
        if quota_status.trailing_30_days_used >= quota_status.trailing_30_days_limit:
            failures.append(
                f"30-day restoration velocity limit reached ({quota_status.trailing_30_days_used}/"
                f"{quota_status.trailing_30_days_limit} used in past 30 days)."
            )
            r10_failed = True
        if not quota_status.is_eligible and quota_status.ineligibility_reason:
            failures.append(f"Account ineligible: {quota_status.ineligibility_reason}")
            r10_failed = True
    checked_rules["rule_10_restoration_quota"] = "FAILED" if r10_failed else "PASSED"

    is_valid = len(failures) == 0
    return ValidationResult(
        valid=is_valid,
        failures=failures,
        checked_rules=checked_rules,
    )
