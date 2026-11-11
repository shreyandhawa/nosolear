import { ESLint } from "eslint";

test("a feature importing another feature is a lint error", async () => {
  const eslint = new ESLint();
  const [result] = await eslint.lintText(
    'import { HomePage } from "../home/HomePage";\nexport const x = HomePage;\n',
    { filePath: "src/features/other/Bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});

test("shared importing a feature is a lint error", async () => {
  const eslint = new ESLint();
  const [result] = await eslint.lintText(
    'import { HomePage } from "../../features/home/HomePage";\nexport const y = HomePage;\n',
    { filePath: "src/shared/lib/bad.ts" },
  );
  expect(result.messages.some((m) => m.ruleId?.startsWith("boundaries/"))).toBe(true);
});
