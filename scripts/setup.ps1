# LIPLAB Setup Script for Windows (PowerShell)

Write-Host "🚀 LIPLAB Setup Script" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python is not installed. Please install Python 3.11+ first." -ForegroundColor Red
    exit 1
}

$pythonVersion = python --version
Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green

# Check if Node.js is installed
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js is not installed. Please install Node.js 18+ first." -ForegroundColor Red
    exit 1
}

$nodeVersion = node --version
Write-Host "✅ Node.js found: $nodeVersion" -ForegroundColor Green
Write-Host ""

# Setup environment variables
if (-not (Test-Path .env)) {
    Write-Host "📝 Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "⚠️  Please edit .env and add your ANTHROPIC_API_KEY" -ForegroundColor Yellow
    Write-Host ""
}

# Setup backend
Write-Host "🔧 Setting up backend..." -ForegroundColor Cyan
Set-Location backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Set-Location ..
Write-Host "✅ Backend setup complete" -ForegroundColor Green
Write-Host ""

# Setup frontend
Write-Host "🎨 Setting up frontend..." -ForegroundColor Cyan
Set-Location frontend
npm install
Write-Host "✅ Frontend setup complete" -ForegroundColor Green
Write-Host ""

# Generate viseme placeholders
Write-Host "🖼️  Generating viseme placeholder images..." -ForegroundColor Cyan
Set-Location public\visemes
if (Get-Command python -ErrorAction SilentlyContinue) {
    python generate_placeholders.py 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  Placeholder generation failed (optional)" -ForegroundColor Yellow
    }
}
Set-Location ..\..\..\

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env and add your ANTHROPIC_API_KEY"
Write-Host "2. Start backend: cd backend; .\venv\Scripts\Activate.ps1; python -m uvicorn main:app --reload"
Write-Host "3. Start frontend (new terminal): cd frontend; npm run dev"
Write-Host ""
Write-Host "Or use Docker:"
Write-Host "  docker-compose up --build"
Write-Host ""
Write-Host "Happy coding! 🎉" -ForegroundColor Cyan
