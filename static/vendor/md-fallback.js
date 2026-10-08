
// minimal markdown fallback if CDN fails
window.__mdFallback = function(text) {
  if (!text) return "";
  var s = text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  s = s.replace(/```([\s\S]*?)```/g, function(_, c){ return "<pre><code>"+c+"</code></pre>"; });
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  s = s.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  s = s.replace(/^\* (.*)$/gm, "<li>$1</li>");
  s = s.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
  s = s.replace(/\n\n/g, "</p><p>");
  return "<p>"+s+"</p>";
};
