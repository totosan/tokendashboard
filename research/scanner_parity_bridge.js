'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const context = vm.createContext({});
const patternSource = fs.readFileSync(path.join(root, 'dist/pattern.js'), 'utf8');
const tradfiSource = fs.readFileSync(path.join(root, 'dist/tradfi.js'), 'utf8');
vm.runInContext(patternSource, context, { filename: 'dist/pattern.js' });
vm.runInContext(tradfiSource, context, { filename: 'dist/tradfi.js' });

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
if (!Array.isArray(input.cases) || input.cases.length > 32) {
  throw new Error('Expected at most 32 finite fixture cases');
}

const output = input.cases.map(item => {
  if (!Array.isArray(item.candles) || item.candles.length > 2000) {
    throw new Error(`Invalid bounded candle fixture: ${item.name}`);
  }
  if (item.scanner === 'pattern') {
    return {
      name: item.name,
      output: context.PulsePattern.detect(item.candles, item.end, item.options || {})
    };
  }
  if (item.scanner === 'tradfi') {
    return {
      name: item.name,
      output: vm.runInContext(
        `tradfiPattern(${JSON.stringify(item.candles)}, ${Number(item.end)}, ${Number(item.minImpulse)})`,
        context
      )
    };
  }
  throw new Error(`Unsupported scanner: ${item.scanner}`);
});

process.stdout.write(JSON.stringify({ cases: output }));
