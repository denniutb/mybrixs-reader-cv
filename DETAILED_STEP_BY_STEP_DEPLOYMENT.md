# Detailed Deployment Guide — MyBrixS Standalone Web App v0.1

## Goal

Create a brand-new Vercel web app with a new Vercel domain, without modifying the existing `brix-reader.vercel.app`.

The new app will provide:
- smartphone image upload/camera capture;
- deterministic OpenCV Brix reading;
- session summary on the web page;
- optional Supabase image and reading saving.

---

## Part 1 — Download and extract

1. Download the ZIP package supplied by ChatGPT.
2. Extract it on your computer.
3. Confirm the extracted folder contains:

```text
index.py
requirements.txt
pyproject.toml
assets/
templates/
public/
```

---

## Part 2 — Create a new GitHub repository

1. Go to GitHub.
2. Click **New repository**.
3. Repository name suggestion:

```text
mybrixs-reader-cv
```

4. Choose **Private** or **Public**.
5. Click **Create repository**.

---

## Part 3 — Upload the web app files to GitHub

1. In the new GitHub repository, click **Add file** → **Upload files**.
2. Upload the **contents inside** the extracted project folder.
3. The GitHub repository root must look like this:

```text
mybrixs-reader-cv/
├── index.py
├── requirements.txt
├── pyproject.toml
├── assets/
├── templates/
├── public/
├── SUPABASE_OPTIONAL_SCHEMA.sql
└── README_DEPLOY.md
```

4. Click **Commit changes**.

Important: Do not upload the outer folder as a nested subfolder. Vercel must see `index.py` at the repository root.

---

## Part 4 — Create the new Vercel project

1. Go to Vercel Dashboard.
2. Click **Add New** → **Project**.
3. Import the GitHub repository:

```text
mybrixs-reader-cv
```

4. Vercel should recognise the Python/Flask application automatically from:
   - `index.py`,
   - `requirements.txt`,
   - `pyproject.toml`.

5. Before deploying, add environment variables if you want cloud saving.

---

## Part 5 — Add Supabase environment variables

If reusing your existing Supabase project:

1. In Vercel project setup, open **Environment Variables**.
2. Add:

```text
SUPABASE_URL
```

3. Add:

```text
SUPABASE_SERVICE_KEY
```

4. Use the same Supabase values used by your earlier `brix-reader` project.

If you do not add them yet, the app can still read Brix, but it will not save images/readings to the cloud.

---

## Part 6 — Deploy

1. Click **Deploy**.
2. Wait for the build to complete.
3. Vercel will issue a new domain, for example:

```text
https://mybrixs-reader-cv.vercel.app
```

---

## Part 7 — Verify the backend health

Open:

```text
https://YOUR-NEW-VERCEL-DOMAIN.vercel.app/api/health
```

Expected:

```json
{
  "ok": true,
  "service": "mybrixs-standalone-webapp",
  "reference_image_present": true,
  "supabase_configured": true
}
```

If `supabase_configured` is false, Brix reading still works, but cloud saving is not active.

---

## Part 8 — Open the new app

Open the app domain:

```text
https://YOUR-NEW-VERCEL-DOMAIN.vercel.app
```

You should see:
- MyBrixS header;
- fruit type field;
- batch ID;
- threshold field;
- camera/image upload area;
- Read Brix button;
- latest reading panel;
- session summary table.

---

## Part 9 — Test against known benchmark images

Test in this order:

| Refractometer image | Expected app reading |
|---|---:|
| Yellow B Bottom | 4.4% |
| Yellow B Middle | 7.2% |
| 14% sample | 14.0% |
| 29.2% sample | 29.2% |

---

## Part 10 — Optional: add a custom domain later

The first deployment gets a free Vercel `.vercel.app` domain.
After confirming accuracy, add a custom domain in:

Vercel Project → Settings → Domains

Examples:
- `reader.mybrixs.com`
- `app.mybrixs.com`

---

## Troubleshooting

### Deployment fails at package installation
Send the Vercel build log to ChatGPT. The likely cause would be dependency build or package-size handling.

### `/api/health` shows 404
Check that `index.py` is at the **repository root**, not nested inside another folder.

### `reference_image_present` is false
Check that GitHub contains:

```text
assets/calibration_reference_10_2_brix.jpg
```

### Scan works but image is not saved
Check the Vercel environment variables:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

### Scan fails with cloud storage error
Check Supabase has a storage bucket named:

```text
mybrixs-images
```

The current MVP expects that bucket name.
