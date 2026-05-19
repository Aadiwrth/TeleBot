# Project Instructions

- **Dependencies**: Always update `requirements.txt` (or `package.json` in `/dashboard`) when adding new external imports.
- **Environment**: Use `.env` for all sensitive tokens and configuration (`BOT_TOKEN`, `ADMIN_IDS`, `DASHBOARD_API_KEY`, `SHORTNER`).
- **Admins**: Multiple admins can be added to `.env` as a comma-separated list under `ADMIN_IDS`.

## System Architecture

The project has evolved into a full-stack platform consisting of three main layers:

1. **Database Layer (SQLite)**
   - Located in `database/database.db`.
   - Uses **WAL (Write-Ahead Logging)** mode to allow concurrent reads/writes from the bot and the dashboard API without locking issues.
   - Manages Users, Redemptions, License Keys, and Point Shop Services/Inventory.

2. **Backend Services (Python/main.py)**
   - **Telegram Bot**: Handles user interactions, redemptions, and inline admin controls.
   - **FastAPI Bridge**: Runs concurrently on port `8000`. Secured via `X-API-Key` header matching `DASHBOARD_API_KEY`. Exposes database state and file upload endpoints.

3. **Frontend Dashboard (React/Vite)**
   - Located in `dashboard/`.
   - Run via `npm run dev`.
   - Provides a professional, web-based UI for managing users, license keys, Point Shop stock, bot responses, and link shortening.
   - Supports advanced drag-and-drop file uploads with visual animations.

## Core Features Implemented

*   **Robust Data Storage**: Migrated from flat JSON files to a relational SQLite database.
*   **Point Shop**: Users can redeem referral points for services (e.g., Netflix Cookies). Stock is managed as physical `.txt` files in `stock/{service}/`.
*   **Asset Management**: License keys can be associated with physical ZIP/asset files stored in `folder_code/{key}/`.
*   **Batch Key Generation**: Generate custom or bulk random keys via the dashboard.
*   **Live HTML Editor**: Modify the bot's standard response messages through the web UI.

## Planned Enhancements (Roadmap)

1.  **✅ Automated Maintenance**:
    - Background job automatically prunes expired keys and their physical files.
2.  **✅ Enhanced Analytics**:
    - Web dashboard provides real-time system metrics.
3.  **✅ Advanced Lookup System**:
    - Dashboard table filtering allows instant lookup of users and keys.
4.  **Admin Proof Verification**:
    - Add inline buttons in Telegram for admins to "Approve" or "Reject" user proof submissions.
5.  **Analytics Graphing**:
    - Implement visual charts (e.g., Recharts) in the React dashboard to track redemptions over time.