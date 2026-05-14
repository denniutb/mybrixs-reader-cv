# MyBrixS Standalone Web App v0.1

This is a **new, self-contained Vercel web app** for MyBrixS.

It combines:

- a smartphone-friendly web interface,
- a deterministic Python/OpenCV Brix-reading API,
- optional Supabase saving of images and readings,
- Vercel deployment under a fresh project domain.

## Why this is easier than modifying the existing app

You deploy a single new Vercel project, get a new Vercel domain, and test it independently.
Your current `brix-reader.vercel.app` can remain untouched until the new app is confirmed.

## Computer-vision method

The scan API uses the validated pipeline developed earlier:

1. detect the central refractometer scale region;
2. align the image to a reference image;
3. detect the blue-white boundary;
4. apply the non-linear Brix calibration;
5. round to the refractometer increment of 0.2% Brix.

This algorithm was checked against the key benchmark images:

| Actual reading | CV result |
|---:|---:|
| 4.4% | 4.4% |
| 7.2% | 7.2% |
| 14.0% | 14.0% |
| 29.2% | 29.2% |
| 7.8% | 7.8% |

## File structure

```text
MyBrixS_Standalone_WebApp_v0_1/
├── index.py
├── requirements.txt
├── pyproject.toml
├── assets/
│   └── calibration_reference_10_2_brix.jpg
├── templates/
│   └── index.html
├── public/
│   ├── app.js
│   └── styles.css
├── SUPABASE_OPTIONAL_SCHEMA.sql
└── README_DEPLOY.md
```

## Environment variables

For cloud saving, set these in Vercel:

```text
SUPABASE_URL
SUPABASE_SERVICE_KEY
```

If they are omitted, the web app still reads Brix, but image/reading saving is skipped.

## Supabase reuse

You can reuse the existing Supabase project from the prior web app if it already has:

- a `readings` table compatible with the current app fields;
- a public storage bucket named `mybrixs-images`.

A fresh optional SQL schema is included in `SUPABASE_OPTIONAL_SCHEMA.sql`.

## Health check after deployment

Open:

```text
https://YOUR-NEW-VERCEL-DOMAIN.vercel.app/api/health
```

Expected response:

```json
{
  "ok": true,
  "service": "mybrixs-standalone-webapp",
  "reference_image_present": true,
  "supabase_configured": true
}
```

If Supabase has not been configured yet, `supabase_configured` may be `false`, but the reader can still be tested.
