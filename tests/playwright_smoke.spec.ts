import { test } from '@playwright/test';
import fs from 'fs';
import http from 'http';
import path from 'path';

function contentTypeFor(filePath: string): string {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.js')) return 'application/javascript; charset=utf-8';
  if (filePath.endsWith('.css')) return 'text/css; charset=utf-8';
  if (filePath.endsWith('.svg')) return 'image/svg+xml';
  if (filePath.endsWith('.png')) return 'image/png';
  return 'application/octet-stream';
}

async function startFrontendStaticServer(frontendRoot: string): Promise<{ server: http.Server; baseUrl: string }> {
  const server = http.createServer((req, res) => {
    const urlPath = (req.url || '/').split('?')[0];
    let relativePath = decodeURIComponent(urlPath);
    if (relativePath === '/') relativePath = '/index.html';

    const fullPath = path.resolve(frontendRoot, `.${relativePath}`);
    const normalizedRoot = path.resolve(frontendRoot);
    if (!fullPath.startsWith(normalizedRoot)) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }

    fs.readFile(fullPath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      res.writeHead(200, { 'Content-Type': contentTypeFor(fullPath) });
      res.end(data);
    });
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address() as { port: number };
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}`,
  };
}

test('cfa filters smoke', async ({ page }) => {
  let localServer: { server: http.Server; baseUrl: string } | null = null;
  const webUrl = process.env.CFA_WEB_URL || '';
  if (!webUrl) {
    localServer = await startFrontendStaticServer(path.resolve(__dirname, '../frontend'));
  }
  const baseUrl = webUrl || localServer.baseUrl;

  try {
    await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
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
  } finally {
    if (localServer?.server) {
      await new Promise<void>((resolve) => localServer.server.close(() => resolve()));
    }
  }
});
