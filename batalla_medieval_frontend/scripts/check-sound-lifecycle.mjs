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
  static deferResume = false;
  static deferSuspend = false;
  static resumeResolvers = [];
  static suspendResolvers = [];

  static releasePendingResumes() {
    const resolvers = [...FakeAudioContext.resumeResolvers];
    FakeAudioContext.resumeResolvers.length = 0;
    for (const resolve of resolvers) resolve();
  }

  static releasePendingSuspends() {
    const resolvers = [...FakeAudioContext.suspendResolvers];
    FakeAudioContext.suspendResolvers.length = 0;
    for (const resolve of resolvers) resolve();
  }

  static resetDeferrals() {
    FakeAudioContext.deferResume = false;
    FakeAudioContext.deferSuspend = false;
    FakeAudioContext.resumeResolvers.length = 0;
    FakeAudioContext.suspendResolvers.length = 0;
  }

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
  async resume() {
    if (FakeAudioContext.deferResume) {
      await new Promise((resolve) => FakeAudioContext.resumeResolvers.push(resolve));
    }
    this.state = 'running';
  }
  async suspend() {
    this.suspendCalls += 1;
    if (FakeAudioContext.deferSuspend) {
      await new Promise((resolve) => FakeAudioContext.suspendResolvers.push(resolve));
    }
    this.state = 'suspended';
  }
}

const nextTurn = () => new Promise((resolve) => setTimeout(resolve, 0));

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
await nextTurn();
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

// Logout must invalidate an unlock that is still waiting for resume().
FakeAudioContext.resetDeferrals();
FakeAudioContext.deferResume = true;
const raceManager = new SoundManager();
const pendingUnlock = raceManager.unlock();
await nextTurn();
const raceContext = raceManager.audioContext;
assert.equal(raceContext.state, 'suspended', 'deferred unlock must still be pending before logout');

const pendingDeactivate = raceManager.deactivate();
assert.equal(raceManager.unlocked, false, 'logout must invalidate an in-flight unlock immediately');
FakeAudioContext.releasePendingResumes();
const staleUnlockResult = await pendingUnlock;
FakeAudioContext.deferResume = false;
await pendingDeactivate;

assert.equal(staleUnlockResult, false, 'an unlock started before logout must not become valid afterward');
assert.equal(raceManager.unlocked, false, 'stale unlock completion must not reactivate the session');
assert.equal(raceContext.state, 'suspended', 'logout must suspend a context resumed by a stale unlock');
assert.ok(raceContext.suspendCalls >= 1, 'logout must release the AudioContext after stale resume');
assert.equal(raceContext.oscillators.length, 0, 'stale unlock must not emit post-logout audio');

// A playSFX callback queued before logout must also become stale and emit no tone.
FakeAudioContext.resetDeferrals();
FakeAudioContext.deferResume = true;
const sfxRaceManager = new SoundManager();
sfxRaceManager.playSFX('click_ui');
await nextTurn();
const sfxRaceContext = sfxRaceManager.audioContext;
const sfxDeactivate = sfxRaceManager.deactivate();
FakeAudioContext.releasePendingResumes();
FakeAudioContext.deferResume = false;
await sfxDeactivate;
await nextTurn();
assert.equal(sfxRaceContext.state, 'suspended', 'logout during SFX unlock must leave the context suspended');
assert.equal(sfxRaceContext.oscillators.length, 0, 'pre-logout SFX must not emit after session deactivation');

// Regression for logout -> immediate reactivation. The old unlock resumes first,
// logout then owns a deferred suspension, and the new unlock must wait behind it
// so that no stale suspend can finish after the current session is unlocked.
FakeAudioContext.resetDeferrals();
FakeAudioContext.deferResume = true;
FakeAudioContext.deferSuspend = true;
const reactivationManager = new SoundManager();
const oldUnlock = reactivationManager.unlock();
await nextTurn();
const reactivationContext = reactivationManager.audioContext;
const logoutTransition = reactivationManager.deactivate();
const currentUnlock = reactivationManager.unlock();
let currentUnlockSettled = false;
void currentUnlock.finally(() => { currentUnlockSettled = true; });

FakeAudioContext.releasePendingResumes();
const oldUnlockResult = await oldUnlock;
await nextTurn();
assert.equal(oldUnlockResult, false, 'pre-logout unlock must be stale after generation changes');
assert.equal(currentUnlockSettled, false, 'new unlock must wait until the queued logout suspension completes');
assert.equal(FakeAudioContext.suspendResolvers.length, 1, 'logout suspension must own the transition before reactivation');

FakeAudioContext.deferResume = false;
FakeAudioContext.deferSuspend = false;
FakeAudioContext.releasePendingSuspends();
await logoutTransition;
const currentUnlockResult = await currentUnlock;

assert.equal(currentUnlockResult, true, 'reactivation unlock must succeed after logout suspension');
assert.equal(reactivationManager.unlocked, true, 'manager must reflect the current reactivated session');
assert.equal(reactivationContext.state, 'running', 'stale suspension must not clobber the reactivated AudioContext');

await reactivationManager.deactivate();
FakeAudioContext.resetDeferrals();

console.log('BM-0082 sound lifecycle passed: preferences normalized, active voices stop cleanly, audio transitions serialize, stale unlock/SFX callbacks are invalidated, and logout cannot clobber reactivation');
