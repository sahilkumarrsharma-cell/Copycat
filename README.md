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

A public GitHub repository shares the source code; it does not run the app. CopyCat can run on Cloudflare Workers Containers using the included `Dockerfile` and `wrangler.jsonc`.

1. Connect this repository to Cloudflare Workers Builds with `main` as the production branch.
2. Set the build command to `npm ci` and deploy command to `npm run deploy`.
3. Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the Worker's server-side **Settings > Variables and Secrets**. Do not put secret values in GitHub or frontend settings.
4. Ensure the private `copycat-glyphs` bucket and database schema are configured in Supabase.

Cloudflare Containers require the Workers Paid plan (minimum USD $5/month), with possible extra charges for container usage above included allowances. The Wrangler worker routes requests to a single basic-size container, which sleeps after inactivity. The container needs outbound internet access to reach Supabase.

Uploaded handwriting and paper images are stored in private Supabase storage. Sessions expire after 24 hours; expired files are cleaned up when a new handwriting sheet is uploaded.
