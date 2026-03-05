# Gemini API Setup Guide

## Step 1: Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy the API key

> **Free Tier**: Gemini 2.0 Flash is free for up to 15 requests/minute, which is more than enough for this automation.

---

## Step 2: Test Locally

```bash
export GEMINI_API_KEY="your-api-key-here"
cd geopolitics
python main.py
```

If the key is not set, the script gracefully falls back to using the original article content without AI enhancement.

---

## Step 3: Add to GitHub Actions

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `GEMINI_API_KEY`
5. Value: Paste your API key
6. Click **Add secret**

The workflow already references this secret in the environment variables.

---

## What Gemini Does

For each breaking news article, Gemini 2.0 Flash:

- Rewrites the headline to be concise and urgent (max 15 words)
- Generates a 4-line factual summary
- Extracts 3-4 key facts as bullet points
- Maintains strictly neutral, unbiased tone

If Gemini is unavailable or fails, the system automatically falls back to the original article content.
