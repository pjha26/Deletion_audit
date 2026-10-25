/* Optional browser QA: requires Playwright and an isolated browser, never a user profile. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const url = process.env.AUDIT_URL || 'http://127.0.0.1:8765';
const output = process.env.UI_SCREENSHOT_DIR || path.resolve(root, '../outputs');
const checks = [];

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const context = await chromium.launchPersistentContext(path.join(root,'work',`browser-qa-${Date.now()}`),{
    headless:true, executablePath:process.env.BROWSER_EXECUTABLE || undefined,
    viewport:{width:1440,height:1050}
  });
  const errors=[];
  try {
    const page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    await page.locator('.person-name').waitFor();
    const summary=await page.evaluate(()=>fetch('/api/summary').then(r=>r.json()));
    assert.equal(await page.locator('.case-row').count(),summary.cases.length);
    checks.push('Real request queue loaded without seeded demonstration data');

    await page.locator('#run-audit').click();
    await page.waitForFunction(()=>document.querySelector('#run-audit').disabled);
    await page.waitForFunction(()=>!document.querySelector('#run-audit').disabled,{},{timeout:60000});
    assert.match(await page.locator('#job-message').innerText(),/finished/);
    checks.push('Run audit control completed real inference and refreshed reports');

    await page.locator('.map-node').last().click();
    assert.ok((await page.locator('#trace-inspector').innerText()).length>30);
    await page.getByRole('tab',{name:/Remediation/}).click();
    assert.ok(await page.locator('.step-row').count()>0);
    checks.push('Clickable map and ordered remediation ledger');
    await page.locator('#case-panel [data-source]').first().click();
    await page.locator('#source-dialog').waitFor({state:'visible'});
    await page.locator('#source-content').waitFor();
    assert.ok((await page.locator('#source-content').innerText()).length>20);
    await page.getByRole('button',{name:'Close source'}).click();
    checks.push('Original text source viewer and modal close');

    const other=summary.cases.find(c=>c.case_id!==summary.cases[0].case_id);
    await page.locator('#case-search').fill(other.case_id);
    await page.locator(`[data-case="${other.case_id}"]`).click();
    await page.waitForFunction(name=>document.querySelector('.person-name').textContent===name,other.name);
    await page.locator('#case-search').fill('');
    await page.locator('[data-filter="COMPLETE"]').click();
    assert.equal(await page.locator('.case-row').count(),summary.counts.COMPLETE);
    await page.locator('[data-filter="all"]').click();
    checks.push('Search, case switching and verdict filters');

    await page.getByRole('button',{name:'Evidence library'}).click();
    await page.locator('.catalog-grid .evidence-item').first().waitFor();
    const files=await page.evaluate(()=>fetch('/api/evidence').then(r=>r.json()));
    assert.equal(await page.locator('.catalog-grid .evidence-item').count(),files.length);
    const image=files.find(f=>f.file_path.endsWith('.png'));
    await page.locator('#evidence-search').fill(image.file_id);
    await page.locator(`.catalog-grid [data-source="${image.file_id}"]`).click();
    await page.locator('#source-content img').waitFor();
    await page.waitForFunction(()=>document.querySelector('#source-content img')?.naturalWidth>0);
    await page.getByRole('button',{name:'Close source'}).click();
    const pdf=files.find(f=>f.file_path.endsWith('.pdf'));
    await page.locator('#evidence-search').fill(pdf.file_id);
    await page.locator(`.catalog-grid [data-source="${pdf.file_id}"]`).click();
    await page.locator('#source-content iframe').waitFor();
    await page.getByRole('button',{name:'Close source'}).click();
    checks.push('Complete evidence library, search, original PNG and PDF views');

    await page.getByRole('button',{name:'Evaluation ledger'}).click();
    await page.locator('.evaluation-metrics').waitFor();
    const evaluation=await page.evaluate(()=>fetch('/api/evaluation').then(r=>r.json()));
    assert.ok((await page.locator('.evaluation-metrics').innerText()).includes(`${(evaluation.metrics.exact_case_accuracy*100).toFixed(1)}%`));
    await page.locator('.report-details summary').click();
    assert.match(await page.locator('#failure-audit-text').innerText(),/Source-backed failure audit/);
    const download=page.waitForEvent('download');
    await page.getByRole('link',{name:/Export all predictions/}).click();
    assert.equal((await download).suggestedFilename(),'output.csv');
    checks.push('Measured evaluation, readable failure audit and CSV download');

    await page.getByRole('button',{name:'Investigations'}).click();
    await page.locator('[data-case]').first().click();
    await page.getByRole('tab',{name:/Trace map/}).click();
    await page.locator('.map-node').first().waitFor();
    await page.evaluate(()=>{document.activeElement.blur();window.scrollTo(0,0);});
    await page.screenshot({path:path.join(output,'audit-desk.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.locator('.mobile-system').first().waitFor({state:'visible'});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.locator('.mobile-system').last().click();
    await page.evaluate(()=>{document.activeElement.blur();window.scrollTo(0,0);});
    await page.screenshot({path:path.join(output,'audit-desk-mobile.png'),fullPage:true});
    await page.setViewportSize({width:768,height:1024});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    checks.push('390px mobile and 768px tablet layouts without page overflow');
    assert.deepEqual(errors,[]);
    const report={passed:true,checks,console_errors:errors,viewports:[1440,390,768],run_at:new Date().toISOString()};
    fs.writeFileSync(path.join(root,'work/browser_results.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally {await context.close();}
})().catch(error=>{console.error(error);process.exit(1)});
