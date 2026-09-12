import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function GeminiChat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I am the EV diagnostics assistant. How can I analyze the current battery telemetry for you today?' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.content })
      });

      const data = await response.json();
      
      if (data.error) {
        if (data.error.includes("429")) {
          setMessages(prev => [...prev, { role: 'assistant', content: `API Rate Limit Exceeded (HTTP 429). The Gemini free tier limits requests per minute. Please wait a moment and try again.` }]);
        } else {
          setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.error}` }]);
        }
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Connection error. Please try again later.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[500px] rounded-2xl border border-sky-400/15 bg-gradient-to-br from-slate-950/80 to-slate-900/60 overflow-hidden">
      <div className="p-4 border-b border-white/5 bg-white/5 flex items-center gap-3">
        <Bot className="w-5 h-5 text-sky-400" />
        <h3 className="font-medium text-slate-200">Diagnostics Assistant</h3>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-sky-500/20 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4 text-sky-400" />
              </div>
            )}
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed overflow-hidden ${
              msg.role === 'user' 
                ? 'bg-sky-500/20 text-sky-100 rounded-tr-sm' 
                : 'bg-slate-800/80 text-slate-200 rounded-tl-sm'
            }`}>
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert prose-sm max-w-none prose-p:leading-snug prose-li:my-0">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-slate-300" />
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-3 justify-start">
            <div className="w-8 h-8 rounded-full bg-sky-500/20 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-sky-400" />
            </div>
            <div className="bg-slate-800/80 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center justify-center">
              <Loader2 className="w-4 h-4 text-slate-400 animate-spin" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-white/5 bg-black/20">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input 
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="w-full bg-slate-900 border border-white/10 rounded-full pl-4 pr-12 py-3 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/50 transition-all"
            disabled={isLoading}
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 rounded-full bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 disabled:opacity-50 transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
