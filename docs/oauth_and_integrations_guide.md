# OAuth & Third-Party Service Integrations Guide

This guide provides step-by-step instructions for configuring Google OAuth (Gmail & Calendar), Spotify Web API, GitHub REST API, and Web Search engines in VESPER.

---

## 1. Google OAuth 2.0 (Gmail & Google Calendar)

VESPER uses Google OAuth 2.0 Installed Application Flow (Desktop / Local Server) to interact with Gmail and Google Calendar.

### A. Google Cloud Console Setup
1. Navigate to **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Select or create your project (e.g., `vesper-507516`).
3. **Enable APIs**:
   - Go to **APIs & Services** → **Library**.
   - Search for and enable **Gmail API**.
   - Search for and enable **Google Calendar API**.
4. **Configure OAuth Consent Screen**:
   - Go to **APIs & Services** → **OAuth consent screen**.
   - User Type: **External**.
   - App Name: `VESPER Desk Companion`.
   - **Scopes**: Click **Add or Remove Scopes** and add:
     - `https://www.googleapis.com/auth/gmail.readonly` *(Read messages and threads)*
     - `https://www.googleapis.com/auth/gmail.modify` *(Modify labels, mark as read)*
     - `https://www.googleapis.com/auth/gmail.compose` *(Create drafts)*
     - `https://www.googleapis.com/auth/gmail.send` *(Send emails)*
     - `https://www.googleapis.com/auth/calendar.readonly` *(Read events)*
     - `https://www.googleapis.com/auth/calendar.events` *(Create & schedule events)*
     *(Or check `https://mail.google.com/` for full Gmail access).*
   - **Test Users**: If the app status is "Testing", add your personal Gmail address under **Test users**.
5. **Download Credentials**:
   - Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth Client ID**.
   - Application Type: **Desktop App**.
   - Name: `VESPER Desktop Client`.
   - Download the JSON client secrets file and place it at:
     ```
     backend/credentials/google_calendar_credentials.json
     ```
     *(Or `backend/credentials/gmail_credentials.json`)*

---

### B. Authorizing Gmail (`scripts/auth_gmail.py`)
Run the dedicated authorization script:
```bash
.venv/bin/python3 scripts/auth_gmail.py
```
- Launches a local browser session at `http://localhost:8080`.
- Upon sign-in and consent, saves the authorized token with refresh capabilities to:
  ```
  backend/credentials/gmail_token.json
  ```
- Tests live connection by printing profile info and recent email headers.

---

### C. Authorizing Google Calendar (`scripts/auth_google_calendar.py`)
Run the calendar authorization script:
```bash
.venv/bin/python3 scripts/auth_google_calendar.py
```
- Saves token to:
  ```
  backend/credentials/google_calendar_token.json
  ```
- Verifies live retrieval by fetching upcoming calendar events.

---

### D. Offline Sandbox Fallback
If credentials or tokens are unconfigured, VESPER does **not crash**. Both `EmailSpecialist` and `TaskSpecialist` automatically fail over to the offline sandbox:
- `EmailSpecialist`: Interacts with preloaded sandbox messages (`msg_001` from Rohit Kumar, GitHub notifications, invoices) and captures drafts into `_sandbox_outbox`.
- `TaskSpecialist`: Uses local SQLite/memory tasks and mock calendar entries.

---

## 2. Spotify Web API (Music Playback & Device Transfer)

Implemented in [`backend/agent/specialists/media_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/media_specialist.py).

### Configuration (`.env`)
```bash
SPOTIPY_CLIENT_ID="your_spotify_client_id"
SPOTIPY_CLIENT_SECRET="your_spotify_client_secret"
SPOTIPY_REDIRECT_URI="http://localhost:8888/callback"
```

### Authorization
- On first playback action, `spotipy.oauth2.SpotifyOAuth` launches a browser consent window with scopes:
  - `user-read-playback-state`
  - `user-modify-playback-state`
  - `user-read-currently-playing`
  - `playlist-read-private`
- Caches credentials to:
  ```
  backend/credentials/.spotify_cache
  ```

### Multi-Device Switching
VESPER can query and switch active playback devices (*"play music on my phone"*, *"switch to desktop speakers"*):
- **`get_available_devices`**: Lists connected Spotify Connect devices with names, IDs, types, and active states.
- **`transfer_playback`**: Seamlessly transfers audio playback to the requested device name.

---

## 3. GitHub REST API (Code & Repository Navigation)

Implemented in [`backend/agent/specialists/github_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/github_specialist.py).

### Configuration (`.env`)
```bash
GITHUB_TOKEN="ghp_yourPersonalAccessToken"
```

### Capabilities
- **Authenticated Mode**: 5,000 requests/hr rate limit. Allows inspecting private and organization repositories.
- **Anonymous Mode**: Falls back to public GitHub API v3 (60 requests/hr limit).
- **Features**:
  - `get_repo_info`: Stars, forks, language breakdown, branch info.
  - `search_code`: Code symbols and keywords.
  - `get_code_snippet`: Line range slicing with syntax formatting.
  - `solve_doubt`: Context-grounded architectural guidance.
  - `list_issues`: Open and closed issues.
  - `get_recent_commits`: Commit histories and timestamps.

---

## 4. Web Search & Research Services

Implemented in [`backend/agent/specialists/research_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/research_specialist.py).

### Configuration (`.env`)
```bash
TAVILY_API_KEY="tvly-yourApiKey"
# Optional SerpAPI fallback:
SERPAPI_API_KEY="yourSerpApiKey"
```

### Features
- **Depth Normalization**: Automatically normalizes search depth to `"basic"` or `"advanced"` to ensure compliance with Tavily v1 specifications.
- **Snippet Formatting**: Returns verified source snippets (`[Title]: Snippet text...`) and direct answer strings directly into Alfred's reasoning loop for zero-hallucination factual reporting.
