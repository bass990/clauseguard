#!/bin/bash

# ClauseGuard startup script
# Run from Terminal: bash start.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Keep terminal open if something goes wrong
trap 'echo ""; echo "Something went wrong. Press Enter to close."; read' ERR

# Check for .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "ERROR: .env file not found."
  echo "Create it by running:"
  echo "  echo \"ANTHROPIC_API_KEY=your_key_here\" > $PROJECT_DIR/.env"
  echo ""
  echo "Press Enter to close."
  read
  exit 1
fi

# Check for Node
if ! command -v node &> /dev/null; then
  echo "ERROR: Node.js is not installed. Install it from nodejs.org"
  echo "Press Enter to close."; read
  exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
  echo "ERROR: Python 3 is not installed. Install it from python.org"
  echo "Press Enter to close."; read
  exit 1
fi

# Set up Python venv if it doesn't exist
if [ ! -d "$PROJECT_DIR/venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$PROJECT_DIR/venv"
fi

# Install Python dependencies
echo "Installing Python dependencies..."
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet

# Install Node dependencies
echo "Installing Node dependencies..."
cd "$PROJECT_DIR/frontend" && npm install --silent

echo ""
echo "----------------------------------------"
echo "  Starting ClauseGuard"
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo "----------------------------------------"
echo ""

# Start backend
cd "$PROJECT_DIR"
"$PROJECT_DIR/venv/bin/uvicorn" backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

# On Ctrl+C, kill both
trap "echo ''; echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait for both
wait $BACKEND_PID $FRONTEND_PID
