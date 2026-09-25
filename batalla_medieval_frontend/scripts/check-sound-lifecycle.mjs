import assert from 'node:assert/strict';

class MemoryStorage {
  constructor(initial = {}) { this.values = new Map(Object.entries(initial)); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

class FakeAudioParam {
  constructor(value = 1) { this.value = value; }
  cancelScheduledValues() {}
  setValueAtTime(value) { this.value = value; }
  exponentialRampToValueAtTime(value) { this.value = value; }
}

class FakeGainNode {
  constructor() { this.gain = new FakeAudioParam(); }
  connect() {}
  disconnect() {}
}

class FakeOscillator {
  constructor(context) {
    this.context = context;
    this.frequency = new FakeAudioParam();
    this.stopCalls = [];
    this.listeners = new Map();
  }
  connect() {}
  disconnect() {}
  start(time) { this.startTime = time; }
  stop(time) {
    this.stopCalls.push(time);
    if (time <= this.context.currentTime) {
      queueMicrotask(() => this.listeners.get('ended')?.());
    }
  }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
}

class FakeAudioContext {
  constructor() {
    this.state = 'suspended';
    this.currentTime = 10;
    this.destination = {};
    this.oscillators = [];
    this.suspendCalls = 0;
  }
  createGain() { return new FakeGainNode(); }
  createOscillator() {
    const oscillator = new FakeOscillator(this);
    this.oscillators.push(oscillator);
    return oscillator;
  }
  async resume() { this.state = 'running'; }
  async suspend() { this.state = 'suspended'; this.suspendCalls += 1; }
}

globalThis.localStorage = new MemoryStorage({
  bm_sound_settings: JSON.stringify({
    musicEnabled: 'corrupt',
    sfxEnabled: null,
    musicVolume: 'not-a-number',
    sfxVolume: 9,
  }),
});
globalThis.window = { AudioContext: FakeAudioContext };

const { SoundManager } = await import('../src/services/sound.js');
const manager = new SoundManager();
const normalized = manager.getSettings();
assert.equal(normalized.musicEnabled, false, 'invalid music toggle must fall back to opt-in default');
assert.equal(normalized.sfxEnabled, true, 'invalid SFX toggle must fall back to default');
assert.equal(normalized.musicVolume, 0.45, 'invalid music volume must fall back to default');
assert.equal(normalized.sfxVolume, 1, 'out-of-range SFX volume must clamp to 1');

manager.playMusic('calm_medieval');
manager.setMusicEnabled(true);
await manager.unlock();
await new Promise((resolve) => setTimeout(resolve, 0));
const context = manager.audioContext;
assert.equal(context.state, 'running', 'audio context must run after explicit unlock');
assert.ok(context.oscillators.length > 0, 'music must schedule a tone after opt-in + unlock');

const calmVoices = [...context.oscillators];
manager.playMusic('war_drums');
for (const oscillator of calmVoices) {
  assert.ok(
    oscillator.stopCalls.some((time) => time <= context.currentTime),
    'switching music must stop every active voice from the previous pattern immediately',
  );
}

const beforeMute = [...context.oscillators];
manager.setMusicEnabled(false);
assert.equal(manager.musicGain.gain.value, 0, 'music master gain must mute immediately');
for (const oscillator of beforeMute) {
  if (oscillator.stopCalls.length > 1) continue;
  assert.ok(
    oscillator.stopCalls.some((time) => time <= context.currentTime),
    'disabling music must stop active music voices immediately',
  );
}

const countBeforeRepeatedUnlock = context.oscillators.length;
await manager.unlock();
await manager.unlock();
assert.equal(
  context.oscillators.length,
  countBeforeRepeatedUnlock,
  'repeated unlock calls must not restart music while disabled',
);

await manager.deactivate();
assert.equal(context.state, 'suspended', 'deactivating a session must suspend the AudioContext');
assert.equal(manager.unlocked, false, 'deactivating a session must clear unlocked state');
assert.ok(context.suspendCalls >= 1, 'deactivation must release running audio resources');

console.log('BM-0082 sound lifecycle passed: preferences normalized, voices stop cleanly, unlock is idempotent, and session audio suspends');
