# Secondhand Market — Real-Time Auction Server

> _A second-hand marketplace backend with live auctions, virtual-currency payments, and real-time chat — built async, end to end._

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-aiomysql-4479A1?logo=mysql&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-Realtime-010101?logo=socketdotio&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-migrations-1F4E79)
![Docker](https://img.shields.io/badge/Docker-GHCR%20%2B%20EC2-2496ED?logo=docker&logoColor=white)

Backend server for a second-hand trading platform with a live auction feature — a **Waffle Studio** 23.5 Team 9 project.

## Overview

The server is a fully asynchronous FastAPI service backing a location-based second-hand marketplace. It exposes a REST API for users, products, regions, virtual-currency payments, and image uploads, layered with a real-time subsystem that powers live auctions and WebSocket chat. The codebase follows a clean per-domain module layout (router → service → repository over SQLAlchemy 2.0 async ORM models), with MySQL as the system of record, JWT-based stateless auth plus Google OAuth2, and an S3-backed image store. Everything runs on async SQLAlchemy (`aiomysql`) and `uvicorn`, and ships as a Docker image deployed to EC2 behind nginx.

## Technical Highlights

- **Auction domain & bidding.** Auctions are modeled as a one-to-one extension of a `Product` (`Auction` carries `current_price`, `end_at`, `bid_count`, and a `status` of `active / finished / failed / canceled`), with each `Bid` linked to its auction and bidder. The `place_bid` flow validates that the auction is still `ACTIVE`, that the deadline has not passed, and that the new bid strictly exceeds the current price, then inserts the bid and bumps `current_price` / `bid_count` **within a single committed transaction** so the highest price and the winning bid stay consistent. Auction listings support category and region filtering with eager-loaded product data, ordered by closing time.
- **Real-time chat over WebSocket.** A WebSocket endpoint (`/api/chat/ws/{room_id}`) authenticates the client via a JWT sent as the first message, then enters a receive-broadcast loop. Incoming messages are routed to the correct table — 1:1 (`ChatRoom`) or group (`GroupChatRoom`, with membership verification) — persisted as `ChatMessage`, and fanned out to every connected peer in the room through an in-process `ConnectionManager` that tracks sockets by room id. The system supports both direct messaging and open group rooms (admin/kick/leave/join semantics), making it suitable for auction-participant group chat.
- **Authentication & sessions.** Stateless JWT auth issues short-lived access tokens and long-lived refresh tokens (HS256, distinct secrets per token type). Passwords are hashed with **Argon2**, verified off the event loop via a thread executor. Token rotation is supported on refresh, and revocation is handled by a `blocked_tokens` denylist checked on every refresh/logout. Social login is implemented with **Authlib + Google OAuth2** (OpenID Connect), auto-provisioning users on first login and linking social accounts to existing emails. Starlette `SessionMiddleware` carries the OAuth flow state.
- **Virtual-currency payments.** A double-entry-style `Ledger` records `DEPOSIT / WITHDRAW / TRANSFER` transactions against per-user `coin` balances. Money movement is **idempotent** (keyed by a client-supplied `request_key`) and **concurrency-safe**: balances are mutated under `SELECT ... FOR UPDATE` row locks inside nested transactions, and transfers acquire the two participant locks in a deterministic id order to avoid deadlocks.
- **Location-aware regions.** Regions are stored with native MySQL **spatial `GEOMETRY`** columns (SRID 4326). Coordinates are ingested via `ST_GeomFromGeoJSON`, and "nearby" lookup resolves a latitude/longitude pair to its containing administrative region with `ST_Contains(...)`, alongside text search over sido/sigugun/dong hierarchy.
- **Persistence & migrations.** SQLAlchemy 2.0 declarative models (`Mapped[...]` typing) over an async engine with connection pooling (`pool_pre_ping`, `pool_recycle`). Schema is version-controlled with **Alembic**, which runs migrations synchronously via `pymysql` while the app itself uses `aiomysql`.
- **Image uploads.** Multipart uploads stream directly to **AWS S3** (`boto3`) under a generated UUID key, with the resulting public URL recorded in an `Image` row and referenced from products and user profiles.
- **REST surface.** Routers are mounted under `/api`: `auth`, `user`, `product`, `auction`, `chat`, `pay`, `region`, `image`, `category`. Domain errors surface through a unified `CarrotException` handler returning structured `{error_code, error_msg}` responses, with a custom handler for missing-field validation.
- **Deployment.** A GitHub Actions workflow builds the Docker image, pushes it to **GHCR**, and SSH-deploys to **EC2** — generating the environment file from secrets, running `alembic upgrade head`, and rolling the container behind nginx (with Let's Encrypt/certbot TLS). The `dev` and `prod` branches map to separate images and environments.

> **Status note:** The platform is an actively developed team project. The auction REST endpoints for creating and fetching auction detail are present in code but currently commented out (the bidding and listing endpoints are live), and the chat `ConnectionManager` is in-process, so real-time fan-out is scoped to a single server instance.

## Architecture

The service is organized by domain under `carrot/app/*`, each module following a **router → service → repository** flow over SQLAlchemy models. `carrot/main.py` builds the FastAPI app, wiring session and CORS middleware and the global exception handlers; `carrot/api.py` aggregates every domain router under the `/api` prefix. Database access is centralized in `carrot/db`, where a `DatabaseManager` owns the pooled async engine and a request-scoped `get_db_session` dependency yields an `AsyncSession` that auto-commits on success and rolls back on error. Authentication is enforced through FastAPI dependencies (`login_with_header` and variants) that decode the bearer JWT and load the current user. The real-time layer lives alongside the chat domain: a WebSocket route persists messages through the same async session factory and broadcasts via a shared in-memory connection registry. Schema evolution is decoupled from runtime through Alembic migrations.

## Tech Stack

- **Language:** Python 3.11
- **Web framework:** FastAPI 0.128 / Starlette, served by Uvicorn (uvloop, httptools)
- **ORM / DB:** SQLAlchemy 2.0 (async) + `aiomysql` over MySQL; Alembic for migrations (`pymysql` sync driver)
- **Auth:** Authlib (JWT HS256 + Google OAuth2 / OIDC), Argon2 password hashing
- **Real-time:** Native WebSockets via FastAPI/Starlette
- **Validation / config:** Pydantic v2, pydantic-settings (env-file driven)
- **Storage:** AWS S3 via boto3
- **Tooling:** `uv` for dependency management; Docker, GitHub Actions, nginx, certbot for delivery

## Getting Started

### Prerequisites

- Python 3.11+ and [`uv`](https://github.com/astral-sh/uv)
- A MySQL instance (the app uses async `aiomysql`; spatial features require MySQL with GIS support)
- Google OAuth2 client credentials (for social login)
- AWS credentials in the environment if exercising image upload (boto3 → S3)

### Configuration

Environment is selected by the `ENV` variable (`local` / `dev` / `test` / `prod`) and loaded from the matching `.env.<ENV>` file. Copy an example and fill it in:

```bash
cp .env.local.example .env.local
# set DB_USER, DB_PASSWORD, DB_DATABASE, the token/session secrets,
# Google OAuth credentials, and FRONTEND_URL
```

### Install & run

```bash
# install dependencies into a managed virtualenv
make sync            # == uv sync

# apply database migrations
uv run alembic upgrade head

# start the API (defaults to ENV=local)
uv run uvicorn carrot.main:app --reload
```

The API is then available at `http://localhost:8000`, with interactive docs at `/docs`. The root route returns a health greeting and all endpoints are served under `/api`.

### Run with Docker

```bash
docker build -t secondhand-market-server .
docker run --env-file .env.dev -e ENV=dev -p 8000:8000 secondhand-market-server
```

The container launches `uvicorn carrot.main:app` on port `8000`. For the full reverse-proxy + TLS topology used in deployment, see `deploy/docker-compose.yml` and `deploy/nginx`.

### Regenerating `requirements.txt`

The pinned `requirements.txt` (used by the Docker build) is exported from the `uv` lockfile:

```bash
make reqs
```
