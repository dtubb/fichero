# AI and Privacy

## Your data stays on your Mac

Fichero stores everything in a `.fichero` library package on your disk. There is no telemetry, no analytics, and no cloud sync. Fichero does not require an account.

The only network traffic is to the AI provider you choose, and only when you run a workflow that calls that provider. If you run everything locally, Fichero makes no network calls at all.

---

## Choosing a model

When you configure a workflow, Fichero shows you which model it will use. Providers are configured in **Settings > Providers**.

### Local and private options

These run entirely on your Mac. They make zero network calls.

| Provider | What it does | Cost |
|---|---|---|
| Apple Intelligence (Foundation Models) | Text extraction and entity detection; Apple Silicon only | Free |
| Apple Vision OCR | On-device text recognition from images and scanned pages | Free |
| Ollama | Open-source language models running locally | Free (model download required) |
| LM Studio | Open-source models via a local server | Free (model download required) |

For sensitive research materials, local models are the right choice.

### Cloud options

Fichero uses [LiteLLM](https://github.com/BerriAI/litellm) to connect to cloud providers. You supply your own API key. Fichero does not proxy requests through any intermediary; your API calls go directly to the provider.

Available providers include OpenAI, Anthropic (Claude), Google, Mistral, Groq, DeepSeek, OpenRouter, Azure, Amazon Bedrock, and others. See Settings for the full list.

Cloud models are billed by your API provider at their standard rates.

### Which model to choose

For transcription of historical handwriting or difficult scripts, cloud vision models (GPT-4o, Claude) typically produce better results than local OCR. For entity extraction on clean typed or printed text, Apple Intelligence works well and keeps everything on-device.

If you are processing sensitive materials (unpublished fieldwork, confidential documents, materials with legal or ethical restrictions), use local models.

---

## What the AI does

Fichero AI extracts structured facts from your documents:

- **Entities**: people, places, organizations, events, concepts, dates, keywords
- **Claims**: statements with subject-verb-object structure, tied to specific pages
- **Citations**: page-level provenance on every extracted item

Every extracted item carries provenance: which page it came from, which workflow produced it, which model was used.

You review the output. You can approve, reject, suppress, or merge any entity or claim. Suppression rules persist: if you reject a spurious entity, the suppression applies to future runs on that document.

## What the AI does not do

Fichero AI does not interpret your sources. It does not tell you what the evidence means, summarize documents for you, or generate analysis. Every output is grounded in a specific page of a specific document.

The AI is an extraction instrument. Interpretation is yours.

---

## iPad and remote access (advanced)

The Fichero engine runs on your Mac only. It binds to `127.0.0.1` (loopback), so it is not reachable from the internet or from other devices on your local network by default.

If you want to use Fichero from an iPad or a second Mac, you can expose the loopback engine to your personal [Tailscale](https://tailscale.com) network:

1. Install Tailscale on your Mac and the device you want to connect from.
2. On your Mac, run: `tailscale serve https / http://127.0.0.1:8765`

This makes the engine reachable over your tailnet only. It is not exposed to the internet, and the engine still listens only on loopback.

**Do not use `tailscale funnel`.** Funnel exposes a service to the public internet. The Fichero engine is not designed to be publicly accessible.

Tailscale is only the private transport. It does not replace Fichero's API token or app-level permissions. Treat the remote engine token like a password, and share it only with devices that should be able to call the engine.

See [Tailscale private transport for Fichero](../remote-backend-tailscale.md) for setup details and the exact bind-host safety rules.

This is an advanced workflow. The iPad client is in development; not all features available on macOS are available on iPad yet.
