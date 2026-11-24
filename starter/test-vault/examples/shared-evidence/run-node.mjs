import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const testFile = fileURLToPath(new URL('./app.test.mjs', import.meta.url));
const app = fileURLToPath(new URL('./app.mjs', import.meta.url));
const caseFile = fileURLToPath(new URL('./case.json', import.meta.url));
const sourceCommit = fileURLToPath(new URL('../../source_commit.py', import.meta.url));
const checkout = execFileSync(process.env.VAULT_EXAMPLE_PYTHON || 'python3', [
  sourceCommit, fileURLToPath(import.meta.url), testFile, app, caseFile,
], { encoding: 'utf8' }).trim();
const plan = readFileSync(caseFile);
const suite = spawnSync(process.execPath, ['--test', testFile], { stdio: 'inherit' });
if (suite.error) throw suite.error;
const evidence = readFileSync(process.env.VAULT_EXAMPLE_EVIDENCE);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const receipt = {
  schema_version: 2,
  case_id: JSON.parse(plan).case_id,
  case_plan_sha256: digest(plan),
  check_id: 'node-test',
  checkout_sha: checkout,
  run_id: process.env.GITHUB_RUN_ID,
  attempt: process.env.GITHUB_RUN_ATTEMPT,
  environment: { os: process.platform, runtime: process.version },
  status: suite.status === 0 ? 'pass' : 'fail',
  evidence_sha256: digest(evidence),
};
writeFileSync(join(process.env.VAULT_EXAMPLE_RECEIPTS, 'node.json'), JSON.stringify(receipt) + '\n');
process.exitCode = suite.status === 0 ? 0 : 1;
