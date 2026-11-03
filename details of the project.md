# MISSION: BUILD "SWASTHYA-VAANI" — AUTOMATED INDIC OUTBOUND POST-DISCHARGE COMPANION

## 1. PROBLEM STATEMENT & RURAL INDIAN REALITY
In rural India, post-discharge mortality and readmission rates are high because patients (often elderly, illiterate, or daily-wage earners) cannot read discharge summaries, do not recognize pharmacological medicine names (e.g., they know "subah ki laal goli" or "BP wali goli", not "Atorvastatin 20mg"), and have no access to smartphones (relying on basic 2G feature phones).

Build **Swasthya-Vaani**: An automated outbound voice calling system powered by **Sarvam AI** that:
1. Calls discharged patients over the phone at scheduled intervals (Day 1, Day 3, Day 7).
2. Speaks in their regional mother tongue (Hindi, Marathi, Telugu, Tamil, Bengali, etc.) using natural colloquial phrasing.
3. Conducts a structured, non-diagnostic check-in covering:
   - **Medication Adherence** (using descriptive physical cues like color/time).
   - **Critical Symptoms & Red Flags** (e.g., chest pain, shortness of breath, high fever).
   - **Follow-up Clinic / PHC Visit Confirmation**.
4. Detects anomalies (missed doses, severe symptoms) and immediately triggers **tiered escalations** to local ASHA workers, ANMs (Auxiliary Nurse Midwives), or the hospital discharge coordinator via WhatsApp/SMS alerts and a real-time dashboard.

---

## 2. STRICT GUARDRAILS & CLINICAL PROTOCOLS
- **Non-Diagnostic Policy**: The voice agent MUST NOT provide medical diagnoses or prescribe/alter dosages. If a patient asks "Can I stop this medicine?", the bot replies: *"Main doctor nahi hoon, isliye goli band mat kijiye. Main aapke ASHA tai / hospital coordinator ko turant soochit kar rahi hoon."*
- **Triage Classification**:
  - 🟢 **Green (Routine)**: Taking medicines on time, feeling better, appointment remembered.
  - 🟡 **Yellow (Advisory/Follow-up)**: Missed 1 dose due to nausea/cost, forgot appointment date. Escalation: Logged for ASHA home check within 24 hours.
  - 🔴 **Red (Critical Emergency)**: Clinician-approved red-flag symptoms (e.g. severe chest pain, breathing difficulty, uncontrolled bleeding) OR a clinician-configured medication rule. Escalation: immediate human review through a configured provider channel; use only locally approved emergency instructions (for example, 112 / state ambulance 108). Confirm delivery before saying an alert was sent.

---

## 3. TECH STACK SPECIFICATION
- **Backend target**: FastAPI (Python 3.10+), `httpx` (async), `pydantic`, Postgres for production. Use a scheduler only when a real, consent-aware call provider is configured. Phase 1 uses synthetic in-memory fixtures and has no patient database or call scheduler.
- **Frontend target**: Next.js / React for the full hospital coordinator / PHC dashboard. Phase 1 uses a small same-origin HTML/CSS/JS dashboard to avoid an extra build chain and ship quickly:
  - Live patient roster with risk badges (Red / Yellow / Green).
  - Call audio recordings, Indic transcripts, and auto-generated clinical summaries.
  - 1-Click "Call ASHA Worker" or "Trigger Re-call" actions.
- **AI Stack (Sarvam AI APIs exclusively)**:
  - **Speech-to-Text (STT)**: Sarvam Saaras API (`POST /speech-to-text`) supporting 8kHz/16kHz telephony audio, noisy rural acoustic backgrounds, and code-mixing (e.g., Marathi + Hindi + English loan words).
  - **Conversational Intelligence**: Sarvam 105B / Chat API for empathetic, simple vernacular phrasing and optional structured extraction. A clinician-approved deterministic protocol—not the LLM—owns risk classification and escalation.
  - **Text-to-Speech (TTS)**: Sarvam Bulbul API (`POST /text-to-speech`) with language-tested voices. Bulbul v4 Flash uses persona IDs; short names such as `shubh`, `ritu`, and `priya` belong to the v3 voice set. Tune pace only after comprehension testing with older speakers.
- **Telephony / Audio Interface**:
  - For production outbound campaigns, prefer Sarvam Voice Agents or a separately configured telephony provider; model API credentials alone cannot place calls. Keep a browser simulator for test-only flows, and require explicit consent before dialing.

---

## 4. RURAL ACCESSIBILITY & CONVERSATIONAL DESIGN
1. **Physical Medicine Mapping (Color/Shape Taggings)**:
   - In the patient profile, doctors register medicines with visual descriptors:
     `{"name": "Metformin 500mg", "vernacular_cue": "khana khane ke baad wali safed lambi goli"}`
   - The bot asks: *"Aapne dopahar ke khane ke baad wali safed lambi goli le li thi na?"*
