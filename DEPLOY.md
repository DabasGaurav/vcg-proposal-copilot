# Demonstration setup

## Full offline AI demonstration (recommended for the course)

Run the application and Ollama on the same laptop. Install dependencies with
`pip install -r requirements.txt`, install Ollama, and download the model once
while connected to the internet:

```bash
ollama pull gemma3
python scripts/seed_corpus.py
LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest streamlit run app.py
```

After the model is downloaded, the app calls only `127.0.0.1` for generation.
Keep **Include external market context** disabled; the UI disables it in local
mode. The CRM, HR, rate-card, and time/billing records are fictional files in
`data/sample_systems/`. There are no live enterprise-system connections.

Test the entire path on the presentation laptop. Local extraction can be slow,
especially on long PDFs. Prepare a full run in advance and time a short live
section demonstration. Clearly label prepared and live outputs. Show the active
provider and token/latency log in the Execution tab.

## Public URL (simulation only)

The Streamlit Community Cloud URL, if deployed, runs the deterministic mock
unless an external provider is explicitly configured. It is useful for a
zero-install walkthrough but is not evidence that a live model generated the
proposal. A public Streamlit server cannot use the presenter's local Ollama
instance. The current public URL may run an older version until the updated
repository is deployed.

On Community Cloud, choose this repository and `app.py` as the entry point.
Storage is ephemeral, so saved runs may disappear after restart or redeploy.
Never upload confidential client documents to that public demo.

## Backup

`python scripts/run_demo.py` exercises the deterministic fixture and prints the
18% supported versus 35% unsupported traceability example. It is a backup
simulation, not a substitute for showing local AI generation.
