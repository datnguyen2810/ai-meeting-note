import { parseSummary } from '../utils/summaryMarkdown';
import './SummaryContent.css';

function inline(tokens) {
  return tokens.map((token, index) => {
    if (token.type === 'strong') return <strong key={index}>{inline(token.children)}</strong>;
    if (token.type === 'em') return <em key={index}>{inline(token.children)}</em>;
    return token.text;
  });
}

export default function SummaryContent({ text }) {
  return (
    <div className="meeting-summary">
      {parseSummary(text).map((block, index) => {
        if (block.type === 'heading') return <h3 key={index}>{inline(block.children)}</h3>;
        if (block.type === 'list') {
          return <ul key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}</ul>;
        }
        return <p key={index}>{inline(block.children)}</p>;
      })}
    </div>
  );
}
