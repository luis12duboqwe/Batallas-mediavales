import { useEffect } from 'react';
import { useCityStore } from '../store/cityStore';
import { formatDate } from '../utils/format';

const MessagesView = () => {
  const { messages, loadMessages } = useCityStore();

  useEffect(() => {
    loadMessages().catch(() => {});
  }, [loadMessages]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Mensajes</h1>
          <p className="text-gray-400">Comunicados y avisos del sistema</p>
        </div>
      </div>
      <div className="space-y-2">
        {messages.length === 0 && <p className="text-gray-500">Sin mensajes.</p>}
        {messages.map((m) => (
          <div key={m.id} className="card p-4 flex items-start justify-between">
            <div>
              <h3 className="text-lg">{m.title}</h3>
              <p className="text-gray-300 text-sm">{m.body}</p>
            </div>
            <span className="text-xs text-gray-500">{formatDate(m.createdAt)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MessagesView;
