# 2K MyPLAYER Build Restoration Agent (`player-restore-agent`)

A conversational AI specialist built with the **Google Agent Development Kit (ADK)** and `agents-cli`. This agent automates the intake, discovery, builder coaching, deterministic safety validation, and Human-in-the-Loop (HITL) ticket staging for corrupted or lost 2K MyPLAYER builds.

---

## Architecture & Workflow

```
[Player Chat Client]
        │
        ▼
[ADK Root Agent (app/agent.py)]
        │
        ├── 1. Intake & Quota Verification ──► [BigQuery Quota Service (app/mock_bigquery.py)]
        │                                      (Lifetime max 10/gen, 30-day velocity max 5)
        │
        ├── 2. Save Discovery & Blueprint  ──► [AdminWeb API (app/mock_adminweb.py)]
        │                                      (Finds orphaned cloud saves >65 OVR)
        │
        ├── 3. Builder Coaching & Detection ──► [Player creates 60 OVR placeholder on console]
        │
        ├── 4. 10-Rule Validation Engine   ──► [app/rule_engine.py]
        │                                      (Server-side deterministic validation)
        │
        ├── 5. Player Consent & SLA Staging ──► [BigQuery / Zendesk Staging Table]
        │                                      (Artifact staged in PENDING_REVIEW; 48h SLA)
        ▼
[CS 1-Click Dispatcher (app/dispatcher.py)] ──► [POST /restorations (AdminWeb)]
```

---

## The 10 Server-Side Validation Rules

Every placeholder candidate is deterministically evaluated against all 10 non-negotiable rules prior to staging:

1. **OVR 60 & Untouched Status**: Target placeholder must have `overall_rating == 60` and `has_upgraded_attributes == False`; source save must be `> 65 OVR`.
2. **Physical Match**: Position, height, weight, wingspan (using length normalization, e.g. `6'11"` vs `83 in`), and archetype name must strictly match.
3. **Attribute Match Against As-Created Baseline**: Every core attribute rating (Finishing, Shooting, Playmaking, Defense/Rebounding, Physicals) must match the original as-created baseline before Cap Breakers or VC upgrades.
4. **Rebirth Verification**: Placeholders cannot use Rebirth (`is_rebirth == False`, Gen 4 XP = 0, Gen 5 badge points $\ne$ 17,250).
5. **Template Conformity**: Player-created builds must use `template_id == 0` (or match source template ID).
6. **Build Specialization Absence**: Specialization unlock flag (`2K26.UNLOCKS.BUILD_SPECIALIZATION`) must be absent.
7. **Timestamp Consistency**: Placeholder `created_at` must match `last_updated` (no subsequent play sessions).
8. **VC History Cleanliness**: Exactly 0 VC transaction records (`vc_transactions_count == 0`).
9. **Game History Cleanliness**: Exactly 0 games played (`games_played_count == 0`).
10. **Quotas & Velocity Limits**: Lifetime restorations $\le 10$ per console generation; trailing 30-day restorations $\le 5$.

---

## Pre-Seeded Test Fixtures

| Player ID | Scenario | Details |
|-----------|----------|---------|
| `2K-USR-984210` | **Happy Path** | 95 OVR PG 2-Way Floor-Spacing Slasher (`save_original_123`) & matching 60 OVR placeholder (`save_placeholder_456`). Passes all 10 rules. |
| `2K-USR-TYPO22` | **Wingspan Typo Coaching** | 90 OVR SG build with 6'11" wingspan; placeholder was created with 6'10" wingspan. Agent detects typo and coaches player to adjust in builder. |
| `2K-USR-EXCEEDED` | **Lifetime Quota Exceeded** | 10 / 10 lifetime restorations already consumed. Agent politely declines without coaching to create a placeholder. |
| `2K-USR-VELOCITY` | **30-Day Velocity Exceeded** | 5 restorations in the trailing 30 days. Request refused politely under velocity limit. |
| `2K-USR-UPGRADE` | **Tainted Placeholder** | Placeholder has `has_upgraded_attributes == True` and 65 OVR. Rejected under Rule 1. |
| `2K-USR-REBIRTH` | **Rebirth Placeholder** | Placeholder has `is_rebirth == True`. Rejected under Rule 4. |

---

## Running and Testing the Agent

### 1. Interactive Playground
Test the conversational agent interactively in your browser:
```bash
agents-cli playground
```

### 2. Run Single Turns or Sessions via CLI
```bash
# Check intake and blueprint coaching:
agents-cli run --prompt "Hi, my 95 OVR build crashed on PS5. Player ID is 2K-USR-984210. Help me restore it."
```

### 3. Run Unit and Integration Tests
```bash
uv run pytest tests/unit tests/integration
```
All 22 tests (18 unit + 4 integration) execute and pass against the mock services and ADK runners.

### 4. Run the Evaluation Suite
```bash
agents-cli eval run --dataset tests/eval/datasets/restoration_dataset.json
```
Evaluates all 8 restoration test cases across two evaluation metrics:
- `restoration_policy_compliance`: Verifies adherence to safety rules, quota checks, zero direct clone execution, and 48-hour SLA notice.
- `custom_response_quality`: LLM-as-a-judge assessing accuracy, customer support empathy, and clarity.

### 5. Code Quality & Linting
```bash
agents-cli lint
```
Runs `ruff check`, `ruff format`, `codespell`, and `ty` type checking.

---

## Project Structure

```
player_restore_agent/
├── app/
│   ├── agent.py                 # ADK Root Agent with conversational system instructions
│   ├── dispatcher.py            # Downstream CS 1-Click approval dispatcher (POST /restorations)
│   ├── fast_api_app.py          # FastAPI / A2A server
│   ├── mock_adminweb.py         # Visual Concepts AdminWeb REST API mock with pre-seeded saves
│   ├── mock_bigquery.py         # BigQuery quota analytics and artifact staging mock
│   ├── models.py                # Pydantic schemas, AttributePanel, validation models, length parser
│   ├── rule_engine.py           # Deterministic 10-rule evaluation engine
│   └── tools.py                 # ADK Function Tools exposed to the LLM agent
├── artifacts/
│   ├── grade_results/           # Timestamped evaluation JSON and HTML reports
│   └── traces/                  # Execution traces from eval generate
├── tests/
│   ├── conftest.py              # Environment setup & dotenv loader for pytest
│   ├── eval/
│   │   ├── datasets/
│   │   │   └── restoration_dataset.json # 8 multi-turn / single-turn evaluation scenarios
│   │   ├── eval_config.yaml     # Eval runner configuration
│   │   ├── response_quality.py  # LLM-as-a-judge metric
│   │   └── restoration_compliance.py # Domain policy compliance metric
│   ├── integration/
│   │   ├── test_agent.py        # ADK streaming runner integration test
│   │   └── test_server_e2e.py   # FastAPI SSE and A2A protocol integration tests
│   └── unit/
│       ├── test_dummy.py        # Scaffold sanity test
│       ├── test_rule_engine.py  # 12 unit tests verifying each of the 10 rules + edge cases
│       └── test_tools_and_dispatcher.py # 5 unit tests for ADK tools and CS dispatcher
├── GEMINI.md                    # Coding agent guidance & lifecycle commands
├── plan.md                      # Architecture and implementation plan
└── pyproject.toml               # Dependencies, Ruff, and tool configurations
```
