import test from 'node:test';
import assert from 'node:assert/strict';
import { voiceActivity, initialActivity } from './voiceActivity.js';

test('generic thinking never claims to read the report', () => {
  assert.equal(voiceActivity(initialActivity, { type: 'agent_state', state: 'thinking' }).text, 'Preparing your answer…');
  assert.equal(voiceActivity(initialActivity, { type: 'stage', stage: 'medical', status: 'working' }).text, 'Checking your report…');
});
test('doctor activity survives thinking and translation events', () => {
  let state = voiceActivity(initialActivity, { type: 'stage', stage: 'doctor_search', status: 'working' });
  state = voiceActivity(state, { type: 'agent_state', state: 'thinking' });
  state = voiceActivity(state, { type: 'stage', stage: 'translate_out', status: 'working' });
  assert.equal(state.text, 'Finding doctor options…');
  assert.equal(state.motion, 'thinking');
  state = voiceActivity(state, { type: 'agent_state', state: 'speaking' });
  assert.equal(state.text, 'Speaking…');
  assert.equal(state.task, null);
  state = voiceActivity(state, { type: 'agent_state', state: 'listening' });
  assert.equal(state.motion, 'listening');
});
test('errors and disconnects stop the animation', () => {
  const state = voiceActivity(initialActivity, { type: 'stage', stage: 'appointment', status: 'working' });
  assert.equal(state.text, 'Preparing your appointment request…');
  assert.equal(voiceActivity(state, { type: 'error' }).motion, 'idle');
  assert.deepEqual(voiceActivity(state, { type: 'reset' }), initialActivity);
});
