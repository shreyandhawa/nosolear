// @vitest-environment node
import { encodeWav } from "./wav";

// The API test `test_web_encoder_bytes_are_accepted_by_the_upload_route` builds the same bytes,
// pins the same digest and posts them to the upload route.
const API_TEST_SHA256 = "e8d62151e71b3d5d29b5093f29eba3375014b376c61df77e22bdf1b357ac7e6d";

function sawtooth(): Float32Array {
  return Float32Array.from({ length: 16000 }, (_, i) => ((i % 40) - 20) / 20);
}

test("encodes synthetic samples as a valid 16 kHz mono 16-bit WAV the upload route accepts", async () => {
  const wav = encodeWav(sawtooth());
  const view = new DataView(wav.buffer);
  const text = (at: number) => String.fromCharCode(...wav.slice(at, at + 4));
  expect(text(0)).toBe("RIFF");
  expect(view.getUint32(4, true)).toBe(wav.length - 8);
  expect(text(8)).toBe("WAVE");
  expect(text(12)).toBe("fmt ");
  expect(view.getUint16(20, true)).toBe(1);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(24, true)).toBe(16000);
  expect(view.getUint16(34, true)).toBe(16);
  expect(text(36)).toBe("data");
  expect(view.getUint32(40, true)).toBe(32000);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", wav));
  expect(Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("")).toBe(API_TEST_SHA256);
});
