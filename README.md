
**Character count: 253** ✅

---

### README.md (Full Description)

```markdown
# Facebook & Instagram AI Automation Bot

A fully automated AI bot that manages Facebook and Instagram pages end-to-end. It generates captions and images with AI, posts on schedule, and auto-replies to every comment in real-time using webhooks.

## What It Does

- **AI Caption Generation**: Uses Groq LLM to write engaging captions with hashtags and emojis
- **AI Image Generation**: Uses Pollinations.ai (Flux model) to create unique images
- **Scheduled Posting**: Posts automatically at set times via Cloud Scheduler
- **Real-Time Comment Replies**: Auto-replies to comments using webhooks
- **Deduplication**: Prevents duplicate replies with fingerprinting
- **Old Comment Filter**: Ignores comments before bot start time
- **Self-Reply Prevention**: Prevents infinite loops
- **Cloud Deployed**: Runs 24/7 on Google Cloud Run

## Tech Stack

- **Backend**: Python, Flask
- **AI (Text)**: Groq LLM (openai/gpt-oss-20b)
- **AI (Image)**: Pollinations.ai (Flux model)
- **Social Media**: Zernio API (Facebook + Instagram)
- **Webhooks**: Real-time comment delivery
- **Deployment**: Google Cloud Run, Docker, Gunicorn

## How It Works

1. Cloud Scheduler triggers the bot at 9 AM and 6 PM
2. Bot generates a caption using Groq LLM
3. Bot generates an image using Pollinations.ai
4. Bot posts to Facebook and Instagram via Zernio
5. When someone comments, Zernio sends a webhook
6. Bot generates a natural reply using Groq LLM
7. Bot sends the reply via Zernio

## Key Features

- Webhook deduplication (fingerprint-based)
- Old comment filtering (BOT_START_TIME)
- Self-reply prevention (isOwnAccount)
- Idempotency (x-request-id)
- Premium image generation (1920x1080)
- Full HD, cinematic images

## Setup

```bash
pip install -r requirements.txt
python app.py
