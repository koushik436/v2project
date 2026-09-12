import sys
import re
import json

file_path = r'd:\v2project expo\v2project expo\ev_dashboard.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

chat_code = '''    @app.route("/api/chat", methods=["POST"])
    def chat():
        message = request.json.get("message", "")
        
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"error": "GEMINI_API_KEY is not set"}), 500

        telemetry_context = {
            "prediction": state.get("prediction"),
            "confidence": state.get("confidence"),
            "voltage": state.get("voltage"),
            "current": state.get("current"),
            "temperature": state.get("temperature"),
            "message": state.get("message"),
            "recovery_action": state.get("recovery_action"),
            "rul_minutes": state.get("rul_minutes"),
        }
        
        system_prompt = (
            "You are an expert AI diagnostics assistant for an EV Battery project.\\n"
            "You analyze live telemetry data and answer questions accurately in simple terms.\\n"
            "Current live telemetry JSON:\\n"
            f"{json.dumps(telemetry_context)}\\n"
        )

        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        body = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": message}]}
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 500,
            },
        }

        try:
            req = urllib_request.Request(
                url=url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=15) as rf:
                payload = json.loads(rf.read().decode("utf-8"))
            
            text_parts = []
            for candidate in payload.get("candidates", []) or []:
                content = candidate.get("content", {})
                for part in content.get("parts", []) or []:
                    text_val = part.get("text")
                    if text_val:
                        text_parts.append(text_val.strip())
            
            answer = "\\n".join([segment for segment in text_parts if segment]).strip()
            if not answer:
                answer = "Gemini returned an empty response"
            return jsonify({"response": answer})
            
        except Exception as e:
            error_details = str(e)
            if hasattr(e, "read"):
                try:
                    error_details += " - " + e.read().decode("utf-8")
                except:
                    pass
            logger.error("Gemini chat error: %s", error_details, exc_info=True)
            return jsonify({"error": error_details}), 500'''

pattern = r'    @app\.route\("/api/chat", methods=\["POST"\]\).*?return jsonify\({"error": error_details}\), 500'
new_text = re.sub(pattern, chat_code, text, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Updated ev_dashboard.py successfully.")
