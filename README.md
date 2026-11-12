# CopyCat

Turn handwriting samples into printable A4 pages, optionally matched to a photo of your assignment paper.

## Setup

Create `backend/.env` from the example and set your Supabase project URL and server-only service-role key. Run `backend/supabase_schema.sql` in the Supabase SQL Editor and create the private `copycat-glyphs` bucket.

```sh
cp backend/.env.example backend/.env
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Copy `frontend/.env.example` to `frontend/.env` if needed, then set `VITE_API_BASE_URL` to the Render URL, for example `https://copycat-api.onrender.com`, and set `CORS_ORIGINS` in the backend to include your frontend origin.

To serve the built frontend through FastAPI, run `npm run build` in `frontend/` and start the backend without `--reload`.

## Hosting

A public GitHub repository shares the source code; it does not run the app. The simplest deployment is to keep the frontend on Cloudflare Pages and run the FastAPI backend on Render.

1. Connect the repository to Cloudflare Pages and build the frontend from `frontend/` using `npm install` and `npm run build`.
2. Set the frontend environment variable `VITE_API_BASE_URL` to the Render backend URL (or leave it empty when the frontend and API share the same domain).
3. Deploy the Python backend on Render using the included `Dockerfile` or a standard Python service, and set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `CORS_ORIGINS` in the service environment.
4. Ensure the private `copycat-glyphs` bucket and database schema are configured in Supabase.

This keeps the app public without exposing secrets in frontend code or GitHub. The Cloudflare worker configuration in this repo is optional and is mainly useful for a single-container prototype; the Pages + Render flow is the safer deployment path for production testing.

Uploaded handwriting and paper images are stored in private Supabase storage. Sessions expire after 24 hours; expired files are cleaned up when a new handwriting sheet is uploaded.
