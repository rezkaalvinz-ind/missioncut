# MissionCut - Hackathon Proposal

## Mission-Aware Incident Containment Planner

### Problem

When an incident is detected, responders face a high-stakes question: which connections to block to contain the threat without breaking critical services. Today this decision is often made by instinct, tribal knowledge, or trial and error on production systems. There is no safe, repeatable way to rehearse containment options and see the trade-offs before acting.

### Solution

MissionCut is an offline incident-response decision-support simulator. You supply (or generate) a connectivity graph of your assets. You define containment scenarios, isolate a suspect workstation, block a specific connection, or a custom combination. MissionCut evaluates each option on an isolated copy of the graph and shows you what happens:

- How many critical services stay reachable
- Which communication routes are cut and which remain
- How many links change and what the explicit cost is
- A transparent, lexicographic recommendation with no black-box scoring

It never touches production networks. It makes no probability or risk predictions. It is a decision aid for humans who make the final call.

### Key differentiators

1. **Graph-copy isolation.** Every scenario runs on an independent copy. The source graph is immutable. No accidental mutation of baseline state.
2. **Transparent lexicographic ranking.** The recommendation criteria are explicit and returned in the API response. No hidden weights, no machine-learned scoring.
3. **Actual path details.** Not just counts. The API returns which specific routes are cut and which remain, so responders can verify the impact at path level.
4. **Strict input validation.** Pydantic schemas with `extra="forbid"` reject unknown fields, dangling references, and invalid data. Uploads are bounded to 1 MB, graphs to 250 nodes and 1,000 edges.
5. **Local-first.** In-memory only. No persistence. No secrets, credentials, or production data stored. Graph state lives in the browser session.

### Architecture

- **Backend:** Python 3.12, FastAPI, Pydantic (strict validation), NetworkX (graph operations)
- **Frontend:** Next.js 15, React 19, TypeScript, SVG-based graph visualization
- **Data:** JSON and CSV graph formats, synthetic demo dataset included
- **CI:** GitHub Actions with backend tests, frontend typecheck/lint/build, dependency audit (pip-audit + npm audit)

See [ARCHITECTURE.md](ARCHITECTURE.md) for system and sequence diagrams.

### Demo flow

1. Load the synthetic topology (5 assets, 6 connections)
2. Select a suspected workstation as the suspect
3. Choose containment approaches: full isolation, selective block, or custom
4. Compare containment options. The dashboard shows:
   - Critical service reachability per scenario
   - Routes lost and remaining per source-target pair
   - Blocked connections, assets touched, explicit change cost
   - Recommended option with transparent criteria
5. Export a JSON report with simulation disclaimer

### Metrics

| Metric | Description |
|--------|-------------|
| Services still reachable | Critical services reachable after containment from selected sources |
| Routes lost | Node-simple paths removed by containment (with actual path sequences) |
| Blocked connections | Active links newly set to blocked |
| Changed assets | Distinct endpoint nodes touched by newly blocked links |
| Change cost | Sum of explicit `change_cost` on newly blocked links |

### Safety and limitations

- Simulation only. No production network integrations, no firewall or device controls.
- No attack probability or risk prediction. Metrics are structural, not probabilistic.
- Graph captures only connectivity represented by the user. No protocol, identity policy, capacity, or time modeling.
- Topology freshness, shared infrastructure, and service dependencies are assumptions that can change the outcome.

### Repository

- [README.md](README.md) - Setup, usage, graph schema, API overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - Architecture diagrams and algorithm notes
- [API.md](API.md) - Full API contract with request/response examples
- [SECURITY.md](SECURITY.md) - Security policy
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development guidelines
- `datasets/` - Synthetic graph examples (JSON and CSV)
- `tests/` - 32 tests covering engine, API, parsing, baseline comparison, and path details
