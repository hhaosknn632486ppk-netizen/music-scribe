// Validation-only official Essentia.js 0.1.3 frontend. Not shipped as runtime.
const fs = require('node:fs');
const path = require('node:path');
const wasm = require(path.join(process.env.ESSENTIA_REFERENCE_DIR || path.join(__dirname, 'package'), 'dist/essentia-wasm.umd.js'));
const Essentia = require(path.join(process.env.ESSENTIA_REFERENCE_DIR || path.join(__dirname, 'package'), 'dist/essentia.js-core.umd.js'));
const engine = new Essentia(wasm);
try {
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const report = [];
for (const item of manifest) {
  const raw = fs.readFileSync(item.path);
  const data = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
  const output = [];
  let frameCount;
  if (item.kind === 'frames') {
    frameCount = data.length / 512;
    for (let i = 0; i < frameCount; i++) {
      const frame = engine.arrayToVector(data.subarray(i * 512, (i + 1) * 512));
      const bands = engine.TensorflowInputMusiCNN(frame).bands;
      output.push(...engine.vectorToArray(bands));
      frame.delete(); bands.delete();
    }
  } else {
    const frames = engine.FrameGenerator(data, 512, 256);
    frameCount = frames.size();
    for (let i = 0; i < frameCount; i++) {
      const frame = frames.get(i);
      const bands = engine.TensorflowInputMusiCNN(frame).bands;
      output.push(...engine.vectorToArray(bands));
      frame.delete(); bands.delete();
    }
    frames.delete();
  }
  const result = new Float32Array(output);
  fs.writeFileSync(item.output, Buffer.from(result.buffer));
  report.push({name: item.name, frames: frameCount, bands: 96});
}
console.log(JSON.stringify(report));
} catch(e) { console.error('Reference failed: '+String(e)); process.exitCode=1; }

