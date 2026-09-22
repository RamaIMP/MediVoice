import './voiceActivity.css';

export default function VoiceActivity({ activity, compact = false }) {
  return <div className={`voice-activity${compact ? ' compact' : ''}`} data-motion={activity.motion}>
    <div className="voice-orb-stage" aria-hidden="true"><div className="voice-orb" /></div>
    <p role="status" aria-live="polite" aria-atomic="true">{activity.text}</p>
  </div>;
}
