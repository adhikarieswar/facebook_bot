import os
import json
import re
import time
import uuid
import urllib.parse
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from flask import Flask, request, jsonify
from groq import Groq

load_dotenv()

app = Flask(__name__)

# ✅ Deduplication set — tracks comment fingerprints we've already replied to
processed_comments = set()

# ✅ Bot start time — ignore any comments created before this moment
BOT_START_TIME = datetime.now(timezone.utc)

# ============================================
# CONFIGURATION (Zernio API)
# ============================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ZERNIO_API_KEY = os.getenv("ZERNIO_API_KEY")
ZERNIO_ACCOUNT_ID = os.getenv("ZERNIO_ACCOUNT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "starting_industries_verify_123")

BUSINESS_DESCRIPTION = os.getenv("BUSINESS_DESCRIPTION",
    "Starting Industries is a leading construction and building company specializing in residential and commercial projects. We offer turnkey solutions from design to completion with over 20 years of experience. We build dream homes, offices, and commercial spaces.")

llm = Groq(api_key=GROQ_API_KEY)
ZERNIO_BASE_URL = "https://zernio.com/api/v1"

# ============================================
# AI POST GENERATOR
# ============================================
def generate_post_content(post_type="promotional"):
    prompt = f"""You are a social media manager for this business:
{BUSINESS_DESCRIPTION}

Create a Facebook Page post of type: {post_type}

Return ONLY a JSON object with two fields:
- "caption": engaging Facebook caption with emojis, call to action, and 5 hashtags (100-150 words)
- "image_prompt": detailed photorealistic image description for an AI image generator (50-80 words)

IMPORTANT:
- Return ONLY the JSON object
- Do NOT use markdown code blocks
- Do NOT add any text before or after the JSON

Example format:
{{"caption": "Your caption here", "image_prompt": "Your image prompt here"}}
"""
    try:
        response = llm.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000,
            reasoning_effort="low"
        )
        result_text = response.choices[0].message.content
        if not result_text or result_text.strip() == "":
            print("❌ LLM returned EMPTY response")
            return None
        result_text = result_text.strip()
        result_text = re.sub(r'```json\s*', '', result_text)
        result_text = re.sub(r'```\s*', '', result_text)
        result_text = result_text.strip()
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(0)
        result = json.loads(result_text)
        print(f"✅ Caption: {result['caption'][:80]}...")
        print(f"✅ Image prompt: {result['image_prompt'][:80]}...")
        return result
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return None

# ============================================
# IMAGE GENERATION (Standard)
# ============================================
def generate_image(image_prompt):
    try:
        encoded_prompt = urllib.parse.quote(image_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={int(time.time())}"
        print(f"✅ Image URL: {image_url[:100]}...")
        return image_url
    except Exception as e:
        print(f"❌ Image error: {e}")
        return None

# ============================================
# PREMIUM IMAGE GENERATION (Full HD, Cinematic)
# ============================================
def generate_premium_image(image_prompt):
    """Generate Full HD, cinematic, enhanced image"""
    try:
        encoded_prompt = urllib.parse.quote(image_prompt)
        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1920"
            f"&height=1080"
            f"&nologo=true"
            f"&enhance=true"
            f"&model=flux"
            f"&seed={int(time.time())}"
        )
        print(f"✅ Premium image URL: {image_url[:120]}...")
        return image_url
    except Exception as e:
        print(f"❌ Premium image error: {e}")
        return None

# ============================================
# ZERNIO HELPERS
# ============================================
def zernio_request(method, path, *, body=None, headers_extra=None):
    headers = {
        "Authorization": f"Bearer {ZERNIO_API_KEY}",
        "Content-Type": "application/json"
    }
    if headers_extra:
        headers.update(headers_extra)
    response = requests.request(
        method, f"{ZERNIO_BASE_URL}/{path}", headers=headers, json=body, timeout=60
    )
    response.raise_for_status()
    return response.json()

