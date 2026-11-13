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

"""Downstream API Dispatcher simulating Human CS 1-click approval and execution."""

import uuid
from typing import Any

from app.mock_adminweb import adminweb_service
from app.mock_bigquery import bigquery_service
from app.models import RestorationExecutionPayload


def approve_and_dispatch_restoration(
    ticket_id: str,
    actor_id: str = "cs_agent_sarah_m",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Simulates a Human CS reviewer clicking 'Approve Restoration' in the CS Console.

    Reads the staged case artifact from BigQuery/Zendesk, verifies PENDING_REVIEW status,
    and executes POST /restorations against Visual Concepts AdminWeb API.

    Args:
        ticket_id: The Zendesk ticket ID of the staged case.
        actor_id: The identifier of the reviewing CS specialist.
        idempotency_key: Optional UUIDv4 string for transactional idempotency.

    Returns:
        Result dictionary from the downstream API dispatcher.
    """
    case = bigquery_service.get_staged_case(ticket_id)
    if not case:
        return {"status": "FAILED", "error": f"Staged case '{ticket_id}' not found."}

    if case.status != "PENDING_REVIEW":
        return {
            "status": "FAILED",
            "error": f"Case '{ticket_id}' is already {case.status}.",
        }

    key = idempotency_key or str(uuid.uuid4())
    payload = RestorationExecutionPayload(
        ticket_id=ticket_id,
        actor_id=actor_id,
        idempotency_key=key,
        player_id=case.player_id,
        generation=case.generation,
        source_save_id=case.source_save_id,
        target_placeholder_id=case.target_placeholder_id,
        target_ovr=case.target_ovr,
        vc_refund_amount=case.vc_delta,
        reason_code="ACCIDENTAL_UPGRADE_RESTORE",
    )

    api_result = adminweb_service.execute_restoration(payload)
    if api_result.get("status") == "SUCCESS":
        case.status = "APPROVED"
        bigquery_service.stage_case_artifact(case)
        return {
            "status": "SUCCESS",
            "ticket_id": ticket_id,
            "actor_id": actor_id,
            "idempotency_key": key,
            "dispatched_to": "Visual Concepts AdminWeb API",
            "api_result": api_result,
        }

    case.status = "REJECTED"
    bigquery_service.stage_case_artifact(case)
    return {"status": "FAILED", "api_result": api_result}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="2K Customer Support 1-Click Restoration Dispatcher"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all staged cases and their review status",
    )
    parser.add_argument(
        "--approve",
        metavar="TICKET_ID",
        help="Approve and execute restoration for the given ticket ID",
    )
    parser.add_argument(
        "--show",
        metavar="TICKET_ID",
        help="Show full details of a specific staged case",
    )
    parser.add_argument(
        "--actor",
        default="cs_specialist_cli",
        help="CS Agent identifier performing the action",
    )

    args = parser.parse_args()

    staged = bigquery_service.list_staged_cases()

    if args.approve:
        result = approve_and_dispatch_restoration(args.approve, actor_id=args.actor)
        print(json.dumps(result, indent=2))
    elif args.show:
        case = bigquery_service.get_staged_case(args.show)
        if case:
            print(json.dumps(case.model_dump(mode="json"), indent=2))
        else:
            print(f"Ticket '{args.show}' not found.")
    else:
        # Default: list cases
        if not staged:
            print("No staged cases found.")
        else:
            print(f"Found {len(staged)} staged case(s):")
            for tid, c in staged.items():
                print(
                    f"  [{c.status}] Ticket: {tid} | Player: {c.player_id} | Target Slot: {c.target_placeholder_id} (OVR: {c.target_ovr}) | Created: {c.created_at}"
                )
