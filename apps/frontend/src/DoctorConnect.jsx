import { useEffect, useRef, useState } from 'react';
import { MapPin, X } from 'lucide-react';
import { carePrompt, careTitle, channelFor, doctorsFor } from './doctorConnect';
import './doctorConnect.css';
import VoiceActivity from './VoiceActivity.jsx';

export default function DoctorConnect({ state, dispatch, live = false, busy = false, error = '', onStop, activity }) {
  const dialog = useRef(null);
  const [answer, setAnswer] = useState('');
  const [area, setArea] = useState('');
  const [chooseArea, setChooseArea] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState('');
  const locationRequest = useRef(0);
  const open = state.stage !== 'closed';
  useEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal();
    if (!open) dialog.current.close();
  }, [open]);
  useEffect(() => { setAnswer(state[state.stage] || ''); if (dialog.current) dialog.current.scrollTop = 0; }, [state.stage, state.date, state.time, state.patient]);
  useEffect(() => { locationRequest.current += 1; setLocating(false); }, [state.stage, state.revision]);
  useEffect(() => () => { locationRequest.current += 1; }, []);
  const doctors = doctorsFor(state);
  const selected = doctors.find(d => d.id === state.selected);
  const real = ['google', 'here'].includes(state.source);
  function useLocation() {
    if (locating || busy) return;
    setLocationError('');
    if (!window.isSecureContext || !navigator.geolocation) {
      setLocationError('Location needs HTTPS or localhost. Please choose your area instead.'); setChooseArea(true); return;
    }
    setLocating(true);
    const request = ++locationRequest.current;
    navigator.geolocation.getCurrentPosition(position => {
      if (request !== locationRequest.current) return;
      setLocating(false);
      dispatch({ type: 'search_location', location: { lat: position.coords.latitude, lng: position.coords.longitude } });
    }, () => {
      if (request !== locationRequest.current) return;
      setLocating(false); setChooseArea(true);
      setLocationError('Could not access your location. Please type or say your area and city.');
    }, { timeout: 10000, maximumAge: 60000, enableHighAccuracy: false });
  }
  function reply(event) {
    event.preventDefault();
    dispatch(['date', 'time', 'patient'].includes(state.stage)
      ? { type: state.stage === 'patient' ? 'set_patient_touch' : `set_${state.stage}`, value: answer } : { type: 'search', area: answer });
  }
  return <dialog ref={dialog} className="care-dialog" aria-labelledby="care-title" onCancel={e => { e.preventDefault(); dispatch({ type: 'close' }); }}>
    <div className="care-heading"><div><strong>MediVoice</strong><small>{real ? 'Real listings · Demo booking' : 'Doctor Connect · Dummy listings'}</small></div><button aria-label="Return to report conversation" disabled={busy} onClick={() => dispatch({ type: 'close' })}><X /></button></div>
    <div className="care-content">
      {live && activity && <VoiceActivity activity={activity} compact />}
      {busy && !live && <p role="status">Preparing your appointment request…</p>}
      {error && live && <p role="alert">{error}</p>}
      <fieldset disabled={busy || locating} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <h2 id="care-title">{careTitle(state.stage)}</h2>
      {['date', 'time', 'patient'].includes(state.stage) && <p className="care-step">Step {['date', 'time', 'patient'].indexOf(state.stage) + 1} of 3 · Date → Time → Name</p>}
      {['date', 'time', 'patient', 'review', 'patient_confirm'].includes(state.stage) && <button className="care-secondary" onClick={() => dispatch({ type: 'back' })}>Back</button>}
      {state.search_notice && <p className="care-warning" role="status">{state.search_notice}</p>}
      {state.stage === 'search' ? <>
        {live && <><button className="care-primary" onClick={useLocation}><MapPin size={18} /> {locating ? 'Finding your location…' : 'Use my location'}</button><button className="care-secondary" onClick={() => { locationRequest.current += 1; setChooseArea(true); }}>Choose area</button><small>Your location is shared with Google to find nearby care only when you tap above.</small>{locationError && <p role="alert">{locationError}</p>}</>}
        {live && chooseArea && <form className="care-reply" onSubmit={e => { e.preventDefault(); dispatch({ type: 'search', area: area.trim() }); }}><label htmlFor="doctor-area">Search your area and city</label><div><input id="doctor-area" value={area} onChange={e => setArea(e.target.value)} maxLength={100} placeholder="Whitefield, Bengaluru" required /><button disabled={!area.trim()} type="submit">Search</button></div><small>Your entered area is sent to the configured location provider only when you tap Search.</small></form>}
        <p className="care-muted"><MapPin size={16} />{real ? state.area : state.source === 'location' ? 'Choose a location to see nearby care' : 'Demo neighbourhood · illustrative distances'}</p>
        {real && doctors.some(d => Number.isFinite(d.distance_km)) && <p className="care-muted">Approximate straight-line distances, not driving distances.</p>}
        {!real && doctors.length > 0 && <div className="care-map" aria-label="Illustrative map, not a real location"><span className="care-road" /><span className="care-road cross" />{doctors.map((d, i) => <button key={d.id} className={`care-pin pin-${i}`} onClick={() => dispatch({ type: 'select_touch', id: d.id })} aria-label={`Select ${d.name}`}>{i + 1}</button>)}<span className="care-you">● You (demo)</span></div>}
        <div className="care-list">{doctors.map((d, i) => <div key={d.id}><button className="care-doctor" onClick={() => dispatch({ type: 'select_touch', id: d.id })}><span className="care-number">{i + 1}</span><span><strong>{d.name}</strong><small>{real ? d.clinic : d.specialty}</small>{real && Number.isFinite(d.distance_km) && <small>~{d.distance_km} km away</small>}</span>{!real && <span className="care-distance">~{d.distance} km</span>}</button>{real && d.maps_url?.startsWith('https://www.google.com/maps/') && <a href={d.maps_url} target="_blank" rel="noopener noreferrer">View location on Google Maps</a>}{real && d.attributions?.filter(Boolean).map((a, i) => <small key={i}>{a}</small>)}</div>)}</div>
      </> : selected && <div className="care-selected"><strong>{selected.name}</strong><small>{selected.clinic}{!real && ' · General physician'}</small><button onClick={() => dispatch({ type: 'back' })}>Choose another</button></div>}
      <p className="care-prompt" role="status">{carePrompt(state)}</p>
      {state.notice && <p role="alert">{state.notice}</p>}
      {state.stage === 'confirm' && <button className="care-primary" onClick={() => dispatch({ type: 'yes' })}>Yes, continue</button>}
      {state.stage === 'patient_confirm' && <><button className="care-primary" onClick={() => dispatch({ type: 'yes' })}>Confirm name</button><button className="care-secondary" onClick={() => dispatch({ type: 'edit_patient' })}>Edit name</button></>}
      {['review', 'handoff'].includes(state.stage) && <>
        <dl className="care-summary"><dt>Name</dt><dd>{state.patient}</dd><dt>Preferred date</dt><dd>{state.date}</dd><dt>Preferred time</dt><dd>{state.time}</dd></dl>
        <p className="care-warning">{real ? 'Simulated WhatsApp message only. No verified WhatsApp number, availability or clinic connection.' : channelFor(selected) === 'WhatsApp' ? 'Demo WhatsApp contact available.' : channelFor(selected) === 'Phone' ? 'No verified WhatsApp. Fallback: call +91 XXXXX XXXXX (dummy number).' : 'No WhatsApp or phone. Fallback: appointment page (simulated).'}</p>
        {state.stage === 'review' && <><button className="care-primary" onClick={() => dispatch({ type: 'yes' })}>Preview booking request</button><button className="care-secondary" onClick={() => dispatch({ type: 'edit' })}>Edit details</button><p>Demo—nothing will be booked.</p></>}
        {state.stage === 'handoff' && <><p className="care-prompt">{channelFor(selected) === 'WhatsApp' ? `Hello, I’d like to request an appointment with ${selected.name} for ${state.patient} on ${state.date}, preferably at ${state.time}. Please confirm availability.` : channelFor(selected) === 'Phone' ? 'In the live version, the Call clinic button opens your phone dialler.' : 'In the live version, the clinic’s verified appointment page opens.'}</p><p role="status">Nothing sent, called or booked.</p><button className="care-primary" onClick={() => dispatch({ type: 'close' })}>Done</button></>}
      </>}
      {['date', 'time', 'patient'].includes(state.stage) && <form onSubmit={reply} className="care-reply"><label htmlFor="care-answer">{state.stage === 'date' ? 'Preferred date' : state.stage === 'time' ? 'Preferred time (not a confirmed slot)' : 'Patient name'}</label><div><input id="care-answer" type={state.stage === 'date' ? 'date' : state.stage === 'time' ? 'time' : 'text'} autoComplete="off" maxLength={100} value={answer} onChange={e => setAnswer(e.target.value)} required /><button type="submit" disabled={!answer.trim()}>{state.stage === 'patient' ? 'Review details' : 'Continue'}</button></div><small>Use these on-screen fields to continue. Voice does not collect booking details.</small></form>}
      <p className="care-footnote">{real ? (state.source === 'here' ? 'HERE listings. ' : 'Google Maps listings. ') : 'Fictional doctors and contacts. '}Booking and WhatsApp are simulated. Nothing is sent to a clinic. Preferred times are not available appointment slots.</p>
      </fieldset>
      {live && <><button className="care-secondary" disabled={busy} onClick={() => dispatch({ type: 'close' })}>Back to report conversation</button><button className="care-secondary" onClick={onStop}>End voice conversation</button></>}
    </div>
  </dialog>;
}
