# AudioScribe

**AudioScribe is a local-first, job-driven audio ingestion pipeline where the core pipeline is the product and interfaces are thin wrappers.**

It reliably turns a list of YouTube URLs into verified MP3 files with structured metadata, stored locally and managed as a searchable library.  
The same core logic powers the CLI today and can later support a Web API and UI without rewrites.

---

## Core Idea

Most tools treat audio downloading as a one-off action.  
AudioScribe treats it as a **repeatable, inspectable process**.

- URLs become **jobs**
- Jobs produce **verifiable audio assets**
- Assets live in a **managed local library**
- Interfaces are interchangeable (CLI now, Web later)
- **The pipeline itself is the product**

---

## Key Principles

- **Local-first**  
  Audio and metadata live on your machine (filesystem + SQLite)

- **Core-first architecture**  
  All logic lives in a reusable core. Interfaces only parse input and present output

- **Job-based workflow**  
  Every ingestion is tracked, logged, and auditable

- **Incremental & slice-based development**  
  Always runnable, always growing in small, testable steps

- **Future-proof**  
  A Web API or UI can be added without changing the core logic

---

## High-Level Architecture

```text
Interfaces
  └── CLI (first)
      └── Web API (later)
          └── Web UI (optional)

            ↓ calls into

Core (the product)
  ├── Job creation & runner
  ├── Audio extraction (download + encode)
  ├── Quality verification
  ├── Library management
  └── Upload logic

            ↓ uses

Storage
  ├── Filesystem (MP3s)
  └── SQLite database (metadata)

---

---

## License

This project is currently unlicensed.

The license will be added once the project reaches a stable public release.
