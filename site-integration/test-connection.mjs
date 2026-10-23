// Node 24+ runs the small TypeScript modules directly; no site build needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {handlePhotoAnalysis} from './app/lib/photo-analysis-proxy.ts';
import {validateAnalysis} from './app/lib/photo-analysis.ts';

const valid = () => ({status:'completed',coverage:{status:'available',value:{coverage_percent:42},confidence:.8,version:'fixture'},growth_form:{status:'available',value:{growth_form:'foliose'},confidence:.9,version:'fixture'},media:{coverage_mask:'data:image/png;base64,YQ=='},warnings:[]});
test('accepts zero coverage; rejects invalid predictions and unsafe images',()=>{
 const v=valid();v.coverage.value.coverage_percent=0;assert.equal(validateAnalysis(v).coverage.value.coverage_percent,0);
 v.coverage.value.coverage_percent=NaN;assert.throws(()=>validateAnalysis(v));
 const m=valid();m.media.coverage_mask='https://untrusted.invalid/image';assert.throws(()=>validateAnalysis(m));
 const f=valid();f.growth_form.value.growth_form='invented';assert.throws(()=>validateAnalysis(f));
 const uncertain=valid();uncertain.growth_form={status:'rejected_low_confidence',version:'fixture',value:{growth_form:'uncertain'}};assert.doesNotThrow(()=>validateAnalysis(uncertain));
});
test('proxy fails clearly when unconfigured and rejects another origin',async()=>{
 assert.equal((await handlePhotoAnalysis(new Request('https://site.example/api/analyze',{method:'POST'}),{})).status,503);
 assert.equal((await handlePhotoAnalysis(new Request('https://site.example/api/analyze',{method:'POST',headers:{origin:'https://another.example'}}),{})).status,403);
});
test('proxy forwards the real file and secret only to the configured service',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async(url,options)=>{
   assert.equal(url.href,'https://analysis.example/analyze');assert.equal(options.headers.Authorization,'Bearer fixture-only');
   const req=new Request(url,{method:'POST',body:options.body,headers:options.headers});
   const file=(await req.formData()).get('image');assert.equal(await file.text(),'fixture pixels');
   return Response.json(valid());
  };
  const form=new FormData();form.append('image',new Blob(['fixture pixels'],{type:'image/png'}),'fixture.png');
  const r=await handlePhotoAnalysis(new Request('https://site.example/api/analyze',{method:'POST',body:form,headers:{origin:'https://site.example'}}),{ECOSIGNAL_ANALYSIS_URL:'https://analysis.example',ECOSIGNAL_ANALYSIS_TOKEN:'fixture-only'});
  assert.equal(r.status,200);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal((await r.json()).coverage.value.coverage_percent,42);
 }finally{globalThis.fetch=original;}
});
test('proxy bounds uploads and reports unavailable upstream without HTML leakage',async()=>{
 const env={ECOSIGNAL_ANALYSIS_URL:'https://analysis.example',ECOSIGNAL_ANALYSIS_TOKEN:'fixture-only'};
 const huge=new Request('https://site.example/api/analyze',{method:'POST',headers:{'content-type':'multipart/form-data; boundary=x','content-length':'99999999'},body:'x'});
 assert.equal((await handlePhotoAnalysis(huge,env)).status,413);
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>new Response('<secret-host-error>',{status:502,headers:{'content-type':'text/html'}});
  const form=new FormData();form.append('image',new Blob(['x']),'x.png');
  const r=await handlePhotoAnalysis(new Request('https://site.example/api/analyze',{method:'POST',body:form}),env);
  assert.equal(r.status,502);assert.ok(!(await r.text()).includes('secret-host-error'));
 }finally{globalThis.fetch=original;}
});
