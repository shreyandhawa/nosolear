import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { alwaysTryTypes: true } },
      "boundaries/elements": [
        { type: "app", pattern: "src/app/**" },
        { type: "feature", pattern: "src/features/*", capture: ["name"] },
        { type: "shared", pattern: "src/shared/**" },
      ],
    },
    rules: {
      "boundaries/dependencies": [
        2,
        {
          default: "disallow",
          policies: [
            {
              from: { element: { type: "app" } },
              allow: { to: { element: { types: ["app", "feature", "shared"] } } },
            },
            {
              from: { element: { type: "feature" } },
              allow: {
                to: [
                  { element: { type: "shared" } },
                  {
                    element: {
                      type: "feature",
                      captured: { name: "{{ from.element.captured.name }}" },
                    },
                  },
                ],
              },
            },
            {
              from: { element: { type: "shared" } },
              allow: { to: { element: { type: "shared" } } },
            },
          ],
        },
      ],
    },
  },
);
