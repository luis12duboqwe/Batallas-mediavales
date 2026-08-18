import React, { createContext, useContext, useEffect, useState } from 'react';
import io from 'socket.io-client';
import { useUserStore } from '../store/userStore';

const SocketContext = createContext();

export const useSocket = () => useContext(SocketContext);

export const SocketProvider = ({ children }) => {
    const [socket, setSocket] = useState(null);
    const token = useUserStore((state) => state.token);

    useEffect(() => {
        if (token) {
            const newSocket = io('/', {
                path: '/socket.io',
                transports: ['websocket'],
                auth: {
                    token,
                },
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

            return () => newSocket.close();
        }

        setSocket((currentSocket) => {
            currentSocket?.close();
            return null;
        });

        return undefined;
    }, [token]);

    return (
        <SocketContext.Provider value={socket}>
            {children}
        </SocketContext.Provider>
    );
};
