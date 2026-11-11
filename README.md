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

Open http://localhost:5173. To serve the built frontend through FastAPI, run `npm run build` in `frontend/` and start the backend without `--reload`.

## Hosting

A public GitHub repository shares the source code; it does not run the backend. To host the app, deploy the included `Dockerfile` on a container service and set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as server environment variables. Never commit `.env` files or put the service-role key in frontend settings.

Uploaded handwriting and paper images are stored in private Supabase storage. Sessions expire after 24 hours; expired files are cleaned up when a new handwriting sheet is uploaded.
