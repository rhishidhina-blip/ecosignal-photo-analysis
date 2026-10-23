/** Apply focused changes to an existing EcoSignal checkout. Run with its path. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(process.argv[2] || '.');
const here = path.dirname(fileURLToPath(import.meta.url));
const pagePath = path.join(root, 'app/page.tsx');
const workerPath = path.join(root, 'worker/index.ts');
let page = fs.readFileSync(pagePath, 'utf8');
let worker = fs.readFileSync(workerPath, 'utf8');
if (page.includes('function cancelPhotoAnalysis()')) throw Error('Photo integration is already installed. No files changed.');
function replace(before, after) {
  if (!page.includes(before) || page.indexOf(before) !== page.lastIndexOf(before)) throw Error(`Site source differs near: ${before.slice(0,90)}. No files changed. Apply the integration manually to the latest source.`);
  page = page.replace(before, after);
}
replace('import UnifiedPanel from "./unified-panel";', 'import UnifiedPanel from "./unified-panel";\nimport {analyzePhoto} from "./lib/photo-analysis";');
replace('type Observation = {id:string;', 'type Observation = {mask?:string; overlay?:string; model_version?:string; id:string;');
replace('const resultRef=useRef<HTMLInputElement>(null);', `const resultRef=useRef<HTMLInputElement>(null);
const [analyzing,setAnalyzing]=useState(false),[analysisError,setAnalysisError]=useState("");
const photoFile=useRef<File|null>(null),photoRequest=useRef<AbortController|null>(null),photoGeneration=useRef(0);
useEffect(()=>()=>{photoRequest.current?.abort()},[]);
function cancelPhotoAnalysis(){photoGeneration.current++;photoRequest.current?.abort();setAnalyzing(false);setAnalysisError("")}`);
replace('function exampleScan(){', 'function exampleScan(){cancelPhotoAnalysis();');
replace('function showExample(){', 'function showExample(){cancelPhotoAnalysis();');
replace('function tourGo(n:number){', 'function tourGo(n:number){cancelPhotoAnalysis();');
replace('function importResults(f?:File){if(!f)return;', 'function importResults(f?:File){if(!f)return;cancelPhotoAnalysis();');
const readStart = page.indexOf('function readPhoto('), readEnd = page.indexOf('function analyze()',readStart);
if (readStart < 0 || readEnd < 0) throw Error('Cannot find photo upload handler. No files changed.');
page = page.slice(0,readStart) + `function readPhoto(f?:File){
 if(!f)return;
 if(!["image/jpeg","image/png","image/webp"].includes(f.type)){notify("Choose a JPEG, PNG, or WebP photograph.");return}
 if(f.size>8*1024*1024){notify("Choose a photograph under 8 MB.");return}
 cancelPhotoAnalysis();const generation=photoGeneration.current;photoFile.current=f;setPhoto("");setResult(null);setExample(false);
 const reader=new FileReader();reader.onload=()=>{if(generation!==photoGeneration.current)return;setPhoto(String(reader.result));setScanStep(0)};
 reader.onerror=()=>notify("This photograph could not be read.");reader.readAsDataURL(f);
}
` + page.slice(readEnd);
const analyzeStart=page.indexOf('function analyze()'),analyzeEnd=page.indexOf('function save()',analyzeStart);
if(analyzeStart<0||analyzeEnd<0)throw Error('Cannot find analysis handler. No files changed.');
page=page.slice(0,analyzeStart)+`async function analyze(){
 if(example){cancelPhotoAnalysis();setResult({...demo});setScanStep(2);return}
 if(analyzing)return;
 if(!photoFile.current){setAnalysisError("Choose the photograph again before analyzing.");return}
 if((lat.trim()&&!Number.isFinite(Number(lat)))||(lon.trim()&&!Number.isFinite(Number(lon)))||(lat.trim()&&Math.abs(Number(lat))>90)||(lon.trim()&&Math.abs(Number(lon))>180)){setAnalysisError("Check the optional coordinates.");return}
 cancelPhotoAnalysis();const generation=photoGeneration.current,controller=new AbortController();photoRequest.current=controller;
 const timeout=setTimeout(()=>controller.abort(),125000);setAnalyzing(true);setAnalysisError("");setResult(null);
 try{
  const raw=await analyzePhoto(photoFile.current,controller.signal);
  if(generation!==photoGeneration.current)return;
  const cov=raw.coverage,form=raw.growth_form;
  const coverage=cov.status==="available"?cov.value?.coverage_percent:undefined;
  const growth=form.status==="available"?form.value?.growth_form:undefined;
  setResult({id:"OBS-"+Date.now().toString(36).toUpperCase(),site:site||"Unnamed field observation",date:new Date().toISOString(),image:photo,
   latitude:lat.trim()?Number(lat):undefined,longitude:lon.trim()?Number(lon):undefined,
   coverage,form:growth,confidence:form.confidence!==undefined?form.confidence*100:undefined,
   coverage_confidence:cov.confidence,growth_form_confidence:form.confidence,
   mask:raw.media.coverage_mask,overlay:raw.media.coverage_overlay,model_version:cov.version+" / "+form.version,raw_model_output:raw,
   source:"Photo analysis · "+cov.version+" / "+form.version,
   status:raw.status==="completed"?"Analyzed · review suggested":"Analysis needs review",
   notes:substrate+". "+raw.coverage_basis+" "+raw.warnings.join(" ")});setScanStep(2);
 }catch(error){if(generation===photoGeneration.current)setAnalysisError(controller.signal.aborted?"Analysis timed out. Please retry.":error instanceof Error?error.message:"Analysis failed. Please retry.")}
 finally{clearTimeout(timeout);if(generation===photoGeneration.current)setAnalyzing(false)}
}
`+page.slice(analyzeEnd);
replace('This frontend captures your photo and context. New photographs remain pending until real analysis results are imported.', 'Your photograph is sent to the photo-analysis service. Both saved models run automatically when you select Analyze photograph. Coverage refers to the full frame; uncertain predictions require review.');
replace('<Button onClick={analyze}>{example?"View example analysis":"Create observation"}', '<div aria-live="polite">{analyzing&&<p role="status">Analyzing coverage and growth form…</p>}{analysisError&&<p role="alert">{analysisError}</p>}</div><Button disabled={analyzing} onClick={analyze}>{analyzing?"Analyzing…":example?"View example analysis":analysisError?"Retry analysis":"Analyze photograph"}');
replace('{example?<LichenArt overlay/>:<div className="awaiting-mask">', '{example?<LichenArt overlay/>:result?.overlay?<img src={result.overlay} alt="Model-generated lichen coverage overlay"/>:<div className="awaiting-mask">');
replace('<b>Mask not supplied</b>', '<b>Mask unavailable</b>');
replace('<small>Actual segmentation will appear here.</small>', '<small>Check the analysis warnings and retry.</small>');
replace('<b>{result?.form||"Pending"}</b>', '<b>{result?.form||"Uncertain / unavailable"}</b>');
replace('`${result.coverage.toFixed(1)}%`:"Pending"', '`${result.coverage.toFixed(1)}%`:"Needs review"');
replace('<span>Within the analyzed region</span>', '<span>Percent of the full analyzed photograph</span>');
replace('<div className="result-actions"><Button onClick={save}>', '<div className="result-actions">{!example&&<Button secondary disabled={analyzing} onClick={()=>{setScanStep(1);void analyze()}}>Run analysis again</Button>}{result?.mask&&<a className="button secondary" href={result.mask} download="EcoSignal-mask.png">Download mask</a>}<Button onClick={save}>');
replace('<p>{activeRecord.notes}</p><UnifiedPanel', '<p>{activeRecord.notes}</p>{activeRecord.overlay&&<img src={activeRecord.overlay} alt="Saved model-generated lichen overlay" style={{width:"100%",height:"auto",borderRadius:12}}/>}{activeRecord.mask&&<a className="text-button" href={activeRecord.mask} download="EcoSignal-mask.png">Download saved mask</a>}<UnifiedPanel');
replace('Examples are labeled. Real photo predictions require imported model results.', 'Examples are labeled. Analyze your photograph to generate coverage masks and growth-form predictions.');
replace('JPEG, PNG or other browser-supported image · up to 8 MB','JPEG, PNG or WebP · up to 8 MB');
// Preserve the rest of the Worker and existing scoring code.
const importAnchor="import {handleAirQuality} from '../app/lib/air-quality';";
const routeAnchor="if (url.pathname === '/api/air-quality') return handleAirQuality(request);";
if(!worker.includes(importAnchor)||!worker.includes(routeAnchor)||!worker.includes('interface Env {'))throw Error('Worker source differs. No files changed.');
worker=worker.replace(importAnchor,importAnchor+"\nimport {handlePhotoAnalysis} from '../app/lib/photo-analysis-proxy';")
 .replace('interface Env {','interface Env {\n  ECOSIGNAL_ANALYSIS_URL?: string;\n  ECOSIGNAL_ANALYSIS_TOKEN?: string;')
 .replace(routeAnchor,routeAnchor+"\n    if (url.pathname === '/api/analyze') return handlePhotoAnalysis(request, env);");
// All compatibility checks finish before writing any changes.
for(const [target,content] of [[pagePath,page],[workerPath,worker]]){
 if(fs.existsSync(target+'.before-photo-analysis'))throw Error('Backup already exists. No files changed.');
}
for(const [target,content] of [[pagePath,page],[workerPath,worker]]){fs.copyFileSync(target,target+'.before-photo-analysis');fs.writeFileSync(target,content);}
for(const file of ['photo-analysis.ts','photo-analysis-proxy.ts'])fs.copyFileSync(path.join(here,'app/lib',file),path.join(root,'app/lib',file));
console.log('Photo inference integrated. Original page and Worker backed up. Configure the two server secrets, then build and publish the site.');