2. **Hum-Haan & Colloquial Affirmation Handling**:
   - Rural speakers often respond with "Hao", "Haa re", "Nahi liya", "Chakkar aavat ba", "Thik lag raha hai". The LLM intent classifier must map these colloquial expressions reliably.
3. **Patience & Re-prompting**:
   - If the patient stays silent or speaks faintly, re-prompt gently in their language: *"Baba, kya aap mujhe sun pa rahe hain?"*

---

## 5. ARCHITECTURE & ENDPOINT SPECIFICATIONS

### Environment Variables (`.env`)
```env
SARVAM_API_KEY=
PORT=8000
DATABASE_URL="sqlite:///./swasthya.db"
COORDINATOR_PHONE= # provision via a deployment secret after consent and escalation setup
```

---

## 6. PLAN REVIEW: SAFETY, INDIA FIT, AND IMPLEMENTATION ORDER

### Corrections to the original design

1. **Separate model APIs from calling.** Sarvam chat/STT/TTS APIs do not themselves place outbound calls or send SMS/WhatsApp. Sarvam Voice Agents supports telephony and outbound campaigns; it is a separate product with its own API key, organization/workspace IDs, and telephony setup. Use it for production dialing rather than building a dialer on top of model endpoints.
2. **Use the right audio transport.** Saaras synchronous REST handles short audio only (up to 30 seconds); real calls need streaming or the managed Voice Agents path, while longer recordings need batch processing. Test actual 8 kHz call audio, dialects, and noisy environments before selecting a model/configuration.
3. **Do not delegate clinical urgency to an LLM.** A clinician-approved deterministic protocol must own red-flag rules. Sarvam may assist with language and structured extraction, but its output cannot downgrade urgency, change a care plan, or trigger an automated clinical decision. Ambiguous speech routes to a human.
4. **Do not treat medicine color as identity.** A visual cue is a patient aid only; the source of truth remains the clinician-approved medication schedule. Never infer a drug, dose, or missed-dose action from color/shape.
5. **Consent and data protection are launch requirements.** Obtain explicit consent for calls, recording/transcription, caregiver contact, and third-party processing; support opt-out and deletion; minimize retention; protect access with least privilege, HTTPS, audit trails, and managed secrets. Do not upload identifiable health data to Sarvam until the organization has approved the relevant privacy/legal terms and retention settings.
6. **Emergency wording must be local and human-approved.** Keep district/state emergency and PHC details in a verified directory, not model-generated text. The prototype must never claim that an alert or call was sent unless the provider confirms it.

### India-specific product additions

- **Shared-phone privacy mode:** Ask whether it is safe to speak, use neutral caller-ID/voicemail wording, avoid sensitive medicine details in SMS, and offer a patient-authorized caregiver path.
- **Voice plus keypad fallback:** Let feature-phone users answer with speech or DTMF keys when audio is weak, speech is unclear, or the caller prefers not to speak aloud.
- **Patient-chosen call windows:** Respect local work, market, prayer, meal, and quiet hours; cap retries and offer a callback time instead of repeatedly dialing.
- **Dialect and code-switch feedback loop:** Let ASHA/ANM reviewers correct transcript intent and language labels (with consent); use corrections to evaluate regional quality, not to silently alter clinical rules.
- **Verified local care navigation:** Show the patient’s assigned PHC, approved follow-up hours, and district escalation contacts from a maintained directory. A later ABDM/ABHA connection must be optional and consent-based.
- **Low-connectivity resilience:** Keep the phone call as the primary interface, support short resumable exchanges, and use SMS only for neutral, consented reminders or human follow-up.

### Phase 1 delivered in this project

- A local, password-protected dashboard with clearly synthetic cases and a Hindi voice loop: Bulbul v4 Flash → Saaras v4 → Sarvam 105B Conversations → Bulbul v4 Flash.
- No real patient database, live calling, recording, SMS, WhatsApp, or automatic escalation. The urgent scenario uses a fixed safety message and never calls the model.
- Docker packaging and a health endpoint for a later hosted demo. Production use still requires a deployment target, HTTPS, managed secrets, encrypted India-hosted storage, clinical approval, and configured Sarvam Voice Agents/telephony credentials.

### Sarvam documentation references

- [Getting started](https://docs.sarvam.ai/api/getting-started/welcome)
- [Chat Completion](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/chat-completion/overview)
- [Speech-to-Text REST](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/rest-api)
- [Text-to-Speech REST](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/rest-api)
- [Voice Agents API](https://docs.sarvam.ai/voice-agents/api/introduction)
