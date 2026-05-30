/** @type {import('@playwright/test').PlaywrightTestConfig} */
module.exports = {
  testDir: "./tests",
  testMatch: ["**/*.spec.cjs", "**/*.spec.ts"],
  reporter: "line",
};
