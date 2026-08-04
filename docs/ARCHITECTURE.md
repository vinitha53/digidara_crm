# Architecture

DigiDARA CRM is a full-stack CRM with a Flask REST API and React/Vite frontend.

## Backend

- `backend/app.py` creates the Flask app, initializes extensions, registers route blueprints, and performs startup synchronization.
- `backend/models/` contains SQLAlchemy ORM models.
- `backend/routes/` contains REST API blueprints.
- `backend/services/` contains external integration logic for AI, email, WhatsApp, and Google Reviews.
- `backend/permissions.py` defines RBAC pages, actions, role aliases, and default permissions.
- `backend/schema.sql` is the MySQL Workbench schema and seed script.

## Frontend

- `frontend/src/App.jsx` defines authenticated routes.
- `frontend/src/context/AuthContext.jsx` stores JWT auth state and user permissions.
- `frontend/src/components/Layout/` contains the application shell, sidebar, and topbar.
- `frontend/src/components/UI/` contains reusable UI primitives.
- `frontend/src/pages/` contains module screens.
- `frontend/src/api/client.js` configures Axios and auth headers.

## Security Model

- Authentication uses JWT access and refresh tokens.
- Backend access is guarded by `permission_required(page, action)`.
- Frontend navigation uses the same permission keys returned from `/auth/me`.
- Staff users are scoped to assigned records in modules such as leads, customers, and tasks.

## Current Limitations

- No formal migration framework yet.
- No automated test suite yet.
- Integration secrets are stored in configuration/database fields and should be hardened before production.
- API responses are not yet standardized across all modules.
