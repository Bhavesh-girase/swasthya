import os
from pathlib import Path

from sarvamai import SarvamAI


api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "SARVAM_API_KEY":
                api_key = value.strip().strip("\"'")
                if api_key:
                    os.environ["SARVAM_API_KEY"] = api_key
                break

if not api_key:
    raise SystemExit("Add your key to SARVAM_API_KEY in .env.")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions(
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
    model="sarvam-105b-conversations",
)
print(response.choices[0].message.content)
