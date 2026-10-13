import React, { useEffect, useState } from 'react';
import clsx from 'clsx';
import useTactileCalibration from '../hooks/useTactileCalibration';
import { completeHand, zeroHand } from '../utils/tactileCalibration';
import useTactilePressureSubscription from '../hooks/useTactilePressureSubscription';

const PRESSURE_COLOR_MAX = 255;
const STALE_AFTER_MS = 2000;
const FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Little'];

export function pressureIntensity(value) {
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.min(value / PRESSURE_COLOR_MAX, 1);
}

function FingerPressure({ side, name, sensor }) {
  const values = sensor?.values || Array(9).fill(null);
  return (
    <div className="min-w-0" role="group" aria-label={`${side} ${name}`}>
      <div className="mb-1 truncate text-center text-[9px] text-slate-300" title={sensor?.sensorName}>
        {name}
      </div>
      <div className="grid grid-cols-3 gap-px overflow-hidden rounded border border-slate-600 bg-slate-700">
        {values.map((value, index) => {
          const known = Number.isFinite(value);
          const saturated = sensor?.saturated?.[index];
          const intensity = pressureIntensity(value);
          const label = sensor?.pressureNames[index] || `cell ${index + 1}`;
          return (
            <span
              key={index}
              aria-label={`${side} ${name} ${label}: ${saturated ? 'saturated' : known ? value : 'unavailable'}`}
              title={`${sensor?.sensorName || name} / ${label}: ${saturated ? `Saturated (raw ${sensor.rawValues[index]})` : known ? value : 'unavailable'}`}
              className="flex h-5 min-w-0 items-center justify-center font-mono text-[9px] font-semibold tabular-nums"
              style={{
                backgroundColor: !known || intensity === 0
                  ? '#0f172a'
                  : `hsl(${210 - intensity * 210} 85% ${25 + intensity * 20}%)`,
                color: saturated ? '#fbbf24' : known ? '#fff' : '#64748b',
              }}
            >
              {saturated ? 'SAT' : known ? value : '—'}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function HandPressure({ side, data, now, replay = false }) {
  const isLive = Boolean(data) && now - data.receivedAt <= STALE_AFTER_MS;
  const displayOrder = side === 'left' ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
  const validValues = (data?.fingers || []).flatMap((finger) => (
    (finger?.values || []).filter(Number.isFinite)
  ));
  const saturatedCount = (data?.fingers || []).reduce((n, finger) => n + (finger?.saturated?.filter(Boolean).length || 0), 0);
  const status = !data ? (replay ? 'No sample' : 'Waiting') : !isLive ? 'Stale' : saturatedCount ? 'Saturated' : validValues.length < 45 ? 'Incomplete' : replay ? 'Recorded' : 'Live';
  const peak = validValues.length ? Math.max(...validValues) : null;

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-950/45 px-2 py-2">
      <div className="mb-2 flex items-center gap-1.5">
        <span className={clsx('h-2 w-2 rounded-full', isLive ? 'bg-emerald-400' : 'bg-slate-600')} />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">{side} hand</span>
        <span className="text-[9px] text-slate-400">{status}</span>
        <span className="ml-auto font-mono text-[10px] text-slate-300">Peak {peak ?? '—'}</span>
      </div>
      <div className={clsx('grid grid-cols-5 gap-1.5', !isLive && 'opacity-50')}>
        {displayOrder.map((index) => (
          <FingerPressure key={index} side={side} name={FINGERS[index]} sensor={data?.fingers?.[index]} />
        ))}
      </div>
    </div>
  );
}

export default function TactileHandsPanel({ enabled = true, replayHands, replayTime = 0 }) {
  const replay = replayHands !== undefined;
  const liveHands = useTactilePressureSubscription(enabled && !replay);
  const hands = replay ? replayHands : liveHands;
  const [now, setNow] = useState(Date.now());
  const hasData = Boolean(hands.left || hands.right);
  const { calibration, calibrating, error, startZero } = useTactileCalibration(hands, enabled && !replay);
  const [showRaw, setShowRaw] = useState(false);
  const zeroed = !replay && Boolean(calibration) && !showRaw;
  const displayed = zeroed ? {
    left: zeroHand(hands.left, calibration, 'left'),
    right: zeroHand(hands.right, calibration, 'right'),
  } : hands;
  const canZero = ['left', 'right'].every((side) => completeHand(hands[side]) && now - hands[side].receivedAt < 1000);
  const saturated = ['left', 'right'].some((side) => displayed[side]?.fingers.some((finger) =>
    finger?.saturated?.some(Boolean) || finger?.values.some((v) => v === 255)));


  useEffect(() => {
    if (replay || !hasData) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [hasData, replay]);

  if (!enabled) return null;

  return (
    <div className={clsx(
      'overflow-y-auto rounded-2xl border border-slate-700 bg-gradient-to-b from-slate-800 to-slate-900 p-3 shadow-md',
      replay ? 'h-full w-full min-w-0' : 'h-[85%] min-w-[360px] max-w-[480px] flex-1',
    )}>
      <div className="mb-2">
        <div className="text-sm font-semibold text-white">Tactile · {zeroed ? 'ZEROED' : 'RAW'}</div>
        <div className="text-[10px] text-slate-400">{replay ? `Recorded · ${replayTime.toFixed(2)} s · 3×3 raw pressure per finger` : zeroed ? 'Unloaded baseline subtracted · Small sensor noise may remain' : '3×3 raw pressure per finger'}</div>
      </div>
      {!replay && <div className="mb-2 flex items-center gap-2 text-xs">
        <button type="button" className="rounded bg-sky-700 px-2 py-1 text-white disabled:opacity-40"
          disabled={!canZero || calibrating} onClick={() => { setShowRaw(false); startZero(); }}>
          {calibrating ? 'Zeroing… keep hands unloaded' : 'Zero now'}
        </button>
        {calibration && <button type="button" className="text-slate-300 underline" onClick={() => setShowRaw(!showRaw)}>
          {showRaw ? 'Show zeroed' : 'Show raw'}
        </button>}
      </div>}
      {!replay && error && <div role="alert" className="mb-2 text-xs text-amber-300">{error}</div>}
      {saturated && <div role="status" className="mb-2 text-[10px] text-amber-300">Sensor at maximum (255). SAT cells cannot measure additional pressure; inspect the sensor.</div>}
      <div className="flex flex-col gap-2">
        <HandPressure side="left" data={displayed.left} now={replay ? replayTime * 1000 : now} replay={replay} />
        <HandPressure side="right" data={displayed.right} now={replay ? replayTime * 1000 : now} replay={replay} />
      </div>
      <div className="mt-1.5 flex justify-between text-[9px] text-slate-400">
        <span>Cells in message order · — = unavailable</span>
        <span>Color 0–{PRESSURE_COLOR_MAX}</span>
      </div>
    </div>
  );
}
