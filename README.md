# Explainable Multi-Agent AI for Police Case Intelligence, Investigation Support, and Resource Optimization

A decision-support platform for the Sierra Leone Police that reads case narratives, links
related cases, suggests investigation leads, recommends patrol/investigator allocation, and
explains every recommendation in plain language. Built for a final year diploma project at
IPAM, University of Sierra Leone. Uses **simulated, anonymised data only** — see Chapter 1,
Scope and Limitations.

## Quick start (Windows, PowerShell, inside VS Code)

1. Unzip this folder and open it in VS Code (File > Open Folder).
2. Make sure PostgreSQL is installed and running, and you know its password.
3. Open a terminal (Terminal > New Terminal) and run:
   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   .\setup.ps1
   ```
4. When setup.ps1 pauses at Step 4, open `.env` and set `PGPASSWORD` to your real PostgreSQL
   password, save the file, then let setup.ps1 finish.
5. From then on, to start the system, run:
   ```
   .\run.ps1
   ```
6. Open your browser to **http://127.0.0.1:8000**

## Demo accounts (created by the seed script)

| Username  | Password      | Role                   |
|-----------|---------------|------------------------|
| commander | Commander@123 | Police Commander       |
| clerk1    | Clerk@123     | Case Records Clerk     |
| officer1  | Officer@123   | Investigating Officer  |
| admin     | Admin@123     | System Administrator   |

## Running the automated tests (for Chapter 2, Testing Methodology)

```
pytest -v
```

## Project layout

```
app/                 backend (FastAPI, database, security, the 4 agents)
  agents/            Case Intelligence, Investigation Support, Resource Optimization,
                      Explainability, and the Controller that connects them
static/index.html    the frontend (React, single file, no build step needed)
scripts/seed.py      creates the database, demo users, simulated cases, trains the model
tests/                automated tests
```
