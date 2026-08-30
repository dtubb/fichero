# Chapter 10. Frequently Asked Questions


**What AI models does Fichero support?** Fichero is model-agnostic. The backend talks to providers through LangChain integrations, and the app includes model-management surfaces. Local options include Apple Foundation Models, MLX, LM Studio, and Ollama; cloud providers include services such as OpenAI, Anthropic, and Google.

**Does it work offline?** Yes, if you use local models. Your library data stays local, and the macOS app runs against its local engine. Internet access is only needed when you choose a cloud provider or a remote backend.

**Does it run on iPhone or iPad?** There are iOS and iPadOS apps available through TestFlight; they connect to an engine running on a Mac. macOS is the primary supported surface today.

**Is my data secure?** Your library data is stored locally. If you use local models, processing stays on your machine. If you use a cloud provider, the content sent to that provider leaves your machine for that request. See Chapter 9.

**Is Fichero free?** Fichero is currently free during alpha development.

**Where do I report bugs or ask questions?** Use [GitHub Discussions](https://github.com/dtubb/fichero/discussions) for questions and feedback. GitHub Issues are the development backlog.

**How is Fichero built?** Fichero is developed in the open with AI coding agents under Daniel Tubb’s direction, with review gates and verification steps. See Appendix B.

**What is the relationship between Fichero and Fichero Toolbox?** They are separate apps. Fichero is the document library and workflow app; Fichero Toolbox is a different project for connecting AI agents to other tools.