# ============================================
# POST TO FACEBOOK VIA ZERNIO
# ============================================
def post_to_facebook(caption, image_url, immediate=True):
    try:
        print("📝 Creating post...")

        payload = {
            "platforms": [{
                "platform": "facebook",
                "accountId": ZERNIO_ACCOUNT_ID
            }],
            "content": caption
        }

        if image_url:
            payload["mediaItems"] = [{
                "type": "image",
                "url": image_url
            }]

        if immediate:
            payload["publishNow"] = True
            print("🚀 Publishing NOW...")
        else:
            payload["scheduledFor"] = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
            print(f"⏰ Scheduling for {payload['scheduledFor']}...")

        request_id = str(uuid.uuid4())

        result = zernio_request(
            "POST", "posts",
            body=payload,
            headers_extra={"x-request-id": request_id}
        )

        post_data = result.get("post", {})
        post_id = post_data.get("_id")
        post_url = None

        platforms = post_data.get("platforms", [])
        if platforms:
            post_url = platforms[0].get("platformPostUrl")

        if post_id:
            print(f"✅ Post published: {post_id}")
            if post_url:
                print(f"🔗 View on Facebook: {post_url}")
            return True
        else:
            print(f"❌ Post creation failed: {result}")
            return False

    except requests.exceptions.HTTPError as e:
        print(f"❌ Zernio HTTP Error: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Zernio error: {e}")
        return False

# ============================================
# REPLY TO COMMENTS VIA ZERNIO
# ============================================
def reply_to_comment(post_id, comment_id, reply_text):
    try:
        payload = {
            "accountId": ZERNIO_ACCOUNT_ID,
            "message": reply_text,
            "commentId": comment_id
        }
        path = f"inbox/comments/{post_id}"
        print(f"📤 Replying to comment {comment_id} on post {post_id}...")

        result = zernio_request("POST", path, body=payload)

        if result.get("success") or result.get("id"):
            print(f"✅ Replied to comment: {comment_id}")
            return True

        print(f"❌ Reply failed: {result}")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"❌ Reply HTTP Error: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Reply error: {e}")
        return False

# ============================================
# GENERATE COMMENT REPLY
# ============================================
def generate_comment_reply(comment_text, username):
    prompt = f"""You are a friendly customer service agent for this business:
{BUSINESS_DESCRIPTION}

A user named @{username} commented: "{comment_text}"

Write a warm, spontaneous, and natural reply. Do not sound robotic or templated.
Keep it under 50 words. Be personal, grateful, and helpful.
Return ONLY the reply text."""
    try:
        response = llm.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=1000,
            reasoning_effort="low"
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Reply generation error: {e}")
        return f"Thanks for your comment, @{username}! We appreciate it."

# ============================================
# MAIN POSTING FUNCTION
# ============================================
def create_and_post(post_type="promotional", immediate=True):
    print(f"\n{'='*50}")
    print(f"🚀 Starting post at {datetime.now()}")
    print(f"📝 Type: {post_type} | Immediate: {immediate}")
    print(f"{'='*50}\n")

    content = generate_post_content(post_type)
    if not content:
        return {"error": "Failed to generate content"}

    image_url = generate_image(content["image_prompt"])
    if not image_url:
        return {"error": "Failed to generate image"}

    success = post_to_facebook(content["caption"], image_url, immediate=immediate)

    if success:
        return {
            "status": "success",
            "caption": content["caption"][:100] + "...",
            "image_url": image_url,
            "immediate": immediate,
            "timestamp": datetime.now().isoformat()
        }
    return {"error": "Failed to post"}

# ============================================
# ENDPOINTS
# ============================================
@app.route("/", methods=["GET"])
def index():
    return "🤖 Starting Industries Facebook Bot (via Zernio) is running!"

@app.route("/post-now", methods=["GET", "POST"])
def post_now():
    try:
        post_type = request.args.get("type", "promotional")
        result = create_and_post(post_type, immediate=True)
        return jsonify(result), 200 if "error" not in result else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/scheduled/post", methods=["POST"])
def scheduled_post():
    try:
        data = request.get_json() or {}
        post_type = data.get("post_type", "promotional")
        result = create_and_post(post_type, immediate=False)
        return jsonify(result), 200 if "error" not in result else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# ✅ FINAL EXCELLENT POST — Premium Graphics
