# Optix — Person Tracker for Homes (Backend API)

Optix is a production-ready backend API for an intelligent home surveillance system. Built with FastAPI and Python, it powers real-time person detection, face recognition, event logging, floor plan management, and multi-user household administration. The system integrates YOLOv11 for person detection and DeepFace for identity recognition, enabling it to distinguish between known family members and unrecognised individuals — logging each person's presence and movement through the home.

This repository contains the full backend service. The companion iOS application is available at:
**iOS Repository:** [https://github.com/muhammadhussnainsaeed/Optix-Person_Tracker_for_Homes-iOS](https://github.com/muhammadhussnainsaeed/Optix-Person_Tracker_for_Homes-iOS)

> This system is intended for research and personal home use. Review applicable local privacy laws and regulations before deploying in any environment where individuals may be recorded without consent.

---

## Table of Contents

- [Project Status](#project-status)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation and Setup](#installation-and-setup)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [API Usage Examples](#api-usage-examples)
- [Data Storage](#data-storage)
- [Deployment Considerations](#deployment-considerations)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Project Status

**Stable — Production Ready**

Core features including real-time detection, identity recognition, event logging, floor plan syncing, and the REST API are fully implemented and stable.

---

## Key Features

- **Real-Time Person Detection** — Processes live RTSP camera feeds using YOLOv11 to detect persons frame-by-frame with low latency.
- **Face Recognition and Identity Classification** — Uses DeepFace to classify detected individuals as known family members or unrecognised subjects.
- **Intelligent Alerting** — Differentiates between three event categories:
  - *Family (Allowed)* — Logs presence with context, e.g. "Ali spotted in Kitchen."
  - *Threat Recognition (Reappearing)* — Identifies returning unrecognised individuals from the unwanted persons list and issues a critical alert.
  - *Auto-Indexing (First-Time)* — Automatically registers first-time unknown visitors as new profiles with generated codenames and notifies the user immediately.
- **Codenames for Unrecognised Subjects** — Assigns distinct, user-friendly identifiers (e.g., "Teal Falcon 882") to unknown individuals for consistent tracking across multiple event logs.
- **Journey Tracking** — Groups event logs per individual into a chronological timeline showing movement through the home (e.g., Main Gate → Hallway → Kitchen).
- **Digital Floor Plan Syncing** — Stores vector-based floor maps including rooms, walls, and doors, enabling consistent state across iOS, Android, and web clients.
- **Camera Management** — Full CRUD support for RTSP and video stream sources, with optional privacy tagging per camera.
- **Family Profile Management** — Register household members with photo uploads used to train and improve face recognition accuracy.
- **Secure Authentication** — JWT-based user authentication with sign-up, sign-in, and password recovery flows using secure password hashing.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Framework | FastAPI |
| Database | PostgreSQL (JSONB for floor plans, UUID primary keys) |
| Person Detection | YOLOv11s (custom trained weights) |
| Face Recognition | DeepFace, OpenCV |
| Authentication | JWT (JSON Web Tokens) |
| Schema Validation | Pydantic |
| Application Server | Uvicorn / Gunicorn |

---

## Repository Structure

```
Optix-Person_Tracker_for_Homes-Backend/
├── config.py                    # Global configuration and environment variables
├── main.py                      # Application entrypoint
├── requirements.txt             # Python dependencies
├── ai_engine/                   # Computer vision and model orchestration
│   ├── face_extractor.py        # Face detection and cropping utilities
│   ├── face_recognition.py      # Identity matching via DeepFace
│   ├── orchestrator.py          # Coordinates detection workers and camera feeds
│   ├── vision_worker.py         # Per-camera frame processing worker
│   └── weights/
│       └── best.pt              # Trained YOLOv11s model weights
├── api/                         # REST API route handlers
│   ├── dashboard.py             # Dashboard and summary endpoints
│   ├── cameras.py               # Camera CRUD and stream management
│   ├── family.py                # Family member profiles and photo management
│   └── unwanted_person.py       # Unwanted person registry and alert endpoints
├── core/                        # Security, authentication, and domain logic
├── db/                          # Database session management and CRUD helpers
├── media/                       # Persistent storage for snapshots and recordings
│   ├── events/
│   │   ├── family/              # Events associated with known members
│   │   └── unwanted/            # Events flagged as unknown or threat
│   ├── snapshots/               # Frame-level snapshot crops
│   └── persons/                 # Face galleries used for recognition
└── schemas/                     # Pydantic request and response schema definitions
```

---

## Prerequisites

- Python 3.8 or later (Python 3.10+ recommended)
- PostgreSQL instance (local or hosted)
- GPU recommended for real-time performance; CPU-only operation is supported but will reduce throughput
- RTSP-capable cameras or video stream sources

---

## Installation and Setup

**1. Clone the repository**

```bash
git clone https://github.com/muhammadhussnainsaeed/Optix-Person_Tracker_for_Homes-Backend.git
cd Optix-Person_Tracker_for_Homes-Backend
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Verify model weights**

Confirm that the trained YOLOv11s weights are present at:

```
ai_engine/weights/best.pt
```

If you are using a custom-trained model, update the weights path in `ai_engine/orchestrator.py` or via `config.py`.

**5. Configure environment variables**

Copy and populate the environment configuration before running (see [Configuration](#configuration)):

```bash
cp .env.example .env
```

---

## Configuration

All application-level settings are managed through `config.py` and environment variables. Key values to configure before running:

| Setting | Location | Description |
|---|---|---|
| Database URL | `config.py` / `.env` | PostgreSQL connection string |
| Camera endpoints | `config.py` / API | RTSP stream URLs per camera |
| File storage paths | `config.py` | Base paths for `media/` subdirectories |
| JWT secret key | `config.py` / `.env` | Secret used to sign and verify tokens |
| Logging level | `config.py` | Set to `DEBUG` for development, `INFO` for production |
| Model weights path | `ai_engine/orchestrator.py` | Path to `best.pt` or a custom weights file |

Additional API-level settings are located in `api/settings.py` and `schemas/settings.py`.

Do not commit secrets or credentials to source control. Use environment variables or a secrets manager for all sensitive values.

---

## Running the System

**Full system — orchestrator and API together (recommended for development)**

```bash
python main.py
```

This starts the detection orchestrator, camera workers, and the API service together. Monitor the console output for startup confirmation and camera connection status.

**API only — serve REST endpoints without the detection engine**

```bash
pip install uvicorn
uvicorn api.dashboard:app --reload
```

Adjust the import target (`api.dashboard:app`) if your FastAPI application object is defined in a different module.

**Production deployment with Gunicorn**

```bash
gunicorn api.dashboard:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## API Usage Examples

The following examples assume the API is running at `http://localhost:8000`. Replace with your deployed host as needed.

**User authentication — sign in and retrieve a JWT**

```bash
curl -X POST http://localhost:8000/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "your_password"}'
```

For a full list of endpoints, start the server and navigate to the interactive API documentation at `http://localhost:8000/docs` (Swagger UI).

---

## Data Storage

**Database**
Events, user sessions, camera records, and floor plan data are managed via the helpers in `db/`. Review `db/session.py` to configure the database engine and connection pool settings.

**File storage**
Captured media is written to the `media/` directory:

| Path | Contents |
|---|---|
| `media/events/family/` | Event snapshots for known family members |
| `media/events/unwanted/` | Snapshots and clips for flagged unknown individuals |
| `media/snapshots/` | General frame-level crops |
| `media/persons/` | Face gallery images used for recognition training |

Ensure the `media/` directory has sufficient disk space and appropriate read/write permissions for the running process.

---

## Deployment Considerations

- **TLS / HTTPS** — Always serve the API behind TLS in any network-accessible deployment. Use a reverse proxy such as Nginx or Caddy to terminate SSL.
- **Authentication** — Enforce strong passwords and rotate JWT secret keys periodically. Do not expose the API publicly without authentication.
- **GPU provisioning** — The YOLOv11s detection model is computationally intensive. A CUDA-compatible GPU is strongly recommended for real-time processing across multiple camera feeds.
- **Data retention** — Define and enforce a media retention policy. Stored recordings and snapshots can grow rapidly. Consider automated cleanup or archival based on event age.
- **Privacy and legal compliance** — Ensure that all recorded individuals are informed where required by law. This system should not be deployed in shared or public spaces without appropriate legal review.
- **Camera security** — Sanitise and validate all camera endpoint URLs. Restrict RTSP access to trusted network segments.

---

## Contributing

Contributions from developers, researchers, and integrators are welcome. Please follow the process below.

**Workflow**

1. Fork the repository.
2. Create a branch with a descriptive name:
   ```bash
   git checkout -b feat/add-alert-webhook
   # or
   git checkout -b fix/face-recognition-timeout
   ```
3. Make focused, well-documented changes. Update `README.md` if your change affects setup, configuration, or API behaviour.
4. Open a pull request with a concise description of the change, the motivation behind it, and any relevant test output or screenshots.

**Guidelines**

- For new model architectures or detector replacements, place weights under `ai_engine/weights/` and update `ai_engine/orchestrator.py` accordingly.
- For API changes, add or update route handlers under `api/` and update corresponding schema definitions under `schemas/`.
- Do not commit secrets, credentials, trained weights over 100 MB, or media files to source control.
- Open an issue first for large or breaking changes to align on approach before implementation.

---

## License

This project is open source.
---

## Contact

**Muhammad Hussnain Saeed**
GitHub: [@muhammadhussnainsaeed](https://github.com/muhammadhussnainsaeed)

For questions about the iOS client or cross-platform integration, refer to the [iOS repository](https://github.com/muhammadhussnainsaeed/Optix-Person_Tracker_for_Homes-iOS). For backend-specific issues or feature requests, open an issue in this repository.
