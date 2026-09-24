import test from 'node:test';
import assert from 'node:assert/strict';
import { careTransition as next, careTitle, carePrompt, initialCare, doctors, channelFor, isCareIntent } from './doctorConnect.js';

test('touch-first booking has three steps, preserves edits, and still needs review', () => {
  let s = next(initialCare(), { type: 'open' });
  s = next(s, { type: 'select_touch', id: 'demo-2' });
  assert.equal(s.stage, 'date');
  s = next(s, { type: 'set_date', value: '2026-10-01' });
  assert.equal(s.stage, 'time');
  s = next(s, { type: 'set_time', value: '10:30' });
  assert.equal(s.stage, 'patient');
  assert.equal(next(s, { type: 'set_patient_touch', value: ' ' }).stage, 'patient');
  s = next(s, { type: 'set_patient_touch', value: 'Hari Sankar Prasad' });
  assert.equal(s.stage, 'review');
  let back = next(s, { type: 'back' });
  assert.equal(back.stage, 'patient');
  assert.equal(back.patient, 'Hari Sankar Prasad');
  back = next(back, { type: 'back' });
  assert.equal(back.stage, 'time');
  assert.equal(back.time, '10:30');
  assert.equal(next(back, { type: 'back' }).date, '2026-10-01');
  assert.equal(next(s, { type: 'yes' }).stage, 'handoff');
});

test('touch appointment controls advance the same demo state as voice replies', () => {
  let state = next(initialCare(), { type: 'select', id: 'demo-1' });
  state = next(state, { type: 'yes' });
  state = next(state, { type: 'set_date', value: '2026-10-01' });
  state = next(state, { type: 'set_time', value: '10:00' });
  state = next(state, { type: 'set_patient', value: 'Demo' });
  assert.equal(state.stage, 'patient_confirm');
  state = next(state, { type: 'yes' });
  assert.equal(state.stage, 'review');
  assert.equal(next(state, { type: 'yes' }).stage, 'handoff');
});

test('HERE results are recognised as real listings in the voice-driven panel', () => {
  const here = { ...initialCare(), stage: 'search', revision: 1, source: 'here',
    doctors: [{ id: 'real-1', name: 'Hospital', clinic: 'Address' }] };
  const state = next(initialCare(), { type: 'server', state: here });
  assert.match(carePrompt(state), /Real listings/);
  assert.equal(next(state, { type: 'server', state: { ...here, stage: 'confirm', revision: 2, selected: 'real-1' } }).selected, 'real-1');
});

test('name confirmation accepts server state and offers correction without losing date/time', () => {
  const incoming = { ...initialCare(), stage: 'patient_confirm', revision: 5, selected: 'demo-1',
    patient: 'Hari Sankar Prasad', date: 'Tomorrow', time: '10:00' };
  const state = next(initialCare(), { type: 'server', state: incoming });
  assert.match(carePrompt(state), /Hari Sankar Prasad/);
  const edit = next(state, { type: 'edit_patient' });
  assert.equal(edit.stage, 'patient');
  assert.equal(edit.time, '10:00');
  assert.equal(next(state, { type: 'yes' }).stage, 'review');
});

test('server selections use real result IDs without altering dummy fallback', () => {
  const real = { ...initialCare(), stage: 'confirm', revision: 2, source: 'google',
    selected: 'real-1', doctors: [{ id: 'real-1', name: 'Example Hospital', clinic: 'Example Road' }] };
  assert.equal(next(initialCare(), { type: 'server', state: real }).selected, 'real-1');
  assert.equal(next(initialCare(), { type: 'server', state: { ...real, selected: 'unknown' } }).stage, 'closed');
  assert.equal(doctors[0].id, 'demo-1');
});

test('care stays hidden during normal conversation and each booking stage has its own screen', () => {
  const state = initialCare();
  assert.equal(state.stage, 'closed');
  assert.equal(next(state, { type: 'reply', text: 'Please explain my report' }), state);
  assert.equal(next(state, { type: 'reply', text: 'Thank you for the summary' }), state);
  assert.equal(careTitle('search'), 'Choose a doctor');
  assert.equal(careTitle('date'), 'Choose a date');
  assert.equal(careTitle('review'), 'Review your request');
});

test('live server updates open the panel and old revisions cannot overwrite it', () => {
  const live = { ...initialCare(), stage: 'search', revision: 3 };
  const state = next(initialCare(), { type: 'server', state: live });
  assert.equal(state.stage, 'search');
  assert.equal(next(state, { type: 'server', state: { ...live, stage: 'closed', revision: 2 } }), state);
  assert.equal(next(state, { type: 'server', state: { ...live, selected: 'unknown' } }), state);
});

test('doctor intent recognises several phrases but not ordinary report questions', () => {
  for (const q of ['Connect me to a doctor', 'I want to see a doctor', 'find a clinic nearby', 'डॉक्टर चाहिए', 'డాక్టర్ కావాలి']) assert.ok(isCareIntent(q));
  assert.equal(isCareIntent('Explain my hemoglobin'), false);
});
test('request automatically opens results and touch and speech transcript agree', () => {
  const s = next(initialCare(), { type: 'reply', text: 'find a doctor near me' });
  assert.equal(s.stage, 'search');
  assert.deepEqual(next(s, { type: 'reply', text: 'Book the second doctor' }), next(s, { type: 'select', id: 'demo-2' }));
});
test('appointment requires confirmation, all fields and final approval', () => {
  let s = next(initialCare(), { type: 'select', id: 'demo-1' });
  assert.equal(s.stage, 'confirm');
  for (const [text, stage] of [['yes', 'date'], ['Tomorrow', 'time'], ['10 am', 'patient'], ['Demo User', 'patient_confirm'], ['yes', 'review']]) {
    s = next(s, { type: 'reply', text }); assert.equal(s.stage, stage);
  }
  assert.equal(next(s, { type: 'reply', text: 'maybe' }).stage, 'review');
  assert.equal(next(s, { type: 'reply', text: 'yes' }).stage, 'handoff');
  assert.equal(next(s, { type: 'edit' }).patient, 'Demo User');
  assert.equal(next(s, { type: 'close' }).patient, '');
});
test('fallback order and no actionable contacts in fictional data', () => {
  assert.deepEqual(doctors.map(channelFor), ['WhatsApp', 'Phone', 'Appointment page']);
  assert.equal(channelFor({}), null);
  assert.ok(!JSON.stringify(doctors).includes('https:'));
});
test('invalid selection and empty replies do not advance', () => {
  const s = next(initialCare(), { type: 'open' });
  assert.equal(next(s, { type: 'select', id: 'unknown' }).stage, 'search');
  assert.equal(next(s, { type: 'reply', text: 'fourth doctor' }).stage, 'search');
  assert.equal(next(s, { type: 'reply', text: '' }), s);
});
