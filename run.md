# Run Order

Execute these commands from the repository root in the exact order shown.

## Demo mode

1. Set the PowerShell execution policy for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

2. Activate the virtual environment:

```powershell
& ".\.venv\Scripts\Activate.ps1"
```

3. (Optional) Rebuild the React frontend if changes were made:

```powershell
Set-Location frontend
npm install
npm run build
Set-Location ..
```

4. Start the project in demo mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_hackathon.ps1 -DemoMode
```

5. Open the dashboard in a browser:

```text
http://127.0.0.1:5000
```

6. Verify the latest state endpoint:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/latest" -Method Get | ConvertTo-Json -Depth 4
```

7. Verify the copilot endpoint:

```powershell
$body = @{ question = 'What is the current battery risk and why?' } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/copilot" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```

## Live mode on COM6

1. Set the PowerShell execution policy for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

2. Activate the virtual environment:

```powershell
& ".\.venv\Scripts\Activate.ps1"
```

3. Start the project in live mode on COM6:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_hackathon.ps1 -Port COM6
```

4. Open the dashboard in a browser:

```text
http://127.0.0.1:5000
```

5. Verify the latest state endpoint:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/latest" -Method Get | ConvertTo-Json -Depth 4
```

6. Verify the copilot endpoint:

```powershell
$body = @{ question = 'What is the current battery risk and why?' } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/copilot" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```
