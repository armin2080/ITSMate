# ITSMate

ITSMate is an AI-powered IT Service Management assistant that works through Microsoft Teams and connects to ServiceNow.

This repository contains the MVP backend for a read-only assistant built with Django, Django REST Framework, a modular LLM provider layer, and a safe ServiceNow integration. The current implementation keeps the LLM constrained to approved backend tools so it cannot generate arbitrary ServiceNow API calls.

## Architecture

```text
Microsoft Teams message
→ Django Teams webhook
→ Chat orchestration service
→ LLM intent parser
→ Safe tool/action selection
→ ServiceNow API client
→ formatted response
→ Microsoft Teams reply
```

Core backend modules live under `backend/apps/`:

- `teams`: receives Teams messages and returns a reply payload.
- `chat`: orchestrates the full flow from user message to ServiceNow action to response.
- `llm`: provider abstraction plus strict intent parsing.
- `servicenow`: ServiceNow REST API client and safe query builder.
- `audit`: persistent audit log model and write service.

## MVP Scope

The first version is read-only and supports:

- incident search
- incident lookup by number
- incident summarization
- audit logging for prompts, intents, tool actions, and response summaries

Write actions are intentionally not implemented yet.

## Setup

1. Create and activate a virtual environment if you do not already have one.
2. Install the Python dependencies.
3. Copy `.env.example` to `.env` and fill in the secrets.
4. Run Django migrations.
5. Start the development server.

Example commands:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
python manage.py migrate
python manage.py runserver
```

## Environment Variables

Required variables:

- `SERVICENOW_INSTANCE_URL=https://dev284757.service-now.com`
- `SERVICENOW_USERNAME=`
- `SERVICENOW_PASSWORD=`
- `LLM_API_KEY=`
- `LLM_MODEL=`
- `DJANGO_SECRET_KEY=`
- `DEBUG=True`

Recommended optional variables:

- `LLM_PROVIDER=groq`
- `DATABASE_URL=` for PostgreSQL later
- `SERVICENOW_TIMEOUT_SECONDS=20`
- `SERVICENOW_MAX_RESULTS=10`
- `ALLOWED_HOSTS=localhost,127.0.0.1`

Browser sign-in now uses your ServiceNow username and password directly.
No OAuth variables are needed for the `/accounts/login/` page.

The backend still uses the configured ServiceNow credentials from `SERVICENOW_USERNAME` and `SERVICENOW_PASSWORD` for the read-only chat tools.

## How the Teams Integration Works

The MVP exposes a webhook-style endpoint at `POST /api/teams/webhook/`.

For quick local testing, a browser chat UI is available at `/api/teams/chat/`.

For local development, you can send a JSON payload containing a user message, for example:

```json
{
	"message": "Show open incidents assigned to Team A",
	"user_id": "user-123",
	"conversation_id": "conversation-abc"
}
```

The Teams view passes the message into the orchestration service, which asks the LLM to classify the intent, validates the returned JSON, and then calls only the approved ServiceNow helper for that intent.

### Chat Memory

ITSMate remembers the current conversation, not every conversation forever.

- Each chat thread is keyed by a `conversation_id`.
- The backend stores recent user and bot turns for that thread.
- The LLM receives the recent turn history so follow-up messages can use context.
- The browser tester keeps a stable `conversation_id` in local storage so the same page keeps its memory across messages.

In a full Teams deployment, this webhook would sit behind a Microsoft Bot Framework endpoint or an equivalent Teams app integration layer. The MVP keeps the channel contract simple so the backend can be developed and tested locally first.

### Local Chat Tester

Start the backend server:

```bash
cd backend
python manage.py runserver 127.0.0.1:8000
```

Then open:

```text
http://127.0.0.1:8000/api/teams/chat/
```

The tester sends requests to the same webhook endpoint used by the Teams flow and shows:

- bot reply text
- detected intent
- parsed parameters
- raw JSON response

## ServiceNow Safety Model

The LLM never receives permission to generate raw ServiceNow queries.

Instead, the backend:

1. asks the LLM for a structured intent payload
2. validates the payload with serializers
3. maps the intent to a fixed backend action
4. constructs the ServiceNow query server-side
5. executes the request with Basic Auth from environment variables

Only a constrained set of read-only filters is supported in the MVP:

- incident number
- state
- priority
- assignment group
- short description keyword
- incidents created today

## Local Database

SQLite is used by default for the MVP. The settings module also supports switching to PostgreSQL later by providing a `DATABASE_URL` value.

## MVP Limitations

- Read-only only; update and delete actions are not implemented.
- Teams integration is a webhook scaffold, not a full production bot registration.
- The LLM provider is currently Groq, but the code is structured so providers can be swapped later.
- The intent parser is strict and will ask for clarification when the request is ambiguous.

## Future Roadmap

- ServiceNow-backed OAuth sign-in for the browser workspace
- incident updates with confirmation
- incident creation
- change request support
- knowledge base search
- CMDB search
- Teams adaptive cards
- role-based permissions
- PostgreSQL deployment
- Docker support

## Project Layout

```text
ITSMate/
	backend/
		manage.py
		itsmate/
		apps/
	.env.example
	requirements.txt
```

## Notes

The current codebase is intentionally modular so the chat workflow, the LLM provider, and the ServiceNow client can evolve independently as the product grows.
