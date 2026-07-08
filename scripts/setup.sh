#!/bin/bash
# LIPLAB Setup Script for Unix-based systems (macOS, Linux)

set -e

echo "🚀 LIPLAB Setup Script"
echo "====================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11+ first."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js found: $(node --version)"
echo ""

# Setup environment variables
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your ANTHROPIC_API_KEY"
    echo ""
fi

# Setup backend
echo "🔧 Setting up backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cd ..
echo "✅ Backend setup complete"
echo ""

# Setup frontend
echo "🎨 Setting up frontend..."
cd frontend
npm install
echo "✅ Frontend setup complete"
echo ""

# Generate viseme placeholders
echo "🖼️  Generating viseme placeholder images..."
cd public/visemes
if command -v python3 &> /dev/null; then
    python3 generate_placeholders.py || echo "⚠️  Placeholder generation failed (optional)"
fi
cd ../../..
echo ""

# Summary
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your ANTHROPIC_API_KEY"
echo "2. Start backend: cd backend && source venv/bin/activate && python -m uvicorn main:app --reload"
echo "3. Start frontend (new terminal): cd frontend && npm run dev"
echo ""
echo "Or use Docker:"
echo "  docker-compose up --build"
echo ""
echo "Happy coding! 🎉"
