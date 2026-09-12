// Capture screenshots of Phase 6/7 pages for visual verification
import { chromium } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_URL = 'http://localhost:5174';
const OUT_DIR = path.resolve(__dirname, '../screenshots');

interface Shot {
  name: string;
  path: string;
  before?: string;
}

const shots: Shot[] = [
  { name: 'phase6-graph-overview', path: '/graph' },
  { name: 'phase7-notes-overview', path: '/notes' },
];

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Local single-machine setup: go straight to the target page
  await page.goto(`${BASE_URL}/`);

  for (const shot of shots) {
    await page.goto(`${BASE_URL}${shot.path}`);
    await page.waitForLoadState('networkidle');
    // Give the lazy-loaded component time to render
    await page.waitForTimeout(2000);
    const out = path.join(OUT_DIR, `${shot.name}.png`);
    await page.screenshot({ path: out, fullPage: false });
    console.log(`Saved ${out}`);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
