# Google Drive Setup Guide

## Prerequisites
- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com/)

---

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it (e.g., `geopolitics-automation`)
4. Click **Create**

---

## Step 2: Enable the Google Drive API

1. In your new project, go to **APIs & Services** → **Library**
2. Search for **Google Drive API**
3. Click **Enable**

---

## Step 3: Create a Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **+ CREATE CREDENTIALS** → **Service account**
3. Name: `geopolitics-uploader`
4. Click **Create and Continue**
5. Role: **Editor** (or skip if you only want Drive access)
6. Click **Done**

---

## Step 4: Generate a JSON Key

1. Click on the newly created service account
2. Go to the **Keys** tab
3. Click **Add Key** → **Create new key**
4. Select **JSON** → **Create**
5. Download the JSON file — **keep it safe and secret**

---

## Step 5: Share Your Drive Folder

1. Open [Google Drive](https://drive.google.com/)
2. Create a folder called **Geopolitics** (the script will also auto-create it)
3. Right-click the folder → **Share**
4. Add the service account email (it looks like `geopolitics-uploader@your-project.iam.gserviceaccount.com`)
5. Give it **Editor** access
6. Click **Send**

---

## Step 6: Add the Secret to GitHub

1. Open your GitHub repository
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `GOOGLE_CREDENTIALS_JSON`
5. Value: Paste the **entire contents** of the downloaded JSON key file
6. Click **Add secret**

---

## Local Testing

To test locally without GitHub Actions:

```bash
# Set the environment variable with your JSON key
export GOOGLE_CREDENTIALS_JSON='$(cat path/to/your-key.json)'

# Run the script
cd geopolitics
python main.py
```

If you don't set `GOOGLE_CREDENTIALS_JSON`, the script will still work — it just skips the Drive upload and saves files locally in the `output/` folder.

---

## Folder Structure on Google Drive

After the script runs, your Drive will look like:

```
My Drive/
  Geopolitics/
    02/
      02_mar_6:33am.png
      02_mar_6:33am.txt
    03/
      03_mar_12:00pm.png
      03_mar_12:00pm.txt
```

Each day gets its own subfolder named by the two-digit day of the month.
