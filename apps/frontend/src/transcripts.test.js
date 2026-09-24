import test from 'node:test';
import assert from 'node:assert/strict';
import { applyUserTranscript } from './transcripts.js';

test('normalization replaces a turn and a late raw event cannot overwrite it', () => {
  const raw = { type: 'user_transcript', id: 'a', text: 'میری رپورٹ', normalized: false };
  const normalized = { ...raw, text: 'मेरी रिपोर्ट', normalized: true };
  let messages = applyUserTranscript([], raw);
  messages = applyUserTranscript(messages, normalized);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].text, normalized.text);
  assert.deepEqual(applyUserTranscript(messages, raw), messages);
  assert.deepEqual(applyUserTranscript(applyUserTranscript([], normalized), raw), messages);
});

test('repeated words in distinct turns remain separate and assistant text is untouched', () => {
  let messages = [{ id: 'assistant', role: 'assistant', text: 'Hello' }];
  for (const id of ['a', 'b']) messages = applyUserTranscript(messages,
    { type: 'user_transcript', id, text: 'Hari Sankar Prasad' });
  assert.equal(messages.length, 3);
  assert.equal(messages[0].text, 'Hello');
  assert.equal(messages[2].text, 'Hari Sankar Prasad');
  assert.deepEqual(applyUserTranscript(messages, { type: 'user_transcript' }), messages);
});
