import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { flushCapture, padPcmFrame } from '../src/utils/flushCapture.js';
import { encodeWav } from '../src/utils/encodeWav.js';

function capture(rate = 16000) {
  let Processor;
  const sent = [];
  const sandbox = {
    sampleRate: rate,
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: (message) => sent.push(message) }; } },
    registerProcessor: (_, implementation) => { Processor = implementation; },
  };
  const code = readFileSync(new URL('../public/capture.worklet.js', import.meta.url), 'utf8');
  vm.runInNewContext(code, sandbox);
  return { worklet: new Processor(), sent };
}

test('flush keeps partial frames and chunk tails in the exported WAV', async () => {
  const { worklet, sent } = capture();
  // One normal 200ms packet plus 50ms and 10 extra samples left in the buffer.
  worklet.process([[new Float32Array(4010).fill(0.25)]]);
  assert.equal(sent.length, 1);
  worklet.port.onmessage({ data: { type: 'flush' } });
  assert.equal(sent.length, 3);
  assert.equal(sent[0].byteLength, 6400);
  assert.equal(sent[1].byteLength, 1620);
  assert.equal(sent[2].type, 'flushed');
  const wav = encodeWav([new Int16Array(sent[0]), new Int16Array(sent[1])], 16000);
  const header = new DataView(await wav.arrayBuffer());
  assert.equal(header.getUint32(40, true), 8020);
  assert.equal(wav.size, 44 + 8020);
  worklet.process([[new Float32Array(3200).fill(1)]]);
  assert.equal(sent.length, 3);
  worklet.port.onmessage({ data: { type: 'flush' } });
  assert.equal(sent.length, 4); // idempotent: acknowledge, never duplicate audio
});

test('a recording shorter than one VAD frame is not discarded locally', () => {
  const { worklet, sent } = capture();
  worklet.process([[new Float32Array(100).fill(0.5)]]);
  worklet.port.onmessage({ data: { type: 'flush' } });
  assert.equal(sent[0].byteLength, 200);
  const padded = padPcmFrame(sent[0]);
  assert.equal(padded.byteLength, 640);
  assert.deepEqual([...new Uint8Array(padded).slice(0, 200)], [...new Uint8Array(sent[0])]);
  assert.ok([...new Uint8Array(padded).slice(200)].every(value => value === 0));
});

test('both browser worklet entry points stay identical', () => {
  assert.equal(readFileSync(new URL('../public/capture.worklet.js', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/audio/capture.worklet.js', import.meta.url), 'utf8'));
});

test('flush waits for PCM before acknowledging completion and removes its listener', async () => {
  const events = [];
  const listeners = new Set();
  const port = {
    addEventListener: (_, listener) => listeners.add(listener),
    removeEventListener: (_, listener) => listeners.delete(listener),
    postMessage: () => queueMicrotask(() => {
      events.push('pcm');
      for (const listener of listeners) listener({ data: new ArrayBuffer(200) });
      for (const listener of listeners) listener({ data: { type: 'flushed' } });
    }),
  };
  assert.equal(await flushCapture({ port }), true);
  events.push('stop');
  assert.deepEqual(events, ['pcm', 'stop']);
  assert.equal(listeners.size, 0);
});

test('flush failure is bounded for missing or stopped processors', async () => {
  assert.equal(await flushCapture(null), false);
  assert.equal(await flushCapture({ port: { addEventListener() {}, removeEventListener() {}, postMessage() {} } }, 1), false);
});
