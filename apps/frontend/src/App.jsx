import { useEffect, useReducer, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';
import { Camera, CheckCircle, Clock3, FileText, Menu, MessageCircle, Mic, PhoneOff, Send, ShieldCheck, Stethoscope, Upload, X } from 'lucide-react';
import { request as apiRequest, uploadReport } from './api';
import DoctorConnect from './DoctorConnect.jsx';
import VoiceActivity from './VoiceActivity.jsx';
import { voiceActivity, initialActivity } from './voiceActivity';
import { careTransition, initialCare, isCareIntent } from './doctorConnect';
import { applyUserTranscript } from './transcripts';

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

const request = (path, body) => apiRequest(path, body, {
  baseUrl: API, timeoutMs: path.endsWith('/message') ? 85000 : 15000,
});

export default function App() {
  const [activity, activityDispatch] = useReducer(voiceActivity, initialActivity);
  const [care, careDispatch] = useReducer(careTransition, undefined, initialCare);
  const [careBusy, setCareBusy] = useState(false);
  const careTimer = useRef(null);
  const [health, setHealth] = useState(null);
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState('Ready when you are');
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([]);
  const [timings, setTimings] = useState({});
  const [language, setLanguage] = useState('Auto-detect');
  const [text, setText] = useState('');
  const [textBusy, setTextBusy] = useState(false);
  const [reportFile, setReportFile] = useState(null);
  const [reportState, setReportState] = useState('empty');
  const [reportPreview, setReportPreview] = useState('');
  const [reportSummary, setReportSummary] = useState(null);
  const [fileError, setFileError] = useState('');
  const photoInput = useRef(null);
  const fileInput = useRef(null);
  const roomRef = useRef(null);
  const disconnectReason = useRef('');
  const generation = useRef(0);
  const workerTimer = useRef(null);
  const audioHost = useRef(null);
  const bottom = useRef(null);
  const conversationDialog = useRef(null);
  const reportDialog = useRef(null);
  const appShell = useRef(null);

  useEffect(() => {
    if (reportState !== 'empty') appShell.current?.scrollTo({ top: 0 });
  }, [reportState]);

  useEffect(() => {
    request('/health').then(setHealth).catch(() => setStatus('Live voice offline. Start the backend to connect.'));
    return () => { generation.current++; clearTimeout(workerTimer.current); clearTimeout(careTimer.current); roomRef.current?.disconnect(); };
  }, []);
  useEffect(() => {
    const container = bottom.current?.parentElement;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages]);
  useEffect(() => {
    if (!reportFile || !reportFile.type.startsWith('image/')) { setReportPreview(''); return; }
    const url = URL.createObjectURL(reportFile);
    setReportPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [reportFile]);
  async function chooseReport(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(file.type)) {
      setFileError('Please choose a JPG, PNG, WebP image or PDF.'); return;
    }
    if (file.size > 10 * 1024 * 1024) { setFileError('Please choose a file smaller than 10 MB.'); return; }
    setFileError(''); setError(''); setReportFile(file); setReportSummary(null); setSession(null); setReportState('processing');
    setStatus('Uploading and reading your report…');
    try {
      const created = await uploadReport('/api/reports', file, { baseUrl: API });
      setSession(created); setReportSummary(created.report_summary); setReportState('ready');
      setStatus('Your report is ready. Let’s talk.');
    } catch (err) {
      setReportState('empty'); setReportFile(null); setReportSummary(null); setFileError(err.message);
      setStatus('Choose a report to try again.');
    }
  }

  async function trySampleReport() {
    setFileError(''); setError(''); setReportFile(null); setReportSummary(null); setReportState('processing');
    setStatus('Preparing the sample report…');
    try {
      const created = await request('/api/sessions', {});
      setSession(created); setReportState('ready'); setStatus('Your report is ready. Let’s talk.');
    } catch (err) {
      setReportState('empty'); setFileError(err.message); setStatus('Choose a report to try again.');
    }
  }

  async function ensureSession() {
    if (session) return session;
    const created = await request('/api/sessions', {});
    setSession(created);
    return created;
  }

  async function stop() {
    activityDispatch({ type: 'reset' });
    careDispatch({ type: 'close' }); setCareBusy(false); clearTimeout(careTimer.current);
    generation.current++;
    clearTimeout(workerTimer.current);
    const room = roomRef.current;
    roomRef.current = null;
    await room?.disconnect();
    audioHost.current?.replaceChildren();
    setConnected(false); setConnecting(false); setStatus('Conversation ended');
    // Keep this report's session so a stopped call can be started again without
    // silently falling back to the configured sample report.
  }

  async function start() {
    if (reportState !== 'ready') return;
    careDispatch({ type: 'close' });
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('Microphone access requires HTTPS on your phone, or localhost on this computer.');
      return;
    }
    const attempt = ++generation.current;
    disconnectReason.current = '';
    activityDispatch({ type: 'connecting' });
    setConnecting(true); setError(''); setStatus('Connecting your microphone…');
    setMessages([]); setTimings({});
    const room = new Room({ audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    let workerReady = false;
    roomRef.current = room;
    // Unlock audio in the initial click handler (important on mobile browsers).
    const unlock = room.startAudio().catch(() => {});
    try {
      const current = await ensureSession();
      if (generation.current !== attempt) { await room.disconnect(); return; }
      const token = await request(`/api/sessions/${current.session_id}/token`, {});
      if (generation.current !== attempt) { await room.disconnect(); return; }
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (generation.current !== attempt) return;
        if (track.kind === Track.Kind.Audio) audioHost.current?.appendChild(track.attach());
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach(el => el.remove()));
      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        if (generation.current !== attempt) return;
        const role = participant?.identity === room.localParticipant.identity ? 'user' : 'assistant';
        // User display text is supplied by the worker so Hindi normalization can
        // replace the same committed turn without racing raw STT segment updates.
        if (role === 'user') return;
        setMessages(previous => {
          const next = [...previous];
          for (const segment of segments) {
            const item = { id: segment.id, role, text: segment.text, final: segment.final };
            const index = next.findIndex(m => m.id === segment.id);
            if (index >= 0) next[index] = item; else next.push(item);
          }
          return next.slice(-100);
        });
      });
      room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
        if (generation.current !== attempt || !participant || participant.identity === room.localParticipant.identity) return;
        if (topic !== 'medivoice') return;
        try {
          const event = JSON.parse(new TextDecoder().decode(payload));
          workerReady = true;
          clearTimeout(workerTimer.current);
          activityDispatch(event);
          if (event.type === 'user_transcript') setMessages(previous => applyUserTranscript(previous, event));
          if (event.type === 'answer_ready') { setTimings(event.timings_ms); setLanguage(event.language); }
          if (event.type === 'latency') setTimings(t => ({ ...t, voice_response: event.speech_end_to_agent_speaking_ms }));
          if (event.type === 'error') setError(event.message);
          if (event.type === 'session_warning') setStatus(event.message);
          if (event.type === 'session_expired') disconnectReason.current = event.message;
          if (event.type === 'doctor_connect') {
            conversationDialog.current?.close();
            careDispatch({ type: 'server', state: event.state });
            setCareBusy(false); clearTimeout(careTimer.current);
          }
        } catch { /* Ignore unrelated/malformed room data. */ }
      });
      room.on(RoomEvent.Reconnecting, () => { if (generation.current === attempt) { setStatus('Reconnecting…'); activityDispatch({ type: 'connecting' }); } });
      room.on(RoomEvent.Reconnected, () => {
        if (generation.current === attempt) {
          setStatus('Listening to you');
          activityDispatch({ type: 'agent_state', state: 'listening' });
          room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({ type: 'sync' })), { reliable: true, topic: 'medivoice.care' }).catch(() => {});
        }
      });
      room.on(RoomEvent.Disconnected, () => {
        if (roomRef.current === room) {
          clearTimeout(workerTimer.current); setConnected(false); setStatus(disconnectReason.current || 'Disconnected — start again');
          activityDispatch({ type: 'reset' });
          // The report session remains valid until its server-side expiry. Retain
          // it so reconnecting continues with the same uploaded report.
          audioHost.current?.replaceChildren(); roomRef.current = null;
          careDispatch({ type: 'close' }); setCareBusy(false); clearTimeout(careTimer.current);
        }
      });
      await room.connect(token.server_url, token.participant_token);
      await unlock;
      if (generation.current !== attempt) { await room.disconnect(); return; }
      await room.localParticipant.setMicrophoneEnabled(true);
      if (generation.current !== attempt) { await room.disconnect(); return; }
      setConnected(true); setStatus('Waiting for MediVoice…');
      if (!workerReady) workerTimer.current = setTimeout(() => {
        if (generation.current !== attempt) return;
        setError('The voice agent has not responded. Check that the agent worker is running.');
        stop();
      }, 30000);
    } catch (err) {
      await room.disconnect();
      if (generation.current === attempt) { setError(err.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow microphone access in your browser and try again.' : err.message); setStatus('Unable to connect'); roomRef.current = null; }
    } finally { if (generation.current === attempt) setConnecting(false); }
  }

  async function sendText(event) {
    event.preventDefault();
    if (!text.trim() || textBusy) return;
    const question = text.trim(); setText(''); setTextBusy(true); setError('');
    setMessages(m => [...m, { id: crypto.randomUUID(), role: 'user', text: question }]);
    if (isCareIntent(question)) {
      conversationDialog.current?.close();
      careDispatch({ type: 'reply', text: question });
      setTextBusy(false);
      return;
    }
    try {
      const current = await ensureSession();
      const result = await request(`/api/sessions/${current.session_id}/message`, { text: question });
      setMessages(m => [...m, { id: crypto.randomUUID(), role: 'assistant', text: result.text }]);
      setTimings(result.timings_ms); setLanguage(result.language);
    } catch (err) { setError(err.message); } finally { setTextBusy(false); }
  }

  async function dispatchCare(action) {
    if (!connected) { careDispatch(action); return; }
    if (careBusy || !roomRef.current) return;
    setCareBusy(true);
    activityDispatch({ type: 'stage', stage: 'appointment', status: 'working' });
    try {
      await roomRef.current.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({
        type: 'action', revision: care.revision, action,
      })), { reliable: true, topic: 'medivoice.care' });
      clearTimeout(careTimer.current);
      careTimer.current = setTimeout(() => {
        activityDispatch({ type: 'error' });
        setCareBusy(false); setError('Doctor Connect took too long. Please try again.');
      }, 85000);
    } catch {
      activityDispatch({ type: 'error' });
      setCareBusy(false); setError('Could not send your selection. Please reconnect.');
    }
  }

  const missing = health?.missing_voice_settings || [];
  const voiceDisabled = reportState !== 'ready' || !health || missing.length > 0 || health.demo_mode || textBusy;
  const textDisabled = !health || (!health.demo_mode && health.missing_text_settings.length > 0) || connected || connecting;

  const reportAdded = reportState !== 'empty';
  const displayActivity = connected || connecting ? activity : reportState === 'processing'
    ? { motion: 'thinking', text: 'Reading your report…' }
    : { motion: 'idle', text: 'Your report is ready. Let’s talk.' };

  return <div className={`desktop-stage${reportAdded ? ' report-added' : ''}`}>
    <aside className="desktop-guide desktop-guide-left" aria-label="How MediVoice works">
      <p className="desktop-guide-label">Getting started</p>
      <h2>How MediVoice works</h2>
      <ol className="desktop-steps">
        <li><FileText aria-hidden="true" /><span><strong>Add your report</strong><small>Choose a clear PDF or report image.</small></span></li>
        <li><MessageCircle aria-hidden="true" /><span><strong>Ask by voice</strong><small>Speak in English or Hindi.</small></span></li>
        <li><Stethoscope aria-hidden="true" /><span><strong>Understand the results</strong><small>Get a simple explanation of your report.</small></span></li>
      </ol>
    </aside>
    <div ref={appShell} className={`app-shell${reportAdded ? ' report-added-layout' : ''}`}>
    <header><div className="brand-row"><button className="menu-button" aria-label="Open conversation text" aria-haspopup="dialog" onClick={() => conversationDialog.current?.showModal()}><Menu size={26} aria-hidden="true" /></button><div><span className="brand">MediVoice</span><p>Your report companion</p></div>{health?.demo_mode && <span className="demo-badge">Demo mode</span>}</div></header>
    <main>
      <div className="welcome"><h1>Understand your report</h1><p className="intro">Ask in Hindi or English.</p>
        {!reportAdded && <p className="voice-home-hint"><Mic size={17} aria-hidden="true" />Voice-enabled · No typing needed</p>}
      </div>
      {reportAdded && <button className="report-summary" aria-haspopup="dialog" aria-label="Report added. View report details" onClick={() => reportDialog.current?.showModal()}>
        <CheckCircle size={24} aria-hidden="true" /><span><strong>Report added</strong><small>{reportFile ? `${reportSummary?.processed_page_count || 1} page${reportSummary?.processed_page_count === 1 ? '' : 's'} analysed` : 'Sample report · demo'}</small></span>
      </button>}
      <section className="step" aria-labelledby="report-title" hidden={reportAdded}>
          <div className="step-heading"><span className="step-number">1</span><div><h2 id="report-title">Add your report</h2></div></div>
          <div className="upload-panel">
            <input hidden ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={chooseReport} aria-label="Take a report photo" />
            <input hidden ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={chooseReport} aria-label="Choose a report image or PDF" />
            {reportState === 'empty' && <><div className="upload-actions"><button className="photo-button" onClick={() => photoInput.current?.click()}><Camera size={25} aria-hidden="true" />Take photo</button><button className="file-button" onClick={() => fileInput.current?.click()}><Upload size={23} aria-hidden="true" />Choose file</button></div>
              <button className="sample-report-button home-voice-option" onClick={trySampleReport}><Mic size={21} aria-hidden="true" /><span>Try voice<small>With a sample report</small></span></button></>}
          </div>
          {fileError && <p className="file-error" role="alert">{fileError}</p>}
          <p className="notice">Your report is securely sent to MediVoice for analysis and used only for this conversation.</p>
      </section>
      <section className="step talk-step" aria-label="Voice conversation" hidden={!reportAdded}>
        {reportAdded ? <p className="conversation-eyebrow">{connected ? 'Conversation in progress' : connecting ? 'Starting your conversation' : reportState === 'processing' ? 'Reading your report…' : 'Ready when you are'}</p> : <div className="step-heading"><span className="step-number">2</span><div><h2>Let’s talk about it</h2><p>Add a report or try the sample to begin.</p></div></div>}
        {reportAdded && care.stage === 'closed' && <VoiceActivity activity={displayActivity} />}
        {connected || connecting ? <button className="call-button end" onClick={stop}><PhoneOff size={26} aria-hidden="true" />Stop talking</button> : <button className="call-button" disabled={voiceDisabled} onClick={start}><Mic size={27} aria-hidden="true" />Start talking</button>}
        {!connected && !connecting && reportState === 'ready' && voiceDisabled && <p className="status" role="status">Voice is unavailable. Check demo setup in the menu.</p>}
        {error && <div role="alert" className="error"><p>Something went wrong. Please try again or ask someone to help.</p><button onClick={() => setError('')}>Dismiss</button></div>}
      </section>
      <footer><p>Always follow your doctor’s advice.</p></footer>
    </main>
    <dialog ref={reportDialog} className="conversation-dialog report-details-dialog" aria-labelledby="report-details-title">
      <div className="dialog-heading"><h2 id="report-details-title">Your report</h2><button className="menu-button" aria-label="Close report details" onClick={() => reportDialog.current?.close()}><X size={25} /></button></div>
      <p className="report-filename">{reportFile?.name || 'Sample report'}</p>
      <p className="notice">{reportFile ? `This report was analysed for this conversation${reportSummary?.lab_name ? ` · ${reportSummary.lab_name}` : ''}.` : 'Demo: answers use the sample report.'}</p>
      {reportPreview && <img className="report-detail-image" src={reportPreview} alt="Selected medical report preview" onError={() => setReportPreview('')} />}
      <button className="sample-report-button" disabled={connected || connecting} onClick={() => { setReportState('empty'); setReportFile(null); setReportSummary(null); setSession(null); setFileError(''); reportDialog.current?.close(); }}>Change report</button>
      {(connected || connecting) && <p>End the conversation before changing your report.</p>}
    </dialog>
    <dialog ref={conversationDialog} className="conversation-dialog" aria-labelledby="conversation-title">
      <div className="dialog-heading"><h2 id="conversation-title">Your conversation</h2><button className="menu-button" aria-label="Close conversation" onClick={() => conversationDialog.current?.close()}><X size={25} aria-hidden="true" /></button></div>
      <p className="conversation-hint">Your conversation text appears here. Closing this panel won’t end your call.</p>
      <p className="conversation-hint">Try “Please explain my report.” Allow microphone access when asked.</p>
      <div className="messages" role="log" aria-live="polite">{messages.length === 0 && <p>No conversation yet. Start talking to see your words and MediVoice’s replies here.</p>}{messages.map(m => <div className={`message ${m.role}`} key={m.id}><strong>{m.role === 'user' ? 'You' : 'MediVoice'}</strong><p>{m.text}{m.final === false && ' …'}</p></div>)}<div ref={bottom} /></div>
      <details className="setup"><summary>Demo setup and testing</summary>
        {health?.demo_mode && <p>Simulated mode: text replies are fixed examples. Voice is disabled.</p>}
        {missing.length > 0 && <p>Missing settings: {missing.join(', ')}. Add these to the backend configuration, restart it, and refresh.</p>}
        {error && <p>{error}</p>}
        <p>Detected response language: {language}. Text tests use the sample report, one question at a time.</p>
        <form onSubmit={sendText}><label htmlFor="test-question">Test question</label><input id="test-question" value={text} maxLength={2000} onChange={e => setText(e.target.value)} disabled={connected || connecting || textBusy} placeholder="Ask about the sample report" /><button disabled={textBusy || connected || connecting || !text.trim() || (textDisabled && !isCareIntent(text))}><Send size={20} aria-hidden="true" />{textBusy ? 'Please wait…' : 'Send question'}</button></form>
        <p>Fictional sample: hemoglobin 9.2 g/dL (reference 13.5–17.5), WBC 7,500 cells/µL, platelets 240,000 cells/µL.</p>
        {Object.keys(timings).length > 0 && <div className="timings"><p>Timings exclude browser audio playback. Voice response is a server-side estimate.</p>{Object.entries(timings).map(([key, value]) => <p key={key}>{key.replaceAll('_', ' ')}: {(value / 1000).toFixed(2)}s</p>)}</div>}
      </details>
    </dialog><DoctorConnect state={care} dispatch={dispatchCare} live={connected} busy={careBusy} error={error} onStop={stop} activity={activity} /><div ref={audioHost} className="audio-host" />
    </div>
    <aside className="desktop-guide desktop-guide-right" aria-label="Report and session guidance">
      <p className="desktop-guide-label">Before you begin</p>
      <h2>Report guidelines</h2>
      <div className="desktop-guide-item"><FileText aria-hidden="true" /><p><strong>Supported files</strong><span>PDF, JPG, PNG or WebP · up to 10 MB · up to 5 pages</span></p></div>
      <div className="desktop-guide-item"><Clock3 aria-hidden="true" /><p><strong>Voice session</strong><span>Up to 3 minutes · ends after 60 seconds without speech</span></p></div>
      <div className="desktop-guide-item"><ShieldCheck aria-hidden="true" /><p><strong>Your privacy</strong><span>Your report is used only for this conversation.</span></p></div>
      <p className="desktop-guide-safety">MediVoice explains report information. It does not diagnose emergencies or replace a doctor.</p>
    </aside>
  </div>;
}
