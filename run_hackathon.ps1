param(
    [switch]$DemoMode,
    [string]$Port = "COM3",
    [int]$WebPort = 5000
)

& "$PSScriptRoot\scripts\start_hackathon.ps1" -DemoMode:$DemoMode -Port $Port -WebPort $WebPort
