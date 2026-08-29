# Chapter 9. AI and Privacy


### Your Data Stays on Your Mac

Fichero stores its library data in a `.fichero` package on your disk. It does not require an account or a hosted Fichero service.

When you use the local engine and local models, your documents stay on your Mac. When you choose a cloud AI provider or a remote backend, the content involved in that request leaves your machine for that call.

### Choosing a Model

When you configure a workflow, Fichero shows you which model it will use. Provider and model setup lives in **Settings \> AI \> Models & Providers**.

#### Local and private options

These run entirely on your Mac and make zero network calls.

| Provider | What it does | Cost |
|----|----|----|
| Apple Intelligence (Foundation Models) | Text extraction and entity detection; Apple Silicon only | Free |
| Apple Vision OCR | On-device text recognition from images and scanned pages | Free |
| Ollama | Open-source language models running locally | Free (model download required) |
| LM Studio | Open-source models via a local server | Free (model download required) |

For sensitive research materials, local models are the right choice.

#### Cloud options

Fichero connects to cloud providers through LangChain provider integrations. You supply your own API key. Fichero does not proxy requests through any intermediary; your API calls go directly to the provider. (LiteLLM is used only to look up model names and estimate cost, not to route or send your content.)

Available providers include OpenAI, Anthropic, Google, Mistral, Groq, DeepSeek, OpenRouter, Azure, Amazon Bedrock, and others. See Settings for the full list in the build you are running. Cloud models are billed by your API provider at their standard rates.

#### Which to choose

For transcription of historical handwriting or difficult scripts, cloud vision models typically produce better results than local OCR. For entity extraction on clean typed or printed text, on-device models work well and keep everything local. If you are processing sensitive materials — unpublished fieldwork, confidential documents, materials with legal or ethical restrictions — use local models.

### What the AI Does

Fichero’s AI extracts structured facts from your documents:

- 
- 
- 

**Entities** — people, places, organizations, events, concepts, dates, keywords**Claims** — statements with subject–verb–object structure, tied to specific pages**Citations** — page-level provenance on every extracted itemEvery extracted item carries provenance: which page it came from, which workflow produced it, which model was used. You review the output — approve, reject, suppress, or merge any entity or claim — and suppression rules persist to future runs.

### What the AI Does Not Do

Fichero’s core promise is provenance and inspectability. It can transcribe, extract, catalogue, and summarize, but those outputs stay tied to specific documents, pages, and workflow runs so you can review them yourself. Interpretation is yours.

### iPad and Remote Access (Advanced)

The Fichero engine runs on your Mac only. It binds to `127.0.0.1` (loopback), so it is not reachable from the internet or from other devices on your network by default.

If you want to use Fichero from an iPad or a second Mac, you can expose the loopback engine to your personal [Tailscale](https://tailscale.com) network:

1.  
2.  

Install Tailscale on your Mac and on the device you want to connect from.On your Mac, run: `tailscale serve https / http://127.0.0.1:8765`This makes the engine reachable over your tailnet only. It is not exposed to the internet, and the engine still listens only on loopback.

**Do not use** `tailscale funnel`**.** Funnel exposes a service to the public internet, and the Fichero engine is not designed to be publicly accessible.

Tailscale is only the private transport. It does not replace Fichero’s API token or app-level permissions. Treat the remote engine token like a password, and share it only with devices that should be able to call the engine.
