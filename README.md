# Live Room — Generic Live Q&A App

A multi-tenant version of the RR Live app. Anyone can host a live room with their own branding, private question history, and a shareable host code.

## Features
- Unique host code per room
- Private question library and usage history (only visible to that host)
- Custom branding: room name, primary color, logo URL
- Timed live questions
- Audience joins via host code or QR code
- Projector view for results
- Question types: Yes/No, scales, custom options (extendable)

## Run locally

1. Install dependencies:
   ```bash
   pip install flask flask-cors
   ```

2. Start the server:
   ```bash
   python server.py
   ```

3. Open http://localhost:8000

## Usage
- **Host**: Click "Host a room". You get a host code. Add questions, set branding, start a timer.
- **Audience**: Join with the host code or scan the QR. Answers appear on the projector.
- **Projector**: Open the projector view (or share the link) so the room can see live results.

## Deploy
This is a simple Flask app. Deploy to any Python host (Railway, Render, Fly.io, a VPS, etc.).  
For production, use a proper WSGI server (gunicorn) and a real database if you need persistence across restarts.

## Notes
- Data is stored in SQLite (`/tmp/rooms.db` in the demo). Change the path for persistent storage.
- The frontend falls back to localStorage if the API is not available.
- Extend the question types and result charts as needed.

Files:
- `index.html` — frontend
- `server.py` — backend API + static serving
