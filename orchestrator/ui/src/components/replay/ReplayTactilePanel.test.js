import { act, render, screen } from '@testing-library/react';
import ReplayTactilePanel, { handAtTime } from './ReplayTactilePanel';
import rosConnectionManager from '../../utils/rosConnectionManager';

jest.mock('react-redux', () => ({
  useSelector: (select) => select({ ros: { rosbridgeUrl: 'ws://test' } }),
}));
jest.mock('../../utils/rosConnectionManager', () => ({ getConnection: jest.fn() }));

const message = (side, value) => ({ sensors: Array.from({ length: 5 }, (_, index) => ({
  sensor_name: `finger_${side}_sensor${index + 1}`,
  pressure_values: Array(9).fill(value),
})) });
const tactileData = {
  left: { timestamps: [0, 1, 2], messages: [message('l', 10), message('l', 20), message('l', 30)] },
  right: { timestamps: [0.5, 1.5], messages: [message('r', 40), message('r', 50)] },
};

test('selects each hand independently without future values, including backward seeks', () => {
  expect(handAtTime(tactileData.right, 0)).toBeNull();
  expect(handAtTime(tactileData.left, 1).fingers[0].values[0]).toBe(20);
  expect(handAtTime(tactileData.right, 1).fingers[0].values[0]).toBe(40);
  expect(handAtTime(tactileData.left, 2.5).fingers[0].values[0]).toBe(30);
  expect(handAtTime(tactileData.left, 0.2).fingers[0].values[0]).toBe(10);
  expect(handAtTime(undefined, 5)).toBeNull();
});

test('follows seeks, stays fresh while paused, and never subscribes or applies live calibration', () => {
  jest.useFakeTimers();
  localStorage.setItem('cyclo:tactile-zero:v1:ws://test', JSON.stringify({
    version: 1, createdAt: Date.now(), hands: Object.fromEntries(['left', 'right'].map((side) => [
      side, Object.fromEntries(message(side[0], 8).sensors.map((sensor) => [
        sensor.sensor_name, { baseline: sensor.pressure_values },
      ])),
    ])),
  }));
  const view = render(<ReplayTactilePanel tactileData={tactileData} currentTime={1} />);
  expect(screen.getByLabelText('left Thumb cell 1: 20')).toHaveTextContent('20');
  expect(screen.getByLabelText('right Thumb cell 1: 40')).toHaveTextContent('40');
  expect(screen.queryByRole('button', { name: 'Zero now' })).not.toBeInTheDocument();
  act(() => jest.advanceTimersByTime(10000));
  expect(screen.getAllByText('Recorded')).toHaveLength(2);
  expect(rosConnectionManager.getConnection).not.toHaveBeenCalled();
  view.rerender(<ReplayTactilePanel tactileData={tactileData} currentTime={0} />);
  expect(screen.getByLabelText('left Thumb cell 1: 10')).toBeInTheDocument();
  expect(screen.getByLabelText('right Thumb cell 1: unavailable')).toHaveTextContent('—');
  view.rerender(<ReplayTactilePanel tactileData={tactileData} currentTime={5} />);
  expect(screen.getAllByText('Stale')).toHaveLength(2);
  view.rerender(<ReplayTactilePanel tactileData={{}} currentTime={0} />);
  expect(screen.getAllByText('No sample')).toHaveLength(2);
  expect(screen.getByLabelText('left Thumb cell 1: unavailable')).toHaveTextContent('—');
  view.unmount();
  localStorage.clear();
  jest.useRealTimers();
});
