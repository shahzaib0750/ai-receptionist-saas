# AI Receptionist SaaS Backend

FastAPI backend for user authentication, business workspaces, receptionist and
Vapi configuration, and business-scoped Vapi call history.

## Architecture

- FastAPI REST API, versioned under `/api/v1`
- PostgreSQL with SQLAlchemy and Alembic migrations
- Pydantic request and response validation
- Argon2 password hashing and short-lived JWT access tokens
- Password changes immediately revoke previously issued access tokens
- Business membership roles with endpoint-level authorization
- Vapi webhook authentication and persisted call lifecycle events

## Environment

The application reads configuration from environment variables and `.env` in
the current working directory. Configure these variable names; do not commit
secret values:

| Variable | Purpose |
|---|---|
| `APP_NAME` | API title |
| `APP_ENV` | `development`, `test`, `staging`, or `production` |
| `DEBUG` | FastAPI debug mode |
| `API_V1_PREFIX` | Versioned API prefix |
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `SECRET_KEY` | JWT signing key; must contain at least 32 characters |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime, from 1 to 1440 minutes |
| `VAPI_API_KEY` | Server-only Vapi API credential used for managed assistant and number setup |
| `PUBLIC_API_BASE_URL` | Public HTTPS backend origin used by Vapi to send authenticated webhooks |
| `VAPI_MODEL_PROVIDER` | Vapi assistant model provider |
| `VAPI_MODEL` | Vapi assistant model name |
| `VAPI_VOICE_PROVIDER` | Vapi assistant voice provider |
| `VAPI_VOICE_ID` | Vapi assistant voice identifier |
| `VAPI_RECOVERY_ENABLED` | Enables the standalone Vapi event recovery worker |
| `VAPI_RECOVERY_POLL_INTERVAL_SECONDS` | Delay between recovery batches; must be positive |
| `VAPI_RECOVERY_BATCH_SIZE` | Maximum receipts per batch, from 1 to 1000 |
| `VAPI_RECOVERY_MAX_ATTEMPTS` | Attempts before a receipt is marked terminally failed |
| `VAPI_RECOVERY_MAX_BACKOFF_SECONDS` | Maximum delay before retrying a failed receipt |
| `TWILIO_ACCOUNT_SID` | Server-only platform Twilio account for number provisioning |
| `TWILIO_AUTH_TOKEN` | Server-only platform Twilio credential |
| `VAPI_WEBHOOK_SECRET` | Bearer token expected by the Vapi webhook |
| `PAYMENT_PROVIDER` | Optional payment provider name |
| `PAYMENT_SECRET_KEY` | Optional payment provider credential |
| `PAYMENT_WEBHOOK_SECRET` | Optional payment webhook credential |
| `BILLING_ADMIN_USER_IDS` | Comma-separated UUIDs authorized to administer platform billing |
| `FRONTEND_ORIGIN` | Allowed browser origin for CORS |

`DB_PASSWORD` and `SECRET_KEY` are required. Keep `.env` out of version
control, use unique production credentials, and use HTTPS for public traffic.

## Local development

From the repository root, create the backend virtual environment and install
the declared dependencies:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

Configure PostgreSQL and the environment variables above, then apply migrations:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m alembic \
  -c backend/alembic.ini upgrade head
```

Start the API:

```bash
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --reload
```

Run the recovery worker in a separate process using the same database
configuration as the API:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.workers.vapi_recovery
```

The worker continuously polls bounded batches, can run as multiple independent
processes, and handles SIGINT/SIGTERM by finishing its current batch before
shutting down. Do not start it inside Uvicorn workers.

Interactive API documentation is available at `/docs`; the OpenAPI document is
at `/openapi.json`. Liveness and database readiness endpoints are available at
`/api/v1/health/live` and `/api/v1/health/ready`.

Run the backend tests with:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/ -q
```

### Frontend

The React frontend uses JavaScript and JSX. From the repository root:

```bash
npm install
cp .env.example .env.local
npm run dev
```

Vite reads `VITE_API_BASE_URL` from `.env.local`; the development default is
`http://127.0.0.1:8000/api/v1`. Keep this file limited to frontend `VITE_`
settings; never put backend secrets in Vite environment files. Restart Vite
after changing environment variables. The frontend provides authentication,
public marketing and pricing pages, business workspaces and members, managed
receptionist onboarding, call history, account settings, and subscription/usage
pages. Customers do not enter Vapi credentials or identifiers. The published
pricing catalog is publicly readable; workspace billing information remains
business-permission protected.
Call records are only available to business owners and admins. Unsupported
features such as appointment management and billing are not simulated.

Validate frontend changes with:

```bash
npm run lint
npm test
npm run build
```

## Managed onboarding and Vapi integration

