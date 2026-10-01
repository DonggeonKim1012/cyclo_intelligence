import React, { useMemo } from 'react';
import TactileHandsPanel from '../TactileHandsPanel';
import { extractRawFingerPressures } from '../../hooks/useTactilePressureSubscription';

export function handAtTime(series, currentTime) {
  const timestamps = series?.timestamps || [];
  // Last recorded sample at or before the playhead, including backward seeks.
  let low = 0;
  let high = timestamps.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] <= currentTime) low = middle + 1;
    else high = middle;
  }
  const index = low - 1;
  const message = series?.messages?.[index];
  if (index < 0 || !message) return null;
  return {
    fingers: extractRawFingerPressures(message),
    receivedAt: timestamps[index] * 1000,
  };
}

export default function ReplayTactilePanel({ tactileData, currentTime }) {
  const hands = useMemo(() => ({
    left: handAtTime(tactileData.left, currentTime),
    right: handAtTime(tactileData.right, currentTime),
  }), [tactileData, currentTime]);

  return <TactileHandsPanel replayHands={hands} replayTime={currentTime} />;
}
