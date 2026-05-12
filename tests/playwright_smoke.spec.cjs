const { test } = require('@playwright/test');

test('cfa filters smoke', async ({ page }) => {
  await page.goto('http://localhost:3001', { waitUntil: 'networkidle' });
  await page.waitForSelector('#filter-race');
  await page.waitForSelector('#filter-stage');

  const raceOptions = await page.$$eval('#filter-race option', (opts) => opts.map((o) => `${o.value}|${(o.textContent || '').trim()}`));
  const stageOptionsInitial = await page.$$eval('#filter-stage option', (opts) => opts.map((o) => `${o.value}|${(o.textContent || '').trim()}`));
  console.log('RACE_OPTIONS', JSON.stringify(raceOptions));
  console.log('STAGE_OPTIONS_INITIAL', JSON.stringify(stageOptionsInitial));

  await page.fill('#filter-min-confidence', '0.90');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(700);
  const titleAfterApply = (await page.locator('#panel-title').innerText()).trim();
  const rowsAfterApply = await page.locator('#issue-list .issue-row').count();
  console.log('AFTER_APPLY', titleAfterApply, rowsAfterApply);

  await page.click('#filter-reset');
  await page.waitForTimeout(700);
  const minAfterReset = await page.inputValue('#filter-min-confidence');
  const rowsAfterReset = await page.locator('#issue-list .issue-row').count();
  console.log('AFTER_RESET', minAfterReset, rowsAfterReset);

  await page.selectOption('#filter-race', { label: 'TX US Senate 2026' });
  await page.waitForTimeout(500);
  const stageOptionsAfterRace = await page.$$eval('#filter-stage option', (opts) => opts.map((o) => `${o.value}|${(o.textContent || '').trim()}`));
  console.log('STAGE_OPTIONS_AFTER_2026', JSON.stringify(stageOptionsAfterRace));

  if (stageOptionsAfterRace.some((s) => s.startsWith('primary_runoff|'))) {
    await page.selectOption('#filter-stage', 'primary_runoff');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(700);
    const t = (await page.locator('#panel-title').innerText()).trim();
    const c = await page.locator('#issue-list .issue-row').count();
    console.log('RUNOFF_RESULT', t, c);
  }

  if (stageOptionsAfterRace.some((s) => s.startsWith('primary|'))) {
    await page.selectOption('#filter-stage', 'primary');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(700);
    const t = (await page.locator('#panel-title').innerText()).trim();
    const s = (await page.locator('#panel-summary').innerText()).trim();
    const c = await page.locator('#issue-list .issue-row').count();
    console.log('PRIMARY_RESULT', t, c, s);
  }
});
