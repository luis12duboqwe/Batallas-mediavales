import { useEffect } from 'react';
import { useSocket } from '../context/SocketContext';
import toast, { Toaster } from 'react-hot-toast';
import soundManager from '../services/sound';

const NotificationListener = () => {
    const socket = useSocket();

    useEffect(() => {
        if (!socket) return;

        const handleNotification = (data) => {
            console.log("Notification received:", data);
            
            // Play sound
            if (data.type === 'attack_incoming') {
                soundManager.playSFX('attack_incoming');
                toast.error(`¡ATAQUE ENTRANTE! ${data.body}`, {
                    duration: 10000,
                    position: 'top-center',
                    style: {
                        background: '#ef4444',
                        color: '#fff',
                        fontWeight: 'bold',
                    },
                });
            } else if (data.type === 'building_complete') {
                soundManager.playSFX('building_complete');
                toast.success(data.title, {
                    style: {
                        background: '#22c55e',
                        color: '#fff',
                    },
                });
            } else if (data.type === 'troop_trained') {
                soundManager.playSFX('troop_trained');
                toast.success(data.title, {
                    style: {
                        background: '#3b82f6',
                        color: '#fff',
                    },
                });
            } else {
                soundManager.playSFX('message_received');
                toast(data.title);
            }
        };

        socket.on('notification', handleNotification);

        return () => {
            socket.off('notification', handleNotification);
        };
    }, [socket]);

    return <Toaster />;
};

export default NotificationListener;
