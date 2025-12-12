import { useState, useEffect, useRef } from 'react';
import { useUserStore } from '../store/userStore';

const ChatWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const ws = useRef(null);
  const messagesEndRef = useRef(null);
  const { token, user } = useUserStore();

  useEffect(() => {
    if (isOpen && !ws.current && token) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/chat/global?token=${token}`;
      
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('Connected to global chat');
      };

      ws.current.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            setMessages((prev) => [...prev, data]);
        } catch (e) {
            console.error("Error parsing chat message", e);
        }
      };

      ws.current.onclose = () => {
        console.log('Disconnected from global chat');
        ws.current = null;
      };
      
      ws.current.onerror = (error) => {
          console.error("WebSocket error", error);
      };
    }

    return () => {
      if (!isOpen && ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
  }, [isOpen, token]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = (e) => {
    e.preventDefault();
    if (!input.trim() || !ws.current) return;
    ws.current.send(input);
    setInput('');
  };

  if (!user) return null;

  return (
    <div className={`fixed bottom-4 right-4 z-50 flex flex-col items-end`}>
      {isOpen && (
        <div className="bg-gray-900 border border-amber-700 rounded-lg w-80 h-96 flex flex-col shadow-xl mb-2">
          <div className="bg-gray-800 p-2 rounded-t-lg flex justify-between items-center border-b border-gray-700">
            <span className="font-bold text-amber-500">Chat Global</span>
            <button onClick={() => setIsOpen(false)} className="text-gray-400 hover:text-white">✕</button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {messages.map((msg, idx) => (
              <div key={idx} className="text-sm break-words">
                <span className="font-bold text-amber-600">{msg.username}: </span>
                <span className="text-gray-300">{msg.message}</span>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          <form onSubmit={sendMessage} className="p-2 border-t border-gray-700 flex">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="flex-1 bg-black/50 border border-gray-600 rounded px-2 py-1 text-sm text-white"
              placeholder="Mensaje..."
            />
          </form>
        </div>
      )}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="bg-amber-700 hover:bg-amber-600 text-white rounded-full p-3 shadow-lg"
      >
        💬
      </button>
    </div>
  );
};

export default ChatWidget;
