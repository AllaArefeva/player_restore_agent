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

"""Unit tests for ADK tools and CS downstream dispatcher."""

import json

from app.dispatcher import approve_and_dispatch_restoration
from app.mock_adminweb import adminweb_service
from app.tools import (
    check_player_eligibility,
    discover_candidate_placeholders,
    discover_lost_saves,
    get_build_blueprint,
    stage_case_for_human_review,
    update_placeholder_setting_in_console,
    validate_restoration_candidate,
)


def test_check_eligibility_eligible_and_ineligible():
    # Eligible player
    res = json.loads(check_player_eligibility("2K-USR-984210"))
    assert res["is_eligible"] is True
    assert res["lifetime_restorations_used"] == 2

    # Ineligible player (limit reached)
    res_exceeded = json.loads(check_player_eligibility("2K-USR-EXCEEDED"))
    assert res_exceeded["is_eligible"] is False
    assert "limit" in res_exceeded["ineligibility_reason"].lower()


def test_discover_lost_saves_and_blueprint():
    lost = json.loads(discover_lost_saves("2K-USR-984210"))
    assert lost["found"] is True
    assert lost["count"] >= 1
    save_id = lost["saves"][0]["save_id"]

    blueprint = json.loads(get_build_blueprint("2K-USR-984210", save_id))
    assert blueprint["ovr"] == 95
    assert blueprint["position"] == "PG"
    assert blueprint["wingspan"] == "6'11\""
    assert "three_point" in blueprint["as_created_attributes"]


def test_candidate_placeholders():
    cand = json.loads(discover_candidate_placeholders("2K-USR-984210"))
    assert cand["count"] >= 1
    assert any(c["save_id"] == "save_placeholder_456" for c in cand["candidates"])


def test_typo_coaching_and_update():
    # Initially wingspan is 6'10" vs original 6'11"
    val = json.loads(
        validate_restoration_candidate("save_typo_source", "save_typo_placeholder")
    )
    assert val["valid"] is False
    assert any("Wingspan mismatch" in f for f in val["failures"])

    # Simulate player fixing wingspan in console
    update_res = json.loads(
        update_placeholder_setting_in_console(
            "save_typo_placeholder", "wingspan", "6'11\""
        )
    )
    assert update_res["success"] is True

    # Re-validate
    val_after = json.loads(
        validate_restoration_candidate("save_typo_source", "save_typo_placeholder")
    )
    assert val_after["valid"] is True
    assert len(val_after["failures"]) == 0


def test_stage_case_and_dispatch():
    # Stage case with explicit confirmation
    stage_res = json.loads(
        stage_case_for_human_review(
            player_id="2K-USR-984210",
            source_save_id="save_original_123",
            target_placeholder_id="save_placeholder_456",
            player_confirmed=True,
            ticket_id="ZD-TEST-001",
        )
    )
    assert stage_res["staged"] is True
    assert stage_res["ticket_id"] == "ZD-TEST-001"
    assert stage_res["status"] == "PENDING_REVIEW"
    assert "48 hours" in stage_res["sla_message"]

    # CS 1-Click approval dispatch
    dispatch_res = approve_and_dispatch_restoration(
        "ZD-TEST-001", actor_id="cs_agent_sarah_m"
    )
    assert dispatch_res["status"] == "SUCCESS"
    assert dispatch_res["api_result"]["restored_ovr"] == 95

    # Check target save was restored in mock database
    restored = adminweb_service.get_save("save_placeholder_456")
    assert restored.ovr == 95
