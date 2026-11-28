import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const expected = process.env.G8_EXPECTED_HEAD || '';
assert.match(expected, /^[a-f0-9]{40}$/, 'Set G8_EXPECTED_HEAD to the full commit SHA');
assert.ok(process.env.G8_PYTHON?.startsWith('/'), 'Set G8_PYTHON to the absolute path of a prepared Python interpreter');
assert.ok(process.env.G8_PLAYWRIGHT_MODULE?.startsWith('/'), 'Set G8_PLAYWRIGHT_MODULE to the absolute path of @playwright/test/index.js');

function command(program, args, options = {}) {
  const result = spawnSync(program, args, { cwd: root, encoding: 'utf8', ...options });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, `${program} ${args.join(' ')} failed: ${result.stderr || result.stdout}`);
  return (result.stdout || '').trim();
}

assert.equal(command('git', ['rev-parse', 'HEAD']), expected, 'Unexpected HEAD');
assert.equal(command('git', ['status', '--porcelain', '--untracked-files=all']), '', 'Checkout must be clean');
assert.equal(command('git', ['rev-parse', '--show-toplevel']), root);

const scratch = await mkdtemp('/tmp/medievol-journey-g8-');
const children = [];
const groups = new Set();
let interrupted = false;
let escalation;
function signalGroup(pid, signal) {
  try { process.kill(-pid, signal); } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
}
const stop = () => {
  interrupted = true;
  for (const pid of groups) signalGroup(pid, 'SIGTERM');
  escalation ||= setTimeout(() => {
    for (const pid of groups) signalGroup(pid, 'SIGKILL');
  }, 5000);
};
process.once('SIGINT', stop);
process.once('SIGTERM', stop);

async function port() {
  return await new Promise((resolvePort, reject) => {
    const server = createServer();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const value = server.address().port;
      server.close((error) => error ? reject(error) : resolvePort(value));
    });
  });
}

function track(child) {
  const done = new Promise((resolveClose) => child.once('close', () => {
    if (child.pid) {
      try { process.kill(-child.pid, 0); } catch (error) {
        if (error.code === 'ESRCH') groups.delete(child.pid);
        else throw error;
      }
    }
    resolveClose();
  }));
  children.push(done);
  if (child.pid) groups.add(child.pid);
}

async function run(program, args, options) {
  assert.ok(!interrupted, 'Interrupted');
  await new Promise((resolveRun, reject) => {
    const child = spawn(program, args, { ...options, detached: true, stdio: 'inherit' });
    track(child);
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      if (code === 0 && !interrupted) resolveRun();
      else reject(new Error(`${program} failed: ${signal || code}`));
    });
  });
}

