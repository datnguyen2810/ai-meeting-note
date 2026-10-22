// Worklet sends its final PCM buffer before acknowledging the flush. Waiting
// for the acknowledgment preserves ordering: final audio -> WebSocket stop.
export function padPcmFrame(buffer) {
  const remainder = buffer.byteLength % 640;
  if (!remainder) return buffer;
  const padded = new Uint8Array(buffer.byteLength + 640 - remainder);
  padded.set(new Uint8Array(buffer));
  return padded.buffer;
}

export function flushCapture(node, timeoutMs = 1000) {
  if (!node) return Promise.resolve(false);
  return new Promise((resolve) => {
    const finish = (flushed) => {
      clearTimeout(timer);
      node.port.removeEventListener('message', onMessage);
      resolve(flushed);
    };
    const onMessage = (event) => {
      if (event.data?.type === 'flushed') finish(true);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    node.port.addEventListener('message', onMessage);
    try {
      node.port.postMessage({ type: 'flush' });
    } catch {
      finish(false);
    }
  });
}
