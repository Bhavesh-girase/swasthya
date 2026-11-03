import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from swasthya.main import app, _LOGIN_FAILURES


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.previous = {
            name: os.environ.get(name)
            for name in ("DASHBOARD_USERNAME", "DASHBOARD_PASSWORD", "SESSION_SECRET", "APP_ENV")
        }
        os.environ["DASHBOARD_USERNAME"] = "demo-operator"
        os.environ["DASHBOARD_PASSWORD"] = "test-only-password"
        os.environ["SESSION_SECRET"] = "test-only-session-secret-long-enough"
        os.environ["APP_ENV"] = "development"
        _LOGIN_FAILURES.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        _LOGIN_FAILURES.clear()

    def sign_in(self):
        return self.client.post(
            "/api/login",
            json={"username": "demo-operator", "password": "test-only-password"},
        )

    def test_health_is_public_and_non_sensitive(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "mode": "synthetic-demo"})

    def test_dashboard_and_static_assets_are_served(self):
        page = self.client.get("/")
        css = self.client.get("/static/styles.css")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Safe demo environment", page.text)
        self.assertEqual(css.status_code, 200)
        self.assertIn("Content-Security-Policy", page.headers)

    def test_demo_cases_require_login(self):
        response = self.client.get("/api/demo/cases")
        self.assertEqual(response.status_code, 401)

    def test_login_sets_http_only_session_and_lists_only_fixtures(self):
        login = self.sign_in()
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.headers.get("set-cookie", "").find("HttpOnly") >= 0)
        response = self.client.get("/api/demo/cases")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["live_calls_enabled"])
        self.assertTrue(all(item["id"].startswith("SV-DEMO-") for item in response.json()["cases"]))

    def test_urgent_fixture_uses_fixed_message_without_sarvam(self):
        self.sign_in()
        with patch("swasthya.main._create_sarvam_client") as create_client:
            response = self.client.post("/api/demo/reply", json={"case_id": "SV-DEMO-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fixed safety message")
        create_client.assert_not_called()

    def test_language_preview_uses_conversation_model_without_network(self):
        self.sign_in()
        completion = Mock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="धन्यवाद।"))]
            )
        )
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        with patch("swasthya.main._create_sarvam_client", return_value=fake_client):
            response = self.client.post("/api/demo/reply", json={"case_id": "SV-DEMO-02"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "धन्यवाद।")
        self.assertTrue(response.json()["preview_only"])
        self.assertEqual(completion.call_args.kwargs["model"], "sarvam-105b-conversations")

    def test_voice_demo_runs_all_sarvam_steps_with_fixtures_only(self):
        self.sign_in()
        fake_audio = base64.b64encode(b"synthetic wav bytes").decode("ascii")
        tts = Mock(side_effect=[SimpleNamespace(audios=[fake_audio]), SimpleNamespace(audios=[fake_audio])])
        stt = Mock(return_value=SimpleNamespace(transcript="कल मेरी दवा छूट गई थी।"))
        completion = Mock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="धन्यवाद। दवा में बदलाव न करें।"))]
            )
        )
        fake_client = SimpleNamespace(
            text_to_speech=SimpleNamespace(convert=tts),
            speech_to_text=SimpleNamespace(transcribe=stt),
            chat=SimpleNamespace(completions=completion),
        )
        with patch("swasthya.main._create_sarvam_client", return_value=fake_client):
            response = self.client.post("/api/demo/voice-loop")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stt_model"], "Saaras v4")
        self.assertTrue(response.json()["preview_only"])
        self.assertEqual(tts.call_count, 2)
        self.assertEqual(stt.call_args.kwargs["model"], "saaras:v4")
        self.assertEqual(completion.call_args.kwargs["model"], "sarvam-105b-conversations")


if __name__ == "__main__":
    unittest.main()