Business owners complete `/onboarding` with a profile, natural-language
receptionist brief, fallback guidance, and country for a local voice number.
Before provisioning begins, the owner must explicitly authorize the platform to
purchase a number; provider charges and local availability requirements apply.
The only offered service is inbound AI call answering. Appointment booking,
call transfers, and CRM lead capture are not enabled because their backend
services are not implemented.

The backend creates the Vapi assistant, buys a voice-enabled local number on
the platform Twilio account, imports it into Vapi, and configures the webhook.
The phone is not assigned to the assistant until the owner activates the
receptionist. Failed setup retains completed provider resource IDs and the
reserved number so retries can resume without intentionally creating duplicate
resources. Setup currently runs synchronously in the API request; a failed
request can be retried from onboarding. Provider account funding, number
availability, and regional regulatory requirements apply. Keep all provider
credentials on the backend, never in Vite environment variables or browser code.

Provisioning moves a business to `ready` only after the assistant and phone
number are configured. The owner must explicitly activate it before calls are
handled. Failed provisioning is reported as `failed`; it is never presented as
active. Number purchase consent is recorded with the consenting user and time.

Assistant model and voice selections are controlled by the server-side
`VAPI_MODEL_PROVIDER`, `VAPI_MODEL`, `VAPI_VOICE_PROVIDER`, and `VAPI_VOICE_ID`
settings. Ensure the corresponding provider credentials are available to the
Vapi account.

The existing webhook endpoint is:

```text
https://<your-public-host>/api/v1/integrations/vapi/webhook
```

New managed assistants receive this webhook URL and server-only authorization
automatically. The manual setup instructions below are retained for existing
legacy integrations. The webhook accepts documented `status-update` and `end-of-call-report`
messages. It stores deduplicated call lifecycle events and available call
metadata. Call summaries are available at
`GET /api/v1/businesses/{business_id}/calls`; transcript and recording
metadata are returned only from the authorized call detail endpoint. Call data
is restricted to business owners and admins; regular members cannot read it.

### Webhook authentication

The endpoint requires a Bearer credential and does not accept unauthenticated
requests:

1. In Vapi, create a Custom Credential for the server URL.
2. Configure it to send the token in the `Authorization` header and enable the
   Bearer prefix.
3. Set that token to the value configured as `VAPI_WEBHOOK_SECRET` on this
   backend.
4. Attach the credential to the effective server URL configuration (organization,
   assistant, or phone number), then save and test the configuration.

The backend expects `Authorization: Bearer <VAPI_WEBHOOK_SECRET>`. An unset
backend secret returns `503`; a missing, malformed, or mismatched credential
returns `401`. Diagnostic logs record only whether the header was present,
whether the Bearer scheme was received, and whether the credential matched.
They do not log the credential or caller data.

Vapi's server-authentication documentation notes that organization credentials
are not automatically attached when a server URL is supplied in an API request.
For that configuration, provide the credential reference in the server
configuration itself. A `401` means the deployed secret and received
Authorization credential do not match (or Vapi did not attach the expected
Bearer credential); confirm the effective URL scope and Bearer-prefix setting
in the Vapi dashboard rather than disabling authentication.

## Current scope

Authentication, profile and password changes, business and member management,
business onboarding, supported-service selection, managed assistant and phone
provisioning, activation status, authenticated webhook processing, call history,
health checks, billing usage metering, plan administration, and billing views
are implemented. Business-facing billing data is tenant-scoped; platform billing
administration is restricted to UUIDs in `BILLING_ADMIN_USER_IDS`.

### Billing integration status

The database-backed billing foundation records plans, subscriptions, provider
events, invoices, payments, per-period usage, and audited minute grants. Usage
is derived from finalized Vapi call records: exact billable seconds are summed
for the applicable billing period and rounded up once to whole minutes.
Inbound calls continue to be answered after the included allowance is exhausted;
the allowance blocks new phone provisioning, not inbound service. No automatic
overage charge is created.

Payment actions are intentionally unavailable until a concrete payment
provider adapter is implemented and configured. The current provider interface
is an integration boundary, not a live gateway. The normalized signed webhook
contract must be mapped and verified against the chosen provider's official
signature and event format before production use. Provider events are not a
substitute for reconciliation with that provider. Do not treat configured
prices, locally created plans, or a successful API response as proof that a
payment was collected.

Set `BILLING_ADMIN_USER_IDS` to a comma-separated list of trusted, already
provisioned user UUIDs; do not use email addresses or allowlist values supplied
by customers. Apply schema changes using Alembic after verifying the target
database, and test migrations against a disposable or isolated database before
production rollout.

Appointments, call transfer, structured contact/lead capture, and email-based
invitation delivery are not implemented.
