const ts = require('C:/Users/user2/Desktop/GrowthOS/growthos-web/node_modules/typescript');
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync('C:/Users/user2/AppData/Local/Temp/claude/C--Users-user2-Desktop-GrowthOS-AiAddicts-growthos/d6307b7c-ffd1-451e-88f9-0fa36df63c8a/scratchpad/render_src.ts','utf8');
const js = ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const m = {exports:{}}; vm.runInNewContext(js,{module:m,exports:m.exports,console,Math,Number,String,Object,Array,JSON});
const out = m.exports.buildManualSystemPrompt(process.argv[2], process.argv[3], process.argv[4]);
fs.writeFileSync(process.argv[5], out, 'utf8'); console.log(out.length);
