import assert from 'node:assert/strict';
import {mkdirSync} from 'node:fs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  mkdirSync('test-output',{recursive:true});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
    await page.setViewportSize({width,height});await page.goto('http://127.0.0.1:8783/');
    assert.match(await page.locator('main').innerText(),/尚无已生成的日报/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    await page.screenshot({path:'test-output/'+name+'.png',fullPage:true});
    await page.goto('http://127.0.0.1:8783/status.html');await page.getByRole('heading',{name:'数据源状态',exact:true}).waitFor();
  }
  assert.deepEqual(errors,[]);console.log('Desktop/mobile preview and source-status routes passed');
}finally{await browser.close();}
