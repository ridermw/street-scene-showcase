/** @param {{durationSeconds:number}} options */
export function createPlayback({ durationSeconds }) {
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) throw new Error('Invalid playback duration');
  let state = 'paused', seconds = 0, previous = null;
  const snapshot = () => ({ state, seconds });
  return {
    snapshot,
    play() {
      if (state === 'playing') return snapshot();
      if (state === 'ended') seconds = 0;
      state = 'playing';
      previous = null;
      return snapshot();
    },
    pause() {
      if (state === 'playing') state = 'paused';
      previous = null;
      return snapshot();
    },
    restart() {
      seconds = 0;
      state = 'playing';
      previous = null;
      return snapshot();
    },
    seek(value) {
      if (!Number.isFinite(value) || value < 0 || value > durationSeconds) throw new Error('Invalid playback seek');
      seconds = value;
      state = value === durationSeconds ? 'ended' : state === 'playing' ? 'playing' : 'paused';
      previous = null;
      return snapshot();
    },
    tick(timestampMs) {
      if (!Number.isFinite(timestampMs) || timestampMs < 0) throw new Error('Invalid playback timestamp');
      if (state !== 'playing') return snapshot();
      if (previous !== null && timestampMs < previous) throw new Error('Playback timestamps must be monotonic');
      // A fresh anchor excludes paused and hidden time from the next playing interval.
      if (previous !== null) seconds = Math.min(durationSeconds, seconds + (timestampMs - previous) / 1000);
      previous = timestampMs;
      if (seconds === durationSeconds) {
        state = 'ended';
        previous = null;
      }
      return snapshot();
    },
  };
}
