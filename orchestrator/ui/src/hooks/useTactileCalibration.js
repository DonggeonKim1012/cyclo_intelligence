import { useEffect, useRef, useState } from 'react';
import { useSelector } from 'react-redux';
import { completeHand, HAND_SIDES, makeCalibration, validCalibration, ZERO_SAMPLE_COUNT } from '../utils/tactileCalibration';

export default function useTactileCalibration(hands, enabled) {
  const url = useSelector((state) => state.ros.rosbridgeUrl);
  const key = `cyclo:tactile-zero:v1:${url}`;
  const [saved, setSaved] = useState(null);
  const [calibrating, setCalibrating] = useState(false);
  const [error, setError] = useState('');
  const collecting = useRef(null);
  const generation = useRef(0);
  const calibration = saved?.key === key ? saved.value : null;

  useEffect(() => {
    let cancelled = false;
    const initialGeneration = ++generation.current;
    collecting.current = null;
    setCalibrating(false);
    setError('');
    setSaved(null);
    if (!enabled || !url) return undefined;
    let local = null;
    try { local = JSON.parse(localStorage.getItem(key)); } catch (_error) {}
    if (validCalibration(local)) setSaved({ key, value: local });
    // This optional file contains only this robot's measured baseline, never a generic default.
    const load = async () => {
      try {
        const response = await fetch(`${process.env.PUBLIC_URL || ''}/tactile-zero.local.json`, { cache: 'no-store' });
        if (!response.ok) return;
        const deployed = await response.json();
        const matchesHost = deployed.hosts?.some((host) => host.toLowerCase() === new URL(url).hostname.toLowerCase());
        if (!cancelled && generation.current === initialGeneration && matchesHost && validCalibration(deployed) &&
            (!validCalibration(local) || deployed.createdAt > local.createdAt)) {
          setSaved({ key, value: deployed });
        }
      } catch (_error) { /* No device baseline installed: keep RAW until explicitly zeroed. */ }
    };
    load();
    return () => { cancelled = true; collecting.current = null; };
  }, [key, url, enabled]);

  useEffect(() => {
    const active = collecting.current;
    if (!calibrating || !active) return;
    for (const side of HAND_SIDES) {
      const hand = hands[side];
      if (hand !== active.last[side] && completeHand(hand) && Date.now() - hand.receivedAt < 1000) {
        active.last[side] = hand;
        if (active.samples[side].length < ZERO_SAMPLE_COUNT) active.samples[side].push(hand);
      }
    }
    if (HAND_SIDES.every((side) => active.samples[side].length >= ZERO_SAMPLE_COUNT &&
        Date.now() - active.last[side].receivedAt < 1000)) {
      try {
        const value = makeCalibration(active.samples);
        setSaved({ key, value });
        try { localStorage.setItem(key, JSON.stringify(value)); }
        catch (_error) { setError('Zero applied for this session; browser storage is unavailable.'); }
      } catch (failure) { setError(failure.message); }
      collecting.current = null;
      setCalibrating(false);
    }
  }, [hands, calibrating, key]);

  useEffect(() => {
    if (!calibrating) return undefined;
    const timeout = setTimeout(() => {
      collecting.current = null;
      setCalibrating(false);
      setError('Zeroing timed out. Check both hands are streaming, then retry.');
    }, 6000);
    return () => clearTimeout(timeout);
  }, [calibrating]);

  const startZero = () => {
    generation.current += 1;
    collecting.current = { samples: { left: [], right: [] }, last: { ...hands } };
    setError('');
    setCalibrating(true);
  };
  return { calibration, calibrating, error, startZero };
}
