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

"""Simulated 2K / Visual Concepts AdminWeb REST API service and storage."""

import copy
from typing import Any

from app.models import (
    AttributePanel,
    PlayerSave,
    RestorationExecutionPayload,
    ValidationResult,
)
from app.rule_engine import validate_restoration_rules


class MockAdminWebService:
    """Simulates the Visual Concepts AdminWeb REST endpoints."""

    def __init__(self):
        self.saves: dict[str, PlayerSave] = {}
        self.cloned_saves: dict[str, PlayerSave] = {}
        self._seed_default_data()

    def _seed_default_data(self):
        """Seeds realistic pre-configured test scenarios."""
        # 1. Standard Happy Path Player: 2K-USR-984210
        p1_ts = "2026-08-18T20:00:00Z"
        self.saves["save_original_123"] = PlayerSave(
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
                as_created={
                    "three_point": 90,
                    "driving_dunk": 85,
                    "speed": 88,
                    "perimeter_defense": 82,
                },
                current={
                    "three_point": 95,
                    "driving_dunk": 90,
                    "speed": 88,
                    "perimeter_defense": 85,
                },
            ),
        )
        self.saves["save_placeholder_456"] = PlayerSave(
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
            status="active",
            created_at=p1_ts,
            last_updated=p1_ts,
            vc_history_count=0,
            game_history_count=0,
            attributes=AttributePanel(
                as_created={
                    "three_point": 90,
                    "driving_dunk": 85,
                    "speed": 88,
                    "perimeter_defense": 82,
                },
                current={
                    "three_point": 90,
                    "driving_dunk": 85,
                    "speed": 88,
                    "perimeter_defense": 82,
                },
            ),
        )

        # 2. Wingspan Typo Player: 2K-USR-TYPO22
        # Target placeholder has 6'10" wingspan instead of 6'11"
        self.saves["save_typo_source"] = PlayerSave(
            save_id="save_typo_source",
            player_id="2K-USR-TYPO22",
            slot=1,
            generation="GEN_5",
            ovr=93,
            position="SG",
            height="6'6\"",
            weight=205,
            wingspan="6'11\"",
            archetype="Inside-Out Threat",
            template_id=0,
            has_upgraded_attributes=True,
            is_rebirth=False,
            status="orphaned_cloud_only",
            created_at="2026-07-20T10:00:00Z",
            last_updated="2026-08-10T14:00:00Z",
            attributes=AttributePanel(
                as_created={"three_point": 88, "mid_range": 84, "driving_dunk": 82},
                current={"three_point": 92, "mid_range": 84, "driving_dunk": 82},
            ),
        )
        typo_ts = "2026-08-19T10:00:00Z"
        self.saves["save_typo_placeholder"] = PlayerSave(
            save_id="save_typo_placeholder",
            player_id="2K-USR-TYPO22",
            slot=2,
            generation="GEN_5",
            ovr=60,
            position="SG",
            height="6'6\"",
            weight=205,
            wingspan="6'10\"",  # Typo: 6'10" instead of 6'11"
            archetype="Inside-Out Threat",
            template_id=0,
            has_upgraded_attributes=False,
            is_rebirth=False,
            status="active",
            created_at=typo_ts,
            last_updated=typo_ts,
            vc_history_count=0,
            game_history_count=0,
            attributes=AttributePanel(
                as_created={"three_point": 88, "mid_range": 84, "driving_dunk": 82},
                current={"three_point": 88, "mid_range": 84, "driving_dunk": 82},
            ),
        )

        # 3. Upgraded / Tainted Placeholder Player: 2K-USR-UPGRADE
        self.saves["save_tainted_source"] = PlayerSave(
            save_id="save_tainted_source",
            player_id="2K-USR-UPGRADE",
            slot=1,
            generation="GEN_5",
            ovr=90,
            position="SF",
            height="6'7\"",
            weight=215,
            wingspan="7'0\"",
            archetype="3-Level Threat",
            template_id=0,
            has_upgraded_attributes=True,
            status="orphaned_cloud_only",
        )
        self.saves["save_tainted_placeholder"] = PlayerSave(
            save_id="save_tainted_placeholder",
            player_id="2K-USR-UPGRADE",
            slot=2,
            generation="GEN_5",
            ovr=68,  # Not 60!
            position="SF",
            height="6'7\"",
            weight=215,
            wingspan="7'0\"",
            archetype="3-Level Threat",
            template_id=0,
            has_upgraded_attributes=True,
            vc_history_count=3,
            game_history_count=2,
            status="active",
        )

        # 4. Rebirth Placeholder Player: 2K-USR-REBIRTH
        self.saves["save_rebirth_source"] = PlayerSave(
            save_id="save_rebirth_source",
            player_id="2K-USR-REBIRTH",
            slot=1,
            generation="GEN_5",
            ovr=91,
            position="C",
            height="7'0\"",
            weight=245,
            wingspan="7'4\"",
            archetype="Glass-Cleaning Interior Scorer",
            template_id=0,
            has_upgraded_attributes=True,
            status="orphaned_cloud_only",
        )
        rb_ts = "2026-08-19T11:00:00Z"
        self.saves["save_rebirth_placeholder"] = PlayerSave(
            save_id="save_rebirth_placeholder",
            player_id="2K-USR-REBIRTH",
            slot=2,
            generation="GEN_5",
            ovr=60,
            position="C",
            height="7'0\"",
            weight=245,
            wingspan="7'4\"",
            archetype="Glass-Cleaning Interior Scorer",
            is_rebirth=True,
            badge_points=17250,  # Gen 5 rebirth flag
            status="active",
            created_at=rb_ts,
            last_updated=rb_ts,
        )

    def get_user_saves(
        self, player_id: str, generation: str = "GEN_5"
    ) -> list[PlayerSave]:
        """GET /users/{id}/saves"""
        return [
            save
            for save in self.saves.values()
            if save.player_id == player_id and save.generation == generation
        ]

    def get_save(self, save_id: str) -> PlayerSave | None:
        """GET /saves/{id}"""
        return self.saves.get(save_id)

    def update_placeholder_setting(
        self, save_id: str, setting_name: str, new_value: Any
    ) -> PlayerSave | None:
        """Simulates player modifying their placeholder in console builder (e.g. fixing wingspan)."""
        save = self.saves.get(save_id)
        if not save:
            return None
        setattr(save, setting_name, new_value)
        return save

    def validate_restoration(
        self, source_save_id: str, target_placeholder_id: str
    ) -> ValidationResult:
        """POST /restorations:validate"""
        src = self.get_save(source_save_id)
        tgt = self.get_save(target_placeholder_id)
        if not src:
            return ValidationResult(
                valid=False,
                failures=[f"Source save '{source_save_id}' not found in AdminWeb."],
                checked_rules={"source_lookup": "FAILED"},
            )
        if not tgt:
            return ValidationResult(
                valid=False,
                failures=[
                    f"Target placeholder save '{target_placeholder_id}' not found in AdminWeb."
                ],
                checked_rules={"target_lookup": "FAILED"},
            )
        return validate_restoration_rules(src, tgt)

    def execute_restoration(self, payload: RestorationExecutionPayload) -> dict:
        """POST /restorations (Clone from another save)"""
        src = self.get_save(payload.source_save_id)
        tgt = self.get_save(payload.target_placeholder_id)
        if not src or not tgt:
            return {
                "status": "FAILED",
                "error": "Invalid source or target save ID",
                "ticket_id": payload.ticket_id,
            }

        # Clone attributes and OVR into target save
        cloned = copy.deepcopy(src)
        cloned.save_id = tgt.save_id
        cloned.slot = tgt.slot
        cloned.status = "active"
        self.cloned_saves[tgt.save_id] = cloned
        self.saves[tgt.save_id] = cloned

        return {
            "status": "SUCCESS",
            "operation": payload.operation,
            "ticket_id": payload.ticket_id,
            "actor_id": payload.actor_id,
            "idempotency_key": payload.idempotency_key,
            "player_id": payload.player_id,
            "restored_save_id": tgt.save_id,
            "restored_ovr": cloned.ovr,
            "message": f"Successfully restored {cloned.ovr} OVR build into {tgt.save_id} (Slot {tgt.slot}).",
        }


# Global singleton instance
adminweb_service = MockAdminWebService()
