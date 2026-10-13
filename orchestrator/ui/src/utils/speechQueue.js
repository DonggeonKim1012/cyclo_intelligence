// Serialize notifications: status, action events and camera warnings can arrive
// together. Cancelling before every speak used to interrupt recording feedback.
export function createSpeechQueue({ getVoice = () => null, onError = () => {} } = {}) {
  const synth = window.speechSynthesis;
  const queue = [];
  let active = null; // Keep the utterance alive through its end/error callback.
  let blocked = null;
  let disposed = false;
  let last = null;

  const pump = () => {
    if (disposed || active || blocked || !queue.length) return;
    const item = queue.shift();
    const utterance = new SpeechSynthesisUtterance(item.text);
    active = { item, utterance };
    utterance.lang = item.lang;
    utterance.rate = 1.1;
    utterance.pitch = 1.1;
    utterance.volume = 1;
    if (item.lang === 'en-US') utterance.voice = getVoice();
    utterance.onend = () => {
      if (disposed) return;
      active = null;
      pump();
    };
    utterance.onerror = ({ error }) => {
      if (disposed) return;
      active = null;
      onError(error);
      // Browser autoplay rejection requires a local user gesture; a ROS button
      // event is not one. Retry once, only while the notification is still fresh.
      if (error === 'not-allowed' && !item.retried) {
        blocked = { ...item, retried: true };
      } else {
        pump();
      }
    };
    try {
      synth.resume();
      synth.speak(utterance);
    } catch (error) {
      utterance.onerror({ error: error.message || 'synthesis-failed' });
    }
  };

  const unlock = () => {
    if (!blocked || disposed) return;
    if (Date.now() - blocked.at < 10000) queue.unshift(blocked);
    blocked = null;
    // Drop stale announcements rather than replay old recording state.
    while (queue.length && Date.now() - queue[0].at >= 10000) queue.shift();
    pump();
  };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);

  return {
    speak(text, lang = 'en-US') {
      if (disposed) return;
      if (!synth) { onError('speech synthesis unavailable'); return; }
      const key = `${lang}:${text}`;
      const at = Date.now();
      // Coalesce the two ROS sources, including duplicates queued behind a warning.
      if (active?.item.key === key || blocked?.key === key ||
          queue.some(item => item.key === key) ||
          (last?.key === key && at - last.at < 2000)) return;
      last = { key, at };
      queue.push({ key, at, text, lang });
      pump();
    },
    dispose() {
      disposed = true;
      queue.length = 0;
      blocked = null;
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      if (active) synth.cancel();
      active = null;
    },
  };
}
