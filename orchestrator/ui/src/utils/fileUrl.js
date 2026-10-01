// Encode raw filesystem names before URL parsing can strip newlines or treat
// filename characters as query strings, fragments, or existing escape sequences.
export function encodeFilePath(path) {
  return path.split('/').map(encodeURIComponent).join('/');
}
