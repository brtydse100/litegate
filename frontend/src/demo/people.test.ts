import { afterEach, expect, it, vi } from "vitest";
import { installDemoApi } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());
it("serves synthetic SSO/no-key people and applies email search and pagination locally", async () => {
  vi.stubGlobal("fetch", vi.fn());
  installDemoApi();
  const result = await (
    await fetch(
      new URL(
        "/api/v1/people?search=no-key&size=1&page=1",
        window.location.origin,
      ),
    )
  ).json();
  expect(result).toMatchObject({
    page: 1,
    size: 1,
    total: 1,
    total_pages: 1,
    users: [{ user_id: "demo-sso-no-key", email: "no-key@example.com" }],
  });
});
