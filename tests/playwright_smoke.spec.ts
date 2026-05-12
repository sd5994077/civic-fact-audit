import { test } from '@playwright/test';

test('cfa filters smoke', async ({ page }) => {
  await page.goto('http://localhost:3001', { waitUntil: 'networkidle' });
  await page.waitForSelector('#filter-race');
  await page.waitForSelector('#filter-stage');

  const raceOptions = await page.$$eval('#filter-race option', opts => opts.map(o => `${(o as HTMLOptionElement).value}|${o.textContent?.trim() || ''}`));
  const stageOptionsInitial = await page.$$eval('#filter-stage option', opts => opts.map(o => `${(o as HTMLOptionElement).value}|${o.textContent?.trim() || ''}`));
  console.log('RACE_OPTIONS', JSON.stringify(raceOptions));
  console.log('STAGE_OPTIONS', JSON.stringify(stageOptionsInitial));

  await page.fill('#filter-min-confidence', '0.90');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(700);
  const titleAfterApply = await page.locator('#panel-title').innerText();
  const rowsAfterApply = await page.locator('#issue-list .issue-row').count();
  console.log('AFTER_APPLY', titleAfterApply.trim(), rowsAfterApply);

  await page.click('#filter-reset');
  await page.waitForTimeout(700);
  const minAfterReset = await page.inputValue('#filter-min-confidence');
  const rowsAfterReset = await page.locator('#issue-list .issue-row').count();
  console.log('AFTER_RESET', minAfterReset, rowsAfterReset);

  const hasRunoff = stageOptionsInitial.some(s => s.startsWith('primary_runoff|'));
  const hasPrimary = stageOptionsInitial.some(s => s.startsWith('primary|'));

  if (hasRunoff) {
    await page.selectOption('#filter-stage', 'primary_runoff');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(700);
    const t = await page.locator('#panel-title').innerText();
    const c = await page.locator('#issue-list .issue-row').count();
    console.log('RUNOFF_RESULT', t.trim(), c);
  }

  if (hasPrimary) {
    await page.selectOption('#filter-stage', 'primary');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(700);
    const t = await page.locator('#panel-title').innerText();
    const s = await page.locator('#panel-summary').innerText();
    const c = await page.locator('#issue-list .issue-row').count();
    console.log('PRIMARY_RESULT', t.trim(), c, s.trim());
  }
});
