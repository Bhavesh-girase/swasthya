from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sarvamai import SarvamAI


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_COOKIE = "sv_session"
SESSION_TTL_SECONDS = 30 * 60
_DEVELOPMENT_SESSION_SECRET = secrets.token_bytes(32)
_LOGIN_FAILURES: dict[str, list[float]] = {}
_SARVAM_CLIENT: SarvamAI | None = None


def load_local_env() -> None:
    """Load simple KEY=value lines without overriding the real environment."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and value and not os.getenv(name):
            os.environ[name] = value


load_local_env()


DEMO_CASES = [
    {
        "id": "SV-DEMO-01",
        "label": "Demo patient 01",
        "language": "हिन्दी",
        "language_code": "hi-IN",
        "day": "Day 1",
        "risk": "critical",
        "signal": "Synthetic red-flag scenario",
        "summary": "Human review needed immediately",
        "updated": "Just now",
    },
    {
        "id": "SV-DEMO-02",
        "label": "Demo patient 02",
        "language": "मराठी",
        "language_code": "mr-IN",
        "day": "Day 3",
        "risk": "follow-up",
        "signal": "Synthetic missed-dose scenario",
        "summary": "Follow-up requested",
        "updated": "8 min ago",
    },
    {
        "id": "SV-DEMO-03",
        "label": "Demo patient 03",
        "language": "தமிழ்",
        "language_code": "ta-IN",
        "day": "Day 7",
        "risk": "routine",
        "signal": "Synthetic routine check-in",
        "summary": "Routine check-in complete",
        "updated": "22 min ago",
    },
    {
        "id": "SV-DEMO-04",
        "label": "Demo patient 04",
        "language": "తెలుగు",
        "language_code": "te-IN",
        "day": "Day 1",
        "risk": "follow-up",
        "signal": "Synthetic unclear-response scenario",
        "summary": "Needs a patient human check-in",
        "updated": "41 min ago",
    },
    {
        "id": "SV-DEMO-05",
        "label": "Demo patient 05",
        "language": "বাংলা",
        "language_code": "bn-IN",
        "day": "Day 3",
        "risk": "routine",
        "signal": "Synthetic appointment reminder scenario",
        "summary": "Follow-up remembered",
        "updated": "1 hr ago",
    },
]
DEMO_CASES_BY_ID = {case["id"]: case for case in DEMO_CASES}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class DemoReplyRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=40)


def _session_secret() -> bytes | None:
    configured = os.getenv("SESSION_SECRET", "")
    if configured:
        encoded = configured.encode("utf-8")
        return encoded if len(encoded) >= 32 else None
    if os.getenv("APP_ENV", "development").lower() == "production":
        return None
    return _DEVELOPMENT_SESSION_SECRET


def _encode_session(username: str) -> str:
    secret = _session_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="Dashboard session security is not configured.")
    payload = json.dumps(
        {
            "sub": username,
            "exp": int(time.time()) + SESSION_TTL_SECONDS,
            "nonce": secrets.token_urlsafe(12),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _session_username(token: str | None) -> str | None:
    secret = _session_secret()
    if not token or secret is None or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(secret, encoded.encode("ascii", errors="ignore"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
    except (ValueError, json.JSONDecodeError):
        return None
    username = os.getenv("DASHBOARD_USERNAME", "")
    if payload.get("sub") != username or payload.get("exp", 0) <= time.time():
        return None
    return username


def require_operator(request: Request) -> str:
    if not os.getenv("DASHBOARD_USERNAME") or not os.getenv("DASHBOARD_PASSWORD"):
        raise HTTPException(status_code=503, detail="Configure dashboard credentials in .env first.")
    username = _session_username(request.cookies.get(SESSION_COOKIE))
    if not username:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return username


def _login_is_throttled(client_ip: str) -> bool:
    now = time.monotonic()
    recent = [attempt for attempt in _LOGIN_FAILURES.get(client_ip, []) if now - attempt < 60]
    _LOGIN_FAILURES[client_ip] = recent
    return len(recent) >= 5


def _record_login_failure(client_ip: str) -> None:
    _LOGIN_FAILURES.setdefault(client_ip, []).append(time.monotonic())


def _create_sarvam_client() -> SarvamAI | None:
    global _SARVAM_CLIENT
    if _SARVAM_CLIENT is not None:
        return _SARVAM_CLIENT
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return None
    _SARVAM_CLIENT = SarvamAI(api_subscription_key=api_key)
    return _SARVAM_CLIENT


app = FastAPI(
    title="Swasthya-Vaani",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if os.getenv("APP_ENV", "development").lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "synthetic-demo"}


@app.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
    username = os.getenv("DASHBOARD_USERNAME", "")
    password = os.getenv("DASHBOARD_PASSWORD", "")
    if not username or not password or _session_secret() is None:
        raise HTTPException(status_code=503, detail="Dashboard credentials and session secret are required.")

    client_ip = request.client.host if request.client else "unknown"
    if _login_is_throttled(client_ip):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in a minute.")

    valid_username = hmac.compare_digest(payload.username.encode("utf-8"), username.encode("utf-8"))
    valid_password = hmac.compare_digest(payload.password.encode("utf-8"), password.encode("utf-8"))
    if not (valid_username and valid_password):
        _record_login_failure(client_ip)
        raise HTTPException(status_code=401, detail="The username or password is incorrect.")

    _LOGIN_FAILURES.pop(client_ip, None)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_encode_session(username),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        samesite="strict",
        path="/",
    )
    return {"ok": True}


@app.post("/api/logout", dependencies=[Depends(require_operator)])
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=os.getenv("APP_ENV", "development").lower() == "production",
        samesite="strict",
        path="/",
    )
    return {"ok": True}


@app.get("/api/demo/cases", dependencies=[Depends(require_operator)])
def list_demo_cases() -> dict[str, object]:
    counts = {
        "critical": sum(case["risk"] == "critical" for case in DEMO_CASES),
        "follow_up": sum(case["risk"] == "follow-up" for case in DEMO_CASES),
        "routine": sum(case["risk"] == "routine" for case in DEMO_CASES),
    }
    return {"cases": DEMO_CASES, "counts": counts, "live_calls_enabled": False}


@app.post("/api/demo/reply", dependencies=[Depends(require_operator)])
def generate_demo_reply(payload: DemoReplyRequest) -> dict[str, str | bool]:
    case = DEMO_CASES_BY_ID.get(payload.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Demo case not found.")

    if case["risk"] == "critical":
        return {
            "reply": "This demo has not sent an alert. A real red-flag report must go to an on-duty human immediately.",
            "source": "fixed safety message",
            "preview_only": True,
        }

    client = _create_sarvam_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Sarvam is not configured. Add SARVAM_API_KEY to .env.")

    try:
        result = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write a short, warm acknowledgement for a fictional post-discharge follow-up demo. "
                        "Use simple everyday language in the requested language. Do not diagnose, interpret symptoms, "
                        "recommend or change medicines or doses, promise that a person was contacted, or add emergency "
                        "instructions. Do not ask for personal details. Return only the spoken message, at most two short sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Language: {case['language']} ({case['language_code']}). "
                        "Render this fixed message naturally: ‘Thank you for sharing. I will note this for your care team. "
                        "Is there anything else you would like me to note?’ This is fictional demo text; do not add facts."
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=160,
            reasoning_effort=None,
        )
        reply = result.choices[0].message.content
    except Exception:
        # Avoid returning vendor exception text, request data, or credentials to the browser.
        raise HTTPException(status_code=502, detail="Sarvam could not generate the demo reply. Please try again.") from None

    if not reply:
        raise HTTPException(status_code=502, detail="Sarvam returned an empty demo reply.")
    return {"reply": reply.strip(), "source": "Sarvam 105B Conversations", "preview_only": True}


@app.post("/api/demo/voice-loop", dependencies=[Depends(require_operator)])
def run_demo_voice_loop() -> dict[str, str | bool]:
    """Run one fixed, fictional Hindi voice exchange through Sarvam's APIs."""
    client = _create_sarvam_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Sarvam is not configured. Add SARVAM_API_KEY to .env.")

    fictional_utterance = "कल मेरी दवा छूट गई थी क्योंकि मुझे मितली हो रही थी।"
    try:
        patient_audio = client.text_to_speech.convert(
            text=fictional_utterance,
            language_code="hi-IN",
            model="bulbul:v4-flash",
            speaker="aparna_hi_customer",
            speech_sample_rate=8000,
            output_audio_codec="wav",
            pace=0.9,
            enable_preprocessing=True,
        )
        patient_audio_b64 = "".join(patient_audio.audios)
        patient_audio_bytes = base64.b64decode(patient_audio_b64)

        transcription = client.speech_to_text.transcribe(
            file=("fictional-patient.wav", io.BytesIO(patient_audio_bytes)),
            model="saaras:v4",
            mode="transcribe",
            language_code="hi-IN",
            input_audio_codec="wav",
        )
        transcript = (transcription.transcript or "").strip()
        if not transcript:
            raise ValueError("Empty transcription")

        completion = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are generating a fictional demo reply, not providing care. In simple Hindi, "
                        "render this approved message in at most two short sentences: thank the caller for sharing, "
                        "say not to change medicines based on this call, and offer to note the concern for their care team. "
                        "Do not diagnose, recommend a dose, say a care team has been contacted, or add emergency instructions. "
                        "Return only the spoken reply."
                    ),
                },
                {"role": "user", "content": f"Fictional caller said: {transcript}"},
            ],
            temperature=0.2,
            max_tokens=150,
            reasoning_effort=None,
        )
        reply = (completion.choices[0].message.content or "").strip()
        if not reply:
            raise ValueError("Empty reply")

        spoken_reply = client.text_to_speech.convert(
            text=reply,
            language_code="hi-IN",
            model="bulbul:v4-flash",
            speaker="ritu_hi_customer_warm",
            speech_sample_rate=22050,
            output_audio_codec="wav",
            pace=0.9,
            enable_preprocessing=True,
        )
        reply_audio_b64 = "".join(spoken_reply.audios)
        if not patient_audio_b64 or not reply_audio_b64:
            raise ValueError("Empty audio")
    except Exception:
        # Do not return vendor errors, user data, or credentials to the browser.
        raise HTTPException(status_code=502, detail="The Sarvam voice demo could not finish. Please try again.") from None

    return {
        "transcript": transcript,
        "reply": reply,
        "patient_audio_base64": patient_audio_b64,
        "reply_audio_base64": reply_audio_b64,
        "stt_model": "Saaras v4",
        "chat_model": "Sarvam 105B Conversations",
        "tts_model": "Bulbul v4 Flash",
        "sample_disposition": "Human follow-up scenario · fictional only",
        "preview_only": True,
    }
