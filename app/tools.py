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

"""ADK Tools for MyPlayer Restoration Agent."""

import json
import uuid
from typing import Any

from app.mock_adminweb import adminweb_service
from app.mock_bigquery import bigquery_service
from app.models import (
    RestorationCaseArtifact,
    RestorationExecutionPayload,
)


def check_player_eligibility(player_id: str, generation: str = "GEN_5") -> str:
    """Checks whether a player is eligible for a MyPlayer restoration.

    Queries BigQuery analytics to verify lifetime restoration limits (max 10
    per generation) and trailing 30-day velocity limits (max 5 in 30 days).

    Args:
        player_id: The unique 2K player account identifier (e.g. '2K-USR-984210').
        generation: The console generation build ('GEN_5' for PS5/Xbox Series X|S/PC,
                    or 'GEN_4' for prior consoles). Defaults to 'GEN_5'.

    Returns:
        JSON string containing eligibility status, restorations used, and limit.
    """
    quota = bigquery_service.get_player_quota(player_id, generation)
    return json.dumps(
        {
            "player_id": quota.player_id,
            "generation": quota.generation,
            "is_eligible": quota.is_eligible,
            "lifetime_restorations_used": quota.lifetime_restorations_used,
            "lifetime_limit": quota.lifetime_limit,
            "trailing_30_days_used": quota.trailing_30_days_used,
            "trailing_30_days_limit": quota.trailing_30_days_limit,
            "ineligibility_reason": quota.ineligibility_reason,
        }
    )


def discover_lost_saves(player_id: str, generation: str = "GEN_5") -> str:
    """Discovers corrupted or lost player builds in the cloud.

    Queries BigQuery and AdminWeb for saves flagged with status 'orphaned_cloud_only'
    with OVR > 65.

    Args:
        player_id: The unique 2K player account identifier.
        generation: Console generation build ('GEN_5' or 'GEN_4').

    Returns:
        JSON string containing a list of matching lost save candidates with build info.
    """
    orphaned_saves = bigquery_service.find_orphaned_cloud_saves(player_id, generation)
    if not orphaned_saves:
        return json.dumps(
            {
                "found": False,
                "message": "No orphaned cloud saves found for this account.",
            }
        )

    results = []
    for s in orphaned_saves:
        results.append(
            {
                "save_id": s.save_id,
                "slot": s.slot,
                "ovr": s.ovr,
                "position": s.position,
                "archetype": s.archetype,
                "height": s.height,
                "weight": f"{s.weight} lbs",
                "wingspan": s.wingspan,
                "status": s.status,
                "last_updated": s.last_updated,
            }
        )
    return json.dumps({"found": True, "count": len(results), "saves": results})


def get_build_blueprint(player_id: str, save_id: str) -> str:
    """Fetches the exact creation blueprint and specifications of a lost save.

    Use this tool to guide and coach the player on how to configure their new
    blank 60 OVR placeholder save on their console.

    Args:
        player_id: The 2K player account identifier.
        save_id: The ID of the lost original save (e.g. 'save_original_123').

    Returns:
        JSON string with physical specs (position, height, weight, wingspan, archetype)
        and baseline starting attributes.
    """
    save = adminweb_service.get_save(save_id)
    if not save:
        return json.dumps({"error": f"Save '{save_id}' not found."})

    return json.dumps(
        {
            "save_id": save.save_id,
            "ovr": save.ovr,
            "position": save.position,
            "height": save.height,
            "weight": f"{save.weight} lbs",
            "wingspan": save.wingspan,
            "archetype": save.archetype,
            "template_id": save.template_id,
            "instructions": (
                f"Instruct the player to build a blank 60 OVR character in any available slot with: "
                f"Position: {save.position}, Height: {save.height}, Weight: {save.weight} lbs, "
                f"Wingspan: {save.wingspan}, Archetype: {save.archetype}. Do NOT upgrade any attributes."
            ),
            "as_created_attributes": save.attributes.as_created
            if save.attributes
            else {},
        }
    )


def discover_candidate_placeholders(player_id: str, generation: str = "GEN_5") -> str:
    """Inspects player saves to find newly created 60 OVR placeholder saves.

    Args:
        player_id: The 2K player account identifier.
        generation: Console generation build ('GEN_5' or 'GEN_4').

    Returns:
        JSON string listing potential 60 OVR placeholder saves on the console.
    """
    saves = adminweb_service.get_user_saves(player_id, generation)
    # Placeholders are typically active saves around 60 OVR
    candidates = [
        {
            "save_id": s.save_id,
            "slot": s.slot,
            "ovr": s.ovr,
            "position": s.position,
            "height": s.height,
            "weight": f"{s.weight} lbs",
            "wingspan": s.wingspan,
            "archetype": s.archetype,
            "has_upgraded_attributes": s.has_upgraded_attributes,
            "is_rebirth": s.is_rebirth,
            "status": s.status,
            "created_at": s.created_at,
        }
        for s in saves
        if s.status == "active" and s.ovr <= 70
    ]
    return json.dumps({"count": len(candidates), "candidates": candidates})


def validate_restoration_candidate(
    source_save_id: str, target_placeholder_id: str
) -> str:
    """Evaluates the 10 server-side validation rules atomically via POST /restorations:validate.

    This is a deterministic, side-effect free pre-check. If any rule fails (e.g. wingspan typo,
    upgraded attributes, rebirth), it returns structured failure messages so you can coach
    the player to correct their settings.

    Args:
        source_save_id: ID of the lost original build.
        target_placeholder_id: ID of the new 60 OVR placeholder save.

    Returns:
        JSON string with 'valid' boolean, list of 'failures', and 'checked_rules' summary.
    """
    res = adminweb_service.validate_restoration(source_save_id, target_placeholder_id)
    return json.dumps(
        {
            "valid": res.valid,
            "failures": res.failures,
            "checked_rules": res.checked_rules,
        }
    )


