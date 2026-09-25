export async function request(path, body, { baseUrl = '', timeoutMs = 85000 } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(baseUrl + path, {
      signal: controller.signal,
      ...(body === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error('The server returned an unreadable response. Please try again.'); }
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed. Please try again.');
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('The request took too long. Please try again.');
    if (error instanceof TypeError) throw new Error('Cannot reach MediVoice. Check your connection and try again.');
    throw error;
  } finally { clearTimeout(timeout); }
}

export async function uploadReport(path, file, { baseUrl = '', timeoutMs = 130000 } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(baseUrl + path, { method: 'POST', body: form, signal: controller.signal });
    let data;
    try { data = await response.json(); }
    catch { throw new Error('The server returned an unreadable response. Please try again.'); }
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Report processing failed. Please try again.');
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Report processing is taking longer than expected. Please try again.');
    if (error instanceof TypeError) throw new Error('Cannot reach MediVoice. Check your connection and try again.');
    throw error;
  } finally { clearTimeout(timeout); }
}
