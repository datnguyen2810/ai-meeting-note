import assert from 'node:assert/strict';
import test from 'node:test';
import { parseInline, parseSummary } from '../src/utils/summaryMarkdown.js';

test('summary sections and assignments render as structured blocks', () => {
  const blocks = parseSummary('### Phân công công việc\r\n- **chị Lan:** chuẩn bị báo cáo.\r\n- **anh Minh:** kiểm thử. **Cần xác nhận.**\r\n\r\n*Thời hạn giữ nguyên theo phiên âm.*');
  assert.deepEqual(blocks.map(block => block.type), ['heading', 'list', 'paragraph']);
  assert.equal(blocks[1].items.length, 2);
  assert.equal(blocks[1].items[0][0].type, 'strong');
  assert.equal(blocks[1].items[0][0].children[0].text, 'chị Lan:');
  assert.equal(blocks[2].children[0].type, 'em');
});

test('escaped source Markdown stays literal inside formatted assignments', () => {
  const tokens = parseInline('**anh An:** đọc \\*\\*mẫu\\*\\* và \\[ghi chú\\].');
  assert.equal(tokens[0].type, 'strong');
  assert.equal(tokens[1].type, 'text');
  assert.equal(tokens[1].text, ' đọc **mẫu** và [ghi chú].');
});

test('HTML and URLs from source remain text tokens', () => {
  const source = '<img src=x onerror=alert(1)> [mở](javascript:alert(1))';
  assert.deepEqual(parseInline(source), [{ type: 'text', text: source }]);
});

test('plain warnings and blank summaries work without Markdown', () => {
  assert.deepEqual(parseSummary(''), []);
  const blocks = parseSummary('Không thể hoàn tất tóm tắt.\nVui lòng thử lại.');
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type, 'paragraph');
});
