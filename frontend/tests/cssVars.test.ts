import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

// 정의되지 않은 CSS 변수를 쓰면 var(--이름, 라이트 색)의 기본값만 쓰이게 되어 다크모드에서도 라이트 색이 남는다
// (로그인 창에서 다크모드 입력 글자가 안 보였던 원인). 쓰는 변수는 모두 styles.css에서 정의돼 있어야 한다.

const SRC = join(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(css|ts|tsx)$/.test(name) ? [path] : [];
  });
}

test("var(--이름)으로 쓰는 CSS 변수는 모두 styles.css에서 정의돼 있다", () => {
  const defined = new Set([...readFileSync(join(SRC, "styles.css"), "utf8").matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]));
  assert.ok(defined.size > 5, "styles.css에서 변수 정의를 찾지 못했다");

  const undefinedUses: string[] = [];
  for (const file of sourceFiles(SRC)) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)) {
      if (!defined.has(m[1])) undefinedUses.push(`${file.slice(SRC.length + 1)}: ${m[1]}`);
    }
  }
  assert.deepEqual(undefinedUses, [], `정의되지 않은 CSS 변수를 쓰고 있다:\n${undefinedUses.join("\n")}`);
});

test("로그인 창 같은 화면 컴포넌트에 색을 직접 적은 인라인 스타일이 없다", () => {
  const hardcoded: string[] = [];
  for (const file of sourceFiles(join(SRC, "features"))) {
    const text = readFileSync(file, "utf8");
    // style={{ ... color/background/border: "#xxxxxx" ... }}
    for (const m of text.matchAll(/style=\{\{[^}]*#[0-9a-fA-F]{3,8}[^}]*\}\}/g)) {
      hardcoded.push(`${file.slice(SRC.length + 1)}: ${m[0].slice(0, 60)}`);
    }
  }
  assert.deepEqual(hardcoded, [], `테마를 따르지 않는 하드코딩 색이 있다:\n${hardcoded.join("\n")}`);
});
