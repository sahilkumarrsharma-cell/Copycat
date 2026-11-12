import { useCallback, useEffect, useRef, useState } from "react";

const INKS = [
  { id: "blue", label: "Blue ballpoint", color: "#1c34a0" },
  { id: "black", label: "Black gel", color: "#141418" },
  { id: "darkblue", label: "Dark blue", color: "#0c1858" },
];
const PAPERS = [
  { id: "photo", label: "My university sheet" },
  { id: "ruled", label: "Ruled A4" },
  { id: "margin", label: "Margin-lined" },
  { id: "blank", label: "Blank A4" },
];
const JSON_HEADERS = { "Content-Type": "application/json" };
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const btn =
  "inline-flex items-center justify-center rounded-xl bg-ink px-5 py-3 font-semibold text-white hover:bg-[#2b416d] disabled:cursor-not-allowed disabled:opacity-40";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function api(path, options) {
  const res = await fetch(apiUrl(path), options);
  if (!res.ok) {
    let msg = "Something went wrong. Check your inputs and try again.";
    try {
      const detail = (await res.json()).detail;
      if (typeof detail === "string") msg = detail;
    } catch {
      /* keep default message */
    }
    throw new Error(msg);
  }
  return res;
}

// Rough page estimate before the real preview arrives (mirrors generator.py sizes).
function estimatePages(text, size) {
  const cap = size * 2.917;
  const perLine = Math.max(10, Math.floor(2000 / (cap * 0.85)));
  const perPage = Math.max(1, Math.floor(2900 / Math.max(94, Math.round(cap * 1.9))));
  const lines = text.split("\n").reduce((n, p) => n + Math.max(1, Math.ceil(p.length / perLine)), 0);
  return Math.max(1, Math.ceil(lines / perPage));
}

function Step({ title, children }) {
  return (
    <section className="mb-5 rounded-2xl border border-slate-200 border-l-4 border-l-margin bg-white p-5 shadow-sm sm:p-6">
      <h2 className="text-base font-semibold tracking-tight text-slate-900">{title}</h2>
      <div className="mt-4 space-y-4 text-sm leading-6 text-slate-600">{children}</div>
    </section>
  );
}

