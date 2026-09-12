# Cleanup and UI Plan

## Goal
Keep the project focused on the hackathon demo, live hardware mode, and AI risk intelligence, while removing old or non-essential material only after approval.

## Keep
- `run_hackathon.ps1`
- `scripts/start_hackathon.ps1`
- `scripts/preflight_check.py`
- `ev_dashboard.py`
- `ev_battery_monitor.py`
- `mlops_runtime.py`
- `train_ev_model.py`
- `web/index.html`
- `web/app.js`
- `web/styles.css`
- Demo mode and live mode startup flow
- AI explainability, drift alerts, and model loading logic

## Proposed non-required or old items to remove after approval
- `Running.md`
- `usage.md`
- `hardwareusage.md`
- `test_all_endpoints.ps1`
- `test_com6_receiver.py`
- `scripts/rollback_now.ps1`
- `old.csv`
- `logs/` runtime output
- `models/candidates/` older training artifacts, except the stable model path needed by the app

## UI Improvement Plan
1. Improve contrast, spacing, and typography for projector-friendly readability.
2. Make the top summary area more obvious by grouping status, prediction, and confidence into a stronger visual hierarchy.
3. Increase card padding, border clarity, and line height so the dashboard feels less crowded.
4. Give metric cards, charts, and timeline a more consistent visual rhythm.
5. Keep the color language tied to status states: green for normal, amber for warning, red for critical.
6. Reduce visual noise from background effects so the data itself stays the focus.
7. Tighten mobile and smaller-screen layout so the demo still looks clean on a laptop.

## Next Steps
- Review the non-required list.
- Approve what should actually be deleted.
- Apply the cleanup only after approval.
- Finish the UI polish and then validate the dashboard in demo mode.

## AI Features to Maximize Expo Winning Chances

### Priority 1: Judge-Visible Intelligence (Must Have)
1. Multitask AI inference panel
	- Show battery risk class, remaining useful life estimate, and anomaly score at the same time.
	- Explain each output in plain language on the UI.
2. Explainable AI card
	- Add top contributing features for each prediction (for example: temperature spike, voltage spread, current surge).
	- Include "why this changed" text when class moves NORMAL -> WARNING -> CRITICAL.
3. Early warning lead-time metric
	- Display "minutes before critical threshold" based on trend forecasting.
	- Judges immediately see practical business value.
4. Confidence calibration and uncertainty
	- Show confidence plus uncertainty band so model is not a black box.
	- Add low-confidence alert for operator review.
5. Natural language incident summary
	- Auto-generate a short copilot-style sentence:
	  - "Pack health degraded due to rising thermal variance over last 90s."

### Priority 2: Reliability and Safety AI (High Impact)
1. Adaptive thresholding
	- Replace static thresholds with dynamic baselines learned from recent healthy windows.
2. Sensor fault diagnosis model
	- Classify whether anomaly is battery issue vs sensor noise vs communication corruption.
3. Auto-heal policy engine
	- AI chooses best recovery action (reconnect, smooth, fallback model, isolate sensor).
4. Out-of-distribution detection
	- Warn when incoming data is unlike training distribution.
5. Ensemble risk scoring
	- Blend classifier + anomaly detector + rule engine for robust decisions.

### Priority 3: Advanced Analytics for Expo Differentiation
1. Remaining Useful Life (RUL) forecasting
	- Predict cycles/time left before performance drops below safe level.
2. What-if simulation sandbox
	- User can simulate "+8 C temp" or "high current burst" and see projected risk.
3. Pack digital twin
	- Lightweight simulation model mirrors pack behavior and compares expected vs observed.
4. Drift monitoring and retrain trigger
	- Track data drift and concept drift; trigger retrain recommendation automatically.
5. Fleet intelligence mode
	- Compare multiple vehicles/packs and rank top-risk assets.

### Priority 4: UX AI Features Judges Remember
1. AI copilot chat on dashboard
	- Ask: "Why is risk high?" "What should operator do now?"
2. Voice alert + speech summary
	- Real-time spoken alerts for critical states.
3. Story mode timeline
	- AI-generated timeline of key events during demo.
4. Executive scorecard
	- Live KPI strip: safety score, reliability score, estimated cost saved.
