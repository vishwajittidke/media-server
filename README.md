# Media Server

A modern, secure, self-hosted web application for uploading, organizing, and browsing photos and files.

## Project Structure
- `backend/` - FastAPI backend application
- `frontend/` - React frontend application using Vite and Tailwind CSS
- `database/` - SQLite database storage
- `uploads/` - Stored file uploads
- `thumbnails/` - Generated thumbnails
- `scripts/` - Utility scripts

## Setup and Run Instructions

### Prerequisites
- Windows 11 (or compatible OS)
- Python 3.11+
- Node.js 18+

### Backend Setup
1. Open a terminal in the root directory.
2. Activate the virtual environment: `.\backend\.venv\Scripts\activate`
3. Install dependencies (if not already done): `pip install -r backend\requirements.txt`
4. Run the setup script to create an admin user: `python scripts\setup.py`
5. Start the backend server: `cd backend` -> `uvicorn main:app --reload`
6. API is available at `http://localhost:8000/docs`

### Frontend Setup
1. Open another terminal in the root directory.
2. Change to the frontend directory: `cd frontend`
3. Install dependencies: `npm install`
4. Start the development server: `npm run dev`
5. Access the application at `http://localhost:5173`

## Status
- Initial project structure created
- Database schemas defined
- Basic Authentication completed (Login)
- Initial frontend scaffold with Tailwind CSS

## Future Roadmap (To be completed)
- Gallery View
- File Uploads
- Real-time WebSockets
- Search & Folders
