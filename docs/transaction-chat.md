# Transaction assistant

Open **AI chat** after signing in (desktop and mobile). Describe one expense, income,
or transfer in natural language. Reply to follow-up questions or send corrections.
Review the amount, currency, category, source/destination accounts, date/time and note,
then choose **Confirm and save transaction**. The assistant never saves on a chat message.
Start a new conversation for another transaction. Editing/deleting existing records
and analytics questions are outside this feature's scope.

## Configuration

Uses the existing `[llm_text_recognition]` provider and model; no second provider or
browser-side API key. Set `[ai] transaction_from_ai_text_recognition = true`, select
`llm_provider`, and configure that provider's model ID and credentials in your private
`conf/ezbookkeeping.ini` (or the application's existing environment overrides). Restart
the app after configuration. Do not commit credentials. Without a provider, the chat
shows a setup message and the server rejects AI requests.

Account/category names, currencies, chat messages, and local current time are sent to
the configured AI service. Conversation history is memory-only, bounded to 20 messages
and 24 KB of content, and cleared on logout/lock/account change. AI providers may retain
submitted content under their own terms. AI suggestions may be wrong; review every draft.

The model sees only the authenticated user's visible accounts and leaf categories.
Unknown/duplicate names, invalid amounts/dates, incomplete transfers, and unsupported
transaction types do not produce a savable draft. Rename duplicate account/category
names to distinguish them. Missing dates default to current app-local time; the
assistant is instructed to disclose this. No currency conversion is invented.
Positive amounts have at most two decimal places, matching the existing ledger.

The server allows one active chat request per user. Normal authentication, feature
restrictions, transaction validation, ownership checks and duplicate-submission
protection are retained. Keep the same preview when retrying a failed save; the
same client session ID is reused. If an outcome is uncertain, check the transaction
list before starting a new draft.

## Build and deployment

Run `npm ci`, `npx vue-tsc --noEmit`, `npm test`, `npm run build`, and
`go test ./pkg/api ./pkg/models ./pkg/llm/...`.
For lower-memory frontend builds after a separate TypeScript check, use
`NODE_ENV=production npx vite build --config vite.chat-build.config.ts`. This uses
native minification and disables the duplicate in-build type checker.

Build on a development machine, not the production VPS:

    docker build --platform linux/amd64 -f deploy/Dockerfile.chat \
      --build-arg COMMIT_HASH="$(git rev-parse --short HEAD)" \
      -t ezbookkeeping:transaction-chat .

Back up the SQLite database, uploads and configuration before changing the image.
Validate against a separate database copy and port first. Update only the
`ezbookkeeping` Compose project. Preserve the previous image and a matching database
snapshot for rollback; do not prune other images or modify other applications.
