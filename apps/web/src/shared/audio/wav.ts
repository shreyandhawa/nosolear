export const SAMPLE_RATE = 16000;

/** Linear resampling, enough for speech going to a 16 kHz scorer. */
export function resample(samples: Float32Array, fromRate: number, toRate = SAMPLE_RATE): Float32Array {
  if (fromRate === toRate) return samples;
  const out = new Float32Array(Math.floor((samples.length * toRate) / fromRate));
  const step = fromRate / toRate;
  for (let i = 0; i < out.length; i++) {
    const at = i * step;
    const lo = Math.floor(at);
    const hi = Math.min(lo + 1, samples.length - 1);
    out[i] = samples[lo] + (samples[hi] - samples[lo]) * (at - lo);
  }
  return out;
}

/** A mono 16-bit PCM WAV. `x * 32768` below zero and `x * 32767` above, rounded half up. */
export function encodeWav(samples: Float32Array, sampleRate = SAMPLE_RATE): Uint8Array<ArrayBuffer> {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => {
    const x = Math.max(-1, Math.min(1, s));
    view.setInt16(44 + i * 2, Math.round(x < 0 ? x * 32768 : x * 32767), true);
  });
  return new Uint8Array(view.buffer);
}

export function joinChunks(chunks: Float32Array[]): Float32Array {
  const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}

export function rms(samples: Float32Array): number {
  let sum = 0;
  for (const s of samples) sum += s * s;
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}
