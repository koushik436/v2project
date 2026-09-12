# V2 Project Expo - No-Fail Hackathon Deployment Package

This package is prepared for reliable hackathon demos with one-command startup, deterministic demo mode, auto-healing behavior, rollback support, and a modern React dashboard UI served by the Python backend.

---

## ⚡ QUICK START (3 Steps)

### **Step 1: Install Dependencies**

From the repository root, activate the virtual environment in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\.venv\Scripts\Activate.ps1"
```

If your prompt is already inside `frontend/`, run `Set-Location ..` first, then activate the environment from the project root.

Important: copy only the PowerShell commands, not the opening or closing ```powershell fence lines.

```powershell
& "./.venv/Scripts/python.exe" -m pip install -r requirements.txt
```

**Expected output:** `Successfully installed all packages` (no errors)

### Optional: Enable Gemini for accurate copilot answers

Set your Gemini key before starting the backend so `/api/copilot` can use live LLM responses grounded in telemetry context.

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key_here"
```

If `GEMINI_API_KEY` is not set (or Gemini is unreachable), the copilot falls back to rule-based responses.

To install the React frontend dependencies and build the production dashboard:

```powershell
Set-Location frontend
npm install
npm run build
Set-Location ..
```

The backend serves the compiled React build from `web/dist/` when it exists.

**Frontend note:** The dashboard UI is now a React app in [`frontend/`](frontend/). The backend serves the compiled output from [`web/dist/`](web/dist/), so if you change the UI source, rebuild it with:

```powershell
Set-Location frontend
npm install
npm run build
```

---

### **Step 2: Choose Your Mode & Run**

Run these commands from the repository root. If your terminal is currently inside `frontend/`, run `Set-Location ..` first.

#### **OPTION A: Demo Mode** (No hardware required - Recommended for judges)

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -DemoMode
```

**Expected output:**
- ✅ Preflight checks pass
- ✅ Backend starts successfully
- ✅ See `Connected` status in UI

---

#### **OPTION B: Live Mode** (With EV hardware on COM6)

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -Port COM6
```

**Note:** Close VS Code Serial Monitor or any other app using COM6 before starting live mode.

**If the backend needs a different port:**

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -DemoMode -WebPort 5001
```

---

### **Step 3: Open Dashboard**

Open your browser and go to:

```
http://127.0.0.1:5000
```

**You should see:**
- System status panel (connection, prediction, confidence)
- Real-time data monitoring
- Model inference results
- Health metrics

If you rebuild the React frontend, refresh the page after `npm run build` completes.

---

## 🛠 Common Commands

### Start demo mode

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -DemoMode
```

Run it from the repository root, or from `frontend/` after `Set-Location ..`.

### Start live mode on a specific port

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -Port COM6
```

### Rebuild the React dashboard

```powershell
Set-Location frontend
npm run build
Set-Location ..
```

### Test the health endpoint

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" -Method Get | ConvertTo-Json -Depth 4
```

### Test the latest state endpoint

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/latest" -Method Get | ConvertTo-Json -Depth 4
```

### Test the AI copilot endpoint

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/copilot" -Method Post -ContentType "application/json" -Body '{"question":"Why is risk high?"}' | ConvertTo-Json -Depth 6
```

Expected response includes:
- `answer` (LLM response)
- `source` (`gemini-1.5-flash` when key is configured, otherwise `rule-based`)

---

## ✅ Verification Checklist

- [ ] No errors in PowerShell console
- [ ] Dashboard loads at `127.0.0.1:5000`
- [ ] Status shows `connected`
- [ ] Data is updating in real-time
- [ ] System health panel is visible

---

## 🧪 Testing & API (Complete Guide)

### **1. Dashboard UI Test**

**URL:** `http://127.0.0.1:5000`

**What to verify:**
- Dashboard loads immediately
- All panels visible (status, health, timeline)
- Real-time data updates flowing in
- Connection status shows `connected`

---

### **2. API Endpoint Tests**

All API endpoints are available at `http://127.0.0.1:5000`

#### **Test 1: Get Latest State (GET)**

**URL:** `http://127.0.0.1:5000/api/latest`

