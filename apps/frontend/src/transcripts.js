// Committed user turns come from the worker, keyed by ChatMessage id.
// LiveKit STT segment ids are different and must not create duplicate bubbles.
export function applyUserTranscript(messages, event) {
  if (event.type !== 'user_transcript' || typeof event.id !== 'string' ||
      typeof event.text !== 'string' || !event.text.trim()) return messages;
  const id = `user:${event.id}`;
  const index = messages.findIndex(message => message.id === id);
  if (index >= 0 && messages[index].normalized && !event.normalized) return messages;
  const item = { id, role: 'user', text: event.text, final: true,
    normalized: event.normalized === true };
  const next = [...messages];
  if (index >= 0) next[index] = item; else next.push(item);
  return next.slice(-100);
}