def update_placeholder_setting_in_console(
    save_id: str, setting_name: str, new_value: str
) -> str:
    """Simulates a player correcting a setting in the console builder and re-saving.

    Call this tool when the player states in chat that they fixed a specific setting
    (e.g. changing wingspan from 6'10\" to 6'11\", or adjusting weight) after receiving coaching.

    Args:
        save_id: The ID of the placeholder save being modified.
        setting_name: The attribute name to update (e.g. 'wingspan', 'height', 'weight').
        new_value: The new value entered by the player (e.g. "6'11\"", "200").

    Returns:
        JSON string indicating whether the simulated save update succeeded.
    """
    val: Any = new_value
    if setting_name == "weight":
        try:
            val = int(new_value.replace("lbs", "").strip())
        except ValueError:
            pass
    updated = adminweb_service.update_placeholder_setting(save_id, setting_name, val)
    if not updated:
        return json.dumps(
            {"success": False, "error": f"Placeholder save '{save_id}' not found."}
        )
    return json.dumps(
        {
            "success": True,
            "save_id": save_id,
            "updated_field": setting_name,
            "new_value": val,
            "message": f"Console save '{save_id}' updated with {setting_name}={val}. Ready for re-validation.",
        }
    )


def stage_case_for_human_review(
    player_id: str,
    source_save_id: str,
    target_placeholder_id: str,
    player_confirmed: bool,
    ticket_id: str | None = None,
) -> str:
    """Stages the verified restoration case for 1-click Human CS approval.

    CRITICAL SAFETY RULES:
    1. Only call this tool AFTER validate_restoration_candidate returns valid=true.
    2. Only call this tool AFTER the player has explicitly confirmed they want to restore.
    3. If player_confirmed is False, do NOT stage the case.

    Args:
        player_id: The 2K player account identifier.
        source_save_id: ID of the original build being cloned.
        target_placeholder_id: ID of the verified 60 OVR placeholder save.
        player_confirmed: Must be True indicating the player provided explicit consent.
        ticket_id: Optional existing ticket ID. If omitted, a new ID is generated.

    Returns:
        JSON string containing the staged ticket artifact and 48h SLA response.
    """
    if not player_confirmed:
        return json.dumps(
            {
                "staged": False,
                "error": "Player did not give final confirmation. Case cannot be staged without player consent.",
            }
        )

    # Run one final deterministic validation check
    val_result = adminweb_service.validate_restoration(
        source_save_id, target_placeholder_id
    )
    if not val_result.valid:
        return json.dumps(
            {
                "staged": False,
                "error": "Validation failed during pre-staging check.",
                "failures": val_result.failures,
            }
        )

    source = adminweb_service.get_save(source_save_id)
    target = adminweb_service.get_save(target_placeholder_id)

    tid = ticket_id or f"ZD-{uuid.uuid4().hex[:6].upper()}"
    artifact = RestorationCaseArtifact(
        ticket_id=tid,
        player_id=player_id,
        generation=source.generation if source else "GEN_5",
        source_save_id=source_save_id,
        target_placeholder_id=target_placeholder_id,
        target_ovr=target.ovr if target else 60,
        vc_delta=42500,  # Estimated VC restoration value
        validation_result=val_result,
        status="PENDING_REVIEW",
        recommendation="APPROVE",
    )
    bigquery_service.stage_case_artifact(artifact)

    return json.dumps(
        {
            "staged": True,
            "ticket_id": tid,
            "status": "PENDING_REVIEW",
            "sla_message": (
                f"Your restoration request has been verified (Ticket #{tid}) and submitted to our "
                f"Specialist Review Team. You will receive an update at your registered email within 48 hours."
            ),
            "cs_summary": {
                "all_10_checks_passed": True,
                "source_ovr": source.ovr if source else 95,
                "target_slot": target.slot if target else 3,
                "ready_for_one_click_approval": True,
            },
        }
    )


def execute_restoration_clone(
    ticket_id: str,
    actor_id: str,
    source_save_id: str,
    target_placeholder_id: str,
    idempotency_key: str | None = None,
) -> str:
    """Executes the transactional MyPlayer clone via POST /restorations.

    NOTE: This tool is typically invoked by the Human CS reviewer or downstream
    dispatcher upon 1-click approval.

    Args:
        ticket_id: Zendesk Ticket ID (e.g. 'ZD-109482').
        actor_id: CS reviewer ID (e.g. 'cs_agent_sarah_m').
        source_save_id: Source save ID.
        target_placeholder_id: Target placeholder save ID.
        idempotency_key: Unique idempotency UUID to prevent duplicate writes.

    Returns:
        JSON string with execution outcome from Visual Concepts AdminWeb API.
    """
    key = idempotency_key or str(uuid.uuid4())
    src = adminweb_service.get_save(source_save_id)
    tgt = adminweb_service.get_save(target_placeholder_id)
    if not src or not tgt:
        return json.dumps({"error": "Source or target save not found."})

    payload = RestorationExecutionPayload(
        ticket_id=ticket_id,
        actor_id=actor_id,
        idempotency_key=key,
        player_id=src.player_id,
        generation=src.generation,
        source_save_id=source_save_id,
        target_placeholder_id=target_placeholder_id,
        target_ovr=60,
        vc_refund_amount=42500,
    )
    res = adminweb_service.execute_restoration(payload)
    return json.dumps(res)