function CameraButton({ disabled, onShot }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [camError, setCamError] = useState("");

  function stop() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  useEffect(() => () => stop(), []);

  useEffect(() => {
    if (open && videoRef.current && streamRef.current) videoRef.current.srcObject = streamRef.current;
  }, [open]);

  async function openCam() {
    setCamError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCamError("This browser has no camera. Choose a photo instead.");
      return;
    }
    try {
      stop();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setOpen(true);
    } catch {
      setCamError("Camera is blocked. Allow camera access, or choose a photo instead.");
    }
  }

  function close() {
    stop();
    setOpen(false);
  }

  function snap() {
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) onShot(new File([blob], "camera.jpg", { type: "image/jpeg" }));
      close();
    }, "image/jpeg", 0.92);
  }

  return (
    <>
      <button type="button" className={btn} disabled={disabled} onClick={openCam}>Take photo</button>
      {camError && <p className="mt-2 text-sm text-margin">{camError}</p>}
      {open && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/70 p-4">
          <div role="dialog" aria-modal="true" aria-label="Take a photo" className="w-full max-w-lg rounded-2xl bg-white p-3 shadow-2xl">
            <video ref={videoRef} autoPlay playsInline className="max-h-[70vh] w-full bg-black object-contain" />
            <div className="mt-3 flex gap-2">
              <button type="button" className={btn} onClick={snap}>Use this photo</button>
              <button type="button" className="rounded-xl border border-slate-300 px-5 py-3 font-semibold text-slate-700 hover:bg-slate-50" onClick={close}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Slider({ label, value, min, max, onChange, suffix = "" }) {
  return (
    <label className="block text-sm">
      <span className="flex justify-between">
        <span>{label}</span>
        <span>{value}{suffix}</span>
      </span>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(+e.target.value)}
        className="mt-1 w-full accent-[#d6403a]" />
    </label>
  );
}

export default function App() {
  const [session, setSession] = useState(() => localStorage.getItem("copycat-session") || "");
  const [glyphs, setGlyphs] = useState([]);
  const [missing, setMissing] = useState([]);
  const [text, setText] = useState("");
  const [ink, setInk] = useState("blue");
  const [paper, setPaper] = useState("ruled");
  const [fontSize, setFontSize] = useState(16);
  const [jitter, setJitter] = useState(50);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [paperDrag, setPaperDrag] = useState(false);
  const [paperPreview, setPaperPreview] = useState("");
  const [paperLines, setPaperLines] = useState(0);
  const [paperDetected, setPaperDetected] = useState(false);
  const fileRef = useRef(null);
  const paperRef = useRef(null);

  const payload = { session, text, ink_color: ink, paper_type: paper, font_size: fontSize, jitter_level: jitter };

  const upload = useCallback(async (file) => {
    if (!file) return;
    setBusy("upload");
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await (await api("/api/upload-handwriting", { method: "POST", body })).json();
      localStorage.setItem("copycat-session", data.session);
      setSession(data.session);
      setGlyphs(data.found);
      setMissing(data.missing);
      setPaper("ruled");
      setPaperPreview("");
      setPaperLines(0);
      setPaperDetected(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }, []);

  const uploadPaper = useCallback(async (file) => {
    if (!file) return;
    if (!session) {
      setError("Upload your handwriting photo first, then the university sheet.");
      return;
    }
    setBusy("paper");
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await (await api(`/api/upload-paper?session=${session}`, { method: "POST", body })).json();
      setPaperPreview(data.preview);
      setPaperLines(data.lines);
      setPaperDetected(data.detected);
      setPaper("photo");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }, [session]);

  useEffect(() => {
    if (!session) {
      setPaper("ruled");
      setPaperPreview("");
      setPaperLines(0);
      setPaperDetected(false);
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const res = await fetch(apiUrl(`/api/paper/${session}`));
        if (cancel) return;
        if (res.status === 404) {
          setPaper("ruled");
          setPaperPreview("");
          setPaperLines(0);
          setPaperDetected(false);
          return;
        }
        if (!res.ok) throw new Error("Could not restore your saved university sheet.");
        const data = await res.json();
        if (cancel) return;
        setPaperPreview(data.preview);
        setPaperLines(data.lines);
        setPaperDetected(data.detected);
        setPaper("photo");
      } catch (e) {
        if (!cancel) setError(e.message);
      }
    })();
    return () => { cancel = true; };
  }, [session]);

  // Live preview: re-render 700 ms after the last change; older requests are cancelled.
  useEffect(() => {
    if (!session || !text.trim() || (paper === "photo" && !paperPreview)) {
      setPreview(null);
      setBusy((current) => current === "preview" ? "" : current);
      return;
    }
    const ctl = new AbortController();
    const timer = setTimeout(async () => {
      setBusy("preview");
      setError("");
      try {
        const res = await api("/api/preview", {
          method: "POST", headers: JSON_HEADERS, signal: ctl.signal,
          body: JSON.stringify({ session, text, ink_color: ink, paper_type: paper, font_size: fontSize, jitter_level: jitter }),
        });
        setPreview(await res.json());
        setBusy("");
      } catch (e) {
        if (e.name !== "AbortError") {
          setError(e.message);
          setBusy("");
        }
      }
    }, 700);
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [session, text, ink, paper, fontSize, jitter, paperPreview]);

  async function downloadPdf() {
    setBusy("pdf");
    setError("");
    try {
      const res = await api("/api/generate-pdf", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) });
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "assignment.pdf";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const status = busy === "upload" ? "Reading your handwriting…"
    : glyphs.length ? `${glyphs.length} characters captured.`
    : session ? "Using the handwriting you uploaded last time." : "No handwriting uploaded yet.";

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Handwriting studio</p>
          <h1 className="text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">CopyCat</h1>
          <p className="mt-2 max-w-xl text-base leading-7 text-slate-600">Turn your handwriting into a printable page, matched to your paper.</p>
        </div>
        <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600">Private by default · sessions expire in 24 hours</span>
      </header>

      {error && (
        <p role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-8">
        <div className="min-w-0">
          <Step title="1. Fill in the calibration sheet">
            <p>Print it at 100% on A4 and write one character in each box with a dark pen. Photograph the full page flat, with all 4 black corner squares visible.</p>
            <a href={apiUrl("/api/template")} download="copycat_sheet.png" className={btn}>Download calibration sheet</a>
          </Step>

          <Step title="2. Upload your photo">
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
              className={`rounded-xl border-2 border-dashed p-6 text-center transition-colors ${drag ? "border-margin bg-rose-50" : "border-slate-300 bg-slate-50/70"}`}
            >
              <p>Drop the calibration photo here, or</p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                <button type="button" className={btn} disabled={busy === "upload"} onClick={() => fileRef.current.click()}>
                  Choose photo
                </button>
                <CameraButton disabled={busy === "upload"} onShot={upload} />
              </div>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => { upload(e.target.files[0]); e.target.value = ""; }} />
            </div>
            <p aria-live="polite" className="text-sm text-slate-500">{status}</p>
            {missing.length > 0 && (
              <p className="text-sm text-margin">Not readable: {missing.join(" ")}. Rewrite those boxes darker and upload again.</p>
            )}
            {glyphs.length > 0 && (
              <div className="grid grid-cols-9 gap-1">
                {glyphs.map((g) => (
                  <img key={g.file} src={g.url} alt={`Captured ${g.char}`} title={g.char}
                    className="h-9 w-full rounded-lg border border-slate-200 bg-white object-contain p-1" />
                ))}
              </div>
            )}
          </Step>

          <Step title="3. Photograph your university sheet">
            <p>Use a blank assignment page from your college. Show the whole sheet, flat, including the header and the printed lines. The finished pages copy this sheet.</p>
            <div
              onDragOver={(e) => { e.preventDefault(); setPaperDrag(true); }}
              onDragLeave={() => setPaperDrag(false)}
              onDrop={(e) => { e.preventDefault(); setPaperDrag(false); uploadPaper(e.dataTransfer.files[0]); }}
              className={`rounded-xl border-2 border-dashed p-6 text-center transition-colors ${paperDrag ? "border-margin bg-rose-50" : "border-slate-300 bg-slate-50/70"}`}
            >
              <p>Drop the blank university sheet here, or</p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                <button type="button" className={btn} disabled={!session || busy === "paper"} onClick={() => paperRef.current.click()}>
                  Choose sheet photo
                </button>
                <CameraButton disabled={!session || busy === "paper"} onShot={uploadPaper} />
              </div>
              <input ref={paperRef} type="file" accept="image/*" hidden onChange={(e) => { uploadPaper(e.target.files[0]); e.target.value = ""; }} />
            </div>
            {!session && <p className="text-sm">Upload your handwriting photo first.</p>}
            {busy === "paper" && <p className="text-sm">Matching your university sheet…</p>}
            {paperPreview && (
              <>
                <p className="text-sm">
                  {paperDetected
                    ? `Found ${paperLines} printed lines. Your writing will sit on those lines.`
                    : "No even ruled lines were found, so writing starts below the header on this same sheet."}
                </p>
                <img src={paperPreview} alt="Your university sheet, straightened" className="w-full rounded-xl border border-slate-200 bg-white" />
              </>
            )}
          </Step>

          <Step title="4. Write your assignment">
            <label className="block">
              <span className="sr-only">Assignment text</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9}
                placeholder="Paste or type your assignment here."
                className="w-full resize-y rounded-xl border border-slate-300 bg-slate-50 p-3 text-slate-800 placeholder:text-slate-400 focus:border-ink focus:bg-white focus:outline-none" />
            </label>
            <p className="text-sm">{text.length} characters, about {text.trim() ? estimatePages(text, fontSize) : 0} page(s)</p>
            {paper === "photo" && <p className="text-sm">Writing size 16 pt matches the printed lines on your sheet.</p>}

            <fieldset>
              <legend className="text-sm">Ink</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                {INKS.map((o) => (
                  <button key={o.id} type="button" aria-pressed={ink === o.id} onClick={() => setInk(o.id)}
                    className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${ink === o.id ? "border-ink bg-slate-50 font-semibold text-slate-900" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
                    <span className="h-3 w-3 rounded-full" style={{ background: o.color }} />{o.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="text-sm">Paper</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                {PAPERS.map((o) => (
                  <button key={o.id} type="button" aria-pressed={paper === o.id} onClick={() => setPaper(o.id)}
                    disabled={o.id === "photo" && !paperPreview}
                    className={`rounded-xl border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40 ${paper === o.id ? "border-ink bg-slate-50 font-semibold text-slate-900" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <Slider label="Writing size" value={fontSize} min={10} max={36} suffix=" pt" onChange={setFontSize} />
            <Slider label="Messiness" value={jitter} min={0} max={100} suffix="%" onChange={setJitter} />
          </Step>
        </div>

        <aside className="h-fit min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 lg:sticky lg:top-6">
          <h2 className="text-base font-semibold tracking-tight text-slate-900">Live preview</h2>
          <div className="mt-4 space-y-4">
            {!session && <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Upload your handwriting sheet to see your pages here.</p>}
            {session && !text.trim() && <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Type some text and your handwritten page appears here.</p>}
            {busy === "preview" && <p aria-live="polite">Rendering your pages…</p>}
            {preview?.missing.length > 0 && (
              <p className="text-sm text-margin">Skipped, not in your sheet: {preview.missing.join(" ")}</p>
            )}
            {preview?.images.map((src, i) => (
              <img key={i} src={src} alt={`Page ${i + 1}`} className="w-full rounded-lg border border-slate-200 bg-white shadow-sm" />
            ))}
            {preview?.pages > preview?.images.length && (
              <p className="text-sm">Showing the first {preview.images.length} of {preview.pages} pages. The PDF has all of them.</p>
            )}
            <button type="button" className={btn} disabled={!session || !text.trim() || busy === "pdf" || (paper === "photo" && !paperPreview)} onClick={downloadPdf}>
              {busy === "pdf" ? "Building PDF…" : "Download printable A4 PDF"}
            </button>
          </div>
        </aside>
      </div>
    </main>
  );
}
