---
layout: base.njk
title: How Fichero is made
permalink: /apps/fichero/how-its-made/
---

# How Fichero is made

> *Draft. Daniel hasn't reviewed this yet — pull requests / corrections welcome on [GitHub](https://github.com/dtubb/fichero).*

Fichero is **100% vibe-coded**. Every line of source — Swift, Python, the build scripts, even this page — was written conversationally with an AI assistant.

Here is how that actually works in practice.

## What "vibe-coded" means

I'm an anthropologist. I'm not a professional software engineer. I do not write Swift or Python from scratch.

What I do is sit down with [Claude](https://www.anthropic.com/claude) — Anthropic's AI assistant — and describe what I want, in plain language, and we build it together. Claude does the typing. I do the directing: what should this app do, how should it feel, where is it broken, what should we work on next.

We work in long conversational sessions. A typical session looks like this:

> **Me:** I want to add a way to extract people's names from scanned documents. Then I want to be able to search across documents to find every page that mentions them.
>
> **Claude:** Let me check what's already in the codebase that could help. *(reads the code, finds the existing knowledge-graph layer, proposes a plan)*
>
> **Me:** OK, but I want it on Apple Intelligence too — privacy matters for archival work.
>
> **Claude:** That needs a Swift bridge because Foundation Models is Swift-only. Let me write a small CLI binary and wire it through Python's chat layer. Want me to estimate first?
>
> **Me:** Just do it.
>
> *(Claude writes the code, runs the tests, ships the commit. I run the app, find a bug, describe it.)*
>
> **Me:** It's saving to the wrong document — should be per-page, not per-folder.
>
> **Claude:** Right. Let me refactor. *(refactors, tests, commits.)*

In a single 12-hour day on April 29, 2026, we shipped:

- A typed knowledge-graph layer wired through six catalogue extractors
- Per-page entity extraction with provenance
- A Swift bridge to Apple Intelligence's Foundation Models framework
- A new on-device `Catalogue (Apple Intelligence)` workflow
- Plus a dozen smaller fixes and 49 new tests

I wrote essentially zero of that code by hand. I described the desired behavior, decided trade-offs, tested the result, and reported back what was wrong.

## Why I do it this way

Honestly: because I can't write software on my own. I have ideas about how research tools should work — informed by 20+ years of doing fieldwork, processing archives, writing field notes, and watching graduate students wrestle with the same problems — but I don't have the engineering training to build them.

Before AI assistants, that meant my ideas stayed ideas. I'd hire someone occasionally for a small piece, but a sustained build of something like Fichero was out of reach.

With AI assistance, I can build it. Not because the AI replaces engineering judgment — it doesn't, and pretending it does is a mistake — but because I can do the *direction* part (what should this app be, what should it do, what's the priority) while the AI does the *implementation* part (the actual Swift, Python, SQL, Build settings, error handling).

This division of labor turns out to suit me well. A research tool benefits enormously from having its developer also be its primary user. I notice when something feels wrong because I'm using it daily on real archival material. I notice when a default is annoying. I notice when a workflow's output is shaped wrong for the kind of analysis I want to do.

## What it's not

It's not "the AI built an app." It's not autonomous. It's not magic.

The AI is a fast typist with broad knowledge. It does what I ask. When I ask for the wrong thing, it builds the wrong thing. When I don't know what to ask for, we figure it out together — but the knowing-what-to-ask-for is mine.

It also makes mistakes. A lot of them. Many of the bugs I report turn out to be code the AI wrote two hours earlier that didn't account for some edge case. Debugging is a real activity that we do together, and the AI is sometimes wrong about how to fix what it broke.

It's not a substitute for code review either. I read the diffs. I question architectural decisions. I push back when an estimate feels off (it usually is). The AI's suggestions become *better* when I push, because the conversation surfaces context that the AI didn't have on the first pass.

## What I've learned about doing this

Some patterns that have emerged:

**Audit before building.** The AI's instinct is to build what you ask for. Often the right move is to look around the codebase first to see if it's already there. Hours saved by 10 minutes of searching.

**Write plans before code.** Long sessions go better when we agree on a written plan — design doc, file list, phases — before any code lands. Code without a plan tends to need rewrites.

**Estimates are unreliable until verified.** When the AI says "this will take 3 weeks," challenge it. The 3-week estimate for Apple Intelligence integration turned out to be 2 hours of focused work because the framework was easier to reach than I initially assumed.

**Trust your testing instincts.** I'm not a software engineer but I am the user. When something feels wrong, it usually is wrong, even when the AI thinks it's working. "Show me what you wrote and why" almost always reveals something off.

**Stop and sleep.** A surprising amount of the worst engineering choices I've made happened at midnight when the AI and I were both grinding. The next morning's first review usually reverses three or four of them. Velocity ≠ progress.

## What's in the source

This site (eleventy + markdown), the macOS app (SwiftUI), the embedded Python backend (FastAPI + LangGraph + DuckDB + LanceDB), the ingestion pipeline, the workflow engine, the documentation. All of it. Including this page.

The only things I didn't write are the libraries Fichero depends on — SwiftUI itself, FastAPI, LangChain, etc. Standard open-source dependencies.

## What it costs

Software engineering's old fixed costs — time spent typing, time spent debugging syntax errors, time spent reading documentation — drop dramatically. New costs replace them: AI subscription fees (Claude / OpenAI / Apple Intelligence runs locally) and a higher need for thoughtful direction (because you can ship the wrong thing very quickly).

For Fichero, the LLM costs are real but small. The bigger investment is time: an hour of focused conversation with an AI assistant produces ~1000 lines of code on a good day. That's faster than I'd type, much slower than mass-produced code, and considerably more thoughtful per line than either.

## The honest part

Some of this works because the project is mine. I make all the decisions. There's no team to coordinate, no design review committee, no engineering manager. The AI and I are an aligned pair: I have the goals, it has the keyboard fluency, we both serve the same plan.

Whether this approach scales beyond a one-person research tool is an open question. I don't know if a five-person engineering team could vibe-code together. I don't know if a startup with revenue could survive on it. I just know it's working well enough for one anthropologist to build a research tool that I actually use.

If you want to read the actual code, it's open source: [github.com/dtubb/fichero](https://github.com/dtubb/fichero).

If you want to see what a session looks like, the commit log is honest: every commit message says what we were trying to do, what changed, and what's still open. Reading the log is roughly equivalent to reading the conversation.

If you have thoughts about this approach — patterns that work, patterns that fail, things you've tried — please get in touch. This is a way of building software that I think is going to matter more, and I'd rather we figure out how to do it well than each rediscover the same things alone.

— Daniel
