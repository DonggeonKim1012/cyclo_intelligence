import { encodeFilePath } from './fileUrl';

test.each(['/data-api/rosbag-list', '/data-api/replay-data', '/files'])(
  'preserves newlines in recorded task paths through %s', (prefix) => {
    const path = '/workspace/rosbag2/Task_000650_Pick_and_hold_two_items\n_MCAP/1';
    const url = new URL(`${prefix}${encodeFilePath(path)}`, 'http://localhost:7080');
    expect(url.pathname).toContain('items%0A_MCAP');
    expect(decodeURIComponent(url.pathname)).toBe(`${prefix}${path}`);
    expect(url.search).toBe('');
    expect(url.hash).toBe('');
  },
);

test('preserves literal percent escapes, spaces, tabs, Unicode and URL delimiters in video paths', () => {
  const path = '/workspace/rosbag2/작업 #1?100%\t%0A/1/videos/left camera.mp4';
  const url = new URL(`/files${encodeFilePath(path)}`, 'http://localhost:7080');
  expect(decodeURIComponent(url.pathname)).toBe(`/files${path}`);
  expect(url.search).toBe('');
  expect(url.hash).toBe('');
});

test('keeps ordinary replay paths unchanged', () => {
  const path = '/workspace/rosbag2/Task_1_MCAP/1/videos/camera.mp4';
  expect(encodeFilePath(path)).toBe(path);
});
