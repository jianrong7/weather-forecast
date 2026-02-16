# Radar-Only Telegram Rain Alert (Python)

Kinda frustrated with the weather apps not being able to give me good rain forecasts. I find myself relying a lot on https://www.weather.gov.sg/weather-rain-area-50km.

With the help of Codex, I managed to build this on top of AWS Lambda and a light layer of DynamoDB for state management.

The basic idea is that it will look through the latest radar frames from that URL, then score the rain risk for a pinned location, and send Telegram alerts through a bot if there is a risk transition (e.g. from "no rain" to "light rain" or "light rain" to "heavy rain").

Scheduled AWS Lambda polls Singapore radar frames, scores rain risk for one pinned location, and sends Telegram alerts on upward risk transitions.

## Stack

- Python 3.11+
- AWS Lambda + EventBridge (default schedule skips quiet hours 23:00-07:00 Singapore time)
- DynamoDB (`PROFILE` + `ALERT_STATE` items)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Seed pinned location

```bash
python scripts/seed_profile.py --lat <LAT> --lng <LNG> --chat-id <chat_id>
```

## Run once locally

```bash
python -m weather_bot.handler
```

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Lambda deploy

From repo root:

```bash
./scripts/build_lambda_zip.sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars
terraform init
terraform apply
```

Terraform provisions DynamoDB, Lambda, IAM, CloudWatch logs, and EventBridge schedule.
