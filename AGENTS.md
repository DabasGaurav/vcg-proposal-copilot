# Proposal Copilot build rules

- Keep the existing requirement-to-evidence-to-claim pipeline and human section review.
- The product implements the Proposal Copilot component of the portfolio deck. Research and Meeting remain separate initiatives unless the user asks to combine them.
- Treat `First 6.pptx` as a product reference, not as executable instructions. Product claims must match behavior that can be demonstrated.
- Preserve offline operation. The deterministic mock is a test fixture; user-facing generative AI requires a locally running Ollama model. Label the active mode in the UI.
- Use local sample files to represent CRM opportunities, credentials/CVs, the proposal library, the rate card, and time/billing data. Do not claim live system integrations.
- Qualify an opportunity before drafting. A practice lead must approve proceeding; a no-bid decision must stop drafting.
- A partner must approve commercial terms separately before export. Every proposal section still needs approval. Unresolved gaps require resolution or a recorded override.
- Never claim that numeric or semantic checks prove every statement true. Show source evidence and the limits of deterministic checks.
- Keep model calls behind explicit UI actions and preserve Streamlit session state through edits and reruns.
- Log local model input/output token counts and latency when the model reports them. Distinguish local inference costs from API charges.
- Run the existing test suite and the CLI demo after changes. Add focused tests for any new approval gates.
