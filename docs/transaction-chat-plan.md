# Transaction chat implementation

1. Add an authenticated, read-only chat drafting endpoint using existing text-recognition provider configuration and user feature restrictions.
2. Pass bounded user/assistant history, current client-local date/time, and only the current user's visible accounts/categories to the model. Resolve names to owned IDs on the server; require missing/ambiguous fields rather than silently guessing.
3. Add one responsive chat component to desktop and mobile. Keep conversation in memory only, clear on lock/logout, present a transaction preview, and save only on an explicit confirmation through the existing validated transaction API.
4. Test request boundaries, account/category resolution, amounts, time, and transfers. Run frontend type checks/build and backend tests. Document provider setup.
5. Push a feature branch; build an image outside the VPS, back up the app, deploy only its Compose service, and verify HTTPS and existing production sites. Preserve an image/config rollback.

Scope: conversational creation of one income, expense, or transfer at a time, including follow-up corrections before saving. Editing/deleting existing transactions and analytics queries are not part of this change. No schema migration or chat-history database is needed.
