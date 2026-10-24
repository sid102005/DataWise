const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Determine project root directory (handles being in workspace root or DataWise subdir)
let projectDir = __dirname;
if (fs.existsSync(path.join(projectDir, 'DataWise', 'backend'))) {
  projectDir = path.join(projectDir, 'DataWise');
}

console.log(`\x1b[36m[DataWise]\x1b[0m Starting DataWise development environment from: ${projectDir}`);

// Determine python command
function getPythonCommand() {
  if (process.platform === 'win32') {
    return 'py';
  }
  return 'python3';
}

const pyCmd = getPythonCommand();

// 1. Start FastAPI Backend
console.log('\x1b[34m[Backend]\x1b[0m Launching FastAPI (Uvicorn) on http://127.0.0.1:8000...');
const backend = spawn(pyCmd, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1'], {
  cwd: projectDir,
  shell: true,
  stdio: ['inherit', 'pipe', 'pipe']
});

backend.stdout.on('data', (data) => {
  process.stdout.write(`\x1b[34m[Backend]\x1b[0m ${data}`);
});

backend.stderr.on('data', (data) => {
  process.stderr.write(`\x1b[33m[Backend]\x1b[0m ${data}`);
});

// 2. Start Streamlit Frontend
console.log('\x1b[35m[Frontend]\x1b[0m Launching Streamlit on http://localhost:8501...');
const frontend = spawn(pyCmd, ['-m', 'streamlit', 'run', 'frontend/app.py', '--server.port', '8501'], {
  cwd: projectDir,
  shell: true,
  stdio: ['inherit', 'pipe', 'pipe']
});

frontend.stdout.on('data', (data) => {
  process.stdout.write(`\x1b[35m[Frontend]\x1b[0m ${data}`);
});

frontend.stderr.on('data', (data) => {
  process.stderr.write(`\x1b[35m[Frontend]\x1b[0m ${data}`);
});

// Graceful shutdown
function shutdown() {
  console.log('\n\x1b[31m[DataWise]\x1b[0m Shutting down services...');
  backend.kill('SIGINT');
  frontend.kill('SIGINT');
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
