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

"""Simulated BigQuery Analytics service for historical player telemetry & quota tracking."""

import json
from pathlib import Path

from app.mock_adminweb import adminweb_service
from app.models import PlayerSave, QuotaStatus, RestorationCaseArtifact


class MockBigQueryService:
    """Simulates BigQuery analytical queries (quotas, telemetry, staged cases)."""

    def __init__(self, storage_file: Path | None = None):
        self.quotas: dict[str, QuotaStatus] = {}
        self.staged_cases: dict[str, RestorationCaseArtifact] = {}
        self.storage_file = storage_file or (
            Path(__file__).resolve().parent.parent / "artifacts" / "staged_cases.json"
        )
        self._seed_default_quotas()
        self._load_staged_cases_from_disk()

    def _load_staged_cases_from_disk(self):
        """Loads staged cases from disk to share state across processes."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for tid, case_data in data.items():
                        self.staged_cases[tid] = RestorationCaseArtifact.model_validate(
                            case_data
                        )
            except Exception:
                pass

    def _save_staged_cases_to_disk(self):
        """Persists staged cases to disk for cross-process access."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                tid: case.model_dump(mode="json")
                for tid, case in self.staged_cases.items()
            }
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _seed_default_quotas(self):
        # 1. Normal eligible player
        self.quotas["2K-USR-984210"] = QuotaStatus(
            player_id="2K-USR-984210",
            generation="GEN_5",
            lifetime_restorations_used=2,
            lifetime_limit=10,
            trailing_30_days_used=1,
            trailing_30_days_limit=5,
            is_eligible=True,
        )
        # 2. Typo scenario player
        self.quotas["2K-USR-TYPO22"] = QuotaStatus(
            player_id="2K-USR-TYPO22",
            generation="GEN_5",
            lifetime_restorations_used=1,
            lifetime_limit=10,
            trailing_30_days_used=0,
            trailing_30_days_limit=5,
            is_eligible=True,
        )
        # 3. Tainted upgrade player
        self.quotas["2K-USR-UPGRADE"] = QuotaStatus(
            player_id="2K-USR-UPGRADE",
            generation="GEN_5",
            lifetime_restorations_used=0,
            lifetime_limit=10,
            trailing_30_days_used=0,
            trailing_30_days_limit=5,
            is_eligible=True,
        )
        # 4. Rebirth scenario player
        self.quotas["2K-USR-REBIRTH"] = QuotaStatus(
            player_id="2K-USR-REBIRTH",
            generation="GEN_5",
            lifetime_restorations_used=3,
            lifetime_limit=10,
            trailing_30_days_used=1,
            trailing_30_days_limit=5,
            is_eligible=True,
        )
        # 5. Quota exceeded player
        self.quotas["2K-USR-EXCEEDED"] = QuotaStatus(
            player_id="2K-USR-EXCEEDED",
            generation="GEN_5",
            lifetime_restorations_used=10,
            lifetime_limit=10,
            trailing_30_days_used=2,
            trailing_30_days_limit=5,
            is_eligible=False,
            ineligibility_reason="Lifetime generation restoration limit of 10 reached.",
        )
        # 6. High velocity (abuse risk) player
        self.quotas["2K-USR-VELOCITY"] = QuotaStatus(
            player_id="2K-USR-VELOCITY",
            generation="GEN_5",
            lifetime_restorations_used=6,
            lifetime_limit=10,
            trailing_30_days_used=5,
            trailing_30_days_limit=5,
            is_eligible=False,
            ineligibility_reason="Maximum limit of 5 restoration requests in the past 30 days reached.",
        )

    def get_player_quota(
        self, player_id: str, generation: str = "GEN_5"
    ) -> QuotaStatus:
        """Queries BigQuery quota and velocity tables."""
        if player_id in self.quotas:
            return self.quotas[player_id]
        # Default fresh player quota
        return QuotaStatus(
            player_id=player_id,
            generation=generation,
            lifetime_restorations_used=0,
            lifetime_limit=10,
            trailing_30_days_used=0,
            trailing_30_days_limit=5,
            is_eligible=True,
        )

    def find_orphaned_cloud_saves(
        self, player_id: str, generation: str = "GEN_5"
    ) -> list[PlayerSave]:
        """Queries BigQuery/Cloud storage for saves with status == 'orphaned_cloud_only'."""
        saves = adminweb_service.get_user_saves(player_id, generation)
        return [s for s in saves if s.status == "orphaned_cloud_only"]

    def stage_case_artifact(self, artifact: RestorationCaseArtifact) -> bool:
        """Writes immutable case artifact to BigQuery / Zendesk staging."""
        self._load_staged_cases_from_disk()
        self.staged_cases[artifact.ticket_id] = artifact
        self._save_staged_cases_to_disk()
        return True

    def get_staged_case(self, ticket_id: str) -> RestorationCaseArtifact | None:
        """Retrieves staged case artifact for CS reviewer."""
        self._load_staged_cases_from_disk()
        return self.staged_cases.get(ticket_id)

    def list_staged_cases(self) -> dict[str, RestorationCaseArtifact]:
        """Returns all staged case artifacts currently stored."""
        self._load_staged_cases_from_disk()
        return self.staged_cases


# Global singleton instance
bigquery_service = MockBigQueryService()