**Command (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/latest" -Method Get
```

**Expected Response:**
```json
{
  "connection": "connected",
  "prediction": "NORMAL",
  "confidence": 0.95,
  "packets_received": 42,
  "uptime_seconds": 125.3,
  "inference_count": 40,
  "model_version": "ev_model_20260327T164222Z",
  "data_source": "demo_simulator",
  ...
}
```

---

#### **Test 2: Get Health Status (GET)**

**URL:** `http://127.0.0.1:5000/api/health`

**Command (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" -Method Get | ConvertTo-Json
```

**Expected Response:**
```json
{
  "connection": "connected",
  "data_status": "healthy",
  "runtime_mode": "demo",
  "data_source": "demo_simulator",
  "packets_received": 42,
  "parse_errors": 0,
  "model_version": "ev_model_20260327T164222Z",
  "model_status": "ready",
  "inference_count": 40,
  "inference_failure_rate": 0.0,
  "inference_avg_latency_ms": 2.5,
  "uptime_seconds": 125.3,
  "auto_heal_count": 0
}
```

---

#### **Test 3A: Inject Disconnect Fault (POST)**

**URL:** `http://127.0.0.1:5000/api/fault/inject`

**Command (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post `
  -ContentType "application/json" `
  -Body '{"type":"disconnect"}'
```

**Expected Response:**
```json
{
  "ok": true,
  "fault": {
    "type": "disconnect",
    "created_at": "2026-05-02T10:30:45Z"
  }
}
```

**Expected UI Behavior:**
- Connection status flips to `disconnected`
- System attempts auto-reconnect
- Toast notification shows recovery attempt

---

#### **Test 3B: Inject Malformed Packet (POST)**

**URL:** `http://127.0.0.1:5000/api/fault/inject`

**Command (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post `
  -ContentType "application/json" `
  -Body '{"type":"malformed"}'
```

**Expected Behavior:**
- `parse_errors` counter increments
- System recovers gracefully (no crash)
- Next packet processes normally

---

#### **Test 3C: Inject Sensor Spike (POST)**

**URL:** `http://127.0.0.1:5000/api/fault/inject`

**Command (PowerShell):**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post `
  -ContentType "application/json" `
  -Body '{"type":"spike"}'
```

**Expected Behavior:**
- Prediction may change to `WARNING` or `CRITICAL`
- Confidence updates
- Timeline logs the anomaly detection

---

### **3. Complete Test Script**

Save as `test_all_endpoints.ps1`:

```powershell
$baseUrl = "http://127.0.0.1:5000"

Write-Host "=== V2 Project Expo - Complete API Test ===" -ForegroundColor Cyan
Write-Host ""

# Test 1: Dashboard UI
Write-Host "TEST 1: Dashboard UI" -ForegroundColor Yellow
Write-Host "URL: $baseUrl"
Write-Host "Open this in browser - should load dashboard"
Write-Host ""

# Test 2: Latest State
Write-Host "TEST 2: Get Latest State" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/latest" -Method Get
    Write-Host "✅ Connection: $($response.connection)"
    Write-Host "✅ Prediction: $($response.prediction)"
    Write-Host "✅ Uptime: $($response.uptime_seconds)s"
    Write-Host "✅ Packets Received: $($response.packets_received)"
} catch {
    Write-Host "❌ Failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 3: Health Status
Write-Host "TEST 3: Get Health Status" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/health" -Method Get
    Write-Host "✅ Data Status: $($response.data_status)"
    Write-Host "✅ Model Status: $($response.model_status)"
    Write-Host "✅ Inference Avg Latency: $($response.inference_avg_latency_ms)ms"
    Write-Host "✅ Auto-heal Count: $($response.auto_heal_count)"
} catch {
    Write-Host "❌ Failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 4: Fault Injection - Disconnect
Write-Host "TEST 4: Inject Disconnect Fault" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/fault/inject" -Method Post `
      -ContentType "application/json" `
      -Body '{"type":"disconnect"}'
    Write-Host "✅ Fault injected: $($response.fault.type)"
    Write-Host "   (Watch dashboard for auto-recovery)"
} catch {
    Write-Host "❌ Failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 5: Fault Injection - Malformed
Write-Host "TEST 5: Inject Malformed Packet" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/fault/inject" -Method Post `
      -ContentType "application/json" `
      -Body '{"type":"malformed"}'
    Write-Host "✅ Fault injected: $($response.fault.type)"
    Write-Host "   (Watch parse_errors counter increase)"
} catch {
    Write-Host "❌ Failed: $_" -ForegroundColor Red
}
Write-Host ""

# Test 6: Fault Injection - Spike
Write-Host "TEST 6: Inject Sensor Spike" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/fault/inject" -Method Post `
      -ContentType "application/json" `
      -Body '{"type":"spike"}'
    Write-Host "✅ Fault injected: $($response.fault.type)"
    Write-Host "   (Watch for prediction change)"
} catch {
    Write-Host "❌ Failed: $_" -ForegroundColor Red
}
Write-Host ""

Write-Host "=== All Tests Complete ===" -ForegroundColor Green
```

**How to run:**
```powershell
powershell -ExecutionPolicy Bypass -File test_all_endpoints.ps1
```

---

### **4. Test Checklist**

While running tests, verify:

- [ ] Dashboard loads at `http://127.0.0.1:5000`
- [ ] `/api/latest` returns current state with all fields
- [ ] `/api/health` shows system metrics (latency, inference count, etc.)
- [ ] Disconnect fault is handled gracefully (auto-reconnect)
- [ ] Malformed packet increments `parse_errors`
- [ ] Spike fault updates prediction state
- [ ] All tests complete without crashes
- [ ] UI remains responsive during all fault tests

---

## 1. Exact Run Commands

### Install dependencies

```powershell
& "./.venv/Scripts/python.exe" -m pip install -r requirements.txt
```

### One-command startup (recommended for judges)

Demo mode (fully deterministic, no hardware required):

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -DemoMode
```

Live mode with serial device:

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -Port COM3
```

Open UI:

- http://127.0.0.1:5000

## 2. Startup & Reliability Guarantees

### One-command startup

- `run_hackathon.ps1` -> wrapper entry point.
- `scripts/start_hackathon.ps1` -> launches preflight + backend and supervises restart.

### Preflight checks (automatic)

`start_hackathon.ps1` runs `scripts/preflight_check.py` for:

- Dependency validation (`flask`, `pandas`, `serial`, `joblib`, `sklearn`)
- Model availability (pointer model or `ev_risk_model.joblib`)
- Serial/device availability (when not in demo mode)

### Auto-restart strategy

- Backend process is supervised in `scripts/start_hackathon.ps1`
- On unexpected crash, backend restarts after 2 seconds
- Data ingestion auto-heals with reconnect logic
- Optional automatic synthetic fallback if serial is unavailable

## 3. Demo Safety (CRITICAL)

### Deterministic Demo Mode

Single trigger:

```powershell
powershell -ExecutionPolicy Bypass -File ./run_hackathon.ps1 -DemoMode
```

Sequence is deterministic and timed:

- NORMAL -> WARNING -> CRITICAL -> RECOVERY

### Hardware failure fallback

If serial input fails in live mode and fallback is enabled (default in start script):

- System auto-switches to synthetic stream
- UI remains live and fully functional
- Recovery/auto-heal message is shown

### External dependency independence

Demo mode runs without hardware input and still exercises:

- model inference path
- dashboard updates
- fault handling
- timeline/toast recovery cues

## 4. System Visibility

UI includes:

- Connection/status indicators (`connected`, `stale`, `disconnected`, `reconnecting`)
- Packet health panel
- System health panel:
  - runtime mode
  - data source
  - model version
  - model status
  - uptime
  - avg latency
  - inference failure rate
  - auto-heal count

API endpoints:

- `/api/latest` - full runtime state
- `/api/health` - health summary

## 5. Failure Handling and Graceful Degradation

Implemented behavior:

- If model inference fails:
  - uses last known prediction (or rule-based fallback)
  - model status becomes `degraded`
  - recovery notification is emitted
- If data is missing:
  - data status becomes degraded/stale
  - warning state persists without crash
- UI remains responsive:
  - polling continues
  - stale overlay + recovery toasts provide operator feedback

## 6. Fault Injection Rehearsal

### Built-in deterministic rehearsals in Demo Mode

Demo mode automatically simulates:

- malformed/corrupted packet
- serial disconnect/unplug event
- sudden sensor spike

### Manual fault injection in live mode

Use API:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post -ContentType "application/json" -Body '{"type":"disconnect"}'
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post -ContentType "application/json" -Body '{"type":"malformed"}'
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/fault/inject" -Method Post -ContentType "application/json" -Body '{"type":"spike"}'
```

Expected result: system handles each case without crash and logs recovery/fault messages.

## 7. 2-3 Minute Demo Script (Timed)

Total target: ~2 minutes 40 seconds

### 00:00-00:20 Startup

Action:

- Run `run_hackathon.ps1 -DemoMode`
- Open browser dashboard

Expected UI:

- connection becomes `connected`
- mode shows `demo`
- data source shows `demo_simulator`

Judge talking point:

- "We can run full-stack with zero external hardware risk."

### 00:20-00:55 NORMAL phase

Expected UI:

- prediction `NORMAL`
- low risk score
- stable green visual tone

Judge talking point:

- "This is healthy baseline telemetry with live ML inference and monitoring."

### 00:55-01:30 WARNING phase

Expected UI:

- prediction flips to `WARNING`
- confidence updates
- timeline logs state transition

Judge talking point:

- "The system detects early degradation and keeps operators informed before failure."

### 01:30-02:10 CRITICAL + fault rehearsals

Expected UI:

- prediction `CRITICAL`
- fail-safe indicators activate
- malformed packet event handled safely
- disconnect event simulated and auto-healed
- spike event shown and absorbed

Judge talking point:

- "We tested corruption, disconnects, and spikes during live operation without crashes."

### 02:10-02:40 RECOVERY phase

Expected UI:

- transition back to safer state
- recovery notification appears
- uptime and health metrics continue increasing

Judge talking point:

- "The core value is resilience: detect, degrade gracefully, auto-heal, and recover visibly."

## 8. Operator Runbook

### Start

- Demo mode: `run_hackathon.ps1 -DemoMode`
- Live mode: `run_hackathon.ps1 -Port COM3`

### Monitor

- UI status chips (`connection`, `prediction`, `confidence`)
- system health panel for mode/source/version/uptime/latency/failure rate
- timeline for transitions and recovery notices

### Recover

1. If serial drops: system auto-reconnects or auto-switches to synthetic fallback
2. If model degrades: system uses last known prediction and shows recovery message
3. If backend exits unexpectedly: startup supervisor restarts it automatically

### Quick debug steps

1. Confirm preflight by rerunning `scripts/preflight_check.py`
2. Check runtime logs in `logs/runtime/backend.log`
3. Check prediction events in `logs/prediction_events.jsonl`
4. Query `/api/health` to verify mode/status counters

## 9. Rollback Plan (Instant)

Rollback command:

```powershell
powershell -ExecutionPolicy Bypass -File ./scripts/rollback_now.ps1
```

What it does:

- Executes `train_ev_model.py --action rollback`
- Re-points stable model to previous model pointer
- Restores root `ev_risk_model.joblib` compatibility target

After rollback:

- restart backend with `run_hackathon.ps1`

## 10. Project Structure (Deployment-Oriented)

```text
.
|- run_hackathon.ps1
|- scripts/
|  |- start_hackathon.ps1
|  |- preflight_check.py
|  |- rollback_now.ps1
|- ev_dashboard.py
|- ev_battery_monitor.py
|- train_ev_model.py
|- mlops_runtime.py
|- requirements.txt
|- models/
|  |- candidates/
|  |- pointers/stable.json
|- logs/
|  |- runtime/backend.log
|  |- prediction_events.jsonl
|- web/
|  |- index.html
|  |- styles.css
|  |- app.js
```

## 11. Rehearsal Checklist

- [ ] Dependencies installed in `.venv`
- [ ] Preflight passes
- [ ] Dashboard opens on `127.0.0.1:5000`
- [ ] Demo mode transitions NORMAL -> WARNING -> CRITICAL -> RECOVERY
- [ ] Fault rehearsals observed (malformed, disconnect, spike)
- [ ] System health metrics visible and updating
- [ ] Recovery notifications appear
- [ ] Backend restart behavior verified (kill once, observe restart)
- [ ] Rollback command tested
- [ ] Logs verified (`logs/runtime/backend.log`, `logs/prediction_events.jsonl`)

---

This package is tuned for hackathon reliability first: deterministic operation, graceful degradation, and visible recovery behavior under fault conditions.