function start(program, args, cwd, env, marker) {
  return new Promise((resolveStart, reject) => {
    const child = spawn(program, args, { cwd, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    track(child);
    let output = '';
    let ready = false;
    const timer = setTimeout(() => reject(new Error(`${program} did not announce startup: ${output.slice(-2000)}`)), 30000);
    const onData = (chunk) => {
      const text = chunk.toString();
      process.stdout.write(text);
      output += text;
      if (!ready && output.includes(marker)) {
        ready = true;
        clearTimeout(timer);
        resolveStart(child);
      }
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', onData);
    child.on('error', (error) => { clearTimeout(timer); if (!ready) reject(error); });
    child.on('exit', (code) => {
      clearTimeout(timer);
      if (!ready) reject(new Error(`${program} exited ${code}: ${output.slice(-2000)}`));
    });
  });
}

try {
  const archive = spawnSync('git', ['archive', '--format=tar', expected], { cwd: root, maxBuffer: 128 * 1024 * 1024 });
  assert.equal(archive.status, 0, 'git archive failed');
  const unpack = spawnSync('tar', ['-xf', '-', '-C', scratch], { input: archive.stdout });
  assert.equal(unpack.status, 0, 'git archive extraction failed');
  assert.equal(command('git', ['rev-parse', 'HEAD']), expected);
  assert.equal(command('git', ['status', '--porcelain', '--untracked-files=all']), '', 'Checkout changed while archiving');
  const lock = await readFile(join(scratch, 'batalla_medieval_frontend/package-lock.json'));
  console.log(`G8_HEAD=${expected} FRONTEND_LOCK_SHA256=${createHash('sha256').update(lock).digest('hex')}`);

  const apiPort = await port();
  let uiPort = await port();
  while (uiPort === apiPort) uiPort = await port();
  const api = `http://127.0.0.1:${apiPort}`;
  const ui = `http://127.0.0.1:${uiPort}`;
  const env = {
    PATH: process.env.PATH, HOME: process.env.HOME, LANG: 'C.UTF-8',
    ...(process.env.NODE_EXTRA_CA_CERTS ? { NODE_EXTRA_CA_CERTS: process.env.NODE_EXTRA_CA_CERTS } : {}),
    PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || join(process.env.HOME, '.cache/ms-playwright'),
    G8_PLAYWRIGHT_MODULE: process.env.G8_PLAYWRIGHT_MODULE,
    G8_REQUIRE_ALL: '1',
    APP_ENV: 'test', PARALLEL_JOURNEY_ALLOW_MUTATIONS: 'isolated',
    PYTHONPATH: join(scratch, 'batalla_medieval_backend'), PYTHONDONTWRITEBYTECODE: '1',
    PARALLEL_JOURNEY_PYTHON: process.env.G8_PYTHON,
    PARALLEL_JOURNEY_DB: join(scratch, 'fixture.db'),
    DATABASE_URL: `sqlite:///${join(scratch, 'fixture.db')}`,
    VITE_API_URL: api, VITE_SOCKET_URL: api, E2E_BASE_URL: ui,
    CORS_ORIGINS: ui, FRONTEND_URL: ui, SECRET_KEY: randomBytes(32).toString('hex'),
  };
  const frontend = join(scratch, 'batalla_medieval_frontend');
  const python = process.env.G8_PYTHON;
  console.log(`Node ${process.version}; Python ${command(python, ['--version'])}`);
  await run('npm', ['ci', '--no-audit', '--no-fund'], { cwd: frontend, env });
  await run(python, ['-m', 'alembic', '-c', join(scratch, 'batalla_medieval_backend/alembic.ini'), 'upgrade', 'head'], { cwd: scratch, env });
  await run(python, ['-m', 'app.seed'], { cwd: scratch, env });
  for (const fixture of ['g2', 'g14', 'g13']) {
    const script = fixture === 'g2' ? 'prepare_g2_e2e.py' : fixture === 'g14' ? 'prepare_g14_community_e2e.py' : 'prepare_g13_hero_e2e.py';
    await run(python, [join(scratch, 'scripts', script)], { cwd: scratch, env });
  }
  await run('npm', ['run', 'build'], { cwd: frontend, env });
  const backend = await start(python, ['-m', 'uvicorn', 'app.main:socket_app', '--app-dir', join(scratch, 'batalla_medieval_backend'), '--host', '127.0.0.1', '--port', String(apiPort)], scratch, env, `Uvicorn running on ${api}`);
  const preview = await start(process.execPath, [join(frontend, 'node_modules/vite/bin/vite.js'), 'preview', '--host', '127.0.0.1', '--port', String(uiPort), '--strictPort'], frontend, env, `${ui}/`);
  const running = (child) => child.exitCode === null && child.signalCode === null;
  assert.ok([backend, preview].every(running), 'A test service exited before the matrix');
  await run(process.execPath, [join(frontend, 'e2e/parallel-g8-browser.mjs')], { cwd: frontend, env });
  assert.ok([backend, preview].every(running), 'A test service exited during the matrix');
  assert.ok(!interrupted, 'Interrupted');
} finally {
  stop();
  await Promise.all(children);
  await new Promise((resolveDrain) => {
    const deadline = Date.now() + 5000;
    const check = () => {
      for (const pid of groups) {
        try { process.kill(-pid, 0); } catch (error) {
          if (error.code === 'ESRCH') groups.delete(pid);
          else throw error;
        }
      }
      if (!groups.size || Date.now() >= deadline) return resolveDrain();
      setTimeout(check, 50);
    };
    check();
  });
  for (const pid of groups) signalGroup(pid, 'SIGKILL');
  clearTimeout(escalation);
  await rm(scratch, { recursive: true, force: true });
  process.removeListener('SIGINT', stop);
  process.removeListener('SIGTERM', stop);
}
