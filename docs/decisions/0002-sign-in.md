# 0002: Sign-in for the pilot, single sign-on for a real deployment

**Status:** accepted, Step 4

## Context

Every action on a case has to be tied to a named person with a role (FR-13 to FR-16, NFR-02). In a real health plan, staff already sign in through an identity provider with multi-factor authentication. Joiners, leavers and role changes are handled there, and IT security will not accept a separate password store (see the stakeholder map). A portfolio project has no identity provider to connect to.

## Decision

**For this project:**
- **Usernames and passwords.** Passwords are stored as salted scrypt hashes.
- **A signed session cookie.** It's HttpOnly, SameSite=Strict, and lasts 8 hours.
- **Lockout:** 15 minutes after 5 failed attempts.
- **A custom header** (`X-Requested-With`) is required on every cookie-authenticated request that changes something, which blocks cross-site form posts.
- **Every request re-reads the user from the database,** so deactivation takes effect at once and an old cookie can't keep an old role.
- **Services use API tokens:** the connectors (intake only) and the extraction worker (extraction only). Neither service role appears in the allowed list of any decision.
- **Queues are per person.** A nurse sees unclaimed cases and their own, a medical director sees escalated cases and the ones they decided, and an admin manages users but sees no cases. A case someone can't see answers "No such case", the same as one that doesn't exist.

**For a real deployment:**
- **Sign-in:** replace the password sign-in with the client's identity provider (OIDC or SAML), map its groups to the four roles, and keep MFA in the provider.
- **Service tokens:** issue them from a secrets manager and rotate them, instead of environment variables.

The permission checks stay exactly as they are, because they depend only on the role, not on how the person signed in.

## Consequences

- **The demo is self-contained,** and the tests prove the permission rules over HTTP, not just in functions.
- **Sessions can't be revoked one by one** before they expire, only by deactivating the user. Acceptable for a pilot. The identity provider's session controls cover it in production.
- **Demo users and a demo password exist** for local use. The service refuses to create them outside development unless `DEMO_PASSWORD` is set explicitly.
