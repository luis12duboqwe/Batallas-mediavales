import React, { createContext, useContext, useEffect, useState } from 'react';
import io from 'socket.io-client';
import { useUserStore } from '../store/userStore';

const SocketContext = createContext(null);

export const useSocket = () => useContext(SocketContext);

const resolveSocketOrigin = () => {
    if (import.meta.env.VITE_SOCKET_URL) {
        return import.meta.env.VITE_SOCKET_URL;
    }

    const apiUrl = import.meta.env.VITE_API_URL;
    if (apiUrl) {
        try {
            return new URL(apiUrl, window.location.origin).origin;
        } catch {
            // Fall through to same-origin; production Nginx proxies /socket.io.
        }
    }

    return window.location.origin;
};

export const SocketProvider = ({ children }) => {
    const [socket, setSocket] = useState(null);
    const token = useUserStore((state) => state.token);

    useEffect(() => {
        if (!token) {
            setSocket((currentSocket) => {
                currentSocket?.close();
                return null;
            });
            return undefined;
        }

        const newSocket = io(resolveSocketOrigin(), {
            path: '/socket.io',
            transports: ['websocket'],
            auth: { token },
        });

        newSocket.on('connect', () => {
            console.log('Socket connected');
        });

        newSocket.on('disconnect', () => {
            console.log('Socket disconnected');
        });

        newSocket.on('connect_error', (err) => {
            console.error('Socket connection error:', err);
        });

        setSocket(newSocket);

        return () => {
            newSocket.removeAllListeners();
            newSocket.close();
        };
    }, [token]);

    return (
        <SocketContext.Provider value={socket}>
            {children}
        </SocketContext.Provider>
    );
};
