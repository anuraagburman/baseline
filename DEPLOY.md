# Deploying Baseline (so a layman can just scan & chat)

You deploy this **once**. After that, anyone can use Baseline by scanning a QR code
and chatting on WhatsApp — they never see an API key, never install an app. The keys
below are **your** secrets, set once on the host.

> **The mental model:** one hosted server runs the WhatsApp number, Claude, and the
> database for *everyone*. Each person's data is isolated by their phone number. The
> only thing a user does is tap one Google sign-in to connect their device.

Everything runs on mocks until you fill these in — so you can deploy first and add
each integration as you go.

---

## 0. Prerequisites
- A [Railway](https://railway.app) account (hosting + Postgres + cron in one place).
- An [Anthropic](https://console.anthropic.com) API key.
- A [Twilio](https://www.twilio.com/whatsapp) account (WhatsApp sender).
- A [Google Cloud](https://console.cloud.google.com) project (Fitness API + OAuth).

---

## 1. Deploy the app to Railway
1. **New Project → Deploy from GitHub repo** → pick `anuraagburman/baseline`.
   Railway reads `railway.json` and builds the `Dockerfile` automatically.
2. **Add Postgres:** *New → Database → PostgreSQL*. Railway injects `DATABASE_URL`;
   copy it into a variable named **`BASELINE_DB_URL`** (same value).
3. Once it boots, confirm `https://<your-app>.up.railway.app/healthz` returns
   `{"status":"ok"}`.

Set these variables now (Railway → your service → **Variables**):

```
BASELINE_PUBLIC_BASE_URL = https://<your-app>.up.railway.app
BASELINE_CRON_SECRET     = <a long random string>
BASELINE_LLM_PROVIDER    = claude
BASELINE_VISION_PROVIDER = claude
ANTHROPIC_API_KEY        = sk-ant-...
```

---

## 2. Connect WhatsApp (Twilio)
1. Twilio Console → **Messaging → Try WhatsApp** (sandbox is free/instant for testing;
   apply for a production WhatsApp sender when ready).
2. Set variables:
   ```
   BASELINE_TWILIO_ACCOUNT_SID  = ACxxxxxxxx
   BASELINE_TWILIO_AUTH_TOKEN   = xxxxxxxx
   BASELINE_TWILIO_WHATSAPP_FROM = whatsapp:+<your number>
   ```
3. Twilio → your WhatsApp sender → **"When a message comes in"** webhook →
   `https://<your-app>.up.railway.app/webhooks/whatsapp` (HTTP POST).
4. **Daily nudge template** (for proactive messages): submit a *utility* template for
   approval, e.g. *"Your Baseline check-in for today is ready 👋 Reply to see today's
   tip."* Put its name in `BASELINE_WHATSAPP_TEMPLATE_NAME`. (Inbound replies work
   without a template; the template is only needed to message users first.)

Test now: from your phone, message the Twilio number **"hi"** → Baseline should start
onboarding.

---

## 3. Connect Google Health (real wearable data)
1. Google Cloud → **APIs & Services** → enable the **Fitness API**.
2. **Credentials → Create OAuth client ID → Web application**. Add the redirect URI:
   `https://<your-app>.up.railway.app/oauth/google/callback`
3. Set variables:
   ```
   BASELINE_GOOGLE_CLIENT_ID          = xxxx.apps.googleusercontent.com
   BASELINE_GOOGLE_CLIENT_SECRET      = xxxx
   BASELINE_GOOGLE_OAUTH_REDIRECT_URI = https://<your-app>.up.railway.app/oauth/google/callback
   ```
> Until Google approves Fitness API access, Baseline automatically falls back to
> synthetic data — the whole flow still works end-to-end.

---

## 4. Schedule the daily nudge
Railway → **New → Cron Job** (or a cron service) hitting your app twice a day:

```
# 08:00 — morning delivery group
curl -X POST "https://<your-app>.up.railway.app/cron/daily-nudge?window=morning" \
     -H "X-Cron-Secret: $BASELINE_CRON_SECRET"

# 19:00 — evening delivery group
curl -X POST "https://<your-app>.up.railway.app/cron/daily-nudge?window=evening" \
     -H "X-Cron-Secret: $BASELINE_CRON_SECRET"
```

Only users who opted in during onboarding (and haven't replied "stop") receive nudges.

---

## 5. Publish the landing page (QR → WhatsApp)
1. Generate the QR for your number:
   ```
   python landing/make_qr.py +<your-twilio-number> hi
   ```
2. In `landing/index.html`, update the **"Open WhatsApp"** button `href` to your number.
3. Deploy the `landing/` folder to **Vercel** or **Netlify** (it's plain static HTML —
   no build step; `landing/netlify.toml` is included). Point a domain at it
   (e.g. `baseline.anuraagburman.com`).

Share that page. Scanning the QR opens WhatsApp straight into Baseline.

---

## 6. Smoke test the live system
1. Scan the landing QR → WhatsApp opens → send "hi".
2. Complete onboarding (one question at a time) → tap the Google link → grant consent.
3. Receive your first insight.
4. Send a **photo of a meal** → get calories + protein + what's left today.
5. Say **"just ran 30 min"** → streak updates.
6. Ask **"why?"** → grounded explanation.
7. Wait for (or manually trigger) the cron → receive the daily nudge → reply → full tip.
8. Reply **"stop"** → confirms opt-out; **"start"** → back on.

---

## Cost (operator-borne, never the user's)
- **Claude**: per coaching message + per food-photo analysis.
- **Twilio**: per WhatsApp message; the proactive nudge is one cheap *utility* template,
  and the user's reply opens a free 24-hour window for the full conversation.
- **Railway/Postgres**: a small monthly hosting fee.

Keep secrets in the host's variable store only — never commit them. No personal or
health data is written to logs.
