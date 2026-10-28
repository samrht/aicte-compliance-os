# AICTE Compliance OS

Working prototype for **Smart India Hackathon 2026, SIH26262: Integrated AICTE Approval Workflow Automation, Compliance Monitoring and Alert Management System**. Team *Ek kachori do samosa*.

Every application is scored on arrival by a LightGBM risk model and routed through a workflow built for its risk tier. Low-risk campuses are ratified with no human step. High-risk ones are locked down, checked one step at a time, inspected, and sent to a regulator. Every state change is appended to a signed Merkle audit log.

All institutions, people and figures are fictional.

## Run it

```powershell
.\start.ps1
```

That opens the API on http://localhost:8000 (docs at `/docs`) and the app on http://localhost:5173. On first start the backend trains the model and seeds 23 institutions with their history (about 15 s).

Manual start:

```powershell
cd backend;  .\.venv\Scripts\python -m uvicorn app.main:app --port 8000
cd frontend; npx vite --port 5173
```

Tests: `cd backend; .\.venv\Scripts\python -m pytest -q` (23 tests, including both demo applications end to end).

**Admin panel:** `/admin/login` (linked from the sign-in page). Demo account `admin` / `aicte-admin-2026`; set `ADMIN_USER` / `ADMIN_PASSWORD` on the server to replace it (the login page then stops showing the hint). The admin sees live stats (refreshing every 3 s) and verifies every uploaded document beside its automatic checks; verdicts are signed into the audit log and rejections notify the institution.

**Reset before every take:** Admin panel → Live stats → *Reset demo data* (click twice). This restores the seeded world.

## What is real and what is simplified

| Pitch deck | In this prototype |
|---|---|
| LightGBM risk scorer | Real LightGBM with monotone constraints, trained on 2,400 synthetic past institutions (holdout AUC shown on the dashboard). Per-case explanations are exact TreeSHAP values. |
| Temporal DAG engine | A persisted DAG engine: node state lives in the database and interrupted cases resume on restart. The risk node grows the rest of the graph for its tier at run time. |
| Geo-tagged CV audit (YOLOv8, pHash) | Real EXIF GPS extraction plus haversine distance to the registered campus, and real perceptual hashing against every other institution's photos. No YOLO object detection. |
| Faculty Collision Radar | Real HMAC-SHA256 blinded tokens from normalised PAN + DOB. Only tokens are stored. |
| LayoutLMv3 DocAI | Text-layer extraction from the PDF with labelled-field patterns. Same interface, no model. |
| OPA/Rego + CP-SAT Shadow Sandbox | Norms are declarative JSON evaluated by a small engine and exported as real Rego. Remediation picks the cheapest option per rule. |
| Ed25519 Merkle log | Real RFC 6962 Merkle tree, Ed25519-signed roots, inclusion proofs, and tamper detection. |
| Kafka, Kubernetes, Postgres, S3, KMS | SQLite and local files. The pepper and signing key are local files. |

## Demo video script (about 5 minutes)

1. **Sign-in (15 s).** Two roles: institution and AICTE regulator. Open the regulator console.
2. **Overview (30 s).** 23 institutions are monitored, about two-thirds were decided with no human step, and low-risk turnaround is inside 48 hours. Point at what drives risk.
3. **Clean application (60 s).** Sign out, then sign in as *Indrayani Institute of Engineering & Research*. Apply: the figures are pre-filled. Upload everything in `demo-assets/1-clean-indrayani-pune/` (`faculty.csv`, the 3 photos, `financials.pdf`) and submit. Watch the DAG: ingestion, then the risk scorer gives LOW, then four checks run in parallel, then batch ratification. The **RATIFIED** stamp lands.
4. **Shady application (90 s).** Sign in as *Thar Desert College of Engineering & Technology* and upload `demo-assets/2-shady-thar-jaipur/`. The risk is HIGH, so the **LOCKDOWN** stamp lands and the checks run one at a time. Scroll to the findings: a photo taken 38 km away, a lab photo recycled from Aravalli Institute, 6 ghost faculty shared with Aravalli and Malwa, an 18% deficit, and norm breaches. Show the SHAP bars and the cheapest path to compliance.
5. **Regulator (60 s).** Open the review queue and the Thar Desert case, reject it with a note, and watch the audit seal run. Open the collision radar: the ghost-faculty ring is drawn, and only token hashes are ever shown.
6. **Audit log (30 s).** It shows all entries verified. Click *Tamper* on a `case.decided` row and the banner turns red naming that entry. Click *Restore original rows* and it turns green again.
7. **Shadow sandbox (30 s).** Drag the faculty-student ratio from 20 to 16. Compliance drops, the colleges that would fall out are named, each gets a costed remediation plan, and *Show Rego* reveals the generated policy.
8. **Alerts (15 s).** Show the alert center and run the compliance sweep on the overview.

## Layout

```
backend/app/
  main.py        HTTP API
  dag/           workflow engine and node handlers
  risk/          LightGBM model, synthetic history, SHAP
  verify/        photos (EXIF GPS, pHash), docai (PDF fields), faculty (HMAC tokens)
  policy/        norms.json, evaluator, remediation, sandbox, Rego export
  audit/         RFC 6962 Merkle log, Ed25519 checkpoints, proofs
  seed.py        demo world + demo-assets generator
frontend/src/
  pages/         Login, institution portal (InstHome, Apply, InstCase), regulator console
  components/    Dag (React Flow), CaseFile, ui
demo-assets/     upload sets for the video (generated by the seed)
```
