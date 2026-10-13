export const HAND_SIDES = ['left', 'right'];
export const ZERO_SAMPLE_COUNT = 30;

export function completeHand(hand) {
  return hand?.fingers?.length === 5 && hand.fingers.every((finger) => (
    finger?.sensorName && finger.values?.length === 9 &&
    finger.values.every((v) => Number.isFinite(v) && v >= 0 && v <= 255)
  ));
}

export function validCalibration(calibration) {
  return calibration?.version === 1 && HAND_SIDES.every((side) => {
    const sensors = Object.values(calibration?.hands?.[side] || {});
    return sensors.length === 5 && sensors.every((sensor) => (
      sensor.baseline?.length === 9 && sensor.baseline.every((v) => Number.isFinite(v) && v >= 0 && v <= 255)
    ));
  });
}

export function makeCalibration(samples) {
  const calibration = { version: 1, createdAt: Date.now(), hands: {} };
  for (const side of HAND_SIDES) {
    const frames = samples[side];
    if (!frames || frames.length < ZERO_SAMPLE_COUNT || !frames.every(completeHand)) {
      throw new Error('Both hands need fresh, complete readings.');
    }
    calibration.hands[side] = {};
    for (const finger of frames[0].fingers) {
      const matched = frames.map((frame) => frame.fingers.find((f) => f.sensorName === finger.sensorName));
      if (matched.some((f) => !f)) throw new Error('Sensor identity changed. Try zeroing again.');
      calibration.hands[side][finger.sensorName] = {
        baseline: finger.values.map((_, i) => {
          const sorted = matched.map((f) => f.values[i]).sort((a, b) => a - b);
          const mid = Math.floor(sorted.length / 2);
          return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
        }),
      };
    }
  }
  return calibration;
}

export function zeroHand(hand, calibration, side) {
  if (!hand) return null;
  return {
    ...hand,
    fingers: hand.fingers.map((finger) => {
      if (!finger) return null;
      const baseline = calibration?.hands?.[side]?.[finger.sensorName]?.baseline;
      const saturated = finger.values.map((value, i) => value === 255 || baseline?.[i] === 255);
      return {
        ...finger,
        saturated,
        rawValues: finger.values,
        values: finger.values.map((value, i) => (
          Number.isFinite(value) && Number.isFinite(baseline?.[i]) && !saturated[i]
            ? Math.max(0, Math.round(value - baseline[i])) : null
        )),
      };
    }),
  };
}