# ============================================
@app.route("/final-post", methods=["GET", "POST"])
def final_post():
    """Generate and publish the final, excellent post with premium graphics"""
    try:
        print(f"\n{'='*60}")
        print(f"🎬 FINAL POST — Premium Graphics Edition")
        print(f"{'='*60}\n")

        # Step 1: Generate excellent caption + premium image prompt
        prompt = f"""You are a world-class social media copywriter for an award-winning construction company.

Business: {BUSINESS_DESCRIPTION}

Write the ULTIMATE FINAL Facebook post that:
- Thanks the community, clients, and partners for 20+ years of trust
- Uses powerful, emotional, cinematic language
- Highlights excellence, craftsmanship, and vision
- Ends with an inspiring, forward-looking call to action
- Includes exactly 5 powerful hashtags
- Uses emojis strategically (not overdone)
- Is 120-180 words

Also create a PREMIUM, CINEMATIC image prompt that describes:
- A breathtaking architectural masterpiece
- Golden hour / dramatic lighting
- Ultra-high detail, photorealistic, 8K quality
- Professional architectural photography style
- Cinematic composition with depth

Return ONLY a JSON object:
{{"caption": "your excellent caption here", "image_prompt": "your premium image prompt here"}}
"""
        response = llm.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=2000,
            reasoning_effort="low"
        )
        result_text = response.choices[0].message.content
        result_text = re.sub(r'```json\s*', '', result_text)
        result_text = re.sub(r'```\s*', '', result_text)
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(0)
        result = json.loads(result_text)

        caption = result["caption"]
        image_prompt = result["image_prompt"]

        print(f"✅ Excellent caption generated: {caption[:120]}...")
        print(f"✅ Premium image prompt: {image_prompt[:120]}...")

        # Step 2: Generate PREMIUM Full HD image
        image_url = generate_premium_image(image_prompt)
        if not image_url:
            return jsonify({"error": "Failed to generate premium image"}), 500

        # Step 3: Post to Facebook
        success = post_to_facebook(caption, image_url, immediate=True)

        if success:
            return jsonify({
                "status": "success",
                "message": "🎉 Final premium post published!",
                "caption": caption,
                "image_url": image_url,
                "resolution": "1920x1080"
            }), 200
        return jsonify({"error": "Failed to post"}), 500

    except Exception as e:
        print(f"❌ Final post error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================
# WEBHOOK VERIFICATION (GET)
# ============================================
@app.route("/webhook/comments", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified")
        return challenge, 200
    return "Verification failed", 403

# ============================================
# HANDLE COMMENT WEBHOOK (POST)
# ✅ Only NEW comments, one reply per comment
# ============================================
@app.route("/webhook/comments", methods=["POST"])
def handle_comment():
    try:
        data = request.get_json()
        print(f"\n{'='*60}")
        print(f"📩 ZERNIO WEBHOOK RECEIVED")
        print(f"{'='*60}")
        print(json.dumps(data, indent=2)[:1000])
        print(f"{'='*60}\n")

        comment = data.get("comment", {}) or {}
        post = data.get("post", {}) or {}

        comment_id = comment.get("id")
        comment_text = comment.get("text", "")
        username = (comment.get("author") or {}).get("name", "friend")
        post_id = post.get("id")
        created_at_str = comment.get("createdAt", "")

        # ✅ CHECK 1: Ignore comments created before bot started
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at < BOT_START_TIME:
                    print(f"⏭️ Ignoring OLD comment (before bot start): {created_at_str}")
                    return "OK", 200
            except Exception as e:
                print(f"⚠️ Could not parse createdAt: {e}")

        # ✅ CHECK 2: Ignore own comments (bot's own replies)
        is_own = (comment.get("author") or {}).get("isOwnAccount", False)
        if is_own:
            print(f"⏭️ Ignoring OWN comment")
            return "OK", 200

        # ✅ CHECK 3: Deduplicate by fingerprint (post + author + text)
        fingerprint = f"{post_id}|{username}|{comment_text}"
        if fingerprint in processed_comments:
            print(f"⏭️ Skipping DUPLICATE comment: {fingerprint}")
            return "OK", 200

        processed_comments.add(fingerprint)
        print(f"🔑 Processing NEW comment: {fingerprint}")

        print(f"💬 Comment ID: {comment_id}")
        print(f"💬 Post ID: {post_id}")
        print(f"💬 From: @{username}")
        print(f"💬 Text: {comment_text}")

        if comment_text and comment_id:
            reply = generate_comment_reply(comment_text, username)
            print(f"🤖 Generated reply: {reply}")
            reply_to_comment(post_id, comment_id, reply)
        else:
            print("⚠️ Missing comment_id or comment_text")

        return "OK", 200
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return "Error", 500

# ============================================
# RUN APP
# ============================================
if __name__ == "__main__":
    print(f"🚀 Bot starting at {BOT_START_TIME.isoformat()}")
    print(f"📝 Only comments created AFTER this time will be replied to.")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)