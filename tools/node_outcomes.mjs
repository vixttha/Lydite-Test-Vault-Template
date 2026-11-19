// Capture Node's native names before the TAP display escapes them.
export default async function* report(source) {
  const levels = [];
  for await (const { type, data } of source) {
    if (type !== 'test:pass' && type !== 'test:fail') continue;
    const { name, nesting, details, skip, todo } = data;
    const children = levels[nesting + 1];
    levels[nesting + 1] = undefined;
    const outcome = skip ? 'skip' : todo ? 'todo' : type === 'test:pass' ? 'pass' : 'fail';
    const leaves = children
      ? children.map(({ path, outcome }) => ({ path: [name, ...path], outcome }))
      : details.type === 'suite' ? [] : [{ path: [name], outcome }];
    (levels[nesting] ??= []).push(...leaves);
  }
  yield JSON.stringify({ leaves: levels[0] ?? [] }) + '\n';
}
