import { useEffect, useState } from 'react';
import { useSocket } from '../context/SocketContext';
import { useUserStore } from '../store/userStore';
import { SERVICE_UNAVAILABLE_EVENT, SERVICE_RECOVERED_EVENT } from '../utils/transportState';

const initiallyOnline = () => typeof navigator === 'undefined' || navigator.onLine !== false;

const CONNECTION_MESSAGES = {
  offline: 'Sin conexión a Internet. Algunas acciones no estarán disponibles hasta recuperar la red.',
  service: 'El servidor no está disponible temporalmente. Reintenta en unos momentos.',
  reconnecting: 'Se interrumpió la conexión en tiempo real. Reconectando…',
};

const ConnectionStatus = () => {
  const token = useUserStore((state) => state.token);
  const socket = useSocket();
  const [online, setOnline] = useState(initiallyOnline);
  const [realtime, setRealtime] = useState('idle');
  const [unavailablePath, setUnavailablePath] = useState(null);

  useEffect(() => {
    const onOffline = () => setOnline(false);
    const onOnline = () => setOnline(true);
    window.addEventListener('offline', onOffline);
    window.addEventListener('online', onOnline);
    return () => {
      window.removeEventListener('offline', onOffline);
      window.removeEventListener('online', onOnline);
    };
  }, []);

  useEffect(() => {
    const onUnavailable = (event) => setUnavailablePath(event.detail?.path || '*');
    const onRecovered = (event) => {
      const recoveredPath = event.detail?.path || '*';
      setUnavailablePath((path) => path === recoveredPath ? null : path);
    };
    window.addEventListener(SERVICE_UNAVAILABLE_EVENT, onUnavailable);
    window.addEventListener(SERVICE_RECOVERED_EVENT, onRecovered);
    return () => {
      window.removeEventListener(SERVICE_UNAVAILABLE_EVENT, onUnavailable);
      window.removeEventListener(SERVICE_RECOVERED_EVENT, onRecovered);
    };
  }, []);

  useEffect(() => {
    if (!token || !socket) {
      setRealtime('idle');
      return undefined;
    }
    setRealtime(socket.connected ? 'connected' : 'idle');
    const onConnect = () => setRealtime('connected');
    const onDisconnect = (reason) => {
      if (reason !== 'io client disconnect') {
        setRealtime((status) => status === 'connected' ? 'reconnecting' : status);
      }
    };
    const onFailure = () => setRealtime('reconnecting');
    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('connect_error', onFailure);
    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('connect_error', onFailure);
    };
  }, [socket, token]);

  const status = !online ? 'offline'
    : unavailablePath ? 'service'
      : token && realtime === 'reconnecting' ? 'reconnecting' : null;
  if (!status) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="connection-status"
      data-state={status}
      className="fixed bottom-24 md:bottom-5 left-3 right-3 md:left-auto md:max-w-lg z-[65] rounded-lg border border-amber-600 bg-gray-950 px-4 py-3 shadow-xl text-amber-100 flex gap-3 items-center justify-between"
    >
      <p className="text-sm">{CONNECTION_MESSAGES[status]}</p>
      <button
        type="button"
        className="shrink-0 rounded border border-amber-500 px-3 py-1 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-300"
        onClick={() => window.location.reload()}
      >
        Reintentar
      </button>
    </div>
  );
};

export default ConnectionStatus;
