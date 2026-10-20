// The summary API emits headings, lists and emphasis. Parse that small subset
// into text tokens; source text never becomes HTML or an executable link.
const ESCAPABLE = new Set('\\`*_{}[]<>#|!');

function closingMarker(text, marker, start) {
  for (let index = text.indexOf(marker, start); index !== -1; index = text.indexOf(marker, index + marker.length)) {
    let slashes = 0;
    for (let previous = index - 1; previous >= 0 && text[previous] === '\\'; previous--) slashes++;
    if (slashes % 2 === 0) return index;
  }
  return -1;
}

export function parseInline(text) {
  const tokens = [];
  let buffer = '';
  const flush = () => {
    if (buffer) tokens.push({ type: 'text', text: buffer });
    buffer = '';
  };
  for (let index = 0; index < text.length;) {
    if (text[index] === '\\' && ESCAPABLE.has(text[index + 1])) {
      buffer += text[index + 1];
      index += 2;
      continue;
    }
    const marker = text.startsWith('**', index) ? '**' : text[index] === '*' ? '*' : null;
    if (marker) {
      const end = closingMarker(text, marker, index + marker.length);
      if (end > index + marker.length) {
        flush();
        tokens.push({ type: marker === '**' ? 'strong' : 'em', children: parseInline(text.slice(index + marker.length, end)) });
        index = end + marker.length;
        continue;
      }
    }
    buffer += text[index++];
  }
  flush();
  return tokens;
}

export function parseSummary(text) {
  const blocks = [];
  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    if (!line.trim()) continue;
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const bullet = line.match(/^-\s+(.+)$/);
    if (heading) {
      blocks.push({ type: 'heading', children: parseInline(heading[1]) });
    } else if (bullet) {
      if (blocks.at(-1)?.type !== 'list') blocks.push({ type: 'list', items: [] });
      blocks.at(-1).items.push(parseInline(bullet[1]));
    } else {
      blocks.push({ type: 'paragraph', children: parseInline(line) });
    }
  }
  return blocks;
}
