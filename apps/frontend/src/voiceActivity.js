export const initialActivity = { motion: 'idle', text: 'Ready when you are', task: null };
const tasks = {
  translate_in: 'Preparing your answer…', medical: 'Checking your report…',
  translate_out: 'Preparing your answer…', doctor_search: 'Finding doctor options…',
  appointment: 'Preparing your appointment request…',
};
export function voiceActivity(state, event) {
  if (event.type === 'reset') return initialActivity;
  if (event.type === 'connecting') return { motion: 'thinking', text: 'Connecting…', task: null };
  if (event.type === 'error') return { motion: 'idle', text: 'Please try again.', task: null };
  if (event.type === 'stage' && event.status === 'working') {
    const task = event.stage === 'translate_out' && ['doctor_search', 'appointment'].includes(state.task) ? state.task : event.stage;
    return { motion: 'thinking', text: tasks[task] || 'Preparing your answer…', task };
  }
  if (event.type === 'agent_state') {
    if (event.state === 'speaking') return { motion: 'speaking', text: 'Speaking…', task: null };
    if (event.state === 'listening') return { motion: 'listening', text: 'Listening…', task: null };
    if (event.state === 'thinking') return { ...state, motion: 'thinking', text: tasks[state.task] || 'Preparing your answer…' };
  }
  return state;
}
