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

Open http://localhost:5173. When the frontend and backend are deployed together, leave `VITE_API_BASE_URL` empty. For a separate frontend host, set it to the backend URL and add the frontend origin to the backend's `CORS_ORIGINS`.

To serve the built frontend through FastAPI, run `npm run build` in `frontend/` and start the backend without `--reload`.

## Hosting

A public GitHub repository shares the source code; it does not run the app. CopyCat is deployed as one Render web service using the included `Dockerfile`, which builds the frontend and serves it with the FastAPI backend.

1. Connect the repository to Render and deploy it as a Docker web service.
2. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the Render service's environment settings. Keep secrets out of GitHub.
3. Ensure the private `copycat-glyphs` bucket and database schema are configured in Supabase.

The frontend and API share one origin, so no separate frontend API URL or CORS configuration is needed for this deployment.

Uploaded handwriting and paper images are stored in private Supabase storage. Sessions expire after 24 hours; expired files are cleaned up when a new handwriting sheet is uploaded.
