import os
from flask import Flask, jsonify, request
import json
import logging

app = Flask(__name__)

# Configure logging to flow into Gunicorn/Render logs
_gunicorn_logger = logging.getLogger('gunicorn.error')
if _gunicorn_logger.handlers:
    app.logger.handlers = _gunicorn_logger.handlers
    app.logger.setLevel(_gunicorn_logger.level)
app.logger.propagate = False

# 🔹 Config (prefer environment variables on Render)
APP_ID = int(os.environ.get("APP_ID", "4222424"))
SECRET = os.environ.get("SECRET", "ccf0a102-ea6a-4f26-8d1c-7a1732eb0780")
FROM_NUMBER = os.environ.get("FROM_NUMBER", "917943446575")
TO_NUMBER = os.environ.get("TO_NUMBER", "919518337344")

# CDN file keys from your TeleCMI portal (2.png -> key Name column)
FILE_KEY_1 = os.environ.get("FILE_KEY_1", "1760350048331ElevenLabs20251009T151503AnikaSweetLivelyHindiSocialMediaVoicepvcsp99s100sb100se0bm2wav6ca049c0-a81c-11f0-9f7b-3b2ce86cca8b_piopiy.wav")
FILE_KEY_2 = os.environ.get("FILE_KEY_2", "1760362929284ElevenLabs20251009T151214AnikaSweetLivelyHindiSocialMediaVoicepvcsp99s100sb100se0bm2wav6a456e30-a83a-11f0-9f7b-3b2ce86cca8b_piopiy.wav")

# === 1️⃣ MAIN API — Generate Play Input JSON ===
@app.route('/make_call', methods=['POST'])
def make_call():
    try:
        # Optionally take input from frontend
        data = request.get_json() or {}

        # If user provides new to/from, override defaults
        from_number = data.get("from", FROM_NUMBER)
        to_number = data.get("to", TO_NUMBER)
        file_name = data.get("file_name", FILE_KEY_1)

        # This will be your logic that Piopiy/GIMA expects
        action_url = request.url_root.rstrip("/") + "/dtmf"
        payload = {
            "appid": APP_ID,
            "secret": SECRET,
            "from": from_number,
            "to": to_number,
            "extra_params": {"order_id": "ORD12345"},
            "pcmo": [
                {
                    "action": "play_get_input",
                    "file_name": file_name,
                    "max_digit": 1,  # collect only 1 digit and proceed immediately
                    "max_retry": 2,
                    "timeout": 10,
                    "action_url": action_url  # Your DTMF handling API
                }
            ]
        }

        return jsonify(payload), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === 2️⃣ Inbound Answer URL — Return initial PCMO (screenshot 1 shows /call)
@app.route('/call', methods=['POST'])
def answer_call():
    try:
        action_url = request.url_root.rstrip("/") + "/dtmf"
        return jsonify([
            {
                "action": "play_get_input",
                "file_name": FILE_KEY_1,
                "max_digit": 1,
                "max_retry": 2,
                "timeout": 10,
                "action_url": action_url
            }
        ]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === 3️⃣ DTMF HANDLER — When user presses keys ===
@app.route('/dtmf', methods=['POST'])
def handle_dtmf():
    try:
        # Be tolerant to different clients (JSON, form-encoded, or raw)
        data = request.get_json(silent=True) or {}
        if not data and request.form:
            data = request.form.to_dict()
        if not data and request.data:
            try:
                data = json.loads(request.data.decode('utf-8'))
            except Exception:
                data = {}

        # TeleCMI/clients may send 'dtmf', 'digit', or 'digits'
        digit = str((data.get("dtmf") or data.get("digit") or data.get("digits") or "")).strip()

        # Debug: log headers and payload
        try:
            app.logger.info("[dtmf] headers=%s", dict(request.headers))
            app.logger.info("[dtmf] raw=%s", request.data.decode('utf-8', errors='ignore'))
            app.logger.info("[dtmf] parsed=%s", data)
        except Exception:
            pass

        if not digit:
            # Bad/missing input — ask again instead of 500
            action_url = request.url_root.rstrip("/") + "/dtmf"
            resp = [{
                "action": "play_get_input",
                "file_name": FILE_KEY_1,
                "max_digit": 1,
                "max_retry": 1,
                "timeout": 10,
                "action_url": action_url
            }]
            app.logger.info("[dtmf] response=%s", json.dumps(resp))
            return jsonify(resp), 200

        app.logger.info("📞 User pressed: %s", digit)

        # Logic for pressed key
        # For any valid input, play your second audio from CDN and keep the call alive
        if digit in {"1", "2"}:
            # Use a single play_get_input with FILE_KEY_2 so the provider plays and waits without ending the call
            action_url = request.url_root.rstrip("/") + "/dtmf"
            actions = [{
                "action": "play_get_input",
                "file_name": FILE_KEY_2,
                "max_digit": 1,
                "max_retry": 1,
                "timeout": 10,
                "action_url": action_url
            }]
        else:
            # Repeat the first prompt on invalid input
            action_url = request.url_root.rstrip("/") + "/dtmf"
            actions = [{
                "action": "play_get_input",
                "file_name": FILE_KEY_1,
                "max_digit": 1,
                "max_retry": 1,
                "timeout": 10,
                "action_url": action_url
            }]

        # IMPORTANT: TeleCMI expects PCMO wrapper in the webhook response
        resp = actions
        app.logger.info("[dtmf] response=%s", json.dumps(resp))
        return jsonify(resp), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === Health and index ===
@app.route('/', methods=['GET'])
def index():
    return "IVR service running", 200

@app.route('/healthz', methods=['GET'])
def healthz():
    return "ok", 200


# === Run the Flask app ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.logger.info("🚀 Flask Server Running — Ready for Piopiy JSON API Logic")
    app.run(host="0.0.0.0", port=port, debug=False)
