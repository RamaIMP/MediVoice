// Fictional local adapter. Replace searchDoctors with the real tool result later.
export const doctors = [
  { id: 'demo-1', name: 'Dr. Asha (Demo)', clinic: 'Demo Green Clinic', specialty: 'General physician', distance: 0.8, whatsapp: true, phone: true, booking: true },
  { id: 'demo-2', name: 'Dr. Ravi (Demo)', clinic: 'Demo Family Clinic', specialty: 'General physician', distance: 1.2, whatsapp: false, phone: true, booking: true },
  { id: 'demo-3', name: 'Dr. Meera (Demo)', clinic: 'Demo Care Centre', specialty: 'General physician', distance: 1.7, whatsapp: false, phone: false, booking: true },
];
export const initialCare = () => ({ stage: 'closed', selected: null, date: '', time: '', patient: '', notice: '' });
export const careTitle = stage => ({ search: 'Choose a doctor', confirm: 'Your selected doctor', date: 'Choose a date', time: 'Choose a time', patient: 'Patient details', patient_confirm: 'Confirm your name', review: 'Review your request', handoff: 'Contact the clinic' })[stage] || 'Doctor Connect';
export const isCareIntent = text => /(?:find|connect|see|visit|book|need|nearby|near me|appointment).*(?:doctor|clinic|hospital)|(?:doctor|clinic|hospital).*(?:near|appointment|book|connect)|डॉक्टर|चिकित्सक|డాక్టర్|వైద్యు|doctor chahiye/i.test(text);
export const channelFor = d => d.whatsapp ? 'WhatsApp' : d.phone ? 'Phone' : d.booking ? 'Appointment page' : null;
export const doctorsFor = s => Array.isArray(s.doctors) ? s.doctors.map(d => ({ ...doctors.find(item => item.id === d.id), ...d })) : doctors;
export function carePrompt(s) {
  const d = doctorsFor(s).find(d => d.id === s.selected);
  if (s.stage === 'patient_confirm') return `You entered ${s.patient}. Please review the request below.`;
  if (s.stage === 'search' && s.source === 'location') return 'Use the controls below to share your location or choose your area and city.';
  if (s.stage === 'search' && ['google', 'here'].includes(s.source)) return 'Real listings · Demo booking. Tap a listing to choose it.';
  return ({ search: 'Tap the doctor you want to book.', confirm: `You selected ${d?.name}. Continue below.`, date: 'Please select your preferred date below.', time: 'Please select your preferred time below.', patient: 'Please enter the patient’s name, then tap Review details.', review: 'Please check the details and use the button below to continue.', handoff: 'Demo handoff only. Nothing has been sent or booked.' })[s.stage] || '';
}
export function careTransition(s, action) {
  if (action.type === 'back') {
    const stage = ({ date: 'search', time: 'date', patient: 'time', review: 'patient', patient_confirm: 'patient' })[s.stage];
    return stage ? { ...s, stage, notice: '' } : s;
  }
  if (action.type === 'set_patient_touch' && s.stage === 'patient') {
    const patient = (action.value || '').trim();
    return patient && patient.length <= 100 ? { ...s, patient, stage: 'review', notice: '' } : { ...s, notice: 'Please enter a name (up to 100 characters).' };
  }
  if (action.type === `set_${s.stage}` && ['date', 'time'].includes(s.stage)) {
    const value = (action.value || '').trim();
    return value && value.length <= 100
      ? { ...s, [s.stage]: value, stage: s.stage === 'date' ? 'time' : 'patient', notice: '' }
      : { ...s, notice: 'Please provide a value.' };
  }
  if (action.type === 'select_touch' && s.stage !== 'closed') {
    return doctorsFor(s).some(d => d.id === action.id) ? { ...s, selected: action.id, stage: 'date', notice: '' } : s;
  }
  if (action.type === 'edit_patient' && s.stage === 'patient_confirm') return { ...s, stage: 'patient', notice: '' };
  if (action.type === 'yes') return careTransition(s, { type: 'reply', text: 'yes' });
  if (action.type === `set_${s.stage}` && s.stage === 'patient') return careTransition(s, { type: 'set_patient_touch', value: action.value });
  if (action.type === 'server') {
    const v = action.state;
    if (!v || !['closed', 'search', 'confirm', 'date', 'time', 'patient', 'patient_confirm', 'review', 'handoff'].includes(v.stage) || !Number.isInteger(v.revision)) return s;
    if (v.revision < (s.revision ?? -1)) return s;
    if (v.selected && !doctorsFor(v).some(d => d.id === v.selected)) return s;
    return { ...v };
  }
  if (action.type === 'close') return initialCare();
  if (action.type === 'open') return { ...initialCare(), stage: 'search' };
  if (action.type === 'edit') return { ...s, stage: 'date', notice: '' };
  if (action.type === 'select') {
    if (!doctors.some(d => d.id === action.id)) return { ...s, notice: 'Please select one of the displayed doctors.' };
    return { ...s, selected: action.id, stage: 'confirm', notice: '' };
  }
  const text = (action.text || '').trim();
  if (!text) return s;
  if (/^(cancel|stop|close|रद्द|ఆపు)[.! ]*$/i.test(text)) return initialCare();
  if (s.stage === 'closed') return isCareIntent(text) ? { ...initialCare(), stage: 'search' } : s;
  if (/^(change doctor|another doctor|choose another)/i.test(text)) return { ...s, selected: null, stage: 'search', notice: '' };
  const yes = /^(yes|yeah|sure|okay|ok|please|हाँ|हां|అవును)\b|^(हाँ|हां|అవును)$|^book( it)?$/i.test(text);
  if (s.stage === 'patient_confirm') return yes ? { ...s, stage: 'review', notice: '' } : { ...s, stage: 'patient', notice: '' };
  if (s.stage === 'search') {
    const index = /\b(1|first|one)\b|पहले|पहला|మొదటి/i.test(text) ? 0 : /\b(2|second|two)\b|दूसरे|दूसरा|రెండో|రెండవ/i.test(text) ? 1 : /\b(3|third|three)\b|तीसरे|तीसरा|మూడో|మూడవ/i.test(text) ? 2 : -1;
    return index < 0 ? { ...s, notice: 'Please choose doctor 1, 2 or 3.' } : careTransition(s, { type: 'select', id: doctors[index].id });
  }
  if (s.stage === 'confirm') return yes ? { ...s, stage: 'date', notice: '' } : { ...s, notice: 'Say yes to continue, or choose another doctor.' };
  if (['date', 'time', 'patient'].includes(s.stage)) {
    if (text.length > 100) return { ...s, notice: 'Please keep this answer under 100 characters.' };
    return { ...s, [s.stage]: text, stage: ({ date: 'time', time: 'patient', patient: 'patient_confirm' })[s.stage], notice: '' };
  }
  if (s.stage === 'review') return yes ? { ...s, stage: 'handoff', notice: '' } : { ...s, notice: 'Confirm with yes, or use Edit details.' };
  return s;
}
