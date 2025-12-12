import React, { createContext, useContext, useEffect, useState } from 'react';
import io from 'socket.io-client';
import useAuthStore from '../store/authStore';

const SocketContext = createContext();

export const useSocket = () => useContext(SocketContext);

export const SocketProvider = ({ children }) => {
    const [socket, setSocket] = useState(null);
    const { user, token } = useAuthStore();

    useEffect(() => {
        if (user && token) {
            const newSocket = io('/', {
                path: '/socket.io',
                transports: ['websocket'],
                auth: {
                    token: token
                },
                query: {
                    user_id: user.id
                }
            });

            newSocket.on('connect', () => {
                console.log('Socket connected');
                newSocket.emit('join', { user_id: user.id });
            });

            newSocket.on('disconnect', () => {
                console.log('Socket disconnected');
            });

            newSocket.on('connect_error', (err) => {
                console.error('Socket connection error:', err);
            });

            setSocket(newSocket);

            return () => newSocket.close();
        } else {
            if (socket) {
                socket.close();
                setSocket(null);
            }
        }
    }, [user, token]);

    return (
        <SocketContext.Provider value={socket}>
            {children}
        </SocketContext.Provider>
    );
};
