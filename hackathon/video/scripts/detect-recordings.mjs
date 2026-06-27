import {existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const recordingsDir = join(root, 'public', 'recordings');
const manifestPath = join(root, 'src', 'video', 'media.generated.ts');

const firstExisting = (names) => {
  for (const name of names) {
    if (existsSync(join(recordingsDir, name))) {
      return `recordings/${name}`;
    }
  }
  return null;
};

const recordings = {
  codexClip: firstExisting([
    'codex-auth-selftest.mp4',
    'codex-auth-selftest.mov',
    'codex-auth-selftest.webm'
  ]),
  goalchainerClip: firstExisting([
    'goalchainer-demo.mp4',
    'goalchainer-demo.mov',
    'goalchainer-demo.webm'
  ]),
  voiceover: firstExisting([
    'voiceover.wav',
    'voiceover.mp3',
    'voiceover.m4a',
    'voiceover.aac'
  ])
};

const source = `export type RecordingManifest = {
  codexClip: string | null;
  goalchainerClip: string | null;
  voiceover: string | null;
};

export const recordings: RecordingManifest = ${JSON.stringify(recordings, null, 2)};
`;

mkdirSync(dirname(manifestPath), {recursive: true});
writeFileSync(manifestPath, source, 'utf8');

for (const [slot, value] of Object.entries(recordings)) {
  console.log(`${slot}=${value ?? 'missing'}`);
}
