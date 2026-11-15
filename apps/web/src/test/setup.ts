import "@testing-library/jest-dom/vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// jsdom has no WebGL: the 3D microphone is verified by screenshot in the browser instead.
vi.mock("../shared/audio/MicScene", () => ({ default: () => null }));
