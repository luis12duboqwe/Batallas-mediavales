import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import IntroAnimation from './components/IntroAnimation.jsx';
import NotificationListener from './components/NotificationListener.jsx';
import ConnectionStatus from './components/ConnectionStatus.jsx';
import { useUserStore } from './store/userStore.js';
import { SESSION_EXPIRED_EVENT } from './utils/transportState.js';
import { SocketProvider } from './context/SocketContext.jsx';
import './index.css';
import './i18n';

// Register before React mounts so an early expired-token response cannot be lost.
window.addEventListener(SESSION_EXPIRED_EVENT, () => {
  useUserStore.getState().expireSession();
});

const ExperienceShell = () => {
  const [introFinished, setIntroFinished] = useState(false);
  const [showLoading, setShowLoading] = useState(false);

  const handleIntroComplete = () => {
    setIntroFinished(true);
    setShowLoading(true);
  };

  const handleLoadingComplete = () => {
    setShowLoading(false);
  };

  return (
    <>
      {!introFinished && <IntroAnimation onComplete={handleIntroComplete} />}
      {showLoading && <LoadingScreen onComplete={handleLoadingComplete} />}
      <NotificationListener />
      <ConnectionStatus />
      <App />
    </>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <SocketProvider>
        <ExperienceShell />
      </SocketProvider>
    </BrowserRouter>
  </React.StrictMode>
);
