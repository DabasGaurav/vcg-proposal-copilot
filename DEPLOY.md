# Deploying the demo (zero-setup URL for evaluators)

The app runs **fully offline** — deterministic mock LLM, TF-IDF embeddings, local
vector store that builds itself on first load. No API keys, no secrets, nothing
to configure. An evaluator just opens the URL and drives it.

## Option A — Streamlit Community Cloud (recommended, free)

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. Go to <https://share.streamlit.io> → **Sign in with GitHub**.
3. **New app** → pick:
   - Repository: `DabasGaurav/vcg-proposal-copilot`
   - Branch: `main`
   - Main file path: `app.py`
4. **Deploy**. First build takes ~2–3 min (installs `requirements.txt`, then the
   app seeds the knowledge base on first open — a one-time ~5 s step).
5. You get `https://<name>.streamlit.app`. Share that link.

### If the repo is private
Streamlit will ask to authorise access to your private repos during "New app".
Grant it. (Or make the repo public: GitHub → Settings → Change visibility.)

### Keep it warm for judging
Community Cloud sleeps an idle app after ~7 days and cold-starts in ~30 s. Open
the URL yourself ~10 min before the session so it's hot.

### Notes
- `runtime.txt` pins Python 3.11.
- `.streamlit/config.toml` sets the theme and headless server options.
- Storage on Community Cloud is ephemeral: the SQLite audit log / resumable runs
  reset on redeploy. Fine for a demo; each fresh session still shows the full
  audit trail for runs done in that session.
- To route through a real model instead of the mock, set the app's **Secrets**
  in the Community Cloud dashboard:
  ```
  LLM_PROVIDER = "litellm"
  LLM_MODEL = "anthropic/claude-sonnet-5"
  ANTHROPIC_API_KEY = "sk-ant-..."
  ```
  Leave them unset for the demo — the mock is what makes the run reproducible.

## Option B — Hugging Face Spaces

Create a Space → SDK **Streamlit** → push this repo to it. Same `app.py`,
same `requirements.txt`. Also free, also public URL.

## Option C — Docker (any container host)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/seed_corpus.py
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t vcg-copilot . && docker run -p 8501:8501 vcg-copilot
```

## Backup that cannot fail on stage

`python scripts/run_demo.py` prints the traceability matrix and the 18 % / 35 %
result in a terminal — no browser, no server. Record a short screen capture of
the Streamlit walkthrough as a second fallback.
