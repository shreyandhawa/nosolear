// @vitest-environment node
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";

const webRoot = fileURLToPath(new URL("../..", import.meta.url));

async function boundaryMessages(code: string, filePath: string) {
  const eslint = new ESLint({ cwd: webRoot });
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((m) => m.ruleId?.startsWith("boundaries/"));
}

test("a feature importing another feature is a lint error", async () => {
  const eslint = new ESLint({ cwd: webRoot });
  const [result] = await eslint.lintText(
    'import { HomePage } from "../home/HomePage";\nexport const x = HomePage;\n',
    { filePath: "src/features/other/Bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});

test("shared importing a feature is a lint error", async () => {
  const eslint = new ESLint({ cwd: webRoot });
  const [result] = await eslint.lintText(
    'import { HomePage } from "../../features/home/HomePage";\nexport const y = HomePage;\n',
    { filePath: "src/shared/lib/bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});

test("a feature importing from its own folder is allowed", async () => {
  const messages = await boundaryMessages(
    'import { HomePage } from "./HomePage";\nexport const z = HomePage;\n',
    "src/features/home/Other.ts",
  );
  expect(messages).toEqual([]);
});

test("a feature importing app code is a lint error", async () => {
  const messages = await boundaryMessages(
    'import { createAppRouter } from "../../app/router";\nexport const r = createAppRouter;\n',
    "src/features/home/BadApp.ts",
  );
  expect(messages.length).toBeGreaterThan(0);
});