5. Smart recommendations
	- Action cards: "reduce load", "check cooling path", "inspect sensor 3".

### Priority 5: MLOps + Trust Features (Technical Depth)
1. Model version comparison in UI
	- Show stable model vs candidate model side-by-side metrics.
2. Online evaluation hooks
	- Continuously log prediction quality signals and latency.
3. Safe rollback with one click
	- Trigger rollback to last stable model from dashboard control.
4. Bias and fairness checks (if fleet data has segments)
	- Validate consistent performance across pack types/usage profiles.
5. Tamper-evident prediction logs
	- Signed event trail for trust and auditability.

### Demo Narrative (How to Present These Features)
1. Detect early: "AI spots thermal risk before failure."
2. Explain clearly: "Top factors and confidence are shown transparently."
3. Act safely: "System auto-heals and recommends next best action."
4. Improve continuously: "Drift-aware MLOps keeps model reliable over time."
5. Scale confidently: "Fleet intelligence extends from one vehicle to many."

### Fast Implementation Order (for limited time)
1. Explainable AI card + natural language summary
2. Early warning lead-time + uncertainty band
3. Sensor fault diagnosis + out-of-distribution alert
4. Copilot chat + smart recommendations
5. RUL forecasting + what-if simulator

## Complete AI Feature Backlog (Expo-Winning)

### A) Core Prediction Intelligence
1. Multi-horizon forecasting (30s, 2m, 10m risk outlook)
2. Per-sensor anomaly scoring and ranked culprit sensors
3. Battery health index (single 0-100 score for judges)
4. Context-aware risk model (mode-aware: charging, cruising, high-load)
5. Event severity classifier (info, warning, critical, emergency)

### B) Explainability and Trust
1. SHAP-style feature attribution per prediction
2. Counterfactuals: "If temperature drops by 4 C, risk becomes WARNING"
3. Confidence decomposition (model uncertainty vs data quality uncertainty)
4. Decision trace panel (inputs -> model path -> output)
5. Human-readable root-cause tags (thermal, electrical, communication)

### C) Prescriptive AI (Actionable Next Steps)
1. AI-generated mitigation playbook by risk type
2. Ranked recommended actions with expected risk reduction
3. "Do now" vs "Do next" action sequencing
4. Operator-safe fallback policy suggestions
5. Auto-generated maintenance ticket text

### D) Reliability and Resilience AI
1. Sensor health scoring and self-healing sensor masking
2. Missing-data imputation with confidence tracking
3. Communication fault predictor (before disconnect occurs)
4. Adaptive sampling rate optimization for unstable periods
5. Failover model routing (primary -> robust fallback model)

### E) MLOps and Continuous Improvement
1. Live drift dashboard (feature drift + prediction drift)
2. Shadow model evaluation in production stream
3. Auto-retrain trigger when drift + error threshold is exceeded
4. Dataset lineage and model lineage view
5. One-click promote/rollback with audit log

### F) Fleet and Business Value AI
1. Fleet-level risk heatmap and top-risk asset ranking
2. Failure-cost avoidance estimator (currency + avoided downtime)
3. SLA risk prediction for maintenance windows
4. Cross-vehicle pattern mining (shared fault signatures)
5. Route/usage-aware battery stress recommendations

### G) Multimodal and Interaction AI
1. Voice query: "Why is Vehicle 2 critical?"
2. Voice alert summarization for live demo narration
3. Natural language to chart query ("show last 3 mins thermal variance")
4. Auto-generated incident report PDF
5. Judge mode overlay (high-level story + KPI impact)

### H) Security and Governance AI
1. Model input tampering detection
2. Prompt/tool abuse guardrails for dashboard copilot
3. Signed prediction records and immutable event timeline
4. PII-safe logging filters (if future user/fleet metadata added)
5. Access-aware recommendations (operator vs admin actions)

### Expo Demo Strategy Map
1. Wow factor: copilot explanation + voice summary + what-if simulator
2. Technical depth: uncertainty, drift, OOD, shadow model, rollback
3. Practical impact: lead-time warning, cost avoidance, prescriptive actions
4. Reliability proof: fault injection + self-heal + graceful degradation
5. Trust proof: explainability + audit trail + safety guardrails