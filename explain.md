# EV Battery Risk Dashboard - Plain English Guide

This file explains the dashboard in simple language. Use it as a quick guide for what each box means and what Gemini can see.

## 1. What this dashboard does

The dashboard watches the battery in real time. It shows the live sensor values, predicts risk, and helps you understand what is happening without reading raw logs.

## 2. Top status area

This is the first thing you see at the top.

### Status summary
This box gives the current battery state at a glance.

- Risk level: tells you whether the battery is normal, warning, or critical.
- Key reason: gives the main reason behind the risk.
- Action buttons: give you shortcuts like review guidance or toggle alerts.

### Risk gauge
This circular dial shows the risk score visually.

- Green means safe.
- Yellow means warning.
- Red means danger.

## 3. Tabs

The dashboard is split into four tabs so the page does not feel crowded.

### Overview
This is the main page for quick checking.

What you see here:
- Copilot box for asking Gemini questions
- Battery snapshot cards
- Confidence and uncertainty information
- Connection and recovery status
- Live sensor cards for temperature, current, and voltage

### Diagnostics
Use this when you want to understand why a warning happened.

What you see here:
- Timeline of recent events
- Decision support cards that explain the likely cause
- Model compare section for comparing model versions

### Analytics
Use this when you want to look at trends and predictions.

What you see here:
- Remaining useful life estimate
- What-if simulation cards
- Trend charts
- Fleet-style ranking view

### System Health
Use this when you want to check if the system itself is healthy.

What you see here:
- Packet health cards
- Uptime, latency, failure rate, and auto-heal counters

## 4. Box-by-box guide

### Copilot box
This is the AI question-and-answer box.

What it does:
- You type a question like "Why is risk high?"
- Gemini reads the current telemetry
- Gemini gives a short answer in plain English

The answer is shown in four parts:
- Summary
- Root cause
- Impact
- Recommended action

### Battery snapshot box
This gives the most important battery values in one place.

It usually shows:
- Battery risk class
- Remaining useful life
- Anomaly score
- A short incident summary

### Confidence box
This box explains how sure the model is.

It helps you answer:
- How confident is the prediction?
- Is there uncertainty?
- What changed most recently?

### Main risk hero box
This is the large central risk panel.

It is meant to answer the question:
- "Is the battery okay right now?"

### Connection and recovery box
This box tells you whether the telemetry stream is active.

It shows:
- Connection state
- Runtime mode
- Data source
- Recovery status

### Temperature, current, voltage cards
These are the live sensor cards.

They show the battery readings directly:
- Temperature
- Current
- Voltage

They are useful because they let you see the raw values, not only the AI summary.

### Timeline box
This shows recent events in order.

It helps you see:
- when the risk changed
- when the connection changed
- when the system recovered

### Decision support box
This explains what the model thinks is driving the problem.

It helps answer:
- Why is risk high?
- Is this a sensor issue?
- What recovery action is being used?

### Model compare box
This lets you compare model versions.

It is useful when you want to:
- inspect the stable model
- inspect a candidate model
- decide whether to promote or roll back a model

### Analytics cards
These are the forward-looking cards.

They are useful for:
- predicting battery life
- testing what happens if values change
- understanding longer-term drift and health

### System health cards
These show whether the backend is running smoothly.

They are useful for:
- packet count
- parse errors
- uptime
- latency
- auto-heal count

## 5. Does Gemini have the reading data?

Yes. Gemini gets the current battery values and recent history from the backend.

### What Gemini receives
Gemini receives a structured context that includes:
- timestamp
- runtime mode
- connection state
- prediction
- confidence
- temperature
- current
- voltage
- recovery action
- sensor fault details
- drift score
- remaining useful life
- health index
- model version
- last 10 to 15 readings for trend analysis

### What this means in practice
Gemini does not talk to the sensor hardware directly. The backend collects the readings, then sends them to Gemini along with your question.

So Gemini can answer things like:
- "Is temperature rising?"
- "Is voltage dropping over time?"
- "What changed in the last few readings?"
- "What should I do next?"

### Important note
The history is used for short-term trend analysis only. It is not a full database of all past readings.

## 6. Simple answer

If you want the shortest possible answer:

- The dashboard shows battery health, risk, and recovery status.
- The tabs separate quick status, troubleshooting, analytics, and system health.
- Gemini can see the latest readings plus the last 10 to 15 values, so it can analyze trends instead of only looking at one point in time.

## 7. Quick summary

- Status summary tells you the current state.
- Overview is for daily monitoring.
- Diagnostics is for troubleshooting.
- Analytics is for trends and forecasting.
- System Health is for backend reliability.
- Gemini uses live readings and recent history to answer questions.
